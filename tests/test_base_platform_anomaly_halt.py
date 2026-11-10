"""LD-338 — the platform-anomaly HALT: the CONSEQUENCE of LD-337's detection.

LD-337 shipped the *sentence*. It deliberately left the *waste*: a schema plan of N entries
meeting the ``/fields`` outage spent **N throttled writes** to collect N identical alien
refusals, and only then learned it was one platform-side condition. The maintainer ruled that waste
removable (session 2026-08-07, verbatim: *"can ship it, not that many people will affect it"*),
so the engine now **halts the tail** the moment the pattern is established.

**The whole file is OFFLINE.** The ``9499`` shape comes from LD-329's committed captures, reused
through the sibling module that already owns those fixtures
(``tests/test_base_platform_anomaly.py``) — one provenance, not two transcriptions — and every
run goes through a fake write client. Zero API calls, proven off this module's own import graph.

What each group pins:

* **the halt point** — a PREFIX rule whose floor is the SAME constant the plan-wide predicate
  reads; an **applied** entry disarms it; plan-time-refused and **stale** entries never count
  toward it, because Lark never judged them;
* **the non-anomaly shapes** — six negatives, each keeping today's continue-shape, plus the pin
  that the ruled tables were not touched: the halt is an engine-level PLAN rule *above* the
  classifier, so the entry-scoped/systemic ruling stands as written;
* **the aftermath** — no entry may still claim the batch CONTINUED once it demonstrably halted,
  and Lark's own code and message survive the correction;
* **the tail** — ``apply-log-complete``: 1:1 with the plan, in plan order, every skipped entry
  typed and told **why** and that **nothing was sent**;
* **no retry** — the halt spends FEWER calls, never more and never later.
"""
import ast
import inspect
from dataclasses import replace as dc_replace
from pathlib import Path

import pytest

from log_reading_apply import reading_the_log
from larkdocio.base import disposition as disposition_module
from larkdocio.base import schema_apply as schema_apply_module
from larkdocio.base import schema_ops_fields as sof
from larkdocio.base.disposition import (
    ENTRY_SCOPED_CODES,
    PLATFORM_ANOMALY_HALTED,
    PLATFORM_ANOMALY_MIN_ATTEMPTS,
    PLATFORM_ANOMALY_NOT_ATTEMPTED,
    PLATFORM_ANOMALY_NOT_YOUR_PLAN,
    SYSTEMIC_CODES,
)
from larkdocio.base.plan import ApplyLog, Refusal
from larkdocio.base.schema_apply import schema_apply, schema_dry_run
schema_apply = reading_the_log(schema_apply)
from larkdocio.errors import LarkPermissionError

# The captures, the fakes and the provenance guards are LD-337's — reused, never re-typed.
from test_base_platform_anomaly import (
    Client,
    World,
    anomaly_error,
    lark_error,
    ld329_code,
)

CONTINUED_CLAIM = "The batch CONTINUED"


# --------------------------------------------------------------------------- #
# The harness — one field-create plan per test, entries named table by table    #
# --------------------------------------------------------------------------- #

def requests_for(entries):
    """``[(table_id, revision), …]`` → one ``create_field`` request per entry, in that order."""
    return [sof.create_field("app", table_id, f"col-{index}", 1, ui_type="Text",
                             revision=revision)
            for index, (table_id, revision) in enumerate(entries)]


def apply_plan(requests, *, world=None, errors=None):
    world = world or World()
    client = Client(world, errors=errors)
    log = schema_apply(schema_dry_run(requests), client=client, read_client=world)
    return log, client, world


def run_entries(entries, *, world=None, errors=None):
    return apply_plan(requests_for(entries), world=world, errors=errors)


def all_refusing(entries, *, table_ids=("tbl1", "tbl2"), code=None, world=None):
    """Every listed table refuses the SAME alien code — the incident's own shape."""
    if code is None:
        errors = {table_id: anomaly_error(table_id) for table_id in table_ids}
    else:
        errors = {table_id: lark_error({"code": code, "msg": "ruled or foreign"},
                                       table_id=table_id)
                  for table_id in table_ids}
    return run_entries(entries, world=world, errors=errors)


