"""A TAB'S VISIBILITY ON THE READ ROUTE — ``SheetTab.hidden`` (LD-477).

What this pins, and why each half is here
-----------------------------------------
The v3 tab query has always answered ``hidden`` on **every** ``sheets[]`` element, and the
read model dropped it in projection: sixteen fields, none of them visibility. So a read-only
reporting job could not tell a hidden scratch tab from a live one, and the only shipped way to
ask was the **write** client's ``query_tabs`` — write credentials for a fact the read had
already paid for on the wire.

This module holds four properties, each of which is a way that fix could quietly rot:

1. **The wire really carries it** — pinned against the verbatim captured body of a live READ
   call (``tests/captures/ld477-hidden-tab-probe/captures/04-READ-route-raw-wire.json``), one tab hidden
   and one visible, the hidden state established independently of the field under test (the
   drive xlsx export's ``state="hidden"``, a different route family). Fixtures in this repo
   are deserialized from real API JSON precisely so a payload drift reddens here rather than
   corrupting output silently.
2. **The projection is honest** — an absent or non-boolean ``hidden`` yields ``None``, never
   ``False``. *"Nobody said"* and *"the tab is visible"* are different facts, and this is the
   same rule ``parse_frozen_panes`` and ``SheetsWriteClient.query_tabs`` already live under.
3. **It costs no additional call** — the whole premise of the shape that was built. One GET,
   the one ``query_sheets`` already made; a second request here would mean the field was not
   free after all.
4. **The renderer does not spend it** — the Markdown a spreadsheet renders to is
   **byte-identical** whether a tab is hidden, visible, or of unknown visibility. Marking a
   hidden tab in rendered output would move every consumer's golden files, and no consent
   exists for that; the model carries the field and the caller decides what to do with it.

Scope of the measurement (a label covers the route it was observed on): one tenant, one day
(2026-08-16), ``tenant_access_token``, the ``larksuite.com`` domain, the READ credential pair,
the route ``GET /open-apis/sheets/v3/spreadsheets/{token}/sheets/query``, on a harness-created
two-tab disposable with one tab hidden. It says nothing about ``metainfo``, the v2 routes, or
a ``user_access_token`` — and, because this tenant's READ and WRITE credential pairs alias one
app, nothing about scope separation either. What it establishes is that the field is on the
read route's own wire and the read already pays for the bytes.
"""
import json
import urllib.parse
from pathlib import Path

import pytest

from larkdocio.sheets.client import SheetsReadClient
from larkdocio.sheets.extent import UsedRange
from larkdocio.sheets.models import SheetTab
from larkdocio.sheets.table import render_spreadsheet

from write_harness import _FakeHTTPResponse

# LD-370 — CONFORMANCE-tier: a public read-model field projected from a real API payload.
# See process/doctrine/conformance-tier.md (a lens, not a gate).
pytestmark = pytest.mark.conformance

#: The verbatim body of a live READ-pair call to the tab-query route, captured by the premise
#: probe. Real API JSON, not a hand-mocked dict — the project's fixture rule.
_PROBE_CAPTURE = (
    Path(__file__).resolve().parent.parent
    / "tests" / "captures" / "ld477-hidden-tab-probe" / "captures" / "04-READ-route-raw-wire.json"
)


def _probe():
    return json.loads(_PROBE_CAPTURE.read_text(encoding="utf-8"))


def _wire_body():
    """The captured response body, exactly as Lark sent it."""
    return _probe()["raw_response_body"]


class _CountingOpener:
    """Returns the queued payloads and records every request — so "no extra call" is
    measured rather than asserted in prose."""

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.requests = []

    def __call__(self, req, timeout=30):
        self.requests.append({"method": req.get_method(), "url": req.full_url})
        return _FakeHTTPResponse(self._payloads[len(self.requests) - 1])


def _client(opener):
    return SheetsReadClient(
        "app", "secret", "larksuite.com",
        urlopen=opener,
        token_fetcher=lambda *a, **k: "t-test",
    )


# --------------------------------------------------------------------------- #
# 1. The wire.                                                                 #
# --------------------------------------------------------------------------- #

def test_the_captured_read_route_body_carries_hidden_on_EVERY_tab():
    """Not only on the hidden one — the key is unconditional, which is what makes an
    absent key meaningful rather than routine."""
    probe = _probe()
    assert probe["http_status"] == 200
    assert probe["raw_response_body"]["code"] == 0
    assert probe["route"].endswith("/sheets/query")
    assert "READ pair" in probe["credentials"]

    sheets = probe["raw_response_body"]["data"]["sheets"]
    assert len(sheets) == 2
    assert all("hidden" in sheet for sheet in sheets)
    assert {s["sheet_id"]: s["hidden"] for s in sheets} == {"3IZPYQ": False, "c7949b": True}


