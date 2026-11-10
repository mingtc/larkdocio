"""LD-163 — `comment_ids` PRESERVATION across the two docx text-edit paths.

The defect: both edit paths rebuilt every run through ``to_write_elements`` →
``_clean_style``, whose emitted key set is **closed** (five style flags plus
``text_color`` / ``background_color`` / ``link``) and excludes ``comment_ids``. So every
patch body either path emitted dropped a reviewer's inline anchor **silently** — no
refusal, no note, nothing in the plan or the apply-log. The loss was *targeted*: in the
sub-span body the span run kept ``bold: true`` while its anchors vanished.

The fix is **asymmetric on purpose** (a settled product decision, not an implementation
convenience):

* the **sub-span** path splits runs at the span boundaries, so each region's ids have
  somewhere to go — every rebuilt run re-emits the ids its source run carried, and the run
  that replaces the span takes its region's ids along with its region's style. Where the
  span's own runs disagree about their anchors there is no single answer, so it **refuses**
  (``span-not-splittable``) exactly as it already does for a disagreeing *style*;
* the **element-level** (whole-paragraph) path collapses the block to a **single** run by
  design, so per-span ids have nothing to attach to. It **refuses** at plan time
  (``comment-anchors-present``) with the sub-span recovery named. Not the leading-run
  variant (which drops the other runs' anchors) and not the union variant (which relocates
  every anchor onto the whole paragraph): a comment that silently moves to the wrong text is
  a lie about what a reviewer objected to, which is worse than a refusal pointing at the
  path that works.

**What the server does with what we send** (the evidence this fix rests on,
``dev/comments-probe-round2-2026-07-29.md`` § Q6): under an edit whose payload omits the
ids the server **orphans** the anchor at both granularities and **cannot be made to
re-attach it afterwards** — re-PATCHing the block with its own baseline elements is refused
``1770001`` once the block has disowned them, while the identical body was accepted ``code
0`` moments earlier when the block still carried them. So the server *validates*
``comment_ids`` against the block's live anchors rather than ignoring the field: sending a
region's own current ids is accepted, and preservation has to happen **in the patch that
does the edit** or not at all. These tests therefore pin the **payload** — what the emitted
body carries — which is the whole of what this library controls.

The three geometries the opener spike characterized are asserted against **its own captured
payloads** (``tests/captures/comments-probe-captures/05-edit-path-comment-ids.json``), so the inputs
are real captured run shapes rather than hand-invented ones: a comment **inside** the edited
span, one **spanning** it, and one on an untouched **neighbour** run.
"""
import json
import pathlib

import pytest

from log_reading_apply import reading_the_log
from larkdocio.model import StyledText, Text, TextNode
from larkdocio.write.apply import (
    apply,
    build_subspan_update,
    build_whole_paragraph_update,
)
apply = reading_the_log(apply)
from larkdocio.write.client import to_write_elements
from larkdocio.write.model import (
    Anchor,
    AnchorById,
    Refusal,
    RefusalReason,
    SubSpanEditRequest,
)
from larkdocio.write.preview import dry_run

from write_harness import (
    StubOpener,
    _block_payload,
    _client,
    _page,
    _para,
    _patch_ok,
    _req,
    _run,
)

ID_A = "7667754726531878624"
ID_B = "7667754726531878625"
ID_C = "7667754726531878626"

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_CAPTURE = REPO_ROOT / "tests" / "captures" / "comments-probe-captures" / "05-edit-path-comment-ids.json"

#: The mutations the capture was taken with (read back off its own recorded bodies).
_WHOLE_PARAGRAPH_REPLACEMENT = "REPLACED WHOLE PARAGRAPH"
_SPAN, _SPAN_REPLACEMENT = "12.4%", "15.0%"


def _geometry(name):
    """One captured geometry: the real live-shaped runs plus the bodies as first shipped."""
    legs = json.loads(_CAPTURE.read_text(encoding="utf-8"))["leg1"]
    assert set(legs) == {"inside", "spanning", "neighbour"}, (
        "the capture no longer holds all three comment geometries"
    )
    return legs[name]


def _anchored_para(bid, *runs, block_ids=None):
    """A model block whose inline runs carry WORD-level anchors.

    ``runs`` are ``(text, comment_ids)`` pairs — ``comment_ids=None`` builds a plain
    :class:`Text` (a run with no ``text_element_style`` at all), anything else a
    :class:`StyledText` carrying that list verbatim. ``block_ids`` is the block's own
    BLOCK-level list, which is a different granularity and a different question (AC6).
    """
    inlines = []
    for text, ids in runs:
        inlines.append(Text(text) if ids is None else StyledText(text, comment_ids=ids))
    return TextNode(content=inlines, block_id=bid, comment_ids=block_ids)


def _elements(body):
    return body["update_text_elements"]["elements"]


def _styles(body):
    return [el["text_run"].get("text_element_style") for el in _elements(body)]


