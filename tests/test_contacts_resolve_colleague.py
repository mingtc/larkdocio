"""LD-348 — ``contacts.resolve_colleague(email|mobile)``, and the honesty it is bound to.

**Offline, against the COMMITTED capture bytes.** Every wire shape asserted here is loaded
from ``tests/captures/name-lookup-spike/batch-get-id/captures/B*.json`` — the real payloads of the
2026-08-08 read-only probe — rather than from a hand-mocked dict, so a Lark-side change to the
unresolved shape reddens here instead of shipping.

**The honesty core (AC2) is the point of this module.** An unresolved identifier is a single
UNDIFFERENTIATED shape: an address that exists nowhere and a real user this app cannot see
produce the identical body (``code: 0``, the identifier echoed, the ``user_id`` key **omitted**
— not ``null``, not empty). The refusal therefore states BOTH halves of that dual truth and
picks neither, and the tests below assert exactly that.
"""
import json
import pathlib

import pytest

from larkdocio import contacts
from larkdocio.contacts import lookup as lookup_mod
from larkdocio.contacts.lookup import (
    MEASURED_REACH,
    MOBILE_LEG_UNOBSERVED,
    NameLookup,
    Partiality,
    UserRef,
    resolve_colleague,
)
from larkdocio.write.model.refusal import RefusalReason

CAPTURES = (pathlib.Path(__file__).resolve().parents[1]
            / "tests" / "captures" / "name-lookup-spike" / "batch-get-id" / "captures")

#: The owner's address as the committed record carries it (``captures/P2``/``P6``/``W2``) — a
#: placeholder in this tree (``tests/captures/README.md``), used exactly as the captures spell it.
#: **No third party's address appears anywhere in this repository** — the second user arms below
#: run off the REDACTED capture, and the live arm reads a real address out of the environment.
OWNER_EMAIL = "example.user@example.com"
OWNER_ID = "ou_exampleowner00000000000000000001"
REDACTED_SECOND_USER = "<SECOND-USER-EMAIL-REDACTED>@example.com"
SECOND_USER_ID = "ou_examplesecond0000000000000000001"
NOWHERE_EMAIL = "nobody.does.not.exist@example.invalid"
SYNTHETIC_MOBILE = "+10000000000"


def capture(name: str) -> dict:
    return json.loads((CAPTURES / f"{name}.json").read_text(encoding="utf-8"))


def body_of(name: str) -> dict:
    """One capture's ``data`` block — the exact bytes the endpoint answered with."""
    return capture(name)["response"]["data"]


class FakeClient:
    """A stand-in that hands back one committed capture's ``data`` block, verbatim.

    Deliberately a **dict**, not the SDK's model: the whole AC2 question is what an OMITTED
    key looks like, and a dict is the only transport that can express *omitted* rather than
    *None*. The shipped reader must cope with both, which is what the SDK arm below proves.
    """

    def __init__(self, data, *, expect=None):
        self.data = data
        self.expect = expect
        self.calls = []

    def batch_get_id(self, *, emails=None, mobiles=None):
        self.calls.append({"emails": emails, "mobiles": mobiles})
        if self.expect is not None:
            assert self.calls[-1] == self.expect, self.calls[-1]
        return self.data


# --------------------------------------------------------------------------- #
# AC1 — the verb ships, reusing the shipped answer types UNCHANGED.            #
# --------------------------------------------------------------------------- #

def test_ac1_the_verb_is_exported_beside_resolve_user():
    assert "resolve_colleague" in contacts.__all__
    assert contacts.resolve_colleague is resolve_colleague
    assert "resolve_user" in contacts.__all__, "the sibling verb is untouched"


def test_ac1_an_email_resolves_to_exactly_one_open_id_from_the_OWNER_capture():
    client = FakeClient(body_of("B1-owner-email-CONTROL"),
                        expect={"emails": [OWNER_EMAIL], "mobiles": None})
    answer = resolve_colleague(email=OWNER_EMAIL, client=client)
    assert isinstance(answer, NameLookup)
    assert answer.resolved
    assert isinstance(answer.user, UserRef)
    assert answer.user.open_id == OWNER_ID
    assert answer.query == OWNER_EMAIL, "NameLookup.query carries the identifier asked about"
    assert not answer.partiality.is_partial
    assert answer.candidate_ids == (OWNER_ID,)


