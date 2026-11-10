"""LD-644 — a scope denial carries the same five facts on a surface that keeps its OWN error
family, and an ordinary refusal on those same legs does not move a byte.

The defect this pins
--------------------
``errors.py`` claimed *"every surface's non-zero Lark code reaches a caller through here"*.
Fifteen sites across four modules did not: they handed Lark's ``code`` straight to a
``LarkAPIError`` **subclass** — ``MediaUploadError``, ``DriveFileChunkedUploadError``,
``DriveFolderCreateError``, ``LarkSpreadsheetUnreadableError`` — so a scope denial on the media
and file legs arrived with **no** ``PermissionDenial``, no console link and no credential
attribution. Those are exactly the legs where a missing grant is the likeliest failure, and it
is the failure whose whole cost is being mistaken for something else.

The fix is not "raise ``LarkPermissionError`` instead". ``MediaUploadError`` says *the
attachment leg failed and the record was never judged*; ``DriveFileChunkedUploadError`` carries
the ``upload_id`` of a transaction no listing shows and no delete removes. Answering *why* by
discarding *what* would be a second defect. So the class stays the surface's and the
classification is shared: :func:`larkdocio.errors.api_error_as`.

Both halves are asserted here, because either alone would let the other regress:

* **the denial half** — the record, the console link and the credential pair are present;
* **the "nothing else moved" half** — an ORDINARY code on the same leg keeps its class, its
  ``code``/``msg`` and its message **bytes**, and reports ``denial is None``. Refusal bytes are
  a consumer surface in this project.
"""
import io
import types

import pytest

from larkdocio import errors
from larkdocio.base import media
from larkdocio.base.media import BaseMediaClient, MediaDownloadError, MediaUploadError
from larkdocio.common.auth import WRITE_ENV
from larkdocio.drive import errors as drive_errors, files_write, folders_write
from larkdocio.drive.files_write import DriveFilesWriteClient, DriveFileUploadError
from larkdocio.drive.folders_write import DriveFolderCreateError, DriveFoldersWriteClient

#: A captured-shape scope denial: Lark's own code, its own message wording, and the console
#: deep link it supplies in the body's ``error.helps``. The link is never synthesized, so a
#: test that wants one has to put one in the answer.
DENIAL_CODE = 99991672
DENIAL_MSG = ("Access denied. One of the following scopes is required: "
              "[drive:drive] Please check the app's permission configuration")
CONSOLE_URL = "https://open.larksuite.com/app/cli_xxx/auth?q=drive:drive&op_from=openapi"

#: An ordinary, non-denial refusal on the same legs — the control.
PLAIN_CODE = 1061002
PLAIN_MSG = "internal error"


def _error_body(url=CONSOLE_URL):
    """The ``error`` half of a Lark answer, in the SDK's own shape (an object, not a dict)."""
    return types.SimpleNamespace(helps=[types.SimpleNamespace(url=url)])


class _Resp:
    """A Lark SDK response: ``code``/``msg``, and the ``error`` the console link lives in."""

    def __init__(self, code=0, msg="ok", *, file=None, data=None, error=None):
        self.code = code
        self.msg = msg
        self.file = file
        self.data = data
        self.error = error

    def success(self):
        return self.code == 0


class _Limiter:
    def acquire(self):
        pass


def _sdk(**leaves):
    """A fake ``sdk.drive.v1`` exposing only the leaves a test asks for."""
    v1 = types.SimpleNamespace(**leaves)
    return types.SimpleNamespace(drive=types.SimpleNamespace(v1=v1))


# --------------------------------------------------------------------------- #
# The media leg (AC4 — "at least one media leg").                              #
# --------------------------------------------------------------------------- #

def _media_client(code, msg, error=None):
    fake = types.SimpleNamespace(
        upload_all=lambda request: _Resp(code=code, msg=msg, error=error),
        download=lambda request: _Resp(code=code, msg=msg, error=error))
    return BaseMediaClient("id", "secret", sdk_client=_sdk(media=fake),
                           rate_limiter=_Limiter())


