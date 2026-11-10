"""LD-337 — the plan-wide **PLATFORM-ANOMALY** disclosure, offline and capture-anchored.

The consumer incident (recorded in the maintainers' incident notes) is the
mandate: a schema plan whose **every** entry refused with the same ``9499`` on table ids their
own listing had just returned was logged ``api-error`` with the ``CONTINUED`` aftermath — *"Lark
answered about the records or the values in this call"* — which is **the one thing it
demonstrably was not**. The falsely-reassuring sentence sent them to audit their own plan.

Everything here is **offline**: the ``9499`` shape is reconstructed from LD-329's committed
captures (the real ``code`` and Lark's real ``msg`` sentence, never a hand-invented string) and
driven through a fake write client, so a multi-entry plan refuses identically with **zero** API
calls. The positive case proves the disclosure fires; the six negatives prove each of the six
conjunctive conditions is load-bearing and that today's log shape is kept **byte for byte** when
any one is absent.
"""
import ast
import inspect
import json
from pathlib import Path

import pytest

from log_reading_apply import reading_the_log
from larkdocio.base import disposition as disposition_module
from larkdocio.base import schema_apply as schema_apply_module
from larkdocio.base import schema_ops_fields as sof
from larkdocio.base.disposition import (
    ENTRY_SCOPED_CODES,
    PLATFORM_ANOMALY_NOT_YOUR_PLAN,
    SYSTEMIC_CODES,
    ReadVouch,
    plan_wide_platform_anomaly,
)
from larkdocio.base.errors import raise_for_base_code
from larkdocio.base.plan import ApplyLog, Refusal
from larkdocio.base.schema_apply import schema_apply, schema_dry_run
schema_apply = reading_the_log(schema_apply)
from larkdocio.errors import LarkPermissionError

REPO = Path(__file__).resolve().parent.parent
CAPTURES = REPO / "tests" / "captures" / "base-study" / "captures"

#: The Lark ticket handle from the incident report — the consumer's own ``log_id``, replaced by a
#: placeholder of the same length in this tree, its leading day zeroed too (a Lark log_id opens
#: with its request's timestamp; the test only needs the value to flow through intact).
LOG_ID = "00000000000000000000000000EXAMPLE1"


# --------------------------------------------------------------------------- #
# The FIXTURE — LD-329's captures, not a hand-invented string                   #
# --------------------------------------------------------------------------- #

def _capture(name):
    return json.loads((CAPTURES / name).read_text(encoding="utf-8"))


def ld329_code():
    """``9499``, read from the shipped-client repro capture rather than typed here."""
    return _capture("ld329-01-shipped-client-repro.json")["_lark_code"]


def ld329_msg(table_id):
    """Lark's own ``msg`` sentence for one table id, taken from the RAW-transport capture.

    Provenance: ``tests/captures/base-study/captures/ld329-02-raw-transport-discriminator.json`` →
    ``response.calls`` label ``B`` (``POST`` on the exact path a ``GET`` had just accepted). Only
    the echoed id is substituted, so the sentence is Lark's, verbatim.
    """
    calls = _capture("ld329-02-raw-transport-discriminator.json")["response"]["calls"]
    template = next(call["msg"] for call in calls if call["label"].startswith("B"))
    echoed = next(call["path"].split("/tables/")[1].split("/")[0]
                  for call in calls if call["label"].startswith("B"))
    return template.replace(echoed, table_id)


def consumer_body(table_id):
    """The consumer's own raw response body, verbatim from the incident report.

    Carries the ``log_id`` line, so this fixture proves the disclosure survives a body whose
    text is full of braces and quotes — the append-after-formatting doctrine under load.
    """
    return {"code": ld329_code(),
            "msg": (f'Invalid parameter type in param: TableId. Invalid parameter value: '
                    f'"{table_id}"'),
            "error": {"log_id": LOG_ID}}


def lark_error(body, *, table_id):
    """The typed exception ``body`` raises, captured rather than re-raised."""
    with pytest.raises(Exception) as caught:
        raise_for_base_code(body, context=f"create column in table {table_id}")
    return caught.value


