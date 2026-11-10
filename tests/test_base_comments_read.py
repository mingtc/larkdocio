"""Base comments — the read half, its record attribution, and the write half's CANNOT.

Every test here is **offline**, against two committed captures of one real Base:

* ``p1-q7-01-comments-populated.json`` — the populated list, captured read-only for this
  story because the earlier pack could only capture the empty state;
* ``p1-q4-01-comments.json`` — the empty state, and the four server refusals that make the
  write half a documented CANNOT.

**The capture corrected the prose it was taken to confirm.** The claim on record was that
``extra.notify_extra`` carries ``record_id`` / ``table_id`` / ``view_id``. The wire carries
the same three ids under the keys **``record`` / ``table`` / ``view``**. The values are what
the claim said they were — they join to the very record and table the earlier pack probed —
so the finding stands and only its spelling was wrong. The never-observed ``*_id`` spelling
is therefore **not** accepted by the code, and a test below pins that: accepting a shape no
server has sent is how a projection starts inventing.
"""
import json
import re
from pathlib import Path

import pytest

from larkdocio import comments as C
from larkdocio.comments import attribution as A
import comments_harness as H

from guard_kit import REPO_ROOT
import private_tree  # noqa: E402  (LD-685)

_CAPTURES = REPO_ROOT / "tests" / "captures" / "base-study" / "captures"
_POPULATED = "p1-q7-01-comments-populated.json"
_EMPTY = "p1-q4-01-comments.json"


def _capture(name):
    return json.loads((_CAPTURES / name).read_text(encoding="utf-8"))


def _populated_body():
    """The one response body the populated capture holds."""
    return _capture(_POPULATED)["steps"][0]["response"]


def _empty_body():
    """The empty-state body: the first step of the earlier pack's sweep."""
    return _capture(_EMPTY)["steps"][0]["response"]


def _read(body, **kwargs):
    """Read a Base's comments offline, straight through the shipped entry point."""
    client = H.client({"list": body})
    return C.comments("BaseScratchExample000000001",
                      file_type=C.FILE_TYPE_BITABLE, client=client, **kwargs), client


# --------------------------------------------------------------------------- #
# AC1 — the capture, its provenance, and the wire keys it corrected.            #
# --------------------------------------------------------------------------- #

def test_ac1_the_capture_is_committed_read_only_and_bitable():
    cap = _capture(_POPULATED)
    assert cap["_read_only"] is True
    step = cap["steps"][0]
    assert step["_method"] == "GET"
    assert step["_lark_code"] == 0
    assert "file_type=bitable" in step["_note"]
    assert "/drive/v1/files/" in step["_endpoint"]
    assert step["_endpoint"].endswith("/comments")


def test_ac1_the_capture_is_the_repositorys_FIRST_notify_extra_for_a_bitable_read():
    """The gap AC1 was written to close: prose, with no payload behind it."""
    assert "notify_extra" in (_CAPTURES / _POPULATED).read_text(encoding="utf-8")
    assert "notify_extra" not in (_CAPTURES / _EMPTY).read_text(encoding="utf-8")


def test_ac1_THE_WIRE_KEYS_ARE_record_table_view_NOT_record_id():
    """The discrepancy, pinned. The capture wins over the prose."""
    extra = _populated_body()["data"]["items"][0]["reply_list"]["replies"][0]["extra"]
    assert sorted(extra["notify_extra"]) == ["record", "table", "view"]
    assert (A.WIRE_KEY_RECORD, A.WIRE_KEY_TABLE, A.WIRE_KEY_VIEW) == (
        "record", "table", "view")


def test_ac1_the_ids_in_notify_extra_JOIN_to_the_records_the_earlier_pack_probed():
    """Why this is a spelling correction and not a refutation: same record, same table."""
    extra = _populated_body()["data"]["items"][0]["reply_list"]["replies"][0]["extra"]
    probed = (_CAPTURES / _EMPTY).read_text(encoding="utf-8")
    assert extra["notify_extra"]["record"] in probed
    assert extra["notify_extra"]["table"] in probed


def test_ac1_the_never_observed_id_spelling_is_NOT_accepted():
    """A shape no server has sent is not a shape this projection reads."""
    assert A.attribution_from_extra(
        {"notify_extra": {"record_id": "rec1", "table_id": "tbl1", "view_id": "vew1"}}
    ) is None


