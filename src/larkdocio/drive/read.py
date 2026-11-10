"""larkdocio.drive.read — ``read_folder()`` and the promise that one bad child never sinks the
walk (LD-326).

LD-324 walks the tree and LD-325 says which reader takes each child. This module is what finally
**runs** them and decides what a consumer receives — and both of its guarantees are promises
about *failure*, not success:

1. **A child that fails NEVER fails the walk.** Every per-child failure mode — the reader
   raising, Lark refusing the child, a child with no reader, a malformed payload — degrades to a
   *disclosed miss* and the walk keeps going. A folder is a heterogeneous pile owned by many
   people; if one refusal aborted the run the feature would be unusable on exactly the trees it
   was built for.
2. **A miss is never silent, and it is disclosed in Lark's own words.** A refusal quotes Lark's
   own ``code`` and ``msg`` — never a paraphrase, never a guess at the cause — the § D4
   discipline applied one level down. Combined with LD-325's ``file`` disclosure and LD-324's
   truncations, this closes the invariant the whole tranche is judged on:
   :func:`FolderRead.accounted` — **every child the walk saw appears in the output, as a read or
   as a disclosed miss** (folders being the third, *structural*, category — see
   :class:`ChildOutcome`).

The shape is maintainer-ruled (§ D5): a **structured result** (:class:`FolderRead`) the caller iterates,
plus **one Markdown document** (:func:`larkdocio.drive.render.render_folder`) — the
model→serializer division the docx reader already runs on
(:mod:`larkdocio.model.nodes` → :mod:`larkdocio.model.renderer`). **The library writes no
files** (AC7): the on-disk shape is the CLI's business (LD-327).

**The reader is the one injectable seam.** ``read_folder(..., reader=...)`` takes a callable
``(surface, *, url, token, name) -> str`` (or a :class:`ChildRead`, which also carries the
revision anchor the read already held); the default (:func:`read_child`) dispatches
to the existing docx / Sheets / Base readers by their own entry points and is **the only thing
here that touches the network**. Every offline test injects a fake, so the orchestration —
skip-loudly, the invariant, the rendering — is proven without a live call. The ``sheet`` and
``base`` legs are **asserted-not-demonstrated** exactly as LD-325 labelled them (no live
enumeration has ever surfaced either), and the docx leg reuses the read pipeline's own
``_resolve_doc`` + ``_parse`` so no reader is re-implemented and no file is written.
"""
from dataclasses import dataclass
from functools import partial
from typing import Any, Callable, NamedTuple, Optional, Tuple

from larkdocio.base import read_base_markdown
from larkdocio.common import validate_download_url
from larkdocio.drive.client import DriveClient
from larkdocio.drive.dispatch import (
    READ as _D_READ,
    RECURSE as _D_RECURSE,
    RESOLVE as _D_RESOLVE,
    dispatch,
)
from larkdocio.drive.models import AssetRef, FolderName, FolderWalk, WalkedChild
from larkdocio.drive.walk import (
    DEFAULT_MAX_CALLS,
    DEFAULT_MAX_CHILDREN,
    DEFAULT_MAX_DEPTH,
    walk_folder,
)
from larkdocio.errors import LarkAPIError, LarkConfigError

#: Where a url this verb cannot walk **is** read — the mirror of ``download``'s own
#: ``_NON_DOCUMENT_URL_MESSAGES`` (LD-397). The two verbs do not overlap, so each names the other
#: side rather than merely turning the caller away; the shipped ``folder`` help already promised
#: this refusal ("hand a document URL to `folder` and the URL validator refuses it as not a
#: folder") while nothing performed it, so the wrong-verb case reached Lark.
_NON_FOLDER_READERS = {
    "docx": 'ONE document — `larkdocio download "<url>" -o ./out/`',
    "wiki": 'ONE document — `larkdocio download "<url>" -o ./out/`',
    # LD-658 AC2: this used to end by referring the reader to a Readme/Release section for a
    # `v1_support` label that no shipped document carries, so the pointer led nowhere. It now
    # states the fact instead of citing. (The old pointer SHAPE is deliberately not reproduced
    # here — a guard in the source repository (`tests/test_drive_folder_cli.py`) derives the population
    # by walking this source.)
    "docs": "the unsupported legacy Docs type — this reader reads `docx`, not `docs`",
    "sheets": ("the Sheets surface — larkdocio.sheets.read_spreadsheet_markdown(url), one "
               "call for the whole workbook"),
    "base": "the Base surface — larkdocio.base.read_base_markdown(url)",
}


