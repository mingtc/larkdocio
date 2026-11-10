import json
from typing import Any, TYPE_CHECKING
from . import register_block
from larkdocio.model import AddOnsNode, BoardNode, GridColumnNode, Node

if TYPE_CHECKING:
    from larkdocio.read.parser import Parser

# The component_type_id Lark assigns to the Mermaid add-on. Sourced from
# observed Type 40 add_ons payloads in real Lark docx exports (the add_ons
# model itself carries no enum — see lark_oapi .../docx/v1/model/add_ons.py).
MERMAID_COMPONENT_TYPE_ID = "blk_640017963d808005a21a6445"


@register_block(40)
def handle_mermaid(parser: "Parser", b: Any, indent_level: int) -> Node:
    """Parse a Mermaid / Add-Ons block (Type 40) into a model node (LD-029).

    The handler owns the ``add_ons.record`` JSON extraction (a data concern);
    the renderer serializes. Only the known Mermaid ``component_type_id`` is
    rendered as a ```` ```mermaid ```` fenced block (source parsed from the
    record JSON ``data`` key); any other add-on yields the visible
    ``[Unsupported Add-On block: {id}]`` marker (``id`` defaulted to ``unknown``
    so a missing id never prints the literal ``None``). Byte-identical to the
    prior string handler.
    """
    if not b or not hasattr(b, 'add_ons'):
        return AddOnsNode()

    add_ons = b.add_ons

    # Only process if it's the known mermaid component ID.
    component_type_id = getattr(add_ons, 'component_type_id', '')
    if component_type_id != MERMAID_COMPONENT_TYPE_ID:
        return AddOnsNode(unsupported_component_id=component_type_id or 'unknown')

    record_json = getattr(add_ons, 'record', '{}')

    try:
        record_data = json.loads(record_json)
        if not isinstance(record_data, dict):
            record_data = {}
        mermaid_source = record_data.get('data', '')
    except json.JSONDecodeError:
        mermaid_source = record_json

    return AddOnsNode(mermaid_source=mermaid_source)


@register_block(43)
def handle_board(parser: "Parser", b: Any, indent_level: int) -> Node:
    """Parse a Board Diagram block (Type 43) into a model node (LD-029).

    These contain a token referring to an external board. Emission-only, like
    the image handler: the SIDE EFFECT (queuing the token on
    ``parser.board_tokens`` for the T1 PNG-export/substitution pipeline) stays
    HERE, at construction time, NOT in the renderer. The renderer emits
    ``![Whiteboard]({token})``. Byte-identical to the prior string handler.

    NOTE: Lark converts Type 29 (Mindmap) and Type 21 (Flowchart) blocks into
    Type 43 Boards internally. These boards can be extracted into high-resolution
    images via the Download As Image API
    (``/open-apis/board/v1/whiteboards/{whiteboard_id}/download_as_image``).

    **The scope that export needs is NOT established here.** This project has long
    associated it with ``board:whiteboard:node:read``, but no capture in this repository
    shows Lark demanding it, and the download succeeds on the read app's granted set — so
    nothing distinguishes "required and held" from "not required at all".
    :mod:`larkdocio.permissions` therefore records that string as a **candidate**
    (``documented-unverified``) rather than a requirement, and deliberately keeps it out of
    any surface's asserted scope list. If the export is ever denied, read Lark's own denial
    body: it names what Lark actually wants.
    """
    if not b or not hasattr(b, 'board'):
        return BoardNode()

    token = getattr(b.board, 'token', None)
    if not token:
        return BoardNode()

    parser.board_tokens.append(token)
    return BoardNode(token=token)


@register_block(25)
def handle_grid_column(parser: "Parser", b: Any, indent_level: int) -> Node:
    """Parse a Grid Column block (Type 25) into a model node (LD-029).

    A grid_column is a layout container; its children are rendered by the parent
    Grid (Type 24) handler, which descends into columns directly. This handler is
    a transparent safety net for a grid_column reached out of context — it
    constructs a :class:`GridColumnNode` which the renderer emits as ``""``
    (nothing directly). Byte-identical to the prior empty-string handler.
    """
    return GridColumnNode()
