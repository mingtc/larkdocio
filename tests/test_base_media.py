"""LD-268 — the attachment out-of-band leg, offline.

Every parameter this module pins comes from a capture, and every byte assertion is a
**hash** assertion: no test here inspects, decodes or renders media bytes, which is the
standing rule for binary artifacts in this repository. The payloads the fake transport
carries are made in-process, compared by ``sha256`` and thrown away.

The credential-class rule is asserted the same way the PII sweep asserts its own: by a
**sweep**, not by trusting each author to remember. ``url`` and ``tmp_url`` are short-lived
signed links, so a fixture that carried one would be a committed credential.
"""
import hashlib
import io
import json
import re
from pathlib import Path

import pytest

import capability_rows as rows
from larkdocio.base import media
from larkdocio.base.disposition import ENTRY_SCOPED, classify_apply_exception
from larkdocio.base.media import (
    BaseMediaClient,
    MediaDownloadError,
    MediaRoundTripError,
    MediaTokenNotFoundError,
    MediaUploadError,
    UploadedMedia,
)
from larkdocio.base.cells import FieldSpec
from larkdocio.base.write_cells import encode_cell

_REPO = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# The fake SDK seam — one recorder for both legs.                              #
# --------------------------------------------------------------------------- #

class _Resp:
    def __init__(self, code=0, file=None, data=None, msg="ok"):
        self.code = code
        self.msg = msg
        self.file = file
        self.data = data

    def success(self):
        return self.code == 0


class _UploadData:
    def __init__(self, file_token):
        self.file_token = file_token


class _FakeMedia:
    """Records every request and answers whatever the test queued."""

    def __init__(self, store=None, upload_code=0, download_code=0, download_file="present"):
        self.requests = []
        self.store = {} if store is None else store
        self.upload_code = upload_code
        self.download_code = download_code
        self.download_file = download_file
        self._n = 0

    def upload_all(self, request):
        self.requests.append(("upload_all", request))
        if self.upload_code:
            return _Resp(code=self.upload_code, msg="upload refused")
        self._n += 1
        token = f"boxcn{self._n:04d}"
        body = request.request_body
        payload = body.file.read() if hasattr(body.file, "read") else body.file
        self.store[token] = payload
        return _Resp(data=_UploadData(token))

    def download(self, request):
        self.requests.append(("download", request))
        if self.download_code:
            return _Resp(code=self.download_code, msg="download refused")
        payload = self.store.get(request.file_token)
        if payload is None:
            return _Resp(code=media.FILE_TOKEN_NOT_FOUND_CODES[0], msg="file not found")
        if self.download_file is None:
            return _Resp(file=None)
        return _Resp(file=io.BytesIO(payload))


class _FakeSDK:
    def __init__(self, fake_media):
        self.drive = type("drive", (), {"v1": type("v1", (), {"media": fake_media})()})()


class _NoTransport:
    """A transport that raises the moment it is touched — so a local refusal that failed to
    fire errors instead of quietly making a call."""

    def __getattr__(self, name):
        raise AssertionError(f"a local refusal must make NO call; touched {name!r}")


def _media_client(fake_media=None, **kwargs):
    fake_media = _FakeMedia() if fake_media is None else fake_media
    return BaseMediaClient("id", "secret", sdk_client=_FakeSDK(fake_media),
                           rate_limiter=_Limiter(), **kwargs), fake_media


class _Limiter:
    def __init__(self):
        self.acquired = 0

    def acquire(self):
        self.acquired += 1


# --------------------------------------------------------------------------- #
# AC1 — the upload leg, its two parent types, and the parent_node warning.     #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("parent_type", ["bitable_file", "bitable_image"])
def test_ac1_the_upload_sends_the_CAPTURED_parameters_for_BOTH_parent_types(parent_type):
    client, fake = _media_client()
    uploaded = client.upload(data=b"eight-bytes", name="probe.txt",
                             parent_type=parent_type, parent_node="appTOKEN")
    (verb, request), = fake.requests
    assert verb == "upload_all"
    assert request.uri == media.UPLOAD_ENDPOINT
    body = request.request_body
    assert (body.parent_type, body.parent_node) == (parent_type, "appTOKEN")
    assert body.file_name == "probe.txt"
    assert body.size == len(b"eight-bytes")
    assert uploaded == UploadedMedia(
        file_token="boxcn0001", parent_type=parent_type, parent_node="appTOKEN",
        size=len(b"eight-bytes"),
        sha256=hashlib.sha256(b"eight-bytes").hexdigest(),
    )


