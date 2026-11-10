"""LD-432 — give a HUMAN access to a docx the app created, and move the two copy levers.

Offline, against fixtures **derived from the permissions spike's committed captures**
(``tests/access_fixtures.py`` carries the per-name provenance). One region per AC:

* **AC1** ``grant_access`` by email or ``open_id``, ``perm ∈ {view, edit, full_access}``;
* **AC2** a bare display NAME is refused **typed, before any network call**, and the refusal
  says *give me an email* without ever asserting the person does not exist;
* **AC3** the whole lifecycle — update (raise), downgrade (lower), revoke;
* **AC4** the member read, with the owner reported honestly (the owner is not a member row);
* **AC5** the copy lever: one key per call, each read back, the value set fenced to what was
  measured;
* **AC6** the disclosure contract, shipped with the surface;
* **AC7** ownership transfer is not shipped, and the refusal is where a caller would reach;
* **AC8** every negative claim enumerates its forms or says ``unmeasured``;
* **AC9** the permission rows — empty, with their reason, never a guessed scope string.

**Conformance-tier** (AC11): everything below that pins a **product contract** or **measured
external truth** this project does not own — the typed name refusal, the
lifecycle-completeness contract, the empty-member-list disclosure, the measured value fence —
is marked ``@pytest.mark.conformance`` per ``process/doctrine/conformance-tier.md`` (a lens,
not a gate). Today's Lark refusal codes are deliberately **not** pinned into an offline
assertion (the LD-417 AC10 precedent): they are quoted in prose and in the captures.
"""
import inspect
import pathlib

import access_fixtures as afx
import pytest

import capability_rows as rows
from larkdocio.drive import ops
from larkdocio.drive.access import (
    ABSENCES,
    BARE_NAME_REFUSAL,
    CLIPBOARD_UNOBSERVABLE,
    COPY_LEVER_KEYS,
    DOCX_TYPE,
    MEMBER_LIST_AT_BIRTH,
    EXTERNAL_ACCESS_REFUSED_HERE,
    GROUPS_UNMEASURED,
    LOCK_SWITCH_READ_ONLY,
    MEASURED_COPY_VALUES,
    MEMBER_FAMILY_IS_V1,
    MEMBER_PERMS,
    NOT_A_SCOPE_ESCALATION,
    OBJECT_TYPES_MEASURED,
    OWNERSHIP_TRANSFER_NOT_SHIPPED,
    OWNER_IS_NOT_A_MEMBER,
    TENANT_TOKEN_ONLY,
    THE_ROUTE_DOES_NOT_SWALLOW,
    WIRE_OBJECT_TYPES,
    AccessRefusedError,
    members_path,
    object_target,
    public_path,
)
from larkdocio.drive.access_write import DriveAccessWriteClient

ACCESS_MODULE = pathlib.Path(inspect.getfile(DriveAccessWriteClient.grant_access)).resolve()
POLICY_MODULE = ACCESS_MODULE.parent / "access.py"

DOC = afx.DOC
GRANTEE = afx.GRANTEE_OPEN_ID


def client(route, **kwargs):
    """A WRITE-pair access client whose whole transport is a recording stub."""
    transport = afx.RecordingTransport(route)
    kwargs.setdefault("token_fetcher", afx.token_fetcher)
    kwargs.setdefault("rate_limiter", afx.fast_limiter())
    return DriveAccessWriteClient("app-id", "app-secret", urlopen=transport, **kwargs), transport


# --------------------------------------------------------------------------- #
# Provenance — the evidence base is real, and these tests move when it does.    #
# --------------------------------------------------------------------------- #

def test_the_fixtures_are_DERIVED_FROM_THE_COMMITTED_CAPTURES():
    assert afx.CAPTURES.is_dir()
    assert afx.members(afx.MEMBERS_EMPTY) == []
    assert afx.members(afx.MEMBERS_FULL_ACCESS)[0]["perm"] == "full_access"
    assert afx.owner_id() == afx.BOT_OPEN_ID
    assert afx.public_payload(afx.PUBLIC_BASELINE)["copy_entity"] == "anyone_can_edit"


# --------------------------------------------------------------------------- #
# AC1 — GRANT, by email or open_id, at any of the three measured levels.        #
# --------------------------------------------------------------------------- #

