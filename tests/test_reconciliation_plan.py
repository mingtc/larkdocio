"""LD-233 — matching + diffing: the reconciliation plan.

Offline, every test. The reconciler makes **zero** API calls and this module proves it
(``test_ac8_*`` installs a network spy over the whole reconcile call), so the suite here
needs no credentials, no scratch document and no network.

The amplifier is real: ``tests/fixtures/reconcile/leg2-trials/`` holds the **24 committed
LD-197 trial outputs** — actual LLM edits of a marked projection across delete /
edit-prose / insert / reorder / table-cell / tighten shapes, two models and three document
lengths — copied here **deliberately** (the suite never imports ``dev/`` probe code) next
to ``leg2-sources.json``, the three source projections they were made from. Both sides were
edited after recording, to remove a product name and a planning-calendar wording: the sources
first, the outputs afterwards to match, so the text is no longer the models' verbatim output.
The marker structure each edit produced is unchanged, which is what these tests read.
"""
import json
import socket
import urllib.request
from pathlib import Path

import pytest

from larkdocio.model.projection import (
    BlockIdProjection,
    project_block_ids,
    unescape_literals,
)
from larkdocio.model.renderer import _ESCAPABLE
from write_harness import _page, _para

from larkdocio.write import reconcile as _reconcile_from_package
from larkdocio.write.model import RefusalReason
from larkdocio.write.reconcile import (
    ABSENT_DISPOSITION_MEANINGS,
    RECONCILIATION_REFUSAL_REASONS,
    RECONCILIATION_STATE_MEANINGS,
    AbsentBlockDisposition,
    ReconciliationEntry,
    ReconciliationPlan,
    ReconciliationState,
    reconcile,
)

FIXTURES = Path(__file__).parent / "fixtures" / "reconcile"


# --------------------------------------------------------------------------- #
# Helpers — hand-built projections, and the committed corpus.                  #
# --------------------------------------------------------------------------- #

def projection(*blocks, opaque=()):
    """A :class:`BlockIdProjection` over ``(block_id, markdown)`` pairs, plus an
    optional leading unmarked head (a pair whose id is ``None``)."""
    parts = []
    ids = []
    for block_id, markdown in blocks:
        if block_id is None:
            parts.append(markdown)
            continue
        ids.append(block_id)
        parts.append(f"<!-- lark:block:{block_id} -->\n{markdown}")
    return BlockIdProjection(
        markdown="\n\n".join(parts) + "\n",
        block_ids=tuple(ids),
        opaque_block_ids=tuple(opaque),
    )


def edited(*blocks):
    """The same shape as :func:`projection`, but returning only the Markdown — this is
    what an agent hands back."""
    return projection(*blocks).markdown


def corpus_sources():
    return json.loads((FIXTURES / "leg2-sources.json").read_text(encoding="utf-8"))


def corpus_trials():
    return sorted((FIXTURES / "leg2-trials").glob("*.json"))


def source_projection(name):
    src = corpus_sources()[name]
    return BlockIdProjection(
        markdown=src["markdown"],
        block_ids=tuple(src["block_ids"]),
        opaque_block_ids=tuple(src["opaque_block_ids"]),
    )


def states(plan):
    return [(e.state, e.block_id) for e in plan.entries]


def reasons(plan):
    return [r.reason for r in plan.refusals]


# --------------------------------------------------------------------------- #
# AC1 — matching resolves against the PROJECTION'S EMITTED ID SET (D11).        #
# --------------------------------------------------------------------------- #

def test_ac1_a_marker_in_the_emitted_set_matches_its_block():
    p = projection(("p1", "one"), ("p2", "two"))
    plan = reconcile(p, edited(("p1", "one edited"), ("p2", "two")))
    assert plan.ok
    assert states(plan) == [
        (ReconciliationState.EDITED, "p1"),
        (ReconciliationState.UNCHANGED, "p2"),
    ]


def test_ac1_an_id_absent_from_the_document_refuses_as_invented():
    """An id the document does not contain is not an 'unknown id' to look up — the
    emitted set is the only identity source, so it is INVENTED."""
    p = projection(("p1", "one"))
    plan = reconcile(p, edited(("p1", "one"), ("doxcnNOTREAL", "smuggled")))
    assert not plan.ok
    assert reasons(plan) == [RefusalReason.MARKER_INVENTED]
    assert "doxcnNOTREAL" in plan.refusals[0].detail


def test_ac1_an_id_appearing_twice_refuses_and_never_picks_one():
    p = projection(("p1", "one"), ("p2", "two"))
    plan = reconcile(p, edited(("p1", "one"), ("p2", "two"), ("p1", "one again")))
    assert not plan.ok
    assert reasons(plan) == [RefusalReason.MARKER_DUPLICATED]
    assert "p1" in plan.refusals[0].detail
    assert plan.entries == ()


def test_ac1_a_marker_shaped_id_that_was_never_emitted_is_the_antiforgery_case():
    """The anti-forgery rule: marker-SHAPED is not identity. The id is well-formed and
    plausible; it was simply never emitted, so it refuses."""
    p = projection(("p1", "one"))
    forged = (
        "<!-- lark:block:p1 -->\n"
        "one\n\n"
        "<!-- lark:block:doxcnForgedByProse -->\n"
        "text a consumer wrote that names a block id\n"
    )
    plan = reconcile(p, forged)
    assert not plan.ok
    assert reasons(plan) == [RefusalReason.MARKER_INVENTED]
    assert "doxcnForgedByProse" in plan.refusals[0].detail


# --------------------------------------------------------------------------- #
# AC2 — a typed, frozen, JSON-round-trippable, non-forgeable plan.              #
# --------------------------------------------------------------------------- #

