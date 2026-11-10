"""THE SHEETS VALUE-WRITE GATE — the Sheets value-write round-trip (LD-113).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` +
network). Run it explicitly — together with every other family in one ring::

    pytest -m live_write

This is the **binding live proof** that a Sheets value write is **surgical** end-to-end.
It joins the same ``live_write`` ring as the docx W0..W3 gates and the LD-112 Sheets
self-provision harness, so a single ``pytest -m live_write`` run exercises **all five
families together** (AC4). Where the LD-112 harness proved the disposable *lifecycle*
(create → populate → mutate → verify → delete → zero-orphan close-out) with the raw
value legs, THIS gate drives the **LD-111 plan-gated apply engine** end-to-end —
``ValueWriteRequest`` → ``dry_run`` Plan → ``apply`` — against a live disposable, and
proves the write is surgical via a **used-range values-leg diff** (D6, the cheap live
leg; the style/format leg is the Sheets read-fidelity spec).

The ring, against a spreadsheet it **provisions and destroys itself** — never the scratch
sheet, never the zoo, never the read canary, never a real document (AC5, D7):

1. **self-provisions** a disposable spreadsheet (the LD-112 ``disposable()`` context
   manager, delete-in-``finally`` + ledger), and **populates a 3×3 baseline** used range
   (distinctive nonce tokens so the diff is exact) via the harness value leg;
2. **reads the baseline used-range value matrix twice** — asserting same-run byte-identity
   (the determinism control that makes any post-edit diff attributable to the edit);
3. drives the **LD-111 apply engine**: a ``ValueWriteRequest`` targeting **one cell (A2)**
   → ``dry_run`` (asserting it resolves to exactly that target, zero refusals) →
   ``apply`` (asserting one ``applied`` log entry carrying the target + post-write
   ``revision``);
4. **re-reads and diffs** the used-range matrix — asserting via the LD-113 values-leg
   differ that **ONLY the A2 target changed** (every other cell byte-identical — the
   full-used-range matrix compare that catches an oversized write, D6), the new value is
   present, and the old value is gone;
5. **restores the baseline** through the *same gated engine* (a second plan writing the
   original A2 value back) and **re-diffs to byte-identity** (``assert_identical`` — the
   restore-verify, AC3);
6. **deletes** the disposable in the harness ``finally`` (AC3), then runs the
   **zero-orphan close-out** re-querying every ledger token (AC4).

**Credentials (AC5).** Writes use the WRITE app only (``SheetsWriteClient.from_write_credentials``
/ ``SheetsLifecycleGateway.from_write_credentials`` — ``LARK_WRITE_APP_*``, never read/legacy).
Because the WRITE app **owns what it creates**, its own credentials read the disposable back
too (the gated engine's compare-and-swap ``revision`` + before-snapshot reads, D1) — no
read-app collaborator step. Writes ride the shared ≤3/sec throttle.
"""
import json
import os
import tempfile
import time
from pathlib import Path

import pytest

import canary_support
import sheets_write_harness as H
from sheets_values_diff import assert_identical, assert_surgical
from larkdocio.sheets.write_apply import ValueWriteRequest, apply, dry_run
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
TARGET_BEFORE = f"LD113-TARGET-BEFORE {TOK}"
TARGET_AFTER = f"LD113-TARGET-AFTER {TOK}"

# The 3×3 baseline used range the gate authors — A2 (row 1, col 0) is the single write
# target; every other cell is a guard neighbour that must stay byte-identical.
BASELINE_ROWS = [
    [f"hdr-A {TOK}", f"hdr-B {TOK}", f"hdr-C {TOK}"],
    [TARGET_BEFORE, f"guard-B {TOK}", f"guard-C {TOK}"],
    [f"tail-A {TOK}", f"tail-B {TOK}", f"tail-C {TOK}"],
]
USED_RANGE_BODY = "A1:C3"      # the authored used range (matrix origin A1)
TARGET_A2 = "A2"              # the single-cell write target (row 1, col 0)


