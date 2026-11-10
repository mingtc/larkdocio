"""LD-121 live gate — the Sheets STRUCTURAL dimension write round-trip (the Sheets rich/structural-write spec § F1-S3).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` +
network). Run it — together with every other family in one ring::

    pytest -m live_write

The live proof that the LD-121 structural dimension writes round-trip **through the gated
apply engine** on a self-provisioned disposable, and that **the load-bearing index-convention
asymmetry produces the correct surgical shift live**:

* **INSERT** 1 row before 1-indexed row 2 (native **0-idx half-open ``[1, 2)``**, via
  :class:`~larkdocio.sheets.write_apply.InsertRowsAt`) — asserts the content shift is surgical
  (row 1 unchanged; the old row-2 content shifted to row 3), the mandatory geometry re-read
  fired, and records the observed row-count delta;
* **DELETE** row 2 (native **1-idx inclusive ``[2, 2]``**, via
  :class:`~larkdocio.sheets.write_apply.DeleteRows`) — restores the grid (old row-2 content
  back at row 2), asserts the reply's ``delCount`` is trusted and re-read;
* **INSERT a COLUMN** before 1-indexed column 2 (LD-461) — the leg that proves the *printed
  diagnostics* are the authority: the landing column is derived from the plan's own
  ``position`` / ``position_convention`` pair (never a hand-typed letter), read back, and the
  column is deleted again to restore the grid;
* the **``values_append INSERT_ROWS``** structural variant (D8, via
  :class:`~larkdocio.sheets.write_apply.AppendRowsWithValues`) and the dimension **append**
  (via :class:`~larkdocio.sheets.write_apply.AppendDimension`, ``addCount`` trusted) — applied
  through the gated engine.

The observed geometry delta (whether Lark's declared ``grid_properties.row_count`` shifts by
the span, or the content shifts within a fixed grid) is **characterized** (printed), not
hard-asserted — the authoritative shift proof is the content surgical-ness + the trusted reply
count. Writes use the WRITE app only (``LARK_WRITE_APP_*``); every target is a self-provisioned
disposable — never the scratch sheet, never the zoo, never a real document (D7); the whole
disposable is deleted in ``finally`` and the zero-orphan close-out is a hard gate.
"""
import json
import tempfile
from pathlib import Path

import pytest

