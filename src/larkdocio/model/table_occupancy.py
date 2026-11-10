"""Merged-table occupancy grid — the shared LD-050 covered-cell semantics.

**Extracted from the renderer's HTML-table path (LD-050)** so the writer's table
anchor resolver (LD-071) computes which cells a merge span covers
the SAME way the reader renders them, instead of reimplementing the algorithm (the
byte-identical goldens gate guards the extraction — see ``renderer.py`` ``_table_html``,
which now calls :func:`covered_positions` in place of its former inline loop).

A merged table is a **flat cell list folded into rows** by ``col_size`` — a cell's
grid position is ``(row, col) = (i // col_size, i % col_size)``. ``merges`` is the
parallel ``(row_span, col_span)`` list (RAW SDK values; ``None`` normalizes to 1). A
cell whose span exceeds ``1×1`` is an **anchor** that *claims* the grid positions its
span covers (all but its own top-left); a claimed position is **covered**.

**Coverage is COMPUTED, not read** (the load-bearing LD-050 finding): real Lark
payloads mark a covered cell ``(1,1)``, NOT span-0, so a covered cell's own
``merge_info`` must be **ignored** — coverage is derived only from *preceding* anchors'
spans. Reading the covered cell's own span emitted a phantom ``<td>`` and misaligned
every row a rowspan intersected (the gauntlet 4x4 table). Span-0 is retained
belt-and-braces: a synthetic payload may mark a covered cell ``0``, so a 0-span cell
neither claims nor is emitted.

**A covered position emits no cell — but its CONTENT is not lost (LD-529).** LD-050's
conclusion above is about *layout*, and it stands unchanged. What LD-050 never weighed
is what happens to the blocks a covered position holds: dropping them was a side effect
of the alignment fix, and it silently ate text and images alike. So this module also
answers *which anchor* claims a position — :func:`occupancy` — and the renderer absorbs
a covered cell's rendered content into that anchor's own ``<td>``/``<th>``. Each covered
position is claimed by exactly **one** anchor (the first in document order), so content
is absorbed once and never duplicated.

Pure grid arithmetic — depends only on the standard library, imports no node types.
"""
from typing import Dict, List, Optional, Sequence, Set, Tuple

Merge = Tuple[Optional[int], Optional[int]]


def fold_rows(n_cells: int, col_size: int) -> List[List[int]]:
    """Fold ``n_cells`` flat cell indices into rows of width ``col_size``.

    A merged/unmerged table is a **flat cell list folded into rows** by
    ``col_size`` — cell ``i`` sits at grid position ``(i // col_size, i % col_size)``.
    Returns rows of the cell indices in document order; the trailing row is left
    **ragged** (short) when ``n_cells`` is not a multiple of ``col_size`` — callers
    that need a rectangular grid (the markdown pipe path) pad it themselves.

    This is the single row-major fold the renderer's ``_table``/``_table_html``
    paths and :func:`covered_positions` all share (LD-084), lifted verbatim from
    the former inline loops so the byte-identical table goldens pin the extraction.
    ``col_size`` is assumed ``>= 1`` (every caller normalizes ``node.col_size or 1``
    before folding).
    """
    rows: List[List[int]] = []
    for i in range(n_cells):
        r_idx = i // col_size
        while len(rows) <= r_idx:
            rows.append([])
        rows[r_idx].append(i)
    return rows


def merge_span(merges: Sequence[Merge], idx: int) -> Tuple[int, int]:
    """The ``(row_span, col_span)`` of cell ``idx``, with ``None`` normalized to 1.

    A cell with no merge entry (``idx`` past the list) is a normal ``1×1`` cell. This
    is the renderer's former ``span_for`` closure, lifted to a shared function so the
    resolver reads a cell's own span exactly as the renderer does.
    """
    if idx < len(merges):
        rs, cs = merges[idx]
        rs = 1 if rs is None else rs
        cs = 1 if cs is None else cs
        return rs, cs
    return 1, 1


