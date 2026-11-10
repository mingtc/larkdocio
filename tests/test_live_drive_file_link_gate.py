"""THE LIVE GATE for *"for the full details, open the attached file"* — end to end.

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*``, network, and a
folder token the caller supplies). Run it with the whole ring::

    pytest -m live_write

**The two halves are demonstrated TOGETHER, in one round trip**, because either alone leaves the
ask unserved:

1. a small ``.html`` is uploaded into a folder **the caller named** (never one this library
   created — no folder-creating call exists), its **permalink** is asked for, and the bytes are
   re-downloaded and compared **by sha256 and length**;
2. a real sentence is authored into a **document this gate created**, whose anchor text is
   **not** the URL, through the plan-gated write engine — never a raw call;
3. the document is **re-downloaded and read back through the reader's own Markdown**, and the
   verdict is that the reader emits ``[anchor](url)`` with the anchor text and the permalink.
   **The read-back is the verdict**, never the write's echo.

A second arm attaches the same file as a **📎 attachment block** (docx type 23), which is the
honestly-named fallback and a **different product**: the wrapper trap is exercised live — the
create answers a type-33 view wrapper, and the op's returned block id must be the **child**.

**BYTES ARE HASHED, NEVER INSPECTED.** Nothing here decodes, renders or prints a payload; the
evidence print carries digests, lengths, ids, tokens and one URL only. The ``.html`` is built
from source in this file — **no binary fixture is committed**.

**TEARDOWN, AND WHAT CANNOT BE TORN DOWN.** The document and the **uploaded file** are deleted
in a ``finally``, and each deletion is **proven by an independent re-query** rather than by the
delete's own ``code:0``. The **media tokens** minted by the attachment arm are *not* deleted and
cannot be: no open-API verb purges drive media, and a ``finally`` that pretended to would be a
lie in the shape of hygiene. They are printed so the residue is recorded rather than implied —
which is exactly the contrast this issue ships: a **file** object is deletable, media is not.

**THE TARGETS ARE ONLY WHAT THIS GATE CREATED.** ``create_document`` is the only way a document
id enters this module, no environment variable naming a document is read, and the standing read
fixture is never addressed. The one thing the gate does **not** create is the destination folder,
because the shipped op creates none either: it is taken from ``LARKDOCIO_TEST_FOLDER`` when that
names one and otherwise from ``LARKDOCIO_DISPOSABLES_FOLDER``, the house-wide folder a human can
open, see and delete. **Configured is not invented, and neither is a default inside the
library**: the op still requires a folder token from its
caller (a test walks the shipped tree to prove no root-folder resolution lives there), and this
gate is the caller. If neither route yields one the gate **skips loudly** rather than guessing a
destination, and the evidence print names which route supplied it (``folder_source``).

**Gentle.** Around a dozen calls, each through the shipped throttles.

**What this gate does NOT prove.** It cannot observe whether a client renders the attachment
card, or what a *mobile* client does with the link — no API call can. What it proves is that the
file exists with a URL, that the bytes round-trip, and that the document reads back carrying the
anchor and the URL.
"""
import time

import pytest

import canary_support
from larkdocio.base.media import sha256_of
from larkdocio.common import get_read_credentials, get_write_credentials
from larkdocio.drive.files_write import DriveFilesWriteClient, put_file_in_folder
from larkdocio.errors import LarkDocIOError
from larkdocio.read.client import Client as ReadClient
from larkdocio.read.config import new_config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    Anchor,
    DocxMediaClient,
    InsertPosition,
    InsertRequest,
    NewBlock,
    TextSpan,
    WriteClient,
    apply,
    dry_run,
    put_file_in_document,
)
from larkdocio.write.client import text_block
from larkdocio.write.media import FILE_BLOCK_TYPE

pytestmark = pytest.mark.live_write
# The live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing the statement
# above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

# The write app's tenant region (the toolkit's default OpenAPI domain). NOT a document URL —
# the gate never addresses a pre-existing doc.
DOMAIN = "larksuite.com"

