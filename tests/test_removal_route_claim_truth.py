"""The shipped claim about a REMOVED object is held against **our own capture** — nobody else's.

The consumer-facing sentence this guards used to say that after a delete in the application's own
space *"the object's metadata still resolves"* and it named **one** route. A consumer then
measured a better number **on their tenant**, and the maintainer declined the class: a third-party
measurement may not be the source of a shipped claim (the row in ``requirements/DECISIONS.md``).
So the number in the guide is now sourced to a probe this project ran
(``tests/test_live_docx_removal_routes_gate.py``), and this file is what keeps the two in step.

**Every arithmetic assertion below is DERIVED from the capture**, never hand-typed beside it:
the guide says *one of five* because ``ld601-summary.json`` says one of five, and the day that
summary changes this file reddens rather than the prose quietly aging. That is the whole point —
a hand-typed count in a test is a second, drifting definition of the measurement.

**Why every assertion is on a pre-computed BOOLEAN and never on ``phrase in guide`` directly.**
The guide is ~850 KB and this module reads it with its line wrapping normalised away, so it is
one enormous line. A failing ``assert phrase in guide`` hands pytest's assertion rewriter that
whole line to explain, and the character-level diff it then builds does not finish in useful
time (measured: a spin, not a slow run). Naming the boolean first keeps the failure message the
one sentence a reader needs.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from larkdocio.common import error_codes
import private_tree  # noqa: E402  (LD-685)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GUIDE = REPO_ROOT / "src" / "larkdocio" / "GUIDE.md"
CAPTURES = REPO_ROOT / "tests" / "captures" / "ld601-trashed-doc-routes" / "captures"
SUMMARY = CAPTURES / "ld601-summary.json"

#: The over-claim this issue retired: it named ONE route and asserted the general case.
RETIRED_OVERCLAIM = "so the object's metadata still resolves afterwards"

#: The hedge that must SURVIVE — the probe measured routes, not search (the existing register).
#: **TRANSFORMED by LD-715** (``process/doctrine/supersession.md`` § A.1): the reason holds — a
#: figure this project did not measure is never promoted to a measured one. What changed is the
#: label's wording: the public text no longer tells who reported a figure, so the hedge it keeps
#: is the half that carries the meaning, *not measured by this project*.
SURVIVING_HEDGE = "**not measured by this project**"
#: The label a third-party figure wears (LD-715: formerly "reported to this project, not
#: measured by it").
NOT_OURS_LABEL = "not measured by this project"

WORD_NUMBERS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}


@pytest.fixture(scope="module")
def guide():
    """The guide with its line wrapping normalised away.

    Deliberate: every assertion here is about a SENTENCE, and a sentence that happens to wrap
    is the same sentence. A raw-text grep would redden on a reflow, which is the classic guard
    that trains people to edit the test instead of the prose.
    """
    return re.sub(r"\s+", " ", GUIDE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def summary():
    if not SUMMARY.exists():
        pytest.fail(f"{SUMMARY} is missing — the shipped claim has no capture behind it")
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def _observed_codes():
    """Every Lark ``code`` this project's own after-leg captures actually recorded."""
    codes = set()
    for path in sorted(CAPTURES.glob("ld601-after-*.json")):
        body = json.loads(path.read_text(encoding="utf-8"))
        code = (body.get("response") or {}).get("code")
        if code:
            codes.add(int(code))
    return codes


# ---------------------------------------------------------------------------
# The capture is the source. These read it; they do not restate it.
# ---------------------------------------------------------------------------

def test_the_capture_carries_a_BEFORE_control_in_which_every_route_resolved(summary):
    """Without the control, an ``after`` answer is a fact about the route, not the delete."""
    before = summary["before"]
    assert before and all(v is True for v in before.values()), (
        f"the before-leg control did not resolve on every route: {before}"
    )


