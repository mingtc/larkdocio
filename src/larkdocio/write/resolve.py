"""larkdocio.write.resolve — the anchor resolution engine (LD-066).

The **one hard problem** the writeback spike surfaced is anchor resolution, not the
API: a verbatim quote is *not* a
unique locator — on the live scratch doc one sentence matched **5** blocks and the value
``97.2%`` matched **6** — so "grep the quote and patch it" is ambiguous and unsafe.

This module resolves an :class:`~larkdocio.write.model.EditRequest` (LD-065: anchor =
verbatim **quote** + **breadcrumb** heading-path, plus a whole-paragraph replacement)
against the reader's **parsed node tree** — W0's ``block_id`` provenance on each block
node (LD-062) is the addressing key — to **exactly one target block or a typed
:class:`~larkdocio.write.model.Refusal`, never a guess, never a best-effort pick**:

* **quote** matches verbatim (substring) against a block's own **plain text**
  (:func:`block_plain_text` — the block's own inline/caption/url text, never its child
  blocks');
* **breadcrumb** (the ordered enclosing heading texts) narrows when the quote alone is
  ambiguous;
* a quote that matches **no** block → ``not-found``; that stays **ambiguous** after
  breadcrumb narrowing → ``ambiguous-N-candidates`` (carrying the candidate ids/count);
  that resolves to a **write-hostile** type (image / board / embed / synced — the
  spike's list, detected BY BLOCK TYPE) → ``write-hostile-target``, even if otherwise
  unique.

**ONE NARROWING, FOR DELETE ONLY.** An **image** block anchored by
:class:`~larkdocio.write.model.AnchorById` **deletes**: Lark's own ``children/batch_delete``
was measured to remove one, and the removal was confirmed by a read-back rather than by the
call's own ``code: 0`` (2026-08-19, beside a same-run text-block control). The reason behind
the fence is untouched — an image carries no text of its own, so it still refuses as an
**edit** target, a **sub-span** target and an **insertion reference**, and a **quote**-anchored
delete of one refuses too (naming the id route that works). **Every other hostile type** —
:data:`WRITE_HOSTILE_NODE_TYPES` minus :data:`DELETE_MEASURED_NODE_TYPES`, which is where
the answer is read rather than a count stated here — refuses **every** op, delete included:
their delete is **unmeasured, not refuted**. The rule lives in :func:`_resolve_delete`.

**Resolution failure vs POSITION failure (LD-131).** A refusal must name what actually went
wrong: a resolved-but-position-incapable target is **not** ``not-found``. An insert whose
reference resolved to a leaf refuses ``cannot-hold-children`` (``append-into``); one whose
reference resolved to the parent-less root refuses ``cannot-hold-siblings``
(``before``/``after``) — the LD-131 mirror. Every refusal this module returns carries a
**mandatory, actionable ``detail``** naming the identifier it is about (the quote, the span,
the row-key, the resolved ``block_id``) and the repair; see
:mod:`larkdocio.write.model.refusal`.

Fully **offline** — it walks an already-parsed node tree and makes **no** network /
``WriteClient`` call. Live anchor re-validation against the API is **S4** (LD-068). This
module never mutates the tree and never touches Markdown output.

**W2 / LD-071 — table-cell resolution.** :func:`resolve` also accepts a
:class:`~larkdocio.write.model.TableLocator` anchor (row-key key-cell quote +
column-target + breadcrumb) and resolves it to **exactly one table CELL block or a
typed refusal** — the spike proved a bare value is useless in a table (``97.2%`` in 6
blocks; Test 5), so a cell is located by coordinates instead:

* the **row** is the one whose **key cell** (column 0) plain text verbatim-matches the
  ``row_key`` (unique-or-refuse *within* the table — ``ambiguous-N-candidates`` on >1,
  ``not-found`` on none), reusing :func:`block_plain_text` over the cell's own text;
* the **column** is the ``column_index`` (0-based) or the column whose header cell
  (row 0) verbatim-matches ``column_header``; a target column absent from the table →
  ``column-not-found``;
* the **breadcrumb** narrows *which* table when the same key cell recurs (exactly as
  the narrative path uses it); still-ambiguous across tables → ``ambiguous-N-candidates``;
* a target cell **covered by a merge span** — or the merge **anchor** itself — refuses
  ``write-hostile-target`` (W2 is refuse-only for merges): coverage is **computed via
  the LD-050 occupancy grid** (:func:`~larkdocio.model.table_occupancy.covered_positions`,
  shared with the renderer), never read off the covered cell's own ``(1,1)`` span.

**LD-137 — by-id resolution.** Every block-level op now resolves its anchor through the ONE
shared seam :func:`_resolve_anchor`, which routes an
:class:`~larkdocio.write.model.AnchorById` (a bare ``block_id``) to :func:`_resolve_by_id` and
anything else to :func:`_resolve_narrative`. The by-id arm is the *same*
exactly-one-or-refuse engine — an id is matched by **exact string equality** (never a prefix
or a fuzzy match), so it resolves to exactly one block or refuses ``not-found`` /
``ambiguous`` / ``write-hostile``, each with the mandatory ``detail`` naming **the id**
(LD-131). The text-replacing ops (whole-block edit / sub-span) additionally require the target
to carry text of its **own** (:func:`_resolve_text_anchor`) — an id can address a pure
container a quote never could, and patching one has nothing to write.
"""
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

from larkdocio.model import (
    AddOnsNode,
    BitableNode,
    BoardNode,
    HeadingNode,
    IframeNode,
    ImageNode,
    Node,
    ReferenceBaseNode,
    ReferenceSyncedNode,
    SheetNode,
    SourceSyncedNode,
    StyledText,
    TableNode,
    Text,
)
from larkdocio.model.table_occupancy import covered_positions, merge_span
from larkdocio.model.tree import _TEXT_FALLBACK_FIELD_NAMES, _TEXT_FIELD_NAMES
from larkdocio.write.model import (
    MAX_TABLE_CELLS,
    AnchorById,
    DeleteRequest,
    GrowTableRequest,
    InsertPosition,
    InsertRequest,
    Refusal,
    SubSpanEditRequest,
    TableLocator,
    _describe_anchor,
)
from larkdocio.write.model.requests import APPEND_ROW_INDEX


# --------------------------------------------------------------------------- #
# Write-hostile block types — the spike's image / board / embed / synced list   #
# --------------------------------------------------------------------------- #
#
# Detected BY BLOCK TYPE (spike § Q3): text/heading/list/table are patchable as
# narrative text; anything living inside an image, board, embed, or synced block is
# NOT text-patchable and must refuse. A board carries no quotable text of its own, so
# its category is covered at the type level (a board can only ever be not-found or,
# reached, type-caught here).
WRITE_HOSTILE_NODE_TYPES: Tuple[type, ...] = (
    ImageNode,           # image (27)
    BoardNode,           # board / whiteboard (43)
    IframeNode,          # embed — iframe (26)
    BitableNode,         # embed — Base (18)
    SheetNode,           # embed — Sheet (30)
    ReferenceBaseNode,   # embed — Base named-view (53)
    SourceSyncedNode,    # synced — origin (49)
    ReferenceSyncedNode, # synced — reference (50)
)

# --------------------------------------------------------------------------- #
# LD-507 — the DELETE narrowing. THE REASON ABOVE IS PRESERVED; ONLY THE        #
# CONCLUSION FOR ONE OP, ON ONE MEASURED TYPE, IS SUPERSEDED.                    #
# --------------------------------------------------------------------------- #
#
# What stays true, unchanged and still enforced: an image / board / embed / synced
# block carries NO TEXT OF ITS OWN, so it is UN-PATCHABLE and UN-ANCHORABLE — it can
# be neither edited nor used as an insertion reference. That is the write spike's
# finding (§ Q3) and every arm above still enforces it.
#
# What was never measured, and is now: the spike's list was cut from a statement about
# PATCHING TEXT, and DELETE does not patch text — it removes a child range. LD-507
# asked Lark's own route the question once, against a disposable, and took the verdict
# from a READ-BACK rather than the call's `code: 0`:
#
#   POST …/documents/{doc}/blocks/{parent}/children/batch_delete against an image
#   block (27) authored by `put_image_in_document` → accepted, and the block is GONE:
#   the parent no longer lists it AND a direct `get_block` answers `1770002 not found`.
#   Same route, same parent, same run, against a TEXT block (2) → also gone (the
#   control, so the answer belongs to the block type and not to the harness).
#   Evidence, in the source repository (not in the wheel):
#   tests/captures/ld507-image-block-delete/captures/001-image-block-delete.json
#   (`_outcome: ROUTE_DELETES_IMAGE_BLOCK`), 2026-08-19.
#
# So this tuple is the measured narrowing, and it is EXACTLY as wide as its evidence
# (a claim is as wide as its evidence): ONE type, because only one was
# measured. Board
# (43), iframe (26), Base embed (18), Sheet embed (30), Base named-view (53) and both
# synced types (49/50) are UNMEASURED, NOT REFUTED — they keep refusing every op,
# including delete, and widening this tuple needs its own measurement, not an analogy.
DELETE_MEASURED_NODE_TYPES: Tuple[type, ...] = (
    ImageNode,           # image (27) — LD-507, measured 2026-08-19
)


@dataclass(frozen=True)
class ResolvedCell:
    """Table-cell context attached to a :class:`ResolvedTarget` when the anchor is a
    :class:`~larkdocio.write.model.TableLocator`.

    The narrative path resolves to a paragraph block and needs nothing beyond
    ``block_id`` + ``node``; a table cell carries more that the previewer surfaces
    (row/column identification) and the apply engine consumes (the inner text-block
    ids to read/patch, and the row-key for the double re-validation). Fields:

    * ``row`` / ``column`` — the resolved cell's 0-based grid coordinates (the human
      "which row / which column" identification the preview shows);
    * ``row_key`` — the locator's verbatim key-cell quote (what apply re-checks against
      the LIVE key cell to confirm the row identity still holds);
    * ``column_label`` — the **row-0** cell text for the column (or ``None`` when row 0
      carries no cell there) — the human-facing column name. Row 0 is a header row only
      when the table says so: for a ``header_row=False`` table this label is a data cell,
      which is why the field is not named ``header``;
    * ``target_text_block_id`` — the **inner** text block a whole-cell patch writes (a
      docx cell (type 32) wraps a child text block (type 2); *that* inner block is what
      patches "like a paragraph" — spike Test 5). ``None`` if the cell holds none;
    * ``key_text_block_id`` — the inner text block of the row's **key cell** (column 0),
      re-read at write time to confirm the row identity is unchanged.
    """

    row: int
    column: int
    row_key: str
    column_label: Optional[str] = None
    target_text_block_id: Optional[str] = None
    key_text_block_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "row": self.row,
            "column": self.column,
            "row_key": self.row_key,
            "column_label": self.column_label,
            "target_text_block_id": self.target_text_block_id,
            "key_text_block_id": self.key_text_block_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ResolvedCell":
        return cls(
            row=d["row"],
            column=d["column"],
            row_key=d["row_key"],
            column_label=d.get("column_label"),
            target_text_block_id=d.get("target_text_block_id"),
            key_text_block_id=d.get("key_text_block_id"),
        )


