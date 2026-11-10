"""File block (Type 23) rendering tests.

The handler must surface the file name AND the file token (for traceability,
since the attachment is not downloaded). It must also use a falsy-aware name
fallback so a ``name=None`` payload renders the literal fallback string rather
than the word ``None``.
"""
from harness import render


def _file_block(file_payload):
    page_id = "page0"
    file_id = "file0"
    return [
        {"block_id": page_id, "block_type": 1, "children": [file_id]},
        {"block_id": file_id, "block_type": 23, "file": file_payload},
    ]


def test_file_block_surfaces_token():
    out = render(_file_block({"token": "boxcnTOKEN123", "name": "report.pdf"}))
    assert "report.pdf" in out
    assert "boxcnTOKEN123" in out, (
        "File token must be surfaced for traceability, got:\n" + out
    )


def test_file_block_name_none_uses_fallback():
    out = render(_file_block({"token": "boxcnABC", "name": None}))
    assert "Unknown File Attachment" in out
    assert "None" not in out, (
        "name=None must fall back, not render the word 'None':\n" + out
    )
