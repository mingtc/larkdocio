# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""ONE uniform permission-refusal shape, on every surface — and the distinction that is the
whole point: **a scope denial must never present as an absence.**

Why this file is the centre of gravity rather than a checkbox
------------------------------------------------------------
A missing **field-level** contacts grant once presented for five days as a data-range
problem, because the call it broke returned a **success** whose name fields were null and the
resolver quietly omitted them. Three outcomes have to stay three:

1. **a scope denial** — I could not look;
2. **a genuine absence** — I looked, and the answer is no;
3. **a success with empty fields** — I looked, I was answered, and the answer was hollowed out
   by a grant I do not hold. This is the one that looks like success, and it is the one that
   cost the five days.

Every fixture below is a **captured** Lark body — real ``code``/``msg`` pairs from the probe
rounds committed under ``dev/``, not synthetic ones.
"""
import json
import pathlib

import pytest

from larkdocio import errors, permissions as perm
from larkdocio.common import transport


CAPTURES = [
    pathlib.Path(__file__).resolve().parent.parent / "tests" / "captures" / "permissions-preflight-probe"
    / "captures",
    pathlib.Path(__file__).resolve().parent.parent / "tests" / "captures" / "name-lookup-spike" / "captures",
    pathlib.Path(__file__).resolve().parent.parent / "tests" / "captures" / "name-lookup-spike" / "reprobe"
    / "captures",
]


def capture(name):
    """One committed probe capture's response body, by probe name."""
    for directory in CAPTURES:
        path = directory / f"{name}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))["response"]
    raise AssertionError(f"no committed capture named {name!r}")


# --------------------------------------------------------------------------- #
# The shape itself.                                                            #
# --------------------------------------------------------------------------- #

def test_a_captured_denial_body_yields_a_permission_denial_carrying_the_exact_scope():
    body = capture("Q12-group-bogus-READ")
    denial = perm.denial_from(body.get("code"), body.get("msg"), body=body)
    assert denial is not None
    assert denial.scopes == ("contact:group:readonly",)
    assert denial.code == 99991672
    assert denial.msg == body["msg"], "Lark's msg must survive VERBATIM"


def test_the_console_deep_link_survives_into_the_detail_WHEN_the_body_carries_one():
    body = capture("Q1-application-self-READ")
    denial = perm.denial_from(body.get("code"), body.get("msg"), body=body)
    assert denial.console_url and denial.console_url.startswith("https://")
    assert "auth?q=" in denial.console_url
    assert denial.console_url in denial.detail()


def test_a_body_with_NO_help_url_is_handled_without_a_placeholder():
    """The amplifier's requirement: absence is handled, never papered over. Nothing is
    synthesized — a console URL we did not receive is simply not claimed."""
    body = dict(capture("Q12-group-bogus-READ"))
    body["error"] = {k: v for k, v in body["error"].items() if k != "helps"}
    denial = perm.denial_from(body.get("code"), body.get("msg"), body=body)
    assert denial.console_url is None
    detail = denial.detail()
    for placeholder in ("None", "unknown", "n/a", "N/A", "TODO", "<"):
        assert placeholder not in detail, f"a missing console URL leaked {placeholder!r}"
    assert "contact:group:readonly" in detail


def test_multiple_required_scopes_are_all_carried_not_just_the_first():
    body = capture("Q2-application-scopes-READ")
    denial = perm.denial_from(body.get("code"), body.get("msg"), body=body)
    assert len(denial.scopes) == 2, denial.scopes
    for scope in denial.scopes:
        assert scope in denial.detail()


def test_the_scope_is_recovered_from_the_MSG_when_no_structured_violation_exists():
    """Not every surface hands back a parsed body — the SDK path gives ``code``/``msg`` only.
    Lark puts the scope list in the message text too, so the shape does not depend on getting
    the structured half."""
    body = capture("Q12-group-bogus-READ")
    denial = perm.denial_from(body["code"], body["msg"], body=None)
    assert denial.scopes == ("contact:group:readonly",)
    assert denial.console_url is None


def test_the_detail_can_RENDER_the_credential_pair_clause():
    """The rendering half only. Note what this does NOT prove — see the tests below, which
    drive a real client instead. An earlier version of this file stopped here and passed
    ``credential_env`` in itself, so it proved the clause can be *rendered* while no shipped
    call site *supplied* it: four of the five required elements arrived on every real denial.
    That is the same inject-the-thing-under-test blind spot that hid the probe client's missing
    attributes, so the funnel tests below are the ones that matter."""
    body = capture("Q12-group-bogus-READ")
    denial = perm.denial_from(body["code"], body["msg"], body=body,
                             credential_env=("LARK_READ_APP_ID", "LARK_READ_APP_SECRET"))
    assert "LARK_READ_APP_ID" in denial.detail()


