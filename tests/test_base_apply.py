"""LD-259 — the APPLY half: the client-side compare-and-swap, the disposition boundary, and
the write-effect oracle.

The plan half is `tests/test_base_plan_gate.py`. Here:

* **AC2** — `STALE_BASE` is a CLIENT-SIDE read-compare-write: the anchor is re-read immediately
  before the batch, drift refuses with ZERO writes, and **no precondition key is ever sent**
  (the reason, captured: a `PUT` carrying bogus `revision` / `last_modified_time` body keys
  answered `code:0` AND applied the write — `05-08`);
* **AC5** — the write-effect oracle: a `code:0` that did not move `table.revision` is `dropped`,
  never `applied`, and the engine does NOT retry;
* **AC6** — the ruled disposition table (D4′), one test per row, each asserting the scope, the
  typed reason, the outcome and whether the change LANDED — plus the structural guard that the
  classification sits INSIDE an `except` in the apply loop;
* **AC7** — the apply-log is 1:1 with the plan, matched per entry rather than by length, with
  everything after a halt logged `not-attempted` naming where and why; and the house invariant
  is DECLARED against LD-254's one authoring, never re-defined here.
"""
import ast
import copy
import inspect
import json
import pathlib
import types

import pytest

from base_captures import scratch_base
from log_reading_apply import reading_the_log
from larkdocio import capabilities
from larkdocio.base import apply as apply_module
from larkdocio.base.apply import DECLARED_SAFETY_CONTRACT, apply, dry_run
apply = reading_the_log(apply)
from larkdocio.base.disposition import (
    ENTRY_SCOPED,
    READ_SEAMS,
    SYSTEMIC,
    WRITE_SEAMS,
    WriteWatch,
    classify_apply_exception,
)
from larkdocio.base.model import ReadProof, snapshot_base, snapshot_table
from larkdocio.base.plan import Refusal
from larkdocio.base.table import assemble_base, assemble_table
from larkdocio.base.write_ops import WRITE_OPS
from larkdocio.capabilities._contracts import APPLY_LOG_COMPLETE
from larkdocio.errors import (
    LarkAPIError,
    LarkConfigError,
    LarkPermissionError,
    LarkRateLimitError,
    api_error,
)

EXHAUSTED = ReadProof(pages=1, records=0, exhausted=True,
                      stopped_because="the last page said there is no more")

MAIN = "tblYtWUpf5q944Ao"
OTHER = "tblvHhs6KA9QYNCo"
APP = "appSCRATCH"
R1, R2, R3 = "recvrodRHhpqtN", "recvrhpTSh8eXs", "recvrewHClIU6q"


# --------------------------------------------------------------------------- #
# A fake Base — the captured payloads, mutable, with a revision counter.        #
# --------------------------------------------------------------------------- #

