"""larkdocio.write.media — put an IMAGE, or attach a FILE, in a document body.

Two ops, one route: **create the empty block → upload the bytes bound to THAT block → patch
the block to bind them → read the block back**. The image is the picture in the body; the
file is the 📎 **attachment card**, and the card is named for what it is — it is a **different
product from an inline sentence link**, which is authored out of a file in a folder plus a run
carrying a link (:meth:`larkdocio.write.model.NewBlock.rich_paragraph`), not from here.

A picture in a document is **three calls, in a fixed order**, and the order is not a style
preference — it is the only order that works:

1. ``POST …/documents/{doc}/blocks/{parent}/children`` with
   ``{"block_type": 27, "image": {…}}`` — an image block, created **empty**;
2. ``POST drive/v1/medias/upload_all`` with ``parent_type: docx_image`` and **``parent_node``
   = the block id from step 1** — the bytes, uploaded *against that block*;
3. ``PATCH …/blocks/{block}`` with ``{"replace_image": {"token": <file_token>}}`` — the bind.

**THE TWO TRAPS, both measured, both the reason this is one op rather than three exposed
calls.**

* **The block must exist before the upload.** An upload parented on the *document* answers
  success and yields a real token — and then **no block will accept it**: the patch is refused
  with a relation mismatch, because the token carries a relation to whatever node it was
  uploaded against. There is no way to fix that token afterwards; it is permanent residue that
  can never be bound.
* **The upload answering ``code:0`` is NOT a bind.** After a successful upload the block's
  ``image.token`` is still **empty**. Nothing points at the bytes until step 3 patches the
  block, and the only thing that proves the bind is a **fresh read of the block** — never the
  patch's own echo. This op reads the block back and refuses if the token it finds is not the
  token it uploaded.

A third measured fact, stated because it is the one that will bite someone reimplementing
this: ``upload_all`` **does not police the type/parent pairing**. It accepted
``parent_type: docx_image`` against a *file* block with ``code:0``. **The bind** is what
enforces the relation, which is why this op's verdict is the read-back and not the upload.

**THE ATTACHMENT'S OWN TRAP — the WRAPPER.** A file create brings **two** blocks into
existence and answers the id of a **view wrapper** whose *child* is the real file block. The
wrapper cannot be created directly and cannot be patched; a caller handed the create's own
``block_id`` meets a block/operation mismatch they have no way to decode. So the attachment op
resolves the child, confirms it really is a file block **before** any upload, and returns the
**child's** id — which is the id anything later has to address.

**PERMANENT, UNPURGEABLE RESIDUE.** Every upload mints a drive media token. The token
outlives the block, and **deleting the document does not remove the media it carried**. This
library's answer is disclosure, not a simulated purge: think of an upload as permanent before
you send it. A *download* mints nothing. The absence of a purge is **measured, enumerated and
scoped**, not assumed:

<<NO_ROUTE_PURGES_DRIVE_MEDIA>>

**SHAREABILITY — the bytes you attach are not an object you can share on their own.**
<<MEDIA_TOKEN_SHAREABILITY>>

**Bytes are hashed, never inspected.** The round-trip check here is
:func:`larkdocio.base.media.verify_round_trip` — the one definition of *"the bytes that came
back are the bytes that went up"* in this library, reused rather than restated. Nothing in
this module decodes, renders, logs or prints a payload.

**What is measured, and what is UNMEASURED.** Everything above was observed on one tenant, on
one day, with a ``tenant_access_token``, on a plain ``docx``, uploading a **PNG**. Therefore:
video, audio, pdf and every other media kind are **unmeasured**; every ``parent_type``
spelling other than ``docx_image`` (``sheet_image``, ``doc_image``, …) is **unmeasured**;
``user_access_token``, ``wiki``-wrapped documents, other tenants, other regions and the
chunked-upload family are **untried, not refuted**. Alignment, scale and a caption were never
measured as create-time image fields and are not offered.

**AND ``width`` / ``height`` DO NOT SURVIVE THE BIND** — the create accepts them, step 3's
``replace_image`` replaces the whole image property, and the block reads back at the uploaded
file's own pixel size. Authored ``560x560``, read back ``2560x2560`` (consumer-observed
on one day, four images); authored ``120x60``, read back ``1x1`` on a **1x1** PNG (captured,
2026-08-19, one image). **No measured route resizes it afterwards** — ``replace_image`` with
size answers ``99992402``, ``update_image`` and a bare ``image`` property answer ``1770001``,
and every other spelling is **unmeasured, not refuted**. **The one lever that works is to
downscale the BYTES before uploading**, so the file's own pixel size is the display size —
and the file extension can lie while you do it: Lark exports a whiteboard as **JPEG** bytes
under a ``.png`` filename, so dispatch on the header rather than the name. The whole
measurement, with its labels, is on :func:`put_image_in_document`.

**The RENDERING axis is UNMEASURED and this module does not claim it.** No API call can
observe what a client draws. What is measured is exactly this: the block is created, the bytes
are bound to it, the block reads back carrying the uploaded token, and the bytes re-download
**byte-identical by sha256 and length**. Whether a reader scrolling past sees a picture is a
question only a human looking at a client can answer, and it is left labelled rather than
answered here.
"""
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from larkdocio.base.media import (
    MEDIA_TOKEN_NOT_INDEPENDENTLY_SHAREABLE,
    NO_ROUTE_PURGES_DRIVE_MEDIA,
    BaseMediaClient,
    UploadedMedia,
    verify_round_trip,
)
from larkdocio.errors import LarkAPIError
from larkdocio.write.client import WriteClient

