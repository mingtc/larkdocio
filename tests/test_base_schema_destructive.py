"""LD-265 — the DESTRUCTIVE schema ops, their CROSS-TABLE loss preview and the consent fence.

The rung's dangerous story. The invariant under test is the Sheets structural rung's, widened:
**a destructive write whose loss cannot be enumerated REFUSES**, and on a Base "the loss" is
**app-scoped** — a ``DuplexLink`` delete takes the mirror column in ANOTHER table, and a table
delete leaves every inbound link in every other table dangling with no error anywhere.

Every world here is a :mod:`base_destructive_fakes` ``ScanWorld``: the test owns the tenant, so
a preview that names a column in another table is naming a column the test put there.
"""
import pytest

from base_destructive_fakes import (
    FakeField,
    FakeRecord,
    ScanWorld,
    ScriptedDestructiveClient,
    link_field,
    lookup_rollup_world,
    two_table_link_world,
)

from log_reading_apply import reading_the_log
from larkdocio.base import loss_preview as lp
from larkdocio.base import schema_ops
from larkdocio.base import schema_ops_destructive as destructive
from larkdocio.base.plan import Refusal
from larkdocio.base.schema_apply import (
    DestructiveConsentRequired,
    consent_to_destroy,
    schema_apply,
    schema_dry_run,
)
schema_apply = reading_the_log(schema_apply)
from larkdocio.base.schema_plan import SchemaPlan
from larkdocio.errors import LarkAPIError

from guard_kit import REPO_ROOT


# --------------------------------------------------------------------------- #
# AC1 — the three ops ship BEHIND THE PLAN GATE and the consent fence          #
# --------------------------------------------------------------------------- #

def test_AC1_the_THREE_destructive_ops_are_registered_and_declare_that_they_MUTATE():
    names = [d.name for d in destructive.SCHEMA_OP_FAMILY.ops]
    assert names == ["delete_field", "delete_table", "batch_delete_tables"]
    assert all(d.mutates is True for d in destructive.SCHEMA_OP_FAMILY.ops)
    assert destructive.__name__ in schema_ops.FAMILY_MODULES
    registered = {d.name for d in schema_ops.schema_ops()}
    assert set(names) <= registered, "the aggregator must carry this family's descriptors"


def test_AC1_the_READ_registry_still_answers_read_only_TRUE_and_the_schema_table_all_mutate():
    from larkdocio.base import ops as base_ops

    assert base_ops.read_only() is True
    assert schema_ops.all_mutate() is True


def test_AC1_the_three_endpoints_and_verbs_are_the_SDKs_OWN():
    seen = {d.name: (d.endpoint, d.http_method) for d in destructive.SCHEMA_OP_FAMILY.ops}
    assert seen == {
        "delete_field": (
            "/open-apis/bitable/v1/apps/:app_token/tables/:table_id/fields/:field_id",
            "DELETE"),
        "delete_table": ("/open-apis/bitable/v1/apps/:app_token/tables/:table_id", "DELETE"),
        "batch_delete_tables": (
            "/open-apis/bitable/v1/apps/:app_token/tables/batch_delete", "POST"),
    }
    for descriptor in destructive.SCHEMA_OP_FAMILY.ops:
        built = descriptor.request_cls.builder().build()
        assert descriptor.endpoint == built.uri
        assert descriptor.http_method == built.http_method.name


def test_AC1_every_destructive_op_IS_DECLARED_DESTRUCTIVE_to_the_aggregator():
    assert schema_ops.destructive_ops() == frozenset(
        {"delete_field", "delete_table", "batch_delete_tables"})


def test_AC1_a_DESTRUCTIVE_PLAN_CANNOT_BE_APPLIED_WITHOUT_CONSENT():
    world = two_table_link_world()
    plan = schema_dry_run([destructive.delete_table("app", "tblThird")], read_client=world)
    assert plan.destructive is True
    with pytest.raises(DestructiveConsentRequired) as caught:
        schema_apply(plan, client=object(), read_client=world)
    assert "consent" in str(caught.value).lower()


def test_AC1_a_CONSENT_MINTED_FOR_ANOTHER_PLAN_IS_REFUSED():
    world = two_table_link_world()
    one = schema_dry_run([destructive.delete_table("app", "tblThird")], read_client=world)
    other = schema_dry_run([destructive.delete_table("app", "tblThird")], read_client=world)
    with pytest.raises(DestructiveConsentRequired):
        schema_apply(one, client=object(), read_client=world,
                     consent=consent_to_destroy(other))


def test_AC1_A_HAND_BUILT_LOOK_ALIKE_CONSENT_IS_REJECTED():
    """The fence is not a boolean a caller can pass by accident."""
    world = two_table_link_world()
    plan = schema_dry_run([destructive.delete_table("app", "tblThird")], read_client=world)

    look_alike = type("LookAlike", (), {"plan": plan, "losses": plan.loss_previews})()

    with pytest.raises(DestructiveConsentRequired):
        schema_apply(plan, client=object(), read_client=world, consent=look_alike)
    with pytest.raises(DestructiveConsentRequired):
        schema_apply(plan, client=object(), read_client=world, consent=True)


def test_AC1_A_HAND_BUILT_LOOK_ALIKE_PLAN_IS_REJECTED():
    class LookAlikePlan:
        entries = ()
        destructive = True

    with pytest.raises(TypeError):
        schema_apply(LookAlikePlan(), client=object(), read_client=object())
    with pytest.raises(TypeError):
        SchemaPlan(entries=())


def test_AC1_a_NON_destructive_plan_is_UNCHANGED_no_consent_and_no_read_client_needed():
    """The fence must not tax the landed ops: a rename still plans with zero API calls."""
    from larkdocio.base.schema_plan import rename_table

    plan = schema_dry_run([rename_table("app", "tbl", "new")])
    assert plan.destructive is False
    assert plan.loss_previews == ()


# --------------------------------------------------------------------------- #
# AC2 — THE LOSS PREVIEW IS APP-SCOPED. The story's reason to exist.           #
# --------------------------------------------------------------------------- #

def test_AC2i_a_DUPLEX_field_delete_names_BOTH_COLUMNS_BOTH_TABLES_and_BOTH_CELL_COUNTS():
    world = two_table_link_world()
    plan = schema_dry_run([destructive.delete_field("app", "tblMain", "fldDuplex")],
                          read_client=world)
    loss = plan.entries[0].loss_preview

    columns = loss["columns"]
    assert [c["table_id"] for c in columns] == ["tblMain", "tblRef"], (
        "the mirror lives in ANOTHER TABLE and the preview names it")
    assert [c["table_name"] for c in columns] == ["Main", "Ref"]
    assert [c["field_name"] for c in columns] == ["DLink", "Main-DLink"]
    # Both cell counts, read from the records the test put there: 2 of 3 rows in Main hold a
    # DLink cell, 1 of 2 in Ref holds the mirror.
    assert [c["cells_with_data"] for c in columns] == [2, 1]
    assert loss["other_tables"] == ["tblRef"]
    assert loss["mirror"]["located_by"] in ("back_field_id", "back_field_name")


def test_AC2i_the_SYMMETRIC_delete_of_the_MIRROR_names_the_SOURCE_column():
    world = two_table_link_world()
    plan = schema_dry_run([destructive.delete_field("app", "tblRef", "fldMirror")],
                          read_client=world)
    columns = plan.entries[0].loss_preview["columns"]
    assert [(c["table_id"], c["field_name"]) for c in columns] == [
        ("tblRef", "Main-DLink"), ("tblMain", "DLink")]


def test_AC2ii_a_TABLE_delete_enumerates_EVERY_INBOUND_LINK_IN_EVERY_OTHER_TABLE():
    world = two_table_link_world()
    plan = schema_dry_run([destructive.delete_table("app", "tblRef")], read_client=world)
    loss = plan.entries[0].loss_preview

    inbound = {(row["table_id"], row["field_name"]) for row in loss["inbound_links"]}
    assert inbound == {("tblMain", "SLink"), ("tblMain", "DLink"),
                       ("tblThird", "RefLink")}, (
        "every referencing field in every OTHER table — including the third table, which the "
        "caller never named")
    assert sorted(loss["other_tables"]) == ["tblMain", "tblThird"]
    for row in loss["inbound_links"]:
        assert row["effect"], "each inbound link states what happens to it"
    assert "silently" in loss["what"].lower()


