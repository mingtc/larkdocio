"""Assembly — ``_build()`` and the public ``capabilities()`` entry point.

LD-244: the verbatim pre-split slice, lines 2461-2770 of the
2,770-line ``capabilities.py``. Nothing in it was rewritten.
"""
import dataclasses
from typing import Optional

from larkdocio import __version__
from larkdocio.common.url import (
    DOCX_BLOCK_ANCHOR_MEASUREMENT as _DOCX_BLOCK_ANCHOR_MEASUREMENT,
    DOCX_SECTION_ANCHOR_UI_ONLY as _DOCX_SECTION_ANCHOR_UI_ONLY,
    SHEETS_CELL_LINK_UI_ONLY as _SHEETS_CELL_LINK_UI_ONLY,
)
from larkdocio.base import field_migration as _field_migration
from larkdocio.base import field_vocabulary as _field_vocabulary
from larkdocio.base import hierarchy as _hierarchy
from larkdocio.base.client import BaseReadClient as _BaseReadClient
from larkdocio.base.embed import deep_read_embedded_base as _deep_read_embedded_base
from larkdocio.base.media import (
    MEDIA_TOKEN_NOT_INDEPENDENTLY_SHAREABLE as _MEDIA_TOKEN_NOT_INDEPENDENTLY_SHAREABLE,
)
from larkdocio.base.media import BaseMediaClient as _BaseMediaClient
from larkdocio.base.permalink import record_permalink as _record_permalink
from larkdocio.base.read import read_base as _read_base
from larkdocio.base.read import read_base_markdown as _read_base_markdown
from larkdocio.comments.client import CommentsReadClient as _CommentsReadClient
from larkdocio.comments.read import comments as _comments_read
from larkdocio.contacts.client import ContactsSearchClient as _ContactsSearchClient
from larkdocio.contacts.lookup import resolve_colleague as _resolve_colleague
from larkdocio.contacts.lookup import resolve_user as _resolve_user
from larkdocio.drive.client import DriveClient as _DriveClient
from larkdocio.drive.access import ABSENCES as _ACCESS_ABSENCES
from larkdocio.drive.access_write import (
    DriveAccessWriteClient as _DriveAccessWriteClient,
)
from larkdocio.drive.folders_write import (
    DriveFoldersWriteClient as _DriveFoldersWriteClient,
)
from larkdocio.drive.versions_write import (
    DriveVersionsWriteClient as _DriveVersionsWriteClient,
)
from larkdocio.model.projection import project_block_ids as _project_block_ids
from larkdocio.read.client import Client as _DocxReadClient
from larkdocio.read.parser import Parser as _DocxParser
from larkdocio.snapshot import SNAPSHOT_INTEGRITY_CONTRACT
from larkdocio.snapshot import load as _load_snapshot
from larkdocio.snapshot import snapshot as _snapshot
from larkdocio.sheets.client import SheetsReadClient as _SheetsReadClient
from larkdocio.sheets.read import (
    read_spreadsheet_markdown as _read_spreadsheet_markdown,
)
from larkdocio.sheets.embed import deep_read_embedded_sheet as _deep_read_embedded_sheet
from larkdocio.sheets.export_reader import SheetsExportReader as _SheetsExportReader
from larkdocio.sheets.ops import dry_run as _sheets_dry_run
from larkdocio.base.schema_client import BaseSchemaClient as _BaseSchemaClient
from larkdocio.base.schema_client import LIFECYCLE_OPS as _BASE_SCHEMA_LIFECYCLE_OPS
from larkdocio.sheets.write_client import LIFECYCLE_OPS as _SHEETS_LIFECYCLE_OPS
from larkdocio.sheets.write_client import SheetsWriteClient as _SheetsWriteClient
from larkdocio.write.absences import DOCX_WRITE_ABSENCES as _DOCX_WRITE_ABSENCES
from larkdocio.write.client import LIFECYCLE_OPS as _DOCX_LIFECYCLE_OPS
from larkdocio.write.client import WriteClient as _DocxWriteClient
from larkdocio.drive import files_write as _drive_files_write
from larkdocio.drive.files_write import LIFECYCLE_OPS as _DRIVE_FILES_LIFECYCLE_OPS
from larkdocio.drive.files_write import DriveFilesWriteClient as _DriveFilesWriteClient
from larkdocio.drive.files_write import put_file_in_folder as _put_file_in_folder
# QUOTED, never re-typed: the duplicate-upload disclosure is authored once and the surface note
# carries it verbatim, so the capability text cannot drift from the op's own docstring.
from larkdocio.drive.lookup import DUPLICATE_UPLOAD_BEHAVIOUR as _DUPLICATE_UPLOAD_BEHAVIOUR
from larkdocio.write.media import put_file_in_document as _put_file_in_document
from larkdocio.write.media import put_image_in_document as _put_image_in_document
from larkdocio.sheets.media import put_image_in_sheet as _put_image_in_sheet
from larkdocio.sheets.media import (
    put_float_image_in_sheet as _put_float_image_in_sheet,
)
from larkdocio.sheets.media import (
    remove_float_image_from_sheet as _remove_float_image_from_sheet,
)

from . import _resolution
from ._contracts import APPLY_LOG_COMPLETE, HISTORICAL_READ_CONTRACT, _safety_contracts
from ._credentials import _read_credentials, _write_credentials
from ._flag_descriptors import _flags
from ._gates import (
    CROSS_TABLE_LOSS_PREVIEW,
    DESTRUCTIVE_CONSENT_REQUIRED,
    REVISION_GUARD_FIELD_SCOPED_ONLY,
    _base_read_gate_coverage,
    _base_schema_write_gate_coverage,
    _base_write_gate_coverage,
    _comments_read_gate_coverage,
    _docx_write_gate_coverage,
)
from ._levels import (
    _base_comments_read_levels,
    _base_embedded_deep_read_levels,
    _base_read_levels,
    _comments_read_levels,
    _contacts_read_levels,
    _docx_read_levels,
    _drive_read_levels,
    _embedded_deep_read_levels,
    _sheets_read_levels,
)
from ._models import Capabilities, FieldAuthoringVocabulary, Operation, Surface
from ._summary import summary as _summary
from ._packaged_docs import _docs, _entry_points
from ._permissions import _with_permissions
from ._projections import (
    _base_schema_write_operations,
    _base_write_operations,
    _docx_block_projection_support,
    _docx_block_read_support,
    _docx_content_constraints,
    _docx_reconciliation,
    _docx_update_workflow,
    _docx_write_operations,
    _lifecycle_operations,
    _read_operations,
    _sheets_write_operations,
    _tree_helper_operations,
)

# --------------------------------------------------------------------------- #
# Assembly.                                                                     #
# --------------------------------------------------------------------------- #

def _base_field_authoring() -> FieldAuthoringVocabulary:
    """The Base field-authoring allow-list, read off the module that ENFORCES it.

    Every sequence below is the enforcing constant itself, reached through the module rather
    than through a from-import, so the list the registry publishes and the list the refusal
    consults are one object. Losing an entry from the constant therefore moves the payload
    and starts a refusal in the same breath; there is no second copy to drift.
    """
    return FieldAuthoringVocabulary(
        authorable_types=_field_vocabulary.AUTHORABLE_TYPES,
        authorable_ui_types=_field_vocabulary.AUTHORABLE_UI_TYPES,
        not_authorable=_field_vocabulary.UNAUTHORABLE_GUIDANCE,
        declared_by=(
            "the Lark server — both enums are carried in error.field_violations on every "
            "field-authoring refusal, on the create route and the convert route alike, and "
            "are transcribed here rather than curated"
        ),
        status=_field_vocabulary.VOCABULARY_STATUS,
        quadrant_note=_field_vocabulary.QUADRANT_NOTE,
        authorable_but_cells_unwritable=(
            _field_vocabulary.AUTHORABLE_BUT_CELLS_UNWRITABLE),
        neither_authorable_nor_writable=(
            _field_vocabulary.NEITHER_AUTHORABLE_NOR_WRITABLE),
        cells_writable_but_field_unauthorable=(
            _field_vocabulary.CELLS_WRITABLE_BUT_FIELD_UNAUTHORABLE),
        projected_from="larkdocio.base.field_vocabulary",
        evidence=_field_vocabulary.VOCABULARY_EVIDENCE,
    )


