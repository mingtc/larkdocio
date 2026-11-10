"""Offline guards for THE LD-481 GATE — the batched table fill and the raised cell cap.

NOT marked ``live_write``: these run in the default ``pytest -q`` with no creds and no
network. They are the automatable half of the gate's contract — they pin the *shape* of the
credential-gated gate (``tests/test_live_write_batched_table_fill_gate.py``) so a future edit
cannot quietly hollow it out. The binding round-trip itself (author the consumer's 216-cell
grid through the front door → count the API calls on the wire → read it back → teardown) runs
only under ``pytest -m live_write`` at QA with write creds.

Three things this gate must never lose, and each has a test below:

* **the grid is the CONSUMER'S** — 6 columns × 36 rows = 216 cells, past the old 200-cell cap
  and past the create endpoint's per-axis ceiling. A gate whose grid quietly shrank under the
  old cap would pass while testing nothing;
* **the pin is the COST CLASS, and it is family-agnostic** (re-cut by LD-578). The arm was
  written when the fill was ⌈cells/48⌉ ``batch_update`` calls; LD-482 lifted a lone
  in-envelope table into one ``/descendant`` call (D-96) and the old per-family pin then
  measured 0. The reason it existed is untouched — this grid once cost **463** calls — so what
  the arm now pins is that no route spends calls per cell, whatever family it uses. The
  superseded arithmetic keeps its own offline pin in ``tests/test_batched_table_fill.py``,
  where route 2 still ships, and the one-call **shape** is the LD-482 arm's question
  (``tests/test_live_write_one_call_table_gate.py``) — the two arms divide cost from shape so
  a future route change reddens only the arm whose question moved;
* **the call count is the pin, and the clock is not.** The measurement this change bought is
  *calls*, so a wall-clock threshold may never gate the suite — elapsed seconds are evidence
  printed for the Activity log and asserted on by nothing;
* **the verdict is a fresh read-back**, including **row-major cell order** at fixed probe
  points — a transposed fill would otherwise pass on cell *count* alone.
"""
from pathlib import Path

from larkdocio.write.client import MAX_BATCH_UPDATES_PER_CALL
from larkdocio.write.encode import MAX_CREATE_GRID_AXIS
from larkdocio.write.model import MAX_TABLE_CELLS

GATE_SRC = Path(__file__).resolve().parent / "test_live_write_batched_table_fill_gate.py"


def _src() -> str:
    return GATE_SRC.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# The ring's discipline — same marker, deselected by default, skips LOUDLY      #
# --------------------------------------------------------------------------- #

def test_the_gate_file_exists():
    assert GATE_SRC.exists(), f"the LD-481 batched-fill gate {GATE_SRC.name} must exist."


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


# --------------------------------------------------------------------------- #
# Disposables only — the gate creates its target and destroys it               #
# --------------------------------------------------------------------------- #

def test_the_gate_creates_its_own_document_and_never_names_a_configured_one():
    src = _src()
    assert "create_document(" in src, (
        "the gate must self-provision its document — it may never address a doc it did not "
        "create.")
    for forbidden in ("LARKDOCIO_CANARY_DOC", "LARK_DOC_URL", "SCRATCH_DOC"):
        assert forbidden not in src, (
            f"the gate names {forbidden} — a live write may only ever touch a document the "
            f"harness itself created.")


def test_the_gate_tears_down_in_a_finally():
    src = _src()
    assert "finally:" in src and "batch_delete(" in src and "delete_document(" in src, (
        "teardown must run on success AND failure, or a failing run leaves litter.")
    assert "assert emptied" in src, (
        "the gate must ASSERT the teardown worked — a best-effort cleanup nobody checks is "
        "how orphans accumulate.")


# --------------------------------------------------------------------------- #
# What THIS gate adds — the consumer's grid, the call count, the row order      #
# --------------------------------------------------------------------------- #

def test_the_gate_authors_the_CONSUMERS_OWN_grid():
    from test_live_write_batched_table_fill_gate import CELLS, COLS, ROWS

    assert (ROWS, COLS) == (36, 6), (
        "the gate must author the grid the bug report named — 6 columns × 36 rows.")
    assert CELLS == 216
    assert 200 < CELLS <= MAX_TABLE_CELLS, (
        "the grid must sit ABOVE the superseded 200-cell cap and inside the current one — "
        "a grid that fits under 200 would pass without exercising the supersession at all.")
    assert ROWS > MAX_CREATE_GRID_AXIS, (
        "the grid must also exceed the create endpoint's per-axis ceiling, so the growth "
        "path is part of what the measured call count covers.")


def test_the_gate_bounds_the_CALL_COUNT_and_nothing_else():
    from test_live_write_batched_table_fill_gate import CELLS, MAX_WRITE_API_CALLS

    assert MAX_WRITE_API_CALLS == 60, (
        "the bound is the one the issue set: ≤60 API calls for 216 cells, against the 463 "
        "the shipped path spent.")
    assert MAX_WRITE_API_CALLS < CELLS, (
        "a bound at or above one call per cell could not tell a batched fill from an "
        "unbatched one.")


