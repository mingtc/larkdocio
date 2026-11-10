"""Opt-in embedded-sheet deep-read bridge (LD-105).

Upgrades the docx reader's ``handle_sheet`` (block type 30) to **optionally**
deep-read the embedded sheet: split the compound token on its **last** ``_`` into
``<spreadsheet_token>_<sheet_id>``, fetch/trim/render/assemble **only** the
referenced ``sheet_id`` tab (D3), and emit that Markdown table in place of the
placeholder — **only when the consumer opts in** via the ``deep_read_sheets`` flag.

The load-bearing invariants pinned here:

* **Default OFF ⇒ byte-identical, ZERO Sheets API calls** (D2/D8, AC1) — the
  traceable placeholder is emitted unchanged and the injected sheets client is
  NEVER touched (an "exploding" client proves no fetch is issued).
* **Compound-token split on the LAST ``_``** (spike Q6, AC2) — a token whose
  ``spreadsheet_token`` itself contains ``_`` still splits correctly; a
  malformed/absent token (no ``_``) **degrades to the placeholder, never raises**.
* **Only the referenced tab renders** (D3, AC3) — the sibling tabs of the
  underlying spreadsheet are never read nor rendered.
* **Determinism-safe & graceful** (D2, AC4) — ANY deep-read failure (API error,
  scope, unresolvable) falls back to the placeholder; a docx download NEVER fails
  because an embedded sheet could not be read.

Fixtures are the LD-100 opener spike's committed embed captures
(``tests/captures/sheets-spike/captures/05-embed-*.json``): the zoo specimen
``Example38428307171a2bd44d36_EQlPwA`` — a 2-tab spreadsheet whose referenced tab
is ``EQlPwA`` (a 2x3 tab) alongside a sibling ``Sheet1`` (``sheet_id=3ceb70``).
All offline (injected fake client); AC5's live deep-read rides ``pytest -m live``.
"""
import json
from pathlib import Path

from harness import build_blocks

from larkdocio.errors import LarkAPIError
from larkdocio.model import MarkdownRenderer, SheetNode
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.sheets.extent import UsedRange
from larkdocio.sheets.models import SheetTab

_CAPTURES = Path(__file__).resolve().parent.parent / "tests" / "captures" / "sheets-spike" / "captures"

ZOO_COMPOUND_TOKEN = "Example38428307171a2bd44d36_EQlPwA"

SHEET_MARKER = (
    "> 📊 **Embedded Sheet** — not fetched. token: `Example38428307171a2bd44d36_EQlPwA`. "
    "The spreadsheet's cells live in a separate Sheet document; deep read is "
    "out of scope.\n"
)


def _capture(name):
    return json.loads((_CAPTURES / name).read_text(encoding="utf-8"))


def _embed_tabs():
    return [SheetTab.from_dict(s) for s in _capture("05-embed-tabs.json")["data"]["sheets"]]


def _embed_values():
    return _capture("05-embed-values.json")["data"]["valueRange"]["values"]


class FakeSheetsClient:
    """A stand-in for :class:`~larkdocio.sheets.client.SheetsReadClient` exposing the
    two methods the bridge calls (``query_sheets`` + ``read_used_range``), recording
    each call so a test can prove ONLY the referenced tab is read."""

    def __init__(self, tabs, values_by_sheet_id, *, fail=False):
        self._tabs = tabs
        self._values = values_by_sheet_id
        self.fail = fail
        self.query_calls = []
        self.read_calls = []

    def query_sheets(self, spreadsheet_token):
        self.query_calls.append(spreadsheet_token)
        if self.fail:
            raise LarkAPIError("simulated tab-query failure")
        return self._tabs

    def read_used_range(self, spreadsheet_token, tab, **kwargs):
        self.read_calls.append(tab.sheet_id)
        if self.fail:
            raise LarkAPIError("simulated values-read failure")
        return UsedRange.from_tab_values(tab, self._values[tab.sheet_id])


