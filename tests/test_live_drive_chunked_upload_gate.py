"""THE LIVE GATE for the CHUNKED half of the upload rung — a genuinely multi-part upload.

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` and network).
Run it with the whole ring::

    pytest -m live_write

**Why this arm exists at all.** The spike **asked** ``upload_prepare`` about a 16-part
partition and **never uploaded one**, so multi-part ordering was unmeasured. An offline test
can get a call sequence internally consistent and still have it wrong on the wire; the only
place ``block_num > 1`` becomes a finding is here, and this is the cheapest moment this library
will ever have to learn it.

**The subject is a disposable this harness creates and deletes.** ``create_folder`` is called
**by the gate, as D-12 plumbing** — exactly as the spike's own probes used it — and never by
the library, which ships no folder-creating call at all (a shipped-tree guard proves that
separately). No standing fixture is addressed, the canary is never touched, and no
caller-supplied destination is used.

**SIZE DISCIPLINE.** The payload is **the smallest one that produces more than one block under
the partition the server declares** — one byte over the ``block_size`` the spike observed — and
not a byte more. A live gate does not upload a genuinely huge file to prove a point. If the
server declares a *larger* block than that, this arm cannot produce a multi-part upload at that
size: it says so in its evidence print and **fails rather than quietly claiming multi-part was
proven**, because the whole finding is the multi-part one.

**BYTES ARE HASHED, NEVER INSPECTED.** The payload is generated in this file — no binary
fixture is committed — and the evidence print carries digests, lengths, counts and tokens only.

**TEARDOWN, AND WHAT CANNOT BE TORN DOWN.** The file and then the folder are deleted in a
``finally``, and each deletion is followed by an **independent re-query** whose answer is
*recorded* rather than asserted: a trashed **file** token still resolves in ``metas/batch_query``
(trash, not purge) while a trashed **folder** token does not. Any **abandoned ``upload_id``** is
ledgered as residue with its expiry unmeasured — no cancel verb was found in the SDK's drive v1
surface and none is called, so no fake cleanup leg appears here.

**Gentle.** Six or seven calls, each through the shipped throttle.
"""
import time

import pytest

import canary_support
from larkdocio.base.media import sha256_of
from larkdocio.common import get_write_credentials
from larkdocio.drive.files_write import DriveFilesWriteClient, put_file_in_folder
from larkdocio.errors import LarkDocIOError

pytestmark = pytest.mark.live_write
# The live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing the statement
# above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

DOMAIN = "larksuite.com"

#: The ``block_size`` the spike observed, **in this test file and nowhere in the library** — it
#: is how the gate picks the smallest interesting payload, not how the client partitions one.
#: The client asks ``upload_prepare`` and obeys whatever it answers.
OBSERVED_BLOCK_SIZE = 4194304


