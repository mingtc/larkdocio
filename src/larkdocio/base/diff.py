"""larkdocio.base.diff — the typed diff over an in-memory Base table model (LD-257).

**This module issues no requests and makes no network call.** It is the Base parity of
:mod:`larkdocio.write.reconcile`, whose docstring states the same property for docx, and the
property is *structural* rather than incidental: nothing here imports a client, a transport,
or an HTTP library, and a guard over this file's own AST says so
(``tests/test_base_model.py::test_ac2_neither_module_imports_a_client_or_a_transport``).
Compiling a disposition into a ``batch_create`` / ``batch_update`` / ``batch_delete`` request
is the next rung's (LD-259); encoding a *value* for the wire is LD-256's registry. Neither is
imported here, in either direction.

**Identity comes from the record id, never from content.** A Base record has a
``record_id``, which is precisely the identity anchor ``reconcile.py``'s first rule demands,
so a diff is meaningful here in a way it never was for a grid. There is deliberately no
content-based fallback: two records with identical cells are two records.

**Every record gets exactly one disposition** — :data:`UNCHANGED`, :data:`EDITED`,
:data:`CREATED`, :data:`DELETED` or :data:`REFUSED` — and the set is *exhaustive* over the
model: every record in the snapshot and every record added in memory appears once and only
once. That is the apply-log completeness property (the ``capabilities()`` contract of the
same name, spelled there and only there), enforced one layer earlier where it is cheap.

**A refusal is record-level, and it is a disposition rather than an exception.** A caller who
edited a computed cell gets a plan that says so, with the type named and the reason quoted
from :mod:`larkdocio.base.write_vocabulary`; they do not get a traceback, and they do not get
a plan that half-applies. The eight computed / opaque pairs are **imported** from that module
— LD-255 authored them once so that this story and LD-256 could share the constant instead of
depending on each other.

**A link is never dereferenced here.** Three rules, from the P0 pack's own captures:

* a ``SingleLink`` **dangles** after its target record is deleted — ``p0-2-07`` shows
  ``SingleLinkOne`` / ``SingleLinkMany`` still holding the deleted ``recvrftvdQu0a2`` — so a
  dangling id is a **normal state** the model represents, not an error it raises;
* an edit to a ``DuplexLink`` cell has an effect in **another table**: the mirror there
  auto-populates with the reverse link, with **no write to that table at all** (``p0-2-05``).
  The diff **discloses** it as a :class:`CrossTableEffect` rather than silently performing it;
* a link field whose ``property.table_name`` has **dropped out** while ``table_id`` remains is
  a **dangling target** — the whole target table was deleted (``p0-5-02``: ``SLink`` reads back
  ``{"multiple": true, "table_id": "tblsT2Ons4CcdJgY"}``, no name) — and is surfaced as such.

**Ordering is documented, not dict-iteration order** (AC8). Dispositions come out in
*snapshot read order* first — every record the table had, whether it was touched or not —
then the records added in memory, in the order they were added. Within an ``edited`` record,
cell changes come out in **field order**, which is ``GET …/fields`` order, the same projection
L1 renders a row against. So the same snapshot diffed against the same edits twice yields a
byte-identical plan structure.
"""
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Tuple

from larkdocio.base.cells import FieldSpec
from larkdocio.base.referential import DUPLEX_LINK, SINGLE_LINK
from larkdocio.base.referential import has_dangling_target as _has_dangling_target
from larkdocio.base.write_vocabulary import is_non_writable, non_writable_reason

#: The record was in the snapshot and nothing about it moved.
UNCHANGED = "unchanged"
#: The record was in the snapshot and at least one cell moved.
EDITED = "edited"
#: The record was added in memory and is not in the snapshot.
CREATED = "created"
#: The record was in the snapshot and is marked for deletion.
DELETED = "deleted"
#: The record's edit cannot be planned — a computed / opaque cell was written.
REFUSED = "refused"

#: Every disposition, in the order a plan reads best. Exhaustive by construction.
DISPOSITIONS: Tuple[str, ...] = (UNCHANGED, EDITED, CREATED, DELETED, REFUSED)

#: What an edit to a symmetric link does in the *other* table, in a caller's terms.
DUPLEX_MIRROR_EFFECT = (
    "Writing this symmetric link also populates its mirror field in the linked table — the "
    "server does that itself, with no write to that table in the plan."
)

