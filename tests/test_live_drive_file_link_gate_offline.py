"""The always-on half of the uploaded-file sentence-link gate — its DISCIPLINE, no credentials.

The gate is credential-gated and deselected by default, so its safety rules would otherwise be
unverified on an ordinary ``pytest`` run. This file checks the ones a static read can settle:

* it skips **loudly** rather than passing quietly — twice: once for the write credentials and
  once for the **caller-supplied folder token**, which it will not invent;
* it **creates no folder** and names no folder-creating call — the organize-rung fence;
* it writes only to a document it **created**, and names no pre-existing document, token or
  environment variable pointing at one;
* it deletes the document **and the uploaded file** in a ``finally``, and proves each gone by an
  **independent re-query** rather than by a delete's own answer;
* it does **not** pretend to purge the media tokens, which nothing can, and prints them instead;
* the verdict is the **reader's own Markdown**, not the write's echo — the gate runs the shipped
  reader rather than walking the write client's answer;
* it reuses the shipped hash check rather than reaching for ``hashlib``;
* it commits **no binary fixture** — the ``.html`` is built from source in the file;
* it pins **no Lark refusal code**, so a renumbering on their side cannot redden it.

This is the ``*_gate_offline`` companion pattern the rest of the write ring uses.
"""
import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tests" / "test_live_drive_file_link_gate.py"


@pytest.fixture(scope="module")
def gate_source():
    return GATE.read_text(encoding="utf-8")


def test_the_gate_exists_and_carries_the_ring_marker(gate_source):
    assert "pytestmark = pytest.mark.live_write" in gate_source


def test_the_gate_skips_LOUDLY_when_credentials_are_absent(gate_source):
    assert "live_write_missing_reason()" in gate_source
    assert "pytest.skip(reason)" in gate_source
    assert "canary_support.load_env()" in gate_source


def test_the_gate_skips_LOUDLY_rather_than_inventing_a_destination_folder(gate_source):
    assert "LARKDOCIO_TEST_FOLDER" in gate_source
    assert "creates none" in gate_source
    assert re.search(r"if not folder:\s*\n\s*pytest\.skip\(", gate_source)


def test_the_fallback_destination_is_CONFIGURED_never_created_and_never_the_apps_own_root(
        gate_source):
    """TRANSFORMED, NOT DELETED.

    The reason stands: a folder the gate MADE is not a legitimate destination, because creating
    one is exactly the rung that issue left closed — so the destination is taken, never made.
    What is superseded is the second choice. The bot's own root was read as legitimate; it is
    the space no human interface can browse, so an object uploaded there could not be seen or
    removed by the account holder. The fall-back is now the configured, human-visible
    disposables folder, and with neither variable set the gate skips.
    """
    assert "disposables_folder()" in gate_source
    assert "root_folder_token()" not in gate_source
    assert "create_folder" not in gate_source
    assert "folder_source" in gate_source


def test_the_gate_CREATES_NO_FOLDER_which_is_the_organize_rung_fence(gate_source):
    assert "create_folder" not in gate_source


def test_the_gate_SELF_PROVISIONS_its_document_and_names_no_pre_existing_one(gate_source):
    assert "create_document(" in gate_source
    assert "delete_document(" in gate_source
    upper = gate_source.upper().replace("CANARY_SUPPORT", "")
    assert "CANARY" not in upper
    # no token-shaped literal standing in for a real document
    assert not re.search(r'"(doc[cx]|Ehf|HXqm)[A-Za-z0-9]{18,}"', gate_source)


def test_both_deletions_are_RE_QUERIED_INDEPENDENTLY_never_taken_on_their_own_answer(
        gate_source):
    """And the two re-queries settle DIFFERENT things, which the gate says rather than blurs:
    the document's read refuses, so its absence is established; the file's does **not**, because
    a delete is trash and not purge — measured, recorded, and never asserted as a purge."""
    assert "_proven_gone" in gate_source
    assert "STILL RESOLVES" in gate_source
    assert "doc_gone" in gate_source and "file_after_delete" in gate_source
    assert "trash, not purge" in gate_source


def test_the_gate_does_NOT_pretend_to_purge_the_media_it_minted(gate_source):
    assert "media_residue" in gate_source
    assert "unpurgeable" in gate_source
    assert "media.delete" not in gate_source


def test_the_verdict_is_the_READERS_OWN_MARKDOWN_not_the_writes_echo(gate_source):
    assert "parse_docx_content" in gate_source
    assert "f\"[{ANCHOR_TEXT}]({linked.url})\" in markdown" in gate_source


def test_the_sentence_goes_through_the_PLAN_GATE_never_a_raw_call(gate_source):
    assert "dry_run(" in gate_source
    assert "plan.refusals" in gate_source
    assert "apply(plan" in gate_source


def test_the_gate_reuses_the_shipped_hash_check_and_commits_no_binary(gate_source):
    assert "sha256_of(" in gate_source
    assert "import hashlib" not in gate_source
    assert "def html_bytes(" in gate_source


def test_the_gate_pins_NO_lark_refusal_code(gate_source):
    numbers = re.findall(r"\b(1[0-9]{6})\b", gate_source)
    assert numbers == [], numbers


def test_the_gate_exercises_the_WRAPPER_TRAP_arm(gate_source):
    assert "put_file_in_document(" in gate_source
    assert "wrapper_block_id" in gate_source
    assert "authored.block_id != authored.wrapper_block_id" in gate_source
