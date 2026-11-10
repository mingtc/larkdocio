"""Behavioral tests for container block handlers (core/blocks/container.py).

Covers the container-quote-page-grid hardening fix:
- quote_container (34): every non-empty line of each rendered child is prefixed
  with '> ' (blank lines with '>'), reusing quote.py logic. A multi-line child
  must have ALL its lines prefixed, not just the first.
- page (1): only emit '# {title}' when the title is non-empty — no dangling
  '# ' line for a title-less page.
- grid (24): columns are separated by a blank line ('\n\n').

LD-096 consolidation: the container-family migration pins (formerly
`test_container_migration.py`, LD-028) were FOLDED IN below — the handler
return-TYPE / carried-child-node construction pins and the three renderer
mutation-kill probes the goldens cannot hold (callout blank line -> "> " WITH
trailing space; quote_container blank -> bare ">"; quote_container per-child
rstrip). The migration file's redundant renderer-serialization pins were dropped
(each held byte-exact by an LD-095/T1 golden — see the LD-096 Handoff-to-QA
removal ledger); the migration file itself was removed.
"""
from harness import build_blocks, render

from builders import text_block as _text

from larkdocio.model import (
    CalloutNode,
    GridNode,
    MarkdownRenderer,
    Node,
    QuoteContainerNode,
    RawBlock,
    TextNode,
)
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser


def _p():
    return Parser(Config())


def _r():
    return MarkdownRenderer()


def _quote_container(bid, parent, child_ids):
    return {
        "block_id": bid,
        "parent_id": parent,
        "block_type": 34,
        "quote_container": {},
        "children": list(child_ids),
    }


def _quote(bid, parent, content):
    return {
        "block_id": bid,
        "parent_id": parent,
        "block_type": 15,
        "quote": {"elements": [{"text_run": {"content": content}}]},
        "children": [],
    }


# --- quote_container: multi-line child has every line prefixed --------------

def test_quote_container_prefixes_every_line_of_multiline_child():
    # A single child that itself renders to multiple non-empty lines. EVERY
    # line of that child must be prefixed by the container's '> ', not just the
    # first. (Pre-fix, only the first line is prefixed and later lines leak out
    # un-nested.)
    blocks = [
        _quote_container("qc", "doc", ["q1"]),
        _quote("q1", "qc", "line1\nline2"),
    ]
    out = render(blocks, doc_id="qc")
    lines = [ln for ln in out.split("\n") if ln.strip()]
    assert lines, f"empty output: {out!r}"
    line1 = next(ln for ln in lines if "line1" in ln)
    line2 = next(ln for ln in lines if "line2" in ln)
    # The inner quote contributes its own '> '; the container adds another.
    assert line1.startswith("> > "), f"line1 not double-prefixed: {line1!r}"
    assert line2.startswith("> > "), (
        f"line2 not double-prefixed (container '> ' missing): {line2!r} in {out!r}"
    )


# --- page: empty title produces no dangling heading ------------------------

def _page_empty_title(bid, child_ids):
    return {
        "block_id": bid,
        "parent_id": "doc",
        "block_type": 1,
        "page": {"elements": []},
        "children": list(child_ids),
    }


def test_page_empty_title_no_dangling_heading():
    blocks = [
        _page_empty_title("root", ["t1"]),
        _text("t1", "root", "body"),
    ]
    out = render(blocks, doc_id="root")
    lines = out.split("\n")
    assert "# " not in lines, f"dangling '# ' heading emitted: {out!r}"
    assert not any(ln.strip() == "#" for ln in lines), f"dangling '#' heading: {out!r}"
    assert "body" in out


def test_page_nonempty_title_still_emits_heading():
    blocks = [
        {
            "block_id": "root",
            "parent_id": "doc",
            "block_type": 1,
            "page": {"elements": [{"text_run": {"content": "Title"}}]},
            "children": ["t1"],
        },
        _text("t1", "root", "body"),
    ]
    out = render(blocks, doc_id="root")
    assert "# Title" in out, f"heading missing: {out!r}"


# --- grid: columns separated by a blank line -------------------------------

def test_grid_separates_columns_with_blank_line():
    blocks = [
        {
            "block_id": "g", "parent_id": "doc", "block_type": 24,
            "grid": {"column_size": 2}, "children": ["c1", "c2"],
        },
        {
            "block_id": "c1", "parent_id": "g", "block_type": 25,
            "grid_column": {}, "children": ["x1"],
        },
        {
            "block_id": "c2", "parent_id": "g", "block_type": 25,
            "grid_column": {}, "children": ["x2"],
        },
        _text("x1", "c1", "colone"),
        _text("x2", "c2", "coltwo"),
    ]
    out = render(blocks, doc_id="g")
    assert "colone" in out and "coltwo" in out
    i = out.index("colone")
    j = out.index("coltwo")
    between = out[i:j]
    assert "\n\n" in between, f"columns not separated by blank line: {out!r}"


