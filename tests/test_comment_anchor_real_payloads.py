"""LD-163 — the carry and the refusal, driven by **real anchored payloads**.

Every other offline test of this fix uses either the opener spike's captured runs or a
hand-paired fixture. This file drives the whole chain — real payload → real SDK ``Block`` →
real parser → real model → real plan → real emitted body — off the **round-2 harvest**
(``tests/captures/comments-probe-round2-captures/10-harvest-docx.json``), which captured the shared
comment document's anchored blocks **verbatim** before anything was touched. Those payloads
are the only real inline-``comment_ids`` shapes that exist in this repository, and they carry
the detail a hand-authored fixture would not think to include: Lark returns
``bold``/``italic``/``inline_code``/``strikethrough``/``underline`` all **false** beside the
anchor, so the run's cleaned *style* is empty and the emitted style object is the anchor
**alone** — a shape no synthetic fixture in this suite had.

Why there is no live **write** arm for this fix (recorded here because the absence is
evidence, not an omission): Lark has **no anchored-comment create** on either surface — the
opener spike proved it across 18 candidate routes and the round-2 run re-confirmed it — so a
self-provisioned disposable **cannot be given** an inline anchor, and the only document that
has real ones is the shared comment zoo, which this issue may read and may never write. The
live read-only arm over that document is
``tests/test_live_comment_anchor_zoo_arm.py``; the payload leg it cannot cover is here,
against the same document's captured bytes.
"""
import json
import pathlib

import pytest
from harness import build_blocks

from log_reading_apply import reading_the_log
from larkdocio.model import StyledText
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write.apply import apply, build_subspan_update, build_whole_paragraph_update
apply = reading_the_log(apply)
from larkdocio.write.model import AnchorById, EditRequest, RefusalReason, SubSpanEditRequest
from larkdocio.write.preview import dry_run

from write_harness import StubOpener, _client

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_HARVEST = (REPO_ROOT / "tests" / "captures" / "comments-probe-round2-captures"
            / "10-harvest-docx.json")


def _harvest() -> dict:
    return json.loads(_HARVEST.read_text(encoding="utf-8"))


def _word_anchored_blocks() -> dict:
    """``{block_id: record}`` for every harvested block carrying **word-level** anchors."""
    blocks = {
        bid: rec for bid, rec in _harvest()["anchored_blocks"].items()
        if rec.get("word_level_anchors")
    }
    assert blocks, "the harvest carries no word-level anchored block — the capture moved"
    return blocks


def _ids(record) -> list:
    """The block's word-level ids, as the harvest recorded them."""
    return list(record["word_level_anchors"])


def _live_elements(record) -> list:
    """The block's real ``elements`` list, straight out of its verbatim payload."""
    container = record["comment_id_view"]["container_key"]
    return record["block_verbatim"][container]["elements"]


def _anchored_run(record):
    """``(index, element)`` of the first run in the payload that carries an anchor."""
    for index, element in enumerate(_live_elements(record)):
        style = (element.get("text_run") or {}).get("text_element_style") or {}
        if style.get("comment_ids"):
            return index, element
    raise AssertionError("no anchored run in a block the harvest labelled word-anchored")


_BLOCK_IDS = sorted(_word_anchored_blocks())


# --------------------------------------------------------------------------- #
# The payload leg — real runs through both builders                             #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("block_id", _BLOCK_IDS)
def test_a_real_anchored_run_shows_the_style_object_the_anchor_lives_in(block_id):
    """Provenance, executable: the harvested run really does carry ``comment_ids`` inside
    ``text_element_style``, beside five all-false style flags. That shape is the reason the
    field had to be carried separately from the *style* reducer — reduce the style alone and
    this run emits nothing at all."""
    record = _word_anchored_blocks()[block_id]
    _index, element = _anchored_run(record)
    style = element["text_run"]["text_element_style"]
    assert style["comment_ids"]
    assert not any(style.get(flag) for flag in
                   ("bold", "italic", "inline_code", "strikethrough", "underline"))


