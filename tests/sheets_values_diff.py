"""THE values-leg surgical differ for the Sheets value-write gate (LD-113).

The binding proof that a Sheets value write is **surgical** is a diff of the whole
**used-range value matrix** before and after the write: *only* the plan's target range
may change; every other cell must be byte-identical. This module is that differ — a
**pure** function of two matrices + an A1 target, with **no** network/creds surface — so
the live gate (``tests/test_live_sheets_write_gate.py``) can assert surgical-ness live
and the offline suite (``tests/test_sheets_values_diff.py``) can prove the differ itself
**red-then-green** on hand-authored fixture matrices (the test-rigor amplifier: an
oversized write — two cells changed when the plan targeted one — must be flagged).

**Matrix-coordinate convention.** A "used-range value matrix" is the raw
(``UnformattedValue``) rectangle read starting at **A1** — ``matrix[r][c]`` is the A1
cell ``(col=c+1, row=r+1)``. :func:`cells_in_range` maps an A1 target to that 0-indexed
coordinate set, reusing the LD-110 A1 model (:func:`~larkdocio.sheets.write_range.parse_write_range`)
rather than forking a parallel A1 parser; an opaque ``{sid}!`` cross-tab prefix is
stripped and never shifts the coordinates.

**Ragged-safe.** :func:`changed_cells` pads short/absent rows with an implicit ``None``
so a value-write that grows or shrinks a row (a cell appearing/vanishing) is caught as a
change, never silently ignored — a shrink is exactly the kind of stray effect the
surgical claim must reject.
"""
from larkdocio.sheets.write_range import parse_write_range


def changed_cells(before, after):
    """The set of ``(row, col)`` 0-indexed coordinates whose value differs between two
    used-range value matrices.

    Ragged/short rows (and a matrix with fewer rows) are padded with an implicit
    ``None`` so a grow/shrink is caught as a change rather than silently ignored.
    """
    n_rows = max(len(before), len(after))
    changed = set()
    for r in range(n_rows):
        b_row = before[r] if r < len(before) else []
        a_row = after[r] if r < len(after) else []
        n_cols = max(len(b_row), len(a_row))
        for c in range(n_cols):
            b = b_row[c] if c < len(b_row) else None
            a = a_row[c] if c < len(a_row) else None
            if b != a:
                changed.add((r, c))
    return changed


def cells_in_range(a1_range):
    """The set of ``(row, col)`` 0-indexed matrix coordinates an A1 target range covers,
    **relative to A1** (the used-range matrix origin).

    Reuses the LD-110 A1/range model (:func:`~larkdocio.sheets.write_range.parse_write_range`)
    — a single cell normalizes to a 1×1 range, an opaque ``{sid}!`` prefix is stripped —
    so a ``B2`` target maps to ``{(1, 1)}`` and ``A2:B2`` to ``{(1, 0), (1, 1)}``.
    """
    wr = parse_write_range(a1_range)
    return {
        (row - 1, col - 1)
        for row in range(wr.start.row, wr.end.row + 1)
        for col in range(wr.start.col, wr.end.col + 1)
    }


def assert_surgical(before, after, target_range):
    """Assert the values-leg diff is **surgical**: at least one cell changed AND every
    changed cell lies **within** ``target_range`` (the plan's target).

    Raises :class:`AssertionError` — naming the stray cell(s) and diagnosing an
    **oversized/stray write** — when a cell *outside* the target changed (the amplifier's
    two-cells-for-a-one-cell-plan bug), or when *nothing* changed (a write with no
    observable effect). Returns the changed-cell set on success.
    """
    changed = changed_cells(before, after)
    assert changed, (
        "values-leg diff found NO change — the write had no observable effect "
        "(a surgical write must change its target range)"
    )
    target = cells_in_range(target_range)
    stray = changed - target
    assert not stray, (
        f"values-leg diff is NOT surgical: cell(s) {sorted(stray)} changed but lie "
        f"OUTSIDE the planned target {target_range!r} (covers {sorted(target)}) — an "
        f"oversized/stray write clobbered a cell the plan never named"
    )
    return changed


def assert_identical(before, after):
    """The restore-verify re-diff: assert two used-range matrices are **byte-identical**
    (zero changed cells). Raises :class:`AssertionError` naming the drifted cell(s) — the
    binding proof that the baseline was restored exactly, with no residual drift.
    """
    changed = changed_cells(before, after)
    assert not changed, (
        f"used-range matrices are NOT byte-identical: cell(s) {sorted(changed)} still "
        f"differ after restore — the baseline was not restored exactly"
    )
