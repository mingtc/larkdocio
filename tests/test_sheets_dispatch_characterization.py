"""Characterization safety net for the Sheets write-apply per-op dispatch (LD-125).

LD-125 replays the docx LD-097 op-descriptor registry on the sheets side: the two
parallel string-ladders inside ``write_apply.py`` — ``_preview_one`` (branches on the
**request-side** ``write_kind`` / ``is_structural``) and ``_apply_one`` (branches on the
**entry-side** ``entry.structural["op"]`` / ``entry.write_kind``) — collapse behind ONE
``SheetsOpDescriptor`` registry. That is a strictly **behavior-preserving** refactor: a
mis-dispatch (routing one op through another op's write seam) would corrupt a spreadsheet
silently, so BOTH keyings must be preserved faithfully.

This module is the **safety net that lands BEFORE the moves** (safety-net-check). It pins,
for **every** request family (value / rich / dropdown-rule / structural insert·delete·
append-dim·append-values / merge·unmerge / tab add·copy·delete), the full
``dry_run → apply`` round-trip characterizing BOTH keyings:

* the **request-side** keying — ``dry_run`` builds a :class:`PlanEntry` whose
  ``write_kind`` / ``structural["op"]`` / ``target`` fingerprint proves the request routed
  to the correct **preview** leg;
* the **entry-side** keying — ``apply`` drives exactly the client write seam that op
  requires (``put_values`` vs ``set_data_validation`` vs ``insert_dimension_range`` vs
  ``merge_cells`` vs ``batch_update_sheets`` …), proving the entry routed to the correct
  **apply** leg.

These characterize **current** behavior (they pass on the pre-refactor code). If any one
reddens after the refactor, dispatch drifted — exactly the failure this net exists to
catch. They are intentionally op-distinct so mis-routing op A through op B's seam breaks
an assertion. (The one-registration-point proof — the NEW registry seam — lives at the
bottom and is added with the registry, not with this baseline net.)
"""
import importlib

from larkdocio.sheets.write_apply import (
    AddTab,
    AppendDimension,
    AppendRowsWithValues,
    ApplyLogEntry,
    CopyTab,
    DeleteRows,
    DeleteTab,
    DropdownRuleWriteRequest,
    InsertRowsAt,
    MergeCells,
    PlanEntry,
    RichCellWriteRequest,
    UnmergeCells,
    ValueWriteRequest,
    apply,
    dry_run,
)

TOKEN = "shtxxxDISPATCH"
SID = "s1"


# --------------------------------------------------------------------------- #
# A single duck-typed gateway exposing EVERY client write seam, each recording  #
# its own name into an ordered call log — the entry-side dispatch fingerprint.  #
# Every write bumps ``revision`` +1 (spike Q4); reads never bump. So a batch     #
# never trips STALE_SHEET: the anchor resyncs to the post-write revision each    #
# entry, and the next entry's compare-and-swap re-reads the same value.         #
# --------------------------------------------------------------------------- #