#: A four-entry plan, every entry refusing ``9499`` on a vouched id: the halt's positive case.
FOUR_ANOMALOUS = (("tbl1", 7), ("tbl2", 7), ("tbl1", 7), ("tbl2", 7))


def assert_continued_shape(log, client, *, calls):
    """TODAY's shape: nothing halted, every entry attempted, no skipped tail."""
    assert log.halt is None, "a non-anomaly shape must not halt"
    assert log.halted is False
    assert log.not_attempted == ()
    assert len(client.calls) == calls
    for entry in log.entries:
        assert entry.outcome != "not-attempted"


# --------------------------------------------------------------------------- #
# AC1 — the HALT POINT: a prefix rule, floor two, written down                   #
# --------------------------------------------------------------------------- #

def test_ac1_the_TAIL_IS_HALTED_once_the_floor_of_identical_alien_refusals_is_reached():
    """The success metric, measured: N calls become N_threshold, and the tail is typed."""
    log, client, _ = all_refusing(FOUR_ANOMALOUS)

    assert len(client.calls) == PLATFORM_ANOMALY_MIN_ATTEMPTS == 2, (
        "the halt did not stop the tail — the waste this issue removes is still there")
    assert [entry.outcome for entry in log.entries] == [
        "refused", "refused", "not-attempted", "not-attempted"]
    assert log.halted is True
    assert log.halt["index"] == 1
    assert log.halt["not_attempted"] == 2
    assert log.platform_anomaly is not None


def test_ac1_the_FLOOR_is_TWO_and_ONE_alien_refusal_is_never_a_pattern():
    """One unmodelled error stays entry-scoped: halting on it would re-rule D4′ by the back
    door for every code outside the ruled tables."""
    assert PLATFORM_ANOMALY_MIN_ATTEMPTS == 2
    # tbl2 applies, so only ONE entry ever refuses — no pattern, no halt, all three calls spent.
    # (The applying table's later entries carry no revision: an applied write bumps the anchor,
    # and a STALE refusal is a different shape than the one under test here.)
    log, client, _ = all_refusing((("tbl1", 7), ("tbl2", None), ("tbl2", None)),
                                  table_ids=("tbl1",))
    assert [entry.outcome for entry in log.entries] == ["refused", "applied", "applied"]
    assert_continued_shape(log, client, calls=3)


def test_ac1_the_floor_is_ONE_constant_read_by_BOTH_the_disclosure_and_the_halt():
    """One number, one reader: a second threshold could drift from the detection it gates."""
    predicate = inspect.getsource(disposition_module.plan_wide_platform_anomaly)
    assert "PLATFORM_ANOMALY_MIN_ATTEMPTS" in predicate, (
        "the plan-wide predicate no longer reads the shared floor")
    engine = inspect.getsource(schema_apply_module.schema_apply)
    assert "plan_wide_platform_anomaly" in engine
    # The halt does NOT re-implement the count: it has no threshold literal of its own.
    assert "MIN_ATTEMPTS" not in engine


def test_ac1_the_floor_is_NOT_a_public_knob_on_schema_apply():
    """AC1.4 / Out of Scope: a caller-tunable halt threshold is its own mint."""
    assert list(inspect.signature(schema_apply).parameters) == [
        "plan", "client", "read_client", "consent", "settle_attempts", "sleep",
        # LD-458's partial-application opt-in — the ONE spelling every plan-gated apply
        # takes. It is not a halt knob, and the floor is still not tunable.
        "allow_partial"]


def test_ac1_an_APPLIED_entry_in_the_prefix_DISARMS_the_halt_permanently():
    """LD-337 condition 2, evaluated over the prefix: a plan that is landing writes is not
    meeting a platform-wide condition, however many later entries refuse."""
    log, client, _ = all_refusing((("tbl1", 7), ("tbl2", 7), ("tbl1", 7), ("tbl1", 7)),
                                  table_ids=("tbl1",))

    assert [entry.outcome for entry in log.entries] == [
        "refused", "applied", "refused", "refused"]
    assert_continued_shape(log, client, calls=4)
    assert log.platform_anomaly is None


