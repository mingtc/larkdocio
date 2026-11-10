"""The always-on offline half of ``test_live_base_row_hierarchy`` (LD-296).

The live arm runs only with credentials and a network, so everything it *claims* about its own
posture is exactly the class of claim a credential-less run verifies by not running. It is
verified **here**, statically, on every plain ``pytest``:

* **disposables only** — every write target comes from ``base_write_harness``, no app-token
  literal appears anywhere, and the arm names **no** configured target at all: this rung needs
  no read fixture, so unlike its view sibling it has no fence to write and nothing to excuse;
* **THE EFFECT ASSERTION EXISTS, AND SO DOES ITS CONTROL** — the arm patches
  ``hierarchy_config`` **twice** and requires the read-back to **MOVE**, and it sends the
  bogus-key control on the **same view** and requires the persisted value to stay put. A
  ``code:0`` on this route means nothing without that pairing, so its absence is checked rather
  than trusted;
* **the deliberate defect is built ON THE WIRE** — a fixture cycle proves the traversal
  terminates and says nothing about whether Lark accepts one. The arm writes the closing edge
  live and asserts the typed marker afterwards;
* **the delete is proved by a RE-QUERY, not by the delete's own code:0** — the arm's teardown
  is the harness's own sweep and it asserts zero survivors;
* **the WRITE pair and never the read one** for every mutating client, a **loud** skip, and a
  budget asserted rather than intended;
* **no destructive verb of its own** — nothing here deletes a table, a field or a record.

It imports nothing from the live arm and runs no gate.
"""
import ast
import re
from pathlib import Path

import pytest

from larkdocio.base import hierarchy as hier
from larkdocio.base import schema_ops
from larkdocio.base import schema_ops_views as views

_ARM = Path(__file__).resolve().parent / "test_live_base_row_hierarchy.py"

#: Every configured target this repository knows about. The arm may name **none** of them.
_FORBIDDEN_TARGET_ENV = (
    "LARKDOCIO_CANARY_DOC",
    "LARKDOCIO_BLOCKZOO_DOC",
    "LARKDOCIO_SCRATCH_SHEET",
    "LARKDOCIO_SCRATCH_BASE",
)


@pytest.fixture(scope="module")
def arm_source():
    return _ARM.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def arm_tree(arm_source):
    return ast.parse(arm_source)


def arm_code(source):
    """The arm with its docstrings removed — prose may discuss what code may not do."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(tree))


def test_the_arm_exists_and_is_marked_live_write(arm_source):
    assert _ARM.exists()
    assert "pytestmark = pytest.mark.live_write" in arm_source


def test_the_arm_NAMES_NO_CONFIGURED_TARGET_ANYWHERE(arm_source):
    """The sharpest fence available to this rung, and it is available *because* the rung needs
    no fixture: there is nothing to read, so there is nothing to name."""
    code = arm_code(arm_source)
    for variable in _FORBIDDEN_TARGET_ENV:
        assert variable not in code, variable
    assert not re.search(r"[\"'](?:bascn|Cs|Q8|[A-Za-z0-9]{20,})[A-Za-z0-9]{6,}[\"']", code), (
        "an app-token-shaped literal in the arm would be a write target the harness did not "
        "mint")


def test_every_write_target_comes_from_the_HARNESS(arm_source):
    code = arm_code(arm_source)
    assert "base_write_harness.disposable_base()" in code
    assert "is_disposable_title(title)" in code


def test_the_arm_resolves_the_WRITE_pair_for_every_mutating_client(arm_source):
    code = arm_code(arm_source)
    for factory in ("BaseSchemaClient.from_write_credentials()",
                    "BaseWriteClient.from_write_credentials()"):
        assert factory in code, factory
    assert "BaseSchemaClient.from_read_credentials" not in code
    assert "BaseWriteClient.from_read_credentials" not in code
    assert "BaseReadClient.from_read_credentials()" in code, (
        "the READ pair is what reads, and it is a different pair on purpose")


def test_the_arm_SKIPS_LOUDLY_rather_than_passing_without_credentials(arm_source):
    code = arm_code(arm_source)
    assert "base_write_harness.missing_reason()" in code
    assert "pytest.skip(reason)" in code


def test_THE_EFFECT_ASSERTION_and_ITS_CONTROL_are_both_present_on_the_SAME_VIEW(arm_source):
    """The pairing this whole route depends on. Either half alone proves nothing."""
    code = arm_code(arm_source)
    assert code.count("set_view_hierarchy") >= 3, (
        "the effect assertion needs TWO patches plus the restore; one is a code:0")
    assert "moved != first" in code, "the read-back must be asserted to have MOVED"
    assert "larkdocio_not_a_real_key" in code, "the R12 control must be sent"
    assert "after_control == link.field_id" in code, (
        "the control must be asserted to have changed NOTHING")


def test_the_LOCAL_refusal_is_exercised_and_costs_nothing(arm_source):
    code = arm_code(arm_source)
    assert "pytest.raises(BaseSchemaRefusal)" in code
    assert "HIERARCHY_FIELD_MUST_BE_A_LINK" in code, (
        "the refusal must be checked against the SERVER's own words, not a paraphrase")


def test_the_DELIBERATE_DEFECT_is_written_LIVE_and_typed_afterwards(arm_source):
    code = arm_code(arm_source)
    assert "PLACEMENT_CYCLE" in code
    assert "cyclic.cycles" in code
    assert "update_record" in code, "the closing edge is WRITTEN, not fixtured"


def test_the_DELETE_is_proved_by_the_SWEEP_not_by_a_success_code(arm_source):
    code = arm_code(arm_source)
    assert "base_write_harness.close_out()" in code
    assert "left == []" in code


def test_the_arm_carries_NO_DESTRUCTIVE_VERB_of_its_own(arm_source):
    code = arm_code(arm_source)
    for verb in ("delete_field", "delete_table", "delete_record", "delete_view",
                 "batch_delete"):
        assert verb not in code, verb


def test_the_arm_WRITES_ITS_OWN_CAPTURE_under_the_captures_directory(arm_source):
    code = arm_code(arm_source)
    assert "ld296-01-row-hierarchy-live.json" in code
    assert "_verdict" in code and "_probe" in code
    # LD-620: the write goes through the sink (redirected out of the working tree, loudly);
    # the pinned property is that the arm still writes its capture, not how it spells it.
    assert "capture_sink.write_capture(CAPTURE," in code


def test_the_view_family_is_WHOLLY_MUTATING_and_the_read_registry_still_is_not():
    from larkdocio.base import ops as base_ops

    assert schema_ops.all_mutate() is True
    assert base_ops.read_only() is True
    assert all(d.mutates is True for d in views.SCHEMA_OP_FAMILY.ops)


def test_the_SHIPPED_hierarchy_module_reaches_no_transport_which_is_why_the_arm_can():
    """The arm exercises the tree read against live data; that read is still pure, which is
    what makes 'the accessor costs no call' a claim the live arm does not have to prove."""
    source = Path(hier.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("lark_oapi"), node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("lark_oapi"), alias.name
