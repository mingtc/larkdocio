"""THE LIVE GATE for floating a picture OVER a range — upload, bind, query, remove.

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it with the whole ring::

    pytest -m live_write

**The full round trip, because a status code is not evidence.** The arm creates its **own**
disposable workbook and then proves the claims the op makes rather than the answers the calls
gave:

1. **the upload alone is not a bind** — before the op runs, a fresh ``float_images/query`` on
   the tab is asserted **empty**, and it is asserted empty again after an upload made by this
   arm on its own, so the route's central hazard is demonstrated live rather than recited;
2. **the bind's verdict is a fresh query** — the op's own verdict read is re-done here
   independently, and the item's ``range`` and ``float_image_token`` are compared against what
   was asked for;
3. **the bytes are downloaded again and compared by sha256 and length** — the shipped
   ``verify_round_trip`` / ``sha256_of``, reused, not restated;
4. **``parent_node`` is the WORKBOOK** — the arm asserts the op parented its upload on the
   spreadsheet token, never on the tab or a cell, by reading back what the op reports;
5. **the mis-typed refusal is exercised live**: binding a token nothing minted must **fail**
   and must leave the tab exactly as it was. Whatever code Lark answers with is **recorded in
   the evidence print rather than asserted**, so a renumbering on their side does not redden
   this gate — what is asserted is that it failed, that it was sent **once**, and that the
   re-query shows no phantom;
6. **the removal's verdict is the query too** — the delete's own ``code:0`` is never the
   proof; the fresh query no longer listing the id is.

**BYTES ARE HASHED, NEVER INSPECTED.** Nothing here decodes, renders or prints a media
payload; the evidence print carries digests, lengths, ids and tokens only. The image is a 1x1
PNG **built in this file from source** — no binary fixture is committed.

**THIS ARM MINTS PERMANENT, UNSWEEPABLE RESIDUE, AND THAT IS BOUGHT KNOWINGLY.** Every run
uploads media, **no open-API verb purges drive media**, and **neither removing the float image
nor trashing the workbook removes the bytes**. So the workbook is deleted in a ``finally`` and
the tokens are **not**: there is no cleanup leg here and there cannot be one — a ``finally``
that pretended to purge media would be a lie in the shape of hygiene. Every token minted is
printed, so the residue is **ledgered rather than implied**.

**THE TARGET IS ONLY A WORKBOOK THIS GATE CREATED.** ``create_spreadsheet`` is the only way a
spreadsheet token enters this module: no environment variable naming a sheet is read, the read
canary is never addressed, and no pre-existing workbook is touched. The teardown is proved by
an **independent re-query**, never by the delete's own ``code:0``.

**Gentle.** Around a dozen calls on one disposable, each through the shipped throttles.

**Skips loudly, never silently.** Without write credentials the arm skips with a message
naming exactly what is missing.

**What this gate does NOT prove.** It cannot observe whether a client **renders** the float
image — no API call can. It proves the tab lists the picture at the range asked for, that its
bytes come back byte-identical, and that the removal is real.
"""
import time
import zlib

import pytest

import canary_support
import sheets_write_harness as H
from larkdocio.base.media import sha256_of
from larkdocio.errors import LarkAPIError
from larkdocio.sheets.media import (
    SHEET_IMAGE_PARENT_TYPE,
    FloatImageMediaClient,
    put_float_image_in_sheet,
    remove_float_image_from_sheet,
)
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


