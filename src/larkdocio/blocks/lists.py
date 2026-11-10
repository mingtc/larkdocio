from typing import Any, List, Optional, TYPE_CHECKING
from larkdocio.blocks import register_block
from larkdocio.blocks.text import build_inline
from larkdocio.model import (
    BulletListItemNode,
    Inline,
    Node,
    OrderedListItemNode,
    TodoListItemNode,
)

if TYPE_CHECKING:
    from larkdocio.read.parser import Parser


def _item_content(parser: "Parser", payload: Any) -> Optional[List[Inline]]:
    """Build the inline sequence for a list item's payload, or ``None``.

    An absent payload (or one with no ``elements``) yields ``None`` so the
    renderer emits just the marker with no trailing newline — byte-identical to
    the prior string handler which appended ``""`` in that case. A present payload
    yields the inline sequence (possibly empty), and the renderer re-adds the
    block newline.
    """
    if not payload or not hasattr(payload, "elements"):
        return None
    return build_inline(parser, payload)


@register_block(12) # Bullet
def handle_bullet(parser: "Parser", b: Any, indent_level: int) -> Node:
    # List children carry NODES (R-S1 flip) and deepen one level: the handler
    # builds them at indent_level + 1 and the list-item serializer renders each at
    # depth + 1 (nesting threaded through the renderer, not baked into strings).
    return BulletListItemNode(
        content=_item_content(parser, b.bullet),
        children=parser._child_nodes(b, indent_level + 1),
    )


def _ordinal_for(parser: "Parser", b: Any) -> int:
    """Return this ordered item's 1-based number within its parent's children.

    Equivalent to walking backward over siblings and counting the consecutive
    run of ordered (block_type 13) blocks ending at ``b``, but computed in a
    single O(n) forward pass over the parent's children and memoized per parent
    on ``parser`` so each parent's run is scanned at most once.

    A non-ordered sibling breaks the run (the counter resets), so the item
    immediately after an interruption restarts at 1 — matching the prior
    backward-walk behavior exactly.
    """
    parent = parser.block_map.get(b.parent_id)
    if not parent:
        return 1

    cache = getattr(parser, "_ordered_ordinals", None)
    if cache is None:
        cache = {}
        parser._ordered_ordinals = cache

    parent_key = parent.block_id
    ordinals = cache.get(parent_key)
    if ordinals is None:
        ordinals = {}
        run = 0
        for cid in (parent.children or []):
            sibling = parser.block_map.get(cid)
            # In python SDK, block_type 13 is Ordered
            if sibling and sibling.block_type == 13:
                run += 1
                ordinals[cid] = run
            else:
                run = 0
        cache[parent_key] = ordinals

    return ordinals.get(b.block_id, 1)


@register_block(13) # Ordered
def handle_ordered(parser: "Parser", b: Any, indent_level: int) -> Node:
    return OrderedListItemNode(
        order=_ordinal_for(parser, b),
        content=_item_content(parser, b.ordered),
        children=parser._child_nodes(b, indent_level + 1),
    )


@register_block(17) # Todo
def handle_todo(parser: "Parser", b: Any, indent_level: int) -> Node:
    done = b.todo.style.done if getattr(b.todo, 'style', None) else False
    return TodoListItemNode(
        done=bool(done),
        content=_item_content(parser, b.todo),
        children=parser._child_nodes(b, indent_level + 1),
    )
