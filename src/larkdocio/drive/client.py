"""larkdocio.drive.client — the Drive folder **enumeration** client.

Three read legs, one transport, one throttle, one refusal seam:

* ``GET /open-apis/drive/v1/files`` — **the enumerator**: a folder's direct children, paged to
  exhaustion. SDK-modelled, ridden raw here so all three legs share one code path.
* ``GET /open-apis/drive/explorer/v2/root_folder/meta`` — the caller's own root folder. A
  **legacy, non-SDK family**: the pinned ``lark-oapi`` models no request for it at all.
* ``POST /open-apis/drive/v1/metas/batch_query`` — a folder's **own** title. A documented
  *query* POST that changes nothing (the listing returns a folder's children, never its own
  name), and the op registry declares that explicitly — see :mod:`larkdocio.drive.ops`.

**No new infrastructure.** All three ride
:class:`larkdocio.common.transport.CredentialedRawHttpClient`, the shared raw-HTTP core built
for the SDK-absent v2 sheets endpoints, which *"genuinely need raw urllib"*. The cost of a
non-SDK endpoint here is a thin declaration.

**READ credentials only.** :meth:`DriveClient.from_read_credentials` resolves the READ pair via
:mod:`larkdocio.common.auth`; nothing in this package names, imports or falls back to the WRITE
pair (the read/write credential separation — and on the tenant these measurements were made
on the two pairs named one app, which is why a same-tenant success proves nothing about scopes).

**Throttled by construction, and the pace is EVIDENCE-ANCHORED rather than measured.** The two
probe rounds made 17 live calls at **≥1.2 s spacing with no limit ever hit**, and 7 calls
covered a 35-node tree — so the default limiter admits one call per 1.2 s
(:data:`DRIVE_MIN_REQUEST_SPACING_SECONDS`), the only spacing this project has evidence for.
**Rate limits are documented, never probed** — the standing posture of this project: nothing
here walks into a limit to discover where it is.

**`option` is never sent — and neither are `order_by` / `direction`.** Both plausible ``option``
values (``obj_type`` and ``1``) were refused ``HTTP 400 / 1061002``
(``tests/captures/drive-spike/captures/14-option-param.json``, in the source repository): the parameter has an
undocumented, non-guessable value vocabulary and a wrong value breaks the **whole** call rather
than being ignored. ``order_by``/``direction`` are unsent for a different reason — their
interaction with paging is unproven, and unproven is not a default — and both decisions are
pinned by test so a later contributor meets the decision instead of adding a parameter that
silently reshapes pagination.
"""
# The internal record this docstring used to carry lives here instead, because the shipped
# guide now sends a consumer to `help(larkdocio.drive.client)` and an issue id resolves to
# nothing for them: LD-324 built this client, LD-126 built the shared raw-HTTP core
# it rides, and LD-100 set the documented-never-probed rate-limit posture, unchanged
# since.
import urllib.request

from larkdocio.common.auth import apply_ipv4_pin, get_read_credentials, resolved_read_env
from larkdocio.common.destination import ApplicationRootToken
from larkdocio.common.metas import failed_reason
from larkdocio.common.transport import (
    CredentialedRawHttpClient,
    RateLimiter,
    api_base,
    fetch_tenant_access_token,
    raise_for_lark_code,
)
from larkdocio.drive import ops
from larkdocio.drive.errors import (
    DRIVE_NOT_FOUND_CODE,
    FOLDER_REFUSED_CODE,
    PaginationStalledError,
    drive_not_found,
    folder_refused,
)
from larkdocio.drive.lookup import FolderNameMatches, match_children_by_name
from larkdocio.drive.models import (
    FolderContents,
    FolderName,
    SecurityLevel,
    Truncation,
)
from larkdocio.drive.versions import (
    DOCX_OBJ_TYPE,
    Version,
    VersionListing,
    check_obj_type,
    versions_path,
)
from larkdocio.errors import LarkConfigError

#: The window a documented per-minute tier would be expressed over.
DRIVE_RATE_WINDOW_SECONDS = 60.0

