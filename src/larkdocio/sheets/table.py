"""larkdocio.sheets.table — table assembly + the merge join.

Turns a tab's trimmed (:mod:`larkdocio.sheets.extent`), rendered (
:mod:`larkdocio.sheets.render`) matrix into **one valid GitHub-flavored Markdown
table** — header row + separator + body — and, for a standalone read, emits **every
tab** as its own titled table.

**The merge join.** Markdown tables have no colspan/rowspan, so a merged region
renders its value in the **top-left anchor** and **blank** for every covered cell.
The geometry comes from the v3 tab-query ``merges`` array (:class:`~larkdocio.sheets.models.Merge`),
which is **0-indexed, END-inclusive** (spike Q3; ``{0,0,0,2}`` = A1:C1) — an off-by-one
would corrupt the table. A values read alone can't distinguish a merge-covered ``null``
from a genuinely empty cell, so the join is the **authority**: every covered cell is
blanked regardless of what the raw read returned (:func:`merge_covered_cells`).

**Reuse, don't fork.** Cells are rendered by the renderer's
:func:`~larkdocio.sheets.render.render_cell` (this layer arranges rendered cells — it does not re-render them), and the pipe/newline
cell escape (:func:`escape_cell`) is **byte-identical** to the docx table serializer's
(``strip`` → ``\\n`` → ``<br>`` → ``|`` → ``\\|``; :mod:`larkdocio.model.renderer`), so a
sheet table and a docx table escape a cell the same way.

**Heading.** A tab's heading text is its ``title``; an **embedded** sheet has no
standalone title (spike Q6), so the heading is synthesized from its ``sheet_id``
(``## Sheet <sheet_id>``). The heading level defaults to ``##`` (H2).

Scope: standalone assembly only. No docx/embedded integration,
no merge-as-colspan/rowspan (L2), no live gate (offline story). All offline.
"""
import re
from dataclasses import dataclass

from larkdocio.sheets.extent import a1_column_to_number, column_number_to_a1
from larkdocio.sheets.models import (
    FILTER_ACTIVE,
    FILTER_UNAVAILABLE,
    SheetTab,
)
from larkdocio.sheets.render import apply_cell_emphasis, render_cell

#: Emitted in place of a table for a tab whose used range is empty.
_EMPTY_MARKER = "_(empty sheet)_"

#: Default per-tab heading level (H2).
_DEFAULT_HEADING_LEVEL = 2

# --------------------------------------------------------------------------- #
# The filter disclosure. A values read cannot see a filter, so a filtered tab  #
# used to render its hidden rows as though a person could see them, with no    #
# signal of any kind. Which rows render is deliberately NOT changed here — the #
# note is added, the row set is not touched.                                   #
# --------------------------------------------------------------------------- #

#: A filter is active and hides rows. The rows are still rendered — saying so is the
#: whole point, since the alternative reading (that the table was filtered for you) is
#: exactly the misunderstanding the silence used to cause.
_FILTER_NOTE_HIDDEN = (
    "_(Filter active on this tab. Hidden from anyone viewing this spreadsheet: "
    "{rows_clause} ({count_clause}, numbered as the spreadsheet numbers them, where the "
    "first row is 1). The table below still includes them.)_"
)

#: A filter is active but matches everything, so nothing is hidden right now. Still
#: disclosed: a live filter can hide rows on the next read, and staying silent would leave
#: a filtered tab indistinguishable from an unfiltered one.
_FILTER_NOTE_NOTHING_HIDDEN = (
    "_(Filter active on this tab, and it currently hides no rows. The table below matches "
    "what someone viewing this spreadsheet sees.)_"
)

#: The filter read did not succeed, so whether rows are hidden is unknown. Disclosing the
#: gap is the point: the reader cannot vouch for the row set and says so, rather than
#: letting an unreadable filter look like an absent one.
_FILTER_NOTE_UNAVAILABLE = (
    "_(Filter state for this tab could not be read: {detail}. Whether any rows are hidden "
    "from someone viewing this spreadsheet is therefore unknown — the table below shows "
    "every row the values read returned.)_"
)


