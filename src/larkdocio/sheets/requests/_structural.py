"""larkdocio.sheets.requests._structural — structural dimension writes — insert / delete / append, the three axis-twin pairs.

Carries its own shared base :class:`_Structural` and the span/shift helpers. Its
``_require_positive`` is the one helper another family reuses (``_dimensions``).

Split out of the flat 2,462-line ``sheets/requests.py`` by LD-224, **verbatim** —
pre-split lines 460–764. The package's ``__init__`` re-exports every name defined here,
so ``from larkdocio.sheets.requests import <name>`` is unchanged.
"""
from dataclasses import dataclass

from larkdocio.errors import LarkConfigError
from larkdocio.sheets.write_range import parse_write_range

from ._gates import WriteOpKind


# --------------------------------------------------------------------------- #
# Structural dimension writes (LD-121, D2/D3/D8).                              #
#                                                                               #
# THE trap this slice exists to encode: the insert and delete endpoints take    #
# the SAME `{startIndex, endIndex}` body but interpret it in OPPOSITE            #
# conventions — `insert_dimension_range` is **0-indexed, half-open              #
# `[start, end)`**; `dimension_range` DELETE is **1-indexed, INCLUSIVE          #
# `[start, end]`** (LD-107 Q4). A naive caller who computed one and reused it    #
# for the other silently corrupts data. So the CALLER-FACING surface is a set   #
# of DISTINCT typed **semantic-span** request objects — insert carries a        #
# `before_*` position + a `count`; delete carries a 1-indexed inclusive         #
# `first`/`last` — and each converts to its endpoint's native convention        #
# INTERNALLY (:meth:`descriptor`). There is deliberately **no** raw             #
# `(start_index, end_index)` on any request; the wrong convention is not        #
# expressible (D3). Apply trusts the reply's `addCount`/`delCount` and          #
# MANDATORILY re-reads geometry (never assumes parity, D2).                     #
#                                                                               #
# LD-461 adds the second half of that guarantee — the DESCRIPTION. The          #
# caller-facing positions (`before_row`/`before_col`/`first`/`last`) are        #
# 1-based against DISPLAYED position (`POSITION_CONVENTION`), which for an      #
# INSERT is a DIFFERENT base from the wire span printed beside them. Both       #
# bases are now named in the diagnostics, because a reader who inferred the     #
# parameter's base from the neighbouring wire `convention` line shifted live    #
# data with `code: 0` and no warning.                                           #
# --------------------------------------------------------------------------- #

#: The **caller-facing** position convention of every structural request in this module:
#: ``before_row`` / ``before_col`` / ``first`` / ``last`` are **1-based against DISPLAYED
#: row or column position** — position 1 is the first row / column ``A``.
#:
#: It is named as a constant, and printed beside the wire ``convention`` rather than left to
#: be inferred from it, because for an **insert** the two bases DIFFER: the parameter is
#: 1-based, the wire span is 0-based half-open. Reading the wire convention as the
#: parameter's basis inserts one column early with ``code: 0`` and no warning, and shifts
#: live data (LD-461). The parameter's meaning did **not** change with that fix — only what this says of it.
POSITION_CONVENTION = "1-index-displayed"


def _insert_semantic(axis: str, field: str, position: int, count: int, start: int) -> str:
    """The ``semantic`` line of an insert — the one string a consumer prints.

    It carries **both** numbers with **both** bases named: the caller's position (1-based,
    displayed) and the span that actually goes on the wire (0-indexed half-open). One builder
    for both axes so the row and column twins cannot drift apart again.
    """
    return (
        f"insert {count} {axis}(s) before {axis} {position} "
        f"({field} is 1-based against displayed {axis} position; "
        f"wire span [{start}, {start + count}) is 0-index-half-open)"
    )


