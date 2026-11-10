"""Shared mechanics for the doc-reading guards — the matrix-guard seam (LD-242).

Three concepts, one definition each:

* :data:`REPO_ROOT`  — the repo root, derived once instead of in every guard.
* :func:`section`    — a **fence-aware** slice of a Markdown document by heading.
* :func:`md_table_rows` — every Markdown table row of a document, fence-aware, as trimmed
  cells; built on :func:`md_table_cells`, the one-row primitive most guards actually want.
* :func:`md_tables` / :func:`md_ragged_rows` — the **header-keyed** accessor (LD-632): every
  table as ``(headers, [row-dict])``, plus the rows it could not key. The header-keyed parse
  had grown three near-copies, one of which split rows naively and so dropped
  ``BASE.md``'s own escaped-pipe row without a sound.

Nothing here knows anything about larkdocio. It is *text mechanics*, lifted from the best
existing implementation rather than newly invented:

* :func:`md_table_cells` began as ``test_sheets_md_matrix.py::_split_row`` — the only
  splitter in the repo that honoured a ``\\|`` escape (`` `a \\| b` `` is one cell, not two).
  LD-242 lifted it here **by copy**, leaving the original in place; LD-632 finished the move,
  so ``_split_row`` is now an alias of this function and there is one definition.
* :func:`section` is ``test_doctrine_and_recipes.py::_section`` /
  ``test_levels_delineation.py::_section`` — fence-aware because a ``# ``-prefixed *comment*
  inside a fenced sample looks exactly like an H1 to a line-anchored regex, which cuts the
  section at its first code sample and makes every content guard over it silently vacuous
  (the LD-132 failure mode, in the guard itself).

**How the next matrix guard enrols — by import, not by copy** (LD-242 AC7). ``BLOCKS.md``,
``SHEETS.md`` and ``PERMISSIONS.md`` each grew their own copy of this mechanic; the fourth
living matrix (``BASE.md``, required by the Base study § 6 inside the Base read spec's own tranche) does
not have to. A ``tests/test_base_md_matrix.py`` uses the three exports in this order::

    from guard_kit import REPO_ROOT, md_table_rows, section

    BASE_MD = REPO_ROOT / "BASE.md"                       # 1. the document
    region = section(BASE_MD.read_text(encoding="utf-8"),  # 2. the matrix's own section,
                     "## Field-type matrix")               #    fences and all
    rows = md_table_rows(region)                           # 3. its rows, separator dropped

and then asserts its own registry against ``rows`` — the *only* part that is Base-specific.
Reach for :func:`md_table_cells` directly when the guard already has the one row in hand.

**Deliberately NOT here** (both standing carve-outs from the 2026-08-01 audit, re-affirmed
by LD-242 AC5): ``test_discovery_truth.py``'s slicer is the repo's only non-fence-aware one —
migrating it *widens* what the guard catches, which is a behavior question, not a migration —
and ``front_door.section_of_line`` / ``test_front_door_doctrine.py`` are documented as
deliberately fence-blind.
"""

import pathlib
import re

#: The repository root — the parent of ``tests/``. **The derivation a guard IMPORTS**, so a
#: matrix guard that reaches for a shipped document does not re-answer "where am I?" in its own
#: prologue. It is a ROLE, not a census: this is emphatically **not** the only spelling of
#: ``Path(__file__).resolve().parent.parent`` in the tree — that one-liner is correct, costs
#: nothing to repeat, and LD-628 explicitly declined migrating the modules that spell it out.
#: (It used to say "the one derivation", which a reader who checked it found false — and the
#: rest of this module's enrolment instruction is load-bearing, so it cannot afford that. No
#: number is written here on purpose: any count of the copies would be stale within days —
#: LD-628 measured the figure its own AC quoted as already drifted one day later.
#: `process/doctrine/staleness.md` § C.)
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: A Markdown table's separator row: ``|---|:--:|---|``.
SEPARATOR_RE = re.compile(r"^\|[\s:\-|]+\|$")

#: An opening/closing code fence, indented or not.
_FENCE_RE = re.compile(r"^\s*```")


def is_separator_row(line: str) -> bool:
    """True for a table's ``|---|---|`` separator row — syntax, never data."""
    return bool(SEPARATOR_RE.match(line.strip()))


