"""Offline unit tests for the DESTRUCTIVE-SAFE gated apply consolidation
(LD-123).

This story does not add write ops — S1..S4 (LD-119..122) build them. It makes the
whole gated write surface **destructive-safe** as one verified unit, mirroring the
docx W3 delete-log discipline (the block create/delete spec § Decision c — a delete's apply-log carries the
FULL removed payload, enough to reconstruct):

* **AC1 — ``STALE_SHEET`` everywhere (D1).** Every op-class (value / rich / dropdown /
  insert / delete-rows / delete-cols / append-dim / append-values / merge / unmerge /
  add-tab / copy-tab / delete-tab) re-reads ``revision`` right before its write and
  refuses ``STALE_SHEET`` (no write) on advance. One consolidated per-op-class matrix.
* **AC2 — deletes carry the FULL removed payload (D5, DESTRUCTIVE-SAFE).** A row/col
  delete's apply-log entry carries the **removed cells' values + pre-write geometry**
  (+ the intersecting merges) — enough to **reconstruct**; the reconstruct test rebuilds
  the deleted rows byte-exact from the log alone, and an **incomplete** payload FAILS the
  reconstruct check (the red half). Tab-delete (removed identity), rich overwrite
  (``before``), and unmerge (``merges_removed``) already carry reconstructable payloads —
  locked here too.
* **AC3 — never unattended (D2).** Every destructive op's dry-run previews **what is
  removed**; ``apply`` accepts ONLY a dry-run ``Plan`` (the ``_PLAN_TOKEN`` hard gate), so
  no un-previewed structural apply is reachable — asserted per destructive op-class. A
  partial batch where one delete goes stale still logs the surviving delete's full payload.
* **AC4 — findings-agnostic (carried).** The new destructive-safe symbols add no consumer
  findings / layer / severity vocabulary; the AST guard covers them and stays clean.

The **test-rigor amplifier** ("go a bit nuts"): a delete whose payload round-trips
byte-exact, a staleness race per op-class, a partial-batch where only the stale op skips
(the deletes still log full payloads), a destructive delete that REFUSES when it cannot
snapshot what it would destroy (a vanished tab), and the preview-completeness matrix.
"""
import ast
import json
from pathlib import Path

import pytest

from log_reading_apply import reading_the_log
from larkdocio.sheets.write_apply import (
    AddTab,
    AppendDimension,
    AppendRowsWithValues,
    CopyTab,
    DeleteCols,
    DeleteRows,
    DeleteTab,
    DropdownRuleWriteRequest,
    InsertRowsAt,
    MergeCells,
    Refusal,
    RichCellWriteRequest,
    UnmergeCells,
    ValueWriteRequest,
    apply,
    dry_run,
)
apply = reading_the_log(apply)

TOKEN = "shtxxxDESTRUCT"
SID = "555c22"


# --------------------------------------------------------------------------- #
# A unified duck-typed gateway supporting EVERY write seam + the write-side    #
# reads, so the destructive-safe consolidation can drive one op-class at a     #
# time through the same engine. A monotonic `revision` (+1 per write, spike    #
# Q4); external writers scheduled by read_revision call number. Every write    #
# is recorded in `self.writes` so a STALE skip can assert "no write happened". #
# --------------------------------------------------------------------------- #

