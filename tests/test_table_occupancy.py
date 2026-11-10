"""Offline unit tests for the shared table-geometry helpers in
``larkdocio.model.table_occupancy`` (LD-071 seam; LD-084 fold extraction).

``fold_rows`` is the single row-major "fold a flat cell list into rows by
``col_size``" arithmetic that was written three times before LD-084 (renderer
``_table``/``_table_html`` and ``covered_positions``' internal loop). These
pins characterize the fold in isolation so the extraction is provably
behavior-preserving; the table goldens + ``test_table_anchor_resolution`` pin
the byte-identity of the render/occupancy paths that consume it.
"""
from larkdocio.model.table_occupancy import fold_rows


def test_fold_rows_even_grid():
    # 6 cells, 3 columns -> two full rows of indices.
    assert fold_rows(6, 3) == [[0, 1, 2], [3, 4, 5]]


def test_fold_rows_ragged_final_row():
    # 7 cells, 3 columns -> the trailing row is short (no padding here; the
    # markdown path pads afterwards, the index fold does not).
    assert fold_rows(7, 3) == [[0, 1, 2], [3, 4, 5], [6]]


def test_fold_rows_single_column():
    assert fold_rows(3, 1) == [[0], [1], [2]]


def test_fold_rows_single_full_row():
    assert fold_rows(3, 3) == [[0, 1, 2]]


def test_fold_rows_empty():
    assert fold_rows(0, 3) == []
