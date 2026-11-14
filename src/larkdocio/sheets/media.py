"""larkdocio.sheets.media — the two ways a picture gets onto a spreadsheet.

**They are different products, not two spellings of one, and the guide says them apart in one
sentence: an IN-CELL image IS the cell's value; a FLOAT image floats OVER a range and is
anchored to it.** Both were measured end to end in the same spike; both ship here.

* **In-cell** (:func:`put_image_in_sheet`) — **one** call carries the bytes as a JSON int
  array, and the verdict is a fresh read of the cell. Described first, below.
* **Float** (:func:`put_float_image_in_sheet`) — **three** beats: an ``upload_all`` bound to
  the **WORKBOOK**, a ``float_images`` create that binds the token to a range, and a fresh
  ``float_images/query`` as the verdict. :func:`remove_float_image_from_sheet` takes it away,
  and its verdict is the query too. Described in full further down.

---

## The IN-CELL route

The picture **is the cell's value**. One ``POST …/values_image`` carries the bytes, the
target cell and a display name; the cell then reads back as an ``embed-image`` value
pointing at a drive media token whose bytes are byte-identical to what was sent.

**Three calls' worth of route, in one call — and then the call that actually proves it.**

1. ``POST /open-apis/sheets/v2/spreadsheets/{tok}/values_image`` with
   ``{"range": …, "image": [ints], "name": …}`` — the write. **There is NO
   ``medias/upload_all`` leg on this route at all**: the bytes travel in the JSON body.
2. ``GET /open-apis/sheets/v2/spreadsheets/{tok}/values/{range}`` — **the verdict**. An
   accepted call is not a stored one, so what this op reports is what the cell now holds,
   never the write's own ``code 0``.
3. optionally ``GET /open-apis/drive/v1/medias/{file_token}/download`` — the bytes, hashed
   against what went up by :func:`larkdocio.base.media.verify_round_trip`, the one
   definition of that check in this library, reused rather than restated.

**THE THREE DISCLOSURES, all measured** (the sheets-media spike's captures, in the
source repository — this library's own source tree, not the wheel — except one control, which
is an unpublished recording).

* **The call mints its OWN media token.** The ``fileToken`` the cell reports is **not** a
  token any caller uploaded — this route has no upload leg — and it is unrelated to a token
  the separate float-image upload leg would mint for the same picture. One picture, two
  independent residues. That token is **PERMANENT, UNPURGEABLE RESIDUE**: trashing the
  workbook does not remove the bytes it carried, and **no route in Lark's open API purges
  drive media — measured, enumerated and scoped in this module's § PERMANENT, UNPURGEABLE
  RESIDUE below**. Think of a write here as permanent before you send it.
* **The clear is an ordinary ``""`` value write, not a delete verb.** Writing the empty
  string over the cell removes the picture (``put_values(tok, "tab!B2:B2", [[""]])``); the
  value then reads back as ``""``. There is no *delete image* call, and this library does
  not invent one.
* **``90215 "can not found sheetId"`` is what a bad tab answers.** That refusal is the
  measured control that makes an accepted write meaningful acceptance rather than an
  unfalsified call. The number is quoted here as prose and lives in the captures; nothing
  in this library asserts it, because Lark may renumber it.

**THE INT-ARRAY BODY IS A REAL SIZE CEILING.** The bytes go up as a **JSON array of
integers**, so one byte becomes up to four characters on the wire and the request is
roughly **3–4×** the file's own size. A consumer sizing an upload budget from the file's
own size will under-provision. **The exact byte limit is unmeasured** — only an 88-byte PNG
was ever sent. The multipart alternatives do not pay this inflation: a file uploaded into a
folder (:func:`larkdocio.drive.files_write.put_file_in_folder`) and linked from a sentence,
and the **float-image** route (``medias/upload_all`` with ``parent_type: sheet_image``, then
a ``float_images`` bind), which anchors a picture **over** a range instead of storing it as
a cell's value — a different product, measured live in the same spike.

**Bytes are hashed, never inspected.** Nothing in this module decodes, renders, logs or
prints a payload.

**What is measured, and what is UNMEASURED.** Everything above was observed on **one
tenant, on one day, with a ``tenant_access_token``, sending one 88-byte PNG, against one
workbook the harness created and then trashed**. Therefore: a ``user_access_token`` is
**unmeasured**; media kinds other than PNG (video, audio, pdf, gif, svg) are
**unmeasured**; images larger than 88 bytes and the route's documented size ceilings are
**unmeasured**; a write into a cell that **already holds a value** is **unmeasured**;
**multi-cell and merged-cell ranges** are **unmeasured** (and refused here rather than
guessed at); the **``STALE_SHEET``** interaction and concurrent writers are **unmeasured**;
whether the picture survives an **xlsx export** is **unmeasured**; and whether the
``embed-image`` value's ``link`` resolves anywhere is **unmeasured** — the measured
retrieval path is the media download above. On the tenant these measurements were made on
the READ and WRITE credential pairs named one app, so nothing here is evidence about scope separation.

**The RENDERING axis is UNMEASURED and this module does not claim it.** No API call can
observe what a client draws. What is measured is exactly this: the write is accepted, the
cell reads back as an image carrying a token, and the bytes re-download byte-identical by
sha256 and length. Whether a human looking at the sheet sees a picture is a question only a
human looking at a client can answer.

**Not plan-gated, and it says so.** This op does **not** go through the sheets writeback
engine's ``dry_run`` → ``Plan`` → ``apply`` gate and is not under the ``STALE_SHEET``
compare-and-swap: it needs bytes, which the plan compiler has no way to carry, and the
staleness interaction was never measured. It is a **leg beside** that engine — the same
shape, and for the same reason, as the docx image op
(:func:`larkdocio.write.media.put_image_in_document`) — and ``capabilities()`` reports it
as one.

---

## The FLOAT route — three beats, and four ways a careful person gets it wrong

A **float image** floats **over** a range and is anchored to it; it is **not a cell value at
all**, which is why no values read can see one. Putting one there is the docx image recipe's
Sheets analogue — the same three beats with one real difference:

1. ``POST /open-apis/drive/v1/medias/upload_all`` with ``parent_type: sheet_image`` and
   **``parent_node`` = THE SPREADSHEET TOKEN**;
2. ``POST /open-apis/sheets/v3/spreadsheets/{tok}/sheets/{sid}/float_images`` with
   ``{float_image_token, range, width, height, offset_x, offset_y}`` — **the bind**, and the
   first place the tab is named at all;
3. ``GET …/float_images/query`` — **the verdict**. Nothing else establishes what exists.

**TRAP 1 — ``parent_node`` IS THE WORKBOOK. This is the one place a docx habit will
mislead.** On the docx route the upload binds to the **block** you created a moment earlier;
here it binds to the **spreadsheet token** — **not a cell, not a sheet_id** — and the tab only
appears later, in the bind's ``range``. A developer carrying the docx shape across will reach
for the tab or the anchor cell, and the endpoint will not tell them otherwise in any useful
way. The invented-parent-type control (``sheet_banana_image`` → ``1061002 params error.``,
an unpublished recording) is what makes the accepted spelling real acceptance rather than an
unfalsified call.

**TRAP 2 — the upload's own ``code 0`` is NOT a bind.** A fresh ``float_images/query`` taken
after a successful upload and before any create answers ``{"items": []}`` (capture ``105-``)
— the same lesson as the docx route. So :func:`put_float_image_in_sheet` never treats the
upload's answer, or the create's answer, as success: it re-queries the tab and refuses if the
float image it created is not listed.

**TRAP 3 — one refusal on this route wears a server error's clothes.**
<<FLOAT_IMAGE_REFUSAL_IS_NOT_A_RETRY>>

**TRAP 4 — the bind DOES NOT POLICE image-vs-file tokens.** A token uploaded with
``parent_type: sheet_file`` is **accepted** by the float-image create with ``code 0`` and is
then listed as a float image (captures ``207-``/``208-``). A caller who mixes their token
families gets **silence rather than a refusal**. This library answers it from both sides, and
neither side is a guess: the op **mints the token it binds** and takes no
``float_image_token`` parameter, so it cannot reach that case at all; and
:class:`FloatImageMediaClient` refuses the ``sheet_file`` spelling **locally, before any
call**, so this leg cannot mint one either. The low-level
:meth:`~larkdocio.sheets.write_client.SheetsWriteClient.create_float_image` relays Lark's
acceptance **with the disclosure**, because nothing in a token's text says which family
minted it and refusing on a guess would be inventing a rule nobody published.

**Removal ships with the create** (:func:`remove_float_image_from_sheet`):
``DELETE …/float_images/{id}`` (capture ``303-``), verdicted by the fresh query no longer
listing the id (``304-``) — never by the delete's own ``code 0``. Without it the route could
not be exercised reversibly and every run would leave a picture behind.

**PERMANENT, UNPURGEABLE RESIDUE — and the delete does not touch it.** The upload mints a
drive media token, and removing the float image (or trashing the whole workbook) does **not**
remove the bytes. A run that uploads and then fails to bind leaves a token that will never
point at anything: that outcome is **reported as what it is** rather than as *nothing
happened*. The absence of a purge is **measured, enumerated and scoped**, not assumed — and it
covers both of this module's routes and the docx one alike:

<<NO_ROUTE_PURGES_DRIVE_MEDIA>>

**What is measured on the float route, and what is UNMEASURED.** The same narrow edge as
above — **one tenant, one day, a ``tenant_access_token``, one 88-byte PNG, one workbook the
harness created and then trashed**. Therefore, all **unmeasured, not refuted**: a
``user_access_token``; media kinds other than PNG; the chunked-upload family; images larger
than 88 bytes and any documented size ceiling; **``float_images`` PATCH (move / resize) and
the GET-one — never tried**; multi-cell and merged ranges; the ``STALE_SHEET`` interaction and
concurrent writers; whether the picture survives an **xlsx export**; and whether a **permalink
exists** for a sheet-bound media token. This tenant's READ and WRITE credential pairs alias
one app, so nothing here is evidence about scope separation.

**And rendering, again: UNMEASURED and unmeasurable by API.** What is proven is that the
token uploads, the bind is accepted, the tab's fresh query lists the float image at the range
asked for, and the bytes re-download byte-identical by sha256 and length. Whether a human
looking at the spreadsheet sees a picture is a click, not a probe.

**Not plan-gated either, and for the same reason** — it needs bytes the plan compiler cannot
carry, and the ``STALE_SHEET`` interaction was never measured. ``capabilities()`` reports both
media ops as **legs** beside the sheets apply engine, never as gated operations.
"""
from dataclasses import dataclass
from typing import Optional, Tuple