class ExplodingSheetsClient:
    """A client whose every method raises — so a test can prove that with the flag
    OFF the handler issues NO Sheets API call (AC1)."""

    def query_sheets(self, *a, **k):
        raise AssertionError("query_sheets called while deep-read OFF — a fetch was issued")

    def read_used_range(self, *a, **k):
        raise AssertionError("read_used_range called while deep-read OFF — a fetch was issued")


def _zoo_fake(**kwargs):
    return FakeSheetsClient(_embed_tabs(), {"EQlPwA": _embed_values()}, **kwargs)


def _block(token="Example38428307171a2bd44d36_EQlPwA"):
    return build_blocks(
        [{"block_id": "sh", "block_type": 30,
          "sheet": {"token": token, "row_size": None, "column_size": None}}]
    )[0]


def _r():
    return MarkdownRenderer()


# --------------------------------------------------------------------------- #
# AC1 — Opt-in flag; default OFF ⇒ placeholder unchanged + ZERO Sheets fetch   #
# --------------------------------------------------------------------------- #

def test_deep_read_off_by_default_emits_placeholder():
    from larkdocio.blocks.embedded import handle_sheet

    node = handle_sheet(Parser(Config()), _block(), 0)
    assert isinstance(node, SheetNode)
    assert node.token == ZOO_COMPOUND_TOKEN
    assert node.deep_read_markdown is None
    assert _r().render(node) == SHEET_MARKER


def test_deep_read_off_issues_no_sheet_fetch_even_with_client_present():
    # Flag OFF but a client IS supplied: the handler must NOT touch it. An
    # exploding client turns any fetch into an AssertionError.
    from larkdocio.blocks.embedded import handle_sheet

    parser = Parser(Config(), deep_read_sheets=False, sheets_client=ExplodingSheetsClient())
    node = handle_sheet(parser, _block(), 0)  # no AssertionError ⇒ no fetch issued
    assert node.deep_read_markdown is None
    assert _r().render(node) == SHEET_MARKER


def test_deep_read_on_but_no_client_emits_placeholder():
    # Flag ON but NO client ⇒ nothing to fetch with ⇒ placeholder, no raise.
    from larkdocio.blocks.embedded import handle_sheet

    parser = Parser(Config(), deep_read_sheets=True, sheets_client=None)
    node = handle_sheet(parser, _block(), 0)
    assert node.deep_read_markdown is None
    assert _r().render(node) == SHEET_MARKER


# --------------------------------------------------------------------------- #
# AC2 — compound-token split on the LAST underscore; malformed ⇒ degrade       #
# --------------------------------------------------------------------------- #

def test_split_compound_token_on_last_underscore():
    from larkdocio.sheets.embed import split_compound_token

    assert split_compound_token(ZOO_COMPOUND_TOKEN) == (
        "Example38428307171a2bd44d36", "EQlPwA"
    )


def test_split_compound_token_spreadsheet_part_may_itself_contain_underscores():
    # The spreadsheet_token itself may carry '_' — only the LAST '_' is the split.
    from larkdocio.sheets.embed import split_compound_token

    assert split_compound_token("spread_sheet_tok_SHEETID") == (
        "spread_sheet_tok", "SHEETID"
    )


def test_split_compound_token_malformed_returns_none():
    from larkdocio.sheets.embed import split_compound_token

    assert split_compound_token("noUnderscoreHere") is None    # no '_'
    assert split_compound_token("_trailingsheetonly") is None  # empty spreadsheet_token
    assert split_compound_token("trailingunderscore_") is None  # empty sheet_id
    assert split_compound_token("_") is None                     # both empty
    assert split_compound_token("") is None
    assert split_compound_token(None) is None


def test_malformed_token_degrades_to_placeholder_and_never_fetches():
    # Flag ON, client present, but the token has no '_': the split fails BEFORE any
    # fetch, so the client is never touched and the placeholder is emitted.
    from larkdocio.blocks.embedded import handle_sheet

    client = _zoo_fake()
    b = build_blocks(
        [{"block_id": "sh", "block_type": 30,
          "sheet": {"token": "noUnderscoreToken", "row_size": None, "column_size": None}}]
    )[0]
    parser = Parser(Config(), deep_read_sheets=True, sheets_client=client)
    node = handle_sheet(parser, b, 0)
    assert node.deep_read_markdown is None
    assert client.query_calls == [] and client.read_calls == []
    # token-only placeholder still emitted (never raises)
    assert "Embedded Sheet" in _r().render(node)


