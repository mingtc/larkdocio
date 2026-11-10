"""The OPTIONAL preflight — and the ways it is kept honest about its own certainty.

The probe that chose this mechanism also mapped what it cannot see, so most of this file is
about the second half: a check that reported a clean bill of health for a scope it never
examined would be the permissions equivalent of the bug this area exists to prevent.
"""
import inspect
import json
import pathlib

import pytest

from larkdocio import permissions as perm, preflight
from larkdocio.errors import LarkConfigError


CAPTURES = (pathlib.Path(__file__).resolve().parent.parent / "tests" / "captures"
            / "permissions-preflight-probe" / "captures")


def answer(name):
    return json.loads((CAPTURES / f"{name}.json").read_text(encoding="utf-8"))["response"]


def held_prober(scope_to_answer):
    """A fake prober driven by CAPTURED answers, keyed by scope."""
    def prober(probe):
        return scope_to_answer[probe.scope]
    return prober


#: The captured resource-error answers — what "the scope IS held" looks like per family.
HELD = {
    "docx:document:readonly": "Q4-docx-bogus-READ",
    "contact:contact.base:readonly": "Q5-contacts-bogus-READ",
}
#: The captured scope denial — what "the scope is NOT held" looks like. Rewritten per scope so
#: the body names the scope under test, exactly as Lark's own body would.
DENIED_TEMPLATE = "Q12-group-bogus-READ"


def denial_answer(scope):
    body = json.loads(json.dumps(answer(DENIED_TEMPLATE)))
    body["msg"] = f"Access denied. One of the following scopes is required: [{scope}]"
    body["error"]["permission_violations"] = [
        {"type": "action_scope_required", "subject": scope}]
    body["error"]["helps"] = [
        {"url": f"https://open.larksuite.com/app/cli_probe/auth?q={scope}"
                "&op_from=openapi&token_type=tenant",
         "description": f"Learn more about scopes and how to add them: [{scope}]"}]
    return body


# --------------------------------------------------------------------------- #
# The derive-only half — zero calls.                                          #
# --------------------------------------------------------------------------- #

def test_the_scope_set_is_derived_from_the_registry_with_no_calls():
    scopes, unknown = preflight.scopes_for_operations(["get_docx_content"])
    assert scopes == ("docx:document:readonly",)
    assert unknown == ()


def test_an_operation_needing_the_contacts_pair_derives_BOTH():
    scopes, _ = preflight.scopes_for_operations(["batch_get_user_names"])
    assert set(scopes) == {"contact:contact.base:readonly", "contact:user.base:readonly"}


def test_a_surface_qualified_name_resolves_too():
    scopes, unknown = preflight.scopes_for_operations(["docx-read.get_docx_content"])
    assert scopes == ("docx:document:readonly",) and unknown == ()


# --------------------------------------------------------------------------- #
# Cost is disclosed BEFORE it is spent. AC7.                                   #
# --------------------------------------------------------------------------- #

def test_the_call_cost_is_knowable_without_making_any_call():
    assert preflight.call_cost(["get_docx_content"]) == 1
    assert preflight.call_cost(["parse_docx_tree"]) == 0, (
        "an operation that makes no call needs no probe")


def test_the_cost_is_per_distinct_FAMILY_not_per_operation():
    """Two operations on the same family cost one call, which is the whole point of aiming the
    probe with the registry rather than probing per operation."""
    one = preflight.call_cost(["get_docx_content"])
    two = preflight.call_cost(["get_docx_content", "docx-read.get_docx_content"])
    assert one == two == 1


def test_the_reported_cost_MATCHES_what_the_check_actually_spends():
    ops = ["get_docx_content", "batch_get_user_names"]
    predicted = preflight.call_cost(ops)
    result = preflight.check_permissions(
        ops, probe=held_prober({s: answer(n) for s, n in HELD.items()}))
    assert result.calls_made == predicted, (
        "a disclosed cost that does not match the spend is worse than no disclosure")


# --------------------------------------------------------------------------- #
# The three operation-set shapes + the unknown name. AC5.                      #
# --------------------------------------------------------------------------- #

def test_an_operation_set_that_is_ENTIRELY_held():
    result = preflight.check_permissions(
        ["get_docx_content"], probe=held_prober({"docx:document:readonly": answer(HELD[
            "docx:document:readonly"])}))
    assert result.missing == ()
    assert result.ok is True
    assert [v.basis for v in result.verdicts] == ["probed"]
    assert result.verdicts[0].held is True


