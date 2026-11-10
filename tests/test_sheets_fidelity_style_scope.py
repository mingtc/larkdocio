"""THE DISAMBIGUATING TEST — what scope of bold does the Sheets fidelity read leg
report? (LD-154 / dogfood F18's § Investigation, decided FIRST.)

The finding under investigation: on a real spreadsheet the fidelity leg returned
**byte-identical** Markdown and its ``ExportedCell.bold`` was ``False`` on a cell whose
values-API read carried ``segmentStyle.bold: true``. Two readings were possible and only
one is a bug:

* **the wording is the defect** — the leg reports *whole-cell (format-level)* style, the
  cell in question carried *run-level* bold, and run-level bold is fully visible to the
  values API (so it was already rendered, and the leg correctly added nothing); or
* **the export parse is the defect** — the leg should have reported that bold and did not.

This module runs the disambiguation **both ways on the same cell reference** so the
conclusion cannot be an artifact of one fixture:

* ``A1`` carrying bold **in the cell's format** (an ``xl/styles.xml`` font behind the
  cell's ``s=`` index) — what the style endpoint writes;
* ``A1`` carrying bold **only inside its text runs** (``<is><r><rPr><b/>``), with the
  cell's own format un-bold.

**Live corroboration for both arms already exists in the repo** (no new live call is
needed to decide this):

* arm *cell-format*: ``tests/captures/sheets-write-spike/captures/02b-export-fidelity.json`` — an
  ``appendStyle {font:{bold:true}}`` write on ``c8d13e!A1:A1``, after which the values API
  answers a bare ``0.1234`` / ``"12.34%"`` with **no style of any kind**, while the export
  of the same cell carries the bold font. That capture is the L2 crux, live.
* arm *run-level*: the dogfood observation itself — ``get_values(...)`` →
  ``segmentStyle.bold: true`` and ``ExportedCell(ref='A9', value='Total', bold=False)``
  through shipped code on the same live cell.

THE VERDICT (asserted below, not asserted in prose): the leg reports **cell-format** bold,
run-level bold arrives through the **values** leg, the two are **layered** (emphasis is
applied *over* the values render, never instead of it), so a run-level-bold cell rendering
identically with the leg on is **correct**. AC2 (wording) applies; AC3 (an export-parse
code fix) does not.
"""
import json
from pathlib import Path

import xlsx_synth as X

from larkdocio.sheets.export_reader import parse_xlsx
from larkdocio.sheets.render import render_cell
from larkdocio.sheets.table import render_matrix

_SPIKE_CAPTURES = Path(__file__).resolve().parent.parent / "tests" / "captures" / "sheets-spike" / "captures"
_WRITE_CAPTURES = (
    Path(__file__).resolve().parent.parent / "tests" / "captures" / "sheets-write-spike" / "captures"
)

#: The captured values-API payload for a **run-level** styled cell (spike read Q1 r17,
#: ``02-types-FormattedValue.json`` row "styled text runs", native column D). Its first
#: run is bold — this is the wire shape the dogfood cell had.
_STYLED_RUNS_CAPTURE = "02-types-FormattedValue.json"

#: The captured live proof for the **cell-format** arm: a style write, then the values
#: reads of the very same cell.
_EXPORT_FIDELITY_CAPTURE = "02b-export-fidelity.json"


def _capture_row(label):
    payload = json.loads((_SPIKE_CAPTURES / _STYLED_RUNS_CAPTURE).read_text(encoding="utf-8"))
    for row in payload["data"]["valueRange"]["values"]:
        if row and row[0] == label:
            return row
    raise AssertionError(f"no type-matrix row labelled {label!r}")


def _run_level_segments():
    """A real captured segment array whose FIRST run is bold (run-level emphasis)."""
    segments = _capture_row("styled text runs")[3]
    assert isinstance(segments, list) and segments[0]["segmentStyle"]["bold"] is True, segments
    return segments


# --------------------------------------------------------------------------- #
# The two workbooks — same cell ref A1, two different places for the bold.     #
# --------------------------------------------------------------------------- #

def _cell_format_bold_workbook(text="Total"):
    """``A1`` = ``text``, bold applied as the **cell's format** (``s=1`` → a bold font).

    This is the shape the style endpoint produces and the shape
    ``02b-export-fidelity.json`` captured live.
    """
    styles = X.styles_xml(
        fonts=[{}, {"bold": True}],
        cell_xfs=[
            {"numFmtId": 0, "fontId": 0, "fillId": 0},
            {"numFmtId": 0, "fontId": 1, "fillId": 0},
        ],
    )
    return X.build_workbook(
        [{"name": "Sheet1", "cells": [("A1", {"s": 1, "t": "s", "v": "0"})]}],
        shared_strings=[text],
        styles=styles,
    )


def _run_level_bold_workbook(text="Total"):
    """``A1`` = ``text`` whose bold lives **inside its text runs** (``<r><rPr><b/>``),
    the cell's own format staying un-bold (``s=0`` → the default font).

    A bold font is still present in ``xl/styles.xml`` (index 1) but **no cell format uses
    it** — so a parse that reported "bold appears in this workbook" rather than "this
    cell's format is bold" would wrongly answer ``True`` here.
    """
    styles = X.styles_xml(
        fonts=[{}, {"bold": True}],
        cell_xfs=[
            {"numFmtId": 0, "fontId": 0, "fillId": 0},
            {"numFmtId": 0, "fontId": 1, "fillId": 0},
        ],
    )
    return X.build_workbook(
        [{
            "name": "Sheet1",
            "cells": [("A1", {"s": 0, "t": "inlineStr",
                              "rich": [(text, {"bold": True})]})],
        }],
        styles=styles,
    )