def test_the_detail_carries_the_fallback_that_still_works_when_there_is_one():
    denial = perm.denial_from(
        99991672, "Access denied. One of the following scopes is required: "
                  "[contact:user.base:readonly]", body=None)
    assert denial.fallback, "a denial on a degrading scope must name what still works"
    assert denial.fallback in denial.detail()


def test_a_denial_on_a_NON_degrading_scope_claims_no_fallback():
    """Honesty in the other direction: inventing a fallback for a scope that has none would
    send a caller down a path that cannot work."""
    denial = perm.denial_from(
        99991672, "Access denied. One of the following scopes is required: [docx:document]",
        body=None)
    assert denial.fallback is None
    assert "fallback" not in denial.detail().lower()


# --------------------------------------------------------------------------- #
# The distinction — three outcomes, three answers. AC3.                        #
# --------------------------------------------------------------------------- #

def test_a_genuine_ABSENCE_is_not_classified_as_a_permission_denial():
    """Every captured bogus-id read on a family we DO hold is a genuine absence. None of them
    may classify as a scope denial, or the shape means nothing."""
    for name in ("Q4-docx-bogus-READ", "Q5-contacts-bogus-READ", "Q6-sheets-bogus-READ",
                 "Q8-wiki-bogus-READ", "Q9-board-bogus-READ"):
        body = capture(name)
        assert perm.denial_from(body.get("code"), body.get("msg"), body=body) is None, (
            f"{name} is a resource error and must NOT read as a permission denial")


def test_the_two_details_DIFFER_for_a_denial_and_an_absence_on_the_SAME_family():
    """The assertion whose absence cost five days, at its sharpest: same endpoint family, one
    scope denial and one genuine absence, and they must not be reported alike."""
    denied = capture("Q12-group-bogus-READ")
    absent = capture("Q5-contacts-bogus-READ")
    denial = perm.denial_from(denied["code"], denied["msg"], body=denied)
    assert denial is not None
    assert perm.denial_from(absent["code"], absent["msg"], body=absent) is None
    assert denial.detail() != absent.get("msg")


def test_a_SUCCESS_with_hollowed_out_fields_is_not_reported_as_an_absence():
    """The third case, and the one that actually happened: ``code`` 0, the call answered, and
    the fields a field-level grant governs came back empty. It must be classified as a
    SUSPECTED PERMISSION GAP naming that grant — never as "there is no such user"."""
    hollow = {"code": 0, "msg": "success",
              "data": {"items": [{"open_id": "ou_real000000000000000000000000001",
                                  "name": None},
                                 {"open_id": "ou_real000000000000000000000000002",
                                  "name": ""}]}}
    gap = perm.suspected_field_level_gap(
        hollow, requested_ids=["ou_real000000000000000000000000001",
                               "ou_real000000000000000000000000002"])
    assert gap is not None, (
        "a success whose governed fields are all empty must be flagged, not read as absence")
    assert "contact:user.base:readonly" in gap.scopes
    assert gap.code == 0, "the honest record is that Lark reported success"
    detail = gap.detail()
    assert "succeed" in detail.lower() or "success" in detail.lower()


def test_a_genuinely_POPULATED_success_is_NOT_flagged_as_a_permission_gap():
    """The false-positive direction. Using the real captured body: names came back, so there
    is no gap and nothing may be claimed."""
    body = capture("R0-users-batch-READ")
    ids = [item["open_id"] for item in body["data"]["items"]]
    assert perm.suspected_field_level_gap(body, requested_ids=ids) is None


def test_a_PARTIALLY_populated_success_is_not_flagged_either():
    """One id resolving and another not is an ordinary absence (an id outside the app's
    contacts range, or a bot). Flagging it would cry wolf on the commonest real shape."""
    partial = {"code": 0, "msg": "success",
               "data": {"items": [{"open_id": "ou_a", "name": "Someone Real"}]}}
    assert perm.suspected_field_level_gap(
        partial, requested_ids=["ou_a", "ou_b"]) is None