def test_an_operation_set_that_is_NOT_AT_ALL_held():
    result = preflight.check_permissions(
        ["get_docx_content"],
        probe=held_prober({"docx:document:readonly": denial_answer(
            "docx:document:readonly")}))
    assert result.missing == ("docx:document:readonly",)
    assert result.ok is False
    verdict = result.verdicts[0]
    assert verdict.held is False and verdict.basis == "probed"
    assert verdict.denial.scopes == ("docx:document:readonly",)
    assert verdict.denial.console_url, "the denial's console link must survive into the verdict"


def test_an_operation_set_that_is_PARTLY_held():
    result = preflight.check_permissions(
        ["get_docx_content", "batch_get_user_names"],
        probe=held_prober({
            "docx:document:readonly": answer(HELD["docx:document:readonly"]),
            "contact:contact.base:readonly": denial_answer("contact:contact.base:readonly"),
        }))
    assert result.missing == ("contact:contact.base:readonly",)
    assert result.ok is False
    by_scope = {v.scope: v for v in result.verdicts}
    assert by_scope["docx:document:readonly"].held is True
    assert by_scope["contact:contact.base:readonly"].held is False
    assert by_scope["contact:user.base:readonly"].held is None, (
        "the field-level grant is never probed, so it must stay unknown")


def test_an_UNKNOWN_operation_name_refuses_cleanly_and_does_not_guess():
    result = preflight.check_permissions(["definitely_not_an_operation"], probe=lambda p: {})
    assert result.unknown_operations == ("definitely_not_an_operation",)
    assert result.ok is False, "an unanswerable request must not read as a clean result"
    assert result.calls_made == 0
    assert any("not an operation" in spot for spot in result.blind_spots)


# --------------------------------------------------------------------------- #
# Honest about its own certainty. AC5.                                         #
# --------------------------------------------------------------------------- #

def test_every_verdict_states_its_BASIS():
    result = preflight.check_permissions(
        ["batch_get_user_names"],
        probe=held_prober({"contact:contact.base:readonly": answer(
            HELD["contact:contact.base:readonly"])}))
    for verdict in result.verdicts:
        assert verdict.basis in preflight.BASES
        if verdict.basis != "probed":
            assert verdict.held is None, (
                "only a probe may return a boolean; anything else must stay unknown")


def test_the_result_declares_itself_ADVISORY():
    result = preflight.check_permissions(["parse_docx_tree"], probe=lambda p: {})
    assert result.advisory is True
    assert result.to_dict()["advisory"] is True


def test_the_write_scope_is_DERIVED_never_probed_and_says_why():
    result = preflight.check_permissions(["docx-write.edit"], probe=lambda p: {})
    assert result.calls_made == 0, "no read may claim to have checked a write scope"
    verdict = {v.scope: v for v in result.verdicts}["docx:document"]
    assert verdict.basis == "derived" and verdict.held is None
    assert "write scope cannot be proved by any read" in verdict.note


def test_the_FIELD_LEVEL_blind_spot_is_named_in_the_result_itself():
    """The scope class that cost five days is the one this mechanism cannot see. Saying so in
    the returned object — not only in a document — is what stops a clean result being read as
    reassurance."""
    result = preflight.check_permissions(
        ["batch_get_user_names"],
        probe=held_prober({"contact:contact.base:readonly": answer(
            HELD["contact:contact.base:readonly"])}))
    spots = " ".join(result.blind_spots)
    assert "contact:user.base:readonly" in spots
    assert "FIELD-LEVEL" in spots or "field-level" in spots.lower()
    assert "SUCCEEDS" in spots or "succeeds" in spots.lower()


def test_a_probe_refused_for_a_DIFFERENT_scope_decides_nothing():
    """If the probe endpoint needs something else we lack, it cannot speak to the scope it was
    aimed at. Reporting that as "not held" would be a guess in the confident direction."""
    result = preflight.check_permissions(
        ["get_docx_content"],
        probe=held_prober({"docx:document:readonly": denial_answer("some:other:scope")}))
    verdict = result.verdicts[0]
    assert verdict.basis == "unknown" and verdict.held is None
    assert "different permission" in verdict.note


# --------------------------------------------------------------------------- #
# Never mutates, never widens. AC6.                                            #
# --------------------------------------------------------------------------- #

def test_every_probe_is_READ_ONLY_by_call_shape_inspection_not_by_trust():
    for probe in preflight.PROBES:
        assert probe.method == "GET", f"{probe.scope}: a preflight probe must be a GET"
        assert "/open-apis/" in probe.path