class FakeAllOpsGateway:
    def __init__(self, *, revision=0, row_count=10, column_count=3,
                 sheet_merges=None, values=None, tabs=None):
        self.revision = revision
        self.row_count = row_count
        self.column_count = column_count
        self.sheet_merges = {k: list(v) for k, v in (sheet_merges or {}).items()}
        self.values = dict(values or {})
        self.tabs = list(tabs or [])
        self.writes = []              # every write op, tagged — for the STALE "no write" assert
        self.geometry_reads = []
        self.value_reads = []
        self.tab_queries = 0
        self.external_bumps = {}
        self._rev_reads = 0
        self._new_sid_seq = 0
        self.geometry_none_for = set()  # sheet_ids whose geometry read returns None

    # -- reads (un-throttled write-side reads) --
    def read_revision(self, spreadsheet_token):
        self._rev_reads += 1
        self.revision += self.external_bumps.pop(self._rev_reads, 0)
        return self.revision

    def read_values(self, spreadsheet_token, a1_range, value_render_option="UnformattedValue"):
        # LD-149: the FORMULA family reads by render mode (Formula for the expression
        # precondition, UnformattedValue for the computed verification). This fake is a
        # destructive-safety / disposition probe, not an evaluator, so every mode answers the
        # stored value — which is exactly the "did not evaluate" signature, and that is fine
        # here: evaluation itself is characterized in tests/test_sheets_formula_write.py and
        # proven live in tests/test_live_sheets_formula_write_gate.py.
        self.value_reads.append(a1_range)
        v = self.values.get(a1_range)
        if isinstance(v, Exception):
            raise v
        return [] if v is None else v

    def read_sheet_geometry(self, spreadsheet_token, sheet_id):
        self.geometry_reads.append(sheet_id)
        if sheet_id in self.geometry_none_for:
            return None
        return {"row_count": self.row_count, "column_count": self.column_count,
                "merges": list(self.sheet_merges.get(sheet_id, []))}

    def query_tabs(self, spreadsheet_token):
        self.tab_queries += 1
        return [dict(t) for t in self.tabs]

    # -- writes (each bumps revision +1) --
    def put_values(self, spreadsheet_token, a1_range, values):
        self.writes.append(("put", a1_range))
        self.values[a1_range] = values
        self.revision += 1
        return {"revision": self.revision}

    def set_data_validation(self, spreadsheet_token, a1_range, rule):
        self.writes.append(("dv", a1_range))
        self.revision += 1
        return {}

    def insert_dimension_range(self, spreadsheet_token, sheet_id, major_dimension, start_index, end_index, inherit_style=None):
        self.writes.append(("insert", sheet_id))
        n = end_index - start_index
        if major_dimension == "ROWS":
            self.row_count += n
        else:
            self.column_count += n
        self.revision += 1
        return {}

    def delete_dimension_range(self, spreadsheet_token, sheet_id, major_dimension, start_index, end_index):
        self.writes.append(("delete", sheet_id))
        n = end_index - start_index + 1
        if major_dimension == "ROWS":
            self.row_count -= n
        else:
            self.column_count -= n
        self.revision += 1
        return {"delCount": n, "majorDimension": major_dimension}

    def append_dimension(self, spreadsheet_token, sheet_id, major_dimension, length):
        self.writes.append(("append-dim", sheet_id))
        if major_dimension == "ROWS":
            self.row_count += length
        else:
            self.column_count += length
        self.revision += 1
        return {"addCount": length, "majorDimension": major_dimension}

    def append_values(self, spreadsheet_token, a1_range, values, insert_data_option=None):
        self.writes.append(("append-values", a1_range))
        if insert_data_option == "INSERT_ROWS":
            self.row_count += len(values)
        self.revision += 1
        return {"revision": self.revision, "updates": {"updatedRows": len(values)}}

    def _region_dict(self, a1):
        from larkdocio.sheets.write_range import parse_write_range
        wr = parse_write_range(a1)
        return {"start_row_index": wr.start.row - 1, "end_row_index": wr.end.row - 1,
                "start_column_index": wr.start.col - 1, "end_column_index": wr.end.col - 1}

    def merge_cells(self, spreadsheet_token, a1_range, merge_type="MERGE_ALL"):
        from larkdocio.sheets.write_range import parse_write_range
        self.writes.append(("merge", a1_range))
        sid = parse_write_range(a1_range).sheet_id
        self.sheet_merges.setdefault(sid, []).append(self._region_dict(a1_range))
        self.revision += 1
        return {"spreadsheetToken": spreadsheet_token}

    def unmerge_cells(self, spreadsheet_token, a1_range):
        from larkdocio.sheets.write_range import parse_write_range
        self.writes.append(("unmerge", a1_range))
        sid = parse_write_range(a1_range).sheet_id
        target = self._region_dict(a1_range)
        self.sheet_merges[sid] = [m for m in self.sheet_merges.get(sid, []) if m != target]
        self.revision += 1
        return {"spreadsheetToken": spreadsheet_token}

    def batch_update_sheets(self, spreadsheet_token, requests):
        self.writes.append(("batch-update-sheets", requests))
        replies = []
        for req in requests:
            if "addSheet" in req:
                self._new_sid_seq += 1
                sid = f"new{self._new_sid_seq:02d}"
                props = dict(req["addSheet"]["properties"])
                props["sheetId"] = sid
                replies.append({"addSheet": {"properties": props}})
            elif "copySheet" in req:
                self._new_sid_seq += 1
                sid = f"copy{self._new_sid_seq:02d}"
                title = req["copySheet"]["destination"]["title"]
                replies.append({"copySheet": {"properties": {"index": 1, "sheetId": sid, "title": title}}})
            elif "deleteSheet" in req:
                sid = req["deleteSheet"]["sheetId"]
                self.tabs = [t for t in self.tabs if t.get("sheet_id") != sid]
                replies.append({"deleteSheet": {"result": True, "sheetId": sid}})
        self.revision += 1
        return {"replies": replies}