# QUOTED, never re-typed: the shareability and purge disclosures each have ONE authoring
# (``larkdocio.base.media``) and this module reads them in rather than paraphrasing them.
__doc__ = (__doc__ or "").replace(
    "<<MEDIA_TOKEN_SHAREABILITY>>", MEDIA_TOKEN_NOT_INDEPENDENTLY_SHAREABLE).replace(
    "<<NO_ROUTE_PURGES_DRIVE_MEDIA>>", NO_ROUTE_PURGES_DRIVE_MEDIA)

#: The docx block type of an image. The join key to the capability matrix.
IMAGE_BLOCK_TYPE = 27

#: The ``parent_type`` an upload bound to a docx image block carries. **The one spelling
#: measured**; every other spelling is unmeasured rather than refuted.
DOCX_IMAGE_PARENT_TYPE = "docx_image"

#: The docx block type of a **file attachment** — the 📎 card. A DIFFERENT PRODUCT from an
#: inline sentence link: it is a block in the body, not an anchor on a run of text.
FILE_BLOCK_TYPE = 23

#: The docx block type of the **view wrapper** a file create actually answers. Measured, and
#: the whole reason the attachment needs an op rather than three exposed calls: creating
#: ``{"block_type": 23, "file": {}}`` brings **two** blocks into existence and hands back the
#: wrapper's id, whose child is the real file block. The wrapper is **not creatable directly**
#: and patching it is refused.
FILE_VIEW_WRAPPER_BLOCK_TYPE = 33

#: The ``parent_type`` an upload bound to a docx **file** block carries. **The one spelling
#: measured**; every other spelling is unmeasured rather than refuted.
DOCX_FILE_PARENT_TYPE = "docx_file"

#: The docx block types this library can bring into existence **out of band** — through the
#: dedicated media ops below rather than through the plan-gated authoring path, because they
#: need bytes and a network call the compiler has neither of. The join key both the docx
#: block matrix ``BLOCKS.md`` (in the source repository, not in the wheel) and ``capabilities()`` are
#: pinned against, so the two cannot drift apart.
OUT_OF_BAND_CREATABLE_BLOCK_TYPES: Tuple[int, ...] = (IMAGE_BLOCK_TYPE, FILE_BLOCK_TYPE)

#: The patch body that binds an uploaded token to an image block.
REPLACE_IMAGE = "replace_image"