def test_every_probe_targets_a_deliberately_NONEXISTENT_resource():
    """Harmlessness is structural: with no real target there is nothing to read, alter or leak,
    and nothing is created that would need cleaning up."""
    for probe in preflight.PROBES:
        haystack = probe.path + json.dumps(probe.params)
        assert ("NoSuchDocument" in haystack or "preflight" in haystack), (
            f"{probe.scope}: the probe must point at a bogus id, not a real resource")


def test_every_probe_carries_the_evidence_for_its_shape():
    for probe in preflight.PROBES:
        assert probe.evidence and len(probe.evidence) > 30


def test_no_probe_exists_for_a_scope_the_evidence_says_is_UNPROBEABLE():
    probeable = {p.scope for p in preflight.PROBES}
    assert probeable.isdisjoint(set(preflight.NOT_PROBEABLE)), (
        "a scope recorded as unprobeable must not also have a probe")
    for scope, reason in preflight.NOT_PROBEABLE.items():
        assert reason and len(reason) > 30


def test_the_preflight_originates_no_write_shaped_call_and_no_scope_request():
    source = inspect.getsource(preflight)
    for forbidden in ('"POST"', "'POST'", '"PATCH"', '"PUT"', '"DELETE"',
                      "/open-apis/application/", "auth?q="):
        assert forbidden not in source, (
            f"the preflight module names {forbidden!r}; it must only ever read")


def test_the_field_level_set_comes_from_the_registry_not_a_second_list():
    assert "contact:user.base:readonly" in perm.field_level_scopes()
    assert "contact:user.base:readonly" in preflight.NOT_PROBEABLE


# --------------------------------------------------------------------------- #
# NEVER MANDATORY — and skipping it changes nothing. AC5.                       #
# --------------------------------------------------------------------------- #

def test_nothing_in_the_library_calls_the_preflight():
    """The optionality is structural, not a promise: no shipped code path invokes it, so no
    operation can have gained a required pre-check.

    Checked over the **parsed syntax tree** rather than by grepping text, because the shipped
    documentation naturally *names* the call — describing an optional check is not invoking it,
    and a text search cannot tell the two apart.
    """
    import ast

    src = pathlib.Path(preflight.__file__).parent
    offenders = []
    for path in sorted(src.rglob("*.py")):
        if path.name == "preflight.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name == "check_permissions":
                offenders.append(f"{path.relative_to(src)}:{node.lineno}")
    assert not offenders, (
        f"these call sites invoke the preflight, making it mandatory somewhere: {offenders}")


def test_with_the_preflight_NEVER_CALLED_every_real_refusal_still_fires_identically():
    """The contract that makes the preflight safe to ignore: the uniform refusal is produced by
    the shared error factory, which knows nothing about this module."""
    from larkdocio import errors

    body = answer("Q12-group-bogus-READ")
    err = errors.api_error("x", code=body["code"], msg=body["msg"], body=body)
    assert isinstance(err, errors.LarkPermissionError)
    assert err.denial.scopes == ("contact:group:readonly",)
    assert "preflight" not in inspect.getsource(errors)


def test_the_check_is_json_serializable_end_to_end():
    result = preflight.check_permissions(
        ["get_docx_content", "docx-write.edit"],
        probe=held_prober({"docx:document:readonly": answer(
            HELD["docx:document:readonly"])}))
    payload = result.to_dict()
    assert json.loads(json.dumps(payload)) == payload


# --------------------------------------------------------------------------- #
# Regression: the default (non-injected) probe client must actually be usable.  #
# --------------------------------------------------------------------------- #

def test_the_default_probe_client_is_fully_wired_and_really_sends():
    """A regression test for a bug every offline test above was blind to.

    Each test that exercises ``check_permissions`` injects a ``probe``, so the real client was
    never constructed — and it was missing the attributes the shared transport skeleton
    documents as the subclass's own responsibility (``_base`` / ``_urlopen`` / ``_timeout`` /
    ``_token``). It raised ``AttributeError`` on the first real call, which only a live run
    surfaced. This builds the real client with an injected socket, so the wiring is proven
    without the network.
    """
    import json as _json

    sent = {}

    class _Resp:
        status = 200

        def read(self):
            return _json.dumps({"code": 99992402, "msg": "field validation failed"}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout=None):
        sent["url"] = req.full_url
        sent["method"] = req.get_method()
        sent["auth"] = req.get_header("Authorization")
        return _Resp()

    client = preflight._PreflightProbeClient(
        "cli_test", "secret", domain="larksuite.com", urlopen=fake_urlopen)
    for attribute in ("_base", "_urlopen", "_timeout", "_token"):
        assert hasattr(client, attribute), (
            f"the shared transport requires the subclass to set {attribute}")
    client._token = "tenant-token-stub"  # skip the token mint; this asserts the send path

    answer_body = client.probe(preflight.PROBES[0])
    assert answer_body["code"] == 99992402
    assert sent["method"] == "GET", "a preflight probe must go out as a GET"
    assert sent["url"].startswith("https://open.larksuite.com/open-apis/docx/v1/documents/")
    assert "NoSuchDocument" in sent["url"], "it must target the bogus id, not a real document"


