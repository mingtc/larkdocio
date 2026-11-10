"""page(1) + parser-core migration tests (LD-031) — the LAST family.

page(1) now CONSTRUCTs a typed ``PageNode`` (the document root node) instead of
concatenating strings, and the parser spine builds a NODE TREE: page's children
flip from ALREADY-RENDERED strings to real CHILD NODES — the first step of the
``List[str]`` -> child-node carriage flip the shim removal completes in LD-032.
The renderer serializes the tree.

These tests assert the handler/spine return TYPES (proving the migration) and pin
the byte-exact serialization of the page-title gate + child-separator behaviors
most exposed to a regression. Byte-identical whole-document output is additionally
locked by the unchanged T1 goldens — every fixture has a page(1) root, so all of
them flow through this path.

KEEP (LD-096, mindfulness not immunity): unique page-node renderer edge pins the
goldens don't hold — blank / whitespace-only title -> no heading, no-children
separator, DocumentNode headless-fallback root concat, RawBlock empty-sentinel
verbatim, and the spine primitive return-TYPE assertions (registered -> typed
node, missing block -> empty RawBlock, unknown-type warning CONTENT via caplog).
The 2 overlaps the audit named were removed (see the inline NOTEs): the
no-string-arm pin (held by test_strangler_shim) and the missing-child pin (held
by test_parser_spine + the page_dangling_child golden). A future audit may revisit.
"""
import logging

from harness import build_blocks

from larkdocio.model import (
    DividerNode,
    DocumentNode,
    MarkdownRenderer,
    PageNode,
    RawBlock,
    Text,
    TextNode,
)
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser


def _p():
    return Parser(Config())


def _r():
    return MarkdownRenderer()


# --- page(1): handler builds a PageNode with child NODES --------------------

def test_page_handler_returns_page_node_with_child_nodes():
    from larkdocio.blocks.container import handle_page

    blocks = build_blocks([
        {"block_id": "root", "parent_id": "doc", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "Title"}}]}, "children": ["t1"]},
        {"block_id": "t1", "parent_id": "root", "block_type": 2,
         "text": {"elements": [{"text_run": {"content": "body"}}]}, "children": []},
    ])
    parser = _p()
    for blk in blocks:
        parser.block_map[blk.block_id] = blk
    node = handle_page(parser, parser.block_map["root"], 0)
    assert isinstance(node, PageNode)
    # title carried as inline model nodes (not a pre-rendered string).
    assert node.title == [Text("Title")]
    # children are REAL child NODES (the flip), not already-rendered strings.
    assert len(node.children) == 1
    assert isinstance(node.children[0], TextNode)


def test_page_handler_missing_page_attr_yields_empty_title_and_children():
    from larkdocio.blocks.container import handle_page

    b = build_blocks([{"block_id": "root", "block_type": 1, "children": []}])[0]
    node = handle_page(_p(), b, 0)
    assert isinstance(node, PageNode)
    assert node.title == []
    assert node.children == []


# NOTE (LD-096): the former ``test_page_handler_missing_child_is_empty_node_not_dropped``
# was removed here — it overlapped ``test_parser_spine.py::test_missing_child_block_renders_empty_not_marker``
# (the mutation-kill holder for the ``if not b: return ""`` dangling-child guard,
# which also pins the preserved per-child separator) and is doc-goldened by
# ``page_dangling_child`` (LD-095).


# --- page renderer: title gate + child separator ---------------------------

def test_page_renderer_title_and_children_separator():
    node = PageNode(title=[Text("Doc")], children=[TextNode(content=[Text("body")])])
    assert _r().render(node) == "# Doc\n\nbody\n\n"


def test_page_renderer_blank_title_emits_no_heading():
    node = PageNode(title=[], children=[TextNode(content=[Text("body")])])
    assert _r().render(node) == "\nbody\n\n"


def test_page_renderer_whitespace_only_title_emits_no_heading():
    # Whitespace-only title strips to empty -> no "# " (the .strip() gate).
    node = PageNode(title=[Text("   ")], children=[])
    assert _r().render(node) == "\n"


def test_page_renderer_no_children_still_emits_separator():
    node = PageNode(title=[Text("T")], children=[])
    assert _r().render(node) == "# T\n\n"


# --- DocumentNode (headless fallback root) + RawBlock (empty sentinel) ------

def test_document_node_concatenates_children_with_no_separator():
    node = DocumentNode(children=[
        TextNode(content=[Text("a")]),
        TextNode(content=[Text("b")]),
    ])
    assert _r().render(node) == "a\nb\n"


def test_document_node_empty_is_empty_string():
    assert _r().render(DocumentNode(children=[])) == ""


def test_raw_block_renders_markup_verbatim():
    assert _r().render(RawBlock("legacy string\n")) == "legacy string\n"
    assert _r().render(RawBlock("")) == ""


# --- the node-producing spine primitive ------------------------------------

def test_parse_docx_node_returns_typed_node_for_registered_block():
    parser = _p()
    b = build_blocks([{"block_id": "d", "block_type": 22, "divider": {}}])[0]
    assert isinstance(parser.parse_docx_node(b, 0), DividerNode)


def test_parse_docx_node_missing_block_is_empty_raw_block():
    parser = _p()
    node = parser.parse_docx_node(None, 0)
    assert isinstance(node, RawBlock)
    assert parser.renderer.render(node) == ""


def test_parse_docx_node_unknown_type_is_empty_and_warns(caplog):
    parser = _p()
    b = build_blocks([
        {"block_id": "u", "parent_id": "root", "block_type": 9999, "children": ["c1", "c2"]},
    ])[0]
    parser.block_map["u"] = b
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        node = parser.parse_docx_node(b, 0)
    assert parser.renderer.render(node) == ""
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    # Warning still carries block_type + parent_id + child count (test_parser_warning
    # pins this at the whole-document level; here at the primitive level too).
    joined = "\n".join(warnings)
    assert "9999" in joined and "root" in joined and "2" in joined, warnings


# NOTE (LD-096): the former ``test_parse_docx_node_returns_handler_node_directly_no_string_arm``
# was removed here — it duplicated
# ``test_strangler_shim.py::test_dual_path_removed_a_string_return_is_not_normalized``
# (the canonical regression pin for the removed LD-032 string arm: an illegal
# bare-string handler return is passed straight through and the renderer raises
# ``TypeError`` rather than normalizing it).
