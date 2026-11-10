"""THE LIVE GATE for the ONE R3 organize verb — create a folder, use it, take it back.

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` and network).
Run it with the whole ring::

    pytest -m live_write

**The arc is proven END TO END, because each leg alone leaves the ask unserved:** a folder is
created under a parent, the parent is **listed** and the folder found in it by the shipped read
client, a **file is uploaded into it** through the shipped upload op and hash-verified, and then
everything this run made is **deleted** and each deletion followed by an **independent
re-query**. A create verb whose product cannot be listed or written into would be a token, not a
folder.

**THE DUPLICATE-NAME DISCLOSURE IS RE-MEASURED LIVE, not taken on trust from the probe.** The
same name is created twice under the same parent, and the assertion is that TWO folders exist
with byte-identical names and distinct tokens. That is the one behaviour a consumer must plan
around, so the shipped sentence is checked against the live route on every run of this ring
rather than only against a committed capture.

**THE SUBJECT IS ONLY WHAT THIS GATE MADE.** The disposable parent is created by the gate
inside the **human-visible disposables folder** named by ``LARKDOCIO_DISPOSABLES_FOLDER`` — the
one environment variable it reads, and unset it SKIPS LOUDLY; no standing fixture is
addressed, no environment variable naming a document is read, and the canary is
never touched. Everything created here is deleted here.

**THE FOLDER DELETE IS THE GATE'S OWN CALL, ON PURPOSE.** The library ships **no folder-delete
verb** — the 2026-08-14 ruling opened creation and nothing else — so this gate makes that call
itself, as D-12 teardown plumbing, exactly as the chunked-upload gate does. A ``finally`` that
leaned on a library verb which does not exist would be a lie in the shape of hygiene.

**WHAT THE TEARDOWN CAN AND CANNOT SETTLE, recorded rather than asserted.** A trashed **folder**
token **stops resolving** in ``metas/batch_query`` while a trashed **file** token does not
(trash, not purge). Both answers are printed as measured; neither is asserted as a purge.

**BYTES ARE HASHED, NEVER INSPECTED.** The uploaded payload is built from source in this file —
no binary fixture is committed — and the evidence print carries names, tokens, digests, lengths
and one URL only.

**Gentle.** About a dozen calls, each through the shipped throttles.

**What this gate does NOT prove.** Nothing about a name-length ceiling or a folder-count quota
(neither was measured, and a run that hit no limit establishes no absence of one), nothing about
nesting deeper than the one level it makes, and nothing about whether the create succeeds on
READ credentials — the two pairs alias one app on this tenant, so that question is not answerable
here at all rather than merely untried.
"""
import time

import pytest

import canary_support
from larkdocio.base.media import sha256_of
from larkdocio.common import get_write_credentials
from larkdocio.drive.files_write import DriveFilesWriteClient, put_file_in_folder
from larkdocio.drive.folders_write import (
    DUPLICATE_NAME_BEHAVIOUR,
    DriveFolderCreateError,
    DriveFoldersWriteClient,
)
from larkdocio.errors import LarkDocIOError

pytestmark = pytest.mark.live_write
# The live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing the statement
# above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

#: The write app's tenant region (the toolkit's default OpenAPI domain).
DOMAIN = "larksuite.com"


def payload_of(stamp):
    """A small textual payload, built from source so no binary fixture is committed."""
    return (f"larkdocio folder-create gate {stamp}\n"
            f"a file living in a folder this gate made\n").encode("utf-8")


def _disposables_parent():
    """The **human-visible** folder this run creates everything inside.

    It used to be the bot's own root, discovered through the shipped read client. That root is
    the space no human interface can browse — a delete there is a trash nothing can list — so
    the house half of the caller-supplied-destination rule points every harness at a folder the
    account holder can open, see and delete themselves (``LARKDOCIO_DISPOSABLES_FOLDER``).
    Unset ⇒ this gate SKIPS LOUDLY rather than falling back to a place nobody can see.
    """
    return canary_support.require_disposables_folder()


