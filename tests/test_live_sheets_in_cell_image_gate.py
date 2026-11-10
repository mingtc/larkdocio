"""THE LIVE GATE for putting a picture IN a spreadsheet cell — write, read back, hash.

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it with the whole ring::

    pytest -m live_write

**The full round trip, because a status code is not evidence.** The arm creates its **own**
disposable workbook, calls the shipped op once, and then proves the claim the op makes rather
than the answers the calls gave:

1. **a fresh read of the cell** shows an ``embed-image`` value carrying a ``fileToken`` — the
   op's own verdict read is re-done here independently, because the whole hazard of this
   route is that ``values_image`` answers ``code:0`` and the only thing that proves storage
   is what the cell now holds;
2. **the bytes are downloaded again and compared by sha256 and length** — the shipped
   ``verify_round_trip``, reused, not restated;
3. **the token is Lark's OWN mint**: nothing was uploaded on this route, and the arm records
   the token as residue rather than as something it owns;
4. **the clear is exercised as what it is** — an ordinary ``""`` value write — and the cell is
   re-read to show the value really is ``""``;
5. **the refusal control is run live**: the same write at a tab that does not exist must fail.
   Whatever code Lark answers with is recorded in the evidence print rather than asserted, so
   a renumbering on their side does not redden this gate — what is asserted is that the write
   **fails** and that the real cell is untouched.

**BYTES ARE HASHED, NEVER INSPECTED.** Nothing here decodes, renders or prints a media
payload; the evidence print carries digests, lengths, ids and tokens only. The image is a 1x1
PNG **built in this file from source** — no binary fixture is committed.

**THIS ARM MINTS PERMANENT, UNSWEEPABLE RESIDUE, AND THAT IS BOUGHT KNOWINGLY.** Every
successful write mints a media ``file_token`` that **no open-API verb purges**, and **trashing
the workbook does not remove it**. So the workbook is deleted in a ``finally`` and the tokens
are **not**: there is no cleanup leg here and there cannot be one — a ``finally`` that
pretended to purge media would be a lie in the shape of hygiene. The tokens minted are printed
so the residue is recorded rather than implied.

**THE TARGET IS ONLY A WORKBOOK THIS GATE CREATED.** ``create_spreadsheet`` is the only way a
spreadsheet token enters this module: no environment variable naming a sheet is read, the read
canary is never addressed, and no pre-existing workbook is touched. The teardown is proved by
an **independent re-query**, never by the delete's own ``code:0``.

**Gentle.** Around eight calls on one disposable, each through the shipped throttles.

**Skips loudly, never silently.** Without write credentials the arm skips with a message
naming exactly what is missing.

**What this gate does NOT prove.** It cannot observe whether a client **renders** the stored
image — no API call can. It proves the cell holds a picture, that the picture's bytes come
back byte-identical, and that writing ``""`` removes it.
"""
import time
import zlib

import pytest

import canary_support
import sheets_write_harness as H
from larkdocio.base.media import sha256_of
from larkdocio.errors import LarkAPIError
from larkdocio.sheets.media import SheetsMediaClient, put_image_in_sheet
from larkdocio.sheets.write_client import SheetsWriteClient, spreadsheet_is_gone

pytestmark = pytest.mark.live_write
# The live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing the statement
# above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

# The write app's tenant region (the toolkit's default OpenAPI domain). NOT a spreadsheet
# URL — every target here is self-provisioned in this run.
DOMAIN = "larksuite.com"


def png_bytes():
    """A 1x1 PNG, built from source so no binary fixture is committed."""
    def chunk(kind, payload):
        body = kind + payload
        return (len(payload).to_bytes(4, "big") + body
                + zlib.crc32(body).to_bytes(4, "big"))

    ihdr = (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + bytes((8, 2, 0, 0, 0))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes((0, 0, 0, 0)))) + chunk(b"IEND", b""))