@dataclass(frozen=True)
class ResolvedInsertion:
    """Where an :class:`~larkdocio.write.model.InsertRequest`'s new block(s) would land
    — attached to a :class:`ResolvedTarget` when the resolved anchor is an insertion
    reference.

    The block-level insert resolver computes the **insertion point** from the resolved
    reference + the requested :class:`~larkdocio.write.model.InsertPosition`, so the
    dry-run preview shows a consumer exactly WHERE the paragraphs go (and the apply
    engine can drive ``create_children`` straight from it). Fields:

    * ``position`` — the :class:`~larkdocio.write.model.InsertPosition` value string
      (``"before"`` / ``"after"`` / ``"append-into"``) — the human-legible intent;
    * ``parent_block_id`` — the ``block_id`` of the block the new child(ren) attach to:
      the reference's **parent** for ``before`` / ``after``, or the **reference itself**
      for ``append-into``. ``None`` only in the degenerate no-locatable-parent case
      (which the resolver refuses before constructing this);
    * ``index`` — **ADVISORY.** The 0-based position the reference occupied in
      that parent's ordered child list **when the plan was built**: the reference's own
      index (``before``), one past it (``after``), or the parent's child count
      (``append-into``, i.e. last). It is a **description of the pre-batch snapshot, not a
      commitment about where the block lands** — see below.

    Computed from the OFFLINE parsed tree — whose parent/child structure mirrors the
    live docx block hierarchy (the reader builds children from each block's ``children``
    id list). The just-before-write live re-validation is the apply engine's job.

    **What the plan actually commits to.** The commitment is *positional relative
    to the reference*: ``position`` beside the block the anchor resolved to, in
    ``parent_block_id``. That is what :func:`~larkdocio.write.apply.apply` guarantees, and it
    derives the real child index off the **live** parent at write time (the discipline
    ``_apply_delete`` always had). ``index`` cannot also be a commitment: in a batch with
    two or more entries in one parent, the first landing write invalidates every later
    entry's pre-batch ordinal, and honouring those ordinals is exactly how same-parent
    multi-insert batches used to silently misplace every insert after the first. Making
    ``index`` predictive instead would mean re-planning sequentially inside ``apply()``,
    which would dissolve the one-tree-one-batch snapshot guarantee. So it is **disclosed as
    advisory rather than made true** — read it as "where the reference sat when you
    planned", and read the *position + reference* pair as the promise.
    """

    position: str
    parent_block_id: Optional[str]
    index: int

    def to_dict(self) -> dict:
        return {
            "position": self.position,
            "parent_block_id": self.parent_block_id,
            "index": self.index,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ResolvedInsertion":
        return cls(
            position=d["position"],
            parent_block_id=d.get("parent_block_id"),
            index=d["index"],
        )


@dataclass(frozen=True)
class ResolvedTarget:
    """Exactly one resolved block: its addressing ``block_id`` + the resolved node.

    The success arm of :func:`resolve`; the failure arm is a
    :class:`~larkdocio.write.model.Refusal`. A caller branches on
    ``isinstance(result, ResolvedTarget)``.

    ``cell`` is attached **only** when the anchor was a
    :class:`~larkdocio.write.model.TableLocator` — it carries the table
    cell's row/column identification + the inner text-block ids the previewer and apply
    engine need. It stays ``None`` for the narrative (paragraph) path, which is
    byte-unchanged.

    ``insertion`` is attached **only** when the request was an
    :class:`~larkdocio.write.model.InsertRequest` — it carries the computed
    insertion point (parent ``block_id`` + index + position) the previewer surfaces and
    the apply engine drives ``create_children`` from. For a
    :class:`~larkdocio.write.model.DeleteRequest`, an :class:`~larkdocio.write.model.EditRequest`,
    or a table edit it stays ``None``; ``block_id``/``node`` then designate the resolved
    target directly.
    """

    block_id: str
    node: Node
    cell: Optional[ResolvedCell] = None
    insertion: Optional[ResolvedInsertion] = None


# --------------------------------------------------------------------------- #
# Plain-text extraction — a block's OWN readable text (never its children)       #
# --------------------------------------------------------------------------- #

def _inline_plain_text(inlines) -> str:
    """Concatenate the readable text of an inline sequence.

    Duck-typed over the inline node model: ``content`` (Text / StyledText /
    InlineEquation), ``title`` (MentionDoc), ``markup`` (RawInline). MentionUser
    (a raw id) and UnsupportedInline (a placeholder variant) carry no plain text a
    consumer would verbatim-quote, so they contribute nothing.
    """
    parts: List[str] = []
    for x in inlines:
        content = getattr(x, "content", None)
        if isinstance(content, str):
            parts.append(content)
            continue
        title = getattr(x, "title", None)
        if isinstance(title, str):
            parts.append(title)
            continue
        markup = getattr(x, "markup", None)
        if isinstance(markup, str):
            parts.append(markup)
    return "".join(parts)


def _own_text_source(node: Node) -> Optional[str]:
    """The block's OWN plain text, or ``None`` when it carries **no text source of its own**.

    The single source-lookup :func:`block_plain_text` and :func:`_has_own_text` share, so the
    "what counts as a block's own text" rule is defined exactly once. Sources, in order: an
    inline ``content`` list (paragraph / heading / list-item / quote / code / source-synced /
    agenda title), a str ``content`` (block equation), a ``title`` inline list (page), a
    ``caption`` str (image — its visible text), a ``url`` str (iframe — its visible rendered
    text).

    ``None`` (no source at all) is what distinguishes a **container** — a table, a table
    cell, a grid, a callout, a quote container — whose text lives only in its *children*.
    Such a block can never be reached by a quote (its own text is empty, and an empty quote
    is refused outright), which is why the by-id path refuses one for a text-replacing op:
    the by-id mirror of an invariant the quote path already had.
    """
    content = getattr(node, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return _inline_plain_text(content)
    title = getattr(node, "title", None)
    if isinstance(title, list):
        return _inline_plain_text(title)
    caption = getattr(node, "caption", None)
    if isinstance(caption, str):
        return caption
    url = getattr(node, "url", None)
    if isinstance(url, str):
        return url
    return None


def block_plain_text(node: Node) -> str:
    """The block's OWN plain text — what the quote is matched against.

    Only the block's own content, **never** its child blocks: a heading's plain text
    is its heading line alone (not the whole section beneath it), so a section-spanning
    quote can't accidentally match a heading. The sources are :func:`_own_text_source`'s;
    a block with none of them → ``""`` (never a candidate).

    **This is the ANCHOR-MATCHING reduction, not the reading one — do not reuse it to read a
    document.** An anchor quote is text a person can literally quote back, so a ``@mention``
    (a raw id, which nobody quotes) contributes **nothing** here. That is deliberate and
    correct for anchoring, and it would be a silent content loss for reading: a paragraph
    saying "@alice please own this" reduces here to " please own this". To read a block's text,
    use ``larkdocio.model.plain_text``, which includes the mention token. The two return
    different strings on any block holding a mention, and that difference is pinned by a test
    so the pair cannot be quietly merged.
    """
    text = _own_text_source(node)
    return "" if text is None else text


def _has_own_text(node: Node) -> bool:
    """Whether ``node`` carries text of its **own** (rather than only in its children).

    ``True`` for every block a quote could ever resolve to; ``False`` for a pure container
    (table / cell / grid / callout / quote-container) — the blocks only an
    :class:`~larkdocio.write.model.AnchorById` can reach.
    """
    return _own_text_source(node) is not None


#: The fields a block's own text can live on **other than** the text-replacing bases' own
#: ``content`` runs — read from the reader's own two constants rather than retyped here, so
#: this module cannot drift from what ``larkdocio.model.plain_text`` actually consults (the
#: divergence between the two lookups is precisely what produced two false refusals).
_OFF_CONTENT_TEXT_FIELD_NAMES: Tuple[str, ...] = tuple(
    name for name in _TEXT_FIELD_NAMES + _TEXT_FALLBACK_FIELD_NAMES if name != "content"
)


def _off_content_text_home(node: Node) -> Optional[Tuple[str, str]]:
    """The ``(field_name, text)`` a block's own words live on when that field is **not**
    ``content`` — or ``None`` when the block's text is on ``content`` (or there is none).

    This is the DIAGNOSIS half of a fact the write bases deliberately do not act on. Two
    lookups answer "what text does this block have of its own", and they disagree by design:
    :func:`_own_text_source` (the anchor-matching / has-own-text basis) reads ``content``,
    ``title``, ``caption`` and ``url``; :func:`_text_run_plain_text` (the sub-span splitting
    basis) reads ``content`` runs **only**; and ``larkdocio.model.plain_text`` (the reading
    basis) additionally reads ``markup``. A block on the far side of any of those gaps has
    text a reader can see and no text the write bases can patch — and the refusals below used
    to describe that as either "the span is not in this block" (true of the basis, false-
    sounding about the document) or "this is a container, target its child" (false about the
    block, and advice that cannot succeed on a block with no children).

    **It widens no basis.** Nothing here is fed to a matcher, an occurrence check or a
    splitter — the only consumers are two refusal ``detail`` strings, so which blocks are
    editable is byte-unchanged. Widening a basis so a page ``title`` or a raw ``markup``
    became patchable is a NEW CAPABILITY and is ruled on where it belongs
    (:func:`_text_run_plain_text`'s docstring).
    """
    if isinstance(getattr(node, "content", None), (str, list)):
        return None
    for name in _OFF_CONTENT_TEXT_FIELD_NAMES:
        value = getattr(node, name, None)
        if isinstance(value, list):
            text = _inline_plain_text(value)
            if text:
                return name, text
        elif isinstance(value, str) and value:
            return name, value
    return None


#: Where the basis rule ("a block's own text lives wherever the block keeps it; a sub-span edit
#: reaches only the ``content`` text runs") is AUTHORED for consumers. The refusals below cite
#: it rather than restating it, so the rule has one statement and not three.
_TEXT_HOME_GUIDE_SECTION = (
    'larkdocio.guide() § "The tree\'s own types — which node is a heading, at what level"'
)


# --------------------------------------------------------------------------- #
# Tree walk — every block node with its breadcrumb (enclosing heading path)      #
# --------------------------------------------------------------------------- #

def _child_block_nodes(node: Node) -> List[Node]:
    """Every child BLOCK node, across the container shapes: ``children`` (most
    containers), ``cells`` (table), ``columns`` (grid, a list-of-lists).

    Flattens the ordered sibling sequences :func:`_child_sequences` enumerates — the
    single source of container-shape truth — in document order (children → cells →
    columns), keeping only ``Node`` entries. A fourth container shape is added in one
    place (``_child_sequences``) and both derive from it."""
    return [
        kid
        for seq in _child_sequences(node)
        for kid in seq
        if isinstance(kid, Node)
    ]


def _sweep(nodes, inherited_stack: Tuple[Tuple[int, str], ...], out: List[Tuple[Node, Tuple[str, ...]]]) -> None:
    """Document-order DFS collecting ``(node, breadcrumb)`` for every block node.

    ``inherited_stack`` is the enclosing heading stack as ``(level, text)`` pairs. A
    LOCAL copy is mutated as we sweep a sibling list so a container-internal heading
    never leaks its outline out past the container. Visiting a :class:`HeadingNode` of
    level L pops entries with level ≥ L then pushes ``(L, text)`` — the standard
    outline rule — and the heading's own children inherit the stack INCLUDING it. Every
    block's breadcrumb is the texts on the stack above it; this is correct whether
    headings nest their content as ``children`` or are flat document-order siblings
    (the common Feishu shape).
    """
    stack = list(inherited_stack)
    for node in nodes:
        breadcrumb = tuple(text for (_level, text) in stack)
        out.append((node, breadcrumb))
        if isinstance(node, HeadingNode):
            level = node.level
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, block_plain_text(node)))
            _sweep(_child_block_nodes(node), tuple(stack), out)
        else:
            children = _child_block_nodes(node)
            if children:
                _sweep(children, tuple(stack), out)


def _collect_blocks(root: Node) -> List[Tuple[Node, Tuple[str, ...]]]:
    """Every block node in ``root`` paired with its breadcrumb, in document order."""
    out: List[Tuple[Node, Tuple[str, ...]]] = []
    _sweep([root], (), out)
    return out


def _breadcrumb_matches(block_path: Tuple[str, ...], anchor_breadcrumb: Tuple[str, ...]) -> bool:
    """True when the anchor's breadcrumb is a contiguous sub-path of the block's
    heading path. An empty breadcrumb matches everything (no narrowing). Contiguous
    (not merely a subsequence) so ``(Results, Q3)`` matches a block under
    Results → Q3 but ``(Q3, Results)`` does not; a partial slice (just the nearest
    heading, or an outer one) still matches."""
    if not anchor_breadcrumb:
        return True
    n, m = len(block_path), len(anchor_breadcrumb)
    for i in range(n - m + 1):
        if block_path[i:i + m] == anchor_breadcrumb:
            return True
    return False


def _is_write_hostile(node: Node) -> bool:
    return isinstance(node, WRITE_HOSTILE_NODE_TYPES)


# --------------------------------------------------------------------------- #
# The projection-quote hedge — the commonest cause of a ``not-found`` refusal    #
#                                                                              #
# "Re-read the document and copy the quote verbatim" is the right advice for a   #
# typo and CANNOT WORK for the commonest failure: the quote was copied out of    #
# the Markdown projection, whose line markers (``- ``, ``# ``, ``> ``, ``1. ``,  #
# ``- [ ] ``) belong to the projection and are in no block's own text. Re-       #
# reading the Markdown and copying it again reproduces the refusal exactly. So    #
# the detail gains a clause — APPENDED, never a rewrite: the ordinary diagnosis   #
# survives byte-for-byte as the prefix, and the clause is EVIDENCE-GATED (the     #
# quote must carry a marker AND dropping it must match a real block), so a quote  #
# that is simply absent still reads exactly as it always did.                    #
# --------------------------------------------------------------------------- #

