"""LD-264 — ONE filter model, TWO dialects, and the crossing made IMPOSSIBLE (AC2/AC3/AC4).

The design fact this story owns is a **dialect split**: ``records/search`` filters are
``field_name``-keyed and **view** filters are ``field_id``-keyed. The tests below hold that
split at the level the AC demands — *by construction*, not by convention: each dialect's
serialiser produces its **own type**, neither type can be hand-built, and the view route's
signature accepts only the view type. A future contributor cannot forget the rule because the
rule is not written down anywhere they could forget to read.
"""
import pytest

from larkdocio.base import view_filters as vf
from larkdocio.base.view_filters import (
    CONJUNCTIONS,
    FILTER_OPERATORS,
    BaseFilterRefusal,
    Condition,
    FieldId,
    FieldName,
    FieldRegistry,
    FilterSpec,
    SearchFilter,
    ViewFilterInfo,
    search_filter,
    view_filter,
)


# --------------------------------------------------------------------------- #
# The vocabulary — evidence-keyed, both halves                                 #
# --------------------------------------------------------------------------- #

def test_the_operator_vocabulary_is_THE_SIX_THE_CAPTURES_PROVED():
    assert FILTER_OPERATORS == (
        "is", "isNot", "contains", "doesNotContain", "isEmpty", "isNotEmpty")
    assert CONJUNCTIONS == ("and", "or")


def test_an_UNKNOWN_operator_is_refused_LOCALLY_naming_the_captured_refusal():
    spec = FilterSpec(conditions=(Condition(FieldId("fldA"), "wibble", ("x",)),))
    with pytest.raises(BaseFilterRefusal) as excinfo:
        view_filter(spec)
    assert "99992402" in str(excinfo.value)
    assert "isNot" in str(excinfo.value)


def test_isGreater_is_NOT_shipped_and_the_refusal_does_NOT_BLAME_LARK_FOR_IT():
    """`isGreater` on a text field answered `1254018` (p1-q3-01), so no capture shows it
    working — but **the view route's own enum lists it**, which this story's probe captured
    verbatim. An operator the library cannot show working is not in its vocabulary; saying
    Lark refuses it would be false, and the refusal says which of the two it is."""
    assert "isGreater" not in FILTER_OPERATORS
    assert "isGreater" in vf.SERVER_VIEW_OPERATOR_ENUM
    with pytest.raises(BaseFilterRefusal) as excinfo:
        view_filter(FilterSpec(conditions=(Condition(FieldId("fldA"), "isGreater", ("1",)),)))
    message = str(excinfo.value)
    assert vf.SERVER_VIEW_OPERATOR_ENUM in message
    assert "not a refusal by Lark" in message


def test_the_server_operator_enum_is_the_one_the_PROBE_CAPTURED_verbatim():
    import json
    import pathlib

    capture = (pathlib.Path(__file__).resolve().parents[1] / "tests" / "captures" / "base-study" /
               "captures" / "ld264-01-view-filter-vocabulary.json")
    if not capture.exists():
        pytest.skip("the probe capture is not committed in this checkout")
    described = [violation["description"]
                 for step in json.loads(capture.read_text(encoding="utf-8"))["steps"]
                 for violation in (step.get("error") or {}).get("field_violations", [])
                 if "operator" in violation.get("field", "")]
    assert described == [vf.SERVER_VIEW_OPERATOR_ENUM], described


def test_an_unknown_conjunction_is_refused_locally():
    with pytest.raises(BaseFilterRefusal):
        view_filter(FilterSpec(conditions=(Condition(FieldId("fldA"), "is", ("x",)),),
                               conjunction="xor"))


# --------------------------------------------------------------------------- #
# AC2 — the view dialect, in the shape the seat addendum proved                #
# --------------------------------------------------------------------------- #

def test_the_view_dialect_serialises_FIELD_ID_KEYED_camelCase_conditions():
    spec = FilterSpec(
        conjunction="or",
        conditions=(Condition(FieldId("fldbbSDMOY"), "isNotEmpty"),
                    Condition(FieldId("fldOTHER"), "contains", ("Text",))))
    info = view_filter(spec)
    assert isinstance(info, ViewFilterInfo)
    assert info.to_dict() == {
        "conjunction": "or",
        "conditions": [
            # A valueless operator OMITS the key entirely — measured live: `""` answers
            # `1254001` and `[]` answers `9499`, while omitting it is `code:0`.
            {"field_id": "fldbbSDMOY", "operator": "isNotEmpty"},
            # And a value is a STRING carrying a JSON array, which the SDK's own `_types`
            # declares and the live probe confirms.
            {"field_id": "fldOTHER", "operator": "contains", "value": '["Text"]'},
        ],
    }