def _non_folder_refusal(url_type: str) -> str:
    """The wrong-verb refusal, stated for free from the URL string alone."""
    reader = _NON_FOLDER_READERS.get(url_type, "another surface")
    return (
        f"that is a {url_type.upper()} url, not a DRIVE FOLDER url. This verb enumerates a "
        f"FOLDER — a container of many documents — and writes ONE Markdown document for the "
        f"whole tree; that url is read by {reader}. The url validator recognised it and handed "
        f"back its type and token, so nothing was asked of Lark and no credential was used."
    )

#: The three outcome kinds a walked child can land in. ``read`` and ``skipped`` are the AC4
#: partition; ``folder`` is the structural third category — a folder recurses (its children
#: appear), it is neither a document to read nor a failure to disclose, but it still appears in
#: the output (the tree index), so it is accounted for, never dropped.
READ = "read"
SKIPPED = "skipped"
FOLDER = "folder"

#: The four skip modes — one per way a child can fail (AC3). Each is a distinct code path so the
#: four mode-tests exercise four real branches.
READER_RAISED = "reader-raised"      #: (a) the reader raised — a bug or an unexpected shape
LARK_REFUSED = "lark-refused"        #: (b) Lark refused the child — its own code+msg are quoted
NO_READER = "no-reader"              #: (c) `file` / unknown type / a disclosed shortcut cycle
MALFORMED = "malformed-payload"      #: (d) the listing returned a child it cannot be read from


@dataclass(frozen=True)
class SkipDisclosure:
    """Why one child was skipped — loudly. ``code`` / ``msg`` are Lark's OWN words, present only
    for a :data:`LARK_REFUSED` miss; everywhere else they are ``None`` and ``reason`` carries the
    honest sentence."""

    mode: str
    reason: str
    code: Optional[int] = None
    msg: Optional[str] = None
    surface: Optional[str] = None


class ChildRead(NamedTuple):
    """What a document reader may hand back: the Markdown, **and the revision anchor the read
    already held**.

    A reader may still return a bare ``str`` — that is the original contract and every caller
    injecting a fake keeps working; the outcome then simply carries no revision, which the
    manifest reports as *unavailable* rather than as a value. The pair exists because a
    change-detection ledger needs an anchor per child, and for the surfaces whose read already
    fetched one, **discarding it at this boundary is the whole defect** — re-obtaining it later
    costs a second call per document.
    """

    markdown: str
    revision: Optional[Any] = None
    assets: Tuple[AssetRef, ...] = ()


@dataclass(frozen=True)
class ChildOutcome:
    """What ``read_folder`` decided for one walked child — exactly one of read / skipped /
    folder. Carries the walked child (so its token/type/name/depth are all reachable) and, for a
    read, its Markdown; for a skip, its :class:`SkipDisclosure`.

    ``revision`` is the anchor the read itself carried, when it carried one — ``None`` means
    **not known**, never a revision of zero (a real value on both surfaces that have one). It is
    populated only on a ``read`` outcome; a skip or a folder has nothing to anchor.
    """

    walked: WalkedChild
    kind: str
    surface: Optional[str] = None
    markdown: Optional[str] = None
    skip: Optional[SkipDisclosure] = None
    revision: Optional[Any] = None
    assets: Tuple[AssetRef, ...] = ()

    @property
    def child(self):
        return self.walked.child

    @property
    def token(self) -> str:
        return self.walked.child.token

    @property
    def name(self) -> Optional[str]:
        return self.walked.child.name

    @property
    def type(self) -> Optional[str]:
        return self.walked.child.type

    @property
    def depth(self) -> int:
        return self.walked.depth


