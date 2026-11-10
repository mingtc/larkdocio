"""Offline unit tests for the Sheets value-write client (LD-109).

The Sheets write client is the head of the Sheets value-write spec's S1→S5 chain: a raw-HTTP,
WRITE-app-only, throttled, typed value-write client. These pin — all offline (a
fake clock + a stub opener fed from the LD-107 spike captures, no network) — the
AC that is offline-testable:

* **AC1** — the four ops (``put_values`` / ``batch_update_values`` /
  ``append_values`` / ``prepend_values``) speak the right v2 method/path/body,
  asserted against ``tests/captures/sheets-write-spike/captures/01-endpoint-matrix.json``;
* **AC2** — ``Start:End`` **always**: a single-cell target is normalized to
  ``A1:A1`` and no code path can emit a bare cell (the ``90202`` guard);
* **AC3** — WRITE creds only (``get_write_credentials`` — no read/legacy
  fallback → ``LarkConfigError``) and every op routes through the shared ≤3/s
  throttle (not bypassable);
* **AC4** — the per-Lark-``code`` typed taxonomy (``90202`` / ``90204`` / a
  rate-limit code / a generic failure).

The binding live write round-trip (AC6) is a self-provisioned disposable at QA,
not here.
"""

import json
from pathlib import Path

import pytest

from larkdocio.sheets.rich_encode import encode_dropdown_rule
from larkdocio.sheets.write_client import SheetsWriteClient, normalize_write_range
from larkdocio.common.transport import WriteTransport
from larkdocio.errors import LarkAPIError, LarkConfigError, LarkRateLimitError

from write_harness import CountingTransport, FakeClock, _FakeHTTPResponse

# The LD-107 spike's endpoint-matrix capture — the fixture source for AC1.
_CAPTURE = (
    Path(__file__).resolve().parent.parent
    / "tests" / "captures" / "sheets-write-spike" / "captures" / "01-endpoint-matrix.json"
)
_MATRIX = json.loads(_CAPTURE.read_text(encoding="utf-8"))["captures"]
_TOK = "Example0e7c15c322aeef5d5867"

# The LD-107 dropdown capture — the fixture source for the LD-120 dataValidation op.
_DROPDOWN = json.loads(
    (Path(__file__).resolve().parent.parent
     / "tests" / "captures" / "sheets-write-spike" / "captures" / "03b-dropdown.json").read_text(encoding="utf-8")
)["captures"]


# --------------------------------------------------------------------------- #
# Test doubles (offline — a fake clock + a stub opener; mirror                  #
# tests/test_write_client.py so the two write clients share one harness shape). #
# --------------------------------------------------------------------------- #


class StubOpener:
    """Records each urllib request and returns the next queued payload."""

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.requests = []

    def __call__(self, req, timeout=30):
        body = json.loads(req.data.decode()) if req.data else None
        self.requests.append({
            "method": req.get_method(),
            "url": req.full_url,
            "body": body,
            "auth": req.headers.get("Authorization"),
        })
        payload = self._payloads[len(self.requests) - 1]
        return _FakeHTTPResponse(payload)


def _client(opener, clock=None, transport=None, **kw):
    clock = clock or FakeClock()
    transport = transport or WriteTransport(
        max_writes_per_sec=3, time_fn=clock.time, sleep_fn=clock.sleep
    )
    return SheetsWriteClient(
        "app", "secret", "larksuite.com",
        transport=transport,
        urlopen=opener,
        token_fetcher=lambda *a, **k: "t-test",
        **kw,
    )


# --------------------------------------------------------------------------- #
# AC1 — the four ops speak the right v2 method/path/body (from the capture)     #
# --------------------------------------------------------------------------- #

def test_put_values_matches_capture_method_path_body():
    cap = _MATRIX["values_put"]
    opener = StubOpener([cap["response"]])
    client = _client(opener)

    data = client.put_values(_TOK, "154e99!A1:C3",
                             [["h1", "h2", "h3"], [1, 2, 3], [4, 5, 6]])

    req = opener.requests[0]
    assert req["method"] == "PUT"
    assert req["url"].endswith(cap["path"])
    assert req["body"] == cap["request_body"]
    assert req["auth"] == "Bearer t-test"
    assert data["revision"] == 1


def test_batch_update_values_matches_capture_method_path_body():
    cap = _MATRIX["values_batch_update"]
    opener = StubOpener([cap["response"]])
    client = _client(opener)

    client.batch_update_values(_TOK, [
        {"range": "154e99!E1:F1", "values": [["batchA", "batchB"]]},
        {"range": "154e99!E2:F2", "values": [["batchC", "batchD"]]},
    ])

    req = opener.requests[0]
    assert req["method"] == "POST"
    assert req["url"].endswith(cap["path"])
    assert req["body"] == cap["request_body"]


