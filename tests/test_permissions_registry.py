# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""The PERMISSIONS REGISTRY guard — the per-operation scope requirement, derived.

What this module guards
-----------------------
``larkdocio.permissions`` is the ONE source of scope truth, stated **per operation** rather
than per surface, and **derived** rather than hand-listed wherever a derivation exists:

* an operation's **endpoints** come from its own code (an AST walk over the callable that
  implements it — the pinned SDK request classes it builds and the raw ``/open-apis/…``
  paths it names), so an operation that starts calling a different endpoint family moves in
  the registry with no one remembering to move it;
* an operation's **scopes** come from joining those endpoints onto the endpoint→scope table,
  which is the one irreducibly hand-listed thing here (a Lark scope string exists nowhere in
  our code) — and every row of it carries an **evidence pointer** plus a **verification
  label**, so a scope we have never seen demanded or granted is marked, not asserted;
* an operation's **credential pair** comes from the surface's own ``Credentials``, whose env
  tuples are code truth (``larkdocio.common.auth``).

The tests below are the bidirectional drift guard (the ``BLOCKS.md`` / ``SHEETS.md``
posture), both directions proven red, plus the derivation proofs: mutate the source a
"derived" field claims to derive from and the projection must move.
"""
import dataclasses
import inspect
import re

import pytest

import capability_rows as rows
from larkdocio import permissions as perm
from larkdocio.capabilities import capabilities

# LD-370 — CONFORMANCE-tier: PERMISSIONS.md is a corpus member; which Lark scopes an operation needs is external truth, measured, not chosen.
# See process/doctrine/conformance-tier.md (a lens, not a gate).
pytestmark = pytest.mark.conformance


# --------------------------------------------------------------------------- #
# The module is importable, public, and shaped as advertised.                  #
# --------------------------------------------------------------------------- #

def test_registry_is_a_public_callable_returning_rows():
    rows = perm.permission_registry()
    assert isinstance(rows, dict) and rows, "the registry must project at least one row"
    for key, row in rows.items():
        assert isinstance(key, tuple) and len(key) == 2, f"row key must be (surface, op): {key}"
        assert isinstance(row, perm.PermissionRow)


def test_every_row_is_frozen_so_no_runtime_path_can_edit_a_requirement():
    """A requirement a caller could mutate is not a requirement. Both the row and the scope
    records are frozen dataclasses, and the endpoint→scope table is a tuple."""
    for cls in (perm.Scope, perm.PermissionRow):
        assert dataclasses.fields(cls), f"{cls.__name__} must be a dataclass"
        assert cls.__dataclass_params__.frozen, f"{cls.__name__} must be frozen"
    assert isinstance(perm.ENDPOINT_SCOPES, tuple)
    row = next(iter(perm.permission_registry().values()))
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.scopes = ()


# --------------------------------------------------------------------------- #
# The derivation legs — endpoints come from code, not from a list.              #
# --------------------------------------------------------------------------- #

def test_endpoints_are_derived_from_the_sdk_request_classes_a_method_builds():
    """The docx read's own ops resolve to the endpoints their SDK request classes carry —
    nothing about them is hand-listed here or in the registry."""
    from larkdocio.read.client import Client

    assert perm.endpoints_of(Client.get_docx_content) == (
        "/open-apis/docx/v1/documents/:document_id",
        # LD-410 — the HISTORICAL read's own route, derived through the private helper the
        # public op delegates to: the walk follows ``self.<method>`` and reads the SDK
        # request class it builds, so a route reachable only under a pin is still declared.
        "/open-apis/docx/v1/documents/:document_id/blocks",
        "/open-apis/docx/v1/documents/:document_id/blocks/:block_id/children",
    )
    assert perm.endpoints_of(Client.batch_get_user_names) == (
        "/open-apis/contact/v3/users/batch",
    )


def test_endpoints_are_derived_from_raw_path_literals_too():
    """The raw-HTTP clients name their paths as literals / module constants; the same walk
    finds those, so both transports are covered by one derivation."""
    from larkdocio.write.client import WriteClient

    found = perm.endpoints_of(WriteClient.create_document)
    assert any(p.startswith("/open-apis/docx/v1/documents") for p in found), found


def test_a_function_that_touches_no_api_derives_no_endpoint():
    """The parser and the tree helpers are operations that make no call. They must derive an
    EMPTY endpoint set — that is what makes "API-using" a derived property rather than a
    judgement call, and it is what the coverage guard keys on."""
    from larkdocio.read.parser import Parser
    from larkdocio.model import tree

    assert perm.endpoints_of(Parser.parse_docx_tree) == ()
    assert perm.endpoints_of(tree.walk) == ()


def test_the_derivation_MOVES_when_the_code_it_derives_from_changes():
    """The amplifier's derivation proof: a "derived" field that does not move under its
    input's mutation is hand-listed with extra steps.

    Two synthetic operations, identical but for the endpoint family they name, must derive
    different scope sets through the SAME join.
    """
    def touches_docx():
        path = "/open-apis/docx/v1/documents/x/blocks"
        return path

    def touches_contacts():
        path = "/open-apis/contact/v3/users/batch"
        return path

    docx = perm.scopes_for_endpoints(perm.endpoints_of(touches_docx), mode="read")
    contacts = perm.scopes_for_endpoints(perm.endpoints_of(touches_contacts), mode="read")
    assert [s.scope for s in docx] == ["docx:document:readonly"]
    assert [s.scope for s in contacts] == [
        "contact:contact.base:readonly", "contact:user.base:readonly"]


def test_the_same_endpoint_derives_a_DIFFERENT_scope_per_credential_MODE():
    """The read/write app split is code truth (the auth env tuples), and the same document
    endpoint requires a different scope on each side. The join reads the mode, so the split
    cannot be lost."""
    ep = ("/open-apis/docx/v1/documents/:document_id",)
    assert [s.scope for s in perm.scopes_for_endpoints(ep, mode="read")] == [
        "docx:document:readonly"]
    assert [s.scope for s in perm.scopes_for_endpoints(ep, mode="write")] == ["docx:document"]


def test_credential_pairs_are_the_auth_env_tuples_not_a_second_list():
    from larkdocio.common.auth import READ_ENV, WRITE_ENV

    rows = perm.permission_registry()
    read_row = rows[("docx-read", "get_docx_content")]
    write_row = rows[("docx-write", "edit")]
    assert read_row.credentials_env == tuple(READ_ENV)
    assert write_row.credentials_env == tuple(WRITE_ENV)
    assert (read_row.credential_app, write_row.credential_app) == ("read", "write")


# --------------------------------------------------------------------------- #
# The join itself — the per-OPERATION answer nothing stated before.            #
# --------------------------------------------------------------------------- #

def test_the_field_level_contacts_scope_is_stated_on_the_operation_that_needs_it():
    """The five-day lesson, mechanized: the name-resolution call needs the directory scope
    AND the field-level grant, and it is the ONE docx-read operation that does. The reader's
    document ops must NOT claim them — that conflation is what made the gap invisible."""
    rows = perm.permission_registry()
    names = rows[("docx-read", "batch_get_user_names")]
    assert [s.scope for s in names.scopes] == [
        "contact:contact.base:readonly", "contact:user.base:readonly"]
    field_level = [s for s in names.scopes if s.scope == "contact:user.base:readonly"][0]
    assert field_level.field_level is True
    assert "null" in (field_level.note or "").lower(), (
        "the field-level grant's note must say what its absence looks like — a call that "
        "SUCCEEDS with null name fields")
    doc_read = rows[("docx-read", "get_docx_content")]
    assert [s.scope for s in doc_read.scopes] == ["docx:document:readonly"]


def test_an_operation_row_names_its_endpoints_so_the_join_is_auditable():
    rows = perm.permission_registry()
    assert rows[("docx-read", "batch_get_user_names")].endpoints == (
        "/open-apis/contact/v3/users/batch",)


def test_rows_carry_a_basis_and_a_derived_row_says_so():
    for row in perm.permission_registry().values():
        assert row.basis in ("derived", "hand-listed"), row
    assert perm.permission_registry()[("docx-read", "get_docx_content")].basis == "derived"


def test_every_hand_listed_row_carries_an_evidence_pointer():
    """A hand-listed row is allowed only where no derivation exists, and only with the
    capture or document that established it."""
    for key, row in perm.permission_registry().items():
        if row.basis == "hand-listed":
            assert row.evidence, f"{key}: a hand-listed row must cite its evidence"


# --------------------------------------------------------------------------- #
# Evidence + honest unknowns.                                                  #
# --------------------------------------------------------------------------- #

def test_every_scope_record_carries_evidence_and_a_verification_label():
    for prefix, mode, scopes, _note in perm.ENDPOINT_SCOPES:
        for scope in scopes:
            assert scope.evidence, f"{prefix} ({mode}) {scope.scope}: no evidence pointer"
            assert scope.verification in perm.VERIFICATION_LABELS, scope


def test_the_captured_scope_strings_cite_the_capture_that_established_them():
    """The scope strings a live probe actually saw are pinned to that probe's captures —
    not to memory."""
    captured = {s.scope: s for s in perm.scopes_for_endpoints(
        ("/open-apis/contact/v3/users/batch",), mode="read")}
    assert set(captured) == {"contact:contact.base:readonly", "contact:user.base:readonly"}
    for scope in captured.values():
        assert "name-lookup-spike" in scope.evidence, scope
        assert scope.verification == "grant-verified"


def test_a_scope_we_have_never_seen_demanded_is_labelled_not_asserted():
    """The honest-unknown discipline: where no scope string has ever been observed demanded
    for an endpoint, the registry says so — it does not invent one."""
    unknown = [
        (prefix, mode) for prefix, mode, scopes, note in perm.ENDPOINT_SCOPES
        if not scopes
    ]
    assert unknown, "at least one endpoint's requirement is genuinely unknown; say so"
    for prefix, mode, scopes, note in perm.ENDPOINT_SCOPES:
        if not scopes:
            assert note, f"{prefix} ({mode}): an empty requirement must carry its reason"
            assert (
                "no scope string" in note
                or "no scope is required" in note
            ), f"{prefix} ({mode}): say why the row is empty, verbatim: {note!r}"


def test_no_row_is_left_unlabelled():
    """The amplifier: every unverified row is LABELLED as such, and no labelled-verified row
    lacks an evidence pointer."""
    for prefix, mode, scopes, _note in perm.ENDPOINT_SCOPES:
        for scope in scopes:
            if scope.verification == "documented-unverified":
                assert "unverified" in scope.verification
            else:
                assert scope.evidence


def test_observed_denials_are_recorded_with_their_lark_code_and_capture():
    """Lark's own denial bodies name the exact scope string and hand back a console link.
    They are the strongest evidence there is, so they are catalogued — with the code, the
    capture, and whether any shipped operation needs the scope."""
    assert perm.OBSERVED_DENIALS, "the captured denial bodies are the evidence base"
    for denial in perm.OBSERVED_DENIALS:
        assert denial.scope and denial.code and denial.capture
        assert isinstance(denial.required_by_a_shipped_operation, bool)
    codes = {d.code for d in perm.OBSERVED_DENIALS}
    assert 99991672 in codes, "the scope-denied code the captures actually carry"
    scopes = {d.scope for d in perm.OBSERVED_DENIALS}
    assert {"directory:employee:search", "contact:group:readonly"} <= scopes


# --------------------------------------------------------------------------- #
# THE DRIFT GUARD — bidirectional, both directions proven red.                  #
# --------------------------------------------------------------------------- #

def test_every_api_using_operation_has_a_permission_row():
    gaps = perm.coverage_gaps()
    assert not gaps.uncovered, (
        "these operations reach the Lark API and have no permission row — add the endpoint "
        f"to the scope table (or the operation to the registry): {gaps.uncovered}")


def test_no_permission_row_names_an_operation_that_does_not_exist():
    gaps = perm.coverage_gaps()
    assert not gaps.orphans, (
        f"these permission rows name operations that no longer exist: {gaps.orphans}")


def test_no_registry_operation_is_missing_from_the_PROJECTION():
    """LD-459, the fourth field: the projection a consumer is pointed at must enumerate every
    call site the registry knows — the direction ``([], [])`` could not see. LD-475 collapsed
    that projection into ONE per-surface key, so the messages name the shape it audits now."""
    gaps = perm.coverage_gaps()
    assert not gaps.unprojected, (
        "these call sites are published under a key OTHER than the surface's one collapsed "
        f"operations key, where a consumer reading it will not find them: {gaps.unprojected}")
    assert not gaps.phantom, (
        f"these rows carry no kind a consumer can act on: {gaps.phantom}")


def test_the_coverage_check_bites_RED_on_an_uncovered_operation():
    """Direction one, proven: an API-using operation with no row reddens the SAME check that
    guards, not a look-alike."""
    truth = perm.permission_registry()
    inventory = dict(perm.operation_inventory())
    inventory[("docx-read", "brand_new_api_using_op")] = ("/open-apis/docx/v1/documents",)
    gaps = perm.coverage_gaps(rows=truth, inventory=inventory)
    assert gaps.uncovered == [("docx-read", "brand_new_api_using_op")]
    assert not gaps.orphans


def test_the_coverage_check_bites_RED_on_a_row_whose_operation_vanished():
    """Direction two, proven: a row that outlives its operation reddens."""
    inventory = dict(perm.operation_inventory())
    stale_key = ("docx-read", "an_op_that_was_deleted")
    rows = dict(perm.permission_registry())
    rows[stale_key] = dataclasses.replace(rows[("docx-read", "get_docx_content")],
                                          operation="an_op_that_was_deleted")
    gaps = perm.coverage_gaps(rows=rows, inventory=inventory)
    assert gaps.orphans == [stale_key]
    assert not gaps.uncovered


def test_the_coverage_check_greens_on_the_truth():
    gaps = perm.coverage_gaps(
        rows=perm.permission_registry(), inventory=perm.operation_inventory())
    assert not gaps.uncovered and not gaps.orphans


def test_an_endpoint_with_no_row_in_the_scope_table_REDDENS():
    """The third red proof the amplifier asks for: change an operation's endpoint family so
    its derived requirement would differ, and the guard must notice rather than silently
    projecting an empty requirement."""
    unknown = perm.unmapped_endpoints({("docx-read", "x"): ("/open-apis/im/v1/messages",)})
    assert unknown == [("docx-read", "x", "/open-apis/im/v1/messages")]
    assert perm.unmapped_endpoints(dict(perm.operation_inventory())) == [], (
        "every endpoint the code actually reaches must have a row in the scope table")


# --------------------------------------------------------------------------- #
# The library never widens, requests or escalates a scope.                     #
# --------------------------------------------------------------------------- #

def test_the_library_reaches_no_scope_GRANTING_endpoint():
    """The binding rule: this registry DESCRIBES requirements; it never asks for them. A
    grant is an action a workspace administrator takes in the Lark console."""
    reached = {ep for eps in dict(perm.operation_inventory()).values() for ep in eps}
    for endpoint in reached:
        assert "/application/" not in endpoint, endpoint
        assert "/admin/" not in endpoint, endpoint
        assert "auth?q=" not in endpoint, endpoint


def test_no_public_CALLABLE_in_the_module_offers_to_grant_or_widen_a_scope():
    """A naming guard on the module's callables. ``NEVER_WIDENS`` is deliberately exempt: it
    is the statement of the rule, not a call that breaks it — which is why the check is over
    callables rather than over every name."""
    banned = re.compile(r"grant|widen|escalate|elevate|request_scope", re.IGNORECASE)
    for name in dir(perm):
        if name.startswith("_"):
            continue
        if not callable(getattr(perm, name)):
            continue
        assert not banned.search(name), (
            f"larkdocio.permissions.{name} reads as a scope-granting call; the library "
            "never widens, requests or escalates a scope")


def test_the_never_widens_rule_is_stated_in_the_module_itself():
    """The rule has to hold where the registry lives, so it is stated there verbatim —
    compared with whitespace normalized, because a module docstring is line-wrapped."""
    def flat(text):
        return " ".join(text.split())

    assert perm.NEVER_WIDENS
    assert flat(perm.NEVER_WIDENS) in flat(inspect.getdoc(perm) or ""), (
        "the rule must be stated where the registry lives, not only in a document")
    assert "console" in perm.NEVER_WIDENS.lower()


def test_no_source_file_reaches_a_scope_MANAGEMENT_surface():
    """A grep-level proof over the shipped package: no call site touches the app-management
    or console-authorization surfaces at all, so no code path can ask Lark for a permission
    even by accident. The scope strings the registry *describes* are data; these are the
    endpoints that would *change* a grant."""
    import pathlib

    src = pathlib.Path(perm.__file__).parent
    forbidden = ("auth?q=", "/open-apis/application/", "/open-apis/admin/",
                 "lark_oapi.api.application", "lark_oapi.api.admin")
    offenders = []
    for path in sorted(src.rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for needle in forbidden:
                if needle in line:
                    offenders.append(f"{path.relative_to(src)}:{lineno}: {needle}")
    assert not offenders, (
        "these lines reach an app-management / console-authorization surface; the library "
        f"never widens, requests or escalates a scope: {offenders}")


# --------------------------------------------------------------------------- #
# The surface-level lists are PROJECTED from the rows — one source, not two.    #
# --------------------------------------------------------------------------- #

def test_surface_scopes_are_projected_from_the_operation_rows():
    """The unification: a surface's ``scopes`` / ``optional_scopes`` are no longer a second
    assertion of the same fact — they are the union of its operations' rows."""
    caps = capabilities(full=True)["surfaces"]
    for sid, surface in caps.items():
        required, optional = perm.surface_scope_projection(sid)
        assert surface["credentials"]["scopes"] == list(required), sid
        assert surface["credentials"]["optional_scopes"] == list(optional), sid


