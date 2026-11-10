"""LD-314 — THE READ-FILTER TRANSPORT: what ``search_filter()`` builds, ``search_records`` sends.

Every test here is offline. The wire assertions are made against the **request objects the
shipped client handed the SDK**, marshalled by the SDK's own ``JSON.marshal`` — so a test asserts
the bytes that would leave the process, not a Python intention.

**Why the assertions are shaped like this.** ``records/search`` silently ignores every body key
it does not recognise (R12, ``client.py:29``), so no offline test — and no ``code:0`` — can prove
a parameter was *honoured*. Offline, the strongest available statement is an **exact wire-shape**
assertion plus a **local refusal** for every shape this library will not send; the honouring is
proven live, differentially, in ``tests/test_live_base_read_filter.py`` (filter + sort, read-only
against the Scratch Base) and ``tests/test_live_base_view_scoped_read.py`` (``view_id``, against
a harness-created disposable). This module is the half that runs in ``pytest -q``.
"""
import inspect
import json
from pathlib import Path

import pytest
from lark_oapi.api.bitable.v1 import (
    Condition as SdkCondition,
    FilterInfo as SdkFilterInfo,
    SearchAppTableRecordResponse,
    Sort as SdkSort,
)
from lark_oapi.core.json import JSON

from larkdocio.base.client import BaseReadClient
from larkdocio.base.view_filters import (
    BaseFilterRefusal,
    Condition,
    FieldId,
    FieldName,
    FilterSpec,
    SortKey,
    search_filter,
    view_filter,
)

_REPO = Path(__file__).resolve().parent.parent
_CAPTURES = _REPO / "tests" / "captures" / "base-study" / "captures"


# --------------------------------------------------------------------------- #
# The smallest possible fake SDK: it records the request and hands back a page. #
# --------------------------------------------------------------------------- #

class _Leg:
    pass


class _Recorder:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, *args, **kwargs):
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self.responses) - 1)
        return self.responses[index]


class _CountingLimiter:
    def __init__(self):
        self.acquisitions = 0

    def acquire(self):
        self.acquisitions += 1


def page(ids, *, has_more=False, token=None):
    data = {"items": [{"record_id": rid, "fields": {}} for rid in ids],
            "has_more": has_more, "total": len(ids)}
    if token is not None:
        data["page_token"] = token
    return JSON.unmarshal(json.dumps({"code": 0, "msg": "success", "data": data}),
                          SearchAppTableRecordResponse)


def client(*pages):
    sdk = _Leg()
    sdk.bitable = _Leg()
    sdk.bitable.v1 = _Leg()
    sdk.bitable.v1.app_table_record = _Leg()
    recorder = _Recorder(pages or [page(["rec1"])])
    sdk.bitable.v1.app_table_record.search = recorder
    read = BaseReadClient("id", "secret", sdk_client=sdk, rate_limiter=_CountingLimiter())
    return read, recorder


def sent_body(recorder, index=0):
    """The body of the ``index``-th request, as the SDK would put it on the wire."""
    return json.loads(JSON.marshal(recorder.requests[index].body))


def sent_query(recorder, index=0):
    return dict(recorder.requests[index].queries)


ONE = FilterSpec(conditions=(Condition(FieldName("Text"), "is", ("Text 1",)),))


# --------------------------------------------------------------------------- #
# AC1 — the signature is ONE decision                                          #
# --------------------------------------------------------------------------- #

def test_the_SIGNATURE_carries_ALL_THREE_keyword_only_in_one_decision():
    """LD-303's Decision: filter, ``view_id`` and sort are *"one signature decision and one live
    proof, not three"*. Shipping two of three is what this asserts against."""
    params = inspect.signature(BaseReadClient.search_records).parameters
    assert list(params) == ["self", "app_token", "table_id", "filter", "view_id", "sort"], (
        f"the read's signature moved: {inspect.signature(BaseReadClient.search_records)}")
    for name in ("filter", "view_id", "sort"):
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY, (
            f"{name} must be keyword-only — a positional filter reads as a table id at the "
            "call site, and every one of these is optional")
        assert params[name].default is None, f"{name} must default to None (an unfiltered read)"


def test_an_UNFILTERED_READ_sends_EXACTLY_what_it_always_did():
    """The regression fence. Widening a signature must not widen the default body: an
    unfiltered read is still the one-key body the R12 restraint was written about."""
    read, recorder = client()
    read.search_records("app", "tbl")
    assert sent_body(recorder) == {"automatic_fields": False}, (
        "the default read grew a body key; `None` must mean the key is ABSENT, not empty")
    assert sent_query(recorder) == {"page_size": "100"}


