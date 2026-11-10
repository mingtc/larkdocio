"""LD-263 — the plan-gated Base SCHEMA engine: AC1's gate, AC3, AC5's disclosure, AC7's
read-back rule.

Three things are asserted here that nothing else can assert:

* **the gate** — a hand-built look-alike plan is refused, the shape all three landed engines
  ship;
* **the disclosure (O3″)** — every app-scoped entry says it carries **no** revision guard, and
  the record engine's entries — which really do carry ``STALE_BASE`` — do **not** carry that
  disclosure. Two facts, two statements, neither absorbed into the other;
* **the read-back rule** — `code:0` is never evidence. A deliberate-defect check drives the
  engine against a client that answers success and changes nothing, and the op is reported
  ``dropped``.
"""
import json

import pytest

from base_schema_fakes import FakeBaseWorld, NoSleep, ScriptedSchemaClient
from log_reading_apply import reading_the_log
from larkdocio.base.plan import ApplyLog, Refusal
from larkdocio.base.schema_apply import (
    DECLARED_SAFETY_CONTRACT,
    SCHEMA_READ_SEAMS,
    SCHEMA_WRITE_SEAMS,
    schema_apply,
    schema_dry_run,
)
schema_apply = reading_the_log(schema_apply)
from larkdocio.base.schema_plan import (
    NO_APP_REVISION_CAS,
    SETTLE_NOT_COMPLETE,
    SchemaPlan,
    batch_create_tables,
    copy_base,
    create_base,
    create_table,
    rename_base,
    rename_table,
)
from larkdocio.base.schema_settle import ASYNC_SETTLE_CONTRACT


def world(**kwargs):
    return FakeBaseWorld(
        apps=kwargs.pop("apps", {"appOLD": "Scratch Base"}),
        tables=kwargs.pop("tables", {"appOLD": {"tbl1": "Table", "tbl2": "Table 2"}}),
        **kwargs)


def run(requests, *, w=None, deaf=(), raises=None, settle_attempts=10):
    w = w or world()
    client = ScriptedSchemaClient(w, deaf=deaf, raises=raises)
    plan = schema_dry_run(requests)
    log = schema_apply(plan, client=client, read_client=w,
                       settle_attempts=settle_attempts, sleep=NoSleep())
    return plan, log, w, client


# --------------------------------------------------------------------------- #
# AC1 — the gate                                                               #
# --------------------------------------------------------------------------- #

def test_a_SchemaPlan_CANNOT_BE_HAND_BUILT():
    with pytest.raises(TypeError) as caught:
        SchemaPlan(entries=())
    assert "schema_dry_run" in str(caught.value)


def test_schema_apply_REFUSES_a_look_alike_plan():
    class LookAlike:
        entries = ()
        api_call_count = 0

    with pytest.raises(TypeError) as caught:
        schema_apply(LookAlike(), client=object(), read_client=object())
    assert "SchemaPlan" in str(caught.value)


def test_schema_apply_REFUSES_a_LIST_OF_REQUESTS_there_is_no_direct_apply_path():
    with pytest.raises(TypeError):
        schema_apply([create_base("x", "fldrXYZ")], client=object(), read_client=object())


def test_schema_apply_NEEDS_BOTH_CLIENTS_because_verification_is_a_READ():
    plan = schema_dry_run([create_base("x", "fldrXYZ")])
    with pytest.raises(TypeError) as caught:
        schema_apply(plan, client=object(), read_client=None)
    assert "READ-BACK" in str(caught.value)


def test_dry_run_COSTS_ZERO_API_CALLS():
    w = world()
    plan = schema_dry_run([create_base("a", "fldrXYZ"), copy_base("appOLD", "b", folder_token="fldrXYZ"),
                           batch_create_tables("appOLD", ["x", "y"],
                        accept_locale_default_primary=True)])
    assert w.calls == []
    assert plan.api_call_count == 3
    assert len(plan) == 3


def test_dry_run_REFUSES_AN_UNREGISTERED_OP_at_plan_time_for_free():
    from larkdocio.base.schema_plan import SchemaRequest

    # `delete_app` — the drive-file delete that removes a Base — is the op this surface
    # deliberately does not ship, so it is the honest stand-in now that `delete_table` is real.
    plan = schema_dry_run([SchemaRequest(op="delete_app", app_token="a",
                                         describe="delete a Base")])
    assert plan.api_call_count == 0
    assert plan.refusals[0].refusal.reason == Refusal.INVALID_REQUEST
    assert "delete_app" in plan.refusals[0].refusal.detail


def test_the_engine_DECLARES_the_house_invariant_BY_REFERENCE():
    from larkdocio.capabilities._contracts import APPLY_LOG_COMPLETE

    assert DECLARED_SAFETY_CONTRACT is APPLY_LOG_COMPLETE


