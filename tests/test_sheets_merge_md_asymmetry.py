"""THE SHEETS-vs-DOCX MERGE ASYMMETRY, stated where a consumer will look
(LD-154 / dogfood F11's documentation half, AC5).

**The asymmetry.** A merged **docx table** survives the read: the reader emits an HTML
``<table>`` with real ``rowspan``/``colspan``, and the guide says so explicitly. A merged
**sheet range** does not: Markdown pipe tables have no span, so the anchor keeps its value
and every covered cell renders **blank** — **indistinguishable from a genuinely empty
cell**. The geometry itself lives in the v3 tab query's ``merges`` array, nowhere in the
Markdown. So a consumer who reads a sheet, edits the Markdown and writes it back **cannot
preserve the merge** from the Markdown alone, and until now nothing said so — while the docx
side was documented.

This is the **documentation half only**. The additive merge-disclosure render option is
**parked** with a recommendation (AC6): changing the default render would be an unconsented
output change, and the zero-drift goldens are the proof it has not happened here.

Both halves are guarded: the behaviour (a merged range really does render blank covered
cells, indistinguishable from empty) and the disclosure (SHEETS.md's row and the guide's
note actually say it).
"""
import re

import consumer_text
import guide_recipes as gr
from guard_kit import REPO_ROOT, md_table_cells

import larkdocio
from larkdocio.sheets.extent import UsedRange
from larkdocio.sheets.models import Merge, SheetTab
from larkdocio.sheets.table import render_matrix, render_spreadsheet

SHEETS_MD = REPO_ROOT / "SHEETS.md"


# --------------------------------------------------------------------------- #
# The BEHAVIOUR being disclosed — asserted, not taken on trust.                 #
# --------------------------------------------------------------------------- #

def test_a_merged_range_renders_blank_covered_cells():
    """A1:B1 merged: the anchor keeps its value, B1 renders ``""``."""
    values = [["Region", None], ["APAC", 12]]
    merges = (Merge(start_row=0, end_row=0, start_col=0, end_col=1),)
    assert render_matrix(values, merges) == [["Region", ""], ["APAC", "12"]]


def test_a_merged_covered_cell_is_INDISTINGUISHABLE_from_an_empty_one():
    """THE defect being documented, as an equality: two different spreadsheets — one with a
    merge, one with a genuinely empty B1 — render **byte-identical** Markdown.

    That is the whole reason the disclosure has to exist: no amount of reading the Markdown
    can recover which one you are holding.

    **The merged sheet's covered cell deliberately carries a value.** With a ``None`` there
    the two renders would match even if the merge join were switched off entirely, so the
    equality would be proving nothing about the join — a mutation probe that disabled the
    join left the weaker version of this test green. With a real value present, the equality
    holds **only because the join blanked it**, which is exactly the claim.
    """
    merged_tab = SheetTab(
        sheet_id="s1", title="Sheet1", index=0, row_count=2, column_count=2,
        merges=(Merge(start_row=0, end_row=0, start_col=0, end_col=1),),
    )
    empty_tab = SheetTab(sheet_id="s1", title="Sheet1", index=0, row_count=2,
                         column_count=2, merges=())

    # The merge-covered B1 still carries the value the merge visually swallowed…
    merged_values = UsedRange(sheet_id="s1", a1_range="s1!A1:B2", revision=1,
                              values=[["Region", "swallowed"], ["APAC", 12]])
    # …and this spreadsheet simply has nothing in B1.
    empty_values = UsedRange(sheet_id="s1", a1_range="s1!A1:B2", revision=1,
                             values=[["Region", None], ["APAC", 12]])

    merged_md = render_spreadsheet([(merged_tab, merged_values)])
    empty_md = render_spreadsheet([(empty_tab, empty_values)])

    assert merged_md == empty_md, "the renders differ, so a consumer COULD tell them apart"
    assert "| Region |  |" in merged_md
    assert "swallowed" not in merged_md


def test_the_merge_join_blanks_a_covered_cell_that_carries_a_value():
    """And it is the join, not the payload, that decides — so a stray non-null covered cell
    is blanked too. A consumer cannot recover the covered value from the Markdown either."""
    values = [["Region", "LEFTOVER"]]
    merges = (Merge(start_row=0, end_row=0, start_col=0, end_col=1),)
    assert render_matrix(values, merges) == [["Region", ""]]


