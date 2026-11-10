"""larkdocio.base.computed — where a computed column's numbers came from, read for free.

A Lookup column is a **mirror of another table**, and a Markdown table that does not say so
can be misread as data someone typed. This module is that disclosure — the column-level
provenance for the computed and opaque field kinds — and, like the link-column reading beside
it, it is deliberately free: **it makes no call.** Everything below comes off a field
``property`` and a cell value a Base read has **already fetched**, so it costs nothing, needs
no credential and imports no transport.

**It reports provenance; it never renders a cell.** The Lookup and Formula renderers live in
:mod:`larkdocio.base.cells` and are not re-implemented, re-decided or wrapped here. The one
thing this module asserts about them is agreement: the type it reports a column as computing
is the same type the renderer dispatched the cell on.

**The wrapper's type is the TARGET field's, not the column's.** A Lookup cell reads as
``{"type": N, "value": [ … ]}`` where ``N`` is the type of the field being rolled up — ``1``
in the captured specimen, never ``19``. That type is knowable only from a **cell**: it is
carried on the schema inside ``filter_info.conditions``, which is one of the things the
transport below drops. With no cell in hand the honest answer is that it is unknown, and this
module answers ``None`` rather than falling back to the column's own type.

**What the transport delivers, and what it does not.** The read client returns SDK-typed
``AppTableField`` objects and :func:`larkdocio.base.table.field_spec` bridges them with the
SDK's own serializer. ``AppTableFieldProperty`` carries only the keys it declares, so of the
four keys that say what a Lookup rolls up from, exactly one survives:
``filter_info.target_table`` — **nested inside the filter configuration**, not at the top of
the property where a reader would look for it first. ``target_field``, ``roll_up`` and
``formula`` do not survive. Lark returns all four; this library's Lark client is what does not
carry three of them through. So the surface reports the **table** and says plainly that it
cannot report the field, the aggregation or the Lookup's formula string — an admitted gap
being worth more than a confident silence. A Formula (20) column has no such gap: both
``formula_expression`` and ``formatter`` are declared by the pinned SDK and come through
unchanged.

**No formula is ever parsed.** A formula string is **opaque provenance** — carried verbatim,
never parsed, tokenized, evaluated or executed, in either direction. Nothing in this library
computes a Base value; every computed value in a reading is the value the server already
computed and sent.

**The aggregation's commas are the server's, and the ambiguity they create is disclosed.** A
``LISTCOMBINE`` Lookup puts its ``","`` separators into the cell as **literal segments**, so
the render joins with the empty string — inserting a delimiter would double-separate. The
honest consequence is that once joined, a comma that came from the aggregation is
indistinguishable from a comma inside a value. That is a property of the server's
aggregation, not something this library can repair, so it is written down here and **no
escaping scheme Lark did not use is invented** — an escape would make the reader's output
disagree with what the product shows.

**Every kind described here is read-only, and the refusal is the write side's.** The reasons a
caller reads on this surface are the *same objects* the write encoder refuses with
(:mod:`larkdocio.base.write_vocabulary`), so a caller cannot be told two different stories
about why a Lookup cannot be set. There is no verb on this surface that writes anything.
"""
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Tuple

from larkdocio.base._typed import _by_name, _nested
from larkdocio.base.cells import STAGE_OPAQUE_MARKER, wrapper_type
from larkdocio.base.write_vocabulary import (
    NON_WRITABLE_PAIRS,
    NON_WRITABLE_REASONS,
)

#: The two computed kinds that carry provenance of their own.
LOOKUP = (19, "Lookup")
FORMULA = (20, "Formula")

#: Every computed / opaque pair, **imported from its one owner** — the write side's
#: vocabulary — rather than re-declared here. The read half and the write half describing
#: different sets is exactly what a second declaration would eventually produce.
COMPUTED_PAIRS: Tuple[Tuple[int, str], ...] = NON_WRITABLE_PAIRS

#: Where a Lookup's target table is read from. **Nested**, and named as a path rather than a
#: key because that nesting is the trap: the top of the property carries no ``target_table``.
TARGET_TABLE_PATH: Tuple[str, ...] = ("filter_info", "target_table")

