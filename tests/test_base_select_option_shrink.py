"""LD-462 — an option SHRINK is a destructive write, gated exactly as ``delete_field`` is.

**The hole LD-339 left open.** LD-339 fenced the two shapes it measured: an options-carrying
update with **no ids anywhere** (every id re-minted, every cell orphaned) and an update with **no
option set at all** (the set emptied outright). Both are decided on the request's own shape. What
neither shape covers is the body that carries **every surviving option with its id** and simply
**omits one** — the shrink. LD-339's fence passes it, the server accepts it, and the cells that
held the dropped option are destroyed with `outcome == 'applied'`, no preview and no consent.

Measured on a harness-created disposable —
``tests/captures/base-study/captures/ld462-01-select-option-shrink.json``, four arms, three records each:

* **SingleSelect, populated option dropped** — 2 of 3 cells read back EMPTY, the survivor
  untouched;
* **SingleSelect, one option RENAMED with every id kept** — every cell survives and the renamed
  cell reads back under the new name (the cell is anchored to the id): **measured
  non-destructive**;
* **MultiSelect, populated option dropped** — a cell holding ``[B, C]`` reads back ``[B]`` and a
  cell holding ``[C]`` alone reads back EMPTY: values are destroyed per cell;
* **SingleSelect, option no record holds dropped** — every cell byte-identical.

So this file pins one doctrine over one blast radius: the shrink rides ``delete_field``'s own
``read_client=`` requirement, ``loss_preview``, ``LOSS_MUST_BE_ENUMERABLE`` refusal and
``consent_to_destroy(plan)`` token — and the shrink that destroys nothing still applies, with a
preview that is **explicitly empty and measured** rather than ``None``.
"""
import json
from pathlib import Path

import base_destructive_fakes as fakes
import pytest

from larkdocio.base import field_authoring as fa
from larkdocio.base import loss_preview as lp
from larkdocio.base import schema_ops, schema_ops_destructive as destructive
from larkdocio.base import schema_ops_fields as sof
from larkdocio.base.plan import Refusal
from larkdocio.base.schema_apply import (
    DestructiveConsentRequired,
    consent_to_destroy,
    schema_apply,
    schema_dry_run,
)

CAPTURE = (Path(__file__).resolve().parents[1] / "tests" / "captures" / "base-study" / "captures"
           / "ld462-01-select-option-shrink.json")

APP = "appLD462"
TBL = "tblMain"

ABC = [{"id": "optA", "name": "A", "color": 0},
       {"id": "optB", "name": "B", "color": 1},
       {"id": "optC", "name": "C", "color": 2}]
KEEP_AB = [ABC[0], ABC[1]]


def _world(*, multi=False, as_dict=False, records=None, **kwargs):
    """One table, one select column carrying ``A, B, C``, and rows that hold them."""
    cells = records if records is not None else [
        {"Title": "one", "Status": "A"},
        {"Title": "two", "Status": "C"},
        {"Title": "three", "Status": "C"},
    ]
    return fakes.ScanWorld({
        TBL: {
            "name": "Main",
            "revision": 4,
            "fields": [
                fakes.FakeField("fldTitle", "Title"),
                fakes.select_field("fldStatus", "Status", options=ABC, multi=multi,
                                   as_dict=as_dict),
            ],
            "records": [fakes.FakeRecord(f"rec{index}", row)
                        for index, row in enumerate(cells)],
        },
    }, **kwargs)


def _shrink(options=None, *, multi=False, field_name="Status"):
    return sof.update_field(APP, TBL, "fldStatus", field_name,
                            4 if multi else 3,
                            ui_type="MultiSelect" if multi else "SingleSelect",
                            properties={"options": KEEP_AB if options is None else options},
                            revision=4)


class _ShrinkingClient:
    """A schema client whose ``update_field`` really replaces the option set in a
    :class:`ScanWorld` and bumps ``table.revision`` — so a read-back that confirms is confirming
    something, and an apply that lands really landed."""

    def __init__(self, world):
        self.world = world
        self.calls = []

    def update_field(self, app_token, table_id, field_id, field_name, field_type,
                     ui_type=None, properties=None):
        self.calls.append(("update_field", table_id, field_id))
        body = self.world.tables[table_id]
        for index, spec in enumerate(body["fields"]):
            if spec.field_id == field_id:
                body["fields"][index] = fakes.select_field(
                    field_id, field_name, options=(properties or {}).get("options") or [],
                    multi=field_type == 4)
        body["revision"] = (body.get("revision") or 0) + 1
        return field_id


