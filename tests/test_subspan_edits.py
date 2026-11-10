"""Offline unit tests for sub-span edits (LD-077, W3-S4).

Sub-span editing changes a **quoted span WITHIN a paragraph** without replacing the whole
paragraph: it **splits the matched run(s) at the span boundaries, mutates ONLY the span,
and preserves the surrounding run styles** — the ``to_write_elements`` element-level
discipline (spike Test 4: styled-run patching preserves style; the "silent killer" only
bites a lossy Markdown rebuild, which this path never does).

The **exactly-one-or-refuse invariant is absolute** (maintainer directive): a span that cannot be
mapped to **exactly one uniformly-styled contiguous run region** — because it crosses runs
of **differing** style, or overlaps a **non-text** inline (mention / equation), or occurs
**≠1** time — **refuses** (``span-not-splittable`` / ``not-found`` / ``stale-anchor``),
never guesses a replacement style, never corrupts. The common case (a value like ``67%``
sitting inside a uniformly-styled run) applies surgically.

Spans model → resolve → preview → apply, so these tests exercise the whole chain: the
findings-agnostic :class:`SubSpanEditRequest`, its resolution + dry-run preview, and the
element-level apply (injected transport, no network). The sub-span live WRITE round-trip
folds into S5 (LD-078); goldens stay ZERO-DRIFT (no reader surface is touched).
"""
import json

import pytest

from log_reading_apply import reading_the_log
from larkdocio.model import ImageNode, MentionUser, Text
from larkdocio.write.apply import apply, build_subspan_update
apply = reading_the_log(apply)
from larkdocio.write.client import WriteClient
from larkdocio.write.model import (
    Anchor,
    ApplyLog,
    EditRequest,
    RefusalReason,
    SubSpanEditRequest,
    _request_from_dict,
)
from larkdocio.write.preview import Plan, PlanEntry, dry_run

# Shared fake-transport doubles + node/request builders (LD-088).
from write_harness import (
    FakeClock,
    StubOpener,
    _block_payload,
    _client,
    _methods,
    _page,
    _para,
    _patch_ok,
    _run,
)


# --------------------------------------------------------------------------- #
# request builder — SubSpanEditRequest (file-local; the shared node builders    #
# _para / _page live in write_harness)                                          #
# --------------------------------------------------------------------------- #

def _subspan(quote, span, replacement, *, breadcrumb=()):
    return SubSpanEditRequest(
        anchor=Anchor(quote=quote, breadcrumb=breadcrumb), span=span, replacement=replacement
    )


# --------------------------------------------------------------------------- #
# file-local helpers: a non-text inline + the sub-span element extractor.        #
# The fake transport + _run / _block_payload / _patch_ok / _methods live in     #
# write_harness.                                                                 #
# --------------------------------------------------------------------------- #

def _mention_user(user_id="u1"):
    """A non-text inline element (a mention) that carries no quotable text run."""
    return {"mention_user": {"user_id": user_id}}


def _elements(opener, i):
    return opener.requests[i]["body"]["update_text_elements"]["elements"]


# =========================================================================== #
# Model — SubSpanEditRequest (findings-agnostic; op-tagged; round-trippable)   #
# =========================================================================== #

def test_subspan_request_round_trips_through_json():
    req = _subspan("On-time delivery was 67% overall.", "67%", "72%", breadcrumb=("KPIs",))
    d = req.to_dict()
    assert d["op"] == "subspan"
    assert d["span"] == "67%"
    assert d["replacement"] == "72%"
    restored = SubSpanEditRequest.from_dict(json.loads(json.dumps(d)))
    assert restored == req
    assert restored.anchor.breadcrumb == ("KPIs",)


def test_request_dispatch_includes_subspan_and_edit_stays_tagless():
    sub = _subspan("q here", "here", "there")
    edit = EditRequest(anchor=Anchor(quote="q"), replacement="r")
    assert "op" not in edit.to_dict()                       # W1 EditRequest unchanged
    assert sub.to_dict()["op"] == "subspan"
    assert isinstance(_request_from_dict(sub.to_dict()), SubSpanEditRequest)
    assert isinstance(_request_from_dict(edit.to_dict()), EditRequest)
    assert _request_from_dict(json.loads(json.dumps(sub.to_dict()))) == sub


