"""LD-202 — the whole-document comment op: create + ownership-scoped removal.

**Every fact this module asserts comes out of a committed probe capture**, not out of a
guess about Lark:

* the create body / path / response — ``tests/captures/comments-probe-round2-captures/14-demo.json``
  (``captures[0]``, label ``demo-create-docx``);
* the sheets enum rejection — the same file's ``sheet_attempts``
  (``99992402`` + ``field_violations[0].description`` verbatim);
* the six silently-accepted anchor shapes — ``dev/comments-probe-2026-07-29.md`` § Q1a's
  shape table (A..F, including the **bogus block id** and the **quote that is not in the
  document**), every one of which the API answered ``code 0`` for while producing a plain
  whole-document comment;
* the removal cascade and its ownership refusal —
  ``tests/captures/comments-probe-round2-captures/16-delete-arm.json`` (``DELETE …/comments/{cid}`` is
  route-absent with a **non-JSON** 404; ``DELETE …/replies/{rid}`` on a **human**-authored
  reply is HTTP 403 / ``1069303`` / ``"forbidden"``).

The AC2 arm is the keystone and it is built to be non-vacuous: the spy sits at the
**request-encoding seam** (the injected transport of a real ``WriteClient``), so "zero API
calls" is a statement about bytes that would have gone on a socket, not about a mock the
test set up to agree with itself.
"""
import json
from pathlib import Path

import pytest

from log_reading_apply import reading_the_log
from larkdocio.errors import LarkAPIError, LarkRateLimitError
from larkdocio.write import apply, dry_run
apply = reading_the_log(apply)
from larkdocio.write.client import WriteClient
from larkdocio.write.comments import (
    ANCHORED_CREATE_ABSENT_EVIDENCE,
    BOT_AUTHORSHIP_DISCLOSURE,
    COMMENT_FILE_TYPES,
    SHEETS_CREATE_REJECTED_EVIDENCE,
)
from larkdocio.write.model import (
    WHOLE_DOCUMENT,
    Anchor,
    CommentThread,
    CreateCommentRequest,
    EditRequest,
    RefusalReason,
    RemoveCommentRequest,
    _anchor_from_dict,
    _request_from_dict,
)

DOC = "doxcnLD202DOCUMENT"
BOT = "ou_examplebot0000000000000000000001"
HUMAN = "ou_exampleowner00000000000000000001"
CID = "7667877938850762473"
RID = "7667877938867556062"

_CAPTURES = Path(__file__).resolve().parents[1] / "tests" / "captures" / "comments-probe-round2-captures"


def _demo_capture():
    return json.loads((_CAPTURES / "14-demo.json").read_text(encoding="utf-8"))


