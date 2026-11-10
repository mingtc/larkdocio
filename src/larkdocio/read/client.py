import logging
from pathlib import Path
from typing import Tuple, List, Any, Dict

from lark_oapi.api.drive.v1 import (
    DownloadMediaRequest,
)

from lark_oapi.api.docx.v1 import (
    GetDocumentRequest,
    GetDocumentBlockChildrenRequest,
    ListDocumentBlockRequest,
)
from lark_oapi.api.board.v1 import DownloadAsImageWhiteboardRequest
from lark_oapi.api.wiki.v2 import GetNodeSpaceRequest
from lark_oapi.api.contact.v3 import BatchUserRequest

from larkdocio.common.auth import get_read_credentials, resolved_read_env
from larkdocio.common.sdk_client import build_sdk_client, require_credentials
from larkdocio.errors import LarkAPIError, api_error
from larkdocio.permissions import looks_like_scope_denial
from larkdocio.read.history import (
    EDITION_TO_CONTENT_UNAVAILABLE,
    HISTORICAL_READ_TRAPS,
    check_revision_pin,
    pinned_meta,
)

logger = logging.getLogger("larkdocio")

# The contacts batch endpoint accepts at most 50 user ids per call.
_USER_BATCH_CHUNK = 50

#: Lark's "one or more of these ids is not a valid / existing {open_id}" code. It is a
#: **malformed-input** answer, not a denial: it names no scope, no grant changes it, and its
#: ``error.field_violations[]`` attributes the rejection to individual ids. Live-captured
#: read-only against a bogus id (the contacts bogus-id probe capture in the source repository, and the
#: same body the sheets id check falsifies against, which carries this constant separately for
#: its own transport). Compared representation-agnostically — the wire may hand back an int or
#: a str.
_INVALID_USER_IDS_CODE = 99992351

#: What a document's ``revision_id`` MEANS — stated, not assumed, because a ledger built on a
#: misunderstood anchor mis-syncs invisibly (LD-382 AC3). Every clause here was measured on
#: harness-created disposable documents, never a real one; the capture is
#: ``tests/captures/docx-revision-probe/captures/01-metadata-route.json`` (in the source repository).
DOCUMENT_REVISION_SEMANTICS = (
    "A document's revision_id is comparable to ITSELF ACROSS TIME and to nothing else: it is "
    "per document, and comparing one document's number with another document's — or with a "
    "spreadsheet's revision or a Base table's — means nothing. Measured: it is monotonic and "
    "advances by one per write (2 -> 3 across a single block insert), and a read never moves "
    "it (two back-to-back reads returned the same number), so polling it is inert. It is the "
    "SAME number the full content read reports at the same moment, so the cheap route and the "
    "expensive one cannot disagree. A moved value means SOMETHING in the document changed and "
    "says nothing about WHAT or WHERE; an unmoved value means no write landed between the two "
    "reads, which is as strong as this anchor gets — if you need certainty about content, "
    "compare the content. None means NOT KNOWN — never a revision of zero, and never a "
    "synthesized number."
)

#: The measured refusal for the BULK half (LD-382 AC2(b), the LD-380 negative-claim doctrine):
#: what was tried and what came back. Deliberately NOT referenced from any method body — the
#: permission registry derives a call site's endpoints from its own source, and a probe's
#: enumeration is evidence, not a call this library makes; the paths carry a leading ellipsis
#: for the same reason. The exact wire spellings are in the shipped guide's docx download
#: recipe and, verbatim, in the capture this text is drawn from.
BULK_DOCUMENT_REVISION_UNAVAILABLE = (
    "There is NO BULK docx revision route, measured 2026-08-10 on two harness-created "
    "disposable documents. What was tried: (1) the Drive metas batch form, a POST to "
    "…/drive/v1/metas/ — it ANSWERED (code 0) for two docx tokens and returned create_time, "
    "doc_token, doc_type, latest_modify_time, latest_modify_user, owner_id, "
    "request_doc_info, sec_label_name, title and url, and NOT ONE revision field; (2) GET "
    "…/docx/v1/documents?document_ids=… — HTTP 404; (3) GET …/docx/v1/documents/batch_get — "
    "code 99992402 'field validation failed'; (4) the same path with the batch-query verb — "
    "code 99992402. So N documents cost N metadata calls, one each. Forms beyond those four "
    "are UNMEASURED, not refuted — in particular no POST-shaped docx batch spelling was "
    "tried, because a POST to an unproven docx path risks hitting a creating verb and a probe "
    "never risks a mutation. What the Drive batch form DOES carry is latest_modify_time, a "
    "second-granularity timestamp that did move for the edited document and not for the "
    "untouched one; it is a timestamp, not a revision, and larkdocio does not report it as "
    "one."
)


