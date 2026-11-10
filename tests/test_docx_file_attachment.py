"""LD-434 — the 📎 attachment block (docx type 23) and its WRAPPER TRAP, offline.

The create answers a **type-33 view wrapper** whose child is the real file block
(``dev/media-spike/captures/321-`` / ``322-``, in the dev repo). Uploading against or
patching the wrapper is refused, so a caller handed the create's own ``block_id`` meets an
error they cannot decode. These tests pin the op that resolves the child instead.

**No bytes are inspected** — payloads are made in-process, compared by ``sha256``, discarded.

Conformance-tier: the wrapper trap and the read-back-is-the-verdict rule are **measured
external truth** (``process/doctrine/conformance-tier.md`` § A.4).
"""
import pathlib

import pytest

from larkdocio.base.media import sha256_of
from larkdocio.write.media import (
    DOCX_FILE_PARENT_TYPE,
    FILE_BLOCK_TYPE,
    FILE_VIEW_WRAPPER_BLOCK_TYPE,
    OUT_OF_BAND_CREATABLE_BLOCK_TYPES,
    REPLACE_FILE,
    AuthoredFile,
    DocxFileBindError,
    DocxFileCreateError,
    DocxMediaClient,
    put_file_in_document,
)

pytestmark = pytest.mark.conformance

REPO = pathlib.Path(__file__).resolve().parent.parent
DOC = "Examplef0c204c531d285ebd8df"
WRAPPER = "doxlgExampledb7d2f3cc66b504"
CHILD = "doxlgExamplec0ada3626749f62"
PAYLOAD = b"<!doctype html><title>an attached file</title>"


class _FakeWriter:
    """The docx write seam, answering the shape capture 321- recorded."""

    def __init__(self, *, wrapper_type=FILE_VIEW_WRAPPER_BLOCK_TYPE,
                 child_type=FILE_BLOCK_TYPE, children=(CHILD,), bind=True):
        self.calls = []
        self._wrapper_type, self._child_type = wrapper_type, child_type
        self._children, self._bind = tuple(children), bind
        self._bound = ""

    def create_children(self, document_id, block_id, children, index):
        self.calls.append(("create_children", document_id, block_id, children, index))
        return {"children": [{"block_id": WRAPPER, "block_type": self._wrapper_type,
                              "children": list(self._children),
                              "parent_id": document_id}]}

    def get_block(self, document_id, block_id):
        self.calls.append(("get_block", document_id, block_id))
        return {"block_id": block_id, "block_type": self._child_type,
                "file": {"name": "", "token": self._bound}}

    def _patch_block(self, document_id, block_id, update):
        self.calls.append(("_patch_block", document_id, block_id, update))
        if self._bind:
            self._bound = update[REPLACE_FILE]["token"]
        return {"code": 0}


class _FakeMedia:
    def __init__(self):
        self.uploads, self.store = [], {}

    def upload(self, *, data, name, parent_type, parent_node):
        self.uploads.append((name, parent_type, parent_node))
        from larkdocio.base.media import UploadedMedia
        token = "boxExample01"
        self.store[token] = data
        return UploadedMedia(file_token=token, parent_type=parent_type,
                             parent_node=parent_node, size=len(data),
                             sha256=sha256_of(data))

    def download(self, file_token):
        return self.store[file_token]


def attach(writer=None, media=None, **kw):
    return put_file_in_document(
        client=writer or _FakeWriter(), media=media or _FakeMedia(),
        document_id=DOC, data=PAYLOAD, name="ld434.html", **kw)


# --------------------------------------------------------------------------- #
# AC9 — the wrapper trap is HANDLED, not documented-around.                    #
# --------------------------------------------------------------------------- #

def test_the_create_sends_the_measured_empty_property_shape():
    writer = _FakeWriter()
    attach(writer)
    (_, doc, parent, payload, index), = [
        c for c in writer.calls if c[0] == "create_children"]
    assert payload == [{"block_type": FILE_BLOCK_TYPE, "file": {}}]
    assert doc == parent == DOC
    assert index == -1


