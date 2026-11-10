"""The always-on half of the restructure gate — its DISCIPLINE, checked without credentials.

The gate is credential-gated and deselected by default, so the rules that make it worth
running would otherwise be unverified on an ordinary ``pytest`` run. The **behaviour** it
exercises is already pinned offline — the shipped recipe it mirrors runs end to end under the
guide-recipe harness, where insert-before-delete is proven on the offline document's own
revision history — so what this companion pins is the part only a shape check keeps honest:

* it skips **loudly** rather than passing quietly when write credentials are absent;
* it asserts the **ORDER off a fresh READ**, not off the applies' outcomes. This is the whole
  reason the arm exists: a fully-applied, refusal-free log is compatible with a document in
  the wrong order, because order is the one thing a log does not describe;
* it asserts the **other half** too — the ids the longest common subsequence left alone are
  still in the document, so a gate cannot pass by deleting and re-making everything;
* the LCS it runs is **sliced out of the shipped recipe**, never re-implemented here: a second
  implementation would agree with itself and prove nothing about what a consumer pastes;
* the comments **READ** is asserted (the leg the recipe's step 1 turns on) while the comment
  **CREATE** is deliberately not — Lark answers its own ``2200 Internal Error`` on it
  intermittently, and a gate a server-side flake can fail is a gate nobody trusts;
* it targets **only** a document it creates itself, empties it in a ``finally``, and proves
  zero orphans by an independent **re-query** rather than by a delete's return code.

This is the ``*_gate_offline`` companion pattern the rest of the write ring uses.
"""
import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tests" / "test_live_restructure_gate.py"


@pytest.fixture(scope="module")
def gate_source():
    return GATE.read_text(encoding="utf-8")


def test_the_gate_exists_and_carries_the_ring_marker(gate_source):
    assert "pytestmark = pytest.mark.live_write" in gate_source


def test_the_gate_skips_LOUDLY_when_credentials_are_absent(gate_source):
    """A silent pass on a missing credential is the failure mode a live gate must not have:
    the ring would look green while proving nothing."""
    assert "live_write_missing_reason()" in gate_source
    assert "pytest.skip(reason)" in gate_source
    assert "canary_support.load_env()" in gate_source


def test_the_gate_names_no_pre_existing_document(gate_source):
    """D-12: a document this arm creates itself, and nothing else. A gate that could be
    pointed at the canary, the write scratch doc or a real document by an environment
    variable is one edit away from writing where it must not."""
    for forbidden in ("LARKDOCIO_WRITE_SCRATCH_DOC", "LARKDOCIO_CANARY_DOC",
                      "LARKDOCIO_BLOCKZOO_DOC", "LARKDOCIO_COMMENT_ZOO_DOC"):
        assert forbidden not in gate_source, forbidden
    assert "docx_ledger.disposable(" in gate_source


def test_the_gate_tears_down_in_a_finally_and_proves_zero_orphans_by_REFETCH(gate_source):
    assert "finally:" in gate_source
    assert "rt.empty_document(" in gate_source
    assert "docx_ledger.close_out(" in gate_source
    assert "report.raise_if_orphans()" in gate_source


def test_the_ORDER_is_asserted_off_a_FRESH_READ_and_not_off_the_apply_outcomes(gate_source):
    """The claim the arm exists for. ``_ordered_steps`` re-downloads through the shipped
    reader; the final assertion compares its answer to the desired order."""
    assert "def _ordered_steps(document_id):" in gate_source
    assert "rt.download(document_id)" in gate_source
    assert 'evidence["after"] == DESIRED' in gate_source
    # …and the read that produced it is taken AFTER the deletes, not reused from before them.
    after_deletes = gate_source.index("removal_log = apply(")
    assert gate_source.index('evidence["after"]', after_deletes) > after_deletes


def test_the_IDENTITY_half_is_asserted_too(gate_source):
    """A reorganisation that re-created everything would satisfy an order check and destroy
    every anchor in the document. The surviving ids are what separates the two."""
    assert "surviving == [b for b in desired_ids if b in kept]" in gate_source
    assert "anchored to it, is gone" in gate_source


def test_the_LCS_is_SLICED_OUT_OF_THE_SHIPPED_RECIPE_not_re_implemented(gate_source):
    """One definition, and the live arm runs the consumer's copy of it."""
    assert "def _guide_lcs():" in gate_source
    assert 'gr.recipe_sources(RESTRUCTURE_SLUG)' in gate_source
    assert 'source.index("def longest_common_subsequence(")' in gate_source
    # The gate defines no LCS of its own — only the slice's own exec may bind that name.
    assert not re.search(r"^def longest_common_subsequence\(", gate_source, re.M)


def test_the_INSERT_precedes_the_DELETE_in_the_arm_itself(gate_source):
    """The ordering the whole discipline turns on: the failure it prevents is a hole."""
    inserts = gate_source.index("log = apply(plan, write_client, document_id=document_id)")
    deletes = gate_source.index("removal_log = apply(")
    assert inserts < deletes
    # …and the duplication state between them is asserted, so the ordering is observed rather
    # than merely written in that order.
    assert "len(mid) == len(STEPS) + 1" in gate_source


def test_the_comments_READ_is_asserted_and_the_flaky_CREATE_is_NOT(gate_source):
    assert "assert review.available, review.unavailable_reason" in gate_source
    assert "allow_partial=True)" in gate_source
    assert "2200 Internal" in gate_source, (
        "the reason the create is not asserted must be written down, or the next reader "
        "reads a missing assertion as an oversight")


def test_the_gate_asserts_the_removed_payload_on_every_delete(gate_source):
    """A delete with no ``removed_payload`` is a destructive edit with no record — the one
    thing this arm must not normalise, since a reorganisation deletes by design."""
    assert "entry.removed_payload for entry in removal_log.applied" in gate_source
