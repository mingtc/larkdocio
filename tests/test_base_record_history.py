"""LD-412 — Base record-level edit history: the measured refusal, said out loud.

LD-404 § Leg 5 probed a Base record's edit history: six route spellings all answer the
gateway's own non-JSON HTTP 404, the drive versions family refuses ``obj_type=bitable``, and
the drive statistics family answers ``code 0`` with view counters and no history. This story
mints **no op, no endpoint, no call** — it is documentation only, authored once in
:mod:`larkdocio.base.history` and quoted into the shipped guide, mirroring
``larkdocio.read.history`` (LD-410).
"""
import pytest

from larkdocio.base import history

pytestmark = pytest.mark.conformance


# --------------------------------------------------------------------------- #
# AC3 — the TRIED list, verbatim, and the NOT-TRIED list, verbatim              #
# --------------------------------------------------------------------------- #

TRIED = (
    "records/{record_id}/history", "records/{record_id}/histories",
    "records/{record_id}/revisions", "record_histories?record_id=",
    "tables/{table_id}/histories", "bitable/v1/apps/{app_token}/histories",
    "404", "versions?obj_type=bitable", "1068411",
    "params error, param [obj_type] is wrong", "statistics?file_type=bitable",
)

NOT_TRIED = (
    "user_access_token", "tenant_access_token", "undocumented product-internal endpoint",
)


@pytest.mark.parametrize("phrase", TRIED)
def test_the_refusal_enumerates_what_was_TRIED(phrase):
    assert phrase in history.RECORD_HISTORY_NOT_SERVED


@pytest.mark.parametrize("phrase", NOT_TRIED)
def test_the_refusal_enumerates_what_was_NOT_TRIED_because_scope_may_not_exceed_evidence(phrase):
    assert phrase in history.RECORD_HISTORY_NOT_SERVED


def test_the_refusal_is_never_a_bare_cannot():
    text = history.RECORD_HISTORY_NOT_SERVED
    assert "TRIED" in text and "NOT TRIED" in text
    assert "NOT SERVED" in text


def test_the_refusal_cites_leg_5_evidence():
    text = history.RECORD_HISTORY_NOT_SERVED
    assert "dev/editions-spike/findings.md" in text and "Leg 5" in text
    assert "300-summary-leg-5-base-history.json" in text
    assert "in the dev repo" in text


# --------------------------------------------------------------------------- #
# AC4 — the nearest served thing: automatic_fields=true, its unit, and the policy #
# --------------------------------------------------------------------------- #

def test_the_nearest_served_thing_names_the_call_and_what_it_answers():
    text = history.NEAREST_SERVED_RECORD_TOUCH
    assert "automatic_fields=true" in text
    assert "created_by" in text and "created_time" in text
    assert "last_modified_by" in text and "last_modified_time" in text
    assert "not what changed" in text.lower() or "not what CHANGED" in text


def test_the_nearest_served_thing_names_the_UNIT_and_contrasts_it_with_the_versions_family():
    text = history.NEAREST_SERVED_RECORD_TOUCH
    assert "MILLISECONDS" in text
    assert "1786403626000" in text  # the captured 13-digit ms value — evidence, not invention
    assert "epoch" in text.lower() and "SECOND" in text  # the drive versions family's own unit


def test_the_nearest_served_thing_states_larkdocios_OWN_POLICY_in_the_same_breath():
    text = history.NEAREST_SERVED_RECORD_TOUCH
    assert "automatic_fields" in text
    assert "FALSE" in text or "False" in text
    assert "person-data policy" in text.lower()
    assert "larkdocio.base.client.AUTOMATIC_FIELDS" in text
    # never sends a consumer to a call this library declines to make without saying so
    assert "does not" in text.lower() or "not what this" in text.lower() \
        or "not what larkdocio exposes" in text.lower()


def test_neither_constant_claims_lark_itself_cannot_do_it():
    banned = ("impossible", "can never", "cannot ever", "permanently forbidden")
    for text in (history.RECORD_HISTORY_NOT_SERVED, history.NEAREST_SERVED_RECORD_TOUCH):
        lowered = text.lower()
        for phrase in banned:
            assert phrase not in lowered


# --------------------------------------------------------------------------- #
# AC5 — authored once, quoted into the shipped guide, findable by the failure  #
# --------------------------------------------------------------------------- #

def test_the_disclosures_are_QUOTED_into_the_shipped_guide_never_re_typed():
    from larkdocio import guide

    text = guide(full=True)
    assert history.RECORD_HISTORY_NOT_SERVED in text, (
        "the guide re-typed the refusal instead of quoting the module constant")
    assert history.NEAREST_SERVED_RECORD_TOUCH in text, (
        "the guide re-typed the nearest-served-thing statement instead of quoting it")


def test_the_guide_carries_a_section_findable_by_the_failure_it_cures():
    from larkdocio import guide_sections

    headings = [section["heading"] for section in guide_sections()]
    matches = [h for h in headings if "record" in h.lower() and "history" in h.lower()]
    assert matches, f"no guide heading names 'record' + 'history': {headings}"
    heading = matches[0]
    assert "who changed this row" in heading.lower() or "changed" in heading.lower()


# --------------------------------------------------------------------------- #
# AC6 — no behavior change: no new op, no new endpoint, no new call            #
# --------------------------------------------------------------------------- #

def test_this_module_makes_no_transport_call_and_registers_nothing():
    """The module carries prose constants only — no client, no op descriptor, no permission
    row. Importing it must not touch larkdocio.capabilities() or larkdocio.permissions."""
    import inspect

    source = inspect.getsource(history)
    for banned in ("requests.", "lark_client", "def get_", "ENDPOINT_SCOPES", "OPS ="):
        assert banned not in source


def test_capabilities_and_permissions_are_UNMOVED_by_this_module():
    from larkdocio import capabilities
    from larkdocio.permissions import consumer_permissions_markdown

    before_caps = capabilities(full=True)
    before_perms = consumer_permissions_markdown()
    # re-derive after importing the new module — byte-identical projections either way
    import larkdocio.base.history  # noqa: F401
    after_caps = capabilities(full=True)
    after_perms = consumer_permissions_markdown()
    assert before_caps == after_caps
    assert before_perms == after_perms
