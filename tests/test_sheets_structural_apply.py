"""Offline unit tests for the plan-gated Sheets STRUCTURAL dimension writes
(LD-121).

The load-bearing trap this story exists to encode: **insert uses a 0-indexed
half-open span `[start,end)`; delete uses a 1-indexed inclusive span
`[start,end]`** (LD-107 Q4). A caller must be STRUCTURALLY UNABLE to pass the
wrong convention — so the caller-facing request objects are DISTINCT typed
semantic-span objects (:class:`InsertRowsAt`/:class:`InsertColsAt` carry a
``before_*`` position + a ``count``; :class:`DeleteRows`/:class:`DeleteCols`
carry a 1-indexed inclusive ``first``/``last``), and each converts to its
endpoint's native convention INTERNALLY. There is no raw ``(start,end)``
pass-through on the request surface.

These pin — all offline (an injected client seam), the story's binding gate is a
live insert/delete round-trip at QA:

* **AC1** — semantic-span → native convention, both directions, and the request
  model can't express a raw wrong-convention span;
* **AC2** — apply trusts the reply's ``addCount``/``delCount`` and MANDATORILY
  re-reads geometry after the write (never assumes parity); a ``delCount``
  mismatch is surfaced;
* **AC3** — the ``values_append INSERT_ROWS`` structural variant (D8);
* **AC4** — gated: ``Plan``→dry-run (previewing exactly what shifts)→apply,
  ``STALE_SHEET`` compare-and-swap, never a blind/unattended write.

The **test-rigor amplifier** ("go a bit nuts"): the index-convention guard as an
explicit torture test (insert ``[1,2)`` vs delete ``[2,3]`` with ``delCount 2``),
off-by-one at row 1 / the last row / single-row ranges, an ``N>1`` insert, a col
op vs a row op, and a ``delCount`` that disagrees with the requested span.
"""
import dataclasses
import json

import pytest

from log_reading_apply import reading_the_log
from larkdocio.sheets.write_apply import (
    AppendDimension,
    AppendRowsWithValues,
    DeleteCols,
    DeleteRows,
    InsertColsAt,
    InsertRowsAt,
    PlanEntry,
    Refusal,
    ValueWriteRequest,
    WriteOpKind,
    apply,
    dry_run,
    requires_merge_leg,
    requires_style_leg,
)
apply = reading_the_log(apply)

TOKEN = "shtxxxSTRUCT"
SID = "555c22"


# --------------------------------------------------------------------------- #
# The structural client seam — a duck-typed stand-in modelling a live sheet's   #
# geometry: a monotonic ``revision`` (+1 per write), a row/column count that    #
# shifts under structural writes, and a recorded call/geometry-read log. The    #
# dimension write replies mirror the LD-107 Q4 captures: DELETE carries         #
# ``delCount``; append(dimension) carries ``addCount``; insert_dimension_range  #
# carries ``data:{}`` (no count — the span width is authoritative).            #
# --------------------------------------------------------------------------- #

class FakeStructuralGateway:
    def __init__(self, *, revision=0, row_count=10, column_count=6, merges=None, values=None):
        self.revision = revision
        self.row_count = row_count
        self.column_count = column_count
        self.merges = list(merges or [])
        self.values = dict(values or {})
        self.geometry_reads = []       # [sheet_id] — recorded mandatory re-reads
        self.calls = []                # recorded structural writes, in order
        self.puts = []                 # [(a1, values)] — plain value writes (mixed batches)
        self.external_bumps = {}       # {read_revision_call_n: delta}
        self._rev_reads = 0
        self.del_count_override = None  # force a reply delCount != the requested span
        self.add_count_override = None

    # -- reads (un-throttled write-side reads) --
    def read_revision(self, spreadsheet_token):
        self._rev_reads += 1
        self.revision += self.external_bumps.pop(self._rev_reads, 0)
        return self.revision

    def read_values(self, spreadsheet_token, a1_range, value_render_option="UnformattedValue"):
        return self.values.get(a1_range, [])

    def read_sheet_geometry(self, spreadsheet_token, sheet_id):
        self.geometry_reads.append(sheet_id)
        return {"row_count": self.row_count, "column_count": self.column_count,
                "merges": list(self.merges)}

    # -- structural writes (each bumps revision +1, spike Q4) --
    def insert_dimension_range(self, spreadsheet_token, sheet_id, major_dimension, start_index, end_index, inherit_style=None):
        n = end_index - start_index  # 0-idx half-open span width
        self.calls.append(("insert", sheet_id, major_dimension, start_index, end_index))
        if major_dimension == "ROWS":
            self.row_count += n
        else:
            self.column_count += n
        self.revision += 1
        return {}  # the insert reply omits any count (fixture data:{})

    def delete_dimension_range(self, spreadsheet_token, sheet_id, major_dimension, start_index, end_index):
        n = end_index - start_index + 1  # 1-idx inclusive span width
        self.calls.append(("delete", sheet_id, major_dimension, start_index, end_index))
        if major_dimension == "ROWS":
            self.row_count -= n
        else:
            self.column_count -= n
        self.revision += 1
        del_count = self.del_count_override if self.del_count_override is not None else n
        return {"delCount": del_count, "majorDimension": major_dimension}

    def append_dimension(self, spreadsheet_token, sheet_id, major_dimension, length):
        self.calls.append(("append-dim", sheet_id, major_dimension, length))
        if major_dimension == "ROWS":
            self.row_count += length
        else:
            self.column_count += length
        self.revision += 1
        add_count = self.add_count_override if self.add_count_override is not None else length
        return {"addCount": add_count, "majorDimension": major_dimension}

    def append_values(self, spreadsheet_token, a1_range, values, insert_data_option=None):
        self.calls.append(("append-values", a1_range, insert_data_option))
        if insert_data_option == "INSERT_ROWS":
            self.row_count += len(values)
        self.revision += 1
        return {"revision": self.revision, "updates": {"updatedRows": len(values)}}

    def put_values(self, spreadsheet_token, a1_range, values):
        self.puts.append((a1_range, values))
        self.values[a1_range] = values
        self.revision += 1
        return {"revision": self.revision}


