"""Offline unit tests for the write-side client (LD-064).

The write client is NEW infrastructure the W0 harness builds on. It rides the S2
shared core (``WriteTransport`` throttle + ``99991400`` backoff,
``fetch_tenant_access_token``) and raises the S1 typed errors. These pin, all
offline (a fake clock + a stub opener, no network), the parts of AC1 that are
offline-testable:

* ``to_write_elements`` rebuilds runs preserving per-run style (no lossy Markdown
  round-trip) — the spike Appendix pattern element patches must follow;
* the client speaks the right docx v1 method/path/body for create-document,
  create-children, patch (``update_text_elements``), and batch-delete, carrying a
  bearer token;
* writes are **throttled** through S2's ``WriteTransport`` (≤3 writes/sec) and a
  non-zero Lark ``code`` raises the S1 typed error via ``raise_for_lark_code``.

The live round-trip (AC4) is the ``live_write`` ring in
``tests/test_live_write_harness.py`` — the binding W0 gate — not here.
"""

import json

import pytest

from larkdocio.write.client import WriteClient, to_write_elements
from larkdocio.common.transport import WriteTransport
from larkdocio.errors import LarkAPIError, LarkRateLimitError

from write_harness import FakeClock, _FakeHTTPResponse


# --------------------------------------------------------------------------- #
# AC1 — to_write_elements: style-preserving run rebuild                         #
# --------------------------------------------------------------------------- #

def test_to_write_elements_preserves_per_run_style():
    """A bold run and an inline_code run keep their flags; a plain run carries no
    style key. Rebuild is element-level, not a lossy Markdown round-trip."""
    read_elements = [
        {"text_run": {"content": "plain ", "text_element_style": {}}},
        {"text_run": {"content": "bold", "text_element_style": {"bold": True}}},
        {"text_run": {"content": "code", "text_element_style": {"inline_code": True}}},
    ]
    out = to_write_elements(read_elements)

    assert out == [
        {"text_run": {"content": "plain "}},
        {"text_run": {"content": "bold", "text_element_style": {"bold": True}}},
        {"text_run": {"content": "code", "text_element_style": {"inline_code": True}}},
    ]


def test_to_write_elements_carries_color_and_link_style():
    read_elements = [
        {"text_run": {"content": "hi", "text_element_style": {
            "text_color": 5, "background_color": 2,
            "link": {"url": "https%3A%2F%2Fx"}}}},
    ]
    out = to_write_elements(read_elements)
    style = out[0]["text_run"]["text_element_style"]
    assert style["text_color"] == 5
    assert style["background_color"] == 2
    assert style["link"] == {"url": "https%3A%2F%2Fx"}


def test_to_write_elements_mutate_changes_content_but_not_style():
    read_elements = [
        {"text_run": {"content": "before", "text_element_style": {"bold": True}}},
    ]
    out = to_write_elements(read_elements, mutate=lambda c: c.replace("before", "after"))
    assert out == [
        {"text_run": {"content": "after", "text_element_style": {"bold": True}}},
    ]


def test_to_write_elements_passes_non_text_runs_through_dropping_none():
    """A non-text element (e.g. a mention) is passed through with its None-valued
    keys dropped (the shape the write API accepts)."""
    read_elements = [
        {"text_run": None, "mention_user": {"user_id": "ou_x"}, "equation": None},
    ]
    out = to_write_elements(read_elements)
    assert out == [{"mention_user": {"user_id": "ou_x"}}]


def test_to_write_elements_handles_empty():
    assert to_write_elements(None) == []
    assert to_write_elements([]) == []


# --------------------------------------------------------------------------- #
# Test doubles for the offline client tests                                    #
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


def _client(opener, clock=None, **kw):
    clock = clock or FakeClock()
    transport = WriteTransport(
        max_writes_per_sec=3, time_fn=clock.time, sleep_fn=clock.sleep
    )
    return WriteClient(
        "app", "secret", "larksuite.com",
        transport=transport,
        urlopen=opener,
        token_fetcher=lambda *a, **k: "t-test",
        **kw,
    )


# --------------------------------------------------------------------------- #
# AC1 — client speaks the right docx v1 requests, carrying the bearer token     #
# --------------------------------------------------------------------------- #

