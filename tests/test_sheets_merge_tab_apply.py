"""Offline unit tests for the plan-gated Sheets MERGE/UNMERGE + TAB writes
(LD-122).

This story adds, on top of LD-121's structural dimension writes:

* **AC1** — merge/unmerge encode + write through the gated engine; the resulting
  ``merges`` array is verified by the **merge leg** (LD-116's v3 ``merges`` diff).
* **AC2** — the engine **models a merge's fate** under structural edits:
  insert-inside → **grow**, insert-outside → **shift**, delete-intersecting →
  **shrink**, shrink-to-1×1 → **dissolve** (LD-107 Q4). Each fate is asserted
  against the byte-captured physics in
  ``tests/captures/sheets-write-spike/captures/04-structural-safety.json``.
* **AC3** — tab add/copy/delete via ``sheets_batch_update``; the reply's new
  ``sheetId`` is captured; a tab **delete** carries the removed tab's identity in
  the apply-log (D5, destructive-safe); a copy duplicates the source's merges.
* **AC4** — a value write targeting a merged/**covered** cell **refuses** (typed).
* **AC5** — merge/tab writes are gated (``Plan``→dry-run→apply) + ``STALE_SHEET``
  compare-and-swap guarded, never a blind/unattended write.

The **test-rigor amplifier** ("go a bit nuts"): the full merge-fate matrix proven
from the Q4 fixture (grow / shift / shrink / dissolve), a shrink-to-1×1 dissolve
torture case, the merge-over-data **loss preview** completeness (every covered
non-null value enumerated), an overlapping-covered-cell write refusal, a
copySheet that duplicates merges, and a tab delete's removed-identity payload.
"""
import json
from pathlib import Path

import pytest

from log_reading_apply import reading_the_log
from larkdocio.sheets.write_apply import (
    AddTab,
    CopyTab,
    DeleteTab,
    MergeCells,
    Refusal,
    UnmergeCells,
    ValueWriteRequest,
    WriteOpKind,
    apply,
    dry_run,
    predict_merge_fate,
    predict_merge_fates,
    requires_merge_leg,
    requires_style_leg,
)
apply = reading_the_log(apply)

TOKEN = "shtxxxMERGETAB"
SID = "555c22"

_FIXTURE = json.loads(
    (Path(__file__).resolve().parent.parent
     / "tests" / "captures" / "sheets-write-spike" / "captures" / "04-structural-safety.json").read_text(encoding="utf-8")
)


def _mtuple(m):
    """Normalize a v3 ``merges`` dict → ``(start_row, end_row, start_col, end_col)``."""
    return (m["start_row_index"], m["end_row_index"],
            m["start_column_index"], m["end_column_index"])


# The structural edit that produced each fixture STEP transition (LD-107 Q4 walk):
# baseline → +1 row @0-idx1 → +1 col @0-idx1 → delete 0-idx rows[1,2] → delete 0-idx cols[2,3].
_STEP_EDITS = [
    dict(kind="insert", dimension="ROWS", at_index_0based=1, count=1),
    dict(kind="insert", dimension="COLUMNS", at_index_0based=1, count=1),
    dict(kind="delete", dimension="ROWS", at_index_0based=1, count=2),
    dict(kind="delete", dimension="COLUMNS", at_index_0based=2, count=2),
]


# =========================================================================== #
# AC2 — the merge-fate model, proven end-to-end against the Q4 fixture walk.     #
# =========================================================================== #

def test_merge_fate_model_reproduces_every_fixture_step_transition():
    """Apply each captured structural edit to the prior step's merges and assert the
    surviving set EXACTLY equals the next step's captured ``merges`` — the whole
    grow/shift/shrink/dissolve physics, byte-checked against the live capture."""
    steps = _FIXTURE["steps"]
    for i, edit in enumerate(_STEP_EDITS):
        before = [_mtuple(m) for m in steps[i]["merges"]]
        expected_after = {_mtuple(m) for m in steps[i + 1]["merges"]}
        fates = predict_merge_fates(before, **edit)
        survived = {f.after for f in fates if f.after is not None}
        assert survived == expected_after, (
            f"step {i}->{i+1} ({edit}) fate mismatch: got {sorted(survived)} "
            f"expected {sorted(expected_after)}"
        )