def test_a_surface_scope_list_MOVES_when_the_endpoint_table_moves(monkeypatch):
    """The amplifier's mutation proof at the surface level: patch the one hand-listed thing
    (the endpoint→scope table) and the surface's projected list must follow."""
    before = capabilities(full=True)["surfaces"]["docx-read"]["credentials"]["scopes"]
    assert before == ["docx:document:readonly"]

    patched = tuple(
        (prefix, mode, tuple(
            dataclasses.replace(s, scope="docx:document:mutated") for s in scopes), note)
        if prefix == "/open-apis/docx/v1/documents" and mode == "read"
        else (prefix, mode, scopes, note)
        for prefix, mode, scopes, note in perm.ENDPOINT_SCOPES
    )
    monkeypatch.setattr(perm, "ENDPOINT_SCOPES", patched)
    perm.clear_caches()
    try:
        after = capabilities(full=True)["surfaces"]["docx-read"]["credentials"]["scopes"]
        assert after == ["docx:document:mutated"], after
    finally:
        monkeypatch.undo()
        perm.clear_caches()
    assert capabilities(full=True)["surfaces"]["docx-read"]["credentials"]["scopes"] == before


def test_every_operation_in_capabilities_carries_its_permission_projection():
    """The registry projects INTO ``capabilities()`` rather than sitting beside it: every op
    (and every lifecycle call) carries the requirement, so a consumer reading the machine
    surface never has to find a second document."""
    caps = capabilities(full=True)["surfaces"]
    for sid, surface in caps.items():
        for op in surface["operations"] + surface.get("lifecycle", []):
            assert "permissions" in op, f"{sid}.{op['name']} carries no permissions block"
            block = op["permissions"]
            assert set(block) >= {
                "endpoints", "credential_app", "credentials_env", "scopes",
                "optional_scopes", "api_using", "basis"}
            assert block["api_using"] is (bool(block["endpoints"]))


