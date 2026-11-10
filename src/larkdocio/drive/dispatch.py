"""larkdocio.drive.dispatch — the child-``type`` → reader dispatcher (LD-325).

*Given one child of a folder, which reader would take it?* This module answers that and nothing
else. It is **pure and offline**:

* it **selects**, it does not fetch — every branch is decidable from the ``FolderChild`` the
  listing already returned, so nothing here makes an API call;
* it **names** the readers, it does not import them — a reader's import cost is real, and the
  dispatcher that runs over 35 children should not pay three readers' import cost to route them;
* it does not render, and it catches no reader failure — that is LD-326's per-child degradation
  contract, and splitting it across two modules would make neither honest.

**THE VOCABULARY SEAM (AC2).** Lark's Drive listing says ``sheet`` and ``bitable`` where
larkdocio's own URL layer (:data:`larkdocio.common.url.URL_TYPE_SURFACES`) says ``sheets`` and
``base``. The translation lives in **exactly one place** — :data:`SEAM` — and its guard (in the
source repository) pins it against *both* vocabularies read from real code, so a rename on either side
reddens rather than silently routing a spreadsheet to nothing. **The seam
is asserted-not-demonstrated:** the maintainer's real tree contained neither a spreadsheet nor a Base
(``bitable`` was seen in round 1's root listing, ``sheet`` in no capture at all), so the Sheets
and Base legs rest on the SDK's model and the listing — no live enumeration has ever dispatched
either end to end.

**THE SHORTCUT BRANCH (AC3) is SDK-modeled and UNOBSERVED.** Neither probe tree held a
``shortcut`` child (spike § VII.1), so this whole branch is built against
``ShortcutInfo{target_type, target_token}`` and never seen live. A shortcut resolves to its
target and **re-dispatches on the target's type**; a shortcut whose target is itself, or is
already in the walk's visited-set, is **disclosed** (:data:`CYCLE`) rather than followed — the
same visited-set discipline LD-324's walker carries, for the same reason.
"""
from dataclasses import dataclass
from typing import Callable, Optional

from larkdocio.drive.models import FolderChild

#: The outcome kinds — one per way a child can be routed.
READ = "read"          #: a reader is selected (docx / sheet / bitable)
RECURSE = "recurse"    #: a folder — LD-324's walker descends the same endpoint
RESOLVE = "resolve"    #: a shortcut — resolved to its target, then re-dispatched
NO_READER = "no-reader"  #: a ``file`` — disclosed by name, never read (AC4)
UNKNOWN = "unknown"    #: a type this dispatcher has never seen — disclosed, never guessed (AC5)
CYCLE = "cycle"        #: a shortcut that points at itself or into the visited-set (AC3)

#: **The vocabulary seam, in exactly one place.** Lark's word → the larkdocio surface name that
#: reads it. Each value is a key of :data:`~larkdocio.common.url.URL_TYPE_SURFACES`, so the
#: guard pins this translation against the surface vocabulary the URL layer actually ships.
SEAM = {"sheet": "sheets", "bitable": "base"}

#: The marker an unrecognised ``type`` is disclosed with — the reader's ``[Unsupported …]``
#: register (``larkdocio.blocks.diagram``'s ``[Unsupported Add-On block: {id}]``), never a
#: silent drop, never a crash, never a guess at which reader might work. Byte-form pinned by a
#: test so a future capture has something exact to replace.
UNKNOWN_TYPE_MARKER = "[Unsupported Drive child type: {child_type}]"


def unknown_marker(child_type: Optional[str]) -> str:
    return UNKNOWN_TYPE_MARKER.format(child_type=child_type if child_type is not None
                                      else "unknown")


@dataclass(frozen=True)
class _Branch:
    """One dispatch branch: what it does, and — when it reads — which surface, named."""

    kind: str
    surface: Optional[str] = None
    #: A dotted reference to the reader this surface uses, **named not imported** (AC7).
    reader: Optional[str] = None
    reason: Optional[str] = None


