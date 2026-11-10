"""larkdocio.common.transport — shared raw-HTTP transport core (LD-061, LD-126).

Two layers of shared read/write infrastructure, both **born raising the S1 typed
errors** (``LarkAPIError`` / ``LarkRateLimitError`` / ``LarkConfigError``), never a
bare ``Exception``:

1. **Rate + token primitives** (LD-061) — :class:`RateLimiter` (a
   rolling-window pacer), :class:`WriteTransport` (the ≤3-writes/sec executor with
   ``99991400`` backoff), :func:`fetch_tenant_access_token`, and
   :func:`raise_for_lark_code`.
2. **The raw-HTTP client skeleton** (LD-126 / T2) — :class:`RawHttpClient` and
   :class:`CredentialedRawHttpClient`: the shared ``urllib`` request/response
   skeleton the raw-HTTP clients ride as thin declarations, with their deliberate
   per-client differences kept as overridable hooks (see :class:`RawHttpClient`).
   **The riders are enumerated once, below**, in the census derived from the imports
   — no count is restated at the class, because "four" outlived the four surfaces
   that existed when LD-126 wrote it while this file's own census said nine (LD-649).

Scope note — throttle governance (LD-126, correcting the pre-extraction framing).
It is **no longer** true that "reads are not throttle-governed": the sheets **read**
client (``sheets/client.py``) and the xlsx **export** reader
(``sheets/export_reader.py``) route their calls through a :class:`RateLimiter` on
this very module (a gentle read cap ≪ Lark's 100/sec), alongside the docx and sheets
**write** clients routing through :class:`WriteTransport` (≤3/sec + ``99991400``
backoff).

**Which clients ride this transport, read off the code (LD-512, superseding the
"SDK for reads is now docx-only" clause LD-126 wrote here; census re-derived and the
SDK column amended by LD-534).** That clause was true of the surfaces that existed
when it was written and has been stale since the Base, comments and contacts surfaces
shipped; the *reason* below is unchanged, only the census is — and that has held
through LD-534, which moved **no** module between the two lists and changed only *how*
the second one reaches this module. Two lists, both derived from the imports rather
than from a summary:

* **On this module's raw-HTTP skeleton** (:class:`RawHttpClient` /
  :class:`CredentialedRawHttpClient`): ``write/client.py``, ``sheets/client.py``,
  ``sheets/write_client.py``, ``sheets/export_reader.py``, ``drive/client.py``,
  ``drive/folders_write.py``, ``drive/access_write.py``, ``drive/versions_write.py``
  and ``preflight.py``'s probe client.
* **Still on the ``lark-oapi`` SDK**, taking only the pacing primitives from here:
  the **docx reader** (``read/client.py``), the whole **Base** surface
  (``base/client.py``, ``base/schema_client.py``, ``base/view_client.py``,
  ``base/write_client.py``, ``base/media.py``), the **comments** client
  (``comments/client.py``), the **contacts** client (``contacts/client.py``) and the
  **drive file-object writes** (``drive/files_write.py``). Since LD-534 every one of
  them **that constructs an SDK client at all** — **eight** of the nine; the ninth,
  ``base/view_client.py``, is the view family's **mixin**: it has no ``__init__`` and
  constructs nothing, and its three calls ride the client
  :class:`~larkdocio.base.schema_client.BaseSchemaClient` built (LD-539 narrows the
  quantifier and nothing else) — **constructs** it through one shared core,
  :mod:`larkdocio.common.sdk_client` — that is where the five chained
  ``lark.Client.builder()`` calls now live, and it is what takes :class:`RateLimiter`
  from here on their behalf. So the pacing primitive still comes from this module for
  every paced client on the list; for five of them it now arrives one hop away instead
  of by a direct import. ``comments/client.py`` and ``contacts/client.py`` still name
  :class:`RateLimiter` directly, for their type annotations. The docx reader takes the
  builder chain and nothing else: it has never had a limiter, and LD-534 deliberately
  did not give it one.

So the SDK is neither reads-only nor docx-only: it carries **both reads and writes**,
and which surfaces is read off the second list above rather than counted here (LD-649:
a bare count in this file had already gone stale once). What *is* still true is the reason the docx reader in particular stays on
it — rewriting that hardened SDK client onto ``urllib`` would risk reader-output
drift and break its stubbed-SDK safety net for no benefit, while the writer and the
SDK-absent v2 sheets endpoints genuinely need raw ``urllib`` (the feasibility spikes,
in the dev repo: ``dev/write-spike/07-report.md`` / ``tests/captures/sheets-spike/``). So the
shared non-transport primitives (auth / URL / IPv4) live in ``common`` too, while the
docx read SDK client stays in ``read/`` — its class, its public ``lark_client``
attribute and every request it builds; LD-534 shared the builder chain that
instantiates it and nothing else.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from larkdocio.common.errors import (
    LarkAPIError,
    LarkConfigError,
    LarkRateLimitError,
    RATE_LIMIT_CODE,  # noqa: F401  (re-exported for callers)
    _is_rate_limit_code,
    api_error,
)

# Spike Q3 (dev/write-spike/07-report.md): per-app 3 writes/sec, per-document
# 3 edits/sec; overflow → HTTP 400 + code 99991400. The throttle ceiling is 3.
DEFAULT_MAX_WRITES_PER_SEC = 3
DEFAULT_MAX_RETRIES = 5
DEFAULT_BASE_BACKOFF = 0.5  # seconds; exponential: base * 2**attempt

TENANT_TOKEN_PATH = "/open-apis/auth/v3/tenant_access_token/internal"


def api_base(domain: str = "larksuite.com") -> str:
    """The **domain root** for a Lark tenant — ``https://open.larksuite.com``, no path.

    It is deliberately NOT an endpoint prefix: the ``/open-apis`` segment belongs to the
    path, so a caller composes the full URL itself —
    ``api_base("feishu.cn") + "/open-apis/docx/v1/documents/…"``. Every client in this
    package does exactly that, which is why the root is what this returns; a raw call that
    404s is usually one that dropped ``/open-apis``.
    """
    return f"https://open.{domain}"


def _resp_code(resp):
    """Lark response ``code`` from a dict payload or an SDK-style object."""
    if isinstance(resp, dict):
        return resp.get("code")
    return getattr(resp, "code", None)


def _resp_msg(resp):
    if isinstance(resp, dict):
        return resp.get("msg")
    return getattr(resp, "msg", None)


class RateLimiter:
    """Rolling-window limiter: at most ``max_per_sec`` acquisitions per ``window``.

    ``acquire()`` blocks (via the injected ``sleep_fn``) until admitting the call
    would keep ``≤ max_per_sec`` acquisitions inside the trailing ``window``
    seconds. The monotonic clock and sleep are injectable so the pacing is
    deterministically unit-testable offline. Single-threaded by design (the
    writer applies edits serially — spike discipline).
    """

    def __init__(
        self,
        max_per_sec: int = DEFAULT_MAX_WRITES_PER_SEC,
        *,
        window: float = 1.0,
        time_fn=time.monotonic,
        sleep_fn=time.sleep,
    ):
        if max_per_sec < 1:
            raise LarkConfigError("RateLimiter max_per_sec must be >= 1")
        self.max_per_sec = max_per_sec
        self.window = window
        self._time = time_fn
        self._sleep = sleep_fn
        self._events: list[float] = []  # monotonic stamps of recent acquisitions

    def _prune(self, now: float):
        cutoff = now - self.window
        self._events = [t for t in self._events if t > cutoff]

    def acquire(self):
        now = self._time()
        self._prune(now)
        if len(self._events) >= self.max_per_sec:
            # Sleep until the oldest in-window event ages out.
            wait = self._events[0] + self.window - now
            if wait > 0:
                self._sleep(wait)
                now = self._time()
                self._prune(now)
        self._events.append(now)


class WriteTransport:
    """Throttled write executor with ``99991400`` backoff, raising the typed errors.

    ``execute(call)`` runs ``call`` — a zero-arg callable performing ONE write
    attempt and returning a Lark response (a dict ``{"code","msg","data",...}``,
    or an SDK-style object exposing ``.code``/``.msg``). It:

    1. throttles via the :class:`RateLimiter` (``≤ max_writes_per_sec``);
    2. on a rate-limit (``99991400``) — whether ``call`` *returns* the code or
       *raises* :class:`LarkRateLimitError` — backs off exponentially and retries
       up to ``max_retries``, then re-raises the typed :class:`LarkRateLimitError`;
    3. returns the response unchanged on any non-rate-limit outcome (mapping other
       error codes to typed errors is the caller's job — see
       :func:`raise_for_lark_code`).

    The transport is transport-agnostic: ``call`` may wrap ``urllib``, the SDK, or
    a stub, which keeps it offline-unit-testable.
    """

    def __init__(
        self,
        *,
        max_writes_per_sec: int = DEFAULT_MAX_WRITES_PER_SEC,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_backoff: float = DEFAULT_BASE_BACKOFF,
        time_fn=time.monotonic,
        sleep_fn=time.sleep,
    ):
        self._limiter = RateLimiter(
            max_writes_per_sec, time_fn=time_fn, sleep_fn=sleep_fn
        )
        self._sleep = sleep_fn
        self.max_retries = max_retries
        self.base_backoff = base_backoff

    def _backoff(self, attempt: int):
        self._sleep(self.base_backoff * (2 ** attempt))

    def execute(self, call):
        attempt = 0
        while True:
            self._limiter.acquire()
            try:
                resp = call()
            except LarkRateLimitError:
                if attempt >= self.max_retries:
                    raise
                self._backoff(attempt)
                attempt += 1
                continue

            if _is_rate_limit_code(_resp_code(resp)):
                if attempt >= self.max_retries:
                    raise LarkRateLimitError(
                        f"Lark rate limit ({RATE_LIMIT_CODE}) did not clear after "
                        f"{self.max_retries} retries",
                        code=_resp_code(resp),
                        msg=_resp_msg(resp),
                    )
                self._backoff(attempt)
                attempt += 1
                continue

            return resp


def raise_for_lark_code(resp, *, context: str = "Lark API call", credential_env=()):
    """Raise the typed error for a non-zero Lark response ``code``.

    A convenience for write-path callers: ``code`` ``0``/absent is success (the
    response is returned); any other code raises :class:`LarkRateLimitError`
    (for ``99991400``), :class:`LarkPermissionError` (a scope denial) or
    :class:`LarkAPIError`, carrying Lark's ``code``/``msg``.

    ``credential_env`` names the pair this call was made on. Every client passes its own,
    because a scope denial has to say WHICH app to fix and only the client knows.
    """
    code = _resp_code(resp)
    if code in (0, None) or str(code) == "0":
        return resp
    # `body=resp` is what lets a scope denial keep the console deep link Lark handed back:
    # the scope string survives in the message either way, but the link lives only in the body.
    raise api_error(
        f"{context} failed: Code: {code}, Msg: {_resp_msg(resp)}",
        code=code,
        msg=_resp_msg(resp),
        body=resp,
        credential_env=credential_env,
    )


def fetch_tenant_access_token(
    app_id: str,
    app_secret: str,
    domain: str = "larksuite.com",
    *,
    urlopen=urllib.request.urlopen,
    timeout: int = 30,
) -> str:
    """Fetch a ``tenant_access_token`` for the given app.

    Tenant-token management for the write path, living in the shared transport
    core and **typed**. The ``urlopen`` is injectable so the
    happy/error paths are unit-testable offline. Raises the typed errors:

    * :class:`LarkConfigError` — missing ``app_id``/``app_secret``;
    * :class:`LarkRateLimitError` — Lark returned ``99991400``;
    * :class:`LarkAPIError` — any other non-zero code, a transport error, or a
      success response missing the token field.

    **Every API error raised here is STAMPED as coming from the token handshake**
    (:func:`from_the_token_mint`), because the class alone cannot say so: this
    library raises :class:`LarkAPIError` for a 404 on a document just as readily,
    and a seam that answered *"your app credentials were rejected"* to both would
    be worse than the traceback it replaced. What makes the failure a *credential*
    rejection is then **Lark's own code** — see :func:`is_credential_rejection`.
    """
    if not app_id or not app_secret:
        raise LarkConfigError(
            "Cannot fetch tenant_access_token: missing app_id/app_secret"
        )

    body = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request(
        api_base(domain) + TENANT_TOKEN_PATH,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        raw = urlopen(req, timeout=timeout).read()
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode())
        except Exception:
            payload = {}
        raise from_the_token_mint(api_error(
            f"tenant_access_token request failed (HTTP {e.code})",
            code=payload.get("code"),
            msg=payload.get("msg"),
        ))
    except urllib.error.URLError as e:
        raise from_the_token_mint(
            LarkAPIError(f"tenant_access_token request failed: {e}"))

    data = json.loads(raw)
    code = data.get("code")
    if code not in (0, None) and str(code) != "0":
        raise from_the_token_mint(api_error(
            f"tenant_access_token error: {data.get('msg')}",
            code=code,
            msg=data.get("msg"),
        ))

    token = data.get("tenant_access_token")
    if not token:
        raise from_the_token_mint(LarkAPIError(
            "tenant_access_token missing from response",
            code=code,
            msg=data.get("msg"),
        ))
    return token


# --------------------------------------------------------------------------- #
# The token mint's OWN failures, told apart from every other Lark failure       #
# (LD-672)                                                                      #
# --------------------------------------------------------------------------- #
#
# **Why any of this exists.** This library mints a tenant token two ways — the
# ``lark_oapi`` SDK's ``TokenManager`` (the docx reader, Base, comments, contacts)
# and :func:`fetch_tenant_access_token` above (every raw-HTTP surface: Drive, the
# write engine, Sheets, preflight). A rejected App ID/Secret therefore arrived as
# TWO different exception classes, and LD-658's credential guidance caught only the
# SDK's. Executed on the other path, ``larkdocio folder <url>`` printed **zero
# bytes** and escaped an uncaught ``LarkAPIError`` — no ``Error:`` line, no
# guidance, no indication which of the two ``.env`` pairs was at fault.
#
# **Two facts are needed, and neither alone is enough.**
#
# 1. *Did this come out of the token handshake?* The **class cannot answer**:
#    ``LarkAPIError`` is also what a missing document, a bad token and a rejected
#    parameter arrive as. So the mint STAMPS its own errors, at the single function
#    that owns the handshake, and a guard in the source repository
#    (``tests/test_token_mint_credential_refusal.py``) walks that function's own
#    ``raise`` statements so a branch added later cannot quietly go unstamped.
# 2. *Did LARK reject the app, or did the call never arrive?* **Lark's code
#    answers**, which is why the stamp is not by itself the verdict: the mint also
#    raises on a dead socket (``URLError``, no code at all) and on Lark's
#    rate-limit code. Telling an operator with no network that their App Secret is
#    wrong is the same defect class in a new costume, so a token-mint failure
#    carrying no code — or carrying ``99991400`` — keeps exactly the behaviour it
#    has today.
#
# **Why a hand-listed set of rejection codes was rejected as the discriminator.**
# Lark answers a rejected pair with more than one number (``10003`` and the
# ``invalid param`` shape are both observed on this endpoint), the list is not
# derivable from any code in this repo, and a hand-typed list is the exact
# instrument this issue exists to stop trusting — the coverage sentence it guards
# was hand-typed three times and wrong three times. *"Lark answered with a
# non-zero, non-throttle code"* needs no list and cannot go stale.

#: The attribute a token-mint failure carries. Its **presence** is the stamp (fact 1
#: above); its value is the env-var pair the rejected handshake was made on, or
#: ``()`` where the code that raised could not say. Read it through
#: :func:`token_mint_credential_env`, never off the attribute name.
TOKEN_MINT_ATTRIBUTION = "larkdocio_token_mint_credential_env"


def from_the_token_mint(error, credential_env=()):
    """Stamp *error* as raised by the tenant-token handshake, and return it.

    Called at the mint's own ``raise`` sites, so the stamp cannot be forgotten by a
    caller and cannot be applied by anything that is not the handshake.
    """
    setattr(error, TOKEN_MINT_ATTRIBUTION, tuple(credential_env))
    return error


def attribute_token_mint_failure(error, credential_env):
    """Give a token-mint failure the credential pair its **caller** knows, and return it.

    The mint takes an ``(app_id, app_secret)`` and has no idea which environment
    variables they came from; the client does — a Drive read runs on the pair
    :func:`~larkdocio.common.auth.resolved_read_env` reports, a write engine on
    ``LARK_WRITE_APP_*``, and telling a ``roundtrip push`` failure to go and check
    the READ pair is the *"names the wrong file"* defect wearing new clothes. So
    attribution is stamped one layer up, at :meth:`RawHttpClient._bearer`, which is
    the single place every raw-HTTP surface's token is fetched.

    A pair already on the error is never overwritten (the innermost knower wins),
    and an error that did not come from the mint is left completely alone.
    """
    if getattr(error, TOKEN_MINT_ATTRIBUTION, None) == ():
        setattr(error, TOKEN_MINT_ATTRIBUTION, tuple(credential_env))
    return error


def token_mint_credential_env(error) -> tuple:
    """The env-var pair a token-mint failure was made on — ``()`` when unattributed.

    ``()`` is the honest answer for a mint called outside a client (the library's
    public :func:`fetch_tenant_access_token` is importable), and its consumers say
    *both pairs, and Lark does not report which* rather than guessing — the pattern
    LD-658 established rather than a new invention.
    """
    return tuple(getattr(error, TOKEN_MINT_ATTRIBUTION, ()) or ())


def is_credential_rejection(error) -> bool:
    """True when *error* is **Lark refusing the app itself** at the token handshake.

    The one predicate the CLI seam and any consumer asks; the two facts it ANDs and
    the reason neither suffices alone are written above this function, not here.
    """
    return (
        isinstance(error, LarkAPIError)
        and hasattr(error, TOKEN_MINT_ATTRIBUTION)
        and error.code is not None
        and str(error.code) != "0"
        and not error.is_rate_limit
    )


# --------------------------------------------------------------------------- #
# Shared raw-HTTP client skeleton (LD-126 / T2)                                 #
# --------------------------------------------------------------------------- #

class RawHttpClient:
    """The shared raw-``urllib`` skeleton the package's raw-HTTP clients ride.

    **Which clients those are is stated in ONE place** — this module's docstring,
    § "Which clients ride this transport, read off the code", whose list is derived
    from the imports. It is not restated here and no count is given here: the
    original wording named *four* by hand and stayed that way while the Drive write
    legs and preflight's probe client joined, so this class ended up contradicting the
    census in its own module. ``grep -rn 'RawHttpClient)' src/larkdocio`` is the
    derivation, and it is cheaper to run than a hand-kept number is to trust.

    It owns the parts each of those clients would otherwise duplicate — the lazy
    tenant-token cache, request construction (URL + query params + JSON body + the
    bearer/Content-Type headers), and the ``urlopen`` send with the ``URLError`` →
    :class:`LarkAPIError` typing — while the deliberate per-client differences stay
    expressed as small overridable hooks, **not** flattened. There are **four hooks,
    B1–B4** — that count is of the hooks listed immediately below, readable in place,
    not of the client population:

    * **B1 — the non-2xx (``HTTPError``) posture** → :meth:`_on_http_error`. The
      default (**every rider except the export reader** — the JSON clients; the
      exception is named rather than the majority counted): parse the Lark error body
      and **return it as a dict**, never raising here — a non-JSON body degrades to
      ``{"code": <http>, "msg": "HTTP <http>"}`` — so the caller's throttle /
      :func:`raise_for_lark_code` can see a ``99991400`` and type the rest. The
      export reader overrides this to **raise**.
    * **B2 — GET-only vs body-bearing** → the per-call ``method``/``body`` of
      :meth:`_send` (a read-only rider such as ``sheets.client`` always calls
      ``method="GET", body=None``).
    * **B3 — JSON dict vs raw bytes on success** → :meth:`_on_success`. Default:
      ``json.loads`` → dict; the export reader overrides it to return the response
      **bytes** verbatim (the xlsx download).
    * **B4 — token wiring** → :meth:`_fetch_token`. The credentialed clients use
      :class:`CredentialedRawHttpClient` (inline ``app_id``/``app_secret``,
      threading ``urlopen`` into the fetch); the export reader resolves a zero-arg
      ``token_provider``.

    Throttle placement is per-client and stays **outside** this skeleton: the read
    and write clients throttle in their own ``_get``/``_write`` wrappers *around*
    :meth:`_send`; the export reader paces *inside* the send via the
    :meth:`_before_send` hook (a no-op in the base), which preserves each client's
    exact acquire ordering.

    Subclasses set ``self._base`` / ``self._urlopen`` / ``self._timeout`` /
    ``self._token`` in their own ``__init__`` (signatures unchanged — no migration)
    and implement :meth:`_fetch_token`.
    """

    #: Query-string ``safe`` chars: A1-range punctuation (``! : ,``) is left
    #: unescaped so a range / comma-separated range list survives on the wire
    #: (the sheets spike's ``get()`` posture).
    _QUERY_SAFE = "!:,"

    def _fetch_token(self):  # pragma: no cover - always overridden
        raise NotImplementedError

    def _credential_pair(self):
        """The env-var pair THIS client's tenant token is minted from — ``()`` if it cannot say.

        **Every rider overrides this**, and a guard in the source repository
        (``tests/test_token_mint_credential_refusal.py``) reddens for a
        :class:`RawHttpClient` subclass that does not, because the base answer is
        the one that loses the attribution: a rejected credential on a write leg
        must name ``LARK_WRITE_APP_*`` and not the pair a reader happens to be
        resolving. The riders already declare this pair for a scope denial
        (``credential_env=`` on :func:`raise_for_lark_code`); this is the same fact
        asked one call earlier, before there is a token to be denied with.

        A method rather than an attribute because the read answer is
        :func:`~larkdocio.common.auth.resolved_read_env`, which depends on the
        environment **as it is when the call fails** — a pair captured at
        construction can name a variable that is no longer the one in force.
        """
        return ()

    def _bearer(self):
        """The lazily-cached tenant bearer token (fetched once per client).

        **The one place every raw-HTTP surface's token is fetched, which is why the
        credential attribution is stamped here** (LD-672): the mint knows the id and
        secret but not which variables they came from, and threading a
        ``credential_env=`` through each of the nine riders' injectable
        ``token_fetcher`` seams would change a signature every offline test injects
        into. See :func:`attribute_token_mint_failure`.
        """
        if self._token is None:
            try:
                self._token = self._fetch_token()
            except LarkAPIError as rejected:
                attribute_token_mint_failure(rejected, self._credential_pair())
                raise
        return self._token

    def _build_request(self, method, path, *, body=None, params=None):
        url = self._base + path
        if params:
            url += "?" + urllib.parse.urlencode(params, safe=self._QUERY_SAFE)
        data = json.dumps(body).encode() if body is not None else None
        return urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self._bearer()}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )

    def _before_send(self):
        """Hook run after the request is built and before ``urlopen`` — a no-op by
        default. The export reader overrides it to acquire its read throttle here
        (preserving its build-then-acquire-then-send order)."""

    def _on_success(self, raw: bytes):
        """Transform a 2xx response body. Default (the JSON clients): parse the
        body as JSON → a dict."""
        return json.loads(raw)

    def _on_http_error(self, e, method, path):
        """Handle an ``HTTPError``. Default (the JSON clients): parse the Lark error
        body and **return** it (never raise here); a non-JSON body degrades to the
        ``{"code": <http>, "msg": "HTTP <http>"}`` fallback so the caller can still
        type it."""
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"code": e.code, "msg": f"HTTP {e.code}"}

    def _send(self, method, path, *, body=None, params=None):
        """Build + send ONE raw attempt. Returns :meth:`_on_success` on a 2xx and
        :meth:`_on_http_error` on an ``HTTPError``; a genuine transport failure
        (``URLError``) always raises the typed :class:`LarkAPIError`."""
        req = self._build_request(method, path, body=body, params=params)
        self._before_send()
        try:
            raw = self._urlopen(req, timeout=self._timeout).read()
        except urllib.error.HTTPError as e:
            return self._on_http_error(e, method, path)
        except urllib.error.URLError as e:
            raise LarkAPIError(f"{method} {path} failed: {e}")
        return self._on_success(raw)


class CredentialedRawHttpClient(RawHttpClient):
    """A :class:`RawHttpClient` whose bearer is a ``tenant_access_token`` fetched
    from an **inline** ``(app_id, app_secret, domain)`` credential pair, threading
    the client's own ``urlopen`` into the fetch (B4 — the sheets read client and
    both write clients). Subclasses set ``self._app_id`` / ``self._app_secret`` /
    ``self._domain`` / ``self._token_fetcher`` / ``self._urlopen`` in ``__init__``.
    """

    def _fetch_token(self):
        return self._token_fetcher(
            self._app_id, self._app_secret, self._domain, urlopen=self._urlopen
        )
