"""LD-405 — the sheets walk's FRONT DOOR, and a result type that has a door at all.

Two defects with one root, both reported by a consumer's agent in round 5:

1. **No front door.** Every other read surface has a URL-first one-call — ``read_base`` /
   ``read_base_markdown`` (``larkdocio.base``), ``read_folder`` (``larkdocio.drive``). The
   whole-workbook walk had only a **method** on a client the caller had to build, fed a
   **token** the caller had to extract. The natural probe (``from larkdocio.sheets import
   walk``) hits a module, not a function.
2. **No door on the result.** ``SpreadsheetRead(client, "tok")`` — the consumer's exact
   mistake — was *accepted*, positionally and silently, by a frozen dataclass that takes
   anything; the failure surfaced three calls later as an ``AttributeError`` on ``.reads``.

The tightening is **fail-safe**: only already-wrong construction behaves differently, the
same direction as v1.32's mangled-link refusal. Everything here runs **offline** against the
live-captured payload shapes ``tests/test_sheets_ghost_tabs_skip_loudly.py`` already drives
(``tests/captures/ghost-tabs-probe/captures/01-ghost-vs-real.json``) with an injected client; the
credential path is tested by its **refusal**, never by reaching Lark.
"""
import json
from pathlib import Path

import pytest

from larkdocio.errors import LarkConfigError
from larkdocio.sheets.client import SheetsReadClient
from larkdocio.sheets.table import render_spreadsheet
from larkdocio.sheets.walk import (
    TAB_READ,
    TAB_SKIPPED,
    SpreadsheetRead,
    TabOutcome,
    TabSkip,
)

from write_harness import _FakeHTTPResponse

_CAPTURES = Path(__file__).resolve().parent.parent / "tests" / "captures" / "ghost-tabs-probe" / "captures"

URL = "https://your-domain.larksuite.com/sheets/SPREADSHEETTOKEN"


def _probe():
    return json.loads((_CAPTURES / "01-ghost-vs-real.json").read_text(encoding="utf-8"))


def _ghost_body():
    return _probe()["steps"][2]["response"]


def _tab_payload(sheet_id, title):
    payload = dict(_probe()["steps"][0]["response"]["data"]["sheets"][0])
    payload["sheet_id"] = sheet_id
    payload["title"] = title
    payload.pop("merges", None)
    return payload


def _query_reply(*ids_and_titles):
    return {"code": 0, "msg": "success",
            "data": {"sheets": [_tab_payload(sid, title)
                                for sid, title in ids_and_titles]}}


def _values_reply(sheet_id, values):
    return {"code": 0, "msg": "success", "data": {"revision": 37, "valueRange": {
        "range": f"{sheet_id}!A1:B2", "revision": 37, "values": values}}}


class QueuedOpener:
    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.urls = []

    def __call__(self, req, timeout=30):
        self.urls.append(req.full_url)
        return _FakeHTTPResponse(self._payloads.pop(0))


def _client(payloads):
    opener = QueuedOpener(payloads)
    client = SheetsReadClient("id", "secret", urlopen=opener,
                             token_fetcher=lambda *a, **k: "t-token")
    client.recorded_urls = opener.urls
    return client


def _one_tab_client():
    return _client([
        _query_reply(("444a1c", "Types")),
        _values_reply("444a1c", [["Name", "Qty"], ["Widget", 3]]),
    ])


def _no_credentials(monkeypatch):
    """Make ANY credential resolution loud, so 'refused before a credential' is provable."""
    def _boom(*a, **k):  # pragma: no cover - the point is that it is never reached
        raise AssertionError("a credential was resolved before the URL was refused")

    monkeypatch.setattr(SheetsReadClient, "from_read_credentials", classmethod(_boom))


# =========================================================================== #
# AC1 — a package-level, URL-FIRST convenience, twin of read_base.             #
# =========================================================================== #

@pytest.mark.conformance
def test_the_entry_point_is_importable_from_the_package_and_is_a_FUNCTION():
    """AC1/AC9. The consumer's natural probe must find a callable, not a module. This is the
    consumer's contract, so it is conformance-tier: a rewrite from the corpus must still
    export this name from this package."""
    from larkdocio.sheets import read_spreadsheet, read_spreadsheet_markdown
    import larkdocio.sheets as sheets

    assert callable(read_spreadsheet) and callable(read_spreadsheet_markdown)
    assert "read_spreadsheet" in sheets.__all__
    assert "read_spreadsheet_markdown" in sheets.__all__


