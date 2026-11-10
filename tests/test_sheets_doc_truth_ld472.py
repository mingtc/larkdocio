# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""LD-472 — the sheets doc-truth guards: the sentences that were FALSE stay out, and the two
capabilities that shipped invisible stay findable.

Six defects were fixed by writing prose, and prose rots. Each guard here pins the **one thing
about its fix that a later edit could quietly undo** — never the wording, which is free to
change:

* **AC1** — the false *"omit ``index`` to append"* sentence is gone from the shipped corpus,
  and the corpus states the measured truth plus the append idiom instead. The behaviour is
  **unchanged** (maintainer ruling: doc-truth only), so nothing here asserts anything about ``AddTab``
  itself — the live gate ``tests/test_live_sheets_ld472_doc_truth_gate.py`` does the measuring.
* **AC3** — every ``RichCellWriteRequest`` constructor has a non-empty ``__doc__``, so the
  next sibling cannot ship blank the way ``hyperlink`` and ``styled_runs`` did, and both are
  named in the guide.
* **AC5** — ``read_spreadsheet_markdown`` is named at BOTH doors: the obviously-named read
  recipe and the CLI's refusal for a sheets url.
* **AC6** — the read route's hidden-tab paragraph, and the code fact under it, asserted so the
  sentence cannot outlive its reason. **The conclusion is SUPERSEDED and the reason is not**
  (LD-477): the code fact used to be *"``SheetTab`` has no ``hidden``; ``query_tabs`` does"*
  and the paragraph disclosed a gap; the field now ships on the read model, so the assertion is
  **inverted rather than deleted** and the paragraph states the answer instead of the gap. What
  did not change is *why* the guard exists — a shipped sentence about hidden tabs may not
  outlive the code underneath it — and it now bites from the other side.
* **AC7** — the dropdown-relocation disclosure exists on BOTH recipes.
* **AC8** — the float-image recipe no longer promises a range, and the label the measurement
  overturned (*unmeasured, not refuted* about a multi-cell anchor) is gone.