def test_LD480_the_ENUMERATED_SET_is_UNCHANGED_and_only_the_DUPLEX_SENTENCE_MOVED():
    """LD-480 AC4, pinned so the answer cannot quietly become the other one.

    Re-measuring the table-delete route per link kind changed **what an inbound two-way column is
    told**, not **which columns are enumerated**: the loop at
    ``src/larkdocio/base/loss_preview.py:704-706`` enumerates on ``spec.is_link``, so a duplex and
    a single are both already in the set and only the ``effect`` string differs. A change to the
    enumerated SET would be consumer-visible behavior and would need its own consent note; this
    test is what would redden if one were ever made by accident.
    """
    world = two_table_link_world()
    loss = schema_dry_run([destructive.delete_table("app", "tblRef")],
                          read_client=world).entries[0].loss_preview
    by_name = {row["field_name"]: row for row in loss["inbound_links"]}
    # BOTH kinds enumerated — the set, unchanged.
    assert {"SLink", "DLink", "RefLink"} <= set(by_name)
    # Only the SENTENCE splits them.
    assert by_name["DLink"]["effect"] == lp.INBOUND_DUPLEX_IS_LOST_EITHER_WAY
    assert by_name["SLink"]["effect"] == lp.INBOUND_LINK_DANGLES_SILENTLY
    assert by_name["DLink"]["effect"] != by_name["SLink"]["effect"]
    # And the duplex sentence now states the measured outcome instead of hedging between two.
    duplex = lp.INBOUND_DUPLEX_IS_LOST_EITHER_WAY
    assert "does not survive" in duplex
    assert "NOT measured" not in duplex, (
        "the table-delete route HAS been measured for a two-way inbound link (LD-480); the hedge "
        "may not come back without a measurement retracting it")


def test_LD480_ONE_PAYLOAD_does_not_tell_a_caller_TWO_THINGS_about_the_SAME_column():
    """**The defect this pins is self-contradiction inside a single returned dict.**

    A table-delete preview's ``what`` is the headline a caller reads first, and its
    ``inbound_links[].effect`` is the per-column detail. Before this, the headline said every
    inbound link *survives with the dead table's id* while the very same payload told the duplex
    column beside it that it *does not survive at all*. Both cannot be true of one column, and a
    caller reading top-down met the wrong one.

    So the headline is held to the per-kind split its own rows carry: it must name **both**
    outcomes and may not assert the surviving-and-dangling one of *every* link.
    """
    world = two_table_link_world()
    loss = schema_dry_run([destructive.delete_table("app", "tblRef")],
                          read_client=world).entries[0].loss_preview
    what = loss["what"]
    lowered = what.lower()
    assert "one-way" in lowered and "two-way" in lowered, what
    assert "does not survive" in lowered or "not survive at all" in lowered, what
    assert "silent" in lowered, "the whole point is that nothing reports it"

    # The headline may not contradict the row beside it: no universal dangling claim.
    assert "leaves every link column" not in lowered, what
    duplex_row = next(row for row in loss["inbound_links"] if row["field_name"] == "DLink")
    assert "does not survive at all" in duplex_row["effect"]
    # …and the two agree on the same word for the same outcome.
    assert "survives" in lowered and "goes with it" in lowered, what


def test_AC2iii_a_PLAIN_field_delete_carries_ITS_CELL_COUNT_and_names_ONE_column():
    world = two_table_link_world()
    plan = schema_dry_run([destructive.delete_field("app", "tblMain", "fldText")],
                          read_client=world)
    loss = plan.entries[0].loss_preview
    assert len(loss["columns"]) == 1
    assert loss["columns"][0]["cells_with_data"] == 2       # rec1 and rec2 carry Notes
    assert loss["other_tables"] == []
    assert loss["mirror"] is None
    assert "no API undo" in loss["what"]


def test_AC2_a_batch_delete_enumerates_EVERY_TABLES_loss_and_the_links_into_all_of_them():
    world = two_table_link_world()
    plan = schema_dry_run(
        [destructive.batch_delete_tables("app", ["tblRef", "tblThird"])], read_client=world)
    loss = plan.entries[0].loss_preview
    assert [t["table_id"] for t in loss["tables"]] == ["tblRef", "tblThird"]
    inbound = {(row["table_id"], row["field_name"]) for row in loss["inbound_links"]}
    assert inbound == {("tblMain", "SLink"), ("tblMain", "DLink")}, (
        "tblThird's own inbound link into tblRef is not reported: tblThird is itself being "
        "deleted, so it is loss, not a survivor left dangling")


def test_AC2_an_ALREADY_DANGLING_link_is_reported_as_such_rather_than_as_a_fresh_loss():
    world = two_table_link_world(dangling=True)
    plan = schema_dry_run([destructive.delete_field("app", "tblMain", "fldDuplex")],
                          read_client=world)
    loss = plan.entries[0].loss_preview
    assert loss["mirror"]["already_gone"] is True
    assert len(loss["columns"]) == 1, "there is no second column left to lose"


# --------------------------------------------------------------------------- #
# AC3 — A LOSS THAT CANNOT BE ENUMERATED REFUSES. NO EXCEPTIONS.               #
# --------------------------------------------------------------------------- #

def _refusal_of(plan):
    entry = plan.entries[0]
    assert entry.refusal is not None, "this entry should have refused at plan time"
    return entry.refusal


def test_AC3_a_TRUNCATED_TABLE_LIST_REFUSES_with_zero_writes():
    world = two_table_link_world()
    world.truncate.add("tables")
    plan = schema_dry_run([destructive.delete_table("app", "tblRef")], read_client=world)
    refusal = _refusal_of(plan)
    assert refusal.reason == Refusal.LOSS_NOT_ENUMERABLE
    assert "exhaust" in refusal.detail.lower()
    assert plan.api_call_count == 0, "a refused entry issues no write"


def test_AC3_a_TRUNCATED_FIELD_READ_of_ANOTHER_TABLE_REFUSES():
    """The scan reads every table, so an unreadable *other* table is an unknowable blast
    radius even though the named table read fine."""
    world = two_table_link_world()
    world.truncate.add("fields:tblThird")
    plan = schema_dry_run([destructive.delete_table("app", "tblRef")], read_client=world)
    assert _refusal_of(plan).reason == Refusal.LOSS_NOT_ENUMERABLE


def test_AC3_a_FIELD_READ_THAT_ERRORS_REFUSES_naming_the_table():
    world = two_table_link_world()
    world.raises["fields:tblThird"] = LarkAPIError("no", code=1254041, msg="TableIdNotFound")
    plan = schema_dry_run([destructive.delete_table("app", "tblRef")], read_client=world)
    refusal = _refusal_of(plan)
    assert refusal.reason == Refusal.LOSS_NOT_ENUMERABLE
    assert "tblThird" in refusal.detail


def test_AC3_a_READ_CLIENT_THAT_CANNOT_PROVE_ITS_PAGING_REFUSES():
    """Absent proof is not proof. A read seam that publishes no paging record cannot be shown
    to have reached the end of the table list, so the destructive op refuses."""
    world = two_table_link_world()
    world.no_proof = True
    plan = schema_dry_run([destructive.delete_table("app", "tblRef")], read_client=world)
    assert _refusal_of(plan).reason == Refusal.LOSS_NOT_ENUMERABLE


def test_AC3_NO_READ_CLIENT_AT_ALL_REFUSES_rather_than_planning_a_blind_delete():
    plan = schema_dry_run([destructive.delete_table("app", "tblRef")])
    refusal = _refusal_of(plan)
    assert refusal.reason == Refusal.LOSS_NOT_ENUMERABLE
    assert "read client" in refusal.detail.lower()


def test_AC3_A_REFUSED_DESTRUCTIVE_ENTRY_CANNOT_BE_CONSENTED_TO():
    """Consent is over an enumerated loss. A plan whose destructive entry refused has none."""
    world = two_table_link_world()
    world.truncate.add("tables")
    plan = schema_dry_run([destructive.delete_table("app", "tblRef")], read_client=world)
    with pytest.raises(DestructiveConsentRequired):
        consent_to_destroy(plan)


def test_AC3_the_refusal_is_the_LD_150_INVARIANT_WIDENED_and_says_so_in_the_shipped_text():
    assert "cannot be enumerated" in lp.LOSS_MUST_BE_ENUMERABLE
    assert "whole app" in lp.LOSS_MUST_BE_ENUMERABLE
    assert "under-report" in lp.LOSS_MUST_BE_ENUMERABLE.lower()