def test_the_capability_registry_still_round_trips_through_json():
    import json

    payload = capabilities(full=True)
    assert json.loads(json.dumps(payload)) == payload


def test_an_unknown_requirement_is_carried_BACK_to_the_caller_not_just_documented():
    """The honest-unknown discipline has to reach a program, not only a reader.

    An endpoint whose requirement has never been observed produces an EMPTY scope list, and
    an empty list read naively means "needs nothing" — the exact misreading that makes a
    permissions gap look like something else. So every such reason travels on the operation's
    own block as ``unknown_requirements``, where a caller can see it.
    """
    from larkdocio.capabilities import capabilities

    surfaces = capabilities(full=True)["surfaces"]
    sheets_read = {op["name"]: op["permissions"]
                   for op in surfaces["sheets-read"]["operations"]}
    block = sheets_read["read_used_range"]
    assert block["scopes"] == [] and block["api_using"] is True
    assert block["unknown_requirements"], (
        "a call with an empty requirement must carry the REASON it is empty, or an empty "
        "list reads as 'needs nothing'")
    # LD-475: the reason is carried ONCE, in the top-level catalog, and the operation names the
    # endpoint it belongs to — so the claim is followed through the reference rather than read
    # off a re-typed copy. What must reach a caller is unchanged: the reason, in full.
    catalog = capabilities(full=True)["unknown_requirements"]
    reasons = [catalog[key]["reason"] for key in block["unknown_requirements"]]
    assert any("no scope string" in reason for reason in reasons), reasons


