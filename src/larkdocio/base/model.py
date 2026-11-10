"""larkdocio.base.model — the in-memory Base table model.

A Base **is** a table with a schema, and the thing a consumer holds in their head is *rows*,
not ranges. So the write spine is the document-style one: the caller takes a
**snapshot**, edits a projection of it, and hands it back; the library — not the caller —
does the diffing, inside the gate, where it can be typed and refused.

Three properties, each a data-safety one rather than a nicety.

**1. A snapshot is complete or it is not a snapshot.** The model is built from the *landed*
structured intermediate (:func:`larkdocio.base.read.read_base` →
:class:`~larkdocio.base.table.BaseRead` / :class:`~larkdocio.base.table.BaseTableRead`), never
from a raw payload — a second parse of the wire would be a second definition of what a Base
cell is. And it is built only from a read that can **prove it reached the end**. The shipped
client walks a cursor to exhaustion and stops safely under every shape of early end, but it
cannot *report* that it stopped early; :class:`ReadProof` reads that off the page bodies the
walk actually saw, and :func:`snapshot_table` refuses a walk that did not finish. **Why this
is rule 1 and not a footnote: a diff over a partial snapshot reads the unseen rows as
DELETIONS.** The named shape is the **ten phantom rows** — a freshly created Base's default
table ships with 10 auto-provisioned empty rows, which fooled the opener's own probe 05, and
``05-07``'s first page still reads *10 items, ``has_more: true``, ``total: 12``*.

**2. The model is not a cache, and its age is visible.** A snapshot carries the
``table.revision`` it was taken at, and that anchor is what the plan is built against. **No
re-read ever happens implicitly** — a consumer holding a stale model finds out at
``dry_run`` / ``apply`` (the compare-and-swap), never by a silent refresh, and the diff
cannot know that a record was deleted in Lark since the snapshot. An anchorless snapshot is
refused at construction, because ``table.revision`` is the *only* compare-and-swap anchor
bitable exposes: ``05-08`` sent ``revision`` and ``last_modified_time`` as body keys and got
``code:0`` with both **silently ignored**, so there is no server-side precondition to fall
back on.

**3. Anchors are per-table.** ``table.revision`` is per-table isolated (``05-08``: the
untouched second table stayed at ``0`` while the edited one advanced ``18 → 19``, and the app
revision did not move at all), so a multi-table draft produces a per-table diff with one
anchor each.

**No network call is made here, in any leg**, and nothing in this module imports a client —
the reading was already done by L1. The diff itself lives in :mod:`larkdocio.base.diff`, and
a syntax-tree check over both files holds the property structurally.
"""
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from larkdocio.base import diff as base_diff
from larkdocio.base.cells import FieldSpec
from larkdocio.base.table import BaseRead, BaseTableRead
from larkdocio.errors import LarkDocIOError

#: Prefix of the id a record added in memory carries until the server assigns it a real one.
#: A caller can tell the two apart at a glance, and a real ``record_id`` never looks like this.
NEW_RECORD_PREFIX = "new:"


class BaseModelError(LarkDocIOError):
    """Something about the in-memory model itself is wrong — not an API refusal."""


class IncompleteSnapshot(BaseModelError):
    """A read that cannot prove it saw the whole table may not become a model."""


class UnknownRecord(BaseModelError):
    """An edit named a record the snapshot does not hold."""


class UnknownField(BaseModelError):
    """An edit named a field the table's schema does not have.

    Adding one is a **schema** change, which this layer does not make — so it is a
    programming error here rather than a refusal in the plan.
    """


class RawNotRetained(BaseModelError):
    """The raw wire values were asked for and were never kept.

    Retention is **opt-in** (``read_base(url, retain_raw=True)``), so the honest answer here
    is a refusal that names the flag — not an empty dict, which would read as *"the cells were
    empty"* about cells nobody looked at.
    """


# --------------------------------------------------------------------------- #
# The paging proof                                                             #
# --------------------------------------------------------------------------- #