class _RefusingClient:
    """A schema client that RAISES on contact — so "nothing was sent" is structural."""

    def __getattr__(self, name):
        def _boom(*_a, **_k):
            raise AssertionError(f"a refused plan reached the transport: {name}")
        return _boom


# =========================================================================== #
# The measurement — the capture says what the gate is for                      #
# =========================================================================== #

def test_the_capture_says_a_POPULATED_shrink_destroys_cells_and_an_UNPOPULATED_one_does_not():
    arms = {arm["arm"]: arm for arm in json.loads(CAPTURE.read_text(encoding="utf-8"))["arms"]}
    populated = arms["single-select-shrink-populated"]
    assert populated["records_changed_count"] == 2
    assert len(populated["cells_emptied"]) == 2, "the two cells that held the dropped option"
    assert arms["single-select-shrink-unpopulated"]["records_changed_count"] == 0
    # AC4, arm 2: a rename with every id kept moves no value out of any cell.
    rename = arms["single-select-rename-every-id-kept"]
    assert rename["cells_emptied"] == []
    assert [o["id"] for o in rename["options_before"]] == [o["id"]
                                                           for o in rename["options_after"]]
    # AC4, arm 3: a MultiSelect narrowing removes the dropped value from each cell, and empties
    # a cell that held nothing else.
    narrow = arms["multi-select-narrowing-populated"]
    assert narrow["cells_after"]["recqnbU7PgpZJD"] == ["B"]
    assert len(narrow["cells_emptied"]) == 1


# =========================================================================== #
# AC1 — refused without consent, and consent is the ONE that already exists     #
# =========================================================================== #

def test_AC1_a_shrink_that_can_destroy_cells_is_REFUSED_from_a_default_apply():
    world = _world()
    plan = schema_dry_run([_shrink()], read_client=world)
    assert plan.destructive is True, "an option shrink that destroys cells is a destructive plan"
    with pytest.raises(DestructiveConsentRequired) as excinfo:
        schema_apply(plan, client=_RefusingClient(), read_client=world)
    assert "consent_to_destroy(plan)" in str(excinfo.value)
    assert lp.LOSS_MUST_BE_ENUMERABLE in str(excinfo.value)


def test_AC1_the_loss_is_enumerated_PER_RECORD_exactly_as_delete_field_enumerates_its_column():
    world = _world()
    loss = schema_dry_run([_shrink()], read_client=world).entries[0].loss_preview
    assert loss is not None
    assert loss["kind"] == "select-option-shrink"
    assert [option["id"] for option in loss["options_dropped"]] == ["optC"]
    assert [option["id"] for option in loss["options_kept"]] == ["optA", "optB"]
    assert [row["record_id"] for row in loss["records"]] == ["rec1", "rec2"]
    assert [row["values_lost"] for row in loss["records"]] == [["C"], ["C"]]
    assert all(row["cell_becomes_empty"] for row in loss["records"])
    assert loss["records_affected"] == 2 and loss["values_lost"] == 2
    assert loss["destroys"] is True
    # The column is described the way a delete_field preview describes it — same keys, same
    # cell count read from the table itself at plan time.
    column = loss["columns"][0]
    assert column["table_id"] == TBL and column["field_id"] == "fldStatus"
    assert column["cells_with_data"] == 3
    assert loss["invariant"] == lp.LOSS_MUST_BE_ENUMERABLE


def test_AC1_the_shrink_applies_ONLY_with_consent_minted_from_ITS_OWN_plan():
    world = _world()
    plan = schema_dry_run([_shrink()], read_client=world)
    client = fakes.ScriptedDestructiveClient(world)
    other = schema_dry_run([_shrink()], read_client=world)
    with pytest.raises(DestructiveConsentRequired) as excinfo:
        schema_apply(plan, client=client, read_client=world,
                     consent=consent_to_destroy(other))
    assert "DIFFERENT plan" in str(excinfo.value)
    assert client.calls == [], "a refused consent sends nothing"


def test_AC1_the_consent_token_is_the_SAME_helper_and_covers_a_MIXED_plan():
    """One plan carrying a ``delete_field`` and an option shrink mints ONE consent, and its
    losses are both previews — the doctrine is reused, not duplicated."""
    world = _world()
    plan = schema_dry_run([destructive.delete_field(APP, TBL, "fldTitle", revision=4),
                           _shrink()], read_client=world)
    consent = consent_to_destroy(plan)
    assert consent.plan is plan
    assert [loss["kind"] for loss in consent.losses] == ["field-delete", "select-option-shrink"]


