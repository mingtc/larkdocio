"""larkdocio.drive.manifest — the machine-readable projection of a folder read.

:func:`larkdocio.drive.render.render_folder` answers *what is in this folder?* for a **person**.
This module answers it for a **program**: one JSON-ready object with a row per walked child
carrying its **title, token, type and revision**, plus the walk's own disclosures. It is the
sidecar the ``folder --dump`` flag writes, and it is built to the conventions
``download --dump`` already established — same flag spelling, the same ``-o`` directory, and a
file named for the **token** rather than the title — because a second grammar for the same idea
is paid for by every reader of both.

Three rules govern it.

**Every walked child is a row.** The manifest inherits
:meth:`~larkdocio.drive.read.FolderRead.accounted`'s promise: a child that could not be read is
a row carrying its disclosure, never an absence. An absent row and a clean folder are
indistinguishable to a machine, which is exactly the failure mode this file exists to prevent.

**A revision is never fabricated.** Where the child's type exposes an anchor the read *already
held*, the row carries it; where it does not, the row says ``availability: "unavailable"`` and
gives the honest reason. There is no third state, no inference from a sibling, and no laundering
of *not known* into ``0`` — ``0`` is a revision a real spreadsheet and a real Base table can
both have. :data:`REVISION_SOURCES` states, per surface, what was measured to expose what, and
it ships **inside** the sidecar so a consumer reads it where it is working.

**It is a pure function of the read.** No clock, no environment, no filesystem, no dict
iteration order: two manifests of one :class:`~larkdocio.drive.read.FolderRead` are
byte-identical, the same discipline :func:`~larkdocio.drive.render.render_folder` is held to.

**What a change-detection ledger should key on.** A revision is the strong anchor but exists
only for children this run actually **read**. The listing itself carries ``modified_time`` for
**every** child at no extra call, and it is on every row — so a ledger deciding *what moved*
has an anchor for the whole folder, and a stronger one where the read supplied it.
"""
from larkdocio.drive.read import FOLDER, READ, SKIPPED, FolderRead

#: The two — and only two — words a row's ``revision.availability`` may take. A missing anchor
#: is spelled out; it never hides behind a null that could be read as a value.
REVISION_AVAILABLE = "available"
REVISION_UNAVAILABLE = "unavailable"

_LISTING_ANCHOR = (
    "The folder listing exposes no revision for any child, so the free per-child change anchor "
    "is modified_time on this row."
)

#: What each surface was **measured** to expose, and at what cost. Every entry is a fact about
#: shipped larkdocio code, not about the Lark API in general: the question this table answers is
#: *"what anchor does the read this walk already performed leave in larkdocio's hands?"* — not
#: *"what could some other call obtain?"*. No extra API call is ever made for a revision.
REVISION_SOURCES = {
    "docx": {
        "availability": REVISION_AVAILABLE,
        "anchor": "document.revision_id",
        "detail": (
            "The document's own revision_id, returned by the block read this walk already "
            "performed — so it costs no extra call. It advances by one per edit operation, "
            "which is what makes it a usable change anchor."
        ),
    },
    "sheets": {
        "availability": REVISION_AVAILABLE,
        "anchor": "properties.revision",
        "detail": (
            "The spreadsheet revision that rides the values reply the read already made — no "
            "extra call. It is spreadsheet-scoped, so the first tab reporting one answers for "
            "the document. Some spreadsheets report no revision at all; such a read is marked "
            "unavailable rather than reported as zero."
        ),
    },
    "base": {
        "availability": REVISION_UNAVAILABLE,
        "anchor": None,
        "detail": (
            "A Base's revision anchor is per-table, not per-document: there is no single number "
            "for a Base child, so none is offered here. Take larkdocio.base.read_base() for the "
            "per-table revisions. " + _LISTING_ANCHOR
        ),
    },
    "folder": {
        "availability": REVISION_UNAVAILABLE,
        "anchor": None,
        "detail": (
            "A folder is a container, not a document; it has no revision to report. Its "
            "children carry their own rows. " + _LISTING_ANCHOR
        ),
    },
    "file": {
        "availability": REVISION_UNAVAILABLE,
        "anchor": None,
        "detail": (
            "A raw uploaded file is disclosed, never read, so no anchor is obtained for it. "
            + _LISTING_ANCHOR
        ),
    },
}

_NOT_READ = (
    "This child was not read, so no revision anchor was obtained for it. " + _LISTING_ANCHOR
)