def _attr(body, name):
    """One field off a page body, whether it is an SDK object or a plain dict."""
    if isinstance(body, Mapping):
        return body.get(name)
    return getattr(body, name, None)


@dataclass(frozen=True)
class ReadProof:
    """Whether the walk that produced a snapshot reached the end of the table, and why it
    stopped.

    This is a **reading of the walk**, not a second walk: it takes the page bodies the client
    already fetched and classifies the last one. The termination shapes are exactly the ones
    :meth:`larkdocio.base.client.BaseReadClient._walk_pages` recognises — the walk believes the
    cursor rather than the ``has_more`` flag — and only one of them is exhaustion.
    """

    pages: int
    records: int
    exhausted: bool
    stopped_because: str

    @classmethod
    def from_pages(cls, bodies: Sequence) -> "ReadProof":
        """Classify the page bodies a cursor walk actually saw."""
        bodies = list(bodies or ())
        records = sum(len(_attr(body, "items") or ()) for body in bodies)
        if not bodies:
            return cls(pages=0, records=0, exhausted=False,
                       stopped_because="no page was read at all")
        seen = set()
        for index, body in enumerate(bodies):
            token = _attr(body, "page_token")
            last = index == len(bodies) - 1
            if not _attr(body, "has_more"):
                if last:
                    return cls(pages=len(bodies), records=records, exhausted=True,
                               stopped_because="the last page said there is no more")
                return cls(
                    pages=len(bodies), records=records, exhausted=False,
                    stopped_because=(
                        "these pages are not one walk: a page said there is no more and "
                        "further pages follow it"))
            if not token:
                return cls(
                    pages=len(bodies), records=records, exhausted=False,
                    stopped_because=(
                        "the server claimed there is more and handed back no cursor to ask "
                        "for it"))
            if token in seen:
                return cls(
                    pages=len(bodies), records=records, exhausted=False,
                    stopped_because=(
                        "the server handed back a cursor it had already given, which would "
                        "replay the same page forever"))
            seen.add(token)
        return cls(
            pages=len(bodies), records=records, exhausted=False,
            stopped_because=(
                "the walk stopped with a live cursor still in hand — there are more rows in "
                "the table than this read saw"))


# --------------------------------------------------------------------------- #
# The snapshot                                                                 #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SnapshotRecord:
    """One record, projected against the field list.

    ``cells`` is ``(field_name, value)`` in **field order** — L1's own rendered, unescaped
    cell text, never a second opinion about what a Base cell looks like.

    ``raw_fields`` is the **opt-in** second artefact beside it: the record's ``fields`` body
    exactly as Lark returned it, present only when the read that produced this snapshot was
    taken with ``retain_raw=True``. Two accessors, symmetric with the rendered pair —
    :meth:`value` / :meth:`as_dict` for what a person reads, :meth:`raw` / :meth:`raw_as_dict`
    for what the server said.
    """

    record_id: str
    cells: Tuple[Tuple[str, str], ...]
    #: The wire body, untouched — or ``None`` when raw was not retained.
    raw_fields: Optional[Mapping[str, Any]] = None

    def value(self, field_name: str) -> str:
        for name, value in self.cells:
            if name == field_name:
                return value
        raise UnknownField(f"the table has no field named {field_name!r}")

    def as_dict(self) -> Dict[str, str]:
        return dict(self.cells)

    def raw(self, field_name: str, default=None):
        """One cell's value **exactly as Lark returned it**, or ``default``.

        The three answers this can give are three different facts, and none of them is
        collapsed into another:

        * a field the **table's schema** does not have raises :class:`UnknownField` — a typo
          is a programming error, exactly as it is for :meth:`value`;
        * a read that did not retain raw raises :class:`RawNotRetained`, naming the flag;
        * a field the schema **has** and this record's body did **not carry** returns
          ``default`` — an empty cell is an *absent key* in ``records/search``, which is the
          wire's own silence rather than an error. **Absence is not the same as a ``null``
          value**: a consumer who must tell the two apart reads :attr:`raw_fields` (or
          :meth:`raw_as_dict`) and tests the key, which is the distinction preserved intact.

        No conversion happens on the way out. An epoch is an ``int``, a Person is the list of
        dicts the API sent, an Email is its segment array with the ``mailto:`` link and the
        plain address both present — which is the whole point: comparing rendered Markdown is
        how the same address in two forms reads as two different vendors.
        """
        if not any(name == field_name for name, _value in self.cells):
            raise UnknownField(f"the table has no field named {field_name!r}")
        if self.raw_fields is None:
            raise RawNotRetained(
                f"record {self.record_id!r} carries no raw values: this snapshot came from a "
                "read taken without them. Take the read again with "
                "read_base(url, retain_raw=True) — it costs no extra API call, only memory.")
        return self.raw_fields.get(field_name, default)

    def raw_as_dict(self) -> Dict[str, Any]:
        """The whole wire body as a plain dict — a **copy**, so a caller cannot corrupt the
        read it came from. An absent key stays absent; refuses, typed, when nothing was
        retained."""
        if self.raw_fields is None:
            raise RawNotRetained(
                f"record {self.record_id!r} carries no raw values: this snapshot came from a "
                "read taken without them. Take the read again with "
                "read_base(url, retain_raw=True) — it costs no extra API call, only memory.")
        return dict(self.raw_fields)