from larkdocio.base.media import (
    NO_ROUTE_PURGES_DRIVE_MEDIA,
    BaseMediaClient,
    UploadedMedia,
    sha256_of,
    verify_round_trip,
)
from larkdocio.errors import LarkAPIError
from larkdocio.sheets import cell_model
from larkdocio.sheets.write_client import (
    FLOAT_IMAGE_REFUSAL_IS_NOT_A_RETRY,
    SheetsWriteClient,
    normalize_write_range,
)

# QUOTED, never re-typed: the mis-typed-refusal disclosure has one authoring (the write
# client, beside the call it describes) and the purge disclosure has one
# (``larkdocio.base.media``); this module reads both in rather than paraphrasing them.
__doc__ = (__doc__ or "").replace(
    "<<FLOAT_IMAGE_REFUSAL_IS_NOT_A_RETRY>>", FLOAT_IMAGE_REFUSAL_IS_NOT_A_RETRY).replace(
    "<<NO_ROUTE_PURGES_DRIVE_MEDIA>>", NO_ROUTE_PURGES_DRIVE_MEDIA)

#: What **Lark's own read-back** calls the mount point of a token minted by
#: ``values_image`` — quoted from the value's ``link``
#: (``…&mount_point=sheet_image&mount_node_token=<spreadsheet token>``, the sheets-media
#: spike's capture ``203-``, in the source repository), **never sent by this library**: this route has no upload leg
#: and this library declares no ``parent_type`` on it. It exists so the round-trip anchor
#: below can say where the bytes live in Lark's own words.
IN_CELL_IMAGE_MOUNT_POINT = "sheet_image"