# --------------------------------------------------------------------------- #
# AC2 — THE SUB-SPAN PATH CARRIES EACH REGION'S ANCHORS THROUGH THE SPLIT       #
# --------------------------------------------------------------------------- #

def test_the_rebuild_emits_a_runs_anchors_beside_its_style():
    """The root cause, inverted at the function the whole loss came through: the style flag
    and the anchor now leave the reducer together."""
    live = [{"text_run": {"content": "12.4%", "text_element_style": {
        "bold": True, "comment_ids": [ID_A]}}}]
    assert to_write_elements(live) == [
        {"text_run": {"content": "12.4%", "text_element_style": {
            "bold": True, "comment_ids": [ID_A]}}}
    ]


def test_the_rebuild_emits_the_anchor_on_a_run_with_NO_other_style():
    """A run whose ``text_element_style`` holds *only* ``comment_ids`` used to reduce to
    ``None`` (no style key at all). It must now emit the anchor by itself."""
    live = [{"text_run": {"content": "Simple Open Comment",
                          "text_element_style": {"comment_ids": [ID_A]}}}]
    assert to_write_elements(live) == [
        {"text_run": {"content": "Simple Open Comment",
                      "text_element_style": {"comment_ids": [ID_A]}}}
    ]


def test_the_rebuilt_ids_are_a_COPY_not_an_alias_of_the_live_payload():
    """Mutating the emitted body must not reach back into the caller's live payload."""
    ids = [ID_A, ID_B]
    live = [{"text_run": {"content": "x", "text_element_style": {"comment_ids": ids}}}]
    out = to_write_elements(live)
    out[0]["text_run"]["text_element_style"]["comment_ids"].append("intruder")
    assert ids == [ID_A, ID_B]


def test_the_ids_order_is_verbatim_with_no_sort_and_no_dedup():
    """The model's own rule (the ids are the API's data, not ours to normalize), applied to
    the write side: a reversed, duplicated list comes out exactly as it went in."""
    ids = [ID_C, ID_A, ID_A, ID_B]
    live = [{"text_run": {"content": "x", "text_element_style": {"comment_ids": list(ids)}}}]
    emitted = to_write_elements(live)[0]["text_run"]["text_element_style"]["comment_ids"]
    assert emitted == ids


@pytest.mark.parametrize("geometry", ["inside", "spanning", "neighbour"])
def test_the_three_captured_geometries_land_the_ids_on_the_RIGHT_run(geometry):
    """The spike's three geometries, against its own captured payloads, with the emitted body
    quoted in full: the body is the previously-shipped one **plus** the ids on exactly the
    runs whose text carries them.

    * *inside* — the anchored run IS the span: only the replacement run takes the ids;
    * *spanning* — one anchored run covers the whole block: the prefix, the replacement and
      the suffix all sit inside the anchored text, so all three carry it;
    * *neighbour* — the anchor is on a run the span never touches: it comes through
      byte-identically and the replacement run stays anchor-free.
    """
    leg = _geometry(geometry)
    live = leg["live_elements_in"]
    assert any("comment_ids" in (e["text_run"].get("text_element_style") or {})
               for e in live), "this geometry's input carries no comment_ids to carry through"

    body = build_subspan_update(live, _SPAN, _SPAN_REPLACEMENT)
    expected = {
        "inside": {"update_text_elements": {"elements": [
            {"text_run": {"content": "The quarterly revenue grew "}},
            {"text_run": {"content": "15.0%", "text_element_style": {
                "bold": True, "comment_ids": [ID_A]}}},
            {"text_run": {"content": " in Q3 across all regions."}},
        ]}},
        "spanning": {"update_text_elements": {"elements": [
            {"text_run": {"content": "The quarterly revenue grew ",
                          "text_element_style": {"comment_ids": [ID_A]}}},
            {"text_run": {"content": "15.0%", "text_element_style": {"comment_ids": [ID_A]}}},
            {"text_run": {"content": " in Q3 across all regions.",
                          "text_element_style": {"comment_ids": [ID_A]}}},
        ]}},
        "neighbour": {"update_text_elements": {"elements": [
            {"text_run": {"content": "The quarterly revenue grew ",
                          "text_element_style": {"comment_ids": [ID_A]}}},
            {"text_run": {"content": "15.0%", "text_element_style": {"bold": True}}},
            {"text_run": {"content": " in Q3 across all regions."}},
        ]}},
    }[geometry]
    # the capture's own id, so the expectation is the captured payload's data.
    captured_ids = {"inside": [ID_A], "spanning": [ID_A], "neighbour": [ID_A]}[geometry]
    assert captured_ids == [ID_A]
    expected_json = json.dumps(expected).replace(ID_A, "7667000000000000001")
    assert body == json.loads(expected_json), body