def test_ac1_the_grant_sends_the_MEASURED_REQUEST_and_reads_it_back_independently():
    """Capture ``707-`` is the request; capture ``708-`` is the **finding**. ``code: 0`` proves
    acceptance and nothing else — the verdict is the separate read-back."""
    route = afx.access_router(
        member_write=afx.response(afx.GRANT_FULL_ACCESS),
        members_pages=[afx.response(afx.MEMBERS_FULL_ACCESS)],
    )
    access, transport = client(route)

    outcome = access.grant_access(DOC, open_id=GRANTEE, perm="full_access")

    sent, read_back = transport.calls
    measured = afx.request(afx.GRANT_FULL_ACCESS)
    assert sent.method == "POST"
    assert sent.path == members_path(DOC) == measured["path"].split("?")[0]
    assert sent.body == measured["body"]
    assert sent.params == {"type": DOCX_TYPE, "need_notification": "false"}
    assert read_back.method == "GET"
    assert outcome.stored_perm == "full_access"
    assert outcome.stored is True


@pytest.mark.conformance
def test_ac1_the_READ_BACK_is_the_verdict_and_a_SWALLOWED_grant_reports_UNSTORED():
    """The spike measured a live swallow on this very family (``759-`` accepted with a complete
    member echo, ``760-`` read back without it). An op that trusted the echo would have called
    that a success — so this one does not."""
    route = afx.access_router(
        member_write=afx.response(afx.TRANSFER_SWALLOW_ECHO),
        members_pages=[afx.response(afx.TRANSFER_SWALLOW_READBACK)],
    )
    access, _transport = client(route)

    outcome = access.grant_access(DOC, open_id=afx.BOT_OPEN_ID, perm="full_access")

    assert outcome.stored is False, "an accepted-but-not-stored grant must not report success"
    assert outcome.stored_perm is None
    assert outcome.requested_perm == "full_access"


def test_ac1_an_EMAIL_goes_through_the_SHIPPED_resolve_colleague_and_nothing_else():
    resolver = afx.FixedResolver(_resolved(GRANTEE))
    route = afx.access_router(
        member_write=afx.response(afx.GRANT_EDIT),
        members_pages=[afx.response(afx.MEMBERS_EDIT)],
    )
    access, transport = client(route, resolver=resolver)

    outcome = access.grant_access(DOC, email=afx.GRANTEE_EMAIL, perm="edit")

    assert resolver.calls == [{"email": afx.GRANTEE_EMAIL}], (
        "the address route is the SHIPPED verb, called with the address and nothing invented "
        "beside it")
    assert transport.calls[0].body["member_id"] == GRANTEE
    assert outcome.open_id == GRANTEE
    assert outcome.stored_perm == "edit"


def test_ac1_the_client_defaults_its_resolver_to_the_SHIPPED_contacts_verb():
    from larkdocio.contacts.lookup import resolve_colleague

    source = POLICY_MODULE.read_text(encoding="utf-8") + ACCESS_MODULE.read_text(encoding="utf-8")
    assert "resolve_colleague" in source
    assert resolve_colleague.__module__ == "larkdocio.contacts.lookup"


@pytest.mark.parametrize("kwargs", [
    {},                                                   # neither
    {"email": afx.GRANTEE_EMAIL, "open_id": GRANTEE},     # both
])
def test_ac1_EXACTLY_ONE_of_email_or_open_id_is_a_typed_refusal_BEFORE_any_call(kwargs):
    access, transport = client(afx.access_router())

    with pytest.raises(AccessRefusedError):
        access.grant_access(DOC, perm="view", **kwargs)

    assert transport.calls == [], "the argument fence must not spend a request"


@pytest.mark.conformance
def test_ac1_the_three_MEASURED_LEVELS_are_the_whole_accepted_set():
    assert MEMBER_PERMS == ("view", "edit", "full_access")


def test_ac1_a_perm_outside_the_measured_set_is_refused_BEFORE_any_call():
    access, transport = client(afx.access_router())

    with pytest.raises(AccessRefusedError) as excinfo:
        access.grant_access(DOC, open_id=GRANTEE, perm="owner")

    assert "full_access" in str(excinfo.value)
    assert transport.calls == []


# --------------------------------------------------------------------------- #
# AC2 — a bare display NAME is refused, typed, and the message says            #
# *give me an email*. The reason is CITED (LD-348), never re-litigated.        #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
@pytest.mark.parametrize("kwargs", [
    {"email": "Example User"},
    {"open_id": "Example User"},
    {"email": "example user at examplecorp"},
])
def test_ac2_a_BARE_NAME_is_refused_TYPED_and_BEFORE_the_network(kwargs):
    access, transport = client(afx.access_router())

    with pytest.raises(AccessRefusedError) as excinfo:
        access.grant_access(DOC, perm="view", **kwargs)

    message = str(excinfo.value)
    assert "email" in message.lower(), "the refusal must ask for an email address"
    assert transport.calls == [], "a name must never reach the wire"


