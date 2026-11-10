"""LD-229 — the OFFLINE half of name → ``open_id``: every AC that can be proved with no network.

**What the fixtures are, and where each one came from.** This module deliberately does not
hand-mock a payload shape. Two of the three sources are **wire captures committed in this
repository**, and the third is honestly labelled as not being one:

* ``R8`` — ``tests/captures/name-lookup-spike/reprobe/captures/R8-search-owner-exact-READ-POSTRELEASE-GO.json``,
  the 2026-07-30 ``code: 0`` body (HTTP 200, log id ``202607301342288BD90E89D33C26972A45``).
  It answers the field question the SDK could not: with ``employee_id_type=open_id`` the
  ``ou_`` id arrives at ``data.employees[].base_info.employee_id`` and ``user_id`` is **absent
  from the body entirely**;
* ``R1`` — ``…/captures/R1-search-owner-exact-READ.json``, the verbatim ``99991672`` denial
  body from the same endpoint, with ``permission_violations[0].subject`` and a ``helps[].url``;
* ``S1`` — ``tests/captures/name-lookup-spike/slice2/captures/S1-search-owner-abnormals-READ.json``,
  **the ``abnormals`` body, and it is WIRE-OBSERVED.** The issue expected this fixture to be
  SDK-shape-derived, because the GO run returned no ``abnormals`` key at all; the live arm run
  under this issue produced a real one by deliberately requesting ``required_fields`` beyond the
  granted set, so the upgrade the AC provided for has happened. It is the exact shape the AC
  warned about: ``code: 0`` with a populated ``employees[]`` **and** an ``abnormals[]`` naming
  that same row (``row_error: 0``, ``field_errors`` = two field groups refused ``2003``) — a
  partial answer wearing the costume of a complete one;
* the remaining ``abnormals`` combinations — an abnormal id **other** than the resolved one, a
  row with no id at all — are still **SDK-SHAPE-DERIVED, NOT WIRE-OBSERVED**, because the wire
  did not produce them. They are built from the pinned ``lark-oapi==1.5.3`` types
  (``SearchEmployeeResponseBody{employees, page_response, abnormals}`` and
  ``AbnormalRecord{id, row_error, field_errors}``) and every test that uses one says so.
"""
import json
import pathlib

import pytest

from larkdocio.common.transport import RateLimiter
from larkdocio.contacts import (
    CONTACTS_MIN_REQUEST_SPACING_SECONDS,
    CONTACTS_RATE_WINDOW_SECONDS,
    CONTAIN_RESIGNED_EMPLOYEE,
    DEFAULT_MAX_SEARCHES_PER_WINDOW,
    ContactsSearchClient,
    NameLookup,
    Partiality,
    UserRef,
    resolve_user,
)
from larkdocio.errors import LarkAPIError, LarkPermissionError
from larkdocio.write.model.refusal import RefusalReason

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CAPTURES = REPO_ROOT / "tests" / "captures" / "name-lookup-spike" / "reprobe" / "captures"

#: The account owner, from the GO capture. An ``open_id`` is not PII the way a name is, and the
#: display name is never hard-coded here — the live arm recovers it through the shipped
#: reverse-direction call.
OWNER_OPEN_ID = "ou_exampleowner00000000000000000001"