# --------------------------------------------------------------------------- #
# AC2 — one comments client, one entry point.                                   #
# --------------------------------------------------------------------------- #

def test_ac2_bitable_is_an_accepted_file_type_on_the_read_path():
    assert C.FILE_TYPE_BITABLE == "bitable"
    read, client = _read(_populated_body())
    assert read.available is True
    assert read.file_type == "bitable"


def test_ac2_a_base_read_goes_through_the_SHIPPED_comments_client():
    read, client = _read(_populated_body())
    assert isinstance(client, C.CommentsReadClient)
    assert client._sdk.paths == [H.PATHS["list"]]
    assert client._sdk.requests_for("list")[0].file_type == "bitable"


def test_ac2_there_is_exactly_ONE_comments_client_class_in_the_package():
    """No second client was born for this file type."""
    root = Path(C.__file__).resolve().parent
    hits = []
    for path in sorted(root.rglob("*.py")):  # LD-654: recursive population
        hits += re.findall(r"^class (\w*Client)\b", path.read_text(encoding="utf-8"),
                           re.MULTILINE)
    assert hits == ["CommentsReadClient"], hits


def test_ac2_the_dev_call_is_recorded_in_the_module_docstring():
    """AC2 requires the shape decision to be written down where it is implemented."""
    assert "notify_extra" in (A.__doc__ or "")


# --------------------------------------------------------------------------- #
# AC3 — attribution off `extra.notify_extra`, and the typed absence path.       #
# --------------------------------------------------------------------------- #

def test_ac3_i_an_attributed_thread_carries_record_table_and_view_to_the_surface():
    read, _ = _read(_populated_body())
    comment = read.comments[0]
    attribution = comment.attribution
    assert attribution == A.BaseAttribution(
        record_id="rec88HpEvHGLV4", table_id="tblYtWUpf5q944Ao", view_id="vewN5yTV1k")
    assert comment.attribution_state == A.ATTRIBUTION_RECORD
    assert comment.replies[0].attribution == attribution
    # structured data, not a string to re-parse
    assert attribution.record_id == "rec88HpEvHGLV4"


def test_ac3_i_the_attribution_survives_a_to_dict_round_trip():
    read, _ = _read(_populated_body())
    wire = read.to_dict()
    assert wire["comments"][0]["attribution"] == {
        "record_id": "rec88HpEvHGLV4", "table_id": "tblYtWUpf5q944Ao",
        "view_id": "vewN5yTV1k"}
    back = C.CommentsRead.from_dict(wire)
    assert back.comments[0].attribution == read.comments[0].attribution


def _body_with_extra(extra):
    """The populated body with its one reply's `extra` replaced."""
    body = _populated_body()
    body["data"]["items"][0]["reply_list"]["replies"][0]["extra"] = extra
    return body


def test_ac3_ii_a_thread_with_no_notify_extra_is_typed_FILE_LEVEL():
    read, _ = _read(_body_with_extra({"image_list": []}))
    comment = read.comments[0]
    assert comment.attribution is None
    assert comment.attribution_state == A.ATTRIBUTION_FILE_LEVEL
    assert A.ATTRIBUTION_FILE_LEVEL == "file-level"
    # named and typed — never silently attributed, never dropped
    assert len(read.comments) == 1


def test_ac3_iii_a_notify_extra_MISSING_the_record_key_does_not_half_attribute():
    read, _ = _read(_body_with_extra(
        {"image_list": [], "notify_extra": {"table": "tblYtWUpf5q944Ao",
                                            "view": "vewN5yTV1k"}}))
    comment = read.comments[0]
    assert comment.attribution is None
    assert comment.attribution_state == A.ATTRIBUTION_FILE_LEVEL


def test_ac3_iii_a_notify_extra_that_is_not_even_a_mapping_does_not_crash():
    for junk in (None, [], "record", 7):
        assert A.attribution_from_extra({"notify_extra": junk}) is None
    assert A.attribution_from_extra(None) is None
    assert A.attribution_from_extra({}) is None


def test_ac3_the_table_and_view_may_be_absent_without_losing_the_record():
    """The record id is the attribution key; the other two are context."""
    got = A.attribution_from_extra({"notify_extra": {"record": "recX"}})
    assert got == A.BaseAttribution(record_id="recX", table_id=None, view_id=None)


