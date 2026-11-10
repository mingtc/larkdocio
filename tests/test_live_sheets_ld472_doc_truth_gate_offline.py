"""The always-on half of the LD-472 sheets doc-truth gate — its DISCIPLINE, without credentials.

The gate is credential-gated and deselected by default, so its safety rules and the shape of
its measurement would otherwise be unverified on an ordinary ``pytest`` run. This companion
checks what can be checked statically, and it checks the things that would make the SHIPPED
SENTENCES unfounded if a later edit removed them:

* it skips **loudly** rather than passing quietly when credentials are absent;
* it writes **only** to a workbook it created, and names no pre-existing spreadsheet, token or
  environment variable pointing at one;
* it deletes that workbook in a ``finally`` and proves gone-ness by an **independent
  re-query**, never by the delete's own code;
* **both measurements are present, each with its control** — ``AddTab`` with no ``index``
  *and* ``index=len(tabs)``; a multi-cell ``a1_range`` *and* the single-cell anchor. Either
  half alone measures nothing: the placement claim needs the append control, and the
  refutation needs the shape that works;
* **the measurement wins.** The gate asserts what the docs now say rather than printing it, so
  a future run that disagrees with the shipped sentences reddens instead of being read past;
* it **discloses** the media residue rather than pretending to purge it — the refused
  multi-cell bind orphans a token by construction, which is the finding, not an accident;
* it commits **no binary fixture** (the PNG is built from source), and pins **no** Lark
  refusal code in an assertion, so a renumbering on their side cannot redden it — the codes
  are recorded in the evidence print.

This is the ``*_gate_offline`` companion pattern the rest of the write ring uses.
"""
import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tests" / "test_live_sheets_ld472_doc_truth_gate.py"


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
    assert "create_spreadsheet(" in gate_source

    for name in ("LARKDOCIO_CANARY_DOC", "LARKDOCIO_BLOCKZOO_DOC", "LARKDOCIO_SCRATCH",
                 "LARKDOCIO_SHEET", "LARKDOCIO_COMMENT_ZOO_DOC"):
        assert name not in gate_source, (
            f"the gate references {name} — it must only touch what it created itself")
    for helper in ("canary_doc_url", "blockzoo_doc_url", "scratch_sheet_url"):
        assert helper not in gate_source, (
            f"the gate calls {helper}() — that is a pre-existing surface, not a disposable")

    for literal in re.findall(r"[\"']([A-Za-z0-9_-]{20,})[\"']", gate_source):
        assert not re.fullmatch(r"(?=.*[a-z])(?=.*[A-Z])(?=.*\d)[A-Za-z0-9]{22,34}", literal), (
            f"the gate carries what looks like a real spreadsheet token: {literal!r}")


def test_the_gate_deletes_its_disposable_and_PROVES_gone_ness_independently(gate_source):
    assert "finally:" in gate_source
    assert "delete_spreadsheet(" in gate_source
    assert "spreadsheet_is_gone(" in gate_source, (
        "gone-ness must be proved by a re-query, never by the delete's own code")


def test_BOTH_HALVES_of_the_AddTab_measurement_are_present(gate_source):
    """A placement claim with no append control measures nothing: *first* is only meaningful
    against a run that also shows what *last* looks like."""
    assert 'AddTab(title="zz-no-index")' in gate_source, (
        "the no-index case is gone — that is the sentence the guide was corrected from")
    assert "index=len(tabs)" in gate_source, (
        "the append idiom the guide now hands over is no longer measured, so the guide would "
        "be teaching an unverified line")


def test_BOTH_HALVES_of_the_float_image_refutation_are_present(gate_source):
    """A refusal with no working control is indistinguishable from a broken call."""
    assert "A1:D10" in gate_source, "the multi-cell shape that is refuted is gone"
    assert "A1:A1" in gate_source, (
        "the single-cell control is gone — without it the refusal proves nothing about the "
        "range and everything about the run")


def test_the_MEASUREMENT_WINS_rather_than_being_printed_past(gate_source):
    """The issue's own rule: if the re-measurement disagrees with what is written, the
    measurement wins. That is only enforceable if the gate ASSERTS the shipped claims."""
    assert 'ev["no_index_position"] == [0]' in gate_source
    assert "append_idiom_position" in gate_source
    assert "assert multi_refusal" in gate_source


def test_the_gate_DISCLOSES_the_media_residue_instead_of_pretending_to_purge_it(gate_source):
    """The refused multi-cell bind orphans a token BY CONSTRUCTION — the upload precedes bind
    validation. A cleanup leg here would be a lie in the shape of hygiene."""
    assert "media_residue" in gate_source
    assert "orphan_file_token" in gate_source
    assert "permanent" in gate_source.lower()
    for fake_purge in ("purge_media", "delete_media", "media.delete("):
        assert fake_purge not in gate_source, fake_purge


def test_the_gate_commits_no_binary_fixture(gate_source):
    assert "def png_bytes(" in gate_source, "the PNG must be built from source in the file"
    assert not list(GATE.parent.glob("test_live_sheets_ld472_doc_truth_gate*.png"))


def test_the_gate_asserts_no_lark_refusal_number(gate_source):
    """Lark renumbers. The gate records the code in its evidence print and asserts only that
    the call FAILED — so a renumbering cannot redden the ring."""
    for line in gate_source.splitlines():
        stripped = line.strip()
        if not stripped.startswith("assert "):
            continue
        assert not re.search(r"\b13\d{5}\b|\b90\d{3}\b", stripped), (
            f"the gate asserts a Lark refusal number: {stripped}")
