"""Pilot-family migration tests (LD-024, AC3).

The three pilot families — divider (22), quote (15), headings (3..11) — now
CONSTRUCT model nodes instead of concatenating strings. These tests assert the
handler return TYPES (proving the migration happened); byte-identical *output*
is proven by the unchanged T1 goldens (test_golden.py) which flow the nodes
through the strangler shim + renderer.

KEEP (LD-096, mindfulness not immunity): unique handler return-TYPE / carried-data
pins the output-goldens don't hold — divider/quote/heading node construction, the
quote missing-attr -> empty-content degenerate, the heading level 3..11 -> 1..9
mapping across handlers, the heading absent-attr -> None content edge, and the
heading child-node collection. A future audit may revisit.
"""
from harness import build_blocks

from larkdocio.model import DividerNode, HeadingNode, MarkdownRenderer, Node, QuoteNode, Text
from larkdocio.read.parser import Parser
from larkdocio.read.config import Config


def _p():
    return Parser(Config())


# --- divider (22) ----------------------------------------------------------

def test_divider_handler_returns_divider_node():
    from larkdocio.blocks.divider import handle_divider

    b = build_blocks([{"block_id": "d", "block_type": 22, "divider": {}}])[0]
    assert isinstance(handle_divider(_p(), b, 0), DividerNode)


# --- quote (15) ------------------------------------------------------------

def test_quote_handler_returns_quote_node_with_inline_content():
    from larkdocio.blocks.quote import handle_quote

    b = build_blocks(
        [{"block_id": "q", "block_type": 15, "quote": {"elements": [{"text_run": {"content": "hi"}}]}}]
    )[0]
    node = handle_quote(_p(), b, 0)
    assert isinstance(node, QuoteNode)
    assert node.content == [Text("hi")]


def test_quote_handler_missing_quote_attr_returns_empty_node():
    from larkdocio.blocks.quote import handle_quote

    b = build_blocks([{"block_id": "q", "block_type": 15}])[0]
    node = handle_quote(_p(), b, 0)
    assert isinstance(node, QuoteNode) and node.content == []


# --- headings (3..11) ------------------------------------------------------

def test_heading_handler_returns_heading_node():
    from larkdocio.blocks.headings import handle_heading_1

    b = build_blocks(
        [{"block_id": "h", "block_type": 3, "heading1": {"elements": [{"text_run": {"content": "T"}}]}, "children": []}]
    )[0]
    node = handle_heading_1(_p(), b, 0)
    assert isinstance(node, HeadingNode)
    assert node.level == 1
    assert node.content == [Text("T")]
    assert node.children == []


def test_heading_level_mapping_3_to_11():
    import larkdocio.blocks.headings as h

    cases = [
        (h.handle_heading_1, 3, "heading1", 1),
        (h.handle_heading_2, 4, "heading2", 2),
        (h.handle_heading_9, 11, "heading9", 9),
    ]
    for fn, block_type, key, level in cases:
        b = build_blocks(
            [{"block_id": "h", "block_type": block_type, key: {"elements": [{"text_run": {"content": "x"}}]}, "children": []}]
        )[0]
        node = fn(_p(), b, 0)
        assert isinstance(node, HeadingNode) and node.level == level


def test_heading_absent_attr_maps_to_none_content():
    # A heading block missing its headingN attr -> content None (legacy emitted
    # just "# " with no trailing newline).
    from larkdocio.blocks.headings import handle_heading_1

    b = build_blocks([{"block_id": "h", "block_type": 3, "children": []}])[0]
    node = handle_heading_1(_p(), b, 0)
    assert node.content is None


def test_heading_collects_rendered_children_strings():
    from larkdocio.blocks.headings import handle_heading_1

    blocks = build_blocks(
        [
            {"block_id": "h", "parent_id": "root", "block_type": 3,
             "heading1": {"elements": [{"text_run": {"content": "Section"}}]}, "children": ["c1"]},
            {"block_id": "c1", "parent_id": "h", "block_type": 2,
             "text": {"elements": [{"text_run": {"content": "body"}}]}, "children": []},
        ]
    )
    parser = _p()
    for blk in blocks:
        parser.block_map[blk.block_id] = blk
    node = handle_heading_1(parser, parser.block_map["h"], 0)
    # R-S2 flip: children are now child NODES (not already-rendered strings);
    # rendering each at depth 0 reproduces the prior string carriage byte-for-byte.
    assert all(isinstance(c, Node) for c in node.children)
    r = MarkdownRenderer()
    assert [r.render(c, 0) for c in node.children] == ["body\n"]