class SheetsInCellImageError(LarkAPIError):
    """An in-cell image write that did not happen, or did not stick."""


class SheetsInCellImageBindError(SheetsInCellImageError):
    """The cell read back **without** an image.

    The one failure this op exists to make visible: the write answered ``code 0`` and the
    cell holds no picture. Carries the workbook and the range so a caller can look.
    """

    def __init__(self, message, *, spreadsheet_token, a1_range, **kwargs):
        super().__init__(message, **kwargs)
        self.spreadsheet_token = spreadsheet_token
        self.a1_range = a1_range


class SheetsMediaClient(BaseMediaClient):
    """The drive media **download** leg for a token a sheet cell reports.

    Same endpoint, same refusals, same pacing and the same round-trip check as every other
    media leg in this library — subclassed rather than re-implemented.

    **It cannot upload, by construction.** :attr:`ALLOWED_PARENT_TYPES` is empty, so an
    upload is refused locally, before any call. That is not shyness: the in-cell route has
    no upload leg, and a stray upload would mint a permanent media token that nothing on a
    sheet would ever point at.
    """

    ALLOWED_PARENT_TYPES: Tuple[str, ...] = ()

    PARENT_NODE_NOUN = (
        "nothing this leg can use — the in-cell image route carries its bytes in the "
        "values_image body and mints its own token, so there is no upload to parent"
    )

    PARENT_TYPE_ADVICE = (
        "this leg downloads and does not upload: the in-cell image route has no "
        "medias/upload_all step at all, so no parent type is sent for any value"
    )

    UPLOAD_REFUSAL_ADVICE = (
        "Write the picture with put_image_in_sheet, which is the whole route; nothing is "
        "uploaded out of band"
    )


