"""``apply-log-complete`` IS A HOUSE INVARIANT — one definition, one id, per-surface caveats.

The contract was born surface-shaped: it was written for the sheets engine, because the sheets
engine is where a raw API error escaped the per-entry loop mid-batch and left landed **and**
un-run entries with no disposition recorded for any of them. Everything about that wording said
"sheets", so a consumer asking **one** question — *can I recover from a half-applied batch?* —
had to ask it once per surface and then **infer** the docx answer from silence.

This module holds the harmonized shape:

* **One definition.** The invariant is authored once, as constants in
  ``larkdocio.capabilities._contracts``, and every declaration site references the constant.
  No second spelling of the id, no second wording of the promise, anywhere in the package's
  Python.
* **The docx position is STATED, not implied** — and it is stated without weakening the
  invariant to fit docx and without implying docx offers the per-entry account that a
  declaring surface gives you.
* **The sheets declaration is unchanged in meaning** — its per-entry text is pinned
  **byte-identical** by digest, so this change is provably vocabulary, not behavior.
* **Declaration is earned, not asserted.** A surface may declare the invariant only if its
  package actually carries the disposition boundary that makes it true
  (``<package>.disposition.classify_apply_exception``). The deliberate-defect check below
  re-declares the contract on a surface whose apply-log is *not* 1:1 and shows this module's
  own test reddening — the guard is not decorative.

Nothing here touches an apply path: the whole subject is vocabulary and disclosure.
"""
import hashlib
import importlib
import pathlib
import re

import pytest

import larkdocio
from larkdocio import capabilities
from larkdocio.capabilities._contracts import (
    APPLY_LOG_COMPLETE,
    APPLY_LOG_COMPLETE_DOCX_LEAD_IN,
    APPLY_LOG_COMPLETE_DOCX_POSITION,
    APPLY_LOG_COMPLETE_INVARIANT,
    APPLY_LOG_COMPLETE_SHEETS_LEAD_IN,
)

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "larkdocio"

#: The sheets per-entry text as it shipped **before** the harmonization (the wording the
#: batch-halt Blocker put there). This change may re-frame the contract's opening and append
#: the docx position; it may not touch a syllable of what sheets promises per entry.
_SHEETS_DETAIL_SHA256 = (
    "e4838987f13352ebb0304e6035a1c9fad9d747c22d26f34bcf3d0826f4075546"
)
_SHEETS_DETAIL_BYTES = 2254


def _contract() -> dict:
    return capabilities(full=True)["safety_contracts"][APPLY_LOG_COMPLETE]


def _summary() -> str:
    return _contract()["summary"]


def _sheets_detail() -> str:
    """The sheets half of the summary, isolated by its two known neighbours."""
    summary = _summary()
    assert APPLY_LOG_COMPLETE_SHEETS_LEAD_IN in summary
    tail = summary.split(APPLY_LOG_COMPLETE_SHEETS_LEAD_IN, 1)[1]
    return tail.split(APPLY_LOG_COMPLETE_DOCX_LEAD_IN, 1)[0].strip()


def _python_sources():
    return sorted(p for p in _SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _flattened(path: pathlib.Path) -> str:
    """A module's text with string-concatenation seams and line wrapping removed, lowercased.

    A paraphrase wrapped across two adjacent string literals is still a second definition, so
    the scan must not be defeated by ``"…" "…"``.
    """
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'["\']\s*\+?\s*["\']', "", text)
    return re.sub(r"\s+", " ", text).lower()


# --------------------------------------------------------------------------- #
# AC1 — one definition, one place, no second copy.                              #
# --------------------------------------------------------------------------- #

def test_ac1_the_invariant_is_authored_once_and_is_surface_independent():
    """The definition is a surface-independent statement: the apply-log is 1:1 with the plan
    and every entry ends in a typed disposition, **whatever happened**."""
    assert APPLY_LOG_COMPLETE == "apply-log-complete"
    for phrase in ("the apply-log is 1:1 with the plan",
                   "every entry ends in a typed disposition",
                   "whatever happened"):
        assert phrase in APPLY_LOG_COMPLETE_INVARIANT.lower(), phrase
    # Surface-independent: the shared sentence names no surface.
    for surface in capabilities(full=True)["surfaces"]:
        assert surface not in APPLY_LOG_COMPLETE_INVARIANT, surface
    assert APPLY_LOG_COMPLETE_INVARIANT in _summary()


