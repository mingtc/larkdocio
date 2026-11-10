"""GHOST TABS — a tab the API listed and then denies exists must not kill the workbook read
(LD-383, consumer priority #3, Major).

The defect
----------
``query_sheets`` enumerated 22 tabs of the consumer's workbook; ``read_used_range`` answered
**`90215 not found sheetId`** for 20 of them, and because the walk was a bare list
comprehension the FIRST ghost ended it — so a consumer with 20 ghosts and 2 readable tabs got
**nothing**, including the two tabs that read perfectly. The data a caller can have was withheld
because of data they cannot.

The fix is the folder reader's **skip-loudly** (`larkdocio.drive.read`), applied one surface
over: a per-tab miss is disclosed with **Lark's own code and msg**, and the walk continues.

What is REAL here and what is not
---------------------------------
The ``90215`` body every test below drives is the **live one**, read off
``tests/captures/ghost-tabs-probe/captures/01-ghost-vs-real.json`` (a read-only probe against the
disposable ``LARKDOCIO_SCRATCH_SHEET``: a values read of a sheet id the same workbook's
``sheets/query`` never listed → ``{"code": 90215, "msg": "not found sheetId", "data": {}}``,
byte-for-byte the consumer's report). A **ghost's own enumeration payload is UNMEASURED** — a
ghost could not be manufactured on a disposable (`dev/ghost-tabs-probe/findings.md`), so the
ghost tabs below carry a *real* tab's payload shape with an id the values leg refuses. That is
the honest edge of the evidence: the refusal is real, the ghost's listing is a stand-in.
"""
import json
from pathlib import Path

import pytest

from larkdocio.errors import (
    LarkAPIError,
    LarkPermissionError,
    LarkRateLimitError,
    LarkSpreadsheetUnreadableError,
)
from larkdocio.sheets.client import SheetsReadClient
from larkdocio.sheets.table import render_spreadsheet
from larkdocio.sheets.walk import TAB_READ, TAB_SKIPPED, SpreadsheetRead

from write_harness import _FakeHTTPResponse

_CAPTURES = Path(__file__).resolve().parent.parent / "tests" / "captures" / "ghost-tabs-probe" / "captures"


def _probe():
    return json.loads((_CAPTURES / "01-ghost-vs-real.json").read_text(encoding="utf-8"))


def _ghost_body():
    """Lark's OWN refusal body for a sheet id the values leg does not accept — live-captured."""
    return _probe()["steps"][2]["response"]


def _real_tab_payload():
    """One real tab's ``sheets/query`` entry, live-captured (grid_properties, resource_type…)."""
    return _probe()["steps"][0]["response"]["data"]["sheets"][0]


def _tab_payload(sheet_id, title):
    payload = dict(_real_tab_payload())
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
    """Serves the queued payloads in order and records the paths asked for."""

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.urls = []

    def __call__(self, req, timeout=30):
        self.urls.append(req.full_url)
        return _FakeHTTPResponse(self._payloads.pop(0))


def _client(payloads):
    return SheetsReadClient("id", "secret", urlopen=QueuedOpener(payloads),
                            token_fetcher=lambda *a, **k: "t-token")


# --------------------------------------------------------------------------- #
# AC1 — the walk COMPLETES; every readable tab is still read.                  #
# --------------------------------------------------------------------------- #

def test_a_ghost_tab_does_not_end_the_walk_and_every_readable_tab_is_still_read():
    """AC1. The consumer's shape in miniature — ghost, real, ghost. The read completes and
    yields THE READABLE TAB, which is precisely what the crash withheld."""
    client = _client([
        _query_reply(("gh0st1", "Ghost A"), ("444a1c", "Types"), ("gh0st2", "Ghost B")),
        _ghost_body(),
        _values_reply("444a1c", [["Name", "Qty"], ["Widget", 3]]),
        _ghost_body(),
    ])

    wb = client.read_spreadsheet("SPREADSHEETTOKEN")

    assert [o.kind for o in wb.outcomes] == [TAB_SKIPPED, TAB_READ, TAB_SKIPPED]
    assert [t.sheet_id for t, _used in wb.pairs] == ["444a1c"]
    assert wb.pairs[0][1].values == [["Name", "Qty"], ["Widget", 3]]
    assert wb.accounted(), "every enumerated tab must appear exactly once as a read or a skip"