class DimensionSpanError(LarkConfigError, ValueError):
    """A structural row/column span is not writable **as given**.

    Raised at **construction** by :class:`DeleteRows` / :class:`DeleteCols` for a **reversed**
    inclusive span (``last < first``) — the fault the seat session hit as a bare
    ``ValueError`` with no example. The message follows the
    :class:`~larkdocio.sheets.formula.FormulaExpressionError` house standard: it names the
    fault, the consequence, **both** repairs, and a **valid-form example**.

    **Deliberately a subclass of BOTH** :class:`~larkdocio.errors.LarkConfigError` (so
    ``except LarkConfigError`` / ``except LarkDocIOError`` catches it, and the apply-time
    disposition boundary would classify it ``invalid-request``) **and** :class:`ValueError`
    (so every caller that already wrote ``except ValueError`` around a span construction is
    byte-unchanged — the typing is additive, never a migration).
    """


class _Structural:
    """Mixin marking a request as a **structural** dimension write (LD-121).

    Every structural request drives the same gated flow through
    :attr:`write_kind` ``"structure"`` and is classified as touching
    :data:`WriteOpKind.STRUCTURE` — so the write-gate differ (D4) turns on
    **both** the export style leg and the live merge leg for it (a structural edit
    shifts merges + style-bearing geometry). The per-op wire details are carried by
    :meth:`descriptor`; the previewed shift by :meth:`shift_preview`.
    """

    write_kind = "structure"
    is_structural = True
    is_rich = False

    @property
    def op_kinds(self) -> tuple:
        return (WriteOpKind.STRUCTURE,)


@dataclass(frozen=True)
class InsertRowsAt(_Structural):
    """Insert ``count`` blank rows immediately before row ``before_row``.

    ``before_row`` is **1-based against displayed row position** — ``before_row=2`` inserts
    above the row a viewer sees as row 2. That basis belongs to the *parameter*; the span
    this request then puts on the wire is a different base — the insert endpoint's native
    wire convention is **0-indexed, half-open ``[start, end)``** — reached by
    ``start = before_row - 1``, ``end = start + count`` (so ``InsertRowsAt(before_row=2,
    count=1)`` → wire span ``[1, 2)``, the live-probed ``insert_row`` capture). The two bases
    are **stated separately everywhere they are printed**: a plan's ``convention`` line
    describes the wire span ``start_index``/``end_index``, never ``before_row``, and the
    ``semantic`` line names both.

    A caller supplies a **position + a count**, never a raw span — a wire span in the wrong
    convention is not expressible here.
    """

    sheet_id: str
    before_row: int
    count: int = 1

    def __post_init__(self):
        _require_positive("before_row", self.before_row)
        _require_positive("count", self.count)

    def descriptor(self) -> dict:
        start = self.before_row - 1
        return {
            "op": "insert",
            "sheet_id": self.sheet_id,
            "major_dimension": "ROWS",
            "start_index": start,
            "end_index": start + self.count,
            "convention": "0-index-half-open",
            "position": self.before_row,
            "position_convention": POSITION_CONVENTION,
            "expected_count": self.count,
            "semantic": _insert_semantic("row", "before_row", self.before_row,
                                         self.count, start),
        }

    def shift_preview(self) -> dict:
        return _insert_shift("ROWS", self.before_row - 1, self.count)


@dataclass(frozen=True)
class InsertColsAt(_Structural):
    """Insert ``count`` blank columns immediately before column ``before_col`` — the column
    twin of :class:`InsertRowsAt`.

    ``before_col`` is **1-based against displayed column position** — ``before_col=3`` inserts
    to the left of the column a viewer sees as ``C``. The span this request puts **on the
    wire** is a different base — the endpoint's native 0-indexed half-open ``[start, end)``,
    with ``start = before_col - 1`` — and the plan's ``convention`` line describes **that wire
    span**, never ``before_col``. Reading the wire convention as the parameter's own costs a
    live column shift, so the ``semantic`` line names both bases.
    """

    sheet_id: str
    before_col: int
    count: int = 1

    def __post_init__(self):
        _require_positive("before_col", self.before_col)
        _require_positive("count", self.count)

    def descriptor(self) -> dict:
        start = self.before_col - 1
        return {
            "op": "insert",
            "sheet_id": self.sheet_id,
            "major_dimension": "COLUMNS",
            "start_index": start,
            "end_index": start + self.count,
            "convention": "0-index-half-open",
            "position": self.before_col,
            "position_convention": POSITION_CONVENTION,
            "expected_count": self.count,
            "semantic": _insert_semantic("column", "before_col", self.before_col,
                                         self.count, start),
        }

    def shift_preview(self) -> dict:
        return _insert_shift("COLUMNS", self.before_col - 1, self.count)


