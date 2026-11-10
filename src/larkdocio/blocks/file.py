from typing import Any, TYPE_CHECKING
from . import register_block
from larkdocio.model import FileNode, Node

if TYPE_CHECKING:
    from larkdocio.read.parser import Parser


@register_block(23)
def handle_file(parser: "Parser", b: Any, indent_level: int) -> Node:
    """Parse a File block (Type 23) into a model node (LD-029).

    A File block references an attachment (name + token). By default the binary is
    NOT downloaded; we surface the name + token for traceability. Construct a
    :class:`FileNode`; the renderer emits ``📎 **File Attachment:** {name}`` with
    the `` (token: `{token}`)`` suffix when a token is present. Byte-identical to
    the prior string handler.

    LD-040: the file token is queued on ``parser.file_tokens`` at construction time
    (emission-only, mirroring image/board token queuing) so the opt-in
    ``download_attachments`` pipeline can fetch it. Queuing is NOT a download —
    when the knob is off (default) the token is queued but never fetched (zero
    attachment network); the rendered marker is unchanged either way.
    """
    if not b or not hasattr(b, 'file'):
        # file payload absent -> name sentinel None => renders "".
        return FileNode()

    file_obj = b.file
    # Falsy-aware fallback: SDK __init__ always sets name to None, so a literal
    # getattr default would never fire. A present file therefore always carries
    # a non-empty name (so name=None uniquely models the absent case above).
    name = getattr(file_obj, 'name', None) or 'Unknown File Attachment'
    token = getattr(file_obj, 'token', None)
    if token:
        # Emission-only queue for the opt-in download_attachments pipeline (T1).
        parser.file_tokens.append(token)
    return FileNode(name=name, token=token)
