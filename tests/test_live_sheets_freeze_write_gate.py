"""LD-186 live gate — the Sheets FREEZE-PANES write round-trip, verified by its own read leg.

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it — together with every other family in one ring::

    pytest -m live_write

The live proof that a freeze round-trips **through the gated apply engine** on a
self-provisioned disposable, and — the reason this arm matters more than most — that **the
read leg this issue shipped really sees it**. Freeze is the one op whose verification leg was
built in the same issue as the write, because before LD-186 the frozen counts were surfaced
nowhere at all: a freeze had nothing to be checked against. So this arm is the first place the
write and the read confront each other against the real API:

* **FREEZE** a header row + a label column in one gated batch → the frozen read reports
  ``frozen_rows=1, frozen_cols=1``, and the apply-log's own ``observed`` (read back inside
  ``apply`` by the verification leg) agrees with an independent read;
* **THE PATCH INVARIANT, live** — freezing *rows only* over that state must leave the frozen
  **column** standing. This is the single assertion a REPLACE misreading would fail, and it is
  the trap a consumer would otherwise hit by silently unfreezing an axis they never named;
* **THE REPLACEMENT DISCLOSURE** — the plan that changes an existing freeze names both the
  current counts and the target ones before the write;
* **THE BOUNDARY LARK'S OWN MESSAGE MISSTATES** — freezing **every** row (``rows ==
  row_count``) is accepted live, while ``row_count + 1`` refuses at plan time and writes
  nothing (proven by the live ``revision`` not moving);
* **UNFREEZE** → both axes read back ``0``, and the tab's **values are byte-identical** to
  before the whole sequence (a freeze is view state: it must change no cell);
* the READ-side graceful leg on the real tab: ``read_tabs_frozen`` resolves the state to
  ``active`` / ``none`` with real counts, never to ``unavailable``, when the read succeeds.

Writes use the WRITE app only (``LARK_WRITE_APP_*``); every target is a **self-provisioned
disposable** — never the scratch sheet, never the canary, never a real document; the whole
disposable is deleted in ``finally`` and the zero-orphan close-out is a hard gate.

**Cost note.** Unlike the dimension leg (an async whole-workbook export), this op's leg is a
single ``metainfo`` GET, which is why it runs inside ``apply`` rather than being deferred to
this ring.
"""
import json
import tempfile
from pathlib import Path

import pytest

import canary_support
import sheets_write_harness as H
from log_reading_apply import reading_the_log
from larkdocio.sheets.models import FROZEN_ACTIVE, FROZEN_NONE, SheetTab
from larkdocio.sheets.plan import Refusal
from larkdocio.sheets.write_apply import FREEZE_VERIFICATION_LEG, FreezePanes, apply, dry_run
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


def _frozen(writer, token, sheet_id):
    """``(frozen_rows, frozen_cols)`` read INDEPENDENTLY of the apply-log's own record."""
    record = writer.read_frozen_panes(token, sheet_id)
    assert isinstance(record, dict), f"the frozen read did not find tab {sheet_id!r}"
    return record["frozen_rows"], record["frozen_cols"]


