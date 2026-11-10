"""LD-188 live gate — the Sheets CELL STYLE write round-trip, through ``src/``.

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it — together with every other family in one ring::

    pytest -m live_write

**What this arm proves that the older L2 gate does not.** LD-118's
``tests/test_live_sheets_style_gate.py`` has exercised this endpoint nightly for the *read*
side's sake, styling through the harness's own writer. This arm proves the **shipped path**: the
typed request → ``dry_run`` → ``apply``, on a self-provisioned disposable, verified through the
export style leg the plan itself discloses the price of:

* **FILL + FONT + NUMBER-FORMAT** on ``A1:B1`` and a **number-format-only** write on ``A2``
  (probed: ``formatter`` alone is a legal write) — verified through the shipped L2 reader's
  resolved cell style (``bold`` / ``fill_rgb`` / ``num_fmt``);
* **the batch form**: two spans, N ranges, **ONE** call — asserted by the spreadsheet
  ``revision`` moving exactly once across it, which is what "one call" means on the wire;
* **the plan's cost disclosure** (``style-verification-cost``) really rides a live plan, and the
  export it names really is what confirms the write;
* **the merge disclosure** (``style-partial-merge``) fires against a real merge, and the live
  export confirms what it claims: styling the merge's anchor styles the anchor and leaves the
  covered cells alone. (This arm is what caught the first probe round's mis-reading — an
  anchor-only style write was expected to cover the whole span and did not — which sent the
  characterization back for a second, distinguishing round.);
* **RESTORE** — the styled cells are returned to a plain baseline (``bold=False``, a white fill)
  and the export confirms it, so the arm leaves nothing it can restore un-restored even though the
  whole workbook is then deleted. **The number format is the one thing it cannot restore**:
  ``formatter="General"`` is refused ``90204 invalid formatter`` (observed here), and no probe
  establishes what this field accepts as "no format", so the arm does not guess one;
* the plan-time **unknown-tab** refusal against a real spreadsheet, proving **zero** writes were
  issued for it (the live ``revision`` does not move).

**The font SIZE is deliberately not asserted from the export.** The shipped
:class:`~larkdocio.sheets.export_reader.ExportedCell` reports bold / italic / fill / number
format and **no size** — and changing the read side is out of this issue's scope — so the size is
written (proving it is accepted) and not read back, rather than asserting a field nobody ships.

Writes use the WRITE app only (``LARK_WRITE_APP_*``); every target is a **self-provisioned
disposable** — never the scratch sheet, never the zoo, never a real document; the whole
disposable is deleted in ``finally`` and the zero-orphan close-out is a hard gate.

**Cost note.** The verification leg is an async whole-workbook export, so this arm runs it
**three** times (baseline / after / after-restore) and nowhere else — which is exactly the price
the plan's own note states.
"""
import json
import tempfile
from pathlib import Path

import pytest

