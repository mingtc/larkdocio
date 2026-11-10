"""The always-on half of the comment-op gate — its DISCIPLINE, checked without credentials.

The gate is credential-gated and deselected by default, so its safety rules would otherwise be
unverified on an ordinary ``pytest`` run. This file checks the ones that can be checked
statically, so what matters most cannot rot silently:

* it skips **loudly** rather than passing quietly when credentials are absent;
* it targets **only** files it creates, and names no pre-existing document, token or environment
  variable pointing at one;
* it tears down in a ``finally`` and proves **zero orphans by re-fetch**, not by a return code;
* it confirms the **removal** by re-reading too, for the same reason;
* it asserts the created comment's scope from the **listing** (``is_whole is True`` /
  ``quote is None``) rather than inferring it from the create's ``code 0``;
* its two refusal arms are wired to a transport that **raises on contact**, so zero-API-calls is
  structural;
* it never sends a spreadsheet request, even though one of its arms is about spreadsheets;
* it runs **twice**, on two distinct disposables.

This is the ``*_gate_offline`` companion pattern the rest of the write ring uses.
"""
import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tests" / "test_live_write_comment_op_gate.py"


@pytest.fixture(scope="module")
def gate_source():
    return GATE.read_text(encoding="utf-8")


def test_the_gate_exists_and_carries_the_ring_marker(gate_source):
    assert "pytestmark = pytest.mark.live_write" in gate_source


def test_the_gate_skips_LOUDLY_when_credentials_are_absent(gate_source):
    """A silent pass on a missing credential is the failure mode a live gate must not have:
    the ring would look green while proving nothing."""
    assert "live_write_missing_reason()" in gate_source
    assert "pytest.skip(reason)" in gate_source
    assert "canary_support.load_env()" in gate_source


def test_the_gate_SELF_PROVISIONS_and_names_no_pre_existing_surface(gate_source):
    """The binding safety rule: it may only write to what it created, so it must not be able to
    name anything else — no canary, no zoo, no scratch baseline, no document token."""
    assert "create_document(" in gate_source

    for name in ("LARKDOCIO_CANARY_DOC", "LARKDOCIO_BLOCKZOO_DOC", "LARKDOCIO_SCRATCH",
                 "LARKDOCIO_SHEET", "LARKDOCIO_COMMENT_ZOO_DOC"):
        assert name not in gate_source, (
            f"the gate references {name} — it must only touch files it created itself")
    for helper in ("canary_doc_url", "blockzoo_doc_url", "scratch_sheet_url"):
        assert helper not in gate_source, (
            f"the gate calls {helper}() — that is a pre-existing surface, not a disposable")

    # No hard-coded document/file token. Lark tokens are ~27 chars of mixed case; a literal that
    # shape in a gate is a pre-existing document by definition. (The gate's one long literal is a
    # deliberately unreal block id for the refusal arm, which is never sent — but it must still
    # not look like a real token.)
    for literal in re.findall(r"[\"']([A-Za-z0-9_-]{20,})[\"']", gate_source):
        assert not re.fullmatch(r"(?=.*[a-z])(?=.*[A-Z])(?=.*\d)[A-Za-z0-9]{22,34}", literal), (
            f"the gate carries what looks like a real document token: {literal!r}")


def test_the_gate_never_touches_the_PMs_demo_comment(gate_source):
    """The demo comment on the granted document is the artifact the product decision rests on.
    This gate must be incapable of addressing it."""
    assert "7667877938850762473" not in gate_source
    assert "DocCommentZooExample0000001" not in gate_source


def test_the_gate_tears_down_in_a_finally_and_proves_zero_orphans_BY_REFETCH(gate_source):
    """A delete that answers ``code 0`` and leaves the file is exactly what a return-code check
    misses, so the close-out must re-ask Lark."""
    assert "finally:" in gate_source
    assert "delete_document(" in gate_source
    assert "wc.get_document(doc_id)" in gate_source, (
        "the close-out must RE-FETCH the disposable to prove it is gone")
    assert 'row["file_absent_after_delete"] = True' in gate_source
    assert "confirmed_gone" in gate_source
    assert "left orphans behind" in gate_source