def test_insert_outside_above_shifts_the_whole_merge():
    # baseline M1 B2:C3 = rows[1,2] cols[1,2]; insert a row @0-idx1 (at the merge's
    # start boundary) → the WHOLE merge shifts down by 1 (SHIFT).
    m1 = (1, 2, 1, 2)
    f = predict_merge_fate(m1, kind="insert", dimension="ROWS", at_index_0based=1, count=1)
    assert f.after == (2, 3, 1, 2)
    assert f.fate == "shift"


def test_insert_inside_grows_the_merge():
    # baseline M2 A6:D6 = rows[5,5] cols[0,3]; after the row insert it is rows[6,6];
    # inserting a COLUMN @0-idx1 lands INSIDE its col span [0,3] → the merge GROWS
    # (end_col 3->4, start_col unchanged).
    m2 = (6, 6, 0, 3)
    f = predict_merge_fate(m2, kind="insert", dimension="COLUMNS", at_index_0based=1, count=1)
    assert f.after == (6, 6, 0, 4)
    assert f.fate == "grow"


def test_delete_intersecting_shrinks_the_merge():
    # M1 rows[2,3] cols[2,3]; delete 0-idx rows [1,2] (count 2) intersects the merge's
    # top row and removes a row above it → SHRINK (2 rows -> 1) + shift up to rows[1,1].
    m1 = (2, 3, 2, 3)
    f = predict_merge_fate(m1, kind="delete", dimension="ROWS", at_index_0based=1, count=2)
    assert f.after == (1, 1, 2, 3)
    assert f.fate == "shrink"


def test_delete_removing_an_entire_axis_dissolves_the_merge():
    # M1 rows[1,1] cols[2,3]; delete 0-idx cols [2,3] removes BOTH of its columns →
    # the merge vanishes entirely (DISSOLVE).
    m1 = (1, 1, 2, 3)
    f = predict_merge_fate(m1, kind="delete", dimension="COLUMNS", at_index_0based=2, count=2)
    assert f.after is None
    assert f.fate == "dissolve"


def test_shrink_to_single_cell_dissolves_not_just_full_removal():
    # A 1×2 merge (rows[0,0] cols[0,1]); delete 0-idx col [1] leaves a lone 1×1 cell →
    # a single cell can't be a merge → DISSOLVE (the shrink-to-1×1 branch, distinct from
    # the full-axis-removal branch above).
    m = (0, 0, 0, 1)
    f = predict_merge_fate(m, kind="delete", dimension="COLUMNS", at_index_0based=1, count=1)
    assert f.after is None
    assert f.fate == "dissolve"


def test_insert_below_the_merge_leaves_it_unaffected():
    m = (1, 2, 1, 2)  # B2:C3
    f = predict_merge_fate(m, kind="insert", dimension="ROWS", at_index_0based=9, count=1)
    assert f.after == (1, 2, 1, 2)
    assert f.fate == "unaffected"


def test_delete_below_the_merge_leaves_it_unaffected():
    m = (1, 2, 1, 2)
    f = predict_merge_fate(m, kind="delete", dimension="ROWS", at_index_0based=8, count=2)
    assert f.after == (1, 2, 1, 2)
    assert f.fate == "unaffected"


def test_delete_above_the_merge_shifts_it_whole():
    # deletion entirely above the merge (no intersection) → the merge shifts up, same size.
    m = (5, 6, 0, 2)
    f = predict_merge_fate(m, kind="delete", dimension="ROWS", at_index_0based=0, count=2)
    assert f.after == (3, 4, 0, 2)
    assert f.fate == "shift"


