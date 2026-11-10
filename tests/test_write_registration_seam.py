"""LD-633 — the **write** op registration seam: the apply-path count stops being hand-kept,
and the registration-seam scanner is pointed at a second package.

**The defect this module closes.** ``larkdocio.write.ops.OPS`` is the ONE registration seam
for the docx write engine — four generic dispatch chains read their behaviour off it — but the
sentence that *maps the paths which write a customer's document* was hand-kept, and it went
stale twice: ``write/apply.py``'s module docstring said **five** resolved-entry paths, last
touched 2026-07-28, while ``comment-create``/``comment-remove`` landed 2026-07-30 and
``grow-table`` on 2026-08-25 — understated by three across two op additions for 35 days. This
is the identical defect ``tests/test_sheets_registration_seam.py`` (LD-213) was written for on
the sheets side, and that guard's scan had never been pointed anywhere else. So the deliverable
here is not the corrected sentence — a sentence re-creates the defect at the next op addition.
It is the scan, generalised over its corpus (``tests/registration_seam.py``) and enrolled on
``write/``.

**THE DECLARED BASIS — EIGHT reachable apply implementations (D-115), and it is declared so
that there cannot be a third reading.** ``OPS`` holds **seven** op kinds and dispatches to
**eight** implementations (``_apply_edit`` is a sub-dispatch wrapper that routes table-cell vs
narrative by ``entry.cell``). Three bases were defensible — 8 reachable implementations,
``len(OPS)`` = 7, or 6 excluding the comment ops — and the ruling took **eight**, because the
claim the sentence makes is a *safety* claim (*every path carries its own live re-validation
and emits exactly one apply-log record*) and the unit a safety claim about writing must count
is **the implementation that touches the customer's document**, not the op kind that names it.
``len(OPS)`` would certify a path it never counted; excluding the comment ops would place two
genuinely writing paths outside a guarantee whose whole value is being exhaustive.

The number is **derived here, once** — :func:`reachable_apply_implementations` — and
``write/apply.py``'s sentence names that helper, mirroring the sheets side which declared its
basis explicitly *"so there would not be a third"*. Nothing hand-types eight.

**THE MECHANISM IS REGISTRATION-SEAM COMPLETENESS, AND A HELPER-CALL CENSUS IS BANNED
(D-115).** This is the binding half of the ruling and it was bought with a measured mistake.
An AST pass over the eight implementations reports that exactly the three the stale docstring
omitted — ``grow-table``, ``comment-create``, ``comment-remove`` — call **no** shared
re-validation helper, which reads as *three write paths skipping the staleness gate*. **It is
FALSE, and there is no safety gap:** ``_apply_grow_table`` re-reads the live block and refuses
``stale_anchor`` **inline** when it is no longer a table; ``_apply_comment_create`` creates a
whole-document comment which has **no anchor to re-validate by construction**; and
``_apply_comment_remove``'s read → judge → delete sequence **is** the validation (every reply
must be the application's own, decided before the first delete). Validation is a **property**,
and three of the eight satisfy it without the shared helper — so this module counts
**registrations and reachability**, never helper calls, and the corrected docstring states each
path's own answer rather than implying one mechanism.

**What is guarded, in both directions**

* **The scan** walks the **source text** of every module under ``src/larkdocio/write/`` and
  finds every apply-path arity claim. Each one must state the derived count, so a new
  hand-typed number cannot land anywhere in the package — comments included.
* **The registered sites** (:data:`_CLAIM_SITES`) name the two docstrings that must carry the
  claim and/or name every implementation, so a site that *loses* its sentence reddens instead
  of going quiet.
* **The census** (the last section) asserts the registry and the implementations agree in both
  directions: every registered op kind dispatches to an implementation this tree defines, no
  implementation is orphaned out of the registry, and every kind round-trips through
  request deserialization to its own ``request_type``.

**What must NOT bite** — a guard that cries wolf is a guard someone weakens. The write package
counts *subsets* of the apply paths in five true sentences (*"the three text paths differ"*,
*"the three single-re-validation write paths (narrative / insert / delete)"*, *"the pre-write
re-validation those three paths call"*, …). A guard that reddened on those would be crying wolf
about a different population, so the discriminator is the **whole modifier phrase**, enumerated
in :data:`_ARITY_MODIFIERS` — not the last word alone (which is how ``write paths`` would have
swept up a subset claim) and not an allowlist of sites.

**And ``ops.py``'s "Five ops × four chains was the classic seam" is correct AS HISTORY and
stays** (D-115 § E1): it is registered in :data:`_HISTORICAL_CLAIMS` with its reason, verified
structurally to be past tense and to name its era. Tense alone does not suffice, because the
risk is not a reader mistaking history for the present — it is a future reader "correcting" a
true historical statement into a false current one, which is strictly worse and leaves no trace
that it was ever history.
"""
import ast
import re