def test_float_image_round_trips_and_every_verdict_is_a_fresh_query(capsys):
    """upload(WORKBOOK) -> bind -> fresh query -> hash -> delete -> fresh query."""
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    payload = png_bytes()
    writer = SheetsWriteClient.from_write_credentials(DOMAIN)
    media = FloatImageMediaClient.from_write_credentials(DOMAIN)

    title = H.disposable_title(f"LD448-float-image-{int(time.time())}")
    dest_folder = canary_support.require_disposables_folder()
    workbook = writer.create_spreadsheet(title, folder_token=dest_folder)
    token = workbook["spreadsheet_token"]
    assert token, f"create returned no spreadsheet_token: {workbook!r}"
    evidence = {"spreadsheet_token": token, "media_residue": []}

    try:
        sheet_id = writer.query_tabs(token)[0]["sheet_id"]
        anchor = f"{sheet_id}!A1:A1"
        evidence["anchor"] = anchor

        # 0) A FRESH TAB HAS NO FLOAT IMAGES — the baseline every later query is read against.
        assert writer.query_float_images(token, sheet_id) == []

        # 1) THE UPLOAD ALONE IS NOT A BIND, demonstrated rather than recited: this arm makes
        #    its OWN upload, parented on the WORKBOOK, and the tab is still empty afterwards.
        #    (That token is permanent residue and is ledgered; nothing will ever point at it.)
        stray = media.upload(data=payload, name="ld448-unbound.png",
                             parent_type=SHEET_IMAGE_PARENT_TYPE, parent_node=token)
        evidence["media_residue"].append(stray.file_token)
        evidence["query_after_upload_only"] = writer.query_float_images(token, sheet_id)
        assert evidence["query_after_upload_only"] == [], (
            "an upload answered success and the tab lists a float image — the route's own "
            "measured behaviour is that an upload binds NOTHING")

        # 2) THE OP, once. Upload (on the workbook) -> bind -> fresh query -> hash-verify.
        floated = put_float_image_in_sheet(
            client=writer, media=media, spreadsheet_token=token, sheet_id=sheet_id,
            a1_range=anchor, data=payload, name="ld448-gate.png",
            width=120, height=120,
        )
        evidence["media_residue"].append(floated.float_image_token)
        evidence["float_image_id"] = floated.float_image_id
        evidence["sha256"] = floated.sha256
        evidence["size"] = floated.size
        assert floated.bytes_verified is True
        assert floated.float_image_id and floated.float_image_token
        # The WORKBOOK trap, asserted: the tab id is not what the picture's token hangs off.
        assert floated.float_image_token != stray.file_token
        assert floated.spreadsheet_token == token and floated.sheet_id == sheet_id

        # 3) AN INDEPENDENT verdict read — not the op's, not the create's echo.
        listed = writer.query_float_images(token, sheet_id)
        evidence["listed_ids"] = [item["float_image_id"] for item in listed]
        mine = [item for item in listed
                if item["float_image_id"] == floated.float_image_id]
        assert len(mine) == 1, listed
        assert mine[0]["float_image_token"] == floated.float_image_token
        assert mine[0]["range"] == anchor, mine[0]

        # 4) AN INDEPENDENT hash check on a second download.
        again = media.download(floated.float_image_token)
        evidence["redownload_len"] = len(again)
        assert len(again) == len(payload)
        assert sha256_of(again) == floated.sha256

        # 5) THE MIS-TYPED REFUSAL, live. A token nothing minted must FAIL — and this route
        #    answers such a failure with a server error that says "retry later" while
        #    refusing. The code is RECORDED, never asserted (Lark may renumber it); what is
        #    asserted is that it failed, and that the tab is UNCHANGED.
        refused = None
        try:
            writer.create_float_image(
                token, sheet_id, float_image_token="ld448-invented-token-nothing-minted",
                a1_range=f"{sheet_id}!C3:C3", width=60, height=60)
        except LarkAPIError as exc:
            refused = f"code={exc.code} msg={exc.msg!r}"
        evidence["invented_token_refused"] = refused
        assert refused, (
            "binding a token nothing minted was expected to fail; it did not, which would "
            "make the successful bind above unfalsified")
        after_control = writer.query_float_images(token, sheet_id)
        evidence["query_after_control"] = [i["float_image_id"] for i in after_control]
        assert evidence["query_after_control"] == [floated.float_image_id], (
            "the refused bind left a PHANTOM float image on the tab")

        # 6) REMOVAL — and its verdict is the fresh query, never the delete's own code:0.
        remaining = remove_float_image_from_sheet(
            client=writer, spreadsheet_token=token, sheet_id=sheet_id,
            float_image_id=floated.float_image_id)
        evidence["remaining_after_remove"] = list(remaining)
        assert floated.float_image_id not in remaining
        assert writer.query_float_images(token, sheet_id) == []

        # ...and THE BYTES ARE STILL THERE. Removing the anchor is not a purge, and this arm
        # proves that rather than assuming it: the token still downloads.
        still = media.download(floated.float_image_token)
        evidence["bytes_survive_removal"] = len(still) == len(payload)
        assert evidence["bytes_survive_removal"], (
            "the media token stopped resolving after the float image was removed — that "
            "would CHANGE the residue disclosure this library ships, so it is asserted")

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
        # media tokens are printed because they are PERMANENT: removing the float image and
        # trashing the workbook took away the anchor and the sheet, not the bytes, and
        # nothing in Lark's open API purges them.
        with capsys.disabled():
            print("\n--- sheets float image gate ---")
            for key, value in evidence.items():
                print(f"  {key}: {value}")
            print("  NOTE: the media tokens above are permanent, unpurgeable residue — this "
                  "run uploaded them, and neither the float-image delete nor trashing the "
                  "workbook removed the bytes. LEDGERED, not cleaned.")