def test_edit_on_the_other_axis_does_not_touch_this_axis():
    # a ROW insert never changes a merge's columns (and vice-versa).
    m = (1, 2, 1, 2)
    f = predict_merge_fate(m, kind="insert", dimension="ROWS", at_index_0based=0, count=3)
    assert f.after == (4, 5, 1, 2)  # rows shifted, cols identical


def test_predict_merge_fate_accepts_a_v3_dict():
    d = {"start_row_index": 1, "end_row_index": 2, "start_column_index": 1, "end_column_index": 2}
    f = predict_merge_fate(d, kind="insert", dimension="ROWS", at_index_0based=0, count=1)
    assert f.before == (1, 2, 1, 2)
    assert f.after == (2, 3, 1, 2)


def test_merge_fate_is_json_serializable_for_a_preview():
    f = predict_merge_fate((1, 2, 1, 2), kind="insert", dimension="ROWS", at_index_0based=0, count=1)
    d = f.to_dict()
    assert json.loads(json.dumps(d)) == d
    assert d["fate"] == "shift"
    assert d["before"] == [1, 2, 1, 2]
    assert d["after"] == [2, 3, 1, 2]


# --------------------------------------------------------------------------- #
# The merge/tab client seam — a duck-typed stand-in modelling a live sheet's    #
# merge set (per sheet_id) + tab set + a monotonic revision (+1 per write). The #
# merge/unmerge writes mutate the sheet's merges array so the mandatory merge   #
# leg (geometry re-read) sees the delta; the tab writes mint/echo sheetIds like #
# the LD-107 sheets_batch_update captures.                                      #
# --------------------------------------------------------------------------- #

def _region_dict(a1):
    from larkdocio.sheets.write_range import parse_write_range
    wr = parse_write_range(a1)
    return {"start_row_index": wr.start.row - 1, "end_row_index": wr.end.row - 1,
            "start_column_index": wr.start.col - 1, "end_column_index": wr.end.col - 1}


class FakeMergeTabGateway:
    def __init__(self, *, revision=0, row_count=10, column_count=6,
                 sheet_merges=None, values=None, tabs=None):
        self.revision = revision
        self.row_count = row_count
        self.column_count = column_count
        self.sheet_merges = {k: list(v) for k, v in (sheet_merges or {}).items()}
        self.values = dict(values or {})
        self.tabs = list(tabs or [])
        self.calls = []
        self.geometry_reads = []
        self.tab_queries = 0
        self.puts = []
        self.external_bumps = {}
        self._rev_reads = 0
        self._new_sid_seq = 0

    # -- reads (un-throttled write-side reads) --
    def read_revision(self, spreadsheet_token):
        self._rev_reads += 1
        self.revision += self.external_bumps.pop(self._rev_reads, 0)
        return self.revision

    def read_values(self, spreadsheet_token, a1_range, value_render_option="UnformattedValue"):
        return self.values.get(a1_range, [])

    def read_sheet_geometry(self, spreadsheet_token, sheet_id):
        self.geometry_reads.append(sheet_id)
        if sheet_id not in self.sheet_merges and sheet_id not in {t.get("sheet_id") for t in self.tabs}:
            return None
        return {"row_count": self.row_count, "column_count": self.column_count,
                "merges": list(self.sheet_merges.get(sheet_id, []))}

    def query_tabs(self, spreadsheet_token):
        self.tab_queries += 1
        return [dict(t) for t in self.tabs]

    # -- writes (each bumps revision +1, spike Q4) --
    def merge_cells(self, spreadsheet_token, a1_range, merge_type="MERGE_ALL"):
        self.calls.append(("merge", a1_range, merge_type))
        from larkdocio.sheets.write_range import parse_write_range
        sid = parse_write_range(a1_range).sheet_id
        self.sheet_merges.setdefault(sid, []).append(_region_dict(a1_range))
        self.revision += 1
        return {"spreadsheetToken": spreadsheet_token}

    def unmerge_cells(self, spreadsheet_token, a1_range):
        self.calls.append(("unmerge", a1_range))
        from larkdocio.sheets.write_range import parse_write_range
        sid = parse_write_range(a1_range).sheet_id
        target = _region_dict(a1_range)
        self.sheet_merges[sid] = [m for m in self.sheet_merges.get(sid, []) if m != target]
        self.revision += 1
        return {"spreadsheetToken": spreadsheet_token}

    def batch_update_sheets(self, spreadsheet_token, requests):
        self.calls.append(("batch-update-sheets", requests))
        replies = []
        for req in requests:
            if "addSheet" in req:
                self._new_sid_seq += 1
                sid = f"new{self._new_sid_seq:02d}"
                props = dict(req["addSheet"]["properties"])
                props["sheetId"] = sid
                self.sheet_merges.setdefault(sid, [])
                self.tabs.append({"sheet_id": sid, "title": props.get("title"),
                                  "index": props.get("index"),
                                  "row_count": self.row_count, "column_count": self.column_count,
                                  "merges": []})
                replies.append({"addSheet": {"properties": props}})
            elif "copySheet" in req:
                self._new_sid_seq += 1
                sid = f"copy{self._new_sid_seq:02d}"
                src = req["copySheet"]["source"]["sheetId"]
                title = req["copySheet"]["destination"]["title"]
                # a copy DUPLICATES the source's content incl. its merges
                self.sheet_merges[sid] = list(self.sheet_merges.get(src, []))
                self.tabs.append({"sheet_id": sid, "title": title, "index": None,
                                  "row_count": self.row_count, "column_count": self.column_count,
                                  "merges": list(self.sheet_merges[sid])})
                replies.append({"copySheet": {"properties": {"index": 1, "sheetId": sid, "title": title}}})
            elif "deleteSheet" in req:
                sid = req["deleteSheet"]["sheetId"]
                self.tabs = [t for t in self.tabs if t.get("sheet_id") != sid]
                self.sheet_merges.pop(sid, None)
                replies.append({"deleteSheet": {"result": True, "sheetId": sid}})
        self.revision += 1
        return {"replies": replies}

    def put_values(self, spreadsheet_token, a1_range, values):
        self.puts.append((a1_range, values))
        self.values[a1_range] = values
        self.revision += 1
        return {"revision": self.revision}


