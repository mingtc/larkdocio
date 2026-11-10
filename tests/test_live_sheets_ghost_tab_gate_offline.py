"""The always-on half of the ghost-tab gate — its DISCIPLINE, checked without credentials.

The gate is credential-gated and deselected by default, so its safety rules would otherwise be
unverified on an ordinary ``pytest`` run. This companion pins the ones that can be checked
statically:

* it is **READ-ONLY** — no write client, no write credentials, no create/delete, no apply;
* it skips **loudly** rather than passing quietly when credentials or the fixture URL are
  absent;
* it addresses **only the designated disposable read fixture** (via ``canary_support``), and
  names **no** pre-existing document token — in particular not the consumer's workbook, which
  this issue's evidence names and its gates must never touch;
* the ghost id it feeds the walk is a **synthetic, non-token** literal, so the gate cannot
  accidentally address a real tab of somebody's spreadsheet;
* it asserts the **skip arm AND a clean control**, because an arm that only ever sees a skip
  proves the walk skips, not that it can also come back whole.

The ``*_gate_offline`` companion pattern the rest of the ring uses.
"""
import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tests" / "test_live_sheets_ghost_tab_gate.py"

#: The workbook the consumer reported the defect on. Evidence, never a target — a gate that
#: named it would be reading somebody's real spreadsheet.
CONSUMER_WORKBOOK = "Example70c458e6bc847b78615b"


@pytest.fixture(scope="module")
def gate_source():
    return GATE.read_text(encoding="utf-8")


def test_the_gate_exists_and_carries_the_ring_marker(gate_source):
    assert "pytestmark = pytest.mark.live" in gate_source


def test_the_gate_skips_LOUDLY_when_credentials_or_the_fixture_are_absent(gate_source):
    """A silent pass on a missing credential is the failure mode a live gate must not have:
    the ring would look green while proving nothing."""
    assert "canary_support.load_env()" in gate_source
    assert "sheets_missing_reason()" in gate_source
    assert "pytest.skip(reason)" in gate_source


def test_the_gate_is_READ_ONLY(gate_source):
    """It reads a spreadsheet it does not own, so it must not be able to change it."""
    forbidden = ("SheetsWriteClient", "from_write_credentials", "LARK_WRITE_APP",
                 "batch_update", "put_values", "append_values", "create_spreadsheet",
                 "delete_spreadsheet", "dry_run", "apply(")
    for name in forbidden:
        assert name not in gate_source, (
            f"the ghost-tab gate references {name} — it is a READ-ONLY gate")


def test_the_gate_addresses_ONLY_the_designated_disposable_read_fixture(gate_source):
    """One target, reached through ``canary_support`` rather than a hard-coded url."""
    assert "canary_support.scratch_sheet_url()" in gate_source
    for helper in ("canary_doc_url", "blockzoo_doc_url", "comment_zoo"):
        assert helper not in gate_source, f"the gate reaches for {helper}() — wrong surface"


def test_the_gate_NEVER_names_the_consumers_workbook_or_any_real_token(gate_source):
    """The reported workbook is EVIDENCE. A gate that addressed it would be reading a real
    document to prove a library behavior — the one thing this issue's dependencies forbid."""
    assert CONSUMER_WORKBOOK not in gate_source
    for literal in re.findall(r"[\"']([A-Za-z0-9_-]{20,})[\"']", gate_source):
        assert not re.fullmatch(r"(?=.*[a-z])(?=.*[A-Z])(?=.*\d)[A-Za-z0-9]{22,34}", literal), (
            f"the gate carries what looks like a real document token: {literal!r}")


def test_the_ghost_id_the_gate_feeds_the_walk_is_SYNTHETIC(gate_source):
    """A short, obviously-fake id — never a plausible real tab of a real workbook."""
    match = re.search(r'GHOST_SHEET_ID = "([^"]+)"', gate_source)
    assert match, "the gate no longer names its synthetic ghost id in one place"
    ghost = match.group(1)
    assert re.fullmatch(r"[a-z0-9]{4,8}", ghost), (
        f"the ghost id {ghost!r} is not obviously synthetic")


def test_the_gate_asserts_BOTH_the_skip_arm_and_a_clean_control(gate_source):
    """An arm that only ever observes a skip cannot tell "the walk skips" from "the walk always
    reports skips". The control read must be there, and it must assert cleanliness."""
    assert "skipped_any is False" in gate_source
    assert "skip.code == 90215" in gate_source
    assert "book.accounted()" in gate_source
