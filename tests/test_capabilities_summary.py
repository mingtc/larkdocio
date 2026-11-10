"""LD-475 — the front door of the machine-readable registry, and the ONE condition on it.

The defect: ``capabilities()`` was the whole registry, hundreds of kilobytes of it, and it was
the first thing a consumer called. Five dogfooding runs read it; one recorded a context-window
incident and two wrote a wrong conclusion into their journal because the key they read
(``operations``) held a *subset* of a surface's verbs.

The fix the maintainer ruled (2026-08-16) is the shape ``guide()`` already has: **summary by default,
the whole thing behind an explicit argument** — with **one binding condition**, and this file
is where it is held: *the summary may not become a second hand-maintained copy of the truth.*
It is a generated, drift-guarded projection of the payload, the way the two permission
documents are projections of the permission registry.

So the arms here are, in order: the default IS the summary and it is **bounded**; the summary
is **derived** (pass the payload, get the same summary); the summary is **complete** (no
shipped call site is missing from it) and **honest** (no name in it that the payload lacks) —
both directions red-proved against specimens rather than asserted; the summary module
**cannot reach** the sources the payload is projected from, and its source carries **no literal
name** of a surface, an operation, a flag or a document; and the two other doors
(``surface=``, and the mutually-exclusive refusal) behave as their docstring says.
"""
import ast
import json
import pathlib

import pytest

import larkdocio
from larkdocio.capabilities import _summary as summary_module
from larkdocio.capabilities._summary import summary, summary_bytes, summary_gaps
from test_index_ratio import is_index_sized  # LD-640 AC5: one spelling of the 20x ratio

#: The consulted-corpus reading budget this repo already uses for "a document a reader is
#: expected to hold in one go" (``PROGRESS_LOG_BYTE_THRESHOLD``, ``scripts/check-board.sh``).
#: Borrowed rather than invented: the number's meaning — *this is small enough to read* — is
#: exactly the claim the no-argument door makes.
READING_BUDGET = 32_768


@pytest.fixture(scope="module")
def payload():
    return larkdocio.capabilities(full=True)


@pytest.fixture(scope="module")
def default():
    return larkdocio.capabilities()


# --------------------------------------------------------------------------- #
# 1. The default IS the summary, and it is BOUNDED — the guard the old shape    #
#    lacked, so the regression that made the front door unreadable cannot recur.#
# --------------------------------------------------------------------------- #

def test_the_no_argument_default_is_the_SUMMARY(default, payload):
    assert default == summary(payload)
    assert default != payload
    assert type(default) is dict


def test_the_default_door_is_BOUNDED_and_the_payload_is_not(default, payload):
    """The specific regression this issue exists to prevent: the first call a consumer makes
    returning something too big to read. The budget is a ceiling, not a target — and the
    figures in the message are **measured here**, never typed."""
    small = summary_bytes(default)
    whole = summary_bytes(payload)
    assert small < READING_BUDGET, (
        f"the no-argument answer is {small} bytes, over the {READING_BUDGET}-byte reading "
        f"budget — it is the first call a consumer makes and it has to be readable")
    assert is_index_sized(small, whole), (
        f"the summary ({small} bytes) is not meaningfully smaller than the payload it "
        f"summarises ({whole} bytes); an index that costs what it indexes buys nothing")


def test_the_summary_is_JSON_round_trippable_with_no_coercion(default):
    """Same contract as the payload: JSON-native types only, so it survives a strict dump."""
    assert json.loads(json.dumps(default, sort_keys=True)) == default


# --------------------------------------------------------------------------- #
# 2. DERIVED — the maintainer's binding condition, in three independent ways.           #
# --------------------------------------------------------------------------- #

def test_the_summary_is_a_PURE_FUNCTION_of_the_payload(payload):
    """Hand it a payload and it answers about *that* payload. The proof is a payload with one
    surface removed: the summary loses exactly that surface and nothing else, which a
    hand-kept copy could not do."""
    victim = sorted(payload["surfaces"])[0]
    reduced = dict(payload, surfaces={k: v for k, v in payload["surfaces"].items()
                                      if k != victim})
    assert set(summary(reduced)["surfaces"]) == set(payload["surfaces"]) - {victim}
    assert summary(reduced)["counts"]["surfaces"] == len(payload["surfaces"]) - 1


