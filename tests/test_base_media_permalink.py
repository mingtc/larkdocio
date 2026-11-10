"""LD-450 — an Attachment cell's ``file_token`` turned into the ``/file/`` permalink a human
can be sent, offline, against the LD-436 parity captures.

Three things are pinned here, and they are different kinds of claim:

1. **the measured shape** — ``POST /open-apis/drive/v1/metas/batch_query`` with
   ``doc_type: file`` and ``with_url: true`` answers a ``/file/`` URL and the file's own
   ``title`` for **both** shipped ``parent_type`` spellings' tokens (capture ``113-``);
2. **THE SWALLOW** — the same endpoint answers ``code:0 Success`` with an **empty** ``metas``
   and the reason in ``failed_list`` for a wrong ``doc_type`` or a token that was never minted
   (``116-``, ``117-``, and ``113-``'s own in-call falsifier). *A ``code:0`` here is not a
   permalink*, and the op must refuse rather than report success on an empty answer — this is
   the exact class of defect the library's *"an accepted call is not a stored one"* discipline
   exists for;
3. **the caveat that makes it honest** — the permalink **outlives the bytes' reachability**
   (``132-``: after the parent Base was deleted both permalinks still resolve, while the bytes
   answer HTTP 404), and a permalink **grants nobody access**.

Conformance-tier: the tests that pin (1), (2) and (3) pin **measured external truth**
(``process/doctrine/conformance-tier.md`` § A.4) and carry ``pytest.mark.conformance``. The
plumbing — local refusals, the never-invent-a-URL rule, the declaration and the shipped text —
is ordinary regression and is deliberately unmarked.

**No Lark numeric code is written into an assertion here** (LD-417 AC10): where a refusal must
carry Lark's own reason, the number is read out of the capture at run time, so the test proves
the reason travelled rather than re-asserting a constant nobody can check.
"""
import copy
import pathlib
import re

import pytest

from base_media_parity_captures import (
    AFTER_THE_PARENT_DIED,
    BOGUS_TOKEN,
    FILE_TOKEN,
    IMAGE_TOKEN,
    PERMALINKS,
    WRONG_DOC_TYPE_BITABLE,
    WRONG_DOC_TYPE_DOCX,
    meta_response,
    payload,
    request_body,
    response_from,
)
import capability_rows as rows
from larkdocio.base import media
from larkdocio.base.media import (
    BaseMediaClient,
    MediaPermalink,
    MediaPermalinkError,
    MediaPermalinkNotResolvedError,
)
from larkdocio.base.media import MEDIA_TOKEN_NOT_INDEPENDENTLY_SHAREABLE as SHAREABILITY
from larkdocio.drive.ops import METAS_BATCH_QUERY_ENDPOINT
from guard_kit import REPO_ROOT

SRC = REPO_ROOT / "src" / "larkdocio"


# --------------------------------------------------------------------------- #
# The fake seam — the SDK's meta leg, answering a captured payload.            #
# --------------------------------------------------------------------------- #

class _FakeMeta:
    def __init__(self, answers):
        self.answers = list(answers)
        self.requests = []

    def batch_query(self, request):
        self.requests.append(request)
        assert self.answers, "the client queried the meta family once too often"
        return self.answers.pop(0)


class _FakeSDK:
    def __init__(self, fake_meta):
        self.drive = type("drive", (), {"v1": type("v1", (), {"meta": fake_meta})()})()


class _Limiter:
    def __init__(self):
        self.acquired = 0

    def acquire(self):
        self.acquired += 1


def _permalink_client(*answers):
    fake = _FakeMeta(answers)
    limiter = _Limiter()
    return BaseMediaClient("id", "secret", sdk_client=_FakeSDK(fake),
                           rate_limiter=limiter), fake, limiter


def _unwrapped(path: pathlib.Path) -> str:
    """Prose wrapped at 95 columns is still one sentence — read it as one."""
    return re.sub(r"\s+", " ", path.read_text("utf-8"))


