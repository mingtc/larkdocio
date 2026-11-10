"""larkdocio.sheets.write_range — the A1/range WRITE model on the L1 model.

The write client (:mod:`larkdocio.sheets.write_client`) addresses cells by
range. Rather than fork a parallel A1 parser, this **reuses L1's** A1/range
+ used-range vocabulary — :func:`~larkdocio.sheets.extent.column_number_to_a1` and
its inverse :func:`~larkdocio.sheets.extent.a1_column_to_number`, plus
:class:`~larkdocio.sheets.extent.UsedRange` — extending it **only** where a write
needs it:

* **Single-cell normalize.** A bare single cell is **not** a writable range
  (a range-bearing v2 endpoint rejects ``{sid}!A1`` with ``90202 wrong range``, as a
  live probe confirmed); :func:`parse_write_range` normalizes ``B2`` → ``B2:B2`` so a
  :class:`WriteRange` is **always** an explicit ``Start:End``. This feeds the write
  client's structural guarantee (:func:`~larkdocio.sheets.write_client.normalize_write_range`).
* **Range validation.** :meth:`WriteRange.validate` refuses — with an inspectable
  :class:`~larkdocio.errors.LarkConfigError`, **before any write** — an **inverted**
  range (``C3:A1``), an **out-of-grid** range (past the declared ``row_count`` ×
  ``column_count``), a sub-``1`` coordinate, or a column past the **100-column
  notation ceiling** (:data:`MAX_A1_COLUMN`).
* **Used-range awareness.** :func:`write_range_from_used_range` builds the write
  target that spans a discovered :class:`UsedRange` (L1's ``read_used_range`` /
  extent output); :func:`parse_write_range` resolves an **open** target (whole
  column ``A:A``, mixed ``A1:C``) against a supplied grid/used-range extent.

Cross-tab addressing (``{sid}!A1:B2``) is carried by an **opaque** ``sheet_id``
prefix — parsed off the last ``!`` and preserved verbatim (unicode / internal
whitespace intact); only the cell-range body is parsed strictly.

Scope: the offline addressing model only — no transport, no plan/apply gating.
Reader/render output is untouched (byte-identical).
"""
import re
from dataclasses import dataclass

from larkdocio.errors import LarkConfigError
from larkdocio.sheets.extent import (
    UsedRange,
    a1_column_to_number,
    column_number_to_a1,
)

#: Lark's A1 column-**notation** ceiling (LD-107 Q1: keep column-notation ranges
#: ≤ 100 columns). Column ``CV`` is number 100; a target past it is refused.
MAX_A1_COLUMN = 100

#: One A1 endpoint: optional letters (a column) then optional digits (a row). An
#: **open** endpoint names only one axis — ``A`` (whole column) or ``5`` (whole
#: row); a full endpoint names both (``A1``). At least one axis must be present.
_ENDPOINT_RE = re.compile(r"^([A-Za-z]*)(\d*)$")


class A1RangeError(LarkConfigError):
    """An A1 write target is not addressable **as written**.

    The typed category for every *form* fault on the way into a :class:`WriteRange` — a
    malformed endpoint (``"banana"``), a column-only / row-only endpoint where a full cell is
    required, an empty body, too many ``:`` separators, an open target with no grid extent to
    resolve it against, and (via :meth:`WriteRange.validate`) an inverted / sub-``1`` /
    out-of-grid / over-ceiling range.

    **Why it exists.** ``for_a1("<sid>!banana")`` used to raise a bare
    :class:`~larkdocio.errors.LarkConfigError` reading ``not a full A1 cell: 'banana'`` — the
    right *family* but no specific type, and **no valid-form example**, which is exactly the
    gap :class:`~larkdocio.sheets.formula.FormulaExpressionError` had already closed on the
    formula path (it names the fault, the consequence, and **both** repairs). This is that
    standard, applied to A1.

    Still a :class:`~larkdocio.errors.LarkConfigError` subclass, so every shipped
    ``except LarkConfigError`` / ``except LarkDocIOError`` caller is unchanged — and the
    apply-time disposition boundary still classifies it ``invalid-request``.
    """