def _exported_sheet(workbook_bytes):
    return parse_xlsx(workbook_bytes).first_sheet


# --------------------------------------------------------------------------- #
# AC1 — the disambiguation, arm by arm, on the SAME cell reference.            #
# --------------------------------------------------------------------------- #

def test_investigation_cell_format_bold_IS_reported_by_the_fidelity_leg():
    """Arm 1 — bold in the cell's **format** is what the leg reads."""
    cell = _exported_sheet(_cell_format_bold_workbook()).cell("A1")
    assert cell is not None
    assert cell.value == "Total"
    assert cell.bold is True


def test_investigation_run_level_bold_is_NOT_reported_by_the_fidelity_leg():
    """Arm 2 — bold living only in the cell's **text runs** is not the leg's subject.

    Same cell reference, same workbook-level bold font available; the difference is
    whether the **cell's format** uses it. The leg answers ``False`` — which is what the
    dogfood cell reported live, and it is the CORRECT answer, not a parse miss: the
    emphasis is not lost, it arrives over the values leg (see the layering tests below).
    """
    cell = _exported_sheet(_run_level_bold_workbook()).cell("A1")
    assert cell is not None
    assert cell.value == "Total"
    assert cell.bold is False


def test_investigation_the_values_api_does_not_carry_cell_format_style_LIVE_CAPTURE():
    """Arm 1's other half, from the **live capture**: after a cell-format bold write, the
    values API answers a bare scalar / display string with no style at all.

    This is why the leg exists — and why its claim must be about *whole-cell* style.
    """
    payload = json.loads(
        (_WRITE_CAPTURES / _EXPORT_FIDELITY_CAPTURE).read_text(encoding="utf-8")
    )
    captures = payload["captures"]

    style_write = captures["write_style"]["request_body"]["appendStyle"]
    assert style_write["style"]["font"]["bold"] is True     # bold as a CELL FORMAT
    assert style_write["range"] == "c8d13e!A1:A1"

    for leg, expected in (("read_unformatted", 0.1234), ("read_formatted", "12.34%")):
        values = captures[leg]["response"]["data"]["valueRange"]["values"]
        assert values == [[expected]], (leg, values)
        # A bare scalar / string: no segment array, so nothing for render_cell to
        # emphasize. The bold is unreachable from this leg.
        assert render_cell(values[0][0]) == str(expected)


def test_investigation_run_level_bold_IS_carried_by_the_values_api():
    """Arm 2's other half: run-level bold is fully visible to the values API, and the
    values-only render already emits it. Nothing needs the export leg to see it."""
    segments = _run_level_segments()
    assert render_cell(segments).startswith("**bold start**")


# --------------------------------------------------------------------------- #
# AC1 — the RENDER-LEVEL consequence: what a consumer actually observes.       #
# --------------------------------------------------------------------------- #

def test_the_leg_changes_the_render_for_a_cell_format_bold_cell():
    """Flag ON must be observably different where the values leg is blind."""
    values = [["Total"]]                       # what the values API answers (no style)
    fidelity = _exported_sheet(_cell_format_bold_workbook())

    assert render_matrix(values) == [["Total"]]
    assert render_matrix(values, fidelity=fidelity) == [["**Total**"]]


def test_byte_identical_output_on_a_run_level_bold_cell_is_CORRECT_not_a_miss():
    """THE FINDING, reproduced and explained.

    A cell whose bold is run-level renders **identically** with the leg on — because the
    values render already carried the emphasis. Byte-identical here means "nothing to
    add", not "nothing was read".
    """
    values = [[_run_level_segments()]]
    fidelity = _exported_sheet(_run_level_bold_workbook())

    values_only = render_matrix(values)
    with_fidelity = render_matrix(values, fidelity=fidelity)

    assert with_fidelity == values_only               # the reported symptom
    assert "**bold start**" in values_only[0][0]      # and the emphasis is THERE


def test_the_fidelity_leg_is_layered_OVER_the_values_render_never_instead_of_it():
    """The layering is deliberate, and this pins it.

    A future render that trusted ``fidelity`` *instead of* the segments would silently
    drop run-level emphasis on exactly the workbook that exposed this finding. The leg
    must only ever ADD.
    """
    values = [[_run_level_segments()]]
    # An exported sheet that knows this cell and reports it un-styled — the strongest
    # form: the leg has an opinion about A1 and that opinion is "no cell-format style".
    fidelity = _exported_sheet(_run_level_bold_workbook())
    assert fidelity.cell("A1") is not None and fidelity.cell("A1").bold is False

    assert render_matrix(values, fidelity=fidelity) == render_matrix(values)


def test_both_scopes_at_once_still_only_ADD():
    """A cell carrying BOTH kinds of bold keeps its run emphasis and gains the cell's."""
    values = [[[{"type": "text", "text": "Total",
                 "segmentStyle": {"bold": True}}]]]
    fidelity = _exported_sheet(_cell_format_bold_workbook())

    values_only = render_matrix(values)
    with_fidelity = render_matrix(values, fidelity=fidelity)

    assert values_only == [["**Total**"]]
    assert with_fidelity != values_only            # the cell format is a real addition
    assert "Total" in with_fidelity[0][0]
    # The run's own markers survive verbatim — the wrap never re-escapes them.
    assert "\\*" not in with_fidelity[0][0]