# --------------------------------------------------------------------------- #
# AC3 — deep-read renders ONLY the referenced sheet_id tab (D3)                #
# --------------------------------------------------------------------------- #

def test_deep_read_renders_only_the_referenced_tab():
    from larkdocio.blocks.embedded import handle_sheet

    client = _zoo_fake()
    parser = Parser(Config(), deep_read_sheets=True, sheets_client=client)
    node = handle_sheet(parser, _block(), 0)

    md = node.deep_read_markdown
    assert md is not None
    # The referenced tab (EQlPwA) rendered, with its data.
    assert "## EQlPwA" in md
    assert "| A1 header | B1 header | C1 header |" in md
    assert "| A2 data | B2 data | C2 data |" in md
    # The SIBLING tab is NEITHER read NOR rendered (D3).
    assert "Sheet1" not in md
    assert "3ceb70" not in md
    assert client.read_calls == ["EQlPwA"], (
        "deep-read must read ONLY the referenced tab, not sibling tabs"
    )
    # Block-separation newline (parity with the placeholder's trailing '\n').
    assert md.endswith("\n")


def test_deep_read_missing_referenced_tab_degrades_to_placeholder():
    # The compound token names a sheet_id that is NOT among the spreadsheet's tabs.
    from larkdocio.blocks.embedded import handle_sheet

    client = _zoo_fake()
    b = _block(token="Example38428307171a2bd44d36_NOSUCHTAB")
    parser = Parser(Config(), deep_read_sheets=True, sheets_client=client)
    node = handle_sheet(parser, b, 0)
    assert node.deep_read_markdown is None
    # It queried the tabs, found none matching, then degraded WITHOUT a values read.
    assert client.read_calls == []


def test_deep_read_renders_through_the_parser_end_to_end():
    # A whole-document parse with the flag ON substitutes the table for the marker.
    blocks = [
        {"block_id": "root", "parent_id": "doc", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "Doc Title"}}]},
         "children": ["sh"]},
        {"block_id": "sh", "parent_id": "root", "block_type": 30,
         "sheet": {"token": ZOO_COMPOUND_TOKEN, "row_size": None, "column_size": None}},
    ]
    sdk_blocks = build_blocks(blocks)
    parser = Parser(Config(), deep_read_sheets=True, sheets_client=_zoo_fake())
    out = parser.parse_docx_content("root", sdk_blocks)
    assert "## EQlPwA" in out
    assert "| A1 header | B1 header | C1 header |" in out
    assert "Embedded Sheet" not in out   # the placeholder was replaced


# --------------------------------------------------------------------------- #
# AC4 — determinism-safe & graceful: ANY failure ⇒ placeholder, never raises   #
# --------------------------------------------------------------------------- #

def test_deep_read_fetch_error_falls_back_to_placeholder():
    from larkdocio.blocks.embedded import handle_sheet

    client = _zoo_fake(fail=True)   # query_sheets raises
    parser = Parser(Config(), deep_read_sheets=True, sheets_client=client)
    node = handle_sheet(parser, _block(), 0)   # must NOT raise
    assert node.deep_read_markdown is None
    assert _r().render(node) == SHEET_MARKER


def test_deep_read_values_error_falls_back_to_placeholder():
    # query_sheets succeeds, then read_used_range raises — still graceful.
    from larkdocio.blocks.embedded import handle_sheet

    class _ValuesFail(FakeSheetsClient):
        def read_used_range(self, spreadsheet_token, tab, **kwargs):
            self.read_calls.append(tab.sheet_id)
            raise LarkAPIError("simulated values failure")

    client = _ValuesFail(_embed_tabs(), {"EQlPwA": _embed_values()})
    parser = Parser(Config(), deep_read_sheets=True, sheets_client=client)
    node = handle_sheet(parser, _block(), 0)
    assert node.deep_read_markdown is None
    assert client.query_calls and client.read_calls == ["EQlPwA"]


