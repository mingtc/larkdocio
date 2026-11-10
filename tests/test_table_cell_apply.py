"""Offline unit tests for the table-cell apply + preview extension (LD-072).

W2-S3 drives a **whole-cell** edit through the **existing plan-gated pipeline** — no
parallel path. The **previewer** (``write/preview.py``) gains, per resolved table edit,
the **before/after cell text** + **row/column identification** (carried on the
:class:`~larkdocio.write.resolve.ResolvedCell` the resolver now attaches). The **apply
engine** (``write/apply.py``) patches the cell's inner text block via
:meth:`WriteClient._patch_block` with the **same** element-level ``to_write_elements``
whole-block ``update_text_elements`` path a paragraph uses (spike Test 5 — a cell patches
like a paragraph because its inner block *is* a text block; **no new endpoint**).

Because a table can shift under the anchor, apply performs a **DOUBLE** live re-validation
right before each write (spec Decision f, stricter than W1): it re-reads the **key cell**
(the row identity — ``row_key`` still verbatim-matches) **AND** the **target cell** (its
content is unchanged since capture); **either** mismatch → ``stale-anchor`` refusal, **no
write**. Writes stay throttled; every processed edit yields an apply-log record. All
offline (a fake clock + a stub opener, no network); the table WRITE round-trip is S4.
"""
import json

from log_reading_apply import reading_the_log
from larkdocio.write.apply import apply
apply = reading_the_log(apply)
from larkdocio.write.model import ApplyLog, RefusalReason
from larkdocio.write.preview import dry_run
from larkdocio.write.resolve import ResolvedCell, ResolvedTarget, resolve

# Shared fake-transport doubles + node/request/table builders (LD-088).
from write_harness import (
    FakeClock,
    StubOpener,
    _block_payload,
    _client,
    _page,
    _para,
    _patch_ok,
    _req,
    _run,
    _table,
    _treq,
)


# --------------------------------------------------------------------------- #
# Per-test DATA tables (readable per-test specs — builders.py doctrine). The     #
# structural builders (_cell / _table / _treq / _req) and the node builders      #
# (_para / _page) live in write_harness.                                         #
# --------------------------------------------------------------------------- #

# The spike-Test-5-shaped table: "97.2%" recurs; row + column pins exactly one cell.
def _spike_test5_table(bid="t5"):
    return _table(bid, [
        [("h0", "Metric"), ("h1", "Q2"), ("h2", "Q3")],
        [("r1k", "On-time delivery"), ("r1a", "95.0%"), ("r1b", "97.2%")],
        [("r2k", "Defect rate"), ("r2a", "96.0%"), ("r2b", "97.2%")],
        [("r3k", "Uptime"), ("r3a", "99.0%"), ("r3b", "97.2%")],
    ])


def _ambiguous_rows_table(bid="ta"):
    return _table(bid, [
        [("ah0", "Metric"), ("ah1", "Val")],
        [("ak1", "Churn"), ("av1", "5%")],
        [("ak2", "Churn"), ("av2", "6%")],
    ])


def _merged_table(bid="tm"):
    # Row 1's Q2 cell (grid (1,1)) is a colspan=2 merge ANCHOR covering the Q3 cell
    # (grid (1,2)). Real Lark marks the covered cell (1,1) — coverage is COMPUTED.
    return _table(bid, [
        [("mh0", "Metric"), ("mh1", "Q2"), ("mh2", "Q3")],
        [("mk", "Latency"), ("mmerged", "10ms"), ("mcovered", "10ms")],
    ], merges=[(1, 1), (1, 1), (1, 1), (1, 1), (1, 2), (1, 1)])


# --------------------------------------------------------------------------- #
# file-local PATCH filter. The fake transport + _run / _block_payload /          #
# _patch_ok / _client live in write_harness.                                     #
# --------------------------------------------------------------------------- #

def _patches(opener):
    return [r for r in opener.requests if r["method"] == "PATCH"]


# --------------------------------------------------------------------------- #
# The resolver now attaches cell context (row/col ids + inner text block ids)    #
# --------------------------------------------------------------------------- #

