"""The always-on half of the LD-477 hidden-tab READ-route gate — its DISCIPLINE, no credentials.

The gate is credential-gated and deselected by default, so its safety rules and the *shape* of
its measurement would otherwise be unverified on an ordinary ``pytest`` run. This companion
checks statically the things whose removal would leave the SHIPPED SENTENCE ("a read can tell a
hidden tab from a visible one, with no extra call and no write credentials") unfounded:

* it skips **loudly** when either credential pair is absent — and it names **both**, because the
  write pair only provisions while the **read** pair is the subject;
* it touches **only** a workbook it created; no environment variable naming a sheet, no
  token-shaped literal, no pre-existing surface;
* it deletes that workbook in a ``finally`` and proves gone-ness by an **independent re-query**;
* **the claim is made through a READ client.** A gate that read the visibility back through the
  write client would be re-measuring what already shipped and would prove nothing about the read
  route — this is the single assertion the whole issue rests on;
* **both cases are present.** ``hidden is True`` alone is half a measurement: without the
  visible tab answering an explicit ``False`` the run cannot distinguish "Lark reports
  visibility" from "Lark reports hiddenness and says nothing otherwise", which is exactly the
  distinction the ``None``-is-not-``False`` rule turns on;
* it asserts the **renderer stayed silent**, which is the half of this change that has no
  consent behind it and would move every consumer's goldens if it drifted.
"""
import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tests" / "test_live_sheets_hidden_tab_read_gate.py"


@pytest.fixture(scope="module")
def gate_source():
    return GATE.read_text(encoding="utf-8")


def test_the_gate_exists_and_carries_the_ring_marker(gate_source):
    assert "pytestmark = pytest.mark.live_write" in gate_source


def test_the_gate_skips_LOUDLY_and_names_BOTH_credential_pairs(gate_source):
    assert "canary_support.load_env()" in gate_source
    assert "live_write_missing_reason()" in gate_source
    assert "pytest.skip(reason)" in gate_source
    assert "read_creds_available()" in gate_source, (
        "the gate does not check the READ pair — its subject is the read leg, so a missing "
        "read credential must skip loudly rather than fail as a config error mid-run")


def test_the_gate_SELF_PROVISIONS_and_names_no_pre_existing_surface(gate_source):
    assert "create_spreadsheet(" in gate_source
    assert "disposable_title(" in gate_source

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


def test_the_CLAIM_IS_MADE_THROUGH_A_READ_CLIENT(gate_source):
    """The one thing this gate exists for.

    Reading the visibility back through ``SheetsWriteClient.query_tabs`` would re-measure a
    capability that shipped long ago and would say nothing at all about the read route.
    """
    assert "SheetsReadClient.from_read_credentials(" in gate_source
    assert re.search(r"reader\s*=\s*SheetsReadClient", gate_source)
    assert "reader.query_sheets(" in gate_source, (
        "the read leg no longer goes through the shipped read op")


def test_BOTH_CASES_are_asserted_hidden_AND_explicitly_visible(gate_source):
    assert "hidden is True" in gate_source, "the hidden case is gone"
    assert "hidden is False" in gate_source, (
        "the visible case is gone — without it the run cannot tell 'Lark reports visibility' "
        "from 'Lark reports only hiddenness', and the None-is-not-False rule turns on exactly "
        "that difference")


def test_the_gate_pins_that_the_RENDERER_STAYED_SILENT(gate_source):
    assert "render_spreadsheet(" in gate_source
    assert "rendered_mentions_hidden" in gate_source, (
        "nothing live checks that the rendered Markdown gained no hidden-tab marker — that is "
        "the output change no consent exists for")


def test_the_gate_mints_no_media_and_says_so(gate_source):
    for verb in ("put_float_image_in_sheet", "FloatImageMediaClient", "upload_media"):
        assert verb not in gate_source, (
            f"the gate calls {verb} — this arm is deliberately residue-free beyond the "
            "disposable it deletes")
    assert "RESIDUE:" in gate_source


def test_the_gate_asserts_no_lark_refusal_NUMBER(gate_source):
    """A renumbering on Lark's side must not redden a gate whose subject is a field."""
    assert not re.search(r"code\s*==\s*\d{4,}", gate_source)
