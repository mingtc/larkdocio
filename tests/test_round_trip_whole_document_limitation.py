"""The whole-document-only limitation is DOCUMENTED, in both places (LD-236).

Patch/diff-shaped agent output is an explicit non-goal of the round-trip projection: nothing
accepts a patch, and handing the reconciler a fragment describes a document that lost every
block the fragment left out. A non-goal a consumer cannot read is a silent gap, so it is
stated **twice** — in the shipped guide's round-trip recipe (where somebody designing an
integration meets it) and in ``capabilities()``' reconciliation contract (where a machine
does).

**Stated in plain language, deliberately.** The internal shorthand for this decision is
exactly the kind of token ``tests/consumer_text.py``'s dialect guard forbids in
consumer-facing text — and the remedy that guard names is "state the decision and its reason
in plain language". So these tests assert the *statement*, never a decision reference, and the
last test below asserts the absence of one so a later edit cannot re-introduce it.
"""
import re

import pytest

import guide_recipes as gr
from larkdocio import capabilities

#: LD-422 retitled this recipe BY TASK (D-60): a consumer searching "update" / "change" /
#: "edit an existing document" reached nothing, and hand-rolled a destructive rewrite. The
#: mechanism the heading used to name is still taught, in the body, where it belongs.
SLUG = "update-an-existing-document-change-or-edit-many-blocks-at-once-without-re-authoring-it"

#: The claim, as the phrases it must be made of — asserted at content level so wrapping and
#: emphasis are irrelevant and only the words count.
WHOLE_DOCUMENT_PHRASES = (
    "whole document",
    "patch",
    "not supported",
)


def _prose(text):
    return re.sub(r"[\s*`_]+", " ", text).lower()


def test_the_guides_round_trip_recipe_exists_and_is_executable():
    assert SLUG in [spec.slug for spec in gr.RECIPE_SPECS], (
        "the round-trip recipe must be in RECIPE_SPECS, which is what makes it EXECUTE in "
        "the extract-and-run harness rather than merely be prose")
    source = gr.recipe_source(SLUG)
    for call in ("project_block_ids(", "reconcile(", "compile_reconciliation(",
                 "dry_run(", "apply("):
        assert call in source, f"the recipe must show the whole shipped chain; missing {call}"


def test_the_recipes_preamble_states_the_whole_document_only_limitation():
    """The **preamble** is where a consumer reads before pasting, so the limitation has to be
    there and not merely somewhere in the guide."""
    preamble = _prose(gr.recipe_preamble(SLUG))
    missing = [p for p in WHOLE_DOCUMENT_PHRASES if p not in preamble]
    assert not missing, (
        f"the round-trip recipe's preamble does not state the whole-document-only "
        f"limitation; missing {missing}")
    assert "diff" in preamble or "fragment" in preamble, (
        "the limitation must name the shapes it excludes (a patch, a diff, a fragment)")


def test_capabilities_states_the_whole_document_only_limitation_too():
    contract = _prose(
        capabilities(full=True)["surfaces"]["docx-write"]["reconciliation"]["contract"])
    missing = [p for p in WHOLE_DOCUMENT_PHRASES if p not in contract]
    assert not missing, (
        f"capabilities()' reconciliation contract must carry the limitation as well — a "
        f"consumer holding only the wheel reads it there; missing {missing}")


def test_the_recipe_teaches_verification_by_compose_equivalence_not_string_equality():
    source = gr.recipe_source(SLUG)
    assert "compose(" in source and "==" in source, (
        "the verification must be the compose comparator (AC5), not `authored in read_back`")
    assert "assert read_back ==" not in source and "read_back ==" not in source, (
        "string equality against the read-back is the trap the comparator recipe exists to "
        "teach against; the round-trip recipe must not re-introduce it")


@pytest.mark.parametrize("text_id", ["recipe", "reconciliation-contract"])
def test_the_limitation_is_stated_without_an_internal_decision_reference(text_id):
    """The guard that forbids internal dialect in shipped text is NOT to be weakened for this
    sentence — the limitation is a consumer fact and reads as one.

    Scoped to the two texts this issue authors rather than to the whole guide: an A1-style
    cell range (``E9:F9``) is decision-reference-shaped and is a spreadsheet reference, which
    is exactly the kind of judgement the shipped corpus guard already carries and a second,
    cruder copy of it here would get wrong.
    """
    text = (gr.recipe_preamble(SLUG) + gr.recipe_source(SLUG) if text_id == "recipe"
            else capabilities(full=True)["surfaces"]["docx-write"]["reconciliation"]["contract"])
    offenders = re.findall(r"\b[DSTF]\d{1,2}\b", text)
    assert not offenders, (
        f"{text_id} carries an internal decision reference {sorted(set(offenders))} — state "
        f"the decision and its reason in plain language instead")