class DispatchGateway:
    def __init__(self, *, revision=0, row_count=10, column_count=6, merges=None,
                 values=None, tabs=None):
        self.revision = revision
        self.row_count = row_count
        self.column_count = column_count
        self.merges = list(merges or [])
        self.values = dict(values or {})
        self.tabs = list(tabs or [])
        self.calls = []  # ordered [(seam_name, *args)] — the dispatch fingerprint

    # -- reads (never bump) --
    def read_revision(self, spreadsheet_token):
        return self.revision

    def read_values(self, spreadsheet_token, a1_range, value_render_option="UnformattedValue"):
        return self.values.get(a1_range, [])

    def read_sheet_geometry(self, spreadsheet_token, sheet_id):
        return {"row_count": self.row_count, "column_count": self.column_count,
                "merges": list(self.merges)}

    def query_tabs(self, spreadsheet_token):
        return list(self.tabs)

    # -- writes (each +1 revision) --
    def put_values(self, spreadsheet_token, a1_range, values):
        self.calls.append(("put_values", a1_range))
        self.revision += 1
        return {"revision": self.revision}

    def set_data_validation(self, spreadsheet_token, a1_range, rule):
        self.calls.append(("set_data_validation", a1_range))
        self.revision += 1
        return {}

    def insert_dimension_range(self, spreadsheet_token, sheet_id, major_dimension, start_index, end_index, inherit_style=None):
        self.calls.append(("insert_dimension_range", sheet_id, major_dimension, start_index, end_index))
        self.revision += 1
        return {}

    def delete_dimension_range(self, spreadsheet_token, sheet_id, major_dimension, start_index, end_index):
        self.calls.append(("delete_dimension_range", sheet_id, major_dimension, start_index, end_index))
        self.revision += 1
        return {"delCount": end_index - start_index + 1}

    def append_dimension(self, spreadsheet_token, sheet_id, major_dimension, length):
        self.calls.append(("append_dimension", sheet_id, major_dimension, length))
        self.revision += 1
        return {"addCount": length}

    def append_values(self, spreadsheet_token, a1_range, values, insert_data_option=None):
        self.calls.append(("append_values", a1_range, insert_data_option))
        self.revision += 1
        return {"updates": {"updatedRows": len(values)}}

    def merge_cells(self, spreadsheet_token, a1_range, merge_type):
        self.calls.append(("merge_cells", a1_range, merge_type))
        self.revision += 1
        return {}

    def unmerge_cells(self, spreadsheet_token, a1_range):
        self.calls.append(("unmerge_cells", a1_range))
        self.revision += 1
        return {}

    def batch_update_sheets(self, spreadsheet_token, requests):
        kinds = tuple(next(iter(r)) for r in requests)  # e.g. ("addSheet",)
        self.calls.append(("batch_update_sheets", kinds))
        self.revision += 1
        replies = []
        for r in requests:
            if "addSheet" in r:
                replies.append({"addSheet": {"properties": {"sheetId": "NEW"}}})
            elif "copySheet" in r:
                replies.append({"copySheet": {"properties": {"sheetId": "COPY"}}})
            elif "deleteSheet" in r:
                replies.append({"deleteSheet": {"result": True}})
        return {"replies": replies}

    def seams(self):
        return [c[0] for c in self.calls]


def _run(request, **gw_kwargs):
    """dry_run([request]) → apply; return (plan_entry, log_entry, gateway)."""
    gw = DispatchGateway(**gw_kwargs)
    plan = dry_run([request], gw, TOKEN)
    log = apply(plan, gw)
    return plan.entries[0], log.entries[0], gw


# =========================================================================== #
# VALUE — plain scalar write → put_values (write_kind "value", no structural)   #
# =========================================================================== #

def test_value_request_side_preview_and_entry_side_apply():
    entry, log, gw = _run(ValueWriteRequest.for_a1("s1!A1:A1", [["x"]]))
    # request-side keying: a plain value entry — write_kind "value", NO structural, target set
    assert (entry.outcome, entry.write_kind, entry.structural, entry.rich) == (
        "resolved", "value", None, False)
    assert entry.target.a1() == "s1!A1:A1"
    # entry-side keying: apply drove the VALUE seam
    assert gw.seams() == ["put_values"]
    assert log.outcome == "applied" and log.write_kind == "value"


# =========================================================================== #
# RICH — encoded cell → put_values, is_rich lifts the structured-cell refusal   #
# =========================================================================== #

def test_rich_request_side_preview_and_entry_side_apply():
    entry, log, gw = _run(RichCellWriteRequest.hyperlink("s1!A1", "https://x", "text"))
    assert (entry.outcome, entry.write_kind, entry.structural, entry.rich) == (
        "resolved", "value", None, True)
    assert gw.seams() == ["put_values"]         # a rich cell still writes through values
    assert log.outcome == "applied"


# =========================================================================== #
# DROPDOWN RULE — dataValidation → set_data_validation (write_kind "data-...")   #
# =========================================================================== #

def test_dropdown_request_side_preview_and_entry_side_apply():
    entry, log, gw = _run(DropdownRuleWriteRequest.list_rule("s1!A1:A1", ["a", "b"]))
    assert (entry.outcome, entry.write_kind, entry.structural) == (
        "resolved", "data-validation", None)
    assert entry.before is None                 # a rule has no scalar before
    assert gw.seams() == ["set_data_validation"]
    assert log.outcome == "applied" and log.write_kind == "data-validation"