def test_resolver_attaches_cell_context_for_a_table_target():
    result = resolve(_treq("On-time delivery", column_index=2), _page(_spike_test5_table()))
    assert isinstance(result, ResolvedTarget)
    assert result.block_id == "r1b"                 # the resolved CELL id (unchanged, LD-071)
    assert isinstance(result.cell, ResolvedCell)
    assert result.cell.row == 1                      # grid row (0 = header)
    assert result.cell.column == 2                   # Q3 → column index 2
    assert result.cell.row_key == "On-time delivery"
    assert result.cell.column_label == "Q3"
    assert result.cell.target_text_block_id == "r1b__t"   # the INNER text block to patch
    assert result.cell.key_text_block_id == "r1k__t"      # the key cell's inner text block


def test_narrative_resolver_target_has_no_cell_context():
    result = resolve(_req("hello there"), _page(_para("p", "hello there")))
    assert isinstance(result, ResolvedTarget)
    assert result.cell is None                       # the narrative path is untouched


# --------------------------------------------------------------------------- #
# AC1 — preview gains cell before/after + row/col id                            #
# --------------------------------------------------------------------------- #

def test_table_plan_entry_carries_before_after_and_row_col_id():
    tree = _page(_spike_test5_table())
    plan = dry_run([_treq("On-time delivery", column_header="Q3", replacement="99.9%")], tree)
    (entry,) = plan.entries
    assert entry.is_resolved
    assert entry.block_id == "r1b"                   # target cell block_id
    assert entry.before == "97.2%"                   # the cell's current text (NOT "")
    assert entry.after == "99.9%"                    # the whole-cell replacement
    # row/column identification
    assert entry.cell is not None
    assert (entry.cell.row, entry.cell.column) == (1, 2)
    assert entry.cell.row_key == "On-time delivery"
    assert entry.cell.column_label == "Q3"


def test_refused_table_edit_carries_typed_refusal_and_no_cell():
    tree = _page(_spike_test5_table())
    plan = dry_run([_treq("On-time delivery", column_index=9)], tree)   # column out of range
    (entry,) = plan.entries
    assert not entry.is_resolved
    assert entry.refusal.reason is RefusalReason.COLUMN_NOT_FOUND
    assert entry.cell is None and entry.block_id is None and entry.before is None


def test_table_plan_entry_round_trips_through_json():
    tree = _page(_spike_test5_table())
    plan = dry_run([_treq("On-time delivery", column_index=2, replacement="99.9%")], tree)
    entry = plan.entries[0]
    from larkdocio.write.preview import PlanEntry
    restored = PlanEntry.from_dict(entry.to_dict())
    assert restored == entry                          # cell context survives the round-trip
    assert restored.cell.column_label == "Q3"


# --------------------------------------------------------------------------- #
# AC2 — cell patches like a paragraph; element-level, style-preserving; no new endpoint #
# --------------------------------------------------------------------------- #

def test_cell_patch_is_element_level_and_preserves_leading_run_style():
    tree = _page(_spike_test5_table())
    plan = dry_run([_treq("On-time delivery", column_index=2, replacement="99.9%")], tree)
    opener = StubOpener([
        _block_payload("r1k__t", [_run("On-time delivery")]),   # key cell re-validation
        _block_payload("r1b__t", [_run("97.2%", bold=True)]),   # target cell re-validation
        _patch_ok(),
    ])
    log = apply(plan, _client(opener), "doc123")

    patch_req = _patches(opener)[0]
    assert patch_req["method"] == "PATCH"
    assert "/blocks/r1b__t" in patch_req["url"]              # patched the INNER text block
    # element-level update_text_elements (not a lossy Markdown rebuild); bold preserved.
    assert patch_req["body"] == {"update_text_elements": {"elements": [
        {"text_run": {"content": "99.9%", "text_element_style": {"bold": True}}}
    ]}}
    assert log.entries[0].outcome == "applied"


def test_cell_edit_uses_only_get_and_patch_no_new_endpoint():
    tree = _page(_spike_test5_table())
    plan = dry_run([_treq("On-time delivery", column_index=2, replacement="99.9%")], tree)
    opener = StubOpener([
        _block_payload("r1k__t", [_run("On-time delivery")]),
        _block_payload("r1b__t", [_run("97.2%")]),
        _patch_ok(),
    ])
    apply(plan, _client(opener), "doc123")
    methods = [r["method"] for r in opener.requests]
    assert set(methods) <= {"GET", "PATCH"}          # only get_block / _patch_block — no new endpoint
    for r in opener.requests:
        assert "/open-apis/docx/v1/documents/doc123/blocks/" in r["url"]


