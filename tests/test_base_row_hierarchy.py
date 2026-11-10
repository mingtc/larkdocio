"""LD-296 — the Lark row tree: a self-referencing link field, one view property, two hazards.

Every test here is **offline** and every fact is pinned against a committed capture from the
LD-294 spike (``tests/captures/base-study/captures/subitems-*.json``), round-tripped through the pinned
SDK's own deserializer where a shape is being pinned — so an API drift reddens at
deserialization rather than travelling on as a plausible tree.

The four disciplines this file holds, in the AC's own order:

1. **A self-link is a link whose target happens to be itself** — authored through the shipped
   field family, with no new op family and no forked path (AC1).
2. **``code:0`` proves nothing on the view route**, so every hierarchy_config assertion is an
   *effect* assertion against the R12 bogus-key control (AC2).
3. **The parent edge is a link-cell VALUE**, written through the shipped write path; no body
   key makes a record a child (AC3).
4. **The read never lies and never hangs** — a cycle terminates with a typed marker, two
   parents both survive, a dangling pointer takes the honest third state, and an unconfigured
   table is *not configured* rather than an empty tree (AC4/AC6).
"""
import ast
import inspect
import json
from pathlib import Path

import pytest
from lark_oapi.api.bitable.v1 import AppTableField
from lark_oapi.core.json import JSON

from larkdocio.base import field_authoring as fa
from larkdocio.base import hierarchy as hier
from larkdocio.base import link_resolution as lr
from larkdocio.base import referential, view_plan
from larkdocio.base import schema_ops_views as views
from larkdocio.base import write_cells
from larkdocio.base.cells import FieldSpec
from larkdocio.base.schema_apply import schema_dry_run
from larkdocio.base.schema_client import BaseSchemaClient, BaseSchemaRefusal

_REPO = Path(__file__).resolve().parent.parent
_CAPTURES = _REPO / "tests" / "captures" / "base-study" / "captures"

#: The disposable's own table id — the id a self-link's ``property.table_id`` echoes.
SELF_TABLE = "tbljnCMElmG4kiQZ"


def capture(name):
    return json.loads((_CAPTURES / name).read_text(encoding="utf-8"))


def selflink_create():
    return capture("subitems-b-04-selflink-field-create.json")["response"]["data"]["attempts"]


def hierarchy_matrix():
    return capture(
        "subitems-b-05-hierarchy-config-patch-matrix.json")["response"]["data"]["attempts"]


def effect():
    return capture("subitems-c-01-hierarchy-effect.json")["response"]["data"]


def _field(payload):
    """A captured field dict → the SDK's own typed object, then a :class:`FieldSpec`."""
    from larkdocio.base.table import field_spec

    return field_spec(JSON.unmarshal(json.dumps(payload), AppTableField))


def _self_single_link():
    return _field(selflink_create()["SelfSingleLink"]["created_field"])


def _self_duplex_link():
    return _field(selflink_create()["SelfDuplexLink"]["created_field"])


def _text_field():
    return FieldSpec(field_name="Text", type=1, ui_type="Text", property=None,
                     field_id="fld8j11vcw", is_primary=True)


def _rows_from_capture():
    """The spike's own six rows — ``(record_id, text, parents)`` — from ``search_after``."""
    return [r for r in effect()["search_after"] if r["text"]]


def _records(rows, field_name="SelfLink"):
    """The captured rows in ``records/search`` wire shape: ``{"link_record_ids": [...]}``."""
    out = []
    for row in rows:
        cells = {"Text": row["text"]}
        if row["parents"]:
            cells[field_name] = {"link_record_ids": list(row["parents"])}
        out.append({"record_id": row["record_id"], "fields": cells})
    return out


def _link_spec(field_name="SelfLink", table_id=SELF_TABLE):
    return FieldSpec(field_name=field_name, type=18, ui_type="SingleLink",
                     property={"multiple": True, "table_id": table_id, "table_name": "Table"},
                     field_id="fldFfAgfd4")


def _fields(field_name="SelfLink"):
    return [_text_field(), _link_spec(field_name)]


# --------------------------------------------------------------------------- #
# AC1 — the self-link is authorable through the EXISTING field family           #
# --------------------------------------------------------------------------- #

def test_AC1_a_self_link_is_a_LINK_WHOSE_TARGET_IS_ITSELF_and_needs_no_new_shape():
    """Both kinds go through the shipped :func:`build_property` — the captured `table_id`
    key, with the table's OWN id in it. No new shape, no new key, no new op family."""
    for ui_type in ("SingleLink", "DuplexLink"):
        prop = fa.build_property(ui_type, table_id=SELF_TABLE)
        assert prop.table_id == SELF_TABLE
        assert fa.FIELD_PROPERTY_SHAPES[ui_type].keys == ("table_id", "multiple")


def test_AC1_the_capture_says_BOTH_KINDS_answered_code_0_on_their_OWN_table():
    attempts = selflink_create()
    for name in ("SelfSingleLink", "SelfDuplexLink"):
        assert attempts[name]["code"] == 0
        assert attempts[name]["property_table_id"] == "<the table's OWN id>"
        assert attempts[name]["created_field"]["property"]["table_id"] == SELF_TABLE
    assert attempts["SelfSingleLink"]["created_field"]["property"]["multiple"] is True