@pytest.mark.conformance
def test_ac2_the_refusal_NEVER_asserts_that_the_person_DOES_NOT_EXIST():
    """LD-348's second half, binding here: a failed resolve means *unresolved here*. The
    address route's measured reach is n = 2; its behaviour for an arbitrary tenant member is
    UNMEASURED, so 'no such person' is a claim past the evidence."""
    lowered = BARE_NAME_REFUSAL.lower()
    for forbidden in ("no such person", "does not exist", "no such user", "not a real"):
        assert forbidden not in lowered, BARE_NAME_REFUSAL
    assert "unresolved" in lowered or "did not resolve" in lowered


@pytest.mark.conformance
def test_ac2_the_reason_is_CITED_not_re_argued():
    """TRANSFORMED, not deleted (LD-456; ``process/doctrine/supersession.md`` § A.1).

    **The reason is unchanged** and still binds: LD-348 settled that an address route is not a
    name route, and this refusal cites rather than re-argues it. What was superseded is *where
    the citation points*. It used to ship two of this library's own source paths — the pointers
    asserted here — at a consumer who installed a **wheel** and has no source tree to open; the
    pointers now live in the policy module's own comment, where the next maintainer looks, and
    the shipped sentence names the shipped **verb** instead. So this test still asserts that the
    reason is findable and that the issue id stays out of the shipped text — it asserts it of
    the module, which is where the citation moved to.
    """
    source = POLICY_MODULE.read_text(encoding="utf-8")
    assert "contacts/__init__.py" in source
    assert "lookup.py" in source
    # The ISSUE ID stays out of the shipped sentence and lives in the module's own comment: a
    # consumer holds only the wheel, where an issue id resolves to nothing (the consumer
    # dialect guard reddens on one). The same now goes for the file pointers — a consumer
    # cannot follow one either, which is what LD-456 corrected.
    assert "LD-348" in source
    assert "LD-348" not in BARE_NAME_REFUSAL
    assert "contacts/__init__.py" not in BARE_NAME_REFUSAL
    assert "lookup.py" not in BARE_NAME_REFUSAL


def test_ac2_an_UNRESOLVED_ADDRESS_refuses_with_the_DUAL_TRUTH_and_never_a_verdict():
    from larkdocio.contacts.lookup import UNRESOLVED_IS_UNDIFFERENTIATED
    from larkdocio.write.model.refusal import Refusal

    resolver = afx.FixedResolver(_unresolved())
    access, transport = client(afx.access_router(), resolver=resolver)

    with pytest.raises(AccessRefusedError) as excinfo:
        access.grant_access(DOC, email="nobody@example.com", perm="view")

    assert UNRESOLVED_IS_UNDIFFERENTIATED in str(excinfo.value)
    assert isinstance(_unresolved().refusal, Refusal)
    assert [c.method for c in transport.calls] == [], "an unresolved address grants nothing"


# --------------------------------------------------------------------------- #
# AC3 — the FULL LIFECYCLE in the same surface. A grant surface that cannot     #
# take a grant back is not shippable.                                          #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_ac3_the_surface_carries_ALL_FOUR_DIRECTIONS():
    for verb in ("grant_access", "update_access", "revoke_access", "list_members"):
        assert callable(getattr(DriveAccessWriteClient, verb)), verb


def test_ac3_the_UPDATE_raises_over_the_measured_PUT_and_reads_it_back():
    route = afx.access_router(
        member_write=afx.response(afx.UPDATE_RAISE),
        members_pages=[afx.response(afx.MEMBERS_AFTER_RAISE)],
    )
    access, transport = client(route)

    outcome = access.update_access(DOC, open_id=GRANTEE, perm="full_access")

    sent = transport.calls[0]
    measured = afx.request(afx.UPDATE_RAISE)
    assert sent.method == "PUT"
    assert sent.path == f"{members_path(DOC)}/{GRANTEE}"
    assert sent.body == measured["body"] == {"member_type": "openid", "perm": "full_access"}
    assert sent.params == {"type": DOCX_TYPE, "need_notification": "false"}
    assert outcome.stored_perm == "full_access" and outcome.stored is True


def test_ac3_the_DOWNGRADE_is_the_same_route_lowered_and_read_back():
    route = afx.access_router(
        member_write=afx.response(afx.UPDATE_LOWER),
        members_pages=[afx.response(afx.MEMBERS_AFTER_LOWER)],
    )
    access, transport = client(route)

    outcome = access.update_access(DOC, open_id=GRANTEE, perm="view")

    assert transport.calls[0].body["perm"] == "view"
    assert outcome.stored_perm == "view" and outcome.stored is True