def test_docx_download_never_fails_because_deep_read_failed():
    # End-to-end: a failing deep-read must not break the whole-document render.
    blocks = [
        {"block_id": "root", "parent_id": "doc", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "Doc Title"}}]},
         "children": ["sh"]},
        {"block_id": "sh", "parent_id": "root", "block_type": 30,
         "sheet": {"token": ZOO_COMPOUND_TOKEN, "row_size": None, "column_size": None}},
    ]
    sdk_blocks = build_blocks(blocks)
    parser = Parser(Config(), deep_read_sheets=True, sheets_client=_zoo_fake(fail=True))
    out = parser.parse_docx_content("root", sdk_blocks)   # must NOT raise
    assert "Embedded Sheet" in out   # degraded to the placeholder marker


# --------------------------------------------------------------------------- #
# The bridge helper directly + the renderer's deep_read_markdown pass-through  #
# --------------------------------------------------------------------------- #

def test_bridge_returns_none_on_malformed_token():
    from larkdocio.sheets.embed import deep_read_embedded_sheet

    assert deep_read_embedded_sheet(_zoo_fake(), "noUnderscore") is None


def test_bridge_renders_referenced_tab_markdown():
    from larkdocio.sheets.embed import deep_read_embedded_sheet

    md = deep_read_embedded_sheet(_zoo_fake(), ZOO_COMPOUND_TOKEN)
    assert md.startswith("## EQlPwA\n\n")
    assert md.endswith("\n")


def test_sheet_renderer_emits_deep_read_markdown_when_present():
    node = SheetNode(token="X", deep_read_markdown="## T\n\n| a |\n|---|\n| b |\n")
    assert _r().render(node) == "## T\n\n| a |\n|---|\n| b |\n"


def test_sheet_renderer_placeholder_unchanged_when_deep_read_none():
    # The default-path byte-identity guard at the node/renderer boundary.
    assert _r().render(SheetNode(token="TOK30")) == (
        "> 📊 **Embedded Sheet** — not fetched. token: `TOK30`. "
        "The spreadsheet's cells live in a separate Sheet document; deep read is "
        "out of scope.\n"
    )


def test_parser_exposes_deep_read_attributes_with_safe_defaults():
    # A default Parser is OFF with no client (byte-identical default path).
    p = Parser(Config())
    assert p.deep_read_sheets is False
    assert p.sheets_client is None


# --------------------------------------------------------------------------- #
# LD-117 gain (a) — OPT-IN fidelity-read flag: cell-level bold/italic → MD     #
# emphasis, gated behind fidelity_read_sheets (mirror of deep_read_sheets).    #
# Flag OFF (default): NO export call is issued (transport spy) and the render  #
# is byte-identical to the values-only deep read. Flag ON: the READ-creds      #
# export runs and whole-cell emphasis renders. Export runs on READ creds       #
# (D1, scope PROVEN); flag naming mirrors deep_read_sheets (Dev's call).       #
# --------------------------------------------------------------------------- #
from larkdocio.sheets.export_reader import (  # noqa: E402
    ExportedCell,
    ExportedSheet,
    ParsedWorkbook,
)


def _exported_workbook_bold_headers():
    """A parsed workbook whose referenced tab (EQlPwA) marks its A1:C1 header row
    bold — the export-only fidelity the values API cannot see."""
    cells = {ref: ExportedCell(ref=ref, value=None, bold=True) for ref in ("A1", "B1", "C1")}
    return ParsedWorkbook(sheets=(ExportedSheet(name="EQlPwA", cells=cells),))


class RecordingExportReader:
    """A stand-in export reader recording each ``read_workbook`` — so a test can
    prove the flag-ON path issues exactly one export, and (with ``fail``) that an
    export failure degrades gracefully."""

    def __init__(self, workbook=None, *, fail=False):
        self._workbook = workbook
        self.fail = fail
        self.workbook_calls = []

    def read_workbook(self, spreadsheet_token):
        self.workbook_calls.append(spreadsheet_token)
        if self.fail:
            raise LarkAPIError("simulated export failure")
        return self._workbook