#: The line-leading markers the reader's Markdown projection adds while it flattens the
#: tree. Anchored to the START of the quote and applied repeatedly (a quoted list item
#: reads ``> - item``), with the projection's tab indentation for a nested item allowed
#: before each marker. A marker in the MIDDLE of a quote is ordinary text and is left
#: alone — stripping it would invent a match the retry would still refuse.
_PROJECTION_MARKER = re.compile(
    r"^[ \t]*(?:"
    r"#{1,6}[ \t]"           # heading, levels 1..6
    r"|>[ \t]?"              # quote / quote container
    r"|[-*+][ \t]\[[ xX]\][ \t]"  # todo, done or not
    r"|[-*+][ \t]"           # bullet
    r"|\d+[.)][ \t]"         # ordered item
    r")"
)

#: The invariant tail of the clause — the part that does not depend on what matched.
#: Kept as a constant so the wording has one home and the tests can read it.
PROJECTION_QUOTE_HEDGE_TAIL = (
    "So this quote came out of the Markdown projection, not off a block: re-reading the "
    "Markdown and copying the same line again reproduces this refusal, because the marker "
    "is added by the projection and is not in the block's own text. Quote the block's own "
    "text off the tree instead (parse_docx_tree), or — steadier — anchor by the block's own "
    "id with AnchorById(block_id=...), which no projection can spell wrong. The shipped "
    "guide's \"Symptoms you picked the wrong level\" table diagnoses this exact case. The "
    "projection's escaping is the same trap wearing another coat: a backslash the Markdown "
    "adds in front of a literal *, _ or | is not in the block either."
)


def strip_projection_markers(quote: str) -> Tuple[str, str]:
    """Split ``quote`` into ``(the projection markers it starts with, what is left)``.

    Returns ``("", quote)`` when the quote starts with no marker at all — indentation alone
    does not count, because a code block's leading whitespace **is** the block's own text.
    Applied repeatedly, so a bullet inside a quote container (``"> - item"``) sheds both.
    """
    markers, rest = "", quote
    while True:
        match = _PROJECTION_MARKER.match(rest)
        if not match:
            return markers, rest
        markers += match.group(0)
        rest = rest[match.end():]


def projection_quote_hedge(quote: str, root: Node) -> str:
    """The clause to append to a ``not-found`` detail when ``quote`` came from the projection.

    ``""`` — no clause — unless **both** halves of the evidence hold: the quote starts with a
    marker the projection adds, and dropping the marker(s) makes it match at least one real
    block's own text. That gate is what keeps the praised ordinary wording intact for every
    other case, including a quote that carries a marker and matches nothing (an ordinary
    absent quote that happens to start with a dash).

    Where exactly one block matches, the clause names it, so the consumer can anchor by id
    without a second read; where several do, it says how many and never picks one — the
    resolver's exactly-one-or-refuse rule holds inside the advice too.
    """
    markers, stripped = strip_projection_markers(quote)
    if not markers or not stripped.strip():
        return ""
    matches = [
        node for (node, _path) in _collect_blocks(root)
        if node.block_id is not None and stripped in block_plain_text(node)
    ]
    if not matches:
        return ""
    if len(matches) == 1:
        node = matches[0]
        where = (
            f"the block {node.block_id!r}, whose own text is "
            f"{block_plain_text(node)!r}"
        )
    else:
        where = f"{len(matches)} blocks (the marker is the only reason none of them matched)"
    return (
        f" — BUT the quote starts with the Markdown line marker {markers!r}, and without it "
        f"the text matches {where}. {PROJECTION_QUOTE_HEDGE_TAIL}"
    )


# --------------------------------------------------------------------------- #
# The whitespace near-miss — the OTHER commonest cause of ``not-found``          #
#                                                                              #
# Lark stores a **soft return** as a literal ``\n`` inside one text run, and     #
# the Markdown shows it as an ordinary line wrap — indistinguishable from        #
# terminal word-wrap. So a sentence a consumer copies out of the library's own    #
# dump can differ from the raw stored text by ONE INVISIBLE CHARACTER, and the   #
# engine — holding the tree, knowing exactly which block is meant — used to say  #
# only ``not-found``. The contract is not the defect and does not move: the       #
# match stays byte-verbatim, the refusal stays a refusal, and nothing here        #
# normalizes whitespace to force a match. What changes is that the near-miss is  #
# NAMED, evidence-gated exactly like the projection-marker hedge above: the      #
# clause is appended only when a whitespace-normalized comparison actually       #
# matches, so a quote that is simply absent reads as it always did (LD-455).      #
# --------------------------------------------------------------------------- #

#: The invariant tail of the whitespace clause — the part that does not depend on what
#: matched. One home for the wording, so the tests read it rather than re-spell it.
WHITESPACE_NEAR_MISS_TAIL = (
    "A quote is matched byte-verbatim against the block's RAW STORED text, and stored text "
    "can carry a soft return — a literal newline inside one paragraph — that the Markdown "
    "shows as an ordinary line wrap, so a sentence copied out of a dump can differ from what "
    "is stored by one invisible character. The library does NOT normalize whitespace to make "
    "this match: exactly-one-or-refuse is the contract, and a matcher that guessed across "
    "whitespace would guess across the case where guessing rewrites the wrong text. Anchor to "
    "a SHORT fragment that sits on one side of the wrap rather than to a whole sentence, or — "
    "steadier — anchor by the block's own id with AnchorById(block_id=...), which no "
    "whitespace can spell wrong."
)

#: What to do instead, for the case where nothing matched even after normalization. The
#: refusal used to say "re-read the document and copy the quote verbatim" — which is exactly
#: what the consumer had just done, so re-reading reproduces the refusal byte for byte.
NOT_FOUND_REMEDY = (
    "quote a SHORT fragment of the block's own text — parse the tree (parse_docx_tree) and "
    "take the fragment off the block rather than off the rendered Markdown, whose wraps and "
    "escaping are the projection's and not the block's — or anchor by the block's own id "
    "with AnchorById(block_id=...)"
)

_WHITESPACE_RUN = re.compile(r"\s+")


def normalize_whitespace(text: str) -> str:
    """``text`` with every run of whitespace collapsed to one space, ends stripped.

    Used **only** to diagnose — never to match. Two strings equal under this and unequal
    byte-for-byte differ *only* in whitespace, which is the precise fact the refusal reports.
    """
    return _WHITESPACE_RUN.sub(" ", text).strip()


def _diagnosable_near_miss(quote: str) -> str:
    """``normalize_whitespace(quote)`` if a whitespace near-miss is a claim worth making
    about it, else ``""``.

    The gate is **two or more words**, and it is not cosmetic. A single-token quote — ``"- "``,
    ``"1. "``, a bare value — normalizes to something a long document contains by accident, so
    "differs only in whitespace" would be technically true and useless, and it would fire on
    quotes whose real defect is something else entirely. The trap this diagnoses lives
    *between* words: a soft return sits at a wrap, and a quote that spans one has words on
    both sides of it.
    """
    normalized = normalize_whitespace(quote)
    return normalized if " " in normalized else ""


# LD-636 / round-4 audit: the binary search below replaced an exhaustive scan (measured
# 3.3 s at 1200 words end-to-end through dry_run, x10 for a ten-entry plan; ~0.1 s after).
# Same-result by construction, and held against the pre-LD-636 scan as an ORACLE over
# randomized inputs by the property check in the suite's anchor-quote-whitespace module
# (in the source repository, tests/test_anchor_quote_whitespace.py) -- including the tie-break.
def longest_matching_fragment(quote: str, stored: str) -> str:
    """The longest run of ``quote``'s words that IS verbatim in ``stored``, or ``""``.

    The concrete repair the refusal hands back: a consumer told only "your whitespace is
    wrong" still has to work out where. A word run is the right unit because a whitespace-only
    difference lives *between* words — every word of the quote is verbatim in the stored text,
    and the run breaks exactly at the wrap.

    **Tie-breaking is part of the contract:** the winner is the LONGEST run measured in
    *characters*, and among equal-length runs the one that starts EARLIEST in the quote.

    The search is a **binary search per start**, not a scan. This function runs *only* on the
    refusal path — the exact scenario the whitespace hedge exists to diagnose — where the scan
    it replaced spent seconds on a long quote end-to-end through :func:`resolve`, once per plan
    entry, so a plan preview could feel hung; a consumer who kills it loses the refusal detail
    the time was being spent on. Containment is **monotone in run length for a fixed start** —
    a run that is not in ``stored`` cannot become one by growing — so the maximum run per
    start needs ``O(log w)`` containment tests, not ``O(w)``. It returns the **identical**
    string, not a cheaper approximation of one: a cap or a truncation would change what the
    refusal tells you and is not on the table.
    """
    words = quote.split()
    total = len(words)
    if not total:
        return ""
    # ``offsets[k]`` = characters consumed by ``words[:k]`` joined with single spaces,
    # so ``words[i:j]`` joins to ``offsets[j] - offsets[i] - 1`` characters (j > i).
    offsets = [0] * (total + 1)
    for k, word in enumerate(words):
        offsets[k + 1] = offsets[k] + len(word) + 1
    best = ""
    for i in range(total):
        # The longest run this start could possibly yield. It shrinks as ``i`` grows, so
        # once it cannot beat ``best`` no later start can either. (Only a STRICTLY longer
        # run replaces ``best`` — which is what makes the earliest start win a tie.)
        if offsets[total] - offsets[i] - 1 <= len(best):
            break
        # Binary-search the largest ``j`` with ``" ".join(words[i:j])`` in ``stored``.
        # ``j == i`` (the empty run) is vacuously true, so ``lo`` starts there.
        lo, hi = i, total
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if " ".join(words[i:mid]) in stored:
                lo = mid
            else:
                hi = mid - 1
        if lo > i and offsets[lo] - offsets[i] - 1 > len(best):
            best = " ".join(words[i:lo])
    return best


def _whitespace_repair(quote: str, stored: str) -> str:
    """The "and here is what to type instead" half, when a fragment can be offered."""
    fragment = longest_matching_fragment(quote, stored)
    if not fragment or fragment == quote:
        return ""
    return f", and the fragment {fragment!r} of your quote DOES match it verbatim"


def whitespace_near_miss_hedge(quote: str, root: Node) -> str:
    """The clause to append to a ``not-found`` detail when ``quote`` differs from a real
    block's own text **only in whitespace**.

    ``""`` — no clause — unless a whitespace-normalized comparison actually matches, which
    is what keeps the ordinary diagnosis intact for an ordinary typo. Exactly one match is
    named, with the stored spelling (``repr``, so the invisible ``\\n`` is visible) and a
    fragment that does match; **more than one** is reported as ambiguous after normalization
    with every candidate id — the resolver's exactly-one-or-refuse rule holds inside the
    advice too, and a diagnostic that picked one would be guessing where the matcher refuses.
    """
    normalized = _diagnosable_near_miss(quote)
    if not normalized:
        return ""
    matches = [
        node for (node, _path) in _collect_blocks(root)
        if node.block_id is not None
        and quote not in block_plain_text(node)
        and normalized in normalize_whitespace(block_plain_text(node))
    ]
    if not matches:
        return ""
    if len(matches) == 1:
        node = matches[0]
        stored = block_plain_text(node)
        return (
            f" — BUT block {node.block_id!r} differs only in whitespace: its own text is "
            f"{stored!r}{_whitespace_repair(quote, stored)}. {WHITESPACE_NEAR_MISS_TAIL}"
        )
    ids = [node.block_id for node in matches]
    return (
        f" — BUT the quote is ambiguous after whitespace normalization: it differs only in "
        f"whitespace from {len(ids)} blocks (candidate ids: {', '.join(ids)}), and the "
        f"resolver never auto-picks. {WHITESPACE_NEAR_MISS_TAIL}"
    )


def not_found_hedge(quote: str, root: Node) -> str:
    """The evidence-gated clause for a ``not-found`` quote — whichever of the two real
    causes the evidence supports, and ``""`` when neither does.

    The projection-marker cause is tried first because it is the stronger evidence (a marker
    is a *visible* piece of the projection that is in no block's text); the whitespace cause
    is tried second, and once more with the markers dropped, so a quote copied off a wrapped
    **list item** — which carries both defects at once — is still diagnosed.
    """
    hedge = projection_quote_hedge(quote, root)
    if hedge:
        return hedge
    hedge = whitespace_near_miss_hedge(quote, root)
    if hedge:
        return hedge
    markers, stripped = strip_projection_markers(quote)
    if not markers or not stripped.strip():
        return ""
    hedge = whitespace_near_miss_hedge(stripped, root)
    if not hedge:
        return ""
    return (
        f" — the quote also starts with the Markdown line marker {markers!r}, which the "
        f"projection adds and no block's text carries{hedge}"
    )


# --------------------------------------------------------------------------- #
# Container topology — can a block parent children, and where does a child sit?  #
# (W3 / LD-075 — the insert resolver computes the insertion point from these.)   #
# --------------------------------------------------------------------------- #