#: The three provenance keys Lark sends and this library's client does not carry through.
#: Reported per column as :attr:`ComputedColumn.unavailable` so the gap travels with the
#: reading instead of living only in prose.
TRANSPORT_DROPPED_KEYS: Tuple[str, ...] = ("formula", "roll_up", "target_field")

#: The gap, in plain language. It has to be readable by someone who has never seen this
#: library's internals, and it must not read as though the server were withholding anything.
TRANSPORT_DOES_NOT_CARRY_THESE_KEYS = (
    "Which FIELD a Lookup column rolls up, HOW it aggregates those values, and the formula "
    "string stored on a Lookup are not reported here. Lark returns all three on the field's "
    "schema; the library's Lark client does not carry these keys through to the reading, so "
    "they are unavailable rather than absent. What does come through is the TABLE the column "
    "rolls up from, and that is reported. A Formula column is unaffected: its expression and "
    "its formatter both come through."
)

#: The join rule, stated once. The renderer already obeys it; this is the sentence that says
#: why, for a reader who would otherwise assume a missing delimiter is a bug.
LISTCOMBINE_JOIN_IS_THE_EMPTY_STRING = (
    "The server has already aggregated. A LISTCOMBINE Lookup sends its separators as literal "
    "segments inside the cell, so the segments are joined with nothing at all — inserting a "
    "delimiter here would put a second separator beside every one the server sent."
)

#: The consequence of that rule, disclosed rather than repaired.
LISTCOMBINE_COMMA_IS_AMBIGUOUS = (
    "Once the segments are joined, a comma that came from the aggregation is "
    "indistinguishable from a comma inside one of the aggregated values. That is a property "
    "of the server's aggregation, not something this library can repair, so it is disclosed "
    "here and left alone: no escaping the server did not use is invented, because an "
    "invented escape would make this reading disagree with what the product displays."
)

#: Why a Lookup's rows can be identical on every record — and the warning that goes with it.
LOOKUP_IS_A_CONSTRAINED_FORMULA = (
    "A Lookup is really a constrained Formula: the captured specimen carries roll_up 0 "
    "alongside a formula that aggregates the whole target table, which is why every record's "
    "cell holds the same identical text. A fixture author who sees identical rows must not "
    "'fix' them — they are what this column really returns. Note where that fact comes from: "
    "roll_up does not survive the typed field seam, so this rests on the capture the "
    "specimen was taken from and not on anything the shipped reading can see."
)

#: The Non-Goal, said on the surface that carries the string.
A_FORMULA_STRING_IS_OPAQUE = (
    "A formula string is carried as opaque provenance. It is never parsed, tokenized, "
    "evaluated or executed, in either direction — this library ships nothing that reads "
    "inside one."
)

#: The other half of the same rule, about values rather than expressions.
NOTHING_IS_COMPUTED_LOCALLY = (
    "Nothing here computes a Base value. Every computed cell in a reading is the value the "
    "server already computed and sent; the reader unwraps it and renders it, and would render "
    "a different answer if the server sent one."
)

#: A Lookup whose target field is not text has never been captured, and is recorded as
#: unmeasured rather than fabricated into a fixture.
NON_TEXT_LOOKUP_TARGET_IS_UNCAPTURED = (
    "Every Lookup ever captured here rolls up a text field, so a Lookup whose wrapper type is "
    "something other than text is uncaptured — unmeasured, not unsupported. The nearest real "
    "evidence that the wrapper type follows the target rather than the column is a Formula "
    "cell, whose wrapper reads as a number over the same code path."
)

#: What would change any of this. Written down so the next maintainer meets the decision.
REVISIT_TRIGGER = (
    "The pinned Lark client's typed field property gains target_field, roll_up or formula — "
    "at which point the gap above closes and the reading reports them instead of naming them "
    "unavailable. Separately: a LISTCOMBINE cell arriving with its separators outside the "
    "segment stream would move the join rule."
)

#: Where the specimen this module was measured against lives. Labelled inline rather than
#: via ``larkdocio.common.citations.dev_repo`` so this module keeps importing NOTHING
#: that could reach the network — the property its own guard asserts.
EVIDENCE = "tests/captures/base-study/captures/p1-q0-03-per-table.json (in the source repository)"


