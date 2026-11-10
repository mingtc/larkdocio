"""larkdocio.preflight — an OPTIONAL, ADVISORY check of whether you hold what an operation needs.

**Read this before trusting the answer.** A live probe chose this mechanism and, just as
importantly, mapped what it cannot see. A check that claimed more than the evidence supports
would be the permissions equivalent of the bug this whole area exists to prevent — a confident
answer that is quietly wrong — so the limits are part of the contract, not a footnote.

**What the probe established.** Lark evaluates the **scope gate before the resource lookup**: a
GET against a deliberately nonexistent id answers ``99991672`` when the scope is missing, and a
plain resource error when the scope is held. So a scope can be checked with one cheap,
read-only call that needs **no real document, spreadsheet or user** — nothing is created,
nothing is touched, and the caller does not have to hand over their data to find out what they
can do. Aiming that instrument with the permission registry gives the mechanism used here:
derive the scope set from the requested operations (zero calls), then spend **one call per
distinct probeable scope family**.

**What it CANNOT see — three blind spots, each established by capture, not assumed.**

1. **A write scope cannot be probed by any read.** A GET is authorized by the *readonly*
   scope, so passing one says nothing about whether the write scope is held. Probing a write
   scope would mean writing, which this must never do. Write scopes are reported
   ``basis="derived"`` — *this is what the operation needs*, never *you have it*.
2. **A FIELD-LEVEL grant is invisible.** Without ``contact:user.base:readonly`` the contacts
   call still **succeeds** and every name field comes back null, so no probe outcome
   distinguishes held from not-held. **This is the exact scope class that cost five days**, and
   it is the one this check cannot verify. It is reported as a blind spot in so many words.
3. **A requirement nobody has ever observed cannot be confirmed.** Where the registry knows no
   scope string for an endpoint family, the answer is ``basis="unknown"`` — not a clean bill of
   health. And where **every** endpoint an operation reaches is in that position, the operation
   derives no scope at all: it is then named in ``blind_spots`` in its own right, because a
   verdict list that is simply empty is the one shape that reads as *"needs nothing"*.

Add that the check reads one endpoint per family (so it proves that endpoint's gate, not every
route in the family), says nothing about the **contacts data range** (a separate console
setting and the other half of the name-resolution precondition), and that a scope can be
revoked between the check and the work — and the honest summary is: **advisory**.

**Therefore, three hard rules this module keeps.** It is **never mandatory** — no operation
gained a required pre-check, and skipping it changes nothing about how a real denial is
reported. It **never mutates** — every probe is a GET against a bogus id. And it **never
widens, requests or escalates a scope**: it reports, and a grant is a Lark console action.
"""
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from larkdocio import permissions as _perm
from larkdocio.common.auth import READ_ENV, get_read_credentials, resolved_read_env
from larkdocio.common.transport import (
    CredentialedRawHttpClient,
    api_base,
    fetch_tenant_access_token,
)
from larkdocio.errors import LarkConfigError


#: What a verdict's basis can be, strongest first. The whole point of carrying it is that
#: ``derived`` and ``unknown`` must never be mistaken for ``probed``.
#:
#: * ``probed`` — a live read distinguished held from not-held for this scope;
#: * ``derived`` — the requirement is known from the registry but **cannot** be probed
#:   read-only (a write scope, an export scope whose only entry point is a create, or a
#:   field-level grant whose absence is invisible). ``held`` is ``None``;
#: * ``unknown`` — no scope string is known for the endpoint family at all. ``held`` is
#:   ``None``, and this is emphatically not "nothing is needed".
BASES = ("probed", "derived", "unknown")

#: Deliberately invalid ids, one per probeable family, in that family's own shape.
#:
#: These are the instrument. Because Lark checks the scope first, a nonexistent target is
#: enough — and it is what makes the probe harmless: there is no real resource to read, alter
#: or leak, and nothing is created that would need cleaning up afterwards.
_BOGUS_DOCUMENT_ID = "Zzzz0000LdIoPreflightNoSuchDocument0000"
_BOGUS_OPEN_ID = "ou_0000000000000000000000000preflight"


@dataclass(frozen=True)
class ScopeProbe:
    """One read-only, resource-free probe for one scope.

    ``method`` is a field rather than a constant so the read-only property is **inspectable**
    (and asserted) instead of merely intended: a probe table entry that was not a GET would be
    caught by looking at the table, without running anything.
    """

    scope: str
    method: str
    path: str
    params: Tuple[Tuple[str, str], ...] = ()
    credential_app: str = "read"
    evidence: str = ""