@dataclass(frozen=True)
class BaseTableSnapshot:
    """One table as it stood at ``revision`` — its schema, its rows, and its paging proof."""

    app_token: str
    table_id: str
    name: str
    fields: Tuple[FieldSpec, ...]
    records: Tuple[SnapshotRecord, ...]
    revision: Optional[int]
    read_proof: ReadProof

    @property
    def width(self) -> int:
        return len(self.fields)

    @property
    def record_ids(self) -> Tuple[str, ...]:
        return tuple(record.record_id for record in self.records)

    @property
    def raw_retained(self) -> bool:
        """Whether every record here carries its raw wire body — i.e. whether the read behind
        this snapshot was taken with ``retain_raw=True``.

        A table with **no records** answers ``True`` vacuously: nothing is missing its raw.
        The per-record question is :attr:`SnapshotRecord.raw_fields`, and the loud form is
        :meth:`SnapshotRecord.raw`, which refuses rather than returning an empty structure.
        """
        return all(record.raw_fields is not None for record in self.records)

    def field(self, field_name: str) -> FieldSpec:
        for spec in self.fields:
            if spec.field_name == field_name:
                return spec
        raise UnknownField(
            f"table {self.table_id!r} has no field named {field_name!r}. Adding one is a "
            "schema change, which this layer does not do.")

    def record(self, record_id: str) -> SnapshotRecord:
        for record in self.records:
            if record.record_id == record_id:
                return record
        raise UnknownRecord(
            f"table {self.table_id!r} holds no record {record_id!r} — identity comes from "
            "the record id, never from content.")

    @property
    def dangling_link_targets(self) -> Tuple[str, ...]:
        """Link fields whose **target table** is gone: ``table_id`` still present,
        ``table_name`` dropped out (``p0-5-02``). A schema observation, not a dereference."""
        return tuple(spec.field_name for spec in self.fields
                     if base_diff.has_dangling_target(spec))

    def edit(self) -> "TableDraft":
        """A fresh, empty draft over this snapshot. The snapshot itself never changes."""
        return TableDraft(self)