def test_ac1_the_DECISIVE_second_user_capture_resolves_a_DIFFERENT_id():
    """`B3` is the whole reason this feature exists: another user no other route here reaches."""
    client = FakeClient(body_of("B3-SECOND-USER-email-DECISIVE"))
    answer = resolve_colleague(email=REDACTED_SECOND_USER, client=client)
    assert answer.resolved
    assert answer.user.open_id == SECOND_USER_ID != OWNER_ID


def test_ac1_the_resolved_user_carries_NO_display_name_because_none_was_returned():
    """``UserRef`` is reused unchanged, so it still has a ``display_name`` field — and this
    endpoint sends none. It is left EMPTY rather than back-filled with the address: an email
    is not a display name, and inventing one would be the guess this surface refuses."""
    client = FakeClient(body_of("B1-owner-email-CONTROL"))
    answer = resolve_colleague(email=OWNER_EMAIL, client=client)
    assert answer.user.display_name == ""


@pytest.mark.parametrize("kwargs", [{}, {"email": OWNER_EMAIL, "mobile": SYNTHETIC_MOBILE},
                                    {"email": "  "}, {"email": None, "mobile": ""}])
def test_ac1_neither_or_both_is_a_CONFIG_ERROR_not_a_refusal_object(kwargs):
    with pytest.raises(ValueError):
        resolve_colleague(**kwargs)


def test_ac1_a_config_error_is_raised_BEFORE_any_call_is_made():
    client = FakeClient(body_of("B1-owner-email-CONTROL"))
    with pytest.raises(ValueError):
        resolve_colleague(client=client)
    assert client.calls == [], "a blank question must not spend a request"


def test_ac1_the_verb_is_KEYWORD_ONLY():
    with pytest.raises(TypeError):
        resolve_colleague(OWNER_EMAIL)  # noqa: B026 - the point of the test


def test_ac1_NO_NEW_RefusalReason_MEMBER_AND_NO_PARALLEL_ANSWER_TYPE():
    """LD-229 AC6, re-asserted. The member list is spelled out so an addition reddens here.

    ``CHANGE_NOT_EXPRESSIBLE`` joined it deliberately (LD-574): the enum grew because the
    compiler gained a refusal it had no member for — a counted change whose compiled request
    set would write bytes identical to what is live. That is the mechanism working, not a
    hole in it: this guard's reason is that no member arrives by accident, and this one
    arrived with an issue, a registry entry and a bidirectional doc guard. ``TABLE_GROW_UNSUPPORTED``
    joined it on the same terms (LD-575): the table-grow op needed a reason for *the table
    resolved and this is not the grow that ships*, which none of the members above meant.

    **The APPLY-TIME family joined it on the same terms (LD-643)** — eight members at once,
    which is the largest single addition this list has taken and therefore the one most worth
    saying out loud. Every reason above is a claim about the document or the request, decided
    before a call or instead of one; the eight are what happened to a call that WAS made, and
    the docx engine had no member for any of them because it had no boundary to produce them.
    They arrived with an issue, one producing module, and the same bidirectional guards.
    """
    assert {member.name for member in RefusalReason} == {
        "AMBIGUOUS", "BLOCK_TYPE_MUTATION", "CANNOT_HOLD_CHILDREN", "CANNOT_HOLD_SIBLINGS",
        "CHANGE_NOT_EXPRESSIBLE",
        "COLUMN_NOT_FOUND", "COMMENT_ANCHORS_PRESENT", "COMMENT_ANCHOR_NOT_CREATABLE",
        "COMMENT_SURFACE_UNSUPPORTED", "COMMENT_THREAD_NOT_SOLELY_AUTHORED",
        "CONSERVED_BLOCK_RE_CREATED", "MARKER_ABSENT", "MARKER_DROPPED", "MARKER_DUPLICATED",
        "MARKER_INVENTED", "MARKER_MANGLED", "MARKER_ORDER_CHANGED", "MARKER_ORPHANED",
        "MARKER_RELOCATED", "MERGE_NOT_EXPRESSIBLE", "NOT_FOUND", "NOT_IN_DIALECT",
        "SEGMENT_AMBIGUOUS", "SPAN_NOT_SPLITTABLE", "STALE_ANCHOR", "STALE_DOCUMENT",
        "TABLE_GROW_UNSUPPORTED",
        "UNDECODABLE_TEXT", "UNMARKED_CONTENT_CHANGED", "WRITE_HOSTILE",
        # LD-643 — the apply-time disposition family.
        "API_ERROR", "NOT_ATTEMPTED", "PAGINATION_UNTERMINATED", "PERMISSION_DENIED",
        "RATE_LIMITED", "TRANSPORT_FAILURE", "UNEXPECTED_ERROR", "UNVERIFIED_WRITE",
    }
    assert lookup_mod.NameLookup is NameLookup, "one answer type, not two"
    answer_types = {name for name, obj in vars(lookup_mod).items()
                    if isinstance(obj, type) and obj.__module__ == lookup_mod.__name__}
    assert answer_types == {"UserRef", "AbnormalRow", "Partiality", "NameLookup"}, (
        "resolve_colleague reuses the shipped answer types; a new one re-fragments exactly "
        "what LD-229 unified")


