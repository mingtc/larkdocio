import logging
from typing import Any, TYPE_CHECKING
from larkdocio.blocks import register_block
from larkdocio.model import ImageNode, Node

if TYPE_CHECKING:
    from larkdocio.read.parser import Parser

logger = logging.getLogger("larkdocio")


@register_block(27) # Image
def handle_image(parser: "Parser", b: Any, indent_level: int) -> Node:
    # Migrated onto the model (LD-029): construct an ImageNode; the renderer
    # emits `![{caption}]({token})` (or the missing-token marker). Emission-only
    # family — the SIDE EFFECT (queuing the token on parser.img_tokens for the
    # T1 download/substitution pipeline) stays HERE, at construction time, NOT
    # in the renderer. Byte-identical to the prior string handler.
    if not b or not b.image:
        # image payload absent -> caption sentinel None => renders "".
        return ImageNode()
    caption = getattr(getattr(b.image, "caption", None), "content", None) or ""
    token = getattr(b.image, "token", None)
    if not token:
        logger.warning("Image block %s has no token; emitting visible marker", getattr(b, "block_id", "?"))
        return ImageNode(token=None, caption=caption)
    parser.img_tokens.append(token)
    return ImageNode(token=token, caption=caption)