def occupancy(
    n_cells: int, merges: Sequence[Merge], col_size: int,
) -> Tuple[Set[Tuple[int, int]], Dict[int, List[int]]]:
    """The merged-table occupancy grid, in ONE pass: ``(covered, claimed_by_anchor)``.

    * ``covered`` — the set of ``(row, col)`` grid positions claimed by a
      *preceding* anchor's span. This is exactly what :func:`covered_positions`
      returns; that function is a thin view onto this pass, so the two can never
      disagree.
    * ``claimed_by_anchor`` — ``{anchor cell index: [covered cell indices]}``, in
      **row-major order** of the positions that anchor claims, and holding only
      positions that carry a real cell (an anchor whose span runs off the grid
      claims nothing there). This is the LD-529 half: the renderer needs to know
      *which* anchor covers a position so it can absorb that position's content
      into the anchor's own cell instead of discarding it.

    Walks the folded grid in document order; an anchor (``row_span``/``col_span``
    > 1) claims every position its span covers except its own top-left. A position
    already covered by an earlier anchor never claims further (its own span is
    ignored — the ``(1,1)`` trap) **and is not re-claimed**: the first anchor to
    claim a position owns it, so a malformed payload with two overlapping anchors
    absorbs the covered content exactly once rather than twice. A 0-span cell
    neither claims nor is emitted. Because an anchor is always visited before the
    positions it claims (all claimed positions come later in row-major order), the
    covered set is identical whether it is built incrementally (the renderer's
    former loop) or in this single up-front pass — the byte-identical goldens gate
    pins that equivalence.
    """
    merges = merges or []
    col_size = col_size or 1

    # Fold the flat cell indices into rows (row-major by col_size) — the shared
    # fold, so this pass and the renderer fold the SAME grid once each (LD-084).
    rows = fold_rows(n_cells, col_size)

    # position -> the cell index sitting there (a claimed position off the grid
    # simply has no entry, so it is covered but absorbs nothing).
    cell_at: Dict[Tuple[int, int], int] = {}
    for r_idx, row in enumerate(rows):
        for c_idx, idx in enumerate(row):
            cell_at[(r_idx, c_idx)] = idx

    covered: Set[Tuple[int, int]] = set()
    claimed_by_anchor: Dict[int, List[int]] = {}
    for r_idx, row in enumerate(rows):
        for c_idx, idx in enumerate(row):
            if (r_idx, c_idx) in covered:
                # Covered by a preceding anchor → its own span is never consulted.
                continue
            rs, cs = merge_span(merges, idx)
            if rs == 0 or cs == 0:
                # Belt-and-braces: a synthetic 0-span covered marker claims nothing.
                continue
            if rs > 1 or cs > 1:
                for dr in range(rs):
                    for dc in range(cs):
                        if not (dr or dc):
                            continue
                        pos = (r_idx + dr, c_idx + dc)
                        if pos in covered:
                            # Already owned by an earlier anchor (only a malformed
                            # payload overlaps two spans) — first claimer wins, so
                            # the content there is absorbed exactly once.
                            continue
                        covered.add(pos)
                        if pos in cell_at:
                            claimed_by_anchor.setdefault(idx, []).append(cell_at[pos])
    return covered, claimed_by_anchor


def covered_positions(n_cells: int, merges: Sequence[Merge], col_size: int) -> Set[Tuple[int, int]]:
    """The set of ``(row, col)`` grid positions COVERED by a preceding anchor's span.

    The covered half of :func:`occupancy` — signature and return value unchanged
    since LD-071, so the writer's anchor resolver reads coverage exactly as it
    always has (LD-529 added the position→anchor half beside it, not in place of
    it). See :func:`occupancy` for the walk and why the single up-front pass is
    equivalent to the renderer's former incremental loop.
    """
    return occupancy(n_cells, merges, col_size)[0]