@dataclass(frozen=True)
class FolderRead:
    """The structured result of a folder read: the walked tree, a per-child outcome, each read
    child's Markdown, and the walk's own truncation records. A plain, inspectable, serializable
    object — not a stream, not a generator the caller must drain to learn what happened."""

    root_token: str
    root_name: FolderName
    walk: FolderWalk
    outcomes: Tuple[ChildOutcome, ...] = ()

    @property
    def reads(self) -> Tuple[ChildOutcome, ...]:
        return tuple(o for o in self.outcomes if o.kind == READ)

    @property
    def skips(self) -> Tuple[ChildOutcome, ...]:
        return tuple(o for o in self.outcomes if o.kind == SKIPPED)

    @property
    def folders(self) -> Tuple[ChildOutcome, ...]:
        return tuple(o for o in self.outcomes if o.kind == FOLDER)

    @property
    def truncations(self):
        return self.walk.truncations

    def accounted(self) -> bool:
        """**The tranche's headline promise, as a boolean.** Every walked child appears exactly
        once in the outcomes, and the read/skipped/folder partition is total and disjoint — so
        nothing the walk saw is dropped and nothing is double-counted."""
        walked_tokens = [w.child.token for w in self.walk.children]
        outcome_tokens = [o.token for o in self.outcomes]
        return (
            len(self.outcomes) == len(self.walk.children)
            and sorted(outcome_tokens) == sorted(walked_tokens)
            and len(self.reads) + len(self.skips) + len(self.folders) == len(self.outcomes)
        )


# --------------------------------------------------------------------------- #
# The public entry point.                                                       #
# --------------------------------------------------------------------------- #

def read_folder(
    folder: str,
    *,
    client: Optional[DriveClient] = None,
    domain: str = "larksuite.com",
    reader: Optional[Callable[..., str]] = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_children: int = DEFAULT_MAX_CHILDREN,
    max_calls: int = DEFAULT_MAX_CALLS,
    page_size: Optional[int] = None,
    max_pages: Optional[int] = None,
    deep_read_sheets: bool = False,
    fidelity_read_sheets: bool = False,
    deep_read_bases: bool = False,
    assets: bool = False,
) -> FolderRead:
    """Read a whole Drive folder and return a :class:`FolderRead`.

    ``folder`` is **either a folder URL or a bare folder token** — the
    :func:`larkdocio.base.read_base_markdown` precedent. ``client`` defaults to a
    :meth:`DriveClient.from_read_credentials`-built READ client; ``reader`` defaults to
    :func:`read_child` (the only network-touching seam). The ``max_*`` caps are passed
    straight to :func:`larkdocio.drive.walk.walk_folder`, whose truncation records ride the
    result unchanged. Children are read **serially** under the client's existing throttle — R1
    adds no concurrency (§ Out of scope).

    ``deep_read_sheets`` / ``fidelity_read_sheets`` / ``deep_read_bases`` are ``download``'s own
    opt-ins reaching the walk — **same spelling, same semantics, same default (OFF)**,
    bound into the DEFAULT reader only. Off (the default) the walk behaves exactly as it always
    has: every embedded sheet and Base stays the traceable placeholder and **no Sheets or Base
    API call is made**. An injected ``reader`` is untouched by them — its published seam stays
    ``(surface, *, url, token, name)``, and a caller wiring their own reader chooses their own
    depth.

    ``assets`` makes each read child report the image / whiteboard tokens it
    REFERENCED, as :class:`~larkdocio.drive.models.AssetRef` values on its outcome. It fetches
    nothing and writes nothing — **the library still writes no files** and the fetch is the
    ``folder`` command's own leg (:mod:`larkdocio.drive.assets`). It is an opt-in anyway, so
    that OFF is provably inert in the RESULT as well as on the wire: with the default every
    outcome carries an empty tuple and a walk's structured result is the object it has always
    been.
    """
    token = folder
    resolved_domain = domain
    if "://" in folder:
        resolved_domain, url_type, token = validate_download_url(folder)
        # LD-397 (spike gap G15): the shape check the parse ALREADY performed decides the
        # verb, and it decides it here — BEFORE the READ client is built and therefore before
        # any credential resolution or token mint. A wrong-verb invocation used to reach the
        # network and come back with Lark's own 1061002 (or, with placeholder credentials, an
        # AUTH error for a command that was never going to run).
        if url_type != "drive":
            raise LarkConfigError(_non_folder_refusal(url_type))

    own_client = client if client is not None else DriveClient.from_read_credentials(
        resolved_domain)
    read_one = reader if reader is not None else partial(
        read_child,
        deep_read_sheets=deep_read_sheets,
        fidelity_read_sheets=fidelity_read_sheets,
        deep_read_bases=deep_read_bases,
        assets=assets,
    )

    walk = walk_folder(
        own_client, token,
        max_depth=max_depth, max_children=max_children, max_calls=max_calls,
        page_size=page_size, max_pages=max_pages,
    )
    root_name = own_client.folder_name(token)

    by_token = {w.child.token: w.child for w in walk.children}
    seen = {token} | set(by_token)
    outcomes = tuple(
        _read_one(walked, read_one, seen=seen, resolve=by_token.get)
        for walked in walk.children
    )
    return FolderRead(root_token=token, root_name=root_name, walk=walk, outcomes=outcomes)