def _capture(name):
    return json.loads((CAPTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def go_body():
    """The ``code: 0`` GO body — WIRE-OBSERVED (R8)."""
    return _capture("R8-search-owner-exact-READ-POSTRELEASE-GO.json")["response"]


@pytest.fixture(scope="module")
def denial_body():
    """The verbatim ``99991672`` denial body — WIRE-OBSERVED (R1)."""
    return _capture("R1-search-owner-exact-READ.json")["response"]


@pytest.fixture(scope="module")
def abnormals_body():
    """The real ``code: 0`` + ``abnormals[]`` body — WIRE-OBSERVED (S1, 2026-08-02)."""
    return json.loads(
        (REPO_ROOT / "tests" / "captures" / "name-lookup-spike" / "slice2" / "captures"
         / "S1-search-owner-abnormals-READ.json").read_text(encoding="utf-8"))["response"]


class _FakeResponse:
    """What the SDK hands back: ``success()``, ``code``, ``msg``, ``data``, and the raw body.

    Deliberately built from a **body dict** so a fixture is the captured JSON rather than a
    hand-assembled object graph.
    """

    def __init__(self, body):
        self.code = body.get("code")
        self.msg = body.get("msg", "")
        self.error = body.get("error")
        self.raw_body = body
        self.data = _FakeData(body.get("data") or {})

    def success(self):
        return self.code == 0


class _FakeData:
    def __init__(self, data):
        self.employees = [_Attr(e) for e in (data.get("employees") or [])]
        self.page_response = _Attr(data["page_response"]) if data.get("page_response") else None
        self.abnormals = [_Attr(a) for a in (data.get("abnormals") or [])] or None


class _Attr:
    """A dict as an attribute bag, recursively — the SDK's deserialized shape."""

    def __init__(self, mapping):
        for key, value in (mapping or {}).items():
            setattr(self, key, _Attr(value) if isinstance(value, dict) else value)

    def __getattr__(self, item):  # an unreported field is None, exactly as the SDK leaves it
        return None


class _FakeSdk:
    """The minimal ``lark.Client`` shape the contacts client touches."""

    def __init__(self, *bodies):
        self._bodies = list(bodies)
        self.requests = []
        self.directory = _FakeNamespace(self)


class _FakeNamespace:
    def __init__(self, sdk):
        self.v1 = self
        self.employee = self
        self._sdk = sdk

    def search(self, request):
        self._sdk.requests.append(request)
        body = self._sdk._bodies.pop(0) if len(self._sdk._bodies) > 1 else self._sdk._bodies[0]
        return _FakeResponse(body)


def _contacts_client(*bodies, **kwargs):
    """A contacts client wired to canned bodies, with pacing that never sleeps in a test."""
    kwargs.setdefault("rate_limiter", RateLimiter(
        1_000_000, window=0.0, time_fn=lambda: 0.0, sleep_fn=lambda _s: None))
    return ContactsSearchClient(
        "id", "secret", sdk_client=_FakeSdk(*bodies), **kwargs)


def _body(employees=(), abnormals=None, has_more=False, page_token="tok", count=None):
    """An SDK-SHAPE-DERIVED ``code: 0`` body. See this module's docstring."""
    page = {"has_more": has_more, "page_token": page_token}
    if count is not None:
        page["count"] = count
    data = {"employees": list(employees), "page_response": page}
    if abnormals is not None:
        data["abnormals"] = list(abnormals)
    return {"code": 0, "msg": "", "data": data}


def _employee(open_id, display_name, i18n=None):
    """One ``employees[]`` entry in the wire's own shape (see R8)."""
    return {
        "base_info": {
            "employee_id": open_id,
            "name": {"name": {"default_value": display_name,
                              "i18n_value": i18n or {"en_us": "", "ja_jp": "", "zh_cn": ""}}},
        }
    }


# --------------------------------------------------------------------------- #
# AC1 — the id field the wire actually uses, over the committed GO capture.     #
# --------------------------------------------------------------------------- #

def test_ac1_the_go_capture_resolves_to_exactly_one_open_id(go_body):
    """The offline half of AC1: the shipped path over the committed ``R8`` body."""
    lookup = resolve_user(name="Example User", client=_contacts_client(go_body))
    assert isinstance(lookup, NameLookup)
    assert lookup.resolved
    assert lookup.user == UserRef(open_id=OWNER_OPEN_ID, display_name="Example User")
    assert lookup.refusal is None


def test_ac1_the_id_is_read_from_employee_id_because_user_id_is_ABSENT(go_body):
    """The wire answered §5's open question and the draft's guess was wrong: with
    ``employee_id_type=open_id`` there is no ``user_id`` key in the body at all."""
    base = go_body["data"]["employees"][0]["base_info"]
    assert base["employee_id"] == OWNER_OPEN_ID
    assert "user_id" not in base, "the capture changed; the id-field claim must be re-derived"
    stripped = json.loads(json.dumps(go_body))
    stripped["data"]["employees"][0]["base_info"]["employee_id"] = None
    lookup = resolve_user(name="Example User", client=_contacts_client(stripped))
    assert not lookup.resolved, "a row with no id must never be reported as a resolved user"


# --------------------------------------------------------------------------- #
# AC3 — THE KEY AC: the `abnormals` partial-answer trap, in four parts.         #
# --------------------------------------------------------------------------- #

def test_ac3a_the_REAL_wire_body_is_never_reported_as_a_clean_answer(abnormals_body):
    """(a) **WIRE-OBSERVED** fixture (S1). The dangerous shape, exactly as Lark sent it: the row
    is in ``employees[]`` AND in ``abnormals[]``. It must not resolve, and the error codes must
    reach the caller verbatim rather than as a boolean."""
    data = abnormals_body["data"]
    assert data["employees"][0]["base_info"]["employee_id"] == OWNER_OPEN_ID
    assert data["abnormals"][0]["id"] == OWNER_OPEN_ID, "the capture changed; re-derive AC3(a)"

    lookup = resolve_user(name="Example User", client=_contacts_client(abnormals_body))
    assert not lookup.resolved, (
        "a row the directory itself flagged was certified as a resolved user — this is the "
        "partial-answer trap AC3 exists to close")
    assert lookup.refusal.reason is RefusalReason.NOT_FOUND
    assert lookup.partiality.is_partial
    assert lookup.partiality.abnormal_rows[0].field_errors == {
        "education_and_work_experience": 2003, "personal_and_social_relationship": 2003}
    assert lookup.partiality.abnormal_rows[0].row_error == 0, (
        "row_error 0 with populated field_errors is precisely the 'looks fine' shape")
    assert "EXCLUDED" in lookup.refusal.detail, (
        "the refusal must say the negative is not clean, or it reads as 'no such person'")


def test_ac3a_an_abnormal_id_can_never_appear_in_the_resolved_output():
    """(a), as a TYPE property. SDK-SHAPE-DERIVED fixture: the constructor itself refuses, so no
    future code path can assemble the forbidden answer even by accident."""
    partial = Partiality(
        abnormal_rows=(dict(id=OWNER_OPEN_ID, row_error=1, field_errors={"base_info": 2}),))
    with pytest.raises(ValueError, match="abnormal"):
        NameLookup(query="Example User", partiality=partial,
                   user=UserRef(open_id=OWNER_OPEN_ID, display_name="Example User"))


def test_ac3b_the_disclosure_is_typed_and_branchable_never_a_boolean():
    """(b) SDK-SHAPE-DERIVED fixture. How many rows were abnormal, and each one's ``row_error``
    and ``field_errors`` map, verbatim."""
    body = _body(
        employees=[_employee("ou_good", "Example User")],
        abnormals=[{"id": "ou_bad", "row_error": 99991672,
                    "field_errors": {"base_info.mobile": 99991672}}],
    )
    lookup = resolve_user(name="Example User", client=_contacts_client(body))
    assert lookup.partiality.is_partial
    assert len(lookup.partiality.abnormal_rows) == 1
    row = lookup.partiality.abnormal_rows[0]
    assert row.id == "ou_bad"
    assert row.row_error == 99991672
    assert row.field_errors == {"base_info.mobile": 99991672}
    assert not isinstance(lookup.partiality.abnormal_rows, bool)


def test_ac3c_a_row_with_no_id_is_the_SAME_CLASS_as_an_abnormal_row():
    """(c) SDK-SHAPE-DERIVED fixture. ``base_info`` present, id field missing: not a resolved
    user, and counted in the disclosure rather than dropped silently."""
    body = _body(employees=[
        _employee("ou_good", "Example User"),
        {"base_info": {"name": {"name": {"default_value": "Example User"}}}},
    ])
    lookup = resolve_user(name="Example User", client=_contacts_client(body))
    assert lookup.partiality.rows_without_an_id == 1
    assert lookup.partiality.is_partial
    assert lookup.resolved and lookup.user.open_id == "ou_good"


def test_ac3d_the_disclosure_survives_even_when_exactly_one_good_hit_resolves():
    """(d) SDK-SHAPE-DERIVED fixture. The success case is where a partial answer is most
    dangerous, so this is the case the disclosure must reach."""
    body = _body(
        employees=[_employee(OWNER_OPEN_ID, "Example User")],
        abnormals=[{"id": "ou_other", "row_error": 1, "field_errors": {}}],
    )
    lookup = resolve_user(name="Example User", client=_contacts_client(body))
    assert lookup.resolved and lookup.user.open_id == OWNER_OPEN_ID
    assert lookup.partiality.is_partial
    assert "1" in lookup.partiality.detail()


def test_ac3_a_bare_success_object_is_STRUCTURALLY_UNREACHABLE():
    """The invariant stated as a type property: there is no way to say *"resolved"* without
    also saying what, if anything, was incomplete."""
    with pytest.raises(TypeError):
        NameLookup(query="Example User",  # noqa: E501 - the missing argument IS the assertion
                   user=UserRef(open_id=OWNER_OPEN_ID, display_name="Example User"))
    with pytest.raises(ValueError, match="exactly one"):
        NameLookup(query="Example User", partiality=Partiality())


def test_ac3_a_clean_body_discloses_NOT_PARTIAL_rather_than_saying_nothing(go_body):
    """The other half: the honest-unknown discipline cuts both ways — a complete answer says
    so, with the same object a partial one uses."""
    lookup = resolve_user(name="Example User", client=_contacts_client(go_body))
    assert not lookup.partiality.is_partial
    assert lookup.partiality.abnormal_rows == ()
    assert lookup.partiality.rows_without_an_id == 0


# --------------------------------------------------------------------------- #
# AC4 — the client-side contract: casefold + whitespace-normalized EXACT.        #
# --------------------------------------------------------------------------- #

def test_ac4_matching_is_casefolded_and_whitespace_normalized(go_body):
    for query in ("example user", "  Example   User ", "EXAMPLE USER"):
        lookup = resolve_user(name=query, client=_contacts_client(go_body))
        assert lookup.resolved and lookup.user.open_id == OWNER_OPEN_ID, query


def test_ac4_a_server_side_PREFIX_or_SUBSTRING_hit_is_filtered_out_client_side():
    """If the server fuzzy- or prefix-matches, the surplus is discarded — not ranked, not
    top-hit-taken. SDK-SHAPE-DERIVED fixture."""
    body = _body(employees=[
        _employee("ou_exact", "Example Person"),
        _employee("ou_prefixy", "Example Personford"),
        _employee("ou_other", "Example"),
    ])
    lookup = resolve_user(name="Example Person", client=_contacts_client(body))
    assert lookup.resolved and lookup.user.open_id == "ou_exact"


def test_ac4_NO_fuzzy_no_phonetics_no_top_hit():
    """A near miss is a miss. SDK-SHAPE-DERIVED fixture."""
    body = _body(employees=[_employee("ou_near", "Example Persen")])
    lookup = resolve_user(name="Example Person", client=_contacts_client(body))
    assert not lookup.resolved
    assert lookup.refusal.reason is RefusalReason.NOT_FOUND


def test_ac4_a_localized_name_the_DIRECTORY_ITSELF_reports_still_matches_exactly():
    """The only widening: the directory's own ``i18n_value`` strings for the same employee are
    compared with the same exact rule. Nothing is transliterated or guessed."""
    body = _body(employees=[
        _employee("ou_i18n", "Example User", i18n={"zh_cn": "姓名", "en_us": "", "ja_jp": ""})])
    assert resolve_user(name="姓名", client=_contacts_client(body)).user.open_id == "ou_i18n"


# --------------------------------------------------------------------------- #
# AC5 — ambiguity, the candidate privacy rule, and the `count` question.        #
# --------------------------------------------------------------------------- #

def test_ac5_more_than_one_exact_hit_is_the_SHIPPED_ambiguous_refusal():
    body = _body(employees=[_employee("ou_a", "Shared Name"), _employee("ou_b", "Shared Name")])
    lookup = resolve_user(name="Shared Name", client=_contacts_client(body))
    assert not lookup.resolved
    assert lookup.refusal.reason is RefusalReason.AMBIGUOUS
    assert lookup.refusal.candidate_ids == ("ou_a", "ou_b")
    assert lookup.refusal.candidate_count == 2


def test_ac5_candidate_ids_are_open_ids_ONLY_never_display_names():
    """A refusal drawn from the live directory must not become an enumeration oracle."""
    body = _body(employees=[
        _employee("ou_a", "Shared Name", i18n={"zh_cn": "名字"}),
        _employee("ou_b", "Shared Name"),
    ])
    lookup = resolve_user(name="Shared Name", client=_contacts_client(body))
    text = lookup.refusal.detail + " ".join(lookup.refusal.candidate_ids)
    for leaked in ("Shared Name", "名字"):
        assert leaked not in text, f"a candidate display name reached the refusal: {leaked!r}"


def test_ac5_how_many_is_derived_from_len_and_has_more_not_from_an_absent_count(go_body):
    """The wire correction: ``page_response`` on ``R8`` carried ``has_more`` + ``page_token``
    and **no** ``count`` key. A refusal must never cite a field whose meaning was assumed."""
    assert "count" not in go_body["data"]["page_response"]
    body = _body(employees=[_employee("ou_a", "Shared Name"), _employee("ou_b", "Shared Name")],
                 has_more=True)
    lookup = resolve_user(name="Shared Name", client=_contacts_client(body))
    assert lookup.reported_count is None
    assert "2" in lookup.refusal.detail
    assert "more" in lookup.refusal.detail.lower()
    assert "count" not in lookup.refusal.detail.lower()


def test_ac5_a_POPULATED_count_is_carried_but_still_not_interpreted():
    """If the field ever arrives it is reported verbatim and never relabelled a total or a
    page count — that reading has not been observed. SDK-SHAPE-DERIVED fixture."""
    body = _body(employees=[_employee("ou_a", "Shared Name")], count=7)
    assert resolve_user(name="Shared Name", client=_contacts_client(body)).reported_count == 7


def test_ac5_the_ambiguous_detail_says_HOW_to_disambiguate():
    body = _body(employees=[_employee("ou_a", "Shared Name"), _employee("ou_b", "Shared Name")])
    detail = resolve_user(name="Shared Name", client=_contacts_client(body)).refusal.detail
    assert "open_id" in detail


# --------------------------------------------------------------------------- #
# AC6 — "I could not look" != "I looked and it is not there", the LD-200 shape.  #
# --------------------------------------------------------------------------- #

def test_ac6_a_scope_denial_reaches_the_caller_as_LarkPermissionError(denial_body):
    """WIRE-OBSERVED fixture (R1). Not ``NOT_FOUND``, not "no such user", not a bare
    ``LarkAPIError``."""
    with pytest.raises(LarkPermissionError) as caught:
        resolve_user(name="Example User", client=_contacts_client(denial_body))
    denial = caught.value.denial
    assert denial is not None
    assert denial.scopes == (
        denial_body["error"]["permission_violations"][0]["subject"],)
    assert denial.console_url == denial_body["error"]["helps"][0]["url"]
    assert denial.code == 99991672
    assert denial.msg == denial_body["msg"]


def test_ac6_the_denial_names_the_credential_pair_that_made_the_call(denial_body):
    with pytest.raises(LarkPermissionError) as caught:
        resolve_user(name="Example User", client=_contacts_client(denial_body))
    assert caught.value.denial.credential_env, (
        "a denial with no credential attribution sends someone to edit the wrong variable")


def test_ac6_COULD_NOT_LOOK_and_MATCHED_NOBODY_are_structurally_different(denial_body):
    """The single most important distinction in the feature, proved side by side."""
    empty = resolve_user(name="Nobody At All", client=_contacts_client(_body()))
    assert not empty.resolved and empty.refusal.reason is RefusalReason.NOT_FOUND
    with pytest.raises(LarkPermissionError):
        resolve_user(name="Nobody At All", client=_contacts_client(denial_body))


def test_ac6_no_surface_local_refusal_reason_was_minted():
    """LD-200 shipped the mechanism generically; a second, surface-local reason would
    re-fragment exactly the shape it unified."""
    assert not [r for r in RefusalReason if "LOOKUP" in r.name or "UNAVAILABLE" in r.name]


def test_ac6_a_NON_permission_api_failure_is_still_a_plain_LarkAPIError():
    """The must-not-bite: not every failure is a scope problem."""
    with pytest.raises(LarkAPIError) as caught:
        resolve_user(name="Example User",
                     client=_contacts_client({"code": 1254001, "msg": "internal error", "data": {}}))
    assert not isinstance(caught.value, LarkPermissionError)


def test_ac6_the_lookup_never_falls_back_to_enumeration(denial_body):
    """A denial ends the lookup. It does not become a directory walk, and it does not guess."""
    client = _contacts_client(denial_body)
    with pytest.raises(LarkPermissionError):
        resolve_user(name="Example User", client=client)
    assert client.api_calls == 1


# --------------------------------------------------------------------------- #
# AC8 — the resigned-employee default is SET, not inherited.                    #
# --------------------------------------------------------------------------- #

def test_ac8_contain_resigned_employee_is_set_EXPLICITLY_on_every_request(go_body):
    client = _contacts_client(go_body)
    resolve_user(name="Example User", client=client)
    body = client.last_request.request_body
    assert body.filter is not None, "the filter must be sent, not left to the server default"
    assert body.filter.contain_resigned_employee is CONTAIN_RESIGNED_EMPLOYEE


def test_ac8_the_shipped_default_EXCLUDES_resigned_employees():
    assert CONTAIN_RESIGNED_EMPLOYEE is False


# --------------------------------------------------------------------------- #
# AC9 — pacing: one named literal, an injectable limiter, testable offline.      #
# --------------------------------------------------------------------------- #

def test_ac9_the_default_limiter_is_built_from_the_named_literals():
    client = ContactsSearchClient("id", "secret", sdk_client=_FakeSdk(_body()))
    assert CONTACTS_RATE_WINDOW_SECONDS == 60.0
    assert DEFAULT_MAX_SEARCHES_PER_WINDOW < 100
    assert CONTACTS_MIN_REQUEST_SPACING_SECONDS == pytest.approx(
        CONTACTS_RATE_WINDOW_SECONDS / DEFAULT_MAX_SEARCHES_PER_WINDOW)
    assert client.limiter.max_per_sec == 1
    assert client.limiter.window == pytest.approx(CONTACTS_MIN_REQUEST_SPACING_SECONDS)


def test_ac9_the_spacing_is_at_least_the_spikes_observed_safe_1_2_seconds():
    assert CONTACTS_MIN_REQUEST_SPACING_SECONDS >= 1.2


def test_ac9_every_call_passes_through_the_limiter(go_body):
    slept, now = [], [0.0]

    def sleep_fn(seconds):
        slept.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(1, window=1.2, time_fn=lambda: now[0], sleep_fn=sleep_fn)
    client = _contacts_client(go_body, rate_limiter=limiter)
    resolve_user(name="Example User", client=client)
    resolve_user(name="Example User", client=client)
    assert client.api_calls == 2
    assert slept and slept[0] == pytest.approx(1.2)


# --------------------------------------------------------------------------- #
# The request shape itself — the two query params the wire capture used.        #
# --------------------------------------------------------------------------- #

def test_the_request_asks_for_open_ids_and_only_the_field_it_needs(go_body):
    client = _contacts_client(go_body)
    resolve_user(name="Example User", client=client)
    request = client.last_request
    assert ("employee_id_type", "open_id") in request.queries
    assert request.request_body.required_fields == ["base_info"]
    assert request.request_body.query == "Example User"


def test_an_empty_name_makes_NO_CALL_at_all(go_body):
    client = _contacts_client(go_body)
    with pytest.raises(ValueError, match="name"):
        resolve_user(name="   ", client=client)
    assert client.api_calls == 0