@pytest.mark.parametrize("geometry", ["inside", "spanning", "neighbour"])
def test_the_untouched_runs_stay_byte_identical_to_the_previously_shipped_body(geometry):
    """The other half of the same pin: apart from the added ids the sub-span body is the
    body that shipped before this fix — the split, the styles and the text are unchanged."""
    leg = _geometry(geometry)
    body = build_subspan_update(leg["live_elements_in"], _SPAN, _SPAN_REPLACEMENT)

    def _stripped(b):
        out = json.loads(json.dumps(b))
        for el in _elements(out):
            style = el["text_run"].get("text_element_style")
            if style is not None:
                style.pop("comment_ids", None)
                if not style:
                    del el["text_run"]["text_element_style"]
        return out

    assert _stripped(body) == leg["subspan_body"]


def test_a_run_carrying_SEVERAL_ids_carries_all_of_them():
    live = [_run("before "), _run("target", bold=True, comment_ids=[ID_A, ID_B, ID_C])]
    body = build_subspan_update(live, "target", "TARGET")
    assert _styles(body)[-1] == {"bold": True, "comment_ids": [ID_A, ID_B, ID_C]}


def test_two_adjacent_runs_with_the_SAME_anchors_carry_when_the_span_crosses_them():
    """Uniform region, uniform anchors: the region has one determinate answer, so the
    replacement run takes it."""
    live = [_run("Hello ", comment_ids=[ID_A]), _run("world", comment_ids=[ID_A])]
    body = build_subspan_update(live, "lo wor", "LO WOR")
    assert _styles(body) == [
        {"comment_ids": [ID_A]},   # the "Hel" prefix, still inside the anchored text
        {"comment_ids": [ID_A]},   # the replacement
        {"comment_ids": [ID_A]},   # the "ld" suffix
    ]


def test_two_adjacent_runs_with_DIFFERING_anchors_REFUSE_rather_than_guess():
    """Same style, different reviewers' anchors: the replacement's anchors would be a guess
    (whose comment does the new text belong to?), so the region is not splittable. Refusing
    is the same answer the path already gives for a disagreeing *style*."""
    live = [_run("Hello ", comment_ids=[ID_A]), _run("world", comment_ids=[ID_B])]
    assert build_subspan_update(live, "lo wor", "LO WOR") is None


def test_a_span_that_starts_INSIDE_an_anchor_and_ends_OUTSIDE_it_refuses():
    """Half the span is anchored and half is not — extending the anchor over text nobody
    commented on is a relocation, and dropping it is the defect. Refuse."""
    live = [_run("commented ", comment_ids=[ID_A]), _run("plain")]
    assert build_subspan_update(live, "ted pla", "X") is None


def test_a_span_EXACTLY_matching_a_commented_run_carries_its_ids():
    live = [_run("intro "), _run("12.4%", comment_ids=[ID_A]), _run(" tail")]
    body = build_subspan_update(live, "12.4%", "15.0%")
    assert _elements(body) == [
        {"text_run": {"content": "intro "}},
        {"text_run": {"content": "15.0%", "text_element_style": {"comment_ids": [ID_A]}}},
        {"text_run": {"content": " tail"}},
    ]


def test_a_span_STRICTLY_INSIDE_a_commented_run_carries_onto_all_three_fragments():
    live = [_run("the 12.4% number", bold=True, comment_ids=[ID_A])]
    body = build_subspan_update(live, "12.4%", "15.0%")
    assert _elements(body) == [
        {"text_run": {"content": "the ", "text_element_style": {
            "bold": True, "comment_ids": [ID_A]}}},
        {"text_run": {"content": "15.0%", "text_element_style": {
            "bold": True, "comment_ids": [ID_A]}}},
        {"text_run": {"content": " number", "text_element_style": {
            "bold": True, "comment_ids": [ID_A]}}},
    ]


def test_an_UNTOUCHED_neighbour_run_is_byte_identical_ids_included():
    live = [
        _run("anchored neighbour", comment_ids=[ID_B]),
        _run(" | "),
        _run("target", italic=True),
    ]
    body = build_subspan_update(live, "target", "TARGET")
    assert _elements(body)[0] == {
        "text_run": {"content": "anchored neighbour",
                     "text_element_style": {"comment_ids": [ID_B]}}
    }
    assert _elements(body)[1] == {"text_run": {"content": " | "}}


def test_the_carrying_body_is_what_reaches_the_WIRE_and_costs_no_extra_call():
    """End to end through the real plan-gated engine: the PATCH body on the wire carries the
    ids, and the call count is unchanged (the anchors are already on the payload the engine
    re-reads, so nothing extra is fetched)."""
    tree = _page(_anchored_para("p1", ("Revenue grew ", None), ("12.4%", [ID_A])))
    plan = dry_run(
        [SubSpanEditRequest(anchor=Anchor(quote="Revenue grew"), span="12.4%",
                            replacement="15.0%")],
        tree,
    )
    opener = StubOpener([
        _block_payload("p1", [_run("Revenue grew "), _run("12.4%", bold=True,
                                                          comment_ids=[ID_A])]),
        _patch_ok(),
    ])
    log = apply(plan, _client(opener), "doc123")

    assert log.entries[0].outcome == "applied"
    assert [r["method"] for r in opener.requests] == ["GET", "PATCH"]   # no extra read
    assert opener.requests[1]["body"] == {"update_text_elements": {"elements": [
        {"text_run": {"content": "Revenue grew "}},
        {"text_run": {"content": "15.0%", "text_element_style": {
            "bold": True, "comment_ids": [ID_A]}}},
    ]}}


