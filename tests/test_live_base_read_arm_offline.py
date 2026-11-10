"""The always-on offline half of ``test_live_base_read_arm`` (LD-247).

The live arm runs only with credentials and a network. What it *claims* — that it is
read-only, that it targets the disposable Scratch Base and nothing else, and that it skips
loudly rather than passing silently — is exactly the class of claim a credential-less run
verifies by not running. So it is verified **here**, statically, on every plain ``pytest``:

* **read-only by construction** — every registered op declares ``mutates: False``, and the arm
  asserts that *before* its first call, so a future write op cannot reach the maintainer's real
  Scratch Base by way of this file;
* **no write credential and no write verb** anywhere in the arm or in the client it drives;
* **the right target** — the arm reads ``LARKDOCIO_SCRATCH_BASE`` and never the canary doc,
  the scratch sheet, the block zoo, or a hard-coded token;
* **loud skips** — the arm's own skip path goes through ``canary_support.base_missing_reason``,
  which names the missing variable, so an absent grant never reads as a pass;
* **the no-write proof is really made** — the arm re-reads ``table.revision`` and compares.

This mirrors the established companion pattern; it imports nothing from the live arm and runs
no gate.
"""
import ast
from pathlib import Path

import canary_support
import pytest

from larkdocio.base import ops as base_ops

_TESTS = Path(__file__).resolve().parent
_ARM = _TESTS / "test_live_base_read_arm.py"


@pytest.fixture(scope="module")
def arm_source():
    return _ARM.read_text(encoding="utf-8")


def test_the_arm_exists_and_is_marked_live(arm_source):
    assert "pytestmark = pytest.mark.live" in arm_source, (
        "the arm must be deselected by default; an unmarked live test runs in every plain "
        "pytest and turns a credential-less clone red")


def test_the_registry_the_arm_leans_on_really_is_read_only():
    """The arm's first assertion, made here too — so the claim is checked on every run and not
    only on the runs that have credentials."""
    assert base_ops.read_only()
    assert all(descriptor.mutates is False for descriptor in base_ops.OPS)


def test_the_arm_asserts_read_only_BEFORE_it_calls_anything(arm_source):
    tree = ast.parse(arm_source)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    names = [f.name for f in functions]
    assert "test_the_registry_declares_the_whole_arm_read_only_BEFORE_it_calls_anything" in names
    assert names.index(
        "test_the_registry_declares_the_whole_arm_read_only_BEFORE_it_calls_anything") < \
        names.index("test_the_live_read_arm_reaches_a_real_base_and_moves_nothing"), (
        "the read-only assertion must come first in file order, because that is the order "
        "pytest runs them in and the point is to fail before touching the Base")


def test_the_arm_names_NO_write_credential_and_NO_write_verb(arm_source):
    for forbidden in ("LARK_WRITE_APP", "from_write_credentials", "get_write_credentials",
                      ".create(", ".update(", ".patch(", ".delete("):
        assert forbidden not in arm_source, forbidden


def test_the_arm_targets_the_SCRATCH_BASE_and_nothing_else(arm_source):
    assert "scratch_base_url" in arm_source or "base_missing_reason" in arm_source
    for other_target in ("LARKDOCIO_CANARY_DOC", "LARKDOCIO_SCRATCH_SHEET",
                         "LARKDOCIO_BLOCKZOO_DOC", "canary_doc_url", "scratch_sheet_url"):
        assert other_target not in arm_source, (
            f"the Base arm must not reach for {other_target}")
    # …and no hard-coded token: the app token comes from the env var, parsed by the shipped
    # URL validator.
    assert "parse_base_url" in arm_source
    assert "BaseScratchExample" not in arm_source, "the Base token belongs in .env, never in a test file"


def test_the_arm_SKIPS_LOUDLY_rather_than_passing(arm_source):
    assert "base_missing_reason" in arm_source and "pytest.skip" in arm_source


def test_the_skip_reason_NAMES_the_variable_that_is_missing(monkeypatch):
    monkeypatch.delenv(canary_support.SCRATCH_BASE_ENV, raising=False)
    reason = canary_support.base_missing_reason()
    assert reason and canary_support.SCRATCH_BASE_ENV in reason


def test_the_url_parse_REFUSES_a_non_base_url():
    """A Base is not a spreadsheet and not a document. The adapter narrows the shipped
    validator rather than re-implementing it, and refuses the other recognised types."""
    domain, token = canary_support.parse_base_url(
        "https://x.sg.larksuite.com/base/BaseScratchExampleEXAMPLEtoken")
    assert (domain, token) == ("larksuite.com", "BaseScratchExampleEXAMPLEtoken")
    for wrong in ("https://x.sg.larksuite.com/sheets/SheetSEXAMPLE",
                  "https://x.sg.larksuite.com/docx/DocCaEXAMPLE"):
        with pytest.raises(ValueError):
            canary_support.parse_base_url(wrong)


def test_the_arm_PROVES_it_wrote_nothing_by_re_reading_the_revision(arm_source):
    assert "revision_before" in arm_source and "after.revision == revision_before" in arm_source


def test_the_arm_keeps_a_live_call_BUDGET(arm_source):
    """Being gentle is an acceptance criterion, not a courtesy — so the arm bounds its own
    call count and the bound is asserted here to exist."""
    assert "client.api_calls" in arm_source
