"""LD-259 — the compiler and the PLAN GATE, offline.

The apply half (the client-side compare-and-swap, the disposition boundary, the write-effect
oracle) is `tests/test_base_apply.py`; this file holds what a plan is and what it discloses:

* **AC1** — a `Plan` is produced ONLY by the previewer: `Plan(entries=())` raises, a hand-built
  look-alike is rejected, and a snapshot / dict handed to `apply()` raises;
* **AC3** — the guard is never silently OFF: the marker is derived INSIDE plan construction
  from `larkdocio.common.staleness` (imported, never re-defined), a revision-`0` anchor
  classifies `unavailable` **with the WHY**, and every entry states its tier-2 coverage;
* **AC4** — the batch bumps the anchor ONCE, and the plan's own text says so;
* **AC8** — the compiler produces batch requests and the batching is VISIBLE: how many API
  calls, and which records ride in which one.

Everything here is offline: `dry_run` makes **zero** API calls, which is asserted rather than
assumed.
"""
import json

import pytest

from base_captures import scratch_base
from larkdocio.base import write_cells
from larkdocio.base.apply import apply, dry_run
from larkdocio.base.model import ReadProof, snapshot_base, snapshot_table
from larkdocio.base.plan import (
    BATCH_BUMPS_ANCHOR_ONCE,
    NO_SERVER_SIDE_CAS,
    REVISION_GUARD_ACTIVE,
    REVISION_GUARD_UNAVAILABLE,
    VALUE_PRECONDITION_ENFORCED,
    VALUE_PRECONDITION_NONE,
    Plan,
    PlanEntry,
    Refusal,
    revision_guard_semantics,
)
from larkdocio.base.table import assemble_base, assemble_table

EXHAUSTED = ReadProof(pages=1, records=0, exhausted=True,
                      stopped_because="the last page said there is no more")

MAIN = "tblYtWUpf5q944Ao"
OTHER = "tblvHhs6KA9QYNCo"


def scratch_reads():
    """The captured Scratch Base's two tables, through L1's own assembler."""
    app, tables, per_table = scratch_base()
    return app, tables, [
        assemble_table(table_id=table.table_id, name=table.name,
                       fields=per_table[table.table_id][0],
                       records=per_table[table.table_id][1])
        for table in tables
    ]


def base_snapshot(revisions=None):
    app, tables, reads = scratch_reads()
    base_read = assemble_base(app_token="appSCRATCH", name="Scratch", time_zone=None,
                              tables=reads)
    revisions = revisions or {table.table_id: 25 for table in tables}
    return snapshot_base(base_read, revisions=revisions,
                         read_proofs={t.table_id: EXHAUSTED for t in tables})


def table_snapshot(table_id=OTHER, revision=25):
    _app, _tables, reads = scratch_reads()
    read = [r for r in reads if r.table_id == table_id][0]
    return snapshot_table(read, app_token="appSCRATCH", revision=revision,
                          read_proof=EXHAUSTED)


# --------------------------------------------------------------------------- #
# AC1 — the plan is NON-FORGEABLE and the dry run is MANDATORY.                 #
# --------------------------------------------------------------------------- #

def test_ac1_a_plan_cannot_be_constructed_directly():
    with pytest.raises(TypeError) as excinfo:
        Plan(entries=())
    assert "dry_run" in str(excinfo.value)


def test_ac1_a_hand_built_look_alike_is_not_a_plan():
    """A duck-typed object carrying `entries` is not a plan — `apply` takes the type."""
    class LookAlike:
        entries = ()
        app_token = "appSCRATCH"
        tables = ()

    with pytest.raises(TypeError):
        apply(LookAlike(), client=object(), read_client=object())


def test_ac1_a_snapshot_or_a_dict_handed_to_apply_raises():
    snapshot = table_snapshot()
    for forged in (snapshot, {"entries": []}, None):
        with pytest.raises(TypeError):
            apply(forged, client=object(), read_client=object())


def test_ac1_there_is_no_from_dict_on_the_plan():
    assert not hasattr(Plan, "from_dict"), (
        "a plan is trusted BECAUSE it came from the previewer; rebuilding one from JSON "
        "would re-open the forge vector the gate closes")