# =========================================================================== #
# AC1 — semantic-span request → NATIVE convention (the structural guard).       #
# Insert is 0-idx half-open [start,end); delete is 1-idx inclusive [start,end]. #
# =========================================================================== #

def test_insert_rows_at_converts_to_0idx_half_open_native_span():
    # insert 1 row BEFORE 1-indexed row 2 → native [1, 2) (the LD-107 insert_row capture).
    d = InsertRowsAt(SID, before_row=2, count=1).descriptor()
    assert d["op"] == "insert"
    assert d["major_dimension"] == "ROWS"
    assert (d["start_index"], d["end_index"]) == (1, 2)
    assert d["convention"] == "0-index-half-open"
    assert d["expected_count"] == 1


def test_insert_cols_at_converts_to_0idx_half_open_native_span():
    d = InsertColsAt(SID, before_col=2, count=1).descriptor()
    assert d["op"] == "insert"
    assert d["major_dimension"] == "COLUMNS"
    assert (d["start_index"], d["end_index"]) == (1, 2)
    assert d["convention"] == "0-index-half-open"


def test_delete_rows_converts_to_1idx_inclusive_native_span():
    # delete 1-indexed rows 2..3 inclusive → native [2, 3], expected 2 rows removed
    # (the LD-107 delete_row capture: delCount 2).
    d = DeleteRows(SID, first=2, last=3).descriptor()
    assert d["op"] == "delete"
    assert d["major_dimension"] == "ROWS"
    assert (d["start_index"], d["end_index"]) == (2, 3)
    assert d["convention"] == "1-index-inclusive"
    assert d["expected_count"] == 2


def test_delete_cols_converts_to_1idx_inclusive_native_span():
    d = DeleteCols(SID, first=2, last=3).descriptor()
    assert d["op"] == "delete"
    assert d["major_dimension"] == "COLUMNS"
    assert (d["start_index"], d["end_index"]) == (2, 3)
    assert d["convention"] == "1-index-inclusive"
    assert d["expected_count"] == 2


def test_the_two_conventions_diverge_for_the_same_target_rows():
    # THE trap, as an explicit torture test: to affect the 2nd row (0-idx 1) the two
    # ops emit DIFFERENT raw spans — insert-before-row-2 → [1,2); delete-row-2 → [2,2].
    ins = InsertRowsAt(SID, before_row=2, count=1).descriptor()
    dele = DeleteRows(SID, first=2, last=2).descriptor()
    assert (ins["start_index"], ins["end_index"]) == (1, 2)
    assert (dele["start_index"], dele["end_index"]) == (2, 2)
    assert ins["convention"] != dele["convention"]


def test_insert_of_n_greater_than_one_widens_the_half_open_span():
    # multi-row insert is expressed NATIVELY by the semantic-span model (Dev's
    # documented phase-1 call, the Sheets rich/structural-write spec Open Questions): 3 rows before row 5 → [4, 7).
    d = InsertRowsAt(SID, before_row=5, count=3).descriptor()
    assert (d["start_index"], d["end_index"]) == (4, 7)
    assert d["expected_count"] == 3


