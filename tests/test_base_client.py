"""LD-247 — the Base read client, its op registry, and its typed error taxonomy.

Every test here is offline. The fixtures are the **committed probe captures**
(`tests/captures/base-study/captures/`) round-tripped through the pinned SDK's own deserializer, so an
API drift reddens **at deserialization** rather than silently producing a wrong render — the
`tests/test_sheets_render.py` precedent, and PROJECT.md § Quality bar.

The two traps this story exists to pin, both from the parity pack's § Verdict:

1. **`page_size` is a QUERY-STRING parameter.** In the body it is *silently ignored* and the
   server returns the whole page-1 set — `code:0` either way. So a test that cannot tell the
   two placements apart pins nothing, and every test below that touches paging asserts the
   placement, not just the outcome.
2. **`records/search` silently ignores every body key it does not recognise** (R12). A
   `code:0` and a non-empty body prove *nothing* about whether a parameter was honoured, so
   every parameter the shipped client sends is pinned by a test that proves it **changed the
   result** — or, where an offline fixture cannot express a difference, by an exact wire-shape
   assertion. The bogus-key control ships too.
"""
import inspect
import pathlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from lark_oapi.api.bitable.v1 import (
    GetAppResponse,
    ListAppTableFieldResponse,
    ListAppTableRecordResponse,
    ListAppTableResponse,
    ListAppTableViewResponse,
    SearchAppTableRecordRequestBody,
    SearchAppTableRecordResponse,
)
from lark_oapi.core.json import JSON

from larkdocio import permissions as perm
from larkdocio.base import client as base_client
from larkdocio.base import errors as base_errors
from larkdocio.base import ops as base_ops
from larkdocio.base.client import BaseReadClient
from larkdocio.errors import (
    LarkAPIError,
    LarkConfigError,
    LarkPermissionError,
    LarkRateLimitError,
)
import private_tree  # noqa: E402  (LD-685)

_REPO = Path(__file__).resolve().parent.parent
_CAPTURES = _REPO / "tests" / "captures" / "base-study" / "captures"


# --------------------------------------------------------------------------- #
# Fixtures: the committed captures, through the SDK deserializer.              #
# --------------------------------------------------------------------------- #

def capture(name):
    return json.loads((_CAPTURES / name).read_text(encoding="utf-8"))


def unmarshal(payload, cls):
    return JSON.unmarshal(json.dumps(payload), cls)


def pagination_steps():
    """The six live steps of `p1-q1-01`, keyed by the probe's own note."""
    return {step["_note"]: step for step in capture("p1-q1-01-pagination-anomaly.json")["steps"]}


def search_pages():
    """The real three-page walk of the 6-row Scratch Base at `?page_size=2`."""
    steps = pagination_steps()
    return [
        unmarshal(steps["page_size in the QUERY STRING"]["response"], SearchAppTableRecordResponse),
        unmarshal(steps["walk step 1"]["response"], SearchAppTableRecordResponse),
        unmarshal(steps["walk step 2"]["response"], SearchAppTableRecordResponse),
    ]


class _Leg:
    """A bare attribute holder standing in for one SDK resource namespace."""


class _Recorder:
    """One SDK resource method: records the request it was handed, hands back the next canned
    response (repeating the last one once the script runs out)."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, *args, **kwargs):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("the fake SDK was called with no canned response")
        index = min(len(self.requests) - 1, len(self.responses) - 1)
        return self.responses[index]


class _Forbidden:
    """A leg the shipped client must never call."""

    def __init__(self, why):
        self.why = why

    def __call__(self, *args, **kwargs):
        raise AssertionError(self.why)


def fake_sdk(*, app_get=(), tables=(), views=(), fields=(), search=()):
    sdk = _Leg()
    sdk.bitable = _Leg()
    sdk.bitable.v1 = v1 = _Leg()
    v1.app = _Leg()
    v1.app.get = _Recorder(app_get)
    v1.app_table = _Leg()
    v1.app_table.list = _Recorder(tables)
    v1.app_table_view = _Leg()
    v1.app_table_view.list = _Recorder(views)
    v1.app_table_field = _Leg()
    v1.app_table_field.list = _Recorder(fields)
    v1.app_table_record = _Leg()
    v1.app_table_record.search = _Recorder(search)
    # AC4: the legacy list, the point read and batch_get are the three OTHER encodings. The
    # shipped read path must never touch them, so they are wired to explode.
    v1.app_table_record.list = _Forbidden(
        "the legacy GET …/records list is NOT the pinned read (AC4 / opener R7)")
    v1.app_table_record.get = _Forbidden("the point read is not the pinned read")
    # `batch_get` is NOT the pinned record read and the L1 render path must never reach it —
    # it is the OPT-IN link resolver's endpoint (LD-269), so it stays wired to explode for
    # every test that is not deliberately about resolution.
    v1.app_table_record.batch_get = _Forbidden(
        "batch_get is the opt-in link resolver's read, never the L1 render path's")
    return sdk


class _CountingLimiter:
    """Stands in for the shared `RateLimiter` and counts acquisitions."""

    def __init__(self):
        self.acquisitions = 0

    def acquire(self):
        self.acquisitions += 1


def client(**legs):
    return BaseReadClient("id", "secret", sdk_client=fake_sdk(**legs),
                          rate_limiter=_CountingLimiter())


def page(items, *, has_more=False, token=None, cls=SearchAppTableRecordResponse):
    """A synthetic one-page response in the wire shape the captures pin."""
    data = {"items": list(items), "has_more": has_more, "total": len(items)}
    if token is not None:
        data["page_token"] = token
    return unmarshal({"code": 0, "msg": "success", "data": data}, cls)


def base_source():
    """Every shipped Base READ module's source, concatenated — for the by-construction scans."""
    # The WRITE half has its own mirror scans; a completeness test proves neither escapes both.
    return "\n".join(p.read_text(encoding="utf-8") for p in read_module_paths())


