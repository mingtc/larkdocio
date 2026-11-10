"""THE LIVE GATE for the ghost-tab skip (LD-383, AC9) — read-only, against the disposable
scratch spreadsheet.

**Why this exists as its own live test.** The offline suite proves the walk against a fixture
of Lark's `90215` body. That is the right unit-level evidence, but it cannot prove the thing the
consumer actually hit: that **Lark itself**, right now, answers a values read of a listed-looking
tab id with a per-tab refusal the walk survives. This drives the shipped `read_spreadsheet` over
a **mixed** tab set — every real tab of the scratch spreadsheet plus one that does not exist —
and asserts the consumer's shape: the real tabs read, the missing one is disclosed with Lark's
own code and message, and the walk completes.

**The honest gap, stated rather than papered over.** A *genuine* ghost — a tab `query_sheets`
itself lists and `read_used_range` then denies — **could not be manufactured on a disposable**
(`dev/ghost-tabs-probe/findings.md`, in the dev repo: an API-deleted tab stops being enumerated
at once, so the deleted-but-indexed hypothesis is refuted). What this gate reproduces live is
therefore the **refusal half** of the consumer's shape, mixed with real readable tabs, by feeding
the walk a tab the values leg will refuse. The tab-listing half is not reproducible without a
workbook that has one, and the consumer's workbook is evidence, never a target.

READ-ONLY. It never writes to Lark.
"""
import pytest

import canary_support
from larkdocio.sheets import SheetsReadClient, render_spreadsheet
from larkdocio.sheets.models import SheetTab

pytestmark = pytest.mark.live
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

#: A sheet id no spreadsheet serves. Six chars, the shape Lark's own ids take, so the request is
#: well-formed and the refusal is about the TAB rather than about the range syntax.
GHOST_SHEET_ID = "gh0st1"


def test_a_refused_tab_does_not_end_a_live_workbook_read(capsys):
    canary_support.load_env()
    reason = canary_support.sheets_missing_reason()
    if reason:
        pytest.skip(reason)

    domain, spreadsheet_token = canary_support.parse_sheet_url(
        canary_support.scratch_sheet_url())
    client = SheetsReadClient.from_read_credentials(domain=domain)

    real_tabs = client.query_sheets(spreadsheet_token)
    assert real_tabs, "expected at least one tab in the scratch spreadsheet"

    ghost = SheetTab(sheet_id=GHOST_SHEET_ID, title="Ghost (does not exist)", index=99,
                     row_count=2, column_count=2)
    mixed = [ghost] + list(real_tabs)

    book = client.read_spreadsheet(spreadsheet_token, tabs=mixed)

    # (a) THE WALK COMPLETED and every real tab still read — the crash withheld exactly this.
    assert [t.sheet_id for t, _u in book.pairs] == [t.sheet_id for t in real_tabs]
    assert book.accounted()

    # (b) The miss is disclosed with LARK'S OWN answer, live — not a fixture, not a paraphrase.
    assert len(book.skips) == 1
    skip = book.skips[0].skip
    assert skip.sheet_id == GHOST_SHEET_ID
    assert skip.code == 90215, f"Lark answered {skip.code}: {skip.msg}"
    assert skip.msg and skip.msg.strip(), "the refusal carried no message to quote"

    # (c) The Markdown a consumer reads says so too.
    markdown = render_spreadsheet(book.pairs, skips=book.skips)
    assert GHOST_SHEET_ID in markdown and str(skip.code) in markdown
    assert "---" in markdown, "the real tabs still rendered as GFM tables"

    # (d) The control: the same spreadsheet with only its real tabs is a CLEAN read — so the
    #     skip arm above is a real branch, not the only thing this code can do.
    clean = client.read_spreadsheet(spreadsheet_token, tabs=real_tabs)
    assert clean.skipped_any is False
    assert render_spreadsheet(clean.pairs, skips=clean.skips) == render_spreadsheet(clean.pairs)

    with capsys.disabled():
        print(f"\n[ghost-tab gate] tabs={len(mixed)} read={len(book.pairs)} "
              f"skipped={len(book.skips)} lark_code={skip.code} msg={skip.msg!r}")
