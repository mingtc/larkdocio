"""LD-408 — the operator vocabulary's claim is re-scoped to its evidence, and the measured
per-type refusal is answered LOCALLY.

Two arms, one maintainer ruling (Option B, 2026-08-12).

**(1) The sentence.** The generated filter-shape region shipped *"the operator vocabulary is
shared and is NOT type-restricted"* three lines above a row stating that a view-route Checkbox
refuses four of the six. The evidence behind the sentence is a **Text** field on both routes; the
claim was stated over every type. The re-scoped sentence says what was observed — the six are
shared **between the routes**, proved on a Text field — and sends per-type acceptance to the rows.

**(2) The refusal.** `FieldRegistry.resolve()` is the VIEW direction's resolver, so it knows the
field's type and the route. The four operators `ld403-01` measured refused on a view-route
Checkbox are now refused there, locally, zero API calls, quoting Lark's own `1254001` — the
`view_type` allow-list's precedent (`view_plan.check_view_type`), applied to an operator.
`doesNotContain` was never sent to a Checkbox, so it stays **unmeasured, not refused**, and
passes through: the refusal list is derived from the probe's own arms rather than from a class.
"""
import pytest

from larkdocio.base import shape_docs as sd
from larkdocio.base import view_filters as vf
from larkdocio.base.view_filters import (
    BaseFilterRefusal,
    Condition,
    FieldId,
    FieldName,
    FieldRegistry,
    FilterSpec,
)

_CHECK = {"field_id": "fldCheck", "field_name": "Check", "ui_type": "Checkbox", "type": 7}
_TEXT = {"field_id": "fldText", "field_name": "Text", "ui_type": "Text", "type": 1}


def _registry(fields=(_CHECK, _TEXT), *, exhaustive=True):
    return FieldRegistry(list(fields), exhaustive=exhaustive)


def _spec(field, operator, values=()):
    return FilterSpec(conditions=(Condition(field, operator, values),))


# --------------------------------------------------------------------------- #
# ARM 1 — the sentence is scoped to what was observed.                          #
# --------------------------------------------------------------------------- #

def test_the_preamble_no_longer_claims_the_vocabulary_is_NOT_type_restricted():
    """The exact over-claim LD-403's own capture refuted, gone from the shipped region."""
    region = sd.filter_shape_markdown()
    assert "type-restricted" not in region


@pytest.mark.conformance
def test_the_preamble_states_the_ROUTE_scope_and_the_FIELD_TYPE_its_capture_used():
    """The claim that survives: shared BETWEEN THE ROUTES, proved on a Text field. A reader can
    see which axis the evidence covers and which it does not."""
    region = sd.filter_shape_markdown()
    assert "shared BETWEEN THE TWO ROUTES" in region
    assert "Text field" in region


@pytest.mark.conformance
def test_the_preamble_sends_PER_TYPE_acceptance_to_the_rows_and_names_the_checkbox_case():
    """Per-type acceptance is claimed only where a row says so — and the one type that was
    measured to differ is named in the preamble rather than left to be discovered."""
    region = sd.filter_shape_markdown()
    assert "Checkbox" in region.split("| Field type |")[0]
    assert "1254001" in region.split("| Field type |")[0]
    assert "FieldRegistry.resolve()" in region.split("| Field type |")[0]


def test_the_authored_module_comment_does_not_repeat_the_retired_claim():
    """The sentence was authored once and projected; the module that authors it may not keep the
    superseded reason alive next to the fixed projection."""
    import inspect
    source = inspect.getsource(sd)
    assert "not type-restricted" not in source
    assert "NOT type-restricted" not in source


# --------------------------------------------------------------------------- #
# ARM 2 — the local, typed refusal, derived from the probe's own arms.           #
# --------------------------------------------------------------------------- #