def base_code():
    """The Base READ modules' source with **every string literal and comment removed**.

    The scans below ask *"does any CODE PATH do X"*, and prose that explains why the code
    deliberately does **not** do X would otherwise trip them — a guard that punishes the
    docstring for naming the hazard it avoids teaches the wrong lesson.
    """
    import io
    import tokenize

    out = []
    # The READ half only — the write modules carry their own mirror of every scan below.
    for path in read_module_paths():
        text = path.read_text(encoding="utf-8")
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type not in (tokenize.STRING, tokenize.COMMENT):
                out.append(token.string)
    return "\n".join(out)


#: A realistic Lark scope-denial body: the structured `permission_violations` is what names
#: the missing scope, and the console link is what makes the refusal actionable.
DENIAL_BODY = {
    "code": 99991672,
    "msg": "Access denied. The app does not hold the required permission.",
    "error": {
        "permission_violations": [{"type": "TenantAccessToken",
                                   "subject": "bitable:app:readonly"}],
        "helps": [{"description": "grant it", "url": "https://open.larksuite.com/app/x/auth"}],
    },
}


# --------------------------------------------------------------------------- #
# AC1 — the transport D2 ruled: SDK-typed, raw fallback ONLY on a gap actually  #
#       hit. No gap was hit, so there is no raw path at all.                    #
# --------------------------------------------------------------------------- #

def test_ac1_every_op_is_built_from_a_pinned_SDK_request_class():
    for desc in base_ops.OPS:
        assert desc.request_cls.__module__.startswith("lark_oapi.api.bitable.v1"), desc


def test_ac1_there_is_NO_raw_http_path_because_no_SDK_gap_was_HIT():
    """The ruling's narrowing is the operative part: a raw path with no demonstrated gap is a
    defect, not a style choice. The whole Base package is scanned, not one file."""
    source = base_code()
    for forbidden in ("urllib", "RawHttpClient", "CredentialedRawHttpClient",
                      "fetch_tenant_access_token"):
        assert forbidden not in source, (
            f"{forbidden} is a raw-HTTP construct; D2 permits one only where an SDK gap was "
            "actually hit, recorded in the docstring with the specific shortfall")


def test_ac1_the_module_docstring_records_the_ruling_and_the_fixture_round_trip():
    """The docstring states the transport RULE; the module records WHICH ruling it is.

    Both halves still hold — what moved is where the decision *id* lives. LD-260's Base write
    recipe imports this module, which enrolled its docstring in the consumer corpus, and an
    internal decision reference resolves to nothing for someone holding only the wheel (the
    dialect guard says so, and offers the `#`-comment route this takes). So the rule is in the
    docstring in plain language and the id is in a comment beside it, checked here against the
    module's SOURCE rather than its `help()` output.
    """
    doc = base_client.__doc__
    source = pathlib.Path(inspect.getfile(base_client)).read_text(encoding="utf-8")
    assert "D2" in source and "D2" not in doc, (
        "the ruling reference belongs in the module, and not in the text a consumer reads")
    assert "deserial" in doc.lower(), "the docstring must say how a capture becomes a fixture"
    assert "raw" in doc.lower(), "the docstring must state the raw-fallback rule it is under"


def test_ac1_a_capture_round_trips_into_TYPED_objects_so_a_drift_reddens_at_deserialization():
    response = unmarshal(capture("00-app-meta.json")["response"], GetAppResponse)
    assert response.success() and response.data.app.name == "Larkdocio Scratch Base"
    assert response.data.app.is_advanced is False
    # A renamed key does not silently become a plausible value — it becomes absent.
    drifted = deepcopy(capture("p1-q0-02-tables.json")["response"])
    drifted["data"]["records"] = drifted["data"].pop("items")
    assert unmarshal(drifted, ListAppTableResponse).data.items is None


# --------------------------------------------------------------------------- #
# AC2 — the op registry carries an EXPLICIT `mutates`, never the HTTP verb.     #
# --------------------------------------------------------------------------- #

def test_ac2_mutates_has_NO_DEFAULT_so_a_descriptor_cannot_omit_it():
    field = base_ops.BaseOpDescriptor.__dataclass_fields__["mutates"]
    import dataclasses

    assert field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING


def test_ac2_every_op_this_story_ships_declares_mutates_FALSE():
    assert base_ops.OPS, "the registry is empty"
    assert all(desc.mutates is False for desc in base_ops.OPS)
    assert base_ops.read_only() is True


def test_ac2_the_flag_is_NOT_derivable_from_the_verb_and_the_registry_proves_it():
    """`records/search` is a **POST read**. A registry that derived `mutates` from the verb
    would call it a write, so the two facts are asserted together."""
    verbs = {desc.http_method for desc in base_ops.OPS}
    assert verbs == {"GET", "POST"}, verbs
    post_reads = [d for d in base_ops.OPS if d.http_method == "POST"]
    assert post_reads and all(d.mutates is False for d in post_reads)


def test_ac2_the_declared_verb_and_endpoint_MATCH_the_sdk_request_class():
    """Both are cross-checked against the SDK rather than trusted, so a descriptor cannot drift
    away from the request it actually builds."""
    for desc in base_ops.OPS:
        built = desc.request_cls.builder().build()
        assert built.uri == desc.endpoint, desc
        assert built.http_method.name == desc.http_method, desc