def test_AC3_the_scan_REFUSES_a_table_the_credential_cannot_see():
    world = ScanWorld({"tblA": {"name": "A", "fields": [FakeField("f", "F")]}})
    world.raises["fields:tblA"] = LarkAPIError("denied", code=99991672, msg="Access denied")
    with pytest.raises(lp.LossNotEnumerable):
        lp.scan_app(world, "app")


# --------------------------------------------------------------------------- #
# AC4 — THE PREVIEW'S COST IS DISCLOSED                                        #
# --------------------------------------------------------------------------- #

def test_AC4_the_plan_states_HOW_MANY_READ_CALLS_the_preview_made_and_WHICH_TABLES():
    world = two_table_link_world()
    plan = schema_dry_run([destructive.delete_table("app", "tblRef")], read_client=world)
    cost = plan.to_dict()["loss_preview_cost"]

    assert cost["read_calls"] == len(world.calls), (
        "the disclosed number is the number of reads that really happened")
    assert cost["tables_inspected"] == ["tblMain", "tblRef", "tblThird"]
    assert cost["read_calls"] >= 4       # the table list + one field read per table
    assert cost["what"]


def test_AC4_the_scan_is_made_ONCE_per_plan_however_many_destructive_entries_ride_it():
    world = two_table_link_world()
    schema_dry_run([destructive.delete_field("app", "tblMain", "fldText"),
                    destructive.delete_table("app", "tblThird")], read_client=world)
    assert world.calls.count("tables") == 1, (
        "one scan per plan — the within-story call AC4 leaves to Dev, disclosed either way")


def test_AC4_a_preview_run_TWICE_is_BYTE_IDENTICAL_in_structure():
    first = schema_dry_run([destructive.delete_table("app", "tblRef")],
                           read_client=two_table_link_world()).to_json(sort_keys=True)
    second = schema_dry_run([destructive.delete_table("app", "tblRef")],
                            read_client=two_table_link_world()).to_json(sort_keys=True)
    assert first == second


# --------------------------------------------------------------------------- #
# AC5 — DELETE IS TRASH, NOT PURGE, and the surface SAYS SO                    #
# --------------------------------------------------------------------------- #

def test_AC5_the_shipped_wording_says_TRASH_and_RECOVERABLE_BY_A_HUMAN():
    text = lp.TRASH_NOT_PURGE.lower()
    assert "trash" in text
    assert "restore" in text and "human" in text
    assert "no open-api verb that purges" in text


def test_AC5_no_shipped_sentence_on_this_rung_implies_PERMANENT_ERASURE():
    """A content test over the modules this story ships. `erase` may appear only inside a
    sentence that DENIES it — never as a claim about what a delete does."""
    import pathlib

    denials = ("not erased", "is a permanent erasure", "implies erasure", "never")
    for module in (lp, destructive):
        text = pathlib.Path(module.__file__).read_text(encoding="utf-8")
        for line in text.splitlines():
            lowered = line.lower()
            if "eras" not in lowered:
                continue
            assert any(denial in lowered for denial in denials), line


def test_AC5_the_preview_CARRIES_the_trash_sentence_on_every_destructive_branch():
    world = two_table_link_world()
    plan = schema_dry_run([destructive.delete_field("app", "tblMain", "fldText"),
                           destructive.delete_table("app", "tblThird")], read_client=world)
    assert [entry.loss_preview["trash"] for entry in plan.entries] == [
        lp.TRASH_NOT_PURGE, lp.TRASH_NOT_PURGE]


def test_AC5_no_PURGE_VERB_is_shipped_anywhere_on_this_family():
    """**Still true after LD-466, and for the reason it was always true.**

    The recorded reason — *"Lark's route trashes rather than purges, so nothing here offers
    one"* — is re-confirmed by measurement, not waived: after a landed
    ``DELETE …/files/{a}?type=bitable``, ``POST /drive/v1/metas/batch_query`` still resolves the
    Base's title and timestamps (``tests/captures/ld466-delete-base/captures/ld466-07-*.json``). So **no
    purge verb exists to ship**, and the ``delete_base`` LD-466 does ship is a **trash**.

    The second assertion keeps its exact form, and it now says something different and sharper:
    the whole-object delete is not a member of *this family* — a schema op with a bitable
    endpoint, a plan-time loss preview and a consent fence. It is a lifecycle call
    (``schema_client.LIFECYCLE_OPS``), which is why appending it here would claim a plan and a
    preview it does not have.
    """
    from larkdocio.base.schema_client import LIFECYCLE_OPS

    names = {d.name for d in destructive.SCHEMA_OP_FAMILY.ops}
    assert not any("purge" in name for name in names)
    assert "delete_app" not in names and "delete_base" not in names
    assert "delete_base" in LIFECYCLE_OPS, (
        "the verb is absent from this family BECAUSE it is declared elsewhere — if it were "
        "absent from both, this assertion would be guarding a capability that vanished")


# --------------------------------------------------------------------------- #
# AC6 — the PROTECTED-LAST codes, typed and ENTRY-SCOPED                       #
# --------------------------------------------------------------------------- #

def test_AC6_the_last_table_message_says_WHAT_TO_DO():
    assert "1254034" in destructive.LAST_TABLE_IS_PROTECTED
    assert "last table cannot be deleted" in destructive.LAST_TABLE_IS_PROTECTED
    assert "every other entry in the plan is judged on its own" in \
        destructive.LAST_TABLE_IS_PROTECTED.lower()


def test_LD466_the_last_table_message_POINTS_AT_A_DOOR_THAT_EXISTS():
    """The whole reason LD-466 was filed, pinned as text.

    This refusal is the **only** exit a caller has from a one-table Base — measured live at
    ``403 1254034`` (``dev/ld466-delete-base/captures/ld466-03-last-table-refusal.json``) — and
    it used to end *"Delete the Base itself if that is what you meant — which this library does
    not offer as an operation"*. It named the way out and then said the way out did not exist.
    It now names a verb that resolves, and what that verb does.
    """
    from larkdocio.base.schema_client import BaseSchemaClient

    message = destructive.LAST_TABLE_IS_PROTECTED
    assert "delete_base" in message
    assert callable(getattr(BaseSchemaClient, "delete_base")), (
        "the message names an attribute — this resolves it, so the text cannot outlive the verb")
    assert "does not offer" not in message
    lowered = message.lower()
    assert "trash" in lowered, "naming a destructive verb without its semantics is a half-answer"
    assert "whole base" in lowered or "the whole Base" in message
    assert "write credentials" in lowered or "write pair" in lowered


def test_AC6_the_last_VIEW_message_is_LD_264s_REUSED_NOT_REDEFINED():
    from larkdocio.base import schema_ops_views

    import pathlib

    assert destructive.LAST_TABLE_IS_PROTECTED != schema_ops_views.LAST_VIEW_IS_PROTECTED
    assert "1254023" in schema_ops_views.LAST_VIEW_IS_PROTECTED
    # This story ships NO second sentence about the last view: the destructive family never
    # writes that code, and the disposition table reaches the view family's own wording by
    # name rather than copying it.
    assert "1254023" not in pathlib.Path(destructive.__file__).read_text(encoding="utf-8")
    from larkdocio.base.disposition import protected_last_advice
    assert protected_last_advice(1254023) is schema_ops_views.LAST_VIEW_IS_PROTECTED
    assert protected_last_advice(1254034) is destructive.LAST_TABLE_IS_PROTECTED


@pytest.mark.parametrize("code", [1254034, 1254023])
def test_AC6_both_protected_last_codes_are_ENTRY_SCOPED_and_the_batch_CONTINUES(code):
    from larkdocio.base.disposition import ENTRY_SCOPED, classify_apply_exception

    disposition = classify_apply_exception(
        LarkAPIError("protected", code=code, msg="protected"), wrote=False)
    assert disposition.scope == ENTRY_SCOPED
    assert disposition.continues is True
    assert disposition.landed == "no"


@pytest.mark.parametrize("code", [1254034, 1254023])
def test_AC6_the_refusal_DETAIL_says_what_to_do(code):
    from larkdocio.base.disposition import classify_apply_exception, disposition_refusal

    exc = LarkAPIError("protected", code=code, msg="protected")
    refusal = disposition_refusal(classify_apply_exception(exc, wrote=False), exc,
                                  where="the delete")
    assert "Create a view first" in refusal.detail or "leave this table" in refusal.detail