def test_no_scope_string_in_the_table_was_invented_rather_than_observed():
    """The rule AC6 turns on: a scope is in the table only because a capture or a live gate
    established it. Every entry is therefore either denial-verified (Lark named it) or
    grant-verified (we hold it and the calls succeed) — and any future
    ``documented-unverified`` entry must still cite the document it came from."""
    for prefix, mode, scopes, _note in perm.ENDPOINT_SCOPES:
        for scope in scopes:
            assert scope.verification in ("denial-verified", "grant-verified",
                                          "documented-unverified"), scope
            assert len(scope.evidence) > 30, (
                f"{prefix} ({mode}) {scope.scope}: an evidence pointer must name where the "
                f"requirement was established, not gesture at it: {scope.evidence!r}")


def test_which_verification_labels_are_actually_IN_USE_is_recorded():
    """A vocabulary with dead entries invites a future author to reach for the wrong one, so
    what is in use is pinned — and this pin has already earned its keep by reddening when the
    set changed.

    Two labels are in use. **``grant-verified``** covers every ESTABLISHED requirement: we hold
    it and the calls succeed. **``documented-unverified``** covers the one CANDIDATE — a scope
    string this project has long carried for the whiteboard image download but has never seen
    Lark demand; it is reported so a caller has something to try, and excluded from every
    surface's asserted requirement so nothing claims it is needed. The captured denials — the
    ``denial-verified`` evidence — sit in their own catalogue, because Lark named those scopes
    while refusing and no shipped call requires them.
    """
    in_use = {scope.verification
              for _p, _m, scopes, _n in perm.ENDPOINT_SCOPES for scope in scopes}
    assert in_use == {"grant-verified", "documented-unverified"}, (
        f"the labels in use have changed to {sorted(in_use)} — update this pin and say why")
    assert set(perm.VERIFICATION_LABELS) >= in_use

    # The label and the exclusion must travel together: an unverified requirement that still
    # got asserted at surface level would be the failure the label exists to prevent.
    unverified = [scope for _p, _m, scopes, _n in perm.ENDPOINT_SCOPES for scope in scopes
                  if scope.verification == "documented-unverified"]
    assert unverified
    for scope in unverified:
        assert scope.established is False, (
            f"{scope.scope} is unverified but is marked established, so a surface would "
            "assert it as a requirement")