def filter_disclosure_note(tab: SheetTab) -> str | None:
    """The tab's filter disclosure line, or ``None`` when there is nothing to disclose.

    ``None`` covers the two states that carry no news: the tab has no filter, and no filter
    read was attempted (the default — so a tab read the way tabs have always been read
    renders **byte-identically** to before). The other two states each get their own note:
    a filter that hides rows names the count and the row numbers; a filter that could not be
    read says so and gives the reason.

    Row numbers are the **spreadsheet's own** (1-based, absolute), which the note states
    outright — bare integers beside a 0-indexed matrix are a trap.
    """
    if tab.filter_state == FILTER_UNAVAILABLE:
        return _FILTER_NOTE_UNAVAILABLE.format(
            detail=_clean_detail(tab.filter_state_detail)
        )
    if tab.filter_state != FILTER_ACTIVE:
        return None
    rows = tab.filtered_out_rows
    if not rows:
        return _FILTER_NOTE_NOTHING_HIDDEN
    if len(rows) == 1:
        rows_clause = f"spreadsheet row {rows[0]}"
        count_clause = "1 row"
    else:
        rows_clause = "spreadsheet rows " + ", ".join(str(r) for r in rows)
        count_clause = f"{len(rows)} rows"
    return _FILTER_NOTE_HIDDEN.format(rows_clause=rows_clause, count_clause=count_clause)


def _clean_detail(detail) -> str:
    """The reason text, kept safe to drop into a line beside a pipe table.

    A literal ``|`` would open a spurious column in some renderers and a newline would
    break the block, so both are normalized — the same hazard :func:`escape_cell` handles
    for cell text, applied to a reason string that comes from an exception message.
    """
    text = " ".join(str(detail or "no reason recorded").split())
    return text.replace("|", "/")


# --------------------------------------------------------------------------- #
# The fill disclosure (LD-331). The export-fidelity leg has always recovered a  #
# cell's fill ARGB, and the render dropped it without a word — so a sheet whose #
# meaning IS its colour (a gantt encoded in cell fills) read as labels with no  #
# bars. Markdown has no cell background, so the answer is the same one the      #
# merge join and the filter note give: state the fact beside the table rather   #
# than silently drop it. The note is added, the table is not touched.           #
# --------------------------------------------------------------------------- #

#: At least one cell carries a fill. The ARGB is reported **as the export carries it** and
#: is deliberately not interpreted — a colour's meaning is the reader's semantics, never a
#: conclusion this library draws.
_FILL_NOTE = (
    "_(Cell fills on this tab, recovered by the export-fidelity read: {fills_clause} "
    "({count_clause}). Markdown has no cell background, so each fill is reported as the "
    "ARGB the export carries, against the cells that carry it; what a colour means is not "
    "something this read concludes. The table below is unchanged.)_"
)

#: The fidelity leg ran but this tab's fills could not be recovered (its worksheet was
#: missing from the export, or the export itself failed). Disclosed because **unknown is
#: not none**: staying silent would make an unread fill layer look like an absent one,
#: which is exactly the silence this disclosure exists to end.
_FILL_NOTE_UNAVAILABLE = (
    "_(Cell fills for this tab could not be read: {detail}. Whether any cell carries a "
    "fill is therefore unknown — an unread fill is not the same as an absent one, and the "
    "table below shows only what the values read returned.)_"
)

#: ``_fidelity_for_tab``'s reason when a per-tab mapping was supplied (so the leg ran) but
#: carries no entry for this tab — e.g. ``exported_by_sheet_id`` omitted it because no
#: worksheet matched, which is a gap, not a finding of "no fills".
TAB_NOT_EXPORTED = "the fidelity read returned no export for this tab"

_A1_REF_RE = re.compile(r"^([A-Za-z]+)([0-9]+)$")


@dataclass(frozen=True)
class FidelityUnavailable:
    """A fidelity source standing in for **"the leg ran and this tab got nothing"**.

    It satisfies the same duck type the emphasis path uses — ``.cell(ref)`` answers
    ``None`` — so it can never add or alter a cell's rendering; its only effect is that
    :func:`fill_disclosure_note` reports the gap and :func:`cell_fills` answers ``None``
    (unknown) rather than ``{}`` (looked, and there are no fills). ``detail`` is the
    reason, rendered into the note.
    """

    detail: str = "no reason recorded"

    def cell(self, ref):
        """Always ``None`` — the sentinel discloses a gap, it never invents a style."""
        return None