# --------------------------------------------------------------------------- #
# AC7 — the DISPOSITION doctrine, one test per ruled row                       #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("code,scope,outcome,landed", [
    (1254023, "entry-scoped", "refused", "no"),
    (1254034, "entry-scoped", "refused", "no"),
    (1254041, "systemic", "refused", "no"),
    (1254004, "systemic", "refused", "no"),
    (1002, "systemic", "refused", "no"),
])
def test_AC7_the_ruled_classification_table_row_by_row(code, scope, outcome, landed):
    from larkdocio.base.disposition import classify_apply_exception

    disposition = classify_apply_exception(
        LarkAPIError("answer", code=code, msg="answer"), wrote=False)
    assert (disposition.scope, disposition.outcome, disposition.landed) == \
        (scope, outcome, landed)


def test_AC7_a_SCOPE_DENIAL_is_SYSTEMIC_and_HALTS_LD_206_inherited_verbatim():
    from larkdocio.base.disposition import SYSTEMIC, classify_apply_exception
    from larkdocio.errors import LarkPermissionError

    disposition = classify_apply_exception(
        LarkPermissionError("denied", code=99991672, msg="Access denied"), wrote=False)
    assert disposition.scope == SYSTEMIC and disposition.halts is True
    assert disposition.landed == "no"


def test_AC7_a_PROTECTED_LAST_TABLE_refusal_lets_the_REST_OF_THE_BATCH_RUN():
    """The scope claim, exercised through the engine rather than asserted about a table."""
    world = two_table_link_world()
    client = ScriptedDestructiveClient(world, raises={
        "delete_table": LarkAPIError("last", code=1254034,
                                     msg="The last table cannot be deleted.")})
    plan = schema_dry_run([destructive.delete_table("app", "tblRef"),
                           destructive.delete_field("app", "tblMain", "fldText")],
                          read_client=world)
    log = schema_apply(plan, client=client, read_client=world,
                       consent=consent_to_destroy(plan))
    assert log.entries[0].outcome == "refused"
    assert log.entries[0].refusal.reason == Refusal.API_ERROR
    assert log.entries[1].outcome == "applied", "the batch CONTINUED past an entry-scoped code"
    assert log.halt is None


def test_AC7_a_TABLE_ID_NOT_FOUND_HALTS_and_the_remainder_is_NOT_ATTEMPTED():
    world = two_table_link_world()
    client = ScriptedDestructiveClient(world, raises={
        "delete_table": LarkAPIError("gone", code=1254041, msg="TableIdNotFound")})
    plan = schema_dry_run([destructive.delete_table("app", "tblRef"),
                           destructive.delete_field("app", "tblMain", "fldText")],
                          read_client=world)
    log = schema_apply(plan, client=client, read_client=world,
                       consent=consent_to_destroy(plan))
    assert log.entries[0].outcome == "refused"
    assert log.entries[1].outcome == "not-attempted"
    assert log.halt is not None


def test_AC7_STALE_BASE_halts_THAT_TABLES_entry_and_leaves_the_OTHERS_judged_on_their_own():
    """D4′'s per-table refinement: a field delete planned against a stale anchor refuses with
    ZERO writes, and an entry against another table still runs."""
    world = two_table_link_world()
    client = ScriptedDestructiveClient(world)
    plan = schema_dry_run(
        [destructive.delete_field("app", "tblMain", "fldText", revision=99),
         destructive.delete_table("app", "tblThird")], read_client=world)
    log = schema_apply(plan, client=client, read_client=world,
                       consent=consent_to_destroy(plan))
    assert log.entries[0].refusal.reason == Refusal.STALE_BASE
    assert ("delete_field",) not in {(call[0],) for call in client.calls}, "ZERO writes"
    assert log.entries[1].outcome == "applied"
    assert log.halt is None


# --------------------------------------------------------------------------- #
# AC8 — the apply-log is 1:1 with the plan, including over a refusal           #
# --------------------------------------------------------------------------- #

def test_AC8_the_log_is_ONE_ENTRY_PER_PLAN_ENTRY_in_plan_order_including_a_LOSS_REFUSAL():
    world = two_table_link_world()
    world.truncate.add("fields:tblThird")           # every destructive entry will refuse
    plan = schema_dry_run([destructive.delete_table("app", "tblRef"),
                           destructive.delete_field("app", "tblMain", "fldText")],
                          read_client=world)
    client = ScriptedDestructiveClient(world)
    log = schema_apply(plan, client=client, read_client=world)

    assert len(log.entries) == len(plan.entries) == 2
    assert [entry.op for entry in log.entries] == [e.op for e in plan.entries]
    assert all(entry.refusal.reason == Refusal.LOSS_NOT_ENUMERABLE for entry in log.entries)
    assert client.calls == [], "a refused destructive entry sends NOTHING"


def test_AC8_a_wholly_refused_destructive_plan_needs_NO_CONSENT_because_it_destroys_nothing():
    """The fence is over what will be *applied*. A plan whose destructive entries all refused
    carries no reachable delete, so it may be handed to apply() to be logged."""
    world = two_table_link_world()
    world.truncate.add("tables")
    plan = schema_dry_run([destructive.delete_table("app", "tblRef")], read_client=world)
    log = schema_apply(plan, client=ScriptedDestructiveClient(world), read_client=world)
    assert log.entries[0].outcome == "refused"


def test_AC8_the_log_entry_carries_THIS_OPS_OWN_disclosure_not_the_family_default():
    from larkdocio.base.field_authoring import FIELD_OPS_RIDE_TABLE_REVISION
    from larkdocio.base.schema_plan import NO_APP_REVISION_CAS, disclosure_for_op

    assert disclosure_for_op("delete_field") == FIELD_OPS_RIDE_TABLE_REVISION
    assert disclosure_for_op("delete_table") == NO_APP_REVISION_CAS
    assert disclosure_for_op("batch_delete_tables") == NO_APP_REVISION_CAS


# --------------------------------------------------------------------------- #
# AC9 — R12 + THE WRITE-EFFECT ORACLE ON DELETES                               #
# --------------------------------------------------------------------------- #

def test_AC9_a_field_delete_is_APPLIED_only_when_the_column_is_GONE_and_the_ANCHOR_MOVED():
    world = two_table_link_world()
    client = ScriptedDestructiveClient(world)
    plan = schema_dry_run([destructive.delete_field("app", "tblMain", "fldText", revision=12)],
                          read_client=world)
    log = schema_apply(plan, client=client, read_client=world,
                       consent=consent_to_destroy(plan))
    entry = log.entries[0]
    assert entry.outcome == "applied"
    assert entry.read_back["gone"] is True
    assert entry.read_back["revision_moved"] == 1, "table.revision moves +1 per field op"


def test_AC9_a_code_0_DELETE_WHOSE_ANCHOR_DID_NOT_MOVE_is_NEVER_applied():
    """The oracle, on a delete: the column vanished from the listing but the anchor stood
    still, so the server registered no operation and the engine says so."""
    world = two_table_link_world()
    client = ScriptedDestructiveClient(world, frozen_revision=True)
    plan = schema_dry_run([destructive.delete_field("app", "tblMain", "fldText", revision=12)],
                          read_client=world)
    log = schema_apply(plan, client=client, read_client=world,
                       consent=consent_to_destroy(plan))
    entry = log.entries[0]
    assert entry.outcome != "applied"
    assert entry.refusal.reason == Refusal.WRITE_NOT_OBSERVED


def test_AC9_a_DEAF_delete_that_answered_code_0_and_changed_nothing_is_reported_DROPPED():
    world = two_table_link_world()
    client = ScriptedDestructiveClient(world, deaf=["delete_table"])
    plan = schema_dry_run([destructive.delete_table("app", "tblThird")], read_client=world)
    log = schema_apply(plan, client=client, read_client=world,
                       consent=consent_to_destroy(plan))
    assert log.entries[0].outcome == "dropped"
    assert log.entries[0].refusal.reason == Refusal.WRITE_NOT_OBSERVED


def test_AC9_an_APP_SCOPED_delete_is_verified_by_the_OBJECT_GONE_ORACLE():
    world = two_table_link_world()
    client = ScriptedDestructiveClient(world)
    plan = schema_dry_run([destructive.delete_table("app", "tblThird")], read_client=world)
    log = schema_apply(plan, client=client, read_client=world,
                       consent=consent_to_destroy(plan))
    read_back = log.entries[0].read_back
    assert log.entries[0].outcome == "applied"
    assert read_back["object_gone"] is True
    assert read_back["gone_codes"] == [1254041, 1002, 91402]