def _can_hold_children(node: Node) -> bool:
    """Whether ``node`` is structurally a **container** — a block that can parent child
    blocks (so an ``append-into`` insertion is meaningful).

    Decided by the presence of a child-list attribute (``children`` / ``cells`` /
    ``columns``), NOT by whether it currently holds any: a heading with zero flat
    children (the common Feishu shape — its section content are document-order siblings)
    can still parent a child. A leaf paragraph (:class:`~larkdocio.model.TextNode` and
    the other text-only blocks — quote / code / equation) carries only inline
    ``content``, no child-list, so it returns ``False`` and ``append-into`` refuses
    :meth:`~larkdocio.write.model.Refusal.cannot_hold_children`.
    """
    for attr in ("children", "cells", "columns"):
        if isinstance(getattr(node, attr, None), list):
            return True
    return False


def _child_count(node: Node) -> int:
    """The number of direct child blocks of a container ``node`` — the ``append-into``
    insertion index (the new block(s) land last). Counts across the container shapes
    (``children`` / ``cells`` / ``columns``) via the shared :func:`_child_block_nodes`."""
    return len(_child_block_nodes(node))


def _child_sequences(node: Node) -> List[List[Node]]:
    """Every ORDERED sibling sequence ``node`` owns — the lists a direct child sits in.

    Most containers own one ``children`` (or ``cells``) list; a grid owns one list per
    ``columns`` entry. Each returned list is a live sibling ordering, so a child's index
    within it is its position among its siblings (what ``before`` / ``after`` need)."""
    seqs: List[List[Node]] = []
    children = getattr(node, "children", None)
    if isinstance(children, list):
        seqs.append(children)
    cells = getattr(node, "cells", None)
    if isinstance(cells, list):
        seqs.append(cells)
    columns = getattr(node, "columns", None)
    if isinstance(columns, list):
        for col in columns:
            if isinstance(col, list):
                seqs.append(col)
    return seqs


def _locate_parent_index(root: Node, target: Node) -> Optional[Tuple[Node, int]]:
    """Find ``target``'s parent block + its index within that parent's ordered child
    sequence, walking ``root`` in document order. Returns ``None`` when ``target`` has no
    parent in the tree (it IS the root) — a degenerate before/after case the caller
    refuses.

    Matches by object **identity** (``is``) — :func:`resolve` returns the very node from
    the tree, so identity is exact and never confuses two equal-content siblings.
    """

    def _visit(node: Node) -> Optional[Tuple[Node, int]]:
        for seq in _child_sequences(node):
            for i, child in enumerate(seq):
                if child is target:
                    return (node, i)
            for child in seq:
                if isinstance(child, Node):
                    found = _visit(child)
                    if found is not None:
                        return found
        return None

    return _visit(root)


# --------------------------------------------------------------------------- #
# Table-cell resolution (W2 / LD-071) — a TableLocator → one cell or refusal     #
# --------------------------------------------------------------------------- #

def _cell_plain_text(cell: Node) -> str:
    """A table cell's OWN readable text — the concatenation of :func:`block_plain_text`
    over its descendant blocks.

    A :class:`~larkdocio.model.TableCellNode` carries no text of its own (its
    ``block_plain_text`` is ``""``); the text lives in its child block(s) — a plain
    cell holds one :class:`~larkdocio.model.TextNode`. This reuses the same
    :func:`block_plain_text` the narrative path matches against (each block's own
    inline text, never re-descending past it — the walk below supplies the descent),
    so a cell's row-key/header match is verbatim-consistent with a paragraph's.
    """
    parts: List[str] = []

    def _gather(node: Node) -> None:
        parts.append(block_plain_text(node))
        for child in _child_block_nodes(node):
            _gather(child)

    for child in _child_block_nodes(cell):
        _gather(child)
    return "".join(parts)


def _first_text_block(cell: Node) -> Optional[Node]:
    """The cell's text-bearing block — **the one block a whole-cell patch writes to**.

    A plain value cell wraps exactly ONE inner text block (docx cell type 32 → child
    text block type 2); *that* inner block is what a cell edit patches, because it is a
    paragraph-shaped block carrying ``elements`` — which is precisely why "a cell patches
    like a paragraph" (spike Test 5, S3/LD-072). Returns the first descendant block (in
    document order) that carries an inline ``content`` list (a text-bearing block, even
    an empty one), or ``None`` when the cell holds no text-bearing block.

    The **node**, not just its id, because the cell path's plan-time preconditions read the
    block's own inline content (its review anchors — see
    :func:`_resolve_whole_cell_edit`): the *scope of the patch* and the *scope of those
    checks* must be the same block by construction, or a check could refuse for a block the
    write never touches (or miss the one it does).
    """

    def _walk(node: Node) -> Optional[Node]:
        for child in _child_block_nodes(node):
            if isinstance(getattr(child, "content", None), list) and child.block_id is not None:
                return child
            deeper = _walk(child)
            if deeper is not None:
                return deeper
        return None

    return _walk(cell)


def _first_text_block_id(cell: Node) -> Optional[str]:
    """The ``block_id`` of the cell's text-bearing block (see :func:`_first_text_block`)."""
    block = _first_text_block(cell)
    return None if block is None else block.block_id


def _num_rows(n_cells: int, col_size: int) -> int:
    """How many (possibly ragged) rows ``n_cells`` folds into at ``col_size``."""
    if col_size <= 0:
        col_size = 1
    return (n_cells + col_size - 1) // col_size


def _row_zero_labels(table: TableNode) -> str:
    """The table's **row-0** cell texts, as a quoted did-you-mean list (LD-131).

    A ``column-not-found`` refusal that merely says "no such column" makes the consumer
    re-read the whole document to learn the real column names; listing them in the
    ``detail`` is the actionable half. Cells are quoted so a label containing a comma or
    a delimiter stays unambiguous.

    **They are row-0 cells, and only sometimes headers** (LD-636). This used to
    be ``_header_labels`` and the refusal used to present its output as *"its headers"* —
    which, for a table whose own ``header_row`` is ``False``, named **data** cells as
    headers inside the very list a consumer was handed so they would not have to re-read
    the document. ``column_header`` is *defined* as the text in row 0 and the resolver is
    right to match it there (a ruling which declined gating it on ``header_row``
    because that would remove a working capability); so what is corrected is the **word**,
    not the lookup. :func:`_row_zero_disclosure` says which of the two this table is.
    """
    col_size = table.col_size or 1
    labels = [
        repr(_cell_plain_text(cell))
        for cell in table.cells[:col_size]
        if isinstance(cell, Node)
    ]
    return f"[{', '.join(labels)}]" if labels else "[] (row 0 holds no addressable cells)"


def _row_zero_disclosure(table: TableNode) -> str:
    """The parenthetical that tells a ``column_header`` miss what row 0 actually **is**.

    Two different situations produce the identical miss, and a consumer can only act on
    the right one: a header-ful table means the column names really are these, whereas a
    ``header_row=False`` table means the strings being offered are the first data row and
    the positional address (``column_index``) is the tool for that job. ``header_row`` is
    read **here and only here** — for the wording. It does not, and by that ruling must not,
    gate what ``column_header`` resolves.
    """
    if table.header_row:
        return "column_header matches row 0, this table's header row"
    return (
        "column_header always matches row 0, and this table declares header_row=False — "
        "so row 0 holds DATA, not headers; address a column positionally with column_index"
    )


def _rows_matching_key(table: TableNode, row_key: str) -> List[int]:
    """Indices of the rows whose **key cell** (column 0) verbatim-contains ``row_key``.

    The key cell of row ``r`` is the flat cell at ``r * col_size`` — the row-header
    column (spike Test 5: the row label ``"On-time delivery"`` sits in column 0). Match
    is verbatim substring on the cell's own text (:func:`_cell_plain_text`), mirroring
    the narrative quote match.
    """
    col_size = table.col_size or 1
    n = len(table.cells)
    out: List[int] = []
    for r in range(_num_rows(n, col_size)):
        key_idx = r * col_size
        if key_idx >= n:
            continue
        key_cell = table.cells[key_idx]
        if isinstance(key_cell, Node) and row_key in _cell_plain_text(key_cell):
            out.append(r)
    return out


def _resolve_column(table: TableNode, locator: TableLocator, row_idx: int) -> Union[int, Refusal]:
    """The 0-based column index the locator's column-target designates, or a refusal.

    ``column_index`` is used directly (out of ``0..col_size-1`` → ``column-not-found``).
    ``column_header`` matches the header cells (row 0) verbatim: no match →
    ``column-not-found``; >1 match → ``ambiguous-N-candidates`` (carrying the candidate
    target-cell ids in the resolved row — the resolver never auto-picks a column).

    Every refusal carries a mandatory, actionable ``detail`` (LD-131): the table's id, the
    column designation that failed, and — for a missing header — the headers that DO exist
    (a did-you-mean the consumer can act on without a re-read).
    """
    col_size = table.col_size or 1
    n = len(table.cells)

    if locator.column_index is not None:
        c = locator.column_index
        if c < 0 or c >= col_size:
            return Refusal.column_not_found(
                detail=(
                    f"table {table.block_id} has {col_size} column(s); the locator's "
                    f"column_index={c} is out of range 0..{col_size - 1}"
                )
            )
        return c

    header = locator.column_header
    matching_cols = [
        c
        for c in range(col_size)
        if c < n and isinstance(table.cells[c], Node) and header in _cell_plain_text(table.cells[c])
    ]
    if not matching_cols:
        return Refusal.column_not_found(
            detail=(
                f"no cell in row 0 of table {table.block_id} contains {header!r} "
                f"({_row_zero_disclosure(table)}); row 0 reads {_row_zero_labels(table)}"
            )
        )
    if len(matching_cols) > 1:
        candidate_ids = []
        for c in matching_cols:
            i = row_idx * col_size + c
            if i < n and isinstance(table.cells[i], Node) and table.cells[i].block_id is not None:
                candidate_ids.append(table.cells[i].block_id)
        return Refusal.ambiguous(
            candidate_ids,
            detail=(
                f"column header {header!r} matched {len(matching_cols)} columns "
                f"{matching_cols} in table {table.block_id} (candidate target-cell ids: "
                f"{', '.join(candidate_ids) or 'none addressable'}) — the resolver never "
                f"auto-picks a column; use column_index instead"
            ),
        )
    return matching_cols[0]


def _locate_table_row(locator: TableLocator,
                      root: Node) -> Union[Tuple[TableNode, int], Refusal]:
    """The **table half** of a :class:`~larkdocio.write.model.TableLocator`: which table, and
    which row in it — ``(table, row_index)`` or a typed refusal.

    Lifted out of :func:`_resolve_table` verbatim (LD-575) because the table-grow op needs
    exactly this and nothing after it: it addresses the **table**, not a cell, so it must not
    inherit the column lookup or the merge-coverage rules that only a cell target can meet.
    The alternative was a second copy of the row-key match, the breadcrumb narrowing and the
    two ambiguity refusals — a parallel definition of *which table did you mean*, which is the
    one thing a locator vocabulary cannot afford to have two of.

    Behaviour is unchanged for the cell path: :func:`_resolve_table` calls this first and its
    refusals are byte-identical to the ones it used to build inline.
    """
    row_key = locator.row_key
    if not row_key:
        # A degenerate locator with no row-key locates nothing (an empty string is a
        # substring of every cell — refusing avoids a spurious all-match).
        return Refusal.row_not_found(
            detail=(
                "the TableLocator carries an empty row_key — an empty key is a substring "
                "of every cell, so it locates no row; supply the verbatim text of the "
                "row's key cell (column 0)"
            )
        )

    breadcrumb = locator.breadcrumb

    # Every addressable table paired with its enclosing heading path (reuses the shared
    # tree walk — no fork). A table with no block_id can't be addressed → excluded.
    tables = [
        (node, path)
        for (node, path) in _collect_blocks(root)
        if isinstance(node, TableNode) and node.block_id is not None
    ]

    # Candidate tables: those with >=1 row whose key cell matches the row-key.
    matching: List[Tuple[TableNode, Tuple[str, ...], List[int]]] = []
    for (table, path) in tables:
        rows = _rows_matching_key(table, row_key)
        if rows:
            matching.append((table, path, rows))
    if not matching:
        # No table anywhere holds a matching row key (table-not-found / row-not-found
        # both map to NOT_FOUND per the LD-070 mapping).
        return Refusal.table_not_found(
            detail=(
                f"no table's key cell (column 0) contains the row_key {row_key!r} — "
                f"searched {len(tables)} addressable table(s) in the document"
            )
        )

    # Breadcrumb narrows WHICH table when the key cell recurs across tables.
    if len(matching) > 1 and breadcrumb:
        narrowed = [m for m in matching if _breadcrumb_matches(m[1], breadcrumb)]
        if len(narrowed) == 1:
            matching = narrowed
        elif not narrowed:
            # The key cell matched tables, but none under the anchor's heading path.
            return Refusal.table_not_found(
                detail=(
                    f"the row_key {row_key!r} matched key cells in {len(matching)} "
                    f"table(s), but none under the locator's breadcrumb "
                    f"{tuple(breadcrumb)}"
                )
            )
        else:
            matching = narrowed  # still ambiguous → the ambiguous-table refusal below

    if len(matching) > 1:
        table_ids = [m[0].block_id for m in matching]
        return Refusal.ambiguous_table(
            table_ids,
            detail=(
                f"the row_key {row_key!r} matched key cells in {len(table_ids)} tables "
                f"(candidate table ids: {', '.join(table_ids)}) — the resolver never "
                f"auto-picks; narrow with a breadcrumb naming the enclosing heading path"
            ),
        )

    table, _path, rows = matching[0]
    col_size = table.col_size or 1

    # Row unique-or-refuse WITHIN the table.
    if len(rows) > 1:
        key_ids = [table.cells[r * col_size].block_id for r in rows]
        return Refusal.ambiguous_row(
            key_ids,
            detail=(
                f"the row_key {row_key!r} matched {len(rows)} rows {rows} in table "
                f"{table.block_id} (candidate key-cell ids: "
                f"{', '.join(str(k) for k in key_ids)}) — the resolver never auto-picks; "
                f"use a row_key unique within the table"
            ),
        )
    return table, rows[0]