def test_ac1_the_contract_id_is_spelled_exactly_once_in_the_package_python():
    """Every declaration site references the constant. The literal string appears in exactly
    one Python line in ``src/larkdocio`` — the constant's own definition — so ``capabilities()``
    cannot grow a second spelling of the id.

    Scope note: this is a ban on a second **authoring**, so it reads the package's Python.
    The packaged Markdown (the guide, the changelog) *references* the id by design and is held
    to the registry by its own guards (``tests/test_guide.py`` is bidirectional over exactly
    this catalog).
    """
    hits = [(path, n, line.strip())
            for path in _python_sources()
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if APPLY_LOG_COMPLETE in line]
    assert len(hits) == 1, f"the contract id is authored more than once: {hits}"
    path, _, line = hits[0]
    assert path.name == "_contracts.py", path
    assert line.startswith("APPLY_LOG_COMPLETE ="), line


def test_ac1_the_invariants_wording_has_no_second_definition_in_the_package_python():
    """The promise itself is written once too — a paraphrase in a second module is exactly the
    drift this issue exists to end."""
    core = "the apply-log is 1:1 with the plan and every entry ends in a typed disposition"
    files = [p.name for p in _python_sources() if core in _flattened(p)]
    assert files == ["_contracts.py"], files


# --------------------------------------------------------------------------- #
# AC2 — the docx position is STATED, and it is not weakened to fit docx.        #
# --------------------------------------------------------------------------- #

def test_ac2_the_docx_position_is_stated_in_the_shipped_registry():
    """docx does not declare the invariant, and the registry says so **in words** instead of
    leaving a consumer to infer it from an absent list entry."""
    assert APPLY_LOG_COMPLETE not in capabilities(full=True)["surfaces"]["docx-write"]["safety_contracts"]
    assert APPLY_LOG_COMPLETE_DOCX_POSITION in _summary()
    assert "docx-write does not declare" in APPLY_LOG_COMPLETE_DOCX_POSITION


def test_ac2_the_docx_text_carries_the_never_partially_applies_reason():
    """The reason is the whole point: a docx batch that refuses issues zero writes, so there
    is nothing to enumerate.

    **TRANSFORMED, NOT STRUCK (LD-585).** The four phrases below are the four this test has
    always required and every one of them still binds: they are the REFUSED-batch claim, which
    nothing has overtaken. What LD-585 added is the SCOPE the four were silently carrying — a
    reader met them beside ``larkdocio.write.model.applylog.INSERT_COST_CONTRACT``, whose whole
    point is the other half (an ACCEPTED batch's per-entry story), with nothing on the page
    saying the two are about different things. So this test keeps its name and its four
    assertions and GAINS the scope assertion; it does not trade one for the other.
    """
    for phrase in ("whole-batch-zero-writes", "zero writes", "never partially applies",
                   "nothing to enumerate"):
        assert phrase in APPLY_LOG_COMPLETE_DOCX_POSITION.lower(), phrase


def test_ac2_the_docx_text_SCOPES_the_refused_batch_claim_against_an_accepted_one():
    """LD-585: the two claims must read as two scopes of one truth, not as a contradiction.

    The scope sentence POINTS AT the per-entry contract by naming its two keys — it does not
    restate it, because ``INSERT_COST_CONTRACT`` is that promise's one authoring (LD-562) and a
    second wording of it would be a second thing to keep true.
    """
    from larkdocio.write.model.applylog import INSERT_ATOMIC_KEY, INSERT_WRITE_CALLS_KEY

    lowered = APPLY_LOG_COMPLETE_DOCX_POSITION.lower()
    assert "refused batch" in lowered, "the zero-writes claim does not say which batch it is about"
    assert "accepted" in lowered, "the accepted batch is not named"
    assert INSERT_WRITE_CALLS_KEY in APPLY_LOG_COMPLETE_DOCX_POSITION
    assert INSERT_ATOMIC_KEY in APPLY_LOG_COMPLETE_DOCX_POSITION