def test_subspan_request_exported_from_write_package():
    import larkdocio.write as w
    assert w.SubSpanEditRequest is SubSpanEditRequest
    assert "SubSpanEditRequest" in w.__all__


def test_empty_span_is_rejected_at_construction():
    # A span that locates nothing is meaningless (an empty string is a substring of every
    # block) — reject it, exactly as InsertRequest rejects empty content.
    with pytest.raises(ValueError):
        SubSpanEditRequest(anchor=Anchor(quote="q"), span="", replacement="x")


# =========================================================================== #
# Resolve — block exactly-one-or-refuse (reused) + span exactly-one-or-refuse  #
# =========================================================================== #

def test_subspan_resolves_when_block_and_span_are_unique():
    tree = _page(_para("p1", "Revenue grew 67 percent overall."))
    plan = dry_run([_subspan("Revenue grew 67 percent overall.", "67", "72")], tree)
    (entry,) = plan.entries
    assert entry.is_subspan and entry.is_resolved
    assert entry.block_id == "p1"


def test_subspan_span_absent_from_block_is_not_found():
    tree = _page(_para("p1", "Revenue grew 67 percent."))
    plan = dry_run([_subspan("Revenue grew 67 percent.", "88", "90")], tree)
    (entry,) = plan.entries
    assert not entry.is_resolved
    assert entry.refusal.reason is RefusalReason.NOT_FOUND


def test_subspan_span_ambiguous_within_block_refuses_not_splittable():
    # The span occurs MORE THAN ONCE in the resolved block → not exactly one region.
    tree = _page(_para("p1", "the cat and the mat"))
    plan = dry_run([_subspan("the cat and the mat", "the", "THE")], tree)
    (entry,) = plan.entries
    assert not entry.is_resolved
    assert entry.refusal.reason is RefusalReason.SPAN_NOT_SPLITTABLE


def test_subspan_block_ambiguous_reuses_the_narrative_refusal():
    tree = _page(_para("a", "twin line"), _para("b", "twin line"))
    plan = dry_run([_subspan("twin line", "twin", "TWIN")], tree)
    (entry,) = plan.entries
    assert not entry.is_resolved
    assert entry.refusal.reason is RefusalReason.AMBIGUOUS
    assert set(entry.refusal.candidate_ids) == {"a", "b"}


def test_subspan_write_hostile_block_reuses_the_narrative_refusal():
    tree = _page(ImageNode(caption="quarterly chart 67", block_id="img"))
    plan = dry_run([_subspan("quarterly chart 67", "67", "72")], tree)
    (entry,) = plan.entries
    assert not entry.is_resolved
    assert entry.refusal.reason is RefusalReason.WRITE_HOSTILE


# =========================================================================== #
# Preview — dry-run surfaces span + replacement (and refusals) with ZERO writes #
# =========================================================================== #

def test_subspan_plan_previews_span_and_replacement():
    tree = _page(_para("p1", "On-time delivery was 67% overall."))
    plan = dry_run([_subspan("On-time delivery was 67% overall.", "67%", "72%")], tree)
    (entry,) = plan.entries
    assert entry.is_subspan and entry.is_resolved
    assert entry.block_id == "p1"
    assert entry.span == "67%"
    assert entry.before == "67%"          # the text that WOULD be replaced (the span)
    assert entry.after == "72%"           # the replacement
    assert entry.replacement == "72%"


def test_subspan_refused_plan_still_carries_span_and_replacement():
    # A refusal still previews the intended span + replacement so an approval UX can show
    # the rejected op — mirrors edit / insert refusals.
    tree = _page(_para("p1", "nothing to see"))
    plan = dry_run([_subspan("nothing to see", "absent", "x")], tree)
    (entry,) = plan.entries
    assert entry.is_subspan and not entry.is_resolved
    assert entry.refusal.reason is RefusalReason.NOT_FOUND
    assert entry.span == "absent"
    assert entry.replacement == "x"


