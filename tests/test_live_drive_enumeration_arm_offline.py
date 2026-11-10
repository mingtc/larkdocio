"""The always-on offline half of ``test_live_drive_enumeration_arm`` (LD-324 AC11).

The live arm runs only with credentials and a network. What it *claims* — that it is read-only,
that its subject is the **bot's own** root folder rather than any human's real tree, that it
never recurses, and that it skips loudly rather than passing silently — is exactly the class of
claim a credential-less run verifies by not running. So it is verified **here**, statically, on
every plain ``pytest``:

* **read-only by construction** — every registered op declares ``mutates: False``, and the arm
  asserts that *before* its first call, so a future write op cannot reach a real tenant by way
  of this file;
* **no write credential and no write verb** anywhere in the arm or in the package it drives;
* **the right subject** — the arm discovers the caller's own root folder live and names no
  folder token, no scratch doc as a subject, and no maintainer-designated tree (the Drive spec § D7);
* **no recursion** — the arm lists one page of one folder; a live walk of an unknown-depth real
  tree is not what a two-call budget buys;
* **loud skips** — the arm's skip path names the missing credential variables, so an absent
  grant never reads as a pass.

It imports nothing from the live arm and runs no gate.
"""
import ast
from pathlib import Path

import pytest

from larkdocio.drive import ops as drive_ops

_TESTS = Path(__file__).resolve().parent
_ARM = _TESTS / "test_live_drive_enumeration_arm.py"


@pytest.fixture(scope="module")
def arm_source():
    return _ARM.read_text(encoding="utf-8")


def test_the_arm_exists_and_is_marked_live(arm_source):
    assert "pytestmark = pytest.mark.live" in arm_source, (
        "the arm must be deselected by default; an unmarked live test runs in every plain "
        "pytest and turns a credential-less clone red")


def test_the_registry_the_arm_leans_on_really_is_read_only():
    """The arm's first assertion, made here too — so the claim is checked on every run and not
    only on the runs that have credentials."""
    # TRANSFORMED, not deleted (LD-409, D-24) — see the arm's own comment: the claim is
    # asserted at the scope the arm has, and the mutating set is pinned so a second write op
    # on this path reddens rather than passing silently.
    assert drive_ops.read_only(drive_ops.ENUMERATION_OPS)
    assert all(descriptor.mutates is False for descriptor in drive_ops.ENUMERATION_OPS)
    assert not [d for d in drive_ops.ENUMERATION_OPS if d.mutates], (
        "a mutating op joined the ENUMERATION set — this arm runs against a real tenant "
        "and must not be the thing that discovers that")
    # LD-432 widened the registry's verb set (the access family declares PUT, DELETE and
    # PATCH), so the claim is asserted at the scope this arm actually has: the ENUMERATION's
    # own declared verbs. Nothing this arm calls can be anything but a GET or the one
    # declared query POST.
    assert sorted({d.http_method for d in drive_ops.ENUMERATION_OPS}) == ["GET", "POST"]


def test_the_arm_asserts_read_only_BEFORE_it_calls_anything(arm_source):
    tree = ast.parse(arm_source)
    names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    first = "test_the_registry_declares_the_whole_arm_read_only_BEFORE_it_calls_anything"
    second = "test_the_live_arm_reaches_the_bots_own_root_folder_and_lists_it"
    assert first in names and second in names
    assert names.index(first) < names.index(second), (
        "the read-only assertion must come first in file order, because that is the order "
        "pytest runs them in and the point is to fail before touching a real tenant")


def test_the_arm_names_NO_write_credential_and_NO_write_verb(arm_source):
    for forbidden in ("LARK_WRITE_APP", "get_write_credentials", "write_client",
                      "upload", "create_folder", "shortcut"):
        assert forbidden not in arm_source, f"the arm names {forbidden!r}"


def test_the_arms_SUBJECT_is_the_callers_own_root_and_no_hard_coded_token(arm_source):
    """The Drive spec § D7 — the bot's own root folder, discovered live. A hard-coded folder token, or
    a dependency on a maintainer-supplied tree, is exactly what this arm must not grow."""
    assert "root_folder_token()" in arm_source
    assert "LARKDOCIO_SCRATCH_BASE" not in arm_source
    assert "FolderRo" not in arm_source, "a real maintainer folder token is hard-coded in the arm"
    for suspicious in ("fldr", "nodl"):
        assert f'"{suspicious}' not in arm_source, (
            f"the arm hard-codes a {suspicious}… token instead of discovering the root")


def test_the_arm_DOES_NOT_RECURSE(arm_source):
    assert "walk_folder" not in arm_source, (
        "a live walk of a real tree of unknown depth is not a two-call arm")
    assert "list_folder_children_to_exhaustion" not in arm_source


def test_the_arm_SKIPS_LOUDLY_and_the_reason_names_what_is_missing(monkeypatch):
    import test_live_drive_enumeration_arm as arm

    monkeypatch.setattr(arm.canary_support, "read_creds_available", lambda: False)
    reason = arm.missing_reason()
    assert reason and "LARK_READ_APP_ID" in reason
    assert "Drive" in reason

    monkeypatch.setattr(arm.canary_support, "read_creds_available", lambda: True)
    assert arm.missing_reason() is None


def test_the_domain_hint_degrades_rather_than_failing(monkeypatch):
    """The canary doc's URL is used only as a tenant-domain hint. A malformed or absent hint
    must fall back, never raise — the arm's subject is not the canary doc."""
    import test_live_drive_enumeration_arm as arm

    monkeypatch.setattr(arm.canary_support, "canary_doc_url", lambda: None)
    assert arm.tenant_domain() == "larksuite.com"
    monkeypatch.setattr(arm.canary_support, "canary_doc_url", lambda: "not-a-url")
    assert arm.tenant_domain() == "larksuite.com"


def test_the_arm_holds_its_live_budget_at_two_calls(arm_source):
    assert "api_calls == 2" in arm_source, (
        "the budget is an assertion, not a hope — a leg added without raising it reddens")
