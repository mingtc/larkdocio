"""LD-322 — **no table is ever created with a name Lark chose.**

A kit-LESS, name-LESS ``create_table`` used to be legal and to land a primary column named by
Lark in the tenant's locale (``多行文本`` on the reporting tenant). It is now **refused at plan
time, with zero API calls, structurally** — no client is constructed on the refusing path — and
the refusal **teaches**: the consequence it prevents, the one-line fix
(``primary_field_name=``), and the kit alternative (``fields=[…]``, entry 0 is the primary).

The mechanism is **LD-336's transport and nothing else**: ``primary_field_name=`` is normalised
into a **one-entry kit** before the gate sees it, so it rides the same ``check_authorable`` /
``build_property`` seams ``create_field`` rides. Rename-after-create is **not** the route, and
no new endpoint is reached.

``batch_create_tables`` is the asymmetric half: Lark **ignores** a per-table ``fields`` array
there (measured twice, ``BATCH_CREATE_IGNORES_A_COLUMN_KIT``), so a name **cannot** be honoured
— the doctrine is discharged by making the silence **explicit** instead, with
``accept_locale_default_primary=True``.
"""
import pytest

from base_schema_fakes import batch_create_echo, create_table_echo, schema_client
from larkdocio.base import schema_ops_app_table as app_table
from larkdocio.base.field_authoring import FIELD_PROPERTY_SHAPES, FieldAuthoringRefusal
from larkdocio.base.schema_apply import schema_dry_run
from larkdocio.base.schema_plan import batch_create_tables, create_table

APP = "bascnLD322"


# --------------------------------------------------------------------------- #
# AC1 — the kitless, nameless create REFUSES, locally, and TEACHES             #
# --------------------------------------------------------------------------- #

def test_a_nameless_kitless_create_table_REFUSES_at_plan_time():
    """``create_table(app_token, name)`` no longer builds a request — it raises."""
    with pytest.raises(FieldAuthoringRefusal) as raised:
        create_table(APP, "Items")
    assert app_table.NAMELESS_PRIMARY_IS_REFUSED in str(raised.value)


def test_the_refusal_TEACHES_all_three_things_and_is_authored_ONCE():
    """(a) the consequence prevented, (b) the one-line fix, (c) the kit alternative.

    Asserted against the **constant**, never a copy of its words — the text is authored once,
    beside its siblings, and quoted everywhere it appears.
    """
    text = app_table.NAMELESS_PRIMARY_IS_REFUSED
    # (a) the consequence it prevents — the measured locale default, named.
    assert "多行文本" in text and "locale" in text
    # (b) the one-line fix.
    assert "primary_field_name=" in text
    # (c) the kit alternative, and what its first entry does.
    assert "fields=" in text and "FIRST" in text
    assert "NAMELESS_PRIMARY_IS_REFUSED" in app_table.__all__


def test_the_refusing_path_CONSTRUCTS_NO_CLIENT_and_makes_no_call(monkeypatch):
    """Zero calls **structurally**: nothing on the transport is even reachable.

    The refusal happens inside the op constructor (guide channel 1), so a client that raises on
    construction proves the path never gets that far.
    """
    from larkdocio.base import schema_client as schema_client_module

    def explode(*_args, **_kwargs):
        raise AssertionError("a client was constructed on a refusing path")

    monkeypatch.setattr(schema_client_module.BaseSchemaClient, "__init__", explode)
    with pytest.raises(FieldAuthoringRefusal):
        create_table(APP, "Items")
    with pytest.raises(FieldAuthoringRefusal):
        batch_create_tables(APP, ["Notes"])


def test_an_EXPLICITLY_EMPTY_kit_is_the_same_refusal():
    """``fields=[]`` means "no columns", which is the very thing being refused."""
    with pytest.raises(FieldAuthoringRefusal) as raised:
        create_table(APP, "Items", fields=[])
    assert app_table.NAMELESS_PRIMARY_IS_REFUSED in str(raised.value)


# --------------------------------------------------------------------------- #
# AC2 — primary_field_name IS a one-entry kit, byte-for-byte                   #
# --------------------------------------------------------------------------- #

def _one_text_kit(name):
    return [{"field_name": name, "field_type": FIELD_PROPERTY_SHAPES["Text"].field_type,
             "ui_type": "Text"}]


def test_primary_field_name_produces_the_SAME_REQUEST_as_the_equivalent_one_entry_kit():
    sugar = create_table(APP, "Items", primary_field_name="Title")
    explicit = create_table(APP, "Items", fields=_one_text_kit("Title"))
    assert sugar.arguments == explicit.arguments
    assert sugar.arguments["fields"] == [
        {"field_name": "Title", "field_type": 1, "ui_type": "Text", "properties": {}}]
    assert sugar.describe == explicit.describe


def test_the_named_primary_is_priced_and_disclosed_before_the_call():
    plan = schema_dry_run([create_table(APP, "Items", primary_field_name="Title")])
    assert plan.api_call_count == 1
    assert plan.read_calls == 2          # read_cost 2 — the table listing plus the field list
    assert "with 1 column: 'Title' (Text)" in plan.entries[0].request.describe


def test_the_sugar_rides_the_SAME_GATE_a_kit_rides():
    """An unusable name is refused by ``_one_column``'s own sentence, not a second copy."""
    with pytest.raises(FieldAuthoringRefusal) as raised:
        create_table(APP, "Items", primary_field_name="")
    assert "not a column" in str(raised.value)


