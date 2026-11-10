"""larkdocio.base.referential — what a link column points at, read for free.

A Base link column is a **reference**, and Lark keeps references intact for one of its two
link kinds and not the other. The library cannot fix that; what it can refuse to do is render
a broken reference as an intact one. This module is the cheapest half of that honesty — the
**column-level** reading — and it is deliberately free:

**It makes no call.** Everything below is read off the field ``property`` a Base read has
**already fetched**, so the reading costs nothing, needs no credential, and is available
whether or not anything downstream ever resolves a link to its target. Nothing here imports a
client or a transport — the one in-package name it imports is the shared by-name property walk
(:mod:`larkdocio.base._typed`), which imports nothing but ``typing`` — and a guard that follows
this file's imports **transitively** says so.

**The signature it reads, and why it is a READING rather than a contract.** When a whole
link-target table is deleted, a **one-way** source column survives: ``property.table_id`` still
names the dead table, the cells still hold record ids of its deleted records, a record search on
the source table still answers success — and ``property.table_name`` **drops out**. That
disappearance is the only free evidence there is, and it is an **observed** signature on
committed captures rather than a documented guarantee. So this module says *observed*, names
the captures it came from, and carries the observation that would refute it. Where the shape is
ambiguous the answer is :data:`TARGET_TABLE_UNKNOWN` — **no liveness claim in either
direction** — because a confident wrong answer about whether data still exists is worse than
an admitted unknown.

**Which columns this reading is actually MET on — measured, not assumed.** A **two-way** column
pointing into a deleted table is not among them: on the table-delete route its twin lives inside
the doomed table and the source column is destroyed along with it, so there is nothing left to
read this way (measured 2026-08-05 and re-measured 2026-08-14). **That is a fact about Lark, not a
rule this module encodes**: recognition below stays keyed on storage type alone, so a two-way
column that *does* arrive in this shape — by some other path, or if that cascade changes — is read
exactly like a one-way one rather than passed over. A detector that hard-coded the measurement
would stop working the day the measurement moved.

**Why the absence of a key is a risky thing to build on, and what protects it.** The pinned
SDK's typed field-property model carries only the keys it declares and silently drops the
rest (``BASE.md`` § Limitations, row 12 — in the source repository, not in the wheel). This detector
keys on an **absence**, so a transport
that quietly dropped ``table_name`` would report *every* link column as dangling — a
false-positive data-honesty failure, not a narrow gap. ``table_name`` **is** declared and
**does** survive that bridge, and that survival is pinned by a test against a committed
capture of a column whose target table is alive, rather than assumed.

**A link column is recognised by its storage type**, not by the ``(type, ui_type)`` pair the
render registry dispatches on. The capture that proves the dangling signature carries no
``ui_type`` at all — a field list read back after the target table was deleted returns the
storage type and the property and nothing else — so a pair-keyed detector would be blind
exactly where it matters.

**Nothing here repairs anything.** There is no verb on this surface that deletes a dangling
id, rewrites a cell, or otherwise tidies a broken reference; the loss a delete would cause is
previewed and fenced elsewhere, before the act, and is neither re-decided nor re-implemented
here. Rendering a broken reference honestly is the whole product of this module.
"""
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Tuple

from larkdocio.base._typed import _by_name

#: The two link pairs, in the ``(type, ui_type)`` form the read registry dispatches on.
#: ``18`` is the one-way link and ``21`` is the symmetric one — the numbering is Lark's and
#: reads backwards, which is exactly why it is written down here once.
SINGLE_LINK = (18, "SingleLink")
DUPLEX_LINK = (21, "DuplexLink")

#: Recognition is by storage type alone. See the module docstring: the capture that proves
#: the dangling signature carries no ``ui_type``.
LINK_TYPES = frozenset({SINGLE_LINK[0], DUPLEX_LINK[0]})

#: The target table is named, so it is there to be named.
TARGET_TABLE_LIVE = "target-table-live"
#: The column names a target table id whose name has dropped out — the deleted-table shape.
TARGET_TABLE_MISSING = "target-table-missing"
#: The shape answers neither way, so nothing is claimed.
TARGET_TABLE_UNKNOWN = "cannot-determine"

