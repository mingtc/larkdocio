"""The comments read: one entry point, the anchor join, and the disclosures it owes.

:func:`comments` is the whole public surface. Given a file token it returns every comment on
the file; given the node tree a document read produced, it instead resolves the review
anchors that tree already carries and lets a caller go from one block — or one run of styled
text inside a block — to the comments on it.

**Two shapes of read, one result type.** Without a tree the read walks the comment list to
exhaustion. With a tree it collects the anchor ids off the nodes and fetches exactly those,
in one batch, de-duplicated at the request (the ids are the API's own data, so the model
keeps them as given and only the *query* is normalized). A tree carrying no anchors at all
costs **no** API call: there is nothing to ask about.

**A read says which of the two shapes it was, and a scoped read never claims completeness.**
The two shapes do not answer the same question, and conflating them is how a caller ends up
reporting 71% of a review as all of it: the whole-list read is the file's comments, while the
anchor-scoped read is *the comments the anchors on one parsed tree point at*. A comment
attached to the **whole document** carries no anchor, so it can **never** appear in a scoped
read — and a comment anchored anywhere the tree did not carry is absent too.
:attr:`CommentsRead.completeness` records which shape produced the result and
:attr:`CommentsRead.disclosure` derives its wording from it, so the scoped read cannot be
relayed as the file's whole comment list. Scoping is worth asking for in exactly one case,
which is the reason it exists: a tree with **no** anchors costs **no** API call. On a tree that
does carry anchors it costs the same single call the whole-list read costs, and returns less.

**An anchor that resolves to nothing is listed, not discarded.** A comment may be removed
between the moment a document is read and the moment its review is read — an ordinary race,
not a caller error. Failing the whole read over it would let one stale anchor hide every
other reviewer's words, and quietly leaving it out would understate the review. So such ids
appear in :attr:`CommentsRead.missing_ids`, and :attr:`CommentsRead.notes` says why.

**Failure is disclosed, not smoothed over.** If the comments read fails, the document read is
unaffected — comments are a separate call — and the result says the comment knowledge is
**unavailable**, with the code and what it means. It does **not** come back as an empty list:
"there are no comments" and "I could not find out" are different answers, and a note that
lies is worse than no note. :attr:`CommentsRead.available` is the discriminator, and an
available read that genuinely found nothing is a distinct, ordinary outcome.

**What is deliberately not here: the reverse join.** The API offers a relation field intended
to map a comment back to the block it is attached to. It cannot be relied on and is not
implemented — the reason is recorded verbatim in :data:`REVERSE_JOIN_NOTE`. The direction
that *is* implemented is the other one, and it needs no such field: the document's own nodes
carry their anchor ids, so block-to-comments is a local lookup.
"""
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from larkdocio.comments.client import CommentsReadClient
from larkdocio.comments.models import Comment, CommentReply
from larkdocio.errors import LarkAPIError

#: The file type to read comments on a document. Also the API's default.
FILE_TYPE_DOCX = "docx"
#: The file type to read comments on a spreadsheet. Accepted for reads — see
#: :data:`SHEETS_READ_ACCEPTED_CREATE_REJECTED_NOTE`.
FILE_TYPE_SHEET = "sheet"
#: The file type to read comments on a Base. Accepted for reads, and **only** for reads —
#: see :data:`BASE_COMMENT_WRITE_REFUSED_NOTE`.
FILE_TYPE_BITABLE = "bitable"

#: The response codes this surface has actually seen from the comment family, each with what
#: it means in practice. Used to explain an unavailable read in words rather than a number.
#: Codes outside this table are reported with their number and the server's own message.
COMMENT_ERROR_CODES: Dict[int, str] = {
    1069301: (
        "the comment could not be resolved as requested — most often because it no longer "
        "exists"
    ),
    1069302: "the reply content was empty",
    1069304: "comments are not available for this file — it may have been deleted",
    1069307: (
        "the comment or file does not exist for this request — check the token and that the "
        "file type matches it"
    ),
    9499: (
        "one of the comment ids was rejected as malformed, which fails the whole batch — no "
        "comment in the batch was returned"
    ),
    41050: (
        "the identity lookup was denied on this application's scopes — comment authors are "
        "therefore reported as raw ids"
    ),
    99992402: (
        "the file type sent with the request is not one this endpoint accepts for that "
        "operation"
    ),
}

