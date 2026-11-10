"""The typed comment model — frozen, JSON-round-trippable, and honest about absence.

Three frozen dataclasses project the API's comment family into values a consumer can hold,
compare and serialize: :class:`ReplyElement` (one piece of a reply's content),
:class:`CommentReply` (one message in the thread) and :class:`Comment` (the thread plus its
metadata). :class:`~larkdocio.comments.read.CommentsRead` — the result object the read
returns — lives beside them in ``read.py``.

**The projection is built on the SDK's own typed models, not on raw dicts.** The pinned
``lark-oapi`` ships the whole comment family (``FileComment`` / ``ReplyList`` /
``FileCommentReply`` / ``ReplyContent`` / ``ReplyElement``), and its deserializer assigns
only the keys a payload actually carries. That property is load-bearing here, not a
convenience: it is what lets a field the server **omitted** stay distinguishable from one
the server **set to false**.

**Why that distinction is the centre of this module.** The API does not report a comment's
scope uniformly. ``is_whole`` — whether a comment is attached to the whole document rather
than to a passage inside it — is **absent** from the create and single-comment-fetch
responses and **present** on the list and batch-fetch responses, for one and the same
comment. Defaulting the absent case to ``false`` would report a whole-document comment as
anchored to a passage, i.e. would invent an answer to "which passage did the reviewer
object to?". So ``is_whole`` is a **tri-state** here — ``True`` / ``False`` / ``None`` for
not reported — surfaced as :attr:`Comment.scope` and
:attr:`Comment.anchor_scope_reported`, and every endpoint's payload goes through the one
projection in :meth:`Comment.from_file_comment`.

**A reply's content is its elements PLUS the images beside them.** An image a reviewer pasted
into a comment does not arrive as a content element: it arrives out of band, as a list of file
tokens on the reply's ``extra``. Projecting only ``elements`` therefore reported an
image-bearing reply as plain text and dropped the image without a word — so
:attr:`CommentReply.image_tokens` carries those tokens verbatim. They are deliberately **not**
spliced into :attr:`CommentReply.text`: the API gives no position for them, so any placement
inside the reviewer's sentence would be invented, and a token is not text. Reported beside the
text, an image is visible; reported inside it, it would be a guess.

**What the API does not report, this model does not invent: reactions.** A comment that was
"liked" in the Lark UI comes back through every endpoint this library uses with **no reaction
field at all** — the shared comment document's own liked comment is the evidence. So there is
no reaction attribute here and none is inferred from anything else; the absence is disclosed
in words instead (:data:`~larkdocio.comments.read.REACTIONS_NOT_MODELLED_NOTE`), because
"there are no reactions" and "reactions are not read" are different answers and only one of
them is true.

**Authorship is raw, deliberately.** ``user_id`` is exposed exactly as the API gives it —
an opaque id (an ``ou_``-prefixed open id by default; ``on_``-prefixed if the caller asks
for union ids). No display name is looked up: the identity endpoint answers *no user
authority* on this library's read scope, so any human-readable name would be a guess. The
payload also carries no human-vs-application discriminator, so none is inferred. A caller
that needs to recognize *its own* application's comments compares ``user_id`` against its
own bot id, which it knows and this library does not.
"""
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Tuple

from lark_oapi.api.drive.v1 import FileComment, FileCommentReply

from larkdocio.comments.attribution import (
    ATTRIBUTION_FILE_LEVEL,
    ATTRIBUTION_RECORD,
    BaseAttribution,
)

#: What a rendered thread calls an author it has no name for. The comment family reports an
#: author as an **opaque id and nothing else** — no ``name``, no ``en_name``, no ``email``,
#: no ``avatar_url`` — so this marker is the only truthful label a rendering can use, and it
#: is used rather than the raw id: an id is tenant data, and a rendered thread is text a
#: consumer may put in front of people.
REDACTED_AUTHOR_LABEL = "<redacted:author>"

#: What a rendered thread puts where a reviewer @-mentioned somebody. Same doctrine as
#: :data:`REDACTED_AUTHOR_LABEL`, distinct wording so a reader can tell *who was mentioned*
#: from *who spoke* without either being a raw id.
REDACTED_MENTION_LABEL = "<redacted:mention>"


