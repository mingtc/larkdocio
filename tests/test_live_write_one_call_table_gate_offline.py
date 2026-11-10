"""Offline guards for THE LD-482 GATE — the one-call table subtree.

NOT marked ``live_write``: these run in the default ``pytest -q`` with no creds and no
network. They are the automatable half of the gate's contract — they pin the *shape* of the
credential-gated gate (``tests/test_live_write_one_call_table_gate.py``) so a future edit
cannot quietly hollow it out. The binding round-trip itself (one batch, one ``/descendant``
call, a read-back of the live child order and the row-major cells, then the atomicity leg and
teardown) runs only under ``pytest -m live_write`` at QA with write creds and a caller-supplied
disposables folder.

Four things this gate must never lose, and each has a test below:

* **the grid is inside the ONE-CALL envelope** — a grid outside it would silently exercise the
  create-seed-grow-fill route and pass while testing nothing this issue changed;
* **the batch is MIXED** — the binding gate is positional, and a table alone in its batch
  cannot show the failure mode LD-453 repaired. Two entries, two anchors, and the read-back
  asserts each landed beside **its own**;
* **the verdict is a fresh read-back**, including the live child ORDER and the row-major cell
  order at fixed probe points — a transposed or misplaced table would otherwise pass on cell
  count alone;
* **atomicity is measured, not reasoned** — a subtree one cell past the envelope is refused
  and the document is read back to prove nothing was created, with a control one cell inside
  it so the boundary is attributable to the envelope.

**LD-496 added a fifth, and it is the one that makes the positional leg DISCRIMINATE.** As
first authored the gate seeded ``TABLE_ANCHOR`` last, so the index the engine derived
coincided with the append position and a route that ignored ``index`` entirely would have read
back identically — the assertion passed either way, and the observed order was never printed.
So the seed now carries a **trailing block after ``TABLE_ANCHOR``**, the read-back asserts the
table landed **between** its anchor and that trailing block, and the ``index`` integer is read
off the ``/descendant`` request body on the wire and printed alongside the live child order.
"""
from pathlib import Path

import pytest

import canary_support
from larkdocio.write.client import MAX_DESCENDANTS_PER_CALL
from larkdocio.write.encode import MAX_ONE_CALL_TABLE_CELLS, table_descendants

GATE_SRC = Path(__file__).resolve().parent / "test_live_write_one_call_table_gate.py"


def _src() -> str:
    return GATE_SRC.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# The ring's discipline — same marker, deselected by default, skips LOUDLY      #
# --------------------------------------------------------------------------- #

def test_the_gate_file_exists():
    assert GATE_SRC.exists(), f"the LD-482 one-call table gate {GATE_SRC.name} must exist."


def test_the_gate_is_marked_live_write_and_conformance():
    src = _src()
    assert "pytest.mark.live_write" in src, (
        "the gate must carry the `live_write` marker so it stays deselected by the default "
        "addopts and joins the same ring as W0/W1/W2/W3/S2.")
    assert "pytest.mark.conformance" in src, (
        "a gate pinning measured external truth is conformance-tier "
        "(process/doctrine/conformance-tier.md § A.4).")


def test_the_gate_skips_loudly_when_write_creds_are_unset():
    src = _src()
    assert "live_write_missing_reason" in src and "pytest.skip" in src, (
        "the gate must gate on canary_support.live_write_missing_reason() and pytest.skip "
        "— never run silently past absent creds.")


def test_the_gate_names_its_DESTINATION_and_never_defaults_into_the_apps_own_space():
    src = _src()
    assert src.count("require_disposables_folder()") == 2, (
        "every leg that creates a document must ask for the caller-supplied destination — "
        "the rule is that nothing this suite creates lands in the application's own space.")
    assert "folder_token=dest_folder" in src, (
        "the destination must be PASSED to create_document, not merely looked up.")


def test_the_gates_SKIP_PATH_fires_loudly_when_the_disposables_folder_is_unset(monkeypatch):
    """**The proof that a parked live half is parked and not silently green.**

    With ``LARKDOCIO_DISPOSABLES_FOLDER`` unset, a harness that creates objects must skip with
    a message that NAMES the variable. This drives the real helper both legs call, so the
    gate's own behaviour is what is demonstrated — not a paraphrase of it.
    """
    monkeypatch.delenv(canary_support.DISPOSABLES_FOLDER_ENV, raising=False)
    assert canary_support.disposables_folder() is None
    reason = canary_support.disposables_folder_missing_reason()
    assert reason and canary_support.DISPOSABLES_FOLDER_ENV in reason, reason
    # `pytest.skip` raises `Skipped`, which derives from BaseException — so `raises(Exception)`
    # here would NOT catch it and this test would itself be reported as skipped, which is the
    # very failure mode it exists to rule out. Named explicitly for that reason.
    from _pytest.outcomes import Skipped

    with pytest.raises(Skipped) as skipped:
        canary_support.require_disposables_folder()
    assert canary_support.DISPOSABLES_FOLDER_ENV in str(skipped.value), (
        "the skip message does not name the variable, so a skipped run reads as a pass")