def test_ac2_the_docx_text_claims_no_per_entry_recovery():
    """The binding rider: the wording must not be weakened to fit docx, and it must never
    imply docx offers the recoverability a declaring surface offers. So the docx sentence
    carries **none** of the per-entry recovery vocabulary.

    **THE LIST BELOW IS UNCHANGED — NOT ONE ENTRY WAS STRUCK (LD-585).** LD-585 added a scope
    sentence to the very text this test polices, which is exactly the moment a list like this
    gets an entry deleted "to fit". It did not: the sentence was written AGAINST the list
    rather than the list widened to admit the sentence, and the sentence is inside the text
    checked here, not exempted from it. The list's original reason is unchanged and still
    binds in full — the docx caveat may never imply docx offers a declaring surface's
    per-entry account. What the scope sentence adds is a POINTER to a different, narrower
    promise (``applylog.INSERT_COST_CONTRACT``'s two keys, LD-562), which is not that account
    and does not use its words.

    **NOT ONE ENTRY WAS STRUCK AT LD-643 EITHER**, and that pass is the sharper test of the
    list: docx gained the disposition boundary, so the temptation was to relax the ban now
    that some of the banned words would arguably be *true* of it. The ban is not about truth,
    it is about a consumer reading the docx caveat as a description of a DECLARING surface —
    so the corrected position sentence was written against the list, in the surface's own
    words, and the list is byte-unchanged.
    """
    lowered = APPLY_LOG_COMPLETE_DOCX_POSITION.lower()
    for claimed in ("recover", "not-attempted", "applied-unverified",
                    "len(log.entries) == len(plan.entries)", "1:1"):
        assert claimed not in lowered, f"the docx position claims {claimed!r}"


def test_ac2_amplifier_the_docx_phrase_is_distinguishable_from_every_declaration():
    """Grep-style: the phrase used for docx appears in **no** surface's declaration text. One
    vocabulary, honest per-surface caveats — a consumer must not read the docx caveat as a
    description of what a declaring surface does."""
    docx_phrase = "never partially applies"
    assert docx_phrase not in _sheets_detail().lower()
    for cid, contract in capabilities(full=True)["safety_contracts"].items():
        if cid == APPLY_LOG_COMPLETE:
            continue
        assert docx_phrase not in contract["summary"].lower(), cid


# --------------------------------------------------------------------------- #
# AC3 — the sheets declaration is unchanged in meaning.                         #
# --------------------------------------------------------------------------- #

def test_ac3_sheets_still_declares_the_contract():
    """Sheets was the first declaring surface and stays one. LD-260 added the SECOND —
    base-write — and LD-266 the THIRD, base-schema-write; both Base surfaces ride the same
    package's disposition boundary, which is the mechanism in this module working rather than a
    widening of it: the amplifier below re-checks that every name on the list has earned it."""
    caps = capabilities(full=True)
    assert APPLY_LOG_COMPLETE in caps["surfaces"]["sheets-write"]["safety_contracts"]
    assert _contract()["applies_to"] == [
        "sheets-write", "base-write", "base-schema-write"]
    for surface_id in ("base-write", "base-schema-write"):
        assert APPLY_LOG_COMPLETE in caps["surfaces"][surface_id]["safety_contracts"]


def test_ac3_the_sheets_per_entry_text_is_byte_identical_to_what_shipped():
    """**This story changes vocabulary, not behavior** — so the sheets per-entry semantics are
    pinned by digest, not by paraphrase. A single differing byte fails this outright."""
    detail = _sheets_detail()
    assert len(detail) == _SHEETS_DETAIL_BYTES, len(detail)
    assert hashlib.sha256(detail.encode("utf-8")).hexdigest() == _SHEETS_DETAIL_SHA256, (
        "the sheets per-entry text moved — this change is vocabulary only"
    )