def test_AC9_the_DUPLEX_delete_is_verified_IN_THE_OTHER_TABLE_TOO():
    """The story's whole subject, asserted on the verification rather than only the preview."""
    world = two_table_link_world()
    client = ScriptedDestructiveClient(world)
    plan = schema_dry_run(
        [destructive.delete_field("app", "tblMain", "fldDuplex", revision=12)],
        read_client=world)
    log = schema_apply(plan, client=client, read_client=world,
                       consent=consent_to_destroy(plan))
    entry = log.entries[0]
    assert entry.outcome == "applied"
    assert entry.read_back["mirror_field_id"] == "fldMirror"
    assert entry.read_back["mirror_gone"] is True
    assert "fldMirror" not in {f.field_id for f in world.tables["tblRef"]["fields"]}


def test_AC9_a_batch_delete_is_verified_in_ONE_read_back_over_EVERY_id():
    world = two_table_link_world()
    client = ScriptedDestructiveClient(world)
    plan = schema_dry_run(
        [destructive.batch_delete_tables("app", ["tblRef", "tblThird"])], read_client=world)
    log = schema_apply(plan, client=client, read_client=world,
                       consent=consent_to_destroy(plan))
    assert log.entries[0].outcome == "applied"
    assert log.entries[0].read_back["read_backs"] == 1
    assert log.entries[0].read_back["still_listed"] == []


def test_AC9_EVERY_PARAMETER_SENT_differs_from_the_parameter_free_control():
    """R12: a parameter this client sends is a parameter a test proved changed the request."""
    from lark_oapi.api.bitable.v1 import (
        BatchDeleteAppTableRequest,
        DeleteAppTableFieldRequest,
        DeleteAppTableRequest,
    )
    from larkdocio.base.schema_client import BaseSchemaClient

    bare_field = DeleteAppTableFieldRequest.builder().build()
    bare_table = DeleteAppTableRequest.builder().build()
    bare_batch = BatchDeleteAppTableRequest.builder().build()

    calls = []

    class _Leg:
        def __getattr__(self, name):
            def _call(request):
                calls.append(request)

                class _R:
                    code = 0
                    data = type("D", (), {"field_id": "fld1"})()
                return _R()
            return _call

    class _SDK:
        pass

    sdk = _SDK()
    sdk.bitable = _SDK()
    sdk.bitable.v1 = _SDK()
    sdk.bitable.v1.app_table = _Leg()
    sdk.bitable.v1.app_table_field = _Leg()
    client = BaseSchemaClient("id", "secret", sdk_client=sdk,
                              rate_limiter=type("L", (), {"acquire": lambda self: None})())

    client.delete_field("appX", "tblY", "fldZ")
    client.delete_table("appX", "tblY")
    client.batch_delete_tables("appX", ["tblY", "tblZ"])

    assert calls[0].paths != bare_field.paths and "fldZ" in str(calls[0].paths)
    assert calls[1].paths != bare_table.paths and "tblY" in str(calls[1].paths)
    assert calls[2].body != bare_batch.body
    assert calls[2].body.table_ids == ["tblY", "tblZ"]


# --------------------------------------------------------------------------- #
# AC10 — the three permission rows, DERIVED and never widened                  #
# --------------------------------------------------------------------------- #

def _destructive_endpoints():
    """This family's endpoints, **derived from its own descriptors** and filtered to it, so a
    claim about three call sites cannot silently become a claim about another family's."""
    return sorted({d.endpoint for d in destructive.SCHEMA_OP_FAMILY.ops})


def test_AC10_the_three_endpoints_RESOLVE_to_a_write_row_with_evidence_and_a_label():
    from larkdocio import permissions as perm

    assert _destructive_endpoints() == [
        "/open-apis/bitable/v1/apps/:app_token/tables/:table_id",
        "/open-apis/bitable/v1/apps/:app_token/tables/:table_id/fields/:field_id",
        "/open-apis/bitable/v1/apps/:app_token/tables/batch_delete",
    ]
    for endpoint in _destructive_endpoints():
        scopes = perm.scopes_for_endpoints((endpoint,), "write")
        assert scopes, f"{endpoint} resolves to no scope row — the requirement is nowhere"
        for scope in scopes:
            assert scope.evidence.strip(), (endpoint, scope.scope)
            assert scope.verification in perm.VERIFICATION_LABELS, scope.verification
        assert perm._table_row(endpoint, "write") is not None, endpoint


def test_AC10_the_endpoints_are_DERIVED_FROM_THE_CLIENTS_OWN_CODE():
    """Not read off the descriptors: walked out of the three client methods themselves, so a
    descriptor that drifted from its call would not paper over the requirement."""
    from larkdocio import permissions as perm
    from larkdocio.base.schema_client import BaseSchemaClient

    for method, endpoint in (
            (BaseSchemaClient.delete_field,
             "/open-apis/bitable/v1/apps/:app_token/tables/:table_id/fields/:field_id"),
            (BaseSchemaClient.delete_table,
             "/open-apis/bitable/v1/apps/:app_token/tables/:table_id"),
            (BaseSchemaClient.batch_delete_tables,
             "/open-apis/bitable/v1/apps/:app_token/tables/batch_delete")):
        assert endpoint in perm.endpoints_of(method), method.__name__


def test_AC10_NO_SCOPE_IS_WIDENED_a_delete_needs_what_a_record_write_needs():
    from larkdocio import permissions as perm
    from larkdocio.base import write_ops

    record = {s.scope for d in write_ops.WRITE_OPS
              for s in perm.scopes_for_endpoints((d.endpoint,), "write")}
    deletes = {s.scope for e in _destructive_endpoints()
               for s in perm.scopes_for_endpoints((e,), "write")}
    assert deletes == record == {"bitable:app"}


def test_AC10_the_READ_row_is_UNTOUCHED_by_this_family():
    from larkdocio import permissions as perm
    from larkdocio.base import ops as base_ops

    read = {s.scope for d in base_ops.OPS
            for s in perm.scopes_for_endpoints((d.endpoint,), "read")}
    assert read == {"bitable:app:readonly"}


def test_AC10_this_story_REQUESTS_WIDENS_AND_ESCALATES_NOTHING():
    import pathlib

    from larkdocio.base import loss_preview, schema_client

    for module in (destructive, loss_preview, schema_client):
        text = pathlib.Path(module.__file__).read_text(encoding="utf-8").lower()
        for forbidden in ("request_scope", "grant_scope", "escalate"):
            assert forbidden not in text, (module.__name__, forbidden)


# --------------------------------------------------------------------------- #
# AC11 — BASE.md: the operations rows, ONE new register row, ONE extension     #
# --------------------------------------------------------------------------- #

def _base_md():
    return (REPO_ROOT / "BASE.md").read_text(
        encoding="utf-8")


def test_AC11_every_destructive_operations_row_NAMES_ITS_BLAST_RADIUS():
    text = _base_md()
    for name, radius in (("delete_field", "ONE COLUMN"),
                         ("delete_table", "THE WHOLE TABLE"),
                         ("batch_delete_tables", "APP-WIDE")):
        row = [line for line in text.splitlines() if line.startswith(f"| `{name}`")]
        assert len(row) == 1, name
        assert "blast radius" in row[0] and radius in row[0], name


def test_AC11_the_ONE_new_register_row_states_the_INVARIANT_and_its_revisit_trigger():
    from base_md import register_rows as _register_rows

    rows = _register_rows(_base_md())
    row = [r for r in rows if r["#"] == "32"]
    assert len(row) == 1, "exactly ONE new register row"
    cell = row[0]["Limitation / workaround"]
    assert "cannot be ENUMERATED" in cell
    assert "app-scoped" in cell.lower() and "under-report" in cell.lower()
    assert "larkdocio.base.loss_preview.LOSS_MUST_BE_ENUMERABLE" in cell
    trigger = row[0]["Revisit trigger — the observable API change"]
    assert "blast radius" in trigger or "impact" in trigger
    assert "cheaper scan is not a trigger" in trigger


def test_AC11_row_9_was_EXTENDED_not_re_authored_and_KEEPS_its_original_claim():
    from base_md import register_rows as _register_rows

    row = [r for r in _register_rows(_base_md()) if r["#"] == "9"][0]
    cell = row["Limitation / workaround"]
    assert "DELETE is TRASH, not purge" in cell, "the original claim survives"
    assert "copied apps" in cell and "copy_app" in cell, "so does LD-263's extension"
    assert "no API undo" in cell, "this story's half"
    assert "larkdocio.base.loss_preview.TRASH_NOT_PURGE" in cell