def test_subspan_plan_entry_round_trips_through_dict():
    tree = _page(_para("p1", "value 67 here"))
    plan = dry_run([_subspan("value 67 here", "67", "72")], tree)
    entry = plan.entries[0]
    d = entry.to_dict()
    assert d["op"] == "subspan"
    assert d["span"] == "67"
    assert PlanEntry.from_dict(d) == entry


def test_subspan_flows_through_the_non_forgeable_plan():
    tree = _page(_para("p1", "alpha 67 beta"))
    plan = dry_run([_subspan("alpha 67 beta", "67", "72")], tree)
    assert isinstance(plan, Plan)
    assert [e.op for e in plan.entries] == ["subspan"]
    with pytest.raises(TypeError):
        Plan([])


def test_dry_run_performs_zero_writes_for_a_subspan_request():
    class _SpyTransport:
        def __init__(self):
            self.executed = []

        def execute(self, fn):
            self.executed.append(fn)
            raise AssertionError("dry-run must perform ZERO writes")

    spy = _SpyTransport()
    WriteClient("app", "secret", transport=spy, token_fetcher=lambda *a, **k: "tok")
    tree = _page(_para("p1", "resolve 67 me"))
    plan = dry_run([_subspan("resolve 67 me", "67", "72")], tree)
    assert isinstance(plan, Plan)
    assert spy.executed == []


# =========================================================================== #
# Apply — AC3: whole SPAN, not whole paragraph (surgical, style-preserving)     #
# =========================================================================== #

def test_subspan_splits_one_run_and_mutates_only_the_span():
    tree = _page(_para("p1", "Revenue grew 67 percent overall"))
    plan = dry_run([_subspan("Revenue grew 67 percent overall", "67", "72")], tree)
    # live block: ONE bold run carrying the span.
    opener = StubOpener([
        _block_payload("p1", [_run("Revenue grew 67 percent overall", bold=True)]),
        _patch_ok(),
    ])
    log = apply(plan, _client(opener), "doc123")

    assert _methods(opener) == ["GET", "PATCH"]
    # the run split at the span boundaries into prefix / replacement / suffix — each
    # fragment keeps the run's bold; ONLY "67" became "72".
    assert _elements(opener, 1) == [
        {"text_run": {"content": "Revenue grew ", "text_element_style": {"bold": True}}},
        {"text_run": {"content": "72", "text_element_style": {"bold": True}}},
        {"text_run": {"content": " percent overall", "text_element_style": {"bold": True}}},
    ]
    assert log.entries[0].outcome == "applied"


# =========================================================================== #
# Apply — AC2: run-splitting preserves EVERY surrounding run's style byte-exact #
# =========================================================================== #

def test_subspan_preserves_neighbouring_run_bold_inline_code_and_colour():
    tree = _page(_para("p1", "start middle 67 text end"))
    plan = dry_run([_subspan("start middle 67 text end", "67", "72")], tree)
    # neighbours carry bold (left) and inline_code + colour (right); the span sits in a
    # PLAIN middle run.
    opener = StubOpener([
        _block_payload("p1", [
            _run("start ", bold=True),
            _run("middle 67 text"),
            _run(" end", inline_code=True, text_color=5),
        ]),
        _patch_ok(),
    ])
    apply(plan, _client(opener), "doc123")

    assert _elements(opener, 1) == [
        {"text_run": {"content": "start ", "text_element_style": {"bold": True}}},      # neighbour bold
        {"text_run": {"content": "middle "}},                                            # plain prefix
        {"text_run": {"content": "72"}},                                                 # plain replacement
        {"text_run": {"content": " text"}},                                              # plain suffix
        {"text_run": {"content": " end", "text_element_style": {"inline_code": True, "text_color": 5}}},  # neighbour code+colour
    ]


