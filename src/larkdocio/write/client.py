"""larkdocio.write.client — the write-side docx v1 client (LD-064).

The write client the W0 self-provisioning harness rides. It is built **on the S2
shared core** (``larkdocio.common``): tenant-token auth via
:func:`~larkdocio.common.transport.fetch_tenant_access_token`, and every write
routed through :class:`~larkdocio.common.transport.WriteTransport` so writes are
**throttled to ≤3/sec** and back off on Lark's ``99991400`` rate-limit code. It is
**born typed** — a non-zero Lark ``code`` raises the S1 taxonomy
(:class:`~larkdocio.errors.LarkAPIError` / :class:`LarkRateLimitError`) via
:func:`~larkdocio.common.transport.raise_for_lark_code`.

The write path is **raw ``urllib``** (the write feasibility spike's
write path): the endpoint surface is the docx v1
block API — create a document, create children, patch one block (``update_text_elements``),
delete a child range — plus a Drive file-delete for teardown. The read SDK client
in ``read/`` is untouched (the shared core's design note: SDK-for-reads,
stdlib-for-writes).

Style fidelity: :func:`to_write_elements` rebuilds a block's runs **element by
element**, preserving each run's clean style — bold / italic / inline_code /
strikethrough / underline / text_color / background_color / link — so a patch never
round-trips through lossy Markdown (spike Appendix — the pattern W1's element-level
patching must follow).

**Inline comment anchors ride with their run.** Each rebuilt run re-emits the
``comment_ids`` its source run carried, so a patch body states a reviewer's anchor
instead of omitting it. The three paths built on the rebuild differ: a sub-span edit's
replacement run takes its region's anchors (and a span whose runs disagree about their
anchors is refused rather than guessed), while a whole-paragraph edit — which collapses
the block to one run — is refused at plan time when the block carries inline comment
anchors, with the sub-span edit named as the way through. A whole-cell (table) edit
collapses the cell's inner text block the same way and is refused when *that* block carries
inline comment anchors, pointing at a sub-span edit anchored by the inner block's id.

No anchor resolution lives here — that is W1. The harness patches a block it
created and whose id it already holds.
"""
import urllib.request
from typing import Optional

from larkdocio.common.auth import WRITE_ENV
from larkdocio.common.destination import require_destination
from larkdocio.common.transport import (
    CredentialedRawHttpClient,
    WriteTransport,
    api_base,
    fetch_tenant_access_token,
    raise_for_lark_code,
)
from larkdocio.errors import FencedPrimitiveError, LarkPaginationError

# Per-run style keys that survive the read→write rebuild. Boolean flags are
# emitted only when truthy; color/link keys are copied verbatim when present.
_STYLE_FLAGS = ("bold", "italic", "inline_code", "strikethrough", "underline")

#: The one non-style key the read ``text_element_style`` object also carries: the run's
#: **review anchors**. Deliberately NOT part of :func:`_clean_style`'s closed key set —
#: an anchor is not styling, and treating it as a style key is exactly the conflation that
#: made the field invisible to the reducer in the first place. It is emitted by
#: :func:`to_write_elements` alongside the cleaned style; see :func:`_carried_comment_ids`.
_COMMENT_IDS_KEY = "comment_ids"


def _clean_style(style):
    """Reduce a read ``text_element_style`` to the minimal write-side **style** dict.

    Emits only truthy boolean flags plus any ``text_color`` / ``background_color``
    / ``link`` present, or ``None`` when nothing carries over. Mirrors the spike
    Appendix ``clean_style``.

    Its key set is **closed to styling** on purpose. The read object it reduces also
    carries the run's review anchors, which are not styling and are emitted separately by
    :func:`to_write_elements` (:func:`_carried_comment_ids`) — so "what does the rebuild
    keep of a run's *style*" stays one question with one answer.
    """
    if not style:
        return None
    out = {k: True for k in _STYLE_FLAGS if style.get(k)}
    for k in ("text_color", "background_color"):
        if style.get(k) is not None:
            out[k] = style[k]
    if style.get("link"):
        out["link"] = style["link"]
    return out or None


def _carried_comment_ids(style):
    """The run's inline review anchors to re-emit, or ``None`` when it has none.

    A **copy** of the read list, in the API's own sequence — no sorting, no de-duplication
    (the ids are the API's data, not ours to normalize; the same rule the model applies on
    the way in), and no aliasing of the caller's payload. An **absent** field and a
    **present-but-empty** list both yield ``None``: neither carries an anchor, and emitting
    an empty key would put a statement about nothing on the wire.
    """
    if not style:
        return None
    ids = style.get(_COMMENT_IDS_KEY)
    if not ids:
        return None
    return list(ids)