# --------------------------------------------------------------------------- #
# Per-child: dispatch, then read-or-skip-loudly.                                #
# --------------------------------------------------------------------------- #

def _read_one(walked: WalkedChild, reader, *, seen, resolve) -> ChildOutcome:
    child = walked.child
    terminal = _terminal(dispatch(child, seen=seen, resolve=resolve))
    kind = terminal.kind

    if kind == _D_RECURSE:
        # A folder (or a shortcut resolving to one): structural, not a document. It appears in
        # the tree index; it is neither read nor a miss.
        return ChildOutcome(walked, FOLDER, surface="drive")

    if kind == _D_READ:
        surface = terminal.surface
        if terminal.url is None:
            return _skip(
                walked, MALFORMED, surface,
                (f"the listing returned no url for this {child.type} child, so it cannot be "
                 "read; disclosed rather than guessed"))
        try:
            produced = reader(surface, url=terminal.url, token=terminal.token, name=child.name)
        except LarkAPIError as exc:
            return _skip(
                walked, LARK_REFUSED, surface, _lark_sentence(exc),
                code=exc.code, msg=exc.msg)
        except Exception as exc:  # noqa: BLE001 — a reader bug is disclosed, never fatal to the walk
            return _skip(
                walked, READER_RAISED, surface,
                (f"the {surface} reader raised while reading this child and the walk continued: "
                 f"{exc!r}"))
        markdown, revision, assets = _normalize(produced)
        return ChildOutcome(walked, READ, surface=surface, markdown=markdown,
                            revision=revision, assets=assets)

    # _D_NO_READER (file), _D_UNKNOWN (a type never seen), CYCLE (a shortcut into the visited
    # set) — each a disclosed miss carrying the dispatcher's own reason.
    reason = terminal.reason or "this child has no reader; disclosed, never read"
    return _skip(walked, NO_READER, terminal.surface, reason)


def _normalize(produced) -> Tuple[str, Optional[Any], Tuple[AssetRef, ...]]:
    """Accept either contract from a reader: a bare Markdown ``str`` (the original), or a
    :class:`ChildRead` carrying the revision the read already held — and, since LD-386, the
    asset refs it saw. Nothing else is guessed at — a reader that hands back something else is
    coerced to text and reports no revision and no assets, which reads as *unavailable*
    downstream rather than as a fabricated anchor."""
    if isinstance(produced, ChildRead):
        return produced.markdown, produced.revision, tuple(produced.assets or ())
    return produced, None, ()


def _terminal(outcome):
    """Follow a resolved shortcut to the outcome that actually reads (or refuses) it."""
    while outcome.kind == _D_RESOLVE and outcome.target is not None:
        outcome = outcome.target
    return outcome


def _skip(walked, mode, surface, reason, *, code=None, msg=None) -> ChildOutcome:
    return ChildOutcome(
        walked, SKIPPED, surface=surface,
        skip=SkipDisclosure(mode=mode, reason=reason, code=code, msg=msg, surface=surface))