def test_the_walk_asks_for_every_tab_even_after_a_ghost_refuses():
    """AC1. Not just "the result has one row" — the client actually issued the later reads."""
    opener = QueuedOpener([
        _query_reply(("gh0st1", "Ghost A"), ("444a1c", "Types")),
        _ghost_body(),
        _values_reply("444a1c", [["ok"]]),
    ])
    client = SheetsReadClient("id", "secret", urlopen=opener,
                             token_fetcher=lambda *a, **k: "t-token")

    client.read_spreadsheet("SPREADSHEETTOKEN")

    assert any("gh0st1" in u for u in opener.urls)
    assert any("444a1c" in u for u in opener.urls)


# --------------------------------------------------------------------------- #
# AC2 — the skip carries LARK'S OWN error, verbatim.                           #
# --------------------------------------------------------------------------- #

def test_the_skip_carries_LARKS_OWN_code_and_msg_verbatim():
    """AC2. Code and message unedited, attached to the tab they belong to — not a paraphrase,
    not a generic "tab unreadable"."""
    body = _ghost_body()
    client = _client([
        _query_reply(("gh0st1", "Ghost A"), ("444a1c", "Types")),
        body,
        _values_reply("444a1c", [["ok"]]),
    ])

    skip = client.read_spreadsheet("SPREADSHEETTOKEN").skips[0].skip

    assert skip.code == body["code"] == 90215
    assert skip.msg == body["msg"] == "not found sheetId"
    assert skip.sheet_id == "gh0st1" and skip.title == "Ghost A"


def test_the_disclosure_QUOTES_lark_rather_than_diagnosing_the_cause():
    """AC2/AC6. The reason sentence may frame the miss, but the cause is never invented —
    larkdocio has not measured what a ghost IS, so nothing here may claim to know."""
    client = _client([
        _query_reply(("gh0st1", "Ghost A"), ("444a1c", "Types")),
        _ghost_body(),
        _values_reply("444a1c", [["ok"]]),
    ])

    reason = client.read_spreadsheet("SPREADSHEETTOKEN").skips[0].skip.reason

    assert "90215" in reason and "not found sheetId" in reason
    assert not any(w in reason.lower() for w in ("because", "deleted", "corrupt"))


# --------------------------------------------------------------------------- #
# AC3 — the skip is LOUD, and the OUTPUT says so.                              #
# --------------------------------------------------------------------------- #

def test_the_skips_are_in_the_RETURNED_STRUCTURE_not_only_in_a_log_line():
    """AC3. A caller reading the result can tell that tabs were skipped and which — without
    having captured a log."""
    client = _client([
        _query_reply(("gh0st1", "Ghost A"), ("444a1c", "Types")),
        _ghost_body(),
        _values_reply("444a1c", [["ok"]]),
    ])

    wb = client.read_spreadsheet("SPREADSHEETTOKEN")

    assert isinstance(wb, SpreadsheetRead)
    assert wb.skipped_any is True
    assert [o.tab.sheet_id for o in wb.skips] == ["gh0st1"]
    assert wb.spreadsheet_token == "SPREADSHEETTOKEN"


def test_the_RENDERED_MARKDOWN_declares_the_skipped_tabs_too():
    """AC3. The Markdown projection is where most consumers meet the read — a silently short
    document would be the worse bug this issue exists to refuse."""
    client = _client([
        _query_reply(("gh0st1", "Ghost A"), ("444a1c", "Types")),
        _ghost_body(),
        _values_reply("444a1c", [["Name", "Qty"], ["Widget", 3]]),
    ])
    wb = client.read_spreadsheet("SPREADSHEETTOKEN")

    markdown = render_spreadsheet(wb.pairs, skips=wb.skips)

    assert "1 of 2" in markdown
    assert "Ghost A" in markdown and "gh0st1" in markdown
    assert "90215" in markdown and "not found sheetId" in markdown
    assert "Widget" in markdown, "the readable tab is still rendered in full"