def test_no_CANDIDATE_scope_reaches_any_surface_asserted_requirement():
    """The structural half of the candidate idea: it is reported on the operation, and it is
    absent from every surface's ``scopes`` / ``optional_scopes``. Without this the only options
    are to assert something unproven or to delete a useful hint."""
    candidates = {scope.scope
                  for _p, _m, scopes, _n in perm.ENDPOINT_SCOPES for scope in scopes
                  if not scope.established}
    assert candidates, "the candidate mechanism must actually be exercised by a real row"
    for surface_id, surface in capabilities(full=True)["surfaces"].items():
        asserted = set(surface["credentials"]["scopes"]) | set(
            surface["credentials"]["optional_scopes"])
        leaked = sorted(candidates & asserted)
        assert not leaked, f"{surface_id} asserts unestablished scope(s) as required: {leaked}"

    # …and it IS reported where a caller can see it, with its reason.
    board = {op["name"]: op["permissions"]
             for op in capabilities(full=True)["surfaces"]["docx-read"]["operations"]}
    block = board["download_board_image"]
    payload = capabilities(full=True)
    assert sorted(rows.scope_strings(payload, block)) == ["board:whiteboard:node:read"]
    assert rows.scope_rows(payload, block)[0]["established"] is False
    assert block["unknown_requirements"], (
        "a candidate-only endpoint must still carry the reason its requirement is unsettled")


