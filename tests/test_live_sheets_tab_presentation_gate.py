"""LD-187 live gate — tab REORDER / RETITLE / HIDE-SHOW on a self-provisioned MULTI-TAB
disposable, each verified by the family's own v3 tab-query leg.

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it — together with every other family in one ring::

    pytest -m live_write

The live proof that the three ``updateSheet`` presentation fields round-trip **through the
gated apply engine**, and — the reason this arm earns its cost — that the four claims the
offline suite can only assert are true against the real API:

* **REORDER lands where asked** — ``index`` is a target position, the tabs it passes close the
  gap, and the apply-log's own ``observed`` (read back inside ``apply`` by the verification
  leg) agrees with an independent read;
* **the two silent hazards refuse and write NOTHING** — a position past the last tab (which
  Lark itself *accepts* and clamps) and a duplicate title, both proven inert by the live
  ``revision`` not moving;
* **RETITLE keeps the ``sheet_id``** — the plan's join-breakage note claims it; the live tab
  query confirms the id is the same one after the rename;
* **A HIDDEN TAB IS STILL READABLE** — the single assertion the whole hide disclosure rests on,
  made here against the real API: the tab's values are read back **while it is hidden** and are
  byte-identical to what they were before;
* **hiding the LAST visible tab is refused by us** on the live state Lark answers ``95201
  server error`` for — and the refusal costs no write;
* hide → show is **idempotent**, and the tab's values are byte-identical across the whole
  sequence (presentation is not content: it must change no cell).

Writes use the WRITE app only (``LARK_WRITE_APP_*``); every target is a **self-provisioned
disposable** — never the scratch sheet, never the canary, never a real document; the whole
disposable is deleted in ``finally`` and the zero-orphan close-out is a hard gate.
"""
import json
import tempfile
from pathlib import Path

import pytest

