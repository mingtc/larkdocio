"""The docx IMAGE-authoring op — create the block, upload bound to it, bind with the PATCH.

Offline, over injected fakes: the three measured calls happen as a unit, in a fixed order,
and the **verdict is the read-back** rather than any call's own ``code:0``.

The tests that pin a **product contract or measured external truth** carry
``@pytest.mark.conformance`` (``process/doctrine/conformance-tier.md``): the fixed order, the
"an upload answering success is not a bind" contract, the hash-verified round trip, and the
agreement between the capability matrix and ``capabilities()``. Everything else is
regression-tier, unmarked.

**No refusal code Lark could renumber is asserted here.** The zero-byte arm drives the code
the shipped module already names as a constant, so the assertion is *"the shared refusal
fired"*, not *"the number is still 1061002"*.
"""
import inspect
import zlib

import pytest

from larkdocio.base.media import (
    EMPTY_UPLOAD_REFUSED_CODE,
    MediaRoundTripError,
    MediaUploadError,
    UploadedMedia,
    sha256_of,
)
from larkdocio.write import media as image_media
from larkdocio.write.media import (
    DOCX_IMAGE_PARENT_TYPE,
    IMAGE_BLOCK_TYPE,
    OUT_OF_BAND_CREATABLE_BLOCK_TYPES,
    AuthoredImage,
    DocxImageBindError,
    DocxImageCreateError,
    DocxMediaClient,
    put_image_in_document,
)

DOC = "doccnFakeDocumentId0000000"
BLOCK = "doxcnFakeImageBlockId0000"
TOKEN = "boxcnFakeFileToken0000000"


# --------------------------------------------------------------------------- #
# A tiny PNG, authored from source — never a committed binary blob.            #
# --------------------------------------------------------------------------- #