def test_the_capture_says_how_many_routes_still_answered_and_names_them(summary):
    after = summary["after"]
    assert len(after) == 5, f"the probe's route set is five routes; found {len(after)}"
    still = summary["still_resolving_after_the_delete"]
    assert still == sorted(k for k, v in after.items() if v is True)
    assert still, "at least one route answered — otherwise the guide's claim shape is wrong"


def test_the_guide_states_OUR_ratio_derived_from_the_capture_not_a_hand_typed_one(
        guide, summary):
    """AC5: the count in the prose is the count in the capture, in words."""
    n = len(summary["still_resolving_after_the_delete"])
    total = len(summary["after"])
    phrase = f"{WORD_NUMBERS[n]} of {WORD_NUMBERS[total]}"
    present = phrase in guide.lower()
    assert present, f"the guide must state the measured ratio '{phrase}' (from {SUMMARY.name})"


def test_the_guide_NAMES_the_route_that_still_answered_with_its_load_bearing_spelling(guide):
    named = "/open-apis/drive/v1/metas/batch_query" in guide
    assert named, "the guide must name the endpoint that still answered"
    spelled = '`doc_type: "docx"`' in guide
    assert spelled, (
        "the spelling is load-bearing — a wrong one answers code:0 with an empty metas — so "
        "the guide must show the literal that was sent"
    )


def test_the_guide_names_what_the_ANSWER_carried_so_a_reader_can_judge_it(guide):
    """A route that "resolves" says nothing as a claim unless the guide says what came back."""
    missing = [f for f in ("title", "owner", "url", "timestamp") if f not in guide]
    assert not missing, f"the guide does not say the answer carried: {missing}"


def test_the_guide_names_the_codes_the_refusing_routes_ANSWERED_and_we_captured(guide):
    """Only codes that appear in OUR bodies may appear in the prose."""
    observed = _observed_codes()
    assert observed, "no refusal code was captured on the after leg"
    unnamed = sorted(c for c in observed if str(c) not in guide)
    assert not unnamed, f"captured on the after leg and not named in the guide: {unnamed}"


#: The anchor for "the DOCUMENT passage", chosen semantically rather than by heading text: the
#: `docx` spelling of this endpoint family appears only in the passage this issue wrote (the
#: folder twin beside it sends `doc_type: "folder"`). Every assertion about the new prose is
#: scoped to the window AFTER it, so a sentence the folder passage already carries cannot
#: satisfy a guard about the document one.
DOCUMENT_PASSAGE_ANCHOR = '`doc_type: "docx"`'


def _document_passage(guide):
    assert DOCUMENT_PASSAGE_ANCHOR in guide, (
        "the document passage is missing — it is anchored by the literal doc_type spelling it "
        "sends"
    )
    return guide[guide.index(DOCUMENT_PASSAGE_ANCHOR):]


def test_the_guide_says_plainly_that_no_route_separates_TRASHED_from_PURGED(guide):
    """AC5's hard half: the honest ceiling on what any of these reads can tell you."""
    window = _document_passage(guide)
    stated = bool(re.search(r"separates?\s+\**trashed\**\s+from\s+\**purged\**",
                            window, re.IGNORECASE))
    assert stated, "the guide must state that these routes do not separate trashed from purged"
    strongest = '"removed" is the strongest true statement' in window
    assert strongest, '"removed" must be named as the strongest true statement'


def test_the_guide_bounds_the_measurement_to_its_own_scope(guide):
    """The claim's scope may not exceed the evidence's scope: one tenant, one document."""
    window = _document_passage(guide)
    bounded = "one tenant" in window and "unmeasured, not refuted" in window
    assert bounded, "the measurement's scope and its unmeasured edge must both be stated"


# ---------------------------------------------------------------------------
# AC6 / AC8 — the declined evidence class, enforced in the shipped text
# ---------------------------------------------------------------------------

def test_the_retired_OVERCLAIM_is_gone(guide):
    survives = RETIRED_OVERCLAIM in guide
    assert not survives, (
        "the un-numbered claim was corrected from our own capture; it must not survive beside "
        f"the correction: {RETIRED_OVERCLAIM!r}"
    )


