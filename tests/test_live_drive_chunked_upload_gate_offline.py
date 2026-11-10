"""The ALWAYS-ON offline half of ``test_live_drive_chunked_upload_gate``.

A live gate proves nothing on a machine with no credentials, and the disciplines that matter
most on this arm are the ones a green run cannot show you — they are properties of what the
gate *is allowed to do*, not of what happened when it ran. So they are pinned here, in the ring
that always runs.

What this file holds, all by reading the gate's own source:

* **the subject is a disposable this harness creates and deletes** — ``create_folder`` appears
  in the GATE as D-12 plumbing and the gate deletes what it made, while the LIBRARY still ships
  no folder-creating call at all;
* **no standing fixture, no canary, no caller-supplied destination** — no token-shaped literal
  and no document-naming environment variable is read;
* **teardown is proven by an independent RE-QUERY**, never by a delete's own ``code:0``, and
  the file half is *recorded* rather than asserted because a delete is trash, not purge;
* **the residue is LEDGERED, never fake-cleaned** — an abandoned ``upload_id`` cannot be
  cancelled by any measured verb, so no cleanup leg may pretend to;
* **the multi-part claim cannot be quietly downgraded** — the gate asserts more than one part
  and says why a single part would be a finding rather than a pass;
* **the shipped hash check is reused** rather than ``hashlib`` reached for, **no binary fixture
  is committed**, and **no Lark refusal number is asserted** anywhere in the arm.
"""
import pathlib

import pytest

pytestmark = pytest.mark.conformance

GATE = pathlib.Path(__file__).resolve().parent / "test_live_drive_chunked_upload_gate.py"
SOURCE = GATE.read_text("utf-8")


def test_the_gate_is_in_the_live_write_ring():
    assert "pytestmark = pytest.mark.live_write" in SOURCE


def test_the_gate_creates_AND_deletes_its_own_folder():
    """D-12 plumbing in the harness, and a deletion that actually happens."""
    assert "create_folder" in SOURCE
    assert "_create_disposable_folder" in SOURCE
    assert "_delete_folder" in SOURCE
    assert 'type("folder")' in SOURCE


def test_the_folder_CREATE_is_now_the_LIBRARYS_and_this_GATE_still_makes_its_own():
    """**TRANSFORMED, NOT DELETED (LD-467, D-24).** This said the gate may create a folder and
    the library may not, and the reason stands: **this gate must own the disposables it
    writes into**, so it may not lean on library code to conjure a destination.

    What is superseded is the library half — a product ruling of 2026-08-14 opened one create
    verb, in one module. So the check is re-scoped to what it was really protecting: the gate
    creates its own parent, on its own raw call, and the shipped create lives in exactly the
    one module that owns it.
    """
    src = GATE.resolve().parent.parent / "src" / "larkdocio"
    hits = {str(p.relative_to(src)) for p in src.rglob("*.py")
            if "create_folder(" in p.read_text("utf-8")
            or "files/create_folder" in p.read_text("utf-8")}
    assert hits == {"common/destination.py", "drive/folders_write.py", "drive/ops.py",
                    "permissions.py"}, hits
    assert "create_folder" in SOURCE, "the gate must still make its own disposable parent"


def test_the_gate_names_no_standing_fixture_and_reads_no_document_env_var():
    for forbidden in ("LARKDOCIO_CANARY_DOC", "LARKDOCIO_TEST_FOLDER", "LARKDOCIO_ZOO"):
        assert forbidden not in SOURCE, forbidden
    # No pasted token: every token in this arm is created in-run. Checked over the STRING
    # LITERALS of its syntax tree, so an SDK class name in the code cannot be mistaken for one.
    import ast

    for node in ast.walk(ast.parse(SOURCE)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for word in node.value.split():
                assert not (len(word) > 20 and word.isalnum() and not word.isdigit()
                            and any(c.isupper() for c in word)
                            and any(c.islower() for c in word)), (
                    f"a token-shaped literal appears in the gate: {word!r}")


def test_teardown_is_proven_by_an_INDEPENDENT_re_query():
    assert "def _probe" in SOURCE
    assert "never a delete's own" in SOURCE
    assert "STILL RESOLVES" in SOURCE
    # And the file half is RECORDED, not asserted: trash is not purge.
    assert "file_after_delete" in SOURCE
    assert 'assert evidence["file_after_delete"]' not in SOURCE


def test_the_residue_is_LEDGERED_and_no_fake_cancel_leg_exists():
    assert "abandoned_upload_ids" in SOURCE
    assert "no cancel verb was found" in SOURCE
    assert "expiry is unmeasured" in SOURCE
    for invented in ("upload_cancel", "cancel_upload", "abort_upload", "files/upload_abort"):
        assert invented not in SOURCE, invented


def test_the_MULTI_PART_claim_cannot_be_quietly_downgraded():
    """The arm exists for ``block_num > 1``; a single part must fail it, not pass it."""
    assert "assert linked.parts > 1" in SOURCE
    assert "do not claim multi-part is proven" in SOURCE


def test_the_size_discipline_is_the_SMALLEST_interesting_payload():
    assert "OBSERVED_BLOCK_SIZE + 1" in SOURCE
    assert "smallest" in SOURCE


def test_the_shipped_hash_check_is_reused_and_no_binary_fixture_is_committed():
    assert "from larkdocio.base.media import sha256_of" in SOURCE
    assert "hashlib" not in SOURCE
    assert "def payload_of" in SOURCE  # bytes are generated, never committed


def test_no_lark_refusal_NUMBER_is_asserted_in_the_arm():
    for line in SOURCE.splitlines():
        if line.strip().startswith("assert"):
            assert not any(token.isdigit() and len(token) >= 4
                           for token in line.replace("(", " ").replace(")", " ").split()), line