#: Client-side cap per :data:`DRIVE_RATE_WINDOW_SECONDS`. **Not** a fraction of a documented
#: tier — no drive rate tier was readable — but the spike's own sustained spacing: 50 requests
#: a minute is exactly the 1.2 s the two probe rounds ran at, over 17 calls, with zero
#: ``rate-limit`` answers. One literal, so re-pacing the surface is a one-line edit.
DEFAULT_MAX_READS_PER_WINDOW = 50

#: The minimum spacing the two literals imply — DERIVED, so the pace cannot disagree with the
#: cap. The default limiter admits one call per this interval rather than a burst of fifty
#: followed by a stall, which keeps a real caller at the spacing the evidence covers.
DRIVE_MIN_REQUEST_SPACING_SECONDS = (
    DRIVE_RATE_WINDOW_SECONDS / DEFAULT_MAX_READS_PER_WINDOW)

#: Children per listing page. The round-2 probe used 50 and every folder in the maintainer's real tree
#: was a single page at that size.
DEFAULT_PAGE_SIZE = 50

#: Pages one folder may be walked over before the exhaustion loop DISCLOSES a truncation. Not
#: infinite: 200 pages at the default page size is 10 000 children in one folder.
DEFAULT_MAX_PAGES = 200

#: The ``doc_type`` the security-level leg sends by default — the ONE object type the field was
#: measured on. Other types are passed through rather than refused: a type this library never
#: tried is unmeasured, not unsupported.
DOCX_DOC_TYPE = "docx"


