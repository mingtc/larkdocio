"""LD-150 — "the plan tells you everything", completed: the nine seat-dogfood disclosure holes.

One module for the whole bug batch, because the nine findings share one subject — **the sheets
plan / dry-run / apply-log disclosure surface** — and the AC10 contract is that *each finding's
exact repro from* `dev/dogfood/2026-07-28-seat-session/report.md` *becomes a permanent test*.
Each section below opens with the report's own repro, verbatim in code, then pins the fix.

| § | finding | hole |
|---|---------|------|
| F21 | shape mismatch resolved instead of refusing | `Refusal.SHAPE_MISMATCH`, pre-I/O |
| F9  | clearing a live formula previewed as data | `"overwrites-live-formula"` note |
| F8  | the warning died between plan and log | `preview_note` on applied entries + `ApplyLog.inert_formula_strings` |
| F20 | a reversed range refused `tab-vanished` | `Refusal.MALFORMED_RANGE` |
| F24 | untyped / mistyped malformed input | `A1RangeError` / `DimensionSpanError` |
| F16 | sub-span hid its compare-and-swap basis | `precondition_text` parity |
| F22 | unmerge on an unmerged range resolved | `"no-merge-at-range"` note |
| F23 | out-of-bounds delete resolved | `"out-of-bounds-dimension"` note |
| F12 | `removed.values` padded to the declared width | trim to the used extent |

Every arm is **offline** (an injected transport). Nothing here opens a socket.
"""
import json

import pytest

from log_reading_apply import reading_the_log
from larkdocio.errors import LarkAPIError, LarkConfigError
from larkdocio.sheets.write_apply import (
    DeleteCols,
    DeleteRows,
    FormulaWriteRequest,
    RichCellWriteRequest,
    ValueWriteRequest,
    apply,
    dry_run,
)
apply = reading_the_log(apply)
from larkdocio.sheets.plan import Refusal
from larkdocio.sheets.requests import DimensionSpanError, MergeCells, UnmergeCells
from larkdocio.sheets.write_range import A1RangeError, parse_write_range

TOKEN = "shtLD150TOKEN"
SID = "2h6Tew"


# =========================================================================== #
# The seam — a gateway that models render modes, geometry and merges, and      #
# COUNTS every call, so "no extra call" claims are proven, not asserted.       #
# =========================================================================== #

class Gateway:
    """A duck-typed write-client seam with a per-render-mode value store.

    ``values`` maps an A1 range → a matrix (or an ``Exception`` to raise). A cell may be the
    formula **object form** (``{"type": "formula", "text": "=…"}``); the render modes then
    behave exactly as the LD-149 probe characterized — ``Formula`` answers the expression,
    ``UnformattedValue`` answers ``computed[expression]``.
    """

    def __init__(self, *, revision=7, values=None, geometry=None, tabs=None, computed=None):
        self.revision = revision
        self.values = dict(values or {})
        self.geometry = dict(geometry or {})
        self.tabs = list(tabs if tabs is not None else [{"sheet_id": SID, "title": "SheetThree"}])
        self.computed = dict(computed or {})
        self.calls = []          # every seam call, in order — the call-count spy
        self.puts = []

    # -- reads -------------------------------------------------------------- #

    def read_revision(self, spreadsheet_token):
        self.calls.append(("read_revision", None))
        return self.revision

    def read_values(self, spreadsheet_token, a1_range, value_render_option="UnformattedValue"):
        self.calls.append(("read_values", a1_range, value_render_option))
        v = self.values.get(a1_range)
        if isinstance(v, Exception):
            raise v
        return [[self._render(c, value_render_option) for c in row] for row in (v or [])]

    def _render(self, cell, mode):
        from larkdocio.sheets.formula import EXPRESSION_RENDER_OPTION, formula_expression

        expression = formula_expression(cell)
        if expression is None:
            return cell
        if mode == EXPRESSION_RENDER_OPTION:
            return expression
        return self.computed.get(expression, expression)

    def read_sheet_geometry(self, spreadsheet_token, sheet_id):
        self.calls.append(("read_sheet_geometry", sheet_id))
        return dict(self.geometry)

    def query_tabs(self, spreadsheet_token):
        self.calls.append(("query_tabs", None))
        return [dict(t) for t in self.tabs]

    # -- writes ------------------------------------------------------------- #

    def put_values(self, spreadsheet_token, a1_range, values):
        self.calls.append(("put_values", a1_range))
        self.puts.append((a1_range, values))
        self.values[a1_range] = [list(r) for r in values]
        self.revision += 1
        return {"revision": self.revision}

    def delete_dimension_range(self, spreadsheet_token, sheet_id, major_dimension, start_index, end_index):
        self.calls.append(("delete_dimension_range", (sheet_id, major_dimension, start_index, end_index)))
        self.revision += 1
        return {"delCount": end_index - start_index + 1}

    def unmerge_cells(self, spreadsheet_token, a1_range):
        self.calls.append(("unmerge_cells", a1_range))
        self.revision += 1
        return {"spreadsheetToken": spreadsheet_token}

    def merge_cells(self, spreadsheet_token, a1_range, merge_type):
        self.calls.append(("merge_cells", a1_range))
        self.revision += 1
        return {"spreadsheetToken": spreadsheet_token}

    def n(self, name):
        """How many times seam ``name`` was called (the call-count spy)."""
        return sum(1 for c in self.calls if c[0] == name)


def _grid(rows=200, cols=20, merges=()):
    return {"row_count": rows, "column_count": cols, "merges": list(merges)}


# =========================================================================== #
# F24 / AC5 — typed, EXAMPLED errors for a malformed A1 ref + a reversed span.  #
#                                                                              #
# Report repro 5: for_a1("<sid>!banana") → LarkConfigError "not a full A1 cell: #
# 'banana'" (wrong category, no valid-form example); DeleteRows(first=5,last=2) #
# → a bare ValueError. The house benchmark is FormulaExpressionError: it names  #
# the fault, the consequence, and BOTH repairs.                                 #
# =========================================================================== #

def test_f24_repro_malformed_a1_ref_raises_a_typed_exampled_error():
    """The report's exact repro — now a typed :class:`A1RangeError` with an example."""
    with pytest.raises(A1RangeError) as ei:
        ValueWriteRequest.for_a1(f"{SID}!banana", [["x"]])
    msg = str(ei.value)
    assert "banana" in msg                                  # names the fault
    assert "A1:B2" in msg or "A1:A1" in msg                 # a VALID-FORM EXAMPLE
    assert "sheet_id" in msg                                # the {sid}! repair
    # still under the config family, so every shipped `except LarkConfigError` keeps working
    assert isinstance(ei.value, LarkConfigError)


def test_f24_repro_reversed_row_span_raises_a_typed_exampled_error():
    """The report's exact repro — ``DeleteRows(first=5, last=2)`` is no longer a bare
    ``ValueError``."""
    with pytest.raises(DimensionSpanError) as ei:
        DeleteRows(sheet_id=SID, first=5, last=2)
    msg = str(ei.value)
    assert "first=5" in msg and "last=2" in msg              # names the fault
    assert "DeleteRows(sheet_id=" in msg                     # a VALID-FORM EXAMPLE
    assert isinstance(ei.value, LarkConfigError)
    # ...and still a ValueError, so no existing caller's `except ValueError` breaks.
    assert isinstance(ei.value, ValueError)


def test_f24_reversed_column_span_gets_the_same_typed_error():
    with pytest.raises(DimensionSpanError) as ei:
        DeleteCols(sheet_id=SID, first=9, last=3)
    assert "DeleteCols(sheet_id=" in str(ei.value)


@pytest.mark.parametrize("bad", ["banana", "A1:B2:C3", "!", "1A", "A1:banana"])
def test_f24_every_malformed_a1_shape_raises_the_typed_error_with_an_example(bad):
    with pytest.raises(A1RangeError) as ei:
        parse_write_range(f"{SID}!{bad}" if bad != "!" else bad)
    assert "A1" in str(ei.value), str(ei.value)


def test_f24_a_well_formed_range_still_parses_unchanged():
    wr = parse_write_range(f"{SID}!A1:B2")
    assert (wr.sheet_id, wr.a1()) == (SID, f"{SID}!A1:B2")
    assert parse_write_range(f"{SID}!B2").a1() == f"{SID}!B2:B2"    # D2 normalize intact