def test_ac2_plan_enumerates_every_state_with_pre_and_post_images():
    p = projection(
        ("p1", "one"),
        ("p2", "two"),
        ("img", "![](tok)"),
        ("p3", "three"),
        opaque=("img",),
    )
    plan = reconcile(
        p,
        edited(("p1", "one rewritten"), ("p2", "two"), ("p3", "three\n\nbrand new")),
        absent=AbsentBlockDisposition.DELETE,
    )
    assert plan.ok
    assert states(plan) == [
        (ReconciliationState.EDITED, "p1"),
        (ReconciliationState.UNCHANGED, "p2"),
        (ReconciliationState.CONSERVED_OPAQUE, "img"),
        (ReconciliationState.UNCHANGED, "p3"),
        (ReconciliationState.INSERTED, None),
    ]
    edit = plan.entries[0]
    assert (edit.before, edit.after) == ("one", "one rewritten")


def test_ac2_plan_is_frozen():
    plan = reconcile(projection(("p1", "one")), edited(("p1", "one")))
    with pytest.raises(Exception):
        plan.entries = ()
    with pytest.raises(Exception):
        plan.entries[0].state = ReconciliationState.EDITED


def test_ac2_plan_json_round_trips_losslessly():
    p = projection(("p1", "one"), ("t", "| a |\n| --- |\n| 1 |"), opaque=("t",))
    plan = reconcile(p, edited(("p1", "one rewritten\n\nand a new paragraph"), ("t", "| a |\n| --- |\n| 1 |")))
    wire = json.loads(json.dumps(plan.to_dict()))
    assert ReconciliationPlan.from_dict(wire) == plan


def test_ac2_refusing_plan_json_round_trips_too():
    plan = reconcile(projection(("p1", "one")), edited(("p1", "one"), ("nope", "x")))
    wire = json.loads(json.dumps(plan.to_dict()))
    assert ReconciliationPlan.from_dict(wire) == plan


@pytest.mark.parametrize("kwargs", [
    # An EDITED entry whose images are equal is not an edit at all.
    dict(state=ReconciliationState.EDITED, block_id="p1", before="a", after="a"),
    # An EDITED entry with no pre-image cannot be applied to anything.
    dict(state=ReconciliationState.EDITED, block_id="p1", before=None, after="b"),
    # An INSERTED entry that names a block id claims an identity it does not have.
    dict(state=ReconciliationState.INSERTED, block_id="p1", after="new"),
    # A DELETED entry with a post-image is a rewrite wearing a deletion's name.
    dict(state=ReconciliationState.DELETED, block_id="p1", before="a", after="b"),
    # A CONSERVED_OPAQUE entry with a post-image contradicts conservation.
    dict(state=ReconciliationState.CONSERVED_OPAQUE, block_id="p1", before="a", after="b"),
    # An UNCHANGED entry whose images differ is a lie.
    dict(state=ReconciliationState.UNCHANGED, block_id="p1", before="a", after="b"),
    # A non-inserted entry with no block id names nothing.
    dict(state=ReconciliationState.UNCHANGED, block_id=None, before="a", after="a"),
])
def test_ac2_entry_is_not_forgeable(kwargs):
    with pytest.raises(ValueError):
        ReconciliationEntry(**kwargs)


def test_ac2_a_plan_that_refuses_carries_no_entries():
    """The house posture: a reconciliation that refuses refuses WHOLE. A half-plan over a
    document whose marker state is ambiguous is the dangerous artifact."""
    with pytest.raises(ValueError):
        ReconciliationPlan(
            entries=(ReconciliationEntry.unchanged("p1", "one"),),
            refusals=(plan_refusal(),),
        )


def plan_refusal():
    from larkdocio.write.model import Refusal
    return Refusal.marker_invented("an id that was never emitted: 'x'")


def test_ac2_the_plan_is_readable_before_anything_is_applied():
    """``reconcile`` produces the plan and nothing else — no client, no requests, no
    apply path. The plan IS the deliverable of this rung."""
    plan = reconcile(projection(("p1", "one")), edited(("p1", "two")))
    assert isinstance(plan, ReconciliationPlan)
    assert plan.change_count == 1
    assert plan.touched_block_ids == ("p1",)


# --------------------------------------------------------------------------- #
# AC3 — a missing marker does NOT mean delete (D10).                           #
# --------------------------------------------------------------------------- #

def test_ac3_an_absent_marker_refuses_by_default_naming_the_block_and_its_text():
    p = projection(("p1", "one"), ("p2", "the paragraph nobody meant to lose"))
    plan = reconcile(p, edited(("p1", "one")))
    assert not plan.ok
    assert reasons(plan) == [RefusalReason.MARKER_ABSENT]
    detail = plan.refusals[0].detail
    assert "p2" in detail
    assert "the paragraph nobody meant to lose" in detail


def test_ac3_the_same_input_under_the_explicit_disposition_plans_a_delete():
    p = projection(("p1", "one"), ("p2", "the paragraph nobody meant to lose"))
    plan = reconcile(p, edited(("p1", "one")), absent=AbsentBlockDisposition.DELETE)
    assert plan.ok
    assert states(plan) == [
        (ReconciliationState.UNCHANGED, "p1"),
        (ReconciliationState.DELETED, "p2"),
    ]
    assert plan.entries[1].before == "the paragraph nobody meant to lose"


def test_ac3_the_default_disposition_is_refuse():
    p = projection(("p1", "one"), ("p2", "two"))
    assert reconcile(p, edited(("p1", "one"))) == reconcile(
        p, edited(("p1", "one")), absent=AbsentBlockDisposition.REFUSE
    )


# --------------------------------------------------------------------------- #
# AC4 — THE SEGMENT MODEL.                                                     #
# --------------------------------------------------------------------------- #

