"""larkdocio.base.media — the attachment OUT-OF-BAND leg: upload, download, hash-verify.

An Attachment cell is written from a ``file_token``, and until now the token was the caller's
problem: the encoder took one and this library had no way to *make* one. This module is that
missing half — upload bytes to the drive media family, get a token back, hand it to the
encoder unchanged, and (the part that makes the claim worth anything) **download the token
again and compare hashes**.

**THE SUBSTRATE CALL, recorded here because the next reader will look here for it.** There is
already exactly one definition of *"download a Lark media token"* in this repository: the
reader's docx image leg, :meth:`larkdocio.read.client.LarkDocsClient.download_image`, which
builds the pinned SDK's ``DownloadMediaRequest`` and rides ``drive.v1.media``. This module
rides **the same SDK seam and the same request classes** rather than opening a raw-HTTP media
leg on :mod:`larkdocio.common.transport` — a **third** independent definition of that call is
the outcome worth avoiding, and the transport core exists for the JSON clients whose bodies it
builds, not for multipart. The two legs differ only in the two ways they must: this one runs
on the **WRITE** pair (it uploads) and keeps the bytes **in memory** to be hashed, where the
reader's runs on the READ pair and streams to disk. Neither difference is a reason to
re-implement the call, and a test pins that both name the same request class.

**MEDIA ACCRETES AND NOTHING CAN SWEEP IT — read this before adding a live arm.** A
``bitable_file`` / ``bitable_image`` ``file_token`` **survives its table's deletion** and
**no route in Lark's open API purges drive media** — that survival is the limitation register's
**row 10** in ``BASE.md`` (in the source repository, not in the wheel), cited here rather than
re-stated; the P0 pack's four tokens left under a now-deleted table are what established it.
The **route** half of that sentence is measured separately and enumerated in
:data:`NO_ROUTE_PURGES_DRIVE_MEDIA` below — with the scope stated there, which a Base caller
should read: the four probed tokens were minted on the **sheets** and **docx** media paths, so
for a **Base-parented** token those nine spellings are **unmeasured, not refuted**. So every
*upload* —
never a download, which mints nothing — adds permanent tenant residue. This library's answer is
disclosure, not a simulated purge: the leg says so here, the live gate says so in its own
docstring, and the test harness **ledgers every
token it mints** with its ``parent_type`` and the disposable it was attached to. An
``orphans == 0`` claim is made against the *bitable* liveness definition and **media residue is
explicitly outside it**.

**``parent_node`` IS AN APP_TOKEN.** It is the single most dangerous parameter this module
takes: point it at the wrong Base and you have attached permanent, unsweepable residue to
something you did not mean to touch — and deleting that Base afterwards does not undo it. See
the warning on :meth:`BaseMediaClient.upload`.

**``url`` and ``tmp_url`` are CREDENTIAL-CLASS.** An Attachment cell reads back
``{file_token, name, size, type, url, tmp_url}``; the last two are short-lived **signed**
links. Nothing here logs one, interpolates one into an error, commits one to a fixture or
renders one into Markdown — L1 renders file **names** and this rung does not widen that.
:func:`scrub_attachment_cell` is the projection every other path here goes through.

**Bytes are hashed, never inspected.** No function in this module decodes, parses, renders or
logs a media payload. :func:`verify_round_trip` compares ``sha256`` digests and reports
digests and lengths — the standing rule for binary artifacts in this repository.

**Gentle.** Both legs pass one shared
:class:`~larkdocio.common.transport.RateLimiter` at the same spacing the record-write client
uses, and nothing here retries on a rate limit.
"""
import hashlib
import io
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from lark_oapi.api.drive.v1 import (
    BatchQueryMetaRequest,
    DownloadMediaRequest,
    MetaRequest,
    RequestDoc,
    UploadAllMediaRequest,
    UploadAllMediaRequestBody,
)

from larkdocio.common.auth import WRITE_ENV, get_write_credentials
from larkdocio.common.metas import failed_reason
from larkdocio.common.sdk_client import (
    require_credentials,
    resolve_rate_limiter,
    resolve_sdk_client,
)
from larkdocio.errors import LarkAPIError, api_error_as

#: The two ``parent_type`` values a Base attachment upload accepts, **both proven ``code:0``**
#: (``tests/captures/base-study/captures/p0-4-01-attachment-population.json``, in the source repository). Neither
#: is a guess and
#: neither is preferred: a file column and an image column are the same call.
MEDIA_PARENT_TYPES: Tuple[str, ...] = ("bitable_file", "bitable_image")

#: The upload endpoint, stated for the permission registry's benefit and cross-checked against
#: the SDK request class's own ``uri`` by a test.
UPLOAD_ENDPOINT = "/open-apis/drive/v1/medias/upload_all"

