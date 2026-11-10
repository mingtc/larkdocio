"""larkdocio.drive.assets — the ``folder --assets`` leg: N documents' binaries, one pool
(LD-386).

**The problem.** A document whose entire content is a picture — a page that is *only a mind map*
— came back from a folder walk as a file containing a bare token and nothing else.
Technically read, semantically empty. The per-document reader has always known how to pull
images and whiteboard PNGs; the walk had no way to say yes.

**Why this is not a flag pass-through.** The deep-read opt-ins (LD-384) were plumbing: the same
behaviour, reached from a second verb. Assets are not, because at folder scale they carry a
question a single document never asks — *where do N documents' binaries land, and what stops two
of them colliding?* That question is answered here, and the answer is the point of the module.

--------------------------------------------------------------------------------------------
THE LAYOUT DECISION (AC2), and the fork not taken
--------------------------------------------------------------------------------------------

**One shared, flat, token-named pool: ``<-o>/static/``.** Same directory name ``download``
uses (:data:`ASSET_DIR` is *derived* from ``OutputConfig().image_dir`` rather than re-coined),
same token-derived filenames, same relative-link rewrite. So a person who has run ``download``
already knows where to look, and the ``folder`` output — which is **one** Markdown file — has
**one** sibling directory beside it.

**Collisions are impossible by construction, not by convention.** The filename *is* the Lark
asset token, and a token is globally unique in the tenant's Drive; two different assets can
therefore never produce one filename. The converse case — the same token referenced by two
documents — is not a collision at all: it is the **same asset**, and converging on one file is
the intended outcome (``Client.download_image``'s own docstring already says so for a single
document). This module goes one step further than ``download`` and fetches such a token
**once for the whole walk**, not once per referencing document, then relinks **every**
occurrence.

**The rejected fork — per-document subdirectories — is the one with a real collision.** It
would have to name each directory from the document's *title*, and two documents in one Lark
folder may legitimately share a title (the bot's own root folder holds two documents both named
*Example Pre-existing Document* today). It would also store a shared asset — a logo used on
ten pages — ten times, and impose a directory hierarchy that the single rendered Markdown
file has no counterpart for.

--------------------------------------------------------------------------------------------
THE REST OF THE POSTURE
--------------------------------------------------------------------------------------------

* **Opt-in, and OFF is inert.** Fetching binaries across a whole folder is expensive and nobody
  should pay it by surprise. With the flag off nothing here runs at all: no ref is collected, no
  credential is resolved, no client is built, no directory is created.
* **This is the COMMAND's leg, not the read's.** ``read_folder`` still writes no files
  (LD-326 AC7): it reports what each child *referenced*, and this module — reached only from
  :mod:`larkdocio.drive.folder_cmd` — is what turns a ref into a file on disk.
* **A per-asset failure skips LOUDLY and never fails the walk (AC3).** The disclosure quotes
  **Lark's own** ``code`` and ``msg``, names the document and the asset, and appears in the
  rendered Markdown (a ``## Assets not fetched`` section, the sibling of ``## Not read``) as
  well as in the log — the folder surface's existing discipline, one level down. Every
  remaining document is still fetched. An empty section is omitted, so its absence means zero
  misses.
* **Nothing is re-encoded, resized or converted** — the bytes land as Lark served them.
"""
import logging
import os
from dataclasses import dataclass
from typing import Optional, Tuple

from larkdocio.common import get_read_credentials, validate_download_url
from larkdocio.drive.models import AssetRef
from larkdocio.errors import LarkAPIError
from larkdocio.read.client import Client
from larkdocio.read.config import OutputConfig

logger = logging.getLogger("larkdocio")

#: The two fetch paths, which are genuinely different endpoints — the Drive media download and
#: the whiteboard PNG export. A mindmap or flowchart in a Lark document is a **type-43 board**,
#: so :data:`BOARD` is the kind the consumer's blocking case travels.
IMAGE = "image"
BOARD = "board"

#: The pool directory, **derived from ``download``'s own config default and never re-coined**,
#: so the two verbs cannot drift into naming the same thing differently.
ASSET_DIR = OutputConfig().image_dir

#: The disclosure heading — the sibling of ``render_folder``'s ``## Not read``.
MISS_HEADING = "## Assets not fetched"


@dataclass(frozen=True)
class AssetMiss:
    """One asset that could not be fetched. ``code`` / ``msg`` are **Lark's own words**,
    present only when Lark itself refused; everywhere else they are ``None`` and ``reason``
    carries the honest sentence."""

    document: str
    token: str
    kind: str
    reason: str
    code: Optional[int] = None
    msg: Optional[str] = None


@dataclass(frozen=True)
class AssetFetch:
    """What the asset leg did: where the pool is, which tokens landed, and every miss.

    A plain inspectable object, like :class:`~larkdocio.drive.read.FolderRead` — so a caller
    embedding the folder read in a pipeline can see the misses without parsing the Markdown.
    """

    directory: str
    fetched: Tuple[str, ...] = ()
    misses: Tuple[AssetMiss, ...] = ()

    @property
    def complete(self) -> bool:
        """``True`` only when every referenced asset landed — so one boolean can never report a
        partial fetch as a whole one."""
        return not self.misses


