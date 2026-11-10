"""LD-424 — ``capabilities()`` represents COMPOUND WORKFLOWS, and the index is guarded
in BOTH directions.

The finding this closes was a **routing** failure, not an absence: reconciliation already
ships whole at ``capabilities()["surfaces"]["docx-write"]["reconciliation"]``, but the
README's prescribed discovery order lands a consumer on ``operations`` — the wire-request
registry — where it is correctly absent. A consumer read the six wire ops, concluded
whole-document reconciliation did not exist, and hand-rolled a destructive clear-and-rewrite.

So the fix is an **index**, never a second description:

* the workflow row is **derived** from the ``Reconciliation`` record (never typed twice), and
  restates none of its contract text — the non-divergence tests below;
* the row **states its own evidence class** — descriptive and guide-pointer-shaped, NOT
  endpoint-derived — and states, in the shipped output, that ``operations`` keeps its
  projection guarantee undiminished;
* and the pointer is guarded **both ways**, in the shape ``test_permissions_registry.py``
  runs: a workflow whose entry point or guide section vanishes reddens, **and** a guide
  section that teaches reconciliation without a workflow row naming it reddens. That second
  direction is the one that would have prevented the finding.
"""
import importlib
import json
import re

import pytest

import larkdocio
from larkdocio.guide import guide, guide_sections

WORKFLOW_ID = "update-a-document-that-already-has-content"
DOCX_WRITE = "docx-write"

#: A guide section "teaches reconciliation" when it shows both halves of the round trip —
#: the diff and the compile. Measured off the shipped document, never hand-listed, so a
#: recipe added or renamed anywhere in the guide is seen by the reverse-direction guard.
_TEACHES_RECONCILIATION = ("reconcile(", "compile_reconciliation(")


@pytest.fixture(scope="module")
def caps():
    return larkdocio.capabilities(full=True)


@pytest.fixture(scope="module")
def workflow(caps):
    return caps["workflows"][WORKFLOW_ID]


def _reconciliation_teaching_slugs():
    """Every level-3 guide section that actually teaches the reconciliation round trip."""
    return {
        row["slug"]
        for row in guide_sections()
        if row["level"] == 3
        and all(marker in guide(section=row["slug"]) for marker in _TEACHES_RECONCILIATION)
    }


# --------------------------------------------------------------------------- #
# AC1 — the section exists, at the level the discovery order lands on.          #
# --------------------------------------------------------------------------- #

def test_ac1_capabilities_carries_a_top_level_workflows_section(caps):
    assert "workflows" in caps, sorted(caps)
    assert WORKFLOW_ID in caps["workflows"], sorted(caps["workflows"])


def test_ac1_the_row_carries_the_four_things_a_consumer_needs(workflow):
    """The task in the consumer's words, what it compiles to (through the named plan
    gate), the module path, and the guide-section pointer."""
    assert "update a document that already has content" in workflow["name"]
    assert workflow["entry_point"] == "larkdocio.write.reconcile"
    assert workflow["compiles_to"] == ["EditRequest", "InsertRequest", "DeleteRequest"]
    # The gate is SAID, because the gate is the safety story.
    assert "plan-gated" in workflow["plan_gate"]
    assert "dry-run-mandatory" in workflow["plan_gate"]
    assert "exactly-one-or-refuse" in workflow["plan_gate"]
    assert workflow["gate_summary"]
    assert workflow["guide_sections"], "no guide-section pointer"


def test_ac1_the_surface_a_consumer_prints_carries_the_pointer_too(caps):
    """The consumer's own reproduce block prints the ``docx-write`` surface. A stub there
    — id, task name, and where the full row is — is what makes the top-level section
    reachable without knowing it exists."""
    stubs = caps["surfaces"][DOCX_WRITE]["workflows"]
    assert [s["id"] for s in stubs] == [WORKFLOW_ID]
    assert "workflows" in stubs[0]["see"] and WORKFLOW_ID in stubs[0]["see"]


