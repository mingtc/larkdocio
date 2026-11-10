"""larkdocio.base.loss_preview — THE CROSS-TABLE LOSS PREVIEW for a destructive schema op.

**The invariant is not new; its SCOPE is.** The Sheets structural rung already ruled this class:
a destructive write whose loss cannot be snapshot **REFUSES**
(:mod:`larkdocio.sheets.ops`' delete preview — *"refusing a destructive delete that …
geometry/values unreadable"*). The only thing this module changes is what "the loss" reaches:
on a Base it is **not table-scoped**, and the evidence forces that.

Three findings are the specification, and every one of them was measured live:

* **a ``DuplexLink`` (21) field delete deletes the mirror column in ANOTHER table** — and the
  symmetric delete of the mirror deletes the source, in both directions
  (``p0-2-07``: ``mirror_survived: false``; ``p0-5-02``: ``source_duplex_survived: false``);
* **a table delete destroys every inbound link in every other table, and the two link kinds are
  destroyed DIFFERENTLY** — measured per kind on the table-delete route, twice, on 2026-08-05 and
  again on 2026-08-14. An inbound **one-way** (``SingleLink``, 18) column **survives and
  dangles**: ``property.table_id`` still names the dead table, ``table_name`` **drops out**, the
  cells still hold record ids of a deleted table's records, and ``records/search`` stays
  ``code:0`` **with no error anywhere** (``p0-5-02``, ``ld480-…``). An inbound **two-way**
  (``DuplexLink``, 21) column does **not** survive: its twin lives inside the doomed table and
  the source column goes with it, so the whole column and its contents are gone (in the source repository:
  ``tests/captures/base-study/captures/ld480-table-delete-link-semantics.json`` and
  ``tests/captures/base-study/captures/ld480-02-table-delete-cascade-timing.json``). Both outcomes are silent
  and both are unrecoverable through the API;
* **a plain field delete destroys one whole column of data in one call, with no API undo**
  (``06-06``);
* **a table delete BLANKS every ``Lookup`` column that rolls up from it, in every other
  table** — the column survives, its configuration still names the dead table, and the cells
  that held a mirror of that table read empty on the next read, with no error anywhere
  (measured on a live Base, 2026-08-05, where a whole column of visible values went blank
  behind a preview that had named only the link columns).

So a preview scoped to the table being edited is *wrong* for ``type:21`` and worse than wrong
for a table delete, where the loss is silent, in tables the caller never named. This module
therefore reads the **whole app** — every table's fields — and refuses when it cannot.

**A partial scan is worse than no scan, because it reads as reassurance.** The exhaustion
requirement is inherited from the L1 model's own rule (:class:`larkdocio.base.model.ReadProof`,
reused here rather than re-derived): a walk is exhaustive only when its last page said there is
no more. A read seam that cannot produce that record cannot be shown to have reached the end of
the table list, so a destructive op over it refuses.

**The blast radius is not the link graph alone.** A ``Lookup`` column is a dependency on
another table that carries no link into it, so a scan that kept only link columns under-reported
by exactly the class that goes silently blank. The dependency costs **no extra call**: the app
scan already holds every table's columns, and the table a Lookup rolls up from is on the
column's own property — read here through :mod:`larkdocio.base.computed`, the surface that owns
that reading, never re-walked. What a Lookup cannot say is followed to its own conclusion: a
Lookup this scan **cannot place** — one whose configuration did not carry the table it rolls up
from — might be rolling up from a doomed table, so the op **refuses** rather than passing over
it.

**Nothing here follows a link.** The dropped ``table_name`` is used **only** as a detector.
Resolving a link cell to its target is a declared Non-Goal (``BASE.md``, in the source repository,
register row 20) and belongs to a later rung; a preview that dereferenced links would be that
feature arriving through a side door.

**Nothing here purges.** Lark's ``DELETE`` is a **trash**, not a purge — no open-API verb purges
an app, and deleted tables sit in the Base's trash too — so every sentence this module ships
says *deleted, recoverable from Lark's trash by a human* and none of them implies erasure.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from larkdocio.base import cells, computed, referential
from larkdocio.base._typed import _by_name
from larkdocio.base.diff import DUPLEX_LINK, SINGLE_LINK
from larkdocio.base.field_authoring import (
    REMAP_THEN_SHRINK,
    SELECT_OPTION_ID_IS_THE_CELL_ANCHOR,
    SELECT_OPTION_KEYS,
    SELECT_OPTION_SHRINK_DESTROYS_CELLS,
    select_label,
)
from larkdocio.base.model import ReadProof
from larkdocio.common.citations import dev_repo
from larkdocio.errors import LarkDocIOError

_CAPTURES = "tests/captures/base-study/captures"
_P0 = "dev/base-study/p0-addendum-2026-08-03.md"

#: The attribute a read client publishes so a walk's **paging proof** can be read back off it:
#: the page bodies the most recent cursor walk actually saw
#: (:attr:`larkdocio.base.client.BaseReadClient.last_walk_pages`). Named as data because its
#: absence is a refusal, not a shrug.
PAGING_PROOF_SEAM = "last_walk_pages"


# --------------------------------------------------------------------------- #
# The sentences this rung must not get wrong, authored ONCE                    #
# --------------------------------------------------------------------------- #

#: **THE INVARIANT**, widened from one sheet to the whole app. Quoted verbatim by every
#: enumeration refusal and by ``BASE.md``'s register (in the source repository), so the two cannot drift.
LOSS_MUST_BE_ENUMERABLE = (
    "A destructive schema op whose loss cannot be enumerated REFUSES, and on a Base the loss "
    "is scoped to the whole app rather than to the table you named. Deleting a two-way link "
    "COLUMN deletes its mirror column in ANOTHER table. Deleting a TABLE is a different call "
    "with its own blast radius, measured on its own route and never inferred from the column "
    "one: it destroys every link pointing into that table from every other table, and the two "
    "link kinds are destroyed DIFFERENTLY. A one-way link SURVIVES and dangles, keeping the "
    "dead table's table_id while its table_name drops out; a two-way link does NOT survive at "
    "all, because its twin lives inside the table being deleted and the source column goes with "
    "it. Both outcomes are silent, with no error anywhere. So the preview "
    "reads every table's columns before anything is deleted, and if any part of that read "
    "cannot be completed — a table list that cannot be proven read to the end, a column read "
    "that errors, a table this credential cannot see — nothing is deleted at all. A partial "
    "scan would under-report the blast radius, which is worse than no scan, because it reads "
    "as reassurance."
)

#: **DELETE IS TRASH, NOT PURGE.** The consumer-facing sentence, authored once and quoted by
#: every loss preview. No open-API verb purges anything on this surface.
TRASH_NOT_PURGE = (
    "Deleted, not erased: Lark's delete puts the object in the Base's trash, where a human can "
    "restore it from the product. There is no open-API verb that purges anything here, and "
    "this library offers none — so nothing below is a permanent erasure, and equally nothing "
    "below can be undone through the API."
)

#: What a caller cannot do afterwards, said plainly beside the trash sentence.
NO_API_UNDO = (
    "There is no API undo. This library detects and reports; it does not retry a destructive "
    "call and it cannot reverse one. Restoring from the Base's trash is a person's action in "
    "the product."
)

#: The two-table half of the specification (``p0-2-07`` / ``p0-5-02``).
DUPLEX_MIRROR_IS_DESTROYED = (
    "This is a two-way link column, so deleting it deletes its MIRROR COLUMN IN ANOTHER TABLE "
    "in the same call — measured in both directions: deleting the source removed the mirror, "
    "and deleting the mirror removed the source. Both columns and both tables are named above, "
    "with the number of cells each currently holds."
)

#: What a mirror looks like when its twin's table is already gone. **This is a defensive branch,
#: not an outcome the table-delete route was seen producing**: on that route a two-way column
#: whose target table is deleted does not survive at all, so it is not there afterwards to be read
#: this way. The shape is still handled, because the column's configuration is the only thing this
#: preview has to go on and some other path may leave it in that state.
DUPLEX_MIRROR_ALREADY_GONE = (
    "This two-way link's target table is already gone — the column still carries its table_id "
    "while the table_name has dropped out — so there is no mirror column left to lose. The "
    "dangling column itself is still destroyed. Deleting a link target table was NOT observed "
    "leaving a two-way column in this state (it removes the column outright, unlike a one-way "
    "link, which survives and dangles), so whatever produced this shape was something else; it "
    "is read from the column's own configuration and reported rather than explained."
)

#: The silent half, and the reason this preview exists at all (``p0-5-02``).
INBOUND_LINK_DANGLES_SILENTLY = (
    "This link column points at a table being deleted. It SURVIVES the delete and dangles: its "
    "property keeps the dead table's table_id while the table_name drops out, its cells keep "
    "the record ids of a deleted table's records, and reading the table it lives in still "
    "answers code:0 with no error anywhere. Nothing will tell you afterwards; that is why it "
    "is told here."
)

#: A two-way link INTO a table being deleted. Its twin is inside that table, and what happens to
#: it **has now been measured on the table-delete route itself** rather than inferred from the
#: field-delete route: the whole column goes.
INBOUND_DUPLEX_IS_LOST_EITHER_WAY = (
    "This is a two-way link column pointing INTO a table being deleted, so its twin is inside "
    "that table — and the whole column goes with it. Measured on the table-delete route, twice: "
    "the source two-way column was already absent from this table's field list under a second "
    "after the delete, and stayed absent for the forty seconds that were watched. So unlike a "
    "one-way link into the same table, which survives and dangles, this column does not survive "
    "at all: the column and every value in it are gone, silently, and neither is recoverable "
    "through the API. Deleting a two-way link COLUMN was separately measured to delete its twin "
    "(p0-2-07, p0-5-02); that is a different call, and it is cited here rather than relied on."
)

#: The computed half of the silent loss — the class a link-only scan could not see.
INBOUND_LOOKUP_BLANKS_SILENTLY = (
    "This Lookup column mirrors a table being deleted. It SURVIVES the delete as a column and "
    "goes BLANK: its values were the server's mirror of that table, so once the table is gone "
    "every cell of it reads empty, on every row, while the column's own configuration still "
    "names the dead table. Nothing errors and nothing says so afterwards — the count above is "
    "how many rows hold a value in it today, read from the table itself at plan time."
)

#: The field-delete mirror of the same class, with its precision gap said out loud.
INBOUND_LOOKUP_MAY_ROLL_UP_THIS_COLUMN = (
    "This Lookup column mirrors the table the column being deleted lives in, so deleting that "
    "column may be what blanks it. WHICH FIELD a Lookup rolls up is unavailable in this "
    "reading — it is one of the provenance keys the library's Lark client does not carry "
    "through — so it cannot be said here whether this Lookup is the one that mirrors the "
    "column you are deleting. Every Lookup that mirrors this table is named for that reason: "
    "the list is complete, the precision is not."
)

#: The link-column case of the same gap: a Lookup reaches its table THROUGH a link column.
LOOKUP_MAY_TRAVERSE_THIS_LINK = (
    "The column being deleted is a link column, and a Lookup reaches another table through a "
    "link column in its own table. Which link column each Lookup travels is unavailable in "
    "this reading, so every Lookup sitting beside this one is named as a candidate: if it "
    "travels this link, deleting the link blanks it silently. The list is complete, the "
    "precision is not."
)

#: The boundary of the computed enumeration, disclosed rather than left silent. It is a
#: DISCLOSURE and not a refusal because a formula string is opaque by ruling — reading inside
#: one is a Non-Goal this rung does not open — and because a Formula's cells are recomputed by
#: the server rather than destroyed.
FORMULA_EXPRESSIONS_ARE_NOT_TRACED = (
    "What is traced here is the Lookup class, because a Lookup's own configuration names the "
    "table it mirrors. A Formula column's expression is carried as opaque provenance and is "
    "never parsed by this library, in either direction, so a Formula whose value depends on a "
    "column named above is not traced and not named — its cells are recomputed by the server "
    "rather than destroyed, and what they will read afterwards is the server's answer, not "
    "something this preview can derive without reading inside a formula string."
)

#: The single-column half (``06-06``).
COLUMN_IS_DESTROYED = (
    "Deleting a column destroys every value in it, in one call, and there is no API undo. The "
    "cell count above is how many rows currently hold a value in it, read from the table "
    "itself at plan time."
)

#: AC4's disclosure: what the number beside a plan means. The same discipline the write
#: batching discloses, for the same reason — a consumer reasoning about a failure needs the
#: shape of what was read, not just the verdict.
SCAN_COST_DISCLOSURE = (
    "This preview is not free: enumerating an app-scoped loss means reading every table's "
    "columns, and the cell counts mean reading the rows of the tables a delete touches. The "
    "count above is how many read calls that cost and which tables were inspected, stated so "
    "the shape of the work is visible before you approve it."
)

#: The codes that mean an object really is gone, asked of the **bitable** API and never of
#: Drive metadata — Drive keeps answering for a deleted Base for ever. The same oracle the live
#: harness defines for ``orphans = 0``; a test holds the two in agreement, because the shipped
#: library cannot import from ``tests/``.
OBJECT_GONE_CODES: Tuple[int, ...] = (1254041, 1002, 91402)


class LossNotEnumerable(LarkDocIOError):
    """The cross-table scan could not be completed, so nothing may be deleted.

    Carries the same sentence the plan-time refusal carries, plus the specific shortfall — a
    typed reason a caller can act on beats "the preview failed".
    """

    def __init__(self, shortfall: str):
        self.shortfall = shortfall
        super().__init__(f"{shortfall} {LOSS_MUST_BE_ENUMERABLE}")


# --------------------------------------------------------------------------- #
# What the scan sees                                                           #
# --------------------------------------------------------------------------- #

def _property_of(field) -> Dict:
    """A field's ``property`` as a plain dict, whatever shape it arrived in.

    The pinned SDK hands back a typed object; a raw capture hands back a dict. Both are read
    here, by name, so the detector works on either — and **``back_field_id`` is deliberately
    read leniently**: the SDK's own property model does not carry it at all (the lossy-property
    class ``BASE.md`` register row 12 records, in the source repository), while the raw payload does. The
    mirror is located by whichever of the two is present, and the preview says which.

    ``filter_info`` is copied for the same reason and it is load-bearing: it is where a
    ``Lookup``'s target table lives, so a property copy that dropped it would make the computed
    half of the blast radius invisible **on the typed door only** — the exact shape a fixture
    built from a raw capture would never reproduce.

    **What is copied through is the value, not a conversion of it.** On the typed door
    ``filter_info`` is itself a typed object rather than a dict, and it travels that way: the
    provenance surface reads the nested path **by name**, on a mapping or an object alike
    (:func:`larkdocio.base.computed.target_table_in`), so nothing here has to know the shape.
    A copy that quietly required a dict at the nested level is how this preview came to refuse
    every op on a Base whose Lookup it was holding the answer for.

    **Where the by-name rule now lives.** Both halves of it — this copy and the nested read the
    provenance surface does — are one shared step, :mod:`larkdocio.base._typed`, so the mistake
    above has one place to be made and one place to be fixed instead of four. The six names
    below stay **here**, because which keys this detector needs is its own contract and the
    shared step holds no list of its own. One consequence, stated because it is a real
    difference: a mapping that is not a ``dict`` is now read by name like anything else rather
    than answering every key ``None``. No door this library has produces one — the SDK hands
    back an object, a capture and the bridge hand back ``dict`` — so it changes no reading here;
    it is simply the shared rule being the same rule everywhere.

    **``options`` is the seventh name, and it is load-bearing for the same reason
    ``filter_info`` is.** A select column's option set is where an option **shrink**'s loss is
    worked out (:func:`select_option_shrink_loss`), and on the typed door the SDK nests each
    option as an ``AppTableFieldPropertyOption`` **object** rather than a dict — so a copy that
    dropped the key, or a reader that required a mapping one level down, would make every shrink
    unenumerable on the typed door only: the exact shape a fixture built from a raw capture
    cannot reproduce.
    """
    if isinstance(field.property if hasattr(field, "property") else None, dict):
        return dict(field.property)
    prop = getattr(field, "property", None)
    if prop is None:
        return {}
    return _by_name(prop, ("table_id", "table_name", "back_field_id", "back_field_name",
                           "multiple", "filter_info", "options"))


@dataclass(frozen=True)
class ScannedField:
    """One column, as the schema reports it. A reading, never a dereference."""

    table_id: str
    table_name: Optional[str]
    field_id: str
    field_name: str
    field_type: Optional[int]
    ui_type: str
    property: Dict

    @property
    def pair(self) -> Tuple[Optional[int], str]:
        return (self.field_type, self.ui_type)

    @property
    def is_link(self) -> bool:
        return self.pair in (SINGLE_LINK, DUPLEX_LINK)

    @property
    def is_duplex(self) -> bool:
        return self.pair == DUPLEX_LINK

    @property
    def is_lookup(self) -> bool:
        """A ``Lookup`` (19) — the one computed kind that mirrors another table's values."""
        return self.pair == computed.LOOKUP

    @property
    def rolls_up_from_table(self) -> Optional[str]:
        """The table a ``Lookup`` mirrors, or ``None`` — including ``None`` for a Lookup whose
        configuration did not carry it, which is a **refusal** and not a shrug (see
        :func:`_lookups_into`).

        The nested key this comes off is walked by :mod:`larkdocio.base.computed`, the surface
        that owns the provenance reading, and read from here rather than re-spelled — the same
        discipline :attr:`dangling` follows for the dead-reference signature.
        """
        return computed.target_table_in(self.property) if self.is_lookup else None

    @property
    def is_select(self) -> bool:
        """A ``SingleSelect`` (3) / ``MultiSelect`` (4) — the kinds whose cells are anchored to
        an option id, decided by the authoring surface's own discriminator rather than a second
        list here."""
        return select_label(self.field_type, self.ui_type) is not None

    @property
    def options(self) -> Optional[Tuple[Dict, ...]]:
        """This select column's option set, or ``None`` when the read did not carry one.

        ``None`` is a **refusal** upstream, never *no options*: a column whose option set did not
        arrive is one whose shrink cannot be worked out. Each option is read **by name** through
        the shared step, because the typed door nests option objects rather than dicts.
        """
        if not self.is_select:
            return None
        options = self.property.get("options")
        if options is None:
            return None
        # The key list is a LITERAL at its own call site, like every other adopter of the shared
        # walk: the shared step may hold no list of its own, and neither may this one borrow one
        # through a name. It is held equal to the select surface's own SELECT_OPTION_KEYS by a
        # test, so the two spellings cannot drift.
        return tuple(_by_name(option, ("id", "name", "color")) for option in options)

    @property
    def target_table_id(self) -> Optional[str]:
        return self.property.get("table_id") if self.is_link else None

    @property
    def target_table_name(self) -> Optional[str]:
        return self.property.get("table_name") if self.is_link else None

    @property
    def dangling(self) -> bool:
        """``True`` when the target table is already gone — ``table_id`` without
        ``table_name`` (``p0-5-02``'s accidental detector).

        The signature is **read, not re-spelled**: it is authored once in
        :mod:`larkdocio.base.referential`, together with the third outcome this boolean
        collapses (a shape that answers neither way is not dangling), so the destructive scan
        and the reader cannot drift apart about what a dead reference looks like.
        """
        return self.is_link and (
            referential.link_target_reading(self.property)
            == referential.TARGET_TABLE_MISSING
        )