@dataclass(frozen=True)
class ComputedColumn:
    """One computed or opaque column, and what its own configuration says about its inputs.

    A reading of a schema plus, where a cell was in hand, that cell's typed wrapper. Never a
    dereference: the target table is **named**, not read, and no record anywhere else is
    fetched to fill this in.
    """

    field_name: str
    field_id: str
    field_type: Optional[int]
    ui_type: str
    #: The type of the value the column computes — the **target field's** type, taken from a
    #: cell's typed wrapper. ``None`` when no cell was in hand: it cannot be read off the
    #: schema, and the column's own type is not an answer to this question.
    value_type: Optional[int]
    #: The table a Lookup rolls up from, from the nested ``filter_info`` key. ``None`` for
    #: every other kind, and for a Lookup whose configuration does not carry it.
    rolls_up_from_table: Optional[str]
    #: Always ``None`` on a Lookup today — the key does not survive the transport.
    rolls_up_from_field: Optional[str]
    #: Always ``None`` on a Lookup today — the key does not survive the transport.
    aggregation: Optional[Any]
    #: A Formula column's expression, verbatim. Never parsed.
    formula_expression: Optional[str]
    #: The column's number/date formatter, where it declares one.
    formatter: Optional[str]
    #: The provenance keys that exist on the server and did not reach this reading.
    unavailable: Tuple[str, ...]
    #: What this column is, in a caller's words.
    note: str

    @property
    def writable(self) -> bool:
        """Always ``False``. Every kind on this surface is computed or opaque, and the
        refusal that enforces it lives on the write side."""
        return False

    @property
    def rolls_up(self) -> bool:
        """``True`` for a Lookup — the one kind that mirrors another table."""
        return (self.field_type, self.ui_type) == LOOKUP


def _property_of(field) -> Optional[Mapping]:
    """A field's ``property`` as a mapping, whatever shape it arrived in.

    A read hands back a typed object, a capture hands back a plain dict, and the structured
    read hands back the bridged dict. All three are read by name here — through the one shared
    step, :func:`larkdocio.base._typed._by_name` — so the reading does not depend on which door
    the field came through. **The three names below are this module's own contract**, not the
    shared walk's: it holds no list and copies exactly what it is asked for.
    """
    prop = getattr(field, "property", None)
    if prop is None or isinstance(prop, Mapping):
        return prop
    return _by_name(prop, ("filter_info", "formula_expression", "formatter"))


def _pair(field) -> Tuple[Optional[int], str]:
    return getattr(field, "type", None), getattr(field, "ui_type", "") or ""


def is_computed_column(field) -> bool:
    """``True`` for the eight computed / opaque pairs, by the landed pair set."""
    return _pair(field) in set(COMPUTED_PAIRS)


def read_only_reason(pair):
    """Why a computed pair cannot be set — **the landed refusal object itself**, not a copy.

    ``None`` for a pair that is writable, which is how a caller tells "computed" from
    "this surface does not know that pair".
    """
    try:
        return NON_WRITABLE_REASONS.get(tuple(pair))
    except TypeError:
        return None


def target_table_in(prop) -> Optional[str]:
    """The table a Lookup rolls up from, read off a field **property already in hand**.

    The same nested walk as :func:`target_table`, exposed for a caller that holds the property
    rather than the field — the destructive scan reads a Lookup's target this way. It is a
    door onto the one authored path, not a second one: a caller that re-walked
    :data:`TARGET_TABLE_PATH` itself is how this surface and that one would come to disagree
    about the same column. ``None`` when the key is not there, which is a normal shape and
    never an error here — what to DO about an unplaceable Lookup belongs to the caller.

    The property may be a mapping, a typed property object, or a mapping whose ``filter_info``
    is *itself* a typed object — the third is what a caller holding the read client's own
    fields has — and the walk reads all three by name.
    """
    value = _nested(prop, TARGET_TABLE_PATH)
    return value if isinstance(value, str) and value else None


def target_table(field) -> Optional[str]:
    """A Lookup column's target table id, from the **nested** ``filter_info`` key."""
    if _pair(field) != LOOKUP:
        return None
    return target_table_in(_property_of(field))