def test_the_seams_are_PROJECTED_off_the_registry_and_are_DISJOINT():
    from larkdocio.base.schema_ops import schema_ops

    assert SCHEMA_WRITE_SEAMS == frozenset(d.name for d in schema_ops())
    assert not (SCHEMA_WRITE_SEAMS & SCHEMA_READ_SEAMS)


# --------------------------------------------------------------------------- #
# AC5 — NO app.revision CAS, and the absence is DISCLOSED (O3″)                 #
# --------------------------------------------------------------------------- #

def test_EVERY_app_scoped_entry_CARRIES_the_no_revision_guard_disclosure():
    plan = schema_dry_run([create_base("a", "fldrXYZ"), rename_base("appOLD", "b"),
                           copy_base("appOLD", "c", folder_token="fldrXYZ"), create_table("appOLD", "t", primary_field_name="Title"),
                           batch_create_tables("appOLD", ["u"],
                        accept_locale_default_primary=True),
                           rename_table("appOLD", "tbl1", "v")])
    for entry in plan.entries:
        assert entry.revision_guard is None, entry.op
        assert entry.revision_guard_disclosure == NO_APP_REVISION_CAS, entry.op
        assert entry.scope == "app", entry.op
    blob = json.loads(plan.to_json())
    assert blob["staleness"]["no_app_revision_compare_and_swap"] == NO_APP_REVISION_CAS
    assert blob["staleness"]["verified_by"] == "read-back"


def test_the_disclosure_is_ABSENT_from_the_RECORD_engines_entries_which_DO_carry_STALE_BASE():
    """The other direction of AC5. The record plan's entries are guarded by
    `table.revision`; stamping them with a *no guard* disclosure would be false, and leaving
    the schema plan without one would be worse."""
    from test_base_plan_gate import _edited_draft
    from larkdocio.base.apply import dry_run

    record_plan = dry_run(_edited_draft())
    for entry in record_plan.entries:
        blob = entry.to_dict()
        assert "revision_guard_disclosure" not in blob
        assert blob["revision_guard"] in ("active", "unavailable")
    assert Refusal.STALE_BASE == "stale-base"


def test_the_disclosure_NAMES_ALL_THREE_DISAGREEING_READINGS_and_forbids_inventing_a_CAS():
    for reading in ("0 to 1", "0 to 14", "0 to 5"):
        assert reading in NO_APP_REVISION_CAS, reading
    assert "READ-BACK" in NO_APP_REVISION_CAS
    assert "not one counting rule" in NO_APP_REVISION_CAS


def test_the_disclosure_is_a_SECOND_FACT_not_a_restatement_of_the_record_engines():
    from larkdocio.base.plan import NO_SERVER_SIDE_CAS

    assert NO_APP_REVISION_CAS != NO_SERVER_SIDE_CAS
    assert "app.revision" in NO_APP_REVISION_CAS
    assert "table.revision" in NO_SERVER_SIDE_CAS
    assert "app.revision" not in NO_SERVER_SIDE_CAS


def test_the_apply_log_REPEATS_the_disclosure_on_every_entry():
    _plan, log, _w, _c = run([create_table("appOLD", "new", primary_field_name="Title")])
    assert log.entries[0].to_dict()["revision_guard_disclosure"] == NO_APP_REVISION_CAS


# --------------------------------------------------------------------------- #
# AC7 — the read-back rule, and the deliberate defect that proves it bites      #
# --------------------------------------------------------------------------- #

def test_a_TABLE_CREATE_is_confirmed_by_the_TABLE_LISTING_not_by_code_0():
    _plan, log, w, _c = run([create_table("appOLD", "third", primary_field_name="Title")])
    entry = log.entries[0]
    assert entry.outcome == "applied"
    assert entry.created_table_ids and entry.created_table_ids[0] in w.tables["appOLD"]
    assert ("list_tables", "appOLD") in w.calls
    assert entry.read_back["listed"] is True


def test_DEFECT_a_call_that_ANSWERS_SUCCESS_AND_CHANGES_NOTHING_is_reported_DROPPED():
    """The falsification of the discipline. `code:0` proves acceptance, never effect."""
    _plan, log, _w, client = run([create_table("appOLD", "ghost", primary_field_name="Title")], deaf={"create_table"})
    entry = log.entries[0]
    assert entry.outcome == "dropped"
    assert entry.refusal.reason == Refusal.WRITE_NOT_OBSERVED
    assert "read-back" in entry.refusal.detail.lower()
    assert client.calls[0][0] == "create_table", "the call really was made"
    assert not log.applied