def test_ac2_every_descriptor_names_a_real_client_method():
    for desc in base_ops.OPS:
        assert callable(base_ops.impl_of(desc)), desc


def test_ac2_the_registry_covers_exactly_the_read_families_L1_NEEDS_plus_get_view():
    """L1's five, plus the one LD-264 added. ``get_view`` is not an L1 rendering read — the
    reader renders a TABLE's schema, not a view's — it is the read that VERIFIES a view write,
    and it exists because `GET …/views` provably does not carry a view's ``property`` while
    `GET …/views/{id}` does."""
    assert {desc.name for desc in base_ops.OPS} == {
        "get_app", "list_tables", "list_views", "get_view", "list_fields", "search_records",
        # LD-269 — the SECOND POST read, and the one opt-in link resolution spends on.
        "batch_get_records"}


# --------------------------------------------------------------------------- #
# AC3 — pagination to exhaustion, and the `page_size` placement pin.            #
# --------------------------------------------------------------------------- #

def test_ac3_page_size_lands_in_the_QUERY_and_the_test_can_tell_the_placements_apart():
    """The pin, and the counter-model in the same test: the request the client sends carries
    `page_size` in `queries` and its typed body has no such key at all. A test that asserted
    only "the client sets a page size" would pass for the broken placement too."""
    c = client(search=[page([])])
    c.search_records("app", "tbl")
    request = c._sdk.bitable.v1.app_table_record.search.requests[0]
    assert ("page_size", str(base_client.DEFAULT_PAGE_SIZE)) in request.queries
    body = json.loads(JSON.marshal(request.request_body))
    assert "page_size" not in body, (
        "page_size in the BODY is silently ignored and the whole page-1 set comes back")


def test_ac3_the_captured_evidence_DISTINGUISHES_the_two_placements():
    """`p1-q1-01`, live: the same call, the same `code:0`, two different answers."""
    steps = pagination_steps()
    query = steps["page_size in the QUERY STRING"]["response"]["data"]
    body = steps["page_size in the BODY — the seat's anomaly reproduced?"]["response"]["data"]
    assert query["code" if False else "has_more"] is True and len(query["items"]) == 2
    assert body["has_more"] is False and len(body["items"]) == 6
    assert "page_token" in query and "page_token" not in body


def test_ac3_a_two_page_fixture_returns_ALL_rows_IN_ORDER():
    pages = search_pages()
    c = client(search=pages)
    records = c.search_records("app", "tbl")
    expected = [record.record_id for p in pages for record in p.data.items]
    assert [r.record_id for r in records] == expected
    assert len(records) == 6 == pages[0].data.total


def test_ac3_the_page_token_pair_is_FOLLOWED():
    pages = search_pages()
    c = client(search=pages)
    c.search_records("app", "tbl")
    requests = c._sdk.bitable.v1.app_table_record.search.requests
    assert len(requests) == 3
    assert not [q for q in requests[0].queries if q[0] == "page_token"], (
        "the first page asks for no cursor")
    for previous, request in zip(pages, requests[1:]):
        assert ("page_token", previous.data.page_token) in request.queries


def test_ac3_THE_TEN_PHANTOM_ROWS_TRAP_is_a_named_regression():
    """**The ten-phantom-rows trap.** A freshly created Base's default table ships with **10
    auto-provisioned empty rows** and 4 default fields. So the first page of a `page_size=10`
    read of a *populated* table can be nothing but those empties — which reads as "this table
    has no data" while the data sits on page two. **The opener's own probe 05 was fooled by
    exactly this before probe 06 corrected it.**

    "The first page" is never "the table": the client must page to exhaustion, and this test
    fails for any implementation that returns page one.
    """
    phantoms = [{"record_id": f"recPHANTOM{i}", "fields": {}} for i in range(10)]
    real = [{"record_id": "recREAL1", "fields": {"Text": [{"text": "THE ROW", "type": "text"}]}}]
    c = client(search=[page(phantoms, has_more=True, token="cursor-to-the-real-rows"),
                       page(real)])
    records = c.search_records("app", "tbl")
    assert len(records) == 11
    assert any(r.fields for r in records), (
        "a first-page-only read returns 10 empty rows and silently asserts an empty table")
    assert [r.record_id for r in records][-1] == "recREAL1"


def test_ac3_the_walk_STOPS_on_a_repeated_token():
    c = client(search=[page([{"record_id": "a", "fields": {}}], has_more=True, token="same"),
                       page([{"record_id": "b", "fields": {}}], has_more=True, token="same")])
    assert len(c.search_records("app", "tbl")) == 2


def test_ac3_the_walk_STOPS_on_has_more_with_no_usable_cursor():
    c = client(search=[page([{"record_id": "a", "fields": {}}], has_more=True)])
    assert len(c.search_records("app", "tbl")) == 1


def test_ac3_the_walk_CANNOT_SPIN_FOREVER():
    endless = [page([{"record_id": str(i), "fields": {}}], has_more=True, token=f"t{i}")
               for i in range(base_client.MAX_PAGES + 5)]
    c = client(search=endless)
    assert len(c.search_records("app", "tbl")) == base_client.MAX_PAGES


