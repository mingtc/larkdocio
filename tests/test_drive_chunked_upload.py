"""LD-449 — the CHUNKED half of the upload rung: prepare → part(s) → finish, hash-verified.

Offline, against a fake SDK seam whose answers are **deserialized from the committed spike
captures** (``tests/captures/drive-media-remainder-spike/captures/703-`` … ``707-``, in the dev repo)
through the pinned SDK's own body classes. Nothing here is hand-mocked from documentation.

**The two things this file exists to hold, because they are the two habits the measurement
forbids:**

1. **the cut-over is SERVER-DECLARED.** ``upload_prepare`` answers ``block_size`` and
   ``block_num``; the client partitions by that answer and by nothing else. The captured answer
   was ``4194304`` on one tenant on one day, so a client carrying that number as a decision
   threshold would be a latent bug the day the server answers differently — the tests below
   drive a **deliberately unfamiliar** ``block_size`` and require the client to follow it;
2. **the verdict is the hash-verified read-back.** ``upload_finish`` answers ``code:0`` with a
   ``file_token`` for something that is only a file once it has been downloaded and hashed.

**No bytes are inspected anywhere in this file** — payloads are made in-process, compared by
``sha256`` through the shipped check, and thrown away.

Conformance-tier: the request shapes, the ``upload_prepare`` answer shape and the
server-declared partition behaviour are **measured external truth**
(``process/doctrine/conformance-tier.md`` § A.4). The plumbing tests at the foot — the local
refusals, the fence greps and the disclosure greps — are ordinary regression and are marked as
such.
"""
import ast
import io
import json
import math
import pathlib

import pytest
from lark_oapi.api.drive.v1 import (
    UploadFinishFileResponseBody,
    UploadPrepareFileResponseBody,
)

from larkdocio.base.media import MediaRoundTripError, sha256_of
from larkdocio.drive import files_write as fw
from larkdocio.drive.files_write import (
    SINGLE_SHOT_MAX_BYTES,
    DriveFileChunkedUploadError,
    DriveFilesWriteClient,
    put_file_in_folder,
)

REPO = pathlib.Path(__file__).resolve().parent.parent
CAPTURES = REPO / "tests" / "captures" / "drive-media-remainder-spike" / "captures"
MODULE = REPO / "src" / "larkdocio" / "drive" / "files_write.py"

FOLDER = "Example6bd9cfa48a93d0f900d7"
PERMALINK = "https://your-domain.larksuite.com/file/Example90686c06d9e09fc9abdc"


def capture(number: int) -> dict:
    """One committed capture, by its number. Missing means the evidence moved, not a skip."""
    matches = sorted(CAPTURES.glob(f"{number}-*.json"))
    assert matches, f"capture {number}- is missing from {CAPTURES}"
    return json.loads(matches[0].read_text("utf-8"))


PREPARE_SMALL = capture(703)     # block_num 1, block_size 4194304, for a 130-byte file
PREPARE_64MIB = capture(704)     # block_num 16, block_size 4194304, for a DECLARED 64 MiB
PART_SEQ_0 = capture(705)        # checksum OMITTED and the part was accepted
FINISH = capture(706)            # code:0 + a file_token — an acceptance, not a verdict
VERDICT = capture(707)           # the re-download that made it a finding

#: What the server answered on the spike's one tenant, on one day. It lives **here, in a test**,
#: as the thing the client must not have compiled in — never in the shipped path (see
#: :func:`test_no_block_size_constant_is_compiled_into_the_shipped_path`).
OBSERVED_BLOCK_SIZE = PREPARE_SMALL["response"]["data"]["block_size"]


# --------------------------------------------------------------------------- #
# The fake seam: real captured payload SHAPES, a server-declared partition.     #
# --------------------------------------------------------------------------- #

#: What the fake records when a form key is **absent** rather than present-and-empty.
_ABSENT = "<no such key>"


class _Resp:
    def __init__(self, code=0, data=None, file=None, msg="Success"):
        self.code, self.data, self.file, self.msg = code, data, file, msg


class _Meta:
    def __init__(self, url):
        self.url = url


class _MetasData:
    def __init__(self, metas):
        self.metas = metas