def _resolve_table(locator: TableLocator, root: Node) -> Union[ResolvedTarget, Refusal]:
    """Resolve a :class:`~larkdocio.write.model.TableLocator` to exactly one cell block
    or a typed refusal. See the module docstring for the full contract."""
    located = _locate_table_row(locator, root)
    if isinstance(located, Refusal):
        return located
    table, row_idx = located
    row_key = locator.row_key
    col_size = table.col_size or 1

    # Column by the target designation.
    col = _resolve_column(table, locator, row_idx)
    if isinstance(col, Refusal):
        return col
    col_idx = col

    n = len(table.cells)
    i = row_idx * col_size + col_idx
    if i >= n:
        # The grid position has no cell in this (ragged) row → no such column here.
        return Refusal.column_not_found(
            detail=(
                f"table {table.block_id} row {row_idx} (row_key {row_key!r}) has no cell "
                f"at column {col_idx} — the table is ragged ({n} cells at col_size "
                f"{col_size})"
            )
        )
    target = table.cells[i]

    # Merged/covered target refuses write-hostile (W2 is refuse-only for merges).
    # Coverage is COMPUTED from preceding anchors' spans via the shared LD-050 grid —
    # a covered cell's own span reads (1,1) and must not be trusted.
    covered = covered_positions(n, table.merges or [], col_size)
    if (row_idx, col_idx) in covered:
        return Refusal.write_hostile(
            detail=(
                f"the target cell at (row {row_idx}, column {col_idx}) of table "
                f"{table.block_id} (row_key {row_key!r}) is COVERED by a merge span — a "
                f"merged/covered cell is refused (it holds no value of its own); target an "
                f"unmerged cell, or unmerge first"
            )
        )
    rs, cs = merge_span(table.merges or [], i)
    if rs > 1 or cs > 1:
        # The target cell is itself a merge anchor — writing it is writing INTO a
        # merged cell, refused this tranche ("merged / covered targets refuse").
        return Refusal.write_hostile(
            detail=(
                f"the target cell at (row {row_idx}, column {col_idx}) of table "
                f"{table.block_id} (row_key {row_key!r}) is a merge ANCHOR spanning "
                f"{rs}x{cs} cells — writing it writes INTO a merged cell, which is refused; "
                f"target an unmerged cell, or unmerge first"
            )
        )

    if not isinstance(target, Node) or target.block_id is None:
        # Defensive: an unaddressable cell (no block_id) can't be a write target.
        return Refusal.column_not_found(
            detail=(
                f"the resolved cell at (row {row_idx}, column {col_idx}) of table "
                f"{table.block_id} (row_key {row_key!r}) carries no block_id — it cannot "
                f"be addressed as a write target"
            )
        )

    # W2 / LD-072 — attach the cell context the S3 previewer + S4 apply engine consume:
    # row/column identification, the row-0 cell label (a header only when the table says
    # so - LD-636), and the INNER text-block ids
    # (the target's — patched; the key cell's — re-read for the row-identity check).
    key_cell = table.cells[row_idx * col_size]
    header_cell = table.cells[col_idx] if col_idx < n else None
    column_label = (
        _cell_plain_text(header_cell) if isinstance(header_cell, Node) else None
    )
    cell_ctx = ResolvedCell(
        row=row_idx,
        column=col_idx,
        row_key=row_key,
        column_label=column_label,
        target_text_block_id=_first_text_block_id(target),
        key_text_block_id=(
            _first_text_block_id(key_cell) if isinstance(key_cell, Node) else None
        ),
    )
    return ResolvedTarget(block_id=target.block_id, node=target, cell=cell_ctx)


# --------------------------------------------------------------------------- #
# Narrative anchor resolution — quote + breadcrumb → one block or a refusal      #
# (shared by the EditRequest path AND the W3 insert/delete reference/target)     #
# --------------------------------------------------------------------------- #

def _resolve_narrative(anchor, root: Node, *,
                       skip_write_hostile: bool = False) -> Union[ResolvedTarget, Refusal]:
    """Resolve a narrative :class:`~larkdocio.write.model.Anchor` (quote + breadcrumb)
    to exactly one :class:`ResolvedTarget` or a typed :class:`Refusal`.

    The core exactly-one-or-refuse engine, extracted so the W1/W2 :class:`EditRequest`
    path AND the W3 insert **reference** / delete **target** anchors resolve through the
    **same** logic (reused, never forked): quote-match candidates → breadcrumb-narrow if
    still ambiguous → ``not-found`` / ``ambiguous`` refusals → write-hostile type check
    on the unique survivor.
    """
    quote = anchor.quote
    breadcrumb = anchor.breadcrumb

    if not quote:
        # A degenerate anchor with no quote locates nothing (an empty string is a
        # substring of every block — refusing here avoids a spurious all-match).
        return Refusal.not_found(
            detail=(
                "the anchor carries an empty quote — an empty quote is a substring of "
                "every block, so it locates nothing; supply the verbatim text you want "
                "to anchor to"
            )
        )

    # AC2 — quote match: verbatim substring on each block's OWN plain text. Only
    # addressable blocks (a real block_id) are candidates; the empty RawBlock("")
    # dangling-child sentinel (no id, no text) is excluded on both counts.
    candidates = [
        (node, path)
        for (node, path) in _collect_blocks(root)
        if node.block_id is not None and quote in block_plain_text(node)
    ]

    # AC5 — nothing matched. The ordinary diagnosis is unchanged (and correct for a typo);
    # a quote copied out of the Markdown projection additionally gets the clause that names
    # its real cause, because for that case the re-read advice alone cannot succeed.
    if not candidates:
        return Refusal.not_found(
            detail=(
                f"no block's own text contains the anchor quote {quote!r} — the quote is "
                f"matched verbatim (substring) against each block's OWN text, never its "
                f"children's; {NOT_FOUND_REMEDY}"
            ) + not_found_hedge(quote, root)
        )

    # AC3 — breadcrumb narrows an ambiguous quote by enclosing heading path.
    if len(candidates) > 1 and breadcrumb:
        narrowed = [(node, path) for (node, path) in candidates if _breadcrumb_matches(path, breadcrumb)]
        if len(narrowed) == 1:
            candidates = narrowed
        elif not narrowed:
            # The quote matched blocks, but none under the anchor's heading path — the
            # combined (quote + breadcrumb) anchor identifies no block.
            return Refusal.not_found(
                detail=(
                    f"the anchor quote {quote!r} matched {len(candidates)} block(s), but "
                    f"none under the anchor's breadcrumb {tuple(breadcrumb)} — correct the "
                    f"breadcrumb (the ordered enclosing heading texts) or drop it"
                )
            )
        else:
            candidates = narrowed  # still ambiguous → the ambiguous refusal below

    # AC4 — still more than one: refuse, carrying the candidate ids (never auto-pick).
    if len(candidates) > 1:
        candidate_ids = [node.block_id for (node, _path) in candidates]
        return Refusal.ambiguous(
            candidate_ids,
            detail=(
                f"the anchor quote {quote!r} matched {len(candidate_ids)} blocks "
                f"(candidate ids: {', '.join(candidate_ids)}) — the resolver never "
                f"auto-picks; lengthen the quote or add a breadcrumb naming the enclosing "
                f"heading path"
            ),
        )

    # AC1 — exactly one survivor.
    node, _path = candidates[0]

    # AC6 — write-hostile target refuses even though it is otherwise unique.
    # ``skip_write_hostile`` is set by ONE caller — :func:`_resolve_delete` — which owns
    # the delete op's own, narrower hostility rule (LD-507). Default False, so every
    # other path through here is byte-unchanged.
    if _is_write_hostile(node) and not skip_write_hostile:
        return Refusal.write_hostile(
            detail=(
                f"the anchor quote {quote!r} resolved to block {node.block_id}, a "
                f"{type(node).__name__} — image / board / embed / synced content is not "
                f"text-patchable, so it can be neither edited nor used as an insertion "
                f"reference; anchor to a narrative paragraph instead"
            )
        )

    return ResolvedTarget(block_id=node.block_id, node=node)


# --------------------------------------------------------------------------- #
# By-id resolution (LD-137) — a block_id → one block/refusal                     #
# --------------------------------------------------------------------------- #

def _resolve_by_id(anchor, root: Node, *,
                   skip_write_hostile: bool = False) -> Union[ResolvedTarget, Refusal]:
    """Resolve an :class:`~larkdocio.write.model.AnchorById` to exactly one
    :class:`ResolvedTarget` or a typed :class:`Refusal`.

    The **same** exactly-one-or-refuse engine as the narrative path, differing only in how
    the block is located: ``block_id`` is matched by **exact string equality** over the
    shared document-order walk (:func:`_collect_blocks`) — never a prefix, a suffix, a
    case-fold or any other guess, because an id is an opaque handle and a "near" id is
    somebody else's block. So:

    * **no match** → :meth:`~larkdocio.write.model.Refusal.not_found`. The three real-world
      causes — the id never existed, it belongs to **another document**, or its block was
      **deleted** — are one refusal with the id named in the ``detail`` (LD-131), plus the
      fact that the match is exact (so hunting for a near-miss is pointless) and the repair
      (re-read + re-plan);
    * **more than one match** → :meth:`~larkdocio.write.model.Refusal.ambiguous` carrying the
      candidates. A well-formed document cannot hold a duplicate ``block_id``, so this arm is
      defensive — but "never auto-pick" is absolute, and silently taking the first match of a
      malformed tree is exactly the guess the engine does not make;
    * a unique but **write-hostile** survivor (image / board / embed / synced, by type) →
      :meth:`~larkdocio.write.model.Refusal.write_hostile`, naming the id and the node type.
      *Hostile, not not-found*: the id **was** found, so "find a better id" is the wrong
      repair.
    """
    block_id = anchor.block_id
    matches = [
        node
        for (node, _path) in _collect_blocks(root)
        if node.block_id is not None and node.block_id == block_id
    ]

    if not matches:
        return Refusal.not_found(
            detail=(
                f"no block in this document has block_id {block_id!r} — an id anchor is "
                f"matched by EXACT equality (never a prefix or a fuzzy match), so the id "
                f"either never existed, belongs to a different document, or its block has "
                f"been deleted; re-read the document and re-plan against a fresh block_id "
                f"(every parsed node carries one, and apply() returns created_block_ids)"
            )
        )

    if len(matches) > 1:
        candidate_ids = [node.block_id for node in matches]
        return Refusal.ambiguous(
            candidate_ids,
            detail=(
                f"block_id {block_id!r} matched {len(candidate_ids)} blocks in the parsed "
                f"tree — a document cannot hold a duplicate id, so the tree is malformed; "
                f"the resolver never auto-picks among duplicates. Re-read the document"
            ),
        )

    node = matches[0]
    # See :func:`_resolve_narrative` — the same one-caller opt-out (LD-507).
    if _is_write_hostile(node) and not skip_write_hostile:
        return Refusal.write_hostile(
            detail=(
                f"block_id {block_id!r} resolved to a {type(node).__name__} — image / board "
                f"/ embed / synced content is not text-patchable, so it can be neither "
                f"edited nor used as an insertion reference. The id WAS found, so a "
                f"different id is the repair, not a different anchor kind; anchor to a "
                f"narrative block instead"
            )
        )

    return ResolvedTarget(block_id=node.block_id, node=node)


