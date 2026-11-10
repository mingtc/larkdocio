"""THE BLIND-SPOT GUARD — what the endpoint derivation cannot see, it must SAY.

What this module guards
-----------------------
``larkdocio.permissions.endpoints_of`` resolves the names in a call site's body against that
function's **module globals**. Before LD-609 an implementation that reached Lark through a
**function-local import** — the symbol is bound in the function's *locals* at call time and
appears in no module namespace — was therefore invisible to it: the operation derived
``endpoints=()``, hence ``api_using=False``, hence no permission row and no scope
requirement, **silently**.

The reason that was Major rather than cosmetic is that the guard which should have caught it
was **circular**: ``operation_inventory()`` filtered on ``if endpoints:``, so *API-using* was
defined AS ``endpoints_of``'s own answer, and a call site the derivation could not see was —
by the guard's own definition — not API-using. ``gaps.uncovered`` was empty and the
bidirectional coverage test greened over the hole.

So this module guards two things that are deliberately different:

* **the widened derivation** — a function-local import of this package (or of the pinned SDK)
  is followed, so the endpoints behind it derive like any other;
* **the disclosure** — every seam the derivation still cannot resolve is **recorded** on the
  operation's own permission block (``unresolved_call_sites``) and reported by
  :func:`~larkdocio.permissions.coverage_gaps` as ``undetermined``. That direction is
  **keyed on the payload having something unresolved, never on the endpoint tuple being
  empty** — the LD-596 discipline, restated: an operation may reach some endpoints through
  globals and others through a seam the walk cannot follow, and an emptiness-keyed check
  greens on exactly that case.

Every specimen below is **purpose-built for the test**, never a shipped function. A guard
written against the instance that was discovered dies the moment someone tidies that one
import, and the mechanism defect survives it.
"""
import dataclasses

import pytest

from larkdocio import permissions as perm
# A module-global import, ON PURPOSE: the visible half of the mixed specimen below.
from larkdocio.write.client import WriteClient
import private_tree  # noqa: E402  (LD-685)

pytestmark = pytest.mark.conformance


# --------------------------------------------------------------------------- #
# THE SPECIMENS — written for this test, not borrowed from the library.        #
# --------------------------------------------------------------------------- #

def specimen_reaches_lark_only_through_a_function_local_import(token: str):
    """Reaches a Lark endpoint through a symbol bound only in this function's LOCALS.

    Deliberately not ``drive.read.read_child_markdown`` (the instance LD-609 was discovered
    through): the guard has to outlive that one function's import style.
    """
    from larkdocio.read.client import Client

    return Client.get_docx_content(None, token)


def specimen_reaches_one_endpoint_through_globals_and_another_through_a_local_import(token):
    """THE TRAP SPECIMEN: partly visible. One endpoint family resolves off module globals,
    another only through a function-local import — so a check keyed on the endpoint tuple
    being EMPTY greens on it while the requirement it publishes is short."""
    from larkdocio.read.client import Client

    WriteClient.create_document(None, "specimen", None)
    return Client.get_docx_content(None, token)


def specimen_reaches_lark_through_an_import_the_derivation_CANNOT_follow(module: str):
    """A dynamically named import. There is no static answer here and none is invented —
    this is the residual class, and the point is that it is DISCLOSED rather than derived."""
    import importlib

    return importlib.import_module(module).Client.get_docx_content(None, "t")


def specimen_is_handed_an_unannotated_client(client, token: str):
    """A call site handed its client with no annotation and no seed: the object whose methods
    reach Lark is not knowable from this source at all."""
    return client.get_docx_content(token)


def specimen_touches_no_api(a: int, b: int) -> int:
    """The control. An empty derivation with NOTHING unresolved is a real answer — it is the
    only shape entitled to read as *needs no permission*."""
    return a + b


# --------------------------------------------------------------------------- #
# AC1/AC2 — the derivation now SEES a function-local import.                   #
# --------------------------------------------------------------------------- #

def test_a_call_site_reaching_lark_only_through_a_function_local_import_DERIVES():
    """The red proof of LD-609: this returned ``()`` before the fix, which is what made the
    operation publish ``api_using=False`` with no permission row and no scope."""
    derived = perm.endpoints_of(specimen_reaches_lark_only_through_a_function_local_import)
    assert derived == (
        "/open-apis/docx/v1/documents/:document_id",
        "/open-apis/docx/v1/documents/:document_id/blocks",
        "/open-apis/docx/v1/documents/:document_id/blocks/:block_id/children",
    ), derived


