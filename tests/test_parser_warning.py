"""Unknown-block warning enrichment test.

When the parser encounters a block type with no registered handler, it emits a
warning. That warning must carry enough diagnostic context to locate the
dropped content: the block's parent id and its child count (children that are
silently dropped along with the unknown block).
"""
import logging

from harness import render


def test_unknown_block_warning_includes_parent_and_child_count(caplog):
    # 9999 is not a registered block type; give it a parent and two children.
    blocks = [
        {"block_id": "root", "block_type": 1, "children": ["mystery"]},
        {
            "block_id": "mystery",
            "block_type": 9999,
            "parent_id": "root",
            "children": ["c1", "c2"],
        },
    ]

    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        render(blocks, doc_id="root")

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("9999" in m for m in warnings), warnings
    unknown_msgs = [m for m in warnings if "9999" in m]
    joined = "\n".join(unknown_msgs)
    # Parent id must be reported.
    assert "root" in joined, joined
    # Child count (2) must be reported.
    assert "2" in joined, joined