@pytest.mark.conformance
def test_ac3_the_REVOKE_leaves_an_EMPTY_LIST_and_not_a_tombstone():
    route = afx.access_router(
        member_write=afx.response(afx.REVOKE),
        members_pages=[afx.response(afx.MEMBERS_AFTER_REVOKE)],
    )
    access, transport = client(route)

    outcome = access.revoke_access(DOC, open_id=GRANTEE)

    sent = transport.calls[0]
    assert sent.method == "DELETE"
    assert sent.path == f"{members_path(DOC)}/{GRANTEE}"
    assert sent.params == {"type": DOCX_TYPE, "member_type": "openid"}
    assert sent.body is None
    assert outcome.listing.members == ()
    assert outcome.stored_perm is None
    assert outcome.stored is True, "a revoke that really emptied the list is a stored revoke"


def test_ac3_a_revoke_whose_member_SURVIVES_the_read_back_reports_UNSTORED():
    route = afx.access_router(
        member_write=afx.response(afx.REVOKE),
        members_pages=[afx.response(afx.MEMBERS_FULL_ACCESS)],
    )
    access, _transport = client(route)

    outcome = access.revoke_access(DOC, open_id=GRANTEE)

    assert outcome.stored is False
    assert outcome.stored_perm == "full_access"


# --------------------------------------------------------------------------- #
# AC4 — READ the member list, and report the OWNER honestly.                    #
# --------------------------------------------------------------------------- #

def test_ac4_the_member_rows_are_TYPED_from_the_measured_shape():
    route = afx.access_router(members_pages=[afx.response(afx.MEMBERS_FULL_ACCESS)],
                              meta=afx.response(afx.META_OWNER))
    access, transport = client(route)

    listing = access.list_members(DOC)

    assert transport.calls[0].params == {"type": DOCX_TYPE}
    assert [(m.member_id, m.member_type, m.perm, m.perm_type) for m in listing.members] == [
        (GRANTEE, "openid", "full_access", "container")]
    assert listing.perm_of(GRANTEE) == "full_access"
    assert listing.perm_of("ou_nobody") is None


@pytest.mark.conformance
def test_ac4_a_FRESH_DOCUMENT_reads_EMPTY_and_the_OWNER_is_reported_anyway():
    """Leg 0b, and the trap: *a reader who checks only this route would conclude the bot holds
    nothing; that reading is wrong.* The owner is not a member row."""
    route = afx.access_router(members_pages=[afx.response(afx.MEMBERS_EMPTY)],
                              meta=afx.response(afx.META_OWNER))
    access, _transport = client(route)

    listing = access.list_members(DOC)

    assert listing.members == ()
    assert listing.owner_id == afx.BOT_OPEN_ID
    assert listing.owner_note is None


def test_ac4_the_OWNER_READ_DEGRADES_honestly_and_never_fails_the_member_read():
    def meta(_call):
        return {"code": 1061002, "msg": "forbidden"}

    route = afx.access_router(members_pages=[afx.response(afx.MEMBERS_EMPTY)], meta=meta)
    access, _transport = client(route)

    listing = access.list_members(DOC)

    assert listing.members == ()
    assert listing.owner_id is None
    assert listing.owner_note, "an unavailable owner must say why, never be synthesized"


def test_ac4_the_owner_read_can_be_DECLINED_and_then_costs_no_call():
    route = afx.access_router(members_pages=[afx.response(afx.MEMBERS_EMPTY)])
    access, transport = client(route)

    listing = access.list_members(DOC, with_owner=False)

    assert len(transport.calls) == 1
    assert listing.owner_id is None and listing.owner_note


@pytest.mark.conformance
def test_ac4_the_OMISSION_is_stated_in_the_shipped_words_as_well_as_in_the_data():
    assert "not" in OWNER_IS_NOT_A_MEMBER.lower() and "owner" in OWNER_IS_NOT_A_MEMBER.lower()
    assert OWNER_IS_NOT_A_MEMBER in DriveAccessWriteClient.list_members.__doc__
    assert MEMBER_LIST_AT_BIRTH in DriveAccessWriteClient.grant_access.__doc__


@pytest.mark.conformance
def test_ac4_the_member_family_is_V1_and_the_v2_spelling_is_FENCED_with_its_form():
    assert members_path(DOC).startswith("/open-apis/drive/v1/permissions/")
    assert "v1" in MEMBER_FAMILY_IS_V1 and "v2" in MEMBER_FAMILY_IS_V1
    assert "one spelling" in MEMBER_FAMILY_IS_V1.lower()
    assert afx.response(afx.MEMBERS_V2_404)["_raw"] == "404 page not found", (
        "not a Lark error envelope at all — plain text, which is what makes it not a route")