@pytest.mark.conformance
def test_one_call_from_a_pasted_URL_to_a_SpreadsheetRead():
    """AC1. Hand it the thing a human copied out of their browser; get the walk back."""
    from larkdocio.sheets import read_spreadsheet

    wb = read_spreadsheet(URL, client=_one_tab_client())

    assert isinstance(wb, SpreadsheetRead)
    assert wb.spreadsheet_token == "SPREADSHEETTOKEN"
    assert [t.sheet_id for t, _used in wb.pairs] == ["444a1c"]
    assert wb.pairs[0][1].values == [["Name", "Qty"], ["Widget", 3]]
    assert wb.accounted()


def test_a_bare_token_is_accepted_exactly_as_read_base_accepts_one():
    """AC1. Not a third rule — ``read_base``'s: a bare alphanumeric token is the token."""
    from larkdocio.sheets import read_spreadsheet

    wb = read_spreadsheet("SPREADSHEETTOKEN", client=_one_tab_client())

    assert wb.spreadsheet_token == "SPREADSHEETTOKEN"


def test_a_partial_workbook_still_comes_back_through_the_one_call():
    """AC1. The one-call inherits the walk's skip-loudly whole, unweakened."""
    from larkdocio.sheets import read_spreadsheet

    wb = read_spreadsheet(URL, client=_client([
        _query_reply(("gh0st1", "Ghost A"), ("444a1c", "Types")),
        _ghost_body(),
        _values_reply("444a1c", [["ok"]]),
    ]))

    assert [o.kind for o in wb.outcomes] == [TAB_SKIPPED, TAB_READ]
    assert wb.skipped_any and wb.skips[0].skip.code == 90215
    assert wb.accounted()


def test_every_walk_option_passes_STRAIGHT_THROUGH_unchanged_in_name_and_meaning():
    """AC1 (D-52 — one grammar across every read verb). ``tabs`` avoids the second
    enumeration; the three render options reach the values call as themselves."""
    from larkdocio.sheets import read_spreadsheet

    client = _client([_values_reply("444a1c", [["ok"]])])   # NO query reply queued
    tabs = list(SheetsReadClient("id", "secret",
                                 urlopen=QueuedOpener([_query_reply(("444a1c", "Types"))]),
                                 token_fetcher=lambda *a, **k: "t").query_sheets("TOK"))

    wb = read_spreadsheet(
        URL,
        client=client,
        tabs=tabs,
        value_render_option="ToString",
        date_time_render_option="FormattedString",
        user_id_type="open_id",
    )

    assert [t.sheet_id for t, _u in wb.pairs] == ["444a1c"]
    url = client.recorded_urls[0]
    assert "valueRenderOption=ToString" in url
    assert "dateTimeRenderOption=FormattedString" in url
    assert "user_id_type=open_id" in url


# =========================================================================== #
# AC2 — a pasted URL works; a wrong one refuses BEFORE any credential.         #
# =========================================================================== #

@pytest.mark.conformance
def test_a_sheets_DEEP_LINK_a_consumer_would_actually_paste_parses():
    """AC2. The URL a human copies carries a tab (and often a cell) in its query."""
    from larkdocio.sheets import read_spreadsheet

    wb = read_spreadsheet(
        "https://your-domain.larksuite.com/sheets/SPREADSHEETTOKEN?sheet=444a1c",
        client=_one_tab_client())

    assert wb.spreadsheet_token == "SPREADSHEETTOKEN"


@pytest.mark.conformance
def test_a_MANGLED_token_region_refuses_WHOLE_and_before_any_credential(monkeypatch):
    """AC2 (LD-396 full-token-or-refuse, LD-397/D-57 the refusal the string alone can make).
    A truncated token looks exactly like a real one — so the URL is refused whole, and it is
    refused before a credential is read or a packet is sent."""
    from larkdocio.sheets import read_spreadsheet

    _no_credentials(monkeypatch)

    with pytest.raises(ValueError) as excinfo:
        read_spreadsheet("https://your-domain.larksuite.com/sheets/SPREAD-SHEET_TOKEN")

    assert "not a Lark token" in str(excinfo.value)


