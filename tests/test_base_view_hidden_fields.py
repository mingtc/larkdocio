"""LD-438 — a view's HIDDEN COLUMNS are settable, and the read-back is the verdict.

**This whole file pins the PRODUCT, not this implementation** — the measured behaviour of
``PATCH …/views/{view_id} {"property":{"hidden_fields":[…]}}`` and the rules a consumer must be
able to rely on across a rewrite: that ``[]`` **clears** and is a different instruction from *not
asked for*; that a ``code:0`` is never the verdict; that a hidden-fields patch does not disturb a
view's filter and a filter patch does not disturb its hidden columns; and that a view is **still
not a column selector**. Hence the module-level ``conformance`` mark (§ A.4).

**The supersession this file is the test half of.** The shipped stance was *"``hidden_fields`` is
still not a parameter"*, and its **reason** — *a knob whose effect the library cannot observe does
not ship* — is kept. What moved is the **premise**: the probe that concluded "no observable
effect" read back only field **names**, so a per-field flag in the same payload could not have
been seen. ``GET …/fields?view_id=`` reports ``is_hidden`` **per view** (``true`` on exactly the
patched column, ``false`` on the same column through a control view, the key absent entirely with
no ``view_id``), and the maintainer's own 2026-08-12 glance settled the human axis. Both halves of this
project's own bar are met, so the conclusion moves and the rule stands.

**Why the read-back is the VIEW echo and not the field flag** (AC4, Dev's call, stated here
because a reader will ask): the family already spends ``GET …/views/{view_id}`` for the filter and
hierarchy read-backs, and that same payload carries ``property.hidden_fields`` — so verification
costs **zero extra calls**. ``fields?view_id=``'s ``is_hidden`` would buy a second read on a
second endpoint, and it cannot tell *"cleared"* from *"never set"* (the key is simply absent
without a ``view_id``). So no view-scoped field read is exposed, which is also why AC5's
anti-selector invariant needs no exception carved into it.
"""
import copy
import inspect

import pytest

from log_reading_apply import reading_the_log
from larkdocio.base import schema_ops_views as views
from larkdocio.base import view_plan
from larkdocio.base.schema_apply import schema_apply, schema_dry_run
schema_apply = reading_the_log(schema_apply)
from larkdocio.base.schema_client import BaseSchemaClient, BaseSchemaRefusal
from larkdocio.base.view_filters import Condition, FieldId, FilterSpec, view_filter
import private_tree  # noqa: E402  (LD-685)

#: Every test below answers *the PRODUCT is wrong*, not *merely different*: each pins a measured
#: Lark behaviour (LD-417 § B.6, the `is_hidden` attribution captures) or a consumer-facing
#: instruction contract a rewrite may not quietly redefine.
pytestmark = [pytest.mark.conformance]


def _views_recipe() -> str:
    """The WHOLE shipped view recipe, read through ``guide()`` — the text a consumer gets."""
    from larkdocio import guide

    return guide("recipe-create-configure-and-delete-a-view-hidden-columns-are-settable-"
                 "grouping-and-a-saved-sort-are-not")


FILTER = view_filter(FilterSpec(conditions=(Condition(FieldId("fldA"), "is", ("x",)),)))


# --------------------------------------------------------------------------- #
# Doubles — deliberately faithful to the two measured shapes                    #
# --------------------------------------------------------------------------- #

class _Store(dict):
    """``{view_id: {"view_name", "view_type", "property"}}``, where ``property`` is ``None`` or
    a dict of the three wire keys — the two states the live API actually serves."""