@dataclass(frozen=True)
class ScannedTable:
    table_id: str
    name: Optional[str]
    revision: Optional[int]
    fields: Tuple[ScannedField, ...]

    def field(self, field_id: str) -> Optional[ScannedField]:
        for spec in self.fields:
            if spec.field_id == field_id:
                return spec
        return None


def cell_holds_data(value) -> bool:
    """Does this cell hold a value a delete would destroy?

    **The absent-key rule is exact for a scalar and false for a wrapper.** A cell of one of
    the multi-valued kinds — link, attachment, person, group chat, multi-select — and a
    computed cell all read back as a *present* key holding an **empty form**: an empty link
    cell is an object whose id list is null (nobody ever wrote one) or empty (its targets were
    deleted), an empty computed cell is a typed wrapper carrying nothing, and an empty
    multi-valued cell is an empty list. Counting those as data over-reported a live column
    twenty-fold, on the one screen where the number is the basis for consent.

    The link cell's two empty forms are **read, not re-spelled** — not even their key is named
    here. They are authored once in :mod:`larkdocio.base.cells`
    (:func:`~larkdocio.base.cells.link_state`), together with the fact that they are
    *different* facts about the same cell, so the preview and the reader cannot drift apart
    about what an empty link cell is; and this module still names no link-cell key at all,
    which is the source-text fence that keeps a resolved link out of the preview.

    **Nothing is inferred from a scalar's shape**, which is the half of the old premise that
    was verified exact against a live Base: ``0`` is a number, ``false`` is a checkbox state,
    and both are data. Only a container that is empty, or a wrapper whose contents are empty,
    is read as no value.
    """
    if value is None:                      # the legacy read route's explicit null
        return False
    if not isinstance(value, (dict, list, tuple)):
        return True                        # a scalar — 0 and False included
    state = cells.link_state(value)
    if state != cells.LINK_NOT_AN_OBJECT:
        return state == cells.LINK_POPULATED
    if cells.wrapper_type(value) is not None:
        members = value.get("value")       # a Formula / Lookup wrapper carrying nothing
        if isinstance(members, (list, tuple)):
            return bool(members)
        return members is not None
    return bool(value)                     # an empty list / dict holds nothing