def test_an_EMPTY_operator_OMITS_the_value_key_entirely():
    """Three shapes were tried live against a disposable and only one is accepted:
    `value: ""` answers `1254001` (the shape `p1-q3-02` had), `value: []` answers `9499`, and
    **omitting the key** answers `code:0` and reads back `value: null`."""
    info = view_filter(FilterSpec(conditions=(Condition(FieldId("fldA"), "isEmpty"),)))
    assert "value" not in info.to_dict()["conditions"][0]
    # The SEARCH route is the other way round: there an empty list is the shape.
    empty = search_filter(FilterSpec(conditions=(Condition(FieldName("A"), "isEmpty"),)))
    assert empty.to_dict()["conditions"][0]["value"] == []


def test_the_TWO_DIALECTS_ENCODE_A_VALUE_DIFFERENTLY_and_that_is_measured():
    """The second reason there are two serialisers rather than one with a flag."""
    spec = FilterSpec(conditions=(Condition(FieldId("fldA"), "is", ("Text 1",)),))
    named = FilterSpec(conditions=(Condition(FieldName("Text"), "is", ("Text 1",)),))
    assert view_filter(spec).to_dict()["conditions"][0]["value"] == '["Text 1"]'
    assert search_filter(named).to_dict()["conditions"][0]["value"] == ["Text 1"]
    assert vf.VIEW_DIALECT.value_encoding == "json-string"
    assert vf.SEARCH_DIALECT.value_encoding == "list"
    assert vf.VIEW_DIALECT.omits_empty_value is True
    assert vf.SEARCH_DIALECT.omits_empty_value is False


def test_a_NON_EMPTY_operator_with_NO_value_is_refused_locally():
    with pytest.raises(BaseFilterRefusal):
        view_filter(FilterSpec(conditions=(Condition(FieldId("fldA"), "is"),)))


def test_an_EMPTY_operator_GIVEN_a_value_is_refused_locally():
    with pytest.raises(BaseFilterRefusal):
        view_filter(FilterSpec(conditions=(Condition(FieldId("fldA"), "isEmpty", ("x",)),)))


def test_the_view_side_ships_ONLY_THE_NESTING_DEPTH_A_CAPTURE_CARRIES():
    """AC2. `children` is proven on the **search** route (`p1-q3-01`) and was never sent to a
    view. So the view serialiser refuses it as `uncaptured` rather than guessing."""
    nested = FilterSpec(conditions=(),
                        children=(FilterSpec(conditions=(
                            Condition(FieldId("fldA"), "is", ("x",)),)),))
    with pytest.raises(BaseFilterRefusal) as excinfo:
        view_filter(nested)
    assert "uncaptured" in str(excinfo.value).lower()
    # The same tree is fine on the search side, where a capture DOES carry it.
    assert search_filter(FilterSpec(
        conditions=(),
        children=(FilterSpec(conditions=(Condition(FieldName("Text"), "is", ("x",)),)),),
    )).to_dict()["children"][0]["conditions"][0]["field_name"] == "Text"


def test_an_empty_filter_is_refused_rather_than_sent_as_a_no_op():
    with pytest.raises(BaseFilterRefusal):
        view_filter(FilterSpec())


# --------------------------------------------------------------------------- #
# AC3 — THE TWO DIALECTS CANNOT CROSS, and it is a TYPE fact                   #
# --------------------------------------------------------------------------- #

def test_the_search_dialect_is_FIELD_NAME_KEYED():
    payload = search_filter(FilterSpec(
        conditions=(Condition(FieldName("Text"), "is", ("Text 1",)),)))
    assert isinstance(payload, SearchFilter)
    assert payload.to_dict() == {
        "conjunction": "and",
        "conditions": [{"field_name": "Text", "operator": "is", "value": ["Text 1"]}],
    }


def test_a_FIELD_ID_at_the_SEARCH_route_is_refused_LOCALLY_naming_1254045():
    """The captured refusal, pinned: `field_names` given an `fld…` id answers `1254045`, and
    a `field_id` in `sort` answers `1254016`. The library meets it at the seam."""
    with pytest.raises(BaseFilterRefusal) as excinfo:
        search_filter(FilterSpec(conditions=(Condition(FieldId("fldbbSDMOY"), "is", ("x",)),)))
    message = str(excinfo.value)
    assert "1254045" in message
    assert "field_name" in message


def test_a_FIELD_NAME_at_the_VIEW_route_is_refused_LOCALLY_in_the_O5_WORDING():
    """The **wording rider**: the message may say the view route requires `field_id`-keyed
    conditions — supportable — and must NOT blame snake_case operators, which the bundled
    probe could not separate from the key."""
    with pytest.raises(BaseFilterRefusal) as excinfo:
        view_filter(FilterSpec(conditions=(Condition(FieldName("Text"), "is", ("x",)),)))
    message = str(excinfo.value)
    assert "field_id" in message
    assert "snake_case" not in message.lower()