def test_the_refused_operator_set_is_DERIVED_from_the_probed_forms_not_hand_listed():
    """Exactly the four whose every probed arm answered `1254001` — no class widening, and a
    later probe extends the tuple by appending an arm rather than by editing a list."""
    assert vf.VIEW_ROUTE_CHECKBOX_REFUSED_OPERATORS == (
        "isNot", "contains", "isEmpty", "isNotEmpty")
    assert "is" not in vf.VIEW_ROUTE_CHECKBOX_REFUSED_OPERATORS
    assert "doesNotContain" not in vf.VIEW_ROUTE_CHECKBOX_REFUSED_OPERATORS


@pytest.mark.parametrize("operator", ("isNot", "contains", "isEmpty", "isNotEmpty"))
def test_resolve_REFUSES_a_measured_refused_operator_on_a_checkbox_locally(operator):
    values = () if operator in vf.VALUELESS_OPERATORS else (True,)
    with pytest.raises(BaseFilterRefusal) as excinfo:
        _registry().resolve(_spec(FieldId("fldCheck"), operator, values))
    message = str(excinfo.value)
    assert operator in message
    assert "1254001" in message, "Lark's own code, quoted — the refusal is a report, not a policy"
    assert "Nothing was sent." in message


def test_the_refusal_is_the_house_TYPED_one_so_an_existing_except_still_catches_it():
    from larkdocio.errors import LarkConfigError, LarkDocIOError
    with pytest.raises(LarkConfigError):
        _registry().resolve(_spec(FieldId("fldCheck"), "isNot", (True,)))
    with pytest.raises(LarkDocIOError):
        _registry().resolve(_spec(FieldName("Check"), "isNot", (True,)))
    with pytest.raises(ValueError):
        _registry().resolve(_spec(FieldId("fldCheck"), "isNot", (True,)))


def test_the_refusal_names_the_operator_that_WAS_seen_working_and_the_unmeasured_one():
    """A refusal that does not say what to do instead is half a refusal."""
    with pytest.raises(BaseFilterRefusal) as excinfo:
        _registry().resolve(_spec(FieldId("fldCheck"), "isNot", (True,)))
    message = str(excinfo.value)
    assert "`is`" in message
    assert "doesNotContain" in message and "unmeasured" in message.lower()


def test_the_operator_the_probe_saw_WORKING_passes_through_untouched():
    resolved = _registry().resolve(_spec(FieldId("fldCheck"), "is", (True,)))
    assert resolved.conditions[0] == Condition(FieldId("fldCheck"), "is", (True,))


def test_the_UNMEASURED_operator_is_NOT_refused_because_nobody_asked_Lark():
    """The evidence-keyed half of the allow-list precedent: `doesNotContain` was never sent to a
    Checkbox, so this library does not invent a refusal for it — Lark answers it."""
    resolved = _registry().resolve(_spec(FieldId("fldCheck"), "doesNotContain", (True,)))
    assert resolved.conditions[0].operator == "doesNotContain"


@pytest.mark.parametrize("operator", ("isNot", "contains", "isEmpty", "isNotEmpty"))
def test_a_NON_checkbox_field_is_untouched_by_the_checkbox_refusal(operator):
    """The measurement is about a Checkbox; a TEXT field on the same view took the valueless
    pair, and the control is why the refusal is attributable at all."""
    values = () if operator in vf.VALUELESS_OPERATORS else ("Text 1",)
    resolved = _registry().resolve(_spec(FieldId("fldText"), operator, values))
    assert resolved.conditions[0].operator == operator


def test_a_field_the_registry_never_read_still_passes_through_as_a_snapshot():
    """An id needs no list — the pass-through `RESOLUTION_IS_A_SNAPSHOT` describes is unchanged,
    so nothing new is refused on a field this library cannot see the type of."""
    resolved = _registry().resolve(_spec(FieldId("fldUnknown"), "isNot", (True,)))
    assert resolved.conditions[0].operator == "isNot"


def test_a_NAME_keyed_checkbox_condition_refuses_after_the_name_resolves():
    with pytest.raises(BaseFilterRefusal) as excinfo:
        _registry().resolve(_spec(FieldName("Check"), "contains", (True,)))
    assert "contains" in str(excinfo.value)


