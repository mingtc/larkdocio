"""THE LIVE GATE for *who can read a document the app just created* — the folder case.

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` and network).
Run it by name::

    pytest tests/test_live_docx_folder_acl_gate.py -m live_write

**Why this gate exists.** The shipped guide carried an **unconditional** sentence — *a fresh
docx is a document only the app can use; its member read answers* ``items: []`` — and dogfood
round 4 measured that sentence FALSE for the case a consumer actually runs: a docx created
**into a folder** comes back carrying the folder's own member rows, each one
``perm_type='container'``. A confident wrong sentence about who can read a document is the
defect class this gate is pointed at, so the claim the guide ships is **re-measured here**
rather than transcribed from a round-4 note (LD-469 AC3).

**The three subjects, and why all three are needed.**

1. **The CONTROL** — a document created with **no** ``folder_token``. **This arm no longer
   runs, and it cannot: the caller-supplied-destination rule makes a destination-less create a
   local refusal, so the library can no longer produce the subject this arm measured.** Its
   finding is PRESERVED rather than deleted — the round-4 measurement was *a document created
   with no folder came back with an empty member list* — and the arm is replaced by the
   refusal check below, which proves the case is now unreachable instead of re-measuring it.
   The reason the control existed (a baseline for "the folder case is different") is met by
   that preserved finding; the reason it is gone is that creating an object nobody can see is
   exactly what the rule removed.
2. **The FOLDER-FILED document** — the same call plus ``folder_token=``, into a folder this run
   made. Its member list is the subject.
3. **The FOLDER ITSELF** — read through the same members route. Inheritance is a claim about
   *whose* rows those are, and only the parent's own list can settle it. The library ships no
   member read for a folder (``folder`` is refused by name as unmeasured — that fence is
   LD-456's and this gate does not move it), so this leg is the **gate's own raw call**, exactly
   as the folder delete below is.

**THE SUBJECT IS ONLY WHAT THIS GATE MADE.** The parent folder is created by this run inside the
**human-visible disposables folder** named by ``LARKDOCIO_DISPOSABLES_FOLDER`` — unset, the gate
SKIPS LOUDLY rather than falling back to the bot's own root, which is the house half of the
caller-supplied-destination rule; the document is created by this run; no standing fixture is
addressed, no document-naming environment variable is read, and the canary is never touched. Everything created here is deleted here, in a
``finally``, and each deletion is followed by an **independent re-query**.

**THE FOLDER DELETE IS THE GATE'S OWN CALL, ON PURPOSE.** The library ships no folder-delete
verb (the 2026-08-14 ruling opened creation and nothing else), so this gate makes that call
itself as D-12 teardown plumbing — the same posture as the folder-create gate.

**MEMBER IDS ARE ABBREVIATED IN THE EVIDENCE PRINT.** An inherited row names a real person or a
real chat in the tenant, which the run did not create and cannot delete; the print carries each
row's ``member_type`` / ``perm`` / ``perm_type`` **in full** — those are the load-bearing fields
— and the id truncated to its first 12 characters. Nothing is asserted on the truncation.

**Gentle.** Roughly a dozen calls, each through the shipped throttles.

**What this gate does NOT prove.** Nothing about what a human can then *do* with the document
(no endpoint reachable with a tenant token reports that — see the guide's grant-access recipe);
nothing about object types other than ``docx``; nothing about a **shared** folder, because this
run's folder is one it made and it can only report the rows that folder actually carries — where
the parent's list is empty the child's is the same empty list, which is inheritance answering
honestly rather than the absolute the guide used to ship; and nothing about wiki-wrapped nodes.
"""
import time

import pytest

import canary_support
from larkdocio.common import get_write_credentials
from larkdocio.drive.access_write import DriveAccessWriteClient
from larkdocio.drive.folders_write import DriveFoldersWriteClient
from larkdocio.errors import LarkDocIOError, MissingDestinationError
from larkdocio.write import WriteClient

pytestmark = pytest.mark.live_write
# The live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing the statement
# above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

#: The write app's tenant region (the toolkit's default OpenAPI domain).
DOMAIN = "larksuite.com"


def _disposables_parent():
    """The human-visible folder this run puts everything it creates in.

    It used to be the bot's own root, discovered through the shipped read client. That root is
    the space no human interface can browse, so the house half of the caller-supplied-destination
    rule points every harness at a folder the account holder can open, see and delete
    (``LARKDOCIO_DISPOSABLES_FOLDER``). Unset ⇒ this gate SKIPS LOUDLY.
    """
    return canary_support.require_disposables_folder()


def _rows(listing):
    """One printable dict per member row — the three fields, plus an abbreviated id."""
    return [{"member_type": m.member_type, "perm": m.perm, "perm_type": m.perm_type,
             "member_id_prefix": (m.member_id or "")[:12]} for m in listing.members]