def test_THE_WORDING_RIDER_IS_HELD_OVER_EVERY_SHIPPED_SENTENCE_IN_THE_MODULE():
    """O5″ generalized: no sentence anywhere in this module may claim snake_case caused the
    view route's refusal. The 2-call probe separated the variables and the answer is recorded
    in :data:`VOCABULARY_PROBE`; nothing here may say more than the probe supports."""
    import inspect

    assert "snake_case" not in vf.VIEW_ROUTE_REQUIRES_FIELD_ID.lower()
    assert "snake_case" not in vf.SEARCH_ROUTE_REQUIRES_FIELD_NAME.lower()
    probe_text = " ".join(str(v) for v in vf.VOCABULARY_PROBE.values())
    source = inspect.getsource(vf)
    for line in source.splitlines():
        if "snake_case" not in line.lower():
            continue
        # The ONLY place the module may say the word is inside the probe record — where it is
        # a variable that was separated, never an asserted cause.
        assert line.strip().strip('"\',') in probe_text or "VOCABULARY_PROBE" in source[
            :source.index(line)][-400:], line
    assert vf.VOCABULARY_PROBE["verdict"] in (
        "inconclusive", "field_name-key alone", "operator-case alone", "both independently")


def test_THE_CROSSING_IS_IMPOSSIBLE_BY_CONSTRUCTION_not_by_convention():
    """AC3's core. Neither serialised product can be hand-built, so the only way to obtain a
    `ViewFilterInfo` is the view serialiser — which is the only thing the view route takes."""
    with pytest.raises(TypeError):
        ViewFilterInfo({"conjunction": "and", "conditions": []})
    with pytest.raises(TypeError):
        SearchFilter({"conjunction": "and", "conditions": []})
    view = view_filter(FilterSpec(conditions=(Condition(FieldId("fldA"), "is", ("x",)),)))
    search = search_filter(FilterSpec(conditions=(Condition(FieldName("A"), "is", ("x",)),)))
    assert not isinstance(search, ViewFilterInfo)
    assert not isinstance(view, SearchFilter)
    # A serialised filter IS a dict (so a plan serialises to JSON with no special case) — but
    # a plain dict is emphatically NOT one of these, which is the direction that matters.
    assert not isinstance({"conjunction": "and", "conditions": []}, ViewFilterInfo)
    assert view != search, "two dialects' bodies are not the same value even when they rhyme"


def test_the_two_dialects_are_DECLARED_and_each_names_its_own_key_and_route():
    assert vf.VIEW_DIALECT.key == "field_id"
    assert vf.SEARCH_DIALECT.key == "field_name"
    assert vf.VIEW_DIALECT.produces is ViewFilterInfo
    assert vf.SEARCH_DIALECT.produces is SearchFilter
    assert "views/:view_id" in vf.VIEW_DIALECT.route
    assert "records/search" in vf.SEARCH_DIALECT.route
    assert vf.VIEW_DIALECT.key != vf.SEARCH_DIALECT.key


def test_the_operator_vocabulary_is_SHARED_and_the_split_is_THE_KEY():
    """The corrected fact (AC3's row-7 correction): `p1-q3-01` shows the SEARCH route taking
    the very same camelCase operators. So the dialects differ in their **key**, and a shipped
    sentence that said otherwise would be asserting something no capture shows."""
    assert vf.VIEW_DIALECT.operators == vf.SEARCH_DIALECT.operators == FILTER_OPERATORS


# --------------------------------------------------------------------------- #
# AC4 — a name is resolved LOCALLY, from an EXHAUSTED field read               #
# --------------------------------------------------------------------------- #

class _Field:
    def __init__(self, field_id, field_name):
        self.field_id, self.field_name = field_id, field_name


_FIELDS = [_Field("fldbbSDMOY", "Text"), _Field("fldDBZXA76", "Email")]


def test_a_field_NAME_resolves_to_its_id_against_the_read_registry():
    registry = FieldRegistry(_FIELDS, exhaustive=True)
    spec = FilterSpec(conditions=(Condition(FieldName("Text"), "is", ("x",)),))
    resolved = registry.resolve(spec)
    assert resolved.conditions[0].field == FieldId("fldbbSDMOY")
    assert view_filter(resolved).to_dict()["conditions"][0]["field_id"] == "fldbbSDMOY"