def test_ac4_insert_between_two_marked_blocks_anchors_to_the_preceding_marker():
    p = projection(("p1", "one"), ("p2", "two"))
    plan = reconcile(p, edited(("p1", "one\n\nbrand new"), ("p2", "two")))
    assert plan.ok
    inserted = [e for e in plan.entries if e.state is ReconciliationState.INSERTED]
    assert len(inserted) == 1
    assert (inserted[0].anchor_block_id, inserted[0].anchor_position) == ("p1", "after")
    assert inserted[0].after == "brand new"
    assert inserted[0].block_id is None


def test_ac4_insert_at_the_head_anchors_to_the_document_root():
    p = projection(("p1", "one"))
    plan = reconcile(p, "a new opening paragraph\n\n<!-- lark:block:p1 -->\none\n")
    assert plan.ok
    inserted = [e for e in plan.entries if e.state is ReconciliationState.INSERTED]
    assert len(inserted) == 1
    assert inserted[0].anchor_block_id is None
    assert inserted[0].after == "a new opening paragraph"


def test_ac4_insert_at_the_tail_anchors_to_the_last_surviving_marker():
    p = projection(("p1", "one"), ("p2", "two"))
    plan = reconcile(p, edited(("p1", "one"), ("p2", "two\n\nappended at the tail")))
    assert plan.ok
    inserted = [e for e in plan.entries if e.state is ReconciliationState.INSERTED]
    assert len(inserted) == 1
    assert (inserted[0].anchor_block_id, inserted[0].anchor_position) == ("p2", "after")


def test_ac4_two_adjacent_inserts_share_the_predecessor_and_keep_their_order():
    p = projection(("p1", "one"), ("p2", "two"))
    plan = reconcile(p, edited(("p1", "one\n\nfirst new\n\nsecond new"), ("p2", "two")))
    assert plan.ok
    inserted = [e for e in plan.entries if e.state is ReconciliationState.INSERTED]
    assert [e.anchor_block_id for e in inserted] == ["p1", "p1"]
    assert [e.after for e in inserted] == ["first new", "second new"]


def test_ac4_an_insert_never_anchors_to_another_inserted_block():
    """The property that keeps the compiled batch free of intra-batch dependencies: an
    anchor is always a SURVIVING marker (or the root), never a block this plan creates."""
    p = projection(("p1", "one"), ("p2", "two"))
    plan = reconcile(p, edited(("p1", "one\n\nnew a\n\nnew b"), ("p2", "two\n\nnew c")))
    surviving = set(p.block_ids)
    for entry in plan.entries:
        if entry.state is ReconciliationState.INSERTED:
            assert entry.anchor_block_id is None or entry.anchor_block_id in surviving


def test_ac4_content_inserted_before_the_marked_block_keeps_its_position():
    """The haiku trial's real shape: the agent put its new paragraph after the marker but
    BEFORE the marked block's own content. Position is knowable, so it is kept."""
    p = projection(("p1", "one"))
    plan = reconcile(p, edited(("p1", "brand new\n\none")))
    assert plan.ok
    inserted = [e for e in plan.entries if e.state is ReconciliationState.INSERTED]
    assert (inserted[0].anchor_block_id, inserted[0].anchor_position) == ("p1", "before")


def test_ac4_a_segment_whose_block_cannot_be_located_refuses_rather_than_guesses():
    """Several units and none of them is the marked block: an edit-plus-insert is not
    separable from an insert-plus-edit, and picking one would rewrite the wrong block."""
    p = projection(("p1", "one"))
    plan = reconcile(p, edited(("p1", "one rewritten\n\nand something new")))
    assert not plan.ok
    assert reasons(plan) == [RefusalReason.SEGMENT_AMBIGUOUS]
    assert "p1" in plan.refusals[0].detail


# --------------------------------------------------------------------------- #
# AC5 — CONSERVATION PROVEN, three ways.                                       #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("disposition", list(AbsentBlockDisposition))
def test_ac5_an_omitted_opaque_block_is_conserved_under_either_disposition(disposition):
    """The centerpiece: the edited projection dropped the image ENTIRELY and the block is
    still conserved — under the refusing default and under the explicit deletion
    disposition alike."""
    p = projection(("p1", "one"), ("img", "![](tok)"), ("p2", "two"), opaque=("img",))
    plan = reconcile(p, edited(("p1", "one"), ("p2", "two")), absent=disposition)
    assert plan.ok, [r.detail for r in plan.refusals]
    assert states(plan) == [
        (ReconciliationState.UNCHANGED, "p1"),
        (ReconciliationState.CONSERVED_OPAQUE, "img"),
        (ReconciliationState.UNCHANGED, "p2"),
    ]
    assert plan.change_count == 0


def test_ac5_an_opaque_block_cannot_be_edited_even_when_its_text_changed():
    p = projection(("p1", "one"), ("t", "| a | b |\n| --- | --- |\n| 1 | 2 |"), opaque=("t",))
    plan = reconcile(p, edited(("p1", "one"), ("t", "| a | b |\n| --- | --- |\n| 9 | 9 |")))
    assert plan.ok
    assert states(plan) == [
        (ReconciliationState.UNCHANGED, "p1"),
        (ReconciliationState.CONSERVED_OPAQUE, "t"),
    ]
    assert plan.change_count == 0


@pytest.mark.parametrize("disposition", list(AbsentBlockDisposition))
def test_ac5_the_negative_no_planned_change_names_the_conserved_block(disposition):
    """The third proof, at the level this issue owns: nothing the plan would compile
    names the conserved id — not as a target and not as an anchor."""
    p = projection(
        ("p1", "one"), ("img", "![](tok)"), ("p2", "two"), ("gone", "dropped"),
        opaque=("img",),
    )
    plan = reconcile(
        p, edited(("p1", "one rewritten"), ("p2", "two\n\nand a new paragraph")),
        absent=disposition,
    )
    if disposition is AbsentBlockDisposition.REFUSE:
        assert not plan.ok  # 'gone' is editable and absent — that refuses
        return
    assert plan.ok
    assert "img" not in plan.touched_block_ids
    assert all(e.block_id != "img" and e.anchor_block_id != "img" for e in plan.changes)


