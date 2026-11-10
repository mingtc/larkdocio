"""larkdocio.write.comments — the whole-document comment ops (LD-202), and their evidence.

Two write ops on the comment family, registered in the one op registry
(:data:`larkdocio.write.ops.OPS`) so they ride the same plan gate, whole-document
compare-and-swap and apply-log as every other docx write:

* **create** a whole-document comment — the one comment creation Lark's API performs;
* **remove** a comment thread the calling application authored and is alone in — deleting
  every reply, which cascades to the comment.

**Why this module is mostly prose.** The two ops are small; what is *not* small is the set
of things the API will cheerfully appear to do and not actually do. Every refusal below
quotes a **committed capture** rather than a recollection, because the sharp failure mode
here is a success code that means nothing. The captures live in the source repository, so the paths
below name the provenance of each finding rather than a document to open:

* the 2026-07-29 comments probe, § Q1a (its write-up was retired from the dev repo on 2026-09-18) —
  anchored creation. Eighteen candidate
  ``create_v2`` routes are absent against a calibrated discriminator with two controls, and
  the v1 route that *does* exist **accepts** ``anchor`` / ``quote`` / ``is_whole:false``,
  answers ``code 0``, and creates a plain whole-document comment. Six shapes were tried,
  including a **bogus block id** and a **quote that does not occur in the document**; not
  one was an error, and the read-back showed six whole-document comments.
* the same probe, § Q1b, with ``tests/captures/comments-probe-round2-captures/14-demo.json`` — a
  spreadsheet is rejected at the ``file_type`` **enum** (``99992402``), for ``sheet`` /
  ``sheets`` / ``spreadsheet`` and for the whole-file attempt alike, while a comment
  **read** on the same spreadsheet answers ``code 0``.
* ``tests/captures/comments-probe-round2-captures/16-delete-arm.json`` — ``DELETE …/comments/{cid}``
  is not a route (a gateway-level, **non-JSON** ``404 page not found``), and
  ``DELETE …/replies/{rid}`` on a reply the caller did not write is HTTP 403 /
  ``1069303 "forbidden"``. The capture also records *why* the spreadsheet arm was not spent:
  ``1069303`` is "an OWNERSHIP-shaped refusal — it is about who the caller is, not about
  which file type it named."

**The one invariant worth stating in one sentence.** A removal reads the whole live thread
and judges it **before** issuing any delete, so a thread this application does not solely
own is not partly deleted — it is not touched at all. A half-deleted thread misrepresents
the conversation and cannot be undone, which is worse than refusing.
"""
from typing import Optional

from larkdocio.errors import LarkAPIError, LarkRateLimitError
from larkdocio.write.model import (
    ApplyLogEntry,
    CommentThread,
    CreateCommentRequest,
    Refusal,
    RemoveCommentRequest,
    WHOLE_DOCUMENT,
)
from larkdocio.write.model.requests import COMMENT_FILE_TYPES
from larkdocio.write.preview import PlanEntry

# --------------------------------------------------------------------------- #
# The captured evidence. Quoted, never paraphrased — a refusal detail that      #
# summarized these would be a second, unverifiable account of Lark's behaviour. #
# --------------------------------------------------------------------------- #

#: Why an anchored comment cannot be created, in the API's own results. Quoted into every
#: ``comment-anchor-not-creatable`` refusal, so a consumer reading one refusal has the whole
#: finding rather than an assertion.
ANCHORED_CREATE_ABSENT_EVIDENCE = (
    "Lark has no anchored-comment create. 18 candidate create_v2 routes answer 404 against "
    "a discriminator calibrated on two controls (an existing route answers JSON with a Lark "
    "code; the drive/v2 namespace is routable), and the v1 route that DOES exist accepts "
    "anchor / quote / is_whole:false, answers code 0, and silently creates a plain "
    "whole-document comment — six shapes were tried, including a bogus block id "
    "('doxcnBOGUSBLOCKID000000000') and a quote absent from the document, and every one "
    "returned code 0 with a read-back of is_whole=true, quote=null. So a request that "
    "carried an anchor through would report an anchored comment that was never created."
)

#: The two things that DO work, named in the same refusal — a refusal that only says no has
#: failed the consumer (LD-131).
ANCHORED_CREATE_ALTERNATIVES = (
    "What works: create a whole-document comment (drop the anchoring field), or READ the "
    "passage anchors that already exist — larkdocio.comments.comments(token) joins each "
    "comment to the block it is anchored to, including anchors a human created in the UI."
)

