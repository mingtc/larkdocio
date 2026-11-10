"""larkdocio.comments — read the review conversation on a Lark file.

A document's comments answer the question its Markdown cannot: **what did reviewers object
to, and about which passage?** This package is that read, and only that read — it creates
nothing, replies to nothing, resolves nothing.

Start at :func:`~larkdocio.comments.read.comments`::

    from larkdocio.comments import comments

    result = comments(file_token)
    for c in result.comments:
        print(c.scope, c.user_id, c.text)

That call reads the file's **whole** comment list. The per-block join needs nothing extra —
:meth:`~larkdocio.comments.read.CommentsRead.for_node` reads each node's own review anchors, so
going from one block, or one run of styled text inside a block, to the comments on it works on
that same result::

    result = comments(file_token)
    for node_comment in result.for_node(some_block):
        print(node_comment.text)

Passing ``root=`` instead makes the read **anchor-scoped** — only the anchors that tree carries
are requested. That is an **optimization with a cost**: a tree with no anchors at all costs no
API call, but a tree that has them costs the same single call as the whole-list read and returns
**less**, because a comment attached to the whole document has no anchor and can never come
back. Such a result marks itself ``completeness="anchor-scoped"`` and says so in its
``disclosure`` rather than looking complete.

**What this surface will not do.**

* **It never guesses an author's name.** ``user_id`` is the raw id the API returns; the
  identity endpoint is not reachable on this library's read scope and no scope is requested
  to make it reachable. There is also no human-vs-application flag in the payload, so none
  is invented. To recognize your own application's comments, compare ``user_id`` with your
  own bot id.
* **It never infers a location the API did not give.** A comment's scope is reported by
  some endpoints and omitted by others, and an omission is reported back as an omission
  (see :mod:`larkdocio.comments.models`). Mapping a comment back to a block id through the
  API's relation field is **not implemented**: the field comes back empty for whole-file
  comments, and a passage-anchored comment cannot be created through the API at all, so
  there was no way to verify such a mapping. Rather than ship an unverified join, this
  package ships none — see :data:`~larkdocio.comments.read.REVERSE_JOIN_NOTE`.
* **It never renders comments into the document's Markdown.** The Markdown a document
  converts to is byte-for-byte unaffected by this package.
* **It never reports "no comments" when it does not know.** A failed comments read leaves
  the document read intact and says plainly that the comment knowledge is missing, with the
  reason — it does not return an empty list. See
  :attr:`~larkdocio.comments.read.CommentsRead.available`.

Spreadsheets are readable here too (pass ``file_type="sheet"``), with one asymmetry worth
knowing before you build on it: the API accepts a comment **read** on a spreadsheet while
refusing a comment **create** on one, and a spreadsheet comment carries no structured cell
reference — its quoted text is often just a cell label. This package therefore never
presents a spreadsheet comment as attached to a cell.

**Bases are readable here too** (pass ``file_type="bitable"``), with the same asymmetry in a
sharper form and one capability the other two file types have no equivalent of. The
asymmetry: the API accepts a comment **read** on a Base and refuses a comment **create** on
one outright, at every granularity — see
:data:`~larkdocio.comments.read.BASE_COMMENT_WRITE_REFUSED_NOTE`. The capability: a Base
comment written against a row says **which row**, and this package surfaces that as
structured data on the thread and on each reply
(:attr:`~larkdocio.comments.models.Comment.attribution`), with a named
:attr:`~larkdocio.comments.models.Comment.attribution_state` for a comment on the Base as a
whole. A row is never inferred for a comment that names none.
"""
from larkdocio.comments.attribution import (
    ATTRIBUTION_FILE_LEVEL,
    ATTRIBUTION_RECORD,
    BaseAttribution,
)
from larkdocio.comments.client import (
    COMMENTS_RATE_WINDOW_SECONDS,
    DEFAULT_MAX_READS_PER_WINDOW,
    CommentsReadClient,
)
from larkdocio.comments.models import (
    KIND_DOCS_LINK,
    KIND_PERSON,
    KIND_TEXT,
    KIND_UNKNOWN_PREFIX,
    SCOPE_ANCHORED,
    SCOPE_UNREPORTED,
    REDACTED_AUTHOR_LABEL,
    REDACTED_MENTION_LABEL,
    SCOPE_WHOLE_DOCUMENT,
    Comment,
    CommentReply,
    ReplyElement,
    author_label,
)
from larkdocio.comments.read import (
    ANCHOR_SCOPED_NOTE,
    BASE_COMMENT_WRITE_REFUSED_NOTE,
    BASE_QUOTE_IS_NOT_AN_ANCHOR_NOTE,
    BASE_RECORD_ATTRIBUTION_NOTE,
    BLOCK_ID_COMMENT_ANCHOR_CONSEQUENCE,
    COMMENT_ERROR_CODES,
    COMPLETENESS_ANCHOR_SCOPED,
    COMPLETENESS_COMPLETE,
    COMPLETENESS_UNAVAILABLE,
    FILE_TYPE_BITABLE,
    FILE_TYPE_DOCX,
    FILE_TYPE_SHEET,
    IMAGE_REPLIES_NOTE,
    REACTIONS_NOT_MODELLED_NOTE,
    REVERSE_JOIN_NOTE,
    SHEETS_NO_CELL_ANCHOR_NOTE,
    SHEETS_READ_ACCEPTED_CREATE_REJECTED_NOTE,
    UNANCHORED_IDS_NOTE,
    CommentsRead,
    anchor_ids,
    comments,
)

__all__ = [
    "ANCHOR_SCOPED_NOTE",
    "ATTRIBUTION_FILE_LEVEL",
    "ATTRIBUTION_RECORD",
    "BASE_COMMENT_WRITE_REFUSED_NOTE",
    "BASE_QUOTE_IS_NOT_AN_ANCHOR_NOTE",
    "BASE_RECORD_ATTRIBUTION_NOTE",
    "BLOCK_ID_COMMENT_ANCHOR_CONSEQUENCE",
    "COMMENTS_RATE_WINDOW_SECONDS",
    "COMMENT_ERROR_CODES",
    "COMPLETENESS_ANCHOR_SCOPED",
    "COMPLETENESS_COMPLETE",
    "COMPLETENESS_UNAVAILABLE",
    "DEFAULT_MAX_READS_PER_WINDOW",
    "FILE_TYPE_BITABLE",
    "FILE_TYPE_DOCX",
    "FILE_TYPE_SHEET",
    "IMAGE_REPLIES_NOTE",
    "KIND_DOCS_LINK",
    "KIND_PERSON",
    "KIND_TEXT",
    "KIND_UNKNOWN_PREFIX",
    "REACTIONS_NOT_MODELLED_NOTE",
    "REDACTED_AUTHOR_LABEL",
    "REDACTED_MENTION_LABEL",
    "REVERSE_JOIN_NOTE",
    "SCOPE_ANCHORED",
    "SCOPE_UNREPORTED",
    "SCOPE_WHOLE_DOCUMENT",
    "SHEETS_NO_CELL_ANCHOR_NOTE",
    "SHEETS_READ_ACCEPTED_CREATE_REJECTED_NOTE",
    "UNANCHORED_IDS_NOTE",
    "BaseAttribution",
    "Comment",
    "CommentReply",
    "CommentsRead",
    "CommentsReadClient",
    "ReplyElement",
    "anchor_ids",
    "author_label",
    "comments",
]