def test_render_spreadsheet_WITHOUT_skips_is_byte_identical_to_before():
    """Zero-drift: the disclosure is additive. No skips (the default) ⇒ not one byte moves,
    so every shipped golden stands unchanged."""
    client = _client([
        _query_reply(("444a1c", "Types")),
        _values_reply("444a1c", [["Name", "Qty"], ["Widget", 3]]),
    ])
    wb = client.read_spreadsheet("SPREADSHEETTOKEN")

    assert render_spreadsheet(wb.pairs, skips=()) == render_spreadsheet(wb.pairs)
    assert render_spreadsheet(wb.pairs, skips=wb.skips) == render_spreadsheet(wb.pairs)


# --------------------------------------------------------------------------- #
# AC4 — a TOTAL failure is still a failure.                                    #
# --------------------------------------------------------------------------- #

def test_ALL_tabs_skipped_RAISES_rather_than_returning_a_cheerful_empty_workbook():
    """AC4. The boundary Dev chose: **100 % skipped is a raise**, not an empty success. A
    caller that reads nothing must not be able to mistake it for a workbook that holds
    nothing — and the raise carries every disclosure so the caller loses no evidence."""
    client = _client([
        _query_reply(("gh0st1", "Ghost A"), ("gh0st2", "Ghost B")),
        _ghost_body(),
        _ghost_body(),
    ])

    with pytest.raises(LarkSpreadsheetUnreadableError) as excinfo:
        client.read_spreadsheet("SPREADSHEETTOKEN")

    err = excinfo.value
    assert isinstance(err, LarkAPIError), "an existing `except LarkAPIError` must still catch it"
    assert err.code == 90215 and err.msg == "not found sheetId"
    assert [s.sheet_id for s in err.skips] == ["gh0st1", "gh0st2"]
    assert "2 of 2" in str(err)


def test_a_workbook_that_ENUMERATES_NO_TABS_is_not_an_all_skipped_failure():
    """AC4's boundary from the other side: zero tabs is Lark's honest answer about an empty
    workbook, not "everything failed". 0 of 0 skipped must not raise."""
    client = _client([{"code": 0, "msg": "success", "data": {"sheets": []}}])

    wb = client.read_spreadsheet("SPREADSHEETTOKEN")

    assert wb.outcomes == () and wb.pairs == [] and wb.skipped_any is False


# --------------------------------------------------------------------------- #
# AC8 — no OTHER error class is swallowed.                                     #
# --------------------------------------------------------------------------- #

def test_a_RATE_LIMIT_on_a_tab_read_still_fails_the_whole_read():
    """AC8. A 99991400 is not a fact about the tab — skipping it would turn a throttle into a
    permanently short document."""
    client = _client([
        _query_reply(("444a1c", "Types"), ("7pg9wE", "Merges")),
        {"code": 99991400, "msg": "too many request", "data": {}},
    ])

    with pytest.raises(LarkRateLimitError):
        client.read_spreadsheet("SPREADSHEETTOKEN")


def test_a_SCOPE_DENIAL_on_a_tab_read_still_fails_the_whole_read():
    """AC8. A denial says *I could not look*, which is never *this tab is unreadable* — the
    same posture as the sheets scope-denial batch halt."""
    denial = json.loads(
        (Path(__file__).resolve().parent.parent / "tests" / "captures" / "permissions-preflight-probe"
         / "captures" / "Q12-group-bogus-READ.json").read_text(encoding="utf-8"))["response"]
    client = _client([_query_reply(("444a1c", "Types"), ("7pg9wE", "Merges")), denial])

    with pytest.raises(LarkPermissionError):
        client.read_spreadsheet("SPREADSHEETTOKEN")