def test_ac1_the_two_parent_types_are_the_captured_pair_and_nothing_else():
    assert media.MEDIA_PARENT_TYPES == ("bitable_file", "bitable_image")


def test_ac1_an_unknown_parent_type_is_refused_LOCALLY_with_zero_calls():
    client = BaseMediaClient("id", "secret", sdk_client=_NoTransport(),
                             rate_limiter=_Limiter())
    with pytest.raises(MediaUploadError) as excinfo:
        client.upload(data=b"x", name="x", parent_type="doc_image", parent_node="appTOKEN")
    assert "bitable_file" in str(excinfo.value) and "bitable_image" in str(excinfo.value)


def test_ac1_an_empty_parent_node_is_refused_LOCALLY_with_zero_calls():
    client = BaseMediaClient("id", "secret", sdk_client=_NoTransport(),
                             rate_limiter=_Limiter())
    with pytest.raises(MediaUploadError) as excinfo:
        client.upload(data=b"x", name="x", parent_type="bitable_file", parent_node="")
    assert "app_token" in str(excinfo.value)


def test_ac1_the_parent_node_warning_is_NAMED_in_the_uploads_own_docstring():
    """O4‴: ``parent_node`` is an app_token, and the wrong one attaches permanent residue to
    the wrong Base. The warning lives on the parameter's own method, not only in the module
    header, because that is where a caller reading ``help()`` meets it."""
    doc = BaseMediaClient.upload.__doc__
    assert "parent_node" in doc and "app_token" in doc
    assert "WARNING" in doc
    assert "cannot be undone" in doc or "cannot be purged" in doc


def test_ac1_the_upload_is_PACED_like_every_other_write_call():
    limiter = _Limiter()
    fake = _FakeMedia()
    client = BaseMediaClient("id", "secret", sdk_client=_FakeSDK(fake), rate_limiter=limiter)
    client.upload(data=b"x", name="x", parent_type="bitable_file", parent_node="appTOKEN")
    client.download("boxcn0001")
    assert limiter.acquired == 2


# --------------------------------------------------------------------------- #
# AC2 — the seam into LD-256's encoder (consumed, never re-authored).          #
# --------------------------------------------------------------------------- #

def _attachment_field():
    return FieldSpec(field_name="Files", type=17, ui_type="Attachment", property={})


def test_ac2_the_uploads_token_feeds_LD256s_ENCODER_UNCHANGED():
    client, _ = _media_client()
    uploaded = client.upload(data=b"payload", name="p.bin", parent_type="bitable_file",
                             parent_node="appTOKEN")
    encoded = encode_cell([uploaded.file_token], _attachment_field())
    assert encoded == [{"file_token": uploaded.file_token}]


def test_ac2_the_BARE_LIST_REFUSAL_is_LD256s_and_is_CITED_not_reasserted():
    """The refusal itself is the encoder's AC, so this story asserts only that the seam still
    reaches it — the object form is what the encoder builds, and its advice still names the
    server's own code."""
    field = _attachment_field()
    with pytest.raises(Exception) as excinfo:
        encode_cell([{"nope": 1}], field)
    assert "1254069" in str(excinfo.value)


def test_ac2_two_uploads_in_ONE_cell_both_survive_the_encoder():
    client, _ = _media_client()
    first = client.upload(data=b"one", name="1", parent_type="bitable_file",
                          parent_node="appTOKEN")
    second = client.upload(data=b"two", name="2", parent_type="bitable_image",
                           parent_node="appTOKEN")
    encoded = encode_cell([first.file_token, second.file_token], _attachment_field())
    assert encoded == [{"file_token": first.file_token}, {"file_token": second.file_token}]


# --------------------------------------------------------------------------- #
# AC3 — the download verifies BY HASH, never by inspection.                    #
# --------------------------------------------------------------------------- #

def test_ac3_the_round_trip_is_verified_BY_HASH():
    client, fake = _media_client()
    payload = b"a hundred and eight bytes, near enough"
    uploaded = client.upload(data=payload, name="p.bin", parent_type="bitable_file",
                             parent_node="appTOKEN")
    got = client.download(uploaded.file_token)
    assert media.verify_round_trip(uploaded, got) == uploaded.sha256
    assert fake.requests[-1][1].uri == media.DOWNLOAD_ENDPOINT