import canary_support
import sheets_write_harness as H
from log_reading_apply import reading_the_log
from larkdocio.sheets.export_reader import SheetsExportReader
from larkdocio.sheets.plan import Refusal
from larkdocio.sheets.write_apply import (
    STYLE_VERIFICATION_LEG,
    BatchStyleWriteRequest,
    CellStyle,
    StyleSpan,
    StyleWriteRequest,
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

#: The style the write spike proved lands as bold + fill ``FFFFFF00`` + numFmt ``0.00%``, plus a
#: font size (accepted, not read back — the export reports no size).
HEADER = CellStyle(bold=True, font_size=18, back_color="#FFFF00", formatter="0.00%")
EXPECT_FILL = "FFFFFF00"
EXPECT_NUM_FMT = "0.00%"
#: The un-styled baseline the arm restores to — font and fill only. **A number format cannot be
#: cleared through this field on any value we can justify**: the obvious ``formatter="General"``
#: is refused live (``90204 invalid formatter``, observed by this very arm on its first run), and
#: no probe establishes what Lark accepts as "no format", so nothing is guessed. The number format
#: is therefore left as written and the arm asserts only what it really restores.
BASELINE = CellStyle(bold=False, italic=False, back_color="#FFFFFF")


def _cells(exporter, token, refs):
    """``{ref: ExportedCell}`` for the disposable's first tab, through the shipped style leg."""
    sheet = exporter.read_workbook(token).first_sheet
    return {ref: sheet.cell(ref) for ref in refs}


def _style_of(cell):
    return None if cell is None else {
        "value": cell.value, "bold": cell.bold, "italic": cell.italic,
        "fill_rgb": cell.fill_rgb, "num_fmt": cell.num_fmt,
    }


def test_sheets_style_write_gate_round_trip(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    gateway = H.SheetsLifecycleGateway.from_write_credentials(DOMAIN)
    writer = SheetsWriteClient.from_write_credentials(DOMAIN)
    exporter = SheetsExportReader.from_write_credentials(DOMAIN)

    tmpdir = tempfile.mkdtemp(prefix="ld188-sheets-style-gate-")
    ledger = H.Ledger(Path(tmpdir) / "run_ledger.json")

    refs = ["A1", "B1", "A2", "C1", "D1", "D2", "D3"]
    evidence = {}
    with H.disposable(gateway, ledger, writer=writer, styler=writer) as d:
        evidence["token"] = d.token
        assert d.token, "create yielded no spreadsheet_token"
        sid = d.first_sheet_id
        evidence["sheet_id"] = sid

        # A marked, numeric-bearing grid: A1/B1/A2 are the style targets, C1 the guard
        # neighbour, D1:D3 the merge the disclosure fires on.
        d.put_values(f"{sid}!A1:D3", [[0.1234, 0.5, "guard-C1", "merge-D1"],
                                      [0.42, "b2", "c2", None],
                                      ["a3", "b3", "c3", None]])
        writer.merge_cells(d.token, f"{sid}!D1:D3")

        baseline = _cells(exporter, d.token, refs)
        assert baseline["A1"] is not None, "the baseline export has no A1"
        assert baseline["A1"].bold is False and baseline["A1"].fill_rgb is None, (
            f"A1 is unexpectedly pre-styled: {baseline['A1']!r}")
        evidence["baseline"] = {r: _style_of(c) for r, c in baseline.items()}

        # 1) FILL + FONT + NUMBER-FORMAT on A1:B1, and a NUMBER-FORMAT-ONLY write on A2.
        plan = dry_run([StyleWriteRequest(f"{sid}!A1:B1", HEADER),
                        StyleWriteRequest(f"{sid}!A2:A2", CellStyle(formatter=EXPECT_NUM_FMT))],
                       writer, d.token)
        assert len(plan.resolved) == 2, f"a style write refused at dry-run: {plan.refusals!r}"
        cost = next(n for n in plan.entries[0].preview_notes
                    if n["kind"] == "style-verification-cost")
        assert cost["verified_by"] == STYLE_VERIFICATION_LEG, cost
        evidence["cost_note"] = {"verified_by": cost["verified_by"],
                                 "scope": cost["scope"]}

        log = apply(plan, writer)
        assert [e.is_applied for e in log.entries] == [True, True], (
            [e.to_dict() for e in log.entries])
        assert log.entries[0].structural["verified_by"] == STYLE_VERIFICATION_LEG
        assert isinstance(log.entries[0].revision, int) and log.entries[0].revision > 0, (
            f"the style apply recorded no post-write revision: {log.entries[0].to_dict()!r}")

        # 2) THE BATCH FORM — two spans, three ranges, ONE call: the revision moves ONCE.
        revision_before_batch = writer.read_revision(d.token)
        batch = BatchStyleWriteRequest([
            StyleSpan([f"{sid}!A3:A3", f"{sid}!B3:B3"], CellStyle(italic=True)),
            StyleSpan([f"{sid}!C3:C3"], CellStyle(back_color="#D9EAD3")),
        ])
        batch_log = apply(dry_run([batch], writer, d.token), writer)
        assert batch_log.entries[0].is_applied, batch_log.entries[0].to_dict()
        revision_after_batch = writer.read_revision(d.token)
        evidence["batch"] = {"ranges": len(batch.ranges),
                             "revision_before": revision_before_batch,
                             "revision_after": revision_after_batch}
        assert revision_after_batch - revision_before_batch == 1, (
            f"three ranges did not cost ONE call: the revision moved "
            f"{revision_after_batch - revision_before_batch} times")

        # 3) THE MERGE DISCLOSURE, live — and the style really covers the whole span.
        merge_plan = dry_run([StyleWriteRequest(f"{sid}!D1:D1",
                                               CellStyle(back_color="#FFFF00", bold=True))],
                            writer, d.token)
        merge_note = next(n for n in merge_plan.entries[0].preview_notes
                          if n["kind"] == "style-partial-merge")
        assert merge_note["whole_regions"] == [f"{sid}!D1:D3"], merge_note
        evidence["merge_note"] = {"ranges": merge_note["merged_ranges"],
                                  "whole_regions": merge_note["whole_regions"]}
        assert apply(merge_plan, writer).entries[0].is_applied

        # 4) The export style leg confirms every one of those writes.
        after = _cells(exporter, d.token, refs)
        evidence["after"] = {r: _style_of(c) for r, c in after.items()}
        for ref in ("A1", "B1"):
            assert after[ref].bold is True, f"{ref} is not bold: {after[ref]!r}"
            assert after[ref].fill_rgb == EXPECT_FILL, f"{ref} fill: {after[ref]!r}"
            assert after[ref].num_fmt == EXPECT_NUM_FMT, f"{ref} numFmt: {after[ref]!r}"
        assert after["A1"].value == 0.1234, (
            f"the style write disturbed A1's value: {after['A1']!r}")
        assert after["A2"].num_fmt == EXPECT_NUM_FMT and after["A2"].bold is False, (
            f"the number-format-only write did more (or less) than it said: {after['A2']!r}")
        assert after["C1"].bold is False and after["C1"].fill_rgb is None, (
            f"the guard neighbour C1 was restyled — the write was not surgical: {after['C1']!r}")
        # THE CORRECTED FINDING, live: the anchor carries the style and the merge's covered
        # cells carry none — a merge does not spread a style.
        assert after["D1"].fill_rgb == EXPECT_FILL, f"the anchor D1 is unstyled: {after['D1']!r}"
        for ref in ("D2", "D3"):
            assert after[ref].fill_rgb is None, (
                f"a style on the anchor D1 spread to the covered cell {ref}, which contradicts "
                f"the probed finding: {after[ref]!r}")

        # 5) The plan-time UNKNOWN-TAB refusal — and it must cost no write.
        revision_before = writer.read_revision(d.token)
        unknown = dry_run([StyleWriteRequest("deadbe!A1:A1", CellStyle(bold=True))],
                          writer, d.token)
        assert unknown.entries[0].refusal.reason == Refusal.UNKNOWN_TAB, (
            unknown.entries[0].to_dict())
        assert not apply(unknown, writer).entries[0].is_applied
        assert writer.read_revision(d.token) == revision_before, (
            "a refused unknown-tab style moved the spreadsheet revision — it wrote something")

        # 6) RESTORE the styled cells to an un-styled baseline, and confirm it.
        restore = apply(dry_run([BatchStyleWriteRequest.one_style(
            [f"{sid}!A1:B1", f"{sid}!A2:A2", f"{sid}!A3:C3", f"{sid}!D1:D3"], BASELINE)],
            writer, d.token), writer)
        assert restore.entries[0].is_applied, (
            f"the restore refused: {restore.entries[0].to_dict()['refusal']}")
        restored = _cells(exporter, d.token, refs)
        evidence["restored"] = {r: _style_of(c) for r, c in restored.items()}
        for ref in ("A1", "B1"):
            cell = restored[ref]
            assert cell.bold is False, f"{ref} is still bold after the restore: {cell!r}"
        assert restored["A1"].value == 0.1234, "the restore disturbed A1's value"
        # ...and the number format is honestly still there: see BASELINE's note.
        assert restored["A1"].num_fmt == EXPECT_NUM_FMT, (
            f"A1's number format changed unexpectedly — the restore claims not to touch it: "
            f"{restored['A1']!r}")
    # 7) delete-in-finally fired on with-exit (the whole disposable is removed).

    report = H.close_out(gateway, ledger)
    report.raise_if_orphans()
    assert report.all_clean, f"close-out found orphans: {report.orphans!r}"

    with capsys.disabled():
        print(
            "\n[LD-188 style-write gate] "
            f"token={evidence['token']} sheet_id={evidence['sheet_id']} "
            f"cost_note={json.dumps(evidence.get('cost_note'))} "
            f"A1_after={json.dumps(evidence['after'].get('A1'))} "
            f"A2_after={json.dumps(evidence['after'].get('A2'))} "
            f"C1_guard={json.dumps(evidence['after'].get('C1'))} "
            f"merged_anchor_D1_after={json.dumps(evidence['after'].get('D1'))} "
            f"merged_covered_D2_after={json.dumps(evidence['after'].get('D2'))} "
            f"merge_note={json.dumps(evidence.get('merge_note'))} "
            f"batch={json.dumps(evidence.get('batch'))} "
            f"A1_restored={json.dumps(evidence['restored'].get('A1'))} "
            f"orphans={report.orphans!r}"
        )