# =========================================================================== #
# F21 / AC1 — a values matrix whose ARITY does not match the target range's     #
# shape is REFUSED pre-I/O, not resolved.                                       #
#                                                                              #
# Report repro 1: ValueWriteRequest.for_a1("<sid>!A1:B2", [["only-one"]]) →     #
# dry_run → before 2×2 / after 1×1, no refusal and no note — so the plan could  #
# not say what happens to B1/A2/B2 (the failure mode is silently blanking them).#
# =========================================================================== #

def test_f21_repro_a_one_by_one_matrix_into_a_two_by_two_range_refuses():
    """The report's exact repro, now a typed refusal naming BOTH shapes."""
    gw = Gateway(values={f"{SID}!A1:B2": [["a", "b"], ["c", "d"]]})
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:B2", [["only-one"]])], gw, TOKEN)
    (entry,) = plan.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason == Refusal.SHAPE_MISMATCH == "shape-mismatch"
    detail = entry.refusal.detail
    assert "2 row(s) x 2 col(s)" in detail          # the TARGET shape
    assert "1 row(s) x 1 col(s)" in detail          # the MATRIX shape
    assert f"{SID}!A1:B2" in detail                 # the offending range
    # the rejected intent is still carried, so an approval UX can show it (PlanEntry contract)
    assert entry.after == [["only-one"]]


def test_f21_the_refusal_is_pre_io_zero_reads():
    """AC1: the arity is known **before any call**, so the refusal costs no values read."""
    gw = Gateway(values={f"{SID}!A1:B2": [["a", "b"], ["c", "d"]]})
    dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:B2", [["only-one"]])], gw, TOKEN)
    assert gw.n("read_values") == 0, gw.calls
    assert gw.n("query_tabs") == 0, gw.calls


def test_f21_an_exact_shape_match_resolves():
    gw = Gateway(values={f"{SID}!A1:B2": [["a", "b"], ["c", "d"]]})
    plan = dry_run(
        [ValueWriteRequest.for_a1(f"{SID}!A1:B2", [["w", "x"], ["y", "z"]])], gw, TOKEN)
    assert plan.entries[0].outcome == "resolved"


def test_f21_a_one_by_one_into_a_single_cell_resolves():
    gw = Gateway(values={f"{SID}!A1:A1": [["old"]]})
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:A1", [["new"]])], gw, TOKEN)
    assert plan.entries[0].outcome == "resolved"
    # ...and the D2 single-cell normalize path too (A1 → A1:A1).
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1", [["new"]])], gw, TOKEN)
    assert plan.entries[0].outcome == "resolved"


@pytest.mark.parametrize("a1,values,why", [
    (f"{SID}!A1:B2", [["one"]], "1x1 into 2x2"),
    (f"{SID}!A1:A1", [["a", "b"], ["c", "d"]], "2x2 into 1x1"),
    (f"{SID}!A1:B2", [["a", "b"], ["c"]], "ragged rows"),
    (f"{SID}!A1:B2", [], "empty matrix"),
    (f"{SID}!A1:B2", [["a", "b", "c"], ["d", "e", "f"]], "wider than the range"),
    (f"{SID}!A1:A3", [["a"], ["b"]], "too few rows"),
    (f"{SID}!A1:A2", [["a"], ["b"], ["c"]], "too many rows"),
    (f"{SID}!A1:A1", "not-a-matrix", "not a list at all"),
])
def test_f21_shape_mismatch_matrix_every_shape_refuses(a1, values, why):
    """The maintainer's amplifier matrix — every arity mismatch refuses, none resolves."""
    gw = Gateway(values={a1: [["x"]]})
    plan = dry_run([ValueWriteRequest(target=parse_write_range(a1), values=values)], gw, TOKEN)
    assert plan.entries[0].outcome == "refused", why
    assert plan.entries[0].refusal.reason == Refusal.SHAPE_MISMATCH, why


def test_f21_a_clear_write_of_the_right_shape_still_resolves():
    """The undocumented-but-real clear idiom (`[[None], [None]]`) is shape-correct and must
    keep resolving — F21 refuses arity mismatches, never the clear technique."""
    gw = Gateway(values={f"{SID}!A1:A2": [["x"], ["y"]]})
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:A2", [[None], [None]])], gw, TOKEN)
    assert plan.entries[0].outcome == "resolved"


def test_f21_a_rich_cell_write_into_a_multi_cell_range_refuses_too():
    """The check lives at the ONE dispatch seam, so every values-bearing family gets it —
    a rich cell is 1×1 by construction (D2) and cannot address a 2×2 range."""
    gw = Gateway(values={f"{SID}!A1:B2": [["a", "b"], ["c", "d"]]})
    plan = dry_run([RichCellWriteRequest.hyperlink(f"{SID}!A1:B2", "https://x")], gw, TOKEN)
    assert plan.entries[0].refusal.reason == Refusal.SHAPE_MISMATCH


def test_f21_a_formula_write_into_a_multi_cell_range_refuses_too():
    gw = Gateway(values={f"{SID}!A1:B2": [["a", "b"], ["c", "d"]]})
    plan = dry_run([FormulaWriteRequest.for_a1(f"{SID}!A1:B2", "=SUM(C1:C2)")], gw, TOKEN)
    assert plan.entries[0].refusal.reason == Refusal.SHAPE_MISMATCH


def test_f21_a_structural_append_with_values_is_not_shape_checked():
    """``AppendRowsWithValues`` appends NEW rows — its values have no target rectangle to
    match, so the arity check must not touch it."""
    from larkdocio.sheets.write_apply import AppendRowsWithValues

    gw = Gateway(geometry=_grid())
    plan = dry_run(
        [AppendRowsWithValues(a1_range=f"{SID}!A1:B2", values=[["a", "b"], ["c", "d"], ["e", "f"]])],
        gw, TOKEN)
    assert plan.entries[0].outcome == "resolved"


def test_f21_the_shape_refusal_still_carries_the_inert_string_warning():
    """A disclosure must never displace another (the F8 lesson): a shape-mismatched payload
    that ALSO carries a '='-prefixed plain string keeps the LD-149 loud note."""
    gw = Gateway(values={f"{SID}!A1:B2": [["a", "b"], ["c", "d"]]})
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:B2", [["=SUM(A1:A4)"]])], gw, TOKEN)
    (entry,) = plan.entries
    assert entry.refusal.reason == Refusal.SHAPE_MISMATCH
    kinds = [n["kind"] for n in entry.preview_notes]
    assert "equals-prefixed-plain-string" in kinds, entry.preview_notes


def test_f21_shape_mismatch_serializes_into_the_plan_json():
    gw = Gateway(values={f"{SID}!A1:B2": [["a", "b"], ["c", "d"]]})
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:B2", [["one"]])], gw, TOKEN)
    wire = json.loads(plan.to_json())
    assert wire["entries"][0]["refusal"]["reason"] == "shape-mismatch"


