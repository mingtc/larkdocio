"""The always-on offline half of ``test_live_base_write_gate``.

The gate runs only with credentials and a network, so everything it *claims about itself* is
verified here, statically, on every plain ``pytest``:

* **disposables only** — every Base it writes comes from ``base_write_harness``, and the file
  names no configured target anywhere. The one configured Base it mentions at all is named in
  a comment about the Base it must never write, which is checked as a mention rather than as a
  target: the assertion below is that no ``os.environ`` / ``getenv`` read of one exists;
* **the three arms are really three arms** — a surgical one, a real-race one, and a
  refused-never-sent one, each present by name;
* **zero-write proofs are STRUCTURAL** — both refusal arms drive ``apply`` with a transport
  that raises on contact, so a refusal that failed to fire errors instead of writing;
* **the credential rider is stated** — on this tenant the pairs alias one app, so the gate
  proves the write path works and proves nothing about scope separation. A gate that quietly
  dropped that sentence would be inviting exactly the over-read the rider exists to prevent;
* **loud skips** — the skip path goes through ``base_write_harness.missing_reason``;
* **the ring knows about it** — ``capabilities()``'s ``base-write`` coverage names this module
  and the transport arm, and both carry the marker they are claimed under.

It imports nothing from the gate and runs no live call.
"""
import ast
from pathlib import Path

import pytest

import base_write_harness
from larkdocio import capabilities
from larkdocio.errors import LarkConfigError

_TESTS = Path(__file__).resolve().parent
_GATE = _TESTS / "test_live_base_write_gate.py"

#: Every configured target this repository knows about. None may be READ by the gate.
_FORBIDDEN_TARGET_ENV = (
    "LARKDOCIO_SCRATCH_BASE",
    "LARKDOCIO_CANARY_DOC",
    "LARKDOCIO_BLOCKZOO_DOC",
    "LARKDOCIO_SCRATCH_SHEET",
)


@pytest.fixture(scope="module")
def gate_source():
    return _GATE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def gate_tree(gate_source):
    return ast.parse(gate_source)


def test_the_gate_exists_and_is_marked_live_write(gate_source):
    assert any(line.startswith("pytestmark = pytest.mark.live_write")
               for line in gate_source.splitlines()), (
        "an unmarked live write gate would run in every plain pytest — and this one creates "
        "real Bases")