#: The download endpoint, same discipline.
DOWNLOAD_ENDPOINT = "/open-apis/drive/v1/medias/:file_token/download"

#: The ONE ``doc_type`` spelling measured to resolve a media token on
#: ``metas/batch_query``. ``bitable`` and ``docx`` were both tried on the same token and both
#: were **swallowed** — see :data:`WRONG_DOC_TYPE_IS_AN_EMPTY_ANSWER`.
MEDIA_META_DOC_TYPE = "file"

#: **THE SWALLOW.** Authored once here because the whole risk of the permalink leg is that a
#: cheap version of it reports ``code:0`` as a success. Quoted into the op's own docstring.
WRONG_DOC_TYPE_IS_AN_EMPTY_ANSWER = (
    "THE WRONG doc_type IS NOT AN ERROR, IT IS AN EMPTY ANSWER. metas/batch_query answers "
    "code:0 Success with an EMPTY metas list — and the reason in failed_list — both for a "
    "doc_type that does not match the token and for a token that was never minted. So a "
    "code:0 from this endpoint is not a permalink, and this leg reads the answer's own "
    "failed_list and refuses with Lark's reason rather than reporting a success it did not "
    "get. The one spelling measured to resolve a media token is doc_type: file "
    "(MEDIA_META_DOC_TYPE); the bitable and docx spellings were both tried on the same token "
    "and both came back empty. Evidence: tests/captures/base-media-parity-spike/captures/113-, 116- and "
    "117- (in the source repository)."
)

#: **THE CAVEAT THAT MAKES THE PERMALINK HONEST.** One authoring, quoted into the op's
#: docstring and into the shipped guide, because an op that returns a URL without this
#: sentence is selling a promise the measurement does not support.
PERMALINK_OUTLIVES_THE_BYTES = (
    "THE PERMALINK OUTLIVES THE BYTES' REACHABILITY — MEASURED. After the parent Base was "
    "deleted, metas/batch_query still returned both permalinks (immediately, and again seven "
    "minutes later, with no failed_list at all) while the bytes did not come back: the "
    "shipped download leg raised on an answer carrying no file content, and the raw "
    "medias/{token}/download route answered HTTP 404 with an empty body, twice, seven "
    "minutes apart. So a link handed to another user today can outlive the content it points "
    "at, and this library cannot tell from the permalink whether the bytes are still there — "
    "the metadata answer is about the object's ADDRESS, not about its CONTENT. A permalink "
    "that resolves is not evidence the bytes are there. The only thing that establishes the "
    "bytes is fetching them: download the token and compare digests (verify_round_trip), and "
    "even that is true only for the moment it was taken. THE EDGE OF THE EVIDENCE: one "
    "tenant, one day, one tenant_access_token, one disposable Base this harness created and "
    "then deleted, two files of 88 and 375 bytes. user_access_token is UNMEASURED; other "
    "tenants, regions and domains are UNMEASURED; whether a restore of the trashed parent "
    "makes the bytes fetchable again is UNMEASURED; and what a human clicking the permalink "
    "actually sees is UNMEASURED — a click is not a probe, and no sentence this library "
    "ships claims to know it. Evidence: tests/captures/base-media-parity-spike/captures/ 132- (in the "
    "source repository); the other recordings of this measurement are not published."
)

#: **WHAT A PERMALINK IS NOT** — the head of the disclosure. The sharing refusal itself is
#: **not** written here: :data:`PERMALINK_IS_NOT_ACCESS`, below the one authoring of it,
#: quotes that constant verbatim onto the end of this text.
_PERMALINK_IS_NOT_ACCESS_HEAD = (
    "A permalink grants nobody access. What comes back is the object's own ADDRESS — a "
    "permalink, not a signed link and not a credential: no signature, no expiry, no query "
    "parameters, and handing it to somebody who could not already open the file gives them "
    "nothing. MEASURED: an unauthenticated GET of such a URL answers HTTP 302 to the login "
    "page, which establishes that the route is live and login-gated and which is not a proof "
    "of human openability — what a human with an account sees is UNMEASURED. The calls that "
    "WOULD grant something are refused on this token class, and that disclosure is quoted "
    "below rather than restated here. This library never widens, requests or escalates a "
    "scope: a grant is a Lark console action, taken by a person, and no call this library "
    "makes asks for one. "
)

#: The two keys an Attachment read-back carries that are **short-lived signed links**. Treated
#: as credential-class everywhere in this library: never logged, never committed, never
#: rendered (the ``shared_url`` precedent).
EPHEMERAL_ATTACHMENT_KEYS: Tuple[str, ...] = ("url", "tmp_url")