def test_who_can_read_a_document_the_app_just_created(capsys):
    """the destination-less create REFUSED, the folder-filed document measured, the parent beside it."""
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    stamp = int(time.time())
    folders = DriveFoldersWriteClient.from_write_credentials(DOMAIN)
    writer = WriteClient(*get_write_credentials(), DOMAIN)
    access = DriveAccessWriteClient.from_write_credentials(DOMAIN)

    folder = folders.create_folder(f"larkdocio-DISPOSABLE-ld469-{stamp}", _disposables_parent())
    evidence = {"folder": folder.token, "residue": []}
    filed_id = None

    try:
        # 1) THE CONTROL, AS IT NOW EXISTS — the destination-less create is a LOCAL REFUSAL,
        #    so the baseline is proved unreachable instead of re-created. Zero calls, zero
        #    objects: this is the arm that shows the rule holds on the live path too.
        with pytest.raises(MissingDestinationError) as refused:
            writer.create_document(title=f"larkdocio-DISPOSABLE-ld469-control-{stamp}",
                                   folder_token="")
        evidence["control_refusal"] = str(refused.value)
        evidence["control_doc"] = "NOT CREATED — the rule refuses a destination-less create"

        # 2) THE FOLDER CASE — the same call plus the argument that decides where it lands.
        filed = writer.create_document(title=f"larkdocio-DISPOSABLE-ld469-filed-{stamp}",
                                       folder_token=folder.token)
        filed_id = filed["document_id"]
        filed_members = access.list_members(filed_id, obj_type="docx")
        evidence["filed_doc"] = filed_id
        evidence["filed_members"] = _rows(filed_members)

        # 3) THE PARENT'S OWN ROWS — asked for, and RECORDED whatever the answer is. The
        #    members route may or may not answer for a folder; either way that is a
        #    measurement, and the guide gets to say which one it is.
        evidence["folder_members"] = _folder_members(folder.token)

        # THE MEASUREMENT, asserted only where it is the gate's own subject.
        # (a) The control case is now unreachable BY DESIGN, and that is what is asserted:
        #     nothing was sent and nothing was created. The old finding (a no-folder document
        #     carried an empty member list) is preserved in this module's docstring, not
        #     re-measured, because the library can no longer make one.
        assert "folder" in evidence["control_refusal"].lower(), (
            "the refusal must say what to supply: " + evidence["control_refusal"])
        # (b) Any row a folder-filed document carries is an INHERITED row, and an inherited
        #     row arrives as perm_type='container'. That is the vocabulary the guide teaches,
        #     so it is asserted per row rather than counted.
        for row in filed_members.members:
            assert row.perm_type == "container", (
                "a row on a folder-filed document must arrive as perm_type='container'; this "
                f"one reads {row.perm_type!r} — the vocabulary the guide teaches is now wrong")
        # (c) The two cases must be *stated* separately, and this is the record of whether
        #     they differed on this run's own folder. A folder with no rows of its own passes
        #     nothing down — which is inheritance answering honestly, not the old absolute.
        evidence["filed_rows"] = (
            [(m.member_type, m.perm, m.perm_type) for m in filed_members.members])

    finally:
        for document_id in (filed_id,):
            if document_id:
                evidence[f"doc_{document_id[:8]}_after_delete"] = _delete_document(
                    writer, document_id)
        evidence[f"folder_{folder.token[:8]}_after_delete"] = _delete_folder(folder.token)
        evidence["residue"] = [key for key, value in evidence.items()
                               if str(value) == "STILL RESOLVES"]

        with capsys.disabled():
            print("\n--- docx folder-ACL gate (control vs folder-filed, + the parent) ---")
            for key, value in evidence.items():
                print(f"  {key}: {value}")
            print("  NOTE: every object above was created BY THIS RUN — the parent folder "
                  "under the bot's own root — and deleted by this run. Anything in `residue` "
                  "is a real leftover and is named, not implied. Member ids are truncated to "
                  "12 characters because an inherited row names a person or a chat this run "
                  "did not create; member_type / perm / perm_type are printed in full.")


def _folder_members(folder_token):
    """The FOLDER's own member rows — the gate's own raw call, and why it is raw.

    The shipped access surface refuses ``folder`` by name as unmeasured (LD-456's fence, which
    this gate does not move), so asking the library for this would mean widening a shipped
    refusal to serve a test. The route is the same members route the docx read uses, with
    ``type=folder``.

    **The answer is RECORDED, never asserted.** Whether that route answers for a folder at all
    is exactly the question, so a refusal here is data — returned as a string — and a raise
    would turn a measurement into a failure.
    """
    from larkdocio.drive.access import Member

    access = DriveAccessWriteClient.from_write_credentials(DOMAIN)
    try:
        response = access._call(  # noqa: SLF001 — D-12 plumbing, not a shipped path
            "GET", f"/open-apis/drive/v1/permissions/{folder_token}/members",
            params={"type": "folder"}, context="ld469 folder member read", obj_type="folder")
    except LarkDocIOError as exc:
        return f"NOT READABLE for a folder: {exc}"
    items = ((response.get("data") or {}).get("items")) or []
    return [{"member_type": m.member_type, "perm": m.perm, "perm_type": m.perm_type,
             "member_id_prefix": (m.member_id or "")[:12]}
            for m in (Member.from_payload(item) for item in items if isinstance(item, dict))]


def _delete_document(writer, document_id):
    """Trash one document this gate made, then report an INDEPENDENT re-query's answer."""
    try:
        writer.delete_document(document_id)
    except LarkDocIOError as exc:
        return f"delete refused ({type(exc).__name__})"
    return _probe(lambda: writer.get_document(document_id))


def _delete_folder(folder_token):
    """Trash the parent folder — the gate's own call, because no folder-delete verb ships."""
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
    from larkdocio.drive.files_write import DriveFilesWriteClient

    files = DriveFilesWriteClient.from_write_credentials(DOMAIN)
    return _probe(lambda: files.permalink(folder_token))


def _probe(probe):
    """An independent re-query — never a delete's own ``code:0``."""
    try:
        probe()
    except Exception as exc:  # noqa: BLE001 - any refusal is the evidence
        return f"gone ({type(exc).__name__})"
    return "STILL RESOLVES"
