"""LD-264 — the VIEW lifecycle: the family, the allow-list, the read-back and the swallow control.

The one story where ``code:0`` is worth nothing and the proof lives one key away: the endpoint
that persists a ``property.filter_info`` **silently discards** a ``property.group_info``. So the
verification here is a **read-back**, and the grouping swallow is the negative control that makes
a positive result mean something. Both halves are pinned by
:func:`test_AC5_THE_PAIRING_the_filter_round_trips_and_the_GROUPING_DOES_NOT`.
"""
import json

import pytest

from log_reading_apply import reading_the_log
from larkdocio.base import ops as base_ops
from larkdocio.base import schema_ops, view_plan
from larkdocio.base import schema_ops_views as views
from larkdocio.base.errors import BASE_ERROR_CODES
from larkdocio.base.schema_apply import (
    SCHEMA_READ_SEAMS,
    SCHEMA_WRITE_SEAMS,
    schema_apply,
    schema_dry_run,
)
schema_apply = reading_the_log(schema_apply)
from larkdocio.base.schema_client import BaseSchemaClient, BaseSchemaRefusal
from larkdocio.base.schema_plan import NO_APP_REVISION_CAS
from larkdocio.base.view_filters import (
    Condition,
    FieldId,
    FilterSpec,
    SearchFilter,
    search_filter,
    view_filter,
)

from guard_kit import REPO_ROOT

FILTER = view_filter(FilterSpec(conditions=(Condition(FieldId("fldA"), "is", ("x",)),)))
SECOND = view_filter(FilterSpec(conditions=(Condition(FieldId("fldB"), "contains", ("y",)),)))


# --------------------------------------------------------------------------- #
# AC1 — the family, registered into LD-263's aggregator                         #
# --------------------------------------------------------------------------- #

def test_AC1_the_view_family_is_REGISTERED_as_its_own_module_and_one_line():
    assert "larkdocio.base.schema_ops_views" in schema_ops.FAMILY_MODULES
    family = views.SCHEMA_OP_FAMILY
    assert family.module == "larkdocio.base.schema_ops_views"
    assert [d.name for d in family.ops] == ["create_view", "update_view", "delete_view"]


def test_AC1_every_view_descriptor_MUTATES_and_the_aggregate_still_says_so():
    for descriptor in views.SCHEMA_OP_FAMILY.ops:
        assert descriptor.mutates is True
        assert descriptor.settles is False
        assert descriptor.family == "view"
        assert descriptor.read_back and descriptor.evidence
    assert schema_ops.all_mutate() is True
    assert schema_ops.settling_ops() and all(
        d.name == "copy_app" for d in schema_ops.settling_ops())


def test_AC1_the_READ_registry_STILL_ANSWERS_read_only_TRUE():
    """LD-255 AC2b: no mutating descriptor was appended to the read tuple, so the landed
    statement about the READ surface is still true — and this story did not edit the three
    assertions that say so, it added a fourth."""
    assert base_ops.read_only() is True


def test_AC1_the_endpoint_and_verb_are_CROSS_CHECKED_against_the_sdk_request_class():
    for descriptor in views.SCHEMA_OP_FAMILY.ops:
        request = descriptor.request_cls.builder().build()
        assert descriptor.endpoint == request.uri
        assert descriptor.http_method == request.http_method.name


def test_AC1_the_three_view_endpoints_are_the_ones_the_AC_names():
    by_name = {d.name: d for d in views.SCHEMA_OP_FAMILY.ops}
    assert by_name["create_view"].http_method == "POST"
    assert by_name["update_view"].http_method == "PATCH"
    assert by_name["delete_view"].http_method == "DELETE"
    assert by_name["create_view"].endpoint.endswith("/views")
    for name in ("update_view", "delete_view"):
        assert by_name[name].endpoint.endswith("/views/:view_id")


def test_AC1_the_write_seams_grew_and_the_read_seam_the_verification_spends_is_declared():
    assert SCHEMA_WRITE_SEAMS >= {"create_view", "update_view", "delete_view"}
    assert "list_views" in SCHEMA_READ_SEAMS
    assert not (SCHEMA_WRITE_SEAMS & SCHEMA_READ_SEAMS)


# --------------------------------------------------------------------------- #
# AC1 / AC7 — the view_type allow-list is EVIDENCE-KEYED, and `form` is POLICY  #
# --------------------------------------------------------------------------- #

def test_AC1_the_allow_list_is_the_FOUR_TYPES_A_CAPTURE_CREATED():
    assert views.VIEW_TYPES == ("grid", "kanban", "gallery", "gantt")


def test_AC1_a_server_refused_type_is_refused_LOCALLY_IN_THE_SERVERS_OWN_WORDS():
    for view_type in ("calendar", "board", "list"):
        with pytest.raises(BaseSchemaRefusal) as excinfo:
            view_plan.create_view("appX", "tblX", "V", view_type)
        message = str(excinfo.value)
        assert "99992402" in message
        assert "options: [grid,kanban,gallery,gantt,form]" in message, message