# --------------------------------------------------------------------------- #
# AC2 — an INDEX onto ["reconciliation"], not a second description of it.       #
# --------------------------------------------------------------------------- #

def test_ac2_the_row_is_DERIVED_from_the_reconciliation_record(caps, workflow):
    """Not typed a second time: the two fields the row echoes are the record's own."""
    record = caps["surfaces"][DOCX_WRITE]["reconciliation"]
    assert workflow["entry_point"] == record["entry_point"]
    assert workflow["compiles_to"] == record["compiles_to"]


def test_ac2_the_detail_pointer_RESOLVES_to_the_record(caps, workflow):
    """``detail`` is a path a consumer can follow, so it is walked here rather than
    eyeballed — a pointer at a key that does not exist is the failure mode."""
    keys = re.findall(r"\['([^']+)'\]", workflow["detail"])
    node = caps
    for key in keys:
        assert key in node, f"detail pointer {workflow['detail']} breaks at {key!r}"
        node = node[key]
    assert node is caps["surfaces"][DOCX_WRITE]["reconciliation"]


def test_ac2_the_row_RESTATES_none_of_the_records_contract_text(caps, workflow):
    """A second copy of a contract is a future drift. The row may point; it may not
    paraphrase."""
    record = caps["surfaces"][DOCX_WRITE]["reconciliation"]
    blob = json.dumps(workflow)
    restated = [record["contract"], record["compiler_contract"]]
    restated += list(record["state_meanings"].values())
    restated += list(record["absent_dispositions"].values())
    restated += list(record["refusal_reasons"])
    for text in restated:
        assert text not in blob, f"the workflow row restates the record: {text[:60]!r}"


def test_ac2_the_reconciliation_docstring_reason_is_UNTOUCHED():
    """D-24 — the modelling reason for not being an ``Operation`` was always correct; this
    issue answers the ROUTING question and supersedes nothing."""
    from larkdocio.capabilities._models import Reconciliation

    # Whitespace-normalised because Python 3.13+ dedents docstrings; the WORDS are the
    # ruling, and they are pinned verbatim.
    doc = " ".join(Reconciliation.__doc__.split())
    assert (
        "the reconciler compiles none of its own: it is an offline diff that produces a "
        "plan for those families to be built from, so listing it there would say the "
        "surface has a seventh request family it does not have"
    ) in doc


# --------------------------------------------------------------------------- #
# AC3 — the evidence class is STATED, and the guarantee is said to be unweakened.
# --------------------------------------------------------------------------- #

def test_ac3_the_row_states_its_own_evidence_class_in_the_SHIPPED_output(workflow):
    text = workflow["evidence_class"].lower()
    assert "descriptive" in text
    assert "not endpoint-derived" in text


def test_ac3_the_row_states_that_operations_keeps_its_projection_guarantee(workflow):
    text = workflow["operations_guarantee"]
    assert "undiminished" in text.lower()
    assert "one wire request family" in text
    assert "bidirection" in text.lower()


# --------------------------------------------------------------------------- #
# AC4 direction 1 — a vanished entry point or guide section reddens.            #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("field", ["entry_point"])
def test_ac4a_the_entry_point_is_IMPORTABLE(workflow, field):
    assert importlib.import_module(workflow[field]) is not None


def test_ac4a_every_guide_section_pointer_RESOLVES(workflow):
    """Checked against ``guide_sections()`` — the same index ``guide(section=…)`` accepts —
    so a heading rename that moves the derived SLUG reddens here instead of shipping a
    dangling reference."""
    known = {row["slug"] for row in guide_sections()}
    for slug in workflow["guide_sections"]:
        assert slug in known, f"{slug} is not a guide section"
        assert guide(section=slug), f"{slug} resolves to nothing"


# --------------------------------------------------------------------------- #
# AC4 direction 2 — the recipe existing WITHOUT a workflow row reddens.          #
# --------------------------------------------------------------------------- #