def _lark_sentence(exc: LarkAPIError) -> str:
    """A disclosure that quotes Lark's OWN code and msg — never a paraphrase (§ D4, one level
    down)."""
    return (f"Lark refused this child (code {exc.code}: {exc.msg}) and the walk continued; "
            "larkdocio quotes Lark's own words and diagnoses no further.")


# --------------------------------------------------------------------------- #
# The default reader — the one network seam. Reuses the existing readers by     #
# their own entry points; re-implements none of them (AC8).                     #
# --------------------------------------------------------------------------- #

def read_child(surface: str, *, url: str, token: str,
               name: Optional[str] = None,
               deep_read_sheets: bool = False,
               fidelity_read_sheets: bool = False,
               deep_read_bases: bool = False,
               assets: bool = False) -> ChildRead:
    """The default document reader: route one child to the existing reader for its ``surface``,
    and hand back its Markdown **plus the revision anchor that read already carried**.

    * ``docx`` — the read pipeline's own ``_resolve_doc`` + ``_parse`` (no file write, no image
      download; the folder read produces text, and the on-disk shape is the ``folder`` CLI
      command's). Revision: the document's own ``revision_id``, which the block read returns.
    * ``sheets`` — :class:`~larkdocio.sheets.client.SheetsReadClient` +
      :func:`~larkdocio.sheets.table.render_spreadsheet` (asserted-not-demonstrated, § O7).
      Revision: ``properties.revision``, which rides the values reply.
    * ``base`` — :func:`~larkdocio.base.read_base_markdown` (asserted-not-demonstrated).
      **No revision**: a Base's anchor is per TABLE, not per document, so there is no single
      number for the child and none is invented.

    **Not one extra API call is made for a revision.** Every anchor here is a value the read
    already fetched and used to throw away; where a surface's read does not carry one, this
    returns ``None`` and the manifest says *unavailable* in as many words.

    ``assets`` is the folder command's own opt-in and lands on the **docx** leg only — a spreadsheet and a Base
    render to text with no binary of their own, so there is nothing to report and nothing is
    invented. The refs are a projection of the parse that already happened; **no extra call is
    made for them either**, and the fetch is somebody else's job.
    """
    if surface == "docx":
        return ChildRead(*_read_docx_markdown(
            url,
            deep_read_sheets=deep_read_sheets,
            fidelity_read_sheets=fidelity_read_sheets,
            deep_read_bases=deep_read_bases,
            assets=assets,
        ))
    if surface == "sheets":
        return ChildRead(*_read_sheet_markdown(
            url, fidelity_read_sheets=fidelity_read_sheets))
    if surface == "base":
        return ChildRead(read_base_markdown(url), None)
    raise ValueError(f"no default reader for surface {surface!r}")


def read_child_markdown(surface: str, *, url: str, token: str, name: Optional[str] = None) -> str:
    """:func:`read_child`'s Markdown alone — the published, unchanged text-only contract.

    Kept beside the revision-carrying reader rather than replaced by it: a caller that wants
    one document's Markdown should not have to learn a pair type to get it.

    **This docstring called itself "the published contract" while nothing a consumer reads
    named it** — 17 mentions of ``read_folder`` in the shipped guide against zero of this, so
    nothing a reader met said that a library-level url-to-Markdown entry point existed.
    **The mechanical reason it escaped every index: it is exported from**
    ``drive.__all__`` **and not from** ``larkdocio.__all__``, so a consumer or a guard that
    learns the public surface off the TOP-LEVEL export list cannot see it. That asymmetry is
    NOTED, not fixed: re-exporting the symbol would publish a second entry point for the one
    question ``capabilities/_levels.py`` already answers, which that standing position declines.
    The fix is routing — the guide's docx-read recipe now names this call and runs it.

    **What it does NOT do, and the guide says all four**: no image fetch, no file write, no
    routing at all (nothing places the output anywhere, because nothing is written; the first
    three are the ``download`` CLI verb's jobs, and the only placement that verb does is the
    caller's own ``--route`` — no destination is derived from a document's contents on either
    side), and **no @mention resolution** — ``read.download._parse`` builds ``Parser(config)`` with no ``read_client``
    and the substitution is a SEPARATE pipeline step ``download`` takes and this leg does not,
    so a mention-bearing document reads back here with raw ``@ou_…`` ids. Asserted in
    ``tests/test_single_document_read_pointer.py`` (in the source repository) rather than left to
    this paragraph.
    """
    return read_child(surface, url=url, token=token, name=name).markdown


