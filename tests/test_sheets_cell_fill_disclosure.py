"""Offline tests for the per-cell FILL disclosure (LD-331).

The export-fidelity leg has always recovered a cell's fill ARGB
(``ExportedCell.fill_rgb``), but nothing carried it to a reader: the render dropped it
without a word and the read-side docs never named it, so a **colour-encoded sheet** — the
consumer's gantt, where the schedule *is* the colour — read as labels with no bars.

Two seams close that, and both are exercised here:

* **the render disclosure** — :func:`~larkdocio.sheets.table.fill_disclosure_note`, in the
  merge/filter-note idiom (the note is added, the table is not touched), emitted by
  :func:`~larkdocio.sheets.table.render_tab` between the heading and the table;
* **the structured accessor** — :func:`~larkdocio.sheets.table.cell_fills`, which the note
  itself is built from (so note and API cannot drift), returning ``{ref: ARGB}`` for the
  filled cells or ``None`` when the fill layer was **not recovered**.

The three-way honesty is the point of half these tests: *no fill*, *cell absent from the
export*, *tab absent from the mapping* and *export failed* are four different answers and
none of them is laundered into "the fill is white".
"""
import pytest

from larkdocio.sheets.export_reader import ExportedCell, ExportedSheet, parse_xlsx
from larkdocio.sheets.extent import UsedRange
from larkdocio.sheets.models import Merge, SheetTab
from larkdocio.sheets.table import (
    FidelityUnavailable,
    cell_fills,
    fill_disclosure_note,
    render_spreadsheet,
    render_tab,
)
import xlsx_synth


def _tab(sheet_id="s1", title="T", rows=1, cols=1, merges=()):
    return SheetTab(sheet_id=sheet_id, title=title, index=0,
                    row_count=rows, column_count=cols, merges=merges)


def _sheet(fills, name="Sheet1"):
    """An ExportedSheet from ``{ref: argb_or_None}`` — a ``None`` value is a cell the
    export carried with **no** fill (present, unfilled), which is not the same fact as a
    cell the export never carried at all."""
    return ExportedSheet(
        name=name,
        cells={ref: ExportedCell(ref=ref, value=None, fill_rgb=argb)
               for ref, argb in fills.items()},
    )


# --------------------------------------------------------------------------- #
# AC3 — the fill is RECOVERABLE, on both chosen seams                          #
# --------------------------------------------------------------------------- #

def test_cell_fills_returns_the_recovered_argb_by_ref():
    assert cell_fills(_sheet({"B2": "FFFFFF00"})) == {"B2": "FFFFFF00"}


def test_the_rendered_tab_discloses_the_fill_argb_and_its_cells():
    """The gantt case: the bar is in the Markdown, colour and position."""
    tab = _tab(rows=2, cols=4)
    ur = UsedRange.from_tab_values(tab, [["Task", "", "", ""],
                                         ["Design", "", "", ""]])
    out = render_tab(tab, ur, fidelity=_sheet({"B2": "FFFFFF00",
                                               "C2": "FFFFFF00",
                                               "D2": "FFFFFF00"}))
    assert "FFFFFF00" in out
    assert "B2:D2" in out, "a contiguous run of filled cells is disclosed as one A1 range"
    assert "3 filled cells" in out


def test_the_disclosure_groups_by_colour_and_compresses_row_runs():
    note = fill_disclosure_note(_sheet({
        "C2": "FFFFFF00", "D2": "FFFFFF00", "E2": "FFFFFF00",
        "C3": "FF00B050", "F5": "FFFFFF00",
    }))
    assert "FFFFFF00 — C2:E2, F5" in note
    assert "FF00B050 — C3" in note
    assert "5 filled cells" in note


def test_the_disclosure_is_a_single_line_that_cannot_break_a_pipe_table():
    note = fill_disclosure_note(_sheet({"A1": "FFFFFF00"}))
    assert "\n" not in note and "|" not in note
    assert note.startswith("_(") and note.endswith(")_")