#: The env var naming the **caller-supplied destination folder**. A folder token is the one
#: input the shipped op refuses to invent, so the gate refuses to invent one either.
FOLDER_ENV = "LARKDOCIO_TEST_FOLDER"

SEED_LINE = "The gate's own anchor line."
ANCHOR_TEXT = "open the attached file"
LEAD_TEXT = "For the full details, "


def html_bytes(stamp):
    """A small textual .html, built from source so no binary fixture is committed."""
    return (
        "<!doctype html><meta charset=\"utf-8\">"
        f"<title>larkdocio attached file {stamp}</title>"
        "<p>An attached file, served as a file rather than rendered in the document."
    ).encode("utf-8")


def _folder_token():
    """The destination, in the one order that keeps the library's own fence true.

    The shipped op **creates no folder**, so this gate creates none either. It takes the
    caller's token from ``LARKDOCIO_TEST_FOLDER`` if one is named, and otherwise from the
    house-wide disposables folder (``LARKDOCIO_DISPOSABLES_FOLDER``). **The fall-back to the
    bot's OWN root folder is gone**: that space has no human interface, so an object uploaded
    there could not be seen or removed by the account holder — which is the whole of the
    caller-supplied-destination rule, applied to our own harness. With neither variable set the
    gate skips loudly rather than inventing a destination.
    """
    import os

    named = (os.environ.get(FOLDER_ENV) or "").strip()
    if named:
        return named, FOLDER_ENV
    house = canary_support.disposables_folder()
    if house:
        return house, canary_support.DISPOSABLES_FOLDER_ENV
    return "", ""