# --------------------------------------------------------------------------- #
# AC5 — THE COPY LEVER, DONE RIGHT: one key per call, each read back.           #
# --------------------------------------------------------------------------- #

def test_ac5_one_key_is_patched_ALONE_and_then_read_back():
    route = afx.access_router(
        public_patch=afx.response(afx.PATCH_COPY),
        public_pages=[afx.response(afx.PUBLIC_AFTER_COPY)],
    )
    access, transport = client(route)

    result = access.set_copy_permissions(DOC, copy_entity="anyone_can_view")

    patch, read_back = transport.calls
    measured = afx.request(afx.PATCH_COPY)
    assert patch.method == "PATCH"
    assert patch.path == public_path(DOC) == measured["path"].split("?")[0]
    assert patch.body == measured["body"] == {"copy_entity": "anyone_can_view"}
    assert patch.params == {"type": DOCX_TYPE}
    assert read_back.method == "GET"
    assert result.stored is True
    assert result.setting("copy_entity").stored == "anyone_can_view"


@pytest.mark.conformance
def test_ac5_TWO_keys_are_still_ONE_KEY_PER_CALL():
    """The measurement was made one key at a time; a multi-key body is **unmeasured**, so the
    op does not invent one."""
    route = afx.access_router(
        public_patch=lambda call: afx.response(
            afx.PATCH_COPY if "copy_entity" in call.body else afx.PATCH_SECURITY),
        public_pages=[afx.response(afx.PUBLIC_AFTER_SECURITY)],
    )
    access, transport = client(route)

    result = access.set_copy_permissions(
        DOC, copy_entity="anyone_can_view", security_entity="anyone_can_view")

    patches = [c for c in transport.calls if c.method == "PATCH"]
    assert len(patches) == 2
    assert [sorted(c.body) for c in patches] == [["copy_entity"], ["security_entity"]]
    assert len([c for c in transport.calls if c.method == "GET"]) == 1
    assert result.stored is True
    assert {s.key for s in result.settings} == set(COPY_LEVER_KEYS)


def test_ac5_a_value_that_did_not_STORE_reports_UNSTORED_rather_than_success():
    route = afx.access_router(
        public_patch=afx.response(afx.PATCH_COPY),
        public_pages=[afx.response(afx.PUBLIC_BASELINE)],   # copy_entity unchanged
    )
    access, _transport = client(route)

    result = access.set_copy_permissions(DOC, copy_entity="anyone_can_view")

    assert result.stored is False
    assert result.setting("copy_entity").stored == "anyone_can_edit"


@pytest.mark.conformance
def test_ac5_the_ACCEPTED_VALUE_SET_is_fenced_to_what_was_MEASURED():
    assert MEASURED_COPY_VALUES == ("anyone_can_edit", "anyone_can_view")
    assert COPY_LEVER_KEYS == ("copy_entity", "security_entity")


def test_ac5_an_unmeasured_value_is_refused_BEFORE_any_call():
    access, transport = client(afx.access_router())

    with pytest.raises(AccessRefusedError) as excinfo:
        access.set_copy_permissions(DOC, copy_entity="only_full_access")

    assert "anyone_can_view" in str(excinfo.value)
    assert transport.calls == []


def test_ac5_NO_KEY_AT_ALL_is_a_typed_refusal_and_spends_nothing():
    access, transport = client(afx.access_router())

    with pytest.raises(AccessRefusedError):
        access.set_copy_permissions(DOC)

    assert transport.calls == []


@pytest.mark.conformance
def test_ac5_the_two_NEIGHBOURS_ship_as_measured_FACTS_and_not_as_options():
    parameters = inspect.signature(DriveAccessWriteClient.set_copy_permissions).parameters
    assert "lock_switch" not in parameters, "lock_switch is READ-ONLY on this PATCH route"
    assert "external_access_entity" not in parameters
    assert "read-only" in LOCK_SWITCH_READ_ONLY.lower()
    assert "unmeasured" in LOCK_SWITCH_READ_ONLY.lower(), "other spellings are unmeasured"
    assert "91009" in EXTERNAL_ACCESS_REFUSED_HERE
    assert afx.response(afx.PATCH_LOCK_SWITCH)["code"] == 1063001
    assert afx.response(afx.PATCH_EXTERNAL_ACCESS)["code"] == 91009


@pytest.mark.conformance
def test_ac5_the_NO_SWALLOW_guarantee_is_SCOPED_TO_THIS_ROUTE():
    """D-59 — an evidence label is scoped to the route it was observed on. The invented-key
    control was **refused** here (capture ``725-``), which is what lets an accepted value be
    read as a stored value on **this** route and nowhere else."""
    assert "this route" in THE_ROUTE_DOES_NOT_SWALLOW.lower()
    assert "invented" in THE_ROUTE_DOES_NOT_SWALLOW.lower()
    assert afx.response(afx.PATCH_INVENTED_KEY)["code"] != 0, "the control was REFUSED"


