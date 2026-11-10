# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""LD-213 (audit T1) — the sheets op-family **registration seam**: the family count stops
being hand-kept, and the registration checklist becomes a guarded artifact.

**The defect this module closes.** ``larkdocio.sheets.ops.OPS`` is the ONE registration seam,
so *dispatch* costs one line — but the family **arity** was restated by hand in six module
docstrings, which by 2026-07-31 gave **three different answers** (six / a textually corrupted
``**Sevenfindings-agnostic**`` / seven) against a registry holding **eight** ops, with
``sheets/plan.py`` contradicting itself inside one file. This is the identical defect LD-132
routed for the shipped guide — *"the guide's sheets-write intro said 'Six request families' and
then listed five"* — already solved once, for the document that ships, and never pointed at the
module docstrings.

**THE DECLARED BASIS (AC1) — request-family arity, and it is the basis that already exists.**
The docstrings' lists are *request-family* enumerations: they name ``rich-cell``, which is a
request **type** of the ``value`` op rather than an op kind of its own. So the arity these
sentences state is

    ``len({op kinds capabilities() projects off OPS}) + 1``      (nine today)

which is **exactly** :func:`test_discovery_truth._expected_family_count` — the helper born from
LD-132 that already holds ``GUIDE.md``'s *"Nine request families"* sentence and its
*"nine families, eight operations"* reconciliation. This module **imports** that helper rather
than re-deriving the arity, so there is **one** counting basis in the suite, not a third one.
:func:`test_the_declared_basis_is_the_one_the_guide_guard_already_uses` pins the two together.

**Route taken (AC1): (b) — the prose keeps its sentence, a guard makes it true.** Not (a)
projection: assembling a docstring from ``OPS`` at import time would put generated text in
``help()`` output, break under ``python -OO`` (docstrings stripped), and buy nothing the guard
does not already give. Not (c) stop-counting: the count is *useful* to a reader (it is the
first thing that tells them whether the list in front of them is complete), and the guide —
this project's own precedent for the identical fact — states it and guards it.

**THE SCAN NOW SERVES TWO PACKAGES (LD-633).** Its mechanism moved, behaviour-unchanged, to
``tests/registration_seam.py``, parameterised by the corpus, the population noun and the
discriminator — because ``write/`` has the **identical** registration seam
(``larkdocio.write.ops.OPS``) and was scanned by nothing, and its own path count had been
understated by three for 35 days. What stayed here is what is *sheets policy*: the noun, the
qualifier set, the list shape and the registers below. The second enrolment is
``tests/test_write_registration_seam.py``.

**What is guarded, in both directions**

* **The scan** (:func:`_scan_claims`) walks the **source text** of every module under
  ``src/larkdocio/sheets/`` and finds every family-arity claim. Each one must state the derived
  arity. So a *new* hand-typed count cannot land anywhere in the package.
* **The registered sites** (:data:`_CLAIM_SITES`) name the five docstrings that MUST carry the
  claim, and which of them must carry the family **list**. So a site that *loses* its sentence —
  or whose bold marker is corrupted into ``**Sevenfindings-agnostic**``, which is what hid site
  #2 from every regex for two releases — reddens instead of going quiet.

**What must NOT bite (AC4)** — a guard that cries wolf is a guard someone weakens:

* the qualifier is the discriminator — only ``<count> families`` / ``<count> request families``
  / ``<count> write-request families`` is a claim about the op-family arity. ``two payload
  families`` (``sheets/models.py``, the metainfo-vs-v3 field naming) is **not**, and neither is
  any other qualified plural;
* a count word about something that is not a family at all — ``sheets/plan.py``'s disposition
  paragraph, which counted the LD-148 **refusal** vocabulary — never matches, because the noun
  is not ``famil(y|ies)``. (LD-206 added a ninth reason and that hand-kept count went stale on
  the spot, so it was **removed** rather than re-typed: the vocabulary is pinned against the code
  in ``tests/test_sheets_plan_disclosure_completion.py``, and a second copy in prose can only
  drift. :func:`test_the_disposition_vocabulary_count_never_matches` now pins the absence too —
  the same *stop-counting* route this module rejected for the family arity, taken here because
  the population has no reader-facing list beside it to be complete against.);