@pytest.mark.conformance
@pytest.mark.parametrize("url, named", [
    ("https://your-domain.larksuite.com/docx/DOCXTOKEN", "docx"),
    ("https://your-domain.larksuite.com/base/BASETOKEN", "base"),
    ("https://your-domain.larksuite.com/drive/folder/FOLDERTOKEN", "drive"),
])
def test_a_NON_SHEETS_url_refuses_by_NAMING_WHAT_IT_GOT(url, named, monkeypatch):
    """AC2. Recognising a URL is not the same as it naming a spreadsheet. The refusal says
    which type it actually is — a generic parse error would send the caller looking in the
    wrong place — and it costs no credential and no packet."""
    from larkdocio.sheets import read_spreadsheet

    _no_credentials(monkeypatch)

    with pytest.raises(LarkConfigError) as excinfo:
        read_spreadsheet(url)

    assert named in str(excinfo.value)


def test_a_blank_or_shapeless_argument_refuses_typed(monkeypatch):
    """AC2. ``read_base``'s own rule, matched: neither a URL nor a bare token is a
    ``LarkConfigError``, not an obscure failure deeper in."""
    from larkdocio.sheets import read_spreadsheet

    _no_credentials(monkeypatch)

    for bad in ("", "   ", "not a token", "tok/en", None):
        with pytest.raises(LarkConfigError):
            read_spreadsheet(bad)


# =========================================================================== #
# AC3 — the MARKDOWN twin.                                                     #
# =========================================================================== #

def test_the_markdown_twin_is_the_read_plus_render_spreadsheet_and_nothing_else():
    """AC3. ``read_base``'s pairing, mapped: the twin is exactly
    ``render_spreadsheet(wb.pairs, skips=wb.skips)`` over the same walk."""
    from larkdocio.sheets import read_spreadsheet, read_spreadsheet_markdown

    walked = read_spreadsheet(URL, client=_one_tab_client())
    expected = render_spreadsheet(walked.pairs, skips=walked.skips)

    assert read_spreadsheet_markdown(URL, client=_one_tab_client()) == expected


def test_the_markdown_twin_DISCLOSES_a_partial_read_rather_than_rendering_short():
    """AC3. The skips have an honest place in the flat string — which is why the twin maps
    cleanly here at all: ``render_spreadsheet`` already opens with the disclosure."""
    from larkdocio.sheets import read_spreadsheet_markdown

    markdown = read_spreadsheet_markdown(URL, client=_client([
        _query_reply(("gh0st1", "Ghost A"), ("444a1c", "Types")),
        _ghost_body(),
        _values_reply("444a1c", [["ok"]]),
    ]))

    assert "Ghost A" in markdown and "90215" in markdown


def test_the_markdown_twin_takes_heading_level_like_read_base_markdown_does():
    """AC3. Same convention as the Base twin — the one render knob that survives the
    projection travels with it."""
    from larkdocio.sheets import read_spreadsheet_markdown

    assert read_spreadsheet_markdown(
        URL, client=_one_tab_client(), heading_level=4).startswith("#### ")


# =========================================================================== #
# AC4 — the walk result dataclasses are KEYWORD-ONLY.                          #
# =========================================================================== #

@pytest.mark.conformance
def test_the_CONSUMERS_EXACT_MISTAKE_now_refuses_AT_THE_CONSTRUCTION_SITE():
    """AC4. ``SpreadsheetRead(client, "tok")`` — a client where a token belongs — used to be
    accepted silently and failed three calls later on ``.reads``. It is a ``TypeError`` here,
    now, at the line that made it."""
    client = _one_tab_client()

    with pytest.raises(TypeError):
        SpreadsheetRead(client, "SPREADSHEETTOKEN")


@pytest.mark.conformance
def test_all_three_walk_result_types_construct_by_KEYWORD_ONLY():
    """AC4. TabSkip / TabOutcome / SpreadsheetRead — positional construction is refused, and
    the keyword form is untouched."""
    with pytest.raises(TypeError):
        TabSkip("444a1c", "Types", 90215, "not found sheetId", "because")
    with pytest.raises(TypeError):
        TabOutcome(object(), TAB_READ)
    with pytest.raises(TypeError):
        SpreadsheetRead("SPREADSHEETTOKEN")

    assert TabSkip(sheet_id="444a1c", title="Types", code=90215,
                   msg="not found sheetId", reason="because").sheet_id == "444a1c"
    assert SpreadsheetRead(spreadsheet_token="TOK").outcomes == ()


