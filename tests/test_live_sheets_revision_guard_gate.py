"""LD-132 — THE REVISION-GUARD LIVE ARM (the doctrine-clean investigation, `live_write`).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it with the rest of the ring::

    pytest -m live_write

**The question this answers.** The dogfood session found ``read_revision()`` returning ``0``
on a live, edited spreadsheet (F7): does a write on a revision-``0`` spreadsheet **bump** the
anchor (``0 → 1``, so the compare-and-swap works from the first write onward and only the
plan-time-``0`` semantics need disclosing), or does the anchor **stay 0** (a permanent no-op)?

**Disposables ONLY — no exceptions (the issue's amended § Investigation, AC7).** A fresh
self-provisioned disposable **starts at revision 0** (the LD-107 fact), so the whole question
is answerable on a spreadsheet this gate creates and destroys itself. It never writes to the
Maintainer dogfood sheet, never the standing canary scratch sheet, never the zoo, never any real
document — the only write target is the LD-112 harness's own disposable, deleted in
``finally`` and re-queried by the zero-orphan close-out. (The seat's earlier dogfood-sheet
write probe is **WITHDRAWN**; the UI-created / revision-0-despite-edits variant stays maintainer-parked
and is covered defensively by the injected-transport tests in
``tests/test_revision_guard_never_silent.py``.)

**The five-step sequence** (all on the one disposable):

1. **provision** a fresh disposable → confirm the raw ``metainfo.properties.revision`` is
   ``0`` (the pre-first-write reality);
2. **plan PRE-first-write** → the plan must visibly carry ``revision_guard == "unavailable"``
   with the WHY, and the entry must still declare its tier-2 ``value_precondition``;
3. **write** one minimal value (through the harness value leg) → re-read the anchor and
   record the transition (``0 → 1`` expected) — **the investigation's answer**;
4. **apply the stale plan** → cached ``0`` vs live ``1`` must refuse ``STALE_SHEET`` with
   **zero writes** (the self-healing proof: "unavailable" never means "compare disabled"),
   then **plan again** on the nonzero anchor → the guard **self-activates** (``"active"``),
   and that fresh plan applies surgically (only the target cell changes);
5. **delete** the disposable (harness ``finally``) + zero-orphan close-out.
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
    REVISION_GUARD_ACTIVE,
    REVISION_GUARD_UNAVAILABLE,
    VALUE_PRECONDITION_ENFORCED,
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

# The write app's tenant region — NOT a document URL (this gate never addresses a
# pre-existing spreadsheet; it self-provisions its own disposable).
DOMAIN = "larksuite.com"

TOK = f"{int(time.time())}-{os.getpid()}"
BASELINE_ROWS = [[f"guard-A {TOK}", f"guard-B {TOK}", f"guard-C {TOK}"]]
USED_RANGE_BODY = "A1:C1"
TARGET_CELL = "B1"                     # the single write target (row 0, col 1)
STALE_ATTEMPT = f"LD132-STALE-ATTEMPT {TOK}"    # must NEVER reach the sheet
FRESH_WRITE = f"LD132-FRESH-WRITE {TOK}"        # the write the re-planned batch lands


def test_revision_guard_live_arm_on_a_self_provisioned_disposable(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    gateway = H.SheetsLifecycleGateway.from_write_credentials(DOMAIN)
    writer = SheetsWriteClient.from_write_credentials(DOMAIN)

    tmpdir = tempfile.mkdtemp(prefix="ld132-revision-guard-gate-")
    ledger = H.Ledger(Path(tmpdir) / "run_ledger.json")

    ev = {}
    with H.disposable(gateway, ledger, writer=writer) as d:
        ev["token"] = d.token
        assert H.is_disposable_title(d.title), "the write target is not a harness-minted disposable (D7 / AC7)"

        sid = d.first_sheet_id
        used_range = f"{sid}!{USED_RANGE_BODY}"
        target = f"{sid}!{TARGET_CELL}"

        # 1) A FRESH disposable starts at revision 0 (the LD-107 fact this arm depends on).
        rev_fresh = writer.read_revision(d.token)
        ev["revision_fresh"] = rev_fresh
        assert rev_fresh == 0, (
            f"a freshly provisioned disposable did not report revision 0 (got {rev_fresh!r}) "
            "— the pre-first-write premise of this arm changed; re-open LD-132's investigation"
        )

        # 2) PLAN PRE-FIRST-WRITE — on the genuinely-zero anchor, so the plan must visibly
        #    carry the unavailable semantics (AC1) while still naming the tier-2 guard (AC2).
        stale_plan = dry_run([ValueWriteRequest.for_a1(target, [[STALE_ATTEMPT]])],
                             writer, d.token)
        ev["plan_revision_pre_write"] = stale_plan.revision
        ev["revision_guard_pre_write"] = stale_plan.revision_guard
        ev["revision_guard_detail_pre_write"] = stale_plan.revision_guard_detail
        assert stale_plan.revision == 0
        assert stale_plan.revision_guard == REVISION_GUARD_UNAVAILABLE, (
            f"a plan on the pre-first-write anchor did not disclose the guard: {stale_plan!r}"
        )
        assert stale_plan.entries[0].value_precondition == VALUE_PRECONDITION_ENFORCED

        # 3) WRITE one minimal value (the harness value leg, not the plan) and observe the
        #    anchor transition — THE INVESTIGATION'S ANSWER.
        d.put_values(used_range, BASELINE_ROWS)
        rev_after_first_write = writer.read_revision(d.token)
        ev["revision_after_first_write"] = rev_after_first_write
        assert rev_after_first_write != 0, (
            "a write on a revision-0 disposable left the anchor at 0 — the anchor is a "
            "PERMANENT sentinel on this tenant; the marker + value precondition are then the "
            "permanent contract (LD-132 AC3, the 'stays 0' branch)"
        )
        ev["bumped_on_first_write"] = True
        baseline = d.read_values(used_range)

        # 4) SELF-HEALING — the plan cached at 0 is NOT trusted as "equal forever": the
        #    advance to a nonzero anchor still refuses STALE_SHEET with zero writes.
        #    "unavailable" never meant "compare disabled".
        stale_log = apply(stale_plan, writer)
        stale_entry = stale_log.entries[0]
        ev["stale_outcome"] = stale_entry.outcome
        ev["stale_reason"] = stale_entry.refusal.reason if stale_entry.refusal else None
        ev["stale_detail"] = stale_entry.refusal.detail if stale_entry.refusal else None
        assert stale_entry.outcome == "stale", f"expected a stale skip: {stale_entry.to_dict()!r}"
        assert stale_entry.refusal.reason == Refusal.STALE_SHEET
        assert stale_entry.revision_guard == REVISION_GUARD_UNAVAILABLE, (
            "the apply-log lost the plan-time revision_guard status"
        )
        mid = d.read_values(used_range)
        assert STALE_ATTEMPT not in [c for row in mid for c in row], (
            "a STALE_SHEET refusal still wrote to the sheet"
        )
        assert mid == baseline, "the refused batch changed the sheet"

        # 5) THE GUARD SELF-ACTIVATES — re-plan on the now-nonzero anchor: the marker flips to
        #    "active" with no consumer action, and the write lands surgically (only B1).
        replan = dry_run([ValueWriteRequest.for_a1(target, [[FRESH_WRITE]])], writer, d.token)
        assert replan.revision_guard == REVISION_GUARD_ACTIVE
        assert replan.entries[0].value_precondition == VALUE_PRECONDITION_ENFORCED
        log = apply(replan, writer)
        applied = log.entries[0]
        assert applied.is_applied, f"the fresh write did not apply: {applied.to_dict()!r}"
        assert applied.revision_guard == REVISION_GUARD_ACTIVE
        ev["applied_revision"] = applied.revision

        after = d.read_values(used_range)
        changed = assert_surgical(mid, after, TARGET_CELL)
        assert changed == {(0, 1)}, f"the changed cell was not exactly B1: {changed!r}"
        ev["changed_cells"] = sorted(changed)
        ev["baseline_cols"] = len(baseline[0])
    # delete-in-finally fired on with-block exit.

    report = H.close_out(gateway, ledger)
    report.raise_if_orphans()
    assert report.all_clean, f"close-out found orphans: {report.orphans!r}"
    ev["ledger_count"] = report.ledger_count
    ev["orphans"] = len(report.orphans)

    with capsys.disabled():
        print(f"\n[live_write:ld132-revision-guard] {json.dumps(ev, sort_keys=True)}")


def test_revision_guard_unavailable_is_visible_pre_first_write(capsys):
    """The PRE-FIRST-WRITE half of the arm, on its OWN fresh disposable: the very first plan
    against a never-written spreadsheet must carry ``revision_guard == "unavailable"`` with a
    WHY — and its entry must still name the tier-2 value precondition that does hold. A second
    disposable keeps this assertion honest (once anything is written the anchor is nonzero, so
    the unavailable state exists only before the first write on an API-created sheet)."""
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    gateway = H.SheetsLifecycleGateway.from_write_credentials(DOMAIN)
    writer = SheetsWriteClient.from_write_credentials(DOMAIN)

    tmpdir = tempfile.mkdtemp(prefix="ld132-revision-guard-prewrite-")
    ledger = H.Ledger(Path(tmpdir) / "run_ledger.json")

    ev = {}
    with H.disposable(gateway, ledger, writer=writer) as d:
        ev["token"] = d.token
        sid = d.first_sheet_id
        target = f"{sid}!{TARGET_CELL}"

        raw = writer.read_revision(d.token)
        ev["revision_pre_first_write"] = raw
        assert raw == 0, f"a fresh disposable reported revision {raw!r}, expected 0"

        # ZERO writes so far → the plan is built on the genuinely-zero anchor.
        plan = dry_run([ValueWriteRequest.for_a1(target, [[f"LD132-first {TOK}"]])],
                       writer, d.token)
        ev["plan_revision"] = plan.revision
        ev["revision_guard"] = plan.revision_guard
        ev["revision_guard_detail"] = plan.revision_guard_detail
        assert plan.revision == 0
        assert plan.revision_guard == REVISION_GUARD_UNAVAILABLE, (
            f"a plan on a revision-0 sheet did not disclose the guard: {plan!r}"
        )
        assert "precondition" in plan.revision_guard_detail.lower()
        assert plan.revision_guard_tiers["tier1_revision_compare_and_swap"] == (
            REVISION_GUARD_UNAVAILABLE)
        (entry,) = plan.entries
        assert entry.revision_guard == REVISION_GUARD_UNAVAILABLE
        assert entry.value_precondition == VALUE_PRECONDITION_ENFORCED

        # The marker is a disclosure, not a refusal: the write still lands, and the apply-log
        # records the plan-time status it ran under.
        log = apply(plan, writer)
        applied = log.entries[0]
        assert applied.is_applied, f"the pre-first-write write was refused: {applied.to_dict()!r}"
        assert applied.revision_guard == REVISION_GUARD_UNAVAILABLE
        ev["applied_revision"] = applied.revision
        # And the anchor moved 0 → nonzero, so the NEXT plan self-activates (self-healing).
        ev["revision_after_first_write"] = writer.read_revision(d.token)
        self_healed = dry_run([ValueWriteRequest.for_a1(target, [[f"LD132-second {TOK}"]])],
                             writer, d.token)
        ev["revision_guard_after_first_write"] = self_healed.revision_guard
        assert self_healed.revision_guard == REVISION_GUARD_ACTIVE, (
            "the guard did not self-activate after the first write"
        )

    report = H.close_out(gateway, ledger)
    report.raise_if_orphans()
    ev["ledger_count"] = report.ledger_count
    ev["orphans"] = len(report.orphans)

    with capsys.disabled():
        print(f"\n[live_write:ld132-revision-guard-prewrite] {json.dumps(ev, sort_keys=True)}")