def _surface_docx_read() -> Surface:
    return Surface(
        title="docx reader — download a Lark docx/wiki document to clean Markdown",
        domain="docx",
        mode="read",
        credentials=_read_credentials(
            note=(
                "Read app (READ pair, legacy fallback). docx:document:readonly is the core "
                "reader scope. The two contacts scopes are OPTIONAL and needed TOGETHER "
                "for @mention (and comment-author) name resolution: "
                "contact:contact.base:readonly opens the directory call and "
                "contact:user.base:readonly is the FIELD-level grant that makes the name "
                "fields non-null — with the first alone the call succeeds and every name "
                "comes back null, which is indistinguishable from 'no such user'. Beyond "
                "the scopes, the app's contacts data range must cover the users being "
                "resolved (a Lark console setting, not an API scope). Absent either, "
                "resolution degrades to the raw @open_id and never fails the read. The "
                "client ops fetch blocks; the Parser ops turn them into Markdown "
                "(parse_docx_content, whose own signature is (doc_id, blocks)) or into "
                "the node tree the writeback engine anchors against (parse_docx_tree). "
                "Mention resolution is the PARSER's, not the call's — construct it as "
                "Parser(config, read_client=client) and every parse it runs resolves the "
                "mentions, exactly as the download command does. The parser needs no "
                "credentials of its own. DEEP LINKS — WHAT CAN BE MINTED, AND HOW FAR IT "
                "IS MEASURED: "
                + _DOCX_BLOCK_ANCHOR_MEASUREMENT
                + " DEEP LINKS — WHAT CANNOT BE MINTED OR FETCHED: "
                + _DOCX_SECTION_ANCHOR_UI_ONLY
            ),
        ),
        # LD-410 — the historical read's contract: the pin rides the route it was MEASURED
        # on, and the three traps around it are met here rather than one at a time.
        # LD-444 — the persisted read's contract: rehydrate exactly, or refuse typed.
        safety_contracts=[HISTORICAL_READ_CONTRACT, SNAPSHOT_INTEGRITY_CONTRACT],
        levels=_docx_read_levels(),
        block_read_support=_docx_block_read_support(),
        block_projection_support=_docx_block_projection_support(),
        operations=(
            _read_operations(_DocxReadClient, "larkdocio.read.client.Client")
            + _read_operations(_DocxParser, "larkdocio.read.parser.Parser")
            + _tree_helper_operations()
            + [
                # The opt-in block-identity projection: the same Markdown with one
                # marker per block and the identifiers it emitted. Offline, like
                # the tree helpers above — it re-renders a tree the caller already
                # holds and touches no endpoint.
                Operation(
                    name="project_block_ids",
                    projected_from="larkdocio.model.projection",
                    impl=_project_block_ids,
                ),
                # LD-444 — the file-first persistence seam. Offline like the helpers
                # above and then some: these two reach NO endpoint and need NO
                # credentials, which is worth reporting rather than leaving the
                # registry's silence to be read as an omission. `snapshot` persists the
                # lossless read (raw block payloads + revision + token) under one
                # checksum; `load` rehydrates it to the same tree, or refuses typed.
                Operation(
                    name="snapshot",
                    projected_from="larkdocio.snapshot",
                    impl=_snapshot,
                ),
                Operation(
                    name="load",
                    projected_from="larkdocio.snapshot",
                    impl=_load_snapshot,
                ),
            ]
        ),
    )


def _surface_docx_comments_read() -> Surface:
    return Surface(
        title=(
            "comments reader — the review conversation on a document or spreadsheet, "
            "joined to the anchors a parsed document already carries"
        ),
        domain="docx",
        mode="read",
        credentials=_read_credentials(
            note=(
                "Read app (READ pair, legacy fallback). The whole comment family answers "
                "on the reader's own scope — listing comments, fetching a batch of them "
                "by id, and listing one comment's replies all succeed with NO additional "
                "scope. The directory lookup is deliberately NOT requested BY THIS "
                "SURFACE: comment authors are reported as raw ids, exactly as the API "
                "gave them, and no name is ever guessed. Resolving one is a separate, "
                "explicit call you make — "
                "batch_get_user_names on the docx-read surface, which takes the same read "
                "credentials — and it depends on that surface's two optional contacts "
                "scopes plus the app's contacts data range covering those users. "
                "Spreadsheets are readable with the same credentials by passing the "
                "spreadsheet file type."
            ),
        ),
        levels=_comments_read_levels(),
        operations=_read_operations(
            _CommentsReadClient, "larkdocio.comments.client.CommentsReadClient"
        ) + [
            Operation(
                name="comments",
                projected_from="larkdocio.comments.read",
                impl=_comments_read,
            ),
        ],
        gate_coverage=_comments_read_gate_coverage(),
    )


def _surface_contacts_read() -> Surface:
    return Surface(
        title=(
            "name lookup — a display name, an email or a mobile → exactly one open_id, "
            "or a typed refusal "
            "saying which of not-found / ambiguous / could-not-look happened"
        ),
        domain="docx",
        mode="read",
        credentials=_read_credentials(
            note=(
                "Read app (READ pair, legacy fallback). This is the FORWARD direction — "
                "name to id — and it is the one surface here that needs a DIRECTORY scope "
                "rather than a contacts one; see this surface's per-operation row for the "
                "exact string, which is authored in larkdocio.permissions and nowhere "
                "else. Without it the call is DENIED and resolve_user raises "
                "LarkPermissionError carrying Lark's own denial body — it does NOT report "
                "the person as absent, and there is no degrade path. WHAT THIS SURFACE "
                "WILL NOT DO: it will not guess; it will not fuzzy-, phonetic- or "
                "rank-match, and it will not take the top hit (matching is casefold + "
                "whitespace-normalized EXACT, client-side, over the directory's own "
                "display strings); it will not name the candidates when it refuses as "
                "ambiguous, because a refusal drawn from the live directory that listed "
                "names would be an enumeration oracle one query at a time; it will not "
                "resolve names inside dry_run(), which keeps plan-time mention validation "
                "an independent second gate; and it WILL NOT ENUMERATE THE DIRECTORY TO "
                "FAKE A NAME SEARCH — that was disqualified before the surface was "
                "written and the rejection is recorded in the package docstring so it is "
                "not re-derived. THE NAME-SEARCH VERDICT, observed live on 2026-08-02: "
                "the endpoint answers, its match rule is token-prefix and "
                "case-insensitive, and its reachable set can be far narrower than the "
                "directory — on the tenant measured it returned only the account owner, "
                "while the REVERSE direction (batch_get_user_names on docx-read) resolved "
                "other users fine. So read a not-found as 'the search did not return "
                "them', never as 'this person does not exist'. Resigned employees are "
                "excluded explicitly rather than by inheriting a server default."
            ),
        ),
        levels=_contacts_read_levels(),
        safety_contracts=["exactly-one-or-refuse"],
        operations=_read_operations(
            _ContactsSearchClient, "larkdocio.contacts.client.ContactsSearchClient"
        ) + [
            Operation(
                name="resolve_user",
                projected_from="larkdocio.contacts.lookup",
                impl=_resolve_user,
            ),
            Operation(
                name="resolve_colleague",
                projected_from="larkdocio.contacts.lookup",
                impl=_resolve_colleague,
            ),
        ],
    )


def _surface_drive_read() -> Surface:
    return Surface(
        title=(
            "Drive folder reader (R1) — hand it one folder link and it enumerates the tree "
            "and reads every document inside, disclosing what it cannot read"
        ),
        domain="drive",
        mode="read",
        credentials=_read_credentials(
            note=(
                "Read app (READ pair, legacy fallback). The one required scope is on this "
                "surface's per-operation rows, authored in larkdocio.permissions and nowhere "
                "else — and for R1 those rows are EMPTY with the requirement recorded UNKNOWN: "
                "every enumeration call answered code 0 on the READ pair with zero grants, "
                "which proves reach and attributes no scope, so no drive scope is asserted, "
                "widened or guessed. Reading each document inside rides the docx / Sheets / "
                "Base read surfaces already published here, each carrying its own scope. "
                "OPTING INTO FIDELITY COSTS A SCOPE THE VALUES WALK DOES NOT NEED, and that is "
                "stated rather than left to be discovered: --fidelity-read-sheets adds the "
                "Sheets L2 xlsx-export leg, so that leg's own declared READ-app export scope "
                "— authored in larkdocio.permissions and quoted from there, never restated "
                "here — applies to the walk too. It governs two legs — a docx EMBEDDED sheet "
                "(which also needs --deep-read-sheets) and a SPREADSHEET child of the folder "
                "(which needs nothing else, being read through the Sheets surface either way); "
                "that second leg is what carries a colour-encoded workbook's per-cell fills "
                "into the Markdown instead of rendering its blank cells as an empty table. "
                "WHAT THIS SURFACE IS AND IS NOT: it is READ-ONLY end to end — every operation "
                "declares mutates=False and no call is ever made on the write pair. That claim "
                "is about THIS surface and is unchanged. Drive WRITES live on their own "
                "surfaces, each on the write pair, so no write is ever filed under read "
                "credentials: drive-versions-write (one NAMED VERSION), drive-folders-write "
                "(create a folder), drive-files-write (upload a file into a folder, and "
                "delete an uploaded file object — to the trash, never a purge) and "
                "drive-access-write (grant, raise, lower and revoke ONE NAMED HUMAN's access "
                "to a document, list its members, and move the copy settings one key per "
                "call). Each was opened by its own product ruling against a standing "
                "reason that still binds the rest: a Drive write is permanent and no open-API "
                "verb purges or un-trashes anything, so MOVE, COPY and SHORTCUT are NOT "
                "OFFERED; and a tool that can flip a document PUBLIC is one that can "
                "exfiltrate a tenant, so the public-link and external-access half of "
                "permission management stays unoffered on every surface; full-text "
                "SEARCH and file SUBSCRIPTIONS are STRUCTURALLY UNREACHABLE — they are "
                "USER-token-only and this library is tenant-token-only, an AUTH-MODEL wall, "
                "NOT a scope denial, so no console grant opens them; and a child whose type is "
                "'file' (raw uploaded bytes NOTHING HERE TURNS INTO MARKDOWN) is DISCLOSED by "
                "name and type, never silently dropped and never downloaded by the walk — and "
                "THE SKIP REASON NAMES THE VERB THAT DOES FETCH THE BYTES, "
                "DriveFilesWriteClient.download(file_token) on drive-files-write, because what "
                "this walk declines to do is not the same as what the library lacks. The "
                "public entry "
                "point is larkdocio.drive.read_folder(url); a child that fails to read never "
                "fails the walk, and every walked child appears in the result as a read or as "
                "a disclosed miss (the sheet / bitable dispatch is asserted, not demonstrated "
                "end to end — no live enumeration has yet surfaced either)."
            ),
        ),
        levels=_drive_read_levels(),
        operations=_read_operations(
            _DriveClient, "larkdocio.drive.client.DriveClient"),
    )


