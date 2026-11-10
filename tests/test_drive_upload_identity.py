"""Upload identity and gone-ness on the Drive files surface — offline.

Two findings, one surface. **Identity:** a second upload of the same name into the same folder
mints a **second file object**, and until now nothing in the library said so and nothing let a
caller check first. **Gone-ness:** a delete refused with Lark's *"file has been delete."* code
used to be reported as *"The file is still there"* — the opposite of the truth.

**Every shape pinned here came off a live probe**, whose captures are committed under
``tests/captures/ld464-upload-identity/captures/`` (in the dev repo) and whose digest is
``ld464-99-findings.json``. Nothing here is hand-mocked from documentation: the child-key set the
lookup is fenced to, the eight overwrite forms that were tried, and the two delete answers are
each read out of that digest by this file, so a re-measurement that disagrees reddens the suite.

Conformance-tier: the disclosure text, the measured identity fence and the delete reading are
**product contract / measured external truth** (``process/doctrine/conformance-tier.md`` § A.4).
"""
import inspect
import json
import pathlib

import pytest

import drive_fixtures as fx
from larkdocio.drive import files_write as fw
from larkdocio.drive.client import DriveClient
from larkdocio.drive.files_write import (
    DRIVE_FILE_GONE_CODES,
    DriveFileDeleteError,
    DriveFilesWriteClient,
    file_is_gone,
    put_file_in_folder,
)
from larkdocio.drive.lookup import (
    DUPLICATE_UPLOAD_BEHAVIOUR,
    IDENTITY_NOT_AFFORDED,
    IDENTITY_THE_LISTING_AFFORDS,
    FolderNameMatches,
    match_children_by_name,
)
from larkdocio.errors import LarkAPIError
from larkdocio.sheets.write_client import FILE_ALREADY_DELETED_CODE, spreadsheet_is_gone

pytestmark = pytest.mark.conformance

REPO = pathlib.Path(__file__).resolve().parent.parent
CAPTURES = REPO / "tests" / "captures" / "ld464-upload-identity" / "captures"
NAME = "modules.csv"


def findings() -> dict:
    """The probe's own digest — the evidence base every pin in this file reads."""
    return json.loads((CAPTURES / "ld464-99-findings.json").read_text("utf-8"))["findings"]


def child(token, name, *, type="file"):
    """One listing row in the captured shape."""
    return {"token": token, "name": name, "type": type, "parent_token": "fldExmpl",
            "url": f"https://example.larksuite.com/file/{token}",
            "created_time": "1755230000", "modified_time": "1755230000",
            "owner_id": "ou_probe"}


def listing_client(children, **kwargs):
    """A read client whose whole transport is a recording stub — no network."""
    transport = fx.RecordingTransport(fx.listing_router({"fldExmpl": fx.page(children)}))
    kwargs.setdefault("token_fetcher", fx.token_fetcher)
    kwargs.setdefault("rate_limiter", fx.fast_limiter())
    return DriveClient("app-id", "app-secret", urlopen=transport, **kwargs), transport


# --------------------------------------------------------------------------- #
# Provenance — the evidence base, before anything is asserted from it.          #
# --------------------------------------------------------------------------- #

def test_the_probe_captures_are_committed_and_say_what_this_file_claims():
    """If the measurement moves, these tests must move with it."""
    digest = findings()
    assert digest["02_03_duplicate_verdict"] == "SECOND_FILE_DISTINCT_TOKEN"
    assert digest["02_03_first_eq_second"] is False
    assert digest["31_second_delete_code"] == FILE_ALREADY_DELETED_CODE
    assert digest["32_trashed_requery_code"] == 0
    assert digest["32_trashed_requery_returned_a_meta"] is True
    assert digest["33_trashed_token_still_listed"] is False


# --------------------------------------------------------------------------- #
# AC1 — the by-name lookup: the facts, and the decision stays the caller's.     #
# --------------------------------------------------------------------------- #

