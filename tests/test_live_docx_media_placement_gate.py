"""THE LIVE GATE that MEASURES WHERE media lands — ``parent_block_id`` and ``index``.

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it with the whole ring::

    pytest -m live_write

**Why this gate exists (LD-470).** ``put_image_in_document`` and ``put_file_in_document`` both
take ``parent_block_id`` and ``index``, and until LD-470 those two arguments appeared in no
shipped text at all — a consumer who needed a picture **in a particular place** could only find
them with ``inspect.signature``, and could only learn what they *do* by writing to a live
document. A dogfood run had **derived** the semantics (*0-based, insert-before-child-N*) from
one diff; a derivation from one run is a hypothesis, and shipping a hypothesis as an absolute
is the exact defect this gate's issue exists to stop. **So the semantics are measured here,
on a document this gate creates**, and the shipped sentences quote this measurement.

**The four cases the shipped text rests on**, all on one disposable, all read back from the
root block's own ``children`` list rather than from any call's echo:

1. ``index`` **positive** — where does the block land among existing children;
2. ``index=0`` — the front of the list;
3. the **default** (``index=-1``) — the end of the list;
4. a **non-root ``parent_block_id``** — the block lands inside *that* block's children and
   the root's child count is unchanged.

Case 4 is run with ``put_file_in_document``, which also pins the **wrapper trap**: a type-23
create brings **two** blocks into existence and the id the create answers is a **type-33 view
wrapper** whose child is the real file block. Both ids are read back and typed here.

**BYTES ARE HASHED, NEVER INSPECTED.** Nothing decodes, renders or prints a payload; the
evidence print carries ids, types, orders, digests and tokens only. The image is a 1x1 PNG
**built from source** and the attachment is a handful of ASCII bytes — no binary fixture is
committed.

**THIS ARM MINTS PERMANENT, UNSWEEPABLE RESIDUE, KNOWINGLY.** Every upload mints a media
``file_token`` that **no open-API verb purges**, and deleting the document does not remove it.
The document is deleted in a ``finally``; the tokens are printed rather than pretend-purged.

**THE TARGET IS ONLY A DOCUMENT THIS GATE CREATED.** ``create_document`` is the only way a
document id enters this module: no environment variable naming a document is read, the read
canary is never addressed, no pre-existing document is touched.

**What this gate does NOT prove.** One tenant, one day, ``tenant_access_token``, a plain
``docx`` (not wiki-wrapped), root and one bullet parent. Other parents, other document kinds
and an ``index`` past the end are **unmeasured, not refuted**.
"""
import time
import zlib

import pytest

import canary_support
from larkdocio.common import get_write_credentials
from larkdocio.errors import LarkDocIOError
from larkdocio.write import (
    DocxMediaClient,
    WriteClient,
    put_file_in_document,
    put_image_in_document,
)
from larkdocio.write.client import text_block
from larkdocio.write.media import (
    FILE_BLOCK_TYPE,
    FILE_VIEW_WRAPPER_BLOCK_TYPE,
    IMAGE_BLOCK_TYPE,
)

pytestmark = pytest.mark.live_write
# The live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing the statement
# above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

# The write app's tenant region (the toolkit's default OpenAPI domain). NOT a document URL —
# the gate never addresses a pre-existing doc.
DOMAIN = "larksuite.com"

#: The bullet block used as the NON-ROOT parent in case 4. A list item is the cheapest docx
#: block that legitimately owns children.
BULLET_BLOCK_TYPE = 12


def png_bytes():
    """A 1x1 PNG, built from source so no binary fixture is committed."""
    def chunk(kind, payload):
        body = kind + payload
        return (len(payload).to_bytes(4, "big") + body
                + zlib.crc32(body).to_bytes(4, "big"))

    ihdr = (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + bytes((8, 2, 0, 0, 0))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes((0, 0, 0, 0)))) + chunk(b"IEND", b""))


def _children(writer, doc_id, block_id):
    """The block's own ordered ``children`` — read back, never taken from a call's echo."""
    return list((writer.get_block(doc_id, block_id) or {}).get("children") or ())