class AppScan:
    """Every table's columns, plus the read budget it cost — the preview's evidence base.

    Bound to the read client that produced it so a **cell count** can be taken on demand: which
    tables need their rows read is not knowable until the loss is worked out, and reading every
    table's rows to answer a one-column question would be a preview nobody could afford.

    The counts are memoised per table, so the second question about a table costs nothing and
    the disclosed budget stays the number of calls that really happened.
    """

    __slots__ = ("app_token", "tables", "_read_client", "_read_calls", "_inspected", "_rows")

    def __init__(self, app_token, tables, read_client, read_calls, inspected):
        self.app_token = app_token
        self.tables = tuple(tables)
        self._read_client = read_client
        self._read_calls = read_calls
        self._inspected = list(inspected)
        self._rows: Dict[str, List] = {}

    @property
    def read_calls(self) -> int:
        """How many read calls this preview has spent so far. Disclosed on the plan."""
        return self._read_calls

    @property
    def tables_inspected(self) -> Tuple[str, ...]:
        return tuple(self._inspected)

    def table(self, table_id: str) -> Optional[ScannedTable]:
        for entry in self.tables:
            if entry.table_id == table_id:
                return entry
        return None

    def require_table(self, table_id: str) -> ScannedTable:
        table = self.table(table_id)
        if table is None:
            raise LossNotEnumerable(
                f"table {table_id!r} is not in this Base's table list, so what deleting it "
                f"would cost cannot be worked out.")
        return table

    def cells_with_data(self, table_id: str, field_name: str) -> Optional[int]:
        """How many rows currently hold a value in one column.

        An empty cell is usually an **absent key** in ``records/search`` — never an empty
        string — and for a scalar column that rule is exact. It is **not** exact for the
        wrapper- and list-valued kinds: an empty link cell arrives as a *present* key holding
        an object whose id list is null, and a key-presence count read that as data (measured
        against a live column: 64 reported where 3 rows linked). So a present key is counted
        only when what it holds is not an **empty form** — see :func:`cell_holds_data`, which
        reads the shapes off the cell surface rather than re-spelling them here.
        """
        rows = self._records(table_id)
        return sum(1 for record in rows
                   if field_name in (getattr(record, "fields", None) or {})
                   and cell_holds_data((getattr(record, "fields", None) or {})[field_name]))

    def row_count(self, table_id: str) -> int:
        return len(self._records(table_id))

    def records(self, table_id: str) -> List:
        """Every row of one table, **proven read to exhaustion** or a refusal — memoised.

        The public form of the read :meth:`cells_with_data` already takes, for the one preview
        that needs the rows themselves rather than a count of them: an option shrink names the
        records it will empty, one line each, and a second walk of the same table would be a
        second opinion about the same rows.
        """
        return self._records(table_id)

    def _records(self, table_id: str) -> List:
        if table_id not in self._rows:
            self._rows[table_id] = _paged(
                self._read_client, "search_records", self.app_token, table_id,
                what=f"the rows of table {table_id}")
            self._read_calls += 1
        return self._rows[table_id]

    def cost(self) -> Dict:
        """AC4's disclosure: the reads this preview spent, and over which tables."""
        return {
            "read_calls": self._read_calls,
            "tables_inspected": sorted(self._inspected),
            "what": SCAN_COST_DISCLOSURE,
        }


