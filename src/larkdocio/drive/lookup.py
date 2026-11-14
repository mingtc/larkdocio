"""larkdocio.drive.lookup — is this name already in that folder?

**The question an automation asks on its second run, and could not ask before.** Uploading the
same file again does not replace the first one: it mints a **second file object with its own
token**, and the folder then lists two children whose names are byte-identical. Nothing about
that is refusable — Lark answers ``code:0`` — so the only way a caller can decide
*replace-or-skip* is to look first. This module is the looking.

**IT IS FACTS, NOT A POLICY.** :func:`match_children_by_name` and
:meth:`larkdocio.drive.client.DriveClient.find_children_by_name` return **what is there** — the
matching children with their tokens — and stop. Nothing here deletes, uploads, renames or
de-duplicates anything, and there is deliberately **no replace helper**: a library that trashed
somebody's file on the way to writing a new one would be destroying data as a convenience, with
no consent gate. A caller who wants replace has the tokens and calls
:meth:`larkdocio.drive.files_write.DriveFilesWriteClient.delete` themselves.

**A LOOK-THEN-UPLOAD IS NOT A LOCK.** Between the lookup and the upload another writer can put
the same name in the folder, and no route this library calls would refuse the second write. The
lookup narrows a race; it does not win one. It is offered as *what is there right now*, which is
exactly the honesty the same fence takes on the folder-create rung.

**WHAT IDENTITY THE API ACTUALLY AFFORDS — the fence, measured.** The folder listing carries
eight keys per child (:data:`IDENTITY_THE_LISTING_AFFORDS`) and the metadata query carries ten,
and **neither reports a size or a digest**. So a match here means *a child of that folder has
that exact name*, never *these are the same bytes*. A caller who must know whether the bytes
agree downloads the token and hashes it (``larkdocio.base.media.verify_round_trip`` is this
library's one definition of that); this module says so rather than implying an identity it
cannot see.

**The match is byte-identical.** No case folding, no whitespace trimming, no extension
normalising: Lark stores the name as it was sent, and a fold here would assert a collision rule
nobody measured.

**No new endpoint.** The lookup rides the folder listing that already ships
(``GET /open-apis/drive/v1/files``, paged to exhaustion by the shipped client), so it reaches
nothing new and asks for no scope of its own.
"""
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from larkdocio.drive.models import FolderChild, Truncation

#: The keys a folder listing reports per child — **measured**, 2026-08-15, on a folder the probe
#: created and swept, and captured under ``tests/captures/ld464-upload-identity/`` (in the source repository).
#: Sorted, so a re-measurement that adds or drops one is a visible diff.
IDENTITY_THE_LISTING_AFFORDS: Tuple[str, ...] = (
    "created_time", "modified_time", "name", "owner_id", "parent_token", "token", "type", "url",
)

#: What **neither** route reports, so neither is offered and neither is implied. The metadata
#: query (``metas/batch_query``, ``doc_type: file``) was measured alongside the listing and
#: carries no size either (an unpublished recording).
IDENTITY_NOT_AFFORDED: Tuple[str, ...] = ("size", "checksum", "digest")

#: **The one authoring of the duplicate-upload disclosure.** Quoted into the upload op's own
#: docstring, into the surface's ``capabilities()`` note and into the consumer guide, so the
#: three cannot drift apart. Written as the sentence a caller needs before their automation's
#: second run, not as a footnote.
DUPLICATE_UPLOAD_BEHAVIOUR = (
    "UPLOADING THE SAME NAME TWICE MAKES A SECOND FILE. An upload is not idempotent and there "
    "is no overwrite: the same name and the same bytes sent into the same folder again answer "
    "code:0 with a DISTINCT file token, and the folder then lists two children whose names are "
    "byte-identical. Every route that could have meant otherwise was tried and none did — five "
    "spellings of an extra upload_all form field (overwrite, duplicate_handling, "
    "conflict_strategy, mode, upsert), an ?overwrite=true query string, and an overwrite key on "
    "upload_prepare: all seven were ACCEPTED AND IGNORED, each minting another new token, on "
    "one tenant against the two upload endpoint families this library calls. So a duplicate is "
    "not refused, not de-duplicated and not warned about, and any automation that has re-run an "
    "upload has been creating a new object every time. THIS LIBRARY WILL NOT OVERWRITE FOR YOU: "
    "a delete-then-upload done on your behalf would destroy somebody's file as a convenience. "
    "CHECK FIRST INSTEAD: DriveClient.find_children_by_name(folder_token, name) lists the "
    "folder and hands back every child already carrying that name with its token, so a caller "
    "decides skip-or-replace and calls DriveFilesWriteClient.delete themselves if they mean "
    "replace. It is a collision CHECK, not a lock — another writer can add the same name "
    "between the look and the upload — and it can compare names only: neither the listing nor "
    "the metadata query reports a size or a digest, so identical-name never means identical "
    "bytes. Download the token and hash it if that is the question."
)


def match_children_by_name(children: Sequence[FolderChild], name: str
                           ) -> Tuple[FolderChild, ...]:
    """Every child of ``children`` whose ``name`` is **byte-identical** to ``name``.

    Pure, and reusable by a caller who already holds a listing — a walk, a manifest — so
    nothing has to make a second call to ask the same question.
    """
    return tuple(child for child in children if child.name == name)


@dataclass(frozen=True)
class FolderNameMatches:
    """What is already in a folder under one name — the facts, and how complete they are.

    ``matches`` are the listing's own rows, carried through untouched, so a caller reads the
    same fields Lark reported (:data:`IDENTITY_THE_LISTING_AFFORDS`) rather than a projection
    this library invented. ``listed`` is how many children were seen in total, which is what
    makes ``found is False`` legible: nothing matched **out of this many**.

    **``truncation`` is why ``complete`` exists.** A listing that hit the page budget is not
    evidence of absence, and an answer that quietly read as one would be the worst possible
    failure for a *check before you write* — so the cap is carried and
    :meth:`describe` says it out loud.
    """

    folder_token: str
    name: str
    matches: Tuple[FolderChild, ...] = ()
    listed: int = 0
    truncation: Optional[Truncation] = None

    @property
    def found(self) -> bool:
        """True iff at least one child already carries that exact name."""
        return bool(self.matches)

    @property
    def tokens(self) -> Tuple[str, ...]:
        """The matching children's tokens — what a caller passes to a delete if they mean
        replace."""
        return tuple(child.token for child in self.matches)

    @property
    def complete(self) -> bool:
        """True iff the whole folder was listed. False means **unknown**, never *absent*."""
        return self.truncation is None

    def describe(self) -> str:
        """One sentence a consumer can log or act on."""
        if self.found:
            head = (f"{len(self.matches)} child(ren) in folder {self.folder_token} already "
                    f"carry the name {self.name!r}: {', '.join(self.tokens)}. Uploading it "
                    f"again would make another one")
        else:
            head = (f"no child of folder {self.folder_token} carries the name {self.name!r} "
                    f"({self.listed} listed)")
        if self.complete:
            return head + ". Names only — no size or digest is reported by either route."
        return (head + f". THIS LISTING IS NOT COMPLETE: {self.truncation.describe()} "
                f"An unfinished listing is not evidence that the name is absent.")


__all__ = [
    "DUPLICATE_UPLOAD_BEHAVIOUR",
    "IDENTITY_NOT_AFFORDED",
    "IDENTITY_THE_LISTING_AFFORDS",
    "FolderNameMatches",
    "match_children_by_name",
]
