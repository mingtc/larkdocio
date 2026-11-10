"""THE LIVE GATE for LD-474 — the folder-ledger truths, measured instead of believed.

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` and network).
Run it with the whole ring::

    pytest -m live_write

**It exists because a shipped sentence was confident, precise and WRONG.** Until this issue the
folder read skipped every raw ``file`` child saying the bytes leg *"is not shipped"*. It ships.
So the disproof is a gate rather than a paragraph: this run **skips a file through the shipped
folder read and then downloads that very token's bytes through the shipped download op**, and
hash-matches them against what it uploaded. A sentence that says a leg is absent must fail a
test the day the leg exists.

**Four measurements, all of them things the shipped guide now states:**

1. **THE DISPROOF** — ``read_folder`` skips a raw file; ``DriveFilesWriteClient.download`` then
   returns that same token's bytes, sha256-identical to the upload. The skip reason is asserted
   to NAME the verb, because a consumer reads the reason and stops there.
2. **THE LEDGER FIELDS** — what a ``folder_manifest`` row actually carries per child, measured
   key by key rather than copied from a report: which of ``created_time`` / ``modified_time`` /
   ``owner_id`` come back populated, whether a ``revision`` is available, and that **no** size,
   digest, etag or content-hash key exists anywhere in a row.
3. **THE CHANGE DETECTOR** — a document's ``revision_id`` before and after one real edit, plus a
   second read with no edit between, so *moves on a write* and *inert under polling* are both
   measured on the same document in the same run.
4. **THE CLASSIFICATION ROUTE** — a document's tenant security level, taken **through the
   shipped op** (``DriveClient.document_security_level``) rather than through a hand-rolled
   call, so what is measured is the product a consumer runs. It rides ``metas/batch_query``, a
   documented open-API route, which is why the guide may not call a per-document fetch
   impossible. The disposable is one nobody classified, so the answer must be the measured
   *empty means NO LEVEL SET* case — a level appearing there would mean that reading, not the
   route, needs re-measuring.

**THE SUBJECT IS ONLY WHAT THIS GATE MADE.** The folder is created by this gate inside the
human-visible disposables folder (``LARKDOCIO_DISPOSABLES_FOLDER``); the document and the
uploaded file are made inside it. No standing fixture is addressed, no environment variable naming an object is
read, and the canary is never touched.

**BYTES ARE HASHED, NEVER INSPECTED.** The payload is built from source in this file — no binary
fixture is committed — and the evidence print carries names, tokens, digests and lengths only.

**Teardown, and what it can and cannot settle.** Everything made here is deleted here, each
deletion followed by an **independent re-query** whose answer is recorded rather than asserted
as a purge (a trashed folder token stops resolving; a trashed file token does not). The folder
delete is the gate's OWN call because the library ships no folder-delete verb. **Named residue:
the uploaded file's bytes are drive media only in the FOLDER sense — a folder file CAN be
deleted, and is.**

**Gentle.** Under two dozen calls, each through the shipped throttles.

**What this gate does NOT prove.** Nothing about non-text uploads (only a ``.txt`` goes up),
nothing about whether ``sec_label_name`` is settable (no write is attempted at it anywhere), and
nothing about a revision's behaviour under a concurrent writer.
"""
import time

import canary_support
import pytest

from larkdocio.base.media import sha256_of
from larkdocio.common import get_write_credentials
from larkdocio.drive import folder_manifest, read_folder
from larkdocio.drive.client import DriveClient
from larkdocio.drive.files_write import DriveFilesWriteClient, put_file_in_folder
from larkdocio.drive.folders_write import DriveFoldersWriteClient
from larkdocio.errors import LarkDocIOError
from larkdocio.write.client import WriteClient, text_block

pytestmark = pytest.mark.live_write
# The live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing the statement
# above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

#: The write app's tenant region (the toolkit's default OpenAPI domain).
DOMAIN = "larksuite.com"

#: The identity keys a ledger would want on a child row but which the listing does not carry.
#: Asserted ABSENT, so the guide's "what you cannot build on" list cannot drift into fiction.
ABSENT_IDENTITY_KEYS = ("size", "digest", "sha256", "etag", "checksum", "content_hash", "md5")


def payload_of(stamp):
    """A small textual payload, built from source so no binary fixture is committed."""
    return (f"larkdocio bytes-leg gate {stamp}\n"
            f"the bytes a skip reason once said were unreachable\n").encode("utf-8")


