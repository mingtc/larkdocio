"""larkdocio.base.table — Base → Markdown assembly, and the structured intermediate.

The cell registry renders cells and the read client fetches them; this is the seam that
turns a Base into a
document. Per table: ``## <table name>`` from ``GET …/tables``, a GFM header row from
``GET …/fields`` **in field order**, then one row per record from ``POST …/records/search``,
every cell rendered by the registry in :mod:`larkdocio.base.cells`.

**This layer arranges rendered cells; it never re-renders one.** Every cell comes from
:func:`larkdocio.base.cells.render_row`, so there is exactly one opinion in the library
about what a Base cell looks like, and a test compares the assembled rows against that
function directly.

**Rows project against the FIELD LIST — the invariant this module exists to enforce.** An
empty cell is an **absent key** in ``records/search``: a populated-but-empty column appears
in no record at all. So the assembler iterates the *fields*, never the keys a record happens
to carry; a union-of-observed-keys implementation drops columns and shifts every cell left.
Every row is exactly ``len(fields)`` wide by construction.

**``view_id`` is NOT a column selector, and no entry point here takes one.** With fields
hidden in a view, ``fields?view_id=`` returned **all** fields in unscoped order and
``records/search {view_id}`` returned the **same** field keys per row
(``p0-3-03-view-projection.json``); ``PATCH property.hidden_fields`` on a view is accepted
and has no API effect at all. So L1 renders **the table's schema**, and the only genuine
server-side projection is ``field_names`` — which L1 does not expose either (a ``field_id``
there is a hard ``1254045``).

**Degenerate shapes are well-formed, not crashes.** A table with fields and no records is a
header and a separator with no body. A table with no fields is a named heading and
:data:`EMPTY_TABLE_MARKER` — never a zero-column table. A Base with no tables is
:data:`EMPTY_BASE_MARKER`, and that shape is **reachable in the wild**: the husk app
``Example3…`` answers ``{"items": []}`` with no ``total``, no ``page_token`` and no
``has_more`` (``02-bitable18-tables.json``), which no healthy app does. The rule it teaches
is wider than the one case — **a missing counter or cursor may never be assumed present** —
so nothing in the code below consults either one; the walk that would have is the client's,
and it already believes the cursor rather than the flag.

**The SDK-typed field seam, and what the pinned SDK drops.** The read client returns
SDK-typed ``AppTableField`` objects; the cell renderers read a plain ``property``
**dict**. :func:`field_spec` bridges them with the SDK's own serializer rather than a
hand-rolled attribute walk. That bridge is lossy in one direction and the loss is
**recorded, not hidden**: ``AppTableFieldProperty`` carries only the keys it declares, so
five keys observed in the captures — ``back_field_id``, ``input_type``, ``formula``,
``roll_up``, ``target_field`` — do not survive it (``BASE.md``, in the source repository, § Limitations,
row 12).
**Not one of them is read by any renderer** (:data:`RENDERER_PROPERTY_KEYS`), which is why
L1 is unaffected, and the dropped set is pinned by a test over every captured field so that
a *renderer-relevant* key joining it reddens the suite instead of quietly rendering wrong.

**GFM safety.** A cell carrying a ``|``, a newline or padding cannot break the table:
:func:`escape_cell` is **byte-identical** to the docx table serializer's convention
(``BLOCKS.md`` type 31) and to the Sheets surface's re-use of it, and a test asserts the
equivalence rather than claiming it. The escape is a *Markdown* concern — the structured
intermediate carries the cell **unescaped**, because a consumer who took the structured
route asked precisely not to be handed Markdown.

**Determinism.** Assembly is pure: same captured payload in, byte-identical Markdown out.
Date cells are a pure function of ``(value, date_formatter, time_zone)`` — the zone comes
from ``GET …/apps/{app_token}`` and never from the host clock or locale.
"""
import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Tuple

from lark_oapi.core.json import JSON

from larkdocio.base import date_zone
from larkdocio.base.cells import (
    FieldSpec,
    RenderContext,
    render_row,
)
from larkdocio.base.computed import (
    ComputedColumn,
    computed_columns as _computed_columns,
)
from larkdocio.base.referential import (
    LinkColumn,
    dangling_link_columns,
    link_columns,
)

#: Emitted for a table that has no fields at all. A zero-column pipe table is not valid
#: GFM, so the heading gets a marker instead.
EMPTY_TABLE_MARKER = "_(empty table — this table has no fields)_"

#: Emitted for a Base with no tables. Reachable in the wild (the husk app).
EMPTY_BASE_MARKER = "_(empty Base — it has no tables)_"

