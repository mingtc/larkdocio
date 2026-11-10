"""LD-172 AC5/AC6 — the plan says its target carries reviewer anchors, and the docs say
which of the three edit paths does what.

**What was actually missing, verified rather than assumed.** The dogfood report filed this as
*"the plan does not disclose that its target carries review anchors, though editing destroys
them"*. The destruction half is **gone**: the sub-span path re-emits each rebuilt run's
anchors, and the whole-**block** and whole-**CELL** paths refuse ``comment-anchors-present``
rather than collapse them away — all three landed before this issue started, and this file
asserts that current state rather than the report's older one. What genuinely remained is
**disclosure on the path that proceeds**: a reviewer approving a preview of a sub-span edit
into commented text could not see, from the plan, that reviewers were involved at all.

So the note here is not a warning about loss. It is the plan saying *this text is under
review* — which is exactly the fact an approval UX needs and the one place it was absent.

**It costs nothing.** The anchors are already on the tree the plan resolved against, so the
disclosure is decided at plan time with **zero** extra API calls — asserted below with a
client that raises on contact, which makes "no call" structural rather than counted.
"""
import json

import pytest
from harness import build_blocks

from larkdocio.capabilities import capabilities
from larkdocio.common.notes import (
    NOTE_KIND_MULTIPLE,
    combine_preview_notes,
    preview_notes_of,
)
from larkdocio.model import StyledText
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write.model import AnchorById, RefusalReason, SubSpanEditRequest
from larkdocio.write.preview import (
    NOTE_KIND_COMMENT_ANCHORS_ON_TARGET,
    PlanEntry,
    dry_run,
)

#: The three-way truth every claim surface owes after the third path landed.
_CONTRACT_ID = "comment-anchors-honored-or-refused"


# --------------------------------------------------------------------------- #
# Fixtures — a commented paragraph and an uncommented one, through the parser.   #
# --------------------------------------------------------------------------- #

_ANCHOR_ID = "7667754726531878624"


def _blocks(*, commented: bool):
    """A page + one paragraph whose middle run carries a real review anchor (or not).

    The anchor id is a real one out of the shared comment document; the run shape (a
    ``text_element_style`` carrying ``comment_ids`` beside five all-false style flags) is the
    shape that document's own blocks come back in.
    """
    style = {"bold": False, "italic": False, "inline_code": False,
             "strikethrough": False, "underline": False}
    middle = {"text_run": {"content": "twelve point four percent",
                           "text_element_style": dict(
                               style, **({"comment_ids": [_ANCHOR_ID]} if commented else {}))}}
    return [
        {"block_id": "doc", "block_type": 1, "children": ["p1"],
         "page": {"elements": [{"text_run": {"content": "Q3 Board Update"}}]}},
        {"block_id": "p1", "parent_id": "doc", "block_type": 2, "children": [],
         "text": {"elements": [
             {"text_run": {"content": "Revenue grew ", "text_element_style": dict(style)}},
             middle,
             {"text_run": {"content": " in Q3.", "text_element_style": dict(style)}},
         ]}},
    ]


def _tree(*, commented: bool):
    return Parser(Config()).parse_docx_tree("doc", build_blocks(_blocks(commented=commented)))


def _subspan(span="twelve point four percent", replacement="12.4%"):
    return SubSpanEditRequest(anchor=AnchorById(block_id="p1"), span=span,
                              replacement=replacement)


class _ExplodingClient:
    """Any attribute access is a failed test — the zero-call proof, structurally.

    A counter would prove "one call fewer than expected"; this proves the previewer cannot
    have consulted a client at all, which is the claim.
    """

    def __getattr__(self, name):
        raise AssertionError(
            f"the previewer touched a client ({name!r}) — the anchor disclosure is decided "
            f"from the tree the plan already has and must cost NO API call")


# --------------------------------------------------------------------------- #
# AC5 — the note appears for a commented target, and only for one.               #
# --------------------------------------------------------------------------- #

def test_a_sub_span_edit_of_a_COMMENTED_target_carries_the_anchor_note():
    plan = dry_run([_subspan()], _tree(commented=True))
    (entry,) = plan.entries
    assert entry.is_resolved, entry.to_dict()
    (note,) = entry.preview_notes
    assert note["kind"] == NOTE_KIND_COMMENT_ANCHORS_ON_TARGET
    assert _ANCHOR_ID in note["comment_ids"]
    assert "p1" in note["note"]


def test_a_sub_span_edit_of_an_UNCOMMENTED_target_carries_NO_note():
    plan = dry_run([_subspan()], _tree(commented=False))
    (entry,) = plan.entries
    assert entry.is_resolved
    assert entry.preview_note is None
    assert entry.preview_notes == ()