# --------------------------------------------------------------------------- #
# AC1 — one operation, the existing endpoint, both shipped spellings.          #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_ac1_the_request_is_the_CAPTURED_shape_on_the_EXISTING_endpoint():
    """The identical request the spike sent — and the endpoint constant the drive leg
    already authored, imported rather than re-spelled."""
    client, fake, limiter = _permalink_client(meta_response(PERMALINKS))
    client.permalink(IMAGE_TOKEN)
    (request,) = fake.requests
    assert request.uri == METAS_BATCH_QUERY_ENDPOINT
    captured = request_body(PERMALINKS)
    assert request.request_body.with_url is captured["with_url"] is True
    (doc,) = request.request_body.request_docs
    assert doc.doc_token == IMAGE_TOKEN
    assert doc.doc_type == media.MEDIA_META_DOC_TYPE
    assert doc.doc_type == captured["request_docs"][0]["doc_type"]
    assert limiter.acquired == 1, "every call on this client passes the shared limiter"
    assert client.api_calls == 1


@pytest.mark.conformance
@pytest.mark.parametrize("token,title", [
    (IMAGE_TOKEN, "ld436-parity.png"),      # the bitable_image spelling's token
    (FILE_TOKEN, "ld436-parity.html"),      # the bitable_file spelling's token
])
def test_ac1_BOTH_shipped_spellings_resolve_to_a_file_permalink_and_a_title(token, title):
    client, _fake, _limiter = _permalink_client(meta_response(PERMALINKS))
    link = client.permalink(token)
    assert isinstance(link, MediaPermalink)
    assert link.file_token == token
    assert link.title == title
    assert link.url.endswith(f"/file/{token}")
    assert link.url == _captured_url(token)


def _captured_url(token):
    metas = payload(PERMALINKS)["data"]["metas"]
    return [meta["url"] for meta in metas if meta["doc_token"] == token][0]


@pytest.mark.conformance
def test_ac1_the_answer_is_MATCHED_BY_TOKEN_and_not_taken_positionally():
    """Capture ``113-`` returns the two metas in the OPPOSITE order to the request.

    A leg that took ``metas[0]`` would hand a caller the other file's address under their own
    token — the quietest possible wrong answer, and the reason the match is by ``doc_token``.
    """
    metas = payload(PERMALINKS)["data"]["metas"]
    assert [meta["doc_token"] for meta in metas] != [IMAGE_TOKEN, FILE_TOKEN]
    client, _fake, _limiter = _permalink_client(meta_response(PERMALINKS))
    assert client.permalink(IMAGE_TOKEN).title == "ld436-parity.png"


# --------------------------------------------------------------------------- #
# AC2 — THE SWALLOW. A code:0 is not a permalink.                              #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
@pytest.mark.parametrize("capture", [WRONG_DOC_TYPE_BITABLE, WRONG_DOC_TYPE_DOCX],
                         ids=["doc_type=bitable", "doc_type=docx"])
def test_ac2_an_EMPTY_SUCCESS_is_REFUSED_rather_than_reported_as_a_permalink(capture):
    """The measured swallow: ``code:0 Success``, ``metas: []``, the reason in ``failed_list``."""
    body = payload(capture)
    assert body["code"] == 0 and body["msg"] == "Success", body
    assert body["data"]["metas"] == [], "the capture must be the EMPTY success, or this proves nothing"

    client, _fake, _limiter = _permalink_client(meta_response(capture))
    with pytest.raises(MediaPermalinkNotResolvedError) as caught:
        client.permalink(IMAGE_TOKEN)
    assert IMAGE_TOKEN in str(caught.value)
    assert str(body["data"]["failed_list"][0]["code"]) in str(caught.value), (
        "the refusal must carry LARK's own reason, not only this library's opinion")


@pytest.mark.conformance
def test_ac2_a_token_that_was_NEVER_MINTED_is_refused_with_larks_reason():
    """``113-``'s in-call falsifier — the same answer that carried two real permalinks."""
    client, _fake, _limiter = _permalink_client(meta_response(PERMALINKS))
    with pytest.raises(MediaPermalinkNotResolvedError) as caught:
        client.permalink(BOGUS_TOKEN)
    message = str(caught.value)
    assert BOGUS_TOKEN in message
    failed = payload(PERMALINKS)["data"]["failed_list"][0]
    assert failed["token"] == BOGUS_TOKEN
    assert str(failed["code"]) in message


