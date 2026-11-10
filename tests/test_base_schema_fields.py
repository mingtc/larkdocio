"""LD-262 — field create / update / convert behind the plan gate.

Offline, capture-anchored, zero network. Every property shape asserted here names the
**capture file** it was transcribed from, because the whole point of this rung is that a
`property` shape nobody captured is a guess, and a guess on a schema write authors a column
that is not the one the caller asked for.
"""
import ast
import json
from pathlib import Path

import pytest

from log_reading_apply import reading_the_log
from larkdocio.base import field_authoring as fa
from larkdocio.base import schema_ops, schema_ops_fields as sof
from larkdocio.base.field_vocabulary import UnauthorableFieldError
from larkdocio.base.plan import Refusal
from larkdocio.base.schema_apply import schema_apply, schema_dry_run
schema_apply = reading_the_log(schema_apply)
from larkdocio.base.schema_plan import SCOPE_APP, SCOPE_TABLE, NO_APP_REVISION_CAS
from domain_vocabulary import RETIRED_ID

REPO = Path(__file__).resolve().parent.parent
CAPTURES = REPO / "tests" / "captures" / "base-study" / "captures"


# --------------------------------------------------------------------------- #
# Fakes — this file's own, so the wave-2 partner's fakes module is untouched.   #
# --------------------------------------------------------------------------- #

class FakeField:
    def __init__(self, field_id, field_name, field_type, ui_type, property=None):
        self.field_id = field_id
        self.field_name = field_name
        self.type = field_type
        self.ui_type = ui_type
        self.property = property


class FakeTable:
    def __init__(self, table_id, name="t", revision=7):
        self.table_id = table_id
        self.name = name
        self.revision = revision


class FieldWorld:
    """A read client over an in-memory Base: tables with revisions, fields per table."""

    def __init__(self, tables=None, fields=None):
        self.tables = tables or {"app": [FakeTable("tbl1")]}
        self.fields = fields or {"tbl1": []}
        self.reads = []

    def list_tables(self, app_token):
        self.reads.append(("list_tables", app_token))
        return list(self.tables.get(app_token, ()))

    def list_fields(self, app_token, table_id):
        self.reads.append(("list_fields", app_token, table_id))
        return list(self.fields.get(table_id, ()))

    def get_app(self, app_token):  # pragma: no cover - not used by field ops
        raise AssertionError("a field op never reads the app")

    def bump(self, app_token="app", table_id="tbl1", by=1):
        for table in self.tables[app_token]:
            if table.table_id == table_id:
                table.revision += by


class ScriptedFieldClient:
    """A schema client stand-in that records calls and mutates the world."""

    def __init__(self, world, *, deaf=(), raises=None):
        self.world = world
        self.calls = []
        self.deaf = set(deaf)
        self.raises = raises or {}
        self._n = 0

    def _record(self, name, *args):
        self.calls.append((name,) + args)

    def create_field(self, app_token, table_id, field_name, field_type,
                     ui_type=None, properties=None):
        self._record("create_field", app_token, table_id, field_name, field_type, ui_type)
        if "create_field" in self.raises:
            raise self.raises["create_field"]
        self._n += 1
        field = FakeField(f"fld{self._n}", field_name, field_type, ui_type)
        if "create_field" not in self.deaf:
            self.world.fields.setdefault(table_id, []).append(field)
            self.world.bump(app_token, table_id)
        return field

    def update_field(self, app_token, table_id, field_id, field_name, field_type,
                     ui_type=None, properties=None):
        self._record("update_field", app_token, table_id, field_id, field_name)
        if "update_field" in self.raises:
            raise self.raises["update_field"]
        for field in self.world.fields.get(table_id, ()):
            if field.field_id == field_id and "update_field" not in self.deaf:
                field.field_name = field_name
                self.world.bump(app_token, table_id)
                return field
        return FakeField(field_id, field_name, field_type, ui_type)

    def convert_field(self, app_token, table_id, field_id, field_name, field_type,
                      *, from_ui_type=None, to_ui_type=None, properties=None):
        self._record("convert_field", app_token, table_id, field_id, to_ui_type)
        if "convert_field" in self.raises:
            raise self.raises["convert_field"]
        for field in self.world.fields.get(table_id, ()):
            if field.field_id == field_id and "convert_field" not in self.deaf:
                field.ui_type = to_ui_type
                self.world.bump(app_token, table_id)
                return field
        return FakeField(field_id, field_name, field_type, to_ui_type)


def _world_with_one_text_field():
    world = FieldWorld()
    world.fields["tbl1"] = [FakeField("fldA", "conv", 1, "Text")]
    return world


# --------------------------------------------------------------------------- #
# AC1 — the plan gate, the registration, and read_only() untouched              #
# --------------------------------------------------------------------------- #

def test_ac1_the_field_family_is_REGISTERED_into_the_aggregator_as_its_own_module():
    assert "larkdocio.base.schema_ops_fields" in schema_ops.FAMILY_MODULES
    families = {family.name: family for family in schema_ops.registered_families()}
    assert sof.FAMILY_NAME in families
    assert families[sof.FAMILY_NAME].module == "larkdocio.base.schema_ops_fields"


def test_ac1_every_field_op_declares_MUTATES_and_the_whole_schema_table_still_does():
    names = {d.name for d in sof.SCHEMA_OP_FAMILY.ops}
    assert names == {"create_field", "update_field", "convert_field"}
    assert all(d.mutates is True for d in sof.SCHEMA_OP_FAMILY.ops)
    assert schema_ops.all_mutate() is True


def test_ac1_the_READ_registry_still_answers_read_only_TRUE():
    """LD-255 AC2b: the three landed assertions are not edited, they are re-asserted."""
    from larkdocio.base import ops as base_ops
    from larkdocio.base import write_ops

    assert base_ops.read_only() is True
    assert write_ops.all_mutate() is True
    read_names = {d.name for d in base_ops.OPS}
    assert not (read_names & {d.name for d in schema_ops.schema_ops()})


def test_ac1_a_HAND_BUILT_LOOK_ALIKE_plan_is_REJECTED_by_schema_apply():
    class LookAlikePlan:
        entries = ()
        resolved = ()

    with pytest.raises(TypeError) as excinfo:
        schema_apply(LookAlikePlan(), client=object(), read_client=object())
    assert "schema_dry_run" in str(excinfo.value)