# --------------------------------------------------------------------------- #
# The scan — every table, proven to exhaustion, or nothing at all              #
# --------------------------------------------------------------------------- #

def _proof_of(read_client) -> ReadProof:
    """The paging proof for the walk this client just finished, or a refusal.

    Read off the client's own page bodies and classified by :class:`ReadProof` — the landed
    reading, reused rather than re-derived. A seam that publishes none cannot be shown to have
    reached the end of anything.
    """
    try:
        pages = getattr(read_client, PAGING_PROOF_SEAM)
    except AttributeError:
        pages = None
    if pages is None:
        raise LossNotEnumerable(
            f"this read client publishes no `{PAGING_PROOF_SEAM}` record, so its walk cannot "
            f"be shown to have reached the end of the list.")
    return ReadProof.from_pages(pages)


def _paged(read_client, method: str, *args, what: str) -> List:
    """One paged read, **proven exhaustive** — or :class:`LossNotEnumerable`."""
    try:
        items = list(getattr(read_client, method)(*args) or ())
    except LossNotEnumerable:
        raise
    except Exception as exc:            # noqa: BLE001 — any unreadable leg is a refusal
        raise LossNotEnumerable(
            f"reading {what} failed ({type(exc).__name__}: {exc}), so the blast radius of this "
            f"delete is unknown.") from exc
    proof = _proof_of(read_client)
    if not proof.exhausted:
        raise LossNotEnumerable(
            f"reading {what} could not be proven to have run to exhaustion "
            f"({proof.stopped_because}), so the blast radius of this delete is unknown.")
    return items


