"""The throttled directory-search client — the pinned SDK's typed models, paced by our limiter.

**Why the SDK and not raw HTTP.** Same reasoning as ``comments/client.py``: the pinned
``lark-oapi`` ships the whole ``directory/v1`` employee family — request builders and response
models alike — including the ``abnormals`` shape that makes a partial answer legible. Hand-
rolling a second HTTP path here would throw away the deserializer whose *omit-what-was-omitted*
behaviour is exactly what keeps *"the field was not reported"* distinguishable from *"the field
is empty"*, which is the distinction this whole surface exists to preserve.

**What the SDK does not bring, and this client does.**

* **Pacing** — every call passes through the shared limiter first (see the constants below).
* **The id form** — ``employee_id_type=open_id`` is sent on every request, because the
  ``open_id`` is the only id form the downstream consumer (``sheets.rich_encode.encode_mention``)
  can use.
* **An explicit resigned-employee stance** (:data:`CONTAIN_RESIGNED_EMPLOYEE`) rather than the
  server's default.
* **Typed failures** — a non-zero code goes through :func:`larkdocio.errors.api_error`, so a
  scope denial arrives as ``LarkPermissionError`` carrying a ``PermissionDenial`` rather than
  wearing the costume of an absence.

This client makes **exactly two** calls, both READS, both POINT queries, both paced through the
one limiter: the employee search (a name), and the contacts-family id lookup (an email or a
mobile). It does not list, filter or walk the directory: enumeration was disqualified
as a name-search strategy before this surface was written, and nothing here re-opens it.

**The second call is a deliberately-minted purchase of a second endpoint family.** A shipped
guard in this project's own test suite (in the source repository) forbids any call site reaching
``batch_get_id`` — it was written so a *documentation* story could not quietly buy an endpoint
family, and it still forbids every call site but the one below, under a maintainer ruling. The ``/im/``
half of that guard is untouched and absolute: no chat lister ships.
"""
import json
from typing import List, Optional, Sequence

from lark_oapi.api.contact.v3 import (
    BatchGetIdUserRequest,
    BatchGetIdUserRequestBody,
)
from lark_oapi.api.directory.v1 import (
    PageCondition,
    SearchEmployeeFilter,
    SearchEmployeeRequest,
    SearchEmployeeRequestBody,
)

from larkdocio.common.auth import get_read_credentials, resolved_read_env
from larkdocio.common.transport import RateLimiter
from larkdocio.common.sdk_client import (
    require_credentials,
    resolve_rate_limiter,
    resolve_sdk_client,
)
from larkdocio.errors import api_error

#: The window a documented per-minute tier would be expressed over: one minute. Same literal,
#: same meaning, as ``comments/client.py``'s ``COMMENTS_RATE_WINDOW_SECONDS``.
CONTACTS_RATE_WINDOW_SECONDS = 60.0

#: Client-side cap per :data:`CONTACTS_RATE_WINDOW_SECONDS`. One literal, so re-pacing the
#: surface is a one-line edit.
#:
#: **The tier this is capped below could not be read, and that is recorded rather than
#: papered over.** ``comments/client.py`` cites *"the documented 100-per-minute tier"* because
#: that tier was readable. For ``directory/v1/employees/search`` it is not, and three
#: independent attempts say so: the response headers carry **no** rate-limit fields at all (no
#: ``x-ogw-ratelimit-*``, no ``x-ratelimit-*``, no ``retry-after`` — see ``response_headers``
#: in every committed capture); the pinned SDK ships no tier metadata; and Lark's own
#: documentation page serves a JavaScript shell rather than text. So this number is **not**
#: a fraction of a documented tier and is not presented as one. It is anchored to the only
#: rate this project has evidence for: the spike's **~1.2 s spacing**, sustained over 12
#: read-only requests with zero ``99991400``. Sixty seconds over fifty requests is exactly
#: that spacing. **Nothing here measures a limit by walking into one**, and if the tier ever
#: becomes readable this constant is where it gets cited.
DEFAULT_MAX_SEARCHES_PER_WINDOW = 50

#: The minimum spacing the two literals above imply — DERIVED, so the pace cannot disagree
#: with the cap. The default limiter admits one call per this interval rather than a burst of
#: fifty followed by a stall, which is what keeps a real caller at the spacing the evidence
#: covers instead of merely under the same hourly total.
CONTACTS_MIN_REQUEST_SPACING_SECONDS = (
    CONTACTS_RATE_WINDOW_SECONDS / DEFAULT_MAX_SEARCHES_PER_WINDOW)

