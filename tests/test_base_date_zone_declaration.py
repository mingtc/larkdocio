"""LD-463 — the WRITE half of the one timezone policy: a Base can be created WITH its zone.

Why this is the fix rather than a nicety. The bug report's ``get_app().time_zone is None`` was
not Lark withholding an answer — the AC1 capture
(``tests/captures/ld463-date-only/captures/ld463-01-date-only-zone.json`` § ``c_*``) shows the ``time_zone``
key **absent from the wire** for a Base this library created and **present** for one created with
the key in the body, ``code:0``, echoed, and readable back through ``GET …/apps/{app}``. So the
recorded reason for withholding it — *"no test could show which zone a Base ended up in from a
shape this library reads"* — is falsified by exactly such a test, and only that conclusion
changes (CLAUDE.md § Supersession).

The R12 discipline this surface ships under applies unchanged: the key is sent **only when
supplied**, and every arm below is **differential against the parameter-free control**, because
``POST /bitable/v1/apps`` ignores a body key it does not recognise and a misplaced key would be
``code:0`` and invisible.
"""
import inspect

from base_schema_fakes import (
    FakeBaseWorld,
    ScriptedSchemaClient,
    create_app_echo,
    schema_client,
)
from test_base_schema_client import body_of

from larkdocio.base import date_zone
from larkdocio.base.schema_apply import _issue
from larkdocio.base.schema_plan import SchemaPlanEntry, create_base


# --------------------------------------------------------------------------- #
# The client — the one route Lark accepts a zone on                            #
# --------------------------------------------------------------------------- #

def test_create_app_sends_time_zone_ONLY_when_it_is_given_R12():
    bare = schema_client(create=[create_app_echo()])
    bare.create_app("n", "fldrXYZ")
    zoned = schema_client(create=[create_app_echo()])
    zoned.create_app("n", "fldrXYZ", time_zone="Asia/Singapore")

    control = body_of(bare._sdk.bitable.v1.app.create.requests[0])
    with_param = body_of(zoned._sdk.bitable.v1.app.create.requests[0])
    assert "time_zone" not in control
    assert with_param != control and with_param["time_zone"] == "Asia/Singapore"


def test_create_app_still_sends_a_folder_token_and_a_zone_TOGETHER():
    client = schema_client(create=[create_app_echo()])
    client.create_app("n", "fldrXYZ", time_zone="UTC")
    body = body_of(client._sdk.bitable.v1.app.create.requests[0])
    assert body == {"name": "n", "folder_token": "fldrXYZ", "time_zone": "UTC"}


def test_the_client_records_the_SUPERSESSION_rather_than_deleting_the_old_reason():
    """CLAUDE.md § Supersession: the recorded reason survives verbatim; only the conclusion
    moves. A silent strike is what gets a settled argument re-litigated."""
    from larkdocio.base import schema_client as module

    doc = module.__doc__ or ""
    assert "no test could show which zone a Base ended up in" in doc, (
        "the original reason for withholding the key must be preserved, not deleted")
    assert "ld463-01" in doc, "and the measurement that falsified it must be cited"


# --------------------------------------------------------------------------- #
# The plan and the engine — the zone travels the whole way, or it is not a fix #
# --------------------------------------------------------------------------- #

def test_create_base_carries_the_zone_into_its_ARGUMENTS_and_says_nothing_when_absent():
    assert "time_zone" not in create_base("n", "fldrXYZ").arguments
    assert create_base("n", "fldrXYZ",
                       time_zone="Asia/Singapore").arguments["time_zone"] == "Asia/Singapore"


def test_create_base_DESCRIBES_the_zone_it_declares():
    """A plan is a preview: a caller must be able to see the zone before anything is sent."""
    assert "Asia/Singapore" in create_base("n", "fldrXYZ",
                                           time_zone="Asia/Singapore").describe
    assert "time zone" not in create_base("n", "fldrXYZ").describe


def test_the_APPLY_ENGINE_forwards_the_zone_to_the_client():
    """The seam a "fix" most easily stops one call short of."""
    client = ScriptedSchemaClient(FakeBaseWorld())
    _issue(client, SchemaPlanEntry(op="create_app",
                                   fields={"name": "n", "time_zone": "Asia/Singapore"}))
    assert client.calls == [("create_app", "n", None, "Asia/Singapore")]


def test_the_APPLY_ENGINE_forwards_NOTHING_when_no_zone_was_asked_for():
    client = ScriptedSchemaClient(FakeBaseWorld())
    _issue(client, SchemaPlanEntry(op="create_app", fields={"name": "n"}))
    assert client.calls == [("create_app", "n", None, None)]


def test_the_plan_side_REFERENCES_the_one_policy():
    from larkdocio.base import schema_plan

    assert "date_zone" in inspect.getsource(schema_plan)
    assert date_zone.CREATE_IS_WHERE_A_ZONE_IS_DECLARED


def test_the_WRITE_ENCODER_IS_UNCHANGED_and_says_why_at_the_one_policy():
    """(a) of the capture: the instant is stored losslessly, so refusing a date-like object
    costs nothing and stays right. The refusal message is not widened — what is new is that it
    points at the policy instead of re-arguing it."""
    import pytest

    from larkdocio.base.cells import FieldSpec
    from larkdocio.base.write_cells import encode_cell

    field = FieldSpec(field_name="D", type=5, ui_type="DateTime",
                      property={"date_formatter": "yyyy/MM/dd"})
    assert encode_cell(1772294400000, field) == 1772294400000
    with pytest.raises(Exception) as excinfo:
        encode_cell("2026/03/01", field)
    assert "MILLISECONDS" in str(excinfo.value)
