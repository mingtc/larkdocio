"""Offline unit tests for table anchor resolution (LD-071).

W2-S2 resolves a :class:`~larkdocio.write.model.TableLocator` anchor (LD-070: row-key
key-cell quote + a column-target + breadcrumb) against the reader's parsed node tree —
W0's ``block_id`` provenance is the addressing key — to **exactly one target cell block
or a typed refusal, never a guess** (spike ``dev/write-spike/07-report.md`` Test 5: a
bare value is useless in a table — ``97.2%`` appeared in 6 blocks; a cell is located by
its row's key cell ``"On-time delivery"`` + its column).

Row by verbatim key-cell match (unique-or-refuse WITHIN the table); column by the
target designation (header quote OR 0-based index); breadcrumb narrows WHICH table.
A merged/covered target refuses ``write-hostile-target`` — coverage computed via
**LD-050's occupancy-grid semantics** (from preceding anchors' spans; a covered cell
reads ``(1,1)``), reused from the renderer, not reimplemented. Fully offline.
"""
from larkdocio.model import DocumentNode, TableCellNode, Text, TextNode
from larkdocio.model.table_occupancy import covered_positions, merge_span
from larkdocio.write.model import Anchor, EditRequest, RefusalReason
from larkdocio.write.resolve import ResolvedTarget, resolve

# Shared node + table structural builders (LD-088). The per-test DATA tables
# below stay inline (readable per-test specs — builders.py doctrine).
from write_harness import _heading, _page, _table, _treq


# The spike-Test-5-shaped table: a value ("97.2%") appears in SIX cells doc-wide (a
# bare quote is ambiguous), but row "On-time delivery" + column "Q3" is exactly one.
def _spike_test5_table(bid="t5"):
    return _table(
        bid,
        [
            [("h0", "Metric"), ("h1", "Q2"), ("h2", "Q3")],
            [("r1k", "On-time delivery"), ("r1a", "95.0%"), ("r1b", "97.2%")],
            [("r2k", "Defect rate"), ("r2a", "97.2%"), ("r2b", "97.2%")],
            [("r3k", "Uptime"), ("r3a", "97.2%"), ("r3b", "97.2%")],
        ],
    )


# --------------------------------------------------------------------------- #
# AC1 — exactly-one-cell-or-refuse (never >1, never a guess); reuses infra      #
# --------------------------------------------------------------------------- #

def test_resolves_table_cell_to_exactly_one_block_id():
    tree = _page(_spike_test5_table())
    result = resolve(_treq("On-time delivery", column_header="Q3"), tree)
    assert isinstance(result, ResolvedTarget)
    assert result.block_id == "r1b"           # row "On-time delivery" × column "Q3"
    assert isinstance(result.node, TableCellNode)


def test_table_result_is_resolved_target_or_typed_refusal_only():
    tree = _page(_spike_test5_table())
    ok = resolve(_treq("On-time delivery", column_index=2), tree)
    miss = resolve(_treq("No such row", column_index=2), tree)
    assert isinstance(ok, ResolvedTarget)
    assert not isinstance(miss, ResolvedTarget)
    assert miss.reason in set(RefusalReason)


def test_resolver_walks_the_whole_tree_reusing_collect_blocks():
    # The table is nested deep under headings — resolving it at all proves the
    # table resolver reuses write/resolve.py's tree walk (_collect_blocks), not a
    # shallow top-level scan.
    tree = _page(
        _heading("h", "Section", level=1),
        _spike_test5_table(),
    )
    result = resolve(_treq("On-time delivery", column_index=2), tree)
    assert isinstance(result, ResolvedTarget)
    assert result.block_id == "r1b"


def test_narrative_anchor_still_resolves_after_dispatch():
    # Regression: the narrative (quote + breadcrumb) path is untouched by the
    # TableLocator dispatch — resolve() still handles a plain Anchor.
    tree = _page(TextNode(content=[Text("plain paragraph here")], block_id="p"))
    req = EditRequest(anchor=Anchor(quote="plain paragraph here"), replacement="X")
    assert resolve(req, tree).block_id == "p"


