"""The always-on offline half of ``test_live_base_schema_gate``.

The gate runs only with credentials and a network, so everything it *claims about itself* is
verified here, statically, on every plain ``pytest``:

* **disposables only** — every Base it changes comes from ``base_write_harness``, and the one
  configured Base it names at all is named in the fence that refuses it, never as a target;
* **the five arms are really five arms** — surgical, cross-table loss, filter-with-control, a
  zero-call refusal, and a column kit landing with its table — each present by name;
* **the zero-call proof is STRUCTURAL** — the refusal arm drives the shipped path with a schema
  client whose transport raises on contact, so a refusal that failed to fire errors instead of
  authoring a column;
* **the surgical claim is a SET DIFFERENCE**, over columns and over cells, rather than a spot
  check — and the restore leg compares against the baseline the arm captured first;
* **the preview is read BEFORE the delete**, in source order, because a preview asserted after
  the fact proves nothing about what a caller could have known;
* **the swallow control rides the library's own RAW core, in tests/** — nothing in
  ``src/larkdocio`` can build a ``group_info`` body, and a probe that needed a hole cut in the
  typed client would have been the defect rather than the evidence;
* **the credential rider is stated** — on this tenant the pairs alias one app, so the gate
  proves the write path works and proves nothing about scope separation;
* **loud skips** — the skip path goes through ``base_write_harness.missing_reason``;
* **the ring knows about it** — ``capabilities()``'s ``base-schema-write`` coverage names this
  module, and it carries the marker it is claimed under.

It imports nothing from the gate and runs no live call.
"""
import ast
from pathlib import Path

import pytest

import base_write_harness
from larkdocio import capabilities

_TESTS = Path(__file__).resolve().parent
_GATE = _TESTS / "test_live_base_schema_gate.py"
_MODULE = "tests/test_live_base_schema_gate.py"


@pytest.fixture(scope="module")
def gate_source():
    return _GATE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def gate_tree(gate_source):
    return ast.parse(gate_source)


def test_the_gate_exists_and_is_marked_live_write(gate_source):
    assert any(line.startswith("pytestmark = pytest.mark.live_write")
               for line in gate_source.splitlines()), (
        "an unmarked schema gate would run in every plain pytest — and this one creates real "
        "Bases and deletes real columns")


def test_every_write_target_comes_from_the_harness(gate_source):
    assert "base_write_harness.disposable_base()" in gate_source
    assert "is_disposable_title" in gate_source
    assert gate_source.count("disposable_base()") >= 5, (
        "every live arm provisions its own Base rather than sharing one")


def test_the_ONLY_mention_of_the_configured_base_is_the_FENCE_that_refuses_it(gate_tree):
    """It may be read in order to assert the gate is not writing it. It may not be handed to
    anything: the read must live in the fence test and nowhere else."""
    users = [node.name for node in ast.walk(gate_tree)
             if isinstance(node, ast.FunctionDef)
             and "LARKDOCIO_SCRATCH_BASE" in ast.dump(node)]
    assert users == ["test_the_gate_NEVER_TOUCHES_THE_CONFIGURED_SCRATCH_BASE"], users


def test_the_provisioner_deletes_in_a_FINALLY():
    """Parsed out of the harness's own syntax tree, so cleanup cannot quietly become
    happy-path-only."""
    harness = ast.parse((_TESTS / "base_write_harness.py").read_text(encoding="utf-8"))
    disposable = next(node for node in ast.walk(harness)
                      if isinstance(node, ast.FunctionDef) and node.name == "disposable_base")
    tries = [node for node in ast.walk(disposable) if isinstance(node, ast.Try)]
    assert tries and any(t.finalbody for t in tries), (
        "disposable_base must delete in a finally")


@pytest.mark.parametrize("arm", ["arm1", "arm2", "arm3", "arm4", "arm5"])
def test_all_five_arms_are_present_by_name(arm, gate_tree):
    names = [node.name for node in ast.walk(gate_tree) if isinstance(node, ast.FunctionDef)]
    assert any(name.startswith(f"test_{arm}") for name in names), (arm, names)


def test_the_refusal_arm_proves_zero_calls_STRUCTURALLY(gate_source):
    """The half a live run cannot verify by passing: the zero-call claim is enforced by a
    transport that raises, not by counting after the fact."""
    assert "class RaisesOnContact" in gate_source
    assert "inert_schema_client()" in gate_source
    assert "client=client" in gate_source, (
        "the refusal must be driven through the SHIPPED apply seam, with the inert client")