def test_ac1_MORE_THAN_ONE_ENTRY_for_one_input_is_AMBIGUOUS_with_open_ids_only():
    """One address, one id, is an ASSUMPTION until observed — so a second entry refuses
    rather than picking. Never seen on the wire; that is precisely why it is guarded."""
    doubled = {"user_list": [{"email": OWNER_EMAIL, "user_id": OWNER_ID},
                             {"email": OWNER_EMAIL, "user_id": SECOND_USER_ID}]}
    answer = resolve_colleague(email=OWNER_EMAIL, client=FakeClient(doubled))
    assert not answer.resolved
    assert answer.refusal.reason is RefusalReason.AMBIGUOUS
    assert set(answer.refusal.candidate_ids) == {OWNER_ID, SECOND_USER_ID}
    for id_ in (OWNER_ID, SECOND_USER_ID):
        assert id_ in answer.refusal.detail or id_ in answer.refusal.candidate_ids
    assert "@" not in answer.refusal.detail, "ids only — a refusal is not an address oracle"


def test_ac1_AN_ENTRY_THE_CALLER_DID_NOT_ASK_ABOUT_is_AMBIGUOUS_never_a_pick():
    """The `B4` mixed-batch hazard seen from the single-input side: an entry echoing an
    identifier that is not the one asked about is never silently adopted."""
    foreign = {"user_list": [{"email": NOWHERE_EMAIL, "user_id": SECOND_USER_ID}]}
    answer = resolve_colleague(email=OWNER_EMAIL, client=FakeClient(foreign))
    assert not answer.resolved
    assert answer.refusal.reason is RefusalReason.AMBIGUOUS
    assert answer.candidate_ids == ()


def test_ac1_an_email_match_is_CASEFOLDED_but_nothing_more():
    shouty = {"user_list": [{"email": OWNER_EMAIL.upper(), "user_id": OWNER_ID}]}
    answer = resolve_colleague(email=OWNER_EMAIL, client=FakeClient(shouty))
    assert answer.resolved and answer.user.open_id == OWNER_ID


def test_ac1_the_SDK_MODEL_transport_reads_the_same_answer_as_the_raw_dict():
    """The pinned SDK deserializes an omitted key to ``None``; a raw dict omits it. Both must
    reach the identical refusal, or the answer would depend on the transport."""
    from lark_oapi.api.contact.v3 import BatchGetIdUserResponseBody

    typed = BatchGetIdUserResponseBody(body_of("B2-unknown-email-CONTROL"))
    assert typed.user_list[0].user_id is None
    from_sdk = resolve_colleague(email=NOWHERE_EMAIL, client=FakeClient(typed))
    from_dict = resolve_colleague(email=NOWHERE_EMAIL,
                                  client=FakeClient(body_of("B2-unknown-email-CONTROL")))
    assert from_sdk.to_dict() == from_dict.to_dict()


# --------------------------------------------------------------------------- #
# AC2 — THE HONESTY CORE: the refusal states the DUAL TRUTH and picks neither. #
# --------------------------------------------------------------------------- #

def test_ac2_THE_COMMITTED_UNRESOLVED_CAPTURE_HAS_THE_user_id_KEY_OMITTED():
    """The fixture's own premise, asserted before anything is read into it: `B2` is `code: 0`,
    the identifier echoed, and the key ABSENT — not ``null``, not empty."""
    raw = capture("B2-unknown-email-CONTROL")["response"]
    assert raw["code"] == 0
    entry, = raw["data"]["user_list"]
    assert entry == {"email": NOWHERE_EMAIL}
    assert "user_id" not in entry