# --------------------------------------------------------------------------- #
# Disposables only — the gate creates its targets and destroys them             #
# --------------------------------------------------------------------------- #

def test_the_gate_creates_its_own_documents_and_never_names_a_configured_one():
    src = _src()
    assert src.count("create_document(") == 2, (
        "both legs must self-provision — neither may address a doc it did not create.")
    for forbidden in ("LARKDOCIO_CANARY_DOC", "LARK_DOC_URL", "SCRATCH_DOC"):
        assert forbidden not in src, (
            f"the gate names {forbidden} — a live write may only ever touch a document the "
            f"harness itself created.")


def test_the_gate_tears_down_in_a_finally():
    src = _src()
    assert src.count("finally:") == 2 and "delete_document(" in src, (
        "teardown must run on success AND failure in BOTH legs, or a failing run leaves "
        "litter.")
    assert "assert emptied" in src, (
        "the authoring leg must ASSERT its restore worked — a best-effort cleanup nobody "
        "checks is how orphans accumulate.")


# --------------------------------------------------------------------------- #
# What THIS gate adds — the envelope, the mixed batch, the order, the atomicity  #
# --------------------------------------------------------------------------- #

def test_the_gate_authors_a_grid_INSIDE_the_one_call_envelope():
    from test_live_write_one_call_table_gate import CELLS, COLS, ROWS

    assert (ROWS, COLS) == (36, 6), (
        "the gate must author the grid the consumer reported and the spike measured — "
        "6 columns × 36 rows, the one that went in as a single 0.82 s call.")
    assert CELLS == 216 <= MAX_ONE_CALL_TABLE_CELLS, (
        "a grid outside the envelope would take the OTHER route and this gate would pass "
        "while testing nothing it exists to test.")
    assert table_descendants(CELLS) == 433 <= MAX_DESCENDANTS_PER_CALL


def test_the_gate_bounds_the_TABLES_calls_at_exactly_one():
    from test_live_write_one_call_table_gate import MAX_TABLE_WRITE_CALLS

    assert MAX_TABLE_WRITE_CALLS == 1, (
        "the claim is ONE call for the whole subtree; a bound with slack could not tell a "
        "one-call construction from a two-call one.")


def test_the_gate_proves_the_grow_and_fill_route_did_not_come_back():
    src = _src()
    assert "grow_or_fill" in src and "/descendant" in src, (
        "the gate must count the route by URL on the wire — a fallback to create-then-fill "
        "would otherwise pass on the read-back alone.")


def test_the_gate_applies_a_MIXED_batch_and_checks_BOTH_landed_beside_their_OWN_anchor():
    src = _src()
    assert src.count("InsertRequest(") == 2, (
        "positional conformance is the binding gate and a table alone in its batch cannot "
        "show the same-parent drift LD-453 repaired — the batch must be mixed.")
    assert "order.index(marker_id) == order.index(marker_anchor_id) + 1" in src
    assert "order.index(table_id) == order.index(table_anchor_id) + 1" in src, (
        "the positional verdict must be read off the LIVE child order, not inferred from "
        "the rendered Markdown.")


# --------------------------------------------------------------------------- #
# LD-496 — the positional leg must DISCRIMINATE, and print what it saw          #
# --------------------------------------------------------------------------- #

def test_the_gate_seeds_a_TRAILING_block_AFTER_the_table_anchor():
    """Without it the sent index IS the append position and the gate settles nothing."""
    from test_live_write_one_call_table_gate import SUFFIX, TABLE_ANCHOR, TRAILING_TEXT

    assert TRAILING_TEXT and SUFFIX in TRAILING_TEXT, (
        "every block this gate seeds must carry the run's own suffix, or teardown cannot "
        "prove it removed what it wrote.")
    assert TRAILING_TEXT != TABLE_ANCHOR

    src = _src()
    # …to the seed literal's own closing bracket — the nested `elements: [...]` inside the
    # heading block carries brackets of its own, so a naive split on "]" stops too early.
    seed = src.split("seed = [", 1)[1].split("\n    ]", 1)[0]
    assert "text_block(TABLE_ANCHOR)" in seed and "text_block(TRAILING_TEXT)" in seed, (
        "the trailing block must be part of the SEED — a block added later would not have "
        "existed at the moment the /descendant index was derived.")
    assert seed.index("text_block(TRAILING_TEXT)") > seed.index("text_block(TABLE_ANCHOR)"), (
        "the trailing block must be seeded AFTER the table's anchor; seeded before it, the "
        "anchor is last again and the index still coincides with the append position.")


