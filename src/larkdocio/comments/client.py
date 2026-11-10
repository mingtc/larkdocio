"""The throttled comments read client — the pinned SDK's typed models, paced by our limiter.

**Why the SDK and not raw HTTP.** The rest of this library reaches the document APIs through
the pinned ``lark-oapi`` SDK and reaches the spreadsheet value APIs with raw ``urllib``. That
split is not a preference: the spreadsheet endpoints in question are simply **absent** from
the SDK, so there was nothing to call. The comment family is the opposite case — the SDK
ships the whole family, request builders and response models alike, for listing comments,
fetching a batch of them by id, and listing one comment's replies. Hand-rolling a second
HTTP path against endpoints that already have typed models would add a URL, a query-string
encoder and an error-envelope parser this library would then own forever, and would throw
away the deserializer whose *omit-what-was-omitted* behaviour is what keeps an unreported
field distinguishable from a false one. So: the SDK.

**What the SDK does not bring, and this client does.**

* **Pacing.** The SDK client has no notion of this library's rate policy, so every call here
  passes through the shared limiter first. The batch-fetch and reply-list endpoints sit on a
  documented tier of 100 requests per minute; this client is capped **below** it and the tier
  is honoured **as documented** — nothing here measures a limit by walking into one.
* **Termination.** Both paged endpoints are followed to exhaustion, and the loop is written
  so that a server answering "there is more" without a usable cursor — or answering with the
  cursor it was just given — ends the walk instead of spinning forever.
* **Typed failures.** A non-zero response code is raised as this library's own error type,
  carrying the code and message, so callers pattern-match on one taxonomy.

This client makes **only** comment-family calls. In particular it never asks the directory
service to turn an author id into a name: that call is not available on this library's read
scope, and a name it cannot obtain is not a name it will guess.
"""
from typing import Dict, List, Optional

from lark_oapi.api.drive.v1 import (
    BatchQueryFileCommentRequest,
    BatchQueryFileCommentRequestBody,
    FileComment,
    FileCommentReply,
    ListFileCommentReplyRequest,
    ListFileCommentRequest,
)

from larkdocio.comments.attribution import BaseAttribution, attributions_from_raw
from larkdocio.common.auth import get_read_credentials
from larkdocio.common.transport import RateLimiter
from larkdocio.common.auth import resolved_read_env
from larkdocio.common.sdk_client import (
    require_credentials,
    resolve_rate_limiter,
    resolve_sdk_client,
)
from larkdocio.errors import api_error

#: The window the documented tier is expressed over: one minute.
COMMENTS_RATE_WINDOW_SECONDS = 60.0

#: Client-side cap per :data:`COMMENTS_RATE_WINDOW_SECONDS`, deliberately **below** the
#: documented 100-per-minute tier for the batch-fetch and reply-list endpoints. One literal
#: so re-pacing the surface is a one-line edit, and comfortably above what any real document
#: needs: a document's whole comment set is one paged list plus one batch fetch.
DEFAULT_MAX_READS_PER_WINDOW = 60

#: Page size requested on both paged endpoints. Well inside the API's own ceiling, and large
#: enough that an ordinary document is one page.
DEFAULT_PAGE_SIZE = 100

#: The id form authors are reported in. ``open_id`` yields the ``ou_``-prefixed form;
#: ``union_id`` yields the ``on_``-prefixed one. Either way the id is surfaced raw.
DEFAULT_USER_ID_TYPE = "open_id"

#: How many pages a single walk will follow before giving up. A safety stop for a server
#: that hands back an endless chain of fresh cursors; the ordinary guards (no cursor, or a
#: repeated cursor) end a walk long before this.
MAX_PAGES = 200


def _require_success(resp, context: str):
    """Return ``resp`` on success; raise this library's typed error otherwise."""
    if not resp.success():
        raise api_error(
            f"Failed to {context}: Code: {resp.code}, Msg: {resp.msg}",
            code=resp.code, msg=resp.msg, body=resp,
            credential_env=resolved_read_env())
    return resp