#: The probe table — **only** scopes a read-only call can actually decide.
#:
#: Every entry's shape was established live (see ``tests/captures/permissions-preflight-probe`` in the source
#: repository): the denial arm on a family we do not hold, the resource-error arm on one we do. A
#: scope absent from this table is absent on purpose, and is reported ``derived`` or ``unknown``
#: rather than guessed at.
PROBES: Tuple[ScopeProbe, ...] = (
    ScopeProbe(
        scope="docx:document:readonly",
        method="GET",
        path=f"/open-apis/docx/v1/documents/{_BOGUS_DOCUMENT_ID}",
        evidence=(
            "the document family answers a nonexistent id with a resource error when the "
            "scope is held (capture Q4) while a not-held family answers 99991672 on an "
            "equally bogus id (capture Q12)"
        ),
    ),
    ScopeProbe(
        scope="contact:contact.base:readonly",
        method="GET",
        path="/open-apis/contact/v3/users/batch",
        params=(("user_ids", _BOGUS_OPEN_ID), ("user_id_type", "open_id")),
        evidence=(
            "the contacts family answers a nonexistent open id with 99992351 when the "
            "directory scope is held (capture Q5); the not-held arm is capture Q12"
        ),
    ),
)

#: Why a known scope is not in :data:`PROBES`. Stated per scope so the reason travels with the
#: verdict instead of living only in a document.
NOT_PROBEABLE: Dict[str, str] = {
    "docx:document": (
        "a write scope cannot be proved by any read — a GET is authorized by the readonly "
        "scope, so passing one says nothing about it, and probing it would mean writing"
    ),
    "contact:user.base:readonly": (
        "a FIELD-LEVEL grant is invisible to a probe: without it the call still SUCCEEDS and "
        "the name fields come back empty, so no probe outcome tells held from not-held. This "
        "is the scope class whose absence once looked like missing data for five days"
    ),
    "drive:export": (
        "the export family's only entry point is a call that CREATES an export task, and a "
        "preflight must never create anything, so it is deliberately not probed"
    ),
}


#: What is known about ONE requested operation's requirement — and, when the answer is empty,
#: **which kind of empty it is**. That distinction is the whole point: an empty scope set that
#: cannot say why reads as "needs nothing" no matter how carefully the rest of the object is
#: worded.
#:
#: * ``known`` — the registry knows at least one scope string for it; the verdicts speak;
#: * ``unmeasured`` — it **does** call Lark, and no scope string has ever been observed
#:   demanded by any endpoint it reaches. An empty answer here means *nobody has measured
#:   this*, and it is reported as a blind spot;
#: * ``no-api-call`` — it reaches no Lark path at all, so it genuinely requires nothing. This
#:   is a measured emptiness, not an unknown one, and it is deliberately **not** a blind spot;
#: * ``undetermined`` — the registry's own derivation could **not be completed** for it: a
#:   seam the static walk cannot resolve sits inside its reach, so its endpoints may be short
#:   and an empty scope set here is not a measurement at all. **Added by LD-609, and it is the
#:   state the answer for such an operation used to take by mistake**: it landed in
#:   ``no-api-call`` — the one state that says an emptiness was MEASURED — and so contributed
#:   to neither list and answered empty-and-silent. It IS a blind spot;
#: * ``unrecognised`` — not an operation this library has (a typo). Reported, never guessed at.
REQUIREMENT_STATES = ("known", "unmeasured", "no-api-call", "undetermined", "unrecognised")


@dataclass(frozen=True)
class OperationRequirement:
    """One requested operation's requirement, with the reason its answer looks the way it does.

    Carried per operation rather than only per scope because the failure this exists to prevent
    lives exactly where an operation contributes **no** scope: before it, such an operation
    passed through the per-scope and the unrecognised-name paths alike and left nothing behind.

    ``unknown_requirements`` carries the registry's own recorded reasons — verbatim, with their
    evidence pointers — for every endpoint whose requirement was never established.

    JSON: call :meth:`to_dict`, which returns plain lists/strings ready for ``json.dumps``.
    """

    operation: str
    state: str
    scopes: Tuple[str, ...] = ()
    endpoints: Tuple[str, ...] = ()
    unknown_requirements: Tuple[str, ...] = ()
    #: The registry's own ``unresolved_call_sites`` for this operation (LD-609) — carried
    #: whatever the ``state``, because an operation can derive three endpoints through module
    #: globals and lose a fourth to a seam. Reading this only when the scope list is empty is
    #: the emptiness-keyed mistake that lets exactly that operation through.
    unresolved_call_sites: Tuple[str, ...] = ()
    note: str = ""

    def to_dict(self) -> dict:
        d = {
            "operation": self.operation,
            "state": self.state,
            "scopes": list(self.scopes),
            "endpoints": list(self.endpoints),
            "note": self.note,
        }
        if self.unknown_requirements:
            d["unknown_requirements"] = list(self.unknown_requirements)
        if self.unresolved_call_sites:
            d["unresolved_call_sites"] = list(self.unresolved_call_sites)
        return d