# =========================================================================== #
# STRUCTURAL — the four dimension ops, keyed entry-side on structural["op"]      #
# =========================================================================== #

def test_structural_insert_dispatch():
    entry, log, gw = _run(InsertRowsAt(sheet_id=SID, before_row=2, count=1))
    assert entry.write_kind == "structure" and entry.structural["op"] == "insert"
    assert entry.target is None                 # a structural entry carries no A1 target
    assert gw.seams() == ["insert_dimension_range"]
    assert log.write_kind == "structure"


def test_structural_delete_dispatch_and_removed_snapshot():
    entry, log, gw = _run(DeleteRows(sheet_id=SID, first=2, last=2))
    assert entry.write_kind == "structure" and entry.structural["op"] == "delete"
    # delete previews its destructive-safe removed payload (delete-log parity)
    assert entry.after.get("removed") is not None
    assert gw.seams() == ["delete_dimension_range"]


def test_structural_append_dim_dispatch():
    entry, log, gw = _run(AppendDimension(sheet_id=SID, major_dimension="ROWS", length=2))
    assert entry.structural["op"] == "append-dim"
    assert gw.seams() == ["append_dimension"]


def test_structural_append_values_dispatch():
    entry, log, gw = _run(AppendRowsWithValues(a1_range="s1!A1:B1", values=[["x", "y"]]))
    assert entry.structural["op"] == "append-values"
    assert gw.seams() == ["append_values"]


# =========================================================================== #
# MERGE / UNMERGE — write_kind "merge", entry-side structural["op"]             #
# =========================================================================== #

def test_merge_dispatch():
    entry, log, gw = _run(MergeCells("s1!A1:B2"), values={"s1!A1:B2": [["a", "b"], ["c", "d"]]})
    assert entry.write_kind == "merge" and entry.structural["op"] == "merge"
    assert gw.seams() == ["merge_cells"]
    assert log.write_kind == "merge"


def test_unmerge_dispatch():
    entry, log, gw = _run(UnmergeCells("s1!A1:B2"))
    assert entry.write_kind == "merge" and entry.structural["op"] == "unmerge"
    assert gw.seams() == ["unmerge_cells"]


# =========================================================================== #
# TAB add / copy / delete — write_kind "tab", entry-side structural["op"]       #
# =========================================================================== #

def test_tab_add_dispatch():
    entry, log, gw = _run(AddTab("NewTab"))
    assert entry.write_kind == "tab" and entry.structural["op"] == "add-tab"
    assert gw.seams() == ["batch_update_sheets"]
    assert gw.calls[0][1] == ("addSheet",)      # the OWNED request element
    assert log.write_kind == "tab"


def test_tab_copy_dispatch():
    entry, log, gw = _run(CopyTab(source_sheet_id="src", dest_title="Copy"))
    assert entry.structural["op"] == "copy-tab"
    assert gw.calls[0][1] == ("copySheet",)


def test_tab_delete_dispatch():
    entry, log, gw = _run(DeleteTab("someSheetId"),
                          tabs=[{"sheet_id": "someSheetId", "title": "Gone"}])
    assert entry.structural["op"] == "delete-tab"
    assert gw.calls[0][1] == ("deleteSheet",)
    # destructive-safe: the removed tab identity was snapshot at plan time
    assert entry.after["removed_identity"] == {"sheet_id": "someSheetId", "title": "Gone"}


# =========================================================================== #
# MIXED BATCH — one dry_run over five distinct families in one plan: the         #
# strongest single pin that each kind keeps its own dispatch arm (no cross-wire).#
# =========================================================================== #

