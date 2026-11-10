"""larkdocio.sheets.requests._dimensions — row/column dimension PROPERTIES — height / width / hide-show.

Deliberately NOT the structural family (a property write moves nothing), but it reuses
``_structural``'s ``_require_positive`` rather than forking a second copy of it.

Split out of the flat 2,462-line ``sheets/requests.py`` by LD-224, **verbatim** —
pre-split lines 767–1075. The package's ``__init__`` re-exports every name defined here,
so ``from larkdocio.sheets.requests import <name>`` is unchanged.
"""
from dataclasses import dataclass
from typing import Optional

from larkdocio.errors import LarkConfigError

from ._gates import WriteOpKind
from ._structural import _require_positive


# --------------------------------------------------------------------------- #
# Dimension PROPERTIES — the fourth verb on the dimension path (LD-185).        #
#                                                                              #
# `PUT …/dimension_range` with `dimensionProperties{visible, fixedSize}`: row   #
# height, column width, hide / show. Its index convention was **characterized   #
# live before anything was written** (tests/captures/sheets-dimension-probe/ in the source    #
# repository, captures                                                               #
# 01/02/03) because the two shipped range verbs on THIS EXACT PATH disagree and #
# the PUT verb's convention was documented nowhere. The answer:                 #
#                                                                              #
#   insert_dimension_range : 0-indexed, HALF-OPEN [start, end)                  #
#   delete_dimension_range : 1-indexed, INCLUSIVE [start, end]                 #
#   PUT dimension_range    : 1-indexed, INCLUSIVE [start, end]  <-- THIS ONE    #
#                                                                              #
# i.e. the PUT verb follows the DELETE convention, not the INSERT one. Probed   #
# three ways: {2,3} landed on sheet rows 2 AND 3; startIndex 0 is refused       #
# outright (`90202 … must greater than 0`), so a 0-indexed reading is not even  #
# expressible; and {2,2} touches row 2 alone.                                  #
# --------------------------------------------------------------------------- #

#: The **characterized** native index convention of ``PUT …/dimension_range`` — the *delete*
#: convention, deliberately named as a constant so a reader never has to re-derive it and a
#: test can pin it. Live evidence:
#: ``tests/captures/sheets-dimension-probe/captures/01-put-dimension_range-INDEX-CONVENTION.json``
#: (in the source repository).
DIMENSION_PROPERTY_CONVENTION = "1-index-inclusive"

#: The documented **≤5000 rows/columns per dimension op** ceiling (in the source repository, not in
#: the wheel: SHEETS.md § "Hard limits on the shipped ops"). Enforced at construction for
#: this family — the first shipped op to enforce it client-side rather than leave the caller
#: to meet it on the wire.
MAX_DIMENSION_SPAN = 5000


class DimensionPropertyError(LarkConfigError, ValueError):
    """A row/column **dimension-property** write is not writable **as given**.

    Raised at **construction** — so a request that Lark would reject, or (worse) accept and
    silently do something other than what the caller meant, **cannot be built** and costs zero
    API calls. Each message names the fault, the consequence, **every** repair, and a
    valid-form example (the :class:`DimensionSpanError` /
    :class:`~larkdocio.sheets.formula.FormulaExpressionError` house standard), and quotes the
    **probed** Lark answer it pre-empts:

    * a **reversed** band → ``90202 invalid dimension range, EndIndex must greater than or
      equal to StartIndex``;
    * **neither** property set → ``90204 dimensionProperties FixedSize and Visible are nil``;
    * a **negative** ``fixed_size`` → ``90204 invalid operation``;
    * ``fixed_size=0`` → Lark answers ``code 0`` and **CLEARS the custom size** (the row
      reverts to the tab's default height). It is **not** a hide, which is what a caller
      writing ``0`` almost always means — the one refusal here that pre-empts a *success*.

    **Deliberately a subclass of BOTH** :class:`~larkdocio.errors.LarkConfigError` (so
    ``except LarkConfigError`` / ``except LarkDocIOError`` catches it, and the apply-time
    disposition boundary would classify it ``invalid-request``) **and** :class:`ValueError`
    (so a caller who already wrote ``except ValueError`` around a span construction is
    unchanged) — exactly as :class:`DimensionSpanError` is.
    """