@dataclass(frozen=True)
class ScopeVerdict:
    """What is known about one scope, and **how** it is known.

    ``held`` is a three-valued answer on purpose: ``True`` / ``False`` only when a probe
    actually decided it, and ``None`` whenever the basis is ``derived`` or ``unknown``. A
    boolean would force an unknown to masquerade as a "no".

    JSON: call :meth:`to_dict` — it returns plain types (a nested denial is flattened the same
    way), so ``json.dumps(verdict.to_dict())`` is the documented route.
    """

    scope: str
    basis: str
    held: Optional[bool] = None
    note: Optional[str] = None
    denial: object = None

    def to_dict(self) -> dict:
        d = {"scope": self.scope, "basis": self.basis, "held": self.held}
        if self.note:
            d["note"] = self.note
        if self.denial is not None:
            d["denial"] = self.denial.to_dict()
        return d


@dataclass(frozen=True)
class PermissionCheck:
    """The advisory answer: a verdict per scope, the calls it cost, and what it cannot see.

    **``ok`` is meaningless on its own — read it together with ``blind_spots``**, which is why
    they are neighbours here. ``ok`` is deliberately conservative (``True`` only when nothing
    was *found* missing) and it is never a claim that everything is fine, because a non-empty
    ``blind_spots`` says part of the answer was not measured at all.

    ``requirements`` carries one :class:`OperationRequirement` per requested operation, so an
    empty verdict set always states **which kind of empty it is**.

    JSON: call :meth:`to_dict` — every nested object is flattened to plain lists and strings,
    so ``json.dumps(result.to_dict())`` round-trips the whole answer, ``blind_spots`` included.
    """

    operations: Tuple[str, ...]
    verdicts: Tuple[ScopeVerdict, ...]
    calls_made: int
    advisory: bool = True
    blind_spots: Tuple[str, ...] = ()
    unknown_operations: Tuple[str, ...] = ()
    requirements: Tuple[OperationRequirement, ...] = ()

    @property
    def missing(self) -> Tuple[str, ...]:
        """The scopes a probe actually found to be absent — never the unprobeable ones."""
        return tuple(v.scope for v in self.verdicts if v.held is False)

    @property
    def ok(self) -> bool:
        """**Meaningless without ``blind_spots``. Read the two together, always.**

        ``True`` says one thing only: no probe *found* a scope missing. It is never a claim
        that everything these operations need is held — a non-empty ``blind_spots`` means part
        of the requirement was never measured, and a scope can be revoked after the check.
        """
        return not self.missing and not self.unknown_operations

    def to_dict(self) -> dict:
        return {
            "operations": list(self.operations),
            "verdicts": [v.to_dict() for v in self.verdicts],
            "calls_made": self.calls_made,
            "advisory": self.advisory,
            "missing": list(self.missing),
            "ok": self.ok,
            "blind_spots": list(self.blind_spots),
            "unknown_operations": list(self.unknown_operations),
            "requirements": [r.to_dict() for r in self.requirements],
        }


def _registry_index():
    """``{operation_name: [PermissionRow]}`` plus the set of valid ``surface.operation`` keys."""
    rows = _perm.permission_registry()
    by_name: Dict[str, List[object]] = {}
    for (surface_id, name), row in rows.items():
        by_name.setdefault(name, []).append(row)
        by_name.setdefault(f"{surface_id}.{name}", []).append(row)
    return by_name


def _surface_ids() -> Tuple[str, ...]:
    """Every surface id, taken from the registry rather than a second list of names."""
    return tuple(sorted({surface_id for surface_id, _name in _perm.permission_registry()}))