def _victim_tab(sheet_id="dead99"):
    return {"sheet_id": sheet_id, "title": "Scratch", "index": 3,
            "row_count": 20, "column_count": 8, "merges": []}


# =========================================================================== #
# AC1 — STALE_SHEET EVERYWHERE: one stale-skip assertion per op-class.          #
#                                                                              #
# dry_run reads revision ONCE (the plan-time cache, call #1); apply re-reads it #
# immediately before the write (call #2). An external writer bumping revision   #
# on call #2 must make EVERY op-class refuse STALE_SHEET with NO write.         #
# =========================================================================== #

_STALE_OP_CASES = {
    "value": lambda: ValueWriteRequest.for_a1(f"{SID}!A1:A1", [["x"]]),
    "rich": lambda: RichCellWriteRequest.hyperlink(f"{SID}!A2:A2", "https://x.example", text="X"),
    "dropdown": lambda: DropdownRuleWriteRequest.list_rule(f"{SID}!A3:A3", ["Red", "Green"]),
    "insert": lambda: InsertRowsAt(SID, before_row=2, count=1),
    "delete-rows": lambda: DeleteRows(SID, first=2, last=3),
    "delete-cols": lambda: DeleteCols(SID, first=2, last=2),
    "append-dim": lambda: AppendDimension(SID, "ROWS", 2),
    "append-values": lambda: AppendRowsWithValues(f"{SID}!A1:B1", [["x", "y"]]),
    "merge": lambda: MergeCells(f"{SID}!A5:C5"),
    "unmerge": lambda: UnmergeCells(f"{SID}!A5:C5"),
    "add-tab": lambda: AddTab("New"),
    "copy-tab": lambda: CopyTab(SID, "Src copy"),
    "delete-tab": lambda: DeleteTab("dead99"),
}


@pytest.mark.parametrize("op_name", sorted(_STALE_OP_CASES))
def test_stale_sheet_refuses_every_op_class_no_write(op_name):
    gw = FakeAllOpsGateway(revision=2, sheet_merges={SID: []}, tabs=[_victim_tab()])
    plan = dry_run([_STALE_OP_CASES[op_name]()], gw, TOKEN)
    # an external writer bumps revision before apply's pre-write re-read (call #2)
    gw.external_bumps = {2: 1}
    (entry,) = apply(plan, gw).entries
    assert not entry.is_applied, f"{op_name}: a stale sheet must not apply"
    assert entry.refusal.reason == Refusal.STALE_SHEET, f"{op_name}: expected STALE_SHEET"
    assert gw.writes == [], f"{op_name}: STALE_SHEET must issue NO write, got {gw.writes}"


# =========================================================================== #
# AC2 — deletes carry the FULL removed payload; reconstruct from the log alone. #
# =========================================================================== #

