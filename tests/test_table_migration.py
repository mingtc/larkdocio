"""table family migration tests (LD-027).

The table family — table (31), table_cell (32) — now CONSTRUCTS model nodes
(``TableNode`` / ``TableCellNode``) instead of concatenating Markdown strings.
The cell pipe-escape (``|`` -> ``\\|``) and ``_html_escape`` moved out of the
handler and into the output layer as serializer concerns. These tests assert
the handler return TYPES + their carried data (proving the migration happened);
byte-identical *output* is proven by the unchanged T1 goldens (test_golden.py),
which flow the nodes through the strangler shim + output layer.

KEEP (LD-096, mindfulness not immunity): the AC2 review vs ``test_table.py``
verdict is KEEP-ALL — ``test_table.py`` is purely OUTPUT-level (pipe-escape,
ragged-row padding, ``<br>`` multiline, the HTML/merge-occupancy path) and never
asserts ``TableNode``/``TableCellNode`` construction or the RAW merge-span node
attribute. The goldens likewise pin only OUTPUT. So every carried-data pin here
is unique: the ``col_size`` / ``header_row`` / cells-are-child-NODES construction
contract, the header_row ``None -> True`` and default-``col_size`` derivations,
and the load-bearing RAW ``{} -> (None, None)`` merge-span preservation that
feeds the output layer's two distinct None-rules (NOT-GOLDENABLE per LD-095).
Nothing was dropped from this file. A future audit may revisit.
"""
from harness import build_blocks

from larkdocio.model import MarkdownRenderer, Node, TableCellNode, TableNode
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser

from builders import cell as _cell, table as _table, text_block as _text


def _r():
    return MarkdownRenderer()


def _parser_with(block_dicts):
    parser = Parser(Config())
    for b in build_blocks(block_dicts):
        parser.block_map[b.block_id] = b
    return parser


# --- table (31) ------------------------------------------------------------

def test_table_handler_returns_tablenode_with_rendered_cells():
    from larkdocio.blocks.table import handle_table

    parser = _parser_with([
        _table("t", "root", 2, ["c0", "c1"]),
        _cell("c0", "t", ["c0t"]), _text("c0t", "c0", "H1"),
        _cell("c1", "t", ["c1t"]), _text("c1t", "c1", "H2"),
    ])
    node = handle_table(parser, parser.block_map["t"], 0)
    assert isinstance(node, TableNode) and isinstance(node, Node)
    assert node.col_size == 2
    assert node.header_row is True
    # Cells carry child NODES (R-S3 flip), one TableCellNode per cell; each
    # renders at depth 0 to the prior already-rendered string (with the text
    # block's trailing newline). The output layer flattens + escapes them.
    assert all(isinstance(c, Node) for c in node.cells)
    assert [_r().render(c, 0) for c in node.cells] == ["H1\n", "H2\n"]
    assert node.merges == []


def test_table_handler_empty_children_is_empty_tablenode():
    from larkdocio.blocks.table import handle_table

    parser = _parser_with([_table("t", "root", 2, [])])
    node = handle_table(parser, parser.block_map["t"], 0)
    assert isinstance(node, TableNode)
    assert node.cells == []  # renders to "" — byte-identical to the legacy early-out


def test_table_handler_defaults_col_size_when_property_absent():
    from larkdocio.blocks.table import handle_table

    parser = _parser_with([
        {"block_id": "t", "parent_id": "root", "block_type": 31,
         "table": {}, "children": ["c0"]},
        _cell("c0", "t", ["c0t"]), _text("c0t", "c0", "A"),
    ])
    node = handle_table(parser, parser.block_map["t"], 0)
    assert isinstance(node, TableNode)
    assert node.col_size == 1  # no property -> default fold width
    assert node.header_row is True  # header_row None -> True
    assert node.merges == []


def test_table_handler_preserves_header_row_false():
    from larkdocio.blocks.table import handle_table

    parser = _parser_with([
        _table("t", "root", 2, ["c0", "c1"], extra={"header_row": False}),
        _cell("c0", "t", ["c0t"]), _text("c0t", "c0", "a"),
        _cell("c1", "t", ["c1t"]), _text("c1t", "c1", "b"),
    ])
    node = handle_table(parser, parser.block_map["t"], 0)
    assert node.header_row is False


def test_table_handler_extracts_raw_merge_spans_preserving_none():
    from larkdocio.blocks.table import handle_table

    merge_info = [{"row_span": 2, "col_span": 1}, {},
                  {"row_span": 1, "col_span": 1}, {"row_span": 1, "col_span": 1}]
    parser = _parser_with([
        _table("t", "root", 2, ["c0", "c1", "c2", "c3"],
               extra={"merge_info": merge_info}),
        _cell("c0", "t", ["c0t"]), _text("c0t", "c0", "x"),
        _cell("c1", "t", []), _cell("c2", "t", []), _cell("c3", "t", []),
    ])
    node = handle_table(parser, parser.block_map["t"], 0)
    # The {} entry yields (None, None) — RAW getattr values are preserved, not
    # normalized, so the output layer can apply its two distinct None rules.
    assert node.merges == [(2, 1), (None, None), (1, 1), (1, 1)]


# --- table_cell (32) -------------------------------------------------------

def test_table_cell_handler_returns_tablecellnode_with_child_strings():
    from larkdocio.blocks.table import handle_table_cell

    parser = _parser_with([
        _cell("c", "t", ["p1", "p2"]),
        _text("p1", "c", "one"), _text("p2", "c", "two"),
    ])
    node = handle_table_cell(parser, parser.block_map["c"], 0)
    assert isinstance(node, TableCellNode) and isinstance(node, Node)
    # Child NODES (R-S3 flip); the output layer renders each at depth 0 and
    # concatenates the results verbatim.
    assert all(isinstance(c, Node) for c in node.children)
    assert [_r().render(c, 0) for c in node.children] == ["one\n", "two\n"]


def test_table_cell_handler_no_children_is_empty():
    from larkdocio.blocks.table import handle_table_cell

    parser = _parser_with([_cell("c", "t", [])])
    node = handle_table_cell(parser, parser.block_map["c"], 0)
    assert isinstance(node, TableCellNode)
    assert node.children == []