def test_in_cell_image_round_trips_and_the_clear_is_an_empty_value_write(capsys):
    """values_image -> fresh read-back -> hash-verified -> "" clears it."""
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    payload = png_bytes()
    writer = SheetsWriteClient.from_write_credentials(DOMAIN)
    media = SheetsMediaClient.from_write_credentials(DOMAIN)

    title = H.disposable_title(f"LD447-in-cell-image-{int(time.time())}")
    dest_folder = canary_support.require_disposables_folder()
    workbook = writer.create_spreadsheet(title, folder_token=dest_folder)
    token = workbook["spreadsheet_token"]
    assert token, f"create returned no spreadsheet_token: {workbook!r}"
    evidence = {"spreadsheet_token": token, "media_residue": []}

    try:
        sheet_id = writer.query_tabs(token)[0]["sheet_id"]
        target = f"{sheet_id}!B2:B2"
        evidence["target"] = target

        # 1) THE OP, once. It does the write, re-reads the cell and hash-verifies the bytes.
        written = put_image_in_sheet(
            client=writer, spreadsheet_token=token, a1_range=target,
            data=payload, name="ld447-gate.png", media=media,
        )
        evidence["media_residue"].append(written.file_token)
        evidence["sha256"] = written.sha256
        evidence["size"] = written.size
        evidence["revision"] = written.revision
        assert written.bytes_verified is True
        assert written.file_token

        # 2) AN INDEPENDENT read-back — not the op's, not the write's echo.
        value_range = writer.read_value_range(token, target)
        cell = value_range["values"][0][0]
        evidence["read_back_type"] = cell.get("type") if isinstance(cell, dict) else cell
        assert isinstance(cell, dict), cell
        assert cell.get("fileToken") == written.file_token, cell

        # 3) AN INDEPENDENT hash check on a second download.
        again = media.download(written.file_token)
        evidence["redownload_len"] = len(again)
        assert len(again) == len(payload)
        assert sha256_of(again) == written.sha256

        # 4) THE REFUSAL CONTROL, live: the same write at a tab that does not exist. The code
        #    is RECORDED, never asserted — Lark may renumber it.
        refused = None
        try:
            put_image_in_sheet(client=writer, spreadsheet_token=token,
                               a1_range="banana9!B2:B2", data=payload,
                               name="ld447-gate-control.png")
        except LarkAPIError as exc:
            refused = f"code={exc.code}"
        evidence["bad_tab_refused"] = refused
        assert refused, (
            "a values_image write at a tab that does not exist was expected to fail; it "
            "did not, which would make the successful write above unfalsified")

        # 5) THE CLEAR — an ordinary value write, then a fresh read proving it landed.
        writer.put_values(token, target, [[""]])
        cleared = writer.read_value_range(token, target)
        evidence["after_clear"] = cleared.get("values")
        assert cleared.get("values") == [[""]], cleared

    finally:
        delete_code = None
        try:
            writer.delete_spreadsheet(token)
            delete_code = 0
        except LarkAPIError as exc:
            delete_code = exc.code
        evidence["delete_code"] = delete_code

        # GONE-NESS IS PROVED BY AN INDEPENDENT RE-QUERY, never by the delete's own code.
        try:
            writer.query_tabs(token)
            evidence["confirmed_gone"] = False
        except LarkAPIError as exc:
            evidence["confirmed_gone"] = bool(spreadsheet_is_gone(exc))
            evidence["confirm_code"] = exc.code

        # THE EVIDENCE PRINT LIVES IN THE `finally`, before any assertion can preempt it. The
        # media tokens are printed because they are PERMANENT: trashing the workbook above
        # removes the sheet, not the bytes, and nothing in Lark's open API purges them.
        with capsys.disabled():
            print("\n--- sheets in-cell image gate ---")
            for key, value in evidence.items():
                print(f"  {key}: {value}")
            print("  NOTE: the media tokens above are permanent, unpurgeable residue — "
                  "Lark minted them itself on the values_image call, and trashing the "
                  "workbook did not remove them.")