def _upload_refusal(code, msg, error=None):
    client = _media_client(code, msg, error)
    with pytest.raises(errors.LarkAPIError) as caught:
        client.upload(data=b"x", name="a.txt", parent_type=media.MEDIA_PARENT_TYPES[0],
                      parent_node="bascnXXXX")
    return caught.value


def test_a_media_upload_denial_now_carries_the_whole_denial_record():
    """The five facts, on the leg that had none of them: the missing scope, Lark's verbatim
    code and msg, the console link Lark supplied, and WHICH credential pair was in force."""
    error = _upload_refusal(DENIAL_CODE, DENIAL_MSG, _error_body())
    denial = error.denial
    assert denial is not None, "a scope denial on the media leg must classify as one"
    assert denial.scopes == ("drive:drive",)
    assert denial.code == DENIAL_CODE
    assert denial.msg == DENIAL_MSG, "Lark's msg must survive VERBATIM"
    assert denial.console_url == CONSOLE_URL
    assert denial.credential_env == WRITE_ENV
    # And all five reach a human through the one rendering, not just the attributes.
    detail = denial.detail()
    assert "drive:drive" in detail and CONSOLE_URL in detail and WRITE_ENV[0] in detail


def test_the_media_upload_denial_keeps_the_MEDIA_class_that_says_which_leg_failed():
    """The classification is added, the family is not taken away. ``MediaUploadError`` is what
    tells an apply log *the attachment leg failed* rather than *Lark judged the record* — the
    arm ``base.disposition`` reads to keep a media failure entry-scoped."""
    error = _upload_refusal(DENIAL_CODE, DENIAL_MSG, _error_body())
    assert isinstance(error, MediaUploadError)
    assert error.code == DENIAL_CODE and error.msg == DENIAL_MSG


def test_a_media_download_denial_classifies_too_and_keeps_its_own_class():
    client = _media_client(DENIAL_CODE, DENIAL_MSG, _error_body())
    with pytest.raises(MediaDownloadError) as caught:
        client.download("boxcnXXXX")
    assert caught.value.denial is not None
    assert caught.value.denial.console_url == CONSOLE_URL


def test_a_denial_body_with_NO_console_link_claims_none():
    """Absence is handled, never papered over — the shape's standing rule. A link this library
    invented would be a guess wearing the shape of an answer."""
    error = _upload_refusal(DENIAL_CODE, DENIAL_MSG, error=None)
    assert error.denial is not None, "the scope is in the message text as well as the body"
    assert error.denial.console_url is None


# --------------------------------------------------------------------------- #
# The file leg (AC4 — "and one file leg").                                     #
# --------------------------------------------------------------------------- #

def _file_upload_refusal(code, msg, error=None):
    fake = types.SimpleNamespace(upload_all=lambda request: _Resp(code=code, msg=msg,
                                                                 error=error))
    client = DriveFilesWriteClient("id", "secret", sdk_client=_sdk(file=fake),
                                   rate_limiter=_Limiter())
    with pytest.raises(errors.LarkAPIError) as caught:
        client.upload(data=b"x", name="a.txt", folder_token="fldcnXXXX")
    return caught.value


def test_a_drive_file_upload_denial_carries_the_record_and_keeps_its_class():
    error = _file_upload_refusal(DENIAL_CODE, DENIAL_MSG, _error_body())
    assert isinstance(error, DriveFileUploadError)
    assert error.denial is not None
    assert error.denial.scopes == ("drive:drive",)
    assert error.denial.console_url == CONSOLE_URL
    assert error.denial.credential_env == WRITE_ENV


