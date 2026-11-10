"""The always-on offline half of ``test_live_drive_access_gate`` (LD-432 AC11).

The gate runs only with write credentials and a network. What it claims **about itself** is
exactly the class of claim a credential-less run "verifies" by not running, so it is verified
here, on every plain ``pytest``:

* **Disposables only (D-12), by text.** The gate names no standing fixture anywhere — not the
  read canary, not either scratch surface, not either zoo — and hard-codes no document token.
  **Including LD-420's living fixture**, which is a standing artifact this issue does not own:
  the gate must not address it, delete it, or reuse it as a target.
* **The subject is self-created and torn down** in a ``finally``, with gone-ness proved by an
  **independent re-query** rather than by the delete's own return code — and the teardown
  iterates a **ledger appended to as each create returns**, so a second create added later
  cannot escape it.
* **THE READ-BACK IS WHAT IS ASSERTED.** The gate must assert ``stored`` and the member rows a
  read returned; a gate that asserted only the absence of an exception would pass against the
  measured swallow this whole surface is shaped around. Structural, so weakening it reddens.
* **It never names the ops it does not ship** — no ``transfer``, no ``opendepartmentid`` —
  because a live gate is also a place a refused capability could be quietly tried. (LD-456
  **transformed** the object-type half of this claim rather than dropping it: the gate now
  addresses ``sheets`` and ``base`` **because it measures them**, and the check below holds it
  to the measured set instead of to ``docx`` alone.)
* **The second arm's disposables are self-created too** — a spreadsheet deleted in the same
  ``finally``, and a Base through the ledgered disposable-Base harness, with ``close_out``
  asserted empty. Checked structurally here, since a credential-less run cannot see it.
* **It skips LOUDLY**, and the registry assertion is ordered **before** the round trip, which is
  the order pytest runs them in and the whole point of asserting it at all.
"""
import ast
import re
from pathlib import Path

import pytest

from larkdocio.drive import ops as drive_ops

_TESTS = Path(__file__).resolve().parent
_GATE = _TESTS / "test_live_drive_access_gate.py"

#: Every standing fixture the gate must never address. Named here rather than in the gate, so
#: the list itself is not a string the gate carries.
STANDING_FIXTURES = (
    "LARKDOCIO_CANARY_DOC", "LARKDOCIO_WRITE_SCRATCH_DOC", "LARKDOCIO_SCRATCH_BASE",
    "LARKDOCIO_SCRATCH_SHEET", "LARKDOCIO_BLOCK_ZOO", "LARKDOCIO_COMMENT_ZOO",
)

#: LD-420 left ONE document alive on purpose, for a human's copy/paste attempt. It is not this
#: gate's subject and not this issue's chore: addressing it here would either destroy a standing
#: artifact or make the gate's result depend on one.
LIVING_FIXTURE_TOKEN = "Example96b1f1037377879d8dd5"

#: The level this tenant's disposables folder confers on the gate's grantee at birth (LD-577).
#: Named here, not pinned in the gate: an arm whose ONLY member write asks for this level has
#: its read-back satisfied by inheritance, so it cannot prove the write stored.
GRANT_LEVEL_INHERITED_HERE = "full_access"


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
    assert "pytest.mark.conformance" in gate_source, (
        "the live rings are conformance-tier, overlaid on the ring marker")


def test_the_gate_NAMES_NO_STANDING_FIXTURE(gate_body):
    for standing in STANDING_FIXTURES:
        assert standing not in gate_body, f"the gate names a standing fixture: {standing}"


def test_the_gate_NEVER_ADDRESSES_LD420s_LIVING_FIXTURE(gate_source):
    assert LIVING_FIXTURE_TOKEN not in gate_source, (
        "the living fixture is left alive on purpose for a human's copy/paste attempt — this "
        "gate must neither target it nor delete it")


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


def test_the_SUBJECT_is_SELF_CREATED_and_torn_down(gate_body):
    assert gate_body.count("create_document(") == 1, "the subject must be self-created"
    assert "finally:" in gate_body, "a create with no finally is a create with no teardown"
    assert "delete_document(" in gate_body