#: Lark's own rejection of a comment create on a spreadsheet, verbatim from
#: ``14-demo.json``'s ``sheet_attempts``. The ``description`` is the server's string,
#: including its own "file_type is optional" phrasing.
SHEETS_CREATE_REJECTED_EVIDENCE = (
    "Lark rejects a comment create on a spreadsheet at the file_type ENUM, not at the "
    "content: HTTP 400, code 99992402, msg \"field validation failed\", with "
    "field_violations naming file_type and printing its options — "
    "'file_type is optional, options: [doc,docx]'. Identical for 'sheet', 'sheets' and "
    "'spreadsheet', and identical for a whole-FILE comment attempt, so sheets comment "
    "creation does not exist at any granularity. Sheets comment READING is a different "
    "answer and works: GET …/comments?file_type=sheet returns code 0 on the same "
    "spreadsheet — use larkdocio.comments.comments(token, file_type='sheet')."
)

#: What a consumer must know about a created comment's authorship **before** creating one
#: (AC6: disclosed, not discovered). Carried in the plan as a preview note and restated in
#: the guide and in ``capabilities()``.
BOT_AUTHORSHIP_DISCLOSURE = (
    "This comment will be authored as your APPLICATION's own bot identity, not as a person: "
    "a bare open_id (ou_…) with no resolvable display name — the directory answers 41050 "
    "\"no user authority\" for it on these scopes, and the payload carries no "
    "human-vs-application flag, so nothing can render it as a name. It appears in the "
    "document's COMMENTS PANEL as a whole-document comment: it highlights no passage, "
    "because Lark's API cannot anchor one. The comment_id and this author id are both "
    "reported in the apply-log, and the author id is what a later removal is judged against."
)

#: :attr:`~larkdocio.write.preview.PlanEntry.preview_note` kind carrying
#: :data:`BOT_AUTHORSHIP_DISCLOSURE` on every resolved comment-create entry. A *note*, not a
#: refusal: the op proceeds, and this is what an approver needs to have read first.
NOTE_KIND_COMMENT_AUTHORSHIP = "comment-lands-as-the-app-bot"

#: Why a removal reads the thread before deleting anything. Quoted into the ownership
#: refusal so the consumer sees the boundary and the reason for it together.
NO_PARTIAL_DELETE_DOCTRINE = (
    "Nothing was deleted. Removal is whole-thread or nothing: a comment has no delete "
    "endpoint (DELETE …/comments/{comment_id} is not a route — it answers a non-JSON 404), "
    "so a comment is removed by deleting every reply, and the API permits that only for "
    "replies the caller wrote (HTTP 403, code 1069303 \"forbidden\" otherwise — an "
    "ownership refusal about who is asking). Deleting the removable part of a mixed thread "
    "would leave it half-deleted, misrepresenting the conversation with no way back."
)


# --------------------------------------------------------------------------- #
# resolve — plan-time, offline, and callless by construction                     #
# --------------------------------------------------------------------------- #

def _resolve_comment_create(request: CreateCommentRequest, root):
    """Resolve a comment create: :data:`WHOLE_DOCUMENT`, or a typed refusal.

    ``root`` is accepted and **ignored**, deliberately: a whole-document comment points at
    the file, so there is no block to locate and nothing about the parsed tree can make this
    request more or less valid. (That is also why a comment op can be planned against a
    document whose tree was never parsed.)

    The two refusals are decided **here**, at plan time, where :func:`dry_run` is
    structurally incapable of a network call — so a caller asking for something the API does
    not have pays nothing and is told the truth, rather than receiving a ``code 0`` for a
    comment that is not what they asked for.
    """
    if request.file_type not in COMMENT_FILE_TYPES:
        return Refusal.comment_surface_unsupported(
            f"a comment cannot be created on file_type={request.file_type!r}. "
            f"{SHEETS_CREATE_REJECTED_EVIDENCE} Accepted here: "
            f"{' / '.join(repr(t) for t in COMMENT_FILE_TYPES)}."
        )
    intent = request.anchoring_intent
    if intent is not None:
        return Refusal.comment_anchor_not_creatable(
            f"this request asked to anchor the comment ({intent}), and no such creation "
            f"exists. {ANCHORED_CREATE_ABSENT_EVIDENCE} {ANCHORED_CREATE_ALTERNATIVES}"
        )
    return WHOLE_DOCUMENT


def _resolve_comment_remove(request: RemoveCommentRequest, root):
    """Resolve a comment removal: the thread anchor, always.

    ``root`` is ignored for the same reason as above — and there is a second reason here
    worth naming: sole ownership of a thread is a **live** fact, so it cannot be settled
    offline. The plan therefore previews *what would be attempted*, and the ownership
    decision is taken at apply time against the live thread (the ``stale-anchor``
    precedent), immediately before — and as the precondition of — any delete.
    """
    return request.target