# --------------------------------------------------------------------------- #
# The table's OTHER direction: a row that outlives its call site.               #
# --------------------------------------------------------------------------- #

#: Table rows no operation reaches, each with the reason it is nonetheless kept.
#:
#: The coverage guard catches an endpoint with no row. This is the mirror — a row with no
#: endpoint — and the exemption is named rather than assumed, the same standard the registry
#: holds itself to for an empty requirement.
#:
#: **LD-251 emptied this table back down to one.** The Base row's exemption was temporary *by
#: construction*: LD-247 landed the client and its scope row together while the capabilities()
#: surface the inventory is built from did not exist yet, and the second half of the test below
#: was written to redden the day it did. LD-251 published `base-read` (and its two siblings), the
#: row became reachable, and the exemption was deleted on that signal — which is the mechanism
#: working exactly as the note said it would.
#: **LD-255 re-opened it with ONE row, on the same temporary-by-construction terms** — and
#: **LD-260 deleted it again**, for exactly the reason the note predicted: the record-write
#: families landed their client and their scope row while the `base-write` surface the
#: inventory is built from was still a later story, so the row was unreachable for as long as
#: that surface was unpublished. LD-260 published it, the staleness half of the test below
#: reddened on the exemption, and the exemption went. Twice now the mechanism has retired its
#: own entry on the signal it was written to watch for, which is the whole point of writing the
#: expiry into the guard rather than into a comment.
#: **LD-324 re-opened it with TWO rows, on those same temporary-by-construction terms** — the
#: Drive enumeration client's two non-SDK legs (``metas/batch_query`` for a folder's own title,
#: ``explorer/v2/root_folder/meta`` for the caller's own root) landed with their scope rows while
#: the ``capabilities()`` Drive surface the inventory is built from was a LATER story. **LD-327
#: PUBLISHED that surface** — the ``drive-read`` enumeration operations now derive all three drive
#: endpoints (``/drive/v1/files`` too), so both rows became reachable and the staleness half of
#: the test below reddened on them exactly as predicted. They are deleted on that signal, the same
#: mechanism that already retired three predecessors — a fourth demonstration that the expiry
#: lives in the guard, not in a comment.
EXPECTED_UNREACHED_ROWS = {
    ("/open-apis/auth/v3/tenant_access_token", "*"): (
        "the tenant-token mint sits BELOW the operation layer — every client does it inside "
        "the shared transport, so no operation's own code names it and it cannot be reached "
        "by the derivation. The row is kept because 'no scope is required to mint a token' is "
        "a real answer a caller needs, and it is verified: every live ring proves it."
    ),
}