def test_a_field_ID_the_caller_supplies_is_PASSED_THROUGH_UNRESOLVED():
    registry = FieldRegistry(_FIELDS, exhaustive=True)
    spec = FilterSpec(conditions=(Condition(FieldId("fldNOTINLIST"), "is", ("x",)),))
    assert registry.resolve(spec).conditions[0] == spec.conditions[0]


def test_an_unresolvable_name_is_a_TYPED_REFUSAL_NAMING_THE_KNOWN_FIELDS():
    registry = FieldRegistry(_FIELDS, exhaustive=True)
    with pytest.raises(BaseFilterRefusal) as excinfo:
        registry.resolve(FilterSpec(conditions=(Condition(FieldName("Nope"), "is", ("x",)),)))
    message = str(excinfo.value)
    assert "'Nope'" in message and "Text" in message and "Email" in message


def test_A_TRUNCATED_FIELD_READ_REFUSES_TO_RESOLVE_AT_ALL():
    """AC4's sharp half. Resolving against a partial list would answer *sometimes*, which is
    worse than not answering: the name that is missing is the one you cannot see is missing."""
    partial = FieldRegistry(_FIELDS[:1], exhaustive=False)
    with pytest.raises(BaseFilterRefusal) as excinfo:
        partial.resolve(FilterSpec(conditions=(Condition(FieldName("Text"), "is", ("x",)),)))
    assert "exhaust" in str(excinfo.value).lower()


def test_a_truncated_registry_still_passes_a_FIELD_ID_through():
    """A caller who supplied ids needs no registry at all, so a truncated one cannot hurt
    them — the refusal is scoped to the thing that actually needs the list."""
    partial = FieldRegistry(_FIELDS[:1], exhaustive=False)
    spec = FilterSpec(conditions=(Condition(FieldId("fldZ"), "is", ("x",)),))
    assert partial.resolve(spec) == spec


def test_the_registry_built_from_the_read_client_is_EXHAUSTIVE_because_the_client_pages():
    class _Read:
        def list_fields(self, app_token, table_id):
            return _FIELDS

    registry = FieldRegistry.from_read_client(_Read(), "appX", "tblX")
    assert registry.exhaustive is True
    assert registry.resolve(
        FilterSpec(conditions=(Condition(FieldName("Email"), "is", ("x",)),))
    ).conditions[0] == Condition(FieldId("fldDBZXA76"), "is", ("x",))


def test_resolution_reaches_CHILDREN_too_so_a_search_tree_is_resolvable():
    registry = FieldRegistry(_FIELDS, exhaustive=True)
    spec = FilterSpec(conditions=(),
                      children=(FilterSpec(conditions=(
                          Condition(FieldName("Text"), "is", ("x",)),)),))
    assert registry.resolve(spec).children[0].conditions[0].field == FieldId("fldbbSDMOY")


def test_the_AMPLIFIER_a_field_DELETED_between_resolve_and_patch_is_the_SERVERS_answer():
    """Test-rigor amplifier. The library resolves against the list it read; a field deleted
    afterwards is a race no local check can win, so the id simply goes out and Lark answers.
    What the library must NOT do is pretend the resolution is still valid — the refusal is
    the server's, and the module says so in one place."""
    assert "deleted" in vf.RESOLUTION_IS_A_SNAPSHOT.lower()
    registry = FieldRegistry(_FIELDS, exhaustive=True)
    resolved = registry.resolve(
        FilterSpec(conditions=(Condition(FieldName("Text"), "is", ("x",)),)))
    # Nothing re-checks the id at serialise time — it is sent, and the server decides.
    assert view_filter(resolved).to_dict()["conditions"][0]["field_id"] == "fldbbSDMOY"


# --------------------------------------------------------------------------- #
# The comparison AC5 rests on: SEMANTIC, explicit, tested — never a loose `in` #
# --------------------------------------------------------------------------- #

def test_the_read_back_normaliser_DROPS_THE_SERVERS_OWN_ADDITIONS():
    """The server echoes `condition_id` and `field_type` back. A comparison that did not
    normalise them would report every persisted filter as not-persisted."""
    sent = view_filter(FilterSpec(conditions=(Condition(FieldId("fldA"), "is", ("x",)),)))
    echoed = {
        "conjunction": "and",
        "conditions": [{"field_id": "fldA", "operator": "is", "value": '["x"]',
                        "condition_id": "conXYZ", "field_type": 1}],
    }
    assert vf.normalize_persisted(echoed) == sent.to_dict()
    assert vf.echoes(sent, echoed) is True