def _refuse_surface_id(surface_id: str) -> None:
    """Refuse a surface id by naming the spellings that would have worked.

    A surface id is the vocabulary the rest of the library teaches, so a caller who reaches for
    one is not making a random mistake — and answering them with silence (an empty, ok-shaped
    result) is the worst of the three possible answers.
    """
    operations = sorted(name for sid, name in _perm.permission_registry() if sid == surface_id)
    shown = operations[:8]
    listing = ", ".join(f"{surface_id}.{name}" for name in shown)
    if len(operations) > len(shown):
        listing += f", and {len(operations) - len(shown)} more"
    raise LarkConfigError(
        f"{surface_id!r} names a SURFACE, not an operation, so there is nothing to check for "
        f"it. Pass one of that surface's operations instead — the bare name where it is "
        f"unique, or the 'surface.operation' spelling: {listing}. The complete list is "
        f"capabilities(surface={surface_id!r})['operations'], and the names alone are in "
        f"capabilities()['surfaces'][{surface_id!r}]['operations'].")


def requirements_for_operations(for_operations: Sequence[str]) \
        -> Tuple[OperationRequirement, ...]:
    """One :class:`OperationRequirement` per requested operation — **zero calls**.

    The honest core of the derive-only half. Every requested name lands in exactly one of the
    :data:`REQUIREMENT_STATES`, so an operation can no longer contribute nothing at all: the
    case that used to fall between *"here are your scopes"* and *"that is not an operation"* —
    an operation this library **has**, which calls Lark, whose requirement nobody has ever
    observed — now says so in its own words.

    A **surface id** is refused with :class:`~larkdocio.errors.LarkConfigError` rather than
    treated as a typo, because it is a name the library itself hands out.
    """
    index = _registry_index()
    surfaces = set(_surface_ids())
    out: List[OperationRequirement] = []
    for name in for_operations:
        rows = index.get(name)
        if not rows:
            if name in surfaces:
                _refuse_surface_id(name)
            out.append(OperationRequirement(
                operation=name, state="unrecognised",
                note=(f"{name!r} is not an operation this library has, so nothing was checked "
                      "for it")))
            continue
        scopes: List[str] = []
        endpoints: List[str] = []
        unknown_requirements: List[str] = []
        unresolved: List[str] = []
        for row in rows:
            for seam in row.unresolved_call_sites:
                if seam not in unresolved:
                    unresolved.append(seam)
            for scope in row.scopes:
                if scope.scope not in scopes:
                    scopes.append(scope.scope)
            for endpoint in row.endpoints:
                if endpoint not in endpoints:
                    endpoints.append(endpoint)
            for reason in _perm.unknown_requirements_for(row.endpoints, row.mode):
                if reason not in unknown_requirements:
                    unknown_requirements.append(reason)
        if scopes:
            state = "known"
            note = (f"the registry knows {len(scopes)} scope(s) for this operation; each "
                    "verdict states how it is known")
        elif endpoints:
            state = "unmeasured"
            note = ("no requirement has been observed for this operation: it calls Lark on "
                    f"{len(endpoints)} endpoint(s) and no scope string has ever been seen "
                    "demanded by any of them, so an empty answer here means UNMEASURED, not "
                    "'needs nothing'")
        elif unresolved:
            # BEFORE the endpoint-less arm below, on purpose: an operation with an unresolved
            # seam has not been measured to reach nothing, and the one thing this module may
            # not do is let those two emptinesses share a state.
            state = "undetermined"
            note = ("the registry could not complete its derivation for this operation, so "
                    f"neither its endpoints nor its scopes are known to be complete: "
                    f"{len(unresolved)} seam(s) in its implementation cannot be resolved "
                    "statically, and capabilities(full=True) names each one under this "
                    "operation's 'unresolved_call_sites'")
        else:
            state = "no-api-call"
            note = ("this operation reaches no Lark endpoint at all, so it requires no scope "
                    "— an emptiness that was measured, not one that is unknown")
        out.append(OperationRequirement(
            operation=name, state=state, scopes=tuple(scopes), endpoints=tuple(endpoints),
            unknown_requirements=tuple(unknown_requirements),
            unresolved_call_sites=tuple(unresolved), note=note))
    return tuple(out)