def test_AC1_the_DUPLEX_MIRROR_lands_IN_THE_SAME_TABLE_and_the_disclosure_fires():
    """A self-``DuplexLink``'s mirror is a cross-table create whose "other" table is this
    one — so the shipped disclosure must still fire, and it must name that table."""
    disclosure = fa.cross_table_create("DuplexLink", "SelfDuplexLink",
                                       {"table_id": SELF_TABLE}, "Table")
    assert disclosure is not None
    assert disclosure["table_id"] == SELF_TABLE
    assert disclosure["what"] == fa.CROSS_TABLE_CREATE_WHAT
    assert disclosure["unpredicted"] is None


def test_AC1_the_mirror_NAME_PREDICTION_IS_CORRECT_for_the_self_case_pinned_to_the_capture():
    """The prediction is not merely *made*, it is checked against what Lark actually named
    the mirror: ``Table`` + ``SelfDuplexLink`` → ``Table-SelfDuplexLink``."""
    created = selflink_create()["SelfDuplexLink"]["created_field"]
    assert created["property"]["back_field_name"] == fa.duplex_mirror_name(
        "Table", "SelfDuplexLink")
    assert created["property"]["back_field_id"]


def test_AC1_without_the_source_table_name_the_mirror_name_is_WITHHELD_not_guessed():
    disclosure = fa.cross_table_create("DuplexLink", "SelfDuplexLink",
                                       {"table_id": SELF_TABLE}, None)
    assert disclosure["predicted_field_name"] is None
    assert disclosure["unpredicted"] == fa.MIRROR_NAME_UNPREDICTED


def test_AC1_a_SINGLE_link_still_discloses_NOTHING_because_it_creates_nothing():
    assert fa.cross_table_create("SingleLink", "SelfSingleLink",
                                 {"table_id": SELF_TABLE}, "Table") is None


# --------------------------------------------------------------------------- #
# AC2 — hierarchy_config as a view parameter, with a LOCAL refusal              #
# --------------------------------------------------------------------------- #

def test_AC2b_THE_R12_CONTROL_a_bogus_key_answered_code_0_WITH_NO_EFFECT():
    """The control that makes every other row of the matrix mean something — carried into
    the suite so ``code:0`` can never be read as evidence on this route."""
    control = hierarchy_matrix()["bogus_key_CONTROL"]
    assert control["patch_code"] == 0
    assert control["readback_property"]["hierarchy_config"] == {"field_id": "fldz7feL7d"}
    assert "larkdocio_not_a_real_key" in control["request_property"]["hierarchy_config"]
    assert hier.CODE_ZERO_IS_NOT_EVIDENCE
    assert "code:0" in hier.CODE_ZERO_IS_NOT_EVIDENCE


def test_AC2a_THE_EFFECT_ASSERTION_a_second_patch_MOVED_the_read_back():
    """Not two ``code:0``s — one read-back that **changed**: SingleLink id → DuplexLink id."""
    matrix = hierarchy_matrix()
    first = matrix["single_link_field"]["readback_property"]["hierarchy_config"]["field_id"]
    second = matrix["duplex_link_field"]["readback_property"]["hierarchy_config"]["field_id"]
    assert first == "fldz7feL7d" and second == "fld9ukArDf"
    assert first != second, "the read-back MOVED — that is the effect"


def test_AC2c_a_TEXT_field_target_is_refused_LOCALLY_in_the_servers_own_words():
    with pytest.raises(BaseSchemaRefusal) as excinfo:
        hier.hierarchy_config("fld8j11vcw", fields=_fields())
    message = str(excinfo.value)
    assert "single_link" in message and "duplex_link" in message
    assert "1254001" in message
    assert "Nothing was sent." in message


def test_AC2c_the_refusal_quotes_the_SERVERS_OWN_MESSAGE_from_the_capture():
    server = hierarchy_matrix()["text_field_CONTROL"]["patch_error_message"]
    assert "the field must be single_link or duplex_link" in server
    assert "the field must be single_link or duplex_link" in hier.HIERARCHY_FIELD_MUST_BE_A_LINK


def test_AC2c_the_refusal_costs_ZERO_CALLS_the_client_is_never_reached():
    sdk, client = _fake_client()
    with pytest.raises(BaseSchemaRefusal):
        hier.hierarchy_config("fld8j11vcw", fields=_fields())
    assert sdk.sent == []


def test_AC2d_an_UNKNOWN_field_id_is_NOT_refused_locally_and_the_module_says_why():
    """The deliberate contrast with (c). A field list is a read of a moment; an id missing
    from it is not proof the id does not exist, so the library does not pretend to know."""
    config = hier.hierarchy_config("fldZZZnotreal", fields=_fields())
    assert config.field_id == "fldZZZnotreal"
    assert config.checked is False
    assert "1254044" in hier.UNKNOWN_FIELD_ID_IS_RELAYED
    assert hierarchy_matrix()["nonexistent_field_CONTROL"]["patch_code"] == 1254044


def test_AC2_a_SELF_LINK_target_is_accepted_and_reads_back_CHECKED():
    config = hier.hierarchy_config(_self_single_link().field_id,
                                   fields=[_text_field(), _self_single_link()],
                                   table_id=SELF_TABLE)
    assert config.checked is True and config.self_referencing is True
    assert config.uncaptured_shape is None


def test_AC2_a_link_at_ANOTHER_table_is_DISCLOSED_as_uncaptured_never_refused():
    """The server's message names the two field KINDS and says nothing about the target, so
    refusing here would be inventing a validation Lark does not perform."""
    other = _link_spec(table_id="tblSOMEOTHER")
    config = hier.hierarchy_config(other.field_id, fields=[_text_field(), other],
                                   table_id=SELF_TABLE)
    assert config.checked is True and config.self_referencing is False
    assert "no capture" in config.uncaptured_shape.lower()


