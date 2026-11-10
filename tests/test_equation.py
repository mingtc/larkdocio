"""Behavioral tests for equation rendering (core/blocks/text.py).

Equation rendering must be STRUCTURAL, not derived from element count:
- An inline equation element (inside a text block's elements) renders as $...$.
- A type-16 equation block renders as $$...$$ fenced EXACTLY ONCE.
"""
from harness import render


def _text_block(elements):
    return [{
        "block_id": "t",
        "parent_id": "doc",
        "block_type": 2,
        "text": {"elements": elements},
        "children": [],
    }]


def test_single_equation_paragraph_is_inline():
    # A paragraph containing only one equation element must render inline ($...$),
    # not block ($$...$$).
    blocks = _text_block([
        {"equation": {"content": "E=mc^2"}},
    ])
    out = render(blocks, doc_id="t")
    assert "$E=mc^2$" in out, f"single equation not inline: {out!r}"
    assert "$$" not in out, f"single equation wrongly block-wrapped: {out!r}"


def test_equation_amid_text_is_inline():
    blocks = _text_block([
        {"text_run": {"content": "before "}},
        {"equation": {"content": "x^2"}},
        {"text_run": {"content": " after"}},
    ])
    out = render(blocks, doc_id="t")
    assert "before $x^2$ after" in out, f"equation amid text not inline: {out!r}"
    assert "$$" not in out, f"inline equation wrongly block-wrapped: {out!r}"


def test_equation_block_type16_single_fence():
    # Type-16 equation block: exactly one $$...$$ pair, no nested $$.
    blocks = [{
        "block_id": "e",
        "parent_id": "doc",
        "block_type": 16,
        "equation": {"elements": [{"equation": {"content": "a+b"}}]},
        "children": [],
    }]
    out = render(blocks, doc_id="e")
    assert out.count("$$") == 2, f"expected exactly one $$...$$ fence: {out!r}"
    assert "a+b" in out, f"equation content lost: {out!r}"
    assert "$$$" not in out, f"nested/malformed $$ fence: {out!r}"