def md_table_cells(line: str) -> list:
    """Split ONE Markdown table row ``| a | b | c |`` into its trimmed cells.

    Honours ``\\|`` escapes (an escaped pipe is cell *content*, not a boundary) and does
    **not** unescape them: the cell text stays exactly what the document says, so a guard
    comparing against the document keeps comparing against the document.

    A ragged row is returned as its own cells — not padded, not dropped, not an error; what
    a short row means is the caller's question.
    """
    inner = line.strip()
    inner = inner[1:] if inner.startswith("|") else inner
    inner = inner[:-1] if inner.endswith("|") else inner
    cells, buf, i = [], [], 0
    while i < len(inner):
        ch = inner[i]
        if ch == "\\" and i + 1 < len(inner):
            buf.append(inner[i : i + 2])
            i += 2
            continue
        if ch == "|":
            cells.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    cells.append("".join(buf).strip())
    return cells


def md_table_rows(text: str) -> list:
    """Every Markdown table row in ``text`` as a list of trimmed cells.

    Fence-aware: a table *shown inside* a fenced code block is a code sample, not data, and
    is never returned. Separator rows are dropped. A line counts as a row when it both opens
    and closes with ``|`` — the convention every table guard in this repo already used.
    """
    rows, fenced = [], False
    for line in text.splitlines():
        if _FENCE_RE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        if is_separator_row(stripped):
            continue
        rows.append(md_table_cells(stripped))
    return rows


def _table_runs(text: str):
    """Yield ``(header_cells, [row_cells, ...])`` for every pipe-table run in ``text``.

    Fence-aware, on the same reasoning as :func:`md_table_rows`: a table shown inside a fenced
    block is a code sample, not data. The first row of a run is its header; a separator row is
    syntax; any line that does not both open and close with ``|`` ends the run.
    """
    header, rows, fenced = None, [], False
    for line in text.splitlines():
        if _FENCE_RE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            if is_separator_row(stripped):
                continue
            cells = md_table_cells(stripped)
            if header is None:
                header, rows = cells, []
            else:
                rows.append(cells)
            continue
        if header is not None:
            yield header, rows
            header, rows = None, []
    if header is not None:
        yield header, rows


def md_tables(text: str) -> list:
    r"""Every Markdown table in ``text`` as ``(headers, [row-dict, ...])``.

    The header-keyed accessor — the shape a matrix guard actually asks for — built on
    :func:`md_table_cells`, so **an escaped pipe is cell content and never a row boundary**.
    That is the whole reason this lives here (LD-632): the parse it replaces split rows with a
    naive ``strip("|").split("|")``, so a row carrying a literal ``\|`` yielded one cell too
    many and was **silently dropped** by the header-length check — and the guard iterating
    those rows went quietly vacuous for the dropped one. One escape-honouring definition, not
    a fourth near-copy.

    A **ragged** row — one whose cell count does not match its table's header count — is still
    not returned, because there is no honest way to key it. It is no longer silent either:
    :func:`md_ragged_rows` reports exactly what was left out, so a guard can assert its own
    document has none and hear about it the day that stops being true.
    """
    return [
        (header, [dict(zip(header, cells)) for cells in rows if len(cells) == len(header)])
        for header, rows in _table_runs(text)
    ]


def md_ragged_rows(text: str) -> list:
    """Every row :func:`md_tables` could not key, as ``(headers, cells)``.

    The companion that keeps :func:`md_tables`'s one omission loud. A document whose guard
    asserts this is empty cannot lose a row to a parse quirk without saying so — which is the
    LD-632 defect, stated as a test instead of a hope.
    """
    return [
        (header, cells)
        for header, rows in _table_runs(text)
        for cells in rows
        if len(cells) != len(header)
    ]


def section(text: str, heading: str) -> str:
    """``text`` from ``heading`` up to the next heading of the same-or-higher level.

    **Fence-aware on purpose**: lines inside a ``` fence are never read as headings, so a
    ``# comment`` in a code sample cannot truncate the section. The returned string starts
    with ``heading`` itself. A missing heading is a loud :class:`AssertionError`, never a
    silently empty section.
    """
    level = len(heading) - len(heading.lstrip("#"))
    start = text.find(heading)
    assert start != -1, f"the document has no {heading!r} section"
    body = text[start + len(heading) :]
    out, fenced = [], False
    for line in body.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced and re.match(rf"#{{1,{level}}} ", line):
            break
        out.append(line)
    return heading + "".join(out)