def test_insert_before_row_1_is_native_span_0_to_count():
    # off-by-one torture at the top edge: insert before row 1 → [0, count).
    d = InsertRowsAt(SID, before_row=1, count=2).descriptor()
    assert (d["start_index"], d["end_index"]) == (0, 2)


def test_delete_single_first_row_is_native_1_to_1():
    # off-by-one torture: deleting only row 1 → native [1, 1], one row.
    d = DeleteRows(SID, first=1, last=1).descriptor()
    assert (d["start_index"], d["end_index"]) == (1, 1)
    assert d["expected_count"] == 1


# --- the request model CANNOT express a raw wrong-convention span (AC1) --- #

def _field_names(cls):
    return {f.name for f in dataclasses.fields(cls)}


def test_insert_requests_expose_only_semantic_before_position_no_raw_indices():
    for cls, pos in ((InsertRowsAt, "before_row"), (InsertColsAt, "before_col")):
        fields = _field_names(cls)
        assert pos in fields and "count" in fields
        # no raw span / no delete-shaped span the caller could hand-build wrong
        assert not (fields & {"start_index", "end_index", "first", "last"})


def test_delete_requests_expose_only_first_last_no_raw_indices():
    for cls in (DeleteRows, DeleteCols):
        fields = _field_names(cls)
        assert {"first", "last"} <= fields
        assert not (fields & {"start_index", "end_index", "before_row", "before_col", "count"})


def test_insert_rejects_sub_1_before_position_and_nonpositive_count():
    with pytest.raises(ValueError):
        InsertRowsAt(SID, before_row=0, count=1)
    with pytest.raises(ValueError):
        InsertRowsAt(SID, before_row=1, count=0)


def test_delete_rejects_inverted_or_sub_1_span():
    with pytest.raises(ValueError):
        DeleteRows(SID, first=3, last=2)   # inverted
    with pytest.raises(ValueError):
        DeleteRows(SID, first=0, last=2)   # sub-1


def test_structural_requests_touch_the_structure_op_kind():
    for req in (InsertRowsAt(SID, before_row=2), DeleteRows(SID, first=2, last=3),
                InsertColsAt(SID, before_col=2), DeleteCols(SID, first=2, last=2),
                AppendDimension(SID, "ROWS", 2), AppendRowsWithValues("555c22!A1:B1", [["x", "y"]])):
        assert req.op_kinds == (WriteOpKind.STRUCTURE,)
    # a structure write needs BOTH the export style leg and the live merge leg at S6
    assert requires_style_leg((WriteOpKind.STRUCTURE,)) is True
    assert requires_merge_leg((WriteOpKind.STRUCTURE,)) is True


# =========================================================================== #
# AC4 — gated: dry-run previews EXACTLY what shifts, ZERO writes.               #
# =========================================================================== #

def test_dry_run_previews_the_insert_shift_and_writes_nothing():
    gw = FakeStructuralGateway(revision=4)
    plan = dry_run([InsertRowsAt(SID, before_row=2, count=1)], gw, TOKEN)
    (entry,) = plan.entries
    assert entry.is_resolved
    assert entry.structural["op"] == "insert"
    shift = entry.after
    assert shift["kind"] == "insert"
    assert shift["dimension"] == "ROWS"
    assert shift["at_index_0based"] == 1
    assert shift["count"] == 1
    assert shift["shift_delta"] == 1  # rows at/after 0-idx 1 shift DOWN by 1
    assert gw.calls == [] and gw.puts == []  # zero writes at plan time


def test_dry_run_previews_the_delete_shift():
    gw = FakeStructuralGateway(revision=4)
    plan = dry_run([DeleteRows(SID, first=2, last=3)], gw, TOKEN)
    shift = plan.entries[0].after
    assert shift["kind"] == "delete"
    assert shift["at_index_0based"] == 1     # 1-indexed row 2 → 0-idx 1
    assert shift["count"] == 2
    assert shift["shift_delta"] == -2        # rows after shift UP by 2


def test_dry_run_caches_revision_at_plan_time():
    gw = FakeStructuralGateway(revision=9)
    plan = dry_run([InsertRowsAt(SID, before_row=2)], gw, TOKEN)
    assert plan.revision == 9
    assert plan.spreadsheet_token == TOKEN


def test_apply_rejects_a_bare_structural_request_not_a_plan():
    gw = FakeStructuralGateway()
    with pytest.raises(TypeError):
        apply([InsertRowsAt(SID, before_row=2)], gw)  # never a blind/unattended write