def test_the_read_back_normaliser_DROPS_A_NULL_VALUE_because_that_is_the_OMITTED_KEY():
    """A valueless operator omits `value`; the server echoes it back as `null`. Dropping that
    `None` **by name** is what makes the round trip compare — and it is the only value the
    normaliser drops, so a value the server REWROTE still fails the comparison."""
    sent = view_filter(FilterSpec(conditions=(Condition(FieldId("fldA"), "isNotEmpty"),)))
    assert vf.echoes(sent, {"conjunction": "and", "conditions": [
        {"field_id": "fldA", "operator": "isNotEmpty", "value": None,
         "condition_id": "c1", "field_type": 1}]}) is True
    assert vf.echoes(sent, {"conjunction": "and", "conditions": [
        {"field_id": "fldA", "operator": "isNotEmpty", "value": '["surprise"]'}]}) is False


def test_the_read_back_comparison_is_FALSE_when_the_server_persisted_SOMETHING_ELSE():
    sent = view_filter(FilterSpec(conditions=(Condition(FieldId("fldA"), "is", ("x",)),)))
    assert vf.echoes(sent, {"conjunction": "and", "conditions": [
        {"field_id": "fldA", "operator": "isNot", "value": '["x"]'}]}) is False
    assert vf.echoes(sent, None) is False
    assert vf.echoes(sent, {}) is False


def test_the_comparison_is_NOT_a_loose_containment_check():
    """A `sent_dict.items() <= read_dict.items()` style check would pass a read-back that
    carried an EXTRA condition the caller never asked for. It must not."""
    sent = view_filter(FilterSpec(conditions=(Condition(FieldId("fldA"), "is", ("x",)),)))
    extra = {"conjunction": "and", "conditions": [
        {"field_id": "fldA", "operator": "is", "value": '["x"]'},
        {"field_id": "fldB", "operator": "is", "value": '["y"]'}]}
    assert vf.echoes(sent, extra) is False


def test_the_ALTER_case_the_second_read_back_must_be_the_SECOND_FILTER_not_a_merge():
    """Test-rigor amplifier: set then alter. A server that merged would leave the first
    condition in place, and `echoes` has to call that not-persisted."""
    second = view_filter(FilterSpec(conditions=(Condition(FieldId("fldB"), "is", ("y",)),)))
    merged = {"conjunction": "and", "conditions": [
        {"field_id": "fldA", "operator": "is", "value": '["x"]'},
        {"field_id": "fldB", "operator": "is", "value": '["y"]'}]}
    assert vf.echoes(second, merged) is False
    assert vf.echoes(second, {"conjunction": "and", "conditions": [
        {"field_id": "fldB", "operator": "is", "value": '["y"]',
         "condition_id": "c1", "field_type": 1}]}) is True


# --------------------------------------------------------------------------- #
# LD-282 — the read-back must not cry wolf on a value LARK ITSELF RE-TYPED      #
# --------------------------------------------------------------------------- #

#: The exact pair from the bug's live capture: what this library can only send, and what the
#: server read back for it. They differ in JSON quoting alone — the filter is the same filter.
LD282_SENT_VALUE = '["ExactDate", "1786147200000"]'
LD282_PERSISTED_VALUE = '["ExactDate",1786147200000]'


def test_LD282_a_NUMERIC_valued_filter_THAT_LANDED_echoes_TRUE():
    """The bug: `_condition_body` `str()`s every value, so an epoch goes out quoted; Lark
    parses the array and stores the number **unquoted**; a raw string compare then reported
    `dropped` for a filter that is in the server's own state (live capture, session P3)."""
    sent = view_filter(FilterSpec(
        conditions=(Condition(FieldId("fldPWMeSwR"), "is", ("ExactDate", 1786147200000)),)))
    assert sent.to_dict()["conditions"][0]["value"] == LD282_SENT_VALUE, (
        "the caller cannot influence this encoding — that is why the comparison must absorb it")
    persisted = {"conjunction": "and", "conditions": [
        {"field_id": "fldPWMeSwR", "operator": "is", "value": LD282_PERSISTED_VALUE,
         "condition_id": "conABC", "field_type": 5}]}
    assert vf.echoes(sent, persisted) is True


def test_LD282_the_int_and_the_str_spelling_of_the_SAME_epoch_both_echo():
    """The consumer passed the epoch both ways and got the identical quoted body and the
    identical false `dropped`. Both spellings are the same filter, and both must echo."""
    persisted = {"conjunction": "and", "conditions": [
        {"field_id": "fldA", "operator": "is", "value": LD282_PERSISTED_VALUE}]}
    for epoch in (1786147200000, "1786147200000"):
        sent = view_filter(FilterSpec(
            conditions=(Condition(FieldId("fldA"), "is", ("ExactDate", epoch)),)))
        assert vf.echoes(sent, persisted) is True, epoch