# --------------------------------------------------------------------------- #
# One shape, every surface — routed through the shared seam. AC2 + AC4.        #
# --------------------------------------------------------------------------- #

def test_the_shared_error_factory_returns_the_PERMISSION_type_for_a_denial():
    body = capture("Q12-group-bogus-READ")
    err = errors.api_error("Failed to list group members: Code: 99991672, Msg: x",
                           code=body["code"], msg=body["msg"], body=body)
    assert isinstance(err, errors.LarkPermissionError)
    assert isinstance(err, errors.LarkAPIError), "must stay catchable as an API error"
    assert err.denial.scopes == ("contact:group:readonly",)


def test_the_shared_error_factory_leaves_an_ordinary_failure_ALONE():
    body = capture("Q4-docx-bogus-READ")
    err = errors.api_error("Failed to get docx document: Code: 99992402, Msg: x",
                           code=body["code"], msg=body["msg"], body=body)
    assert isinstance(err, errors.LarkAPIError)
    assert not isinstance(err, errors.LarkPermissionError)


def test_a_rate_limit_is_still_a_rate_limit_and_not_a_permission_problem():
    err = errors.api_error("throttled", code=errors.RATE_LIMIT_CODE, msg="too many")
    assert isinstance(err, errors.LarkRateLimitError)
    assert not isinstance(err, errors.LarkPermissionError)


def test_the_message_stays_BYTE_IDENTICAL_so_existing_routing_is_untouched():
    """The library routes some operator-facing behavior on message substrings, so the new type
    must not alter ``str(err)``."""
    body = capture("Q12-group-bogus-READ")
    message = "Failed to list group members: Code: 99991672, Msg: whatever"
    err = errors.api_error(message, code=body["code"], msg=body["msg"], body=body)
    assert str(err) == message


def test_the_raw_http_transport_seam_raises_the_permission_type():
    """Every raw-HTTP surface (both write engines, the comments client) funnels non-zero codes
    through this one function, which is what makes the shape uniform rather than repeated."""
    body = capture("Q12-group-bogus-READ")
    with pytest.raises(errors.LarkPermissionError) as caught:
        transport.raise_for_lark_code(body, context="probe")
    assert caught.value.denial.scopes == ("contact:group:readonly",)


def test_every_api_using_call_site_reaches_a_denial_through_a_SHARED_seam():
    """AC4, derived from the permission registry rather than hand-listed: every module that
    owns an API-using call site must build its Lark-code errors through the shared factory, so
    a new operation cannot ship a non-conforming denial.

    Derived: the module set comes from the registry's own ``projected_from`` values, not from a
    list in this test.
    """
    sites = perm.nonconforming_denial_sites()
    assert not sites, (
        "these modules own an API-using call site but construct a Lark-code error directly "
        "instead of through larkdocio.errors.api_error / api_error_as / raise_for_lark_code, "
        f"so their denials would not carry the uniform shape: {sites} "
        "(module -> the line numbers to look at)")


def test_the_coverage_check_bites_RED_on_a_non_conforming_denial_path():
    """Proven red: a module that raises the base error type for a Lark code is reported."""
    offenders = perm.nonconforming_denial_modules(
        sources={"larkdocio.made_up": 'raise LarkAPIError("x", code=code, msg=msg)'})
    assert offenders == ["larkdocio.made_up"], offenders


def test_the_coverage_check_greens_on_a_conforming_path():
    offenders = perm.nonconforming_denial_modules(
        sources={"larkdocio.fine": "raise api_error(msg, code=code, msg=msg, body=resp)"})
    assert offenders == []


def test_the_coverage_check_greens_on_the_class_preserving_factory():
    """``api_error_as`` is the second door and is conforming: it classifies through the same
    seam, and only the CLASS it wraps the answer in comes from the surface."""
    offenders = perm.nonconforming_denial_modules(sources={
        "larkdocio.fine": "raise api_error_as(MediaUploadError, m, code=code, msg=msg, "
                          "body=resp, credential_env=WRITE_ENV)"})
    assert offenders == []


