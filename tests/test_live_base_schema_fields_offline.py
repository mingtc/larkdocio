"""The always-on offline half of ``test_live_base_schema_fields`` (LD-262).

The live arm runs only with credentials and a network. What it *claims* — that it changes only
Bases it created itself, that it resolves the WRITE pair and never the read one, that it skips
loudly rather than passing silently, that it never sleeps and never deletes — is exactly the
class of claim a credential-less run verifies by not running. So it is verified **here**,
statically, on every plain ``pytest``:

* **disposables only** — this rung's sharpest fence yet. The arm's verbs include *convert a
  column's kind*, which rewrites every value in the column, server-side and permanently; the
  configured Scratch Base holds hand-authored ``Lookup`` / ``Email`` / ``Stage`` columns the API
  cannot recreate. So no configured target may be named in any code path, and the arm must SAY
  which Base it is refusing to touch and why;
* **mutating by construction** — every registered schema op declares that it mutates and the arm
  asserts it before its first call, with the read registry asserted still wholly read-only in
  the same breath;
* **no destructive verb** — the arm deletes nothing of its own; teardown is the harness's sweep;
* **the conversion probe is over a POPULATED cell** — an empty-column conversion is what the
  pack already had, and it is precisely the evidence that does not settle the question;
* **the Formula probe records BOTH outcomes** — a probe that only asserts on success is a probe
  that reports silence as a pass;
* **loud skips** and **a budget**, the shape every Base arm ships.

It imports nothing from the live arm and runs no gate.
"""
import ast
import re
from pathlib import Path

import pytest

from larkdocio.base import field_authoring as fa
from larkdocio.base import ops as base_ops
from larkdocio.base import schema_ops
from larkdocio.base import write_ops

_REPO = Path(__file__).resolve().parent.parent
_TESTS = Path(__file__).resolve().parent
_ARM = _TESTS / "test_live_base_schema_fields.py"

#: Every configured target this repository knows about. None may appear in the arm.
_FORBIDDEN_TARGET_ENV = (
    "LARKDOCIO_SCRATCH_BASE",
    "LARKDOCIO_CANARY_DOC",
    "LARKDOCIO_BLOCKZOO_DOC",
    "LARKDOCIO_SCRATCH_SHEET",
)


@pytest.fixture(scope="module")
def arm_source():
    return _ARM.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def arm_tree(arm_source):
    return ast.parse(arm_source)


def arm_code(source):
    """The arm's source with every string literal and comment removed.

    The scan below asks *"does any CODE PATH read a configured target"*, and this arm's own
    docstring **names** the Scratch Base in prose — deliberately, because a reader has to be
    told why it is off limits. Prose that explains the fence must not trip the fence.
    """
    import io
    import tokenize

    return "\n".join(
        token.string
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type not in (tokenize.STRING, tokenize.COMMENT))


def test_the_arm_exists_and_is_marked_live_write(arm_source):
    assert "pytestmark = pytest.mark.live_write" in arm_source, (
        "an unmarked live write test would run in every plain pytest — and this one CONVERTS "
        "a column's kind, which rewrites every value in it")


def test_the_field_family_is_REGISTERED_and_wholly_MUTATING():
    assert schema_ops.all_mutate() is True
    assert write_ops.all_mutate() is True
    assert base_ops.read_only() is True
    field = [f for f in schema_ops.registered_families() if f.name == "field"]
    assert len(field) == 1
    assert {d.name for d in field[0].ops} == {"create_field", "update_field", "convert_field"}


def test_the_arm_asserts_the_registry_BEFORE_it_calls_anything(arm_source):
    head = arm_source.split("def test_the_live_field_lifecycle")[0]
    assert "schema_ops.all_mutate() is True" in head
    assert "base_ops.read_only() is True" in head


def test_the_arm_NAMES_NO_CONFIGURED_TARGET(arm_source):
    code = arm_code(arm_source)
    for variable in _FORBIDDEN_TARGET_ENV:
        assert variable not in code, (
            f"{variable} names a configured object; every live target on this rung is "
            "self-provisioned")
    assert "os.environ" not in code and "getenv" not in code
    docstring = ast.get_docstring(ast.parse(arm_source)) or ""
    assert "LARKDOCIO_SCRATCH_BASE" in docstring, (
        "the arm must SAY which configured Base it is refusing to touch, and why")
    assert "convert" in docstring.lower(), (
        "the fence's reason on THIS rung is the conversion verb — say it")