def _document_revision(document) -> Any:
    """The ONE reading of a docx ``revision_id``: only a real :class:`int` is knowledge.

    A ``bool`` (an ``int`` subclass in Python, but drift rather than a version), a
    digit-string, a float, ``None`` and an absent object all read as ``None`` — *not known*.
    ``0`` passes through as ``0``: rounding an unknown down to a number a real document could
    hold is exactly the failure this rule exists to prevent.
    """
    raw = getattr(document, "revision_id", None)
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None
    return raw


def _invalid_ids_named(resp, asked) -> List[str]:
    """The ids Lark attributed the rejection to, restricted to ids we actually asked about.

    Reads ``error.field_violations[]`` — the per-id attribution — tolerating both the SDK's
    objects and a plain ``dict`` body. Filtering against ``asked`` is the falsification
    discipline the sheets id check already uses: a drifted or echoed value can never make the
    resolver drop an id the caller never named. When the body attributes nothing, nothing is
    claimed — an unproven rejection is disclosed, never invented.
    """
    error = resp.get("error") if isinstance(resp, dict) else getattr(resp, "error", None)
    if isinstance(error, dict):
        violations = error.get("field_violations") or []
    else:
        violations = getattr(error, "field_violations", None) or []
    asked_set = set(asked)
    named: List[str] = []
    for violation in violations:
        value = (violation.get("value") if isinstance(violation, dict)
                 else getattr(violation, "value", None))
        if value in asked_set and value not in named:
            named.append(value)
    return named


def _ensure_success(resp, context: str) -> None:
    """Raise a uniform ``api_error`` when ``resp.success()`` is false.

    Covers the four API calls that share the identical failure shape
    (``download_image``, ``get_docx_content``'s document + block-children fetches,
    ``get_wiki_node_info``). The raised message is byte-identical to the previous
    per-site f-strings — ``context`` supplies the exact clause between ``Failed to``
    and ``: Code:`` (e.g. ``download image {img_token}`` / ``get docx document
    {doc_token}`` / ``get docx blocks`` / ``get wiki node info {token}``) — and the
    ``code``/``msg`` attributes are carried through unchanged. The deliberately
    different board-download raise (log_id/status) and the graceful-degrade
    contacts path are NOT routed through here.
    """
    if not resp.success():
        raise api_error(
            f"Failed to {context}: Code: {resp.code}, Msg: {resp.msg}",
            code=resp.code, msg=resp.msg, body=resp,
            credential_env=resolved_read_env())