#: The valid-form example every :class:`A1RangeError` carries (one string so the message,
#: the docs and the tests cannot drift). Names the two repairs a malformed target has: write
#: a full cell, or write a bounded ``Start:End`` range — and states the ``{sheet_id}!`` rule,
#: because the seat session's own trap was reaching for a tab **title**.
_A1_VALID_FORM = (
    "Valid forms: a full cell 'B2' (which normalizes to 'B2:B2'), or a bounded range "
    "'A1:B2'; for a cross-tab target prefix the tab's sheet_id (never its title) — "
    "'<sheet_id>!A1:B2'. An OPEN endpoint ('A' for a whole column, '5' for a whole row) is "
    "accepted only inside a two-part range AND only when a grid extent (grid_rows/grid_cols) "
    "is supplied to resolve it against."
)


@dataclass(frozen=True)
class A1Cell:
    """A single A1 cell coordinate — 1-indexed ``(col, row)``.

    The column is stored as a **number** (via L1's bijective base-26 vocabulary)
    so bounds checks are arithmetic; the A1 letters are emitted on demand. A bare
    cell is a **coordinate, not a writable range** — a :class:`WriteRange`
    wraps two cells into an explicit ``Start:End``.
    """

    col: int
    row: int

    def a1(self) -> str:
        return f"{column_number_to_a1(self.col)}{self.row}"

    @classmethod
    def parse(cls, text: str) -> "A1Cell":
        """Parse a **full** A1 cell (``B2`` → ``A1Cell(2, 2)``). A malformed or open
        (column-only / row-only) input is a :class:`LarkConfigError`."""
        col, row = _parse_endpoint(text)
        if col is None or row is None:
            raise A1RangeError(
                f"not a full A1 cell: {text!r} — a single-cell write target needs BOTH a "
                f"column and a row (letters then digits), so this target cannot be addressed "
                f"and no read or write is attempted. {_A1_VALID_FORM}"
            )
        return cls(col, row)


@dataclass(frozen=True)
class WriteRange:
    """A rectangular A1 **write** range on one tab — **always** ``Start:End``.

    Reuses L1's column vocabulary (no parallel parser). ``sheet_id`` is the opaque
    optional ``{sid}!`` prefix (cross-tab addressing, preserved verbatim);
    ``start`` / ``end`` are fully-bounded :class:`A1Cell`\\ s. Order is preserved on
    construction (an inverted range is representable so :meth:`validate` can refuse
    it); :meth:`validate` is the gate a caller runs **before any write**.
    """

    start: A1Cell
    end: A1Cell
    sheet_id: str | None = None

    def a1(self) -> str:
        body = f"{self.start.a1()}:{self.end.a1()}"
        return f"{self.sheet_id}!{body}" if self.sheet_id is not None else body

    @property
    def n_rows(self) -> int:
        return self.end.row - self.start.row + 1

    @property
    def n_cols(self) -> int:
        return self.end.col - self.start.col + 1

    def validate(self, *, grid_rows: int = None, grid_cols: int = None) -> "WriteRange":
        """Refuse — with an inspectable :class:`A1RangeError`, before any write —
        an inverted / sub-``1`` / over-ceiling / out-of-grid range. Returns ``self``
        on success so it chains (``parse_write_range(t).validate(...)``).

        ``grid_rows`` / ``grid_cols`` are the tab's declared extent (from the v3
        tab-query metadata / a :class:`UsedRange`); omit them to skip the out-of-grid
        check (inversion + the notation ceiling are always checked).

        The raised type is the typed :class:`A1RangeError` — still a
        :class:`~larkdocio.errors.LarkConfigError` subclass, so every existing catcher is
        unchanged — and the **inverted** message now carries the valid form, because that is
        the one an operator hits by hand (``C3:A1``). At *plan* time an inverted range that
        reaches Lark is separately re-categorized ``malformed-range`` rather than
        ``tab-vanished``.
        """
        for cell, label in ((self.start, "start"), (self.end, "end")):
            if cell.col < 1 or cell.row < 1:
                raise A1RangeError(
                    f"A1 range {self.a1()} has a sub-1 {label} coordinate "
                    f"(1-indexed cells only). {_A1_VALID_FORM}"
                )
        if self.start.col > self.end.col or self.start.row > self.end.row:
            raise A1RangeError(
                f"inverted A1 range {self.a1()}: start must be <= end on both axes — write "
                f"the top-left cell first ({self.end.a1()}:{self.start.a1()} is the same "
                f"rectangle written the right way round), or address a single cell. "
                f"{_A1_VALID_FORM}"
            )
        if self.end.col > MAX_A1_COLUMN:
            raise A1RangeError(
                f"A1 range {self.a1()} column {column_number_to_a1(self.end.col)} "
                f"exceeds the {MAX_A1_COLUMN}-column notation ceiling (column CV is the last "
                f"addressable column in a column-notation range); split the write into "
                f"≤{MAX_A1_COLUMN}-column ranges. {_A1_VALID_FORM}"
            )
        if grid_cols is not None and self.end.col > grid_cols:
            raise A1RangeError(
                f"A1 range {self.a1()} is out of grid: column {self.end.col} "
                f"> declared column_count {grid_cols} — narrow the range, or grow the tab "
                f"first (AppendDimension(major_dimension='COLUMNS', length=…)). "
                f"{_A1_VALID_FORM}"
            )
        if grid_rows is not None and self.end.row > grid_rows:
            raise A1RangeError(
                f"A1 range {self.a1()} is out of grid: row {self.end.row} "
                f"> declared row_count {grid_rows} — shorten the range, or grow the tab "
                f"first (AppendDimension(major_dimension='ROWS', length=…)). "
                f"{_A1_VALID_FORM}"
            )
        return self