def test_the_argb_survives_the_real_xlsx_parse_end_to_end():
    """Not a hand-built model: the ARGB comes out of ``xl/styles.xml`` through the
    shipped parser, then through the new seam."""
    workbook = parse_xlsx(xlsx_synth.fidelity_workbook())
    exported = workbook.first_sheet
    assert cell_fills(exported) == {"A1": "FFFFFF00"}
    tab = _tab(title="Sheet1")
    ur = UsedRange.from_tab_values(tab, [["0.1234"]])
    assert "FFFFFF00" in render_tab(tab, ur, fidelity=exported)


def test_the_note_states_it_does_not_interpret_the_colour():
    note = fill_disclosure_note(_sheet({"A1": "FFFFFF00"}))
    assert "what a colour means" in note


# --------------------------------------------------------------------------- #
# AC4 — an unrecoverable fill is STATED, never guessed                         #
# --------------------------------------------------------------------------- #

def test_a_cell_with_no_fill_is_absent_from_the_map_and_never_coerced_to_white():
    exported = _sheet({"A1": None})
    assert exported.cell("A1").fill_rgb is None      # stated absence, not "FFFFFFFF"
    assert cell_fills(exported) == {}                # looked, and there is nothing


def test_a_cell_the_export_omitted_is_None_not_an_unfilled_cell():
    exported = _sheet({"A1": None})
    assert exported.cell("Z9") is None               # never carried
    assert exported.cell("A1") is not None           # carried, unfilled — a different fact


def test_zero_fills_is_an_empty_map_which_is_not_the_unknown_answer():
    """``{}`` (the export covered this tab, nothing is filled) must not read as ``None``
    (the fill layer was never recovered)."""
    assert cell_fills(_sheet({"A1": None})) == {}
    assert cell_fills(_sheet({"A1": None})) is not None
    assert cell_fills(None) is None
    assert cell_fills(FidelityUnavailable("no export")) is None


def test_zero_fills_discloses_nothing_because_nothing_is_unknown():
    assert fill_disclosure_note(_sheet({"A1": None})) is None
    assert fill_disclosure_note(None) is None


def test_a_tab_missing_from_the_fidelity_mapping_says_so_rather_than_reading_as_unfilled():
    """The leg ran; this tab got no export. That is *unknown*, not *no fills* — the
    house rule the sheets surface applies everywhere ('unknown' is never laundered)."""
    tab = _tab(sheet_id="s1")
    ur = UsedRange.from_tab_values(tab, [["hello"]])
    out = render_spreadsheet([(tab, ur)], fidelity={"OTHER": _sheet({"A1": "FFFFFF00"})})
    assert "could not be read" in out
    assert "unknown" in out


def test_the_unavailable_sentinel_renders_the_could_not_be_read_note_with_its_reason():
    note = fill_disclosure_note(FidelityUnavailable("the xlsx export could not be read"))
    assert "the xlsx export could not be read" in note
    assert "unknown" in note


def test_the_unavailable_sentinel_leaves_the_cells_alone():
    """It answers ``.cell(ref)`` with ``None`` so emphasis is untouched — the sentinel
    discloses a gap, it never invents a style."""
    sentinel = FidelityUnavailable("nope")
    assert sentinel.cell("A1") is None
    tab = _tab()
    ur = UsedRange.from_tab_values(tab, [["hello"]])
    assert "| hello |" in render_tab(tab, ur, fidelity=sentinel)


def test_a_failed_export_in_the_embedded_deep_read_degrades_to_the_unavailable_note():
    from larkdocio.sheets.embed import _read_cell_fidelity

    class _Boom:
        def read_workbook(self, token):
            raise RuntimeError("export refused")

    result = _read_cell_fidelity(_Boom(), "tok", _tab(title="Sheet1"))
    assert isinstance(result, FidelityUnavailable)
    assert cell_fills(result) is None


