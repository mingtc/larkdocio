"""larkdocio.write — the Lark docx writeback surface.

The **write client + self-provisioning harness** prove
the write round-trip end-to-end: :class:`~larkdocio.write.client.WriteClient` rides
the shared core (throttle + ``99991400`` backoff, tenant-token auth) and speaks the
docx v1 block write surface, with :func:`~larkdocio.write.client.to_write_elements`
the style-preserving element rebuild.

The **findings-agnostic edit-request + apply-log model**
(``larkdocio.write.model``): a typed :class:`~larkdocio.write.model.EditRequest`
(anchor = quote + breadcrumb + whole-paragraph replacement), the typed refusal
reasons the resolver/apply-engine return (:class:`~larkdocio.write.model.Refusal` /
:class:`~larkdocio.write.model.RefusalReason`), and a JSON-serializable
:class:`~larkdocio.write.model.ApplyLog`.

The **anchor resolution engine** (``larkdocio.write.resolve``):
:func:`~larkdocio.write.resolve.resolve` takes an ``EditRequest`` + a parsed node tree
and returns **exactly one** :class:`~larkdocio.write.resolve.ResolvedTarget` (block_id
+ node) **or a typed Refusal, never a guess** — quote match on a block's plain text,
breadcrumb narrowing, write-hostile (image/board/embed/synced) refusal.

The **mandatory dry-run previewer** (``larkdocio.write.preview``):
:func:`~larkdocio.write.preview.dry_run` turns a batch of edit requests + a parsed tree
into a non-forgeable :class:`~larkdocio.write.preview.Plan` (per edit: block_id +
before/after, or a typed refusal) with **zero writes** — the only input the apply engine
accepts.

The **whole-paragraph apply engine** (``larkdocio.write.apply``):
:func:`~larkdocio.write.apply.apply` executes a dry-run ``Plan`` via the ``WriteClient``
— element-level ``update_text_elements`` patches rebuilt with ``to_write_elements``
(style-preserving, whole-paragraph), the anchor **re-validated against the live block
right before each write** (drift → ``stale-anchor`` skip), throttled through the shared
transport, with an :class:`~larkdocio.write.model.ApplyLog` written for every attempt.
The binding **write round-trip gate** SHIPS: a live gate ring whose members are
enumerated in ``README.md`` § "Live-test discipline" and held there against
``capabilities(full=True)["surfaces"]["docx-write"]["gate_coverage"]`` — the count
is stated once, in that one guarded place, and deliberately not repeated here. The ring
is never part of the offline suite: it needs real write credentials and a disposable
document, so it is armed and run by hand. See ``README.md`` for the ring, the arming
protocol and the least-privilege two-app credential rationale.

The **creatable floor** is not paragraphs-only: the typed
:class:`~larkdocio.write.model.NewBlock` family — heading(level 1–9), paragraph, bullet /
ordered / todo list items **with nesting**, code(language), quote — plus the encoder
(``larkdocio.write.encode``) that turns each into its real ``create_children`` payload.
:class:`~larkdocio.write.model.NewParagraph` stays valid and byte-compatible; everything
flows through the same ``dry_run`` → ``Plan`` → ``apply`` gate.

A table is creatable, not only editable:
``NewBlock.table(rows, header_row=...)`` authors an **R×C grid** whose cells are each plain
text **or a `TextSpan` sequence carrying a link anchor**, encoded
to the docx grid property Lark auto-provisions the cell family from, with each authored cell
then filled through the same whole-cell patch the shipped ``TableLocator`` edit path uses — so
a created table is immediately a first-class edit target. **Merged cells are inexpressible**
from Markdown: a ragged grid is refused with the typed ``merge-not-expressible`` refusal
(:class:`~larkdocio.write.model.RefusedError`), never approximated.

That structure is also **authorable from Markdown**:
:func:`~larkdocio.write.compose.compose` compiles a fragment written in **exactly our
reader's dialect** (the GFM subset it emits, **including its escaping rules read in
reverse**) into the ordered typed content an ``InsertRequest`` carries, and
:func:`~larkdocio.write.compose.compose_insert` pairs that content with an anchor. It
**produces requests, never writes**. A construct outside the dialect is refused with the
**construct and its line named** (``not-in-dialect``) — never dropped, flattened or
approximated; :data:`~larkdocio.write.compose.NOT_EXPRESSIBLE_CONSTRUCTS` is the closed
set, and the shipped lossiness table in ``README.md`` is guarded against it.

There is a second **anchor kind**:
:class:`~larkdocio.write.model.AnchorById` lets **insert / edit / delete** (and sub-span)
target a **``block_id``** directly — ``apply()`` has always returned
``created_block_ids``, but anchors were quote-only, so following up on a block you just created
meant round-tripping a verbatim quote out of a fresh read. An id is matched by **exact
equality** under the same exactly-one-or-refuse discipline (a vanished id refuses with the id
named in its ``detail``), and live re-validation still applies: an id-anchored write is a
**compare-and-swap** on the anchored block's content (drift → ``stale-anchor``, no write). It
is also what an id-anchored round-trip editing projection builds on.
"""
from larkdocio.write.apply import apply, build_subspan_update, build_whole_paragraph_update
from larkdocio.write.client import (
    DOCX_REPLY_CARRIES_NO_URL,
    CreatedDocument,
    WriteClient,
    text_block,
    to_write_elements,
)
from larkdocio.write.compiler import (
    COMPILED_REQUEST_FAMILIES,
    RECONCILIATION_COMPILER_CONTRACT,
    compile_reconciliation,
)
from larkdocio.write.compose import (
    NOT_EXPRESSIBLE_CONSTRUCTS,
    ComposeCheck,
    ComposeRefusal,
    compose,
    compose_check,
    compose_insert,
)
from larkdocio.write.encode import (
    CREATABLE_BLOCK_TYPES,
    TABLE_BLOCK_TYPE,
    TABLE_CELL_BLOCK_TYPE,
    EncodedChild,
    block_type_for,
    create_batches,
    encode_block,
    encode_content,
    table_cell_spans,
    table_cell_texts,
)
from larkdocio.write.model import (
    COMMENT_FILE_TYPES,
    MAX_CHILDREN_PER_CALL,
    MAX_NEST_DEPTH,
    MAX_TABLE_CELLS,
    APPEND_ROW_INDEX,
    MAX_TABLE_COLUMNS,
    WHOLE_DOCUMENT,
    Anchor,
    AnchorById,
    ApplyLog,
    ApplyLogEntry,
    CommentThread,
    CreateCommentRequest,
    DeleteRequest,
    EditRequest,
    InsertPosition,
    InsertRequest,
    NewBlock,
    NewBlockKind,
    TextSpan,
    NewContent,
    NewParagraph,
    Refusal,
    RefusalReason,
    RefusedError,
    RemoveCommentRequest,
    GrowTableRequest,
    SubSpanEditRequest,
    TableLocator,
    WholeDocument,
)
from larkdocio.write.preview import Plan, PlanEntry, dry_run
from larkdocio.write.media import (
    OUT_OF_BAND_CREATABLE_BLOCK_TYPES,
    AuthoredImage,
    DocxImageBindError,
    DocxImageCreateError,
    DocxImageError,
    DocxMediaClient,
    put_file_in_document,
    put_image_in_document,
)
from larkdocio.write.reconcile import (
    AbsentBlockDisposition,
    ReconciliationEntry,
    ReconciliationPlan,
    ReconciliationState,
    reconcile,
)
from larkdocio.write.revision import (
    REVISION_GUARD_ACTIVE,
    REVISION_GUARD_UNAVAILABLE,
    revision_guard_semantics,
    revision_guard_status,
)
from larkdocio.write.resolve import (
    WRITE_HOSTILE_NODE_TYPES,
    ResolvedCell,
    ResolvedInsertion,
    ResolvedTarget,
    block_plain_text,
    resolve,
)