def test_uploaded_file_linked_inline_in_a_sentence(capsys):
    """upload → permalink → an anchored sentence → read back through the reader's Markdown."""
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)
    folder, source = _folder_token()
    if not folder:
        pytest.skip(
            f"neither {FOLDER_ENV} nor {canary_support.DISPOSABLES_FOLDER_ENV} is set — this "
            f"gate uploads into a CALLER-SUPPLIED folder and creates none, so there is no "
            f"destination to use")

    stamp = int(time.time())
    payload = html_bytes(stamp)
    writer = WriteClient(*get_write_credentials(), DOMAIN)
    files = DriveFilesWriteClient.from_write_credentials(DOMAIN)
    media = DocxMediaClient.from_write_credentials(DOMAIN)

    dest_folder = canary_support.require_disposables_folder()
    doc = writer.create_document(title=f"larkdocio-file-link-gate {stamp}",
                                 folder_token=dest_folder)
    doc_id = doc["document_id"]
    evidence = {"doc_id": doc_id, "folder": folder, "folder_source": source,
                "media_residue": []}
    linked = None

    try:
        # A seed paragraph so the insert has a real anchor to point at — the engine resolves
        # a quote, never a raw index.
        writer.create_children(doc_id, doc_id, [text_block(SEED_LINE)], index=0)
        # 1) THE FILE, in the caller's folder, with its URL — one op, hash-verified.
        linked = put_file_in_folder(
            files=files, data=payload, name=f"ld434-attached-file-{stamp}.html",
            folder_token=folder)
        evidence["file_token"] = linked.file_token
        evidence["url"] = linked.url
        evidence["url_class"] = linked.url_class
        evidence["sha256"] = linked.sha256
        assert linked.bytes_verified is True
        assert linked.url, "a file with no URL does not serve 'open the attached file'"

        # 2) AN INDEPENDENT hash check on a second download.
        again = files.download(linked.file_token)
        evidence["redownload_len"] = len(again)
        assert sha256_of(again) == linked.sha256

        # 3) THE SENTENCE, through the plan-gated engine — never a raw call.
        _, tree = _download(doc_id)
        insert = InsertRequest(
            reference=Anchor(quote=SEED_LINE),
            position=InsertPosition.AFTER,
            content=(NewBlock.rich_paragraph((
                TextSpan(LEAD_TEXT),
                TextSpan(ANCHOR_TEXT, link_url=linked.url),
            )),),
        )
        plan = dry_run([insert], tree)
        assert not plan.refusals, f"dry-run refused the anchored sentence: {plan.refusals!r}"
        log = apply(plan, writer, doc_id)
        assert len(log.entries) == 1, log
        evidence["authored"] = list(log.entries[0].created_block_ids)

        # 4) THE VERDICT — a fresh read of the document, through the READER's own Markdown.
        markdown, _ = _download(doc_id)
        evidence["markdown_has_anchor"] = f"[{ANCHOR_TEXT}]({linked.url})" in markdown
        assert LEAD_TEXT.strip() in markdown, markdown[:400]
        assert f"[{ANCHOR_TEXT}]({linked.url})" in markdown, markdown[:400]

        # 5) THE FALLBACK ARM — the 📎 attachment block and its WRAPPER trap, live.
        authored = put_file_in_document(
            client=writer, media=media, document_id=doc_id,
            data=payload, name=f"ld434-attachment-{stamp}.html")
        evidence["media_residue"].append(authored.file_token)
        evidence["attachment_block"] = authored.block_id
        evidence["attachment_wrapper"] = authored.wrapper_block_id
        assert authored.block_id != authored.wrapper_block_id
        block = writer.get_block(doc_id, authored.block_id)
        assert block.get("block_type") == FILE_BLOCK_TYPE, block
        assert (block.get("file") or {}).get("token") == authored.file_token, block

    finally:
        # THE DOCUMENT — deleted, then PROVEN GONE by an independent re-query.
        try:
            writer.delete_document(doc_id)
        except LarkDocIOError as exc:
            evidence["doc_delete"] = f"refused ({exc})"
        evidence["doc_gone"] = _proven_gone(lambda: writer.get_block(doc_id, doc_id))

        # THE FILE — deletable, unlike the media above, and proven the same way.
        if linked is not None:
            try:
                files.delete(linked.file_token)
            except LarkDocIOError as exc:
                evidence["file_delete"] = f"refused ({exc})"
            # MEASURED, and recorded rather than asserted: a deleted file is TRASHED, not
            # purged, and the metadata route STILL RESOLVES a trashed token. So this re-query
            # reports what the route said; it does not claim the object is gone, because that
            # is not what this route can establish.
            evidence["file_after_delete"] = _proven_gone(
                lambda: files.permalink(linked.file_token))

        with capsys.disabled():
            print("\n--- uploaded-file sentence-link gate ---")
            for key, value in evidence.items():
                print(f"  {key}: {value}")
            print("  NOTE: the media tokens above are permanent, unpurgeable residue — the "
                  "FILE object is not, which is the difference this gate exists to show.")


def _download(document_id):
    """Download + parse via the SHIPPED reader: ``(markdown, tree)``.

    The reader is the verdict here, so it is the reader that is run — not a hand-rolled walk
    over the write client's own answer, which would only prove the write echoed itself.
    """
    attempts = []
    if canary_support.read_creds_available():
        attempts.append(get_read_credentials())
    attempts.append(get_write_credentials())

    last_err = None
    for (app_id, app_secret) in attempts:
        try:
            client = ReadClient(app_id, app_secret, DOMAIN)
            docx, blocks = client.get_docx_content(document_id)
            parser = Parser(new_config())
            markdown = parser.parse_docx_content(docx.document_id, blocks)
            tree = parser.parse_docx_tree(docx.document_id, blocks)
            return markdown, tree
        except Exception as e:  # noqa: BLE001 — try the next identity
            last_err = e
    raise last_err


def _proven_gone(probe):
    """An independent re-query — never a delete's own ``code:0``.

    **What it can and cannot settle.** For the document it settles absence: the block read
    refuses. For the **file** it does not, and that is a measured fact rather than a gap in the
    gate — a delete is **trash, not purge**, and the metadata route was observed still
    resolving a trashed token. So the result is *recorded* and never asserted as a purge.
    """
    try:
        probe()
    except Exception as exc:  # noqa: BLE001 - any refusal is the evidence
        return f"gone ({type(exc).__name__})"
    return "STILL RESOLVES"