def test_AC1_the_gate_is_the_ENGINEs_and_not_a_second_one_in_the_request_constructor():
    """The shrink request itself still builds — locally, with no read and no client — because
    the fence belongs at the plan/apply seam where ``delete_field``'s lives. A second gate one
    level down would be the third consent shape this issue exists to avoid."""
    request = _shrink()
    assert request.op == "update_field"
    assert sof.build_update_request(APP, TBL, "fldStatus", "Status", 3,
                                    ui_type="SingleSelect",
                                    properties={"options": KEEP_AB}) is not None


# =========================================================================== #
# AC2 — enumerable or refused. Never applied with an unknown blast radius       #
# =========================================================================== #

def test_AC2_no_read_client_REFUSES_the_shrink_and_NAMES_what_to_pass():
    plan = schema_dry_run([_shrink()])
    entry = plan.entries[0]
    assert entry.refusal is not None and entry.loss_preview is None
    assert entry.refusal.reason == Refusal.LOSS_NOT_ENUMERABLE
    assert "read_client=BaseReadClient(...)" in entry.refusal.detail
    assert lp.LOSS_MUST_BE_ENUMERABLE in entry.refusal.detail
    # And nothing is applied: the entry is logged refused, with zero writes. `allow_partial=True`
    # because the subject here IS the log — the apply seam raises on a refusal by default.
    log = schema_apply(plan, client=_RefusingClient(), read_client=_world(),
                       allow_partial=True)
    assert [entry.outcome for entry in log.entries] == ["refused"]


@pytest.mark.parametrize("truncate,shortfall", [
    (("records:tblMain",), "exhaustion"),
    (("tables",), "exhaustion"),
])
def test_AC2_a_paging_failure_REFUSES_rather_than_guessing_an_EMPTY_preview(truncate, shortfall):
    world = _world(truncate=truncate)
    entry = schema_dry_run([_shrink()], read_client=world).entries[0]
    assert entry.loss_preview is None, "never a guessed-empty preview"
    assert entry.refusal.reason == Refusal.LOSS_NOT_ENUMERABLE
    assert shortfall in entry.refusal.detail


def test_AC2_an_UNREADABLE_table_REFUSES():
    world = _world(raises={"records:tblMain": RuntimeError("boom")})
    entry = schema_dry_run([_shrink()], read_client=world).entries[0]
    assert entry.loss_preview is None
    assert entry.refusal.reason == Refusal.LOSS_NOT_ENUMERABLE


def test_AC2_a_column_whose_OPTION_SET_could_not_be_read_REFUSES():
    world = fakes.ScanWorld({TBL: {"name": "Main", "fields": [
        fakes.select_field("fldStatus", "Status", options=None)], "records": []}})
    entry = schema_dry_run([_shrink()], read_client=world).entries[0]
    assert entry.loss_preview is None
    assert entry.refusal.reason == Refusal.LOSS_NOT_ENUMERABLE
    assert "option set" in entry.refusal.detail


def test_AC2_a_column_that_is_NOT_THERE_REFUSES_rather_than_planning_a_blind_write():
    world = fakes.ScanWorld({TBL: {"name": "Main", "fields": [], "records": []}})
    entry = schema_dry_run([_shrink()], read_client=world).entries[0]
    assert entry.refusal.reason == Refusal.LOSS_NOT_ENUMERABLE


def test_AC2_consent_CANNOT_be_minted_over_a_shrink_whose_loss_refused():
    plan = schema_dry_run([_shrink()])
    with pytest.raises(DestructiveConsentRequired) as excinfo:
        consent_to_destroy(plan)
    assert "read_client=BaseReadClient(...)" in str(excinfo.value)


# =========================================================================== #
# AC3 — a shrink that destroys nothing stays cheap, quiet, and MEASURED empty   #
# =========================================================================== #

def test_AC3_a_shrink_of_an_option_NO_RECORD_HOLDS_applies_with_NO_consent():
    world = _world(records=[{"Status": "A"}, {"Status": "B"}])
    plan = schema_dry_run([_shrink()], read_client=world)
    assert plan.destructive is False, "nothing is destroyed, so there is nothing to consent to"
    log = schema_apply(plan, client=_ShrinkingClient(world), read_client=world)
    assert [entry.outcome for entry in log.entries] == ["applied"], log.to_dict()


def test_AC3_the_empty_preview_is_EXPLICITLY_EMPTY_AND_MEASURED_never_None():
    world = _world(records=[{"Status": "A"}, {"Status": "B"}])
    loss = schema_dry_run([_shrink()], read_client=world).entries[0].loss_preview
    assert loss is not None, "an empty loss is a MEASURED emptiness, not an absent preview"
    assert loss["records"] == [] and loss["records_affected"] == 0
    assert loss["destroys"] is False
    assert [option["id"] for option in loss["options_dropped"]] == ["optC"]
    assert "MEASURED" in loss["what"] and "read at plan time" in loss["what"]


