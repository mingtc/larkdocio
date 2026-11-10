"""Image block (Type 27) rendering tests.

The handler must surface the image caption (as alt text and/or a caption line)
and, on a missing token, emit a visible marker rather than silently dropping
the block.
"""
from harness import render


def _image_block(image_payload):
    page_id = "page0"
    img_id = "img0"
    return [
        {"block_id": page_id, "block_type": 1, "children": [img_id]},
        {"block_id": img_id, "block_type": 27, "image": image_payload},
    ]


def test_image_caption_surfaced():
    out = render(_image_block({
        "token": "boxcnTOKEN123",
        "caption": {"content": "A descriptive caption"},
    }))
    assert "boxcnTOKEN123" in out
    assert "A descriptive caption" in out, (
        "Image caption must be surfaced as alt text and/or a caption line:\n" + out
    )


def test_image_missing_token_visible_marker():
    out = render(_image_block({"caption": {"content": "orphan"}}))
    assert "[Image: missing token]" in out, (
        "Missing-token image must emit a visible marker, not '':\n" + repr(out)
    )