def _reconstruct_deleted_grid(removed):
    """Rebuild the exact deleted cell grid from a delete's removed payload ALONE.

    This is the destructive-safe contract: the apply-log must carry enough to
    reconstruct what was destroyed. An INCOMPLETE payload (missing the removed
    values, its addressing range, or the pre-write geometry) cannot reconstruct →
    :class:`AssertionError` (the "a delete with an incomplete payload FAILS" half)."""
    assert removed is not None, "no removed payload — nothing to reconstruct from"
    assert removed.get("a1_range"), "removed payload has no a1_range — cannot address the loss"
    assert removed.get("values") is not None, "removed payload has no values — cannot reconstruct"
    assert removed.get("geometry") is not None, "removed payload has no pre-write geometry"
    return removed["values"]


def test_row_delete_apply_log_reconstructs_the_deleted_rows_byte_exact():
    removed_rows = [["b1", "b2", "b3"], ["c1", "c2", "c3"]]  # rows 2..3, all 3 columns
    gw = FakeAllOpsGateway(revision=0, row_count=4, column_count=3,
                           values={f"{SID}!A2:C3": removed_rows})
    log = apply(dry_run([DeleteRows(SID, first=2, last=3)], gw, TOKEN), gw)
    (entry,) = log.entries
    assert entry.is_applied
    removed = entry.structural["removed"]
    # the FULL removed payload: the addressing range + the removed values + pre-write geometry
    assert removed["a1_range"] == f"{SID}!A2:C3"
    assert removed["geometry"]["row_count"] == 4 and removed["geometry"]["column_count"] == 3
    # reconstruct the deleted rows from the log ALONE — byte-exact
    assert _reconstruct_deleted_grid(removed) == removed_rows


def test_col_delete_apply_log_reconstructs_the_deleted_columns_byte_exact():
    removed_cols = [["b1", "c1"], ["b2", "c2"], ["b3", "c3"]]  # cols 2..3, all 3 rows
    gw = FakeAllOpsGateway(revision=0, row_count=3, column_count=3,
                           values={f"{SID}!B1:C3": removed_cols})
    entry = apply(dry_run([DeleteCols(SID, first=2, last=3)], gw, TOKEN), gw).entries[0]
    assert entry.is_applied
    removed = entry.structural["removed"]
    assert removed["a1_range"] == f"{SID}!B1:C3"
    assert _reconstruct_deleted_grid(removed) == removed_cols


def test_incomplete_removed_payload_fails_the_reconstruct_check():
    # The RED half of the destructive-safe guard: an incomplete payload (values dropped /
    # geometry dropped / range dropped) MUST fail the reconstruct contract — proving the
    # reconstruct test is sensitive to completeness (a payload regression would be caught).
    complete = {"a1_range": f"{SID}!A2:C3", "values": [["b1", "b2", "b3"]],
                "geometry": {"row_count": 4, "column_count": 3, "merges": []},
                "removed_merges": []}
    assert _reconstruct_deleted_grid(complete)  # sanity: complete reconstructs

    for missing in ("values", "geometry", "a1_range"):
        broken = dict(complete)
        broken.pop(missing)
        with pytest.raises(AssertionError):
            _reconstruct_deleted_grid(broken)


def test_row_delete_removed_payload_captures_intersecting_merges():
    # a merge inside the deleted span is captured in the removed payload (reconstruction
    # needs the merge geometry, not only the cell values).
    merge_in_span = {"start_row_index": 1, "end_row_index": 2,
                     "start_column_index": 0, "end_column_index": 1}  # rows 2..3
    merge_outside = {"start_row_index": 8, "end_row_index": 8,
                     "start_column_index": 0, "end_column_index": 1}  # far below
    gw = FakeAllOpsGateway(revision=0, row_count=10, column_count=3,
                           sheet_merges={SID: [merge_in_span, merge_outside]})
    entry = apply(dry_run([DeleteRows(SID, first=2, last=3)], gw, TOKEN), gw).entries[0]
    removed = entry.structural["removed"]
    assert merge_in_span in removed["removed_merges"]
    assert merge_outside not in removed["removed_merges"]