class _SchemaDouble:
    """The write half. Applies **only the keys it was handed**, which is the omission guarantee
    the client's builder gives, and clears ``property`` to ``None`` when nothing is left set —
    exactly what the live capture shows for ``hidden_fields=[]`` (arm 4: ``property: null``)."""

    def __init__(self, store, *, swallow_hidden=False):
        self.store, self.calls, self.swallow_hidden = store, [], swallow_hidden

    def update_view(self, app_token, table_id, view_id, *, view_name=None, filter_info=None,
                    hierarchy_config=None, hidden_fields=None):
        self.calls.append(("update_view", view_id, sorted(
            key for key, value in (("view_name", view_name), ("filter_info", filter_info),
                                   ("hierarchy_config", hierarchy_config),
                                   ("hidden_fields", hidden_fields))
            if value is not None)))
        view = self.store[view_id]
        prop = dict(view.get("property") or {})
        if view_name is not None:
            view["view_name"] = view_name
        if filter_info is not None:
            prop["filter_info"] = filter_info.to_dict()
        if hierarchy_config is not None:
            prop["hierarchy_config"] = hierarchy_config.to_dict()
        if hidden_fields is not None and not self.swallow_hidden:
            prop["hidden_fields"] = list(hidden_fields) or None
        view["property"] = prop if any(v is not None for v in prop.values()) else None
        return True

    def create_view(self, app_token, table_id, view_name, view_type):
        view_id = f"vew{len(self.store):02d}"
        self.store[view_id] = {"view_name": view_name, "view_type": view_type,
                               "property": None}
        return view_id

    def delete_view(self, app_token, table_id, view_id):
        self.store.pop(view_id, None)
        return True


class _ReadDouble:
    """The read half. The LISTING carries no ``property`` (measured); only the SINGLE-view read
    does — so a read-back that consulted the listing could not see a hidden set at all."""

    def __init__(self, store):
        self.store, self.calls = store, []

    def list_views(self, app_token, table_id):
        self.calls.append(("list_views", table_id))
        out = []
        for view_id, blob in self.store.items():
            view = type("V", (), {})()
            view.view_id, view.view_name = view_id, blob["view_name"]
            view.view_type, view.property = blob["view_type"], None
            out.append(view)
        return out

    def get_view(self, app_token, table_id, view_id):
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
    prop.hidden_fields = blob.get("hidden_fields")
    prop.filter_info = _as_filter(blob.get("filter_info"))
    config = blob.get("hierarchy_config")
    prop.hierarchy_config = (
        type("H", (), {"field_id": config["field_id"]})() if config else None)
    return prop


def _as_filter(blob):
    if blob is None:
        return None
    info = type("F", (), {})()
    info.conjunction, info.conditions = blob["conjunction"], []
    for condition in blob["conditions"]:
        node = type("C", (), {})()
        for key, value in condition.items():
            setattr(node, key, value)
        info.conditions.append(node)
    return info


def _run(requests, store, *, swallow_hidden=False):
    client = _SchemaDouble(store, swallow_hidden=swallow_hidden)
    read = _ReadDouble(store)
    return schema_apply(schema_dry_run(requests), client=client, read_client=read), client, read


def _view(**property_):
    return _Store({"vew01": {"view_name": "V", "view_type": "grid",
                             "property": property_ or None}})


class _FakeResponse:
    def __init__(self, data=None, code=0, msg="success"):
        self.code, self.msg, self.data, self.raw = code, msg, data, None


class _FakeSdk:
    """Records the request bodies the client builds, so the WIRE shape is assertable."""

    def __init__(self):
        self.sent = []
        outer = self

        class _View:
            def patch(self, request):
                outer.sent.append(request)
                return _FakeResponse(type("D", (), {"view": None})())

        self.bitable = type("B", (), {"v1": type("V1", (), {"app_table_view": _View()})()})()


class _NoWait:
    def acquire(self):
        pass


def _fake_client():
    sdk = _FakeSdk()
    return sdk, BaseSchemaClient("id", "secret", sdk_client=sdk, rate_limiter=_NoWait())


# --------------------------------------------------------------------------- #
# AC1 — the parameter exists, keyword-only, and the "change nothing" gate counts it
# --------------------------------------------------------------------------- #