# =========================================================================== #
# AC1 — merge/unmerge encode + write through the gated engine; the resulting    #
# `merges` array is verified by the LD-116 MERGE LEG (assert_merge_change).      #
# =========================================================================== #

from sheets_fidelity_diff import assert_merge_change  # the LD-116 merge leg


def test_merge_write_is_verified_by_the_merge_leg():
    gw = FakeMergeTabGateway(revision=0, sheet_merges={SID: []},
                             values={f"{SID}!A5:C5": [["keep", "x", "y"]]})
    plan = dry_run([MergeCells(f"{SID}!A5:C5")], gw, TOKEN)
    log = apply(plan, gw)
    (entry,) = log.entries
    assert entry.is_applied
    assert gw.calls == [("merge", f"{SID}!A5:C5", "MERGE_ALL")]
    s = entry.structural
    # the merge leg proves the geometry: EXACTLY the A5:C5 region was added, none removed.
    assert_merge_change(s["merges_before"], s["merges_after"],
                        added=[(4, 4, 0, 2)], removed=[])
    assert entry.revision == 1  # every write bumps +1 (metainfo fallback — merge reply omits it)


def test_merge_op_kind_and_gate_legs():
    req = MergeCells(f"{SID}!A5:C5")
    assert req.op_kinds == (WriteOpKind.MERGE,)
    assert requires_merge_leg(req.op_kinds) is True     # the merge leg is required
    assert requires_style_leg(req.op_kinds) is True     # (a merge also auto-ons the style leg, LD-116)


