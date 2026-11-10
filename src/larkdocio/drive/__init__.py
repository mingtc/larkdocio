"""larkdocio.drive — read a whole Drive folder.

*Hand the library one folder link and it enumerates the tree and reads every document inside.*
The public entry point is :func:`read_folder`, which returns a structured
:class:`~larkdocio.drive.read.FolderRead` — the walked tree, a per-child outcome (read, with
its Markdown; skipped, with the reason in Lark's own words; or folder), and the walk's own
truncation records — and :func:`~larkdocio.drive.render.render_folder`, which serialises that
result to ONE Markdown document (a tree index, each document under its heading, then a
disclosure of what could not be read). The command line reaches it as
``larkdocio folder "<url>" -o ./out/``. **The folder walk is read-only** — nothing is moved,
uploaded or written by it — and that claim is now scoped to the walk rather than to this
package: the claim it used to make about the package was **re-scoped, not deleted**
(``DRIVE.md``, in the source repository, the note "The surface also writes — four direct-call
legs"), because four write legs ship beside the
walk.

**The five surfaces this package carries**, as ``larkdocio.capabilities()`` reads them:

* ``drive-read`` — the folder walk and :func:`read_folder`, on the READ credential pair.
* ``drive-versions-write`` — :class:`~larkdocio.drive.versions_write.DriveVersionsWriteClient`,
  re-exported here, beside the read-side :func:`~larkdocio.drive.versions.list_versions`.
* ``drive-access-write`` — :class:`~larkdocio.drive.access_write.DriveAccessWriteClient`,
  re-exported here: who may use an object the app created — ``docx``, ``sheet`` or ``bitable``,
  the object type a parameter and fenced to those three — every answer an independent
  read-back.
* ``drive-files-write`` — one file into a folder
  (:func:`larkdocio.drive.files_write.put_file_in_folder`,
  :class:`~larkdocio.drive.files_write.DriveFilesWriteClient`, :class:`LinkedFile`). Reached at
  ``larkdocio.drive.files_write`` and deliberately **NOT** re-exported here: a re-export is a
  public-surface addition, and the change that corrected this docstring was a truth sweep
  forbidden to move a capability. The asymmetry is recorded rather than tidied away.
* ``drive-folders-write`` — **one** folder created under a parent
  (:class:`~larkdocio.drive.folders_write.DriveFoldersWriteClient`). Reached at
  ``larkdocio.drive.folders_write`` and **not** re-exported here either, for the reason above.
  It is the whole organize rung this library opens: no move, rename, copy, shortcut or folder
  delete ships (``folders_write.R3_NOT_SHIPPED``, a reason per row), and creating the same name
  twice under one parent makes a **second folder** — measured, and disclosed rather than deduped.

The four write legs need the WRITE credential pair and none of them is plan-gated — there is no
dry run to approve. **What stands in for one is stated PER LEG, never as one blanket promise
over all four**, because only two of the four verify inside this library:

* ``drive-access-write`` — **verified here.** Every grant, update and revoke follows its write
  with an independent member read and reports what that read found
  (:meth:`~larkdocio.drive.access_write.DriveAccessWriteClient.list_members`); an op that was
  accepted and did not store reports ``stored=False`` rather than success.
* ``drive-files-write`` — **verified here.** With ``verify_bytes`` (the default)
  :func:`~larkdocio.drive.files_write.put_file_in_folder` re-downloads the object and compares
  it to what went up **by sha256 and length**, and publishes that verdict as
  ``LinkedFile.bytes_verified``. Pass ``verify_bytes=False`` and nothing verifies.
* ``drive-versions-write`` — **NOT verified here.** The head revision is read **before** the
  create, and that read is a *pairing* — it makes ``(name, token, revision)`` one row — not a
  verdict on the write: the new version is never listed back, and where the revision is
  unavailable the field is honestly ``None`` with the reason in ``revision_note``.
* ``drive-folders-write`` — **NOT verified here.** ``create_folder`` is one call, and only one;
  nothing is read back, and a success with no token is refused rather than invented.

The read-back that would verify the last two exists only in the credential-gated live gates,
never in the shipped call path.

Underneath: a throttled, READ-only client for the one listing endpoint
(``GET /open-apis/drive/v1/files``), a depth-first walker that pages to exhaustion and carries a
visited-set, a pure ``type``→reader dispatcher that routes each child to the docx / Sheets /
Base reader (and discloses a raw ``file`` or an unknown type rather than reading it), and two
non-SDK legs — the caller's own root folder and a folder's own title — riding the existing
raw-HTTP core. Reading each document uses those read surfaces' own scopes; the folder read adds
none of its own.

The disciplines this surface enforces in code rather than in prose:

1. **Nothing is silently dropped.** Every walked child appears in the result as a read or a
   disclosed miss — ``FolderRead.accounted()`` proves ``children == read + skipped + folders``.
2. **A child that fails never fails the walk.** A refusal, a reader error or a malformed child
   degrades to a disclosed miss and the other documents still come back.
3. **A refusal that cannot know may not claim to.** ``1061002`` collapses three distinct causes
   into one code, so the refusal names both possibilities and diagnoses neither
   (:mod:`larkdocio.drive.errors`).
4. **A cap that fires is visible in the output** — every truncation names which cap, where, and
   what was not visited (:mod:`larkdocio.drive.walk`).

Scope requirements are authored only in :mod:`larkdocio.permissions`, and the machine-readable
capability surface is ``larkdocio.capabilities(full=True)["surfaces"]["drive-read"]``.
"""
from larkdocio.drive.client import DriveClient
# The type ``root_folder_token()`` answers, lifted onto this package so a caller holding a
# ``DriveClient`` can reach it from the same import as the client. Its one authoring site stays
# ``larkdocio.common.destination``, where the destination rule that refuses it lives — the fence
# must be importable without importing any client (LD-581 AC3).
from larkdocio.common.destination import ApplicationRootToken
# NB: the ``dispatch`` *function* is deliberately NOT re-exported here — re-binding the name
# ``dispatch`` on the package would shadow the ``larkdocio.drive.dispatch`` *submodule* (an
# ``import a.b.c as D`` resolves by attribute access), so callers reach the function via
# ``from larkdocio.drive.dispatch import dispatch``. Only the non-colliding names are lifted.
from larkdocio.drive.dispatch import (
    DISPATCH,
    DispatchOutcome,
    SEAM,
    UNKNOWN_TYPE_MARKER,
)
from larkdocio.drive.errors import (
    DriveError,
    DriveObjectNotFoundError,
    FolderRefusedError,
    PaginationStalledError,
    REFUSAL_SENTENCE,
)
# LD-409 — a file's NAMED versions. The model + policy half is read-safe and shared; the
# mutating client is imported from its own module here (a package __init__ is a re-export
# shelf, not an import path a CLI handler walks through), so the read client stays clear of
# the write engine while a consumer still reaches both by one name.
from larkdocio.drive.versions import (
    ABSENCES as VERSION_ABSENCES,
    MEASURED_ACCEPTED_OBJ_TYPES,
    MEASURED_REFUSED_OBJ_TYPES,
    Version,
    VersionListing,
    VersionRefusedError,
)
from larkdocio.drive.versions_write import CreatedVersion, DriveVersionsWriteClient
# LD-432 — WHO may use a document the app created. Same split as the versions family: the
# models, the gates and the disclosures are read-safe and shared; the mutating client is
# imported from its own module, reachable from no CLI command.
from larkdocio.drive.access import (
    ABSENCES as ACCESS_ABSENCES,
    COPY_LEVER_KEYS,
    MEASURED_COPY_VALUES,
    MEMBER_PERMS,
    AccessOutcome,
    AccessRefusedError,
    CopyPermissions,
    CopySetting,
    Member,
    MemberListing,
)
from larkdocio.drive.access_write import DriveAccessWriteClient
from larkdocio.drive.models import (
    AssetRef,
    CycleDisclosure,
    FolderChild,
    FolderContents,
    FolderName,
    FolderWalk,
    RefusedFolder,
    SECURITY_LEVEL_NOT_SETTABLE,
    SECURITY_LEVEL_OUTCOMES,
    SECURITY_LEVEL_UNMEASURED,
    SecurityLevel,
    Truncation,
    WalkedChild,
)
from larkdocio.drive.walk import walk_folder
# LD-326 — the composition: run the readers over the walk and produce a structured result +
# one Markdown document, per-child skip-loudly (a child failure never fails the walk).
from larkdocio.drive.read import (
    ChildOutcome,
    ChildRead,
    FolderRead,
    SkipDisclosure,
    read_child,
    read_child_markdown,
    read_folder,
)
from larkdocio.drive.render import render_folder
# LD-386 — the folder-scale asset leg: N documents' images and whiteboard PNGs into ONE shared
# token-named pool. The COMMAND's leg, never ``read_folder``'s: the library still writes no
# files for a folder read.
from larkdocio.drive.assets import (
    ASSET_DIR,
    AssetFetch,
    AssetMiss,
    fetch_folder_assets,
    folder_assets,
)
# The machine-readable projection of the same result — one row per child (title, token, type,
# revision), for a change-detection ledger rather than a person.
from larkdocio.drive.manifest import (
    REVISION_AVAILABLE,
    REVISION_SOURCES,
    REVISION_UNAVAILABLE,
    folder_manifest,
)

