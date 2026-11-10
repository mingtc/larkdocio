"""Offline unit tests for the Sheets read client (LD-101).

The Sheets read client is NEW infrastructure the L1 values→Markdown reader rides
(S1, head of the S1→S6 chain). It reaches the Sheets API over **raw HTTP** — the
v2 ``values`` / ``values_batch_get`` endpoints are absent from the pinned
``lark-oapi`` SDK (spike Q5/Q7) — reusing the shared core: ``common.auth``'s READ
credential resolution + IPv4 pin and ``common.transport``'s :class:`RateLimiter`
(a read cap ≪ Lark's 100/sec ceiling), raising the S1 typed taxonomy.

Every payload here is fed from the LD-100 opener spike's **committed captures**
(``tests/captures/sheets-spike/captures/*.json``) — the exact bytes a real read returned, so
these fixtures pin real payload shapes and an API drift reddens the suite
(PROJECT.md § Quality bar). All offline: a fake clock + a stub opener, no network.

The live round-trip is the S6 sheets canary (``pytest -m live``, LD-106) — not
here.
"""
import json
import urllib.parse
from pathlib import Path

import pytest

from larkdocio.sheets.client import SheetsReadClient, DEFAULT_MAX_READS_PER_SEC
from larkdocio.sheets.models import Merge, SheetTab, SpreadsheetMeta, ValueRange
from larkdocio.common.transport import RateLimiter
from larkdocio.errors import LarkAPIError, LarkConfigError, LarkRateLimitError

from write_harness import FakeClock, _FakeHTTPResponse

# The spike's captures are the offline-fixture seed (the Sheets read spec § References): raw
# API JSON, immutable spike artifacts explicitly designated fixture material.
_CAPTURES = Path(__file__).resolve().parent.parent / "tests" / "captures" / "sheets-spike" / "captures"


