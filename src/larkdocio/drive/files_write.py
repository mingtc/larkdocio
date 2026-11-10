"""larkdocio.drive.files_write — put a FILE in a folder and get its openable URL.

The half of *"for the full details, open the attached file"* that is not a document: a real
file, living in a folder somebody named, with a **URL a human can open**. Three calls, and
each one is here for a reason a caller can check:

1. ``POST drive/v1/files/upload_all`` with ``parent_type: explorer`` and ``parent_node`` =
   **the caller's folder token** — the bytes;
2. ``POST drive/v1/metas/batch_query`` with ``with_url: true`` and ``doc_type: file`` — the
   file's own web URL, **asked for, never constructed**;
3. ``GET drive/v1/files/{token}/download`` — the bytes again, compared **by sha256 and
   length** against what went up.

**A LARGE file goes up in CHUNKS, and the caller does not have to know.** Above
:data:`SINGLE_SHOT_MAX_BYTES` the same op takes the chunked family instead —
``upload_prepare`` → ``upload_part`` (once per block) → ``upload_finish`` — and returns the
same :class:`LinkedFile` with the same hash-verified verdict. **THE SHAPE, AND THE ONE THAT
WAS REJECTED:** this is **size-triggered auto-chunking inside the shipped
:func:`put_file_in_folder`** — one op, one caller-visible contract, the partition invisible.
The alternative was **a sibling op** (a second public upload verb for large files); it was
rejected because nothing in the measurement forces it — there is no resumability to express
and no progress callback in the contract — and because a second op would give a caller two
upload recipes for one ask, which is exactly the duplication the consumer guide is held
against. What the chunked route adds to the *return* is one honest fact, ``parts``: how many
blocks the bytes actually went up in, **reported, never chosen**.

**THE PARTITION IS THE SERVER'S, AND IS ASKED FOR EVERY TIME.** ``upload_prepare`` answers
``block_size`` and ``block_num``; this module partitions by that answer and by nothing else.
Measured on one tenant on one day, the answer was ``block_size`` **4194304** for *both* a
130-byte file and a *declared* 64 MiB, while ``block_num`` moved **1 → 16** with the declared
size — so the server sizes the blocks and the caller counts them. That number is cited here as
**evidence and is not compiled in anywhere**: a client that assumed it would be right today on
that tenant and **a latent bug the day it is not**.

**THE DESTINATION IS ALWAYS THE CALLER'S.** There is no default folder, no root-folder
resolution and **no folder-creating call anywhere in this module** — a permanent write into a
destination this library picked would be a surprise, and organising a Drive is a different
product. A missing folder token is refused **locally, before any call**.

**TRANSFORMED, NOT DELETED.** The sentence above once read *"no folder-creating
call anywhere in this library"*, and **the reason it was written is unchanged and still binds
here**: this module picks no destination, resolves no root and creates nothing to put a file
in. What is superseded is only the **library-wide** half of the conclusion — a product ruling
of 2026-08-14 opened **one** organize verb, :meth:`larkdocio.drive.folders_write.
DriveFoldersWriteClient.create_folder`, on a surface of its own with its own credentials note.
A caller who needs a folder to upload into makes that create themselves and passes the token
back in; this module still will not create one for them, and the rest of the organize rung —
move, rename, copy, folder delete, shortcut — remains unshipped
(:data:`larkdocio.drive.folders_write.R3_NOT_SHIPPED`, one reason per row).

**THE URL IS A PERMALINK, NOT A SIGNED LINK, AND THE TWO ARE DIFFERENT PRODUCTS.** What
:class:`LinkedFile` carries is the file object's own address —
``https://<host>/file/<token>`` — which does not expire on a timer and is not a credential.
It is **not** described with the lifetime language of a signed link anywhere here, because
that would be a claim about a different thing. What *is* credential-class is the
short-lived signed link the **upload's own answer** happens to carry: it is read by nothing,
returned by nothing, logged by nothing and never persisted, exactly as the attachment leg
treats the two ephemeral keys it meets (:data:`larkdocio.base.media.EPHEMERAL_ATTACHMENT_KEYS`).

**Access is NOT granted here.** A permalink is an address, not an admission: whoever opens it
still needs access to the file, and this module ships no sharing verb for a file object. The
docx grant surface is fenced to documents.

**BUT THIS ROUTE IS THE SHAREABLE ONE — and that is why a caller ends up here rather than
attaching the file to a document body.** <<MEDIA_TOKEN_SHAREABILITY>>

**RESIDUE — and the difference from media, which is the whole point of the disclosure.**
Media bytes uploaded into a document are **permanent and unpurgeable**: **no route in Lark's
open API purges drive media — measured, not assumed** (the nine spellings tried, the fourteen
sends and the scope the claim may not exceed are in
:data:`larkdocio.base.media.NO_ROUTE_PURGES_DRIVE_MEDIA`), and deleting the document does not
remove them. A file uploaded into a
folder is **not** in that class — it is a real Drive object, and :meth:`DriveFilesWriteClient.
delete` removes it. But *removes* has an edge, and it is measured rather than assumed: the
delete is **trash, not purge**, no API undo was measured, and after a successful delete the
**metadata route still resolves the token**. So the honest sentence is not "uploads are
permanent" and not "a file can be made to vanish" — it is that the two uploads are different,
and that this one can be trashed. Both halves are said rather than the safer one.

**THE CHUNKED ROUTE HAS A THIRD KIND OF LEFTOVER, AND IT IS DISCLOSED RATHER THAN DISCOVERED.**
A run that prepares an upload and sends parts but never reaches ``upload_finish`` leaves a
**pending upload transaction with no Drive object** — an ``upload_id`` and nothing a folder
listing, a metadata query or a delete can see. **No cancel verb was found in the SDK's drive v1
surface and none was called: this is `unmeasured, not "cannot"`** — whether one exists under
another name, another API version, or the web client's internal API has not been looked into.
The transaction's **expiry is unmeasured** too. So the failure path here *says what it left
behind* (:class:`DriveFileChunkedUploadError` carries the ``upload_id``, how many parts went
and how many the server declared) instead of raising a bare error and letting a caller find out
some other way.

**Bytes are hashed, never inspected.** The round-trip check is
:func:`larkdocio.base.media.verify_round_trip` — the one definition of *"the bytes that came
back are the bytes that went up"* in this library, reused rather than restated. Nothing here
decodes, renders, logs or prints a payload.

**WRITE credentials only.** An upload is a write; the read pair is never consulted here and is
not named in this module. Whether ``upload_all`` succeeds on READ credentials is **unmeasured**
and is deliberately left open rather than quietly answered.

**What is measured, and what is UNMEASURED.** One tenant, a ``tenant_access_token``: a
**single-shot** upload of a small ``.html``; a **chunked upload** of a 130-byte file carried end
to end and hash-verified; and a **genuinely multi-part** upload — two blocks, one byte over the
declared ``block_size`` — carried end to end and hash-verified by the live gate. All into a
folder the harness itself created.
Therefore: ``user_access_token`` is untried, other tenants and regions are untried, every
``parent_type`` spelling other than ``explorer`` is unmeasured rather than refuted, and every
file type and size other than those uploaded is unmeasured — nothing here re-encodes, converts
or previews a file, and an ``.html`` in particular is **not** rendered inside a document by
uploading it. Whether *anything* renders is unmeasured. On the chunked family in particular:
``upload_part`` **does not require the optional Adler-32 ``checksum``** — it was omitted and
the parts were accepted — but that is **three parts across two uploads** (``seq: 0`` of a
130-byte ``.html``, and both blocks of a two-block ``.bin``), so this module omits it and says
plainly that the optional checksum **buys no guarantee this library can point to**; the sha256
read-back stays the definition of a round trip. **Omitting it means DELETING THE KEY, not
leaving it empty** — measured both ways round on this route, and the reason is in
:meth:`DriveFilesWriteClient.upload_part`. A **resumed** session and a **gap in ``seq``** were
never tried, and **part ordering is measured only for two blocks sent in order**. And
**whether ``upload_all``
succeeds on READ credentials is not answerable on the tenant everything here was measured on**
— on that tenant the READ and WRITE credential pairs named one app, so
a success would prove only that one app can upload and a failure is not available to be
observed; the question stays open rather than being manufactured. All of those are
**unmeasured, not refuted**.

**One measured swallow, stated because it will bite a reimplementer:** ``upload_all`` does
**not** police the ``parent_type`` / ``parent_node`` pairing — a mismatched pair was accepted
with ``code:0``. Whatever enforces the relation, it is not the upload, which is why this
module's verdict is the **read-back and the hash**, never the upload's own answer.
"""
# LD-467 TRANSFORMED the folder-creation absence in the docstring above (D-24: preserve the
# reason, supersede only the conclusion). The module-scoped claim — *no folder-creating call
# anywhere in THIS MODULE* — is unchanged and still true; the library-wide half is superseded by
# `larkdocio.drive.folders_write.DriveFoldersWriteClient.create_folder`, opened by the product
# ruling of 2026-08-14, which the docstring points a reader at. The issue id lives in this
# COMMENT rather than in the docstring because a docstring is consumer-reaching text where an
# issue id is internal dialect (tests/test_consumer_dialect_guard.py, in the source repository) — so
# the record is kept
# rather than dropped, and the consumer meets the date and the destination instead.
import io
import math
from dataclasses import dataclass
from typing import Optional, Tuple