__all__ = [
    "ACCESS_ABSENCES",
    "ASSET_DIR",
    "AccessOutcome",
    "AccessRefusedError",
    "ApplicationRootToken",
    "COPY_LEVER_KEYS",
    "CopyPermissions",
    "CopySetting",
    "DriveAccessWriteClient",
    "MEASURED_COPY_VALUES",
    "MEMBER_PERMS",
    "Member",
    "MemberListing",
    "AssetFetch",
    "AssetMiss",
    "AssetRef",
    "ChildOutcome",
    "ChildRead",
    "CreatedVersion",
    "CycleDisclosure",
    "DISPATCH",
    "DispatchOutcome",
    "DriveClient",
    "DriveVersionsWriteClient",
    "MEASURED_ACCEPTED_OBJ_TYPES",
    "MEASURED_REFUSED_OBJ_TYPES",
    "SEAM",
    "UNKNOWN_TYPE_MARKER",
    "DriveError",
    "DriveObjectNotFoundError",
    "FolderChild",
    "FolderContents",
    "FolderName",
    "FolderRead",
    "FolderRefusedError",
    "FolderWalk",
    "PaginationStalledError",
    "SECURITY_LEVEL_NOT_SETTABLE",
    "SECURITY_LEVEL_OUTCOMES",
    "SECURITY_LEVEL_UNMEASURED",
    "SecurityLevel",
    "REFUSAL_SENTENCE",
    "REVISION_AVAILABLE",
    "REVISION_SOURCES",
    "REVISION_UNAVAILABLE",
    "RefusedFolder",
    "SkipDisclosure",
    "Truncation",
    "VERSION_ABSENCES",
    "Version",
    "VersionListing",
    "VersionRefusedError",
    "WalkedChild",
    "fetch_folder_assets",
    "folder_assets",
    "folder_manifest",
    "read_child",
    "read_child_markdown",
    "read_folder",
    "render_folder",
    "walk_folder",
]