@pytest.mark.parametrize("op,leg,cls,args", [
    ("list_tables", "app_table", ListAppTableResponse, ("app",)),
    ("list_views", "app_table_view", ListAppTableViewResponse, ("app", "tbl")),
    ("list_fields", "app_table_field", ListAppTableFieldResponse, ("app", "tbl")),
])
def test_ac3_EVERY_list_read_pages_to_exhaustion_not_just_records(op, leg, cls, args):
    first = page([{"table_id": "t1"}], has_more=True, token="next", cls=cls)
    second = page([{"table_id": "t2"}], cls=cls)
    c = client(**{{"app_table": "tables", "app_table_view": "views",
                   "app_table_field": "fields"}[leg]: [first, second]})
    assert len(getattr(c, op)(*args)) == 2
    requests = getattr(getattr(c._sdk.bitable.v1, leg), "list").requests
    assert ("page_token", "next") in requests[1].queries


# --------------------------------------------------------------------------- #
# AC4 — `records/search` IS the read, and the pin is test-asserted.             #
# --------------------------------------------------------------------------- #

def test_ac4_the_record_read_calls_SEARCH_and_the_other_three_routes_EXPLODE():
    c = client(search=[page([])])
    c.search_records("app", "tbl")
    request = c._sdk.bitable.v1.app_table_record.search.requests[0]
    assert request.uri.endswith("/records/search")
    assert "records/search" in base_ops.op("search_records").endpoint


def test_ac4_the_legacy_GET_and_SEARCH_really_do_DISAGREE():
    """Pinning a fixture to the wrong encoding is the failure this guard exists for, so the
    disagreement is asserted off the two live captures rather than described."""
    legacy = unmarshal(capture("06-04-records-list-GET-populated.json")["response"],
                       ListAppTableRecordResponse)
    searched = unmarshal(pagination_steps()["page_size in the QUERY STRING"]["response"],
                         SearchAppTableRecordResponse)
    legacy_raw = capture("06-04-records-list-GET-populated.json")["response"]["data"]["items"][0]
    search_raw = pagination_steps()[
        "page_size in the QUERY STRING"]["response"]["data"]["items"][0]
    assert "id" in legacy_raw and "id" not in search_raw, (
        "the legacy GET duplicates the id as both `id` and `record_id`; search carries only "
        "`record_id` (opener R7)")
    assert legacy.data.items and searched.data.items


def test_ac4_automatic_fields_is_PINNED_FALSE_in_the_typed_body():
    c = client(search=[page([])])
    c.search_records("app", "tbl")
    body = json.loads(JSON.marshal(
        c._sdk.bitable.v1.app_table_record.search.requests[0].request_body))
    assert body["automatic_fields"] is False


def test_ac4_text_field_as_array_is_NOT_SENT():
    """It has no observable effect on `search` (which is always array-shaped) — the flag
    belongs to the legacy GET. So it is absent from the wire, not set to a default."""
    c = client(search=[page([])])
    c.search_records("app", "tbl")
    request = c._sdk.bitable.v1.app_table_record.search.requests[0]
    body = json.loads(JSON.marshal(request.request_body))
    assert "text_field_as_array" not in body
    assert not [q for q in request.queries if q[0] == "text_field_as_array"]


def test_ac4_field_names_is_NOT_exposed_and_the_docstring_SAYS_SO():
    """AC4's conditional: expose it and pin the name-keying, or do not expose it and say so.
    L1 does not expose it — the projection buys nothing a full read does not already give,
    and every unexposed parameter is one fewer silent-ignore surface (R12)."""
    signature = inspect.signature(BaseReadClient.search_records)
    assert "field_names" not in signature.parameters
    assert "field_names" in base_client.__doc__
    # …and the refusal a caller WOULD hit is still in the taxonomy, so it is legible.
    assert 1254045 in base_errors.BASE_ERROR_CODES


# --------------------------------------------------------------------------- #
# AC5 — R12: every parameter is pinned by a test that proves it CHANGED the     #
#       result (or, where a fixture cannot, by an exact wire-shape assertion).   #
# --------------------------------------------------------------------------- #

def test_ac5_a_BY_CONSTRUCTION_the_body_is_a_typed_builder_never_a_hand_dict():
    c = client(search=[page([])])
    c.search_records("app", "tbl")
    body = c._sdk.bitable.v1.app_table_record.search.requests[0].request_body
    assert isinstance(body, SearchAppTableRecordRequestBody)
    source = base_code()
    assert "json.dumps" not in source and "request_body({" not in source


def test_ac5_b_page_size_CHANGED_THE_RESULT_and_the_placement_is_why():
    steps = pagination_steps()
    with_it = steps["page_size in the QUERY STRING"]["response"]["data"]
    without_it = steps["page_size in the BODY — the seat's anomaly reproduced?"][
        "response"]["data"]
    assert len(with_it["items"]) != len(without_it["items"])
    assert len(steps["min page size?"]["response"]["data"]["items"]) == 1, "no minimum page size"


def test_ac5_b_page_token_CHANGED_THE_RESULT():
    pages = search_pages()
    first = {r.record_id for r in pages[0].data.items}
    later = {r.record_id for p in pages[1:] for r in p.data.items}
    assert first and later and not (first & later), (
        "following the cursor returns rows the first page did not")


def test_ac5_b_automatic_fields_CHANGED_THE_RESULT_which_is_why_it_is_pinned_false():
    """From `06-03`, live: with `automatic_fields` the record grows four record-level keys —
    two of them **person objects** (D1: PII) — while `fields` is byte-identical. That is the
    whole reason the default is `false`, and it is a measured difference, not a belief."""
    modes = capture("06-03-value-read-option-matrix.json")["response"]["data"]["modes"]
    plain = modes["plain"]["populated_record"]
    enriched = modes["automatic_fields"]["populated_record"]
    added = set(enriched) - set(plain)
    assert added == {"created_by", "last_modified_by", "created_time", "last_modified_time"}
    assert plain["fields"] == enriched["fields"], "it changes nothing in `fields`"