def scan_app(read_client, app_token: str) -> AppScan:
    """Read **every** table's columns in the Base ``app_token``, or refuse.

    One table-list read plus one field read per table. Nothing is deleted, nothing is written,
    and no link is followed — this is the evidence base every loss preview below is built from.
    """
    tables = _paged(read_client, "list_tables", app_token,
                    what=f"the table list of Base {app_token}")
    read_calls = 1
    scanned = []
    inspected = []
    for table in tables:
        table_id = getattr(table, "table_id", None)
        name = getattr(table, "name", None)
        fields = _paged(read_client, "list_fields", app_token, table_id,
                        what=f"the columns of table {table_id}")
        read_calls += 1
        inspected.append(table_id)
        scanned.append(ScannedTable(
            table_id=table_id, name=name, revision=getattr(table, "revision", None),
            fields=tuple(
                ScannedField(
                    table_id=table_id, table_name=name,
                    field_id=getattr(field, "field_id", None),
                    field_name=getattr(field, "field_name", None),
                    field_type=getattr(field, "type", None),
                    ui_type=getattr(field, "ui_type", None) or "",
                    property=_property_of(field))
                for field in fields)))
    return AppScan(app_token, scanned, read_client, read_calls, inspected)


# --------------------------------------------------------------------------- #
# The previews                                                                 #
# --------------------------------------------------------------------------- #

def _column(scan: AppScan, spec: ScannedField) -> Dict:
    return {
        "table_id": spec.table_id,
        "table_name": spec.table_name,
        "field_id": spec.field_id,
        "field_name": spec.field_name,
        "ui_type": spec.ui_type,
        "field_type": spec.field_type,
        "cells_with_data": scan.cells_with_data(spec.table_id, spec.field_name),
    }