@dataclass(frozen=True)
class InCellImage:
    """One picture stored as a cell's value: where it landed, what landed, and the proof.

    ``file_token`` is Lark's **own** minted token, read off the cell rather than supplied —
    and it is permanent, unpurgeable residue. ``range`` and ``revision`` come from the
    **fresh read-back**, not from the write's answer. ``sha256`` is the digest of the bytes
    as they were **sent**; ``bytes_verified`` says whether they were downloaded again and
    compared against it — the difference between *"the calls answered"* and *"the file is
    there"*.

    ``width`` / ``height`` are the cell-image geometry Lark reports. ``link`` is captured
    exactly as reported and is **UNMEASURED**: an internal-api host URL with no signature
    parameter, whose resolvability — for a browser, a collaborator, or at all — was never
    established, so it is carried as structure and never presented as a working URL.
    """

    spreadsheet_token: str
    range: str
    file_token: str
    size: int
    sha256: str
    bytes_verified: bool
    revision: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    link: Optional[str] = None


def put_image_in_sheet(
    *,
    client: SheetsWriteClient,
    spreadsheet_token: str,
    a1_range: str,
    data: bytes,
    name: str,
    media: Optional[SheetsMediaClient] = None,
) -> InCellImage:
    """Put ``data`` in ONE cell as its value, and return what the cell then holds.

    ``a1_range`` is a **single cell**, ``"{sheetId}!B2"`` or ``"{sheetId}!B2:B2"`` (a bare
    cell is normalized — the ``90202`` guard the whole sheets write surface lives under).
    A wider range is **refused before any call**: multi-cell and merged-cell targets are
    **unmeasured**, and an unmeasured guess here would mint permanent residue.

    **The verdict is the fresh read-back, never the write's ``code 0``.** After the write
    this re-reads the range and confirms the cell now carries an ``embed-image`` value with
    a token, raising :class:`SheetsInCellImageBindError` if it does not — reusing the
    reader's own typed in-cell-image segment for the parse rather than minting a second one.

    **Byte verification is opt-in, and opt-in by construction**: pass a
    :class:`SheetsMediaClient` as ``media`` and the token is downloaded again and compared
    against what went up by :func:`larkdocio.base.media.verify_round_trip` — the one
    definition of that check here. Without one, nothing is downloaded and
    ``bytes_verified`` is ``False``, which is the honest answer rather than a silent claim.

    **Residue.** A successful call mints a **permanent** drive media token — Lark's own,
    not one you uploaded — and **no route in Lark's open API purges drive media — measured,
    not assumed** (the nine spellings tried, the fourteen sends, and the scope the claim may
    not exceed are in :data:`larkdocio.base.media.NO_ROUTE_PURGES_DRIVE_MEDIA`): trashing the
    workbook does not remove it. A failure *after* the write leaves that token behind, so
    the exception carries ``orphan_file_token`` when one is known; nothing here issues a
    cleanup, because none exists.

    **The clear.** There is no delete verb: write ``""`` over the cell
    (``client.put_values(token, a1_range, [[""]])``) and the value reads back as ``""``.

    **Rendering is unmeasured** — no API call can observe what a client draws.
    """
    if data is None or not data:
        raise SheetsInCellImageError(
            "an in-cell image needs bytes; nothing was sent, because a write here mints a "
            "permanent media token and an empty one could never be undone")
    if not name:
        raise SheetsInCellImageError(
            "an in-cell image needs a name — it is the display name Lark stores with the "
            "picture, and the route was only ever measured with one")
    target = normalize_write_range(a1_range)
    _refuse_a_range_wider_than_one_cell(target)

    client.put_values_image(spreadsheet_token, target, data, name)

    value_range = client.read_value_range(spreadsheet_token, target)
    image = _the_image_the_cell_now_holds(value_range)
    if image is None or not image.file_token:
        raise SheetsInCellImageBindError(
            f"the cell {target!r} in {spreadsheet_token!r} read back without an image: the "
            f"write was accepted and nothing is stored there. An accepted call is not a "
            f"stored one, so this is reported rather than counted as success",
            spreadsheet_token=spreadsheet_token, a1_range=target)

    verified = False
    if media is not None:
        try:
            verify_round_trip(_the_anchor(image.file_token, spreadsheet_token, data),
                              media.download(image.file_token))
        except Exception as exc:  # the token exists and is permanent; say which one
            exc.orphan_file_token = image.file_token
            raise
        verified = True

    return InCellImage(
        spreadsheet_token=spreadsheet_token,
        range=value_range.get("range") or target,
        file_token=image.file_token,
        size=len(data),
        sha256=sha256_of(data),
        bytes_verified=verified,
        revision=value_range.get("revision"),
        width=image.width,
        height=image.height,
        link=image.link,
    )


