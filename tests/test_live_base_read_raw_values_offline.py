"""The always-on offline half of ``test_live_base_read_raw_values`` (LD-293).

The live arm runs only with credentials and a network. What it *claims* — that it is
read-only, that it targets the disposable Scratch Base and nothing else, that it writes
nothing and provisions nothing, and that it skips loudly rather than passing silently — is
exactly the class of claim a credential-less run verifies by not running. So it is verified
**here**, statically, on every plain ``pytest``:

* **read-only by construction** — every registered op declares ``mutates: False``, and the arm
  asserts that *before* its first call;
* **no write credential, no write verb, and no provisioning** anywhere in the arm — retention
  is a decision about a payload already received, so an arm that created or uploaded anything
  would be proving a different surface;
* **the right target** — the arm reads ``LARKDOCIO_SCRATCH_BASE`` and never the canary doc,
  the scratch sheet, the block zoo, or a hard-coded token;
* **loud skips** — the arm's skip path goes through ``canary_support.base_missing_reason``,
  which names the missing variable;
* **the no-write proof is really made** — the arm re-reads ``table.revision`` and compares;
* **the ring knows about it** — the surface's own gate coverage names this module, which is
  what stops a live arm from existing outside the registry that prices live coverage.

This mirrors the established companion pattern; it imports nothing from the live arm and runs
no gate.
"""
import ast
from pathlib import Path

import pytest

from larkdocio import capabilities
from larkdocio.base import ops as base_ops

_TESTS = Path(__file__).resolve().parent
_ARM = _TESTS / "test_live_base_read_raw_values.py"


@pytest.fixture(scope="module")
def arm_source():
    return _ARM.read_text(encoding="utf-8")


def test_the_arm_exists_and_is_marked_live(arm_source):
    assert "pytestmark = pytest.mark.live" in arm_source, (
        "the arm must be deselected by default; an unmarked live test runs in every plain "
        "pytest and turns a credential-less clone red")


def test_the_registry_the_arm_leans_on_really_is_read_only():
    assert base_ops.read_only()
    assert all(descriptor.mutates is False for descriptor in base_ops.OPS)


def test_the_arm_asserts_read_only_BEFORE_it_calls_anything(arm_source):
    tree = ast.parse(arm_source)
    names = [node.name for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]
    first = "test_the_registry_declares_the_whole_arm_read_only_BEFORE_it_calls_anything"
    assert first in names
    assert names.index(first) == 0, (
        "the read-only assertion must come first in file order, because that is the order "
        "pytest runs them in and the point is to fail before touching the Base")


def test_the_arm_names_NO_write_credential_and_NO_write_verb(arm_source):
    for forbidden in ("LARK_WRITE_APP", "from_write_credentials", "BaseWriteClient",
                      "BaseSchemaClient", "apply(", "dry_run("):
        assert forbidden not in arm_source, f"the read arm names {forbidden!r}"


def test_the_arm_PROVISIONS_nothing_and_UPLOADS_nothing(arm_source):
    """Retention keeps a payload the read already received. An arm that had to create a Base,
    a table, a record or a file to prove it would be proving something else."""
    for forbidden in ("base_write_harness", "create_app", "create_table", "batch_create",
                      "upload", "media"):
        assert forbidden not in arm_source, f"the read arm reaches for {forbidden!r}"


def test_the_arm_targets_the_SCRATCH_BASE_and_nothing_else(arm_source):
    assert "canary_support.scratch_base_url()" in arm_source
    for forbidden in ("LARKDOCIO_CANARY_DOC", "LARKDOCIO_BLOCKZOO_DOC",
                      "LARKDOCIO_SCRATCH_SHEET", "LARKDOCIO_WRITE_SCRATCH_DOC"):
        assert forbidden not in arm_source, f"the arm names {forbidden!r}"


def test_the_arm_skips_LOUDLY_when_the_grant_or_the_url_is_absent(arm_source):
    assert "canary_support.base_missing_reason()" in arm_source
    assert "pytest.skip(reason)" in arm_source


def test_the_arm_really_makes_its_no_write_proof(arm_source):
    assert "table.revision" in arm_source
    assert "this arm is READ-ONLY" in arm_source


def test_the_base_read_ring_NAMES_this_arm():
    coverage = capabilities(full=True)["surfaces"]["base-read"]["gate_coverage"]
    modules = {member["module"] for member in coverage["members"]}
    assert "tests/test_live_base_read_raw_values.py" in modules, (
        "a live arm outside its surface's own gate coverage is coverage nobody can price")
    assert coverage["marker"] == "live" and coverage["command"] == "pytest -m live"