def test_AC7_form_is_refused_BY_POLICY_and_the_reason_is_NOT_impossible():
    with pytest.raises(BaseSchemaRefusal) as excinfo:
        view_plan.create_view("appX", "tblX", "Signups", "form")
    message = str(excinfo.value)
    assert "larkdocio does not control a Base's shareability" in message
    for claim in ("impossible", "lark forbids", "cannot be created", "not supported by lark"):
        assert claim not in message.lower(), claim
    # And it says plainly that the API DOES allow it — the honest half.
    assert "works" in message.lower() or "reachable" in message.lower()


def test_AC7_the_policy_sentence_is_the_ONE_ALREADY_SHIPPED_not_a_second_authoring():
    """The refusal quotes register row 17's own sentence rather than writing a rival one."""
    base_md = REPO_ROOT / "BASE.md"
    assert views.SHAREABILITY_IS_NOT_OURS in base_md.read_text(encoding="utf-8")


def test_AC7_NOTHING_IN_THE_LIBRARY_REACHES_A_FORMS_ENDPOINT():
    """Out of scope, in every direction: no `…/forms/*` call of any kind, and no `shared`
    write ever."""
    src = REPO_ROOT / "src" / "larkdocio"
    offenders = []
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "/forms/" in line and "open-apis" in line:
                offenders.append((path.name, line.strip()[:70]))
    assert not offenders, offenders


def test_AC7_the_form_view_id_IS_the_form_id_and_the_module_says_so():
    """The reason the exclusion is not cosmetic: `POST …/views {"view_type":"form"}` works,
    and the `view_id` it returns IS the `form_id` one `PATCH` away from a public URL."""
    assert "form_id" in views.FORM_IS_REFUSED_BY_POLICY
    assert "form" in views.SERVER_VIEW_TYPE_ENUM


# --------------------------------------------------------------------------- #
# AC9 — the surface is FILTERS ONLY (D1″(a))                                    #
#                                                                               #
# **NARROWED by LD-438, not withdrawn.** Every guard below still guards; what   #
# each now guards is the narrowed claim — **grouping and a saved view-level     #
# sort still have NO parameter anywhere**, and `hidden_fields` has **exactly    #
# one**, verified by read-back. The banned-spelling sweep for `group_info` /    #
# `grouping` / `group_by` and the sort keys is intact and, where the old        #
# assertion had room, widened. The `hidden_fields` half of each claim moved to  #
# its own positive guards in `tests/test_base_view_hidden_fields.py`; a strike  #
# here rather than a re-aim is what would re-litigate a settled argument.       #
# --------------------------------------------------------------------------- #

def test_AC9_NO_PUBLIC_PARAMETER_ANYWHERE_takes_grouping_or_sort():
    """The surviving half of the old `…_takes_grouping_hidden_fields_or_sort` guard, with the
    sort spellings LD-417 measured added to the sweep. `hidden_fields` left this list under
    LD-438 **on the evidence**, and its own entry points are asserted positively elsewhere."""
    import inspect

    banned = ("group_info", "grouping", "group_by", "hide_fields",
              "view_sort", "sort", "sort_info", "sorts", "sort_infos", "auto_sort")
    surface = [view_plan.create_view, view_plan.rename_view, view_plan.set_view_filter,
               view_plan.set_view_hierarchy, view_plan.set_view_hidden_fields,
               view_plan.clear_view_hidden_fields, view_plan.delete_view,
               BaseSchemaClient.create_view, BaseSchemaClient.update_view,
               BaseSchemaClient.delete_view]
    for fn in surface:
        params = set(inspect.signature(fn).parameters)
        assert not (params & set(banned)), (fn.__qualname__, params & set(banned))


def test_AC9_the_client_SENDS_no_grouping_or_sort_key_even_when_it_hides_columns():
    """The old `…_SENDS_no_grouping_or_hidden_fields_key_either`, re-aimed: the swallowed keys
    are still never sent, and the omission guarantee is asserted on the key that DID move — a
    filter patch leaves `hidden_fields` unset, which is what stops it un-hiding columns."""
    sdk, client = _fake_client()
    client.update_view("appX", "tblX", "vewX", filter_info=FILTER)
    body = sdk.sent[-1].request_body
    assert body.property.hidden_fields is None, "a filter patch must not touch hidden columns"
    assert body.property.hierarchy_config is None
    for swallowed in ("group_info", "sort_info", "sort", "sorts", "auto_sort"):
        assert not hasattr(body.property, swallowed)

    client.update_view("appX", "tblX", "vewX", hidden_fields=["fldA"])
    body = sdk.sent[-1].request_body
    assert body.property.filter_info is None, "a hide must not disturb the view's filter"
    for swallowed in ("group_info", "sort_info", "sort", "sorts", "auto_sort"):
        assert not hasattr(body.property, swallowed)