@pytest.mark.parametrize("payload,name", [
    (b"", "empty.bin"),                       # the zero-byte case
    (b"non-ascii-named", "näme-中.bin"),   # the non-ASCII name case
])
def test_ac3_the_amplifier_cases_round_trip_by_hash(payload, name):
    client, _ = _media_client()
    uploaded = client.upload(data=payload, name=name, parent_type="bitable_file",
                             parent_node="appTOKEN")
    assert media.verify_round_trip(uploaded, client.download(uploaded.file_token)) \
        == hashlib.sha256(payload).hexdigest()


def test_ac3_a_SINGLE_CORRUPTED_BYTE_reddens_the_verify():
    """The deliberate-defect check: the hash assertion is the gate, so it must fail on a
    one-byte corruption or it is proving nothing."""
    client, _ = _media_client()
    payload = b"the payload, whole"
    uploaded = client.upload(data=payload, name="p.bin", parent_type="bitable_file",
                             parent_node="appTOKEN")
    corrupted = bytearray(client.download(uploaded.file_token))
    corrupted[0] ^= 0x01
    with pytest.raises(MediaRoundTripError):
        media.verify_round_trip(uploaded, bytes(corrupted))


def test_ac3_a_hash_mismatch_reports_HASHES_AND_LENGTHS_never_the_bytes():
    uploaded = UploadedMedia(file_token="boxcn1", parent_type="bitable_file",
                             parent_node="appTOKEN", size=3,
                             sha256=hashlib.sha256(b"abc").hexdigest())
    with pytest.raises(MediaRoundTripError) as excinfo:
        media.verify_round_trip(uploaded, b"xyz")
    message = str(excinfo.value)
    assert uploaded.sha256 in message and hashlib.sha256(b"xyz").hexdigest() in message
    assert "xyz" not in message and "abc" not in message


def test_ac3_a_download_that_returns_NO_FILE_CONTENT_is_typed():
    client, fake = _media_client(_FakeMedia(download_file=None))
    uploaded = client.upload(data=b"x", name="x", parent_type="bitable_file",
                             parent_node="appTOKEN")
    with pytest.raises(MediaDownloadError):
        client.download(uploaded.file_token)


# --------------------------------------------------------------------------- #
# AC4 — url / tmp_url are credential-class.                                    #
# --------------------------------------------------------------------------- #

def test_ac4_the_ephemeral_keys_are_named_and_are_the_two_from_the_capture():
    assert media.EPHEMERAL_ATTACHMENT_KEYS == ("url", "tmp_url")


#: The stand-in every test here uses where a real read-back carries a signed link. It is
#: deliberately NOT link-shaped: a plausible-looking one committed to a test file is the exact
#: shape the sweep below exists to catch, and a fake that trips your own detector is a bad fake.
_LINK_PLACEHOLDER = "<signed-link-not-committed>"


def test_ac4_the_readback_projection_DROPS_the_two_signed_links():
    cell = {"file_token": "boxcn1", "name": "p.bin", "size": 108, "type": "text/plain",
            "url": _LINK_PLACEHOLDER, "tmp_url": _LINK_PLACEHOLDER}
    projected = media.scrub_attachment_cell(cell)
    assert projected == {"file_token": "boxcn1", "name": "p.bin", "size": 108,
                         "type": "text/plain"}
    assert "http" not in json.dumps(projected)


def test_ac4_the_projection_is_what_a_LOG_OR_ERROR_may_carry():
    """The scrubber is not advisory: the module's own describe path runs a read-back through
    it before anything is interpolated into a message."""
    cell = {"file_token": "boxcn1", "name": "p.bin", "size": 1,
            "tmp_url": _LINK_PLACEHOLDER}
    assert "signed-link" not in str(media.describe_attachment_cell(cell))


#: ``tmp_url`` belongs to exactly one payload shape in this API — an attachment / media
#: read-back — so a link-shaped value under that key is unambiguously the ephemeral credential.
_TMP_LINK = re.compile(r'"tmp_url"\s*:\s*"\s*http')
#: ``url`` is ambiguous repo-wide (a docx link block legitimately carries one), so the plain
#: key is swept only where a ``file_token`` sits beside it — that pairing IS the attachment
#: read-back.
_ANY_LINK = re.compile(r'"(?:tmp_)?url"\s*:\s*"\s*http')

#: Everything this story ships or touches that a signed link could land in.
_STORY_FILES = (
    "src/larkdocio/base/media.py",
    "tests/test_base_media.py",
    "tests/test_live_base_media_gate.py",
    "tests/test_live_base_media_gate_offline.py",
    "tests/base_write_harness.py",
)


