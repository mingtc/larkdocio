"""larkdocio.write.model — the findings-agnostic edit-request + apply-log surface
(LD-065, head of the W1 chain).

This is the **pure-offline public vocabulary** the rest of the W1 apply engine is built
on. A consumer expresses an edit against a Lark docx **without leaking its findings
schema into the library**: larkdocio never learns a consumer's findings vocabulary, layer
labels, or status flow. A consumer maps its own accepted edits onto :class:`EditRequest`
values, and owns its approval UX and any status-flipping afterward; larkdocio only resolves
(S2), previews/applies (S3–S5), and returns the :class:`ApplyLog`.

The vocabulary is split across four concern-group submodules — grown across W1..W3 and
changing on different tranche cadences — with this package as a **transparent re-export
shim** (the ``larkdocio.auth`` precedent) so ``from larkdocio.write.model import X`` keeps
working for every public name **and the two private dispatchers**, unchanged:

* :mod:`~larkdocio.write.model.anchors` — :class:`Anchor`, :class:`TableLocator`,
  :class:`AnchorById` (LD-137), the two comment shapes :class:`WholeDocument` /
  :class:`CommentThread` (LD-202), and the ``_anchor_from_dict`` shape dispatcher (plus the
  ``_describe_anchor`` refusal-detail phrasing helper): **where** an edit points.
* :mod:`~larkdocio.write.model.requests` — :class:`EditRequest`, :class:`InsertRequest`,
  :class:`DeleteRequest`, :class:`SubSpanEditRequest`, :class:`InsertPosition`, the
  creatable-content family :class:`NewBlock` / :class:`NewBlockKind` /
  :class:`NewParagraph` (LD-134, plus LD-135's table kind), the two comment ops
  :class:`CreateCommentRequest` / :class:`RemoveCommentRequest` (LD-202), and the
  ``_request_from_dict`` / ``_content_from_dict`` dispatchers: **what** edit is requested.
* :mod:`~larkdocio.write.model.refusal` — :class:`RefusalReason` / :class:`Refusal` /
  :class:`RefusedError`: the typed **skip** reasons the resolver (S2) and apply engine (S4)
  return (never guess, always skip), plus the construction-time carrier for content that is
  *inexpressible* (LD-135); the full table + insert/delete refusal-mapping rationale lives
  there.
* :mod:`~larkdocio.write.model.applylog` — :class:`ApplyLogEntry` / :class:`ApplyLog`: the
  JSON-serializable **record** of processing each request.

No resolution, no write, no ``WriteClient`` call happens here — this package is dumb typed
data (the model/renderer split the reader already follows). It depends only on the standard
library. The names bound here are the *same objects* the submodules define, not a fork.
"""
from .anchors import (
    WHOLE_DOCUMENT,
    Anchor,
    AnchorById,
    CommentThread,
    TableLocator,
    WholeDocument,
    _anchor_from_dict,
    _describe_anchor,
)
from .applylog import ApplyLog, ApplyLogEntry
from .refusal import Refusal, RefusalReason, RefusedError
from .requests import (
    COMMENT_FILE_TYPES,
    MAX_CHILDREN_PER_CALL,
    MAX_NEST_DEPTH,
    MAX_TABLE_CELLS,
    APPEND_ROW_INDEX,
    MAX_TABLE_COLUMNS,
    CreateCommentRequest,
    DeleteRequest,
    EditRequest,
    InsertPosition,
    InsertRequest,
    GrowTableRequest,
    NarrativeAnchor,
    TableAnchor,
    NewBlock,
    NewBlockKind,
    NewContent,
    NewParagraph,
    RemoveCommentRequest,
    SubSpanEditRequest,
    TextSpan,
    _content_from_dict,
    _request_from_dict,
)

__all__ = [
    "Anchor",
    "AnchorById",
    "CommentThread",
    "NarrativeAnchor",
    "TableAnchor",
    "GrowTableRequest",
    "TableLocator",
    "WHOLE_DOCUMENT",
    "WholeDocument",
    "COMMENT_FILE_TYPES",
    "CreateCommentRequest",
    "RemoveCommentRequest",
    "EditRequest",
    "InsertPosition",
    "NewParagraph",
    "NewBlock",
    "NewBlockKind",
    "NewContent",
    "TextSpan",
    "MAX_NEST_DEPTH",
    "MAX_CHILDREN_PER_CALL",
    "MAX_TABLE_CELLS",
    "MAX_TABLE_COLUMNS",
    "APPEND_ROW_INDEX",
    "InsertRequest",
    "SubSpanEditRequest",
    "DeleteRequest",
    "RefusalReason",
    "Refusal",
    "RefusedError",
    "ApplyLogEntry",
    "ApplyLog",
]
