"""Offline unit tests for the whole-paragraph apply engine (LD-068).

W1-S4 executes an approved **dry-run plan** (LD-067) against Lark. For each **resolved**
edit the engine patches the target block's text via the W0 :class:`WriteClient` using an
**element-level** ``update_text_elements`` body whose runs are rebuilt with the
style-preserving :func:`to_write_elements` pattern (§ Decision (d): **whole-paragraph**
granularity, maintainer-settled). Because docx writes default to ``document_revision_id=-1``
(no compare-and-swap — the spike's warning), the engine **re-validates the anchor against
the live block right before each write** (:meth:`WriteClient.get_block`, quote still a
substring?) and **refuses with ``stale-anchor`` + skips** on drift. Writes are **throttled**
through W0's transport and every processed edit produces an **apply-log** record.

These are all offline (a fake clock + a stub opener, no network): the plan is produced by
the real :func:`dry_run` (the hard gate — only a resolver-backed plan reaches apply), and
the live block is a stubbed :meth:`get_block` payload. The full write round-trip is S5.
"""
import inspect
import json

import pytest

from log_reading_apply import reading_the_log
from larkdocio.model import ImageNode
from larkdocio.write.apply import apply, build_whole_paragraph_update
apply = reading_the_log(apply)
from larkdocio.write.model import ApplyLog, RefusalReason
from larkdocio.write.preview import Plan, dry_run

# Shared fake-transport doubles + node/request builders (LD-088).
from write_harness import (
    FakeClock,
    StubOpener,
    _block_payload,
    _client,
    _heading,
    _page,
    _para,
    _patch_ok,
    _req,
    _run,
)


# --------------------------------------------------------------------------- #
# The hard gate (closes LD-067 co-verified AC3): apply accepts ONLY a Plan       #
# --------------------------------------------------------------------------- #

def test_apply_accepts_only_a_dry_run_plan_not_raw_records():
    client = _client(StubOpener([]))
    with pytest.raises(TypeError):
        apply([], client, "doc123")                 # a bag of records is not a Plan
    with pytest.raises(TypeError):
        apply(_req("x"), client, "doc123")           # a raw EditRequest is not a Plan
    with pytest.raises(TypeError):
        apply([_req("x")], client, "doc123")         # a list of raw EditRequests either


def test_apply_signature_takes_the_plan_first():
    params = list(inspect.signature(apply).parameters)
    assert params[0] == "plan"


def test_a_real_dry_run_plan_is_accepted():
    tree = _page(_para("p1", "accept me please"))
    plan = dry_run([_req("accept me please", replacement="accepted")], tree)
    assert isinstance(plan, Plan)
    opener = StubOpener([_block_payload("p1", [_run("accept me please")]), _patch_ok()])
    log = apply(plan, _client(opener), "doc123")
    assert log.entries[0].outcome == "applied"


# --------------------------------------------------------------------------- #
# AC1 — element-level, style-preserving patch                                   #
# --------------------------------------------------------------------------- #

def test_patch_body_is_element_level_and_preserves_leading_run_style():
    tree = _page(_para("p1", "Revenue grew 67% this quarter."))
    plan = dry_run(
        [_req("Revenue grew 67% this quarter.", replacement="Revenue grew 72% this quarter.")],
        tree,
    )
    # live block: a BOLD run still carrying the quote.
    opener = StubOpener([
        _block_payload("p1", [_run("Revenue grew 67% this quarter.", bold=True)]),
        _patch_ok(),
    ])
    apply(plan, _client(opener), "doc123")

    patch_req = opener.requests[1]
    assert patch_req["method"] == "PATCH"
    # element-level update_text_elements (not a lossy Markdown rebuild); bold preserved.
    assert patch_req["body"] == {
        "update_text_elements": {"elements": [
            {"text_run": {
                "content": "Revenue grew 72% this quarter.",
                "text_element_style": {"bold": True},
            }}
        ]}
    }


def test_build_whole_paragraph_update_preserves_color_and_link_of_leading_run():
    # The build helper rebuilds the leading run via to_write_elements: color + link on
    # the leading run survive; the trailing run's style is dropped (whole-paragraph).
    live = [_run("old", text_color=5, link={"url": "https%3A%2F%2Fx"}), _run(" tail", bold=True)]
    body = build_whole_paragraph_update(live, "a whole new paragraph")
    (el,) = body["update_text_elements"]["elements"]
    assert el["text_run"]["content"] == "a whole new paragraph"
    assert el["text_run"]["text_element_style"] == {"text_color": 5, "link": {"url": "https%3A%2F%2Fx"}}


