"""The always-on half of the folder-create gate — its DISCIPLINE, no credentials.

The gate is credential-gated and deselected by default, so its safety rules would otherwise be
unverified on an ordinary ``pytest`` run. This file checks the ones a static read can settle:

* it skips **loudly** rather than passing quietly when the write credentials are absent;
* every folder it touches is one it **created**, under the bot's own root **discovered** through
  the shipped read client — it names no standing fixture, no document, and no environment
  variable pointing at either;
* it deletes everything it made in a ``finally``, proves each deletion by an **independent
  re-query** rather than by a delete's own answer, and **names any residue** instead of implying
  none;
* the folder delete is the **gate's own** call, because the library ships no folder-delete verb —
  and the gate says so rather than reaching for a shipped verb that does not exist;
* it re-measures the **duplicate-name** behaviour live instead of trusting the committed capture,
  and it checks the shipped disclosure string rather than restating it;
* the verdict for "the folder exists" is the **shipped read client's listing**, not the create's
  own echo;
* it reuses the shipped hash check rather than reaching for ``hashlib``;
* it commits **no binary fixture** — the payload is built from source in the file;
* it pins **no Lark refusal code**, so a renumbering on their side cannot redden it.

This is the ``*_gate_offline`` companion pattern the rest of the write ring uses.
"""
import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tests" / "test_live_drive_folder_create_gate.py"


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
    assert "larkdocio-DISPOSABLE-ld467" in gate_source


def test_the_gate_names_NO_STANDING_FIXTURE_and_reads_no_object_env_var(gate_source):
    for forbidden in ("LARKDOCIO_CANARY_DOC", "LARKDOCIO_TEST_FOLDER", "LARKDOCIO_ZOO",
                      "LARKDOCIO_SCRATCH_BASE", "LARKDOCIO_BLOCKZOO_DOC"):
        assert forbidden not in gate_source, forbidden
    # No pasted token: every token in this gate is created in-run. Checked over the STRING
    # LITERALS of its syntax tree, so an SDK class name in the code cannot be mistaken for one.
    import ast

    for node in ast.walk(ast.parse(gate_source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for word in node.value.split():
                assert not (len(word) > 20 and word.isalnum() and not word.isdigit()
                            and any(c.isupper() for c in word)
                            and any(c.islower() for c in word)), (
                    f"a token-shaped literal appears in the gate: {word!r}")


def test_the_teardown_is_in_a_finally_and_PROVEN_by_an_INDEPENDENT_re_query(gate_source):
    assert "finally:" in gate_source
    assert "def _probe" in gate_source
    assert "never a delete's own" in gate_source
    assert "STILL RESOLVES" in gate_source


def test_the_teardown_NAMES_ITS_RESIDUE_rather_than_implying_there_is_none(gate_source):
    """The one thing a live gate may not do is leave a mess quietly. A folder that survived its
    own delete is reported by name in the evidence print."""
    assert 'evidence["residue"]' in gate_source
    assert "is a real leftover and is named" in gate_source


def test_the_folder_delete_is_THE_GATES_OWN_call_and_the_gate_says_why(gate_source):
    """The library ships no folder-delete verb (the ruling opened creation only), so a
    ``finally`` leaning on one would be fiction. The gate makes the raw call and records that."""
    assert "DeleteFileRequest" in gate_source
    assert 'type("folder")' in gate_source
    assert "ships no folder-delete verb" in gate_source


def test_the_DUPLICATE_NAME_behaviour_is_RE_MEASURED_live_not_assumed(gate_source):
    assert "DUPLICATE_NAME_BEHAVIOUR" in gate_source
    assert re.search(r"twin\.token != created\.token", gate_source)
    assert "the disclosure is now WRONG" in gate_source, (
        "a live re-measurement must say what a contradiction MEANS, not merely fail")


def test_the_verdict_that_the_folder_EXISTS_is_the_SHIPPED_LISTING(gate_source):
    """A create's own echo proves acceptance and nothing else — the read-back is the verdict,
    and it is the shipped read client that performs it."""
    assert "list_folder_children_to_exhaustion" in gate_source
    assert 'child["type"] == "folder"' in gate_source


def test_the_upload_leg_uses_the_SHIPPED_op_and_the_SHIPPED_hash_check(gate_source):
    assert "put_file_in_folder" in gate_source
    assert "sha256_of" in gate_source
    assert "import hashlib" not in gate_source


def test_no_binary_fixture_and_no_bytes_are_INSPECTED(gate_source):
    assert "def payload_of" in gate_source
    for forbidden in ("open(", "read_bytes(", "print(data", "decode()"):
        assert forbidden not in gate_source, forbidden


def test_the_gate_pins_NO_LARK_REFUSAL_CODE(gate_source):
    """A renumbering on Lark's side may not redden a live gate — the refusal is asserted on the
    library's own sentence instead."""
    for code in ("1061002", "99992402", "970005", "1061003"):
        assert code not in gate_source, code
    assert '"not a folder" in str(refusal.value)' in gate_source