# --------------------------------------------------------------------------- #
# AC2 — row by key cell (unique-or-refuse WITHIN the table)                     #
# --------------------------------------------------------------------------- #

def test_row_resolved_by_key_cell_verbatim():
    tree = _page(_spike_test5_table())
    # column 1 = "Q2"; the "Defect rate" row's Q2 cell is r2a.
    assert resolve(_treq("Defect rate", column_index=1), tree).block_id == "r2a"


def test_row_key_matching_more_than_one_row_is_ambiguous_row():
    # Two rows share the key cell "On-time delivery" → ambiguous-row; never picks.
    tree = _page(_table(
        "t",
        [
            [("h0", "Metric"), ("h1", "Val")],
            [("k1", "On-time delivery"), ("v1", "95%")],
            [("k2", "On-time delivery"), ("v2", "97%")],
        ],
    ))
    result = resolve(_treq("On-time delivery", column_index=1), tree)
    assert result.reason is RefusalReason.AMBIGUOUS
    assert set(result.candidate_ids) == {"k1", "k2"}   # the two key-cell ids


def test_row_key_matching_no_row_is_not_found():
    tree = _page(_spike_test5_table())
    result = resolve(_treq("Nonexistent metric", column_index=1), tree)
    assert result.reason is RefusalReason.NOT_FOUND


def test_key_cell_is_column_zero_not_any_cell_in_the_row():
    # "95.0%" lives in a NON-key column (col 1). It must NOT resolve a row by it —
    # the key cell is column 0 only. (No row's column-0 cell contains "95.0%".)
    tree = _page(_spike_test5_table())
    result = resolve(_treq("95.0%", column_index=2), tree)
    assert result.reason is RefusalReason.NOT_FOUND


# --------------------------------------------------------------------------- #
# AC3 — column by target (header quote OR 0-based index); missing → col-not-found #
# --------------------------------------------------------------------------- #

def test_column_by_header_quote():
    tree = _page(_spike_test5_table())
    assert resolve(_treq("On-time delivery", column_header="Q2"), tree).block_id == "r1a"
    assert resolve(_treq("On-time delivery", column_header="Q3"), tree).block_id == "r1b"


def test_column_by_zero_based_index():
    tree = _page(_spike_test5_table())
    assert resolve(_treq("On-time delivery", column_index=0), tree).block_id == "r1k"
    assert resolve(_treq("On-time delivery", column_index=1), tree).block_id == "r1a"
    assert resolve(_treq("On-time delivery", column_index=2), tree).block_id == "r1b"


def test_absent_column_header_is_column_not_found():
    tree = _page(_spike_test5_table())
    result = resolve(_treq("On-time delivery", column_header="Q4"), tree)
    assert result.reason is RefusalReason.COLUMN_NOT_FOUND


def test_out_of_range_column_index_is_column_not_found():
    tree = _page(_spike_test5_table())   # col_size 3 → valid indices 0..2
    assert resolve(_treq("On-time delivery", column_index=3), tree).reason is RefusalReason.COLUMN_NOT_FOUND
    assert resolve(_treq("On-time delivery", column_index=-1), tree).reason is RefusalReason.COLUMN_NOT_FOUND


def test_ambiguous_column_header_never_auto_picks():
    # Two header cells both contain "Q" → the column-target is ambiguous; the
    # resolver refuses (AMBIGUOUS) rather than guessing a column.
    tree = _page(_table(
        "t",
        [
            [("h0", "Metric"), ("h1", "Q2 value"), ("h2", "Q3 value")],
            [("k", "On-time delivery"), ("a", "1"), ("b", "2")],
        ],
    ))
    result = resolve(_treq("On-time delivery", column_header="value"), tree)
    assert result.reason is RefusalReason.AMBIGUOUS
    assert set(result.candidate_ids) == {"a", "b"}   # candidate target cells in the row


# --------------------------------------------------------------------------- #
# AC4 — breadcrumb narrows WHICH table                                          #
# --------------------------------------------------------------------------- #

