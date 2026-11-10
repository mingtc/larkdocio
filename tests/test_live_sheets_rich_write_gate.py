"""LD-119 live gate — the Sheets RICH-cell write round-trip (the Sheets rich/structural-write spec § F1-S1, D6/D7).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` +
network). Run it — together with every other family in one ring::

    pytest -m live_write

The live proof that the four LD-119 rich-cell encoders round-trip **through the gated
apply engine** on a self-provisioned disposable: a **hyperlink**, **styled-runs**, an
**@mention** (``notify:false`` — nobody is pinged, D6), and a **multi-select** cell each
written via a :class:`~larkdocio.sheets.write_apply.RichCellWriteRequest` →
``dry_run`` Plan → ``apply``, then read back and verified:

* the **values leg is surgical** — only the four rich target cells changed, every guard
  neighbour byte-identical (the LD-113 used-range differ, reused);
* each rich cell **round-trips** — the hyperlink/link+text and styled-run flags survive
  (parsed via the LD-115 typed model), the mention lands as a mention segment, and the
  **multi-select normalizes to the same ordered label set** on both sides of the
  read/write asymmetry (write object → read comma-joined string → LD-115 normalizer, D7).

The disposable is **provisioned and destroyed by this gate itself** — never the scratch
sheet, never the zoo, never a real document (D7); teardown deletes in ``finally`` and the
zero-orphan close-out re-queries every ledger token. The **@mention target is the sheet
owner's own ``open_id``** read from the spreadsheet metadata, written ``notify:false`` so
nobody is pinged. Writes use the WRITE app only (``LARK_WRITE_APP_*``).

The style-leg fidelity of a styled-run cell (fonts/fills via the export leg) is the arc's
final gate (S6/LD-124), not this story — here the values leg + typed-model round-trip is
the proof.
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
from larkdocio.sheets.cell_model import Hyperlink, TextRun, UserMention, parse_segments
from larkdocio.sheets.rich_encode import normalize_multi_select
from larkdocio.sheets.write_apply import RichCellWriteRequest, apply, dry_run
from larkdocio.sheets.write_client import SheetsWriteClient

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

DOMAIN = "larksuite.com"

# A per-run nonce so the authored baseline is unique and the diff assertion is exact.
TOK = f"{int(time.time())}-{os.getpid()}"
LINK = "https://www.larksuite.com/ld119"
LINK_TEXT = f"Lark LD119 {TOK}"
MULTI_LABELS = ["Red", "Green"]

# A 5×1 baseline column: A1..A4 are the four rich targets, A5 a guard neighbour that must
# stay byte-identical through every rich write (the surgical control).
BASELINE_ROWS = [
    [f"hyperlink-slot {TOK}"],
    [f"styled-slot {TOK}"],
    [f"mention-slot {TOK}"],
    [f"multi-slot {TOK}"],
    [f"guard-tail {TOK}"],
]
USED_RANGE_BODY = "A1:A5"
RICH_TARGETS_BODY = "A1:A4"   # the four rich cells (the surgical target set)


def _owner_open_id(request, token):
    """The disposable's owner ``open_id`` from the v3 spreadsheet metadata — the
    least-surprise @mention target (written ``notify:false`` so nobody is pinged)."""
    _status, resp = request("GET", f"/open-apis/sheets/v3/spreadsheets/{token}", None, None)
    return (((resp or {}).get("data") or {}).get("spreadsheet") or {}).get("owner_id")


def test_sheets_rich_write_gate_round_trip(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    gateway = H.SheetsLifecycleGateway.from_write_credentials(DOMAIN)
    writer = SheetsWriteClient.from_write_credentials(DOMAIN)
    request = H.build_throttled_write_request(DOMAIN)

    tmpdir = tempfile.mkdtemp(prefix="ld119-sheets-rich-gate-")
    ledger = H.Ledger(Path(tmpdir) / "run_ledger.json")

    evidence = {}
    with H.disposable(gateway, ledger, writer=writer) as d:
        evidence["token"] = d.token
        evidence["sheet_id"] = d.first_sheet_id
        assert d.token, "create yielded no spreadsheet_token"

        sid = d.first_sheet_id
        used_range = f"{sid}!{USED_RANGE_BODY}"
        a1, a2, a3, a4 = (f"{sid}!A{r}" for r in (1, 2, 3, 4))

        owner_open_id = _owner_open_id(request, d.token)
        assert owner_open_id, "could not read the disposable owner_id (the @mention target)"
        evidence["mention_open_id"] = owner_open_id

        # 1) Populate the plain baseline, then two same-run reads → determinism control.
        d.put_values(used_range, BASELINE_ROWS)
        baseline = d.read_values(used_range)
        assert baseline == d.read_values(used_range), "sheets read is non-deterministic"

        # 2) THE GATED ENGINE — four rich writes (encoded types) in one plan.
        requests = [
            RichCellWriteRequest.hyperlink(a1, LINK, text=LINK_TEXT),
            RichCellWriteRequest.styled_runs(a2, [
                {"text": "bold ", "bold": True},
                {"text": "then italic", "italic": True, "fore_color": "#FF0000"},
            ]),
            # notify:false is the default — nobody is pinged (D6).
            RichCellWriteRequest.mention(a3, owner_open_id),
            RichCellWriteRequest.multi_select(a4, MULTI_LABELS),  # rule pairs in S2/LD-120
        ]
        plan = dry_run(requests, writer, d.token)
        assert len(plan.resolved) == 4, f"a rich write was refused at dry-run: {plan.refusals!r}"
        log = apply(plan, writer)
        assert all(e.is_applied for e in log.entries), (
            f"a rich write did not apply: {[e.to_dict() for e in log.entries]!r}"
        )
        evidence["post_write_revisions"] = [e.revision for e in log.entries]

        # 3) VALUES-LEG SURGICAL DIFF — only the four rich cells changed; A5 byte-identical.
        after = d.read_values(used_range)
        changed = assert_surgical(baseline, after, RICH_TARGETS_BODY)
        assert changed == {(0, 0), (1, 0), (2, 0), (3, 0)}, (
            f"the changed cells were not exactly A1:A4: {sorted(changed)!r}"
        )

        # 4) PER-TYPE ROUND-TRIP FIDELITY (the typed LD-115 model parses each readback).
        (hyper,) = parse_segments(after[0][0])
        assert isinstance(hyper, Hyperlink) and hyper.link == LINK and hyper.text == LINK_TEXT

        runs = parse_segments(after[1][0])
        assert [r.text for r in runs] == ["bold ", "then italic"], f"styled-run texts drifted: {runs!r}"
        assert all(isinstance(r, TextRun) for r in runs)
        assert runs[0].style.bold is True and runs[1].style.italic is True

        (mention_seg,) = parse_segments(after[2][0])
        assert isinstance(mention_seg, UserMention), f"A3 did not land as a mention: {after[2][0]!r}"

        # multi-select: read-back is a comma-joined string — normalize BOTH sides (D7).
        read_multi = after[3][0]
        assert normalize_multi_select(read_multi) == normalize_multi_select(
            {"type": "multipleValue", "values": MULTI_LABELS}
        ) == tuple(MULTI_LABELS), f"multi-select did not round-trip: {read_multi!r}"
        evidence["multi_readback"] = read_multi

        # 5) RESTORE the plain baseline (harness value leg — a plain write over a rich cell
        #    is refused by the gated plain path by design) → re-diff to byte-identity.
        d.put_values(used_range, BASELINE_ROWS)
        assert_identical(baseline, d.read_values(used_range))
        evidence["restored_byte_identical"] = True
    # 6) delete-in-finally fired on with-exit.

    report = H.close_out(gateway, ledger)
    report.raise_if_orphans()
    assert report.all_clean, f"close-out found orphans: {report.orphans!r}"
    evidence["orphans"] = len(report.orphans)

    with capsys.disabled():
        print(
            "\n[live_write:sheets-rich-gate] "
            f"token={evidence.get('token')} "
            f"sheet_id={evidence.get('sheet_id')} "
            f"mention_open_id={evidence.get('mention_open_id')} "
            f"post_write_revisions={json.dumps(evidence.get('post_write_revisions'))} "
            f"multi_readback={evidence.get('multi_readback')!r} "
            f"restored_byte_identical={evidence.get('restored_byte_identical')} "
            f"orphans={evidence.get('orphans')}"
        )