def _refuse_a_range_wider_than_one_cell(target: str) -> None:
    """One cell only — everything wider is unmeasured, and refused rather than guessed."""
    cell = target.rpartition("!")[2]
    start, _, end = cell.partition(":")
    if start != end:
        raise SheetsInCellImageError(
            f"{target!r} spans more than one cell. Only a single-cell target was ever "
            f"measured on this route; multi-cell and merged-cell writes are UNMEASURED, "
            f"not refuted — and nothing was sent, because a write here mints a permanent "
            f"media token. Write one cell at a time, or measure the wider case first")


def _the_image_the_cell_now_holds(value_range: dict) -> "Optional[cell_model.EmbedImage]":
    """The typed in-cell image in the first cell of a read-back, or ``None``.

    The parse is the reader's — :func:`larkdocio.sheets.cell_model.parse_segments` — so the
    wire shape has exactly one reader in this library.
    """
    rows = value_range.get("values") or []
    if not rows or not rows[0]:
        return None
    for segment in cell_model.parse_segments(rows[0][0]):
        if isinstance(segment, cell_model.EmbedImage):
            return segment
    return None


def _the_anchor(file_token: str, spreadsheet_token: str, data: bytes) -> UploadedMedia:
    """The comparison anchor :func:`verify_round_trip` takes — its own input type, reused.

    The token is **Lark's**, minted by the write; the parent fields are **quoted from
    Lark's own read-back** (the value's ``link`` carries ``mount_point=sheet_image`` and
    ``mount_node_token=<the workbook>``), because this route sends no parent of its own.
    """
    return UploadedMedia(
        file_token=file_token,
        parent_type=IN_CELL_IMAGE_MOUNT_POINT,
        parent_node=spreadsheet_token,
        size=len(data),
        sha256=sha256_of(data),
    )


# --------------------------------------------------------------------------- #
# The FLOAT route (LD-448) — a picture anchored OVER a range.                  #
# --------------------------------------------------------------------------- #

#: The ``parent_type`` the float-image upload **sends**. The one spelling measured for a
#: spreadsheet (capture ``103-``); the invented ``sheet_banana_image`` control was refused
#: (an unpublished recording), and every other spelling is unmeasured rather than refuted. It happens to be
#: the same string Lark reports as the *mount point* of an in-cell image's own token
#: (:data:`IN_CELL_IMAGE_MOUNT_POINT`) — a measured coincidence, and two different facts:
#: that one is **read** out of a link this library never sends, this one is **sent**.
SHEET_IMAGE_PARENT_TYPE = "sheet_image"

#: The ``parent_type`` of the OTHER sheet-bound media family — named here **only** so the
#: swallow can be disclosed and refused by name. **This library never sends it**: the upload
#: is accepted (capture ``206-``), no sheets route consumes it *as a file*, and the one route
#: that takes it (the float-image bind) files it as an image (``207-``/``208-``).
SHEET_FILE_PARENT_TYPE = "sheet_file"


class SheetFloatImageError(LarkAPIError):
    """A float-image failure. Carries what exists so far, never a guess."""


