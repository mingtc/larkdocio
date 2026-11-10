from typing import Any, TYPE_CHECKING
from larkdocio.blocks import register_block
from larkdocio.model import DividerNode, Node

if TYPE_CHECKING:
    from larkdocio.read.parser import Parser

@register_block(22) # Divider
def handle_divider(parser: "Parser", b: Any, indent_level: int) -> Node:
    # Migrated onto the model (LD-024): construct a node; the renderer emits the
    # thematic break ("---\n"). Byte-identical to the prior string return.
    return DividerNode()
