"""The always-on half of the upload-identity gate — its DISCIPLINE, no credentials.

The gate is credential-gated and deselected by default, so its safety rules would otherwise be
unverified on an ordinary ``pytest`` run. This file checks the ones a static read can settle:

* it skips **loudly** rather than passing quietly when the write credentials are absent;
* every object it touches is one it **created**, in a folder it made under the bot's own root
  **discovered** through the shipped read client — it names no standing fixture, no document and
  no environment variable pointing at either;
* it deletes everything it made in a ``finally`` and **names any residue** instead of implying
  none;
* the folder delete is the **gate's own** call, because the library ships no folder-delete verb;
* it re-measures the **duplicate-upload** behaviour live instead of trusting the committed
  capture, and says what a contradiction would MEAN rather than merely failing;
* the second delete is read through the **shipped predicate** (``file_is_gone``) rather than by
  matching a message string — which is the whole point of shipping a predicate;
* **both halves of gone-ness** appear: the token must leave the folder listing (asserted), and
  what the metadata route then says is **recorded, never asserted as a purge**;
* it reuses the shipped hash check rather than reaching for ``hashlib``;
* it commits **no binary fixture** — the payload is built from source in the file;
* it pins **no Lark refusal code**, so a renumbering on their side cannot redden it.

This is the ``*_gate_offline`` companion pattern the rest of the write ring uses.
"""
import ast
import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tests" / "test_live_drive_upload_identity_gate.py"


@pytest.fixture(scope="module")
def gate_source():
    return GATE.read_text(encoding="utf-8")


def test_the_gate_exists_and_carries_the_ring_marker(gate_source):
    assert "pytestmark = pytest.mark.live_write" in gate_source


def test_the_gate_skips_LOUDLY_when_credentials_are_absent(gate_source):
    assert "canary_support.load_env()" in gate_source
    assert "live_write_missing_reason()" in gate_source
    assert "pytest.skip(reason)" in gate_source


def test_every_subject_is_one_this_gate_CREATED_in_the_human_visible_disposables_folder(
        gate_source):
    """TRANSFORMED, NOT DELETED. This guard used to assert the gate created its parent under
    ``root_folder_token()`` — the bot's OWN root — so that everything the run touched was made
    by the run. **That reason stands: every SUBJECT is still one this gate created.** What moved
    is WHERE they are made: the app's own root has no human interface, so a subject created
    there could not be seen — nor its residue cleaned — by the account holder. The parent is now
    the configured, human-visible disposables folder, and the gate SKIPS LOUDLY when it is unset
    rather than falling back to a place nobody can see.
    """
    assert "require_disposables_folder()" in gate_source
    assert "root_folder_token()" not in gate_source, (
        "the app's own root is no longer a destination this harness writes into")
    assert "larkdocio-DISPOSABLE-ld464" in gate_source
    assert "create_folder(" in gate_source


def test_the_gate_names_NO_STANDING_FIXTURE_and_reads_no_object_env_var(gate_source):
    for forbidden in ("LARKDOCIO_CANARY_DOC", "LARKDOCIO_TEST_FOLDER", "LARKDOCIO_ZOO",
                      "LARKDOCIO_SCRATCH_BASE", "LARKDOCIO_BLOCKZOO_DOC"):
        assert forbidden not in gate_source, forbidden
    # No pasted token: every token in this gate is created in-run. Checked over the STRING
    # LITERALS of its syntax tree, so an SDK class name in the code cannot be mistaken for one.
    for node in ast.walk(ast.parse(gate_source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for word in node.value.split():
                assert not (len(word) > 20 and word.isalnum() and not word.isdigit()
                            and any(c.isupper() for c in word)
                            and any(c.islower() for c in word)), (
                    f"a token-shaped literal appears in the gate: {word!r}")


def test_the_teardown_is_in_a_finally_and_NAMES_ITS_RESIDUE(gate_source):
    assert "finally:" in gate_source
    assert 'evidence["residue"]' in gate_source
    assert "is a real leftover and is named" in gate_source


def test_the_folder_delete_is_THE_GATES_OWN_call_and_the_gate_says_why(gate_source):
    assert "DeleteFileRequest" in gate_source
    assert 'type("folder")' in gate_source
    assert "ships no folder-delete verb" in gate_source


def test_the_DUPLICATE_UPLOAD_behaviour_is_RE_MEASURED_live_not_assumed(gate_source):
    assert "DUPLICATE_UPLOAD_BEHAVIOUR" in gate_source
    assert re.search(r"second\.file_token != first\.file_token", gate_source)
    assert "the disclosure is now WRONG" in gate_source, (
        "a live re-measurement must say what a contradiction MEANS, not merely fail")


def test_the_LOOKUP_is_exercised_on_BOTH_arms(gate_source):
    """Found and not-found are different answers and both must run: a lookup that only ever
    matched would never prove that an absence comes back as an empty answer rather than a
    refusal."""
    assert gate_source.count("find_children_by_name(") >= 4
    assert "absent.found is False" in gate_source
    assert "found.found is True" in gate_source


def test_the_SECOND_DELETE_is_read_through_the_SHIPPED_PREDICATE(gate_source):
    """The predicate is the contract; the message is disclosure. A gate that asserted the
    sentence would re-freeze the very string this issue had to change."""
    assert "file_is_gone(refusal.value) is True" in gate_source
    assert '"still there" not in str(refusal.value)' in gate_source


def test_BOTH_HALVES_of_gone_ness_appear_and_only_ONE_is_asserted(gate_source):
    """The trap this issue exists to avoid: swapping one wrong sentence for another. The
    listing half is asserted because the library claims it; the metadata half is RECORDED,
    because a trashed file token was measured still resolving."""
    assert "not in after.tokens" in gate_source
    assert 'evidence["metadata_after_delete"]' in gate_source
    assert "STILL RESOLVES" in gate_source
    assert "trash, not purge" in gate_source


def test_the_upload_leg_uses_the_SHIPPED_op_and_the_SHIPPED_hash_check(gate_source):
    assert "put_file_in_folder" in gate_source
    assert "sha256_of" in gate_source
    assert "import hashlib" not in gate_source


def test_no_binary_fixture_and_no_bytes_are_INSPECTED(gate_source):
    assert "def payload_of" in gate_source
    for forbidden in ("open(", "read_bytes(", "print(data", "decode()"):
        assert forbidden not in gate_source, forbidden


def test_the_gate_pins_NO_LARK_REFUSAL_CODE(gate_source):
    """A renumbering on Lark's side may not redden a live gate — the already-gone answer is
    read through the shipped predicate instead, which is where the code is authored once."""
    for code in ("1061007", "1061002", "1061003", "99992402", "970005"):
        assert code not in gate_source, code


def test_the_gate_does_NOT_re_send_the_eight_overwrite_forms(gate_source):
    """They are measured and captured; re-sending eight ignored parameters on every run would
    be noise against a live tenant, and the gate says so rather than leaving it implicit."""
    for form in ("duplicate_handling", "conflict_strategy", "upsert=true", "?overwrite=true"):
        assert form not in gate_source, form
    assert "they are captured, not re-sent here" in gate_source