class SheetFloatImageBindError(SheetFloatImageError):
    """The tab's fresh query did **not** list the float image that was just created.

    The one failure this op exists to make visible: the upload answered success, the create
    answered success, and the tab does not carry the picture. Carries the ids so a caller can
    look at both — and the media token, because it is permanent residue either way.
    """

    def __init__(self, message, *, spreadsheet_token, sheet_id, float_image_token,
                 float_image_id=None, **kwargs):
        super().__init__(message, **kwargs)
        self.spreadsheet_token = spreadsheet_token
        self.sheet_id = sheet_id
        self.float_image_token = float_image_token
        self.float_image_id = float_image_id


class SheetFloatImageRemoveError(SheetFloatImageError):
    """The delete was accepted and the fresh query **still lists** the float image."""

    def __init__(self, message, *, spreadsheet_token, sheet_id, float_image_id, **kwargs):
        super().__init__(message, **kwargs)
        self.spreadsheet_token = spreadsheet_token
        self.sheet_id = sheet_id
        self.float_image_id = float_image_id


#: What a caller is told when the upload landed and the bind did not. Its own sentence,
#: because *"the call failed"* and *"a permanent token now exists and no picture does"* are
#: different facts and only the second one costs the caller anything.
FLOAT_IMAGE_PARTIAL_SUCCESS = (
    "THE UPLOAD LANDED AND THE BIND DID NOT, so this is NOT 'nothing happened': a "
    "PERMANENT, UNPURGEABLE media token now exists and NO PICTURE does. NO ROUTE in Lark's "
    "open API purges drive media — MEASURED, NOT ASSUMED: the nine spellings tried, the "
    "fourteen sends and the scope the claim may not exceed are in "
    "larkdocio.base.media.NO_ROUTE_PURGES_DRIVE_MEDIA — so the token cannot be cleaned up. "
    "It is carried on this error as "
    "orphan_file_token so it can at least be recorded. Nothing was retried: an error on this "
    "route is a refusal, and a fresh float_images/query is the only verdict"
)


class FloatImageMediaClient(BaseMediaClient):
    """The drive media **upload + download** leg for the FLOAT-image route.

    Same endpoint, same refusals, same pacing and the same round-trip check as every other
    media leg here — subclassed rather than re-implemented. Two things are its own:

    * **``parent_node`` IS THE SPREADSHEET TOKEN** — the workbook, *not a cell and not a
      ``sheet_id``*. This is the parameter a docx habit gets wrong (there, it is the block
      id), and pointing it at the wrong workbook attaches permanent, unpurgeable residue to
      something you did not mean to touch.
    * **``sheet_image`` and nothing else.** The ``sheet_file`` spelling is refused **locally,
      before any call**, so this leg cannot mint a token the float-image bind would silently
      swallow as an image (:data:`SHEET_FILE_PARENT_TYPE`).

    Distinct from :class:`SheetsMediaClient`, which is the IN-CELL route's download-only leg
    and can upload nothing at all — the two routes mint tokens differently and merging the
    clients would blur which one a token came from.
    """

    ALLOWED_PARENT_TYPES: Tuple[str, ...] = (SHEET_IMAGE_PARENT_TYPE,)

    PARENT_NODE_NOUN = (
        "the spreadsheet_token of the WORKBOOK the picture is going into — NOT a cell and "
        "NOT a sheet_id (the tab is named later, in the bind's range), and NOT a block id "
        "the way the docx image route takes one"
    )

    PARENT_TYPE_ADVICE = (
        "sheet_image is the one spelling measured for a spreadsheet, and the sheet_file "
        "spelling is deliberately not sent here: the float-image bind accepts it and files "
        "it as an image, so a token minted under it is a swallow waiting to happen"
    )

    UPLOAD_REFUSAL_ADVICE = (
        "Check that parent_node is the spreadsheet_token of a workbook this app can write — "
        "not a sheet_id and not a cell — then retry"
    )


@dataclass(frozen=True)
class FloatImage:
    """One picture floating over a range: where it landed, what landed, and the proof.

    Every field but ``size`` / ``sha256`` / ``bytes_verified`` comes from **the fresh
    ``float_images/query``**, not from the create's own answer — the whole point of the route
    being three beats is that the last one is the only verdict.

    ``sha256`` is the digest of the bytes as they were **sent**; ``bytes_verified`` says
    whether they were downloaded again and compared against it. ``float_image_token`` is the
    media token the upload minted, and it is **permanent, unpurgeable residue** that outlives
    both the float image and the workbook.

    Carries **no link of any kind**: the upload answers a token, and a media read-back's
    link-bearing keys are short-lived signed links treated as credential-class everywhere in
    this library.
    """

    spreadsheet_token: str
    sheet_id: str
    float_image_id: str
    float_image_token: str
    a1_range: str
    size: int
    sha256: str
    bytes_verified: bool
    width: Optional[int] = None
    height: Optional[int] = None
    offset_x: Optional[int] = None
    offset_y: Optional[int] = None