def _read_docx_markdown(url: str, *, deep_read_sheets: bool = False,
                        fidelity_read_sheets: bool = False,
                        deep_read_bases: bool = False,
                        assets: bool = False):
    """Read one docx through the existing pipeline, writing nothing; return
    ``(markdown, revision_id, asset_refs)``.

    Reuses ``larkdocio.read.download``'s own ``_resolve_doc`` (URL/host validation, wiki-to-docx
    resolution, client construction) and ``_parse`` (block read + parse). The image tokens are
    left un-downloaded on purpose — the library writes no files (AC7) and downloading images is
    the CLI's on-disk concern (LD-327). The ``revision_id`` comes off the document object that
    same block read already returned, so it costs nothing; a payload without one yields
    ``None`` — *not known*, never revision zero.

    **The deep reads are ``download``'s, plumbed — not re-implemented (LD-384).** The three
    opt-ins default OFF, and OFF constructs nothing: the call below is byte-for-byte the one
    this leg has always made, so a folder walk with no flags makes no Sheets or Base API call.
    Opted in, the clients come from ``download``'s own
    :func:`~larkdocio.read.download.build_deep_read_clients` — one construction shared by both
    verbs, so the flags cannot come to mean two things. A deep read that fails still degrades
    to the placeholder inside the bridge; a failure this leg cannot absorb (a client that will
    not build) rides the walk's per-child skip-loudly arm and is disclosed as that child's
    miss.

    **``assets`` REPORTS, it does not fetch (LD-386).** With it on, the image and whiteboard
    tokens the parse already queued (``parser.img_tokens`` / ``parser.board_tokens``) come back
    as :class:`~larkdocio.drive.models.AssetRef` values so the ``folder`` command's own leg can
    fetch them; nothing here downloads, and the docstring's "no file is written" promise above
    is untouched. **Attachments (type-23 ``file_tokens``) are deliberately NOT in this set** —
    they are ``download``'s own separate opt-in (``download_attachments``, default off), and
    folding them in here would make one folder flag mean two of ``download``'s knobs."""
    from larkdocio.read import download as _dl

    _dl.init_env(None)
    app_id, app_secret = _dl.get_read_credentials()
    client, config, _doc_type, doc_token = _dl._resolve_doc(url, "", None, app_id, app_secret)
    sheets_client, sheets_export_reader, base_client = _dl.build_deep_read_clients(
        url, "", app_id, app_secret,
        deep_read_sheets=deep_read_sheets,
        fidelity_read_sheets=fidelity_read_sheets,
        deep_read_bases=deep_read_bases,
    )
    docx, _blocks, parser, _title, markdown = _dl._parse(
        client, config, doc_token,
        sheets_client=sheets_client, sheets_export_reader=sheets_export_reader,
        base_client=base_client,
    )
    return markdown, getattr(docx, "revision_id", None), _asset_refs(parser, assets)


def _asset_refs(parser, wanted: bool) -> Tuple[AssetRef, ...]:
    """The image + whiteboard tokens one parse queued, in document order per kind.

    Empty unless opted in, so the default carries no refs at all rather than carrying refs
    nobody asked for. Order is images then boards, each in the order the parser saw them —
    deterministic, because the fetch and the disclosure that follow are.
    """
    if not wanted:
        return ()
    images = tuple(AssetRef(token, "image")
                   for token in getattr(parser, "img_tokens", None) or ())
    boards = tuple(AssetRef(token, "board")
                   for token in getattr(parser, "board_tokens", None) or ())
    return images + boards


#: Why the fill layer is missing when the export leg itself did not complete. Rendered into
#: the render's own ``FidelityUnavailable`` note, which is the point: the tab then SAYS its
#: fills could not be read instead of looking exactly like a tab that has none.
_SHEET_EXPORT_FAILED = "the xlsx export the fidelity read needs did not complete"