# --------------------------------------------------------------------------- #
# LD-644 — the two blind spots the LD-200 regex had, each of which alone made    #
# the check answer `[]` over the whole library.                                 #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("subclass", [
    "LarkRateLimitError",              # a direct subclass, in common/errors.py
    "MediaUploadError",                # a surface's own family, two levels down
    "DriveFileChunkedUploadError",     # three levels down, with its own __init__
    "LarkSpreadsheetUnreadableError",  # a subclass with an extra attribute
])
def test_the_detector_sees_a_code_carrying_raise_of_a_SUBCLASS(subclass):
    """**Blind spot 1 — the literal name.** ``LarkAPIError`` is a family, and every member of
    it can carry a Lark ``code``. The shipped regex matched the base name only, so all 15 real
    bypassing sites — every one of them a subclass — were invisible and the guard reported no
    offenders over 29 modules.
    """
    offenders = perm.nonconforming_denial_modules(
        sources={"larkdocio.made_up": f'raise {subclass}("x", code=code, msg=msg)'})
    assert offenders == ["larkdocio.made_up"], offenders


def test_the_detector_sees_a_construction_whose_ARGUMENTS_NEST():
    """**Blind spot 2 — the nesting window**, and it was independent of the first: even under
    the base name, ``[^)]*`` could not cross the ``)`` of a call in the message, so the pattern
    stopped matching and the site passed SILENTLY.

    This is the same defect LD-210 AC9 found and fixed in
    ``permissions._omits_the_credential_pair`` — in this same file, thirty lines away — and the
    fix was not carried to its twin. Nesting is irrelevant to a walk, at any depth.
    """
    nested = 'raise LarkAPIError(f"the read of {name(token)} failed", code=code, msg=msg)'
    assert perm.nonconforming_denial_modules(sources={"larkdocio.made_up": nested}) == \
        ["larkdocio.made_up"]
    # And the pattern that shipped genuinely did not match it — the false negative is measured
    # here, not asserted from memory.
    import re
    shipped = re.compile(r"raise\s+LarkAPIError\s*\([^)]*\bcode\s*=", re.DOTALL)
    assert shipped.search(nested) is None


def test_the_detector_sees_a_BUILDER_that_is_not_itself_a_raise():
    """The rule is *build*, not *raise*: a helper that assembles the exception and a caller
    that raises its return value bypasses the factory exactly as squarely.

    Not hypothetical — ``sheets/client.py``'s ``_all_skipped`` is that shape, and a raise-only
    check called it conforming.
    """
    builder = ("def _all_skipped(read):\n"
               "    return LarkSpreadsheetUnreadableError('x', code=c, msg=m, skips=s)\n")
    assert perm.nonconforming_denial_modules(sources={"larkdocio.made_up": builder}) == \
        ["larkdocio.made_up"]


def test_the_detector_reports_WHERE_not_just_that():
    """The population is derivable, so the guard names the lines to look at rather than
    handing back a boolean somebody has to re-derive an enumeration from."""
    sites = perm.nonconforming_denial_sites(sources={
        "larkdocio.made_up": "x = 1\nraise MediaUploadError('a', code=c)\n"
                             "y = 2\nraise MediaDownloadError('b', code=c)\n"})
    assert sites == {"larkdocio.made_up": (2, 4)}


def test_an_UNPARSEABLE_module_is_an_offender_rather_than_a_silent_pass():
    """A check that cannot read a source must not answer "no offenders" — the same posture its
    twin ``_omits_the_credential_pair`` takes."""
    sites = perm.nonconforming_denial_sites(sources={"larkdocio.made_up": "def ("})
    assert sites == {"larkdocio.made_up": (perm.UNPARSEABLE_SOURCE,)}


def test_the_class_graph_is_WALKED_and_reaches_every_shipped_api_error_subclass():
    """The names come from ``__subclasses__`` transitively, after importing the denial-owning
    modules — not from a list anybody maintains. Spot-checked at three depths."""
    names = perm.api_error_class_names()
    assert "LarkAPIError" in names
    assert {"LarkRateLimitError", "LarkPermissionError"} <= names  # depth 1, common/errors.py
    assert {"BaseMediaError", "DriveFileError"} <= names            # depth 1, a surface's own
    assert {"MediaTokenNotFoundError", "DriveFileChunkedUploadError"} <= names  # depth 3
    # Derived, so it cannot be a stale list: every subclass the runtime knows is present.
    from larkdocio.errors import LarkAPIError
    seen, stack = set(), [LarkAPIError]
    while stack:
        cls = stack.pop()
        if cls in seen:
            continue
        seen.add(cls)
        stack.extend(cls.__subclasses__())
    assert {cls.__name__ for cls in seen} == set(names)