#: Why this surface ships no comment-to-block mapping. Stated in full because "unverified"
#: without the reason is indistinguishable from "we did not get round to it".
REVERSE_JOIN_NOTE = (
    "Mapping a comment back to the block it is attached to is NOT implemented and is NOT "
    "claimed to work. The relation field the API offers for it comes back empty for "
    "whole-file comments, and a comment attached to a passage cannot be created through the "
    "API at all — so there was no payload against which such a mapping could be verified, "
    "and an unverified join is not shipped. Go the other way instead: the document reader "
    "records each block's and each styled run's own comment anchors, so reading a document "
    "and passing its node tree to this surface gives you block-to-comments directly, with "
    "no reliance on that field."
)

#: The one consequence that makes block identity matter to a person rather than to a program,
#: authored HERE — beside :meth:`CommentIndex.for_node`, the join that proves it — and quoted
#: verbatim by every shipped document that warns a block id will not survive an edit.
#: ``GUIDE.md`` and ``write/README.md`` are static packaged documents and cannot import a
#: constant, so the projection is a **guarded literal**: this is the single authored source,
#: and the suite (in the source repository) pins each shipped copy against it byte-identically.
BLOCK_ID_COMMENT_ANCHOR_CONSEQUENCE = (
    "Block ids are what comments anchor to, so re-creating a block orphans every review "
    "comment left on it — the conversation is not moved, it is stranded, and nothing in the "
    "document says so afterwards. This library ships the join that shows you which comments "
    "are at stake before you decide: `review.for_node(block)` answers with what reviewers "
    "said about that exact block."
)

#: The spreadsheet asymmetry, disclosed because building on the read without knowing it
#: leads straight into a wall.
SHEETS_READ_ACCEPTED_CREATE_REJECTED_NOTE = (
    "Reading comments on a spreadsheet is accepted by the API; CREATING one on a "
    "spreadsheet is refused outright — the endpoint's file-type list admits documents only. "
    "So a spreadsheet's comments can be read but not authored through this API at any "
    "granularity, including a whole-file comment."
)

#: The spreadsheet anchoring disclosure. A cell-looking quote is text, not a location.
SHEETS_NO_CELL_ANCHOR_NOTE = (
    "A spreadsheet comment carries no structured cell reference. Its quoted text is often "
    "just a cell label such as C3, and the API itself treats that text as a weak match — so "
    "this surface reports the quote verbatim and never presents a spreadsheet comment as "
    "attached to a cell. Treat the quote as a hint for a human, not as a coordinate."
)

#: The Base asymmetry, and the one thing a caller most needs to know before building on this
#: file type: the read works, the write does not, and the refusal is the server's own.
BASE_COMMENT_WRITE_REFUSED_NOTE = (
    "Reading comments on a Base is accepted by the API; CREATING one is refused by the "
    "server itself — the create endpoint answers a field-validation failure naming its own "
    "file-type list, [doc, docx], which does not include bitable. There is no record-level "
    "or table-level comment route either: those paths are not part of the API and answer "
    "with the gateway's own not-found. So a Base's comments can be read but not authored "
    "through this API at any granularity, including a comment on the Base as a whole."
)

#: How a Base comment says which row it belongs to — and what it means when it does not.
BASE_RECORD_ATTRIBUTION_NOTE = (
    "A Base comment written against a row carries the record it was written against, plus "
    "the table and the view the reviewer had open. It is reported as structured data on the "
    "thread and on each reply, so no consumer has to parse it back out of a string. A thread "
    "carrying none is a comment on the Base as a whole and is reported as file-level. No row "
    "is ever attached by inference, and every thread reaches you either way."
)

#: The quote disclosure for a Base, the counterpart of the spreadsheet one.
BASE_QUOTE_IS_NOT_AN_ANCHOR_NOTE = (
    "The quoted text on a Base comment is the row label the server echoed back, not a "
    "structural anchor. Use the reported record instead: that is the identifier the rest of "
    "this library reads a Base's rows by."
)

