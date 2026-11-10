"""LD-434 — the folder-upload slice: upload a file, get its permalink, verify by hash.

Offline, against a fake SDK seam. Every request shape pinned here comes from a capture in the
media spike (``dev/media-spike/captures/203-`` … ``207-``, in the dev repo); nothing is
hand-mocked from documentation.

**No bytes are inspected anywhere in this file** — the payloads are made in-process, compared
by ``sha256`` and thrown away.

Conformance-tier: the request shapes, the permalink-not-signed classification and the
caller-supplied-destination fence are **product contract / measured external truth**
(``process/doctrine/conformance-tier.md`` § A.4).
"""
import io
import pathlib

import pytest

from larkdocio.base.media import EMPTY_UPLOAD_ADVICE, EMPTY_UPLOAD_REFUSED_CODE, sha256_of
from larkdocio.drive import files_write as fw
from larkdocio.drive.files_write import (
    URL_CLASS,
    DriveFileDeleteError,
    DriveFileMetaError,
    DriveFileUploadError,
    DriveFilesWriteClient,
    put_file_in_folder,
)

pytestmark = pytest.mark.conformance

REPO = pathlib.Path(__file__).resolve().parent.parent
FOLDER = "Example9e2799ef0b30cb6f27c3"
PERMALINK = "https://your-domain.larksuite.com/file/Examplee188933a13fa6792c0c7"
PAYLOAD = b"<!doctype html><title>an attached file</title><p>hello"


class _Resp:
    def __init__(self, code=0, data=None, file=None, msg="Success"):
        self.code, self.data, self.file, self.msg = code, data, file, msg


class _UploadData:
    def __init__(self, file_token, url):
        self.file_token = file_token
        #: the upload's OWN answer carries a short-lived signed link. It is here in the fake
        #: precisely so a test can prove the library never reads it.
        self.url = url


class _Meta:
    def __init__(self, url):
        self.url = url


class _MetasData:
    def __init__(self, metas):
        self.metas = metas


class _FakeFile:
    def __init__(self, outer):
        self._outer = outer

    def upload_all(self, request):
        self._outer.calls.append(("upload_all", request))
        if self._outer.upload_code:
            return _Resp(code=self._outer.upload_code, msg="upload refused")
        body = request.request_body
        self._outer.store["boxcn0001"] = body.file.read()
        return _Resp(data=_UploadData("boxcn0001", "https://signed.example/tmp?sig=SECRET"))

    def download(self, request):
        self._outer.calls.append(("download", request))
        if self._outer.download_code:
            return _Resp(code=self._outer.download_code, msg="download refused")
        return _Resp(file=io.BytesIO(self._outer.store[request.file_token]))

    def delete(self, request):
        self._outer.calls.append(("delete", request))
        if self._outer.delete_code:
            return _Resp(code=self._outer.delete_code, msg="delete refused")
        self._outer.store.pop(request.file_token, None)
        return _Resp()


class _FakeMeta:
    def __init__(self, outer):
        self._outer = outer

    def batch_query(self, request):
        self._outer.calls.append(("batch_query", request))
        if self._outer.meta_code:
            return _Resp(code=self._outer.meta_code, msg="meta refused")
        return _Resp(data=_MetasData([_Meta(self._outer.url)]))


class _FakeSDK:
    def __init__(self, *, upload_code=0, download_code=0, delete_code=0, meta_code=0,
                 url=PERMALINK):
        self.calls, self.store = [], {}
        self.upload_code, self.download_code = upload_code, download_code
        self.delete_code, self.meta_code, self.url = delete_code, meta_code, url
        v1 = type("_V1", (), {"file": _FakeFile(self), "meta": _FakeMeta(self)})()
        self.drive = type("_Drive", (), {"v1": v1})()


def client(**kw):
    return DriveFilesWriteClient("id", "secret", sdk_client=_FakeSDK(**kw),
                                 rate_limiter=_NoWait())


class _NoWait:
    def acquire(self):
        return None


# --------------------------------------------------------------------------- #
# AC1 — the upload, into a folder the CALLER named.                            #
# --------------------------------------------------------------------------- #

def test_the_upload_sends_the_measured_request_shape():
    c = client()
    uploaded = c.upload(data=PAYLOAD, name="ld434.html", folder_token=FOLDER)
    (_, request), = [c for c in c._sdk.calls if c[0] == "upload_all"]
    body = request.request_body
    assert body.parent_type == "explorer"
    assert body.parent_node == FOLDER
    assert body.file_name == "ld434.html"
    assert body.size == len(PAYLOAD)
    assert uploaded.sha256 == sha256_of(PAYLOAD)
    assert uploaded.folder_token == FOLDER