# --------------------------------------------------------------------------- #
# AC6 — THE DISCLOSURE CONTRACT ships with the surface.                         #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_ac6_the_contract_says_what_the_caller_must_SUPPLY():
    text = DriveAccessWriteClient.grant_access.__doc__
    assert "email" in text and "open_id" in text
    assert BARE_NAME_REFUSAL in text


@pytest.mark.conformance
def test_ac6_the_contract_says_the_library_CANNOT_TELL_YOU_WHETHER_COPY_PASTE_WORKS():
    assert "hypothesis" in CLIPBOARD_UNOBSERVABLE.lower()
    assert "clipboard" in CLIPBOARD_UNOBSERVABLE.lower()
    assert CLIPBOARD_UNOBSERVABLE in DriveAccessWriteClient.set_copy_permissions.__doc__


@pytest.mark.conformance
def test_ac6_NOTHING_SHIPPED_CLAIMS_that_copy_paste_is_ENABLED():
    """The one thing this issue fences harder than the findings do. The answer needs a human's
    click, which has not been reported — so no shipped sentence may promise it."""
    claims = (
        "enables copy", "enables copy/paste", "makes copy/paste work", "so ⌘c works",
        "allows copying", "copy/paste will work", "unlocks copy",
    )
    corpus = (POLICY_MODULE.read_text(encoding="utf-8")
              + ACCESS_MODULE.read_text(encoding="utf-8")).lower()
    hits = [claim for claim in claims if claim in corpus]
    assert not hits, f"the surface claims an effect it cannot observe: {hits}"


@pytest.mark.conformance
def test_ac6_the_MEMBER_LIST_AT_BIRTH_states_BOTH_cases_and_neither_as_an_absolute():
    """TRANSFORMED, not deleted (LD-469; supersession doctrine A.1).

    LD-432's guard held this constant to *the constructive fact* that a fresh document's member
    list is empty. That measurement stands — and is still pinned here, capture and all — but its
    **conclusion** did not survive LD-469's re-measurement: it was taken on a document created
    with no folder, and a document filed INTO a folder inherits that folder's rows. So the guard
    now holds the constant to stating **both** cases, with the inherited-row vocabulary a
    consumer will actually see on the wire. A constant that went back to the bare absolute would
    fail this the way it used to fail on a missing capture pointer.
    """
    lowered = MEMBER_LIST_AT_BIRTH.lower()
    # The LD-432 half, unchanged: the no-folder case, and the capture it was measured in.
    assert "empty" in lowered
    assert "702" in MEMBER_LIST_AT_BIRTH or "captures/702" in MEMBER_LIST_AT_BIRTH
    # The LD-469 half: the folder case, its condition, and the word the wire uses for it.
    assert "folder_token" in MEMBER_LIST_AT_BIRTH
    assert "perm_type='container'" in MEMBER_LIST_AT_BIRTH
    assert "inherit" in lowered
    # And no unlabelled absolute: each case is stated as a case.
    assert "depends on where it was filed" in lowered


@pytest.mark.conformance
def test_ac6_D15_is_stated_in_one_sentence_and_the_library_ESCALATES_NOTHING():
    lowered = NOT_A_SCOPE_ESCALATION.lower()
    assert "never widens" in lowered or "does not widen" in lowered
    assert "console" in lowered
    source = POLICY_MODULE.read_text(encoding="utf-8") + ACCESS_MODULE.read_text(encoding="utf-8")
    for forbidden in ("request_scope", "grant_scope", "escalate"):
        assert f"def {forbidden}" not in source


# --------------------------------------------------------------------------- #
# AC7 — OWNERSHIP TRANSFER IS NOT SHIPPED, and the refusal is documented        #
# where a consumer would reach for it.                                         #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_ac7_there_is_NO_TRANSFER_OP_and_NO_TRANSFER_PARAMETER():
    verbs = [name for name in dir(DriveAccessWriteClient) if not name.startswith("_")]
    assert not [v for v in verbs if "transfer" in v.lower()], verbs
    for verb in ("grant_access", "update_access", "revoke_access", "set_copy_permissions"):
        parameters = inspect.signature(getattr(DriveAccessWriteClient, verb)).parameters
        assert not [p for p in parameters if "transfer" in p or "owner" in p], verb
    source = ACCESS_MODULE.read_text(encoding="utf-8")
    assert "transfer_owner?" not in source
    assert "/members/transfer_owner" not in source


