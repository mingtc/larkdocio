"""Offline unit tests for table assembly + the merge join (LD-104).

Assembles the trimmed (S2, LD-102), rendered (S3, LD-103) matrix into a valid
GitHub-flavored Markdown table per tab, **joined with the v3 tab-query ``merges``
metadata**. The merge convention is D5: a merged region shows its value only in the
**top-left anchor** and **blank** for every covered cell. The ``merges`` objects are
**0-indexed, END-inclusive** (spike Q3; ``{0,0,0,2}`` = A1:C1), so an off-by-one
would corrupt the table — the boundary tests below make one fail.

Fixtures are the LD-100 opener spike's **committed captures**
(``tests/captures/sheets-spike/captures/``): ``00-scratch-tabs.json`` carries the tab metadata
+ the ``merges`` array; ``01-extent-{Types,Merged}.json`` are the raw 200×20 reads.
All offline (no network) — AC5's live gate is N/A (offline story).
"""
import json
import re
from pathlib import Path

from larkdocio.sheets.models import Merge, SheetTab
from larkdocio.sheets.extent import UsedRange
from larkdocio.sheets.export_reader import ExportedCell, ExportedSheet
from larkdocio.sheets.table import (
    escape_cell,
    matrix_to_gfm_table,
    merge_covered_cells,
    render_matrix,
    render_spreadsheet,
    render_tab,
    tab_heading,
)

_CAPTURES = Path(__file__).resolve().parent.parent / "tests" / "captures" / "sheets-spike" / "captures"


def _capture(name):
    return json.loads((_CAPTURES / name).read_text(encoding="utf-8"))


def _tab(title):
    for s in _capture("00-scratch-tabs.json")["data"]["sheets"]:
        if s["title"] == title:
            return SheetTab.from_dict(s)
    raise AssertionError(f"no tab titled {title!r} in 00-scratch-tabs.json")


def _used_range(tab, extent_name):
    vals = _capture(extent_name)["data"]["valueRange"]["values"]
    return UsedRange.from_tab_values(tab, vals)


# --------------------------------------------------------------------------- #
# AC1 — a valid GFM table per tab (header row + separator + body)              #
# --------------------------------------------------------------------------- #

def test_matrix_to_gfm_table_small_matrix():
    rendered = [["A", "B", "C"], ["1", "2", "3"], ["x", "", "z"]]
    assert matrix_to_gfm_table(rendered) == (
        "| A | B | C |\n"
        "|---|---|---|\n"
        "| 1 | 2 | 3 |\n"
        "| x |  | z |"
    )


def test_gfm_table_shape_is_header_separator_body():
    lines = matrix_to_gfm_table([["h1", "h2"], ["a", "b"], ["c", "d"]]).split("\n")
    assert lines[0] == "| h1 | h2 |"           # header row (first matrix row)
    assert lines[1] == "|---|---|"             # GFM separator
    assert lines[2:] == ["| a | b |", "| c | d |"]  # body


def test_gfm_table_pads_ragged_rows_to_width():
    # A short row is padded with empty cells so the table stays rectangular.
    out = matrix_to_gfm_table([["a", "b", "c"], ["d"]])
    assert out.split("\n") == ["| a | b | c |", "|---|---|---|", "| d |  |  |"]


def test_gfm_table_empty_matrix_is_empty_string():
    assert matrix_to_gfm_table([]) == ""


# --------------------------------------------------------------------------- #
# AC2 — merge join → anchor keeps the value, every covered cell is blank (D5)  #
# --------------------------------------------------------------------------- #