def test_a_PARTLY_visible_call_site_derives_BOTH_halves():
    """LD-596's trap, in the derivation: the visible half made the endpoint tuple non-empty,
    so nothing keyed on emptiness could ever have noticed the missing half."""
    derived = perm.endpoints_of(
        specimen_reaches_one_endpoint_through_globals_and_another_through_a_local_import)
    assert "/open-apis/docx/v1/documents" in derived, derived
    assert "/open-apis/docx/v1/documents/:document_id/blocks" in derived, derived


def test_the_widened_walk_only_follows_THIS_package_and_the_pinned_sdk():
    """The derivation imports modules to resolve a local import, so what it may import is
    fenced: an import of anything outside this package or the pinned SDK is disclosed as
    unresolved rather than executed."""
    source = perm.pathlib_read(perm.__file__)
    assert 'IMPORTABLE_PREFIXES = ("larkdocio", "lark_oapi")' in source


# --------------------------------------------------------------------------- #
# The DISCLOSURE — the seams the walk still cannot resolve say so.              #
# --------------------------------------------------------------------------- #

def test_an_import_the_walk_cannot_follow_is_RECORDED_not_ignored():
    spots = perm.unresolved_call_sites_of(
        specimen_reaches_lark_through_an_import_the_derivation_CANNOT_follow)
    assert any("importlib" in spot for spot in spots), spots
    assert all(specimen_reaches_lark_through_an_import_the_derivation_CANNOT_follow.__name__
               in spot for spot in spots), spots


def test_an_unannotated_unseeded_CLIENT_parameter_is_RECORDED_not_ignored():
    spots = perm.unresolved_call_sites_of(specimen_is_handed_an_unannotated_client)
    assert any("client" in spot for spot in spots), spots


def test_a_SEEDED_client_parameter_is_not_a_blind_spot_because_it_resolves():
    """The seed table's own case must not be reported as unresolved — the surface has said
    which class it hands, so the derivation knows."""
    from larkdocio.read.client import Client

    assert perm.unresolved_call_sites_of(specimen_is_handed_an_unannotated_client,
                               {"client": Client}) == ()


def test_a_call_site_that_touches_no_api_has_NOTHING_unresolved():
    """The control, and the reason this is not merely a louder empty: a derivation of ``()``
    with no blind spot is entitled to read as *needs no permission*."""
    assert perm.endpoints_of(specimen_touches_no_api) == ()
    assert perm.unresolved_call_sites_of(specimen_touches_no_api) == ()


def test_a_blind_spot_travels_onto_the_operations_own_permission_block():
    block = perm.permissions_for(
        specimen_is_handed_an_unannotated_client, mode="read",
        credential_app="read", credentials_env=("LARK_READ_APP_ID",))
    assert block.unresolved_call_sites, block
    assert "unresolved_call_sites" in block.to_dict()
    clean = perm.permissions_for(
        specimen_touches_no_api, mode="read",
        credential_app="read", credentials_env=("LARK_READ_APP_ID",))
    assert clean.unresolved_call_sites == ()
    assert "unresolved_call_sites" not in clean.to_dict(), (
        "a call site with nothing unresolved must say nothing — the key's presence is itself "
        "the information")


# --------------------------------------------------------------------------- #
# THE CIRCULARITY — the guard's subject is no longer the derivation's answer.   #
# --------------------------------------------------------------------------- #

def test_the_INVENTORY_no_longer_defines_api_using_as_the_derivations_own_answer():
    """``operation_inventory()`` filtered on ``if endpoints:``, so a call site the derivation
    could not see was by definition not API-using and could never be reported as a gap. It
    now admits a call site whose derivation is UNRESOLVED as well as one that derived."""
    source = perm.pathlib_read(perm.__file__)
    region = source.split("def operation_inventory")[1].split("\ndef ")[0]
    assert "unresolved_call_sites" in region, region


def test_coverage_gaps_reports_an_UNDETERMINED_call_site():
    rows = dict(perm.permission_registry())
    key = ("docx-read", "a_specimen_whose_derivation_is_incomplete")
    rows[key] = dataclasses.replace(
        rows[("docx-read", "get_docx_content")],
        operation=key[1], endpoints=(),
        unresolved_call_sites=("specimen: parameter 'client' is bound to no class",))
    gaps = perm.coverage_gaps(rows=rows, inventory=dict(perm.operation_inventory()))
    assert key in gaps.undetermined, gaps.undetermined


