"""Verify a sheet write — compare **values**, not their string forms (LD-190, dogfood F19).

The sheets parity of the docx side's compose-equivalence recipe, and it exists for the same
reason: the obvious self-check — write, read back, compare — reports a difference nobody made.

**The trap, measured live.** Every **whole-valued float** you write comes back as an ``int``:
``18.0`` → ``18``, ``0.0`` → ``0``, ``-3.0`` → ``-3``, ``1e6`` → ``1000000``, and ``2.5 * 4``
→ ``10``. A non-whole float is untouched (``22.5`` → ``22.5``, artefacts and all), a string stays
a string (``"18.0"`` → ``"18.0"``), and an empty cell comes back as ``None`` — or, if it trails a
row, does not come back at all. So a comparison of **string forms** — ``str()``, ``json.dumps``,
the rendered Markdown, a diff of two text dumps — reports a change on every whole-valued number
in the sheet, while the numbers themselves are exactly equal.

**The fix is a typed comparison, not a tolerance.** The normalization above changes the *type* of
a value and never its magnitude, so nothing here needs a fuzz factor — and a tolerance would be
worse than useless: it would launder a real ``18.0`` → ``18.01`` drift, which is precisely what
verification exists to catch. :func:`values_equivalent` therefore compares numbers **numerically
across int/float**, treats an empty cell and an absent trailing cell as the same emptiness, and
keeps every other difference visible: a text ``"18.0"`` is **not** the number ``18``, and a
``bool`` is **not** ``1``.

Nothing in here reads, writes or resolves a credential — it is pure comparison over two values
matrices you already hold.
"""
from typing import Iterable, List, Sequence

from larkdocio.sheets.write_range import A1Cell, parse_write_range

#: **The trap and the fix, stated once, loudly** — quoted verbatim by ``GUIDE.md`` and by
#: ``SHEETS.md`` (in the source repository, not in the wheel), so the three cannot drift. Every number
#: in it was measured on a disposable, not read off a doc page.
NUMERIC_READ_BACK_NORMALIZED = (
    "A SHEET'S NUMERIC READ-BACK IS NORMALIZED, so verifying a write by comparing STRING FORMS "
    "reports a phantom difference. Measured live: every whole-valued float comes back as an int "
    "— 18.0 reads back as 18, 0.0 as 0, -3.0 as -3, 1e6 as 1000000, and 2.5*4 as 10 — while a "
    "non-whole float is returned untouched (22.5 stays 22.5) and a string stays a string ('18.0' "
    "stays the text '18.0'). An empty cell reads back as null, and a trailing empty cell may not "
    "be returned at all. So str(written) == str(read_back), json.dumps of the two matrices, and "
    "a diff of two rendered Markdown tables all report a change on every whole number in the "
    "sheet, and none of those changes happened. Compare values, not their string forms: "
    "larkdocio.sheets.values_equivalent(written, read_back) compares numbers numerically across "
    "int/float, treats an empty cell and an absent trailing cell as the same emptiness, and "
    "keeps every REAL difference visible — a text '18.0' is not the number 18, a bool is not 1, "
    "and 18.01 is not 18. It is a typed comparison and NOT a tolerance, deliberately: the "
    "normalization changes a value's type and never its magnitude, so a fuzz factor would buy "
    "nothing and would hide the 18.0-to-18.01 drift you are checking for. "
    "larkdocio.sheets.value_differences(written, read_back, origin='A1') returns the same "
    "answer cell by cell, each difference carrying its A1 ref. Evidence: "
    "tests/captures/sheets-merge-variant-probe/captures/02-numeric-read-back.json in the source repository."
)


def _is_empty(value) -> bool:
    """An empty cell. ``None`` (how the API reports one) and ``""`` (how a caller writes one)
    are the same emptiness — the read-back never distinguishes them."""
    return value is None or value == ""


def _numbers_equal(a, b) -> bool:
    """Numeric equality **across int/float**, with ``bool`` excluded on purpose: ``True == 1``
    in Python, and a checkbox that reads back as the number 1 is a real difference a consumer
    must see, not a normalization to swallow."""
    if isinstance(a, bool) or isinstance(b, bool):
        return False
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return False
    return float(a) == float(b)


def cells_equivalent(written, read_back) -> bool:
    """One cell: is ``read_back`` the same value as ``written``, allowing only the read-back's
    own normalizations (whole float → int, empty → null)?"""
    if _is_empty(written) and _is_empty(read_back):
        return True
    if _numbers_equal(written, read_back):
        return True
    return type(written) is type(read_back) and written == read_back


def _row(matrix: Sequence, index: int) -> Sequence:
    row = matrix[index] if index < len(matrix) else []
    return row if isinstance(row, (list, tuple)) else [row]


def _cell(row: Sequence, index: int):
    return row[index] if index < len(row) else None


def values_equivalent(written: Iterable, read_back: Iterable) -> bool:
    """Are two values matrices the same content, read-back normalizations aside?

    ``written`` / ``read_back`` are the row-major matrices the write and the read use
    (``[[…], [… ]]``). A row (or a trailing cell) missing from either side counts as **empty**,
    because a read never returns trailing blanks — so a matrix and the same matrix with its empty
    tail trimmed are equivalent, while a matrix missing a cell that carries a value is **not**.
    """
    return not value_differences(written, read_back)


def value_differences(written: Iterable, read_back: Iterable, *,
                      origin: str = "A1") -> List[dict]:
    """Every **real** difference between two values matrices, each carrying its A1 ``ref``.

    ``origin`` is the A1 cell (optionally ``sheet!``-prefixed) the two matrices' top-left
    corner sits at, so the refs are the sheet's own and not matrix indices. The result is a
    list of ``{"ref", "written", "read_back"}`` dicts in row-major order — empty exactly when
    :func:`values_equivalent` is ``True``.
    """
    top_left = _origin_cell(origin)
    left = list(written or [])
    right = list(read_back or [])
    diffs: List[dict] = []
    for r in range(max(len(left), len(right))):
        lrow, rrow = _row(left, r), _row(right, r)
        for c in range(max(len(lrow), len(rrow))):
            a, b = _cell(lrow, c), _cell(rrow, c)
            if cells_equivalent(a, b):
                continue
            diffs.append({
                "ref": A1Cell(top_left.col + c, top_left.row + r).a1(),
                "written": a,
                "read_back": b,
            })
    return diffs


def _origin_cell(origin: str) -> A1Cell:
    """``"A1"`` / ``"Sheet!B2"`` / ``"154e99!B2:D9"`` → the top-left :class:`A1Cell`."""
    text = origin.split("!", 1)[-1]
    if ":" in text:
        return parse_write_range(origin).start
    col, row = _split_ref(text)
    return A1Cell(col, row)


def _split_ref(ref: str) -> tuple:
    from larkdocio.sheets.extent import a1_column_to_number

    letters = "".join(ch for ch in ref if ch.isalpha())
    digits = "".join(ch for ch in ref if ch.isdigit())
    if not letters or not digits:
        raise ValueError(
            f"value_differences: origin must be an A1 cell or range (e.g. 'A1', "
            f"'154e99!B2'), got {ref!r}")
    return a1_column_to_number(letters.upper()), int(digits)