def test_NO_create_document_ESCAPES_the_TEARDOWN(gate_source):
    """Every create must be acquired INSIDE a ``try`` whose ``finally`` trashes — a create that
    precedes the ``try`` is an orphan waiting for the next failure (LD-415's lesson)."""
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
    tree = ast.parse(gate_source)
    tries = _trashing_tries(tree)
    assert tries, "no try/finally trashes at all"
    ledgers, iterated = set(), set()
    for try_node in tries:
        for stmt in try_node.body:
            for node in ast.walk(stmt):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "append"
                        and isinstance(node.func.value, ast.Name)):
                    ledgers.add(node.func.value.id)
        for stmt in try_node.finalbody:
            for node in ast.walk(stmt):
                if (isinstance(node, ast.For) and isinstance(node.iter, ast.Name)
                        and _calls_named(node, "delete_document")):
                    iterated.add(node.iter.id)
    assert ledgers & iterated, (
        f"the finally trashes {sorted(iterated)} but the try ledgers {sorted(ledgers)} — the "
        "teardown must iterate the ledger every create appends to")


def test_GONE_NESS_is_proved_by_an_INDEPENDENT_RE_QUERY(gate_body):
    assert "wc.get_document(token)" in gate_body
    assert "file_absent_after_delete" in gate_body


def test_the_gate_ASSERTS_THE_READ_BACK_and_not_merely_the_absence_of_an_exception(gate_body):
    """The claim this whole surface is shaped around: ``code 0`` is not storage. A gate that
    called the ops and asserted nothing about what a READ returned would pass against the
    measured swallow — so the assertions are structural here.

    **TRANSFORMED by LD-577, not weakened.** The read-back rule is untouched; what moved is the
    *baseline* the read-back is judged against. The birth-emptiness half (``members_at_birth ==
    []``) was a fact about a document filed nowhere, and this gate files into a disposables
    folder, so the object inherits container rows at birth — the library's own
    ``MEMBER_LIST_AT_BIRTH`` says so. The arms therefore assert the **delta their own grant and
    revoke cause** — and, per leg (LD-577 fix round): the revoke and nobody-else legs are
    strengthened, the ADD-route grant read-back is **inheritance-confounded** here, and the
    stored-ness proof is carried by the level change every arm now makes.
    """
    assert 'row["granted"][3] is True' in gate_body, (
        "the grant's STORED flag — the read-back's own verdict — must be asserted")
    assert 'row["members_at_birth"]' in gate_body, (
        "birth membership must still be READ and recorded — the delta has no baseline without it")
    assert 'row["members_after_grant"]' in gate_body, (
        "the post-grant member read is the other end of the delta")
    assert 'row["members_after_revoke"]' in gate_body
    assert 'row["copy_stored"] ==' in gate_body, (
        "each copy-lever key must be asserted against what the settings READ returned")
    assert 'row["owner_at_birth"]' in gate_body, (
        "the owner leg is the half of the member read a member list cannot show")


def test_the_gate_ASSERTS_A_DELTA_and_never_BIRTH_EMPTINESS_again(gate_body, gate_source):
    """LD-577. The old premise — *a freshly minted object has no members* — is FALSE in this
    tenant, and a gate that stops at its own premise proves nothing about the surface. Both arms
    must judge the **delta** they themselves cause: the grant adds exactly its own row to
    whatever birth membership the object came with, and the revoke returns the list to that same
    birth membership. Structural, so a regression to the emptiness form reddens here."""
    for dead in ('row["members_at_birth"] == []', 'arm["members_at_birth"] == []',
                 'row["members_after_revoke"] == []', 'arm["members_after_revoke"] == []'):
        assert dead not in gate_body, (
            f"the falsified birth-emptiness premise is back as {dead!r} — the arm would fail on "
            "its own premise before exercising a single grant")
    for helper in ("def _delta(", "def _perm_of(", "def _others("):
        assert helper in gate_source, (
            f"the delta verdict must be computed in one named place: {helper!r}")
    for prefix in ("row", "arm"):
        # The grantee reads at the level this run asked for, and NOBODY ELSE moved.
        assert f'_perm_of({prefix}["members_after_grant"], grantee) ==' in gate_body, (
            f"the {prefix} arm must judge its grant on the grantee's own READ-BACK row")
        assert f'_others({prefix}["members_after_grant"], grantee) == _others(' in gate_body, (
            f"the {prefix} arm must assert its grant moved nobody it was not asked about")
        # The revoke takes back exactly its own grant: the grantee holds no row, everyone
        # else is untouched, and the lifecycle added nothing birth did not have.
        assert f'_perm_of({prefix}["members_after_revoke"], grantee) is None' in gate_body, (
            "a revoke that leaves the grantee a row is a tombstone by another name")
        assert f'_others({prefix}["members_after_revoke"], grantee) == _others(' in gate_body
        assert (f'_delta({prefix}["members_at_birth"], {prefix}["members_after_revoke"]) == []'
                in gate_body), (
            "the whole lifecycle must add no row against the object's own birth membership")