def test_ac3_the_shipped_docx_reply_projection_still_drops_nothing_it_carried():
    """Zero-drift on the two shipped file types: image tokens still arrive."""
    body = _body_with_extra({"image_list": ["img-token-1"]})
    read, _ = _read(body)
    assert read.comments[0].replies[0].image_tokens == ("img-token-1",)


# --------------------------------------------------------------------------- #
# AC4 — the typed absence, in the register the surface already uses.            #
# --------------------------------------------------------------------------- #

def test_ac4_the_empty_state_is_the_surfaces_documented_no_comments_result():
    read, _ = _read(_empty_body())
    assert read.available is True
    assert read.comments == ()
    assert read.completeness == C.COMPLETENESS_COMPLETE
    assert read.disclosure.startswith(
        "No comments on BaseScratchExample000000001 (bitable) — the read succeeded and "
        "found none.")


def test_ac4_the_empty_state_is_NOT_an_error_and_NOT_silence():
    read, _ = _read(_empty_body())
    assert read.unavailable_code is None and read.unavailable_reason is None
    assert read.notes  # the Base disclosures still ship on an empty read


def test_ac4_the_register_matches_the_one_a_document_with_none_gets():
    """Same words for a docx and for a Base — only the file type differs."""
    docx, _ = H.client({"list": _empty_body()}), None
    empty_docx = C.comments("doccnDocToken", client=docx)
    assert empty_docx.disclosure.split(" — ")[1].startswith(
        "the read succeeded and found none.")


# --------------------------------------------------------------------------- #
# AC5 — the write half is a hard, documented CANNOT.                            #
# --------------------------------------------------------------------------- #

def test_ac5_the_surface_exposes_NO_path_to_commenting_a_base():
    root = Path(C.__file__).resolve().parent
    forbidden = re.compile(r"def (create|add|post|reply|resolve|delete)_\w*comment")
    for path in sorted(root.rglob("*.py")):  # LD-654: recursive population
        assert not forbidden.search(path.read_text(encoding="utf-8")), path.name


def test_ac5_the_refusal_names_the_servers_OWN_enum():
    note = C.BASE_COMMENT_WRITE_REFUSED_NOTE
    assert "[doc, docx]" in note or "[doc,docx]" in note
    assert "bitable" in note


def test_ac5_the_refusal_does_NOT_advise_requesting_a_scope():
    note = C.BASE_COMMENT_WRITE_REFUSED_NOTE.lower()
    for advice in ("scope", "permission", "grant", "authoriz", "authoris"):
        assert advice not in note, advice


def test_ac5_the_refusal_is_disclosed_on_every_base_read():
    read, _ = _read(_populated_body())
    assert C.BASE_COMMENT_WRITE_REFUSED_NOTE in read.notes
    assert C.BASE_COMMENT_WRITE_REFUSED_NOTE in read.disclosure


def test_ac5_the_four_server_refusals_are_in_the_committed_capture():
    """The CANNOT is server-declared, not asserted by this library."""
    steps = _capture(_EMPTY)["steps"]
    notes = [s["_note"] for s in steps]
    create = [s for s in steps if s["_method"] == "POST"][0]
    violations = create["response"]["error"]["field_violations"][0]
    assert violations["value"] == "bitable"
    assert violations["description"].endswith("options: [doc,docx]")
    assert any("file_token=RECORD id" in n for n in notes)
    assert any("bitable_record" in n for n in notes)
    assert [s["response"] for s in steps
            if "records/{r}/comments" in s["_note"]] == [{"_non_json_body_bytes": 18}]


def test_ac5_the_base_notes_do_not_leak_into_a_docx_read():
    """Zero-drift: the two shipped file types keep their own disclosures."""
    docx = C.comments("doccnDocToken", client=H.client({"list": _empty_body()}))
    assert C.BASE_COMMENT_WRITE_REFUSED_NOTE not in docx.notes


# --------------------------------------------------------------------------- #
# AC8 — the name-only doctrine, extended to a new payload class.                #
# --------------------------------------------------------------------------- #

_EMAILISH = re.compile(r"[^\s\"']+@[^\s\"']+\.[A-Za-z]{2,}")
_AVATAR_URL = re.compile(r"https?://\S*(avatar|cdn)\S*", re.I)
_PERSON_ID = re.compile(r"\b(ou_|on_|od-|ug_)[A-Za-z0-9]{10,}")


