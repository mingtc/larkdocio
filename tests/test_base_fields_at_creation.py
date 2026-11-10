"""LD-336 — THE BLOCKER FIX: a table's whole column kit lands **with the table**, in ONE
plan-gated call that never touches the down ``/fields`` write family.

Everything here is offline. The claim under test is not "the body carries a key" — that would
be an R12 lie (`schema_ops_app_table` § "Nothing here is verified by ``code:0``") — it is that
**the field definitions ride the SAME gate ``create_field`` rides**, refuse **at plan time with
zero calls**, and reach the wire through the pinned SDK's own builders. The live half (the
created table's own field list) is arm 5 of ``tests/test_live_base_schema_gate.py``.

**The amended ruling.** ``fields`` used to be `not sent` on a table create, on the reasoning
that field authoring rides an allow-list and a table create must not be a side door around
that gate. That *reason* is preserved and the *conclusion* is superseded: the array goes
**through** the gate — :func:`larkdocio.base.field_vocabulary.check_authorable` and
:func:`larkdocio.base.field_authoring.build_property`, the same two seams
``create_field`` calls — so a definition ``create_field`` would refuse is refused here too,
locally, before a client is touched. ``default_view_name`` is **still not sent**, and this
module asserts that half explicitly rather than letting it be swept up — with its reason
corrected by LD-344 (Option A): the key is not withheld as *unprovable* but because Lark's
``create_table`` **rejects** a body carrying it (``1254001 WrongRequestBody``, no table created;
measured twice, raw core + pinned SDK, probe ``ld344-01``); the view name itself is readable via
``list_views``.
"""
import json

import pytest
from lark_oapi.core.json import JSON

from base_schema_fakes import (
    FakeBaseWorld,
    NoSleep,
    ScriptedSchemaClient,
    batch_create_echo,
    create_table_echo,
    schema_client,
)
from log_reading_apply import reading_the_log
from larkdocio.base import schema_ops_app_table as app_table
from larkdocio.base.field_authoring import (
    FIELD_PROPERTY_SHAPES,
    FieldAuthoringRefusal,
    REQUIRED_PROPERTY_KINDS,
    UncapturedFieldPropertyError,
)
from larkdocio.base.field_vocabulary import UnauthorableFieldError, UncapturedFieldPairError
from larkdocio.base.schema_apply import schema_apply, schema_dry_run
schema_apply = reading_the_log(schema_apply)
from larkdocio.base.schema_plan import batch_create_tables, create_table

TEXT = FIELD_PROPERTY_SHAPES["Text"].field_type
CURRENCY = FIELD_PROPERTY_SHAPES["Currency"].field_type
DATETIME = FIELD_PROPERTY_SHAPES["DateTime"].field_type

#: A three-kind kit: a bare ``Text``, a kind whose ``property`` is MANDATORY (``Currency`` — one
#: of ``field_authoring.REQUIRED_PROPERTY_KINDS``, and measured landing on THIS route), and one
#: more. ``Rating`` is the required-property kind this route refuses (probe ``ld336-02``), which
#: is why the mandatory-property member here is ``Currency`` rather than the obvious one.
KIT = (
    {"field_name": "Title", "field_type": TEXT, "ui_type": "Text"},
    {"field_name": "Budget", "field_type": CURRENCY, "ui_type": "Currency",
     "properties": {"formatter": "0.00", "currency_code": "USD"}},
    {"field_name": "Due", "field_type": DATETIME, "ui_type": "DateTime",
     "properties": {"date_formatter": "yyyy/MM/dd"}},
)


def body_of(request):
    raw = getattr(request, "body", None)
    if raw is None:
        return {}
    if isinstance(raw, (bytes, bytearray)):
        return json.loads(raw.decode("utf-8"))
    if isinstance(raw, str):
        return json.loads(raw)
    return json.loads(JSON.marshal(raw))