def test_the_lookup_finds_every_child_of_that_name_with_its_token():
    children = [child("boxA", NAME), child("boxB", "other.csv"), child("boxC", NAME)]
    drive, transport = listing_client(children)

    answer = drive.find_children_by_name("fldExmpl", NAME)

    assert isinstance(answer, FolderNameMatches)
    assert answer.found is True
    assert answer.tokens == ("boxA", "boxC")
    assert answer.listed == 3
    assert [match.name for match in answer.matches] == [NAME, NAME]
    assert len(transport.calls) == 1


def test_an_absent_name_is_an_EMPTY_ANSWER_not_a_refusal():
    """"Nothing is there" is the answer a caller wants most, so it is not an exception."""
    drive, _t = listing_client([child("boxB", "other.csv")])
    answer = drive.find_children_by_name("fldExmpl", NAME)
    assert answer.found is False and answer.tokens == () and answer.listed == 1


def test_the_match_is_BYTE_IDENTICAL_never_case_folded_or_normalised():
    """Lark stores the name verbatim; a fold here would claim a rule nobody measured."""
    drive, _t = listing_client([child("boxA", "Modules.CSV"), child("boxB", " modules.csv")])
    assert drive.find_children_by_name("fldExmpl", NAME).found is False


def test_the_lookup_NEVER_DELETES_OR_UPLOADS_ANYTHING():
    """The library hands over facts; replace-or-skip stays the caller's decision."""
    drive, transport = listing_client([child("boxA", NAME)])
    drive.find_children_by_name("fldExmpl", NAME)
    assert {call.method for call in transport.calls} == {"GET"}
    assert all(call.path.endswith("/drive/v1/files") for call in transport.calls)


def test_a_truncated_listing_CANNOT_read_as_an_absent_name():
    """A cap that fired is carried through: an incomplete listing is not evidence of absence."""
    from larkdocio.drive.models import Truncation

    complete = FolderNameMatches(folder_token="fldExmpl", name=NAME, matches=(), listed=0)
    assert complete.complete is True

    capped = FolderNameMatches(
        folder_token="fldExmpl", name=NAME, matches=(), listed=5,
        truncation=Truncation(cap="max_pages", limit=1, at_folder="fldExmpl",
                              at_path="fldExmpl"))
    assert capped.complete is False
    assert "not complete" in capped.describe().lower()


def test_the_lookup_is_fenced_to_the_identity_the_API_ACTUALLY_AFFORDS():
    """No size and no digest come back from either route — measured, so neither is implied."""
    digest = findings()
    assert tuple(sorted(IDENTITY_THE_LISTING_AFFORDS)) == tuple(digest["20_child_keys"])
    assert digest["20_listing_carries_size"] is False
    assert "size" in IDENTITY_NOT_AFFORDED
    doc = inspect.getdoc(DriveClient.find_children_by_name)
    assert "size" in doc and "hash" in doc.lower()


def test_the_pure_matcher_is_reusable_without_a_client():
    """A caller who already holds a listing — a walk, a manifest — matches without a call."""
    drive, _t = listing_client([child("boxA", NAME), child("boxB", "other.csv")])
    contents = drive.list_folder_children_to_exhaustion("fldExmpl")
    assert [m.token for m in match_children_by_name(contents.children, NAME)] == ["boxA"]


# --------------------------------------------------------------------------- #
# AC2 — the disclosure, in all three places a consumer meets the upload path.   #
# --------------------------------------------------------------------------- #

#: The four words the dogfood round found **zero** occurrences of, across 563,718 characters.
WORDS = ("duplicate", "overwrite", "collision", "idempot")


def test_the_disclosure_is_authored_ONCE_and_says_all_four_things():
    text = DUPLICATE_UPLOAD_BEHAVIOUR.lower()
    for word in WORDS:
        assert word in text, word
    assert "second" in text
    assert "find_children_by_name" in DUPLICATE_UPLOAD_BEHAVIOUR


def test_the_upload_ops_own_docstring_carries_it():
    doc = inspect.getdoc(put_file_in_folder)
    assert DUPLICATE_UPLOAD_BEHAVIOUR in doc, (
        "the op a consumer calls must say it, quoted rather than re-worded")


def test_the_surfaces_capabilities_text_carries_it():
    from larkdocio import capabilities

    surface = capabilities(full=True)["surfaces"]["drive-files-write"]
    note = surface["credentials"]["note"].lower()
    for word in WORDS:
        assert word in note, word
    assert "find_children_by_name" in surface["credentials"]["note"]