def test_merge_dry_run_previews_the_anchor_value_loss_explicitly():
    # ANCHOR-VALUE semantics (D4): only A5 (anchor) survives; B5/C5 values are LOST — and
    # the dry-run must enumerate that loss (delete-log parity), writing NOTHING.
    gw = FakeMergeTabGateway(revision=3, sheet_merges={SID: []},
                             values={f"{SID}!A5:C5": [["keep", "lose-b", "lose-c"]]})
    plan = dry_run([MergeCells(f"{SID}!A5:C5")], gw, TOKEN)
    (entry,) = plan.entries
    assert entry.is_resolved
    preview = entry.after
    assert preview["anchor"] == {"ref": "A5", "value": "keep"}
    assert preview["covered_count"] == 2
    assert {c["ref"] for c in preview["covered"]} == {"B5", "C5"}
    # both covered cells held data → both enumerated as LOST
    assert preview["lost_count"] == 2
    assert {c["ref"]: c["value"] for c in preview["lost_values"]} == {"B5": "lose-b", "C5": "lose-c"}
    assert gw.calls == [] and gw.puts == []  # ZERO writes at plan time


def test_merge_loss_preview_only_flags_non_null_covered_cells_as_lost():
    # a covered cell that is already empty is enumerated (covered) but NOT counted as a loss.
    gw = FakeMergeTabGateway(revision=0, sheet_merges={SID: []},
                             values={f"{SID}!A5:C5": [["keep", None, "lose-c"]]})
    preview = dry_run([MergeCells(f"{SID}!A5:C5")], gw, TOKEN).entries[0].after
    assert preview["covered_count"] == 2
    assert preview["lost_count"] == 1
    assert preview["lost_values"][0]["ref"] == "C5"


def test_unmerge_write_is_verified_by_the_merge_leg_removing_the_region():
    region = _region_dict(f"{SID}!A5:C5")
    gw = FakeMergeTabGateway(revision=0, sheet_merges={SID: [region]})
    plan = dry_run([UnmergeCells(f"{SID}!A5:C5")], gw, TOKEN)
    entry = apply(plan, gw).entries[0]
    assert entry.is_applied
    assert gw.calls == [("unmerge", f"{SID}!A5:C5")]
    s = entry.structural
    # the merge leg proves the region was removed, none added.
    assert_merge_change(s["merges_before"], s["merges_after"], added=[], removed=[(4, 4, 0, 2)])


def test_unmerge_preview_characterizes_the_values_state_no_restore():
    gw = FakeMergeTabGateway(revision=0, sheet_merges={SID: [_region_dict(f"{SID}!A5:C5")]})
    preview = dry_run([UnmergeCells(f"{SID}!A5:C5")], gw, TOKEN).entries[0].after
    assert preview["kind"] == "unmerge"
    assert preview["merge_region"] == [4, 4, 0, 2]
    assert "no value restored" in preview["note"]
    assert gw.calls == []  # deterministic preview — no read/write at plan time


# =========================================================================== #
# AC5 — merge/tab writes are gated + STALE_SHEET compare-and-swap guarded.      #
# =========================================================================== #

def test_merge_write_is_stale_sheet_guarded_no_write():
    gw = FakeMergeTabGateway(revision=2, sheet_merges={SID: []},
                             values={f"{SID}!A5:C5": [["k", "x", "y"]]})
    plan = dry_run([MergeCells(f"{SID}!A5:C5")], gw, TOKEN)
    gw.external_bumps = {2: 1}  # external writer bumps revision before apply's re-read
    (entry,) = apply(plan, gw).entries
    assert not entry.is_applied
    assert entry.refusal.reason == Refusal.STALE_SHEET
    assert gw.calls == []            # STALE_SHEET → no merge write
    assert gw.geometry_reads == []   # not even the merge-leg re-read fires on a skipped write


def test_apply_rejects_a_bare_merge_request_not_a_plan():
    gw = FakeMergeTabGateway()
    with pytest.raises(TypeError):
        apply([MergeCells(f"{SID}!A5:C5")], gw)  # never a blind/unattended write


# =========================================================================== #
# AC3 — tab add/copy/delete; new sheetId captured; delete carries removed       #
# identity (D5); copy duplicates the source's merges.                           #
# =========================================================================== #