class FakeBase:
    """The captured Scratch Base behind a read seam and a write seam.

    Real captured payloads (so a shape drift reddens at deserialization), a per-table
    ``revision`` counter that behaves the way `p0-2-06` measured — **+1 per batch call, not per
    row** — and the two knobs the safety properties need: a call that raises, and a call that
    answers `code:0` **without moving the anchor** (the Stage discard, `p1-q2-02`).
    """

    def __init__(self, revisions=None, *, raises=None, silent=()):
        _app, tables, per_table = scratch_base()
        self.fields = {t.table_id: per_table[t.table_id][0] for t in tables}
        self.records = {t.table_id: list(copy.deepcopy(per_table[t.table_id][1]))
                        for t in tables}
        self.names = {t.table_id: t.name for t in tables}
        self.revisions = dict(revisions or {t.table_id: 25 for t in tables})
        self.raises = raises or {}          # call kind -> exception
        self.silent = set(silent)           # call kinds that do not move the anchor
        self.calls = []                     # every write call, as (kind, table_id, payload)
        self.reads = []                     # every read call, as its seam name
        self.missing_tables = set()

    # ---- the read seam ---------------------------------------------------- #

    def list_tables(self, app_token):
        self.reads.append("list_tables")
        return [types.SimpleNamespace(table_id=tid, name=self.names[tid],
                                      revision=self.revisions[tid])
                for tid in self.records if tid not in self.missing_tables]

    def list_fields(self, app_token, table_id):
        self.reads.append("list_fields")
        return self.fields[table_id]

    def search_records(self, app_token, table_id):
        self.reads.append("search_records")
        return self.records[table_id]

    # ---- the write seam --------------------------------------------------- #

    def _did(self, kind, table_id):
        if kind in self.raises:
            raise self.raises.pop(kind)
        if kind not in self.silent:
            self.revisions[table_id] += 1

    def batch_create_records(self, app_token, table_id, rows):
        self.calls.append(("batch_create", table_id, list(rows)))
        self._did("batch_create", table_id)
        return [types.SimpleNamespace(record_id=f"recNEW{n}", fields=dict(row))
                for n, row in enumerate(rows, 1)]

    def batch_update_records(self, app_token, table_id, updates):
        updates = list(updates)
        self.calls.append(("batch_update", table_id, updates))
        self._did("batch_update", table_id)
        for record_id, fields in updates:
            for record in self.records[table_id]:
                if record.record_id == record_id:
                    record.fields.update(fields)
        return [types.SimpleNamespace(record_id=rid, fields=f) for rid, f in updates]

    def batch_delete_records(self, app_token, table_id, record_ids):
        record_ids = list(record_ids)
        self.calls.append(("batch_delete", table_id, record_ids))
        self._did("batch_delete", table_id)
        self.records[table_id] = [r for r in self.records[table_id]
                                  if r.record_id not in record_ids]
        return [types.SimpleNamespace(record_id=rid, deleted=True) for rid in record_ids]

    # ---- helpers the tests drive it with ---------------------------------- #

    def move_out_of_band(self, table_id, cell=None):
        """Someone else wrote to this table between the plan and the apply."""
        self.revisions[table_id] += 1
        if cell:
            record_id, field, value = cell
            for record in self.records[table_id]:
                if record.record_id == record_id:
                    record.fields[field] = value

    def snapshot(self, table_id=OTHER, revision=None):
        read = assemble_table(table_id=table_id, name=self.names[table_id],
                              fields=self.fields[table_id],
                              records=copy.deepcopy(self.records[table_id]))
        return snapshot_table(read, app_token=APP,
                              revision=(self.revisions[table_id] if revision is None
                                        else revision),
                              read_proof=EXHAUSTED)

    def base_snapshot(self):
        reads = [assemble_table(table_id=tid, name=self.names[tid], fields=self.fields[tid],
                                records=copy.deepcopy(self.records[tid]))
                 for tid in self.records]
        base_read = assemble_base(app_token=APP, name="Scratch", time_zone=None, tables=reads)
        return snapshot_base(base_read, revisions=dict(self.revisions),
                             read_proofs={tid: EXHAUSTED for tid in self.records})


def one_edit_plan(base, *, revision=None, records_per_call=None):
    draft = base.snapshot(revision=revision).edit()
    draft.set(R1, "Text", "moved by the plan")
    return dry_run(draft, records_per_call=records_per_call)


def run(plan, base):
    return apply(plan, client=base, read_client=base)


# --------------------------------------------------------------------------- #
# AC2 — the client-side compare-and-swap, and NO precondition key.              #
# --------------------------------------------------------------------------- #

def _keys(payload):
    """Every key anywhere inside a call's payload."""
    found = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            found.add(key)
            found |= _keys(value)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            found |= _keys(item)
    return found


def test_ac2_no_precondition_key_is_ever_sent():
    """The captured reason: a `PUT` carrying bogus `revision` / `last_modified_time` body keys
    answered `code:0` AND applied the write, so a precondition key would be a lie that reads
    like safety. The engine sends neither — it reads, compares, then writes."""
    base = FakeBase()
    log = run(one_edit_plan(base), base)
    assert log.applied
    sent = set()
    for _kind, _table, payload in base.calls:
        sent |= _keys(payload)
    assert "revision" not in sent
    assert "last_modified_time" not in sent