#: The patch body that binds an uploaded token to a **file** block. Sent to the CHILD; the
#: wrapper answers a block/operation mismatch.
REPLACE_FILE = "replace_file"


class DocxImageError(LarkAPIError):
    """An image-authoring failure. Carries what exists so far, never a guess."""


class DocxImageCreateError(DocxImageError):
    """The create did not answer an image block, so there is nothing to bind bytes to."""


class DocxImageBindError(DocxImageError):
    """The block read back **without** the token that was uploaded to it.

    The one failure this op exists to make visible: the upload answered success, the patch
    answered success, and the block still does not point at the bytes. Carries the block id
    and the file token so a caller can look at both.
    """

    def __init__(self, message, *, block_id, file_token, **kwargs):
        super().__init__(message, **kwargs)
        self.block_id = block_id
        self.file_token = file_token


class DocxMediaClient(BaseMediaClient):
    """The drive media leg with the **docx image** parent vocabulary.

    Identical call, identical refusals, identical pacing, identical round-trip check — the
    only difference from the attachment leg is what a ``parent_type`` may say and what a
    ``parent_node`` *is*. Here ``parent_node`` is **a block id**, not a file or app token.
    """

    ALLOWED_PARENT_TYPES: Tuple[str, ...] = (
        DOCX_IMAGE_PARENT_TYPE, DOCX_FILE_PARENT_TYPE)

    PARENT_NODE_NOUN = (
        "the block_id of the image or file block the bytes are being bound to — NOT the "
        "document id (an upload parented on the document yields a token no block will ever "
        "accept), and for an attachment NOT the view wrapper the create answered"
    )

    PARENT_TYPE_ADVICE = (
        "those are the two spellings measured against a document's own image and file "
        "blocks; every other spelling is unmeasured rather than refused, and nothing is sent "
        "for one"
    )

    UPLOAD_REFUSAL_ADVICE = (
        "Check that parent_node is the block_id of an image or file block that already "
        "exists in a document this app can write, then retry"
    )


@dataclass(frozen=True)
class AuthoredImage:
    """One image put in a document: where it landed, what landed, and the proof.

    ``sha256`` is the digest of the bytes as they were **sent**. ``bytes_verified`` says
    whether they were downloaded again and compared against it — the difference between
    *"the calls answered"* and *"the file is there"*.

    Carries **no link of any kind**: the upload answer's own body is a token, and the two
    link-bearing keys a media read-back can carry are short-lived signed links treated as
    credential-class everywhere in this library.
    """

    document_id: str
    block_id: str
    file_token: str
    size: int
    sha256: str
    bytes_verified: bool


#: The disclosure a caller who never opened the docstring still meets. ``width`` / ``height``
#: are accepted at create and replaced at bind, so a caller who passes them and walks away
#: believes something that is not true; a docstring cannot reach someone who copied a recipe.
#: The parameters are unchanged and still sent — this says so out loud, once, per call.
_GEOMETRY_DOES_NOT_SURVIVE = (
    "put_image_in_document: width/height DO NOT SURVIVE THE BIND. The create accepts them, "
    "then the binding replace_image patch replaces the whole image property, so the block "
    "reads back at the uploaded file's own pixel size (authored 560x560 -> read back "
    "2560x2560, consumer-observed on one day; authored 120x60 -> read back 1x1 on a 1x1 PNG, "
    "captured 2026-08-19). No measured route resizes it afterwards. DOWNSCALE THE IMAGE "
    "BYTES BEFORE UPLOADING - that is the only lever that works."
)