"""
import inspect
import pathlib
import re

import pytest

import consumer_text
from larkdocio import guide
from larkdocio.read.download import _NON_DOCUMENT_URL_MESSAGES
from larkdocio.sheets.models import SheetTab
from larkdocio.sheets.write_apply import RichCellWriteRequest
from larkdocio.sheets.write_client import SheetsWriteClient

pytestmark = pytest.mark.conformance


# --------------------------------------------------------------------------- #
# AC1 — the false sentence is OUT, and the truth plus the idiom are IN.         #
# --------------------------------------------------------------------------- #

#: The claim as it was written, and the two ways a later edit would most plausibly re-write
#: it. Matched loosely (whitespace-collapsed, case-insensitive) so a re-wrap cannot smuggle it
#: back in.
_APPEND_LIE_PATTERNS = (
    r"omit\s+`?index`?\s+to\s+append",
    r"omitting\s+`?index`?\s+appends",
    r"no\s+`?index`?[^.]{0,40}\bappends\b",
)


def _corpus():
    return consumer_text.shipped_docs()


@pytest.mark.parametrize("pattern", _APPEND_LIE_PATTERNS)
def test_ac1_the_append_lie_is_nowhere_in_the_shipped_corpus(pattern):
    offenders = []
    for label, text in _corpus().items():
        flat = re.sub(r"\s+", " ", text)
        if re.search(pattern, flat, re.IGNORECASE):
            offenders.append(label)
    assert not offenders, (
        f"{pattern!r} is back in the shipped corpus ({offenders}). AddTab with no index places "
        "the new tab FIRST — measured twice live; see "
        "tests/test_live_sheets_ld472_doc_truth_gate.py. To append, name the position: "
        "index=len(tabs).")


def test_ac1_the_corpus_states_the_measured_truth_and_hands_over_the_idiom():
    text = re.sub(r"\s+", " ", guide(full=True))
    assert re.search(r"omitting\s+`?index`?[^.]{0,80}first", text, re.IGNORECASE), (
        "the guide no longer states what omitting `index` actually does")
    assert "index=len(tabs)" in text, (
        "the append idiom is gone — a consumer who wanted append gets a correction with no "
        "working line, which is the half-fix AC1 exists to prevent")


def test_ac1_the_addtab_docstring_carries_the_correction_too():
    """``help(AddTab)`` is a door of its own, and it said the same false thing."""
    from larkdocio.sheets.write_apply import AddTab

    doc = re.sub(r"\s+", " ", AddTab.__doc__ or "")
    assert doc, "AddTab lost its docstring"
    assert not re.search(r"omit\s+`?`?index`?`?\s+to\s+append", doc, re.IGNORECASE), doc
    assert "FIRST" in doc, doc
    assert "index=len(" in doc, doc


# --------------------------------------------------------------------------- #
# AC3 — a rich-cell constructor cannot ship blank again.                        #
# --------------------------------------------------------------------------- #

def _rich_constructors():
    """Every public classmethod that BUILDS a ``RichCellWriteRequest`` — derived, not listed,
    so a fifth rich kind is enrolled by existing rather than by being remembered."""
    out = {}
    for name, member in vars(RichCellWriteRequest).items():
        if name.startswith("_") or not isinstance(member, classmethod):
            continue
        out[name] = member.__func__
    return out


def test_ac3_every_rich_cell_constructor_has_a_real_docstring():
    blank = [name for name, fn in _rich_constructors().items()
             if not (fn.__doc__ or "").strip()]
    assert not blank, (
        f"a RichCellWriteRequest constructor ships with no __doc__: {blank}. hyperlink() and "
        "styled_runs() shipped that way for eight releases and read to a consumer as "
        "capabilities that did not exist.")


def test_ac3_the_constructor_set_is_the_four_kinds_this_guard_was_written_for():
    """A canary, not a fence: a NEW rich kind is welcome and reddens this one line, which is
    the prompt to give it a recipe as well as a docstring."""
    assert set(_rich_constructors()) == {"hyperlink", "styled_runs", "mention", "multi_select"}


@pytest.mark.parametrize("symbol", ["hyperlink", "styled_runs"])
def test_ac3_the_invisible_capabilities_are_named_in_the_guide(symbol):
    assert symbol in guide(full=True), (
        f"{symbol} has vanished from the guide again — zero hits is how this defect looked")


def test_ac3_the_two_invisible_capabilities_have_a_recipe_of_their_own():
    headings = [row["heading"] for row in __import__("larkdocio").guide_sections()]
    named = [h for h in headings if h.lower().startswith("recipe:") and "hyperlink" in h.lower()]
    assert named, f"no recipe heading names the hyperlink write: {headings[:3]}…"


# --------------------------------------------------------------------------- #
# AC5 — the one call, at both doors.                                           #
# --------------------------------------------------------------------------- #

def test_ac5_the_obviously_named_read_recipe_names_the_one_call():
    section = guide("recipe-read-a-sheet-to-markdown")
    assert "read_spreadsheet_markdown" in section, (
        "the read recipe routes a consumer into the hand-rolled loop again")


def test_ac5_the_cli_refusal_for_a_sheets_url_names_the_one_call():
    message = _NON_DOCUMENT_URL_MESSAGES["sheets"]
    assert "read_spreadsheet_markdown" in message, message


def test_ac5_the_control_path_says_it_does_not_skip():
    section = re.sub(r"\s+", " ", guide("recipe-read-a-sheet-to-markdown")).lower()
    assert "control path" in section, section[:400]
    assert "does not skip" in section or "not skip a refused tab" in section, section[:400]


# --------------------------------------------------------------------------- #
# AC6 — the hidden-tab paragraph, and the code fact under it.                  #
#                                                                              #
# TRANSFORMED, NOT DELETED (LD-477). The original assertion was `"hidden" not  #
# in SheetTab's fields` — TRUE when AC6's paragraph was written, and the reason #
# it was asserted is UNCHANGED: a shipped sentence about hidden tabs may not    #
# outlive the code fact underneath it. Only the CONCLUSION moved. The field is  #
# now projected off the read route's own wire, so each assertion below is       #
# inverted onto the new truth and the coverage survives the amendment.          #
# --------------------------------------------------------------------------- #

#: The gap as AC6 stated it, and the two ways a later edit would most plausibly restate it.
#: All three were TRUE through 1.35 and are FALSE now — the read model carries the field —
#: so they are pinned OUT of the shipped corpus exactly as AC1's append claim is.
_SUPERSEDED_HIDDEN_GAP_PATTERNS = (
    r"`?SheetTab`?\s+carries\s+no\s+`?hidden`?",
    r"a\s+read\s+cannot\s+tell\s+a\s+hidden\s+tab",
    r"only\s+way\s+to\s+ask[^.]{0,40}`?SheetsWriteClient\.query_tabs`?",
)


#: The one surface where the superseded sentence STAYS, and must: the release notes are an
#: **append-only dated record**, and their 1.35.0 section states what was true at 1.35.0. The
#: same carve-out ``tests/test_absence_claims_guard.py``'s ``DATED_RECORD_SURFACES`` makes, for
#: the same reason — rewriting history there would destroy the record of what a consumer was
#: told, which is the opposite of the supersession ethic this amendment is made under.
_DATED_RECORD_SURFACES = frozenset({"release_notes() (the packaged RELEASE_NOTES.md)"})


@pytest.mark.parametrize("pattern", _SUPERSEDED_HIDDEN_GAP_PATTERNS)
def test_ac6_the_superseded_hidden_tab_gap_is_nowhere_in_the_shipped_corpus(pattern):
    offenders = []
    for label, text in _corpus().items():
        if label in _DATED_RECORD_SURFACES:
            continue
        flat = re.sub(r"\s+", " ", text)
        if re.search(pattern, flat, re.IGNORECASE):
            offenders.append(label)
    assert not offenders, (
        f"{pattern!r} is back in the shipped corpus ({offenders}). It was true through 1.35 "
        "and stopped being true when SheetTab gained `hidden`: the read route answers a tab's "
        "visibility itself, on the wire it was already reading.")


def test_ac6_the_dated_record_KEEPS_the_old_claim_AND_publishes_the_correction():
    """The carve-out above has to bite, or it is a suppression file.

    The release notes must still contain the 1.35 statement of the gap — that is the record of
    what a consumer was told — **and** must carry the correction, so a reader who acted on the
    old sentence meets the new one where they look for changes.

    **The two arms read two different copies, and that is the amendment (LD-591).** The reason
    is untouched: an append-only dated record may not be rewritten, and the correction must be
    where a consumer looks. What moved is only WHICH copy answers which arm. The copy inside
    the wheel is a WINDOW of the newest 8 releases by design, so the 1.35.0 section aged out of
    it the moment an 1.43.0 section landed — nothing was rewritten, the record simply passed
    the window's edge, exactly as that copy's own preamble says it will. So the RECORD arm is
    asserted against the CANONICAL ROOT document (the full history, which the refresh script
    drops beside the wheel as `vendor/larkdocio-RELEASE_NOTES.md` — what a re-pinning consumer
    actually holds), while the CORRECTION arm stays on the PACKAGED copy, because "where a
    consumer looks for what moved under them" is precisely the in-window view.

    **And LD-592 moved the SECOND arm for the SAME reason the first one moved.** The premise
    that made the correction arm a packaged-copy assertion — the in-window view is where a
    consumer looks — holds only while the correcting section is still inside the window, and a
    window rolls at every cut. It aged past the edge with nothing rewritten. So the correction
    arm is asserted against the same canonical root document the record arm already reads, and
    the wheel-facing claim is **kept for as long as it can be true**: while the packaged copy
    still carries a section publishing the correction, it must carry the correction too.
    """
    root_notes_text = (
        pathlib.Path(__file__).resolve().parent.parent / "RELEASE_NOTES.md"
    ).read_text("utf-8")
    root_notes = re.sub(r"\s+", " ", root_notes_text)
    notes = re.sub(r"\s+", " ", _corpus()["release_notes() (the packaged RELEASE_NOTES.md)"])
    assert re.search(_SUPERSEDED_HIDDEN_GAP_PATTERNS[0], root_notes, re.IGNORECASE), (
        "the release notes no longer record that a read could not tell — an append-only dated "
        "record was rewritten, which is the erasure the supersession rule forbids")
    assert re.search(r"`?SheetTab\.hidden`?", root_notes), (
        "the correction is not published where a consumer looks for what moved under them")
    # The wheel-facing arm, while the window still reaches it. Derived, never a second
    # expectation: the correcting section is located in the root by its own content, and only
    # if the packaged copy still carries that section is it required to carry the correction.
    correcting = [
        s for s in re.split(r"^(?=## \[\d+\.\d+\.\d+\] — \d{4}-\d{2}-\d{2}$)",
                            root_notes_text, flags=re.MULTILINE)[1:]
        if re.search(r"`?SheetTab\.hidden`?", s)
    ]
    assert correcting, "no release section publishes the correction at all"
    packaged_text = _corpus()["release_notes() (the packaged RELEASE_NOTES.md)"]
    for section in correcting:
        header = section.splitlines()[0]
        if header in packaged_text:
            assert re.search(r"`?SheetTab\.hidden`?", notes), (
                f"{header} is still inside the packaged window but its correction is not in "
                "the packaged copy — the projection must never edit a byte")


def test_ac6_the_code_fact_the_hidden_tab_sentence_rests_on_still_holds():
    """``SheetTab`` carries ``hidden``, and the WRITE client's tab query still does too.

    **Superseded in its conclusion, not in its reason.** Until LD-477 this asserted the
    opposite — that ``SheetTab`` had no such field — because the read recipe disclosed a gap
    and a disclosure must not outlive the thing it discloses. That is still exactly why this
    test exists; the fact underneath simply moved, so the assertion moved with it. A day this
    field is dropped again, the recipe's paragraph goes false in the other direction and this
    is what says so.
    """
    fields = {f for f in vars(SheetTab).get("__annotations__", {})}
    fields |= {name for name in dir(SheetTab) if not name.startswith("_")}
    assert "hidden" in fields, (
        "SheetTab lost `hidden` — the read recipe now tells a consumer the read route "
        "answers a tab's visibility, and that sentence is FALSE again. Move both together.")
    assert "hidden" in (inspect.getdoc(SheetsWriteClient.query_tabs) or ""), (
        "query_tabs no longer documents the `hidden` it carries — it remains the write side's "
        "own verification leg for a visibility write, which LD-477 did not touch")


def test_ac6_an_unknown_visibility_is_never_reported_as_visible():
    """The half of the fix that a careless simplification would undo.

    ``hidden=False`` is a claim that Lark said the tab is visible. A payload that says nothing
    yields ``None`` — the same honesty rule the frozen read and ``query_tabs`` live under.
    """
    assert SheetTab.from_dict({"sheet_id": "s1", "title": "T", "index": 0}).hidden is None
    assert SheetTab.from_dict({"sheet_id": "s1", "hidden": "true"}).hidden is None
    assert SheetTab.from_dict({"sheet_id": "s1", "hidden": False}).hidden is False


def test_ac6_the_read_recipe_states_that_the_read_ROUTE_answers_visibility():
    section = re.sub(r"\s+", " ", guide("recipe-read-a-sheet-to-markdown"))
    assert "hidden" in section.lower(), section[:400]
    assert "tab.hidden" in section or "SheetTab.hidden" in section, (
        "the read recipe does not hand over the field a consumer reads visibility from")
    assert re.search(r"\bNone\b", section), (
        "the read recipe does not say what an unanswered visibility reads as, which is the "
        "half of this field a report can get wrong silently")


# --------------------------------------------------------------------------- #
# AC7 — the relocation, disclosed on both recipes.                             #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("slug", [
    "recipe-insert-and-delete-rows-and-columns-a-structural-write",
    "recipe-add-a-dropdown-list-rule-to-a-range",
])
def test_ac7_both_recipes_disclose_the_dropdown_relocation(slug):
    section = re.sub(r"\s+", " ", guide(slug))
    assert "InsertColsAt" in section, slug
    assert "preview_note" in section, (
        f"{slug} no longer says that NOTHING warns about the relocation, which is the half of "
        "the disclosure a consumer plans around")
    assert "dropdown" in section.lower() or "validation" in section.lower(), slug


# --------------------------------------------------------------------------- #
# AC8 — the recipe stops promising a range.                                    #
# --------------------------------------------------------------------------- #

def test_ac8_the_float_image_recipe_title_no_longer_promises_a_range():
    headings = [row["heading"] for row in __import__("larkdocio").guide_sections()]
    floats = [h for h in headings if "float" in h.lower() and h.lower().startswith("recipe:")]
    assert floats, headings[:3]
    for heading in floats:
        assert "over a range" not in heading.lower(), (
            f"{heading!r} promises a range again — a multi-cell a1_range answers 1310202 "
            "Wrong Range, measured twice")


def test_ac8_the_refutation_replaced_the_unmeasured_label():
    section = re.sub(r"\s+", " ", guide(
        "recipe-float-a-picture-over-a-single-cell-anchor-the-float-image-write"))
    assert "1310202" in section, section[:400]
    assert "REFUTED" in section.upper(), section[:400]
    assert not re.search(r"multi-cell[^.]{0,60}unmeasured, not refuted", section), (
        "the superseded label is back: a multi-cell anchor is refuted, not untried")


def test_ac9_the_orphaned_token_consequence_is_stated_where_the_failure_happens():
    section = re.sub(r"\s+", " ", guide(
        "recipe-float-a-picture-over-a-single-cell-anchor-the-float-image-write"))
    assert "orphan_file_token" in section, section[:400]
    assert re.search(r"upload happens BEFORE the bind", section, re.IGNORECASE), section[:400]