def _rendered_corpus():
    read, _ = _read(_populated_body())
    return "\n".join([read.disclosure]
                     + [c.rendered_thread for c in read.comments])


def test_ac8_a_rendered_thread_corpus_carries_no_email_and_no_avatar_url():
    corpus = _rendered_corpus()
    assert _EMAILISH.findall(corpus) == []
    assert _AVATAR_URL.findall(corpus) == []


def test_ac8_a_rendered_thread_carries_no_raw_person_id_either():
    assert _PERSON_ID.findall(_rendered_corpus()) == []


def test_ac8_the_rendered_thread_still_carries_what_the_reviewer_SAID():
    read, _ = _read(_populated_body())
    assert "This is a comment on row 1" in read.comments[0].rendered_thread


def test_ac8_the_author_label_falls_back_name_then_en_name_then_redacted():
    assert C.author_label("Ada", "Ada English") == "Ada"
    assert C.author_label(None, "Ada English") == "Ada English"
    assert C.author_label(None, None) == C.REDACTED_AUTHOR_LABEL
    assert C.author_label("", "") == C.REDACTED_AUTHOR_LABEL
    assert "redacted" in C.REDACTED_AUTHOR_LABEL


def test_ac8_the_comment_payload_carries_NO_name_so_the_marker_branch_is_the_real_one():
    text = (_CAPTURES / _POPULATED).read_text(encoding="utf-8")
    assert '"name"' not in text and '"en_name"' not in text
    read, _ = _read(_populated_body())
    assert read.comments[0].rendered_thread.startswith(C.REDACTED_AUTHOR_LABEL)


def test_ac8_a_mention_inside_a_rendered_thread_is_redacted_not_raw():
    body = _populated_body()
    body["data"]["items"][0]["reply_list"]["replies"][0]["content"]["elements"].append(
        {"type": "person", "person": {"user_id": "ou_1234567890abcdef"},
         "text_run": None, "docs_link": None})
    read, _ = _read(body)
    rendered = read.comments[0].rendered_thread
    assert "ou_1234567890abcdef" not in rendered
    assert C.REDACTED_AUTHOR_LABEL in rendered
    # the structured projection still carries the raw id for a caller that can join it
    assert read.comments[0].mentioned_user_ids == ("ou_1234567890abcdef",)


# --------------------------------------------------------------------------- #
# AC9 — determinism.                                                            #
# --------------------------------------------------------------------------- #

def test_ac9_two_reads_of_the_same_captured_payload_are_byte_identical():
    first, _ = _read(_populated_body())
    second, _ = _read(_populated_body())
    assert json.dumps(first.to_dict(), sort_keys=True) == json.dumps(
        second.to_dict(), sort_keys=True)
    assert first.disclosure == second.disclosure
    assert first.comments[0].rendered_thread == second.comments[0].rendered_thread


# --------------------------------------------------------------------------- #
# AC6 — BASE.md's two comments rows and the register's row 3.                   #
# --------------------------------------------------------------------------- #

_BASE_MD = REPO_ROOT / "BASE.md"


def test_ac6_base_md_carries_both_comments_rows():
    text = _BASE_MD.read_text(encoding="utf-8")
    assert "`comments.read`" in text
    assert "`comments.write`" in text
    read_row = [l for l in text.splitlines() if "`comments.read`" in l][0]
    write_row = [l for l in text.splitlines() if "`comments.write`" in l][0]
    assert "notify_extra" in read_row
    assert _POPULATED in read_row
    assert "refused-by-server" in write_row
    assert "[doc, docx]" in write_row or "[doc,docx]" in write_row


def test_ac6_register_row_3_points_at_THIS_storys_capture():
    text = _BASE_MD.read_text(encoding="utf-8")
    row = [l for l in text.splitlines() if l.startswith("| 3 |")][0]
    assert _POPULATED in row
    # the revisit trigger is left intact
    assert "99992402" in row and "field_violations" in row


@private_tree.citations
def test_ac6_every_capture_base_md_cites_exists():
    text = _BASE_MD.read_text(encoding="utf-8")
    for path in sorted(set(re.findall(r"dev/base-study/captures/[\w.\-]+\.json", text))):
        assert (Path(_BASE_MD).parent / path).exists(), path