def test_the_gates_MOVED_PREMISE_carries_its_reason_and_its_measurement(gate_source):
    """Supersession (CLAUDE.md § House rules): the conclusion moved, the reason is preserved.
    The gate must say **why** the emptiness premise was written and **why** it moved, dated, and
    must point at the library's own measured statement rather than restating it."""
    assert "LD-577" in gate_source, "the transformation must name the issue that made it"
    assert "MEMBER_LIST_AT_BIRTH" in gate_source, (
        "the birth-membership truth is authored in the library, not re-derived in a gate")
    assert re.search(r"perm_type='container'|perm_type=\"container\"|container", gate_source), (
        "the reason the birth list is non-empty here — inherited folder rows — must be stated")
    assert re.search(r"20\d\d-\d\d-\d\d", gate_source), (
        "a measurement with no date is not a measurement (staleness doctrine)")


@pytest.fixture(scope="module")
def mirror_source():
    """This mirror's own text. It carries the same strength claim the gate does, so a claim
    re-cut in one place and left standing in the other is exactly the drift to catch."""
    return Path(__file__).resolve().read_text(encoding="utf-8")


def test_EVERY_KIND_carries_a_member_write_NO_INHERITED_ROW_can_satisfy(gate_source, gate_body):
    """LD-577 fix round. The delta form alone is **not** enough to prove a grant landed: this
    tenant's disposables folder already carries the grantee at ``full_access``, so on the ADD
    route ``members_after_grant == members_at_birth`` and a *swallowed* member write satisfies
    the grant assertion from the birth state. The unambiguous leg is a **level change** —
    ``update_access`` asking for a level nothing inherited reads back as — and **every** arm must
    carry one, including the sheet, which had none. Structural, so an arm added later cannot
    default its way out of the proof."""
    assert "def _type_arm(access, token, *, obj_type, update_perm):" in gate_source, (
        "the level-change leg must be a REQUIRED keyword of the type arm — a default is how an "
        "arm silently ships with only the inheritance-confounded grant")
    assert "with_update" not in gate_source, (
        "the optional-update form is what left the sheet arm with no unambiguous member write")
    calls = re.findall(r"(?<!def )_type_arm\(\s*access[^)]*\)", gate_body)
    assert len(calls) == 2, f"expected the sheet and Base call sites, found {calls!r}"
    for call in calls:
        assert "update_perm=" in call, (
            f"a type arm is called with no level change to read back: {call!r}")
    table = re.search(r"UPDATE_PERM = \{([^}]*)\}", gate_source)
    assert table, "the per-kind update levels must be one named table, not scattered literals"
    asked = re.findall(r"[\"'](\w+)[\"']\s*:\s*[\"'](\w+)[\"']", table.group(1))
    assert len(asked) == 2, f"a kind has no level of its own: {asked!r}"
    for kind, perm in asked:
        assert perm != GRANT_LEVEL_INHERITED_HERE, (
            f"the {kind} arm asks {perm!r} — the very level birth already inherits, so its "
            "read-back proves nothing (LD-577)")
    assert 'arm["moved"] == (arm["update_asked"], True)' in gate_body, (
        "each kind's level change must be judged against the level THAT arm asked for")


def test_the_gates_STRENGTH_CLAIM_is_cut_PER_LEG_and_not_stated_as_a_blanket(gate_source,
                                                                            mirror_source):
    """LD-577 fix round. The transformed premise claimed the delta form was *strictly stronger
    than the old form* — false as measured for the GRANT leg, whose read-back the folder's
    inherited ``full_access`` row satisfies with or without a stored write. The claim must be
    re-cut leg by leg: which legs the delta form strengthens, and which stay
    inheritance-confounded."""
    # Composed, never written out: a literal blanket claim in this file would match itself.
    for stem in ("stronger", "more"):
        blanket = f"strictly {stem} than the old form"
        assert blanket not in gate_source, f"the blanket claim survives in the gate: {blanket!r}"
        assert blanket not in mirror_source, (
            f"the blanket claim survives in the mirror: {blanket!r}")
    for source, where in ((gate_source, "gate"), (mirror_source, "mirror")):
        assert "inheritance-confounded" in source, (
            f"the {where} must NAME the leg the inherited rows confound, not imply it")
    assert "update_access" in gate_source.split('"""')[1], (
        "the premise section must say which leg carries the unambiguous member write")