def test_the_gate_names_NO_configured_target(gate_source, gate_tree):
    """A mention in prose is fine; a *read* of one is not. Checked on the syntax tree, so the
    docstring that explains which Base this gate must never write cannot trip it."""
    reads = set()
    for node in ast.walk(gate_tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            continue
    for node in ast.walk(gate_tree):
        if isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"}:
            reads.add(node.attr)
    assert not reads, f"the gate reads the environment directly: {sorted(reads)}"
    for name in _FORBIDDEN_TARGET_ENV:
        # It may be discussed; it may not be a string the code hands to anything.
        for node in ast.walk(gate_tree):
            if isinstance(node, ast.Constant) and node.value == name:
                raise AssertionError(f"{name} appears as a code literal in the gate")


def test_every_write_target_comes_from_the_harness(gate_source):
    assert "base_write_harness.disposable_base()" in gate_source
    assert "is_disposable_title" in gate_source


def test_the_provisioner_deletes_in_a_FINALLY():
    """Parsed out of the harness's own syntax tree, so cleanup cannot quietly become
    happy-path-only."""
    harness = ast.parse((_TESTS / "base_write_harness.py").read_text(encoding="utf-8"))
    disposable = next(node for node in ast.walk(harness)
                      if isinstance(node, ast.FunctionDef) and node.name == "disposable_base")
    tries = [node for node in ast.walk(disposable) if isinstance(node, ast.Try)]
    assert tries and any(t.finalbody for t in tries), (
        "disposable_base must delete in a finally")


@pytest.mark.parametrize("arm", ["arm1", "arm2", "arm3a", "arm3b", "arm4"])
def test_all_four_arm_functions_are_present(arm, gate_tree):
    names = [node.name for node in ast.walk(gate_tree)
             if isinstance(node, ast.FunctionDef)]
    assert any(name.startswith(f"test_{arm}") for name in names), (arm, names)


def test_the_date_round_trip_arm_carries_its_REVERTED_FIX_CONTROL(gate_source):
    """A gate that cannot fail on the defect is not proof. The control leg must run the same
    round-trip against a Base created WITHOUT the zone key — the pre-fix create — and assert the
    one-day shift, so the arm's positive half is falsifiable."""
    assert "declare_zone=False" in gate_source and "declare_zone=True" in gate_source, (
        "both halves must run: the declared-zone round-trip and its zone-less control")
    assert "timedelta(days=1)" in gate_source, (
        "the control must assert the ONE-DAY shift, not merely that something differs")
    assert "date_zone_disclosure" in gate_source, (
        "and the control must prove the shift is no longer silent")


def test_the_date_round_trip_arm_reads_NO_HOST_CLOCK(gate_source):
    """Its dates are fixed literals: a gate whose expectation moved with the calendar would be
    green on a wrong renderer half the year."""
    for forbidden in ("datetime.now", "date.today", "time.time", "utcnow"):
        assert forbidden not in gate_source, forbidden


def test_both_refusal_arms_prove_zero_calls_STRUCTURALLY(gate_source):
    """The half a live run cannot verify by passing: that the zero-write claim is enforced by
    a transport that raises rather than by counting after the fact."""
    assert "class RaisesOnContact" in gate_source
    assert gate_source.count("inert_write_client()") >= 2, (
        "both refusal arms must apply against the raise-on-contact transport")
    assert "_InertReadClient" in gate_source, (
        "the read seam must explode too — a fully-refused plan reads no anchor either")


def test_the_surgical_arm_compares_CELL_BY_CELL_not_a_summary(gate_source):
    assert "moved == {(target, TEXT_FIELD)}" in gate_source, (
        "the surgical claim is a per-cell set difference, not a spot check")
    assert "== baseline" in gate_source, "the restore leg must compare against the baseline"


def test_the_race_arm_uses_a_SECOND_client_and_measures_writes_at_the_boundary(gate_source):
    assert "interloper" in gate_source
    assert "write.api_calls == calls_before" in gate_source, (
        "zero writes must be MEASURED at the client boundary, not inferred from an outcome")


def test_the_oracle_arm_carries_its_POSITIVE_CONTROL(gate_source):
    assert "after > before" in gate_source, (
        "the negative reading of the write-effect oracle is only meaningful with the positive "
        "control that a landed write really does advance the anchor")


def test_it_skips_LOUDLY_and_the_reason_NAMES_what_is_missing(gate_source):
    """AC5, and the sharp edge under it: the shipped write-credential getter RAISES rather
    than answering with empties, so a gate that called ``missing_reason()`` bare would ERROR on
    a credential-less machine instead of skipping. The gate catches that and uses the error's
    own text, which already names both variables — so the skip is loud either way."""
    assert "base_write_harness.missing_reason()" in gate_source
    assert "pytest.skip(reason)" in gate_source
    assert "except LarkConfigError" in gate_source, (
        "a credential-less run must SKIP loudly, not error out of the fixture")
    try:
        reason = base_write_harness.missing_reason()
    except LarkConfigError as exc:
        reason = str(exc)
    if reason is not None:  # only non-None when the environment really lacks them
        assert "LARK_WRITE_APP_ID" in reason and "LARK_WRITE_APP_SECRET" in reason, reason


def test_the_credential_ALIASING_RIDER_is_restated_in_the_gate(gate_source):
    """AC4. The pairs alias one app on this tenant, so this gate proves the write path works
    and proves nothing about the read path lacking write scope."""
    doc = ast.get_docstring(ast.parse(gate_source)) or ""
    flat = " ".join(doc.lower().split())
    assert "alias" in flat
    assert "scope separation" in flat or "separate app" in flat, doc[-400:]


def test_the_stage_arm_says_WHY_it_runs_over_a_captured_schema(gate_source):
    """An arm that steps outside the disposables-only shape owes its reason in writing."""
    doc = " ".join((ast.get_docstring(ast.parse(gate_source)) or "").lower().split())
    assert "no field authoring" in doc, doc[-600:]
    assert "schema-write spec" in doc


def test_the_capability_ring_NAMES_this_gate_and_carries_the_marker():
    coverage = capabilities(full=True)["surfaces"]["base-write"]["gate_coverage"]
    modules = {member["module"] for member in coverage["members"]}
    assert "tests/test_live_base_write_gate.py" in modules
    assert "tests/test_live_base_write_arm.py" in modules
    for member in coverage["members"]:
        path = _TESTS.parent / member["module"]
        assert path.exists(), member["module"]
        declared = member.get("marker") or coverage["marker"]
        assert any(line.startswith(f"pytestmark = pytest.mark.{declared}")
                   for line in path.read_text(encoding="utf-8").splitlines()), member["module"]