def test_ac2_the_dual_truth_is_AUTHORED_ONCE_as_a_module_constant():
    assert isinstance(lookup_mod.UNRESOLVED_IS_UNDIFFERENTIATED, str)
    assert "UNRESOLVED_IS_UNDIFFERENTIATED" in contacts.__all__


def test_ac2_an_unresolved_email_refuses_with_BOTH_HALVES_and_neither_side_picked():
    answer = resolve_colleague(email=NOWHERE_EMAIL,
                               client=FakeClient(body_of("B2-unknown-email-CONTROL")))
    assert not answer.resolved
    assert answer.refusal.reason is RefusalReason.NOT_FOUND
    detail = answer.refusal.detail
    assert lookup_mod.UNRESOLVED_IS_UNDIFFERENTIATED in detail, (
        "the wording is QUOTED, never paraphrased")
    lowered = detail.lower()
    assert "does not mean no such person exists" in lowered, "half one of the dual truth"
    assert "out of this app's reach" in lowered, "half two of the dual truth"
    assert "no such user" not in lowered, (
        "a shipped string that reads as 'no such user' is exactly the misreading AC2 forbids")


def test_ac2_the_unresolved_answer_is_PARTIAL_not_a_clean_negative():
    answer = resolve_colleague(email=NOWHERE_EMAIL,
                               client=FakeClient(body_of("B2-unknown-email-CONTROL")))
    assert answer.partiality.is_partial
    assert answer.partiality.rows_without_an_id == 1
    assert isinstance(answer.partiality, Partiality)


def test_ac2_an_input_that_VANISHED_from_user_list_is_a_partiality_too():
    """The mixed-batch hazard (`B4`) in its worst single-input form: `code: 0` and the input
    is simply not mentioned. That is an absence of an ANSWER, not an answer of absence."""
    answer = resolve_colleague(email=OWNER_EMAIL, client=FakeClient({"user_list": []}))
    assert not answer.resolved
    assert answer.partiality.is_partial
    assert lookup_mod.UNRESOLVED_IS_UNDIFFERENTIATED in answer.refusal.detail


def test_ac2_the_dual_truth_reads_beside_the_packages_existing_rider():
    """The rider is CITED, not re-authored — it already binds the search route and binds
    harder here, because this route reaches further."""
    rider = ('Read\n  a *not-found* from this endpoint as *"the search did not return them"*, '
             'never as *"this\n  person does not exist"*')
    assert rider in contacts.__doc__, "the shipped rider is quoted verbatim, not re-typed"
    assert contacts.__doc__.count(rider) == 1, "cited ONCE — re-authoring it is the failure"
    assert "binds **harder** there" in contacts.__doc__, (
        "and the new route says the rider reaches it too, because it reaches further")


def test_ac2_the_constant_lands_in_the_refusal_the_docstring_the_guide_and_capabilities():
    from larkdocio import capabilities, guide

    text = lookup_mod.UNRESOLVED_IS_UNDIFFERENTIATED
    assert text in (resolve_colleague.__doc__ or "")
    assert text in guide(full=True)
    blob = json.dumps(capabilities(full=True))
    assert json.dumps(text)[1:-1] in blob


# --------------------------------------------------------------------------- #
# AC3 — the MOBILE leg is ACCEPTED-BUT-NEVER-OBSERVED-RESOLVING, and says so.  #
# --------------------------------------------------------------------------- #

def test_ac3_a_mobile_is_ACCEPTED_and_refuses_cleanly_on_the_B5_capture():
    client = FakeClient(body_of("B5-mobile-leg"),
                        expect={"emails": None, "mobiles": [SYNTHETIC_MOBILE]})
    answer = resolve_colleague(mobile=SYNTHETIC_MOBILE, client=client)
    assert not answer.resolved
    assert answer.refusal.reason is RefusalReason.NOT_FOUND
    assert answer.query == SYNTHETIC_MOBILE
    assert lookup_mod.UNRESOLVED_IS_UNDIFFERENTIATED in answer.refusal.detail