def test_AC9_the_public_view_ops_reach_NO_grouping_or_sort_ARGUMENT_even_by_kwargs():
    """The old `…_reach_NO_hidden_fields_ARGUMENT_even_by_kwargs`, re-aimed onto the two that
    did not move — and `set_view_filter` still refuses a `hidden_fields` kwarg, because the
    hidden set has its OWN request constructor rather than riding another op's signature."""
    for banned in ({"group_info": {}}, {"sort_info": []}, {"hidden_fields": ["fldA"]}):
        with pytest.raises(TypeError):
            view_plan.set_view_filter("appX", "tblX", "vewX", FILTER, **banned)
    for banned in ({"group_info": {}}, {"sort_info": []}):
        with pytest.raises(TypeError):
            view_plan.set_view_hidden_fields("appX", "tblX", "vewX", ["fldA"], **banned)


# --------------------------------------------------------------------------- #
# The client — typed builders only, and the DIALECT BOUNDARY at the signature   #
# --------------------------------------------------------------------------- #

class _FakeResponse:
    def __init__(self, data=None, code=0, msg="success"):
        self.code, self.msg, self.data = code, msg, data
        self.raw = None


class _FakeView:
    def __init__(self, view_id="vewNEW01", view_name="V", view_type="grid", property_=None):
        self.view_id, self.view_name, self.view_type = view_id, view_name, view_type
        self.property = property_


class _FakeSdk:
    def __init__(self, responses=None):
        self.sent = []
        self._responses = list(responses or [])
        outer = self

        class _View:
            def create(self, request):
                outer.sent.append(request)
                return outer._next(_FakeResponse(type("D", (), {"view": _FakeView()})()))

            def patch(self, request):
                outer.sent.append(request)
                return outer._next(_FakeResponse(type("D", (), {"view": _FakeView()})()))

            def delete(self, request):
                outer.sent.append(request)
                return outer._next(_FakeResponse(type("D", (), {})()))

        self.bitable = type("B", (), {"v1": type("V1", (), {"app_table_view": _View()})()})()

    def _next(self, default):
        return self._responses.pop(0) if self._responses else default


class _NoWait:
    def acquire(self):
        pass


def _fake_client(responses=None):
    sdk = _FakeSdk(responses)
    return sdk, BaseSchemaClient("id", "secret", sdk_client=sdk, rate_limiter=_NoWait())


def test_the_create_sends_ONLY_a_name_and_a_type_through_the_typed_builder():
    sdk, client = _fake_client()
    view_id = client.create_view("appX", "tblX", "Open risks", "grid")
    assert view_id == "vewNEW01"
    request = sdk.sent[-1]
    assert request.app_token == "appX" and request.table_id == "tblX"
    assert request.request_body.view_name == "Open risks"
    assert request.request_body.view_type == "grid"


def test_the_patch_puts_the_FILTER_UNDER_property_filter_info():
    sdk, client = _fake_client()
    client.update_view("appX", "tblX", "vewX", filter_info=FILTER)
    body = sdk.sent[-1].request_body
    assert body.view_name is None
    condition = body.property.filter_info.conditions[0]
    assert condition.field_id == "fldA" and condition.operator == "is"
    # A STRING carrying a JSON array — the SDK's own `_types` declares `value: str`, and the
    # live probe agrees: an array here answers `9499`.
    assert condition.value == '["x"]'
    assert body.property.filter_info.conjunction == "and"


def test_a_VALUELESS_operator_leaves_the_value_key_OFF_the_request_entirely():
    sdk, client = _fake_client()
    client.update_view("appX", "tblX", "vewX", filter_info=view_filter(
        FilterSpec(conditions=(Condition(FieldId("fldA"), "isNotEmpty"),))))
    condition = sdk.sent[-1].request_body.property.filter_info.conditions[0]
    assert condition.value is None, (
        "`\"\"` answers 1254001 and `[]` answers 9499; only omitting the key is code:0")


def test_the_patch_can_RENAME_without_touching_the_filter():
    sdk, client = _fake_client()
    client.update_view("appX", "tblX", "vewX", view_name="Renamed")
    body = sdk.sent[-1].request_body
    assert body.view_name == "Renamed" and body.property is None


def test_THE_DIALECT_BOUNDARY_IS_THE_SIGNATURE_a_search_filter_CANNOT_REACH_THE_VIEW_ROUTE():
    """AC3, at the seam that matters: the wrong dialect is not merely discouraged, it is
    rejected by the route's own signature — and NOTHING is sent."""
    sdk, client = _fake_client()
    wrong = search_filter(FilterSpec(conditions=(
        Condition(__import__("larkdocio.base.view_filters", fromlist=["FieldName"]).FieldName(
            "Text"), "is", ("x",)),)))
    assert isinstance(wrong, SearchFilter)
    with pytest.raises(TypeError) as excinfo:
        client.update_view("appX", "tblX", "vewX", filter_info=wrong)
    assert "field_id" in str(excinfo.value)
    with pytest.raises(TypeError):
        client.update_view("appX", "tblX", "vewX",
                           filter_info={"conjunction": "and", "conditions": []})
    assert sdk.sent == [], "a refused dialect must cost ZERO calls"


def test_a_patch_that_asks_for_NOTHING_is_refused_rather_than_sent():
    sdk, client = _fake_client()
    with pytest.raises(BaseSchemaRefusal):
        client.update_view("appX", "tblX", "vewX")
    assert sdk.sent == []