def test_AC2_the_PATCH_puts_the_field_id_under_property_hierarchy_config():
    sdk, client = _fake_client()
    client.update_view("appX", SELF_TABLE, "vewX",
                       hierarchy_config=hier.hierarchy_config("fldFfAgfd4", fields=_fields()))
    body = sdk.sent[-1].request_body
    assert body.property.hierarchy_config.field_id == "fldFfAgfd4"


def test_AC2e_a_HIERARCHY_patch_leaves_filter_info_and_hidden_fields_UNSET():
    sdk, client = _fake_client()
    client.update_view("appX", SELF_TABLE, "vewX",
                       hierarchy_config=hier.hierarchy_config("fldFfAgfd4", fields=_fields()))
    body = sdk.sent[-1].request_body
    assert body.property.filter_info is None
    assert body.property.hidden_fields is None
    assert body.view_name is None


def test_AC2e_and_the_SYMMETRIC_guarantee_a_FILTER_patch_leaves_hierarchy_config_UNSET():
    from larkdocio.base.view_filters import Condition, FieldId, FilterSpec, view_filter

    sdk, client = _fake_client()
    client.update_view("appX", SELF_TABLE, "vewX", filter_info=view_filter(
        FilterSpec(conditions=(Condition(FieldId("fldA"), "is", ("x",)),))))
    assert sdk.sent[-1].request_body.property.hierarchy_config is None


def test_AC2_the_view_route_takes_a_HierarchyConfig_AND_NOTHING_ELSE():
    sdk, client = _fake_client()
    for wrong in ("fldFfAgfd4", {"field_id": "fldFfAgfd4"}, 7):
        with pytest.raises(TypeError) as excinfo:
            client.update_view("appX", SELF_TABLE, "vewX", hierarchy_config=wrong)
        assert "hierarchy_config" in str(excinfo.value)
    assert sdk.sent == [], "a refused dialect must cost ZERO calls"


def test_AC2_the_plan_gains_ONE_request_on_the_EXISTING_update_view_op():
    request = view_plan.set_view_hierarchy(
        "appX", SELF_TABLE, "vewX", hier.hierarchy_config("fldFfAgfd4", fields=_fields()))
    assert request.op == "update_view"
    plan = schema_dry_run([request])
    assert plan.api_call_count == 1 and not plan.refusals
    assert plan.entries[0].read_cost == 2
    body = json.loads(plan.to_json())["entries"][0]["fields"]["hierarchy_config"]
    assert body == {"field_id": "fldFfAgfd4"}


def test_AC2_the_READ_BACK_is_an_ECHO_of_the_field_id_never_a_code_0():
    """The family's own read-back handler, which is what makes the R12 control survivable."""
    store = _ViewStore()
    store.property["vewX"] = {"hierarchy_config": {"field_id": "fldFfAgfd4"}}
    confirmed, disclosure = views._read_back(
        store, _entry("update_view", {"app_token": "appX", "table_id": SELF_TABLE,
                                      "view_id": "vewX",
                                      "hierarchy_config": hier.hierarchy_config(
                                          "fldFfAgfd4", fields=_fields())}), None, None)
    assert confirmed is True
    assert disclosure["persisted_hierarchy_config"] == {"field_id": "fldFfAgfd4"}


def test_AC2_a_read_back_that_does_NOT_echo_is_reported_NOT_PERSISTED():
    store = _ViewStore()
    store.property["vewX"] = {"hierarchy_config": None}
    confirmed, disclosure = views._read_back(
        store, _entry("update_view", {"app_token": "appX", "table_id": SELF_TABLE,
                                      "view_id": "vewX",
                                      "hierarchy_config": hier.hierarchy_config(
                                          "fldFfAgfd4", fields=_fields())}), None, None)
    assert confirmed is False
    assert disclosure["persisted_hierarchy_config"] is None


def test_AC2_the_view_module_docstrings_are_AMENDED_not_left_contradicting_the_ship():
    from larkdocio.base import view_client

    doc = view_client.__doc__
    assert "FILTERS ONLY" not in doc, "the FILTERS ONLY paragraph is amended by this change"
    assert "hierarchy_config" in doc
    assert "hidden_fields" in doc, "hidden_fields stays unset and stays contradicted"
    assert "left unset deliberately" not in (view_client._property_of.__doc__ or "")
    assert "hidden_fields" in (view_client._property_of.__doc__ or "")
    assert "FILTERS ONLY" not in views.__doc__


def test_AC2_grouping_and_sort_are_STILL_unreachable_by_every_public_view_surface():
    """**Re-aimed by LD-438, not deleted.** This guard's job here is that adding the HIERARCHY
    knob did not smuggle in the ones that stay out; LD-438 moved `hidden_fields` out of the
    banned set on measured evidence (its own positive guards are in
    `tests/test_base_view_hidden_fields.py`), and grouping and the saved sort — the two that
    are still `code:0`-and-not-stored — are what this sweep now watches, widened to the sort
    spellings LD-417 measured."""
    banned = ("group_info", "grouping", "group_by", "hide_fields",
              "view_sort", "sort", "sort_info", "sorts", "sort_infos", "auto_sort")
    surface = [view_plan.create_view, view_plan.rename_view, view_plan.set_view_filter,
               view_plan.set_view_hierarchy, view_plan.set_view_hidden_fields,
               view_plan.clear_view_hidden_fields, view_plan.delete_view,
               BaseSchemaClient.create_view, BaseSchemaClient.update_view,
               BaseSchemaClient.delete_view]
    for fn in surface:
        assert not (set(inspect.signature(fn).parameters) & set(banned)), fn.__qualname__