@pytest.mark.conformance
def test_ac7_the_MEASURED_FINDING_rides_where_a_caller_would_reach_for_it():
    text = OWNERSHIP_TRANSFER_NOT_SHIPPED
    assert "delete" in text.lower() and "swallow" in text.lower()
    assert "unmeasured" in text.lower(), "the untried forms are unmeasured, not impossible"
    assert "remove_old_owner=true" in text, "the forms NOT tried are named"
    assert text in DriveAccessWriteClient.grant_access.__doc__


# --------------------------------------------------------------------------- #
# AC8 — NEGATIVE CLAIMS AND FENCES, enumerated.                                 #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
@pytest.mark.parametrize("claim", ["GROUPS_UNMEASURED", "OBJECT_TYPES_MEASURED",
                                   "TENANT_TOKEN_ONLY",
                                   "LOCK_SWITCH_READ_ONLY", "MEMBER_FAMILY_IS_V1",
                                   "OWNERSHIP_TRANSFER_NOT_SHIPPED"])
def test_ac8_every_negative_claim_ENUMERATES_or_says_UNMEASURED(claim):
    from larkdocio.drive import access

    text = getattr(access, claim).lower()
    assert "unmeasured" in text or "tried" in text, claim


@pytest.mark.conformance
def test_ac8_GROUPS_are_UNMEASURED_and_not_reported_as_refused():
    lowered = GROUPS_UNMEASURED.lower()
    assert "unmeasured" in lowered
    assert "synthetic" in lowered, "one synthetic-id call cannot attribute the refusal"
    assert "not refused" in lowered or "never refused" in lowered
    assert afx.request(afx.GROUP_SHAPE)["body"]["member_type"] == "opendepartmentid"


@pytest.mark.conformance
def test_ac8_the_TYPE_IS_FENCED_TO_WHAT_WAS_MEASURED_rather_than_by_prose():
    """TRANSFORMED, not deleted (LD-456; ``process/doctrine/supersession.md`` § A.1).

    **The rule is unchanged**: only a value this surface has measured may reach the wire, and
    the fence is *construction*, not prose. What was superseded is the fence's shape. LD-432
    achieved it by taking **no** object-type argument at all — which also made a Base grant
    impossible from outside and, worse, silent (a bare Lark ``1063001``). The fence is now the
    resolver: every verb takes ``obj_type``, exactly the measured set can be spelled, and
    anything else is refused locally. So this test still holds every verb to the fence — it
    holds them to the new one, and additionally proves the unmeasured types cannot get out.
    """
    assert DOCX_TYPE == "docx"
    for verb in ("grant_access", "update_access", "revoke_access", "list_members",
                 "set_copy_permissions"):
        parameters = inspect.signature(getattr(DriveAccessWriteClient, verb)).parameters
        assert "obj_type" in parameters, verb
        assert not {"type", "doc_type"} & set(parameters), (
            f"{verb} must take the ONE resolved argument, not Lark's raw key as well")
    assert set(WIRE_OBJECT_TYPES) == {"docx", "sheet", "bitable"}
    for unmeasured in ("folder", "file", "wiki"):
        with pytest.raises(AccessRefusedError):
            object_target(DOC, unmeasured)
    lowered = OBJECT_TYPES_MEASURED.lower()
    for named in ("sheet", "bitable", "folder", "wiki"):
        assert named in lowered, f"{named} is not named on either side of the fence"


@pytest.mark.conformance
def test_ac8_the_TENANT_TOKEN_fence_and_the_ALIASING_are_both_stated():
    lowered = TENANT_TOKEN_ONLY.lower()
    assert "tenant_access_token" in lowered and "user_access_token" in lowered
    assert "alias" in lowered, "no scope-separation claim may be drawn from this tenant"


def test_ac8_the_ABSENCES_are_DATA_rather_than_scattered_prose():
    assert GROUPS_UNMEASURED in ABSENCES
    assert OWNERSHIP_TRANSFER_NOT_SHIPPED in ABSENCES
    assert all(isinstance(text, str) and text for text in ABSENCES)


# --------------------------------------------------------------------------- #
# AC9 — the op registry rows and the PERMISSION rows.                           #
# --------------------------------------------------------------------------- #

def test_ac9_the_endpoints_are_MODULE_LEVEL_CONSTANTS_in_the_tokenised_shape():
    assert ops.PERMISSION_MEMBERS_ENDPOINT == (
        "/open-apis/drive/v1/permissions/:file_token/members")
    assert ops.PERMISSION_PUBLIC_ENDPOINT == "/open-apis/drive/v2/permissions/:file_token/public"
    assert ops.op("grant_access").endpoint == ops.PERMISSION_MEMBERS_ENDPOINT
    assert ops.op("set_copy_permissions").endpoint == ops.PERMISSION_PUBLIC_ENDPOINT