def test_the_delete_sends_the_three_path_segments_and_nothing_else():
    sdk, client = _fake_client()
    assert client.delete_view("appX", "tblX", "vewX") is True
    request = sdk.sent[-1]
    assert (request.app_token, request.table_id, request.view_id) == ("appX", "tblX", "vewX")


def test_AC8_the_LAST_VIEW_refusal_is_TYPED_ENTRY_SCOPED_and_tells_the_caller_what_to_do():
    note = BASE_ERROR_CODES[1254023]
    assert note.label == "LastViewDeleteForbidden"
    assert views.LAST_VIEW_IS_PROTECTED
    text = views.LAST_VIEW_IS_PROTECTED.lower()
    assert "create" in text and "view" in text
    # Entry-scoped: it says nothing about any other entry in the plan.
    from larkdocio.base.disposition import classify_apply_exception
    from larkdocio.errors import LarkAPIError

    error = LarkAPIError("delete the last view: 1254023 LastViewDeleteForbidden")
    error.code = 1254023
    disposition = classify_apply_exception(error, wrote=False)
    assert disposition.halts is False, "1254023 is about ONE view, not the batch"


# --------------------------------------------------------------------------- #
# The plan — typed requests, refusals decided BEFORE any call                    #
# --------------------------------------------------------------------------- #

def test_the_four_typed_requests_name_registered_ops():
    requests = [
        view_plan.create_view("appX", "tblX", "Open risks", "grid"),
        view_plan.rename_view("appX", "tblX", "vewX", "Closed risks"),
        view_plan.set_view_filter("appX", "tblX", "vewX", FILTER),
        view_plan.delete_view("appX", "tblX", "vewX"),
    ]
    assert [r.op for r in requests] == [
        "create_view", "update_view", "update_view", "delete_view"]
    plan = schema_dry_run(requests)
    assert plan.api_call_count == 4 and not plan.refusals
    assert json.loads(plan.to_json())["entries"][2]["fields"]["filter_info"] == FILTER.to_dict()


def test_the_plan_says_HOW_EACH_VIEW_OP_WILL_BE_VERIFIED_before_any_call():
    """And what the verification COSTS, declared as this family's own trait.

    A filter patch is read back with **two** reads, not one: the listing answers *does this
    view still exist*, and the single-view `GET …/views/{v}` answers *did the filter persist* —
    the listing does not carry a view's `property` at all. The budget is stated rather than
    assumed, so a plan a consumer approves is honest about what it will spend.
    """
    plan = schema_dry_run([view_plan.set_view_filter("appX", "tblX", "vewX", FILTER)])
    assert "read" in plan.entries[0].read_back.lower()
    assert plan.entries[0].asynchronous is False
    assert plan.entries[0].read_cost == 2
    assert plan.read_calls == 2

    # A create is verified by the listing alone, so it costs one — the budget tracks the
    # read-back each op actually performs rather than a per-family constant.
    create = schema_dry_run([view_plan.create_view("appX", "tblX", "Q3")])
    assert create.read_calls == 1


def test_AC6_a_view_entry_DISCLOSES_THAT_THERE_IS_NO_ANCHOR_and_it_is_its_OWN_statement():
    plan = schema_dry_run([view_plan.set_view_filter("appX", "tblX", "vewX", FILTER)])
    disclosure = plan.entries[0].revision_guard_disclosure
    assert disclosure == views.NO_VIEW_ANCHOR
    assert disclosure != NO_APP_REVISION_CAS, (
        "the app-revision fact is about app.revision; a view has no anchor AT ALL and the two "
        "must not be collapsed into one sentence")
    assert plan.entries[0].revision_guard is None
    assert plan.entries[0].scope == "view"
    low = disclosure.lower()
    assert "no" in low and "read-back" in low
    for overclaim in ("atomic", "guaranteed", "safe from", "compare-and-swap protects"):
        assert overclaim not in low, overclaim


def test_AC6_an_APP_SCOPED_entry_in_the_SAME_PLAN_keeps_ITS_OWN_disclosure():
    from larkdocio.base.schema_plan import rename_base

    plan = schema_dry_run([rename_base("appX", "Q3"),
                           view_plan.set_view_filter("appX", "tblX", "vewX", FILTER)])
    assert plan.entries[0].revision_guard_disclosure == NO_APP_REVISION_CAS
    assert plan.entries[1].revision_guard_disclosure == views.NO_VIEW_ANCHOR


# --------------------------------------------------------------------------- #
# AC5 — THE READ-BACK, and the SWALLOW CONTROL that gives it meaning            #
# --------------------------------------------------------------------------- #