def test_a_folder_is_created_used_and_taken_back(capsys):
    """create → list → upload → delete, plus the duplicate-name behaviour, live."""
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    stamp = int(time.time())
    folders = DriveFoldersWriteClient.from_write_credentials(DOMAIN)
    files = DriveFilesWriteClient.from_write_credentials(DOMAIN)
    name = f"larkdocio-DISPOSABLE-ld467-gate-{stamp}"

    parent = folders.create_folder(f"larkdocio-DISPOSABLE-ld467-parent-{stamp}", _disposables_parent())
    evidence = {"parent": parent.token, "parent_url_is_larks": bool(parent.url),
                "created": [], "residue": []}
    made, linked = [parent.token], None

    try:
        # 1) THE VERB — one folder under the parent, and what the answer actually carries.
        created = folders.create_folder(name, parent.token)
        made.append(created.token)
        evidence["created"].append(created.token)
        assert created.token and created.token != parent.token
        assert created.name == name and created.parent_token == parent.token
        assert created.url and created.token in created.url, (
            "the url must be Lark's own answer about THIS folder")

        # 2) THE DUPLICATE — re-measured live, because it is what a consumer plans around.
        twin = folders.create_folder(name, parent.token)
        made.append(twin.token)
        evidence["created"].append(twin.token)
        assert twin.token != created.token, (
            "the shipped disclosure says a duplicate name makes a SECOND folder; this route "
            "reused the first one, so the disclosure is now WRONG and must be re-measured")
        assert "SECOND FOLDER" in DUPLICATE_NAME_BEHAVIOUR

        # 3) THE LISTING — the parent, read through the SHIPPED read client, is the verdict.
        listed = _children(parent.token)
        evidence["listed_names"] = sorted(child["name"] for child in listed)
        matching = [child for child in listed if child["name"] == name]
        assert len(matching) == 2, (
            f"the parent lists {len(matching)} folders named {name!r}, not the two that were "
            f"created — the duplicate measurement and the listing disagree")
        assert {child["token"] for child in matching} == {created.token, twin.token}
        assert all(child["type"] == "folder" for child in matching), matching

        # 4) A FILE INTO IT — a folder nothing can be written into is not a folder.
        data = payload_of(stamp)
        linked = put_file_in_folder(files=files, data=data,
                                    name=f"ld467-in-the-new-folder-{stamp}.txt",
                                    folder_token=created.token)
        evidence["file_token"] = linked.file_token
        evidence["sha256"] = linked.sha256
        assert linked.bytes_verified is True
        assert sha256_of(data) == linked.sha256

        # 5) THE REFUSALS, live — the created FILE token is not a folder, and the library says
        #    so in its own voice rather than passing Lark's bare code through.
        with pytest.raises(DriveFolderCreateError) as refusal:
            folders.create_folder(f"{name}-under-a-file", linked.file_token)
        evidence["file_as_parent_refusal"] = str(refusal.value)[:120]
        assert "not a folder" in str(refusal.value)

    finally:
        # THE FILE — the shipped delete verb, then an independent re-query whose answer is
        # RECORDED: a trashed file token still resolves (trash, not purge).
        if linked is not None:
            try:
                files.delete(linked.file_token)
            except LarkDocIOError as exc:
                evidence["file_delete"] = f"refused ({exc})"
            evidence["file_after_delete"] = _probe(
                lambda: files.permalink(linked.file_token))

        # THE FOLDERS — the gate's OWN call, because the library ships no folder-delete verb.
        # Children first, then the parent: a delete order that trashed the parent first would
        # leave the two children's own answers unmeasurable.
        for token in reversed(made):
            evidence[f"folder_{token[:8]}_after_delete"] = _delete_folder(token)
        evidence["residue"] = [token for token in made
                              if evidence.get(f"folder_{token[:8]}_after_delete")
                              == "STILL RESOLVES"]

        with capsys.disabled():
            print("\n--- drive folder-create gate (create → list → upload → delete) ---")
            for key, value in evidence.items():
                print(f"  {key}: {value}")
            print("  NOTE: every folder above was created BY THIS RUN inside the disposables folder "
                  "and deleted by this run's own call — the library ships no folder-delete "
                  "verb. Anything left in `residue` is a real leftover and is named, not "
                  "implied. A trashed FOLDER token stops resolving; a trashed FILE token does "
                  "not (trash, not purge) — both are recorded, neither asserted as a purge.")


def _children(folder_token):
    """``[{name, type, token}]`` for a folder's children, via the SHIPPED read client."""
    from larkdocio.drive.client import DriveClient

    app_id, app_secret = get_write_credentials()
    client = DriveClient(app_id, app_secret, DOMAIN)
    contents = client.list_folder_children_to_exhaustion(folder_token)
    return [{"name": child.name, "type": child.type, "token": child.token}
            for child in contents.children]


def _delete_folder(folder_token):
    """Trash one folder this gate made and report what an independent re-query then said.

    The call is the gate's own (``DELETE /drive/v1/files/{token}`` with ``type=folder``) because
    the library ships no folder-delete verb — the ruling opened creation only, and the route
    being measured working is exactly why the absence is a product decision rather than a gap.
    """
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
    """An independent re-query — never a delete's own ``code:0``.

    What it can settle differs by object type, which is why the answer is recorded rather than
    asserted: a trashed FOLDER token stops resolving, a trashed FILE token does not.
    """
    try:
        probe()
    except Exception as exc:  # noqa: BLE001 - any refusal is the evidence
        return f"gone ({type(exc).__name__})"
    return "STILL RESOLVES"