def test_subspan_across_a_same_style_run_boundary_applies_uniform_style():
    # The span crosses a run boundary but both runs share ONE style (bold) → the region
    # is uniform, so the replacement carries that single style; neighbours preserved.
    tree = _page(_para("p1", "Say Hello world now"))
    plan = dry_run([_subspan("Say Hello world now", "lo wor", "LOWOR")], tree)
    opener = StubOpener([
        _block_payload("p1", [
            _run("Say "),
            _run("Hello ", bold=True),
            _run("world", bold=True),
            _run(" now"),
        ]),
        _patch_ok(),
    ])
    apply(plan, _client(opener), "doc123")

    assert _elements(opener, 1) == [
        {"text_run": {"content": "Say "}},
        {"text_run": {"content": "Hel", "text_element_style": {"bold": True}}},
        {"text_run": {"content": "LOWOR", "text_element_style": {"bold": True}}},
        {"text_run": {"content": "ld", "text_element_style": {"bold": True}}},
        {"text_run": {"content": " now"}},
    ]


# =========================================================================== #
# Apply — AC1: exactly-one-or-refuse — the silent-killer guards (NEVER guess)   #
# =========================================================================== #

def test_subspan_across_differing_run_styles_refuses_never_guesses():
    # The span crosses a bold→plain boundary → the replacement style is ambiguous → refuse
    # (span-not-splittable). NO write — the exactly-one-or-refuse invariant is absolute.
    tree = _page(_para("p1", "Hello world"))
    plan = dry_run([_subspan("Hello world", "lo wor", "LOWOR")], tree)
    opener = StubOpener([
        _block_payload("p1", [_run("Hello ", bold=True), _run("world")]),
        # NO patch payload — a PATCH here would be a corruption bug.
    ])
    log = apply(plan, _client(opener), "doc123")

    assert _methods(opener) == ["GET"]
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason is RefusalReason.SPAN_NOT_SPLITTABLE


def test_subspan_overlapping_a_non_text_inline_refuses():
    # The span straddles a mention (a non-text element that cannot be split) → refuse.
    tree = _page(_para("m1", None, inlines=[Text("before "), MentionUser(user_id="u1"), Text(" after")]))
    plan = dry_run([_subspan("before  after", "re  af", "X")], tree)
    opener = StubOpener([
        _block_payload("m1", [_run("before "), _mention_user("u1"), _run(" after")]),
        # NO patch payload — a PATCH here would risk clobbering the mention.
    ])
    log = apply(plan, _client(opener), "doc123")

    assert _methods(opener) == ["GET"]
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason is RefusalReason.SPAN_NOT_SPLITTABLE


# =========================================================================== #
# Apply — AC4: live re-validation before the write (drift → skip, never write)  #
# =========================================================================== #

def test_subspan_stale_when_span_gone_from_live_skips_the_write():
    tree = _page(_para("p1", "the value 67 stands"))
    plan = dry_run([_subspan("the value 67 stands", "67", "72")], tree)
    # live drifted — the span is no longer present.
    opener = StubOpener([
        _block_payload("p1", [_run("the value 88 stands")]),
        # NO patch payload queued.
    ])
    log = apply(plan, _client(opener), "doc123")

    assert _methods(opener) == ["GET"]
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason is RefusalReason.STALE_ANCHOR


def test_subspan_ambiguous_when_span_now_occurs_twice_in_live_refuses():
    tree = _page(_para("p1", "67 alpha beta"))
    plan = dry_run([_subspan("67 alpha beta", "67", "72")], tree)
    # live drifted so the span now appears TWICE → not exactly one region → refuse.
    opener = StubOpener([
        _block_payload("p1", [_run("67 and 67 again")]),
        # NO patch payload queued.
    ])
    log = apply(plan, _client(opener), "doc123")

    assert _methods(opener) == ["GET"]
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason is RefusalReason.SPAN_NOT_SPLITTABLE


# =========================================================================== #
# Apply — AC4/AC5: gated, throttled, apply-logged (JSON round-trippable)        #
# =========================================================================== #

def test_subspan_apply_accepts_only_a_dry_run_plan():
    client = _client(StubOpener([]))
    with pytest.raises(TypeError):
        apply([_subspan("q here", "here", "there")], client, "doc123")