def test_sheets_freeze_panes_write_gate_round_trip(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    gateway = H.SheetsLifecycleGateway.from_write_credentials(DOMAIN)
    writer = SheetsWriteClient.from_write_credentials(DOMAIN)

    tmpdir = tempfile.mkdtemp(prefix="ld186-sheets-freeze-gate-")
    ledger = H.Ledger(Path(tmpdir) / "run_ledger.json")

    evidence = {}
    with H.disposable(gateway, ledger, writer=writer) as d:
        evidence["token"] = d.token
        assert d.token, "create yielded no spreadsheet_token"
        sid = d.first_sheet_id
        evidence["sheet_id"] = sid

        # A marked grid, so "a freeze changed a cell" would be unmistakable.
        grid = [[f"A{r}", f"B{r}", f"C{r}"] for r in range(1, 6)]
        d.put_values(f"{sid}!A1:C5", grid)
        values_before = d.read_values(f"{sid}!A1:C5")
        assert values_before == grid, "grid populate did not round-trip"

        baseline = writer.read_frozen_panes(d.token, sid)
        evidence["baseline"] = {k: baseline[k] for k in
                               ("frozen_rows", "frozen_cols", "row_count", "column_count")}
        assert (baseline["frozen_rows"], baseline["frozen_cols"]) == (0, 0), (
            f"a fresh disposable already freezes something: {baseline!r}")

        # 1) FREEZE a header row + a label column — one gated batch, both axes.
        plan = dry_run([FreezePanes(sid, rows=1, cols=1)], writer, d.token)
        assert len(plan.resolved) == 1, f"the freeze refused at dry-run: {plan.refusals!r}"
        assert plan.entries[0].preview_notes == (), (
            "nothing is frozen yet, so there is no replacement to disclose")
        log = apply(plan, writer)
        assert log.entries[0].is_applied, log.entries[0].to_dict()
        assert log.entries[0].structural["verified_by"] == FREEZE_VERIFICATION_LEG
        evidence["log_observed"] = log.entries[0].structural["observed"]

        after_first = _frozen(writer, d.token, sid)
        evidence["after_freeze"] = after_first
        assert after_first == (1, 1), f"the freeze did not land: {after_first!r}"
        # the leg's own read-back (inside apply) agrees with this independent read
        assert log.entries[0].structural["observed"] == {"frozen_rows": 1, "frozen_cols": 1}

        # 2) THE PATCH INVARIANT, LIVE — rows only, over an existing frozen column.
        patch_plan = dry_run([FreezePanes(sid, rows=2)], writer, d.token)
        (note,) = patch_plan.entries[0].preview_notes
        assert note["kind"] == "freeze-replaces-freeze", note
        assert note["current"] == {"frozen_rows": 1, "frozen_cols": 1}, note
        assert note["target"] == {"frozen_rows": 2, "frozen_cols": 1}, note
        assert note["preserved_axes"] == ["frozen_cols"], note
        evidence["replacement_note"] = {k: note[k] for k in
                                        ("current", "target", "preserved_axes")}
        apply(patch_plan, writer)
        after_patch = _frozen(writer, d.token, sid)
        evidence["after_rows_only"] = after_patch
        assert after_patch == (2, 1), (
            f"a rows-only freeze did not PATCH — the frozen column was lost: {after_patch!r}")

        # 3) THE READ-side graceful leg, on the real tab.
        read_tab = SheetTab(sheet_id=sid, title=baseline.get("title"), index=0,
                            row_count=baseline["row_count"],
                            column_count=baseline["column_count"])
        (resolved,) = writer_read_tabs_frozen(writer, d.token, [read_tab])
        assert resolved.frozen_state == FROZEN_ACTIVE, resolved.frozen_state_detail
        assert (resolved.frozen_panes.rows, resolved.frozen_panes.cols) == (2, 1)
        evidence["read_state"] = resolved.frozen_state

        # 4) THE BOUNDARY — every row is legal, one more is not, and the refusal writes nothing.
        row_count = baseline["row_count"]
        all_rows = dry_run([FreezePanes(sid, rows=row_count)], writer, d.token)
        assert all_rows.entries[0].is_resolved, (
            f"freezing all {row_count} rows was refused, but the API accepts it: "
            f"{all_rows.entries[0].to_dict()}")
        revision_before = writer.read_revision(d.token)
        over = dry_run([FreezePanes(sid, rows=row_count + 1)], writer, d.token)
        assert over.entries[0].refusal.reason == Refusal.FROZEN_COUNT_OUT_OF_RANGE, (
            over.entries[0].to_dict())
        over_log = apply(over, writer)
        assert not over_log.entries[0].is_applied
        assert writer.read_revision(d.token) == revision_before, (
            "a refused over-count freeze moved the spreadsheet revision — it wrote something")
        evidence["row_count"] = row_count

        # 5) UNFREEZE both axes — and the values must be byte-identical throughout.
        unfroze = apply(dry_run([FreezePanes.unfreeze(sid)], writer, d.token), writer)
        assert unfroze.entries[0].is_applied, unfroze.entries[0].to_dict()
        after_unfreeze = _frozen(writer, d.token, sid)
        evidence["after_unfreeze"] = after_unfreeze
        assert after_unfreeze == (0, 0), f"the unfreeze did not clear: {after_unfreeze!r}"
        (cleared,) = writer_read_tabs_frozen(writer, d.token, [read_tab])
        assert cleared.frozen_state == FROZEN_NONE, cleared.frozen_state_detail

        values_after = d.read_values(f"{sid}!A1:C5")
        evidence["values_byte_identical"] = values_after == values_before
        assert values_after == values_before, (
            "a freeze/unfreeze sequence changed cell values — it is view state and must not")
    # 6) delete-in-finally fired on with-exit (the whole disposable is removed).

    report = H.close_out(gateway, ledger)
    report.raise_if_orphans()
    assert report.all_clean, f"close-out found orphans: {report.orphans!r}"

    with capsys.disabled():
        print(
            "\n[LD-186 freeze-panes gate] "
            f"token={evidence['token']} sheet_id={evidence['sheet_id']} "
            f"baseline={evidence.get('baseline')} "
            f"after_freeze={evidence.get('after_freeze')} "
            f"log_observed={evidence.get('log_observed')} "
            f"after_rows_only={evidence.get('after_rows_only')} (PATCH invariant) "
            f"read_state={evidence.get('read_state')} "
            f"row_count={evidence.get('row_count')} "
            f"after_unfreeze={evidence.get('after_unfreeze')} "
            f"values_byte_identical={evidence.get('values_byte_identical')} "
            f"orphans={report.orphans!r}\n"
            f"{json.dumps(evidence, default=str)}"
        )


def writer_read_tabs_frozen(writer, token, tabs):
    """The READ client's graceful frozen leg, driven with the WRITE app's credentials.

    The two clients hold different credentials by doctrine, and this ring is a WRITE-credential
    ring — so rather than constructing a read client here (which would need the READ pair and
    would prove nothing extra about the frozen leg), the shipped graceful method is bound to the
    write client, whose ``get_frozen_panes`` twin has the identical contract. What is under test
    is the composition — ``metainfo`` → four states → carried on the tab — not which app asked.
    """
    from larkdocio.sheets.client import SheetsReadClient

    class _Bound:
        def get_frozen_panes(self, spreadsheet_token):
            state = writer.read_frozen_panes(spreadsheet_token)
            from larkdocio.sheets.models import FrozenPanes

            return {sid: FrozenPanes(rows=rec["frozen_rows"], cols=rec["frozen_cols"],
                                     source=rec["source"])
                    for sid, rec in (state or {}).get("sheets", {}).items()}

    return SheetsReadClient.read_tabs_frozen(_Bound(), token, tabs)