def test_no_table_row_outlives_the_call_site_it_was_written_for():
    """A row nobody reaches is a requirement nobody can act on and a maintenance cost nobody
    can retire — the phantom-row failure this project treats as red everywhere else."""
    unreached = set(perm.unreached_table_rows())
    unexplained = sorted(unreached - set(EXPECTED_UNREACHED_ROWS))
    assert not unexplained, (
        "these endpoint-scope rows are reached by no operation and carry no recorded reason: "
        f"{unexplained}")
    stale = sorted(set(EXPECTED_UNREACHED_ROWS) - unreached)
    assert not stale, (
        "these rows are now reachable, so their exemption is obsolete and should be deleted: "
        f"{stale}")
    for row, reason in EXPECTED_UNREACHED_ROWS.items():
        assert len(reason) > 60, f"{row} is exempted without a real reason"


def test_the_orphan_guard_bites_RED_on_a_row_nothing_reaches():
    """Proven by running the REAL function against an inventory that reaches nothing, rather
    than by asserting set arithmetic in the test."""
    unreached = perm.unreached_table_rows(inventory={("docx-read", "x"): ()})
    assert len(unreached) == len(perm.ENDPOINT_SCOPES), (
        "with an inventory that reaches no endpoint, every row must be reported")
    assert ("/open-apis/docx/v1/documents", "read") in unreached
