"""LD-403 — the VIEW route's Checkbox condition, measured, and the ROUTE-SCOPED evidence rule.

Two defects, one change. **(1)** The shipped filter-shape table claimed a view-route Checkbox
condition matches on *"the same boolean"* as the search route — on the strength of a **search**
route observation — and the consumer measured four view-route spellings all answering
``1254001``. **(2)** The evidence vocabulary let a single label span both routes, so *any* row
could inherit one route's observation as the other's proof. The first is a fact this issue
measured; the second is the rule that outlives the row.

**What the probe found** (``tests/captures/base-study/captures/ld403-01-checkbox-view-filter.json``, live
against a disposable the probe created and deleted): the view route DOES take a Checkbox
condition, and Lark's own ``1254001`` body says the shape verbatim — *"the condition value of
'Checkbox' must be a legal json string, and the content is a list of booleans"*. So ``"[true]"``
is ``code:0`` and shows the ticked rows; every **quoted** spelling — ``["true"]``, ``["True"]``,
``["1"]`` — and both valueless operators are refused. The library's own serialiser stringified
every value, so the one shape it could produce for ``("is", (True,))`` was the refused
``["True"]``: the row was wrong AND unreachable.

These tests are **conformance-marked** where they pin the product rather than this
implementation — the measured wire shape and the route-scoped evidence rule survive a rewrite.
"""
import json

import pytest
from guard_kit import REPO_ROOT

from larkdocio.base import shape_docs as sd
from larkdocio.base import view_filters as vf
from larkdocio.base.view_filters import (
    Condition,
    FieldId,
    FieldName,
    FilterSpec,
    search_filter,
    view_filter,
)

_CAPTURES = REPO_ROOT / "tests" / "captures" / "base-study" / "captures"

#: The captures this issue minted — the files that make the row's `captured` label legal. The
#: first asked the SERVER what the route takes (raw bodies, 20 spellings, TEXT controls); the
#: second asked whether a caller of THIS library can send it (the shipped chain end to end).
CAPTURE = "ld403-01-checkbox-view-filter.json"
SHIPPED_CAPTURE = "ld403-02-checkbox-shipped-path.json"


def _view_value(values, operator="is"):
    spec = FilterSpec(conditions=(Condition(FieldId("fldCheck"), operator, values),))
    return view_filter(spec).to_dict()["conditions"][0].get("value")


# --------------------------------------------------------------------------- #
# The MEASURED wire shape — a list of JSON BOOLEANS inside the json-string.      #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_a_view_route_BOOLEAN_is_carried_as_a_JSON_BOOLEAN_not_as_its_python_repr():
    """The measured shape, and the exact bug: ``str(True)`` is ``"True"``, so the serialiser's
    blanket stringification produced ``'["True"]'`` — one of the four spellings Lark refused."""
    assert _view_value((True,)) == "[true]"
    assert _view_value((False,)) == "[false]"


@pytest.mark.conformance
def test_the_SEARCH_route_is_UNCHANGED_because_its_own_measurement_is_of_the_string():
    """The search route's Checkbox condition was measured working with ``["True"]`` — the value
    this library already sent — so nothing there moves. A route's fix is that route's."""
    named = FilterSpec(conditions=(Condition(FieldName("Check"), "is", (True,)),))
    assert search_filter(named).to_dict()["conditions"][0]["value"] == ["True"]
    assert vf.SEARCH_DIALECT.preserves_json_booleans is False
    assert vf.VIEW_DIALECT.preserves_json_booleans is True


def test_every_NON_boolean_view_value_is_still_stringified_exactly_as_before():
    """The narrowness is the point: only ``bool`` changes spelling, because only ``bool`` is
    what Lark's refusal body named. An int, a string and a float are untouched."""
    assert _view_value(("Text 1",)) == '["Text 1"]'
    assert _view_value((1,)) == '["1"]'
    assert _view_value((1786147200000,)) == '["1786147200000"]'
    assert _view_value(("ExactDate", 1786147200000)) == '["ExactDate", "1786147200000"]'


@pytest.mark.conformance
def test_a_boolean_filter_ECHOES_its_own_read_back():
    """The persisted body Lark hands back for the accepted shape, verbatim from the capture —
    the round-trip a caller's ``set_view_filter`` confirms against."""
    sent = view_filter(FilterSpec(conditions=(Condition(FieldId("fldCheck"), "is", (True,)),)))
    persisted = {"conjunction": "and",
                 "conditions": [{"condition_id": "con9LpPssM", "field_id": "fldCheck",
                                 "field_type": 7, "operator": "is", "value": "[true]"}]}
    assert vf.echoes(sent, persisted)


def test_the_measured_refusals_are_ENUMERATED_where_the_shape_is_authored():
    """Negative-claim doctrine § A.1: the reader can see the edge of the evidence — which
    spellings were tried and refused, not merely that "others" were."""
    for refused in ('["true"]', '["True"]', '["1"]', "isEmpty", "isNotEmpty"):
        assert refused in vf.VIEW_ROUTE_CHECKBOX_TAKES_JSON_BOOLEANS, refused
    assert "1254001" in vf.VIEW_ROUTE_CHECKBOX_TAKES_JSON_BOOLEANS


def test_the_enumeration_carries_every_form_the_probe_sent_with_its_own_answer():
    """The tuple is the edge of the evidence, and it is a tuple rather than a sentence so a
    later probe extends it by appending rather than by rewriting prose."""
    forms = vf.CHECKBOX_VIEW_PROBED_FORMS
    assert len(forms) >= 20, "the consumer's four plus this probe's own extension"
    assert {op for op, _, _ in forms} >= {"is", "isNot", "contains", "isEmpty", "isNotEmpty"}
    accepted = [row for row in forms if row[2].startswith("code:0")]
    assert accepted, "an all-refused enumeration would be the OTHER arm of this issue"