class _FakeFile:
    def __init__(self, outer):
        self._outer = outer

    def upload_prepare(self, request):
        o = self._outer
        o.calls.append(("upload_prepare", request))
        if o.prepare_code:
            return _Resp(code=o.prepare_code, msg="prepare refused")
        size = request.request_body.size
        block_num = o.declared_block_num
        if block_num is None:
            block_num = max(1, math.ceil(size / o.block_size))
        # Deserialized through the SDK's OWN body class, from a dict shaped exactly like the
        # committed capture's ``data`` — so a drift in that shape reddens here.
        body = UploadPrepareFileResponseBody({
            "upload_id": o.upload_id,
            "block_size": o.block_size,
            "block_num": block_num,
        })
        return _Resp(data=body)

    def upload_part(self, request):
        o = self._outer
        o.calls.append(("upload_part", request))
        body = request.request_body
        # ``checksum`` is read with a sentinel on purpose: the shipped leg DELETES the key
        # rather than leaving it None, because Lark refuses an empty checksum field.
        o.parts.append((body.seq, body.size, getattr(body, "checksum", _ABSENT),
                        body.file.read()))
        if body.seq in o.part_refusals:
            return _Resp(code=o.part_refusals[body.seq], msg="part refused")
        return _Resp(data=None)

    def upload_finish(self, request):
        o = self._outer
        o.calls.append(("upload_finish", request))
        if o.finish_code:
            return _Resp(code=o.finish_code, msg="finish refused")
        if o.finish_without_token:
            return _Resp(data=UploadFinishFileResponseBody({}))
        o.store[o.file_token] = b"".join(part[3] for part in o.parts)
        return _Resp(data=UploadFinishFileResponseBody({"file_token": o.file_token}))

    def download(self, request):
        o = self._outer
        o.calls.append(("download", request))
        if o.download_code:
            return _Resp(code=o.download_code, msg="download refused")
        payload = o.corrupt_download if o.corrupt_download is not None else o.store[
            request.file_token]
        return _Resp(file=io.BytesIO(payload))

    def delete(self, request):
        self._outer.calls.append(("delete", request))
        return _Resp()

    def upload_all(self, request):  # the single-shot leg, so routing can be observed
        o = self._outer
        o.calls.append(("upload_all", request))
        o.store[o.file_token] = request.request_body.file.read()
        return _Resp(data=type("_D", (), {"file_token": o.file_token, "url": "https://s/ig"})())


class _FakeMeta:
    def __init__(self, outer):
        self._outer = outer

    def batch_query(self, request):
        self._outer.calls.append(("batch_query", request))
        return _Resp(data=_MetasData([_Meta(PERMALINK)]))


class _FakeSDK:
    def __init__(self, *, block_size=OBSERVED_BLOCK_SIZE, declared_block_num=None,
                 prepare_code=0, finish_code=0, part_refusals=None,
                 finish_without_token=False, download_code=0, corrupt_download=None):
        self.calls, self.parts, self.store = [], [], {}
        self.block_size = block_size
        self.declared_block_num = declared_block_num
        self.prepare_code, self.finish_code = prepare_code, finish_code
        self.part_refusals = part_refusals or {}
        self.finish_without_token = finish_without_token
        self.download_code, self.corrupt_download = download_code, corrupt_download
        self.upload_id = PREPARE_SMALL["response"]["data"]["upload_id"]
        self.file_token = FINISH["response"]["data"]["file_token"]
        v1 = type("_V1", (), {"file": _FakeFile(self), "meta": _FakeMeta(self)})()
        self.drive = type("_Drive", (), {"v1": v1})()


class _NoWait:
    def acquire(self):
        return None


def client(**kw):
    sdk = _FakeSDK(**kw)
    return DriveFilesWriteClient("id", "secret", sdk_client=sdk, rate_limiter=_NoWait())


def seq_of(sdk):
    return [part[0] for part in sdk.parts]


# --------------------------------------------------------------------------- #
# AC2 — THE CUT-OVER IS SERVER-DECLARED.                                       #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_the_prepare_request_carries_the_captured_body_shape():
    """The four keys the capture's request body carried, and no invented fifth."""
    c = client()
    body = PREPARE_SMALL["request"]["body"]
    c.upload_prepare(name=body["file_name"], size=body["size"], folder_token=FOLDER)
    (_, request), = [call for call in c._sdk.calls if call[0] == "upload_prepare"]
    sent = request.request_body
    assert sent.file_name == body["file_name"]
    assert sent.parent_type == body["parent_type"] == "explorer"
    assert sent.parent_node == FOLDER
    assert sent.size == body["size"]


@pytest.mark.conformance
def test_the_prepare_answer_is_read_as_the_partition_the_server_declared():
    """Capture 703's own answer, deserialized: one block of 4194304 for 130 bytes."""
    c = client()
    partition = c.upload_prepare(name="ld437-chunked.html", size=130, folder_token=FOLDER)
    answer = PREPARE_SMALL["response"]["data"]
    assert partition.upload_id == answer["upload_id"]
    assert partition.block_size == answer["block_size"]
    assert partition.block_num == answer["block_num"] == 1