def _mirror_of(scan: AppScan, spec: ScannedField):
    """``(mirror_spec_or_None, disclosure)`` for a two-way link column.

    The mirror lives in ``property.table_id``. It is identified by ``back_field_id`` when the
    payload carries it and by ``back_field_name`` when it does not — the pinned SDK's property
    model drops the id, so the name is the key that survives a typed read.
    """
    if not spec.is_duplex:
        return None, None
    if spec.dangling:
        return None, {"already_gone": True, "table_id": spec.target_table_id,
                      "what": DUPLEX_MIRROR_ALREADY_GONE}
    target = scan.table(spec.target_table_id)
    if target is None:
        raise LossNotEnumerable(
            f"column {spec.field_name!r} is a two-way link into table "
            f"{spec.target_table_id!r}, which is not in this Base's table list, so the mirror "
            f"column this delete would also destroy cannot be named.")
    back_id = spec.property.get("back_field_id")
    back_name = spec.property.get("back_field_name")
    for candidate in target.fields:
        if back_id and candidate.field_id == back_id:
            return candidate, {"already_gone": False, "located_by": "back_field_id"}
    for candidate in target.fields:
        if back_name and candidate.field_name == back_name:
            return candidate, {"already_gone": False, "located_by": "back_field_name"}
    raise LossNotEnumerable(
        f"column {spec.field_name!r} is a two-way link whose mirror in table "
        f"{spec.target_table_id!r} could not be found by back_field_id {back_id!r} or "
        f"back_field_name {back_name!r}, so the second column this delete would destroy cannot "
        f"be named.")


def _lookup_row(scan: AppScan, table: ScannedTable, spec: ScannedField, effect: str) -> Dict:
    return {
        "table_id": table.table_id,
        "table_name": table.name,
        "field_id": spec.field_id,
        "field_name": spec.field_name,
        "ui_type": spec.ui_type,
        "rolls_up_from_table": spec.rolls_up_from_table,
        "cells_with_data": scan.cells_with_data(table.table_id, spec.field_name),
        "effect": effect,
    }


def _lookups_into(scan: AppScan, table_ids: Sequence[str], effect: str) -> List[Dict]:
    """Every ``Lookup`` OUTSIDE ``table_ids`` that mirrors one of them — or a refusal.

    A Lookup inside a doomed table is destroyed with it and is already named among the columns;
    what this finds is the survivor that goes blank. **A Lookup this scan cannot place refuses
    the whole op**: a column whose configuration did not carry the table it mirrors might be
    mirroring a doomed one, and passing over it would be the partial scan the invariant names —
    the under-report that reads as reassurance.
    """
    targets = set(table_ids)
    rows: List[Dict] = []
    for table in scan.tables:
        if table.table_id in targets:
            continue
        for spec in table.fields:
            if not spec.is_lookup:
                continue
            if spec.rolls_up_from_table is None:
                raise LossNotEnumerable(
                    f"column {spec.field_name!r} ({spec.field_id!r}) in table "
                    f"{table.table_id!r} is a Lookup whose configuration does not say which "
                    f"table it mirrors, so whether this delete blanks it cannot be worked "
                    f"out.")
            if spec.rolls_up_from_table in targets:
                rows.append(_lookup_row(scan, table, spec, effect))
    return rows


def field_delete_loss(scan: AppScan, table_id: str, field_id: str) -> Dict:
    """What deleting ONE column destroys — **in every table it reaches**."""
    table = scan.require_table(table_id)
    spec = table.field(field_id)
    if spec is None:
        raise LossNotEnumerable(
            f"table {table_id!r} has no column {field_id!r}, so what deleting it would cost "
            f"cannot be worked out. Re-read the table's columns and re-plan.")
    mirror, mirror_note = _mirror_of(scan, spec)
    columns = [_column(scan, spec)]
    if mirror is not None:
        columns.append(_column(scan, mirror))

    # The computed half: a Lookup mirroring THIS table may be mirroring this very column, and
    # a Lookup beside a link column may be travelling it. Neither is knowable to the field —
    # both keys are dropped by the transport — so the candidate set is named in full.
    lookups = _lookups_into(scan, [table_id], INBOUND_LOOKUP_MAY_ROLL_UP_THIS_COLUMN)
    if spec.is_link:
        lookups.extend(_lookup_row(scan, table, beside, LOOKUP_MAY_TRAVERSE_THIS_LINK)
                       for beside in table.fields if beside.is_lookup)

    other = sorted(({column["table_id"] for column in columns}
                    | {row["table_id"] for row in lookups}) - {table_id})
    what = COLUMN_IS_DESTROYED
    if spec.is_duplex:
        what = (DUPLEX_MIRROR_IS_DESTROYED if mirror is not None
                else DUPLEX_MIRROR_ALREADY_GONE) + " " + COLUMN_IS_DESTROYED
    return {
        "kind": "field-delete",
        "app_token": scan.app_token,
        "columns": columns,
        "other_tables": other,
        "mirror": (dict(mirror_note or {}, **({} if mirror is None else {
            "table_id": mirror.table_id, "table_name": mirror.table_name,
            "field_id": mirror.field_id, "field_name": mirror.field_name}))
            if mirror_note is not None else None),
        "inbound_links": [],
        "inbound_lookups": lookups,
        "tables": [],
        "what": f"{what} {NO_API_UNDO}",
        "not_traced": FORMULA_EXPRESSIONS_ARE_NOT_TRACED,
        "trash": TRASH_NOT_PURGE,
        "invariant": LOSS_MUST_BE_ENUMERABLE,
        "evidence": [dev_repo(f"{_CAPTURES}/06-06-destructive-ops.json"),
                     dev_repo(f"{_CAPTURES}/p0-2-07-link-deletion-behaviour.json"),
                     dev_repo(f"{_CAPTURES}/p0-5-02-symmetric-link-deletion.json"),
                     dev_repo(f"{_P0} § 2")],
    }


# --------------------------------------------------------------------------- #
# The SELECT-OPTION SHRINK — the same doctrine, a write that is not a delete    #
# --------------------------------------------------------------------------- #

#: The sentence an **empty** shrink preview carries. AC3's whole point: an empty loss here is a
#: **measurement**, not an absence, and it says which read it came from.
SELECT_OPTION_SHRINK_MEASURED_EMPTY = (
    "MEASURED EMPTY: every option this update drops is held by NO record in this table — read "
    "at plan time, from the table itself, to exhaustion. So this shrink destroys nothing, needs "
    "no consent token, and is applied like any other schema edit. This is an empty preview that "
    "was measured, never a preview that was skipped: a shrink whose loss could not be read is a "
    "REFUSAL and carries no preview at all."
)

