"""larkdocio.common.sdk_client — the ONE ``lark-oapi`` SDK client constructor core (LD-534).

**What lives here: the MECHANISM an SDK-backed client is CONSTRUCTED out of** — the five
chained builder calls, the injectable-client seam, the injectable-limiter seam, and the typed
credential-absent refusal. Nothing else. No request is built here, no endpoint is named, no
response is read, no error is mapped, and no retry or backoff policy is decided: this module
runs once per client, before the first call.

**Why it exists (the drift it closes).** The raw-HTTP half of this project's transport story
was consolidated long ago — nine thin declarations ride one shared skeleton in
:mod:`larkdocio.common.transport`. The SDK half grew its own unshared idiom **eight times**,
once per surface, in landing order: the same five-call chain, the same
``rate_limiter if rate_limiter is not None else RateLimiter(...)`` line, the same
``if not (app_id and app_secret): raise`` guard. The cost was never runtime and never really
line count — it was that a fix to the shared shape (a log level, a timeout policy, a
credential-absent message) had to be found and applied eight times, and the eighth copy is the
one nobody remembers.

**What each surface keeps.** Only its own policy, and it keeps all of it: its constructor
signature, its limiter defaults, its timeout default, its credential pair, its own refusal
texts, and its own ``from_read_credentials`` / ``from_write_credentials`` classmethod. What it
stops holding is the plumbing.

**The credential fence, and it is the reason this module's shape is what it is.** The READ and
WRITE credential pairs are resolved **independently, at each call site, by name** — this module
neither imports, names, nor calls either getter, and there is deliberately no
``credentials=``-shaped parameter, no getter argument and no "which pair" flag anywhere in it.
The distinction that matters: :func:`resolve_sdk_client` accepts an *already-resolved* id and
secret, exactly as every one of these constructors already did, because a constructor that
builds an SDK client must be handed one; what it must never acquire is the ability to *resolve*
a pair, because a single shared resolver is the one seam through which a read client could
reach a write credential. A guard asserts the fence structurally — no module under
``larkdocio.common`` outside the credential module itself and the package facade may so much as
name a getter (in the source repository: ``tests/test_sdk_client_core.py``) — and it is structural on
purpose: on the tenant these measurements were made on the two pairs named one app, so a runtime or scope-based check could not tell them apart.

**The docx reader is IN for the chain and OUT of the seam, deliberately.** The reader
(:mod:`larkdocio.read.client`) builds its client through :func:`build_sdk_client` like every
other surface, so the chain genuinely exists once. It does **not** use
:func:`resolve_sdk_client` or :func:`resolve_rate_limiter`, and that is a decision rather than
an omission: it has no injectable-client seam, **no rate limiter at all**, a positional
constructor, and it holds its client on a *public* attribute that stubs and tests assign to by
name. It is also the determinism-guaranteed read path, so giving it a limiter it never had
would change its pacing — a behaviour change wearing a refactor's clothes. Its shape was
weighed and left alone; only the chain was shared.
"""
import lark_oapi as lark

from larkdocio.common.transport import RateLimiter
from larkdocio.common.errors import LarkConfigError


def build_sdk_client(app_id: str, app_secret: str, domain: str, *, timeout: int = 30):
    """The five chained ``lark.Client.builder()`` calls — the only place they exist.

    ``domain`` is a **tenant domain**, never a URL: the ``https://open.`` prefix is this
    function's business, which is what makes ``"larksuite.com"`` and ``"feishu.cn"`` the only
    thing a caller has to know. The log level is pinned to ``ERROR`` because the SDK's default
    writes request chatter to stdout, and stdout is where this library's readers put Markdown.
    """
    return lark.Client.builder() \
        .app_id(app_id) \
        .app_secret(app_secret) \
        .domain(f"https://open.{domain}") \
        .log_level(lark.LogLevel.ERROR) \
        .timeout(timeout) \
        .build()


def require_credentials(app_id: str, app_secret: str, message: str) -> None:
    """Raise :class:`~larkdocio.errors.LarkConfigError` with ``message`` unless **both** halves
    of a credential pair are present.

    Both halves, never one: an id with no secret is as unusable as neither, and mixing a
    configured id with a blank secret is how a caller ends up reading an authentication failure
    instead of a configuration error. ``message`` is the caller's own sentence — every surface
    says what *it* cannot do, so the refusal names the operation the reader was attempting
    rather than a generic missing-credential complaint.
    """
    if not (app_id and app_secret):
        raise LarkConfigError(message)


def resolve_sdk_client(sdk_client, app_id: str, app_secret: str, domain: str, *,
                       timeout: int = 30, no_credentials: str):
    """The injectable-client seam: ``sdk_client`` if one was supplied, else a real client.

    **An injected client bypasses credential resolution entirely** — that is the seam's whole
    contract, and it is why every offline test of these surfaces can construct a client with
    blank credentials and a stub. Only when nothing was injected do the credentials matter, and
    then their absence is a typed refusal carrying ``no_credentials``, raised *before* anything
    is built and long before anything is sent.
    """
    if sdk_client is not None:
        return sdk_client
    require_credentials(app_id, app_secret, no_credentials)
    return build_sdk_client(app_id, app_secret, domain, timeout=timeout)


def resolve_rate_limiter(rate_limiter, max_per_sec: int, window: float) -> RateLimiter:
    """The injectable-limiter seam: ``rate_limiter`` if one was supplied, else the family's own.

    The defaults stay with the surface — a Base read, a schema change and a media upload pace
    differently, and each of those numbers is evidence about one endpoint family rather than a
    project-wide policy. What is shared is only the *"a supplied limiter is the limiter, not a
    template"* rule, which is the half a caller injecting a deterministic clock depends on.
    """
    if rate_limiter is not None:
        return rate_limiter
    return RateLimiter(max_per_sec, window=window)