def snapshot_table(
    table_read: BaseTableRead,
    *,
    app_token: str,
    revision: Optional[int],
    read_proof: ReadProof,
) -> BaseTableSnapshot:
    """The landed structured intermediate + its paging proof + its anchor → a model.

    ``table_read`` must be a :class:`~larkdocio.base.table.BaseTableRead` — what
    :func:`larkdocio.base.read.read_base` hands back. A raw payload is refused rather than
    parsed here.

    Refuses, typed, when the read cannot prove it reached the end of the table (rule 1) or
    when there is no ``table.revision`` to compare-and-swap against (rule 2).
    """
    if not isinstance(table_read, BaseTableRead):
        raise BaseModelError(
            "A snapshot is built from the landed structured intermediate "
            "(larkdocio.base.read.read_base -> BaseTableRead), not from a raw payload: "
            f"got {type(table_read).__name__}.")
    if not isinstance(read_proof, ReadProof):
        raise BaseModelError(
            "A snapshot needs a ReadProof over the pages its read actually saw; "
            f"got {type(read_proof).__name__}.")
    if not read_proof.exhausted:
        raise IncompleteSnapshot(
            f"The read of table {table_read.table_id!r} cannot be proven to have exhausted "
            f"its pages, so it is not a snapshot: {read_proof.stopped_because}. A diff over a "
            "partial snapshot reads the rows it never saw as DELETIONS, so this refuses "
            "instead of building a model that would delete them.")
    if revision is None:
        raise IncompleteSnapshot(
            f"The read of table {table_read.table_id!r} carries no table revision. That is "
            "the only compare-and-swap anchor bitable exposes — the request body keys "
            "'revision' and 'last_modified_time' are silently ignored — so a model without "
            "one could never be safely applied.")
    names = tuple(spec.field_name for spec in table_read.fields)
    # The raw body rides through untouched when the read kept one, and stays `None` when it
    # did not — the model neither re-parses the wire nor invents an empty stand-in for it.
    records = tuple(
        SnapshotRecord(record_id=row.record_id, cells=tuple(zip(names, row.cells)),
                       raw_fields=row.raw_fields)
        for row in table_read.rows)
    return BaseTableSnapshot(
        app_token=app_token, table_id=table_read.table_id, name=table_read.name,
        fields=tuple(table_read.fields), records=records, revision=revision,
        read_proof=read_proof)


@dataclass(frozen=True)
class BaseSnapshot:
    """A whole Base as a set of per-table snapshots, each with **its own** anchor."""

    app_token: str
    name: str
    tables: Tuple[BaseTableSnapshot, ...]

    def table(self, table_id: str) -> BaseTableSnapshot:
        for table in self.tables:
            if table.table_id == table_id:
                return table
        raise KeyError(table_id)

    def edit(self) -> "BaseDraft":
        return BaseDraft(self)


def snapshot_base(
    base_read: BaseRead,
    *,
    revisions: Mapping[str, Optional[int]],
    read_proofs: Mapping[str, ReadProof],
) -> BaseSnapshot:
    """A whole-Base read → a per-table model.

    ``revisions`` and ``read_proofs`` are keyed by ``table_id`` and are supplied by the
    caller, because L1's structured intermediate does not carry either: the revision comes
    from ``GET …/tables`` and the proof from the walk. A table missing from either mapping is
    a table this read cannot vouch for, and is refused rather than defaulted.
    """
    if not isinstance(base_read, BaseRead):
        raise BaseModelError(
            "A Base snapshot is built from a BaseRead (larkdocio.base.read.read_base), not "
            f"from a raw payload: got {type(base_read).__name__}.")
    tables = []
    for table_read in base_read.tables:
        if table_read.table_id not in (read_proofs or {}):
            raise IncompleteSnapshot(
                f"No ReadProof was supplied for table {table_read.table_id!r}, so nothing "
                "vouches for its read having reached the end of the table.")
        tables.append(snapshot_table(
            table_read,
            app_token=base_read.app_token,
            revision=(revisions or {}).get(table_read.table_id),
            read_proof=read_proofs[table_read.table_id]))
    return BaseSnapshot(app_token=base_read.app_token, name=base_read.name,
                        tables=tuple(tables))


# --------------------------------------------------------------------------- #
# The draft — edit a projection, hand it back                                  #
# --------------------------------------------------------------------------- #