__all__ = [
    "WriteClient",
    # LD-583 — the create's typed answer, and the reason it has no url. Exported so a caller
    # can `isinstance` against it and read the disclosure without provoking an AttributeError.
    "CreatedDocument",
    "DOCX_REPLY_CARRIES_NO_URL",
    "put_file_in_document",
    "put_image_in_document",
    "AuthoredImage",
    "DocxMediaClient",
    "DocxImageError",
    "DocxImageCreateError",
    "DocxImageBindError",
    "OUT_OF_BAND_CREATABLE_BLOCK_TYPES",
    "text_block",
    "to_write_elements",
    "compose",
    "compose_check",
    "compose_insert",
    "ComposeCheck",
    "ComposeRefusal",
    "NOT_EXPRESSIBLE_CONSTRUCTS",
    "Anchor",
    "AnchorById",
    "ApplyLog",
    "ApplyLogEntry",
    "COMMENT_FILE_TYPES",
    "CommentThread",
    "CreateCommentRequest",
    "RemoveCommentRequest",
    "WHOLE_DOCUMENT",
    "WholeDocument",
    "EditRequest",
    "InsertRequest",
    "DeleteRequest",
    "SubSpanEditRequest",
    "GrowTableRequest",
    "InsertPosition",
    "NewParagraph",
    "NewBlock",
    "NewBlockKind",
    "TextSpan",
    "NewContent",
    "MAX_NEST_DEPTH",
    "MAX_CHILDREN_PER_CALL",
    "MAX_TABLE_CELLS",
    "MAX_TABLE_COLUMNS",
    "APPEND_ROW_INDEX",
    "CREATABLE_BLOCK_TYPES",
    "TABLE_BLOCK_TYPE",
    "TABLE_CELL_BLOCK_TYPE",
    "EncodedChild",
    "block_type_for",
    "encode_block",
    "encode_content",
    "table_cell_spans",
    "table_cell_texts",
    "create_batches",
    "TableLocator",
    "Refusal",
    "RefusalReason",
    "RefusedError",
    "resolve",
    "ResolvedTarget",
    "ResolvedCell",
    "ResolvedInsertion",
    "block_plain_text",
    "WRITE_HOSTILE_NODE_TYPES",
    "Plan",
    "PlanEntry",
    "dry_run",
    "reconcile",
    "compile_reconciliation",
    "COMPILED_REQUEST_FAMILIES",
    "RECONCILIATION_COMPILER_CONTRACT",
    "ReconciliationPlan",
    "ReconciliationEntry",
    "ReconciliationState",
    "AbsentBlockDisposition",
    "REVISION_GUARD_ACTIVE",
    "REVISION_GUARD_UNAVAILABLE",
    "revision_guard_status",
    "revision_guard_semantics",
    "apply",
    "build_whole_paragraph_update",
    "build_subspan_update",
]
