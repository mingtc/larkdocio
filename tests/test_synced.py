"""Synced-family migration + behavioral pins (LD-030).

The synced family — source_synced (49) and reference_synced (50) — now
CONSTRUCTs typed model nodes instead of concatenating strings. These tests:

* assert the handler return TYPES (proving the migration happened);
* pin the node payload shapes (source_synced carries an inline sequence + its
  child NODES — R-S4 flipped the carriage from already-rendered strings, and
  unlike the recurse-at-0 group it descends at its OWN depth; reference_synced
  carries the resolved source-doc / source-block ids, ``None`` modelling an
  absent payload);
* pin the renderer's byte-exact serialization of both — source_synced's
  inline-run + trailing-newline gating + child recursion, and reference_synced's
  exact placeholder text (em-dash, backticked ids, the ``'unknown'`` default).

Two behaviors the maintainer pinned as INTENTIONAL and this story keeps byte-identical:

* **source_synced (49) descends into its child blocks.** (The handler's OLD
  docstring wrongly claimed it did *not*; LD-023 QA flagged the drift. The
  docstring now matches the code, and ``test_source_synced_renders_children``
  pins the real behavior so the docstring can't silently re-diverge.) Its own
  ``elements`` are rendered through the text-run path (``_text_run_node`` per
  element), exactly as the legacy handler did — preserved byte-for-byte here.
* **reference_synced (50) is NOT fetched** — a traceable placeholder naming the
  source ids is emitted instead (cross-document resolution is impractical).

Byte-identical whole-document *output* is additionally locked by the unchanged
T1 goldens (test_golden.py: ``source_synced_children`` and
``reference_synced``) which flow these nodes through the strangler shim +
renderer.

Mutation note (AC2): ``dev/mutation-baseline-2026-07-24.md`` § per-module lists
NO survivors for ``synced.py`` (it does not appear in the per-module table — the
family had no triaged net-gap, and there was no ``test_synced.py`` at all before
this story). There is therefore no family-specific survivor to kill test-first;
the pins below both establish the family's net from scratch and strengthen it
against the mutations the rewrite is most exposed to (the ``has_text`` newline
gate, the child recursion, the placeholder literal, the ``'unknown'`` default).
"""
from harness import build_blocks, render

from larkdocio.model import (
    BulletListItemNode,
    MarkdownRenderer,
    RawBlock,
    ReferenceSyncedNode,
    SourceSyncedNode,
    Text,
    TextNode,
)
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser


def _p():
    return Parser(Config())


def _r():
    return MarkdownRenderer()


# --- source_synced (49): handler builds a SourceSyncedNode -----------------

def test_source_synced_handler_returns_node():
    from larkdocio.blocks.synced import handle_source_synced

    blocks = build_blocks(
        [
            {"block_id": "s", "parent_id": "root", "block_type": 49,
             "source_synced": {"elements": []}, "children": ["t1"]},
            {"block_id": "t1", "parent_id": "s", "block_type": 2,
             "text": {"elements": [{"text_run": {"content": "body"}}]}, "children": []},
        ]
    )
    parser = _p()
    for blk in blocks:
        parser.block_map[blk.block_id] = blk
    node = handle_source_synced(parser, parser.block_map["s"], 0)
    assert isinstance(node, SourceSyncedNode)
    # Container-ish: carries child NODES (R-S4 flip — was already-rendered strings).
    assert len(node.children) == 1 and isinstance(node.children[0], TextNode)
    assert _r().render(node) == "body\n"


def test_source_synced_handler_missing_attr_returns_empty_node():
    from larkdocio.blocks.synced import handle_source_synced

    # An object lacking the `source_synced` attr entirely trips the guard ->
    # empty node (renders ""), no child recursion. (Real SDK Blocks always carry
    # the attr — see test_source_synced_handler_none_payload_is_empty below.)
    class _Bare:
        pass

    node = handle_source_synced(_p(), _Bare(), 0)
    assert isinstance(node, SourceSyncedNode)
    assert node.content == [] and node.children == []