class _DimensionProperty:
    """Mixin marking a request as a **dimension-property** write (LD-185).

    Its own family, with its own :attr:`write_kind` and its own
    :data:`WriteOpKind.DIMENSION_PROPERTY` op-kind — deliberately **NOT** the structural
    family and **NOT** :data:`WriteOpKind.STRUCTURE`, because a property write moves nothing:
    no row shifts, no merge changes shape, no cell changes value. ``is_structural`` is
    therefore ``False`` (the structural leg's geometry-delta verification has nothing to
    measure here), and neither the export style leg nor the v3 merge leg is triggered — the
    posture :class:`WriteOpKind` documents for ``TAB`` / ``DATA_VALIDATION``.
    """

    write_kind = "dimension-property"
    is_structural = False
    is_rich = False

    @property
    def op_kinds(self) -> tuple:
        return (WriteOpKind.DIMENSION_PROPERTY,)


def _dimension_properties(visible, fixed_size, *, cls_name, axis, sheet_id, first, last) -> dict:
    """The validated ``dimensionProperties`` wire dict — the ONE validator both axes share,
    so the refusal wording cannot drift between rows and columns."""
    if visible is None and fixed_size is None:
        raise DimensionPropertyError(
            f"{cls_name}: no property to set — a dimension-property write must carry "
            f"`visible` and/or `fixed_size`, and this one carries neither, so it names a band "
            f"and asks for nothing (Lark answers this exact body '90204 dimensionProperties "
            f"FixedSize and Visible are nil'; the request cannot be built, which is why you "
            f"see this instead of a surprise at apply). Pass a size "
            f"({cls_name}(sheet_id={sheet_id!r}, first={first}, last={last}, fixed_size=60)), "
            f"a visibility ({cls_name}(sheet_id={sheet_id!r}, first={first}, last={last}, "
            f"visible=False)), or both."
        )
    if visible is not None and not isinstance(visible, bool):
        raise DimensionPropertyError(
            f"{cls_name}: `visible` must be a bool (True = show, False = hide), got "
            f"{visible!r}. A truthy string like 'false' would HIDE nothing while reading as a "
            f"hide, so it is refused rather than coerced. Write "
            f"{cls_name}(sheet_id={sheet_id!r}, first={first}, last={last}, visible=False)."
        )
    if fixed_size is not None:
        if isinstance(fixed_size, bool) or not isinstance(fixed_size, int):
            raise DimensionPropertyError(
                f"{cls_name}: `fixed_size` must be an int number of PIXELS, got "
                f"{fixed_size!r}. Write {cls_name}(sheet_id={sheet_id!r}, first={first}, "
                f"last={last}, fixed_size=60)."
            )
        if fixed_size == 0:
            raise DimensionPropertyError(
                f"{cls_name}: fixed_size=0 does not hide a {axis} — probed live, Lark accepts "
                f"it with code 0 and CLEARS the custom size, so the {axis} reverts to the "
                f"tab's default and it looks like nothing happened. To HIDE the {axis}, pass "
                f"the visibility instead ({cls_name}(sheet_id={sheet_id!r}, first={first}, "
                f"last={last}, visible=False)); to set a size, pass a positive pixel count "
                f"({cls_name}(sheet_id={sheet_id!r}, first={first}, last={last}, "
                f"fixed_size=60)). Clearing a custom size back to the default is not exposed "
                f"as a magic zero — it would be a separate, named intent."
            )
        if fixed_size < 0:
            raise DimensionPropertyError(
                f"{cls_name}: fixed_size must be a positive pixel count, got {fixed_size}. A "
                f"negative size is refused by Lark itself ('90204 invalid operation'), a "
                f"message that names nothing — so it is refused here, before any call. Write "
                f"{cls_name}(sheet_id={sheet_id!r}, first={first}, last={last}, "
                f"fixed_size={abs(fixed_size)}) if you meant that size, or pass "
                f"visible=False if you meant to hide the {axis}."
            )
    props = {}
    if visible is not None:
        props["visible"] = visible
    if fixed_size is not None:
        props["fixedSize"] = fixed_size
    return props