class _RecordingSchemaClient:
    """A schema client that lands what it is told to land — and, for the control, one that
    answers `code:0` and changes nothing, exactly as `property.group_info` does."""

    def __init__(self, store, *, swallow=False):
        self.store, self.swallow, self.calls = store, swallow, []

    def create_view(self, app_token, table_id, view_name, view_type="grid"):
        self.calls.append(("create_view", view_name, view_type))
        view_id = f"vew{len(self.store) + 1:02d}"
        self.store[view_id] = {"view_name": view_name, "view_type": view_type,
                               "property": None}
        return view_id

    def update_view(self, app_token, table_id, view_id, *, view_name=None, filter_info=None,
                    hierarchy_config=None, hidden_fields=None):
        self.calls.append(("update_view", view_id))
        if self.swallow:
            return True                    # code:0 — and NOTHING changes. The swallow.
        view = self.store[view_id]
        if view_name is not None:
            view["view_name"] = view_name
        if hierarchy_config is not None:
            # LD-296: the same read-back discipline, one key over — the persisted
            # property carries the field id that was sent, and the OTHER keys are left
            # exactly as they were, which is what the omission guarantee means.
            existing = view.get("property") or {}
            view["property"] = {"filter_info": existing.get("filter_info"),
                                "hidden_fields": existing.get("hidden_fields"),
                                "hierarchy_config": hierarchy_config.to_dict()}
        if filter_info is not None:
            persisted = filter_info.to_dict()
            for index, condition in enumerate(persisted["conditions"]):
                condition["condition_id"] = f"con{index}"
                condition["field_type"] = 1
            existing = view.get("property") or {}
            # LD-438: the hidden set is CARRIED THROUGH, not reset. A double that blanked it
            # would let a regression in the omission guarantee pass unnoticed — which is
            # exactly the invariant `test_base_view_hidden_fields.py` pins in both directions.
            view["property"] = {"filter_info": persisted,
                                "hidden_fields": existing.get("hidden_fields"),
                                "hierarchy_config": existing.get("hierarchy_config")}
        if hidden_fields is not None:
            existing = view.get("property") or {}
            view["property"] = {"filter_info": existing.get("filter_info"),
                                "hidden_fields": list(hidden_fields) or None,
                                "hierarchy_config": existing.get("hierarchy_config")}
        return True

    def delete_view(self, app_token, table_id, view_id):
        self.calls.append(("delete_view", view_id))
        self.store.pop(view_id, None)
        return True


class _RecordingReadClient:
    def __init__(self, store):
        self.store, self.calls = store, []

    def list_views(self, app_token, table_id):
        """The LISTING — and, exactly as the live API does, it carries **no** `property`."""
        self.calls.append(("list_views", table_id))
        out = []
        for view_id, blob in self.store.items():
            view = type("V", (), {})()
            view.view_id = view_id
            view.view_name = blob["view_name"]
            view.view_type = blob["view_type"]
            view.property = None
            out.append(view)
        return out

    def get_view(self, app_token, table_id, view_id):
        """The SINGLE-view read — the only one that carries `property`. Modelled this way on
        purpose: a double whose listing carried the filter would let a read-back pass that the
        real API cannot serve."""
        self.calls.append(("get_view", view_id))
        blob = self.store[view_id]
        view = type("V", (), {})()
        view.view_id, view.view_name = view_id, blob["view_name"]
        view.view_type = blob["view_type"]
        view.property = _as_property(blob["property"])
        return view


def _as_property(blob):
    if blob is None:
        return None
    prop = type("P", (), {})()
    prop.filter_info = _as_filter(blob.get("filter_info"))
    prop.hidden_fields = blob.get("hidden_fields")
    config = blob.get("hierarchy_config")
    prop.hierarchy_config = (
        type("H", (), {"field_id": config["field_id"]})() if config else None)
    return prop


def _as_filter(blob):
    if blob is None:
        return None
    info = type("F", (), {})()
    info.conjunction = blob["conjunction"]
    info.conditions = []
    for condition in blob["conditions"]:
        node = type("C", (), {})()
        for key, value in condition.items():
            setattr(node, key, value)
        info.conditions.append(node)
    return info


def _run(requests, *, swallow=False, store=None):
    store = {} if store is None else store
    client = _RecordingSchemaClient(store, swallow=swallow)
    read = _RecordingReadClient(store)
    log = schema_apply(schema_dry_run(requests), client=client, read_client=read)
    return log, store, client, read


def test_AC5_a_filter_that_PERSISTS_reads_back_and_is_reported_APPLIED():
    log, store, _client, _read = _run([
        view_plan.create_view("appX", "tblX", "Open risks", "grid"),
    ])
    view_id = next(iter(store))
    log2, store, _c, _r = _run(
        [view_plan.set_view_filter("appX", "tblX", view_id, FILTER)], store=store)
    entry = log2.entries[0]
    assert entry.outcome == "applied", entry.refusal and entry.refusal.detail
    assert entry.read_back["persisted"] == FILTER.to_dict()
    assert entry.read_back["echoes"] is True


