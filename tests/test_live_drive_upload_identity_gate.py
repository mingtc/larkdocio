"""THE LIVE GATE for upload identity and gone-ness — upload, look, upload again, delete twice.

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` and network).
Run it with the whole ring::

    pytest -m live_write

**The arc is proven END TO END, because each leg alone leaves the ask unserved:** a file is
uploaded into a folder this gate made, the **by-name lookup finds it**, the **identical file is
uploaded again** and the lookup then shows **two children with byte-identical names and distinct
tokens** — which is the moment a caller would have skipped — and then the file is deleted and
**deleted again**, the second delete answering *already gone* rather than *still there*.

**THE DUPLICATE BEHAVIOUR IS RE-MEASURED LIVE, not taken on trust from the probe.** The shipped
disclosure says a second upload of the same name makes a second object; this gate sends that
second upload on every run and asserts the tokens differ. If Lark ever starts de-duplicating,
the shipped sentence becomes wrong and this is where that is found out.

**THE SECOND DELETE IS THE POINT, AND SO IS WHAT IT DOES NOT PROVE.** The refusal must be
readable through the shipped predicate rather than by matching a string, and the honest answer
has two halves: the token leaves the folder listing, **and** the metadata route keeps resolving
it. Both are recorded here; neither is asserted as a purge.

**THE SUBJECT IS ONLY WHAT THIS GATE MADE.** The disposable folder is created by the gate
inside the **human-visible disposables folder** named by ``LARKDOCIO_DISPOSABLES_FOLDER`` — the
one environment variable it reads, and unset it SKIPS LOUDLY; no standing fixture is
addressed, no environment variable naming a document is read, and the canary is
never touched. Everything created here is deleted here, and anything that survives is **named**.

**THE FOLDER DELETE IS THE GATE'S OWN CALL, ON PURPOSE.** The library ships no folder-delete
verb, so this gate makes that call itself as teardown plumbing — a ``finally`` that leaned on a
library verb which does not exist would be a lie in the shape of hygiene.

**BYTES ARE HASHED, NEVER INSPECTED.** The payload is built from source in this file — no binary
fixture is committed — and the evidence print carries names, tokens, digests and counts only.

**Gentle.** About a dozen calls, each through the shipped throttles.

**What this gate does NOT prove.** Nothing about any overwrite spelling other than the eight the
probe tried (they are captured, not re-sent here — re-sending eight ignored parameters every run
would be noise), nothing about ``user_access_token``, other tenants or other regions, and
nothing about whether the lookup or the upload succeeds on READ credentials — the two pairs
alias one app on this tenant, so that question is not answerable here at all rather than merely
untried.
"""
import time

import pytest

import canary_support
from larkdocio.base.media import sha256_of
from larkdocio.common import get_write_credentials
from larkdocio.drive.files_write import (
    DriveFileDeleteError,
    DriveFilesWriteClient,
    file_is_gone,
    put_file_in_folder,
)
from larkdocio.drive.folders_write import DriveFoldersWriteClient
from larkdocio.drive.lookup import DUPLICATE_UPLOAD_BEHAVIOUR
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
    return (f"larkdocio upload-identity gate {stamp}\n"
            f"the same bytes, uploaded twice on purpose\n").encode("utf-8")


def _disposables_parent():
    """The **human-visible** folder this run creates everything inside.

    It used to be the bot's own root, discovered through the shipped read client. That root is
    the space no human interface can browse — a delete there is a trash nothing can list — so
    the house half of the caller-supplied-destination rule points every harness at a folder the
    account holder can open, see and delete themselves (``LARKDOCIO_DISPOSABLES_FOLDER``).
    Unset ⇒ this gate SKIPS LOUDLY rather than falling back to a place nobody can see.
    """
    return canary_support.require_disposables_folder()


def _reader():
    """The shipped read client, built on the pair that owns the destination.

    On this tenant the two credential pairs alias one app; the gate still asks for the WRITE
    pair explicitly, because the folder it is looking into is one the WRITE app made and the
    library never crosses the pairs on a caller's behalf.
    """
    from larkdocio.drive.client import DriveClient

    app_id, app_secret = get_write_credentials()
    return DriveClient(app_id, app_secret, DOMAIN)