def anomaly_error(table_id):
    return lark_error({"code": ld329_code(), "msg": ld329_msg(table_id)}, table_id=table_id)


# --------------------------------------------------------------------------- #
# Fakes — this file's own, so no sibling module's fakes are disturbed           #
# --------------------------------------------------------------------------- #

class FakeTable:
    def __init__(self, table_id, name="t", revision=7):
        self.table_id = table_id
        self.name = name
        self.revision = revision


class FakeField:
    def __init__(self, field_id, field_name, field_type, ui_type):
        self.field_id = field_id
        self.field_name = field_name
        self.type = field_type
        self.ui_type = ui_type
        self.property = None


class World:
    """A read client over an in-memory Base. ``list_tables`` is the VOUCHING seam."""

    def __init__(self, table_ids=("tbl1", "tbl2"), *, revision=7, listable=True):
        self.tables = [FakeTable(table_id, revision=revision) for table_id in table_ids]
        self.fields = {table_id: [] for table_id in table_ids}
        self.reads = []
        self.listable = listable

    def list_tables(self, app_token):
        self.reads.append(("list_tables", app_token))
        return list(self.tables) if self.listable else []

    def list_fields(self, app_token, table_id):
        self.reads.append(("list_fields", app_token, table_id))
        return list(self.fields.get(table_id, ()))

    def get_app(self, app_token):   # pragma: no cover — a field op never reads the app
        raise AssertionError("a field op never reads the app")


class Client:
    """A schema client whose ``create_field`` raises whatever ``errors`` says for that table."""

    def __init__(self, world, *, errors=None):
        self.world = world
        self.errors = dict(errors or {})
        self.calls = []

    def create_field(self, app_token, table_id, field_name, field_type,
                     ui_type=None, properties=None):
        self.calls.append(("create_field", app_token, table_id, field_name))
        error = self.errors.get(table_id)
        if error is not None:
            raise error
        field = FakeField(f"fld{len(self.calls)}", field_name, field_type, ui_type)
        self.world.fields.setdefault(table_id, []).append(field)
        for table in self.world.tables:
            if table.table_id == table_id:
                table.revision += 1
        return field


def run(entries, *, world=None, errors=None):
    """Dry-run + apply one field-create plan. ``entries`` is ``[(table_id, revision), …]``."""
    world = world or World()
    client = Client(world, errors=errors)
    requests = [sof.create_field("app", table_id, f"col-{index}", 1, ui_type="Text",
                                 revision=revision)
                for index, (table_id, revision) in enumerate(entries)]
    plan = schema_dry_run(requests)
    log = schema_apply(plan, client=client, read_client=world)
    return log, client, world


def anomalous(*, errors=None, entries=(("tbl1", 7), ("tbl2", 7))):
    """The incident's own shape: every entry refuses the same 9499 on vouched ids."""
    errors = errors or {"tbl1": anomaly_error("tbl1"), "tbl2": anomaly_error("tbl2")}
    return run(list(entries), errors=errors)


# --------------------------------------------------------------------------- #
# AC5 — the POSITIVE case, offline, from the captures                           #
# --------------------------------------------------------------------------- #

def test_ac5_a_plan_whose_EVERY_entry_refuses_the_SAME_unknown_code_gets_the_disclosure():
    log, client, world = anomalous()

    assert log.platform_anomaly is not None, "the plan-wide disclosure did not fire"
    assert log.platform_anomaly["code"] == ld329_code()
    assert log.platform_anomaly["entries"] == 2
    assert log.platform_anomaly["table_ids"] == ["tbl1", "tbl2"]
    assert log.platform_anomaly["reason"] == Refusal.API_ERROR
    # Every entry's own detail carries it too — the second place the incident asked for.
    for entry in log.entries:
        assert entry.outcome == "refused"
        assert PLATFORM_ANOMALY_NOT_YOUR_PLAN in entry.refusal.detail