def test_merged_matrix_anchor_value_covered_blank_real_fixture():
    tab = _tab("Merged")
    m = render_matrix(_used_range(tab, "01-extent-Merged.json").values, tab.merges)

    # A1:C1 — anchor A1 keeps the value; B1, C1 blank.
    assert m[0][0] == "merged title spanning A1:C1"
    assert m[0][1] == "" and m[0][2] == ""
    # A3:A5 — anchor A3 keeps the value; A4, A5 blank.
    assert m[2][0] == "vertical merge A3:A5"
    assert m[3][0] == "" and m[4][0] == ""
    # B3:C3 — anchor B3 keeps the value; C3 blank.
    assert m[2][1] == "b3 beside merge"
    assert m[2][2] == ""
    # B7:D8 — anchor B7 keeps the value; the covered cells inside the used range blank.
    assert m[6][1] == "99.5"
    assert m[6][2] == "" and m[7][1] == "" and m[7][2] == ""
    # A10:C10 — anchor A10 keeps the value; B10, C10 blank.
    assert m[9][0] == "lonely cell after merges"
    assert m[9][1] == "" and m[9][2] == ""


def test_non_covered_cell_outside_any_merge_survives():
    # 'c5 sparse' at C5 (row 4, col 2) is NOT inside any merge — it must survive.
    tab = _tab("Merged")
    m = render_matrix(_used_range(tab, "01-extent-Merged.json").values, tab.merges)
    assert m[4][2] == "c5 sparse"


def test_merge_join_blanks_a_non_null_covered_cell():
    # The merge join is the authority (D5): a covered cell carrying a stray value
    # (contrary to the usual merge-covered null) must STILL render blank — proving
    # the join actively masks, not merely that the raw read happened to be null.
    m = render_matrix([["anchor", "STRAY", "STRAY2"]], (Merge(0, 0, 0, 2),))
    assert m == [["anchor", "", ""]]


# --------------------------------------------------------------------------- #
# AC3 — merges are 0-indexed, END-inclusive; an off-by-one must fail           #
# --------------------------------------------------------------------------- #

def test_merge_covered_cells_horizontal_end_inclusive():
    # {0,0,0,2} = A1:C1: anchor A1 excluded; covered exactly B1, C1.
    assert merge_covered_cells([Merge(0, 0, 0, 2)]) == {(0, 1), (0, 2)}


def test_merge_covered_cells_boundary_a3_a5_covers_exactly_a4_a5():
    # A3:A5 = Merge(start_row=2, end_row=4, start_col=0, end_col=0). END-INCLUSIVE:
    # covers exactly A4 (row 3) and A5 (row 4). An end-EXCLUSIVE off-by-one would
    # drop A5; an anchor-inclusive bug would add A3 (row 2). Either makes this fail.
    covered = merge_covered_cells([Merge(2, 4, 0, 0)])
    assert covered == {(3, 0), (4, 0)}
    assert (4, 0) in covered        # END-inclusive: A5 IS covered
    assert (2, 0) not in covered    # anchor A3 keeps its value


def test_merge_covered_cells_rectangular_block_b7_d8():
    # B7:D8 = Merge(6,7,1,3): a 2×3 block; anchor B7 excluded; 5 covered cells.
    covered = merge_covered_cells([Merge(6, 7, 1, 3)])
    assert covered == {(6, 2), (6, 3), (7, 1), (7, 2), (7, 3)}
    assert (6, 1) not in covered    # anchor B7


def test_merge_covered_cells_single_cell_merge_covers_nothing():
    # A degenerate 1×1 "merge" has only its anchor — nothing is covered.
    assert merge_covered_cells([Merge(3, 3, 3, 3)]) == set()


def test_merge_covered_cells_unions_all_regions():
    tab = _tab("Merged")
    covered = merge_covered_cells(tab.merges)
    # Union of A1:C1, A3:A5, B3:C3, B7:D8, A10:C10 covered (non-anchor) cells.
    assert covered == {
        (0, 1), (0, 2),                      # A1:C1
        (3, 0), (4, 0),                      # A3:A5
        (2, 2),                              # B3:C3
        (6, 2), (6, 3), (7, 1), (7, 2), (7, 3),  # B7:D8
        (9, 1), (9, 2),                      # A10:C10
    }


# --------------------------------------------------------------------------- #
# AC4 — a standalone read emits EVERY tab as its own titled table (D3)         #
# --------------------------------------------------------------------------- #