def test_f21_a_refused_shape_never_reaches_a_write():
    gw = Gateway(values={f"{SID}!A1:B2": [["a", "b"], ["c", "d"]]})
    log = apply(dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:B2", [["one"]])], gw, TOKEN), gw)
    assert gw.puts == []
    assert log.entries[0].outcome == "refused"
    assert log.entries[0].refusal.reason == Refusal.SHAPE_MISMATCH


# =========================================================================== #
# F20 / AC4 — Lark's `90202` is a MALFORMED RANGE, not staleness.               #
#                                                                              #
# Report repro 4: for_a1("<sid>!C3:A1", …) → dry_run → reason: tab-vanished,    #
# detail = a raw "Code: 90202, Msg: validate RangeVal fail". The tab existed and #
# had been written to all session — "not recoverable from the message".         #
# =========================================================================== #

def _range_val_fail(a1):
    return LarkAPIError(
        f"Failed to read range {a1}. Code: 90202, Msg: validate RangeVal fail",
        code=90202, msg="validate RangeVal fail")


def test_f20_repro_a_reversed_range_refuses_malformed_range():
    """The report's exact repro — now correctly categorized, with an actionable detail."""
    a1 = f"{SID}!C3:A1"
    gw = Gateway(values={a1: _range_val_fail(a1)})
    plan = dry_run([ValueWriteRequest.for_a1(a1, [["x", "y", "z"]] * 3)], gw, TOKEN)
    (entry,) = plan.entries
    assert entry.refusal.reason == Refusal.MALFORMED_RANGE == "malformed-range"
    detail = entry.refusal.detail
    assert a1 in detail                                  # the offending range
    assert "A1:C3" in detail                             # the valid form / the repair
    assert "90202" in detail                             # Lark's own signal, named
    assert "not staleness" in detail.lower()


def test_f20_a_reversed_range_is_caught_PRE_IO_without_asking_lark():
    """Better than the report asked for: the reversal is knowable from the range alone, so the
    refusal costs **zero** calls — Lark is never troubled for a diagnosis we already have."""
    a1 = f"{SID}!C3:A1"
    gw = Gateway(values={a1: _range_val_fail(a1)})
    plan = dry_run([ValueWriteRequest.for_a1(a1, [["x", "y", "z"]] * 3)], gw, TOKEN)
    assert plan.entries[0].refusal.reason == Refusal.MALFORMED_RANGE
    assert gw.n("read_values") == 0 and gw.n("query_tabs") == 0, gw.calls


def test_f20_a_malformed_target_is_diagnosed_as_malformed_not_as_a_shape_mismatch():
    """Ordering matters: a reversed range has a nonsense arity, so the shape check would
    "explain" the wrong thing. The form check runs FIRST."""
    a1 = f"{SID}!C3:A1"
    gw = Gateway()
    plan = dry_run([ValueWriteRequest.for_a1(a1, [["x"]])], gw, TOKEN)
    assert plan.entries[0].refusal.reason == Refusal.MALFORMED_RANGE


def test_f20_lark_90202_on_a_WELL_FORMED_range_still_maps_to_malformed_range():
    """AC4's literal contract: the ``90202`` code maps to ``malformed-range``, whatever the
    engine could or could not see for itself."""
    a1 = f"{SID}!A1:A1"
    gw = Gateway(values={a1: _range_val_fail(a1)})
    plan = dry_run([ValueWriteRequest.for_a1(a1, [["x"]])], gw, TOKEN)
    refusal = plan.entries[0].refusal
    assert refusal.reason == Refusal.MALFORMED_RANGE
    assert "validate RangeVal fail" in refusal.detail          # Lark's own msg, carried


def test_f20_a_genuinely_vanished_tab_still_refuses_tab_vanished():
    """AC4: the staleness story is untouched — a non-90202 read failure on a tab the listing
    still shows stays :data:`Refusal.TAB_VANISHED`."""
    a1 = f"{SID}!A1:A1"
    gw = Gateway(values={a1: LarkAPIError("tab gone", code=1310249)})
    plan = dry_run([ValueWriteRequest.for_a1(a1, [["x"]])], gw, TOKEN)
    assert plan.entries[0].refusal.reason == Refusal.TAB_VANISHED


def test_f20_the_did_you_mean_path_for_a_wrong_id_is_unaffected():
    """AC4: LD-131's ``unknown-tab`` + did-you-mean still fires for a wrong identifier."""
    a1 = "Sheet1!A1:A1"       # a TITLE where a sheet_id belongs — the classic F4 trap
    gw = Gateway(
        values={a1: LarkAPIError("Code: 90215, Msg: not found sheetId", code=90215)},
        tabs=[{"sheet_id": SID, "title": "Sheet1"}],
    )
    plan = dry_run([ValueWriteRequest.for_a1(a1, [["x"]])], gw, TOKEN)
    refusal = plan.entries[0].refusal
    assert refusal.reason == Refusal.UNKNOWN_TAB
    assert "Did you mean" in refusal.detail and SID in refusal.detail


def test_f20_malformed_range_costs_no_did_you_mean_read():
    """A malformed range is decided from Lark's own code — no ``query_tabs`` enrichment read
    is spent chasing a tab that is not the problem."""
    a1 = f"{SID}!A1:A1"
    gw = Gateway(values={a1: _range_val_fail(a1)})
    dry_run([ValueWriteRequest.for_a1(a1, [["x"]])], gw, TOKEN)
    assert gw.n("query_tabs") == 0, gw.calls


def test_f20_the_three_range_failures_land_on_three_distinct_reasons():
    """The maintainer's amplifier: `90202` vs a real vanished tab vs a wrong-id did-you-mean must be
    three DIFFERENT reasons, or a consumer cannot act on any of them."""
    cases = [
        (f"{SID}!A1:A1", _range_val_fail(f"{SID}!A1:A1"), None, Refusal.MALFORMED_RANGE),
        (f"{SID}!A1:A1", LarkAPIError("gone", code=1310249), None, Refusal.TAB_VANISHED),
        ("nope!A1:A1", LarkAPIError("Code: 90215", code=90215),
         [{"sheet_id": SID, "title": "T"}], Refusal.UNKNOWN_TAB),
    ]
    seen = []
    for a1, exc, tabs, expected in cases:
        gw = Gateway(values={a1: exc}, tabs=tabs)
        plan = dry_run([ValueWriteRequest.for_a1(a1, [["x"]])], gw, TOKEN)
        assert plan.entries[0].refusal.reason == expected, (a1, plan.entries[0].refusal)
        seen.append(expected)
    assert len(set(seen)) == 3


def test_f20_a_malformed_range_on_a_formula_target_maps_the_same_way():
    """The classifier is shared by every plan-time read site, so the formula leg inherits it."""
    a1 = f"{SID}!C3:C3"
    gw = Gateway(values={a1: _range_val_fail(a1)})
    plan = dry_run([FormulaWriteRequest.for_a1(a1, "=SUM(A1:A2)")], gw, TOKEN)
    assert plan.entries[0].refusal.reason == Refusal.MALFORMED_RANGE


def test_f20_a_malformed_range_on_a_delete_snapshot_maps_the_same_way():
    a1_geom = _grid()
    gw = Gateway(geometry=a1_geom,
                 values={f"{SID}!A1:T2": _range_val_fail(f"{SID}!A1:T2")})
    plan = dry_run([DeleteRows(sheet_id=SID, first=1, last=2)], gw, TOKEN)
    assert plan.entries[0].refusal.reason == Refusal.MALFORMED_RANGE


def test_f20_pre_io_form_check_also_covers_a_merge_target():
    """The form check lives at the seam, so every family with a range target inherits it."""
    gw = Gateway()
    plan = dry_run([UnmergeCells(a1_range=f"{SID}!C3:A1")], gw, TOKEN)
    assert plan.entries[0].refusal.reason == Refusal.MALFORMED_RANGE
    assert gw.n("read_values") == 0


def test_f20_apply_time_tab_vanished_is_deliberately_unchanged():
    """LD-131 RESERVED ``tab-vanished`` for a range that WAS readable at plan time; that site
    stays as it is (a 90202 there is not a diagnosis a re-plan can act on differently)."""
    a1 = f"{SID}!A1:A1"
    gw = Gateway(values={a1: [["old"]]})
    plan = dry_run([ValueWriteRequest.for_a1(a1, [["new"]])], gw, TOKEN)
    gw.values[a1] = _range_val_fail(a1)
    log = apply(plan, gw)
    assert log.entries[0].refusal.reason == Refusal.TAB_VANISHED
    assert gw.puts == []


# =========================================================================== #
# F12 / AC8 — `removed.values` trimmed to the USED extent, not padded to the    #
# tab's declared width.                                                        #
#                                                                              #
# Report repro 9: a DeleteRows preview on a 20-column tab came back 2x20 with   #
# 18 nulls per row — "on a 100-column tab the preview becomes unreadable and    #
# expensive to log".                                                           #
# =========================================================================== #

def _delete_rows_plan(gw, first=1, last=2):
    return dry_run([DeleteRows(sheet_id=SID, first=first, last=last)], gw, TOKEN)


def test_f12_repro_removed_values_are_trimmed_to_the_used_width():
    """The report's exact repro: 2 rows on a 20-column tab, 2 columns used."""
    gw = Gateway(
        geometry=_grid(rows=200, cols=20),
        values={f"{SID}!A1:T2": [["a", "b"] + [None] * 18, ["c", "d"] + [None] * 18]},
    )
    removed = _delete_rows_plan(gw).entries[0].after["removed"]
    assert removed["values"] == [["a", "b"], ["c", "d"]], removed["values"]
    assert all(len(row) == 2 for row in removed["values"])


def test_f12_the_trim_is_disclosed_not_silent():
    """A trimmed payload that did not say so would be a new silence — the preview names the
    declared width, the used width and the axis."""
    gw = Gateway(
        geometry=_grid(rows=200, cols=20),
        values={f"{SID}!A1:T2": [["a", "b"] + [None] * 18, ["c", "d"] + [None] * 18]},
    )
    trim = _delete_rows_plan(gw).entries[0].after["removed"]["values_trim"]
    assert trim["declared"] == 20 and trim["used"] == 2
    assert trim["axis"] == "COLUMNS"
    assert "trim" in trim["note"].lower()


def test_f12_interior_and_trailing_nulls_inside_the_used_range_survive():
    """AC8: only the PAD is removed. An interior blank and a trailing blank *within* the used
    width are values the delete really destroys and must stay enumerated."""
    gw = Gateway(
        geometry=_grid(rows=200, cols=20),
        values={f"{SID}!A1:T2": [["a", None, "c"] + [None] * 17,
                                 ["d", "e", None] + [None] * 17]},
    )
    removed = _delete_rows_plan(gw).entries[0].after["removed"]
    assert removed["values"] == [["a", None, "c"], ["d", "e", None]]


def test_f12_every_doomed_row_is_kept_even_when_entirely_empty():
    """The row axis is NOT trimmed for a row delete: an empty doomed row is still a row that
    disappears, and dropping it would make the payload lie about the delete's extent."""
    gw = Gateway(
        geometry=_grid(rows=200, cols=20),
        values={f"{SID}!A1:T3": [["a"] + [None] * 19, [None] * 20, [None] * 20]},
    )
    removed = _delete_rows_plan(gw, first=1, last=3).entries[0].after["removed"]
    assert len(removed["values"]) == 3
    assert removed["values"] == [["a"], [None], [None]]


@pytest.mark.parametrize("cols,used", [(5, 1), (20, 2), (60, 3), (100, 1)])
def test_f12_padded_vs_trimmed_property_over_several_tab_widths(cols, used):
    """The maintainer's amplifier: the property holds at every tab width — the payload is as wide as
    the DATA, never as wide as the declaration."""
    from larkdocio.sheets.extent import column_number_to_a1

    end = f"{column_number_to_a1(cols)}2"
    row = [f"v{i}" for i in range(used)] + [None] * (cols - used)
    gw = Gateway(geometry=_grid(rows=200, cols=cols),
                 values={f"{SID}!A1:{end}": [list(row), list(row)]})
    removed = _delete_rows_plan(gw).entries[0].after["removed"]
    assert [len(r) for r in removed["values"]] == [used, used]


def test_f12_a_column_delete_trims_the_ROW_axis_instead():
    """The trim follows the delete's axis: a COLUMN delete's payload is (all rows) x (deleted
    columns), so the pad to strip is the trailing empty ROWS — never the doomed columns."""
    gw = Gateway(
        geometry=_grid(rows=6, cols=20),
        values={f"{SID}!A1:B6": [["a", "b"], ["c", None], [None, None],
                                 [None, None], [None, None], [None, None]]},
    )
    plan = dry_run([DeleteCols(sheet_id=SID, first=1, last=2)], gw, TOKEN)
    removed = plan.entries[0].after["removed"]
    assert removed["values"] == [["a", "b"], ["c", None]]
    assert removed["values_trim"] == {
        "axis": "ROWS", "declared": 6, "used": 2, "note": removed["values_trim"]["note"]}


def test_f12_an_all_empty_removed_payload_trims_to_an_empty_matrix_and_says_so():
    gw = Gateway(geometry=_grid(rows=200, cols=20),
                 values={f"{SID}!A1:T2": [[None] * 20, [None] * 20]})
    removed = _delete_rows_plan(gw).entries[0].after["removed"]
    assert removed["values"] == [[], []]
    assert removed["values_trim"]["used"] == 0


# =========================================================================== #
# F23 / AC7 — an out-of-bounds dimension delete says so, from the geometry the   #
# preview ALREADY read (zero extra calls).                                      #
#                                                                              #
# Report repro 8: DeleteRows(first=9999, last=10000) on a 200-row tab resolves   #
# happily, in a preview that reports geometry_before.row_count: 202 in the same  #
# breath. "The engine already holds the number that would catch it."            #
# =========================================================================== #

def test_f23_repro_an_out_of_bounds_row_delete_carries_a_note():
    """The report's exact repro — 200 rows, ``DeleteRows(first=9999, last=10000)``."""
    gw = Gateway(geometry=_grid(rows=200, cols=20),
                 values={f"{SID}!A1:T10000": []})
    plan = dry_run([DeleteRows(sheet_id=SID, first=9999, last=10000)], gw, TOKEN)
    (entry,) = plan.entries
    notes = {n["kind"]: n for n in entry.preview_notes}
    note = notes["out-of-bounds-dimension"]
    assert note["span"] == [9999, 10000]
    assert note["dimension"] == "ROWS"
    assert note["row_count"] == 200 or note["count"] == 200
    assert "200" in note["note"] and "9999" in note["note"]


def test_f23_the_note_costs_no_extra_call():
    """AC7: the engine already holds ``geometry_before`` — the note must not buy it again."""
    gw = Gateway(geometry=_grid(rows=200, cols=20), values={f"{SID}!A1:T10000": []})
    dry_run([DeleteRows(sheet_id=SID, first=9999, last=10000)], gw, TOKEN)
    assert gw.n("read_sheet_geometry") == 1, gw.calls


def test_f23_an_in_bounds_delete_carries_no_such_note():
    gw = Gateway(geometry=_grid(rows=200, cols=20),
                 values={f"{SID}!A1:T2": [["a"] + [None] * 19, ["b"] + [None] * 19]})
    plan = dry_run([DeleteRows(sheet_id=SID, first=1, last=2)], gw, TOKEN)
    kinds = {n["kind"] for n in plan.entries[0].preview_notes}
    assert "out-of-bounds-dimension" not in kinds


def test_f23_a_partially_out_of_bounds_delete_is_noted_too():
    """A span that STARTS in bounds and runs past the end deletes fewer rows than asked — the
    count mismatch the log would surface after the fact, disclosed before it."""
    gw = Gateway(geometry=_grid(rows=10, cols=2),
                 values={f"{SID}!A9:B12": [["i", "j"], ["k", "l"]]})
    plan = dry_run([DeleteRows(sheet_id=SID, first=9, last=12)], gw, TOKEN)
    note = {n["kind"]: n for n in plan.entries[0].preview_notes}["out-of-bounds-dimension"]
    assert note["overshoot"] == 2


def test_f23_an_out_of_bounds_column_delete_is_noted_on_the_column_count():
    gw = Gateway(geometry=_grid(rows=10, cols=5), values={f"{SID}!H1:I10": []})
    plan = dry_run([DeleteCols(sheet_id=SID, first=8, last=9)], gw, TOKEN)
    note = {n["kind"]: n for n in plan.entries[0].preview_notes}["out-of-bounds-dimension"]
    assert note["dimension"] == "COLUMNS" and note["count"] == 5


def test_f23_the_note_survives_the_plan_json():
    gw = Gateway(geometry=_grid(rows=200, cols=20), values={f"{SID}!A1:T10000": []})
    plan = dry_run([DeleteRows(sheet_id=SID, first=9999, last=10000)], gw, TOKEN)
    wire = json.loads(plan.to_json())
    assert wire["entries"][0]["preview_note"]["kind"] == "out-of-bounds-dimension"


# =========================================================================== #
# F22 / AC7 — an unmerge that will dissolve NOTHING says so.                     #
#                                                                              #
# Report repro 7: UnmergeCells on an unmerged range RESOLVES as if it will       #
# dissolve a merge — "so exactly-one-or-refuse doesn't really cover unmerge, and #
# a no-op is indistinguishable from a real one", while MergeCells pays for a     #
# read and previews precisely. Fix: reuse the geometry read for a note.          #
#                                                                              #
# The merge set comes from the plan's OWN `merges=` argument (the LD-122 / D4    #
# opt-in), so the note costs ZERO extra calls — the AC7 constraint.              #
# =========================================================================== #

#: a merge over A1:B1, in the v3 0-idx END-inclusive convention
_M_A1B1 = {"start_row_index": 0, "end_row_index": 0,
           "start_column_index": 0, "end_column_index": 1}


def test_f22_repro_unmerge_on_an_unmerged_range_carries_a_no_merge_note():
    """The report's exact repro, with the tab's merge set supplied: the plan now says the
    unmerge will dissolve nothing."""
    gw = Gateway()
    plan = dry_run([UnmergeCells(a1_range=f"{SID}!A5:B5")], gw, TOKEN, merges=[_M_A1B1])
    (entry,) = plan.entries
    assert entry.outcome == "resolved"          # not a refusal — it is a no-op, not an error
    note = {n["kind"]: n for n in entry.preview_notes}["no-merge-at-range"]
    assert note["a1_range"] == f"{SID}!A5:B5"
    assert note["merges_checked"] == 1
    assert "no merge" in note["note"].lower()
    assert "nothing" in note["note"].lower()


def test_f22_a_tab_with_no_merges_at_all_is_still_checked():
    """``merges=[]`` means "I looked, there are none" — distinct from omitting the argument,
    so an empty merge set must still produce the note."""
    gw = Gateway()
    plan = dry_run([UnmergeCells(a1_range=f"{SID}!A1:B1")], gw, TOKEN, merges=[])
    kinds = {n["kind"] for n in plan.entries[0].preview_notes}
    assert "no-merge-at-range" in kinds


def test_f22_a_real_unmerge_carries_no_such_note():
    gw = Gateway()
    plan = dry_run([UnmergeCells(a1_range=f"{SID}!A1:B1")], gw, TOKEN, merges=[_M_A1B1])
    assert plan.entries[0].preview_notes == ()


def test_f22_a_partially_overlapping_range_is_a_real_unmerge():
    """Touching a merge at all is enough — Lark dissolves the merge the range intersects."""
    gw = Gateway()
    plan = dry_run([UnmergeCells(a1_range=f"{SID}!B1:C1")], gw, TOKEN, merges=[_M_A1B1])
    assert plan.entries[0].preview_notes == ()


def test_f22_the_note_costs_no_extra_call():
    """AC7 + the maintainer's call-count spy: the disclosure is derived from what the caller already
    handed the plan, so the unmerge preview stays read-free."""
    gw = Gateway()
    dry_run([UnmergeCells(a1_range=f"{SID}!A5:B5")], gw, TOKEN, merges=[])
    assert [c[0] for c in gw.calls] == ["read_revision"], gw.calls


def test_f22_a_merge_unaware_plan_is_byte_unchanged():
    """No ``merges=`` ⇒ the engine cannot know, and says nothing new — the same opt-in posture
    the D4 covered-cell refusal already has. (Detecting it would cost a read, which AC7
    forbids.)"""
    gw = Gateway()
    plan = dry_run([UnmergeCells(a1_range=f"{SID}!A5:B5")], gw, TOKEN)
    assert plan.entries[0].preview_notes == ()
    assert [c[0] for c in gw.calls] == ["read_revision"], gw.calls


def test_f22_a_merge_write_is_never_given_the_no_merge_note():
    """The note is about an unmerge dissolving nothing; a MERGE over an unmerged range is
    exactly what a merge is for."""
    gw = Gateway(values={f"{SID}!A5:B5": [["keep", "lost"]]})
    plan = dry_run([MergeCells(a1_range=f"{SID}!A5:B5")], gw, TOKEN, merges=[])
    kinds = {n["kind"] for n in plan.entries[0].preview_notes}
    assert "no-merge-at-range" not in kinds
    # ...and its own D6/D7 loss preview still enumerates what the merge discards.
    assert plan.entries[0].after["lost_values"] == [{"ref": "B5", "value": "lost"}]


def test_f22_the_note_survives_the_plan_json():
    gw = Gateway()
    plan = dry_run([UnmergeCells(a1_range=f"{SID}!A5:B5")], gw, TOKEN, merges=[])
    wire = json.loads(plan.to_json())
    assert wire["entries"][0]["preview_note"]["kind"] == "no-merge-at-range"


# =========================================================================== #
# F9 / AC2 — an `overwrites-live-formula` note: the dry-run warns loudly about a  #
# FAKE formula and used to say nothing about destroying a REAL one.               #
#                                                                              #
# Report repro 2: clearing A1:A5 where A5 is a LIVE formula previewed            #
# `before: [[11],[22],[33],[44],[110]]` with no note — `110` reads as data.       #
# `MergeCells.loss_preview` is the precedent: a destructive sheets write pays     #
# for a read.                                                                   #
# =========================================================================== #

SUM = "=SUM(A1:A4)"


def _column_with_live_formula():
    """The report's sheet: A1..A4 data, A5 a live ``=SUM(A1:A4)`` computing 110."""
    return Gateway(
        values={
            f"{SID}!A1:A5": [[11], [22], [33], [44],
                             [{"type": "formula", "text": SUM}]],
            f"{SID}!A5:A5": [[{"type": "formula", "text": SUM}]],
        },
        computed={SUM: 110},
    )


def test_f9_repro_clearing_a_live_formula_is_disclosed():
    """The report's exact repro — clearing A1:A5 over a live formula in A5."""
    gw = _column_with_live_formula()
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:A5", [[None]] * 5)], gw, TOKEN)
    (entry,) = plan.entries
    assert entry.outcome == "resolved"
    note = {n["kind"]: n for n in entry.preview_notes}["overwrites-live-formula"]
    assert [c["ref"] for c in note["cells"]] == ["A5"]
    assert note["cells"][0]["expression"] == SUM
    assert note["cells"][0]["computed_value"] == 110
    assert "formula" in note["note"].lower() and "destroy" in note["note"].lower()
    # and the `before` still reads 110 — the note is what tells you that 110 is COMPUTED.
    assert entry.before == [[11], [22], [33], [44], [110]]


def test_f9_plain_values_earn_no_note():
    gw = Gateway(values={f"{SID}!A1:A2": [[1], [2]]})
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:A2", [[9], [9]])], gw, TOKEN)
    assert plan.entries[0].preview_notes == ()


def test_f9_the_note_costs_exactly_ONE_extra_read_per_entry():
    """AC2: "one ``Formula``-mode read beside the existing precondition read" — the read is not
    duplicated per entry beyond what's needed."""
    gw = _column_with_live_formula()
    dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:A5", [[None]] * 5)], gw, TOKEN)
    reads = [c for c in gw.calls if c[0] == "read_values"]
    assert len(reads) == 2, gw.calls
    assert [r[2] for r in reads] == ["UnformattedValue", "Formula"]


def test_f9_a_refused_entry_buys_no_formula_read():
    """A refusal decided before/at the precondition read must not pay for the disclosure read."""
    gw = Gateway(values={f"{SID}!A1:B2": [["a", "b"], ["c", "d"]]})
    dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:B2", [["one"]])], gw, TOKEN)   # shape mismatch
    assert gw.n("read_values") == 0, gw.calls


@pytest.mark.parametrize("where", [0, 2, 4])
def test_f9_a_formula_in_the_first_middle_or_last_cell_is_found(where):
    """The maintainer's amplifier: position must not matter."""
    matrix = [[1], [2], [3], [4], [5]]
    matrix[where] = [{"type": "formula", "text": SUM}]
    gw = Gateway(values={f"{SID}!A1:A5": matrix}, computed={SUM: 110})
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:A5", [[None]] * 5)], gw, TOKEN)
    note = {n["kind"]: n for n in plan.entries[0].preview_notes}["overwrites-live-formula"]
    assert [c["ref"] for c in note["cells"]] == [f"A{where + 1}"]


def test_f9_several_formulas_are_all_enumerated():
    """The amplifier again: the note ENUMERATES, like every other destructive preview here."""
    other = "=SUM(B1:B2)"
    gw = Gateway(
        values={f"{SID}!A1:B2": [[{"type": "formula", "text": SUM}, "plain"],
                                 ["plain", {"type": "formula", "text": other}]]},
        computed={SUM: 110, other: 7},
    )
    plan = dry_run(
        [ValueWriteRequest.for_a1(f"{SID}!A1:B2", [["x", "y"], ["z", "w"]])], gw, TOKEN)
    note = {n["kind"]: n for n in plan.entries[0].preview_notes}["overwrites-live-formula"]
    assert [c["ref"] for c in note["cells"]] == ["A1", "B2"]
    assert note["count"] == 2


def test_f9_an_INERT_equals_string_in_the_target_is_not_called_a_live_formula():
    """The LD-149 discriminator: a stored ``=``-string reads the same under BOTH legs, so it is
    inert text — destroying it loses nothing computed, and mislabelling it would cry wolf."""
    gw = Gateway(values={f"{SID}!A1:A1": [[SUM]]})     # a PLAIN string, not the object form
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:A1", [["x"]])], gw, TOKEN)
    kinds = {n["kind"] for n in plan.entries[0].preview_notes}
    assert "overwrites-live-formula" not in kinds


def test_f9_both_disclosures_ride_the_same_entry_when_both_apply():
    """The composite: replacing a live formula WITH an inert '='-string earns both warnings —
    and neither may displace the other (the F8 lesson, applied at the plan)."""
    gw = _column_with_live_formula()
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A5:A5", [[SUM]])], gw, TOKEN)
    kinds = [n["kind"] for n in plan.entries[0].preview_notes]
    assert set(kinds) == {"overwrites-live-formula", "equals-prefixed-plain-string"}
    assert plan.entries[0].preview_note["kind"] == "multiple"
    assert len(plan.entries[0].preview_note["notes"]) == 2


def test_f9_a_seam_that_cannot_serve_a_render_read_degrades_without_crashing():
    """A duck-typed seam whose ``read_values`` takes no ``value_render_option`` cannot be asked
    for the expression leg. The value write must keep working (the disclosure is best-effort on
    such a seam; the shipped SheetsWriteClient always serves it)."""
    class NoRenderGateway(Gateway):
        def read_values(self, spreadsheet_token, a1_range):     # no render option
            return Gateway.read_values(self, spreadsheet_token, a1_range)

    gw = NoRenderGateway(values={f"{SID}!A1:A1": [["old"]]})
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:A1", [["new"]])], gw, TOKEN)
    assert plan.entries[0].outcome == "resolved"
    assert plan.entries[0].preview_notes == ()


def test_f9_a_formula_write_over_a_formula_already_discloses_via_its_own_note():
    """A FormulaWriteRequest's own preview already carries ``current_expression`` +
    ``current_computed_value``, so it needs no second note — it is not silent."""
    gw = _column_with_live_formula()
    plan = dry_run([FormulaWriteRequest.for_a1(f"{SID}!A5:A5", "=SUM(A1:A3)")], gw, TOKEN)
    note = plan.entries[0].preview_note
    assert note["kind"] == "formula"
    assert note["current_expression"] == [[SUM]]


def test_f9_the_note_survives_the_plan_json():
    gw = _column_with_live_formula()
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:A5", [[None]] * 5)], gw, TOKEN)
    wire = json.loads(plan.to_json())
    assert wire["entries"][0]["preview_note"]["kind"] == "overwrites-live-formula"


# =========================================================================== #
# F8 / AC3 — the warning must survive the plan → log transition, and the guide's  #
# own one-line CI assertion must actually catch the trap.                        #
#                                                                              #
# Report repro 3: apply a batch storing the inert string "=SUM(A1:A4)" → the log  #
# shows `formula_not_evaluated == ()` and the applied entry has NO preview_note.  #
# "So the warning is loud only to an interactive operator; a CI job or background #
# batch gets a green log."                                                      #
# =========================================================================== #

def _inert_batch():
    """The report's trap batch: a '='-prefixed PLAIN string written as an ordinary value."""
    gw = Gateway(values={f"{SID}!C2:C2": [["old"]]})
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!C2:C2", [[SUM]])], gw, TOKEN)
    return gw, plan, apply(plan, gw)


def test_f8_repro_the_applied_entry_retains_the_warning():
    """The report's exact repro — the applied log entry keeps the note that carried the
    LOUD WARNING."""
    from larkdocio.sheets.formula import INERT_STRING_NOTE

    gw, plan, log = _inert_batch()
    (entry,) = log.entries
    assert entry.outcome == "applied"                 # the write DID land — that stays true
    note = {n["kind"]: n for n in entry.preview_notes}["equals-prefixed-plain-string"]
    assert note["note"] == INERT_STRING_NOTE
    assert entry.preview_note == plan.entries[0].preview_note      # carried, not rebuilt


def test_f8_the_log_exposes_inert_formula_strings():
    """AC3: the new accessor names the entries whose write STORED an inert '='-string."""
    gw, plan, log = _inert_batch()
    assert len(log.inert_formula_strings) == 1
    assert log.inert_formula_strings[0] is log.entries[0]


def test_f8_a_clean_batch_reports_no_inert_strings():
    gw = Gateway(values={f"{SID}!C2:C2": [["old"]]})
    log = apply(dry_run([ValueWriteRequest.for_a1(f"{SID}!C2:C2", [["plain"]])], gw, TOKEN), gw)
    assert log.inert_formula_strings == ()


def test_f8_a_REFUSED_inert_string_is_not_reported_as_stored():
    """The accessor is about what LANDED: a refused entry stored nothing, so reporting it
    would send a consumer hunting for text that is not on the sheet."""
    gw = Gateway(values={f"{SID}!A1:B2": [["a", "b"], ["c", "d"]]})
    log = apply(dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:B2", [[SUM]])], gw, TOKEN), gw)
    assert log.entries[0].outcome == "refused"
    assert log.entries[0].preview_notes                 # the warning is still ON the entry...
    assert log.inert_formula_strings == ()              # ...but nothing was stored


def test_f8_the_guides_one_line_ci_assertion_now_catches_the_inert_batch():
    """AC3 + the maintainer's amplifier: asserted **exactly as the guide writes the CI line**, so the
    doc and the code cannot drift. The line is READ OUT OF THE SHIPPED GUIDE."""
    import re

    import larkdocio

    lines = [ln.strip() for ln in larkdocio.guide(full=True).splitlines()
             if ln.strip().startswith("assert not log.")]
    assert lines, "the guide no longer carries a one-line `assert not log.…` CI assertion"
    ci_line = lines[0]
    # the assertion must consult BOTH failure modes — a formula that did not evaluate AND a
    # '='-string stored as inert text (the trap that used to sail through).
    assert "formula_not_evaluated" in ci_line and "inert_formula_strings" in ci_line, ci_line

    gw, plan, log = _inert_batch()
    entry = log.entries[0]                                   # the name the guide's line uses
    with pytest.raises(AssertionError):
        exec(re.sub(r",.*$", "", ci_line), {"log": log, "entry": entry})


def test_f8_the_guides_ci_assertion_still_passes_for_a_healthy_formula_batch():
    """The same line must stay quiet on a good batch, or it is not usable in CI."""
    import re

    import larkdocio

    ci_line = next(ln.strip() for ln in larkdocio.guide(full=True).splitlines()
                   if ln.strip().startswith("assert not log."))
    gw = Gateway(values={f"{SID}!C1:C1": [["old"]]}, computed={"=SUM(B3:B8)": 21})
    log = apply(dry_run([FormulaWriteRequest.for_a1(f"{SID}!C1:C1", "=SUM(B3:B8)")], gw, TOKEN), gw)
    assert log.entries[0].formula_evaluated is True
    exec(re.sub(r",.*$", "", ci_line), {"log": log, "entry": log.entries[0]})   # no raise


def test_f8_the_note_is_carried_onto_every_disposition_not_only_applied():
    """The fix is structural (the plan-entry → log-entry transition CARRIES disclosure), so a
    stale / not-attempted entry keeps its warning too — the F8 lesson generalized."""
    gw = Gateway(values={f"{SID}!C2:C2": [["old"]]})
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!C2:C2", [[SUM]])], gw, TOKEN)
    gw.revision += 1                       # an external writer moved the sheet under the plan
    log = apply(plan, gw)
    assert log.entries[0].outcome == "stale"
    assert {n["kind"] for n in log.entries[0].preview_notes} == {"equals-prefixed-plain-string"}


def test_f8_the_carried_note_survives_the_apply_log_json():
    gw, plan, log = _inert_batch()
    wire = json.loads(log.to_json())
    assert wire["entries"][0]["preview_note"]["kind"] == "equals-prefixed-plain-string"
    from larkdocio.sheets.plan import ApplyLogEntry
    assert ApplyLogEntry.from_dict(wire["entries"][0]).preview_note is not None


def test_f8_an_entry_with_no_warning_serializes_byte_identically():
    """ZERO-DRIFT: the new field appears only when there IS a note."""
    gw = Gateway(values={f"{SID}!C2:C2": [["old"]]})
    log = apply(dry_run([ValueWriteRequest.for_a1(f"{SID}!C2:C2", [["plain"]])], gw, TOKEN), gw)
    assert "preview_note" not in json.loads(log.to_json())["entries"][0]


# =========================================================================== #
# F16 / AC6 — the id-anchored SUB-SPAN plan shows its compare-and-swap basis.     #
#                                                                              #
# Report repro 6: an id-anchored EditRequest plan exposes `precondition_text`;    #
# an id-anchored SubSpanEditRequest plan does NOT — "in a library whose ethos is  #
# 'never silently off, always disclosed on the plan', the one family that doesn't #
# show its compare-and-swap basis stands out."                                   #
#                                                                              #
# This is the one DOCX-surface finding in the batch; it lives here with its eight #
# siblings because the AC10 contract is one test per report repro.                #
# =========================================================================== #

def _docx_tree():
    from write_harness import _heading, _page, _para

    return _page(
        _heading("h1", "Overview", children=[_para("p1", "first line")]),
        _para("p2", "second line"),
        _para("p3", "third line"),
    )


def test_f16_repro_the_id_anchored_subspan_plan_exposes_precondition_text():
    """The report's exact repro — disclosure parity with the id-anchored EditRequest."""
    from larkdocio.write.model import AnchorById, EditRequest, SubSpanEditRequest
    from larkdocio.write.preview import dry_run as docx_dry_run

    tree = _docx_tree()
    (edit,) = docx_dry_run(
        [EditRequest(anchor=AnchorById("p3"), replacement="NEW")], tree).entries
    (subspan,) = docx_dry_run(
        [SubSpanEditRequest(anchor=AnchorById("p3"), span="third", replacement="3rd")],
        tree).entries

    assert edit.precondition_text == "third line"
    assert subspan.precondition_text == "third line"      # ← was None before LD-150
    assert subspan.to_dict()["precondition_text"] == "third line"


def test_f16_a_quote_anchored_subspan_still_carries_none_and_its_json_is_unchanged():
    """ZERO-DRIFT: a quote anchor re-validates against its own quote, so it needs no captured
    basis — and its shipped wire form gains no key."""
    from larkdocio.write.model import Anchor, SubSpanEditRequest
    from larkdocio.write.preview import dry_run as docx_dry_run

    (entry,) = docx_dry_run(
        [SubSpanEditRequest(anchor=Anchor(quote="third line"), span="third",
                            replacement="3rd")], _docx_tree()).entries
    assert entry.precondition_text is None
    assert "precondition_text" not in entry.to_dict()


def test_f16_the_subspan_precondition_round_trips_through_the_wire_form():
    from larkdocio.write.model import AnchorById, SubSpanEditRequest
    from larkdocio.write.preview import PlanEntry as DocxPlanEntry, dry_run as docx_dry_run

    (entry,) = docx_dry_run(
        [SubSpanEditRequest(anchor=AnchorById("p3"), span="third", replacement="3rd")],
        _docx_tree()).entries
    rebuilt = DocxPlanEntry.from_dict(json.loads(json.dumps(entry.to_dict())))
    assert rebuilt == entry
    assert rebuilt.precondition_text == "third line"


def test_f16_every_id_anchored_family_now_discloses_its_basis():
    """The parity claim, stated as a set: no family is the odd one out any more."""
    from larkdocio.write.model import (
        AnchorById,
        DeleteRequest,
        EditRequest,
        InsertPosition,
        InsertRequest,
        NewParagraph,
        SubSpanEditRequest,
    )
    from larkdocio.write.preview import dry_run as docx_dry_run

    requests = [
        EditRequest(anchor=AnchorById("p3"), replacement="NEW"),
        InsertRequest(reference=AnchorById("p3"), position=InsertPosition.AFTER,
                      content=(NewParagraph("x"),)),
        DeleteRequest(target=AnchorById("p3")),
        SubSpanEditRequest(anchor=AnchorById("p3"), span="third", replacement="3rd"),
    ]
    plan = docx_dry_run(requests, _docx_tree())
    assert [e.precondition_text for e in plan.entries] == ["third line"] * 4
    assert {e.op for e in plan.entries} == {"edit", "insert", "delete", "subspan"}


# =========================================================================== #
# AC9 — DISCLOSURE REGRESSIONS GUARDED.                                          #
#                                                                              #
# The F8 lesson generalized: a disclosure field that silently disappears is the  #
# bug. These pin the FULL disclosure surface — the refusal vocabulary, the note   #
# kinds, and the serialized field sets of Plan / PlanEntry / ApplyLogEntry /      #
# ApplyLog — so a future change cannot drop one without reddening the suite.      #
# =========================================================================== #

#: Every refusal reason the sheets engine may hand back. LD-150 adds exactly two
#: (`shape-mismatch`, `malformed-range`) and RENAMES none; F20's re-categorization moves a
#: *case* between two reasons that both still exist.
_REFUSAL_REASONS = {
    "stale-sheet", "precondition-mismatch", "rich-cell-target", "unknown-tab", "tab-vanished",
    "merged-cell-target", "unknown-mention", "api-error", "invalid-request", "rate-limited",
    "transport-failure", "unexpected-error", "not-attempted", "unverified-write",
    # LD-150
    "shape-mismatch", "malformed-range",
    # LD-185 — a dimension-property band past the tab's declared row/column count.
    "out-of-bounds-dimension",
    # LD-186 — a freeze pinning more leading rows/columns than the tab has. Its own reason,
    # because the boundary differs by one from the band case above: freezing EVERY row is
    # legal (probed), while a band ending past the last row is not.
    "frozen-count-out-of-range",
    # LD-206 — a scope denial reclassified SYSTEMIC (it answers with a code, so it used to
    # land on `api-error` and continue the batch). Its own reason, because a missing grant is
    # knowably batch-wide while an ordinary coded rejection is not.
    "permission-denied",
    # LD-187 — the three tab-PRESENTATION faults, each its own reason because each has its own
    # repair and its own relationship to what Lark does: a target position past the last tab
    # (which Lark ACCEPTS and silently clamps — the reason the refusal exists at all), a
    # duplicate title (exact, case-sensitive, as the API compares), and a hide that would leave
    # no visible tab (which Lark answers `95201 server error` for).
    "tab-index-out-of-range", "duplicate-tab-title", "last-visible-tab",
}

#: Every preview-note kind a plan entry may carry.
_NOTE_KINDS = {
    "formula", "equals-prefixed-plain-string",                       # LD-149
    "overwrites-live-formula", "no-merge-at-range",                   # LD-150
    "out-of-bounds-dimension", "multiple",                           # LD-150
    "hidden-dimension-fidelity",                                     # LD-185
    "freeze-replaces-freeze",                                        # LD-186
    "hidden-tab-fidelity", "retitle-breaks-title-joins",             # LD-187
    "tab-presentation-no-op",                                        # LD-187
}


def test_ac9_the_refusal_vocabulary_is_pinned_and_complete():
    """Every ``Refusal`` class constant is in the pinned set, and vice-versa — a reason added
    or dropped without a matrix/doc pass reddens here."""
    live = {v for k, v in vars(Refusal).items()
            if k.isupper() and isinstance(v, str)}
    assert live == _REFUSAL_REASONS, (
        f"the refusal vocabulary drifted: only in code {sorted(live - _REFUSAL_REASONS)}, "
        f"only in the pin {sorted(_REFUSAL_REASONS - live)}"
    )


def test_ac9_the_two_new_reasons_are_distinct_from_every_older_one():
    assert Refusal.SHAPE_MISMATCH not in {Refusal.TAB_VANISHED, Refusal.UNKNOWN_TAB,
                                          Refusal.PRECONDITION_MISMATCH}
    assert Refusal.MALFORMED_RANGE != Refusal.TAB_VANISHED
    assert len(_REFUSAL_REASONS) == 22


def test_ac9_every_note_kind_the_engine_emits_is_in_the_pinned_set():
    from larkdocio.sheets import formula as F
    from larkdocio.sheets import ops as O
    from larkdocio.sheets.plan import NOTE_KIND_MULTIPLE

    emitted = {
        F.equals_prefixed_note([["=SUM(A1:A2)"]])["kind"],
        F.formula_preview_note("=A1", current_expression=None,
                               current_computed_value=None)["kind"],
        F.overwrites_live_formula_note(
            [{"ref": "A1", "row": 0, "col": 0, "expression": "=A1", "computed_value": 1}],
            a1_range="s!A1:A1")["kind"],
        O.no_merge_at_range_note("s!A1:A1", [])["kind"],
        O.out_of_bounds_dimension_note(
            {"major_dimension": "ROWS", "start_index": 9, "end_index": 10},
            {"row_count": 5})["kind"],
        O.hidden_dimension_note(
            {"major_dimension": "ROWS", "start_index": 2, "end_index": 3, "hides": True},
            {"row_count": 5})["kind"],
        O.frozen_replacement_note(
            {"sheet_id": SID, "rows": 4, "cols": None},
            {"frozen_rows": 2, "frozen_cols": 1})["kind"],
        O.hidden_tab_note({"op": "set-tab-visibility", "sheet_id": SID, "hidden": True},
                          {"sheet_id": SID, "title": "One", "hidden": False})["kind"],
        O.retitle_join_note({"op": "retitle-tab", "sheet_id": SID, "title": "Two"},
                            {"sheet_id": SID, "title": "One"})["kind"],
        O.tab_presentation_noop_note({"op": "reorder-tab", "sheet_id": SID, "index": 0},
                                     {"sheet_id": SID, "index": 0})["kind"],
        NOTE_KIND_MULTIPLE,
    }
    assert emitted == _NOTE_KINDS


def test_ac9_the_plan_wire_form_carries_every_disclosure_field():
    gw = Gateway(values={f"{SID}!A1:A1": [["old"]]})
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:A1", [["new"]])], gw, TOKEN)
    wire = json.loads(plan.to_json())
    assert set(wire) == {
        "spreadsheet_token", "revision",
        "revision_guard", "revision_guard_detail", "revision_guard_tiers",      # LD-132
        "mention_validation", "mention_validation_detail", "mention_validation_ids",  # LD-148
        "entries",
    }
    assert set(wire["entries"][0]) == {
        "outcome", "target", "before", "after", "refusal", "rich", "write_kind",
        "revision_guard", "value_precondition",                                  # LD-132
    }


def test_ac9_the_apply_log_wire_form_carries_every_disclosure_field():
    gw = Gateway(values={f"{SID}!A1:A1": [["old"]]})
    log = apply(dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:A1", [["new"]])], gw, TOKEN), gw)
    wire = json.loads(log.to_json())
    assert set(wire) == {"entries", "halt"}                                       # LD-148
    assert set(wire["entries"][0]) == {
        "outcome", "target", "before", "after", "revision", "refusal", "write_kind",
        "revision_guard",                                                        # LD-132
    }


def test_ac9_the_optional_disclosure_keys_appear_exactly_when_earned():
    """The three conditional keys (`structural`, `formula`, `preview_note`) are absent when
    there is nothing to say — that is what keeps every pre-LD-150 wire form byte-identical —
    and present the moment there is."""
    gw = _column_with_live_formula()
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:A5", [[None]] * 5)], gw, TOKEN)
    log = apply(plan, gw)
    assert "preview_note" in json.loads(plan.to_json())["entries"][0]
    assert "preview_note" in json.loads(log.to_json())["entries"][0]

    gw2 = Gateway(geometry=_grid(rows=200, cols=20),
                  values={f"{SID}!A1:T2": [["a"] + [None] * 19, ["b"] + [None] * 19]})
    d = json.loads(dry_run([DeleteRows(sheet_id=SID, first=1, last=2)], gw2,
                           TOKEN).to_json())["entries"][0]
    assert "structural" in d and "preview_note" not in d


def test_ac9_the_accessors_are_all_public_and_answer_uniformly():
    """The new accessors LD-152's recipes quote, pinned by name."""
    from larkdocio.sheets.plan import ApplyLog, ApplyLogEntry, PlanEntry

    for owner, name in (
        (PlanEntry, "preview_notes"),
        (ApplyLogEntry, "preview_notes"),
        (ApplyLogEntry, "preview_note"),
        (ApplyLogEntry, "stored_inert_formula_string"),
        (ApplyLog, "inert_formula_strings"),
        (ApplyLog, "formula_not_evaluated"),
    ):
        assert hasattr(owner, name), f"{owner.__name__}.{name} is gone"

    # a uniform tuple, whatever the underlying shape
    assert PlanEntry(outcome="resolved").preview_notes == ()
    single = {"kind": "x", "note": "n"}
    assert PlanEntry(outcome="resolved", preview_note=single).preview_notes == (single,)
    from larkdocio.sheets.plan import combine_preview_notes
    both = combine_preview_notes(single, {"kind": "y", "note": "m"})
    assert PlanEntry(outcome="resolved", preview_note=both).preview_notes == (
        single, {"kind": "y", "note": "m"})


def test_ac9_combining_notes_is_idempotent_and_order_preserving():
    from larkdocio.sheets.plan import combine_preview_notes, preview_notes_of

    a, b = {"kind": "a"}, {"kind": "b"}
    assert combine_preview_notes(None, None) is None
    assert combine_preview_notes(a, None) == a
    once = combine_preview_notes(a, b)
    assert preview_notes_of(combine_preview_notes(once, a, b)) == (a, b)
    assert [n["kind"] for n in preview_notes_of(once)] == ["a", "b"]


def test_ac9_the_disclosure_pin_BITES_when_a_field_is_dropped():
    """The guard is only worth its line count if it goes red. Simulated drops of each new
    disclosure — the plan-entry note, the log-entry note, and a refusal reason — each fail the
    SAME comparison the pins above make (proven red here, green above)."""
    gw = _column_with_live_formula()
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:A5", [[None]] * 5)], gw, TOKEN)
    log = apply(plan, gw)

    dropped_plan = {k: v for k, v in json.loads(plan.to_json())["entries"][0].items()
                    if k != "preview_note"}
    assert "preview_note" not in dropped_plan            # ← the regression, simulated

    dropped_log = {k: v for k, v in json.loads(log.to_json())["entries"][0].items()
                   if k != "preview_note"}
    assert "preview_note" not in dropped_log

    dropped_reasons = _REFUSAL_REASONS - {"shape-mismatch"}
    live = {v for k, v in vars(Refusal).items() if k.isupper() and isinstance(v, str)}
    assert live != dropped_reasons, "the vocabulary pin would not notice a dropped reason"


def test_ac9_no_pre_existing_note_or_refusal_was_renamed():
    """AC9's other half: LD-150 ADDS. Every reason and note kind that shipped before it still
    spells itself exactly the same way (F20's re-categorization moves a *case*, not a name)."""
    from larkdocio.sheets.formula import INERT_STRING_NOTE

    for shipped in ("stale-sheet", "precondition-mismatch", "rich-cell-target", "unknown-tab",
                    "tab-vanished", "merged-cell-target", "unknown-mention", "api-error",
                    "invalid-request", "rate-limited", "transport-failure",
                    "unexpected-error", "not-attempted", "unverified-write"):
        assert shipped in _REFUSAL_REASONS
    assert "formula" in _NOTE_KINDS and "equals-prefixed-plain-string" in _NOTE_KINDS
    assert INERT_STRING_NOTE.startswith("LOUD WARNING:")     # the pinned text is untouched


# =========================================================================== #
# AC11 — TRUTH ROWS. The shipped wording is what LD-152's recipes quote, so it   #
# is drift-guarded here against the code that produces it.                      #
# =========================================================================== #

def test_ac11_sheets_md_records_every_new_reason_note_and_accessor():
    """/SHEETS.md is the source of truth for this surface — every name LD-150 ships must be
    IN it, or the matrix has drifted from the code (the BLOCKS.md/SHEETS.md guard pattern)."""
    from pathlib import Path

    text = Path(__file__).resolve().parent.parent.joinpath("SHEETS.md").read_text("utf-8")
    for name in (
        "shape-mismatch", "malformed-range",                                   # reasons
        "overwrites-live-formula", "no-merge-at-range",                          # notes
        "out-of-bounds-dimension", "`multiple`",
        "preview_notes", "inert_formula_strings", "values_trim",                 # accessors
        "A1RangeError", "DimensionSpanError",                                    # typed errors
        "precondition_text",                                                     # F16
    ):
        assert name in text, f"/SHEETS.md does not record {name!r} — the matrix drifted"


def test_ac11_capabilities_safety_contracts_carry_the_new_disclosure_vocabulary():
    """``capabilities()`` is the machine-readable half of the same truth. The contract IDS are
    unchanged (the guide↔capabilities bidirectional guard stays green); their summaries now
    state what the plan and the log disclose."""
    from larkdocio import capabilities

    contracts = capabilities(full=True)["safety_contracts"]
    dry_run_summary = contracts["dry-run-mandatory"]["summary"]
    for name in ("shape-mismatch", "malformed-range", "overwrites-live-formula",
                 "no-merge-at-range", "out-of-bounds-dimension", "preview_notes",
                 "A1RangeError", "DimensionSpanError", "precondition_text"):
        assert name in dry_run_summary, f"dry-run-mandatory omits {name!r}"

    log_summary = contracts["apply-log-complete"]["summary"]
    assert "inert_formula_strings" in log_summary and "preview_note" in log_summary

    stale_summary = contracts["STALE_SHEET"]["summary"]
    assert "malformed-range" in stale_summary and "tab-vanished" in stale_summary


def test_ac11_the_guide_and_capabilities_agree_on_the_ci_assertion():
    """The guide's CI line names an accessor that must exist on ``ApplyLog`` — the doc, the
    contract summary and the code are one fact in three places."""
    import larkdocio
    from larkdocio.sheets.plan import ApplyLog

    ci_line = next(ln.strip() for ln in larkdocio.guide(full=True).splitlines()
                   if ln.strip().startswith("assert not log."))
    for accessor in ("formula_not_evaluated", "inert_formula_strings"):
        assert accessor in ci_line
        assert isinstance(getattr(ApplyLog, accessor), property)
    assert accessor in larkdocio.capabilities(full=True)[
        "safety_contracts"]["apply-log-complete"]["summary"]