def test_AC11_rows_10_and_20_are_NEITHER_EDITED_NOR_CONTRADICTED():
    from base_md import register_rows as _register_rows

    rows = {r["#"]: r for r in _register_rows(_base_md())}
    assert "UN-PURGEABLE" in rows["10"]["Limitation / workaround"]
    # LD-269 SHIPPED the resolution and rewrote row 20 in place, which its own revisit trigger
    # named. LD-265's boundary is unchanged and is asserted where it belongs — on this story's
    # CODE, in the test below: the loss preview still reads the schema and follows no link.
    assert rows["20"]["Status"].strip().strip("`") == "supported"
    assert "LINK CELL IS FOLLOWED" in rows["20"]["Limitation / workaround"]


def test_AC11_the_LOSS_PREVIEW_uses_the_DETECTOR_ONLY_and_follows_NO_LINK():
    """Row 20's boundary, asserted on the code rather than on the doc: nothing in the preview
    reads a record of a linked table to resolve an id."""
    import pathlib

    text = pathlib.Path(lp.__file__).read_text(encoding="utf-8")
    assert "link_record_ids" not in text, (
        "resolving a link cell is a later rung's; this module reads the SCHEMA only")


# --------------------------------------------------------------------------- #
# AC12 — dialect-free                                                          #
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# The COMPUTED half of the blast radius — a Lookup that rolls up from a table   #
# being deleted survives and BLANKS, and a link-only scan cannot see it.        #
#                                                                              #
# Measured live: a table delete blanked a whole Lookup column on every row that #
# the preview never named. The dependency costs zero extra calls — the app scan #
# already holds every table's fields, and the target table is on the Lookup's   #
# own property.                                                                 #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("as_dict", [False, True], ids=["typed-property", "raw-property"])
def test_a_TABLE_delete_NAMES_the_lookup_that_ROLLS_UP_FROM_IT(as_dict):
    world = lookup_rollup_world(as_dict=as_dict)
    plan = schema_dry_run([destructive.delete_table("app", "tblSrc")], read_client=world)
    loss = plan.entries[0].loss_preview

    rows = {(row["table_id"], row["field_name"]): row for row in loss["inbound_lookups"]}
    assert set(rows) == {("tblRoll", "Source rollup")}, (
        "the Lookup mirrors the doomed table; it is the column that goes blank")
    row = rows[("tblRoll", "Source rollup")]
    assert row["rolls_up_from_table"] == "tblSrc"
    assert row["field_id"] == "fldLook"
    assert row["cells_with_data"] == 2
    assert "blank" in row["effect"].lower()
    assert "tblRoll" in loss["other_tables"]
    # The reported reproduction, inverted: the serialized preview must name the column.
    assert "Source rollup" in str(loss) and "fldLook" in str(loss)
    # The link half is untouched by the widening.
    assert [(r["table_id"], r["field_name"]) for r in loss["inbound_links"]] == [
        ("tblRoll", "Source link")]


def test_a_lookup_rolling_up_from_a_SURVIVING_table_is_NOT_reported():
    world = lookup_rollup_world()
    plan = schema_dry_run([destructive.delete_table("app", "tblSrc")], read_client=world)
    named = {row["field_name"] for row in plan.entries[0].loss_preview["inbound_lookups"]}
    assert "Rollup rollup" not in named, (
        "that Lookup mirrors Rollup, which survives — reporting it would be noise")


def test_a_lookup_INSIDE_the_doomed_table_is_LOSS_not_a_blanking_survivor():
    world = lookup_rollup_world()
    plan = schema_dry_run([destructive.delete_table("app", "tblRoll")], read_client=world)
    loss = plan.entries[0].loss_preview
    assert {(r["table_id"], r["field_name"]) for r in loss["inbound_lookups"]} == {
        ("tblOther", "Rollup rollup")}
    assert "Source rollup" in {c["field_name"] for c in loss["columns"]}, (
        "the doomed table's own Lookup is destroyed with the table, not left dangling")


def test_a_lookup_the_scan_CANNOT_PLACE_refuses_rather_than_going_silent():
    """The invariant's own arm. A Lookup whose provenance did not arrive might roll up from
    the table being deleted, and might not — and an unenumerable loss refuses."""
    world = lookup_rollup_world(target=None)
    plan = schema_dry_run([destructive.delete_table("app", "tblSrc")], read_client=world)
    refusal = _refusal_of(plan)
    assert refusal.reason == Refusal.LOSS_NOT_ENUMERABLE
    assert "Source rollup" in refusal.detail and "tblRoll" in refusal.detail
    assert plan.api_call_count == 0
    with pytest.raises(DestructiveConsentRequired):
        consent_to_destroy(plan)


def test_a_FIELD_delete_names_every_lookup_that_ROLLS_UP_FROM_ITS_TABLE():
    """The mirror case: which FIELD a Lookup rolls up does not survive the transport, so the
    candidate set is named in full and the missing precision is said out loud."""
    world = lookup_rollup_world()
    plan = schema_dry_run([destructive.delete_field("app", "tblSrc", "fldSrcName")],
                          read_client=world)
    loss = plan.entries[0].loss_preview
    rows = {(r["table_id"], r["field_name"]): r for r in loss["inbound_lookups"]}
    assert set(rows) == {("tblRoll", "Source rollup")}
    effect = rows[("tblRoll", "Source rollup")]["effect"].lower()
    assert "which field" in effect and "unavailable" in effect
    assert "tblRoll" in loss["other_tables"]


def test_deleting_a_LINK_column_names_the_lookups_in_ITS_OWN_table_as_candidates():
    """A Lookup reaches another table THROUGH a link column in its own table, and which link
    is not reported — so deleting a link column names every Lookup beside it."""
    world = lookup_rollup_world()
    plan = schema_dry_run([destructive.delete_field("app", "tblRoll", "fldSrcLink")],
                          read_client=world)
    loss = plan.entries[0].loss_preview
    rows = {(r["table_id"], r["field_name"]) for r in loss["inbound_lookups"]}
    assert ("tblRoll", "Source rollup") in rows
    assert any("link column" in r["effect"].lower() for r in loss["inbound_lookups"])


def test_a_PLAIN_field_delete_in_a_table_NO_LOOKUP_MIRRORS_reports_none():
    """The widening must not turn every delete into a wall of candidates: nothing mirrors
    Other, and the column is not a link, so there is nothing computed to say."""
    world = lookup_rollup_world()
    plan = schema_dry_run([destructive.delete_field("app", "tblOther", "fldOtherOwn")],
                          read_client=world)
    loss = plan.entries[0].loss_preview
    assert loss["inbound_lookups"] == []
    assert loss["other_tables"] == []


def test_every_preview_says_that_FORMULA_EXPRESSIONS_ARE_NOT_TRACED():
    """The boundary of the enumeration, disclosed rather than left as silence: the Lookup
    class is traced from its own configuration, a formula string is never read."""
    world = lookup_rollup_world()
    plan = schema_dry_run([destructive.delete_table("app", "tblSrc"),
                           destructive.delete_field("app", "tblSrc", "fldSrcName")],
                          read_client=world)
    for entry in plan.entries:
        note = entry.loss_preview["not_traced"]
        assert note == lp.FORMULA_EXPRESSIONS_ARE_NOT_TRACED
        assert "never parsed" in note.lower() and "lookup" in note.lower()


def test_the_lookup_reading_is_the_PROVENANCE_SURFACES_OWN_not_a_second_spelling():
    """One authored path to the target table. A second walk of the nested filter key in this
    module is how the preview and the reader would come to disagree about the same column."""
    import pathlib

    from larkdocio.base import computed

    text = pathlib.Path(lp.__file__).read_text(encoding="utf-8")
    assert 'get("filter_info"' not in text and "TARGET_TABLE_PATH" not in text, (
        "the nested provenance path is walked in larkdocio.base.computed and read from here")

    world = lookup_rollup_world()
    scan = lp.scan_app(world, "app")
    spec = scan.require_table("tblRoll").field("fldLook")
    assert spec.is_lookup is True
    assert spec.rolls_up_from_table == "tblSrc"
    # The same column, read through the provenance surface's own door: one answer, not two.
    reading = computed.computed_columns(world.tables["tblRoll"]["fields"])
    assert [(r.field_id, r.rolls_up_from_table) for r in reading] == [("fldLook", "tblSrc")]