def _subspan_refusal_over(live, span="lo wor"):
    """Drive the real engine to the write-time ``span-not-splittable`` refusal and return it."""
    text = "".join(el["text_run"]["content"] for el in live)
    tree = _page(_para("p1", text))
    plan = dry_run(
        [SubSpanEditRequest(anchor=AnchorById(block_id="p1"), span=span, replacement="X")],
        tree,
    )
    assert plan.entries[0].is_resolved, plan.entries[0].to_dict()
    opener = StubOpener([_block_payload("p1", live)])
    log = apply(plan, _client(opener), "doc123")
    assert [r["method"] for r in opener.requests] == ["GET"]    # read, then refuse — no write
    entry = log.entries[0]
    assert entry.refusal.reason is RefusalReason.SPAN_NOT_SPLITTABLE
    return entry.refusal.detail


def test_the_subspan_refusal_does_NOT_send_an_ANCHORED_block_to_the_path_that_also_refuses():
    """A refusal must name a recovery that works. The shipped wording said "edit the whole
    paragraph instead", which is now a dead end for a block carrying anchors — that path
    refuses on the same anchors. So the anchored case gets its own paragraph."""
    detail = _subspan_refusal_over(
        [_run("Hello ", comment_ids=[ID_A]), _run("world", comment_ids=[ID_B])])
    lowered = detail.lower()
    assert "review anchor" in lowered or "comment anchor" in lowered, detail
    assert "narrow the span" in lowered, detail
    assert "comment-anchors-present" in lowered, detail
    assert "will not help" in lowered, detail


def test_the_subspan_refusal_detail_is_UNCHANGED_when_no_anchor_is_involved():
    """The common case's shipped wording, verbatim — the anchored branch must not disturb the
    message every existing consumer already reads."""
    detail = _subspan_refusal_over([_run("Hello ", bold=True), _run("world", italic=True)])
    assert detail == (
        "the span 'lo wor' in block p1 does not map to exactly one uniformly-styled run "
        "region — it crosses runs of differing style or overlaps a non-text inline "
        "(mention / equation), so the replacement style would be a guess; edit the whole "
        "paragraph instead, or narrow the span to one styled run"
    )


# --------------------------------------------------------------------------- #
# AC3 — THE ELEMENT-LEVEL PATH REFUSES, TYPED, IN THE HOUSE DETAIL STANDARD     #
# --------------------------------------------------------------------------- #

def test_the_new_reason_exists_and_is_spelled_in_the_family_style():
    assert RefusalReason.COMMENT_ANCHORS_PRESENT.value == "comment-anchors-present"
    assert RefusalReason("comment-anchors-present") is RefusalReason.COMMENT_ANCHORS_PRESENT
    assert callable(Refusal.comment_anchors_present)
    assert Refusal.comment_anchors_present(detail="d").reason is (
        RefusalReason.COMMENT_ANCHORS_PRESENT)