# --------------------------------------------------------------------------- #
# 2. The projection.                                                           #
# --------------------------------------------------------------------------- #

def test_query_sheets_projects_the_captured_hidden_onto_the_read_model():
    opener = _CountingOpener([_wire_body()])
    tabs = _client(opener).query_sheets("Example402d14e864078abc36ae")

    assert [(t.sheet_id, t.title, t.hidden) for t in tabs] == [
        ("3IZPYQ", "LD477-Beta", False),
        ("c7949b", "Sheet1", True),
    ]


def test_from_dict_reads_the_captured_elements_the_same_way():
    """The model's own door, fed the same real elements."""
    sheets = _wire_body()["data"]["sheets"]
    assert [SheetTab.from_dict(s).hidden for s in sheets] == [False, True]


@pytest.mark.parametrize("raw, why", [
    ({}, "the key is absent altogether"),
    ({"hidden": None}, "the key is present and null"),
    ({"hidden": "true"}, "the key is a string, not a boolean"),
    ({"hidden": 1}, "the key is a number, not a boolean"),
])
def test_an_unusable_hidden_is_None_and_NEVER_False(raw, why):
    """'Unknown' is never laundered into 'visible'.

    ``False`` here would be a claim — that Lark said the tab is visible — and nothing said
    it. The same honesty rule the frozen read established and the write client's ``query_tabs``
    already applies to this very flag.
    """
    element = {"sheet_id": "s1", "title": "T", "index": 0,
               "grid_properties": {"row_count": 2, "column_count": 2}, **raw}
    tab = SheetTab.from_dict(element)
    assert tab.hidden is None, why


def test_hidden_survives_the_state_carrying_copies():
    """``with_filter`` / ``with_frozen`` / ``with_revision`` return copies; a visibility read
    must not be lost by a later filter read layering onto the same tab."""
    tab = SheetTab.from_dict({"sheet_id": "c7949b", "title": "Sheet1", "index": 1,
                              "hidden": True,
                              "grid_properties": {"row_count": 200, "column_count": 20}})
    assert tab.with_filter(None).hidden is True
    assert tab.with_filter_unavailable("no permission").hidden is True
    assert tab.with_revision_unavailable("not read").hidden is True


# --------------------------------------------------------------------------- #
# 3. The cost.                                                                 #
# --------------------------------------------------------------------------- #

def test_the_visibility_answer_costs_NO_ADDITIONAL_CALL():
    """One GET — the one the read already made. This is the whole premise of the shape that
    was built: the field was already on the wire, so surfacing it is a projection change and
    not a new endpoint, a new leg, or a new credential."""
    opener = _CountingOpener([_wire_body()])
    tabs = _client(opener).query_sheets("Example402d14e864078abc36ae")

    assert [t.hidden for t in tabs] == [False, True]
    assert len(opener.requests) == 1, opener.requests
    assert opener.requests[0]["method"] == "GET"
    path = urllib.parse.urlsplit(opener.requests[0]["url"]).path
    assert path == (
        "/open-apis/sheets/v3/spreadsheets/Example402d14e864078abc36ae/sheets/query")


# --------------------------------------------------------------------------- #
# 4. The renderer does not spend it.                                           #
# --------------------------------------------------------------------------- #

def _rendered(hidden):
    tab = SheetTab(sheet_id="c7949b", title="Sheet1", index=0,
                   row_count=2, column_count=2, hidden=hidden)
    used = UsedRange.from_tab_values(tab, [["Item", "Qty"], ["Bolt", "3"]])
    return render_spreadsheet([(tab, used)])


def test_the_RENDERED_MARKDOWN_IS_BYTE_IDENTICAL_whatever_the_visibility():
    """The model carries the field; the renderer does not spend it.

    A hidden-tab marker in rendered Markdown would move every consumer's golden files, and
    that is an output change nobody consented to. It is a live product question — *should* a
    hidden tab be marked? — and it is answered somewhere other than here.
    """
    unknown, visible, hidden = _rendered(None), _rendered(False), _rendered(True)
    assert unknown == visible == hidden
    assert unknown.encode("utf-8") == hidden.encode("utf-8")
    assert "hidden" not in hidden.lower()