def test_where_the_guards_reach_STOPS_is_labelled_and_every_module_there_is_cleared():
    """AC6's narrowing, made visible to the suite and not only to a reader.

    The guard's module set is DERIVED from the registry, which is why a new API-using operation
    cannot escape it — and is also why a module that builds a Lark-code error while owning no
    registry-projected call site is outside it. The invariant sentence reaches further than the
    check does, so the gap is written down, reasoned per module, and held here.

    **This is the bite:** a NEW construction outside the guard's reach reddens this test and has
    to be triaged, instead of arriving in a place nothing looks at — which is exactly the
    failure this whole issue was.
    """
    found = perm.constructions_outside_the_guards_reach()
    assert set(found) == set(perm.CLEARED_OUTSIDE_THE_GUARDS_REACH), (
        "a module builds a Lark-code error outside the guard's derived module set and is not "
        "recorded as a cleared exception (or a recorded one no longer does). Triage it and "
        "either route it through larkdocio.errors.api_error / api_error_as, or add it to "
        "permissions.CLEARED_OUTSIDE_THE_GUARDS_REACH with the reason it is cleared.\n"
        f"  found   : {sorted(found)}\n"
        f"  declared: {sorted(perm.CLEARED_OUTSIDE_THE_GUARDS_REACH)}")
    for module, reason in perm.CLEARED_OUTSIDE_THE_GUARDS_REACH.items():
        assert reason.strip(), f"{module} is listed with no reason, which is a silent exception"


def test_the_labelled_exception_is_a_DISCLOSURE_and_does_not_widen_the_guard():
    """The two answer different questions and must not be conflated: the guard says *is any
    denial-owning module non-conforming* (it must be empty), and the disclosure says *where does
    the guard not look* (it is expected to be non-empty and cleared)."""
    assert perm.nonconforming_denial_sites() == {}
    assert perm.constructions_outside_the_guards_reach(), (
        "an empty disclosure would mean the walk found nothing at all — more likely a broken "
        "walk than a library with no factory of its own")
    assert not (set(perm.constructions_outside_the_guards_reach())
                & set(perm.denial_owning_modules())), \
        "the disclosure must cover only what the guard does NOT"


def test_a_non_error_class_of_the_same_shape_is_not_flagged():
    """Only the api-error family is the detector's business: an ordinary call carrying a
    ``code`` keyword is not a refusal and is not reported."""
    assert perm.nonconforming_denial_modules(
        sources={"larkdocio.fine": "record = TabSkip(sheet_id=s, code=code, msg=msg)"}) == []


def test_the_denial_codes_table_records_its_evidence_per_code():
    """The codes are classified from captures, and any code named in a document but never
    captured says so rather than passing as observed."""
    assert perm.DENIAL_CODES
    for code, record in perm.DENIAL_CODES.items():
        assert record["verification"] in perm.VERIFICATION_LABELS
        assert record["evidence"]
    captured = [c for c, r in perm.DENIAL_CODES.items()
                if r["verification"] == "denial-verified"]
    assert 99991672 in captured


def test_the_two_UNCAPTURED_denial_codes_still_classify_and_are_labelled_as_unverified():
    """This project's own notes name three permission-denied codes. Only ``99991672`` has ever
    been seen on the wire here.

    Both halves matter. The other two must still **classify** — a denial code we have never
    captured must not be silently demoted to an ordinary failure — and they must be **labelled**
    ``documented-unverified`` rather than passing as observed fact. That is the honest-unknown
    discipline applied to a code rather than to a scope.
    """
    for code in (41050, 1069303):
        assert perm.DENIAL_CODES[code]["verification"] == "documented-unverified"
        assert "never observed" in perm.DENIAL_CODES[code]["evidence"]
        assert perm.looks_like_scope_denial(
            code, "Access denied. One of the following scopes is required: [docx:document]")
        denial = perm.denial_from(
            code, "Access denied. One of the following scopes is required: [docx:document]")
        assert denial is not None and denial.scopes == ("docx:document",)
        assert denial.code == code, "the code is reported as Lark gave it, not normalised"


def test_a_denial_code_we_have_NEVER_heard_of_still_classifies_by_message_shape():
    """The robustness the message-shape check buys: a future denial code classifies correctly
    on the first encounter, rather than reaching a caller as a generic failure."""
    denial = perm.denial_from(
        4242424242,
        "Access denied. One of the following scopes is required: [some:future:scope]")
    assert denial is not None
    assert denial.scopes == ("some:future:scope",)
    assert 4242424242 not in perm.DENIAL_CODES