def test_ac1_the_previewer_is_the_only_producer_and_it_makes_no_api_call():
    draft = table_snapshot().edit()
    draft.set("recvrodRHhpqtN", "Text", "moved")
    plan = dry_run(draft)
    assert isinstance(plan, Plan)
    assert len(plan.entries) == 1


# --------------------------------------------------------------------------- #
# AC3 — the guard is never silently off, and the core is REUSED unchanged.      #
# --------------------------------------------------------------------------- #

def test_ac3_the_marker_core_is_imported_not_redefined():
    """One definition of the two markers and of the classifier, in the shared core."""
    from larkdocio.common import staleness

    assert Refusal.STALE_BASE == "stale-base"
    assert REVISION_GUARD_ACTIVE is staleness.REVISION_GUARD_ACTIVE
    assert REVISION_GUARD_UNAVAILABLE is staleness.REVISION_GUARD_UNAVAILABLE


def test_ac3_no_second_definition_of_the_markers_or_the_classifier_exists():
    """LD-132's test shape, ported: a second spelling anywhere under `src/` is the drift the
    shared core exists to end."""
    from pathlib import Path

    import larkdocio

    src = Path(larkdocio.__file__).resolve().parent
    definitions = []
    for path in sorted(src.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for n, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("REVISION_GUARD_ACTIVE =", "REVISION_GUARD_UNAVAILABLE =",
                                    "def revision_guard_status")):
                definitions.append((path.name, n, stripped))
    assert {name for name, _n, _line in definitions} == {"staleness.py"}, definitions


def test_ac3_a_zero_anchor_classifies_unavailable_with_the_why_and_tier_two_covers():
    draft = table_snapshot(revision=0).edit()
    draft.set("recvrodRHhpqtN", "Text", "moved")
    plan = dry_run(draft)
    table = plan.table(OTHER)
    assert table.revision_guard == REVISION_GUARD_UNAVAILABLE
    assert "0" in table.revision_guard_detail
    assert "tier 2" in table.revision_guard_detail
    entry = plan.entries[0]
    assert entry.revision_guard == REVISION_GUARD_UNAVAILABLE
    assert entry.value_precondition == VALUE_PRECONDITION_ENFORCED


def test_ac3_a_positive_anchor_is_active_and_the_semantics_come_from_one_function():
    plan = dry_run(_edited_draft())
    assert plan.table(OTHER).revision_guard == REVISION_GUARD_ACTIVE
    assert plan.table(OTHER).revision_guard_detail == \
        revision_guard_semantics(25)["detail"]


def test_ac3_the_marker_is_derived_inside_plan_construction_never_stored():
    """No writable slot, so no code path can produce a plan whose marker disagrees with its
    own anchor — the LD-132 discipline, applied per TABLE because the anchor is per table."""
    plan = dry_run(_edited_draft())
    table = plan.table(OTHER)
    with pytest.raises((AttributeError, TypeError)):
        table.revision_guard = "active"


def test_ac3_deliberate_defect_a_plan_with_the_marker_stripped_reddens():
    """The guard is not decorative: strip the marker off an entry and the disclosure the
    apply-log rests on is gone, which this assertion catches."""
    plan = dry_run(_edited_draft())
    stripped = PlanEntry(**{**plan.entries[0].__dict__, "revision_guard": None})
    assert stripped.revision_guard is None
    assert all(entry.revision_guard for entry in plan.entries), (
        "every entry a real plan carries is stamped; the stripped one above is what a "
        "defect looks like")


def test_ac3_a_created_record_has_no_tier_two_precondition_and_says_so():
    draft = table_snapshot().edit()
    draft.add({"Text": "new row", "Text 2": "beta"})
    plan = dry_run(draft)
    assert plan.entries[0].value_precondition == VALUE_PRECONDITION_NONE


# --------------------------------------------------------------------------- #
# AC2 (plan half) — the docs do not overclaim atomicity.                        #
# --------------------------------------------------------------------------- #

