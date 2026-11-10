"""Behavioral tests for heading block handlers (core/blocks/headings.py).

Heading-newline fix: a heading line must be newline-separated from any child
content it renders, mirroring handle_page. Pre-fix the heading text and the
first child concatenate onto the same line.
"""
from harness import render

from builders import heading1 as _heading1, text_block as _text


def test_heading_with_child_newline_separated():
    # Mirror handle_page: a heading with children must be newline-separated from
    # its child content (a blank line between the heading and the first child),
    # so the heading text line never concatenates onto child output.
    blocks = [
        _heading1("h", "doc", "My Heading", ["c1"]),
        _text("c1", "h", "child body"),
    ]
    out = render(blocks, doc_id="h")
    assert "# My Heading" in out, f"heading missing: {out!r}"
    assert "child body" in out, f"child missing: {out!r}"
    # Blank-line separation between the heading line and the child, as handle_page emits.
    assert "# My Heading\n\nchild body" in out, (
        f"heading and child not blank-line separated: {out!r}"
    )