def _surface_drive_versions_write() -> Surface:
    """The Drive surface's FIRST mutating rung (LD-409) — creating one **named version**.

    A surface of its own rather than an operation on ``drive-read``, and the reason is
    mechanical rather than aesthetic: a surface carries **one** mode and **one** credential
    pair, and a write filed under a read surface would publish "this needs read credentials",
    which is exactly the kind of quiet mis-statement the permission registry exists to make
    impossible. ``drive-read`` stays read-only end to end; this surface says what it changes.
    """
    return Surface(
        title=(
            "Drive named versions (write) — create one named version of a file, paired with "
            "the head revision read immediately before it"
        ),
        domain="drive",
        mode="write",
        credentials=_write_credentials(
            note=(
                "Write app (WRITE pair, NO fallback — least-privilege). WHAT THIS SURFACE "
                "CHANGES: it adds one NAMED VERSION to a Drive file. The change is ADDITIVE "
                "and measured REVISION-INERT — the document's head revision was identical "
                "immediately before and immediately after the create — so a version is a "
                "label on a moment, not an edit to the document. WHAT IT RETURNS is the whole "
                "point: the new version token PAIRED with the head revision read immediately "
                "BEFORE the create, so a ledger can record (name, token, revision) as one "
                "row; that triple is exact absent a concurrent edit, and where the revision "
                "is not available (the read failed, or the file is not a docx) the field is "
                "honestly absent rather than synthesized or zeroed. WHAT IT DOES NOT DO: "
                "there is NO delete-version verb here. The route is measured working and is "
                "deliberately unshipped pending its own ruling, because deleting a named "
                "version on a real user's document is a destruction this surface has measured "
                "no restore verb for. A version token also cannot be resolved back to content "
                "or to a revision by any route tried, so a name records a moment it cannot "
                "reproduce. THE SCOPE REQUIREMENT IS UNKNOWN AND SAYS SO: no scope string has "
                "ever been observed demanded on this endpoint family, on either credential "
                "pair — authored in larkdocio.permissions with its reason, never restated "
                "here, and never guessed. Duplicate names are allowed by Lark (a second "
                "'V1.0' comes back 'V1.0(1)' with a distinct token) and that is disclosed "
                "rather than deduped; no name-length ceiling and no quota are claimed, "
                "because neither was measured."
            ),
        ),
        safety_contracts=["version-pairing-is-not-a-verdict"],
        operations=[
            Operation(
                name="create_version",
                projected_from="larkdocio.drive.versions_write.DriveVersionsWriteClient",
                impl=_DriveVersionsWriteClient.create_version,
            ),
        ],
    )


def _surface_drive_files_write() -> Surface:
    """The folder-upload slice — put a FILE in a folder and get its openable URL.

    A surface of its own for the same mechanical reason the named-version rung is one: a
    surface carries one mode and one credential pair, and this one **writes a permanent
    object into somebody's Drive**. It is deliberately the narrowest slice that makes a
    sentence-link executable, and it says so.
    """
    return Surface(
        title=(
            "Drive folder upload (write) — put a file in a caller-named folder and return "
            "its token and its permalink"
        ),
        domain="drive",
        mode="write",
        credentials=_write_credentials(
            note=(
                "Write app (WRITE pair, NO fallback — least-privilege). WHAT THIS SURFACE "
                "CHANGES: it puts a real FILE OBJECT into a folder. THE DESTINATION IS "
                "ALWAYS THE CALLER'S — the folder token is required, and the rule is the one "
                "stated by the module this surface is projected from "
                f"({_drive_files_write.__name__}), scoped to it: "
                # PROJECTED, never re-typed (LD-571). The library-wide spelling of this rule
                # shipped here after the 2026-08-14 ruling opened create_folder, denying a call
                # listed in the same payload; only the scope was superseded, and the constant is
                # now the single authoring of the sentence.
                + _drive_files_write.DESTINATION_IS_THE_CALLERS
                + " WHAT IT RETURNS is what makes the ask "
                "executable: the file token AND the file's own web URL, ASKED FOR via a "
                "metadata query and never constructed from a token. THAT URL IS A "
                "PERMALINK, NOT A SIGNED LINK — the object's own address, not a "
                "credential; the short-lived signed link the upload's own answer carries is "
                "read by nothing here and returned by nothing. A PERMALINK GRANTS NOBODY "
                "ACCESS: whoever opens it still needs access to the file, and this library "
                "ships no sharing verb for a file object. RESIDUE: a file object CAN be "
                "deleted (trash, not purge, and no API undo was measured) — which is the "
                "opposite of media bytes uploaded into a document, which no open-API verb "
                "purges at all. SIZE IS HANDLED FOR THE CALLER AND THE PARTITION IS THE "
                "SERVER'S: above a stated LIBRARY-POLICY boundary (SINGLE_SHOT_MAX_BYTES, "
                "overridable per call, and not a limit anyone observed Lark enforcing) the "
                "same op sends the bytes in blocks through upload_prepare / upload_part / "
                "upload_finish, partitioned by the block_size and block_num LARK declares for "
                "that upload and by nothing this library compiled in — a size constant would "
                "be right on one tenant on one day and a latent bug afterwards. The verdict is "
                "unchanged and is the hash-verified read-back: upload_finish answers code:0 "
                "with a file_token for something that is only a file once it has been "
                "downloaded again and hashed, and the optional Adler-32 checksum is NOT sent "
                "because it was omitted in the measurement and buys no guarantee this library "
                "can point to. THE CHUNKED ROUTE'S OWN RESIDUE, disclosed rather than "
                "discovered: a run that sends parts and never reaches upload_finish leaves a "
                "pending upload transaction with NO Drive object, no cancel verb was found in "
                "the SDK's drive v1 surface and none was called (unmeasured, not 'cannot'), "
                "its expiry is unmeasured, and the failure says what it left behind instead of "
                "raising a bare error. WHAT IS NOT HERE: the uploaded-file-to-native-doc "
                "import is untried, and every folder-organising verb is out of scope. THE "
                "SCOPE REQUIREMENT IS UNKNOWN "
                "AND SAYS SO — authored in larkdocio.permissions with its reason, never "
                "guessed — and whether the upload succeeds on READ credentials is "
                "UNMEASURED rather than quietly answered. " + _DUPLICATE_UPLOAD_BEHAVIOUR
            ),
        ),
        safety_contracts=["caller-supplied-destination", "bytes-verified-round-trip"],
        operations=[
            Operation(
                name="put_file_in_folder",
                projected_from="larkdocio.drive.files_write",
                impl=_put_file_in_folder,
            ),
        ],
        # LD-710 — the two PUBLIC verbs a consumer is sent to on this surface and that were
        # declared nowhere: ``download`` (a folder file's bytes, back) and ``permalink`` (its
        # own web address, asked again). Both are API-using on this surface's own credential
        # pair, and the guide, the README and the surface note above point a consumer at
        # them — so a census claiming to be complete has to carry them. LEGS rather than
        # operations: each is one call a caller makes by name, not a step of the upload.
        legs=[
            Operation(
                name="download",
                projected_from="larkdocio.drive.files_write.DriveFilesWriteClient",
                impl=_DriveFilesWriteClient.download,
            ),
            Operation(
                name="permalink",
                projected_from="larkdocio.drive.files_write.DriveFilesWriteClient",
                impl=_DriveFilesWriteClient.permalink,
            ),
        ],
        # THE DESTROY HALF, DECLARED (LD-442). ``delete`` shipped with the slice, is public, is
        # exercised by the live round trip and is named in the surface note above as the
        # reversibility this slice is safe because of — and it was declared NOWHERE, so its
        # scope requirement was written down nowhere. It is a lifecycle call in the exact sense
        # the registry means: it destroys the file object this surface created. The create half
        # is the operation above and is not repeated here.
        lifecycle=_lifecycle_operations(
            _DriveFilesWriteClient, "larkdocio.drive.files_write.DriveFilesWriteClient",
            _DRIVE_FILES_LIFECYCLE_OPS),
    )