def test_the_gate_confirms_the_REMOVAL_by_rereading_not_by_a_return_code(gate_source):
    assert "comment_absent_after_removal" in gate_source
    assert "the comment survived the cascade" in gate_source


def test_the_gate_asserts_the_created_comments_SCOPE_from_the_listing(gate_source):
    """The create response does not report the scope at all, so ``code 0`` proves nothing about
    what was made. The listing's own answer is the evidence."""
    assert "assert got.is_whole is True" in gate_source
    assert "assert got.quote is None" in gate_source


def test_the_gates_refusal_arms_CANNOT_send(gate_source):
    """Zero-API-calls proved by construction: if a plan-time refusal failed to fire, the attempted
    call raises instead of writing."""
    assert "class RaisesOnContact" in gate_source
    assert "raise AssertionError(" in gate_source
    assert "transport=RaisesOnContact()" in gate_source
    assert "COMMENT_ANCHOR_NOT_CREATABLE" in gate_source
    assert "COMMENT_SURFACE_UNSUPPORTED" in gate_source


def test_the_gate_sends_NO_spreadsheet_request_despite_having_a_sheets_arm(gate_source):
    """The sheets arm proves a refusal, so it must never reach a spreadsheet. The only client it
    uses for that arm is the one that cannot send."""
    assert "SheetsWriteClient" not in gate_source
    assert "shtcn" not in gate_source
    body = gate_source.split("def _refusal_arms_touch_nothing")[1].split("def _one_round")[0]
    assert "_refusing_client()" in body
    assert "get_write_credentials" not in body, (
        "the refusal arms must not even hold real credentials")


def test_the_gate_runs_TWICE_on_two_fresh_disposables(gate_source):
    assert "for i in range(2)" in gate_source
    assert "len(ledger) == 2" in gate_source
    assert "the two rounds shared a file" in gate_source


def test_the_gate_uses_the_SHIPPED_plan_gated_ops_not_the_raw_client(gate_source):
    """The point of the gate: it must exercise ``dry_run`` → ``apply``, because that is what a
    consumer runs. A gate that called the client directly would prove the endpoint, not the op."""
    assert "dry_run([CreateCommentRequest(" in gate_source
    assert "dry_run([RemoveCommentRequest(" in gate_source
    assert "apply(plan, wc, doc_id)" in gate_source
    # ...and it reads back through the shipped reader, not through the transport it wrote with.
    assert "from larkdocio.comments import" in gate_source
    assert "comments(doc_id, client=reader)" in gate_source


def test_the_gate_proves_the_authorship_disclosure_LOOP(gate_source):
    """The create's apply-log hands back the author id the removal requires — that loop is the
    whole reason the disclosure is a disclosure and not a footnote."""
    assert 'author_id = created.comment_record["author_id"]' in gate_source
    assert "RemoveCommentRequest(comment_id=comment_id, author_id=author_id)" in gate_source
    assert "assert got.user_id == author_id" in gate_source


def test_the_gate_is_registered_in_the_capability_registrys_ring():
    """The gate must be discoverable from the registry, not only from the filesystem."""
    from larkdocio import capabilities

    coverage = capabilities(full=True)["surfaces"]["docx-write"]["gate_coverage"]
    members = {m["module"]: m for m in coverage["members"]}
    assert "tests/test_live_write_comment_op_gate.py" in members
    member = members["tests/test_live_write_comment_op_gate.py"]
    assert set(member["proves_contracts"]) >= {
        "comment-create-whole-document-only", "comment-removal-sole-author-or-refuse"}
    assert "zero-orphan-close-out" in member["arms"]