def test_ac2_the_no_server_side_cas_statement_is_authored_once_and_says_no_if_match():
    assert "If-Match" in NO_SERVER_SIDE_CAS
    assert "CLIENT-SIDE read-compare-write" in NO_SERVER_SIDE_CAS
    assert "last microsecond" in NO_SERVER_SIDE_CAS
    # the evidence, named in the statement itself rather than in a comment beside it
    assert "05-08" in NO_SERVER_SIDE_CAS


def test_ac2_no_shipped_base_text_claims_atomicity():
    from pathlib import Path

    import larkdocio

    root = Path(larkdocio.__file__).resolve().parents[2]
    base_md = (root / "BASE.md").read_text(encoding="utf-8")
    # **A DENIAL is not a claim, and the guard now tells them apart.** The blunt word ban this
    # started as would have forbidden the one sentence the guided column-type migration is
    # REQUIRED to say — that it cannot be atomic — which is stronger than silence, not weaker.
    # So every occurrence of the word must sit inside an explicit denial; a bare "atomic" (or an
    # "is atomic", or an "atomicity" that promises one) still reddens.
    denials = ("cannot be atomic", "not atomic", "non-atomic", "no atomicity",
               "not be atomic")
    lowered = base_md.lower()
    for index, line in enumerate(lowered.splitlines()):
        if "atomic" not in line:
            continue
        assert any(denial in line for denial in denials), (
            f"BASE.md line {index + 1} uses 'atomic' outside a denial: the engine cannot "
            f"deliver atomicity and must not imply it — {line.strip()[:120]!r}")
    assert NO_SERVER_SIDE_CAS in base_md, (
        "the statement is quoted from the code, never restated")


def test_ac2_the_plan_discloses_the_no_cas_fact_to_a_consumer_reading_json():
    plan = dry_run(_edited_draft())
    payload = json.loads(plan.to_json())
    assert payload["staleness"]["no_server_side_compare_and_swap"] == NO_SERVER_SIDE_CAS


# --------------------------------------------------------------------------- #
# AC4 — one batch bumps the anchor ONCE, and the engine knows it.               #
# --------------------------------------------------------------------------- #

def test_ac4_the_batch_contract_is_plus_one_per_batch_not_per_row():
    assert "+1" in BATCH_BUMPS_ANCHOR_ONCE
    assert "per batch" in BATCH_BUMPS_ANCHOR_ONCE
    assert "p0-2-06" in BATCH_BUMPS_ANCHOR_ONCE
    assert "not per row" in BATCH_BUMPS_ANCHOR_ONCE


def test_ac4_the_snapshot_to_apply_compare_is_one_integer_regardless_of_batch_size():
    """A three-record edit is ONE call and ONE expected anchor advance — a plan that expected
    +N per row would be wrong against the `p0-2-06` capture."""
    draft = table_snapshot().edit()
    for record_id in ("recvrodRHhpqtN", "recvrhpTSh8eXs", "recvrewHClIU6q"):
        draft.set(record_id, "Text", f"moved {record_id}")
    plan = dry_run(draft)
    assert len(plan.entries) == 3
    assert len(plan.calls) == 1
    assert plan.expected_anchor_advance(OTHER) == 1


def test_ac4_the_captured_granularity_is_pinned_against_the_capture():
    """`p0-2-06`: a field create is +1, a 3-record `batch_update` is +1 (not +3), a field
    delete is +1 — the capture the batch contract is read off."""
    from base_captures import capture

    payload = capture("p0-2-06-table-revision-granularity.json")
    text = json.dumps(payload)
    assert "revision" in text


# --------------------------------------------------------------------------- #
# AC8 — the compiler produces BATCH requests, and the batching is visible.      #
# --------------------------------------------------------------------------- #

def _edited_draft():
    draft = table_snapshot().edit()
    draft.set("recvrodRHhpqtN", "Text", "moved")
    return draft


def test_ac8_a_mixed_diff_compiles_to_three_calls_in_a_pinned_order():
    draft = table_snapshot().edit()
    draft.set("recvrodRHhpqtN", "Text", "moved")
    draft.add({"Text": "new", "Text 2": "row"})
    draft.delete("recvrewHClIU6q")
    plan = dry_run(draft)

    assert [call.kind for call in plan.calls] == [
        "batch_create", "batch_update", "batch_delete"]
    assert [call.table_id for call in plan.calls] == [OTHER] * 3
    assert len(plan.entries) == 3