from lark_oapi.api.drive.v1 import (
    BatchQueryMetaRequest,
    DeleteFileRequest,
    DownloadFileRequest,
    FileUploadInfo,
    MetaRequest,
    RequestDoc,
    UploadAllFileRequest,
    UploadAllFileRequestBody,
    UploadFinishFileRequest,
    UploadFinishFileRequestBody,
    UploadPartFileRequest,
    UploadPartFileRequestBody,
    UploadPrepareFileRequest,
)

from larkdocio.base.media import (
    EMPTY_UPLOAD_ADVICE,
    EMPTY_UPLOAD_REFUSED_CODE,
    MEDIA_MAX_CALLS_PER_WINDOW,
    MEDIA_RATE_WINDOW_SECONDS,
    MEDIA_TOKEN_NOT_INDEPENDENTLY_SHAREABLE,
    sha256_of,
    verify_round_trip,
)
from larkdocio.common.auth import WRITE_ENV, get_write_credentials
from larkdocio.common.metas import failed_reason
from larkdocio.drive.lookup import DUPLICATE_UPLOAD_BEHAVIOUR
from larkdocio.common.sdk_client import (
    require_credentials,
    resolve_rate_limiter,
    resolve_sdk_client,
)
from larkdocio.errors import LarkAPIError, api_error_as
# ONE definition of Lark's "this file is already in the trash" code, in this library. It was
# authored on the sheets surface (live-observed there 2026-07-30) and is IMPORTED rather than
# re-typed — the same reuse the Base schema client makes of it. Re-measured on the Drive file
# route 2026-08-15: a second delete of a token this library had just deleted answered it.
from larkdocio.sheets.write_client import FILE_ALREADY_DELETED_CODE

# QUOTED, never re-typed: one authoring of the shareability disclosure
# (``larkdocio.base.media``), read in by both media routes so they cannot drift apart.
__doc__ = (__doc__ or "").replace(
    "<<MEDIA_TOKEN_SHAREABILITY>>", MEDIA_TOKEN_NOT_INDEPENDENTLY_SHAREABLE)

