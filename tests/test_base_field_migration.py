"""LD-291 — the guided column-type migration, offline.

The refusal `convert_field` gives a `Text -> Number` ask is **correct and stays**; what this
module pins is the sequence that stands beside it. Every test here runs against the destructive
rung's own `ScanWorld` — one read seam whose state the test owns — plus a scripted schema/write
client pair that really mutates that world, so a read-back that confirms is confirming
something.
"""
import ast
import inspect

import pytest

from base_destructive_fakes import FakeField, FakeRecord, ScanWorld

from larkdocio.base import field_migration as fm
from larkdocio.base.field_authoring import (
    CONVERSION_PAIRS,
    UncapturedConversionError,
    enabled_conversion_pairs,
)
from larkdocio.base.schema_apply import (
    DestructiveConsentRequired,
    consent_to_destroy,
    schema_dry_run,
)
from larkdocio.base.schema_ops import schema_ops
from larkdocio.base.schema_ops_destructive import delete_field
from larkdocio.base.schema_ops_fields import convert_field


APP = "appLD291"
TABLE = "tblWork"


# --------------------------------------------------------------------------- #
# The world, and the clients that really change it                              #
# --------------------------------------------------------------------------- #

def a_world(values=("1", "2", "3"), *, ui_type="Text", type_=1):
    """One table, one primary Name column and one `Estimate` column holding ``values``."""
    return ScanWorld({
        TABLE: {
            "name": "Work", "revision": 7,
            "fields": [FakeField("fldName", "Name"),
                       FakeField("fldEst", "Estimate", type=type_, ui_type=ui_type)],
            "records": [FakeRecord(f"rec{i}", {"Name": f"row {i}", "Estimate": value})
                        for i, value in enumerate(values, start=1)],
        },
    })


class WorldSchemaClient:
    """A schema client whose field ops really mutate a :class:`ScanWorld`.

    ``mangle`` is the forced-defect knob AC4 is verified with: it is applied to the value the
    RECORD client stores, not here, but the two clients share the world so the knob lives with
    it.
    """

    def __init__(self, world, *, deaf=()):
        self.world = world
        self.deaf = set(deaf)
        self.calls = []
        self._next = 0

    def _bump(self, table_id):
        body = self.world.tables[table_id]
        body["revision"] = (body.get("revision") or 0) + 1

    def create_field(self, app_token, table_id, field_name, field_type, ui_type=None,
                     properties=None):
        self.calls.append(("create_field", table_id, field_name, field_type, ui_type))
        if "create_field" in self.deaf:
            return None
        self._next += 1
        field_id = f"fldNEW{self._next}"
        self.world.tables[table_id]["fields"].append(
            FakeField(field_id, field_name, type=field_type, ui_type=ui_type or "Text"))
        self._bump(table_id)
        return field_id

    def update_field(self, app_token, table_id, field_id, field_name, field_type,
                     ui_type=None, properties=None):
        self.calls.append(("update_field", table_id, field_id, field_name))
        body = self.world.tables[table_id]
        for spec in body["fields"]:
            if spec.field_id == field_id:
                # A record's `fields` body is keyed on the field NAME, so a rename moves every
                # cell's key with it — the fake models that, or a migration would read as
                # having lost the values it really kept.
                for record in body["records"]:
                    if spec.field_name in record.fields:
                        record.fields[field_name] = record.fields.pop(spec.field_name)
                spec.field_name = field_name
        self._bump(table_id)
        return field_id

    def delete_field(self, app_token, table_id, field_id):
        self.calls.append(("delete_field", table_id, field_id))
        body = self.world.tables[table_id]
        gone = [f for f in body["fields"] if f.field_id == field_id]
        body["fields"] = [f for f in body["fields"] if f.field_id != field_id]
        for spec in gone:
            for record in body["records"]:
                record.fields.pop(spec.field_name, None)
        self._bump(table_id)
        return field_id


class WorldWriteClient:
    """A record write client that really stores values into the same world.

    ``mangle`` corrupts what is stored — the forced copy defect AC4 demands be verified.
    ``drop`` stores nothing at all, which is the other half of the same failure.
    """

    def __init__(self, world, *, mangle=None, drop=False):
        self.world = world
        self.mangle = mangle
        self.drop = drop
        self.calls = []

    def batch_update_records(self, app_token, table_id, updates):
        self.calls.append(("batch_update_records", table_id, len(updates)))
        body = self.world.tables[table_id]
        for record_id, fields in updates:
            for record in body["records"]:
                if record.record_id == record_id:
                    if self.drop:
                        continue
                    for name, value in fields.items():
                        record.fields[name] = (self.mangle(value) if self.mangle
                                               else value)
        body["revision"] = (body.get("revision") or 0) + 1
        return []

    def batch_create_records(self, app_token, table_id, rows):  # pragma: no cover
        raise AssertionError("a migration never creates a record")

    def batch_delete_records(self, app_token, table_id, record_ids):  # pragma: no cover
        raise AssertionError("a migration never deletes a record")