def test_ac4b_every_surface_carrying_a_reconciliation_record_is_INDEXED(caps):
    indexed = {
        (w["surface"], w["entry_point"]) for w in caps["workflows"].values()
    }
    for sid, surface in caps["surfaces"].items():
        record = surface.get("reconciliation")
        if record is None:
            continue
        assert (sid, record["entry_point"]) in indexed, (
            f"surface {sid} ships a reconciliation record that no workflow row indexes — "
            "the discovery order would land a consumer on operations and miss it"
        )


def test_ac4b_every_guide_recipe_that_TEACHES_reconciliation_is_named_by_a_workflow(caps):
    """The direction that would have prevented the finding: the guide can ship the recipe
    and the registry stay silent about it. Measured off the document, so a NEW reconcile
    recipe reddens until a workflow row names it."""
    named = {slug for w in caps["workflows"].values() for slug in w["guide_sections"]}
    taught = _reconciliation_teaching_slugs()
    assert taught, "no guide section teaches reconciliation — the markers moved"
    assert taught <= named, {
        "taught but not named by any workflow": sorted(taught - named),
    }


def test_ac4b_the_workflow_names_no_section_that_does_NOT_teach_it(workflow):
    """The mirror: a pointer that survives only because nobody checks what is behind it."""
    assert set(workflow["guide_sections"]) <= _reconciliation_teaching_slugs()


def _unnamed_teaching_slugs(workflows):
    """The reverse-direction check itself, factored out so the test below can prove it
    BITES rather than merely pass."""
    named = {slug for w in workflows.values() for slug in w["guide_sections"]}
    return sorted(_reconciliation_teaching_slugs() - named)


def test_ac4b_the_reverse_guard_BITES(caps):
    """Anti-vacuity, in the shape this repo already runs: drop the recipe from the row and
    the same check must FIND it. A green reverse direction has to mean "every recipe is
    named", not "nothing was looked at"."""
    import copy

    assert _unnamed_teaching_slugs(caps["workflows"]) == []
    doctored = copy.deepcopy(caps["workflows"])
    doctored[WORKFLOW_ID]["guide_sections"] = []
    assert _unnamed_teaching_slugs(doctored), "the reverse guard would not have caught it"


# --------------------------------------------------------------------------- #
# AC6 — the pointer is DERIVED, so LD-422's rename could not dangle it.         #
# --------------------------------------------------------------------------- #

def test_ac6_the_pointer_is_DERIVED_from_the_shipped_document_not_typed(workflow):
    """No section name is written down in ``src/`` (``test_guide_sections.py`` forbids it,
    and this is the positive statement of the same rule): the slugs come off the packaged
    guide, matched by the reconciler's own symbols. The first is the one to read first —
    document order, which is the order the guide puts them in."""
    from larkdocio.capabilities._projections import (
        _DOCX_UPDATE_TEACHING_SYMBOLS,
        _docx_update_guide_sections,
    )

    assert workflow["guide_sections"] == _docx_update_guide_sections()
    assert workflow["guide_sections"][0].startswith("recipe-update-an-existing-document")
    first = guide(section=workflow["guide_sections"][0])
    assert all(symbol in first for symbol in _DOCX_UPDATE_TEACHING_SYMBOLS)


def test_ac6_a_workflow_pointing_at_NOTHING_is_REFUSED_at_construction():
    """Direction 1's bite: if the guide stopped teaching the workflow, the derived list
    empties — and the registry must redden rather than ship a row routing nowhere."""
    from larkdocio.capabilities._models import Workflow

    with pytest.raises(ValueError, match="points at no guide section"):
        Workflow(
            id="x", name="x", surface="docx-write",
            entry_point="larkdocio.write.reconcile", compiles_to=[], plan_gate=[],
            gate_summary="", detail="", guide_sections=[],
            evidence_class="", operations_guarantee="",
        )


# --------------------------------------------------------------------------- #
# Serialization — the registry's own discipline.                                #
# --------------------------------------------------------------------------- #

def test_the_workflows_section_is_json_native(caps):
    assert json.loads(json.dumps(caps["workflows"])) == caps["workflows"]