#: **THE DESTINATION RULE, AUTHORED ONCE.** The module docstring's own sentence, in a constant
#: the discovery registry (``larkdocio.capabilities()``) **PROJECTS** — the same discipline
#: :data:`LIFECYCLE_OPS` below follows, and for a sharper reason. There were three statements of
#: this rule (this docstring, :meth:`DriveFilesWriteClient.upload`'s docstring, and the
#: registry's ``drive-files-write`` credentials note) and the registry's copy was the one that
#: went stale: the 2026-08-14 ruling opened :meth:`larkdocio.drive.folders_write.
#: DriveFoldersWriteClient.create_folder`, this module's docstring narrowed its claim from *the
#: library* to *this module*, and the hand-typed projection kept the superseded half — denying,
#: in the generated front door, a call listed in the same payload.
#:
#: **The scope word is the whole content of the fix**, so it is the one thing no copy may spell
#: for itself. A guard pins this constant as a substring of the docstring above (normalized for
#: Markdown emphasis and line wraps) and as a substring of the registry note, so a re-typed
#: fourth statement cannot drift from the three.
DESTINATION_IS_THE_CALLERS = (
    "There is no default folder, no root-folder resolution and no folder-creating call "
    "anywhere in this module — a permanent write into a destination this library picked "
    "would be a surprise, and organising a Drive is a different product. A missing folder "
    "token is refused locally, before any call."
)

#: The one ``parent_type`` spelling measured for a folder destination. Every other spelling
#: is **unmeasured rather than refused by Lark** — nothing is sent for one, because an upload
#: is a permanent object in somebody's Drive.
EXPLORER_PARENT_TYPE = "explorer"

#: The ``doc_type`` a metadata query uses for an uploaded file object.
FILE_DOC_TYPE = "file"

#: The endpoints this leg reaches, named as module constants so the permission derivation
#: resolves them from the source rather than from a runtime attribute, and cross-checked
#: against the pinned SDK request classes' own ``uri`` by a test.
FILES_UPLOAD_ALL_ENDPOINT = "/open-apis/drive/v1/files/upload_all"
FILES_UPLOAD_PREPARE_ENDPOINT = "/open-apis/drive/v1/files/upload_prepare"
FILES_UPLOAD_PART_ENDPOINT = "/open-apis/drive/v1/files/upload_part"
FILES_UPLOAD_FINISH_ENDPOINT = "/open-apis/drive/v1/files/upload_finish"
FILE_DOWNLOAD_ENDPOINT = "/open-apis/drive/v1/files/:file_token/download"
FILE_DELETE_ENDPOINT = "/open-apis/drive/v1/files/:file_token"
METAS_BATCH_QUERY_ENDPOINT = "/open-apis/drive/v1/metas/batch_query"

#: The largest payload this library will send in **one shot**, above which
#: :func:`put_file_in_folder` takes the chunked family instead.
#:
#: **THIS IS A LIBRARY POLICY, NOT A SERVER FACT — no server ever declared it.** It answers a
#: question the server is never asked: *whether* to chunk at all. It is emphatically **not** the
#: partition — the partition is ``upload_prepare``'s own ``block_size`` / ``block_num``, asked
#: for on every chunked upload and obeyed (see :meth:`DriveFilesWriteClient.upload_prepare`).
#:
#: **Why this number.** The single-shot route is measured only on small payloads, and the
#: chunked route is the one whose partition the server states, so the conservative choice is to
#: stop trusting the single shot well before anything anybody has evidence about. Twenty
#: mebibytes is a round, deliberately unremarkable boundary picked by this library; it is not a
#: limit anyone observed Lark enforcing, and no claim is made that a larger single shot would
#: fail. A caller who knows better passes ``chunk_above_bytes`` and moves it.
SINGLE_SHOT_MAX_BYTES = 20 * 1024 * 1024

#: What the URL this op returns **is**, in one word, so no caller has to infer it from prose.
#: A permalink is the object's own address; a *signed* link is a short-lived credential. This
#: op returns the first and never the second, and the distinction is the same one the
#: attachment leg draws when it scrubs an attachment cell.
URL_CLASS = "permalink"

#: The file-lifecycle calls on this client, named beside the methods themselves so the
#: discovery registry (``larkdocio.capabilities()``) PROJECTS them instead of keeping a second
#: hand-maintained list — the ``write.client`` / ``sheets.write_client`` precedent.
#:
#: **Only the destroy half.** The create half of this surface's lifecycle is
#: :func:`put_file_in_folder`, which is already a declared *operation*; naming it here too
#: would report one call twice.
#:
#: **Why this constant exists at all (LD-442).** ``delete`` shipped, was exercised by the live
#: round trip, and was declared by nothing — so it had no permission row, and the registry's
#: bidirectional coverage check could not see the gap because both of its directions are seeded
#: from this same declaration. The row is what a caller needs before they try the call; the
#: guard that now reads the CODE rather than the declaration is
#: ``larkdocio.permissions.undeclared_endpoints``.
LIFECYCLE_OPS = ("delete",)

#: Every code that means **"this file object is already gone"** on this surface. One member, and
#: it is the sheets surface's constant :data:`larkdocio.sheets.write_client.
#: FILE_ALREADY_DELETED_CODE` imported rather than a second spelling of the same number — the
#: shape :func:`larkdocio.base.schema_client.base_is_gone` already ships. Kept as strings so the
#: comparison is representation-agnostic (the wire may hand back an int or a str).
#:
#: **What is deliberately NOT in this set.** The metadata route's answer for a trashed token is
#: not a gone-code at all: it answers ``code:0`` with a meta row for a file that has already
#: been deleted (measured 2026-08-15). Gone-ness here is *the delete route's own* answer, and it
#: means the object left the folder listing — not that every route stopped resolving it.
DRIVE_FILE_GONE_CODES = frozenset({str(FILE_ALREADY_DELETED_CODE)})

#: What a delete refusal carrying :data:`DRIVE_FILE_GONE_CODES` actually establishes — **both
#: halves**, because either one alone is a wrong sentence. Measured on a file the probe created
#: and swept: the second delete answered *"file has been delete."*, the folder listing no longer
#: showed the token, and ``metas/batch_query`` **still resolved it**.
ALREADY_DELETED_READING = (
    "Lark's own answer is that this file HAS ALREADY BEEN DELETED, so this call removed "
    "nothing — an earlier delete already did. file_is_gone(exc) is True for exactly this. It "
    "is still trash rather than purge, and the second half is measured too: the metadata route "
    "was observed STILL RESOLVING a trashed file token, so 'already deleted' means the object "
    "left its folder listing, not that nothing answers for it any more"
)