_READ_WITHOUT_ANCHOR = (
    "The read succeeded but the reply did not carry a revision, so none is reported — reporting "
    "zero would be indistinguishable from a real revision of zero. " + _LISTING_ANCHOR
)


def folder_manifest(result: FolderRead) -> dict:
    """Project one :class:`~larkdocio.drive.read.FolderRead` to the JSON-ready manifest.

    The returned object uses only built-in types, so ``json.dump`` needs no custom encoder — a
    sidecar a consumer must import this library to decode is not machine-readable.
    """
    return {
        "folder": {
            "token": result.root_token,
            "title": result.root_name.name,
            "title_disclosure": (
                None if result.root_name.resolved else result.root_name.disclosure),
        },
        "children": [_child_row(outcome) for outcome in result.outcomes],
        "counts": {
            "children": len(result.outcomes),
            "read": len(result.reads),
            "skipped": len(result.skips),
            "folders": len(result.folders),
        },
        "walk": _walk(result),
        "revision_sources": REVISION_SOURCES,
    }


def _child_row(outcome) -> dict:
    child = outcome.child
    return {
        # `title` is the consumer's word for it; the listing calls the same field `name`, and it
        # is carried through verbatim — never synthesised when Lark reported none.
        "title": child.name,
        "token": child.token,
        # Lark's OWN type word, untranslated (`sheet` / `bitable`), beside larkdocio's reader
        # word for the same child (`sheets` / `base`). Translating in place would make the
        # manifest disagree with the listing a consumer can fetch itself.
        "type": child.type,
        "surface": outcome.surface,
        "outcome": outcome.kind,
        # The walk is FLAT and nesting rides `path` + `depth` — `download --dump`'s flat
        # `blocks` list is the precedent, and a flat list is what a ledger diffs.
        "path": outcome.walked.path,
        "depth": outcome.walked.depth,
        "url": child.url,
        "parent_token": child.parent_token,
        "created_time": child.created_time,
        "modified_time": child.modified_time,
        "owner_id": child.owner_id,
        "revision": _revision(outcome),
        "skip": _skip(outcome),
    }


def _revision(outcome) -> dict:
    """The row's revision block — available with its value, or unavailable with the reason."""
    if outcome.kind == READ and outcome.revision is not None:
        source = REVISION_SOURCES.get(outcome.surface or "", {})
        return {
            "availability": REVISION_AVAILABLE,
            "value": outcome.revision,
            "anchor": source.get("anchor"),
            "detail": source.get("detail", ""),
        }

    if outcome.kind == READ:
        source = REVISION_SOURCES.get(outcome.surface or "", {})
        detail = (source["detail"] if source.get("availability") == REVISION_UNAVAILABLE
                  else _READ_WITHOUT_ANCHOR)
        return {"availability": REVISION_UNAVAILABLE, "value": None, "anchor": None,
                "detail": detail}

    if outcome.kind == FOLDER:
        return {"availability": REVISION_UNAVAILABLE, "value": None, "anchor": None,
                "detail": REVISION_SOURCES["folder"]["detail"]}

    return {"availability": REVISION_UNAVAILABLE, "value": None, "anchor": None,
            "detail": _NOT_READ}


def _skip(outcome):
    """A skipped child's disclosure, quoting Lark's own ``code``/``msg`` where there was one."""
    if outcome.kind != SKIPPED or outcome.skip is None:
        return None
    return {
        "mode": outcome.skip.mode,
        "reason": outcome.skip.reason,
        "code": outcome.skip.code,
        "msg": outcome.skip.msg,
    }


def _walk(result: FolderRead) -> dict:
    """The walk's own record — including everything it did **not** see. A truncated walk must
    never read as a complete folder, so ``complete`` is on the sidecar beside the disclosures
    that make it false."""
    walk = result.walk
    return {
        "complete": walk.complete,
        "listing_calls": walk.listing_calls,
        "max_depth_reached": walk.max_depth_reached,
        "truncations": [
            {
                "cap": truncation.cap,
                "limit": truncation.limit,
                "at_folder": truncation.at_folder,
                "at_path": truncation.at_path,
                "not_visited": list(truncation.not_visited),
                "describe": truncation.describe(),
            }
            for truncation in walk.truncations
        ],
        "cycles": [
            {"token": cycle.token, "path": cycle.path,
             "first_seen_path": cycle.first_seen_path, "note": cycle.note}
            for cycle in walk.cycles
        ],
        "refusals": [
            {"token": refusal.token, "path": refusal.path, "note": refusal.note}
            for refusal in walk.refusals
        ],
    }