#: **THE SHAREABILITY DISCLOSURE — authored ONCE here and quoted wherever a media token is
#: minted or offered as an alternative** (the attachment leg in
#: :mod:`larkdocio.write.media`, the folder leg in :mod:`larkdocio.drive.files_write`, the
#: guide's recipes and the machine-readable surface note). One authoring, because two
#: paraphrases of a disclosure are two things that can drift into disagreeing about what was
#: measured. The refusals are recorded at ``dev/media-spike/captures/518-`` and ``519-`` and
#: the successful pair at ``516-``/``517-`` (in the dev repo).
#:
#: **The scope widened from DOCX-BOUND to PARENT-BOUND** (LD-442, on the base-media parity
#: spike): the same two refusals were measured on **Base-bound** tokens too — both spellings,
#: same ``1066001`` — so a text that said only *docx* told a Base caller nothing while
#: describing their case exactly. Three corroborations came with it, and they are the reason
#: the inference now has a positive side rather than only two refusals: the permission family
#: **reads** a media token happily and refuses only to **mutate** it; the bytes **stop being
#: fetchable when the parent dies** while token, metadata and permalink keep resolving; and
#: the obvious work-around — attaching the token that *is* shareable — is refused by name.
#: Evidence: ``tests/captures/base-media-parity-spike/captures/`` ``132-`` (in the source
#: repository); the other recordings of this measurement are not published.
MEDIA_TOKEN_NOT_INDEPENDENTLY_SHAREABLE = (
    "A PARENT-BOUND MEDIA TOKEN CANNOT BE PERMISSION-GRANTED — MEASURED FOR BOTH THE "
    "DOCX-BOUND AND THE BASE-BOUND KINDS. Both halves of the sharing recipe that works on a "
    "document — the public-settings PATCH and the member POST on the drive permission "
    "family — are refused on a media token bound to a document, each answering the same "
    "internal error (1066001), and the same two calls answer the same code on a media token "
    "bound to a Base (both the image and the file spellings), while the SAME TWO CALLS on a "
    "DRIVE-UPLOADED FILE token succeed. THE READING, LABELLED AS AN INFERENCE RATHER THAN A "
    "MEASUREMENT: the parent-bound token's access appears to RIDE ITS PARENT OBJECT — "
    "whoever can open the document or the Base can fetch the media it carries, and nobody "
    "else can be added to the media itself. THREE OBSERVATIONS CORROBORATE IT FROM THE "
    "POSITIVE SIDE, and none of them promotes it to a measurement: the permission family "
    "READS such a token happily (the public-settings GET answers success with a full "
    "settings body, while a token that was never minted answers 1063001) and so refuses only "
    "to MUTATE it, which rules out 'the family does not know this token'; trashing the parent "
    "makes the bytes UNFETCHABLE (HTTP 404, empty body, still 404 seven minutes later) while "
    "the token, its metadata and its permalink KEEP RESOLVING; and a RESTORE of the parent is "
    "UNMEASURED. Corroborated is not promoted: this stays an inference from two refusals, not "
    "a measurement of the rule — no endpoint states it, the refusals are the permission "
    "family's own internal error rather than a scope denial or a published policy, and the "
    "post-delete 404 body is empty and names no cause. THE STEER THAT FOLLOWS "
    "IS A ROUTE CHOICE: a file that must be INDEPENDENTLY SHAREABLE — granted to another user, "
    "or link-shared on its own — belongs in a folder "
    "(larkdocio.drive.files_write.put_file_in_folder) and is linked from a sentence, rather "
    "than attached to a document body or a Base row; and this library ships no sharing verb "
    "for a file object either way, so that grant is arranged elsewhere. THE OTHER HALF OF "
    "THAT STEER, SAID HERE BECAUSE IT IS THE OBVIOUS THING TO TRY NEXT: the folder route is "
    "NOT a way to fill an Attachment column. A drive-uploaded file token written into a Base "
    "Attachment cell is REFUSED BY NAME — 1254303, 'The attachment does not belong to this "
    "bitable.' — so a caller whose column needs an attachment cannot take the shareable token "
    "and put it there; the two routes mint tokens their own parent will accept and nobody "
    "else's. UNMEASURED, NOT REFUTED: every other permission-family spelling, "
    "user_access_token, other tenants and regions, every media kind but the ones uploaded, "
    "and whether restoring a trashed parent makes the bytes fetchable again."
)