@dataclass
class TableDraft:
    """The editable projection of one table. Holds *intent*; the diff types it.

    Every operation is validated against the snapshot's own schema and record set, so a typo
    in a field name is a `UnknownField` here rather than a mystery at apply time. A write to a
    computed cell is **not** refused here — that is a plan-level fact the caller should see in
    the diff, with its reason, rather than an exception thrown mid-edit.
    """

    snapshot: BaseTableSnapshot
    _edits: Dict[str, Dict[str, str]] = dataclass_field(default_factory=dict)
    _additions: List[Tuple[str, Dict[str, str]]] = dataclass_field(default_factory=list)
    _deletions: List[str] = dataclass_field(default_factory=list)

    # ---- editing ---------------------------------------------------------- #

    def set(self, record_id: str, field_name: str, value: str) -> "TableDraft":
        """Put ``value`` in one cell of one existing record."""
        if record_id in self._deletions:
            raise BaseModelError(
                f"record {record_id!r} is marked for deletion in this draft; editing a cell "
                "on it would be an instruction the plan cannot carry out")
        self.snapshot.record(record_id)
        self.snapshot.field(field_name)
        self._edits.setdefault(record_id, {})[field_name] = value
        return self

    def update(self, record_id: str, cells: Mapping[str, str] = None,
               **more: str) -> "TableDraft":
        """Several cells of one record at once. Ordering in the diff is field order, so the
        order they are named here cannot change the plan."""
        for name, value in list((cells or {}).items()) + list(more.items()):
            self.set(record_id, name, value)
        return self

    def add(self, cells: Mapping[str, str] = None, **more: str) -> str:
        """Add a record in memory. Returns the **local** id it carries until the server
        assigns a real ``record_id`` — a plan-time handle, never a Lark id."""
        written = dict(cells or {})
        written.update(more)
        for name in written:
            self.snapshot.field(name)
        local_id = f"{NEW_RECORD_PREFIX}{len(self._additions) + 1}"
        self._additions.append((local_id, written))
        return local_id

    def delete(self, record_id: str) -> "TableDraft":
        """Mark an existing record for deletion. Any pending edits on it are dropped — a
        record cannot be both written and removed."""
        self.snapshot.record(record_id)
        self._edits.pop(record_id, None)
        if record_id not in self._deletions:
            self._deletions.append(record_id)
        return self

    # ---- reading the draft back ------------------------------------------- #

    @property
    def pending_edits(self) -> Mapping[str, Mapping[str, str]]:
        return {rid: dict(cells) for rid, cells in self._edits.items()}

    @property
    def pending_additions(self) -> Tuple[Tuple[str, Mapping[str, str]], ...]:
        return tuple((local_id, dict(cells)) for local_id, cells in self._additions)

    @property
    def pending_deletions(self) -> Tuple[str, ...]:
        return tuple(self._deletions)

    # ---- the diff --------------------------------------------------------- #

    def diff(self) -> base_diff.TableDiff:
        """Snapshot + intent → typed dispositions. **Zero network calls**, by construction."""
        return base_diff.diff_table(
            self.snapshot,
            edits=self._edits,
            additions=tuple(self._additions),
            deletions=tuple(self._deletions))


@dataclass
class BaseDraft:
    """A draft across several tables. Each table's entries carry their own anchor."""

    snapshot: BaseSnapshot
    _drafts: Dict[str, TableDraft] = dataclass_field(default_factory=dict)

    def table(self, table_id: str) -> TableDraft:
        """The draft for one table, created on first use."""
        if table_id not in self._drafts:
            self._drafts[table_id] = TableDraft(self.snapshot.table(table_id))
        return self._drafts[table_id]

    def diff(self) -> base_diff.BaseDiff:
        """Every table in the snapshot, in read order, each with its own anchor."""
        return base_diff.BaseDiff(
            app_token=self.snapshot.app_token,
            tables=tuple(self.table(table.table_id).diff()
                         for table in self.snapshot.tables))


__all__ = [
    "BaseDraft",
    "BaseModelError",
    "BaseSnapshot",
    "BaseTableSnapshot",
    "IncompleteSnapshot",
    "NEW_RECORD_PREFIX",
    "RawNotRetained",
    "ReadProof",
    "SnapshotRecord",
    "TableDraft",
    "UnknownField",
    "UnknownRecord",
    "snapshot_base",
    "snapshot_table",
]
