"""The always-on offline half of ``test_live_docx_historical_read_gate`` (LD-410).

The gate runs only with write credentials and a network. What it claims **about itself** is
exactly the class of claim a credential-less run "verifies" by not running, so it is verified
here, on every plain ``pytest``:

* **Disposables only (D-12), by text.** The gate names no standing fixture anywhere — not the
  read canary, not either scratch surface, not either zoo — and hard-codes no document token.
* **Its subject is self-created and torn down** in a ``finally``, with gone-ness proved by an
  **independent re-query** rather than by the delete's own return code.
* **It is FALSIFIABLE by construction (D-05).** The gate must write a SECOND STATE and must
  assert the pinned body **differs** from the head body — an arm that only asserted "the pinned
  read returned blocks" would pass against a silently ignored parameter, which is the entire
  hazard this issue exists to fence. Both the second write and the inequality assertion are
  required here, statically.
* **It skips LOUDLY** without write credentials, and separately without READ credentials — the
  pinned read is a read, and borrowing the write pair for it would prove the wrong thing.
"""
import ast
from pathlib import Path

import pytest

_TESTS = Path(__file__).resolve().parent
_GATE = _TESTS / "test_live_docx_historical_read_gate.py"

#: Every standing fixture the gate must never address. Named here rather than in the gate, so
#: the list itself is not a string the gate carries.
STANDING_FIXTURES = (
    "LARKDOCIO_CANARY_DOC", "LARKDOCIO_WRITE_SCRATCH_DOC", "LARKDOCIO_SCRATCH_BASE",
    "LARKDOCIO_SCRATCH_SHEET", "LARKDOCIO_BLOCK_ZOO", "LARKDOCIO_COMMENT_ZOO",
)


@pytest.fixture(scope="module")
def gate_source():
    return _GATE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def gate_body(gate_source):
    """The gate's source WITHOUT its module docstring — the docstring names the fixtures the
    gate deliberately avoids, and a sweep that counted those would refuse the disclosure."""
    return gate_source.split('"""', 2)[-1]


def test_the_gate_is_MARKED_live_write_and_deselected_by_default(gate_source):
    assert "pytestmark = pytest.mark.live_write" in gate_source, (
        "an unmarked live gate runs in every plain pytest and turns a credential-less clone red")


def test_the_gate_NAMES_NO_STANDING_FIXTURE(gate_body):
    for standing in STANDING_FIXTURES:
        assert standing not in gate_body, f"the gate names a standing fixture: {standing}"


def test_the_gate_HARD_CODES_no_document_token(gate_source):
    """A 22-27 character token-shaped literal in a gate is a real document somewhere."""
    tree = ast.parse(gate_source)
    suspects = [
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and 22 <= len(node.value) <= 27 and node.value.isalnum()
    ]
    assert not suspects, f"token-shaped literal(s) in the gate: {suspects}"


def test_the_gate_CREATES_its_subject_and_DELETES_it_in_a_finally(gate_source):
    assert "wc.create_document(" in gate_source
    assert "finally:" in gate_source
    delete_at = gate_source.index("wc.delete_document(")
    finally_at = gate_source.index("finally:")
    assert finally_at < delete_at, "the delete is not inside the finally"


def test_goneness_is_proved_by_an_INDEPENDENT_RE_QUERY_not_by_the_deletes_return_code(
        gate_source):
    assert "wc.get_document(doc_id)" in gate_source
    assert 'row["file_absent_after_delete"] is True' in gate_source


def test_the_gate_WRITES_A_SECOND_STATE_or_it_could_not_falsify_anything(gate_source):
    """The load-bearing one. Two ``create_children`` calls, then an INEQUALITY assertion."""
    assert gate_source.count("wc.create_children(") == 2, (
        "a falsifiable pin arm needs TWO states; with one, the pinned read and the head read "
        "return the same body and the run proves nothing")
    assert 'row["pinned_texts"] != row["head_texts"]' in gate_source, (
        "the gate must assert the two bodies DIFFER — 'it returned blocks' is exactly what a "
        "silently ignored parameter does too (D-05)")


def test_the_gate_asserts_the_STATE_TWO_line_is_ABSENT_from_the_pinned_read(gate_source):
    assert "assert state_two not in row[\"pinned_texts\"]" in gate_source
    assert "assert state_one in row[\"pinned_texts\"]" in gate_source
    assert "assert state_two in row[\"head_texts\"]" in gate_source


def test_the_gate_re_measures_ALL_THREE_shipped_traps(gate_source):
    """The disclosures are only as good as the day they were measured; the gate re-measures
    them, so a Lark change makes the shipped words redden rather than quietly become false."""
    assert 'row["over_range_texts"] == row["head_texts"]' in gate_source, "over-range → head"
    assert 'row["meta_revision_under_a_pin"] == row["revision_at_state_two"]' in gate_source, (
        "the meta route ignoring the pin")
    # raw_content is fenced by NOT EXISTING on this library's surface — the gate cannot call
    # what is not there, and the offline suite asserts that absence instead
    # (tests/test_docx_historical_read.py).
    assert "raw_content" not in gate_source


def test_the_gate_proves_the_LOCAL_refusals_on_the_LIVE_client(gate_source):
    assert "for refused in (0, -1, -2, \"2\"):" in gate_source
    assert "HistoricalReadRefusedError" in gate_source


def test_the_gate_skips_LOUDLY_for_BOTH_credential_pairs(gate_source):
    assert "canary_support.live_write_missing_reason()" in gate_source
    assert "pytest.skip(reason)" in gate_source
    assert "no READ credentials in the environment" in gate_source, (
        "the pinned read is a READ; borrowing the write pair for it would prove the wrong "
        "thing and the doctrine forbids it")