def test_LD282_a_BARE_number_and_a_FLOAT_echo_too():
    for value, stored in ((42, "[42]"), (1.5, "[1.5]"), (True, "[true]")):
        sent = view_filter(FilterSpec(
            conditions=(Condition(FieldId("fldA"), "is", (value,)),)))
        assert vf.echoes(sent, {"conjunction": "and", "conditions": [
            {"field_id": "fldA", "operator": "is", "value": stored}]}) is True, value


def test_LD282_the_TOLERANCE_IS_RETYPING_ONLY_a_REWRITTEN_number_is_still_DROPPED():
    """The negative controls that make the fix a fix rather than a loosening: a server that
    stored a **different** number, dropped an element, added one, or reordered them is still
    reported not-persisted."""
    sent = view_filter(FilterSpec(
        conditions=(Condition(FieldId("fldA"), "is", ("ExactDate", 1786147200000)),)))
    for stored in ('["ExactDate",1786147200001]',        # one millisecond off
                   '["ExactDate"]',                       # the number dropped
                   '["ExactDate",1786147200000,"x"]',     # an element added
                   '[1786147200000,"ExactDate"]',         # reordered
                   '["ExactDate",178614720]',             # truncated
                   'ExactDate,1786147200000'):            # not JSON at all
        assert vf.echoes(sent, {"conjunction": "and", "conditions": [
            {"field_id": "fldA", "operator": "is", "value": stored}]}) is False, stored


def test_LD282_the_normaliser_still_reports_WHAT_THE_SERVER_ACTUALLY_STORED():
    """The tolerance lives in the comparison, not in the disclosure: `normalize_persisted` is
    what the apply-log shows a caller, and it keeps the server's own bytes."""
    persisted = {"conjunction": "and", "conditions": [
        {"field_id": "fldA", "operator": "is", "value": LD282_PERSISTED_VALUE,
         "condition_id": "c1", "field_type": 5}]}
    assert vf.normalize_persisted(persisted)["conditions"][0]["value"] == LD282_PERSISTED_VALUE


# --------------------------------------------------------------------------- #
# LD-318 — the OPTION half of resolve(): a select value is keyed by `opt…` id   #
# --------------------------------------------------------------------------- #
#
# The defect this section pins: `resolve()` translated a condition's FIELD and never looked at
# its VALUES, so an option NAME — the only thing a consumer holds — sailed through `dry_run` and
# died at apply on Lark's own *"the option id of 'Single Option' is not found"*. That is the
# dry-run-passes / apply-fails shape the plan gate exists to prevent.
#
# The DECISION (LD-318 AC1) is **translate**: a known option name becomes its id, an unknown one
# refuses locally naming what exists, and an id the caller already holds passes through — the
# same rule the field key follows.

_OPT_DONE, _OPT_TODO = "opt552919755", "opt553396111"


class _Option:
    """An option as the SDK's typed door delivers it: an object, not a mapping."""

    def __init__(self, option_id, name):
        self.id, self.name = option_id, name


class _Property:
    """A property as the SDK's typed door delivers it — the door LD-281 proved a mapping-only
    walk cannot read."""

    def __init__(self, options):
        self.options = options


class _SelectField:
    def __init__(self, field_id, field_name, ui_type="SingleSelect", type=3, options=(
            (_OPT_DONE, "Done"), (_OPT_TODO, "Todo"))):
        self.field_id, self.field_name = field_id, field_name
        self.ui_type, self.type = ui_type, type
        self.property = None if options is None else _Property(
            [_Option(i, n) for i, n in options])


def _typed_door():
    return [_SelectField("fldSELECT01", "Single option"),
            _SelectField("fldNFTI2013", "Text", ui_type="Text", type=1, options=None)]


def _bridged_door():
    """The bridged dict `larkdocio.base.table.field_spec` produces with the SDK's own
    serializer — the second of the three doors a field arrives through."""
    from larkdocio.base.table import field_spec
    return [field_spec(field) for field in _typed_door()]


def _wire_door():
    """A captured payload's wire dict, verbatim — mappings all the way down."""
    return [
        {"field_id": "fldSELECT01", "field_name": "Single option", "ui_type": "SingleSelect",
         "type": 3, "property": {"options": [{"id": _OPT_DONE, "name": "Done"},
                                             {"id": _OPT_TODO, "name": "Todo"}]}},
        {"field_id": "fldNFTI2013", "field_name": "Text", "ui_type": "Text", "type": 1,
         "property": None},
    ]


_DOORS = {"typed": _typed_door, "bridged": _bridged_door, "wire": _wire_door}