def test_ac2_the_anchor_is_read_before_the_write_and_again_after_it():
    base = FakeBase()
    run(one_edit_plan(base), base)
    assert base.reads[0] == "list_tables", "the compare comes before the write"
    assert base.reads[-1] == "list_tables", "and the oracle reads it again after"


def test_ac2_a_table_that_moved_out_of_band_refuses_stale_base_with_zero_writes():
    base = FakeBase()
    plan = one_edit_plan(base)
    base.move_out_of_band(OTHER)
    log = run(plan, base)

    assert base.calls == [], "STALE_BASE must issue ZERO writes"
    assert [e.outcome for e in log.entries] == ["stale"]
    assert log.entries[0].refusal.reason == Refusal.STALE_BASE
    assert len(log.entries) == len(plan.entries)
    assert log.table_halts[OTHER]["reason"] == Refusal.STALE_BASE


def test_ac2_the_stale_refusal_does_not_overclaim_atomicity():
    base = FakeBase()
    plan = one_edit_plan(base)
    base.move_out_of_band(OTHER)
    detail = run(plan, base).entries[0].refusal.detail
    assert "CLIENT-SIDE" in detail
    assert "If-Match" in detail
    assert "last microsecond" in detail
    assert "atomic" not in detail.lower()


def test_ac2_amplifier_a_zero_anchor_still_refuses_on_drift_via_tier_two():
    """Tier 1 is `unavailable` on a revision-0 table — comparing 0 == 0 observes nothing — and
    tier 2 is what refuses. The guard is never silently off."""
    base = FakeBase(revisions={MAIN: 0, OTHER: 0})
    plan = one_edit_plan(base)
    assert plan.table(OTHER).revision_guard == "unavailable"
    base.records[OTHER][0].fields["Text"] = "somebody else got here first"
    log = run(plan, base)

    assert base.calls == []
    assert log.entries[0].outcome == "refused"
    assert log.entries[0].refusal.reason == Refusal.PRECONDITION_MISMATCH
    assert "tier 2" in log.entries[0].refusal.detail
    assert log.entries[0].revision_guard == "unavailable", (
        "the log records WHICH guard the write ran under")


def test_ac2_a_deleted_records_precondition_is_its_existence():
    base = FakeBase()
    draft = base.snapshot().edit()
    draft.delete(R3)
    plan = dry_run(draft)
    base.records[OTHER] = [r for r in base.records[OTHER] if r.record_id != R3]
    log = run(plan, base)
    assert log.entries[0].outcome == "refused"
    assert log.entries[0].refusal.reason == Refusal.PRECONDITION_MISMATCH


def test_ac2_apply_refuses_to_run_without_a_read_seam():
    """A client-side compare-and-swap that cannot read cannot compare — so there is no
    argument that turns the guard off."""
    base = FakeBase()
    with pytest.raises(TypeError) as excinfo:
        apply(one_edit_plan(base), client=base, read_client=None)
    assert "read" in str(excinfo.value).lower()


# --------------------------------------------------------------------------- #
# AC5 — the write-effect oracle.                                               #
# --------------------------------------------------------------------------- #

def test_ac5_a_code_zero_that_did_not_move_the_anchor_is_dropped_never_applied():
    """`p1-q2-02` generalized: the Stage write answered `code:0` with `25 → 25` while the
    positive control moved `1 → 2`. A write the anchor did not register did not happen."""
    base = FakeBase(silent=("batch_update",))
    log = run(one_edit_plan(base), base)

    assert [e.outcome for e in log.entries] == ["dropped"]
    assert log.entries[0].refusal.reason == Refusal.WRITE_NOT_OBSERVED
    assert log.applied == (), "a dropped write is NEVER counted as applied"
    assert log.dropped == log.entries


def test_ac5_the_engine_reports_a_dropped_write_and_does_NOT_retry_it():
    """The scope fence, deliberate: detection, not retry."""
    base = FakeBase(silent=("batch_update",))
    run(one_edit_plan(base), base)
    assert len(base.calls) == 1, "a dropped write is reported, never re-sent"


