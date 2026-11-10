"""larkdocio.drive.versions_write — create ONE named version of a Drive file.

**A module of its own, and the reason is a claim this project keeps.** The command line is
read-only and says so, and its guard is falsifiable: it walks what a CLI handler can reach and
fails if a write engine is in that set. ``larkdocio.drive.client`` is on that path (the folder
verb), so the write client cannot live beside the read one — the models and the ``obj_type`` /
``name`` policy live in :mod:`larkdocio.drive.versions`, which both sides share, and the
mutating client lives here, reachable from no CLI command. The same split ``larkdocio.base``
makes between its read op registry and its write registries.

**WRITE credentials only**, and the head-revision leg the pairing rests on is made on that same
pair — so this op never mixes credential pairs and never falls back across them.
"""
import urllib.request
from dataclasses import dataclass
from typing import Optional, Tuple

from larkdocio.common.auth import WRITE_ENV, apply_ipv4_pin, get_write_credentials
from larkdocio.common.transport import (
    CredentialedRawHttpClient,
    RateLimiter,
    api_base,
    fetch_tenant_access_token,
    raise_for_lark_code,
)
from larkdocio.drive import ops
from larkdocio.drive.versions import (
    DOCX_OBJ_TYPE,
    REVISION_UNAVAILABLE_NOT_DOCX,
    REVISION_UNAVAILABLE_READ_FAILED,
    Version,
    check_name,
    check_obj_type,
    versions_path,
)
from larkdocio.errors import LarkConfigError
from larkdocio.write.client import WriteClient


@dataclass(frozen=True)
class CreatedVersion:
    """A newly created version, **paired with the head revision read immediately before it**.

    ``revision`` is ``None`` — never zero, never synthesized — when the pairing could not be
    made, and ``revision_note`` then says why.
    """

    version: Version
    #: The name the caller asked for. Lark may hand back a different one (a duplicate becomes
    #: ``"V1.0(1)"``), so both are reported and neither is silently preferred.
    requested_name: str
    revision: Optional[int] = None
    revision_note: Optional[str] = None

    @property
    def name_was_changed_by_lark(self) -> bool:
        """``True`` when Lark's echoed name differs from the requested one (the duplicate case)."""
        return self.version.name != self.requested_name

    @property
    def triple(self) -> Tuple[Optional[str], Optional[str], Optional[int]]:
        """``(name, token, revision)`` — the ledger row this whole op exists to produce."""
        return (self.version.name, self.version.token, self.revision)


