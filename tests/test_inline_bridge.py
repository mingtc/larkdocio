"""Tests for build_inline — the SDK-text -> inline-model builder (LD-025).

build_inline turns an SDK text payload (``b.quote``, ``b.heading1``, ``b.text``
...) into a list of typed inline model nodes. After the text-family migration
(LD-025) it produces REAL typed inlines — no ``RawInline`` bridge:

* a plain literal run      -> :class:`Text`     (escapable literal text)
* a styled / linked run    -> :class:`StyledText`
* ``mention_user``         -> :class:`MentionUser`
* ``mention_doc``          -> :class:`MentionDoc`
* an inline ``equation``   -> :class:`InlineEquation`
* an unsupported variant   -> :class:`UnsupportedInline`

The rendered string stays byte-identical to the prior formatter — proven here by
comparing ``render_inline(build_inline(...))`` to the string helper
``parse_docx_text_element`` (which is now itself a thin wrapper over the model).
"""
from harness import build_blocks

from larkdocio.model import (
    InlineEquation,
    MarkdownRenderer,
    MentionDoc,
    MentionUser,
    StyledText,
    Text,
    UnsupportedInline,
)
from larkdocio.blocks.text import build_inline, parse_docx_text_element
from larkdocio.read.parser import Parser
from larkdocio.read.config import Config


def _text_obj(block_type, key, payload_elements):
    """Build one SDK block and return its text-bearing sub-object (b.<key>)."""
    d = {
        "block_id": "b",
        "parent_id": "root",
        "block_type": block_type,
        key: {"elements": payload_elements},
    }
    b = build_blocks([d])[0]
    return getattr(b, key)


def test_plain_run_maps_to_text_node():
    parser = Parser(Config())
    obj = _text_obj(15, "quote", [{"text_run": {"content": "A quoted line"}}])
    nodes = build_inline(parser, obj)
    assert nodes == [Text("A quoted line")]


def test_plain_run_renders_byte_identical_to_its_content():
    # A plain run's rendered form IS its content — no wrappers, no markers.
    parser = Parser(Config())
    obj = _text_obj(15, "quote", [{"text_run": {"content": "plain prose, nothing to escape"}}])
    nodes = build_inline(parser, obj)
    assert MarkdownRenderer().render_inline(nodes) == "plain prose, nothing to escape"


def test_plain_run_with_pairable_markers_is_escaped():
    # UPDATED BY LD-130 (maintainer-consented output change): a plain run carrying a
    # PAIRABLE `*...*` used to emit live emphasis — literal text masquerading as
    # markup. It is now escaped, so the text round-trips as text.
    parser = Parser(Config())
    obj = _text_obj(15, "quote", [{"text_run": {"content": "raw *stars* stay raw"}}])
    nodes = build_inline(parser, obj)
    assert MarkdownRenderer().render_inline(nodes) == r"raw \*stars\* stay raw"


def test_styled_run_maps_to_styledtext_node_byte_identical():
    parser = Parser(Config())
    element = {"text_run": {"content": "bold", "text_element_style": {"bold": True}}}
    obj = _text_obj(15, "quote", [element])
    nodes = build_inline(parser, obj)
    # A styled run is now a typed StyledText node (no RawInline).
    assert len(nodes) == 1 and isinstance(nodes[0], StyledText)
    assert nodes[0].content == "bold" and nodes[0].bold is True
    # Rendering it is byte-identical to the string helper (itself model-backed).
    legacy = parse_docx_text_element(parser, obj.elements[0])
    assert parser.renderer.render_inline(nodes) == legacy == "**bold**"


def test_mention_doc_maps_to_mention_doc_node():
    parser = Parser(Config())
    element = {"mention_doc": {"title": "Doc", "url": "https://x/y"}}
    obj = _text_obj(15, "quote", [element])
    nodes = build_inline(parser, obj)
    assert nodes == [MentionDoc("Doc", "https://x/y")]
    assert MarkdownRenderer().render_inline(nodes) == "[Doc](https://x/y)"


def test_mention_user_maps_to_mention_user_node():
    parser = Parser(Config())
    obj = _text_obj(15, "quote", [{"mention_user": {"user_id": "ou_1"}}])
    nodes = build_inline(parser, obj)
    assert nodes == [MentionUser("ou_1")]
    assert MarkdownRenderer().render_inline(nodes) == "@ou_1"


def test_inline_equation_maps_to_inline_equation_node():
    parser = Parser(Config())
    obj = _text_obj(15, "quote", [{"equation": {"content": "a^2\n"}}])
    nodes = build_inline(parser, obj)
    # Trailing newline stripped at build time.
    assert nodes == [InlineEquation("a^2")]
    assert MarkdownRenderer().render_inline(nodes) == "$a^2$"


def test_unsupported_variant_maps_to_unsupported_node():
    parser = Parser(Config())
    obj = _text_obj(15, "quote", [{"reminder": {}}])
    nodes = build_inline(parser, obj)
    assert nodes == [UnsupportedInline("reminder")]
    assert MarkdownRenderer().render_inline(nodes) == "[unsupported inline: reminder]"


def test_mixed_elements_preserve_order_and_kinds():
    parser = Parser(Config())
    obj = _text_obj(
        15,
        "quote",
        [
            {"text_run": {"content": "plain "}},
            {"text_run": {"content": "bold", "text_element_style": {"bold": True}}},
        ],
    )
    nodes = build_inline(parser, obj)
    assert isinstance(nodes[0], Text) and nodes[0].content == "plain "
    assert isinstance(nodes[1], StyledText) and nodes[1].content == "bold"
    assert MarkdownRenderer().render_inline(nodes) == "plain **bold**"


def test_element_with_multiple_members_yields_multiple_nodes():
    # A single TextElement may populate several union members; each contributes
    # a node, in fixed order — byte-identical to the string formatter's join.
    parser = Parser(Config())
    obj = _text_obj(
        15,
        "quote",
        [{"text_run": {"content": "hi "}, "mention_user": {"user_id": "u1"}}],
    )
    nodes = build_inline(parser, obj)
    assert nodes == [Text("hi "), MentionUser("u1")]
    legacy = parse_docx_text_element(parser, obj.elements[0])
    assert parser.renderer.render_inline(nodes) == legacy == "hi @u1"


def test_none_and_empty_return_empty_list():
    parser = Parser(Config())
    assert build_inline(parser, None) == []
    obj = _text_obj(15, "quote", [])
    assert build_inline(parser, obj) == []


def test_run_with_present_but_falsey_style_is_still_byte_identical():
    # An all-false style object exists (not None) -> a StyledText with all flags
    # off, which renders as the bare content. Byte-identical to the formatter.
    parser = Parser(Config())
    element = {"text_run": {"content": "hi", "text_element_style": {"bold": False}}}
    obj = _text_obj(15, "quote", [element])
    nodes = build_inline(parser, obj)
    legacy = parse_docx_text_element(parser, obj.elements[0])
    assert parser.renderer.render_inline(nodes) == legacy == "hi"