#: R4 scopes what THE WALK does, not what the library HAS. R1 lists a ``file`` child and fetches
#: no bytes for it (AC4) — and the reason a consumer reads must say which of those two it is,
#: because the sentence that lived here until LD-474 said the download leg did not exist and it
#: does. The *reason* the walk does not fetch stands unchanged; only the false absence is gone.
_FILE_REASON = (
    "larkdocio ships no reader that turns raw uploaded bytes into Markdown, so this walk "
    "listed the file and read nothing from it. THE BYTES THEMSELVES ARE FETCHABLE: "
    "DriveFilesWriteClient.download(file_token) "
    "(larkdocio.drive.files_write, GET /drive/v1/files/:file_token/download) returns them in "
    "memory, unexamined, and they are hash-verifiable — this walk simply does not call it")

#: **The dispatch table — one branch per Lark child type, and the guarded half of the surface.**
#: Its keys are exactly Lark's six child types; the Drive matrix guard (in the source repository) holds
#: it bidirectional against the capability matrix's dispatch rows from the moment this dict exists.
DISPATCH = {
    "docx": _Branch(READ, surface="docx",
                    reader="larkdocio.read.download.handle_download_command"),
    "sheet": _Branch(READ, surface=SEAM["sheet"],
                     reader="larkdocio.sheets.SheetsReadClient"),
    "bitable": _Branch(READ, surface=SEAM["bitable"],
                       reader="larkdocio.base.read_base_markdown"),
    "folder": _Branch(RECURSE, surface="drive",
                      reader="larkdocio.drive.walk.walk_folder"),
    "shortcut": _Branch(RESOLVE),
    "file": _Branch(NO_READER, reason=_FILE_REASON),
}


@dataclass(frozen=True)
class DispatchOutcome:
    """What the dispatcher decided for one child — a *selection*, never a fetched result."""

    child_type: Optional[str]
    kind: str
    surface: Optional[str] = None
    reader: Optional[str] = None
    url: Optional[str] = None
    token: Optional[str] = None
    name: Optional[str] = None
    reason: Optional[str] = None
    #: For a resolved :data:`RESOLVE`: the outcome of re-dispatching on the target's type.
    target: Optional["DispatchOutcome"] = None


def dispatch(child: FolderChild, *, seen=None,
             resolve: Optional[Callable[[str], Optional[FolderChild]]] = None
             ) -> DispatchOutcome:
    """Select the outcome for one ``child``. Pure, offline, no reader imported.

    ``seen`` is LD-324's visited-set (a set of tokens); a shortcut whose target is already in it
    — or is the shortcut itself — is disclosed as a :data:`CYCLE` rather than followed.
    ``resolve`` is an **optional** caller-supplied lookup (``token -> FolderChild``) used only to
    follow a shortcut *chain*; the dispatcher never fetches, so without it a shortcut is routed
    on the ``target_type`` its ``shortcut_info`` already carries.
    """
    branch = DISPATCH.get(child.type)
    if branch is None:
        return DispatchOutcome(
            child_type=child.type, kind=UNKNOWN, token=child.token, name=child.name,
            reason=unknown_marker(child.type))
    if branch.kind == RESOLVE:
        return _resolve_shortcut(child, seen=seen, resolve=resolve)
    return DispatchOutcome(
        child_type=child.type, kind=branch.kind, surface=branch.surface,
        reader=branch.reader, url=child.url, token=child.token, name=child.name,
        reason=branch.reason)


def _resolve_shortcut(child, *, seen, resolve) -> DispatchOutcome:
    seen = set(seen) if seen else set()
    info = child.shortcut_info or {}
    target_type = info.get("target_type")
    target_token = info.get("target_token")

    if target_token is None:
        return DispatchOutcome(
            child_type="shortcut", kind=NO_READER, token=child.token, name=child.name,
            reason="a shortcut with no target_token — disclosed, not followed")

    if target_token == child.token or target_token in seen:
        return DispatchOutcome(
            child_type="shortcut", kind=CYCLE, token=child.token, name=child.name,
            reason=(f"this shortcut's target {target_token!r} was already visited in this "
                    "walk (or is the shortcut itself), so it is disclosed rather than "
                    "followed — a cycle, never a loop"))

    seen |= {child.token, target_token}
    resolved = resolve(target_token) if resolve is not None else None
    target = resolved if resolved is not None else FolderChild(
        token=target_token, type=target_type, name=child.name, url=child.url)
    return DispatchOutcome(
        child_type="shortcut", kind=RESOLVE, token=child.token, name=child.name,
        target=dispatch(target, seen=seen, resolve=resolve))