def test_no_EXISTING_reason_changed_its_meaning():
    """The new member joins the family; it does not reshuffle it."""
    assert {r.name: r.value for r in RefusalReason} == {
        "AMBIGUOUS": "ambiguous-N-candidates",
        "NOT_FOUND": "not-found",
        "WRITE_HOSTILE": "write-hostile-target",
        "STALE_ANCHOR": "stale-anchor",
        "COLUMN_NOT_FOUND": "column-not-found",
        "CANNOT_HOLD_CHILDREN": "cannot-hold-children",
        "CANNOT_HOLD_SIBLINGS": "cannot-hold-siblings",
        "SPAN_NOT_SPLITTABLE": "span-not-splittable",
        "MERGE_NOT_EXPRESSIBLE": "merge-not-expressible",
        # LD-574 — the compiled-no-op refusal. Added, never renamed: every
        # existing member above keeps its own wire value byte for byte.
        "CHANGE_NOT_EXPRESSIBLE": "change-not-expressible",
        # LD-575 — the table-grow boundary. Added, never renamed: every existing member above
        # and below keeps its own wire value byte for byte.
        "TABLE_GROW_UNSUPPORTED": "table-grow-unsupported",
        "NOT_IN_DIALECT": "not-in-dialect",
        "STALE_DOCUMENT": "stale-document",
        "COMMENT_ANCHORS_PRESENT": "comment-anchors-present",
        # The comment WRITE ops' three (LD-202) — added deliberately, and note that this
        # test's actual subject is unmoved: no reason above changed its name or its value,
        # so a consumer branching on any of them needs no new branch.
        "COMMENT_ANCHOR_NOT_CREATABLE": "comment-anchor-not-creatable",
        "COMMENT_SURFACE_UNSUPPORTED": "comment-surface-unsupported",
        "COMMENT_THREAD_NOT_SOLELY_AUTHORED": "comment-thread-not-solely-authored",
        # The reconciler's eight (LD-233) — same note: each is about an edited projection
        # coming back in, and no reason above changed its name or its value.
        "MARKER_INVENTED": "marker-invented",
        "MARKER_DUPLICATED": "marker-duplicated",
        "MARKER_ABSENT": "marker-absent",
        # The four that complete the loss taxonomy (LD-235) — added deliberately, same
        # note: no reason above changed its name or its value, and `marker-absent` still
        # means exactly what it meant (marker AND content both gone). `marker-dropped` is
        # the strictly narrower case it could not previously tell apart.
        "MARKER_DROPPED": "marker-dropped",
        "MARKER_RELOCATED": "marker-relocated",
        "MARKER_MANGLED": "marker-mangled",
        "MARKER_ORPHANED": "marker-orphaned",
        "MARKER_ORDER_CHANGED": "marker-order-changed",
        "BLOCK_TYPE_MUTATION": "block-type-mutation",
        "SEGMENT_AMBIGUOUS": "segment-ambiguous",
        "UNMARKED_CONTENT_CHANGED": "unmarked-content-changed",
        "UNDECODABLE_TEXT": "undecodable-text",
        # The twelfth taxonomy row, ruled in later (LD-235, fixing LD-238): a plan that
        # conserves a block must never ALSO plan that block's own content as new. Same
        # note again — no reason above changed its name or its value.
        "CONSERVED_BLOCK_RE_CREATED": "conserved-block-re-created",
        # LD-643 — the APPLY-TIME disposition family. Added at the tail, never renamed: every
        # existing member above keeps its own wire value byte for byte, and none of these
        # re-uses or re-points one. Seven of the eight are deliberately the SAME wire values
        # the sheets and Base engines publish, so one condition does not get two names across
        # two engines; `pagination-unterminated` is this surface's own.
        "API_ERROR": "api-error",
        "PERMISSION_DENIED": "permission-denied",
        "RATE_LIMITED": "rate-limited",
        "TRANSPORT_FAILURE": "transport-failure",
        "PAGINATION_UNTERMINATED": "pagination-unterminated",
        "UNEXPECTED_ERROR": "unexpected-error",
        "UNVERIFIED_WRITE": "unverified-write",
        "NOT_ATTEMPTED": "not-attempted",
    }


def _refused_element_level(**kwargs):
    tree = _page(_anchored_para(
        "p1", ("The quarterly revenue grew ", None), ("12.4%", [ID_A]),
        ("in Q3.", None), **kwargs))
    plan = dry_run([_req("quarterly revenue", replacement="NEW TEXT")], tree)
    (entry,) = plan.entries
    return entry


def test_a_whole_block_edit_on_an_inline_anchored_block_REFUSES():
    entry = _refused_element_level()
    assert not entry.is_resolved
    assert entry.refusal.reason is RefusalReason.COMMENT_ANCHORS_PRESENT


def test_the_refusal_detail_names_WHAT_WHY_and_THE_RECOVERY_THAT_WORKS():
    """The D13 bar — a paragraph a consumer could paste to another user: what is in the way,
    why this path cannot honor it, and the path that can."""
    detail = _refused_element_level().refusal.detail
    lowered = detail.lower()
    assert "p1" in detail, detail                              # the resolved block
    assert ID_A in detail, detail                              # the anchor in the way
    assert "comment" in lowered, detail                        # WHAT
    assert "one run" in lowered or "single run" in lowered, detail   # WHY
    assert "sub-span" in lowered, detail                       # the RECOVERY
    assert len(detail.split()) >= 40, f"too terse for the house standard: {detail}"
    assert detail.strip()[0].islower() or detail.strip()[0].isupper()


def test_the_refusal_detail_carries_NO_internal_dialect():
    """It is a shipped consumer-facing string."""
    import consumer_text
    assert not consumer_text.dialect_hits(_refused_element_level().refusal.detail)


def test_the_refusal_names_the_recovery_the_engine_ACTUALLY_HAS():
    """The recovery a detail names must work. The identical block, sub-span-edited, resolves
    — so the paragraph is not sending a consumer somewhere that also refuses."""
    tree = _page(_anchored_para(
        "p1", ("The quarterly revenue grew ", None), ("12.4%", [ID_A])))
    plan = dry_run(
        [SubSpanEditRequest(anchor=Anchor(quote="quarterly revenue"), span="12.4%",
                            replacement="15.0%")],
        tree,
    )
    assert plan.entries[0].is_resolved, plan.entries[0].to_dict()