def author_label(name: Optional[str], en_name: Optional[str] = None) -> str:
    """The name-only doctrine, as one function: ``name`` → ``en_name`` → a redacted marker.

    Stated as a pure function because the *doctrine* is real while the *data* is not: no
    comment payload this library has observed carries either name, so the surface's own
    rendering always takes the third branch (see :data:`REDACTED_AUTHOR_LABEL`). A caller
    that has joined an identity in from elsewhere gets the same ordering, and an empty string
    counts as absent — a blank label is not a name.
    """
    return (name or "").strip() or (en_name or "").strip() or REDACTED_AUTHOR_LABEL

#: :attr:`Comment.scope` when the API reported the comment as attached to the whole file.
SCOPE_WHOLE_DOCUMENT = "whole-document"
#: :attr:`Comment.scope` when the API reported the comment as attached to a passage.
SCOPE_ANCHORED = "anchored"
#: :attr:`Comment.scope` when the endpoint did **not** report the scope at all. Not a
#: synonym for either of the above — it means the answer is unknown from this response.
SCOPE_UNREPORTED = "unreported"

#: :attr:`ReplyElement.kind` for a run of literal text.
KIND_TEXT = "text"
#: :attr:`ReplyElement.kind` for a mention of a person — carries a raw id, never a name.
KIND_PERSON = "person"
#: :attr:`ReplyElement.kind` for a link to a document.
KIND_DOCS_LINK = "docs-link"
#: :attr:`ReplyElement.kind` for an element whose type this projection does not model. Its
#: ``kind`` keeps the server's own type string so an unmodelled element is visible as
#: itself rather than silently dropped.
KIND_UNKNOWN_PREFIX = "unknown:"


def _text_of(element) -> str:
    """The readable text one reply element projects to.

    A mention projects to ``@<raw id>`` — the same shape the document reader uses for an
    unresolved mention, and the honest one here, because no name is obtainable. A document
    link projects to its URL. An element of an unmodelled type projects to the empty
    string: it contributes no text rather than a placeholder that could be mistaken for
    content.
    """
    text_run = getattr(element, "text_run", None)
    if text_run is not None:
        return text_run.text or ""
    person = getattr(element, "person", None)
    if person is not None:
        return f"@{person.user_id}" if person.user_id else ""
    docs_link = getattr(element, "docs_link", None)
    if docs_link is not None:
        return docs_link.url or ""
    return ""


def _kind_of(element) -> str:
    """Which of the three modelled element kinds this is (or a labelled unknown).

    Decided by which typed sub-object is **populated**, not by the ``type`` string, because
    the payload always carries all three keys with the two irrelevant ones ``null`` — so
    the populated one is the fact and ``type`` is its label. When nothing is populated the
    server's own label is preserved behind :data:`KIND_UNKNOWN_PREFIX`.
    """
    if getattr(element, "text_run", None) is not None:
        return KIND_TEXT
    if getattr(element, "person", None) is not None:
        return KIND_PERSON
    if getattr(element, "docs_link", None) is not None:
        return KIND_DOCS_LINK
    return KIND_UNKNOWN_PREFIX + (getattr(element, "type", None) or "unspecified")


@dataclass(frozen=True)
class ReplyElement:
    """One piece of a reply's content: literal text, a person mention, or a document link.

    ``text`` is the piece's readable projection (a mention reads ``@<raw id>``). ``user_id``
    is set only on a mention and is the **raw** id — no name is resolved for it. ``url`` is
    set only on a document link.
    """

    kind: str
    text: str
    user_id: Optional[str] = None
    url: Optional[str] = None

    @classmethod
    def from_sdk(cls, element) -> "ReplyElement":
        person = getattr(element, "person", None)
        docs_link = getattr(element, "docs_link", None)
        return cls(
            kind=_kind_of(element),
            text=_text_of(element),
            user_id=person.user_id if person is not None else None,
            url=docs_link.url if docs_link is not None else None,
        )

    def to_dict(self) -> dict:
        return {"kind": self.kind, "text": self.text,
                "user_id": self.user_id, "url": self.url}

    @classmethod
    def from_dict(cls, d: dict) -> "ReplyElement":
        return cls(kind=d["kind"], text=d["text"],
                   user_id=d.get("user_id"), url=d.get("url"))


