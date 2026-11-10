"""The always-on half of the in-cell image gate — its DISCIPLINE, without credentials.

The gate is credential-gated and deselected by default, so its safety rules would otherwise be
unverified on an ordinary ``pytest`` run. This file checks the ones that can be checked
statically:

* it skips **loudly** rather than passing quietly when credentials are absent;
* it writes **only** to a workbook it created, and names no pre-existing spreadsheet, token or
  environment variable pointing at one;
* it deletes that workbook in a ``finally``, proves gone-ness by an **independent re-query**
  rather than by the delete's own ``code:0`` — and does **not** pretend to purge the media,
  which nothing can;
* the verdict it asserts is an **independent read-back** of the cell, not a call's own answer;
* it reuses the shipped ``verify_round_trip`` / ``sha256_of`` rather than re-deriving a hash
  check;
* it commits **no binary fixture** — the image is built from source in the file;
* it pins **no Lark refusal code** in an assertion, so a renumbering on their side cannot
  redden it — the bad-tab control records what came back and asserts only that it failed;
* it exercises the **clear** as what it is, an ordinary ``""`` value write, and never reaches
  for a delete verb that does not exist.

This is the ``*_gate_offline`` companion pattern the rest of the write ring uses.
"""
import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tests" / "test_live_sheets_in_cell_image_gate.py"


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
    """The binding safety rule: it may only write to what it created — and for a route that
    mints media it matters twice over, because the residue cannot be undone even by trashing
    the workbook it was stored in."""
    assert "create_spreadsheet(" in gate_source

    for name in ("LARKDOCIO_CANARY_DOC", "LARKDOCIO_BLOCKZOO_DOC", "LARKDOCIO_SCRATCH",
                 "LARKDOCIO_SHEET", "LARKDOCIO_COMMENT_ZOO_DOC"):
        assert name not in gate_source, (
            f"the gate references {name} — it must only touch files it created itself")
    for helper in ("canary_doc_url", "blockzoo_doc_url", "scratch_sheet_url"):
        assert helper not in gate_source, (
            f"the gate calls {helper}() — that is a pre-existing surface, not a disposable")

    for literal in re.findall(r"[\"']([A-Za-z0-9_-]{20,})[\"']", gate_source):
        assert not re.fullmatch(r"(?=.*[a-z])(?=.*[A-Z])(?=.*\d)[A-Za-z0-9]{22,34}", literal), (
            f"the gate carries what looks like a real spreadsheet token: {literal!r}")


def test_the_gate_deletes_its_disposable_in_a_finally_and_PROVES_it_gone(gate_source):
    """A ``code:0`` from a delete means accepted, not gone. The proof is a re-query."""
    assert "finally:" in gate_source
    assert "delete_spreadsheet(" in gate_source
    assert "confirmed_gone" in gate_source
    assert "spreadsheet_is_gone(" in gate_source


def test_the_gate_DISCLOSES_the_media_residue_instead_of_pretending_to_purge_it(gate_source):
    """No verb purges drive media, so a cleanup leg here would be a lie in the shape of
    hygiene. What the gate owes instead is a printed record of what was minted — and on this
    route it is Lark that mints it, which is the part a reader will not expect."""
    assert "media_residue" in gate_source
    assert "permanent" in gate_source.lower()
    for fake_purge in ("purge_media", "delete_media", "media.delete("):
        assert fake_purge not in gate_source, fake_purge


def test_the_verdict_is_an_INDEPENDENT_read_back_of_the_cell(gate_source):
    """``code:0`` proves acceptance and nothing else — the gate must re-read the cell itself
    rather than trusting the op's word or the write's echo."""
    assert "writer.read_value_range(" in gate_source
    assert 'cell.get("fileToken")' in gate_source


def test_the_hash_check_is_the_SHIPPED_one(gate_source):
    """Reused, never re-derived — the gate imports the library's digest helper instead of
    reaching for hashlib."""
    assert "sha256_of" in gate_source
    assert "hashlib" not in gate_source


def test_the_gate_exercises_the_CLEAR_as_an_ordinary_value_write(gate_source):
    """There is no delete verb for an in-cell image, and the gate must not imply one."""
    assert '[[""]]' in gate_source
    for invented in ("delete_image", "clear_image", "remove_image"):
        assert invented not in gate_source, invented


def test_the_gate_commits_no_binary_fixture(gate_source):
    """The image is built from source in the file, so nothing binary is committed and
    nothing binary is read."""
    assert "def png_bytes(" in gate_source
    assert "read_bytes()" not in gate_source
    for forbidden in ("b64decode", ".decode(", "print(payload"):
        assert forbidden not in gate_source, forbidden


def test_the_gate_pins_no_lark_refusal_code(gate_source):
    """Today's refusal numbers are quoted in prose, never asserted — the day Lark renumbers
    one, this gate must still be measuring the same thing."""
    assert "bad_tab_refused" in gate_source
    for code in ("90215", "90202", "1061002", "1315203", "1310249"):
        assert code not in gate_source, (
            f"the gate asserts or embeds the refusal code {code}; quote it in prose instead")