def to_write_elements(read_elements, mutate=None):
    """Rebuild read ``elements`` into write ``elements``, preserving per-run style.

    THE style-preserving rebuild (spike Appendix). Each ``text_run`` becomes a
    clean write run — its ``content`` optionally transformed by ``mutate`` (a
    ``str -> str`` callable), its style reduced via :func:`_clean_style`. Non-text
    elements (mentions, equations, …) are passed through with their ``None``-valued
    keys dropped (the shape the write API accepts).

    **What carries over** is exactly :func:`_clean_style`'s closed key set: bold /
    italic / inline_code / strikethrough / underline / text_color / background_color /
    link. There is no lossy Markdown round-trip, so none of those is degraded.

    **Inline comment anchors ride with the run they belong to.** Each rebuilt
    ``text_run`` re-emits the ``comment_ids`` its source run carried, in the API's own
    order, so a reviewer's anchor stays on the text it was anchored to instead of being
    left out of the patch body. The three edit paths built on this rebuild differ, and
    deliberately: a **sub-span** edit splits at the span boundaries and the run that
    replaces the span takes its region's anchors (a span whose runs disagree about their
    anchors is **refused** — ``span-not-splittable`` — rather than guessing which passage
    a reviewer meant), while a **whole-paragraph** edit collapses the block to one run,
    where per-passage anchors have nowhere to attach: that path **refuses** at plan time
    (``comment-anchors-present``) and names the sub-span edit as the way through, and this
    rebuild's collapsed run therefore carries no anchor of any other run
    (:func:`~larkdocio.write.apply.build_whole_paragraph_update`). A **whole-cell** (table)
    edit rides that same collapse and **refuses** the same way, on the inline comment
    anchors of the cell's inner text block — the one block it rewrites. Because a
    row-key-and-column locator cannot name a span, that refusal's ``detail`` names the
    sub-span edit anchored by the inner block's id.

    What Lark then does with the anchors it accepts is the server's own affair; what this
    function guarantees is the **payload**.
    """
    out = []
    for e in read_elements or []:
        tr = e.get("text_run")
        if tr is not None:
            content = tr.get("content", "")
            run = {"content": mutate(content) if mutate else content}
            style = tr.get("text_element_style")
            cs = _clean_style(style)
            ids = _carried_comment_ids(style)
            if cs or ids:
                run["text_element_style"] = cs or {}
                if ids:
                    run["text_element_style"][_COMMENT_IDS_KEY] = ids
            out.append({"text_run": run})
        else:
            out.append({k: v for k, v in e.items() if v is not None and k != "text_run"})
    return out


def text_block(content, style=None):
    """A minimal docx v1 **text** block (type 2) carrying one styled run.

    A convenience for populating a harness baseline; ``style`` is a write-side
    ``text_element_style`` dict (or ``None`` for a plain run).
    """
    run = {"content": content}
    if style:
        run["text_element_style"] = style
    return {"block_type": 2, "text": {"elements": [{"text_run": run}]}}


#: The docx-v1 "latest revision" query pinned on every block read/write (§ Decision (e)
#: — docx writes are NOT compare-and-swap; ``-1`` means "against latest"). One literal so
#: an endpoint-version or revision-pin change is a one-line edit, not a 4-site sweep.
_REVISION_Q = "document_revision_id=-1"


#: The most block updates one ``batch_update`` call may carry — **a MEASURED envelope, and
#: deliberately not an inferred one** (LD-481). ``PATCH …/blocks/batch_update`` was probed on a
#: disposable the spike created and trashed and answered ``code 0`` at **48**, 40 and 3 updates
#: in one call, with all 48 read back (the 2026-08-14 table-cell-creation spike, § 3c; its
#: write-up was retired on 2026-09-18). Larger batches are
#: **unmeasured, not refuted** — the number here is the largest one an actual capture supports,
#: so the fill's arithmetic is anchored on evidence rather than on a round number. **Route
#: scope:** one tenant, ``tenant_access_token``, docx v1, on documents the probe created (not
#: wiki-wrapped).
MAX_BATCH_UPDATES_PER_CALL = 48

#: The most blocks one ``descendant`` call may carry — **a MEASURED Lark ceiling, bisected**
#: (LD-482, on the LD-481 spike's own evidence). It is a count of **descendants**, not of bytes
#: and not of cells: the same spike's § 3b (retired on 2026-09-18)
#: created a 1×499 text table = **999 descendants** ``code 0`` and read it back ``row_size 499``,
#: while 1×500 = **1001 descendants** answered ``99992402 field validation failed`` with
#: **nothing created**, and 6×83 = 997 passed where 6×84 = 1009 failed — two shapes, the same
#: cut. A third shape failed at the same count for a *different* reason (1000 descendants of
#: childless type-32 cells answer ``1770041 open schema mismatch``), which is why this number
#: is the ceiling on the count and the cell shape is enforced separately.
#: **Route scope:** one tenant, ``tenant_access_token``, docx v1, block type 31, on
#: documents the spike created (not wiki-wrapped). ``user_access_token``, other tenants and
#: wiki-wrapped documents are **unmeasured, not refuted**.
MAX_DESCENDANTS_PER_CALL = 1000

#: The page size the document block list asks for — the same 500 the read path has always
#: used (``read/client.py``), so both walks of the same endpoint page identically.
BLOCK_LIST_PAGE_SIZE = 500