def test_ac5_the_code_and_the_MSG_are_the_CAPTURED_ones_not_hand_invented():
    """Provenance guard: the fixture is LD-329's capture, so a re-transcription reddens."""
    assert ld329_code() == 9499
    assert ld329_msg("tblZ") == (
        'Invalid parameter type in param: TableId. Invalid parameter value: "tblZ". '
        "Please check and modify accordingly.")
    assert "TableId" in _capture("ld329-01-shipped-client-repro.json")["_lark_msg"]


def test_ac5_the_CONSUMERS_OWN_BODY_verbatim_log_id_and_all_still_gets_the_disclosure():
    errors = {table_id: lark_error(consumer_body(table_id), table_id=table_id)
              for table_id in ("tbl1", "tbl2")}
    log, _, _ = anomalous(errors=errors)

    assert log.platform_anomaly is not None
    assert consumer_body("tbl1")["error"]["log_id"] == LOG_ID
    detail = log.entries[0].refusal.detail
    # Lark's own answer is still readable, and the disclosure is appended AFTER it.
    assert 'Invalid parameter value: "tbl1"' in detail
    assert detail.index("Invalid parameter value") < detail.index(
        PLATFORM_ANOMALY_NOT_YOUR_PLAN)


def test_ac5_the_whole_offline_arm_makes_ZERO_api_calls():
    """No real client, no transport, no credentials: proven off this module's own IMPORTS.

    Read as an import graph rather than as text, so this test cannot be satisfied by the
    spelling of its own assertion — the trap the ``ENTRY_SCOPED_CODES`` guard names.
    """
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


# --------------------------------------------------------------------------- #
# AC1 — the six conditions, each proven LOAD-BEARING by its own negative        #
# --------------------------------------------------------------------------- #

def _todays_shape(log):
    """Today's log shape, asserted unchanged: no slot, no appended sentence."""
    assert log.platform_anomaly is None
    assert "platform_anomaly" not in log.to_dict()
    for entry in log.entries:
        if entry.refusal is not None and entry.refusal.detail:
            assert PLATFORM_ANOMALY_NOT_YOUR_PLAN not in entry.refusal.detail


def test_ac1_condition1_a_SINGLE_entry_plan_keeps_todays_shape():
    log, _, _ = anomalous(entries=(("tbl1", 7),))
    assert len(log.entries) == 1
    _todays_shape(log)


def test_ac1_condition2_a_plan_where_ONE_ENTRY_LANDED_keeps_todays_shape():
    log, _, _ = anomalous(errors={"tbl1": anomaly_error("tbl1")})
    assert [e.outcome for e in log.entries] == ["refused", "applied"]
    _todays_shape(log)


def test_ac1_condition3_a_MIXED_CODE_plan_keeps_todays_shape():
    other = lark_error({"code": 91403, "msg": "Forbidden"}, table_id="tbl2")
    log, _, _ = anomalous(errors={"tbl1": anomaly_error("tbl1"), "tbl2": other})
    assert [e.outcome for e in log.entries] == ["refused", "refused"]
    _todays_shape(log)


@pytest.mark.parametrize("code", [ENTRY_SCOPED_CODES[0], SYSTEMIC_CODES[0]])
def test_ac1_condition4_a_code_the_RULED_TABLE_KNOWS_keeps_todays_shape(code):
    errors = {table_id: lark_error({"code": code, "msg": "ruled"}, table_id=table_id)
              for table_id in ("tbl1", "tbl2")}
    log, _, _ = anomalous(errors=errors)
    _todays_shape(log)


def test_ac1_condition5_a_wholly_PERMISSION_DENIED_plan_keeps_its_OWN_disclosure():
    """Every other reason already carries a TRUE disclosure; this one must not overwrite it."""
    errors = {table_id: LarkPermissionError(
                  f"create column in table {table_id} failed: Code: 99991672",
                  code=99991672, msg="Forbidden")
              for table_id in ("tbl1", "tbl2")}
    log, _, _ = anomalous(errors=errors)
    assert log.entries[0].refusal.reason == Refusal.PERMISSION_DENIED
    assert "lacks a required SCOPE" in log.entries[0].refusal.detail
    _todays_shape(log)