def test_mixed_batch_preserves_per_family_dispatch_and_order():
    gw = DispatchGateway()
    requests = [
        ValueWriteRequest.for_a1("s1!A1:A1", [["v"]]),          # value    → put_values
        DropdownRuleWriteRequest.list_rule("s1!B1:B1", ["a"]),  # dropdown → set_data_validation
        InsertRowsAt(sheet_id=SID, before_row=2, count=1),      # structural insert
        MergeCells("s1!D1:E1"),                                 # merge    → merge_cells
        AddTab("Extra"),                                        # tab      → batch_update_sheets
    ]
    plan = dry_run(requests, gw, TOKEN)

    # request-side keying, 1:1 in order (write_kind / structural op fingerprint)
    fingerprints = [
        (e.write_kind, None if e.structural is None else e.structural["op"])
        for e in plan.entries
    ]
    assert fingerprints == [
        ("value", None),
        ("data-validation", None),
        ("structure", "insert"),
        ("merge", "merge"),
        ("tab", "add-tab"),
    ]

    log = apply(plan, gw)
    # entry-side keying: each family drove its own seam, in order (no cross-wire)
    assert gw.seams() == [
        "put_values",
        "set_data_validation",
        "insert_dimension_range",
        "merge_cells",
        "batch_update_sheets",
    ]
    assert [e.outcome for e in log.entries] == ["applied"] * 5


# =========================================================================== #
# PUBLIC SURFACE PINS (B2) — the split must not change the re-export surface.    #
# =========================================================================== #