@pytest.mark.parametrize("options,label", [
    (ABC, "a full pass-through"),
    (ABC + [{"name": "D", "color": 3}], "an addition beside the kept ids"),
    ([dict(ABC[0], name="A-RENAMED"), ABC[1], ABC[2]], "a rename with every id kept"),
])
def test_AC3_the_non_shrinking_option_edits_destroy_NOTHING(options, label):
    """AC4's sweep, decided by the same enumeration: none of these drops an id, so none of them
    loses a cell — which the ld462 capture measured directly for the rename."""
    world = _world()
    plan = schema_dry_run([_shrink(options)], read_client=world)
    loss = plan.entries[0].loss_preview
    assert loss["options_dropped"] == [], label
    assert loss["destroys"] is False and plan.destructive is False, label


def test_AC3_a_NON_SELECT_update_pays_NOTHING_no_read_no_preview_no_consent():
    """The counterweight: this issue must not turn every schema tidy-up into a ceremony."""
    world = _world()
    plan = schema_dry_run([sof.update_field(APP, TBL, "fldTitle", "Renamed", 1)],
                          read_client=world)
    assert plan.destructive is False
    assert plan.entries[0].loss_preview is None
    assert plan.loss_preview_cost is None
    assert world.calls == [], "a non-destructive plan still costs ZERO reads"


def test_AC3_a_non_options_PROPERTY_edit_pays_nothing_either():
    world = _world()
    plan = schema_dry_run([sof.update_field(APP, TBL, "fldMoney", "Money", 2,
                                            ui_type="Currency",
                                            properties={"currency_code": "USD",
                                                        "formatter": "0.00"})],
                          read_client=world)
    assert plan.destructive is False and world.calls == []


# =========================================================================== #
# AC4 — the whole destructive surface of option authoring, swept once           #
# =========================================================================== #

def test_AC4_a_MULTISELECT_NARROWING_is_under_the_SAME_gate_and_names_what_each_cell_keeps():
    world = _world(multi=True, records=[
        {"Status": ["A", "B"]}, {"Status": ["B", "C"]}, {"Status": ["C"]}])
    plan = schema_dry_run([_shrink(multi=True)], read_client=world)
    assert plan.destructive is True
    rows = {row["record_id"]: row for row in plan.entries[0].loss_preview["records"]}
    assert set(rows) == {"rec1", "rec2"}
    assert rows["rec1"]["values_lost"] == ["C"] and rows["rec1"]["values_kept"] == ["B"]
    assert rows["rec1"]["cell_becomes_empty"] is False, (
        "a MultiSelect cell holding another value KEEPS the cell — only the value is destroyed")
    assert rows["rec2"]["cell_becomes_empty"] is True


def test_AC4_replacing_the_option_set_WHOLESALE_is_the_maximal_shrink():
    world = _world()
    replacement = [{"id": "optZ", "name": "Z", "color": 0}]
    loss = schema_dry_run([_shrink(replacement)], read_client=world).entries[0].loss_preview
    assert [option["id"] for option in loss["options_dropped"]] == ["optA", "optB", "optC"]
    assert loss["records_affected"] == 3 and loss["destroys"] is True


def test_AC4_LD339s_two_STRUCTURAL_refusals_are_untouched_and_still_cost_zero_reads():
    """Supersession, not replacement: the id-less and option-less shapes are still refused on
    the request's own shape, before a client or a read exists. Only the SHRINK is new."""
    for properties in ({"options": [{"name": "A"}]}, None):
        with pytest.raises(fa.SelectOptionIdRequiredError):
            sof.update_field(APP, TBL, "fldStatus", "Status", 3, ui_type="SingleSelect",
                             properties=properties)


def test_AC4_the_conditional_destructiveness_is_DECLARED_by_the_field_family():
    """Declared, never inferred from the verb — the rule ``DESTRUCTIVE_OPS`` already lives by.
    ``update_field`` is destructive in exactly one shape, and the family says which."""
    assert "update_field" in schema_ops.destructive_shapes()
    assert "update_field" not in schema_ops.destructive_ops()
    assert schema_ops.request_destroys_data(_shrink()) is True
    assert schema_ops.request_destroys_data(
        sof.update_field(APP, TBL, "fldTitle", "T", 1)) is False
    assert schema_ops.request_destroys_data(
        destructive.delete_field(APP, TBL, "fldTitle")) is True