def test_source_synced_handler_none_payload_is_empty():
    # A real SDK Block whose `source_synced` is present-but-None (e.g. a mis-
    # routed type-2 block): elements default to [] and children to [] -> empty
    # node (renders ""). Byte-identical to the legacy handler.
    from larkdocio.blocks.synced import handle_source_synced

    b = build_blocks([{"block_id": "x", "block_type": 2}])[0]
    node = handle_source_synced(_p(), b, 0)
    assert node.content == [] and node.children == []
    assert _r().render(node) == ""


def test_source_synced_handler_recurses_children_as_nodes_own_depth():
    # The child is a bullet (type 12). R-S4 flipped the carriage to NODES: the
    # handler recurses children to a BulletListItemNode, and the leading-tab
    # indent is now applied at RENDER time from the source_synced's own depth
    # (own-depth recurser). Rendering the node at depth 2 proves the depth is
    # threaded through — byte-identical to the legacy
    # `parse_docx_block(child, indent_level)` at indent_level 2 ("\t\t- item\n").
    from larkdocio.blocks.synced import handle_source_synced

    blocks = build_blocks(
        [
            {"block_id": "s", "parent_id": "root", "block_type": 49,
             "source_synced": {"elements": []}, "children": ["b1"]},
            {"block_id": "b1", "parent_id": "s", "block_type": 12,
             "bullet": {"elements": [{"text_run": {"content": "item"}}]}, "children": []},
        ]
    )
    parser = _p()
    for blk in blocks:
        parser.block_map[blk.block_id] = blk
    node = handle_source_synced(parser, parser.block_map["s"], 2)
    assert len(node.children) == 1 and isinstance(node.children[0], BulletListItemNode)
    assert _r().render(node, depth=2) == "\t\t- item\n"


# --- source_synced renderer: inline run + newline gate + children ----------

def test_source_synced_renderer_children_only_when_no_inline_text():
    # Empty inline content -> NO leading text and NO gating newline; just the
    # children's serialization concatenated. This is the shape of the T1 golden
    # fixture. (Child NODES post-R-S4; RawBlock injects a known verbatim string.)
    node = SourceSyncedNode(content=[], children=[RawBlock("Child paragraph content\n")])
    assert _r().render(node) == "Child paragraph content\n"


def test_source_synced_renderer_inline_text_gets_trailing_newline():
    # Non-empty inline content -> the run, then the has_text gating "\n".
    node = SourceSyncedNode(content=[Text("hi")], children=[])
    assert _r().render(node) == "hi\n"


def test_source_synced_renderer_inline_then_children():
    node = SourceSyncedNode(content=[Text("hi")], children=[RawBlock("child\n")])
    assert _r().render(node) == "hi\nchild\n"


def test_source_synced_renderer_empty_is_empty_string():
    assert _r().render(SourceSyncedNode(content=[], children=[])) == ""


def test_source_synced_renderer_empty_inline_no_gating_newline():
    # A content list that renders to "" (e.g. an empty Text) must NOT emit the
    # gating newline — pins the `if text:` gate rather than `if content:`.
    node = SourceSyncedNode(content=[Text("")], children=[RawBlock("c\n")])
    assert _r().render(node) == "c\n"


def test_source_synced_renders_children_end_to_end():
    # The maintainer-pinned INTENTIONAL behavior: source_synced DESCENDS into children
    # (the old docstring wrongly said otherwise). Whole-doc render proves it.
    blocks = [
        {"block_id": "root", "parent_id": "doc", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "Doc Title"}}]}, "children": ["s"]},
        {"block_id": "s", "parent_id": "root", "block_type": 49,
         "source_synced": {"elements": []}, "children": ["t1"]},
        {"block_id": "t1", "parent_id": "s", "block_type": 2,
         "text": {"elements": [{"text_run": {"content": "nested child text"}}]}, "children": []},
    ]
    out = render(blocks, doc_id="root")
    assert "nested child text" in out