def _sheet_fidelity(domain: str, token: str, pairs):
    """The opt-in fill/emphasis source for a whole spreadsheet: ``{sheet_id: ExportedSheet}``.

    Nothing here is new machinery — it is the two shipped pieces joined at the one place that
    never joined them. :meth:`~larkdocio.sheets.export_reader.SheetsExportReader.read_workbook`
    is **one whole-workbook export** (create → poll → download), not a call per cell, which is
    what makes fidelity affordable on a real sheet; and
    :func:`~larkdocio.sheets.export_reader.exported_by_sheet_id` is the title↔``sheet_id`` join
    the renderer's ``fidelity=`` argument takes.

    **A failure degrades to a DISCLOSED gap, never to silence.** Any error building the reader
    or running the export answers a :class:`~larkdocio.sheets.table.FidelityUnavailable`
    sentinel carrying the reason, so every tab's note says the fill layer could not be read —
    unknown is not none, and an unread fill that rendered like an absent one is precisely the
    silence this leg exists to end. The values the read already has are delivered either way.
    """
    from larkdocio.sheets.export_reader import SheetsExportReader, exported_by_sheet_id
    from larkdocio.sheets.table import FidelityUnavailable

    try:
        export_reader = SheetsExportReader.from_read_credentials(domain=domain)
        parsed = export_reader.read_workbook(token)
    except Exception as exc:  # noqa: BLE001 — disclosed as a gap, never fatal to the read
        return FidelityUnavailable(f"{_SHEET_EXPORT_FAILED} ({type(exc).__name__}: {exc})")
    if parsed is None:
        return FidelityUnavailable(_SHEET_EXPORT_FAILED)
    return exported_by_sheet_id([tab for tab, _used in pairs], parsed)


def _read_sheet_markdown(url: str, *, fidelity_read_sheets: bool = False):
    """Read one spreadsheet through the existing Sheets entry points; return
    ``(markdown, revision)``.

    ``fidelity_read_sheets`` is ``download``'s own opt-in reaching a **standalone**
    spreadsheet (LD-385). Off (the default) this is byte-for-byte the values-only read it has
    always been and **no export is issued**. On, the L2 export-fidelity leg's per-cell
    **background fills** — the layer the values API does not carry at all — ride into the
    Markdown as each tab's fill disclosure, which is what stops a workbook whose meaning IS
    its colour (a schedule drawn in cell fills, cells otherwise blank) from reading as an
    empty table with nothing said. The ARGB is reported as the export carries it and is never
    interpreted; what a colour means is the reader's semantics, not this library's.

    The revision is the one the values reply already carried
    (:attr:`~larkdocio.sheets.extent.UsedRange.revision`) — spreadsheet-scoped, so the first tab
    that reports one answers for the document. A spreadsheet whose reply carries none yields
    ``None``.

    **The walk skips loudly (LD-383).** This leg was itself a list comprehension over
    ``query_sheets`` — the exact shape one refused tab killed — so it now goes through
    :meth:`~larkdocio.sheets.client.SheetsReadClient.read_spreadsheet`, and the tabs Lark refuses
    ride into the rendered Markdown as a disclosure rather than vanishing from it. Skip-loudly
    inside a child, inside a walk that already skips its children loudly: a workbook whose
    every tab misses raises, and this module's own per-child arm discloses that as the child's
    miss."""
    from larkdocio.sheets.client import SheetsReadClient
    from larkdocio.sheets.table import render_spreadsheet

    sheet_domain, _url_type, token = validate_download_url(url)
    client = SheetsReadClient.from_read_credentials(domain=sheet_domain)
    workbook = client.read_spreadsheet(token)
    revision = next(
        (used.revision for _tab, used in workbook.pairs
         if getattr(used, "revision", None) is not None),
        None)
    fidelity = (_sheet_fidelity(sheet_domain, token, workbook.pairs)
                if fidelity_read_sheets else None)
    return (render_spreadsheet(workbook.pairs, skips=workbook.skips, fidelity=fidelity),
            revision)