def test_the_geometry_is_only_in_the_tab_query_not_in_the_markdown():
    """The other half of the claim: the Markdown carries no merge signal at all, so the
    round-trip cannot reconstruct one."""
    tab = SheetTab(
        sheet_id="s1", title="Sheet1", index=0, row_count=2, column_count=2,
        merges=(Merge(start_row=0, end_row=0, start_col=0, end_col=1),),
    )
    md = render_spreadsheet([(tab, UsedRange(sheet_id="s1", a1_range="s1!A1:B1", revision=1,
                                      values=[["Region", None]]))])
    for signal in ("colspan", "rowspan", "merge", "A1:B1"):
        assert signal not in md.lower(), f"the render leaks a {signal!r} signal: {md}"


# --------------------------------------------------------------------------- #
# AC5 — the DISCLOSURE: SHEETS.md's row.                                       #
# --------------------------------------------------------------------------- #

def _structural_row(feature_prefix):
    for line in SHEETS_MD.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"| {feature_prefix}"):
            return line
    return None


def test_sheets_md_has_the_merge_markdown_render_row():
    row = _structural_row("merge → Markdown render")
    assert row is not None, (
        "SHEETS.md has no row for how a merge RENDERS — the merges row documents the "
        "geometry and the write op, which is not the same fact"
    )
    flat = row.lower()
    for claim in ("indistinguishable", "blank", "anchor", "merges"):
        assert claim in flat, f"the merge-render row never says {claim!r}: {row}"
    assert "cannot preserve" in flat or "cannot be preserved" in flat, (
        "the row must state that read→edit→write-back cannot preserve a merge from the "
        f"Markdown alone: {row}"
    )
    assert "rowspan" in flat or "colspan" in flat, (
        f"the row must name the docx contrast a reader of this file will expect: {row}")


def test_the_merge_render_row_names_a_resolving_code_anchor():
    """The SHEETS.md drift guard enforces this for every row; asserting it here too means a
    typo in the new row is reported against THIS issue's test, not as a mysterious
    matrix-guard failure."""
    row = _structural_row("merge → Markdown render")
    cells = md_table_cells(row)
    anchor = cells[3].strip("`")
    module, _, symbol = anchor.rpartition(".")
    mod = __import__(module, fromlist=[symbol])
    assert hasattr(mod, symbol), f"the row's code anchor {anchor!r} does not resolve"


# --------------------------------------------------------------------------- #
# AC5 — the DISCLOSURE: the guide's contrast note.                             #
# --------------------------------------------------------------------------- #

def test_the_guide_contrasts_sheet_merges_with_docx_merges():
    flat = " ".join(larkdocio.guide(full=True).split())
    window = re.search(
        r"[^.]*merged[^.]*sheet[^.]*\.|[^.]*sheet[^.]*merge[^.]*\.", flat, re.IGNORECASE)
    assert window, "the guide never mentions a merged sheet range"

    for claim in ("indistinguishable", "rowspan", "colspan"):
        assert claim.lower() in flat.lower(), (
            f"the guide's merge note never says {claim!r} — the contrast with docx (which "
            f"the guide DOES document) is the point of the note"
        )
    assert "merges" in flat, "the guide must name where the geometry actually lives"


def test_the_guide_note_sits_with_the_sheet_read_recipe_not_three_sections_away():
    """Block-level placement, the same anti-rot rule the concurrency warning follows: the
    fact has to reach the person reading the sheet-read recipe."""
    preamble = gr.recipe_preamble("read-a-sheet-to-markdown")
    flat = " ".join(preamble.split()).lower()
    assert "indistinguishable" in flat, (
        "the sheet-read recipe's own preamble does not warn that a merge-covered cell is "
        f"indistinguishable from an empty one:\n{preamble}"
    )
    assert "rowspan" in flat or "colspan" in flat, (
        f"the docx contrast is missing from the recipe preamble:\n{preamble}")


def test_the_disclosure_is_dialect_free():
    """AC7: the new shipped strings pass the internal-dialect guard."""
    assert not consumer_text.dialect_hits(gr.recipe_preamble("read-a-sheet-to-markdown"))
