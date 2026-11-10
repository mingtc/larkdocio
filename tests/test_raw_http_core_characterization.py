"""Characterization tests for the shared raw-HTTP core (LD-126 / T2 safety net).

These pin the **FOUR DELIBERATE behavioral differences** the T2 transport
extraction must *preserve* (audit § T2) — the behaviors a naive "de-dupe" would
silently flatten. They assert **current** behavior on the pre-move code, so the
extraction into ``common/transport.py`` cannot quietly homogenize any of them.
This file lands *before* any move (safety-net-check Phase 4).

* **B1 — non-2xx (HTTPError) posture.** The three JSON clients (``SheetsReadClient``,
  the docx ``WriteClient``, ``SheetsWriteClient``) **PARSE the Lark error body and
  RETURN it as a dict at the raw layer — they never raise there**: that is what lets
  the docx/sheets write transport *see* a ``99991400`` and back off, and lets
  ``raise_for_lark_code`` type the rest one layer up. A non-JSON error body degrades
  to ``{"code": <http>, "msg": "HTTP <http>"}`` — still no raise. ``SheetsExportReader``
  is the opposite: it **RAISES ``LarkAPIError`` on any ``HTTPError``** (it returns raw
  bytes, so it has no dict to hand a code-typing wrapper).
* **B2 — GET-only vs body-bearing** — the read client is GET-only; the writers carry
  bodies. (Pinned by the client suites' method/body assertions; reinforced end-to-end
  here via B1's typed-error paths.)
* **B3 — JSON dict returns (three clients) vs raw BYTES (export download).**
* **B4 — inline-cred token fetch (threading ``urlopen=self._urlopen`` into the
  fetcher) vs the ``export_reader`` ``token_provider`` indirection (a zero-arg
  callable — no creds, no urlopen threaded — lazily cached).**

The raw layer's own method names (``_raw_get`` / ``_raw_request`` / ``_request_bytes``)
are pinned by name deliberately: T2 keeps them as thin delegators over the shared
core, so these are stable anchors for the contract, not incidental internals.
"""
import io
import json
import urllib.error

import pytest

from larkdocio.sheets.client import SheetsReadClient
from larkdocio.write.client import WriteClient
from larkdocio.sheets.write_client import SheetsWriteClient
from larkdocio.sheets.export_reader import SheetsExportReader
from larkdocio.errors import LarkAPIError, LarkRateLimitError


# --------------------------------------------------------------------------- #
# Test doubles                                                                  #
# --------------------------------------------------------------------------- #

class _Resp:
    def __init__(self, body: bytes):
        self._b = body

    def read(self):
        return self._b


class SeqOpener:
    """Serves queued items in order. An item may be an ``Exception`` (raised — e.g.
    an ``HTTPError``), raw ``bytes`` (served verbatim), or a dict (JSON-encoded)."""

    def __init__(self, items):
        self._items = list(items)
        self.calls = []

    def __call__(self, req, timeout=30):
        self.calls.append({
            "method": req.get_method(),
            "url": req.full_url,
            "body": json.loads(req.data.decode()) if req.data else None,
            "auth": req.headers.get("Authorization"),
        })
        item = self._items[len(self.calls) - 1]
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, (bytes, bytearray)):
            return _Resp(bytes(item))
        return _Resp(json.dumps(item).encode())


def _http_error(code, body):
    """An ``HTTPError`` whose ``.read()`` yields ``body`` (a dict → JSON, or bytes)."""
    raw = body if isinstance(body, (bytes, bytearray)) else json.dumps(body).encode()
    return urllib.error.HTTPError("http://x/p", code, "err", {}, io.BytesIO(bytes(raw)))


def _read_client(opener):
    return SheetsReadClient("A", "S", "larksuite.com",
                            urlopen=opener, token_fetcher=lambda *a, **k: "t")


def _write_client(opener):
    return WriteClient("A", "S", "larksuite.com",
                       urlopen=opener, token_fetcher=lambda *a, **k: "t")


def _sheets_write_client(opener):
    return SheetsWriteClient("A", "S", "larksuite.com",
                             urlopen=opener, token_fetcher=lambda *a, **k: "t")


def _export_reader(opener):
    return SheetsExportReader(token_provider=lambda: "t", urlopen=opener)


# --------------------------------------------------------------------------- #
# B1 — the HTTPError posture: three clients RETURN a dict, export RAISES         #
# --------------------------------------------------------------------------- #

def test_b1_read_client_raw_get_returns_dict_never_raises():
    """The read client's raw layer parses a Lark JSON error body and RETURNS it;
    a non-JSON body degrades to the ``{"code": <http>, "msg": "HTTP <http>"}``
    fallback — either way it never raises on an HTTPError."""
    c = _read_client(SeqOpener([_http_error(400, {"code": 90202, "msg": "wrong range"})]))
    assert c._raw_get("/p") == {"code": 90202, "msg": "wrong range"}

    c2 = _read_client(SeqOpener([_http_error(503, b"<html>nope</html>")]))
    assert c2._raw_get("/p") == {"code": 503, "msg": "HTTP 503"}


def test_b1_read_client_http_error_is_typed_one_layer_up():
    """End-to-end: because the raw layer returned the dict, ``_get``'s
    ``raise_for_lark_code`` types it — a non-JSON 503 surfaces as code 503 /
    ``HTTP 503`` (NOT a raw-layer raise with a different message shape)."""
    c = _read_client(SeqOpener([_http_error(503, b"<html>nope</html>")]))
    with pytest.raises(LarkAPIError) as ei:
        c.get_values("tok", "s!A1:B2")
    assert ei.value.code == 503
    assert ei.value.msg == "HTTP 503"
    assert not isinstance(ei.value, LarkRateLimitError)


