"""THE SPREADSHEET FILE-LIFECYCLE live arm (LD-176 AC5).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it explicitly::

    pytest -m live_write tests/test_live_sheets_lifecycle_gate.py

The binding live proof of the two **shipped** calls this issue adds —
``SheetsWriteClient.create_spreadsheet`` / ``.delete_spreadsheet``. Until they existed, a
consumer following the guide's whole section on working against disposables could not follow
it for spreadsheets, and the round-3 dogfood seat left the library for raw ``urllib`` to make
and trash its own; the test harness was the only implementation. The arm runs the doctrine's
own shape, twice:

1. **create** a disposable through the shipped call, capturing its token (a token that is not
   captured is an orphan by construction) and **ledgering it immediately**;
2. **use** it — one trivial value write into the fresh workbook's own tab, read back;
3. **delete** it in a ``finally``, so a failure in step 2 still cleans up;
4. **confirm deleted** — and confirm it the only honest way: any call against a trashed token
   answers Lark's deleted-token code, so the **typed error IS the confirmation**. A ``code: 0``
   from the delete means "accepted", not "gone". The second delete is asserted to raise the
   same typed code, which is the idempotency posture a ``finally`` depends on;
5. …and the whole thing runs **twice on fresh disposables**, closing with the zero-orphan
   close-out over the ledger — so a clean sweep is structural rather than lucky.

**Disposables only.** Every token this file touches is one it created in this run. It names no
canary, no standing scratch sheet, no zoo target and no real document; the offline companion
(``tests/test_live_sheets_lifecycle_gate_offline.py``) pins that statically. Titles carry the
grep-able ``larkdocio-harness-DISPOSABLE-`` prefix so a stray survivor is findable by name as
well as through the ledger. Creates/deletes ride the shared ≤3/s WRITE throttle; the
close-out re-query is a read.
"""
import json
import tempfile
import time
from pathlib import Path

import pytest

import canary_support
import sheets_write_harness as H
from larkdocio.errors import LarkAPIError
from larkdocio.sheets.write_client import (
    FILE_ALREADY_DELETED_CODE,
    SPREADSHEET_GONE_CODE,
    SheetsWriteClient,
    spreadsheet_is_gone,
)

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

# The write app's tenant region — NOT a document URL (nothing here addresses a pre-existing
# file; every target is self-provisioned in this run).
DOMAIN = "larksuite.com"


def test_the_shipped_spreadsheet_lifecycle_round_trips_with_zero_orphans(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    writer = SheetsWriteClient.from_write_credentials(DOMAIN)
    # The gateway is here for ONE thing: the close-out re-query, which needs the raw reply
    # code (a gone token answers a non-zero code) that a typed client call raises away.
    gateway = H.SheetsLifecycleGateway.from_write_credentials(DOMAIN)

    tmpdir = tempfile.mkdtemp(prefix="ld176-sheets-lifecycle-")
    ledger = H.Ledger(Path(tmpdir) / "run_ledger.json")

    evidence = []
    for arm in (1, 2):
        title = H.disposable_title(f"LD176-arm{arm}-{int(time.time())}")

        # 1) CREATE through the shipped call, and capture the token in the same breath.
        dest_folder = canary_support.require_disposables_folder()
        spreadsheet = writer.create_spreadsheet(title, folder_token=dest_folder)
        token = spreadsheet["spreadsheet_token"]
        assert token, f"create returned no spreadsheet_token: {spreadsheet!r}"
        assert H.is_disposable_title(spreadsheet.get("title", "")), (
            f"the disposable is not titled with the grep-able prefix: {spreadsheet!r}")
        ledger.record_create(token, title)

        delete_code = None
        read_back = None
        try:
            # 2) USE it: the fresh workbook's own first tab, one trivial value write.
            sheet_id = writer.query_tabs(token)[0]["sheet_id"]
            writer.put_values(token, f"{sheet_id}!A1:A1", [[f"LD-176 arm {arm}"]])
            read_back = writer.read_values(token, f"{sheet_id}!A1:A1")
        finally:
            # 3) DELETE in `finally` — a failure above still trashes the workbook. The code
            #    is recorded rather than raised here, so a teardown problem cannot displace
            #    the real failure; it is asserted below.
            try:
                writer.delete_spreadsheet(token)
                delete_code = 0
            except LarkAPIError as exc:
                delete_code = exc.code
            ledger.record_delete(token, delete_code)

        assert read_back == [[f"LD-176 arm {arm}"]], (
            f"the write did not land in the disposable: {read_back!r}")
        assert delete_code == 0, f"the delete did not succeed: code={delete_code!r}"

        # 4) CONFIRM DELETED — the deleted-token error IS the confirmation.
        with pytest.raises(LarkAPIError) as gone:
            writer.query_tabs(token)
        assert gone.value.code == SPREADSHEET_GONE_CODE, (
            f"a trashed token answered {gone.value.code!r}, expected "
            f"{SPREADSHEET_GONE_CODE} (deleted/not-found)")

        # ...and the shipped delete is typed-not-idempotent: deleting an already-trashed file
        # raises. The code is the DRIVE endpoint's own (`1061007 file has been delete.`), NOT
        # the sheets one above — a distinction this arm discovered and the offline doubles now
        # model. It is the outcome a `finally` may forgive, so it is asserted through the
        # shipped predicate that spans both codes.
        with pytest.raises(LarkAPIError) as second:
            writer.delete_spreadsheet(token)
        assert second.value.code == FILE_ALREADY_DELETED_CODE, second.value.code
        assert spreadsheet_is_gone(second.value)

        evidence.append({
            "arm": arm, "token": token, "sheet_id": sheet_id,
            "read_back": read_back, "delete_code": delete_code,
            "confirm_code": gone.value.code, "second_delete_code": second.value.code,
        })

    # 5) Zero-orphan close-out: re-query EVERY ledger token, independently.
    report = H.close_out(gateway, ledger)
    report.raise_if_orphans()
    assert report.all_clean, f"close-out found orphans: {report.orphans!r}"
    assert report.ledger_count == 2, report.ledger_count
    for rec in report.clean:
        assert rec["recheck_code"] == H.NOT_FOUND_CODE, rec
    for entry in ledger.entries():
        assert entry["deleted"] is True, entry

    with capsys.disabled():
        print("\n[live_write:sheets-lifecycle] "
              f"arms={json.dumps(evidence)} "
              f"ledger_count={report.ledger_count} orphans={len(report.orphans)}")