def test_AC5_THE_PAIRING_the_filter_round_trips_and_the_GROUPING_DOES_NOT():
    """**The entire argument for read-back verification, in one test.** The same endpoint,
    the same `code:0`, two sibling keys — one persists and one is silently swallowed. A
    `code:0` whose read-back does not echo is a typed NOT-PERSISTED disposition, never
    `applied`."""
    import copy as _copy

    store = {"vew01": {"view_name": "V", "view_type": "grid", "property": None}}
    applied, _s, _c, _r = _run(
        [view_plan.set_view_filter("appX", "tblX", "vew01", FILTER)],
        store=_copy.deepcopy(store))
    assert applied.entries[0].outcome == "applied"

    swallowed, _s, client, _r = _run(
        [view_plan.set_view_filter("appX", "tblX", "vew01", FILTER)],
        store=_copy.deepcopy(store), swallow=True)
    entry = swallowed.entries[0]
    assert entry.outcome == "dropped", "a swallowed write must NEVER be reported applied"
    assert client.calls == [("update_view", "vew01")], "the engine does not retry a swallow"
    detail = entry.refusal.detail
    assert "code:0" in detail and "read-back" in detail.lower()
    assert entry.read_back["echoes"] is False
    assert entry.read_back["persisted"] is None


def test_AC5_the_normalisation_of_the_servers_own_additions_is_EXPLICIT():
    """The server adds `condition_id` and echoes `field_type`. The comparison is semantic and
    the dropped keys are named — the read-back records what it compared."""
    store = {"vew01": {"view_name": "V", "view_type": "grid", "property": None}}
    log, store, _c, _r = _run(
        [view_plan.set_view_filter("appX", "tblX", "vew01", FILTER)], store=store)
    persisted = store["vew01"]["property"]["filter_info"]
    assert persisted["conditions"][0]["condition_id"] == "con0"
    assert persisted["conditions"][0]["field_type"] == 1
    assert log.entries[0].read_back["normalized_away"] == ["condition_id", "field_type"]


def test_AC5_the_ALTER_LOOP_the_second_read_back_is_the_SECOND_FILTER_not_a_merge():
    store = {"vew01": {"view_name": "V", "view_type": "grid", "property": None}}
    _first, store, _c, _r = _run(
        [view_plan.set_view_filter("appX", "tblX", "vew01", FILTER)], store=store)
    second, store, _c, _r = _run(
        [view_plan.set_view_filter("appX", "tblX", "vew01", SECOND)], store=store)
    assert second.entries[0].outcome == "applied"
    assert second.entries[0].read_back["persisted"] == SECOND.to_dict()
    assert store["vew01"]["property"]["filter_info"]["conditions"][0]["field_id"] == "fldB"


def test_AC5_ONE_PLAN_TWO_KEYS_one_applied_and_one_NOT_PERSISTED():
    """Test-rigor amplifier: the swallow and the persist ride the SAME plan, and the log
    records one of each — which is only observable because the verification is a read-back."""
    store = {"vew01": {"view_name": "V", "view_type": "grid", "property": None}}

    class _Mixed(_RecordingSchemaClient):
        def update_view(self, app_token, table_id, view_id, *, view_name=None,
                        filter_info=None, hierarchy_config=None, hidden_fields=None):
            # The rename lands; the filter is swallowed — one call each, both `code:0`.
            self.swallow = filter_info is not None
            return super().update_view(app_token, table_id, view_id, view_name=view_name,
                                       filter_info=filter_info,
                                       hierarchy_config=hierarchy_config,
                                       hidden_fields=hidden_fields)

    client, read = _Mixed(store), _RecordingReadClient(store)
    log = schema_apply(schema_dry_run([
        view_plan.rename_view("appX", "tblX", "vew01", "Renamed"),
        view_plan.set_view_filter("appX", "tblX", "vew01", FILTER),
    ]), client=client, read_client=read)
    assert [e.outcome for e in log.entries] == ["applied", "dropped"]
    assert log.halt is None, "a not-persisted entry is entry-scoped, not a batch halt"


def test_the_create_is_verified_by_the_view_appearing_in_the_LISTING():
    log, store, _c, read = _run([view_plan.create_view("appX", "tblX", "Open risks", "grid")])
    assert log.entries[0].outcome == "applied"
    assert log.entries[0].read_back["view_id"] in store
    assert ("list_views", "tblX") in read.calls


def test_the_delete_is_verified_by_the_view_being_GONE_from_the_listing():
    store = {"vew01": {"view_name": "V", "view_type": "grid", "property": None},
             "vew02": {"view_name": "W", "view_type": "grid", "property": None}}
    log, store, _c, _r = _run([view_plan.delete_view("appX", "tblX", "vew01")], store=store)
    assert log.entries[0].outcome == "applied"
    assert log.entries[0].read_back["gone"] is True
    assert set(store) == {"vew02"}


def test_a_delete_the_server_ACCEPTED_but_did_not_perform_is_DROPPED():
    class _NoOpDelete(_RecordingSchemaClient):
        def delete_view(self, app_token, table_id, view_id):
            self.calls.append(("delete_view", view_id))
            return True                     # code:0 — and the view is still there.

    store = {"vew01": {"view_name": "V", "view_type": "grid", "property": None}}
    log = schema_apply(schema_dry_run([view_plan.delete_view("appX", "tblX", "vew01")]),
                       client=_NoOpDelete(store), read_client=_RecordingReadClient(store))
    assert log.entries[0].outcome == "dropped"