def test_the_refusal_arm_covers_ALL_FOUR_unauthorable_kinds(gate_source):
    from larkdocio.base import field_vocabulary as fv

    for kind in ("Lookup", "Stage", "Email", "Button"):
        assert f'"{kind}"' in gate_source, kind
        if kind != "Button":
            assert kind in fv.UNAUTHORABLE_GUIDANCE, (
                f"{kind} must still be outside the shipped allow-list for this arm to mean "
                "anything")


def test_the_refusal_arm_carries_a_LIVE_POSITIVE_CONTROL(gate_source):
    """Without it, zero calls could equally mean the path is broken."""
    assert "LIVE_POSITIVE_CONTROL" in gate_source
    assert "table_revision" in gate_source


def test_the_surgical_arm_compares_COLUMNS_AND_CELLS_as_set_differences(gate_source):
    assert "set(columns_after) - set(columns_before)" in gate_source, (
        "the added-column claim is a set difference, not a length check")
    assert "unchanged == columns_before" in gate_source
    assert "cells_of(read, app_token, table_id) == cells_before" in gate_source, (
        "every existing cell of every existing row must be compared, not sampled")
    assert "columns_of(read, app_token, table_id) == columns_before" in gate_source, (
        "the restore leg must compare against the baseline the arm captured first")


def test_the_cross_table_arm_reads_the_PREVIEW_BEFORE_it_applies(gate_source):
    """Source order is the assertion. A preview read after the delete proves nothing about what
    a caller could have known beforehand."""
    body = gate_source.split("def test_arm2_", 1)[1].split("\ndef ", 1)[0]
    preview_at = body.index("loss_preview")
    apply_at = body.index("consent=consent_to_destroy")
    assert preview_at < apply_at, "the preview must be read before the delete is applied"
    assert "previewed_tables == [main_id, target_id]" in body, (
        "the preview must name BOTH tables by identity")
    assert "predicted_mirror not in columns_of(read, app_token, target_id)" in body, (
        "the mirror's disappearance must be asserted in the OTHER table — that is the claim")


def test_the_cross_table_arm_mints_CONSENT_FROM_ITS_OWN_PLAN(gate_source):
    assert "consent=consent_to_destroy(plan)" in gate_source
    assert gate_source.count("consent_to_destroy") >= 2, (
        "both destructive legs — the surgical restore and the cross-table delete — go through "
        "the fence")


def test_the_swallow_control_rides_the_RAW_CORE_and_lives_in_TESTS(gate_source):
    assert "class _RawProbe(CredentialedRawHttpClient)" in gate_source
    assert "group_info" in gate_source
    from larkdocio.base import view_plan

    assert "group_info" not in (Path(view_plan.__file__).read_text(encoding="utf-8")), (
        "nothing in the shipped view surface may build a group_info body — the probe exists "
        "BECAUSE the typed dialect refuses it")


def test_the_control_is_on_the_SAME_view_as_the_positive_result(gate_source):
    body = gate_source.split("def test_arm3_", 1)[1].split("\ndef ", 1)[0]
    assert body.count("disposable_base()") == 1, (
        "one Base, one view: a control on a different view is a difference between two views, "
        "not a control")
    assert "echoes(wanted, None) is False" in body, (
        "the typed not-persisted disposition comes from the SHIPPED classifier, not from this "
        "test's own opinion")
    assert "normalize_persisted" in body, (
        "the filter comparison must be semantic, with its normalisation named")


