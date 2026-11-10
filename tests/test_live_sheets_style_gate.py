"""THE L2 GATE — the Sheets style-leg fidelity round-trip (LD-118).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it explicitly — together with every other family in one ring::

    pytest -m live_write

This is the **binding live proof** that the Sheets L2 **style/number-format read** is
full-fidelity end-to-end. Where the LD-113 value gate proved a *value* write surgical with
the cheap live values-leg diff, THIS gate proves the **style leg** — the export-only crux
(LD-107 Q2): a cell's WHOLE-CELL (format-level) bold / fill / numFmt are invisible to the
values API and readable
**only** through the ``export_tasks`` → xlsx path. It joins the same ``live_write`` ring as
the docx W0..W3 gates + the LD-112 harness + the LD-113 value gate, so a single
``pytest -m live_write`` run exercises **all families together** (AC4).

The ring, against a spreadsheet it **provisions and destroys itself** — never the scratch
sheet, never the zoo, never the read canary, never a real document (AC5, D7):

1. **self-provisions** a disposable (the LD-112 ``disposable()`` context manager,
   delete-in-``finally`` + ledger) and **populates a 2×2 baseline** — the numeric target
   ``A1`` = ``0.1234`` (LD-107 Q2) plus three distinctive **guard-neighbour** cells (B1 /
   A2 / B2) whose style must stay untouched;
2. **exports the baseline** (the shipped LD-114 ``SheetsExportReader`` — export→poll→download
   →``zipfile``/``xml.etree`` parse) and asserts ``A1`` is **un-styled** (the reference the
   post-write export is confirmed against — the restore-verify / baseline-confirm);
3. **writes the style** to ``A1`` via the SHIPPED client's style op (LD-188 promoted the
   harness's ``SheetsStyleWriter`` into ``SheetsWriteClient.put_style``; this gate proves the L2
   READ fidelity, and since LD-188 it does so through ``src/`` on both sides) —
   ``{"font":{"bold":true},"backColor":"#FFFF00","formatter":"0.00%"}`` (LD-107 Q2);
4. **re-exports + stdlib-parses**, then asserts the parsed ``xl/styles.xml`` carries the
   **exact** fidelity: ``A1`` is **bold**, fill **``FFFFFF00``**, numFmt **``0.00%``** (the
   value ``0.1234`` preserved) — LD-107 Q2 reproduced **through shipped code** (AC2);
5. **proves the write surgical** — every style change lies **within** ``A1`` (the three
   guard neighbours' style is byte-identical baseline→post; a stray fill/bold reddens);
6. **deletes** the disposable in the harness ``finally`` (AC3), then runs the **zero-orphan
   close-out** re-querying every ledger token (AC4).

**Credentials (AC5, D1).** Every surface — the lifecycle gateway, the write client (values
AND style since LD-188), and the export reader — is built ``from_write_credentials`` (``LARK_WRITE_APP_*``,
never read/legacy). Because the WRITE app **owns what it creates**, it exports the disposable
it made too (no read-app collaborator). Writes ride the shared ≤3/s throttle; the export poll
is gentle (≥0.5s between polls).
"""
import json
import os
import tempfile
import time
from pathlib import Path

import pytest

import canary_support
import sheets_fidelity_diff as D
import sheets_write_harness as H
from larkdocio.sheets.export_reader import SheetsExportReader
from larkdocio.sheets.extent import UsedRange
from larkdocio.sheets.models import SheetTab
from larkdocio.sheets.table import cell_fills, render_tab
from larkdocio.sheets.write_client import SheetsWriteClient

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

# The write app's tenant region — NOT a document URL (the gate never addresses a
# pre-existing doc; it self-provisions its own disposable).
DOMAIN = "larksuite.com"

# A per-run nonce so the authored baseline is unique and the diff assertion is exact.
TOK = f"{int(time.time())}-{os.getpid()}"

# The LD-107 Q2 target: a numeric cell (renders "12.34%" once the 0.00% numFmt lands) that
# is the single style-write target; B1 / A2 / B2 are guard neighbours whose style must NOT
# move (the surgical proof for the style leg).
VALUE = 0.1234
GUARD_B1 = f"guard-B1 {TOK}"
GUARD_A2 = f"guard-A2 {TOK}"
GUARD_B2 = f"guard-B2 {TOK}"
BASELINE_ROWS = [[VALUE, GUARD_B1], [GUARD_A2, GUARD_B2]]
USED_RANGE_BODY = "A1:B2"     # the authored used range (matrix origin A1)
TARGET_A1 = "A1"             # the single-cell style target (row 0, col 0)

# The LD-107 Q2 style payload — bold font + a #FFFF00 fill + a 0.00% numFmt — which the
# spike PROVED lands in xl/styles.xml as <b/> + fill FFFFFF00 + numFmt "0.00%".
STYLE = {"font": {"bold": True}, "backColor": "#FFFF00", "formatter": "0.00%"}

# The exact resolved-style fidelity the export reader must recover (LD-107 Q2).
EXPECT_FILL_RGB = "FFFFFF00"
EXPECT_NUM_FMT = "0.00%"


