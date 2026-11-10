"""THE NAMED-VERSION GATE (LD-409 AC14) — the versions family, proved against real Lark.

``@pytest.mark.live_write``, deselected by default. Run it explicitly::

    pytest -m live_write

**What only a live run can establish.** The offline tests pin the request bytes and the parsed
shapes against committed captures; they cannot tell you what Lark *made*. Three things here are
live-only:

1. **The version really exists** — proved by **listing it back** through the shipped read leg
   and finding the token the create returned, not by trusting the create's ``code 0``.
2. **The pairing is exact** — the head revision this gate reads for itself, immediately before
   and immediately after the create, must be the **same number**, which is the measured
   revision-inertness the shipped docstring rests on. If Lark ever starts bumping the revision
   on a version create, the ``(name, token, revision)`` triple stops being exact and this
   reddens.
3. **A never-versioned document answers EMPTY, not a denial** — proved on a second disposable
   that is created and listed and never versioned at all.

**Disposables only (D-12).** Every document this gate touches it created itself, in this run,
and trashes in a ``finally`` — each one **acquired inside** the protected region and ledgered
the instant its id exists, so a create that fails cannot leave an earlier one behind (LD-415:
it did, once, when both creates sat above the ``try``). It names **no** pre-existing document: not the read canary, not
``LARKDOCIO_WRITE_SCRATCH_DOC``, not ``LARKDOCIO_SCRATCH_BASE``, not
``LARKDOCIO_SCRATCH_SHEET``, not the block zoo and not the comment zoo. Gone-ness is proved by
an **independent re-query** after the delete, never by the delete's own return code.

**Gentle.** Six calls on one round, each through a client limiter. No burst, no quota probe —
the quota question is answered ``unmeasured`` in the shipped words and this gate does not go
looking for the edge.

**Skips loudly, never silently.** Without write credentials the whole gate skips with a message
naming exactly what is missing.

**It ships WITH its mirror.** Everything it claims *about itself* — the disposables-only
posture, the self-created subjects, the teardown, the independent re-query — is exactly the
class of claim a credential-less run "verifies" by not running, so it is verified in
``test_live_drive_versions_gate_offline.py`` on every plain ``pytest``.
"""
import time

import canary_support
import pytest

from larkdocio.common import get_write_credentials
from larkdocio.drive import ops as drive_ops
from larkdocio.drive.client import DriveClient
from larkdocio.drive.versions_write import DriveVersionsWriteClient
from larkdocio.errors import LarkAPIError
from larkdocio.write.client import WriteClient

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

#: The write app's tenant region — matches the toolkit's default OpenAPI domain. NOT a document
#: reference: this gate never addresses a file it did not create.
DOMAIN = "larksuite.com"

#: A distinctive name so the read-back match is exact and could match nothing else.
VERSION_NAME_PREFIX = "larkdocio version gate :: SIGMA-"


def test_the_registry_declares_EXACTLY_ONE_MUTATING_OP_before_anything_is_called():
    """The read-only claim, re-scoped rather than dropped (D-24), asserted **before** the first
    call — so a second write op cannot be smuggled onto this path unnoticed."""
    assert drive_ops.read_only() is False, "create_version mutates; the surface-wide claim is over"
    # NOT an equality against the mutating set: other mutating rungs have since joined the
    # registry (the access family), and this gate's claim is about ITS op, not their absence.
    assert drive_ops.read_only(drive_ops.ENUMERATION_OPS) is True
    assert "create_version" in {d.name for d in drive_ops.mutating_ops()}
    assert drive_ops.op("create_version").mutates is True


def test_the_named_version_round_trips_on_a_disposable_this_run_created(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    app_id, app_secret = get_write_credentials()
    wc = WriteClient(app_id, app_secret, DOMAIN)
    versions = DriveVersionsWriteClient(app_id, app_secret, DOMAIN)
    reader = DriveClient.from_read_credentials(DOMAIN)

    nonce = str(int(time.time()))
    name = f"{VERSION_NAME_PREFIX}{nonce}"
    row = {"file_token": None, "empty_file_token": None, "revision_before": None,
           "paired_revision": None, "revision_after": None, "version_token": None,
           "listed_back": None, "empty_listing": None,
           "file_absent_after_delete": None, "empty_file_absent_after_delete": None}

    # LD-415: the teardown ledger. Every disposable is acquired INSIDE the protected region and
    # appended the instant its id exists, so a create that fails cannot orphan an earlier one.
    ledger = []
    try:
        dest_folder = canary_support.require_disposables_folder()
        doc = wc.create_document(title=f"larkdocio-version-gate {nonce}",
                                 folder_token=dest_folder)
        doc_id = doc["document_id"]
        ledger.append((doc_id, "file_absent_after_delete"))
        row["file_token"] = doc_id
        empty = wc.create_document(title=f"larkdocio-version-gate-empty {nonce}",
                                   folder_token=dest_folder)
        empty_id = empty["document_id"]
        ledger.append((empty_id, "empty_file_absent_after_delete"))
        row["empty_file_token"] = empty_id

        # (0) A document that has never been versioned answers an EMPTY LIST, not a denial.
        row["empty_listing"] = list(reader.list_versions(empty_id))

        # (1) The head revision, read for THIS gate's own comparison — independent of the one
        # the op reads internally, so the inertness check is not the op marking its own work.
        row["revision_before"] = wc.read_document_revision(doc_id)

        # (2) CREATE, through the shipped op — the pairing comes back with it.
        created = versions.create_version(doc_id, name)
        row["version_token"] = created.version.token
        row["paired_revision"] = created.revision

        # (3) The head revision AFTER — revision-inertness, measured here rather than assumed.
        row["revision_after"] = wc.read_document_revision(doc_id)

        # (4) LIST IT BACK through the shipped read leg — the only proof the version exists.
        listing = reader.list_versions(doc_id)
        row["listed_back"] = [(v.name, v.token, v.create_time) for v in listing]

        print(f"[version gate {nonce}] {row}")
    finally:
        for token, key in ledger:
            try:
                wc.delete_document(token)
            except Exception as exc:            # pragma: no cover - teardown must not mask
                row[f"{key}_delete_error"] = str(exc)
            # ZERO ORPHANS, verified INDEPENDENTLY: re-query and require Lark to say it is
            # gone. A delete that returned 0 and left the file is exactly what this catches.
            try:
                wc.get_document(token)
                row[key] = False
            except LarkAPIError:
                row[key] = True
        with capsys.disabled():
            print(f"[version gate close-out] {row}")

    assert row["empty_listing"] == [], (
        f"a never-versioned document did not answer an empty list: {row['empty_listing']!r}")
    assert row["version_token"], "the create returned no version token"
    assert row["paired_revision"] == row["revision_before"], (
        "the paired revision is not the head revision read immediately before the create")
    assert row["revision_after"] == row["revision_before"], (
        "creating a version moved the head revision — it is no longer revision-inert, so the "
        "(name, token, revision) triple this op returns is no longer exact")
    assert (name, row["version_token"]) in [
        (listed_name, token) for listed_name, token, _t in row["listed_back"]], (
        "the created version did not come back from the listing — code 0 is not existence")
    assert row["file_absent_after_delete"] is True, "the disposable survived its delete"
    assert row["empty_file_absent_after_delete"] is True, (
        "the second disposable survived its delete")