def test_b1_docx_write_client_raw_request_returns_dict_never_raises():
    """The docx write client's raw layer RETURNS the parsed error dict — this is
    what lets the WriteTransport see a 99991400 (delivered as an HTTP 400) and back
    off, rather than the raw layer swallowing/raising it."""
    c = _write_client(SeqOpener([_http_error(400, {"code": "99991400", "msg": "rate"})]))
    assert c._raw_request("POST", "/p", {"x": 1}) == {"code": "99991400", "msg": "rate"}

    c2 = _write_client(SeqOpener([_http_error(500, b"oops")]))
    assert c2._raw_request("POST", "/p") == {"code": 500, "msg": "HTTP 500"}


def test_b1_docx_write_client_http_error_99991400_backs_off_then_succeeds():
    """End-to-end through the transport: a 99991400 delivered as an HTTPError (the
    real wire shape) is retried after backoff — proof the return-a-dict posture is
    load-bearing for the throttle."""
    class _FakeClock:
        def __init__(self):
            self.now, self.sleeps = 0.0, []

        def time(self):
            return self.now

        def sleep(self, dt):
            self.sleeps.append(dt)
            self.now += dt

    from larkdocio.common.transport import WriteTransport
    clock = _FakeClock()
    opener = SeqOpener([
        _http_error(400, {"code": "99991400", "msg": "rate"}),
        {"code": 0, "data": {"document": {"document_id": "doc9"}}},
    ])
    client = WriteClient("A", "S", "larksuite.com",
                         transport=WriteTransport(time_fn=clock.time, sleep_fn=clock.sleep),
                         urlopen=opener, token_fetcher=lambda *a, **k: "t")
    doc = client.create_document(title="x", folder_token="fldExample25")
    assert doc == {"document_id": "doc9"}
    assert len(opener.calls) == 2  # retried once after the HTTPError-delivered 99991400


def test_b1_sheets_write_client_raw_request_returns_dict_never_raises():
    c = _sheets_write_client(SeqOpener([_http_error(400, {"code": 90202, "msg": "wrong range=x"})]))
    assert c._raw_request("PUT", "/p", {"x": 1}) == {"code": 90202, "msg": "wrong range=x"}

    c2 = _sheets_write_client(SeqOpener([_http_error(500, b"<html/>")]))
    assert c2._raw_request("PUT", "/p") == {"code": 500, "msg": "HTTP 500"}


def test_b1_export_reader_raises_on_http_error_never_returns_dict():
    """The opposite posture: the export reader RAISES on any HTTPError. A non-JSON
    body raises a bare ``<method> <path> failed: HTTP <code>``; a JSON body with a
    non-zero code raises the typed error carrying that code."""
    r = _export_reader(SeqOpener([_http_error(500, b"<html>err</html>")]))
    with pytest.raises(LarkAPIError) as ei:
        r._request_bytes("GET", "/p")
    assert "failed: HTTP 500" in str(ei.value)

    r2 = _export_reader(SeqOpener([_http_error(400, {"code": 1069902, "msg": "denied"})]))
    with pytest.raises(LarkAPIError) as ei2:
        r2._request_bytes("GET", "/p")
    assert ei2.value.code == 1069902


# --------------------------------------------------------------------------- #
# B3 — JSON dict returns vs raw BYTES                                            #
# --------------------------------------------------------------------------- #

def test_b3_export_reader_returns_raw_bytes_verbatim():
    """The export reader's raw layer returns the response BYTES unparsed (the xlsx
    download) — no ``json.loads``."""
    payload = b"PK\x03\x04 binary xlsx bytes \xff\xfe not json"
    r = _export_reader(SeqOpener([payload]))
    assert r._request_bytes("GET", "/download") == payload


def test_b3_json_clients_parse_the_body_to_a_dict():
    c = _read_client(SeqOpener([{"code": 0, "data": {"ok": 1}}]))
    assert c._raw_get("/p") == {"code": 0, "data": {"ok": 1}}


# --------------------------------------------------------------------------- #
# B4 — inline-cred token fetch (urlopen threaded) vs zero-arg token_provider     #
# --------------------------------------------------------------------------- #

def test_b4_inline_clients_thread_urlopen_into_the_token_fetcher():
    """The three credentialed clients fetch the tenant token with their inline
    ``app_id``/``app_secret``/``domain`` AND thread ``urlopen=self._urlopen`` into
    the fetcher (so the token fetch shares the injected opener)."""
    captured = {}

    def fetcher(app_id, app_secret, domain, urlopen=None, **k):
        captured["args"] = (app_id, app_secret, domain)
        captured["urlopen_is_injected"] = urlopen is opener
        return "tok"

    opener = SeqOpener([{"code": 0, "data": {}}])
    c = SheetsReadClient("APPID", "SECRET", "larksuite.com",
                         urlopen=opener, token_fetcher=fetcher)
    c._raw_get("/p")

    assert captured["args"] == ("APPID", "SECRET", "larksuite.com")
    assert captured["urlopen_is_injected"] is True


def test_b4_export_reader_uses_a_zero_arg_cached_token_provider():
    """The export reader resolves its bearer through a zero-arg ``token_provider``
    (no creds/urlopen threaded), lazily cached — a second request does not
    re-invoke the provider."""
    seen = {"count": 0}

    def provider():
        seen["count"] += 1
        return "tok-x"

    r = SheetsExportReader(token_provider=provider, urlopen=SeqOpener([b"a", b"b"]))
    r._request_bytes("GET", "/p")
    r._request_bytes("GET", "/p2")
    assert seen["count"] == 1  # zero-arg, and cached after the first fetch