@pytest.mark.parametrize("door", sorted(_DOORS))
def test_LD318_a_known_option_NAME_becomes_ITS_ID_through_ALL_THREE_DOORS(door):
    """AC1 (translate) + AC2 (three doors answer identically). The registry now RETAINS enough
    of `property` to answer the option question — it used to keep two strings and discard the
    rest — and it reads it through the one by-name walk, so the typed door's nested objects are
    not the blind spot LD-281 cost a shipped refusal over."""
    registry = FieldRegistry(_DOORS[door](), exhaustive=True)
    resolved = registry.resolve(FilterSpec(conditions=(
        Condition(FieldName("Single option"), "is", ("Done",)),)))
    assert resolved.conditions[0] == Condition(FieldId("fldSELECT01"), "is", (_OPT_DONE,))
    assert view_filter(resolved).to_dict()["conditions"][0]["value"] == f'["{_OPT_DONE}"]'


@pytest.mark.parametrize("door", sorted(_DOORS))
def test_LD318_an_UNKNOWN_option_name_REFUSES_LOCALLY_naming_the_ids_that_exist(door):
    registry = FieldRegistry(_DOORS[door](), exhaustive=True)
    with pytest.raises(BaseFilterRefusal) as excinfo:
        registry.resolve(FilterSpec(conditions=(
            Condition(FieldName("Single option"), "is", ("Shipped",)),)))
    message = str(excinfo.value)
    assert "'Shipped'" in message
    assert _OPT_DONE in message and "'Done'" in message and "'Todo'" in message
    assert vf.VIEW_ROUTE_REQUIRES_OPTION_ID in message
    assert "Nothing was sent." in message


@pytest.mark.parametrize("door", sorted(_DOORS))
def test_LD318_an_option_ID_the_caller_ALREADY_HOLDS_passes_through_UNRESOLVED(door):
    """AC1's pass-through half — the same rule `resolve()` already applies to a FieldId, for
    the same reason: they said which option they meant."""
    registry = FieldRegistry(_DOORS[door](), exhaustive=True)
    spec = FilterSpec(conditions=(Condition(FieldId("fldSELECT01"), "is", (_OPT_TODO,)),))
    assert registry.resolve(spec) == spec


@pytest.mark.parametrize("door", sorted(_DOORS))
def test_LD318_a_NON_SELECT_fields_values_are_UNTOUCHED(door):
    registry = FieldRegistry(_DOORS[door](), exhaustive=True)
    resolved = registry.resolve(FilterSpec(conditions=(
        Condition(FieldName("Text"), "is", ("Done",)),)))
    assert resolved.conditions[0] == Condition(FieldId("fldNFTI2013"), "is", ("Done",))


def test_LD318_a_select_whose_OPTIONS_MAP_DID_NOT_ARRIVE_REFUSES_rather_than_guessing():
    """AC2's sharp half — the `exhaustive` doctrine EXTENDED, not weakened. A select field with
    no readable options map cannot tell a valid option from an invalid one, so it refuses for
    the same reason a partial field list refuses a name."""
    registry = FieldRegistry([_SelectField("fldSELECT01", "Single option", options=None)],
                             exhaustive=True)
    with pytest.raises(BaseFilterRefusal) as excinfo:
        registry.resolve(FilterSpec(conditions=(
            Condition(FieldName("Single option"), "is", ("Done",)),)))
    message = str(excinfo.value)
    assert "did not arrive" in message and vf.VIEW_ROUTE_REQUIRES_OPTION_ID in message


def test_LD318_a_select_with_NO_OPTIONS_YET_says_so_rather_than_listing_an_empty_set():
    """A freshly created Base's default `Single option` column really does carry `options: []`
    until a record writes one — measured live — so this is a shape a consumer meets, and the
    sentence it gets is different from the unreadable one."""
    registry = FieldRegistry([_SelectField("fldSELECT01", "Single option", options=())],
                             exhaustive=True)
    with pytest.raises(BaseFilterRefusal) as excinfo:
        registry.resolve(FilterSpec(conditions=(
            Condition(FieldName("Single option"), "is", ("Done",)),)))
    assert "NO options at all" in str(excinfo.value)


def test_LD318_MULTISELECT_rides_the_same_path_and_the_docstring_SAYS_SO():
    """Out of scope says: if the fix covers MultiSelect, say so and test it. It does — the
    options live in the same property under the same key — and only the SingleSelect half is
    proven live, which the docstring states rather than implying coverage."""
    registry = FieldRegistry(
        [_SelectField("fldMULTI001", "Tags", ui_type="MultiSelect", type=4)], exhaustive=True)
    resolved = registry.resolve(FilterSpec(conditions=(
        Condition(FieldName("Tags"), "is", ("Done", "Todo")),)))
    assert resolved.conditions[0].values == (_OPT_DONE, _OPT_TODO)
    assert "MultiSelect" in FieldRegistry.resolve.__doc__


