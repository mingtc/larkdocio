"""The always-on half of the LD-474 bytes-leg gate — its DISCIPLINE, no credentials.

The gate is credential-gated and deselected by default, so its safety rules would otherwise be
unverified on an ordinary ``pytest`` run — and a gate that "passes" by never running is exactly
the shape of evidence this issue exists to distrust. This file checks what a static read can
settle:

* it skips **loudly** rather than passing quietly when the write credentials are absent;
* every object it touches is one it **created**, under the bot's own root **discovered** through
  the shipped read client — it names no standing fixture, no canary, and no environment variable
  pointing at an object;
* it deletes everything it made in a ``finally``, proves each deletion by an **independent
  re-query** rather than by a delete's own answer, and **names any residue**;
* the folder delete is the **gate's own** call, because the library ships no folder-delete verb;
* the disproof is a real **round trip**: the token the walk skipped is the token that is
  downloaded, and the verdict is the shipped hash — not a length, not an eyeball;
* the ledger-field measurement asserts the **absences** (no size, no digest, no etag) rather
  than only the presences, because the guide's *"what you cannot build on"* list is the half
  that rots silently;
* it commits **no binary fixture** — the payload is built from source in the file;
* it pins **no Lark refusal code**, so a renumbering on their side cannot redden it.
"""
import ast
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tests" / "test_live_drive_bytes_leg_gate.py"


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
    assert "larkdocio-DISPOSABLE-ld474" in gate_source


def test_the_gate_names_NO_STANDING_FIXTURE_and_reads_no_object_env_var(gate_source):
    for forbidden in ("LARKDOCIO_CANARY_DOC", "LARKDOCIO_TEST_FOLDER", "LARKDOCIO_ZOO",
                      "LARKDOCIO_SCRATCH_BASE", "LARKDOCIO_BLOCKZOO_DOC"):
        assert forbidden not in gate_source, forbidden
    # No pasted token: every token in this gate is minted in-run. Checked over the STRING
    # LITERALS of its syntax tree, so an SDK class name in the code cannot be mistaken for one.
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
    assert 'evidence["residue"]' in gate_source
    assert "is a real leftover and is named" in gate_source


def test_the_folder_delete_is_THE_GATES_OWN_call_and_the_gate_says_why(gate_source):
    assert "DeleteFileRequest" in gate_source
    assert 'type("folder")' in gate_source
    assert "ships no folder-delete verb" in gate_source


def test_THE_DISPROOF_downloads_THE_TOKEN_THE_WALK_SKIPPED(gate_source):
    """The whole point. A gate that downloaded *a* file would prove the download leg works; this
    one must download **the child the folder read declined to read**, which is what makes it a
    disproof of the sentence rather than a demonstration of an unrelated verb."""
    assert "read_folder(folder.token" in gate_source
    assert "files.download(uploaded.file_token)" in gate_source
    assert "child.child.token == uploaded.file_token" in gate_source
    assert "sha256_of(fetched) == uploaded.sha256" in gate_source


def test_the_gate_asserts_the_SKIP_REASON_names_the_verb_and_claims_no_absence(gate_source):
    assert '"DriveFilesWriteClient.download" in skip_reason' in gate_source
    assert '"is not shipped" not in skip_reason' in gate_source


def test_the_ledger_measurement_asserts_the_ABSENCES_not_only_the_presences(gate_source):
    """The half that rots in silence. A row gaining a `size` key would make the shipped guide
    wrong in the consumer's favour and nothing would say so — so the absence is asserted."""
    assert "ABSENT_IDENTITY_KEYS" in gate_source
    for key in ("size", "digest", "sha256", "etag", "checksum", "content_hash", "md5"):
        assert f'"{key}"' in gate_source, key
    assert "must be re-measured" in gate_source


def test_the_change_detector_measures_BOTH_the_move_AND_the_inert_poll(gate_source):
    """One edit must advance it and a read must not — a gate that measured only the first would
    let *"polling it is inert"* ship on nothing."""
    assert "assert after > before" in gate_source
    assert 'assert again == after, "a read moved the revision' in gate_source


def test_the_classification_probe_goes_through_the_SHIPPED_OP_on_a_DOCUMENTED_route(gate_source):
    """**TRANSFORMED, not deleted (D-24).** The reason is unchanged: the whole point of this leg
    is that the field rides an ordinary **documented** open-API call rather than a private one,
    so the gate may never reach it by a hand-typed path. What moved is the conclusion about
    *which* shipped thing carries it — until 1.36 the library surfaced the field for nothing and
    the constant was the closest shipped anchor; the read now ships, so the gate goes through
    the **op** (which rides that same constant), and a gate still hand-rolling the call would
    leave the shipped leg unmeasured."""
    assert "document_security_level(doc_id)" in gate_source
    assert "documented" in gate_source
    assert "answer.reported" in gate_source and "answer.outcome" in gate_source
    assert "_call(" not in gate_source, (
        "the gate reaches the transport seam directly again — the classification leg is a "
        "shipped op now and must be measured as one")


def test_no_binary_fixture_and_no_bytes_are_INSPECTED(gate_source):
    assert "def payload_of" in gate_source
    for forbidden in ("open(", "read_bytes(", "print(data", "decode()"):
        assert forbidden not in gate_source, forbidden
    assert "import hashlib" not in gate_source, "the shipped sha256_of is the hash here"


def test_the_gate_pins_NO_LARK_REFUSAL_CODE(gate_source):
    for code in ("1061002", "99992402", "970005", "1063001", "1069914"):
        assert code not in gate_source, code
