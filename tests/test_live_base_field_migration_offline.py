"""The always-on offline half of ``test_live_base_field_migration`` (LD-291).

The live arm runs only with credentials and a network. What it *claims* — that it touches only
Bases it created itself, that it skips loudly rather than passing silently, that it never
sleeps, and that its forced-defect arm really forces a defect rather than asserting one — is
exactly the class of claim a credential-less run verifies by not running. So it is verified
**here**, statically, on every plain ``pytest``:

* **disposables only.** This arm's subject is *deleting a populated column*. The configured
  Scratch Base holds hand-authored ``Lookup`` / ``Email`` / ``Stage`` columns the API cannot
  recreate, so no configured target may appear in any code path — and the arm must SAY which
  Base it is refusing to touch and why;
* **the forced defect is REAL** — the mismatch arm wraps the shipped write client and changes
  the values it writes, rather than asserting a refusal a fake produced;
* **both halves of the fence are asserted** — the arm must check that the source column is
  still listed AND that its values are unchanged, because "the column is there" alone would
  pass over an emptied one;
* **no sleep, loud skip**, the shape every Base arm ships.

It imports nothing from the live arm and runs no gate.
"""
import ast
from pathlib import Path

import pytest

from larkdocio.base import field_migration as fm

_TESTS = Path(__file__).resolve().parent
_ARM = _TESTS / "test_live_base_field_migration.py"

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


def arm_code(source):
    """The arm's source with every string literal and comment removed.

    The scan below asks *"does any CODE PATH read a configured target"*, and the arm's own
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
        "an unmarked live write test would run in every plain pytest — and this one DELETES a "
        "populated column")


def test_no_configured_target_is_reachable_from_any_code_path(arm_source):
    code = arm_code(arm_source)
    for name in _FORBIDDEN_TARGET_ENV:
        assert name not in code, (
            f"{name} is read in a code path of an arm whose verbs include deleting a populated "
            "column")
    assert "getenv" not in code and "environ" not in code, (
        "this arm resolves its targets through the harness's own create, never through the "
        "environment")


def test_every_target_comes_from_the_harnesss_OWN_create(arm_source):
    tree = ast.parse(arm_source)
    withs = [node for node in ast.walk(tree) if isinstance(node, ast.withitem)]
    provisioned = [item for item in withs
                   if isinstance(item.context_expr, ast.Call)
                   and getattr(item.context_expr.func, "attr", "") == "disposable_base"]
    assert len(provisioned) == 3, (
        "each of the three arms must open its own disposable Base — a shared one would make "
        "the forced-defect arm's assertions about a table the other arm had already changed")
    assert "base_write_harness" in arm_source


def test_the_arm_SKIPS_LOUDLY_and_never_sleeps(arm_source):
    assert "pytest.skip(reason)" in arm_source
    assert "missing_reason()" in arm_source
    code = arm_code(arm_source)
    assert "sleep" not in code, (
        "a live arm that sleeps is paying for a settle it has not measured")


def test_the_forced_defect_arm_really_CHANGES_the_values_it_writes(arm_source):
    """A refusal is only evidence if something real produced it."""
    tree = ast.parse(arm_source)
    mangler = [node for node in ast.walk(tree)
               if isinstance(node, ast.ClassDef) and node.name == "_MangledCopy"]
    assert len(mangler) == 1, "the forced-defect wrapper must be in the arm itself"
    body = ast.dump(mangler[0])
    assert "batch_update_records" in body, (
        "the wrapper must intercept the COPY, which is the only step whose defect the "
        "verification is supposed to catch")
    assert "getattr" in body, (
        "everything except the one intercepted call must reach the SHIPPED client")


def test_the_mismatch_arm_asserts_BOTH_halves_of_the_fence(arm_source):
    arm = arm_source.split("def test_a_copy_that_did_NOT_round_trip")[1]
    arm = arm.split("\ndef test_")[0]
    assert "SOURCE_COLUMN in names" in arm, "the source column must still be LISTED"
    assert "source_cells_before" in arm and "must be intact" in arm, (
        "a listed column that had been emptied would pass a presence check alone — the arm "
        "must compare the VALUES")
    assert "not-attempted" in arm, "the delete and the rename must never have been attempted"


def test_the_arm_records_a_COMMITTED_capture(arm_source):
    assert "ld291-01-guided-migration.json" in arm_source
    assert "_record(" in arm_source


def test_the_migration_module_ships_the_three_statements_the_arm_rests_on():
    """The arm asserts behaviour; these are the statements that behaviour is described by, and
    they are checked here so a credential-less run still holds the library to them."""
    assert "not a conversion" in fm.MIGRATION_IS_NOT_A_CONVERSION.lower()
    assert "cannot be atomic" in fm.MIGRATION_IS_NOT_ATOMIC.lower()
    assert "not a value" in fm.EMPTY_CELLS_ARE_SKIPPED.lower()
    assert fm.MIGRATION_STEPS[2] == fm.STEP_VERIFY_COPY, (
        "the verification must sit BETWEEN the copy and the delete — that ordering is the "
        "whole fence")
    assert fm.MIGRATION_STEPS.index(fm.STEP_DELETE_SOURCE) > fm.MIGRATION_STEPS.index(
        fm.STEP_VERIFY_COPY)