def _disposables_parent():
    """The **human-visible** folder this run creates everything inside.

    It used to be the bot's own root, discovered through the shipped read client. That root is
    the space no human interface can browse — a delete there is a trash nothing can list — so
    the house half of the caller-supplied-destination rule points every harness at a folder the
    account holder can open, see and delete themselves (``LARKDOCIO_DISPOSABLES_FOLDER``).
    Unset ⇒ this gate SKIPS LOUDLY rather than falling back to a place nobody can see.
    """
    return canary_support.require_disposables_folder()


def test_a_skipped_files_bytes_ARE_fetchable_and_the_ledger_fields_are_measured(capsys):
    """The whole LD-474 evidence set, in one arc against one disposable folder."""
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    stamp = int(time.time())
    app_id, app_secret = get_write_credentials()
    folders = DriveFoldersWriteClient.from_write_credentials(DOMAIN)
    files = DriveFilesWriteClient.from_write_credentials(DOMAIN)
    writer = WriteClient(app_id, app_secret, DOMAIN)

    folder = folders.create_folder(f"larkdocio-DISPOSABLE-ld474-{stamp}", _disposables_parent())
    evidence = {"folder": folder.token, "residue": []}
    doc_id, uploaded = None, None

    try:
        # 1) A DOCUMENT in the folder — the revision anchor's subject, and a child the walk
        #    actually reads.
        doc_id = writer.create_document(
            title=f"larkdocio-DISPOSABLE-ld474-doc-{stamp}", folder_token=folder.token
        )["document_id"]
        evidence["doc"] = doc_id

        # 2) A RAW FILE in the same folder — the child the folder read skips.
        data = payload_of(stamp)
        uploaded = put_file_in_folder(files=files, data=data,
                                      name=f"ld474-raw-{stamp}.txt",
                                      folder_token=folder.token)
        evidence["file_token"] = uploaded.file_token
        evidence["uploaded_sha256"] = uploaded.sha256
        assert uploaded.sha256 == sha256_of(data)

        # 3) THE FOLDER READ — through the shipped op, on a client built the way the guide now
        #    shows (client= is how you choose the credential pair; the default is the READ one).
        result = read_folder(folder.token,
                             client=DriveClient(app_id, app_secret, DOMAIN))
        assert result.accounted()
        skipped = [child for child in result.skips
                   if child.child.token == uploaded.file_token]
        assert len(skipped) == 1, (
            f"the uploaded file is not among the walk's skips: "
            f"{[child.child.token for child in result.skips]}")
        skip_reason = skipped[0].skip.reason
        evidence["skip_reason"] = skip_reason

        # THE DISPROOF, part one: the reason a consumer reads must NAME the verb that works.
        assert "DriveFilesWriteClient.download" in skip_reason, (
            "the skip reason does not name the verb that fetches the bytes — this is the "
            "defect LD-474 exists to fix, and it cost a real run its job")
        assert "is not shipped" not in skip_reason, (
            "the skip reason still claims the bytes leg is absent; it ships, and this gate "
            "downloads it three lines below")

        # THE DISPROOF, part two: the bytes themselves, on the very token that was skipped.
        fetched = files.download(uploaded.file_token)
        evidence["downloaded_len"] = len(fetched)
        evidence["downloaded_sha256"] = sha256_of(fetched)
        assert sha256_of(fetched) == uploaded.sha256, (
            "the skipped child's bytes did not round-trip")

        # 4) THE LEDGER FIELDS — measured per key, never copied from a report.
        manifest = folder_manifest(result)
        rows = {row["token"]: row for row in manifest["children"]}
        file_row, doc_row = rows[uploaded.file_token], rows[doc_id]
        evidence["listing_fields_populated"] = {
            key: sorted(name for name, row in (("file", file_row), ("doc", doc_row))
                        if row.get(key))
            for key in ("created_time", "modified_time", "owner_id", "url")
        }
        # The SHAPE of the timestamp decides what a ledger may conclude from it, so it is
        # recorded rather than described: Lark's own string, verbatim, for both child kinds.
        evidence["timestamp_shape"] = {
            kind: {"created_time": row.get("created_time"),
                   "modified_time": row.get("modified_time")}
            for kind, row in (("file", file_row), ("doc", doc_row))
        }
        evidence["revision_availability"] = {
            "file": file_row["revision"]["availability"],
            "doc": doc_row["revision"]["availability"],
        }
        evidence["doc_revision_in_manifest"] = doc_row["revision"]["value"]
        for row in (file_row, doc_row):
            for key in ABSENT_IDENTITY_KEYS:
                assert key not in row, (
                    f"a {key!r} key appeared on a manifest row — the guide's "
                    f"'what you cannot build on' list is now wrong and must be re-measured")

        # 5) THE CHANGE DETECTOR — one edit moves it; a second read with no edit does not.
        before = writer.read_document_revision(doc_id)
        writer.create_children(doc_id, doc_id,
                               [text_block(f"ld474 change-detector line {stamp}")], index=0)
        after = writer.read_document_revision(doc_id)
        again = writer.read_document_revision(doc_id)
        evidence["revision_before_edit"] = before
        evidence["revision_after_edit"] = after
        evidence["revision_polled_again"] = again
        assert after > before, (
            "one block insert did not advance revision_id — the change-detector recipe's "
            "central claim is now false and must be re-measured")
        assert again == after, "a read moved the revision; polling it is NOT inert"

        # 6) THE CLASSIFICATION ROUTE — through the SHIPPED OP, so this measures the product.
        #    Until 1.36 this leg hand-rolled the call, because the library surfaced the field
        #    for nothing; it ships now, and a gate that kept hand-rolling would prove the route
        #    while leaving the shipped leg unmeasured.
        answer = DriveClient(app_id, app_secret, DOMAIN).document_security_level(doc_id)
        evidence["sec_label_name_key_present"] = answer.reported
        evidence["sec_label_name_value"] = repr(answer.level)
        evidence["sec_label_name_outcome"] = answer.outcome
        evidence["sec_label_name_disclosure"] = answer.disclosure
        assert answer.reported, (
            "the shipped document_security_level leg could not answer for a document it just "
            f"created — the guide's classification section says it can: {answer.disclosure}")
        # '' means NO LEVEL SET (a before-control + a negative control established that), so a
        # disposable nobody classified must read exactly that. A level appearing here would
        # mean the reading itself needs re-measuring.
        assert answer.outcome == "no-level-set", (
            f"a disposable created seconds ago reported a security level ({answer.level!r}) — "
            "the empty-means-no-level reading must be re-measured before the guide keeps it")

    finally:
        if doc_id is not None:
            evidence["doc_after_delete"] = _teardown(
                lambda: writer.delete_document(doc_id),
                lambda: writer.get_document(doc_id))
        if uploaded is not None:
            evidence["file_after_delete"] = _teardown(
                lambda: files.delete(uploaded.file_token),
                lambda: files.permalink(uploaded.file_token))
        evidence["folder_after_delete"] = _delete_folder(folder.token)
        evidence["residue"] = [name for name in ("doc_after_delete", "folder_after_delete")
                               if evidence.get(name) == "STILL RESOLVES"]

        with capsys.disabled():
            print("\n--- LD-474 drive bytes-leg gate (skip → download → ledger → revision) ---")
            for key, value in evidence.items():
                print(f"  {key}: {value}")
            print("  NOTE: every object above was created BY THIS RUN inside the disposables folder "
                  "and deleted by this run. Anything in `residue` "
                  "is a real leftover and is named, not implied. "
                  "A trashed FILE token still resolves (trash, not purge) "
                  "and that is recorded, never asserted as a purge.")