def test_the_gate_asserts_the_table_landed_BETWEEN_its_anchor_and_the_trailing_block():
    src = _src()
    assert "order.index(trailing_id) == order.index(table_id) + 1" in src, (
        "the discriminating assertion: a route that ignored `index` and appended would put "
        "the table AFTER the trailing block, and only this assertion would notice.")
    assert "order.index(table_id) == order.index(table_anchor_id) + 1" in src, (
        "the positional verdict must still be read off the LIVE child order.")


def test_the_gate_reads_the_WIRE_index_off_the_descendant_body_and_pins_it_POSITIVE():
    src = _src()
    assert "descendant_indexes" in src and "json.loads" in src, (
        "the `index` integer is the wire half of LD-482's AC2 — the counting opener must "
        "record it off the request BODY, not merely the (method, url) pair.")
    assert "wire_index > 0" in src, (
        "`index: -1` is what every capture behind this route used; the gate exists to "
        "measure a POSITIVE one, so it must assert the sign.")


def test_the_evidence_line_PRINTS_the_live_order_and_the_wire_index():
    src = _src()
    printed = src.split('"\\n[live_write:LD482-one-call-table-gate] "', 1)[1]
    assert "live_order=" in printed, (
        "`evidence['live_order']` was collected and discarded — a verdict nobody can audit "
        "from the run's output is not evidence.")
    assert "descendant_index=" in printed, (
        "the index actually sent must appear in the evidence line.")
    assert "order_ok=True" not in src, (
        "a hard-coded `order_ok=True` prints the same string whatever happened.")


def test_the_gate_authors_from_MARKDOWN_through_the_plan_gate():
    src = _src()
    assert "compose(" in src, (
        "the consumer meets this through compose() — the gate must enter the same way.")
    assert "dry_run(" in src and "apply(" in src, (
        "content must reach Lark only through dry_run → Plan → apply.")
    for authored_key in ('"row_size":', '"column_size":'):
        assert authored_key not in src, (
            f"the gate must not author {authored_key} itself — the grid property is the "
            f"encoder's business, and a gate that writes it is not testing the encoder.")


def test_the_gate_earns_its_verdict_from_a_FRESH_READ_BACK_in_ROW_MAJOR_ORDER():
    from test_live_write_one_call_table_gate import PROBE_POINTS

    src = _src()
    assert "_download(doc_id)" in src, (
        "the verdict must come from re-downloading through the reader, never from the "
        "write's own success code.")
    assert "row_size" in src and "column_size" in src, (
        "the gate must assert the LIVE grid property, so a table created short cannot pass "
        "on Markdown alone.")
    assert PROBE_POINTS == {0: "h0", 6: "r1c0", 108: "r18c0", 215: "r35c5"}, (
        "the probe points are the spike's own — first cell, first cell of row 1, a cell deep "
        "in the middle, and the last cell. Each catches a different transposition.")
    assert "ndiff" in src, (
        "the gate must prove the write was purely additive — a table that clobbered "
        "neighbouring content would otherwise pass.")


def test_the_ATOMICITY_leg_measures_the_boundary_and_reads_back_that_NOTHING_landed():
    src = _src()
    assert "MAX_ONE_CALL_TABLE_CELLS + 1" in src, (
        "the refusal must be provoked ONE cell past the envelope — a wildly oversized body "
        "would prove only that something big fails.")
    assert "assert not _tables(tree_after)" in src, (
        "atomicity is the claim that a refused subtree leaves NOTHING; it has to be read "
        "back, not inferred from the error.")
    assert "the control" in src and "control_cells" in src, (
        "a refusal with no passing control cannot attribute the boundary to the envelope.")


def test_the_gate_records_the_CLOCK_as_evidence_and_never_asserts_on_it():
    """The house rule, pinned: no wall-clock assertion may gate the suite."""
    src = _src()
    assert "elapsed" in src, "the gate must measure elapsed seconds — it is the evidence."
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("assert ") and "elapsed" in stripped:
            raise AssertionError(
                f"a wall-clock assertion gates the suite: {stripped!r}. Elapsed time is "
                f"EVIDENCE for the Activity log; the pin is the CALL COUNT.")