def test_ac1_the_rule_is_ALL_ATTEMPTED_SO_FAR_not_consecutive_from_entry_zero():
    """A PLAN-TIME refusal never reached the platform, so it neither counts toward the floor
    nor keeps the halt from arming. Its own entry is untouched."""
    requests = requests_for((("tbl1", 7), ("tbl1", 7), ("tbl2", 7), ("tbl2", 7)))
    requests[0] = dc_replace(requests[0], op="no_such_registered_schema_op")
    errors = {table_id: anomaly_error(table_id) for table_id in ("tbl1", "tbl2")}
    log, client, _ = apply_plan(requests, errors=errors)

    assert log.entries[0].outcome == "refused"
    assert log.entries[0].refusal.reason == Refusal.INVALID_REQUEST
    assert PLATFORM_ANOMALY_NOT_YOUR_PLAN not in log.entries[0].refusal.detail, (
        "a plan-time refusal is not evidence of a platform anomaly")
    # The two ATTEMPTED entries are the pattern; entry 3 is the halted tail.
    assert [entry.outcome for entry in log.entries[1:]] == [
        "refused", "refused", "not-attempted"]
    assert len(client.calls) == 2
    assert log.halted is True


def test_ac1_a_STALE_entry_does_NOT_count_toward_the_floor_either():
    """The compare-and-swap refused it with ZERO writes, so Lark never judged it."""
    world = World(revision=9)
    errors = {table_id: anomaly_error(table_id) for table_id in ("tbl1", "tbl2")}
    log, client, _ = run_entries((("tbl1", 7), ("tbl1", 9), ("tbl2", 9), ("tbl2", 9)),
                                 world=world, errors=errors)

    assert log.entries[0].outcome == "stale"
    assert log.entries[0].refusal.reason == Refusal.STALE_BASE
    assert [entry.outcome for entry in log.entries[1:]] == [
        "refused", "refused", "not-attempted"]
    assert len(client.calls) == 2, "a stale entry issued a write, or was counted as one"


def test_ac1_the_halt_needs_a_TAIL_a_plan_that_ran_to_its_END_did_continue():
    """Two entries, both refusing, nothing left to skip: `halted` would be a claim about a
    tail that does not exist. The disclosure still fires — that is LD-337's, unchanged."""
    log, client, _ = all_refusing((("tbl1", 7), ("tbl2", 7)))

    assert len(client.calls) == 2
    assert [entry.outcome for entry in log.entries] == ["refused", "refused"]
    assert log.halt is None and log.halted is False
    assert log.platform_anomaly is not None
    assert CONTINUED_CLAIM in log.entries[0].refusal.detail


# --------------------------------------------------------------------------- #
# AC2 — the DETECTION is not relaxed; the non-anomaly shapes keep TODAY's shape  #
# --------------------------------------------------------------------------- #

def test_ac2_i_a_SINGLE_entry_plan_refusing_the_alien_code_does_not_halt():
    log, client, _ = all_refusing((("tbl1", 7),))
    assert [entry.outcome for entry in log.entries] == ["refused"]
    assert_continued_shape(log, client, calls=1)
    assert log.platform_anomaly is None


def test_ac2_ii_a_MIXED_CODE_plan_attempts_EVERY_entry():
    errors = {"tbl1": anomaly_error("tbl1"),
              "tbl2": lark_error({"code": 91403, "msg": "Forbidden"}, table_id="tbl2")}
    log, client, _ = run_entries(FOUR_ANOMALOUS, errors=errors)

    assert [entry.outcome for entry in log.entries] == ["refused"] * 4
    assert_continued_shape(log, client, calls=4)
    assert log.platform_anomaly is None


@pytest.mark.parametrize("code", [ENTRY_SCOPED_CODES[0], 99992402])
def test_ac2_iii_GENUINE_per_entry_refusals_spend_every_call(code):
    """A code the ruled table KNOWS is Lark judging each call — every call is still made."""
    log, client, _ = all_refusing(FOUR_ANOMALOUS, code=code)
    assert_continued_shape(log, client, calls=4)
    assert log.platform_anomaly is None


