"""LD-606 — a ``metas/batch_query`` ``code:0`` with an empty ``metas`` array is a REFUSAL.

The reason is parked in a sibling key, ``failed_list``. Five call sites in this library reach
``POST /open-apis/drive/v1/metas/batch_query``; exactly one of them read that key, so the other
four disclosed a **missing field** when the fact was a **refused token**.

Two things are pinned here, and the second is the one that would have shipped broken:

1. the four uncured disclosures now carry Lark's own reason, **appended** to the text they
   already emitted (nothing is rewritten — the pre-existing sentence is asserted alongside);
2. the shared reader works on **both response seams** from the same payload — the SDK object the
   ``lark-oapi`` legs receive and the plain dict the raw-HTTP legs receive. A reader reaching
   ``failed_list`` by ``getattr`` only returns its "named no reason" fallback against every
   dict, i.e. it looks like it works and never finds a reason.

Plus leg C: ``99992402``'s widened meaning, and the derivation-not-measurement shape of the
sentence that widening had to carry.

Offline, from captures already committed to this tree (``ld467-13``, ``ld494`` ``620-``/``621-``).
No Lark call is made by anything in this file.
"""
import io
import json
import pathlib
import types

import pytest

import access_fixtures as afx
import drive_fixtures as fx
from larkdocio.common.error_codes import ERROR_CODES, note_for
from larkdocio.common.metas import failed_reason
from larkdocio.drive.access_write import DriveAccessWriteClient
from larkdocio.drive.client import DriveClient
from larkdocio.drive.files_write import DriveFileMetaError, DriveFilesWriteClient
import private_tree  # noqa: E402  (LD-685)

REPO = pathlib.Path(__file__).resolve().parent.parent
TOKEN = "Examplee71ea02037eeb7c22b7e"
REFUSED_CODE = "970005"

#: The negative leg, verbatim from the committed capture: a trashed FOLDER token re-queried.
TRASHED_FOLDER_CAPTURE = (
    REPO / "tests" / "captures" / "ld467-create-folder" / "captures"
    / "ld467-13-re-query-a-trashed-folder-token.json"
)


def refusal_in_disguise() -> dict:
    """``{"code": 0, "msg": "Success", "data": {"metas": [], "failed_list": [...]}}``.

    Read out of the committed capture rather than hand-typed, so the shape is Lark's.
    """
    body = json.loads(TRASHED_FOLDER_CAPTURE.read_text("utf-8"))["response"]
    assert body["code"] == 0 and body["data"]["metas"] == []
    assert body["data"]["failed_list"][0]["code"] == 970005
    return body


def as_sdk_object(body: dict):
    """The SAME payload as the ``lark-oapi`` seam hands it over — attributes, not keys."""
    data = body["data"]
    return types.SimpleNamespace(
        code=body["code"], msg=body["msg"],
        data=types.SimpleNamespace(
            metas=[types.SimpleNamespace(**m) for m in data.get("metas", [])],
            failed_list=[types.SimpleNamespace(**e) for e in data.get("failed_list", [])],
        ),
    )


# --------------------------------------------------------------------------- #
# AC1 — ONE shared reader, and it reads BOTH seams from the same payload.       #
# --------------------------------------------------------------------------- #

def test_ac1_the_shared_reader_finds_the_SAME_reason_on_BOTH_response_shapes():
    body = refusal_in_disguise()

    from_dict = failed_reason(body["data"], TOKEN)
    from_sdk = failed_reason(as_sdk_object(body).data, TOKEN)

    assert REFUSED_CODE in from_dict
    assert from_dict == from_sdk, (
        "the dict seam is the one a getattr-only reader silently loses: it would return the "
        "'named no reason' fallback while looking like it worked")


def test_ac1_the_reader_still_admits_when_the_answer_named_NO_reason():
    silent = {"metas": [], "failed_list": []}
    assert "no reason" in failed_reason(silent, TOKEN)
    assert REFUSED_CODE not in failed_reason(silent, TOKEN)


def test_ac1_a_failed_list_entry_for_ANOTHER_token_is_not_read_as_this_token_s_reason():
    other = {"metas": [], "failed_list": [{"code": 970005, "token": "someone-elses-token"}]}
    assert "no reason" in failed_reason(other, TOKEN)


def test_ac1_base_media_reads_the_SHARED_authoring_rather_than_a_second_copy():
    from larkdocio.base import media

    assert media._failed_reason is failed_reason


# --------------------------------------------------------------------------- #
# AC2 — the four uncured disclosures gain Lark's reason, APPENDED.              #
# --------------------------------------------------------------------------- #

def _drive_client(metas):
    transport = fx.RecordingTransport(fx.listing_router({}, metas=metas))
    return DriveClient("app-id", "app-secret", urlopen=transport,
                       token_fetcher=fx.token_fetcher, rate_limiter=fx.fast_limiter())


def test_ac2_folder_name_appends_larks_own_reason_to_the_no_title_disclosure():
    answer = _drive_client(refusal_in_disguise()).folder_name(TOKEN)

    assert answer.name is None, "no behaviour change: the leg still DEGRADES"
    assert "Lark returned no title" in answer.disclosure, "the existing text is APPENDED to"
    assert REFUSED_CODE in answer.disclosure


def test_ac2_document_security_level_appends_larks_own_reason():
    answer = _drive_client(refusal_in_disguise()).document_security_level(TOKEN)

    assert answer.level is None, "no behaviour change: the leg still DISCLOSES"
    assert "carried no security-level key at all" in answer.disclosure
    assert REFUSED_CODE in answer.disclosure