def test_ac3_the_mobile_refusal_says_the_leg_has_NEVER_been_observed_resolving():
    answer = resolve_colleague(mobile=SYNTHETIC_MOBILE, client=FakeClient(body_of("B5-mobile-leg")))
    assert MOBILE_LEG_UNOBSERVED in answer.refusal.detail


def test_ac3_the_caveat_lands_in_the_docstring_the_guide_and_capabilities():
    from larkdocio import capabilities, guide

    assert MOBILE_LEG_UNOBSERVED in (resolve_colleague.__doc__ or "")
    assert MOBILE_LEG_UNOBSERVED in guide(full=True)
    assert json.dumps(MOBILE_LEG_UNOBSERVED)[1:-1] in json.dumps(capabilities(full=True))


def test_ac3_NOTHING_SHIPPED_PROMISES_THE_MOBILE_LEG_WORKS():
    import consumer_text

    corpus = dict(consumer_text.consumer_corpus())
    corpus["MOBILE_LEG_UNOBSERVED"] = MOBILE_LEG_UNOBSERVED
    corpus["resolve_colleague.__doc__"] = resolve_colleague.__doc__ or ""
    offenders = []
    for label, text in corpus.items():
        lowered = text.lower()
        for promise in ("a mobile should work", "mobiles resolve", "a mobile resolves",
                        "mobile lookup works"):
            if promise in lowered:
                offenders.append((label, promise))
    assert not offenders, offenders


# --------------------------------------------------------------------------- #
# AC4 — REACH IS MEASURED AT n=2 AND SAID SO. "any other user" is a FAIL.       #
# --------------------------------------------------------------------------- #

#: Every generalisation the measurement does not support. An occurrence is allowed ONLY where
#: the words just before it negate or bound it — which is how LD-347's landed *"never as
#: org-wide"* line stays legal while a fresh claim does not.
_FORBIDDEN_GENERALISATIONS = ("any other user", "all other users", "every other user",
                              "org-wide", "the whole directory")
_NEGATORS = ("never", "not ", "no ", "rather than", "unmeasured", "cannot", "does not")


def _unbounded_claims(text: str):
    lowered = text.lower()
    for phrase in _FORBIDDEN_GENERALISATIONS:
        start = 0
        while True:
            at = lowered.find(phrase, start)
            if at < 0:
                break
            start = at + 1
            window = lowered[max(0, at - 80):at]
            if not any(negator in window for negator in _NEGATORS):
                yield phrase, lowered[max(0, at - 80):at + len(phrase) + 20]


def test_ac4_the_measured_reach_is_authored_once_and_says_n_equals_two():
    assert "MEASURED_REACH" in contacts.__all__
    lowered = MEASURED_REACH.lower()
    assert "two" in lowered and "unmeasured" in lowered
    assert not list(_unbounded_claims(MEASURED_REACH))
    # LD-700 (T2): the n = 2 bound is stated as the TENANT it was measured on, and only that.
    assert "organisation" not in lowered and "organization" not in lowered
    assert "the tenant it was measured on" in lowered


def test_ac4_the_measured_reach_lands_in_the_refusal_docstring_guide_and_capabilities():
    from larkdocio import capabilities, guide

    answer = resolve_colleague(email=NOWHERE_EMAIL,
                               client=FakeClient(body_of("B2-unknown-email-CONTROL")))
    assert MEASURED_REACH in answer.refusal.detail
    assert MEASURED_REACH in (resolve_colleague.__doc__ or "")
    assert MEASURED_REACH in guide(full=True)
    assert json.dumps(MEASURED_REACH)[1:-1] in json.dumps(capabilities(full=True))


def test_ac4_NO_SHIPPED_STRING_GENERALISES_THE_REACH():
    import consumer_text

    offenders = []
    for label, text in consumer_text.consumer_corpus().items():
        for phrase, context in _unbounded_claims(text):
            offenders.append((label, phrase, context))
    assert not offenders, offenders


def test_ac4_the_DEFECT_of_generalising_the_reach_REDDENS():
    """A guard that cannot fail is not a guard."""
    assert list(_unbounded_claims("this resolves any other user on the tenant"))
    assert not list(_unbounded_claims("this is not a claim about any other user"))


# --------------------------------------------------------------------------- #
# AC5 — the scope row is a CANDIDATE/UNKNOWN, never a guessed string.          #
# --------------------------------------------------------------------------- #