def test_ac2_iv_a_plan_where_some_entries_APPLIED_does_not_halt():
    log, client, _ = all_refusing((("tbl1", 7), ("tbl2", None), ("tbl1", 7), ("tbl2", None)),
                                  table_ids=("tbl1",))
    assert [entry.outcome for entry in log.entries] == [
        "refused", "applied", "refused", "applied"]
    assert_continued_shape(log, client, calls=4)


def test_ac2_v_a_PERMISSION_DENIED_plan_halts_on_ITS_OWN_terms_and_is_not_double_handled():
    """The reasons that already halt keep their own halt, their own detail, and no anomaly key."""
    errors = {table_id: LarkPermissionError(
                  f"create column in table {table_id} failed: Code: 99991672",
                  code=99991672, msg="Forbidden")
              for table_id in ("tbl1", "tbl2")}
    log, client, _ = run_entries(FOUR_ANOMALOUS, errors=errors)

    assert log.entries[0].refusal.reason == Refusal.PERMISSION_DENIED
    assert "lacks a required SCOPE" in log.entries[0].refusal.detail
    assert log.halted is True and log.halt["index"] == 0
    assert "platform_anomaly" not in log.halt, "an existing halt was re-labelled"
    assert log.platform_anomaly is None
    assert len(client.calls) == 1, "the systemic halt already stopped after one call"
    assert PLATFORM_ANOMALY_NOT_ATTEMPTED.split("{")[0] not in log.entries[1].refusal.detail


def test_ac2_v_a_SYSTEMIC_ruled_code_keeps_the_ruled_tables_own_halt():
    log, client, _ = all_refusing(FOUR_ANOMALOUS, code=SYSTEMIC_CODES[0])
    assert log.halted is True
    assert "platform_anomaly" not in log.halt
    assert len(client.calls) == 1


def test_ac2_vi_ids_the_READ_CLIENT_NEVER_LISTED_do_not_halt():
    """The conservative default: no read-side vouch, no claim — and so no halt."""
    world = World(listable=False)
    log, client, _ = all_refusing(FOUR_ANOMALOUS, world=world)
    assert [entry.outcome for entry in log.entries] == ["refused"] * 4
    assert_continued_shape(log, client, calls=4)


def test_ac2_the_RULED_TABLES_and_the_API_ERROR_disposition_are_UNCHANGED():
    """D4′ stands: the halt is set ABOVE the classifier, never inside it."""
    assert SYSTEMIC_CODES == (1254041, 1254004, 1002)
    assert ENTRY_SCOPED_CODES == (1254043, 1254069, 1254060, 1255002, 99992402,
                                  1254034, 1254023)
    assert ld329_code() not in SYSTEMIC_CODES
    assert ld329_code() not in ENTRY_SCOPED_CODES
    api_error = disposition_module.classify_apply_exception(
        anomaly_error("tbl1"), wrote=False)
    assert api_error.reason == Refusal.API_ERROR
    assert api_error.halts is False, "the classifier itself was re-ruled — AC2 forbids it"
    assert api_error.continues is True


# --------------------------------------------------------------------------- #
# AC3 — the AFTERMATH: nothing may still claim the batch CONTINUED               #
# --------------------------------------------------------------------------- #

def test_ac3_NO_entry_detail_claims_the_batch_CONTINUED_after_an_anomaly_halt():
    log, _, _ = all_refusing(FOUR_ANOMALOUS)
    for index, entry in enumerate(log.entries):
        assert CONTINUED_CLAIM not in entry.refusal.detail, (
            f"entry {index} still claims the batch continued, and it did not")
    for entry in log.entries[:2]:
        assert PLATFORM_ANOMALY_HALTED in entry.refusal.detail
        assert PLATFORM_ANOMALY_NOT_YOUR_PLAN in entry.refusal.detail


def test_ac3_LARKS_OWN_code_and_msg_SURVIVE_the_correction_byte_for_byte():
    log, _, _ = all_refusing(FOUR_ANOMALOUS)
    detail = log.entries[0].refusal.detail

    assert f"code={ld329_code()!r}" in detail
    assert 'Invalid parameter type in param: TableId' in detail
    assert "NOTHING landed for its entries." in detail
    # Order: Lark's answer, then the re-stated aftermath, then the disclosure.
    assert (detail.index("Invalid parameter type")
            < detail.index(PLATFORM_ANOMALY_HALTED)
            < detail.index(PLATFORM_ANOMALY_NOT_YOUR_PLAN))