#: Default per-table heading level (H2), matching the Sheets surface's tab headings.
DEFAULT_HEADING_LEVEL = 2

#: The ``property`` keys the Base **read surface** actually reads. Kept here because the
#: SDK's typed property model is lossy: the guard that pins the dropped set asserts that none
#: of these is ever in it, and a second test checks this list against the reading modules
#: themselves so it cannot rot into a comforting fiction.
#:
#: **Entries are PATHS, and the guard compares them as paths.** A dropped parent shadows a
#: guarded child — losing ``filter_info`` wholesale would take ``filter_info.target_table``
#: with it — so the alarm is not defeated by the loss happening one level up.
#:
#: ``table_id`` joined the list with LD-269: the opt-in link resolver reads a link column's
#: own ``property.table_id`` to know which table to follow it to. ``filter_info.target_table``
#: and ``formula_expression`` joined it with LD-270, which reads them for computed-column
#: provenance. All three are read-relevant rather than render-relevant, and the row-12 drift
#: alarm covers a wrong disclosure for the same reason it covers a wrong render. (Extending
#: this list is not the same as editing the pinned dropped set — that pin is asserted
#: elsewhere.)
RENDERER_PROPERTY_KEYS = frozenset({
    "formatter", "currency_code", "rating", "date_formatter", "options", "table_id",
    "filter_info.target_table", "formula_expression",
})

_DEFAULT_CONTEXT = RenderContext()


# --------------------------------------------------------------------------- #
# The SDK-typed field seam                                                     #
# --------------------------------------------------------------------------- #

def field_spec(field) -> FieldSpec:
    """One field → the :class:`~larkdocio.base.cells.FieldSpec` the renderers dispatch on.

    Accepts what the client hands back (an SDK ``AppTableField``), what a capture holds (the
    raw dict), or a ``FieldSpec`` already — so a fixture does not have to go through the SDK
    to be readable, and the shipped path does not have to leave it.
    """
    if isinstance(field, FieldSpec):
        return field
    if isinstance(field, dict):
        return FieldSpec.from_payload(field)
    return FieldSpec(
        field_name=getattr(field, "field_name", "") or "",
        type=getattr(field, "type", None),
        ui_type=getattr(field, "ui_type", "") or "",
        property=_property_dict(getattr(field, "property", None)),
        field_id=getattr(field, "field_id", "") or "",
        is_primary=bool(getattr(field, "is_primary", False)),
    )


def _property_dict(prop) -> Optional[dict]:
    """An SDK property object → the plain dict the renderers read, via the SDK's own
    serializer (the same one the client's responses are deserialized with).

    ``None`` in, ``None`` out: ``property: null`` is the shape the auto fields (1001 / 1002)
    read back, and the date renderer keys its documented default formatter off exactly that,
    so collapsing it to ``{}`` would erase a distinction the render depends on.
    """
    if prop is None or isinstance(prop, dict):
        return prop
    try:
        decoded = json.loads(JSON.marshal(prop))
    except Exception:  # pragma: no cover - a shape the SDK cannot serialize
        return None
    return decoded if isinstance(decoded, dict) else None


def _raw_fields(values) -> Optional[dict]:
    """One record's ``fields`` body, kept **exactly as the wire carried it**.

    This is the opt-in raw view's whole contract in one function: no key renamed, no absence
    coerced, no epoch turned into a string, no list flattened or sorted, no dict re-keyed, no
    number reinterpreted. It is evidence, not a model — when Lark changes a shape the accessor
    changes with it, which is the correct behaviour for a surface whose only purpose is *"tell
    me what the server actually said"*.

    **The one permitted transformation, and its limit.** Where the pinned SDK hands the
    transport a typed object rather than a ``dict``, the raw form is the **JSON-decoded body**
    — the :func:`_property_dict` / ``JSON.marshal`` precedent already in this module. Decoding
    is not normalization; renaming a key would be.

    That fallback has one asymmetry worth naming rather than discovering later: the SDK's
    serializer **omits a null-valued key**, so a body reaching raw through it would lose the
    difference between *"the key was `null`"* and *"the key was absent"*. It does not arise on
    the shipped path — ``AppTableRecord.fields`` deserializes to a plain ``dict`` and is
    returned untouched, which is why a captured ``{"link_record_ids": null}`` survives whole.

    A body the SDK cannot serialize yields ``None`` — *"there is no raw for this record"* —
    never ``{}``, which would claim the record was empty.
    """
    if isinstance(values, dict):
        return values
    try:
        decoded = json.loads(JSON.marshal(values))
    except Exception:  # pragma: no cover - a shape the SDK cannot serialize
        return None
    return decoded if isinstance(decoded, dict) else None