def test_EVERY_write_target_comes_from_the_HARNESS(arm_tree):
    body = ast.unparse(arm_tree)
    assert "base_write_harness.disposable_base()" in body
    tokens = [node.value for node in ast.walk(arm_tree)
              if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    suspicious = [text for text in tokens
                  if re.fullmatch(r"[A-Za-z0-9]{27}", text or "")]
    assert not suspicious, f"an app-token-shaped literal in a live arm: {suspicious}"
    fields = [text for text in tokens if re.fullmatch(r"fld[A-Za-z0-9]{7,}", text or "")]
    assert not fields, f"a field-id literal in a live arm: {fields}"


def test_the_arm_CALLS_NO_DESTRUCTIVE_VERB_of_its_own(arm_source):
    for verb in ("delete_app", "delete_table", "delete_field", "batch_delete",
                 "drive.v1.files"):
        assert verb not in arm_source, verb
    assert "close_out()" in arm_source, "teardown is the harness's sweep, not a hand-rolled one"


def test_the_CONVERSION_probe_is_over_a_POPULATED_cell_and_reads_the_value_BACK(arm_source):
    """The whole reason this arm exists. An empty-column conversion is what the pack already
    had; it is the cells that decide whether a pair belongs in the table."""
    assert "create_record(" in arm_source
    assert "cells_before" in arm_source and "cells_after" in arm_source
    assert "the value must survive the conversion" in arm_source


def test_the_FORMULA_probe_records_BOTH_outcomes(arm_source):
    probe = arm_source.split("def test_the_FORMULA_authoring_probe")[1]
    assert '"status": "captured"' in probe and '"status": "refused"' in probe, (
        "either outcome is a pass; a probe that only records success reports silence as one")
    assert "NON_WRITABLE_PAIRS" in probe, (
        "whichever way the probe goes, a Formula CELL stays refused — the two constants are "
        "not blurred by a successful field create")


def test_the_FORMULA_probe_READS_THE_CELLS_and_not_merely_the_column(arm_source):
    """The half ld262 never took. A column that exists is not a column that computes, and
    the read-back that proved existence is exactly what let four dead columns ship."""
    probe = arm_source.split("def test_LD280_the_FORMULA_probe_READS_THE_CELLS")[1]
    assert "search_records(" in probe and "batch_get_records(" in probe, (
        "one read route cannot tell a dead column from a route that omits the key")
    assert "cells_present_per_expression" in probe
    for expression_case in ("ld280-const", "ld280-ref", "ld280-bound"):
        assert expression_case in probe, (
            f"{expression_case} is one of the three expressions the boundary is drawn from")
    assert "all(any(name in row for row in rows) for name in wanted)" in probe, (
        "stopping the poll when ANY formula has arrived is how a slow sibling gets "
        "mistaken for a dead one")


def test_the_FORMULA_probe_BINDS_the_shipped_row_to_what_it_observes(arm_source):
    probe = arm_source.split("def test_LD280_the_FORMULA_probe_READS_THE_CELLS")[1]
    assert "fa.FORMULA_EVALUATION" in probe
    assert "constant_computes" in probe and "reference_computes" in probe
    assert "re-capture" in probe, (
        "the arm must say what to do when the server changes, or it becomes a stale refusal")
    assert "ld280-01-formula-evaluation-probe.json" in arm_source, (
        "the evidence this refusal rests on is committed, not described")


def test_the_shipped_FORMULA_status_is_DERIVED_from_the_measurement():
    assert fa.FORMULA_AUTHORING["status"] == fa.formula_authoring_status(fa.FORMULA_EVALUATION)
    assert fa.FORMULA_EVALUATION["reference_computes"] is False
    with pytest.raises(fa.RefutedFieldAuthoringError):
        fa.build_property("Formula", formula_expression="CurrentValue.[x]*2")


def test_the_arm_uses_NO_SLEEP_and_no_hand_rolled_settle(arm_source):
    assert "time.sleep" not in arm_source and "import time" not in arm_source


def test_the_arm_resolves_the_WRITE_pair_for_both_write_clients(arm_source):
    assert "BaseSchemaClient.from_write_credentials()" in arm_source
    assert "BaseWriteClient.from_write_credentials()" in arm_source
    assert "get_read_credentials" not in arm_source


def test_the_skip_is_LOUD_and_goes_through_the_harnesss_own_reason(arm_source):
    assert "base_write_harness.missing_reason()" in arm_source
    assert "pytest.skip(reason)" in arm_source


def test_the_arm_ASSERTS_a_call_budget_rather_than_intending_one(arm_source):
    assert "schema.api_calls == 1" in arm_source


def test_the_arm_VERIFIES_BY_READ_BACK_and_never_by_code_0(arm_source):
    assert 'read_back["revision_moved"] == 1' in arm_source or (
        'created["revision_moved"] == 1' in arm_source)
    assert "read.list_fields(" in arm_source


def test_the_arm_WRITES_ITS_CAPTURE_so_the_evidence_is_committed(arm_source):
    assert "ld262-01-field-authoring-probes.json" in arm_source
    assert "_record(" in arm_source


def test_the_PAIR_TABLE_the_arm_exercises_is_the_SHIPPED_one():
    assert [(p.from_ui_type, p.to_ui_type) for p in fa.CONVERSION_PAIRS] == [
        ("Text", "Barcode")]


def test_the_gate_is_CLASSIFIED_in_the_registry_with_a_written_reason():
    import gate_registry

    row = gate_registry.REGISTRY["test_live_base_schema_fields.py"]
    assert row.kind is gate_registry.Kind.HAS_COMPANION
    assert len(row.reason) > 120, "a classification without a usable reason is a shrug"
    companion = gate_registry.REGISTRY["test_live_base_schema_fields_offline.py"]
    assert companion.subject == "test_live_base_schema_fields.py"