def test_ac3_the_TYPED_CONTRACT_is_untouched_no_new_Refusal_reason_was_minted():
    log, _, _ = all_refusing(FOUR_ANOMALOUS)
    assert [entry.refusal.reason for entry in log.entries] == [
        Refusal.API_ERROR, Refusal.API_ERROR,
        Refusal.NOT_ATTEMPTED, Refusal.NOT_ATTEMPTED]
    assert "platform" not in " ".join(
        value for name, value in vars(Refusal).items()
        if name.isupper() and isinstance(value, str)).lower()


def test_ac3_the_rewrite_is_a_FIXED_SENTENCE_SWAP_that_cannot_be_broken_by_a_brace():
    """The append-after-formatting doctrine: no template is re-rendered over Lark's prose."""
    braces = "{who} {0} {} %s {code}"
    assert disposition_module.platform_anomaly_halted(braces) == braces
    swapped = disposition_module.platform_anomaly_halted(
        f"head {disposition_module._CONTINUED} tail")
    assert swapped == f"head {PLATFORM_ANOMALY_HALTED} tail"


# --------------------------------------------------------------------------- #
# AC4 — the SKIPPED entries: apply-log-complete holds                           #
# --------------------------------------------------------------------------- #

def test_ac4_the_log_is_ONE_TO_ONE_with_the_plan_IN_PLAN_ORDER():
    """The house invariant, quoted: *"the apply-log is 1:1 with the plan and every entry ends
    in a typed disposition, whatever happened … every remaining entry is logged not-attempted,
    never silently dropped"*. A halt that hid the tail would trade false reassurance for silent
    truncation, which is not a trade."""
    requests = requests_for(FOUR_ANOMALOUS)
    world = World()
    client = Client(world, errors={t: anomaly_error(t) for t in ("tbl1", "tbl2")})
    plan = schema_dry_run(requests)
    log = schema_apply(plan, client=client, read_client=world)

    assert len(log.entries) == len(plan.entries) == 4
    assert [entry.fields["field_name"] for entry in log.entries] == [
        "col-0", "col-1", "col-2", "col-3"]
    assert [entry.table_id for entry in log.entries] == ["tbl1", "tbl2", "tbl1", "tbl2"]
    for entry in log.entries:
        assert entry.refusal is not None and entry.refusal.detail.strip()


def test_ac4_every_SKIPPED_entry_is_TYPED_and_says_WHY_and_that_NOTHING_was_sent():
    log, _, _ = all_refusing(FOUR_ANOMALOUS)
    skipped = log.not_attempted

    assert len(skipped) == 2
    assert skipped == log.entries[2:]
    for entry in skipped:
        detail = entry.refusal.detail
        assert entry.outcome == "not-attempted"
        assert entry.refusal.reason == Refusal.NOT_ATTEMPTED
        # (a) the cause is named as the anomaly — not merely "the batch halted at …".
        assert "PLATFORM ANOMALY, NOT YOUR PLAN" in detail
        assert f"the same Lark code {ld329_code()}" in detail
        # (b) nothing was sent, and this entry was never judged.
        assert detail.startswith("NOTHING was sent for this entry")
        assert "never judged by Lark" in detail
        # (c) what a re-run would do.
        assert "A RE-RUN applies it normally once that route answers again" in detail
        assert "re-run the dry run first" in detail


def test_ac4_the_HALT_DICT_carries_the_count_and_enough_to_identify_the_anomaly():
    log, _, _ = all_refusing(FOUR_ANOMALOUS)

    assert log.halt["not_attempted"] == 2
    assert log.halt["reason"] == Refusal.API_ERROR
    anomaly = log.halt["platform_anomaly"]
    assert anomaly["code"] == ld329_code()
    assert anomaly["entries"] == 2
    assert anomaly["table_ids"] == ["tbl1", "tbl2"]
    # And it is ABSENT on every other halt — a new key defaults to not being there.
    other, _, _ = all_refusing(FOUR_ANOMALOUS, code=SYSTEMIC_CODES[0])
    assert "platform_anomaly" not in other.halt