def test_ac5_b_the_EXACT_wire_shape_of_every_parameter_is_pinned():
    """The complete inventory, both placements, so a parameter cannot be added without a test
    noticing. Three are sent and nothing else is."""
    c = client(search=search_pages())
    c.search_records("app", "tbl")
    requests = c._sdk.bitable.v1.app_table_record.search.requests
    assert [q[0] for q in requests[0].queries] == ["page_size"]
    assert sorted(q[0] for q in requests[1].queries) == ["page_size", "page_token"]
    body = json.loads(JSON.marshal(requests[0].request_body))
    assert body == {"automatic_fields": False}


def test_ac5_b_user_id_type_is_NOT_SENT_because_no_test_could_prove_it_changed_anything():
    """L1 renders person fields **name-only** (D1), so the id form is unobservable in the
    output — and R12 says an unprovable parameter does not ship."""
    c = client(search=[page([])])
    c.search_records("app", "tbl")
    request = c._sdk.bitable.v1.app_table_record.search.requests[0]
    assert not [q for q in request.queries if q[0] == "user_id_type"]
    assert "user_id_type" not in json.loads(JSON.marshal(request.request_body))


def test_ac5_c_THE_BOGUS_KEY_CONTROL_ships_as_a_test():
    """`p1-q3-01`, live: the bogus key `{"zzz": 1}` and four plausible grouping keys all
    behave **identically to `{}`**. The day the server stops ignoring unknown keys, this
    recorded control is what the next probe is compared against."""
    steps = capture("p1-q3-01-filter-sort.json")["steps"]
    notes = {step["_note"].split(" :: ")[0]: step["_note"] for step in steps}
    baseline = notes["no filter / no sort"].split(" :: ", 1)[1]
    baseline_shape = baseline.split(" body=")[0]
    for control in ("bogus body key 'zzz' (baseline for silent-ignore)",
                    "body key 'group_by' (ignored-key control)",
                    "body key 'grouping' (ignored-key control)",
                    "body key 'group_info' (ignored-key control)",
                    "body key 'groups' (ignored-key control)"):
        observed = notes[control].split(" :: ", 1)[1].split(" body=")[0]
        assert observed == baseline_shape, (control, observed, baseline_shape)


def test_ac5_c_the_TYPED_BODY_has_no_way_to_carry_an_unknown_key():
    """The construction half of the control: the SDK body's builder surface is a fixed set, so
    a misplaced key cannot even be expressed. Pinned, so a new SDK key arrives loudly."""
    builder = SearchAppTableRecordRequestBody.builder()
    settable = {n for n in dir(builder) if not n.startswith("_") and n != "build"}
    assert settable == {"view_id", "field_names", "sort", "filter", "automatic_fields"}
    assert "page_size" not in settable and "group_by" not in settable


# --------------------------------------------------------------------------- #
# AC6 — be gentle: throttled by construction, limits documented not hunted.     #
# --------------------------------------------------------------------------- #

def test_ac6_the_throttle_is_applied_ON_THE_SHIPPED_READ_PATH_of_every_op():
    c = client(app_get=[unmarshal(capture("00-app-meta.json")["response"], GetAppResponse)],
               tables=[page([{"table_id": "t"}], cls=ListAppTableResponse)],
               views=[page([{"view_id": "v"}], cls=ListAppTableViewResponse)],
               fields=[page([{"field_id": "f"}], cls=ListAppTableFieldResponse)],
               search=search_pages())
    c.get_app("app")
    c.list_tables("app")
    c.list_views("app", "tbl")
    c.list_fields("app", "tbl")
    c.search_records("app", "tbl")
    assert c.api_calls == 7  # 1 + 1 + 1 + 1 + 3 pages
    assert c.limiter.acquisitions == c.api_calls, (
        "every call passes the limiter; a leg that bypassed it would show here")


def test_ac6_the_default_pace_is_the_ONE_the_probe_packs_evidenced():
    """483 live calls across three packs at ≥1.2 s spacing, no limit hit. The default is that
    spacing, expressed as a rolling window — not a number read off a doc page and not a limit
    anybody walked into."""
    assert base_client.BASE_RATE_WINDOW_SECONDS == 60.0
    assert base_client.DEFAULT_MAX_READS_PER_WINDOW == 50
    spacing = base_client.BASE_RATE_WINDOW_SECONDS / base_client.DEFAULT_MAX_READS_PER_WINDOW
    assert spacing >= 1.2


def test_ac6_a_real_client_gets_a_real_limiter_not_none():
    c = BaseReadClient("id", "secret", sdk_client=fake_sdk())
    from larkdocio.common.transport import RateLimiter

    assert isinstance(c.limiter, RateLimiter)


def test_ac6_nothing_here_PROBES_a_rate_limit():
    source = base_code()
    assert "99991400" not in source, (
        "rate limits are documented from the packs' evidence, deliberately never probed "
        "(opener R9); a retry-on-rate-limit loop here would be a probe by another name")


# --------------------------------------------------------------------------- #
# AC7 — the typed error taxonomy, from the captured vocabulary.                 #
# --------------------------------------------------------------------------- #

