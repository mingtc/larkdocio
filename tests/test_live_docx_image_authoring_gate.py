"""THE LIVE GATE for putting an IMAGE in a docx body — create, upload, bind, verify.

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it with the whole ring::

    pytest -m live_write

**The full round trip, because a status code is not evidence.** The gate creates its **own**
disposable document, calls the shipped op once, and then proves the claim the op makes rather
than the answers the calls gave:

1. **a fresh read-back of the block** shows ``image.token`` equal to the uploaded token — the
   op's own read-back is re-done here independently, because the whole point of this route is
   that an upload answering ``code:0`` leaves the token **empty** until the bind;
2. **the bytes are downloaded again and compared by sha256 and length** — the shipped
   ``verify_round_trip``, reused, not restated;
3. **the ORDER trap is exercised live**: an upload parented on the **document** answers
   success and yields a token, and binding *that* token is refused. Whatever code Lark
   answers with is recorded in the evidence print rather than asserted, so a renumbering on
   their side does not redden this gate — what is asserted is that the bind **fails** and the
   block's token is **unchanged**.

**BYTES ARE HASHED, NEVER INSPECTED.** Nothing here decodes, renders or prints a media
payload; the evidence print carries digests, lengths, ids and tokens only. The image is a 1x1
PNG **built in this file from source** — no binary fixture is committed.

**THIS ARM MINTS PERMANENT, UNSWEEPABLE RESIDUE, AND THAT IS BOUGHT KNOWINGLY.** Every upload
mints a media ``file_token`` that **no open-API verb purges**, and **deleting the document
does not remove it**. So the document is deleted in a ``finally`` and the tokens are **not**:
there is no cleanup leg here and there cannot be one — a ``finally`` that pretended to purge
media would be a lie in the shape of hygiene. The tokens minted are printed so the residue is
recorded rather than implied.

**THE TARGET IS ONLY A DOCUMENT THIS GATE CREATED.** ``create_document`` is the only way a
document id enters this module: no environment variable naming a document is read, the read
canary is never addressed, and no pre-existing document is touched.

**Gentle.** Around ten calls on one disposable, each through the shipped throttles.

**Skips loudly, never silently.** Without write credentials the arm skips with a message
naming exactly what is missing.

**What this gate does NOT prove.** It cannot observe whether a client **renders** the bound
image — no API call can. It proves the block exists, carries the bytes, and hands them back
byte-identical.
"""
import time
import zlib

import pytest

import canary_support
from larkdocio.common import get_write_credentials
from larkdocio.errors import LarkDocIOError
from larkdocio.write import DocxMediaClient, WriteClient, put_image_in_document
from larkdocio.write.media import DOCX_IMAGE_PARENT_TYPE, IMAGE_BLOCK_TYPE

pytestmark = pytest.mark.live_write
# The live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing the statement
# above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

# The write app's tenant region (the toolkit's default OpenAPI domain). NOT a document URL —
# the gate never addresses a pre-existing doc.
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


def test_image_authoring_round_trip(capsys):
    """create -> upload bound to the block -> PATCH -> fresh read-back -> hash-verified."""
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    payload = png_bytes()
    writer = WriteClient(*get_write_credentials(), DOMAIN)
    media = DocxMediaClient.from_write_credentials(DOMAIN)

    dest_folder = canary_support.require_disposables_folder()
    doc = writer.create_document(title=f"larkdocio-image-authoring-gate {int(time.time())}",
                                 folder_token=dest_folder)
    doc_id = doc["document_id"]
    evidence = {"doc_id": doc_id, "media_residue": []}

    try:
        # 1) THE OP, once. It does the three calls, re-reads and hash-verifies.
        authored = put_image_in_document(
            client=writer, media=media, document_id=doc_id,
            data=payload, name="ld433-gate.png", width=24, height=24,
        )
        evidence["media_residue"].append(authored.file_token)
        evidence["block_id"] = authored.block_id
        evidence["sha256"] = authored.sha256
        evidence["size"] = authored.size
        assert authored.bytes_verified is True

        # 2) AN INDEPENDENT read-back — not the op's, not any call's echo.
        block = writer.get_block(doc_id, authored.block_id)
        evidence["read_back_type"] = block.get("block_type")
        evidence["read_back_token"] = (block.get("image") or {}).get("token")
        assert block.get("block_type") == IMAGE_BLOCK_TYPE, block
        assert (block.get("image") or {}).get("token") == authored.file_token, block

        # 3) AN INDEPENDENT hash check on a second download.
        again = media.download(authored.file_token)
        evidence["redownload_len"] = len(again)
        assert len(again) == len(payload)
        from larkdocio.base.media import sha256_of

        assert sha256_of(again) == authored.sha256

        # 4) THE ORDER TRAP, live: an upload parented on the DOCUMENT yields a token no block
        #    will accept. The refusal CODE is recorded, never asserted — Lark may renumber it.
        stray = media.upload(data=payload, name="ld433-gate-stray.png",
                             parent_type=DOCX_IMAGE_PARENT_TYPE, parent_node=doc_id)
        evidence["media_residue"].append(stray.file_token)
        bind_refused = None
        try:
            writer._patch_block(doc_id, authored.block_id,
                               {"replace_image": {"token": stray.file_token}})
        except LarkDocIOError as exc:
            bind_refused = str(exc)
        evidence["stray_bind_refused"] = bind_refused
        assert bind_refused, (
            "binding a token uploaded against the DOCUMENT was expected to fail; it did not")
        after = writer.get_block(doc_id, authored.block_id)
        assert (after.get("image") or {}).get("token") == authored.file_token, after

    finally:
        try:
            resp = writer.delete_document(doc_id)
            evidence["deleted"] = resp.get("code") if isinstance(resp, dict) else "ok"
        except LarkDocIOError as exc:
            evidence["deleted"] = f"skipped ({exc})"

        # THE EVIDENCE PRINT LIVES IN THE `finally`, before any assertion can preempt it. The
        # media tokens are printed because they are PERMANENT: deleting the document above
        # removes the block, not the bytes, and nothing in Lark's open API purges them.
        with capsys.disabled():
            print("\n--- docx image-authoring gate ---")
            for key, value in evidence.items():
                print(f"  {key}: {value}")
            print("  NOTE: the media tokens above are permanent, unpurgeable residue.")