def test_delete_that_cannot_snapshot_its_loss_refuses_no_write():
    # DESTRUCTIVE-SAFE: if the pre-write geometry is unreadable (a vanished tab), the
    # engine cannot record what the delete would destroy → it REFUSES rather than perform
    # an un-reconstructable destruction.
    gw = FakeAllOpsGateway(revision=0)
    gw.geometry_none_for = {SID}
    plan = dry_run([DeleteRows(SID, first=2, last=3)], gw, TOKEN)
    (entry,) = plan.entries
    assert not entry.is_resolved
    assert entry.refusal.reason == Refusal.TAB_VANISHED
    log = apply(plan, gw)
    assert not log.entries[0].is_applied
    assert gw.writes == []  # nothing destroyed


def test_rich_overwrite_apply_log_carries_the_removed_before_payload():
    # a rich-cell overwrite is destructive to the prior cell content: the apply-log's
    # `before` carries the removed payload (the value that was overwritten).
    prior = [[{"cellPosition": None, "link": "https://old.example", "text": "old", "type": "url"}]]
    gw = FakeAllOpsGateway(revision=0, values={f"{SID}!A1:A1": prior})
    req = RichCellWriteRequest.hyperlink(f"{SID}!A1:A1", "https://new.example", text="new")
    entry = apply(dry_run([req], gw, TOKEN), gw).entries[0]
    assert entry.is_applied
    assert entry.before == prior  # the overwritten content is preserved for reconstruction


def test_unmerge_apply_log_reconstructs_the_removed_merge():
    region = {"start_row_index": 4, "end_row_index": 4, "start_column_index": 0, "end_column_index": 2}
    gw = FakeAllOpsGateway(revision=0, sheet_merges={SID: [region]})
    entry = apply(dry_run([UnmergeCells(f"{SID}!A5:C5")], gw, TOKEN), gw).entries[0]
    assert entry.is_applied
    # the removed merge is preserved in the apply-log → re-merge the region to reconstruct
    assert region in entry.structural["merges_removed"]


def test_tab_delete_apply_log_reconstructs_the_removed_tab_identity():
    victim = _victim_tab("dead77")
    gw = FakeAllOpsGateway(revision=0, tabs=[victim])
    entry = apply(dry_run([DeleteTab("dead77")], gw, TOKEN), gw).entries[0]
    assert entry.is_applied
    assert entry.structural["removed_identity"] == victim  # full identity → recreate the tab


# =========================================================================== #
# AC3 — never unattended: every destructive op requires the dry-run handshake;  #
# the delete preview enumerates what is removed; a partial batch still logs the #
# surviving delete's full payload.                                             #
# =========================================================================== #

_DESTRUCTIVE_CASES = {
    "delete-rows": lambda: DeleteRows(SID, first=2, last=3),
    "delete-cols": lambda: DeleteCols(SID, first=2, last=2),
    "unmerge": lambda: UnmergeCells(f"{SID}!A5:C5"),
    "delete-tab": lambda: DeleteTab("dead99"),
}


@pytest.mark.parametrize("op_name", sorted(_DESTRUCTIVE_CASES))
def test_no_destructive_op_can_apply_without_the_dry_run_handshake(op_name):
    gw = FakeAllOpsGateway(revision=0, sheet_merges={SID: []}, tabs=[_victim_tab()])
    # a bare request (bypassing dry_run) is NOT a Plan — apply refuses structurally (D2).
    with pytest.raises(TypeError):
        apply([_DESTRUCTIVE_CASES[op_name]()], gw)
    assert gw.writes == []


def test_row_delete_dry_run_previews_what_is_removed_before_any_write():
    removed_rows = [["b1", "b2", "b3"], ["c1", "c2", "c3"]]
    gw = FakeAllOpsGateway(revision=0, row_count=4, column_count=3,
                           values={f"{SID}!A2:C3": removed_rows})
    plan = dry_run([DeleteRows(SID, first=2, last=3)], gw, TOKEN)
    (entry,) = plan.entries
    assert entry.is_resolved
    # the preview enumerates the loss (destructive-safe) BEFORE any write
    assert entry.after["removed"]["values"] == removed_rows
    assert gw.writes == []