#: **THE PURGE DISCLOSURE — authored ONCE here and quoted wherever this library tells a
#: caller that an upload is permanent** (the docx image/attachment leg in
#: :mod:`larkdocio.write.media`, the two sheets media routes in :mod:`larkdocio.sheets.media`,
#: and the packaged guide's disposables doctrine). One authoring, for the same reason its
#: shareability sibling above has one: two paraphrases of a disclosure are two things that can
#: drift into disagreeing about what was measured.
#:
#: **What changed, and why the sentence is longer than it was.** This library used to say
#: *"no verb purges drive media"* — a sentence about **larkdocio's** own surface, stated in the
#: **platform's** voice with no attempt list behind it, which is the exact over-claim
#: ``process/doctrine/negative-claims.md`` (in the dev repo) § A.1 forbids. The claim is now
#: **measured**, and the enumeration is what makes it falsifiable: a reader can see the edge of
#: the evidence and knows which spellings were never tried. The consequence for a caller is
#: unchanged — **an upload is permanent before you send it** — but it is now provable rather
#: than asserted. Evidence: ``dev/ld476-media-purge-probe/captures/`` (in the dev repo),
#: envelopes ``300``–``330`` (the sheets path), ``610``–``642`` (the docx path) and ``900``
#: (the positive control).
NO_ROUTE_PURGES_DRIVE_MEDIA = (
    "NO ROUTE PURGES A DRIVE MEDIA TOKEN — MEASURED ON BOTH MEDIA PATHS, and this is a "
    "statement about Lark's open API rather than about what this library chose to ship. "
    "THE ENUMERATION, so you can see the edge of it: NINE distinct destructive request "
    "spellings, in FOURTEEN sends, against FOUR media tokens minted on both of this "
    "library's media paths (two on the sheets float-image path, two on the docx image "
    "path) — DELETE drive/v1/files/:token with type=file, type=media, type=sheet_image and "
    "type=docx_image; DELETE drive/v1/medias/:token; POST drive/v1/medias/:token/delete; "
    "POST drive/v1/medias/batch_delete; DELETE drive/explorer/v2/file/:token; and the "
    "UNBIND, docx children/batch_delete over the only block referencing a bound token. "
    "NOT ONE REMOVED A MEDIA TOKEN, and the liveness oracle answered 'still resolves' "
    "after every send. THE LOAD-BEARING ARMS, WHICH ARE NOT AVERAGED: the one DOCUMENTED "
    "delete route (DELETE drive/v1/files/:token?type=file) refuses a media token with HTTP "
    "404 identically on both paths, while a positive control in the same run under the same "
    "credential removes a real Drive file (the delete answers code 0 and an independent "
    "re-query answers 'is deleted'); that route's own error body prints a CLOSED type enum "
    "-- file, docx, bitable, folder, doc, sheet, mindnote, shortcut, slides -- containing "
    "neither media, nor sheet_image, nor docx_image, all three of which were sent and all "
    "three refused with the server echoing the value it received; UNBINDING IS NOT A PURGE "
    "(deleting the only block referencing a successfully bound token answered code 0, the "
    "parent's children read back empty, and the token still resolved); and TRASHING THE "
    "PARENT IS NOT A PURGE (the media object still resolves in a metadata query afterwards, "
    "as does the trashed parent itself -- what a trashed parent can change is BYTE "
    "REACHABILITY, not existence, and that is a separate disclosure quoted beside this one). "
    "THE SCOPE, WHICH THE CLAIM MAY NOT EXCEED: one "
    "tenant, on one day, on larksuite.com, with a tenant_access_token. A "
    "user_access_token is UNMEASURED -- and a human trash UI exists for a user identity, so "
    "a user-scoped route is the most plausible unprobed thing; every spelling outside the "
    "nine above is UNMEASURED, NOT REFUTED, and an API gains endpoints. NOTHING IS SHIPPED "
    "AGAINST THIS: there is no purge verb here to invent, because the measurement is that "
    "the route does not exist. Record the tokens you mint -- recording them is the only "
    "thing anyone can do with them."
)

#: **WHAT A PERMALINK IS NOT**, whole: the address-not-credential head, then the sharing
#: refusal **QUOTED** from its single authoring above. Two paraphrases of one disclosure are
#: two things that can drift into disagreeing about what was measured, so the permalink leg
#: cites rather than re-authors — the same discipline the two media routes already live under.
PERMALINK_IS_NOT_ACCESS = (
    _PERMALINK_IS_NOT_ACCESS_HEAD + MEDIA_TOKEN_NOT_INDEPENDENTLY_SHAREABLE)

#: The drive family's captured not-found code (``1061003``, recorded in
#: ``dev/base-study/p0-addendum-2026-08-03.md`` § 4's error vocabulary (in the dev repo) as
#: *drive-file-not-found*
#: and in the disposable harness as one of the teardown-lag codes). **A media-specific
#: token-not-found answer has never been captured**, so this set is the drive family's own
#: not-found code and nothing more; every other non-zero answer raises the generic
#: :class:`MediaDownloadError` with Lark's code attached rather than being sorted into a
#: taxonomy nobody has observed.
FILE_TOKEN_NOT_FOUND_CODES: Tuple[int, ...] = (1061003,)