ENDPOINT = "/open-apis/contact/v3/users/batch_get_id"


def test_ac5_the_endpoint_has_ITS_OWN_row_rather_than_inheriting_the_users_batch_pair():
    from larkdocio import permissions as perm

    row = perm._table_row(ENDPOINT, "read")
    assert row is not None and row[0] == ENDPOINT, (
        "without its own row the longest-prefix join would hand this endpoint the "
        "/contact/v3/users/batch pair — exactly the plausible-but-unproven guess AC5 forbids")


def test_ac5_the_row_ASSERTS_NO_SCOPE_STRING_and_records_why():
    from larkdocio import permissions as perm

    _prefix, _mode, scopes, note = perm._table_row(ENDPOINT, "read")
    assert scopes == (), (
        "no scope string could be sourced for this endpoint, so none is named — a string from "
        "memory is exactly what the evidence field exists to prevent")
    assert note, "an empty requirement without its reason reads as 'needs nothing'"
    lowered = note.lower()
    assert "code 0" in lowered or "code: 0" in lowered
    assert "denial" in lowered


def test_ac5_the_unknown_requirement_TRAVELS_to_the_operation_that_uses_it():
    from larkdocio import permissions as perm

    reasons = perm.unknown_requirements_for((ENDPOINT,), "read")
    assert reasons and reasons[0].startswith(ENDPOINT + ":")


def test_ac5_the_new_call_sites_ARE_COVERED_by_the_registry():
    from larkdocio import permissions as perm

    rows = perm.permission_registry()
    for op in ("resolve_colleague", "batch_get_id"):
        assert ("contacts-read", op) in rows, op
        assert ENDPOINT in rows[("contacts-read", op)].endpoints
    gaps = perm.coverage_gaps()
    assert (gaps.uncovered, gaps.orphans) == ([], [])


def test_ac5_the_candidate_never_becomes_a_SURFACE_requirement():
    from larkdocio import capabilities

    creds = capabilities(full=True)["surfaces"]["contacts-read"]["credentials"]
    assert "contact:contact.base:readonly" not in creds["scopes"], (
        "the plausible pair carried for /users/batch is NOT asserted for this endpoint")


# --------------------------------------------------------------------------- #
# AC6 — consumer truth ships with the change.                                  #
# --------------------------------------------------------------------------- #

def test_ac6_the_guide_names_a_FOURTH_honest_source_of_an_id():
    from larkdocio import guide

    text = guide(full=True)
    assert "Four honest sources of an id" in text
    assert "Three honest sources of an id" not in text
    assert "resolve_colleague" in text


def test_ac6_the_person_cell_FENCE_moves_without_blurring_name_into_email():
    """The `text` fence is generated from ``write_cells._PERSON_IDS_ONLY``; it gains the
    email route and must NOT read as if another user's NAME were now resolvable."""
    from larkdocio.base.write_cells import _PERSON_IDS_ONLY

    assert "resolve_colleague" in _PERSON_IDS_ONLY
    assert "email" in _PERSON_IDS_ONLY.lower()
    lowered = _PERSON_IDS_ONLY.lower()
    assert "a display name is not an id" in lowered
    assert "name into an id" not in lowered


def test_ac6_capabilities_reports_the_new_operation_on_contacts_read():
    from larkdocio import capabilities

    surface = capabilities(full=True)["surfaces"]["contacts-read"]
    names = {op["name"] for op in surface["operations"]}
    assert {"resolve_colleague", "batch_get_id", "resolve_user", "search_employees"} <= names


def test_ac6_the_guide_surfaces_table_and_readme_list_the_verb():
    from larkdocio import guide

    assert "`resolve_colleague`" in guide(full=True)
    readme = (pathlib.Path(__file__).resolve().parents[1] / "README.md").read_text("utf-8")
    assert "resolve_colleague" in readme


def test_ac6_the_POINT_QUERY_stance_is_shipped_and_the_prohibition_is_NOT_softened():
    from larkdocio import capabilities, guide

    blob = (guide(full=True) + json.dumps(capabilities(full=True))).lower()
    assert "point query" in blob
    offenders = [phrase for phrase in ("roster dump", "lookup table", "directory cache")
                 if phrase in blob and "not" not in blob[:blob.find(phrase)][-90:]]
    assert not offenders, offenders