#: A shrink names one column in one table, and what it does NOT follow is said rather than left
#: to be assumed. A Lookup mirroring this table is the class ``field_delete_loss`` names for the
#: same reason, with the same precision gap, and it is named here on the same terms.
LOOKUP_MAY_MIRROR_A_SHRUNK_COLUMN = (
    "This Lookup column mirrors the table the shrinking column lives in, so the values it rolls "
    "up may include the cells this shrink empties. WHICH FIELD a Lookup rolls up is unavailable "
    "in this reading — it is one of the provenance keys the library's Lark client does not carry "
    "through — so every Lookup that mirrors this table is named for that reason: the list is "
    "complete, the precision is not. A Lookup is the server's own mirror, so it is recomputed "
    "rather than destroyed; what it reads afterwards is the server's answer about a column that "
    "no longer holds those values."
)

#: The boundary of this preview, disclosed. A lost select value is **not** a delete-to-trash, so
#: :data:`TRASH_NOT_PURGE` is deliberately NOT quoted here — it would be false comfort.
SELECT_OPTION_SHRINK_IS_NOT_A_TRASH = (
    "This is not a delete-to-trash. Nothing is put anywhere: the cell simply reads empty on the "
    "next read, and the column, the record and the table all survive. Whether the Base's record "
    "HISTORY retains the old value was NOT measured, so it is neither promised nor refuted here "
    "— treat the value as gone. There is no API undo."
)


def _option_row(option: Dict) -> Dict:
    return {key: option.get(key) for key in SELECT_OPTION_KEYS}