def _malformed_endpoint(text) -> str:
    """The :class:`A1RangeError` message for a malformed A1 endpoint — fault, consequence,
    both repairs, and a valid-form example."""
    return (
        f"malformed A1 endpoint: {text!r} — an A1 endpoint is COLUMN LETTERS then ROW DIGITS "
        f"in that order (digits-before-letters, punctuation, or an empty endpoint cannot be "
        f"addressed), so no read or write is attempted. {_A1_VALID_FORM}"
    )


def _parse_endpoint(text: str):
    """One A1 endpoint → ``(col, row)`` 1-indexed, either axis open (``None``).

    ``A1`` → ``(1, 1)``; ``A`` → ``(1, None)`` (whole column); ``5`` → ``(None, 5)``
    (whole row). A malformed endpoint (empty, digits-before-letters, punctuation)
    is a :class:`LarkConfigError`.
    """
    raw = text.strip()
    m = _ENDPOINT_RE.match(raw)
    if not raw or m is None:
        raise A1RangeError(_malformed_endpoint(text))
    letters, digits = m.group(1), m.group(2)
    if not letters and not digits:
        raise A1RangeError(_malformed_endpoint(text))
    try:
        col = a1_column_to_number(letters) if letters else None
    except ValueError as e:
        raise A1RangeError(_malformed_endpoint(text)) from e
    row = int(digits) if digits else None
    return col, row