def test_ac1_no_field_op_settles_the_ONE_async_op_is_still_the_copy():
    assert [d.name for d in schema_ops.settling_ops()] == ["copy_app"]


def test_ac1_the_client_method_for_every_field_descriptor_RESOLVES():
    for descriptor in sof.SCHEMA_OP_FAMILY.ops:
        assert callable(schema_ops.impl_of(descriptor)), descriptor.name


# --------------------------------------------------------------------------- #
# AC2 — the property shapes come from captures, and each names its capture      #
# --------------------------------------------------------------------------- #

def test_ac2_every_captured_shape_NAMES_A_CAPTURE_FILE_THAT_EXISTS():
    assert fa.FIELD_PROPERTY_SHAPES
    for ui_type, shape in fa.FIELD_PROPERTY_SHAPES.items():
        assert shape.capture, ui_type
        assert (CAPTURES / shape.capture).exists(), (ui_type, shape.capture)


def test_ac2_LOCATION_nests_under_property_location_input_type():
    """`05-04-field-zoo-create-results.json`: the created Location echoed
    `property: {"location": {"input_type": "not_limit"}}` — a NESTED shape no flat
    `input_type` key would have produced."""
    payload = json.loads((CAPTURES / "05-04-field-zoo-create-results.json").read_text(encoding="utf-8"))
    created = [a["created"] for a in payload["response"]["data"]["attempts"]
               if a["requested"]["field_name"] == "Z-Location"][0]
    assert created["property"] == {"location": {"input_type": "not_limit"}}

    built = fa.build_property("Location", input_type="not_limit")
    assert built.location is not None
    assert built.location.input_type == "not_limit"
    assert fa.FIELD_PROPERTY_SHAPES["Location"].capture == "05-04-field-zoo-create-results.json"


def test_ac2_CURRENCY_uses_property_currency_code():
    payload = json.loads((CAPTURES / "06-01-field-schema.json").read_text(encoding="utf-8"))
    field = [f for f in payload["response"]["data"]["items"]
             if f["ui_type"] == "Currency"][0]
    assert field["property"]["currency_code"] == "USD"

    built = fa.build_property("Currency", currency_code="USD", formatter="0.00")
    assert built.currency_code == "USD" and built.formatter == "0.00"
    assert fa.FIELD_PROPERTY_SHAPES["Currency"].capture == "06-01-field-schema.json"


def test_ac2_RATING_uses_property_rating_symbol_and_the_MINIMAL_form_was_REFUSED():
    payload = json.loads((CAPTURES / "p0-2-02-remaining-types-create.json").read_text(encoding="utf-8"))
    data = payload["response"]["data"]
    assert data["Rating"]["field"]["property"]["rating"] == {"symbol": "star"}
    # The capture's own control: a Rating with NO property answered 1254001.
    assert data["Rating_minimal"]["code"] == 1254001

    built = fa.build_property("Rating", symbol="star", formatter="0", min=0, max=5)
    assert built.rating is not None and built.rating.symbol == "star"
    with pytest.raises(fa.UncapturedFieldPropertyError) as excinfo:
        fa.build_property("Rating")
    assert "1254001" in str(excinfo.value)


def test_ac2_SELECTS_take_options_and_each_option_carries_name_and_color():
    payload = json.loads((CAPTURES / "05-04-field-zoo-create-results.json").read_text(encoding="utf-8"))
    created = [a["created"] for a in payload["response"]["data"]["attempts"]
               if a["requested"]["field_name"] == "Z-SingleSelect"][0]
    assert [o["name"] for o in created["property"]["options"]] == ["Alpha", "Beta"]

    built = fa.build_property("SingleSelect", options=[{"name": "Alpha", "color": 0}])
    assert [o.name for o in built.options] == ["Alpha"]


def test_ac2_THE_PHONE_TRAP_the_ui_type_is_Phone_and_NOT_PhoneNumber():
    """The named regression test for the captured trap. `05-04` asked for
    `ui_type: "PhoneNumber"` and was refused `99992402`; `06-01` shows the shipped
    identity is `type:13` / `ui_type:"Phone"` with `property: null`."""
    zoo = json.loads((CAPTURES / "05-04-field-zoo-create-results.json").read_text(encoding="utf-8"))
    attempt = [a for a in zoo["response"]["data"]["attempts"]
               if a["requested"]["field_name"] == "Z-Phone"][0]
    assert attempt["requested"]["ui_type"] == "PhoneNumber"
    assert attempt["code"] == 99992402, "the trap: PhoneNumber is not the ui_type"

    schema = json.loads((CAPTURES / "06-01-field-schema.json").read_text(encoding="utf-8"))
    phone = [f for f in schema["response"]["data"]["items"] if f["ui_type"] == "Phone"][0]
    assert (phone["type"], phone["ui_type"], phone["property"]) == (13, "Phone", None)

    # The shipped surface refuses `PhoneNumber` LOCALLY, through LD-261's allow-list,
    # and its message names `Phone` as what is possible instead.
    with pytest.raises(UnauthorableFieldError) as excinfo:
        sof.create_field("app", "tbl1", "Mobile", 13, ui_type="PhoneNumber")
    assert "Phone" in str(excinfo.value)
    assert fa.FIELD_PROPERTY_SHAPES["Phone"].keys == ()


def test_ac2_a_ui_type_whose_property_shape_NO_CAPTURE_CARRIES_is_refused_uncaptured():
    """The set is DERIVED from the two constants, so it fills itself when the server's enum
    grows a kind this library has no shape for. It is empty today — `Formula` was the one
    member and this rung's own probe flipped it — so the refusal is proved on a synthetic
    kind rather than left unexercised."""
    assert fa.UNCAPTURED_PROPERTY_UI_TYPES == (), fa.UNCAPTURED_PROPERTY_UI_TYPES
    with pytest.raises(fa.UncapturedFieldPropertyError) as excinfo:
        fa.build_property("SomethingLarkAddedLater", whatever=1)
    assert "no captured authoring shape" in str(excinfo.value)

    original = fa.UNCAPTURED_PROPERTY_UI_TYPES
    try:
        fa.UNCAPTURED_PROPERTY_UI_TYPES = ("Formula",)
        with pytest.raises(fa.UncapturedFieldPropertyError) as excinfo:
            fa.build_property("Formula", formula_expression="1+1")
        message = str(excinfo.value)
        assert "uncaptured" in message.lower() and "Formula" in message
    finally:
        fa.UNCAPTURED_PROPERTY_UI_TYPES = original