#: Every code AC7 names, including the nine the parity pack added.
_AC7_CODES = (
    1002, 91402, 1254004, 1254041, 1254043, 1254301, 99992402, 1061003, 1254023, 1254034,
    1254069, 1255002, 1770001, 1770029,
    1254016, 1254018, 1254045, 1254050, 1254060, 1254302, 1069307, 800074800, 1254036,
)


@pytest.mark.parametrize("code", _AC7_CODES)
def test_ac7_every_captured_code_maps_to_a_typed_entry_with_an_actionable_message(code):
    note = base_errors.BASE_ERROR_CODES[code]
    assert note.label, code
    assert len(note.meaning) > 40, (code, note.meaning)
    assert note.evidence, code


@private_tree.citations
def test_ac7_every_evidence_pointer_RESOLVES_to_a_file_that_exists():
    missing = []
    for code, note in base_errors.BASE_ERROR_CODES.items():
        for token in note.evidence.split():
            token = token.strip("`,;()").split("§")[0].rstrip()
            if token.startswith("dev/") and not (_REPO / token).exists():
                missing.append((code, token))
    assert not missing, missing


def test_ac7_a_nonzero_response_raises_the_typed_error_carrying_lark_code_and_msg():
    with pytest.raises(LarkAPIError) as exc:
        base_errors.raise_for_base_code(
            {"code": 1254041, "msg": "TableIdNotFound"}, context="list fields on tbl")
    assert exc.value.code == 1254041 and exc.value.msg == "TableIdNotFound"
    assert "list fields on tbl" in str(exc.value)
    assert base_errors.BASE_ERROR_CODES[1254041].meaning in str(exc.value)


def test_ac7_a_code_the_taxonomy_does_not_know_still_raises_TYPED_not_bare():
    with pytest.raises(LarkAPIError) as exc:
        base_errors.raise_for_base_code({"code": 424242, "msg": "who knows"}, context="read")
    assert exc.value.code == 424242


def test_ac7_a_zero_code_is_returned_UNTOUCHED():
    response = unmarshal(capture("00-app-meta.json")["response"], GetAppResponse)
    assert base_errors.raise_for_base_code(response, context="read app") is response


def test_ac7_1254301_is_a_FEATURE_GATE_and_the_message_does_NOT_advise_a_scope():
    """`app.is_advanced: false`. Enabling advanced permissions is a **Base-owner action in the
    product**, not a console grant — and the API cannot do it either (`1254302`). A message
    that sent the reader to the scope console would send them somewhere that cannot help."""
    with pytest.raises(LarkAPIError) as exc:
        base_errors.raise_for_base_code(
            {"code": 1254301, "msg": "OperationTypeError"}, context="list roles")
    message = str(exc.value)
    assert not isinstance(exc.value, LarkPermissionError), (
        "a feature gate is not a scope denial")
    for scope_advice in ("grant", "console", "administrator", "request the scope",
                         "add the permission"):
        assert scope_advice not in message.lower(), (scope_advice, message)
    assert "is_advanced" in message and "owner" in message.lower()


def test_ac7_1254302_says_the_API_CANNOT_ENABLE_advanced_permissions():
    assert "cannot" in base_errors.BASE_ERROR_CODES[1254302].meaning.lower()


def test_ac7_99992402_FIELD_VIOLATIONS_reach_the_caller_verbatim():
    """The P0 addendum recorded `99992402` as opaque — *"error: null, no field_violations, no
    hint"*. It is not: every one of the parity pack's 33 refusals carried
    `error.field_violations` naming the offending field, its value **and the complete accepted
    enum**. The typed error surfaces them rather than discarding them."""
    body = None
    for step in capture("p1-q2-01-button-sweep.json")["steps"]:
        if step.get("response", {}).get("code") == 99992402:
            body = step["response"]
            break
    assert body is not None, "the capture no longer carries a 99992402 body"

    violations = base_errors.field_violations(body)
    assert [v["field"] for v in violations] == ["type", "ui_type"]
    assert "Button" in violations[1]["value"]
    assert "options: [Text,Barcode" in violations[1]["description"]

    with pytest.raises(LarkAPIError) as exc:
        base_errors.raise_for_base_code(body, context="create a field")
    assert exc.value.field_violations == violations
    assert "ui_type" in str(exc.value) and "options: [Text,Barcode" in str(exc.value)


def test_ac7_field_violations_on_a_body_that_has_none_is_EMPTY_not_an_error():
    assert base_errors.field_violations({"code": 1002, "msg": "note has been deleted"}) == ()
    assert base_errors.field_violations(None) == ()


def test_ac7_the_rate_limit_code_still_routes_to_the_shared_typed_error():
    with pytest.raises(LarkRateLimitError):
        base_errors.raise_for_base_code({"code": 99991400, "msg": "too many"}, context="read")


def test_ac7_a_real_scope_denial_still_routes_to_LarkPermissionError():
    """The uniform refusal is not bypassed: the Base client raises through the same
    `api_error` seam every other surface does."""
    with pytest.raises(LarkPermissionError) as exc:
        base_errors.raise_for_base_code(DENIAL_BODY, context="read app")
    assert exc.value.denial.scopes == ("bitable:app:readonly",)
    assert exc.value.denial.console_url


def test_ac7_the_client_raises_the_taxonomy_on_a_failed_call():
    failed = unmarshal({"code": 1254041, "msg": "TableIdNotFound"}, ListAppTableFieldResponse)
    c = client(fields=[failed])
    with pytest.raises(LarkAPIError) as exc:
        c.list_fields("app", "tbl")
    assert exc.value.code == 1254041