#: Every outcome, exhaustively. Three, not two — the third is the honest one.
TARGET_TABLE_STATES: Tuple[str, ...] = (
    TARGET_TABLE_LIVE, TARGET_TABLE_MISSING, TARGET_TABLE_UNKNOWN,
)

#: What each outcome means, in a caller's words. These are the strings a reading carries, so
#: a consumer never has to look up a slug to know what was and was not claimed.
STATE_MEANINGS = {
    TARGET_TABLE_LIVE: (
        "This link points at a table that still exists: the schema carries both the target "
        "table's id and its name."
    ),
    TARGET_TABLE_MISSING: (
        "This link points at a table that no longer exists. The schema still carries the "
        "target table's id and the cells still hold record ids, but the target table's name "
        "has dropped out of the column's configuration, which is what a deleted target table "
        "reads like — and nothing anywhere reports an error about it."
    ),
    TARGET_TABLE_UNKNOWN: (
        "Whether this link's target table still exists cannot be told from the schema alone: "
        "the column's configuration does not carry the shape the reading depends on, so no "
        "claim is made in either direction."
    ),
}

#: Said plainly, once: this is a reading of an observed shape, not a promise the API makes.
DANGLING_TARGET_IS_OBSERVED = (
    "A deleted target table was OBSERVED to leave a surviving one-way link column carrying a "
    "table id with no table name. That is a signature seen in captured responses, not a guarantee "
    "the API documents, so it is reported as a reading of the schema and never as a certainty. A "
    "two-way link column into a deleted table was observed NOT to survive at all, so this reading "
    "is one it is not normally met in; the reading is applied by storage type either way, because "
    "which columns arrive in this shape is Lark's decision and not this reading's."
)

#: Where the signature was captured — a path in the maintainer's repository, labelled
#: inline rather than through ``larkdocio.common.citations.dev_repo`` so this module keeps
#: importing NOTHING from the library, which is the property its own guard asserts.
DANGLING_TARGET_EVIDENCE = (
    "tests/captures/base-study/captures/p0-5-02-symmetric-link-deletion.json and "
    "tests/captures/base-study/captures/ld480-table-delete-link-semantics.json (both in the source repository)")

#: What would refute the reading. Written down so a future maintainer meets the decision
#: instead of re-discovering the boundary.
DANGLING_TARGET_REVISIT_TRIGGER = (
    "A capture showing table_name absent on a LIVE target table refutes this reading — at "
    "that point the absence stops meaning the table is gone and this becomes cannot-determine. "
    "Separately: a capture showing a TWO-WAY link column SURVIVING its target table's deletion "
    "would widen which columns this reading is met on. That was seen once and did not reproduce on "
    "two re-measurements the same day, so a second sighting is what would settle it."
)


@dataclass(frozen=True)
class LinkColumn:
    """One link column, and what its own configuration says about its target table.

    A reading of the schema — never a dereference. No record is fetched, no target table is
    read, and no cell is followed to whatever it points at.
    """

    field_name: str
    field_id: str
    field_type: Optional[int]
    ui_type: str
    target_table_id: Optional[str]
    target_table_name: Optional[str]
    state: str
    note: str

    @property
    def dangling(self) -> bool:
        """``True`` only for the one outcome that says the target table is gone.

        An ambiguous reading is **not** dangling: it is an unknown, and answering it ``True``
        would turn every shape this module cannot read into a claim that data was lost.
        """
        return self.state == TARGET_TABLE_MISSING

    @property
    def symmetric(self) -> bool:
        """``True`` for the two-way link kind, whose mirror lives in the target table."""
        return self.field_type == DUPLEX_LINK[0]