@pytest.mark.conformance
def test_a_declared_64_mib_partitions_into_the_sixteen_blocks_the_server_counted():
    """Capture 704: ``block_size`` did NOT move with the size; ``block_num`` did (1 → 16).

    Pure arithmetic over the captured answer — no bytes are made, because the spike never
    sent this one either.
    """
    answer = PREPARE_64MIB["response"]["data"]
    declared = PREPARE_64MIB["request"]["body"]["size"]
    assert answer["block_size"] == PREPARE_SMALL["response"]["data"]["block_size"]
    assert answer["block_num"] == 16
    assert fw.parts_for(declared, answer["block_size"]) == answer["block_num"]


@pytest.mark.conformance
def test_the_client_follows_a_server_declared_block_size_it_did_not_expect():
    """**The AC2 test.** A ``block_size`` of 7 — nothing like the captured 4 MiB — and the
    client sends the partition the server declared rather than one it assumed."""
    c = client(block_size=7)
    data = bytes(range(30))
    uploaded = c.upload_chunked(data=data, name="unexpected.bin", folder_token=FOLDER)
    sdk = c._sdk
    assert [part[1] for part in sdk.parts] == [7, 7, 7, 7, 2]
    assert seq_of(sdk) == [0, 1, 2, 3, 4]
    assert b"".join(part[3] for part in sdk.parts) == data
    (_, finish), = [call for call in sdk.calls if call[0] == "upload_finish"]
    assert finish.request_body.block_num == 5
    assert finish.request_body.upload_id == sdk.upload_id
    assert uploaded.parts == 5
    assert uploaded.sha256 == sha256_of(data)


@pytest.mark.conformance
def test_the_part_request_carries_the_captured_form_field_shape():
    """Capture 705's own form fields — ``upload_id`` / ``seq`` / ``size`` — and the file."""
    fields = PART_SEQ_0["request"]["form_fields"]
    c = client(block_size=7)
    c.upload_part(upload_id=fields["upload_id"], seq=int(fields["seq"]), data=b"abc")
    (_, request), = [call for call in c._sdk.calls if call[0] == "upload_part"]
    body = request.request_body
    assert body.upload_id == fields["upload_id"]
    assert body.seq == int(fields["seq"])
    assert body.size == 3


@pytest.mark.conformance
def test_a_declared_block_num_that_disagrees_with_the_block_size_is_refused_before_any_part():
    """Two halves of one answer that cannot both be true: nothing is sent, and the message
    says what it would have been guessing at."""
    c = client(block_size=7, declared_block_num=99)
    with pytest.raises(DriveFileChunkedUploadError) as excinfo:
        c.upload_chunked(data=bytes(30), name="disagreement.bin", folder_token=FOLDER)
    assert [call[0] for call in c._sdk.calls] == ["upload_prepare"]
    assert "99" in str(excinfo.value) and "5" in str(excinfo.value)
    assert excinfo.value.parts_sent == 0


def test_no_block_size_constant_is_compiled_into_the_shipped_path():
    """**A 4194304 literal used as a decision threshold is a FAIL** (AC2).

    Checked over the module's own syntax tree rather than its text, so the captured number may
    be **cited in prose** — it is evidence — while never being reachable as a value.
    """
    tree = ast.parse(MODULE.read_text("utf-8"))
    ints = [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, int)
            and not isinstance(node.value, bool)]
    assert OBSERVED_BLOCK_SIZE not in ints, (
        "the server's declared block size is compiled into the shipped path; it must be ASKED "
        "for, because 4194304 is one tenant's answer on one day")


def test_the_single_shot_cut_over_is_a_stated_library_POLICY_and_is_overridable():
    """A threshold is needed to decide *whether* to chunk; it is the library's, says so, and
    the caller can move it."""
    assert SINGLE_SHOT_MAX_BYTES != OBSERVED_BLOCK_SIZE
    source = MODULE.read_text("utf-8")
    assert "LIBRARY POLICY" in source
    assert "no server ever declared it" in source
    # Overridable, and the override is what routes: 30 bytes is far below the policy default.
    c = client(block_size=7)
    linked = put_file_in_folder(files=c, data=bytes(30), name="over.bin",
                                folder_token=FOLDER, chunk_above_bytes=8)
    assert linked.parts == 5
    assert [call[0] for call in c._sdk.calls].count("upload_all") == 0


