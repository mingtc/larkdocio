"""The offline transport double for the comments read — and the spies the ACs need.

**The double replaces the network and nothing else.** :class:`FakeSdk` stands where the
pinned SDK client stands and answers each call by **deserializing a captured response body
through the SDK's own response class** — so the objects the shipped client receives are the
objects a real call would produce, ``is_whole`` omissions and all. Nothing about the request
building, the pagination walk, the pacing or the error typing is faked.

**Three spies, because three acceptance criteria are about calls not made.**

* :attr:`FakeSdk.calls` records every endpoint touched, in order — so "no comment ids means
  no call at all" is an assertion about the transport, not a hopeful read of the code.
* :attr:`FakeSdk.paths` records the endpoint **path** of each call, so "the identity service
  is never consulted" is checked against what was actually sent rather than against an
  import list. Any call outside the comment family shows up here as itself.
* :class:`SpyLimiter` counts acquisitions, so the throttle is proved **by count** and never
  by measuring elapsed time — this surface honours a documented tier, it does not discover
  one by walking into it.
"""
import json
from typing import Dict, List, Optional

from lark_oapi.api.drive.v1 import (
    BatchQueryFileCommentResponse,
    ListFileCommentReplyResponse,
    ListFileCommentResponse,
)
from lark_oapi.core import JSON
from lark_oapi.core.model import RawResponse

from larkdocio.common.transport import RateLimiter

#: The endpoint paths the comment family uses, keyed by the operation this double serves.
#: Recorded per call so a test can assert on what was requested, including that nothing
#: outside this table was.
PATHS = {
    "list": "/open-apis/drive/v1/files/:file_token/comments",
    "batch_query": "/open-apis/drive/v1/files/:file_token/comments/batch_query",
    "reply_list": "/open-apis/drive/v1/files/:file_token/comments/:comment_id/replies",
}

_RESPONSE_CLASSES = {
    "list": ListFileCommentResponse,
    "batch_query": BatchQueryFileCommentResponse,
    "reply_list": ListFileCommentReplyResponse,
}


class SpyLimiter(RateLimiter):
    """A real limiter that also counts acquisitions.

    A subclass rather than a stub, so the shipped pacing code runs unchanged; the clock and
    sleep are stubbed out so counting is instant and no test ever sleeps.
    """

    def __init__(self, max_per_sec=1000, window=60.0):
        self.acquisitions = 0
        self._now = 0.0
        super().__init__(max_per_sec, window=window,
                         time_fn=lambda: self._now, sleep_fn=self._advance)

    def _advance(self, seconds):
        self._now += seconds

    def acquire(self):
        self.acquisitions += 1
        super().acquire()


class FakeSdk:
    """Stands in for the SDK client at the network boundary.

    ``responses`` maps an operation name (``list`` / ``batch_query`` / ``reply_list``) to the
    captured response **bodies** to serve, in order. A single dict is shorthand for a
    one-element queue. The last body of a queue is re-served if the client asks again, so a
    test that means "this endpoint always answers X" says it once.
    """

    def __init__(self, responses: Optional[Dict[str, object]] = None):
        self.responses: Dict[str, List[dict]] = {}
        for op, value in (responses or {}).items():
            self.responses[op] = list(value) if isinstance(value, list) else [value]
        #: ``[(op, request)]`` in call order.
        self.calls: List[tuple] = []
        #: the endpoint path of each call, in order.
        self.paths: List[str] = []
        #: ``[(op, page_token)]`` in call order — the cursor walk, visible.
        self.page_tokens: List[tuple] = []
        self._served: Dict[str, int] = {}
        self.drive = _Drive(self)

    def _answer(self, op: str, request):
        self.calls.append((op, request))
        self.paths.append(PATHS[op])
        self.page_tokens.append((op, getattr(request, "page_token", None)))
        queue = self.responses.get(op)
        assert queue, f"the double was asked for {op!r} with no response queued"
        index = min(self._served.get(op, 0), len(queue) - 1)
        self._served[op] = index + 1
        body = queue[index]
        serialized = json.dumps(body)
        response = JSON.unmarshal(serialized, _RESPONSE_CLASSES[op])
        # The real SDK hangs the untouched response bytes off `raw` before handing the typed
        # object back (`Transport.execute` → `response.raw = resp`). The double does the
        # same, because a key the SDK's typed model does not declare — `extra.notify_extra`,
        # which is how a Base comment names its row — is readable ONLY from those bytes.
        raw = RawResponse()
        raw.status_code = 200
        raw.content = serialized.encode("utf-8")
        response.raw = raw
        return response

    # ---- assertions a test reads ------------------------------------------ #

    @property
    def ops(self) -> List[str]:
        """Just the operation names, in call order."""
        return [op for op, _req in self.calls]

    def requests_for(self, op: str) -> List:
        return [req for name, req in self.calls if name == op]


class _Drive:
    def __init__(self, sdk):
        self.v1 = _DriveV1(sdk)


class _DriveV1:
    def __init__(self, sdk):
        self.file_comment = _FileComment(sdk)
        self.file_comment_reply = _FileCommentReply(sdk)


class _FileComment:
    def __init__(self, sdk):
        self._sdk = sdk

    def list(self, request, option=None):
        return self._sdk._answer("list", request)

    def batch_query(self, request, option=None):
        return self._sdk._answer("batch_query", request)


class _FileCommentReply:
    def __init__(self, sdk):
        self._sdk = sdk

    def list(self, request, option=None):
        return self._sdk._answer("reply_list", request)


def client(responses=None, *, limiter=None, **kwargs):
    """A shipped :class:`~larkdocio.comments.client.CommentsReadClient` on the double."""
    from larkdocio.comments import CommentsReadClient

    return CommentsReadClient(
        "cli_offline", "secret-offline", "larksuite.com",
        sdk_client=FakeSdk(responses),
        rate_limiter=limiter if limiter is not None else SpyLimiter(),
        **kwargs,
    )


def paged_list(pages):
    """Build a ``list`` response queue from ``[(items, has_more, page_token)]`` triples."""
    return [
        {"code": 0, "msg": "Success",
         "data": {"items": items, "has_more": has_more, "page_token": token}}
        for items, has_more, token in pages
    ]


def error_body(code, msg="failed"):
    """A Lark error envelope for the graceful-degrade arms."""
    return {"code": code, "msg": msg, "error": {"log_id": "offline"}}