def test_an_unmatched_worksheet_in_the_embedded_deep_read_is_unknown_not_unfilled():
    from larkdocio.sheets.embed import _read_cell_fidelity
    from larkdocio.sheets.export_reader import ParsedWorkbook

    class _TwoSheets:
        def read_workbook(self, token):
            return ParsedWorkbook(sheets=(_sheet({}, name="A"), _sheet({}, name="B")))

    result = _read_cell_fidelity(_TwoSheets(), "tok", _tab(title="Nope"))
    assert isinstance(result, FidelityUnavailable)


# --------------------------------------------------------------------------- #
# AC5 — the flag-OFF invariant and the ADD-ONLY invariant                      #
# --------------------------------------------------------------------------- #

def test_flag_off_render_is_byte_identical_to_the_values_only_render():
    tab = _tab(rows=2, cols=2)
    ur = UsedRange.from_tab_values(tab, [["a", "b"], ["c", "d"]])
    assert render_tab(tab, ur, fidelity=None) == render_tab(tab, ur)
    assert render_spreadsheet([(tab, ur)], fidelity=None) == render_spreadsheet([(tab, ur)])


def test_the_disclosure_only_adds_the_table_itself_is_untouched():
    tab = _tab(rows=2, cols=2)
    ur = UsedRange.from_tab_values(tab, [["a", "b"], ["c", "d"]])
    plain = render_tab(tab, ur)
    disclosed = render_tab(tab, ur, fidelity=_sheet({"A1": "FFFFFF00"}))
    added = [ln for ln in disclosed.splitlines() if ln.startswith("_(")]
    assert len(added) == 1, "exactly one line is added"
    # Removing the added line yields the values-only render, byte for byte.
    assert "\n".join(ln for ln in disclosed.splitlines()
                     if not ln.startswith("_(")).replace("\n\n\n", "\n\n") == plain


def test_the_disclosure_never_alters_run_level_or_cell_level_emphasis():
    tab = _tab(rows=1, cols=1)
    ur = UsedRange.from_tab_values(tab, [["hello"]])
    exported = ExportedSheet(name="Sheet1", cells={
        "A1": ExportedCell(ref="A1", value=None, bold=True, fill_rgb="FFFFFF00"),
    })
    out = render_tab(tab, ur, fidelity=exported)
    assert "| **hello** |" in out          # the emphasis the leg already added survives
    assert "FFFFFF00" in out               # and the fill is disclosed alongside it


def test_a_merge_covered_cell_stays_blank_and_the_fill_is_still_disclosed():
    """The merge join stays the authority for the TABLE; the disclosure is a separate
    statement about the sheet, so a covered cell's fill is reported without unblanking it."""
    tab = _tab(rows=1, cols=2, merges=(Merge(0, 0, 0, 1),))
    ur = UsedRange.from_tab_values(tab, [["anchor", "STRAY"]])
    out = render_tab(tab, ur, fidelity=_sheet({"B1": "FFFFFF00"}))
    assert "| anchor |  |" in out
    assert "FFFFFF00 — B1" in out


def test_the_filter_note_and_the_fill_note_coexist_in_a_stated_order():
    tab = SheetTab(sheet_id="s1", title="T", index=0, row_count=1, column_count=1,
                   filter_state="active", filtered_out_rows=(2,))
    ur = UsedRange.from_tab_values(tab, [["hello"]])
    out = render_tab(tab, ur, fidelity=_sheet({"A1": "FFFFFF00"}))
    assert out.index("Filter active") < out.index("Cell fills"), \
        "the filter note qualifies the ROW SET and comes first; the fill note follows"


@pytest.mark.parametrize("bad", [object(), "not a sheet", 7])
def test_an_unenumerable_fidelity_source_is_unknown_not_empty(bad):
    """A duck-typed ``.cell(ref)``-only source (documented as acceptable for emphasis)
    cannot be enumerated for fills — that is *unknown*, and must not read as 'no fills'."""
    assert cell_fills(bad) is None