#: Hard stop on a single :meth:`WriteClient.list_document_blocks` walk. The ordinary guard
#: below — a cursor the walk has already used — ends a pathological walk long before this;
#: this is the backstop for a server handing back an endless chain of FRESH cursors, which no
#: cursor-equality check can catch.
#:
#: **Why 200, and not a number invented here.** It is the SIBLING PRECEDENT: ``base/client.py``
#: and ``comments/client.py`` each cap a cursor walk at 200 pages, independently, and both say
#: it is a backstop rather than an expected limit. Adopting their number keeps one answer to
#: "how long may a walk run" across the library instead of three. It is also far outside any
#: real document at this page size: 200 × :data:`BLOCK_LIST_PAGE_SIZE` is 100 000 blocks, and
#: the largest document this repository has ever read is three orders of magnitude smaller —
#: so the cap cannot be reached by an ordinary document, which is the property that lets it be
#: an ERROR rather than a truncation.
#:
#: **And here it refuses where the siblings truncate**, deliberately. Those two walks return
#: what they collected: their callers are reading, and a short read is a result the caller can
#: inspect (base publishes the page bodies as its own completeness proof). This list is not a
#: result — it is how :func:`~larkdocio.write.apply._provisioned_cell_ids` learns WHICH BLOCKS
#: TO WRITE TO. A short list here does not produce a short answer; it produces writes aimed at
#: a subset of a table, silently. So the walk raises.
MAX_BLOCK_LIST_PAGES = 200


#: ``(create, delete)`` — the file-lifecycle calls on this client, named beside the methods
#: themselves so the discovery registry (``larkdocio.capabilities()``) can PROJECT them
#: instead of keeping a second hand-maintained list. These two shipped well documented and
#: were reported by no discovery surface at all, so a caller working against a disposable
#: document could find them only with `dir()`. A name here that is not a method on the class
#: fails at projection time.
LIFECYCLE_OPS = ("create_document", "delete_document")


#: **What the docx create's own answer does NOT carry: a url.** Authored once, here, and met
#: three ways — in :meth:`WriteClient.create_document`'s docstring, restated on the returned
#: value itself as :attr:`CreatedDocument.no_url_reason`, and inside the ``AttributeError`` a
#: caller gets for asking. LD-572 established the fact and the paved road; LD-583 moved it onto
#: the value without touching the reason.
DOCX_REPLY_CARRIES_NO_URL = (
    "the docx v1 create reply hands back document_id, revision_id and title, and nothing that "
    "names a web address — and this library never assembles one from a host and a token, "
    "because a constructed link is a guess wearing the shape of an answer (the same reason "
    "DriveFilesWriteClient.permalink states for a file). So this value has no `url` attribute "
    "at all, which is a different fact from a `url` that is None: None is what a reply that "
    "CARRIED the key and left it empty means (drive.CreatedFolder.url). The paved road is to "
    "list the parent folder afterward and read the new document back off it — the listing's "
    "per-child `url` (FolderChild.url) is Lark's own answer. See `larkdocio.guide()`, "
    "section \"Recipe: read every document in a folder\"."
)


class CreatedDocument(dict):
    """One docx document created in a folder: **what Lark answered, and where it was put.**

    **It IS the reply's own ``data.document`` dict** — a ``dict`` subclass whose body is that
    payload unchanged, so ``created["document_id"]``, ``.get``, ``in``, iteration,
    ``len``, ``.keys()/.values()/.items()``, ``json.dumps``, ``dict(created)``, ``{**created}``
    and ``==`` against the plain dict all answer exactly what they answered when this method
    returned a bare dict. Nothing that already worked changes; the one thing that does is
    ``type(created) is dict``, which is now ``False`` (``isinstance`` answers ``True``).

    :attr:`document_id`, :attr:`title` and :attr:`revision_id` are **views onto that same
    body**, not a second copy, so an attribute cannot drift from its key. ``document_id`` is
    also the **root Page block's id**.

    ``folder_token`` is what the caller asked for, echoed so a ledger row is complete without a
    second call — and carried **outside** the dict body on purpose: adding a key the reply never
    sent would have broken equality against the plain dict.

    **There is no ``url`` here, and there will not be one** —
    :data:`DOCX_REPLY_CARRIES_NO_URL`, restated on this value as :attr:`no_url_reason` so a
    caller reading a returned object — not the module — still meets it.
    """

    __slots__ = ("folder_token",)

    #: Restated on the value itself, readable without provoking an exception.
    no_url_reason = DOCX_REPLY_CARRIES_NO_URL

    def __init__(self, document, *, folder_token):
        super().__init__(document or {})
        object.__setattr__(self, "folder_token", folder_token)

    @property
    def document_id(self):
        """The new document's id — **and the root Page block's id**."""
        return self.get("document_id")

    @property
    def title(self):
        """The title Lark stored, as the reply echoed it."""
        return self.get("title")

    @property
    def revision_id(self):
        """The document's revision at creation — the compare-and-swap anchor's starting point."""
        return self.get("revision_id")

    def __getattr__(self, name):
        """Turn ``created.url`` into the reason rather than the interpreter's bare message.

        A caller must be able to tell *"Lark did not answer"* from *"we did not ask"*, and
        ``AttributeError: 'CreatedDocument' object has no attribute 'url'`` says neither.
        Every other missing attribute raises normally.
        """
        if name == "url":
            raise AttributeError(
                f"a created docx document has no `url`: {DOCX_REPLY_CARRIES_NO_URL}")
        raise AttributeError(
            f"{type(self).__name__!r} object has no attribute {name!r}")