def a_plan(world, **kwargs):
    kwargs.setdefault("field_name", "Estimate")
    kwargs.setdefault("to_field_type", 2)
    kwargs.setdefault("to_ui_type", "Number")
    return fm.plan_field_migration(world, APP, TABLE, **kwargs)


def field_names(world, table_id=TABLE):
    return [spec.field_name for spec in world.tables[table_id]["fields"]]


# --------------------------------------------------------------------------- #
# AC1 — one entry point, one plan, no consumer-authored ordering                #
# --------------------------------------------------------------------------- #

def test_AC1_one_call_produces_one_plan_covering_every_step_in_apply_order():
    plan = a_plan(a_world())
    assert [step.kind for step in plan.steps] == list(fm.MIGRATION_STEPS)
    assert [step.index for step in plan.steps] == [0, 1, 2, 3, 4]


def test_AC1_the_entry_points_are_reachable_from_larkdocio_base():
    import larkdocio.base as base

    for name in ("plan_field_migration", "apply_field_migration", "FieldMigrationPlan"):
        assert hasattr(base, name), name
        assert name in base.__all__


def test_AC1_the_plan_is_NON_FORGEABLE_like_every_other_plan_on_this_surface():
    with pytest.raises(TypeError, match="plan_field_migration"):
        fm.FieldMigrationPlan()


# --------------------------------------------------------------------------- #
# AC2 — the preview covers the WHOLE sequence, and issues ZERO writes           #
# --------------------------------------------------------------------------- #

def test_AC2_planning_issues_ZERO_writes_because_no_write_client_is_even_reachable():
    world = a_world()
    schema, write = WorldSchemaClient(world), WorldWriteClient(world)
    a_plan(world)
    assert schema.calls == [] and write.calls == []
    # And the plan-time signature cannot take one: the only client it accepts is a READ one.
    parameters = list(inspect.signature(fm.plan_field_migration).parameters)
    assert parameters[0] == "read_client"
    assert not [name for name in parameters
                if name.endswith("client") and name != "read_client"]


def test_AC2_every_step_says_what_it_will_do_and_how_many_writes_it_costs():
    plan = a_plan(a_world())
    assert all(step.describe for step in plan.steps)
    assert plan.api_call_count == sum(step.writes for step in plan.steps)
    assert plan.steps[2].writes == 0            # the verification is a read


def test_AC2_the_destructive_step_carries_the_EXISTING_loss_preview_UNCHANGED():
    world = a_world()
    plan = a_plan(world)
    theirs = schema_dry_run([delete_field(APP, TABLE, "fldEst", revision=7)],
                            read_client=a_world()).entries[0].loss_preview
    assert plan.loss_preview == theirs
    assert plan.loss_previews == (theirs,)
    assert plan.steps[3].loss_preview == theirs
    assert theirs["columns"][0]["cells_with_data"] == 3


# --------------------------------------------------------------------------- #
# AC3 — consent binds the SEQUENCE, not step 3                                  #
# --------------------------------------------------------------------------- #

def test_AC3_a_migration_applied_WITHOUT_consent_refuses_before_any_call():
    world = a_world()
    schema, write = WorldSchemaClient(world), WorldWriteClient(world)
    plan = a_plan(world)
    with pytest.raises(DestructiveConsentRequired):
        fm.apply_field_migration(plan, schema_client=schema, client=write, read_client=world)
    assert schema.calls == [] and write.calls == []
    assert "Estimate" in field_names(world)


def test_AC3_consent_is_the_EXISTING_primitive_minted_over_the_MIGRATION_plan():
    from larkdocio.base.schema_apply import DestructiveConsent

    plan = a_plan(a_world())
    consent = consent_to_destroy(plan)
    assert isinstance(consent, DestructiveConsent)
    assert consent.plan is plan
    assert consent.losses == plan.loss_previews


def test_AC3_a_token_minted_against_a_DIFFERENT_plan_is_refused():
    world = a_world()
    schema, write = WorldSchemaClient(world), WorldWriteClient(world)
    plan, other = a_plan(world), a_plan(a_world())
    with pytest.raises(DestructiveConsentRequired, match="DIFFERENT plan"):
        fm.apply_field_migration(plan, schema_client=schema, client=write,
                                 read_client=world, consent=consent_to_destroy(other))
    assert schema.calls == [] and write.calls == []