@pytest.mark.conformance
def test_ONLY_the_is_operator_and_ONE_element_were_seen_working_and_the_row_says_so():
    """Two limits the shipped-path probe measured, both stated rather than worked around:
    ``isNot`` answers ``1254001`` even carrying the accepted value spelling, and a two-element
    array is stored as its first element alone — a ``code:0`` that did not persist what was
    sent, which is precisely the class ``echoes()`` exists to catch."""
    view_half = sd.FILTER_SHAPES[(7, "Checkbox")].view.value
    assert "isNot" in view_half and "first element" in view_half
    data = json.loads((_CAPTURES / SHIPPED_CAPTURE).read_text(encoding="utf-8"))
    arms = {row["arm"]: row for row in data["arms"]}
    assert arms["is True"]["echoes"] is True
    assert arms["is False"]["echoes"] is True
    assert arms["isNot True"]["accepted"] is False and "1254001" in arms["isNot True"]["refusal"]
    assert arms["is (True, False)"]["echoes"] is False


@pytest.mark.conformance
def test_the_SHIPPED_chain_is_what_was_measured_not_a_hand_written_body():
    """The row describes what a caller of THIS library sends, so the evidence behind it has to
    be the library's own serialiser — ``'[true]'``, produced by ``view_filter``, accepted, read
    back and echoed. A raw-HTTP-only measurement would document somebody else's client."""
    data = json.loads((_CAPTURES / SHIPPED_CAPTURE).read_text(encoding="utf-8"))
    arms = {row["arm"]: row for row in data["arms"]}
    assert arms["is True"]["serialised_value"] == "[true]"
    assert arms["is True"]["rows_visible_through_view"] == 2, "the two ticked rows"
    assert arms["is False"]["serialised_value"] == "[false]"
    assert _view_value((True,)) == arms["is True"]["serialised_value"], (
        "the serialiser today must still produce the body the capture proved working")


# --------------------------------------------------------------------------- #
# AC6 — the EVIDENCE LABEL IS ROUTE-SCOPED, structurally.                       #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_no_filter_shape_can_carry_ONE_evidence_label_spanning_BOTH_routes():
    """The structural half of the fix: there is no longer a field on which a single label could
    stand for two routes. Each route half carries its own value, evidence and captures."""
    assert not hasattr(sd.FilterShape, "evidence"), (
        "a route-spanning evidence label is exactly the defect LD-403 removed")
    assert sd.FilterShape._fields == ("search", "view")
    for pair, shape in sd.FILTER_SHAPES.items():
        for route in (shape.search, shape.view):
            assert isinstance(route, sd.RouteShape), pair
            assert route.evidence in sd.FILTER_EVIDENCE_CLASSES, (pair, route.evidence)


def test_each_route_half_of_every_row_carries_its_OWN_evidence_in_the_rendered_table():
    region = sd.filter_shape_markdown()
    for pair, shape in sd.FILTER_SHAPES.items():
        row = [line for line in region.splitlines()
               if line.startswith(f"| `{pair[0]} / {pair[1]}`")]
        assert row, pair
        assert shape.search.evidence in row[0], pair
        assert shape.view.evidence in row[0], pair


def test_a_captured_route_half_cites_a_capture_that_EXISTS_and_a_non_captured_one_cites_none():
    for pair, shape in sd.FILTER_SHAPES.items():
        for route in (shape.search, shape.view):
            if route.evidence == "captured":
                assert route.captures, pair
                for name in route.captures:
                    assert (_CAPTURES / name).exists(), f"{pair} cites a missing {name}"
            else:
                assert route.captures == (), (
                    f"{pair} labels a half {route.evidence!r} yet cites captures, which "
                    "would overclaim")


@pytest.mark.conformance
def test_the_CHECKBOX_row_now_states_the_MEASURED_view_shape_with_its_OWN_capture():
    """AC4's arm: a working shape was found, so the view half is `captured` and names the file
    on disk. The SEARCH half moves to `captured` too — and only because the same run captured
    it as a control; its SHAPE is unchanged, which is the difference between re-labelling a
    claim to its own evidence and re-litigating it."""
    shape = sd.FILTER_SHAPES[(7, "Checkbox")]
    assert shape.view.evidence == "captured"
    assert shape.view.captures == (CAPTURE, SHIPPED_CAPTURE)
    assert (_CAPTURES / CAPTURE).exists()
    assert "[true]" in shape.view.value
    assert shape.search.evidence == "captured"
    assert shape.search.captures == (CAPTURE,)
    assert '("is", (True,))' in shape.search.value, (
        "the consumer's reported search-route shape is retained, now with a capture behind it")


def test_the_probe_capture_records_the_working_shape_AND_every_refused_form():
    """The capture is the evidence the `captured` label stands on; this reads it rather than
    restating it, so a capture edited to disagree with the row reddens here."""
    data = json.loads((_CAPTURES / CAPTURE).read_text(encoding="utf-8"))
    arms = {row["form"]: row for row in data["view_route_arms"]}
    assert arms["json bool inside the array"]["code"] == 0
    assert arms["json bool inside the array"]["value_sent"] == "[true]"
    for refused in ("consumer-1 / library's own True", "consumer-2 / lowercase true",
                    "consumer-3 / the int 1", "consumer-4 / valueless isNotEmpty"):
        assert arms[refused]["code"] == 1254001, refused
    assert all(row["accepted"] for row in data["controls"]), (
        "a refusal is only attributable when the TEXT control on the same view passed")