def test_ac3_the_sheets_per_entry_vocabulary_is_still_named():
    """Readable half of the digest above: the dispositions a consumer codes against."""
    detail = _sheets_detail()
    for name in ("api-error", "invalid-request", "permission-denied", "rate-limited",
                 "transport-failure", "unexpected-error", "not-attempted",
                 "applied-unverified", "ApplyLog.halt", "inert_formula_strings"):
        assert name in detail, name


# --------------------------------------------------------------------------- #
# AC4 — zero behavior change: the declaration SET did not move.                  #
# --------------------------------------------------------------------------- #

def test_ac4_no_surface_gained_or_lost_a_declaration():
    """LD-254 was vocabulary only, and the two surfaces it harmonized still declare exactly
    what they declared then. **LD-260 added ``base-write``**, which this test was written to
    redden on: the assertion below is the same one, extended to the surface that now exists —
    and it pins that publishing the Base engine changed neither docx's list nor sheets'."""
    declared = {sid: sorted(s["safety_contracts"])
                for sid, s in capabilities(full=True)["surfaces"].items()}
    # LD-493 added ``caller-supplied-destination`` to both write surfaces, because both ship a
    # create-class verb (``create_document`` / ``create_spreadsheet``). The pin is extended
    # rather than loosened: everything else each surface declared is still declared.
    # LD-707 (round 7, X3) moved no behaviour: each surface's list is now DERIVED from the
    # catalogue's applies_to, so the cross-cutting ``permission-denial-is-never-an-absence``
    # that the catalogue already applied to both write surfaces is listed on them too.
    assert declared["sheets-write"] == sorted([
        "STALE_SHEET", "apply-log-complete", "caller-supplied-destination",
        "dry-run-mandatory", "exactly-one-or-refuse", "permission-denial-is-never-an-absence",
        "plan-gated",
    ])
    assert declared["docx-write"] == sorted([
        "STALE_ANCHOR", "STALE_DOCUMENT", "caller-supplied-destination",
        "comment-anchors-honored-or-refused",
        "comment-create-whole-document-only", "comment-removal-sole-author-or-refuse",
        "dry-run-mandatory", "exactly-one-or-refuse", "one-tree-one-batch",
        "permission-denial-is-never-an-absence", "plan-gated",
    ])
    assert declared["base-write"] == sorted([
        "STALE_BASE", "apply-log-complete", "dry-run-mandatory", "plan-gated",
    ])


# --------------------------------------------------------------------------- #
# The amplifier — declaring the invariant is EARNED, and the guard bites.        #
# --------------------------------------------------------------------------- #

def _packages_behind(surface: dict) -> set:
    """The implementation packages a surface's operations are projected from.

    Taken as the first two dotted parts — ``larkdocio.<package>`` — rather than by splitting on
    a registry module's name. The original form split on ``".ops"``, which reads
    ``larkdocio.sheets.ops.OPS`` correctly and ``larkdocio.base.write_ops.WRITE_OPS`` not at
    all: a Base surface would have derived the whole dotted path as its "package" and then
    reported the boundary as missing for a package that has one. Two parts is what the check
    actually means, and it is the same answer for every surface here.
    """
    return {".".join(op["projected_from"].split(".")[:2])
            for op in surface.get("operations", []) if op.get("projected_from")}


def _has_disposition_boundary(package: str) -> bool:
    """Does ``package`` carry the boundary that makes the invariant true — the one
    classification seam that turns any exception into a typed, logged disposition?"""
    try:
        module = importlib.import_module(f"{package}.disposition")
    except ModuleNotFoundError:
        return False
    return callable(getattr(module, "classify_apply_exception", None))


def _surfaces_declaring_without_the_boundary(applies_to) -> list:
    surfaces = capabilities(full=True)["surfaces"]
    return sorted(
        sid for sid in applies_to
        if not all(_has_disposition_boundary(pkg) for pkg in _packages_behind(surfaces[sid]))
    )


def test_the_invariants_own_test_passes_for_every_surface_that_declares_it():
    assert _surfaces_declaring_without_the_boundary(_contract()["applies_to"]) == []
    assert _has_disposition_boundary("larkdocio.sheets")