def test_the_probe_reaches_ONLY_ITS_THREE_DECLARED_ROUTES(gate_tree):
    """The raw core is a hole in the dialect boundary if it can reach anything else.

    **Exactly two routes, each with its own reason.** The swallow control reaches a **view**
    (``property.group_info`` has no parameter anywhere in the shipped surface, which is the
    feature). Arm 5's same-window control reaches ``…/tables/{t}/fields`` — the one route whose
    *availability* the arm has to observe rather than assume, and which it therefore must not
    reach through the typed client, because a typed create would be a capability claim rather
    than a probe — and ``…/tables/batch_create``, whose *swallow* of an inline column kit is the
    measurement that earns the shipped refusal, and which therefore cannot be measured through a
    client that refuses it. Anything else is a hole: this list is closed, and widening it is a
    decision.
    """
    paths = [node.value for node in ast.walk(gate_tree)
             if isinstance(node, ast.Constant) and isinstance(node.value, str)
             and node.value.startswith("/open-apis")]
    assert paths, "the probe's route must be a literal so it can be checked"
    for path in paths:
        assert path.startswith("/open-apis/bitable/v1/apps/"), path
    # Every route the probe FORMATS and calls is one of the two, and both are present.
    formatted = [ast.dump(node) for node in ast.walk(gate_tree)
                 if isinstance(node, ast.JoinedStr)
                 and "/open-apis/bitable" in ast.dump(node)]
    assert formatted, "the probe's paths are built as literal f-strings"
    for dumped in formatted:
        assert any(route in dumped
                   for route in ("/views/", "/fields", "/tables/batch_create")), dumped[:200]
    assert any("/views/" in dumped for dumped in formatted), "the swallow control's route"
    assert any("/fields" in dumped for dumped in formatted), (
        "arm 5's same-window control on the /fields write family")
    assert any("/tables/batch_create" in dumped for dumped in formatted), (
        "arm 5's batch-swallow refutation")


def test_the_kit_arm_PROVES_ITSELF_ON_THE_FIELD_LIST_and_never_on_code_0(gate_source):
    """Arm 5's whole claim is a read, not an acceptance. A version of it that asserted only on
    the apply outcome would pass on a create whose array the server silently ignored."""
    body = gate_source.split("def test_arm5_", 1)[1].split("\ndef ", 1)[0]
    assert "read.list_fields(" in body, "the created table's OWN columns are the evidence"
    assert "field.type == asked[\"field_type\"]" in body, (
        "each column is checked on its TYPE, not merely on its presence")
    assert "ui_type" in body and "_property_blob(field)" in body, (
        "ui_type and property are part of 'the column landed'")
    assert "is_primary" in body, (
        "is_primary is what answers whether the kit REPLACED the primary or added beside it")


def test_the_kit_arms_FIELDS_CONTROL_is_RECORDED_and_NEVER_ASSERTED(gate_source):
    """The arm must pass whether the ``/fields`` write family is up or down: it exists to route
    AROUND that family, so an assertion on the control's code would make a platform state a
    precondition of a capability that has none."""
    body = gate_source.split("def test_arm5_", 1)[1].split("\ndef ", 1)[0]
    control = body.split("fields_write_control", 1)[1].split("# ---", 1)[0]
    assert "assert" not in control, (
        "the control's code is written into the capture, never asserted on")
    assert "control.call(" in body, "the control rides the raw core, not the typed client"


def test_the_gate_SKIPS_LOUDLY_through_the_harnesss_own_reason(gate_source):
    assert "base_write_harness.missing_reason()" in gate_source
    assert "pytest.skip(reason)" in gate_source
    assert callable(base_write_harness.missing_reason)


def test_the_CREDENTIAL_ALIASING_RIDER_is_stated_in_the_gates_own_docstring(gate_source):
    """A gate that quietly dropped this sentence would invite exactly the over-read the rider
    exists to prevent: on this tenant the pairs alias ONE app."""
    doc = ast.get_docstring(ast.parse(gate_source)) or ""
    lowered = doc.lower()
    for phrase in ("alias one", "write path works", "scope separation"):
        assert phrase in lowered, phrase


def test_NOTHING_IN_THE_GATE_UPLOADS_MEDIA(gate_source):
    """An uploaded attachment token has no purge verb at all, so a live arm that minted one
    would leave residue nothing can remove."""
    for forbidden in ("upload_all", "bitable_file", "upload_media"):
        assert forbidden not in gate_source.replace(
            "``bitable_file``", ""), forbidden


def test_the_RING_names_this_module_and_it_carries_the_claimed_marker():
    coverage = capabilities(full=True)["surfaces"]["base-schema-write"]["gate_coverage"]
    modules = [member["module"] for member in coverage["members"]]
    assert _MODULE in modules, modules
    member = next(m for m in coverage["members"] if m["module"] == _MODULE)
    assert member["proves_contracts"], "a gate member that proves nothing is a row, not a gate"
    assert (member.get("marker") or coverage["marker"]) == "live_write"


def test_the_TEARDOWN_SWEEP_is_the_last_test_in_the_module(gate_tree):
    names = [node.name for node in gate_tree.body if isinstance(node, ast.FunctionDef)
             and node.name.startswith("test_")]
    assert names[-1] == "test_the_teardown_LEDGER_is_swept_and_every_survivor_is_NAMED", names