# --------------------------------------------------------------------------- #
# AC6 — block-type mutation refuses.                                           #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("before,after", [
    ("a plain paragraph", "## A heading"),          # paragraph -> heading
    ("## A heading", "a plain paragraph"),          # heading -> paragraph
    ("- a bullet", "1. an ordered item"),           # bullet -> ordered
    ("a plain paragraph", "- a bullet"),            # paragraph -> list
    ("a plain paragraph", "> a quote"),             # paragraph -> quote
    ("a plain paragraph", "```\ncode\n```"),        # paragraph -> code
])
def test_ac6_a_block_edited_into_a_different_type_refuses(before, after):
    plan = reconcile(projection(("p1", before)), edited(("p1", after)))
    assert not plan.ok
    assert reasons(plan) == [RefusalReason.BLOCK_TYPE_MUTATION]
    detail = plan.refusals[0].detail
    assert "p1" in detail
    assert "delete" in detail and "insert" in detail


def test_ac6_a_heading_edited_to_a_different_level_refuses():
    plan = reconcile(projection(("h", "## Two")), edited(("h", "### Three")))
    assert not plan.ok
    assert reasons(plan) == [RefusalReason.BLOCK_TYPE_MUTATION]


def test_ac6_an_edit_that_keeps_the_type_is_an_ordinary_edit():
    plan = reconcile(projection(("h", "## Two")), edited(("h", "## Two, revised")))
    assert plan.ok
    assert states(plan) == [(ReconciliationState.EDITED, "h")]


# --------------------------------------------------------------------------- #
# AC7 — reorder refuses, precisely (D12).                                      #
# --------------------------------------------------------------------------- #

def test_ac7_reordered_markers_refuse_naming_why():
    p = projection(("p1", "one"), ("p2", "two"), ("p3", "three"))
    plan = reconcile(p, edited(("p1", "one"), ("p3", "three"), ("p2", "two")))
    assert not plan.ok
    assert reasons(plan) == [RefusalReason.MARKER_ORDER_CHANGED]
    detail = plan.refusals[0].detail
    assert "p2" in detail and "p3" in detail
    assert "Moving a block is not expressible" in detail


def test_ac7_a_reorder_is_never_faked_as_delete_plus_insert():
    p = projection(("p1", "one"), ("p2", "two"))
    plan = reconcile(
        p, edited(("p2", "two"), ("p1", "one")), absent=AbsentBlockDisposition.DELETE
    )
    assert not plan.ok
    assert plan.entries == ()


# --------------------------------------------------------------------------- #
# AC8 — a no-op reconciliation is a NO-OP, and issues zero API calls.          #
# --------------------------------------------------------------------------- #

def test_ac8_an_unedited_projection_reconciles_to_zero_changes():
    p = projection(("p1", "one"), ("p2", "two"), ("img", "![](tok)"), opaque=("img",))
    plan = reconcile(p, p.markdown)
    assert plan.ok
    assert plan.change_count == 0
    assert plan.changes == ()
    assert [e.state for e in plan.entries] == [
        ReconciliationState.UNCHANGED,
        ReconciliationState.UNCHANGED,
        ReconciliationState.CONSERVED_OPAQUE,
    ]


def test_ac8_reconciliation_issues_zero_api_calls(monkeypatch):
    """The call-count spy. ``reconcile`` is offline by construction; this is the proof,
    over the whole committed corpus rather than one input."""
    calls = []
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda *a, **k: calls.append("urlopen") or (_ for _ in ()).throw(AssertionError),
    )
    monkeypatch.setattr(
        socket.socket, "connect",
        lambda *a, **k: calls.append("connect") or (_ for _ in ()).throw(AssertionError),
    )
    for path in corpus_trials():
        trial = json.loads(path.read_text(encoding="utf-8"))
        reconcile(source_projection(trial["trial"]["doc"]), trial["edited_document"])
        reconcile(
            source_projection(trial["trial"]["doc"]),
            trial["edited_document"],
            absent=AbsentBlockDisposition.DELETE,
        )
    assert calls == []


# --------------------------------------------------------------------------- #
# AC9 — THE REAL-EDIT CORPUS IS THE AMPLIFIER (24 committed LD-197 trials).     #
# --------------------------------------------------------------------------- #

#: What each committed trial must reconcile to, keyed by its file stem. Derived from the
#: trial's own recorded shape, not from the algorithm: a `reorder` trial refuses; a
#: `delete-block` trial refuses under the default and plans exactly one delete under the
#: explicit disposition; a `table-cell` trial is the conservation case (the corpus tables
#: are the opaque blocks), so it plans NOTHING.
EXPECTED = {
    "C-edit-prose-1": ("edits", 1),
    "C-tighten-1": ("edits", 4),
    "L-delete-block-1": ("absent", ["l15"]),
    "L-edit-prose-1-C-haiku": ("edits", 1),
    "L-edit-prose-1": ("edits", 1),
    "L-table-cell-1": ("conserved", "l23"),
    "L-tighten-1-C-haiku": ("edits", 15),
    "L-tighten-1": ("edits", 14),
    "S-delete-block-1": ("absent", ["s06"]),
    "S-delete-block-2": ("absent", ["s06"]),
    "S-edit-prose-1": ("edits", 1),
    "S-edit-prose-2": ("edits", 1),
    "S-insert-block-1-C-haiku": ("insert", ("s05", "before")),
    "S-insert-block-1": ("insert", ("s04", "after")),
    "S-insert-block-2": ("insert", ("s04", "after")),
    "S-reorder-1": ("reorder", None),
    "S-reorder-2": ("reorder", None),
    "S-table-cell-1": ("conserved", "s08"),
    "S-table-cell-2": ("conserved", "s08"),
    "S-tighten-1-C-haiku": ("edits", 4),
    "S-tighten-1": ("edits", 4),
    "S-tighten-2": ("edits", 4),
    "S-tighten-armB-1": ("edits", 4),
    "S-tighten-armB-2": ("edits", 4),
}