def test_LD318_a_VALUELESS_operator_on_a_select_translates_nothing():
    registry = FieldRegistry(_typed_door(), exhaustive=True)
    spec = FilterSpec(conditions=(Condition(FieldName("Single option"), "isEmpty"),))
    assert registry.resolve(spec).conditions[0] == Condition(FieldId("fldSELECT01"), "isEmpty")


def test_LD318_a_TRUNCATED_registry_refuses_the_OPTION_question_too():
    partial = FieldRegistry(_typed_door(), exhaustive=False)
    with pytest.raises(BaseFilterRefusal) as excinfo:
        partial.resolve(FilterSpec(conditions=(
            Condition(FieldId("fldSELECT01"), "is", ("Done",)),)))
    assert "exhaust" in str(excinfo.value).lower()


def test_LD318_a_FIELD_ID_NOT_IN_THE_LIST_keeps_its_pass_through_and_is_not_refused():
    """The snapshot doctrine, unchanged: an id needs no list. The registry cannot know whether
    an unknown id is a select, so it translates nothing and refuses nothing — Lark answers."""
    registry = FieldRegistry(_typed_door(), exhaustive=True)
    spec = FilterSpec(conditions=(Condition(FieldId("fldNOTINLIST"), "is", ("Done",)),))
    assert registry.resolve(spec) == spec


def test_LD318_the_property_read_REUSES_the_ONE_by_name_walk_and_does_not_fork_a_fourth():
    """AC2's mechanism check: the walk is imported from `_typed`, and this call site keeps its
    own key list because that module's docstring forbids it one."""
    from larkdocio.base import _typed
    assert vf._step is _typed._step and vf._nested is _typed._nested
    assert vf._OPTIONS_PATH == ("property", "options")


def test_LD318_the_SHIPPED_SENTENCE_is_authored_ONCE_beside_the_code_and_EXPORTED():
    """AC5. One author, in the style of VIEW_ROUTE_REQUIRES_FIELD_ID, quoted by the refusals
    rather than restated in them."""
    assert "opt" in vf.VIEW_ROUTE_REQUIRES_OPTION_ID
    assert "option id of" in vf.VIEW_ROUTE_REQUIRES_OPTION_ID
    assert "VIEW_ROUTE_REQUIRES_OPTION_ID" in vf.__all__
    assert "SEARCH_ROUTE_TAKES_OPTION_NAME" in vf.__all__


def test_LD318_AC4_the_SEARCH_route_is_MEASURED_and_its_serialiser_translates_NOTHING():
    """AC4 — established, not assumed. Measured live 2026-08-07 on a self-provisioned
    disposable: `is` / 'Done' returned the 2 matching rows of 3, and the same condition
    carrying that option's `opt…` id answered `1254018 InvalidFilter`. So the search dialect is
    the mirror at the VALUE as well as at the KEY, and `search_filter()` sends the name as
    given."""
    assert "1254018" in vf.SEARCH_ROUTE_TAKES_OPTION_NAME
    assert "NAME" in vf.SEARCH_ROUTE_TAKES_OPTION_NAME
    body = search_filter(FilterSpec(conditions=(
        Condition(FieldName("Single option"), "is", ("Done",)),))).to_dict()
    assert body["conditions"][0] == {"field_name": "Single option", "operator": "is",
                                    "value": ["Done"]}


def test_LD318_AC6_the_read_back_comparison_is_NOT_WIDENED_by_the_translation():
    """An option-id translation must not widen what the read-back forgives: a server that
    stored a DIFFERENT option id is still reported not-persisted."""
    sent = view_filter(FilterSpec(conditions=(
        Condition(FieldId("fldSELECT01"), "is", (_OPT_DONE,)),)))
    assert vf.echoes(sent, {"conjunction": "and", "conditions": [
        {"field_id": "fldSELECT01", "operator": "is", "value": f'["{_OPT_DONE}"]',
         "condition_id": "c1", "field_type": 3}]}) is True
    assert vf.echoes(sent, {"conjunction": "and", "conditions": [
        {"field_id": "fldSELECT01", "operator": "is", "value": f'["{_OPT_TODO}"]'}]}) is False
    # And the name it was translated FROM is not quietly accepted as an echo either.
    assert vf.echoes(sent, {"conjunction": "and", "conditions": [
        {"field_id": "fldSELECT01", "operator": "is", "value": '["Done"]'}]}) is False


def test_LD314_QA_rider_SortKey_is_EXPORTED_because_the_shipped_guide_imports_it_BY_NAME():
    assert "SortKey" in vf.__all__ and vf.SortKey is not None