def test_ac1_condition6_ids_the_READ_CLIENT_NEVER_LISTED_keep_todays_shape():
    """No read-side artifact ⇒ do NOT fire. The conservative default, proven."""
    world = World(listable=False)
    errors = {table_id: anomaly_error(table_id) for table_id in ("tbl1", "tbl2")}
    log, _, _ = run([("tbl1", 7), ("tbl2", 7)], world=world, errors=errors)
    assert [e.outcome for e in log.entries] == ["refused", "refused"]
    _todays_shape(log)


def test_ac1_the_rule_is_CODE_AGNOSTIC_a_different_unknown_code_fires_too():
    errors = {table_id: lark_error({"code": 91403, "msg": "who knows"}, table_id=table_id)
              for table_id in ("tbl1", "tbl2")}
    log, _, _ = anomalous(errors=errors)
    assert log.platform_anomaly["code"] == 91403


def test_ac1_no_LARK_CODE_is_HARDCODED_in_the_detection_or_the_engine():
    """The observed code appears in PROSE only — never as a literal the rule branches on.

    Read as AST constants, so a docstring naming ``9499`` (this module does, and so does the
    disposition boundary's own) is not mistaken for a special case in the logic.
    """
    for module in (disposition_module, schema_apply_module):
        tree = ast.parse(Path(inspect.getsourcefile(module)).read_text(encoding="utf-8"))
        literals = {node.value for node in ast.walk(tree)
                    if isinstance(node, ast.Constant) and isinstance(node.value, int)}
        assert ld329_code() not in literals, (
            f"{module.__name__} branches on the observed code — the rule is code-agnostic")


# --------------------------------------------------------------------------- #
# AC2 — the wording STATES ITS EVIDENCE and invents nothing                     #
# --------------------------------------------------------------------------- #

def test_ac2_the_disclosure_carries_ALL_THREE_parts():
    log, _, _ = anomalous()
    disclosure = log.platform_anomaly["detail"]

    # (a) what was OBSERVED — N of N, the code, the vouched ids.
    assert "PLATFORM ANOMALY, NOT YOUR PLAN." in disclosure
    assert "OBSERVED:" in disclosure
    assert "all 2 of the 2 calls" in disclosure
    assert "9499" in disclosure
    assert "tbl1, tbl2" in disclosure
    # (b) what it MEANS — platform side, not the caller's plan.
    assert "MEANS:" in disclosure
    assert "not in your plan" in disclosure
    # (c) what to DO.
    assert "WHAT TO DO:" in disclosure
    assert "change NOTHING in your plan" in disclosure
    assert "Re-run" in disclosure
    assert "log_id" in disclosure


def test_ac2_the_disclosure_INVENTS_NO_cause_scope_endpoint_or_outage():
    from larkdocio.permissions import ENDPOINT_SCOPES

    text = PLATFORM_ANOMALY_NOT_YOUR_PLAN
    scopes = {getattr(item, "scope") for row in ENDPOINT_SCOPES for cell in row
              for item in (cell or ()) if hasattr(item, "scope")}
    assert scopes, "the scope registry read back empty — this guard would assert nothing"
    for scope in scopes:
        assert scope not in text, f"the disclosure names the scope {scope!r}"
    assert "/open-apis" not in text
    for diagnosis in ("outage", "incident", "degraded", "maintenance", "rollback",
                      "server error", "5xx", "deploy"):
        assert diagnosis not in text.lower(), f"the disclosure diagnoses {diagnosis!r}"


# --------------------------------------------------------------------------- #
# AC3 — BOTH places, and NEITHER destroys what is already there                 #
# --------------------------------------------------------------------------- #

def test_ac3_the_log_slot_DEFAULTS_TO_ABSENT():
    assert ApplyLog().platform_anomaly is None
    assert "platform_anomaly" not in ApplyLog().to_dict()