def test_build_whole_paragraph_update_plain_paragraph_carries_no_style_key():
    body = build_whole_paragraph_update([_run("plain old text")], "brand new text")
    (el,) = body["update_text_elements"]["elements"]
    assert el == {"text_run": {"content": "brand new text"}}


# --------------------------------------------------------------------------- #
# AC2 — whole-paragraph granularity (the whole ¶ is the unit of change)          #
# --------------------------------------------------------------------------- #

def test_whole_paragraph_is_the_unit_of_change():
    tree = _page(_para("p1", "Hello world from Q3."))
    plan = dry_run([_req("Hello world from Q3.", replacement="Farewell everyone.")], tree)
    # live block has MULTIPLE styled runs; the whole ¶ collapses to ONE replacement run.
    opener = StubOpener([
        _block_payload("p1", [_run("Hello "), _run("world", bold=True), _run(" from Q3.")]),
        _patch_ok(),
    ])
    apply(plan, _client(opener), "doc123")

    elements = opener.requests[1]["body"]["update_text_elements"]["elements"]
    assert len(elements) == 1  # collapsed to one run — no sub-span / partial-run edit
    assert elements[0]["text_run"]["content"] == "Farewell everyone."  # entire ¶ replaced


# --------------------------------------------------------------------------- #
# AC3 — live anchor re-validation before each write (drift → stale-anchor skip)  #
# --------------------------------------------------------------------------- #

def test_stale_anchor_when_live_text_drifted_skips_the_write():
    tree = _page(_para("p1", "The uptime was 99.9 percent."))
    plan = dry_run(
        [_req("uptime was 99.9 percent", replacement="uptime was 99.99 percent")], tree
    )
    # the live block DRIFTED — the anchor quote is no longer a substring.
    opener = StubOpener([
        _block_payload("p1", [_run("The uptime was 42 percent now.")]),
        # deliberately NO patch payload queued — a PATCH here would be a bug.
    ])
    log = apply(plan, _client(opener), "doc123")

    assert [r["method"] for r in opener.requests] == ["GET"]  # got the block, never patched
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason is RefusalReason.STALE_ANCHOR


def test_fresh_anchor_that_still_matches_live_text_is_applied():
    # The re-validation passes when the live text still contains the quote (even if the
    # rest of the ¶ drifted around it) — the write proceeds.
    tree = _page(_para("p1", "Q3 uptime was 99.9 percent overall."))
    plan = dry_run([_req("uptime was 99.9 percent", replacement="uptime was 100 percent")], tree)
    opener = StubOpener([
        _block_payload("p1", [_run("Q3 uptime was 99.9 percent overall, revised.")]),
        _patch_ok(),
    ])
    log = apply(plan, _client(opener), "doc123")
    assert log.entries[0].outcome == "applied"
    # `before` reflects the LIVE text at write time (what was actually replaced).
    assert log.entries[0].before == "Q3 uptime was 99.9 percent overall, revised."
    assert log.entries[0].after == "uptime was 100 percent"


# --------------------------------------------------------------------------- #
# AC4 — throttled: writes route through the shared transport, never a raw socket #
# --------------------------------------------------------------------------- #

def test_writes_route_through_the_shared_throttle_not_a_raw_socket():
    tree = _page(_para("p1", "alpha unique line"), _para("p2", "beta unique line"))
    plan = dry_run([_req("alpha unique line"), _req("beta unique line")], tree)
    clock = FakeClock()
    opener = StubOpener([
        _block_payload("p1", [_run("alpha unique line")]), _patch_ok(),
        _block_payload("p2", [_run("beta unique line")]), _patch_ok(),
    ])
    apply(plan, _client(opener, clock=clock), "doc123")

    # every call (2 GET + 2 PATCH) went through the injected opener — not a raw socket.
    assert [r["method"] for r in opener.requests] == ["GET", "PATCH", "GET", "PATCH"]
    # the 4th call in the same second was PACED by S2's RateLimiter (≤3/sec) — proof the
    # engine did not bypass common/transport.py.
    assert clock.sleeps == [1.0]


