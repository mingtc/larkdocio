"""larkdocio.sheets.extent — used-range discovery + in-memory trim.

The Sheets values API returns the **full declared grid** with trailing cells as
``null`` — a 200×20 sheet reads back 200×20, never trimmed server-side (spike Q2; the read is
``tests/captures/sheets-spike/captures/01-extent-Types.json``, range ``A1:T200``, in the source repository). So L1
finds the true used range itself, in two
disciplined steps that never over-read:

1. **The declared grid is the upper bound.** :func:`declared_grid_range` turns a
   tab's declared ``row_count`` × ``column_count`` (from the v3 tab-query metadata)
   into the single A1 range to request. It is exactly the grid's extent — **never a
   cell further** — so a read never probes past the declared grid (no iterative
   over-probe). :meth:`~larkdocio.sheets.client.SheetsReadClient.read_used_range`
   ties this to one bounded read.

2. **Trailing all-null trim, in memory.** :func:`trim_trailing_nulls` strips the
   trailing all-``null`` rows and columns the API padded on, returning the minimal
   bounding used range as a rectangular matrix. **Interior blanks are preserved** —
   an empty interior cell, and (critically) a merge-covered ``null`` inside the used
   region, both survive, because trimming only removes *trailing* all-null bands.
   This runs on the matrix **before** the merge join that assembles a table:
   collapsing an interior/merge-covered null here would corrupt that join.

A cell counts as empty for trimming iff it **is ``None``** — the API's pad marker.
An empty *string* is a value the API returned and is never trimmed.

Scope: the raw values matrix only — no cell→Markdown render, and no merge join /
table assembly. :class:`UsedRange` is the typed hand-off to the renderer.
"""
from dataclasses import dataclass

from larkdocio.sheets.models import SheetTab


def column_number_to_a1(n: int) -> str:
    """A 1-indexed column number → its A1 letters (``1``→``A``, ``26``→``Z``,
    ``27``→``AA``) — bijective base-26."""
    if n < 1:
        raise ValueError(f"column number must be >= 1, got {n}")
    letters = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


def a1_column_to_number(letters: str) -> int:
    """The inverse of :func:`column_number_to_a1` — A1 letters → 1-indexed column
    number (``A``→``1``, ``Z``→``26``, ``AA``→``27``).

    Case-insensitive; the round-trip ``a1_column_to_number(column_number_to_a1(n))
    == n`` holds for every ``n >= 1``. The A1 write model reuses this
    single column vocabulary rather than forking a parallel parser. A non-letter
    input (empty, digits, punctuation) is a :class:`ValueError`.
    """
    s = letters.upper()
    if not s or not s.isalpha() or not s.isascii():
        raise ValueError(f"not an A1 column: {letters!r}")
    n = 0
    for ch in s:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n


def declared_grid_range(sheet_id: str, row_count: int, column_count: int) -> str:
    """The A1 range covering a tab's **declared grid** — the used-range UPPER BOUND.

    ``declared_grid_range("444a1c", 200, 20)`` → ``"444a1c!A1:T200"``. This is the
    grid's exact extent, so a read of it never probes past the declared grid — no
    iterative over-probe.
    """
    if not row_count or not column_count:
        raise ValueError(
            f"tab {sheet_id!r} has no declared grid extent "
            f"(row_count={row_count!r}, column_count={column_count!r})"
        )
    return f"{sheet_id}!A1:{column_number_to_a1(column_count)}{row_count}"


def _is_empty(cell) -> bool:
    """A cell is empty for trimming iff it is the API's ``null`` pad (``None``).

    An empty string is a value the API returned deliberately — never trimmed.
    """
    return cell is None