def _write_binary(resp, out_path: Path, what: str) -> None:
    """Write a media response's binary payload to ``out_path``.

    Shared file-write tail for ``download_image`` and ``download_board_image``:
    ensure the parent dir exists, guard the ``resp.file is None`` case with the
    byte-identical ``response contained no file content`` message (``what`` is the
    exact ``image {img_token}`` / ``board image {whiteboard_id}`` clause), then
    stream ``resp.file.read()`` to disk. No signature or behavior change.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if resp.file is None:
        raise LarkAPIError(f"Failed to download {what}: response contained no file content")

    with open(out_path, "wb") as f:
        f.write(resp.file.read())


def _mention_resolution_summary(requested_ids, returned_ids, resolved_ids, records=None):
    """The one line a SUCCESSFUL mention lookup logs when it still left mentions unresolved,
    or ``None`` when everything resolved.

    **The invariant is SET-based, not count-based (LD-210 AC6).** It used to take three
    integers, and three integers cannot express a set difference — so the check
    ``requested == returned == named`` was satisfied by answers that had not answered:

    * ask ``[A, B]``, get ``[A, C]`` — two asked, two returned, two named, **summary ``None``**
      while ``B`` is genuinely absent. That is the exact silence class this line exists to
      remove, surviving inside the fix for it;
    * duplicate input ids over-count absence (the parser dedupes, so this was a precondition
      rather than an observation — precisely why it must not be what keeps the invariant true);
    * a record that comes back with no ``open_id`` is not evidence of a contacts-range gap: the
      directory answered, and the record simply cannot be matched to the id that asked for it.

    ``requested_ids`` / ``returned_ids`` / ``resolved_ids`` are id iterables; ``records`` is how
    many user records the response carried, which exceeds ``len(returned_ids)`` exactly when a
    record arrived with no ``open_id``. Those unmatched records are reported as their own
    observation and are **not** counted as absent, because any of the missing ids could be one of
    them — an absence claim there would send a reader to a console setting for a payload problem.

    **Why this function exists.** The lookup had three ways to come back short and two log
    lines. The two loud paths had something to quote — an exception, or Lark's own error code
    — and the two quiet ones had neither: a user returned with every name field empty is
    dropped because there is nothing to substitute, and an id that simply does not come back
    is never seen by the loop at all. Both produced ``{}``, which is also what a zero-item
    response produces, so at every probe the three were **indistinguishable**. That cost about
    five days: the recorded diagnosis was the contacts availability range, and the truth was a
    missing field-level scope — invisible for exactly this reason.

    So the three are separated here, and the separation is the point:

    * **name-less users returned** → a missing **user-base field scope** is the signature.
      Without that grant the directory answers and every name field comes back empty, which
      reads like "no such user" and is not. Deliberately the **class** of scope rather than a
      literal scope string: a literal would rot the moment Lark renames one, and the class is
      what a reader needs in order to act. Where the literal IS authoritative — inside Lark's
      own error body — the permission-denied path already quotes it verbatim.
    * **ids that did not come back** → the app's contacts **data range** (a console setting,
      not an api scope) or an id that is not a user of this tenant. Never the field scope;
      saying "scope" here is the wrong-but-confident diagnosis this whole line exists to stop.
    * **nothing returned at all** → its own clause, because a caller cannot otherwise tell it
      from either of the two above.

    A run that hits both classes reports both, rather than picking one and sending a reader to
    fix half the problem. The line names a class and a **count** — never an id, which would
    make it per-user and chatty as well as noisy in a log.
    """
    requested_set = set(requested_ids)
    returned_set = set(returned_ids)
    resolved_set = set(resolved_ids)
    requested = len(requested_set)
    returned = len(returned_set)

    # THE SET DIFFERENCES. ``unnamed`` came back and could not be used; ``missing`` never came
    # back under an id we asked about. Their union is ``requested_set - resolved_set`` plus any
    # id the answer volunteered without being asked, which is why counting could not see P1.
    unnamed = len(returned_set - resolved_set)
    missing = requested_set - returned_set
    records = returned if records is None else max(records, 0)
    # Records the answer carried that no id can be attributed to (no ``open_id`` at all).
    unmatched = max(records - returned, 0)
    # An unmatched record could BE one of the missing ids, so only the excess is absence.
    absent = max(len(missing) - unmatched, 0)

    if not unnamed and not absent and not unmatched:
        return None

    observations = []
    causes = []

    if records == 0:
        observations.append(
            f"the directory answered, and returned no user at all for the {requested} "
            f"id(s) asked about"
        )
    else:
        if unnamed:
            observations.append(
                f"{unnamed} of the {returned} users returned carried no readable display "
                f"name (every name field empty)"
            )
        if unmatched:
            observations.append(
                f"{unmatched} record(s) came back carrying no open_id, so they cannot be "
                f"matched to the id(s) that asked for them"
            )
        if absent:
            observations.append(
                f"{absent} of the {requested} id(s) asked about did not come back at all"
            )

    if unnamed or unmatched:
        causes.append(
            "A user returned without a readable name is the signature of a missing "
            "user-base field scope — the field-level contacts grant is what makes the name "
            "fields readable — rather than of a user who does not exist, because without "
            "that grant the call succeeds and every name field answers empty. A record with "
            "no open_id is the same field-level shape and not an absent user."
        )
    if absent or records == 0:
        causes.append(
            "An id that does not come back is outside the app's contacts data range, or "
            "belongs to no user of this tenant; the range is a console setting rather than "
            "an api scope."
        )

    return (
        "@mention name resolution fell short: "
        + "; ".join(observations)
        + ". "
        + " ".join(causes)
        + " Those mentions read as their raw @open_id."
    )


class Client:
    """The docx reader's client — and the home of the **reverse** name direction.

    ``batch_get_user_names(ids)`` turns ``open_id``s a caller already holds into display names
    (``{"ou_…": "Example User"}``); its inverse, name → id, is
    :func:`larkdocio.contacts.resolve_user`. The two live on different surfaces, so this class
    is re-exported from :mod:`larkdocio.contacts` as ``ReadClient`` — one import away from the
    direction a reader was already looking for.
    """

    @classmethod
    def from_read_credentials(cls, domain: str = "larksuite.com") -> "Client":
        """Build from the environment's READ credentials, like every other read client here.

        A document read — and the directory lookup that resolves its @mentions — is a read, so
        the write credential pair is **never** consulted; a write-only environment is a refusal
        rather than a promotion. The other read clients this repository ships — the contacts
        search client and the comments read client — carry the identically-named constructor
        and resolve the same pair; this one was the odd one out. **It is not named by dotted
        path here on purpose:** the reader's package must not reference those surfaces even in
        prose, so that the dependency arrow stays one-way and greppable
        (``tests/test_comments_surface_truth.py``).
        """
        app_id, app_secret = get_read_credentials()
        require_credentials(
            app_id, app_secret,
            "Cannot read: no read credentials in the environment (the "
            f"{'/'.join(resolved_read_env())} pair). The write pair is never borrowed for "
            "a read.")
        return cls(app_id, app_secret, domain)

    def __init__(self, app_id: str, app_secret: str, domain: str):
        # The one shared builder chain (it prefixes "https://open." itself). This client keeps
        # its own constructor shape deliberately: positional, no injectable-client seam, and
        # NO rate limiter — it is the determinism-guaranteed read path, and giving it a pace it
        # never had would be a behaviour change. The attribute is public because stubs and
        # tests assign to it by name.
        self.lark_client = build_sdk_client(app_id, app_secret, domain, timeout=30)
            
    def download_image(self, img_token: str, out_dir: str) -> str:
        """Download the image ``img_token`` into ``out_dir`` and return its file path.

        The name is the token plus the extension the response reports (``.png`` when it
        reports none), so two documents sharing an image write one file.
        """
        req = DownloadMediaRequest.builder() \
            .file_token(img_token) \
            .build()
            
        resp = self.lark_client.drive.v1.media.download(req)
        _ensure_success(resp, f"download image {img_token}")

        # The Python SDK resp.file gives us a byte array or stream.
        # It also usually provides a filename in the headers, but we can fallback to token if not.
        filename = resp.file_name if hasattr(resp, "file_name") and resp.file_name else f"{img_token}.png"
        file_ext = Path(filename).suffix if Path(filename).suffix else ".png"

        out_path = Path(out_dir) / f"{img_token}{file_ext}"
        _write_binary(resp, out_path, f"image {img_token}")

        return str(out_path)

    def download_board_image(self, whiteboard_id: str, out_dir: str) -> str:
        """Render the whiteboard ``whiteboard_id`` to a PNG in ``out_dir``; return its path.

        A board has no text form, so this export is the only way it reaches Markdown. A
        permission failure raises with the request's log id attached, because Lark answers
        this endpoint with an empty ``code``/``msg`` when the app lacks board scope.
        """
        req = DownloadAsImageWhiteboardRequest.builder() \
            .whiteboard_id(whiteboard_id) \
            .build()

        resp = self.lark_client.board.v1.whiteboard.download_as_image(req)
        if not resp.success():
            # Board permission failures often return code/msg=None; surface the
            # request log id and HTTP status so the error is actionable.
            log_id = resp.get_log_id() if hasattr(resp, "get_log_id") else None
            status = getattr(getattr(resp, "raw", None), "status_code", None)
            raise api_error(
                f"Failed to download board image {whiteboard_id}: "
                f"Code: {resp.code}, Msg: {resp.msg}, "
                f"HTTP: {status}, LogID: {log_id}",
                code=resp.code, msg=resp.msg, body=resp,
                credential_env=resolved_read_env())
            
        filename = f"{whiteboard_id}.png"
        out_path = Path(out_dir) / filename
        _write_binary(resp, out_path, f"board image {whiteboard_id}")

        return str(out_path)


    def get_docx_content(self, doc_token: str,
                         document_revision_id=None) -> Tuple[Any, List[Any]]:
        """Read a document whole: returns ``(Document, [Block])`` — or a PAST revision of it.

        The first element is the document's own metadata object — its ``title`` and its
        ``revision_id``; the second is **every** block in it, flat and in document order,
        paged through with descendants included (a 500-block page size, so a large document
        costs several calls and one return).

        Hand ``revision_id`` to a write plan (``dry_run(..., document_revision_id=…)``) and it
        becomes the whole-document compare-and-swap: if the document moves between this read
        and the write, the batch refuses ``STALE_DOCUMENT`` and writes nothing. That is the
        one field connecting a read to a safe write, which is why it is named here.

        **``document_revision_id=<n>`` reads the document AS OF revision n.** Omit it (or pass
        ``None``) and everything above is exactly what happens — same two routes, same calls,
        same bytes; the parameter changes nothing for a caller who does not use it. Pass a
        positive integer and the read goes down a **different, deliberately chosen route**:
        the flat blocks list (``GET …/docx/v1/documents/{id}/blocks``), which is the ONE route
        measured to honour the pin — at ``document_revision_id=2`` it returned a document's
        2-block earlier body while ``-1`` returned its 3-block head in the same instant, and a
        4-revision document walked rung by rung reproduced its edit history exactly. The
        children route this method uses at head *models* the parameter and was never measured
        honouring it, and *being modelled is not being honoured*: two neighbouring routes are
        measured accepting it and discarding it. So the historical read rides the measured
        route, and a pinned read returns a
        :class:`~larkdocio.read.history.HistoricalDocumentMeta` in place of the ``Document``,
        because the metadata route cannot answer for a past revision (below).

        A pin of ``0`` or below, or anything that is not an ``int``, is refused **locally**
        before a call is spent, in Lark's own words
        (:func:`~larkdocio.read.history.check_revision_pin`); ``-1`` is Lark's head sentinel
        and is refused by naming the spelling that works here, which is ``None``.

        **THE THREE MEASURED TRAPS AROUND THIS PARAMETER:**

        <<HISTORICAL_READ_TRAPS>>

        **And what a caller usually asks for next — "read the edition someone named V1.3" —
        is a measured refusal:**

        <<EDITION_TO_CONTENT_UNAVAILABLE>>
        """
        if document_revision_id is not None:
            return self._get_docx_content_at_revision(
                doc_token, check_revision_pin(document_revision_id))

        req = GetDocumentRequest.builder() \
            .document_id(doc_token) \
            .build()

        resp = self.lark_client.docx.v1.document.get(req)
        _ensure_success(resp, f"get docx document {doc_token}")

        docx = resp.data.document

        blocks = []
        page_token = ""
        while True:
            list_req = GetDocumentBlockChildrenRequest.builder() \
                .document_id(doc_token) \
                .block_id(doc_token) \
                .page_size(500) \
                .with_descendants(True)
            if page_token:
                list_req.page_token(page_token)
            list_req = list_req.build()
                
            block_resp = self.lark_client.docx.v1.document_block_children.get(list_req)
            _ensure_success(block_resp, "get docx blocks")

            blocks.extend(block_resp.data.items or [])
            
            page_token = block_resp.data.page_token
            if not block_resp.data.has_more:
                break

        return docx, blocks

    def _get_docx_content_at_revision(self, doc_token: str,
                                      document_revision_id: int) -> Tuple[Any, List[Any]]:
        """The pinned half of :meth:`get_docx_content` — the MEASURED route, and only it.

        ``GET …/docx/v1/documents/{id}/blocks?document_revision_id=<n>``, paged to
        exhaustion with the pin on **every** page (a page-2 request without it would come from
        head, which is the quiet way a historical read stops being one — a pinned read pages
        normally, ``has_more``/``page_token`` honoured, capture ``209-``).

        **No metadata call is made.** The meta route accepts the pin and answers head
        (:data:`~larkdocio.read.history.DOCUMENT_META_IGNORES_THE_PIN`), so calling it would
        buy one round trip and a number that then has to be fenced. The metadata half is
        :class:`~larkdocio.read.history.HistoricalDocumentMeta`, built from what was asked.
        """
        blocks = []
        page_token = ""
        while True:
            list_req = ListDocumentBlockRequest.builder() \
                .document_id(doc_token) \
                .page_size(500) \
                .document_revision_id(document_revision_id)
            if page_token:
                list_req.page_token(page_token)
            list_req = list_req.build()

            block_resp = self.lark_client.docx.v1.document_block.list(list_req)
            _ensure_success(
                block_resp, f"get docx blocks at revision {document_revision_id}")

            blocks.extend(block_resp.data.items or [])

            page_token = block_resp.data.page_token
            if not block_resp.data.has_more:
                break

        return pinned_meta(doc_token, document_revision_id), blocks

    def read_document_revision(self, doc_token: str):
        """``GET …/docx/v1/documents/{document_id}`` → ``revision_id``, or ``None``.

        **The cheap change-detection anchor: one metadata call, no block tree.** It is the
        first half of what :meth:`get_docx_content` already does — the meta reply carries
        ``document_id`` / ``title`` / ``display_setting`` / ``revision_id`` and no content — so
        a ledger asking *"did this document move since I last saw it?"* stops paying for the
        whole document in order to decide whether to download it. It costs **one** call
        (``0.119 s`` / ``0.242 s`` across two disposable runs) against the content read's meta
        call **plus one block page per 500 blocks**, so the saving grows with the document. It
        is made on the **READ** pair and the reader's own scope — this endpoint family is the
        one :meth:`get_docx_content` already opens, so nothing new is required and **no scope
        moved**.

        It reports the **same** number the full content read reports at the same moment
        (measured before and after an edit), which is what makes it safe to substitute for
        one. What the number means — and what a moved or unmoved value does and does not imply
        — is :data:`DOCUMENT_REVISION_SEMANTICS`, stated there rather than assumed here.

        **There is no bulk form**: N documents cost N calls. What was tried and what came back
        is enumerated in :data:`BULK_DOCUMENT_REVISION_UNAVAILABLE` rather than left as a bare
        *"not possible"*.

        ``None`` means **not known** — never a revision of zero, never a synthesized number
        (:func:`_document_revision`). A refused or failed read raises the same typed taxonomy
        every other read op here raises; it is not laundered into *"unchanged"*.
        """
        req = GetDocumentRequest.builder() \
            .document_id(doc_token) \
            .build()

        resp = self.lark_client.docx.v1.document.get(req)
        _ensure_success(resp, f"get docx document meta {doc_token}")

        return _document_revision(getattr(resp.data, "document", None))

    def batch_get_user_names(self, ids: List[str]) -> Dict[str, str]:
        """Resolve open_ids → display names via ``contact.v3.user.batch``.

        Best-effort, GRACEFUL DEGRADE (the ``download_image`` warn-and-continue
        precedent): the download must NEVER fail because of mention resolution.

        * Chunked ≤50 ids/call (SDK limit), ``user_id_type="open_id"``.
        * Name preference per user: ``.name`` → ``.en_name`` → ``.nickname``; a
          user with none usable is omitted (nothing to substitute) — and that
          omission is now **DISCLOSED** rather than silent. Once per run, a
          successful call that left mentions unresolved logs one info line saying
          **which way** it fell short: users returned with no readable name at all
          (the signature of a missing user-base **field** scope, since without that
          grant the call succeeds and every name field answers empty), ids that did
          not come back (the app's contacts data range, or not a user of this
          tenant), or nothing returned at all. See :func:`_mention_resolution_summary`
          for why those three had to become distinguishable.
        * On a permission / missing-scope error (or any exception), log **ONE**
          info line carrying Lark's error body — the scope string an administrator must
          grant — then **negative-cache the whole run**: stop issuing further
          chunk calls and return whatever resolved so far. A partial result (an
          earlier chunk succeeded) rewrites only the resolved ids. These paths return
          early and therefore emit no summary: one failure must not read as two.
        * A **rejected id is not a denial.** Lark answers a malformed or nonexistent
          ``open_id`` with its own code, naming the offending ids one by one in the
          body — no scope is named and no grant changes it. That family logs that the
          call was **not** denied, names the ids Lark rejected, drops **only** those and
          re-asks for the rest of the chunk, and lets the run continue: one bad id must
          not discard the valid names asked for alongside it. The rejected ids are then
          excluded from the shortfall summary, which explains a different thing (the
          contacts data range) and would otherwise blame it for a rejection that already
          has its answer. Any other non-success code is reported verbatim with **no**
          prescription — advice that cannot help is worse than none.

        Returns a ``{open_id: display_name}`` dict (empty when unresolved). The
        per-run cache is this single dict — the parser already deduped the ids, so
        the same doc yields the same id set ⇒ the same names ⇒ byte-identical
        output within a run.
        """
        resolved: Dict[str, str] = {}
        if not ids:
            return resolved

        #: Accumulated across ALL chunks so the disclosure is once per RUN, not per chunk and
        #: never per user — a document with many mentions must not make this chatty. The ids
        #: are kept as a SET rather than a count, because the invariant is a set difference
        #: (LD-210 AC6): counting cannot tell "the id I asked about came back" from "some id
        #: came back". ``records`` is the raw item count, which is how a record arriving with
        #: no ``open_id`` stays distinguishable from an id that never came back at all.
        returned_ids: set = set()
        records = 0
        #: Ids Lark itself rejected, per-id. They are subtracted from the summary's requested
        #: set: the rejection line already explained them, and the summary's other explanation
        #: (the contacts data range) would be the wrong-but-confident diagnosis for them.
        rejected_ids: set = set()

        for start in range(0, len(ids), _USER_BATCH_CHUNK):
            chunk = ids[start:start + _USER_BATCH_CHUNK]
            items, halt, rejected = self._resolve_chunk(chunk)
            rejected_ids.update(rejected)

            records += len(items)
            for user in items:
                open_id = getattr(user, "open_id", None)
                if not open_id:
                    continue
                returned_ids.add(open_id)
                name = (
                    getattr(user, "name", None)
                    or getattr(user, "en_name", None)
                    or getattr(user, "nickname", None)
                )
                if name:
                    resolved[open_id] = name

            if halt:
                # A denial or a transport failure: negative-cache the run. Those paths have
                # already logged the line that names the cause and must not gain a summary on
                # top — one failure must not read as two.
                return resolved

        # Every chunk was answered, and resolution may still have fallen short. ONE line, after
        # the loop, so the count is the run's — and none at all on the common path.
        summary = _mention_resolution_summary(
            [i for i in ids if i not in rejected_ids], returned_ids, resolved, records)
        if summary:
            logger.info(summary)

        return resolved

    def _resolve_chunk(self, chunk: List[str]):
        """One chunk of ≤50 ids → ``(items, halt, rejected)``.

        Where the failure taxonomy lives, because the three families need three different
        answers and the old single ``not resp.success()`` branch gave them one:

        * **a scope denial** (classified by :func:`looks_like_scope_denial`, which reads the
          code *and* the message shape, so an uncaptured denial code still classifies) — keeps
          the grant advice, and ``halt`` stops the run: a scope the app does not hold will not
          be held by the next chunk either;
        * **rejected ids** — Lark's malformed/nonexistent-id answer, attributed per id in the
          body. The ids it names are dropped and the rest of the chunk is re-asked **once**, so
          a single bad id costs its own name and nothing else. Not a halt: the rest of the run
          is unaffected by an id shape. When the code says so but the body attributes nothing,
          nothing is dropped and nothing is claimed — the chunk is skipped, still without
          halting;
        * **anything else** — Lark's code and message verbatim, no prescription. It halts,
          because an unclassified failure repeating per chunk is the shape of a transport or
          rate problem and hammering it helps nobody.

        A transport exception keeps its existing whole-run degrade: the download must never
        fail because of mention resolution.
        """
        asked = list(chunk)
        rejected: List[str] = []

        while asked:
            try:
                req = BatchUserRequest.builder() \
                    .user_ids(asked) \
                    .user_id_type("open_id") \
                    .build()
                resp = self.lark_client.contact.v3.user.batch(req)
            except Exception as e:
                # Any transport/SDK failure degrades the whole run (best-effort).
                logger.info(
                    f"@mention name resolution unavailable ({e}); "
                    f"falling back to raw @open_id for this download."
                )
                return [], True, rejected

            if resp.success():
                items = getattr(getattr(resp, "data", None), "items", None) or []
                return list(items), False, rejected

            if looks_like_scope_denial(resp.code, resp.msg):
                # Missing-scope / permission error. Surface Lark's exact code+msg so the
                # required scope can be read from the error body, then negative-cache: do not
                # retry remaining chunks this run.
                logger.info(
                    f"@mention name resolution denied (Code: {resp.code}, "
                    f"Msg: {resp.msg}); falling back to raw @open_id for this "
                    f"download. Grant the scope named in the message to enable it."
                )
                return [], True, rejected

            named = _invalid_ids_named(resp, asked) if not rejected else []
            if named:
                rejected = named
                remaining = [i for i in asked if i not in set(named)]
                logger.info(
                    f"@mention name resolution rejected {len(named)} of the {len(asked)} "
                    f"id(s) asked about as not a valid or existing open_id (Code: "
                    f"{resp.code}, Msg: {resp.msg}). The call was NOT denied — the id shape "
                    f"is what was rejected, so no permission change affects it. Rejected: "
                    f"{', '.join(named)}. Re-asking for the remaining {len(remaining)} "
                    f"id(s); the rejected ones read as their raw @open_id."
                )
                asked = remaining
                continue

            if str(resp.code) == str(_INVALID_USER_IDS_CODE):
                # The rejected-id family without per-id attribution: positive proof only, so
                # no id is dropped and none is named. The chunk is skipped rather than
                # halting the run — an id shape says nothing about the next chunk.
                logger.info(
                    f"@mention name resolution rejected one or more of the {len(asked)} "
                    f"id(s) asked about as not a valid or existing open_id (Code: "
                    f"{resp.code}, Msg: {resp.msg}). The call was NOT denied and no "
                    f"permission change affects it; the answer attributed the rejection to "
                    f"no individual id, so none is claimed here. Those mentions read as "
                    f"their raw @open_id."
                )
                return [], False, rejected

            logger.info(
                f"@mention name resolution failed (Code: {resp.code}, Msg: {resp.msg}); "
                f"falling back to raw @open_id for this download. The call was neither "
                f"denied nor answered, so there is no action to prescribe beyond the code "
                f"and message above."
            )
            return [], True, rejected

        # Every id in the chunk was rejected: nothing left to ask about, and asking the
        # endpoint with an empty list would be a call that cannot answer anything.
        return [], False, rejected

    def get_wiki_node_info(self, token: str) -> Any:
        """Resolve a wiki node ``token`` to its node object (the ``obj_token`` + ``obj_type``).

        A wiki URL addresses a node, not a document; the node names the real ``docx`` token
        underneath it, which is what every other read call takes.
        """
        req = GetNodeSpaceRequest.builder() \
            .token(token) \
            .build()
            
        resp = self.lark_client.wiki.v2.space.get_node(req)
        _ensure_success(resp, f"get wiki node info {token}")

        return resp.data.node


# The three traps and the measured refusal are authored ONCE in ``larkdocio.read.history`` and
# quoted here verbatim (a docstring must be a literal, so the quotation is spliced in after the
# class rather than built inline) — the same pattern ``larkdocio.common.doc_link`` uses for the
# block-anchor measurement. A caller reading ``help(Client.get_docx_content)`` meets exactly the
# text the guide carries, because it IS that text.
Client.get_docx_content.__doc__ = (
    (Client.get_docx_content.__doc__ or "")
    .replace("<<HISTORICAL_READ_TRAPS>>", HISTORICAL_READ_TRAPS)
    .replace("<<EDITION_TO_CONTENT_UNAVAILABLE>>", EDITION_TO_CONTENT_UNAVAILABLE)
)