# --------------------------------------------------------------------------- #
# AC3 — whole-cell granularity (the whole cell is the unit of change)           #
# --------------------------------------------------------------------------- #

def test_whole_cell_is_the_unit_of_change():
    tree = _page(_spike_test5_table())
    plan = dry_run([_treq("On-time delivery", column_index=2, replacement="brand new")], tree)
    # the live target cell has MULTIPLE styled runs summing to "97.2%" (== captured before).
    opener = StubOpener([
        _block_payload("r1k__t", [_run("On-time delivery")]),
        _block_payload("r1b__t", [_run("97"), _run(".2", bold=True), _run("%")]),
        _patch_ok(),
    ])
    apply(plan, _client(opener), "doc123")

    elements = _patches(opener)[0]["body"]["update_text_elements"]["elements"]
    assert len(elements) == 1                         # collapsed to one run — no sub-span edit
    assert elements[0]["text_run"]["content"] == "brand new"   # entire cell replaced


# --------------------------------------------------------------------------- #
# AC4 — DOUBLE live re-validation: key cell (row identity) AND target (content)  #
# --------------------------------------------------------------------------- #

def test_stale_when_key_cell_row_identity_drifts_skips_write():
    tree = _page(_spike_test5_table())
    plan = dry_run([_treq("On-time delivery", column_index=2, replacement="99.9%")], tree)
    # the KEY cell drifted — the row_key "On-time delivery" is no longer present.
    opener = StubOpener([
        _block_payload("r1k__t", [_run("Late delivery")]),
        # NO target GET, NO patch queued — any further call is a bug.
    ])
    log = apply(plan, _client(opener), "doc123")

    assert [r["method"] for r in opener.requests] == ["GET"]   # read only the key cell
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason is RefusalReason.STALE_ANCHOR


def test_stale_when_target_cell_content_drifts_skips_write():
    tree = _page(_spike_test5_table())
    plan = dry_run([_treq("On-time delivery", column_index=2, replacement="99.9%")], tree)
    # the KEY cell still matches, but the TARGET cell's content changed since capture.
    opener = StubOpener([
        _block_payload("r1k__t", [_run("On-time delivery")]),   # row identity holds
        _block_payload("r1b__t", [_run("42.0%")]),              # content != captured "97.2%"
        # NO patch queued.
    ])
    log = apply(plan, _client(opener), "doc123")

    assert [r["method"] for r in opener.requests] == ["GET", "GET"]   # read key + target, never patched
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason is RefusalReason.STALE_ANCHOR


def test_fresh_key_and_target_cell_is_applied():
    tree = _page(_spike_test5_table())
    plan = dry_run([_treq("On-time delivery", column_index=2, replacement="99.9%")], tree)
    opener = StubOpener([
        _block_payload("r1k__t", [_run("On-time delivery")]),
        _block_payload("r1b__t", [_run("97.2%")]),
        _patch_ok(),
    ])
    log = apply(plan, _client(opener), "doc123")

    assert [r["method"] for r in opener.requests] == ["GET", "GET", "PATCH"]
    entry = log.entries[0]
    assert entry.outcome == "applied"
    assert entry.block_id == "r1b"
    assert (entry.before, entry.after) == ("97.2%", "99.9%")


# --------------------------------------------------------------------------- #
# AC5 — throttled through the shared transport + apply-log for a mixed batch      #
# --------------------------------------------------------------------------- #

def test_cell_writes_route_through_the_shared_throttle_not_a_raw_socket():
    tree = _page(_spike_test5_table())
    plan = dry_run([
        _treq("On-time delivery", column_index=2, replacement="A"),
        _treq("Defect rate", column_index=2, replacement="B"),
    ], tree)
    clock = FakeClock()
    opener = StubOpener([
        _block_payload("r1k__t", [_run("On-time delivery")]), _block_payload("r1b__t", [_run("97.2%")]), _patch_ok(),
        _block_payload("r2k__t", [_run("Defect rate")]), _block_payload("r2b__t", [_run("97.2%")]), _patch_ok(),
    ])
    apply(plan, _client(opener, clock=clock), "doc123")

    # 2 cell edits = 6 calls (GET,GET,PATCH ×2), all through the injected opener.
    assert [r["method"] for r in opener.requests] == ["GET", "GET", "PATCH", "GET", "GET", "PATCH"]
    # the 4th call in the same second was PACED by the ≤3/sec limiter — proof the engine
    # did not bypass common/transport.py.
    assert clock.sleeps == [1.0]


