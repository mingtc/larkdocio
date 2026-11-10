from typing import Any, TYPE_CHECKING
from larkdocio.blocks import register_block
from larkdocio.blocks.text import build_inline
from larkdocio.model import (
    AgendaItemContentNode,
    AgendaItemNode,
    AgendaItemTitleNode,
    AgendaNode,
    GridNode,
    Node,
    PageNode,
    QuoteContainerNode,
    ViewNode,
)

if TYPE_CHECKING:
    from larkdocio.read.parser import Parser


@register_block(1) # Page
def handle_page(parser: "Parser", b: Any, indent_level: int) -> Node:
    # Migrated onto the model (LD-031 — the LAST family): build the document root
    # PageNode. `title` carries the page's inline sequence (via the text inline
    # path, like a heading line); the renderer applies the `if title.strip()`
    # gate (no dangling "# " for a title-less/whitespace-only page). Page's
    # children flip to REAL CHILD NODES — recursed through the node-producing
    # spine primitive at indent_level 0 (the first step of the List[str] ->
    # child-node carriage flip that a scoped post-T2 follow-up completes; LD-032
    # removed the strangler shim but DEFERRED the remaining families' flip). The
    # renderer serializes the tree byte-identically to the prior string handler.
    title = build_inline(parser, getattr(b, "page", None))
    children = [
        parser.parse_docx_node(parser.block_map.get(child_id), 0)
        for child_id in (b.children or [])
    ]
    return PageNode(title=title, children=children)


@register_block(34) # QuoteContainer
def handle_quote_container(parser: "Parser", b: Any, indent_level: int) -> Node:
    # Migrated onto the model (LD-028): recurse each child to a typed NODE via
    # Parser._child_nodes at indent_level 0 (R-S2 carriage flip — quote_container
    # recurses at depth 0) and carry them — ONE entry per child — on a
    # QuoteContainerNode. The renderer renders each child at depth 0, then applies
    # the per-child rstrip + "> " blockquote wrapping. Byte-identical to the prior
    # string handler.
    return QuoteContainerNode(children=parser._child_nodes(b, 0))


@register_block(24) # Grid
def handle_grid(parser: "Parser", b: Any, indent_level: int) -> Node:
    # Migrated onto the model (LD-028): flatten each column (type-25
    # grid_column) to its children; a childless/missing column contributes
    # nothing (it is omitted, so no stray blank-line separator leaks). The
    # renderer joins each column's children verbatim, then joins the columns with
    # a blank line. R-S4 flip: children now recurse to typed NODES via
    # parse_docx_node at the grid's OWN indent_level (the renderer threads that
    # depth through), replacing the prior already-rendered string carriage.
    # Byte-identical.
    columns: list = []
    for col_id in (b.children or []):
        col_block = parser.block_map.get(col_id)
        if col_block and col_block.children:
            columns.append([
                parser.parse_docx_node(parser.block_map.get(child_id), indent_level)
                for child_id in col_block.children
            ])
    return GridNode(columns=columns)


@register_block(33) # View
def handle_view(parser: "Parser", b: Any, indent_level: int) -> Node:
    # Transparent wrapper (LD-040). Lark wraps embedded content — notably EVERY
    # `/file` attachment — in a type-33 view (`view_type=1`, sole child = the
    # wrapped block). Render its children by their OWN handlers with NO markup of
    # the view itself; view is an own-depth recurser (like grid / source_synced),
    # so children recurse at the view's own `indent_level`. Views are NOT
    # homogeneous — a child may be a file, a bitable, a sheet, … — so each child
    # reaches its own status (a file → the 📎 marker; a bitable → its own
    # intentionally-skipped warn+drop). Before LD-040 type 33 was unregistered, so
    # real file attachments (always view-wrapped in live docs) were silently
    # dropped with only an "Unknown block type 33" warning — the type-23 file
    # handler was unreachable. `_child_nodes` yields the empty RawBlock sentinel
    # for a missing/childless view, which the renderer emits as "".
    return ViewNode(children=parser._child_nodes(b, indent_level))


# -- agenda family (types 44 / 45 / 46 / 47) ---------------------------------
#
# The meeting-agenda block tree (LD-046, Decision d).
# These are REGISTERED (known) handlers — agenda no longer rides the S1
# unknown-type fallback (registering them removes the family from the fallback,
# so the `Unknown block type N` warn stays a meaningful signal — Decision e's
# design ruling). 44/45/47 are TRANSPARENT structural wrappers (empty `{}` SDK
# models) that carry only children; 46 carries its title text in its OWN
# `elements`, so it needs a dedicated handler even though its wrappers are
# transparent.


@register_block(44) # Agenda
def handle_agenda(parser: "Parser", b: Any, indent_level: int) -> Node:
    # Transparent wrapper (the view/grid own-depth-recurser precedent): recurse
    # children (agenda_items) to typed NODES at the agenda's own depth and carry
    # them; the renderer emits them with NO markup of the wrapper's own.
    return AgendaNode(children=parser._child_nodes(b, indent_level))


@register_block(45) # AgendaItem
def handle_agenda_item(parser: "Parser", b: Any, indent_level: int) -> Node:
    # Transparent wrapper: carries the item's title (46) + content (47) child
    # NODES at its own depth. Rendered transparently, like handle_agenda.
    return AgendaItemNode(children=parser._child_nodes(b, indent_level))


@register_block(47) # AgendaItemContent
def handle_agenda_item_content(parser: "Parser", b: Any, indent_level: int) -> Node:
    # Transparent wrapper: carries the item's body block child NODES at its own
    # depth. Rendered transparently, like handle_agenda.
    return AgendaItemContentNode(children=parser._child_nodes(b, indent_level))


@register_block(46) # AgendaItemTitle
def handle_agenda_item_title(parser: "Parser", b: Any, indent_level: int) -> Node:
    # A REAL title handler: the title text lives in the block's OWN
    # `agenda_item_title.elements` (an inline run — NOT children), so route it
    # through the text/heading inline path via build_inline. The renderer emits
    # the rendered run + a trailing newline when non-empty; an empty `elements`
    # emits nothing. `align` is dropped (visual, no MD form) — build_inline reads
    # only `elements`.
    return AgendaItemTitleNode(content=build_inline(parser, getattr(b, "agenda_item_title", None)))