def test_ac9_the_corpus_is_the_committed_24_trials():
    assert len(corpus_trials()) == 24
    assert {p.stem for p in corpus_trials()} == set(EXPECTED)


@pytest.mark.parametrize("path", corpus_trials(), ids=lambda p: p.stem)
def test_ac9_every_committed_real_agent_edit_reconciles_to_its_expected_shape(path):
    trial = json.loads(path.read_text(encoding="utf-8"))
    p = source_projection(trial["trial"]["doc"])
    plan = reconcile(p, trial["edited_document"])
    kind, expected = EXPECTED[path.stem]

    # Whatever the shape, EVERY opaque block of the source is conserved and nothing the
    # plan would compile names it.
    for block_id in p.opaque_block_ids:
        if plan.ok:
            assert (ReconciliationState.CONSERVED_OPAQUE, block_id) in states(plan)
            assert block_id not in plan.touched_block_ids

    if kind == "reorder":
        assert not plan.ok
        assert reasons(plan) == [RefusalReason.MARKER_ORDER_CHANGED]
        return
    if kind == "absent":
        assert not plan.ok
        assert reasons(plan) == [RefusalReason.MARKER_ABSENT] * len(expected)
        deleting = reconcile(
            p, trial["edited_document"], absent=AbsentBlockDisposition.DELETE
        )
        assert deleting.ok, [r.detail for r in deleting.refusals]
        assert [e.block_id for e in deleting.changes] == expected
        assert all(
            e.state is ReconciliationState.DELETED for e in deleting.changes
        )
        return

    assert plan.ok, [r.detail for r in plan.refusals]
    if kind == "conserved":
        # The agent edited a table cell. The table is opaque, so the whole document
        # reconciles to NOTHING — the conservation contract, on a real agent edit.
        assert plan.change_count == 0
        assert (ReconciliationState.CONSERVED_OPAQUE, expected) in states(plan)
    elif kind == "edits":
        assert [e.state for e in plan.changes] == [ReconciliationState.EDITED] * expected
    elif kind == "insert":
        anchor, position = expected
        inserted = [e for e in plan.changes if e.state is ReconciliationState.INSERTED]
        assert len(inserted) == 1
        assert (inserted[0].anchor_block_id, inserted[0].anchor_position) == (anchor, position)


def test_ac9_no_trial_smuggles_an_invented_id_past_the_emitted_set():
    """The corpus's own claim (0 invented ids across 302 markers) re-derived by the
    reconciler rather than trusted from the capture's classification block."""
    for path in corpus_trials():
        trial = json.loads(path.read_text(encoding="utf-8"))
        p = source_projection(trial["trial"]["doc"])
        plan = reconcile(p, trial["edited_document"])
        assert RefusalReason.MARKER_INVENTED not in reasons(plan), path.stem


# --------------------------------------------------------------------------- #
# AC10 — COMPARISON HAPPENS IN THE DECODED DOMAIN (D7.1).                      #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("projected,normalized_body", [
    # Inline — unescaping changes CHARACTERS only.
    ("The uptime was 99\\.9 percent\\.", "The uptime was 99.9 percent."),
    # LD-240 / AC7 — MULTI-LINE with a STRUCTURAL escape: unescaping changes the
    # Markdown structure too (one paragraph becomes paragraph + list item). Every
    # AC10 case used to be a single-line paragraph, which is the blind spot that let
    # LD-240 ship.
    ("intro line\n\\- second line bullet", "intro line\n- second line bullet"),
])
def test_ac10_an_escape_normalizing_editor_produces_zero_changes(
    projected, normalized_body
):
    """The projection escapes literals; an editor that merely normalized ``99\\.9`` back
    to ``99.9`` touched nothing, and the plan must say so."""
    p = projection(("p1", projected))
    plan = reconcile(p, edited(("p1", normalized_body)))
    assert plan.ok
    assert plan.change_count == 0
    assert states(plan) == [(ReconciliationState.UNCHANGED, "p1")]


def test_ac10_an_escape_preserving_editor_produces_zero_changes_too():
    p = projection(("p1", "The uptime was 99\\.9 percent\\."))
    plan = reconcile(p, edited(("p1", "The uptime was 99\\.9 percent\\.")))
    assert plan.ok
    assert plan.change_count == 0


def test_ac10_a_real_edit_under_either_escaping_is_still_an_edit():
    p = projection(("p1", "The uptime was 99\\.9 percent\\."))
    for after in ("The uptime was 99.8 percent.", "The uptime was 99\\.8 percent\\."):
        plan = reconcile(p, edited(("p1", after)))
        assert plan.ok
        assert plan.change_count == 1
        assert plan.entries[0].before == "The uptime was 99.9 percent."
        assert plan.entries[0].after == "The uptime was 99.8 percent."


def test_ac10_the_decoder_is_the_shipped_one_and_refuses_rather_than_guesses():
    """LD-230 AC9's decoder, reused rather than re-authored: a backslash the escape
    policy never emits cannot be decoded, so the reconciliation refuses."""
    p = projection(("p1", "plain"))
    plan = reconcile(p, edited(("p1", "a path C:\\x that the policy never escapes")))
    assert not plan.ok
    assert reasons(plan) == [RefusalReason.UNDECODABLE_TEXT]
    assert "p1" in plan.refusals[0].detail


