"""The always-on half of the FLOAT-image gate — its DISCIPLINE, without credentials.

The gate is credential-gated and deselected by default, so its safety rules would otherwise be
unverified on an ordinary ``pytest`` run. This file checks the ones that can be checked
statically:

* it skips **loudly** rather than passing quietly when credentials are absent;
* it writes **only** to a workbook it created, and names no pre-existing spreadsheet, token or
  environment variable pointing at one;
* it deletes that workbook in a ``finally``, proves gone-ness by an **independent re-query**
  rather than by the delete's own ``code:0`` — and does **not** pretend to purge the media,
  which nothing can;
* every verdict it asserts is a **fresh ``float_images/query``** — for the bind and for the
  removal alike — and it demonstrates the route's central hazard live, by asserting the tab is
  still empty after an upload of its own;
* it reuses the shipped ``verify_round_trip`` / ``sha256_of`` rather than re-deriving a hash
  check;
* it commits **no binary fixture** — the image is built from source in the file;
* it pins **no Lark refusal code** in an assertion, so a renumbering on their side cannot
  redden it — the invented-token control records what came back and asserts only that it
  failed and that no phantom appeared;
* it **never retries** the bind, which is the highest-consequence disclosure on this route.

This is the ``*_gate_offline`` companion pattern the rest of the write ring uses.
"""
import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tests" / "test_live_sheets_float_image_gate.py"


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
    """The binding safety rule (D-12): it may only write to what it created — and for a route
    that mints media it matters twice over, because the residue cannot be undone even by
    trashing the workbook it was attached to."""
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


def test_the_gate_LEDGERS_the_media_residue_instead_of_pretending_to_purge_it(gate_source):
    """No verb purges drive media, so a cleanup leg here would be a lie in the shape of
    hygiene. What the gate owes instead is a printed record of every token minted — and this
    route mints TWO per run, because it demonstrates the unbound upload as well."""
    assert "media_residue" in gate_source
    assert gate_source.count('evidence["media_residue"].append(') == 2, (
        "both minted tokens must be ledgered — the deliberately unbound one as well as the "
        "bound one, since neither can ever be cleaned up")
    assert "permanent" in gate_source.lower()
    for fake_purge in ("purge_media", "delete_media", "media.delete("):
        assert fake_purge not in gate_source, fake_purge


def test_every_verdict_is_a_FRESH_QUERY_never_a_calls_own_code_zero(gate_source):
    """The route's whole contract. The gate re-queries for the bind AND for the removal, and
    it proves the hazard rather than reciting it: after an upload of its own, the tab is
    asserted still empty."""
    assert gate_source.count("query_float_images(") >= 5, gate_source.count(
        "query_float_images(")
    assert 'evidence["query_after_upload_only"] == []' in gate_source
    assert "remove_float_image_from_sheet(" in gate_source
    assert "assert writer.query_float_images(token, sheet_id) == []" in gate_source


def test_the_gate_asserts_the_upload_is_parented_on_the_WORKBOOK(gate_source):
    """The docx trap, held live: ``parent_node`` is the spreadsheet token, never the tab."""
    assert "parent_node=token" in gate_source
    assert "parent_node=sheet_id" not in gate_source


def test_the_gate_NEVER_RETRIES_the_bind(gate_source):
    """The highest-consequence disclosure on this route: a refusal here can arrive as an HTTP
    500 saying *retry later*. A gate that looped would be teaching the opposite."""
    assert gate_source.count("create_float_image(") == 1
    for loop in ("for attempt", "while True", "retry(", "range(3)"):
        assert loop not in gate_source, loop


def test_the_hash_check_is_the_SHIPPED_one(gate_source):
    """Reused, never re-derived — the gate imports the library's digest helper instead of
    reaching for hashlib."""
    assert "sha256_of" in gate_source
    assert "hashlib" not in gate_source


def test_the_gate_proves_the_BYTES_SURVIVE_the_removal(gate_source):
    """The residue disclosure is a claim about Lark, so the gate measures it rather than
    assuming it: after the float image is removed, the media token must still download."""
    assert "bytes_survive_removal" in gate_source


def test_the_gate_commits_no_binary_fixture(gate_source):
    """The image is built from source in the file, so nothing binary is committed and
    nothing binary is read."""
    assert "def png_bytes(" in gate_source
    assert "read_bytes()" not in gate_source
    for forbidden in ("b64decode", ".decode(", "print(payload"):
        assert forbidden not in gate_source, forbidden


def test_the_gate_pins_no_lark_refusal_code(gate_source):
    """Today's refusal numbers are quoted in prose, never asserted — the day Lark renumbers
    one, this gate must still be measuring the same thing. That matters most here: the
    mis-typed refusal is named by number all over this issue's prose, and NOT in this file."""
    assert "invented_token_refused" in gate_source
    for code in ("1315203", "1061002", "90202", "90215", "1310249"):
        assert code not in gate_source, (
            f"the gate asserts or embeds the refusal code {code}; quote it in prose instead")