def test_a_MISSING_folder_token_is_refused_locally_with_no_call_at_all():
    c = client()
    with pytest.raises(DriveFileUploadError) as exc:
        c.upload(data=PAYLOAD, name="x.html", folder_token="")
    assert c._sdk.calls == []
    assert "no default destination" in str(exc.value)
    assert "creates no folder" in str(exc.value)


def test_an_unmeasured_parent_type_is_refused_locally_and_named_unmeasured():
    c = client()
    with pytest.raises(DriveFileUploadError) as exc:
        c.upload(data=PAYLOAD, name="x.html", folder_token=FOLDER,
                 parent_type="explorer-banana")
    assert c._sdk.calls == []
    assert "unmeasured rather than refused" in str(exc.value)


def test_a_zero_byte_upload_REUSES_the_existing_refusal_rather_than_restating_it():
    c = client(upload_code=EMPTY_UPLOAD_REFUSED_CODE)
    with pytest.raises(DriveFileUploadError) as exc:
        c.upload(data=b"", name="empty.html", folder_token=FOLDER)
    assert EMPTY_UPLOAD_ADVICE in str(exc.value)
    # the call IS still sent: the finding is the server's.
    assert [name for name, _ in c._sdk.calls] == ["upload_all"]


# --------------------------------------------------------------------------- #
# AC2 — the URL is a PERMALINK, and no signed link is ever read or kept.       #
# --------------------------------------------------------------------------- #

def test_the_permalink_is_ASKED_FOR_with_the_measured_body():
    c = client()
    assert c.permalink("boxcn0001") == PERMALINK
    (_, request), = [call for call in c._sdk.calls if call[0] == "batch_query"]
    body = request.request_body
    assert body.with_url is True
    assert [(d.doc_token, d.doc_type) for d in body.request_docs] == [("boxcn0001", "file")]


def test_the_uploaded_value_carries_NO_url_so_a_signed_link_cannot_hide_in_it():
    c = client()
    uploaded = c.upload(data=PAYLOAD, name="x.html", folder_token=FOLDER)
    assert not [f for f in vars(uploaded) if "url" in f.lower() and f != "url_class"]


def test_the_result_classifies_its_url_as_a_permalink():
    linked = put_file_in_folder(files=client(), data=PAYLOAD, name="x.html",
                                folder_token=FOLDER)
    assert linked.url == PERMALINK
    assert linked.url_class == URL_CLASS == "permalink"


def test_no_url_is_ever_CONSTRUCTED_from_a_token():
    c = client(url=None)
    with pytest.raises(DriveFileMetaError) as exc:
        c.permalink("boxcn0001")
    assert "never constructed" in str(exc.value)


def test_the_shipped_module_uses_no_signed_link_LIFETIME_language():
    """AC2's own words: a permalink and a signed temporary link are different products."""
    source = (REPO / "src" / "larkdocio" / "drive" / "files_write.py").read_text("utf-8")
    # the module may (and must) say what a signed link IS; what it may not do is describe
    # the permalink with that lifetime language.
    for sentence in source.split("."):
        if "permalink" in sentence.lower():
            assert "expires" not in sentence.lower(), sentence
            assert "temporary" not in sentence.lower(), sentence


# --------------------------------------------------------------------------- #
# AC3 — the hash-verified round trip, reusing verify_round_trip.               #
# --------------------------------------------------------------------------- #

def test_the_op_hash_verifies_the_round_trip_by_reusing_the_shipped_check():
    linked = put_file_in_folder(files=client(), data=PAYLOAD, name="x.html",
                                folder_token=FOLDER)
    assert linked.bytes_verified is True
    assert linked.sha256 == sha256_of(PAYLOAD)
    assert linked.size == len(PAYLOAD)


def test_the_op_reuses_verify_round_trip_rather_than_comparing_bytes_itself():
    source = (REPO / "src" / "larkdocio" / "drive" / "files_write.py").read_text("utf-8")
    assert "verify_round_trip(" in source
    assert "==" not in source.split("def put_file_in_folder")[1].split("def ")[0]


def test_a_failure_after_the_upload_names_the_ORPHAN_rather_than_deleting_it():
    c = client(meta_code=1061003)
    with pytest.raises(DriveFileMetaError) as exc:
        put_file_in_folder(files=c, data=PAYLOAD, name="x.html", folder_token=FOLDER)
    assert exc.value.orphan_file_token == "boxcn0001"
    assert "delete" not in [name for name, _ in c._sdk.calls]


# --------------------------------------------------------------------------- #
# AC14 — the residue disclosure: a FILE can be deleted; media cannot.          #
# --------------------------------------------------------------------------- #