def cell_fills(fidelity) -> dict | None:
    """``{a1_ref: ARGB}`` for every filled cell of a fidelity source — the **structured**
    half of the fill disclosure, and the function :func:`fill_disclosure_note` is built
    from, so the note and the programmatic answer cannot drift.

    **Three answers, deliberately distinct** (the sheets surface never launders an
    unknown):

    * a **non-empty dict** — these cells carry these fills;
    * ``{}`` — the export covered this tab and **no** cell carries a fill;
    * ``None`` — the fill layer was **not recovered**: no fidelity source at all
      (``None``), a :class:`FidelityUnavailable` sentinel, or a source that exposes only
      ``.cell(ref)`` and therefore cannot be enumerated. Unknown, not empty.

    A cell the export carried with no fill has ``fill_rgb is None`` and is simply absent
    from the dict — it is never coerced to white; a cell the export never carried at all is
    ``ExportedSheet.cell(ref) is None``, a different fact, and also absent. The two are
    told apart on the :class:`~larkdocio.sheets.export_reader.ExportedSheet` itself, which
    is why this returns refs rather than a per-cell verdict.
    """
    if fidelity is None or isinstance(fidelity, FidelityUnavailable):
        return None
    cells = getattr(fidelity, "cells", None)
    if not isinstance(cells, dict):
        return None
    return {
        ref: getattr(cell, "fill_rgb", None)
        for ref, cell in cells.items()
        if getattr(cell, "fill_rgb", None)
    }


def fill_disclosure_note(fidelity) -> str | None:
    """The tab's cell-fill disclosure line, or ``None`` when there is nothing to disclose.

    ``None`` covers the states that carry no news — **no fidelity source** (the flag-OFF
    path, which stays byte-identical to the values-only render), a source with **zero**
    filled cells (the leg looked and there is nothing), and a source that cannot be
    enumerated (silence, never a claim that there are no fills; :func:`cell_fills` answers
    ``None`` for it). The two states that DO carry news each get a note: filled cells are
    listed by colour, and a :class:`FidelityUnavailable` tab says so with its reason.

    Cells are grouped by ARGB and each row's **contiguous run** is compressed to one A1
    range (``FFFFFF00 — C2:E2, B7``), so a colour-encoded gantt costs about one range per
    bar rather than one ref per cell. Colours appear in first-cell order (top-left first),
    which makes the note deterministic for a given sheet.
    """
    if isinstance(fidelity, FidelityUnavailable):
        return _FILL_NOTE_UNAVAILABLE.format(detail=_clean_detail(fidelity.detail))
    fills = cell_fills(fidelity)
    if not fills:
        return None
    count = len(fills)
    return _FILL_NOTE.format(
        fills_clause=_fills_clause(fills),
        count_clause=f"{count} filled cell" if count == 1 else f"{count} filled cells",
    )


def _ref_position(ref):
    """``(row, col)`` (both 1-indexed) for an A1 ``ref``, or ``None`` when it is not a
    plain A1 cell reference — an unparseable ref is reported verbatim rather than dropped."""
    m = _A1_REF_RE.match(ref or "")
    if m is None:
        return None
    return int(m.group(2)), a1_column_to_number(m.group(1).upper())


def _fills_clause(fills: dict) -> str:
    """``"FFFFFF00 — C2:E2, B7; FF00B050 — C3"`` from ``{ref: ARGB}``."""
    by_colour = {}
    for ref in sorted(fills, key=lambda r: (_ref_position(r) or (10**9, 10**9), r)):
        by_colour.setdefault(fills[ref], []).append(ref)
    return "; ".join(
        f"{argb} — {', '.join(_compress_row_runs(refs))}"
        for argb, refs in by_colour.items()
    )


def _compress_row_runs(refs) -> list:
    """Consecutive columns in the same row → one A1 range (``C2:E2``); a lone cell stays a
    lone ref. ``refs`` arrives sorted by (row, col). A ref that is not a plain A1 cell
    reference is passed through untouched — the disclosure never silently loses a cell."""
    runs, passthrough = [], []
    for ref in refs:
        pos = _ref_position(ref)
        if pos is None:
            passthrough.append(ref)
            continue
        row, col = pos
        if runs and runs[-1][0] == row and runs[-1][2] == col - 1:
            runs[-1][2] = col
        else:
            runs.append([row, col, col])
    out = [
        f"{column_number_to_a1(first)}{row}" if first == last
        else f"{column_number_to_a1(first)}{row}:{column_number_to_a1(last)}{row}"
        for row, first, last in runs
    ]
    return out + passthrough