def test_BASE_md_records_that_the_preview_reaches_the_LOOKUP_class():
    cell = [r for r in __import__("test_base_md_matrix")._register_rows(_base_md())
            if r["#"] == "32"][0]["Limitation / workaround"]
    assert "Lookup" in cell, "the register row must not claim a link-only scan is complete"


# --------------------------------------------------------------------------- #
# LD-285 — THE COUNT IS SHAPE-AWARE FOR WRAPPER-VALUED KINDS.                  #
#                                                                              #
# "An empty cell is an absent key" is exact for a scalar and FALSE for a       #
# wrapper: an empty link cell arrives as a PRESENT key carrying                #
# `{"link_record_ids": null}`, so a key-presence count scored it as data. The  #
# two empty link forms are the landed reading of the Base read spec § F1-S1 AC3             #
# (`larkdocio.base.cells.link_state`) — read here, never re-pinned.            #
# --------------------------------------------------------------------------- #

def _example_table_world(*, populated=3, never_set=61):
    """A link column present on every row, populated on a few: 64 rows, 3 of which actually
    link — the table a key-presence count scores as 64.
    """
    rows = [FakeRecord(f"pop{i}", {"Name": f"p{i}",
                                   "Legacy record": {"link_record_ids": [f"old{i}"]}})
            for i in range(populated)]
    rows += [FakeRecord(f"nev{i}", {"Name": f"n{i}",
                                    "Legacy record": {"link_record_ids": None}})
             for i in range(never_set)]
    return ScanWorld({
        "tblExample": {
            "name": "Example Table", "revision": 9,
            "fields": [FakeField("fldName", "Name"),
                       link_field("fldLegacy", "Legacy record",
                                  target_table_id="tblOld", target_table_name="Legacy")],
            "records": rows,
        },
        "tblOld": {
            "name": "Legacy", "revision": 1,
            "fields": [FakeField("fldOldName", "Name")],
            "records": [FakeRecord(f"old{i}", {"Name": f"o{i}"}) for i in range(3)],
        },
    })


def _one_column_world(field, values):
    """One table, one column, one row per value — **the key is present in every row**,
    which is the whole point: these are exactly the cells a key-presence count scored."""
    return ScanWorld({"tblOne": {
        "name": "One", "revision": 1, "fields": [field],
        "records": [FakeRecord(f"rec{i}", {field.field_name: value})
                    for i, value in enumerate(values)]}})


def test_LD285_the_REPORTED_REPRO_64_rows_3_of_which_LINK_counts_THREE_not_64():
    world = _example_table_world()
    scan = lp.scan_app(world, "app")
    assert scan.row_count("tblExample") == 64, "the world under test is 64 rows"
    assert scan.cells_with_data("tblExample", "Legacy record") == 3, (
        "61 rows carry a PRESENT key holding an empty wrapper; only 3 hold a link")


@pytest.mark.parametrize("empty", [{"link_record_ids": None}, {"link_record_ids": []}],
                         ids=["never-set", "emptied"])
def test_LD285_BOTH_of_the_link_cells_EMPTY_FORMS_count_ZERO(empty):
    """The two empties are different facts about the same cell and neither is data."""
    field = link_field("fldL", "Link", target_table_id="tblGone", target_table_name="Gone")
    scan = lp.scan_app(_one_column_world(field, [empty] * 5), "app")
    assert scan.cells_with_data("tblOne", "Link") == 0


def test_LD285_a_POPULATED_link_counts_ROWS_not_the_ids_inside_them():
    field = link_field("fldL", "Link", target_table_id="tblGone", target_table_name="Gone")
    world = _one_column_world(field, [{"link_record_ids": ["a", "b", "c"]},
                                      {"link_record_ids": None},
                                      {"link_record_ids": ["d"]}])
    assert lp.scan_app(world, "app").cells_with_data("tblOne", "Link") == 2


@pytest.mark.parametrize("field,value", [
    (FakeField("f", "C", type=17, ui_type="Attachment"), []),
    (FakeField("f", "C", type=11, ui_type="User"), []),
    (FakeField("f", "C", type=23, ui_type="GroupChat"), []),
    (FakeField("f", "C", type=1003, ui_type="CreatedUser"), []),
    (FakeField("f", "C", type=4, ui_type="MultiSelect"), []),
    (FakeField("f", "C", type=19, ui_type="Lookup"), {"type": 1, "value": None}),
    (FakeField("f", "C", type=19, ui_type="Lookup"), {"type": 1, "value": []}),
    (FakeField("f", "C", type=20, ui_type="Formula"), {"type": 1, "value": []}),
    (FakeField("f", "C", type=22, ui_type="Location"), {}),
    (FakeField("f", "C"), None),
], ids=["attachment", "user", "group-chat", "created-user", "multi-select",
        "lookup-null", "lookup-empty", "formula-empty", "location-empty", "explicit-null"])
def test_LD285_EVERY_OTHER_PRESENT_BUT_EMPTY_WRAPPER_counts_ZERO(field, value):
    """The audit the report asked for, one row per kind whose empty form is a present key —
    including the typed wrapper a `Lookup` blanked by a table delete reads back as."""
    scan = lp.scan_app(_one_column_world(field, [value] * 4), "app")
    assert scan.cells_with_data("tblOne", "C") == 0


@pytest.mark.parametrize("field,value", [
    (FakeField("f", "C", type=17, ui_type="Attachment"), [{"name": "quote.pdf"}]),
    (FakeField("f", "C", type=11, ui_type="User"), [{"name": "Ada"}]),
    (FakeField("f", "C", type=4, ui_type="MultiSelect"), ["a", "b"]),
    (FakeField("f", "C", type=19, ui_type="Lookup"), {"type": 1, "value": ["x"]}),
    (FakeField("f", "C", type=19, ui_type="Lookup"), {"type": 2, "value": [0]}),
    (FakeField("f", "C", type=22, ui_type="Location"), {"full_address": "1 Main St"}),
    (FakeField("f", "C", type=2, ui_type="Number"), 0),
    (FakeField("f", "C", type=7, ui_type="Checkbox"), False),
    (FakeField("f", "C"), ""),
], ids=["attachment", "person", "multi-select", "lookup", "lookup-zero", "location",
        "number-zero", "checkbox-false", "empty-string"])
def test_LD285_a_PRESENT_KEY_THAT_IS_NOT_AN_EMPTY_WRAPPER_IS_STILL_DATA(field, value):
    """The mirror-image bug this fix must not introduce: **zero is a value**, and so is
    `false`. Nothing is inferred from a scalar's shape — the key-presence rule stands
    everywhere it was verified exact, and only the wrapper kinds are re-read."""
    scan = lp.scan_app(_one_column_world(field, [value] * 3), "app")
    assert scan.cells_with_data("tblOne", "C") == 3


def test_LD285_the_PREVIEW_THAT_QUOTES_THE_COUNT_reports_the_corrected_number():
    """End to end: the number an operator reads before pressing the button."""
    world = _example_table_world()
    plan = schema_dry_run([destructive.delete_field("app", "tblExample", "fldLegacy")],
                          read_client=world)
    loss = plan.entries[0].loss_preview
    assert [c["cells_with_data"] for c in loss["columns"]] == [3]

    inbound = schema_dry_run([destructive.delete_table("app", "tblOld")],
                             read_client=world).entries[0].loss_preview["inbound_links"]
    assert [(r["field_name"], r["cells_with_data"]) for r in inbound] == [
        ("Legacy record", 3)], "the dangling-link entry quotes the same corrected count"


def test_LD285_the_link_reading_is_the_CELL_SURFACES_OWN_not_a_second_spelling(monkeypatch):
    """One authored definition of what an empty link cell is. A second spelling here is how
    the preview and the reader would come to disagree about the same cell — and it would also
    breach the source-text fence that keeps a resolved link out of this module (AC11)."""
    from larkdocio.base import cells

    assert lp.cell_holds_data({"link_record_ids": None}) is False
    assert cells.link_state({"link_record_ids": None}) == cells.LINK_NEVER_SET
    assert cells.link_state({"link_record_ids": []}) == cells.LINK_EMPTIED
    # The reading is the cell surface's, called — a re-implementation here would have to name
    # the key, which AC11's fence forbids outright.
    calls = []
    original = cells.link_state
    monkeypatch.setattr(cells, "link_state",
                        lambda value: calls.append(value) or original(value))
    lp.scan_app(_example_table_world(), "app").cells_with_data("tblExample", "Legacy record")
    assert len(calls) == 64, "every cell's emptiness is decided by the cell surface's reading"


