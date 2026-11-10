"""The always-on offline half of ``test_live_contacts_resolve_colleague``.

The live arm runs only with credentials, a network and a real user address in the
environment. Everything it *claims about itself* — that it is **read-only**, that it touches no
document / sheet / Base, that it requests and widens **no scope**, that it **skips loudly**
rather than passing silently when the credentials or the address are absent, and above all that
it **commits no third party's identifier** — is exactly the class of claim a credential-less run
"verifies" by not running. So it is verified **here**, statically, on every plain ``pytest``.

The BEHAVIOUR the arm exercises is already pinned offline against the committed probe bytes by
``test_contacts_resolve_colleague.py``; this file is about the arm's POSTURE, plus its
:mod:`gate_registry` row.

It imports nothing from the live gate and runs no gate.
"""
import ast
import re
from pathlib import Path

import gate_registry as gr
import pytest

from guard_kit import REPO_ROOT

_GATE_NAME = "test_live_contacts_resolve_colleague.py"
_GATE = REPO_ROOT / "tests" / _GATE_NAME

#: The owner's address is in the committed capture record already; the synthetic control can
#: never be a real address (``.invalid`` is reserved by RFC 2606). Nothing else may appear.
_PERMITTED_ADDRESSES = {"example.user@example.com", "nobody.does.not.exist@example.invalid"}

#: The one endpoint the arm is allowed to reach, and the families it may not.
_PERMITTED_ENDPOINT = "batch_get_id"
_FORBIDDEN_CALLS = ("write_client", "WriteClient", "from_write_credentials", "apply(",
                    "dry_run(", "create_", "delete_", "update_", "trash", "/im/")


@pytest.fixture(scope="module")
def gate_source():
    return _GATE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def gate_tree(gate_source):
    return ast.parse(gate_source)


def test_the_gate_file_exists_and_is_marked_live(gate_source):
    assert "pytestmark = pytest.mark.live" in gate_source, (
        "the arm must be credential-gated by the live marker, or a plain pytest run would try "
        "to reach Lark")


def test_NO_THIRD_PARTY_ADDRESS_IS_COMMITTED_IN_THE_GATE(gate_source):
    """The redaction rule (the slice-2 precedent), enforced from OUTSIDE the gate.

    The gate carries this assertion about itself too, but that copy only runs with credentials
    — which is precisely the run a contributor without them never makes. This is the copy that
    runs always.
    """
    addresses = set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", gate_source))
    assert addresses <= _PERMITTED_ADDRESSES, sorted(addresses - _PERMITTED_ADDRESSES)


def test_the_second_user_address_is_read_from_the_ENVIRONMENT_not_a_file(gate_source):
    assert "LD348_COLLEAGUE_EMAIL" in gate_source
    assert "os.environ.get" in gate_source
    for reader in ("read_text(", "open(CAPTURES", "json.load"):
        assert reader not in gate_source.replace("open(__file__", ""), (
            f"the arm reads {reader!r} — a real address must never be lifted out of a "
            "committed file into a live test")


def test_the_gate_IS_READ_ONLY_and_touches_no_write_surface(gate_source):
    body = gate_source[gate_source.index('"""', gate_source.index('"""') + 3) + 3:]
    offenders = [token for token in _FORBIDDEN_CALLS if token in body]
    assert not offenders, (
        f"the arm reaches a write or chat surface: {offenders}. It is a READ arm — nothing is "
        "written to Lark, no document, sheet or Base is touched, and the declined /im/ "
        "purchase stays declined")


def test_the_gate_reaches_ONLY_the_batch_get_id_route(gate_source):
    assert _PERMITTED_ENDPOINT in gate_source
    assert "resolve_user" not in gate_source, "the name route is a different arm"
    assert "search_employees" not in gate_source


def test_every_absent_precondition_SKIPS_LOUDLY_rather_than_passing(gate_source, gate_tree):
    """Two skips, each naming the exact variable to set. A silent pass is the failure mode."""
    skips = [node for node in ast.walk(gate_tree)
             if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and node.func.attr == "skip"]
    assert len(skips) == 2, f"expected two loud skips (credentials, user address); {skips}"
    assert "LARK_READ_APP_ID" in gate_source
    assert "LD348_COLLEAGUE_EMAIL" in gate_source
    assert "write credential" in gate_source, (
        "the credential skip should say the arm needs no WRITE pair, so nobody supplies one")


def test_the_three_AC8_arms_are_all_present(gate_tree):
    names = {node.name for node in ast.walk(gate_tree) if isinstance(node, ast.FunctionDef)}
    for arm in ("test_ac8a_the_owners_email_resolves_to_the_owners_open_id",
                "test_ac8b_a_second_users_email_resolves_to_a_DIFFERENT_open_id",
                "test_ac8c_the_fake_email_control_is_UNRESOLVED_with_the_user_id_key_OMITTED"):
        assert arm in names, arm


def test_the_control_arm_checks_the_OMISSION_on_the_raw_body(gate_source):
    """The whole honesty core rests on the ``user_id`` key being ABSENT. The live arm must read
    that off the client's own body, not through the reader that already interprets it."""
    assert "client.batch_get_id(emails=[NOWHERE_EMAIL])" in gate_source
    assert 'getattr(rows[0], "user_id", None) is None' in gate_source


def test_the_arm_asserts_the_shipped_disclosures_VERBATIM(gate_source):
    for constant in ("UNRESOLVED_IS_UNDIFFERENTIATED", "MEASURED_REACH"):
        assert f"{constant} in answer.refusal.detail" in gate_source, (
            f"{constant} must be asserted by identity, so a paraphrase in the refusal reddens")


def test_the_gate_row_exists_and_names_THIS_file():
    row = gr.REGISTRY[_GATE_NAME]
    assert row.kind is gr.Kind.HAS_COMPANION
    assert row.companion == Path(__file__).name
    assert gr.REGISTRY[Path(__file__).name].subject == _GATE_NAME
