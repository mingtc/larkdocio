"""LD-149 live gate — the Sheets FORMULA write round-trip (dogfood round-2 **T23**).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it — together with every other family in one ring::

    pytest -m live_write

The live proof that a formula written through the gated apply engine **actually evaluates**,
on a **self-provisioned disposable** the gate creates and deletes in the same run (never the
canary sheet, never the zoo, never a maintainer surface). Nine arms, each one a claim the offline
suite can only model:

* **(a) the round-trip** — ``FormulaWriteRequest`` → ``dry_run`` (preview: the expression +
  the target's current computed value) → ``apply`` → the apply-log's ``formula`` record
  carries the **computed** value read back off the live sheet, ``evaluated: True``;
* **(b) the four render modes** — ``Formula`` / ``UnformattedValue`` / ``FormattedValue`` /
  ``ToString`` asserted on the written cell (the LD-100 matrix discipline);
* **(c) surgical + restored** — the whole used-range is diffed before/after (only the target
  changed) and then restored to a byte-identical baseline before teardown;
* **(d) THE TRAP, live** — a plain ``"=SUM(...)"`` value write gets the loud dry-run note, is
  applied, and is **proven inert** on the live sheet. This is what makes the note honest;
* **(e) the precondition, both ways** — changing the **data** under a plan does **not** refuse
  (the computed value moved; the expression did not), while an out-of-band edit to the
  **expression** refuses ``precondition-mismatch`` with **zero** writes;
* **(f) an invalid formula** — ``"=SUM("`` is **accepted** by Lark (no error) and stored inert;
  the engine detects it (``evaluated: False``, ``ApplyLog.formula_not_evaluated``);
* **(g) error sentinels** — a bad function name evaluates to ``#NAME?`` (``error_value``), and
  a cross-tab reference by ``sheet_id`` (instead of by TITLE) to ``#REF!``;
* **(h) cross-tab by TITLE + normalization** — ``=SUM(Other!A1:A2)`` computes, and Lark
  rewrites the stored expression to ``=SUM('Other'!A1:A2)`` (``normalized``);
* **(i) commas + a merge anchor** — a nested comma-bearing expression round-trips verbatim
  (the multi-select comma interplay non-regression), a formula into a merge **anchor** applies,
  and a formula into a merge-**covered** cell refuses at plan time.

Every write goes through the gate; the ``finally``-delete + the zero-orphan close-out are the
LD-112 harness's, unchanged.
"""
import json
import tempfile
from pathlib import Path

import pytest

import canary_support
import sheets_values_diff as D
import sheets_write_harness as H
from log_reading_apply import reading_the_log
from larkdocio.sheets.formula import (
    COMPUTED_RENDER_OPTION,
    DISPLAY_RENDER_OPTION,
    EXPRESSION_RENDER_OPTION,
    INERT_STRING_NOTE,
)
from larkdocio.sheets.write_apply import (
    AddTab,
    FormulaWriteRequest,
    MergeCells,
    Refusal,
    ValueWriteRequest,
    apply,
    dry_run,
)
from larkdocio.sheets.write_client import SheetsWriteClient

# This gate's subject is the LOG — which entry landed, which refused, with which typed
# reason — not the return-vs-raise policy (pinned offline in
# tests/test_apply_refusal_policy.py, proved live in
# tests/test_live_write_refusal_policy_gate.py). So it opts into partial application
# once, here, the same way the offline log-reading suites do.
apply = reading_the_log(apply)

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

DOMAIN = "larksuite.com"

SUM_EXPR = "=SUM(B3:B8)"
NESTED_EXPR = '=IF(SUM(B3:B8)>10,"big","small")'


def _apply_one(request, writer, token, **kw):
    """dry_run one request → apply → ``(plan, log)``; the whole gate, nothing skipped."""
    plan = dry_run([request], writer, token, **kw)
    return plan, apply(plan, writer)