def test_the_refusal_survives_the_plan_wire_format():
    entry = _refused_element_level()
    wire = json.loads(json.dumps(entry.to_dict()))
    assert wire["refusal"]["reason"] == "comment-anchors-present"
    assert wire["refusal"]["detail"] == entry.refusal.detail


# --------------------------------------------------------------------------- #
# AC4 — PRE-I/O, AND THE BATCH CONTRACT IS HONORED                              #
# --------------------------------------------------------------------------- #

def test_the_refusal_is_decided_at_PLAN_time_before_any_client_exists():
    """``dry_run`` takes no client and opens no socket: the information is already on the
    model, so the refusal cannot be a write-time discovery."""
    entry = _refused_element_level()
    assert not entry.is_resolved and entry.refusal.reason is (
        RefusalReason.COMMENT_ANCHORS_PRESENT)


def test_a_batch_holding_only_such_an_edit_issues_ZERO_writes():
    tree = _page(_anchored_para("p1", ("commented text here", [ID_A])))
    plan = dry_run([_req("commented text", replacement="NEW")], tree)
    opener = StubOpener([])                     # any request at all would IndexError
    log = apply(plan, _client(opener), "doc123")
    assert opener.requests == []                # the call-count spy: zero API calls
    assert log.entries[0].refusal.reason is RefusalReason.COMMENT_ANCHORS_PRESENT


def test_a_MIXED_batch_writes_nothing_for_the_refused_entry():
    """The batch contract: a refused entry contributes **zero** writes. The per-entry skip is
    the docx engine's shipped semantics for every reason except ``stale-document`` (which is
    the document-wide compare-and-swap), so the entries around it still apply — and the
    proof that nothing leaked is the request log: exactly one GET + one PATCH, both for the
    unanchored block."""
    tree = _page(
        _anchored_para("p1", ("commented text here", [ID_A])),
        _para("p2", "plain text here"),
    )
    plan = dry_run(
        [_req("commented text", replacement="NEW A"), _req("plain text", replacement="NEW B")],
        tree,
    )
    opener = StubOpener([_block_payload("p2", [_run("plain text here")]), _patch_ok()])
    log = apply(plan, _client(opener), "doc123")

    assert log.entries[0].refusal.reason is RefusalReason.COMMENT_ANCHORS_PRESENT
    assert log.entries[1].outcome == "applied"
    assert [r["method"] for r in opener.requests] == ["GET", "PATCH"]
    assert opener.requests[0]["url"].endswith("blocks/p2?document_revision_id=-1")


def test_a_batch_of_only_anchored_edits_writes_nothing_at_all():
    tree = _page(
        _anchored_para("p1", ("first commented line", [ID_A])),
        _anchored_para("p2", ("second commented line", [ID_B])),
    )
    plan = dry_run(
        [_req("first commented", replacement="A"), _req("second commented", replacement="B")],
        tree,
    )
    opener = StubOpener([])
    log = apply(plan, _client(opener), "doc123")
    assert opener.requests == []
    assert [e.refusal.reason for e in log.entries] == [
        RefusalReason.COMMENT_ANCHORS_PRESENT, RefusalReason.COMMENT_ANCHORS_PRESENT]


def test_the_element_level_builder_NEVER_relocates_the_leading_runs_anchors():
    """The rejected leading-run variant, structurally excluded. The path refuses before it
    reaches the builder, but the builder is shared (a whole-CELL edit rides it too), so it
    must never carry an anchor onto the collapsed run: that would move a reviewer's comment
    onto text they never commented on."""
    live = [_run("anchored lead", bold=True, comment_ids=[ID_A]),
            _run(" tail", comment_ids=[ID_B])]
    body = build_whole_paragraph_update(live, "A WHOLE NEW PARAGRAPH")
    assert _elements(body) == [
        {"text_run": {"content": "A WHOLE NEW PARAGRAPH",
                      "text_element_style": {"bold": True}}}
    ]
    assert "comment_ids" not in json.dumps(body)


@pytest.mark.parametrize("geometry", ["inside", "spanning", "neighbour"])
def test_the_element_level_body_is_byte_identical_to_the_captured_payload(geometry):
    """AC5's golden-style pin on the common path, taken from the spike's own capture: the
    element-level body this fix emits is the body that shipped before it."""
    leg = _geometry(geometry)
    body = build_whole_paragraph_update(leg["live_elements_in"], _WHOLE_PARAGRAPH_REPLACEMENT)
    assert body == leg["element_level_body"]