# --------------------------------------------------------------------------- #
# preview — the plan entry, with the authorship disclosure                      #
# --------------------------------------------------------------------------- #

def _preview_comment_create(request: CreateCommentRequest, result) -> PlanEntry:
    """Preview a comment create — resolved (with the authorship note) or refused."""
    if isinstance(result, Refusal):
        return PlanEntry.comment_create_refused(anchor=WHOLE_DOCUMENT, request=request,
                                                refusal=result)
    return PlanEntry.comment_create_resolved(anchor=result, request=request)


def _preview_comment_remove(request: RemoveCommentRequest, result) -> PlanEntry:
    """Preview a comment removal — resolved (the attempt) or refused."""
    if isinstance(result, Refusal):
        return PlanEntry.comment_remove_refused(anchor=request.target, request=request,
                                                refusal=result)
    return PlanEntry.comment_remove_resolved(anchor=result, request=request)


# --------------------------------------------------------------------------- #
# apply — the two live paths                                                     #
# --------------------------------------------------------------------------- #

def _lark_denial(exc: LarkAPIError) -> str:
    """Lark's own answer, in its own numbers — the phrase every comment refusal ends with.

    A refusal that said "the server refused" would strip exactly the part a consumer can act
    on (LD-131). ``1069303`` means an ownership problem, ``1069307`` means the thing is gone,
    ``1069302`` means the content was rejected — different repairs, and only the code
    distinguishes them.
    """
    return f"Lark said code={exc.code!r} msg={exc.msg!r}."


def _apply_comment_create(entry, client, document_id: str) -> ApplyLogEntry:
    """Create the whole-document comment; log its ``comment_id`` and its author id.

    The body carries ``reply_list`` and nothing else — no ``anchor``, no ``quote``, no
    ``is_whole``, not even the ``is_whole=True`` a caller may have passed (that field was a
    request-level statement of intent, and the endpoint's treatment of it on the wire is
    precisely what makes it untrustable).

    A Lark error becomes a **typed refusal carrying Lark's own code and message** rather than
    an exception escaping mid-batch: the apply-log stays 1:1 with the plan, and the entries
    after this one still get their disposition. A rate-limit error is re-raised — throttling
    is not a refusal, and telling a consumer their comment was rejected when the server
    merely asked them to slow down would be a lie (the ``_live_or_stale`` doctrine).
    """
    comment = entry.comment
    try:
        data = client.create_whole_document_comment(
            document_id, comment.text, file_type=comment.file_type)
    except LarkRateLimitError:
        raise
    except LarkAPIError as exc:
        return ApplyLogEntry.refused(
            anchor=entry.anchor,
            refusal=Refusal.comment_surface_unsupported(
                f"the comment was not created on {document_id!r}. {_lark_denial(exc)} "
                f"No comment exists as a result of this entry."
            ),
        )
    return ApplyLogEntry.commented(
        anchor=entry.anchor,
        comment_record={
            "comment_id": data.get("comment_id"),
            # The author id the create response reports: the application's own bot open_id,
            # and the id a later removal must be able to state. Reported rather than looked
            # up — see BOT_AUTHORSHIP_DISCLOSURE for why looking it up is not possible.
            "author_id": data.get("user_id"),
            "reply_ids": [r.get("reply_id")
                          for r in ((data.get("reply_list") or {}).get("replies") or ())],
            "scope": "whole-document",
            "file_type": comment.file_type,
        },
    )


def _foreign_authors(replies, author_id: str):
    """The reply ids and author ids in ``replies`` that are **not** ``author_id``'s.

    Empty ⇒ the thread is solely this application's and the removal may proceed. A reply with
    no ``user_id`` at all counts as foreign: an unattributed reply is not evidence of
    ownership, and treating an absent id as "probably ours" is the guess this library does
    not make.
    """
    return [(r.get("reply_id"), r.get("user_id")) for r in replies
            if r.get("user_id") != author_id]