def test_ac10_unmarked_head_content_is_compared_decoded_too():
    p = projection((None, "# Title with 99\\.9"), ("p1", "one"))
    plan = reconcile(p, "# Title with 99.9\n\n<!-- lark:block:p1 -->\none\n")
    assert plan.ok
    assert plan.change_count == 0


def test_ac10_changed_unmarked_content_refuses_because_it_carries_no_identity():
    p = projection((None, "# Title"), ("p1", "one"))
    plan = reconcile(p, "# A different title\n\n<!-- lark:block:p1 -->\none\n")
    assert not plan.ok
    assert reasons(plan) == [RefusalReason.UNMARKED_CONTENT_CHANGED]


# --------------------------------------------------------------------------- #
# LD-240 — escape-only normalization that changes the Markdown STRUCTURE.       #
#                                                                               #
# AC10 held while unescaping changed only CHARACTERS. Where the projection had  #
# to escape a metacharacter that carries STRUCTURE, the source segment parsed   #
# to one unit and the normalized one to two, ``_locate`` found nothing, and the #
# plan refused ``segment-ambiguous`` — taking every unrelated edit with it.     #
# The fix is AC10's own rule at SEGMENT granularity: decoded whole-segment      #
# identity is ``unchanged``, however many units either side parses into.        #
# --------------------------------------------------------------------------- #

#: The filed repro, verbatim: what the projection emits for a text block whose second
#: line starts with a hyphen, and what an editor that ONLY normalized escaping hands
#: back. Pinned as constants because both halves are the bug.
REPRO_PROJECTED = "intro line\n\\- second line bullet"
REPRO_NORMALIZED = "intro line\n- second line bullet"

MARKER_PREFIX = "<!-- lark:block:"


def normalize_escaping(markdown):
    """The document an editor that ONLY normalized escaping hands back: every non-marker
    line run through :func:`unescape_literals`, and nothing else touched at all."""
    return "\n".join(
        line if line.startswith(MARKER_PREFIX) else unescape_literals(line)
        for line in markdown.split("\n")
    )


def network_spy(monkeypatch):
    """A list that stays empty unless something reaches for the network."""
    calls = []
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda *a, **k: calls.append("urlopen") or (_ for _ in ()).throw(AssertionError),
    )
    monkeypatch.setattr(
        socket.socket, "connect",
        lambda *a, **k: calls.append("connect") or (_ for _ in ()).throw(AssertionError),
    )
    return calls


def real_projection(second_line, *, extra=()):
    """A projection made by the READER's own escaper — not by this test's guess at it.

    The first block is a two-line paragraph whose second line is ``second_line``; the
    escaped shape is whatever :func:`project_block_ids` really emits.
    """
    paragraphs = [_para("b1", f"intro line\n{second_line}"), _para("b2", "untouched")]
    paragraphs.extend(_para(bid, text) for bid, text in extra)
    return project_block_ids(_page(*paragraphs))


# --- AC1: the no-op ---------------------------------------------------------- #

def test_ld240_ac1_the_filed_repro_normalizes_to_a_noop(monkeypatch):
    calls = network_spy(monkeypatch)
    p = projection(("b1", REPRO_PROJECTED), ("b2", "untouched neighbour"))

    plan = reconcile(p, edited(("b1", REPRO_NORMALIZED), ("b2", "untouched neighbour")))

    assert plan.ok
    assert plan.refusals == ()
    assert plan.change_count == 0
    assert states(plan) == [
        (ReconciliationState.UNCHANGED, "b1"),
        (ReconciliationState.UNCHANGED, "b2"),
    ]
    assert calls == []


def test_ld240_ac1_the_same_no_op_through_the_readers_own_escaper():
    """The escaped shape is the reader's, not the test's: the projection is rendered,
    and the edited document is that projection with ONLY the escaping decoded."""
    p = real_projection("- second line bullet")
    assert REPRO_PROJECTED in p.markdown, p.markdown

    plan = reconcile(p, normalize_escaping(p.markdown))

    assert plan.ok, [r.detail for r in plan.refusals]
    assert plan.change_count == 0
    assert all(e.state is ReconciliationState.UNCHANGED for e in plan.entries)


# --- AC2: the blast radius --------------------------------------------------- #

def test_ld240_ac2_the_rest_of_the_plan_survives_the_normalized_block():
    """One incidentally-normalized block used to refuse the whole batch. The genuinely
    edited block is now the plan's ONE change, and nothing refuses."""
    p = projection(
        ("b1", REPRO_PROJECTED), ("b2", "untouched neighbour"), ("b3", "third block")
    )

    plan = reconcile(p, edited(
        ("b1", REPRO_NORMALIZED),
        ("b2", "untouched neighbour"),
        ("b3", "third block, genuinely edited"),
    ))

    assert plan.refusals == ()
    assert plan.ok
    assert plan.change_count == 1
    assert [(e.state, e.block_id) for e in plan.changes] == [
        (ReconciliationState.EDITED, "b3")
    ]


# --- AC3: exhaustive over the escaper's OWN alphabet ------------------------- #

@pytest.mark.parametrize("ch", list(_ESCAPABLE), ids=lambda c: f"chr-{ord(c)}")
def test_ld240_ac3_every_character_the_escaper_knows_normalizes_to_a_noop(ch):
    """Driven off ``renderer._ESCAPABLE`` itself, so a future escaper change is covered
    without a new case. ``.`` and ``)`` are only markers after a digit, so they are put
    in the ordered-list shape the escaper actually escapes.

    The ONE exception is the backslash, and it is AC6's rule rather than a gap: a line
    whose literal text starts with ``\\`` projects as ``\\\\``, and decoding THAT leaves a
    lone backslash the policy never emits — not comparable, so still a refusal.
    """
    second_line = f"1{ch} second line" if ch in ".)" else f"{ch} second line"
    p = real_projection(second_line)
    assert "\\" + ch in p.markdown, p.markdown          # the escaper really escaped it

    plan = reconcile(p, normalize_escaping(p.markdown))

    if ch == "\\":
        assert not plan.ok
        assert reasons(plan) == [RefusalReason.UNDECODABLE_TEXT]
        return
    assert plan.ok, [r.detail for r in plan.refusals]
    assert plan.change_count == 0
    assert all(e.state is ReconciliationState.UNCHANGED for e in plan.entries)