# --------------------------------------------------------------------------- #
# AC5 — NO FALSE REFUSALS (absent vs present-but-empty vs populated)            #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("ids,refuses", [
    (None, False),   # the field is ABSENT on the run — nothing is anchored
    ([], False),     # PRESENT BUT EMPTY — the API said nothing is anchored here
    ([ID_A], True),  # populated — a reviewer really is anchored inside this block
])
def test_absent_and_empty_both_mean_PROCEED(ids, refuses):
    """The distinction the model deliberately keeps must not become a false refusal. (An
    empty list is the server's option, not an observed shape — the round-2 harvest saw 457
    absent and zero empty — so this arm pins the defensive branch, not a reality claim.)"""
    tree = _page(_anchored_para("p1", ("commented text here", ids)))
    (entry,) = dry_run([_req("commented text", replacement="NEW")], tree).entries
    assert (not entry.is_resolved) is refuses, entry.to_dict()
    if not refuses:
        assert entry.block_id == "p1"


def test_a_plain_unanchored_block_edits_with_a_BYTE_IDENTICAL_body():
    """The common path, pinned as a golden: an ordinary paragraph's emitted body is exactly
    what it always was."""
    tree = _page(_para("p1", "Revenue grew 67% this quarter."))
    plan = dry_run([_req("Revenue grew 67% this quarter.", replacement="Revenue grew 72%.")],
                   tree)
    opener = StubOpener([
        _block_payload("p1", [_run("Revenue grew 67% this quarter.", bold=True)]),
        _patch_ok(),
    ])
    apply(plan, _client(opener), "doc123")
    assert opener.requests[1]["body"] == {"update_text_elements": {"elements": [
        {"text_run": {"content": "Revenue grew 72%.",
                      "text_element_style": {"bold": True}}}
    ]}}


def test_an_unanchored_subspan_body_is_byte_identical_too():
    live = [_run("The value "), _run("12.4%", bold=True), _run(" holds.")]
    assert build_subspan_update(live, "12.4%", "15.0%") == {"update_text_elements": {
        "elements": [
            {"text_run": {"content": "The value "}},
            {"text_run": {"content": "15.0%", "text_element_style": {"bold": True}}},
            {"text_run": {"content": " holds."}},
        ]}}


def test_an_EMPTY_id_list_on_the_wire_payload_adds_no_key():
    """The rebuild's own half of the same rule: an empty list carries no anchor, so it adds
    nothing to the emitted body (a key that says nothing is noise on the wire)."""
    live = [{"text_run": {"content": "x", "text_element_style": {
        "bold": True, "comment_ids": []}}}]
    assert to_write_elements(live) == [
        {"text_run": {"content": "x", "text_element_style": {"bold": True}}}]


# --------------------------------------------------------------------------- #
# AC6 — BLOCK-LEVEL vs WORD-LEVEL ANCHORS ARE DISTINGUISHED                     #
# --------------------------------------------------------------------------- #

def test_a_BLOCK_LEVEL_only_anchor_PROCEEDS_on_the_element_level_path():
    """The conflation risk the dual-granularity capture creates. A block-level anchor is not
    attached to any passage inside the block, so the whole-paragraph rebuild does not destroy
    it — refusing on it would be a false refusal on a shipped path."""
    tree = _page(_anchored_para("p1", ("commented text here", None), block_ids=[ID_A]))
    (entry,) = dry_run([_req("commented text", replacement="NEW")], tree).entries
    assert entry.is_resolved, entry.to_dict()
    assert entry.block_id == "p1"


def test_a_BLOCK_LEVEL_only_anchor_PROCEEDS_on_the_sub_span_path_too():
    tree = _page(_anchored_para("p1", ("The value 12.4% holds.", None), block_ids=[ID_A]))
    (entry,) = dry_run(
        [SubSpanEditRequest(anchor=Anchor(quote="The value"), span="12.4%",
                            replacement="15.0%")],
        tree,
    ).entries
    assert entry.is_resolved, entry.to_dict()


def test_a_WORD_LEVEL_anchor_refuses_even_when_the_BLOCK_carries_none():
    tree = _page(_anchored_para("p1", ("commented text here", [ID_A]), block_ids=None))
    (entry,) = dry_run([_req("commented text", replacement="NEW")], tree).entries
    assert not entry.is_resolved
    assert entry.refusal.reason is RefusalReason.COMMENT_ANCHORS_PRESENT


def test_both_granularities_together_still_refuse_and_the_detail_names_the_WORD_level_ids():
    tree = _page(_anchored_para(
        "p1", ("plain ", None), ("commented text here", [ID_B]), block_ids=[ID_A]))
    (entry,) = dry_run([_req("commented text", replacement="NEW")], tree).entries
    assert entry.refusal.reason is RefusalReason.COMMENT_ANCHORS_PRESENT
    assert ID_B in entry.refusal.detail, entry.refusal.detail


def test_an_EMPTY_word_level_list_beside_a_populated_BLOCK_level_one_proceeds():
    tree = _page(_anchored_para("p1", ("commented text here", []), block_ids=[ID_A, ID_B]))
    (entry,) = dry_run([_req("commented text", replacement="NEW")], tree).entries
    assert entry.is_resolved, entry.to_dict()