def scopes_for_operations(for_operations: Sequence[str]):
    """``(scopes, unknown_operations)`` for a requested operation set — **zero calls**.

    The derive-only half, and useful on its own: it answers *what does this need* without
    touching the network at all. It cannot, however, tell you *why* a scope set came back
    empty — :func:`requirements_for_operations` is the answer that can.
    """
    requirements = requirements_for_operations(for_operations)
    scopes: List[str] = []
    for requirement in requirements:
        for scope in requirement.scopes:
            if scope not in scopes:
                scopes.append(scope)
    unknown = [r.operation for r in requirements if r.state == "unrecognised"]
    return tuple(scopes), tuple(unknown)


def call_cost(for_operations: Sequence[str]) -> int:
    """How many API calls :func:`check_permissions` would spend on this operation set.

    Published as its own function so the cost is knowable **before** it is spent. A caller must
    never discover that a "quick check" was a handful of throttled calls.
    """
    scopes, _unknown = scopes_for_operations(for_operations)
    probeable = {probe.scope for probe in PROBES}
    return len([scope for scope in scopes if scope in probeable])


class _PreflightProbeClient(CredentialedRawHttpClient):
    """A read-only client for the probe calls, on the shared raw-HTTP skeleton.

    Rides the same transport as every other surface so the token handling, header construction
    and error typing are not reimplemented here. It only ever issues GETs.
    """

    def __init__(self, app_id, app_secret, domain="larksuite.com", urlopen=None,
                 timeout=30):
        # The shared skeleton documents these four as the subclass's own responsibility
        # (``_base`` / ``_urlopen`` / ``_timeout`` / ``_token``), so they are set here rather
        # than inherited.
        self._base = api_base(domain)
        self._urlopen = urlopen if urlopen is not None else urllib.request.urlopen
        self._timeout = timeout
        self._token = None
        self._app_id = app_id
        self._app_secret = app_secret
        self._domain = domain
        self._token_fetcher = fetch_tenant_access_token

    def _credential_pair(self):
        """The READ pair, as resolved right now — every probe is a GET and this client
        consults no other pair (LD-672). ``preflight`` is the one surface a consumer runs
        *because* something is wrong, so a rejected pair here must name the variable to fix
        rather than escape as an untyped failure."""
        return resolved_read_env()

    def probe(self, probe: ScopeProbe) -> dict:
        """Issue one probe and hand back Lark's parsed answer. GET only, by construction."""
        assert probe.method == "GET", "a preflight probe is a read; nothing else is allowed"
        return self._send(probe.method, probe.path, params=dict(probe.params), body=None)


def _verdict_from_answer(probe: ScopeProbe, answer, credential_env) -> ScopeVerdict:
    """Turn one probe's answer into a verdict.

    The whole classification, and it rests on the ordering the live probe established: a scope
    denial means the scope is **missing**; any other error means the call got **past** the scope
    gate and failed on the resource that deliberately does not exist — which is the positive
    signal. A success would be surprising (the id is bogus) but is still positive.
    """
    code = answer.get("code") if isinstance(answer, dict) else None
    msg = answer.get("msg") if isinstance(answer, dict) else None
    denial = _perm.denial_from(code, msg, body=answer, credential_env=credential_env)
    if denial is not None and probe.scope in denial.scopes:
        return ScopeVerdict(scope=probe.scope, basis="probed", held=False, denial=denial,
                            note="Lark refused the probe naming this scope")
    if denial is not None:
        # A denial naming some OTHER scope: the endpoint needs something we did not ask about,
        # so this probe cannot speak to the scope it was aimed at. Say so rather than guess.
        return ScopeVerdict(
            scope=probe.scope, basis="unknown", held=None, denial=denial,
            note=("the probe was refused for a different permission ("
                  + ", ".join(denial.scopes) + "), so it could not decide this one"))
    return ScopeVerdict(
        scope=probe.scope, basis="probed", held=True,
        note=("the probe reached past the permission gate and failed on the deliberately "
              "nonexistent target, which is what holding the scope looks like"))