def put_float_image_in_sheet(
    *,
    client: SheetsWriteClient,
    media: FloatImageMediaClient,
    spreadsheet_token: str,
    sheet_id: str,
    a1_range: str,
    data: bytes,
    name: str,
    width: int,
    height: int,
    offset_x: int = 0,
    offset_y: int = 0,
    verify_bytes: bool = True,
) -> FloatImage:
    """Float a picture over ``a1_range`` and return what the tab's fresh query then lists.

    The three calls happen here as a unit, in the fixed order, and the order is enforced by
    there being no other way in: this function takes **no pre-made token**, so neither the
    wrong upload parent nor a token from another family can be driven from outside.

    **``parent_node`` is the WORKBOOK — the one place a docx habit will mislead.** The upload
    is parented on ``spreadsheet_token``, *not a cell and not a ``sheet_id``*; the tab is
    named for the first time in the bind, and in ``a1_range``. On the docx route the upload
    binds to the image **block**, and carrying that shape across is the mistake this op exists
    to make unmakeable.

    **The verdict is the fresh ``float_images/query``, never any call's own ``code 0``.** An
    upload that answers success has bound nothing (a query before the create answers
    ``{"items": []}``), and the create's answer is an answer, not a read. If the query does
    not list what was just created, this raises :class:`SheetFloatImageBindError` rather than
    reporting a success nobody observed.

    **An error here is a REFUSAL and is never retried.** Nothing in this path retries; the
    typed refusal arrives carrying Lark's verbatim body plus this library's own words about
    the route mis-typing a refusal as a server error.

    ``a1_range`` is the anchor, ``"{sheetId}!A1:A1"`` (a bare cell is normalized — the
    ``90202`` guard the whole sheets write surface lives under). ``width`` / ``height`` are
    required because the route was only ever measured with them; ``offset_x`` / ``offset_y``
    default to the measured ``0``.

    With ``verify_bytes`` (the default) the token is downloaded again and compared against the
    upload **by sha256 and length** — :func:`larkdocio.base.media.verify_round_trip`, the one
    definition of that check in this library. The bytes are never inspected.

    **Residue.** A successful call mints a **permanent** drive media token. **No route in
    Lark's open API purges drive media — measured, not assumed** (the nine spellings tried,
    the fourteen sends, and the scope the claim may not exceed are in
    :data:`larkdocio.base.media.NO_ROUTE_PURGES_DRIVE_MEDIA`), and neither
    :func:`remove_float_image_from_sheet` nor trashing the workbook removes it. A failure *after* the upload leaves that token behind: the exception carries
    ``orphan_file_token`` and says plainly that a token exists and a picture does not.

    **Rendering is unmeasured.** This returns when the tab lists the float image and the bytes
    round-trip; what a client draws is outside what any API call can observe.
    """
    if not data:
        raise SheetFloatImageError(
            "a float image needs bytes; nothing was sent, because an upload mints a "
            "permanent media token and an empty one could never be undone")
    if not name:
        raise SheetFloatImageError(
            "a float image needs a name — it is the file name the upload carries, and the "
            "route was only ever measured with one")
    target = normalize_write_range(a1_range)

    # BEAT 1 — the bytes, parented on the WORKBOOK. Nothing exists on the tab yet.
    uploaded = media.upload(
        data=data, name=name,
        parent_type=SHEET_IMAGE_PARENT_TYPE, parent_node=spreadsheet_token,
    )

    # BEAT 2 — the bind. From here on a failure leaves a permanent token behind, so every
    # refusal is re-raised intact, carrying which token that is.
    try:
        created = client.create_float_image(
            spreadsheet_token, sheet_id,
            float_image_token=uploaded.file_token, a1_range=target,
            width=width, height=height, offset_x=offset_x, offset_y=offset_y,
        )
    except Exception as exc:
        _blame_the_orphan(exc, uploaded.file_token)
        raise

    try:
        # BEAT 3 — THE VERDICT. Not the create's answer: a fresh read of the tab.
        listed = _the_float_image_the_tab_now_lists(
            client, spreadsheet_token, sheet_id, created, uploaded)
        verified = False
        if verify_bytes:
            verify_round_trip(uploaded, media.download(uploaded.file_token))
            verified = True
    except Exception as exc:
        _blame_the_orphan(exc, uploaded.file_token)
        raise

    return FloatImage(
        spreadsheet_token=spreadsheet_token,
        sheet_id=sheet_id,
        float_image_id=listed.get("float_image_id") or "",
        float_image_token=listed.get("float_image_token") or uploaded.file_token,
        a1_range=listed.get("range") or target,
        size=uploaded.size,
        sha256=uploaded.sha256,
        bytes_verified=verified,
        width=listed.get("width"),
        height=listed.get("height"),
        offset_x=listed.get("offset_x"),
        offset_y=listed.get("offset_y"),
    )