def test_a_chunked_upload_denial_keeps_the_upload_id_AND_gains_the_denial():
    """Both, which is the whole reason the class is preserved rather than replaced: the
    resumption evidence (a transaction no listing shows and no delete removes) and the
    classification are not in competition."""
    fake = types.SimpleNamespace(
        upload_prepare=lambda request: _Resp(code=DENIAL_CODE, msg=DENIAL_MSG,
                                             error=_error_body()))
    client = DriveFilesWriteClient("id", "secret", sdk_client=_sdk(file=fake),
                                   rate_limiter=_Limiter())
    with pytest.raises(files_write.DriveFileChunkedUploadError) as caught:
        client.upload_prepare(name="a.bin", size=1, folder_token="fldcnXXXX")
    assert caught.value.denial is not None
    assert caught.value.denial.console_url == CONSOLE_URL


def _folder_create_refusal(code, msg, error=None):
    client = DriveFoldersWriteClient("id", "secret")
    body = {"code": code, "msg": msg}
    if error is not None:
        body["error"] = error
    client._send = lambda *a, **kw: body
    client._limiter = _Limiter()
    with pytest.raises(errors.LarkAPIError) as caught:
        client.create_folder("plans", "fldcnXXXX")
    return caught.value


def test_the_two_MEASURED_folder_refusals_keep_their_class_their_bytes_and_their_attributes():
    """The folder leg's two bypassing sites are its two **measured** codes, and neither is a
    denial code — so what routing them buys is uniformity, not a new classification. What must
    not change is everything else: the class, the wording, and the ``name``/``parent_token`` a
    traceback needs to say WHICH create failed."""
    error = _folder_create_refusal(folders_write.FOLDER_REFUSED_CODE, "Forbidden")
    assert type(error) is DriveFolderCreateError
    assert error.denial is None
    assert error.name == "plans" and error.parent_token == "fldcnXXXX"
    assert error.code == folders_write.FOLDER_REFUSED_CODE
    assert str(error) == (
        "the folder 'plans' was not created under 'fldcnXXXX'. "
        f"{drive_errors.REFUSAL_SENTENCE} On this route that same code is also the answer "
        "when the token is not a folder at all — a real file token as the parent was refused "
        "with it. Nothing was created. Check that the token names a FOLDER this app "
        "may write to, then retry")


def test_a_REAL_denial_on_the_folder_leg_still_goes_through_the_shared_seam_untouched():
    """The other half of the folder leg, unchanged: an unmeasured code is surfaced through
    ``raise_for_lark_code`` undecorated, so a scope denial there already arrived as a
    :class:`LarkPermissionError` with the whole record. Pinned so the routing above cannot
    quietly swallow it into the typed family."""
    error = _folder_create_refusal(DENIAL_CODE, DENIAL_MSG,
                                   error={"helps": [{"url": CONSOLE_URL}]})
    assert isinstance(error, errors.LarkPermissionError)
    assert error.denial.console_url == CONSOLE_URL
    assert error.denial.credential_env == WRITE_ENV


# --------------------------------------------------------------------------- #
# AC5 — nothing else moves. The control, on the same legs.                     #
# --------------------------------------------------------------------------- #

def test_an_ORDINARY_refusal_on_the_media_leg_is_byte_for_byte_what_it_was():
    """The exact shipped text, quoted here so a change to it has to be deliberate. Refusal
    bytes are a consumer surface in this project — a message is not free to drift because a
    classification was added behind it."""
    error = _upload_refusal(PLAIN_CODE, PLAIN_MSG)
    assert type(error) is MediaUploadError
    assert error.denial is None, "an ordinary failure must NOT read as a scope denial"
    assert error.code == PLAIN_CODE and error.msg == PLAIN_MSG
    assert str(error) == (
        "the upload of 'a.txt' to 'bascnXXXX' was refused: "
        f"Code: {PLAIN_CODE}, Msg: {PLAIN_MSG}. Nothing was attached and no token "
        f"exists. {BaseMediaClient.UPLOAD_REFUSAL_ADVICE}")