def _resolve_anchor(anchor, root: Node, *,
                    skip_write_hostile: bool = False) -> Union[ResolvedTarget, Refusal]:
    """Resolve a **narrative-or-by-id** anchor — the ONE seam every block-level op shares.

    An :class:`~larkdocio.write.model.AnchorById` routes to :func:`_resolve_by_id`, anything
    else to :func:`_resolve_narrative`. Every downstream op (edit / insert / delete /
    sub-span) resolves its anchor through *this* function rather than picking a resolver
    itself, so adding an anchor shape is one registration point and no op can be left behind
    (the discipline :mod:`larkdocio.write.ops` enforces for ops, applied to anchors).

    ``skip_write_hostile`` is the **one** op-specific dial, and exactly one caller sets it:
    :func:`_resolve_delete`, which owns the delete op's own narrower hostility rule
    (LD-507). It defaults to ``False``, so edit / insert / sub-span resolution through this
    seam is byte-unchanged.
    """
    if isinstance(anchor, AnchorById):
        return _resolve_by_id(anchor, root, skip_write_hostile=skip_write_hostile)
    return _resolve_narrative(anchor, root, skip_write_hostile=skip_write_hostile)


def _resolve_text_anchor(anchor, root: Node) -> Union[ResolvedTarget, Refusal]:
    """:func:`_resolve_anchor` plus the **text-replacing** ops' target-shape requirement.

    A whole-block edit and a sub-span edit both rewrite the resolved block's *own* text, so
    the target must **have** own text. A pure container — a table, a table cell, a grid, a
    callout — carries none (its text lives in its children), and patching one has nothing to
    write, so it refuses :meth:`~larkdocio.write.model.Refusal.write_hostile` with the real
    repair named (the text-bearing child's id, or a
    :class:`~larkdocio.write.model.TableLocator` for a cell).

    For a **quote** anchor this arm is unreachable by construction: a non-empty quote can only
    match a block whose own text contains it, and an empty quote is refused earlier — so the
    quote path's behavior is byte-unchanged. It exists because an *id* can address blocks a
    quote never could.
    """
    resolved = _resolve_anchor(anchor, root)
    if isinstance(resolved, Refusal):
        return resolved
    if not _has_own_text(resolved.node):
        if isinstance(resolved.node, AddOnsNode):
            # A DIAGRAM is not a container: it has no children, and its source lives in
            # `add_ons.record` rather than in any block's elements. So the generic message
            # below would be false about the block AND its advice ("target the text-bearing
            # child block's id") could not succeed — there is no such child. Name the route
            # that does work instead, with the cost it carries.
            return Refusal.write_hostile(
                detail=(
                    f"{_describe_anchor(anchor)} resolved to block {resolved.block_id}, a "
                    f"diagram add-on (docx block type 40). A diagram is CREATABLE but has NO "
                    f"IN-PLACE UPDATE: the docx block-patch surface carries no add_ons "
                    f"updater at all, so its source cannot be patched. Change it by "
                    f"DELETE + RE-CREATE at the same index — insert a NewBlock.mermaid(...) "
                    f"positioned BEFORE this block, then delete this block, both through the "
                    f"ordinary dry_run/apply gate. Note the cost: the replacement gets a NEW "
                    f"block_id, so do not cache a diagram's block_id across an edit — "
                    f"re-resolve after one"
                )
            )
        off_content = _off_content_text_home(resolved.node)
        if off_content is not None:
            # THE THIRD SUCH ARM, for the same reason as the diagram one above: this block is
            # not a container either. Its own words are real — `larkdocio.model.plain_text`
            # returns them — but they live on a single string field that no text-replacing
            # basis reads, and it has no children, so the generic message below would be false
            # about the block AND its advice ("target the text-bearing child block's id")
            # could not succeed. Say where the text really is, and that reading is the route
            # that works.
            field, _own_text = off_content
            return Refusal.write_hostile(
                detail=(
                    f"{_describe_anchor(anchor)} resolved to block {resolved.block_id}, a "
                    f"{type(resolved.node).__name__} — NOT a container: it has no children "
                    f"at all, and its own text is the {field} it carries verbatim rather than "
                    f"content text runs. So a text-replacing write has nothing it can patch "
                    f"here and no child to redirect you to: this block is not text-patchable, "
                    f"whole-block or sub-span. READING it works — plain_text(node) returns "
                    f"that {field}. The rule and which node classes it covers: "
                    f"{_TEXT_HOME_GUIDE_SECTION}"
                )
            )
        return Refusal.write_hostile(
            detail=(
                f"{_describe_anchor(anchor)} resolved to block {resolved.block_id}, a "
                f"{type(resolved.node).__name__} — a CONTAINER block that carries no text of "
                f"its own (its text lives in its child blocks), so a whole-block text "
                f"replacement has nothing to patch. Target the text-bearing child block's id "
                f"instead, or use a TableLocator (row-key + column) for a table cell"
            )
        )
    return resolved


# --------------------------------------------------------------------------- #
# The whole-block edit's own precondition: INLINE (word-level) review anchors     #
# --------------------------------------------------------------------------- #

def _inline_comment_ids(node: Node) -> Tuple[str, ...]:
    """The **word-level** review anchors on the block's own inline runs, in run order.

    The distinction this function exists to draw. The reader captures ``comment_ids`` at
    **two** granularities: on the **block** (:attr:`~larkdocio.model.Node.comment_ids` —
    what a reviewer anchored to the block as a whole) and on each styled **run**
    (:attr:`~larkdocio.model.StyledText.comment_ids` — what they anchored to a *passage*
    inside it). Only the second is what a single-run rebuild destroys, so only the second
    may drive a refusal: a whole-block edit leaves the block-level list untouched, and
    refusing on it would be a false refusal on a shipped path.

    Read off the same inline lists the write basis uses (``content``, or the page node's
    ``title``), duck-typed like every other reduction here, so an inline class that grows
    the attribute is covered without a registration. Ids are returned **verbatim** — the
    API's own order, no sorting, no de-duplication — so a refusal ``detail`` can name them
    as the document reports them. An **absent** field and a **present-but-empty** list both
    yield nothing: neither is an anchor, and neither may refuse.
    """
    inlines = getattr(node, "content", None)
    if not isinstance(inlines, list):
        inlines = getattr(node, "title", None)
    if not isinstance(inlines, list):
        return ()
    out: List[str] = []
    for inline in inlines:
        ids = getattr(inline, "comment_ids", None)
        if not ids:
            continue
        out.extend(ids)
    return tuple(out)


def _resolve_whole_block_edit(anchor, root: Node) -> Union[ResolvedTarget, Refusal]:
    """:func:`_resolve_text_anchor` plus the **whole-block** path's own precondition.

    A whole-block edit collapses the target to a **single** run (§ Decision (d)), so a
    reviewer's **inline** anchor inside it has nowhere to attach afterwards. Rather than
    drop the anchors (the silent-loss defect), pick one run's and drop the rest, or union
    them all onto the collapsed run (relocating every one of them), this path **refuses**
    :meth:`~larkdocio.write.model.Refusal.comment_anchors_present` and names the **sub-span**
    edit — which splits the runs and re-emits each one's anchors — as the recovery.

    It is decided **here, at plan time**, because the information is already on the parsed
    tree: no extra read, no write attempted, and the refusal is visible in the plan a
    consumer approves rather than in the log of a batch that already ran.

    The **sub-span** path deliberately does NOT go through this function: splitting is
    exactly what lets it honor the anchors, so the same block it refuses here it edits
    there. The **table-cell** arm has its own version of this precondition
    (:func:`_resolve_whole_cell_edit`) rather than sharing this one, because its locator
    resolves a *cell* while the patch rewrites the cell's *inner* block — a different
    subject and a different recovery.
    """
    resolved = _resolve_text_anchor(anchor, root)
    if isinstance(resolved, Refusal):
        return resolved
    anchors = _inline_comment_ids(resolved.node)
    if anchors:
        return Refusal.comment_anchors_present(
            detail=(
                f"block {resolved.block_id} (resolved from {_describe_anchor(anchor)}) "
                f"carries {len(anchors)} inline comment "
                f"{'anchor' if len(anchors) == 1 else 'anchors'} "
                f"({', '.join(anchors)}): a reviewer's comment is attached to particular "
                f"words inside it. A whole-block edit rebuilds the block as ONE run, so "
                f"those per-passage anchors would have nowhere to attach — this edit is "
                f"refused rather than move a reviewer's comment onto text they never "
                f"commented on. Use a sub-span edit (SubSpanEditRequest) naming just the "
                f"text you mean to change: it splits the runs at the span boundaries, "
                f"re-emits each run's anchors, and leaves every run it does not touch "
                f"exactly as it was. To replace the whole block anyway, resolve or remove "
                f"the comments on it first"
            )
        )
    return resolved


# --------------------------------------------------------------------------- #
# The whole-CELL edit's own precondition: the same INLINE anchors, one path over   #
# (the cell's locator resolves a CELL; the patch rewrites the cell's INNER block)  #
# --------------------------------------------------------------------------- #

def _enclosing_table_id(root: Node, cell: Node) -> Optional[str]:
    """The ``block_id`` of the table holding ``cell``, or ``None`` if it is not in one.

    A resolved cell knows its row and column but not which table it came from, and the model
    carries no parent link — so the enclosing table is found by the shared document-order walk
    (:func:`_collect_blocks`, never a fork) matching on **identity**, not equality: two cells
    with the same text and no ids compare equal, and naming the wrong table in a refusal is
    exactly the lying-detail defect the house standard exists to prevent.

    Called **only** on the refusal path, so a resolving cell edit pays nothing for it.
    """
    for (node, _path) in _collect_blocks(root):
        if isinstance(node, TableNode) and any(c is cell for c in node.cells):
            return node.block_id
    return None


def _resolve_whole_cell_edit(locator, root: Node) -> Union[ResolvedTarget, Refusal]:
    """:func:`_resolve_table` plus the **whole-cell** path's own precondition.

    The third edit path with the whole-block path's problem, and for the same reason: a
    whole-cell edit patches the target cell's **inner text block** with the *same* collapsing
    builder, so a reviewer's **inline** anchor inside that block has nowhere to attach
    afterwards. It therefore gives the same answer —
    :meth:`~larkdocio.write.model.Refusal.comment_anchors_present`, the **existing** reason
    reused, because it is the same failure in kind and a caller already branching on it needs
    no new branch.

    Two things differ from the whole-block version, both because a cell is not a block:

    * the **subject** is the cell's inner text block, not the resolved target — a
      :class:`~larkdocio.write.model.TableLocator` resolves the *cell*, while the write
      rewrites exactly one block inside it (:func:`_first_text_block`). Only that block's
      anchors are in danger, so only they may refuse: an anchor on the row's **key** cell
      (re-read for row identity, never patched), on another cell, or on a **later**
      paragraph inside the same cell survives the edit untouched, and refusing on one would
      be a false refusal on a shipped path;
    * the **recovery** cannot be phrased as "use a sub-span edit", full stop. A row-key +
      column locator has no way to name a span, so the ``detail`` names the sub-span edit
      **anchored by the inner block's id** — the only spelling that actually works.

    Decided **here, at plan time**: the anchors are already on the parsed tree, so the
    refusal costs no read, attempts no write, and shows up in the plan a consumer approves
    rather than in the log of a batch that already ran. As on the whole-block path, a
    **block-level** ``comment_ids`` (on the inner block or on the cell) does not trigger it —
    the rebuild replaces the block's *elements* and leaves its own comment list alone.
    """
    resolved = _resolve_table(locator, root)
    if isinstance(resolved, Refusal):
        return resolved
    inner = _first_text_block(resolved.node)
    if inner is None:
        return resolved
    anchors = _inline_comment_ids(inner)
    if not anchors:
        return resolved
    cell = resolved.cell
    column = (
        f"column {cell.column}" if cell.column_label is None
        else f"column {cell.column} ({cell.column_label!r})"
    )
    return Refusal.comment_anchors_present(
        detail=(
            f"the cell at row {cell.row} / {column} of table "
            f"{_enclosing_table_id(root, resolved.node) or 'its table'} "
            f"(row_key {cell.row_key!r}) carries {len(anchors)} inline comment "
            f"{'anchor' if len(anchors) == 1 else 'anchors'} ({', '.join(anchors)}) on the "
            f"text block a whole-cell edit rewrites (block {inner.block_id}): a reviewer's "
            f"comment is attached to particular words inside that cell. A whole-cell edit "
            f"rebuilds that block as ONE run, so those per-passage anchors would have nowhere "
            f"to attach — this edit is refused rather than move a reviewer's comment onto "
            f"text they never commented on. A row-key-and-column locator cannot name a span, "
            f"so the recovery is a sub-span edit (SubSpanEditRequest) aimed straight at the "
            f"inner block: AnchorById(block_id={inner.block_id!r}) with the span you mean to "
            f"change. That path splits the runs at the span boundaries, re-emits each run's "
            f"anchors, and leaves every run it does not touch exactly as it was. To replace "
            f"the whole cell anyway, resolve or remove the comments on it first"
        )
    )