# --------------------------------------------------------------------------- #
# The happy path — the five-step dance as one call plus one consent             #
# --------------------------------------------------------------------------- #

def test_the_whole_sequence_lands_and_the_column_ends_up_named_as_the_old_one():
    world = a_world()
    schema, write = WorldSchemaClient(world), WorldWriteClient(world)
    plan = a_plan(world)
    log = fm.apply_field_migration(plan, schema_client=schema, client=write,
                                   read_client=world, consent=consent_to_destroy(plan))
    assert [entry.outcome for entry in log.entries] == ["applied"] * 5
    assert log.halt is None
    assert field_names(world) == ["Name", "Estimate"]
    survivor = [f for f in world.tables[TABLE]["fields"] if f.field_name == "Estimate"][0]
    assert (survivor.type, survivor.ui_type) == (2, "Number")
    assert [record.fields["Estimate"] for record in world.tables[TABLE]["records"]] == [
        1.0, 2.0, 3.0]


# --------------------------------------------------------------------------- #
# AC4 — the destructive step is unreachable on an unverified copy               #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("client_kwargs, needle", [
    ({"mangle": lambda value: value + 1000}, "does not hold"),
    ({"drop": True}, "does not hold"),
])
def test_AC4_a_copy_that_did_not_round_trip_HALTS_and_leaves_the_source_INTACT(
        client_kwargs, needle):
    world = a_world()
    schema = WorldSchemaClient(world)
    write = WorldWriteClient(world, **client_kwargs)
    plan = a_plan(world)
    log = fm.apply_field_migration(plan, schema_client=schema, client=write,
                                   read_client=world, consent=consent_to_destroy(plan))

    outcomes = [entry.outcome for entry in log.entries]
    assert outcomes[:2] == ["applied", "applied"]
    assert outcomes[2] == "refused"
    assert outcomes[3:] == ["not-attempted", "not-attempted"]
    assert needle in log.entries[2].refusal.detail
    # NOTHING was destroyed: no delete was even attempted, and the column is still there.
    assert not [call for call in schema.calls if call[0] == "delete_field"]
    assert "Estimate" in field_names(world)


def test_AC4_the_verification_compares_VALUES_not_merely_counts():
    world = a_world()
    schema = WorldSchemaClient(world)
    # Same count, wrong values — the failure a row-count check would wave through.
    write = WorldWriteClient(world, mangle=lambda value: value * 10)
    plan = a_plan(world)
    log = fm.apply_field_migration(plan, schema_client=schema, client=write,
                                   read_client=world, consent=consent_to_destroy(plan))
    assert log.entries[2].outcome == "refused"
    assert "Estimate" in field_names(world)


# --------------------------------------------------------------------------- #
# AC5 — a complete account, and the non-atomicity STATED                        #
# --------------------------------------------------------------------------- #

def test_AC5_the_log_is_ONE_ENTRY_PER_STEP_in_plan_order_with_a_typed_disposition():
    world = a_world()
    plan = a_plan(world)
    log = fm.apply_field_migration(plan, schema_client=WorldSchemaClient(world),
                                   client=WorldWriteClient(world, drop=True),
                                   read_client=world, consent=consent_to_destroy(plan))
    assert len(log.entries) == len(plan.steps)
    assert [entry.op for entry in log.entries] == list(fm.MIGRATION_STEPS)
    assert all(entry.outcome for entry in log.entries)
    assert all(entry.refusal is not None
               for entry in log.entries if entry.outcome != "applied")


def test_AC5_a_HALTED_run_names_the_state_the_table_is_now_in_and_what_recovery_would_do():
    world = a_world()
    plan = a_plan(world)
    log = fm.apply_field_migration(plan, schema_client=WorldSchemaClient(world),
                                   client=WorldWriteClient(world, drop=True),
                                   read_client=world, consent=consent_to_destroy(plan))
    recovery = log.halt["recovery"]
    assert recovery["source_column"] == "Estimate"
    assert recovery["source_column_present"] is True
    assert recovery["staging_column"] in field_names(world)
    assert recovery["what_a_recovery_would_do"]


def test_AC5_the_NON_ATOMICITY_is_stated_in_the_shipped_text_and_on_the_plan():
    assert "cannot be atomic" in fm.MIGRATION_IS_NOT_ATOMIC.lower()
    assert a_plan(a_world()).to_dict()["not_atomic"] == fm.MIGRATION_IS_NOT_ATOMIC


# --------------------------------------------------------------------------- #
# AC6 — NO NEW BYPASS OF ANY EXISTING GATE                                       #
# --------------------------------------------------------------------------- #