import canary_support
import sheets_write_harness as H
from log_reading_apply import reading_the_log
from larkdocio.sheets.plan import Refusal
from larkdocio.sheets.write_apply import (
    TAB_VERIFICATION_LEG,
    AddTab,
    ReorderTab,
    RetitleTab,
    SetTabVisibility,
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


def _tabs(writer, token):
    """The live tab list, read INDEPENDENTLY of the apply-log's own record."""
    return {t["sheet_id"]: t for t in writer.query_tabs(token)}


def _order(writer, token):
    return [(t["index"], t["sheet_id"]) for t in writer.query_tabs(token)]


def test_sheets_tab_presentation_write_gate_round_trip(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    gateway = H.SheetsLifecycleGateway.from_write_credentials(DOMAIN)
    writer = SheetsWriteClient.from_write_credentials(DOMAIN)

    tmpdir = tempfile.mkdtemp(prefix="ld187-sheets-tab-presentation-gate-")
    ledger = H.Ledger(Path(tmpdir) / "run_ledger.json")

    evidence = {}
    with H.disposable(gateway, ledger, writer=writer) as d:
        evidence["token"] = d.token
        assert d.token, "create yielded no spreadsheet_token"
        first = d.first_sheet_id

        # A marked grid on the tab under test, so "a presentation write moved data" would be
        # unmistakable — and so the hidden tab has something to still-be-readable.
        grid = [["A1", "B1"], ["A2", "B2"], ["A3", "B3"]]
        d.put_values(f"{first}!A1:B3", grid)
        values_before = d.read_values(f"{first}!A1:B3")
        assert values_before == grid, "grid populate did not round-trip"

        # A MULTI-TAB disposable, built through the SHIPPED gated add (never a raw call).
        add = apply(dry_run([AddTab("LD187-Beta"), AddTab("LD187-Gamma")], writer, d.token),
                    writer)
        assert [e.to_dict()["outcome"] for e in add.entries] == ["applied", "applied"], (
            [e.to_dict() for e in add.entries])
        live = _tabs(writer, d.token)
        assert len(live) == 3, f"expected a 3-tab disposable, got {sorted(live)}"
        target = live[first]
        evidence["sheet_id"] = first
        evidence["baseline_order"] = _order(writer, d.token)
        evidence["baseline_title"] = target["title"]
        assert target["hidden"] is False, (
            f"a fresh disposable's tab is already hidden: {target!r}")

        # 1) REORDER — move the values tab to the FRONT and read it back.
        plan = dry_run([ReorderTab(first, 0)], writer, d.token)
        assert len(plan.resolved) == 1, f"the reorder refused at dry-run: {plan.refusals!r}"
        log = apply(plan, writer)
        assert log.entries[0].is_applied, log.entries[0].to_dict()
        assert log.entries[0].structural["verified_by"] == TAB_VERIFICATION_LEG
        evidence["log_observed_reorder"] = log.entries[0].structural["observed"]
        assert log.entries[0].structural["observed"]["index"] == 0

        order_after = _order(writer, d.token)
        evidence["order_after_reorder"] = order_after
        assert order_after[0][1] == first, f"the reorder did not land first: {order_after!r}"
        assert [i for (i, _sid) in order_after] == [0, 1, 2], (
            f"the tabs a reorder passed did not close the gap: {order_after!r}")

        # 2) THE NO-OP — asked for the position it already holds: accepted, disclosed, and the
        # live revision does not even move (the probed fact this library pins).
        revision_before_noop = writer.read_revision(d.token)
        noop = dry_run([ReorderTab(first, 0)], writer, d.token)
        (note,) = noop.entries[0].preview_notes
        assert note["kind"] == "tab-presentation-no-op", note
        apply(noop, writer)
        evidence["noop_revision_unmoved"] = (
            writer.read_revision(d.token) == revision_before_noop)
        assert evidence["noop_revision_unmoved"], (
            "a no-op reorder moved the live revision — the disclosure's claim is wrong")

        # 3) THE SILENT HAZARD — a position past the last tab. Lark ACCEPTS and clamps; we
        # refuse, and the refusal must cost no write.
        revision_before = writer.read_revision(d.token)
        over = dry_run([ReorderTab(first, len(live))], writer, d.token)
        assert over.entries[0].refusal.reason == Refusal.TAB_INDEX_OUT_OF_RANGE, (
            over.entries[0].to_dict())
        over_log = apply(over, writer)
        assert not over_log.entries[0].is_applied
        assert writer.read_revision(d.token) == revision_before, (
            "a refused out-of-range reorder moved the revision — it wrote something")

        # 4) RETITLE — the id stands still, and a duplicate is refused before any write.
        retitle = dry_run([RetitleTab(first, "LD187-Renamed")], writer, d.token)
        (join_note,) = retitle.entries[0].preview_notes
        assert join_note["kind"] == "retitle-breaks-title-joins", join_note
        assert join_note["old_title"] == evidence["baseline_title"]
        assert join_note["new_title"] == "LD187-Renamed"
        retitle_log = apply(retitle, writer)
        assert retitle_log.entries[0].structural["observed"]["title"] == "LD187-Renamed"
        after_retitle = _tabs(writer, d.token)
        evidence["sheet_id_survived_retitle"] = (
            first in after_retitle and after_retitle[first]["title"] == "LD187-Renamed")
        assert evidence["sheet_id_survived_retitle"], (
            "the retitle changed the sheet_id — the join note's claim is wrong")

        revision_before = writer.read_revision(d.token)
        dup = dry_run([RetitleTab(first, "LD187-Beta")], writer, d.token)
        assert dup.entries[0].refusal.reason == Refusal.DUPLICATE_TAB_TITLE, (
            dup.entries[0].to_dict())
        apply(dup, writer)
        assert writer.read_revision(d.token) == revision_before, (
            "a refused duplicate-title retitle moved the revision — it wrote something")

        # 5) HIDE — and THE claim the disclosure rests on: the data is still readable.
        hide = dry_run([SetTabVisibility.hide(first)], writer, d.token)
        (hide_note,) = hide.entries[0].preview_notes
        assert hide_note["kind"] == "hidden-tab-fidelity", hide_note
        assert hide_note["already"] is False
        hide_log = apply(hide, writer)
        assert hide_log.entries[0].structural["observed"]["hidden"] is True
        evidence["log_observed_hide"] = hide_log.entries[0].structural["observed"]
        assert _tabs(writer, d.token)[first]["hidden"] is True, "the hide did not land"

        values_while_hidden = d.read_values(f"{first}!A1:B3")
        evidence["readable_while_hidden"] = values_while_hidden == values_before
        assert evidence["readable_while_hidden"], (
            f"a HIDDEN tab's values did not read back — the hide disclosure claims they do: "
            f"{values_while_hidden!r}")

        # hiding an already-hidden tab: accepted, disclosed as already-hidden
        (again_note,) = dry_run([SetTabVisibility.hide(first)], writer,
                                d.token).entries[0].preview_notes
        assert again_note["already"] is True, again_note

        # 6) THE LAST VISIBLE TAB — hide the other two, then prove OUR refusal fires on the
        # live state Lark answers `95201 server error` for, writing nothing.
        others = [sid for sid in live if sid != first]
        apply(dry_run([SetTabVisibility.hide(others[0])], writer, d.token), writer)
        revision_before = writer.read_revision(d.token)
        last = dry_run([SetTabVisibility.hide(others[1])], writer, d.token)
        assert last.entries[0].refusal.reason == Refusal.LAST_VISIBLE_TAB, (
            last.entries[0].to_dict())
        apply(last, writer)
        assert writer.read_revision(d.token) == revision_before, (
            "a refused last-visible-tab hide moved the revision — it wrote something")
        evidence["last_visible_refused"] = True
        apply(dry_run([SetTabVisibility.show(others[0])], writer, d.token), writer)

        # 7) SHOW — back to visible, idempotently, and the values byte-identical throughout.
        show = apply(dry_run([SetTabVisibility.show(first)], writer, d.token), writer)
        assert show.entries[0].structural["observed"]["hidden"] is False
        apply(dry_run([SetTabVisibility.show(first)], writer, d.token), writer)  # idempotent
        final = _tabs(writer, d.token)
        evidence["hidden_after_show"] = {sid: t["hidden"] for sid, t in final.items()}
        assert all(t["hidden"] is False for t in final.values()), evidence["hidden_after_show"]

        values_after = d.read_values(f"{first}!A1:B3")
        evidence["values_byte_identical"] = values_after == values_before
        assert values_after == values_before, (
            "a presentation sequence changed cell values — it must change none")
    # 8) delete-in-finally fired on with-exit (the whole disposable is removed).

    report = H.close_out(gateway, ledger)
    report.raise_if_orphans()
    assert report.all_clean, f"close-out found orphans: {report.orphans!r}"

    with capsys.disabled():
        print(
            "\n[LD-187 tab-presentation gate] "
            f"token={evidence['token']} sheet_id={evidence['sheet_id']} "
            f"baseline_order={evidence.get('baseline_order')} "
            f"order_after_reorder={evidence.get('order_after_reorder')} "
            f"log_observed_reorder={evidence.get('log_observed_reorder')} "
            f"noop_revision_unmoved={evidence.get('noop_revision_unmoved')} "
            f"sheet_id_survived_retitle={evidence.get('sheet_id_survived_retitle')} "
            f"log_observed_hide={evidence.get('log_observed_hide')} "
            f"READABLE_WHILE_HIDDEN={evidence.get('readable_while_hidden')} "
            f"last_visible_refused={evidence.get('last_visible_refused')} "
            f"hidden_after_show={evidence.get('hidden_after_show')} "
            f"values_byte_identical={evidence.get('values_byte_identical')} "
            f"orphans={report.orphans!r}\n"
            f"{json.dumps(evidence, default=str)}"
        )