# --------------------------------------------------------------------------- #
# AC7 — the permission row, and the evidenced finding that it widens nothing.   #
# --------------------------------------------------------------------------- #

def test_ac7_the_comments_read_row_covers_the_bitable_file_type_with_its_evidence():
    from larkdocio import permissions as perm

    scopes = perm.scopes_for_endpoints(
        ("/open-apis/drive/v1/files/:file_token/comments",), "read")
    assert scopes, "the comments read call site has no permission row"
    evidence = " ".join(s.evidence for s in scopes)
    assert "bitable" in evidence
    assert _POPULATED in evidence
    for scope in scopes:
        assert scope.verification in perm.VERIFICATION_LABELS


def test_ac7_widening_the_file_type_widened_NO_scope():
    """Stated as an evidenced finding: the same row, the same scope set."""
    from larkdocio import permissions as perm

    scopes = perm.scopes_for_endpoints(
        ("/open-apis/drive/v1/files/:file_token/comments",), "read")
    assert [s.scope for s in scopes] == ["docx:document:readonly"]


def test_ac7_nothing_in_the_comments_package_requests_or_widens_a_scope():
    root = Path(C.__file__).resolve().parent
    for path in sorted(root.rglob("*.py")):  # LD-654: recursive population
        text = path.read_text(encoding="utf-8").lower()
        for phrase in ("request the scope", "add the scope", "grant yourself",
                       "escalate"):
            assert phrase not in text, (path.name, phrase)


# --------------------------------------------------------------------------- #
# The harvest itself — the SDK drops `notify_extra`, so it is read from the      #
# SAME response's own bytes. No second call, no second client.                  #
# --------------------------------------------------------------------------- #

def test_the_pinned_sdk_really_does_drop_notify_extra():
    """The reason the harvest exists, pinned so it reddens if the SDK ever models it."""
    from lark_oapi.api.drive.v1 import ReplyExtra

    assert set(ReplyExtra._types) == {"image_list"}


def test_the_harvest_costs_no_extra_api_call():
    read, client = _read(_populated_body())
    assert read.api_calls == 1
    assert client.api_calls == 1
    assert len(client._sdk.calls) == 1


def test_the_harvest_survives_a_response_with_no_raw_bytes_at_all():
    """A response object without `raw` must degrade to no attribution, never to a crash."""
    assert A.attributions_from_raw(None) == {}
    assert A.attributions_from_raw(b"not json") == {}
    assert A.attributions_from_raw(b'{"data": {"items": null}}') == {}


def test_the_harvest_reads_the_reply_list_endpoints_body_shape_too():
    """A truncated thread completes through the reply-list route; its replies carry
    `extra` in the same place, one level shallower."""
    body = {"code": 0, "msg": "Success", "data": {"has_more": False, "items": [
        {"reply_id": "r1", "extra": {"notify_extra": {"record": "recZ"}}}]}}
    got = A.attributions_from_raw(json.dumps(body).encode("utf-8"))
    assert got == {"r1": A.BaseAttribution(record_id="recZ")}


def test_a_CALLER_SUPPLIED_reader_that_cannot_harvest_degrades_instead_of_raising():
    """``comments()`` documents ``client=`` as an extension point, and a reader written
    before Bases were readable offers no harvest. That is *no attribution* — the same answer
    a document has — not an AttributeError in the middle of someone's comment read."""

    class ReaderWithoutTheHarvest:
        api_calls = 0

        def list_comments(self, file_token, *, file_type="docx"):
            from lark_oapi.api.drive.v1 import FileComment

            items = _populated_body()["data"]["items"]
            return [FileComment(i) for i in items]

    read = C.comments("tok", file_type=C.FILE_TYPE_BITABLE,
                      client=ReaderWithoutTheHarvest())
    assert read.available is True
    assert read.comments[0].attribution is None
    assert read.comments[0].attribution_state == A.ATTRIBUTION_FILE_LEVEL


@pytest.mark.parametrize("file_type", ["docx", "sheet", "bitable"])
def test_the_harvest_is_file_type_blind_it_reads_what_the_payload_carries(file_type):
    read = C.comments("tok", file_type=file_type,
                      client=H.client({"list": _populated_body()}))
    assert read.comments[0].attribution is not None