def _surface_drive_folders_write() -> Surface:
    """The ONE R3 organize verb that opened (LD-467) — **create a folder under a parent**.

    A surface of its own for the mechanical reason the upload rung is one: a surface carries
    one mode and one credential pair. It carries **one operation**, and the note is as
    concerned with what is *not* here as with what is — the maintainer ruling of 2026-08-14 opened
    folder creation and nothing else on the rung.
    """
    return Surface(
        title=(
            "Drive folder creation (write) — create ONE folder under a caller-named parent, "
            "and nothing else on the organize rung"
        ),
        domain="drive",
        mode="write",
        credentials=_write_credentials(
            note=(
                "Write app (WRITE pair, NO fallback — least-privilege). WHAT THIS SURFACE "
                "CHANGES: it creates a real FOLDER inside a folder the caller names. WHY IT "
                "EXISTS AT ALL: a consumer could read a folder tree and upload a file into a "
                "folder but could not MAKE one, so 'publish these and organise them into "
                "subfolders' was structurally impossible rather than merely undocumented — "
                "opened by a product ruling of 2026-08-14. WHAT IT RETURNS is what the "
                "response actually carries and no more: the new folder's token AND Lark's own "
                "url for it, two keys, measured — the url is honestly absent when Lark sends "
                "none rather than assembled from a host and a token. DUPLICATE NAMES MAKE A "
                "SECOND FOLDER: creating a folder whose name already exists under the same "
                "parent answered code:0 with a DISTINCT token, and the parent's own listing "
                "then showed two folders whose names are byte-identical — no de-duplication, "
                "no rename, no reuse and no warning. Nothing is pre-checked here, because a "
                "look-then-create is a race this library cannot win; a caller who needs one "
                "folder per name lists the parent and decides. THE DESTINATION IS ALWAYS THE "
                "CALLER'S, and both halves of that are measured: OMITTING the parent is "
                "refused by LARK as failing its own field validation (folder_token is "
                "required), so there is no "
                "default-parent behaviour to lean on, while sending it as the EMPTY STRING is "
                "ACCEPTED by Lark and puts the folder in the CALLING APP'S OWN ROOT — a "
                "destination this library did not pick, so it is refused locally instead of "
                "forwarded. AN EMPTY NAME IS LIKEWISE ACCEPTED BY LARK and stored as the empty "
                "string, so that refusal too is this library's own and says so rather than "
                "blaming the server. WHAT IS NOT HERE, AND IT IS THE SCOPE RATHER THAN AN "
                "OVERSIGHT: the rest of the organize rung stays SHUT — no move, no rename, no "
                "copy, no bulk 'organise by type' helper, no shortcut, and NO FOLDER DELETE. A "
                "folder this library creates is therefore permanent as far as this library is "
                "concerned; the Drive delete route was measured working on a folder and is "
                "deliberately unshipped under the one-verb ruling, so a caller who needs it "
                "makes that call themselves. THE SCOPE REQUIREMENT IS UNKNOWN AND SAYS SO: no "
                "scope string has ever been observed demanded on this endpoint — authored in "
                "larkdocio.permissions with its reason, never restated here and never guessed "
                "— and whether the call succeeds on READ credentials is not answerable on the "
                "measured tenant at all, because its two pairs alias one app. No name-length "
                "ceiling and no folder-count quota are claimed, because neither was measured."
            ),
        ),
        safety_contracts=["caller-supplied-destination"],
        operations=[
            Operation(
                name="create_folder",
                projected_from="larkdocio.drive.folders_write.DriveFoldersWriteClient",
                impl=_DriveFoldersWriteClient.create_folder,
            ),
        ],
    )


def _surface_drive_access_write() -> Surface:
    """WHO may use a docx, sheet or Base the app created (LD-432) — the grant surface, fenced
    to what was measured.

    A surface of its own for the reason ``drive-versions-write`` is one: a surface carries one
    mode and one credential pair, and these calls are made on the WRITE pair. ``drive-read``
    stays read-only end to end.
    """
    return Surface(
        title=(
            "Drive access management (write) — grant a HUMAN view / edit / full_access on a "
            "docx, sheet or Base the app created, read the members and the owner, take the "
            "grant back, and move the two document settings whose names govern copying"
        ),
        domain="drive",
        mode="write",
        credentials=_write_credentials(
            note=(
                "Write app (WRITE pair, NO fallback — least-privilege), and EVERY leg is on "
                "that one pair: the member calls, the owner metadata read, and the contacts "
                "lookup that turns an email into an open_id. WHY THIS SURFACE EXISTS: the bot "
                "is the OWNER of what it mints without being a member row, and nobody else is "
                "on it at a level anyone chose — a document created with NO folder carries no "
                "member row at all, while one created INTO a folder carries that folder's "
                "rows, each marked perm_type='container' (both cases measured; the older "
                "unconditional 'a fresh docx answers items: []' was false for the folder "
                "case). WHAT IT CHANGES: it adds, raises, lowers and removes ONE "
                "human's member level (view / edit / full_access, all three measured route "
                "with independent read-backs) and it sets two document-level switches "
                "(copy_entity / security_entity), one key per call. THE VERDICT IS ALWAYS THE "
                "READ-BACK: code 0 proves acceptance and nothing else, and this very family "
                "produced a measured SWALLOW — a member re-add accepted with a complete echo "
                "and absent from the independent read — so every op here reads its own work "
                "back and reports what it found. THE GRANTEE IS AN EMAIL OR AN open_id: an "
                "email goes through the shipped contacts resolve_colleague, an open_id is "
                "passed through, and a bare display NAME is refused before any call with a "
                "message that asks for an email — an address route is not a name route, and a "
                "failed resolve means UNRESOLVED HERE, never that the person does not exist — "
                "and the refusal NAMES the shipped verb that does answer a name, "
                "larkdocio.contacts.resolve_user(name=...), rather than only saying no. THE "
                "OBJECT TYPE IS A PARAMETER: every verb takes obj_type, in larkdocio's own "
                "vocabulary (docx / sheets / base) or Lark's (docx / sheet / bitable), or reads "
                "it off the object's url; the measured set is docx, sheet and bitable, a bare "
                "token with no obj_type is addressed as docx (declared, not inferred — a Lark "
                "token carries no type), and every other type is refused LOCALLY by name as "
                "unmeasured rather than guessed onto the wire. Where Lark itself answers 1063001 "
                "Invalid parameter, its code and message are preserved and the library adds what "
                "that code means on this family and which knob answers it. "
                "WHAT IT DOES NOT DO, each with its own words in larkdocio.drive.access and "
                "quoted rather than restated: it does NOT transfer ownership (measured, and "
                "measured NOT clean — the transfer stores, the app then loses its delete right "
                "irrecoverably, a member re-add is swallowed and transferring back is denied); "
                "it does not grant to a GROUP (one synthetic-id call is not evidence, so "
                "groups are UNMEASURED rather than refused); lock_switch is READ-ONLY on the "
                "settings route and "
                "external_access_entity was refused there, both shipping as documented facts "
                "rather than options; and it CANNOT TELL YOU WHETHER A HUMAN'S CLIPBOARD THEN "
                "OBEYS — no reachable endpoint reports that, so this surface reports what "
                "STORED and states the mechanism only as a hypothesis. THE SCOPE REQUIREMENT "
                "IS UNKNOWN AND SAYS SO: no scope string has ever been observed demanded on "
                "these endpoint families, authored in larkdocio.permissions with its reason "
                "and never guessed. AND THIS IS NOT A SCOPE ESCALATION: it grants a HUMAN "
                "access to an object the BOT owns; granting the APP a scope stays a Lark "
                "console action this library has no code path for."
            ),
        ),
        safety_contracts=["read-back-is-the-verdict"],
        operations=[
            Operation(
                name="grant_access",
                projected_from="larkdocio.drive.access_write.DriveAccessWriteClient",
                impl=_DriveAccessWriteClient.grant_access,
            ),
            Operation(
                name="update_access",
                projected_from="larkdocio.drive.access_write.DriveAccessWriteClient",
                impl=_DriveAccessWriteClient.update_access,
            ),
            Operation(
                name="revoke_access",
                projected_from="larkdocio.drive.access_write.DriveAccessWriteClient",
                impl=_DriveAccessWriteClient.revoke_access,
            ),
            Operation(
                name="list_members",
                projected_from="larkdocio.drive.access_write.DriveAccessWriteClient",
                impl=_DriveAccessWriteClient.list_members,
            ),
            Operation(
                name="set_copy_permissions",
                projected_from="larkdocio.drive.access_write.DriveAccessWriteClient",
                impl=_DriveAccessWriteClient.set_copy_permissions,
            ),
        ],
        # The address -> id LEG, declared for the reason the sheets writer's plan-time
        # contacts read is: it is a real API-using call site that is not one of the dispatched
        # operations, and a leg with no row would carry a requirement written down nowhere.
        # It rides the WRITE pair — the pair the measurement itself was made on.
        legs=[
            Operation(
                name="resolve_grantee_email",
                projected_from="larkdocio.drive.access_write.DriveAccessWriteClient",
                impl=_DriveAccessWriteClient.resolve_grantee_email,
            ),
        ],
    )


def _surface_sheets_read() -> Surface:
    return Surface(
        title="Sheets reader (L1) — a spreadsheet's values → titled Markdown tables",
        domain="sheets",
        mode="read",
        credentials=_read_credentials(
            note=(
                "Read app (READ pair, legacy fallback) — reachability verified with READ "
                "creds. drive:export is the OPTIONAL READ-app scope for the L2 style/numFmt "
                "fidelity leg (the xlsx export reader); base values/metadata reads do not "
                "need it. DEEP LINKS — TAB LINKS ARE MINTABLE (larkdocio.sheets.tab_url), "
                "CELL LINKS ARE NOT: "
                + _SHEETS_CELL_LINK_UI_ONLY
            ),
        ),
        levels=_sheets_read_levels(),
        operations=(
            _read_operations(_SheetsReadClient, "larkdocio.sheets.client.SheetsReadClient")
            + [
                # LD-405 — the walk's URL-first front door, the twin of `read_base_markdown`
                # on the Base surface and enumerated the same way: a composed entry point
                # that is not a client method.
                #
                # Only the MARKDOWN twin is listed, deliberately. Its structured partner is
                # `larkdocio.sheets.read_spreadsheet`, which composes the client method of
                # THE SAME NAME and reaches exactly the endpoints that row already reports —
                # so a second row would key the projection twice under one name (and print
                # `read_spreadsheet` twice in every generated table) while disclosing
                # nothing a consumer does not already read there.
                Operation(
                    name="read_spreadsheet_markdown",
                    projected_from="larkdocio.sheets.read",
                    impl=_read_spreadsheet_markdown,
                ),
            ]
        ),
        # The style/number-format fidelity leg is a SECOND client on this surface, and it
        # was the one public, documented, credential-needing leg with no row here at all —
        # so the export scope it needs (and only it needs) had no call site to belong to.
        # Projected exactly like a read client's ops, but as a LEG: it is not one of the
        # surface's dispatched read ops, and every guard that reads `operations` means
        # those.
        legs=_read_operations(
            _SheetsExportReader,
            "larkdocio.sheets.export_reader.SheetsExportReader"),
    )