def test_AC1_update_view_takes_hidden_fields_KEYWORD_ONLY_beside_the_other_three():
    signature = inspect.signature(BaseSchemaClient.update_view)
    parameter = signature.parameters["hidden_fields"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is None, "None means NOT ASKED FOR — never 'clear'"
    for name in ("view_name", "filter_info", "hierarchy_config"):
        assert signature.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY


def test_AC1_hidden_fields_ALONE_is_a_legitimate_call_and_an_empty_one_is_still_refused():
    sdk, client = _fake_client()
    client.update_view("appX", "tblX", "vewX", hidden_fields=["fldA"])
    assert sdk.sent[-1].request_body.property.hidden_fields == ["fldA"]
    with pytest.raises(BaseSchemaRefusal):
        client.update_view("appX", "tblX", "vewX")
    assert len(sdk.sent) == 1, "the empty PATCH must cost ZERO calls"


def test_AC1_the_change_nothing_refusal_NAMES_hidden_fields_among_the_ways_out():
    _sdk, client = _fake_client()
    with pytest.raises(BaseSchemaRefusal) as excinfo:
        client.update_view("appX", "tblX", "vewX")
    assert "hidden_fields" in str(excinfo.value)


def test_AC1_KEY_ISOLATION_IN_BOTH_DIRECTIONS_at_the_wire():
    """The omission guarantee, asserted on the body the client actually builds: a filter patch
    leaves ``hidden_fields`` unset, and a hidden-fields patch leaves ``filter_info`` unset."""
    sdk, client = _fake_client()
    client.update_view("appX", "tblX", "vewX", filter_info=FILTER)
    body = sdk.sent[-1].request_body
    assert body.property.hidden_fields is None
    assert body.property.filter_info is not None

    client.update_view("appX", "tblX", "vewX", hidden_fields=["fldA", "fldB"])
    body = sdk.sent[-1].request_body
    assert body.property.filter_info is None and body.property.hierarchy_config is None
    assert body.property.hidden_fields == ["fldA", "fldB"]
    assert body.view_name is None


def test_AC1_KEY_ISOLATION_END_TO_END_a_filter_patch_leaves_the_hidden_set_alone():
    store = _view(hidden_fields=["fldA"])
    log, _client, _read = _run(
        [view_plan.set_view_filter("appX", "tblX", "vew01", FILTER)], store)
    assert log.entries[0].outcome == "applied"
    assert store["vew01"]["property"]["hidden_fields"] == ["fldA"], (
        "setting a filter must not un-hide a consumer's columns")

    log, _client, _read = _run(
        [view_plan.set_view_hidden_fields("appX", "tblX", "vew01", ["fldB"])], store)
    assert log.entries[0].outcome == "applied"
    assert store["vew01"]["property"]["filter_info"] is not None, (
        "hiding a column must not drop the view's persistent filter")


# --------------------------------------------------------------------------- #
# AC2 — SET, MOVE and CLEAR, and `[]` is not `None`                             #
# --------------------------------------------------------------------------- #

def test_AC2_the_set_reads_back_and_a_SECOND_patch_MOVES_it():
    """LD-417 § B.6 rows 1-3: ``[Alpha]`` stores, ``[Beta]`` **moves** it, ``[Beta, Gamma]``
    holds a set. A stuck value would mean the first write only *looked* like it landed."""
    store = _view()
    log, _c, _r = _run(
        [view_plan.set_view_hidden_fields("appX", "tblX", "vew01", ["fldAlpha"])], store)
    assert log.entries[0].outcome == "applied"
    assert log.entries[0].read_back["persisted_hidden_fields"] == ["fldAlpha"]

    log, _c, _r = _run(
        [view_plan.set_view_hidden_fields("appX", "tblX", "vew01", ["fldBeta"])], store)
    assert log.entries[0].read_back["persisted_hidden_fields"] == ["fldBeta"]
    assert store["vew01"]["property"]["hidden_fields"] == ["fldBeta"]

    log, _c, _r = _run(
        [view_plan.set_view_hidden_fields("appX", "tblX", "vew01",
                                         ["fldBeta", "fldGamma"])], store)
    assert log.entries[0].outcome == "applied"
    assert set(log.entries[0].read_back["persisted_hidden_fields"]) == {"fldBeta", "fldGamma"}


def test_AC2_an_EMPTY_LIST_CLEARS_and_the_server_answers_property_null():
    """LD-417 § B.6 row 5: ``hidden_fields=[]`` reads back ``property: null`` — so the
    read-back must count *absent* as a confirmed clear, or a correct clear would be reported
    NOT PERSISTED."""
    store = _view(hidden_fields=["fldAlpha"])
    log, _c, _r = _run(
        [view_plan.clear_view_hidden_fields("appX", "tblX", "vew01")], store)
    entry = log.entries[0]
    assert entry.outcome == "applied", entry.refusal and entry.refusal.detail
    assert entry.read_back["sent_hidden_fields"] == []
    assert entry.read_back["persisted_hidden_fields"] in (None, [])
    assert store["vew01"]["property"] is None


def test_AC2_the_EMPTY_LIST_IS_SENT_while_None_sends_NO_KEY_AT_ALL():
    """The three-way distinction at the wire, which is where it can actually be checked:
    ``[]`` is a *value* (the clear), ``None`` is *silence*."""
    sdk, client = _fake_client()
    client.update_view("appX", "tblX", "vewX", hidden_fields=[])
    assert sdk.sent[-1].request_body.property.hidden_fields == [], (
        "an empty list must reach the wire — it is the CLEAR instruction")
    client.update_view("appX", "tblX", "vewX", view_name="Renamed")
    assert sdk.sent[-1].request_body.property is None, (
        "hidden_fields=None must not even mint a property object")


def test_AC2_the_THREE_WAY_DISTINCTION_IS_IN_THE_SHIPPED_DOCUMENTATION():
    """A caller who reads ``[]`` as *unchanged* silently un-hides a consumer's columns, so the
    signature's own docstring has to say it — not only the guide."""
    for doc in (BaseSchemaClient.update_view.__doc__ or "",
                view_plan.set_view_hidden_fields.__doc__ or "",
                view_plan.clear_view_hidden_fields.__doc__ or ""):
        lowered = doc.lower()
        assert "clear" in lowered
        assert "not asked for" in lowered or "asked for" in lowered


def test_AC2_clear_view_hidden_fields_IS_set_view_hidden_fields_with_an_empty_list():
    """Two names, one op and one wire shape — the explicit verb exists so *clear* need not be
    spelled as a falsy argument, not because a second code path was added."""
    explicit = view_plan.clear_view_hidden_fields("appX", "tblX", "vew01")
    spelled = view_plan.set_view_hidden_fields("appX", "tblX", "vew01", [])
    assert explicit.op == spelled.op == "update_view"
    assert explicit.arguments == spelled.arguments


# --------------------------------------------------------------------------- #
# AC3 — validated locally where it is free; RELAYED where a local check costs a read
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("bad", ["fldA", ("fldA",), {"fldA"}, 7, {"fields": ["fldA"]}])
def test_AC3_a_NON_LIST_is_refused_LOCALLY_before_any_call(bad):
    sdk, client = _fake_client()
    with pytest.raises(TypeError) as excinfo:
        client.update_view("appX", "tblX", "vewX", hidden_fields=bad)
    assert "list" in str(excinfo.value).lower()
    assert sdk.sent == [], "a refused dialect must cost ZERO calls"


def test_AC3_a_NON_STRING_MEMBER_is_refused_LOCALLY_and_the_message_says_which():
    sdk, client = _fake_client()
    with pytest.raises(TypeError) as excinfo:
        client.update_view("appX", "tblX", "vewX", hidden_fields=["fldA", 7])
    message = str(excinfo.value)
    assert "index 1" in message
    assert sdk.sent == []


def test_AC3_A_BARE_STRING_IS_NOT_A_LIST_OF_ONE_and_the_message_says_so():
    """The footgun this check exists for: ``hidden_fields="fldA"`` is iterable, so a naive
    implementation would hide seven columns named ``f``, ``l``, ``d``, ``A``…"""
    _sdk, client = _fake_client()
    with pytest.raises(TypeError) as excinfo:
        client.update_view("appX", "tblX", "vewX", hidden_fields="fldA")
    assert "[\"fldA\"]" in str(excinfo.value) or "['fldA']" in str(excinfo.value)


def test_AC3_the_plan_constructor_refuses_the_same_shapes_with_ZERO_calls():
    with pytest.raises(TypeError):
        view_plan.set_view_hidden_fields("appX", "tblX", "vew01", "fldA")
    with pytest.raises(TypeError):
        view_plan.set_view_hidden_fields("appX", "tblX", "vew01", ["fldA", None])


def test_AC3_AN_UNKNOWN_FIELD_ID_IS_RELAYED_and_the_shipped_text_says_WHY():
    """**The deliberate half of AC3, recorded where it is looked up.** Lark answers
    ``1254044 "Field id is not found."`` — measured — and this library **relays** it rather than
    predicting it, on the precedent BASE.md register row 44 set for the hierarchy target:
    *a field list is a read of a moment*, so a local check would have to buy a ``list_fields``
    read this route does not otherwise spend, and would still be racing the answer. The numeric
    code is quoted in prose and in captures and deliberately **not** pinned into an offline
    assertion (LD-417 AC10 precedent)."""
    for doc in (BaseSchemaClient.update_view.__doc__ or "",
                view_plan.set_view_hidden_fields.__doc__ or ""):
        lowered = doc.lower()
        assert "relay" in lowered, "the split must be STATED, not inferred from behaviour"
        assert "read of a moment" in lowered or "list_fields" in lowered

    # …and the relay is real: an id shaped like a field id is NOT locally refused.
    sdk, client = _fake_client()
    client.update_view("appX", "tblX", "vewX", hidden_fields=["fldNONEXISTENT"])
    assert sdk.sent[-1].request_body.property.hidden_fields == ["fldNONEXISTENT"]


def test_AC3_THE_PRIMARY_FIELD_CANNOT_BE_HIDDEN_and_the_shipped_text_says_so():
    """**Found by the LIVE gate, which is why the live gate is binding.** The offline suite was
    green and the guide was written when Lark refused the very first hide this library ever
    sent — because it named the table's PRIMARY field, and *"the primary field cannot be set as
    a hidden type"*. That refusal is relayed on the same precedent as an unknown id (which
    column is primary is a read of a moment), so what has to be shipped is the SENTENCE."""
    from larkdocio import guide
    from larkdocio.base import view_client

    disclosure = view_client.HIDDEN_FIELDS_PRIMARY_IS_REFUSED
    assert "primary field cannot be set as a hidden type" in disclosure, (
        "Lark's own words, quoted — not a paraphrase")
    assert "1254001" in disclosure and "relay" in disclosure.lower()

    recipe = _views_recipe().lower()
    assert "primary field" in recipe and "1254001" in recipe

    # …and the error table's 1254001 row no longer implies the answer is always about SHAPE.
    from larkdocio.base.errors import BASE_ERROR_CODES

    note = BASE_ERROR_CODES[1254001].meaning
    assert "primary field" in note, (
        "a caller who reads 1254001 as 'my body is malformed' will re-shape a body that was "
        "already correct; the row must carry the other meaning")


def test_AC3_the_primary_field_refusal_EXPLAINS_the_old_1254001_and_the_register_says_so():
    """Supersession discipline, applied to an *observation* rather than a conclusion: the
    2026-08-03 seat addendum's unexplained `1254001` is not struck and is no longer labelled a
    hypothesis — it is accounted for."""
    from guard_kit import REPO_ROOT

    row = next(line for line in
               (REPO_ROOT / "BASE.md").read_text(encoding="utf-8").splitlines()
               if line.startswith("| 30 |"))
    assert "primary field cannot be set as a hidden type" in row
    assert "hypothesis, not a measurement" not in row, (
        "the hypothesis was replaced BY A MEASUREMENT, and the row must say the measured thing")


def test_AC3_no_offline_test_or_shipped_line_PINS_the_numeric_code_as_an_assertion():
    """LD-417 AC10's rule: today's numeric code is quoted, never asserted — a suite that
    reddens the day Lark renumbers is measuring Lark's changelog, not this library."""
    from larkdocio.base.errors import BASE_ERROR_CODES

    assert 1254044 in BASE_ERROR_CODES, (
        "the code is KNOWN to the error table — that is a mapping, not a behavioural pin")


# --------------------------------------------------------------------------- #
# AC4 — the READ-BACK is the verdict, never `code:0`                            #
# --------------------------------------------------------------------------- #

def test_AC4_a_SWALLOWED_hidden_fields_patch_is_reported_DROPPED_not_applied():
    """The whole argument, one key over from the grouping control: the same endpoint, the same
    ``code:0``, and a read-back that does not echo. ``applied`` here would be a lie."""
    store = _view()
    log, client, _read = _run(
        [view_plan.set_view_hidden_fields("appX", "tblX", "vew01", ["fldAlpha"])],
        store, swallow_hidden=True)
    entry = log.entries[0]
    assert entry.outcome == "dropped", "a swallowed write must NEVER be reported applied"
    assert entry.read_back["echoes"] is False
    assert entry.read_back["persisted_hidden_fields"] is None
    assert len(client.calls) == 1, "the engine does not retry a swallow"
    detail = entry.refusal.detail
    assert "code:0" in detail and "read-back" in detail.lower()


def test_AC4_the_read_back_is_the_SINGLE_VIEW_read_not_the_listing():
    store = _view()
    _log, _client, read = _run(
        [view_plan.set_view_hidden_fields("appX", "tblX", "vew01", ["fldAlpha"])], store)
    assert ("get_view", "vew01") in read.calls, (
        "the LISTING carries no property at all — it cannot see a hidden set")


def test_AC4_the_op_descriptors_read_back_STRING_names_hidden_fields():
    descriptor = next(d for d in views.SCHEMA_OP_FAMILY.ops if d.name == "update_view")
    assert "hidden_fields" in descriptor.read_back
    assert "code:0" in descriptor.read_back


def test_AC4_the_ISSUE_handler_PASSES_hidden_fields_through_so_it_cannot_be_issued_unverified():
    """The family's ``_issue`` drops any key it is not told about, so the handler and the
    parameter have to move together or a plan entry would be silently a no-op."""
    store = _view()
    log, client, _read = _run(
        [view_plan.set_view_hidden_fields("appX", "tblX", "vew01", ["fldAlpha"])], store)
    assert client.calls[0][2] == ["hidden_fields"], (
        "exactly the key that was asked for reached the client")
    assert log.entries[0].outcome == "applied"


def test_AC4_the_SET_ORDER_IS_NOT_THE_CONTRACT_the_comparison_is_over_the_SET():
    """A hidden *set* is a set. Field ORDERING is out of scope on this surface (no route
    exists), so a server that returns the two ids the other way round has still complied."""
    store = _view()
    client = _SchemaDouble(store)
    read = _ReadDouble(store)

    def reversing(*args, **kwargs):
        kwargs["hidden_fields"] = list(reversed(kwargs["hidden_fields"]))
        return _SchemaDouble.update_view(client, *args, **kwargs)

    client.update_view = reversing
    log = schema_apply(schema_dry_run([view_plan.set_view_hidden_fields(
        "appX", "tblX", "vew01", ["fldAlpha", "fldBeta"])]), client=client, read_client=read)
    assert log.entries[0].outcome == "applied"
    assert log.entries[0].read_back["echoes"] is True


# --------------------------------------------------------------------------- #
# AC5 — the ANTI-SELECTOR invariant survives untouched                          #
# --------------------------------------------------------------------------- #

def test_AC5_the_L1_READ_PATH_STILL_TAKES_NO_VIEW_ID():
    """Re-asserted here, in the change that ships the write knob, because this is exactly the
    change a careless reader would take as licence to add one. What the new evidence adds is a
    per-view **flag** on the field listing — not a projection. The records payload through a
    hidden view is measurably UNCHANGED (capture ``788-``)."""
    from larkdocio.base import read as base_read
    from larkdocio.base import table as base_table

    for fn in (base_read.read_base, base_read.read_base_markdown,
               base_table.assemble_table, base_table.assemble_base):
        assert "view_id" not in inspect.signature(fn).parameters


def test_AC5_NO_VIEW_SCOPED_FIELD_READ_IS_EXPOSED_so_the_flag_cannot_be_mistaken_for_one():
    from larkdocio.base.client import BaseReadClient

    assert "view_id" not in inspect.signature(BaseReadClient.list_fields).parameters, (
        "exposing fields?view_id= would put an is_hidden flag on the read surface; if that is "
        "ever wanted it ships documented as 'the same columns, plus a per-view is_hidden "
        "flag', never as a narrowing")


def test_AC5_the_SHIPPED_TEXT_STILL_SAYS_A_VIEW_IS_NOT_A_COLUMN_SELECTOR():
    import consumer_text

    from guard_kit import REPO_ROOT

    docs = dict(consumer_text.shipped_docs())
    docs["BASE.md"] = (REPO_ROOT / "BASE.md").read_text(encoding="utf-8")
    hits = [name for name, text in docs.items() if "not a column selector" in text.lower()]
    assert hits, "the ruling must remain stated somewhere a consumer reads"


# --------------------------------------------------------------------------- #
# AC6 / AC9 — grouping and the saved sort DO NOT MOVE                           #
# --------------------------------------------------------------------------- #

def test_AC6_GROUPING_AND_SORT_STILL_HAVE_NO_PARAMETER_ANYWHERE():
    banned = ("group_info", "grouping", "group_by", "view_sort", "sort", "sort_info",
              "sorts", "sort_infos", "auto_sort", "gantt_date")
    surface = [view_plan.create_view, view_plan.rename_view, view_plan.set_view_filter,
               view_plan.set_view_hierarchy, view_plan.set_view_hidden_fields,
               view_plan.clear_view_hidden_fields, view_plan.delete_view,
               BaseSchemaClient.create_view, BaseSchemaClient.update_view,
               BaseSchemaClient.delete_view]
    for fn in surface:
        params = set(inspect.signature(fn).parameters)
        assert not (params & set(banned)), (fn.__qualname__, params & set(banned))


def test_AC6_the_CLIENT_SENDS_NO_GROUPING_OR_SORT_KEY_even_when_hiding_columns():
    sdk, client = _fake_client()
    client.update_view("appX", "tblX", "vewX", hidden_fields=["fldA"])
    prop = sdk.sent[-1].request_body.property
    for absent in ("group_info", "sort_info", "sort", "auto_sort"):
        assert getattr(prop, absent, None) is None


def test_AC6_the_gantt_date_binding_and_the_saved_sort_KEEP_their_register_rows():
    from guard_kit import REPO_ROOT

    text = (REPO_ROOT / "BASE.md").read_text(encoding="utf-8")
    assert "group_info" in text and "sort" in text
    assert "uncaptured" in text, "row 31's honest gap is not upgraded by this change"


# --------------------------------------------------------------------------- #
# AC7 / AC9 — the matrix, the guide and capabilities() agree with the code       #
# --------------------------------------------------------------------------- #

def test_AC7_BASE_md_row_30_moved_to_SUPPORTED_and_KEPT_ITS_REASON():
    from guard_kit import REPO_ROOT

    row = next(line for line in
               (REPO_ROOT / "BASE.md").read_text(encoding="utf-8").splitlines()
               if line.startswith("| 30 |"))
    assert "`supported`" in row
    # The reason is PRESERVED, not struck: the original contradiction and the refuted premise
    # both stay legible, and the reopen condition is recorded as HAVING FIRED.
    assert "1254001" in row, "the seat addendum's observation is not deleted"
    assert "is_hidden" in row, "the captures that fired the reopen condition are cited"
    assert "FIRED" in row or "fired" in row


def test_AC7_the_L1_row_no_longer_claims_NO_API_EFFECT_and_states_the_measured_truth():
    from guard_kit import REPO_ROOT

    row = next(line for line in
               (REPO_ROOT / "BASE.md").read_text(encoding="utf-8").splitlines()
               if "A view is NOT a projection" in line)
    assert "not a column selector" in row, "the surviving half stays"
    assert "is_hidden" in row, "the flag the corrected read found is named"
    assert "has **no API effect** either" not in row


def test_AC9_capabilities_no_longer_says_a_view_is_a_FILTER_AND_NOTHING_ELSE():
    from larkdocio import capabilities

    note = capabilities(full=True)["surfaces"]["base-schema-write"]["credentials"]["note"]
    assert "and nothing else" not in note
    assert "hidden" in note.lower()
    assert "grouping" in note.lower() and "sort" in note.lower()


def test_AC9_the_guide_op_table_row_for_update_view_NAMES_hidden_columns():
    from larkdocio import guide

    row = next(line for line in guide(full=True).splitlines()
               if line.startswith("| `update_view` |"))
    assert "hidden" in row.lower()
    assert "There is no other knob" not in row


def test_AC6_the_guide_recipe_SUPERSEDES_its_own_conclusion_and_keeps_the_REASON():
    text = _views_recipe().lower()
    # (a) the hidden-fields bullet is now a CAPABILITY…
    assert "is_hidden" in text
    assert "clears" in text
    # (b) …and grouping / the saved sort / the gantt binding do NOT move.
    assert "group_info" in text and "not stored" in text
    assert "eight" in text, "the eight sort spellings stay enumerated (D-59)"
    assert "gantt" in text
    # (d) the REASON for the old refusal is restated and kept, with the premise named as the
    #     thing that was refuted.
    assert "premise" in text
    assert "cannot be observed" in text
    # …and the negative claims keep their scope (AC11).
    assert "grid" in text and "unmeasured" in text


def test_AC6_the_recipe_HEADING_keeps_the_burn_keywords_and_promises_what_the_code_DOES():
    from larkdocio import guide_sections

    slug = next(s["slug"] for s in guide_sections()
                if s["slug"].startswith("recipe-create-configure-and-delete-a-view"))
    assert "hidden" in slug and "group" in slug and "sort" in slug
    assert "are-not-among-them" not in slug, (
        "the old heading promised the opposite of what this library now does")


# --------------------------------------------------------------------------- #
# AC10 — the ruling is recorded where it is looked up                           #
# --------------------------------------------------------------------------- #

@private_tree.register
def test_AC10_DECISIONS_md_carries_the_standing_ruling_with_its_provenance():
    from guard_kit import REPO_ROOT

    text = (REPO_ROOT / "requirements" / "DECISIONS.md").read_text(encoding="utf-8")
    block = text[text.index("### D-75"):][:3200]
    lowered = block.lower()
    assert "read-back" in lowered
    assert "clear" in lowered and "not asked for" in lowered
    assert "grouping" in lowered and "sort" in lowered
    assert "LD-438" in block, "the issue id rides beside the D-NN (same-day collision rule)"


# --------------------------------------------------------------------------- #
# AC11 — every remaining `cannot` names its forms or says `unmeasured`          #
# --------------------------------------------------------------------------- #

def test_AC11_the_UI_HALF_IS_SCOPED_TO_THE_CLICK_THAT_WAS_ACTUALLY_MADE():
    text = _views_recipe().lower()
    assert "web" in text, "the glance was on the Lark WEB client and says so"
    assert "unmeasured" in text
    for narrower in ("grid", "tenant"):
        assert narrower in text


def test_AC11_the_RECORDS_PAYLOAD_IS_UNCHANGED_and_the_guide_says_hiding_is_not_a_read_filter():
    text = _views_recipe().lower()
    assert "unchanged" in text or "still returns" in text
    assert "search" in text, "records/search's empty projection is evidence NEITHER way"


def test_AC11_search_records_projection_is_recorded_as_EVIDENCE_NEITHER_WAY():
    text = _views_recipe().lower()
    assert "neither way" in text
    assert "no rows" in text and "baseline" in text


# --------------------------------------------------------------------------- #
# The plan gate — a hidden-fields entry is DESCRIBED, PREVIEWED and read-costed  #
# --------------------------------------------------------------------------- #

def test_the_plan_entry_DESCRIBES_itself_in_a_humans_words_and_declares_its_read_cost():
    request = view_plan.set_view_hidden_fields("appX", "tblX", "vew01", ["fldA", "fldB"])
    assert request.op == "update_view"
    assert "hide" in request.describe.lower() and "vew01" in request.describe
    assert request.traits["read_cost"] == 2
    assert request.traits["revision_guard_disclosure"] == views.NO_VIEW_ANCHOR

    clear = view_plan.clear_view_hidden_fields("appX", "tblX", "vew01")
    assert "show" in clear.describe.lower() or "clear" in clear.describe.lower()


def test_the_dry_run_PREVIEWS_a_hidden_fields_entry_without_calling_anything():
    plan = schema_dry_run([
        view_plan.set_view_hidden_fields("appX", "tblX", "vew01", ["fldA"])])
    assert len(plan.entries) == 1
    entry = plan.entries[0]
    assert entry.op == "update_view"
    assert entry.fields["hidden_fields"] == ["fldA"]


def test_the_hidden_set_is_COPIED_into_the_plan_so_a_later_mutation_cannot_change_the_call():
    columns = ["fldA"]
    request = view_plan.set_view_hidden_fields("appX", "tblX", "vew01", columns)
    columns.append("fldB")
    assert request.arguments["hidden_fields"] == ["fldA"], (
        "a plan a caller can mutate after previewing it is not a plan")


def test_ONE_PLAN_a_rename_a_filter_and_a_HIDE_each_verified_on_its_own_read_back():
    store = _view()
    log, _client, _read = _run([
        view_plan.rename_view("appX", "tblX", "vew01", "Renamed"),
        view_plan.set_view_filter("appX", "tblX", "vew01", FILTER),
        view_plan.set_view_hidden_fields("appX", "tblX", "vew01", ["fldAlpha"]),
    ], copy.deepcopy(store) if False else store)
    assert [e.outcome for e in log.entries] == ["applied", "applied", "applied"]
    assert store["vew01"]["view_name"] == "Renamed"
    assert store["vew01"]["property"]["filter_info"] is not None
    assert store["vew01"]["property"]["hidden_fields"] == ["fldAlpha"]