import pytest

import registration_seam
from registration_seam import REPO_ROOT
from larkdocio.write import model as write_model
from larkdocio.write.model.requests import _request_from_dict
from larkdocio.write.ops import BY_KIND, OPS, classify
from domain_vocabulary import RETIRED_ID

_WRITE_SRC = REPO_ROOT / "src" / "larkdocio" / "write"

#: The op kind that is deliberately **tagless** on the wire — its serialization predates the
#: ``"op"`` tag and stays byte-compatible, so the deserializer's fallback arm IS its
#: registration. Named here because the ladder census below has to exclude exactly it.
_TAGLESS_KIND = "edit"


# --------------------------------------------------------------------------- #
# THE DECLARED BASIS — derived, in ONE place.                                   #
# --------------------------------------------------------------------------- #

def _module_level_apply_functions():
    """``{name: (path, FunctionDef)}`` for every module-level ``_apply_*`` in ``write/``.

    Read off the **source text** rather than by import, so a function that stopped being
    reachable is still seen (that is the orphan case the census below reports)."""
    found = {}
    for path in sorted(_WRITE_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("_apply_"):
                assert node.name not in found, (
                    f"two module-level definitions of {node.name} — this derivation keys on "
                    f"the name")
                found[node.name] = (path.relative_to(REPO_ROOT).as_posix(), node)
    return found


def _apply_calls(node) -> set:
    """The ``_apply_*`` functions ``node`` itself calls — how a sub-dispatch wrapper is told
    from a leaf. This is a **structure** question (who dispatches to whom), NOT the banned
    helper-call census (which asked *whether a path calls one particular validation helper*
    and got a confident, wrong answer)."""
    return {n.func.id for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id.startswith("_apply_")}


def registered_apply_names() -> tuple:
    """The apply callable each registered op dispatches to, in registry order."""
    return tuple(desc.apply.__name__ for desc in OPS)


def reachable_apply_implementations() -> dict:
    """**THE declared basis: ``{name: path}`` for every apply implementation reachable through
    the ``OPS`` dispatch** — the one helper ``write/apply.py``'s sentence is pinned to.

    Start from the registered apply callables, follow every ``_apply_*`` call they make (which
    is how ``_apply_edit``'s two leaves join), and keep the **leaves** — the implementations
    that dispatch to no further apply path and therefore are the code that touches the
    document. A ninth op moves this by one; a new sub-dispatch wrapper contributes its leaves
    and not itself.
    """
    defined = _module_level_apply_functions()
    missing = [name for name in registered_apply_names() if name not in defined]
    assert not missing, (
        f"the registry dispatches to {missing}, which this tree defines nowhere at module "
        f"level — the derivation cannot see it, so the basis would silently undercount")

    closure, frontier = set(), list(registered_apply_names())
    while frontier:
        name = frontier.pop()
        if name in closure or name not in defined:
            continue
        closure.add(name)
        frontier.extend(_apply_calls(defined[name][1]))

    return {name: defined[name][0] for name in sorted(closure)
            if not _apply_calls(defined[name][1])}


def _expected_labels() -> tuple:
    """The labels a prose list must name — one per reachable implementation, DERIVED."""
    return tuple(sorted(reachable_apply_implementations()))


def _expected_count() -> int:
    return len(reachable_apply_implementations())


# --------------------------------------------------------------------------- #
# The claim scanner — the shared mechanism, this package's policy.              #
# --------------------------------------------------------------------------- #

#: The population nouns an apply-path arity claim can use, and — per noun — the **whole**
#: modifier phrases that make the phrase a claim about the arity rather than about a subset or
#: a different population. The full phrase is the discriminator (not the last word) because
#: ``the three single-re-validation write paths`` is a TRUE subset claim whose last word is
#: ``write``; enumerating phrases keeps that structurally out of scope instead of allowlisting
#: the file it lives in.
#: **``path``/``paths`` deliberately has NO bare (``""``) entry, and LD-628 AC1f measured the
#: price of adding one instead of assuming it.** The hand-over said the ``""`` entry catches a
#: bare *"eight paths"* and breaks none of the eight must-not-bite cases. Re-measured
#: 2026-09-03 with the entry added, that is **not so**: it bites the must-not-bite case *"the
#: pre-write re-validation those three paths call"* (nothing sits between the count and the
#: noun, so the modifier phrase is empty and a TRUE subset claim becomes an arity claim), and
#: it reddens FOUR live sentences in ``src/larkdocio/write/**`` — three *"three paths"* and one
#: *"two paths"*, each a true statement about a subset. That is a guard crying wolf on correct
#: prose, which is how a guard gets weakened, so the widening was **declined** rather than
#: landed. What would make it safe is a discriminator that tells *"those three paths"* from
#: *"eight paths"* — a real design question with its own cry-wolf risk, not a refactor. The
#: bare shape is pinned as out-of-scope in the must-not-bite set below, beside the same
#: exemption for bare ``<count> ops``.
_ARITY_MODIFIERS = {
    "implementation": ("", "apply", "reachable apply"),
    "implementations": ("", "apply", "reachable apply"),
    "path": ("resolved-entry", "apply"),
    "paths": ("resolved-entry", "apply"),
}

#: The pre-registry ``N ops × M chains`` shape — the one ``ops`` claim shape that is about this
#: seam's arity. A bare ``<count> ops`` is NOT scanned: in this package it counts the two
#: out-of-band media ops or a named subset (*"the two comment ops"*), which are different
#: populations with no qualifier to tell them apart.
_CHAIN_SHAPE = re.compile(r"^ops\s*(?:×|x)\s")

_NOUN_RE = (r"implementations?|paths?|ops\s*(?:×|x)\s*(?:"
            + "|".join(sorted(registration_seam.SCANNED_COUNTS, key=len, reverse=True))
            + r")\s+chains?")


def _is_arity_claim(claim) -> bool:
    if _CHAIN_SHAPE.match(claim.noun):
        return claim.mods == ""
    return claim.mods.lower() in _ARITY_MODIFIERS.get(claim.noun.lower(), ())


#: **The write seam**, as the shared scanner needs it.
_SEAM = registration_seam.Seam(
    package="larkdocio.write",
    source_dir=_WRITE_SRC,
    noun_re=_NOUN_RE,
    is_arity_claim=_is_arity_claim,
    population="reachable apply implementations",
)


def _claims_in(text: str, path: str, line_offset: int = 1) -> list:
    return registration_seam.claims_in(_SEAM, text, path, line_offset)


def _scan_claims() -> list:
    return registration_seam.scan_claims(_SEAM)


def _docstring(site: str) -> str:
    return registration_seam.docstring(site)


# --------------------------------------------------------------------------- #
# The registers.                                                                #
# --------------------------------------------------------------------------- #

#: The docstrings that MUST carry the claim → ``(states the arity, names every
#: implementation)``. Two sites, and they are the two the audit named: the module docstring
#: (the map: the count plus the per-path list) and ``apply()``'s own dispatch list, which
#: enumerated six bullets for eight paths.
_CLAIM_SITES = {
    "larkdocio.write.apply": (True, True),
    "larkdocio.write.apply:apply": (False, True),
}

#: The EXPLICIT historical-narration register (D-115 § E1). Keyed ``(file, claim text
#: lowercased)`` → why the claim is correct as history. An explicit register, not a loose rule:
#: an unknown site can never wear this exemption, and every entry is verified structurally
#: below (past tense AND its era named).
_HISTORICAL_CLAIMS = {
    ("src/larkdocio/write/ops.py", "five ops × four chains"): (
        "ops.py's own narration of the state this module REPLACED — four parallel per-op "
        "isinstance/op-string dispatch ladders, when the surface held five ops. Correct as "
        "history; 'correcting' it to the current arity would falsify the paragraph that "
        "explains why the registry exists, and would leave no trace that it was ever "
        "history."),
}

#: Past-tense markers + era citations — how a registered HISTORICAL claim is verified to
#: actually be history rather than a drifted claim wearing an exemption.
_PAST_TENSE_RE = re.compile(r"\b(was|were|had|used to|grew|meant)\b", re.IGNORECASE)
_ERA_RE = re.compile(r"\b(LD-\d+|pre-registry)\b|" + RETIRED_ID.pattern)


def _violations(expected: int, expected_labels=None) -> list:
    """Every way the tree's apply-path claims disagree with ``expected`` — the single function
    both the live assertion and the ninth-implementation bite proof drive."""
    labels = tuple(expected_labels if expected_labels is not None else _expected_labels())
    problems = []

    for claim in _scan_claims():
        if (claim.path, claim.text.lower().replace("*", "")) in _HISTORICAL_CLAIMS:
            continue
        if claim.stated != expected:
            problems.append(
                f"{claim.site}: says {claim.text!r} but the registry dispatches to "
                f"{expected} {_SEAM.population}")

    for site, (states_arity, names_all) in _CLAIM_SITES.items():
        doc = _docstring(site)
        claims = _claims_in(doc, site)
        if states_arity:
            if not claims:
                problems.append(
                    f"{site}: no apply-path arity claim found — the sentence was removed or "
                    f"reworded out of the guarded shape")
            for claim in claims:
                if claim.stated != expected:
                    problems.append(
                        f"{site}: says {claim.text!r} but the registry dispatches to "
                        f"{expected}")
        if names_all:
            for label in labels:
                if label not in doc:
                    problems.append(f"{site}: the path list does not name {label!r}")
    return problems


# =========================================================================== #
# AC1 + AC3 — the basis is declared, derived, and eight.                       #
# =========================================================================== #

def test_the_declared_basis_is_eight_reachable_apply_implementations():
    """D-115 § E2, pinned. The count is derived from ``OPS`` + the dispatch structure; this
    test names the eight so that a ninth reddens **here**, where the ruling is cited, rather
    than only in a docstring diff."""
    reachable = reachable_apply_implementations()
    assert set(reachable) == {
        "_apply_narrative",
        "_apply_table_cell",
        "_apply_insert",
        "_apply_delete",
        "_apply_subspan",
        "_apply_grow_table",
        "_apply_comment_create",
        "_apply_comment_remove",
    }, sorted(reachable)
    assert len(reachable) == 8
    assert reachable["_apply_comment_create"] == "src/larkdocio/write/comments.py"


def test_the_basis_is_NOT_len_OPS_and_the_difference_is_the_edit_wrapper():
    """Why the two numbers differ, asserted rather than explained: ``len(OPS)`` is seven
    because ``edit`` dispatches through ``_apply_edit``, which is a **wrapper** routing
    table-cell vs narrative. Counting op kinds would certify a path it never counted."""
    assert len(OPS) == 7
    registered = set(registered_apply_names())
    reachable = set(reachable_apply_implementations())
    assert registered - reachable == {"_apply_edit"}
    assert reachable - registered == {"_apply_narrative", "_apply_table_cell"}
    assert _apply_calls(_module_level_apply_functions()["_apply_edit"][1]) == {
        "_apply_narrative", "_apply_table_cell"}


def test_every_apply_path_claim_in_the_write_package_is_derived():
    """AC1 + AC3: every apply-path arity claim in ``src/larkdocio/write/**`` states the derived
    count, both registered sites still carry their claim, and both name every
    implementation."""
    assert _violations(_expected_count()) == []


def test_each_reachable_implementation_returns_exactly_ONE_apply_log_entry():
    """The second predicate the guarded sentence asserts, held against code truth: every
    reachable implementation is annotated to return **one**
    :class:`~larkdocio.write.model.ApplyLogEntry` — not a list, not an
    :class:`~larkdocio.write.model.ApplyLog`. Together with ``apply()``'s loop, which appends
    exactly one entry per plan entry, that is what makes the log 1:1 with the plan (pinned as
    a property under randomized failure injection in
    ``tests/test_apply_disposition_invariant.py``). The interior wrapper is excluded
    deliberately: it emits nothing of its own."""
    defined = _module_level_apply_functions()
    for name in reachable_apply_implementations():
        returns = defined[name][1].returns
        assert isinstance(returns, ast.Name) and returns.id == "ApplyLogEntry", (
            f"{name} is annotated {ast.dump(returns) if returns else None} — every apply "
            f"implementation answers with exactly one apply-log entry")


# =========================================================================== #
# AC1 — the bite, proved.                                                      #
# =========================================================================== #

def test_a_ninth_apply_implementation_reddens_every_claim_site():
    """The in-suite equivalent of registering a ninth op: raise the derived count by one and
    add a label, and **every** registered site must be named in the report. A guard that does
    not visibly bite on a ninth path is decoration."""
    problems = _violations(_expected_count() + 1, _expected_labels() + ("_apply_dummy",))
    assert problems, "a ninth implementation changed nothing — the guard is decoration"
    for site in _CLAIM_SITES:
        assert any(p.startswith(site + ":") for p in problems), (site, problems)
    assert sum("does not name '_apply_dummy'" in p for p in problems) == sum(
        names_all for _, names_all in _CLAIM_SITES.values())
    # …and the file-level scan names the source site too, by path:line.
    assert any(re.match(r"src/larkdocio/write/\w+\.py:\d+:", p) for p in problems), problems


def test_dropping_one_implementation_name_from_the_module_map_reddens():
    """The list half's evidence clause: a mutation that drops a single path from the module
    map is reported, naming the site and the missing implementation."""
    doc = _docstring("larkdocio.write.apply")
    assert "_apply_grow_table" in doc
    mutated = doc.replace("_apply_grow_table", "_apply_something_else")
    assert "_apply_grow_table" not in mutated
    missing = [label for label in _expected_labels() if label not in mutated]
    assert missing == ["_apply_grow_table"], missing


# =========================================================================== #
# AC4 — the registered historical claim.                                       #
# =========================================================================== #

def test_the_historical_narration_is_registered_and_really_is_history():
    """AC4 / D-115 § E1: ``ops.py``'s *"Five ops × four chains was the classic seam"* is exempt
    by an EXPLICIT register, and the exemption is verified structurally — the sentence must be
    past tense AND name its era, so the register cannot shelter a present-tense claim that
    simply drifted."""
    assert len(_HISTORICAL_CLAIMS) == 1, (
        "a second historical exemption appeared — each one needs its own reason and its own "
        "structural check, not a widened allowlist")
    for (path, text), reason in _HISTORICAL_CLAIMS.items():
        claims = [c for c in _scan_claims()
                  if c.path == path and c.text.lower().replace("*", "") == text]
        assert claims, f"registered historical claim {text!r} is no longer in {path} — stale"
        for claim in claims:
            assert _PAST_TENSE_RE.search(claim.sentence), (
                f"{claim.site} wears the historical exemption but reads as present tense: "
                f"{claim.sentence!r}")
            assert _ERA_RE.search(claim.sentence), (
                f"{claim.site} wears the historical exemption but names no era: "
                f"{claim.sentence!r}")
        assert len(reason) > 80, "an exemption needs a reason, not a label"


def test_the_historical_claim_would_otherwise_be_caught():
    """Anti-vacuity for the exemption above: without the register the sentence IS a claim the
    scanner reports — so the exemption is load-bearing and the scanner is not simply blind."""
    claims = _claims_in((_WRITE_SRC / "ops.py").read_text(encoding="utf-8"),
                        "src/larkdocio/write/ops.py")
    stale = [c.text.lower().replace("*", "") for c in claims
             if c.stated != _expected_count()]
    assert stale == ["five ops × four chains"], claims


# =========================================================================== #
# AC1's must-not-bite set — the true subset claims in the live tree.           #
# =========================================================================== #

@pytest.mark.parametrize("prose", [
    "the three text paths differ",
    "the pre-write re-validation those three paths call",
    "Reached by the three single-re-validation paths through _revalidated_or_stale",
    "The single opening of the three single-re-validation write paths (narrative / insert / "
    "delete)",
    "These two ops are the only docx writes that position with a bare integer",
    "Two ops, one route",
    "the two comment ops",
    "a helper-call census produces a confident, wrong 'three write paths skip the staleness "
    "gate'",
    # THE BARE SHAPE, out of scope on purpose — the same carve-out bare ``<count> ops`` has,
    # and for the same reason: in this package a bare ``<count> paths`` is how the true SUBSET
    # sentences above are spelled (four of them live in ``write/`` today), so scanning it would
    # redden correct prose. Measured, and the measurement is in :data:`_ARITY_MODIFIERS`'s own
    # comment (LD-628 AC1f). Pinned here so a future widening has to move this line and read
    # the reason.
    "eight paths",
])
def test_a_count_about_a_subset_or_another_population_never_matches(prose):
    """A count word about a **subset** of the apply paths, or about a different population of
    ops entirely, is not an arity claim. Every string here is (or paraphrases) a sentence in
    the live tree, and every one of them is TRUE — a guard that reddened on them would be
    crying wolf, which is how a guard gets weakened."""
    assert _claims_in(prose, "synthetic.py") == []


@pytest.mark.parametrize("prose", [
    "**eight** reachable apply implementations ride this one plan-gated pipeline",
    "eight apply implementations",
    "five resolved-entry paths ride this one plan-gated pipeline",
    "Five ops × four chains was the classic seam",
])
def test_the_guarded_shapes_do_match(prose):
    """Anti-vacuity for the case above: the shapes the corrected site actually uses, the stale
    shape it replaced, and the registered historical shape ARE recognised — so the must-not-bite
    cases pass for the right reason."""
    assert len(_claims_in(prose, "synthetic.py")) == 1, prose


def test_the_write_corpus_is_the_write_package_and_nothing_else():
    """The scan is enrolled on ``write/`` — not on the sheets tree (whose own arity is a
    different population held by its own guard), and not on any Markdown."""
    corpus = {c.path for c in _scan_claims()}
    assert corpus, "the scanner found nothing at all — the corpus path is wrong"
    assert all(p.startswith("src/larkdocio/write/") and p.endswith(".py") for p in corpus)


# =========================================================================== #
# AC5 — the round-trip census over OPS.                                        #
# =========================================================================== #

_ANCHOR = write_model.AnchorById("blk1")

#: One representative request per registered op kind — keyed off ``OPS``, so a new op with no
#: sample reddens :func:`test_every_registered_op_kind_has_a_census_sample` rather than
#: quietly not being censused.
_SAMPLES = {
    "insert": write_model.InsertRequest(
        reference=_ANCHOR, position=write_model.InsertPosition.AFTER,
        content=(write_model.NewParagraph("x"),)),
    "delete": write_model.DeleteRequest(target=_ANCHOR),
    "subspan": write_model.SubSpanEditRequest(anchor=_ANCHOR, span="a", replacement="b"),
    "grow-table": write_model.GrowTableRequest(anchor=_ANCHOR, row_index=-1),
    "comment-create": write_model.CreateCommentRequest(text="hi"),
    "comment-remove": write_model.RemoveCommentRequest(
        target=write_model.CommentThread(comment_id="c1"), author_id="u1"),
    "edit": write_model.EditRequest(anchor=_ANCHOR, replacement="z"),
}


def test_every_registered_op_kind_has_a_census_sample():
    """The census is driven off the registry, so it cannot silently skip a new op."""
    assert sorted(_SAMPLES) == sorted(desc.kind for desc in OPS)


@pytest.mark.parametrize("kind", sorted(_SAMPLES))
def test_every_op_kind_round_trips_to_its_own_request_type(kind):
    """The round-trip census: a request of each registered kind classifies as that kind and
    survives ``to_dict`` → ``_request_from_dict`` as its **own** ``request_type``, equal to
    what went in. ``_request_from_dict`` is a per-op ladder outside ``OPS``, and nothing
    iterated the registry over it — so an op whose author forgot a spot test round-tripped on
    trust."""
    desc = BY_KIND[kind]
    request = _SAMPLES[kind]
    assert classify(request) == kind
    assert isinstance(request, desc.request_type)
    wire = request.to_dict()
    assert wire.get("op") == (None if kind == _TAGLESS_KIND else kind), wire
    back = _request_from_dict(wire)
    assert type(back) is desc.request_type, (kind, type(back).__name__)
    assert back == request


def test_the_request_deserialization_ladder_covers_every_TAGGED_kind():
    """The ladder's arms, read off its own source, must be exactly the tagged kinds. ``edit``
    is absent by design — it is the tagless fallback, and that fallback IS its arm."""
    tree = ast.parse((_WRITE_SRC / "model" / "requests.py").read_text(encoding="utf-8"))
    ladder = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "_request_from_dict")
    arms = {c.value for n in ast.walk(ladder) if isinstance(n, ast.Compare)
            for c in n.comparators if isinstance(c, ast.Constant)}
    assert arms == {desc.kind for desc in OPS} - {_TAGLESS_KIND}, arms


def test_no_apply_implementation_is_orphaned_out_of_the_registry():
    """The census's other direction: every module-level ``_apply_*`` in the package is
    reachable through ``OPS`` dispatch. An implementation that stops being registered is dead
    code that still reads as a write path."""
    defined = set(_module_level_apply_functions())
    reachable = set(reachable_apply_implementations()) | set(registered_apply_names())
    assert defined == reachable, {"orphaned": sorted(defined - reachable)}


def test_every_registered_op_kind_dispatches_to_a_function_this_tree_defines():
    """…and the first direction: an op kind whose implementation is renamed or removed cannot
    stay registered — the derivation itself refuses, naming the missing function."""
    assert set(BY_KIND) == {desc.kind for desc in OPS}
    defined = _module_level_apply_functions()
    for desc in OPS:
        assert desc.apply.__name__ in defined, desc.kind