#: What the single-block PATCH primitive **costs** — stated ONCE here and projected at both
#: doors it is met through: the primitive's own docstring and the guide's write-recipe router.
#:
#: **LD-576 superseded this constant's CONCLUSION and preserved its REASON.** LD-562 wrote it
#: about a *public* method, to disclose the price of walking through a public door that carried
#: no warning of what it sat outside. That reason survives intact — the four things the primitive
#: sits outside of, and who owns the read-back, are exactly why the door is now shut. What
#: changed is the conclusion: *disclose the public door* became *there is no public door*. The
#: cost text is still true of the engine's own internal primitive, and this is where the
#: engine's own maintainers read it.
PATCH_BLOCK_COST = (
    "The docx single-block PATCH is the engine's own primitive and calling it directly steps "
    "OUTSIDE everything the gated route gives you: outside the plan gate (nothing previews it, "
    "and no `Plan` records it), outside the `STALE_DOCUMENT` whole-document compare-and-swap (a "
    "document edited under you is not detected), and outside the refusal set (no typed refusal "
    "is raised on your behalf, and no apply-log entry is written). THE CALLER OWNS THE "
    "READ-BACK: read the block back and check it says what you meant, because nothing else "
    "will. What it does that the gated route cannot is IN-PLACE, IDENTITY-PRESERVING mutation "
    "— the block keeps its id, and so does everything anchored to it. That is the whole of its "
    "advantage: delete-and-recreate reaches the same content through the gate, at the price of "
    "new block ids. Which is why it is NOT PART OF THE PUBLIC SURFACE: it is `_patch_block`, "
    "internal to this library, and every one of the engine's own writes goes through it. "
    "`patch_block` — the public name it used to carry — still answers, and refuses, naming the "
    "gated route to use instead."
)

#: What a caller who reaches the FENCED public name is told — authored ONCE here and raised as
#: :class:`larkdocio.errors.FencedPrimitiveError`.
#:
#: It names **the two supported routes that now exist** (LD-574's plan-gated `todo.done` edit
#: and LD-575's append-only `GrowTableRequest`), because those are the two edits the public
#: primitive was the only route to before they existed, and then the general route for
#: everything else. It deliberately does **not** say only "deprecated" — the difference between
#: a good refusal and a bad one is not severity, it is whether the message tells the caller
#: what to DO — and it deliberately does **not** name `_patch_block`: pointing a consumer at
#: the private spelling would re-open the door under a new name.
PATCH_BLOCK_FENCE = (
    "WriteClient.patch_block is NOT part of larkdocio's public surface and nothing was sent. "
    "It took the raw docx oneof body around the plan gate, the whole-document revision guard "
    "and the refusal set, so a green call proved nothing and the caller owned the read-back. "
    "Use the gated route instead. To tick or untick a CHECKBOX on an item that already exists: "
    "flip `- [ ]` to `- [x]` in an edited block-identity projection and reconcile — the plan "
    "and the apply-log entry carry `todo_done`, the item keeps its block id and its text is not "
    "rewritten. To add a ROW to a table that already exists: a `GrowTableRequest` through "
    "`dry_run` and `apply` appends one row at the end and keeps every pre-existing block id, in "
    "order. For anything else, author the replacement and delete the old block through the same "
    "plan gate — that reaches the same content, at the price of new block ids. Both routes, "
    "end to end, are in `larkdocio guide` (the write-recipe router)."
)


def _block_path(document_id, block_id, suffix=""):
    """The docx-v1 block path (no query): ``…/documents/{doc}/blocks/{block}[{suffix}]``.

    The shared prefix every block read/write composes; ``suffix`` appends the
    sub-resource (``/children``, ``/children/batch_delete``) for the collection calls.
    """
    return f"/open-apis/docx/v1/documents/{document_id}/blocks/{block_id}{suffix}"