#: What every OTHER delete refusal establishes about the object: nothing. The sentence this
#: replaced claimed *"The file is still there"* — which contradicted Lark's own message on the
#: one code that has a measured reading, and asserted a presence no route this library calls
#: reports either way.
UNMEASURED_DELETE_READING = (
    "Nothing was reported as removed, and no claim is made about the object either way: no "
    "route this library calls establishes an object's presence or its absence, so Lark's code "
    "and message above are passed through undecorated instead of being read as a verdict"
)


def file_is_gone(error) -> bool:
    """True iff ``error`` says the **file object is already gone**.

    The Drive-side mirror of :func:`larkdocio.sheets.write_client.spreadsheet_is_gone` and
    :func:`larkdocio.base.schema_client.base_is_gone` — one check a teardown can use, so nobody
    has to know which number a second delete answers. Use it to forgive exactly that outcome in
    a ``finally`` while every other failure (a permission problem, a transport failure) still
    surfaces:

    .. code-block:: python

        try:
            files.delete(file_token)
        except LarkDocIOError as exc:
            if not file_is_gone(exc):
                raise

    Anything that is not a Lark error carrying one of :data:`DRIVE_FILE_GONE_CODES` is
    ``False`` — including a **code-less** error, where the failure happened below Lark and
    whether the file is gone is unknown and must not be assumed.

    **What True does and does not mean:** the object is out of its folder listing and a delete
    of it removes nothing. It is **not** a purge — the metadata route was measured still
    resolving a trashed file token.
    """
    code = getattr(error, "code", None)
    return code is not None and str(code) in DRIVE_FILE_GONE_CODES


class DriveFileError(LarkAPIError):
    """A failure on the folder-upload leg. Its own family: a drive **file** object is not
    drive **media**, and folding the two would tell a caller the wrong thing about residue."""


class DriveFileUploadError(DriveFileError):
    """An upload refused — locally, before any call, or by Lark."""


class DriveFileChunkedUploadError(DriveFileUploadError):
    """A chunked upload that stopped, **carrying what it left behind**.

    ``upload_id`` is the pending transaction, ``parts_sent`` how many blocks reached Lark and
    ``block_num`` how many the server declared. All three are on the exception because the
    leftover is invisible everywhere else: it is a transaction, **not a Drive object**, so no
    listing shows it and no delete removes it — and **no cancel verb was found in the SDK's
    drive v1 surface and none was called**, which is `unmeasured, not "cannot"`.
    """

    def __init__(self, message, *, upload_id=None, parts_sent=0, block_num=0, **kwargs):
        super().__init__(message, **kwargs)
        self.upload_id = upload_id
        self.parts_sent = parts_sent
        self.block_num = block_num


class DriveFileDownloadError(DriveFileError):
    """A download that returned no usable bytes."""


class DriveFileMetaError(DriveFileError):
    """The metadata query did not yield the file's own URL, so there is nothing to link to."""


class DriveFileDeleteError(DriveFileError):
    """A delete Lark refused — and what that does, and does not, say about the file.

    Nothing is reported as removed. **It does not follow that the file is there**: this class's
    own docstring used to say so, and on the one code that has a measured reading it said the
    opposite of the truth. A refusal carrying :data:`DRIVE_FILE_GONE_CODES` means the object was
    **already deleted** — check it with :func:`file_is_gone` rather than by matching a string —
    and every other code establishes nothing about the object either way, so Lark's own code and
    message are passed through undecorated.
    """


@dataclass(frozen=True)
class UploadedFile:
    """One file uploaded into a folder: its token, where it landed, its size and ``sha256``.

    Carries **no URL of any kind** — the upload's own answer includes a short-lived signed
    link, and a signed link is a credential. The openable address is asked for separately
    (:meth:`DriveFilesWriteClient.permalink`) and is a different class of thing.

    The three field names :func:`larkdocio.base.media.verify_round_trip` reads
    (``file_token`` / ``size`` / ``sha256``) are spelled exactly as that function expects, so
    the round-trip check is this library's **one** definition reused rather than a second one
    written for a second surface.
    """

    file_token: str
    folder_token: str
    name: str
    size: int
    sha256: str

    #: How many blocks the bytes actually went up in — ``1`` for the single shot. **Reported,
    #: never chosen:** on the chunked route it is the count the *server's* declared partition
    #: produced, not a number this library picked.
    parts: int = 1


@dataclass(frozen=True)
class UploadPartition:
    """``upload_prepare``'s answer: **the server's own partition**, obeyed as given.

    ``block_size`` is how big Lark wants each block and ``block_num`` how many it counted for
    the size that was declared. Measured on one tenant on one day, ``block_size`` was the same
    for a 130-byte file and a *declared* 64 MiB while ``block_num`` moved 1 → 16 — which is why
    this is **asked for on every upload** and why no size constant decides a partition here.

    ``upload_id`` is the transaction the parts belong to. It is also the thing left behind if a
    run stops before ``upload_finish``: a pending upload with **no Drive object**, which no
    measured verb cancels.
    """

    upload_id: str
    block_size: int
    block_num: int


def parts_for(size: int, block_size: int) -> int:
    """How many blocks ``size`` bytes fall into under a **server-declared** ``block_size``.

    Arithmetic over the server's answer and nothing else — the one place the count is derived,
    so the number sent to ``upload_finish`` and the number of parts actually sent cannot come
    from two different reckonings.
    """
    if block_size <= 0:
        raise DriveFileChunkedUploadError(
            f"upload_prepare declared a block_size of {block_size!r}, which cannot partition "
            f"anything. Nothing was sent: the partition is the server's and this library will "
            f"not substitute one of its own")
    return max(1, math.ceil(size / block_size))