def test_the_upload_is_bound_to_the_CHILD_not_to_the_wrapper():
    media = _FakeMedia()
    attach(media=media)
    assert media.uploads == [("ld434.html", DOCX_FILE_PARENT_TYPE, CHILD)]


def test_the_patch_addresses_the_CHILD_and_uses_replace_file():
    writer = _FakeWriter()
    attach(writer)
    (_, _, block_id, body), = [c for c in writer.calls if c[0] == "_patch_block"]
    assert block_id == CHILD
    assert set(body) == {REPLACE_FILE}


def test_the_op_returns_the_CHILD_id_because_that_is_what_a_caller_must_hold():
    authored = attach()
    assert isinstance(authored, AuthoredFile)
    assert authored.block_id == CHILD
    assert authored.wrapper_block_id == WRAPPER
    assert authored.bytes_verified is True
    assert authored.sha256 == sha256_of(PAYLOAD)


def test_the_child_is_IDENTIFIED_BEFORE_any_upload_happens():
    writer, media = _FakeWriter(child_type=2), _FakeMedia()
    with pytest.raises(DocxFileCreateError, match="not 23"):
        attach(writer, media)
    assert media.uploads == []


def test_a_create_that_stops_answering_the_wrapper_refuses_rather_than_guessing():
    writer, media = _FakeWriter(wrapper_type=FILE_BLOCK_TYPE), _FakeMedia()
    with pytest.raises(DocxFileCreateError, match="view wrapper"):
        attach(writer, media)
    assert media.uploads == []


def test_a_wrapper_with_no_child_refuses_and_uploads_nothing():
    writer, media = _FakeWriter(children=()), _FakeMedia()
    with pytest.raises(DocxFileCreateError, match="no child"):
        attach(writer, media)
    assert media.uploads == []


def test_the_verdict_is_the_READ_BACK_not_the_patch_echo():
    writer = _FakeWriter(bind=False)
    with pytest.raises(DocxFileBindError) as exc:
        attach(writer)
    assert exc.value.block_id == CHILD
    assert "still EMPTY" in str(exc.value)
    assert exc.value.orphan_file_token == "boxExample01"
    assert exc.value.orphan_wrapper_block_id == WRAPPER


# --------------------------------------------------------------------------- #
# AC10 — it is named for what it IS: a different product.                      #
# --------------------------------------------------------------------------- #

def test_the_op_says_plainly_it_is_not_an_inline_sentence_link():
    text = put_file_in_document.__doc__ + AuthoredFile.__doc__
    assert "attachment card" in text
    assert "not a link inside a sentence" in text or "not an inline sentence link" in text
    assert "rich_paragraph" in text


def test_the_upload_client_accepts_BOTH_measured_parent_spellings_and_nothing_else():
    assert DOCX_FILE_PARENT_TYPE in DocxMediaClient.ALLOWED_PARENT_TYPES
    assert len(DocxMediaClient.ALLOWED_PARENT_TYPES) == 2


# --------------------------------------------------------------------------- #
# AC11 — the out-of-band creatable set moved with the code.                    #
# --------------------------------------------------------------------------- #

def test_the_out_of_band_creatable_set_now_carries_the_file_block():
    assert FILE_BLOCK_TYPE in OUT_OF_BAND_CREATABLE_BLOCK_TYPES


def test_the_wrapper_type_is_NOT_claimed_creatable():
    assert FILE_VIEW_WRAPPER_BLOCK_TYPE not in OUT_OF_BAND_CREATABLE_BLOCK_TYPES


# --------------------------------------------------------------------------- #
# The residue disclosure stays attached to the media route.                    #
# --------------------------------------------------------------------------- #

def test_the_attachment_op_states_the_media_residue_and_its_CONTRAST():
    doc = put_file_in_document.__doc__
    assert "purges drive media" in doc
    assert "deletable" in doc or "is* deletable" in doc