def test_AC12_the_shipped_text_of_this_story_carries_NO_INTERNAL_DIALECT():
    from consumer_text import dialect_hits

    for module in (lp, destructive):
        for name in dir(module):
            value = getattr(module, name)
            if isinstance(value, str) and not name.startswith("__"):
                assert not dialect_hits(value), (module.__name__, name,
                                                 dialect_hits(value))
        assert not dialect_hits(module.__doc__ or ""), module.__name__


# --------------------------------------------------------------------------- #
# LD-304 — the raised exception HOISTS the per-entry refusal's own fix line     #
#                                                                              #
# The per-entry ``Refusal.detail`` names the exact call to make; the raised     #
# ``DestructiveConsentRequired`` is the one that lands in a terminal. It now    #
# leads with that detail and keeps the doctrine behind it.                      #
# --------------------------------------------------------------------------- #

def _unpreviewed_plan():
    """A plan whose destructive entry carries NEITHER a loss preview NOR a refusal.

    ``schema_dry_run`` cannot produce one — every destructive entry either previews or
    refuses — so the state that reaches ``consent_to_destroy``'s first branch is built by
    stripping the preview off a real plan's real entry.
    """
    from dataclasses import replace

    world = two_table_link_world()
    plan = schema_dry_run([destructive.delete_table("app", "tblThird")], read_client=world)
    object.__setattr__(plan, "_entries", (replace(plan.entries[0], loss_preview=None),))
    return plan


def _refused_plan():
    """A destructive dry run with no read client."""
    return schema_dry_run([destructive.delete_table("app", "tblRef")])


def test_LD304_AC1_the_consent_refusal_HOISTS_THE_ENTRYS_OWN_FIX_LINE():
    """The consumer's acceptance example, verbatim: the exception names the call to make."""
    plan = _refused_plan()
    with pytest.raises(DestructiveConsentRequired) as caught:
        consent_to_destroy(plan)
    message = str(caught.value)

    assert "Pass read_client=BaseReadClient(...) to schema_dry_run" in message, (
        "the per-entry refusal's own fix line must ride the raised exception")
    # Hoisted, not paraphrased: the entry's own detail IS the text, doctrine lifted off the
    # tail so the message can carry it once, at the end.
    detail = _refusal_of(plan).detail
    assert detail.replace(lp.LOSS_MUST_BE_ENUMERABLE, "").strip() in message


def test_LD304_AC2_THE_FIX_LINE_COMES_FIRST_before_the_doctrine():
    """A truncating log or a narrow terminal shows the fix, not the invariant."""
    for plan in (_refused_plan(), _unpreviewed_plan()):
        message = str(pytest.raises(DestructiveConsentRequired,
                                    consent_to_destroy, plan).value)
        doctrine = message.index(lp.LOSS_MUST_BE_ENUMERABLE)
        assert doctrine > 0, "the doctrine must not open the message"
        for actionable in ("read_client=BaseReadClient(...)", "schema_dry_run"):
            assert message.index(actionable) < doctrine, actionable
        assert message.count(lp.LOSS_MUST_BE_ENUMERABLE) == 1, (
            "hoisting must not duplicate the doctrine into the middle of the message")


def test_LD304_AC3_the_DOCTRINE_IS_PRESERVED_at_every_one_of_the_FIVE_SITES():
    """``LOSS_MUST_BE_ENUMERABLE`` still rides every message that carried it: a Base delete's
    blast radius is not table-scoped, and this issue reorders rather than trades safety text
    for brevity."""
    world = two_table_link_world()
    doctrine = lp.LOSS_MUST_BE_ENUMERABLE

    # 1. consent_to_destroy — an entry with no loss preview.
    site_1 = str(pytest.raises(DestructiveConsentRequired,
                               consent_to_destroy, _unpreviewed_plan()).value)
    # 2. consent_to_destroy — entries that refused at plan time.
    site_2 = str(pytest.raises(DestructiveConsentRequired,
                               consent_to_destroy, _refused_plan()).value)
    # 3. _check_consent — a destructive plan applied with no consent object.
    live = schema_dry_run([destructive.delete_table("app", "tblThird")], read_client=world)
    site_3 = str(pytest.raises(DestructiveConsentRequired, schema_apply, live,
                              client=object(), read_client=world).value)
    # 4. the dry run's own refusal — no read client at all.
    site_4 = _refusal_of(_refused_plan()).detail
    # 5. the dry run's own refusal — a scan that could not be completed.
    truncated = two_table_link_world()
    truncated.truncate.add("tables")
    site_5 = _refusal_of(schema_dry_run([destructive.delete_table("app", "tblRef")],
                                        read_client=truncated)).detail

    for index, site in enumerate((site_1, site_2, site_3, site_4, site_5), start=1):
        assert doctrine in site, f"site {index} dropped the doctrine"


def test_LD304_AC4_BOTH_consent_to_destroy_BRANCHES_hoist_an_actionable_line():
    """The no-loss-preview branch and the refused-at-plan-time branch both lead with the
    entry's own actionable text — the refusal's ``detail`` where there is one, and the
    entry's own description plus the exact call where there is not."""
    refused = str(pytest.raises(DestructiveConsentRequired,
                                consent_to_destroy, _refused_plan()).value)
    assert refused.startswith("- "), "the actionable line opens the message"
    assert "Pass read_client=BaseReadClient(...) to schema_dry_run" in refused

    unpreviewed = str(pytest.raises(DestructiveConsentRequired,
                                    consent_to_destroy, _unpreviewed_plan()).value)
    assert unpreviewed.startswith("- ")
    assert "tblThird" in unpreviewed, (
        "with no refusal to hoist, the entry still names itself")
    assert "read_client=BaseReadClient(...)" in unpreviewed
    assert "schema_dry_run" in unpreviewed


def test_LD304_AC5_the_TWO_BRANCHES_WITH_NO_DETAIL_TO_HOIST_still_name_the_exact_call():
    """``_check_consent``'s two branches carry no per-entry detail — they were read and
    deliberately left: each already names the exact call and already says nothing was sent."""
    world = two_table_link_world()
    plan = schema_dry_run([destructive.delete_table("app", "tblThird")], read_client=world)

    no_consent = str(pytest.raises(DestructiveConsentRequired, schema_apply, plan,
                                   client=object(), read_client=world).value)
    assert "consent=larkdocio.base.schema_apply.consent_to_destroy(plan)" in no_consent
    assert "Nothing was sent." in no_consent

    other = schema_dry_run([destructive.delete_table("app", "tblThird")], read_client=world)
    wrong_plan = str(pytest.raises(DestructiveConsentRequired, schema_apply, plan,
                                   client=object(), read_client=world,
                                   consent=consent_to_destroy(other)).value)
    assert "DIFFERENT plan" in wrong_plan
    assert "re-run schema_dry_run" in wrong_plan
    assert "Nothing was sent." in wrong_plan


def test_LD304_AC6_NOTHING_WAS_SENT_survives_and_stays_findable_in_every_message():
    """The second half of the consumer's delight. Every fence message still says it."""
    world = two_table_link_world()
    plan = schema_dry_run([destructive.delete_table("app", "tblThird")], read_client=world)
    other = schema_dry_run([destructive.delete_table("app", "tblThird")], read_client=world)

    messages = [
        str(pytest.raises(DestructiveConsentRequired,
                          consent_to_destroy, _unpreviewed_plan()).value),
        str(pytest.raises(DestructiveConsentRequired,
                          consent_to_destroy, _refused_plan()).value),
        str(pytest.raises(DestructiveConsentRequired, schema_apply, plan,
                          client=object(), read_client=world).value),
        str(pytest.raises(DestructiveConsentRequired, schema_apply, plan,
                          client=object(), read_client=world,
                          consent=consent_to_destroy(other)).value),
    ]
    for message in messages:
        assert "nothing was sent" in message.lower(), message[:80]


def test_LD304_AC7_the_hoisting_messages_carry_NO_INTERNAL_DIALECT():
    from consumer_text import dialect_hits

    for plan in (_unpreviewed_plan(), _refused_plan()):
        message = str(pytest.raises(DestructiveConsentRequired,
                                    consent_to_destroy, plan).value)
        assert not dialect_hits(message), dialect_hits(message)