def test_sheets_style_leg_fidelity_gate(capsys):
    # Load the repo .env (local runs) — a no-op in CI where creds are injected as
    # variables. Then skip LOUDLY if we cannot run.
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    gateway = H.SheetsLifecycleGateway.from_write_credentials(DOMAIN)
    writer = SheetsWriteClient.from_write_credentials(DOMAIN)
    reader = SheetsExportReader.from_write_credentials(DOMAIN)

    tmpdir = tempfile.mkdtemp(prefix="ld118-sheets-style-gate-")
    ledger = H.Ledger(Path(tmpdir) / "run_ledger.json")

    evidence = {}
    # LD-188: the value writer IS the styler — one shipped client, both seams.
    with H.disposable(gateway, ledger, writer=writer, styler=writer) as d:
        evidence["token"] = d.token
        evidence["sheet_id"] = d.first_sheet_id
        assert d.token, "create yielded no spreadsheet_token"
        assert H.is_disposable_title(d.title), "disposable was not titled with the grep-able DISPOSABLE prefix"

        sid = d.first_sheet_id
        used_range = f"{sid}!{USED_RANGE_BODY}"
        target = f"{sid}!{TARGET_A1}"

        # 1) Populate the 2×2 baseline: numeric target A1 + three guard neighbours.
        d.put_values(used_range, BASELINE_ROWS)

        # 2) Export the BASELINE and assert the target is un-styled — the reference the
        #    post-write export is confirmed against (the restore-verify / baseline-confirm).
        baseline_wb = reader.read_workbook(d.token)
        baseline_a1 = baseline_wb.first_sheet.cell(TARGET_A1)
        assert baseline_a1 is not None, (
            f"baseline export has no {TARGET_A1} cell: {baseline_wb.first_sheet.cells!r}"
        )
        assert baseline_a1.value == VALUE, (
            f"baseline {TARGET_A1} value is not the authored {VALUE}: {baseline_a1.value!r}"
        )
        assert baseline_a1.bold is False and baseline_a1.fill_rgb is None, (
            f"baseline {TARGET_A1} is unexpectedly pre-styled: {baseline_a1!r}"
        )
        assert baseline_a1.num_fmt != EXPECT_NUM_FMT, (
            f"baseline {TARGET_A1} already carries the target numFmt — the style change "
            f"would be a no-op: {baseline_a1!r}"
        )

        # 3) THE STYLE WRITE — bold + #FFFF00 fill + 0.00% numFmt to A1 ONLY (S5 style leg).
        d.put_style(target, STYLE)

        # 4) Re-export + stdlib-parse, then assert the EXACT LD-107 Q2 fidelity: the parsed
        #    xl/styles.xml carries bold + fill FFFFFF00 + numFmt 0.00% on A1 (AC2).
        post_wb = reader.read_workbook(d.token)
        post_a1 = post_wb.first_sheet.cell(TARGET_A1)
        assert post_a1 is not None, (
            f"post-write export has no {TARGET_A1} cell: {post_wb.first_sheet.cells!r}"
        )
        # The binding fidelity assertion — fails ACTIONABLY naming any missing attribute.
        D.assert_cell_style(
            post_a1, bold=True, fill_rgb=EXPECT_FILL_RGB, num_fmt=EXPECT_NUM_FMT
        )
        assert post_a1.value == VALUE, (
            f"the style write disturbed the {TARGET_A1} value: {post_a1.value!r} != {VALUE}"
        )

        # 5) Surgical proof: EVERY style change lies within A1 — the three guard neighbours'
        #    style stayed byte-identical baseline→post (a stray fill/bold reddens). This
        #    also confirms the baseline is the reference (restore-verify).
        diffs = D.assert_style_surgical(baseline_wb, post_wb, [TARGET_A1])
        changed_attrs = {sd.attr for sd in diffs if sd.ref == TARGET_A1}
        assert changed_attrs == {"bold", "fill_rgb", "num_fmt"}, (
            f"the style leg did not change EXACTLY bold+fill+numFmt on {TARGET_A1}: "
            f"{changed_attrs!r}"
        )
        # 5b) LD-331 — the recovered fill must REACH a reader, not just the parser. Both
        #     shipped seams are exercised over the LIVE export: the structured accessor
        #     (`cell_fills` → {ref: ARGB}) and the render disclosure (the note above the
        #     table, which is what makes a colour-encoded sheet recoverable from Markdown).
        #     The values-only render of the same rows must NOT carry the ARGB — the leg is
        #     what recovers it.
        live_fills = cell_fills(post_wb.first_sheet)
        assert live_fills == {TARGET_A1: EXPECT_FILL_RGB}, (
            f"the live fill did not reach cell_fills: {live_fills!r}"
        )
        live_tab = SheetTab(sheet_id=sid, title=post_wb.first_sheet.name, index=0,
                            row_count=len(BASELINE_ROWS), column_count=len(BASELINE_ROWS[0]))
        live_used = UsedRange.from_tab_values(live_tab, BASELINE_ROWS)
        disclosed = render_tab(live_tab, live_used, fidelity=post_wb.first_sheet)
        values_only = render_tab(live_tab, live_used)
        assert f"{EXPECT_FILL_RGB} — {TARGET_A1}" in disclosed, disclosed
        assert EXPECT_FILL_RGB not in values_only, values_only
        evidence["fill_through_the_seam"] = {
            "cell_fills": live_fills,
            "disclosure": next(ln for ln in disclosed.splitlines()
                               if ln.startswith("_(Cell fills")),
            "values_only_mentions_the_fill": EXPECT_FILL_RGB in values_only,
        }
        # 5c) LD-385 — the fill must reach a reader through the SHIPPED STANDALONE-SPREADSHEET
        #     leg, not only through a hand-assembled render_tab. `larkdocio.drive.read`'s
        #     sheets child (what the `folder` walk uses, and the one path from a spreadsheet
        #     URL to Markdown) called render_spreadsheet with NO fidelity argument, so a
        #     workbook whose meaning IS its colour rendered as blanks with no flag that could
        #     change it. This drives that leg end to end against the live disposable: OFF must
        #     be values-only, ON must carry the ARGB. The gate still reaches for NO read app:
        #     the WRITE app owns the disposable it created, so the leg's two read-side entry
        #     points are rebound to WRITE-app builders for the duration — the same reason this
        #     gate's own export reader is built from write credentials.
        #     `SheetsExportReader` is deliberately NOT re-imported here: it is already
        #     bound at module level (line 56) and used at line 105, so a local import
        #     would make it function-local for the whole body and crash the gate with
        #     UnboundLocalError before its first API call. Guarded by
        #     tests/test_ring_invocability_guard.py.
        from larkdocio.common.auth import get_write_credentials
        from larkdocio.drive import read as drive_read
        from larkdocio.sheets.client import SheetsReadClient

        sheet_url = f"https://larkdocio.{DOMAIN}/sheets/{d.token}"
        w_id, w_secret = get_write_credentials()
        _saved = (SheetsReadClient.__dict__["from_read_credentials"],
                  SheetsExportReader.__dict__["from_read_credentials"])
        SheetsReadClient.from_read_credentials = classmethod(
            lambda cls, domain=DOMAIN, **kw: cls(w_id, w_secret, domain, **kw))
        SheetsExportReader.from_read_credentials = (
            SheetsExportReader.__dict__["from_write_credentials"])
        try:
            leg_values_only, _rev = drive_read._read_sheet_markdown(sheet_url)
            leg_fidelity, _rev2 = drive_read._read_sheet_markdown(
                sheet_url, fidelity_read_sheets=True)
        finally:
            SheetsReadClient.from_read_credentials = _saved[0]
            SheetsExportReader.from_read_credentials = _saved[1]

        assert EXPECT_FILL_RGB not in leg_values_only, (
            "the values-only spreadsheet leg leaked the fill — the opt-in is not opt-in")
        assert f"{EXPECT_FILL_RGB} — {TARGET_A1}" in leg_fidelity, leg_fidelity
        evidence["standalone_leg"] = {
            "url_token": d.token,
            "values_only_carries_the_fill": EXPECT_FILL_RGB in leg_values_only,
            "fidelity_disclosure": next(
                ln for ln in leg_fidelity.splitlines() if ln.startswith("_(Cell fills")),
        }
        evidence["post_style"] = {
            "bold": post_a1.bold,
            "fill_rgb": post_a1.fill_rgb,
            "num_fmt": post_a1.num_fmt,
            "value": post_a1.value,
        }
        evidence["changed_attrs"] = sorted(changed_attrs)
    # 6) delete-in-finally already fired here (the with-block exited).

    # Zero-orphan close-out: re-query every ledger token, assert each is gone (AC3/AC4).
    report = H.close_out(gateway, ledger)
    report.raise_if_orphans()
    assert report.all_clean, f"close-out found orphans: {report.orphans!r}"
    assert report.ledger_count >= 1
    for rec in report.clean:
        assert rec["recheck_code"] == H.NOT_FOUND_CODE, (
            f"a gone token re-queried to {rec['recheck_code']}, expected "
            f"{H.NOT_FOUND_CODE} (deleted/not-found): {rec!r}"
        )
    ledger_entry = ledger.entries()[0]
    assert ledger_entry["deleted"] is True, "ledger did not mark the disposable deleted"
    evidence["ledger_count"] = report.ledger_count
    evidence["orphans"] = len(report.orphans)

    with capsys.disabled():
        print(
            "\n[live_write:sheets-style-gate] "
            f"token={evidence.get('token')} "
            f"sheet_id={evidence.get('sheet_id')} "
            f"post_style={json.dumps(evidence.get('post_style'))} "
            f"changed_attrs={json.dumps(evidence.get('changed_attrs'))} "
            f"fill_through_the_seam={json.dumps(evidence.get('fill_through_the_seam'))} "
            f"standalone_leg={json.dumps(evidence.get('standalone_leg'))} "
            f"ledger_count={evidence.get('ledger_count')} "
            f"orphans={evidence.get('orphans')}"
        )