#: The shapes that really FORM the structure each metacharacter opens — a lone ``~`` or
#: ``|`` on a line does not. Every one of these diverged in unit count before the fix
#: (the recorded red set), which is what makes this table the bug class itself.
STRUCTURE_FORMING = [
    ("-", "- bullet", "bullet list"),
    ("+", "+ bullet", "bullet list"),
    ("*", "* bullet", "bullet list"),
    ("#", "# heading", "heading"),
    (">", "> quote", "block quote"),
    ("`", "``` fenced", "code fence"),
    ("~", "~~~ fenced", "code fence"),
    ("_", "___", "thematic break"),
    (".", "1. ordered", "ordered list"),
    (")", "1) ordered", "ordered list"),
    ("|", "| a | b |\n| --- | --- |\n| 1 | 2 |", "table"),
    ("<", "<div>html block</div>", "HTML block"),
    ("[", "[ref]: http://example.test/", "link-reference definition"),
]


@pytest.mark.parametrize("ch,second_line,structure", STRUCTURE_FORMING,
                         ids=[s[2].replace(" ", "-") + f"-{s[0]!r}" for s in STRUCTURE_FORMING])
def test_ld240_ac3_the_structure_forming_shapes_normalize_to_a_noop(
    ch, second_line, structure
):
    p = real_projection(second_line)
    assert "\\" + ch in p.markdown, p.markdown

    plan = reconcile(p, normalize_escaping(p.markdown))

    assert plan.ok, f"{structure}: " + repr([r.detail for r in plan.refusals])
    assert plan.change_count == 0
    assert all(e.state is ReconciliationState.UNCHANGED for e in plan.entries)


# --- AC4: the whole-plan refusal doctrine is untouched ----------------------- #

def test_ld240_ac4_a_genuinely_ambiguous_segment_still_refuses_the_WHOLE_plan():
    """A real addition beside a real edit is still not separable — and the refusal still
    takes the whole batch, including the unrelated edit on ``b2``."""
    p = projection(("b1", "one"), ("b2", "two"))

    plan = reconcile(p, edited(
        ("b1", "one rewritten\n\nand something new"), ("b2", "two edited")
    ))

    assert not plan.ok
    assert reasons(plan) == [RefusalReason.SEGMENT_AMBIGUOUS]
    assert plan.entries == ()                    # b2's real edit dies with it
    assert plan.change_count == 0
    detail = plan.refusals[0].detail
    assert "b1" in detail
    assert "two separate rounds" in detail       # the same detail vocabulary


def test_ld240_ac4_the_refusal_vocabulary_is_unchanged():
    """No reason added, removed or renamed by this fix — the reconciler's whole
    vocabulary, spelled out, so a change to it has to be deliberate."""
    assert sorted(r.value for r in RECONCILIATION_REFUSAL_REASONS) == [
        "block-type-mutation",
        # LD-574's compiled-no-op refusal. LD-240 added no reason and this guard's point
        # stands: a change to the vocabulary has to be deliberate. This one is — it is the
        # refusal that stops a counted change compiling to a request that writes nothing.
        "change-not-expressible",
        "conserved-block-re-created",
        "marker-absent",
        "marker-dropped",
        "marker-duplicated",
        "marker-invented",
        "marker-mangled",
        "marker-order-changed",
        "marker-orphaned",
        "marker-relocated",
        "merge-not-expressible",
        "not-in-dialect",
        "segment-ambiguous",
        "undecodable-text",
        "unmarked-content-changed",
    ]


# --- AC5: the neighbouring refusals still bite ------------------------------- #

def test_ld240_ac5a_one_character_of_real_difference_is_still_an_edit():
    p = projection(("p1", "The uptime was 99\\.9 percent\\."))
    plan = reconcile(p, edited(("p1", "The uptime was 99.8 percent.")))
    assert plan.ok
    assert plan.change_count == 1
    assert plan.entries[0].after == "The uptime was 99.8 percent."


def test_ld240_ac5b_a_segment_holding_another_blocks_text_still_refuses_relocated():
    p = projection(("b1", REPRO_PROJECTED), ("b2", "the neighbour's own text"))
    plan = reconcile(p, edited(("b1", "the neighbour's own text"), ("b2", "the neighbour's own text")))
    assert not plan.ok
    assert RefusalReason.MARKER_RELOCATED in reasons(plan)


def test_ld240_ac5c_an_emptied_segment_still_refuses_orphaned():
    p = projection(("b1", REPRO_PROJECTED), ("b2", "untouched neighbour"))
    plan = reconcile(p, edited(("b1", ""), ("b2", "untouched neighbour")))
    assert not plan.ok
    assert reasons(plan) == [RefusalReason.MARKER_ORPHANED]


def test_ld240_ac5d_an_opaque_block_is_still_conserved_not_unchanged():
    p = projection(
        ("b1", REPRO_PROJECTED), ("b2", "untouched neighbour"), opaque=("b1",)
    )
    plan = reconcile(p, edited(("b1", REPRO_NORMALIZED), ("b2", "untouched neighbour")))
    assert plan.ok
    assert plan.change_count == 0
    assert states(plan) == [
        (ReconciliationState.CONSERVED_OPAQUE, "b1"),
        (ReconciliationState.UNCHANGED, "b2"),
    ]


# --- AC6: undecodable is "not comparable", never a match --------------------- #