# --------------------------------------------------------------------------- #
# Table-GROW resolution (LD-575) — a TableAnchor → the TABLE, or a typed refusal  #
# --------------------------------------------------------------------------- #

def table_grid(table: TableNode) -> Tuple[int, int]:
    """``(rows, columns)`` of a parsed table — the grid a preview shows and a cap is read against.

    Derived from what the reader actually parsed (the flat cell list and ``col_size``) rather
    than from the table's declared ``row_size`` property, because the cell list is what a grow
    appends to and a ragged read must not be reported as a rectangle it is not. ``col_size``
    falls back to 1 the same way the cell resolver's does, so one degenerate table cannot make
    two call sites disagree about its shape.
    """
    col_size = table.col_size or 1
    return _num_rows(len(table.cells), col_size), col_size


def _grid_phrase(rows: int, columns: int) -> str:
    """``"3 rows × 2 columns"`` — the human-legible grid a plan entry previews."""
    return (f"{rows} row{'' if rows == 1 else 's'} × "
            f"{columns} column{'' if columns == 1 else 's'}")


def _resolve_grow_table(request: GrowTableRequest,
                        root: Node) -> Union[ResolvedTarget, Refusal]:
    """Resolve a :class:`~larkdocio.write.model.GrowTableRequest` to the **table** it would
    append a row to, or a typed refusal.

    Four steps, each reusing a shipped one — this op composes primitives and defines none:

    1. **the spelling.** Only :data:`~larkdocio.write.model.requests.APPEND_ROW_INDEX` ships.
       Anything else refuses ``table-grow-unsupported`` naming the append spelling as the
       remedy and saying the other spellings are **unmeasured, not refuted** — the honest
       label, because no measurement in this tree covers one. Checked FIRST, so a caller who
       asked for the unshipped thing is told *that*, rather than being sent to fix an anchor
       that was fine.
    2. **which table.** An :class:`~larkdocio.write.model.AnchorById` goes through
       :func:`_resolve_by_id` (exact-equality id match, its not-found and ambiguous refusals
       verbatim); a :class:`~larkdocio.write.model.TableLocator` goes through
       :func:`_locate_table_row` — the table half of the cell resolver, shared rather than
       re-derived, so *which table did you mean* has one definition. The locator's
       column-target is not consulted: a grow addresses the table.
    3. **is it a table.** A resolved block that is not a :class:`~larkdocio.model.TableNode`
       refuses ``write-hostile-target``, naming the block and its kind — the exact mirror of
       :func:`_resolve_text_anchor` refusing a *container* for a text edit. The id **was**
       found, so a different id is the repair, not a different anchor kind.
    4. **the one ceiling this op enforces.** A grown grid past
       :data:`~larkdocio.write.model.MAX_TABLE_CELLS` refuses: that is larkdocio's own
       authoring cap, so a table this library refuses to *author* at a size is one it refuses
       to *grow* to. **No row cap is invented** — the row axis has none here, deliberately
       (see :data:`~larkdocio.write.model.MAX_TABLE_COLUMNS`'s note), so rows past the measured
       200 are neither refused nor claimed. And the column ceiling is unreachable from this op
       by construction: it never changes the column axis.
    """
    anchor = request.anchor
    if request.row_index != APPEND_ROW_INDEX:
        return Refusal.table_grow_unsupported(
            detail=(
                f"this operation appends a row at the END of a table and nothing else, so "
                f"row_index={request.row_index!r} is not something it performs — the shipped "
                f"value is {APPEND_ROW_INDEX} ({_describe_anchor(anchor)}). Re-issue the "
                f"request with row_index={APPEND_ROW_INDEX} to append. Inserting at any other "
                f"index is UNMEASURED from this library, neither refuted nor supported: that "
                f"spelling has never been called from this tree and no measurement in it "
                f"covers one, so this refusal is about what larkdocio ships and says nothing "
                f"about what Lark's API would do. Nothing was written"
            )
        )

    if isinstance(anchor, TableLocator):
        located = _locate_table_row(anchor, root)
        if isinstance(located, Refusal):
            return located
        table = located[0]
    else:
        resolved = _resolve_by_id(anchor, root)
        if isinstance(resolved, Refusal):
            return resolved
        table = resolved.node

    if not isinstance(table, TableNode):
        return Refusal.write_hostile(
            detail=(
                f"{_describe_anchor(anchor)} resolved to block {table.block_id}, a "
                f"{type(table).__name__} — a table-grow appends a row to a TABLE (docx block "
                f"type 31) and there is nothing to append to on any other kind of block. The "
                f"anchor WAS found, so the repair is a different id: anchor the table itself "
                f"(every parsed table node carries its own block_id), or a TableLocator whose "
                f"row_key names one of its rows. To change what a CELL says, that is a "
                f"different operation — an EditRequest anchored by a TableLocator"
            )
        )

    rows, columns = table_grid(table)
    if (rows + 1) * columns > MAX_TABLE_CELLS:
        return Refusal.table_grow_unsupported(
            detail=(
                f"appending a row to table {table.block_id} would take it from "
                f"{_grid_phrase(rows, columns)} to {_grid_phrase(rows + 1, columns)} = "
                f"{(rows + 1) * columns} cells, past the {MAX_TABLE_CELLS}-cell cap this "
                f"library holds every table to. That cap is larkdocio's OWN, anchored on a "
                f"measured platform envelope, and it is the same one that refuses an authored "
                f"grid of this size at construction — a table this library will not author at "
                f"a size is not one it will grow to. Continue in a second table instead; the "
                f"grid is never truncated and nothing was written"
            )
        )

    return ResolvedTarget(block_id=table.block_id, node=table)


# --------------------------------------------------------------------------- #
# Insert/delete resolution (W3 / LD-075) — reference/target → one block/refusal  #
# + the computed insertion point for an insert                                   #
# --------------------------------------------------------------------------- #

def _resolve_insert(request: InsertRequest, root: Node) -> Union[ResolvedTarget, Refusal]:
    """Resolve an :class:`~larkdocio.write.model.InsertRequest`: resolve the **reference**
    anchor exactly-one-or-refuse, then compute WHERE the new block(s) land.

    The reference resolves through the shared :func:`_resolve_anchor` — a quote+breadcrumb
    :class:`~larkdocio.write.model.Anchor` or an :class:`~larkdocio.write.model.AnchorById`,
    with identical downstream semantics (so a not-found / ambiguous / **write-hostile**
    reference refuses with the reused reason — you cannot anchor an insertion into a
    synced/image/board/embed block, by quote or by id). On a unique,
    write-friendly reference the insertion point is derived from the
    :class:`~larkdocio.write.model.InsertPosition`:

    * ``BEFORE`` — the reference's own index within its parent's child list;
    * ``AFTER`` — one past the reference's index;
    * ``APPEND_INTO`` — the reference **itself** is the parent, at its current child count
      (appended last). If the reference is a **leaf** that cannot parent children →
      :meth:`~larkdocio.write.model.Refusal.cannot_hold_children` (the LD-074 reason S2
      produces).

    **The sibling mirror (LD-131).** A ``BEFORE``/``AFTER`` whose reference resolved to a
    block with **no parent in the tree** — it IS the root / page node, which the doc *title*
    anchors to — has no sibling position to occupy. That is NOT ``not-found`` (the anchor
    *was* found; the identical anchor with ``APPEND_INTO`` resolves), so it refuses
    :meth:`~larkdocio.write.model.Refusal.cannot_hold_siblings`, naming the resolved block
    and pointing at the position that works. Reusing ``not-found`` here was the F5 bug: it
    sent consumers hunting for a better quote instead of changing the position.
    """
    resolved = _resolve_anchor(request.reference, root)
    if isinstance(resolved, Refusal):
        return resolved

    position = request.position
    if position is InsertPosition.APPEND_INTO:
        if not _can_hold_children(resolved.node):
            # The reference resolved (unique, write-friendly) but is a leaf paragraph —
            # it cannot parent children, so there is no "into" to append to.
            return Refusal.cannot_hold_children(
                detail=(
                    f"insert position=append-into resolved (from "
                    f"{_describe_anchor(request.reference)}) to block {resolved.block_id}, a "
                    f"{type(resolved.node).__name__} — a leaf block that cannot parent "
                    f"children, so there is no 'into' to append to; use position=before / "
                    f"after to place the block beside it, or anchor to a container block"
                )
            )
        insertion = ResolvedInsertion(
            position=position.value,
            parent_block_id=resolved.block_id,
            index=_child_count(resolved.node),
        )
        return ResolvedTarget(block_id=resolved.block_id, node=resolved.node, insertion=insertion)

    # BEFORE / AFTER — a sibling insertion: find the reference's parent + its index.
    located = _locate_parent_index(root, resolved.node)
    if located is None:
        # The reference resolved but has NO PARENT in the tree — it is the root / page
        # node. There is no sibling position beside it, and that is a position-capability
        # failure, NOT a resolution failure (LD-131): the anchor WAS found, so saying
        # `not-found` would send the consumer to fix the quote instead of the position.
        return Refusal.cannot_hold_siblings(
            detail=(
                f"insert position={position.value} resolved (from "
                f"{_describe_anchor(request.reference)}) to block {resolved.block_id}, a "
                f"{type(resolved.node).__name__} — the document ROOT (page) node. It has "
                f"no parent, so no sibling position exists beside it. The anchor WAS found: "
                f"use position=append-into to place the block INSIDE it (the identical "
                f"anchor resolves there), or anchor to a child block"
            )
        )
    parent, index = located
    if position is InsertPosition.AFTER:
        index += 1
    insertion = ResolvedInsertion(
        position=position.value,
        parent_block_id=parent.block_id,
        index=index,
    )
    return ResolvedTarget(block_id=resolved.block_id, node=resolved.node, insertion=insertion)


def _resolve_delete(request: DeleteRequest, root: Node) -> Union[ResolvedTarget, Refusal]:
    """Resolve a :class:`~larkdocio.write.model.DeleteRequest`: resolve the **target**
    anchor exactly-one-or-refuse via the shared :func:`_resolve_anchor` (a quote+breadcrumb
    :class:`~larkdocio.write.model.Anchor` or an
    :class:`~larkdocio.write.model.AnchorById`).

    A not-found / ambiguous target refuses with the reused reason. The success arm is a
    plain :class:`ResolvedTarget` — no insertion point, no cell; the previewer reads the
    block's current plain text off ``node`` as the would-remove text.

    Deliberately **no** own-text requirement (unlike the text-replacing ops): removing a
    whole **container** — a table, or a list item with its children — is a legitimate delete,
    and by-id is the only anchor that can address one.

    **THE HOSTILITY RULE IS THE DELETE OP'S OWN (LD-507)** — which is why this function
    resolves with ``skip_write_hostile=True`` and then asks the narrower question itself,
    instead of inheriting the shared type-level fence. The shared fence was cut from the
    write spike's finding that image / board / embed / synced content **is not
    text-patchable**; that reason is TRUE, is PRESERVED, and still governs every other op.
    It just is not a statement about DELETE, which patches no text — it removes a child
    range. So this op refuses on the narrower ground:

    * a target in :data:`DELETE_MEASURED_NODE_TYPES` — today exactly **image (27)** —
      **resolves**, because Lark's own ``children/batch_delete`` was MEASURED to remove one
      and the removal was confirmed by a read-back (2026-08-19; the capture,
      ``tests/captures/ld507-image-block-delete/captures/001-image-block-delete.json``, is in the source repository
      and not in the wheel) — **but only under an**
      :class:`~larkdocio.write.model.AnchorById`. A **quote** anchor stays
      refused, and that is the *un-anchorable* half of the preserved reason doing its job
      rather than an oversight: an image's own quotable text is its **caption**, which lives
      nowhere in the live block's ``text_run`` elements, so the delete path's apply-time
      precondition (*the quote must still be a substring of the live text*) can never hold
      for one. Planning it would ship a plan that always refuses ``stale-anchor`` at write
      time. The id is the route, and it is the id
      :func:`~larkdocio.write.media.put_image_in_document` hands back.
    * every **other** write-hostile type still refuses, on **delete too** — board / iframe /
      Base embed / Sheet embed / Base named-view / synced. They are **unmeasured, not
      refuted**: nothing here says their delete fails, only that nobody has asked.
    """
    resolved = _resolve_anchor(request.target, root, skip_write_hostile=True)
    if isinstance(resolved, Refusal) or not _is_write_hostile(resolved.node):
        return resolved

    node_type = type(resolved.node).__name__
    if not isinstance(resolved.node, DELETE_MEASURED_NODE_TYPES):
        return Refusal.target_write_hostile(
            detail=(
                f"{_describe_anchor(request.target)} resolved to block "
                f"{resolved.block_id}, a {node_type} — board / embed / synced content "
                f"carries no text of its own, so it can be neither edited nor used as an "
                f"insertion reference, and whether Lark's own child-delete route removes "
                f"one is UNMEASURED, NOT REFUTED — only image blocks were measured "
                f"(2026-08-19). Delete it in the Lark UI, or anchor to a narrative "
                f"block instead"
            )
        )

    if not isinstance(request.target, AnchorById):
        return Refusal.target_write_hostile(
            detail=(
                f"{_describe_anchor(request.target)} resolved to block "
                f"{resolved.block_id}, a "
                f"{node_type} — an image CAN be deleted (measured "
                f"2026-08-19), but only by AnchorById(block_id="
                f"{resolved.block_id!r}), not by quote: an image "
                f"carries no quotable text of its own on the live basis, so a "
                f"quote-anchored delete could only refuse stale-anchor at write time. "
                f"Re-issue this delete with AnchorById — put_image_in_document returns "
                f"exactly that id"
            )
        )

    return resolved