# --------------------------------------------------------------------------- #
# AC3 — the body: omitted entirely when not given, per-table when it is        #
# --------------------------------------------------------------------------- #

def test_ac3_fields_is_OMITTED_ENTIRELY_when_not_given_not_null_and_not_empty_list():
    """The byte-identical half. No-columns-asked-for reaches the wire as the **absent key**,
    never ``null`` and never ``[]``.

    **LD-322 amended where that is observable, not what it is.** ``None`` / ``()`` / ``[]`` on a
    ``create_table`` are now all the same *refusal* — a table is never created with a primary
    column Lark named — so the absent-key body is asserted on the verb that still sends it, the
    batch, whose ``tables`` are the same ``ReqTable`` model.
    """
    for kit in (None, (), []):
        with pytest.raises(FieldAuthoringRefusal):
            create_table("app", "t", fields=kit)

        batch = schema_client(table_batch_create=[batch_create_echo()])
        batch.batch_create_tables("app", ["a", "b"], fields=kit,
                                  accept_locale_default_primary=True)
        assert body_of(batch._sdk.bitable.v1.app_table.batch_create.requests[0]) == {
            "tables": [{"name": "a"}, {"name": "b"}]}, kit


def test_ac3_create_table_carries_the_WHOLE_KIT_in_ONE_body_R12():
    """R12's parameter-free control: the body must DIFFER from the kit-less one, and each
    definition must land where the endpoint reads it."""
    # LD-322: the parameter-free control is now the MINIMAL LEGAL create — a create with no
    # kit at all is refused (a table is never created with a primary column Lark named), so the
    # thing the kitted body is held against is the one-entry `primary_field_name=` form.
    control = schema_client(table_create=[create_table_echo()])
    control.create_table("app", "Items", primary_field_name="Title")
    kitted = schema_client(table_create=[create_table_echo()])
    kitted.create_table("app", "Items", fields=KIT)

    bare = body_of(control._sdk.bitable.v1.app_table.create.requests[0])
    with_kit = body_of(kitted._sdk.bitable.v1.app_table.create.requests[0])
    assert with_kit != bare
    assert with_kit == {"table": {"name": "Items", "fields": [
        {"field_name": "Title", "type": TEXT, "ui_type": "Text"},
        {"field_name": "Budget", "type": CURRENCY, "ui_type": "Currency",
         "property": {"formatter": "0.00", "currency_code": "USD"}},
        {"field_name": "Due", "type": DATETIME, "ui_type": "DateTime",
         "property": {"date_formatter": "yyyy/MM/dd"}},
    ]}}
    assert kitted.api_calls == 1, "a table and its whole column kit are ONE call — the point"


def test_ac3_batch_create_tables_REFUSES_a_column_kit_because_LARK_IGNORES_IT():
    """**The measured refutation.** The batch's ``tables`` are the SAME ``ReqTable`` model the
    single create uses, so a kit is transportable there — and Lark accepts it at ``code:0`` and
    creates every table WITHOUT it, each with the locale-named default primary and none of the
    kit (probe ``ld336-02``, proved server-side by sending the identical hand-written body
    through the raw HTTP core). Forwarding a parameter measured to do nothing is what R12 exists
    to forbid, so the kit refuses here — with the route that DOES author it named.
    """
    for door in (
        lambda kit: batch_create_tables("app", ["a", "b"], fields=kit),
        lambda kit: schema_client(table_batch_create=[batch_create_echo()])
        .batch_create_tables("app", ["a", "b"], fields=kit),
    ):
        with pytest.raises(FieldAuthoringRefusal) as excinfo:
            door([KIT[:1], None])
        message = str(excinfo.value)
        assert "code:0" in message and "WITHOUT it" in message, message
        assert "create_table" in message, "the refusal names the route that DOES author a kit"
        assert "Nothing was sent." in message