def put_image_in_document(
    *,
    client: WriteClient,
    media: DocxMediaClient,
    document_id: str,
    data: bytes,
    name: str,
    parent_block_id: Optional[str] = None,
    index: int = -1,
    width: Optional[int] = None,
    height: Optional[int] = None,
    verify_bytes: bool = True,
) -> AuthoredImage:
    """Put an image in ``document_id`` and return the block id **and** the file token.

    The three calls happen here as a unit, in the fixed order, and the order is enforced by
    there being no other way in: this function takes no pre-made block id and no pre-made
    token, so the sequence that produces a relation mismatch cannot be driven from outside.

    **The block must exist first**, so the create comes before the upload; and **an upload
    answering success is not a bind** — the block's token stays empty until the patch — so the
    verdict is a **fresh read-back** of the block, never the patch's own echo. If the block
    reads back without the uploaded token, this raises :class:`DocxImageBindError` rather than
    reporting a success nobody observed.

    With ``verify_bytes`` (the default) the token is downloaded again and compared against the
    upload **by sha256 and length** — :func:`larkdocio.base.media.verify_round_trip`, the one
    definition of that check in this library. The bytes are never inspected.

    **WHERE IT LANDS — ``parent_block_id`` + ``index``, MEASURED.** ``parent_block_id`` names
    the block the new image becomes a **child of**, and defaults to the document's root (a docx
    document's root block id **is** its document id). ``index`` is a **0-based position in that
    parent's ordered ``children`` list, and the new block is inserted BEFORE the child
    currently at that position** — ``index=0`` puts it first, ``index=1`` puts it between the
    existing first and second children, and the default ``-1`` **appends**. Measured on a
    disposable document by ``tests/test_live_docx_media_placement_gate.py`` (**in the source repository**,
    not in the wheel), which reads the parent's own ``children`` back after every case rather
    than trusting a create's echo. An
    ``index`` past the end is **unmeasured, not refuted**.

    **A TABLE CELL is a legal parent** — a cell's own block id, passed here, creates the image
    **inside that cell**, with the bytes verified and the block reading back carrying
    ``parent_id == <the cell id>``. Observed by a consumer on a disposable document.
    Any parent other than the root, a list item and a table cell stays
    **unmeasured, not refuted**. **Get the cell id from what ``apply()`` handed you, never by
    re-reading the document and taking the last table it finds**: an insert of a table reports
    one created id — the table's — and the cells are that block's own ``children``, row-major.
    Targeting by position puts pictures in the wrong table, and unlike a mis-placed paragraph
    the upload behind a mis-placed image is permanent whatever you do to the block (see
    **Residue** below).

    **These two ops are the only docx writes that position with a bare integer.** Everything
    else in this library positions with :class:`~larkdocio.write.model.Anchor` /
    :class:`~larkdocio.write.model.AnchorById` through the plan gate; this route is out of band
    and takes neither. The id to hold for a later anchored write is the ``block_id`` on the
    result.

    **``width`` / ``height`` DO NOT SURVIVE THE BIND, and passing them warns.** The create
    accepts them — the block really is created carrying them, and omitting them creates an
    empty image property, which is also a measured shape — and then step 3's
    ``replace_image`` **replaces the whole image property**, geometry included. Read the
    block back and it carries dimensions you did not choose. **Two observations, two
    different files, one conclusion:**

    * *consumer-observed on one day, four images* — authored ``width=560, height=560``,
      every one read back ``width: 2560, height: 2560, scale: 1``;
    * *captured, 2026-08-19, one image* — authored ``width=120, height=60``, read back
      ``width: 1, height: 1, scale: 1, align: 2`` — and the file uploaded was a **1x1** PNG
      (an unpublished recording).

    The numbers disagree because the **files** disagree; both are consistent with the bind
    writing the file's own pixel dimensions, and neither sample isolates that mechanism from
    any other rule, so this library claims only what both show: **the values you pass are not
    the values that come back**, and the property that comes back carries fields
    (``scale``, ``align``) nobody asked for. Nothing here re-sends geometry — the patch body
    is ``{"replace_image": {"token": …}}`` and carries none.

    **NO MEASURED ROUTE RESIZES THE BLOCK AFTERWARDS.** Three patch shapes were tried on
    this route on 2026-08-18 and all three were refused: ``{"replace_image": {"width": …,
    "height": …}}`` → **``99992402`` field validation failed**; ``{"update_image": {…}}`` →
    **``1770001`` invalid param**; a bare ``{"image": {…}}`` → **``1770001`` invalid param**.
    ``update_image_scale`` and ``update_block_property`` were tried and refused too. That is
    what **those spellings, on that route, on that date** answered — every other spelling is
    **unmeasured, not refuted**, and no resize op ships here.

    **THE ONE LEVER THAT WORKS: DOWNSCALE THE BYTES BEFORE YOU UPLOAD**, so the file's own
    pixel size *is* the display size. Decide it where you decide the file. Afterwards the
    only repair is to delete the block and author a smaller file — the block does delete
    (see above), but the re-upload mints a **second** permanent media token, so the bytes
    accumulate either way.

    **AND THE EXTENSION CAN LIE:** Lark exports a whiteboard as **JPEG bytes under a
    ``.png`` filename** (consumer-observed on one day, five exports), so a sizing step that
    dispatches on the filename skips exactly the images most likely to be oversized —
    dispatch on the bytes' own header instead. That is a warning about **your** sizing step:
    this library never inspects, decodes or re-encodes image bytes, so nothing here is
    affected by it.

    Alignment, scale and captions were never measured as create-time fields and are not
    offered.

    **Residue.** A successful call mints a **permanent** drive media token. **No route in
    Lark's open API purges drive media — measured, not assumed** (the nine spellings tried,
    the fourteen sends, and the scope the claim may not exceed are in
    :data:`larkdocio.base.media.NO_ROUTE_PURGES_DRIVE_MEDIA`), and **deleting the document
    does not remove it**. A failure *after* the block
    was created leaves that block behind: nothing here issues an unrequested delete, so the
    exception carries ``orphan_block_id`` and the caller decides.

    **THE BLOCK IS REMOVABLE; THE BYTES ARE NOT — two facts, and they are separate.** The
    image **block** this returns can be deleted through the ordinary plan gate: build a
    :class:`~larkdocio.write.model.DeleteRequest` targeting
    ``AnchorById(block_id=<the id this returned>)`` and apply it. **Measured 2026-08-19**:
    Lark's own child-delete route removes an image block and it stays removed — the parent no
    longer lists it and a direct read of the id answers *not found* — checked against a
    same-run control on a text block in the same parent. **Use the id, not a quote**: an image
    carries no quotable text of its own, so a quote anchor is refused with the id route named.
    What deleting the block does **not** do is reclaim the upload: the media token above stays,
    and putting the picture back somewhere else is a **new** upload and therefore a **second**
    permanent token. So plan a reorganisation of an image-carrying document knowing the blocks
    move for free and the bytes accumulate.

    **Rendering is unmeasured.** This returns when the block carries the bytes and the bytes
    round-trip; what a client draws is outside what any API call can observe.
    """
    if width is not None or height is not None:
        logging.getLogger("larkdocio").warning("%s", _GEOMETRY_DOES_NOT_SURVIVE)
    created = client.create_children(
        document_id,
        parent_block_id or document_id,
        [{"block_type": IMAGE_BLOCK_TYPE, "image": _image_property(width, height)}],
        index,
    )
    block_id = _created_image_block_id(created)

    try:
        uploaded = media.upload(
            data=data, name=name,
            parent_type=DOCX_IMAGE_PARENT_TYPE, parent_node=block_id,
        )
    except Exception as exc:  # the block exists; say so and let the refusal through intact
        exc.orphan_block_id = block_id
        raise

    try:
        client._patch_block(
            document_id, block_id, {REPLACE_IMAGE: {"token": uploaded.file_token}})
        _assert_bound(client, document_id, block_id, uploaded)
        verified = False
        if verify_bytes:
            verify_round_trip(uploaded, media.download(uploaded.file_token))
            verified = True
    except Exception as exc:
        exc.orphan_block_id = block_id
        exc.orphan_file_token = uploaded.file_token
        raise

    return AuthoredImage(
        document_id=document_id,
        block_id=block_id,
        file_token=uploaded.file_token,
        size=uploaded.size,
        sha256=uploaded.sha256,
        bytes_verified=verified,
    )