def test_render_spreadsheet_emits_a_titled_table_per_tab():
    types_tab, merged_tab = _tab("Types"), _tab("Merged")
    out = render_spreadsheet([
        (types_tab, _used_range(types_tab, "01-extent-Types.json")),
        (merged_tab, _used_range(merged_tab, "01-extent-Merged.json")),
    ])

    # Exactly two per-tab headings, in sheet order.
    headings = re.findall(r"^## .+$", out, flags=re.MULTILINE)
    assert headings == ["## Types", "## Merged"]
    # Exactly two GFM tables — one separator line each.
    sep_lines = [ln for ln in out.splitlines() if re.fullmatch(r"\|(?:---\|)+", ln)]
    assert len(sep_lines) == 2
    # Tab order is preserved (Types before Merged).
    assert out.index("## Types") < out.index("## Merged")


def test_render_tab_titles_a_single_tab():
    tab = _tab("Merged")
    out = render_tab(tab, _used_range(tab, "01-extent-Merged.json"))
    assert out.startswith("## Merged\n\n")
    assert "| merged title spanning A1:C1 |" in out


def test_tab_heading_uses_title_when_present():
    tab = SheetTab(sheet_id="abc123", title="Budget", index=0,
                   row_count=1, column_count=1)
    assert tab_heading(tab) == "## Budget"


def test_tab_heading_synthesized_from_sheet_id_when_title_empty():
    # An embedded sheet has no standalone title (spike Q6) — synthesize from sheet_id.
    tab = SheetTab(sheet_id="shtcnXYZ", title="", index=0,
                   row_count=1, column_count=1)
    assert tab_heading(tab) == "## Sheet shtcnXYZ"


def test_tab_heading_synthesized_when_title_none():
    tab = SheetTab(sheet_id="shtcnXYZ", title=None, index=0,
                   row_count=1, column_count=1)
    assert tab_heading(tab) == "## Sheet shtcnXYZ"


def test_render_tab_empty_matrix_emits_heading_and_empty_marker():
    tab = SheetTab(sheet_id="e1", title="Empty", index=0, row_count=1, column_count=1)
    out = render_tab(tab, UsedRange(sheet_id="e1", a1_range=None, revision=None, values=[]))
    assert out.startswith("## Empty")
    assert "_(empty sheet)_" in out
    assert "|" not in out    # no table emitted for an empty tab


# --------------------------------------------------------------------------- #
# ESCAPING — a cell with a pipe or newline is normalized to keep the GFM valid #
# --------------------------------------------------------------------------- #

def test_escape_cell_normalizes_newline_to_br():
    assert escape_cell("line one\nline two") == "line one<br>line two"


def test_escape_cell_escapes_pipe():
    assert escape_cell("a | b") == "a \\| b"


def test_escape_cell_matches_docx_table_convention():
    # Byte-identical to the docx table cell escape (strip → \n→<br> → |→\|), D6 reuse.
    assert escape_cell("  x\ny | z  ") == "x<br>y \\| z"


def test_newline_in_cell_normalized_real_fixture():
    # Our own fixture data has a newline-in-cell: the Types tab row 'string with
    # newline' col D reads "line one\nline two" — it MUST be normalized to <br> so
    # the raw newline can't break the table row.
    tab = _tab("Types")
    m = render_matrix(_used_range(tab, "01-extent-Types.json").values, tab.merges)
    row = next(r for r in m if r and r[0] == "string with newline")
    assert "line one<br>line two" in row
    assert not any("\n" in cell for cell in row)   # no raw newline survives


def test_types_standalone_table_rows_stay_intact():
    # A raw newline inside a cell would split a table row; the <br> normalization
    # must keep every table line a complete `| … |` row.
    tab = _tab("Types")
    out = render_tab(tab, _used_range(tab, "01-extent-Types.json"))
    assert "<br>" in out    # the newline cell was normalized, not dropped
    table_lines = [ln for ln in out.splitlines() if ln.startswith("|")]
    assert table_lines, "expected a table"
    assert all(ln.rstrip().endswith("|") for ln in table_lines)


# --------------------------------------------------------------------------- #
# Reuse / parity — the shared renderer config threads through (D6)             #
# --------------------------------------------------------------------------- #