def test_ac5_a_write_that_moved_the_anchor_is_applied_and_carries_the_post_revision():
    base = FakeBase()
    log = run(one_edit_plan(base), base)
    assert [e.outcome for e in log.entries] == ["applied"]
    assert log.entries[0].revision == 26
    assert base.revisions[OTHER] == 26


def test_ac5_the_oracle_survives_a_batch_and_expects_plus_one_not_plus_n():
    base = FakeBase()
    draft = base.snapshot().edit()
    for record_id in (R1, R2, R3):
        draft.set(record_id, "Text", f"moved {record_id}")
    plan = dry_run(draft)
    log = run(plan, base)

    assert len(base.calls) == 1, "three records ride in ONE batch call"
    assert base.revisions[OTHER] == 26, "+1 per batch, not per row"
    assert {e.outcome for e in log.entries} == {"applied"}


def test_ac5_a_created_record_reports_the_id_the_server_assigned():
    base = FakeBase()
    draft = base.snapshot().edit()
    local = draft.add({"Text": "brand new"})
    plan = dry_run(draft)
    log = run(plan, base)
    assert log.entries[0].record_id == local
    assert log.entries[0].created_record_id == "recNEW1"


# --------------------------------------------------------------------------- #
# AC6 — the RULED disposition table (D4′), row by row.                          #
# --------------------------------------------------------------------------- #

def coded(code, msg="nope"):
    return api_error(f"a call failed: Code: {code}, Msg: {msg}", code=code, msg=msg)


@pytest.mark.parametrize("code", [1254043, 1254069, 1254060, 1255002, 99992402])
def test_ac6_entry_scoped_codes_refuse_their_call_and_the_batch_CONTINUES(code):
    """`1254043 RecordIdNotFound` and the value-conversion codes are Lark's answer about the
    records / the values in THAT call; the next call's are its own question."""
    base = FakeBase(raises={"batch_update": coded(code)})
    draft = base.snapshot().edit()
    draft.set(R1, "Text", "one")           # the update call — it will be refused
    draft.add({"Text": "two"})             # the create call — it must still run
    plan = dry_run(draft)
    log = run(plan, base)

    by_op = {e.op: e for e in log.entries}
    assert by_op["update"].outcome == "refused"
    assert by_op["update"].refusal.reason == Refusal.API_ERROR
    assert "CONTINUED" in by_op["update"].refusal.detail
    assert by_op["create"].outcome == "applied", "the batch continued"
    assert log.halt is None
    assert len(log.entries) == len(plan.entries)


@pytest.mark.parametrize("code", [1254041, 1254004, 1002])
def test_ac6_systemic_codes_HALT_and_the_remainder_is_logged_not_attempted(code):
    """An answer about the TABLE or the APP: every remaining call would be refused
    identically, so the batch stops rather than spending a throttled call per call."""
    base = FakeBase(raises={"batch_create": coded(code)})
    draft = base.snapshot().edit()
    draft.add({"Text": "first"})           # creates run first — this is entry #1
    draft.set(R1, "Text", "never sent")
    plan = dry_run(draft)
    log = run(plan, base)

    assert log.halted
    assert log.halt["reason"] == Refusal.API_ERROR
    assert "HALTED" in log.halt["detail"]
    outcomes = [e.outcome for e in log.entries]
    assert outcomes.count("not-attempted") == 1
    assert len(log.entries) == len(plan.entries)
    assert [c[0] for c in base.calls] == ["batch_create"], "nothing after the halt was sent"


def test_ac6_a_scope_denial_HALTS_the_batch_LD206_inherited_verbatim():
    denial = LarkPermissionError("Code: 99991672, Msg: no permission", code=99991672,
                                 msg="no permission")
    base = FakeBase(raises={"batch_update": denial})
    draft = base.snapshot().edit()
    draft.set(R1, "Text", "one")
    draft.set(R2, "Text", "two")
    plan = dry_run(draft, records_per_call=1)
    log = run(plan, base)

    assert log.halted
    assert log.entries[0].refusal.reason == Refusal.PERMISSION_DENIED
    assert "console" in log.entries[0].refusal.detail
    assert "never requests, widens or escalates" in log.entries[0].refusal.detail
    assert log.entries[1].outcome == "not-attempted"
    assert len(base.calls) == 1