def test_a_MISSPELLED_PARAMETER_is_a_LOCAL_TypeError_which_is_the_R12_DEFENCE():
    """R12's lesson turned into a property of the signature: there are no ``**kwargs`` here, so a
    parameter this client does not ship cannot be *silently* forwarded and silently ignored. The
    caller learns locally, before a call is paced."""
    read, _ = client()
    with pytest.raises(TypeError):
        read.search_records("app", "tbl", filtre=search_filter(ONE))
    with pytest.raises(TypeError):
        read.search_records("app", "tbl", group_by=["Text"])


# --------------------------------------------------------------------------- #
# AC2 (offline half) — the filter's exact wire shape                           #
# --------------------------------------------------------------------------- #

def test_the_FILTER_travels_as_the_SDKs_OWN_TYPED_FilterInfo_not_a_dict():
    """The module's by-construction defence: the request is built from the SDK's typed builders,
    never a hand-assembled dict, so a key cannot be silently misplaced."""
    read, recorder = client()
    read.search_records("app", "tbl", filter=search_filter(ONE))
    body = recorder.requests[0].request_body
    assert isinstance(body.filter, SdkFilterInfo)
    assert all(isinstance(c, SdkCondition) for c in body.filter.conditions)


def test_the_FILTER_reaches_the_wire_BYTE_FOR_BYTE_as_search_filter_built_it():
    """The producer and the transport are pinned to each other: whatever ``search_filter()``
    spells is what leaves the process, with no re-spelling in between."""
    read, recorder = client()
    built = search_filter(ONE)
    read.search_records("app", "tbl", filter=built)
    assert sent_body(recorder)["filter"] == built.to_dict()
    assert sent_body(recorder)["filter"] == {
        "conjunction": "and",
        "conditions": [{"field_name": "Text", "operator": "is", "value": ["Text 1"]}]}


def test_a_VALUELESS_OPERATOR_keeps_its_EMPTY_ARRAY_on_the_search_route():
    """The two dialects disagree here and the transport must not helpfully "fix" it: the search
    route takes ``value: []``; only the view route omits the key."""
    read, recorder = client()
    read.search_records("app", "tbl", filter=search_filter(
        FilterSpec(conditions=(Condition(FieldName("Text"), "isNotEmpty"),))))
    assert sent_body(recorder)["filter"]["conditions"][0]["value"] == []


def test_ONE_LEVEL_of_CHILDREN_travels_because_a_capture_proved_it():
    """``p1-q3-01`` step 24 sent a nested tree and got the right single row back."""
    nested = FilterSpec(
        conjunction="and",
        children=(FilterSpec(conjunction="or", conditions=(
            Condition(FieldName("Text"), "is", ("Text 1",)),
            Condition(FieldName("Text"), "is", ("Text 3",)))),))
    read, recorder = client()
    read.search_records("app", "tbl", filter=search_filter(nested))
    assert sent_body(recorder)["filter"]["children"] == [
        {"conjunction": "or",
         "conditions": [{"field_name": "Text", "operator": "is", "value": ["Text 1"]},
                        {"field_name": "Text", "operator": "is", "value": ["Text 3"]}]}]


def test_a_SECOND_LEVEL_of_nesting_is_REFUSED_rather_than_hand_assembled():
    """Two reasons that point the same way, and the refusal names both: no capture nests twice,
    and the SDK's ``ChildrenFilter`` has no ``children`` field at all — so sending it would mean
    hand-assembling the dict this module refuses to hand-assemble."""
    deep = FilterSpec(children=(FilterSpec(children=(FilterSpec(conditions=(
        Condition(FieldName("Text"), "is", ("Text 1",)),)),)),))
    read, recorder = client()
    with pytest.raises(BaseFilterRefusal) as excinfo:
        read.search_records("app", "tbl", filter=search_filter(deep))
    assert "Nothing was sent." in str(excinfo.value)
    assert not recorder.requests, "the refusal must land BEFORE the call"


# --------------------------------------------------------------------------- #
# The refusals — every wrong shape stopped locally                            #
# --------------------------------------------------------------------------- #