def _teardown(delete, probe):
    """Delete through the SHIPPED verb, then report what an independent re-query said."""
    try:
        delete()
    except LarkDocIOError as exc:
        return f"delete refused ({exc})"
    except Exception as exc:  # noqa: BLE001 - the re-query below is the evidence either way
        return f"delete raised ({type(exc).__name__})"
    return _probe(probe)


def _delete_folder(folder_token):
    """Trash the folder this gate made — the gate's OWN call, because the library ships no
    folder-delete verb (the 2026-08-14 ruling opened creation and nothing else)."""
    from lark_oapi.api.drive.v1 import DeleteFileRequest

    import lark_oapi as lark

    app_id, app_secret = get_write_credentials()
    sdk = lark.Client.builder().app_id(app_id).app_secret(app_secret) \
        .domain(f"https://open.{DOMAIN}").log_level(lark.LogLevel.ERROR).build()
    try:
        sdk.drive.v1.file.delete(
            DeleteFileRequest.builder().file_token(folder_token).type("folder").build())
    except Exception as exc:  # noqa: BLE001 - the re-query below is the evidence either way
        return f"delete raised ({type(exc).__name__})"
    files = DriveFilesWriteClient.from_write_credentials(DOMAIN)
    return _probe(lambda: files.permalink(folder_token))


def _probe(probe):
    """An independent re-query — never a delete's own ``code:0``."""
    try:
        probe()
    except Exception as exc:  # noqa: BLE001 - any refusal is the evidence
        return f"gone ({type(exc).__name__})"
    return "STILL RESOLVES"