def test_ld240_ac6_an_undecodable_segment_never_reads_as_identical():
    """The identity check must not be reached at all for text the decoder refuses."""
    p = projection(("b1", REPRO_PROJECTED))
    plan = reconcile(p, edited(("b1", REPRO_NORMALIZED + "\n\na path C:\\x")))
    assert not plan.ok
    assert reasons(plan) == [RefusalReason.UNDECODABLE_TEXT]
    assert "b1" in plan.refusals[0].detail


# --- The combined case stays refused BY DESIGN (§ Out of Scope) -------------- #

def test_ld240_normalized_AND_edited_stays_refused_by_design():
    """Decoded texts differ AND the unit count diverges: nothing distinguishes
    "normalized escaping plus edited prose" from "deliberately split into two blocks",
    and the two readings differ by rewriting the block into something else. Refusing
    here IS the two-commit route — a design decision, not a residual defect."""
    p = projection(("b1", REPRO_PROJECTED))
    plan = reconcile(p, edited(("b1", "intro line edited\n- second line bullet")))
    assert not plan.ok
    assert reasons(plan) == [RefusalReason.SEGMENT_AMBIGUOUS]


# --------------------------------------------------------------------------- #
# AC12 — the front door: the surface is registered and reachable.              #
# --------------------------------------------------------------------------- #

def test_ac12_reconcile_is_exported_from_the_write_package():
    assert _reconcile_from_package is reconcile


def test_ac12_reconcile_is_registered_on_the_docx_write_surface():
    """Registered as the surface's `reconciliation` answer rather than as a seventh
    request family: it compiles none of its own, so listing it among the operations would
    claim a request family the engine does not have."""
    from larkdocio import capabilities
    from larkdocio.write import reconcile as _entry_point  # noqa: F401
    from larkdocio.write.reconcile import (
        ABSENT_DISPOSITION_MEANINGS,
        RECONCILIATION_CONTRACT,
        RECONCILIATION_REFUSAL_REASONS,
        RECONCILIATION_STATE_MEANINGS,
    )

    surface = capabilities(full=True)["surfaces"]["docx-write"]
    assert "reconcile" not in {op["name"] for op in surface["operations"]}
    registered = surface["reconciliation"]
    assert registered["entry_point"] == "larkdocio.write.reconcile"
    assert registered["returns"] == "ReconciliationPlan"
    assert registered["contract"] == RECONCILIATION_CONTRACT
    assert registered["state_meanings"] == RECONCILIATION_STATE_MEANINGS
    assert registered["absent_dispositions"] == ABSENT_DISPOSITION_MEANINGS
    assert registered["refusal_reasons"] == [
        r.value for r in RECONCILIATION_REFUSAL_REASONS
    ]


def test_ac12_the_registered_vocabularies_are_complete_in_both_directions():
    """A state or disposition minted without its meaning — or a meaning for one that no
    longer exists — reddens here rather than shipping a registry with a hole in it."""
    assert set(RECONCILIATION_STATE_MEANINGS) == {s.value for s in ReconciliationState}
    assert set(ABSENT_DISPOSITION_MEANINGS) == {
        d.value for d in AbsentBlockDisposition
    }
    assert all(v.strip() for v in RECONCILIATION_STATE_MEANINGS.values())
    assert all(v.strip() for v in ABSENT_DISPOSITION_MEANINGS.values())


def test_ac12_every_refusal_the_reconciler_mints_is_registered():
    """Derived from the whole module's own source, not from a second list: a refusal
    factory called anywhere in ``reconcile.py`` — ``reconcile()``'s body or any of its
    stage helpers — whose reason is unregistered reddens, so the registry cannot
    silently fall behind the code."""
    import ast
    import importlib
    import inspect

    from larkdocio.write.model import Refusal

    # THE SHADOW TRAP (LD-363): ``import larkdocio.write.reconcile as module`` binds the
    # re-exported FUNCTION, not the submodule — ``write/__init__.py`` does
    # ``from .reconcile import reconcile``, so the package attribute ``reconcile`` is the
    # function and the ``import ... as`` form resolves to it. ``inspect.getsource`` then
    # read only ``reconcile()``'s own body, and every ``Refusal.*`` mint in a sibling
    # helper was invisible to this scan. ``importlib.import_module`` returns the real
    # module regardless of the parent-package attribute, which is what the docstring
    # above has always claimed to scan.
    module = importlib.import_module("larkdocio.write.reconcile")
    assert inspect.ismodule(module), "the guard must scan the module, not the re-export"

    tree = ast.parse(inspect.getsource(module))
    minted = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "Refusal"
    }
    # ``Refusal.from_dict`` is the plan DESERIALIZER (``ReconciliationPlan.from_dict``
    # rebuilds refusals from a payload) — it takes a dict, not a detail string, and mints
    # no new reason. It sits outside ``reconcile()``'s body, so it too was invisible until
    # the scope was widened. Excluding it is only honest if it really is not a factory, so
    # the loop below proves that from the signature rather than trusting the name; a NEW
    # non-factory ``Refusal.*`` call site reddens here until it is listed deliberately.
    NOT_A_REFUSAL_FACTORY = {"from_dict"}
    for name in sorted(NOT_A_REFUSAL_FACTORY):
        params = inspect.signature(getattr(Refusal, name)).parameters
        assert "detail" not in params, (
            f"{name} takes a detail string — it is a refusal factory and must not be excluded"
        )

    factories = minted - NOT_A_REFUSAL_FACTORY
    assert factories, "the AST scan found no refusal factories — the guard would be vacuous"
    registered = set(RECONCILIATION_REFUSAL_REASONS)
    for factory in sorted(factories):
        reason = getattr(Refusal, factory)("probe").reason
        assert reason in registered, f"{factory} mints an unregistered reason: {reason}"