def test_DEFECT_a_RENAME_that_did_nothing_is_reported_DROPPED_too():
    _plan, log, _w, _c = run([rename_base("appOLD", "renamed")], deaf={"rename_app"})
    assert log.entries[0].outcome == "dropped"


def test_a_BATCH_CREATE_of_two_tables_is_verified_in_a_SINGLE_read_back():
    """The spec's own test-rigor amplifier: one call, one verification, both tables."""
    _plan, log, w, _c = run([batch_create_tables("appOLD", ["p1sw-A", "p1sw-B"],
                        accept_locale_default_primary=True)])
    entry = log.entries[0]
    assert entry.outcome == "applied"
    assert len(entry.created_table_ids) == 2
    assert entry.read_back["read_backs"] == 1
    assert w.calls.count(("list_tables", "appOLD")) == 1
    assert sorted(w.tables["appOLD"].values())[-2:] == ["p1sw-A", "p1sw-B"]


def test_a_BATCH_whose_SECOND_table_never_appeared_is_NOT_reported_applied():
    w = world()
    client = ScriptedSchemaClient(w)
    plan = schema_dry_run([batch_create_tables("appOLD", ["a", "b"],
                        accept_locale_default_primary=True)])

    real = client.batch_create_tables

    def half(app_token, names, **kwargs):
        ids = real(app_token, names, **kwargs)
        w.tables[app_token].pop(ids[1])          # the server "forgot" one
        return ids

    client.batch_create_tables = half
    log = schema_apply(plan, client=client, read_client=w, sleep=NoSleep())
    assert log.entries[0].outcome == "dropped"
    assert log.entries[0].read_back["missing"]


def test_a_RENAME_IS_RESTORABLE_the_probes_own_shape():
    """`p1-q4-03` renamed the Scratch Base and put the name back in the same probe."""
    w = world()
    client = ScriptedSchemaClient(w)
    for name in ("larkdocio-p1-rename-probe", "Scratch Base"):
        plan = schema_dry_run([rename_base("appOLD", name)])
        log = schema_apply(plan, client=client, read_client=w, sleep=NoSleep())
        assert log.entries[0].outcome == "applied"
        assert w.apps["appOLD"] == name
    assert w.apps["appOLD"] == "Scratch Base"


def test_a_TABLE_RENAME_is_confirmed_against_the_listing():
    _plan, log, w, _c = run([rename_table("appOLD", "tbl2", "Renamed")])
    assert log.entries[0].outcome == "applied"
    assert w.tables["appOLD"]["tbl2"] == "Renamed"


# --------------------------------------------------------------------------- #
# AC2 / AC3 — the copy through the engine                                       #
# --------------------------------------------------------------------------- #

def test_THE_COPYS_ECHO_IS_NOT_ITS_STATE_the_engine_SETTLES_before_it_believes_anything():
    w = world()
    w.copying = {}
    client = ScriptedSchemaClient(w)
    plan = schema_dry_run([copy_base("appOLD", "larkdocio-DISPOSABLE-copy", folder_token="fldrXYZ")])
    assert plan.entries[0].asynchronous is True

    # The copy answers 1254036 twice before it is readable — the captured shape.
    real = client.copy_app

    def racing(app_token, name, without_content=False, folder_token=None):
        app = real(app_token, name, without_content, folder_token)
        w.copying[app.app_token] = 2
        return app

    client.copy_app = racing
    sleeper = NoSleep()
    log = schema_apply(plan, client=client, read_client=w, sleep=sleeper)

    entry = log.entries[0]
    assert entry.outcome == "applied"
    assert entry.settle["status"] == "settled"
    assert entry.settle["attempts"] == 3
    assert entry.settle["codes"] == [1254036, 1254036]
    assert len(sleeper.sleeps) == 2
    assert entry.read_back["table_ids"], "the tables are readable only AFTER the settle"


def test_a_COPY_THAT_NEVER_SETTLES_is_applied_unverified_NOT_failed_and_NOT_applied():
    w = world()
    client = ScriptedSchemaClient(w)
    plan = schema_dry_run([copy_base("appOLD", "c", folder_token="fldrXYZ")])
    real = client.copy_app

    def forever(app_token, name, without_content=False, folder_token=None):
        app = real(app_token, name, without_content, folder_token)
        w.copying[app.app_token] = 99
        return app

    client.copy_app = forever
    log = schema_apply(plan, client=client, read_client=w, settle_attempts=3,
                       sleep=NoSleep())

    entry = log.entries[0]
    assert entry.outcome == "applied-unverified"
    assert entry.refusal.reason == SETTLE_NOT_COMPLETE
    assert entry.created_app_token, "the copy IS on the tenant and the log names it"
    assert entry.settle["attempts"] == 3 and entry.settle["status"] == "not-settled"
    assert entry.is_applied is True