def _capture(name):
    return json.loads((_CAPTURES / name).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Test doubles (offline — a fake clock + a stub opener; mirror test_write_client) #
# --------------------------------------------------------------------------- #


class StubOpener:
    """Records each urllib GET and returns the next queued payload (a dict).

    The stub opener IS the injected/fake transport (AC1): fed a ``captures/`` JSON
    payload, it lets each call's parse + outgoing query params be asserted offline.
    """

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.requests = []

    def __call__(self, req, timeout=30):
        self.requests.append({
            "method": req.get_method(),
            "url": req.full_url,
            "auth": req.headers.get("Authorization"),
        })
        return _FakeHTTPResponse(self._payloads[len(self.requests) - 1])

    def query_of(self, i):
        """The parsed query-param dict of the i-th recorded request's URL."""
        qs = urllib.parse.urlsplit(self.requests[i]["url"]).query
        return dict(urllib.parse.parse_qsl(qs))


def _client(opener, *, rate_limiter=None, **kw):
    return SheetsReadClient(
        "app", "secret", "larksuite.com",
        urlopen=opener,
        token_fetcher=lambda *a, **k: "t-test",
        rate_limiter=rate_limiter,
        **kw,
    )


# --------------------------------------------------------------------------- #
# AC1 — the four calls parse the expected shapes from captures                  #
# --------------------------------------------------------------------------- #

def test_metadata_parses_spreadsheet_and_hits_v3_endpoint():
    opener = StubOpener([_capture("00-scratch-meta.json")])
    client = _client(opener)

    meta = client.get_spreadsheet_meta("SheetScratchExample00000001")

    assert isinstance(meta, SpreadsheetMeta)
    assert meta.token == "SheetScratchExample00000001"
    assert meta.title == "Larkdocio Scratch Sheet"
    assert meta.owner_id == "ou_exampleowner00000000000000000001"
    assert meta.url.endswith("/sheets/SheetScratchExample00000001")
    req = opener.requests[0]
    assert req["method"] == "GET"
    assert req["auth"] == "Bearer t-test"
    assert req["url"].endswith(
        "/open-apis/sheets/v3/spreadsheets/SheetScratchExample00000001"
    )


def test_tab_query_surfaces_id_title_index_extent_and_merges():
    opener = StubOpener([_capture("00-scratch-tabs.json")])
    client = _client(opener)

    tabs = client.query_sheets("SheetScratchExample00000001")

    assert [t.sheet_id for t in tabs] == ["444a1c", "7pg9wE"]
    types, merged = tabs

    # id / title / index / grid extent are all surfaced.
    assert isinstance(types, SheetTab)
    assert (types.title, types.index) == ("Types", 0)
    assert (types.row_count, types.column_count) == (200, 20)
    assert types.merges == ()          # Types tab declares no merges

    # The merges array is surfaced, 0-indexed and END-inclusive (spike Q3).
    assert (merged.title, merged.index) == ("Merged", 1)
    assert len(merged.merges) == 5
    assert merged.merges[0] == Merge(
        start_row=0, end_row=0, start_col=0, end_col=2  # A1:C1
    )
    # A3:A5 vertical merge — the boundary case an off-by-one would break.
    assert Merge(start_row=2, end_row=4, start_col=0, end_col=0) in merged.merges

    assert opener.requests[0]["url"].endswith(
        "/open-apis/sheets/v3/spreadsheets/SheetScratchExample00000001/sheets/query"
    )


def test_values_single_range_parses_matrix_and_revision():
    opener = StubOpener([_capture("02-types-FormattedValue.json")])
    client = _client(opener)

    vr = client.get_values("SheetScratchExample00000001", "444a1c!A1:D24")

    assert isinstance(vr, ValueRange)
    assert vr.range == "444a1c!A1:D24"
    assert vr.revision == 34
    assert vr.major_dimension == "ROWS"
    # The raw matrix is returned untouched (no trim — that is S2; no render — S3).
    assert vr.values[0] == ["Type", "Value", "Notes", "Value (recreated natively)"]
    assert vr.values[3] == ["integer", 42, None, 42]        # numeric JSON preserved
    assert vr.values[15][1][0]["type"] == "url"             # rich cell stays structured
    # The values endpoint is the v2 single-range path.
    assert "/open-apis/sheets/v2/spreadsheets/" in opener.requests[0]["url"]
    assert "/values/444a1c!A1:D24" in urllib.parse.unquote(opener.requests[0]["url"])


# --------------------------------------------------------------------------- #
# AC2 — explicit render options ALWAYS; no code path omits valueRenderOption    #
# --------------------------------------------------------------------------- #

def test_values_default_sends_explicit_formatted_value_and_options():
    opener = StubOpener([_capture("02-types-FormattedValue.json")])
    client = _client(opener)

    client.get_values("tok", "444a1c!A1:D24")

    q = opener.query_of(0)
    assert q["valueRenderOption"] == "FormattedValue"     # D1 default, explicit
    assert q["dateTimeRenderOption"] == "FormattedString"  # dates as strings (D1)
    assert "user_id_type" in q                             # D6 mention rendering


def test_passing_none_render_option_still_sends_explicit_default():
    """A caller passing value_render_option=None must NOT omit it — it falls back
    to the explicit FormattedValue default (D1: never the unspecified default)."""
    opener = StubOpener([_capture("02-types-FormattedValue.json")])
    client = _client(opener)

    client.get_values("tok", "r!A1:B2", value_render_option=None)

    assert opener.query_of(0)["valueRenderOption"] == "FormattedValue"


def test_value_render_option_override_is_honored():
    opener = StubOpener([_capture("02-types-UnformattedValue.json")])
    client = _client(opener)

    client.get_values("tok", "r!A1:B2", value_render_option="UnformattedValue")

    assert opener.query_of(0)["valueRenderOption"] == "UnformattedValue"


def test_no_values_code_path_omits_value_render_option():
    """Belt-and-braces for AC2: every values-endpoint method sends an explicit
    valueRenderOption on its outgoing request."""
    payload = _capture("02-types-FormattedValue.json")
    batch = _capture("04-batch-get.json")

    single = StubOpener([payload])
    _client(single).get_values("tok", "r!A1:B2")
    assert "valueRenderOption" in single.query_of(0)

    multi = StubOpener([batch])
    _client(multi).batch_get_values("tok", ["r!A1:B2"])
    assert "valueRenderOption" in multi.query_of(0)


# --------------------------------------------------------------------------- #
# AC3 — throttled through the shared RateLimiter + typed errors                  #
# --------------------------------------------------------------------------- #

def test_reads_are_throttled_through_the_shared_rate_limiter():
    """A 4th read inside the same second is paced by common.transport's
    RateLimiter (a read cap ≪ 100/sec)."""
    clock = FakeClock()
    limiter = RateLimiter(max_per_sec=3, time_fn=clock.time, sleep_fn=clock.sleep)
    opener = StubOpener([_capture("00-scratch-meta.json") for _ in range(4)])
    client = _client(opener, rate_limiter=limiter)

    for _ in range(4):
        client.get_spreadsheet_meta("tok")

    assert clock.sleeps == [1.0]   # the 4th read waited one full window


def test_default_read_cap_is_well_under_the_lark_ceiling():
    assert 1 <= DEFAULT_MAX_READS_PER_SEC <= 20   # gentle, ≪ Lark's 100/sec


def test_non_zero_code_raises_typed_api_error_with_code_and_msg():
    opener = StubOpener([{"code": 1310213, "msg": "sheet not found"}])
    client = _client(opener)

    with pytest.raises(LarkAPIError) as ei:
        client.get_values("tok", "r!A1:B2")
    assert ei.value.code == 1310213
    assert ei.value.msg == "sheet not found"


def test_rate_limit_code_raises_typed_rate_limit_error():
    opener = StubOpener([{"code": "99991400", "msg": "frequency limited"}])
    client = _client(opener)

    with pytest.raises(LarkRateLimitError):
        client.query_sheets("tok")


# --------------------------------------------------------------------------- #
# AC4 — READ credentials only; the write path is never consulted                #
# --------------------------------------------------------------------------- #

def test_from_read_credentials_resolves_read_path_never_write(monkeypatch):
    from unittest.mock import MagicMock

    read_spy = MagicMock(return_value=("read-id", "read-secret"))
    write_spy = MagicMock()
    pin_spy = MagicMock()   # spy the pin (avoid a global socket.getaddrinfo patch)
    monkeypatch.setattr("larkdocio.sheets.client.get_read_credentials", read_spy)
    monkeypatch.setattr("larkdocio.common.auth.get_write_credentials", write_spy)
    monkeypatch.setattr("larkdocio.sheets.client.apply_ipv4_pin", pin_spy)

    opener = StubOpener([_capture("00-scratch-meta.json")])
    client = SheetsReadClient.from_read_credentials(
        urlopen=opener, token_fetcher=lambda *a, **k: "t-test"
    )
    client.get_spreadsheet_meta("tok")

    read_spy.assert_called_once()          # resolved via the READ path
    pin_spy.assert_called_once()           # under the shared IPv4 pin (AC4)
    write_spy.assert_not_called()          # the write path is never consulted


def test_from_read_credentials_missing_creds_raises_config_error(monkeypatch):
    monkeypatch.setattr(
        "larkdocio.sheets.client.get_read_credentials", lambda: ("", "")
    )
    with pytest.raises(LarkConfigError):
        SheetsReadClient.from_read_credentials()


# --------------------------------------------------------------------------- #
# AC5 — values_batch_get batches: one comma-separated ranges=, ordered results  #
# --------------------------------------------------------------------------- #

def test_batch_get_sends_comma_separated_ranges_and_parses_in_order():
    opener = StubOpener([_capture("04-batch-get.json")])
    client = _client(opener)

    ranges = ["444a1c!A1:D3", "444a1c!A23:B24", "7pg9wE!A1:C3"]
    results = client.batch_get_values("SheetScratchExample00000001", ranges)

    # Per-range results returned in order, each carrying its own revision.
    assert [r.range for r in results] == ranges
    assert all(r.revision == 34 for r in results)
    assert results[0].values[0] == ["Type", "Value", "Notes", "Value (recreated natively)"]
    assert results[2].values[0] == ["merged title spanning A1:C1", None, None]

    # One call, ranges passed as a single comma-separated ranges= param.
    assert len(opener.requests) == 1
    assert opener.query_of(0)["ranges"] == ",".join(ranges)
    assert opener.requests[0]["url"].split("?")[0].endswith(
        "/open-apis/sheets/v2/spreadsheets/SheetScratchExample00000001/values_batch_get"
    )
