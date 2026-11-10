"""LD-579 — the conserved-opaque entry DISCLOSES that its body read back differently.

Offline, every test. The reconciler already computes the signal (``_diff_segment``'s single
``_locate`` call) and used to drop it; this module pins that it is now **carried** on the
entry, that the wording states **both** readings and asserts neither, that nothing about what
compiles moves, and that no refusal vocabulary is created anywhere.

The point of the field is the ambiguity: ``start is None`` means *either* the consumer edited
the opaque body *or* the projection reshaped it and the editor normalised the reshaping.
Refusing on that predicate produces false refusals on documents nobody edited (the round's own
evidence: ``dev/dogfood5/DIGEST.md`` § 7 P1c ``:685-687``), which is why the ruled shape is a
disclosure.
"""
import ast
import inspect
import json
import re
from dataclasses import fields
from pathlib import Path

import pytest

from larkdocio.model.projection import BlockIdProjection
from larkdocio.write.reconcile import (
    CONSERVED_BODY_DIFFERS_MEANING,
    RECONCILIATION_REFUSAL_REASONS,
    RECONCILIATION_STATE_MEANINGS,
    AbsentBlockDisposition,
    ReconciliationEntry,
    ReconciliationPlan,
    ReconciliationState,
    reconcile,
)

SRC = Path(__file__).resolve().parent.parent / "src" / "larkdocio"


# --------------------------------------------------------------------------- #
# Helpers — hand-built projections (the same shape test_reconciliation_plan     #
# uses, kept local so this module owns its own fixtures).                      #
# --------------------------------------------------------------------------- #

def projection(*blocks, opaque=()):
    parts, ids = [], []
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
    return projection(*blocks).markdown


#: One plain block and one opaque one — the smallest document that can carry the disclosure.
SOURCE = projection(("p1", "one"), ("img", "![](tok)"), opaque=("img",))


def conserved(plan):
    return [e for e in plan.entries if e.state is ReconciliationState.CONSERVED_OPAQUE]


def norm(text):
    return " ".join(text.split())