def test_sheets_formula_write_gate_round_trip(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    gateway = H.SheetsLifecycleGateway.from_write_credentials(DOMAIN)
    writer = SheetsWriteClient.from_write_credentials(DOMAIN)

    tmpdir = tempfile.mkdtemp(prefix="ld149-sheets-formula-gate-")
    ledger = H.Ledger(Path(tmpdir) / "run_ledger.json")

    ev = {}
    with H.disposable(gateway, ledger, writer=writer) as d:
        ev["token"] = d.token
        ev["sheet_id"] = d.first_sheet_id
        assert d.token, "create yielded no spreadsheet_token"
        sid = d.first_sheet_id

        # ---- seed the operand data (a plain value write, not the subject) -------- #
        d.put_values(f"{sid}!B3:B8", [[1], [2], [3], [4], [5], [6]])
        baseline = d.read_values(f"{sid}!A1:H10")

        # ================================================================== #
        # (a) THE ROUND-TRIP — a formula through the gate, verified live.      #
        # ================================================================== #
        target = f"{sid}!C1:C1"
        plan, log = _apply_one(FormulaWriteRequest.for_a1(target, SUM_EXPR), writer, d.token)

        note = plan.entries[0].preview_note
        assert note["kind"] == "formula", note
        assert note["expression"] == SUM_EXPR
        assert note["precondition_compares"] == "expression"
        ev["preview_current_computed"] = note["current_computed_value"]

        entry = log.entries[0]
        assert entry.outcome == "applied", entry.to_dict()
        assert entry.write_kind == "formula"
        assert entry.formula["evaluated"] is True, entry.formula
        assert entry.formula["computed_value"] == 21, entry.formula
        assert entry.formula["error_value"] is False, entry.formula
        assert log.formula_not_evaluated == (), "the formula must not have landed inert"
        ev["round_trip"] = {k: entry.formula[k] for k in
                            ("expression", "stored_expression", "computed_value",
                             "evaluated", "error_value", "normalized")}

        # ================================================================== #
        # (b) ALL FOUR RENDER MODES on the written cell (LD-100 discipline).   #
        # ================================================================== #
        modes = {
            mode: d.read_values(target, value_render_option=mode)[0][0]
            for mode in (EXPRESSION_RENDER_OPTION, COMPUTED_RENDER_OPTION,
                         DISPLAY_RENDER_OPTION, "ToString")
        }
        assert modes[EXPRESSION_RENDER_OPTION] == SUM_EXPR, modes
        assert modes[COMPUTED_RENDER_OPTION] == 21, modes
        assert modes[DISPLAY_RENDER_OPTION] == 21, modes
        assert modes["ToString"] == "SUM(B3:B8)", modes    # the leading '=' is STRIPPED
        ev["render_modes"] = modes

        # ================================================================== #
        # (c) SURGICAL — only the target changed — then RESTORE byte-identical. #
        # ================================================================== #
        after = d.read_values(f"{sid}!A1:H10")
        D.assert_surgical(baseline, after, target)
        d.put_values(target, [[None]])
        D.assert_identical(baseline, d.read_values(f"{sid}!A1:H10"))
        ev["surgical_and_restored"] = True

        # ================================================================== #
        # (d) THE TRAP, LIVE — a '='-prefixed PLAIN string is flagged, and IS  #
        #     inert. The dry-run note is only honest if this holds.            #
        # ================================================================== #
        trap_cell = f"{sid}!C2:C2"
        trap_plan, trap_log = _apply_one(
            ValueWriteRequest.for_a1(trap_cell, [[SUM_EXPR]]), writer, d.token)
        trap_note = trap_plan.entries[0].preview_note
        assert trap_note is not None, "a '='-prefixed plain string must be flagged at dry-run"
        assert trap_note["kind"] == "equals-prefixed-plain-string"
        assert trap_note["note"] == INERT_STRING_NOTE
        assert trap_log.entries[0].outcome == "applied"

        trap_modes = {
            mode: d.read_values(trap_cell, value_render_option=mode)[0][0]
            for mode in (EXPRESSION_RENDER_OPTION, COMPUTED_RENDER_OPTION,
                         DISPLAY_RENDER_OPTION, "ToString")
        }
        assert set(trap_modes.values()) == {SUM_EXPR}, (
            f"the note promised INERT TEXT; the live sheet says {trap_modes!r}")
        ev["trap_modes"] = trap_modes

        # ================================================================== #
        # (e) THE PRECONDITION (tier 2), BOTH WAYS.                            #
        #                                                                     #
        # Any out-of-band write bumps the spreadsheet `revision`, so tier 1     #
        # (the STALE_SHEET compare-and-swap) fires FIRST and would mask tier 2. #
        # Each armed plan therefore carries a LEADING sacrificial entry: it     #
        # absorbs the stale refusal and RESYNCS the anchor (the documented      #
        # resync-and-continue semantics), so the formula entry behind it is     #
        # judged on a fresh revision and its EXPRESSION precondition alone is   #
        # what decides. That is the only way to isolate tier 2 live.            #
        # ================================================================== #
        pre_cell = f"{sid}!C3:C3"
        apply(dry_run([FormulaWriteRequest.for_a1(pre_cell, SUM_EXPR)], writer, d.token), writer)
        assert d.read_values(pre_cell, value_render_option=COMPUTED_RENDER_OPTION) == [[21]]

        # (e-i) the DATA moves under an armed plan → the formula write STILL applies.
        armed = dry_run(
            [ValueWriteRequest.for_a1(f"{sid}!H1:H1", [["stale-absorber"]]),
             FormulaWriteRequest.for_a1(pre_cell, "=SUM(B3:B8)*2")],
            writer, d.token)
        d.put_values(f"{sid}!B3:B3", [[100]])          # an out-of-band DATA edit (1 -> 100)
        data_log = apply(armed, writer)
        assert data_log.entries[0].refusal.reason == Refusal.STALE_SHEET, (
            data_log.entries[0].to_dict())            # tier 1 fired and resynced the anchor
        assert data_log.entries[1].outcome == "applied", (
            "a changed COMPUTED value must not refuse — the expression did not drift: "
            f"{data_log.entries[1].to_dict()!r}")
        assert data_log.entries[1].formula["computed_value"] == 240, data_log.entries[1].formula
        ev["data_drift_applied"] = data_log.entries[1].formula["computed_value"]

        # (e-ii) the EXPRESSION moves under an armed plan → refuses, cell untouched.
        armed2 = dry_run(
            [ValueWriteRequest.for_a1(f"{sid}!H2:H2", [["stale-absorber"]]),
             FormulaWriteRequest.for_a1(pre_cell, SUM_EXPR)],
            writer, d.token)
        apply(dry_run([FormulaWriteRequest.for_a1(pre_cell, "=SUM(B3:B4)")], writer, d.token),
              writer)                                  # an out-of-band EXPRESSION edit
        before_expr = d.read_values(pre_cell, value_render_option=EXPRESSION_RENDER_OPTION)
        expr_log = apply(armed2, writer)
        assert expr_log.entries[0].refusal.reason == Refusal.STALE_SHEET, (
            expr_log.entries[0].to_dict())            # tier 1 fired and resynced the anchor
        assert expr_log.entries[1].refusal is not None, expr_log.entries[1].to_dict()
        assert expr_log.entries[1].refusal.reason == Refusal.PRECONDITION_MISMATCH, (
            expr_log.entries[1].to_dict())
        assert d.read_values(
            pre_cell, value_render_option=EXPRESSION_RENDER_OPTION) == before_expr, (
            "a refused formula write must not have touched the cell")
        ev["expression_drift_refused"] = expr_log.entries[1].refusal.reason

        # ================================================================== #
        # (f) AN INVALID FORMULA — accepted by Lark, detected by the engine.   #
        # ================================================================== #
        bad_cell = f"{sid}!C4:C4"
        _p, bad_log = _apply_one(
            FormulaWriteRequest.for_a1(bad_cell, "=SUM("), writer, d.token)
        bad = bad_log.entries[0]
        assert bad.outcome == "applied", "Lark accepts it — the log must not deny the write"
        assert bad.formula["evaluated"] is False, bad.formula
        assert bad_log.formula_not_evaluated == (bad,)
        assert d.read_values(bad_cell, value_render_option=COMPUTED_RENDER_OPTION) == [["=SUM("]]
        ev["invalid_formula"] = {"evaluated": bad.formula["evaluated"],
                                 "computed": bad.formula["computed_value"]}

        # ================================================================== #
        # (g) ERROR SENTINELS — a live formula whose evaluation failed.        #
        # ================================================================== #
        name_cell = f"{sid}!C5:C5"
        _p, name_log = _apply_one(
            FormulaWriteRequest.for_a1(name_cell, "=NOTAFUNC(B3)"), writer, d.token)
        name_rec = name_log.entries[0].formula
        assert name_rec["evaluated"] is True and name_rec["error_value"] is True, name_rec
        ev["bad_function"] = name_rec["computed_value"]

        # ================================================================== #
        # (h) CROSS-TAB by TITLE (works + normalized) vs by sheet_id (#REF!).  #
        # ================================================================== #
        tab_log = apply(dry_run([AddTab("Other")], writer, d.token), writer)
        other_sid = tab_log.entries[0].structural["new_sheet_id"]
        assert other_sid, tab_log.entries[0].to_dict()
        d.put_values(f"{other_sid}!A1:A2", [[10], [20]])

        by_title = _apply_one(
            FormulaWriteRequest.for_a1(f"{sid}!D1:D1", "=SUM(Other!A1:A2)"),
            writer, d.token)[1].entries[0].formula
        assert by_title["evaluated"] is True and by_title["computed_value"] == 30, by_title
        assert by_title["normalized"] is True, by_title      # Lark quotes the tab title
        ev["cross_tab_by_title"] = {k: by_title[k] for k in
                                    ("stored_expression", "computed_value", "normalized")}

        by_id = _apply_one(
            FormulaWriteRequest.for_a1(f"{sid}!D2:D2", f"=SUM({other_sid}!A1:A2)"),
            writer, d.token)[1].entries[0].formula
        assert by_id["error_value"] is True, (
            f"a cross-tab reference by sheet_id should not resolve: {by_id!r}")
        ev["cross_tab_by_sheet_id"] = by_id["computed_value"]

        # ================================================================== #
        # (i) COMMAS (multi-select interplay) + the MERGE ANCHOR split.        #
        # ================================================================== #
        nested = _apply_one(
            FormulaWriteRequest.for_a1(f"{sid}!D3:D3", NESTED_EXPR), writer, d.token
        )[1].entries[0].formula
        assert nested["evaluated"] is True, nested
        assert nested["computed_value"] == "big", nested
        assert d.read_values(
            f"{sid}!D3:D3", value_render_option=EXPRESSION_RENDER_OPTION) == [[NESTED_EXPR]], (
            "the commas / quotes in a nested expression must round-trip verbatim")
        ev["nested_commas"] = nested["computed_value"]

        apply(dry_run([MergeCells(f"{sid}!E1:F1")], writer, d.token), writer)
        merges = (writer.read_sheet_geometry(d.token, sid) or {}).get("merges") or []
        assert merges, "the merge did not land, so the anchor/covered split is untestable"

        anchor_log = apply(
            dry_run([FormulaWriteRequest.for_a1(f"{sid}!E1:E1", SUM_EXPR)],
                    writer, d.token, merges=merges),
            writer)
        assert anchor_log.entries[0].outcome == "applied", anchor_log.entries[0].to_dict()
        assert anchor_log.entries[0].formula["evaluated"] is True
        ev["merge_anchor_computed"] = anchor_log.entries[0].formula["computed_value"]

        covered_plan = dry_run([FormulaWriteRequest.for_a1(f"{sid}!F1:F1", SUM_EXPR)],
                               writer, d.token, merges=merges)
        assert covered_plan.entries[0].refusal.reason == Refusal.MERGED_CELL_TARGET, (
            covered_plan.entries[0].to_dict())
        ev["merge_covered_refused"] = covered_plan.entries[0].refusal.reason
    # the delete-in-finally fired on with-exit (the whole disposable is removed).

    report = H.close_out(gateway, ledger)
    report.raise_if_orphans()
    assert report.all_clean, f"close-out found orphans: {report.orphans!r}"
    ev["orphans"] = len(report.orphans)

    with capsys.disabled():
        print(
            "\n[live_write:sheets-formula-gate] "
            f"token={ev.get('token')} sheet_id={ev.get('sheet_id')} "
            f"round_trip={json.dumps(ev.get('round_trip'))} "
            f"render_modes={json.dumps(ev.get('render_modes'))} "
            f"surgical_and_restored={ev.get('surgical_and_restored')} "
            f"trap_modes={json.dumps(ev.get('trap_modes'))} "
            f"data_drift_applied={ev.get('data_drift_applied')} "
            f"expression_drift_refused={ev.get('expression_drift_refused')} "
            f"invalid_formula={json.dumps(ev.get('invalid_formula'))} "
            f"bad_function={ev.get('bad_function')!r} "
            f"cross_tab_by_title={json.dumps(ev.get('cross_tab_by_title'))} "
            f"cross_tab_by_sheet_id={ev.get('cross_tab_by_sheet_id')!r} "
            f"nested_commas={ev.get('nested_commas')!r} "
            f"merge_anchor_computed={ev.get('merge_anchor_computed')} "
            f"merge_covered_refused={ev.get('merge_covered_refused')} "
            f"orphans={ev.get('orphans')}"
        )