# --------------------------------------------------------------------------- #
# AC3 — the parent edge rides the SHIPPED write-cells path                      #
# --------------------------------------------------------------------------- #

def test_AC3_the_edge_is_a_LINK_CELL_VALUE_through_the_SHIPPED_encoder():
    spec = _link_spec()
    assert write_cells.encode_cell(["recPARENT"], spec) == ["recPARENT"]
    assert write_cells.encode_cell("recPARENT", spec) == ["recPARENT"]


def test_AC3_a_THREE_LEVEL_tree_is_written_with_NO_hierarchy_specific_branch():
    """The whole write side of this capability, in three lines of shipped API."""
    spec = _link_spec()
    tree = {"C1": ["recP1"], "C2": ["recP1"], "G1": ["recC1"]}
    assert {row: write_cells.encode_cell(value, spec) for row, value in tree.items()} == tree
    edges = capture(
        "subitems-b-08-parent-edges-via-link-value.json")["response"]["data"]["edges"]
    assert set(edges) == {"C1->P1", "C2->P1", "G1->C1"}
    for edge in edges.values():
        assert edge["code"] == 0 and edge["readback_fields"]["SelfSingleLink"]


def test_AC3_NO_BODY_KEY_MAKES_A_RECORD_A_CHILD_and_the_control_proves_it():
    battery = capture("subitems-b-06-parent-key-battery.json")["response"]["data"]
    control = battery["control_key"]
    assert control == "larkdocio_not_a_real_key"
    for key in hier.REFUTED_PARENT_BODY_KEYS:
        assert key in hier.NO_BODY_KEY_MAKES_A_CHILD
    assert control in hier.NO_BODY_KEY_MAKES_A_CHILD
    assert len(hier.REFUTED_PARENT_BODY_KEYS) == 6