def test_ac4_NO_FIXTURE_OR_STORY_FILE_CARRIES_A_SIGNED_LINK():
    """The sweep, on the same standard as the PII sweep: a committed ``url`` / ``tmp_url``
    **value** is a committed credential, so no file this story ships may carry one — and
    neither may any offline fixture, since an attachment read-back is exactly the payload
    somebody would paste. A fixture that carries a ``file_token`` is held to the stricter
    pattern, because there the bare ``url`` key is the attachment's own."""
    offenders = []
    candidates = [(_REPO / name, True) for name in _STORY_FILES]
    candidates += [(p, False) for p in sorted((_REPO / "tests" / "fixtures").rglob("*.json"))]
    for path, story in candidates:
        if not path.exists():
            offenders.append(f"{path}: missing")
            continue
        text = path.read_text(encoding="utf-8")
        pattern = _ANY_LINK if (story or "file_token" in text) else _TMP_LINK
        if pattern.search(text):
            offenders.append(str(path.relative_to(_REPO)))
    assert not offenders, f"a signed attachment link is committed in: {offenders}"


# --------------------------------------------------------------------------- #
# AC5 — the residue is disclosed where the leg lives.                          #
# --------------------------------------------------------------------------- #

def test_ac5_the_module_DISCLOSES_that_media_accretes_and_cannot_be_swept():
    """TRANSFORMED, never deleted, when the absence stopped being an assumption.

    **The reason is preserved:** the leg that mints permanent tenant residue must say so
    where it lives, or the disclosure rots into a release note nobody re-reads. **Only the
    conclusion moved.** The original assertion accepted either spelling of an *unmeasured*
    class-level negative — ``"no open-api …"`` or ``"no purge verb"`` — which is exactly the
    sentence ``process/doctrine/negative-claims.md`` § A.1 forbids: a claim about Lark's
    platform with the attempt list left in the author's head. The absence is now **measured**
    (nine destructive request spellings, fourteen sends, not one removed a token), so this
    guard asks for the measured shape instead — the claim, the pointer to the one authoring
    that carries the enumeration, and the scope word that keeps it falsifiable. Accepting the
    old spelling would let the weaker sentence grow back.
    """
    doc = media.__doc__
    lowered = doc.lower()
    assert "row 10" in lowered
    assert "no route in lark's open api purges drive media" in lowered
    assert "no_route_purges_drive_media" in lowered
    assert "unmeasured, not refuted" in lowered
    assert "ledger" in lowered


def test_ac5_the_module_records_the_SUBSTRATE_CALL():
    """The within-story Dev call, recorded where the next reader will look: this leg rides the
    pinned-SDK drive media path the docx image download already rides, rather than minting a
    third definition of 'download a Lark media token'."""
    doc = media.__doc__
    assert "download_image" in doc
    assert "third" in doc.lower()


# --------------------------------------------------------------------------- #
# AC7 — the error vocabulary is typed and actionable.                          #
# --------------------------------------------------------------------------- #

def test_ac7_a_token_that_no_longer_resolves_is_its_OWN_type():
    client, _ = _media_client()
    with pytest.raises(MediaTokenNotFoundError) as excinfo:
        client.download("boxcnGONE")
    message = str(excinfo.value)
    assert "boxcnGONE" in message
    assert "upload" in message.lower()


def test_ac7_a_non_zero_download_is_typed_and_carries_the_code():
    client, _ = _media_client(_FakeMedia(download_code=1061003))
    with pytest.raises(MediaDownloadError) as excinfo:
        client.download("boxcn1")
    assert excinfo.value.code == 1061003


def test_ac7_a_non_zero_upload_is_typed_and_carries_the_code():
    client, _ = _media_client(_FakeMedia(upload_code=1061003))
    with pytest.raises(MediaUploadError) as excinfo:
        client.upload(data=b"x", name="x", parent_type="bitable_file",
                      parent_node="appTOKEN")
    assert excinfo.value.code == 1061003


def test_ac7_NO_media_message_advises_requesting_a_scope():
    """The binding rule, asserted at the one place this story adds messages."""
    source = (_REPO / "src/larkdocio/base/media.py").read_text(encoding="utf-8")
    for forbidden in ("request the scope", "ask for the scope", "widen the scope",
                      "escalate the scope"):
        assert forbidden not in source.lower()


# --------------------------------------------------------------------------- #
# AC9 — the disposition of a media failure is its OWN typed reason.            #
# --------------------------------------------------------------------------- #