def merge_covered_cells(merges) -> set:
    """The set of ``(row, col)`` cells **covered** by a merge — its anchor excluded.

    Each :class:`~larkdocio.sheets.models.Merge` is **0-indexed, END-inclusive**
    (spike Q3): ``Merge(0, 0, 0, 2)`` (A1:C1) covers exactly ``{(0, 1), (0, 2)}`` —
    the top-left anchor ``(0, 0)`` keeps its value and is never in the returned set.
    A boundary merge like A3:A5 (``Merge(2, 4, 0, 0)``) covers exactly ``{(3, 0),
    (4, 0)}``; an end-exclusive off-by-one would drop A5, so the join would corrupt.
    """
    covered = set()
    for m in merges or ():
        for r in range(m.start_row, m.end_row + 1):
            for c in range(m.start_col, m.end_col + 1):
                if r == m.start_row and c == m.start_col:
                    continue  # the anchor keeps its value
                covered.add((r, c))
    return covered


def escape_cell(text: str) -> str:
    """Normalize one rendered cell so it stays valid inside a GFM pipe table.

    Byte-identical to the docx table serializer (deliberate reuse): strip outer whitespace,
    join internal newlines with ``<br>`` (a literal newline would break the row), and
    escape a literal ``|`` as ``\\|`` (an unescaped pipe would open a spurious column).
    """
    return text.strip().replace("\n", "<br>").replace("|", "\\|")


def render_matrix(values, merges=(), *, mention_names=None, renderer=None, fidelity=None) -> list:
    """Render + merge-join a raw values matrix into a table-ready string matrix.

    Each raw cell is rendered by :func:`~larkdocio.sheets.render.render_cell`
    (arranged, not re-rendered), then merge-**covered** cells are blanked (the
    join is the authority — a stray non-null covered cell is blanked anyway) and every
    surviving cell is escaped for GFM (:func:`escape_cell`). Returns a list of lists of
    strings, same shape as ``values``.

    **Opt-in whole-cell (format-level) emphasis.** ``fidelity`` is an
    :class:`~larkdocio.sheets.export_reader.ExportedSheet` (or any object exposing
    ``.cell(a1_ref)`` → an object with ``.bold`` / ``.italic``) supplying the
    **whole-cell (format-level)** bold/italic — the emphasis set on the CELL, which the
    values API does not carry. When supplied, each surviving cell's rendered text is wrapped
    in emphasis (:func:`~larkdocio.sheets.render.apply_cell_emphasis`)
    **before** the GFM escape, so a bold cell renders ``**text**``. ``fidelity=None``
    (the default) is **byte-identical** to the values-only render — the flag-OFF
    invariant. A merge-covered cell stays blank regardless (the join is the authority),
    and the emphasis reuses the shared serializer (no fork; ``renderer`` config threads
    through).

    **Run-level emphasis is a different thing and needs none of this.** Bold/italic on a
    text **run** inside a cell travels in the values API's own ``segmentStyle`` and is
    already rendered by :func:`~larkdocio.sheets.render.render_cell`. So on a sheet whose
    emphasis is run-level, passing ``fidelity`` **correctly changes nothing** — the output
    is byte-identical because there was nothing to add, not because nothing was read. The
    two are **layered**: ``fidelity`` only ever ADDS to the values render, so it can never
    drop a run's own emphasis."""
    covered = merge_covered_cells(merges)
    out = []
    for i, row in enumerate(values):
        rendered_row = []
        for j, cell in enumerate(row):
            if (i, j) in covered:
                rendered_row.append("")
            else:
                text = render_cell(cell, mention_names=mention_names, renderer=renderer)
                text = _apply_fidelity(text, i, j, fidelity, renderer)
                rendered_row.append(escape_cell(text))
        out.append(rendered_row)
    return out