import canary_support
import sheets_write_harness as H
from larkdocio.sheets.write_apply import (
    AppendDimension,
    AppendRowsWithValues,
    DeleteCols,
    DeleteRows,
    InsertColsAt,
    InsertRowsAt,
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


def _col_letter(displayed_position):
    """The A1 letter of a **1-based displayed** column position — the reading the plan's
    `position` / `position_convention` pair asserts, spelled out so the live assertion is
    derived from the diagnostics rather than from a letter typed by hand (LD-461)."""
    letters = ""
    n = displayed_position
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


def test_sheets_structural_dimension_write_gate_round_trip(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    gateway = H.SheetsLifecycleGateway.from_write_credentials(DOMAIN)
    writer = SheetsWriteClient.from_write_credentials(DOMAIN)

    tmpdir = tempfile.mkdtemp(prefix="ld121-sheets-structural-gate-")
    ledger = H.Ledger(Path(tmpdir) / "run_ledger.json")

    evidence = {}
    with H.disposable(gateway, ledger, writer=writer) as d:
        evidence["token"] = d.token
        evidence["sheet_id"] = d.first_sheet_id
        assert d.token, "create yielded no spreadsheet_token"
        sid = d.first_sheet_id

        # Populate a marked 4x3 grid — each cell holds its own address, so a shift is
        # unambiguously observable.
        grid = [["A1", "B1", "C1"], ["A2", "B2", "C2"], ["A3", "B3", "C3"], ["A4", "B4", "C4"]]
        d.put_values(f"{sid}!A1:C4", grid)
        assert d.read_values(f"{sid}!A2:A2") == [["A2"]], "grid populate did not round-trip"
        geo0 = writer.read_sheet_geometry(d.token, sid)
        evidence["row_count_baseline"] = (geo0 or {}).get("row_count")

        # 1) INSERT 1 row BEFORE 1-indexed row 2 — native 0-idx half-open [1,2), gated.
        ins = apply(dry_run([InsertRowsAt(sid, before_row=2, count=1)], writer, d.token), writer).entries[0]
        assert ins.is_applied, f"insert did not apply: {ins.to_dict()!r}"
        assert ins.structural["start_index"] == 1 and ins.structural["end_index"] == 2
        assert ins.structural["convention"] == "0-index-half-open"
        assert ins.structural["geometry_after"] is not None, "mandatory geometry re-read did not fire"
        # SURGICAL: row 1 unchanged; the old row-2 content shifted DOWN to row 3.
        assert d.read_values(f"{sid}!A1:A1") == [["A1"]], "insert disturbed row 1"
        assert d.read_values(f"{sid}!A3:A3") == [["A2"]], "old row 2 did not shift to row 3"
        evidence["insert_observed_delta"] = ins.structural["observed_delta"]
        evidence["insert_shift_verified"] = ins.structural["shift_verified"]

        # 2) DELETE row 2 — native 1-idx inclusive [2,2]; delCount trusted + re-read. Restores.
        de = apply(dry_run([DeleteRows(sid, first=2, last=2)], writer, d.token), writer).entries[0]
        assert de.is_applied, f"delete did not apply: {de.to_dict()!r}"
        assert de.structural["start_index"] == 2 and de.structural["end_index"] == 2
        assert de.structural["convention"] == "1-index-inclusive"
        assert de.structural["reply_count"] == 1, f"delCount not trusted: {de.structural!r}"
        # SURGICAL restore: the old row-2 content is back at row 2 (net-zero round-trip).
        assert d.read_values(f"{sid}!A2:A2") == [["A2"]], "delete did not restore the grid"
        assert d.read_values(f"{sid}!A1:A1") == [["A1"]]
        geo1 = writer.read_sheet_geometry(d.token, sid)
        evidence["row_count_after_roundtrip"] = (geo1 or {}).get("row_count")
        evidence["delete_observed_delta"] = de.structural["observed_delta"]

        # 2b) LD-461 — the COLUMN insert lands where the PRINTED DIAGNOSTICS say it does.
        # Nothing here is hard-coded: the target column letter is derived from the plan's own
        # `position` + `position_convention`, and the wire span from `start_index`. This is the
        # move that shifted live data when the diagnostics only printed the WIRE convention.
        before_col = 2
        ins_col = apply(dry_run([InsertColsAt(sid, before_col=before_col, count=1)],
                                writer, d.token), writer).entries[0]
        assert ins_col.is_applied, f"column insert did not apply: {ins_col.to_dict()!r}"
        sd = ins_col.structural
        assert sd["position_convention"] == "1-index-displayed", sd
        assert sd["position"] == before_col and sd["start_index"] == before_col - 1, sd
        landed_at = _col_letter(sd["position"])                    # the displayed column the
        shifted_to = _col_letter(sd["position"] + sd["expected_count"])   # blank now occupies
        assert d.read_values(f"{sid}!A1:A1") == [["A1"]], "column insert disturbed column A"
        assert d.read_values(f"{sid}!{shifted_to}1:{shifted_to}1") == [["B1"]], (
            f"the diagnostics say the blank column lands at displayed column {landed_at} "
            f"(1-based) / wire index {sd['start_index']}, so the old column B content should "
            f"now be at {shifted_to} — it is not"
        )
        assert d.read_values(f"{sid}!{landed_at}1:{landed_at}1") in ([], [[""]], [[None]]), (
            f"displayed column {landed_at} should be the newly inserted blank"
        )
        evidence["insert_col_position"] = sd["position"]
        evidence["insert_col_wire_start"] = sd["start_index"]
        evidence["insert_col_landed_at"] = landed_at
        evidence["insert_col_semantic"] = sd["semantic"]

        # restore: delete the blank column again (1-idx inclusive) so the grid is as it was.
        dc = apply(dry_run([DeleteCols(sid, first=before_col, last=before_col)],
                           writer, d.token), writer).entries[0]
        assert dc.is_applied, f"column restore did not apply: {dc.to_dict()!r}"
        assert d.read_values(f"{sid}!B1:B1") == [["B1"]], "column delete did not restore B"

        # 3) values_append INSERT_ROWS (D8) — the structural row-inserting append, gated.
        av = apply(dry_run([AppendRowsWithValues(f"{sid}!A1:C1", [["X", "Y", "Z"]])], writer, d.token), writer).entries[0]
        assert av.is_applied, f"values_append INSERT_ROWS did not apply: {av.to_dict()!r}"
        assert av.structural["op"] == "append-values"
        evidence["append_values_observed_delta"] = av.structural["observed_delta"]

        # 4) append dimension (blank rows at the end) — addCount trusted, gated.
        ad = apply(dry_run([AppendDimension(sid, "ROWS", 2)], writer, d.token), writer).entries[0]
        assert ad.is_applied, f"append dimension did not apply: {ad.to_dict()!r}"
        evidence["append_dim_reply_count"] = ad.structural["reply_count"]
        evidence["append_dim_observed_delta"] = ad.structural["observed_delta"]
    # 5) delete-in-finally fired on with-exit (the whole disposable is removed).

    report = H.close_out(gateway, ledger)
    report.raise_if_orphans()
    assert report.all_clean, f"close-out found orphans: {report.orphans!r}"
    evidence["orphans"] = len(report.orphans)

    with capsys.disabled():
        print(
            "\n[live_write:sheets-structural-gate] "
            f"token={evidence.get('token')} sheet_id={evidence.get('sheet_id')} "
            f"row_count baseline={evidence.get('row_count_baseline')} "
            f"after_roundtrip={evidence.get('row_count_after_roundtrip')} "
            f"insert(observed_delta={evidence.get('insert_observed_delta')}, "
            f"shift_verified={evidence.get('insert_shift_verified')}) "
            f"delete(observed_delta={evidence.get('delete_observed_delta')}) "
            f"insert_col(position={evidence.get('insert_col_position')}, "
            f"wire_start={evidence.get('insert_col_wire_start')}, "
            f"landed_at={evidence.get('insert_col_landed_at')}) "
            f"append_values(observed_delta={evidence.get('append_values_observed_delta')}) "
            f"append_dim(reply_count={evidence.get('append_dim_reply_count')}, "
            f"observed_delta={evidence.get('append_dim_observed_delta')}) "
            f"orphans={evidence.get('orphans')}"
        )