# --- reference_synced (50): handler builds a ReferenceSyncedNode -----------

def test_reference_synced_handler_returns_node_with_resolved_ids():
    from larkdocio.blocks.synced import handle_reference_synced

    b = build_blocks(
        [{"block_id": "r", "block_type": 50,
          "reference_synced": {"source_document_id": "docABC", "source_block_id": "blk123"}}]
    )[0]
    node = handle_reference_synced(_p(), b, 0)
    assert isinstance(node, ReferenceSyncedNode)
    assert node.source_doc == "docABC" and node.source_block == "blk123"


def test_reference_synced_handler_defaults_missing_ids_to_unknown():
    # Present payload but ids absent -> the handler owns the 'unknown' default
    # (a data concern), exactly like AddOnsNode / FileNode.
    from larkdocio.blocks.synced import handle_reference_synced

    b = build_blocks([{"block_id": "r", "block_type": 50, "reference_synced": {}}])[0]
    node = handle_reference_synced(_p(), b, 0)
    assert node.source_doc == "unknown" and node.source_block == "unknown"


def test_reference_synced_handler_missing_attr_returns_empty_node():
    from larkdocio.blocks.synced import handle_reference_synced

    # An object lacking the `reference_synced` attr entirely trips the guard ->
    # None ids -> renders "".
    class _Bare:
        pass

    node = handle_reference_synced(_p(), _Bare(), 0)
    assert isinstance(node, ReferenceSyncedNode)
    assert node.source_doc is None and node.source_block is None
    assert _r().render(node) == ""


def test_reference_synced_handler_none_payload_still_emits_placeholder():
    # A real SDK Block whose `reference_synced` is present-but-None (e.g. a mis-
    # routed type-2 block): the `not hasattr` guard does NOT fire (SDK Blocks
    # always carry the attr), so getattr(None, ...) -> 'unknown' and the
    # placeholder is emitted. Pins this byte-identical legacy edge.
    from larkdocio.blocks.synced import handle_reference_synced

    b = build_blocks([{"block_id": "x", "block_type": 2}])[0]
    node = handle_reference_synced(_p(), b, 0)
    assert node.source_doc == "unknown" and node.source_block == "unknown"


# --- reference_synced renderer: exact placeholder, absent -> "" ------------

def test_reference_synced_renderer_exact_placeholder():
    node = ReferenceSyncedNode(source_doc="docABC", source_block="blk123")
    assert _r().render(node) == (
        "> 🔗 **Synced content** referenced from document `docABC` "
        "(block `blk123`) — not fetched. The source document must grant "
        "this integration read access for its content to be pulled.\n"
    )


def test_reference_synced_renderer_none_doc_is_empty_string():
    # None source_doc models an absent payload -> emit nothing (never the
    # placeholder), mirroring the ImageNode / FileNode Optional sentinel.
    assert _r().render(ReferenceSyncedNode(source_doc=None, source_block=None)) == ""


def test_reference_synced_end_to_end_matches_golden_shape():
    blocks = [
        {"block_id": "root", "parent_id": "doc", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "Doc Title"}}]}, "children": ["r"]},
        {"block_id": "r", "parent_id": "root", "block_type": 50,
         "reference_synced": {"source_document_id": "docSourceABC",
                              "source_block_id": "blkSource123"}},
    ]
    out = render(blocks, doc_id="root")
    assert "> 🔗 **Synced content** referenced from document `docSourceABC`" in out
    assert "(block `blkSource123`) — not fetched." in out


# --- registry division unchanged (Decision Log #2) -------------------------

def test_registry_division_unchanged():
    from larkdocio.blocks import get_registry

    registry = get_registry()
    assert 49 in registry and 50 in registry