def test_the_rename_is_verified_by_the_NEW_NAME_in_the_listing():
    store = {"vew01": {"view_name": "V", "view_type": "grid", "property": None}}
    log, store, _c, _r = _run(
        [view_plan.rename_view("appX", "tblX", "vew01", "Closed risks")], store=store)
    assert log.entries[0].outcome == "applied"
    assert log.entries[0].read_back["view_name"] == "Closed risks"


def test_the_READ_BACK_USES_THE_SINGLE_VIEW_READ_because_the_LISTING_HAS_NO_PROPERTY():
    """Measured live: `GET …/views` does not carry a view's `property` at all, while
    `GET …/views/{id}` does. So the listing answers *does this view still exist* and the
    single-view read answers *did the filter persist* — and a read-back that used only the
    listing would report every filter as not persisted."""
    from larkdocio.base import ops as base_ops

    assert "get_view" in {d.name for d in base_ops.OPS}
    assert base_ops.op("get_view").endpoint.endswith("/views/:view_id")
    assert base_ops.read_only() is True, "a new READ op does not make the read registry mutate"

    store = {"vew01": {"view_name": "V", "view_type": "grid", "property": None}}
    log, store, _c, read = _run(
        [view_plan.set_view_filter("appX", "tblX", "vew01", FILTER)], store=store)
    assert log.entries[0].outcome == "applied"
    assert ("get_view", "vew01") in read.calls
    assert ("list_views", "tblX") in read.calls


# --------------------------------------------------------------------------- #
# AC6 / AC7 / AC11 — the CONSUMER TEXT, held to the same bar as the code       #
# --------------------------------------------------------------------------- #

def _two_filters_recipe():
    """The WHOLE shipped section — prose before AND after the code, which is where the
    disclosures live. Read through `guide()`, so this is the text a consumer really gets."""
    from larkdocio import guide

    return guide("recipe-filter-a-base-two-ways-the-rows-a-read-returns-and-the-rows-a-person-sees")


def test_AC6_THE_GUIDE_MAKES_NO_ATOMICITY_OR_GUARD_CLAIM_for_a_view_write():
    """LD-259's no-overclaim rule, on a different surface. There is no view revision and
    `table.revision`'s response to a view PATCH is unmeasured, so the shipped text must not
    imply a guard — and must say plainly that there is none."""
    text = _two_filters_recipe().lower()
    for overclaim in ("atomic", "compare-and-swap", "staleness guard protects", "guaranteed",
                      "safely concurrent", "transaction"):
        assert overclaim not in text, overclaim
    assert "no staleness guard" in text, (
        "the absence must be STATED, not merely not-overstated — a consumer who is told "
        "nothing assumes the guard the record path has")


def test_AC7_THE_GUIDE_SAYS_FORM_IS_A_POLICY_CHOICE_and_does_not_blame_lark():
    text = _two_filters_recipe().lower()
    assert "does not control a base's shareability" in text
    assert "creating one works" in text or "works on lark's side" in text, (
        "the honest half: Lark allows it and this library declines — saying otherwise would "
        "be a false claim about Lark")
    for claim in ("impossible", "lark forbids", "lark does not allow", "not supported by lark"):
        assert claim not in text, claim


def test_AC11_THE_GUIDE_TEACHES_BOTH_FILTERS_SIDE_BY_SIDE_in_plain_language():
    text = _two_filters_recipe()
    lowered = text.lower()
    assert "search_filter" in text and "view_filter" in text
    assert "field's **name**" in text or "the field's **name**" in text
    assert "rows a read returns" in lowered and "rows a person sees" in lowered
    assert "dropped" in lowered and "applied" in lowered, (
        "a consumer must be told what the two outcomes mean, because on this endpoint a "
        "success code is not proof")


def test_AC9_THE_GUIDE_SAYS_WHY_grouping_and_sort_are_not_offered_AND_WHY_HIDING_NOW_IS():
    """**Re-aimed by LD-438, and it still guards the same thing where it still holds.** The
    reason has to survive the supersession, not be quietly dropped with the conclusion: this
    recipe must still say why grouping and a saved sort stay out (*a knob whose effect cannot
    be checked is worse than no knob*), and must now also say that hidden columns left that
    list — on evidence, pointing at the recipe that carries it."""
    text = _two_filters_recipe().lower()
    assert "grouping" in text and "hidden columns" in text and "sort" in text
    assert "no knob" in text or "cannot be checked" in text, "the REASON survives"
    assert "hidden columns are offered" in text, "the conclusion moved, and it says so"
    assert "is_hidden" in text, "…and names the evidence that moved it"


# --------------------------------------------------------------------------- #
# AC10 — the three view permission rows, derived and never widened             #
# --------------------------------------------------------------------------- #

def _view_endpoints():
    """This family's endpoints, **derived from its own descriptors**.

    Filtered to the view family for the same reason the app-and-table matrix filters to its
    own: a claim about three call sites must not silently become a claim about another
    family's, which is exactly what an unfiltered projection would do the next time a family
    registers.
    """
    return sorted({d.endpoint for d in views.SCHEMA_OP_FAMILY.ops})