def test_upload_look_upload_again_and_delete_twice(capsys):
    """upload → lookup finds it → identical re-upload → lookup shows TWO → delete → delete."""
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    stamp = int(time.time())
    folders = DriveFoldersWriteClient.from_write_credentials(DOMAIN)
    files = DriveFilesWriteClient.from_write_credentials(DOMAIN)
    name = f"ld464-the-same-name-{stamp}.txt"

    parent = folders.create_folder(f"larkdocio-DISPOSABLE-ld464-{stamp}", _disposables_parent())
    evidence = {"folder": parent.token, "uploaded": [], "residue": []}
    uploaded = []

    try:
        data = payload_of(stamp)

        # 1) THE FIRST UPLOAD — the shipped op, hash-verified.
        first = put_file_in_folder(files=files, data=data, name=name,
                                   folder_token=parent.token)
        uploaded.append(first.file_token)
        evidence["uploaded"].append(first.file_token)
        assert first.bytes_verified is True and first.sha256 == sha256_of(data)

        # 2) THE LOOKUP FINDS IT — this is the call that did not exist before.
        found = _reader().find_children_by_name(parent.token, name)
        evidence["lookup_1"] = (found.found, found.tokens, found.complete)
        assert found.found is True and found.complete is True
        assert found.tokens == (first.file_token,), found.tokens

        # 3) THE IDENTICAL RE-UPLOAD — re-measured live, because it is what a consumer plans
        #    around. A second object, not a replacement.
        second = put_file_in_folder(files=files, data=data, name=name,
                                    folder_token=parent.token)
        uploaded.append(second.file_token)
        evidence["uploaded"].append(second.file_token)
        assert second.file_token != first.file_token, (
            "the shipped disclosure says a second upload of the same name makes a SECOND "
            "object; this route replaced the first one, so the disclosure is now WRONG and "
            "must be re-measured")
        assert second.sha256 == first.sha256, "identical bytes, so identical digests"
        assert "no overwrite" in DUPLICATE_UPLOAD_BEHAVIOUR

        # 4) …AND THE LOOKUP WOULD HAVE LET THE CALLER SKIP: two children, one name.
        again = _reader().find_children_by_name(parent.token, name)
        evidence["lookup_2"] = (again.found, len(again.tokens), again.complete)
        evidence["lookup_2_sentence"] = again.describe()[:160]
        assert set(again.tokens) == {first.file_token, second.file_token}, again.tokens
        assert again.complete is True

        # 5) A NAME THAT IS NOT THERE IS AN EMPTY ANSWER, not a refusal — the skip-nothing arm.
        absent = _reader().find_children_by_name(parent.token, f"{name}.absent")
        evidence["lookup_absent"] = (absent.found, absent.listed, absent.complete)
        assert absent.found is False and absent.listed >= 2 and absent.complete is True

        # 6) DELETE, THEN DELETE AGAIN — the second answers ALREADY GONE, not "still there".
        files.delete(first.file_token)
        with pytest.raises(DriveFileDeleteError) as refusal:
            files.delete(first.file_token)
        uploaded.remove(first.file_token)
        evidence["second_delete_is_gone"] = file_is_gone(refusal.value)
        evidence["second_delete_says"] = str(refusal.value)[:160]
        assert file_is_gone(refusal.value) is True, (
            "a delete of an already-deleted token must read as ALREADY GONE through the "
            "shipped predicate, not as a bare refusal")
        assert "still there" not in str(refusal.value)

        # 7) …AND THE OTHER HALF, RECORDED RATHER THAN ASSERTED: the token left the folder
        #    listing, while the metadata route may well keep answering for it.
        after = _reader().find_children_by_name(parent.token, name)
        evidence["listed_after_delete"] = after.tokens
        assert first.file_token not in after.tokens, (
            "a deleted file must leave the folder listing — that is the half of gone-ness "
            "this library does claim")
        evidence["metadata_after_delete"] = _probe(
            lambda: files.permalink(first.file_token))

    finally:
        for token in list(uploaded):
            try:
                files.delete(token)
            except LarkDocIOError as exc:
                if not file_is_gone(exc):
                    evidence[f"file_{token[:8]}_delete"] = f"refused ({exc})"
                    evidence["residue"].append(token)

        evidence["folder_after_delete"] = _delete_folder(parent.token)
        if evidence["folder_after_delete"] == "STILL RESOLVES":
            evidence["residue"].append(parent.token)

        with capsys.disabled():
            print("\n--- drive upload-identity gate (upload → look → re-upload → delete×2) ---")
            for key, value in evidence.items():
                print(f"  {key}: {value}")
            print("  NOTE: every object above was created BY THIS RUN in a folder this run made "
                  "inside the configured disposables folder, and deleted by this run. Anything in `residue` "
                  "is a real leftover and is named, not implied. Gone-ness is recorded with BOTH of "
                  "its measured halves: the token leaves the folder listing, and the metadata "
                  "route may keep resolving it — trash, not purge, and neither half is asserted "
                  "as one.")


def _delete_folder(folder_token):
    """Trash the folder this gate made and report what an independent re-query then said.

    The call is the gate's own because the library ships no folder-delete verb.
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
