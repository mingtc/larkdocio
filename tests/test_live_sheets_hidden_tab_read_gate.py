"""LD-477 live gate — a READ-ONLY consumer determines that a tab is hidden.

``@pytest.mark.live_write``, deselected by default. Run it by NAME (never a bare ring sweep)::

    pytest tests/test_live_sheets_hidden_tab_read_gate.py -m live_write -s -n0

**The subject is the READ leg.** The write credentials appear here only to *provision the
situation* — a workbook with two tabs, one of them hidden — because there is no way to observe
a hidden tab without one existing. The claim under test is made by a client built from the
**READ** pair alone: ``SheetsReadClient.from_read_credentials(...).query_sheets(token)`` reports
``hidden=True`` for the tab that was hidden and ``hidden=False`` for the one that was not, with
**no second call** beyond the tab query the read already makes.

**What this gate does NOT prove**, stated so nobody reads it as proving it: on this tenant the
READ and WRITE credential pairs alias one app with identical secrets (PROJECT.md § "Credential
aliasing"), so a call succeeding "on the READ pair" is **not** evidence that the read path lacks
write scope. What it establishes is what it measures — the field is on the read route's own wire
and the read already pays for it.

**The hidden state is established by the write and CONFIRMED by the write side's own tab query**
before the read leg is asked, so a read reporting ``hidden=True`` cannot be read as an artifact
of the read leg agreeing with itself. The independent cross-route confirmation (the drive xlsx
export's ``state="hidden"``) is recorded in ``tests/captures/ld477-hidden-tab-probe/``; this gate is the
shipped-surface arm, not the premise probe.

**THE TARGET IS ONLY A WORKBOOK THIS GATE CREATED.** No environment variable naming a sheet is
read, no pre-existing spreadsheet is addressed, and the workbook is deleted in a ``finally``
with gone-ness proved by an independent re-query rather than by the delete's own ``code: 0``.
No media is uploaded, so this arm mints **no permanent residue**.

**Skips loudly, never silently** — and it needs *both* credential pairs to run: the write pair
to provision, the read pair because it is the subject.
"""
import time

import pytest

import canary_support
import sheets_write_harness as H
from larkdocio.errors import LarkAPIError
from larkdocio.sheets.client import SheetsReadClient
from larkdocio.sheets.requests import AddTab, SetTabVisibility
from larkdocio.sheets.write_apply import apply, dry_run
from larkdocio.sheets.write_client import SheetsWriteClient, spreadsheet_is_gone

pytestmark = pytest.mark.live_write
# The live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing the statement
# above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

DOMAIN = "larksuite.com"


def test_a_read_only_consumer_can_tell_a_hidden_tab_from_a_visible_one(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)
    if not canary_support.read_creds_available():
        pytest.skip(
            "READ creds unset — this gate's SUBJECT is the read leg, so it cannot run without "
            "LARK_READ_APP_ID / LARK_READ_APP_SECRET (or the legacy LARK_APP_* pair).")

    writer = SheetsWriteClient.from_write_credentials(DOMAIN)

    title = H.disposable_title(f"hidden-tab-read-{int(time.time())}")
    dest_folder = canary_support.require_disposables_folder()
    workbook = writer.create_spreadsheet(title, folder_token=dest_folder)
    token = workbook["spreadsheet_token"]
    assert token, f"create returned no spreadsheet_token: {workbook!r}"
    ev = {"spreadsheet_token": token}

    try:
        # A second tab, so that hiding one is legal at all (hiding the LAST VISIBLE tab
        # refuses at plan time) and so "hidden" and "visible" are both observable in one read.
        added = apply(dry_run([AddTab(title="visible-tab", index=1)], writer, token), writer)
        assert added.entries[0].is_applied, added.entries[0].to_dict()

        tabs = writer.query_tabs(token)
        ev["provisioned"] = [(t["index"], t["title"], t["hidden"]) for t in tabs]
        assert len(tabs) == 2, ev["provisioned"]
        hidden_id = tabs[0]["sheet_id"]
        visible_id = tabs[1]["sheet_id"]

        hide = apply(dry_run([SetTabVisibility.hide(hidden_id)], writer, token), writer)
        assert hide.entries[0].is_applied, hide.entries[0].to_dict()
        # The situation, confirmed on the WRITE side before the read leg is asked.
        ev["write_side_readback"] = {
            t["sheet_id"]: t["hidden"] for t in writer.query_tabs(token)}
        assert ev["write_side_readback"][hidden_id] is True, ev["write_side_readback"]

        # ---------------------------------------------------------------- #
        # THE SUBJECT: a client built from the READ pair, and nothing else.  #
        # ---------------------------------------------------------------- #
        reader = SheetsReadClient.from_read_credentials(DOMAIN)
        read_tabs = reader.query_sheets(token)
        ev["read_leg"] = [(t.index, t.title, t.hidden) for t in read_tabs]
        by_id = {t.sheet_id: t for t in read_tabs}

        assert by_id[hidden_id].hidden is True, (
            "the READ route did not report the hidden tab as hidden — the shipped sentence "
            f"that a read can now tell is FALSE and must move with the measurement: {ev!r}")
        assert by_id[visible_id].hidden is False, (
            "the READ route did not report the visible tab as explicitly visible — an absent "
            f"answer must read as None, and this asserts Lark actually said False: {ev!r}")

        # And the rendered projection is unchanged by any of it: the model carries the field,
        # the renderer does not spend it.
        from larkdocio.sheets.table import render_spreadsheet
        from larkdocio.sheets.extent import UsedRange
        rendered = render_spreadsheet([
            (t, UsedRange.from_tab_values(t, [["a"]])) for t in read_tabs])
        ev["rendered_mentions_hidden"] = "hidden" in rendered.lower()
        assert ev["rendered_mentions_hidden"] is False, rendered[:400]

    finally:
        delete_code = None
        try:
            writer.delete_spreadsheet(token)
            delete_code = 0
        except LarkAPIError as exc:
            delete_code = exc.code
        ev["delete_code"] = delete_code

        try:
            writer.query_tabs(token)
            ev["confirmed_gone"] = False
        except LarkAPIError as exc:
            ev["confirmed_gone"] = bool(spreadsheet_is_gone(exc))

        # The evidence print lives in the `finally`, before any assertion can preempt it.
        with capsys.disabled():
            print("\n--- LD-477 hidden-tab READ-route gate ---")
            for key in ("spreadsheet_token", "provisioned", "write_side_readback", "read_leg",
                        "rendered_mentions_hidden", "delete_code", "confirmed_gone"):
                if key in ev:
                    print(f"  {key} = {ev[key]!r}")
            print("  RESIDUE: one disposable spreadsheet, deleted above. No media uploaded.")
