"""LD-185 live gate — the Sheets DIMENSION-PROPERTY write round-trip.

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it — together with every other family in one ring::

    pytest -m live_write

The live proof that row height / column width / hide-show round-trip **through the gated apply
engine** on a self-provisioned disposable, that the **characterized index convention is the one
that actually lands** (1-indexed INCLUSIVE — the delete convention, not insert's half-open
span), and that a hide is **restorable**:

* **HEIGHT** on rows 2..3 (a two-row band) and **WIDTH** on column B — verified through this
  op's **own leg**, the xlsx export's ``<row ht>`` / ``<col width>`` read
  (``ExportedSheet.row_dimensions`` / ``.col_dimensions``), which is the only read that can see
  a dimension property at all;
* **THE CONVENTION, live**: the band ``first=2, last=3`` must land on sheet rows **2 and 3** —
  not 3 and 4, and not row 3 alone. That single assertion is what a 0-indexed or half-open
  misreading would fail;
* **HIDE** row 4 → the export reports it ``hidden``, while a values read **still returns its
  content** (the fidelity event the plan disclosed);
* **RESTORE** → ``visible=True`` puts it back, and the export reports it un-hidden again;
* the plan-time **out-of-bounds** refusal against the real tab's real row count, proving **zero**
  writes were issued for it (the live revision does not move).

Writes use the WRITE app only (``LARK_WRITE_APP_*``); every target is a **self-provisioned
disposable** — never the scratch sheet, never the zoo, never a real document; the whole
disposable is deleted in ``finally`` and the zero-orphan close-out is a hard gate.

**Cost note.** The verification leg is an async whole-workbook export, so this arm runs it
**three** times (baseline / after / after-restore) and nowhere else — which is exactly why the
op's kind is kept out of the auto-on export-leg set: an export per column width would be absurd.
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
    DIMENSION_VERIFICATION_LEG,
    SetColProperties,
    SetRowProperties,
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


def _dimensions(exporter, token, title="Sheet1"):
    """``(sheet, row_dimensions, col_dimensions)`` for the disposable's only tab, read through
    the shipped export dimension leg."""
    workbook = exporter.read_workbook(token)
    sheet = workbook.sheet(title) or workbook.first_sheet
    return sheet, sheet.row_dimensions, sheet.col_dimensions


def test_sheets_dimension_property_write_gate_round_trip(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    gateway = H.SheetsLifecycleGateway.from_write_credentials(DOMAIN)
    writer = SheetsWriteClient.from_write_credentials(DOMAIN)
    exporter = SheetsExportReader.from_write_credentials(DOMAIN)

    tmpdir = tempfile.mkdtemp(prefix="ld185-sheets-dimension-gate-")
    ledger = H.Ledger(Path(tmpdir) / "run_ledger.json")

    evidence = {}
    with H.disposable(gateway, ledger, writer=writer) as d:
        evidence["token"] = d.token
        assert d.token, "create yielded no spreadsheet_token"
        sid = d.first_sheet_id
        evidence["sheet_id"] = sid

        # A marked grid, so a property landing on the wrong band is unmistakable.
        d.put_values(f"{sid}!A1:C5", [[f"A{r}", f"B{r}", f"C{r}"] for r in range(1, 6)])
        assert d.read_values(f"{sid}!A4:A4") == [["A4"]], "grid populate did not round-trip"

        _sheet, rows0, cols0 = _dimensions(exporter, d.token)
        evidence["baseline_custom_rows"] = sorted(rows0)
        evidence["baseline_cols"] = sorted(cols0)
        evidence["default_row_height"] = _sheet.default_row_height
        evidence["default_col_width"] = _sheet.default_col_width

        # 1) HEIGHT on a TWO-row band + WIDTH on one column + a HIDE, one gated batch.
        plan = dry_run(
            [SetRowProperties(sid, first=2, last=3, fixed_size=60),
             SetColProperties(sid, first=2, last=2, fixed_size=200),
             SetRowProperties(sid, first=4, last=4, visible=False)],
            writer, d.token)
        assert len(plan.resolved) == 3, f"a dimension write refused at dry-run: {plan.refusals!r}"
        assert [e.structural["convention"] for e in plan.entries] == ["1-index-inclusive"] * 3

        # the HIDE is disclosed as a fidelity event; the two size changes are not
        disclosures = [[n["kind"] for n in e.preview_notes] for e in plan.entries]
        assert disclosures == [[], [], ["hidden-dimension-fidelity"]], disclosures
        evidence["hide_note"] = plan.entries[2].preview_notes[0]["hidden_rows"]

        log = apply(plan, writer)
        assert [e.is_applied for e in log.entries] == [True, True, True], (
            [e.to_dict() for e in log.entries])
        assert log.entries[0].structural["verified_by"] == DIMENSION_VERIFICATION_LEG

        # 2) THE CONVENTION, LIVE — via this op's own leg.
        _sheet, rows1, cols1 = _dimensions(exporter, d.token)
        resized = sorted(r for r, dim in rows1.items()
                         if dim.size is not None and dim.size != (rows0.get(r) and rows0[r].size))
        evidence["rows_resized"] = resized
        assert 2 in rows1 and 3 in rows1, (
            f"the height did not land on rows 2 AND 3 (1-indexed inclusive): {rows1!r}")
        assert rows1[2].size == rows1[3].size, (
            f"the two rows of the band got different heights: {rows1!r}")
        assert 1 not in rows1 or rows1[1].size is None, (
            f"the band leaked onto row 1 — an off-by-one: {rows1!r}")
        evidence["row2_size"] = rows1[2].size
        evidence["row3_size"] = rows1[3].size

        assert 2 in cols1 and cols1[2].size is not None, (
            f"the width did not land on column B: {cols1!r}")
        evidence["colB_size"] = cols1[2].size

        # 3) THE HIDE — reported hidden by the export, and its content STILL readable (the
        #    fidelity event the plan disclosed: our reader would still emit it).
        assert rows1[4].hidden is True, f"row 4 is not hidden: {rows1.get(4)!r}"
        assert d.read_values(f"{sid}!A4:A4") == [["A4"]], (
            "the hidden row's content should still be readable — that is the fidelity event")
        evidence["row4_hidden"] = rows1[4].hidden

        # 4) The plan-time OUT-OF-BOUNDS refusal, against the real tab's real row count —
        #    and it must cost no write (the live revision does not move).
        geometry = writer.read_sheet_geometry(d.token, sid)
        row_count = geometry["row_count"]
        revision_before = writer.read_revision(d.token)
        over = dry_run(
            [SetRowProperties(sid, first=row_count, last=row_count + 5, fixed_size=60)],
            writer, d.token)
        assert over.entries[0].refusal.reason == Refusal.OUT_OF_BOUNDS_DIMENSION, (
            over.entries[0].to_dict())
        over_log = apply(over, writer)
        assert not over_log.entries[0].is_applied
        assert writer.read_revision(d.token) == revision_before, (
            "a refused out-of-bounds band moved the spreadsheet revision — it wrote something")
        evidence["out_of_bounds_row_count"] = row_count

        # 5) RESTORE — show row 4 again; the export reports it un-hidden.
        restore = apply(dry_run([SetRowProperties(sid, first=4, last=4, visible=True)],
                                writer, d.token), writer)
        assert restore.entries[0].is_applied, restore.entries[0].to_dict()
        _sheet, rows2, _cols2 = _dimensions(exporter, d.token)
        assert 4 not in rows2 or rows2[4].hidden is False, (
            f"row 4 is still hidden after the restore: {rows2.get(4)!r}")
        evidence["row4_hidden_after_restore"] = bool(4 in rows2 and rows2[4].hidden)
    # 6) delete-in-finally fired on with-exit (the whole disposable is removed).

    report = H.close_out(gateway, ledger)
    report.raise_if_orphans()
    assert report.all_clean, f"close-out found orphans: {report.orphans!r}"

    with capsys.disabled():
        print(
            "\n[LD-185 dimension-property gate] "
            f"token={evidence['token']} sheet_id={evidence['sheet_id']} "
            f"default_row_height={evidence.get('default_row_height')} "
            f"default_col_width={evidence.get('default_col_width')} "
            f"band(2..3)->row2_ht={evidence.get('row2_size')} "
            f"row3_ht={evidence.get('row3_size')} colB_width={evidence.get('colB_size')} "
            f"row4_hidden={evidence.get('row4_hidden')} "
            f"row4_hidden_after_restore={evidence.get('row4_hidden_after_restore')} "
            f"hide_note_rows={evidence.get('hide_note')} "
            f"out_of_bounds_vs_row_count={evidence.get('out_of_bounds_row_count')} "
            f"orphans={report.orphans!r}\n"
            f"{json.dumps(evidence, default=str)}"
        )