def _surface_sheets_embedded_deep_read() -> Surface:
    return Surface(
        title="Embedded-sheet deep-read bridge — inline a docx type-30 embedded sheet",
        domain="sheets",
        mode="read",
        opt_in=True,
        gated_by=["deep_read_sheets", "fidelity_read_sheets"],
        # It fires INSIDE a document read, so the document scope is genuinely part of
        # what it needs even though none of its own calls asks for it.
        composes=["docx-read"],
        credentials=_read_credentials(
            note=(
                "Opt-in (--deep-read-sheets): composes the docx read (docx:document:readonly) "
                "with the Sheets read of the referenced tab only. --fidelity-read-sheets adds "
                "the READ-app drive:export leg for whole-cell (format-level) bold/italic."
            ),
        ),
        levels=_embedded_deep_read_levels(),
        operations=[
            Operation(
                name="deep_read_embedded_sheet",
                projected_from="larkdocio.sheets.embed",
                impl=_deep_read_embedded_sheet,
            ),
        ],
    )


def _surface_base_read() -> Surface:
    return Surface(
        title="Base (bitable) reader (L1) — a Base's tables → titled Markdown tables",
        domain="base",
        mode="read",
        credentials=_read_credentials(
            note=(
                "Read app (READ pair, legacy fallback). READ-ONLY END TO END: every "
                "operation on this surface declares mutates=False, so no Base call is ever "
                "made on the write pair and there is no path here that creates, edits or "
                "deletes anything in a Base — including its sharing: this library does not "
                "control a Base's shareability, and exposes no operation that would. The "
                "one required scope is on this surface's per-operation rows, authored in "
                "larkdocio.permissions and nowhere else. A BASE URL's SLUG IS ITS APP "
                "TOKEN, so either form is accepted; a spreadsheet or document URL is "
                "refused by name rather than attempted. TWO REFUSALS WORTH KNOWING BEFORE "
                "YOU PLAN: a Base's roles / advanced-permission family answers "
                "OperationTypeError because advanced permissions are switched OFF on the "
                "Base itself — that is a product feature gate the Base's OWNER turns on in "
                "the product, NOT a scope you can be granted, and the API refuses to turn "
                "it on for you either; and a type-24 Flow column's values are returned by "
                "no read route, so those cells carry a visible absent-with-reason marker."
            ),
        ),
        levels=_base_read_levels(),
        # LD-260 (O6′): declarable at last. LD-251 correctly refused to name a ring that
        # was still LD-252's unlanded product; it landed, so the claim is made from real
        # files and bounded to what those two read-only arms actually prove.
        gate_coverage=_base_read_gate_coverage(),
        operations=(
            _read_operations(_BaseReadClient, "larkdocio.base.client.BaseReadClient")
            + [
                # The two public entry points a consumer actually calls. Neither is a
                # client method — each composes the client's five reads into one answer —
                # so they are enumerated the way the comments surface's composed entry
                # point is.
                Operation(
                    name="read_base",
                    projected_from="larkdocio.base.read",
                    impl=_read_base,
                ),
                Operation(
                    name="read_base_markdown",
                    projected_from="larkdocio.base.read",
                    impl=_read_base_markdown,
                ),
                # LD-345 — the per-selection record permalink fetch. A composed entry point,
                # like the two above: it spends the client's batch_get_records (with
                # with_shared_url) and shapes the answer into typed per-id outcomes. It reaches
                # the same records/batch_get endpoint the read families already do, so its
                # derived permission row resolves to base-read's own read scope with NO new
                # scope and no new endpoint row (the scope is authored in larkdocio.permissions).
                Operation(
                    name="record_permalink",
                    projected_from="larkdocio.base.permalink",
                    impl=_record_permalink,
                ),
            ]
        ),
        legs=[
            # LD-296 — the ROW-HIERARCHY read. A leg rather than an operation, for the
            # reason legs exist: it reaches NO endpoint of its own. It is pure over what a
            # read already holds — field specs, records, an already-read view — so it costs
            # no call, needs no scope, and cannot be switched on by accident: the default
            # read path never reaches it.
            Operation(
                name="read_hierarchy",
                projected_from="larkdocio.base.hierarchy",
                impl=_hierarchy.read_hierarchy,
            ),
        ],
    )


def _surface_base_comments_read() -> Surface:
    return Surface(
        title=(
            "Base comments reader — the review conversation on a Base, attributed to the "
            "record, table and view the reviewer had open"
        ),
        domain="base",
        mode="read",
        # It IS the document comment read with a third accepted file type, so its
        # requirement is that surface's requirement rather than a second claim.
        composes=["docx-comments-read"],
        credentials=_read_credentials(
            note=(
                "Read app (READ pair, legacy fallback). A Base's comments are NOT part of "
                "the Base API: they are listed by the drive comment family, with the "
                "Base's app token as the file token and the bitable file type — so this is "
                "the shipped comments client and the shipped comments entry point, with a "
                "third accepted file type, and it needs NO scope the document comment read "
                "does not already need (observed: the same call site with the bitable file "
                "type answered on unchanged grants). THE WRITE HALF IS REFUSED BY THE "
                "SERVER at every granularity — the create route's own file-type list names "
                "documents only, and the record-level comment routes do not exist — so no "
                "path to creating, editing, resolving or deleting a Base comment is "
                "exposed, and none is hidden behind a flag."
            ),
        ),
        levels=_base_comments_read_levels(),
        operations=[
            Operation(
                name="comments",
                projected_from="larkdocio.comments.read",
                impl=_comments_read,
            ),
        ],
    )


def _surface_base_embedded_deep_read() -> Surface:
    return Surface(
        title="Embedded-Base deep-read bridge — inline a Base embedded in a document",
        domain="base",
        mode="read",
        opt_in=True,
        gated_by=["deep_read_bases"],
        # It fires INSIDE a document read and reaches the Base read, so both surfaces'
        # requirements are genuinely part of what it needs.
        composes=["docx-read", "base-read"],
        credentials=_read_credentials(
            note=(
                "Opt-in, from the command line (--deep-read-bases) or in code "
                "(Parser(deep_read_bases=True, base_client=…)): it composes the document "
                "read with the Base read of the referenced table only. Off by default, in "
                "which case it makes no Base call at all and the reader emits the "
                "placeholder it always has. Every failure degrades to that placeholder."
            ),
        ),
        levels=_base_embedded_deep_read_levels(),
        operations=[
            Operation(
                name="deep_read_embedded_base",
                projected_from="larkdocio.base.embed",
                impl=_deep_read_embedded_base,
            ),
        ],
    )


def _surface_base_write() -> Surface:
    return Surface(
        title=(
            "Base (bitable) record-write engine — plan-gated record create / update / "
            "delete; the rows, not the shape"
        ),
        domain="base",
        mode="write",
        credentials=_write_credentials(
            note=(
                "Write app (WRITE pair, NO fallback — least-privilege). WHAT THIS SURFACE "
                "WRITES: RECORDS — the rows. Changing a Base's SHAPE is a separate, "
                "separately-gated surface, base-schema-write, with its own operations, its "
                "own contracts and its own live ring; no operation here creates, renames, "
                "converts or deletes a field, a table, a view or a Base itself, so the "
                "schema THIS engine plans against is the one it read, and a shape change "
                "made through the other surface is a change this engine's next plan reads "
                "rather than one it makes. Every one of the six record families runs on "
                "the WRITE pair "
                "against the one scope on this surface's per-operation rows, which is "
                "authored in larkdocio.permissions and nowhere else. THE GUARD NEEDS TO "
                "READ: applying a plan takes BOTH a write client and a read client, "
                "because this API has no If-Match — the compare-and-swap is client-side, "
                "so the engine reads table.revision on the WRITE pair before it writes, "
                "and a guard that cannot read cannot compare. Those reads land on the same "
                "endpoint family as the writes, so they add no scope the row above does "
                "not already carry; what they do add is a requirement that the WRITE app "
                "be able to read the table it is writing. EIGHT KINDS OF CELL CANNOT BE "
                "WRITTEN AT ALL — a formula, a lookup, a stage, an auto-number and the "
                "four created/modified time and user fields are computed or opaque, the "
                "server owns their value, and this engine refuses them LOCALLY before any "
                "call rather than letting a write answer success and store nothing. A "
                "PERSON OR GROUP CELL IS WRITTEN BY ID, never by name — and an "
                "id-written cell renders a FULL NAME CHIP in the product, so the display "
                "is unaffected and it is the addressing alone that is limited. Three "
                "honest sources of an id: harvest one from a Base read, which keeps the "
                "raw id on the structured form for every person object it read; supply "
                "one the caller already holds; or, for the ACCOUNT OWNER's own id, the "
                "name lookup in larkdocio.contacts, which resolves to exactly one id or "
                "refuses in a typed way. Turning another USER's name into an id is the "
                "thing this library cannot do today: on the tenant its directory search "
                "was measured against, every query returns only the account owner, and "
                "the documented email-or-mobile route HAS been called from here — it "
                "resolved another user's open_id from that second user's email, reaching "
                "past the search rather than being refused — but that reach is measured "
                "at two identifiers on one tenant, not established for an arbitrary "
                "member; the verb that makes that call is larkdocio.contacts."
                "resolve_colleague, an email or a mobile in and exactly one id or a typed "
                "refusal out, never a name. No roster, no "
                "directory dump and no closest match ships in their place, and nothing "
                "here asks for a grant to reach one. THE ROUND TRIP IS ASYMMETRIC BY "
                "DESIGN: a person cell round-trips through the MODEL, which keeps the raw "
                "id it read, and NOT through the MARKDOWN, which emits the display name "
                "only — so a cell rendered to Markdown and parsed back is a name, and a "
                "name is not an id. Chat ids are the easier twin, obtainable in band, and "
                "a group-chat cell takes the same id shape — but no chat lister ships "
                "here either: that is a different endpoint family with its own grant, and "
                "this surface does not buy one for the sake of a disclosure. AN "
                "ATTACHMENT CELL NOW HAS ITS OWN FILE LEG, out of band and "
                "beside the record write rather than part of it: media is uploaded (as a "
                "file or as an image), the returned file token is what the cell is written "
                "from, and the same token downloads back so a caller can verify the bytes "
                "by hash rather than trusting a success code. TWO THINGS ABOUT IT ARE NOT "
                "NEGOTIABLE. It reaches the DRIVE endpoint family, not the Base one, so "
                "holding only the Base permissions says nothing about whether it will be "
                "permitted — the per-operation rows below carry that separately. And an "
                "upload is PERMANENT: the file token survives the deletion of the table, "
                "and of the Base itself, and no interface in Lark's open API purges "
                "uploaded media at all. Nothing here simulates a purge or implies one is "
                "possible. The short-lived signed links a cell reads back are treated as "
                "credentials: never logged, never stored, never rendered."
            ),
        ),
        safety_contracts=[
            "plan-gated", "dry-run-mandatory", "STALE_BASE",
            # LD-254's house invariant — the id is imported, never re-spelled, and the
            # Base package earns it by carrying the disposition boundary that makes it
            # true (larkdocio.base.disposition).
            APPLY_LOG_COMPLETE,
        ],
        operations=_base_write_operations(),
        legs=[
            # LD-268 — the attachment OUT-OF-BAND leg. Legs rather than operations,
            # deliberately: neither is a record write, neither rides the plan gate, and
            # appending them to the record registry would flip what that registry says
            # about itself. They are here because they are API-USING on this surface's own
            # credential pair, and a leg that reaches a DIFFERENT endpoint family than
            # every operation beside it is exactly the thing a per-operation permission
            # row exists to surface.
            Operation(
                name="upload_attachment_media",
                projected_from="larkdocio.base.media",
                resolves_by=_resolution.ENTRY_POINT,
                impl=_BaseMediaClient.upload,
            ),
            Operation(
                name="download_attachment_media",
                projected_from="larkdocio.base.media",
                resolves_by=_resolution.ENTRY_POINT,
                impl=_BaseMediaClient.download,
            ),
            # LD-450 — the address a PERSON can be sent. A third leg rather than a widened
            # download: it reaches a different endpoint family again (the drive META family,
            # not medias), so it carries its own permission row, and it is a READ that mints
            # nothing where the upload above mints permanent residue.
            Operation(
                name="permalink_attachment_media",
                projected_from="larkdocio.base.media",
                resolves_by=_resolution.ENTRY_POINT,
                impl=_BaseMediaClient.permalink,
            ),
        ],
        gate_coverage=_base_write_gate_coverage(),
    )