def test_add_tab_captures_the_new_sheet_id():
    gw = FakeMergeTabGateway(revision=0)
    entry = apply(dry_run([AddTab("QA Notes", index=2)], gw, TOKEN), gw).entries[0]
    assert entry.is_applied
    assert entry.structural["op"] == "add-tab"
    assert entry.structural["new_sheet_id"] == "new01"
    # the wire element the request owns (a caller never hand-assembles it)
    assert gw.calls[0][0] == "batch-update-sheets"
    assert gw.calls[0][1] == [{"addSheet": {"properties": {"title": "QA Notes", "index": 2}}}]


def test_add_tab_op_kind_triggers_neither_style_nor_merge_leg():
    req = AddTab("X")
    assert req.op_kinds == (WriteOpKind.TAB,)
    assert requires_style_leg(req.op_kinds) is False
    assert requires_merge_leg(req.op_kinds) is False


def test_copy_tab_captures_new_sheet_id_and_duplicates_merges():
    src_region = _region_dict(f"{SID}!A5:C5")
    gw = FakeMergeTabGateway(revision=0, sheet_merges={SID: [src_region]},
                             tabs=[{"sheet_id": SID, "title": "Src", "index": 0,
                                    "row_count": 10, "column_count": 6, "merges": [src_region]}])
    entry = apply(dry_run([CopyTab(SID, "Src (copy)")], gw, TOKEN), gw).entries[0]
    assert entry.is_applied
    s = entry.structural
    assert s["op"] == "copy-tab"
    assert s["new_sheet_id"] == "copy01"
    # content fidelity: the copy carries the source's merges (re-read on the new tab)
    assert s["copied_merges"] == [src_region]
    assert gw.calls[0][1] == [{"copySheet": {"source": {"sheetId": SID},
                                             "destination": {"title": "Src (copy)"}}}]


def test_delete_tab_carries_the_removed_identity_in_the_apply_log():
    victim = {"sheet_id": "dead99", "title": "Scratch", "index": 3,
              "row_count": 20, "column_count": 8,
              "merges": [{"start_row_index": 0, "end_row_index": 0,
                          "start_column_index": 0, "end_column_index": 1}]}
    gw = FakeMergeTabGateway(revision=0, tabs=[victim])
    entry = apply(dry_run([DeleteTab("dead99")], gw, TOKEN), gw).entries[0]
    assert entry.is_applied
    s = entry.structural
    assert s["op"] == "delete-tab"
    # D5 destructive-safe: the FULL removed identity is preserved (title/index/geometry/merges)
    assert s["removed_identity"] == victim
    assert s["result"] is True
    assert gw.calls[-1][1] == [{"deleteSheet": {"sheetId": "dead99"}}]


def test_delete_tab_snapshots_identity_at_plan_time_before_the_delete():
    victim = {"sheet_id": "dead99", "title": "Scratch", "index": 3,
              "row_count": 20, "column_count": 8, "merges": []}
    gw = FakeMergeTabGateway(revision=0, tabs=[victim])
    plan = dry_run([DeleteTab("dead99")], gw, TOKEN)
    # the identity is previewed at plan time (destructive-safe), before any write
    assert plan.entries[0].after["removed_identity"] == victim
    assert gw.tab_queries == 1
    assert gw.calls == []  # ZERO writes at plan time


def test_tab_delete_is_stale_sheet_guarded_no_write():
    gw = FakeMergeTabGateway(revision=5, tabs=[{"sheet_id": "dead99", "title": "S", "index": 0,
                                                "row_count": 1, "column_count": 1, "merges": []}])
    plan = dry_run([DeleteTab("dead99")], gw, TOKEN)
    gw.external_bumps = {2: 1}
    (entry,) = apply(plan, gw).entries
    assert not entry.is_applied
    assert entry.refusal.reason == Refusal.STALE_SHEET
    assert not any(c[0] == "batch-update-sheets" for c in gw.calls)  # no tab write


# =========================================================================== #
# AC4 — a value write targeting a merged/COVERED cell REFUSES (typed).          #
# =========================================================================== #

_M = {"start_row_index": 4, "end_row_index": 4, "start_column_index": 0, "end_column_index": 2}  # A5:C5