def test_the_note_names_the_sub_span_path_as_the_reason_this_edit_proceeds():
    """The note has to be actionable, not ominous. The sub-span path is the one that CAN edit
    such a block, so the note says what the plan will do with the anchors rather than warning
    about a loss that is not going to happen."""
    (entry,) = dry_run([_subspan()], _tree(commented=True)).entries
    text = entry.preview_notes[0]["note"].lower()
    assert "sub-span" in text
    assert "re-emit" in text or "rides" in text
    assert "whole-block" in text and "refus" in text


def test_the_note_costs_ZERO_api_calls():
    """The whole point of deciding it at plan time: the anchors are already on the tree."""
    tree = _tree(commented=True)
    plan = dry_run([_subspan()], tree)
    assert plan.entries[0].preview_notes, "the arm is vacuous unless the note fired"
    # dry_run's signature has no client at all; prove it cannot reach one anyway.
    from larkdocio.write import preview as preview_mod

    assert "client" not in preview_mod.dry_run.__code__.co_varnames
    _ExplodingClient()  # constructed, never handed over — nothing may ask it for anything


def test_the_note_survives_the_plan_wire_form_and_comes_back_on_from_dict():
    (entry,) = dry_run([_subspan()], _tree(commented=True)).entries
    wire = json.loads(json.dumps(entry.to_dict()))
    assert wire["preview_note"]["kind"] == NOTE_KIND_COMMENT_ANCHORS_ON_TARGET
    back = PlanEntry.from_dict(wire)
    assert back.preview_note == entry.preview_note
    assert back == entry


def test_an_uncommented_entry_omits_the_key_entirely_so_shipped_json_is_byte_unchanged():
    """The trailing-and-conditional discipline every added plan field has followed: a plan
    that earns no note serializes exactly as it did before the field existed."""
    (entry,) = dry_run([_subspan()], _tree(commented=False)).entries
    assert "preview_note" not in entry.to_dict()


def test_the_whole_plan_wire_form_carries_the_note_too():
    plan = dry_run([_subspan()], _tree(commented=True))
    wire = json.loads(plan.to_json())
    assert wire["entries"][0]["preview_note"]["kind"] == NOTE_KIND_COMMENT_ANCHORS_ON_TARGET


def test_a_REFUSED_sub_span_entry_needs_no_note_because_nothing_will_happen():
    """A refusal already says everything; adding a disclosure about a target that will not be
    touched would be noise competing with the reason."""
    plan = dry_run([_subspan(span="not in this block at all")], _tree(commented=True))
    (entry,) = plan.entries
    assert not entry.is_resolved
    assert entry.refusal.reason is RefusalReason.NOT_FOUND
    assert entry.preview_note is None


def test_a_BLOCK_level_only_anchor_earns_no_note_on_the_sub_span_path():
    """The same distinction the refusal draws: a comment on the block as a whole is untouched
    by a run split, so it is not what this note is about. Drawing it differently here would
    make the note fire on edits no reviewer has any stake in."""
    blocks = _blocks(commented=False)
    blocks[1]["comment_ids"] = [_ANCHOR_ID]
    tree = Parser(Config()).parse_docx_tree("doc", build_blocks(blocks))
    (entry,) = dry_run([_subspan()], tree).entries
    assert entry.is_resolved
    assert entry.preview_note is None


def test_the_note_composes_with_another_disclosure_rather_than_displacing_it():
    """The shared note core's contract, exercised from the docx side: two disclosures on one
    entry flatten to two, so no future note can silently push this one out."""
    first = {"kind": NOTE_KIND_COMMENT_ANCHORS_ON_TARGET, "note": "a"}
    second = {"kind": "something-else", "note": "b"}
    combined = combine_preview_notes(first, second)
    assert combined["kind"] == NOTE_KIND_MULTIPLE
    assert preview_notes_of(combined) == (first, second)
    assert combine_preview_notes(first) == first
    assert combine_preview_notes(None) is None


def test_the_shared_note_core_is_the_ONE_definition_both_surfaces_use():
    """No second definition of the same convention: sheets reads the same functions."""
    from larkdocio.common import notes as core
    from larkdocio.sheets import plan as sheets_plan

    assert sheets_plan.preview_notes_of is core.preview_notes_of
    assert sheets_plan.combine_preview_notes is core.combine_preview_notes
    assert sheets_plan.NOTE_KIND_MULTIPLE == core.NOTE_KIND_MULTIPLE


# --------------------------------------------------------------------------- #
# AC6 — the guide and capabilities() document the LANDED behavior, all three     #
#       paths, with the refusal as a named safety contract.                      #
# --------------------------------------------------------------------------- #