# --- regression: type 35 is `task`, NOT grid — must stay unregistered ---------

def test_task_type_35_not_registered():
    """Grid is type 24; type 35 is a Feishu Task block (verified against the
    official docx block enum). An earlier change re-registered handle_grid under
    35, re-creating a bug that had already been fixed once. Guard against re-adding it:
    an unregistered 35 correctly warns 'Unknown block type 35' rather than
    silently mis-rendering a task as an empty grid.
    """
    from larkdocio.blocks import get_registry

    registry = get_registry()
    assert 24 in registry, "grid (24) should be registered"
    assert 35 not in registry, (
        "block type 35 is `task`, not grid — it must NOT have a handler. "
        "Remove the stray @register_block(35) from handle_grid."
    )


# ===========================================================================
# Container-family migration pins folded in from test_container_migration.py
# (LD-028) by LD-096. These assert the handler return TYPES + carried child
# NODES (the strangler-migration proof, live coverage the goldens don't hold —
# goldens pin OUTPUT, not the intermediate node shape), plus the three renderer
# mutation-kill probes the goldens cannot express (they need synthetic RawBlock
# children carrying interior blank lines / trailing blanks).
# ===========================================================================


# --- callout (19): handler builds a CalloutNode ----------------------------

def test_callout_handler_returns_callout_node_with_child_strings():
    from larkdocio.blocks.callout import handle_callout

    blocks = build_blocks(
        [
            {"block_id": "c", "parent_id": "root", "block_type": 19,
             "callout": {"emoji_id": "bulb"}, "children": ["t1"]},
            {"block_id": "t1", "parent_id": "c", "block_type": 2,
             "text": {"elements": [{"text_run": {"content": "body"}}]}, "children": []},
        ]
    )
    parser = _p()
    for blk in blocks:
        parser.block_map[blk.block_id] = blk
    node = handle_callout(parser, parser.block_map["c"], 0)
    assert isinstance(node, CalloutNode)
    # R-S2 flip: children are child NODES; rendering each at depth 0 reproduces
    # the prior already-rendered string carriage byte-for-byte.
    assert all(isinstance(c, Node) for c in node.children)
    assert [_r().render(c, 0) for c in node.children] == ["body\n"]


def test_callout_handler_missing_attr_returns_empty_node():
    from larkdocio.blocks.callout import handle_callout

    # No `callout` attr present on the SDK object -> empty node (renders "").
    b2 = build_blocks([{"block_id": "x", "block_type": 2}])[0]  # a non-callout obj
    node = handle_callout(_p(), b2, 0)
    assert isinstance(node, CalloutNode) and node.children == []


# --- callout renderer mutation-kill probe: wrap EVERY line -----------------

def test_callout_renderer_wraps_every_line_including_blank_with_space():
    # A child that itself renders blank lines: callout prefixes EVERY line,
    # and a blank line becomes "> " WITH a trailing space (distinct from
    # quote_container's bare ">"). This pins the `f"> {line}\n"` format — a
    # mutation-kill probe (the golden callout_wrapping_quote holds the doc-level
    # trailing-space blank, but the synthetic RawBlock isolates the format).
    node = CalloutNode(children=[RawBlock("a\n\nb\n")])
    assert _r().render(node) == "> a\n> \n> b\n"


def test_callout_renderer_empty_children_is_empty_string():
    assert _r().render(CalloutNode(children=[])) == ""
    assert _r().render(CalloutNode(children=[RawBlock(""), RawBlock("")])) == ""


# --- quote_container (34): handler builds a QuoteContainerNode --------------

def test_quote_container_handler_returns_node_with_per_child_strings():
    from larkdocio.blocks.container import handle_quote_container

    blocks = build_blocks(
        [
            {"block_id": "qc", "parent_id": "root", "block_type": 34,
             "quote_container": {}, "children": ["a", "b"]},
            {"block_id": "a", "parent_id": "qc", "block_type": 2,
             "text": {"elements": [{"text_run": {"content": "one"}}]}, "children": []},
            {"block_id": "b", "parent_id": "qc", "block_type": 2,
             "text": {"elements": [{"text_run": {"content": "two"}}]}, "children": []},
        ]
    )
    parser = _p()
    for blk in blocks:
        parser.block_map[blk.block_id] = blk
    node = handle_quote_container(parser, parser.block_map["qc"], 0)
    assert isinstance(node, QuoteContainerNode)
    # One entry PER CHILD (the rstrip is applied per child in the renderer).
    # R-S2 flip: children are child NODES; rendering each at depth 0 reproduces
    # the prior per-child string carriage byte-for-byte.
    assert all(isinstance(c, Node) for c in node.children)
    assert [_r().render(c, 0) for c in node.children] == ["one\n", "two\n"]