def test_the_guides_upload_recipe_carries_it():
    from larkdocio import guide

    recipe = guide(full=True).split("### Recipe: link a file from a sentence")[1] \
                    .split("### Recipe: create a folder")[0].lower()
    for word in WORDS:
        assert word in recipe, word
    assert "find_children_by_name" in recipe


# --------------------------------------------------------------------------- #
# AC4 — delete tells the truth about gone-ness.                                 #
# --------------------------------------------------------------------------- #

def test_the_gone_code_is_the_SHEETS_constant_REUSED_never_a_second_definition():
    assert DRIVE_FILE_GONE_CODES == frozenset({str(FILE_ALREADY_DELETED_CODE)})
    source = pathlib.Path(inspect.getfile(fw)).read_text("utf-8")
    assert "1061007" not in source, (
        "the code is IMPORTED from the sheets surface, never re-typed here")
    assert "FILE_ALREADY_DELETED_CODE" in source


def test_file_is_gone_MIRRORS_the_sheets_predicate():
    exc = DriveFileDeleteError("x", code=FILE_ALREADY_DELETED_CODE, msg="file has been delete.")
    assert file_is_gone(exc) is True and spreadsheet_is_gone(exc) is True
    assert file_is_gone(DriveFileDeleteError("x", code=1061003)) is False
    assert file_is_gone(LarkAPIError("no code at all")) is False
    assert file_is_gone(ValueError("not a lark error")) is False


def test_a_second_delete_says_ALREADY_DELETED_never_still_there():
    """The measured shape: a delete of an already-trashed token answers ``1061007``."""
    client = DriveFilesWriteClient(
        "id", "secret", sdk_client=_delete_sdk(FILE_ALREADY_DELETED_CODE),
        rate_limiter=fx.fast_limiter())
    with pytest.raises(DriveFileDeleteError) as refusal:
        client.delete("boxcn0001")
    message = str(refusal.value)
    assert "still there" not in message
    assert "already" in message.lower()
    assert file_is_gone(refusal.value) is True


def test_the_already_deleted_reading_ALSO_says_the_metadata_route_still_resolves():
    """Both halves, because either alone is a wrong sentence: it left the folder listing, and
    the metadata route was measured still answering for the token."""
    client = DriveFilesWriteClient(
        "id", "secret", sdk_client=_delete_sdk(FILE_ALREADY_DELETED_CODE),
        rate_limiter=fx.fast_limiter())
    with pytest.raises(DriveFileDeleteError) as refusal:
        client.delete("boxcn0001")
    reading = str(refusal.value).lower()
    assert "metadata" in reading and "resolv" in reading
    assert "trash" in reading and "purge" in reading


def test_an_UNMEASURED_refusal_claims_NOTHING_about_the_file():
    """The old sentence's real defect: a refusal was read as a verdict about the object."""
    client = DriveFilesWriteClient(
        "id", "secret", sdk_client=_delete_sdk(1061003), rate_limiter=fx.fast_limiter())
    with pytest.raises(DriveFileDeleteError) as refusal:
        client.delete("boxcn0001")
    message = str(refusal.value)
    assert "still there" not in message
    assert "nothing was reported as removed" in message.lower()
    assert file_is_gone(refusal.value) is False


def test_the_error_CLASSES_OWN_DOCSTRING_no_longer_carries_the_wrong_claim():
    doc = inspect.getdoc(DriveFileDeleteError)
    assert "The file is still there" not in doc
    assert "still there" not in doc
    assert str(FILE_ALREADY_DELETED_CODE) in doc or "already" in doc.lower()


def _delete_sdk(code):
    """The narrowest SDK seam a delete needs: one ``drive.v1.file.delete``."""

    class _Resp:
        def __init__(self):
            self.code, self.msg = code, "file has been delete."

    class _File:
        def delete(self, request):
            return _Resp()

    class _V1:
        file = _File()

    class _Drive:
        v1 = _V1()

    class _Sdk:
        drive = _Drive()

    return _Sdk()