def test_ac3_the_batch_verb_is_BYTE_IDENTICAL_to_todays_and_a_kitless_list_is_accepted():
    """The refusal must not cost the batch its own behaviour: names still ride in one call, and
    an all-``None`` kit list is simply no kit rather than an error."""
    client = schema_client(table_batch_create=[batch_create_echo()])
    client.batch_create_tables("app", ["a", "b"], fields=[None, None],
                               accept_locale_default_primary=True)
    assert body_of(client._sdk.bitable.v1.app_table.batch_create.requests[0]) == {
        "tables": [{"name": "a"}, {"name": "b"}]}
    assert client.api_calls == 1

    entry = schema_dry_run([batch_create_tables(
        "app", ["a", "b"], accept_locale_default_primary=True)]).entries[0]
    assert entry.fields == {"app_token": "app", "names": ["a", "b"]}
    assert entry.read_cost == 1, "no field read: this verb authors no columns"


def test_ac3_the_CLIENT_SEAM_RECHECKS_the_gate_rather_than_trusting_the_plan():
    """`create_field`'s own reason, applied to this door: a refusal a caller can read beats a
    round trip to an opaque code whichever door they came in through."""
    client = schema_client(table_create=[create_table_echo()])
    with pytest.raises(UnauthorableFieldError):
        client.create_table("app", "t", fields=[
            {"field_name": "Ref", "field_type": 19, "ui_type": "Lookup"}])
    assert client.api_calls == 0, "the seam refused before the transport was reached"


# --------------------------------------------------------------------------- #
# AC2 — the SAME gate as create_field, at PLAN time, with ZERO calls           #
# --------------------------------------------------------------------------- #

def test_ac2_an_UNAUTHORABLE_kind_ANYWHERE_in_the_kit_refuses_the_WHOLE_op():
    """A partial create that silently drops one column is the failure this refuses."""
    with pytest.raises(UnauthorableFieldError) as excinfo:
        create_table("app", "t", fields=[
            KIT[0],
            {"field_name": "Manager", "field_type": 19, "ui_type": "Lookup"},
            KIT[2],
        ])
    message = str(excinfo.value)
    assert "index 1" in message and "'Manager'" in message, message
    assert "Lookup" in message


def test_ac2_an_UNCAPTURED_PAIR_in_the_kit_refuses_with_the_EXISTING_type():
    """Two individually-legal coordinates can still describe a column no registry carries —
    ``field_type=1`` (Text) with ``ui_type="Number"`` (whose storage type is 2). No new
    exception type is minted."""
    with pytest.raises(UncapturedFieldPairError) as excinfo:
        create_table("app", "t", fields=[{"field_name": "Count", "field_type": TEXT,
                                          "ui_type": "Number"}])
    assert "index 0" in str(excinfo.value) and "'Count'" in str(excinfo.value)
    assert isinstance(excinfo.value, UnauthorableFieldError), (
        "the pair refusal must stay a SUBCLASS, so a caller catching the family keeps catching")


#: The mandatory-``property`` kinds THIS route authors — the shared required list minus the ones
#: it refuses outright (probe ``ld336-02``), which are refused by a different, earlier branch.
REQUIRED_AND_AUTHORABLE_AT_CREATION = tuple(
    ui_type for ui_type in REQUIRED_PROPERTY_KINDS
    if ui_type not in app_table.NOT_AUTHORABLE_AT_CREATION)


@pytest.mark.parametrize("ui_type", REQUIRED_AND_AUTHORABLE_AT_CREATION)
def test_ac2_a_REQUIRED_PROPERTY_kind_with_no_property_refuses_the_whole_kit(ui_type):
    """The same enforcement ``create_field`` applies — ``build_property``'s own required
    branch, reached because the kit calls the one shared builder."""
    with pytest.raises(UncapturedFieldPropertyError) as excinfo:
        create_table("app", "t", fields=[
            KIT[0],
            {"field_name": f"Needs{ui_type}",
             "field_type": FIELD_PROPERTY_SHAPES[ui_type].field_type, "ui_type": ui_type},
        ])
    assert "index 1" in str(excinfo.value) and f"'Needs{ui_type}'" in str(excinfo.value)


