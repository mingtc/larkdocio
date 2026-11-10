import logging
from typing import Any, List, TYPE_CHECKING

from . import register_block
from .text import _text_run_node
from larkdocio.model import Inline, Node, ReferenceSyncedNode, SourceSyncedNode
from larkdocio.read.references import NEVER_BY_DESIGN, SYNCED_BLOCK, note_reference

if TYPE_CHECKING:
    from larkdocio.read.parser import Parser

logger = logging.getLogger("larkdocio")


@register_block(49)
def handle_source_synced(parser: "Parser", b: Any, indent_level: int) -> Node:
    """
    Parse a Source Synced block (Type 49) — the *origin* side of a synced block.

    Migrated onto the model (LD-030): the handler CONSTRUCTs a
    :class:`~larkdocio.model.nodes.SourceSyncedNode`; the renderer serializes it.

    It renders the block's own inline ``source_synced.elements`` (through the
    text-run path — one :func:`~larkdocio.blocks.text._text_run_node` per
    element, byte-for-byte as before) AND descends into its child blocks,
    recursing them to typed NODES via :meth:`Parser._child_nodes` at the block's
    OWN ``indent_level`` (R-S4 carriage flip — source_synced is an own-depth
    recurser; the renderer threads that depth through to the children). So a
    synced origin containing structured content (lists, tables, ...) has that
    content rendered by its own handlers.

    (An earlier docstring wrongly claimed this handler did NOT descend into
    child blocks; the code always did — LD-023 QA flagged the drift and LD-030
    corrected it. ``tests/test_synced.py`` now pins the real behavior.)
    """
    if not b or not hasattr(b, 'source_synced'):
        return SourceSyncedNode(content=[], children=[])

    source_synced = b.source_synced
    elements = getattr(source_synced, "elements", None) or []
    content: List[Inline] = [_text_run_node(parser, tr) for tr in elements]

    child_ids = b.children or []
    if child_ids and not parser.renderer.render_inline(content):
        logger.debug(
            "source_synced block %s has children but no inline elements; "
            "rendering children only.",
            getattr(b, "block_id", "?"),
        )

    # R-S4 flip: recurse children to typed NODES at the block's OWN indent_level
    # (the renderer threads that depth through), replacing the prior
    # already-rendered per-child string carriage. Byte-identical.
    children: List[Node] = parser._child_nodes(b, indent_level)

    return SourceSyncedNode(content=content, children=children)


@register_block(50)
def handle_reference_synced(parser: "Parser", b: Any, indent_level: int) -> Node:
    """
    Parse a Reference Synced block (Type 50) — the *reference* side of a synced block.

    Migrated onto the model (LD-030): the handler CONSTRUCTs a
    :class:`~larkdocio.model.nodes.ReferenceSyncedNode`; the renderer serializes
    the placeholder.

    The content is NOT present in this document's block list (``children`` is
    None). It lives in another document, identified by
    ``reference_synced.source_document_id`` and ``source_block_id``.

    Fully resolving it would require a second API call to fetch the source
    document's blocks — which requires this integration to have been granted read
    access to that source document. In Lark that means the source document's owner
    must explicitly add the app/bot to it, which is rarely done. So rather than
    failing silently (the block would otherwise drop with an "Unknown block type"
    warning), we emit a visible placeholder recording where the content lives.
    """
    if not b or not hasattr(b, 'reference_synced'):
        return ReferenceSyncedNode(source_doc=None, source_block=None)

    ref = b.reference_synced
    source_doc = getattr(ref, 'source_document_id', None) or 'unknown'
    source_block = getattr(ref, 'source_block_id', None) or 'unknown'

    # LD-334: disclose it on the parser's reference queue as well as in the Markdown. A
    # synced reference is NEVER fetched — an intentional won't-do, not a flag away — so the
    # summary must not invite the operator to "just pass a flag" for it.
    note_reference(parser, SYNCED_BLOCK, source_doc,
                   fetched=False, reason=NEVER_BY_DESIGN)

    return ReferenceSyncedNode(source_doc=source_doc, source_block=source_block)