def test_deliberate_defect_declaring_the_invariant_on_a_boundaryless_surface_reddens():
    """Re-declare the contract on a surface whose apply-log is not 1:1 **whatever happened**
    and the guard reddens.

    **TRANSFORMED, NOT STRUCK (LD-643) — and the transformation is the whole point.** This
    check used to make its demonstration out of ``docx-write``, whose package carried no
    disposition boundary. LD-643 gave it one, so the old assertion
    (``not _has_disposition_boundary("larkdocio.write")``) stopped being a statement about the
    guard and became a false statement about the tree. Deleting it would have thrown away the
    only proof that this guard bites at all, which is the thing a "declaring is EARNED" rule
    rests on. So the demonstration MOVES to a surface that genuinely has no boundary —
    ``drive-files-write``, a write surface, so the shape of the demonstration is unchanged —
    and the docx fact it used to assert is asserted in its new, true form beside it.
    """
    boundaryless = "drive-files-write"
    assert not _has_disposition_boundary("larkdocio.drive")
    mutated = list(_contract()["applies_to"]) + [boundaryless]
    assert _surfaces_declaring_without_the_boundary(mutated) == [boundaryless]


def test_docx_now_HAS_the_boundary_and_still_does_not_declare_and_the_text_says_why():
    """The other half of the transformation above, stated so it cannot drift back.

    ``larkdocio.write`` carries the boundary now, so the mechanical test in this module no
    longer explains docx's position — and the position has to keep explaining itself. It
    does: the whole-document compare-and-swap runs BEFORE the entry loop and deliberately
    re-raises a rate-limit error, so exactly one failure still leaves ``apply()`` with no log,
    and the invariant is declared only where it holds without a rider.
    """
    assert _has_disposition_boundary("larkdocio.write")
    assert APPLY_LOG_COMPLETE not in \
        capabilities(full=True)["surfaces"]["docx-write"]["safety_contracts"]

    lowered = APPLY_LOG_COMPLETE_DOCX_POSITION.lower()
    assert "disposition boundary" in lowered, "the boundary docx now has is not mentioned"
    assert "rate-limit" in lowered and "before the batch" in lowered, (
        "the reason docx still does not declare is not stated")
    # The claim this text used to make, which is now false, must be gone.
    assert "runs no per-entry disposition boundary" not in lowered

    # And the engine really does re-raise it, rather than the text saying so alone.
    apply_src = (_SRC / "write" / "apply.py").read_text(encoding="utf-8")
    cas = apply_src.split("def _document_cas", 1)[1].split("\ndef ", 1)[0]
    assert "except LarkRateLimitError:\n        raise" in cas


# --------------------------------------------------------------------------- #
# AC6 — the shipped guide says it in plain language, dialect-free.               #
# --------------------------------------------------------------------------- #

def test_ac6_the_guide_states_the_invariant_and_the_docx_caveat_in_the_same_plain_words():
    guide = larkdocio.guide(full=True)
    assert APPLY_LOG_COMPLETE_DOCX_POSITION in guide, (
        "the guide must carry the docx caveat in the SAME plain words as the registry"
    )
    assert "the apply-log is 1:1 with the plan and every entry ends in a typed disposition" \
        in guide.lower()


def test_ac6_the_guide_text_is_dialect_free():
    """No decision-sheet reference, no issue id, no role attribution reaches a consumer."""
    from consumer_text import dialect_hits  # noqa: PLC0415 — the suite's own helper

    row = next(line for line in larkdocio.guide(full=True).splitlines()
               if line.startswith(f"| `{APPLY_LOG_COMPLETE}`"))
    assert dialect_hits(row) == []
    assert dialect_hits(APPLY_LOG_COMPLETE_INVARIANT) == []
    assert dialect_hits(APPLY_LOG_COMPLETE_DOCX_POSITION) == []


@pytest.mark.parametrize("text", [APPLY_LOG_COMPLETE_INVARIANT,
                                  APPLY_LOG_COMPLETE_DOCX_POSITION])
def test_ac6_no_internal_decision_label_reaches_the_shipped_text(text):
    """Belt and braces on the one dialect class this issue could plausibly leak: the ruling's
    own label."""
    assert not re.search(r"\bD\d", text)