def test_create_document_posts_title_and_returns_document():
    opener = StubOpener([
        {"code": 0, "data": {"document": {"document_id": "doc123", "revision_id": 1}}},
    ])
    client = _client(opener)

    doc = client.create_document(title="harness", folder_token="fldExample25")

    assert doc == {"document_id": "doc123", "revision_id": 1}
    req = opener.requests[0]
    assert req["method"] == "POST"
    assert req["url"].endswith("/open-apis/docx/v1/documents")
    assert req["body"] == {"title": "harness", "folder_token": "fldExample25"}
    assert req["auth"] == "Bearer t-test"


def test_create_children_posts_children_at_index():
    opener = StubOpener([
        {"code": 0, "data": {"children": [{"block_id": "b1"}]}},
    ])
    client = _client(opener)

    children = [{"block_type": 2, "text": {"elements": [{"text_run": {"content": "x"}}]}}]
    data = client.create_children("doc123", "doc123", children, index=0)

    assert data == {"children": [{"block_id": "b1"}]}
    req = opener.requests[0]
    assert req["method"] == "POST"
    assert "/open-apis/docx/v1/documents/doc123/blocks/doc123/children" in req["url"]
    assert req["body"] == {"index": 0, "children": children}


def test_the_private_patch_block_sends_update_text_elements():
    opener = StubOpener([{"code": 0, "data": {"block": {"block_id": "b1"}}}])
    client = _client(opener)

    update = {"update_text_elements": {"elements": [{"text_run": {"content": "after"}}]}}
    client._patch_block("doc123", "b1", update)

    req = opener.requests[0]
    assert req["method"] == "PATCH"
    assert "/open-apis/docx/v1/documents/doc123/blocks/b1" in req["url"]
    assert req["body"] == update


def test_batch_delete_sends_child_range():
    opener = StubOpener([{"code": 0, "data": {}}])
    client = _client(opener)

    client.batch_delete("doc123", "doc123", 0, 3)

    req = opener.requests[0]
    assert req["method"] == "DELETE"
    assert "/blocks/doc123/children/batch_delete" in req["url"]
    assert req["body"] == {"start_index": 0, "end_index": 3}


# --------------------------------------------------------------------------- #
# AC1 — writes ride the S2 throttle (≤3 writes/sec) and raise S1 typed errors   #
# --------------------------------------------------------------------------- #

def test_writes_are_throttled_through_the_shared_transport():
    """A 4th write in the same second is paced by S2's RateLimiter (≤3/sec)."""
    clock = FakeClock()
    opener = StubOpener([{"code": 0, "data": {}} for _ in range(4)])
    client = _client(opener, clock=clock)

    for _ in range(4):
        client.batch_delete("doc123", "doc123", 0, 1)

    assert clock.sleeps == [1.0]   # the 4th write waited one full window


def test_non_zero_code_raises_typed_api_error():
    opener = StubOpener([{"code": 1770001, "msg": "invalid param"}])
    client = _client(opener)

    with pytest.raises(LarkAPIError) as ei:
        client.create_children("doc123", "doc123", [], index=-1)
    assert ei.value.code == 1770001
    assert ei.value.msg == "invalid param"


def test_rate_limit_code_backs_off_then_succeeds():
    """A 99991400 then a success is retried by the shared transport (S2 backoff)."""
    clock = FakeClock()
    opener = StubOpener([
        {"code": "99991400", "msg": "rate"},
        {"code": 0, "data": {"document": {"document_id": "doc9"}}},
    ])
    client = _client(opener, clock=clock)

    doc = client.create_document(title="x", folder_token="fldExample25")
    assert doc == {"document_id": "doc9"}
    assert len(opener.requests) == 2   # retried once after backoff


def test_rate_limit_exhausted_raises_typed_rate_limit():
    clock = FakeClock()
    opener = StubOpener([{"code": "99991400", "msg": "rate"} for _ in range(10)])
    transport = WriteTransport(
        max_writes_per_sec=1000, max_retries=2,
        time_fn=clock.time, sleep_fn=clock.sleep,
    )
    client = WriteClient(
        "app", "secret", "larksuite.com",
        transport=transport, urlopen=opener,
        token_fetcher=lambda *a, **k: "t-test",
    )
    with pytest.raises(LarkRateLimitError):
        client.create_document(title="x", folder_token="fldExample25")