#: What a link field whose target table has been deleted looks like.
DANGLING_TARGET_EFFECT = (
    "This link field's target table no longer exists: the schema still carries its table_id "
    "but the table_name has dropped out, which is what a deleted target table reads like."
)


# --------------------------------------------------------------------------- #
# The pieces of a disposition                                                  #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class CellChange:
    """One cell that moved: which field, and from what to what.

    ``before`` is the value the snapshot carried — L1's own rendered cell, never a second
    opinion — and ``after`` is what the caller put there. A field the record never carried a
    key for has an ``before`` of whatever its *absence* renders as, because an empty cell in
    ``records/search`` is an **absent key**, not an empty string.
    """

    field_id: str
    field_name: str
    field_type: Optional[int]
    ui_type: str
    before: str
    after: str

    @property
    def pair(self) -> Tuple[Optional[int], str]:
        return (self.field_type, self.ui_type)


@dataclass(frozen=True)
class Refusal:
    """One cell that cannot be written, and why — the reason quoted from LD-255's constant."""

    field_name: str
    pair: Tuple[Optional[int], str]
    reason: str


@dataclass(frozen=True)
class CrossTableEffect:
    """One disclosed effect **outside this table**. The plan never writes it; it says it."""

    field_name: str
    pair: Tuple[Optional[int], str]
    table_id: Optional[str]
    table_name: Optional[str]
    effect: str
    dangling_target: bool = False


@dataclass(frozen=True)
class RecordDisposition:
    """Exactly one per record — the typed answer to "what happens to this row?"."""

    record_id: str
    disposition: str
    changes: Tuple[CellChange, ...] = ()
    refusals: Tuple[Refusal, ...] = ()
    cross_table: Tuple[CrossTableEffect, ...] = ()

    @property
    def is_new(self) -> bool:
        return self.disposition == CREATED


@dataclass(frozen=True)
class TableDiff:
    """One table's dispositions, carrying **its own** anchor.

    ``revision`` is the ``table.revision`` the snapshot was taken at, and it travels with the
    diff because ``table.revision`` is **per-table isolated** (``05-08``: the untouched second
    table stayed at ``0`` while the edited one advanced ``18 → 19``, and the *app* revision did
    not move at all). Nothing here re-reads it.
    """

    table_id: str
    name: str
    revision: Optional[int]
    dispositions: Tuple[RecordDisposition, ...]

    def of(self, disposition: str) -> Tuple[RecordDisposition, ...]:
        """Every record with one disposition, in plan order."""
        if disposition not in DISPOSITIONS:
            raise ValueError(
                f"{disposition!r} is not a disposition; expected one of {DISPOSITIONS}")
        return tuple(entry for entry in self.dispositions
                     if entry.disposition == disposition)

    def record(self, record_id: str) -> RecordDisposition:
        for entry in self.dispositions:
            if entry.record_id == record_id:
                return entry
        raise KeyError(record_id)

    @property
    def refusals(self) -> Tuple[Refusal, ...]:
        return tuple(refusal for entry in self.dispositions for refusal in entry.refusals)

    @property
    def cross_table_effects(self) -> Tuple[CrossTableEffect, ...]:
        return tuple(effect for entry in self.dispositions for effect in entry.cross_table)

    @property
    def touches_nothing(self) -> bool:
        """True when every record is ``unchanged`` — a plan with nothing in it."""
        return all(entry.disposition == UNCHANGED for entry in self.dispositions)


@dataclass(frozen=True)
class BaseDiff:
    """A multi-table diff. **Per-table by construction** — each entry carries its own anchor,
    so a halt scoped to one table is coherent."""

    app_token: str
    tables: Tuple[TableDiff, ...]

    def table(self, table_id: str) -> TableDiff:
        for entry in self.tables:
            if entry.table_id == table_id:
                return entry
        raise KeyError(table_id)

    @property
    def refusals(self) -> Tuple[Refusal, ...]:
        return tuple(refusal for entry in self.tables for refusal in entry.refusals)

    @property
    def cross_table_effects(self) -> Tuple[CrossTableEffect, ...]:
        return tuple(effect for entry in self.tables for effect in entry.cross_table_effects)


# --------------------------------------------------------------------------- #
# Link-field reading — schema only, never a dereference                        #
# --------------------------------------------------------------------------- #

def is_link_field(spec: FieldSpec) -> bool:
    """``True`` for the two link pairs. Nothing here follows one."""
    return spec.pair in (SINGLE_LINK, DUPLEX_LINK)