# =========================================================================== #
# AC5 — outcomes is TYPE-CHECKED at construction, and the refusal is LOUD.     #
# =========================================================================== #

@pytest.mark.conformance
def test_outcomes_that_are_not_TabOutcomes_refuse_AT_CONSTRUCTION_naming_the_value():
    """AC5. Not at ``.reads``, three calls later — here, with the value named."""
    with pytest.raises(TypeError) as excinfo:
        SpreadsheetRead(spreadsheet_token="TOK", outcomes=("not-an-outcome",))

    message = str(excinfo.value)
    assert "outcomes" in message
    assert "TabOutcome" in message
    assert "'not-an-outcome'" in message and "str" in message
    assert "index 0" in message


def test_outcomes_that_are_not_a_SEQUENCE_at_all_refuse_at_construction():
    """AC5. A single ``TabOutcome`` passed where the tuple belongs, or any non-sequence."""
    for bad in (object(), 7, None):
        with pytest.raises(TypeError) as excinfo:
            SpreadsheetRead(spreadsheet_token="TOK", outcomes=bad)
        assert "outcomes" in str(excinfo.value)


def test_a_spreadsheet_token_that_is_not_a_string_refuses_at_construction():
    """AC5. The other half of the consumer's mistake: a client is not a token."""
    with pytest.raises(TypeError) as excinfo:
        SpreadsheetRead(spreadsheet_token=_one_tab_client())

    assert "spreadsheet_token" in str(excinfo.value)


@pytest.mark.conformance
def test_a_TabOutcome_whose_kind_and_payload_DISAGREE_refuses_at_construction():
    """AC5. ``accounted()``'s per-outcome half, enforced where it is cheap and honest: a
    ``read`` carries its used range, a ``skipped`` carries its skip, and neither carries the
    other's. An outcome that violated this used to make ``accounted()`` answer False long
    after the mistake was made."""
    tab = _one_tab_client().query_sheets("TOK")[0]
    skip = TabSkip(sheet_id=tab.sheet_id, title=tab.title, code=90215,
                   msg="not found sheetId", reason="because")

    with pytest.raises(TypeError) as excinfo:
        TabOutcome(tab=tab, kind=TAB_READ)               # a read with no used range
    assert "used" in str(excinfo.value)

    with pytest.raises(TypeError):
        TabOutcome(tab=tab, kind=TAB_SKIPPED)            # a skip with no disclosure
    with pytest.raises(TypeError):
        TabOutcome(tab=tab, kind=TAB_READ, skip=skip)    # a read carrying a skip
    with pytest.raises(ValueError):
        TabOutcome(tab=tab, kind="maybe", skip=skip)     # not one of the two kinds


def test_a_TabSkip_whose_fields_are_the_wrong_TYPE_refuses_at_construction():
    """AC5. The disclosure is Lark's own words about a tab; a non-string reason or a
    non-integer code is a construction mistake, named here."""
    with pytest.raises(TypeError) as excinfo:
        TabSkip(sheet_id=object(), title="Types", code=90215,
                msg="not found sheetId", reason="because")
    assert "sheet_id" in str(excinfo.value)

    with pytest.raises(TypeError):
        TabSkip(sheet_id="444a1c", title="Types", code="90215",
                msg="not found sheetId", reason="because")


# =========================================================================== #
# AC6 — a FAIL-SAFE tightening: only already-wrong construction moves.         #
# =========================================================================== #

def test_the_SHIPPED_walk_still_constructs_its_results_and_they_are_ACCOUNTED():
    """AC6. The client method — the library's own correct construction — is untouched by the
    tightening, in both the clean and the partial shape."""
    clean = SheetsReadClient(
        "id", "secret", urlopen=QueuedOpener([
            _query_reply(("444a1c", "Types")),
            _values_reply("444a1c", [["ok"]])]),
        token_fetcher=lambda *a, **k: "t").read_spreadsheet("TOK")
    partial = _client([
        _query_reply(("gh0st1", "Ghost A"), ("444a1c", "Types")),
        _ghost_body(),
        _values_reply("444a1c", [["ok"]]),
    ]).read_spreadsheet("TOK")

    assert clean.accounted() and partial.accounted()
    assert render_spreadsheet(partial.pairs, skips=partial.skips)