#: **Resigned employees are EXCLUDED, deliberately.** The pinned SDK exposes
#: ``SearchEmployeeFilter.contain_resigned_employee`` and this surface sets it on every request
#: rather than inheriting whatever the server defaults to. The reason is that the two failure
#: directions are not symmetric: resolving a name to a **departed** user and handing that
#: id to an @mention is a correctness bug with a compliance flavour — the mention renders, the
#: person is gone, and nothing in the answer says so. Failing to find someone who has left is
#: merely a miss, and it refuses loudly. A caller who genuinely wants a former employee is
#: better served passing the ``open_id`` directly, which this surface never stands between.
CONTAIN_RESIGNED_EMPLOYEE = False

#: The id-lookup route's own resigned stance — the same asymmetry, stated for the second
#: endpoint rather than inherited by silence. ``batch_get_id`` takes ``include_resigned``; the
#: 2026-08-08 probe sent no such flag, so the server's default here is **unobserved** and this
#: constant is the LIBRARY's stance rather than a claim about that default. It is set in the
#: conservative direction for the reason :data:`CONTAIN_RESIGNED_EMPLOYEE` gives: handing a
#: departed user's id to an @mention is a correctness bug with a compliance flavour, and
#: failing to find someone who has left merely refuses loudly.
INCLUDE_RESIGNED_USER = False

#: The id form every request asks for. ``open_id`` is the ``ou_``-prefixed form, and the only
#: one the downstream mention encoder accepts. The contacts family calls the same parameter
#: ``user_id_type`` and takes the same value, so one constant serves both calls.
EMPLOYEE_ID_TYPE = "open_id"

#: The one field group the search asks for. Requesting more would pull user contact data
#: this surface has no use for; ``base_info`` is where the id and the display name live.
REQUIRED_FIELDS = ("base_info",)

#: Page size for one search. Large enough that an ordinary name query is a single page, and
#: small enough that an over-broad query cannot pull the directory down by accident.
DEFAULT_PAGE_SIZE = 20