def test_ac2_a_key_the_captured_shape_DOES_NOT_CARRY_is_refused_never_guessed():
    with pytest.raises(fa.UncapturedFieldPropertyError) as excinfo:
        fa.build_property("Currency", currency_code="USD", zzz=1)
    assert "zzz" in str(excinfo.value)


def test_ac2_a_type_with_NO_captured_property_is_authored_WITHOUT_one():
    assert fa.build_property("Checkbox") is None
    assert fa.build_property("Url") is None
    assert fa.build_property("Attachment") is None


# --------------------------------------------------------------------------- #
# AC3 — the DuplexLink cross-table CREATE, disclosed in the DRY RUN             #
# --------------------------------------------------------------------------- #

def test_ac3_the_MIRROR_NAMING_RULE_is_pinned_against_the_capture():
    payload = json.loads((CAPTURES / "p0-2-01-interconnection-field-create.json").read_text(encoding="utf-8"))
    data = payload["response"]["data"]
    source = data["DuplexLink"]["field"]
    mirror = data["duplex_mirror_in_ref_table"]["new_fields"][0]
    source_table_name = mirror["property"]["table_name"]      # the SOURCE table
    assert mirror["field_name"] == fa.duplex_mirror_name(source_table_name,
                                                         source["field_name"])
    assert mirror["property"]["back_field_id"] == source["field_id"]


def test_ac3_the_DRY_RUN_discloses_the_second_table_and_the_predicted_mirror_name():
    request = sof.create_field("app", "tbl1", "DuplexLink", 21, ui_type="DuplexLink",
                               properties={"table_id": "tblRef"},
                               source_table_name="Main")
    plan = schema_dry_run([request])
    entry = plan.entries[0]
    disclosure = entry.to_dict()["cross_table_create"]
    assert disclosure["table_id"] == "tblRef"
    assert disclosure["predicted_field_name"] == fa.duplex_mirror_name("Main", "DuplexLink")
    assert "another table" in disclosure["what"].lower()
    # And it is in the plan's own JSON, before any call is made.
    assert "tblRef" in plan.to_json()


def test_ac3_a_NON_duplex_create_discloses_NO_cross_table_create():
    plan = schema_dry_run([sof.create_field("app", "tbl1", "Note", 1, ui_type="Text")])
    assert plan.entries[0].to_dict()["cross_table_create"] is None


def test_ac3_the_disclosure_is_made_with_ZERO_api_calls():
    world = FieldWorld()
    client = ScriptedFieldClient(world)
    schema_dry_run([sof.create_field("app", "tbl1", "L", 21, ui_type="DuplexLink",
                                     properties={"table_id": "tblRef"},
                                     source_table_name="Main")])
    assert client.calls == [] and world.reads == []


# --------------------------------------------------------------------------- #
# LD-295 — FORMULA_EVALUATION_WHAT actually reaches the Formula dry-run entry  #
# --------------------------------------------------------------------------- #

def test_ld295_a_formula_create_carries_FORMULA_EVALUATION_WHAT_in_the_dry_run():
    plan = schema_dry_run([sof.create_field("app", "tbl1", "F", 20, ui_type="Formula",
                                            properties={"formula_expression": "1+1"})])
    entry = plan.entries[0]
    assert fa.FORMULA_EVALUATION_WHAT in entry.revision_guard_disclosure
    assert fa.FORMULA_EVALUATION_WHAT in entry.to_dict()["revision_guard_disclosure"]
    # And it is in the plan's own JSON, before any call is made — same shape as the
    # DuplexLink mirror disclosure (AC3 above).
    assert fa.FORMULA_EVALUATION_WHAT in plan.to_json()


def test_ld295_a_NON_formula_create_does_NOT_carry_the_formula_sentence():
    plan = schema_dry_run([sof.create_field("app", "tbl1", "Note", 1, ui_type="Text")])
    assert fa.FORMULA_EVALUATION_WHAT not in plan.entries[0].revision_guard_disclosure


# --------------------------------------------------------------------------- #
# AC4 — PUT for non-type edits, allow-list applied to any ui_type in the body   #
# --------------------------------------------------------------------------- #

def test_ac4_update_field_is_a_PUT_on_the_field_path():
    descriptor = schema_ops.schema_op("update_field")
    assert descriptor.http_method == "PUT"
    assert descriptor.endpoint == (
        "/open-apis/bitable/v1/apps/:app_token/tables/:table_id/fields/:field_id")


def test_ac4_the_allow_list_bites_on_PUT_IDENTICALLY_to_POST():
    """`p1-q2-02` step 11: the same `99992402` on the PUT route. The block is the
    vocabulary, not the verb — so the local refusal must not be create-only."""
    payload = json.loads((CAPTURES / "p1-q2-02-true-identity-retries.json").read_text(encoding="utf-8"))
    put_refusal = [s for s in payload["steps"]
                   if s["_method"] == "PUT" and s["_lark_code"] == 99992402][0]
    assert "ui_type" in put_refusal["response"]["error"]["field_violations"][0]["field"]

    with pytest.raises(UnauthorableFieldError):
        sof.update_field("app", "tbl1", "fldA", "conv", 1, ui_type="Email")


def test_ac4_update_field_edits_the_NAME_and_leaves_the_type_alone():
    world = _world_with_one_text_field()
    client = ScriptedFieldClient(world)
    plan = schema_dry_run([sof.update_field("app", "tbl1", "fldA", "renamed", 1,
                                            revision=7)])
    log = schema_apply(plan, client=client, read_client=world)
    assert [e.outcome for e in log.entries] == ["applied"], log.entries[0].refusal
    assert world.fields["tbl1"][0].field_name == "renamed"
    assert world.fields["tbl1"][0].ui_type == "Text"