def test_ac3_the_pre_existing_detail_is_PREFIX_PRESERVED_and_the_reason_UNCHANGED():
    log, _, _ = anomalous()
    baseline_log, _, _ = anomalous(entries=(("tbl1", 7),))     # single entry ⇒ no disclosure

    baseline = baseline_log.entries[0].refusal.detail
    detail = log.entries[0].refusal.detail
    head, _, tail = detail.partition(" PLATFORM ANOMALY,")
    # The whole of today's detail — code, msg AND the `CONTINUED` aftermath — is the prefix.
    assert head == baseline.replace("col-0", "col-0")
    assert "The batch CONTINUED" in head
    assert f"code={ld329_code()!r}" in head
    assert tail, "the disclosure is appended, not substituted"
    # The typed contract is untouched: no new Refusal reason value was minted.
    assert log.entries[0].refusal.reason == Refusal.API_ERROR
    assert "platform" not in " ".join(
        value for name, value in vars(Refusal).items()
        if name.isupper() and isinstance(value, str)).lower()


# --------------------------------------------------------------------------- #
# AC4 — the SHARED ApplyLog and the RECORD engine                               #
# --------------------------------------------------------------------------- #

def test_ac4_the_RECORD_engines_log_shape_is_UNCHANGED():
    from larkdocio.base import apply as record_apply

    assert list(ApplyLog().to_dict()) == ["entries", "halt", "table_halts"]
    source = Path(inspect.getsourcefile(record_apply)).read_text(encoding="utf-8")
    assert "platform_anomaly" not in source, (
        "the record engine must never set the slot — widening it there is a separate mint")


def test_ac4_the_detection_helpers_ONLY_caller_is_the_SCHEMA_engine():
    src = REPO / "src" / "larkdocio"
    callers = sorted(path.relative_to(src).as_posix()
                     for path in src.rglob("*.py")
                     if "plan_wide_platform_anomaly" in path.read_text(encoding="utf-8"))
    assert callers == ["base/disposition.py", "base/schema_apply.py"]


# --------------------------------------------------------------------------- #
# AC6 — the LD-307 reachability guard                                           #
# --------------------------------------------------------------------------- #

def test_ac6_the_new_constant_is_WIRED_so_DECLARED_UNWIRED_stays_empty():
    from test_base_constant_reachability import DECLARED_UNWIRED

    assert DECLARED_UNWIRED == {}
    source = Path(inspect.getsourcefile(disposition_module)).read_text(encoding="utf-8")
    assert source.count("PLATFORM_ANOMALY_NOT_YOUR_PLAN") >= 2, "defined but never read"


# --------------------------------------------------------------------------- #
# AC7 — NO retry, NO backoff, NO breather. Nothing about the calls moves.        #
# --------------------------------------------------------------------------- #

def test_ac7_the_PREFIX_calls_are_IDENTICAL_and_there_are_ZERO_calls_after_the_halt(
        monkeypatch):
    """**AMENDED by LD-338**, on the authority of the maintainer ruling of session 2026-08-07 (verbatim:
    *"can ship it, not that many people will affect it"*) — the answer to the scope question this
    issue's § Problem (ii) recorded and deliberately did not answer.

    **What this test asserted BEFORE the amendment:** the write-call count and order for an
    anomalous plan were *identical with and without the disclosure* — LD-337 added a sentence and
    changed nothing about the calls, so its pin held the call count equal to today's.

    **What it asserts NOW:** LD-338 halts the tail on purpose, so the count deliberately DROPS.
    The invariant that survives is the one that matters — the calls that ARE made are the same
    calls in the same order up to the halt, and there are **zero** after it. The detection itself
    is unchanged (this module's other pins are the proof); only the consequence moved, and it
    moved toward spending FEWER calls, never more and never later.
    """
    entries = (("tbl1", 7), ("tbl2", 7), ("tbl1", 7), ("tbl2", 7))
    with_log, with_client, with_world = anomalous(entries=entries)
    monkeypatch.setattr(schema_apply_module, "plan_wide_platform_anomaly",
                        lambda *args, **kwargs: None)
    without_log, without_client, without_world = anomalous(entries=entries)

    assert with_log.platform_anomaly is not None
    assert without_log.platform_anomaly is None
    # WITHOUT the rule: today's pre-LD-338 shape — every entry attempted, nothing halted.
    assert len(without_client.calls) == 4
    assert without_log.halt is None
    assert [e.outcome for e in without_log.entries] == ["refused"] * 4
    # WITH it: the same prefix, and the tail costs nothing.
    assert len(with_client.calls) == 2
    assert with_client.calls == without_client.calls[:2]
    assert with_world.reads == without_world.reads[:len(with_world.reads)]
    assert [e.outcome for e in with_log.entries] == [
        "refused", "refused", "not-attempted", "not-attempted"]