def parse_write_range(text: str, *, grid_rows: int = None, grid_cols: int = None) -> WriteRange:
    """Parse an A1 write target into a **bounded** ``Start:End`` :class:`WriteRange`.

    * An optional ``{sid}!`` prefix is split off the **last** ``!`` and kept opaque
      (unicode / internal whitespace preserved verbatim); the body is parsed strictly.
    * A single cell (``B2``) **normalizes** to ``B2:B2``.
    * A fully-bounded range (``A1:C3``) parses as-is (order preserved — an inverted
      range is refused by :meth:`WriteRange.validate`, not silently reordered).
    * An **open** range (whole column ``A:A``, mixed ``A1:C``, whole row ``1:5``) is
      resolved against the supplied grid extent (``grid_rows`` / ``grid_cols``): an
      open **start** axis fills to ``1``, an open **end** axis to the grid bound.
      An open range with no grid extent is an unbounded target → :class:`LarkConfigError`.

    Does **not** run bounds/inversion validation — call :meth:`WriteRange.validate`.
    A malformed target (empty, missing body, ``A1:B2:C3``, junk) raises here.
    """
    if text is None:
        raise A1RangeError(
            f"write range must not be None — a write needs an A1 target to address. "
            f"{_A1_VALID_FORM}"
        )
    prefix, sep, body = text.strip().rpartition("!")
    sheet_id = prefix if sep else None
    body = body.strip()
    if not body:
        raise A1RangeError(
            f"empty A1 range body: {text!r} — the part after the '!' names the cells, and "
            f"there is nothing there, so no target can be addressed. {_A1_VALID_FORM}"
        )

    parts = body.split(":")
    if len(parts) == 1:
        start = end = A1Cell.parse(parts[0])
    elif len(parts) == 2:
        sc, sr = _parse_endpoint(parts[0])
        ec, er = _parse_endpoint(parts[1])
        start_col = sc if sc is not None else 1
        start_row = sr if sr is not None else 1
        end_col = ec if ec is not None else grid_cols
        end_row = er if er is not None else grid_rows
        if end_col is None or end_row is None:
            raise A1RangeError(
                f"unbounded A1 range {text!r}: an open (whole-column/row) target needs a grid "
                f"extent (grid_rows/grid_cols) to resolve, and none was supplied — so the "
                f"target has no last cell and nothing is read or written. Either bound the "
                f"range yourself or pass the tab's declared extent. {_A1_VALID_FORM}"
            )
        start, end = A1Cell(start_col, start_row), A1Cell(end_col, end_row)
    else:
        raise A1RangeError(
            f"malformed A1 range {text!r}: too many ':' separators — a range is exactly "
            f"Start:End (one colon), so this cannot be addressed. {_A1_VALID_FORM}"
        )

    return WriteRange(start, end, sheet_id=sheet_id)


def matrix_shape(values):
    """The ``(rows, cols)`` shape of a values matrix, or ``None`` when it is **not a
    rectangle**.

    A rectangle is a non-empty ``list`` of rows all of the same width, where a row that is not
    a ``list`` counts as width **1** (the convention the rest of the engine already reads a
    values matrix by — see :func:`~larkdocio.sheets.formula.equals_prefixed_cells`). ``None``
    for anything else: not a list at all, empty, or ragged.

    Pure arithmetic on the caller's own payload — this is what makes the arity refusal
    **pre-I/O**: a write's arity is knowable before any call is made.
    """
    if not isinstance(values, list) or not values:
        return None
    widths = {len(row) if isinstance(row, list) else 1 for row in values}
    if len(widths) != 1:
        return None
    return (len(values), widths.pop())


def describe_matrix_shape(values) -> str:
    """A human phrase for a values matrix's shape — ``"2 row(s) x 3 col(s)"`` for a rectangle,
    else WHY it is not one. Used verbatim in the ``shape-mismatch`` detail, so
    the refusal names both shapes in the same vocabulary."""
    shape = matrix_shape(values)
    if shape is not None:
        return f"{shape[0]} row(s) x {shape[1]} col(s)"
    if not isinstance(values, list):
        return f"not a values matrix at all (got {type(values).__name__} {values!r})"
    if not values:
        return "an EMPTY matrix (0 row(s)) — it addresses no cell"
    widths = sorted({len(row) if isinstance(row, list) else 1 for row in values})
    return (
        f"{len(values)} RAGGED row(s) of differing widths {widths} — a values matrix must be "
        f"rectangular"
    )


def write_range_from_used_range(used_range: UsedRange) -> WriteRange:
    """The write target that spans a discovered :class:`UsedRange` (L1 extent output).

    Parses ``used_range.a1_range`` (produced by
    :func:`~larkdocio.sheets.extent.used_range_a1`) into a bounded write target — so
    a write addresses **exactly** the discovered used range, reusing L1's extent
    rather than reforking. An **empty** used range (``a1_range is None``) has no
    write target → :class:`LarkConfigError`.
    """
    if used_range.a1_range is None:
        raise A1RangeError(
            f"used range for {used_range.sheet_id!r} is empty — no write target"
        )
    return parse_write_range(used_range.a1_range)