def test_sheets_value_write_gate_surgical_round_trip(capsys):
    # Load the repo .env (local runs) — a no-op in CI where creds are injected as
    # variables. Then skip LOUDLY if we cannot run.
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    gateway = H.SheetsLifecycleGateway.from_write_credentials(DOMAIN)
    writer = SheetsWriteClient.from_write_credentials(DOMAIN)

    tmpdir = tempfile.mkdtemp(prefix="ld113-sheets-write-gate-")
    ledger = H.Ledger(Path(tmpdir) / "run_ledger.json")

    evidence = {}
    with H.disposable(gateway, ledger, writer=writer) as d:
        evidence["token"] = d.token
        evidence["sheet_id"] = d.first_sheet_id
        assert d.token, "create yielded no spreadsheet_token"
        assert H.is_disposable_title(d.title), "disposable was not titled with the grep-able DISPOSABLE prefix"

        sid = d.first_sheet_id
        used_range = f"{sid}!{USED_RANGE_BODY}"
        target = f"{sid}!{TARGET_A2}"

        # 1) Populate the 3×3 baseline used range (harness value leg — not the gate).
        d.put_values(used_range, BASELINE_ROWS)

        # 2) Determinism control: two same-run reads of the unedited used range must be
        #    byte-identical (so any post-edit diff is attributable to the edit).
        baseline = d.read_values(used_range)
        baseline_2 = d.read_values(used_range)
        assert baseline == baseline_2, (
            f"sheets read is non-deterministic: two used-range reads differ\n"
            f"  a={baseline!r}\n  b={baseline_2!r}"
        )
        assert baseline[1][0] == TARGET_BEFORE, (
            f"baseline target cell A2 is not the authored value: {baseline!r}"
        )

        # 3) THE GATED ENGINE. One request targeting exactly A2 → dry_run → apply
        #    (the LD-111 plan-gated apply engine, not a raw put_values).
        req = ValueWriteRequest.for_a1(target, [[TARGET_AFTER]])
        plan = dry_run([req], writer, d.token)
        assert len(plan.resolved) == 1, (
            f"dry-run must resolve to exactly one target; got {plan!r}"
        )
        assert len(plan.refusals) == 0, f"dry-run refused the write: {plan.refusals!r}"
        planned = plan.resolved[0]
        assert planned.before == [[TARGET_BEFORE]], (
            f"plan.before did not capture the live A2 value: {planned.before!r}"
        )
        assert planned.after == [[TARGET_AFTER]], "plan.after is not the replacement value"

        log = apply(plan, writer)
        assert len(log.entries) == 1, f"apply-log is not 1:1 with the plan: {log!r}"
        applied = log.entries[0]
        assert applied.is_applied, f"the write was not applied: {applied.to_dict()!r}"
        assert applied.after == [[TARGET_AFTER]], "apply-log after is not the replacement"
        assert applied.revision is not None, (
            "apply-log lost the post-write revision (compare-and-swap anchor)"
        )

        # 4) Re-read + VALUES-LEG SURGICAL DIFF: ONLY the A2 target changed (every other
        #    cell of the used range byte-identical — the full-used-range matrix compare).
        after = d.read_values(used_range)
        changed = assert_surgical(baseline, after, TARGET_A2)
        assert changed == {(1, 0)}, f"the changed cell was not exactly A2: {changed!r}"
        assert after[1][0] == TARGET_AFTER, "A2 did not take the new value"
        assert TARGET_BEFORE not in [cell for row in after for cell in row], (
            "the old A2 value survived somewhere in the used range"
        )
        evidence["changed_cells"] = sorted(changed)
        evidence["post_write_revision"] = applied.revision

        # 5) RESTORE the baseline through the SAME gated engine, then re-diff to
        #    byte-identity (the restore-verify — AC3).
        restore = ValueWriteRequest.for_a1(target, [[TARGET_BEFORE]])
        restore_plan = dry_run([restore], writer, d.token)
        assert len(restore_plan.resolved) == 1, f"restore dry-run refused: {restore_plan!r}"
        restore_log = apply(restore_plan, writer)
        assert restore_log.entries[0].is_applied, "restore write was not applied"

        restored = d.read_values(used_range)
        assert_identical(baseline, restored)
        evidence["restored_byte_identical"] = True
    # 6) delete-in-finally already fired here (the with-block exited).

    # Zero-orphan close-out: re-query every ledger token, assert each is gone (AC4).
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
            "\n[live_write:sheets-value-gate] "
            f"token={evidence.get('token')} "
            f"sheet_id={evidence.get('sheet_id')} "
            f"changed_cells={json.dumps(evidence.get('changed_cells'))} "
            f"post_write_revision={evidence.get('post_write_revision')} "
            f"restored_byte_identical={evidence.get('restored_byte_identical')} "
            f"ledger_count={evidence.get('ledger_count')} "
            f"orphans={evidence.get('orphans')}"
        )
