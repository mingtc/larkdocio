"""LD-122 live gate — the Sheets MERGE/UNMERGE + TAB write round-trip (the Sheets rich/structural-write spec § F1-S4).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` +
network). Run it — together with every other family in one ring::

    pytest -m live_write

The live proof that the LD-122 merge/unmerge + tab writes round-trip **through the gated
apply engine** on a self-provisioned disposable, verified by the **merge leg** (LD-116's v3
``merges`` diff) and the tab-query identity read:

* **MERGE** ``A5:C5`` (MERGE_ALL) — the dry-run previews the **anchor-value loss** (B5/C5
  values LOST), the write applies, and the merge leg confirms EXACTLY the ``A5:C5`` region
  appeared in the live ``merges`` array;
* a value write into a merge-**covered** cell (B5) **REFUSES** ``MERGED_CELL_TARGET`` (D4) —
  merge-aware, reading the live merges;
* **UNMERGE** ``A5:C5`` — the merge leg confirms the region vanished;
* **tab ADD** — the reply's new ``sheetId`` is captured;
* **tab COPY** of a merged source — the copy duplicates the source's merges (content
  fidelity), new ``sheetId`` captured;
* **tab DELETE** of the added tab — the removed tab's identity is carried in the apply-log
  (D5, destructive-safe).

Writes use the WRITE app only (``LARK_WRITE_APP_*``); every target is a self-provisioned
disposable — never the scratch sheet, never the zoo, never a real document (D7); the whole
disposable is deleted in ``finally`` and the zero-orphan close-out is a hard gate.
"""
import tempfile
from pathlib import Path

import pytest

import canary_support
import sheets_write_harness as H
from sheets_fidelity_diff import assert_merge_change
from larkdocio.sheets.write_apply import (
    AddTab,
    CopyTab,
    DeleteTab,
    MergeCells,
    Refusal,
    UnmergeCells,
    ValueWriteRequest,
    apply,
    dry_run,
)
from larkdocio.sheets.write_client import SheetsWriteClient

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

DOMAIN = "larksuite.com"


def test_sheets_merge_and_tab_write_gate_round_trip(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    gateway = H.SheetsLifecycleGateway.from_write_credentials(DOMAIN)
    writer = SheetsWriteClient.from_write_credentials(DOMAIN)

    tmpdir = tempfile.mkdtemp(prefix="ld122-sheets-merge-tab-gate-")
    ledger = H.Ledger(Path(tmpdir) / "run_ledger.json")

    ev = {}
    with H.disposable(gateway, ledger, writer=writer) as d:
        ev["token"] = d.token
        sid = d.first_sheet_id
        ev["sheet_id"] = sid
        assert d.token, "create yielded no spreadsheet_token"

        # Populate A5:C5 with an anchor + two covered-to-be values.
        d.put_values(f"{sid}!A5:C5", [["keep", "lose-b", "lose-c"]])
        assert d.read_values(f"{sid}!A5:A5") == [["keep"]], "populate did not round-trip"

        # 1) MERGE A5:C5 — the dry-run previews the anchor-value loss; the write applies.
        mplan = dry_run([MergeCells(f"{sid}!A5:C5")], writer, d.token)
        preview = mplan.entries[0].after
        ev["lost"] = {c["ref"]: c["value"] for c in preview["lost_values"]}
        assert preview["anchor"]["ref"] == "A5"
        merged = apply(mplan, writer).entries[0]
        assert merged.is_applied, f"merge did not apply: {merged.to_dict()!r}"
        s = merged.structural
        # the merge leg: EXACTLY the A5:C5 region (0-idx 4,4,0,2) appeared, none removed.
        assert_merge_change(s["merges_before"], s["merges_after"], added=[(4, 4, 0, 2)], removed=[])
        ev["merge_added"] = s["merges_added"]

        # 2) a value write into a COVERED cell (B5) refuses (D4), reading the live merges.
        live_merges = (writer.read_sheet_geometry(d.token, sid) or {}).get("merges") or []
        refused = dry_run([ValueWriteRequest.for_a1(f"{sid}!B5", [["nope"]])],
                          writer, d.token, merges=live_merges).entries[0]
        assert not refused.is_resolved and refused.refusal.reason == Refusal.MERGED_CELL_TARGET
        ev["covered_write_refused"] = True

        # 3) UNMERGE A5:C5 — the merge leg confirms the region vanished.
        un = apply(dry_run([UnmergeCells(f"{sid}!A5:C5")], writer, d.token), writer).entries[0]
        assert un.is_applied, f"unmerge did not apply: {un.to_dict()!r}"
        su = un.structural
        assert_merge_change(su["merges_before"], su["merges_after"], added=[], removed=[(4, 4, 0, 2)])

        # 4) tab ADD — capture the new sheetId.
        add = apply(dry_run([AddTab("LD122-added", index=1)], writer, d.token), writer).entries[0]
        assert add.is_applied and add.structural["new_sheet_id"], f"add-tab failed: {add.to_dict()!r}"
        added_sid = add.structural["new_sheet_id"]
        ev["added_sheet_id"] = added_sid

        # 5) tab COPY of a merged source — re-merge A5:C5 first, then copy; the copy
        # duplicates the source's merges (content fidelity).
        apply(dry_run([MergeCells(f"{sid}!A5:C5")], writer, d.token), writer)
        cp = apply(dry_run([CopyTab(sid, "LD122-copy")], writer, d.token), writer).entries[0]
        assert cp.is_applied and cp.structural["new_sheet_id"], f"copy-tab failed: {cp.to_dict()!r}"
        ev["copied_sheet_id"] = cp.structural["new_sheet_id"]
        ev["copied_merges"] = cp.structural["copied_merges"]
        assert (4, 4, 0, 2) in {(m["start_row_index"], m["end_row_index"],
                                 m["start_column_index"], m["end_column_index"])
                                for m in (cp.structural["copied_merges"] or [])}, \
            "copy did not duplicate the source's A5:C5 merge"

        # 6) tab DELETE of the added tab — the removed identity is carried (D5).
        de = apply(dry_run([DeleteTab(added_sid)], writer, d.token), writer).entries[0]
        assert de.is_applied, f"delete-tab failed: {de.to_dict()!r}"
        ident = de.structural["removed_identity"]
        assert ident and ident["sheet_id"] == added_sid and ident["title"] == "LD122-added", \
            f"removed identity not carried: {ident!r}"
        ev["removed_identity_title"] = ident["title"]
    # delete-in-finally removed the whole disposable (all tabs with it).

    report = H.close_out(gateway, ledger)
    report.raise_if_orphans()
    assert report.all_clean, f"close-out found orphans: {report.orphans!r}"
    ev["orphans"] = len(report.orphans)

    with capsys.disabled():
        print(
            "\n[live_write:sheets-merge-tab-gate] "
            f"token={ev.get('token')} sheet_id={ev.get('sheet_id')} "
            f"merge(lost={ev.get('lost')}, added={ev.get('merge_added')}) "
            f"covered_write_refused={ev.get('covered_write_refused')} "
            f"add_sid={ev.get('added_sheet_id')} copy_sid={ev.get('copied_sheet_id')} "
            f"copied_merges={ev.get('copied_merges')} "
            f"deleted_tab={ev.get('removed_identity_title')} "
            f"orphans={ev.get('orphans')}"
        )