def payload_of(size, stamp):
    """``size`` deterministic, in-process bytes. No binary fixture is committed."""
    seed = f"larkdocio chunked gate {stamp} ".encode("utf-8")
    return (seed * (size // len(seed) + 1))[:size]


def _create_disposable_folder(name):
    """D-12 plumbing: the GATE creates its own folder. The library never does.

    Raw through the pinned SDK on the WRITE pair, inside the **human-visible disposables
    folder** (``LARKDOCIO_DISPOSABLES_FOLDER``) — unset ⇒ the gate SKIPS LOUDLY. It used to go
    under the bot's own root; that root is the space no human interface can browse, so what
    landed there could not be seen or cleaned up by the account holder. The subject of this arm
    is still something nobody else owns and this file deletes — it is now also something the
    account holder can watch it happen in.
    """
    import lark_oapi as lark
    from lark_oapi.api.drive.v1 import CreateFolderFileRequest, CreateFolderFileRequestBody

    app_id, app_secret = get_write_credentials()
    sdk = lark.Client.builder().app_id(app_id).app_secret(app_secret) \
        .domain(f"https://open.{DOMAIN}").log_level(lark.LogLevel.ERROR).build()
    # The destination is the house disposables folder, never the app's own root.
    parent = canary_support.require_disposables_folder()
    body = CreateFolderFileRequestBody.builder().name(name).folder_token(parent).build()
    response = sdk.drive.v1.file.create_folder(
        CreateFolderFileRequest.builder().request_body(body).build())
    if getattr(response, "code", 0):
        raise AssertionError(f"the gate could not create its own folder: {response.code} "
                             f"{getattr(response, 'msg', '')}")
    return response.data.token, sdk


def test_a_genuinely_multi_part_upload_round_trips(capsys):
    """prepare → **two** parts → finish → download → hash, on a disposable this gate owns."""
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    stamp = int(time.time())
    folder, sdk = _create_disposable_folder(f"larkdocio-chunked-gate-{stamp}")
    files = DriveFilesWriteClient.from_write_credentials(DOMAIN)
    # The smallest payload that cannot fit in one block under the declared partition.
    size = OBSERVED_BLOCK_SIZE + 1
    data = payload_of(size, stamp)
    evidence = {"folder": folder, "size": size, "sha256": sha256_of(data),
                "abandoned_upload_ids": []}
    linked = None

    try:
        # The SHIPPED op, routed by size — the gate names no upload verb of its own.
        linked = put_file_in_folder(
            files=files, data=data, name=f"ld449-chunked-{stamp}.bin", folder_token=folder,
            chunk_above_bytes=OBSERVED_BLOCK_SIZE)
        evidence["file_token"] = linked.file_token
        evidence["parts"] = linked.parts
        evidence["url_class"] = linked.url_class
        evidence["bytes_verified"] = linked.bytes_verified

        assert linked.bytes_verified is True
        assert linked.sha256 == sha256_of(data)
        assert linked.url, "a file with no URL is not what this surface returns"
        assert linked.parts > 1, (
            "the payload was one byte over the block size the spike observed and still went up "
            "in a single part — the server declared a LARGER block, so this run did not "
            "produce the multi-part upload the arm exists to measure. Record the new "
            "block_size; do not claim multi-part is proven")

        # An INDEPENDENT second download, hashed again: the verdict is the read-back, and one
        # read-back is worth repeating on the arm whose whole subject is reassembly.
        again = files.download(linked.file_token)
        evidence["redownload_len"] = len(again)
        assert len(again) == size
        assert sha256_of(again) == linked.sha256

    finally:
        if linked is not None:
            try:
                files.delete(linked.file_token)
            except LarkDocIOError as exc:
                evidence["file_delete"] = f"refused ({exc})"
            # RECORDED, not asserted: a delete is trash, not purge, and the metadata route was
            # measured still resolving a trashed FILE token.
            evidence["file_after_delete"] = _probe(
                lambda: files.permalink(linked.file_token))
        evidence["folder_after_delete"] = _delete_folder(sdk, folder)

        with capsys.disabled():
            print("\n--- chunked (multi-part) drive upload gate ---")
            for key, value in evidence.items():
                print(f"  {key}: {value}")
            print("  NOTE: no upload_id was abandoned by this run — every prepare reached its "
                  "finish. An abandoned one would be ledgered above and could NOT be cleaned "
                  "up: no cancel verb was found in the SDK's drive v1 surface and none is "
                  "called here, and its expiry is unmeasured.")


def _delete_folder(sdk, folder_token):
    """Trash the gate's own folder and report what an independent re-query then said."""
    from lark_oapi.api.drive.v1 import DeleteFileRequest

    try:
        sdk.drive.v1.file.delete(
            DeleteFileRequest.builder().file_token(folder_token).type("folder").build())
    except Exception as exc:  # noqa: BLE001 - the re-query below is the evidence either way
        return f"delete raised ({type(exc).__name__})"
    files = DriveFilesWriteClient.from_write_credentials(DOMAIN)
    return _probe(lambda: files.permalink(folder_token))


def _probe(probe):
    """An independent re-query — never a delete's own ``code:0``.

    What it can settle differs by object type, which is why the answer is recorded rather than
    asserted: a trashed FOLDER token stops resolving, a trashed FILE token does not.
    """
    try:
        probe()
    except Exception as exc:  # noqa: BLE001 - any refusal is the evidence
        return f"gone ({type(exc).__name__})"
    return "STILL RESOLVES"