# --------------------------------------------------------------------------- #
# ALL FIVE ELEMENTS ARRIVE ON A REAL DENIAL — driven through the REAL funnels.  #
#                                                                              #
# These are the tests that matter for the uniform-refusal contract. Each builds  #
# a REAL client, stubs only the socket, feeds it a CAPTURED denial body, and       #
# asserts the exception the library actually raises carries every element the      #
# shipped documentation promises — including WHICH CREDENTIAL PAIR made the call,   #
# which no call site used to supply.                                                #
# --------------------------------------------------------------------------- #

#: The five elements the refusal contract promises, as the shipped documents state them.
REQUIRED_ELEMENTS = (
    "the exact missing permission",
    "Lark's verbatim code/msg",
    "the console deep link when the body supplies one",
    "which credential pair the call used",
    "the fallback that still works where one exists",
)


def _denial_body_urlopen(body):
    """A urlopen stub that answers every request with ``body`` as an HTTP 400.

    Only the socket is faked. Token minting, header construction, throttling, response
    parsing and error typing all run as they do in production, which is the entire point:
    the previous version of this contract's test bypassed all of it.
    """
    import io
    import urllib.error

    payload = json.dumps(body).encode()

    def urlopen(req, timeout=None):
        url = req.full_url
        if "tenant_access_token" in url:
            class _Ok:
                status = 200

                def read(self):
                    return json.dumps(
                        {"code": 0, "tenant_access_token": "t-stub", "expire": 7200}).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False
            return _Ok()
        raise urllib.error.HTTPError(url, 400, "Bad Request", {}, io.BytesIO(payload))

    return urlopen


def _assert_full_denial(err, expected_scope, expected_env):
    """Every element of the contract, on one real exception."""
    assert isinstance(err, errors.LarkPermissionError), type(err)
    denial = err.denial
    assert denial is not None
    assert expected_scope in denial.scopes, denial.scopes
    assert denial.code and denial.msg
    detail = denial.detail()
    assert expected_scope in detail
    assert str(denial.code) in detail and denial.msg in detail
    # THE ELEMENT THAT WAS MISSING on every shipped path.
    assert tuple(denial.credential_env) == tuple(expected_env), (
        f"the denial must name the credential pair the call used; got "
        f"{denial.credential_env!r}, expected {expected_env!r}")
    for name in expected_env:
        assert name in detail, f"{name} missing from detail(): {detail}"
    assert list(denial.to_dict()["credential_env"]) == list(expected_env), (
        "to_dict() must not render a bare [] for the credential pair")


def test_a_real_WRITE_client_denial_carries_all_five_elements(monkeypatch):
    """The raw-HTTP funnel on the WRITE pair, through ``raise_for_lark_code``."""
    from larkdocio.write.client import WriteClient

    body = json.loads(json.dumps(capture("Q12-group-bogus-READ")))
    body["msg"] = "Access denied. One of the following scopes is required: [docx:document]"
    body["error"]["permission_violations"] = [
        {"type": "action_scope_required", "subject": "docx:document"}]

    client = WriteClient("cli_w", "secret", "larksuite.com",
                         urlopen=_denial_body_urlopen(body))
    with pytest.raises(errors.LarkPermissionError) as caught:
        client.get_block("doc-1", "blk-1")
    _assert_full_denial(caught.value, "docx:document",
                        ("LARK_WRITE_APP_ID", "LARK_WRITE_APP_SECRET"))


def test_a_real_SHEETS_READ_client_denial_carries_all_five_elements(monkeypatch):
    """The same funnel on the READ pair, so the pair reported is the one actually used
    rather than a constant."""
    from larkdocio.sheets.client import SheetsReadClient

    monkeypatch.setenv("LARK_READ_APP_ID", "cli_r")
    monkeypatch.setenv("LARK_READ_APP_SECRET", "secret")
    body = json.loads(json.dumps(capture("Q12-group-bogus-READ")))
    body["msg"] = ("Access denied. One of the following scopes is required: "
                   "[docx:document:readonly]")
    body["error"]["permission_violations"] = [
        {"type": "action_scope_required", "subject": "docx:document:readonly"}]

    client = SheetsReadClient("cli_r", "secret", urlopen=_denial_body_urlopen(body))
    with pytest.raises(errors.LarkPermissionError) as caught:
        client.get_spreadsheet_meta("sheet-token")
    _assert_full_denial(caught.value, "docx:document:readonly",
                        ("LARK_READ_APP_ID", "LARK_READ_APP_SECRET"))