def test_the_UNDETERMINED_direction_is_NOT_keyed_on_the_endpoint_TUPLE_BEING_EMPTY():
    """LD-596's trap, in the guard: an operation that reaches three endpoints through globals
    and a fourth through a seam the walk cannot follow must still be reported. A check keyed
    on emptiness greens on exactly this row, which is why this one is keyed on the record."""
    rows = dict(perm.permission_registry())
    key = ("docx-read", "a_specimen_that_derives_SOME_of_what_it_reaches")
    donor = rows[("docx-read", "get_docx_content")]
    assert donor.endpoints, "the donor row must be API-using for this proof to mean anything"
    rows[key] = dataclasses.replace(
        donor, operation=key[1],
        unresolved_call_sites=("specimen: an import the walk cannot follow",))
    gaps = perm.coverage_gaps(rows=rows, inventory=dict(perm.operation_inventory()))
    assert key in gaps.undetermined, gaps.undetermined
    assert key not in gaps.uncovered, (
        "the row EXISTS — its defect is an incomplete derivation, which is what "
        "'undetermined' reports; calling it uncovered would say nobody wrote a row")


def test_the_undetermined_direction_greens_on_a_COMPLETE_derivation():
    rows = {key: dataclasses.replace(row, unresolved_call_sites=())
            for key, row in perm.permission_registry().items()}
    gaps = perm.coverage_gaps(rows=rows, inventory=dict(perm.operation_inventory()))
    assert gaps.undetermined == []


# --------------------------------------------------------------------------- #
# THE SHIPPED REGISTRY — incompleteness may exist; SILENT incompleteness may not.#
# --------------------------------------------------------------------------- #

def test_NO_shipped_call_site_is_SILENTLY_incomplete():
    """The anti-circularity check, and the one that keeps its subject independent: the blind
    spots are re-derived here **off the implementing callables** and every one of them must
    appear in the payload a consumer reads. A shipped operation whose derivation is
    incomplete is allowed — what is not allowed is a consumer being unable to tell.
    """
    from larkdocio.capabilities import capabilities
    from larkdocio.capabilities._assembly import _build
    from larkdocio.capabilities._permissions import _IMPL_SEEDS

    published = {}
    payload = capabilities(full=True)
    for surface_id, surface in payload["surfaces"].items():
        for op in surface["operations"]:
            published[(surface_id, op["name"])] = tuple(
                op["permissions"].get("unresolved_call_sites") or ())

    silent = []
    for surface_id, surface in _build().surfaces.items():
        seeds = _IMPL_SEEDS.get(surface_id, {})
        sites = (list(surface.operations) + list(surface.legs)
                 + list(surface.lifecycle or ()))
        for op in sites:
            impls = op.impl
            impls = () if impls is None else (
                (impls,) if callable(impls) else tuple(impls))
            spots = set()
            for impl in impls:
                spots |= set(perm.unresolved_call_sites_of(impl, seeds))
            if spots and not spots <= set(published.get((surface_id, op.name), ())):
                silent.append((surface_id, op.name, sorted(spots)))
    assert not silent, (
        "these shipped call sites have a derivation the walk could not complete and the "
        f"payload does not say so: {silent}")


def test_a_shipped_call_site_with_an_incomplete_derivation_is_reported_as_UNDETERMINED():
    """The live registry's own answer, asserted as a LIST rather than a count: whatever is
    undetermined today is named here, so a new one cannot join it unnoticed and a resolved
    one cannot leave the list without this test saying so."""
    assert perm.coverage_gaps().undetermined == [
        ("base-schema-write", "migrate_field_type"),
    ]


def test_the_MAINTAINER_matrix_does_not_call_an_incomplete_derivation_needs_nothing():
    """``dev_permissions_markdown`` listed every ``api_using=False`` row under *"Makes no
    Lark call, so needs no permission"* — a confident empty about a row whose derivation had
    merely stopped early. The two lists are now different lists."""
    text = perm.dev_permissions_markdown()
    assert "Makes no Lark call, so needs no permission" in text
    assert "derivation could not be completed" in text
    quiet = text.split("Makes no Lark call, so needs no permission")[1].split("\n")[0]
    assert "migrate_field_type" not in quiet, quiet


# --------------------------------------------------------------------------- #
# PREFLIGHT — the consumer-facing answer must not read as complete either.      #
# --------------------------------------------------------------------------- #