class ContactsSearchClient:
    """Searches the employee directory by free-text query. One call, one page, paced.

    ``sdk_client`` and ``rate_limiter`` are injectable so request construction, pacing and
    error typing are all testable without a network; the defaults are a real SDK client built
    from the supplied credentials and a limiter admitting one call per
    :data:`CONTACTS_MIN_REQUEST_SPACING_SECONDS`.
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        domain: str = "larksuite.com",
        *,
        sdk_client=None,
        rate_limiter: Optional[RateLimiter] = None,
        employee_id_type: str = EMPLOYEE_ID_TYPE,
        page_size: int = DEFAULT_PAGE_SIZE,
        timeout: int = 30,
    ):
        self._domain = domain
        self._employee_id_type = employee_id_type
        self._page_size = page_size
        self._api_calls = 0
        self._last_request = None
        self._limiter = resolve_rate_limiter(
            rate_limiter, 1, CONTACTS_MIN_REQUEST_SPACING_SECONDS)
        self._sdk = resolve_sdk_client(
            sdk_client, app_id, app_secret, domain, timeout=timeout,
            no_credentials="Cannot search the directory: no credentials were resolved")

    @classmethod
    def from_read_credentials(cls, domain: str = "larksuite.com", **kwargs):
        """Build from the environment's READ credentials. A directory search is a read; the
        write credential pair is never consulted here."""
        app_id, app_secret = get_read_credentials()
        require_credentials(
            app_id, app_secret,
            "Cannot search the directory: no read credentials in the environment")
        return cls(app_id, app_secret, domain, **kwargs)

    # ---- pacing + provenance ---------------------------------------------- #

    @property
    def limiter(self) -> RateLimiter:
        """The limiter every call on this client passes through."""
        return self._limiter

    @property
    def api_calls(self) -> int:
        """How many API calls this client has made. Incremented in exactly one place, so it
        is a count of real requests rather than of intentions."""
        return self._api_calls

    @property
    def last_request(self):
        """The last request object handed to the SDK, so a caller (or a test) can see the
        exact shape that went out rather than infer it."""
        return self._last_request

    # ---- the one operation ------------------------------------------------ #

    def search_employees(self, query: str, *, page_size: Optional[int] = None,
                         page_token: Optional[str] = None,
                         required_fields: Optional[List[str]] = None):
        """One page of directory hits for a free-text ``query``, as the SDK's response body.

        Returns the deserialized ``SearchEmployeeResponseBody`` — ``employees``,
        ``page_response`` and (when the server sends it) ``abnormals``. The body is returned
        **whole and uninterpreted**: deciding what an answer means is
        :func:`larkdocio.contacts.lookup.resolve_user`'s job, and a client that pre-digested it
        would be the place a partial answer got smoothed into a clean one.
        """
        page = PageCondition.builder().page_size(page_size or self._page_size)
        if page_token:
            page = page.page_token(page_token)
        body = SearchEmployeeRequestBody.builder() \
            .query(query) \
            .page_request(page.build()) \
            .required_fields(list(required_fields or REQUIRED_FIELDS)) \
            .filter(SearchEmployeeFilter.builder()
                    .contain_resigned_employee(CONTAIN_RESIGNED_EMPLOYEE).build()) \
            .build()
        request = SearchEmployeeRequest.builder() \
            .employee_id_type(self._employee_id_type) \
            .request_body(body) \
            .build()
        self._last_request = request
        resp = self._paced(self._sdk.directory.v1.employee.search, request)
        if not resp.success():
            raise api_error(
                f"Failed to search the employee directory: Code: {resp.code}, Msg: {resp.msg}",
                code=resp.code, msg=resp.msg, body=_denial_body(resp),
                credential_env=resolved_read_env())
        return resp.data

    def batch_get_id(self, *, emails: Optional[Sequence[str]] = None,
                     mobiles: Optional[Sequence[str]] = None):
        """Email or mobile → ``open_id``, as the SDK's response body.

        Returns the deserialized ``BatchGetIdUserResponseBody`` — a ``user_list`` where each
        entry echoes the identifier it was asked about and carries ``user_id`` **only when the
        endpoint resolved it**. The body is returned **whole and uninterpreted**, for the same
        reason :meth:`search_employees` returns its own: deciding what an unresolved entry
        MEANS is :func:`larkdocio.contacts.lookup.resolve_colleague`'s job, and the meaning is
        the hard part here — an address that exists nowhere and a real user this app
        cannot see come back identical.

        Rides the **same limiter** as the search: it is the same contacts family and the same
        unreadable rate tier (:data:`DEFAULT_MAX_SEARCHES_PER_WINDOW`'s docstring is the
        standing statement, and no second tier number is invented here).
        """
        body = BatchGetIdUserRequestBody.builder()
        if emails:
            body = body.emails(list(emails))
        if mobiles:
            body = body.mobiles(list(mobiles))
        request = BatchGetIdUserRequest.builder() \
            .user_id_type(self._employee_id_type) \
            .request_body(body.include_resigned(INCLUDE_RESIGNED_USER).build()) \
            .build()
        self._last_request = request
        resp = self._paced(self._sdk.contact.v3.user.batch_get_id, request)
        if not resp.success():
            raise api_error(
                f"Failed to look up a contact id: Code: {resp.code}, Msg: {resp.msg}",
                code=resp.code, msg=resp.msg, body=_denial_body(resp),
                credential_env=resolved_read_env())
        return resp.data

    def _paced(self, call, *args):
        """Acquire a slot, then make exactly one API call. Every call in this module goes
        through here, so no endpoint can be added that bypasses the pace."""
        self._limiter.acquire()
        self._api_calls += 1
        return call(*args)


def _denial_body(resp):
    """The parsed body a ``PermissionDenial`` reads its scope list and console link out of.

    The SDK's typed response models drop the ``error`` envelope, which is where Lark puts
    ``permission_violations[].subject`` and ``helps[].url`` — so the denial's console link would
    be lost on this transport for no reason other than deserialization. The raw bytes are still
    on the response, so they are parsed back here when they parse; otherwise the response object
    itself is handed on and the classification falls back to the message text, exactly as every
    other SDK call site in this library does. **Nothing is reconstructed**: a console link we
    did not receive is never claimed.
    """
    raw = getattr(getattr(resp, "raw", None), "content", None)
    if raw:
        try:
            return json.loads(raw)
        except (ValueError, TypeError):  # pragma: no cover - a non-JSON error envelope
            pass
    return resp