@pytest.mark.parametrize("block_id", _BLOCK_IDS)
def test_a_sub_span_edit_of_a_REAL_anchored_run_carries_its_real_ids(block_id):
    """The span is taken from the run's own text, so the region is the anchored run itself:
    the replacement run must go back carrying exactly the ids the document reports."""
    record = _word_anchored_blocks()[block_id]
    _index, element = _anchored_run(record)
    content = element["text_run"]["content"]
    span = content.strip().split(" ")[0]
    assert span and content.count(span) == 1, (span, content)

    body = build_subspan_update(_live_elements(record), span, "REPLACED")
    assert body is not None, "a real single-run anchored block must be splittable"
    runs = [el["text_run"] for el in body["update_text_elements"]["elements"]]
    replacement = [r for r in runs if r["content"] == "REPLACED"]
    assert len(replacement) == 1, runs
    assert replacement[0]["text_element_style"]["comment_ids"] == _ids(record)


@pytest.mark.parametrize("block_id", _BLOCK_IDS)
def test_a_whole_block_body_for_a_REAL_anchored_run_carries_no_anchor(block_id):
    """The rejected leading-run variant, checked against real data: the collapsed run never
    inherits a real reviewer's anchor."""
    record = _word_anchored_blocks()[block_id]
    body = build_whole_paragraph_update(_live_elements(record), "REPLACED WHOLE BLOCK")
    assert "comment_ids" not in json.dumps(body)


# --------------------------------------------------------------------------- #
# The model + plan leg — real payload → real SDK Block → real parser → refusal   #
# --------------------------------------------------------------------------- #

def _tree_for(record):
    """Parse the real block (under a synthetic page root) with the real reader."""
    verbatim = json.loads(json.dumps(record["block_verbatim"]))
    verbatim.pop("children", None)          # its real children are outside this capture
    root = {
        "block_id": "zoo-root",
        "block_type": 1,
        "page": {"elements": [{"text_run": {"content": "Comment zoo"}}]},
        "children": [verbatim["block_id"]],
    }
    blocks = build_blocks([root, verbatim])
    return Parser(Config()).parse_docx_tree("zoo-root", blocks)


@pytest.mark.parametrize("block_id", _BLOCK_IDS)
def test_the_real_payload_reaches_the_model_at_the_word_level(block_id):
    record = _word_anchored_blocks()[block_id]
    (block,) = _tree_for(record).children
    runs = [x for x in block.content if isinstance(x, StyledText) and x.comment_ids]
    assert runs, block.content
    assert [i for run in runs for i in run.comment_ids] == _ids(record)


@pytest.mark.parametrize("block_id", _BLOCK_IDS)
def test_a_whole_block_edit_of_a_REAL_anchored_block_refuses_with_its_real_ids(block_id):
    record = _word_anchored_blocks()[block_id]
    tree = _tree_for(record)
    plan = dry_run([EditRequest(anchor=AnchorById(block_id=block_id),
                                replacement="REPLACED WHOLE BLOCK")], tree)
    (entry,) = plan.entries
    assert entry.refusal.reason is RefusalReason.COMMENT_ANCHORS_PRESENT, entry.to_dict()
    for comment_id in _ids(record):
        assert comment_id in entry.refusal.detail
    assert block_id in entry.refusal.detail


@pytest.mark.parametrize("block_id", _BLOCK_IDS)
def test_the_sub_span_recovery_the_refusal_NAMES_resolves_on_the_same_real_block(block_id):
    """The recovery has to work on the very block that refused, or the detail is a lie."""
    record = _word_anchored_blocks()[block_id]
    span = record["plain_text"].strip().split(" ")[0]
    plan = dry_run([SubSpanEditRequest(anchor=AnchorById(block_id=block_id), span=span,
                                       replacement="X")], _tree_for(record))
    (entry,) = plan.entries
    assert entry.is_resolved, entry.to_dict()


def test_the_refusal_on_real_blocks_issues_ZERO_api_calls():
    """Pre-I/O, over the whole harvested set at once: a batch of whole-block edits against
    every real anchored block writes nothing — the opener would raise on any request."""
    records = _word_anchored_blocks()
    trees = {bid: _tree_for(rec) for bid, rec in records.items()}
    opener = StubOpener([])
    for block_id, tree in trees.items():
        plan = dry_run([EditRequest(anchor=AnchorById(block_id=block_id),
                                    replacement="REPLACED")], tree)
        log = apply(plan, _client(opener), "doc-never-touched")
        assert log.entries[0].refusal.reason is RefusalReason.COMMENT_ANCHORS_PRESENT
    assert opener.requests == []