#: **A ZERO-BYTE upload is refused by Lark**, with the generic ``1061002 params error`` and
#: nothing in the body naming the size. Observed live on the attachment gate's first run
#: (2026-08-04) with ``size: 0``; the same call with one byte succeeds. It is recorded here so
#: the refusal arrives with its cause instead of as an opaque parameter complaint — the library
#: still **sends** the call rather than refusing locally, because the finding is the server's
#: and pre-empting it would be asserting a rule nobody published.
EMPTY_UPLOAD_REFUSED_CODE = 1061002

#: The sentence that explains :data:`EMPTY_UPLOAD_REFUSED_CODE` to a caller who just met it.
#: Hoisted out of :meth:`BaseMediaClient.upload` so the **folder** upload leg
#: (:mod:`larkdocio.drive.files_write`) raises this refusal by *reusing* it: one definition of
#: what an empty upload means, not two that can drift into disagreeing about the same code.
EMPTY_UPLOAD_ADVICE = (
    "This file is EMPTY, and an empty upload is refused — the code is the endpoint's generic "
    "parameter complaint, and the size is what it is complaining about. Attach a file with at "
    "least one byte"
)

#: The apply-log refusal reason a media-leg failure carries. Its **own** reason, deliberately:
#: a drive media endpoint is not the bitable API, and folding its failures into the bitable
#: taxonomy would tell a consumer that Lark judged their *record* when it judged their *file*.
MEDIA_REFUSAL_REASON = "media-leg-failure"

#: Same pace as the record-write client: 50 calls a minute is a 1.2 s spacing.
MEDIA_MAX_CALLS_PER_WINDOW = 50
MEDIA_RATE_WINDOW_SECONDS = 60.0


# --------------------------------------------------------------------------- #
# The typed failures — each says what the caller can DO.                        #
# --------------------------------------------------------------------------- #

class BaseMediaError(LarkAPIError):
    """A failure on the attachment out-of-band leg.

    Its own family, so an apply log can say *the file leg failed* rather than implying Lark
    judged the record. Carries Lark's ``code`` / ``msg`` when there was an answer.
    """


class MediaUploadError(BaseMediaError):
    """An upload that was refused — locally, before any call, or by Lark."""


class MediaDownloadError(BaseMediaError):
    """A download that did not return usable bytes: a non-zero answer, or a response with no
    file content at all."""


class MediaTokenNotFoundError(MediaDownloadError):
    """A ``file_token`` the drive family no longer resolves."""


class MediaPermalinkError(BaseMediaError):
    """The metadata query did not yield a ``/file/`` address for the token.

    Its own family under the media leg, because *"I could not get you a link"* is a different
    fact from *"the bytes did not come back"* — and a caller who wanted a link for another user
    can act on the difference.
    """


class MediaPermalinkNotResolvedError(MediaPermalinkError):
    """``metas/batch_query`` answered **success with no meta** for this token.

    The typed name for :data:`WRONG_DOC_TYPE_IS_AN_EMPTY_ANSWER`: Lark's ``code:0`` here is
    not a permalink, the reason sits in the answer's ``failed_list``, and this refusal carries
    that reason rather than this library's opinion of it.
    """


class MediaRoundTripError(BaseMediaError):
    """The bytes that came back are **not** the bytes that went up.

    Reported as digests and lengths. The payloads themselves are never in the message — a
    corrupted media byte is still a media byte.
    """


# --------------------------------------------------------------------------- #
# What an upload IS — never a URL.                                             #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class UploadedMedia:
    """One uploaded file: the token, where it was attached, its size and its ``sha256``.

    Deliberately carries **no link of any kind**. The upload answer's own body is
    ``{file_token, version}``, and the read-back's two links are credential-class
    (:data:`EPHEMERAL_ATTACHMENT_KEYS`), so there is nothing here for one to hide in.

    ``sha256`` is the hash of the bytes as they were **sent** — the anchor
    :func:`verify_round_trip` compares the download against.
    """

    file_token: str
    parent_type: str
    parent_node: str
    size: int
    sha256: str


@dataclass(frozen=True)
class MediaPermalink:
    """One attachment's ``/file/`` address and the file's own ``title``, **as Lark answered**.

    Deliberately three fields and no fourth: there is no ``exists`` flag and no freshness
    stamp, because the answer that produced this object says nothing about whether the bytes
    are still fetchable (:data:`PERMALINK_OUTLIVES_THE_BYTES`). ``url`` is a **permalink** —
    an address, never a signed link — so unlike :data:`EPHEMERAL_ATTACHMENT_KEYS` it is not
    credential-class and may be logged, stored and handed to a person; what it is not is
    access (:data:`PERMALINK_IS_NOT_ACCESS`).
    """

    file_token: str
    url: str
    title: str


