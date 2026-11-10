"""⛳ THE ARC'S FINAL GATE — the rich + structural Sheets write round-trip ring under the
FULL two-leg differ (LD-124/D5/D2).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it — together with every other family in one ring::

    pytest -m live_write

This is the **binding live proof that closes the Sheets write beast.** Where LD-119..122
each proved ONE write family live and LD-118 proved the style-leg in isolation, THIS gate
runs **all four rich/structural write kinds** on a **single self-provisioned disposable**,
EACH verified by the **full fidelity differ** (the Sheets read-fidelity spec): the live **values leg** (used-range
surgical diff), the export-based **style/format leg** (``--verify-style`` AUTO-ON — D9 —
because the ring touches style/merge/structure), and the live **merge leg** (v3 ``merges``
diff). It adds the two cross-cutting proofs the per-family gates could not:

* **the style/format EXPORT leg run against a rich write** (LD-114 export reader → the
  LD-116 ``assert_style_surgical`` — a stray fill/bold on a guard-neighbour cell reddens);
* **the destructive-safe removed payload asserted from a LIVE delete** (D5, AC3): a row
  delete's apply-log carries the FULL removed payload (``entry.structural["removed"]``),
  proven complete + reconstructable via ``assert_removed_payload_complete``, then restored.

The ring, on a spreadsheet it **provisions and destroys itself** — never the scratch sheet,
never the read canary, never the zoo, never a real document (AC6, D7):

1. self-provision + populate a baseline; export the baseline workbook (the style-leg
   reference);
2. **RICH** (hyperlink / styled-runs / @mention ``notify:false`` / multi-select) → values
   leg surgical + typed-model round-trip + **style export leg surgical** + merge leg
   identical → restore byte-identical;
3. **DROPDOWN rule** (list rule + a value through it) → value round-trips → restore;
4. **STRUCTURAL delete** of a content row → **destructive-safe removed payload** complete +
   reconstructable (AC3) + values-leg surgical shift → restore byte-identical (insert +
   rewrite from the payload);
5. **MERGE / UNMERGE + TAB** → merge leg exact add, covered-cell write refuses (D4), merge
   leg exact remove; tab add/copy/delete carries the removed identity (D5);
6. delete-in-``finally`` (teardown on success AND failure) + the **zero-orphan close-out**
   hard gate (AC4).

**Credentials (AC6, D1).** Every surface — the lifecycle gateway, the value writer, the
export reader — is built ``from_write_credentials`` (``LARK_WRITE_APP_*``, never
read/legacy). The WRITE app owns what it creates, so it exports the disposable it made too.
Writes ride the shared ≤3/s throttle; the export poll is gentle (≥0.5s between polls).
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
from larkdocio.sheets.cell_model import Hyperlink, TextRun, UserMention, parse_segments
from larkdocio.sheets.export_reader import SheetsExportReader
from larkdocio.sheets.rich_encode import normalize_multi_select
from larkdocio.sheets.write_apply import (
    AddTab,
    CopyTab,
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
from larkdocio.sheets.write_client import SheetsWriteClient

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

DOMAIN = "larksuite.com"

# A per-run nonce so the authored baseline is unique and every diff assertion is exact.
TOK = f"{int(time.time())}-{os.getpid()}"

LINK = "https://www.larksuite.com/ld124"
LINK_TEXT = f"Lark LD124 {TOK}"
MULTI_LABELS = ["Red", "Green"]
SINGLE_CONDS = ["Alpha", "Bravo", "Charlie"]

# The rich region: A1:A4 are the four rich targets, A5 + columns B/C are guard neighbours
# whose VALUES and cell-level STYLE must stay untouched (the surgical control for both the
# values leg and the style/format export leg).
RICH_ROWS = [
    [f"hyperlink-slot {TOK}", f"g-B1 {TOK}", f"g-C1 {TOK}"],
    [f"styled-slot {TOK}", f"g-B2 {TOK}", f"g-C2 {TOK}"],
    [f"mention-slot {TOK}", f"g-B3 {TOK}", f"g-C3 {TOK}"],
    [f"multi-slot {TOK}", f"g-B4 {TOK}", f"g-C4 {TOK}"],
    [f"guard-A5 {TOK}", f"g-B5 {TOK}", f"g-C5 {TOK}"],
]
RICH_USED_BODY = "A1:C5"
RICH_TARGETS_BODY = "A1:A4"     # the four rich cells (the surgical target set)
RICH_TARGET_REFS = ["A1", "A2", "A3", "A4"]   # the style-leg allowed set

# The dropdown region (isolated in column D so a rule/value write cannot touch the rich set).
DROPDOWN_BASE = [[f"dropdown-base {TOK}", f"g-E1 {TOK}"]]
DROPDOWN_USED_BODY = "D1:E1"

# The merge region (row 10, isolated). Merging A10:C10 LOSES B10/C10 (characterized, D4) —
# the merge round-trip's restore is the merge GEOMETRY (unmerge), not the covered values.
MERGE_ROW = [["keep", "lose-b", "lose-c"]]
MERGE_USED_BODY = "A10:C10"
MERGE_REGION_0IDX = (9, 9, 0, 2)   # A10:C10 as v3 0-idx end-inclusive (row 10 → 9)

# The structural / destructive-safe region (rows 20-21, isolated so a row shift disturbs no
# other region). Deleting the CONTENT row 21 must carry a reconstructable removed payload.
STRUCT_ROW20 = ["R20a", "R20b", "R20c"]
STRUCT_ROW21 = ["R21a", "R21b", "R21c"]
STRUCT_USED_BODY = "A20:C21"


def _owner_open_id(request, token):
    """The disposable's owner ``open_id`` from the v3 spreadsheet metadata — the
    least-surprise @mention target (written ``notify:false`` so nobody is pinged, D6)."""
    _status, resp = request("GET", f"/open-apis/sheets/v3/spreadsheets/{token}", None, None)
    return (((resp or {}).get("data") or {}).get("spreadsheet") or {}).get("owner_id")


def test_sheets_final_gate_all_families_round_trip(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    gateway = H.SheetsLifecycleGateway.from_write_credentials(DOMAIN)
    writer = SheetsWriteClient.from_write_credentials(DOMAIN)
    reader = SheetsExportReader.from_write_credentials(DOMAIN)
    request = H.build_throttled_write_request(DOMAIN)

    tmpdir = tempfile.mkdtemp(prefix="ld124-sheets-final-gate-")
    ledger = H.Ledger(Path(tmpdir) / "run_ledger.json")

    ev = {}
    with H.disposable(gateway, ledger, writer=writer) as d:
        ev["token"] = d.token
        ev["sheet_id"] = d.first_sheet_id
        assert d.token, "create yielded no spreadsheet_token"
        assert H.is_disposable_title(d.title), "disposable was not titled with the grep-able DISPOSABLE prefix (D7)"
        sid = d.first_sheet_id

        rich_used = f"{sid}!{RICH_USED_BODY}"
        dd_used = f"{sid}!{DROPDOWN_USED_BODY}"
        merge_used = f"{sid}!{MERGE_USED_BODY}"
        struct_used = f"{sid}!{STRUCT_USED_BODY}"
        a1, a2, a3, a4 = (f"{sid}!A{r}" for r in (1, 2, 3, 4))

        # -------------------------------------------------------------------- #
        # 1) BASELINE — populate every region; export the baseline workbook      #
        #    (the style/format leg reference); read each region's values.        #
        # -------------------------------------------------------------------- #
        d.put_values(rich_used, RICH_ROWS)
        d.put_values(dd_used, DROPDOWN_BASE)
        d.put_values(merge_used, MERGE_ROW)
        d.put_values(struct_used, [STRUCT_ROW20, STRUCT_ROW21])

        base_rich = d.read_values(rich_used)
        assert base_rich == d.read_values(rich_used), "sheets read is non-deterministic"
        base_dd = d.read_values(dd_used)
        base_struct = d.read_values(struct_used)

        baseline_wb = reader.read_workbook(d.token)   # the style-leg reference (AC2, D9)

        # -------------------------------------------------------------------- #
        # 2) RICH — the four encoded types, verified by the FULL differ.         #
        # -------------------------------------------------------------------- #
        owner_open_id = _owner_open_id(request, d.token)
        assert owner_open_id, "could not read the disposable owner_id (the @mention target)"
        ev["mention_open_id"] = owner_open_id

        merges_before_rich = (writer.read_sheet_geometry(d.token, sid) or {}).get("merges") or []
        rich_plan = dry_run([
            RichCellWriteRequest.hyperlink(a1, LINK, text=LINK_TEXT),
            RichCellWriteRequest.styled_runs(a2, [
                {"text": "bold ", "bold": True},
                {"text": "then italic", "italic": True, "fore_color": "#FF0000"},
            ]),
            RichCellWriteRequest.mention(a3, owner_open_id),   # notify:false default (D6)
            RichCellWriteRequest.multi_select(a4, MULTI_LABELS),
        ], writer, d.token)
        assert len(rich_plan.resolved) == 4, f"a rich write was refused at dry-run: {rich_plan.refusals!r}"
        rich_log = apply(rich_plan, writer)
        assert all(e.is_applied for e in rich_log.entries), (
            f"a rich write did not apply: {[e.to_dict() for e in rich_log.entries]!r}"
        )

        # VALUES leg — only A1:A4 changed; every guard (A5, B/C) byte-identical.
        after_rich = d.read_values(rich_used)
        changed = D.assert_surgical(base_rich, after_rich, RICH_TARGETS_BODY)
        assert changed == {(0, 0), (1, 0), (2, 0), (3, 0)}, (
            f"the changed cells were not exactly A1:A4: {sorted(changed)!r}"
        )

        # Typed-model round-trip (the LD-115 parser) — each rich type survives.
        (hyper,) = parse_segments(after_rich[0][0])
        assert isinstance(hyper, Hyperlink) and hyper.link == LINK and hyper.text == LINK_TEXT
        runs = parse_segments(after_rich[1][0])
        assert [r.text for r in runs] == ["bold ", "then italic"], f"styled-run texts drifted: {runs!r}"
        assert all(isinstance(r, TextRun) for r in runs)
        assert runs[0].style.bold is True and runs[1].style.italic is True
        (mention_seg,) = parse_segments(after_rich[2][0])
        assert isinstance(mention_seg, UserMention), f"A3 did not land as a mention: {after_rich[2][0]!r}"
        read_multi = after_rich[3][0]
        assert normalize_multi_select(read_multi) == normalize_multi_select(
            {"type": "multipleValue", "values": MULTI_LABELS}
        ) == tuple(MULTI_LABELS), f"multi-select did not round-trip: {read_multi!r}"

        # STYLE/FORMAT export leg (AUTO-ON, D9) — export post-write + assert surgical: EVERY
        # cell-level style change lies within the rich targets; a stray fill/bold on a guard
        # neighbour (A5 / B* / C*) reddens.
        post_rich_wb = reader.read_workbook(d.token)
        D.assert_style_surgical(baseline_wb, post_rich_wb, RICH_TARGET_REFS)
        ev["style_leg_surgical"] = True

        # MERGE leg — a rich write touches no merges.
        merges_after_rich = (writer.read_sheet_geometry(d.token, sid) or {}).get("merges") or []
        D.assert_merges_identical(merges_before_rich, merges_after_rich)

        # RESTORE the plain baseline → re-diff byte-identical (AC4).
        d.put_values(rich_used, RICH_ROWS)
        D.assert_identical(base_rich, d.read_values(rich_used))
        ev["rich_restored"] = True

        # -------------------------------------------------------------------- #
        # 3) DROPDOWN RULE — a list rule + a value through it (LD-120).           #
        # -------------------------------------------------------------------- #
        single_cell = f"{sid}!D1"
        dd_log = apply(
            dry_run([DropdownRuleWriteRequest.list_rule(single_cell, SINGLE_CONDS)], writer, d.token),
            writer,
        )
        assert dd_log.entries[0].is_applied, f"dropdown rule did not apply: {dd_log.entries[0].to_dict()!r}"
        assert dd_log.entries[0].write_kind == "data-validation"
        # a value THROUGH the rule round-trips (values leg).
        d.put_values(f"{sid}!D1:D1", [["Bravo"]])
        assert d.read_values(f"{sid}!D1:D1") == [["Bravo"]], "dropdown value did not round-trip"
        # RESTORE the base value → re-diff byte-identical (the guard E1 never moved).
        d.put_values(dd_used, DROPDOWN_BASE)
        D.assert_identical(base_dd, d.read_values(dd_used))
        ev["dropdown_restored"] = True

        # -------------------------------------------------------------------- #
        # 4) STRUCTURAL DELETE — destructive-safe removed payload (AC3, D5).      #
        # -------------------------------------------------------------------- #
        de = apply(dry_run([DeleteRows(sid, first=21, last=21)], writer, d.token), writer).entries[0]
        assert de.is_applied, f"delete did not apply: {de.to_dict()!r}"
        assert de.structural["convention"] == "1-index-inclusive"
        assert de.structural["reply_count"] == 1, f"delCount not trusted: {de.structural!r}"

        # THE destructive-safe proof: the apply-log carries the FULL removed payload,
        # complete + reconstructable (the removed row-21 content), asserted from the
        # round-trip (AC3). A payload regression (a dropped field) reddens loudly.
        removed = de.structural["removed"]
        D.assert_removed_payload_complete(removed)
        assert [row[:3] for row in removed["values"]] == [STRUCT_ROW21], (
            f"the removed payload does not reconstruct the deleted row-21 content: {removed['values']!r}"
        )
        ev["removed_a1_range"] = removed["a1_range"]

        # VALUES leg — row 20 untouched; row 21 content is gone (the surgical delete shift).
        assert d.read_values(f"{sid}!A20:C20") == [STRUCT_ROW20], "delete disturbed row 20"
        assert d.read_values(f"{sid}!A21:C21") != [STRUCT_ROW21], "row-21 content was not deleted"

        # RESTORE byte-identical — insert a blank row at 21 + rewrite the reconstructed
        # content (from the removed payload) → re-diff (AC4).
        ins = apply(dry_run([InsertRowsAt(sid, before_row=21, count=1)], writer, d.token), writer).entries[0]
        assert ins.is_applied and ins.structural["convention"] == "0-index-half-open"
        d.put_values(f"{sid}!A21:C21", [[c for c in removed["values"][0][:3]]])
        D.assert_identical(base_struct, d.read_values(struct_used))
        ev["structural_restored"] = True

        # -------------------------------------------------------------------- #
        # 5) MERGE / UNMERGE + TAB (LD-122) — the merge leg + destructive-safe.   #
        # -------------------------------------------------------------------- #
        # MERGE A10:C10 — the merge leg confirms EXACTLY the region appeared.
        merged = apply(dry_run([MergeCells(merge_used)], writer, d.token), writer).entries[0]
        assert merged.is_applied, f"merge did not apply: {merged.to_dict()!r}"
        sm = merged.structural
        D.assert_merge_change(sm["merges_before"], sm["merges_after"], added=[MERGE_REGION_0IDX], removed=[])

        # a value write into a COVERED cell (B10) refuses MERGED_CELL_TARGET (D4).
        live_merges = (writer.read_sheet_geometry(d.token, sid) or {}).get("merges") or []
        refused = dry_run([ValueWriteRequest.for_a1(f"{sid}!B10", [["nope"]])],
                          writer, d.token, merges=live_merges).entries[0]
        assert not refused.is_resolved and refused.refusal.reason == Refusal.MERGED_CELL_TARGET
        ev["covered_write_refused"] = True

        # UNMERGE A10:C10 — the merge leg confirms the region vanished (geometry restored).
        un = apply(dry_run([UnmergeCells(merge_used)], writer, d.token), writer).entries[0]
        assert un.is_applied, f"unmerge did not apply: {un.to_dict()!r}"
        su = un.structural
        D.assert_merge_change(su["merges_before"], su["merges_after"], added=[], removed=[MERGE_REGION_0IDX])

        # TAB add/copy/delete — the deleted tab's identity is carried destructive-safe (D5).
        add = apply(dry_run([AddTab("LD124-added", index=1)], writer, d.token), writer).entries[0]
        assert add.is_applied and add.structural["new_sheet_id"], f"add-tab failed: {add.to_dict()!r}"
        added_sid = add.structural["new_sheet_id"]
        cp = apply(dry_run([CopyTab(sid, "LD124-copy")], writer, d.token), writer).entries[0]
        assert cp.is_applied and cp.structural["new_sheet_id"], f"copy-tab failed: {cp.to_dict()!r}"
        de_tab = apply(dry_run([DeleteTab(added_sid)], writer, d.token), writer).entries[0]
        assert de_tab.is_applied, f"delete-tab failed: {de_tab.to_dict()!r}"
        ident = de_tab.structural["removed_identity"]
        assert ident and ident["sheet_id"] == added_sid and ident["title"] == "LD124-added", (
            f"removed tab identity not carried: {ident!r}"
        )
        ev["deleted_tab"] = ident["title"]
    # 6) delete-in-finally fired on with-exit (the whole disposable + all its tabs removed).

    report = H.close_out(gateway, ledger)
    report.raise_if_orphans()
    assert report.all_clean, f"close-out found orphans: {report.orphans!r}"
    assert report.ledger_count >= 1
    for rec in report.clean:
        assert rec["recheck_code"] == H.NOT_FOUND_CODE, (
            f"a gone token re-queried to {rec['recheck_code']}, expected "
            f"{H.NOT_FOUND_CODE} (deleted/not-found): {rec!r}"
        )
    ev["orphans"] = len(report.orphans)
    ev["ledger_count"] = report.ledger_count

    with capsys.disabled():
        print(
            "\n[live_write:sheets-FINAL-gate] "
            f"token={ev.get('token')} sheet_id={ev.get('sheet_id')} "
            f"mention_open_id={ev.get('mention_open_id')} "
            f"style_leg_surgical={ev.get('style_leg_surgical')} "
            f"rich_restored={ev.get('rich_restored')} "
            f"dropdown_restored={ev.get('dropdown_restored')} "
            f"removed_a1_range={ev.get('removed_a1_range')!r} "
            f"structural_restored={ev.get('structural_restored')} "
            f"covered_write_refused={ev.get('covered_write_refused')} "
            f"deleted_tab={ev.get('deleted_tab')} "
            f"ledger_count={ev.get('ledger_count')} orphans={ev.get('orphans')}"
        )