def test_the_VIEW_DIALECT_handed_to_the_READ_is_refused_before_any_call():
    """The crossing the type seal exists to make impossible, now that a read has somewhere to
    put a filter — this is the moment that seal earns its keep."""
    read, recorder = client()
    wrong = view_filter(FilterSpec(conditions=(Condition(FieldId("fldabc"), "isNotEmpty"),)))
    with pytest.raises(BaseFilterRefusal) as excinfo:
        read.search_records("app", "tbl", filter=wrong)
    message = str(excinfo.value)
    assert "view" in message and "search_filter" in message
    assert "Nothing was sent." in message
    assert not recorder.requests


def test_a_RAW_FilterSpec_is_refused_and_told_which_serialiser_to_run():
    """A ``FilterSpec`` is dialect-neutral by design. The client picking a dialect for the caller
    would be the library guessing between ``field_name`` and ``field_id`` — the one guess this
    whole module exists to prevent."""
    read, _ = client()
    with pytest.raises(BaseFilterRefusal) as excinfo:
        read.search_records("app", "tbl", filter=ONE)
    assert "search_filter(" in str(excinfo.value)


def test_a_PLAIN_DICT_is_refused_even_when_it_looks_exactly_right():
    """The seal is on the type, not on the shape — a correct-looking dict has not been through
    the operator, value and conjunction checks, and that is what the type stands for."""
    read, _ = client()
    with pytest.raises(BaseFilterRefusal):
        read.search_records("app", "tbl", filter={
            "conjunction": "and",
            "conditions": [{"field_name": "Text", "operator": "is", "value": ["Text 1"]}]})


# --------------------------------------------------------------------------- #
# AC4 (offline half) — sort                                                    #
# --------------------------------------------------------------------------- #

def test_the_SORT_travels_as_typed_Sort_objects_IN_THE_ORDER_GIVEN():
    """A multi-key sort is ordered; a set would be a different feature."""
    read, recorder = client()
    read.search_records("app", "tbl", sort=(SortKey(FieldName("Email")),
                                            SortKey(FieldName("Text"), desc=True)))
    assert all(isinstance(s, SdkSort) for s in recorder.requests[0].request_body.sort)
    assert sent_body(recorder)["sort"] == [{"field_name": "Email", "desc": False},
                                           {"field_name": "Text", "desc": True}]


def test_a_SORT_KEYED_BY_FIELD_ID_is_refused_LOCALLY_with_the_captured_code():
    """``p1-q3-01`` step 7: a ``fld…`` id in ``sort`` is a hard ``1254016``. The library knows
    that already, so the caller gets a sentence instead of a round trip to an opaque code."""
    with pytest.raises(BaseFilterRefusal) as excinfo:
        SortKey(FieldId("fldbbSDMOY"))
    assert "1254016" in str(excinfo.value)


def test_an_EMPTY_SORT_LIST_is_refused_rather_than_sent_as_a_no_op():
    """The house rule from ``_serialise``: say what you mean. ``sort=[]`` is the sort-shaped
    version of an empty filter."""
    read, _ = client()
    with pytest.raises(BaseFilterRefusal):
        read.search_records("app", "tbl", sort=())


def test_FILTER_AND_SORT_TOGETHER_is_allowed_because_a_capture_proved_the_pair():
    """``p1-q3-01`` step 23 sent filter + sort in one body and got the filtered rows in the
    sorted order. The combination ships because it is captured, not because it is plausible."""
    read, recorder = client()
    read.search_records("app", "tbl", filter=search_filter(
        FilterSpec(conditions=(Condition(FieldName("Text"), "isNotEmpty"),))),
        sort=(SortKey(FieldName("Text"), desc=True),))
    body = sent_body(recorder)
    assert "filter" in body and "sort" in body


# --------------------------------------------------------------------------- #
# AC3 (offline half) — view_id                                                 #
# --------------------------------------------------------------------------- #

def test_the_VIEW_ID_travels_on_the_BODY_and_never_on_the_QUERY_STRING():
    """The mirror of trap 1: ``page_size`` is honoured in the query and ignored in the body, and
    ``view_id`` is a body key on this endpoint. Placement is the assertion."""
    read, recorder = client()
    read.search_records("app", "tbl", view_id="vewN5yTV1k")
    assert sent_body(recorder)["view_id"] == "vewN5yTV1k"
    assert "view_id" not in sent_query(recorder)