def test_preflight_calls_an_undetermined_operation_a_BLIND_SPOT_not_a_no_api_call(
        monkeypatch):
    """LD-460's rule, reached through LD-609's honesty: ``no-api-call`` is the state that says
    an emptiness was MEASURED. An operation whose derivation could not be completed must not
    borrow it.

    **TRANSFORMED by LD-642, not weakened — and the reason above is untouched.** This asserted
    the rule against the one SHIPPED operation that happened to be in that state,
    ``base-schema-write.migrate_field_type``, which reached the ``undetermined`` arm because
    its seed row named no class for ``read_client`` and it therefore derived *no scopes and no
    endpoints at all*. LD-642 seeded the class; the operation now derives four bitable
    endpoints and ``bitable:app``, so it is ``known`` — and no shipped operation is in the
    ``undetermined`` state any more. Asserting the rule against a live instance was always the
    thing this module's own header forbids (*"a guard written against the instance that was
    discovered dies the moment someone tidies that one import"*), and that is exactly how it
    died. It is re-asserted here against a purpose-built specimen row, so the rule outlives
    every future seeding; the live half of the claim moved to
    ``test_a_seeded_operation_that_still_carries_a_seam_stays_a_disclosed_blind_spot``.
    """
    from larkdocio import preflight

    seam = ("specimen.derivation_stopped: a function-local import the derivation cannot "
            "follow, so any endpoint reached through it is not in this operation's "
            "endpoint list")
    row = perm.PermissionRow(
        surface="specimen", operation="derivation_stopped", kind="operation", mode="write",
        endpoints=(), credential_app="specimen-app", credentials_env=(),
        scopes=(), optional_scopes=(), api_using=False, basis="derived",
        unresolved_call_sites=(seam,))
    monkeypatch.setattr(preflight, "_registry_index",
                        lambda: {"specimen.derivation_stopped": [row]})

    requirement, = preflight.requirements_for_operations(["specimen.derivation_stopped"])
    assert requirement.state == "undetermined", requirement
    assert requirement.state != "no-api-call", requirement
    assert requirement.unresolved_call_sites, requirement
    assert "unresolved_call_sites" in requirement.to_dict()


def test_a_seeded_operation_that_still_carries_a_seam_stays_a_disclosed_blind_spot():
    """LD-642's live half. Seeding ``read_client`` moved the Base column-type migration out of
    ``undetermined`` **as a preflight state** — its scopes are now derived — and it must NOT
    thereby go quiet: two dynamic-import seams remain inside its reach (both resolved through
    ``importlib`` at call time), so the row still publishes them and
    ``coverage_gaps().undetermined`` — which is keyed on the seam, not on the state — still
    names it. The failure this forbids is the one LD-642 fixed reappearing inverted: a
    confident, complete-looking answer over a derivation that is still short."""
    from larkdocio import preflight

    requirement, = preflight.requirements_for_operations(
        ["base-schema-write.migrate_field_type"])
    assert requirement.state == "known", requirement
    assert "bitable:app" in requirement.scopes, requirement
    assert requirement.endpoints, requirement
    assert requirement.unresolved_call_sites, requirement
    assert ("base-schema-write", "migrate_field_type") in perm.coverage_gaps().undetermined


@private_tree.dev_record
def test_preflight_discloses_a_seam_on_an_operation_whose_scopes_ARE_known(monkeypatch):
    """The trap again, one layer out: a KNOWN requirement with a lost seam would otherwise
    hand back a full-looking verdict list and an empty ``blind_spots``."""
    from larkdocio import preflight

    partly = preflight.OperationRequirement(
        operation="specimen.partly_derived", state="known",
        scopes=("docx:document:readonly",),
        endpoints=("/open-apis/docx/v1/documents/:document_id",),
        unresolved_call_sites=("specimen: an import the walk cannot follow",),
        note="the registry knows 1 scope(s) for this operation")
    monkeypatch.setattr(preflight, "requirements_for_operations", lambda names: (partly,))
    # The captured probe answers live beside LD-460's own guard; reusing them keeps one
    # definition of "what a held scope looks like" rather than minting a second.
    from test_permission_preflight import ALL_HELD

    result = preflight.check_permissions(
        ["specimen.partly_derived"], probe=ALL_HELD, credentials=("id", "secret"))
    assert result.verdicts, "the visible half must still answer"
    assert any("cannot be resolved statically" in spot for spot in result.blind_spots), \
        result.blind_spots