def test_ac4_an_ORDINARY_halt_keeps_its_ORIGINAL_not_attempted_wording():
    """The anomaly wording is reached only by the anomaly halt; nothing else moved."""
    log, _, _ = all_refusing(FOUR_ANOMALOUS, code=SYSTEMIC_CODES[0])
    detail = log.not_attempted[0].refusal.detail
    assert detail.startswith("the batch halted at ")
    assert "NOTHING was sent for it" in detail
    assert "PLATFORM ANOMALY" not in detail


# --------------------------------------------------------------------------- #
# AC5 — NO retry, NO backoff, NO breather, NO re-probe                          #
# --------------------------------------------------------------------------- #

def test_ac5_the_halt_introduces_NO_sleep_NO_retry_NO_backoff_and_NO_re_probe():
    """LD-329 finding 4 is binding: *"Do not encode a retry for 9499 on this route."*"""
    for obj in (disposition_module.platform_anomaly_halted,
                disposition_module.platform_anomaly_not_attempted,
                schema_apply_module._vouched_ids,
                schema_apply_module._not_attempted):
        source = inspect.getsource(obj).lower()
        for banned in ("sleep", "retry", "backoff", "breather", "time."):
            assert banned not in source, f"{obj.__name__} introduces {banned!r}"


def test_ac5_the_halt_DECISION_ITSELF_makes_NO_extra_call():
    """It reads only what the loop already has in hand: the same reads a non-halting run makes,
    and FEWER writes — never one more, never one later."""
    halted, halt_client, halt_world = all_refusing(FOUR_ANOMALOUS)
    control, control_client, control_world = all_refusing(FOUR_ANOMALOUS, code=99992402)

    assert len(halt_client.calls) == 2 < len(control_client.calls) == 4
    # The PREFIX is byte-identical to what a continuing run does for those same entries.
    assert halt_client.calls == control_client.calls[:2]
    assert halt_world.reads == control_world.reads[:len(halt_world.reads)]


# --------------------------------------------------------------------------- #
# AC8 — OFFLINE, and the RECORD engine is untouched                             #
# --------------------------------------------------------------------------- #

def test_ac8_the_whole_arm_makes_ZERO_api_calls():
    """Read as an import graph, so the assertion cannot be satisfied by its own spelling."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    for forbidden in ("os", "urllib", "requests", "lark_oapi",
                      "larkdocio.base.schema_client", "larkdocio.base.client",
                      "larkdocio.common.transport", "larkdocio.auth"):
        assert not any(name == forbidden or name.startswith(forbidden + ".")
                       for name in imported), f"{forbidden} would make this arm non-offline"


def test_ac8_the_RECORD_engine_never_reaches_the_halt_and_its_LOG_SHAPE_is_unchanged():
    from larkdocio.base import apply as record_apply

    assert list(ApplyLog().to_dict()) == ["entries", "halt", "table_halts"]
    source = Path(inspect.getsourcefile(record_apply)).read_text(encoding="utf-8")
    for name in ("platform_anomaly", "PLATFORM_ANOMALY"):
        assert name not in source, (
            "widening the halt to the record engine is a separate mint — AC8's Out of Scope")


def test_ac8_the_SHEETS_engine_is_out_of_scope_and_untouched():
    from larkdocio.sheets import disposition as sheets_disposition

    source = Path(inspect.getsourcefile(sheets_disposition)).read_text(encoding="utf-8")
    assert "PLATFORM_ANOMALY" not in source


def test_ac8_the_new_constants_are_WIRED_so_the_reachability_sweep_stays_empty():
    from test_base_constant_reachability import DECLARED_UNWIRED

    assert DECLARED_UNWIRED == {}
    source = Path(inspect.getsourcefile(disposition_module)).read_text(encoding="utf-8")
    for name in ("PLATFORM_ANOMALY_MIN_ATTEMPTS", "PLATFORM_ANOMALY_HALTED",
                 "PLATFORM_ANOMALY_NOT_ATTEMPTED"):
        assert source.count(name) >= 2, f"{name} is defined but never read"