def test_the_gate_pins_the_COST_CLASS_and_never_a_SUPERSEDED_CALL_FAMILY():
    """LD-578 — the reason survives, the call FAMILY moved.

    The arm used to assert ``len(batches) == 5`` — ⌈216/48⌉ ``blocks/batch_update`` calls.
    LD-482 then lifted a lone in-envelope table into **one** ``/descendant`` call (D-96), so
    for this grid that family is not on the wire at all and the pin measured **0**. LD-481's
    *reason* is untouched — the fill must never be per-cell again, it once cost 463 calls —
    so the pin is re-cut onto the **cost class**, family-agnostically: whatever endpoint the
    engine spells the fill with, authoring 216 cells may not spend calls that scale with
    cells.
    """
    from test_live_write_batched_table_fill_gate import (
        CELLS,
        MAX_MUTATING_WRITE_CALLS,
    )

    src = _src()
    assert "len(batches) == 5" not in src, (
        "the superseded pin is back: ⌈cells/48⌉ batched calls is route 2's arithmetic, and a "
        "216-cell table takes route 1 (one /descendant call). That arithmetic is pinned "
        "offline in tests/test_batched_table_fill.py, where route 2 still ships.")
    assert "mutating" in src, (
        "the gate must count the MUTATING calls — the family-agnostic cost measure that "
        "survives a route swap, which a per-family count provably did not.")
    assert 0 < MAX_MUTATING_WRITE_CALLS <= CELLS // 10, (
        f"the mutating bound must sit an order of magnitude under the cell count so any "
        f"per-cell route fails it; got {MAX_MUTATING_WRITE_CALLS} for {CELLS} cells.")
    assert "463" in src, (
        "the gate must keep the number that earned it — 463 calls for these 216 cells. A pin "
        "re-cut without its reason is the next reader's folklore "
        "(CLAUDE.md § House rules, supersession).")
    assert "LD-482" in src and "LD-578" in src, (
        "the gate must name the change that moved the family and the change that re-cut the "
        "pin, or the supersession is unreadable from the gate itself.")
    assert "per_cell_reads" in src, (
        "the gate must prove the per-cell get_block loop did not come back — the regression "
        "this whole change exists to prevent.")


def test_the_superseded_BATCH_ARITHMETIC_stays_pinned_OFFLINE_where_route_2_still_ships():
    """Nothing was lost by re-cutting the live pin: the arithmetic never lived only there."""
    fill_pin = GATE_SRC.parent / "test_batched_table_fill.py"
    src = fill_pin.read_text(encoding="utf-8")
    assert "MAX_BATCH_UPDATES_PER_CALL" in src and MAX_BATCH_UPDATES_PER_CALL == 48, (
        f"the ⌈cells/{MAX_BATCH_UPDATES_PER_CALL}⌉ batching arithmetic must stay pinned in "
        f"{fill_pin.name} — route 2 still ships for a mixed entry or a grid past the "
        f"one-call envelope, and that pin is what makes the live arm's re-cut lossless.")
    assert "ceil_cells_over_the_envelope" in src, (
        f"{fill_pin.name} must keep the explicit ⌈cells/envelope⌉ arithmetic test.")


def test_the_two_ARMS_DIVIDE_the_question_and_neither_restates_the_other():
    """LD-578 — this arm owns COST, the LD-482 arm owns SHAPE.

    Both arms author the same 216-cell grid, so without a stated division they drift into
    asserting each other's claim — and then a route change reddens both while only one of
    them has a question that actually changed. The division: **this** arm asks *how much does
    the consumer's grid cost* (calls of any family, per-cell absence), the **LD-482** arm asks
    *what shape is the call* (exactly one ``/descendant``, at the derived index, atomic on
    refusal).
    """
    src = _src()
    other_path = GATE_SRC.parent / "test_live_write_one_call_table_gate.py"
    other = other_path.read_text(encoding="utf-8")

    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("assert ") and "descendant" in stripped:
            raise AssertionError(
                f"the cost arm asserts on the /descendant SHAPE: {stripped!r}. That is the "
                f"LD-482 arm's pin ({other_path.name}); duplicating it here is how the "
                f"stale pin LD-578 fixed came to exist. Print it as evidence, assert nothing.")
    assert "descendant_calls" in other and "MAX_TABLE_WRITE_CALLS" in other, (
        f"{other_path.name} must keep the SHAPE pin — one /descendant call — since this arm "
        f"deliberately no longer carries it.")
    assert other_path.name[: -len(".py")] in src, (
        f"this arm must NAME {other_path.name} where it states the division, so a reader "
        f"following a route change finds the other half.")
    assert GATE_SRC.name[: -len(".py")] in other, (
        f"{other_path.name} must name this arm back — the division is only readable if both "
        f"halves state it.")


def test_the_gate_records_the_CLOCK_as_evidence_and_never_asserts_on_it():
    """AC5's own rule, pinned: no wall-clock assertion may gate the suite."""
    src = _src()
    assert "elapsed" in src, "the gate must measure elapsed seconds — it is the evidence."
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("assert ") and "elapsed" in stripped:
            raise AssertionError(
                f"a wall-clock assertion gates the suite: {stripped!r}. Elapsed time is "
                f"EVIDENCE for the Activity log; the pin is the CALL COUNT.")


def test_the_gate_authors_from_MARKDOWN_through_the_plan_gate():
    src = _src()
    assert "compose(" in src, (
        "the consumer hit this through compose() — the gate must enter the same way, not by "
        "hand-building typed content.")
    assert "dry_run(" in src and "apply(" in src, (
        "content must reach Lark only through dry_run → Plan → apply.")
    for authored_key in ('"row_size":', '"column_size":'):
        assert authored_key not in src, (
            f"the gate must not author {authored_key} itself — the grid property is the "
            f"encoder's business, and a gate that writes it is not testing the encoder.")


def test_the_gate_earns_its_verdict_from_a_FRESH_READ_BACK_in_ROW_MAJOR_ORDER():
    from test_live_write_batched_table_fill_gate import PROBE_POINTS

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
        "the gate must prove the write was purely additive — a fill that clobbered "
        "neighbouring content would otherwise pass.")