def test_ac2_the_refusal_is_raised_at_PLAN_time_having_made_ZERO_calls_STRUCTURALLY():
    """Structural, not counted afterwards: the request is never built, so there is nothing to
    hand an engine, and the client the refusal happens in front of is never constructed."""
    client = schema_client(table_create=[create_table_echo()])
    with pytest.raises(UnauthorableFieldError):
        schema_dry_run([create_table("app", "t", fields=[
            {"field_name": "Ref", "field_type": 19, "ui_type": "Lookup"}])])
    assert client.api_calls == 0


def test_ac2_the_property_builder_is_the_SHARED_one_and_NOT_a_second_shape_table():
    """Identity, not resemblance: the ``property`` on the wire is compared to what
    ``build_property`` itself marshals, and an unknown key is refused with **that function's own
    sentence**. A parallel builder could match one shape by luck; it could not match both.
    """
    from larkdocio.base.field_authoring import build_property

    client = schema_client(table_create=[create_table_echo()])
    client.create_table("app", "t", fields=[KIT[1]])
    header = body_of(client._sdk.bitable.v1.app_table.create.requests[0])["table"]["fields"][0]
    assert header["property"] == json.loads(
        JSON.marshal(build_property(KIT[1]["ui_type"], **KIT[1]["properties"])))

    with pytest.raises(UncapturedFieldPropertyError) as through_the_kit:
        create_table("app", "t", fields=[dict(KIT[1], properties={"nope": 1})])
    with pytest.raises(UncapturedFieldPropertyError) as directly:
        build_property(KIT[1]["ui_type"], nope=1)
    assert str(directly.value) in str(through_the_kit.value), (
        "the kit's property refusal IS build_property's, only prefixed with which entry it "
        "came from — a second validator would word it differently")

    source = app_table.__loader__.get_source(app_table.__name__)
    assert "FIELD_PROPERTY_SHAPES" not in source, (
        "the family module must not carry a second copy of the property shape table")
    assert "build_property" in source and "check_authorable" in source


def test_ac2_an_UNKNOWN_KEY_on_a_kit_entry_refuses_rather_than_being_dropped():
    """This API silently ignores what it does not recognise, so a key this library does not
    understand must never be forwarded — nor quietly discarded."""
    with pytest.raises(FieldAuthoringRefusal) as excinfo:
        create_table("app", "t", fields=[
            {"field_name": "Title", "field_type": TEXT, "description": "nope"}])
    assert "description" in str(excinfo.value)
    assert ", ".join(app_table.COLUMN_KIT_KEYS) in str(excinfo.value)


@pytest.mark.parametrize("entry", [
    "Title",
    {"field_type": TEXT},
    {"field_name": "", "field_type": TEXT},
    {"field_name": "Title"},
])
def test_ac2_a_MALFORMED_kit_entry_refuses_locally(entry):
    with pytest.raises(FieldAuthoringRefusal):
        create_table("app", "t", fields=[entry])


# --------------------------------------------------------------------------- #
# AC4 — the plan gate holds; the pricing is honest BY CONSTRUCTION             #
# --------------------------------------------------------------------------- #

def test_ac4_the_dry_run_DISCLOSES_the_whole_column_kit_before_any_call_is_made():
    plan = schema_dry_run([create_table("app", "Items", fields=KIT)])
    entry = plan.entries[0]

    assert entry.request.describe == (
        "create table 'Items' in Base app with 3 columns: 'Title' (Text), "
        "'Budget' (Currency), 'Due' (DateTime)")
    assert [column["field_name"] for column in entry.fields["fields"]] == \
        ["Title", "Budget", "Due"]
    assert entry.to_dict()["fields"]["fields"][1]["ui_type"] == "Currency", (
        "the kit must survive into the plan's own JSON — a preview nobody can read is not one")