@dataclass(frozen=True)
class DeleteRows(_Structural):
    """Delete **1-indexed rows ``first``..``last`` INCLUSIVE**.

    Converts to the delete endpoint's native **1-indexed, inclusive ``[start, end]``**
    span internally — ``start = first``, ``end = last`` — so ``DeleteRows(first=2,
    last=3)`` → ``[2, 3]`` removing **2** rows (the live-probed ``delete_row`` capture:
    ``delCount 2``). The OPPOSITE convention to :class:`InsertRowsAt`'s half-open span:
    a caller expresses an inclusive ``first``/``last`` range, never a raw span, so the
    two conventions can never be confused.
    """

    sheet_id: str
    first: int
    last: int

    def __post_init__(self):
        _require_positive("first", self.first)
        _require_positive("last", self.last)
        if self.last < self.first:
            raise _reversed_span("DeleteRows", "row", self.first, self.last, self.sheet_id)

    def descriptor(self) -> dict:
        return {
            "op": "delete",
            "sheet_id": self.sheet_id,
            "major_dimension": "ROWS",
            "start_index": self.first,
            "end_index": self.last,
            "convention": "1-index-inclusive",
            "expected_count": self.last - self.first + 1,
            "semantic": f"delete rows {self.first}..{self.last} (inclusive)",
        }

    def shift_preview(self) -> dict:
        return _delete_shift("ROWS", self.first - 1, self.last - self.first + 1)


@dataclass(frozen=True)
class DeleteCols(_Structural):
    """Delete **1-indexed columns ``first``..``last`` INCLUSIVE** — the column twin of
    :class:`DeleteRows` (native 1-idx inclusive)."""

    sheet_id: str
    first: int
    last: int

    def __post_init__(self):
        _require_positive("first", self.first)
        _require_positive("last", self.last)
        if self.last < self.first:
            raise _reversed_span("DeleteCols", "column", self.first, self.last, self.sheet_id)

    def descriptor(self) -> dict:
        return {
            "op": "delete",
            "sheet_id": self.sheet_id,
            "major_dimension": "COLUMNS",
            "start_index": self.first,
            "end_index": self.last,
            "convention": "1-index-inclusive",
            "expected_count": self.last - self.first + 1,
            "semantic": f"delete columns {self.first}..{self.last} (inclusive)",
        }

    def shift_preview(self) -> dict:
        return _delete_shift("COLUMNS", self.first - 1, self.last - self.first + 1)


@dataclass(frozen=True)
class AppendDimension(_Structural):
    """Append ``length`` blank rows/columns at the grid **end** (``dimension_range``
    POST). No positional convention (an append has no start/end to confuse); the reply
    carries ``addCount``, which apply trusts + re-reads geometry to confirm."""

    sheet_id: str
    major_dimension: str
    length: int = 1

    def __post_init__(self):
        if self.major_dimension not in ("ROWS", "COLUMNS"):
            raise ValueError(f"AppendDimension: major_dimension must be ROWS|COLUMNS, got {self.major_dimension!r}")
        _require_positive("length", self.length)

    def descriptor(self) -> dict:
        return {
            "op": "append-dim",
            "sheet_id": self.sheet_id,
            "major_dimension": self.major_dimension,
            "length": self.length,
            "expected_count": self.length,
            "semantic": f"append {self.length} blank {self.major_dimension.lower()} at the grid end",
        }

    def shift_preview(self) -> dict:
        return {"kind": "append-dim", "dimension": self.major_dimension,
                "count": self.length, "shift_delta": self.length}