def folder_assets(result) -> Tuple[Tuple[str, AssetRef], ...]:
    """Every asset the walk's read children referenced, **deduplicated by token**, paired with
    the display name of the first document that referenced it.

    Deduplication is what makes the shared pool cheap: a logo on ten pages is one fetch.
    The first referencing document is the one named in a miss, because a token that fails fails
    for every document equally and naming all ten would be noise.
    """
    seen = set()
    refs = []
    for outcome in result.reads:
        document = outcome.name or outcome.token
        for ref in outcome.assets or ():
            if ref.token in seen:
                continue
            seen.add(ref.token)
            refs.append((document, ref))
    return tuple(refs)


def fetch_folder_assets(result, markdown: str, output_dir: str, *,
                        domain: Optional[str] = None,
                        fetcher=None,
                        asset_dir: str = ASSET_DIR) -> Tuple[str, AssetFetch]:
    """Fetch every asset the walk referenced into one pool and relink the rendered Markdown.

    Returns ``(markdown, AssetFetch)`` — the Markdown with each fetched token rewritten to its
    local relative link (and a ``## Assets not fetched`` section appended if anything missed),
    plus the structured report.

    ``fetcher`` is the one network seam: ``(kind, token, directory) -> path``. It defaults to
    :func:`_default_fetcher`, which routes ``image`` to the Drive media download and ``board``
    to the whiteboard PNG export — the **existing** client methods ``download`` already uses, so
    no new endpoint is reached and no permission row moves. It is built **lazily**: a folder
    with no assets resolves no credentials and constructs no client.

    ``domain`` defaults to the host of the first asset-bearing child's own listing ``url`` —
    the authoritative host for that child, which is where its binaries live.
    """
    refs = folder_assets(result)
    report_dir = os.path.join(output_dir, asset_dir)
    if not refs:
        return markdown, AssetFetch(directory=report_dir)

    fetch = fetcher or _default_fetcher(domain or _domain_of(result))
    fetched, misses = [], []
    for document, ref in refs:
        try:
            path = fetch(ref.kind, ref.token, report_dir)
        except LarkAPIError as exc:
            misses.append(_disclose(_refusal(document, ref, exc)))
        except Exception as exc:  # noqa: BLE001 — one bad asset never sinks the walk
            misses.append(_disclose(AssetMiss(
                document=document, token=ref.token, kind=ref.kind,
                reason=(f"fetching this {ref.kind} raised and the walk continued: "
                        f"{exc!r}"))))
        else:
            link = os.path.relpath(path, output_dir).replace(os.sep, "/")
            # EVERY occurrence, not the first: the pool is shared, so one token legitimately
            # appears once per referencing document in the single rendered file.
            markdown = markdown.replace(ref.token, link)
            fetched.append(ref.token)

    if misses:
        markdown = markdown.rstrip("\n") + "\n\n" + _disclosure(misses)
    return markdown, AssetFetch(directory=report_dir,
                                fetched=tuple(fetched), misses=tuple(misses))


def _disclose(miss: AssetMiss) -> AssetMiss:
    """Say the miss out loud, then hand it back for the report. **Silence is the one thing this
    leg may not do** — the miss reaches the log here and the rendered Markdown below, so a
    person reading either one sees it."""
    logger.warning("Could not fetch %s %s (in %s): %s",
                   miss.kind, miss.token, miss.document, miss.reason)
    return miss


def _refusal(document: str, ref: AssetRef, exc: LarkAPIError) -> AssetMiss:
    """A refusal in **Lark's own words** — the § D4 discipline the folder read already applies
    to a child, applied one level down to a child's asset."""
    return AssetMiss(
        document=document, token=ref.token, kind=ref.kind, code=exc.code, msg=exc.msg,
        reason=(f"Lark refused this {ref.kind} (code {exc.code}: {exc.msg}) and the walk "
                "continued; larkdocio quotes Lark's own words and diagnoses no further."))


def _disclosure(misses) -> str:
    """The ``## Assets not fetched`` section — omitted entirely when nothing missed, so its
    absence is trustworthy."""
    lines = [MISS_HEADING, ""]
    for miss in misses:
        lines.append(f"- {miss.document} — {miss.kind} `{miss.token}`: {miss.reason}")
    return "\n".join(lines) + "\n"


def _domain_of(result) -> str:
    """The tenant host to fetch from: the first read child's own listing ``url``.

    Falls back to the library-wide default when the listing carried no url or it cannot be
    parsed — the fetch then either works or is disclosed as a miss, which is the same
    skip-loudly arm every other failure takes. Nothing here guesses at a tenant.
    """
    for outcome in result.reads:
        url = getattr(outcome.child, "url", None)
        if not url:
            continue
        try:
            return validate_download_url(url)[0]
        except Exception:  # noqa: BLE001 — an unparseable url is not this leg's error to raise
            continue
    return "larksuite.com"


def _default_fetcher(domain: str):
    """The real fetch seam: one READ-credential docx client, both of its asset methods.

    **No new API reach.** ``download_image`` is the Drive media download the docx reader's image
    leg already makes, and ``download_board_image`` is the whiteboard PNG export it already
    makes for a type-43 board; this leg reaches them from a second caller and nothing else. The
    client is built once per run, so N documents' assets ride one client and its throttle.
    """
    app_id, app_secret = get_read_credentials()
    client = Client(app_id, app_secret, domain)

    def fetch(kind: str, token: str, directory: str) -> str:
        if kind == BOARD:
            return client.download_board_image(token, directory)
        return client.download_image(token, directory)

    return fetch