# --------------------------------------------------------------------------- #
# AC5 — conversion: a pair table keyed on evidence (D2″ ruled (c))              #
# --------------------------------------------------------------------------- #

def test_ac5_the_ONLY_enabled_pair_today_is_TEXT_TO_BARCODE_and_it_names_its_capture():
    assert len(fa.CONVERSION_PAIRS) == 1
    pair = fa.CONVERSION_PAIRS[0]
    assert (pair.from_ui_type, pair.to_ui_type) == ("Text", "Barcode")
    assert pair.field_type == 1, "same storage type both sides — that is the whole tranche"
    for capture in pair.captures:
        assert (CAPTURES / capture).exists(), capture


def test_ac5_the_capture_really_shows_the_conversion_landing_on_the_SAME_storage_type():
    payload = json.loads((CAPTURES / "p1-q2-02-true-identity-retries.json").read_text(encoding="utf-8"))
    before = [s for s in payload["steps"]
              if s["_method"] == "POST" and "'conv'" in str(s["_note"])][0]
    after = [s for s in payload["steps"]
             if s["_method"] == "PUT" and s["_lark_code"] == 0][0]
    assert before["response"]["data"]["field"]["ui_type"] == "Text"
    assert after["response"]["data"]["field"]["ui_type"] == "Barcode"
    assert (before["response"]["data"]["field"]["type"]
            == after["response"]["data"]["field"]["type"] == 1)


def test_ac5_EVERY_UNCAPTURED_PAIR_refuses_typed_uncaptured_NAMING_THE_PAIR():
    for pair in (("Text", "Number"), ("MultiSelect", "SingleSelect"), ("Text", "Checkbox"),
                 ("Number", "Text"), ("Barcode", "Text")):
        with pytest.raises(fa.UncapturedConversionError) as excinfo:
            fa.check_conversion(*pair)
        message = str(excinfo.value)
        assert pair[0] in message and pair[1] in message, message
        assert "uncaptured" in message.lower()


def test_ac5_an_uncaptured_conversion_makes_ZERO_TRANSPORT_CALLS():
    """The call-count spy. The refusal happens before a client is even reachable."""
    world = FieldWorld()
    client = ScriptedFieldClient(world)
    with pytest.raises(fa.UncapturedConversionError):
        sof.convert_field("app", "tbl1", "fldA", "conv", 1,
                          from_ui_type="Text", to_ui_type="Number")
    assert client.calls == []
    assert world.reads == []


def test_ac5_CROSS_STORAGE_conversions_are_OUT_and_the_refusal_SAYS_WHY():
    with pytest.raises(fa.UncapturedConversionError) as excinfo:
        fa.check_conversion("Text", "Number")
    message = str(excinfo.value)
    assert "Text -> Barcode" in message, "the refusal must name what IS possible"
    assert "coerce" in message or "blank" in message, (
        "the refusal must say WHY an unobserved pair is not inferred")


def test_ac5_a_CAPTURED_pair_converts_and_the_field_reads_back_with_the_new_identity():
    world = _world_with_one_text_field()
    client = ScriptedFieldClient(world)
    plan = schema_dry_run([sof.convert_field("app", "tbl1", "fldA", "conv", 1,
                                             from_ui_type="Text", to_ui_type="Barcode",
                                             revision=7)])
    log = schema_apply(plan, client=client, read_client=world)
    assert [e.outcome for e in log.entries] == ["applied"], log.entries[0].refusal
    assert world.fields["tbl1"][0].ui_type == "Barcode"


def test_ac5_the_pair_table_is_keyed_on_CELL_EFFECT_not_on_code_0():
    for pair in fa.CONVERSION_PAIRS:
        assert pair.cell_effect.strip(), pair
        assert "code:0" not in pair.cell_effect


# --------------------------------------------------------------------------- #
# AC6 — multiple:false is not a cardinality guarantee, on the AUTHORING side    #
# --------------------------------------------------------------------------- #

def test_ac6_the_capture_shows_a_multiple_false_link_ACCEPTING_TWO_IDS():
    payload = json.loads((CAPTURES / "p0-4-06-field-authoring-boundary.json").read_text(encoding="utf-8"))
    assert "multiple_false_fed_two_ids" in json.dumps(payload)


def test_ac6_the_authoring_surface_SETS_multiple_and_never_calls_it_a_constraint():
    built = fa.build_property("SingleLink", table_id="tblRef", multiple=False)
    assert built.multiple is False
    text = " ".join([
        fa.MULTIPLE_IS_NOT_A_CARDINALITY_GUARANTEE,
        (Path(sof.__file__).read_text(encoding="utf-8")),
        (Path(fa.__file__).read_text(encoding="utf-8")),
    ]).lower()
    for forbidden in ("enforces single", "guarantees single", "at most one value",
                      "cardinality is enforced"):
        assert forbidden not in text, forbidden
    assert "not a cardinality guarantee" in fa.MULTIPLE_IS_NOT_A_CARDINALITY_GUARANTEE.lower()


# --------------------------------------------------------------------------- #
# AC7 — Formula authoring probed or honestly uncaptured; cells STILL refused    #
# --------------------------------------------------------------------------- #

def test_ac7_FORMULA_authoring_is_recorded_HONESTLY_either_way():
    row = fa.FORMULA_AUTHORING
    assert row["status"] in ("captured", "partial", "refuted"), row
    assert row["evidence"], "silence is not a pass — the row states what was observed"
    assert (CAPTURES / row["evidence"]).exists()
    # The create answered code:0, and the capture says so itself.
    probe = json.loads((CAPTURES / row["evidence"]).read_text(encoding="utf-8"))
    observed = probe["observations"]["formula_authoring_probe"]
    assert observed["status"] == "captured" and observed["code"] == 0
    assert observed["created"]["type"] == 20
    assert fa.FIELD_PROPERTY_SHAPES["Formula"].capture == row["evidence"]


# --------------------------------------------------------------------------- #
# LD-280 — the CELL read the ld262 probe never took                             #
# --------------------------------------------------------------------------- #
# `code:0` and a column that reads back as type 20 prove the column EXISTS. The live probe
# then read the CELLS: a constant expression computes on every row, and a REFERENCING one
# — the shape every real formula has — never materialises, on either read route, over a
# record written before the column and one written after it. So the status is derived from
# the measured cell effect and the referencing shape is refused locally, with zero calls.