def test_a_third_party_figure_is_LABELLED_as_a_report_or_absent(guide, summary):
    """AC6: a bare *two of five routes* in consumer text is a FAIL.

    Enforced structurally rather than by hoping: any *N of five* phrase that is NOT the ratio
    our own capture supports must sit inside a passage that marks it as not ours
    (:data:`NOT_OURS_LABEL`; LD-715 replaced the word *reported* with that label).
    """
    ours = f"{WORD_NUMBERS[len(summary['still_resolving_after_the_delete'])]} of five"
    unlabelled = []
    for match in re.finditer(r"\b(one|two|three|four|five) of five\b", guide, re.IGNORECASE):
        phrase = match.group(0).lower()
        if phrase == ours:
            continue
        passage = guide[max(0, match.start() - 400):match.end() + 400].lower()
        if NOT_OURS_LABEL not in passage:
            unlabelled.append(phrase)
    assert not unlabelled, (
        f"not our measured ratio and not labelled as not ours: {unlabelled} — a third-party "
        f"figure ships labelled '{NOT_OURS_LABEL}', or not at all"
    )


def test_the_existing_unmeasured_hedge_SURVIVES(guide):
    """AC8: nothing labelled *not measured* / *unmeasured* is silently promoted."""
    hedge = SURVIVING_HEDGE in guide
    assert hedge, f"the existing hedge must survive verbatim: {SURVIVING_HEDGE!r}"
    subject = "surface in search results" in guide
    assert subject, "the search-results disclosure (not measured) must survive"


@private_tree.citations
def test_every_capture_the_guide_cites_EXISTS_and_wears_the_dev_repo_label(guide):
    cited = sorted(set(re.findall(
        r"tests/captures/ld601-trashed-doc-routes/captures/[\w\-.]+\.json", guide)))
    assert cited, "the corrected claim must cite the capture it came from"
    absent = [rel for rel in cited if not (REPO_ROOT / rel).exists()]
    assert not absent, f"cited by the guide and not on disk: {absent}"
    unlabelled = [rel for rel in cited
                  if not any(label in guide[guide.index(rel):guide.index(rel) + 400]
                          for label in ("in the dev repo", "in the source repository"))]
    assert not unlabelled, f"dev-repo paths cited without the label: {unlabelled}"


# ---------------------------------------------------------------------------
# AC7 — a row only from OUR OWN body, and `unknown` stays `unknown`
# ---------------------------------------------------------------------------

def test_the_code_we_OBSERVED_has_a_wire_observed_row_citing_its_capture():
    assert 1770003 in _observed_codes(), (
        "this guard's premise is that 1770003 arrived from Lark in our own capture"
    )
    note = error_codes.note_for(1770003)
    assert note is not None, "1770003 was observed on the wire here and must carry a row"
    assert note.verification == "wire-observed", (
        f"observed on the wire here, so the label is wire-observed, not {note.verification!r}"
    )
    assert note.label == "resource deleted", "the label is Lark's own msg, verbatim"
    assert "ld601-trashed-doc-routes" in note.evidence, (
        f"the row must cite the capture that established it; got {note.evidence!r}"
    )
    assert "in the dev repo" in note.evidence or "in the source repository" in note.evidence


def test_the_code_the_probe_did_NOT_observe_still_has_NO_ROW():
    """AC7's other half. The empty slot is an honest unknown, not a fact.

    Derived, not remembered: if a later capture ever records 1069604 arriving, this test tells
    its author to add the row **and** amend this guard — rather than letting a
    documented-unverified row be invented from a third-party report, which is exactly the
    evidence class the ruling declined.
    """
    assert 1069604 not in _observed_codes(), (
        "1069604 now appears in a capture — add its row with verification='wire-observed' and "
        "amend this guard"
    )
    assert error_codes.note_for(1069604) is None, (
        "no capture here records 1069604, so it may not carry a row: a documented-unverified "
        "row minted from a third-party report is the declined evidence class"
    )