def _apply_fidelity(text, row, col, fidelity, renderer):
    """Wrap ``text`` in export-derived **whole-cell (format-level)** emphasis when a
    ``fidelity`` source marks the cell at 0-indexed ``(row, col)`` bold/italic; a
    no-fidelity / unlisted / unstyled cell is returned unchanged (the flag-OFF invariant).
    The cell's A1 ref is ``column(col + 1) + str(row + 1)`` (used ranges start at A1).

    Note what this deliberately does NOT do: it never inspects or overrides the emphasis
    ``render_cell`` already produced from the values API's run styles. It wraps whatever it
    was handed. That layering is the reason turning the leg on cannot lose emphasis.
    """
    if fidelity is None:
        return text
    ref = f"{column_number_to_a1(col + 1)}{row + 1}"
    cell = fidelity.cell(ref)
    if cell is None:
        return text
    return apply_cell_emphasis(
        text, bold=bool(cell.bold), italic=bool(cell.italic), renderer=renderer
    )


def matrix_to_gfm_table(rendered_rows) -> str:
    """A rectangular matrix of **already-rendered, already-escaped** cell strings →
    one GFM table (header row + separator + body). The first row is the header.

    Ragged rows are padded to the widest row so the table stays rectangular. An empty
    matrix yields ``""``. No trailing newline — the caller joins tabs.
    """
    if not rendered_rows:
        return ""
    width = max(len(r) for r in rendered_rows)
    padded = [list(r) + [""] * (width - len(r)) for r in rendered_rows]

    lines = ["| " + " | ".join(padded[0]) + " |"]        # header (first row)
    lines.append("|" + "|".join(["---"] * width) + "|")  # separator
    for row in padded[1:]:                               # body
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def tab_heading(tab: SheetTab, level: int = _DEFAULT_HEADING_LEVEL) -> str:
    """The Markdown heading line for a tab.

    Heading text is the tab's ``title``; an **embedded** sheet has no standalone title
    (spike Q6), so an empty/absent title is synthesized as ``Sheet <sheet_id>``.
    """
    text = tab.title or f"Sheet {tab.sheet_id}"
    return f"{'#' * level} {text}"


def render_tab(
    tab: SheetTab,
    used_range,
    *,
    mention_names=None,
    renderer=None,
    heading_level: int = _DEFAULT_HEADING_LEVEL,
    fidelity=None,
) -> str:
    """One tab → a titled GFM table: its heading + the merge-joined table.

    ``used_range`` is the tab's :class:`~larkdocio.sheets.extent.UsedRange` (the
    trimmed values); ``tab`` carries the ``merges`` geometry and the heading title. An
    empty used range emits the heading + an ``_(empty sheet)_`` marker (no table).

    ``fidelity`` is the opt-in export-derived **whole-cell (format-level)** emphasis
    source, threaded to :func:`render_matrix`; ``None`` (default) → the values-only,
    byte-identical render. Run-level emphasis needs no ``fidelity``: it arrives over the
    values API and is already rendered either way.

    If ``tab`` carries filter knowledge, the **filter disclosure**
    (:func:`filter_disclosure_note`) is emitted between the heading and the table — before
    the data it qualifies, not after it. **Which rows render is unchanged**: the disclosure
    is additive, and a tab with no filter knowledge (the default) renders byte-identically
    to before.

    If ``fidelity`` reports **cell fills** (or reports that it could not read them), the
    **fill disclosure** (:func:`fill_disclosure_note`) follows the filter note, for the same
    reason and in the same idiom: Markdown has no cell background, so a sheet whose meaning
    is its colour would otherwise render as labels with the bars silently gone. The filter
    note comes first because it qualifies the **row set**; the fill note qualifies the
    **cells**. With ``fidelity=None`` (the default) neither this nor the emphasis exists and
    the render is byte-identical to the values-only one.
    """
    heading = tab_heading(tab, heading_level)
    rendered = render_matrix(
        used_range.values, tab.merges,
        mention_names=mention_names, renderer=renderer, fidelity=fidelity,
    )
    table = matrix_to_gfm_table(rendered)
    body = table if table else _EMPTY_MARKER
    parts = [heading]
    for note in (filter_disclosure_note(tab), fill_disclosure_note(fidelity)):
        if note:
            parts.append(note)
    parts.append(body)
    return "\n\n".join(parts)