# --------------------------------------------------------------------------- #
# Sub-span resolution (W3 / LD-077) — block anchor + span exactly-one-or-refuse #
# --------------------------------------------------------------------------- #

def _text_run_inlines_plain_text(inlines) -> str:
    """Concatenate only the literal/styled **text runs** of an inline sequence
    (:class:`Text` / :class:`StyledText`), excluding mentions / equations / raw inlines.

    The projection of the apply engine's live basis onto an inline list: a live
    ``get_block`` payload's ``elements`` yield text only for ``text_run`` entries, and these
    two inline classes are exactly what the reader builds a ``text_run`` into. Shared by the
    sub-span offset basis (:func:`_text_run_plain_text`) and the by-id precondition basis
    (:func:`_live_basis_plain_text`) so the run filter is defined once.
    """
    parts: List[str] = []
    for x in inlines:
        if isinstance(x, (Text, StyledText)):
            c = getattr(x, "content", None)
            if isinstance(c, str):
                parts.append(c)
    return "".join(parts)


def _text_run_plain_text(node: Node) -> str:
    """The block's **``content``** text counting only literal/styled text runs — the
    **sub-span splitting basis**.

    A sub-span edit splits the live block's ``content`` runs at character offsets, so this
    must project exactly the runs the write-time split walks: the dry-run occurrence check
    and the live run-splitting have to agree offset-for-offset. A block whose ``content`` is
    a bare ``str`` (a block-level equation) carries no splittable text runs → its own string
    is returned only when it is genuinely a str, else ``""`` (never a sub-span candidate).

    **Deliberately ``content``-only** (LD-141). A block whose own text lives somewhere else
    — the page node's ``title`` — reads ``""`` here, so a sub-span edit of a document title
    refuses (the span is absent) on **both** anchor kinds, exactly as it has always done.
    Widening this arm would newly permit a sub-span write against ``page.elements``, which
    is a new capability, not a bug fix. The by-id **staleness precondition** needs a
    different question answered ("what will the live read return for this block?") and so
    has its own basis: :func:`_live_basis_plain_text`.
    """
    content = getattr(node, "content", None)
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return _text_run_inlines_plain_text(content)


def _live_basis_plain_text(node: Node) -> str:
    """The block's OWN text **as the apply engine will read it back live** — the by-id
    staleness-precondition basis (LD-141).

    The apply engine re-reads the anchored block and reduces it with
    ``_elements_plain_text(_live_elements(block))``: it finds the block's type-named content
    container (the one value carrying an ``elements`` list) and concatenates its ``text_run``
    contents. This function is the OFFLINE mirror of that reduction, so an **unchanged**
    block always satisfies its own compare-and-swap. The arms, matching
    :func:`_own_text_source`'s but filtered to the text-run projection:

    * an inline ``content`` list (paragraph / heading / list-item / quote / code / agenda
      title) → its text runs. Mentions and equations contribute nothing — which is the
      point: they are not ``text_run`` elements live either, so an untouched paragraph
      holding a mention is not reported as drifted (LD-137's reason for this basis);
    * a ``title`` inline list (the **page** node) → its text runs. The root block's own text
      lives under its ``page`` container — ``page.elements`` — which
      ``_live_elements`` finds like any other content container, and which the reader builds
      ``PageNode.title`` from through the *same* inline path (``handle_page``:
      ``build_inline(parser, b.page)``). Omitting this arm is LD-141: the plan previewed
      ``''`` while the live read returned the document title, so **every** id-anchored write
      against the document root refused a false ``stale-anchor`` — on the one anchor an
      empty-document authoring pass has to use;
    * a bare ``str`` ``content`` (a block-level equation) → the string, carried over
      verbatim from :func:`_text_run_plain_text`. This arm is knowingly **not** a live
      mirror (an equation block's live elements are ``equation`` entries, not ``text_run``s,
      so the live read returns ``""``), but the quote path refuses such a block identically
      — it is a symmetric, pre-existing limitation, explicitly out of LD-141's scope, and
      collapsing it to ``""`` here would turn a clean refusal into an attempted write on a
      block that is not text-patchable;
    * anything else → ``""``, which is also what the live read returns for a block with no
      content container at all. An image's ``caption`` / an iframe's ``url`` are visible
      text the *quote* basis counts, but they are **absent from the live element basis** —
      that is why neither kind is text-patchable and why a quote anchor cannot address one,
      and **that reason stands unchanged**. What used to follow it — *"and both node kinds
      are write-hostile, so no by-id op can reach this function with one"* — is **FALSE
      since LD-507**, and is superseded here rather than struck: LD-507 measured Lark's own
      ``children/batch_delete`` against an image and narrowed the fence for DELETE, so a
      by-id **delete** of an image reaches this arm routinely. Its ``""`` is not a dead
      corner; it is the mechanism that makes that delete's compare-and-swap (``'' == ''``)
      trivially hold, which is exactly why the id route works where a quote-anchored one
      could only ever refuse ``stale-anchor`` at write time. The **iframe** half is
      untouched and must not be widened by accident: an iframe is UNMEASURED, NOT REFUTED
      — it still refuses every op, delete included.
    """
    content = getattr(node, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return _text_run_inlines_plain_text(content)
    title = getattr(node, "title", None)
    if isinstance(title, list):
        return _text_run_inlines_plain_text(title)
    return ""


def _span_whitespace_near_miss(span: str, text: str, block_id: str) -> str:
    """The whitespace near-miss clause for a **sub-span** span (LD-455).

    The same trap as the narrative quote's, one block narrower: the block is already
    resolved, so there is no ambiguity to report — either the span differs from this block's
    text only in whitespace, or the clause is silent.
    """
    normalized = _diagnosable_near_miss(span)
    if not normalized or normalized not in normalize_whitespace(text):
        return ""
    return (
        f" — BUT block {block_id!r} differs only in whitespace: its text runs read "
        f"{text!r}{_whitespace_repair(span, text)}. {WHITESPACE_NEAR_MISS_TAIL}"
    )


def _resolve_subspan(request: SubSpanEditRequest, root: Node) -> Union[ResolvedTarget, Refusal]:
    """Resolve a :class:`~larkdocio.write.model.SubSpanEditRequest`: resolve the **block**
    anchor exactly-one-or-refuse via the shared :func:`_resolve_text_anchor` (a
    quote+breadcrumb :class:`~larkdocio.write.model.Anchor` or an
    :class:`~larkdocio.write.model.AnchorById`), then require the **span** to occur
    **exactly once** in that block's text-run-only plain text.

    A not-found / ambiguous / **write-hostile** block refuses with the reused narrative
    reason. On a unique, write-friendly block the span is checked against
    :func:`_text_run_plain_text` (the offline mirror of the live element basis):

    * the span is **absent** → :meth:`~larkdocio.write.model.Refusal.not_found` (the span
      text isn't in the block);
    * the span occurs **>1** time → :meth:`~larkdocio.write.model.Refusal.span_not_splittable`
      (multiple candidate regions — not exactly one);
    * the span occurs **exactly once** → the resolved block :class:`ResolvedTarget` (the
      previewer/apply engine read the span + replacement off the request).

    The authoritative run-region mapping (uniform-style-or-refuse, non-text-overlap
    refusal) happens at write time against the **live** block (S4, LD-077 apply), exactly
    as stale-anchor is a write-time-only refusal — the block's live runs, not the offline
    projection, are what a surgical patch splits.
    """
    resolved = _resolve_text_anchor(request.anchor, root)
    if isinstance(resolved, Refusal):
        return resolved

    text = _text_run_plain_text(resolved.node)
    span = request.span
    first = text.find(span)
    if first < 0:
        off_content = _off_content_text_home(resolved.node)
        if off_content is not None and span in off_content[1]:
            # The span IS this block's own text — it is just not on the sub-span splitting
            # basis, which reads `content` runs only. The shared message below is true about
            # the basis and reads as false about the document ("those words are not there"
            # while they are plainly on the page), so name the class and its text home. The
            # basis itself is unchanged: the span is still absent from it, and the refusal
            # still refuses.
            field, _own_text = off_content
            return Refusal.not_found(
                detail=(
                    f"the span {span!r} is text of block {resolved.block_id} (resolved from "
                    f"{_describe_anchor(request.anchor)}) — but NOT sub-span-editable text: "
                    f"that block is a {type(resolved.node).__name__}, which keeps its own "
                    f"words on its {field} rather than in content text runs, and a sub-span "
                    f"edit reaches only the content text runs. So the span is genuinely absent "
                    f"from the basis a sub-span edit splits, and lengthening or re-quoting it "
                    f"cannot help: no span matches on this block. READING it works — "
                    f"plain_text(node) returns that {field}. The rule and which node classes "
                    f"it covers: {_TEXT_HOME_GUIDE_SECTION}"
                )
            )
        return Refusal.not_found(
            detail=(
                f"the span {span!r} does not occur in the text runs of block "
                f"{resolved.block_id} (resolved from {_describe_anchor(request.anchor)}) — a "
                f"sub-span edit's span must be verbatim text of that block"
            ) + _span_whitespace_near_miss(span, text, resolved.block_id)
        )
    if text.find(span, first + 1) != -1:
        # more than one occurrence in the block → not exactly one region.
        return Refusal.span_not_splittable(
            detail=(
                f"the span {span!r} occurs {text.count(span)} times in block "
                f"{resolved.block_id} (resolved from {_describe_anchor(request.anchor)}) — a "
                f"sub-span edit requires EXACTLY one region; lengthen the span so it is "
                f"unique within the block"
            )
        )
    return resolved


# --------------------------------------------------------------------------- #
# resolve — exactly one or a typed refusal                                      #
# --------------------------------------------------------------------------- #

def resolve(request, root: Node) -> Union[ResolvedTarget, Refusal]:
    """Resolve a write request against a parsed node tree ``root`` to exactly one
    :class:`ResolvedTarget` or a typed :class:`Refusal` — never >1, never a guess.

    Dispatches on the request kind through the **one op-descriptor registry**
    (:mod:`larkdocio.write.ops`) — the same ordered classifier :func:`~larkdocio.write.preview.dry_run`
    reads, so resolve and preview can never disagree on kind. Per op:

    * an :class:`~larkdocio.write.model.InsertRequest` → :func:`_resolve_insert` (resolve
      the reference + compute the insertion point);
    * a :class:`~larkdocio.write.model.DeleteRequest` → :func:`_resolve_delete` (resolve
      the target);
    * a :class:`~larkdocio.write.model.SubSpanEditRequest` → :func:`_resolve_subspan`
      (resolve the block, then require the span to occur exactly once);
    * an :class:`~larkdocio.write.model.EditRequest` whose anchor is a
      :class:`~larkdocio.write.model.TableLocator` → the whole-cell resolver
      (:func:`_resolve_whole_cell_edit` — the table-cell locator plus that path's
      inline-anchor precondition); otherwise the whole-block resolver
      (:func:`_resolve_whole_block_edit` — the shared narrative-or-by-id text-target path
      plus its own inline-anchor precondition).

    See the module docstring for the full contract. The registry is imported lazily to
    keep this lower module free of a load-time cycle (see :mod:`larkdocio.write.ops`).
    """
    from larkdocio.write import ops

    return ops.resolve_dispatch(request, root)