def test_media_placement_semantics(capsys):
    """parent_block_id + index, measured: positive, 0, default, and a non-root parent."""
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    payload = png_bytes()
    writer = WriteClient(*get_write_credentials(), DOMAIN)
    media = DocxMediaClient.from_write_credentials(DOMAIN)

    dest_folder = canary_support.require_disposables_folder()
    doc = writer.create_document(title=f"larkdocio-media-placement-gate {int(time.time())}",
                                 folder_token=dest_folder)
    doc_id = doc["document_id"]
    evidence = {"doc_id": doc_id, "media_residue": []}

    try:
        # ---- the baseline: three paragraphs at the root, in a known order --------------- #
        writer.create_children(
            doc_id, doc_id,
            [text_block("A"), text_block("B"), text_block("C")], -1)
        seeded = _children(writer, doc_id, doc_id)
        evidence["seeded_root_children"] = seeded
        assert len(seeded) == 3, seeded
        a, b, c = seeded

        # ---- case 1: a POSITIVE index --------------------------------------------------- #
        at_one = put_image_in_document(
            client=writer, media=media, document_id=doc_id,
            data=payload, name="ld470-index-1.png", index=1)
        evidence["media_residue"].append(at_one.file_token)
        order = _children(writer, doc_id, doc_id)
        evidence["after_index_1"] = order
        evidence["index_1_landed_at"] = order.index(at_one.block_id)
        assert order == [a, at_one.block_id, b, c], order

        # ---- case 2: index=0 ------------------------------------------------------------ #
        at_zero = put_image_in_document(
            client=writer, media=media, document_id=doc_id,
            data=payload, name="ld470-index-0.png", index=0)
        evidence["media_residue"].append(at_zero.file_token)
        order = _children(writer, doc_id, doc_id)
        evidence["after_index_0"] = order
        evidence["index_0_landed_at"] = order.index(at_zero.block_id)
        assert order == [at_zero.block_id, a, at_one.block_id, b, c], order

        # ---- case 3: THE DEFAULT (index=-1) --------------------------------------------- #
        appended = put_image_in_document(
            client=writer, media=media, document_id=doc_id,
            data=payload, name="ld470-default.png")
        evidence["media_residue"].append(appended.file_token)
        order = _children(writer, doc_id, doc_id)
        evidence["after_default"] = order
        evidence["default_landed_at"] = order.index(appended.block_id)
        assert order[-1] == appended.block_id, order
        root_before_case_4 = order

        # ---- case 4: a NON-ROOT parent, and the wrapper trap ----------------------------- #
        made = writer.create_children(
            doc_id, doc_id,
            [{"block_type": BULLET_BLOCK_TYPE,
              "bullet": {"elements": [{"text_run": {"content": "a parent bullet"}}]}}], -1)
        bullet_id = made["children"][0]["block_id"]
        evidence["bullet_id"] = bullet_id

        attached = put_file_in_document(
            client=writer, media=media, document_id=doc_id,
            data=b"ld470 placement gate attachment\n", name="ld470-gate.txt",
            parent_block_id=bullet_id, index=0)
        evidence["media_residue"].append(attached.file_token)
        evidence["file_block_id"] = attached.block_id
        evidence["wrapper_block_id"] = attached.wrapper_block_id
        assert attached.bytes_verified is True

        bullet_children = _children(writer, doc_id, bullet_id)
        evidence["bullet_children"] = bullet_children
        assert bullet_children == [attached.wrapper_block_id], bullet_children

        root_after = _children(writer, doc_id, doc_id)
        evidence["root_after_nonroot_parent"] = root_after
        assert root_after == root_before_case_4 + [bullet_id], root_after
        assert attached.block_id not in root_after
        assert attached.wrapper_block_id not in root_after

        # the two blocks, typed from a fresh read of each
        wrapper = writer.get_block(doc_id, attached.wrapper_block_id) or {}
        child = writer.get_block(doc_id, attached.block_id) or {}
        evidence["wrapper_type"] = wrapper.get("block_type")
        evidence["file_block_type"] = child.get("block_type")
        evidence["wrapper_children"] = list(wrapper.get("children") or ())
        evidence["file_block_parent"] = child.get("parent_id")
        assert wrapper.get("block_type") == FILE_VIEW_WRAPPER_BLOCK_TYPE, wrapper
        assert child.get("block_type") == FILE_BLOCK_TYPE, child
        assert list(wrapper.get("children") or ()) == [attached.block_id], wrapper
        assert (child.get("file") or {}).get("token") == attached.file_token, child

        # and the image blocks really are image blocks where they landed
        for authored in (at_one, at_zero, appended):
            block = writer.get_block(doc_id, authored.block_id) or {}
            assert block.get("block_type") == IMAGE_BLOCK_TYPE, block
            assert (block.get("image") or {}).get("token") == authored.file_token, block

    finally:
        try:
            resp = writer.delete_document(doc_id)
            evidence["deleted"] = resp.get("code") if isinstance(resp, dict) else "ok"
        except LarkDocIOError as exc:
            evidence["deleted"] = f"skipped ({exc})"

        # THE EVIDENCE PRINT LIVES IN THE `finally`, before any assertion can preempt it. The
        # media tokens are printed because they are PERMANENT: deleting the document above
        # removes the blocks, not the bytes, and nothing in Lark's open API purges them.
        with capsys.disabled():
            print("\n--- docx media PLACEMENT gate (LD-470) ---")
            for key, value in evidence.items():
                print(f"  {key}: {value}")
            print("  NOTE: the media tokens above are permanent, unpurgeable residue.")