@dataclass(frozen=True)
class LinkedFile:
    """An uploaded file **plus the URL that opens it** — the whole point of the op.

    ``url`` is a :data:`URL_CLASS` — the file object's own web address, as Lark reported it.
    It is never constructed from a token by this library, and it is not a signed link.

    ``bytes_verified`` says whether the bytes were downloaded again and compared by hash
    against the upload: the difference between *"the calls answered"* and *"the file is
    there"*.
    """

    file_token: str
    folder_token: str
    name: str
    size: int
    sha256: str
    url: str
    bytes_verified: bool

    #: Restated on the value itself so a caller reading a returned object — not the module —
    #: still meets the classification.
    url_class: str = URL_CLASS

    #: How the bytes went up: ``1`` for the single shot, otherwise the number of blocks the
    #: **server's** declared partition produced. A fact about what happened, not a knob.
    parts: int = 1


class DriveFilesWriteClient:
    """Uploads, re-downloads and deletes **file objects** in a Drive folder, on the WRITE pair.

    ``sdk_client`` and ``rate_limiter`` are injectable exactly as on the attachment leg, so
    request construction, pacing and error typing are testable without a network. The pace is
    the same the media leg runs at, which is the only spacing this project has evidence for.

    **WRITE credentials only.** the read credential pair is never consulted here and is
    not named in this module. (On the tenant these measurements were made on the two pairs named one app —
    a configuration fact this code neither knows nor relies on.)
    """

    #: The ``parent_type`` values THIS client will send. Anything else is refused locally,
    #: before any call, because an upload puts a permanent object in somebody's Drive.
    ALLOWED_PARENT_TYPES: Tuple[str, ...] = (EXPLORER_PARENT_TYPE,)

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        domain: str = "larksuite.com",
        *,
        sdk_client=None,
        rate_limiter=None,
        timeout: int = 30,
    ):
        self._domain = domain
        self._api_calls = 0
        self._limiter = resolve_rate_limiter(
            rate_limiter, MEDIA_MAX_CALLS_PER_WINDOW, MEDIA_RATE_WINDOW_SECONDS)
        self._sdk = resolve_sdk_client(
            sdk_client, app_id, app_secret, domain, timeout=timeout,
            no_credentials="Cannot upload a file: no credentials were resolved")

    @classmethod
    def from_write_credentials(cls, domain: str = "larksuite.com", **kwargs):
        """Build from the environment's WRITE pair. No fallback to the read pair."""
        app_id, app_secret = get_write_credentials()
        require_credentials(
            app_id, app_secret,
            "Cannot upload a file: no write credentials in the environment "
            f"({WRITE_ENV[0]} / {WRITE_ENV[1]})")
        return cls(app_id, app_secret, domain, **kwargs)

    @property
    def limiter(self):
        """The limiter every call on this client passes through."""
        return self._limiter

    @property
    def api_calls(self) -> int:
        """How many API calls this client has made — incremented in exactly one place."""
        return self._api_calls

    def _paced(self, call, request):
        self._limiter.acquire()
        self._api_calls += 1
        return call(request)

    # ---- the legs --------------------------------------------------------- #

    def upload(self, *, data: bytes, name: str, folder_token: str,
               parent_type: str = EXPLORER_PARENT_TYPE) -> UploadedFile:
        """Upload ``data`` into ``folder_token`` and return its :class:`UploadedFile`.

        ``folder_token`` is **required** and is refused locally when missing: there is no
        default destination, no root-folder resolution and no folder creation anywhere in
        this module, so an unaddressed upload cannot be guessed at.

        A **zero-byte** upload is refused by Lark with a generic parameter complaint, and the
        advice that explains it is :data:`larkdocio.base.media.EMPTY_UPLOAD_ADVICE` — the same
        sentence the attachment leg raises, imported rather than re-worded. The call is still
        **sent**: the finding is the server's, and pre-empting it here would be asserting a
        rule nobody published.

        The answer's own body carries a short-lived signed link. It is not read, not returned
        and not logged: only the ``file_token`` leaves this method.
        """
        self._refuse_unaddressed(parent_type, folder_token)
        if data is None:
            raise DriveFileUploadError(
                "an upload needs bytes; pass data=b'' for an empty file")

        body = UploadAllFileRequestBody.builder() \
            .file_name(name) \
            .parent_type(parent_type) \
            .parent_node(folder_token) \
            .size(len(data)) \
            .file(io.BytesIO(data)) \
            .build()
        request = UploadAllFileRequest.builder().request_body(body).build()
        response = self._paced(self._sdk.drive.v1.file.upload_all, request)
        code = _code_of(response)
        if code:
            advice = ("Check that the folder token names a folder this app may write to, "
                      "then retry")
            if not data and code == EMPTY_UPLOAD_REFUSED_CODE:
                advice = EMPTY_UPLOAD_ADVICE
            raise api_error_as(
                DriveFileUploadError,
                f"the upload of {name!r} into {folder_token!r} was refused: Code: {code}, "
                f"Msg: {_msg_of(response)}. Nothing was uploaded and no token exists. "
                f"{advice}",
                code=code, msg=_msg_of(response), body=response,
                credential_env=WRITE_ENV)
        token = getattr(getattr(response, "data", None), "file_token", None)
        if not token:
            raise DriveFileUploadError(
                f"the upload of {name!r} returned no file_token, so there is nothing to "
                f"link to and nothing to verify")
        return UploadedFile(file_token=token, folder_token=folder_token, name=name,
                            size=len(data), sha256=sha256_of(data))

    # ---- the chunked family (LD-449) -------------------------------------- #

    def upload_prepare(self, *, name: str, size: int, folder_token: str,
                       parent_type: str = EXPLORER_PARENT_TYPE) -> UploadPartition:
        """**Ask** Lark how to partition ``size`` bytes, and return its answer verbatim.

        ``POST drive/v1/files/upload_prepare``. The answer — ``block_size``, ``block_num`` and
        the ``upload_id`` — is the whole basis on which the bytes are cut up here. Nothing in
        this module second-guesses it, and no size constant of this library's own decides a
        partition.

        **A prepare that is not followed by an ``upload_finish`` leaves a pending upload
        transaction with no Drive object**, which no measured verb cancels (see the module
        docstring: `unmeasured, not "cannot"`). So this leg is not a probe to reach for.
        """
        self._refuse_unaddressed(parent_type, folder_token)
        body = FileUploadInfo.builder() \
            .file_name(name) \
            .parent_type(parent_type) \
            .parent_node(folder_token) \
            .size(size) \
            .build()
        request = UploadPrepareFileRequest.builder().request_body(body).build()
        response = self._paced(self._sdk.drive.v1.file.upload_prepare, request)
        code = _code_of(response)
        if code:
            raise api_error_as(
                DriveFileChunkedUploadError,
                f"upload_prepare for {name!r} into {folder_token!r} was refused: Code: {code}, "
                f"Msg: {_msg_of(response)}. Nothing was sent and no upload transaction exists",
                code=code, msg=_msg_of(response), body=response,
                credential_env=WRITE_ENV)
        data = getattr(response, "data", None)
        upload_id = getattr(data, "upload_id", None)
        block_size = getattr(data, "block_size", None)
        block_num = getattr(data, "block_num", None)
        if not upload_id or not block_size or not block_num:
            raise DriveFileChunkedUploadError(
                f"upload_prepare for {name!r} answered success without a complete partition "
                f"(upload_id={upload_id!r}, block_size={block_size!r}, "
                f"block_num={block_num!r}). Nothing was sent: the partition is the server's, "
                f"and this library will not invent the missing half",
                upload_id=upload_id)
        return UploadPartition(upload_id=upload_id, block_size=int(block_size),
                               block_num=int(block_num))

    def upload_part(self, *, upload_id: str, seq: int, data: bytes) -> None:
        """Send one block of an upload transaction.

        ``POST drive/v1/files/upload_part``, ``multipart/form-data``. The optional Adler-32
        ``checksum`` is **deliberately not sent**: it was omitted in the measurement and the
        part was accepted, so sending it **buys no guarantee this library can point to**.
        That is **three parts across two uploads** (``seq: 0`` of a 130-byte ``.html``, and
        both blocks of a two-block ``.bin``) — the edge is stated at its real width rather than
        generalised.

        **AND "OMITTED" HAS TO MEAN THE KEY IS GONE, WHICH IS A MEASURED TRAP.** The pinned
        SDK builds this call's form from the body's own attributes and **keeps a key whose
        value is ``None``**, so an unset ``checksum`` goes out as an **empty form field** — and
        Lark refuses that with ``1061002 params error``. The same body with the key *deleted*
        is accepted. Measured live on this route, both ways round; the identical shape is
        accepted on ``upload_all``, so this is the part leg's own strictness rather than a
        general rule. Hence the ``pop`` below: it is not tidiness, it is the difference between
        a part that uploads and one that cannot.
        """
        body = UploadPartFileRequestBody.builder() \
            .upload_id(upload_id) \
            .seq(seq) \
            .size(len(data)) \
            .file(io.BytesIO(data)) \
            .build()
        # Omitting a field means REMOVING it, not leaving it None — see the docstring above.
        # Defensive by construction: a future SDK body that never had the key is unaffected.
        vars(body).pop("checksum", None)
        request = UploadPartFileRequest.builder().request_body(body).build()
        response = self._paced(self._sdk.drive.v1.file.upload_part, request)
        code = _code_of(response)
        if code:
            raise api_error_as(
                DriveFileChunkedUploadError,
                f"block {seq} of upload {upload_id!r} was refused: Code: {code}, "
                f"Msg: {_msg_of(response)}",
                code=code, msg=_msg_of(response), body=response,
                credential_env=WRITE_ENV, upload_id=upload_id)

    def upload_finish(self, *, upload_id: str, block_num: int) -> str:
        """Close an upload transaction and return the ``file_token`` it answers.

        ``POST drive/v1/files/upload_finish``. **Its ``code:0`` is an ACCEPTANCE, not a
        verdict** — the file exists once it has been downloaded again and hashed, which is what
        :func:`put_file_in_folder` does with the token this returns.
        """
        body = UploadFinishFileRequestBody.builder() \
            .upload_id(upload_id) \
            .block_num(block_num) \
            .build()
        request = UploadFinishFileRequest.builder().request_body(body).build()
        response = self._paced(self._sdk.drive.v1.file.upload_finish, request)
        code = _code_of(response)
        if code:
            raise api_error_as(
                DriveFileChunkedUploadError,
                f"upload_finish for {upload_id!r} was refused: Code: {code}, "
                f"Msg: {_msg_of(response)}",
                code=code, msg=_msg_of(response), body=response,
                credential_env=WRITE_ENV, upload_id=upload_id,
                parts_sent=block_num, block_num=block_num)
        token = getattr(getattr(response, "data", None), "file_token", None)
        if not token:
            raise DriveFileChunkedUploadError(
                f"upload_finish for {upload_id!r} answered success with no file_token, so "
                f"there is nothing to download and nothing to verify — and the verdict on this "
                f"route is the hash-verified read-back, never the call's own answer",
                upload_id=upload_id, parts_sent=block_num, block_num=block_num)
        return token

    def upload_chunked(self, *, data: bytes, name: str, folder_token: str,
                       parent_type: str = EXPLORER_PARENT_TYPE) -> UploadedFile:
        """Upload ``data`` in the **blocks the server declares**, and return its
        :class:`UploadedFile`.

        prepare → part × ``block_num`` → finish. The partition comes from
        :meth:`upload_prepare` and from nowhere else; if the two halves of that answer
        disagree — a ``block_num`` that is not what ``block_size`` implies for the size that was
        declared — **nothing is sent**, because obeying one half would mean guessing which one.

        A refusal part-way leaves a pending transaction with no Drive object, and the raised
        :class:`DriveFileChunkedUploadError` says so and names it.
        """
        self._refuse_unaddressed(parent_type, folder_token)
        if data is None:
            raise DriveFileUploadError(
                "an upload needs bytes; pass data=b'' for an empty file")
        partition = self.upload_prepare(
            name=name, size=len(data), folder_token=folder_token, parent_type=parent_type)
        counted = parts_for(len(data), partition.block_size)
        if counted != partition.block_num:
            raise DriveFileChunkedUploadError(
                f"upload_prepare answered a partition whose halves disagree: block_num "
                f"{partition.block_num} for {len(data)} bytes at block_size "
                f"{partition.block_size}, which is {counted} blocks. Nothing was sent — "
                f"obeying one half would be guessing which one is right. The transaction "
                f"{partition.upload_id!r} is left prepared and unsent: a pending upload with "
                f"no Drive object, and no cancel verb was found in the SDK's drive v1 surface "
                f"and none was called (unmeasured, not \"cannot\"); its expiry is unmeasured",
                upload_id=partition.upload_id, parts_sent=0, block_num=partition.block_num)
        sent = 0
        for seq in range(counted):
            block = data[seq * partition.block_size:(seq + 1) * partition.block_size]
            try:
                self.upload_part(upload_id=partition.upload_id, seq=seq, data=block)
            except DriveFileChunkedUploadError as exc:
                # A RE-WRAP: `exc` was classified once already, at the block call. The
                # record is carried rather than rebuilt — re-deriving it from code/msg alone
                # would silently drop the console link the original response body supplied.
                raise api_error_as(
                    DriveFileChunkedUploadError,
                    f"{exc} — {sent} of {counted} blocks had been sent. Left behind: the "
                    f"upload transaction {partition.upload_id!r}, which is a pending upload "
                    f"with no Drive object (nothing was created, so there is nothing to "
                    f"delete), and no cancel verb was found in the SDK's drive v1 surface "
                    f"and none was called — unmeasured, not \"cannot\" — and the "
                    f"transaction's expiry is unmeasured. Retrying means starting a new "
                    f"upload",
                    code=exc.code, msg=exc.msg, denial=exc.denial,
                    credential_env=WRITE_ENV, upload_id=partition.upload_id,
                    parts_sent=sent, block_num=counted) from exc
            sent += 1
        token = self.upload_finish(upload_id=partition.upload_id, block_num=counted)
        return UploadedFile(file_token=token, folder_token=folder_token, name=name,
                            size=len(data), sha256=sha256_of(data), parts=counted)

    def _refuse_unaddressed(self, parent_type: str, folder_token: str) -> None:
        """The destination fence, applied identically on both upload routes."""
        if parent_type not in self.ALLOWED_PARENT_TYPES:
            allowed = ", ".join(repr(p) for p in self.ALLOWED_PARENT_TYPES)
            raise DriveFileUploadError(
                f"{parent_type!r} is not a parent type this leg sends. Accepted here: "
                f"{allowed} — that is the one spelling measured for a folder destination, "
                f"and every other spelling is unmeasured rather than refused, so nothing is "
                f"sent for one")
        if not folder_token:
            raise DriveFileUploadError(
                "an upload needs a folder token — the token of the folder the file is being "
                "put in. Nothing was sent: this library picks no default destination and "
                "creates no folder, so an unaddressed upload is refused rather than guessed "
                "at")

    def permalink(self, file_token: str) -> str:
        """The file's own web URL — **asked for**, never built from the token.

        ``POST drive/v1/metas/batch_query`` with ``with_url: true``. What comes back is a
        :data:`URL_CLASS`: the object's address, not a short-lived signed link. This library
        never assembles a URL out of a host and a token, because a URL it invented would be a
        guess wearing the shape of an answer — so an absent ``url`` raises rather than falls
        back to one.
        """
        if not file_token:
            raise DriveFileMetaError(
                "a metadata query needs a file token; the upload's file_token is the handle")
        doc = RequestDoc.builder().doc_token(file_token).doc_type(FILE_DOC_TYPE).build()
        body = MetaRequest.builder().request_docs([doc]).with_url(True).build()
        request = BatchQueryMetaRequest.builder().request_body(body).build()
        response = self._paced(self._sdk.drive.v1.meta.batch_query, request)
        code = _code_of(response)
        if code:
            raise api_error_as(
                DriveFileMetaError,
                f"the metadata query for {file_token!r} was refused: Code: {code}, "
                f"Msg: {_msg_of(response)}. The file may exist; its URL is simply not known, "
                f"and this library will not construct one",
                code=code, msg=_msg_of(response), body=response,
                credential_env=WRITE_ENV)
        data = getattr(response, "data", None)
        for meta in (getattr(data, "metas", None) or ()):
            url = getattr(meta, "url", None) or (
                meta.get("url") if isinstance(meta, dict) else None)
            if url:
                return url
        raise DriveFileMetaError(
            f"the metadata query for {file_token!r} answered success but reported no URL, "
            f"so there is no address to link to. A URL is never constructed from the token "
            f"here: an invented address that happened to 404 would be worse than none. "
            # An empty `metas` is a REFUSAL wearing a code:0, so the refusal this leg raises
            # carries Lark's own reason for the token rather than only the missing field
            # (LD-606). The RAISE is unchanged: it was a raise before and it is a raise now.
            f"{failed_reason(data, file_token)}")

    def download(self, file_token: str) -> bytes:
        """Download ``file_token``'s bytes, **in memory, unexamined**.

        Returned for **hashing** — see :func:`larkdocio.base.media.verify_round_trip`;
        nothing in this library decodes or renders them. A download creates nothing.
        """
        if not file_token:
            raise DriveFileDownloadError("a download needs a file token")
        request = DownloadFileRequest.builder().file_token(file_token).build()
        response = self._paced(self._sdk.drive.v1.file.download, request)
        code = _code_of(response)
        if code:
            raise api_error_as(
                DriveFileDownloadError,
                f"the download of {file_token!r} was refused: Code: {code}, "
                f"Msg: {_msg_of(response)}. No bytes were returned",
                code=code, msg=_msg_of(response), body=response,
                credential_env=WRITE_ENV)
        payload = getattr(response, "file", None)
        if payload is None:
            raise DriveFileDownloadError(
                f"the download of {file_token!r} answered success with no file content, so "
                f"there is nothing to verify")
        return payload.read()

    def delete(self, file_token: str) -> None:
        """Delete an uploaded file object.

        **Trash, not purge**, and no API undo was measured — so this is reversible only in the
        sense that a human can go and look in the trash. Its counterpart is what makes the
        disclosure worth reading: media bytes uploaded *into a document* cannot be deleted at
        all, by this or any open-API verb.

        Returns nothing on success **on purpose**: a delete's own ``code:0`` is not evidence
        the object is gone — and here the honest answer goes one step further. **Measured:
        after a successful delete the metadata route STILL RESOLVES the token.** That is what
        *trash, not purge* looks like from the API side, so this method claims a delete and
        never claims a purge, and no route this library calls establishes the object's
        absence. Whether any route can is **unmeasured, not refuted**.

        **Deleting the SAME token twice is answered truthfully.** The second call is refused
        with Lark's *"file has been delete."* code, and the refusal says the file was already
        deleted — :func:`file_is_gone` is the predicate to test it with. It used to say *"The
        file is still there"*, which contradicted Lark's own message.
        """
        if not file_token:
            raise DriveFileDeleteError("a delete needs a file token")
        request = DeleteFileRequest.builder() \
            .file_token(file_token).type(FILE_DOC_TYPE).build()
        response = self._paced(self._sdk.drive.v1.file.delete, request)
        code = _code_of(response)
        if code:
            reading = (ALREADY_DELETED_READING if str(code) in DRIVE_FILE_GONE_CODES
                       else UNMEASURED_DELETE_READING)
            raise api_error_as(
                DriveFileDeleteError,
                f"the delete of {file_token!r} was refused: Code: {code}, "
                f"Msg: {_msg_of(response)}. {reading}",
                code=code, msg=_msg_of(response), body=response,
                credential_env=WRITE_ENV)