def test_AC6_the_module_reaches_NO_client_directly_it_only_composes_the_shipped_applies():
    tree = ast.parse(inspect.getsource(fm))
    reached = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            target = node.func.value
            if isinstance(target, ast.Name) and target.id in (
                    "client", "schema_client", "write_client"):
                reached.add(f"{target.id}.{node.func.attr}")
    assert reached == set(), reached


def test_AC6_a_table_that_MOVED_under_the_plan_refuses_with_zero_writes():
    world = a_world()
    schema, write = WorldSchemaClient(world), WorldWriteClient(world)
    plan = a_plan(world)
    world.tables[TABLE]["revision"] = 99          # something else wrote to the table
    log = fm.apply_field_migration(plan, schema_client=schema, client=write,
                                   read_client=world, consent=consent_to_destroy(plan))
    assert log.entries[0].outcome == "stale"
    assert [entry.outcome for entry in log.entries[1:]] == ["not-attempted"] * 4
    assert schema.calls == [] and write.calls == []


def test_AC6_an_UNAUTHORABLE_target_inherits_check_authorable_rather_than_routing_round_it():
    from larkdocio.base.field_vocabulary import UnauthorableFieldError

    with pytest.raises(UnauthorableFieldError):
        a_plan(a_world(), to_field_type=19, to_ui_type="Lookup")


def test_AC6_a_source_whose_CELLS_ARE_NOT_WRITABLE_refuses_because_a_copy_cannot_be_verified():
    world = a_world(values=("x",), ui_type="Formula", type_=20)
    with pytest.raises(fm.FieldMigrationRefused, match="cannot be read back"):
        a_plan(world)


# --------------------------------------------------------------------------- #
# AC7 — the uncaptured-conversion refusal is UNCHANGED                          #
# --------------------------------------------------------------------------- #

def test_AC7_convert_field_still_refuses_Text_to_Number_exactly_as_before():
    with pytest.raises(UncapturedConversionError):
        convert_field(APP, TABLE, "fldEst", "Estimate", 2,
                      from_ui_type="Text", to_ui_type="Number")


def test_AC7_the_pair_table_is_THE_SAME_SET_and_the_migration_is_not_in_it():
    assert enabled_conversion_pairs() == ("Text -> Barcode",)
    assert len(CONVERSION_PAIRS) == 1
    assert "Text -> Number" not in enabled_conversion_pairs()
    registered = {descriptor.name for descriptor in schema_ops()}
    assert not registered & set(fm.MIGRATION_STEPS)


def test_AC7_the_migration_says_plainly_that_it_is_NOT_a_conversion():
    text = fm.MIGRATION_IS_NOT_A_CONVERSION
    assert "not a conversion" in text.lower()
    assert "server-side" in text.lower() and "rebuild" in text.lower()
    assert fm.plan_field_migration.__doc__ is not None
    assert a_plan(a_world()).to_dict()["not_a_conversion"] == text


def test_AC7_no_value_is_converted_IN_PLACE_the_writes_all_land_on_the_STAGING_column():
    world = a_world()
    write = WorldWriteClient(world)
    plan = a_plan(world)
    fm.apply_field_migration(plan, schema_client=WorldSchemaClient(world), client=write,
                             read_client=world, consent=consent_to_destroy(plan))
    assert plan.staging_name != "Estimate"


# --------------------------------------------------------------------------- #
# AC8 — a value the target kind cannot encode REFUSES; never coerced on a guess  #
# --------------------------------------------------------------------------- #

def test_AC8_a_value_the_target_cannot_encode_refuses_the_WHOLE_migration_at_PLAN_time():
    world = a_world(values=("1", "not a number", "3"))
    with pytest.raises(fm.UntranscodableValueError) as caught:
        a_plan(world)
    message = str(caught.value)
    assert "rec2" in message and "not a number" in message
    assert "Number" in message


def test_AC8_a_target_kind_with_NO_transcoding_refuses_rather_than_guessing():
    with pytest.raises(fm.UntranscodableValueError, match="no transcoding"):
        a_plan(a_world(), to_field_type=17, to_ui_type="Attachment")


def test_AC8_there_is_NO_default_lossy_mode_anywhere_on_the_entry_point():
    parameters = inspect.signature(fm.plan_field_migration).parameters
    assert not [name for name in parameters if "skip" in name or "lossy" in name]


def test_AC8_an_EMPTY_source_cell_is_skipped_and_the_count_is_DISCLOSED():
    world = a_world(values=("1", "", "3"))
    plan = a_plan(world)
    assert plan.skipped_empty == ("rec2",)
    assert plan.to_dict()["skipped_empty"] == ["rec2"]
    assert len(plan.values) == 2