def test_ac6_a_rate_limit_HALTS_and_nothing_landed():
    base = FakeBase(raises={"batch_update": LarkRateLimitError(
        "Code: 99991400", code=99991400, msg="too many requests")})
    log = run(one_edit_plan(base), base)
    assert log.halted
    assert log.entries[0].refusal.reason == Refusal.RATE_LIMITED
    assert log.entries[0].outcome == "refused"
    assert not log.applied


def test_ac6_an_uncoded_api_error_is_TRANSPORT_and_INDETERMINATE():
    """No `code` means the call never got an answer (the transport's URLError wrap), so
    whether it landed is unknown and the engine says so instead of guessing."""
    base = FakeBase(raises={"batch_update": LarkAPIError("connection reset")})
    log = run(one_edit_plan(base), base)
    assert log.entries[0].outcome == "failed"
    assert log.entries[0].refusal.reason == Refusal.TRANSPORT_FAILURE
    assert log.indeterminate == log.entries
    assert log.halted


def test_ac6_an_unmodelled_exception_is_recorded_not_raised():
    base = FakeBase(raises={"batch_update": ValueError("something nobody modelled")})
    log = run(one_edit_plan(base), base)      # must not raise
    assert log.entries[0].outcome == "failed"
    assert log.entries[0].refusal.reason == Refusal.UNEXPECTED_ERROR
    assert "INDETERMINATE" in log.entries[0].refusal.detail


def test_ac6_a_local_config_error_is_entry_scoped_and_nothing_was_sent():
    base = FakeBase(raises={"batch_update": LarkConfigError("bad shape")})
    log = run(one_edit_plan(base), base)
    assert log.entries[0].outcome == "refused"
    assert log.entries[0].refusal.reason == Refusal.INVALID_REQUEST


def test_ac6_a_failure_AFTER_the_write_returned_is_applied_unverified():
    """The write-watch answer overrides the exception's own class: once the change is on the
    Base the only truthful record is `applied-unverified`."""
    base = FakeBase()
    original = base.list_tables
    state = {"n": 0}

    def flaky(app_token):
        state["n"] += 1
        if state["n"] > 1:        # the post-write anchor read
            raise LarkAPIError("the read after the write failed")
        return original(app_token)

    base.list_tables = flaky
    log = run(one_edit_plan(base), base)
    assert log.entries[0].outcome == "applied-unverified"
    assert log.entries[0].refusal.reason == Refusal.UNVERIFIED_WRITE
    assert log.entries[0].is_applied, "the change IS on the Base"
    assert log.halted, "the anchor is now unknown, so the batch stops"


def test_ac6_STALE_BASE_halts_THAT_TABLE_and_leaves_the_others_to_their_own_anchors():
    """D4′'s Base-specific refinement. `table.revision` is per-table isolated, so a halt
    scoped to one table is coherent — and the other table still applies."""
    base = FakeBase()
    draft = base.base_snapshot().edit()
    draft.table(MAIN).set("rec88HpEvHGLV4", "Text", "main moves")
    draft.table(OTHER).set(R1, "Text", "other moves")
    plan = dry_run(draft)
    base.move_out_of_band(MAIN)
    log = run(plan, base)

    assert [e.outcome for e in log.of_table(MAIN)] == ["stale"]
    assert [e.outcome for e in log.of_table(OTHER)] == ["applied"]
    assert set(log.table_halts) == {MAIN}
    assert log.halt is None, "a per-table halt is NOT a batch halt"
    assert [c[1] for c in base.calls] == [OTHER]


