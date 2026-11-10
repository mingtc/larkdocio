"""THE Sheets self-provision live cycle (LD-112).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` +
network). Run it explicitly::

    pytest -m live_write

The binding **live** proof of the leak-proof harness: a full
**create → populate → mutate → verify → DELETE-in-``finally`` → zero-orphan close-out**
cycle against a spreadsheet it **provisions and destroys itself** — never the scratch
sheet, never the zoo, never a real document (D7). It uses the WRITE app's own
credentials throughout (the app owns what it creates), the shipped LD-109
``SheetsWriteClient`` for the value legs, and the LD-112 harness for the lifecycle:

1. ``disposable()`` **creates** its own disposable spreadsheet (v3), ledgering the token;
2. **populates** a 2×2 baseline via ``put_values``;
3. **mutates** row 2 via a second ``put_values``;
4. **verifies** the read-back (``UnformattedValue``) reflects the mutation;
5. **DELETES in ``finally``** (drive v1, ``type=sheet``) — so a mid-cycle crash still cleans up;
6. runs the **zero-orphan close-out**: re-queries every ledger token, asserting each is gone
   (``1310249``) — the independent proof that nothing leaked.

The ledger is a per-run temp file (the audit list for this cycle). Creates/deletes ride
the shared ≤3/sec throttle; the close-out re-query is a read (un-throttled).
"""
import json
import tempfile
from pathlib import Path

import pytest

import canary_support
import sheets_write_harness as H
from larkdocio.sheets.write_client import SheetsWriteClient

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

# The write app's tenant region — NOT a document URL (the harness never addresses a
# pre-existing doc; it self-provisions).
DOMAIN = "larksuite.com"


def test_sheets_harness_round_trips_and_leaves_zero_orphans(capsys):
    # Load the repo .env (local runs); skip LOUDLY if we cannot run.
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    gateway = H.SheetsLifecycleGateway.from_write_credentials(DOMAIN)
    writer = SheetsWriteClient.from_write_credentials(DOMAIN)

    tmpdir = tempfile.mkdtemp(prefix="ld112-sheets-harness-")
    ledger = H.Ledger(Path(tmpdir) / "run_ledger.json")

    evidence = {}
    with H.disposable(gateway, ledger, writer=writer) as d:
        evidence["token"] = d.token
        evidence["sheet_id"] = d.first_sheet_id
        assert d.token, "create yielded no spreadsheet_token"
        assert H.is_disposable_title(d.title), "disposable was not titled with the grep-able DISPOSABLE prefix"

        sid = d.first_sheet_id
        # 2) Populate a 2x2 baseline.
        d.put_values(f"{sid}!A1:B2", [["h1", "h2"], ["v1", "v2"]])
        # 3) Mutate row 2.
        d.put_values(f"{sid}!A2:B2", [["m1", "m2"]])
        # 4) Verify the read-back reflects the mutation (raw UnformattedValue).
        matrix = d.read_values(f"{sid}!A1:B2")
        assert matrix[0] == ["h1", "h2"], f"header row drifted: {matrix!r}"
        assert matrix[1] == ["m1", "m2"], f"mutation not reflected in read-back: {matrix!r}"
        evidence["verified_matrix"] = matrix
    # 5) delete-in-finally already fired here (the with-block exited).

    # 6) Zero-orphan close-out: re-query every ledger token, assert each is gone.
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
            "\n[live_write:sheets] "
            f"token={evidence.get('token')} "
            f"sheet_id={evidence.get('sheet_id')} "
            f"verified={json.dumps(evidence.get('verified_matrix'))} "
            f"ledger_count={evidence.get('ledger_count')} "
            f"orphans={evidence.get('orphans')}"
        )