class CommentsReadClient:
    """Reads comments on a file: the whole list, a batch by id, and one thread's replies.

    ``sdk_client`` and ``rate_limiter`` are injectable so request construction, pacing and
    error typing are all testable without a network; the defaults are a real SDK client
    built from the supplied credentials and a limiter at
    :data:`DEFAULT_MAX_READS_PER_WINDOW` per :data:`COMMENTS_RATE_WINDOW_SECONDS`.
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        domain: str = "larksuite.com",
        *,
        sdk_client=None,
        rate_limiter: Optional[RateLimiter] = None,
        user_id_type: str = DEFAULT_USER_ID_TYPE,
        page_size: int = DEFAULT_PAGE_SIZE,
        timeout: int = 30,
    ):
        self._domain = domain
        self._user_id_type = user_id_type
        self._page_size = page_size
        self._api_calls = 0
        self._reply_attributions: Dict[str, BaseAttribution] = {}
        self._limiter = resolve_rate_limiter(
            rate_limiter, DEFAULT_MAX_READS_PER_WINDOW, COMMENTS_RATE_WINDOW_SECONDS)
        self._sdk = resolve_sdk_client(
            sdk_client, app_id, app_secret, domain, timeout=timeout,
            no_credentials="Cannot read comments: no credentials were resolved")

    @classmethod
    def from_read_credentials(cls, domain: str = "larksuite.com", **kwargs):
        """Build from the environment's READ credentials. Comments are a read; the write
        credential pair is never consulted here."""
        app_id, app_secret = get_read_credentials()
        require_credentials(
            app_id, app_secret,
            "Cannot read comments: no read credentials in the environment")
        return cls(app_id, app_secret, domain, **kwargs)

    # ---- pacing ----------------------------------------------------------- #

    @property
    def limiter(self) -> RateLimiter:
        """The limiter every call on this client passes through."""
        return self._limiter

    @property
    def api_calls(self) -> int:
        """How many API calls this client has made. Incremented in exactly one place, so it
        is a count of real requests rather than of intentions."""
        return self._api_calls

    def _paced(self, call, *args):
        """Acquire a slot, then make exactly one API call. Every call in this module goes
        through here, so no endpoint can be added that bypasses the pace — nor one that
        skips the attribution harvest below, which is the other thing every response owes."""
        self._limiter.acquire()
        self._api_calls += 1
        resp = call(*args)
        self._harvest_attribution(resp)
        return resp

    # ---- the attribution harvest ------------------------------------------ #

    @property
    def reply_attributions(self) -> Dict[str, BaseAttribution]:
        """``{reply_id: attribution}`` for every attributed reply this client has seen.

        A **Base** comment says which record it was written against, in
        ``extra.notify_extra`` — and the pinned SDK's ``ReplyExtra`` models only
        ``image_list``, so its deserializer discards the object before any typed model can
        see it. Rather than open a second HTTP path for one key, this client reads it off the
        **same response's own bytes**, which the SDK hands back as ``response.raw.content``.
        One call, one response, two readers.

        It accumulates across calls on purpose: a truncated thread is completed through the
        reply-list endpoint, and those replies carry their attribution in the same place, so
        the completed thread must be able to find it.
        """
        return dict(self._reply_attributions)

    def _harvest_attribution(self, resp) -> None:
        """Read the one object the SDK's typed model does not declare.

        Never raises. A response whose bytes are absent or unreadable simply contributes no
        attribution, so a side channel cannot fail the read it rides on.
        """
        raw = getattr(resp, "raw", None)
        self._reply_attributions.update(
            attributions_from_raw(getattr(raw, "content", None)))

    # ---- the paged walk --------------------------------------------------- #

    def _walk_pages(self, fetch_page) -> List:
        """Follow a cursor-paged endpoint to exhaustion, and STOP under every shape of
        server answer that would otherwise not terminate.

        ``fetch_page(page_token)`` returns the response body for one page. The walk ends
        when the body says there is no more, when it claims more but hands back no usable
        cursor, when it hands back a cursor already used (which would replay the same page
        forever), or at :data:`MAX_PAGES`.
        """
        items: List = []
        token: Optional[str] = None
        seen = set()
        for _ in range(MAX_PAGES):
            body = fetch_page(token)
            items.extend(getattr(body, "items", None) or ())
            if not getattr(body, "has_more", None):
                return items
            token = getattr(body, "page_token", None)
            if not token or token in seen:
                # "There is more" with nothing to ask for next, or with the cursor we just
                # used: believe the cursor, not the flag, and stop.
                return items
            seen.add(token)
        return items

    # ---- the operations --------------------------------------------------- #

    def list_comments(self, file_token: str, *, file_type: str = "docx") -> List[FileComment]:
        """Every comment on the file, following the cursor to exhaustion."""
        def page(token):
            builder = ListFileCommentRequest.builder() \
                .file_token(file_token) \
                .file_type(file_type) \
                .user_id_type(self._user_id_type) \
                .page_size(self._page_size)
            if token:
                builder = builder.page_token(token)
            resp = self._paced(self._sdk.drive.v1.file_comment.list, builder.build())
            return _require_success(resp, f"list comments on {file_token}").data

        return self._walk_pages(page)

    def batch_query_comments(self, file_token: str, comment_ids,
                             *, file_type: str = "docx") -> List[FileComment]:
        """The comments for the given ids. **No ids means no call** — an empty request is a
        request not worth making, and a caller with nothing to ask about should pay nothing.
        """
        ids = list(comment_ids)
        if not ids:
            return []
        body = BatchQueryFileCommentRequestBody.builder().comment_ids(ids).build()
        request = BatchQueryFileCommentRequest.builder() \
            .file_token(file_token) \
            .file_type(file_type) \
            .user_id_type(self._user_id_type) \
            .request_body(body) \
            .build()
        resp = self._paced(self._sdk.drive.v1.file_comment.batch_query, request)
        _require_success(resp, f"fetch comments on {file_token}")
        return list(getattr(resp.data, "items", None) or ())

    def list_replies(self, file_token: str, comment_id: str, *,
                     file_type: str = "docx",
                     page_token: Optional[str] = None) -> List[FileCommentReply]:
        """One comment's replies from ``page_token`` onward, following the cursor.

        Used when a comment's embedded thread came back truncated — the batch-fetch response
        says so per comment, and this completes it rather than silently reporting a partial
        conversation.
        """
        def page(token):
            builder = ListFileCommentReplyRequest.builder() \
                .file_token(file_token) \
                .comment_id(comment_id) \
                .file_type(file_type) \
                .user_id_type(self._user_id_type) \
                .page_size(self._page_size)
            cursor = token if token else page_token
            if cursor:
                builder = builder.page_token(cursor)
            resp = self._paced(
                self._sdk.drive.v1.file_comment_reply.list, builder.build())
            return _require_success(
                resp, f"list replies on comment {comment_id}").data

        return self._walk_pages(page)
