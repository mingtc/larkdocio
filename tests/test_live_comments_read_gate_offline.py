"""The always-on half of the comments-read gate — its DISCIPLINE, checked without credentials.

The gate itself is credential-gated and deselected by default, which means its safety rules
would otherwise be unverified on an ordinary ``pytest`` run. This file checks the rules that
can be checked statically, so the ones that matter most cannot rot silently:

* it skips **loudly** rather than passing quietly when credentials are absent;
* it targets **only files it creates**, and names no pre-existing document, token or
  environment variable that points at one;
* its teardown is in a ``finally`` and its close-out asserts **zero orphans**;
* it runs **twice**, on two distinct disposables;
* its comment writes go through the **shipped** comment calls, and there is exactly **one**
  implementation of them anywhere in the repo.

**The last of those rules changed, deliberately.** While comment creation was not a capability,
this file's job was to keep it out of ``src/``: the create and the cascade removal lived in
``tests/comments_live_scaffold.py``, and nothing that shipped could reach them. Comment creation
and removal are shipped, plan-gated ops now, so that scaffolding is **deleted** and the rule it
enforced is replaced by its successor — not "creation must not be in the package" but "creation
must be in the package **exactly once**". The successor is the stronger rule: the old one would
have permitted two hand-rolled copies as long as both sat in the test tree.

This is the ``*_gate_offline`` companion pattern the write ring already uses.
"""
import ast
import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tests" / "test_live_comments_read_gate.py"
TESTS = REPO_ROOT / "tests"
SRC = REPO_ROOT / "src" / "larkdocio"

#: The one module allowed to build a comment-family URL: the shipped write client. Every other
#: file — test tree included — must reach the endpoints through it.
COMMENT_PATH_OWNER = SRC / "write" / "client.py"


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
    """The binding safety rule. It may only write to what it created, so it must not be able
    to name anything else — no canary, no zoo, no scratch baseline, no document token."""
    assert "create_document(" in gate_source

    forbidden_env = (
        "LARKDOCIO_CANARY_DOC", "LARKDOCIO_BLOCKZOO_DOC", "LARKDOCIO_SCRATCH",
        "LARKDOCIO_SHEET",
    )
    for name in forbidden_env:
        assert name not in gate_source, (
            f"the gate references {name} — it must only touch files it created itself")
    for helper in ("canary_doc_url", "blockzoo_doc_url", "scratch_sheet_url"):
        assert helper not in gate_source, (
            f"the gate calls {helper}() — that is a pre-existing surface, not a disposable")

    # No hard-coded document/file token. Lark tokens are ~27 chars of mixed case; a literal
    # that shape in a gate is a pre-existing document by definition.
    for literal in re.findall(r"[\"']([A-Za-z0-9_-]{20,})[\"']", gate_source):
        assert not re.fullmatch(r"(?=.*[a-z])(?=.*[A-Z])(?=.*\d)[A-Za-z0-9]{22,34}", literal), (
            f"the gate carries what looks like a real document token: {literal!r}")


def test_the_gate_tears_down_in_a_finally_and_asserts_zero_orphans(gate_source):
    assert "finally:" in gate_source
    assert "delete_document(" in gate_source
    assert "_remove_via_reply_cascade(" in gate_source
    assert "confirmed_gone" in gate_source
    assert "left orphans behind" in gate_source


def test_the_gate_runs_TWICE_on_two_fresh_disposables(gate_source):
    """A single clean close-out can be luck; the amplifier asks for the procedure."""
    assert "for i in range(2)" in gate_source
    assert 'len(ledger) == 2' in gate_source
    assert 'the two rounds shared a file' in gate_source


def test_the_gate_asserts_the_SHAPE_ASYMMETRY_live_not_only_offline(gate_source):
    """The trap most worth proving against real Lark: the create response omits the scope and
    the listing reports it, for the same comment, through the same model."""
    assert 'assert "is_whole" not in created' in gate_source
    assert "SCOPE_UNREPORTED" in gate_source and "SCOPE_WHOLE_DOCUMENT" in gate_source
    assert "Comment.from_file_comment(FileComment(created))" in gate_source