def test_ac4_api_call_count_is_ONE_because_a_kitted_create_is_LITERALLY_ONE_HTTP_CALL():
    """LD-322's AC5 two-write pricing worry is N/A here: one entry, one call, no arithmetic."""
    plan = schema_dry_run([create_table("app", "Items", fields=KIT)])
    assert plan.api_call_count == 1

    client = schema_client(table_create=[create_table_echo()])
    client.create_table("app", "Items", fields=KIT)
    assert client.api_calls == plan.api_call_count


def test_ac4_read_cost_RISES_when_a_kit_is_given_and_is_UNCHANGED_when_it_is_not():
    """The read-back now has two questions to answer — is the table listed, and did its
    columns land — so it costs two reads and the plan says so before anything is sent."""
    # LD-322: the kit-LESS create no longer exists to price — it is refused before a plan entry
    # is built — so the "unchanged" half is asserted where a kit-less body still ships (the
    # batch), and the create half is asserted on BOTH of its legal forms.
    with pytest.raises(FieldAuthoringRefusal):
        schema_dry_run([create_table("app", "t")])

    named = schema_dry_run([create_table("app", "t", primary_field_name="Title")])
    assert named.entries[0].read_cost == 2 and named.read_calls == 2

    kitted = schema_dry_run([create_table("app", "t", fields=KIT)])
    assert kitted.entries[0].read_cost == 2 and kitted.read_calls == 2

    batch = schema_dry_run([batch_create_tables("app", ["a", "b", "c"],
                                               accept_locale_default_primary=True)])
    assert batch.entries[0].read_cost == 1, (
        "the batch authors no columns — one table listing, exactly as before")


def test_ac4_a_kitless_plan_entry_is_BYTE_IDENTICAL_to_todays():
    """The zero-drift half, asserted on the plan rather than assumed from the body."""
    # LD-322 re-points the create half at the refusal (there is no kit-less create to compare)
    # and keeps the batch half, whose entry is byte-identical to the one it always produced.
    with pytest.raises(FieldAuthoringRefusal):
        schema_dry_run([create_table("app", "t")])

    batch = schema_dry_run([batch_create_tables(
        "app", ["a", "b"], accept_locale_default_primary=True)]).entries[0]
    assert batch.fields == {"app_token": "app", "names": ["a", "b"]}
    assert batch.request.describe == "create 2 table(s) in Base app"


# --------------------------------------------------------------------------- #
# AC5's OFFLINE half — the read-back is the created table's OWN FIELD LIST      #
# --------------------------------------------------------------------------- #

def _run(requests, *, deaf=()):
    world = FakeBaseWorld(apps={"appOLD": "Scratch Base"},
                          tables={"appOLD": {"tbl1": "Table"}})
    client = ScriptedSchemaClient(world, deaf=deaf)
    plan = schema_dry_run(requests)
    log = schema_apply(plan, client=client, read_client=world, sleep=NoSleep())
    return plan, log, world, client


def test_ac5_a_KITTED_create_is_confirmed_by_the_TABLE_LIST_AND_ITS_OWN_FIELD_LIST():
    """R12 at its sharpest on this rung: a create carrying ``fields`` answers ``code:0``
    whether or not the array was processed, so the columns are the only evidence."""
    _plan, log, world, _client = _run([create_table("appOLD", "Items", fields=KIT)])
    entry = log.entries[0]
    table_id = entry.created_table_ids[0]

    assert entry.outcome == "applied"
    assert entry.read_back["listed"] is True
    landed = entry.read_back["columns"][0]
    assert landed["asked"] == ["Title", "Budget", "Due"]
    assert landed["missing"] == [] and landed["mismatched"] == []
    assert ("list_fields", "appOLD", table_id) in world.calls, (
        "the created table's own field list is READ — never inferred from the create's echo")