def test_ac2_the_refusal_is_a_TYPED_member_of_the_media_family():
    """A caller catching the media family catches this; a caller catching the permalink
    refusal catches only it."""
    assert issubclass(MediaPermalinkNotResolvedError, MediaPermalinkError)
    assert issubclass(MediaPermalinkError, media.BaseMediaError)


def test_ac2_the_swallow_is_DISCLOSED_where_the_op_is_read():
    doc = BaseMediaClient.permalink.__doc__
    assert media.WRONG_DOC_TYPE_IS_AN_EMPTY_ANSWER in doc
    assert "not a permalink" in media.WRONG_DOC_TYPE_IS_AN_EMPTY_ANSWER


def test_a_success_with_NO_URL_raises_rather_than_constructing_one():
    """Nobody has captured this; the op still refuses to invent an address.

    Derived from ``113-`` by removing the ``url`` key — an edit of a real payload, stated in
    the loader, never a hand-authored dict. A URL this library assembled from a host and a
    token would be a guess wearing the shape of an answer.
    """
    body = copy.deepcopy(payload(PERMALINKS))
    for meta in body["data"]["metas"]:
        meta.pop("url")
    client, _fake, _limiter = _permalink_client(response_from(body))
    with pytest.raises(MediaPermalinkError) as caught:
        client.permalink(IMAGE_TOKEN)
    assert "never constructed" in str(caught.value)


def test_a_NON_ZERO_answer_raises_typed_and_carries_larks_code():
    """Also uncaptured: this endpoint has never been seen refusing a media token."""
    body = copy.deepcopy(payload(PERMALINKS))
    body["code"] = 1061003
    body["msg"] = "not found"
    client, _fake, _limiter = _permalink_client(response_from(body))
    with pytest.raises(MediaPermalinkError) as caught:
        client.permalink(IMAGE_TOKEN)
    assert str(body["code"]) in str(caught.value)


def test_an_EMPTY_token_is_refused_LOCALLY_before_any_call():
    client, fake, _limiter = _permalink_client()
    with pytest.raises(MediaPermalinkError):
        client.permalink("")
    assert fake.requests == [], "a local refusal must make no call"


# --------------------------------------------------------------------------- #
# AC3 — the permalink OUTLIVES the bytes' reachability.                        #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_ac3_the_permalink_STILL_RESOLVES_after_the_parent_base_was_deleted():
    """Capture ``132-`` — the caveat's own evidence, run through the shipped op.

    The op happily returns an address for content whose bytes answer HTTP 404. That is not a
    bug to fix: it is the fact the disclosure exists to state, and the reason a resolving
    permalink is **not** evidence that the file is still there.
    """
    body = payload(AFTER_THE_PARENT_DIED)
    assert body["data"].get("failed_list") is None, body
    for token in (IMAGE_TOKEN, FILE_TOKEN):
        client, _fake, _limiter = _permalink_client(meta_response(AFTER_THE_PARENT_DIED))
        assert client.permalink(token).url.endswith(f"/file/{token}")


@pytest.mark.parametrize("needle", [
    "OUTLIVES",
    "404",
    "cannot tell from the permalink whether the bytes are still there",
    "verify_round_trip",
])
def test_ac3_the_caveat_says_the_whole_thing(needle):
    assert needle in media.PERMALINK_OUTLIVES_THE_BYTES


def test_ac3_the_caveat_ships_in_the_ops_own_docstring():
    assert media.PERMALINK_OUTLIVES_THE_BYTES in BaseMediaClient.permalink.__doc__
    assert "<<" not in BaseMediaClient.permalink.__doc__, "an unreplaced marker shipped"


def test_ac3_the_caveat_ships_in_the_GUIDE():
    guide = _unwrapped(SRC / "GUIDE.md")
    assert "outlives the bytes" in guide.lower()
    assert "a permalink that resolves is not evidence the bytes are there" in guide.lower()