class DocxFileError(LarkAPIError):
    """An attachment-authoring failure. Its own family: a 📎 attachment card is a **different
    product** from an image and from an inline sentence link, and one taxonomy for all three
    would tell a caller the wrong thing about what they were making."""


class DocxFileCreateError(DocxFileError):
    """The create did not answer the wrapper-and-child shape this op knows how to bind to."""


class DocxFileBindError(DocxFileError):
    """The file block read back **without** the token that was uploaded to it.

    Carries the block id and the file token, so a caller can look at both.
    """

    def __init__(self, message, *, block_id, file_token, **kwargs):
        super().__init__(message, **kwargs)
        self.block_id = block_id
        self.file_token = file_token


@dataclass(frozen=True)
class AuthoredFile:
    """One file attached to a document as a 📎 **attachment card**.

    ``block_id`` is **the file block** — the type-23 child — because that is the id a caller
    must hold: it is what a later patch, delete or read has to address, and the id the create
    handed back (``wrapper_block_id``) is refused by the patch surface. Both are reported;
    neither is silently preferred.

    **This is not an inline sentence link.** It is an attachment BLOCK in the document body,
    which a client is expected to present as a 📎 card — expected, not measured: no API call
    can observe what a client draws. A
    caller who wants *"for the full details, **open the attached file**"* wants a file in a
    folder plus an anchored run, not this.

    Carries **no link of any kind**: a media read-back's link-bearing keys are short-lived
    signed links, treated as credential-class everywhere in this library.
    """

    document_id: str
    block_id: str
    wrapper_block_id: str
    file_token: str
    size: int
    sha256: str
    bytes_verified: bool


