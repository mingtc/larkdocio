"""The comments read client — pagination that PROVABLY terminates, and a counted throttle.

Two properties are worth more here than any happy path.

**Pagination terminates under a hostile server.** A cursor walk that trusts a "there is
more" flag will spin forever the moment a server sets it without handing back a usable
cursor — and one of the captured list responses really does return a non-empty
``page_token`` alongside ``has_more: false``, so the flag and the cursor genuinely disagree
in the field. The walk here believes the cursor.

**The throttle is proved by COUNT, not by clock.** The endpoints sit on a documented
per-minute tier which this surface honours as documented. Asserting on elapsed time would
be measuring the limit — exactly what this surface must never do — so the limiter is a real
one that counts its acquisitions.
"""
import comments_harness as harness
import comments_payloads as payloads
import pytest

from larkdocio.comments import CommentsReadClient
from larkdocio.comments.client import (
    COMMENTS_RATE_WINDOW_SECONDS,
    DEFAULT_MAX_READS_PER_WINDOW,
    MAX_PAGES,
)
from larkdocio.errors import LarkAPIError, LarkConfigError, LarkRateLimitError

_ITEM = payloads.LIST_ONE_PAGE["data"]["items"][0]


def _items(*ids):
    return [dict(_ITEM, comment_id=cid) for cid in ids]


# --------------------------------------------------------------------------- #
# AC6 — pagination at 1, 2 and 3 pages, plus every non-termination shape.        #
# --------------------------------------------------------------------------- #

def test_a_single_page_is_one_call():
    client = harness.client({"list": payloads.LIST_ONE_PAGE})
    got = client.list_comments("doc-token")

    assert [c.comment_id for c in got] == ["7667710952829095653"]
    assert client._sdk.ops == ["list"]


def test_two_pages_are_followed_to_exhaustion():
    pages = harness.paged_list([
        (_items("c1", "c2"), True, "cursor-2"),
        (_items("c3"), False, ""),
    ])
    client = harness.client({"list": pages})

    got = client.list_comments("doc-token")

    assert [c.comment_id for c in got] == ["c1", "c2", "c3"]
    assert client._sdk.page_tokens == [("list", None), ("list", "cursor-2")]


def test_three_pages_are_followed_to_exhaustion():
    pages = harness.paged_list([
        (_items("c1"), True, "cursor-2"),
        (_items("c2"), True, "cursor-3"),
        (_items("c3"), False, None),
    ])
    client = harness.client({"list": pages})

    got = client.list_comments("doc-token")

    assert [c.comment_id for c in got] == ["c1", "c2", "c3"]
    assert client._sdk.page_tokens == [
        ("list", None), ("list", "cursor-2"), ("list", "cursor-3")]


@pytest.mark.parametrize("bad_token", ["", None])
def test_has_more_true_with_no_usable_cursor_TERMINATES(bad_token):
    """The malformed-server case. Believe the cursor, not the flag."""
    pages = harness.paged_list([(_items("c1"), True, bad_token)])
    client = harness.client({"list": pages})

    got = client.list_comments("doc-token")

    assert [c.comment_id for c in got] == ["c1"]
    assert len(client._sdk.calls) == 1, "the walk asked again with nothing to ask for"


def test_a_server_that_repeats_its_cursor_TERMINATES():
    """The transport that would otherwise loop forever: every page says "more", and hands
    back the cursor it was just given."""
    page = harness.paged_list([(_items("c1"), True, "same-cursor")])
    client = harness.client({"list": page})   # the queue re-serves its last body

    got = client.list_comments("doc-token")

    assert [c.comment_id for c in got] == ["c1", "c1"], (
        "expected exactly one repeat before the cursor is recognized as already used")
    assert len(client._sdk.calls) == 2
    assert len(client._sdk.calls) < MAX_PAGES


def test_the_captured_page_token_beside_has_more_false_does_NOT_cause_a_second_call():
    """The real captured list response carries ``has_more: false`` AND a non-empty
    ``page_token`` (the id of the last item). A walk keyed on the token's presence would
    fetch a phantom second page on every ordinary document."""
    assert payloads.LIST_ONE_PAGE["data"]["page_token"], "fixture drift"
    assert payloads.LIST_ONE_PAGE["data"]["has_more"] is False

    client = harness.client({"list": payloads.LIST_ONE_PAGE})
    client.list_comments("doc-token")
    assert len(client._sdk.calls) == 1


def test_the_reply_list_walk_paginates_too():
    pages = [payloads.REPLY_LIST_ONE_PAGE]
    pages[0] = {"code": 0, "msg": "Success", "data": {
        **payloads.REPLY_LIST_ONE_PAGE["data"], "has_more": True,
        "page_token": "reply-cursor-2"}}
    pages.append(payloads.REPLY_LIST_PAGE_TWO)
    client = harness.client({"reply_list": pages})

    got = client.list_replies("doc-token", "comment-1")

    assert [r.reply_id for r in got] == ["7667710952845889243", "reply-2"]