def test_AC10_the_three_view_endpoints_RESOLVE_to_a_write_row_with_evidence_and_a_label():
    from larkdocio import permissions as perm

    assert _view_endpoints() == [
        "/open-apis/bitable/v1/apps/:app_token/tables/:table_id/views",
        "/open-apis/bitable/v1/apps/:app_token/tables/:table_id/views/:view_id",
    ], "POST …/views plus the PATCH and the DELETE that share the …/views/{v} path"
    for endpoint in _view_endpoints():
        scopes = perm.scopes_for_endpoints((endpoint,), "write")
        assert scopes, f"{endpoint} resolves to no scope row — the requirement is nowhere"
        for scope in scopes:
            assert scope.evidence.strip(), (endpoint, scope.scope)
            assert scope.verification in perm.VERIFICATION_LABELS, scope.verification
        assert perm._table_row(endpoint, "write") is not None, endpoint


def test_AC10_NO_SCOPE_IS_WIDENED_a_view_write_needs_what_a_record_write_needs():
    from larkdocio import permissions as perm
    from larkdocio.base import write_ops

    record = {s.scope for d in write_ops.WRITE_OPS
              for s in perm.scopes_for_endpoints((d.endpoint,), "write")}
    view = {s.scope for e in _view_endpoints()
            for s in perm.scopes_for_endpoints((e,), "write")}
    assert view == record == {"bitable:app"}


def test_AC10_the_READ_row_is_UNTOUCHED_by_this_family():
    from larkdocio import permissions as perm

    read = {s.scope for d in base_ops.OPS
            for s in perm.scopes_for_endpoints((d.endpoint,), "read")}
    assert read == {"bitable:app:readonly"}, (
        "the read half must keep resolving to the readonly scope — including get_view, the one "
        "read op this story added")


def test_AC10_this_story_REQUESTS_WIDENS_AND_ESCALATES_NOTHING():
    from pathlib import Path

    from larkdocio.base import view_client, view_filters

    for module in (views, view_plan, view_client, view_filters):
        text = Path(module.__file__).read_text(encoding="utf-8").lower()
        for forbidden in ("request_scope", "grant_scope", "escalate"):
            assert forbidden not in text, (module.__name__, forbidden)


# --------------------------------------------------------------------------- #
# LD-282 — the read-back reports APPLIED for a numeric filter the server KEPT   #
# --------------------------------------------------------------------------- #

class _RetypingSchemaClient(_RecordingSchemaClient):
    """A schema client that lands the filter **and re-types it the way Lark does** — it parses
    the json-string value and stores a numeric-looking element unquoted, which is exactly the
    body `get_view` returned in the live session-P3 capture."""

    def update_view(self, app_token, table_id, view_id, *, view_name=None, filter_info=None,
                    hierarchy_config=None, hidden_fields=None):
        result = super().update_view(app_token, table_id, view_id,
                                     view_name=view_name, filter_info=filter_info,
                                     hierarchy_config=hierarchy_config,
                                     hidden_fields=hidden_fields)
        stored = (self.store[view_id].get("property") or {}).get("filter_info")
        for condition in (stored or {}).get("conditions", ()):
            if isinstance(condition.get("value"), str):
                elements = [_retype(e) for e in json.loads(condition["value"])]
                condition["value"] = json.dumps(elements, separators=(",", ":"))
        return result


def _retype(element):
    try:
        return int(element)
    except (TypeError, ValueError):
        return element


DATE_FILTER = view_filter(FilterSpec(conditions=(
    Condition(FieldId("fldPWMeSwR"), "is", ("ExactDate", 1786147200000)),)))


def test_LD282_a_DATE_filter_the_server_KEPT_is_reported_APPLIED_not_dropped():
    """The bug at the level the consumer met it: `code:0`, the filter **is** in `get_view`,
    and the apply-log said `dropped`. The only difference was JSON quoting Lark itself
    introduced."""
    store = {"vew01": {"view_name": "V", "view_type": "grid", "property": None}}
    client = _RetypingSchemaClient(store)
    read = _RecordingReadClient(store)
    log = schema_apply(
        schema_dry_run([view_plan.set_view_filter("appX", "tblX", "vew01", DATE_FILTER)]),
        client=client, read_client=read)
    entry = log.entries[0]
    assert entry.outcome == "applied", entry.refusal and entry.refusal.detail
    assert entry.read_back["echoes"] is True
    # And the disclosure still shows the server's OWN bytes, unretouched.
    assert entry.read_back["persisted"]["conditions"][0]["value"] == (
        '["ExactDate",1786147200000]')


def test_LD282_the_SWALLOW_CONTROL_still_fires_for_the_SAME_numeric_filter():
    """The fix may not cost the negative control: the grouping-style swallow — `code:0`,
    nothing stored — is still `dropped` when the filter carries a numeric value."""
    store = {"vew01": {"view_name": "V", "view_type": "grid", "property": None}}
    log, _s, client, _r = _run(
        [view_plan.set_view_filter("appX", "tblX", "vew01", DATE_FILTER)],
        store=store, swallow=True)
    assert log.entries[0].outcome == "dropped"
    assert log.entries[0].read_back["echoes"] is False
    assert client.calls == [("update_view", "vew01")]