def test_ac3_NOTHING_SHIPPED_says_the_link_proves_the_file_exists():
    """The failure mode this caveat exists against, guarded rather than trusted."""
    for path in list(SRC.rglob("*.py")) + [SRC / "GUIDE.md", REPO_ROOT / "BASE.md"]:
        text = _unwrapped(path).lower()
        for claim in ("the permalink proves the file exists",
                      "a permalink proves the bytes",
                      "if the permalink resolves the file is there"):
            assert claim not in text, f"{path}: {claim}"


# --------------------------------------------------------------------------- #
# AC4 / AC5 — a permalink grants nobody access, and the disclosure is CITED.   #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("needle", [
    "grants nobody access",
    "not a credential",
    "302",
    "not a proof of human openability",
    "never widens, requests or escalates a scope",
])
def test_ac4_the_not_access_text_says_the_whole_thing(needle):
    assert needle in media.PERMALINK_IS_NOT_ACCESS


def test_ac5_the_shareability_disclosure_is_QUOTED_not_re_authored():
    """The single authoring is ``MEDIA_TOKEN_NOT_INDEPENDENTLY_SHAREABLE`` (LD-442 widened it
    to the parent-bound token, so the Base voice is already in it). This op cites it."""
    assert SHAREABILITY in media.PERMALINK_IS_NOT_ACCESS
    assert "BASE-BOUND" in SHAREABILITY, "the widened (LD-442) text is what is being cited"


def test_ac4_the_not_access_text_ships_in_the_ops_own_docstring_and_the_guide():
    assert media.PERMALINK_IS_NOT_ACCESS in BaseMediaClient.permalink.__doc__
    guide = _unwrapped(SRC / "GUIDE.md")
    assert "grants nobody access" in guide.lower()


# --------------------------------------------------------------------------- #
# AC6 — negative claims, scoped to what was tried.                             #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("needle", [
    "one tenant",
    "tenant_access_token",
    "user_access_token",
    "UNMEASURED",
    "restore",
    "click",
])
def test_ac6_the_edge_of_the_evidence_is_named(needle):
    text = media.PERMALINK_OUTLIVES_THE_BYTES + " " + media.PERMALINK_IS_NOT_ACCESS
    assert needle in text


def test_ac6_the_human_click_is_recorded_UNMEASURED_and_not_claimed():
    text = (media.PERMALINK_OUTLIVES_THE_BYTES + " " + media.PERMALINK_IS_NOT_ACCESS).lower()
    assert "unmeasured" in text
    assert "a click is not a probe" in text


# --------------------------------------------------------------------------- #
# AC7 / AC8 — the declaration, the permission row, and the matrices.           #
# --------------------------------------------------------------------------- #

def test_ac7_the_new_call_site_has_a_permission_row_on_the_existing_endpoint():
    from larkdocio.permissions import coverage_gaps, permission_registry, undeclared_endpoints

    rows = permission_registry()
    row = rows[("base-write", "permalink_attachment_media")]
    assert row.endpoints == (METAS_BATCH_QUERY_ENDPOINT,)
    assert row.api_using
    gaps = coverage_gaps(rows=rows)
    assert (gaps.uncovered, gaps.orphans) == ([], [])
    assert [site for site in undeclared_endpoints()
            if "base.media" in site[0]] == []


def test_ac8_capabilities_reports_the_leg_beside_the_two_it_belongs_with():
    from larkdocio import capabilities

    legs = [leg["name"]
            for leg in rows.call_sites(capabilities(full=True)["surfaces"]["base-write"], rows.LEG)]
    assert legs == ["upload_attachment_media", "download_attachment_media",
                    "permalink_attachment_media"]


def test_ac8_BASE_md_carries_the_permalink_beat_with_its_caveat():
    base_md = _unwrapped(REPO_ROOT / "BASE.md")
    assert "permalink_attachment_media" in base_md, "the shipped op has no row"
    assert "metas/batch_query` with `doc_type: file" in base_md
    assert "outlives the bytes" in base_md.lower()
    assert "grants nobody access" in base_md.lower()
    assert "tests/test_base_media_permalink.py" in base_md
    assert "dev/base-media-parity-spike" in base_md