class DriveVersionsWriteClient(CredentialedRawHttpClient):
    """The Drive surface's **first mutating** client: it creates one named version.

    **WRITE credentials only**, resolved through :func:`~larkdocio.common.auth.
    get_write_credentials`; nothing here consults, infers or falls back to the READ pair, and
    a denial is surfaced with Lark's own code and message rather than retried on another pair
    (the credential doctrine in PROJECT.md, in the dev repo — and its § Credential
    aliasing — on the tenant these measurements were made on the two
    pairs named one app, which the code must keep treating as a coincidence).

    Throttled by the same evidence-anchored limiter the enumeration client rides (one call per
    :data:`~larkdocio.drive.client.DRIVE_MIN_REQUEST_SPACING_SECONDS`), so the two Drive legs
    pace alike.
    """

    def __init__(
        self,
        app_id,
        app_secret,
        domain="larksuite.com",
        *,
        urlopen=urllib.request.urlopen,
        token_fetcher=fetch_tenant_access_token,
        rate_limiter=None,
        timeout=30,
    ):
        from larkdocio.drive.client import DRIVE_MIN_REQUEST_SPACING_SECONDS

        self._app_id = app_id
        self._app_secret = app_secret
        self._domain = domain
        self._base = api_base(domain)
        self._urlopen = urlopen
        self._token_fetcher = token_fetcher
        self._limiter = rate_limiter if rate_limiter is not None else RateLimiter(
            1, window=DRIVE_MIN_REQUEST_SPACING_SECONDS)
        self._timeout = timeout
        self._token = None
        self._api_calls = 0

    def _credential_pair(self):
        """The WRITE pair — this client resolves no other, so a rejected credential here
        names ``LARK_WRITE_APP_*`` and never the pair a reader is resolving (LD-672)."""
        return WRITE_ENV

    @classmethod
    def from_write_credentials(cls, domain="larksuite.com", **kwargs):
        """Build from the environment's **WRITE** pair (+ the shared IPv4 pin)."""
        app_id, app_secret = get_write_credentials()
        if not app_id or not app_secret:
            raise LarkConfigError(
                f"Drive versions write client: no WRITE credentials resolved. Set "
                f"{WRITE_ENV[0]}/{WRITE_ENV[1]}."
            )
        apply_ipv4_pin()
        return cls(app_id, app_secret, domain, **kwargs)

    @property
    def api_calls(self) -> int:
        """How many API calls this client has made on its own transport."""
        return self._api_calls

    @property
    def limiter(self):
        """The limiter every call on this client passes through."""
        return self._limiter

    def create_version(self, file_token, name, obj_type=DOCX_OBJ_TYPE, *,
                       revision_reader: Optional[WriteClient] = None) -> CreatedVersion:
        """Create a named version of ``file_token``, **paired with the head revision**.

        ``POST /open-apis/drive/v1/files/:file_token/versions`` with
        ``{"name": …, "obj_type": …}``. The response's ``data`` **is the version object
        itself** — there is no ``data.version`` wrapper, and its ``version`` field is the new
        token (capture ``02-``).

        **THE PAIRING, which is why this op exists.** The head docx revision is read
        **immediately before** the create — one metadata call, no block tree — and returned
        alongside the new version, so a ledger can record ``(name, token, revision)`` as one
        row. The exactness condition, as measured: creating a version is **revision-inert** —
        the head revision measured the same immediately before and immediately after the create
        — so the (name, token, revision) triple is exact absent a concurrent edit, and a
        concurrent edit is the one thing that can make it wrong. Where the revision is not
        available — the read failed, or ``obj_type`` is not ``docx`` (a ``sheet`` version has
        no docx revision) — the field is honestly ``None`` with the reason in
        ``revision_note``, never synthesized and never zero.

        **``name`` is required.** A missing or empty name is refused **locally and typed**
        before the call, in Lark's own words (``252804105 Params error, param [name] is
        wrong.``, capture ``04-``) rather than in an invented message of this library's.

        **Duplicate names are ALLOWED, and that is disclosed rather than deduped.** A second
        ``"V1.0"`` created a distinct token and came back named ``"V1.0(1)"`` (capture
        ``104-``); the result reports both the requested and the echoed name
        (:attr:`CreatedVersion.name_was_changed_by_lark`) and nothing is warned away.

        **No length ceiling is claimed:** a **300**-character name was accepted and echoed
        whole (capture ``105-``), so the true ceiling is **unmeasured**.

        **No quota is claimed:** 7 versions on one document, 4 of them back-to-back at roughly
        2 calls/s, all ``code 0``, with no warning field and no rate refusal (captures ``106-``
        – ``109-``; ``107-`` and ``108-`` are in the dev repo only). The honest words are *no quota disclosed* — never a claim that none
        exists.

        ``obj_type`` follows :func:`check_obj_type`: required, the two measured-refused values
        typed locally, and an unmeasured value passed through so Lark answers for it.
        """
        obj_type = check_obj_type(obj_type)
        name = check_name(name)

        revision, revision_note = None, None
        if obj_type == DOCX_OBJ_TYPE:
            if revision_reader is None:
                revision_reader = WriteClient(
                    self._app_id, self._app_secret, self._domain,
                    urlopen=self._urlopen, token_fetcher=self._token_fetcher,
                    timeout=self._timeout)
            try:
                revision = revision_reader.read_document_revision(file_token)
            except Exception as exc:  # noqa: BLE001 - the pairing degrades; the create does not
                revision, revision_note = None, REVISION_UNAVAILABLE_READ_FAILED.format(
                    error=exc)
        else:
            revision_note = REVISION_UNAVAILABLE_NOT_DOCX.format(obj_type=obj_type)

        descriptor = ops.op("create_version")
        self._limiter.acquire()
        self._api_calls += 1
        response = self._send(
            descriptor.http_method, versions_path(file_token),
            body={"name": name, "obj_type": obj_type})
        code = response.get("code") if isinstance(response, dict) else None
        if not (code in (0, None) or str(code) == "0"):
            raise_for_lark_code(response, context="drive create_version",
                                credential_env=WRITE_ENV)
        return CreatedVersion(
            version=Version.from_payload(response.get("data") or {}),
            requested_name=name,
            revision=revision,
            revision_note=revision_note,
        )
