"""The always-on half of the docx media-PLACEMENT gate — its DISCIPLINE, without credentials.

The gate is credential-gated and deselected by default, so its safety rules and the shape of
its measurement would otherwise be unverified on an ordinary ``pytest`` run. This file checks
the ones that can be checked statically:

* it skips **loudly** rather than passing quietly when credentials are absent;
* it writes **only** to a document it created, and names no pre-existing document, token or
  environment variable pointing at one;
* it deletes that document in a ``finally`` — and does **not** pretend to purge the media,
  which nothing can;
* **the placement verdict is read from the parent block's own ``children`` list**, never from
  a create's echo — an echo answers *what* was made, not *where*, so an arm that trusted it
  would assert nothing at all about placement;
* **all four measured cases are present** — a positive ``index``, ``index=0``, the default,
  and a **non-root ``parent_block_id``** — because the shipped sentences LD-470 writes rest on
  exactly those four, and a later edit must not be able to quietly drop one;
* the **wrapper trap** is measured on the wire: both ids typed from independent reads;
* it commits **no binary fixture** — the image is built from source in the file;
* it pins **no Lark refusal code** in an assertion, so a renumbering on their side cannot
  redden it.

This is the ``*_gate_offline`` companion pattern the rest of the write ring uses.
"""
import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tests" / "test_live_docx_media_placement_gate.py"


@pytest.fixture(scope="module")
def gate_source():
    return GATE.read_text(encoding="utf-8")


def test_the_gate_exists_and_carries_the_ring_marker(gate_source):
    assert "pytestmark = pytest.mark.live_write" in gate_source


def test_the_gate_skips_LOUDLY_when_credentials_are_absent(gate_source):
    assert "live_write_missing_reason()" in gate_source
    assert "pytest.skip(reason)" in gate_source
    assert "canary_support.load_env()" in gate_source


def test_the_gate_SELF_PROVISIONS_and_names_no_pre_existing_surface(gate_source):
    """The binding safety rule: it may only write to what it created — and for a media
    upload that matters twice over, because the residue an upload leaves cannot be undone
    even by deleting the document it was attached to."""
    assert "create_document(" in gate_source

    for name in ("LARKDOCIO_CANARY_DOC", "LARKDOCIO_BLOCKZOO_DOC", "LARKDOCIO_SCRATCH",
                 "LARKDOCIO_SHEET", "LARKDOCIO_COMMENT_ZOO_DOC"):
        assert name not in gate_source, (
            f"the gate references {name} — it must only touch files it created itself")
    for helper in ("canary_doc_url", "blockzoo_doc_url", "scratch_sheet_url"):
        assert helper not in gate_source, (
            f"the gate calls {helper}() — that is a pre-existing surface, not a disposable")

    for literal in re.findall(r"[\"']([A-Za-z0-9_-]{20,})[\"']", gate_source):
        assert not re.fullmatch(r"(?=.*[a-z])(?=.*[A-Z])(?=.*\d)[A-Za-z0-9]{22,34}", literal), (
            f"the gate carries what looks like a real document token: {literal!r}")


def test_the_gate_deletes_its_disposable_in_a_finally(gate_source):
    assert "finally:" in gate_source
    assert "delete_document(" in gate_source


def test_the_gate_DISCLOSES_the_media_residue_instead_of_pretending_to_purge_it(gate_source):
    """Four uploads mint four permanent tokens. No verb purges drive media, so a cleanup leg
    here would be a lie in the shape of hygiene; what the gate owes instead is a printed
    record of what it minted."""
    assert "media_residue" in gate_source
    assert "permanent" in gate_source.lower()
    for fake_purge in ("purge_media", "delete_media", "media.delete("):
        assert fake_purge not in gate_source, fake_purge


def test_the_placement_verdict_is_the_PARENT_BLOCKS_OWN_CHILDREN_LIST(gate_source):
    """The one thing this arm exists to measure, and the one way it can be measured.

    A create answers the block it made. It does not answer the order it was made into — so a
    gate asserting on the create's echo would be asserting that something was created, which
    was never in doubt, and would leave ``index`` unmeasured while looking green.
    """
    assert 'def _children(' in gate_source
    assert '.get("children")' in gate_source
    assert "writer.get_block(" in gate_source
    assert gate_source.count("_children(writer, doc_id") >= 5, (
        "every case must re-read the parent's children; a case that skips the re-read is "
        "not measuring placement")


def test_ALL_FOUR_measured_cases_are_present(gate_source):
    """The shipped sentences rest on these four. Dropping one silently would leave a shipped
    absolute standing on evidence that no longer exists."""
    assert "index=1" in gate_source, "the POSITIVE-index case is missing"
    assert "index=0" in gate_source, "the index=0 case is missing"
    assert "case 3: THE DEFAULT" in gate_source, "the default (index=-1) case is missing"
    assert "parent_block_id=bullet_id" in gate_source, "the NON-ROOT parent case is missing"
    # and the default case must really omit the argument rather than pass -1 by hand
    default_call = gate_source.split("appended = put_image_in_document(")[1].split(")")[0]
    assert "index=" not in default_call, (
        "the default case must let the signature's own default apply, not restate it")


def test_the_non_root_case_also_proves_the_ROOT_DID_NOT_MOVE(gate_source):
    """"It landed under the bullet" is only half the claim; the other half is that it did not
    also land at the root, which is what a caller reading the sentence will assume."""
    assert "root_before_case_4" in gate_source
    assert "root_after ==" in gate_source
    assert "not in root_after" in gate_source


def test_the_WRAPPER_TRAP_is_measured_on_the_wire(gate_source):
    """The id a file create hands back is a view wrapper. Both ids are typed here from
    independent reads, because the whole consequence for a caller is which id they hold."""
    assert "FILE_VIEW_WRAPPER_BLOCK_TYPE" in gate_source
    assert "FILE_BLOCK_TYPE" in gate_source
    assert "wrapper_block_id" in gate_source
    assert "wrapper.get(\"children\")" in gate_source


def test_the_gate_commits_no_binary_fixture(gate_source):
    """The image is built from source in the file, so nothing binary is committed and
    nothing binary is read."""
    assert "def png_bytes(" in gate_source
    assert "read_bytes()" not in gate_source
    for forbidden in ("b64decode", "print(payload"):
        assert forbidden not in gate_source, forbidden


def test_the_gate_pins_no_lark_refusal_code(gate_source):
    """Today's refusal numbers are quoted in prose, never asserted — the day Lark renumbers
    one, this gate must still be measuring the same thing."""
    for code in ("1770013", "1061002", "1770025", "1771001"):
        assert code not in gate_source, (
            f"the gate asserts or embeds the refusal code {code}; quote it in prose instead")
