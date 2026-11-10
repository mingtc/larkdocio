"""LD-148 live gate — the DISPOSITION invariant observed against the real API (AC7).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network)::

    pytest -m live_write

The dogfood round-2 **T27** Blocker was found live and must be proven fixed live. Two arms, on
a **self-provisioned disposable** this gate creates and destroys itself — never the canary,
never the zoo, never the maintainer's scratch surfaces (D7):

**(a) PLAN-TIME REFUSAL.** A batch with a nonexistent mention ``open_id`` **mid-list** is
refused at ``dry_run`` — ``unknown-mention``, naming the id — with the plan's
``mention_validation`` reading ``active``. The batch's other entries stay resolved, and the
refused one **never reaches the transport**.

**(b) THE MID-BATCH DISPOSITION, FORCED PAST PLANNING.** The same bad id is then pushed past
the plan-time check (the previewer is handed a client seam **without** ``validate_user_ids``,
which is exactly the "validation unavailable" path a consumer without the contact scope is on)
and applied against the **live** API — so the real ``90204 id not found`` comes back from Lark,
mid-batch, on the exact shape that used to crash. Observed live:

* the entries **before** the bad mention **landed**;
* the bad entry is a typed **``api-error``** refusal in the log (carrying Lark's own
  ``90204``), not a raised exception;
* the entries **after** it **still applied** — the maintainer-blessed per-entry doctrine;
* **the sheet's final state matches the apply-log exactly**, cell for cell: every entry the
  log calls ``applied`` changed, and the refused entry's cell is byte-identical to its
  baseline. That equality is the whole point of the invariant.

Teardown deletes in a ``finally`` and the zero-orphan close-out re-queries every ledger token.
"""
import json
import os
import tempfile
import time
from pathlib import Path

import pytest