def test_subspan_apply_log_records_span_before_replacement_after_and_round_trips():
    tree = _page(_para("p1", "Revenue grew 67 percent overall"))
    plan = dry_run([_subspan("Revenue grew 67 percent overall", "67", "72")], tree)
    opener = StubOpener([
        _block_payload("p1", [_run("Revenue grew 67 percent overall", bold=True)]),
        _patch_ok(),
    ])
    log = apply(plan, _client(opener), "doc123")

    (entry,) = log.entries
    assert entry.outcome == "applied"
    assert entry.block_id == "p1"
    assert entry.before == "67"          # the span actually replaced
    assert entry.after == "72"           # the replacement
    # the apply-log round-trips losslessly.
    assert ApplyLog.from_dict(json.loads(log.to_json())).entries == log.entries


def test_subspan_writes_route_through_the_shared_throttle_not_a_raw_socket():
    tree = _page(_para("p1", "alpha 67 unique"), _para("p2", "beta 88 unique"))
    plan = dry_run([
        _subspan("alpha 67 unique", "67", "72"),
        _subspan("beta 88 unique", "88", "90"),
    ], tree)
    clock = FakeClock()
    opener = StubOpener([
        _block_payload("p1", [_run("alpha 67 unique")]), _patch_ok(),
        _block_payload("p2", [_run("beta 88 unique")]), _patch_ok(),
    ])
    apply(plan, _client(opener, clock=clock), "doc123")

    assert _methods(opener) == ["GET", "PATCH", "GET", "PATCH"]
    # the 4th call in the same second was PACED by the ≤3/sec limiter — proof the engine
    # routed through common/transport.py, not a raw socket.
    assert clock.sleeps == [1.0]


# =========================================================================== #
# build_subspan_update — the pure element-level builder (contract lock)         #
# =========================================================================== #

def test_build_subspan_update_returns_none_when_span_crosses_differing_styles():
    live = [_run("Hello ", bold=True), _run("world")]
    assert build_subspan_update(live, "lo wor", "X") is None   # ambiguous style → caller refuses


def test_build_subspan_update_is_element_level_for_a_clean_uniform_span():
    live = [_run("Revenue grew 67 percent overall", bold=True)]
    body = build_subspan_update(live, "67", "72")
    assert body == {"update_text_elements": {"elements": [
        {"text_run": {"content": "Revenue grew ", "text_element_style": {"bold": True}}},
        {"text_run": {"content": "72", "text_element_style": {"bold": True}}},
        {"text_run": {"content": " percent overall", "text_element_style": {"bold": True}}},
    ]}}


# =========================================================================== #
# Dispatch — sub-span coexists with a whole-paragraph edit in ONE gated batch    #
# =========================================================================== #

def test_edit_and_subspan_apply_in_one_batch_without_cross_routing():
    tree = _page(
        _para("e", "edit this whole paragraph"),
        _para("s", "the score was 67 today"),
    )
    plan = dry_run([
        EditRequest(anchor=Anchor(quote="edit this whole paragraph"), replacement="edited whole"),
        _subspan("the score was 67 today", "67", "72"),
    ], tree)
    assert [e.op for e in plan.entries] == ["edit", "subspan"]

    opener = StubOpener([
        _block_payload("e", [_run("edit this whole paragraph")]), _patch_ok(),   # edit: GET + PATCH
        _block_payload("s", [_run("the score was 67 today")]), _patch_ok(),      # subspan: GET + PATCH
    ])
    log = apply(plan, _client(opener), "doc123")

    assert _methods(opener) == ["GET", "PATCH", "GET", "PATCH"]
    assert [e.outcome for e in log.entries] == ["applied", "applied"]
    # the whole-paragraph edit collapsed to ONE run; the sub-span split only "67" → "72".
    assert _elements(opener, 1) == [{"text_run": {"content": "edited whole"}}]
    assert _elements(opener, 3) == [
        {"text_run": {"content": "the score was "}},
        {"text_run": {"content": "72"}},
        {"text_run": {"content": " today"}},
    ]