@dataclass(frozen=True)
class CommentReply:
    """One message in a comment thread.

    ``user_id`` is the author's raw id. ``elements`` is the reply's content in order;
    :attr:`text` is their concatenation, which is what a consumer reads.

    ``image_tokens`` is the other half of the content: the file tokens of any images the reply
    carries. They arrive **out of band** — on the reply's ``extra``, not among ``elements`` —
    so a projection that read ``elements`` alone reported an image-bearing reply as plain text
    and lost the image silently. They are listed here rather than spliced into :attr:`text`
    because the payload gives them no position in the sentence.
    """

    reply_id: Optional[str] = None
    user_id: Optional[str] = None
    create_time: Optional[int] = None
    update_time: Optional[int] = None
    elements: Tuple[ReplyElement, ...] = ()
    #: The file tokens of images this reply carries, in the API's own order. Empty for a
    #: text-only reply — and empty is a fact here, not a default standing in for "unknown":
    #: the key is present on every reply payload, holding ``null`` when there are none.
    image_tokens: Tuple[str, ...] = ()
    #: The **record** this reply was written against, on a Base. ``None`` for a file-level
    #: Base comment and for every document and spreadsheet comment, which have no such
    #: notion. It does not come through the typed model — the SDK drops the object that
    #: carries it — so it is supplied by the client that read the response; see
    #: :mod:`larkdocio.comments.attribution`.
    attribution: Optional[BaseAttribution] = None

    @classmethod
    def from_sdk(cls, reply: FileCommentReply, *,
                 attribution: Optional[BaseAttribution] = None) -> "CommentReply":
        content = getattr(reply, "content", None)
        raw_elements = getattr(content, "elements", None) if content is not None else None
        extra = getattr(reply, "extra", None)
        images = getattr(extra, "image_list", None) if extra is not None else None
        return cls(
            reply_id=reply.reply_id,
            user_id=reply.user_id,
            create_time=reply.create_time,
            update_time=reply.update_time,
            elements=tuple(ReplyElement.from_sdk(e) for e in (raw_elements or ())),
            image_tokens=tuple(str(t) for t in (images or ())),
            attribution=attribution,
        )

    @property
    def text(self) -> str:
        """The reply's content as one readable string."""
        return "".join(e.text for e in self.elements)

    @property
    def mentioned_user_ids(self) -> Tuple[str, ...]:
        """The raw ids this reply mentions, in order — never resolved to names."""
        return tuple(e.user_id for e in self.elements
                     if e.kind == KIND_PERSON and e.user_id)

    def to_dict(self) -> dict:
        return {
            "reply_id": self.reply_id,
            "user_id": self.user_id,
            "create_time": self.create_time,
            "update_time": self.update_time,
            "elements": [e.to_dict() for e in self.elements],
            "text": self.text,
            "image_tokens": list(self.image_tokens),
            "attribution": (self.attribution.to_dict()
                            if self.attribution is not None else None),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CommentReply":
        return cls(
            reply_id=d.get("reply_id"),
            user_id=d.get("user_id"),
            create_time=d.get("create_time"),
            update_time=d.get("update_time"),
            elements=tuple(ReplyElement.from_dict(e) for e in d.get("elements") or ()),
            image_tokens=tuple(d.get("image_tokens") or ()),
            attribution=BaseAttribution.from_dict(d.get("attribution")),
        )

    @property
    def rendered(self) -> str:
        """One line of a rendered thread: an author label and what they said.

        The **rendering** obeys the name-only doctrine and the projection does not have to:
        :attr:`user_id` and :attr:`mentioned_user_ids` keep the raw ids for a caller that can
        join them to real identities, while this string — the one a consumer is likely to
        show a person — carries no id, no address and no avatar. A mention inside the text is
        rendered as the same marker for the same reason.
        """
        pieces = []
        for element in self.elements:
            pieces.append(REDACTED_MENTION_LABEL if element.kind == KIND_PERSON
                          else element.text)
        return f"{author_label(None)}: {''.join(pieces)}"


@dataclass(frozen=True)
class Comment:
    """One comment thread on a file, as this library reads it.

    ``is_whole`` is the **tri-state** scope flag described in this module's own
    documentation: ``True`` whole file, ``False`` attached to a passage, ``None`` the
    endpoint did not report it. Read it through :attr:`scope` unless the three-way
    distinction matters to you directly.

    ``quote`` is the passage the API echoes back for an anchored comment, verbatim and
    unparsed. It is **not** a structural anchor: it is text the server chose, it can be
    absent, and on a spreadsheet it is frequently just a cell label — so nothing here turns
    it into a location. ``replies`` is the thread in order; :attr:`text` is the whole thread
    as one string.

    **A resolved comment says WHO resolved it and never WHEN.** ``solved_time`` reads ``None``
    on every comment, resolved or not: the key is **never** sent — it is absent from the body
    of every comment endpoint, on documents and on spreadsheets alike, and captured resolved
    comments confirm it. So the combination to expect is ``is_solved=True`` with a populated
    ``solver_user_id`` and ``solved_time=None``; nothing was lost in the projection, and no
    amount of re-reading will fill it. The field is kept (rather than dropped) because it is
    the SDK's own, and a server that starts sending it will be carried through untouched. If
    you need *when*, the nearest available signal is the comment's ``update_time``, which
    moves when a comment is resolved — but it moves for other reasons too, so it is a hint
    and not a resolution timestamp.
    """

    comment_id: Optional[str] = None
    user_id: Optional[str] = None
    is_whole: Optional[bool] = None
    is_solved: Optional[bool] = None
    solved_time: Optional[int] = None
    solver_user_id: Optional[str] = None
    quote: Optional[str] = None
    create_time: Optional[int] = None
    update_time: Optional[int] = None
    replies: Tuple[CommentReply, ...] = ()

    # ---- the ONE projection every endpoint's payload goes through ---------- #

    @classmethod
    def from_file_comment(
        cls,
        comment: FileComment,
        *,
        replies: Optional[List[CommentReply]] = None,
        attributions: Optional[Mapping[str, BaseAttribution]] = None,
    ) -> "Comment":
        """Project one deserialized comment object.

        This is the only place a comment is built, and it is deliberately blind to which
        endpoint the payload came from: every field is read straight off the typed object,
        so a key the server omitted arrives here as ``None`` and stays ``None``. There is no
        per-endpoint branch and no default that would turn an omission into a claim.

        ``replies`` overrides the thread embedded in the payload — used when the embedded
        list was truncated and the rest was fetched separately.

        ``attributions`` is the ``{reply_id: attribution}`` map the reading client harvested
        from the response's own bytes, because the SDK's typed reply model drops the object
        that carries it. It is *joined in*, not parsed here: this projection stays the one
        place a comment is built, and stays blind to which endpoint produced the payload.
        """
        reply_list = getattr(comment, "reply_list", None)
        embedded = getattr(reply_list, "replies", None) if reply_list is not None else None
        joined = attributions or {}
        return cls(
            comment_id=comment.comment_id,
            user_id=comment.user_id,
            is_whole=comment.is_whole,
            is_solved=comment.is_solved,
            solved_time=comment.solved_time,
            solver_user_id=comment.solver_user_id,
            quote=comment.quote,
            create_time=comment.create_time,
            update_time=comment.update_time,
            replies=tuple(replies) if replies is not None
            else tuple(CommentReply.from_sdk(r, attribution=joined.get(str(r.reply_id)))
                       for r in (embedded or ())),
        )

    @classmethod
    def from_wire(cls, data: dict, **kwargs) -> "Comment":
        """Project one comment from a raw response body, via the SDK's deserializer.

        A thin door onto :meth:`from_file_comment` for callers holding an undeserialized
        body. The deserialization is the SDK's, so an absent key stays absent, and the
        projection below it is the same single code path.
        """
        return cls.from_file_comment(FileComment(data), **kwargs)

    # ---- derived views ---------------------------------------------------- #

    @property
    def anchor_scope_reported(self) -> bool:
        """Whether this response reported the comment's scope at all."""
        return self.is_whole is not None

    @property
    def scope(self) -> str:
        """:data:`SCOPE_WHOLE_DOCUMENT`, :data:`SCOPE_ANCHORED` or
        :data:`SCOPE_UNREPORTED` — never a guess for the third case."""
        if self.is_whole is None:
            return SCOPE_UNREPORTED
        return SCOPE_WHOLE_DOCUMENT if self.is_whole else SCOPE_ANCHORED

    @property
    def text(self) -> str:
        """The whole thread as one readable string, one reply per line."""
        return "\n".join(r.text for r in self.replies)

    @property
    def mentioned_user_ids(self) -> Tuple[str, ...]:
        """Every raw id mentioned anywhere in the thread, in order, de-duplicated."""
        seen: Dict[str, None] = {}
        for reply in self.replies:
            for uid in reply.mentioned_user_ids:
                seen.setdefault(uid, None)
        return tuple(seen)

    @property
    def attribution(self) -> Optional[BaseAttribution]:
        """The record this **thread** was written against, on a Base — or ``None``.

        Derived from the replies rather than stored, like :attr:`scope`, so it cannot drift
        from the thread it describes. The payload hangs the attribution off each reply; the
        first reply that carries one is the thread's, because that is the reviewer who opened
        it and chose the row. A thread whose replies carry none is **file-level** — see
        :attr:`attribution_state` — and is never given a row by inference.
        """
        for reply in self.replies:
            if reply.attribution is not None:
                return reply.attribution
        return None

    @property
    def attribution_state(self) -> str:
        """:data:`~larkdocio.comments.attribution.ATTRIBUTION_RECORD` or
        :data:`~larkdocio.comments.attribution.ATTRIBUTION_FILE_LEVEL` — a named state either
        way, so an unattributed comment is reported as *file-level* rather than as a gap."""
        return (ATTRIBUTION_RECORD if self.attribution is not None
                else ATTRIBUTION_FILE_LEVEL)

    @property
    def rendered_thread(self) -> str:
        """The whole thread as text safe to show a person: one rendered reply per line.

        The counterpart to :attr:`text`, which is unchanged and still renders a mention as
        ``@<raw id>`` for the two file types that shipped before this one. This rendering
        applies the name-only doctrine — no id, no address, no avatar — and is what a Base
        review summary should quote.
        """
        return "\n".join(r.rendered for r in self.replies)

    @property
    def image_tokens(self) -> Tuple[str, ...]:
        """Every image token anywhere in the thread, in order, de-duplicated.

        The thread-level view of :attr:`CommentReply.image_tokens`, so "does this reviewer's
        objection include a picture?" is one lookup rather than a walk. Non-empty here means
        :attr:`text` is **not** the whole of what was said.
        """
        seen: Dict[str, None] = {}
        for reply in self.replies:
            for token in reply.image_tokens:
                seen.setdefault(token, None)
        return tuple(seen)

    # ---- serialization ---------------------------------------------------- #

    def to_dict(self) -> dict:
        """A JSON-native projection. ``is_whole`` is always present as a key so that
        ``null`` (not reported) survives a serialization round trip distinctly from
        ``false``."""
        return {
            "comment_id": self.comment_id,
            "user_id": self.user_id,
            "is_whole": self.is_whole,
            "scope": self.scope,
            "is_solved": self.is_solved,
            "solved_time": self.solved_time,
            "solver_user_id": self.solver_user_id,
            "quote": self.quote,
            "create_time": self.create_time,
            "update_time": self.update_time,
            "replies": [r.to_dict() for r in self.replies],
            "text": self.text,
            "image_tokens": list(self.image_tokens),
            # Derived, like `scope`: emitted so a consumer reading only the wire form sees
            # the attribution, and recomputed from the replies on the way back in.
            "attribution": (self.attribution.to_dict()
                            if self.attribution is not None else None),
            "attribution_state": self.attribution_state,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Comment":
        """Rebuild from :meth:`to_dict`. ``scope`` and ``text`` are derived, so they are
        read back from the fields that produce them, never trusted from the dict."""
        return cls(
            comment_id=d.get("comment_id"),
            user_id=d.get("user_id"),
            is_whole=d.get("is_whole"),
            is_solved=d.get("is_solved"),
            solved_time=d.get("solved_time"),
            solver_user_id=d.get("solver_user_id"),
            quote=d.get("quote"),
            create_time=d.get("create_time"),
            update_time=d.get("update_time"),
            replies=tuple(CommentReply.from_dict(r) for r in d.get("replies") or ()),
        )
