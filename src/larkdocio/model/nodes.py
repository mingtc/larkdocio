"""Typed block/document model nodes — the field-level reference for a parsed document.

**This module's docstrings are the answer to "what is on this node".** A document read
(``parse_docx_tree``) hands back a tree of these, one node per block, and each class below
documents its own fields: which node carries text, which carries children, what each field
means and which fields the Markdown projection deliberately drops. ``larkdocio.model.walk``
visits every node in such a tree and ``larkdocio.model.plain_text`` reduces one to its words;
``isinstance`` against a class here is how you tell what a block *is* (a ``HeadingNode``
carries its true ``level``, 1-9).

Dumb typed data only. A node carries the structured content of a block or an
inline span; it has NO serialization behavior and imports nothing from the
Markdown output layer. A single Markdown serializer (the sibling module) is the
ONE component that serializes a node per its type — this keeps the model
reusable (e.g. by the writer) independent of Markdown output.

Two bases:

* ``Node``   — a BLOCK-level node; this is what every registry handler returns.
* ``Inline`` — an INLINE node; the content that lives inside a block.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Node:
    """Base for BLOCK-level model nodes. Dumb typed data — no behavior.

    ``block_id`` carries the SOURCE Feishu docx ``Block.block_id`` the node was
    parsed from. It is **consumed-into-model,
    dropped-at-render** — the same pattern the color attributes follow:
    the parser stamps every parsed BLOCK node with its source block's id (see
    ``read/parser.py::parse_docx_node``) so a future writer can recover which
    live block a node came from, but the Markdown serializer NEVER reads it — a
    block id has no Markdown form — so capturing it changes NO output (the
    byte-identical invariant; goldens stay zero-drift).

    It is declared ONCE on this base and inherited by every block node type — a
    field addition, not a re-shape of the per-block registry / one-serializer
    architecture (settled). It is:

    * **keyword-only** (``kw_only=True``): so it sits at the END of every
      subclass's ``__init__`` regardless of that subclass's own required
      positional fields (``HeadingNode.level``, ``OrderedListItemNode.order``,
      …), sidestepping the dataclass "non-default field follows a default field"
      ordering error — and so existing POSITIONAL constructions are unaffected;
    * **excluded from equality/ordering** (``compare=False``): it is provenance
      metadata, not semantic identity — two nodes that render identically stay
      equal regardless of which source block each came from, keeping node equality
      a pure function of rendered content (and keeping every existing
      equality-based test robust);
    * **defaulting to absent** (``None``): synthetic/wrapper nodes with no source
      ``Block`` legitimately leave it absent — the empty ``RawBlock("")`` sentinel
      a dangling child id resolves to (no source block) and the headless
      :class:`DocumentNode` root synthesized when the page block is absent (built
      directly by the parser spine, not via ``parse_docx_node``). Inline nodes
      (:class:`Inline` subclasses) carry no ``block_id`` at all — a block id is a
      block-level concept; inlines are sub-block content.

    ``comment_ids`` carries the SOURCE Feishu docx ``Block.comment_ids`` — the
    BLOCK-level review-anchor list. It follows exactly the same
    **consumed-into-model, dropped-at-render** contract as ``block_id`` above and
    the :class:`StyledText` colors: the parser stamps every parsed BLOCK node with
    its source block's list (see ``read/parser.py::parse_docx_node``) so a future
    writer can tell which live block a reviewer anchored to, but the Markdown
    serializer NEVER reads it — a review anchor has no Markdown form — so
    capturing it changes NO output (goldens stay zero-drift).

    It is declared here on the base, ONCE, rather than per-subclass, because it is
    a field on the SDK ``Block`` itself and therefore applies to EVERY block type
    the reader registers — including the unknown-type fallback. It takes the same
    three flags as ``block_id`` and for the same reasons: **keyword-only** (so
    positional subclass constructions are unaffected), **excluded from
    equality/ordering** (``compare=False`` — a review anchor is provenance, not
    semantic identity, so two nodes that render identically stay equal and every
    existing equality-based test is untouched), and **defaulting to absent**.

    The absent sentinel is load-bearing and distinct from an empty list. ``None``
    means the SDK block carried no ``comment_ids`` field at all; ``[]`` means the
    API said there is nothing anchored here. Those are different facts, so the raw
    attribute is passed through unchanged — a valid ``[]`` is never falsy-coerced
    to ``None``, an absent field never becomes ``[]``, and the ids are stored in
    the API's own sequence with no sorting and no de-duplication (they are the
    API's data, not ours to normalize). Synthetic/wrapper nodes with no source
    ``Block`` — the empty ``RawBlock("")`` a dangling child id resolves to, the
    headless :class:`DocumentNode` root — legitimately leave it absent, exactly
    like ``block_id``. Inline nodes carry their own word-level list on
    :class:`StyledText` instead; see there.
    """

    block_id: Optional[str] = field(default=None, kw_only=True, compare=False)
    comment_ids: Optional[List[str]] = field(default=None, kw_only=True, compare=False)
    #: The SOURCE Feishu docx ``Block.block_type`` this node was parsed from — the third
    #: field on this base to follow the **consumed-into-model, dropped-at-render**
    #: contract, and stamped in the same place as the two above
    #: (``read/parser.py::parse_docx_node``). The Markdown serializer never reads it for
    #: the document's bytes; the block-identity PROJECTION reads it to answer whether a
    #: block is editable or conserved (:mod:`larkdocio.model.conservation`), which is a
    #: question about the block's TYPE and so cannot be answered from the node class
    #: alone — the unknown-type fallback collapses every unhandled type onto one class,
    #: and that type number is exactly what an unknown block must be conserved by.
    #:
    #: Same three flags and the same reasons as ``block_id``: keyword-only, excluded from
    #: equality (provenance, not semantic identity), and defaulting to absent. ``None``
    #: means no source block — the empty :class:`RawBlock` a dangling child id resolves
    #: to, the synthesized headless :class:`DocumentNode`, or a node a caller built by
    #: hand — and the projection makes no editability claim about such a node.
    block_type: Optional[int] = field(default=None, kw_only=True, compare=False)


class Inline:
    """Base for INLINE model nodes (the content inside a block)."""


@dataclass
class Text(Inline):
    """A literal-text span.

    Markdown metacharacters in ``content`` carry NO semantics here — the text is
    literal. Whether they are backslash-escaped on output is decided by the
    output layer's escape-literals policy (Decision Log #3), not by this node.
    """
    content: str


@dataclass
class RawInline(Inline):
    """Already-formatted inline markup that passes through output verbatim.

    Originally the strangler bridge to the string-based
    ``blocks/text.py`` inline formatter. The text family now builds styled runs,
    links, mentions and inline equations as real typed inline nodes
    (:class:`StyledText`, :class:`MentionUser`, :class:`MentionDoc`,
    :class:`InlineEquation`, :class:`UnsupportedInline`), so ``build_inline`` no
    longer produces ``RawInline``. It is deliberately kept as the
    output layer's stable verbatim-inline passthrough primitive (never escaped) —
    the inline analogue of :class:`RawBlock`'s empty sentinel — rather than
    deleting a documented public model type; it is no longer a strangler bridge.
    """
    markup: str


@dataclass
class StyledText(Inline):
    """A styled/linked text run — Feishu docx ``TextElement.text_run`` with a style.

    Dumb data: the style booleans and the (already-resolved) link URL. The
    Markdown serializer composes the wrappers per its ``use_html_tags`` policy —
    bold (``**`` / ``<strong>``), italic (``_`` / ``<em>``), strikethrough
    (``~~`` / ``<del>``), underline (always the HTML ``<u>…</u>`` wrapper —
    Markdown has no underline), inline code (`` ` ``) and a Markdown link. A
    plain run with no style maps to :class:`Text`, not this node.

    ``content`` is literal text (Markdown metacharacters carry no semantics
    here; the output layer's escape-literals policy decides escaping, exactly as
    for :class:`Text`). ``link_url`` is ``None`` when the run has no link, and a
    (possibly empty) string when it does — so an explicit empty-URL link still
    wraps ``[…]()``.

    ``text_color`` / ``background_color`` carry the Feishu docx color-enum ints
    off ``text_element_style`` (fg/bg). They are **consumed-into-model,
    dropped-at-render**: the model keeps them so a future writer can
    round-trip them, but the Markdown serializer ignores them (Markdown has no
    portable color form) — capturing them changes NO output. ``None`` models the
    field being absent on the run.

    ``comment_ids`` is the WORD-level review-anchor list off the same
    ``text_element_style``, and takes the identical **consumed-into-model,
    dropped-at-render** treatment: the model carries it so a future writer knows
    which *passage* a reviewer anchored to, and the Markdown serializer ignores it
    (a review anchor has no Markdown form), so capturing it changes NO output. It
    is the word-level twin of the block-level list on :class:`Node`, and a run may
    carry one while its block carries another — the two are independent. ``None``
    models the field being absent on the run; ``[]`` models the API reporting
    nothing anchored to it — a distinction a future writer needs, so the raw
    attribute is passed through with no falsy coercion, in the API's own sequence,
    with no sorting and no de-duplication.

    Which node a run maps to is decided by the presence of a ``text_element_style``
    object at all, so a run whose style holds ONLY ``comment_ids`` and no style
    flags lands here rather than on :class:`Text`, and the reader reads its
    word-level anchor off it like any other. Such a run renders exactly like a bare
    :class:`Text` (no markers, line start intact), which is why it costs no output
    bytes.
    """
    content: str
    bold: bool = False
    italic: bool = False
    strikethrough: bool = False
    underline: bool = False
    inline_code: bool = False
    link_url: Optional[str] = None
    text_color: Optional[int] = None
    background_color: Optional[int] = None
    comment_ids: Optional[List[str]] = None


@dataclass
class MentionUser(Inline):
    """A user mention — ``TextElement.mention_user``. Renders as ``@{user_id}``."""
    user_id: str


@dataclass
class MentionDoc(Inline):
    """A document mention — ``TextElement.mention_doc``.

    Renders as a Markdown link ``[{title}]({url})``. ``url`` is already
    URL-unescaped at build time (the node carries the resolved URL).
    """
    title: str
    url: str


@dataclass
class InlineEquation(Inline):
    """An inline equation — ``TextElement.equation`` in normal text flow.

    Renders as ``${content}$``. ``content`` already has any trailing newlines
    stripped at build time. (Block-level type-16 equations use
    :class:`EquationBlockNode`, fenced ``$$…$$``.)
    """
    content: str


@dataclass
class UnsupportedInline(Inline):
    """A visible marker for an inline variant the reader does not render.

    Covers the ``TextElement`` variants reminder / file / inline_block /
    link_preview / undefined. Renders as ``[unsupported inline: {variant}]`` so
    the loss is obvious in output rather than a silent drop.
    """
    variant: str


@dataclass
class RawBlock(Node):
    """A block-level verbatim-passthrough node.

    The block-level analogue of :class:`RawInline`: it carries a Markdown string
    that the output layer emits verbatim (never escaped).

    Its remaining use is the **empty sentinel**: a falsy/missing block (a dangling
    ``child_id`` that resolves to no block) or an unregistered block type maps to
    ``RawBlock("")`` — a node that renders to ``""`` — so the recursion never
    produces a ``None`` child while a missing block still contributes nothing.

    (An earlier migration step also had ``RawBlock`` carry the transitional
    string arm — :meth:`Parser.parse_docx_node` wrapped a not-yet-migrated
    handler's legacy Markdown string in a ``RawBlock`` so the node tree stayed
    uniform. That arm went away once every handler returned a node; the node
    remains as the empty sentinel + the verbatim-block primitive.)
    """
    markup: str = ""


@dataclass
class UnknownBlockNode(Node):
    """The transparent fallback for an UNREGISTERED block type.

    When the parser meets a block type with no
    registered handler it warns ONCE (naming the type + block_id, unchanged
    message shape) and — instead of dropping the block AND its entire subtree —
    carries the block's child block NODES here so the output layer emits them
    TRANSPARENTLY: each child's own serialization at the unknown block's own
    depth, concatenated verbatim, with NO markup of the unknown block itself (the
    :class:`ViewNode` / :class:`GridNode` own-depth-recurser precedent). So an
    unknown CONTAINER type surfaces its content instead of vanishing; a LEAF
    unknown (no children) carries an empty ``children`` list and renders ``""``.

    ``children`` are recursed via ``Parser._child_nodes`` at the unknown block's
    OWN ``indent_level`` (own-depth recurser, like view/grid/source_synced); a
    dangling child id resolves to the empty :class:`RawBlock` sentinel.

    Design ruling (Decision e, encoded in the AC): this is the net for
    *genuinely unknown* types ONLY. A KNOWN type keeps its registered handler, so
    the ``Unknown block type N`` warn stays a MEANINGFUL signal — a known type
    must never silently ride this fallback. (Distinct from :class:`RawBlock`'s
    empty sentinel, which is the MISSING-block — dangling child id — case.)
    """
    children: List[Node] = field(default_factory=list)


@dataclass
class PageNode(Node):
    """The document root — Feishu docx block type 1.

    The spine's root node. UNLIKE the other container-ish nodes (which still
    carry ALREADY-RENDERED child strings during the strangler period), PageNode
    flips its children to REAL CHILD NODES: the parser spine builds a node tree
    and the output layer descends it. This is the first step of the ``List[str]``
    -> child-node carriage flip (every handler
    now returns a node) but the remaining containers still carry string children —
    flipping that carriage to nodes is a scoped follow-up. Page is
    the feasible place to start it (its children sit at ``indent_level`` 0, so
    the list-item indent tab — owned by the string boundary — never applies).

    ``title`` is the page-title inline sequence (built via the text inline path,
    exactly like a heading's line). The output layer emits ``# `` + the rendered
    title ONLY when the rendered title is non-blank (``.strip()`` truthy — a
    title-less or whitespace-only page emits no dangling ``# ``); either way a
    single blank separator line follows before the children. An empty title list
    and an absent page payload therefore behave identically (no ``# ``) —
    byte-identical to the prior string handler's ``if title.strip()`` gate.

    ``children`` are the top-level child block nodes in payload order; the output
    layer serializes each and appends the page's own ``"\\n"`` child separator
    after it (byte-identical to the prior handler's per-child trailing newline).
    A missing child is carried as an empty :class:`RawBlock`, so its separator is
    still emitted.
    """
    title: List[Inline] = field(default_factory=list)
    children: List[Node] = field(default_factory=list)


@dataclass
class DocumentNode(Node):
    """A headless document root — the entry-block-missing fallback.

    When the ``doc_id`` (page) block is ABSENT from the payload, the parser spine
    reconstructs the document from the top-level children (``parent_id ==
    doc_id``) and carries them as REAL CHILD NODES on this node. The output layer
    concatenates their serializations with NO separator and no title — exactly
    the prior string fallback's ``"".join(...)``. Defensive/degenerate path
    (``doc_id`` is normally the present page block); pinned byte-identical by
    ``tests/test_parser_spine.py``.
    """
    children: List[Node] = field(default_factory=list)


@dataclass
class TextNode(Node):
    """A text paragraph — Feishu docx block type 2.

    ``content`` is the inline sequence. ``None`` models the SDK ``text``
    attribute being *absent* (the legacy handler emitted nothing); a list
    (possibly empty) models it being present (the output layer emits the inline
    run then the block's trailing newline, so present-but-empty is ``"\\n"``).
    """
    content: Optional[List[Inline]] = None


@dataclass
class CodeNode(Node):
    """A code block — Feishu docx block type 14.

    ``lang`` is the resolved Markdown language tag (``""`` for PlainText /
    unmapped). ``content`` is the inline sequence for the code body; the output
    layer fences it as ```` ```{lang}\\n…\\n``` ````.
    """
    lang: str = ""
    content: List[Inline] = field(default_factory=list)


@dataclass
class EquationBlockNode(Node):
    """A block-level equation — Feishu docx block type 16.

    ``content`` is the raw equation text pulled directly from the block's
    ``equation.elements`` (joined, trailing newlines stripped). The output layer
    fences it exactly once as ``$$\\n{content}\\n$$\\n``. Pulling the content
    directly (rather than through the inline path) avoids re-wrapping each
    element as ``$…$``.
    """
    content: str = ""


@dataclass
class DividerNode(Node):
    """A thematic break — Feishu docx block type 22."""


@dataclass
class QuoteNode(Node):
    """A blockquote — Feishu docx block type 15.

    ``content`` is the inline sequence to quote.
    """
    content: List[Inline] = field(default_factory=list)


@dataclass
class BulletListItemNode(Node):
    """A bullet list item — Feishu docx block type 12.

    ``content`` is the inline sequence for the item line. ``None`` models the SDK
    ``bullet`` payload being *absent* / lacking ``elements`` (the legacy handler
    then emitted just the ``"- "`` marker with no trailing newline); a list
    (possibly empty) models it being present (the output layer emits the inline
    run then the block's trailing newline, so present-but-empty is ``"- \\n"``).

    ``children`` holds the child block NODES (real nodes, not already-rendered
    strings — the document below the list boundary is a node tree). List nesting is a
    render-time concern: the list-item serializer owns the leading indent tab and
    renders each child NODE one level deeper (``depth + 1``) — the list family is
    the one place indent deepens — so a nested list item gains a tab while a
    block-level child (table/code) still renders at column 0.
    """
    content: Optional[List[Inline]] = None
    children: List[Node] = field(default_factory=list)


@dataclass
class OrderedListItemNode(Node):
    """An ordered list item — Feishu docx block type 13.

    ``order`` is the item's 1-based number within its parent's *consecutive run*
    of ordered siblings — computed by the handler's memoized run logic (a
    non-ordered sibling resets the run). ``content`` and ``children`` behave
    exactly as :class:`BulletListItemNode` (``children`` are child NODES).
    """
    order: int
    content: Optional[List[Inline]] = None
    children: List[Node] = field(default_factory=list)


@dataclass
class TodoListItemNode(Node):
    """A todo (checkbox) list item — Feishu docx block type 17.

    ``done`` selects the ``"- [x] "`` vs ``"- [ ] "`` marker (from the SDK
    ``todo.style.done``). ``content`` and ``children`` behave exactly as
    :class:`BulletListItemNode` (``children`` are child NODES).
    """
    done: bool = False
    content: Optional[List[Inline]] = None
    children: List[Node] = field(default_factory=list)


@dataclass
class HeadingNode(Node):
    """A heading — Feishu docx block types 3..11 (``level`` = 1..9).

    ``content`` is the inline sequence for the heading line. ``None`` models the
    SDK heading attribute being *absent* (the legacy handler then emits just the
    ``#`` prefix with no trailing newline); an empty list models the attribute
    being *present but empty*.

    ``children`` holds the child block NODES (real nodes, not already-rendered
    strings, exactly like the list family).
    Child blocks are recursed through the node primitive (``parse_docx_node`` via
    ``Parser._child_nodes``) at ``indent_level`` 0; the output layer descends each
    child at depth 0 — heading is a recurse-at-0 container, so no indent deepens.
    Byte-identical to the prior string carriage.
    """
    level: int
    content: Optional[List[Inline]] = None
    children: List[Node] = field(default_factory=list)


@dataclass
class TableNode(Node):
    """A table — Feishu docx block type 31.

    Container-ish node. ``cells`` holds the child-cell NODES
    (:class:`TableCellNode`) in row-major order (real nodes, not already-rendered
    strings, like the rest of the recurse-at-0 group). Each cell is recursed through the
    node primitive (``parse_docx_node`` via ``Parser._child_nodes``) at ``indent_level``
    0; the output layer descends each cell at depth 0 — a table recurses at depth 0, so no indent deepens.

    ``col_size`` folds the flat cell list into rows. ``header_row`` promotes the
    first row to a header (default ``True`` — Lark promotes the first row; an
    explicit ``False`` instead emits an empty header row above the delimiter,
    Markdown having no headerless-table syntax).

    ``merges`` is a list of ``(row_span, col_span)`` pairs extracted from
    ``table.property.merge_info`` (RAW SDK values — ``None`` is preserved, so the
    output layer can reproduce the two distinct None-handling rules the legacy
    handler used). When any span exceeds 1 the output layer emits an HTML
    ``<table>`` with ``rowspan``/``colspan``; otherwise a Markdown pipe table.

    The output layer is the ONE serializer and owns every table-structure
    concern — the cell pipe-escape (``|`` -> ``\\|``), the HTML-escape of cell
    content, newline flattening, row folding, ragged-row padding and header
    promotion. The node is dumb typed data only. Byte-identical to the prior
    string carriage.
    """
    cells: List[Node] = field(default_factory=list)
    col_size: int = 1
    header_row: bool = True
    merges: List[Tuple[Optional[int], Optional[int]]] = field(default_factory=list)


@dataclass
class TableCellNode(Node):
    """A table cell — Feishu docx block type 32.

    ``children`` holds the child block NODES (real nodes, not already-rendered
    strings, like :class:`TableNode` ``cells``).
    Child blocks are recursed via ``Parser._child_nodes`` at ``indent_level`` 0
    (a cell recurses at depth 0). A cell is serialized within its parent
    :class:`TableNode`; the output layer renders each child at depth 0 and
    concatenates the results verbatim, then that table serialization collapses
    the cell's newlines to spaces and escapes its content per the chosen
    (Markdown/HTML) path. Byte-identical to the prior string carriage.
    """
    children: List[Node] = field(default_factory=list)


@dataclass
class CalloutNode(Node):
    """A callout — Feishu docx block type 19.

    A callout carries no text of its own; its content lives in its children.
    ``children`` holds the child block NODES (real nodes, not already-rendered
    strings, exactly like :class:`HeadingNode` ``children``). Child blocks are recursed
    via ``Parser._child_nodes`` at ``indent_level`` 0 (callout is a recurse-at-0
    container). The output layer descends each child at depth 0, concatenates the results, then prefixes EVERY
    output line — including blank lines — with the blockquote marker ``> `` (a
    blank line becomes ``> `` WITH the trailing space, distinct from
    :class:`QuoteContainerNode`'s bare ``>``).

    The callout emits **no emoji**: the SDK ``emoji_id`` is an unmapped shortcode
    (e.g. ``"bulb"``), and there is no verified shortcode->unicode map — emitting
    the raw shortcode or ``None`` would corrupt the output.
    The node deliberately carries no emoji field, pinning that behavior.
    """
    children: List[Node] = field(default_factory=list)


@dataclass
class QuoteContainerNode(Node):
    """A quote container — Feishu docx block type 34.

    A layout container that wraps its children in a Markdown blockquote.
    ``children`` holds the child block NODES, ONE entry per child (real nodes, not
    already-rendered strings, like :class:`HeadingNode` ``children``). Child blocks are
    recursed via
    ``Parser._child_nodes`` at ``indent_level`` 0 (quote_container recurses at
    depth 0). The output layer renders each child at depth 0, then processes that
    child string independently — right-stripping its trailing newlines, then
    prefixing every remaining line with ``> `` (a blank interior line becomes a
    bare ``>`` with no trailing space). Keeping the entry list per-child is
    load-bearing: the ``rstrip`` is applied per child, so a child's trailing blank
    line is dropped rather than leaking a bare ``>`` between children.
    """
    children: List[Node] = field(default_factory=list)


@dataclass
class GridNode(Node):
    """A grid — Feishu docx block type 24.

    A layout container that flattens its columns (each a type-25 ``grid_column``)
    into their children. ``columns`` holds ONE ENTRY per column that had children
    (a childless/missing column contributes nothing — it is omitted by the
    handler, so no stray ``\\n\\n`` separator leaks); each entry is the LIST of
    that column's child block NODES, in payload order. Each entry holds real child nodes,
    not one already-rendered string per column (recursed via
    ``parse_docx_node`` at the grid's OWN ``indent_level`` — grid is an own-depth
    recurser, like :class:`SourceSyncedNode`). The output layer descends each
    column's children at the depth the grid itself is rendered at, joins each
    column's children with no separator, then joins the columns with a blank line
    (``\\n\\n``) — byte-identical to the prior string carriage.
    """
    columns: List[List[Node]] = field(default_factory=list)


@dataclass
class GridColumnNode(Node):
    """A grid column — Feishu docx block type 25.

    A transparent layout safety-net: a column's content is emitted by its parent
    :class:`GridNode` (type 24) handler, which descends into columns directly.
    This node exists only to swallow a ``grid_column`` reached OUT of that
    context (rather than warn); the output layer emits ``""`` for it. Dumb data
    with no fields — its type alone selects the empty serialization.
    """


@dataclass
class ViewNode(Node):
    """A view wrapper — Feishu docx block type 33.

    A **transparent** layout wrapper. Lark wraps embedded content — notably
    **every** ``/file`` attachment — in a type-33 view (``view_type=1``, the sole
    child being the wrapped block, e.g. a type-23 file). The wrapper carries NO
    content of its own; ``children`` holds the wrapped child block NODES, recursed
    via ``Parser._child_nodes`` at the view's OWN ``indent_level`` — view is an
    own-depth recurser like :class:`GridNode` / :class:`SourceSyncedNode`, so a
    view nested under a list threads that indent through to its children.

    The output layer emits each child's own serialization, in payload order, with
    NO markup of its own — the wrapper is invisible. Views are NOT homogeneous:
    the node makes no assumption about the child's type, so a view-wrapped file
    reaches the file 📎 marker, a view-wrapped bitable/sheet reaches THAT child's
    own 📊 embedded-data placeholder marker, and so on. In an earlier release type
    33 was unregistered, so real (always view-wrapped) file attachments were
    silently dropped with only an "Unknown block type 33" warning.
    """
    children: List[Node] = field(default_factory=list)


@dataclass
class ImageNode(Node):
    """An image — Feishu docx block type 27.

    An emission-only node: it carries the image ``token`` and ``caption``; the
    actual download + token->local-link substitution is NOT a model concern — it
    lives in the download pipeline (``read/download.py``), which reads the token off
    ``parser.img_tokens`` (queued by the handler at construction time) and
    rewrites the emitted ``![…]({token})`` link. The node deliberately carries no
    image geometry/align (intentionally dropped — no portable Markdown sizing).

    ``caption`` uses the Optional[str] sentinel exactly like :class:`TextNode`
    ``content``: ``None`` models the SDK ``image`` attribute being *absent* (the
    legacy handler emitted ``""``); a string (possibly empty) models it being
    present. ``token`` is the resolved image token, or ``None`` when the payload
    has none (the output layer then emits the visible ``[Image: missing token]``
    marker rather than dropping the block).
    """
    token: Optional[str] = None
    caption: Optional[str] = None


@dataclass
class IframeNode(Node):
    """An embedded iframe — Feishu docx block type 26.

    An iframe embeds an external component (a YouTube video, a web preview, …);
    the doc carries only its URL, in ``iframe.component.url``. That URL arrives
    **percent-encoded** (``https%3A%2F%2F…``), so the handler DECODES it (via
    ``utils.url.unescape_url`` — the link/mention precedent) before storing it
    here. The output layer emits it as a Markdown link ``[{url}]({url})``.

    ``url`` is the already-decoded URL, or ``None`` when the payload has no usable
    url (absent ``iframe``/``component``, or an empty ``url``). The output layer
    then emits a visible ``[Iframe: missing url]`` marker rather than dropping the
    block or emitting a broken empty link — the ``ImageNode`` ``[Image: missing
    token]`` no-silent-drop precedent.

    ``iframe_type`` carries the SDK ``IframeComponent.iframe_type`` (15 =
    known-provider e.g. YouTube, 99 = generic web-preview). It is
    **consumed-into-model, dropped-at-render** (like :class:`StyledText`'s color
    ints): the model keeps it so a future writer can round-trip it, but
    the Markdown serializer ignores it (a raw type int has no portable Markdown
    form) — capturing it changes NO output. ``None`` models the field being
    absent.
    """
    url: Optional[str] = None
    iframe_type: Optional[int] = None


@dataclass
class BoardNode(Node):
    """A board / whiteboard — Feishu docx block type 43.

    Emission-only, like :class:`ImageNode`: carries the board ``token`` (queued
    on ``parser.board_tokens`` by the handler at construction time for the download
    PNG-export pipeline). The output layer emits ``![Whiteboard]({token})`` when
    a token is present, else ``""``. Flowcharts (type 21) and mindmaps (type 29)
    arrive as type 43. Board align/size are intentionally dropped. ``token`` is
    ``None`` when the payload carries none (handler emits nothing).
    """
    token: Optional[str] = None


@dataclass
class AddOnsNode(Node):
    """An add-on block — Feishu docx block type 40.

    Two mutually-exclusive shapes, decided by the handler (which owns the
    ``add_ons.record`` JSON extraction — a data concern, not a serialization
    one):

    * **Mermaid** — ``mermaid_source`` holds the extracted diagram source (the
      ``data`` key of the record JSON, or the raw record when it is not a JSON
      object). The output layer fences it as ``` ```mermaid\\n{source}\\n``` ```
      (source stripped); a falsy source emits ``""``.
    * **Unsupported** — ``unsupported_component_id`` holds the (already
      ``or 'unknown'``-defaulted, never ``None``) component id for a non-Mermaid
      add-on; the output layer emits ``[Unsupported Add-On block: {id}]``.

    A bare ``AddOnsNode()`` (both fields ``None``) models an absent ``add_ons``
    payload and renders ``""``.
    """
    mermaid_source: Optional[str] = None
    unsupported_component_id: Optional[str] = None


@dataclass
class FileNode(Node):
    """A file attachment — Feishu docx block type 23.

    The binary is NOT downloaded (intentional won't-fix — full download needs the
    drive media pipeline + an extra scope). The node surfaces the file ``name``
    and, for traceability, the ``token``. The output layer emits
    ``📎 **File Attachment:** {name}`` with a `` (token: `{token}`)`` suffix when
    a token is present.

    ``name`` uses the Optional[str] sentinel: ``None`` models the SDK ``file``
    attribute being *absent* (legacy emitted ``""``); when present the handler
    supplies the falsy-aware ``'Unknown File Attachment'`` fallback, so a present
    ``name`` is always a non-empty string. ``token`` is ``None`` when the payload
    has none (the suffix is then omitted).
    """
    name: Optional[str] = None
    token: Optional[str] = None


@dataclass
class SourceSyncedNode(Node):
    """The origin side of a synced block — Feishu docx block type 49.

    ``content`` is the block's OWN inline sequence, built from
    ``source_synced.elements`` through the text-run path (one
    :func:`~larkdocio.blocks.text._text_run_node` per element, exactly as the
    legacy handler did — preserved byte-for-byte). ``children`` holds the child
    block NODES: source_synced DESCENDS into its children (an intentional,
    deliberate behavior — the handler's old docstring wrongly claimed it did not).
    These are real nodes, not already-rendered strings
    (recursed via ``Parser._child_nodes`` at the block's OWN ``indent_level`` —
    source_synced is an own-depth recurser, unlike the recurse-at-0 group). The
    output layer descends each child at the depth source_synced itself is
    rendered at (``render(child, depth)``), so a source_synced nested under a
    list still threads the list's indent through to its children — byte-identical
    to the prior already-rendered per-child string carriage.

    The output layer emits the inline run, then a single trailing newline ONLY
    when that run is non-empty (the legacy ``has_text`` gate — a present-but-
    empty ``elements`` list emits no newline), then each child's serialization.
    """
    content: List[Inline] = field(default_factory=list)
    children: List[Node] = field(default_factory=list)


@dataclass
class ReferenceSyncedNode(Node):
    """The reference side of a synced block — Feishu docx block type 50.

    The referenced content is NOT fetched (intentional won't-do: it lives in
    another document, and cross-document resolution needs a read grant the
    integration usually lacks). The node carries the source ids for a traceable
    placeholder; the output layer emits
    ``> 🔗 **Synced content** referenced from document `{source_doc}`
    (block `{source_block}`) — not fetched. …\\n``.

    ``source_doc`` / ``source_block`` use the Optional[str] sentinel like
    :class:`ImageNode` / :class:`FileNode`: ``None`` models the SDK
    ``reference_synced`` attribute being *absent* (the legacy handler emitted
    ``""``); when present the handler owns the falsy-aware ``'unknown'`` default
    (a data concern, exactly like :class:`AddOnsNode`), so a present payload
    always carries non-``None`` id strings and renders the placeholder.
    """
    source_doc: Optional[str] = None
    source_block: Optional[str] = None


# -- embedded-data family (types 18 / 30 / 53) -------------------------------
#
# Embedded Base / Sheet blocks (LD-048, Decision a).
# The block carries only an id (token, +view_id for 53) — the actual records /
# cells / views live in a SEPARATE Base or Sheet document. Deep read of those
# contents is EXPLICITLY out of scope here (a strategic descope —
# reserved for future standalone tranches); these nodes emit a TRACEABLE MARKER
# only (the reference_synced / file-attachment precedent — name the block + its
# id(s), never a silent drop). Per Decision (a) this UPGRADES 18/30 from
# intentionally-skipped and 53 from unregistered-warn to a placeholder. Each uses
# the Optional[str] token sentinel: ``token is None`` models an ABSENT payload
# (renders ""), exactly like :class:`FileNode` / :class:`ReferenceSyncedNode`;
# when the payload is present the handler owns the falsy-aware ``'unknown'``
# default (a data concern), so a present block always renders its marker.


@dataclass
class BitableNode(Node):
    """An embedded Base (bitable) — Feishu docx block type 18.

    Embedding a base yields a type-18 bitable (``{token, view_type}``; the zoo's
    live specimen carried a null ``view_type``, so only the ``token`` is marked).
    Switching that embedded base to a NAMED VIEW converts it to a
    :class:`ReferenceBaseNode` (type 53) instead — a distinct type a consumer
    hits interchangeably; the marker names that relationship. The output
    layer emits a ``> 📊 **Embedded Base** (bitable) …`` traceable marker; a
    ``None`` token models an absent payload and renders ``""``.

    ``deep_read_markdown`` carries the **opt-in embedded-Base deep-read** result,
    the :class:`SheetNode` field of the same name replayed: ``None`` on the DEFAULT path
    (deep-read off, or on but unavailable / failed) so the byte-identical placeholder is
    emitted, and the referenced table's already-assembled GFM table (with a trailing
    newline) when a consumer opted in and the read succeeded.
    """
    token: Optional[str] = None
    deep_read_markdown: Optional[str] = None


@dataclass
class SheetNode(Node):
    """An embedded Sheet — Feishu docx block type 30.

    The SDK model is ``{token, row_size, column_size}``, but the zoo's live
    specimen carried BOTH dims null, so the marker is **token-only** (there is
    nothing else to mark). The output layer emits a ``> 📊 **Embedded Sheet**
    …`` traceable marker; a ``None`` token models an absent payload and renders
    ``""``.

    ``deep_read_markdown`` carries the **opt-in deep-read** result. It is ``None`` on the
    DEFAULT path (deep-read off, or on but unavailable / failed) — the byte-identical
    placeholder is emitted then. When a
    consumer opts in (``deep_read_sheets``) and the referenced tab reads cleanly,
    the handler stores that tab's already-assembled GFM table string here (with a
    trailing newline, for block-separation parity with the placeholder), and the
    output layer emits it **in place of** the marker. Keeping the deep-read result
    on the node (a verbatim-emitted string, the :class:`RawBlock` precedent) keeps
    the one-serializer / per-block-registry architecture intact — no new node type,
    and this module stays dumb typed data with no output-layer coupling.
    """
    token: Optional[str] = None
    deep_read_markdown: Optional[str] = None


@dataclass
class ReferenceBaseNode(Node):
    """An embedded Base switched to a named view — Feishu docx block type 53
    (a newer SDK type, off the 1-52 matrix).

    The SDK model is ``{token, view_id, layout_mode}``. This is the "named-view"
    form of an embedded base — **distinct from** :class:`BitableNode` (type 18),
    which a consumer hits interchangeably (embedding a base = 18; switching it to
    a named view = 53). The marker carries the ``token`` **and** the ``view_id``
    and names the 18-vs-53 relationship. ``layout_mode`` is dropped (no
    portable Markdown form). The output layer emits a ``> 📊 **Embedded Base —
    named view** (reference_base) …`` traceable marker; a ``None`` token models
    an absent payload and renders ``""``.

    ``deep_read_markdown`` is the same opt-in deep-read slot :class:`BitableNode` carries
    — both embed types ride ONE bridge, so both nodes hold its result the same way.
    The ``view_id`` plays no part in the deep read: a view is **not** a column selector
    (``view_id`` hides nothing the API returns), so the deep read renders the **table's**
    schema, exactly as the standalone Base read does.
    """
    token: Optional[str] = None
    view_id: Optional[str] = None
    deep_read_markdown: Optional[str] = None


# -- agenda family (types 44 / 45 / 46 / 47) ---------------------------------
#
# The meeting-agenda block tree (LD-046, Decision d).
# 44 (agenda) / 45 (agenda_item) / 47 (agenda_item_content) are empty structural
# WRAPPERS that hold children; 46 (agenda_item_title) carries the title inline
# run in its OWN ``elements`` (NOT in children). These are REGISTERED (known)
# types with dedicated handlers — agenda does NOT ride the S1 unknown-type
# fallback (that would leave a misleading ``Unknown block type`` warn for a type
# the reader actually supports; Decision e's design ruling).


@dataclass
class AgendaNode(Node):
    """A meeting agenda — Feishu docx block type 44.

    A **transparent** structural wrapper (the SDK model is empty ``{}`` — it
    holds only children). ``children`` holds the agenda_item (45) child NODES,
    recursed via ``Parser._child_nodes`` at the agenda's OWN ``indent_level``
    (own-depth recurser, like :class:`ViewNode` / :class:`GridNode`). The output
    layer emits each child's own serialization, concatenated verbatim, with NO
    markup of the wrapper itself.
    """
    children: List[Node] = field(default_factory=list)


@dataclass
class AgendaItemNode(Node):
    """A single agenda item — Feishu docx block type 45.

    A **transparent** structural wrapper (empty ``{}`` SDK model). ``children``
    holds its title (46) + content (47) child NODES, recursed at the item's OWN
    ``indent_level``. Emitted transparently, exactly like :class:`AgendaNode`.
    """
    children: List[Node] = field(default_factory=list)


@dataclass
class AgendaItemContentNode(Node):
    """An agenda item's content wrapper — Feishu docx block type 47.

    A **transparent** structural wrapper (empty ``{}`` SDK model) holding the
    item's body blocks. ``children`` holds those child NODES, recursed at its OWN
    ``indent_level``. Emitted transparently, exactly like :class:`AgendaNode`.
    """
    children: List[Node] = field(default_factory=list)


@dataclass
class AgendaItemTitleNode(Node):
    """An agenda item's title — Feishu docx block type 46.

    UNLIKE the transparent wrappers (44/45/47), the title carries its text in its
    OWN ``elements`` inline run (SDK model ``{align, elements}``), NOT in children
    — so it needs a dedicated handler even though the surrounding wrappers are
    transparent. ``content`` is the inline sequence built through the text/heading
    inline path (:func:`~larkdocio.blocks.text.build_inline`).

    The output layer emits the rendered title text followed by a single trailing
    newline WHEN the rendered run is non-empty; an empty ``elements`` (or an
    absent title payload) renders ``""`` — nothing, no dangling marker (the
    page-title ``if title`` gate, applied to an item title). ``align`` is dropped
    (visual, no portable Markdown form — consistent with the other ``align``
    drops).
    """
    content: List[Inline] = field(default_factory=list)