def test_apply_log_reflects_a_mixed_table_batch():
    tree = _page(_spike_test5_table())
    plan = dry_run([
        _treq("On-time delivery", column_index=2, replacement="99.9%"),   # applies
        _treq("On-time delivery", column_index=9),                        # column-not-found (refused @plan)
        _treq("Defect rate", column_index=2, replacement="X"),            # resolves, but target drifts → stale
    ], tree)
    opener = StubOpener([
        _block_payload("r1k__t", [_run("On-time delivery")]), _block_payload("r1b__t", [_run("97.2%")]), _patch_ok(),
        _block_payload("r2k__t", [_run("Defect rate")]), _block_payload("r2b__t", [_run("changed!")]),
    ])
    log = apply(plan, _client(opener), "doc123")

    assert len(log.entries) == len(plan.entries) == 3
    kinds = [(e.outcome, e.block_id, (e.refusal.reason if e.refusal else None)) for e in log.entries]
    assert kinds[0] == ("applied", "r1b", None)
    assert kinds[1] == ("refused", None, RefusalReason.COLUMN_NOT_FOUND)
    assert kinds[2] == ("refused", None, RefusalReason.STALE_ANCHOR)
    applied = log.entries[0]
    assert (applied.before, applied.after) == ("97.2%", "99.9%")
    # the whole log (incl. TableLocator anchors) round-trips through JSON losslessly.
    assert ApplyLog.from_dict(json.loads(log.to_json())).entries == log.entries


# --------------------------------------------------------------------------- #
# AC6 — refusals never write; the rest of the batch still applies                #
# --------------------------------------------------------------------------- #

def test_only_resolved_and_fresh_cells_write():
    tree = _page(_spike_test5_table(), _ambiguous_rows_table(), _merged_table())
    plan = dry_run([
        _treq("On-time delivery", column_index=2, replacement="99.9%"),   # applies (fresh)
        _treq("Churn", column_index=1),                                   # ambiguous-row → refuse @plan
        _treq("Latency", column_index=2),                                 # covered/merged → refuse @plan
        _treq("Nonexistent metric", column_index=1),                      # not-found → refuse @plan
        _treq("Defect rate", column_index=2, replacement="X"),            # resolves, target drifts → stale
    ], tree)
    opener = StubOpener([
        _block_payload("r1k__t", [_run("On-time delivery")]), _block_payload("r1b__t", [_run("97.2%")]), _patch_ok(),
        _block_payload("r2k__t", [_run("Defect rate")]), _block_payload("r2b__t", [_run("drifted!")]),
    ])
    log = apply(plan, _client(opener), "doc123")

    patches = _patches(opener)
    assert len(patches) == 1                          # exactly ONE write — only the fresh cell
    assert "/blocks/r1b__t" in patches[0]["url"]
    assert [e.outcome for e in log.entries] == ["applied", "refused", "refused", "refused", "refused"]
    reasons = [e.refusal.reason for e in log.entries[1:]]
    assert reasons == [
        RefusalReason.AMBIGUOUS,
        RefusalReason.WRITE_HOSTILE,
        RefusalReason.NOT_FOUND,
        RefusalReason.STALE_ANCHOR,
    ]


# --------------------------------------------------------------------------- #
# Narrative + table edits coexist in one plan-gated batch (dispatch intact)      #
# --------------------------------------------------------------------------- #

def test_narrative_and_table_edits_apply_in_one_batch():
    tree = _page(_para("p", "plain paragraph text"), _spike_test5_table())
    plan = dry_run([
        _req("plain paragraph text", replacement="new para"),             # narrative: 1 GET + PATCH
        _treq("On-time delivery", column_index=2, replacement="99.9%"),   # table: 2 GET + PATCH
    ], tree)
    opener = StubOpener([
        _block_payload("p", [_run("plain paragraph text")]), _patch_ok(),
        _block_payload("r1k__t", [_run("On-time delivery")]), _block_payload("r1b__t", [_run("97.2%")]), _patch_ok(),
    ])
    log = apply(plan, _client(opener), "doc123")

    assert [e.outcome for e in log.entries] == ["applied", "applied"]
    assert [r["method"] for r in opener.requests] == ["GET", "PATCH", "GET", "GET", "PATCH"]
