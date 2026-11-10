"""LD-080 — per-parse accumulator reset (safety net for the reset refactor).

The five per-instance accumulators (`img_tokens`, `board_tokens`, `file_tokens`,
`mention_user_ids`, `block_map`) are seeded in `__init__` but neither parse entry
(`parse_docx_content` / `parse_docx_tree`) reset them. Calling either method twice
on ONE Parser therefore DOUBLED every token list and MERGED two docs' block_maps
(stale-id resolution / unbounded growth). Production was safe only because every
caller built a fresh Parser per parse — an implicit "one Parser per parse" contract.

These tests pin the intended per-parse scoping: two sequential parses on ONE Parser
are independent — the second parse's accumulators reflect ONLY the second doc.
"""
from harness import build_blocks

from larkdocio.read.parser import Parser
from larkdocio.read.config import Config


def _doc(page_id, img_id, text_id, token, mention_id):
    """A minimal page with one image (queues `token` on img_tokens) and one text
    block carrying an @mention (queues `mention_id` on mention_user_ids)."""
    return [
        {"block_id": page_id, "block_type": 1, "children": [text_id, img_id]},
        {"block_id": text_id, "parent_id": page_id, "block_type": 2,
         "text": {"elements": [{"mention_user": {"user_id": mention_id}}]}},
        {"block_id": img_id, "parent_id": page_id, "block_type": 27,
         "image": {"token": token, "caption": {"content": "cap"}}},
    ]


def test_two_sequential_parse_docx_content_calls_are_independent():
    """Two `parse_docx_content` calls on ONE Parser must NOT accumulate: the token
    lists and block_map after the second parse reflect ONLY the second doc."""
    parser = Parser(Config())

    doc_a = _doc("pageA", "imgA", "txtA", "tokA", "ou_a")
    doc_b = _doc("pageB", "imgB", "txtB", "tokB", "ou_b")

    out_a = parser.parse_docx_content("pageA", build_blocks(doc_a))
    out_b = parser.parse_docx_content("pageB", build_blocks(doc_b))

    # Token lists reflect ONLY the second parse (not doubled / not merged).
    assert parser.img_tokens == ["tokB"]
    assert parser.mention_user_ids == ["ou_b"]

    # block_map holds ONLY the second doc's blocks — the first doc's ids are gone.
    assert set(parser.block_map) == {"pageB", "imgB", "txtB"}

    # And output is stable: parsing doc_b on this reused Parser matches a fresh one.
    fresh = Parser(Config()).parse_docx_content("pageB", build_blocks(doc_b))
    assert out_b == fresh
    # (doc_a still rendered fine on its own first pass.)
    assert out_a == Parser(Config()).parse_docx_content("pageA", build_blocks(doc_a))


def test_two_sequential_parse_docx_tree_calls_are_independent():
    """Same independence guarantee for the writer's non-rendering entry."""
    parser = Parser(Config())

    doc_a = _doc("pageA", "imgA", "txtA", "tokA", "ou_a")
    doc_b = _doc("pageB", "imgB", "txtB", "tokB", "ou_b")

    parser.parse_docx_tree("pageA", build_blocks(doc_a))
    parser.parse_docx_tree("pageB", build_blocks(doc_b))

    assert parser.img_tokens == ["tokB"]
    assert parser.mention_user_ids == ["ou_b"]
    assert set(parser.block_map) == {"pageB", "imgB", "txtB"}


def test_mixed_content_then_tree_entries_are_independent():
    """Crossing the two entries (render, then get-tree) on ONE Parser — the W1
    anchor-resolver-alongside-render case the audit called out — is also clean."""
    parser = Parser(Config())

    doc_a = _doc("pageA", "imgA", "txtA", "tokA", "ou_a")
    doc_b = _doc("pageB", "imgB", "txtB", "tokB", "ou_b")

    parser.parse_docx_content("pageA", build_blocks(doc_a))
    parser.parse_docx_tree("pageB", build_blocks(doc_b))

    assert parser.img_tokens == ["tokB"]
    assert parser.mention_user_ids == ["ou_b"]
    assert set(parser.block_map) == {"pageB", "imgB", "txtB"}