def _two_tables_same_key():
    # The SAME key cell ("On-time delivery") appears in two tables under two
    # headings — a bare row-key is ambiguous across tables.
    return _page(
        _heading("hA", "Alpha"),
        _table("tA", [
            [("a_h0", "Metric"), ("a_h1", "Val")],
            [("a_k", "On-time delivery"), ("a_v", "95%")],
        ]),
        _heading("hB", "Beta"),
        _table("tB", [
            [("b_h0", "Metric"), ("b_h1", "Val")],
            [("b_k", "On-time delivery"), ("b_v", "97%")],
        ]),
    )


def test_breadcrumb_narrows_to_the_intended_table():
    tree = _two_tables_same_key()
    assert resolve(_treq("On-time delivery", column_index=1, breadcrumb=("Alpha",)), tree).block_id == "a_v"
    assert resolve(_treq("On-time delivery", column_index=1, breadcrumb=("Beta",)), tree).block_id == "b_v"


def test_key_cell_in_two_tables_no_breadcrumb_is_ambiguous_table():
    tree = _two_tables_same_key()
    result = resolve(_treq("On-time delivery", column_index=1), tree)
    assert result.reason is RefusalReason.AMBIGUOUS
    assert set(result.candidate_ids) == {"tA", "tB"}   # the two candidate TABLE ids


def test_breadcrumb_matching_no_table_is_not_found():
    tree = _two_tables_same_key()
    result = resolve(_treq("On-time delivery", column_index=1, breadcrumb=("Gamma",)), tree)
    assert result.reason is RefusalReason.NOT_FOUND


# --------------------------------------------------------------------------- #
# AC5 — merged/covered target refuses write-hostile (reuse LD-050 occupancy)    #
# --------------------------------------------------------------------------- #

def _merged_table():
    # 3 cols. Row 1's Q2 cell (grid (1,1)) is a colspan=2 merge ANCHOR covering the
    # Q3 cell (grid (1,2)). Real Lark marks the covered Q3 cell (1,1) — so coverage
    # must be COMPUTED from the anchor's span, not read off the covered cell.
    return _table(
        "tm",
        [
            [("h0", "Metric"), ("h1", "Q2"), ("h2", "Q3")],
            [("k", "On-time delivery"), ("merged", "97.2%"), ("covered", "97.2%")],
        ],
        merges=[(1, 1), (1, 1), (1, 1),          # header row: all 1x1
                (1, 1), (1, 2), (1, 1)],          # k=1x1, merged=colspan2, covered reads (1,1)
    )


def test_covered_target_cell_refuses_write_hostile():
    tree = _page(_merged_table())
    # column 2 (Q3) resolves to the COVERED cell (grid (1,2)) → write-hostile.
    result = resolve(_treq("On-time delivery", column_index=2), tree)
    assert result.reason is RefusalReason.WRITE_HOSTILE


def test_merge_anchor_target_cell_refuses_write_hostile():
    tree = _page(_merged_table())
    # column 1 (Q2) resolves to the merge ANCHOR itself (colspan=2) → write-hostile
    # ("merged / covered targets refuse" — W2 never writes into a merge span).
    result = resolve(_treq("On-time delivery", column_index=1), tree)
    assert result.reason is RefusalReason.WRITE_HOSTILE


def test_unmerged_cell_in_a_merged_table_still_resolves():
    tree = _page(_merged_table())
    # column 0 (the key cell itself) is a plain 1x1 cell → resolves normally.
    assert resolve(_treq("On-time delivery", column_index=0), tree).block_id == "k"


def test_coverage_computed_from_preceding_anchor_not_covered_cells_own_span():
    # The covered cell's OWN merge entry is (1,1); only the preceding anchor's
    # (1,2) span reveals the coverage. This pins the LD-050 semantics reuse.
    tree = _page(_merged_table())
    result = resolve(_treq("On-time delivery", column_index=2), tree)
    assert result.reason is RefusalReason.WRITE_HOSTILE


# --------------------------------------------------------------------------- #
# AC5 (helper) — the shared occupancy grid is REUSED, not reimplemented         #
# --------------------------------------------------------------------------- #