def test_append_values_matches_capture_method_path_body():
    cap = _MATRIX["values_append"]
    opener = StubOpener([cap["response"]])
    client = _client(opener)

    client.append_values(_TOK, "154e99!A1:C1", [["appended", "row", "here"]])

    req = opener.requests[0]
    assert req["method"] == "POST"
    assert req["url"].endswith(cap["path"])
    assert req["body"] == cap["request_body"]


def test_prepend_values_matches_capture_method_path_body():
    cap = _MATRIX["values_prepend"]
    opener = StubOpener([cap["response"]])
    client = _client(opener)

    client.prepend_values(_TOK, "154e99!A1:C1", [["prepended", "row", "here"]])

    req = opener.requests[0]
    assert req["method"] == "POST"
    assert req["url"].endswith(cap["path"])
    assert req["body"] == cap["request_body"]


def test_append_optional_insert_data_option_is_a_query_param():
    """The structural INSERT_ROWS variant (the Sheets rich/structural-write spec-parked) is opt-in via a query
    param; the default append emits no ``insertDataOption`` (non-structural)."""
    opener = StubOpener([{"code": 0, "data": {"revision": 9}},
                         {"code": 0, "data": {"revision": 10}}])
    client = _client(opener)

    client.append_values(_TOK, "154e99!A1:C1", [["x"]])
    assert "insertDataOption" not in opener.requests[0]["url"]

    client.append_values(_TOK, "154e99!A1:C1", [["x"]],
                         insert_data_option="INSERT_ROWS")
    assert "insertDataOption=INSERT_ROWS" in opener.requests[1]["url"]


# --------------------------------------------------------------------------- #
# AC2 — Start:End ALWAYS; a bare single-cell range is structurally impossible   #
# --------------------------------------------------------------------------- #

def test_single_cell_target_is_normalized_to_start_end_on_the_wire():
    """A bare single-cell target reaches Lark as ``B2:B2`` — never a bare ``B2``
    (which the API rejects with 90202)."""
    opener = StubOpener([{"code": 0, "data": {"revision": 1}}])
    client = _client(opener)

    client.put_values(_TOK, "154e99!B2", [["only"]])

    emitted = opener.requests[0]["body"]["valueRange"]["range"]
    assert emitted == "154e99!B2:B2"
    assert ":" in emitted


@pytest.mark.parametrize("bare, expected", [
    ("154e99!A1", "154e99!A1:A1"),
    ("A1", "A1:A1"),
    ("Sheet1!B2", "Sheet1!B2:B2"),          # cross-tab prefix preserved
    ("abc123!CV100", "abc123!CV100:CV100"), # 100-col notation edge
])
def test_normalize_write_range_forces_start_end_on_bare_cells(bare, expected):
    assert normalize_write_range(bare) == expected


@pytest.mark.parametrize("already_ranged", [
    "154e99!A1:C3",
    "A1:C3",
    "C3:A1",             # reversed bounds still carry a colon (validation is S2)
    "Sheet1!A1:CV100",   # 100-col range edge
])
def test_normalize_write_range_leaves_ranged_inputs_untouched(already_ranged):
    assert normalize_write_range(already_ranged) == already_ranged
    assert ":" in normalize_write_range(already_ranged)


def test_no_op_can_emit_a_bare_cell_across_every_path():
    """Every values-write op routes its range(s) through the Start:End guard —
    a bare cell handed to ANY op is impossible on the wire."""
    opener = StubOpener([{"code": 0, "data": {}} for _ in range(4)])
    client = _client(opener)

    client.put_values(_TOK, "s!A1", [["v"]])
    client.append_values(_TOK, "s!B2", [["v"]])
    client.prepend_values(_TOK, "s!C3", [["v"]])
    client.batch_update_values(_TOK, [{"range": "s!D4", "values": [["v"]]}])

    ranges = []
    ranges.append(opener.requests[0]["body"]["valueRange"]["range"])
    ranges.append(opener.requests[1]["body"]["valueRange"]["range"])
    ranges.append(opener.requests[2]["body"]["valueRange"]["range"])
    ranges.append(opener.requests[3]["body"]["valueRanges"][0]["range"])
    for r in ranges:
        assert ":" in r, f"bare cell leaked to the wire: {r!r}"


def test_unicode_cell_content_round_trips_in_the_body():
    opener = StubOpener([{"code": 0, "data": {}}])
    client = _client(opener)

    client.put_values(_TOK, "154e99!A1:A1", [["café — 日本語 — Ω"]])

    assert opener.requests[0]["body"]["valueRange"]["values"] == [["café — 日本語 — Ω"]]


# --------------------------------------------------------------------------- #
# AC3 — WRITE creds only (no read/legacy fallback) + throttle on every op       #
# --------------------------------------------------------------------------- #

def test_from_write_credentials_uses_write_pair(monkeypatch):
    monkeypatch.setenv("LARK_WRITE_APP_ID", "wid")
    monkeypatch.setenv("LARK_WRITE_APP_SECRET", "wsecret")
    client = SheetsWriteClient.from_write_credentials()
    assert client._app_id == "wid"
    assert client._app_secret == "wsecret"


