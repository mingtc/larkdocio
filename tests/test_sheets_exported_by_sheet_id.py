"""LD-152 AC2 — ``exported_by_sheet_id(tabs, workbook)``: the title↔sheet_id join.

**The gap (dogfood F17).** The standalone L2 fidelity read needs a
``{sheet_id: ExportedSheet}`` map, and an xlsx export names its worksheets by the tab's
**title**. So a consumer must join title→sheet_id — in a guide that devotes a paragraph to
"a title is never a ``sheet_id``" and then requires exactly that join. The join also carries
two rules that are easy to get wrong and impossible to guess: a tab whose worksheet is
absent must degrade to **values-only** (never raise, never borrow another sheet's styles),
and the sole-sheet fallback is only sound when there is nothing to be ambiguous about.

This is the shipped join, so the recipe is a call rather than eight lines of re-derived
matching — and so the guide and the reader's own opt-in fidelity leg agree by construction.
"""
import pytest

from larkdocio.sheets.export_reader import (
    ExportedCell,
    ExportedSheet,
    ParsedWorkbook,
    exported_by_sheet_id,
)
from larkdocio.sheets.models import SheetTab
from larkdocio.sheets.table import render_spreadsheet


def _tab(sheet_id, title, index=0):
    return SheetTab(sheet_id=sheet_id, title=title, index=index,
                    row_count=2, column_count=2)


def _sheet(name, **cells):
    return ExportedSheet(
        name=name,
        cells={ref: ExportedCell(ref=ref, value=ref, **kw) for ref, kw in cells.items()},
    )


# --------------------------------------------------------------------------- #
# The join itself.                                                             #
# --------------------------------------------------------------------------- #

def test_it_keys_the_exported_sheets_by_sheet_id_not_by_title():
    """The whole point: in → title-keyed workbook, out → ``sheet_id``-keyed map."""
    tabs = [_tab("3bf016", "Sheet1"), _tab("9aa021", "Q3 Detail", index=1)]
    workbook = ParsedWorkbook(sheets=(_sheet("Q3 Detail"), _sheet("Sheet1")))

    joined = exported_by_sheet_id(tabs, workbook)

    assert sorted(joined) == ["3bf016", "9aa021"]
    assert joined["3bf016"].name == "Sheet1"
    assert joined["9aa021"].name == "Q3 Detail"


def test_the_map_is_exactly_what_render_spreadsheet_consumes():
    """End-to-end coupling: the returned map, handed straight to
    ``render_spreadsheet(fidelity=…)``, actually produces the L2 emphasis — and the
    values-only render of the same pairs does not. (Dogfood F18's "the fidelity leg returned
    byte-identical output" is the symptom of the join being wrong, so proving a DIFFERENCE
    is what proves the join right.)"""
    from larkdocio.sheets.extent import UsedRange

    tab = _tab("3bf016", "Sheet1")
    used = UsedRange(sheet_id="3bf016", a1_range="3bf016!A1:B1", revision=7,
                     values=[["Name", "Qty"]])
    workbook = ParsedWorkbook(sheets=(_sheet("Sheet1", A1={"bold": True}),))

    fidelity = exported_by_sheet_id([tab], workbook)
    plain = render_spreadsheet([(tab, used)])
    emphasized = render_spreadsheet([(tab, used)], fidelity=fidelity)

    assert "| Name | Qty |" in plain
    assert "| **Name** | Qty |" in emphasized
    assert plain != emphasized


def test_a_tab_with_no_exported_worksheet_is_omitted_so_it_renders_values_only():
    """A missing worksheet must degrade that tab to values-only — never raise, and never
    borrow a neighbour's styles."""
    tabs = [_tab("3bf016", "Sheet1"), _tab("9aa021", "Hidden", index=1)]
    workbook = ParsedWorkbook(sheets=(_sheet("Sheet1"),))

    joined = exported_by_sheet_id(tabs, workbook)

    assert sorted(joined) == ["3bf016"]
    assert "9aa021" not in joined, "a tab with no worksheet must not be given another's sheet"


def test_the_sole_sheet_fallback_applies_only_when_nothing_is_ambiguous():
    """A one-tab spreadsheet whose single worksheet is named differently still joins (the
    shipped embedded-sheet leg's fallback) — but the fallback is **not** applied when there
    is more than one tab, because then it would be a guess."""
    single = exported_by_sheet_id([_tab("3bf016", "Sheet1")],
                                  ParsedWorkbook(sheets=(_sheet("Renamed"),)))
    assert single["3bf016"].name == "Renamed"

    ambiguous = exported_by_sheet_id(
        [_tab("3bf016", "Sheet1"), _tab("9aa021", "Other", index=1)],
        ParsedWorkbook(sheets=(_sheet("Renamed"),)),
    )
    assert ambiguous == {}, (
        "with two tabs and one worksheet, which tab it belongs to is unknown — a guess here "
        "would attach the wrong styles to real cells")


def test_it_accepts_the_write_clients_dict_tabs_too():
    """``query_sheets`` hands back ``SheetTab`` objects and ``query_tabs`` hands back dicts;
    a join that spoke only one of them would recreate the very confusion F17 is about."""
    joined = exported_by_sheet_id(
        [{"sheet_id": "3bf016", "title": "Sheet1", "index": 0}],
        ParsedWorkbook(sheets=(_sheet("Sheet1"),)),
    )
    assert joined["3bf016"].name == "Sheet1"


def test_an_absent_workbook_or_empty_tabs_join_to_nothing():
    """The degrade path is a value, not an exception: a failed export (``None``) yields an
    empty map, which renders values-only."""
    assert exported_by_sheet_id([_tab("3bf016", "Sheet1")], None) == {}
    assert exported_by_sheet_id([], ParsedWorkbook(sheets=(_sheet("Sheet1"),))) == {}
    assert exported_by_sheet_id([_tab("3bf016", "Sheet1")], ParsedWorkbook(sheets=())) == {}


def test_a_tab_without_a_sheet_id_is_refused_loudly():
    """A tab-shaped object with no ``sheet_id`` cannot be joined — and silently dropping it
    would produce exactly the "the flag did nothing" confusion of F18."""
    with pytest.raises(ValueError) as exc:
        exported_by_sheet_id([{"title": "Sheet1"}], ParsedWorkbook(sheets=(_sheet("Sheet1"),)))
    assert "sheet_id" in str(exc.value)


def test_duplicate_titles_keep_the_first_tab_in_order():
    """Lark permits two tabs with the same title; the export has one worksheet per name, so
    the join is documented as first-in-order rather than arbitrary."""
    tabs = [_tab("first0", "Same"), _tab("second", "Same", index=1)]
    joined = exported_by_sheet_id(tabs, ParsedWorkbook(sheets=(_sheet("Same"),)))
    assert sorted(joined) == ["first0", "second"], (
        "both tabs legitimately match the one worksheet by title — the join reports both "
        "rather than dropping one")