LD280 = "ld280-01-formula-evaluation-probe.json"


def test_ld280_the_ROW_IS_PINNED_to_a_capture_that_actually_READ_THE_CELLS():
    row = fa.FORMULA_EVALUATION
    assert row["evidence"] == LD280
    probe = json.loads((CAPTURES / LD280).read_text(encoding="utf-8"))
    seen = probe["observations"]["formula_cell_read"]
    assert row["constant_computes"] is seen["constant_computes"]
    assert row["reference_computes"] is seen["reference_computes"]
    # The three expressions the boundary is drawn from, all present in the committed capture.
    assert set(seen["cells_present_per_expression"]) == {
        "ld280-const", "ld280-ref", "ld280-bound"}
    assert seen["cells_present_per_expression"]["ld280-const"] is True
    assert seen["cells_present_per_expression"]["ld280-ref"] is False, (
        "the capture this refusal rests on must show the referencing cell ABSENT")
    assert seen["cells_present_per_expression"]["ld280-bound"] is False, (
        "the server's own rebound form, sent verbatim, is the control that rules out "
        "'Lark just rebinds names badly'")
    assert seen["polls"] >= 2, "one read is not a settle window"


def test_ld280_the_STATUS_IS_DERIVED_from_the_measured_cell_effect():
    """A hand-typed status is a claim; this one is a consequence of the measurement."""
    assert fa.FORMULA_AUTHORING["status"] == fa.formula_authoring_status(
        fa.FORMULA_EVALUATION)
    assert fa.formula_authoring_status(
        {"constant_computes": True, "reference_computes": True}) == "captured"
    assert fa.formula_authoring_status(
        {"constant_computes": True, "reference_computes": False}) == "partial"
    assert fa.formula_authoring_status(
        {"constant_computes": False, "reference_computes": False}) == "refuted"
    assert fa.FORMULA_AUTHORING["status"] == "partial"


def test_ld280_NO_TEXT_ON_THIS_ROW_CLAIMS_the_computation_the_evidence_does_not_show():
    text = " ".join(str(value) for value in fa.FORMULA_AUTHORING.values()).lower()
    assert "never computed" in text or "never materialis" in text or "inert" in text
    assert "code:0" in text and "cell" in text, (
        "the row must say what the acceptance proved and what it did not")


def test_ld280_a_REFERENCING_formula_expression_is_REFUSED_locally_with_ZERO_calls():
    for expression in ("CurrentValue.[PR Currency] * 2",
                       "CurrentValue.bitable::$table[tbl1].$field[fld1]*2",
                       "COUNTA(CurrentValue.[Stories])",
                       "SUM({Hours})"):
        with pytest.raises(fa.RefutedFieldAuthoringError) as caught:
            fa.build_property("Formula", formula_expression=expression)
        message = str(caught.value)
        assert LD280 in message, "the refusal cites the capture it rests on"
        assert "product" in message.lower(), "a refusal without a next move is a shrug"


def test_ld280_the_ONE_CAPTURED_EXPRESSION_CLASS_still_authors():
    """The constant computed on every row, so refusing it would refuse measured evidence."""
    for expression in ("1+1", "2 * (3 + 4)", "42", "1.5/2"):
        assert fa.build_property("Formula", formula_expression=expression) is not None


def test_ld280_an_EMPTY_or_UNPARSEABLE_expression_is_refused_rather_than_guessed():
    for expression in ("", "   ", "TODAY()"):
        with pytest.raises(fa.FieldAuthoringRefusal):
            fa.build_property("Formula", formula_expression=expression)


def test_ld280_the_REFUSAL_reaches_the_PLAN_CONSTRUCTOR_before_a_client_exists():
    with pytest.raises(fa.RefutedFieldAuthoringError):
        sof.create_field("app", "tbl", "progress", 20, ui_type="Formula",
                         properties={"formula_expression": "CurrentValue.[Done] / 2"})


def test_ld280_the_REFUSAL_reaches_the_CLIENT_SEAM_too():
    """The public client re-checks: a caller who came in that door reads the same refusal."""
    from larkdocio.base import schema_ops_fields as fields_module

    with pytest.raises(fa.RefutedFieldAuthoringError):
        fields_module.build_create_request(
            "app", "tbl", "progress", 20, ui_type="Formula",
            properties={"formula_expression": "CurrentValue.[Done] / 2"})


def test_ld280_the_ONE_CAPTURED_CLASS_still_PLANS_cleanly():
    """The refusal is a fence around the measured-dead shape, not around the kind."""
    request = sof.create_field("app", "tbl", "two", 20, ui_type="Formula",
                               properties={"formula_expression": "1+1"}, revision=3)
    assert request.op == "create_field"
    plan = schema_dry_run([request])
    assert plan.entries[0].refusal is None and plan.entries[0].is_resolved


def test_ac7_an_AUTHORABLE_field_is_NOT_a_LICENCE_to_write_its_cells():
    from larkdocio.base.field_vocabulary import (
        AUTHORABLE_BUT_CELLS_UNWRITABLE, is_authorable_ui_type)
    from larkdocio.base.write_vocabulary import NON_WRITABLE_PAIRS

    unwritable = {pair[1] for pair in NON_WRITABLE_PAIRS}
    for ui_type in ("Formula", "AutoNumber", "CreatedTime", "ModifiedTime",
                    "CreatedUser", "ModifiedUser"):
        assert is_authorable_ui_type(ui_type), ui_type
        assert ui_type in unwritable, ui_type
    assert {p[1] for p in AUTHORABLE_BUT_CELLS_UNWRITABLE} == {
        "Formula", "AutoNumber", "CreatedTime", "ModifiedTime", "CreatedUser",
        "ModifiedUser"}