def put_file_in_document(
    *,
    client: WriteClient,
    media: DocxMediaClient,
    document_id: str,
    data: bytes,
    name: str,
    parent_block_id: Optional[str] = None,
    index: int = -1,
    verify_bytes: bool = True,
) -> AuthoredFile:
    """Attach a file to ``document_id`` as a 📎 attachment card, and return the FILE block id.

    **THIS IS THE FALLBACK, AND IT IS A DIFFERENT PRODUCT.** What it produces is an attachment
    card in the document body — not a link inside a sentence. Naming it honestly is the point:
    a caller who wants *"for the full details, **open the attached file**"* wants a file uploaded
    into a folder (:func:`larkdocio.drive.files_write.put_file_in_folder`) and an anchored run
    (:meth:`larkdocio.write.model.NewBlock.rich_paragraph`), and will not get it from here.

    **THE WRAPPER TRAP — the whole reason this is an op and not three exposed calls.** Creating
    ``{"block_type": 23, "file": {}}`` creates **two** blocks, and the id the create answers is
    a **view wrapper** (type 33) whose *child* is the real file block. Uploading against the
    wrapper, or patching it, is refused with a block/operation mismatch — an error a caller
    handed only the create's own ``block_id`` cannot decode. So this op resolves the child,
    **reads it back to confirm it really is a file block before any upload happens** (binding
    bytes to a block this library did not identify is how permanent residue gets attached to
    the wrong thing), uploads against the child, patches the child, and returns the child's id.

    **WHERE IT LANDS — ``parent_block_id`` + ``index``, MEASURED, with the wrapper's own
    twist.** ``parent_block_id`` names the block the attachment becomes a **child of** and
    defaults to the document's root (a docx document's root block id **is** its document id);
    ``index`` is a **0-based position in that parent's ordered ``children`` list, inserting
    BEFORE the child currently at that position**, and the default ``-1`` **appends**. The
    twist is the wrapper: **what lands at that position is the type-33 wrapper**, and the file
    block this function returns is the wrapper's child — one level deeper than the position you
    named. Measured on a disposable by
    ``tests/test_live_docx_media_placement_gate.py`` (**in the source repository**, not in the wheel): a
    non-root parent read back carrying the **wrapper** as its only child, the file block's ``parent_id`` being the wrapper, and the
    root's own child list unmoved). An ``index`` past the end, and parents other than the root
    and a list item, are **unmeasured, not refuted**.

    **This op and :func:`put_image_in_document` are the only docx writes that position with a
    bare integer** — everything else positions with :class:`~larkdocio.write.model.Anchor` /
    :class:`~larkdocio.write.model.AnchorById` through the plan gate. This route is out of band
    and takes neither.

    Two more measured facts, stated as measured rather than as guessed constraints: a create
    carrying a **name** in the file property is refused, and creating the **view wrapper
    directly** is refused. Neither is worked around here; the empty-property create is the
    shape that was measured to work, and the file's name comes from the upload.

    **The upload's own ``code:0`` is not a bind.** After a successful upload the block's
    ``file.token`` is still empty; only the patch binds it, and only a **fresh read of the
    block** proves it. That read-back is this op's verdict.

    **PERMANENT, UNPURGEABLE RESIDUE.** The bytes go to the drive **media** family, and **no
    route in Lark's open API purges drive media — measured, not assumed** (the nine spellings
    tried, the fourteen sends, and the scope the claim may not exceed are in
    :data:`larkdocio.base.media.NO_ROUTE_PURGES_DRIVE_MEDIA`): the token outlives the block,
    and deleting the document does not remove it. That is the opposite of a file uploaded into
    a folder, which *is* deletable — the two are different and the difference is why both are
    said.

    **Rendering is unmeasured.** No API call can observe what a client draws. What is proven
    here is that the block exists, carries the bytes, and hands them back byte-identical.
    """
    created = client.create_children(
        document_id,
        parent_block_id or document_id,
        [{"block_type": FILE_BLOCK_TYPE, "file": {}}],
        index,
    )
    wrapper_id, block_id = _created_file_block_ids(created)
    _assert_is_file_block(client, document_id, block_id, wrapper_id)

    try:
        uploaded = media.upload(
            data=data, name=name,
            parent_type=DOCX_FILE_PARENT_TYPE, parent_node=block_id,
        )
    except Exception as exc:  # the blocks exist; say so and let the refusal through intact
        exc.orphan_block_id = block_id
        exc.orphan_wrapper_block_id = wrapper_id
        raise

    try:
        client._patch_block(
            document_id, block_id, {REPLACE_FILE: {"token": uploaded.file_token}})
        _assert_bound(client, document_id, block_id, uploaded,
                      property_key="file", error_cls=DocxFileBindError)
        verified = False
        if verify_bytes:
            verify_round_trip(uploaded, media.download(uploaded.file_token))
            verified = True
    except Exception as exc:
        exc.orphan_block_id = block_id
        exc.orphan_wrapper_block_id = wrapper_id
        exc.orphan_file_token = uploaded.file_token
        raise

    return AuthoredFile(
        document_id=document_id,
        block_id=block_id,
        wrapper_block_id=wrapper_id,
        file_token=uploaded.file_token,
        size=uploaded.size,
        sha256=uploaded.sha256,
        bytes_verified=verified,
    )