def test_ac9_MUTATES_is_DECLARED_and_a_GET_on_a_write_surface_declares_FALSE():
    assert ops.op("grant_access").mutates is True
    assert ops.op("update_access").mutates is True
    assert ops.op("revoke_access").mutates is True
    assert ops.op("set_copy_permissions").mutates is True
    assert ops.op("list_members").mutates is False


def test_ac9_the_READ_ONLY_claim_is_TRANSFORMED_AGAIN_and_the_ENUMERATION_half_still_holds():
    """D-24 once more: the reason (*a read-only claim should be checkable*) is unchanged; only
    the conclusion for the whole registry moves as ops join it — LD-467's ``create_folder`` is
    the latest, and it joins the mutating set by DECLARING itself rather than by anyone
    remembering to add it."""
    assert ops.read_only() is False
    assert ops.read_only(ops.ENUMERATION_OPS) is True
    assert {d.name for d in ops.mutating_ops()} == {
        "create_version", "grant_access", "update_access", "revoke_access",
        "set_copy_permissions", "create_folder"}


def test_ac9_the_permission_rows_land_EMPTY_WITH_THEIR_REASON():
    from larkdocio import permissions

    prefixes = {ops.PERMISSION_MEMBERS_ENDPOINT, ops.PERMISSION_PUBLIC_ENDPOINT}
    rows = [row for row in permissions.ENDPOINT_SCOPES if row[0] in prefixes]
    assert {row[0] for row in rows} == prefixes
    for _prefix, mode, scopes, reason in rows:
        assert mode in ("write", "*")
        assert scopes == (), "no scope string has ever been observed demanded here"
        assert "not guessed" in reason.lower()
        assert "documented-unverified" in reason.lower(), (
            "the honest label for a requirement asserted from documentation alone is named")


def test_ac9_NO_INVENTED_SCOPE_STRING_rides_in_on_the_new_rows():
    from larkdocio import permissions

    prefixes = {ops.PERMISSION_MEMBERS_ENDPOINT, ops.PERMISSION_PUBLIC_ENDPOINT}
    known_before = {scope.scope
                    for prefix, _m, scopes, _n in permissions.ENDPOINT_SCOPES
                    for scope in scopes if prefix not in prefixes}
    added = {scope.scope
             for prefix, _m, scopes, _n in permissions.ENDPOINT_SCOPES
             for scope in scopes if prefix in prefixes}
    assert added <= known_before, f"a scope string was authored here: {sorted(added)}"


def test_ac9_the_surface_is_reported_by_capabilities_with_its_operations():
    import larkdocio

    surface = larkdocio.capabilities(full=True)["surfaces"]["drive-access-write"]
    assert surface["mode"] == "write"
    assert set(rows.names(surface, rows.OPERATION)) == {
        "grant_access", "update_access", "revoke_access", "list_members",
        "set_copy_permissions"}
    for op in rows.call_sites(surface, rows.OPERATION):
        assert op["permissions"]["endpoints"], op["name"]


# --------------------------------------------------------------------------- #
# Gentleness + credential doctrine — the same posture the other Drive legs keep. #
# --------------------------------------------------------------------------- #

def test_every_call_passes_through_the_clients_own_LIMITER():
    route = afx.access_router(members_pages=[afx.response(afx.MEMBERS_EMPTY)],
                              meta=afx.response(afx.META_OWNER))
    access, _transport = client(route)

    before = access.limiter.acquisitions if hasattr(access.limiter, "acquisitions") else None
    access.list_members(DOC)

    assert access.api_calls == 2, "the owner leg is a call and is counted like one"
    assert before is None or access.limiter.acquisitions > before


def test_the_client_resolves_WRITE_credentials_and_never_falls_back_to_the_read_pair():
    source = ACCESS_MODULE.read_text(encoding="utf-8")
    assert "get_write_credentials" in source
    assert "get_read_credentials" not in source, (
        "this op never mixes credential pairs and never falls back across them")


def _resolved(open_id):
    from larkdocio.contacts.lookup import NameLookup, Partiality, UserRef

    return NameLookup(query=afx.GRANTEE_EMAIL, partiality=Partiality(),
                      user=UserRef(open_id=open_id, display_name="another user"))


def _unresolved():
    from larkdocio.contacts.lookup import NameLookup, Partiality
    from larkdocio.write.model.refusal import Refusal

    return NameLookup(query="nobody@example.com", partiality=Partiality(),
                      refusal=Refusal.not_found("unresolved"))