def test_the_probe_client_honours_the_api_domain():
    client = preflight._PreflightProbeClient("cli_test", "secret", domain="feishu.cn")
    assert "feishu.cn" in client._base


# --------------------------------------------------------------------------- #
# THE EMPTY ANSWER. An operation whose requirement nobody ever observed used to  #
# come back verdicts=() blind_spots=() — the one shape this whole module exists  #
# to prevent, on the boolean an integrator gates a deploy on.                   #
# --------------------------------------------------------------------------- #

#: A prober that answers "held" for every probeable family, from the captures.
ALL_HELD = held_prober({scope: answer(capture) for scope, capture in HELD.items()})

#: The two operations the report measured: the library HAS them, they reach Lark, and the
#: registry records only *why nobody knows* what they need.
UNMEASURED_OPERATIONS = (
    "drive-files-write.put_file_in_folder",
    "drive-access-write.grant_access",
)


def test_an_operation_whose_requirement_was_NEVER_OBSERVED_is_a_blind_spot():
    """The reported defect. These two derive no scope at all, so before this they fell between
    the per-scope loop and the unknown-operation loop and contributed to neither list."""
    result = preflight.check_permissions(list(UNMEASURED_OPERATIONS), probe=ALL_HELD)
    assert result.verdicts == (), "neither operation derives a scope — that is the premise"
    assert result.unknown_operations == (), "the library HAS both; they are not typos"
    for operation in UNMEASURED_OPERATIONS:
        assert any(operation in spot and "no requirement has been observed" in spot
                   for spot in result.blind_spots), (
            f"{operation} answered empty with nothing said about it: "
            f"{result.blind_spots}")


def test_the_unknown_operation_control_still_populates_and_is_a_DIFFERENT_reason():
    """The positive control from the report: the machinery always worked, the blind spots were
    simply never emitted for the class above. Both must stay distinguishable."""
    result = preflight.check_permissions(["not_a_real_operation"], probe=ALL_HELD)
    assert result.unknown_operations == ("not_a_real_operation",)
    assert any("not an operation this library has" in spot for spot in result.blind_spots)
    assert not any("no requirement has been observed" in spot for spot in result.blind_spots)


def test_NO_OPERATION_IN_THE_INVENTORY_can_answer_with_both_lists_empty():
    """The general rule, not the two measured cases: for **every** operation that reaches Lark,
    the answer carries at least one verdict or at least one blind spot. An empty pair is the
    false-reassurance shape, and no member of the inventory may produce it."""
    inventory = perm.operation_inventory()
    assert len(inventory) > 100, "the inventory itself must be non-trivial for this to mean much"
    silent = []
    for (surface_id, name), _endpoints in inventory:
        result = preflight.check_permissions([f"{surface_id}.{name}"], probe=ALL_HELD)
        if not result.verdicts and not result.blind_spots:
            silent.append(f"{surface_id}.{name}")
    assert silent == [], f"these answered empty-and-silent: {silent}"


def test_an_operation_THAT_REACHES_NO_ENDPOINT_says_so_rather_than_answering_blank():
    """The other half of honesty: a local operation genuinely needs nothing, and saying "no
    requirement has been observed" about it would be false in the opposite direction. It states
    its own emptiness instead — measured, not unknown."""
    result = preflight.check_permissions(["parse_docx_tree"], probe=ALL_HELD)
    requirement = {r.operation: r for r in result.requirements}["parse_docx_tree"]
    assert requirement.state == "no-api-call"
    assert requirement.endpoints == ()
    assert "no Lark" in requirement.note
    assert not any("no requirement has been observed" in spot for spot in result.blind_spots)


def test_EVERY_operation_the_library_has_states_which_kind_of_empty_it_is():
    """The total form of the rule, across the whole registry rather than the API-using subset:
    no operation may come back with nothing said about it in any of the three places."""
    rows = perm.permission_registry()
    silent = []
    for surface_id, name in rows:
        result = preflight.check_permissions([f"{surface_id}.{name}"], probe=ALL_HELD)
        stated = {r.operation for r in result.requirements}
        if not (result.verdicts or result.blind_spots) and not stated:
            silent.append(f"{surface_id}.{name}")
    assert silent == []