def _created_file_block_ids(created) -> Tuple[str, str]:
    """``(wrapper_id, file_block_id)`` from a file create — checked, never assumed."""
    children = list((created or {}).get("children") or ())
    if not children:
        raise DocxFileCreateError(
            "the file-block create answered no children, so there is no block to bind bytes "
            "to. Nothing was uploaded")
    wrapper = children[0]
    block_type = wrapper.get("block_type")
    if block_type != FILE_VIEW_WRAPPER_BLOCK_TYPE:
        raise DocxFileCreateError(
            f"the file-block create answered a block of type {block_type!r}, not the view "
            f"wrapper {FILE_VIEW_WRAPPER_BLOCK_TYPE} this route was measured to answer. "
            f"Nothing was uploaded: the shape changed, and guessing which block to bind "
            f"bytes to is how permanent residue gets attached to the wrong thing")
    wrapper_id = wrapper.get("block_id")
    grandchildren = list(wrapper.get("children") or ())
    if not wrapper_id or not grandchildren:
        raise DocxFileCreateError(
            f"the file-block create answered a view wrapper with no child, so the file block "
            f"this library must bind bytes to does not exist. Nothing was uploaded. The "
            f"wrapper is {wrapper_id!r}")
    return wrapper_id, grandchildren[0]