# --------------------------------------------------------------------------- #
# AC8 — READ credentials only.                                                  #
# --------------------------------------------------------------------------- #

def test_ac8_the_read_path_resolves_READ_and_never_consults_WRITE(monkeypatch):
    monkeypatch.setenv("LARK_READ_APP_ID", "read-app")
    monkeypatch.setenv("LARK_READ_APP_SECRET", "read-secret")
    monkeypatch.setenv("LARK_WRITE_APP_ID", "write-app")
    monkeypatch.setenv("LARK_WRITE_APP_SECRET", "write-secret")

    from larkdocio.common import auth

    def explode(*args, **kwargs):
        raise AssertionError("the Base read path consulted the WRITE credential pair")

    monkeypatch.setattr(auth, "get_write_credentials", explode)
    monkeypatch.setattr(base_client, "get_read_credentials", lambda: ("read-app", "read-secret"))

    captured = {}

    class _Probe(BaseReadClient):
        def __init__(self, app_id, app_secret, domain="larksuite.com", **kwargs):
            captured["pair"] = (app_id, app_secret)
            super().__init__(app_id, app_secret, domain, sdk_client=fake_sdk(), **kwargs)

    _Probe.from_read_credentials()
    assert captured["pair"] == ("read-app", "read-secret")


def test_ac8_no_base_READ_module_NAMES_a_write_credential():
    source = base_code()
    assert "LARK_WRITE_APP" not in source
    assert "get_write_credentials" not in source


def test_ac8_missing_read_credentials_is_a_typed_config_error(monkeypatch):
    monkeypatch.setattr(base_client, "get_read_credentials", lambda: ("", ""))
    with pytest.raises(LarkConfigError):
        BaseReadClient.from_read_credentials()
    with pytest.raises(LarkConfigError):
        BaseReadClient("", "")


def test_ac8_the_credential_env_named_on_a_denial_is_the_READ_pair():
    from larkdocio.common.auth import resolved_read_env

    with pytest.raises(LarkPermissionError) as exc:
        base_errors.raise_for_base_code(DENIAL_BODY, context="read app",
                                        credential_env=resolved_read_env())
    assert exc.value.denial.credential_env == tuple(resolved_read_env())
    assert not any("WRITE" in name for name in exc.value.denial.credential_env)


def test_ac8_the_docstring_refuses_to_cite_a_same_tenant_probe_as_scope_separation():
    """PROJECT.md § Credential aliasing: on this tenant the two pairs are the same app with
    byte-identical secrets, so an isolation test passing here proves nothing about scopes. The
    module says so rather than letting a reader over-read the test above."""
    assert "alias" in base_client.__doc__.lower()


# --------------------------------------------------------------------------- #
# AC9 — the permission rows land in THIS change.                                #
# --------------------------------------------------------------------------- #

def test_ac9_the_endpoints_are_DERIVED_from_the_client_code_not_hand_listed():
    derived = set()
    for desc in base_ops.OPS:
        derived |= set(perm.endpoints_of(base_ops.impl_of(desc)))
    assert derived == {
        "/open-apis/bitable/v1/apps/:app_token",
        "/open-apis/bitable/v1/apps/:app_token/tables",
        "/open-apis/bitable/v1/apps/:app_token/tables/:table_id/views",
        # LD-264 — the single-view read the view write's read-back spends.
        "/open-apis/bitable/v1/apps/:app_token/tables/:table_id/views/:view_id",
        "/open-apis/bitable/v1/apps/:app_token/tables/:table_id/fields",
        "/open-apis/bitable/v1/apps/:app_token/tables/:table_id/records/search",
        # LD-269 — the batched named-record read link resolution follows a link with.
        "/open-apis/bitable/v1/apps/:app_token/tables/:table_id/records/batch_get",
    }, sorted(derived)


def test_ac9_every_endpoint_this_client_reaches_HAS_A_ROW_in_the_scope_table():
    """The mechanical half of AC9, available before the surface itself registers in
    `capabilities()` (that is LD-251). An endpoint the table does not know would project an
    empty requirement in silence; this makes it a failure instead."""
    unmapped = []
    for desc in base_ops.OPS:
        for endpoint in perm.endpoints_of(base_ops.impl_of(desc)):
            if perm._table_row(endpoint, "read") is None:
                unmapped.append((desc.name, endpoint))
    assert not unmapped, unmapped


def test_ac9_each_bitable_row_carries_its_evidence_and_a_verification_label():
    rows = [row for row in perm.ENDPOINT_SCOPES if row[0].startswith("/open-apis/bitable/")]
    assert rows, "the bitable families have no row in the endpoint→scope table"
    for prefix, mode, scopes, reason in rows:
        # Widened when the record-WRITE families earned their own row. Both modes are held to
        # the same standard here; that the READ families still resolve to the read row is
        # asserted where it belongs, on the read side, below.
        assert mode in ("read", "write"), (prefix, mode)
        assert scopes, (prefix, "the calls were evidenced effective under a real grant")
        for scope in scopes:
            assert scope.verification in perm.VERIFICATION_LABELS
            assert len(scope.evidence) > 40, (prefix, scope.evidence)
            assert scope.note


def test_ac9_the_derived_scope_for_every_op_is_NON_EMPTY_and_read_mode():
    for desc in base_ops.OPS:
        endpoints = perm.endpoints_of(base_ops.impl_of(desc))
        scopes = perm.scopes_for_endpoints(endpoints, "read")
        assert scopes, desc.name
        assert all(s.established for s in scopes), desc.name