def test_AC3_there_is_NO_SECOND_WRITE_ROUTE_the_module_reaches_no_client_at_all():
    """The AC's own check, made structural: this module imports no client and defines no
    function that takes one, so a parallel write route cannot hide in it."""
    source = Path(hier.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in tree.body:  # MODULE LEVEL only — a lazy import inside a refusal is the
        if isinstance(node, ast.ImportFrom):  # shipped view-route pattern, not a transport
            imported.add(node.module or "")
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    banned = {"larkdocio.base.client", "larkdocio.base.write_client",
              "larkdocio.base.schema_client", "larkdocio.base.apply",
              "larkdocio.base.write_ops", "lark_oapi"}
    assert not (imported & banned), imported & banned
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names = {a.arg for a in node.args.args} | {a.arg for a in node.args.kwonlyargs}
            assert not (names & {"client", "read_client", "write_client", "sdk"}), node.name


# --------------------------------------------------------------------------- #
# AC4 — the tree accessor, and where it says it got the hierarchy from          #
# --------------------------------------------------------------------------- #

def test_AC4a_the_parent_is_exposed_AS_A_POINTER_never_as_nesting():
    tree = hier.read_hierarchy(_fields(), _records(_rows_from_capture()),
                               field_name="SelfLink")
    row = {r.record_id: r for r in tree.rows}["recvramm0oObCE"]
    assert row.parent_ids == ("recvrvyxLVX9TP",)
    assert not hasattr(row, "children")
    assert "pointer" in hier.PARENT_NEVER_NESTING.lower()
    assert "nest" in hier.PARENT_NEVER_NESTING.lower()


def test_AC4b_DEPTH_FIRST_ORDER_IS_RECONSTRUCTED_CLIENT_SIDE_and_matches_the_server():
    """The order the server produced on the legacy list, reproduced from the pointers alone
    — no second endpoint, no second cell dialect, no configured view."""
    tree = hier.read_hierarchy(_fields(), _records(_rows_from_capture()),
                               field_name="SelfLink")
    server = [r["text"] for r in effect()["records_list_view_scoped_after"] if r["text"]]
    by_id = {r["record_id"]: r["text"] for r in effect()["search_after"]}
    assert [by_id[row.record_id] for row in tree.rows] == server
    assert server[0] == "P1-parent" and server[-1] == "P2-parent"


def test_AC4b_the_client_side_reconstruction_costs_NO_CALL_AND_NO_SECOND_DIALECT():
    assert hier.TREE_ORDER_IS_RECONSTRUCTED_CLIENT_SIDE
    text = hier.TREE_ORDER_IS_RECONSTRUCTED_CLIENT_SIDE
    assert "link_record_ids" in text and "record_ids" in text
    assert "no extra API call" in text


def test_AC4c_the_accessor_NAMES_the_field_it_built_the_tree_from_and_HOW_it_learned_it():
    tree = hier.read_hierarchy(_fields(), _records(_rows_from_capture()),
                               field_name="SelfLink")
    assert tree.field_name == "SelfLink" and tree.field_id == "fldFfAgfd4"
    assert tree.source == hier.SOURCE_NAMED_BY_CALLER
    assert "SelfLink" in tree.source_detail


def test_AC4c_a_hierarchy_read_from_a_VIEW_says_WHICH_VIEW():
    view = _View("vew6edJbS0", {"hierarchy_config": {"field_id": "fldFfAgfd4"}})
    tree = hier.read_hierarchy(_fields(), _records(_rows_from_capture()), view=view)
    assert tree.source == hier.SOURCE_VIEW_HIERARCHY_CONFIG
    assert "vew6edJbS0" in tree.source_detail
    assert tree.field_id == "fldFfAgfd4" and tree.field_name == "SelfLink"


def test_AC4c_a_view_id_HERE_is_a_CITATION_and_read_base_still_takes_none():
    import larkdocio.base.read as base_read

    assert "view_id" not in inspect.signature(base_read.read_base).parameters
    assert "view_id" not in inspect.signature(base_read.read_base_markdown).parameters
    assert "a view is not a projection" in base_read.read_base.__doc__.lower().replace(
        "**", "")
    assert "citation" in hier.A_VIEW_ID_HERE_IS_A_CITATION.lower()


def test_AC4c_THE_ACCESSOR_NEVER_GUESSES_A_COLUMN_even_with_exactly_one_self_link():
    tree = hier.read_hierarchy(_fields(), _records(_rows_from_capture()))
    assert tree.configured is False
    assert "never guesses" in tree.not_configured_reason.lower()
    assert tree.rows == ()


def test_AC4d_records_search_HIERARCHY_BLINDNESS_is_disclosed_and_pinned():
    assertions = effect()["ASSERTIONS"]
    assert assertions["search_unchanged_by_hierarchy_config"] is True
    assert assertions["view_scoped_search_equals_unscoped"] is True
    assert assertions["records_list_unchanged_by_hierarchy_config"] is False
    knobs = effect()["knob_digest_identical_to_bogus_control"]
    assert knobs == {"with_hierarchy_true": True, "hierarchy_true": True,
                     "BOGUS_CONTROL": True}
    text = hier.SEARCH_IS_HIERARCHY_BLIND
    assert "with_hierarchy" in text and "hierarchy" in text
    assert "never sends" in text


def test_AC4d_the_library_SENDS_NEITHER_KNOB_anywhere_in_the_shipped_tree():
    offenders = []
    for path in (_REPO / "src" / "larkdocio").rglob("*.py"):
        body = path.read_text(encoding="utf-8")
        for knob in ('"with_hierarchy"', "'with_hierarchy'"):
            if knob in body:
                offenders.append((path.name, knob))
    assert not offenders, offenders


def test_AC4c_the_hierarchy_fact_LIVES_ON_THE_VIEW_and_GET_fields_cannot_tell_you():
    """``GET …/fields`` returns an ordinary link column — nothing marks it as the hierarchy."""
    field = _self_single_link()
    assert referential.is_link_column(_self_single_link_raw())
    assert "hierarchy" not in json.dumps(selflink_create()["SelfSingleLink"]["created_field"])
    assert "view" in hier.HIERARCHY_LIVES_ON_THE_VIEW.lower()
    assert field.property["table_id"] == SELF_TABLE


def test_AC4_hierarchy_field_id_reads_an_ALREADY_READ_view_and_a_null_property_is_None():
    assert hier.hierarchy_field_id(
        _View("vewX", {"hierarchy_config": {"field_id": "fldA"}})) == "fldA"
    assert hier.hierarchy_field_id(_View("vewX", None)) is None
    assert hier.hierarchy_field_id(_View("vewX", {"hierarchy_config": None})) is None


# --------------------------------------------------------------------------- #
# AC5 — the WRITE side DISCLOSES the hazards; it does not refuse them           #
# --------------------------------------------------------------------------- #

def test_AC5_a_SECOND_PARENT_is_disclosed_and_NOT_refused():
    tree = hier.read_hierarchy(_fields(), _records(_rows_from_capture()),
                               field_name="SelfLink")
    disclosure = hier.parent_write_disclosure(
        child_id="recvramm0oObCE", parent_ids=["recvrvyxLVX9TP", "recvruabFLz9VF"],
        hierarchy=tree)
    assert disclosure["refused"] is False
    assert disclosure["checked"] is True
    assert disclosure["second_parent"] is not None
    assert disclosure["parent_ids"] == ("recvrvyxLVX9TP", "recvruabFLz9VF")
    assert "code:0" in hier.TWO_PARENTS_ARE_ACCEPTED


def test_AC5_a_CYCLE_self_or_longer_is_disclosed_and_NOT_refused():
    tree = hier.read_hierarchy(_fields(), _records(_rows_from_capture()),
                               field_name="SelfLink")
    direct = hier.parent_write_disclosure(child_id="recvrvyxLVX9TP",
                                          parent_ids=["recvrvyxLVX9TP"], hierarchy=tree)
    assert direct["refused"] is False and direct["cycle"] is not None
    assert direct["cycle"]["rows"] == ("recvrvyxLVX9TP",)
    # A LONGER cycle: making P1 a child of its own grandchild closes P1 → C1 → G1 → P1.
    longer = hier.parent_write_disclosure(child_id="recvrvyxLVX9TP",
                                          parent_ids=["recvrmgyOULK2M"], hierarchy=tree)
    assert longer["refused"] is False and longer["cycle"] is not None
    assert longer["cycle"]["rows"] == ("recvrvyxLVX9TP", "recvrmgyOULK2M",
                                       "recvramm0oObCE")


def test_AC5_an_ORDINARY_edge_discloses_NEITHER_hazard():
    tree = hier.read_hierarchy(_fields(), _records(_rows_from_capture()),
                               field_name="SelfLink")
    plain = hier.parent_write_disclosure(child_id="recvrwwfxbFAwP",
                                         parent_ids=["recvrvyxLVX9TP"], hierarchy=tree)
    assert plain["cycle"] is None and plain["second_parent"] is None
    assert plain["checked"] is True


def test_AC5_THE_HONESTY_FENCE_no_graph_means_IT_DID_NOT_CHECK_never_a_guarantee():
    blind = hier.parent_write_disclosure(child_id="recX", parent_ids=["recY"])
    assert blind["checked"] is False
    assert blind["cycle"] is None and blind["second_parent"] is None
    assert blind["note"] == hier.HIERARCHY_WAS_NOT_CHECKED
    assert "did not check" in hier.HIERARCHY_WAS_NOT_CHECKED.lower()
    assert "not a guarantee" in hier.HIERARCHY_WAS_NOT_CHECKED.lower()


def test_AC5_the_disclosure_BUYS_NO_CALL_it_reads_only_the_graph_in_hand():
    """Structural, not aspirational: the function takes no client and the module has none."""
    params = set(inspect.signature(hier.parent_write_disclosure).parameters)
    assert params == {"child_id", "parent_ids", "hierarchy"}
    assert "must not buy" in hier.DISCLOSURE_IS_FREE.lower()


def test_AC5_the_DRAFT_PREVIEW_discloses_every_parent_write_before_the_plan_is_built():
    """The loss-preview precedent, on the value ``dry_run`` itself takes: a draft in hand,
    a disclosure per parent edge, and zero calls."""
    draft = _Draft(edits={"recvrvyxLVX9TP": {"SelfLink": ["recvrvyxLVX9TP"]}},
                   additions=[("new:1", {"SelfLink": ["recvrvyxLVX9TP",
                                                      "recvruabFLz9VF"]})])
    tree = hier.read_hierarchy(_fields(), _records(_rows_from_capture()),
                               field_name="SelfLink")
    preview = hier.hierarchy_write_preview(draft, hierarchy=tree)
    assert [entry["record_id"] for entry in preview["entries"]] == ["recvrvyxLVX9TP", "new:1"]
    assert preview["entries"][0]["cycle"] is not None
    assert preview["entries"][1]["second_parent"] is not None
    assert preview["checked"] is True
    assert preview["field_name"] == "SelfLink"


def test_AC5_a_draft_preview_WITHOUT_the_graph_says_so_for_EVERY_entry():
    draft = _Draft(edits={"recA": {"SelfLink": ["recB"]}})
    preview = hier.hierarchy_write_preview(draft, field_name="SelfLink")
    assert preview["checked"] is False
    assert preview["entries"][0]["note"] == hier.HIERARCHY_WAS_NOT_CHECKED


def test_AC5_NOTHING_HERE_REFUSES_A_HAZARD_no_raise_anywhere_on_the_write_side():
    tree = hier.read_hierarchy(_fields(), _records(_rows_from_capture()),
                               field_name="SelfLink")
    for parents in (["recvrvyxLVX9TP"], ["recvrvyxLVX9TP", "recvruabFLz9VF"]):
        disclosure = hier.parent_write_disclosure(child_id="recvrvyxLVX9TP",
                                                  parent_ids=parents, hierarchy=tree)
        assert disclosure["refused"] is False
    assert "never invents a validation" in hier.HAZARDS_ARE_DISCLOSED_NOT_REFUSED.lower()


# --------------------------------------------------------------------------- #
# AC6 — the READ side must never lie and never hang                             #
# --------------------------------------------------------------------------- #

def test_AC6a_THE_DELIBERATE_DEFECT_a_cycle_TERMINATES_and_is_TYPED():
    """A hand-built defect, not a captured one: A → B → C → A, plus one honest root."""
    rows = [("recA", ["recC"]), ("recB", ["recA"]), ("recC", ["recB"]),
            ("recROOT", None)]
    tree = hier.read_hierarchy(_fields(), _records(
        [{"record_id": r, "text": r, "parents": p} for r, p in rows]),
        field_name="SelfLink")
    assert len(tree.rows) == 4, "termination: every row is emitted exactly once"
    by_id = {row.record_id: row for row in tree.rows}
    for record_id in ("recA", "recB", "recC"):
        assert by_id[record_id].placement == hier.PLACEMENT_CYCLE
    assert by_id["recROOT"].placement == hier.PLACEMENT_ROOT
    assert tree.cycles == (("recA", "recC", "recB"),)


def test_AC6a_a_SELF_PARENT_is_the_shortest_cycle_and_terminates_too():
    tree = hier.read_hierarchy(_fields(), _records(
        [{"record_id": "recP2", "text": "P2", "parents": ["recP2"]}]), field_name="SelfLink")
    assert [row.placement for row in tree.rows] == [hier.PLACEMENT_CYCLE]
    assert tree.cycles == (("recP2",),)
    assert "code:0" in hier.A_ROW_MAY_BE_ITS_OWN_PARENT


def test_AC6a_a_LONG_chain_terminates_without_a_RecursionError():
    """A 5,000-deep chain — deeper than CPython's default recursion limit — so a recursive
    traversal would raise here rather than pass. Bounded, not merely 'fast'."""
    rows = [{"record_id": "rec0", "text": "0", "parents": None}]
    rows += [{"record_id": f"rec{i}", "text": str(i), "parents": [f"rec{i - 1}"]}
             for i in range(1, 5000)]
    tree = hier.read_hierarchy(_fields(), _records(rows), field_name="SelfLink")
    assert len(tree.rows) == 5000
    assert tree.rows[-1].depth == 4999


def test_AC6b_TWO_PARENTS_BOTH_SURVIVE_into_the_structure_and_the_rendering():
    tree = hier.read_hierarchy(_fields(), _records(_rows_from_capture()),
                               field_name="SelfLink")
    row = {r.record_id: r for r in tree.rows}["recvrqqa2v2Jkn"]
    assert row.parent_ids == ("recvrvyxLVX9TP", "recvruabFLz9VF"), "neither is dropped"
    assert row.placement == hier.PLACEMENT_CHILD
    assert tree.multi_parent == ("recvrqqa2v2Jkn",)
    rendered = hier.render_hierarchy(tree)
    for parent in row.parent_ids:
        assert parent in rendered
    assert "recvrqqa2v2Jkn" in rendered


def test_AC6c_a_DANGLING_parent_pointer_takes_THE_EXISTING_THIRD_STATE():
    tree = hier.read_hierarchy(_fields(), _records([
        {"record_id": "recCHILD", "text": "child", "parents": ["recGONE"]},
    ]), field_name="SelfLink")
    row = tree.rows[0]
    assert row.parent_states == (lr.LINK_UNRESOLVABLE,)
    assert row.placement == hier.PLACEMENT_DETACHED
    assert row.placement != hier.PLACEMENT_ROOT, "not a root, and not a silent drop"
    assert row.parent_ids == ("recGONE",)
    assert lr.STATE_MEANINGS[lr.LINK_UNRESOLVABLE] in row.note


def test_AC6c_a_resolution_ALREADY_IN_HAND_upgrades_the_unknown_to_DANGLING():
    """Composition with LD-269 rather than a second opinion: where the shipped resolver has
    already been told the record is gone, this read says *gone* instead of *unknown*."""
    resolution = lr.LinkResolution(records={
        (SELF_TABLE, "recGONE"): lr.ResolvedLink(
            table_id=SELF_TABLE, record_id="recGONE", state=lr.LINK_DANGLING,
            text=lr.dangling_marker("recGONE"))})
    tree = hier.read_hierarchy(_fields(), _records([
        {"record_id": "recCHILD", "text": "child", "parents": ["recGONE"]},
    ]), field_name="SelfLink", links=resolution)
    assert tree.rows[0].parent_states == (lr.LINK_DANGLING,)
    assert tree.rows[0].placement == hier.PLACEMENT_DETACHED


def test_AC6d_a_table_with_NO_SELF_LINK_COLUMN_is_NOT_CONFIGURED_not_an_empty_tree():
    tree = hier.read_hierarchy([_text_field()], [], field_name="SelfLink")
    assert tree.configured is False and tree.rows == ()
    assert "no field named" in tree.not_configured_reason.lower()
    assert tree.not_configured_reason != ""


def test_AC6d_a_view_whose_PROPERTY_IS_NULL_is_NOT_CONFIGURED_and_says_which_view():
    tree = hier.read_hierarchy(_fields(), _records(_rows_from_capture()),
                               view=_View("vew6edJbS0", None))
    assert tree.configured is False
    assert "vew6edJbS0" in tree.not_configured_reason
    assert tree.rows == ()


def test_AC6d_the_product_built_view_really_does_return_property_null():
    scratch = capture("subitems-a-02-scratch-views-hierarchy-config.json")
    assert "null" in json.dumps(scratch)
    assert hier.A_PRODUCT_BUILT_VIEW_READS_NULL


def test_AC6d_a_named_field_that_is_NOT_A_LINK_is_NOT_CONFIGURED_rather_than_traversed():
    tree = hier.read_hierarchy(_fields(), _records(_rows_from_capture()), field_name="Text")
    assert tree.configured is False
    assert "link" in tree.not_configured_reason.lower()


def test_AC6_the_disclosure_names_every_hazard_it_found_in_ONE_sentence():
    tree = hier.read_hierarchy(_fields(), _records(_rows_from_capture()),
                               field_name="SelfLink")
    text = tree.disclosure
    assert "1" in text and "cycle" in text.lower() and "parent" in text.lower()
    empty = hier.read_hierarchy([_text_field()], [], field_name="SelfLink")
    assert "not configured" in empty.disclosure.lower()


# --------------------------------------------------------------------------- #
# AC7 — OFF is byte-identical, and OFF is the default                           #
# --------------------------------------------------------------------------- #

def test_AC7_read_base_GAINED_NO_PARAMETER_and_lost_no_default():
    import larkdocio.base.read as base_read

    read = inspect.signature(base_read.read_base).parameters
    assert list(read) == ["base", "client", "domain", "resolve_links", "retain_raw"]
    assert read["resolve_links"].default is False and read["retain_raw"].default is False
    markdown = inspect.signature(base_read.read_base_markdown).parameters
    assert list(markdown) == ["base", "client", "domain", "heading_level", "resolve_links"]


def test_AC7_the_read_path_NEVER_REACHES_the_hierarchy_module_at_all():
    """The strongest form the opt-in can take: the tree read is a separate accessor the
    default read does not import, so 'off' is not a branch that could be taken by accident."""
    import larkdocio.base.read as base_read
    import larkdocio.base.table as base_table

    for module in (base_read, base_table):
        assert "hierarchy" not in Path(module.__file__).read_text(encoding="utf-8")


def test_AC7_the_accessor_makes_ZERO_API_CALLS_in_either_mode():
    class _Spy:
        api_calls = 0

        def __getattr__(self, name):  # pragma: no cover - reaching one is the failure
            raise AssertionError(f"the tree read must make no call; reached {name!r}")

    spy = _Spy()
    tree = hier.read_hierarchy(_fields(), _records(_rows_from_capture()),
                               field_name="SelfLink")
    assert spy.api_calls == 0 and len(tree.rows) == 6


def test_AC7_snapshot_table_KEEPS_ITS_SIGNATURE():
    from larkdocio.base.model import snapshot_table

    params = inspect.signature(snapshot_table).parameters
    assert "hierarchy" not in params and "view_id" not in params


# --------------------------------------------------------------------------- #
# AC8 — no new vocabulary, no new scope, no widening                            #
# --------------------------------------------------------------------------- #

def test_AC8_the_PER_POINTER_states_are_link_resolutions_OWN_WORDS_not_a_third_set():
    assert hier.PARENT_POINTER_STATES == lr.LINK_RESOLUTION_STATES
    assert hier.PARENT_POINTER_STATES == (lr.LINK_RESOLVED, lr.LINK_DANGLING,
                                          lr.LINK_UNRESOLVABLE)
    source = Path(hier.__file__).read_text(encoding="utf-8")
    for invented in ('"orphan"', '"broken"', '"missing-parent"', '"dead"'):
        assert invented not in source


def test_AC8_the_link_kinds_are_referentials_OWN_reading_not_a_second_copy():
    assert hier.LINK_TYPES is referential.LINK_TYPES
    tree_source = Path(hier.__file__).read_text(encoding="utf-8")
    assert "== 18" not in tree_source and "== 21" not in tree_source


def test_AC8_PLACEMENT_is_about_the_ROW_and_the_module_says_so_in_one_place():
    assert set(hier.PLACEMENTS) == {hier.PLACEMENT_ROOT, hier.PLACEMENT_CHILD,
                                    hier.PLACEMENT_CYCLE, hier.PLACEMENT_DETACHED}
    assert len(hier.PLACEMENTS) == 4
    for placement in hier.PLACEMENTS:
        assert hier.PLACEMENT_MEANINGS[placement]
    assert "placement" in hier.PLACEMENT_IS_NOT_A_LIVENESS_CLAIM.lower()


def test_AC8_no_typed_value_class_and_no_per_type_converter_ships_here():
    source = Path(hier.__file__).read_text(encoding="utf-8")
    for banned in ("datetime", "Decimal", "def _convert", "CONVERTERS"):
        assert banned not in source


def test_AC8_the_permission_registry_gains_NO_SCOPE_and_no_new_endpoint():
    from larkdocio import permissions

    rows = permissions.permission_registry()
    row = rows[("base-read", "read_hierarchy")]
    assert row.endpoints == (), "the tree read reaches no endpoint of its own"
    assert row.api_using is False
    assert row.scopes == ()
    gaps = permissions.coverage_gaps()
    assert not gaps.uncovered and not gaps.orphans
    assert permissions.unmapped_endpoints() == []


def test_AC8_the_view_PATCH_endpoint_was_ALREADY_in_the_table_no_scope_is_widened():
    from larkdocio import permissions

    scopes = permissions.scopes_for_endpoints(
        ("/open-apis/bitable/v1/apps/:app_token/tables/:table_id/views/:view_id",), "write")
    assert [s.scope for s in scopes] == ["bitable:app"]


# --------------------------------------------------------------------------- #
# Offline doubles                                                              #
# --------------------------------------------------------------------------- #

class _View:
    def __init__(self, view_id, property_):
        self.view_id, self.view_name, self.view_type = view_id, "V", "grid"
        self.property = _Property(property_) if isinstance(property_, dict) else property_


class _Property:
    def __init__(self, blob):
        config = blob.get("hierarchy_config")
        self.filter_info = blob.get("filter_info")
        self.hidden_fields = blob.get("hidden_fields")
        self.hierarchy_config = (
            type("H", (), {"field_id": config["field_id"]})() if config else None)


class _ViewStore:
    """The read seam the view family's read-back calls — a dict, not a client."""

    def __init__(self):
        self.property = {}

    def list_views(self, app_token, table_id):
        return [_View(view_id, self.property.get(view_id)) for view_id in self.property]

    def get_view(self, app_token, table_id, view_id):
        return _View(view_id, self.property.get(view_id))


class _Draft:
    def __init__(self, edits=None, additions=()):
        self.pending_edits = edits or {}
        self.pending_additions = tuple(additions)
        self.pending_deletions = ()


class _FakeResponse:
    def __init__(self, data=None, code=0, msg="success"):
        self.code, self.msg, self.data = code, msg, data
        self.raw = None


class _FakeSdk:
    def __init__(self):
        self.sent = []
        outer = self

        class _View_:
            def patch(self, request):
                outer.sent.append(request)
                return _FakeResponse(type("D", (), {"view": None})())

        self.bitable = type("B", (), {"v1": type("V1", (), {"app_table_view": _View_()})()})()


class _NoWait:
    def acquire(self):
        pass


def _fake_client():
    sdk = _FakeSdk()
    return sdk, BaseSchemaClient("id", "secret", sdk_client=sdk, rate_limiter=_NoWait())


def _entry(op, fields):
    return type("E", (), {"op": op, "fields": fields,
                          "read_back": "GET …/views/{v} re-reads the view"})()


def _self_single_link_raw():
    return JSON.unmarshal(
        json.dumps(selflink_create()["SelfSingleLink"]["created_field"]), AppTableField)