@dataclass(frozen=True)
class AppendRowsWithValues(_Structural):
    """The **``values_append INSERT_ROWS``** structural variant (the earlier-parked
    call, adopted here).

    Distinct from the *non-structural* append (overwrite-in-place / used-range
    append): this appends ``values`` **inserting new rows** (``?insertDataOption=
    INSERT_ROWS``), so it shifts the grid and is treated as a **structural** write —
    preview-gated, ``STALE_SHEET``-guarded, geometry re-read. The target
    ``a1_range`` is a :class:`~larkdocio.sheets.write_range.WriteRange` string; its
    ``sheet_id`` prefix names the tab for the geometry re-read.
    """

    a1_range: str
    values: list

    def descriptor(self) -> dict:
        sheet_id = parse_write_range(self.a1_range).sheet_id
        return {
            "op": "append-values",
            "sheet_id": sheet_id,
            "major_dimension": "ROWS",
            "a1_range": self.a1_range,
            "values": self.values,
            "insert_data_option": "INSERT_ROWS",
            "expected_count": len(self.values),
            "semantic": f"append {len(self.values)} row(s) with values (INSERT_ROWS) after {self.a1_range}",
        }

    def shift_preview(self) -> dict:
        return {"kind": "append-values", "dimension": "ROWS",
                "count": len(self.values), "shift_delta": len(self.values)}


def _reversed_span(cls_name: str, axis: str, first, last, sheet_id) -> DimensionSpanError:
    """The typed, EXAMPLED error for a reversed inclusive delete span.

    One builder for both axes so the wording — fault, consequence, both repairs, valid-form
    example — cannot drift between :class:`DeleteRows` and :class:`DeleteCols`.
    """
    return DimensionSpanError(
        f"{cls_name}: reversed span — first={first}, last={last}, and a delete span is "
        f"1-indexed INCLUSIVE with first <= last, so this names no {axis}s and nothing is "
        f"deleted (the request cannot be built, which is why you see this instead of a "
        f"surprise at apply). Either swap the ends "
        f"({cls_name}(sheet_id={sheet_id!r}, first={last}, last={first})) or, if you meant a "
        f"single {axis}, pass the same index twice "
        f"({cls_name}(sheet_id={sheet_id!r}, first={first}, last={first})). Note the "
        f"convention split: a DELETE span is 1-indexed inclusive, while an INSERT takes a "
        f"position + a count (InsertRowsAt(before_row=…, count=…))."
    )


def _require_positive(name: str, value) -> None:
    """A structural span coordinate must be a positive int (1-indexed positions /
    positive counts) — a sub-1 position or a non-positive count is a ``ValueError`` at
    construction, so a wrong-convention or empty span cannot even be built (D3)."""
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive (>= 1) int, got {value!r}")


def _insert_shift(dimension: str, at_index_0based: int, count: int) -> dict:
    """The previewed shift for an insert: ``count`` blanks at 0-idx ``at_index_0based``;
    everything at/after shifts by ``+count`` (AC4 — "exactly what shifts")."""
    return {
        "kind": "insert",
        "dimension": dimension,
        "at_index_0based": at_index_0based,
        "count": count,
        "shift_delta": count,
        "shifts_existing_from_0based": at_index_0based,
    }


def _delete_shift(dimension: str, at_index_0based: int, count: int) -> dict:
    """The previewed shift for a delete: ``count`` removed at 0-idx ``at_index_0based``;
    everything after shifts by ``-count`` (AC4)."""
    return {
        "kind": "delete",
        "dimension": dimension,
        "at_index_0based": at_index_0based,
        "count": count,
        "shift_delta": -count,
        "removes_from_0based": at_index_0based,
    }