def _record_parts(record) -> Tuple[str, dict]:
    """A record → ``(record_id, fields)``. ``search`` returns only ``record_id`` — the
    legacy list's duplicated ``id`` is a different route and is not the pin."""
    if isinstance(record, dict):
        return record.get("record_id") or "", record.get("fields") or {}
    return (getattr(record, "record_id", "") or "",
            getattr(record, "fields", None) or {})


# --------------------------------------------------------------------------- #
# The structured intermediate                                                  #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class BaseRow:
    """One record, projected against the field list. ``cells`` is exactly as wide as the
    table's field list and holds **rendered, unescaped** cell text."""

    record_id: str
    cells: Tuple[str, ...]
    #: The record's own ``fields`` body, **exactly as ``records/search`` returned it** — the
    #: opt-in raw view (``read_base(url, retain_raw=True)``). ``None`` on every default read:
    #: nothing is retained unless it was asked for, and an empty dict here would be a claim
    #: that the cells were empty rather than that nothing was kept.
    #:
    #: It is the wire's own **name-keyed** body, so it is the parallel of ``cells`` rather
    #: than a second copy of it: an empty cell is an **absent key** here (``cells`` widens it
    #: to a blank because a table must be rectangular), and the two empty link forms — `null`
    #: and `[]` — stay the distinct facts they are. The *named* accessor with the typed
    #: refusal is :meth:`larkdocio.base.model.SnapshotRecord.raw`, which stands where the
    #: field names live.
    raw_fields: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class BaseTableRead:
    """One Base table: its identity, its schema, its projected rows — and the ``revision`` it
    was read at.

    **``revision`` is the change-detection anchor, and it means exactly four things.** It is
    the ``revision`` the ``GET …/tables`` reply carried for this table, so it costs **no extra
    call** — the read already receives that reply, and the number simply rides it.

    1. **It is per-table isolated.** An untouched sibling table stays where it was while the
       edited one advances, and the **app** revision does not move at all (capture ``05-08``;
       :mod:`larkdocio.base.plan`). There is deliberately **no** Base-level or app-level
       revision here, and none is synthesized from these — a max or a sum over tables would be
       a derived number presented as an API fact.
    2. **It is an OP counter, not a row counter.** A field create is ``+1``; one op, one bump
       (:mod:`larkdocio.base.plan`, :mod:`larkdocio.base.field_authoring`). So a post-write
       expectation of ``+N`` per row is wrong.
    3. **``0`` is a REAL observed value; ``None`` means "not known".** A freshly created Base
       reads ``0``, and the standing Scratch Base read ``0`` before moving to ``14``. So the
       two are kept distinguishable: nothing here defaults, coerces or renders an absent
       revision as ``0``.
    4. **There is no ``If-Match``** — this API ignores a precondition body key
       (:mod:`larkdocio.base`), so the revision is an **observation** and any guard built on it
       is client-side read-compare-write. It is the *only* compare-and-swap anchor bitable
       exposes, which is why the write engine reads this same number off this same call
       (:mod:`larkdocio.base.apply`).

    **The limitation, stated rather than papered over:** a Base with **zero tables** gives a
    consumer nothing to compare, and so does a change that moves no table's op counter — so a
    ledger must treat "nothing to compare" as "unknown", never as "unchanged".
    """

    table_id: str
    name: str
    fields: Tuple[FieldSpec, ...]
    rows: Tuple[BaseRow, ...]
    #: The computed / opaque columns and what their own configuration says about their
    #: inputs — derived at assembly, where the **raw** cell values are still in hand. It has
    #: to be derived there and stored: a computed cell's typed wrapper carries the target
    #: field's type, and that type cannot be recovered from the rendered string afterwards.
    #: Empty is the normal case, and costs no call either way.
    computed_columns: Tuple[ComputedColumn, ...] = ()
    #: The ``revision`` this table's ``GET …/tables`` entry carried — see the class docstring
    #: for what the number means. ``None`` means **not known** (the reply carried no revision,
    #: or the table was assembled from a payload that has none, as a docx-embedded Base is);
    #: ``0`` is a **real** value and is never synthesized to stand in for the unknown.
    revision: Optional[int] = None

    @property
    def width(self) -> int:
        """How many cells every row has — the field count, never a per-record count."""
        return len(self.fields)

    @property
    def link_columns(self) -> Tuple[LinkColumn, ...]:
        """Every link column in this table, with what its own configuration says about the
        table it points at — in field order.

        Derived from the schema this read already holds, so it costs **no call**: it is not
        behind a flag, because it costs nothing to be right about.
        """
        return link_columns(self.fields)

    @property
    def dangling_link_columns(self) -> Tuple[LinkColumn, ...]:
        """Only the link columns whose target table reads as deleted.

        A link whose whole target table was deleted keeps its target table's id and its cells
        keep record ids, while the target table's name drops out of the column's
        configuration and nothing anywhere reports an error — so a reader that says nothing
        renders a broken reference as an intact one. Empty is the normal case.
        """
        return dangling_link_columns(self.fields)