@pytest.mark.parametrize("as_dict", [False, True])
def test_AC4_the_option_set_is_read_through_BOTH_doors_typed_and_raw(as_dict):
    """The typed door nests ``AppTableFieldPropertyOption`` OBJECTS, not dicts — the shape a
    reader that required a mapping at the option level would be blind to (LD-281's lesson)."""
    world = _world(as_dict=as_dict)
    loss = schema_dry_run([_shrink()], read_client=world).entries[0].loss_preview
    assert [option["name"] for option in loss["options_dropped"]] == ["C"]
    assert loss["records_affected"] == 2


def test_AC4_two_options_sharing_a_NAME_are_disclosed_rather_than_silently_over_counted():
    """``records/search`` renders a select cell as the option NAME, so a dropped name that a
    KEPT option also carries cannot be attributed exactly. The preview says so."""
    twins = [{"id": "optA", "name": "A", "color": 0}, {"id": "optC", "name": "A", "color": 2}]
    world = fakes.ScanWorld({TBL: {"name": "Main", "fields": [
        fakes.select_field("fldStatus", "Status", options=twins)],
        "records": [fakes.FakeRecord("rec0", {"Status": "A"})]}})
    loss = schema_dry_run([_shrink([twins[0]])], read_client=world).entries[0].loss_preview
    assert loss["ambiguous_option_names"] == ["A"]
    assert "ambiguous" in loss["what"] or "cannot be attributed" in loss["what"]


# =========================================================================== #
# AC5 — the safe route is discoverable AT the refusal                           #
# =========================================================================== #

def test_AC5_the_refusal_names_REMAP_THEN_SHRINK_in_one_sentence():
    world = _world()
    plan = schema_dry_run([_shrink()], read_client=world)
    with pytest.raises(DestructiveConsentRequired) as excinfo:
        schema_apply(plan, client=_RefusingClient(), read_client=world)
    text = str(excinfo.value)
    assert fa.REMAP_THEN_SHRINK in plan.entries[0].loss_preview["remap_first"]
    assert "remap" in text.lower() and "then shrink" in text.lower()


def test_AC5_the_remap_sentence_names_the_ORDER_and_the_consequence_of_getting_it_wrong():
    text = fa.REMAP_THEN_SHRINK
    assert "before" in text or "first" in text
    assert "consent" in text


def test_AC5_no_shipped_text_still_says_there_is_NO_API_ROUTE_AT_ALL_for_an_option_set():
    """The phrasing both dogfood tiers read as *impossible*. It described a route the library
    now ships behind consent, so it is corrected where it touches option authoring."""
    guide = (Path(__file__).resolve().parents[1] / "src" / "larkdocio"
             / "GUIDE.md").read_text(encoding="utf-8")
    section = guide.split("A SELECT column's OPTIONS")[1].split("\n### ")[0]
    assert "there is no API route at all" not in section
    assert "does not ship it: do it in the product" not in fa.select_option_refusal(
        "no-ids", "SingleSelect")


# =========================================================================== #
# Zero drift — the delete previews this issue reuses are UNCHANGED              #
# =========================================================================== #

def test_the_field_delete_preview_shape_is_UNTOUCHED_by_this_issue():
    world = _world()
    loss = schema_dry_run([destructive.delete_field(APP, TBL, "fldStatus", revision=4)],
                          read_client=world).entries[0].loss_preview
    assert set(loss) == {"kind", "app_token", "columns", "other_tables", "mirror",
                         "inbound_links", "inbound_lookups", "tables", "what", "not_traced",
                         "trash", "invariant", "evidence"}
    assert loss["kind"] == "field-delete"


def test_the_OPTION_KEY_LIST_the_scan_reads_is_the_SELECT_SURFACES_OWN():
    """The shared-walk guard requires each key list to be a **literal at its own call site**, so
    the option read spells ``("id", "name", "color")`` there rather than borrowing a name. This
    holds that literal equal to the one authority for what keys an option carries, so the two
    spellings cannot drift apart."""
    assert fa.SELECT_OPTION_KEYS == ("id", "name", "color")
    world = _world()
    option = schema_dry_run([_shrink()], read_client=world) \
        .entries[0].loss_preview["options_dropped"][0]
    assert sorted(option) == sorted(fa.SELECT_OPTION_KEYS)


def test_the_shrink_preview_is_READABLE_BY_a_delete_preview_reader():
    """Same keys where the question is the same, so a consumer's preview printer keeps working
    instead of learning a second shape."""
    world = _world()
    loss = schema_dry_run([_shrink()], read_client=world).entries[0].loss_preview
    for shared in ("kind", "app_token", "columns", "other_tables", "mirror", "inbound_links",
                   "inbound_lookups", "tables", "what", "invariant", "evidence"):
        assert shared in loss, shared