def test_covered_positions_matches_the_renderers_rowspan_example():
    # The renderer's merged-table pin: a rowspan=2 anchor at (0,0) covers (1,0).
    covered = covered_positions(4, [(2, 1), (1, 1), (1, 1), (1, 1)], col_size=2)
    assert covered == {(1, 0)}


def test_covered_positions_colspan_and_none_normalization():
    # colspan=2 at (1,1) covers (1,2); None spans normalize to 1 (no coverage).
    covered = covered_positions(6, [(1, 1), (None, None), (1, 1), (1, 1), (1, 2), (1, 1)], col_size=3)
    assert covered == {(1, 2)}


def test_covered_positions_covered_cell_own_span_is_ignored():
    # Even when a covered position's own entry is (1,1) (the real-Lark trap), it is
    # still covered because coverage derives from the preceding anchor's span.
    covered = covered_positions(6, [(1, 1), (1, 1), (1, 1), (1, 1), (1, 2), (1, 1)], col_size=3)
    assert (1, 2) in covered


def test_merge_span_normalizes_none_and_out_of_range():
    assert merge_span([(2, 3)], 0) == (2, 3)
    assert merge_span([(None, None)], 0) == (1, 1)
    assert merge_span([], 5) == (1, 1)          # no entry → 1x1


# --------------------------------------------------------------------------- #
# AC6 — spike-Test-5 + 6-way ambiguous value, all offline                       #
# --------------------------------------------------------------------------- #

def _six_way_value_table(bid="t6"):
    # "97.2%" appears in SIX value cells; "On-time delivery" × "Q3" is exactly one.
    return _table(
        bid,
        [
            [("h0", "Metric"), ("h1", "Q2"), ("h2", "Q3")],
            [("r1k", "On-time delivery"), ("r1a", "95.0%"), ("r1b", "97.2%")],
            [("r2k", "Defect rate"), ("r2a", "97.2%"), ("r2b", "97.2%")],
            [("r3k", "Uptime"), ("r3a", "97.2%"), ("r3b", "97.2%")],
            [("r4k", "Churn"), ("r4a", "97.2%"), ("r4b", "99.0%")],
        ],
    )
    # 97.2% count: r1b, r2a, r2b, r3a, r3b, r4a = 6.


def test_spike_test5_shaped_table_resolves_by_row_key_and_column():
    tree = _page(_six_way_value_table())
    result = resolve(_treq("On-time delivery", column_header="Q3"), tree)
    assert isinstance(result, ResolvedTarget)
    assert result.block_id == "r1b"


def test_six_way_value_bare_quote_is_ambiguous_but_table_locator_resolves():
    tree = _page(_six_way_value_table())
    # A bare quote for the value would mis-hit six cells (the narrative path refuses).
    bare = resolve(EditRequest(anchor=Anchor(quote="97.2%"), replacement="X"), tree)
    assert bare.reason is RefusalReason.AMBIGUOUS
    assert bare.candidate_count == 6
    # The table_locator disambiguates to exactly one cell.
    located = resolve(_treq("On-time delivery", column_header="Q3"), tree)
    assert isinstance(located, ResolvedTarget)
    assert located.block_id == "r1b"


# --------------------------------------------------------------------------- #
# AC7-adjacent — works over the headless DocumentNode root too                  #
# --------------------------------------------------------------------------- #

def test_resolves_over_a_headless_document_root():
    tree = DocumentNode(children=[_six_way_value_table()], block_id=None)
    assert resolve(_treq("On-time delivery", column_index=2), tree).block_id == "r1b"


# --------------------------------------------------------------------------- #
# LD-636 / `D-117` — a table that declares ``header_row=False``.                #
#                                                                              #
# The hole this section closes, named by the audit that found it: ``header_row  #
# =False`` appeared at 12 test sites and EVERY ONE was creation or rendering —  #
# no test resolved a locator against a header-less table, which is why nothing  #
# reddened when the refusal called row-0 DATA cells "its headers". Two claims   #
# live here and they are different claims: the CAPABILITY (`D-117` Reading A:   #
# ``column_header`` means the text in row 0, and a header-less table resolves   #
# by it) and the WORDING (the refusal must not assert those cells are headers). #
# --------------------------------------------------------------------------- #

