"""text/code/equation family migration tests (LD-025).

The text family — text (2), code (14), equation (16) — now CONSTRUCTS model
nodes instead of concatenating strings. These tests assert the handler return
TYPES + their carried data (proving the migration happened); byte-identical
*output* is proven by the unchanged T1 goldens (test_golden.py), which flow the
nodes through the strangler shim + renderer.

KEEP (LD-096, mindfulness not immunity): unique handler return-TYPE / carried-data
pins the output-goldens don't hold — the text absent-attr -> None vs present-but-
empty -> [] distinction, styled-run -> StyledText carriage, code unknown-language
-> "" tag, the equation multi-element newline-strip/join, and the inline-vs-block
equation discriminant (an equation element inside a type-2 block -> InlineEquation,
not EquationBlockNode). A future audit may revisit.
"""
from harness import build_blocks

from larkdocio.model import (
    CodeNode,
    EquationBlockNode,
    InlineEquation,
    StyledText,
    Text,
    TextNode,
)
from larkdocio.read.parser import Parser
from larkdocio.read.config import Config


def _p():
    return Parser(Config())


# --- text (2) --------------------------------------------------------------

def test_text_handler_returns_text_node_with_inline_content():
    from larkdocio.blocks.text import handle_text

    b = build_blocks(
        [{"block_id": "t", "block_type": 2, "text": {"elements": [{"text_run": {"content": "hi"}}]}}]
    )[0]
    node = handle_text(_p(), b, 0)
    assert isinstance(node, TextNode)
    assert node.content == [Text("hi")]


def test_text_handler_absent_text_attr_maps_to_none_content():
    # No `text` attr -> content None (legacy handler emitted "" for this case).
    from larkdocio.blocks.text import handle_text

    b = build_blocks([{"block_id": "t", "block_type": 2}])[0]
    node = handle_text(_p(), b, 0)
    assert isinstance(node, TextNode) and node.content is None


def test_text_handler_present_but_empty_maps_to_empty_list():
    from larkdocio.blocks.text import handle_text

    b = build_blocks([{"block_id": "t", "block_type": 2, "text": {"elements": []}}])[0]
    node = handle_text(_p(), b, 0)
    assert isinstance(node, TextNode) and node.content == []


def test_text_handler_styled_run_is_styledtext():
    from larkdocio.blocks.text import handle_text

    b = build_blocks(
        [{"block_id": "t", "block_type": 2,
          "text": {"elements": [{"text_run": {"content": "b", "text_element_style": {"bold": True}}}]}}]
    )[0]
    node = handle_text(_p(), b, 0)
    assert isinstance(node.content[0], StyledText) and node.content[0].bold is True


# --- code (14) -------------------------------------------------------------

def test_code_handler_returns_code_node_with_language():
    from larkdocio.blocks.text import handle_code

    b = build_blocks(
        [{"block_id": "c", "block_type": 14,
          "code": {"style": {"language": 49}, "elements": [{"text_run": {"content": "print('hi')"}}]}}]
    )[0]
    node = handle_code(_p(), b, 0)
    assert isinstance(node, CodeNode)
    assert node.lang == "python"
    assert node.content == [Text("print('hi')")]


def test_code_handler_unknown_language_maps_to_empty_tag():
    from larkdocio.blocks.text import handle_code

    b = build_blocks(
        [{"block_id": "c", "block_type": 14,
          "code": {"style": {"language": 9999}, "elements": [{"text_run": {"content": "x"}}]}}]
    )[0]
    node = handle_code(_p(), b, 0)
    assert isinstance(node, CodeNode) and node.lang == ""


# --- equation (16) ---------------------------------------------------------

def test_equation_handler_returns_equation_block_node():
    from larkdocio.blocks.text import handle_equation

    b = build_blocks(
        [{"block_id": "e", "block_type": 16,
          "equation": {"elements": [{"equation": {"content": "a+b"}}]}}]
    )[0]
    node = handle_equation(_p(), b, 0)
    assert isinstance(node, EquationBlockNode)
    assert node.content == "a+b"


def test_equation_handler_joins_multiple_elements_stripping_newlines():
    from larkdocio.blocks.text import handle_equation

    b = build_blocks(
        [{"block_id": "e", "block_type": 16,
          "equation": {"elements": [{"equation": {"content": "a\n"}}, {"equation": {"content": "b\n"}}]}}]
    )[0]
    node = handle_equation(_p(), b, 0)
    assert node.content == "ab"


def test_inline_equation_in_text_block_is_inline_equation_node():
    # A type-2 block containing an equation element -> InlineEquation (not block).
    from larkdocio.blocks.text import handle_text

    b = build_blocks(
        [{"block_id": "t", "block_type": 2, "text": {"elements": [{"equation": {"content": "x^2"}}]}}]
    )[0]
    node = handle_text(_p(), b, 0)
    assert node.content == [InlineEquation("x^2")]