# --------------------------------------------------------------------------- #
# AC5 — apply-log written for a mixed applied / refused batch                    #
# --------------------------------------------------------------------------- #

def test_apply_log_reflects_a_mixed_applied_and_refused_batch():
    tree = _page(
        _para("ok", "apply me now"),
        _para("dupA", "twin line"), _para("dupB", "twin line"),  # ambiguous
        _para("stale", "will drift away"),
    )
    plan = dry_run([
        _req("apply me now", replacement="applied!"),
        _req("twin line"),                              # ambiguous → refused in the plan
        _req("will drift away", replacement="nope"),    # resolves, but live has drifted
    ], tree)
    opener = StubOpener([
        _block_payload("ok", [_run("apply me now")]), _patch_ok(),   # applied
        _block_payload("stale", [_run("totally different now")]),    # stale → no patch
    ])
    log = apply(plan, _client(opener), "doc123")

    # one apply-log entry per processed edit (applied AND refused), 1:1 with the plan.
    assert len(log.entries) == len(plan.entries) == 3
    kinds = [(e.outcome, e.block_id, (e.refusal.reason if e.refusal else None)) for e in log.entries]
    assert kinds[0] == ("applied", "ok", None)
    assert kinds[1] == ("refused", None, RefusalReason.AMBIGUOUS)
    assert kinds[2] == ("refused", None, RefusalReason.STALE_ANCHOR)
    # the applied entry carries block_id + before/after.
    applied = log.entries[0]
    assert (applied.before, applied.after) == ("apply me now", "applied!")
    # the ambiguous refusal still carries its candidate ids (from the plan).
    assert set(log.entries[1].refusal.candidate_ids) == {"dupA", "dupB"}
    # the whole log round-trips through JSON losslessly.
    assert ApplyLog.from_dict(json.loads(log.to_json())).entries == log.entries


# --------------------------------------------------------------------------- #
# AC6 — refusals never write; the rest of the batch still applies                #
# --------------------------------------------------------------------------- #

def test_only_resolved_and_fresh_edits_write():
    tree = _page(
        _para("ok", "write this line"),
        _para("dupA", "dup"), _para("dupB", "dup"),           # ambiguous
        ImageNode(caption="a chart", block_id="img"),          # write-hostile
        _para("stale", "fresh now"),                           # resolves, but stale live
    )
    plan = dry_run([
        _req("write this line", replacement="written"),
        _req("dup"),                        # ambiguous → refuse
        _req("a chart"),                    # write-hostile → refuse
        _req("nowhere at all"),             # not-found → refuse
        _req("fresh now", replacement="drifted"),
    ], tree)
    opener = StubOpener([
        _block_payload("ok", [_run("write this line")]), _patch_ok(),
        _block_payload("stale", [_run("changed entirely")]),   # stale → no patch
    ])
    log = apply(plan, _client(opener), "doc123")

    patches = [r for r in opener.requests if r["method"] == "PATCH"]
    assert len(patches) == 1  # exactly ONE write — only the resolved-and-fresh edit
    assert patches[0]["body"]["update_text_elements"]["elements"][0]["text_run"]["content"] == "written"
    outcomes = [e.outcome for e in log.entries]
    assert outcomes == ["applied", "refused", "refused", "refused", "refused"]
    reasons = [e.refusal.reason for e in log.entries[1:]]
    assert reasons == [
        RefusalReason.AMBIGUOUS,
        RefusalReason.WRITE_HOSTILE,
        RefusalReason.NOT_FOUND,
        RefusalReason.STALE_ANCHOR,
    ]


# --------------------------------------------------------------------------- #
# The container-key finder is block-type-agnostic (heading, list, … all work)    #
# --------------------------------------------------------------------------- #

def test_apply_reads_and_patches_a_heading_block_container():
    tree = _page(_heading("h1", "Quarterly Findings", level=1))
    plan = dry_run([_req("Quarterly Findings", replacement="Annual Findings")], tree)
    opener = StubOpener([
        _block_payload("h1", [_run("Quarterly Findings", bold=True)], block_type=3, key="heading1"),
        _patch_ok(),
    ])
    log = apply(plan, _client(opener), "doc123")

    assert log.entries[0].outcome == "applied"
    body = opener.requests[1]["body"]
    assert body["update_text_elements"]["elements"][0]["text_run"]["content"] == "Annual Findings"