def test_value_write_into_a_covered_cell_refuses():
    gw = FakeMergeTabGateway(revision=0, values={f"{SID}!B5:B5": [["x"]]})
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!B5", [["x"]])], gw, TOKEN, merges=[_M])
    (entry,) = plan.entries
    assert not entry.is_resolved
    assert entry.refusal.reason == Refusal.MERGED_CELL_TARGET
    # and apply writes nothing for a refused entry
    log = apply(plan, gw)
    assert not log.entries[0].is_applied
    assert gw.puts == []


def test_value_write_to_the_merge_anchor_is_allowed():
    # the ANCHOR (A5) is not a covered cell — a write to it sets the merged cell's value.
    gw = FakeMergeTabGateway(revision=0, values={f"{SID}!A5:A5": [["old"]]})
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A5", [["new"]])], gw, TOKEN, merges=[_M])
    assert plan.entries[0].is_resolved


def test_value_write_range_overlapping_covered_cells_refuses():
    gw = FakeMergeTabGateway(revision=0, values={f"{SID}!A5:C5": [["a", "b", "c"]]})
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A5:C5", [["a", "b", "c"]])], gw, TOKEN, merges=[_M])
    assert plan.entries[0].refusal.reason == Refusal.MERGED_CELL_TARGET


def test_value_write_outside_any_merge_is_unaffected_by_merge_awareness():
    gw = FakeMergeTabGateway(revision=0, values={f"{SID}!A1:A1": [["a"]]})
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1", [["a"]])], gw, TOKEN, merges=[_M])
    assert plan.entries[0].is_resolved


def test_merges_default_none_keeps_the_value_path_merge_unaware_zero_drift():
    # WITHOUT merges= (the default), the value path is byte-identical to LD-111 — no
    # merged-cell refusal, no geometry read. This is the ZERO-DRIFT guarantee.
    gw = FakeMergeTabGateway(revision=0, values={f"{SID}!B5:B5": [["old"]]})
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!B5", [["new"]])], gw, TOKEN)  # no merges=
    assert plan.entries[0].is_resolved
    assert gw.geometry_reads == []  # the value path never read geometry


# =========================================================================== #
# Serialization — merge/tab plan + apply-log entries are JSON round-trippable.  #
# =========================================================================== #

def test_merge_plan_and_apply_log_round_trip_through_json():
    gw = FakeMergeTabGateway(revision=0, sheet_merges={SID: []},
                             values={f"{SID}!A5:C5": [["k", "x", "y"]]})
    plan = dry_run([MergeCells(f"{SID}!A5:C5")], gw, TOKEN)
    pd = plan.entries[0].to_dict()
    assert json.loads(json.dumps(pd)) == pd
    log = apply(plan, gw)
    ld = log.to_dict()
    assert json.loads(json.dumps(ld)) == ld
    assert ld["entries"][0]["write_kind"] == "merge"


def test_tab_apply_log_round_trips_and_names_the_op():
    gw = FakeMergeTabGateway(revision=0)
    log = apply(dry_run([AddTab("T")], gw, TOKEN), gw)
    d = log.to_dict()
    assert json.loads(json.dumps(d)) == d
    assert d["entries"][0]["write_kind"] == "tab"


def test_merge_and_value_and_tab_writes_batch_in_one_plan_in_order():
    gw = FakeMergeTabGateway(revision=0, sheet_merges={SID: []},
                             values={f"{SID}!A1:A1": [["a0"]], f"{SID}!A5:C5": [["k", "x", "y"]]})
    plan = dry_run([
        ValueWriteRequest.for_a1(f"{SID}!A1:A1", [["a1"]]),
        MergeCells(f"{SID}!A5:C5"),
        AddTab("Extra"),
    ], gw, TOKEN)
    log = apply(plan, gw)
    assert [e.outcome for e in log.entries] == ["applied", "applied", "applied"]
    assert [e.write_kind for e in log.entries] == ["value", "merge", "tab"]