def _cell_values(value) -> List:
    """The option names one select cell holds, in the order the read reported them.

    ``records/search`` renders a select cell as the option **name** — a bare string for a
    ``SingleSelect``, a list for a ``MultiSelect`` (``BASE.md``, in the source repository, the Single
    Option / Multiple Options rows) — which is why the attribution below is by name and says so.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [member for member in value if member is not None]
    return [value]


def select_option_shrink_loss(scan: AppScan, table_id: str, field_id: str, options) -> Dict:
    """What REPLACING a select column's option set with ``options`` destroys — per record.

    ``PUT …/fields/{f}`` replaces the whole option set and matches on each option's ``id``
    (:data:`~larkdocio.base.field_authoring.SELECT_OPTION_ID_IS_THE_CELL_ANCHOR`), so the loss is
    exactly the records holding an option whose ``id`` the new set does not carry
    (:data:`~larkdocio.base.field_authoring.SELECT_OPTION_SHRINK_DESTROYS_CELLS`). Enumerated
    here, before anything is sent — and **refused** rather than guessed whenever the column, its
    option set or the rows cannot be read, which is the one invariant this module exists for.

    The loss is table-scoped because the write is: the only cells it touches are this column's.
    A ``Lookup`` in another table that mirrors this one is named on the same terms
    ``field_delete_loss`` names it, with the same precision gap, and only when something is
    really being destroyed — an empty shrink pays for no extra read.
    """
    table = scan.require_table(table_id)
    spec = table.field(field_id)
    if spec is None:
        raise LossNotEnumerable(
            f"table {table_id!r} has no column {field_id!r}, so what replacing its option set "
            f"would cost cannot be worked out. Re-read the table's columns and re-plan.")
    if not spec.is_select:
        raise LossNotEnumerable(
            f"column {spec.field_name!r} ({field_id!r}) in table {table_id!r} does not read back "
            f"as a select column (it is {spec.ui_type or spec.field_type!r}), so an option set "
            f"cannot be replaced on it and what this update would do to its cells cannot be "
            f"worked out.")
    existing = spec.options
    if existing is None:
        raise LossNotEnumerable(
            f"the option set of column {spec.field_name!r} ({field_id!r}) in table {table_id!r} "
            f"did not come back on this read, so which options this update DROPS — and which "
            f"cells go with them — cannot be worked out. {SELECT_OPTION_ID_IS_THE_CELL_ANCHOR}")

    proposed = [dict(option or {}) for option in (options or ())]
    proposed_ids = {option.get("id") for option in proposed if option.get("id")}
    dropped = [_option_row(option) for option in existing
               if option.get("id") not in proposed_ids]
    kept = [_option_row(option) for option in existing if option.get("id") in proposed_ids]
    dropped_names = [option["name"] for option in dropped if option["name"] is not None]

    # A select cell reads back as the option NAME, so a dropped name a KEPT option also carries
    # cannot be attributed exactly. Disclosed rather than silently over-counted.
    ambiguous = sorted({option["name"] for option in kept
                        if option["name"] in set(dropped_names)})

    records: List[Dict] = []
    values_lost = 0
    for record in scan.records(table_id):
        held = _cell_values((getattr(record, "fields", None) or {}).get(spec.field_name))
        lost = [value for value in held if value in set(dropped_names)]
        if not lost:
            continue
        remaining = [value for value in held if value not in set(dropped_names)]
        values_lost += len(lost)
        records.append({
            "record_id": getattr(record, "record_id", None),
            "values_lost": lost,
            "values_kept": remaining,
            "cell_becomes_empty": not remaining,
        })

    destroys = bool(records)
    lookups = (_lookups_into(scan, [table_id], LOOKUP_MAY_MIRROR_A_SHRUNK_COLUMN)
               if destroys else [])
    what = SELECT_OPTION_SHRINK_MEASURED_EMPTY
    if destroys:
        what = (f"{SELECT_OPTION_SHRINK_DESTROYS_CELLS} This update drops "
                f"{len(dropped)} option(s) — {dropped_names} — and {len(records)} record(s) hold "
                f"one, losing {values_lost} value(s) in total; each is named above with what its "
                f"cell keeps. {SELECT_OPTION_SHRINK_IS_NOT_A_TRASH} {REMAP_THEN_SHRINK}")
    if ambiguous:
        what += (f" AMBIGUOUS: {ambiguous} names both a dropped option and a kept one, and a "
                 f"select cell reads back as the option NAME, so those records cannot be "
                 f"attributed exactly — they are named as candidates and the count is an upper "
                 f"bound.")
    return {
        "kind": "select-option-shrink",
        "app_token": scan.app_token,
        "columns": [_column(scan, spec)],
        "options_dropped": dropped,
        "options_kept": kept,
        "options_added": sum(1 for option in proposed if not option.get("id")),
        "records": records,
        "records_affected": len(records),
        "values_lost": values_lost,
        "ambiguous_option_names": ambiguous,
        # AC3: the answer to *"will this destroy anything?"* is a MEASURED boolean on every
        # preview this function returns, which is what lets the engine gate the shrink that
        # destroys and wave through the one that does not.
        "destroys": destroys,
        "other_tables": sorted({row["table_id"] for row in lookups}),
        "mirror": None,
        "inbound_links": [],
        "inbound_lookups": lookups,
        "tables": [],
        "what": what,
        "remap_first": REMAP_THEN_SHRINK,
        "not_traced": FORMULA_EXPRESSIONS_ARE_NOT_TRACED,
        "invariant": LOSS_MUST_BE_ENUMERABLE,
        "evidence": [dev_repo(f"{_CAPTURES}/ld462-01-select-option-shrink.json"),
                     dev_repo(f"{_CAPTURES}/ld339-01-select-option-id-remint.json")],
    }


def table_delete_loss(scan: AppScan, table_ids: Sequence[str]) -> Dict:
    """What deleting one or more TABLES destroys — **and what it silently dangles elsewhere**.

    The second half is the whole point: the tables that lose something are not the tables the
    caller named, and nothing afterwards will say so.
    """
    doomed = [scan.require_table(table_id) for table_id in table_ids]
    doomed_ids = {table.table_id for table in doomed}

    inbound = []
    for table in scan.tables:
        if table.table_id in doomed_ids:
            continue
        for spec in table.fields:
            if not spec.is_link or spec.target_table_id not in doomed_ids:
                continue
            inbound.append({
                "table_id": table.table_id,
                "table_name": table.name,
                "field_id": spec.field_id,
                "field_name": spec.field_name,
                "ui_type": spec.ui_type,
                "target_table_id": spec.target_table_id,
                "cells_with_data": scan.cells_with_data(table.table_id, spec.field_name),
                "effect": (INBOUND_DUPLEX_IS_LOST_EITHER_WAY if spec.is_duplex
                           else INBOUND_LINK_DANGLES_SILENTLY),
            })

    lookups = _lookups_into(scan, sorted(doomed_ids), INBOUND_LOOKUP_BLANKS_SILENTLY)

    return {
        "kind": "table-delete",
        "app_token": scan.app_token,
        "tables": [{"table_id": table.table_id, "table_name": table.name,
                    "columns": len(table.fields), "rows": scan.row_count(table.table_id)}
                   for table in doomed],
        "columns": [_column(scan, spec) for table in doomed for spec in table.fields],
        "inbound_links": inbound,
        "inbound_lookups": lookups,
        "other_tables": sorted({row["table_id"] for row in inbound}
                               | {row["table_id"] for row in lookups}),
        "mirror": None,
        "what": (
            "Deleting a table destroys every column and every row in it. It also destroys or "
            "dangles every link column pointing at it — in every OTHER table of this Base — "
            "SILENTLY, and the two link kinds end differently: a ONE-WAY link column SURVIVES "
            "with the dead table's id, its cells keeping the record ids of deleted rows, while "
            "a TWO-WAY link column does NOT survive at all, because its twin lives inside the "
            "table being deleted and the source column goes with it. Nothing errors either "
            "way; the per-column entries above say which outcome each one gets. Every Lookup "
            "column that mirrors it, in every other table, survives too and goes BLANK on "
            "every row for the same reason: the values were that table's, and nothing says "
            f"so. {NO_API_UNDO}"
        ),
        "not_traced": FORMULA_EXPRESSIONS_ARE_NOT_TRACED,
        "trash": TRASH_NOT_PURGE,
        "invariant": LOSS_MUST_BE_ENUMERABLE,
        "evidence": [dev_repo(f"{_CAPTURES}/p0-5-02-symmetric-link-deletion.json"),
                     dev_repo(f"{_CAPTURES}/06-06-destructive-ops.json"),
                     dev_repo(f"{_P0} § 2")],
    }


__all__ = [
    "AppScan",
    "COLUMN_IS_DESTROYED",
    "DUPLEX_MIRROR_ALREADY_GONE",
    "DUPLEX_MIRROR_IS_DESTROYED",
    "FORMULA_EXPRESSIONS_ARE_NOT_TRACED",
    "INBOUND_DUPLEX_IS_LOST_EITHER_WAY",
    "INBOUND_LINK_DANGLES_SILENTLY",
    "INBOUND_LOOKUP_BLANKS_SILENTLY",
    "INBOUND_LOOKUP_MAY_ROLL_UP_THIS_COLUMN",
    "LOOKUP_MAY_TRAVERSE_THIS_LINK",
    "LOOKUP_MAY_MIRROR_A_SHRUNK_COLUMN",
    "LOSS_MUST_BE_ENUMERABLE",
    "LossNotEnumerable",
    "NO_API_UNDO",
    "OBJECT_GONE_CODES",
    "PAGING_PROOF_SEAM",
    "SCAN_COST_DISCLOSURE",
    "SELECT_OPTION_SHRINK_IS_NOT_A_TRASH",
    "SELECT_OPTION_SHRINK_MEASURED_EMPTY",
    "ScannedField",
    "ScannedTable",
    "TRASH_NOT_PURGE",
    "field_delete_loss",
    "scan_app",
    "select_option_shrink_loss",
    "table_delete_loss",
]
