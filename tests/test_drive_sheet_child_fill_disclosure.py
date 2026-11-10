"""LD-385 — the fill disclosure reaches a STANDALONE spreadsheet, not just an embedded one.

The measured finding
--------------------
AC1 asked first whether the existing L2 export-fidelity leg already exposes fills. **It does**
— LD-331 shipped the whole answer: ``export_reader`` recovers each cell's ARGB from
``xl/styles.xml``, ``table.cell_fills`` is the programmatic ``{ref: ARGB}`` reading (modelled
on the merge/filter disclosure idiom), and ``table.fill_disclosure_note`` states it above the
tab's table. So AC2 forks to **(a) a route exists and scales** — one whole-workbook export per
spreadsheet, not one call per cell — and this issue is *surfacing*, not building.

What was still missing is the half that made the consumer's report true anyway: the **only**
shipped path from a standalone spreadsheet URL to Markdown — ``larkdocio.drive.read``'s
``sheets`` child leg, which the ``folder`` walk uses — called ``render_spreadsheet`` with **no
fidelity argument at all**, and ``--fidelity-read-sheets`` governed only the docx
**embedded**-sheet leg (LD-384 recorded that gap in as many words: *"a spreadsheet child of the
folder is read values-only either way"*). A consumer whose gantt is its own spreadsheet
therefore got a rectangle of blanks and **no flag that could change it**.

These tests pin the leg: the opt-in reaches a spreadsheet child, OFF is byte-identical and
costs no export, an export that fails discloses the gap rather than reading as an absent fill
layer, and the note reports the ARGB without interpreting it.
"""
import json
from pathlib import Path

import pytest

from larkdocio.errors import LarkAPIError
from xlsx_synth import build_workbook, styles_xml

from write_harness import _FakeHTTPResponse

_CAPTURES = Path(__file__).resolve().parent.parent / "tests" / "captures" / "ghost-tabs-probe" / "captures"

_SHEET_URL = "https://x.larksuite.com/sheets/SPREADSHEETTOKEN"
_TAB_ID = "444a1c"
_TAB_TITLE = "Schedule"
_BAR = "FFFFFF00"


def _real_tab_payload():
    probe = json.loads((_CAPTURES / "01-ghost-vs-real.json").read_text(encoding="utf-8"))
    return probe["steps"][0]["response"]["data"]["sheets"][0]


def _query_reply():
    payload = dict(_real_tab_payload())
    payload["sheet_id"] = _TAB_ID
    payload["title"] = _TAB_TITLE
    payload.pop("merges", None)
    return {"code": 0, "msg": "success", "data": {"sheets": [payload]}}


def _values_reply():
    """The consumer's shape: the bars are the FILL, so the cells themselves are blank."""
    return {"code": 0, "msg": "success", "data": {"revision": 37, "valueRange": {
        "range": f"{_TAB_ID}!A1:C2", "revision": 37,
        "values": [["Task", "", ""], ["Design", "", ""]]}}}


class _Opener:
    def __init__(self, payloads):
        self._payloads = list(payloads)

    def __call__(self, req, timeout=30):
        return _FakeHTTPResponse(self._payloads.pop(0))


def _fill_workbook_bytes():
    """One worksheet named for the tab, whose B2 carries a solid ``FFFFFF00`` fill — a bar."""
    styles = styles_xml(
        fonts=[{}],
        fills=[{"pattern": "none"}, {"pattern": "gray125"},
               {"pattern": "solid", "fg_rgb": _BAR}],
        cell_xfs=[{"numFmtId": 0, "fontId": 0, "fillId": 0},
                  {"numFmtId": 0, "fontId": 0, "fillId": 2}],
    )
    return build_workbook(
        [{"name": _TAB_TITLE, "cells": [("B2", {"s": 1})]}],
        styles=styles,
    )