# --------------------------------------------------------------------------- #
# AC7 — the throttle, counted.                                                  #
# --------------------------------------------------------------------------- #

def test_every_call_acquires_the_shared_limiter():
    limiter = harness.SpyLimiter()
    pages = harness.paged_list([
        (_items("c1"), True, "cursor-2"),
        (_items("c2"), False, ""),
    ])
    client = harness.client({"list": pages}, limiter=limiter)

    client.list_comments("doc-token")

    assert limiter.acquisitions == 2 == len(client._sdk.calls), (
        "acquisitions must equal API calls — one page, one slot")


def test_the_batch_fetch_and_the_reply_list_are_throttled_too():
    limiter = harness.SpyLimiter()
    client = harness.client(
        {"batch_query": payloads.BATCH_QUERY_ONE,
         "reply_list": payloads.REPLY_LIST_ONE_PAGE},
        limiter=limiter,
    )

    client.batch_query_comments("doc-token", ["c1"])
    client.list_replies("doc-token", "c1")

    assert limiter.acquisitions == 2 == len(client._sdk.calls)


def test_the_limiter_is_the_SHARED_transport_primitive_at_a_documented_tier():
    """Not a private re-implementation, and paced under the documented per-minute tier."""
    from larkdocio.common.transport import RateLimiter

    client = CommentsReadClient("cli_x", "secret", sdk_client=harness.FakeSdk())
    assert isinstance(client.limiter, RateLimiter)
    assert client.limiter.window == COMMENTS_RATE_WINDOW_SECONDS == 60.0
    assert client.limiter.max_per_sec == DEFAULT_MAX_READS_PER_WINDOW
    assert DEFAULT_MAX_READS_PER_WINDOW < 100, (
        "the client-side cap must sit BELOW the documented 100-per-window tier")


def test_no_call_bypasses_the_pace():
    """Structural, not per-endpoint: every request in the client is issued through the one
    paced helper, so an endpoint added later cannot quietly skip the throttle."""
    import ast
    import inspect

    from larkdocio.comments import client as client_mod

    tree = ast.parse(inspect.getsource(client_mod))
    unpaced = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Any attribute call reaching into the SDK client object.
        if isinstance(func, ast.Attribute) and "_sdk" in ast.dump(func):
            unpaced.append(ast.unparse(node))
    assert unpaced == [], (
        f"these SDK calls are made directly instead of through the paced helper: {unpaced}")


# --------------------------------------------------------------------------- #
# Typed failures + the zero-ids rule.                                           #
# --------------------------------------------------------------------------- #

def test_zero_comment_ids_makes_NO_call_at_all():
    client = harness.client({"batch_query": payloads.BATCH_QUERY_ONE})
    assert client.batch_query_comments("doc-token", []) == []
    assert client._sdk.calls == []
    assert client.api_calls == 0


@pytest.mark.parametrize("code", [1069307, 1069304, 9499, 99992402])
def test_a_non_zero_code_raises_the_typed_error_carrying_it(code):
    client = harness.client({"list": harness.error_body(code, "nope")})
    with pytest.raises(LarkAPIError) as excinfo:
        client.list_comments("doc-token")
    assert excinfo.value.code == code
    assert excinfo.value.msg == "nope"


def test_a_rate_limit_code_raises_the_rate_limit_subclass():
    client = harness.client({"list": harness.error_body(99991400, "too fast")})
    with pytest.raises(LarkRateLimitError):
        client.list_comments("doc-token")


def test_missing_credentials_raise_a_config_error_not_a_bare_exception():
    with pytest.raises(LarkConfigError):
        CommentsReadClient("", "")


# --------------------------------------------------------------------------- #
# Request shaping — the file type and the id form actually go on the wire.       #
# --------------------------------------------------------------------------- #

def test_the_file_type_and_id_form_are_sent_on_every_endpoint():
    client = harness.client({
        "list": payloads.LIST_ONE_PAGE,
        "batch_query": payloads.BATCH_QUERY_ONE,
        "reply_list": payloads.REPLY_LIST_ONE_PAGE,
    })
    client.list_comments("doc-token", file_type="sheet")
    client.batch_query_comments("doc-token", ["c1"], file_type="sheet")
    client.list_replies("doc-token", "c1", file_type="sheet")

    for _op, request in client._sdk.calls:
        assert request.file_type == "sheet"
        assert request.user_id_type == "open_id"


def test_the_batch_fetch_sends_the_ids_it_was_given():
    client = harness.client({"batch_query": payloads.BATCH_QUERY_ONE})
    client.batch_query_comments("doc-token", ["a", "b", "c"])
    request = client._sdk.requests_for("batch_query")[0]
    assert request.request_body.comment_ids == ["a", "b", "c"]