def test_the_summary_MODULE_cannot_reach_the_registRIES_the_payload_is_built_from():
    """Structural, not a promise: the module imports the payload's key vocabulary and the
    stdlib, and nothing else at module scope — so there is no registry, client or op table it
    could read a second answer out of."""
    source = pathlib.Path(summary_module.__file__).read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.col_offset == 0:
            imported.add("." * node.level + (node.module or ""))
        elif isinstance(node, ast.Import) and node.col_offset == 0:
            imported |= {alias.name for alias in node.names}
    assert imported == {"inspect", "json", "._models"}, (
        f"the summary module's module-level imports are {sorted(imported)} — it may reach the "
        f"payload's own key vocabulary and the stdlib, and nothing that holds capability truth")


def test_the_summary_SOURCE_names_no_surface_operation_flag_or_document(payload):
    """The other half of the same condition, from the text side: a hand-maintained copy would
    have to *name* something. Every id the payload carries is searched for in the module's
    source; finding one would mean the summary states a fact of its own."""
    tree = ast.parse(pathlib.Path(summary_module.__file__).read_text(encoding="utf-8"))
    docstrings = {ast.get_docstring(node) for node in ast.walk(tree)
                  if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))}
    literals = {node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    literals -= docstrings
    ids = set(payload["surfaces"]) | set(payload["flags"]) | set(payload["docs"])
    ids |= set(payload["safety_contracts"]) | set(payload["entry_points"])
    for surface in payload["surfaces"].values():
        ids |= {row["name"] for row in surface["operations"]}
    found = sorted(literals & ids)
    assert not found, (
        f"the summary module carries a literal naming payload content: {found} — the summary "
        f"is a projection, and a name it spells itself is a second source of truth")


# --------------------------------------------------------------------------- #
# 3. COMPLETE and HONEST — bidirectional, both directions red-proved.           #
# --------------------------------------------------------------------------- #

def test_the_summary_OMITS_NO_shipped_call_site(payload, default):
    """The failure that matters. A consumer reading the default answer must not be able to
    conclude that a shipped verb does not exist — the 1.33.0 defect, one door up."""
    omitted, phantom = summary_gaps(payload, default)
    assert omitted == [], f"these shipped call sites are missing from the summary: {omitted}"
    assert phantom == [], f"the summary names call sites the payload does not carry: {phantom}"


def test_every_INDEX_in_the_summary_is_the_payloads_OWN_KEY_SET(payload, default):
    """A name in the summary is an address in the payload, so a reader who finds one knows
    where its full row is without being told a mapping."""
    for key in ("flags", "safety_contracts", "workflows", "docs", "entry_points"):
        assert default[key] == sorted(payload[key]), key
        assert default["counts"][key] == len(payload[key]), key
    assert set(default["surfaces"]) == set(payload["surfaces"])
    assert default["version"] == payload["version"] == larkdocio.__version__


def test_the_scopes_in_the_summary_are_the_surfaces_OWN_derived_union(payload, default):
    """``what does it need`` is half the opening question, so the scope STRINGS are in the
    summary — copied from the surface's own credentials block, which is itself the union of
    its operations' permission rows, so this is the third view of one fact and not a fourth
    assertion of it."""
    for sid, row in default["surfaces"].items():
        credentials = payload["surfaces"][sid]["credentials"]
        assert row["scopes"] == credentials["scopes"], sid
        assert row["optional_scopes"] == credentials["optional_scopes"], sid


_SPECIMEN = {
    "surfaces": {"a-surface": {
        "title": "t", "domain": "d", "mode": "read",
        "credentials": {"scopes": [], "optional_scopes": []},
        "operations": [{"name": "op_one", "kind": "operation",
                        "projected_from": "larkdocio.x"}],
    }},
    "version": "0.0.0",
}


def test_the_completeness_arm_bites_RED_on_an_OMITTED_call_site():
    """Direction 1, red-proved in-process: a summary that dropped a row reddens and NAMES it.

    The specimen is a summary built by the real function and then damaged, so what is proved
    is that the check bites — not that a hand-made pair of dicts differ.
    """
    damaged = summary(_SPECIMEN)
    damaged["surfaces"]["a-surface"]["operations"] = []
    omitted, phantom = summary_gaps(_SPECIMEN, damaged)
    assert omitted == [("a-surface", "op_one")]
    assert phantom == []


def test_the_completeness_arm_bites_RED_on_a_PHANTOM_row():
    """Direction 2: a summary naming an operation the payload does not carry — a name a caller
    cannot follow to a row."""
    damaged = summary(_SPECIMEN)
    damaged["surfaces"]["a-surface"]["operations"].append(
        {"name": "an_op_that_was_deleted", "kind": "operation"})
    omitted, phantom = summary_gaps(_SPECIMEN, damaged)
    assert omitted == []
    assert phantom == [("a-surface", "an_op_that_was_deleted")]


def test_the_completeness_arm_bites_RED_on_a_WHOLE_SURFACE_a_summary_invented():
    damaged = summary(_SPECIMEN)
    damaged["surfaces"]["a-surface-that-does-not-exist"] = {"operations": [{"name": "x"}]}
    omitted, phantom = summary_gaps(_SPECIMEN, damaged)
    assert phantom == [("a-surface-that-does-not-exist", "x")]


def test_the_completeness_arm_bites_RED_on_a_CALL_SITE_THAT_ESCAPED_the_one_key():
    """The collapse's own failure shape: a call site published under some *other* key. The
    payload side is duck-typed off the row shape, so it is found and reported as omitted
    rather than quietly falling outside the walk."""
    escaped = {"surfaces": {"a-surface": dict(
        _SPECIMEN["surfaces"]["a-surface"],
        legs=[{"name": "a_leg_nobody_indexed", "kind": "leg",
               "projected_from": "larkdocio.x"}])}}
    omitted, phantom = summary_gaps(escaped)
    assert omitted == [("a-surface", "a_leg_nobody_indexed")]


# --------------------------------------------------------------------------- #
# 4. The other doors: one surface, and the refusals.                            #
# --------------------------------------------------------------------------- #

def test_the_reading_block_SPELLS_CALLS_THAT_WORK(default, payload):
    """The front door names your next call, and the names are read off the function's own
    signature — so this asserts the spellings actually run and return what they promise."""
    reading = default["reading"]
    assert reading["everything"] == "capabilities(full=True)"
    example = reading["one_surface"]
    assert example.startswith("capabilities(surface=")
    surface_id = example.split("'")[1]
    assert larkdocio.capabilities(surface=surface_id) == payload["surfaces"][surface_id]


def test_the_reading_block_DISCLOSES_THE_SIZE_OF_WHAT_THE_NEXT_CALL_RETURNS(default, payload):
    """LD-571 — and the shape is ``guide()``'s, deliberately.

    Two dogfooding legs blew a tool output limit on the front door because nothing told them how
    big the next call was. ``guide()`` has solved this since LD-468 by disclosing the size of
    what the **next** call returns; *"disclose your own size"* read literally is a fixed point,
    because inserting the count changes the count.

    So the summary discloses ``full=True``'s size, and the assertion below is a **derivation**
    check rather than a spelling check: the figure has to move when the payload moves, which a
    hard-coded number could not do. The exact-string pin on ``everything`` is kept beside it —
    the sibling key is an addition, and nothing that worked before answers differently.
    """
    reading = default["reading"]
    assert reading["everything"] == "capabilities(full=True)"
    disclosed = reading["everything_is_this_big"]
    real = summary_module.json_bytes(payload)
    assert f"{real:,}" in disclosed, (
        f"the disclosure does not carry the payload's real size ({real:,}): {disclosed!r}")

    victim = sorted(payload["surfaces"])[0]
    reduced = dict(payload, surfaces={k: v for k, v in payload["surfaces"].items()
                                     if k != victim})
    assert summary(reduced)["reading"]["everything_is_this_big"] != disclosed, (
        "the size did not move when the payload lost a surface — the figure is a literal, not "
        "a measurement, which is the whole defect a stated size is supposed to avoid")
    assert summary_module.json_bytes(reduced) < real


def test_ONE_SURFACE_is_the_payloads_own_row(payload):
    for sid, surface in payload["surfaces"].items():
        assert larkdocio.capabilities(surface=sid) == surface


def test_an_UNKNOWN_surface_raises_and_NAMES_EVERY_SURFACE(payload):
    """The ``guide(section=…)`` rule: recovering from a wrong name takes no second call."""
    with pytest.raises(ValueError) as excinfo:
        larkdocio.capabilities(surface="no-such-surface")
    message = str(excinfo.value)
    for sid in payload["surfaces"]:
        assert sid in message, sid


def test_asking_for_ONE_SURFACE_and_EVERYTHING_at_once_is_refused():
    """Two requests in one call, refused rather than silently answered — the same rule
    ``guide(section=…, full=True)`` follows."""
    with pytest.raises(ValueError) as excinfo:
        larkdocio.capabilities(surface="docx-read", full=True)
    assert "not both" in str(excinfo.value)


def test_the_registry_is_still_reachable_WHOLE(payload):
    """The breaking change moved the payload; it did not shrink it. Everything the registry
    ever carried is one explicit argument away."""
    assert set(payload) >= {"version", "surfaces", "flags", "safety_contracts", "docs",
                            "entry_points", "workflows"}
    assert payload["surfaces"], "the whole registry came back empty"


# --------------------------------------------------------------------------- #
# 5. LD-596 — an empty scope list is not "needs nothing": the door says which   #
#    endpoints' requirement is UNRECORDED, derived, endpoint names only.        #
# --------------------------------------------------------------------------- #

def _unrecorded_by_surface(payload):
    """``{surface_id: sorted endpoint keys}`` folded from the payload's OWN per-operation
    permission rows — the second, independent derivation the assertions below compare the
    summary against. Computed, never spelled: a registry change moves it.
    """
    out = {}
    for sid, surface in (payload.get("surfaces") or {}).items():
        keys = set()
        for op in surface.get("operations") or ():
            keys |= set((op.get("permissions") or {}).get("unknown_requirements") or ())
        if keys:
            out[sid] = sorted(keys)
    return out


def _surfaces_claiming_NEITHER(payload_summary):
    """The surfaces on which LD-460's rule — *never both empty* — is broken: a surface that
    names no scope and names no unrecorded endpoint either, so its silence has no reading.
    Injectable and pure, so the arm below can be red-proved against a specimen.
    """
    return sorted(sid for sid, row in (payload_summary.get("surfaces") or {}).items()
                  if not row.get("scopes") and not row.get("unknown_requirements"))


def test_the_summary_NAMES_the_endpoints_whose_requirement_is_UNRECORDED(payload, default):
    """The defect: the default door printed a bare ``"scopes": []`` and a reader concluded the
    surface needs no Lark permission, where the registry's own answer is *unrecorded*. The key
    lands on exactly the surfaces the payload says have one, and its value is that surface's
    own union — both sides derived here, so nothing is a hard-coded list of surface names.
    """
    expected = _unrecorded_by_surface(payload)
    assert expected, "the payload records no unknown requirement at all — probe first"
    carried = {sid: row["unknown_requirements"] for sid, row in default["surfaces"].items()
               if "unknown_requirements" in row}
    assert carried == expected


def test_NEVER_BOTH_EMPTY__a_surface_naming_no_scope_names_its_unknowns(default):
    """LD-460's AC1, generalised to this door: a surface may say what it needs, or say which
    endpoints' requirement was never observed — it may not say neither, because an empty list
    with nothing beside it reads as *needs no permission* and that is not what it means.
    """
    assert _surfaces_claiming_NEITHER(default) == []


def test_the_never_both_empty_arm_bites_RED_on_a_SILENT_surface():
    """Red-proved in-process against a specimen the real function summarised: a surface with no
    scope and no unrecorded endpoint is reported and NAMED, so the arm above is a check.
    """
    assert _surfaces_claiming_NEITHER(summary(_SPECIMEN)) == ["a-surface"]


def test_the_unrecorded_endpoint_names_are_ADDRESSES_into_the_payloads_CATALOG(payload, default):
    """NAMES, NOT PROSE. Every value is an endpoint key of the payload's own top-level
    ``unknown_requirements`` catalog — which proves at once that the summary explains nothing
    (the reasons stay in the catalog) and that it invented nothing.
    """
    catalog = set(payload["unknown_requirements"])
    assert catalog
    for sid, row in default["surfaces"].items():
        for key in row.get("unknown_requirements") or ():
            assert key in catalog, (sid, key)
            assert isinstance(key, str)


def test_the_disclosure_is_NOT_KEYED_ON_AN_EMPTY_scope_list(default):
    """The reason the fix is thirteen surfaces and not six: a surface can print a
    complete-LOOKING scope list and still reach endpoints whose requirement is unrecorded.
    Keying on emptiness would have fixed the six and locked the other seven in.
    """
    both = sorted(sid for sid, row in default["surfaces"].items()
                  if row.get("scopes") and row.get("unknown_requirements"))
    assert both, ("no surface carries both a real scope and an unrecorded endpoint — the "
                  "disclosure is keyed on emptiness, which under-reports")


def test_the_reading_block_says_an_EMPTY_SCOPE_LIST_MAY_MEAN_UNKNOWN(default):
    """AC5 — the sentence the empty list is read against. It must point at the new key by its
    own name (read off the payload's vocabulary, not typed here) and must no longer let an
    empty scope list be read alone.
    """
    from larkdocio.capabilities._models import UNKNOWN_REQUIREMENTS_KEY

    this_is = default["reading"]["this_is"]
    assert UNKNOWN_REQUIREMENTS_KEY in this_is
    assert "unrecorded" in this_is
    assert "the scopes each surface needs" not in this_is