def remove_float_image_from_sheet(
    *,
    client: SheetsWriteClient,
    spreadsheet_token: str,
    sheet_id: str,
    float_image_id: str,
) -> Tuple[str, ...]:
    """Remove one float image and return the ids the tab's **fresh query** still lists.

    Removal ships with the create because without it the route cannot be exercised reversibly
    and every run would leave a picture behind.

    **The delete's own ``code 0`` is not the verdict.** This re-queries the tab and raises
    :class:`SheetFloatImageRemoveError` if the id is still listed. The returned tuple is what
    the query answered, so the caller sees the tab rather than a boolean.

    **The BYTES do not go away.** The media token the upload minted is permanent, unpurgeable
    residue: **no route in Lark's open API purges drive media — measured, not assumed** (the
    nine spellings tried, the fourteen sends, and the scope the claim may not exceed are in
    :data:`larkdocio.base.media.NO_ROUTE_PURGES_DRIVE_MEDIA`), and neither this call nor
    trashing the workbook removes it. What this removes is the anchor, not the file.
    """
    if not float_image_id:
        raise SheetFloatImageError(
            "removing a float image needs its float_image_id — the id the tab's "
            "float_images/query reports; nothing was sent")
    client.delete_float_image(spreadsheet_token, sheet_id, float_image_id)
    remaining = tuple(item.get("float_image_id")
                      for item in client.query_float_images(spreadsheet_token, sheet_id))
    if float_image_id in remaining:
        raise SheetFloatImageRemoveError(
            f"the delete of float image {float_image_id!r} was accepted and the tab's fresh "
            f"query STILL lists it. A delete's own code 0 means accepted, not gone, which is "
            f"why this call re-reads rather than believing it. The media token the picture "
            f"points at is permanent residue either way and is not removed by any delete",
            spreadsheet_token=spreadsheet_token, sheet_id=sheet_id,
            float_image_id=float_image_id)
    return remaining


def _the_float_image_the_tab_now_lists(client, spreadsheet_token, sheet_id,
                                       created, uploaded) -> dict:
    """The created float image as the **fresh query** reports it — or a typed refusal.

    Matched on the id the create answered; when the create answered no id at all the token is
    matched instead, so a shape change is reported rather than silently passing.
    """
    float_image_id = (created or {}).get("float_image_id") or ""
    items = client.query_float_images(spreadsheet_token, sheet_id) or []
    for item in items:
        if float_image_id and item.get("float_image_id") == float_image_id:
            return item
        if not float_image_id and item.get("float_image_token") == uploaded.file_token:
            return item
    detail = (f"lists {len(items)} float image(s), none of them this one"
              if items else "lists NO float images at all — which is what an upload alone "
                            "leaves a tab as")
    raise SheetFloatImageBindError(
        f"the float image was not bound: the tab {sheet_id!r} of {spreadsheet_token!r} "
        f"{detail}. The create answered {float_image_id!r} and the uploaded media token was "
        f"{uploaded.file_token!r}. The fresh query is the verdict on this route — a call's "
        f"own success answer is not a stored picture — and the media token is PERMANENT, "
        f"UNPURGEABLE residue that no verb can clean up",
        spreadsheet_token=spreadsheet_token, sheet_id=sheet_id,
        float_image_token=uploaded.file_token, float_image_id=float_image_id or None)


def _blame_the_orphan(error, file_token: str) -> None:
    """Attach the permanent token to a failure after the upload, and say what that means.

    Not a message rewrite: the refusal travels intact (its class, code, msg and body), and
    what is added is the fact only this op knows — that a token exists and a picture does not.
    """
    error.orphan_file_token = file_token
    error.residue_disclosure = FLOAT_IMAGE_PARTIAL_SUCCESS
