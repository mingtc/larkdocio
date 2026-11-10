"""Offline red-then-green proof of THE values-leg surgical differ (LD-113).

NOT marked ``live_write`` — these are pure fixture-matrix unit tests that run in the
default ``pytest -q`` with no creds and no network. They are the automatable heart of
the Sheets value-write gate's **test-rigor amplifier**: the live values-leg round-trip
(``tests/test_live_sheets_write_gate.py``) proves a value write is **surgical** by
diffing the whole **used-range value matrix** before/after and asserting **only the
target range changed**. That claim is only as trustworthy as the differ behind it, so
these tests prove the differ itself **red-then-green** on hand-authored matrices:

* it **passes** (green) a surgical write — the changed cells all lie within the plan's
  target range;
* it **catches** (red) a deliberately **oversized** write — the plan targeted one cell
  but the after-matrix changed a second cell → the differ flags the stray cell;
* it **catches** a no-op write (nothing changed) and any stray change elsewhere;
* the restore-verify re-diff (:func:`assert_identical`) proves byte-identity and reddens
  on any residual drift.

The differ (``tests/sheets_values_diff.py``) is a **pure** function of two matrices + an
A1 target — it reuses the LD-110 A1 model (``parse_write_range``) to map the target range
to matrix coordinates, and has **no** network/creds surface, so this whole proof is offline.
"""
import pytest

from sheets_values_diff import (
    assert_identical,
    assert_surgical,
    cells_in_range,
    changed_cells,
)

# A hand-authored 3x3 used-range baseline (matrix origin is A1 — the convention the
# live gate reads under). Row r / col c ↔ A1 cell (col=c+1, row=r+1).
BASELINE = [
    ["A1", "B1", "C1"],
    ["A2", "B2", "C2"],
    ["A3", "B3", "C3"],
]


def _mutated(base, r, c, value):
    """A deep-ish copy of ``base`` with cell (r, c) set to ``value``."""
    out = [list(row) for row in base]
    out[r][c] = value
    return out


# --------------------------------------------------------------------------- #
# changed_cells — the full used-range matrix compare (ragged-safe)             #
# --------------------------------------------------------------------------- #

def test_changed_cells_empty_when_identical():
    assert changed_cells(BASELINE, [list(r) for r in BASELINE]) == set()


def test_changed_cells_pinpoints_the_single_edited_cell():
    after = _mutated(BASELINE, 1, 0, "A2-EDITED")  # A2 → (row 1, col 0)
    assert changed_cells(BASELINE, after) == {(1, 0)}


def test_changed_cells_is_ragged_safe_shrink_is_caught():
    # A shrunk row (B2/C2 dropped) must be caught as changed, not silently ignored.
    after = [["A1", "B1", "C1"], ["A2"], ["A3", "B3", "C3"]]
    assert changed_cells(BASELINE, after) == {(1, 1), (1, 2)}


def test_changed_cells_is_ragged_safe_grow_is_caught():
    after = [["A1", "B1", "C1"], ["A2", "B2", "C2", "D2"], ["A3", "B3", "C3"]]
    assert changed_cells(BASELINE, after) == {(1, 3)}


# --------------------------------------------------------------------------- #
# cells_in_range — the A1 target → 0-indexed matrix coords (A1 origin)          #
# --------------------------------------------------------------------------- #

def test_cells_in_range_single_cell():
    assert cells_in_range("A2") == {(1, 0)}


def test_cells_in_range_rectangle():
    assert cells_in_range("A2:B2") == {(1, 0), (1, 1)}


def test_cells_in_range_strips_sheet_id_prefix():
    # A cross-tab {sid}! prefix is opaque and must not shift the coordinates.
    assert cells_in_range("abc123!A2:B2") == {(1, 0), (1, 1)}


# --------------------------------------------------------------------------- #
# assert_surgical — GREEN: every changed cell lies within the target range      #
# --------------------------------------------------------------------------- #

def test_assert_surgical_accepts_a_single_cell_write():
    after = _mutated(BASELINE, 1, 0, "A2-EDITED")
    changed = assert_surgical(BASELINE, after, "A2")
    assert changed == {(1, 0)}


def test_assert_surgical_accepts_a_full_target_rectangle_write():
    after = _mutated(_mutated(BASELINE, 1, 0, "A2-NEW"), 1, 1, "B2-NEW")
    assert assert_surgical(BASELINE, after, "A2:B2") == {(1, 0), (1, 1)}


def test_assert_surgical_accepts_a_partial_write_within_the_target():
    # Writing only A2 while the plan targeted A2:B2 is still surgical (changed ⊆ target).
    after = _mutated(BASELINE, 1, 0, "A2-NEW")
    assert assert_surgical(BASELINE, after, "A2:B2") == {(1, 0)}


# --------------------------------------------------------------------------- #
# assert_surgical — RED: the deliberately-OVERSIZED write is flagged            #
# (the amplifier's core: "write two cells when the plan said one")             #
# --------------------------------------------------------------------------- #

def test_assert_surgical_flags_an_oversized_write_two_cells_for_a_one_cell_plan():
    # The plan targeted ONE cell (A2) but the write also clobbered its neighbour B2 —
    # a real over-write bug the surgical diff MUST catch.
    oversized = _mutated(_mutated(BASELINE, 1, 0, "A2-EDITED"), 1, 1, "B2-CLOBBERED")
    with pytest.raises(AssertionError) as excinfo:
        assert_surgical(BASELINE, oversized, "A2")
    # The stray cell (B2 → row 1, col 1) is named, and the diagnosis says "oversized".
    msg = str(excinfo.value)
    assert "(1, 1)" in msg
    assert "OUTSIDE" in msg or "oversized" in msg


def test_assert_surgical_flags_a_stray_change_far_from_the_target():
    # Target A2, but a distant cell (C3 → row 2, col 2) also drifted.
    stray = _mutated(_mutated(BASELINE, 1, 0, "A2-EDITED"), 2, 2, "C3-DRIFTED")
    with pytest.raises(AssertionError):
        assert_surgical(BASELINE, stray, "A2")


def test_assert_surgical_flags_a_no_op_write():
    # Nothing changed — a surgical write must have an observable effect on its target.
    with pytest.raises(AssertionError):
        assert_surgical(BASELINE, [list(r) for r in BASELINE], "A2")


# --------------------------------------------------------------------------- #
# assert_identical — the restore-verify re-diff (byte-identity)                 #
# --------------------------------------------------------------------------- #

def test_assert_identical_accepts_byte_identical_matrices():
    assert_identical(BASELINE, [list(r) for r in BASELINE])  # no raise


def test_assert_identical_reddens_on_any_residual_drift():
    after = _mutated(BASELINE, 0, 0, "A1-STILL-DIRTY")
    with pytest.raises(AssertionError) as excinfo:
        assert_identical(BASELINE, after)
    assert "(0, 0)" in str(excinfo.value)