def _surface_base_schema_write() -> Surface:
    return Surface(
        title=(
            "Base (bitable) schema-write engine — plan-gated column, table and view "
            "authoring, with every delete INSIDE a Base behind a loss preview and a consent "
            "fence, plus the whole-object delete that trashes the Base itself"
        ),
        domain="base",
        mode="write",
        credentials=_write_credentials(
            note=(
                "Write app (WRITE pair, NO fallback — least-privilege). WHAT THIS SURFACE "
                "CHANGES: a Base's SHAPE. It creates, renames and copies a Base; creates, "
                "renames and deletes tables; creates, edits, converts and deletes COLUMNS; "
                "and creates, updates and deletes VIEWS. What it configures on a view is its "
                "NAME, its persistent FILTER, its HIERARCHY field and the columns it HIDES — "
                "each verified by read-back, never by a success code. Hiding a column hides "
                "it from a human and marks it `is_hidden` on a per-view field read; it "
                "narrows no read and every value stays readable. GROUPING and a saved "
                "view-level SORT are still not knobs offered here — both answer code:0 and "
                "store nothing — and a form view is out by "
                "this library's own policy rather than by any refusal from Lark. A COLUMN "
                "IS ONLY CREATED FOR A KIND ON THE ALLOW-LIST published beside this note, "
                "and that list is the server's own vocabulary, transcribed from the "
                "violations it returns rather than curated: a lookup, a stage, an email or "
                "a button column is refused LOCALLY, before any call, with what to do "
                "instead — for the ones the API will never author, copying a Base that "
                "already has the column is the route. A FORMULA COLUMN IS ONLY CREATED "
                "FOR AN EXPRESSION THAT REFERENCES NOTHING, because that is the only kind "
                "measured to COMPUTE through this API: the create is accepted either way "
                "and the server even rebinds a column reference into its own id form, but "
                "the cell of a referencing formula is then absent from every record, on "
                "both read routes, before and after a write. So a referencing expression "
                "is refused locally, with zero calls, and the fix is to author that "
                "formula in the product — a column that reads as authored and computes "
                "nothing is worse than a refusal. A COLUMN'S KIND IS ONLY CONVERTED "
                "FOR A PAIR A CAPTURE COVERS: a conversion rewrites every value in the "
                "column server-side and cannot be undone, so a pair nobody has watched "
                "happen to a populated cell refuses rather than guesses. THE REVISION "
                "GUARD IS NOT UNIFORM AND SAYS SO: a column op rides the table's own "
                "revision, an app-scoped or view-scoped op has no such anchor to ride and "
                "carries no guard at all; those are verified by READ-BACK instead, and a "
                "success code is never taken as evidence — one property write on this API "
                "answers success and persists nothing, which is why every write here is "
                "re-read. AND EVERY DELETE COSTS TWO ACTS: the plan enumerates what would "
                "be lost across the WHOLE Base, including the mirror of a two-way link in "
                "a table you did not name, and applying it needs consent minted from that "
                "same plan. A loss that cannot be enumerated is refused, not warned about. "
                "THE ONE DELETE THAT IS NOT PLAN-GATED IS THE ONE THAT REMOVES THE WHOLE "
                "BASE, and it says so rather than pretending otherwise: `delete_base` "
                "(published under this surface's `lifecycle`, beside the create it undoes) "
                "trashes the Base and everything in it in one act, on a DRIVE endpoint. It "
                "carries no consent token because it has no plan to mint one from — consent "
                "here is consent to an ENUMERATED loss, and a whole Base's loss is every "
                "table, column, record and view it holds. It is the same whole-object gate "
                "`delete_document` and `delete_spreadsheet` ride, not a third shape. It is a "
                "TRASH, NOT A PURGE: a human can restore from the product, no open-API verb "
                "purges anything here, and after a landed delete the Drive metadata route "
                "still resolves the token — so a `code: 0` is acceptance and the proof is "
                "addressing the app_token again, where the bitable side answers that it is "
                "gone. `base_is_gone(exc)` spans both codes, which is what a `finally` needs. "
                "No attachment upload, no link resolution and no comment write ships here."
            ),
        ),
        safety_contracts=[
            "plan-gated", "dry-run-mandatory", "caller-supplied-destination",
            DESTRUCTIVE_CONSENT_REQUIRED, CROSS_TABLE_LOSS_PREVIEW,
            REVISION_GUARD_FIELD_SCOPED_ONLY,
            APPLY_LOG_COMPLETE,
        ],
        operations=_base_schema_write_operations(),
        legs=[
            # LD-291 — the GUIDED COLUMN-TYPE MIGRATION. A leg rather than an operation,
            # deliberately and for the reason legs exist: it is not a registered schema op
            # and appending it to that registry would claim an endpoint the API does not
            # have. It reaches NO endpoint of its own — every call it makes is one of the
            # operations above, through their own plan gates — which is exactly what makes
            # it safe to publish here: a consumer meets it at the door, and its permission
            # requirement is the union of the ops it composes rather than a second claim.
            Operation(
                name="migrate_field_type",
                projected_from="larkdocio.base.field_migration",
                resolves_by=_resolution.ENTRY_POINT,
                impl=_field_migration.apply_field_migration,
            ),
        ],
        field_authoring=_base_field_authoring(),
        gate_coverage=_base_schema_write_gate_coverage(),
        # The WHOLE-OBJECT delete. A lifecycle call rather than an operation, for the reason
        # lifecycle exists: it has no plan, no anchor and no target inside the Base, because it
        # *is* the Base — the same distinction that puts `delete_spreadsheet` here and
        # `DeleteTab` under `operations`. The create half is `create_app`, a registered
        # plan-gated schema op on a bitable endpoint, so it stays under `operations`; naming it
        # in both keys would collapse its two permission rows into one.
        lifecycle=_lifecycle_operations(
            _BaseSchemaClient, "larkdocio.base.schema_client.BaseSchemaClient",
            _BASE_SCHEMA_LIFECYCLE_OPS),
    )


#: The docx write surface's own safety contracts — hoisted out of the surface constructor
#: so the compound-workflow row can filter its plan-gate list from the SAME list rather
#: than re-spelling three contract ids.
_DOCX_WRITE_SAFETY_CONTRACTS = [
    "plan-gated", "dry-run-mandatory", "STALE_ANCHOR", "STALE_DOCUMENT",
    "exactly-one-or-refuse",
    # LD-493 — the destination is the caller's on every create-class verb, refused locally
    # when it is missing. Here because create_document is one of them.
    "caller-supplied-destination",
    # The two comment-write contracts: creation exists only whole-document (and an
    # anchored request is refused, not downgraded), and removal is sole-author-only
    # and whole-thread-or-nothing.
    "comment-create-whole-document-only",
    "comment-removal-sole-author-or-refuse",
    # LD-151 (dogfood F14) — the batch-semantics contract that had no home: one
    # tree, one batch, so a batch cannot depend on its own writes (and the
    # not-found detail says so when the anchor text is the batch's own).
    "one-tree-one-batch",
    # LD-172 (round-3, the re-scoped F8) — the three-path reviewer-anchor contract
    # LD-163/LD-170 landed, plus the plan-side disclosure on the path that proceeds.
    # It had no named home, so "which of my three edit shapes is safe on commented
    # text?" was answerable only by reading prose.
    "comment-anchors-honored-or-refused",
]