def _dimension_band(cls_name: str, axis: str, sheet_id, first, last) -> int:
    """Validate a 1-indexed INCLUSIVE band and return its count.

    The band is validated here — reversed and over-ceiling both refuse at **construction** —
    because both are knowable from the caller's own arguments, so neither should cost a call.
    """
    _require_positive("first", first)
    _require_positive("last", last)
    if last < first:
        raise DimensionPropertyError(
            f"{cls_name}: reversed span — first={first}, last={last}, and a "
            f"dimension-property span is 1-indexed INCLUSIVE with first <= last, so this "
            f"names no {axis}s and nothing would be set (Lark answers this body '90202 "
            f"invalid dimension range, EndIndex must greater than or equal to StartIndex'; the "
            f"request cannot be built, which is why you see this instead of a surprise at "
            f"apply). Either swap the ends ({cls_name}(sheet_id={sheet_id!r}, first={last}, "
            f"last={first})) or, if you meant a single {axis}, pass the same index twice "
            f"({cls_name}(sheet_id={sheet_id!r}, first={first}, last={first})). Note the "
            f"convention split on this one endpoint: a dimension-PROPERTY span and a DELETE "
            f"span are both 1-indexed inclusive, while an INSERT takes a position + a count "
            f"(InsertRowsAt(before_row=…, count=…))."
        )
    count = last - first + 1
    if count > MAX_DIMENSION_SPAN:
        raise DimensionPropertyError(
            f"{cls_name}: the band names {count} {axis}s ({first}..{last}) but a dimension op "
            f"accepts at most {MAX_DIMENSION_SPAN} — so first={first}, "
            f"last={MAX_DIMENSION_SPAN + first - 1} "
            f"is the widest band that starts where yours does, and last={last} is over it. "
            f"Split the write into bands of {MAX_DIMENSION_SPAN} or fewer {axis}s. (The "
            f"ceiling is Lark's, documented in SHEETS.md § 'Hard limits on the shipped ops'; "
            f"it is enforced here so an over-ceiling band is refused before any call rather "
            f"than answered by the API at the size where it matters.)"
        )
    return count


def _dimension_semantic(axis: str, first: int, last: int, props: dict) -> str:
    """The English restatement of the intent (the ``semantic`` every dimension op carries)."""
    band = f"{axis} {first}" if first == last else f"{axis}s {first}..{last} (inclusive)"
    parts = []
    if "fixedSize" in props:
        measure = "height" if axis == "row" else "width"
        parts.append(f"set {measure} to {props['fixedSize']}px")
    if props.get("visible") is False:
        parts.append("HIDE (the data stays, it becomes invisible to a viewer)")
    elif props.get("visible") is True:
        parts.append("show (un-hide)")
    return f"{' and '.join(parts)} on {band}"