class ExplodingExportReader:
    """An export reader whose every call raises — so a test proves that with the
    fidelity flag OFF NO export is issued (the zero-export transport spy)."""

    def read_workbook(self, *a, **k):
        raise AssertionError("read_workbook called while fidelity-read OFF — an export was issued")


def test_parser_exposes_fidelity_read_attributes_with_safe_defaults():
    p = Parser(Config())
    assert p.fidelity_read_sheets is False
    assert p.sheets_export_reader is None


def test_fidelity_read_off_issues_no_export_even_with_reader_present():
    # deep-read ON (so a table renders) but fidelity OFF + an EXPLODING export
    # reader present: no export call is issued (the exploding reader would raise),
    # and the table is byte-identical to the values-only deep read (no emphasis).
    from larkdocio.blocks.embedded import handle_sheet

    parser = Parser(
        Config(),
        deep_read_sheets=True,
        sheets_client=_zoo_fake(),
        fidelity_read_sheets=False,
        sheets_export_reader=ExplodingExportReader(),
    )
    node = handle_sheet(parser, _block(), 0)  # no AssertionError ⇒ no export issued
    md = node.deep_read_markdown
    assert md is not None
    assert "**" not in md            # no cell emphasis
    assert "| A1 header | B1 header | C1 header |" in md   # values-only headers


def test_fidelity_read_on_applies_cell_emphasis_from_export():
    from larkdocio.blocks.embedded import handle_sheet

    reader = RecordingExportReader(_exported_workbook_bold_headers())
    parser = Parser(
        Config(),
        deep_read_sheets=True,
        sheets_client=_zoo_fake(),
        fidelity_read_sheets=True,
        sheets_export_reader=reader,
    )
    node = handle_sheet(parser, _block(), 0)
    md = node.deep_read_markdown
    assert md is not None
    # The export-only bold header row now renders emphasised.
    assert "| **A1 header** | **B1 header** | **C1 header** |" in md
    # The (non-bold) data row is unchanged.
    assert "| A2 data | B2 data | C2 data |" in md
    # Exactly one export was issued, on the referenced spreadsheet_token.
    assert reader.workbook_calls == ["Example38428307171a2bd44d36"]


def test_fidelity_read_on_export_failure_degrades_to_values_only():
    # The export leg fails, but the deep-read still succeeds values-only (never
    # raises, never falls all the way back to the placeholder).
    from larkdocio.blocks.embedded import handle_sheet

    reader = RecordingExportReader(fail=True)
    parser = Parser(
        Config(),
        deep_read_sheets=True,
        sheets_client=_zoo_fake(),
        fidelity_read_sheets=True,
        sheets_export_reader=reader,
    )
    node = handle_sheet(parser, _block(), 0)
    md = node.deep_read_markdown
    assert md is not None
    assert "**" not in md
    assert "| A1 header | B1 header | C1 header |" in md
    assert reader.workbook_calls == ["Example38428307171a2bd44d36"]  # it tried once


def test_bridge_fidelity_read_off_never_touches_export_reader():
    from larkdocio.sheets.embed import deep_read_embedded_sheet

    md = deep_read_embedded_sheet(
        _zoo_fake(), ZOO_COMPOUND_TOKEN,
        fidelity_read=False, export_reader=ExplodingExportReader(),
    )
    assert md is not None and "**" not in md


def test_bridge_fidelity_read_on_emphasises_referenced_tab():
    from larkdocio.sheets.embed import deep_read_embedded_sheet

    reader = RecordingExportReader(_exported_workbook_bold_headers())
    md = deep_read_embedded_sheet(
        _zoo_fake(), ZOO_COMPOUND_TOKEN,
        fidelity_read=True, export_reader=reader,
    )
    assert "| **A1 header** | **B1 header** | **C1 header** |" in md
    assert reader.workbook_calls == ["Example38428307171a2bd44d36"]