class WriteClient(CredentialedRawHttpClient):
    """Throttled, typed docx v1 write client on the shared core.

    ``transport`` / ``urlopen`` / ``token_fetcher`` are injectable so the client's
    request-building, throttling, and error-typing are unit-testable offline
    (see ``tests/test_write_client.py``); the defaults are the real
    :class:`WriteTransport`, ``urllib``, and the shared token fetcher.
    """

    def __init__(
        self,
        app_id,
        app_secret,
        domain="larksuite.com",
        *,
        transport=None,
        urlopen=urllib.request.urlopen,
        token_fetcher=fetch_tenant_access_token,
        timeout=30,
    ):
        self._app_id = app_id
        self._app_secret = app_secret
        self._domain = domain
        self._base = api_base(domain)
        self._transport = transport or WriteTransport()
        self._urlopen = urlopen
        self._token_fetcher = token_fetcher
        self._timeout = timeout
        self._token = None

    def _credential_pair(self):
        """The WRITE pair — every write leg rides it and nothing here falls back to the
        read pair, so a rejected credential on ``roundtrip``'s **push** phase names
        ``LARK_WRITE_APP_*`` rather than the pair its **pull** phase used (LD-672)."""
        return WRITE_ENV

    # -- transport (over common.transport.RawHttpClient) ------------------ #

    def _raw_request(self, method, path, body=None):
        """One raw docx-v1 attempt over the shared core (B2 — body-bearing). Returns
        the parsed JSON body (dict). The shared skeleton's default HTTPError posture
        applies (B1): an error body is parsed and **returned** so the transport can
        see a ``99991400`` and back off — never raised here — and a non-JSON body
        degrades to ``{"code","msg"}``; a genuine transport (``URLError``) failure
        raises the typed :class:`~larkdocio.errors.LarkAPIError`.
        """
        return self._send(method, path, body=body)

    def _write(self, method, path, body=None, *, context="Lark write"):
        """Throttled write: pace + 99991400 backoff (S2), then type non-zero codes."""
        resp = self._transport.execute(lambda: self._raw_request(method, path, body))
        return raise_for_lark_code(resp, context=context,
                                   credential_env=WRITE_ENV)

    # -- docx v1 write surface ------------------------------------------- #

    # The summary line below is deliberately ONE line: capabilities() projects a lifecycle op's
    # summary from the first docstring LINE, so a summary wrapped across two ships TRUNCATED.
    # LD-577's typed-return rewrite wrapped this one and the front door read "…returns a" for a
    # whole release; LD-586 unwrapped it. Keep it on one line.
    def create_document(self, title="", *, folder_token: Optional[str] = None
                        ) -> "CreatedDocument":
        """Create a docx document in the folder ``folder_token``, returning a :class:`CreatedDocument`.

        **The returned value IS the reply's ``data.document``** — a ``dict`` subclass carrying
        that payload unchanged, so every subscript, ``.get``, membership test, splat,
        ``json.dumps`` and ``==`` against the plain dict keeps its old answer. What it adds is
        :attr:`~CreatedDocument.document_id`, :attr:`~CreatedDocument.title`,
        :attr:`~CreatedDocument.revision_id`, the destination echoed back as
        :attr:`~CreatedDocument.folder_token` — and the ability to *say* it has no url
        (:data:`DOCX_REPLY_CARRIES_NO_URL`), which no bag could.

        **The destination is the caller's** — ``folder_token`` is **required**, and every way of
        not giving one reaches the same refusal: **omitted** entirely, ``None``, empty, or
        whitespace, all refused **locally, before any call**, with
        :class:`~larkdocio.errors.MissingDestinationError`. It is keyword-only and defaults to
        ``None`` — the default is not a licence to skip it, it is what lets *this library* answer
        an omitted destination with its teaching text instead of leaving the caller a bare
        ``KeyError``-grade traceback from the interpreter. (``None`` is not a destination and
        cannot become one; :meth:`larkdocio.base.schema_client.BaseSchemaClient.create_app` has
        shipped the same shape from the start.) ``folder_token`` used to default to the empty
        string, which Lark accepts and files in the application's own space: a space with no
        human interface, whose trash cannot be listed and where a delete is a trash rather than
        a purge. The rule, and the measurements behind it, are on
        :mod:`larkdocio.common.destination`; nothing here creates a folder to put the document
        in.

        The root Page block's id equals the ``document_id``.
        """
        require_destination(folder_token, what="a document")
        body = {"title": title, "folder_token": folder_token}
        resp = self._write(
            "POST", "/open-apis/docx/v1/documents", body, context="create document"
        )
        return CreatedDocument(resp["data"]["document"], folder_token=folder_token)

    def get_document(self, document_id):
        """``GET …/documents/{id}`` → ``data.document`` — the whole-document **meta**.

        The docx meta object: ``document_id``, ``title``, ``display_setting`` and — the
        reason this exists — ``revision_id``, the whole-document
        compare-and-swap anchor. Characterized live on a self-provisioned disposable doc
        (2026-07-28): ``revision_id`` is ``1`` on a fresh document, **advances one per
        write**, and is **stable across reads**, so it is a monotonic, read-inert anchor.

        Note the distinction from the ``document_revision_id=-1`` query every *block* call
        carries: that is a request pin meaning "against latest", not a document revision.
        """
        path = f"/open-apis/docx/v1/documents/{document_id}"
        resp = self._write("GET", path, None, context="get document")
        return resp["data"]["document"]

    def read_document_revision(self, document_id):
        """The document's current ``revision_id`` (:meth:`get_document`), or ``None``.

        The scalar the whole-document compare-and-swap compares: cached at plan time and
        re-read by :func:`larkdocio.write.apply.apply` immediately before the batch, which
        refuses the **entire** batch (``STALE_DOCUMENT``, zero writes) on any difference.
        ``None`` when the meta payload carries no ``revision_id`` — reported by the plan's
        ``revision_guard`` marker as unavailable rather than guessed at (the guard is never
        silently off). An API error propagates; the engine turns it into the conservative
        refusal so it cannot be mistaken for "unchanged".
        """
        return self.get_document(document_id).get("revision_id")

    def create_children(self, document_id, block_id, children, index=-1):
        """Create 1–50 child blocks under ``block_id`` at ``index``; returns ``data``."""
        path = f"{_block_path(document_id, block_id, '/children')}?{_REVISION_Q}"
        resp = self._write(
            "POST", path, {"index": index, "children": children},
            context="create children",
        )
        return resp["data"]

    def create_descendant(self, document_id, block_id, *, children_id, descendants,
                          index=-1):
        """Create a whole **subtree** under ``block_id`` at ``index`` in ONE call; returns
        ``data``.

        ``POST …/documents/{doc}/blocks/{block}/descendant`` — the same block family, the same
        parent-and-``index`` placement pair :meth:`create_children` takes, and **the same
        scope**: no new grant is requested, widened or escalated, and the permission registry
        derives the requirement from this method's own path exactly as it does for every other
        call here. What differs is the body: the blocks are sent **flat, keyed by
        CALLER-MINTED temporary ids** (``block_id`` on each descendant, referenced from its
        parent's ``children``), and ``children_id`` names which of them attach at the insertion
        point. Lark answers with ``data.block_id_relations`` — a ``temporary_block_id`` → real
        ``block_id`` map — plus the created top-level ``children``.

        **This library uses it for exactly one thing: authoring a TABLE subtree atomically.**
        A table is the one authored block whose cells and their inner text blocks are a tree
        the create endpoint cannot express in one call, and building it in three movements
        (create the seed grid → grow it a line per call → fill each cell) is what makes a
        failure partway through leave a **half-written table in a real document**. This
        endpoint has no such state: every over-envelope refusal measured on it read back as
        **nothing created**. A general subtree-authoring route over the other block kinds is
        deliberately NOT built on it here — that is a larger question, and this method answers
        the narrow one.

        **The envelope is measured, not assumed** (route scope: one tenant,
        ``tenant_access_token``, docx v1, block type 31, on documents the probe created — not
        wiki-wrapped; ``user_access_token``, other tenants and wiki-wrapped documents are
        **unmeasured, not refuted**). The bisection (the 2026-08-14 table-cell-creation
        spike, § 3b; its write-up was retired on 2026-09-18) ran at two shapes:
        :data:`MAX_DESCENDANTS_PER_CALL` descendants pass and one more answers
        ``99992402 field validation failed`` with nothing created. See
        :data:`~larkdocio.write.encode.MAX_ONE_CALL_TABLE_CELLS` for what that is in cells.
        """
        path = f"{_block_path(document_id, block_id, '/descendant')}?{_REVISION_Q}"
        resp = self._write(
            "POST", path,
            {"index": index,
             "children_id": list(children_id),
             "descendants": list(descendants)},
            context="create descendant",
        )
        return resp["data"]

    def get_block(self, document_id, block_id):
        """Fetch one live block (re-validate a cached id right before patching)."""
        path = f"{_block_path(document_id, block_id)}?{_REVISION_Q}"
        resp = self._write("GET", path, None, context="get block")
        return resp["data"]["block"]

    # ----------------------------------------------------------------------- #
    # THE FENCE — its provenance sits here in the source rather than in the docstring below,
    # so the durable record is beside the code without entering the wheel's consumer-facing
    # docstring corpus, where an issue id is internal dialect.
    #
    # LD-576, on the maintainer ruling in the 2026-08-25 round-5 fix-program handoff § 2.1 (that
    # handoff was retired on 2026-09-18), ruling 3, quoted in full because
    # a successor will be tempted to declare it instead:
    #
    #   "Fork 3 — FENCE patch_block. Do NOT declare it in capabilities(). The reasoning,
    #    because a successor will be tempted to declare it instead: declaring an operation that
    #    bypasses the plan gate, the revision guard and the entire refusal set would make an
    #    unsafe path SUPPORTED — a permissions row, two guarded projections, and a capability
    #    that can never be removed. That discloses it by BLESSING it. Fencing satisfies 'no
    #    undeclared capability' properly: nothing is undeclared because nothing is public. It is
    #    a rename to private, not a deletion — the internal call sites keep using it."
    #
    # The sequence was load-bearing and is satisfied: the two gated routes the fence names
    # (LD-574's todo.done edit, LD-575's append-only table grow) shipped FIRST, because fencing
    # before them would have closed a consumer's only identity-preserving route to a checkbox
    # and a table row — converting a silent-success defect into a hard-refusal defect and
    # calling it a fix. Declaring it is refused permanently, not deferred: declare it only if
    # you intend to keep it, and we do not.
    # ----------------------------------------------------------------------- #

    def patch_block(self, document_id, block_id, update):
        """**FENCED — not part of larkdocio's public surface. Raises; sends nothing.**

        This name used to be the raw single-block PATCH. It is now a permanent signpost: it
        answers (so ``hasattr`` and every import still behave) and it refuses with
        :class:`~larkdocio.errors.FencedPrimitiveError`, whose message names the gated route to
        use instead (:data:`PATCH_BLOCK_FENCE`). The primitive itself did not go away — it is
        :meth:`_patch_block`, internal, and every one of the engine's own writes still runs
        through it. **This is a rename to private, not a deletion.**

        **WHY THIS IS FENCED AND NOT DECLARED — read this before "helpfully" declaring it.**
        Declaring an operation that bypasses the plan gate, the revision guard and the entire
        refusal set would make an unsafe path **supported**: a permissions row, two guarded
        projections, and a capability that can never be removed. That discloses it by
        **blessing** it. Fencing satisfies "no undeclared capability" properly — **nothing is
        undeclared because nothing is public.** The refusal to declare it is permanent, not
        deferred, and the reason is preserved here rather than only in the record of the change
        that closed the door.

        The disclosure that preceded the fence is not struck either — :data:`PATCH_BLOCK_COST`
        still states, once, what the primitive sits outside of and who owns the read-back. Only
        its conclusion moved.
        """
        raise FencedPrimitiveError(PATCH_BLOCK_FENCE)

    def _patch_block(self, document_id, block_id, update):
        """Patch ONE block. ``update`` is the oneof body (e.g. ``update_text_elements``).

        **Internal — the engine's own primitive** (fenced out of the public surface by LD-576;
        the public name :meth:`patch_block` refuses and routes the caller to the gated ops).
        Every mutating docx write this library performs goes through here.

        <<PATCH_BLOCK_COST>>
        """
        path = f"{_block_path(document_id, block_id)}?{_REVISION_Q}"
        resp = self._write("PATCH", path, update, context="patch block")
        return resp.get("data")

    def batch_update_blocks(self, document_id, requests):
        """Patch MANY blocks in ONE call — ``PATCH …/documents/{doc}/blocks/batch_update``.

        Each entry of ``requests`` is a ``block_id`` plus the same oneof body
        :meth:`_patch_block` takes for that block (``{"block_id": …,
        "update_text_elements": {…}}``), so a batched write and a single write put the
        **identical** body on a block — nothing about what lands changes with the route.

        This exists because the per-cell fill was the whole cost of authoring a table: 216
        cells cost **463 write API calls / 158.41 s** as one ``get_block`` + one
        ``_patch_block`` each, against a platform that takes the same content in a handful of
        calls — the same table now measures **37 calls / 12.4 s**. The route is **measured, not assumed** — 48, 40 and 3 updates in one call, all
        ``code 0``, all read back on a disposable document the probe created and trashed —
        and :data:`MAX_BATCH_UPDATES_PER_CALL` is the largest of those, so a caller chunking
        by it stays inside the evidence.

        Same endpoint family, same throttle, same typed error surfacing as every other write
        here: **no new scope is requested, widened or escalated** — the docx document scope
        this surface already requires is the one this call rides (see
        :mod:`larkdocio.permissions`, which derives that from this method's own path).

        An **empty** ``requests`` issues nothing and returns ``None``: a call that says
        nothing would spend a throttled slot for nothing.
        """
        if not requests:
            return None
        path = (f"/open-apis/docx/v1/documents/{document_id}/blocks/batch_update"
                f"?{_REVISION_Q}")
        resp = self._write("PATCH", path, {"requests": list(requests)},
                           context="batch update blocks")
        return resp.get("data")

    def list_document_blocks(self, document_id, page_size=BLOCK_LIST_PAGE_SIZE):
        """Every block of a document, flat — ``GET …/documents/{doc}/blocks``, paged out.

        The write side's own read of the block tree, walked to exhaustion on ``has_more`` /
        ``page_token`` **the way the guarded sibling walks do it** —
        ``comments/client.py``'s ``_walk_pages`` and ``base/client.py``'s: a page cap
        (:data:`MAX_BLOCK_LIST_PAGES`) and a seen-cursor set, so no shape of server answer can
        make it run forever. It used to say it walked *"exactly the way the reader walks the
        same endpoint"*, and that sentence was pointing at the wrong sibling: the reader's two
        walks of this endpoint family are bare ``while True:`` loops with neither guard, so
        the model named in writing was the unguarded one. Each item carries its ``block_id``,
        ``block_type``, ``parent_id`` and ``children`` — which is what makes this the cheap way
        to learn the inner text-block id of every cell of a freshly created table: **one
        paginated read** instead of one ``get_block`` per cell.

        Returns the raw block payloads in the API's own order, unfiltered — this client does
        not model the tree; it hands back what Lark said.

        **It never returns a SHORT list.** Two server answers would otherwise make it do so,
        and both raise :class:`~larkdocio.errors.LarkPaginationError` naming what was seen:

        * ``has_more: true`` with a ``page_token`` the walk has **already used** — asking
          again would replay the same page forever;
        * ``has_more: true`` past :data:`MAX_BLOCK_LIST_PAGES` fresh cursors.

        A caller here derives WRITE TARGETS from this list, so quietly returning what was
        collected would aim a table's cell fill at a subset of its cells and report success.
        A ``has_more: true`` with **no** cursor at all raises for the same reason: the server
        says there is more and hands back no way to ask for it.
        """
        blocks = []
        page_token = ""
        seen = set()
        for _ in range(MAX_BLOCK_LIST_PAGES):
            path = (f"/open-apis/docx/v1/documents/{document_id}/blocks"
                    f"?{_REVISION_Q}&page_size={page_size}")
            if page_token:
                path = f"{path}&page_token={page_token}"
            data = self._write("GET", path, None,
                               context="list document blocks").get("data") or {}
            blocks.extend(data.get("items") or ())
            if not data.get("has_more"):
                return blocks
            seen.add(page_token)
            page_token = data.get("page_token") or ""
            if not page_token or page_token in seen:
                raise LarkPaginationError(
                    f"listing the blocks of document {document_id} could not be run to "
                    f"exhaustion: page {len(seen)} reported has_more=true and handed back "
                    + ("no page_token at all" if not page_token
                       else f"page_token {page_token!r}, which this walk has already used")
                    + f". {len(blocks)} blocks were collected and the list is INCOMPLETE, so "
                    "it is refused rather than returned — a caller derives which blocks to "
                    "WRITE TO from this list, and a short one would aim those writes at a "
                    "subset without saying so.",
                    pages=len(seen), items=len(blocks))
        raise LarkPaginationError(
            f"listing the blocks of document {document_id} followed "
            f"{MAX_BLOCK_LIST_PAGES} pages of fresh cursors and the server still reports "
            f"has_more=true. {len(blocks)} blocks were collected and the list is INCOMPLETE, "
            "so it is refused rather than returned. The cap is a backstop against an endless "
            "chain of cursors, not a document-size limit: at this page size it is far beyond "
            "any document this endpoint is expected to hold.",
            pages=MAX_BLOCK_LIST_PAGES, items=len(blocks))

    def batch_delete(self, document_id, block_id, start_index, end_index):
        """Delete the contiguous child range ``[start_index, end_index)`` of ``block_id``."""
        path = f"{_block_path(document_id, block_id, '/children/batch_delete')}?{_REVISION_Q}"
        return self._write(
            "DELETE", path, {"start_index": start_index, "end_index": end_index},
            context="batch delete",
        )

    def delete_document(self, document_id):
        """Trash the whole document via Drive (best-effort full teardown).

        Needs a Drive scope, and WHICH one is not established — see
        :mod:`larkdocio.permissions`, whose row for this endpoint is deliberately empty with
        that reason rather than a guess. The harness treats a failure here as non-fatal and
        falls back to emptying the doc's children (which needs only the ``docx:document``
        scope this surface already requires; the registry is the source for that too).
        """
        path = f"/open-apis/drive/v1/files/{document_id}?type=docx"
        return self._write("DELETE", path, None, context="delete document")

    # -- the comment family (LD-202) — Drive v1, THREE calls and no more ---- #
    #
    # These three are the ONLY comment writes that exist, and they are here — on the
    # shipped client — rather than in the test tree, because the ops that ride them ship
    # (LD-202 / the LD-176 promotion pattern: the shipped path is the exercised path).
    # What is deliberately NOT here:
    #
    # * **no anchored create.** The route takes an ``anchor`` / ``quote`` / ``is_whole``,
    #   answers ``code 0``, and silently ignores all three. The body built below therefore
    #   carries ``reply_list`` and **nothing else** — the refusal happens upstream, at plan
    #   time, so a caller learns the truth instead of getting a comment they did not ask for;
    # * **no delete-a-comment call.** ``DELETE …/comments/{cid}`` is not a route: it answers
    #   a gateway-level, non-JSON ``404 page not found``. A comment's content *is* its
    #   replies, so removal is :meth:`delete_comment_reply` over every reply;
    # * **no reply-content rewrite** (``PUT …/replies/{rid}``) and no solve/unsolve
    #   (``PATCH …/comments/{cid}``) — both exist on the API and neither ships.

    def _comment_path(self, document_id, suffix="", *, file_type="docx"):
        """The Drive-v1 comment path with its ``file_type`` query — built in ONE place.

        Every comment call composes its URL here, so the ``file_type`` query cannot be spelled
        differently per call and the family's shape is one line to re-point.
        """
        return (f"/open-apis/drive/v1/files/{document_id}/comments{suffix}"
                f"?file_type={file_type}")

    def create_whole_document_comment(self, document_id, text, *, file_type="docx"):
        """Put ONE whole-document comment carrying ``text`` on the file; returns ``data``.

        The response reports the new ``comment_id``, the thread's single ``reply_id``, and
        the ``user_id`` the comment was authored as — the application's own bot id, which is
        the id a later :meth:`delete_comment_reply` is judged against. Note that it does
        **not** report ``is_whole``: the create and single-fetch responses omit the scope
        flag that ``list`` / ``batch_query`` carry, so "is it really whole-document?" is a
        question only a read-back can answer (which is exactly what the live gate does).
        """
        body = {"reply_list": {"replies": [
            {"content": {"elements": [{"type": "text_run", "text_run": {"text": text}}]}}
        ]}}
        resp = self._write("POST", self._comment_path(document_id, file_type=file_type),
                           body, context="create whole-document comment")
        return resp["data"]

    def list_comment_replies(self, document_id, comment_id, *, file_type="docx"):
        """One comment thread's replies, as raw bodies — ``data.items``.

        The read the ownership check runs on: each item carries its ``reply_id`` and the
        ``user_id`` that wrote it, which together decide whether a removal may proceed at
        all.
        """
        path = self._comment_path(document_id, f"/{comment_id}/replies", file_type=file_type)
        resp = self._write("GET", path, None, context="list comment replies")
        return list((resp.get("data") or {}).get("items") or ())

    def delete_comment_reply(self, document_id, comment_id, reply_id, *, file_type="docx"):
        """Delete ONE reply. Deleting a thread's **last** reply removes the comment with it.

        The one comment deletion the API offers, and the whole of how a comment is removed.
        A reply the caller did not author is refused HTTP 403 / ``1069303 "forbidden"`` — an
        ownership refusal about *who is asking*. The engine never relies on that server-side
        check to protect a thread, because being refused halfway through a cascade would
        leave the thread half-deleted; it establishes sole ownership first (see
        :mod:`larkdocio.write.comments`).
        """
        path = self._comment_path(
            document_id, f"/{comment_id}/replies/{reply_id}", file_type=file_type)
        return self._write("DELETE", path, None, context="delete comment reply")


# The cost is written ONCE (:data:`PATCH_BLOCK_COST`) and projected into the primitive's own
# docstring, so the door a maintainer reads and the guide's router cannot state it differently.
# LD-576 moved the target from the public name to the private primitive; the mechanism, and the
# guarantee that there is exactly one statement of the cost, are unchanged.
WriteClient._patch_block.__doc__ = (WriteClient._patch_block.__doc__ or "").replace(
    "<<PATCH_BLOCK_COST>>", PATCH_BLOCK_COST)