def test_a_real_DOCX_READER_denial_carries_all_five_elements(monkeypatch):
    """The SDK funnel — a different code path (``resp.success()`` rather than a parsed body),
    and the one a consumer meets first."""
    from larkdocio.read.client import Client

    monkeypatch.setenv("LARK_READ_APP_ID", "cli_r")
    monkeypatch.setenv("LARK_READ_APP_SECRET", "secret")

    class _Resp:
        code = 99991672
        msg = ("Access denied. One of the following scopes is required: "
               "[docx:document:readonly]")

        def success(self):
            return False

    client = Client("cli_r", "secret", "larksuite.com")
    monkeypatch.setattr(client.lark_client.docx.v1.document, "get",
                        lambda req: _Resp(), raising=False)
    with pytest.raises(errors.LarkPermissionError) as caught:
        client.get_docx_content("doc-token")
    _assert_full_denial(caught.value, "docx:document:readonly",
                        ("LARK_READ_APP_ID", "LARK_READ_APP_SECRET"))


def test_a_real_COMMENTS_client_denial_carries_all_five_elements(monkeypatch):
    """The second SDK funnel, so both ``_require_success`` helpers are covered."""
    from larkdocio.comments.client import CommentsReadClient

    monkeypatch.setenv("LARK_READ_APP_ID", "cli_r")
    monkeypatch.setenv("LARK_READ_APP_SECRET", "secret")

    class _Resp:
        code = 99991672
        msg = ("Access denied. One of the following scopes is required: "
               "[docx:document:readonly]")

        def success(self):
            return False

    class _Sdk:
        class drive:
            class v1:
                class file_comment:
                    @staticmethod
                    def list(req):
                        return _Resp()

    client = CommentsReadClient("cli_r", "secret", sdk_client=_Sdk)
    with pytest.raises(errors.LarkPermissionError) as caught:
        client.list_comments("file-token")
    _assert_full_denial(caught.value, "docx:document:readonly",
                        ("LARK_READ_APP_ID", "LARK_READ_APP_SECRET"))


def test_the_reader_reports_the_LEGACY_pair_when_that_is_what_it_resolved(monkeypatch):
    """Truthfulness over convenience: the read path accepts a legacy credential pair, so a
    denial must name the pair the call ACTUALLY used. Reporting the preferred names while the
    legacy ones are in force would send a reader to edit a variable that is not being read."""
    from larkdocio.common import auth

    monkeypatch.delenv("LARK_READ_APP_ID", raising=False)
    monkeypatch.delenv("LARK_READ_APP_SECRET", raising=False)
    monkeypatch.setenv("LARK_APP_ID", "cli_legacy")
    monkeypatch.setenv("LARK_APP_SECRET", "secret")
    assert auth.resolved_read_env() == auth.LEGACY_ENV

    monkeypatch.setenv("LARK_READ_APP_ID", "cli_r")
    monkeypatch.setenv("LARK_READ_APP_SECRET", "secret")
    assert auth.resolved_read_env() == auth.READ_ENV


def test_str_of_the_error_stays_BYTE_IDENTICAL_after_threading_the_pair(monkeypatch):
    """The clause lives in ``detail()`` / ``to_dict()``, never in the message: the library
    routes some operator-facing behaviour on message substrings, so ``str(err)`` must not move
    because a denial learned which credentials it used."""
    from larkdocio.write.client import WriteClient

    body = json.loads(json.dumps(capture("Q12-group-bogus-READ")))
    body["msg"] = "Access denied. One of the following scopes is required: [docx:document]"
    body["error"]["permission_violations"] = [
        {"type": "action_scope_required", "subject": "docx:document"}]
    client = WriteClient("cli_w", "secret", "larksuite.com",
                         urlopen=_denial_body_urlopen(body))
    with pytest.raises(errors.LarkPermissionError) as caught:
        client.get_block("doc-1", "blk-1")
    assert str(caught.value) == (
        f"get block failed: Code: {body['code']}, Msg: {body['msg']}")
    assert "LARK_WRITE_APP_ID" not in str(caught.value)


def test_EVERY_denial_owning_module_supplies_the_credential_pair():
    """The coverage direction, derived from the registry rather than hand-listed: every module
    that owns an API-using call site must hand a credential pair to the error factory, or its
    denials would arrive with four of the five promised elements."""
    offenders = perm.modules_not_supplying_credential_env()
    assert not offenders, (
        "these modules raise Lark-code errors without naming the credential pair the call "
        f"used, so their denials cannot carry all five elements: {offenders}")