class DriveClient(CredentialedRawHttpClient):
    """The throttled, READ-only Drive enumeration client.

    **How to build one, first, because that is what a caller needs:**
    :meth:`from_read_credentials` is the normal construction — it resolves the environment's
    READ pair and needs nothing but a loaded ``.env``. The plain constructor
    ``DriveClient(app_id, app_secret, domain)`` is for a caller holding its own credentials.

    **What you build one FOR.** Two shipped functions take a client as their first positional
    argument and construct none of their own: :func:`~larkdocio.drive.walk.walk_folder` (the
    enumeration alone) and :func:`~larkdocio.drive.manifest.folder_manifest`'s upstream
    :func:`~larkdocio.drive.read.read_folder` — which *will* build one for you when its
    ``client=`` keyword is omitted. Passing your own is how you choose the credential pair and
    the API domain, and how one rate limiter is shared across every call of a run instead of
    one being minted per entry point.

    ``urlopen`` / ``token_fetcher`` / ``rate_limiter`` are injectable so request construction,
    pacing and refusal typing are all testable offline; the defaults are real ``urllib``, the
    shared tenant-token mint, and a limiter admitting one call per
    :data:`DRIVE_MIN_REQUEST_SPACING_SECONDS` (**1.2 s** — the spike's own spacing). They are a
    **test seam**, not the construction path — a caller reaching for them is on the wrong road.

    Every call goes through :meth:`_call`, which takes its verb from the op descriptor rather
    than from a hand-typed literal — so a leg cannot be added that bypasses the pace, the
    typing, or the declared read-only verb set.
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
        page_size=DEFAULT_PAGE_SIZE,
        timeout=30,
    ):
        self._app_id = app_id
        self._app_secret = app_secret
        self._domain = domain
        self._base = api_base(domain)
        self._urlopen = urlopen
        self._token_fetcher = token_fetcher
        self._limiter = rate_limiter if rate_limiter is not None else RateLimiter(
            1, window=DRIVE_MIN_REQUEST_SPACING_SECONDS)
        self._page_size = page_size
        self._timeout = timeout
        self._token = None
        self._api_calls = 0

    def _credential_pair(self):
        """The READ pair, as resolved right now — enumeration is a read and this client
        consults no other pair. It is what a rejected-credential refusal names (LD-672),
        the same pair its scope denials already name."""
        return resolved_read_env()

    # -- construction ------------------------------------------------------ #

    @classmethod
    def from_read_credentials(cls, domain="larksuite.com", **kwargs):
        """Build from the environment's **READ** pair (+ the shared IPv4 pin).

        Enumeration is a read; the write pair is never consulted here, and nothing in this
        package can consult it. Missing or half-configured read credentials are a loud
        :class:`~larkdocio.errors.LarkConfigError`, never a silent fallback.
        """
        app_id, app_secret = get_read_credentials()
        if not app_id or not app_secret:
            raise LarkConfigError(
                "Drive enumeration client: no READ credentials resolved. Set "
                "LARK_READ_APP_ID/LARK_READ_APP_SECRET (or the legacy "
                "LARK_APP_ID/LARK_APP_SECRET)."
            )
        apply_ipv4_pin()
        return cls(app_id, app_secret, domain, **kwargs)

    # -- pacing + provenance ----------------------------------------------- #

    @property
    def limiter(self):
        """The limiter every call on this client passes through."""
        return self._limiter

    @property
    def api_calls(self) -> int:
        """How many API calls this client has made. Incremented in exactly one place."""
        return self._api_calls

    # -- the ONE send seam -------------------------------------------------- #

    def _call(self, name, *, path=None, params=None, body=None, token=None):
        """Throttle, send **one** request on the op's own declared verb, then type the answer.

        The verb comes from the descriptor (``descriptor.http_method``), never from a literal
        at the call site — which is what makes the shipped verb set enumerable and keeps R1
        GET-only-plus-one-declared-query by construction.
        """
        descriptor = ops.op(name)
        self._limiter.acquire()
        self._api_calls += 1
        response = self._send(
            descriptor.http_method, path or descriptor.endpoint, body=body, params=params)
        return self._typed(response, context=descriptor.name, token=token)

    def _typed(self, response, *, context, token=None):
        """Success through; ``1061002`` and ``1061003`` to their own types; the rest to the
        shared taxonomy (so a scope denial still arrives as a permission error)."""
        code = response.get("code") if isinstance(response, dict) else None
        if code in (0, None) or str(code) == "0":
            return response
        if str(code) == str(FOLDER_REFUSED_CODE):
            raise folder_refused(token, code=code, msg=response.get("msg"))
        if str(code) == str(DRIVE_NOT_FOUND_CODE):
            raise drive_not_found(token, code=code, msg=response.get("msg"))
        return raise_for_lark_code(
            response, context=f"drive {context}", credential_env=resolved_read_env())

    # -- the enumerator ----------------------------------------------------- #

    def _listing_params(self, folder_token, page_size, page_token):
        """The ONE builder for listing params — and the whole of what may go on the wire.

        ``option`` is absent, deliberately and permanently until a documented value exists;
        ``order_by`` / ``direction`` likewise, because their interaction with paging is
        unproven. ``page_token`` is passed through **verbatim**: it is an opaque 135-character
        cursor, and nothing here parses, increments or reconstructs it.
        """
        params = {"page_size": page_size or self._page_size}
        if folder_token:
            params["folder_token"] = folder_token
        if page_token:
            params["page_token"] = page_token
        return params

    def list_folder_children(self, folder_token=None, *, page_size=None, page_token=None
                             ) -> FolderContents:
        """**One page** of a folder's direct children (omit the token ⇒ the caller's root).

        One page is a page, never the folder: read ``has_more`` / ``next_page_token``, or use
        :meth:`list_folder_children_to_exhaustion`, which does it for you.
        """
        response = self._call(
            "list_folder_children",
            path=ops.LIST_FILES_ENDPOINT,
            params=self._listing_params(folder_token, page_size, page_token),
            token=folder_token,
        )
        return FolderContents.from_response(response, folder_token=folder_token)

    def list_folder_children_to_exhaustion(self, folder_token=None, *, page_size=None,
                                           max_pages=DEFAULT_MAX_PAGES) -> FolderContents:
        """Every child of a folder, following ``has_more`` / ``next_page_token`` to exhaustion.

        **The first page is never the folder.** The loop cannot spin: a repeated cursor, a
        ``has_more: true`` with no cursor, and an empty page that still claims more each raise
        :class:`~larkdocio.drive.errors.PaginationStalledError` — a typed stop rather than a
        hang. The page budget (``max_pages``, default **200**) is the one bound that is *not*
        an error: hitting it returns a :class:`~larkdocio.drive.models.Truncation` on the
        result, because a budget that fires silently would make the answer lie about the
        folder.
        """
        children = []
        seen_cursors = set()
        cursor = None
        pages = 0
        truncation = None
        while True:
            contents = self.list_folder_children(
                folder_token, page_size=page_size, page_token=cursor)
            pages += 1
            children.extend(contents.children)
            if not contents.has_more:
                break
            if not contents.children:
                raise PaginationStalledError(
                    f"Lark returned an empty page for folder {folder_token} while still "
                    "reporting has_more: true — the listing cannot make progress."
                )
            if not contents.next_page_token:
                raise PaginationStalledError(
                    f"Lark reported has_more: true with no next_page_token for folder "
                    f"{folder_token} — the listing cannot make progress."
                )
            if contents.next_page_token in seen_cursors:
                raise PaginationStalledError(
                    f"Lark returned a repeated next_page_token for folder {folder_token} — "
                    "the listing would loop, so it stopped instead."
                )
            seen_cursors.add(contents.next_page_token)
            cursor = contents.next_page_token
            if pages >= max_pages:
                truncation = Truncation(
                    cap="max_pages",
                    limit=max_pages,
                    at_folder=str(folder_token),
                    at_path=str(folder_token),
                    not_visited=("the folder's remaining pages",),
                    detail=("Lark still reported has_more: true; raise max_pages to see the "
                            "rest of this folder."),
                )
                break
        return FolderContents(
            folder_token=folder_token,
            children=tuple(children),
            pages=pages,
            has_more=False if truncation is None else True,
            truncation=truncation,
        )

    def find_children_by_name(self, folder_token, name, *, page_size=None,
                              max_pages=DEFAULT_MAX_PAGES) -> FolderNameMatches:
        """**Is this name already in that folder?** — the check to run before an upload.

        Lists ``folder_token`` to exhaustion through the leg above and hands back every child
        already carrying that **byte-identical** ``name``, each with its token, so a caller can
        decide *skip or replace* before writing. It answers a question and takes no action:
        nothing here uploads, deletes, renames or de-duplicates, because an upload that quietly
        trashed somebody's file first would be destroying data as a convenience.

        **Why it exists.** An upload is **not** idempotent — sending the same name and the same
        bytes again mints a second file object with its own token, and no parameter on either
        upload family changes that. Without this call an automation's second run silently
        doubled the folder, which is the one collision behaviour a consumer has to plan around
        (:data:`larkdocio.drive.lookup.DUPLICATE_UPLOAD_BEHAVIOUR`).

        **It is a check, not a lock.** Another writer can add the same name between this call
        and the upload; nothing would refuse them. And an incomplete listing is **not** evidence
        of absence: a page-budget truncation is carried on the answer and
        :attr:`~larkdocio.drive.lookup.FolderNameMatches.complete` reports it.

        **Names only, and that fence is measured.** The listing reports
        :data:`~larkdocio.drive.lookup.IDENTITY_THE_LISTING_AFFORDS` and the metadata query
        reports no more — **neither carries a size or a digest**
        (:data:`~larkdocio.drive.lookup.IDENTITY_NOT_AFFORDED`) — so a match means *same name*,
        never *same bytes*. Download the token and hash it if that is the question.

        No new endpoint is reached: this is the folder listing already shipped here, so it asks
        for no scope of its own.
        """
        if not folder_token:
            raise LarkConfigError(
                "a by-name lookup needs a folder token: this call asks what is already inside "
                "ONE folder, and no default destination is picked anywhere in this library")
        contents = self.list_folder_children_to_exhaustion(
            folder_token, page_size=page_size, max_pages=max_pages)
        return FolderNameMatches(
            folder_token=folder_token,
            name=name,
            matches=match_children_by_name(contents.children, name),
            listed=len(contents.children),
            truncation=contents.truncation,
        )

    # -- the versions leg (LD-409) ------------------------------------------ #

    def _versions_page(self, file_token, obj_type, page_size, page_token):
        """ONE page of a file's named versions — and the whole of what goes on the wire."""
        params = {"obj_type": obj_type, "page_size": page_size or self._page_size}
        if page_token:
            params["page_token"] = page_token
        return self._call(
            "list_versions",
            path=versions_path(file_token),
            params=params,
            token=file_token,
        )

    def list_versions(self, file_token, obj_type=DOCX_OBJ_TYPE, *, page_size=None,
                      max_pages=DEFAULT_MAX_PAGES) -> VersionListing:
        """Every **named version** of a file, paged to exhaustion. Newest first.

        ``GET /open-apis/drive/v1/files/:file_token/versions``. Paging is never the caller's
        problem: the walk follows ``page_token`` while ``has_more`` is true, exactly like this
        surface's folder listing, and hands back one list. The cursor is echoed **verbatim** and
        never parsed. The page budget (``max_pages``) is the one bound that is not an error —
        hitting it returns a :class:`~larkdocio.drive.models.Truncation` on the result, because
        a budget that fired silently would make the answer lie about the file.

        **A named version is not a revision.** It carries no ``revision_id`` and cannot be
        resolved back to content by any route tried, so it names a moment without being able to
        reproduce it; :class:`~larkdocio.drive.versions.Version` states every absence and its
        consequence.

        **ORDERING IS THIS LIBRARY'S, and the server's order is never promised.** The list is
        sorted here — ``create_time`` descending (newest first), ties broken deterministically
        by token, because two versions created in the same second is a shape the captures
        actually contain. Lark's own order was **observed** descending on one three-row
        listing: enough to use, not enough to rely on, so it is not relied on.

        **EMPTY IS NEVER A DISGUISED DENIAL.** A file that has never been versioned answers
        ``code 0`` with ``{"has_more": false, "items": []}`` → an empty list and no error. A
        malformed request answers ``HTTP 400 / 99992402`` → this surface's typed error carrying
        Lark's **verbatim** code and message. The two are different answers and stay different.

        ``obj_type`` is **required** — Lark refuses its absence (``99992402 field validation
        failed: obj_type is required``), so it is always sent. **Measured accepted:** ``docx``
        and ``sheet``. **Measured refused** (typed locally, before the call, in Lark's own
        words): ``bitable`` (``1068411``) and ``sheets`` (``99992402``). Every other value —
        ``doc`` (legacy), ``mindnote``, ``file``, ``slides``, ``wiki`` — is
        **unmeasured, not refuted**, and is passed through so Lark answers for it, because a
        limit this library never observed is not this library's to assert.
        """
        obj_type = check_obj_type(obj_type)
        found = []
        seen_cursors = set()
        cursor = None
        pages = 0
        truncation = None
        while True:
            response = self._versions_page(file_token, obj_type, page_size, cursor)
            data = response.get("data") or {}
            pages += 1
            found.extend(Version.from_payload(row) for row in (data.get("items") or []))
            next_cursor = data.get("page_token") or data.get("next_page_token") or None
            if not data.get("has_more"):
                break
            if not next_cursor or next_cursor in seen_cursors:
                raise PaginationStalledError(
                    f"Lark reported has_more: true for the versions of {file_token} with "
                    f"{'no page_token' if not next_cursor else 'a repeated page_token'} — the "
                    "listing cannot make progress, so it stopped instead of spinning."
                )
            seen_cursors.add(next_cursor)
            cursor = next_cursor
            if pages >= max_pages:
                truncation = Truncation(
                    cap="max_pages",
                    limit=max_pages,
                    at_folder=str(file_token),
                    at_path=str(file_token),
                    not_visited=("this file's remaining version pages",),
                    detail=("Lark still reported has_more: true; raise max_pages to see the "
                            "rest of this file's versions."),
                )
                break
        return VersionListing(
            file_token=file_token,
            obj_type=obj_type,
            versions=tuple(sorted(found, key=lambda version: version._sort_key())),
            pages=pages,
            truncation=truncation,
        )

    # -- the two non-SDK legs ----------------------------------------------- #

    def root_folder_token(self) -> ApplicationRootToken:
        """The token of the **caller's own** root folder (the legacy ``explorer/v2`` family).

        **This stays public on purpose.** Reading that space is how you inspect it, and this
        operation stays exactly where it was in the ``drive-read`` matrix — same endpoint, same
        credential pair, same permission requirement.

        **And its answer is not a destination.** The value is an
        :class:`~larkdocio.common.destination.ApplicationRootToken` — a ``str`` subclass, so
        every existing string use of it is unchanged — which
        :func:`~larkdocio.common.destination.require_destination` refuses **by type**, locally,
        before any call. Passing it as a ``folder_token`` to a create therefore raises
        :class:`~larkdocio.errors.MissingDestinationError` instead of filing an object where no
        human interface can browse. A raw root token copied in from elsewhere is not this type
        and is not refused; that limit is stated with the guarantee, in
        :mod:`larkdocio.common.destination`.
        """
        response = self._call("root_folder_token", path=ops.ROOT_FOLDER_META_ENDPOINT)
        # Typed even when empty: the type marks provenance, not non-emptiness, so the ``or ""``
        # answer keeps its meaning and is refused by the pre-existing blankness branch.
        return ApplicationRootToken(((response.get("data") or {}).get("token")) or "")

    def folder_name(self, folder_token) -> FolderName:
        """A folder's **own** title — or the disclosed reason there isn't one.

        Degradable by construction, and **the design reason is unchanged by what has since
        been measured**: a refusal (or an empty ``metas`` array) returns a
        :class:`~larkdocio.drive.models.FolderName` with ``name=None`` and a disclosure. The
        folder then renders by its token. A title is never invented.

        **What IS established, on a control pair** (superseding this docstring's earlier
        no-capture reading, false since 2026-08-15). This endpoint **does** resolve a folder
        token, and it discriminates a folder's existence. Every capture path named below is
        **in the source repository**:

        * **positive** —
          ``tests/captures/ld467-create-folder/captures/ld467-25-r2-metadata-of-the-empty-named-folder.json``
          (2026-08-15) is the single-token control: ``code:0`` with a meta keyed to the token,
          ``doc_type: "folder"``, an ``owner_id`` and a real ``url``. Its ``title`` is ``""``
          because that probe's subject was the empty-name folder, so it establishes
          **resolution**, not a title. At scale, a folder-cleanup sweep on 2026-08-19 (its
          recording is not published) re-queried 43 tokens and **4 live folders** answered
          ``resolves: true`` with a non-empty title and an empty ``failed_list``.
        * **negative** —
          ``tests/captures/ld467-create-folder/captures/ld467-13-re-query-a-trashed-folder-token.json``
          (2026-08-15): a trashed folder token answers ``code:0`` with ``metas: []`` and
          ``failed_list: [{code: 970005}]``, replicated by that same sweep's **36 trashed folder
          rows** (2026-08-19).

        So the degrade is not a hedge against an unmeasured route; it is what the **measured
        negative** looks like, and a caller reading a disclosure is reading a real refusal. All
        of it is one tenant, two days; every other tenant, region and token type is
        **unmeasured, not refuted**.
        """
        body = {"request_docs": [{"doc_token": folder_token, "doc_type": "folder"}],
                "with_url": False}
        try:
            response = self._call(
                "folder_name", path=ops.METAS_BATCH_QUERY_ENDPOINT, body=body,
                token=folder_token)
        except Exception as exc:  # noqa: BLE001 - every failure degrades, none propagates
            return FolderName(
                token=folder_token,
                disclosure=(f"the title of {folder_token} could not be read: {exc}"),
            )
        data = response.get("data") or {}
        metas = data.get("metas") or []
        for meta in metas:
            if meta.get("title"):
                return FolderName(token=folder_token, name=meta["title"])
        return FolderName(
            token=folder_token,
            disclosure=(f"Lark returned no title for {folder_token}; the folder is named by "
                        "its token rather than by a title larkdocio would have to invent. "
                        # An empty `metas` on this endpoint is a REFUSAL wearing a code:0, and
                        # the reason is in a sibling key — so the disclosure names the refused
                        # TOKEN rather than leaving a caller to read "no title" as a fact about
                        # the folder (LD-606).
                        f"{failed_reason(data, folder_token)}"),
        )

    def document_security_level(self, document_token, *, doc_type=DOCX_DOC_TYPE
                                ) -> SecurityLevel:
        """A **document's tenant SECURITY LEVEL** — the field a tenant policy can gate editing on.

        **Read this if a person tells you they were stopped from editing.** A tenant can carry
        a tenant security-level policy that requires a **human** to choose a level in the
        Lark client before editing is allowed at all. This call reports what level the document
        carries; it is the same documented ``metas/batch_query`` query POST the folder-title leg
        rides, on READ credentials, and it **changes nothing**.

        **ONE token per call.** The endpoint accepts a list; this leg sends exactly one entry,
        because that is the shape measured and the only shape shipped. ``doc_type`` defaults to
        ``"docx"`` — the one object type this field was measured on — and is passed through for
        any other value so Lark answers for it, rather than this library refusing a type it
        never tried.

        **What the answer means** (:class:`~larkdocio.drive.models.SecurityLevel` carries all
        three cases in the type): a non-empty ``level`` is the level Lark reported, verbatim and
        un-normalised; ``level == ""`` means **NO LEVEL IS SET**; and ``level is None`` with a
        ``disclosure`` means the key was absent or the call could not answer — never a ``""``
        this library invented.

        **Why ``""`` is read as *no level* rather than as *no such field*.** It was measured
        against controls, not inferred: on the fixture whose level a human had just chosen by
        hand the identical call read back ``"Label A"``; that same fixture's own **before control**
        — the identical call, identical token, earlier the same day — read ``""``; and a
        **negative control**, an object with no level ever set, read ``""`` too. Three
        readings, one variable.

        **It is not settable here, or by any route found**
        (:data:`~larkdocio.drive.models.SECURITY_LEVEL_NOT_SETTABLE`), and what stays
        **unmeasured rather than refuted** is carried on the result too
        (:attr:`~larkdocio.drive.models.SecurityLevel.unmeasured`) — read it there; it is
        authored in one place and cited everywhere else.
        """
        body = {"request_docs": [{"doc_token": document_token, "doc_type": doc_type}],
                "with_url": False}
        try:
            response = self._call(
                "document_security_level", path=ops.METAS_BATCH_QUERY_ENDPOINT, body=body,
                token=document_token)
        except Exception as exc:  # noqa: BLE001 - every failure DISCLOSES, none propagates
            return SecurityLevel(
                token=document_token,
                disclosure=(f"the security level of {document_token} could not be read: {exc}. "
                            "That is a disclosure, not a level: nothing here reads it as "
                            "'no level set'."),
            )
        data = response.get("data") or {}
        metas = data.get("metas") or []
        for meta in metas:
            if "sec_label_name" in meta:
                # THE ONE READ of this field in the whole library, and it is written as a
                # LITERAL subscript on purpose: the allow-listed guard over src/ matches the
                # literal shape, so routing it through a constant would evade the very guard
                # that keeps a SECOND reader from appearing unnoticed.
                return SecurityLevel(token=document_token, level=meta["sec_label_name"])
        return SecurityLevel(
            token=document_token,
            disclosure=(
                f"Lark's metadata reply for {document_token} carried no security-level key at "
                f"all ({len(metas)} metadata entr{'y' if len(metas) == 1 else 'ies'} returned), "
                "so this call could not answer. An empty string would have meant 'no level "
                "set', which is a different answer and is not invented here. "
                # Zero entries is the refusal-in-disguise case: the envelope says code:0 and the
                # per-token verdict is in failed_list, so the reason ships with the count
                # (LD-606).
                f"{failed_reason(data, document_token)}"),
        )