def sha256_of(data: bytes) -> str:
    """The digest of ``data``. The only thing this library ever computes over media bytes."""
    return hashlib.sha256(data).hexdigest()


def verify_round_trip(uploaded: UploadedMedia, downloaded: bytes) -> str:
    """Compare a download against its upload **by hash**, returning the digest they share.

    Raises :class:`MediaRoundTripError` when they differ, reporting the two digests and the
    two lengths — never the payloads. This is the whole of what *"the round trip is verified"*
    means here: a status code proves an answer arrived, a digest proves the file did.
    """
    got = sha256_of(downloaded)
    if got != uploaded.sha256:
        raise MediaRoundTripError(
            f"the file token {uploaded.file_token!r} did not round-trip: uploaded "
            f"{uploaded.size} bytes with sha256 {uploaded.sha256}, downloaded "
            f"{len(downloaded)} bytes with sha256 {got}. The bytes are NOT compared by "
            f"inspection and are not shown. Re-upload the file and re-attach the new token; "
            f"the old token cannot be purged — no route in Lark's open API purges drive "
            f"media, measured, not assumed: the enumeration and its scope are in "
            f"larkdocio.base.media.NO_ROUTE_PURGES_DRIVE_MEDIA"
        )
    return got


def scrub_attachment_cell(cell: Mapping) -> dict:
    """An Attachment read-back with its **signed links removed**.

    The projection every log, error and capture in this library goes through. What survives is
    ``file_token`` / ``name`` / ``size`` / ``type`` — the durable half — and what does not is
    :data:`EPHEMERAL_ATTACHMENT_KEYS`, which are short-lived signed links and therefore
    credentials.
    """
    return {k: v for k, v in dict(cell).items() if k not in EPHEMERAL_ATTACHMENT_KEYS}


def describe_attachment_cell(cell: Mapping) -> str:
    """One safe line about an attachment cell, for a message or a log.

    Built from :func:`scrub_attachment_cell`, so a caller cannot leak a signed link by
    interpolating a cell they read back.
    """
    safe = scrub_attachment_cell(cell)
    return (f"attachment {safe.get('file_token')!r} "
            f"({safe.get('name')!r}, {safe.get('size')} bytes)")


# --------------------------------------------------------------------------- #
# The client.                                                                  #
# --------------------------------------------------------------------------- #