@dataclass(frozen=True)
class SetRowProperties(_DimensionProperty):
    """Set **1-indexed rows ``first``..``last`` INCLUSIVE**'s height and/or visibility.

    ``fixed_size`` is the row **height in pixels**; ``visible=False`` **hides** the rows
    (``True`` shows them again). At least one of the two must be given, and a hide is
    **disclosed as a fidelity event** by the previewer — hiding a row makes real data
    invisible to a human while larkdocio's own reader still emits it.

    **The convention, stated beside the two divergent shipped ones** (this is the whole reason
    the family exists as typed requests rather than a raw span):

    * ``insert_dimension_range`` is **0-indexed, half-open ``[start, end)``**;
    * ``delete_dimension_range`` is **1-indexed, INCLUSIVE ``[start, end]``**;
    * ``PUT dimension_range`` — **this** verb — is **1-indexed, INCLUSIVE ``[start, end]``**,
      i.e. it follows the *delete* convention, **not** the insert one. Characterized live
      before any of this was written (``tests/captures/sheets-dimension-probe/``, in the source repository):
      ``{2, 3}`` landed on
      sheet rows 2 **and** 3, ``startIndex: 0`` is refused outright, and ``{2, 2}`` touches
      row 2 alone.

    So ``SetRowProperties(sheet_id, first=2, last=3, fixed_size=60)`` sets **two** rows'
    height, and a single row is ``first == last``. The caller-facing form is the human one —
    an inclusive ``first``/``last`` — and :meth:`descriptor` is the only place the native span
    is produced, so the wrong convention is not expressible.
    """

    sheet_id: str
    first: int
    last: int
    visible: Optional[bool] = None
    fixed_size: Optional[int] = None

    def __post_init__(self):
        _dimension_band("SetRowProperties", "row", self.sheet_id, self.first, self.last)
        _dimension_properties(
            self.visible, self.fixed_size, cls_name="SetRowProperties", axis="row",
            sheet_id=self.sheet_id, first=self.first, last=self.last)

    @property
    def properties(self) -> dict:
        """The validated ``dimensionProperties`` wire dict (``visible`` / ``fixedSize``)."""
        return _dimension_properties(
            self.visible, self.fixed_size, cls_name="SetRowProperties", axis="row",
            sheet_id=self.sheet_id, first=self.first, last=self.last)

    def descriptor(self) -> dict:
        props = self.properties
        return {
            "op": "dimension-property",
            "sheet_id": self.sheet_id,
            "major_dimension": "ROWS",
            "start_index": self.first,
            "end_index": self.last,
            "convention": DIMENSION_PROPERTY_CONVENTION,
            "properties": props,
            "expected_count": self.last - self.first + 1,
            "hides": props.get("visible") is False,
            "semantic": _dimension_semantic("row", self.first, self.last, props),
        }

    def property_preview(self) -> dict:
        """The previewed change — exactly what the write sets, and what it does **not**
        touch (no value moves, no row shifts, no merge changes shape)."""
        return _property_preview(self.descriptor())


@dataclass(frozen=True)
class SetColProperties(_DimensionProperty):
    """Set **1-indexed columns ``first``..``last`` INCLUSIVE**'s width and/or visibility —
    the column twin of :class:`SetRowProperties`, same native **1-indexed inclusive**
    convention (``{2, 3}`` sets columns **B and C**, probed), ``fixed_size`` in pixels."""

    sheet_id: str
    first: int
    last: int
    visible: Optional[bool] = None
    fixed_size: Optional[int] = None

    def __post_init__(self):
        _dimension_band("SetColProperties", "column", self.sheet_id, self.first, self.last)
        _dimension_properties(
            self.visible, self.fixed_size, cls_name="SetColProperties", axis="column",
            sheet_id=self.sheet_id, first=self.first, last=self.last)

    @property
    def properties(self) -> dict:
        return _dimension_properties(
            self.visible, self.fixed_size, cls_name="SetColProperties", axis="column",
            sheet_id=self.sheet_id, first=self.first, last=self.last)

    def descriptor(self) -> dict:
        props = self.properties
        return {
            "op": "dimension-property",
            "sheet_id": self.sheet_id,
            "major_dimension": "COLUMNS",
            "start_index": self.first,
            "end_index": self.last,
            "convention": DIMENSION_PROPERTY_CONVENTION,
            "properties": props,
            "expected_count": self.last - self.first + 1,
            "hides": props.get("visible") is False,
            "semantic": _dimension_semantic("column", self.first, self.last, props),
        }

    def property_preview(self) -> dict:
        return _property_preview(self.descriptor())


def _property_preview(desc: dict) -> dict:
    """The ``after`` payload for a dimension-property entry — the previewed change plus the
    explicit statement of what it leaves alone (the reason this op is off the heavy legs)."""
    return {
        "kind": "dimension-property",
        "dimension": desc["major_dimension"],
        "span": [desc["start_index"], desc["end_index"]],
        "count": desc["expected_count"],
        "convention": desc["convention"],
        "properties": desc["properties"],
        "hides": desc["hides"],
        "changes_values": False,
        "changes_geometry": False,
        "changes_merges": False,
    }