# =========================================================================== #
# AC2 — trust addCount/delCount + MANDATORY geometry re-read.                   #
# =========================================================================== #

def test_insert_applies_writes_native_span_and_re_reads_geometry():
    gw = FakeStructuralGateway(revision=0, row_count=9)
    plan = dry_run([InsertRowsAt(SID, before_row=2, count=1)], gw, TOKEN)
    log = apply(plan, gw)
    (entry,) = log.entries
    assert entry.is_applied
    # native 0-idx half-open [1,2) reached the client
    assert gw.calls == [("insert", SID, "ROWS", 1, 2)]
    # the MANDATORY geometry re-read fired after the write
    assert gw.geometry_reads, "apply must re-read geometry after a structural write"
    assert entry.structural["observed_delta"] == 1   # row_count 9 -> 10
    assert entry.structural["expected_count"] == 1
    assert entry.structural["shift_verified"] is True
    assert entry.revision == 1                        # every write bumps +1


def test_delete_trusts_reply_delcount_and_re_reads_geometry():
    gw = FakeStructuralGateway(revision=0, row_count=9)
    plan = dry_run([DeleteRows(SID, first=2, last=3)], gw, TOKEN)
    log = apply(plan, gw)
    entry = log.entries[0]
    assert entry.is_applied
    assert gw.calls == [("delete", SID, "ROWS", 2, 3)]  # 1-idx inclusive
    assert gw.geometry_reads
    assert entry.structural["reply_count"] == 2          # trusted delCount from the reply
    assert entry.structural["observed_delta"] == -2      # row_count 9 -> 7
    assert entry.structural["count_mismatch"] is False


def test_delete_delcount_mismatch_is_surfaced_but_applied():
    # NEVER assume parity: a reply delCount that disagrees with the requested span is
    # surfaced (recorded), trusting the reply's authoritative count.
    gw = FakeStructuralGateway(revision=0, row_count=20)
    gw.del_count_override = 5  # the API removed a different count than we asked for
    plan = dry_run([DeleteRows(SID, first=2, last=3)], gw, TOKEN)  # expected 2
    entry = apply(plan, gw).entries[0]
    assert entry.is_applied
    assert entry.structural["expected_count"] == 2
    assert entry.structural["reply_count"] == 5
    assert entry.structural["count_mismatch"] is True
    assert "5" in entry.structural["count_mismatch_detail"]
    assert "2" in entry.structural["count_mismatch_detail"]


def test_insert_reply_omits_count_so_span_width_is_authoritative():
    # insert_dimension_range returns data:{} — no count. The engine trusts the
    # requested span width, and the geometry re-read confirms the shift.
    gw = FakeStructuralGateway(revision=0, row_count=5)
    entry = apply(dry_run([InsertRowsAt(SID, before_row=1, count=3)], gw, TOKEN), gw).entries[0]
    assert entry.structural["reply_count"] is None
    assert entry.structural["expected_count"] == 3
    assert entry.structural["observed_delta"] == 3
    assert entry.structural["shift_verified"] is True


def test_append_dimension_trusts_reply_addcount():
    gw = FakeStructuralGateway(revision=0, row_count=5)
    entry = apply(dry_run([AppendDimension(SID, "ROWS", 3)], gw, TOKEN), gw).entries[0]
    assert entry.is_applied
    assert gw.calls == [("append-dim", SID, "ROWS", 3)]
    assert entry.structural["reply_count"] == 3   # addCount trusted
    assert entry.structural["observed_delta"] == 3
    assert entry.structural["count_mismatch"] is False


def test_column_delete_shifts_the_column_axis_not_rows():
    gw = FakeStructuralGateway(revision=0, row_count=8, column_count=6)
    entry = apply(dry_run([DeleteCols(SID, first=2, last=3)], gw, TOKEN), gw).entries[0]
    assert gw.calls == [("delete", SID, "COLUMNS", 2, 3)]
    assert entry.structural["observed_delta"] == -2   # column_count 6 -> 4
    assert gw.row_count == 8                            # rows untouched


# =========================================================================== #
# AC3 — the values_append INSERT_ROWS structural variant (D8).                  #
# =========================================================================== #

def test_append_rows_with_values_is_a_structural_insert_rows_append():
    gw = FakeStructuralGateway(revision=0, row_count=4)
    req = AppendRowsWithValues("555c22!A1:B1", [["x", "y"], ["z", "w"]])
    assert req.op_kinds == (WriteOpKind.STRUCTURE,)
    log = apply(dry_run([req], gw, TOKEN), gw)
    entry = log.entries[0]
    assert entry.is_applied
    # writes via values_append with ?insertDataOption=INSERT_ROWS (structural)
    assert gw.calls == [("append-values", "555c22!A1:B1", "INSERT_ROWS")]
    assert entry.structural["op"] == "append-values"
    assert entry.structural["expected_count"] == 2   # two rows inserted
    assert entry.structural["observed_delta"] == 2