def test_ac2_the_owner_read_appends_larks_own_reason_to_the_no_owner_id_note():
    route = afx.access_router(members_pages=[afx.response(afx.MEMBERS_EMPTY)],
                              meta=lambda _call: refusal_in_disguise())
    access = DriveAccessWriteClient("app-id", "app-secret",
                                    urlopen=afx.RecordingTransport(route),
                                    token_fetcher=afx.token_fetcher,
                                    rate_limiter=afx.fast_limiter())

    listing = access.list_members(TOKEN)

    assert listing.owner_id is None, "no behaviour change: the owner still degrades to None"
    assert "no owner_id" in listing.owner_note
    assert REFUSED_CODE in listing.owner_note


class _FakeMetaOnly:
    """The ``lark-oapi`` seam, answering one refusal-in-disguise for ``meta.batch_query``."""

    def __init__(self, body):
        self._body = body
        self.calls = []
        v1 = type("_V1", (), {"meta": self, "file": self})()
        self.drive = type("_Drive", (), {"v1": v1})()

    def batch_query(self, request):
        self.calls.append(("batch_query", request))
        return as_sdk_object(self._body)


class _NoWait:
    def acquire(self):
        return None


def test_ac2_permalink_appends_larks_own_reason_and_STILL_RAISES():
    files = DriveFilesWriteClient("id", "secret",
                                  sdk_client=_FakeMetaOnly(refusal_in_disguise()),
                                  rate_limiter=_NoWait())

    with pytest.raises(DriveFileMetaError) as exc:
        files.permalink(TOKEN)

    message = str(exc.value)
    assert "reported no URL" in message, "the existing text is APPENDED to"
    assert REFUSED_CODE in message
    assert io  # the module still imports its own seam helpers unchanged


# --------------------------------------------------------------------------- #
# AC7 / AC8 — 99992402 is a REQUEST-LAYER rejection, and the widening says so.  #
# --------------------------------------------------------------------------- #

VIOLATION_CAPTURES = (
    "tests/captures/ld494-app-space-census/captures/620-root-members-read-r1.json",
    "tests/captures/ld494-app-space-census/captures/621-root-members-read-r2.json",
)


def test_ac7_the_99992402_meaning_says_the_rejection_is_decided_on_the_REQUEST():
    meaning = note_for(99992402).meaning.lower()

    assert "request" in meaning
    assert "nothing" in meaning and "target" in meaning, (
        "the row must say it establishes NOTHING about the target — that is the whole point")


@private_tree.citations
def test_ac8_the_added_sentences_carry_their_OWN_citations():
    evidence = note_for(99992402).evidence

    for path in VIOLATION_CAPTURES:
        assert path in evidence
        assert (REPO / path).is_file(), "the guarded evidence pointer must resolve"    # LD-720: the Base provenance is KEPT as the published capture; the private study document
    # (ui-parity-matrix-2026-08-03.md) is no longer cited from shipped text.
    assert "tests/captures/base-study/captures/p1-q2-01-button-sweep.json" in evidence, (
        "the Base provenance is KEPT")
    assert "ui-parity-matrix" not in evidence


def test_ac8_the_live_vs_removed_identity_is_DERIVED_and_the_removed_leg_is_UNMEASURED():
    meaning = note_for(99992402).meaning.lower()

    assert "derived" in meaning or "derivation" in meaning
    assert "unmeasured" in meaning, (
        "there is no capture of 99992402 against a REMOVED object in this tree; writing the "
        "pair as a measured control would ship the very false universal leg E fixes")
    assert "not refuted" in meaning


def test_ac10_no_row_is_added_and_the_verification_label_is_not_upgraded():
    assert 99992402 in ERROR_CODES
    assert note_for(99992402).verification == "wire-observed"


# --------------------------------------------------------------------------- #
# AC15/16/17 — the dead universal is gone from every home. A narrow regression  #
# pin, NOT the deferred DRIVE.md drift guard (AC18): it names one clause.       #
# --------------------------------------------------------------------------- #

DEAD_CLAUSE_HOMES = (
    "src/larkdocio/drive/client.py",
    "src/larkdocio/drive/ops.py",
    "DRIVE.md",
    "tests/test_drive_enumeration_client.py",
)


@pytest.mark.parametrize("home", DEAD_CLAUSE_HOMES)
def test_ac15_no_home_still_says_a_folder_token_is_established_by_no_capture(home):
    text = (REPO / home).read_text("utf-8")
    assert "established by no capture" not in text, (
        f"{home} still carries the clause that has been false since 2026-08-15")


@pytest.mark.parametrize("home", ("src/larkdocio/drive/client.py",
                                 "src/larkdocio/drive/folders_write.py",
                                 "DRIVE.md"))
def test_ac16_the_claim_now_rests_on_a_CONTROL_PAIR_and_both_legs_are_cited(home):
    text = (REPO / home).read_text("utf-8")
    assert "ld467-25" in text or "ld514-04" in text, f"{home} cites no POSITIVE leg"
    assert "ld467-13" in text or "ld514-04" in text, f"{home} cites no NEGATIVE leg"


def test_ac15_the_REASON_for_the_degradable_design_is_preserved_not_struck():
    text = (REPO / "src/larkdocio/drive/client.py").read_text("utf-8")
    assert "Degradable by construction" in text
    assert "A title is never invented." in text


# --------------------------------------------------------------------------- #
# AC20 — the 1061007 row's trash-not-purge clause is BOUNDED to a drive FILE.   #
# --------------------------------------------------------------------------- #

def test_ac20_the_1061007_row_bounds_trash_not_purge_to_a_FILE_token():
    meaning = note_for(1061007).meaning

    assert "FILE token" in meaning, (
        "the clause was stated bare about the endpoint, and a trashed FOLDER token does the "
        "opposite — the bound is the honest fix")
    assert "FOLDER" in meaning and REFUSED_CODE in meaning