def test_ac5_DEFECT_a_create_whose_ARRAY_WAS_IGNORED_is_reported_DROPPED():
    """The falsification. The table appears, the columns do not, ``code:0`` throughout — which
    is precisely the outage-shaped failure this capability could otherwise hide."""
    _plan, log, _world, client = _run([create_table("appOLD", "Ghost", fields=KIT)],
                                      deaf={"create_table_fields"})
    entry = log.entries[0]
    assert entry.outcome == "dropped"
    assert entry.read_back["columns"][0]["missing"] == ["Title", "Budget", "Due"]
    assert client.calls[0][0] == "create_table", "the call really was made"


def test_ac5_a_KITLESS_create_read_back_is_UNCHANGED_and_costs_NO_FIELD_READ():
    """The zero-drift half of the read-back: today's disclosure, key for key, and not one
    extra call for a caller who did not ask for columns."""
    # LD-322: a kit-LESS create is refused, so the shape this test pinned is asserted where it
    # still ships — the batch verb, whose read-back has always been the listing alone — and the
    # create's own kit-less path is pinned as the refusal it became.
    with pytest.raises(FieldAuthoringRefusal):
        create_table("appOLD", "third")

    _plan, log, world, _client = _run([batch_create_tables(
        "appOLD", ["third"], accept_locale_default_primary=True)])
    entry = log.entries[0]
    assert set(entry.read_back) == {"how", "table_ids", "missing", "read_backs"}
    assert not entry.read_back["missing"]
    assert not [call for call in world.calls if call[0] == "list_fields"]


def test_ac5_a_BATCH_read_back_is_UNCHANGED_one_listing_and_no_column_claim():
    """The batch verb authors no columns, so its read-back must make no claim about any — one
    listing, the shape it has always had."""
    _plan, log, world, _client = _run([batch_create_tables(
        "appOLD", ["a", "b"], accept_locale_default_primary=True)])
    entry = log.entries[0]
    assert entry.outcome == "applied"
    assert set(entry.read_back) == {"how", "table_ids", "missing", "read_backs"}
    assert entry.read_back["read_backs"] == 1
    assert world.calls.count(("list_tables", "appOLD")) == 1
    assert not [call for call in world.calls if call[0] == "list_fields"]


def test_the_KITS_FIRST_ENTRY_BECOMES_THE_PRIMARY_and_the_read_back_CARRIES_that_answer():
    """The MEASURED answer to the question LD-322's spike was minted to ask: ``fields[0]``
    **becomes** the primary column — the locale-named default Lark creates for a kit-less
    create is not there at all (probe ``ld336-02``, nine cases).

    The offline world models exactly that; the live arm measures it on the tenant. What this
    test pins is that the read-back **carries the answer** — a disclosure that dropped
    ``is_primary`` could not settle the question either way, whichever way it fell.
    """
    _plan, log, _world, _client = _run([create_table("appOLD", "Items", fields=KIT)])
    landed = log.entries[0].read_back["columns"][0]
    assert landed["primary"] == ["Title"], (
        "the kit's first entry IS the primary column, under the name the caller gave")
    assert FakeBaseWorld.DEFAULT_PRIMARY not in landed["seen"], (
        "a kitted create does NOT also get Lark's locale-named default column")

    # LD-322 closed the other half of that question rather than leaving it: there IS no kit-less
    # create any more, so the locale-named default can no longer be reached through this verb.
    with pytest.raises(FieldAuthoringRefusal):
        create_table("appOLD", "plain")


