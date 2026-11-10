"""The always-on offline half of ``test_live_drive_versions_gate`` (LD-409 AC14).

The gate runs only with write credentials and a network. What it claims **about itself** is
exactly the class of claim a credential-less run "verifies" by not running, so it is verified
here, on every plain ``pytest``:

* **Disposables only (D-12), by text.** The gate names no standing fixture anywhere — not the
  read canary, not either scratch surface, not either zoo — and hard-codes no document token.
* **Both subjects are self-created, and both are torn down** in a ``finally``, with gone-ness
  proved by an **independent re-query** rather than by the delete's own return code (the one
  mistake that leaves an orphan behind a green run).
* **The teardown COVERS every create — structurally** (LD-415). ``"finally:" in source`` was the
  original check and it stayed green while the first ``create_document`` sat *outside* the
  ``try``, so a failing second create orphaned the first document. The presence check is kept
  (it is still necessary) and is now backed by an **AST** check that no ``create_document`` call
  lies outside a ``try`` body whose ``finally`` trashes, and that the teardown iterates a
  **ledger appended to as each create returns** rather than a fixed pair of names.
* **The read-only claim it leans on is the RE-SCOPED one** (D-24): the R1 enumeration legs are
  still read-only, the registry as a whole no longer is, and **exactly one** op mutates — the
  assertion that stops a second write op arriving on this path unnoticed.
* **It skips LOUDLY**, and the discipline assertion is ordered **before** the round trip, which
  is the order pytest runs them in and the whole point of asserting it at all.
"""
import ast
from pathlib import Path

import pytest

from larkdocio.drive import ops as drive_ops

_TESTS = Path(__file__).resolve().parent
_GATE = _TESTS / "test_live_drive_versions_gate.py"

#: Every standing fixture the gate must never address. Named here rather than in the gate, so
#: the list itself is not a string the gate carries.
STANDING_FIXTURES = (
    "LARKDOCIO_CANARY_DOC", "LARKDOCIO_WRITE_SCRATCH_DOC", "LARKDOCIO_SCRATCH_BASE",
    "LARKDOCIO_SCRATCH_SHEET", "LARKDOCIO_BLOCK_ZOO", "LARKDOCIO_COMMENT_ZOO",
)


@pytest.fixture(scope="module")
def gate_source():
    return _GATE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def gate_body(gate_source):
    """The gate's source WITHOUT its module docstring — the docstring names the fixtures the
    gate deliberately avoids, and a sweep that counted those would refuse the disclosure."""
    return gate_source.split('"""', 2)[-1]


def test_the_gate_is_MARKED_live_write_and_deselected_by_default(gate_source):
    assert "pytestmark = pytest.mark.live_write" in gate_source, (
        "an unmarked live gate runs in every plain pytest and turns a credential-less clone red")


def test_the_gate_NAMES_NO_STANDING_FIXTURE(gate_body):
    for standing in STANDING_FIXTURES:
        assert standing not in gate_body, f"the gate names a standing fixture: {standing}"


def test_the_gate_HARD_CODES_no_document_token(gate_source):
    """A 22-27 character token-shaped literal in a gate is a real document somewhere."""
    tree = ast.parse(gate_source)
    suspects = [
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and 20 <= len(node.value) <= 30 and node.value.isalnum()
    ]
    assert not suspects, f"the gate carries token-shaped literals: {suspects}"


def _calls_named(node, attr):
    """True if ``node``'s subtree calls something spelled ``attr`` (``x.attr(…)`` or ``attr(…)``)."""
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Call):
            continue
        func = inner.func
        if isinstance(func, ast.Attribute) and func.attr == attr:
            return True
        if isinstance(func, ast.Name) and func.id == attr:
            return True
    return False


def _calls_to(tree, attr):
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr == attr]


def _trashing_tries(tree):
    """Every ``Try`` whose ``finally`` trashes — the only regions a create may be acquired in."""
    return [n for n in ast.walk(tree) if isinstance(n, ast.Try)
            and any(_calls_named(stmt, "delete_document") for stmt in n.finalbody)]