# --------------------------------------------------------------------------- #
# THE THIRD PATH — the whole-CELL edit, which now refuses on the same anchors    #
# --------------------------------------------------------------------------- #

def test_the_whole_CELL_path_also_refuses_and_the_shared_builder_still_DROPS():
    """Supersedes the characterization that pinned the cell path as a KNOWN silent drop.

    A table-cell edit resolves a **cell** through its own locator and then patches the cell's
    inner text block with the **same** collapsing builder a whole-paragraph edit uses. It now
    carries its own plan-time precondition too, so it **refuses** rather than collapse a
    reviewer's anchors away — see ``tests/test_comment_anchor_cell_path.py`` for that path's
    own suite (its refusal names the row/column and the by-id sub-span recovery a cell locator
    cannot express).

    What stays true, and is pinned here because *this* file owns the builder: the shared
    collapsing builder still **strips** the ids. It is a drop, never a *relocation* of the
    leading run's anchor onto the rewritten text — the variant that was rejected — and the
    refusals on both paths are what keep the drop unreachable through a plan."""
    live = [_run("On-time delivery", comment_ids=[ID_A])]
    body = build_whole_paragraph_update(live, "REWRITTEN CELL")
    assert body == {"update_text_elements": {"elements": [
        {"text_run": {"content": "REWRITTEN CELL"}}]}}
    assert "comment_ids" not in json.dumps(body)


# --------------------------------------------------------------------------- #
# AC8 — THE TRUTH ROWS: the discovery surfaces carry the new reason + recovery   #
# --------------------------------------------------------------------------- #

def _guide() -> str:
    from larkdocio import guide
    return guide(full=True)


def _floor() -> dict:
    from larkdocio import capabilities
    return capabilities(full=True)["surfaces"]["docx-write"]["content_constraints"]


def test_the_capability_registry_states_the_per_path_comment_anchor_policy():
    """A consumer planning an integration reads the registry, not the source. The row must
    name the refusal reason **and** the recovery — a reason with no recovery is the dead end
    the house standard forbids."""
    rows = " ".join(_floor()["editable_not_creatable"]).lower()
    assert "comment-anchors-present" in rows, rows
    assert "sub-span" in rows, rows
    assert "whole-block" in rows, rows


def test_the_shipped_guide_names_the_new_refusal_and_its_recovery():
    text = _guide()
    assert "comment-anchors-present" in text
    lowered = text.lower()
    # the recovery, in the refusal section AND the sub-span recipe.
    assert "recipe: edit part of a paragraph" in lowered
    section = lowered.split("comment-anchors-present", 1)[1][:1200]
    assert "sub-span" in section, section[:400]


def test_the_shipped_guide_states_the_block_level_vs_word_level_distinction():
    """The distinction is the one most likely to surprise a consumer whose document has
    block-level comments: those do NOT refuse, and the guide has to say so."""
    lowered = _guide().lower()
    assert "block-level" in lowered
    window = lowered.split("comment-anchors-present", 1)[1][:1500]
    assert "block-level" in window, window[:400]


def test_the_release_notes_announce_the_new_refusal_code():
    """The notes' own INCLUDE rule: "a new or renamed refusal code" is a consumer-observable
    change, and a caller switching on refusal reasons needs the branch.

    **LD-540 — the window, and why this is asserted over a DERIVED set of copies.** The wheel
    now carries a recent-N window of each release document while the repository keeps the whole
    history, so "this claim is written down" and "this claim ships" stopped being one sentence.
    ``test_shipped_notes.notes_claim_copies`` answers which copies must carry it: the root
    always (a deletion from the authoring source reddens with full force), and the packaged
    window whenever it still holds the section — and if it does not, that helper PROVES the
    section is genuinely out of window rather than letting the claim go missing. Nothing was
    weakened and no copy was dropped by hand.

    The byte-identity half is delegated to the one function that owns it rather than re-spelled.
    """
    from test_shipped_notes import notes_claim_copies, notes_identity_report

    assert notes_identity_report() == []
    copies = notes_claim_copies("RELEASE_NOTES.md", "comment-anchors-present")
    for label, text in copies:
        assert "comment-anchors-present" in text, label


def test_every_new_consumer_facing_string_is_dialect_free():
    """No issue ids, no requirement ids, no criterion numbers on a shipped surface."""
    import consumer_text
    from larkdocio import capabilities

    strings = [row for row in
               capabilities(full=True)["surfaces"]["docx-write"]["content_constraints"][
                   "editable_not_creatable"]
               if "comment" in row.lower()]
    strings.append(_refused_element_level().refusal.detail)
    strings.extend(s for s in _guide().split("\n") if "comment-anchors-present" in s)
    assert len(strings) >= 3, strings
    for text in strings:
        assert not consumer_text.dialect_hits(text), text