def computed_value_type(values: Sequence) -> Optional[int]:
    """The type a computed column's cells report — the **target field's**, from the first
    typed wrapper in hand.

    ``None`` when no value is a typed wrapper. That includes the legacy bare-value read
    route, whose cells announce themselves by having no wrapper at all.
    """
    for value in values or ():
        found = wrapper_type(value)
        if found is not None:
            return found
    return None


def _note_for(pair, prop: Optional[Mapping]) -> str:
    """What this column is, said for the caller rather than for the maintainer."""
    if pair == LOOKUP:
        table = _nested(prop, TARGET_TABLE_PATH)
        where = f" from table {table}" if isinstance(table, str) and table else ""
        return (
            f"This column is a Lookup: the server mirrors values{where} rather than anyone "
            f"typing them here. {TRANSPORT_DOES_NOT_CARRY_THESE_KEYS}"
        )
    if pair == FORMULA:
        return (
            "This column is a Formula: the server computes every cell from the expression "
            f"stored on the field. {NOTHING_IS_COMPUTED_LOCALLY}"
        )
    if pair == (24, "Stage"):
        return STAGE_OPAQUE_MARKER
    reason = NON_WRITABLE_REASONS.get(pair)
    return reason if reason else "This column is maintained by the server."


def computed_column(field, values: Sequence = ()) -> Optional[ComputedColumn]:
    """One field → its :class:`ComputedColumn` reading, or ``None`` if it is not computed.

    ``values`` are that column's **raw** cell values, when the caller has them; they are read
    only for the typed wrapper's type and are never rendered here.
    """
    pair = _pair(field)
    if pair not in set(COMPUTED_PAIRS):
        return None
    prop = _property_of(field)
    mapping = prop if isinstance(prop, Mapping) else {}
    expression = mapping.get("formula_expression")
    formatter = mapping.get("formatter")
    return ComputedColumn(
        field_name=getattr(field, "field_name", "") or "",
        field_id=getattr(field, "field_id", "") or "",
        field_type=pair[0],
        ui_type=pair[1],
        value_type=computed_value_type(values),
        rolls_up_from_table=target_table(field),
        rolls_up_from_field=None,
        aggregation=None,
        formula_expression=expression if isinstance(expression, str) else None,
        formatter=formatter if isinstance(formatter, str) else None,
        unavailable=TRANSPORT_DROPPED_KEYS if pair == LOOKUP else (),
        note=_note_for(pair, mapping),
    )


def computed_columns(fields: Sequence, records: Sequence = ()) -> Tuple[ComputedColumn, ...]:
    """Every computed column in a field list, **in field order** — the order the schema was
    read in, never a sort.

    ``records`` are the raw records the same read fetched; each column's cells are picked out
    of them by field name, which is the key ``records/search`` returns them under. A field no
    record carries simply has no cell in hand, and its value type reads ``None``.
    """
    readings = []
    for field in fields or ():
        if not is_computed_column(field):
            continue
        name = getattr(field, "field_name", "") or ""
        values = [value for value in (_values_of(record).get(name) for record in records or ())
                  if value is not None]
        readings.append(computed_column(field, values=values))
    return tuple(readings)


def _values_of(record) -> Mapping:
    if isinstance(record, Mapping):
        return record.get("fields") or {}
    return getattr(record, "fields", None) or {}


__all__ = [
    "A_FORMULA_STRING_IS_OPAQUE",
    "COMPUTED_PAIRS",
    "EVIDENCE",
    "FORMULA",
    "LISTCOMBINE_COMMA_IS_AMBIGUOUS",
    "LISTCOMBINE_JOIN_IS_THE_EMPTY_STRING",
    "LOOKUP",
    "LOOKUP_IS_A_CONSTRAINED_FORMULA",
    "NON_TEXT_LOOKUP_TARGET_IS_UNCAPTURED",
    "NOTHING_IS_COMPUTED_LOCALLY",
    "REVISIT_TRIGGER",
    "TARGET_TABLE_PATH",
    "TRANSPORT_DOES_NOT_CARRY_THESE_KEYS",
    "TRANSPORT_DROPPED_KEYS",
    "ComputedColumn",
    "computed_column",
    "computed_columns",
    "computed_value_type",
    "is_computed_column",
    "read_only_reason",
    "target_table",
    "target_table_in",
]