def test_render_matrix_threads_mention_map():
    # render_matrix delegates to render_cell (S3), so the mention-resolution map
    # threads through — no forked cell rendering.
    obj = {"type": "mention", "mentionType": 0, "userID": "ou_1"}
    m = render_matrix([[obj]], (), mention_names={"ou_1": "Resolved"})
    assert m == [["@Resolved"]]


def test_public_surface_exported_from_package():
    from larkdocio.sheets import (  # noqa: F401
        escape_cell,
        matrix_to_gfm_table,
        merge_covered_cells,
        render_matrix,
        render_spreadsheet,
        render_tab,
        tab_heading,
    )


# --------------------------------------------------------------------------- #
# LD-117 gain (a) — OPT-IN fidelity: cell-level bold/italic → MD emphasis      #
# threaded through render_matrix/render_tab. ``fidelity`` is an ExportedSheet  #
# (LD-114) keyed by A1 ref; a cell at (row i, col j) maps to A1               #
# ``column(j+1)+str(i+1)``. fidelity=None (the DEFAULT) is byte-identical to   #
# the values-only render — the flag-OFF invariant.                            #
# --------------------------------------------------------------------------- #

def _fidelity(cells):
    """Build an ExportedSheet fidelity source from ``{ref: (bold, italic)}``."""
    return ExportedSheet(
        name="Sheet1",
        cells={
            ref: ExportedCell(ref=ref, value=None, bold=b, italic=i)
            for ref, (b, i) in cells.items()
        },
    )


def test_render_matrix_fidelity_none_is_byte_identical():
    values = [["hello", "Red,Green"], ["$1,234.56", "world"]]
    assert render_matrix(values, fidelity=None) == render_matrix(values)


def test_render_matrix_applies_cell_bold_from_fidelity():
    m = render_matrix([["hello"]], fidelity=_fidelity({"A1": (True, False)}))
    assert m == [["**hello**"]]


def test_render_matrix_applies_cell_italic_from_fidelity():
    m = render_matrix([["hello"]], fidelity=_fidelity({"A1": (False, True)}))
    assert m == [["_hello_"]]


def test_render_matrix_fidelity_only_flagged_cells_emphasised():
    m = render_matrix([["a", "b"]], fidelity=_fidelity({"A1": (True, False)}))
    assert m == [["**a**", "b"]]


def test_render_matrix_bold_multiselect_wraps_the_whole_set():
    # gain (a) + gain (b): a bold multi-select cell → the WHOLE ordered set bold.
    m = render_matrix([["Red,Green"]], fidelity=_fidelity({"A1": (True, False)}))
    assert m == [["**Red, Green**"]]


def test_render_matrix_fidelity_ref_maps_row_col_to_a1():
    # (row 1, col 1) is B2 — only that cell is flagged.
    values = [["a", "b"], ["c", "d"]]
    m = render_matrix(values, fidelity=_fidelity({"B2": (True, False)}))
    assert m == [["a", "b"], ["c", "**d**"]]


def test_render_matrix_fidelity_never_unblanks_a_covered_cell():
    # A merge-covered cell stays blank even if the export marks it bold (the merge
    # join is the authority — D5 — and an empty cell has no core to emphasise).
    m = render_matrix(
        [["anchor", "STRAY"]], (Merge(0, 0, 0, 1),),
        fidelity=_fidelity({"A1": (True, False), "B1": (True, False)}),
    )
    assert m == [["**anchor**", ""]]


def test_render_tab_threads_fidelity_into_the_table():
    tab = SheetTab(sheet_id="s1", title="T", index=0, row_count=1, column_count=1)
    ur = UsedRange.from_tab_values(tab, [["hello"]])
    out = render_tab(tab, ur, fidelity=_fidelity({"A1": (True, False)}))
    assert "**hello**" in out


def test_render_tab_fidelity_none_byte_identical():
    tab = SheetTab(sheet_id="s1", title="T", index=0, row_count=1, column_count=2)
    ur = UsedRange.from_tab_values(tab, [["hello", "Red,Green"]])
    assert render_tab(tab, ur, fidelity=None) == render_tab(tab, ur)
