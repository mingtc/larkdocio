"""Typed block/document model + Markdown renderer + the two tree-reading helpers.

The reader's architecture: every registry handler constructs typed model *nodes*
(dumb data); the ``MarkdownRenderer`` serializes a node per its type. Families
migrated onto this model one story at a time behind a strangler shim in
``read/parser.py`` (a handler could return a node OR a legacy Markdown string
during the transition); that transitional string arm is gone, so a
handler now returns a Node only.

**Editing** what a read handed back starts one step earlier, with knowing which block each
piece of the Markdown came from: :func:`project_block_ids` renders the same tree with one
identity marker per block and returns the identifiers alongside the text,
:func:`strip_block_id_markers` takes them back out, and :func:`unescape_literals` decodes the
escaping the projection renders under. See ``help(larkdocio.model.projection)``.

Reading the tree a document read hands back takes two functions, and both ship from here:
:func:`walk` visits every block (following all three container shapes — ``children``,
a table's ``cells`` and a grid's ``columns``), and :func:`plain_text` says what one block —
or one inline run — says, with ``@mentions`` included. Each node class documents its own
fields; ``help(larkdocio.model.nodes)`` is the field-level reference.
"""
from .nodes import (
    AddOnsNode,
    AgendaItemContentNode,
    AgendaItemNode,
    AgendaItemTitleNode,
    AgendaNode,
    BitableNode,
    BoardNode,
    BulletListItemNode,
    CalloutNode,
    CodeNode,
    DividerNode,
    DocumentNode,
    EquationBlockNode,
    FileNode,
    GridColumnNode,
    GridNode,
    HeadingNode,
    IframeNode,
    ImageNode,
    Inline,
    InlineEquation,
    MentionDoc,
    MentionUser,
    Node,
    OrderedListItemNode,
    PageNode,
    QuoteContainerNode,
    QuoteNode,
    RawBlock,
    RawInline,
    ReferenceBaseNode,
    ReferenceSyncedNode,
    SheetNode,
    SourceSyncedNode,
    StyledText,
    TableCellNode,
    TableNode,
    Text,
    TextNode,
    TodoListItemNode,
    UnknownBlockNode,
    UnsupportedInline,
    ViewNode,
)
from .projection import (
    BlockIdProjection,
    block_id_marker,
    block_markdown,
    project_block_ids,
    replace_block_markdown,
    strip_block_id_markers,
    unescape_literals,
)
from .renderer import MarkdownRenderer
from .tree import plain_text, walk

__all__ = [
    "Node",
    "Inline",
    "Text",
    "RawInline",
    "RawBlock",
    "UnknownBlockNode",
    "PageNode",
    "DocumentNode",
    "StyledText",
    "MentionUser",
    "MentionDoc",
    "InlineEquation",
    "UnsupportedInline",
    "DividerNode",
    "QuoteNode",
    "HeadingNode",
    "BulletListItemNode",
    "OrderedListItemNode",
    "TodoListItemNode",
    "TextNode",
    "CodeNode",
    "EquationBlockNode",
    "TableNode",
    "TableCellNode",
    "CalloutNode",
    "QuoteContainerNode",
    "GridNode",
    "GridColumnNode",
    "ViewNode",
    "IframeNode",
    "ImageNode",
    "BoardNode",
    "AddOnsNode",
    "FileNode",
    "SourceSyncedNode",
    "ReferenceSyncedNode",
    "BitableNode",
    "SheetNode",
    "ReferenceBaseNode",
    "AgendaNode",
    "AgendaItemNode",
    "AgendaItemContentNode",
    "AgendaItemTitleNode",
    "MarkdownRenderer",
    "walk",
    "plain_text",
    "BlockIdProjection",
    "block_id_marker",
    "block_markdown",
    "project_block_ids",
    "replace_block_markdown",
    "strip_block_id_markers",
    "unescape_literals",
]