import canary_support
import sheets_write_harness as H
from sheets_values_diff import assert_surgical
from log_reading_apply import reading_the_log
from larkdocio.sheets.write_apply import (
    Refusal,
    RichCellWriteRequest,
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
TOK = f"{int(time.time())}-{os.getpid()}"

#: A structurally valid but nonexistent ``open_id`` — the T27 trigger. Never a real user.
BAD_OPEN_ID = "ou_0000000000000000000000000000dead"

# A 6×1 baseline column. A1/A2 land before the bad mention (A3); A4/A5 land after it; A6 is a
# guard neighbour that no entry targets and must stay byte-identical throughout.
BASELINE_ROWS = [[f"slot-{r} {TOK}"] for r in range(1, 7)]
USED_RANGE_BODY = "A1:A6"


class _NoMentionCheck:
    """The writer, with :meth:`validate_user_ids` hidden — the "validation unavailable" seam.

    This is how arm (b) forces the bad id **past planning** without stubbing the transport:
    it is the very shape a consumer whose WRITE app lacks the contact scope is on, so the arm
    observes the real, reachable failure path rather than an artificial one. Every other call
    (including every write) goes straight to the real client.
    """

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        if name == "validate_user_ids":
            raise AttributeError(name)
        return getattr(self._inner, name)


def test_sheets_disposition_gate_no_exception_escapes_apply(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    gateway = H.SheetsLifecycleGateway.from_write_credentials(DOMAIN)
    writer = SheetsWriteClient.from_write_credentials(DOMAIN)

    tmpdir = tempfile.mkdtemp(prefix="ld148-sheets-disposition-gate-")
    ledger = H.Ledger(Path(tmpdir) / "run_ledger.json")

    evidence = {}
    with H.disposable(gateway, ledger, writer=writer) as d:
        evidence["token"] = d.token
        evidence["sheet_id"] = d.first_sheet_id
        assert d.token, "create yielded no spreadsheet_token"

        sid = d.first_sheet_id
        used_range = f"{sid}!{USED_RANGE_BODY}"
        a1, a2, a3, a4, a5 = (f"{sid}!A{r}" for r in (1, 2, 3, 4, 5))

        d.put_values(used_range, BASELINE_ROWS)
        baseline = d.read_values(used_range)
        assert baseline == d.read_values(used_range), "sheets read is non-deterministic"

        def _batch():
            """The T27 shape: 2 valid entries, the bad mention, then 2 more valid entries."""
            return [
                ValueWriteRequest.for_a1(a1, [[f"before-1 {TOK}"]]),
                ValueWriteRequest.for_a1(a2, [[f"before-2 {TOK}"]]),
                RichCellWriteRequest.mention(a3, BAD_OPEN_ID),
                ValueWriteRequest.for_a1(a4, [[f"after-1 {TOK}"]]),
                ValueWriteRequest.for_a1(a5, [[f"after-2 {TOK}"]]),
            ]

        # ---- ARM (a): the bad mention is refused at PLAN TIME. -------------------- #
        plan_a = dry_run(_batch(), writer, d.token)
        evidence["arm_a_mention_validation"] = plan_a.mention_validation
        evidence["arm_a_invalid_ids"] = plan_a.mention_validation_ids["invalid"]
        assert plan_a.mention_validation == "active", (
            "the plan-time mention check did not run — plan says "
            f"{plan_a.mention_validation!r}: {plan_a.mention_validation_detail}"
        )
        refused = plan_a.entries[2]
        assert not refused.is_resolved, "the nonexistent open_id was not refused at dry-run"
        assert refused.refusal.reason == Refusal.UNKNOWN_MENTION
        assert BAD_OPEN_ID in refused.refusal.detail
        assert plan_a.mention_validation_ids["invalid"] == [BAD_OPEN_ID]
        assert len(plan_a.resolved) == 4, "only the bad mention should be refused"
        # …and the refusal is carried into the log with NO write for it.
        log_a = apply(plan_a, writer)
        assert log_a.entries[2].refusal.reason == Refusal.UNKNOWN_MENTION
        assert not log_a.halted, "a plan-time refusal must not halt the batch"
        assert [e.is_applied for e in log_a.entries] == [True, True, False, True, True]
        evidence["arm_a_outcomes"] = [e.outcome for e in log_a.entries]

        after_a = d.read_values(used_range)
        changed_a = assert_surgical(baseline, after_a, "A1:A5")
        assert changed_a == {(0, 0), (1, 0), (3, 0), (4, 0)}, (
            f"arm (a): the changed cells were not exactly A1,A2,A4,A5: {sorted(changed_a)}"
        )
        assert after_a[2] == baseline[2], "arm (a): the refused mention cell must be untouched"
        assert after_a[5] == baseline[5], "arm (a): the guard neighbour A6 must be untouched"

        # ---- ARM (b): forced PAST planning → the live 90204 mid-batch. ------------ #
        d.put_values(used_range, BASELINE_ROWS)          # re-baseline for a clean diff
        baseline_b = d.read_values(used_range)

        unchecked = _NoMentionCheck(writer)
        plan_b = dry_run(_batch(), unchecked, d.token)
        evidence["arm_b_mention_validation"] = plan_b.mention_validation
        assert plan_b.mention_validation == "unavailable", (
            "arm (b) needs the bad id to reach apply; the plan still validated it"
        )
        assert "UNVERIFIED" in plan_b.mention_validation_detail, (
            "an unavailable check must be DISCLOSED with the WHY"
        )
        assert len(plan_b.resolved) == 5, "all five entries should reach apply in arm (b)"

        # THE MOMENT T27 CRASHED. apply() must return an ApplyLog.
        log_b = apply(plan_b, writer)          # ← pre-LD-148: raised LarkAPIError(90204)
        evidence["arm_b_outcomes"] = [e.outcome for e in log_b.entries]
        evidence["arm_b_bad_entry"] = log_b.entries[2].to_dict()

        assert len(log_b.entries) == 5, "the apply-log must be 1:1 with the plan"
        bad = log_b.entries[2]
        assert bad.outcome == "refused", f"expected an entry-scoped refusal, got {bad.outcome}"
        assert bad.refusal.reason == Refusal.API_ERROR, (
            f"the live API error was not typed api-error: {bad.to_dict()!r}"
        )
        assert "90204" in bad.refusal.detail, (
            f"the refusal detail does not carry Lark's own code: {bad.refusal.detail!r}"
        )
        assert not log_b.halted, "an entry-scoped error must NOT halt the batch"
        assert [e.is_applied for e in log_b.entries] == [True, True, False, True, True], (
            "the per-entry doctrine was not honored: "
            f"{[e.outcome for e in log_b.entries]!r}"
        )

        # THE INVARIANT'S PAYOFF: the sheet's final state matches the log EXACTLY.
        after_b = d.read_values(used_range)
        changed_b = assert_surgical(baseline_b, after_b, "A1:A5")
        assert changed_b == {(0, 0), (1, 0), (3, 0), (4, 0)}, (
            f"arm (b): the changed cells were not exactly A1,A2,A4,A5: {sorted(changed_b)}"
        )
        for row_index, entry in enumerate(log_b.entries):
            live_cell = after_b[row_index][0]
            if entry.is_applied:
                assert live_cell == entry.after[0][0], (
                    f"row {row_index + 1}: the log says applied {entry.after[0][0]!r} but the "
                    f"sheet holds {live_cell!r}"
                )
            else:
                assert live_cell == baseline_b[row_index][0], (
                    f"row {row_index + 1}: the log says {entry.outcome} but the sheet changed "
                    f"to {live_cell!r}"
                )
        assert after_b[5] == baseline_b[5], "arm (b): the guard neighbour A6 must be untouched"
        evidence["log_matches_sheet"] = True
    # delete-in-finally fired on with-exit.

    report = H.close_out(gateway, ledger)
    report.raise_if_orphans()
    assert report.all_clean, f"close-out found orphans: {report.orphans!r}"
    evidence["orphans"] = len(report.orphans)

    with capsys.disabled():
        print(
            "\n[live_write:sheets-disposition-gate] "
            f"token={evidence.get('token')} "
            f"sheet_id={evidence.get('sheet_id')} "
            f"arm_a_mention_validation={evidence.get('arm_a_mention_validation')} "
            f"arm_a_invalid_ids={json.dumps(evidence.get('arm_a_invalid_ids'))} "
            f"arm_a_outcomes={json.dumps(evidence.get('arm_a_outcomes'))} "
            f"arm_b_mention_validation={evidence.get('arm_b_mention_validation')} "
            f"arm_b_outcomes={json.dumps(evidence.get('arm_b_outcomes'))} "
            f"arm_b_refusal_reason={(evidence.get('arm_b_bad_entry') or {}).get('refusal', {}).get('reason')} "
            f"log_matches_sheet={evidence.get('log_matches_sheet')} "
            f"orphans={evidence.get('orphans')}"
        )