def test_ac7_this_story_does_NOT_BLUR_the_two_constants():
    """One is the field-authoring allow-list, the other the non-writable CELL set. Neither
    is re-declared here, and neither is consulted for the other's question."""
    for module in (fa, sof):
        source = Path(module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        assigned = {
            target.id
            for node in ast.walk(tree) if isinstance(node, (ast.Assign, ast.AnnAssign))
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
            if isinstance(target, ast.Name)}
        for constant in ("AUTHORABLE_TYPES", "AUTHORABLE_UI_TYPES", "NON_WRITABLE_PAIRS"):
            assert constant not in assigned, (
                f"{constant} is re-declared in {module.__name__} — one definition")
    enforcement = Path(sof.__file__).read_text(encoding="utf-8")
    assert "check_authorable" in enforcement, "the allow-list is IMPORTED and enforced"
    assert "NON_WRITABLE_PAIRS" not in enforcement, (
        "the non-writable CELL set answers a different question and is not consulted here")


# --------------------------------------------------------------------------- #
# AC8 — table.revision is the anchor and it moves +1 per field op               #
# --------------------------------------------------------------------------- #

def test_ac8_the_capture_pins_PLUS_ONE_PER_FIELD_OP():
    payload = json.loads((CAPTURES / "p0-2-06-table-revision-granularity.json").read_text(encoding="utf-8"))
    data = payload["response"]["data"]
    assert data["after_field_create"] - data["before_field_create"] == 1
    assert data["after_field_delete"] - data["after_batch_update_of_3_records"] == 1
    assert fa.FIELD_OP_BUMPS_TABLE_REVISION_ONCE


def test_ac8_a_field_entry_is_TABLE_SCOPED_and_does_NOT_carry_the_app_disclosure():
    plan = schema_dry_run([sof.create_field("app", "tbl1", "N", 1, ui_type="Text",
                                            revision=7)])
    entry = plan.entries[0]
    assert entry.scope == SCOPE_TABLE
    assert entry.revision_guard_disclosure != NO_APP_REVISION_CAS
    assert NO_APP_REVISION_CAS not in entry.to_dict()["revision_guard_disclosure"]
    assert entry.revision_guard == "active"


def test_ac8_an_APP_SCOPED_entry_is_UNCHANGED_and_still_carries_the_absence():
    from larkdocio.base.schema_plan import create_table

    entry = schema_dry_run([create_table("app", "t", primary_field_name="Title")]).entries[0]
    assert entry.scope == SCOPE_APP
    assert entry.revision_guard_disclosure == NO_APP_REVISION_CAS
    assert entry.revision_guard is None


def test_ac8_STALE_BASE_refuses_with_ZERO_WRITES_when_the_table_moved():
    world = _world_with_one_text_field()
    client = ScriptedFieldClient(world)
    plan = schema_dry_run([sof.create_field("app", "tbl1", "N", 1, ui_type="Text",
                                            revision=7)])
    world.bump()      # somebody else wrote to the table between plan and apply
    log = schema_apply(plan, client=client, read_client=world)
    assert [e.outcome for e in log.entries] == ["stale"]
    assert log.entries[0].refusal.reason == Refusal.STALE_BASE
    assert client.calls == [], "a stale refusal issues ZERO writes"


def test_ac8_the_REVISION_ZERO_SENTINEL_is_unavailable_and_does_not_refuse():
    world = _world_with_one_text_field()
    world.tables["app"][0].revision = 0
    client = ScriptedFieldClient(world)
    plan = schema_dry_run([sof.create_field("app", "tbl1", "N", 1, ui_type="Text",
                                            revision=0)])
    assert plan.entries[0].revision_guard == "unavailable"
    log = schema_apply(plan, client=client, read_client=world)
    assert [e.outcome for e in log.entries] == ["applied"], log.entries[0].refusal


def test_ac8_the_shared_staleness_core_is_IMPORTED_not_copied():
    source = Path(sof.__file__).read_text(encoding="utf-8")
    assert "revision_guard_status" in source
    assert "def revision_guard_status" not in source


# --------------------------------------------------------------------------- #
# AC9 — R12 by construction + the write-effect oracle                           #
# --------------------------------------------------------------------------- #

def test_ac9_a_code_0_THAT_LEFT_THE_ANCHOR_UNMOVED_is_DROPPED_never_applied():
    """The deliberate-defect check: a client that answers happily and changes nothing."""
    world = _world_with_one_text_field()
    client = ScriptedFieldClient(world, deaf=("create_field",))
    plan = schema_dry_run([sof.create_field("app", "tbl1", "N", 1, ui_type="Text",
                                            revision=7)])
    log = schema_apply(plan, client=client, read_client=world)
    assert [e.outcome for e in log.entries] == ["dropped"]
    assert log.entries[0].refusal.reason == Refusal.WRITE_NOT_OBSERVED
    assert "revision" in log.entries[0].refusal.detail.lower()


def test_ac9_the_POSITIVE_CONTROL_the_same_op_on_a_live_client_is_applied():
    world = _world_with_one_text_field()
    client = ScriptedFieldClient(world)
    plan = schema_dry_run([sof.create_field("app", "tbl1", "N", 1, ui_type="Text",
                                            revision=7)])
    log = schema_apply(plan, client=client, read_client=world)
    assert [e.outcome for e in log.entries] == ["applied"]
    assert log.entries[0].read_back["revision_moved"] == 1


def test_ac9_EVERY_PARAMETER_SENT_differs_from_the_PARAMETER_FREE_CONTROL():
    """R12 by construction: every key the request carries is proved to change the request
    against the control that omits it — never that the call answered `code:0`."""
    control = sof.build_create_request("app", "tbl1", "N", 1)
    for kwargs, key in (
        ({"ui_type": "Barcode"}, "ui_type"),
        ({"ui_type": "Currency", "properties": {"currency_code": "USD"}}, "property"),
    ):
        variant = sof.build_create_request("app", "tbl1", "N", 1, **kwargs)
        assert variant.request_body != control.request_body, key
        assert getattr(variant.request_body, key if key != "property" else "property")


def test_ac9_a_BOGUS_property_key_is_refused_rather_than_silently_ignored():
    """The bogus-key control, applied at the seam: the API would swallow `zzz`, so the
    library refuses it instead of shipping a request whose `code:0` proves nothing."""
    with pytest.raises(fa.UncapturedFieldPropertyError):
        sof.create_field("app", "tbl1", "N", 2, ui_type="Currency",
                         properties={"zzz": 1})


# --------------------------------------------------------------------------- #
# AC10 — the error vocabulary, extended and actionable                          #
# --------------------------------------------------------------------------- #

def test_ac10_every_code_the_field_ops_can_meet_is_TYPED_with_ACTIONABLE_guidance():
    from larkdocio.base.errors import BASE_ERROR_CODES

    for code in (99992402, 1254001, 1254041, 1254004, 1002, 91402):
        assert code in fa.FIELD_OP_ERROR_CODES, code
        assert code in BASE_ERROR_CODES, code
        guidance = fa.FIELD_OP_ERROR_GUIDANCE[code]
        assert len(guidance) > 60, code
        assert any(verb in guidance.lower() for verb in
                   ("read ", "list ", "check", "re-read", "file ", "use ", "pass ")), code


def test_ac10_a_99992402_that_still_ARRIVES_is_an_API_DRIFT_ALARM_quoting_the_enum():
    from larkdocio.base.field_vocabulary import AUTHORABLE_UI_TYPES

    alarm = fa.FIELD_OP_ERROR_GUIDANCE[99992402]
    assert "drift" in alarm.lower()
    assert "not a caller error" in alarm.lower()
    assert AUTHORABLE_UI_TYPES[0] in fa.drift_alarm_detail(), (
        "the alarm quotes the server's own enum as this library currently holds it")


def test_ac10_a_1254001_in_a_SHIPPED_op_is_named_a_LIBRARY_DEFECT():
    guidance = fa.FIELD_OP_ERROR_GUIDANCE[1254001]
    assert "library" in guidance.lower() and "defect" in guidance.lower()
    assert "your" not in guidance.lower().split("defect")[0], (
        "the message must not blame the caller for a body this library assembled")


# --------------------------------------------------------------------------- #
# AC11 — permission rows, derived, never widened                                #
# --------------------------------------------------------------------------- #

def _field_endpoints():
    return sorted({d.endpoint for d in sof.SCHEMA_OP_FAMILY.ops})


def test_ac11_both_field_endpoints_RESOLVE_to_a_write_row_with_evidence_and_a_label():
    from larkdocio import permissions as perm

    assert _field_endpoints() == [
        "/open-apis/bitable/v1/apps/:app_token/tables/:table_id/fields",
        "/open-apis/bitable/v1/apps/:app_token/tables/:table_id/fields/:field_id",
    ]
    for endpoint in _field_endpoints():
        scopes = perm.scopes_for_endpoints((endpoint,), "write")
        assert scopes, endpoint
        for scope in scopes:
            assert scope.evidence.strip()
            assert scope.verification in perm.VERIFICATION_LABELS
        assert perm._table_row(endpoint, "write") is not None, endpoint


def test_ac11_NO_SCOPE_IS_WIDENED_a_field_op_needs_what_a_record_write_needs():
    from larkdocio import permissions as perm
    from larkdocio.base import write_ops

    record = {s.scope for d in write_ops.WRITE_OPS
              for s in perm.scopes_for_endpoints((d.endpoint,), "write")}
    field = {s.scope for e in _field_endpoints()
             for s in perm.scopes_for_endpoints((e,), "write")}
    assert field == record == {"bitable:app"}


def test_ac11_the_READ_row_is_UNTOUCHED():
    from larkdocio import permissions as perm
    from larkdocio.base import ops as base_ops

    read = {s.scope for d in base_ops.OPS
            for s in perm.scopes_for_endpoints((d.endpoint,), "read")}
    assert read == {"bitable:app:readonly"}


def test_ac11_this_story_REQUESTS_WIDENS_AND_ESCALATES_NOTHING():
    for module in (fa, sof):
        text = Path(module.__file__).read_text(encoding="utf-8").lower()
        for forbidden in ("request_scope", "grant_scope", "escalate"):
            assert forbidden not in text, (module.__name__, forbidden)


# --------------------------------------------------------------------------- #
# AC13 — dialect-free                                                           #
# --------------------------------------------------------------------------- #

def test_ac13_no_internal_dialect_reaches_the_consumer_strings_this_story_ships():
    """The `_DECISION_REF` trap: no `D2″`, no issue ids, no spec/AC/story refs in the text a
    consumer reads out of a refusal or a disclosure."""
    import re

    consumer_text = " ".join([
        fa.MULTIPLE_IS_NOT_A_CARDINALITY_GUARANTEE,
        fa.CROSS_TABLE_CREATE_WHAT,
        fa.FIELD_OPS_RIDE_TABLE_REVISION,
        fa.drift_alarm_detail(),
        *fa.FIELD_OP_ERROR_GUIDANCE.values(),
        *(p.cell_effect for p in fa.CONVERSION_PAIRS),
    ])
    assert not re.search(r"\bLD-\d+\b", consumer_text)
    assert not RETIRED_ID.search(consumer_text)
    assert not re.search(r"\bAC\d+\b", consumer_text)
    assert "D2" not in consumer_text


# --------------------------------------------------------------------------- #
# LD-317 — THE MINIMAL-FORM SWEEP: `required` is DERIVED from a control, per row #
# --------------------------------------------------------------------------- #

MINIMAL_FORM_CAPTURE = "ld317-01-minimal-form-sweep.json"


def _sweep():
    return json.loads((CAPTURES / MINIMAL_FORM_CAPTURE).read_text(encoding="utf-8"))


def test_ld317_EVERY_row_carries_a_minimal_form_control_so_NONE_is_dispositioned_on_nobody_looked():
    """The guard the defect needed: a row with no property-less control is a row whose
    `required` flag is an assumption, which is exactly how `Progress` shipped wrong."""
    assert len(fa.FIELD_PROPERTY_SHAPES) == 24
    for ui_type, shape in fa.FIELD_PROPERTY_SHAPES.items():
        control = shape.minimal_form
        assert control.capture, ui_type
        assert (CAPTURES / control.capture).exists(), (ui_type, control.capture)
        assert control.path, ui_type
        assert control.msg, ui_type


def test_ld317_every_control_RESOLVES_INSIDE_ITS_OWN_CAPTURE_to_the_code_it_claims():
    """Mechanical, not narrative: the path is walked and the code compared. A registry row
    that invents an answer the capture does not carry reddens here."""
    for ui_type, shape in fa.FIELD_PROPERTY_SHAPES.items():
        blob = json.loads((CAPTURES / shape.minimal_form.capture).read_text(encoding="utf-8"))
        node = blob
        for step in shape.minimal_form.path:
            node = node[step]
        assert node == shape.minimal_form.code, (ui_type, node, shape.minimal_form.code)


def test_ld317_required_is_DERIVED_from_the_control_and_is_no_longer_a_settable_field():
    import dataclasses

    for ui_type, shape in fa.FIELD_PROPERTY_SHAPES.items():
        assert shape.required is (shape.minimal_form.code != 0), ui_type
    names = {f.name for f in dataclasses.fields(fa.FieldPropertyShape)}
    assert "required" not in names, "a hand-set `required` is the defect itself"
    assert "minimal_form" in names


def test_ld317_THE_SWEEP_the_five_kinds_that_refuse_a_property_less_create_are_the_measured_five():
    """`Progress` (the consumer's report) and `Currency` (the consumer's suspicion) are both
    in, and so are the two link kinds the 2026-07 zoo recorded as accepting one."""
    assert fa.REQUIRED_PROPERTY_KINDS == (
        "Currency", "DuplexLink", "Progress", "Rating", "SingleLink")


def test_ld317_PROGRESS_is_refused_LOCALLY_with_zero_calls_and_the_measured_shape_in_the_message():
    with pytest.raises(fa.UncapturedFieldPropertyError) as excinfo:
        fa.build_property("Progress")
    text = str(excinfo.value)
    assert "1254001" in text and "WrongRequestBody" in text
    assert MINIMAL_FORM_CAPTURE in text
    assert '"formatter": "0%"' in text and '"max": 100' in text and '"min": 0' in text
    assert "formatter, min, max" in text
    assert "Nothing was sent" in text


def test_ld317_CURRENCY_the_consumers_OTHER_suspect_is_refused_locally_too():
    with pytest.raises(fa.UncapturedFieldPropertyError) as excinfo:
        fa.build_property("Currency")
    text = str(excinfo.value)
    assert "1254001" in text and '"currency_code": "USD"' in text


def test_ld317_the_LINK_kinds_refuse_with_LARKS_OWN_code_not_a_borrowed_1254001():
    """The old refusal hard-coded `1254001 WrongRequestBody` into its own sentence. The link
    kinds answer something else entirely, and the message now quotes what was measured."""
    with pytest.raises(fa.UncapturedFieldPropertyError) as single:
        fa.build_property("SingleLink")
    assert "1254089" in str(single.value) and "LinkFieldPropertyError" in str(single.value)
    with pytest.raises(fa.UncapturedFieldPropertyError) as duplex:
        fa.build_property("DuplexLink")
    assert "1254092" in str(duplex.value)
    assert "DuplexLinkFieldPropertyError" in str(duplex.value)


def test_ld317_FORMULA_the_server_ACCEPTS_its_minimal_form_and_this_library_still_refuses_it():
    """The over-enforcement side of the same flag. `Formula`'s property-less create answers
    `code:0` — so `required` is now False for it — and the refusal a caller meets is LD-280's
    refutation, which is about a column that never computes, not about a body the server
    rejects. Two different sentences for two different facts."""
    assert fa.FIELD_PROPERTY_SHAPES["Formula"].required is False
    with pytest.raises(fa.RefutedFieldAuthoringError) as excinfo:
        fa.build_property("Formula")
    assert "COMPUTING" in str(excinfo.value)


def test_ld317_a_row_whose_control_says_ACCEPTED_still_builds_NO_property():
    for ui_type in ("Text", "Checkbox", "Phone", "Url", "Attachment", "CreatedUser"):
        assert fa.build_property(ui_type) is None, ui_type


def test_ld317_the_working_shape_in_each_refusal_is_the_body_the_capture_measured_ACCEPTED():
    """Not a suggestion and not a default — a quotation. Each refusing row's `working` text is
    byte-equal to the `property` of the follow-up the sweep recorded answering `code:0`."""
    sweep = _sweep()["observations"]
    for ui_type in fa.REQUIRED_PROPERTY_KINDS:
        follow_up = sweep[ui_type]["with_property"]
        assert follow_up["code"] == 0, ui_type
        working = fa.FIELD_PROPERTY_SHAPES[ui_type].minimal_form.working
        assert json.loads(working) == follow_up["request"]["property"], ui_type


def test_ld317_a_kind_whose_control_ACCEPTS_carries_no_working_shape_to_quote():
    for ui_type, shape in fa.FIELD_PROPERTY_SHAPES.items():
        if not shape.required:
            assert shape.minimal_form.working == "", ui_type


# --------------------------------------------------------------------------- #
# AC4 — the `required` prose is GENERATED, so the sweep cannot leave it stale    #
# --------------------------------------------------------------------------- #

def test_ac4_the_required_SENTENCE_is_generated_and_counts_the_table_it_describes():
    sentence = fa.REQUIRED_PROPERTY_SENTENCE
    assert str(len(fa.REQUIRED_PROPERTY_KINDS)) in sentence
    assert str(len(fa.FIELD_PROPERTY_SHAPES)) in sentence
    for ui_type in fa.REQUIRED_PROPERTY_KINDS:
        assert ui_type in sentence


def test_ac4_the_docstring_NAMES_NO_KIND_AND_NO_COUNT_so_it_cannot_drift_again():
    """The shipped docstring said *"Exactly one kind is: `Rating`"* while two rows carried the
    flag — the field that under-enforced also mis-described itself. The fix is not a better
    sentence: it is a docstring that states no countable fact at all and points at the
    generated one, so the next sweep cannot make it wrong."""
    import re

    doc = fa.FieldPropertyShape.__doc__
    bullet = doc.split("``required``")[1].split("* ``capture``")[0]
    for ui_type in fa.FIELD_PROPERTY_SHAPES:
        assert ui_type not in bullet, f"the bullet names {ui_type}; the table already does"
    assert not re.search(r"\b(one|two|three|four|five|\d+)\b", bullet), bullet
    assert "REQUIRED_PROPERTY_SENTENCE" in bullet
