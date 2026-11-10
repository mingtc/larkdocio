from typing import Any, TYPE_CHECKING
from . import register_block
from .text import build_inline
from larkdocio.model import Node, QuoteNode

if TYPE_CHECKING:
    from larkdocio.read.parser import Parser

@register_block(15)
def handle_quote(parser: "Parser", b: Any, indent_level: int) -> Node:
    """
    Parse a Quote block (Type 15) into a model node (LD-024).

    The handler constructs a :class:`QuoteNode` carrying the inline content; the
    renderer formats it as a Markdown blockquote (each line prefixed with
    ``> ``). Byte-identical to the prior string handler.
    """
    if not b or not hasattr(b, 'quote'):
        return QuoteNode(content=[])
    return QuoteNode(content=build_inline(parser, b.quote))