#: The exact ``larkdocio.sheets.__all__`` set (order-independent) at the LD-125
#: baseline — the split is internal only, so this set must be byte-identical after.
_SHEETS_ALL_BASELINE = frozenset({
    "DEFAULT_MAX_READS_PER_SEC", "SheetsReadClient", "deep_read_embedded_sheet",
    "split_compound_token", "UsedRange", "a1_column_to_number", "column_number_to_a1",
    "declared_grid_range", "trim_trailing_nulls", "used_range_a1", "Merge", "SheetTab",
    "SpreadsheetMeta", "ValueRange", "render_cell", "ExportedCell", "ExportedSheet",
    "ParsedWorkbook", "SheetsExportReader", "XlsxParseError", "parse_xlsx",
    # LD-152 — the standalone fidelity JOIN (title-keyed export → sheet_id-keyed render).
    # An ADDITIVE, deliberate widening of the re-export surface, recorded here the way
    # LD-149's formula family was: it lives in `export_reader` beside `ExportedSheet` /
    # `ParsedWorkbook` / `parse_xlsx`, which this facade already re-exports, so leaving the
    # join out would hand a consumer half of one module (dogfood F6 in miniature).
    "exported_by_sheet_id",
    # LD-155 — the filter read + its disclosure. The same additive, deliberate widening:
    # the filter's typed parse lives in `models` beside `SheetTab` / `Merge` and the note
    # composer in `table` beside `render_tab`, both of which this facade already re-exports,
    # so omitting them would again hand a consumer half of a module. The four FILTER_* state
    # slugs ship because they are the vocabulary a consumer BRANCHES on (`not-read` vs
    # `none` vs `active` vs `unavailable`), and a state machine whose constants are private
    # forces the consumer to hard-code string literals.
    "FILTER_ACTIVE", "FILTER_NONE", "FILTER_NOT_READ", "FILTER_UNAVAILABLE",
    "FilterColumn", "FilterCondition", "SheetFilter", "filter_disclosure_note",
    # LD-186 — the FROZEN-panes read leg (the read half of freeze panes). The same additive,
    # deliberate widening the filter-state slugs above are: the four state slugs are the
    # vocabulary a consumer BRANCHES on, and `FrozenPanes` / `parse_frozen_panes` live in
    # `models` beside `SheetTab`, which this facade already re-exports.
    "FROZEN_ACTIVE", "FROZEN_NONE", "FROZEN_NOT_READ", "FROZEN_UNAVAILABLE",
    "FrozenPanes", "parse_frozen_panes",
    "SheetsWriteClient", "normalize_write_range",
    # LD-176 — the spreadsheet FILE-lifecycle teardown vocabulary: the two already-gone codes
    # (a Drive delete of an already-trashed file and a sheets call against a trashed token
    # report the fact with DIFFERENT codes — live-observed) and the one predicate over them.
    # The same additive, deliberate widening as the filter-state slugs above: it is what a
    # consumer branches on in a `finally`, and `SheetsWriteClient` already rides this facade,
    # so omitting it would hand them half of one module.
    "SPREADSHEET_GONE_CODE", "FILE_ALREADY_DELETED_CODE", "spreadsheet_is_gone",
    # LD-583 — TWO names, the same additive, signed-off widening as every block above, and
    # for the same reason those blocks give: `create_spreadsheet`'s own ANSWER now has a type,
    # and a type a consumer cannot import is a type they cannot `isinstance` against. The
    # disclosure rides with it because `CAPTURE_THE_TOKEN` is the sentence this facade's own
    # teardown vocabulary (`spreadsheet_is_gone`, right above) exists to serve — round 5 lost
    # a live workbook to a create whose token was dropped. Nothing was LOST here, which is the
    # only thing this pin guards.
    "CreatedSpreadsheet", "CAPTURE_THE_TOKEN",
    "MAX_A1_COLUMN", "A1Cell", "WriteRange",
    "parse_write_range", "write_range_from_used_range", "ApplyLog", "ApplyLogEntry",
    "GateNotVerified", "Plan", "PlanEntry", "Refusal", "ValueWriteRequest", "WriteOpKind",
    # LD-149 — the formula write family (the seventh) + its typed build-time refusal.
    "FormulaWriteRequest", "FormulaExpressionError",
    "apply", "certify_gate_legs", "dry_run", "effective_verify_style", "requires_merge_leg",
    "requires_style_leg", "escape_cell", "matrix_to_gfm_table", "merge_covered_cells",
    "render_matrix", "render_spreadsheet", "render_tab", "tab_heading",
    # LD-190 — the three shipped-op truth riders. An ADDITIVE widening (this pin guards the
    # LD-125 split against LOSS, not against deliberate growth): the read-back comparator a
    # sheet self-check needs, and the two limits a consumer branches on — there is no colors
    # read-back, and MERGE_ALL is the only merge type.
    "DROPDOWN_COLORS_NOT_READ_BACK", "MERGE_VARIANTS_NOT_GATE_COVERED", "MergeTypeError",
    "NUMERIC_READ_BACK_NORMALIZED", "SUPPORTED_MERGE_TYPES",
    "cells_equivalent", "value_differences", "values_equivalent",
    # LD-331 — the per-cell FILL disclosure. Additive again, and for the same reason the
    # LD-190 riders were: the fill ARGB the export leg already recovered had no way of
    # reaching a reader, so the render disclosure and its structured half join the facade.
    "FidelityUnavailable", "cell_fills", "fill_disclosure_note",
    # LD-346 — the one click-proven mintable spreadsheet deep link and the loud cell-link
    # negative it points at. Additive again, same rule: `tab_url` is a pure offline string
    # function on this surface, and `SHEETS_CELL_LINK_UI_ONLY` (authored in common.url) is
    # re-exported so a consumer meets the "you cannot mint a cell link" verdict beside it.
    "tab_url", "SHEETS_CELL_LINK_UI_ONLY",
    # LD-383 — the spreadsheet walk's result vocabulary. Additive again, same rule: a caller
    # whose read came back PARTIAL (a tab Lark refused was skipped rather than allowed to end
    # the read) has to branch on that, and it cannot do so on types it has no name for.
    "SpreadsheetRead", "TabOutcome", "TabSkip", "TAB_READ", "TAB_SKIPPED",
    "skipped_tabs_disclosure",
    # LD-405 — the walk's URL-first FRONT DOOR: the same additive, issue-signed-off widening
    # as every entry above. The walk's only entry point was a client METHOD wanting a TOKEN,
    # so a consumer holding a link had nothing to call; `read_spreadsheet` /
    # `read_spreadsheet_markdown` are the `read_base` / `read_base_markdown` pairing one
    # surface over, and `resolve_spreadsheet` is the URL-or-token rule they share.
    "read_spreadsheet", "read_spreadsheet_markdown", "resolve_spreadsheet",
    # LD-457 — the refusal-reason VOCABULARY, the same additive widening as every entry
    # above and for the same reason the filter-state slugs shipped: it is what a consumer
    # BRANCHES on. `Refusal.reason` is a plain string carrying the wire value, the facade
    # already re-exports `Refusal`, and leaving the reasons off the surface is what made a
    # retry guard copied out of the guide compare against a spelling that matches nothing.
    "RefusalReason", "REFUSAL_REASONS",
})