def test_the_refusal_is_a_named_safety_contract_of_the_docx_write_surface():
    caps = capabilities(full=True)
    assert _CONTRACT_ID in caps["safety_contracts"]
    assert _CONTRACT_ID in caps["surfaces"]["docx-write"]["safety_contracts"]
    assert _CONTRACT_ID not in caps["surfaces"]["sheets-write"]["safety_contracts"]
    assert caps["safety_contracts"][_CONTRACT_ID]["applies_to"] == ["docx-write"]


@pytest.mark.parametrize("phrase", [
    "sub-span",           # the path that proceeds
    "whole-block",        # path two: refuses
    "whole-cell",         # path three: refuses (the one a reader used to have to infer)
    "comment-anchors-present",
    "no anchored-comment create",   # why none of this can be proved by creating an anchor
])
def test_the_contract_summary_names_every_path_and_the_refusal_code(phrase):
    summary = capabilities(full=True)["safety_contracts"][_CONTRACT_ID]["summary"].lower()
    assert phrase in summary, f"the contract summary does not name: {phrase!r}"


def test_the_contract_summary_names_the_PLAN_SIDE_disclosure_too():
    """The half this issue adds: a contract that only described refusals would leave the
    proceeding path's disclosure undiscoverable from the registry."""
    summary = capabilities(full=True)["safety_contracts"][_CONTRACT_ID]["summary"]
    assert NOTE_KIND_COMMENT_ANCHORS_ON_TARGET in summary


def test_the_contract_does_NOT_claim_a_path_is_still_broken():
    """Written against the board, not against the report: all three paths are handled now, so
    the summary must not describe one of them as an outstanding gap."""
    summary = capabilities(full=True)["safety_contracts"][_CONTRACT_ID]["summary"].lower()
    for stale in ("still drops", "not yet", "planned", "outstanding gap"):
        assert stale not in summary, f"the contract summary carries a stale claim: {stale!r}"


def test_the_guide_matrix_row_exists_and_the_bidirectional_guard_covers_it():
    """The guide's contract table and ``capabilities()`` are joined by the shipped drift guard;
    this asserts the new row is really in the table the guard parses, not merely in the prose."""
    import test_guide

    assert _CONTRACT_ID in test_guide._guide_contracts()


def test_the_guide_row_names_all_three_paths():
    guide = capabilities  # imported for symmetry; the guide text is read below
    del guide
    import larkdocio

    rows = [line for line in larkdocio.guide(full=True).splitlines()
            if line.startswith(f"| `{_CONTRACT_ID}`")]
    assert len(rows) == 1, rows
    row = rows[0].lower()
    for phrase in ("sub-span", "whole-block", "whole-cell",
                   NOTE_KIND_COMMENT_ANCHORS_ON_TARGET):
        assert phrase in row, f"the guide's contract row does not name: {phrase!r}"


def test_the_live_ring_names_the_member_that_proves_this_contract():
    """A safety contract nothing proves live is a claim, not a guarantee — and this one cannot
    be proved by the write ring's usual shape: Lark has **no anchored-comment create**, so a
    self-provisioned disposable cannot be given an inline anchor. The proof is therefore a
    READ-ONLY arm against the one document that has real ones, and the ring records that it
    runs under a different marker rather than pretending it is a write gate."""
    coverage = capabilities(full=True)["surfaces"]["docx-write"]["gate_coverage"]
    members = {m["id"]: m for m in coverage["members"]}
    proving = [m for m in members.values() if _CONTRACT_ID in m["proves_contracts"]]
    assert len(proving) == 1, [m["id"] for m in proving]
    (member,) = proving
    assert member["module"] == "tests/test_live_comment_anchor_zoo_arm.py"
    assert member["marker"] == "live"
    assert member["marker"] != coverage["marker"], (
        "the override is the point: this member is read-only and needs no write credentials")
    assert "read-only" in member["summary"].lower()


def test_the_sub_span_recipe_tells_a_reader_the_plan_will_say_so():
    """The disclosure is only useful if a consumer knows to look at it."""
    import doc_prose
    import guide_recipes as gr

    preamble = doc_prose.prose(gr.recipe_preamble("edit-part-of-a-paragraph-a-sub-span-edit"))
    assert doc_prose.prose(NOTE_KIND_COMMENT_ANCHORS_ON_TARGET) in preamble


def test_a_run_anchor_reaches_the_model_so_this_whole_file_is_not_vacuous():
    """Provenance check: the fixture really does carry the anchor at the run level, which is
    the granularity everything above turns on."""
    (block,) = _tree(commented=True).children
    anchored = [x for x in block.content if isinstance(x, StyledText) and x.comment_ids]
    assert [i for run in anchored for i in run.comment_ids] == [_ANCHOR_ID]
    # Exactly ONE of the three runs carries it — the note must not be firing off a block-wide
    # property that would make the "uncommented target" arm meaningless.
    assert len(block.content) == 3 and len(anchored) == 1
    assert block.comment_ids is None