def test_quote_container_handler_no_children_returns_empty_node():
    from larkdocio.blocks.container import handle_quote_container

    b = build_blocks([{"block_id": "qc", "block_type": 34, "quote_container": {}}])[0]
    node = handle_quote_container(_p(), b, 0)
    assert isinstance(node, QuoteContainerNode) and node.children == []


# --- quote_container renderer mutation-kill probes --------------------------

def test_quote_container_renderer_blank_line_is_bare_gt():
    # A blank interior line renders as a bare ">" (no trailing space) — the
    # branch that distinguishes quote_container from callout. Mutation-kill probe
    # on _blockquote_lines' blank-line arm, which is now the ONLY thing that can
    # produce that ">" (the blank_marker parameter it used to read was removed in
    # LD-631: no caller ever passed it, so the arm had exactly one reachable
    # output). Needs a synthetic RawBlock child; not doc output.
    node = QuoteContainerNode(children=[RawBlock("a\n\nb\n")])
    assert _r().render(node) == "> a\n>\n> b\n\n"


def test_quote_container_renderer_rstrip_is_per_child():
    # rstrip("\n") is applied to EACH child separately, so trailing blank lines
    # within one child are dropped and do NOT bleed a bare ">" between children.
    # (If the renderer joined first then rstripped once, child-one's trailing
    # blank would survive as an interior ">".) The precise per-child probe; the
    # observable distinction is goldened by quote_container_wrapping_quote.
    node = QuoteContainerNode(children=[RawBlock("a\n\n"), RawBlock("b\n")])
    assert _r().render(node) == "> a\n> b\n\n"


def test_quote_container_renderer_empty_is_empty_string():
    assert _r().render(QuoteContainerNode(children=[])) == ""


# --- grid (24): handler builds a GridNode ----------------------------------

def test_grid_handler_returns_node_with_column_child_nodes():
    from larkdocio.blocks.container import handle_grid

    blocks = build_blocks(
        [
            {"block_id": "g", "parent_id": "root", "block_type": 24,
             "grid": {"column_size": 2}, "children": ["c1", "c2"]},
            {"block_id": "c1", "parent_id": "g", "block_type": 25,
             "grid_column": {}, "children": ["x1"]},
            {"block_id": "c2", "parent_id": "g", "block_type": 25,
             "grid_column": {}, "children": ["x2"]},
            {"block_id": "x1", "parent_id": "c1", "block_type": 2,
             "text": {"elements": [{"text_run": {"content": "L"}}]}, "children": []},
            {"block_id": "x2", "parent_id": "c2", "block_type": 2,
             "text": {"elements": [{"text_run": {"content": "R"}}]}, "children": []},
        ]
    )
    parser = _p()
    for blk in blocks:
        parser.block_map[blk.block_id] = blk
    node = handle_grid(parser, parser.block_map["g"], 0)
    assert isinstance(node, GridNode)
    # One entry per column, each the LIST of that column's child NODES (R-S4 flip
    # — was one flattened string per column). The render assertion also carries
    # the dropped test_grid_renderer_joins_columns_with_blank_line byte pin.
    assert len(node.columns) == 2
    assert all(isinstance(child, TextNode) for col in node.columns for child in col)
    assert _r().render(node) == "L\n\n\nR\n"


def test_grid_handler_skips_childless_columns():
    from larkdocio.blocks.container import handle_grid

    blocks = build_blocks(
        [
            {"block_id": "g", "parent_id": "root", "block_type": 24,
             "grid": {"column_size": 2}, "children": ["c1", "c2"]},
            {"block_id": "c1", "parent_id": "g", "block_type": 25,
             "grid_column": {}, "children": []},  # childless -> skipped
            {"block_id": "c2", "parent_id": "g", "block_type": 25,
             "grid_column": {}, "children": ["x2"]},
            {"block_id": "x2", "parent_id": "c2", "block_type": 2,
             "text": {"elements": [{"text_run": {"content": "R"}}]}, "children": []},
        ]
    )
    parser = _p()
    for blk in blocks:
        parser.block_map[blk.block_id] = blk
    node = handle_grid(parser, parser.block_map["g"], 0)
    # The childless column is omitted -> exactly one column entry, rendering to
    # "R\n" with no stray blank-line separator (byte-identical to the prior
    # single-string carriage; also carries the dropped single-column-no-separator
    # renderer pin).
    assert len(node.columns) == 1
    assert _r().render(node) == "R\n"


# --- registry division unchanged (Decision Log #2) -------------------------

def test_registry_division_unchanged():
    from larkdocio.blocks import get_registry

    registry = get_registry()
    assert 19 in registry and 34 in registry and 24 in registry
    # type 35 is `task`, not grid — must stay unregistered (guarded elsewhere too).
    assert 35 not in registry