def test_append_rows_with_values_is_preview_gated_never_blind():
    gw = FakeStructuralGateway(revision=0, row_count=4)
    plan = dry_run([AppendRowsWithValues("555c22!A1:B1", [["x", "y"]])], gw, TOKEN)
    assert plan.entries[0].is_resolved
    assert plan.entries[0].structural["op"] == "append-values"
    assert gw.calls == []  # dry-run wrote nothing (preview-gated, D2)


# =========================================================================== #
# AC4 — STALE_SHEET compare-and-swap on structural writes; never unattended.    #
# =========================================================================== #

def test_structural_write_is_stale_sheet_guarded_no_write():
    gw = FakeStructuralGateway(revision=2, row_count=9)
    plan = dry_run([InsertRowsAt(SID, before_row=2)], gw, TOKEN)
    gw.external_bumps = {2: 1}  # an external writer bumps revision before apply's re-read
    log = apply(plan, gw)
    (entry,) = log.entries
    assert not entry.is_applied
    assert entry.refusal.reason == Refusal.STALE_SHEET
    assert gw.calls == []            # STALE_SHEET → no structural write
    assert gw.geometry_reads == []   # not even the re-read fires on a skipped write


def test_delete_stale_mid_batch_only_that_one_skips():
    gw = FakeStructuralGateway(revision=1, row_count=20)
    plan = dry_run([
        InsertRowsAt(SID, before_row=2, count=1),
        DeleteRows(SID, first=5, last=6),
    ], gw, TOKEN)
    # read_revision order: #1 dry_run cache; #2 insert pre-read; insert writes (rev+1);
    # #3 insert POST-write metainfo fallback (the insert reply omits revision, spike Q4);
    # #4 delete pre-read (external bump here → delete stale).
    gw.external_bumps = {4: 1}
    log = apply(plan, gw)
    assert [e.outcome for e in log.entries] == ["applied", "stale"]
    assert gw.calls == [("insert", SID, "ROWS", 1, 2)]  # the stale delete never fired


def test_structural_batch_advances_the_compare_and_swap_anchor():
    # our own structural writes bump revision +1 each; a batch must not self-poison.
    gw = FakeStructuralGateway(revision=0, row_count=20, column_count=10)
    plan = dry_run([
        InsertRowsAt(SID, before_row=2, count=1),
        DeleteCols(SID, first=3, last=3),
        AppendDimension(SID, "ROWS", 2),
    ], gw, TOKEN)
    log = apply(plan, gw)
    assert [e.outcome for e in log.entries] == ["applied", "applied", "applied"]
    assert len(gw.calls) == 3


def test_structural_and_value_writes_batch_in_one_plan_in_order():
    gw = FakeStructuralGateway(revision=0, row_count=9, values={"555c22!A1:A1": [["a0"]]})
    plan = dry_run([
        ValueWriteRequest.for_a1("555c22!A1:A1", [["a1"]]),
        InsertRowsAt(SID, before_row=2, count=1),
    ], gw, TOKEN)
    log = apply(plan, gw)
    assert [e.outcome for e in log.entries] == ["applied", "applied"]
    assert gw.puts == [("555c22!A1:A1", [["a1"]])]
    assert gw.calls == [("insert", SID, "ROWS", 1, 2)]


# =========================================================================== #
# Serialization — a structural plan/apply-log entry is JSON round-trippable.    #
# =========================================================================== #

def test_structural_plan_entry_round_trips_through_json():
    gw = FakeStructuralGateway(revision=0, row_count=9)
    plan = dry_run([InsertRowsAt(SID, before_row=2, count=1)], gw, TOKEN)
    d = plan.entries[0].to_dict()
    assert json.loads(json.dumps(d)) == d
    assert d["structural"]["op"] == "insert"
    assert d["target"] is None
    back = PlanEntry.from_dict(d)
    assert back.structural["op"] == "insert"
    assert back.target is None


def test_structural_apply_log_is_json_serializable():
    gw = FakeStructuralGateway(revision=0, row_count=9)
    log = apply(dry_run([DeleteRows(SID, first=2, last=3)], gw, TOKEN), gw)
    d = log.to_dict()
    assert json.loads(json.dumps(d)) == d
    assert d["entries"][0]["structural"]["op"] == "delete"