def test_ac7_the_new_code_introduces_NO_sleep_NO_retry_NO_backoff():
    for obj in (plan_wide_platform_anomaly, ReadVouch,
                disposition_module.attempted_write):
        source = inspect.getsource(obj).lower()
        for banned in ("sleep", "retry", "backoff", "breather", "time."):
            assert banned not in source, f"{obj.__name__} introduces {banned!r}"


# --------------------------------------------------------------------------- #
# The detection function itself — unit-level, so each clause is nameable        #
# --------------------------------------------------------------------------- #

def _attempt(position, table_id, code, reason=Refusal.API_ERROR):
    return disposition_module.AttemptedWrite(position=position, table_id=table_id,
                                             reason=reason, code=code)


def test_the_detection_function_returns_None_on_an_EMPTY_run():
    assert plan_wide_platform_anomaly((), vouched_table_ids={"tbl1"}) is None


def test_the_detection_function_needs_a_NON_EMPTY_vouch_set():
    attempts = [_attempt(0, "tbl1", 9499), _attempt(1, "tbl2", 9499)]
    assert plan_wide_platform_anomaly(attempts, vouched_table_ids=()) is None
    anomaly = plan_wide_platform_anomaly(attempts, vouched_table_ids={"tbl1", "tbl2"})
    assert anomaly is not None and anomaly.positions == (0, 1)


def test_an_APP_SCOPED_attempt_with_no_table_id_can_never_be_vouched_for():
    attempts = [_attempt(0, None, 9499), _attempt(1, "tbl2", 9499)]
    assert plan_wide_platform_anomaly(attempts, vouched_table_ids={"tbl2"}) is None


def test_ReadVouch_records_the_ids_its_LISTING_returned_and_forwards_everything_else():
    world = World()
    vouch = ReadVouch(world)
    assert vouch.vouched_table_ids == frozenset()
    assert [t.table_id for t in vouch.list_tables("app")] == ["tbl1", "tbl2"]
    assert vouch.vouched_table_ids == frozenset({"tbl1", "tbl2"})
    # Everything else is the wrapped client's, verbatim — no read is invented.
    assert vouch.list_fields("app", "tbl1") == []
    assert world.reads == [("list_tables", "app"), ("list_fields", "app", "tbl1")]


def test_the_DRY_RUNS_OWN_SCAN_also_vouches_for_the_ids_it_inspected():
    """The second read-side artifact AC1.6 names: ``schema_dry_run``'s cross-table scan."""
    world = World(listable=False)
    errors = {table_id: anomaly_error(table_id) for table_id in ("tbl1", "tbl2")}
    client = Client(world, errors=errors)
    requests = [sof.create_field("app", table_id, "col", 1, ui_type="Text")
                for table_id in ("tbl1", "tbl2")]
    plan = schema_dry_run(requests)
    object.__setattr__(plan, "_preview_cost",
                       {"read_calls": 1, "tables_inspected": ["tbl1", "tbl2"], "what": "scan"})
    log = schema_apply(plan, client=client, read_client=world)
    assert log.platform_anomaly is not None
    assert log.platform_anomaly["table_ids"] == ["tbl1", "tbl2"]