@dataclass(frozen=True)
class BaseRead:
    """A whole Base: its app metadata and its tables, in the order ``…/tables`` returned.

    ``time_zone`` is the app's own and is what date cells were rendered in. It can be
    ``None``: a docx-born embedded Base has none at all, and a Base this library created before
    the zone became declarable has none either.

    **When it is ``None`` the read SAYS SO.** :attr:`date_zone` is the zone the dates
    above were actually rendered in, :attr:`date_zone_assumed` is whether this library chose it
    rather than the Base declaring it, :attr:`date_zone_requested` is the declared zone in the
    one case where it was declared and could not be used (no tz database on this machine), and
    :attr:`date_zone_disclosure` is the sentence to show a person — the measured reason a
    date-only value can be one calendar day early. All four
    are **derived** rather than stored beside ``time_zone``, so they cannot drift from it, and
    none of them reaches the rendered Markdown: the disclosure is provenance on the result, not
    a marker in the output. The one policy is :mod:`larkdocio.base.date_zone`.

    **They are derived from ``time_zone`` AND from this machine** — stated because it reads
    like a pure function of the payload and is not: a zone the Base declares can only be
    rendered in where the host carries a tz database for it, so the same payload read on a slim
    container answers ``date_zone == "UTC"``, ``date_zone_assumed == True`` and
    ``date_zone_requested == <the declared zone>``. That was true before it was disclosed —
    the read fell back to UTC and reported the zone it was asked for — and since 1.51.0 it is
    visible in these four values instead of only in the rendered dates.

    ``link_resolution`` is the **cost disclosure** of the opt-in cross-table link resolution
    (:class:`larkdocio.base.link_resolution.LinkResolution`) — how many extra API calls it
    made, which target tables it touched, and the typed per-id outcome of every link it
    followed. ``None`` on every default read: with resolution off nothing was followed, and
    an empty disclosure would be a claim that something was.
    """

    app_token: str
    name: str
    time_zone: Optional[str]
    tables: Tuple[BaseTableRead, ...]
    link_resolution: Optional[object] = None

    @property
    def date_zone(self) -> str:
        """The zone the date cells above were rendered in — declared or assumed."""
        return date_zone.resolve_zone(self.time_zone).zone

    @property
    def date_zone_assumed(self) -> bool:
        """``True`` when :attr:`date_zone` is this library's choice rather than the Base's
        declaration governing. Then — and only then — :attr:`date_zone_disclosure` says so.

        **Two different causes, one answer**: the Base declared no zone, or it declared one
        this machine has no tz database to load. Releases before 1.51.0 reported the second
        case as ``False`` — the caller was told a zone they never got — and
        :attr:`date_zone_requested` is which of the two it was.
        """
        return date_zone.resolve_zone(self.time_zone).assumed

    @property
    def date_zone_requested(self) -> Optional[str]:
        """The zone the Base DECLARED when it could not be used, else ``None``.

        ``None`` covers both good outcomes and is not ambiguous between them, because
        :attr:`date_zone_assumed` separates them: assumed and ``None`` means the Base declared
        nothing; not assumed means the declaration was honoured and :attr:`date_zone` is it.
        """
        return date_zone.resolve_zone(self.time_zone).requested

    @property
    def date_zone_disclosure(self) -> Optional[str]:
        """The plain-language disclosure when the zone was assumed, else ``None``. Which
        sentence depends on which of the two assumptions happened."""
        return date_zone.zone_disclosure(self.time_zone)


# --------------------------------------------------------------------------- #
# Assembly                                                                     #
# --------------------------------------------------------------------------- #