def render_spreadsheet(
    tabs,
    *,
    mention_names=None,
    renderer=None,
    heading_level: int = _DEFAULT_HEADING_LEVEL,
    fidelity=None,
    skips=(),
) -> str:
    """A standalone spreadsheet render: **every** tab as its own titled table.

    ``tabs`` is an iterable of ``(SheetTab, UsedRange)`` pairs **in sheet order**; each
    becomes a heading + table (:func:`render_tab`), joined by a blank line.

    ``fidelity`` is the opt-in export-derived **whole-cell (format-level)** emphasis
    source: a mapping ``{sheet_id: ExportedSheet}`` (the per-tab export lookup) or a single
    ExportedSheet applied to every tab, or ``None`` (default) for the values-only render.
    Run-level emphasis (a styled run inside a cell) comes through the values API and renders
    with or without it, so a spreadsheet styled that way renders identically both ways.

    ``skips`` are the tabs that **could not be read** — the ``skips`` of a
    :class:`~larkdocio.sheets.walk.SpreadsheetRead` (or bare
    :class:`~larkdocio.sheets.walk.TabSkip` objects). Given any, the render **opens with a
    disclosure** naming each missing tab and quoting Lark's own code and message, because a
    partial workbook that renders as a short document with nothing said is the silent failure
    this refuses. Empty (the default) it adds **nothing at all** — a full read's
    Markdown is byte-identical to what it always was.
    """
    sections = [
        render_tab(
            tab,
            used_range,
            mention_names=mention_names,
            renderer=renderer,
            heading_level=heading_level,
            fidelity=_fidelity_for_tab(fidelity, tab),
        )
        for tab, used_range in tabs
    ]
    disclosure = skipped_tabs_disclosure(skips, read_count=len(sections))
    if disclosure:
        sections.insert(0, disclosure)
    return "\n\n".join(sections)


def skipped_tabs_disclosure(skips, *, read_count: int) -> str:
    """The **loud** note a partial workbook render opens with — or ``""`` when nothing was
    skipped.

    Says the count first (*"N of M tabs could not be read"*), then one line per missing tab
    carrying **Lark's own code and message, verbatim**. It diagnoses nothing: what makes a tab
    unreadable while the same API enumerates it is unmeasured, and a note that guessed would
    be worse than one that quotes. A blockquote so it cannot be mistaken for content.

    Accepts either :class:`~larkdocio.sheets.walk.TabOutcome` objects (what
    ``SpreadsheetRead.skips`` holds) or bare :class:`~larkdocio.sheets.walk.TabSkip` objects,
    so a caller never has to unwrap one shape into the other.
    """
    entries = [getattr(s, "skip", None) or s for s in (skips or ())]
    if not entries:
        return ""
    total = read_count + len(entries)
    lines = [
        f"> **{len(entries)} of {total} tabs could not be read — this document is "
        f"INCOMPLETE.** Lark refused them; larkdocio quotes its answer and diagnoses no "
        f"further.",
        ">",
    ]
    lines += [f"> - `{e.sheet_id}` ({e.title}) — Lark answered code {e.code}: {e.msg}"
              for e in entries]
    return "\n".join(lines)


def _fidelity_for_tab(fidelity, tab: SheetTab):
    """Resolve the per-tab fidelity source: a ``{sheet_id: ExportedSheet}`` mapping is
    indexed by the tab's ``sheet_id``; anything else (a single ExportedSheet, or ``None``)
    is passed through unchanged.

    A tab **missing** from the mapping resolves to a :class:`FidelityUnavailable` sentinel
    rather than to ``None``. Both render the tab's cells values-only — the sentinel adds no
    emphasis — but they are different facts and are now said differently: ``None`` means the
    leg was never turned on, while a mapping that has no entry for this tab means the leg
    RAN and this tab got nothing (``exported_by_sheet_id`` omits a tab whose worksheet it
    could not match, deliberately, rather than borrowing a neighbour's styles). Reporting
    that as "no fills" would be exactly the laundering of an unknown the sheets surface
    refuses everywhere else."""
    if isinstance(fidelity, dict):
        exported = fidelity.get(tab.sheet_id)
        return exported if exported is not None else FidelityUnavailable(TAB_NOT_EXPORTED)
    return fidelity