def _apply_comment_remove(entry, client, document_id: str) -> ApplyLogEntry:
    """Remove a comment thread the application solely owns — read, judge, then delete.

    The order is the contract:

    1. **read** the live thread's replies (one call);
    2. **judge** it — every reply must be ``author_id``'s. A thread that is empty or gone
       refuses ``not-found``; a thread carrying anyone else's reply refuses
       ``comment-thread-not-solely-authored``. Both refuse with **zero deletes issued**, so
       the thread is left exactly as it was;
    3. **delete** every reply, oldest first. The comment goes with the last one.

    Step 2 is what makes AC5 structural rather than careful: because the decision is taken
    before the first delete, and because every reply is by the same author (so the API judges
    every delete identically), there is no code path that removes some replies and stops.
    The one thing a pre-check cannot rule out is the server failing partway through; that
    cannot be undone, so it is **recorded** — the refusal carries the ids that did go, since
    silence about a partial removal would be the real failure.
    """
    comment = entry.comment
    comment_id = comment.comment_id
    try:
        replies = client.list_comment_replies(
            document_id, comment_id, file_type=comment.file_type)
    except LarkRateLimitError:
        raise
    except LarkAPIError as exc:
        return ApplyLogEntry.refused(
            anchor=entry.anchor,
            refusal=Refusal.comment_thread_not_found(
                f"comment_id {comment_id!r} could not be read on {document_id!r}, so its "
                f"replies cannot be removed — it may already be gone (code 1069307 "
                f"\"not exist\" is the shape a removed comment answers with), or belong to "
                f"another file. {_lark_denial(exc)} Nothing was deleted."
            ),
        )

    if not replies:
        return ApplyLogEntry.refused(
            anchor=entry.anchor,
            refusal=Refusal.comment_thread_not_found(
                f"comment_id {comment_id!r} has no replies on {document_id!r}, so there is "
                f"nothing to remove and nothing was removed. A comment's content IS its "
                f"replies, so an empty thread is a comment that is already gone — reported "
                f"as a refusal rather than as a removal this run did not perform."
            ),
        )

    foreign = _foreign_authors(replies, comment.author_id)
    if foreign:
        named = ", ".join(f"reply {rid!r} by {uid!r}" for rid, uid in foreign)
        return ApplyLogEntry.refused(
            anchor=entry.anchor,
            refusal=Refusal.comment_thread_not_solely_authored(
                f"comment_id {comment_id!r} is not a thread author_id "
                f"{comment.author_id!r} is alone in: {named}. {NO_PARTIAL_DELETE_DOCTRINE}"
            ),
        )

    removed = []
    for reply in replies:
        reply_id = reply.get("reply_id")
        try:
            client.delete_comment_reply(
                document_id, comment_id, reply_id, file_type=comment.file_type)
        except LarkRateLimitError:
            raise
        except LarkAPIError as exc:
            # The one case the pre-check cannot make impossible. Irreversible, so it is
            # named: which replies went, which one failed, and Lark's own answer.
            return ApplyLogEntry.refused(
                anchor=entry.anchor,
                refusal=Refusal.comment_thread_not_solely_authored(
                    f"removing comment_id {comment_id!r} stopped at reply {reply_id!r}: "
                    f"{_lark_denial(exc)} The replies already deleted are listed in this "
                    f"entry's comment_record and CANNOT be restored — the thread is now "
                    f"partial. Re-read the thread before deciding what to do next."
                ),
                comment_record={"comment_id": comment_id, "removed_reply_ids": removed,
                                "failed_reply_id": reply_id, "complete": False},
            )
        removed.append(reply_id)

    return ApplyLogEntry.comment_removed(
        anchor=entry.anchor,
        comment_record={"comment_id": comment_id, "removed_reply_ids": removed,
                        "author_id": comment.author_id, "complete": True},
    )


# --------------------------------------------------------------------------- #
# serialize / deserialize — the op's own wire fields                             #
# --------------------------------------------------------------------------- #

def _serialize_comment_create(entry) -> dict:
    d: dict = {"comment": entry.comment.to_dict()}
    if not entry.is_resolved:
        d["refusal"] = entry.refusal.to_dict() if entry.refusal else None
    return d


def _deserialize_comment_create(anchor, d, resolved) -> PlanEntry:
    request = CreateCommentRequest.from_dict(d["comment"])
    if resolved:
        return PlanEntry.comment_create_resolved(anchor=anchor, request=request)
    return PlanEntry.comment_create_refused(
        anchor=anchor, request=request, refusal=Refusal.from_dict(d["refusal"]))


def _serialize_comment_remove(entry) -> dict:
    d: dict = {"comment": entry.comment.to_dict()}
    if not entry.is_resolved:
        d["refusal"] = entry.refusal.to_dict() if entry.refusal else None
    return d


def _deserialize_comment_remove(anchor, d, resolved) -> PlanEntry:
    request = RemoveCommentRequest.from_dict(d["comment"])
    if resolved:
        return PlanEntry.comment_remove_resolved(anchor=anchor, request=request)
    return PlanEntry.comment_remove_refused(
        anchor=anchor, request=request, refusal=Refusal.from_dict(d["refusal"]))