def test_a_VIEW_ID_COMBINED_with_a_filter_or_a_sort_is_REFUSED_as_UNCAPTURED():
    """The honest edge of this issue. How a view's SAVED filter composes with a request filter —
    intersection? override? — is something no capture in this repository shows, and the R12
    family answers ``code:0`` to both readings. So the combination is refused with the reason,
    rather than shipped on a guess a consumer would then rely on."""
    read, recorder = client()
    for extra in ({"filter": search_filter(ONE)},
                  {"sort": (SortKey(FieldName("Text")),)}):
        with pytest.raises(BaseFilterRefusal) as excinfo:
            read.search_records("app", "tbl", view_id="vew1", **extra)
        assert "uncaptured" in str(excinfo.value).lower()
        assert "Nothing was sent." in str(excinfo.value)
    assert not recorder.requests


# --------------------------------------------------------------------------- #
# AC9 — the pagination interplay, pinned rather than merely stated             #
# --------------------------------------------------------------------------- #

def test_the_FILTER_IS_RE_SENT_ON_EVERY_PAGE_of_a_multi_page_filtered_walk():
    """A filtered read that silently returned only the first page would be a **Critical** bug,
    and a filter dropped on page two would return unfiltered rows under a filtered ask. The body
    is rebuilt inside the page closure, so every page carries all three; the cursor rides the
    query string, where the server honours it."""
    read, recorder = client(page(["r1", "r2"], has_more=True, token="tok1"),
                            page(["r3"], has_more=False))
    records = read.search_records("app", "tbl", filter=search_filter(ONE),
                                  sort=(SortKey(FieldName("Text"), desc=True),))
    assert [r.record_id for r in records] == ["r1", "r2", "r3"]
    assert len(recorder.requests) == 2
    for index in (0, 1):
        assert sent_body(recorder, index)["filter"] == search_filter(ONE).to_dict()
        assert sent_body(recorder, index)["sort"] == [{"field_name": "Text", "desc": True}]
    assert "page_token" not in sent_query(recorder, 0)
    assert sent_query(recorder, 1)["page_token"] == "tok1", (
        "the cursor must stay in the QUERY STRING on a filtered walk too")


def test_last_walk_pages_REPORTS_A_FILTERED_WALK_exactly_as_it_reports_an_unfiltered_one():
    """``last_walk_pages`` is what a caller consults to know a walk ran to exhaustion. Filtering
    must not make that record thinner, or a filtered read could not be shown complete."""
    read, _ = client(page(["r1"], has_more=True, token="tok1"), page(["r2"], has_more=False))
    read.search_records("app", "tbl", filter=search_filter(ONE))
    pages = read.last_walk_pages
    assert len(pages) == 2
    assert [p.has_more for p in pages] == [True, False]


def test_the_VIEW_ID_is_also_re_sent_on_every_page():
    read, recorder = client(page(["r1"], has_more=True, token="tok1"),
                            page(["r2"], has_more=False))
    read.search_records("app", "tbl", view_id="vew1")
    assert [sent_body(recorder, i)["view_id"] for i in (0, 1)] == ["vew1", "vew1"]


# --------------------------------------------------------------------------- #
# The shipped docstring carries AC9's statement, where a consumer reads it     #
# --------------------------------------------------------------------------- #

def test_the_SHIPPED_DOCSTRING_states_the_pagination_interplay_and_the_R12_bar():
    doc = " ".join(BaseReadClient.search_records.__doc__.split())
    for needle in ("every page", "page_token", "last_walk_pages"):
        assert needle in doc, f"the docstring does not state {needle!r} for a filtered walk"
    assert "R12" in doc or "silently ignores" in doc, (
        "the widened read must carry R12 forward: a code:0 is not proof a parameter landed")


def test_the_CAPTURE_THIS_TRANSPORT_RESTS_ON_is_still_on_disk_and_still_says_so():
    """The evidence the direction was taken on, re-read rather than remembered."""
    steps = json.loads(
        (_CAPTURES / "p1-q3-01-filter-sort.json").read_text(encoding="utf-8"))["steps"]
    notes = {step["_note"].split("::")[0].strip(): step for step in steps}
    assert "n=1" in notes["filter is 'Text 1'"]["_note"]
    assert notes["sort by field_id not name"]["_lark_code"] == 1254016
    assert "n=6" in notes["bogus body key 'zzz' (baseline for silent-ignore)"]["_note"], (
        "the R12 control: an unrecognised key returns the WHOLE table")
