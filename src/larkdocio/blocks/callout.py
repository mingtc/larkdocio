from typing import Any, TYPE_CHECKING
from . import register_block
from larkdocio.model import CalloutNode, Node

if TYPE_CHECKING:
    from larkdocio.read.parser import Parser


@register_block(19)
def handle_callout(parser: "Parser", b: Any, indent_level: int) -> Node:
    """
    Parse a Callout block (Type 19) into a model node (LD-028).

    A callout has no text of its own — its content lives in its children
    (see SDK ``Callout`` model: only color/emoji_id fields). The base parser
    does NOT auto-recurse, so we recurse the children ourselves to typed NODES
    via ``Parser._child_nodes`` at ``indent_level`` 0 (R-S2 carriage flip —
    callout recurses at depth 0) and carry them on a :class:`CalloutNode`. The
    output layer descends each child and wraps every output line in a Markdown
    blockquote marker ``> `` (blank lines included).

    ``emoji_id`` is a shortcode string (e.g. "bulb"), not a unicode char. We
    have no verified shortcode->unicode mapping, so we do not emit it (emitting
    the raw shortcode or ``None`` would corrupt the output — LD-010's
    correction). The node deliberately carries no emoji field, pinning that.
    Byte-identical to the prior string handler.
    """
    if not b or not hasattr(b, 'callout'):
        return CalloutNode(children=[])

    return CalloutNode(children=parser._child_nodes(b, 0))