def test_BOTH_subjects_are_SELF_CREATED_and_BOTH_are_torn_down(gate_body):
    assert gate_body.count("create_document(") == 2, "both disposables must be self-created"
    assert "finally:" in gate_body, "a create with no finally is a create with no teardown"
    assert "delete_document(" in gate_body
    # LD-415: the three checks above are NECESSARY but NOT SUFFICIENT — every one of them stayed
    # green while the FIRST create sat outside the try, so a failed second create left a real
    # document behind. Coverage (not presence) is asserted structurally below; the presence
    # checks are kept because they are what makes the structural message legible.


def test_NO_create_document_ESCAPES_the_TEARDOWN(gate_source):
    """LD-415: every create must be acquired INSIDE a ``try`` whose ``finally`` trashes.

    A create that precedes the ``try`` is an orphan waiting for the next create to fail — which
    is exactly what happened (``folder locked``, 2026-08-11). Structural, so moving a create back
    above the ``try`` reddens this file.
    """
    tree = ast.parse(gate_source)
    protected = set()
    for try_node in _trashing_tries(tree):
        for stmt in try_node.body:
            protected.update(id(n) for n in ast.walk(stmt))
    escaped = [c.lineno for c in _calls_to(tree, "create_document") if id(c) not in protected]
    assert not escaped, (
        f"create_document at line(s) {escaped} lies outside the try whose finally trashes — "
        "a failure after it leaves a real document in the tenant")


def test_the_TEARDOWN_TRASHES_A_LEDGER_appended_to_as_each_create_returns(gate_source):
    """The ``finally`` must iterate what the ``try`` *recorded*, not a fixed pair of names.

    A hard-coded ``(doc_id, empty_id)`` teardown is right only for exactly today's two creates,
    and silently drops the third one somebody adds later.
    """
    tree = ast.parse(gate_source)
    tries = _trashing_tries(tree)
    assert tries, "no try/finally trashes at all"
    ledgers = set()
    for try_node in tries:
        for stmt in try_node.body:
            for node in ast.walk(stmt):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "append"
                        and isinstance(node.func.value, ast.Name)):
                    ledgers.add(node.func.value.id)
    assert ledgers, "nothing is ledgered inside the try — the teardown cannot be create-driven"
    iterated = set()
    for try_node in tries:
        for stmt in try_node.finalbody:
            for node in ast.walk(stmt):
                if (isinstance(node, ast.For) and isinstance(node.iter, ast.Name)
                        and _calls_named(node, "delete_document")):
                    iterated.add(node.iter.id)
    assert ledgers & iterated, (
        f"the finally trashes {sorted(iterated)} but the try ledgers {sorted(ledgers)} — the "
        "teardown must iterate the ledger every create appends to")


def test_GONE_NESS_is_proved_by_an_INDEPENDENT_RE_QUERY(gate_body):
    """The delete's own return code is not evidence: a delete that answered 0 and left the file
    is exactly the orphan this check exists to catch."""
    assert "wc.get_document(token)" in gate_body
    assert "file_absent_after_delete" in gate_body


def test_the_registry_the_gate_leans_on_is_the_RE_SCOPED_claim():
    """The gate's first assertion, made here too — so it is checked on every run and not only
    on the runs that have credentials."""
    assert drive_ops.read_only() is False
    assert drive_ops.read_only(drive_ops.ENUMERATION_OPS) is True
    assert "create_version" in {d.name for d in drive_ops.mutating_ops()}
    assert drive_ops.op("create_version").mutates is True


def test_the_gate_asserts_the_registry_claim_BEFORE_it_calls_anything(gate_source):
    tree = ast.parse(gate_source)
    names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    first = "test_the_registry_declares_EXACTLY_ONE_MUTATING_OP_before_anything_is_called"
    second = "test_the_named_version_round_trips_on_a_disposable_this_run_created"
    assert first in names and second in names
    assert names.index(first) < names.index(second), (
        "the registry assertion must come first in file order, because that is the order "
        "pytest runs them in and the point is to fail before touching a real tenant")


def test_the_gate_SKIPS_LOUDLY_rather_than_passing_without_credentials(gate_source):
    assert "live_write_missing_reason()" in gate_source
    assert "pytest.skip(reason)" in gate_source