def test_a_nested_child_spec_is_refused_too_because_resolve_recurses():
    spec = FilterSpec(children=(_spec(FieldId("fldCheck"), "isNot", (True,)),))
    with pytest.raises(BaseFilterRefusal):
        _registry().resolve(spec)


def test_the_serialiser_itself_is_UNCHANGED_so_a_hand_built_view_filter_still_reaches_Lark():
    """The refusal lives in `resolve()` — the one place that knows the field's TYPE. `view_filter`
    sees only a `fld…` id and cannot know, so it is not the place, and a caller who serialises
    without resolving still gets Lark's own answer rather than a guess of ours."""
    body = vf.view_filter(_spec(FieldId("fldCheck"), "isNot", (True,))).to_dict()
    assert body["conditions"][0]["operator"] == "isNot"


def test_the_measured_operator_scope_is_AUTHORED_ONCE_and_quoted_by_the_refusal():
    sentence = vf.VIEW_ROUTE_CHECKBOX_OPERATOR_SCOPE
    assert "1254001" in sentence and "view" in sentence.lower()
    with pytest.raises(BaseFilterRefusal) as excinfo:
        _registry().resolve(_spec(FieldId("fldCheck"), "isEmpty"))
    assert sentence in str(excinfo.value)


# --------------------------------------------------------------------------- #
# ARM 3 (LD-428) — the JSON-booleans constant is swept to the same truth.       #
# --------------------------------------------------------------------------- #

def test_the_json_booleans_constant_no_longer_claims_isNot_reaches_Lark_unworked_around():
    """LD-408 made ``isNot`` (and the three operators measured alongside it) a LOCAL refusal.
    The exported evidence constant must not still claim that limit is answered by Lark rather
    than by this library — the withdrawn conclusion LD-428 exists to correct."""
    sentence = vf.VIEW_ROUTE_CHECKBOX_TAKES_JSON_BOOLEANS
    assert ("isNot` on a Checkbox is a `1254001` even carrying the accepted value spelling "
            "(only `is` was seen working), and a TWO-element array") not in sentence


def test_the_json_booleans_constant_still_names_the_isNot_measurement_and_points_at_the_scope():
    """The reason (the measurement) is preserved; only the conclusion changes — and the sentence
    points a reader at :data:`VIEW_ROUTE_CHECKBOX_OPERATOR_SCOPE` for what now happens."""
    sentence = vf.VIEW_ROUTE_CHECKBOX_TAKES_JSON_BOOLEANS
    assert "isNot" in sentence
    assert "only `is` was seen working" in sentence
    assert "VIEW_ROUTE_CHECKBOX_OPERATOR_SCOPE" in sentence


def test_the_json_booleans_constant_still_claims_the_two_element_array_limit_unworked_around():
    """The two-element-array limit is genuinely NOT worked around locally (`echoes()` reports the
    silent drop as not-persisted rather than this library absorbing it) — that half of the
    sentence must survive the sweep unchanged."""
    sentence = vf.VIEW_ROUTE_CHECKBOX_TAKES_JSON_BOOLEANS
    assert "NOT worked around locally" in sentence
    assert ("a TWO-element array is accepted with `code:0` and silently stored as the FIRST "
            "element alone") in sentence


@pytest.mark.parametrize("operator", vf.VIEW_ROUTE_CHECKBOX_REFUSED_OPERATORS)
def test_no_locally_refused_operator_is_claimed_unworked_around_by_the_constant(operator):
    """The suggested-fix guard: every operator this registry now refuses locally must not be
    named inside the constant's "NOT worked around locally" clause — that clause is reserved for
    the limit that genuinely still reaches Lark (the two-element array)."""
    sentence = vf.VIEW_ROUTE_CHECKBOX_TAKES_JSON_BOOLEANS
    not_worked_around_clause = sentence.split("NOT worked around locally", 1)[1]
    stop = not_worked_around_clause.find(". ")
    clause_scope = not_worked_around_clause[:stop] if stop != -1 else not_worked_around_clause
    assert operator not in clause_scope, (
        f"{operator!r} is measured refused LOCALLY (LD-408) — it must not sit inside the "
        "constant's claim of what is NOT worked around locally")