def _property_of(field) -> Optional[Mapping]:
    """A field's ``property`` as a mapping, whatever shape it arrived in.

    A read hands back a typed object, a capture hands back a plain dict, and the structured
    read hands back the bridged dict. All three are read here by name — through the one shared
    step, :func:`larkdocio.base._typed._by_name` — so the reading does not depend on which door
    the field came through. On a typed object an undeclared key is simply absent, which reads
    identically to the key being ``None`` — and that equivalence is exactly what makes the
    reading below safe across the bridge; the shared step is what re-materialises the key.

    **The two names below are this module's own contract**, not the shared walk's: it holds no
    list of its own, so a name another reader copies cannot leak into this reading.
    """
    prop = getattr(field, "property", None)
    if prop is None or isinstance(prop, Mapping):
        return prop
    return _by_name(prop, ("table_id", "table_name"))


def link_target_reading(prop: Optional[Mapping]) -> str:
    """One link column's ``property`` → one of :data:`TARGET_TABLE_STATES`.

    Three outcomes and no more. A target table id with a **name** reads live; a target table
    id whose **name is absent or empty of value** reads as the deleted-table signature; and
    anything else — no id at all, a name of the wrong shape, no configuration — reads
    :data:`TARGET_TABLE_UNKNOWN`, which claims nothing.
    """
    if not isinstance(prop, Mapping):
        return TARGET_TABLE_UNKNOWN
    table_id = prop.get("table_id")
    if not isinstance(table_id, str) or not table_id:
        return TARGET_TABLE_UNKNOWN
    if "table_name" not in prop or prop.get("table_name") is None:
        return TARGET_TABLE_MISSING
    table_name = prop.get("table_name")
    if isinstance(table_name, str) and table_name:
        return TARGET_TABLE_LIVE
    return TARGET_TABLE_UNKNOWN


def is_link_column(field) -> bool:
    """``True`` for the one-way and two-way link kinds, by storage type."""
    return getattr(field, "type", None) in LINK_TYPES


def target_table_state(field) -> str:
    """One field → what its configuration says about its link target.

    A column that is not a link at all points at no table, so it reads
    :data:`TARGET_TABLE_UNKNOWN` rather than borrowing a liveness answer it has no basis for.
    """
    if not is_link_column(field):
        return TARGET_TABLE_UNKNOWN
    return link_target_reading(_property_of(field))


def has_dangling_target(field) -> bool:
    """``True`` when a link column's target table reads as deleted (the free signature)."""
    return target_table_state(field) == TARGET_TABLE_MISSING


def link_column(field) -> Optional[LinkColumn]:
    """One field → its :class:`LinkColumn` reading, or ``None`` if it is not a link."""
    if not is_link_column(field):
        return None
    prop = _property_of(field)
    state = link_target_reading(prop)
    mapping = prop if isinstance(prop, Mapping) else {}
    return LinkColumn(
        field_name=getattr(field, "field_name", "") or "",
        field_id=getattr(field, "field_id", "") or "",
        field_type=getattr(field, "type", None),
        ui_type=getattr(field, "ui_type", "") or "",
        target_table_id=mapping.get("table_id"),
        target_table_name=mapping.get("table_name"),
        state=state,
        note=STATE_MEANINGS[state],
    )


def link_columns(fields: Sequence) -> Tuple[LinkColumn, ...]:
    """Every link column in a field list, **in field order** — the order the schema was read
    in, never a sort."""
    readings = (link_column(field) for field in fields or ())
    return tuple(reading for reading in readings if reading is not None)


def dangling_link_columns(fields: Sequence) -> Tuple[LinkColumn, ...]:
    """Only the link columns whose target table reads as deleted. Empty is the normal case."""
    return tuple(reading for reading in link_columns(fields) if reading.dangling)


__all__ = [
    "DANGLING_TARGET_EVIDENCE",
    "DANGLING_TARGET_IS_OBSERVED",
    "DANGLING_TARGET_REVISIT_TRIGGER",
    "DUPLEX_LINK",
    "LINK_TYPES",
    "LinkColumn",
    "SINGLE_LINK",
    "STATE_MEANINGS",
    "TARGET_TABLE_LIVE",
    "TARGET_TABLE_MISSING",
    "TARGET_TABLE_STATES",
    "TARGET_TABLE_UNKNOWN",
    "dangling_link_columns",
    "has_dangling_target",
    "is_link_column",
    "link_column",
    "link_columns",
    "link_target_reading",
    "target_table_state",
]
