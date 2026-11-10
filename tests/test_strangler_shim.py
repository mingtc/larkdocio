"""Node/string-boundary contract tests (LD-024 shim; shim REMOVED in LD-032).

Through the T2 migration a registry handler could return EITHER a legacy Markdown
string OR a model node, and ``Parser.parse_docx_node`` normalized the string arm
by wrapping it in a ``RawBlock``. LD-032 removed that strangler shim: **every
handler now returns a model node**, and ``parse_docx_node`` returns the handler's
node directly (no string arm). Serializing a node to its Markdown string is
``renderer.render(node, depth)`` — the ``depth`` carries the list-item indent tab
(the ``parse_docx_block`` string-boundary delegate that used to wrap this was
retired in the R-S5 teardown, LD-038). These tests pin that post-shim contract
directly, independent of which families are exercised.

KEEP (LD-096, mindfulness not immunity): the canonical holder for the removed
LD-032 strangler shim — ``parse_docx_node`` returns the handler node directly (no
wrapping), an illegal bare-string handler return is NOT normalized (renderer
raises ``TypeError``; now also the holder for the removed
``test_page_parser_migration`` no-string-arm overlap), the list-item indent is
owned by the serializer via ``depth``, and the renderer defaults to escape-off.
A future audit may revisit.
"""
import pytest

from harness import build_blocks

from larkdocio.model import BulletListItemNode, DividerNode, Node, QuoteNode, Text
from larkdocio.read.parser import Parser
from larkdocio.read.config import Config


def _block(block_type, key="text"):
    return build_blocks(
        [{"block_id": "x", "parent_id": "root", "block_type": block_type, key: {"elements": []}}]
    )[0]


def test_node_producing_primitive_returns_the_handler_node_directly():
    # parse_docx_node returns the exact node the handler built — no wrapping.
    node = DividerNode()
    parser = Parser(Config())
    parser.registry = {22: lambda p, b, i: node}
    b = build_blocks([{"block_id": "d", "block_type": 22, "divider": {}}])[0]
    assert parser.parse_docx_node(b, 0) is node


def test_string_boundary_renders_a_returned_node_to_string():
    parser = Parser(Config())
    parser.registry = {22: lambda p, b, i: DividerNode()}
    b = build_blocks([{"block_id": "d", "block_type": 22, "divider": {}}])[0]
    assert parser.renderer.render(parser.parse_docx_node(b, 0), depth=0) == "---\n"


def test_dual_path_removed_a_string_return_is_not_normalized():
    # AC1: the string-or-node dual path is GONE. A handler that (illegally)
    # returns a bare Markdown string is no longer silently wrapped in a RawBlock;
    # parse_docx_node hands the string straight through, so the renderer surfaces
    # it as a TypeError rather than normalizing it. This is the regression pin for
    # the removed strangler shim — with the shim present the string would have
    # round-tripped unchanged instead of raising.
    parser = Parser(Config())
    parser.registry = {2: lambda p, b, i: "legacy string\n"}
    b = _block(2)
    assert not isinstance(parser.parse_docx_node(b, 0), Node)
    with pytest.raises(TypeError):
        parser.renderer.render(parser.parse_docx_node(b, 0), depth=0)


def test_list_item_serializer_owns_the_indent_tab():
    # R-S1 relocated the list indent: it is no longer prepended at a string
    # boundary (keyed on block_type), it is owned by the LIST-ITEM SERIALIZER
    # (_list_item) and applied via the depth threaded through render(node, depth),
    # keyed on the NODE KIND. A list-item node rendered at depth N carries N
    # leading hard tabs.
    parser = Parser(Config())
    parser.registry = {12: lambda p, b, i: BulletListItemNode(content=[Text("x")])}
    b = _block(12, key="bullet")
    assert parser.renderer.render(parser.parse_docx_node(b, 2), depth=2) == "\t\t- x\n"


def test_renderer_uses_escape_literals_off_by_default():
    # The parser constructs the renderer with the escape-literals policy OFF, so
    # only LD-130's structural-ambiguity layer applies: a pairable `*b*` is
    # escaped (it would otherwise emit live emphasis from literal text), while
    # the surrounding punctuation the sledgehammer WOULD have escaped — the
    # comma, the period — is left alone.
    parser = Parser(Config())
    parser.registry = {15: lambda p, b, i: QuoteNode(content=[Text("a *b* c, d.")])}
    b = _block(15, key="quote")
    assert parser.renderer.render(parser.parse_docx_node(b, 0), depth=0) == (
        "> a \\*b\\* c, d.\n\n"
    )