def png_bytes(rgb=(0, 0, 0)):
    """A 1x1 PNG, built here so the fixture is textual and regenerable.

    The spike uploaded a PNG and nothing else; this keeps the offline fixture the same
    media kind as the measured one rather than inventing a second claim.
    """
    def chunk(kind, payload):
        body = kind + payload
        return (len(payload).to_bytes(4, "big") + body
                + zlib.crc32(body).to_bytes(4, "big"))

    ihdr = (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + bytes((8, 2, 0, 0, 0))
    raw = bytes((0,)) + bytes(rgb)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


PNG = png_bytes()


# --------------------------------------------------------------------------- #
# The fakes. Every call is recorded in ORDER, because the order IS the contract. #
# --------------------------------------------------------------------------- #

class FakeWriteClient:
    def __init__(self, log, *, created_type=IMAGE_BLOCK_TYPE, read_back_token=TOKEN):
        self.log = log
        self._created_type = created_type
        self._read_back_token = read_back_token

    def create_children(self, document_id, block_id, children, index=-1):
        self.log.append(("create_children", document_id, block_id, children, index))
        return {"children": [{"block_id": BLOCK, "block_type": self._created_type,
                              "image": {"token": ""}}]}

    def _patch_block(self, document_id, block_id, update):
        self.log.append(("_patch_block", document_id, block_id, update))
        return {"block": {"block_id": block_id}}

    def get_block(self, document_id, block_id):
        self.log.append(("get_block", document_id, block_id))
        return {"block_id": block_id, "block_type": IMAGE_BLOCK_TYPE,
                "image": {"token": self._read_back_token}}


class FakeMediaClient:
    def __init__(self, log, *, upload_error=None, downloaded=None):
        self.log = log
        self._upload_error = upload_error
        self._downloaded = downloaded

    def upload(self, *, data, name, parent_type, parent_node):
        self.log.append(("upload", name, parent_type, parent_node, len(data)))
        if self._upload_error is not None:
            raise self._upload_error
        return UploadedMedia(file_token=TOKEN, parent_type=parent_type,
                             parent_node=parent_node, size=len(data),
                             sha256=sha256_of(data))

    def download(self, file_token):
        self.log.append(("download", file_token))
        return PNG if self._downloaded is None else self._downloaded


def run(log=None, *, data=PNG, **kwargs):
    """Drive the op over the fakes; returns ``(result, call log)``."""
    log = [] if log is None else log
    client_kwargs = {k: kwargs.pop(k) for k in ("created_type", "read_back_token")
                     if k in kwargs}
    media_kwargs = {k: kwargs.pop(k) for k in ("upload_error", "downloaded")
                    if k in kwargs}
    result = put_image_in_document(
        client=FakeWriteClient(log, **client_kwargs),
        media=FakeMediaClient(log, **media_kwargs),
        document_id=DOC, data=data, name="diagram.png", **kwargs)
    return result, log


def calls(log):
    return [entry[0] for entry in log]


def source():
    return inspect.getsource(image_media)


# --------------------------------------------------------------------------- #
# AC1 — ONE op, returning BOTH handles.                                        #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_ac1_one_op_returns_both_the_block_id_and_the_file_token():
    """A caller needs the block id to position or delete the image, and the token to prove
    what landed — so the op returns both, plus the digest it verified them with."""
    result, _log = run()
    assert isinstance(result, AuthoredImage)
    assert result.block_id == BLOCK
    assert result.file_token == TOKEN
    assert result.document_id == DOC
    assert result.size == len(PNG)
    assert result.sha256 == sha256_of(PNG)
    assert result.bytes_verified is True


@pytest.mark.conformance
def test_ac1_the_create_payload_is_the_measured_shape():
    """``{"block_type": 27, "image": {width, height}}`` — the measured create fields, and
    only those two."""
    _result, log = run(width=24, height=24)
    _name, document_id, parent, children, index = log[0]
    assert document_id == DOC and parent == DOC and index == -1
    assert children == [{"block_type": IMAGE_BLOCK_TYPE,
                         "image": {"width": 24, "height": 24}}]


def test_ac1_an_unmeasured_create_time_field_is_not_offered():
    """``align`` / ``scale`` / a caption were never measured, so the signature has no way to
    send one — an unmeasured field is absent, not defaulted."""
    parameters = inspect.signature(put_image_in_document).parameters
    for unmeasured in ("align", "scale", "caption", "block_type", "token", "file_token"):
        assert unmeasured not in parameters, parameters


def test_ac1_the_create_payload_omits_geometry_that_was_not_given():
    """All three probed create shapes routed, including the empty one, so an omitted
    dimension is omitted rather than guessed at."""
    _result, log = run()
    assert log[0][3] == [{"block_type": IMAGE_BLOCK_TYPE, "image": {}}]


def test_ac1_the_op_creates_under_an_explicit_parent_at_an_explicit_index():
    _result, log = run(parent_block_id="doxcnSomeParent", index=3)
    assert log[0][2] == "doxcnSomeParent" and log[0][4] == 3


def test_ac1_a_create_that_answers_a_different_block_type_is_refused_not_guessed():
    """The file-block route answers a wrapper whose CHILD is the real block; the image route
    was measured to answer the image block itself. If that ever stops being true the op says
    what came back instead of binding bytes to a block it did not identify."""
    with pytest.raises(DocxImageCreateError) as exc:
        run(created_type=33)
    assert "33" in str(exc.value) and str(IMAGE_BLOCK_TYPE) in str(exc.value)


# --------------------------------------------------------------------------- #
# AC2 — the ORDER is enforced and disclosed, and the BIND is the PATCH.        #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_ac2_the_calls_happen_in_the_measured_order():
    _result, log = run()
    assert calls(log) == ["create_children", "upload", "_patch_block", "get_block",
                          "download"]


@pytest.mark.conformance
def test_ac2_the_upload_is_bound_to_the_created_block_never_to_the_document():
    """The measured trap: an upload parented on the DOCUMENT succeeds and yields a token,
    and then no block will accept it (a relation mismatch at bind time). The op never has a
    chance to make that mistake — the parent it uploads against is the block it just
    created."""
    _result, log = run()
    _name, _fname, parent_type, parent_node, _size = log[1]
    assert parent_type == DOCX_IMAGE_PARENT_TYPE
    assert parent_node == BLOCK
    assert parent_node != DOC


def test_ac2_the_op_takes_no_pre_made_block_or_token():
    """The order cannot be driven wrong because there is no way to hand the op a block id it
    did not create, or a token it did not upload."""
    parameters = set(inspect.signature(put_image_in_document).parameters)
    assert not parameters & {"block_id", "image_block_id", "file_token", "token"}


@pytest.mark.conformance
def test_ac2_an_upload_answering_success_is_not_a_bind_the_read_back_is_the_verdict():
    """The upload answers success and leaves the block's token EMPTY until the patch binds
    it. If the read-back still shows an empty token, the op refuses rather than reporting a
    success it did not observe."""
    with pytest.raises(DocxImageBindError) as exc:
        run(read_back_token="")
    message = str(exc.value)
    assert BLOCK in message and TOKEN in message
    assert exc.value.block_id == BLOCK and exc.value.file_token == TOKEN


def test_ac2_a_read_back_naming_another_token_is_refused():
    with pytest.raises(DocxImageBindError):
        run(read_back_token="boxcnSomeOtherTokenEntirely")


def test_ac2_the_patch_body_is_the_replace_image_oneof():
    _result, log = run()
    assert log[2][3] == {"replace_image": {"token": TOKEN}}


def test_ac2_both_traps_are_disclosed_in_the_docstring():
    """A caller who reimplements this from the vendor's documentation hits both, so both are
    shipped as facts rather than left in a findings file."""
    doc = put_image_in_document.__doc__.lower()
    assert "before the upload" in doc or "must exist first" in doc
    assert "is not a bind" in doc
    assert "read-back" in doc


# --------------------------------------------------------------------------- #
# AC3 — the zero-byte refusal is the one that already exists.                  #
# --------------------------------------------------------------------------- #

def test_ac3_a_zero_byte_upload_is_refused_by_the_shared_refusal():
    """The refusal is the media leg's own, unwrapped and unrestated: the op does not mint a
    second definition of what an empty upload means."""
    refusal = MediaUploadError("this file is EMPTY, and an empty upload is refused",
                               code=EMPTY_UPLOAD_REFUSED_CODE)
    with pytest.raises(MediaUploadError) as exc:
        run(data=b"", upload_error=refusal)
    assert exc.value is refusal


def test_ac3_the_empty_upload_refusal_is_defined_in_exactly_one_place():
    """Grep-level, because the way a second definition arrives is by looking reasonable."""
    text = source()
    assert "EMPTY_UPLOAD_REFUSED_CODE" not in text
    assert "1061002" not in text


def test_ac3_a_failure_after_the_create_names_the_block_it_left_behind():
    """Nothing is auto-deleted — a failed authoring does not issue an unrequested delete —
    so the block id rides out on the exception for the caller who wants to clean up."""
    refusal = MediaUploadError("refused", code=EMPTY_UPLOAD_REFUSED_CODE)
    with pytest.raises(MediaUploadError) as exc:
        run(data=b"", upload_error=refusal)
    assert getattr(exc.value, "orphan_block_id", None) == BLOCK


# --------------------------------------------------------------------------- #
# AC4 — the round trip is HASH-verified, by REUSING verify_round_trip.         #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_ac4_the_round_trip_is_hash_verified():
    result, log = run()
    assert ("download", TOKEN) in log
    assert result.sha256 == sha256_of(PNG)
    assert result.bytes_verified is True


@pytest.mark.conformance
def test_ac4_bytes_that_come_back_different_raise_the_shared_round_trip_error():
    with pytest.raises(MediaRoundTripError):
        run(downloaded=png_bytes((255, 0, 0)))


def test_ac4_the_hash_check_is_the_shared_one_not_a_second_definition():
    text = source()
    assert "verify_round_trip" in text
    assert "hashlib" not in text and "sha256(" not in text


def test_ac4_the_byte_verification_can_be_declined_and_says_so_in_the_result():
    result, log = run(verify_bytes=False)
    assert "download" not in calls(log)
    assert result.bytes_verified is False
    assert result.sha256 == sha256_of(PNG)  # still the digest of what was SENT


def test_ac4_no_payload_is_ever_read_or_rendered():
    """Bytes are hashed, never inspected — the standing rule for a binary artifact here."""
    text = source()
    for forbidden in ("print(", ".decode(", "b64encode", "repr(data)"):
        assert forbidden not in text, forbidden


# --------------------------------------------------------------------------- #
# The parent-type vocabulary, and the measured swallow.                        #
# --------------------------------------------------------------------------- #

def test_the_docx_media_client_accepts_only_the_measured_parent_types():
    """SUPERSEDED IN PART: the REASON is unchanged — an upload is permanent residue, so this
    leg sends only spellings that were MEASURED, and everything else is refused locally
    before any call. What moved is the membership: the docx **file** parent type was measured
    too and joined the set. The invariant the guard exists for is that the set is exactly the
    measured spellings, so it is asserted that way rather than deleted."""
    from larkdocio.write.media import DOCX_FILE_PARENT_TYPE

    assert DocxMediaClient.ALLOWED_PARENT_TYPES == (
        DOCX_IMAGE_PARENT_TYPE, DOCX_FILE_PARENT_TYPE)


def test_an_unmeasured_parent_type_spelling_is_refused_before_any_call():
    client = DocxMediaClient("id", "secret", sdk_client=object())
    with pytest.raises(MediaUploadError) as exc:
        client.upload(data=PNG, name="x.png", parent_type="sheet_image",
                      parent_node=BLOCK)
    assert DOCX_IMAGE_PARENT_TYPE in str(exc.value)


def test_ac11_the_measured_swallow_is_stated_where_it_matters():
    """The upload endpoint does not police the type/parent pairing — it accepted the image
    parent type against a FILE block. The bind is what enforces the relation."""
    text = source().lower()
    assert "does not police" in text
    assert "the bind" in text


def test_ac11_the_negative_claims_name_their_unmeasured_forms():
    text = source().lower()
    for enumeration in ("png", "unmeasured", "tenant_access_token", "user_access_token",
                        "wiki"):
        assert enumeration in text, enumeration


def test_ac9_the_permanent_residue_is_disclosed_with_the_op():
    """An uploaded token is permanent, unpurgeable residue: no verb purges drive media, and
    deleting the document does not remove what it carried."""
    doc = (put_image_in_document.__doc__ + source()).lower()
    assert "residue" in doc
    assert "permanent" in doc
    assert "deleting the document" in doc


@pytest.mark.conformance
def test_ac10_the_rendering_claim_is_fenced_to_the_evidence():
    """No call can prove a client renders the bound image. What the module may claim is what
    was measured — created, bound, byte-identical — with the rendering axis labelled."""
    text = source()
    assert "unmeasured" in text.lower()
    lowered = text.lower()
    for overclaim in ("it renders", "renders in the document", "will render",
                      "renders the image"):
        assert overclaim not in lowered, overclaim


# --------------------------------------------------------------------------- #
# The out-of-band creatable set — the join key the matrix and capabilities use. #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_the_out_of_band_creatable_set_carries_the_image_block_type():
    """SUPERSEDED IN PART: the REASON is unchanged — this tuple is the join key the block
    matrix and ``capabilities()`` are both pinned against, so it must say exactly what the
    shipped media ops create. What moved is the membership: the 📎 file attachment joined it
    when its op shipped. The image's own membership is still asserted here."""
    from larkdocio.write.media import FILE_BLOCK_TYPE

    assert OUT_OF_BAND_CREATABLE_BLOCK_TYPES == (IMAGE_BLOCK_TYPE, FILE_BLOCK_TYPE)
    assert IMAGE_BLOCK_TYPE == 27