#: Disclosed whenever some requested anchors resolved to nothing.
MISSING_IDS_NOTE = (
    "Some review anchors in the document resolved to no comment. That normally means the "
    "comment was removed after the document was read. They are listed rather than dropped, "
    "so the count of anchors and the count of comments can be reconciled."
)

#: :attr:`CommentsRead.completeness` when the file's WHOLE comment list was read — nothing on
#: the file is hidden from this result.
COMPLETENESS_COMPLETE = "complete"
#: :attr:`CommentsRead.completeness` when the read was SCOPED to the review anchors a parsed
#: document tree carried. Not a synonym for complete and not a failure: a legitimate, cheaper
#: read that answers a narrower question and cannot report what has no anchor.
COMPLETENESS_ANCHOR_SCOPED = "anchor-scoped"
#: :attr:`CommentsRead.completeness` when the read failed. Nothing is known either way.
COMPLETENESS_UNAVAILABLE = "unavailable"

#: Disclosed on every anchor-scoped read. The direction :data:`MISSING_IDS_NOTE` never
#: covered: a comment the read could not have returned because nothing pointed at it.
ANCHOR_SCOPED_NOTE = (
    "This read was SCOPED to the review anchors the document tree carried, so it is NOT the "
    "file's whole comment list and may hold fewer comments than the file does. A comment "
    "attached to the whole document carries no anchor and can never appear in a scoped read; "
    "a comment anchored anywhere this tree did not carry is absent too. Read the whole list by "
    "passing no tree — on a document that has anchors that costs the same single API call, and "
    "the per-block lookup works on its result just as well."
)

#: Disclosed on a whole-list read that found comments no anchor can reach.
UNANCHORED_IDS_NOTE = (
    "Some comments in this result are attached to the WHOLE document rather than to a passage. "
    "They carry no review anchor, so no anchor-scoped read can return them and no block will "
    "ever point at them — they are listed in unanchored_ids, and a review summary that walks "
    "blocks alone would omit them."
)

#: Disclosed whenever a reply in the result carries an image. The text is then not the whole
#: of what was said, and a report built from text alone would omit part of it silently.
IMAGE_REPLIES_NOTE = (
    "Some replies in this result carry IMAGES. Their file tokens are on each reply as "
    "image_tokens (and per thread as the comment's own image_tokens); the reply's text does "
    "NOT include them, because the payload gives them no position in the sentence. So text "
    "alone is not the whole of what those reviewers said."
)

#: Disclosed on any read that found comments. Reactions are not modelled because the API does
#: not report them — see :mod:`larkdocio.comments.models`.
REACTIONS_NOT_MODELLED_NOTE = (
    "Reactions on a comment — a 'like' and its kin — are NOT read: the comment endpoints "
    "report no reaction field at all, so nothing here can tell a comment that was liked from "
    "one that was not. Their absence from this result is not evidence that there are none."
)

#: Disclosed whenever the comments read failed. The document read is untouched by it.
UNAVAILABLE_NOTE = (
    "The comments could not be read, so this result carries NO comment knowledge — it is "
    "not a report that the file has no comments. The document's own content is unaffected."
)


# --------------------------------------------------------------------------- #
# Anchor collection — the ids a parsed document already carries.                 #
# --------------------------------------------------------------------------- #

def _child_sequences(node) -> List[Sequence]:
    """Every ordered child sequence a node owns, across the container shapes.

    Most containers own one ``children`` list; a table owns ``cells``; a grid owns one list
    per entry of ``columns``. Read by attribute rather than by node class so a container
    added to the model is walked here without a change.
    """
    out: List[Sequence] = []
    for name in ("children", "cells"):
        seq = getattr(node, name, None)
        if isinstance(seq, list):
            out.append(seq)
    columns = getattr(node, "columns", None)
    if isinstance(columns, list):
        for column in columns:
            if isinstance(column, list):
                out.append(column)
    return out