def trim_trailing_nulls(values: list) -> list:
    """Trim trailing all-``None`` rows and columns to the minimal bounding matrix.

    Returns a new rectangular matrix (list of lists). **Interior nulls are
    preserved** — an empty interior cell, an interior all-null row, and a
    merge-covered null all survive, because only *trailing* all-null bands are
    removed. An all-null (or empty) input trims to ``[]``.
    """
    # Last row bearing any non-empty cell → drop every trailing all-null row.
    last_row = -1
    for i, row in enumerate(values):
        if any(not _is_empty(c) for c in row):
            last_row = i
    if last_row < 0:
        return []

    # Last column (across the kept rows) bearing any non-empty cell → drop every
    # trailing all-null column.
    last_col = -1
    for row in values[: last_row + 1]:
        for j, cell in enumerate(row):
            if not _is_empty(cell) and j > last_col:
                last_col = j

    width = last_col + 1
    # Rebuild rectangular at width — a row shorter than the used width is padded
    # with None so interior blanks are explicit and the matrix stays rectangular.
    return [
        [row[j] if j < len(row) else None for j in range(width)]
        for row in values[: last_row + 1]
    ]


def used_extent_along(values: list, axis: str) -> int:
    """How far the **used** data reaches along ``axis`` (``"COLUMNS"`` → the widest row bearing
    a value; ``"ROWS"`` → the last row bearing one), as a count.

    The measurement half of :func:`trim_trailing_nulls`, exposed on its own because a
    destructive **delete preview** must trim only the axis the delete does *not* consume —
    trimming both would drop the delete's own empty rows/columns and make the removed payload
    lie about the extent of the loss. Uses the same emptiness rule (``None`` is the API pad).
    """
    if axis == "ROWS":
        last = -1
        for i, row in enumerate(values):
            if any(not _is_empty(c) for c in row):
                last = i
        return last + 1
    last = -1
    for row in values:
        for j, cell in enumerate(row):
            if not _is_empty(cell) and j > last:
                last = j
    return last + 1


def trim_pad_along(values: list, axis: str) -> list:
    """``values`` with its trailing all-``None`` pad removed along ``axis`` **only** — the
    other axis is preserved in full.

    ``axis="COLUMNS"`` narrows every row to the used width (the values API pads a read to the
    tab's **declared** ``column_count``, so a 2-row read of a 20-column tab comes back 2×20);
    ``axis="ROWS"`` drops the trailing empty rows. **Interior and trailing blanks inside the
    used extent survive**, exactly as :func:`trim_trailing_nulls` preserves them.
    """
    used = used_extent_along(values, axis)
    if axis == "ROWS":
        return [list(row) for row in values[:used]]
    return [[row[j] if j < len(row) else None for j in range(used)] for row in values]


def used_range_a1(sheet_id: str, trimmed: list) -> str | None:
    """The A1 range of an already-trimmed matrix (``"444a1c!A1:D24"``), or ``None``
    for an empty matrix. ``trimmed`` is rectangular (a :func:`trim_trailing_nulls`
    result)."""
    if not trimmed:
        return None
    n_rows = len(trimmed)
    n_cols = max(len(row) for row in trimmed)
    return f"{sheet_id}!A1:{column_number_to_a1(n_cols)}{n_rows}"


@dataclass(frozen=True)
class UsedRange:
    """A tab's discovered used range: the trimmed values matrix + its A1 range.

    The typed hand-off from the extent scan to table assembly (which
    performs the merge join). ``values`` is the trailing-null-trimmed matrix (interior
    nulls intact);
    ``a1_range`` is its minimal bounding A1 range (``None`` when the tab is empty);
    ``revision`` carries through the source read's revision for determinism checks.
    """

    sheet_id: str
    a1_range: str | None
    revision: int | None
    values: list

    @classmethod
    def from_tab_values(cls, tab: SheetTab, values: list, revision=None) -> "UsedRange":
        """Trim a raw ``values`` matrix to ``tab``'s used range."""
        trimmed = trim_trailing_nulls(values)
        return cls(
            sheet_id=tab.sheet_id,
            a1_range=used_range_a1(tab.sheet_id, trimmed),
            revision=revision,
            values=trimmed,
        )