def test_ac9_a_media_leg_failure_is_classified_with_its_OWN_reason():
    disposition = classify_apply_exception(
        MediaDownloadError("nope", code=1061003), wrote=False)
    assert disposition.reason == media.MEDIA_REFUSAL_REASON
    assert disposition.scope == ENTRY_SCOPED


def test_ac9_the_ATTACH_CONVERSION_CODE_stays_ENTRY_SCOPED_per_the_ruled_table():
    from larkdocio.errors import LarkAPIError

    disposition = classify_apply_exception(
        LarkAPIError("AttachFieldConvFail", code=1254069), wrote=False)
    assert disposition.scope == ENTRY_SCOPED


def test_ac9_a_media_failure_is_NOT_folded_into_the_bitable_taxonomy():
    from larkdocio.errors import LarkAPIError

    bitable = classify_apply_exception(LarkAPIError("nope", code=1254069), wrote=False)
    assert classify_apply_exception(
        MediaDownloadError("nope", code=1061003), wrote=False).reason != bitable.reason


# --------------------------------------------------------------------------- #
# AC8 — the two DRIVE-family permission rows, derived from these call sites.   #
# --------------------------------------------------------------------------- #

def test_ac8_both_media_endpoints_have_their_own_WRITE_side_row():
    from larkdocio import permissions as perm

    rows = {(prefix, mode) for prefix, mode, _s, _n in perm.ENDPOINT_SCOPES}
    assert (media.UPLOAD_ENDPOINT, "write") in rows
    assert (media.DOWNLOAD_ENDPOINT, "write") in rows


def test_ac8_the_rows_say_the_leg_is_DRIVE_FAMILY_not_bitable():
    """The consumer-visible point of the rows: a Base grant says nothing about this call."""
    from larkdocio import permissions as perm

    for endpoint in (media.UPLOAD_ENDPOINT, media.DOWNLOAD_ENDPOINT):
        reasons = perm.unknown_requirements_for((endpoint,), "write")
        assert reasons, endpoint
        assert any("drive" in r.lower() for r in reasons), endpoint
    assert perm.scopes_for_endpoints((media.UPLOAD_ENDPOINT,), "write") == (), (
        "no scope has ever been observed demanded here; none may be invented")


def test_ac8_the_media_legs_are_DERIVED_from_their_own_call_sites():
    import larkdocio

    legs = {leg["name"]: leg for leg
            in rows.call_sites(larkdocio.capabilities(full=True)["surfaces"]["base-write"], rows.LEG)}
    assert legs["upload_attachment_media"]["permissions"]["endpoints"] == [
        media.UPLOAD_ENDPOINT]
    assert legs["download_attachment_media"]["permissions"]["endpoints"] == [
        media.DOWNLOAD_ENDPOINT]
    assert legs["upload_attachment_media"]["permissions"]["credentials_env"][0] \
        == "LARK_WRITE_APP_ID"


# --------------------------------------------------------------------------- #
# AC10 — the landed register rows are corrected IN PLACE.                      #
# --------------------------------------------------------------------------- #

def _register_row(number):
    text = (_REPO / "BASE.md").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith(f"| {number} |"):
            return line
    raise AssertionError(f"BASE.md has no register row {number}")


def test_ac10_row_19_is_RETRACTED_and_REWRITTEN_in_place():
    """The row's own revisit trigger named this decision, so the honest correction is a
    rewrite of row 19 — not a new row saying the opposite of a row still standing."""
    row = _register_row(19)
    assert "`deferred`" not in row, "row 19 still carries the retracted status"
    assert "`supported`" in row
    for claim in ("bitable_file", "bitable_image", "app_token", "sha256", "1254069"):
        assert claim in row, f"row 19 does not state {claim}"
    assert "never render" in row, "row 19 must keep what still does NOT happen"
    assert "tests/test_live_base_media_gate.py" in row


def test_ac10_row_10_is_EXTENDED_with_this_legs_ledger_not_re_authored():
    row = _register_row(10)
    assert "UN-PURGEABLE" in row, "row 10's original subject must survive"
    assert "tests/base_write_harness.py" in row
    assert "row 19" in row


def test_ac10_the_register_COUNT_DOES_NOT_MOVE_for_this_story():
    """This story appends no numbered row. The count is read from the guard rather than
    restated here, so the two cannot drift."""
    from test_base_md_matrix import _REGISTER_ROWS, _register_rows

    rows = _register_rows((_REPO / "BASE.md").read_text(encoding="utf-8"))
    assert len(rows) == _REGISTER_ROWS