def test_ac6_the_classification_table_is_total_and_typed():
    """Every arm of the ruled table, asserted as data rather than through a live path."""
    rows = [
        (LarkRateLimitError("x", code=99991400), SYSTEMIC, Refusal.RATE_LIMITED, "no"),
        (LarkPermissionError("x", code=99991672), SYSTEMIC, Refusal.PERMISSION_DENIED, "no"),
        (coded(1254043), ENTRY_SCOPED, Refusal.API_ERROR, "no"),
        (coded(1254041), SYSTEMIC, Refusal.API_ERROR, "no"),
        (coded(1254004), SYSTEMIC, Refusal.API_ERROR, "no"),
        (coded(1002), SYSTEMIC, Refusal.API_ERROR, "no"),
        (coded(1254069), ENTRY_SCOPED, Refusal.API_ERROR, "no"),
        (coded(1254060), ENTRY_SCOPED, Refusal.API_ERROR, "no"),
        (coded(1255002), ENTRY_SCOPED, Refusal.API_ERROR, "no"),
        (LarkAPIError("no code"), SYSTEMIC, Refusal.TRANSPORT_FAILURE, "indeterminate"),
        (LarkConfigError("local"), ENTRY_SCOPED, Refusal.INVALID_REQUEST, "no"),
        (RuntimeError("unmodelled"), SYSTEMIC, Refusal.UNEXPECTED_ERROR, "indeterminate"),
    ]
    for exc, scope, reason, landed in rows:
        disposition = classify_apply_exception(exc, wrote=False)
        assert (disposition.scope, disposition.reason, disposition.landed) == \
            (scope, reason, landed), exc
    # `wrote` overrides every row above.
    for exc, _scope, _reason, _landed in rows:
        assert classify_apply_exception(exc, wrote=True).reason == Refusal.UNVERIFIED_WRITE


def test_ac6_the_write_seams_are_projected_off_the_op_registry():
    """A write op added to the registry cannot be forgotten here — which would make the engine
    claim "nothing landed" about a call that landed something."""
    assert WRITE_SEAMS == frozenset(d.name for d in WRITE_OPS)
    assert not (WRITE_SEAMS & READ_SEAMS), "the split is exhaustive and disjoint"


def test_ac6_the_write_watch_reports_only_a_seam_that_RETURNED():
    class Boom:
        def batch_update_records(self, *_a, **_k):
            raise LarkAPIError("late")

        def list_tables(self, *_a, **_k):
            return []

    watch = WriteWatch(Boom())
    with pytest.raises(LarkAPIError):
        watch.batch_update_records(APP, OTHER, [])
    assert watch.issued == ("batch_update_records",)
    assert watch.completed == ()
    assert watch.wrote is False