def test_below_the_policy_the_single_shot_route_is_still_the_one_taken():
    c = client()
    linked = put_file_in_folder(files=c, data=b"small", name="small.bin", folder_token=FOLDER)
    assert linked.parts == 1
    kinds = [call[0] for call in c._sdk.calls]
    assert "upload_all" in kinds
    assert "upload_prepare" not in kinds


# --------------------------------------------------------------------------- #
# AC3 — THE VERDICT IS THE HASH-VERIFIED READ-BACK.                            #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_the_finish_answer_alone_is_not_treated_as_success():
    """``code:0`` with no ``file_token`` is an acceptance of nothing there is anything to
    verify — and the refusal says the verdict is the read-back."""
    c = client(block_size=7, finish_without_token=True)
    with pytest.raises(DriveFileChunkedUploadError) as excinfo:
        c.upload_chunked(data=bytes(30), name="tokenless.bin", folder_token=FOLDER)
    assert "no file_token" in str(excinfo.value)
    assert excinfo.value.upload_id == c._sdk.upload_id


@pytest.mark.conformance
def test_the_chunked_round_trip_is_verified_by_hash_through_the_shipped_check():
    c = client(block_size=7)
    data = bytes(range(30))
    linked = put_file_in_folder(files=c, data=data, name="verified.bin",
                                folder_token=FOLDER, chunk_above_bytes=8)
    assert linked.bytes_verified is True
    assert linked.sha256 == sha256_of(data)
    assert linked.url == PERMALINK
    assert [call[0] for call in c._sdk.calls].count("download") == 1


@pytest.mark.conformance
def test_bytes_that_come_back_different_fail_the_chunked_op():
    """The whole reason ``code:0`` is not the verdict: finish accepted, the file is wrong."""
    c = client(block_size=7, corrupt_download=b"not what went up")
    with pytest.raises(MediaRoundTripError):
        put_file_in_folder(files=c, data=bytes(range(30)), name="wrong.bin",
                           folder_token=FOLDER, chunk_above_bytes=8)


@pytest.mark.conformance
def test_the_verdict_capture_is_what_the_shipped_check_compares():
    """Capture 707 is a size and a digest — the two things ``verify_round_trip`` compares —
    and no bytes at all."""
    verdict = VERDICT["response"]
    assert verdict["downloaded_size"] == PREPARE_SMALL["request"]["body"]["size"]
    assert verdict["downloaded_sha256"] == PART_SEQ_0["request"]["file_part"]["sha256"]


def test_the_round_trip_truth_is_REUSED_not_redefined():
    source = MODULE.read_text("utf-8")
    assert "verify_round_trip" in source
    assert "import hashlib" not in source and "hashlib." not in source


# --------------------------------------------------------------------------- #
# AC4 — THE ABANDONED upload_id IS DISCLOSED, as `unmeasured`.                 #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_a_failed_part_says_what_it_left_behind():
    c = client(block_size=7, part_refusals={2: 1061045})
    with pytest.raises(DriveFileChunkedUploadError) as excinfo:
        c.upload_chunked(data=bytes(30), name="halfway.bin", folder_token=FOLDER)
    exc = excinfo.value
    message = str(exc)
    assert exc.upload_id == c._sdk.upload_id
    assert exc.parts_sent == 2 and exc.block_num == 5
    assert exc.upload_id in message
    assert "no Drive object" in message
    assert "no cancel verb" in message
    assert "unmeasured, not" in message
    # It stopped at the refusal rather than sending the rest at a transaction it cannot finish.
    assert seq_of(c._sdk) == [0, 1, 2]
    assert "upload_finish" not in [call[0] for call in c._sdk.calls]


@pytest.mark.parametrize("sentence", [
    "no cancel verb was found",
    "unmeasured, not \"cannot\"",
    "expiry is unmeasured",
])
def test_the_residue_disclosure_is_in_the_shipped_text(sentence):
    assert sentence in MODULE.read_text("utf-8")


# --------------------------------------------------------------------------- #
# AC10 — the checksum edge, grounded on exactly what was tried.                #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_the_optional_checksum_is_omitted_exactly_as_the_capture_omitted_it():
    assert "checksum" not in PART_SEQ_0["request"]["form_fields"]
    assert PART_SEQ_0["response"]["code"] == 0
    c = client(block_size=7)
    c.upload_chunked(data=bytes(30), name="nochecksum.bin", folder_token=FOLDER)
    assert [part[2] for part in c._sdk.parts] == [_ABSENT] * 5