def _surface_docx_write() -> Surface:
    # Bound once each, because the compound-workflow row below is DERIVED from them: its
    # entry point and compiled families come off this very ``Reconciliation``, and its
    # plan-gate list is filtered from this very contract list. Nothing is typed twice.
    reconciliation = _docx_reconciliation()
    safety_contracts = _DOCX_WRITE_SAFETY_CONTRACTS
    return Surface(
        title="docx writeback engine — plan-gated block-level edits",
        domain="docx",
        mode="write",
        credentials=_write_credentials(
            note=(
                "Write app (WRITE pair, NO fallback — least-privilege). The engine puts "
                "NO restriction on the target: a consumer may write to any document its "
                "WRITE app can reach. larkdocio's own live write gates write only to "
                "disposable, API-created docs the harness provisions itself — that is "
                "this project's own test-suite policy, not an engine restriction. The "
                "COMMENT ops on this surface needed NO ADDITIONAL GRANT: every call in "
                "the family — creating a whole-document comment, listing a thread's "
                "replies, deleting one — answered on the write app's existing granted "
                "set, and nothing has ever been observed demanding a scope for them (the "
                "one refusal the family produces, 1069303, is about WHO is asking, not "
                "about a missing scope). So the requirement is recorded as unknown with "
                "that reason rather than guessed — see this surface's per-operation rows. "
                "What no scope buys is a comment author's display name: the directory "
                "answers 41050 for the app's own bot id, and this library requests no "
                "scope to change that. AND ONE THING NO SCOPE ON THIS SURFACE BUYS, "
                "because the attachment leg below is where a consumer meets it: "
                # QUOTED from its one authoring rather than paraphrased here — the
                # machine-readable answer and the prose say the same sentence.
                + _MEDIA_TOKEN_NOT_INDEPENDENTLY_SHAREABLE
            ),
        ),
        safety_contracts=safety_contracts,
        operations=_docx_write_operations(),
        legs=[
            # LD-433 — the IMAGE-authoring leg. A leg rather than an operation because it is
            # not plan-gated: it needs bytes, so it does not go through dry_run → Plan →
            # apply. It reaches the docx block family AND the drive media family, and the
            # second of those is the reason this entry exists at all — a consumer holding the
            # document scopes would otherwise discover the media requirement at the call.
            Operation(
                name="put_image_in_document",
                projected_from="larkdocio.write.media",
                impl=_put_image_in_document,
            ),
            # The 📎 ATTACHMENT leg. Same reason it is a leg and not an operation, and the
            # same two families reached — plus the wrapper resolution, which is why it is one
            # op rather than a recipe a caller assembles and gets wrong.
            Operation(
                name="put_file_in_document",
                projected_from="larkdocio.write.media",
                impl=_put_file_in_document,
            ),
            # LD-711 — the two PUBLIC ``WriteClient`` reads a consumer is sent to by name and
            # that were declared nowhere while the census exempted the whole class:
            # ``get_block`` (one live block, which the guide's in-cell picture and attachment
            # recipes read back) and ``read_document_revision`` (the document's revision
            # anchor, the scalar the whole-document compare-and-swap compares). Both reach
            # the docx block family on this surface's own credential pair. LEGS rather than
            # operations: each is one call a caller makes by name, not a plan-gated edit.
            Operation(
                name="get_block",
                projected_from="larkdocio.write.client.WriteClient",
                impl=_DocxWriteClient.get_block,
            ),
            Operation(
                name="read_document_revision",
                projected_from="larkdocio.write.client.WriteClient",
                impl=_DocxWriteClient.read_document_revision,
            ),
        ],
        reconciliation=reconciliation,
        workflows=[
            _docx_update_workflow("docx-write", reconciliation, safety_contracts),
        ],
        lifecycle=_lifecycle_operations(
            _DocxWriteClient, "larkdocio.write.client.WriteClient",
            _DOCX_LIFECYCLE_OPS),
        content_constraints=_docx_content_constraints(),
        gate_coverage=_docx_write_gate_coverage(),
        # The register is authored ONCE, as data, beside the engine it describes
        # (:mod:`larkdocio.write.absences`) and projected here verbatim. A row typed
        # into this file instead would be a second place to look for the same answer —
        # which is the shape of the defect the rows themselves record, one layer up.
        absences=list(_DOCX_WRITE_ABSENCES),
    )


def _surface_sheets_write() -> Surface:
    return Surface(
        title="Sheets writeback engine — plan-gated value / rich / structural writes",
        domain="sheets",
        mode="write",
        credentials=_write_credentials(
            note=(
                "Write app (WRITE pair, NO fallback — least-privilege). Reuses the WRITE "
                "app. The engine puts NO restriction on the target: a consumer may write "
                "to any spreadsheet its WRITE app can reach. larkdocio's own live write "
                "gates write only to self-provisioned disposable spreadsheets — that is "
                "this project's own test-suite policy, not an engine restriction."
            ),
        ),
        safety_contracts=[
            "plan-gated", "dry-run-mandatory", "STALE_SHEET", "exactly-one-or-refuse",
            "caller-supplied-destination",
            # LD-148 — the disposition/apply-log completeness invariant (round-2 T27),
            # a HOUSE INVARIANT since LD-254: the id is imported, never re-spelled, so
            # this list cannot drift from the one authoring in ``_contracts``.
            APPLY_LOG_COMPLETE,
        ],
        operations=_sheets_write_operations(),
        legs=[
            # The PLAN-TIME leg, API-using in its own right: building a plan reads the
            # target range AND — for a rich cell carrying an @mention — proves the
            # mentioned ids exist with one contacts read. That read is made on the WRITE
            # pair, so the WRITE app is the one that needs the contacts scopes, and it
            # discloses itself as unavailable rather than silently skipping when it cannot
            # run. Nothing said so anywhere: the one scope requirement a spreadsheet write
            # can hit outside the spreadsheet family was written down nowhere.
            Operation(
                name="dry_run",
                projected_from="larkdocio.sheets.ops",
                impl=_sheets_dry_run,
            ),
            # LD-447 — the IN-CELL IMAGE leg. A leg rather than an operation, and for the
            # same reason the docx image op is one: it needs BYTES, so it does not go
            # through dry_run → Plan → apply and is not under STALE_SHEET (whose
            # interaction with this route is unmeasured). Stating that here is the point —
            # a row under `operations` would inherit a plan-gating promise this call does
            # not keep. It reaches the spreadsheet values family AND the drive media family
            # on the optional byte-verification leg, and the second of those is why this
            # entry exists at all: a consumer holding only the spreadsheet grants would
            # otherwise discover the media requirement at the call.
            Operation(
                name="put_image_in_sheet",
                projected_from="larkdocio.sheets.media",
                impl=_put_image_in_sheet,
            ),
            # LD-448 — the FLOAT IMAGE leg: a picture anchored OVER a range, which is a
            # DIFFERENT PRODUCT from the in-cell image above (that one IS the cell's value).
            # A leg for the same reason: it needs bytes, so no dry_run → Plan → apply and no
            # STALE_SHEET. It reaches THREE families — the drive media upload/download, and
            # the sheets v3 float-image collection — and the upload is the one a consumer
            # holding only the spreadsheet grants would meet at the call.
            Operation(
                name="put_float_image_in_sheet",
                projected_from="larkdocio.sheets.media",
                impl=_put_float_image_in_sheet,
            ),
            # Removal ships WITH the create: without it the route cannot be exercised
            # reversibly and every run leaves a picture behind. Its verdict is the same fresh
            # query, never the delete's own code 0.
            Operation(
                name="remove_float_image_from_sheet",
                projected_from="larkdocio.sheets.media",
                impl=_remove_float_image_from_sheet,
            ),
            # LD-711 — the PUBLIC ``SheetsWriteClient`` calls the guide's recipes make by name
            # and that were declared nowhere while the census exempted the whole class. Six
            # are READS on this surface's own credential pair — the tab listing, the tab's
            # float images (the float-image route's verdict read), a range's values (as a
            # matrix and as the whole value range), a tab's geometry and its frozen panes.
            # ``put_values`` is the one WRITE among them, and it is a direct call with NO
            # plan: no dry_run, no STALE_SHEET, no refusal set — the guide uses it to put a
            # scratch value in a disposable workbook and to clear a cell. Declaring it does
            # not make it plan-gated; it makes the call a consumer is already shown visible,
            # with its requirement, rather than present in the guide and absent here.
            Operation(
                name="put_values",
                projected_from="larkdocio.sheets.write_client.SheetsWriteClient",
                impl=_SheetsWriteClient.put_values,
            ),
            Operation(
                name="query_tabs",
                projected_from="larkdocio.sheets.write_client.SheetsWriteClient",
                impl=_SheetsWriteClient.query_tabs,
            ),
            Operation(
                name="query_float_images",
                projected_from="larkdocio.sheets.write_client.SheetsWriteClient",
                impl=_SheetsWriteClient.query_float_images,
            ),
            Operation(
                name="read_values",
                projected_from="larkdocio.sheets.write_client.SheetsWriteClient",
                impl=_SheetsWriteClient.read_values,
            ),
            Operation(
                name="read_value_range",
                projected_from="larkdocio.sheets.write_client.SheetsWriteClient",
                impl=_SheetsWriteClient.read_value_range,
            ),
            Operation(
                name="read_sheet_geometry",
                projected_from="larkdocio.sheets.write_client.SheetsWriteClient",
                impl=_SheetsWriteClient.read_sheet_geometry,
            ),
            Operation(
                name="read_frozen_panes",
                projected_from="larkdocio.sheets.write_client.SheetsWriteClient",
                impl=_SheetsWriteClient.read_frozen_panes,
            ),
        ],
        lifecycle=_lifecycle_operations(
            _SheetsWriteClient, "larkdocio.sheets.write_client.SheetsWriteClient",
            _SHEETS_LIFECYCLE_OPS),
    )