def test_the_requirement_carries_the_registry_s_OWN_recorded_reasons():
    """The nine paragraphs already written down for these two endpoints are the evidence; the
    answer points at them instead of re-stating an empty list."""
    result = preflight.check_permissions(
        ["drive-access-write.grant_access"], probe=ALL_HELD)
    requirement = result.requirements[0]
    assert requirement.state == "unmeasured"
    assert requirement.endpoints, "it reaches Lark; that is why the empty answer was dangerous"
    assert requirement.unknown_requirements, "the recorded reasons travel with the answer"
    assert any("no scope string has ever been observed" in reason
               for reason in requirement.unknown_requirements)


# --------------------------------------------------------------------------- #
# A SURFACE ID refuses instead of no-opping — it is the vocabulary the rest of  #
# the library teaches, so silence on it is the worst possible answer.           #
# --------------------------------------------------------------------------- #

def test_a_SURFACE_ID_refuses_and_says_what_to_pass_instead():
    with pytest.raises(LarkConfigError) as caught:
        preflight.check_permissions(["docx-read"], probe=ALL_HELD)
    message = str(caught.value)
    assert "docx-read" in message
    assert "surface" in message.lower()
    assert "docx-read.get_docx_content" in message, (
        "the refusal must name a spelling that works, not merely reject one that does not")


def test_the_surface_id_refusal_reaches_the_DERIVE_ONLY_half_too():
    """``scopes_for_operations`` and ``call_cost`` resolve the same names, so a spelling that is
    refused by one and silently dropped by the other would be a second version of the bug."""
    for call in (preflight.scopes_for_operations, preflight.call_cost):
        with pytest.raises(LarkConfigError):
            call(["sheets-write"])


@pytest.mark.parametrize("spelling", ["get_docx_content", "docx-read.get_docx_content"])
def test_the_two_ACCEPTED_spellings_still_resolve(spelling):
    result = preflight.check_permissions([spelling], probe=ALL_HELD)
    assert [v.scope for v in result.verdicts] == ["docx:document:readonly"]


def test_an_unknown_STRING_is_still_reported_not_raised():
    """Only a surface id raises. A typo stays a clean, reported refusal — unchanged."""
    result = preflight.check_permissions(["get_docx_contents"], probe=ALL_HELD)
    assert result.unknown_operations == ("get_docx_contents",)


# --------------------------------------------------------------------------- #
# JSON — the library's other self-description surface has always been           #
# serializable; this one says how, on the class.                                #
# --------------------------------------------------------------------------- #

def test_the_whole_ANSWER_round_trips_through_json_including_its_blind_spots():
    result = preflight.check_permissions(
        ["get_docx_content", "docx-write.edit"] + list(UNMEASURED_OPERATIONS),
        probe=ALL_HELD)
    payload = json.loads(json.dumps(result.to_dict()))
    for field in ("operations", "verdicts", "calls_made", "advisory", "missing", "ok",
                  "blind_spots", "unknown_operations", "requirements"):
        assert field in payload, f"a caller reads {field}; the payload must carry it"
    assert payload["blind_spots"], "the field this fix exists for must survive the round trip"
    assert payload["requirements"][0]["operation"] == "get_docx_content"


def test_a_single_VERDICT_round_trips_on_its_own():
    result = preflight.check_permissions(["get_docx_content"], probe=ALL_HELD)
    verdict = result.verdicts[0]
    assert json.loads(json.dumps(verdict.to_dict()))["scope"] == "docx:document:readonly"


@pytest.mark.parametrize("name", ["PermissionCheck", "ScopeVerdict", "OperationRequirement"])
def test_the_json_ROUTE_is_documented_on_the_class_itself(name):
    """A serializable object whose route lives only in a test is not documented."""
    cls = getattr(preflight, name)
    doc = cls.__doc__ or ""
    assert "to_dict" in doc and "json" in doc.lower(), (
        f"{cls.__name__} must say on itself how it becomes JSON")


def test_OK_cannot_be_read_alone_and_the_docstring_says_so_first():
    doc = preflight.PermissionCheck.ok.__doc__ or ""
    assert "blind_spots" in doc
    assert "meaningless" in doc.lower(), (
        "the sentence a consumer meets before the boolean must be unmissable")


def test_the_shipped_guide_reads_ok_TOGETHER_WITH_blind_spots():
    from larkdocio import guide

    text = guide(full=True)
    assert "blind_spots" in text
    recipe = text[text.index("check_permissions"):]
    window = recipe[:6000]
    assert ".ok" in window and "blind_spots" in window, (
        "the recipe must show the two read together, not the boolean alone")
