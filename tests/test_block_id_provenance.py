"""block_id provenance on the typed node model (LD-062, W0-S3).

The writer (W1) addresses live blocks by their ``block_id``. This story threads the
source ``block_id`` onto every parsed BLOCK node as an ADDITIVE field the parser
populates and the renderer ignores — the LD-042 "capture-into-model,
drop-at-render, byte-identical" pattern (colors), now for block provenance.

AC1 — additive field on the model (default absent, existing constructions unaffected).
AC2 — the parser populates it from the source SDK ``Block``'s id on every node.
AC3 — the renderer ignores it: a node WITH a block_id renders identically to one
      WITHOUT (zero output change; the byte-identical invariant).

(AC4 goldens zero-drift and AC5 pytest-green/build/live-canary are gate runs, not
unit tests — see the issue's Handoff-to-QA notes and progress.md.)
"""
import dataclasses

import pytest

from harness import build_blocks

from larkdocio.model import (
    DividerNode,
    HeadingNode,
    Node,
    OrderedListItemNode,
    PageNode,
    RawBlock,
    Text,
    TextNode,
)
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser


# --- AC1: additive field on the model --------------------------------------


def test_node_has_block_id_field_defaulting_to_absent():
    # AC1: the model gains an additive block_id field defaulting to absent, so a
    # node constructed without one has block_id None.
    assert HeadingNode(level=1).block_id is None
    assert TextNode().block_id is None
    assert DividerNode().block_id is None
    assert RawBlock("").block_id is None


def test_block_id_is_declared_on_the_node_base():
    # AC1: it is ONE additive field inherited by every block node type (a field
    # addition, not a re-shape of the per-block registry / one-renderer contract).
    names = {f.name for f in dataclasses.fields(HeadingNode)}
    assert "block_id" in names
    # keyword-only: existing POSITIONAL constructions are unaffected (a required
    # positional field like HeadingNode.level still constructs positionally, and
    # OrderedListItemNode.order too — no "non-default follows default" breakage).
    assert HeadingNode(1).level == 1
    assert OrderedListItemNode(3).order == 3


def test_block_id_is_settable_and_carries_a_value():
    # AC1: the field accepts a source id (keyword-only).
    assert HeadingNode(1, block_id="doxNNN").block_id == "doxNNN"


# --- AC2: parser populates block_id from the real Block ---------------------


def test_parser_stamps_block_id_from_the_source_block():
    # AC2: parsing a fixture Block yields a node carrying THAT Block's block_id.
    b = build_blocks(
        [{"block_id": "blk-123", "parent_id": "root", "block_type": 2,
          "text": {"elements": [{"text_run": {"content": "hi"}}]}}]
    )[0]
    node = Parser(Config()).parse_docx_node(b, 0)
    assert isinstance(node, TextNode)
    assert node.block_id == "blk-123"


def test_parser_stamps_block_id_on_every_parsed_node_in_the_tree():
    # AC2: EVERY parsed node in the document tree carries its source block's id —
    # the page root and each descendant, recursed through parse_docx_node.
    blocks = build_blocks([
        {"block_id": "page", "parent_id": "", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "Title"}}]},
         "children": ["h", "p"]},
        {"block_id": "h", "parent_id": "page", "block_type": 3,
         "heading1": {"elements": [{"text_run": {"content": "H"}}]}},
        {"block_id": "p", "parent_id": "page", "block_type": 2,
         "text": {"elements": [{"text_run": {"content": "body"}}]}},
    ])
    parser = Parser(Config())
    for b in blocks:
        parser.block_map[b.block_id] = b
    root = parser._build_document("page", blocks)

    assert isinstance(root, PageNode)
    assert root.block_id == "page"
    got = {child.block_id for child in root.children}
    assert got == {"h", "p"}


def test_missing_block_sentinel_leaves_block_id_absent():
    # AC2 boundary / documented exception: the empty RawBlock("") sentinel a
    # dangling child id resolves to has NO source Block, so it legitimately leaves
    # block_id absent (None) — nothing to stamp.
    node = Parser(Config()).parse_docx_node(None, 0)
    assert isinstance(node, RawBlock)
    assert node.block_id is None


def test_stamp_guards_a_non_node_handler_return():
    # A handler that (illegally) returns a bare string must still pass straight
    # through un-stamped — stamping guards on isinstance(node, Node) so it never
    # AttributeErrors on a str (the removed-strangler-shim regression pin).
    parser = Parser(Config())
    parser.registry = {2: lambda p, b, i: "legacy string\n"}
    b = build_blocks([{"block_id": "x", "parent_id": "root", "block_type": 2,
                       "text": {"elements": []}}])[0]
    result = parser.parse_docx_node(b, 0)
    assert result == "legacy string\n"
    assert not isinstance(result, Node)


# --- AC3: renderer ignores block_id; byte-identical -------------------------


def test_renderer_ignores_block_id_byte_identical():
    # AC3: a node WITH a block_id renders identically to the same node WITHOUT —
    # the renderer never reads it, so capturing it changes NO output.
    parser = Parser(Config())
    render = parser.renderer.render

    without = HeadingNode(1, content=[Text("Hi")])
    with_id = HeadingNode(1, content=[Text("Hi")], block_id="doxABC")
    assert render(with_id, depth=0) == render(without, depth=0)

    # And a fuller node with children.
    without2 = OrderedListItemNode(1, content=[Text("x")])
    with_id2 = OrderedListItemNode(1, content=[Text("x")], block_id="blk-9")
    assert render(with_id2, depth=0) == render(without2, depth=0)