def test_the_gate_reads_back_THROUGH_THE_SHIPPED_SURFACE(gate_source):
    """Not through the raw transport it wrote with — otherwise it proves the API, not us."""
    assert "from larkdocio.comments import" in gate_source
    assert re.search(r"\bcomments\(doc_id, client=reader\)", gate_source)


#: The raw-transport seams a hand-rolled comment call would have to reach for. Naming a path is
#: not the offence — a byte-exact test *must* be able to spell the URL it asserts on, and the
#: read double must be able to key its responses by endpoint. Handing a comment path to one of
#: these is the offence, because that is what "an implementation" means.
_TRANSPORT_SEAMS = ("_write", "_send", "_raw_request")


def _spells_a_comment_path(tree):
    """Whether this module's **string literals** compose a comment-family URL.

    AST-based rather than a substring grep, deliberately: a grep cannot tell a URL from a
    sentence describing one, so it would flag every explanatory paragraph in the repo. The pieces
    of an f-string are literals too, which is the shape the retired scaffolding had.
    """
    literals = "\n".join(n.value for n in ast.walk(tree)
                         if isinstance(n, ast.Constant) and isinstance(n.value, str))
    return "drive/v1/files" in literals and "/comments" in literals


def _reaches_a_transport(tree):
    """Whether this module calls one of :data:`_TRANSPORT_SEAMS` — i.e. actually sends."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name in _TRANSPORT_SEAMS:
                return True
    return False


def _comment_implementations(root):
    """Modules under ``root`` that BOTH spell a comment URL and send it somewhere.

    The conjunction is the whole idea. Spelling a path is not an implementation — a byte-exact
    test must be able to name the URL it asserts on, and the read double must key its canned
    responses by endpoint. Reaching a transport is not an implementation either; plenty of code
    does. Doing both in one module is what "a hand-rolled comment call" is.
    """
    out = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if _spells_a_comment_path(tree) and _reaches_a_transport(tree):
            out.append(path)
    return out


def test_comment_writes_have_EXACTLY_ONE_implementation_in_the_repo():
    """The promotion's real contract: the shipped path is the only path.

    Comment creation and the cascade removal were hand-rolled in the test tree while they were
    not capabilities. They ship now, so a surviving second copy would let the gates pass against
    an implementation consumers never run — the exact defect the promotion pattern exists to
    prevent. So the shipped write client must be the ONLY module anywhere in ``src/`` or
    ``tests/`` that both knows a comment URL and sends one.
    """
    owners = _comment_implementations(SRC) + _comment_implementations(TESTS)
    assert owners == [COMMENT_PATH_OWNER], (
        "exactly one module may issue a comment-family request (the shipped write client); "
        f"found {[str(p.relative_to(REPO_ROOT)) for p in owners]}")


def test_the_one_implementation_guard_is_not_vacuous():
    """The guard above passes if it finds exactly one module. It would also pass if its
    conjunction were broken and it found *nothing* — so prove each half really discriminates.

    Both halves must be **selective**: some modules spell a comment path without sending
    (the byte-exact write-op test and the read double), some reach a transport without spelling
    one (every other client), and the owner is the only module in the intersection.
    """
    trees = {path: ast.parse(path.read_text(encoding="utf-8"))
             for root in (SRC, TESTS) for path in sorted(root.rglob("*.py"))}
    spellers = {p for p, t in trees.items() if _spells_a_comment_path(t)}
    senders = {p for p, t in trees.items() if _reaches_a_transport(t)}

    assert COMMENT_PATH_OWNER in spellers and COMMENT_PATH_OWNER in senders, (
        "the guard cannot even see the module it is about — its predicates are broken")
    assert len(spellers - senders) >= 2, (
        "no module spells a comment path without sending it, so the 'spells' half is not being "
        f"tested by anything: {sorted(str(p.name) for p in spellers)}")
    assert len(senders - spellers) >= 2, (
        "no module reaches a transport without a comment path, so the 'sends' half is untested")
    assert spellers & senders == {COMMENT_PATH_OWNER}


def test_the_write_client_owns_exactly_the_three_comment_calls_and_no_fourth():
    """Three comment calls ship — create, list replies, delete reply. A fourth would be a
    comment write this project deliberately does not have (a reply-content rewrite, a
    solve/unsolve, or the delete-a-comment route that does not exist)."""
    from larkdocio.write.client import WriteClient

    comment_methods = sorted(
        name for name in vars(WriteClient)
        if not name.startswith("_") and "comment" in name)
    assert comment_methods == [
        "create_whole_document_comment", "delete_comment_reply", "list_comment_replies",
    ], comment_methods

    text = COMMENT_PATH_OWNER.read_text(encoding="utf-8")
    for absent in ("DELETE\", self._comment_path(document_id, f\"/{comment_id}\"",
                   "PUT\", self._comment_path", "PATCH\", self._comment_path"):
        assert absent not in text, (
            f"the client gained a comment write that does not ship: {absent!r}")


def test_the_deleted_scaffolding_has_not_come_back_under_any_name():
    """The specific duplicate that was removed, named so it cannot quietly return.

    This file is excluded from its own scan: a guard has to be able to name what it forbids.
    Nothing hides in the gap — an implementation placed *here* would be an implementation inside
    the test asserting there is none.
    """
    assert not (TESTS / "comments_live_scaffold.py").exists(), (
        "the comment scaffolding is back — its three calls are shipped WriteClient methods now")
    retired = ("create_whole_file_comment", "remove_comment_via_reply_cascade",
               "import comments_live_scaffold")
    me = pathlib.Path(__file__).resolve()
    offenders = []
    for path in sorted(SRC.rglob("*.py")) + sorted(TESTS.rglob("*.py")):
        if path.resolve() == me:
            continue
        text = path.read_text(encoding="utf-8")
        offenders += [f"{path.relative_to(REPO_ROOT)}: {t}" for t in retired if t in text]
    assert not offenders, f"the retired scaffolding is still referenced: {offenders}"


def test_the_read_gate_calls_the_SHIPPED_comment_methods():
    """Not merely 'no duplicate exists' — this gate must actually be the shipped path's caller,
    otherwise the promotion moved the code without moving the coverage."""
    gate = GATE.read_text(encoding="utf-8")
    for shipped in ("wc.create_whole_document_comment(",
                    "wc.list_comment_replies(",
                    "wc.delete_comment_reply("):
        assert shipped in gate, f"the read gate no longer exercises {shipped}"


def test_the_shipped_package_issues_NO_comment_write_of_any_kind():
    """The out-of-scope fence, mechanized: no create, no reply, no resolve, no delete anywhere
    on the comments surface — it is a read."""
    comments_pkg = SRC / "comments"
    for path in sorted(comments_pkg.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("CreateFileComment", "PatchFileComment", "UpdateFileCommentReply",
                          "DeleteFileCommentReply"):
            assert forbidden not in text, (
                f"{path.relative_to(REPO_ROOT)} reaches a comment WRITE endpoint: {forbidden}")


def test_the_gate_is_registered_in_the_capability_registrys_ring():
    """The gate must be discoverable from the registry, not only from the filesystem."""
    from larkdocio import capabilities

    coverage = capabilities(full=True)["surfaces"]["docx-comments-read"]["gate_coverage"]
    modules = [m["module"] for m in coverage["members"]]
    assert "tests/test_live_comments_read_gate.py" in modules
    # LD-539: the payload states the command a consumer can TYPE, and the bare
    # command has not run the ring since LD-537 armed the consent fence.
    assert coverage["command"] == "LARKDOCIO_LIVE_WRITE_AUTHORIZED_BY=LD-NNN pytest -m live_write"
    assert "self-provision" in coverage["target_policy"]
    # The disposables-only rule is part of the published contract, not a footnote.
    assert "It never reads the canary document" in coverage["target_policy"]
    assert "never anything it did not create" in coverage["target_policy"]
    # Superseded deliberately: this used to require the registry to call comment creation
    # scaffolding rather than a capability. It IS a capability now, and the registry must say
    # so — and must say that this gate uses the shipped calls rather than a private copy.
    assert "SHIPPED comment calls" in coverage["target_policy"], (
        "the registry must say this gate's comment writes are the shipped ones")
    assert "one implementation" in coverage["target_policy"]