def put_file_in_folder(
    *,
    files: DriveFilesWriteClient,
    data: bytes,
    name: str,
    folder_token: str,
    verify_bytes: bool = True,
    chunk_above_bytes: Optional[int] = None,
) -> LinkedFile:
    """Put a file in ``folder_token`` and return it **with the URL that opens it**.

    The two calls that make the ask executable happen here as a unit — the upload, then the
    metadata query for the file's own URL — because a token with no URL does not serve
    *"open the attached file"* and a URL this library assembled would be a guess.

    **A large file goes up in chunks, and that is the only difference a caller can see.** Above
    ``chunk_above_bytes`` — defaulting to :data:`SINGLE_SHOT_MAX_BYTES`, which is **this
    library's policy and not a server fact** — the bytes take ``upload_prepare`` /
    ``upload_part`` / ``upload_finish``, partitioned by **the server's own declared
    ``block_size`` / ``block_num``**, and the returned :class:`LinkedFile` reports how many
    ``parts`` it took. Everything else is identical, including the verdict.

    With ``verify_bytes`` (the default) the file is downloaded again and compared against the
    upload **by sha256 and length** (:func:`larkdocio.base.media.verify_round_trip`, reused).
    The bytes are never inspected.

    **The destination is the caller's**: ``folder_token`` is required, no folder is created,
    and no default is chosen. **The URL is a permalink**, not a signed link, and it grants
    nobody access — whoever opens it still needs access to the file, which this library does
    not arrange.

    A failure *after* the upload leaves a real file behind: nothing here issues an unrequested
    delete, so the exception carries ``orphan_file_token`` and the caller decides. A failure
    *during* a chunked upload leaves something different and less visible — a pending upload
    transaction with **no Drive object** — and :class:`DriveFileChunkedUploadError` names it.

    <<DUPLICATE_UPLOAD_BEHAVIOUR>>
    """
    threshold = SINGLE_SHOT_MAX_BYTES if chunk_above_bytes is None else chunk_above_bytes
    if data is not None and len(data) > threshold:
        uploaded = files.upload_chunked(data=data, name=name, folder_token=folder_token)
    else:
        uploaded = files.upload(data=data, name=name, folder_token=folder_token)
    try:
        url = files.permalink(uploaded.file_token)
        verified = False
        if verify_bytes:
            verify_round_trip(uploaded, files.download(uploaded.file_token))
            verified = True
    except Exception as exc:  # the file exists; say so and let the refusal through intact
        exc.orphan_file_token = uploaded.file_token
        raise
    return LinkedFile(
        file_token=uploaded.file_token,
        folder_token=uploaded.folder_token,
        name=uploaded.name,
        size=uploaded.size,
        sha256=uploaded.sha256,
        url=url,
        bytes_verified=verified,
        parts=uploaded.parts,
    )


# QUOTED, never re-typed — the same discipline the shareability disclosure above rides on: the
# duplicate-upload sentence is authored once in ``larkdocio.drive.lookup`` and the op a consumer
# actually calls carries it verbatim, so the docstring, the guide and the capability note cannot
# drift into three different accounts of one measurement.
put_file_in_folder.__doc__ = (put_file_in_folder.__doc__ or "").replace(
    "<<DUPLICATE_UPLOAD_BEHAVIOUR>>", DUPLICATE_UPLOAD_BEHAVIOUR)


def _code_of(response) -> Optional[int]:
    code = getattr(response, "code", None)
    if code in (0, None):
        return None
    try:
        return int(str(code))
    except (TypeError, ValueError):  # pragma: no cover - a non-numeric code
        return code


def _msg_of(response) -> str:
    return getattr(response, "msg", "") or ""