* ``sheets/ops.py``'s *"six families × two ladders"* narrates the **pre-registry** state at
  LD-125 and is correct AS HISTORY. It is an **explicitly registered** exemption
  (:data:`_HISTORICAL_CLAIMS`, the LD-201 two-entry-register precedent, not a loose allowlist)
  **and** the sentence was disambiguated in the same change so the register can be verified
  structurally: past tense plus the era named. Both were done — the register keeps the guard
  strict, the disambiguation keeps the register honest;
* ``GUIDE.md`` is **outside** this module's corpus. Its two sentences are already held by
  ``test_discovery_truth`` / ``test_guide_sheets_completion``; double-guarding them would create
  exactly the redundant pair LD-201 ruled against (*"two guards asserting one property invite
  one to be weakened while the other covers"*).

**The bite is proved, not asserted (AC3).** :func:`test_a_ninth_op_reddens_every_claim_site`
raises the derived arity by one — the in-suite equivalent of appending a dummy ninth
``SheetsOpDescriptor`` — and asserts **every** registered site is named in the report.
"""
import importlib
import re
from pathlib import Path

import pytest

from larkdocio.sheets.ops import OPS
from larkdocio.sheets.plan import VALUE_PRECONDITION_NONE, PlanEntry
import registration_seam
from test_discovery_truth import _COUNT_WORDS, _expected_family_count
from domain_vocabulary import RETIRED_ID

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SHEETS_SRC = _REPO_ROOT / "src" / "larkdocio" / "sheets"

#: The rich-cell request family — the ONE family that is not an op kind (it is a request
#: **type** of the ``value`` op). Named here because the prose lists name it, which is exactly
#: why the arity the prose states is ``len(op kinds) + 1``.
_RICH_CELL_FOLD = "rich-cell"


def _expected_family_labels() -> tuple:
    """The family labels the registry holds, DERIVED — one per registered op kind plus the
    rich-cell fold. A prose list must name every one of them."""
    return tuple(d.kind for d in OPS) + (_RICH_CELL_FOLD,)


# --------------------------------------------------------------------------- #
# The claim scanner — GENERALISED over the package (LD-633).                    #
# --------------------------------------------------------------------------- #
#
# The mechanism moved to ``tests/registration_seam.py`` verbatim in behaviour and is now
# parameterised by the corpus, the population noun and the discriminator, because ``write/``
# has the identical seam and was scanned by nothing (LD-633 / D-115). What stays here is what
# is SHEETS policy: the noun, the qualifier set, the list shape, the registers below.

#: Arities worth scanning for — the shared table's members from two up. See
#: ``registration_seam.SCANNED_COUNTS`` for why ``zero``/``one`` are excluded.
_SCANNED_COUNTS = registration_seam.SCANNED_COUNTS

#: The ONLY qualifiers that make a ``<count> … families`` phrase a claim about the op-family
#: arity. Anything else names a different population of "families" (``payload families`` in
#: ``sheets/models.py`` is the live-tree case) and is left alone.
_FAMILY_QUALIFIERS = frozenset({None, "request", "write-request"})

#: A family LIST: the parenthesised, slash-separated enumeration, required to follow the noun
#: IMMEDIATELY (whitespace only) so an unrelated parenthetical aside is never mistaken for it.
#: The parenthesised form is the shape ``GUIDE.md`` already uses and ``test_discovery_truth``
#: already parses.
_LIST_RE = re.compile(r"famil(?:y|ies)\s*\(([^()]*)\)")

#: Past-tense markers + era citations — how a registered HISTORICAL claim is verified to
#: actually be history rather than a drifted claim wearing an exemption.
_PAST_TENSE_RE = re.compile(r"\b(was|were|had|used to|grew|meant)\b", re.IGNORECASE)
_ERA_RE = re.compile(r"\b(LD-\d+|pre-registry)\b|" + RETIRED_ID.pattern)


def _split_families(listed: str) -> list:
    """Families are separated by ``/``; a ``·`` joins the variants WITHIN one family
    (``merge·unmerge`` is one family, not two) — the same split ``test_discovery_truth`` uses."""
    return [p.strip().strip("`").strip("*") for p in listed.split("/") if p.strip()]


def _listed_after(text: str, noun_start: int):
    """The parenthesised family list immediately following the noun, or ``None``."""
    m = _LIST_RE.match(text, noun_start)
    return _split_families(m.group(1)) if m else None


#: **The sheets seam**, as the shared scanner needs it: the qualifier is the discriminator, so
#: "the two **payload** families" is structurally out of scope rather than allowlisted.
_SEAM = registration_seam.Seam(
    package="larkdocio.sheets",
    source_dir=_SHEETS_SRC,
    noun_re=r"famil(?:y|ies)",
    is_arity_claim=lambda claim: (
        (claim.qualifier.lower() if claim.qualifier else None) in _FAMILY_QUALIFIERS),
    population="request families",
    listed_after=_listed_after,
)


def _claims_in(text: str, path: str, line_offset: int = 1) -> list:
    """Every family-arity claim in ``text`` (a source file or a single docstring)."""
    return registration_seam.claims_in(_SEAM, text, path, line_offset)


def _scan_claims() -> list:
    """Every family-arity claim in the **source text** of the sheets package."""
    return registration_seam.scan_claims(_SEAM)


# --------------------------------------------------------------------------- #
# The registers.                                                                #
# --------------------------------------------------------------------------- #

#: The docstrings that MUST state the family arity → whether the site must also carry the
#: family LIST. These are the six drifted sites LD-213 corrected (``PlanEntry``'s docstring
#: carries two of them), registered so a site that *loses* its sentence — or hides it behind a
#: corrupted bold marker, which is how ``write_apply``'s went unread — reddens.
_CLAIM_SITES = {
    "larkdocio.sheets": True,
    "larkdocio.sheets.write_apply": True,
    "larkdocio.sheets.ops:dry_run": True,
    "larkdocio.sheets.plan:PlanEntry": True,
    # The value-precondition disclosure states a SUBSET of the arity ("N of the M families"),
    # so it carries the total but no list of its own.
    "larkdocio.sheets.plan:PlanEntry.value_precondition": False,
}

#: The EXPLICIT historical-narration register (AC4). Keyed ``(file, the claim text lowercased)``
#: → why the claim is correct as history. An explicit register, not a loose rule: an unknown
#: site can never wear this exemption, and every entry is verified structurally below.
_HISTORICAL_CLAIMS = {
    ("src/larkdocio/sheets/ops/__init__.py", "six families"): (
        "LD-125's own narration of the state this module REPLACED — two hand-branched dispatch "
        "ladders keyed on different discriminators, when the surface held six families. Correct "
        "as history; 'correcting' it to the current arity would falsify the paragraph that "
        "explains why the registry exists."),
}


def _docstring(site: str) -> str:
    """The docstring of a registered site, addressed as ``module`` or ``module:attr.path``
    (the shared resolver — LD-633)."""
    return registration_seam.docstring(site)


def _violations(expected: int, expected_labels=None) -> list:
    """Every way the tree's family-arity claims disagree with ``expected`` — the single
    function both the live assertion and the ninth-op bite proof drive."""
    labels = tuple(expected_labels if expected_labels is not None else _expected_family_labels())
    problems = []

    for claim in _scan_claims():
        if (claim.path, claim.text.lower().replace("*", "")) in _HISTORICAL_CLAIMS:
            continue
        if claim.stated != expected:
            problems.append(
                f"{claim.site}: says {claim.text!r} but the registry holds {expected} "
                f"request families")

    for site, needs_list in _CLAIM_SITES.items():
        doc = _docstring(site)
        claims = [c for c in _claims_in(doc, site)]
        if not claims:
            problems.append(
                f"{site}: no family-arity claim found — the sentence was removed, reworded out "
                f"of the guarded shape, or its bold marker is corrupted")
            continue
        for claim in claims:
            if claim.stated != expected:
                problems.append(
                    f"{site}: says {claim.text!r} but the registry holds {expected}")
        if needs_list:
            listed = next((c.listed for c in claims if c.listed is not None), None)
            if listed is None:
                problems.append(
                    f"{site}: states the arity but carries no parenthesised family list")
                continue
            if len(listed) != expected:
                problems.append(
                    f"{site}: lists {len(listed)} families, registry holds {expected}: {listed}")
            joined = " ".join(listed).lower()
            for label in labels:
                if not any(item.lower().startswith(label) for item in listed):
                    problems.append(
                        f"{site}: the family list does not name {label!r}: {listed} "
                        f"(joined: {joined!r})")
    return problems


# =========================================================================== #
# AC1 — the arity is derived, on the basis that already exists.                 #
# =========================================================================== #

def test_the_declared_basis_is_the_one_the_guide_guard_already_uses():
    """AC1: ONE counting basis in the suite, not a third one. The labels this module derives
    off ``OPS`` and the arity ``test_discovery_truth._expected_family_count`` derives off the
    ``capabilities()`` projection must agree — if they ever disagree, the projection and the
    registry have drifted and BOTH guards are lying."""
    assert len(_expected_family_labels()) == _expected_family_count()
    assert _RICH_CELL_FOLD not in {d.kind for d in OPS}, (
        "rich-cell became an op kind of its own — the +1 fold in the declared basis is now a "
        "double count; re-derive the basis in test_discovery_truth first")


def test_every_family_arity_claim_in_the_sheets_package_is_derived():
    """AC1 + AC2: every family-arity claim in ``src/larkdocio/sheets/**`` states the derived
    arity, every registered site still carries its claim, and every list names every family."""
    assert _violations(_expected_family_count()) == []


def test_all_six_drifted_sites_are_registered_and_present():
    """AC2: the six sites the mint measured are the five docstrings registered here (PlanEntry's
    carries two of them), so none can quietly stop stating the arity."""
    assert set(_CLAIM_SITES) == {
        "larkdocio.sheets",
        "larkdocio.sheets.write_apply",
        "larkdocio.sheets.ops:dry_run",
        "larkdocio.sheets.plan:PlanEntry",
        "larkdocio.sheets.plan:PlanEntry.value_precondition",
    }
    for site in _CLAIM_SITES:
        assert _claims_in(_docstring(site), site), site


def test_no_count_word_is_fused_to_the_next_word_anywhere_in_the_package():
    """AC2, the specific rot: ``write_apply``'s count word was fused to the next word —
    ``**Sevenfindings-agnostic**`` — which hid a stale claim from every regex that looked for
    it, in the file whose own subject is the write families. The check is over PROSE: a
    double-backticked literal is a **citation**, so the corrected sentence may (and does) quote
    the exact rot it replaced without re-tripping the guard."""
    fused = re.compile(
        r"(?i)^(" + "|".join(sorted(_SCANNED_COUNTS, key=len, reverse=True)) + r")[a-z-]")
    offenders = []
    for site in _CLAIM_SITES:
        prose = re.sub(r"``[^`]*``", "", _docstring(site))
        for span in re.findall(r"\*\*([^*]+)\*\*", prose):
            token = span.split()[0].strip(",.;:") if span.split() else ""
            if fused.match(token) and token.lower() not in _COUNT_WORDS:
                offenders.append(f"{site}: **{span}**")
    assert offenders == [], offenders


@pytest.mark.parametrize("family", sorted({d.kind for d in OPS}))
def test_every_registry_family_is_named_by_every_list_site(family):
    """AC2's other direction, per family: ``formula``, ``dimension-property`` and
    ``freeze-panes`` were the three that went missing (``freeze-panes`` from all six sites)."""
    for site, needs_list in _CLAIM_SITES.items():
        if not needs_list:
            continue
        listed = next(
            (c.listed for c in _claims_in(_docstring(site), site) if c.listed is not None), None)
        assert listed is not None, site
        assert any(item.lower().startswith(family) for item in listed), (site, family, listed)


# =========================================================================== #
# AC3 — the bite, proved.                                                      #
# =========================================================================== #

def test_a_ninth_op_reddens_every_claim_site():
    """AC3 (in-suite form): raise the derived arity by one — what appending a dummy ninth
    ``SheetsOpDescriptor`` to ``OPS`` does — and EVERY registered site must be named in the
    report. A guard that does not visibly bite on a ninth family is decoration."""
    ninth = _expected_family_count() + 1
    problems = _violations(ninth, _expected_family_labels() + ("dummy",))
    assert problems, "a ninth op changed nothing — the guard is decoration"
    for site in _CLAIM_SITES:
        assert any(p.startswith(site + ":") for p in problems), (site, problems)
    # …and the file-level scan names the source sites too, by path:line.
    assert any(re.match(r"src/larkdocio/sheets/\w+\.py:\d+:", p) for p in problems), problems
    # …and every list site is told which family it fails to name.
    assert sum("does not name 'dummy'" in p for p in problems) == sum(_CLAIM_SITES.values())


def test_dropping_one_family_name_from_one_list_reddens():
    """AC2's evidence clause: a mutation that drops a single family name from a single site is
    reported, naming the site and the missing family."""
    doc = _docstring("larkdocio.sheets")
    assert "freeze-panes" in doc
    mutated = _claims_in(doc.replace(" / freeze-panes", ""), "larkdocio.sheets")
    listed = next(c.listed for c in mutated if c.listed is not None)
    assert "freeze-panes" not in listed
    assert len(listed) == _expected_family_count() - 1


# =========================================================================== #
# AC4 — the must-not-bite set.                                                 #
# =========================================================================== #

def test_the_historical_narration_is_registered_and_really_is_history():
    """AC4: ``ops.py``'s "six families × two ladders" is exempt by an EXPLICIT register, and the
    exemption is verified structurally — the sentence must be past tense AND name its era, so
    the register cannot shelter a present-tense claim that simply drifted."""
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
    claims = _claims_in(
        (_SHEETS_SRC / "ops" / "__init__.py").read_text(encoding="utf-8"),
        "src/larkdocio/sheets/ops/__init__.py")
    historical = [c for c in claims if c.stated != _expected_family_count()]
    assert [c.text.lower().replace("*", "") for c in historical] == ["six families"], historical


def test_the_disposition_vocabulary_count_never_matches():
    """AC4 (live tree): ``sheets/plan.py``'s disposition paragraph counts the LD-148
    **disposition** vocabulary, not op families, so the family-count scanner must never bite
    on it — a guard that reddened there would be crying wolf about a different population.

    It used to read "These **six** reasons close that hole". LD-206 added a ninth reason
    (``permission-denied``) and that hand-kept count went stale on the spot — so the count was
    **removed** rather than re-typed, the prose-count lesson applied to its own exhibit: the
    set is pinned in ``tests/test_sheets_plan_disclosure_completion.py``, which is code truth,
    and a second copy of it in prose can only ever drift. All three halves are pinned here: the
    paragraph is still present, it states no number, and the scanner still reports nothing."""
    text = (_SHEETS_SRC / "plan.py").read_text(encoding="utf-8")
    assert "close that hole" in text, "the LD-148 disposition paragraph moved — re-pin this case"
    assert "six reasons" not in text, (
        "a hand-kept reason count is back in plan.py — the vocabulary is pinned against the "
        "code in tests/test_sheets_plan_disclosure_completion.py, so prose must not re-state it")
    assert not [c for c in _claims_in(text, "plan.py") if "reason" in c.text.lower()]


def test_a_differently_qualified_family_population_never_matches():
    """AC4 (live tree): ``sheets/models.py``'s "the two payload families name the fields
    differently" is about the metainfo-vs-v3 payload shapes, not op families. The qualifier is
    the discriminator, so it is structurally out of scope rather than allowlisted."""
    text = (_SHEETS_SRC / "models.py").read_text(encoding="utf-8")
    assert "two payload families" in text, "the freeze-read paragraph moved — re-pin this case"
    assert _claims_in(text, "models.py") == []


@pytest.mark.parametrize("prose", [
    "These **six** reasons close that hole.",
    "the two payload families name the fields differently",
    "**four** legs certify a write surgical",
    "**three** disclosure kinds ride every entry",
    "the creatable-content family is one family, named once",
    "**seven** endpoint families answer the read side",
])
def test_a_count_about_something_that_is_not_an_op_family_never_matches(prose):
    """AC4 (synthetic): a count word in the sheets package about anything that is not an op
    family — reasons, legs, disclosures, payload/endpoint families — is not a claim."""
    assert _claims_in(prose, "synthetic.py") == []


@pytest.mark.parametrize("prose", [
    "**nine** request families (a / b)",
    "nine write-request families flow through the ONE gate",
    "a lie for six of the nine families",
])
def test_the_guarded_shapes_do_match(prose):
    """Anti-vacuity for the case above: the three shapes the corrected sites actually use ARE
    recognised, so the must-not-bite cases pass for the right reason."""
    assert len(_claims_in(prose, "synthetic.py")) == 1, prose


def test_the_guide_is_not_double_guarded():
    """AC4: ``GUIDE.md`` is outside this corpus. Its family sentence and its nine-vs-eight
    reconciliation are already held by ``test_discovery_truth`` /
    ``test_guide_sheets_completion``; a second guard over the same sentence is the redundant
    pair LD-201 ruled against."""
    corpus = {c.path for c in _scan_claims()}
    assert corpus, "the scanner found nothing at all — the corpus path is wrong"
    assert all(p.startswith("src/larkdocio/sheets/") and p.endswith(".py") for p in corpus)
    assert not any("GUIDE" in p or p.endswith(".md") for p in corpus)


# =========================================================================== #
# The value-precondition subset — the one site that states TWO numbers.        #
# =========================================================================== #

def _families_without_value_precondition() -> int:
    """How many of the request families have NO tier-2 value precondition — derived by asking
    the property itself, one representative entry per family, rather than restating its
    ``write_kind`` test in a second place."""
    entries = [
        PlanEntry(outcome="resolved", write_kind=d.write_kind,
                  structural={"op": d.entry_ops[0]} if d.entry_ops else None)
        for d in OPS
    ]
    entries.append(PlanEntry(outcome="resolved", write_kind="value", rich=True))
    return sum(e.value_precondition == VALUE_PRECONDITION_NONE for e in entries)


def test_the_value_precondition_disclosure_states_both_numbers_derived():
    """AC2 site #6 said *"a lie for four of the seven families"* — both numbers wrong. The
    subset is derived from the property itself and the total from the registry, so neither can
    drift again."""
    doc = _docstring("larkdocio.sheets.plan:PlanEntry.value_precondition")
    flat = " ".join(doc.split())
    subset = _families_without_value_precondition()
    total = _expected_family_count()
    expected = (f"{[w for w, n in _COUNT_WORDS.items() if n == subset][0]} of the "
                f"{[w for w, n in _COUNT_WORDS.items() if n == total][0]} families")
    assert re.search(r"\b" + expected.replace(" ", r"\W+") + r"\b", flat.replace("*", "")), (
        f"the disclosure must say {expected!r} (derived: {subset} of {total}):\n{flat}")


def test_the_value_precondition_subset_is_not_a_restated_literal():
    """Anti-vacuity: the subset really is what the property answers, and it is a strict, useful
    subset — every family with no cell-value ``before`` and no others."""
    subset = _families_without_value_precondition()
    assert 0 < subset < _expected_family_count()
    enforced = _expected_family_count() - subset
    assert enforced == 3, (
        "value / formula / rich-cell are the enforced three; a fourth enforced family means "
        "the precondition contract changed, which is not a docstring matter")


# =========================================================================== #
# AC5 — the registration CHECKLIST.                                            #
# =========================================================================== #

#: The contributor-facing checklist lives in the registry module's own docstring — the file a
#: Dev adding a family already has open. NOT a consumer document (§J: ``GUIDE.md`` /
#: ``README.md`` / ``SHEETS.md`` / ``RELEASE_NOTES.md`` / ``write/README.md`` are written for a
#: consumer; ``blocks/BLOCK_TYPES.md`` is the named contributor-doc precedent).
_CHECKLIST_OWNER = "larkdocio.sheets.ops"
_CHECKLIST_HEADING = "**Adding an op family — the registration checklist.**"
_REGISTER_RE = re.compile(r"^\s*\*\s+\*\*REGISTER\*\*\s+``([^`]+)``\s+—\s+(DERIVED|HAND-KEPT)\b",
                          re.MULTILINE)
#: Digits that are an identifier, not an arity — an arity in the checklist would make the
#: checklist itself the seventh hand-kept count.
_ID_DIGITS_RE = re.compile(r"\bLD-\d+|" + RETIRED_ID.pattern + r"|\bv\d+|\bA1\b|\bL[12]\b")


def _checklist() -> str:
    doc = _docstring(_CHECKLIST_OWNER)
    assert _CHECKLIST_HEADING in doc, (
        f"{_CHECKLIST_OWNER}'s docstring must carry the registration checklist under the "
        f"heading {_CHECKLIST_HEADING!r}")
    return doc[doc.index(_CHECKLIST_HEADING):]


def _resolve(location: str):
    """Resolve one checklist location. A checklist naming a moved list is worse than none."""
    if "::" in location:
        path, _, symbol = location.partition("::")
        target = _REPO_ROOT / path
        assert target.is_file(), f"checklist cites missing file {path}"
        assert symbol in target.read_text(encoding="utf-8"), (
            f"checklist cites {symbol!r} in {path}, which no longer defines it")
        return
    if "/" in location or location.endswith(".md"):
        assert (_REPO_ROOT / location).is_file(), f"checklist cites missing path {location}"
        return
    parts = location.split(".")
    for cut in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:cut]))
        except ImportError:
            continue
        for attr in parts[cut:]:
            assert hasattr(obj, attr), (
                f"checklist cites {location}, but {attr!r} is not there any more")
            obj = getattr(obj, attr)
        return
    raise AssertionError(f"checklist cites {location}, which does not import")


def test_the_registration_checklist_lands_in_the_registry_module():
    """AC5: the checklist exists, in ``sheets/ops.py``'s own docstring, and it carries the
    substance — every list to update, and what breaks if it is forgotten."""
    checklist = _checklist()
    rows = _REGISTER_RE.findall(checklist)
    assert len(rows) >= 8, f"a checklist of {len(rows)} rows is a gesture, not the inventory"
    locations = [loc for loc, _ in rows]
    assert any(loc.endswith("ops.OPS") for loc in locations), locations
    assert any(loc.endswith("WRITE_SEAMS") for loc in locations), locations
    # Every list must say what breaks if it is forgotten — the reason the checklist is read.
    assert checklist.lower().count("forget") >= 6, (
        "the checklist must say what BREAKS when each list is forgotten, not just name it")


def test_every_checklist_location_resolves():
    """AC5's evidence: each named module / symbol / path exists. A checklist citing a list that
    moved is worse than no checklist, because it is believed."""
    for location, _ in _REGISTER_RE.findall(_checklist()):
        _resolve(location)


def test_every_checklist_row_says_derived_or_hand_kept():
    """AC5: the checklist says which items are DERIVED (so nobody edits them by hand) and which
    are HAND-KEPT (so nobody assumes they are safe)."""
    rows = _REGISTER_RE.findall(_checklist())
    kinds = {kind for _, kind in rows}
    assert kinds == {"DERIVED", "HAND-KEPT"}, kinds


def test_no_checklist_row_states_an_arity():
    """The checklist must not become the seventh hand-kept count. A row names its list and says
    what breaks; it never says how many entries the list has today."""
    offenders = []
    for line in _checklist().splitlines():
        if "**REGISTER**" not in line:
            continue
        stripped = _ID_DIGITS_RE.sub("", line)
        if re.search(r"\d", stripped) or _claims_in(stripped, "checklist"):
            offenders.append(line.strip())
    assert offenders == [], offenders


def test_the_checklist_is_not_in_a_consumer_document():
    """AC5 (§J role separation): the checklist is CONTRIBUTOR-facing. It must not appear in any
    packaged consumer document — those are written for someone using the library, not extending
    it."""
    import consumer_text

    for label, text in consumer_text.shipped_docs().items():
        assert "**REGISTER**" not in text, f"the checklist leaked into {label}"
        assert _CHECKLIST_HEADING not in text, f"the checklist leaked into {label}"


def test_the_checklist_records_the_fan_out_cost():
    """AC5: the checklist is honest about what adding a family actually costs — LD-185's
    measured fan-out, so nobody plans a family as a one-line change."""
    checklist = _checklist()
    assert "LD-185" in checklist
    assert re.search(r"\b(9|nine)\b[^.]*\btest files\b", checklist), checklist