def test_a_TRANSPORT_failure_on_a_tab_read_still_fails_the_whole_read():
    """AC8. An error carrying NO Lark code is not Lark's answer about this tab; the skip needs
    Lark's own verdict, so a codeless failure propagates."""
    class Boom:
        def __init__(self, payloads):
            self._payloads = list(payloads)

        def __call__(self, req, timeout=30):
            if self._payloads:
                return _FakeHTTPResponse(self._payloads.pop(0))
            raise LarkAPIError("GET /open-apis/... failed: <urlopen error timed out>")

    client = SheetsReadClient(
        "id", "secret",
        urlopen=Boom([_query_reply(("444a1c", "Types"), ("7pg9wE", "Merges"))]),
        token_fetcher=lambda *a, **k: "t-token")

    with pytest.raises(LarkAPIError) as excinfo:
        client.read_spreadsheet("SPREADSHEETTOKEN")
    assert excinfo.value.code is None
    assert not isinstance(excinfo.value, LarkSpreadsheetUnreadableError)


def test_a_WORKBOOK_LEVEL_enumeration_failure_still_fails_the_whole_read():
    """AC8. The skip is per-TAB. If the enumeration itself is refused there is no walk to
    continue, and nothing may pretend there was one."""
    client = _client([{"code": 1310213, "msg": "spreadsheet not found", "data": {}}])

    with pytest.raises(LarkAPIError) as excinfo:
        client.read_spreadsheet("SPREADSHEETTOKEN")
    assert excinfo.value.code == 1310213


# --------------------------------------------------------------------------- #
# The shipped WALK sites use it — a fix nobody's code path reaches is no fix.   #
# --------------------------------------------------------------------------- #

def test_the_FOLDER_readers_sheet_leg_skips_loudly_and_says_so_in_its_markdown(monkeypatch):
    """The folder walk's ``sheets`` child was the shipped list comprehension — the very shape
    that died on the first ghost. It now walks with ``read_spreadsheet`` and carries the
    disclosure into the Markdown it hands the folder read."""
    from larkdocio.drive import read as drive_read
    from larkdocio.sheets import client as sheets_client

    opener = QueuedOpener([
        _query_reply(("gh0st1", "Ghost A"), ("444a1c", "Types")),
        _ghost_body(),
        _values_reply("444a1c", [["Name", "Qty"], ["Widget", 3]]),
    ])
    monkeypatch.setattr(
        sheets_client.SheetsReadClient, "from_read_credentials",
        classmethod(lambda cls, domain="larksuite.com", **kw: cls(
            "id", "secret", urlopen=opener, token_fetcher=lambda *a, **k: "t")))

    markdown, revision = drive_read._read_sheet_markdown(
        "https://x.larksuite.com/sheets/SPREADSHEETTOKEN")

    assert "Widget" in markdown, "the readable tab still reaches the folder read"
    assert "gh0st1" in markdown and "90215" in markdown, "and the miss is disclosed, loudly"
    assert revision == 37


# --------------------------------------------------------------------------- #
# The caller-supplied tab set (what the live gate drives).                      #
# --------------------------------------------------------------------------- #

def test_a_caller_that_already_enumerated_can_pass_its_own_tabs_and_pays_no_second_query():
    """``tabs=`` is the ``read_tabs_frozen`` precedent: a caller holding the tab set should
    not pay to enumerate twice — and it is how the live gate mixes a real tab with a refused
    one against the real API."""
    opener = QueuedOpener([_values_reply("444a1c", [["ok"]])])
    client = SheetsReadClient("id", "secret", urlopen=opener,
                              token_fetcher=lambda *a, **k: "t-token")
    from larkdocio.sheets.models import SheetTab

    tab = SheetTab.from_dict(_tab_payload("444a1c", "Types"))
    wb = client.read_spreadsheet("SPREADSHEETTOKEN", tabs=[tab])

    assert [o.kind for o in wb.outcomes] == [TAB_READ]
    assert not any("sheets/query" in u for u in opener.urls)
