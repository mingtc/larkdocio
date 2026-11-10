"""The always-on half of the docx folder-ACL gate — its DISCIPLINE, no credentials.

The gate is credential-gated and deselected by default, so its safety rules would otherwise be
unverified on an ordinary ``pytest`` run. This file checks the ones a static read can settle:

* it skips **loudly** rather than passing quietly when the write credentials are absent;
* every object it touches is one it **created** — both documents and the parent folder, the
  folder under the bot's own root **discovered** through the shipped read client — so it names
  no standing fixture, no canary and no environment variable pointing at either;
* it carries the **CONTROL** — a document created with no ``folder_token`` — because "the folder
  case is different" is a claim with no baseline otherwise;
* the folder-filed document's rows are asserted to arrive as ``perm_type='container'``, which is
  the vocabulary the guide teaches, **per row** rather than counted: a folder that carries no
  rows of its own passes none down, and that is inheritance answering rather than a failure;
* the FOLDER's own member list is **recorded, never asserted** — whether that route answers for
  a folder at all is the question, so a refusal there is data;
* it deletes everything it made in a ``finally``, proves each deletion by an **independent
  re-query** rather than by a delete's own answer, and **names any residue** instead of implying
  none;
* the folder delete is the **gate's own** call, because the library ships no folder-delete verb;
* it pins **no Lark refusal code**, so a renumbering on their side cannot redden it.

This is the ``*_gate_offline`` companion pattern the rest of the write ring uses.
"""
import ast
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tests" / "test_live_docx_folder_acl_gate.py"


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
    assert "larkdocio-DISPOSABLE-ld469" in gate_source
    assert "create_document(" in gate_source


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


def test_the_CONTROL_is_now_a_REFUSAL_and_the_old_finding_is_PRESERVED(gate_source):
    """TRANSFORMED, NOT DELETED.

    The reason the control existed stands verbatim: the no-folder case was the baseline the
    folder case is different FROM, and a gate that ran only the folder half could not tell an
    inherited row from a row every document has. What changed is that the library **can no
    longer create the control's subject**: a destination-less create is a local refusal, so the
    baseline can only be *proved unreachable*, not re-measured. The old finding — a document
    created with no folder came back with an empty member list — is preserved in the gate's own
    module docstring, where a reader looking for the baseline will find it.
    """
    assert "MissingDestinationError" in gate_source, (
        "the control arm must assert the refusal, not create a subject nobody can see")
    assert "NOT CREATED" in gate_source
    assert "control_members.members == ()" not in gate_source
    assert "no folder came back with an empty member list" in gate_source, (
        "the preserved finding must be readable in the gate itself")


def test_the_INHERITED_ROW_VOCABULARY_is_asserted_per_row_not_counted(gate_source):
    """``perm_type='container'`` is the word a consumer gets back and the word the guide now
    teaches, so it is asserted on every row the folder-filed document carries — and only on
    those, because a folder with no rows of its own passes none down."""
    assert 'row.perm_type == "container"' in gate_source
    assert "the vocabulary the guide teaches is now wrong" in gate_source


def test_the_FOLDERS_OWN_member_list_is_RECORDED_rather_than_asserted(gate_source):
    """Whether the members route answers for a folder at all is the question this leg asks, so
    a refusal is a measurement. The gate must not raise on it, and must not assert it either."""
    assert "NOT READABLE for a folder" in gate_source
    assert "RECORDED, never asserted" in gate_source
    assert 'evidence["folder_members"]' in gate_source


def test_the_folder_member_read_is_the_gates_OWN_call_and_says_why(gate_source):
    """The shipped surface refuses ``folder`` by name as unmeasured — LD-456's fence. A gate
    that widened a shipped refusal to serve itself would be moving the product to pass."""
    assert "LD-456's fence, which" in gate_source
    assert "this gate does not move" in gate_source


def test_the_teardown_is_in_a_finally_and_PROVEN_by_an_INDEPENDENT_re_query(gate_source):
    assert "finally:" in gate_source
    assert "def _probe" in gate_source
    assert "never a delete's own" in gate_source
    assert "STILL RESOLVES" in gate_source


def test_the_teardown_NAMES_ITS_RESIDUE_rather_than_implying_there_is_none(gate_source):
    assert 'evidence["residue"]' in gate_source
    assert "is a real leftover and is named, not implied" in gate_source


def test_the_folder_delete_is_the_gates_own_call_because_no_verb_ships(gate_source):
    assert "the gate's own call, because no folder-delete verb ships" in gate_source
    assert "DeleteFileRequest" in gate_source


def test_member_ids_are_abbreviated_and_nothing_is_asserted_on_the_abbreviation(gate_source):
    """An inherited row names a person or a chat this run did not create and cannot delete."""
    assert "member_id_prefix" in gate_source
    assert "Nothing is asserted on the truncation." in gate_source


def test_the_gate_pins_no_lark_refusal_number(gate_source):
    """A renumbering on Lark's side must not redden this ring."""
    for code in ("99992402", "1061007", "1063001", "1310249", "1770001"):
        assert code not in gate_source, code