def test_ac9_the_kit_reaches_NO_NEW_ENDPOINT_and_the_FIELD_FAMILY_IS_NEVER_TOUCHED():
    """0 new endpoints, 0 new scopes: the two table-create descriptors are unchanged, and the
    apply path for a kitted create makes no ``/fields`` **write** call at all — which is the
    whole point of the route."""
    from larkdocio.base.schema_ops import schema_op

    assert schema_op("create_table").endpoint == \
        "/open-apis/bitable/v1/apps/:app_token/tables"
    assert schema_op("batch_create_tables").endpoint == \
        "/open-apis/bitable/v1/apps/:app_token/tables/batch_create"

    _plan, _log, _world, client = _run([create_table("appOLD", "Items", fields=KIT)])
    assert [call[0] for call in client.calls] == ["create_table"], (
        "no create_field / update_field — the down /fields write family is not on this route")


# --------------------------------------------------------------------------- #
# The two MEASURED facts about this route (probe ld336-02)                      #
# --------------------------------------------------------------------------- #

def test_the_kinds_MEASURED_REFUSING_at_creation_are_refused_LOCALLY_naming_create_field():
    """`Rating` and `Checkbox` answer `1254012 Unsupported field type.` on this route and
    create **nothing at all** — not the table, not the columns. An opaque `1254012` on a
    whole-table create is a worse answer than a sentence naming the column and the route that
    does author it, so they are refused before the call."""
    for ui_type in app_table.NOT_AUTHORABLE_AT_CREATION:
        with pytest.raises(FieldAuthoringRefusal) as excinfo:
            create_table("app", "t", fields=[
                KIT[0],
                {"field_name": f"my-{ui_type}",
                 "field_type": FIELD_PROPERTY_SHAPES[ui_type].field_type, "ui_type": ui_type}])
        message = str(excinfo.value)
        assert "index 1" in message and f"'my-{ui_type}'" in message, message
        assert "create_field" in message, (
            "the refusal must name the route that DOES author this kind — it is authorable, "
            "just not at creation")
        assert "1254012" in message, "the refusal cites what was measured, not an opinion"


def test_the_measured_refusals_are_still_INSIDE_create_fields_own_allow_list():
    """The narrowing is this ROUTE's, not the vocabulary's: both kinds remain authorable by
    `create_field`, which is exactly why the refusal can name it as the way forward. A version
    of this that had quietly shrunk the shared allow-list would break the other route too."""
    from larkdocio.base import field_vocabulary as fv

    for ui_type in app_table.NOT_AUTHORABLE_AT_CREATION:
        assert ui_type in fv.AUTHORABLE_UI_TYPES, ui_type
        assert ui_type not in fv.UNAUTHORABLE_GUIDANCE, ui_type


def test_the_KIT_FIRST_ENTRY_IS_THE_PRIMARY_fact_is_authored_ONCE_and_says_it_plainly():
    """The measured answer to LD-322's spike question, and the sentence the guide states. It is
    a constant rather than prose in three places so the guide, the docstring and the dev-repo
    register cannot drift from each other."""
    stated = app_table.KIT_FIRST_ENTRY_IS_THE_PRIMARY
    assert "FIRST" in stated and "PRIMARY" in stated
    assert "locale" in stated, "the contrast with the name-only create is the whole point"
    assert "is_primary" in stated, "it names the flag a caller can read it off"


def test_a_property_is_NEVER_sent_without_the_ui_type_it_belongs_to_R12():
    """Probe ld336-02 case E: a `property` sent with NO `ui_type` is ACCEPTED and silently
    ignored — the column lands as the storage type's default kind. So the builder must not be
    able to produce that body, which is a structural guarantee here rather than a warning."""
    client = schema_client(table_create=[create_table_echo()])
    client.create_table("app", "t", fields=[
        {"field_name": "bare", "field_type": TEXT, "properties": {}}])
    header = body_of(client._sdk.bitable.v1.app_table.create.requests[0])["table"]["fields"][0]
    assert "property" not in header, (
        "no ui_type was given, so no property may be sent — the server would ignore it at "
        "code:0 and author a column nobody asked for")
    assert "ui_type" not in header
