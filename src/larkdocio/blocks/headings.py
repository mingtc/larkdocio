from typing import Any, TYPE_CHECKING
from larkdocio.blocks import register_block
from larkdocio.blocks.text import build_inline
from larkdocio.model import HeadingNode, Node

if TYPE_CHECKING:
    from larkdocio.read.parser import Parser


def _handle_heading(parser: "Parser", b: Any, heading_level: int) -> Node:
    """Build a :class:`HeadingNode` (LD-024).

    ``content`` is the inline sequence, or ``None`` when the SDK heading attr is
    absent (the renderer then emits just the ``#`` prefix, no trailing newline).
    Child blocks are recursed to typed NODES via ``Parser._child_nodes`` at
    ``indent_level`` 0 (R-S2 carriage flip — heading recurses at depth 0); the
    renderer descends each with ``render(child, 0)`` and re-joins them with the
    same blank-line separation the prior string handler produced.
    """
    heading_attr = f"heading{heading_level}"
    heading_text = getattr(b, heading_attr, None)
    content = build_inline(parser, heading_text) if heading_text else None

    return HeadingNode(
        level=heading_level,
        content=content,
        children=parser._child_nodes(b, 0),
    )

@register_block(3)
def handle_heading_1(parser: "Parser", b: Any, indent_level: int) -> Node:
    return _handle_heading(parser, b, 1)

@register_block(4)
def handle_heading_2(parser: "Parser", b: Any, indent_level: int) -> Node:
    return _handle_heading(parser, b, 2)

@register_block(5)
def handle_heading_3(parser: "Parser", b: Any, indent_level: int) -> Node:
    return _handle_heading(parser, b, 3)

@register_block(6)
def handle_heading_4(parser: "Parser", b: Any, indent_level: int) -> Node:
    return _handle_heading(parser, b, 4)

@register_block(7)
def handle_heading_5(parser: "Parser", b: Any, indent_level: int) -> Node:
    return _handle_heading(parser, b, 5)

@register_block(8)
def handle_heading_6(parser: "Parser", b: Any, indent_level: int) -> Node:
    return _handle_heading(parser, b, 6)

@register_block(9)
def handle_heading_7(parser: "Parser", b: Any, indent_level: int) -> Node:
    return _handle_heading(parser, b, 7)

@register_block(10)
def handle_heading_8(parser: "Parser", b: Any, indent_level: int) -> Node:
    return _handle_heading(parser, b, 8)

@register_block(11)
def handle_heading_9(parser: "Parser", b: Any, indent_level: int) -> Node:
    return _handle_heading(parser, b, 9)