def _assert_is_file_block(client, document_id, block_id, wrapper_id) -> None:
    """Refuse before any upload unless the resolved child really is a file block.

    One read, spent deliberately: an upload is permanent, unpurgeable residue, so identifying
    the target *first* is cheaper than any apology afterwards.
    """
    block = client.get_block(document_id, block_id) or {}
    if block.get("block_type") == FILE_BLOCK_TYPE:
        return
    raise DocxFileCreateError(
        f"the child {block_id!r} of the view wrapper {wrapper_id!r} reads back as block type "
        f"{block.get('block_type')!r}, not {FILE_BLOCK_TYPE}. Nothing was uploaded: bytes are "
        f"permanent residue and are not bound to a block this library did not identify")


def _image_property(width, height) -> dict:
    """The create-time ``image`` property: the measured fields, and only when given."""
    prop = {}
    if width is not None:
        prop["width"] = width
    if height is not None:
        prop["height"] = height
    return prop


def _created_image_block_id(created) -> str:
    """The id of the image block the create answered — checked, never assumed.

    A file-block create answers a **view wrapper** whose child is the real block; an image
    create was measured to answer the image block itself. If that ever stops being true, this
    says what came back instead of binding bytes to a block it did not identify.
    """
    children = list((created or {}).get("children") or ())
    if not children:
        raise DocxImageCreateError(
            "the image-block create answered no children, so there is no block to bind "
            "bytes to. Nothing was uploaded")
    child = children[0]
    block_type = child.get("block_type")
    if block_type != IMAGE_BLOCK_TYPE:
        raise DocxImageCreateError(
            f"the image-block create answered a block of type {block_type!r}, not "
            f"{IMAGE_BLOCK_TYPE}. Nothing was uploaded: binding bytes to a block this "
            f"library did not identify is how permanent residue gets attached to the wrong "
            f"thing")
    block_id = child.get("block_id")
    if not block_id:
        raise DocxImageCreateError(
            "the image-block create answered a block with no block_id, so there is nothing "
            "to upload against. Nothing was uploaded")
    return block_id


def _assert_bound(client, document_id, block_id, uploaded: UploadedMedia, *,
                  property_key: str = "image", error_cls=None) -> None:
    """Re-read the block and refuse unless it carries the token that was uploaded.

    One definition for both media kinds: the image and the attachment differ only in which
    property carries the token and which typed failure names the product. The *rule* — the
    verdict is a fresh read, never the patch's echo — is stated once.
    """
    error_cls = error_cls or DocxImageBindError
    block = client.get_block(document_id, block_id) or {}
    bound = ((block.get(property_key) or {}).get("token")) or ""
    if bound == uploaded.file_token:
        return
    detail = (f"carries {bound!r}" if bound
              else "is still EMPTY — which is what an upload alone leaves it as")
    raise error_cls(
        f"the {property_key} block {block_id!r} did not bind the uploaded file token: the block "
        f"{detail}, and the token uploaded to it was {uploaded.file_token!r}. The upload's "
        f"own success answer is not a bind, so this read-back is the verdict. The block and "
        f"the token both exist; the media token is permanent residue and no route in Lark's "
        f"open API purges drive media — measured, not assumed: the nine spellings tried, the "
        f"fourteen sends and the scope of that claim are in "
        f"larkdocio.base.media.NO_ROUTE_PURGES_DRIVE_MEDIA",
        block_id=block_id, file_token=uploaded.file_token)