def node_anchor_ids(node) -> Tuple[str, ...]:
    """The review anchors recorded on **one** node or one run of styled text.

    Returned in the order the API gave them, with nothing added and nothing removed: an
    absent list and an empty one are both reported as no anchors here, while the difference
    between them stays visible on the node itself.
    """
    ids = getattr(node, "comment_ids", None)
    if not ids:
        return ()
    return tuple(str(i) for i in ids)


def anchor_ids(root) -> Tuple[str, ...]:
    """Every review anchor in a parsed document, in document order, de-duplicated.

    Both granularities are collected: the anchor recorded on a block, and the anchor recorded
    on a styled run inside a block. A block and a run may carry the same id, and two runs in
    one block may carry different ids; de-duplication here is about not asking the API the
    same question twice, and does not change what any node reports about itself.
    """
    seen: Dict[str, None] = {}

    def visit(node):
        for anchor in node_anchor_ids(node):
            seen.setdefault(anchor, None)
        content = getattr(node, "content", None)
        if isinstance(content, list):
            for inline in content:
                for anchor in node_anchor_ids(inline):
                    seen.setdefault(anchor, None)
        for sequence in _child_sequences(node):
            for child in sequence:
                if child is not None and not isinstance(child, (str, int, float, bool)):
                    visit(child)

    if root is not None:
        visit(root)
    return tuple(seen)


