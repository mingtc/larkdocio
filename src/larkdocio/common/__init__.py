"""larkdocio.common — the shared read/write core.

Everything genuinely shared between the reader and the
writer lives here as **one hardened substrate** that also DEFINES the
typed errors — the exception taxonomy the whole library raises and the Lark
error-code lookup beside it (:mod:`.errors`, :mod:`.error_codes`),
tenant-token/auth management + the IPv4 pin (:mod:`.auth`), URL
validation (:mod:`.url`), the write-side HTTP transport carrying the
write-throttle + ``99991400`` backoff (:mod:`.transport`), and the staleness-marker
vocabulary both write surfaces state their never-silent guard in
(:mod:`.staleness`). Read-only or write-only specifics stay in
``read/`` / ``write/``.

This is the **bottom tier**: no module in this package imports anything above it at import
time, which is what makes the taxonomy safe to define here even though the core raises it.

Importers get the shared primitives straight off this package
(``from larkdocio.common import validate_download_url, get_read_credentials,
WriteTransport, ...``). The pre-extraction module paths (``larkdocio.auth``,
``larkdocio.utils.url``) remain as transparent back-compat shims that re-export
these same objects, as does ``larkdocio.errors`` — which is not legacy, and is still the
path the packaged guide's recipes use for the taxonomy.
``larkdocio.utils.common`` and ``larkdocio.utils.sanitize`` now live
here as :mod:`.reporting` (the operator-facing ``pretty_print`` / ``check_err``) and
:mod:`.sanitize` (filename sanitisation); import them from those modules — they are
deliberately not re-exported on this facade.
"""

from larkdocio.common.url import (
    BASE_DEEP_LINK_CLICK_MEASUREMENT,
    DOCUMENT_URL_TYPES,
    DOCX_BLOCK_ANCHOR_MEASUREMENT,
    DOCX_EDITION_LINK_CLICK_MEASUREMENT,
    DOCX_SECTION_ANCHOR_UI_ONLY,
    URL_PATH_SHAPES,
    URL_TYPE_SURFACES,
    unescape_url,
    validate_download_url,
)
from larkdocio.common.doc_link import docx_block_url, docx_edition_url
from larkdocio.common.auth import (
    DISABLE_IPV4_PIN_ENV,
    LEGACY_ENV,
    READ_ENV,
    WRITE_ENV,
    apply_ipv4_pin,
    get_read_credentials,
    get_write_credentials,
    init_env,
    pin_socket_to_ipv4,
    set_env_credentials,
)
from larkdocio.common.staleness import (
    REVISION_GUARD_ACTIVE,
    REVISION_GUARD_UNAVAILABLE,
    revision_guard_status,
)
from larkdocio.common.transport import (
    DEFAULT_BASE_BACKOFF,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_WRITES_PER_SEC,
    CredentialedRawHttpClient,
    RateLimiter,
    RawHttpClient,
    WriteTransport,
    api_base,
    fetch_tenant_access_token,
    raise_for_lark_code,
)

__all__ = [
    # url
    "DOCUMENT_URL_TYPES",
    "URL_PATH_SHAPES",
    "URL_TYPE_SURFACES",
    "unescape_url",
    "validate_download_url",
    # the docx deep-link family — the mintable grammars and the one that is not, each
    # carrying the edge of its own evidence (they are asked about together, so they are
    # reachable together). The edition link's label carries the narrowest claim of the
    # three: click-VERIFIED (LD-419), but only on one client (Lark WEB), one tenant, one
    # day — with the unclicked axes (mobile, the desktop app, wiki-wrapped, every other
    # tenant) still named unmeasured, never averaged into a broader claim.
    # The Base table/view/record grammar's own label — a FOURTH strength of claim, kept
    # beside the three above so a reader comparing them finds them together. It is minted
    # by `larkdocio.base.table_url` / `view_url`, which live on the Base surface; only the
    # disclosure is authored here, where every deep-link label is.
    "BASE_DEEP_LINK_CLICK_MEASUREMENT",
    "DOCX_BLOCK_ANCHOR_MEASUREMENT",
    "DOCX_EDITION_LINK_CLICK_MEASUREMENT",
    "DOCX_SECTION_ANCHOR_UI_ONLY",
    "docx_block_url",
    "docx_edition_url",
    # auth / ipv4 pin
    "DISABLE_IPV4_PIN_ENV",
    "LEGACY_ENV",
    "READ_ENV",
    "WRITE_ENV",
    "apply_ipv4_pin",
    "get_read_credentials",
    "get_write_credentials",
    "init_env",
    "pin_socket_to_ipv4",
    "set_env_credentials",
    # transport
    "DEFAULT_BASE_BACKOFF",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_MAX_WRITES_PER_SEC",
    "CredentialedRawHttpClient",
    "RateLimiter",
    "RawHttpClient",
    "WriteTransport",
    "api_base",
    "fetch_tenant_access_token",
    "raise_for_lark_code",
    # staleness vocabulary (shared by both write surfaces — LD-143)
    "REVISION_GUARD_ACTIVE",
    "REVISION_GUARD_UNAVAILABLE",
    "revision_guard_status",
]