def test_from_write_credentials_never_falls_back_to_read_or_legacy(monkeypatch):
    """Only legacy READ creds present, WRITE unset → LarkConfigError, never a
    silent promotion of a read-only app to a write (credential doctrine D1)."""
    for k in ("LARK_WRITE_APP_ID", "LARK_WRITE_APP_SECRET",
              "LARK_READ_APP_ID", "LARK_READ_APP_SECRET"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LARK_APP_ID", "legacy-id")
    monkeypatch.setenv("LARK_APP_SECRET", "legacy-secret")

    with pytest.raises(LarkConfigError):
        SheetsWriteClient.from_write_credentials()


def test_write_client_does_not_import_read_credentials():
    """Static guard: the write module never references the read-cred resolver, so
    no future edit can wire a read/legacy fallback into the write path."""
    import larkdocio.sheets.write_client as mod
    text = Path(mod.__file__).read_text(encoding="utf-8")
    assert "get_read_credentials" not in text
    assert "LARK_APP_ID" not in text
    assert "LARK_READ_APP" not in text


def test_every_op_routes_through_the_transport():
    """The throttle is the transport's job; proving each op calls ``execute``
    proves no op can bypass the ≤3/s limiter."""
    inner = WriteTransport(max_writes_per_sec=3,
                           time_fn=FakeClock().time, sleep_fn=lambda *_: None)
    spy = CountingTransport(inner)
    opener = StubOpener([{"code": 0, "data": {}} for _ in range(4)])
    client = _client(opener, transport=spy)

    client.put_values(_TOK, "s!A1:A1", [["v"]])
    client.batch_update_values(_TOK, [{"range": "s!A1:A1", "values": [["v"]]}])
    client.append_values(_TOK, "s!A1:A1", [["v"]])
    client.prepend_values(_TOK, "s!A1:A1", [["v"]])

    assert spy.executes == 4


def test_writes_are_throttled_to_three_per_second():
    """A 4th write in the same second is paced by the shared RateLimiter (≤3/s) —
    the throttle-order proof (amplifier)."""
    clock = FakeClock()
    opener = StubOpener([{"code": 0, "data": {}} for _ in range(4)])
    client = _client(opener, clock=clock)

    client.put_values(_TOK, "s!A1:A1", [["v"]])
    client.put_values(_TOK, "s!A1:A1", [["v"]])
    client.put_values(_TOK, "s!A1:A1", [["v"]])
    client.put_values(_TOK, "s!A1:A1", [["v"]])

    assert clock.sleeps == [1.0]   # the 4th waited one full window


# --------------------------------------------------------------------------- #
# AC4 — typed error taxonomy, one test per Lark code (the amplifier)            #
# --------------------------------------------------------------------------- #

def test_wrong_range_90202_surfaces_as_inspectable_typed_error():
    cap = _MATRIX["style_put"]  # the real 90202 body from the spike
    opener = StubOpener([cap["response"]])
    client = _client(opener)

    with pytest.raises(LarkAPIError) as ei:
        client.put_values(_TOK, "154e99!B2:B2", [["v"]])
    assert ei.value.code == 90202
    assert "wrong range" in (ei.value.msg or "")
    assert not isinstance(ei.value, LarkRateLimitError)


def test_validation_90204_surfaces_as_inspectable_typed_error():
    opener = StubOpener([{"code": 90204, "msg": "validation failed", "data": {}}])
    client = _client(opener)

    with pytest.raises(LarkAPIError) as ei:
        client.put_values(_TOK, "154e99!A1:A1", [["v"]])
    assert ei.value.code == 90204
    assert ei.value.msg == "validation failed"


def test_generic_non_zero_code_raises_lark_api_error():
    opener = StubOpener([{"code": 1310217, "msg": "no permission", "data": {}}])
    client = _client(opener)

    with pytest.raises(LarkAPIError) as ei:
        client.put_values(_TOK, "154e99!A1:A1", [["v"]])
    assert ei.value.code == 1310217
    assert not isinstance(ei.value, LarkRateLimitError)


def test_rate_limit_code_raises_typed_rate_limit_error():
    clock = FakeClock()
    opener = StubOpener([{"code": "99991400", "msg": "rate"} for _ in range(10)])
    transport = WriteTransport(
        max_writes_per_sec=1000, max_retries=2,
        time_fn=clock.time, sleep_fn=clock.sleep,
    )
    client = _client(opener, transport=transport)

    with pytest.raises(LarkRateLimitError):
        client.put_values(_TOK, "154e99!A1:A1", [["v"]])


# --------------------------------------------------------------------------- #
# LD-111 — the write-side READ helpers the gated apply engine's compare-and-swap #
# needs: the metainfo `revision` anchor (D5) + the raw before/precondition read. #
# The WRITE app reads its OWN compare-and-swap anchor as part of the gated write #
# flow (parity with the docx WriteClient.get_block re-validation); reads bypass  #
# the ≤3/s WRITE throttle (reads are not write-rate-limited).                     #
# --------------------------------------------------------------------------- #

def test_read_revision_gets_v2_metainfo_and_returns_properties_revision():
    # the LD-107 style-read capture's metainfo response shape (data.properties.revision).
    resp = {"code": 0, "data": {"properties": {"revision": 7, "title": "x"}}}
    opener = StubOpener([resp])
    client = _client(opener)

    rev = client.read_revision(_TOK)

    req = opener.requests[0]
    assert req["method"] == "GET"
    assert req["url"].endswith(f"/open-apis/sheets/v2/spreadsheets/{_TOK}/metainfo")
    assert req["auth"] == "Bearer t-test"
    assert rev == 7


def test_read_revision_bypasses_the_write_throttle():
    resp = {"code": 0, "data": {"properties": {"revision": 1}}}
    opener = StubOpener([resp])
    transport = CountingTransport(WriteTransport())
    client = _client(opener, transport=transport)

    client.read_revision(_TOK)

    assert transport.executes == 0  # a read never spends WRITE-throttle budget


def test_read_values_gets_unformatted_value_range_matrix():
    resp = {"code": 0, "data": {"valueRange": {
        "range": "s1!A1:B1", "revision": 3, "values": [["raw-a", 42]],
    }}}
    opener = StubOpener([resp])
    client = _client(opener)

    matrix = client.read_values(_TOK, "s1!A1:B1")

    req = opener.requests[0]
    assert req["method"] == "GET"
    assert f"/open-apis/sheets/v2/spreadsheets/{_TOK}/values/s1!A1:B1" in req["url"]
    assert "valueRenderOption=UnformattedValue" in req["url"]
    assert matrix == [["raw-a", 42]]


def test_read_values_typed_error_on_non_zero_code():
    opener = StubOpener([{"code": 90202, "msg": "wrong range=s1!A1"}])
    client = _client(opener)

    with pytest.raises(LarkAPIError) as ei:
        client.read_values(_TOK, "s1!A1")
    assert ei.value.code == 90202


# --------------------------------------------------------------------------- #
# LD-120 — the dropdown-RULE write op (`POST …/dataValidation`).                  #
# The encoder (rich_encode.encode_dropdown_rule) owns the rule shape + the 90204  #
# colors guard; this client op speaks the right v2 method/path/body (from the     #
# 03b-dropdown capture), forces Start:End (90202 guard), rides the throttle, and   #
# surfaces a live 90204 as a typed LarkAPIError (belt-and-suspenders — the encoder #
# already refuses the mismatch before the write).                                  #
# --------------------------------------------------------------------------- #

def test_set_data_validation_matches_capture_method_path_body():
    cap = _DROPDOWN["dv_set_valid"]
    # the capture's own token + range (its path is …/{token}/dataValidation).
    tok = cap["path"].split("/spreadsheets/")[1].split("/")[0]
    rng = cap["request_body"]["range"]
    opener = StubOpener([cap["response"]])
    client = _client(opener)

    rule = encode_dropdown_rule(["Red", "Green", "Blue"], multiple_values=True)
    client.set_data_validation(tok, rng, rule)

    req = opener.requests[0]
    assert req["method"] == "POST"
    assert req["url"].endswith(cap["path"])
    assert req["body"] == cap["request_body"]
    assert req["auth"] == "Bearer t-test"


def test_set_data_validation_forces_start_end_on_a_bare_cell():
    opener = StubOpener([{"code": 0, "data": {}}])
    client = _client(opener)

    client.set_data_validation(_TOK, "154e99!B2",
                               encode_dropdown_rule(["Yes", "No"]))

    emitted = opener.requests[0]["body"]["range"]
    assert emitted == "154e99!B2:B2"
    assert ":" in emitted


def test_set_data_validation_routes_through_the_transport():
    inner = WriteTransport(max_writes_per_sec=3,
                           time_fn=FakeClock().time, sleep_fn=lambda *_: None)
    spy = CountingTransport(inner)
    opener = StubOpener([{"code": 0, "data": {}}])
    client = _client(opener, transport=spy)

    client.set_data_validation(_TOK, "s!A1:A1", encode_dropdown_rule(["a", "b"]))

    assert spy.executes == 1  # the rule write is throttled like every other write op


def test_set_data_validation_90204_surfaces_as_inspectable_typed_error():
    # a live 90204 (e.g. a highlight/colors mismatch the encoder didn't catch, or any
    # server-side validation) surfaces typed, carrying the code.
    opener = StubOpener([{"code": 90204, "msg": "validation failed", "data": {}}])
    client = _client(opener)

    with pytest.raises(LarkAPIError) as ei:
        client.set_data_validation(_TOK, "s!A1:A1", encode_dropdown_rule(["a", "b"]))
    assert ei.value.code == 90204
    assert ei.value.msg == "validation failed"


# --------------------------------------------------------------------------- #
# LD-121 — structural dimension write client ops                                #
# (insert/delete/append rows·cols + the write-side geometry re-read). These pin #
# the RAW-NATIVE transport bytes against the LD-107 Q4 capture                  #
# (04-structural-safety.json). The insert-vs-delete INDEX CONVENTION is encoded #
# STRUCTURALLY one layer up (the write_apply request objects) — the client is   #
# the faithful native-convention transport (insert emits its 0-idx half-open    #
# span, delete its 1-idx inclusive span) and passes indices straight to the     #
# wire; it never reinterprets them.                                            #
# --------------------------------------------------------------------------- #

_STRUCT = json.loads(
    (Path(__file__).resolve().parent.parent
     / "tests" / "captures" / "sheets-write-spike" / "captures" / "04-structural-safety.json").read_text(encoding="utf-8")
)["captures"]
_STRUCT_TOK = "Example3ae51823ecac6f104704"  # the capture's own spreadsheet token


def test_insert_dimension_range_rows_matches_capture_method_path_body():
    cap = _STRUCT["insert_row"]  # insert ROWS [1,2) — 0-idx half-open, 1 blank row @0-idx1
    opener = StubOpener([cap["response"]])
    client = _client(opener)

    client.insert_dimension_range(_STRUCT_TOK, "555c22", "ROWS", 1, 2)

    req = opener.requests[0]
    assert req["method"] == "POST"
    assert req["url"].endswith(cap["path"])
    assert req["body"] == cap["request_body"]  # {dimension:{sheetId,majorDimension:ROWS,startIndex:1,endIndex:2}}


def test_insert_dimension_range_columns_matches_capture_body():
    cap = _STRUCT["insert_col"]  # insert COLUMNS [1,2)
    opener = StubOpener([cap["response"]])
    client = _client(opener)

    client.insert_dimension_range(_STRUCT_TOK, "555c22", "COLUMNS", 1, 2)

    assert opener.requests[0]["body"] == cap["request_body"]


def test_insert_dimension_range_body_carries_no_inherit_style_by_default():
    # the byte-exact capture has NO inheritStyle key — the default insert emits just
    # the dimension body (inheritStyle stays an optional, off-by-default extra).
    opener = StubOpener([_STRUCT["insert_row"]["response"]])
    client = _client(opener)
    client.insert_dimension_range(_STRUCT_TOK, "555c22", "ROWS", 1, 2)
    assert "inheritStyle" not in opener.requests[0]["body"]


def test_delete_dimension_range_rows_matches_capture_and_returns_delcount():
    cap = _STRUCT["delete_row"]  # delete ROWS [2,3] — 1-idx inclusive; delCount 2
    opener = StubOpener([cap["response"]])
    client = _client(opener)

    data = client.delete_dimension_range(_STRUCT_TOK, "555c22", "ROWS", 2, 3)

    req = opener.requests[0]
    assert req["method"] == "DELETE"
    assert req["url"].endswith(cap["path"])
    assert req["body"] == cap["request_body"]  # startIndex:2, endIndex:3 (native 1-idx inclusive)
    assert data["delCount"] == 2               # the reply's authoritative removed count


def test_delete_dimension_range_columns_matches_capture_and_returns_delcount():
    cap = _STRUCT["delete_col"]
    opener = StubOpener([cap["response"]])
    client = _client(opener)

    data = client.delete_dimension_range(_STRUCT_TOK, "555c22", "COLUMNS", 2, 3)

    assert opener.requests[0]["body"] == cap["request_body"]
    assert data["delCount"] == 2


def test_append_dimension_posts_length_body_and_returns_addcount():
    # No byte-exact fixture; the Q1 endpoint-matrix documents the shape:
    # POST /dimension_range, dimension{sheetId,majorDimension,length}, addCount in reply.
    opener = StubOpener([{"code": 0, "data": {"addCount": 3, "majorDimension": "ROWS"}}])
    client = _client(opener)

    data = client.append_dimension(_STRUCT_TOK, "555c22", "ROWS", 3)

    req = opener.requests[0]
    assert req["method"] == "POST"
    assert req["url"].endswith(f"/open-apis/sheets/v2/spreadsheets/{_STRUCT_TOK}/dimension_range")
    assert req["body"] == {"dimension": {"sheetId": "555c22", "majorDimension": "ROWS", "length": 3}}
    assert data["addCount"] == 3


def test_read_sheet_geometry_returns_grid_and_merges_for_the_named_sheet():
    query_resp = {"code": 0, "data": {"sheets": [
        {"sheet_id": "555c22", "grid_properties": {"row_count": 9, "column_count": 5},
         "merges": [{"start_row_index": 1, "end_row_index": 2,
                     "start_column_index": 1, "end_column_index": 2}]},
        {"sheet_id": "other99", "grid_properties": {"row_count": 1, "column_count": 1}, "merges": []},
    ]}}
    opener = StubOpener([query_resp])
    client = _client(opener)

    geo = client.read_sheet_geometry(_STRUCT_TOK, "555c22")

    req = opener.requests[0]
    assert req["method"] == "GET"
    assert req["url"].endswith(f"/open-apis/sheets/v3/spreadsheets/{_STRUCT_TOK}/sheets/query")
    assert geo["row_count"] == 9
    assert geo["column_count"] == 5
    assert geo["merges"] == [{"start_row_index": 1, "end_row_index": 2,
                              "start_column_index": 1, "end_column_index": 2}]


def test_read_sheet_geometry_is_none_when_the_sheet_id_is_absent():
    query_resp = {"code": 0, "data": {"sheets": [
        {"sheet_id": "other99", "grid_properties": {"row_count": 1, "column_count": 1}, "merges": []},
    ]}}
    client = _client(StubOpener([query_resp]))
    assert client.read_sheet_geometry(_STRUCT_TOK, "555c22") is None


def test_delete_dimension_range_routes_through_the_transport():
    inner = WriteTransport(max_writes_per_sec=3,
                           time_fn=FakeClock().time, sleep_fn=lambda *_: None)
    spy = CountingTransport(inner)
    opener = StubOpener([_STRUCT["delete_row"]["response"]])
    client = _client(opener, transport=spy)

    client.delete_dimension_range(_STRUCT_TOK, "555c22", "ROWS", 2, 3)

    assert spy.executes == 1  # a structural write is throttled like every other write op


def test_read_sheet_geometry_bypasses_the_write_throttle():
    # a write-side read (the mandatory geometry re-read) is un-throttled, like
    # read_revision / read_values — reads are not write-rate-limited.
    inner = WriteTransport(max_writes_per_sec=3,
                           time_fn=FakeClock().time, sleep_fn=lambda *_: None)
    spy = CountingTransport(inner)
    query_resp = {"code": 0, "data": {"sheets": [
        {"sheet_id": "555c22", "grid_properties": {"row_count": 9, "column_count": 5}, "merges": []},
    ]}}
    opener = StubOpener([query_resp])
    client = _client(opener, transport=spy)

    client.read_sheet_geometry(_STRUCT_TOK, "555c22")

    assert spy.executes == 0  # the geometry re-read never spends throttle budget


# --------------------------------------------------------------------------- #
# LD-122 — merge/unmerge + tab-write client ops. These pin the                  #
# RAW transport bytes against the LD-107 Q1 endpoint-matrix capture             #
# (01-endpoint-matrix.json: merge_cells / unmerge_cells / sheets_batch_update   #
# add·copy·delete). The client is the faithful transport (it forces Start:End   #
# on the range-bearing merge ops — the 90202 guard — and passes the            #
# sheets_batch_update requests[] array through verbatim); the merge-aware       #
# grow/shift/shrink/dissolve semantics live one layer up in the gated engine.   #
# --------------------------------------------------------------------------- #

def test_merge_cells_matches_capture_method_path_body():
    cap = _MATRIX["merge_cells"]  # {range:"154e99!A5:C5", mergeType:"MERGE_ALL"}
    opener = StubOpener([cap["response"]])
    client = _client(opener)

    data = client.merge_cells(_TOK, "154e99!A5:C5", merge_type="MERGE_ALL")

    req = opener.requests[0]
    assert req["method"] == "POST"
    assert req["url"].endswith(cap["path"])
    assert req["body"] == cap["request_body"]
    assert req["auth"] == "Bearer t-test"
    assert data["spreadsheetToken"] == _TOK


def test_merge_cells_defaults_to_merge_all():
    cap = _MATRIX["merge_cells"]
    opener = StubOpener([cap["response"]])
    client = _client(opener)
    client.merge_cells(_TOK, "154e99!A5:C5")
    assert opener.requests[0]["body"]["mergeType"] == "MERGE_ALL"


def test_merge_cells_forces_start_end_on_a_bare_cell():
    # the 90202 guard: a bare single cell is normalized to A1:A1 on the wire.
    opener = StubOpener([{"code": 0, "data": {"spreadsheetToken": _TOK}}])
    client = _client(opener)
    client.merge_cells(_TOK, "154e99!B2")
    assert opener.requests[0]["body"]["range"] == "154e99!B2:B2"


def test_unmerge_cells_matches_capture_method_path_body():
    cap = _MATRIX["unmerge_cells"]  # {range:"154e99!A5:C5"}
    opener = StubOpener([cap["response"]])
    client = _client(opener)

    data = client.unmerge_cells(_TOK, "154e99!A5:C5")

    req = opener.requests[0]
    assert req["method"] == "POST"
    assert req["url"].endswith(cap["path"])
    assert req["body"] == cap["request_body"]
    assert data["spreadsheetToken"] == _TOK


def test_merge_cells_routes_through_the_transport():
    inner = WriteTransport(max_writes_per_sec=3,
                           time_fn=FakeClock().time, sleep_fn=lambda *_: None)
    spy = CountingTransport(inner)
    opener = StubOpener([_MATRIX["merge_cells"]["response"]])
    client = _client(opener, transport=spy)
    client.merge_cells(_TOK, "154e99!A5:C5")
    assert spy.executes == 1  # a merge write is throttled like every other write op


def test_batch_update_sheets_add_matches_capture_and_returns_replies():
    cap = _MATRIX["sheets_batch_update_add"]
    opener = StubOpener([cap["response"]])
    client = _client(opener)

    requests = [{"addSheet": {"properties": {"title": "AddedTab", "index": 1}}}]
    data = client.batch_update_sheets(_TOK, requests)

    req = opener.requests[0]
    assert req["method"] == "POST"
    assert req["url"].endswith(cap["path"])
    assert req["body"] == cap["request_body"]
    # the reply carries the new tab's sheetId
    assert data["replies"][0]["addSheet"]["properties"]["sheetId"] == "2SMeha"


def test_batch_update_sheets_copy_matches_capture():
    cap = _MATRIX["sheets_batch_update_copy"]
    opener = StubOpener([cap["response"]])
    client = _client(opener)

    requests = [{"copySheet": {"source": {"sheetId": "154e99"},
                               "destination": {"title": "CopiedTab"}}}]
    data = client.batch_update_sheets(_TOK, requests)

    assert opener.requests[0]["body"] == cap["request_body"]
    assert data["replies"][0]["copySheet"]["properties"]["sheetId"] == "2SVZvO"


def test_batch_update_sheets_delete_matches_capture():
    cap = _MATRIX["sheets_batch_update_delete"]
    opener = StubOpener([cap["response"]])
    client = _client(opener)

    requests = [{"deleteSheet": {"sheetId": "2SMeha"}}]
    data = client.batch_update_sheets(_TOK, requests)

    assert opener.requests[0]["body"] == cap["request_body"]
    assert data["replies"][0]["deleteSheet"]["result"] is True
    assert data["replies"][0]["deleteSheet"]["sheetId"] == "2SMeha"


def test_batch_update_sheets_routes_through_the_transport():
    inner = WriteTransport(max_writes_per_sec=3,
                           time_fn=FakeClock().time, sleep_fn=lambda *_: None)
    spy = CountingTransport(inner)
    opener = StubOpener([_MATRIX["sheets_batch_update_delete"]["response"]])
    client = _client(opener, transport=spy)
    client.batch_update_sheets(_TOK, [{"deleteSheet": {"sheetId": "2SMeha"}}])
    assert spy.executes == 1


def test_query_tabs_returns_identity_geometry_and_merges_per_tab():
    query_resp = {"code": 0, "data": {"sheets": [
        {"sheet_id": "555c22", "title": "Sheet1", "index": 0,
         "grid_properties": {"row_count": 9, "column_count": 5},
         "merges": [{"start_row_index": 1, "end_row_index": 2,
                     "start_column_index": 1, "end_column_index": 2}]},
        {"sheet_id": "other99", "title": "Sheet2", "index": 1,
         "grid_properties": {"row_count": 1, "column_count": 1}, "merges": []},
    ]}}
    opener = StubOpener([query_resp])
    client = _client(opener)

    tabs = client.query_tabs(_STRUCT_TOK)

    req = opener.requests[0]
    assert req["method"] == "GET"
    assert req["url"].endswith(f"/open-apis/sheets/v3/spreadsheets/{_STRUCT_TOK}/sheets/query")
    assert tabs[0] == {"sheet_id": "555c22", "title": "Sheet1", "index": 0,
                       # LD-187 — `hidden` joins the projection (the field was always on this
                       # endpoint's wire). This payload names none, and an ABSENT flag is
                       # reported as unknown (`None`), never as "visible".
                       "hidden": None,
                       "row_count": 9, "column_count": 5,
                       "merges": [{"start_row_index": 1, "end_row_index": 2,
                                   "start_column_index": 1, "end_column_index": 2}]}
    assert tabs[1]["sheet_id"] == "other99" and tabs[1]["title"] == "Sheet2"


def test_query_tabs_bypasses_the_write_throttle():
    inner = WriteTransport(max_writes_per_sec=3,
                           time_fn=FakeClock().time, sleep_fn=lambda *_: None)
    spy = CountingTransport(inner)
    opener = StubOpener([{"code": 0, "data": {"sheets": []}}])
    client = _client(opener, transport=spy)
    client.query_tabs(_STRUCT_TOK)
    assert spy.executes == 0  # a write-side read never spends throttle budget


# --------------------------------------------------------------------------- #
# LD-148 — the plan-time @mention id check (`validate_user_ids`).               #
#                                                                              #
# The response shapes below are the LIVE ones, probed read-only 2026-07-28 with #
# the WRITE app (log_id 20260728152453A52E092131CF9A78E884). They are the whole #
# reason the check is falsification-based: only a 99992351 field_violation is   #
# proof of non-existence, and a real id can legitimately return NO item.        #
# --------------------------------------------------------------------------- #

_BOGUS_ID = "ou_0000000000000000000000000000dead"
_REAL_ID = "ou_examplebot0000000000000000000001"

#: Live capture: a nonexistent open_id → code 99992351 + per-id `field_violations`.
_INVALID_ID_RESPONSE = {
    "code": 99992351,
    "msg": ("The request you send is not a valid {open_id} or not exists, and the example "
            "value is {ou_da5****************dfe}. Invalid ids: [" + _BOGUS_ID + "] . "
            "Please see field_violations for details"),
    "error": {
        "log_id": "20260728152453A52E092131CF9A78E884",
        "field_violations": [
            {"field": "user_ids", "value": _BOGUS_ID, "description": "id not exist"},
        ],
    },
}

#: Live capture: a REAL open_id on an app with no contact *detail* scope → code 0, items [].
_EXISTS_BUT_UNNAMED_RESPONSE = {"code": 0, "msg": "success", "data": {"items": []}}


def test_validate_user_ids_reports_only_ids_lark_proves_invalid():
    opener = StubOpener([_INVALID_ID_RESPONSE])
    client = _client(opener)

    result = client.validate_user_ids([_BOGUS_ID])

    req = opener.requests[0]
    assert req["method"] == "GET"
    assert "/open-apis/contact/v3/users/batch?" in req["url"]
    assert "user_id_type=open_id" in req["url"] and _BOGUS_ID in req["url"]
    assert result == {"checked": [_BOGUS_ID], "resolved": {}, "invalid": [_BOGUS_ID]}


def test_validate_user_ids_does_not_call_an_existing_id_invalid_when_it_has_no_name():
    """The live trap: code 0 + `items: []` for a REAL id (no contact detail scope). "No
    name" must NEVER be reported as "no such user" — that would refuse a legitimate write."""
    opener = StubOpener([_EXISTS_BUT_UNNAMED_RESPONSE])
    result = _client(opener).validate_user_ids([_REAL_ID])
    assert result == {"checked": [_REAL_ID], "resolved": {}, "invalid": []}


def test_validate_user_ids_reports_names_when_the_scope_does_return_them():
    opener = StubOpener([{"code": 0, "data": {"items": [
        {"open_id": _REAL_ID, "name": "Example"},
        {"open_id": "ou_other", "en_name": "Other"},
    ]}}])
    result = _client(opener).validate_user_ids([_REAL_ID, "ou_other"])
    assert result["resolved"] == {_REAL_ID: "Example", "ou_other": "Other"}
    assert result["invalid"] == []


def test_validate_user_ids_names_only_the_ids_we_actually_asked_about():
    """A drifted / echoed violation for an id the caller never wrote must not make the
    engine refuse it."""
    poisoned = json.loads(json.dumps(_INVALID_ID_RESPONSE))
    poisoned["error"]["field_violations"].append(
        {"field": "user_ids", "value": "ou_never_requested", "description": "id not exist"})
    result = _client(StubOpener([poisoned])).validate_user_ids([_BOGUS_ID])
    assert result["invalid"] == [_BOGUS_ID]


def test_validate_user_ids_reports_nothing_invalid_when_the_body_names_no_id():
    """The code says "invalid ids" but the body carries no parsable violation → refuse
    NOTHING (the check only ever acts on positive proof; the caller then discloses)."""
    vague = {"code": 99992351, "msg": "invalid ids", "error": {}}
    result = _client(StubOpener([vague])).validate_user_ids([_BOGUS_ID])
    assert result["invalid"] == [] and result["checked"] == [_BOGUS_ID]


def test_validate_user_ids_raises_typed_on_a_permission_failure():
    """A missing scope is NOT an id verdict — it raises, so the caller can disclose
    `mention_validation: "unavailable"` instead of pretending the ids were checked."""
    denied = {"code": 99991672, "msg": "no permission to access contact"}
    with pytest.raises(LarkAPIError) as excinfo:
        _client(StubOpener([denied])).validate_user_ids([_REAL_ID])
    assert str(excinfo.value.code) == "99991672"


def test_validate_user_ids_bypasses_the_write_throttle_and_is_a_noop_on_no_ids():
    inner = WriteTransport(max_writes_per_sec=3,
                           time_fn=FakeClock().time, sleep_fn=lambda *_: None)
    spy = CountingTransport(inner)
    opener = StubOpener([_EXISTS_BUT_UNNAMED_RESPONSE])
    client = _client(opener, transport=spy)

    assert client.validate_user_ids([]) == {"checked": [], "resolved": {}, "invalid": []}
    assert opener.requests == [], "no ids ⇒ no call at all"

    client.validate_user_ids([_REAL_ID])
    assert spy.executes == 0, "a write-side read never spends throttle budget"


def test_validate_user_ids_chunks_at_fifty_ids_per_call():
    ids = [f"ou_{i:032d}" for i in range(120)]
    opener = StubOpener([_EXISTS_BUT_UNNAMED_RESPONSE] * 3)
    result = _client(opener).validate_user_ids(ids)
    assert len(opener.requests) == 3, "120 ids ⇒ 50 + 50 + 20"
    assert result["checked"] == ids and result["invalid"] == []