def test_a_file_object_can_be_deleted_and_the_delete_says_nothing_about_being_gone():
    c = client()
    c.upload(data=PAYLOAD, name="x.html", folder_token=FOLDER)
    assert c.delete("boxcn0001") is None
    (_, request), = [call for call in c._sdk.calls if call[0] == "delete"]
    assert request.file_token == "boxcn0001"
    assert request.type == "file"


def test_a_refused_delete_reports_that_NOTHING_WAS_REMOVED():
    """**TRANSFORMED, not deleted.** This test used to require the refusal to say *"The file is
    still there"*, and the reason it was written is unchanged and still binds: a refused delete
    must not let a caller believe the object went away. What is superseded is only the
    conclusion — *nothing was removed* does not license *it is still there*, and on the one code
    that has a measured reading the old sentence said the opposite of the truth (Lark's own
    answer is that the file has already been deleted). So the refusal now reports what it
    established and refuses to read itself as a verdict about the object. The already-deleted
    half is pinned in ``tests/test_drive_upload_identity.py``."""
    c = client(delete_code=1061003)
    with pytest.raises(DriveFileDeleteError, match="Nothing was reported as removed"):
        c.delete("boxcn0001")


def test_the_module_states_BOTH_halves_of_the_residue_difference():
    source = (REPO / "src" / "larkdocio" / "drive" / "files_write.py").read_text("utf-8")
    assert "unpurgeable" in source
    assert "Trash, not purge" in source or "trash; *trash is not purge*" in source


# --------------------------------------------------------------------------- #
# AC15 — the negative claims are enumerated, and the swallow is stated.        #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("word", [
    "chunked upload", "user_access_token", "other tenants", "unmeasured, not refuted",
])
def test_the_untried_forms_are_named_as_UNMEASURED(word):
    source = (REPO / "src" / "larkdocio" / "drive" / "files_write.py").read_text("utf-8")
    assert word in source


def test_the_measured_swallow_is_stated():
    source = (REPO / "src" / "larkdocio" / "drive" / "files_write.py").read_text("utf-8")
    assert "does\n**not** police" in source or "not**\npolice" in source or (
        "police the ``parent_type`` / ``parent_node`` pairing" in source)


def test_the_folder_CREATE_lives_in_EXACTLY_ONE_module_and_this_one_still_does_not_call_it():
    """**TRANSFORMED, NOT DELETED (LD-467, D-24).** This asserted that no folder-creating call
    site existed anywhere in the shipped tree, and the reason it was written is unchanged: a
    module that puts a file in a folder must not quietly start making folders, and an
    organize-rung fence should be mechanical rather than a promise in prose.

    What is superseded is only the *nowhere* half of the conclusion — a product ruling of
    2026-08-14 opened one create verb. So the fence is re-scoped rather than dropped: the call
    site may exist in **exactly one** module (plus the endpoint constant's home and the
    permission table that must declare it), THIS module still may not call it, and any new
    file appearing in that set reddens here the same day.
    """
    allowed = {
        "src/larkdocio/drive/folders_write.py",   # the one verb the ruling opened
        "src/larkdocio/drive/ops.py",             # where a Drive endpoint is NAMED
        "src/larkdocio/permissions.py",           # where its scope requirement is authored
        # The caller-supplied-destination rule NAMES the verb in the sentence that tells a
        # refused caller how to get a folder token. It calls nothing: the mention is the
        # actionable half of a refusal, which is why this module is a text-only hit.
        "src/larkdocio/common/destination.py",
    }
    hits = set()
    for path in (REPO / "src" / "larkdocio").rglob("*.py"):
        source = path.read_text("utf-8")
        if "create_folder(" in source or "files/create_folder" in source:
            hits.add(str(path.relative_to(REPO)))
    assert hits == allowed, hits
    assert "create_folder(" not in (REPO / "src/larkdocio/drive/files_write.py").read_text(
        "utf-8"), "the upload module started creating folders"


# --------------------------------------------------------------------------- #
# The endpoint constants ARE the SDK's own paths (the permission derivation).  #
# --------------------------------------------------------------------------- #

def test_every_endpoint_constant_matches_the_pinned_sdk_request_class():
    from lark_oapi.api.drive.v1 import (
        BatchQueryMetaRequest,
        DeleteFileRequest,
        DownloadFileRequest,
        UploadAllFileRequest,
    )
    assert UploadAllFileRequest.builder().build().uri == fw.FILES_UPLOAD_ALL_ENDPOINT
    assert DownloadFileRequest.builder().build().uri == fw.FILE_DOWNLOAD_ENDPOINT
    assert DeleteFileRequest.builder().build().uri == fw.FILE_DELETE_ENDPOINT
    assert BatchQueryMetaRequest.builder().build().uri == fw.METAS_BATCH_QUERY_ENDPOINT