def function_ast(module_path, name):
    tree = ast.parse(Path(module_path).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in {module_path}")


# --------------------------------------------------------------------------- #
# AC1 — THE FIELD: the signal the reconciler already computed, carried.        #
# --------------------------------------------------------------------------- #

def test_ac1_a_conserved_body_that_read_back_differently_is_disclosed():
    plan = reconcile(SOURCE, edited(("p1", "one"), ("img", "a caption someone typed")))
    assert plan.ok
    entry, = conserved(plan)
    assert entry.state is ReconciliationState.CONSERVED_OPAQUE
    assert entry.body_differs is True


def test_ac1_a_conserved_body_that_came_back_intact_says_so_and_absence_is_not_used():
    """``False`` is a real answer and is stated: absence means *no opinion*, not *no*."""
    plan = reconcile(SOURCE, edited(("p1", "one edited"), ("img", "![](tok)")))
    assert plan.ok
    entry, = conserved(plan)
    assert entry.body_differs is False


def test_ac1_a_conserved_block_whose_marker_never_CAME_BACK_has_no_opinion():
    """Nothing read back, so there is nothing to compare — and re-deriving a comparison the
    reconciler did not make is exactly what this issue forbids. ``None``: no opinion."""
    plan = reconcile(
        SOURCE, edited(("p1", "one")), absent=AbsentBlockDisposition.DELETE)
    entry, = conserved(plan)
    assert entry.body_differs is None


def test_ac1_a_state_that_cannot_have_an_opinion_cannot_carry_one():
    plan = reconcile(
        SOURCE,
        edited(("p1", "one rewritten\n\nbrand new"), ("img", "![](tok)")),
    )
    for entry in plan.entries:
        if entry.state is not ReconciliationState.CONSERVED_OPAQUE:
            assert entry.body_differs is None, entry


@pytest.mark.parametrize("state,kwargs", [
    (ReconciliationState.UNCHANGED, dict(block_id="p1", before="a", after="a")),
    (ReconciliationState.EDITED, dict(block_id="p1", before="a", after="b")),
    (ReconciliationState.DELETED, dict(block_id="p1", before="a")),
    (ReconciliationState.INSERTED, dict(after="new", anchor_position="after")),
])
@pytest.mark.parametrize("value", (True, False))
def test_ac1_forging_the_disclosure_onto_another_state_refuses(state, kwargs, value):
    with pytest.raises(ValueError):
        ReconciliationEntry(state, body_differs=value, **kwargs)


def test_ac1_the_signal_is_READ_and_never_RE_DERIVED():
    """``_diff_segment`` establishes the position **once**, for every branch. A second
    ``_locate`` — here or downstream — would be a second, divergent definition of the
    reconciler's own transforms, which is the defect ``roundtrip._no_change_refusal``'s
    docstring was written to prevent."""
    node = function_ast(SRC / "write" / "reconcile.py", "_diff_segment")
    branches = [
        n for n in ast.walk(node)
        if isinstance(n, ast.If) and getattr(n.test, "id", None) == "is_opaque"
    ]
    assert len(branches) == 1, "the opaque branch is the one under test"
    branch = branches[0]
    assert not [
        c for c in ast.walk(branch)
        if isinstance(c, ast.Call) and getattr(c.func, "id", None) == "_locate"
    ], "the opaque branch must READ the position, not recompute it"

    # ...and the entry is built from that one already-computed value.
    factories = [
        c for c in ast.walk(branch)
        if isinstance(c, ast.Call) and getattr(c.func, "attr", None) == "conserved_opaque"
    ]
    assert factories, "the conserved-opaque entry is built in _diff_segment"
    names = {
        n.id for f in factories for kw in f.keywords for n in ast.walk(kw.value)
        if isinstance(n, ast.Name)
    }
    assert "start" in names, "the disclosure must come from the position already computed"


# --------------------------------------------------------------------------- #
# AC2 — THE WORDING: both readings, neither asserted, no refusal register.      #
# --------------------------------------------------------------------------- #

def test_ac2_the_documented_meaning_states_BOTH_readings():
    text = norm(CONSERVED_BODY_DIFFERS_MEANING)
    assert "EITHER the consumer edited" in text, text
    assert "OR the projection reshaped" in text, text
    assert "asserts neither" in text, text


@pytest.mark.parametrize("asserted", (
    "was edited", "must have", "we know", "evidence that", "proves", "because you edited",
))
def test_ac2_the_documented_meaning_never_reads_as_evidence_of_an_edit(asserted):
    assert asserted not in CONSERVED_BODY_DIFFERS_MEANING.lower()


def test_ac2_the_documented_meaning_is_not_refusal_vocabulary():
    """A success path that speaks in refusal words is the round's F1 defect in the mirror
    direction, so the wording is held clear of the register entirely."""
    text = CONSERVED_BODY_DIFFERS_MEANING.lower()
    assert "refus" not in text, text
    for reason in RECONCILIATION_REFUSAL_REASONS:
        assert reason.value not in text
        assert reason.value.replace("-", " ") not in text


def test_ac2_the_meaning_is_ONE_definition_that_every_documented_spelling_PROJECTS_FROM():
    """Round 4's ``STALE_SHEET`` defect was a documented spelling that did not equal the wire
    value, with a guard that never fired. Both directions are checked here."""
    guide = (SRC / "GUIDE.md").read_text(encoding="utf-8")
    # constant → the shipped guide, and → the shipped capability record.
    assert norm(CONSERVED_BODY_DIFFERS_MEANING) in norm(guide)
    assert CONSERVED_BODY_DIFFERS_MEANING in RECONCILIATION_STATE_MEANINGS[
        ReconciliationState.CONSERVED_OPAQUE.value]
    # ...and it is stated ONCE, not retyped.
    assert norm(guide).count("EITHER the consumer edited") == 1

    # every documented spelling of the key → the wire key, exactly.
    key = "body_differs"
    assert key in {f.name for f in fields(ReconciliationEntry)}
    for label, text in (
        ("GUIDE.md", guide),
        ("CHANGELOG.md", (SRC / "CHANGELOG.md").read_text(encoding="utf-8")),
        ("RELEASE_NOTES.md", (SRC / "RELEASE_NOTES.md").read_text(encoding="utf-8")),
    ):
        # The lookbehind lets the CONSTANT'S OWN NAME through (…_BODY_DIFFERS_MEANING) and
        # catches every other spelling: bodyDiffers, body-differs, body_differed.
        for match in re.findall(
            r"(?<![A-Za-z0-9_])body[ _-]?differ\w*", text, flags=re.IGNORECASE
        ):
            assert match == key, f"{label} spells the key {match!r}, the wire key is {key!r}"


# --------------------------------------------------------------------------- #
# AC3 — SERIALIZATION: trailing, conditional, and backward-compatible.         #
# --------------------------------------------------------------------------- #

#: A plan exactly as it was written BEFORE this change — eight keys, no disclosure.
OLD_SHAPE = {
    "entries": [
        {
            "state": "unchanged",
            "block_id": "p1",
            "before": "one",
            "after": "one",
            "after_markdown": None,
            "anchor_block_id": None,
            "anchor_position": None,
            "opaque_kind": None,
        },
        {
            "state": "conserved-opaque",
            "block_id": "img",
            "before": "![](tok)",
            "after": None,
            "after_markdown": None,
            "anchor_block_id": None,
            "anchor_position": None,
            "opaque_kind": None,
        },
    ],
    "refusals": [],
}


def test_ac3_a_plan_written_before_this_change_round_trips_BYTE_IDENTICALLY():
    rebuilt = ReconciliationPlan.from_dict(OLD_SHAPE)
    assert [e.body_differs for e in rebuilt.entries] == [None, None]
    assert json.dumps(rebuilt.to_dict()) == json.dumps(OLD_SHAPE)


def test_ac3_an_entry_with_nothing_to_disclose_serializes_AS_BEFORE():
    plan = reconcile(
        projection(("p1", "one")), edited(("p1", "one rewritten\n\nbrand new")))
    wire = json.dumps(plan.to_dict())
    assert "body_differs" not in wire, wire


def test_ac3_the_new_key_is_TRAILING_and_round_trips():
    plan = reconcile(SOURCE, edited(("p1", "one"), ("img", "typed over")))
    entry = plan.to_dict()["entries"][-1]
    assert list(entry)[-1] == "body_differs"
    assert entry["body_differs"] is True
    wire = json.loads(json.dumps(plan.to_dict()))
    assert ReconciliationPlan.from_dict(wire) == plan


def test_ac3_the_stability_promise_is_written_WHERE_THE_SHAPE_IS_DEFINED():
    doc = norm(ReconciliationEntry.__doc__)
    assert "body_differs" in doc
    assert "no opinion" in doc, doc
    assert "conserved" in doc


# --------------------------------------------------------------------------- #
# AC4 — ZERO BEHAVIOUR CHANGE TO WHAT COMPILES. Not one request moves.         #
# --------------------------------------------------------------------------- #

def test_ac4_a_disclosed_difference_compiles_to_NOTHING():
    from larkdocio.write.compiler import compile_reconciliation

    plan = reconcile(SOURCE, edited(("p1", "one"), ("img", "typed over")))
    entry, = conserved(plan)
    assert entry.body_differs is True
    assert plan.changes == ()
    assert plan.change_count == 0
    assert plan.touched_block_ids == ()
    assert plan.refusals == ()
    assert compile_reconciliation(plan, SOURCE) == ()


def test_ac4_conserved_opaque_is_still_not_a_change_state():
    from larkdocio.write.reconcile import _CHANGE_STATES

    assert ReconciliationState.CONSERVED_OPAQUE not in _CHANGE_STATES


def test_ac4_the_disclosure_does_not_move_what_a_real_edit_compiles_to():
    from larkdocio.write.compiler import compile_reconciliation

    plan = reconcile(SOURCE, edited(("p1", "one rewritten"), ("img", "typed over")))
    requests = compile_reconciliation(plan, SOURCE)
    assert [r.anchor.block_id for r in requests] == ["p1"]
    assert plan.touched_block_ids == ("p1",)


# --------------------------------------------------------------------------- #
# AC5 — this is a DISCLOSURE: the refusal register gains nothing.              #
# --------------------------------------------------------------------------- #

#: Read off trunk on 2026-08-26, before a line of this change was written. The
#: cleanest available proof that a disclosure is not a refusal: this list is unchanged,
#: element for element, in the shipped registry a consumer reads.
REFUSAL_REASONS_BEFORE = (
    "marker-invented", "marker-duplicated", "marker-absent", "marker-dropped",
    "marker-relocated", "marker-mangled", "marker-orphaned", "marker-order-changed",
    "conserved-block-re-created", "block-type-mutation", "segment-ambiguous",
    "unmarked-content-changed", "undecodable-text", "not-in-dialect",
    "merge-not-expressible", "change-not-expressible",
)


def test_ac5_the_refusal_vocabulary_is_UNCHANGED_element_for_element():
    import larkdocio

    assert tuple(r.value for r in RECONCILIATION_REFUSAL_REASONS) == REFUSAL_REASONS_BEFORE
    shipped = larkdocio.capabilities(full=True)["surfaces"]["docx-write"]["reconciliation"]
    assert tuple(shipped["refusal_reasons"]) == REFUSAL_REASONS_BEFORE


def test_ac5_no_refusal_is_appended_on_the_conserved_path():
    for body in ("![](tok)", "typed over", ""):
        plan = reconcile(SOURCE, edited(("p1", "one"), ("img", body)))
        assert plan.refusals == (), body
        assert plan.ok


# --------------------------------------------------------------------------- #
# AC6 — the CLI disjunction sharpens its conserved arm, and stays a disjunction.
# --------------------------------------------------------------------------- #

def _plan_with(differing=(), conserved_ids=("a", "b")):
    entries = tuple(
        ReconciliationEntry.conserved_opaque(
            block_id, "body", body_differs=block_id in differing)
        for block_id in conserved_ids
    )
    return ReconciliationPlan(entries=entries)


def test_ac6_the_conserved_arm_NAMES_the_blocks_that_read_back_differently():
    from larkdocio import roundtrip

    message = roundtrip._no_change_refusal("/tmp/document.md", _plan_with(differing=("b",)))
    low = message.lower()
    assert "'b'" in message
    # Both arms survive, and the sharpened sentence is itself a disjunction.
    assert "either" in low and " or " in low
    assert low.count("either") >= 2, message
    for asserted in ("swallowed", "absorbed", "must have", "we know", "your edit landed"):
        assert asserted not in low, f"the message ASSERTS what it cannot know: {asserted!r}"
    # The sharpened sentence lives INSIDE the disjunction, never ahead of it.
    assert low.index("read back") > low.index("either")
    assert "read back differently" in low


def test_ac6_with_nothing_disclosed_the_LD560_wording_stands_unchanged():
    """A plan that discloses nothing must read exactly as it did before this change —
    otherwise every consumer's refusal text moved for no information gained."""
    from larkdocio import roundtrip

    silent = roundtrip._no_change_refusal("/tmp/document.md", _plan_with())
    no_opinion = roundtrip._no_change_refusal(
        "/tmp/document.md", _plan_with(differing=()))
    assert silent == no_opinion
    assert "read back differently" not in silent.lower(), silent
    assert "either" in silent.lower()


def test_ac6_the_bit_is_read_off_the_PLAN_and_never_re_derived_downstream():
    from larkdocio import roundtrip

    node = function_ast(SRC / "roundtrip.py", "_no_change_refusal")
    banned = ("_locate", "_units", "_decode", "reconcile", "compose", "project_block_ids")
    for call in ast.walk(node):
        if isinstance(call, ast.Call):
            name = getattr(call.func, "id", None) or getattr(call.func, "attr", None)
            assert name not in banned, f"{name!r} re-derives what the plan already carries"
    source = inspect.getsource(roundtrip._no_change_refusal)
    assert "body_differs" in source or "read_back" in source


def test_ac6_the_docstring_TRANSFORMS_rather_than_being_struck():
    """The reason (re-parsing would be a second, divergent definition) is PRESERVED; only the
    conclusion (that no signal exists) is superseded."""
    from larkdocio import roundtrip

    doc = norm(roundtrip._no_change_refusal.__doc__)
    assert "second, divergent definition of the reconciler's own transforms" in doc, doc
    assert "The plan cannot tell them apart" not in doc, doc
    assert "body_differs" in doc, doc