def test_ac9_NO_scope_is_widened_and_no_drive_metas_bridge_is_called():
    """The Drive metadata bridge gets a row only if this story actually calls it. It does
    not — the Base app-meta read already carries the name — so no row and no scope."""
    reached = {e for desc in base_ops.OPS for e in perm.endpoints_of(base_ops.impl_of(desc))}
    assert not any("metas/batch_query" in e for e in reached)
    assert not any("drive" in e for e in reached)


def test_ac9_the_base_package_AUTHORS_no_scope_string():
    source = base_source()
    import re as _re

    assert not _re.findall(r"\b(?:bitable|drive|docx|sheets|contact):[a-z_.:]+", source), (
        "a scope requirement is authored in larkdocio.permissions and nowhere else")


# --------------------------------------------------------------------------- #
# AC10 — the offline ring is the whole client over the captures.                #
# --------------------------------------------------------------------------- #

def test_ac10_the_WHOLE_client_runs_over_the_committed_captures():
    """`00-*` / `01-*` / `p1-q0-*` / `p1-q1-01`, through an injected transport — the sheets
    `captures/` → fixtures pattern."""
    recon = capture("p1-q0-03-per-table.json")
    c = client(
        app_get=[unmarshal(capture("00-app-meta.json")["response"], GetAppResponse)],
        tables=[unmarshal(capture("p1-q0-02-tables.json")["response"], ListAppTableResponse)],
        views=[unmarshal(capture("01-views.json")["response"], ListAppTableViewResponse)],
        fields=[unmarshal(capture("01-fields.json")["response"], ListAppTableFieldResponse)],
        search=search_pages(),
    )
    app = c.get_app("BaseScratchExample…")
    assert app.name == "Larkdocio Scratch Base" and app.time_zone == "Asia/Singapore"
    tables = c.list_tables("BaseScratchExample…")
    assert [t.name for t in tables] == ["Table", "Table 2"]
    assert c.list_views("BaseScratchExample…", tables[0].table_id)
    assert c.list_fields("BaseScratchExample…", tables[0].table_id)
    records = c.search_records("BaseScratchExample…", tables[0].table_id)
    assert len(records) == 6
    assert recon["app_token"].startswith("BaseScratchExample")


def test_ac10_the_records_feed_the_LD_246_registry_unchanged():
    """The join this story exists for: `search` records are exactly what `render_row` eats."""
    from larkdocio.base import cells

    per_table = capture("p1-q0-03-per-table.json")["per_table"][0]
    fields = unmarshal(per_table["fields"]["response"], ListAppTableFieldResponse)
    c = client(search=search_pages())
    records = c.search_records("app", "tbl")
    specs = [cells.FieldSpec.from_payload(json.loads(JSON.marshal(f)))
             for f in fields.data.items]
    rendered = cells.render_row(json.loads(JSON.marshal(records[0]))["fields"], specs)
    assert len(rendered) == len(specs)


def test_ac10_the_client_makes_ZERO_write_calls():
    """Read-only end to end: no descriptor mutates, and no SDK leg outside the five read
    methods is reachable from the shipped code."""
    source = base_code()
    for verb in (".create(", ".update(", ".patch(", ".delete(", ".batch_create(",
                 ".batch_update(", ".batch_delete(", ".copy("):
        assert verb not in source, verb


# --------------------------------------------------------------------------- #
# AC11 — BASE.md's client/operations rows are guarded in `test_base_md_matrix`.  #
#        (kept there so BASE.md has exactly one guard file)                     #
# --------------------------------------------------------------------------- #

def test_ac11_the_operations_guard_lives_with_the_rest_of_the_BASE_md_guard():
    guard = (_REPO / "tests" / "test_base_md_matrix.py").read_text(encoding="utf-8")
    assert "mutates" in guard


# --------------------------------------------------------------------------- #
# The read/write scan split (LD-255). Defined at the END of the file ON PURPOSE: #
# the read-only assertion at line 247 above is one of three the write story is   #
# forbidden to touch, and a helper inserted above it would move it.              #
# --------------------------------------------------------------------------- #

#: The Base package's WRITE modules. `base_source()` / `base_code()` scan everything else, so
#: every by-construction check in this file keeps meaning what it meant when it was written:
#: *the READ half does not do this*. The write half's mirror scans live beside its own client,
#: and `tests/test_base_write_client.py` asserts the two lists together cover the package —
#: so a module cannot slip into neither and go unscanned by both.
WRITE_MODULE_NAMES = ("media.py", "write_client.py", "write_ops.py",
                      "write_vocabulary.py")

#: The Base package's SCHEMA modules (LD-263) — the **third** half of the same split, and
#: excluded here for the same reason the write modules are: they resolve the WRITE credential
#: pair by design, so scanning them for "the READ half does not do this" would assert the
#: opposite of what they are. Their own by-construction scans live in
#: `tests/test_base_schema_client.py`, and the three lists are held jointly exhaustive over the
#: package by `tests/test_base_write_client.py`.
SCHEMA_MODULE_NAMES = (
    "schema_apply.py", "schema_client.py", "schema_ops.py", "schema_ops_app_table.py",
    "schema_plan.py", "schema_settle.py",
)

#: Every module the read-half scans deliberately skip.
NON_READ_MODULE_NAMES = WRITE_MODULE_NAMES + SCHEMA_MODULE_NAMES


def read_module_paths():
    """Every shipped Base READ module, sorted."""
    package = _REPO / "src" / "larkdocio" / "base"
    return [p for p in sorted(package.rglob("*.py"))
            if p.name not in NON_READ_MODULE_NAMES]