@pytest.mark.conformance
def test_the_checksum_KEY_IS_DELETED_because_an_empty_one_is_REFUSED():
    """**Measured live, both ways round.** The pinned SDK builds this call's form from the
    body's attributes and keeps a key whose value is ``None``, so an unset ``checksum`` goes
    out as an EMPTY form field — which Lark refuses with a params error. The same body with the
    key deleted is accepted. So "omitted" has to mean *gone*, and this test pins that rather
    than the weaker claim that it is not set."""
    c = client(block_size=7)
    c.upload_part(upload_id="7673163768917937897", seq=0, data=b"abc")
    (_, request), = [call for call in c._sdk.calls if call[0] == "upload_part"]
    assert "checksum" not in vars(request.request_body)


@pytest.mark.parametrize("sentence", [
    "buys no guarantee this library can point to",
    "three parts across two uploads",
    "user_access_token",
    "other tenants",
])
def test_the_checksum_and_scope_edges_are_named(sentence):
    assert sentence in MODULE.read_text("utf-8")


# --------------------------------------------------------------------------- #
# AC1 — the shape choice, and AC5 — the fence, both stated in the change.      #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("sentence", [
    "size-triggered",           # the shape chosen
    "a sibling op",             # the alternative, named rather than silently dropped
])
def test_the_shape_choice_and_its_rejected_alternative_are_written_into_the_change(sentence):
    assert sentence in fw.__doc__


def test_nothing_here_opens_import_tasks_or_any_R3_verb():
    """The fence, checked mechanically over the whole shipped tree rather than promised.

    A **call site** is what may not appear — the verb followed by an open parenthesis, or the
    endpoint path itself. The words may appear in prose, because saying what stays shut is
    part of the disclosure.
    """
    # TRANSFORMED, NOT DELETED (LD-467, D-24): `create_folder(` left this list when a product
    # ruling of 2026-08-14 opened that ONE verb, and the reason the list exists is untouched —
    # every OTHER R3 rung (move, copy, shortcut) and the import-task family stay shut, and are
    # still checked mechanically. The opened verb is fenced by its own module-scoped guard in
    # `test_drive_files_write.py`, so nothing is merely trusted here either.
    forbidden = ("import_tasks(", "files/import_tasks", "files/move", "files/copy",
                 "create_shortcut(", "files/create_shortcut")
    hits = []
    for path in (REPO / "src" / "larkdocio").rglob("*.py"):
        text = path.read_text("utf-8")
        for word in forbidden:
            if word in text:
                hits.append((str(path.relative_to(REPO)), word))
    assert hits == [], hits


def test_the_destination_is_still_the_callers_and_is_refused_locally_when_missing():
    c = client(block_size=7)
    with pytest.raises(fw.DriveFileUploadError, match="folder token"):
        c.upload_chunked(data=bytes(30), name="nowhere.bin", folder_token="")
    assert c._sdk.calls == []


# --------------------------------------------------------------------------- #
# AC9 — the three endpoints are authored in the permission registry.           #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_every_chunked_endpoint_constant_matches_the_pinned_sdk_request_class():
    from lark_oapi.api.drive.v1 import (
        UploadFinishFileRequest,
        UploadPartFileRequest,
        UploadPrepareFileRequest,
    )
    assert UploadPrepareFileRequest.builder().build().uri == fw.FILES_UPLOAD_PREPARE_ENDPOINT
    assert UploadPartFileRequest.builder().build().uri == fw.FILES_UPLOAD_PART_ENDPOINT
    assert UploadFinishFileRequest.builder().build().uri == fw.FILES_UPLOAD_FINISH_ENDPOINT
    for path in PART_SEQ_0, FINISH:
        assert path["request"]["path"].startswith("/open-apis/drive/v1/files/upload_")


@pytest.mark.parametrize("endpoint", [
    "/open-apis/drive/v1/files/upload_prepare",
    "/open-apis/drive/v1/files/upload_part",
    "/open-apis/drive/v1/files/upload_finish",
])
def test_each_chunked_endpoint_has_its_own_recorded_unknown_scope_row(endpoint):
    from larkdocio import permissions as perms

    row = perms._table_row(endpoint, "write")
    assert row is not None and row[0] == endpoint, (
        "the chunked family must answer at its OWN row, not inherit the single-shot upload's "
        "non-observation")
    assert row[2] == (), "no scope string was ever observed demanded; none may be guessed"
    assert "recorded unknown" in row[3] or "never guessed" in row[3]


def test_the_op_reaches_the_three_endpoints_in_the_derivation():
    from larkdocio import permissions as perms

    reached = set(perms.endpoints_of(put_file_in_folder))
    assert {fw.FILES_UPLOAD_PREPARE_ENDPOINT, fw.FILES_UPLOAD_PART_ENDPOINT,
            fw.FILES_UPLOAD_FINISH_ENDPOINT} <= reached