def test_an_ORDINARY_refusal_on_the_file_leg_is_byte_for_byte_what_it_was():
    error = _file_upload_refusal(PLAIN_CODE, PLAIN_MSG)
    assert type(error) is DriveFileUploadError
    assert error.denial is None
    assert str(error) == (
        f"the upload of 'a.txt' into 'fldcnXXXX' was refused: Code: {PLAIN_CODE}, "
        f"Msg: {PLAIN_MSG}. Nothing was uploaded and no token exists. "
        "Check that the folder token names a folder this app may write to, then retry")


def test_a_RATE_LIMIT_code_on_a_typed_leg_keeps_the_surfaces_own_class():
    """``api_error_as`` classifies; it does not re-type. ``api_error`` would return
    :class:`LarkRateLimitError` here, and a surface that asked for its own family gets its own
    family on every code — the ``is_rate_limit`` property still answers, from the base."""
    error = _upload_refusal(int(errors.RATE_LIMIT_CODE), "too many requests")
    assert type(error) is MediaUploadError
    assert error.is_rate_limit is True
    assert error.denial is None


def test_a_local_pre_call_refusal_still_carries_no_denial_and_no_code():
    """The refusals that never reached Lark are untouched: no code, no classification, and the
    same class they always raised."""
    client = _media_client(0, "ok")
    with pytest.raises(MediaUploadError) as caught:
        client.upload(data=b"x", name="a.txt", parent_type="not_a_parent_type",
                      parent_node="bascnXXXX")
    assert caught.value.code is None and caught.value.denial is None


# --------------------------------------------------------------------------- #
# The base attribute itself.                                                   #
# --------------------------------------------------------------------------- #

def test_every_api_error_answers_the_denial_question_the_same_way():
    """``err.denial is not None`` is the ONE check that means the same thing on every surface.
    Before this it was answerable only on ``LarkPermissionError``, so a caller asking it of a
    media failure got an ``AttributeError`` and a caller who did not ask got a permissions
    problem wearing the costume of an ordinary one."""
    assert errors.LarkAPIError("x").denial is None
    assert errors.LarkRateLimitError("x", code=99991400).denial is None
    assert errors.LarkSpreadsheetUnreadableError("x", code=1, skips=()).denial is None
    assert MediaUploadError("x").denial is None


def test_api_error_as_carries_an_ALREADY_classified_record_rather_than_rebuilding_it():
    """The re-wrap door. Re-deriving the record from ``code``/``msg`` alone would work — and
    would silently drop the console link the original body supplied, which is the half that
    only ever exists in a body."""
    first = errors.api_error_as(DriveFileUploadError, "inner", code=DENIAL_CODE,
                                msg=DENIAL_MSG, body=_error_carrier(), credential_env=WRITE_ENV)
    assert first.denial.console_url == CONSOLE_URL
    again = errors.api_error_as(DriveFileUploadError, "outer — 3 of 9 blocks sent",
                                code=first.code, msg=first.msg, denial=first.denial,
                                credential_env=WRITE_ENV)
    assert again.denial is first.denial, "the record is carried, not rebuilt"
    assert again.denial.console_url == CONSOLE_URL


def _error_carrier():
    """A body carrying only the ``error`` half — what ``_console_url_from_body`` reads."""
    return types.SimpleNamespace(error=_error_body())


def test_the_message_is_passed_through_VERBATIM_by_the_class_preserving_door():
    """This family adds attributes; it does not edit text. Asserted directly on the factory so
    the rule is pinned independently of any one call site."""
    text = "a message with {braces} and a 100% literal — unchanged"
    error = errors.api_error_as(MediaUploadError, text, code=PLAIN_CODE, msg=PLAIN_MSG)
    assert str(error) == text


def test_the_download_leg_answers_bytes_when_nothing_is_wrong():
    """A smoke check that the routed legs still work on the happy path — a classification seam
    that broke the success path would be a poor trade."""
    fake = types.SimpleNamespace(
        download=lambda request: _Resp(code=0, file=io.BytesIO(b"payload")))
    client = BaseMediaClient("id", "secret", sdk_client=_sdk(media=fake),
                             rate_limiter=_Limiter())
    assert client.download("boxcnXXXX") == b"payload"