def link_target(spec: FieldSpec) -> Tuple[Optional[str], Optional[str]]:
    """A link field's ``(table_id, table_name)`` **as the schema reports them**."""
    prop = spec.property if isinstance(spec.property, dict) else {}
    return prop.get("table_id"), prop.get("table_name")


#: ``True`` when a link field's target **table** is gone — the detector the P0 pack found by
#: accident (``p0-5-02``): deleting the target table leaves ``property.table_id`` in place and
#: **drops ``table_name``**. **Re-exported, never re-spelled:** the signature is authored once
#: in :mod:`larkdocio.base.referential`, with its three outcomes, its evidence and its revisit
#: trigger, and every leg that needs it — this one and the destructive scan — resolves to that
#: single function, so a second definition cannot drift away from the first.
has_dangling_target = _has_dangling_target


def _effects_for(spec: FieldSpec) -> Tuple[CrossTableEffect, ...]:
    """What a write to this cell does outside this table, disclosed rather than performed."""
    if not is_link_field(spec):
        return ()
    table_id, table_name = link_target(spec)
    effects = []
    if spec.pair == DUPLEX_LINK:
        effects.append(CrossTableEffect(
            field_name=spec.field_name, pair=spec.pair, table_id=table_id,
            table_name=table_name, effect=DUPLEX_MIRROR_EFFECT))
    if has_dangling_target(spec):
        effects.append(CrossTableEffect(
            field_name=spec.field_name, pair=spec.pair, table_id=table_id,
            table_name=None, effect=DANGLING_TARGET_EFFECT, dangling_target=True))
    return tuple(effects)


# --------------------------------------------------------------------------- #
# The diff                                                                     #
# --------------------------------------------------------------------------- #

def _change(spec: FieldSpec, before: str, after: str) -> CellChange:
    return CellChange(field_id=spec.field_id, field_name=spec.field_name,
                      field_type=spec.type, ui_type=spec.ui_type,
                      before=before, after=after)


def _refusal(spec: FieldSpec) -> Refusal:
    return Refusal(field_name=spec.field_name, pair=spec.pair,
                   reason=non_writable_reason(spec.pair) or "")


def _disposition_for(record_id, specs, before_cells, written, created):
    """One record's disposition, walking the fields **in schema order**.

    ``written`` maps a field name to the value the caller put there; ``before_cells`` maps a
    field name to what the snapshot held (empty for a created record, which had nothing).
    """
    changes = []
    refusals = []
    effects = []
    for spec in specs:
        if spec.field_name not in written:
            continue
        before = before_cells.get(spec.field_name, "")
        after = written[spec.field_name]
        if is_non_writable(spec.pair):
            refusals.append(_refusal(spec))
            changes.append(_change(spec, before, after))
            continue
        if not created and after == before:
            continue  # a no-op edit is not a change; it is not written down as one
        changes.append(_change(spec, before, after))
        effects.extend(_effects_for(spec))
    if refusals:
        disposition = REFUSED
    elif created:
        disposition = CREATED
    elif changes:
        disposition = EDITED
    else:
        disposition = UNCHANGED
    return RecordDisposition(record_id=record_id, disposition=disposition,
                             changes=tuple(changes), refusals=tuple(refusals),
                             cross_table=tuple(effects))


def diff_table(
    snapshot,
    *,
    edits: Mapping[str, Mapping[str, str]] = None,
    additions: Sequence = (),
    deletions: Sequence[str] = (),
) -> TableDiff:
    """One table's snapshot + the edits held against it → one :class:`TableDiff`.

    Pure, offline and deterministic: no request is issued, nothing is re-read, and the output
    order is snapshot order then addition order (never dict-iteration order).

    ``snapshot`` is a :class:`~larkdocio.base.model.BaseTableSnapshot`; it is duck-typed here
    so this module can stay free of any import that could reach a client.
    """
    edits = edits or {}
    specs = tuple(snapshot.fields)
    dispositions = []
    for record in snapshot.records:
        if record.record_id in set(deletions):
            dispositions.append(RecordDisposition(record_id=record.record_id,
                                                  disposition=DELETED))
            continue
        dispositions.append(_disposition_for(
            record.record_id, specs, dict(record.cells),
            edits.get(record.record_id, {}), created=False))
    for local_id, written in additions:
        dispositions.append(_disposition_for(local_id, specs, {}, written, created=True))
    return TableDiff(table_id=snapshot.table_id, name=snapshot.name,
                     revision=snapshot.revision, dispositions=tuple(dispositions))