def _headerless_table(bid="t9"):
    """The audit's own shape: ``header_row=False``, so row 0 is the first DATA row."""
    return _table(
        bid,
        [
            [("c00", "Widgets"), ("c01", "1200")],
            [("c10", "Gadgets"), ("c11", "340")],
        ],
        header_row=False,
    )


def test_ld636_a_headerless_table_STILL_RESOLVES_by_a_row_zero_cell_quote():
    """`D-117` Reading A, pinned as a capability so no later tidy-up can remove it:
    ``column_header`` is *the text in row 0*, and the resolver deliberately never reads
    ``TableNode.header_row``. Gating on it was the alternative reading and was **declined** —
    it would take away a working way to repair a sentence in a header-less table."""
    tree = _page(_headerless_table())
    result = resolve(_treq("Gadgets", column_header="1200"), tree)
    assert isinstance(result, ResolvedTarget), result
    assert result.block_id == "c11"           # row "Gadgets" x the column row 0 calls "1200"


def test_ld636_the_headerless_resolution_is_still_unique_or_refuse():
    """The contract does not loosen for a header-less table: a row-0 text matching two
    columns refuses rather than picking one, exactly as it does for a header-ful one."""
    tree = _page(_table(
        "t",
        [
            [("c00", "1200 units"), ("c01", "1200 boxes")],
            [("c10", "Gadgets"), ("c11", "340")],
        ],
        header_row=False,
    ))
    result = resolve(_treq("Gadgets", column_header="1200"), tree)
    assert result.reason is RefusalReason.AMBIGUOUS


def test_ld636_the_refusal_NEVER_calls_a_headerless_tables_row_zero_its_headers():
    """The defect itself. A ``header_row=False`` table asking for a missing column used to
    be told *"its headers are ['Widgets', '1200']"* — naming data cells, inside the very
    did-you-mean list (LD-131) that exists so a consumer need not re-read the document."""
    tree = _page(_headerless_table())
    result = resolve(_treq("Gadgets", column_header="Units"), tree)
    assert result.reason is RefusalReason.COLUMN_NOT_FOUND
    assert "its headers" not in result.detail
    assert "headers are" not in result.detail
    # The only surviving uses of the word are the field name and an explicit DENIAL that
    # row 0 holds headers -- never an assertion that it does.
    assert result.detail.count("header") == result.detail.count("column_header") + 2, (
        result.detail)


def test_ld636_the_refusal_says_row_zero_holds_DATA_and_names_the_positional_escape():
    """What replaces the false claim is not silence: the consumer is told that ``column_header``
    matches row 0, that *this* table declares ``header_row=False`` so row 0 is data, and that
    ``column_index`` is how a column is addressed positionally — the three facts that turn a
    dead end into a next action."""
    tree = _page(_headerless_table())
    detail = resolve(_treq("Gadgets", column_header="Units"), tree).detail
    assert "no cell in row 0 of table t9 contains 'Units'" in detail
    assert "header_row=False" in detail
    assert "row 0 holds DATA, not headers" in detail
    assert "column_index" in detail
    # ...and the did-you-mean list survives the rewording, still quoted per LD-131.
    assert "row 0 reads ['Widgets', '1200']" in detail


def test_ld636_a_header_ful_tables_refusal_still_says_header_row():
    """The wording is not flattened to the lowest common denominator: where row 0 really is
    the header row the refusal says so, because that is the fact the consumer needs there.
    Same list, different sentence — which is the whole point of reading ``header_row`` for
    the WORDING while the lookup stays ungated."""
    tree = _page(_spike_test5_table())
    detail = resolve(_treq("On-time delivery", column_header="Q4"), tree).detail
    assert "this table's header row" in detail
    assert "header_row=False" not in detail
    assert "row 0 reads ['Metric', 'Q2', 'Q3']" in detail


def test_ld636_a_row_zero_column_target_is_offered_by_INDEX_too():
    """The escape the refusal names is a real one, proved by using it: the column the
    header-less table could not be given by name is reachable by index."""
    tree = _page(_headerless_table())
    assert resolve(_treq("Gadgets", column_index=1), tree).block_id == "c11"