def assemble_table(
    *,
    table_id: str,
    name: str,
    fields: Sequence,
    records: Sequence,
    context: RenderContext = _DEFAULT_CONTEXT,
    retain_raw: bool = False,
    revision: Optional[int] = None,
) -> BaseTableRead:
    """Fields + records → one :class:`BaseTableRead`.

    Every row is projected against ``fields`` and is therefore exactly ``len(fields)`` wide:
    a key the schema does not know cannot widen a row, and a field no record carries still
    gets its column. Cells come from :func:`larkdocio.base.cells.render_row`, so an absent
    key renders whatever that field's absence *means* — blank for most, ``[ ]`` for a
    checkbox, and the absent-with-reason marker for a Stage column.

    **``retain_raw`` is the one place a raw value can be kept, which is why the knob is
    here.** The record's ``fields`` body is in hand exactly once — right here, on its way into
    the renderer — and is dropped at the end of the iteration; the same fact
    ``computed_columns`` records about itself. Off (the default) nothing is retained and the
    row is byte-for-byte the row this function always built. On, each row also carries
    :attr:`BaseRow.raw_fields`, the wire body untouched. Either way this function makes no
    call: the payload was already received.

    ``revision`` is the table's own ``GET …/tables`` revision, carried through untouched and
    defaulting to ``None`` — **not known**, which is the honest shape for a caller (a
    docx-embedded Base, a snapshot rebuilt from records) that has no table listing in hand.
    It is never defaulted to ``0``, because ``0`` is a real observed revision.
    """
    specs = tuple(field_spec(field) for field in fields or ())
    rows = []
    for record in records or ():
        record_id, values = _record_parts(record)
        rows.append(BaseRow(
            record_id=record_id,
            cells=tuple(render_row(values, specs, context=context)),
            raw_fields=_raw_fields(values) if retain_raw else None,
        ))
    return BaseTableRead(
        table_id=table_id, name=name, fields=specs, rows=tuple(rows),
        computed_columns=_computed_columns(specs, records or ()),
        revision=revision,
    )


def assemble_base(
    *,
    app_token: str,
    name: str,
    time_zone: Optional[str],
    tables: Sequence[BaseTableRead],
    link_resolution=None,
) -> BaseRead:
    """Assembled tables → one :class:`BaseRead`, preserving the order they were given in
    (which is the order ``…/tables`` returned them — never a sort).

    ``link_resolution`` is carried through untouched and defaults to ``None`` — the shape of
    a read that followed no link.
    """
    return BaseRead(app_token=app_token, name=name, time_zone=time_zone,
                    tables=tuple(tables or ()), link_resolution=link_resolution)


# --------------------------------------------------------------------------- #
# Markdown                                                                     #
# --------------------------------------------------------------------------- #

def escape_cell(text: str) -> str:
    """Normalize one rendered cell so it stays valid inside a GFM pipe table.

    Byte-identical to the docx table serializer and to the Sheets surface's re-use of it
    (deliberate, and asserted by a test): strip outer whitespace, join internal newlines
    with ``<br>``, escape a literal ``|`` as ``\\|``.
    """
    return text.strip().replace("\n", "<br>").replace("|", "\\|")


def table_heading(table: BaseTableRead, level: int = DEFAULT_HEADING_LEVEL) -> str:
    """The Markdown heading for a table — its name, verbatim, from ``…/tables``."""
    return f"{'#' * level} {table.name}"


def render_table(table: BaseTableRead, heading_level: int = DEFAULT_HEADING_LEVEL) -> str:
    """One table → its heading plus one GFM table.

    A table with no fields renders its heading and :data:`EMPTY_TABLE_MARKER` — a
    zero-column pipe table is not valid GFM, and a silent omission would make a schemaless
    table indistinguishable from a missing one. A table with fields and no records renders
    the header and separator with no body, which is the honest shape: the columns exist.
    """
    heading = table_heading(table, heading_level)
    if not table.fields:
        return f"{heading}\n\n{EMPTY_TABLE_MARKER}"
    width = len(table.fields)
    lines = [
        "| " + " | ".join(escape_cell(f.field_name) for f in table.fields) + " |",
        "|" + "|".join(["---"] * width) + "|",
    ]
    for row in table.rows:
        lines.append("| " + " | ".join(escape_cell(cell) for cell in row.cells) + " |")
    return f"{heading}\n\n" + "\n".join(lines)


def render_base(document: BaseRead, heading_level: int = DEFAULT_HEADING_LEVEL) -> str:
    """A whole Base → Markdown: every table as its own headed GFM table, in order.

    A Base with no tables renders :data:`EMPTY_BASE_MARKER` rather than an empty string, so
    a caller can tell "read it, there was nothing" from "did not read it".
    """
    if not document.tables:
        return EMPTY_BASE_MARKER
    return "\n\n".join(
        render_table(table, heading_level) for table in document.tables)