# --------------------------------------------------------------------------- #
# The result.                                                                   #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class CommentsRead:
    """The outcome of a comments read: what was found, what was asked for, what is missing.

    :attr:`available` is the first thing to look at. ``True`` with an empty
    :attr:`comments` means the read succeeded and there are none; ``False`` means the read
    did not happen and this object carries no knowledge either way —
    :attr:`unavailable_reason` says why.

    :attr:`completeness` is the second. It says whether this is the file's **whole** comment
    list or an **anchor-scoped** subset of it, and it is what stops the second being relayed as
    the first. The two directions in which a read can be short of the file are reported
    separately, because they are different facts with different causes:
    :attr:`missing_ids` is *an anchor that resolved to no comment* (normally a comment removed
    since the document read) and :attr:`unanchored_ids` is *a comment no anchor can reach*
    (a whole-document comment — no scoped read can ever return one).
    """

    file_token: str
    file_type: str = FILE_TYPE_DOCX
    comments: Tuple[Comment, ...] = ()
    #: The anchors this read set out to resolve — empty when the whole list was read.
    requested_ids: Tuple[str, ...] = ()
    #: Requested anchors that resolved to no comment. Reported, never dropped.
    missing_ids: Tuple[str, ...] = ()
    available: bool = True
    unavailable_code: Optional[int] = None
    unavailable_reason: Optional[str] = None
    #: Everything a caller should know before acting on this result.
    notes: Tuple[str, ...] = ()
    #: How many API calls this read cost. Zero is a legitimate, cheap answer.
    api_calls: int = 0
    #: Which of the two read shapes produced this result —
    #: :data:`COMPLETENESS_COMPLETE`, :data:`COMPLETENESS_ANCHOR_SCOPED` or
    #: :data:`COMPLETENESS_UNAVAILABLE`. Normalized in ``__post_init__``: an unavailable read
    #: is **always** reported as unavailable, whatever it was constructed with, so no code path
    #: can hand back a failed read labelled complete.
    completeness: str = COMPLETENESS_COMPLETE

    def __post_init__(self):
        object.__setattr__(self, "_by_id", {
            c.comment_id: c for c in self.comments if c.comment_id is not None})
        if not self.available:
            object.__setattr__(self, "completeness", COMPLETENESS_UNAVAILABLE)

    # ---- lookups ---------------------------------------------------------- #

    @property
    def by_id(self) -> Dict[str, Comment]:
        """The comments keyed by id."""
        return dict(self._by_id)

    def for_ids(self, ids: Iterable[str]) -> Tuple[Comment, ...]:
        """The comments for ``ids``, in the order given, skipping ids that resolved to
        nothing (those are in :attr:`missing_ids`)."""
        out: List[Comment] = []
        for anchor in ids:
            comment = self._by_id.get(str(anchor))
            if comment is not None:
                out.append(comment)
        return tuple(out)

    def for_node(self, node) -> Tuple[Comment, ...]:
        """The comments anchored to one block **or** one run of styled text.

        Both carry their own anchor list, so the same call answers either — which is the
        point: a reviewer's objection is attached to a passage, and the passage may be a
        whole block or a few words inside it.
        """
        return self.for_ids(node_anchor_ids(node))

    # ---- the comment → NO ANCHOR direction -------------------------------- #

    @property
    def unanchored_ids(self) -> Tuple[str, ...]:
        """The comments in this result that **no review anchor can reach**, in order.

        The missing counterpart to :attr:`missing_ids`. That one is *anchor → no comment*; this
        one is *comment → no anchor*, which had no field at all and is the direction an
        anchor-scoped read loses comments in.

        A comment the API reports as attached to the whole file has no anchor by construction —
        no block will ever point at it, and no anchor-scoped read can ever return it. A comment
        whose scope the endpoint did **not** report is deliberately not listed: ``unreported``
        is not a synonym for either answer, and guessing here would invent one.

        **Derived, never stored**, like :attr:`Comment.scope` — so it cannot drift from the
        comments it describes, and a hand-built result cannot claim an accounting it does not
        have.
        """
        return tuple(c.comment_id for c in self.comments
                     if c.is_whole is True and c.comment_id is not None)

    # ---- disclosure ------------------------------------------------------- #

    @property
    def disclosure(self) -> str:
        """One paragraph a caller can relay as-is: the state of this read and its caveats.

        The head is derived from :attr:`completeness`, not from the count alone. That is the
        whole point: a count-only sentence read identically for a whole-list read and for a
        scoped one that had silently dropped comments, so relaying it passed off a partial
        review as the full one.
        """
        if not self.available:
            head = f"Comments unavailable for {self.file_token}: {self.unavailable_reason}"
        elif self.completeness == COMPLETENESS_ANCHOR_SCOPED:
            head = (f"{len(self.comments)} comment(s) read for {self.file_token} "
                    f"({self.file_type}) from the {len(self.requested_ids)} review anchor(s) "
                    f"the document tree carried — an anchor-scoped read, NOT the file's whole "
                    f"comment list.")
        elif self.comments:
            head = (f"{len(self.comments)} comment(s) read for {self.file_token}"
                    f" ({self.file_type}) — the file's whole comment list.")
        else:
            head = (f"No comments on {self.file_token} ({self.file_type}) — the read "
                    f"succeeded and found none.")
        return " ".join([head] + list(self.notes))

    # ---- serialization ---------------------------------------------------- #

    def to_dict(self) -> dict:
        return {
            "file_token": self.file_token,
            "file_type": self.file_type,
            "available": self.available,
            "unavailable_code": self.unavailable_code,
            "unavailable_reason": self.unavailable_reason,
            "comments": [c.to_dict() for c in self.comments],
            "requested_ids": list(self.requested_ids),
            "missing_ids": list(self.missing_ids),
            "notes": list(self.notes),
            "api_calls": self.api_calls,
            "completeness": self.completeness,
            # Derived, like the comment's own `scope`: emitted so a consumer reading only the
            # wire form sees the accounting, and recomputed on the way back in rather than
            # trusted from the dict.
            "unanchored_ids": list(self.unanchored_ids),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CommentsRead":
        return cls(
            file_token=d["file_token"],
            file_type=d.get("file_type", FILE_TYPE_DOCX),
            comments=tuple(Comment.from_dict(c) for c in d.get("comments") or ()),
            requested_ids=tuple(d.get("requested_ids") or ()),
            missing_ids=tuple(d.get("missing_ids") or ()),
            available=d.get("available", True),
            unavailable_code=d.get("unavailable_code"),
            unavailable_reason=d.get("unavailable_reason"),
            notes=tuple(d.get("notes") or ()),
            api_calls=d.get("api_calls", 0),
            completeness=d.get("completeness", COMPLETENESS_COMPLETE),
        )


# --------------------------------------------------------------------------- #
# The entry point.                                                              #
# --------------------------------------------------------------------------- #

def _describe(code, msg) -> str:
    """A code the caller can act on, in words. An unknown code keeps its number and the
    server's own message rather than being dressed up as something understood."""
    try:
        known = COMMENT_ERROR_CODES.get(int(code))
    except (TypeError, ValueError):
        known = None
    if known:
        return f"{known} (code {code})"
    return f"the request failed with code {code}: {msg}"


def _file_type_notes(file_type: str) -> List[str]:
    if file_type == FILE_TYPE_SHEET:
        return [SHEETS_READ_ACCEPTED_CREATE_REJECTED_NOTE, SHEETS_NO_CELL_ANCHOR_NOTE]
    if file_type == FILE_TYPE_BITABLE:
        return [BASE_COMMENT_WRITE_REFUSED_NOTE, BASE_RECORD_ATTRIBUTION_NOTE,
                BASE_QUOTE_IS_NOT_AN_ANCHOR_NOTE]
    return []


def _content_notes(found: List[Comment]) -> List[str]:
    """The disclosures the comments themselves earn — what is in this result, and what is not.

    Three facts, each attached to the condition that makes it matter rather than announced on
    every read:

    * a comment **no anchor can reach** is in the result (a whole-document comment) — so a
      caller walking blocks alone would miss it;
    * a reply carries an **image**, so its ``text`` is not the whole of what was said;
    * **reactions are unread**, disclosed whenever there is a review to report at all, because
      a reviewer summary that silently drops "and four people agreed" misstates the review.

    Order is fixed so the paragraph a caller relays is stable rather than incidental.
    """
    if not found:
        return []
    out: List[str] = []
    if any(c.is_whole is True for c in found):
        out.append(UNANCHORED_IDS_NOTE)
    if any(r.image_tokens for c in found for r in c.replies):
        out.append(IMAGE_REPLIES_NOTE)
    out.append(REACTIONS_NOT_MODELLED_NOTE)
    return out


def _attributions_of(client) -> Dict[str, "object"]:
    """The record attributions the reading client harvested — or none, without complaining.

    ``comments()`` accepts a **caller-supplied** reader (to share a rate budget, or to read in
    another region), and a reader written before Bases were readable has no harvest to offer.
    That is *no attribution*, which is exactly what a document or a spreadsheet has, and it is
    not worth failing a comment read over. The shipped client always offers one.
    """
    return getattr(client, "reply_attributions", None) or {}


def _complete_threads(client, file_token, file_type, raw_comments) -> List[Comment]:
    """Project each comment, completing a thread the response reported as truncated.

    The batch-fetch response marks per comment whether its embedded reply list is partial and
    hands back a cursor for the rest. Following it is what keeps a long review thread from
    being reported as its first page — a silent truncation is the kind of half-answer this
    surface is supposed to refuse.
    """
    out: List[Comment] = []
    attributions = _attributions_of(client)
    for raw in raw_comments:
        if not getattr(raw, "has_more", None):
            out.append(Comment.from_file_comment(raw, attributions=attributions))
            continue
        reply_list = getattr(raw, "reply_list", None)
        embedded = getattr(reply_list, "replies", None) if reply_list is not None else None
        replies = [CommentReply.from_sdk(r, attribution=attributions.get(str(r.reply_id)))
                   for r in (embedded or ())]
        rest = client.list_replies(
            file_token, raw.comment_id, file_type=file_type,
            page_token=getattr(raw, "page_token", None) or None)
        # Re-read after the completion call: the replies it just fetched carry their own
        # attribution, harvested from that response.
        attributions = _attributions_of(client)
        known = {r.reply_id for r in replies if r.reply_id is not None}
        for reply in rest:
            projected = CommentReply.from_sdk(
                reply, attribution=attributions.get(str(reply.reply_id)))
            if projected.reply_id is None or projected.reply_id not in known:
                replies.append(projected)
                known.add(projected.reply_id)
        out.append(Comment.from_file_comment(
            raw, replies=replies, attributions=attributions))
    return out


def comments(
    document: str,
    *,
    file_type: str = FILE_TYPE_DOCX,
    root=None,
    client: Optional[CommentsReadClient] = None,
    domain: str = "larksuite.com",
) -> CommentsRead:
    """Read the comments on a file.

    ``document`` is the file's token. **Called with nothing else, this reads the file's whole
    comment list** — which is what "the comments on this document" means, and what a review
    summary needs. The per-block lookup (:meth:`CommentsRead.for_node`) works on that result:
    it reads each node's own anchors, so it needs no tree passed in here.

    ``root`` — the node tree a document read produced — makes the read **anchor-scoped**: only
    the review anchors that tree carries are requested. It is an **optimization with a cost, not
    a better default.** The optimization: a tree carrying **no** anchors costs **no** API call,
    because there is nothing to ask about. The cost: on a tree that does carry anchors it costs
    the same single call the whole-list read costs and returns **less** — a comment attached to
    the whole document has no anchor and can **never** come back, and a comment anchored
    anywhere the tree did not carry is absent too. So reach for it when you expect most
    documents to have no comments at all and want to pay nothing for them; do not reach for it
    to get the per-block join, which you have either way. Such a result marks itself
    :data:`COMPLETENESS_ANCHOR_SCOPED` and says so in :attr:`CommentsRead.disclosure`.

    ``file_type`` is ``"docx"`` for a document, ``"sheet"`` for a spreadsheet, and
    ``"bitable"`` for a Base — whose threads carry the **record, table and view** the reviewer
    had open, so a comment can be attributed to a row rather than only to the file. It is the
    same three this function branches on (:data:`FILE_TYPE_DOCX`, :data:`FILE_TYPE_SHEET`,
    :data:`FILE_TYPE_BITABLE`); a Base read on the ``"docx"`` default answers ``1069307``. A
    spreadsheet and a Base read each carry extra disclosures in :attr:`CommentsRead.notes`.

    ``client`` lets a caller supply its own reader (sharing a rate budget, or reading in a
    non-default region); by default one is built from the environment's read credentials.

    A failure to read comments never raises: it comes back as an unavailable result carrying
    the reason. Everything else about the document — its content, its Markdown — is
    untouched by this call either way.
    """
    reader = client if client is not None else CommentsReadClient.from_read_credentials(
        domain)
    notes = _file_type_notes(file_type)
    requested: Tuple[str, ...] = ()
    completeness = (COMPLETENESS_ANCHOR_SCOPED if root is not None
                    else COMPLETENESS_COMPLETE)
    if root is not None:
        notes = notes + [ANCHOR_SCOPED_NOTE]

    if root is not None:
        requested = anchor_ids(root)
        if not requested:
            # Nothing is anchored anywhere in this document, so there is nothing to ask. The
            # result is still an ANCHOR-SCOPED one, not an empty file: "no anchor on this tree"
            # and "no comment on this file" are different answers, and reporting the first as
            # the second was the cheapest way to lie about a commented document.
            return CommentsRead(
                file_token=document, file_type=file_type, comments=(),
                requested_ids=(), missing_ids=(), notes=tuple(notes), api_calls=0,
                completeness=completeness)

    before = reader.api_calls
    try:
        if root is not None:
            raw = reader.batch_query_comments(document, requested, file_type=file_type)
        else:
            raw = reader.list_comments(document, file_type=file_type)
        found = _complete_threads(reader, document, file_type, raw)
    except LarkAPIError as exc:
        reason = _describe(exc.code, exc.msg)
        return CommentsRead(
            file_token=document, file_type=file_type, comments=(),
            requested_ids=requested, missing_ids=requested,
            available=False,
            unavailable_code=_as_int(exc.code),
            unavailable_reason=reason,
            notes=tuple([UNAVAILABLE_NOTE] + notes),
            api_calls=reader.api_calls - before,
        )

    resolved = {c.comment_id for c in found if c.comment_id is not None}
    missing = tuple(i for i in requested if i not in resolved)
    if missing:
        notes = notes + [MISSING_IDS_NOTE]
    notes = notes + _content_notes(found)
    return CommentsRead(
        file_token=document, file_type=file_type, comments=tuple(found),
        requested_ids=requested, missing_ids=missing, notes=tuple(notes),
        api_calls=reader.api_calls - before, completeness=completeness,
    )


def _as_int(code):
    try:
        return int(code)
    except (TypeError, ValueError):
        return None