def check_permissions(for_operations: Sequence[str], *, domain: str = "larksuite.com",
                      probe=None, credentials=None) -> PermissionCheck:
    """**Optional, advisory.** Do I hold what these operations need?

    ``for_operations`` names operations as ``"get_docx_content"`` or, where a name is not
    unique, ``"docx-read.get_docx_content"``. An operation this library does not have is
    **refused cleanly** — reported in ``unknown_operations`` rather than guessed at or silently
    dropped, because a typo answered with a confident "you're fine" is worse than no check. A
    **surface id** (``"docx-read"``) raises :class:`~larkdocio.errors.LarkConfigError` naming
    the operations that surface has: it is a name this library hands out everywhere else, so
    answering it with an empty result would be that same confident nothing.

    Returns a :class:`PermissionCheck` whose every verdict states **how** it was reached
    (``probed`` / ``derived`` / ``unknown``), whose ``requirements`` say per operation **which
    kind of empty** an empty answer is, and whose ``blind_spots`` name what this mechanism
    structurally cannot see — including any operation whose requirement has never been
    observed. Read ``ok`` together with ``blind_spots``; and read the module docstring before
    treating a clean result as reassurance, since a **write** scope and a **field-level** grant
    are never probed.

    Costs :func:`call_cost` API calls — ask first if that matters. ``probe`` is injectable
    (``ScopeProbe -> Lark answer dict``), which is how this is exercised offline; ``credentials``
    overrides the ``(app_id, app_secret)`` pair.

    **This is never mandatory.** Nothing in the library calls it, no operation requires it, and
    skipping it changes nothing about how a real denial is reported: the uniform permission
    refusal fires identically either way.
    """
    operations = tuple(for_operations)
    requirements = requirements_for_operations(operations)
    scopes: List[str] = []
    for requirement in requirements:
        for scope in requirement.scopes:
            if scope not in scopes:
                scopes.append(scope)
    unknown_operations = tuple(
        r.operation for r in requirements if r.state == "unrecognised")
    probes = {p.scope: p for p in PROBES}

    verdicts: List[ScopeVerdict] = []
    blind_spots: List[str] = []
    to_probe = [probes[scope] for scope in scopes if scope in probes]

    prober = probe
    if prober is None and to_probe:
        app_id, app_secret = credentials if credentials else get_read_credentials()
        # LD-580 made the comment below TRUE. Until then ``get_read_credentials`` returned
        # ``('','')`` and this branch was the only thing standing between a blank pair and the
        # probe client — the pragma described behaviour the getter did not have. The getter now
        # refuses first, so the only route still reaching here is an explicitly blank
        # ``credentials=`` tuple from a caller, which deserves the same typed answer.
        if not app_id or not app_secret:  # pragma: no cover - get_read_credentials raises first
            raise LarkConfigError(
                "check_permissions needs read credentials to probe; set "
                + " / ".join(READ_ENV))
        prober = _PreflightProbeClient(app_id, app_secret, domain=domain).probe

    calls_made = 0
    for scope in scopes:
        if scope in probes:
            answer = prober(probes[scope])
            calls_made += 1
            verdicts.append(_verdict_from_answer(probes[scope], answer, READ_ENV))
            continue
        reason = NOT_PROBEABLE.get(scope)
        if reason:
            verdicts.append(ScopeVerdict(scope=scope, basis="derived", held=None, note=reason))
            blind_spots.append(f"{scope}: {reason}")
        else:
            verdicts.append(ScopeVerdict(
                scope=scope, basis="unknown", held=None,
                note=("no read-only probe exists for this scope, so this check cannot speak "
                      "to it")))
            blind_spots.append(f"{scope}: no read-only probe exists for it")

    # The per-OPERATION blind spots. An operation whose requirement was never observed used to
    # contribute to neither list above — it derives no scope, so the loop never reached it, and
    # the library does have it, so it was not an unrecognised name either. That silence is what
    # turned an unmeasured requirement into an ok-shaped empty answer.
    for requirement in requirements:
        if requirement.state in ("unmeasured", "undetermined"):
            blind_spots.append(f"{requirement.operation}: {requirement.note}")
        elif requirement.state == "unrecognised":
            blind_spots.append(requirement.note)
        elif requirement.unresolved_call_sites:
            # THE PARTLY-DERIVED CASE, and it is not keyed on the scope list being empty: an
            # operation whose scopes are KNOWN can still have lost an endpoint family to a
            # seam, and a verdict list that looks complete is exactly the answer that needs
            # this said out loud.
            blind_spots.append(
                f"{requirement.operation}: the scopes above are what the registry could "
                f"derive, and {len(requirement.unresolved_call_sites)} seam(s) in this "
                "operation's implementation cannot be resolved statically, so the "
                "requirement may be short — capabilities(full=True) names each seam under "
                "this operation's 'unresolved_call_sites'")

    return PermissionCheck(
        operations=operations,
        verdicts=tuple(verdicts),
        calls_made=calls_made,
        advisory=True,
        blind_spots=tuple(blind_spots),
        unknown_operations=unknown_operations,
        requirements=requirements,
    )