def test_the_plan_DISCLOSES_that_the_copy_is_asynchronous_BEFORE_anything_is_sent():
    plan = schema_dry_run([copy_base("appOLD", "c", folder_token="fldrXYZ"), create_table("appOLD", "t", primary_field_name="Title")])
    blob = json.loads(plan.to_json())
    assert blob["async_settle"] == ASYNC_SETTLE_CONTRACT
    assert [e["asynchronous"] for e in blob["entries"]] == [True, False]
    assert blob["read_calls"] == 4, (
        "the copy costs one settle probe more than a sync op — and LD-322's create names its "
        "primary column, so it is a kitted create and carries the field listing that verifies "
        "the column landed")


def test_a_SCHEMA_ONLY_copy_is_expressible_and_travels_to_the_client():
    _plan, log, _w, client = run([copy_base("appOLD", "c", without_content=True, folder_token="fldrXYZ")])
    assert client.calls[0] == ("copy_app", "appOLD", "c", True, "fldrXYZ")
    assert log.entries[0].outcome == "applied"


def test_a_copy_can_be_PLACED_IN_A_FOLDER_and_the_key_TRAVELS_THE_WHOLE_WAY():
    """LD-387. The plan carries it, the engine forwards it, the client receives it.

    TRANSFORMED: the parameter-free copy used to be byte-identical to what this engine had
    always issued, so an existing caller saw nothing move. That copy went to the application's
    own space — which nothing human can browse — so the destination is now required, and the
    no-destination case is asserted below as a **plan-time refusal costing zero calls** rather
    than as a body shape.
    """
    plan = schema_dry_run([copy_base("appOLD", "c", folder_token="fldrXYZ")])
    assert plan.entries[0].fields["folder_token"] == "fldrXYZ"

    from larkdocio.errors import MissingDestinationError

    _p, log, _w, client = run([copy_base("appOLD", "c", folder_token="fldrXYZ")])
    assert client.calls[0] == ("copy_app", "appOLD", "c", False, "fldrXYZ")
    assert log.entries[0].outcome == "applied"

    for spelling in (None, "", "   "):
        with pytest.raises(MissingDestinationError):
            copy_base("appOLD", "c", folder_token=spelling)
        with pytest.raises(MissingDestinationError):
            create_base("c", spelling)


# --------------------------------------------------------------------------- #
# The log is LD-259's, and it is 1:1 with the plan on every run                 #
# --------------------------------------------------------------------------- #

def test_the_log_is_LD259s_APPLY_LOG_and_one_entry_per_plan_entry_IN_PLAN_ORDER():
    plan, log, _w, _c = run([create_base("a", "fldrXYZ"), create_table("appOLD", "t", primary_field_name="Title"),
                             rename_table("appOLD", "tbl1", "u")])
    assert isinstance(log, ApplyLog)
    assert len(log.entries) == len(plan.entries)
    assert [e.op for e in log.entries] == [e.op for e in plan.entries]
    assert all(e.record_id is None for e in log.entries), (
        "a schema op has no row; inventing a record id would be a lie that survives the log")


def test_a_SYSTEMIC_failure_HALTS_and_every_remaining_entry_is_NOT_ATTEMPTED():
    from larkdocio.errors import LarkPermissionError

    denial = LarkPermissionError("denied", code=99991672, msg="scope required")
    _plan, log, _w, _c = run([create_table("appOLD", "a", primary_field_name="Title"), create_table("appOLD", "b", primary_field_name="Title"),
                              create_table("appOLD", "c", primary_field_name="Title")],
                             raises={"create_table": denial})
    assert log.halted
    assert log.entries[0].refusal.reason == Refusal.PERMISSION_DENIED
    assert [e.outcome for e in log.entries[1:]] == ["not-attempted", "not-attempted"]
    assert log.halt["not_attempted"] == 2


def test_the_log_is_JSON_SERIALISABLE_end_to_end():
    _plan, log, _w, _c = run([create_base("a", "fldrXYZ"), copy_base("appOLD", "b", folder_token="fldrXYZ")])
    blob = json.loads(log.to_json())
    assert len(blob["entries"]) == 2
    assert blob["entries"][0]["created_app_token"]
    assert blob["entries"][1]["settle"]["asynchronous"] is True


def test_a_CREATE_names_the_APP_TOKEN_it_made_which_is_how_a_caller_finds_it_again():
    _plan, log, w, _c = run([create_base("larkdocio-DISPOSABLE-y", "fldrXYZ")])
    token = log.entries[0].created_app_token
    assert token and w.apps[token] == "larkdocio-DISPOSABLE-y"