class _ExportCounter:
    """Stands in for the READ-creds export reader and records whether it was reached at all."""

    def __init__(self, *, workbook_bytes=None, raises=None):
        self._workbook_bytes = workbook_bytes
        self._raises = raises
        self.calls = []

    def read_workbook(self, token):
        self.calls.append(token)
        if self._raises is not None:
            raise self._raises
        from larkdocio.sheets.export_reader import parse_xlsx
        return parse_xlsx(self._workbook_bytes)


@pytest.fixture
def sheet_leg(monkeypatch):
    """Wire the values read offline and hand the test control of the export leg."""
    from larkdocio.sheets import client as sheets_client
    from larkdocio.sheets import export_reader as export_mod

    def _install(export=None):
        opener = _Opener([_query_reply(), _values_reply()])
        monkeypatch.setattr(
            sheets_client.SheetsReadClient, "from_read_credentials",
            classmethod(lambda cls, domain="larksuite.com", **kw: cls(
                "id", "secret", urlopen=opener, token_fetcher=lambda *a, **k: "t")))
        if export is not None:
            monkeypatch.setattr(
                export_mod.SheetsExportReader, "from_read_credentials",
                classmethod(lambda cls, domain="larksuite.com", **kw: export))
        else:
            def _never(cls, domain="larksuite.com", **kw):
                raise AssertionError(
                    "the values-only read built an export reader — the opt-in leaked")
            monkeypatch.setattr(
                export_mod.SheetsExportReader, "from_read_credentials",
                classmethod(_never))
        return export

    return _install


# --------------------------------------------------------------------------- #
# AC2(a) + AC5 — the opt-in REACHES a standalone spreadsheet child.             #
# --------------------------------------------------------------------------- #

def test_the_fidelity_opt_in_REACHES_a_standalone_spreadsheet_and_discloses_its_fills(
        sheet_leg):
    """The defect this issue closes: the spreadsheet leg never had a fidelity argument, so a
    colour-encoded workbook read as blanks with nothing said. It now carries the same
    disclosure the embedded leg has carried since LD-331."""
    from larkdocio.drive import read as drive_read

    export = sheet_leg(_ExportCounter(workbook_bytes=_fill_workbook_bytes()))

    markdown, revision = drive_read._read_sheet_markdown(
        _SHEET_URL, fidelity_read_sheets=True)

    assert export.calls == ["SPREADSHEETTOKEN"], "one whole-workbook export, not one per cell"
    assert _BAR in markdown, "the recovered ARGB reaches the reader"
    assert "B2" in markdown, "against the cell that carries it"
    assert "Design" in markdown, "and the values table is unchanged"
    assert revision == 37


def test_read_child_PLUMBS_the_flag_to_the_spreadsheet_leg(sheet_leg):
    """``read_folder`` binds the three opt-ins into ``read_child``; the ``sheets`` arm dropped
    ``fidelity_read_sheets`` on the floor, so the flag could not reach a spreadsheet child even
    when the caller passed it."""
    from larkdocio.drive import read as drive_read

    sheet_leg(_ExportCounter(workbook_bytes=_fill_workbook_bytes()))

    produced = drive_read.read_child(
        "sheets", url=_SHEET_URL, token="SPREADSHEETTOKEN", fidelity_read_sheets=True)

    assert _BAR in produced.markdown


# --------------------------------------------------------------------------- #
# AC3 — OFF is byte-identical, and costs no export call.                        #
# --------------------------------------------------------------------------- #

def test_the_default_read_is_BYTE_IDENTICAL_and_issues_NO_export(sheet_leg):
    """The determinism promise: a caller who did not ask for fidelity gets exactly the bytes
    they always got, and not one extra API call. The fixture's export reader raises on
    construction, so a leak is a failure rather than a silent cost."""
    from larkdocio.drive import read as drive_read

    sheet_leg(None)
    default_md, _rev = drive_read._read_sheet_markdown(_SHEET_URL)

    sheet_leg(None)
    explicit_off_md, _rev2 = drive_read._read_sheet_markdown(
        _SHEET_URL, fidelity_read_sheets=False)

    assert default_md == explicit_off_md
    assert _BAR not in default_md
    assert "fill" not in default_md.lower(), (
        "the values-only render says nothing new — the disclosure is the opt-in's, not the "
        "default's")