def test_partial_batch_stale_delete_skips_but_surviving_delete_logs_full_payload():
    removed_first = [["b1", "b2", "b3"]]  # row 2, 3 columns
    gw = FakeAllOpsGateway(revision=0, row_count=10, column_count=3,
                           values={f"{SID}!A2:C2": removed_first})
    plan = dry_run([
        DeleteRows(SID, first=2, last=2),
        DeleteRows(SID, first=5, last=5),
    ], gw, TOKEN)
    # read_revision order: #1 dry_run cache; #2 delete-1 pre-read; delete-1 writes (rev+1);
    # #3 delete-1 post-write metainfo fallback; #4 delete-2 pre-read (external bump → stale).
    gw.external_bumps = {4: 1}
    log = apply(plan, gw)
    assert [e.outcome for e in log.entries] == ["applied", "stale"]
    # the surviving delete STILL logged a full, reconstructable removed payload
    survivor = log.entries[0].structural["removed"]
    assert _reconstruct_deleted_grid(survivor) == removed_first
    assert gw.writes == [("delete", SID)]  # only the first delete fired


def test_delete_removed_payload_round_trips_through_json():
    gw = FakeAllOpsGateway(revision=0, row_count=4, column_count=3,
                           values={f"{SID}!A2:C3": [["b1", "b2", "b3"], ["c1", "c2", "c3"]]})
    log = apply(dry_run([DeleteRows(SID, first=2, last=3)], gw, TOKEN), gw)
    d = log.to_dict()
    assert json.loads(json.dumps(d)) == d
    assert d["entries"][0]["structural"]["removed"]["values"] == [["b1", "b2", "b3"], ["c1", "c2", "c3"]]


# =========================================================================== #
# AC4 — findings-agnostic: the AST guard covers the new destructive-safe        #
# symbols and stays clean (no consumer findings/layer/severity vocabulary).     #
# =========================================================================== #

# LD-125 split the 2,057-line ``write_apply.py`` god module into a facade over four concern
# modules; the findings-agnostic AST guard now scans the WHOLE sheets write surface so the
# guarantee follows the code (``_snapshot_removed_dimension`` now lives in ``ops.py``).
# LD-224 did the same to ``requests.py`` — now a package — so its members are DERIVED from
# the tree rather than listed: a family module added tomorrow is scanned on its own.
# LD-532 did the same to ``ops.py`` — now a package too — for the same reason, so its
# members are DERIVED from the tree as well.
_SHEETS_DIR = Path(__file__).resolve().parents[1] / "src" / "larkdocio" / "sheets"
_SHEETS_WRITE_MODULES = tuple(
    [_SHEETS_DIR / name
     for name in ("write_apply.py", "plan.py", "merge_geometry.py")]
    + sorted(p for p in (_SHEETS_DIR / "requests").rglob("*.py")
             if "__pycache__" not in p.parts)
    + sorted(p for p in (_SHEETS_DIR / "ops").rglob("*.py")
             if "__pycache__" not in p.parts)
)


def _identifiers():
    names = set()
    for path in _SHEETS_WRITE_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.arg):
                names.add(node.arg)
            elif isinstance(node, ast.keyword) and node.arg:
                names.add(node.arg)
    return names


def test_new_destructive_safe_symbols_exist_and_are_findings_agnostic():
    idents = _identifiers()
    # the guard actually COVERS the new destructive-safe symbols this story added
    assert "_snapshot_removed_dimension" in idents, (
        "the AST findings guard must see the new destructive-safe snapshot symbol"
    )
    # ...and the whole identifier set (new symbols included) stays findings-agnostic (D4)
    lowered = {n.lower() for n in idents}
    for word in ("finding", "layer", "severity", "accepted", "rejected"):
        offenders = {n for n in lowered if word in n}
        assert not offenders, f"findings-schema vocabulary leaked into identifiers: {offenders}"