def test_that_coverage_check_bites_RED_on_a_module_that_omits_the_pair():
    offenders = perm.modules_not_supplying_credential_env(
        sources={"larkdocio.sloppy": "raise_for_lark_code(resp, context=ctx)"})
    assert offenders == ["larkdocio.sloppy"], offenders
    assert perm.modules_not_supplying_credential_env(
        sources={"larkdocio.fine":
                 "raise_for_lark_code(resp, context=ctx, credential_env=READ_ENV)"}) == []


# --------------------------------------------------------------------------- #
# LD-210 AC9 — the obligation check is an AST WALK, not a paren-nesting regex. #
# --------------------------------------------------------------------------- #
#
# LD-200 shipped the check as a regex whose body — ``(?:(?!credential_env)[^()]|\([^()]*\))*`` —
# models EXACTLY ONE level of paren nesting inside the call. Its QA probed five shapes and found
# no false positives but one false NEGATIVE, needing a nesting depth no current call site has:
# at two levels the regex stops matching, the call is never examined, and a call site that omits
# the credential pair passes silently. The technique that closes it was already in the same
# module (``ast.parse`` / ``ast.walk``), which is what AC9 asks for.

#: Call shapes that MUST be reported — each omits ``credential_env``, at a different nesting
#: depth. Depth 2 is the one the regex missed.
_OMITS_THE_PAIR = {
    "depth 0": "raise_for_lark_code(resp, context=ctx)",
    "depth 1": "raise_for_lark_code(resp, context=fmt(name))",
    "depth 2": "raise_for_lark_code(resp, context=_ctx(fmt(name)))",
    "depth 3": "api_error(f'x', code=resp.code, msg=one(two(three(name))))",
    "depth 2, multi-line": (
        "raise_for_lark_code(\n"
        "    resp,\n"
        "    context=_ctx(fmt(name, sep=join(parts))),\n"
        ")"
    ),
}

#: Shapes that must NOT be reported — the must-not-bite arm, at the same depths.
_SUPPLIES_THE_PAIR = {
    "depth 0": "raise_for_lark_code(resp, context=ctx, credential_env=READ_ENV)",
    "depth 2": "raise_for_lark_code(resp, context=_ctx(fmt(name)), credential_env=READ_ENV)",
    "depth 2, pair itself nested": (
        "api_error('x', code=c, credential_env=resolved_read_env(mode(name)))"
    ),
    "the factory's own definition": (
        "def raise_for_lark_code(resp, context, credential_env=None):\n"
        "    raise LarkAPIError(context)\n"
    ),
    "no obliged call at all": "logger.info(fmt(one(two(three))))",
}


@pytest.mark.parametrize("label", sorted(_OMITS_THE_PAIR))
def test_ac9_the_obligation_check_catches_an_omission_at_ANY_paren_nesting_depth(label):
    """AC9's red proof. ``depth 2`` is the shape LD-200's QA identified as the regex's
    false-negative window; the others hold the depths that already worked, so closing the
    window cannot be paid for by losing them."""
    assert perm.modules_not_supplying_credential_env(
        sources={"larkdocio.nested": _OMITS_THE_PAIR[label]}
    ) == ["larkdocio.nested"], label


@pytest.mark.parametrize("label", sorted(_SUPPLIES_THE_PAIR))
def test_ac9_the_obligation_check_produces_NO_FALSE_POSITIVE_at_any_depth(label):
    """The must-not-bite arm, which is what LD-200's QA verified about the regex and what the
    AST walk must not give up: a definition is not a call site, a call that supplies the pair is
    fine however deeply the argument nests, and an unrelated call is not this check's business."""
    assert perm.modules_not_supplying_credential_env(
        sources={"larkdocio.fine": _SUPPLIES_THE_PAIR[label]}
    ) == [], label


def test_ac9_a_source_that_does_not_parse_is_not_silently_treated_as_clean():
    """An AST walk has a failure mode a regex does not: unparseable source. Reporting the module
    is the honest answer — a check that cannot read a file must not answer "no offenders"."""
    assert perm.modules_not_supplying_credential_env(
        sources={"larkdocio.broken": "def f(:\n"}
    ) == ["larkdocio.broken"]