# --------------------------------------------------------------------------- #
# AC3 — one transport: the apply path routes through the family handler        #
# --------------------------------------------------------------------------- #

def test_the_apply_path_routes_through_the_FAMILY_HANDLER_so_no_kit_can_be_dropped():
    """``schema_apply``'s generic fallback drops ``fields``; ``ISSUE_HANDLERS`` owns both verbs."""
    assert set(app_table.ISSUE_HANDLERS) == {"create_table", "batch_create_tables"}
    from larkdocio.base import schema_apply as apply_module

    handlers = apply_module._family_handlers("ISSUE_HANDLERS")
    assert handlers["create_table"] is app_table.ISSUE_HANDLERS["create_table"]
    assert handlers["batch_create_tables"] is app_table.ISSUE_HANDLERS["batch_create_tables"]


def test_no_new_reach_the_named_primary_never_touches_the_fields_write_family():
    import inspect

    # The CODE, not the docstring — which names `update_field` precisely to say it is NOT the
    # mechanism. `__doc__` is stripped so the assertion is about what the function DOES.
    def body(function):
        return inspect.getsource(function).split('"""')[2]

    code = body(app_table.check_primary_naming)
    assert "update_field" not in code
    assert "/fields" not in code
    # And the same for the public seam that calls it.
    from larkdocio.base import schema_client as client_module

    assert "update_field" not in body(client_module.BaseSchemaClient.create_table)


# --------------------------------------------------------------------------- #
# AC4 — both given is REFUSED, even when the names agree                       #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("primary", ["Title", "Item"])
def test_primary_field_name_AND_fields_together_is_REFUSED(primary):
    with pytest.raises(FieldAuthoringRefusal) as raised:
        create_table(APP, "Items", fields=_one_text_kit("Item"), primary_field_name=primary)
    assert app_table.PRIMARY_FIELD_NAME_AND_KIT in str(raised.value)


def test_the_both_given_refusal_says_WHY_and_WHAT_TO_DO():
    text = app_table.PRIMARY_FIELD_NAME_AND_KIT
    assert "FIRST" in text and "primary" in text
    assert "Drop one" in text
    assert "PRIMARY_FIELD_NAME_AND_KIT" in app_table.__all__


# --------------------------------------------------------------------------- #
# AC5 — the batch verb's explicit acknowledgement                              #
# --------------------------------------------------------------------------- #

def test_batch_create_tables_REFUSES_without_the_acknowledgement():
    with pytest.raises(FieldAuthoringRefusal) as raised:
        batch_create_tables(APP, ["Notes", "Archive"])
    assert app_table.BATCH_CREATE_LOCALE_DEFAULT_PRIMARY in str(raised.value)


def test_the_batch_refusal_names_the_consequence_the_optin_and_the_alternative():
    text = app_table.BATCH_CREATE_LOCALE_DEFAULT_PRIMARY
    assert "多行文本" in text and "locale" in text                     # (a)
    assert "accept_locale_default_primary=True" in text                # (b)
    assert "primary_field_name" in text and "one call" in text         # (c)
    assert "BATCH_CREATE_LOCALE_DEFAULT_PRIMARY" in app_table.__all__


def test_batch_create_tables_PROCEEDS_with_the_acknowledgement_body_unchanged():
    request = batch_create_tables(APP, ["Notes", "Archive"],
                                  accept_locale_default_primary=True)
    assert request.arguments == {"app_token": APP, "names": ["Notes", "Archive"]}
    assert request.describe == f"create 2 table(s) in Base {APP}"


def test_primary_field_name_on_the_BATCH_gets_the_sentence_not_a_TypeError():
    with pytest.raises(FieldAuthoringRefusal) as raised:
        batch_create_tables(APP, ["Notes"], primary_field_name="Title",
                            accept_locale_default_primary=True)
    assert app_table.BATCH_CREATE_LOCALE_DEFAULT_PRIMARY in str(raised.value)


def test_a_kit_on_the_batch_still_draws_the_KIT_refusal_which_is_the_more_specific_one():
    with pytest.raises(FieldAuthoringRefusal) as raised:
        batch_create_tables(APP, ["Notes"], fields=[_one_text_kit("Title")],
                            accept_locale_default_primary=True)
    assert app_table.BATCH_CREATE_IGNORES_A_COLUMN_KIT in str(raised.value)


# --------------------------------------------------------------------------- #
# The client seam re-checks — the same posture through the other door          #
# --------------------------------------------------------------------------- #

def test_the_CLIENT_seam_refuses_a_nameless_create_too():
    client = schema_client(table_create=[create_table_echo()])
    with pytest.raises(FieldAuthoringRefusal):
        client.create_table(APP, "Items")


def test_the_CLIENT_seam_refuses_an_unacknowledged_batch_too():
    client = schema_client(table_batch_create=[batch_create_echo()])
    with pytest.raises(FieldAuthoringRefusal):
        client.batch_create_tables(APP, ["Notes"])


def test_the_CLIENT_seam_takes_primary_field_name_and_sends_the_one_entry_kit():
    client = schema_client(table_create=[create_table_echo()])
    assert client.create_table(APP, "Items", primary_field_name="Title")


def test_an_ACKNOWLEDGED_batch_reaches_the_wire_unchanged():
    client = schema_client(table_batch_create=[batch_create_echo()])
    assert client.batch_create_tables(
        APP, ["Notes", "Archive"], accept_locale_default_primary=True)