#: The full symbol set the tests + the package import DIRECTLY from
#: ``larkdocio.sheets.write_apply`` — the thin facade must keep every one importable
#: after the split (zero downstream import churn).
_WRITE_APPLY_FACADE_SURFACE = frozenset({
    "AddTab", "AppendDimension", "AppendRowsWithValues", "ApplyLog", "ApplyLogEntry",
    "CopyTab", "DeleteCols", "DeleteRows", "DeleteTab", "DropdownRuleWriteRequest",
    "GateNotVerified", "InsertColsAt", "InsertRowsAt", "MergeCells", "Plan", "PlanEntry",
    "Refusal", "RichCellWriteRequest", "UnmergeCells", "ValueWriteRequest", "WriteOpKind",
    # LD-457 — the reason vocabulary rides the same facade its `Refusal` does.
    "RefusalReason", "REFUSAL_REASONS",
    # LD-149 — the formula family + the formula helpers the facade re-exports.
    "FormulaWriteRequest", "FormulaExpressionError", "FormulaRenderOptionUnsupported",
    "INERT_STRING_NOTE", "EXPRESSION_RENDER_OPTION", "COMPUTED_RENDER_OPTION",
    "encode_formula", "formula_expression",
    "apply", "certify_gate_legs", "dry_run", "effective_verify_style", "predict_merge_fate",
    "predict_merge_fates", "requires_merge_leg", "requires_style_leg",
})


def test_sheets_all_is_pinned_across_the_split():
    import larkdocio.sheets as s
    assert set(s.__all__) == _SHEETS_ALL_BASELINE


def test_write_apply_facade_reexports_full_surface():
    wa = importlib.import_module("larkdocio.sheets.write_apply")
    missing = {n for n in _WRITE_APPLY_FACADE_SURFACE if not hasattr(wa, n)}
    assert not missing, f"write_apply no longer re-exports {sorted(missing)}"


# =========================================================================== #
# ONE-REGISTRATION-POINT PROOF (B4) — the payoff of the LD-125 registry: a NEW  #
# op registers in ONE place (append one SheetsOpDescriptor to OPS) and is        #
# reachable by BOTH preview AND apply with no other edit. Before LD-125 this     #
# needed a coordinated edit to TWO hand-branched ladders keyed on different      #
# discriminators — the drift hazard the registry closes.                         #
# =========================================================================== #

def test_one_registration_point_reaches_both_preview_and_apply(monkeypatch):
    ops = importlib.import_module("larkdocio.sheets.ops")
    seen = {}

    def _dummy_preview(request, client, spreadsheet_token, merges=None):
        seen["preview"] = True
        return PlanEntry.resolved_structural(
            structural={"op": "dummy-op"}, after={"kind": "dummy"}, write_kind="dummy")

    def _dummy_apply(entry, client, spreadsheet_token, expected_revision):
        seen["apply"] = True
        return (
            ApplyLogEntry.applied_structural(
                structural={"op": "dummy-op"}, revision=expected_revision, write_kind="dummy"),
            expected_revision,
        )

    dummy = ops.SheetsOpDescriptor(
        kind="dummy",
        request_type=(),
        write_kind="dummy",          # the request-side key
        entry_ops=("dummy-op",),     # the entry-side key
        preview=_dummy_preview,
        apply=_dummy_apply,
    )
    # THE ONE registration point — append a single descriptor to OPS, nothing else.
    monkeypatch.setattr(ops, "OPS", ops.OPS + (dummy,))

    class _DummyRequest:
        write_kind = "dummy"

    gw = DispatchGateway()
    plan = dry_run([_DummyRequest()], gw, TOKEN)          # request-side → dummy PREVIEW
    assert seen.get("preview") is True, "the new op was not reached through preview dispatch"
    assert plan.entries[0].structural["op"] == "dummy-op"

    apply(plan, gw)                                        # entry-side → dummy APPLY
    assert seen.get("apply") is True, "the new op was not reached through apply dispatch"