def _delete_arm_capture():
    return json.loads((_CAPTURES / "16-delete-arm.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# The offline transport double — a REAL WriteClient with its socket replaced.    #
# Every assertion about "what went on the wire" reads this recorder.             #
# --------------------------------------------------------------------------- #

class WireRecorder:
    """Records ``(method, path, body)`` per attempt and serves queued reply bodies.

    Injected as the ``WriteClient``'s ``urlopen``, so the shipped client's own path
    building, JSON encoding, throttling and error typing all run unchanged — the only thing
    replaced is the socket. That is what makes the zero-call assertions mean something.
    """

    def __init__(self, replies=None):
        self.sent = []
        self._replies = list(replies or ())

    # -- the urlopen contract WriteClient's shared core calls ---------------- #

    def __call__(self, request, timeout=None):
        body = request.data.decode("utf-8") if request.data else None
        self.sent.append((
            request.get_method(),
            request.full_url,
            json.loads(body) if body else None,
        ))
        reply = self._replies.pop(0) if self._replies else {"code": 0, "msg": "ok", "data": {}}
        if isinstance(reply, Exception):
            raise reply
        return _Resp(reply)

    # -- what the tests read ------------------------------------------------- #

    @property
    def methods(self):
        return [m for m, _p, _b in self.sent]

    @property
    def paths(self):
        return [p for _m, p, _b in self.sent]

    @property
    def bodies(self):
        return [b for _m, _p, b in self.sent]

    def json_sent(self):
        """Every request body this recorder saw, as one JSON string — the bytes an
        anchor-field assertion has to search. Serialized rather than walked so a field
        nested anywhere in any body is caught."""
        return json.dumps(self.sent)


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _NoSleepTransport:
    """The write transport with its pacing sleep removed — real code path, no wall clock."""

    def execute(self, call):
        return call()


def client(replies=None):
    recorder = WireRecorder(replies)
    wc = WriteClient(
        "cli_offline", "secret-offline",
        transport=_NoSleepTransport(),
        urlopen=recorder,
        token_fetcher=lambda *a, **k: "t-offline",
    )
    return wc, recorder


def _create_reply(comment_id=CID, reply_id=RID, user_id=BOT):
    """The create response, in the captured shape (note ``is_whole`` is ABSENT here —
    the capture proves the create response does not report the scope)."""
    return {
        "code": 0, "msg": "Success",
        "data": {
            "comment_id": comment_id,
            "create_time": 1785316956,
            "is_solved": False,
            "reply_list": {"replies": [{
                "content": {"elements": [
                    {"docs_link": None, "person": None,
                     "text_run": {"text": "hello"}, "type": "text_run"},
                ]},
                "create_time": 1785316956, "extra": None,
                "reply_id": reply_id, "update_time": 1785316956, "user_id": user_id,
            }]},
            "solver_user_id": None, "update_time": 1785316956, "user_id": user_id,
        },
    }


def _replies_reply(*authors):
    """The reply-list response with one reply per author id, in order."""
    return {
        "code": 0, "msg": "Success",
        "data": {
            "has_more": False, "page_token": "0",
            "items": [
                {"reply_id": f"{RID}{i}", "user_id": uid,
                 "content": {"elements": [{"type": "text_run",
                                           "text_run": {"text": f"r{i}"}}]},
                 "create_time": 1785316956, "extra": {"image_list": []},
                 "update_time": 1785316956}
                for i, uid in enumerate(authors)
            ],
        },
    }


def _lark_error(code, msg):
    return {"code": code, "msg": msg, "error": {"log_id": "offline"}}


def _plan(*requests, revision=None):
    """A plan over comment requests. The tree is irrelevant to a comment op — it points at
    the file, not at a block — so an empty root is passed deliberately."""
    return dry_run(list(requests), None, document_revision_id=revision)


# =========================================================================== #
# AC1 — a typed whole-document comment CREATE through the existing gate.        #
# =========================================================================== #

def test_ac1_the_request_is_frozen_and_json_round_trips():
    req = CreateCommentRequest(text="a review note")
    with pytest.raises(Exception):
        req.text = "mutated"
    assert _request_from_dict(req.to_dict()) == req
    assert json.loads(json.dumps(req.to_dict())) == req.to_dict()


def test_ac1_the_removal_request_is_frozen_and_json_round_trips():
    req = RemoveCommentRequest(comment_id=CID, author_id=BOT)
    with pytest.raises(Exception):
        req.comment_id = "mutated"
    assert _request_from_dict(req.to_dict()) == req
    assert json.loads(json.dumps(req.to_dict())) == req.to_dict()


def test_ac1_the_two_new_anchors_round_trip_through_the_one_dispatcher():
    assert _anchor_from_dict(WHOLE_DOCUMENT.to_dict()) == WHOLE_DOCUMENT
    thread = CommentThread(comment_id=CID)
    assert _anchor_from_dict(thread.to_dict()) == thread
    # and the tagless narrative Anchor is untouched by the two new tags
    assert _anchor_from_dict({"quote": "q", "breadcrumb": []}) == Anchor("q")


def test_ac1_a_create_previews_resolved_and_carries_its_intent():
    plan = _plan(CreateCommentRequest(text="a review note"))
    (entry,) = plan.entries
    assert entry.op == "comment-create"
    assert entry.is_resolved
    assert entry.anchor == WHOLE_DOCUMENT
    assert entry.comment.text == "a review note"
    # the plan round-trips as a record, like every other op's entry
    from larkdocio.write.preview import PlanEntry
    assert PlanEntry.from_dict(entry.to_dict()) == entry


def test_ac1_a_create_sends_the_byte_exact_captured_method_path_and_body():
    """The keystone of AC1: the request this library encodes is compared field for field
    against the committed capture of the call that really worked."""
    captured = _demo_capture()["captures"][0]
    assert captured["label"] == "demo-create-docx"

    text = captured["request_body"]["reply_list"]["replies"][0]["content"]["elements"][0]["text_run"]["text"]
    wc, wire = client([_create_reply()])
    log = apply(_plan(CreateCommentRequest(text=text)), wc, DOC)

    (method, path, body) = wire.sent[0]
    assert method == captured["method"] == "POST"
    assert path.endswith(f"/open-apis/drive/v1/files/{DOC}/comments?file_type=docx")
    # the capture's path template, with its two placeholders filled
    assert captured["path"] == "drive/v1/files/{tok}/comments?file_type=docx"
    assert body == captured["request_body"]

    (entry,) = log.entries
    assert entry.outcome == "commented"
    assert entry.comment_record["comment_id"] == CID
    assert entry.comment_record["author_id"] == BOT
    assert entry.comment_record["scope"] == "whole-document"


def test_ac1_the_apply_log_round_trips_with_the_new_outcomes():
    from larkdocio.write.model import ApplyLog

    wc, _wire = client([_create_reply()])
    log = apply(_plan(CreateCommentRequest(text="x")), wc, DOC)
    assert ApplyLog.from_dict(log.to_dict()) == log
    assert json.loads(log.to_json()) == log.to_dict()


def test_ac1_apply_still_refuses_a_forged_plan():
    """The non-forgeable Plan gate is not weakened by the new ops."""
    from larkdocio.write.preview import Plan, PlanEntry

    entry = _plan(CreateCommentRequest(text="x")).entries[0]
    with pytest.raises(TypeError):
        Plan([entry])
    with pytest.raises(TypeError):
        apply([entry], *client()[:1], DOC)
    assert PlanEntry.from_dict(entry.to_dict()) == entry


def test_ac1_a_comment_create_rides_the_whole_batch_zero_writes_contract():
    """The docx CAS is the batch's outer gate; a drifted document refuses the comment op
    too, with zero writes issued."""
    wc, wire = client([
        {"code": 0, "msg": "ok", "data": {"document": {"revision_id": 99}}},
    ])
    log = apply(_plan(CreateCommentRequest(text="x"), revision=7), wc, DOC)
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason is RefusalReason.STALE_DOCUMENT
    assert wire.methods == ["GET"], "the CAS read only; no comment was posted"


def test_ac1_a_create_can_ride_a_batch_beside_an_ordinary_edit():
    """One registration point means one batch: the plan stays 1:1 and in order."""
    tree = _one_paragraph_tree("the target text")
    plan = dry_run(
        [CreateCommentRequest(text="note"),
         EditRequest(anchor=Anchor("the target text"), replacement="new text")],
        tree,
    )
    assert [e.op for e in plan.entries] == ["comment-create", "edit"]
    assert all(e.is_resolved for e in plan.entries)


def _one_paragraph_tree(text):
    """A minimal parsed tree carrying one text block — the reader's own node shape."""
    from larkdocio.model import PageNode, Text, TextNode

    child = TextNode(content=[Text(text)], block_id="blkLD202")
    return PageNode(title=[Text("Doc")], children=[child], block_id=DOC)


# =========================================================================== #
# AC2 — anchored intent is REFUSED, never silently downgraded. THE keystone.    #
# =========================================================================== #

#: The six shapes the probe sent on the v1 route, § Q1a's table A..F. **Every one was
#: answered ``code 0`` and produced a plain whole-document comment** — including C's bogus
#: block id and F's quote that does not occur in the document. Tabled here so a pass-through
#: regression has to break six tests, not one.
SIX_ANCHOR_SHAPES = [
    ("A valid block id + quote + is_whole:false",
     dict(anchor_block_id="doxcnRealBlockId0000000001", quote="12.4%", is_whole=False)),
    ("B the anchor as a JSON string",
     dict(anchor_block_id='{"block_id": "doxcnRealBlockId0000000001"}')),
    ("C a BOGUS block id — not even an error to Lark",
     dict(anchor_block_id="doxcnBOGUSBLOCKID000000000")),
    ("D quote + is_whole:false, no anchor",
     dict(quote="12.4%", is_whole=False)),
    ("E quote only",
     dict(quote="12.4%")),
    ("F a quote that is NOT IN THE DOCUMENT — not an error either",
     dict(quote="TEXT-THAT-IS-NOT-IN-THE-DOCUMENT-zzz")),
]


@pytest.mark.parametrize("label,kwargs", SIX_ANCHOR_SHAPES,
                         ids=[label.split()[0] for label, _ in SIX_ANCHOR_SHAPES])
def test_ac2_each_of_the_six_silently_accepted_shapes_is_refused_at_plan_time(label, kwargs):
    plan = _plan(CreateCommentRequest(text="note", **kwargs))
    (entry,) = plan.entries
    assert not entry.is_resolved, label
    assert entry.refusal.reason is RefusalReason.COMMENT_ANCHOR_NOT_CREATABLE, label
    detail = entry.refusal.detail
    assert detail.strip(), "LD-131: every refusal carries a non-empty actionable detail"
    # the captured evidence, and the working alternative, are both in the detail
    assert "code 0" in detail, detail
    assert "whole-document" in detail, detail


@pytest.mark.parametrize("label,kwargs", SIX_ANCHOR_SHAPES,
                         ids=[label.split()[0] for label, _ in SIX_ANCHOR_SHAPES])
def test_ac2_a_refused_anchor_shape_costs_ZERO_api_calls(label, kwargs):
    """The zero-call spy, at the request-encoding seam.

    ``dry_run`` is structurally callless, so the interesting half is ``apply``: it must
    carry the refusal into the log and send **nothing**. The recorder is the injected
    socket of a real ``WriteClient``, so a call that reached encoding would be recorded
    even if it never left the machine.
    """
    wc, wire = client()
    log = apply(_plan(CreateCommentRequest(text="note", **kwargs)), wc, DOC)
    assert wire.sent == [], f"{label}: {wire.sent}"
    assert wc._token is None, "no token was even fetched"
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason is RefusalReason.COMMENT_ANCHOR_NOT_CREATABLE


def test_ac2_no_accepted_create_ever_puts_an_anchor_field_on_the_wire():
    """The other half of the trap: the shape we DO send must never carry ``anchor`` /
    ``quote`` / ``is_whole``, because the API accepts them and drops them."""
    wc, wire = client([_create_reply()])
    apply(_plan(CreateCommentRequest(text="note", is_whole=True)), wc, DOC)
    sent = wire.json_sent()
    for field in ("anchor", "quote", "is_whole"):
        assert f'"{field}"' not in sent, f"{field} reached the wire: {sent}"
    assert wire.bodies[0] == {"reply_list": {"replies": [
        {"content": {"elements": [{"type": "text_run", "text_run": {"text": "note"}}]}}]}}


def test_ac2_is_whole_true_is_accepted_because_it_is_what_we_do_anyway():
    """``is_whole=True`` is not an anchored intent — it restates the only shape that
    exists, so it proceeds (and still never reaches the wire, above)."""
    (entry,) = _plan(CreateCommentRequest(text="note", is_whole=True)).entries
    assert entry.is_resolved


def test_ac2_the_evidence_constant_quotes_the_probe_not_a_paraphrase():
    text = ANCHORED_CREATE_ABSENT_EVIDENCE
    assert "code 0" in text
    assert "18" in text, "the 18 absent create_v2 routes are the other half of the finding"
    assert "silently" in text.lower()


# =========================================================================== #
# AC3 — a SHEETS target is refused with the captured evidence.                  #
# =========================================================================== #

@pytest.mark.parametrize("file_type", ["sheet", "sheets", "spreadsheet"])
def test_ac3_every_sheets_spelling_is_refused_with_the_captured_enum(file_type):
    plan = _plan(CreateCommentRequest(text="note", file_type=file_type))
    (entry,) = plan.entries
    assert not entry.is_resolved
    assert entry.refusal.reason is RefusalReason.COMMENT_SURFACE_UNSUPPORTED
    detail = entry.refusal.detail
    assert "99992402" in detail, detail
    assert "options: [doc,docx]" in detail, detail
    assert "read" in detail.lower(), "the refusal must note that sheets comment READING works"


@pytest.mark.parametrize("file_type", ["sheet", "sheets", "spreadsheet"])
def test_ac3_a_sheets_target_costs_zero_api_calls(file_type):
    wc, wire = client()
    apply(_plan(CreateCommentRequest(text="n", file_type=file_type)), wc, DOC)
    assert wire.sent == []


def test_ac3_the_refusal_reproduces_the_captured_field_violation_verbatim():
    """Not a paraphrase: the shipped evidence string contains the capture's own
    ``field_violations[0].description``."""
    captured = _demo_capture()["sheet_attempts"]["sheet"]
    description = captured["field_violations"][0]["description"]
    assert description in SHEETS_CREATE_REJECTED_EVIDENCE
    assert str(captured["code"]) in SHEETS_CREATE_REJECTED_EVIDENCE
    assert captured["msg"] in SHEETS_CREATE_REJECTED_EVIDENCE


@pytest.mark.parametrize("file_type", ["docx", "doc"])
def test_ac3_the_two_file_types_lark_ACCEPTS_proceed(file_type):
    (entry,) = _plan(CreateCommentRequest(text="n", file_type=file_type)).entries
    assert entry.is_resolved
    assert set(COMMENT_FILE_TYPES) == {"doc", "docx"}, (
        "the accepted set is Lark's own enum, quoted from the field violation")


def test_ac3_an_unknown_file_type_is_refused_too_rather_than_attempted():
    (entry,) = _plan(CreateCommentRequest(text="n", file_type="bitable")).entries
    assert not entry.is_resolved
    assert entry.refusal.reason is RefusalReason.COMMENT_SURFACE_UNSUPPORTED


# =========================================================================== #
# AC4 — REMOVAL via the proven cascade, OWNERSHIP-SCOPED.                       #
# =========================================================================== #

def test_ac4_the_apps_own_single_reply_thread_removes_via_the_cascade():
    wc, wire = client([
        _replies_reply(BOT),
        {"code": 0, "msg": "success", "data": {}},
    ])
    log = apply(_plan(RemoveCommentRequest(comment_id=CID, author_id=BOT)), wc, DOC)
    (entry,) = log.entries
    assert entry.outcome == "comment-removed"
    assert entry.comment_record["comment_id"] == CID
    assert entry.comment_record["removed_reply_ids"] == [f"{RID}0"]
    assert wire.methods == ["GET", "DELETE"]
    assert wire.paths[1].endswith(
        f"/open-apis/drive/v1/files/{DOC}/comments/{CID}/replies/{RID}0?file_type=docx")


def test_ac4_a_two_reply_thread_the_app_owns_removes_BOTH_replies():
    """The cascade is 'delete every reply'; the comment goes with the last one. Pinned so
    a future 'delete only the last reply' shortcut cannot slip in."""
    wc, wire = client([
        _replies_reply(BOT, BOT),
        {"code": 0, "msg": "success", "data": {}},
        {"code": 0, "msg": "success", "data": {}},
    ])
    log = apply(_plan(RemoveCommentRequest(comment_id=CID, author_id=BOT)), wc, DOC)
    (entry,) = log.entries
    assert entry.outcome == "comment-removed"
    assert entry.comment_record["removed_reply_ids"] == [f"{RID}0", f"{RID}1"]
    assert wire.methods == ["GET", "DELETE", "DELETE"]


def test_ac4_a_human_authored_thread_is_refused_before_any_delete():
    wc, wire = client([_replies_reply(HUMAN)])
    log = apply(_plan(RemoveCommentRequest(comment_id=CID, author_id=BOT)), wc, DOC)
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason is RefusalReason.COMMENT_THREAD_NOT_SOLELY_AUTHORED
    assert HUMAN in entry.refusal.detail
    assert wire.methods == ["GET"], "the ownership check refused BEFORE any DELETE"


def test_ac4_a_thread_carrying_another_partys_reply_is_refused():
    """The app authored the thread but a human replied: still refused, nothing deleted."""
    wc, wire = client([_replies_reply(BOT, HUMAN)])
    log = apply(_plan(RemoveCommentRequest(comment_id=CID, author_id=BOT)), wc, DOC)
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason is RefusalReason.COMMENT_THREAD_NOT_SOLELY_AUTHORED
    assert "DELETE" not in wire.methods


def test_ac4_larks_own_1069303_denial_body_reaches_the_consumer_verbatim():
    """The captured ownership refusal, reproduced rather than paraphrased: when the API
    itself denies the delete, its ``code`` and ``msg`` are in the refusal detail."""
    arm = _delete_arm_capture()["doc_arm"]
    denial = [c for c in arm["captures"] if c["label"] == "delete-reply"][0]
    assert denial["http_status"] == 403 and denial["code"] == 1069303
    assert denial["msg"] == "forbidden"

    wc, _wire = client([
        _replies_reply(BOT),
        LarkAPIError("delete reply failed", code=denial["code"], msg=denial["msg"]),
    ])
    log = apply(_plan(RemoveCommentRequest(comment_id=CID, author_id=BOT)), wc, DOC)
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert "1069303" in entry.refusal.detail
    assert "forbidden" in entry.refusal.detail


def test_ac4_a_comment_that_is_already_gone_is_a_typed_refusal_not_a_silent_success():
    """The decision, pinned: ``1069307`` refuses. Reporting 'removed' for something this
    run did not remove would be a claim the apply-log cannot back."""
    wc, wire = client([LarkAPIError("list replies failed", code=1069307, msg="not exist")])
    log = apply(_plan(RemoveCommentRequest(comment_id=CID, author_id=BOT)), wc, DOC)
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason is RefusalReason.NOT_FOUND
    assert "1069307" in entry.refusal.detail
    assert "DELETE" not in wire.methods


def test_ac4_a_thread_with_no_replies_left_is_refused_rather_than_reported_removed():
    wc, wire = client([_replies_reply()])
    log = apply(_plan(RemoveCommentRequest(comment_id=CID, author_id=BOT)), wc, DOC)
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason is RefusalReason.NOT_FOUND
    assert "DELETE" not in wire.methods


def test_ac4_the_removal_never_asks_for_the_absent_delete_comment_route():
    """``DELETE …/comments/{cid}`` answers a **non-JSON** gateway 404 — it does not exist.
    The shipped path must never try it."""
    arm = _delete_arm_capture()["doc_arm"]
    absent = [p for p in arm["paths"] if p["path"] == "DELETE …/comments/{cid}"][0]
    assert absent["route_absent"] and absent["http_status"] == 404

    wc, wire = client([_replies_reply(BOT), {"code": 0, "msg": "ok", "data": {}}])
    apply(_plan(RemoveCommentRequest(comment_id=CID, author_id=BOT)), wc, DOC)
    for method, path, _body in wire.sent:
        if method == "DELETE":
            assert "/replies/" in path, f"the absent comment-delete route was attempted: {path}"


def test_ac4_a_rate_limit_is_re_raised_because_throttling_is_not_a_denial():
    """**TRANSFORMED, NOT STRUCK (LD-643).** The reason is unchanged and still binds:
    throttling is not a denial, so a rate limit may never come back as
    ``comment-thread-not-solely-authored`` (or any other ownership answer) — asserted below,
    as it always was. What LD-643 supersedes is the conclusion that it therefore leaves
    ``apply()`` as a raw ``LarkRateLimitError``: escaping the per-entry loop is what left the
    caller with no apply-log at all. It is now typed ``rate-limited`` inside a complete log,
    which says the same thing and loses nothing."""
    wc, _wire = client([LarkRateLimitError("slow down", code=99991400, msg="too many")])
    log = apply(_plan(RemoveCommentRequest(comment_id=CID, author_id=BOT)), wc, DOC)

    entry = log.entries[0]
    assert entry.refusal.reason.value != "comment-thread-not-solely-authored"
    assert entry.refusal.reason.value == "rate-limited"
    assert "NOTHING landed" in entry.refusal.detail


def test_ac4_a_removal_request_needs_an_author_id_it_will_not_guess():
    with pytest.raises(TypeError):
        RemoveCommentRequest(comment_id=CID)
    with pytest.raises(ValueError):
        RemoveCommentRequest(comment_id=CID, author_id="   ")
    with pytest.raises(ValueError):
        RemoveCommentRequest(comment_id="  ", author_id=BOT)


# =========================================================================== #
# AC5 — NEVER PARTIAL-DELETE.                                                   #
# =========================================================================== #

@pytest.mark.parametrize("authors", [(HUMAN,), (BOT, HUMAN), (HUMAN, BOT), (BOT, BOT, HUMAN)])
def test_ac5_a_refused_removal_leaves_the_thread_intact(authors):
    """Reply count unchanged, because not one DELETE was issued."""
    wc, wire = client([_replies_reply(*authors)])
    log = apply(_plan(RemoveCommentRequest(comment_id=CID, author_id=BOT)), wc, DOC)
    assert log.entries[0].outcome == "refused"
    assert wire.methods == ["GET"], (
        f"a refused removal issued writes: {wire.methods}")


def test_ac5_the_ownership_check_precedes_every_delete_in_the_call_ORDER():
    """Structural, not incidental: the whole thread is read and judged before the first
    delete, so there is no code path that deletes some replies and then stops."""
    wc, wire = client([
        _replies_reply(BOT, BOT, BOT),
        {"code": 0, "msg": "ok", "data": {}},
        {"code": 0, "msg": "ok", "data": {}},
        {"code": 0, "msg": "ok", "data": {}},
    ])
    apply(_plan(RemoveCommentRequest(comment_id=CID, author_id=BOT)), wc, DOC)
    assert wire.methods == ["GET", "DELETE", "DELETE", "DELETE"]
    assert wire.methods.index("GET") == 0


def test_ac5_no_source_path_can_delete_a_reply_without_the_ownership_check_first():
    """A source-level guard on the one function that deletes: the ownership decision and
    the delete loop are in the same function, and the decision returns early."""
    import ast
    import inspect

    from larkdocio.write import comments as mod

    src = inspect.getsource(mod._apply_comment_remove)
    tree = ast.parse(src.lstrip())
    calls = [n.func.attr for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert "list_comment_replies" in calls
    assert "delete_comment_reply" in calls
    assert calls.index("list_comment_replies") < calls.index("delete_comment_reply"), (
        "the live thread must be read (and judged) before the first delete")
    # and no other function in the module deletes a reply
    others = [name for name, fn in vars(mod).items()
              if callable(fn) and getattr(fn, "__module__", None) == mod.__name__
              and name != "_apply_comment_remove"
              and "delete_comment_reply" in _safe_source(fn)]
    assert others == [], f"a second deletion path exists: {others}"


def _safe_source(fn):
    import inspect
    try:
        return inspect.getsource(fn)
    except (OSError, TypeError):
        return ""


def test_ac5_a_mid_cascade_failure_is_logged_as_a_refusal_naming_what_was_removed():
    """The one case the pre-check cannot make impossible — the server failing partway.
    It cannot be undone, so the log must say exactly which replies went. Silence here
    would be the real failure."""
    wc, wire = client([
        _replies_reply(BOT, BOT),
        {"code": 0, "msg": "ok", "data": {}},
        LarkAPIError("delete reply failed", code=1069301, msg="fail"),
    ])
    log = apply(_plan(RemoveCommentRequest(comment_id=CID, author_id=BOT)), wc, DOC)
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.comment_record is not None, "the partial removal must be RECORDED"
    assert entry.comment_record["removed_reply_ids"] == [f"{RID}0"]
    assert "1069301" in entry.refusal.detail
    assert wire.methods == ["GET", "DELETE", "DELETE"]


# =========================================================================== #
# AC6 — AUTHORSHIP IS DISCLOSED, not discovered.                                #
# =========================================================================== #

def test_ac6_the_plan_discloses_the_bot_identity_before_anything_is_written():
    plan = _plan(CreateCommentRequest(text="note"))
    (entry,) = plan.entries
    notes = [n for n in entry.preview_notes if n["kind"] == "comment-lands-as-the-app-bot"]
    assert notes, entry.preview_notes
    note = notes[0]["note"]
    assert "open_id" in note
    assert "41050" in note, "the display-name gap is named by its code"
    assert "comments panel" in note.lower()


def test_ac6_the_disclosure_survives_a_plan_round_trip():
    from larkdocio.write.preview import PlanEntry

    (entry,) = _plan(CreateCommentRequest(text="note")).entries
    assert PlanEntry.from_dict(entry.to_dict()).preview_notes == entry.preview_notes


def test_ac6_the_disclosure_constant_states_all_four_facts():
    text = BOT_AUTHORSHIP_DISCLOSURE.lower()
    for fact in ("open_id", "41050", "comments panel", "whole-document", "apply-log"):
        assert fact in text, fact


def test_ac6_the_apply_log_reports_the_author_id_the_removal_will_need():
    """The loop AC6 exists for: the create hands back the very id the removal requires,
    so a consumer never has to discover it."""
    wc, _wire = client([_create_reply()])
    log = apply(_plan(CreateCommentRequest(text="note")), wc, DOC)
    record = log.entries[0].comment_record
    assert record["author_id"] == BOT
    # and that id is exactly what RemoveCommentRequest asks for
    RemoveCommentRequest(comment_id=record["comment_id"], author_id=record["author_id"])


def test_ac6_the_guide_and_capabilities_both_state_the_bot_identity():
    from larkdocio import capabilities, guide

    contract = capabilities(full=True)["safety_contracts"]["comment-create-whole-document-only"]
    assert "bot" in contract["summary"].lower()
    assert "41050" in contract["summary"]
    assert "41050" in guide(full=True)