class BaseMediaClient:
    """Uploads and downloads Base attachment media on the WRITE credential pair.

    ``sdk_client`` and ``rate_limiter`` are injectable, exactly as on the record-write client,
    so request construction, pacing and error typing are all testable without a network.

    **WRITE credentials only.** An upload is a write; ``LARK_READ_APP_*`` is never consulted
    here and is not named anywhere in this module. (On the tenant these measurements were made on the two pairs
    named one app — a configuration fact this code neither knows nor relies on.)

    **The two class attributes below are the ONLY surface-specific thing about this leg.** The
    endpoint, the refusals, the pacing and the round-trip check are the drive media family's
    and are the same wherever a token is minted; what differs between an attachment column and
    a document image is the ``parent_type`` vocabulary and what a ``parent_node`` *is*. So a
    second surface subclasses and re-states those two — it does not re-implement the call.
    :class:`larkdocio.write.media.DocxMediaClient` is that subclass.
    """

    #: The ``parent_type`` values THIS client will send. Anything else is refused locally,
    #: before any call, because an upload is permanent residue.
    ALLOWED_PARENT_TYPES: Tuple[str, ...] = MEDIA_PARENT_TYPES

    #: What a ``parent_node`` is on this surface, in the words the refusals use.
    PARENT_NODE_NOUN = "the app_token of the Base the file is attached to"

    #: The half-sentence a bad ``parent_type`` refusal ends with — the surface's own evidence.
    PARENT_TYPE_ADVICE = (
        "use the file-column or image-column spelling — those two are what this endpoint was "
        "proven to accept for a Base, and nothing is sent for any other value"
    )

    #: What to check when Lark refuses an upload on this surface.
    UPLOAD_REFUSAL_ADVICE = (
        "Check that parent_node is the app_token of a Base this app can write, then retry"
    )

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
            no_credentials="Cannot upload or download media: no credentials were resolved")

    @classmethod
    def from_write_credentials(cls, domain: str = "larksuite.com", **kwargs):
        """Build from the environment's WRITE credentials. No fallback to the read pair."""
        app_id, app_secret = get_write_credentials()
        require_credentials(
            app_id, app_secret,
            "Cannot upload media: no write credentials in the environment "
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

    # ---- the two legs ----------------------------------------------------- #

    def upload(self, *, data: bytes, name: str, parent_type: str,
               parent_node: str) -> UploadedMedia:
        """Upload ``data`` as an attachment and return its :class:`UploadedMedia`.

        ``parent_type`` is one of this client's :attr:`ALLOWED_PARENT_TYPES` — on the Base leg
        :data:`MEDIA_PARENT_TYPES`, i.e. ``bitable_file`` for a file column and
        ``bitable_image`` for an image one, both proven ``code:0``. Anything else is refused
        **locally, before any call**. A subclass re-states that vocabulary (and what a
        ``parent_node`` is) without re-implementing this call.

        **WARNING — ``parent_node`` is an app_token**, the token of the Base the file is
        attached to, not a table id, a record id or a field id. Pass the wrong one and the
        upload succeeds against the wrong Base: that residue is permanent, it cannot be undone
        by deleting the Base afterwards, and it cannot be purged — **no route in Lark's open
        API purges drive media**, measured and enumerated in
        :data:`NO_ROUTE_PURGES_DRIVE_MEDIA` (read its scope: the four probed tokens were
        sheets- and docx-parented, so for a Base-parented one those spellings are
        **unmeasured, not refuted**), and the survival itself is the limitation register's row
        10 (``BASE.md``, in the source repository). Point it only at a Base you meant to write.

        The returned token is exactly what
        :func:`larkdocio.base.write_cells.encode_cell` wants for an Attachment field; this
        method does not encode a cell and does not write one.
        """
        if parent_type not in self.ALLOWED_PARENT_TYPES:
            allowed = ", ".join(repr(p) for p in self.ALLOWED_PARENT_TYPES)
            raise MediaUploadError(
                f"{parent_type!r} is not a parent type this leg sends. Accepted here: "
                f"{allowed} — {self.PARENT_TYPE_ADVICE}")
        if not parent_node:
            raise MediaUploadError(
                f"an upload needs a parent_node — {self.PARENT_NODE_NOUN}. Nothing was "
                f"sent: an upload is permanent residue, so an unaddressed one is refused "
                f"rather than guessed at")
        if data is None:
            raise MediaUploadError("an upload needs bytes; pass data=b'' for an empty file")
        body = UploadAllMediaRequestBody.builder() \
            .file_name(name) \
            .parent_type(parent_type) \
            .parent_node(parent_node) \
            .size(len(data)) \
            .file(io.BytesIO(data)) \
            .build()
        request = UploadAllMediaRequest.builder().request_body(body).build()
        response = self._paced(self._sdk.drive.v1.media.upload_all, request)
        code = _code_of(response)
        if code:
            advice = self.UPLOAD_REFUSAL_ADVICE
            if not data and code == EMPTY_UPLOAD_REFUSED_CODE:
                advice = EMPTY_UPLOAD_ADVICE
            raise api_error_as(
                MediaUploadError,
                f"the upload of {name!r} to {parent_node!r} was refused: "
                f"Code: {code}, Msg: {_msg_of(response)}. Nothing was attached and no token "
                f"exists. {advice}",
                code=code, msg=_msg_of(response), body=response,
                credential_env=WRITE_ENV)
        token = getattr(getattr(response, "data", None), "file_token", None)
        if not token:
            raise MediaUploadError(
                f"the upload of {name!r} returned no file_token, so nothing can be attached")
        return UploadedMedia(
            file_token=token, parent_type=parent_type, parent_node=parent_node,
            size=len(data), sha256=sha256_of(data),
        )

    def download(self, file_token: str) -> bytes:
        """Download ``file_token`` and return its bytes, **in memory, unexamined**.

        Rides the same pinned-SDK ``drive.v1.media`` seam the reader's docx image leg rides
        (module docstring). The bytes are returned for **hashing** — see
        :func:`verify_round_trip`; nothing in this library decodes or renders them.

        A download mints **no** residue: the token was minted by the upload.
        """
        if not file_token:
            raise MediaDownloadError(
                "a download needs a file_token; an attachment cell's file_token is the only "
                "durable handle a read-back carries")
        request = DownloadMediaRequest.builder().file_token(file_token).build()
        response = self._paced(self._sdk.drive.v1.media.download, request)
        code = _code_of(response)
        if code in FILE_TOKEN_NOT_FOUND_CODES:
            raise api_error_as(
                MediaTokenNotFoundError,
                f"the drive family no longer resolves the file token {file_token!r}: "
                f"Code: {code}, Msg: {_msg_of(response)}. A token outlives the table it was "
                f"attached to, so this is not a table problem — re-upload the file and attach "
                f"the new token",
                code=code, msg=_msg_of(response), body=response,
                credential_env=WRITE_ENV)
        if code:
            raise api_error_as(
                MediaDownloadError,
                f"the download of {file_token!r} was refused: Code: {code}, "
                f"Msg: {_msg_of(response)}. No bytes were returned. Verify the token came "
                f"from an attachment cell this app can read, then retry",
                code=code, msg=_msg_of(response), body=response,
                credential_env=WRITE_ENV)
        payload = getattr(response, "file", None)
        if payload is None:
            raise MediaDownloadError(
                f"the download of {file_token!r} answered success with no file content, so "
                f"there is nothing to verify. Re-read the cell and retry with the token it "
                f"reports")
        return payload.read()

    def permalink(self, file_token: str) -> MediaPermalink:
        """The ``/file/`` address a **person** can be sent for this attachment, plus its title.

        An Attachment cell hands a caller a ``file_token`` and two ``open-apis`` API routes —
        addresses for a client, not for another user. This asks Lark for the object's own
        web address instead: ``POST drive/v1/metas/batch_query`` with ``doc_type: file`` and
        ``with_url: true``, **the same call the folder leg
        (:meth:`larkdocio.drive.files_write.DriveFilesWriteClient.permalink`) already makes**,
        measured working on both shipped ``parent_type`` spellings' tokens. A URL is never
        assembled from a host and a token here: an address this library invented would be a
        guess wearing the shape of an answer, so an absent ``url`` raises instead.

        <<SWALLOW>>

        <<OUTLIVES>>

        <<NOT_ACCESS>>

        A metadata query mints nothing: it is a read, it leaves no residue, and it is the one
        leg of this module that can be run against a token whose parent is gone.
        """
        if not file_token:
            raise MediaPermalinkError(
                "a permalink needs a file_token; an attachment cell's file_token is the only "
                "durable handle a read-back carries")
        doc = RequestDoc.builder() \
            .doc_token(file_token).doc_type(MEDIA_META_DOC_TYPE).build()
        body = MetaRequest.builder().request_docs([doc]).with_url(True).build()
        request = BatchQueryMetaRequest.builder().request_body(body).build()
        response = self._paced(self._sdk.drive.v1.meta.batch_query, request)
        code = _code_of(response)
        if code:
            raise api_error_as(
                MediaPermalinkError,
                f"the metadata query for {file_token!r} was refused: Code: {code}, "
                f"Msg: {_msg_of(response)}. The file may well exist; its address is simply "
                f"not known, and one is never constructed from the token here",
                code=code, msg=_msg_of(response), body=response,
                credential_env=WRITE_ENV)
        data = getattr(response, "data", None)
        for meta in (getattr(data, "metas", None) or ()):
            if _meta_field(meta, "doc_token") != file_token:
                # The batch route answers in its own order, so the meta is matched by TOKEN.
                # Taking metas[0] would hand a caller another file's address under their own
                # token — the quietest possible wrong answer.
                continue
            url = _meta_field(meta, "url")
            if url:
                return MediaPermalink(file_token=file_token, url=url,
                                      title=_meta_field(meta, "title") or "")
            raise MediaPermalinkError(
                f"the metadata query for {file_token!r} answered success and reported no "
                f"url, so there is no address to hand anyone. An address is never "
                f"constructed from the token here: an invented one that happened to 404 "
                f"would be worse than none")
        raise MediaPermalinkNotResolvedError(
            f"the metadata query for {file_token!r} answered success WITH NO META for that "
            f"token, which is not a permalink. {_failed_reason(data, file_token)} "
            f"{WRONG_DOC_TYPE_IS_AN_EMPTY_ANSWER}")


# The three disclosures the permalink leg must ship WITH — quoted into the op's own docstring
# from their single authorings above, the ``larkdocio.write.media`` precedent. A docstring
# that restated them in its own words would be three more things that can drift.
BaseMediaClient.permalink.__doc__ = (BaseMediaClient.permalink.__doc__ or "") \
    .replace("<<SWALLOW>>", WRONG_DOC_TYPE_IS_AN_EMPTY_ANSWER) \
    .replace("<<OUTLIVES>>", PERMALINK_OUTLIVES_THE_BYTES) \
    .replace("<<NOT_ACCESS>>", PERMALINK_IS_NOT_ACCESS)


def _meta_field(meta, name: str):
    """One field of a meta, however the seam hands it over (SDK object or mapping)."""
    value = getattr(meta, name, None)
    if value is None and isinstance(meta, Mapping):
        value = meta.get(name)
    return value


#: Lark's own reason for a token, read out of the answer's ``failed_list`` — the SHARED
#: authoring (LD-606), not a second copy. This module was the ONE of five call sites on
#: ``metas/batch_query`` that read the key at all; it is now the one that quotes the reader every
#: site quotes. The lifted version also reads the **raw-HTTP dict** seam, which the copy that
#: lived here could not: it reached ``failed_list`` by ``getattr`` alone, so against a dict it
#: returned the "named no reason" fallback while looking like it worked.
_failed_reason = failed_reason


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