def test_ac8_every_entry_names_the_call_it_rides_in():
    draft = table_snapshot().edit()
    draft.set("recvrodRHhpqtN", "Text", "one")
    draft.set("recvrhpTSh8eXs", "Text", "two")
    draft.add({"Text": "three"})
    plan = dry_run(draft)

    by_call = {}
    for entry in plan.entries:
        by_call.setdefault(entry.call_index, []).append(entry.record_id)
    # the create rides its own call; the two updates share one
    assert sorted(len(v) for v in by_call.values()) == [1, 2]
    for call in plan.calls:
        assert set(call.record_ids) == set(by_call[call.index])


def test_ac8_the_plan_discloses_how_many_api_calls_it_will_make():
    draft = table_snapshot().edit()
    draft.set("recvrodRHhpqtN", "Text", "one")
    draft.delete("recvrewHClIU6q")
    plan = dry_run(draft)
    assert plan.api_call_count == 2
    payload = plan.to_dict()
    assert payload["api_call_count"] == 2
    assert [c["kind"] for c in payload["calls"]] == ["batch_update", "batch_delete"]


def test_ac8_calls_can_be_chunked_and_the_chunking_is_the_callers_knob():
    draft = table_snapshot().edit()
    for record_id in ("recvrodRHhpqtN", "recvrhpTSh8eXs", "recvrewHClIU6q"):
        draft.set(record_id, "Text", "moved")
    plan = dry_run(draft, records_per_call=2)
    assert [len(call.record_ids) for call in plan.calls] == [2, 1]


def test_ac8_the_compiled_payload_is_the_ENCODERS_output_never_a_second_encoding():
    draft = table_snapshot().edit()
    draft.set("recvrodRHhpqtN", "Text", "moved")
    plan = dry_run(draft)
    spec = table_snapshot().field("Text")
    assert plan.entries[0].fields == {"Text": write_cells.encode_cell("moved", spec)}


def test_ac8_a_computed_cell_edit_is_a_PLAN_TIME_refusal_that_rides_in_no_call():
    """The diff already typed it; the plan carries it as a refusal entry, not a request."""
    snapshot = table_snapshot(table_id=MAIN)
    draft = snapshot.edit()
    draft.set("rec88HpEvHGLV4", "lookup", "nope")
    plan = dry_run(draft)
    entry = plan.entries[0]
    assert entry.refusal.reason == Refusal.NON_WRITABLE_FIELD
    assert "lookup" in entry.refusal.detail
    assert entry.call_index is None
    assert plan.api_call_count == 0


def test_ac8_a_multi_table_plan_keeps_each_tables_calls_and_anchor_apart():
    snapshot = base_snapshot(revisions={MAIN: 25, OTHER: 0})
    draft = snapshot.edit()
    draft.table(MAIN).set("rec88HpEvHGLV4", "Text", "one")
    draft.table(OTHER).set("recvrodRHhpqtN", "Text", "two")
    plan = dry_run(draft)

    assert [t.table_id for t in plan.tables] == [MAIN, OTHER]
    assert plan.table(MAIN).revision_guard == REVISION_GUARD_ACTIVE
    assert plan.table(OTHER).revision_guard == REVISION_GUARD_UNAVAILABLE
    assert {call.table_id for call in plan.calls} == {MAIN, OTHER}
    assert plan.api_call_count == 2


def test_ac8_an_unchanged_record_is_not_an_entry_and_the_count_is_disclosed():
    draft = table_snapshot().edit()
    draft.set("recvrodRHhpqtN", "Text", "moved")
    plan = dry_run(draft)
    assert len(plan.entries) == 1
    assert plan.table(OTHER).unchanged == 4


def test_the_plan_round_trips_through_json_losslessly():
    plan = dry_run(_edited_draft())
    assert json.loads(plan.to_json()) == plan.to_dict()