def test_the_gate_PINS_NO_TENANT_MEMBER_ID(gate_source):
    """maintainer-ruled with LD-577: record the birth membership, never pin it. A hard-coded ``ou_`` /
    ``cli_`` / ``oc_`` id would make the gate fail the next time the tenant's folder sharing
    changes — the same brittleness the emptiness premise had, one layer down."""
    pinned = re.findall(r"['\"](?:ou_|cli_|oc_|on_)[0-9a-zA-Z]{6,}['\"]", gate_source)
    assert not pinned, f"the gate pins tenant member ids: {pinned}"


def test_the_gate_NEVER_TRIES_WHAT_THE_SURFACE_DOES_NOT_SHIP(gate_body):
    for forbidden in ("transfer_owner", "opendepartmentid", "remove_old_owner",
                      "lock_switch=", "external_access_entity="):
        assert forbidden not in gate_body, (
            f"the gate reaches for {forbidden!r} — an unshipped capability is not something a "
            "live gate gets to try on the way past")


def test_the_gate_ADDRESSES_ONLY_TYPES_THE_SURFACE_MEASURES(gate_body):
    """TRANSFORMED, not deleted (LD-456). The rule is unchanged — a live gate may not reach
    for a capability the surface does not ship — but the object types are no longer *docx
    alone*: the gate's second arm is what MADE ``sheet`` and ``bitable`` measured. So the check
    now reads the shipped alias table and forbids everything outside it."""
    from larkdocio.drive.access import OBJECT_TYPE_ALIASES

    asked = set(re.findall(r"obj_type=[\"']([^\"']+)[\"']", gate_body))
    assert asked, "the second arm must address its types explicitly, not by the default"
    unmeasured = asked - set(OBJECT_TYPE_ALIASES)
    assert not unmeasured, (
        f"the gate addresses object types the surface has not measured: {sorted(unmeasured)}")


def test_the_SECOND_ARMS_disposables_are_SELF_CREATED_and_swept(gate_body):
    assert "disposable_base(" in gate_body, (
        "a Base's measured delete lag needs the ledgered harness, not a bare finally")
    assert "close_out()" in gate_body and 'row["orphans"] == []' in gate_body, (
        "zero orphans must be ASSERTED from the sweep, never assumed")
    assert gate_body.count("create_spreadsheet(") == 1
    assert "delete_spreadsheet(" in gate_body
    assert 'row["sheet_deleted"] is True' in gate_body, (
        "the spreadsheet's teardown must be asserted, not merely attempted")


def test_the_SECOND_ARM_asserts_the_READ_BACK_and_reproduces_the_REPORTED_FAILURE(gate_body):
    """The same standard the docx arm is held to, plus the control that makes the arm an
    answer to the bug rather than only a new feature's demo."""
    assert 'arm["granted"][3] is True' in gate_body
    assert 'arm["members_at_birth"]' in gate_body
    assert 'arm["members_after_revoke"]' in gate_body
    assert '"1063001" in arm["as_docx"]' in gate_body, (
        "the reported consumer failure must be reproduced as this arm's own control")
    assert '"obj_type" in arm["as_docx"]' in gate_body, (
        "and the library's voice on that bare code is the half the defect was about")


def test_the_registry_claims_the_gate_leans_on_hold_OFFLINE_TOO():
    """The gate's first assertion, made here too — so it is checked on every run and not only
    on the runs that have credentials."""
    assert drive_ops.op("list_members").mutates is False
    for name in ("grant_access", "update_access", "revoke_access", "set_copy_permissions"):
        assert drive_ops.op(name).mutates is True, name
    assert drive_ops.read_only(drive_ops.ENUMERATION_OPS) is True


def test_the_gate_asserts_the_registry_claim_BEFORE_it_calls_anything(gate_source):
    tree = ast.parse(gate_source)
    names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    first = "test_the_registry_declares_the_ACCESS_OPS_MUTATING_before_anything_is_called"
    second = "test_the_grant_lifecycle_round_trips_on_a_disposable_this_run_created"
    assert first in names and second in names
    assert names.index(first) < names.index(second), (
        "the registry assertion must come first in file order, because that is the order "
        "pytest runs them in and the point is to fail before touching a real tenant")


def test_the_gate_SKIPS_LOUDLY_rather_than_passing_without_credentials(gate_source):
    assert "live_write_missing_reason()" in gate_source
    assert "pytest.skip(reason)" in gate_source