def test_ac6_structural_the_classification_sits_INSIDE_an_except_in_the_apply_loop():
    """The LD-148 structural guard, ported: a classification call outside a handler is a
    boundary that is not one."""
    source = pathlib.Path(inspect.getfile(apply_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    inside = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and getattr(child.func, "id", None) == \
                    "classify_apply_exception":
                inside.append(child.lineno)
    every = [n.lineno for n in ast.walk(tree)
             if isinstance(n, ast.Call) and getattr(n.func, "id", None) ==
             "classify_apply_exception"]
    assert every and sorted(inside) == sorted(every), (
        "every classification call must sit inside an `except`")


def test_ac6_the_boundary_does_not_swallow_a_BaseException():
    """The deliberate carve-out: a KeyboardInterrupt is the operator tearing the process
    down, and swallowing it into a log entry would be a worse bug."""
    base = FakeBase(raises={"batch_update": KeyboardInterrupt()})
    with pytest.raises(KeyboardInterrupt):
        run(one_edit_plan(base), base)


# --------------------------------------------------------------------------- #
# AC7 — the apply-log is 1:1 with the plan, and the invariant is DECLARED.      #
# --------------------------------------------------------------------------- #

def test_ac7_the_log_is_one_entry_per_plan_entry_matched_by_TARGET_not_by_length():
    base = FakeBase()
    draft = base.snapshot().edit()
    draft.set(R1, "Text", "one")
    draft.add({"Text": "two"})
    draft.delete(R3)
    plan = dry_run(draft)
    log = run(plan, base)

    assert len(log.entries) == len(plan.entries)
    for planned, logged in zip(plan.entries, log.entries):
        assert (logged.table_id, logged.record_id, logged.op) == \
            (planned.table_id, planned.record_id, planned.op)


def test_ac7_amplifier_a_systemic_failure_at_entry_one_still_produces_a_FULL_log():
    base = FakeBase(raises={"batch_update": coded(1254041)})
    draft = base.snapshot(revision=25).edit()
    for record_id in (R1, R2, R3):
        draft.set(record_id, "Text", "moved")
    plan = dry_run(draft, records_per_call=1)
    log = run(plan, base)

    assert len(log.entries) == len(plan.entries) == 3
    assert [e.outcome for e in log.entries] == ["refused", "not-attempted", "not-attempted"]
    for entry in log.not_attempted:
        assert entry.refusal.reason == Refusal.NOT_ATTEMPTED
        assert "halted at" in entry.refusal.detail
        assert "batch_update" in entry.refusal.detail, "the halt names WHERE"
    assert log.halt["not_attempted"] == 2


def test_ac7_amplifier_an_entry_scoped_failure_mid_batch_keeps_both_sides_correct():
    """The landed / not-landed column is right on both sides of the failure."""
    base = FakeBase(raises={"batch_update": coded(1254043)})
    draft = base.snapshot().edit()
    draft.set(R1, "Text", "refused")       # call 2 (updates) — raises
    draft.add({"Text": "created"})         # call 1 (creates) — lands
    draft.delete(R3)                       # call 3 (deletes) — still runs
    plan = dry_run(draft)
    log = run(plan, base)

    by_op = {e.op: e for e in log.entries}
    assert by_op["create"].is_applied and by_op["delete"].is_applied
    assert not by_op["update"].is_applied
    assert by_op["update"].refusal.reason == Refusal.API_ERROR
    assert len(log.entries) == len(plan.entries)


def test_ac7_a_plan_time_refusal_is_logged_and_never_attempted():
    base = FakeBase()
    draft = base.snapshot(table_id=MAIN).edit()
    draft.set("rec88HpEvHGLV4", "lookup", "computed cells cannot be written")
    plan = dry_run(draft)
    log = run(plan, base)
    assert [e.outcome for e in log.entries] == ["refused"]
    assert log.entries[0].refusal.reason == Refusal.NON_WRITABLE_FIELD
    assert base.calls == []


def test_ac7_the_log_round_trips_through_json():
    base = FakeBase()
    log = run(one_edit_plan(base), base)
    assert json.loads(log.to_json()) == log.to_dict()


def test_ac7_the_invariant_is_DECLARED_by_reference_never_redefined_here():
    """LD-254 authors the wording; this surface declares **that** id. No second id, no second
    wording — and the engine earns the declaration by carrying the boundary that makes it
    true."""
    from larkdocio.base import disposition as base_disposition

    assert DECLARED_SAFETY_CONTRACT is APPLY_LOG_COMPLETE
    assert callable(base_disposition.classify_apply_exception), (
        "declaring the invariant is EARNED: the package must carry the disposition boundary")

    src = pathlib.Path(inspect.getfile(apply_module)).resolve().parent
    for path in sorted(src.rglob("*.py")):  # LD-654: recursive population
        text = path.read_text(encoding="utf-8")
        assert APPLY_LOG_COMPLETE not in text, (
            f"{path.name} spells the contract id instead of importing it")
        assert "the apply-log is 1:1 with the plan and every entry ends in a typed " \
            "disposition" not in " ".join(text.lower().split()), (
                f"{path.name} carries a second wording of the invariant")


def test_ac7_the_declaration_is_the_ONE_ID_and_nothing_beside_it():
    """LD-259 left this as the forward promise: the `base-write` surface is published by the
    story that DESCRIBES it (LD-260), and when it arrives its declaration must be the ONE
    imported id rather than a second wording. It arrived. So this now asserts the promise was
    kept — the surface declares the house invariant by reference, the contract's `applies_to`
    names it, and the Base package still spells the id nowhere."""
    caps = capabilities(full=True)
    surface = caps["surfaces"]["base-write"]
    assert APPLY_LOG_COMPLETE in surface["safety_contracts"]
    assert caps["safety_contracts"][APPLY_LOG_COMPLETE]["applies_to"] == [
        "sheets-write", "base-write", "base-schema-write"]
    assert DECLARED_SAFETY_CONTRACT is APPLY_LOG_COMPLETE