# --------------------------------------------------------------------------- #
# AC5 — an unread fill layer is NOT an absent one.                              #
# --------------------------------------------------------------------------- #

def test_a_FAILED_export_DISCLOSES_the_gap_instead_of_reading_as_no_fills(sheet_leg):
    """The export is a whole second lifecycle (create → poll → download) and it can fail. When
    it does, the tab must SAY its fills could not be read — silence would make an unread fill
    layer look exactly like an absent one, which is the silence this issue exists to end."""
    from larkdocio.drive import read as drive_read

    sheet_leg(_ExportCounter(raises=LarkAPIError("export task failed: 1062506 too many tasks")))

    markdown, _rev = drive_read._read_sheet_markdown(
        _SHEET_URL, fidelity_read_sheets=True)

    assert "could not be read" in markdown
    assert "1062506" in markdown, "Lark's own words, not a paraphrase"
    assert "Design" in markdown, "and the values the read DID get are still delivered"


def test_a_tab_the_export_did_not_carry_says_so_per_tab(sheet_leg):
    """The export succeeded but named its worksheet something else — a gap, not a finding of
    'no fills'. ``exported_by_sheet_id`` omits the tab and the render's own sentinel discloses
    it."""
    from larkdocio.drive import read as drive_read
    from larkdocio.sheets.table import TAB_NOT_EXPORTED

    other = build_workbook([{"name": "Some other tab", "cells": [("A1", {"v": "1"})]},
                            {"name": "And another", "cells": [("A1", {"v": "2"})]}])
    sheet_leg(_ExportCounter(workbook_bytes=other))

    markdown, _rev = drive_read._read_sheet_markdown(
        _SHEET_URL, fidelity_read_sheets=True)

    assert TAB_NOT_EXPORTED in markdown


# --------------------------------------------------------------------------- #
# AC4 — a DISCLOSURE, never an interpretation.                                  #
# --------------------------------------------------------------------------- #

def test_the_disclosure_REPORTS_the_colour_and_CONCLUDES_nothing_about_it(sheet_leg):
    """What a colour MEANS is the consumer's semantics. The note carries the ARGB the export
    carries and no reading of it — no gantt, no status, no palette mapping."""
    from larkdocio.drive import read as drive_read

    sheet_leg(_ExportCounter(workbook_bytes=_fill_workbook_bytes()))
    markdown, _rev = drive_read._read_sheet_markdown(
        _SHEET_URL, fidelity_read_sheets=True)

    lowered = markdown.lower()
    for interpretation in ("gantt", "status", "milestone", "yellow", "in progress", "rag"):
        assert interpretation not in lowered, (
            f"the disclosure interpreted the colour ({interpretation!r})")


# --------------------------------------------------------------------------- #
# AC5/AC6 — the doc that recorded the gap must stop claiming it.                #
# --------------------------------------------------------------------------- #

def test_the_shipped_flag_text_no_longer_says_a_spreadsheet_CHILD_is_values_only(sheet_leg):
    """LD-384 wrote the gap into the CLI help, the flag descriptor and the guide in as many
    words. A closed gap whose docs still describe it is a consumer reading the truth of the
    previous release."""
    from larkdocio.capabilities._flag_descriptors import _flags
    from larkdocio.cli import cli
    from larkdocio.guide import guide

    summary = _flags()["fidelity_read_sheets"].summary
    assert "values-only either way" not in summary
    assert "spreadsheet" in summary.lower(), (
        "and it says what the flag now does for a spreadsheet child")

    help_text = cli.commands["folder"].get_help(
        __import__("click").Context(cli.commands["folder"]))
    assert "values-only either way" not in help_text

    assert "values-only either way" not in guide(full=True)