def _with_contract_census(surfaces: dict, contracts: dict) -> dict:
    """ONE census of which surfaces carry which safety contract, readable in both directions
    (LD-707). The catalogue's ``applies_to`` is the source. Each surface publishes its own
    authored list, in its authored order, plus every catalogue contract that names the surface
    and that list omitted, in catalogue order. A surface naming a contract whose ``applies_to``
    does not name it back is refused rather than published: the two halves of
    ``capabilities()`` would otherwise give two answers to "which surfaces carry C"."""
    out = {}
    for sid, surface in surfaces.items():
        authored = list(surface.safety_contracts)
        for cid in authored:
            assert cid in contracts and sid in contracts[cid].applies_to, (
                f"surface {sid} declares safety contract {cid!r}, but the catalogue's "
                f"applies_to does not name it")
        derived = [cid for cid, contract in contracts.items()
                   if sid in contract.applies_to and cid not in authored]
        out[sid] = dataclasses.replace(surface, safety_contracts=authored + derived)
    return out


def _build() -> Capabilities:
    surfaces = {
        "docx-read": _surface_docx_read(),
        "docx-comments-read": _surface_docx_comments_read(),
        "contacts-read": _surface_contacts_read(),
        "drive-read": _surface_drive_read(),
        "drive-versions-write": _surface_drive_versions_write(),
        "drive-access-write": _surface_drive_access_write(),
        "drive-files-write": _surface_drive_files_write(),
        "drive-folders-write": _surface_drive_folders_write(),
        "sheets-read": _surface_sheets_read(),
        "sheets-embedded-deep-read": _surface_sheets_embedded_deep_read(),
        "base-read": _surface_base_read(),
        "base-comments-read": _surface_base_comments_read(),
        "base-embedded-deep-read": _surface_base_embedded_deep_read(),
        "base-write": _surface_base_write(),
        "base-schema-write": _surface_base_schema_write(),
        "docx-write": _surface_docx_write(),
        "sheets-write": _surface_sheets_write(),
    }
    # COLLECTED, not authored here: a compound workflow is written down once, beside the
    # surface that answers it, and the top-level section is the index the README's
    # discovery order lands on. A row claiming a surface it was not found under would be a
    # pointer nobody could follow, so it is refused rather than published.
    safety_contracts = _safety_contracts()
    surfaces = _with_contract_census(surfaces, safety_contracts)
    workflows = {}
    for surface_id, surface in surfaces.items():
        for workflow in surface.workflows:
            assert workflow.surface == surface_id, (
                f"workflow {workflow.id} claims surface {workflow.surface} but is "
                f"registered on {surface_id}"
            )
            workflows[workflow.id] = workflow
    return Capabilities(
        version=__version__,
        # The scope lists on every ``credentials`` above are PLACEHOLDERS — this pass
        # replaces them with the union of each surface's own operations' derived
        # requirements, so a scope string is asserted in exactly one place.
        surfaces=_with_permissions(surfaces),
        flags=_flags(),
        safety_contracts=safety_contracts,
        docs=_docs(),
        entry_points=_entry_points(),
        workflows=workflows,
    )


def capabilities(surface: Optional[str] = None, *, full: bool = False) -> dict:
    """The larkdocio capability registry as a JSON-serializable ``dict`` — its **summary**,
    one surface, or all of it.

    A projection over the op registries (``write/ops.py`` + ``sheets/ops/``), the read
    clients, and the parser — never a hand-list where a registry exists.

    **With no argument you get the summary**: every surface, every operation NAME with its
    kind, and the scopes each surface is **known** to need, each surface's
    ``unknown_requirements`` naming the endpoints whose requirement was never observed so an
    empty scope list is not read as *needs no permission* — names only, never prose, and more
    than 20× smaller than the whole registry (the ratio its size guard enforces on every run). It carries a ``reading`` block that spells
    the next call, so a first call leaves a caller knowing their second. The summary is
    **derived from the full payload on every call** and holds no fact of its own: an operation
    cannot be in the registry and missing from it.

    **Pass ``full=True`` for the whole registry.** That is the ~400 KB answer, and it is the
    one to read when the question is *"what exactly does this operation require"*. It
    answers, from itself alone: **what can I do** — ``surfaces[<id>]["operations"]``, the
    COMPLETE list of that surface's call sites, each row carrying the ``kind`` that says what
    sort of call it is (``operation``, a kind the surface's engine dispatches; ``leg``, an
    API-using call that is not one of those; ``lifecycle``, a call that creates or destroys
    the file itself). **One key, every verb**: there is nowhere else on a surface for a call
    site to hide, which is what stopped a caller concluding the library cannot put an image in
    a document because ``put_image_in_document`` was under a sibling key they never read. That
    one list is also what the permission registry is built from, so an operation cannot be in
    one and absent from the other,
    **and what TASK am I actually here for** (``workflows`` — the compound workflows that
    compile DOWN to those operations rather than being one of them, each naming its module,
    the request families it compiles to, the plan gate they go through and the guide section
    that teaches it; a surface that answers one carries a stub under its own ``workflows``
    key pointing at the row. A workflow row is descriptive and guide-pointer-shaped, NOT
    endpoint-derived, and it says so in the row — ``operations`` keeps its projection
    guarantee undiminished),
    **what can I CREATE vs only edit** (``surfaces["docx-write"]["content_constraints"]``),
    **which block types survive a READ, what they turn into, and how lossily**
    (``surfaces["docx-read"]["block_read_support"]`` — one row per docx block type, with the
    lossiness vocabulary shipped beside the rows),
    **what creds do I need** (``surfaces[<id>]["credentials"]``), **what opt-in flags
    exist** (``flags``), **what safety contracts govern the write surfaces**
    (``surfaces[<id>]["safety_contracts"]`` + the ``safety_contracts`` catalog), **where
    those contracts are proved live** (``surfaces["docx-write"]["gate_coverage"]``), and
    **what documentation ships in the wheel and how to read it** (``docs`` — one row per
    packaged **consumer** document, each naming the accessor that returns its text, so no
    consumer has to discover a document through ``dir()``; the wheel's one contributor doc,
    ``blocks/BLOCK_TYPES.md``, deliberately has no accessor and no row), and **what I can call
    from the top level and what it costs** (``entry_points`` — one row per symbol
    ``larkdocio.__all__`` exports, projected off it, which is where the advisory permission
    pre-check ``larkdocio.preflight`` is indexed; documents live in ``docs``, callables here).
    It round-trips through ``json.dumps``/``loads`` losslessly (JSON-native types only).

    **The prose each operation's scope requirement rests on is carried ONCE.** A scope row
    inside an operation is the scope **string**; the evidence that established it, what its
    absence looks like and how firmly it is verified live in ``scope_evidence`` under that
    string, and the reasons a requirement is *not* known live in ``unknown_requirements``
    under the endpoint they belong to. Nothing is dropped — the same paragraphs are all still
    here, they are simply not re-typed once per operation.

    **Pass ``surface`` for one surface's full row** — ``capabilities(surface="docx-write")``
    is that surface exactly as ``full=True`` carries it, which is how a caller reads a
    surface's detail without holding the whole registry. An unknown id raises
    :class:`ValueError` naming **every** surface there is, so recovering takes no second
    call. ``surface`` together with ``full=True`` is two requests in one and also raises
    :class:`ValueError`.

    **What the middle rung does NOT carry.** ``capabilities(surface=...)`` returns that
    surface's row and nothing else, so the scope strings in its ``permissions`` blocks are
    **keys into ``scope_evidence`` / ``unknown_requirements``, and those catalogs are top-level
    — they are not in the returned row.** Resolving a key is therefore a ``full=True`` call:
    ``capabilities(full=True)["scope_evidence"][scope]`` for a scope's evidence,
    ``[...]["unknown_requirements"][endpoint]`` for an endpoint's honest unknown. Ask for
    ``full=True`` once if you want the row and its evidence out of the same payload.

    **Reading it as a human:** it is a nested dict, so ``print(capabilities(full=True))`` is a
    multi-hundred-kilobyte single line. Print
    ``json.dumps(capabilities(), indent=2)`` instead — see ``larkdocio.guide()``.
    """
    if full and surface is not None:
        raise ValueError(
            f"capabilities(surface={surface!r}, full=True) asks for one surface and for the "
            "whole registry at once. Pass surface= for one of them, or full=True for all of "
            "it — not both; capabilities() with neither returns the summary, which names "
            "every surface that can be asked for."
        )
    payload = _build().to_dict()
    if full:
        return payload
    if surface is not None:
        try:
            return payload["surfaces"][surface]
        except KeyError:
            raise ValueError(
                f"unknown surface {surface!r}. capabilities() knows: "
                + ", ".join(repr(sid) for sid in payload["surfaces"])
                + ". capabilities() with no argument returns the summary of all of them."
            ) from None
    return _summary(payload)
