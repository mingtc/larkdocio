"""THE RE-TRUTH, content-guarded — and the SCOPE LIMIT that goes with it
(LD-192 / AC7 + AC8).

Four shipped sites called mermaid **write-hostile** and one of them quoted ``1770001 invalid
param`` **as fact**. A gate probe proved a specimen-shaped type-40 create is accepted
``code 0``, so all four were false. This file holds the correction in place, in both
directions:

* the **old wording is gone** for mermaid, and the new wording says the right thing — that
  mermaid is **API-creatable**, and that whatever remains inexpressible is **larkdocio's design
  choice, not an API limit**;
* **the bitable / sheet claims are BYTE-UNCHANGED.** This is the half that is easy to get
  wrong, and the probe's report warned about it explicitly: it covered **mermaid only**. An
  over-correction that quietly relicensed bitable (18) or sheet (30) would be the same
  category of error as the original — a claim about the API with no measurement behind it,
  just pointed the other way. So the surviving sentences are pinned **whole and exact** —
  each one quoted here at sentence length, not by a keyword — so "unchanged" means unchanged
  rather than "looks similar".

The fourth site is the **packaged** writer brief (``writer_brief()``), which reaches consumers
inside the wheel — so it is asserted through the public accessor, not by reading the repo file.
"""
import pathlib
import re

import pytest

from larkdocio import capabilities, guide, writer_brief
from larkdocio.write.model import NewBlock, NewBlockKind, NewParagraph

#: **How the byte-unchanged half is pinned, and why it is no longer read out of git.**
#: This check was first written against ``git show origin/develop:<path>``, which was a real
#: before/after comparison **while the correction sat on its branch** — and the KNOWN LIMIT
#: recorded here at the time said what would happen on landing: once the trunk contains the
#: new text, the same assertion degrades to a **presence check** against a moving ref, and
#: recommended pinning something immovable instead. Landing happened, so the ref leg was worth
#: nothing it could not get from the tree — while costing the suite a **live-git read**, the
#: one shape ``tests/test_no_test_reads_live_git.py`` exists to forbid (a question about a
#: checkout rather than about content: it skipped silently on a shallow clone or a detached
#: export, and answered differently depending on what the developer had fetched).
#:
#: What replaced it is **stronger**, not weaker: each surviving sentence is quoted **whole**,
#: at sentence length, as an immovable literal below. The presence check proved a keyword was
#: still somewhere on a ref; the pinned sentence proves the whole claim still reads exactly as
#: it shipped, in the tree the test is running against. The over-correction sweep
#: (:func:`test_NOTHING_anywhere_claims_bitable_or_sheet_became_creatable`) and the structural
#: check (:func:`test_the_unprobed_types_are_still_STRUCTURALLY_inexpressible`) never depended
#: on the ref and keep their full strength, exactly as that note anticipated.
_PINNED_AGAINST = "the shipped tree, by whole-sentence literal"


def _prose(text):
    """Collapse whitespace so a claim is matched by its WORDS, not by its line wrapping.

    Load-bearing: every one of these claims is wrapped in the shipped source, and a flat
    substring grep walks straight past a phrase that breaks across a line — the lesson the
    comment-anchor reassurance guard learned the hard way.
    """
    return " ".join(text.split())


#: The four sites, as the objects a consumer actually reads.
def _sites():
    return {
        "requests module docstring": __import__(
            "larkdocio.write.model.requests", fromlist=["x"]).__doc__,
        "NewParagraph docstring": NewParagraph.__doc__,
        "NewBlockKind docstring": NewBlockKind.__doc__,
        "packaged writer brief": writer_brief(),
    }


# =========================================================================== #
# AC7 (a) — the OLD wording is gone, at every one of the four sites             #
# =========================================================================== #

@pytest.mark.parametrize("name", list(_sites()))
def test_no_site_still_calls_MERMAID_write_hostile(name):
    """The exact shapes the four sites used, all of which named mermaid inside a
    hostile/inexpressible list."""
    text = _prose(_sites()[name])
    forbidden = (
        "bitable / sheet / mermaid",
        "bitable/sheet/mermaid",
        "sheet / mermaid",
        "sheet/mermaid",
    )
    for phrase in forbidden:
        assert phrase not in text, (
            f"{name} still groups mermaid with the write-hostile types: {phrase!r}")


#: Words that mark a mention of ``1770001`` near mermaid as a **correction** rather than a
#: claim. The re-truth has to be allowed to explain itself — "this code was once quoted for
#: mermaid and here is why that was wrong" is the honest form, and a test that banned the two
#: words from appearing together would forbid exactly that and push the docs toward silently
#: dropping the history instead.
_NARROWING_WORDS = ("narrowed", "malformed", "artifact", "not a prohibition",
                    "no ``add_ons`` object at all", "no `add_ons` object at all")


@pytest.mark.parametrize("name", list(_sites()))
def test_no_site_still_attaches_1770001_TO_MERMAID_AS_A_CURRENT_FACT(name):
    """The most damaging half: ``NewParagraph``'s docstring quoted the error code **as fact**
    for a group that included mermaid.

    The code may still appear — it is still true of bitable/sheet — and it may appear *near*
    mermaid, because explaining the correction requires naming what was corrected. What is
    forbidden is the **assertion**: wherever the two occur together, the passage must carry a
    narrowing word, so the reader meets the code as overturned history rather than as a live
    limit.
    """
    # THE PARAGRAPH is the unit of a claim, not a character window. A sliding window straddles
    # the boundary between "bitable/sheet are rejected 1770001" (true, and it must survive) and
    # the next paragraph's "Mermaid is NOT in that list" (the correction) — and would then
    # report the two TRUE statements as one false one. Splitting on blank lines asks the right
    # question: does any single claim assert the code for mermaid?
    offenders = []
    for paragraph in re.split(r"\n\s*\n", _sites()[name]):
        flat = _prose(paragraph).lower()
        if "1770001" not in flat or "mermaid" not in flat:
            continue
        if not any(w in flat for w in _NARROWING_WORDS):
            offenders.append(flat)
    assert not offenders, (
        f"{name} states 1770001 for mermaid without narrowing it:\n"
        + "\n---\n".join(offenders))


def test_the_NewParagraph_docstring_no_longer_makes_the_false_claim_at_all():
    """Pinned as its own test because this is the site the report singled out."""
    text = _prose(NewParagraph.__doc__)
    assert "bitable/sheet/mermaid are rejected" not in text
    assert "all spike-proven write-hostile" not in text


# =========================================================================== #
# AC7 (b) — the NEW wording says the right thing                                #
# =========================================================================== #

@pytest.mark.parametrize("name", ["NewParagraph docstring", "NewBlockKind docstring",
                                  "packaged writer brief"])
def test_each_site_now_says_mermaid_is_API_CREATABLE(name):
    text = _prose(_sites()[name]).lower()
    assert "api-creatable" in text or "creatable by the api" in text, name


@pytest.mark.parametrize("name", ["NewParagraph docstring", "NewBlockKind docstring",
                                  "packaged writer brief"])
def test_each_site_now_frames_the_closed_enum_as_OUR_CHOICE_not_an_API_LIMIT(name):
    """The precise correction the report asked for: the justification for the closed enum
    changes from *"the API refuses it"* to *"larkdocio has not shipped an authoring path"* —
    a **weaker and more honest** claim."""
    text = _prose(_sites()[name]).lower()
    assert "design choice" in text, name
    assert "not an api limit" in text or "api hostility" in text, name


def test_the_correction_names_the_EVIDENCE_rather_than_asserting_the_reversal():
    """A reversal with no evidence behind it is the same mistake as the original claim."""
    for name in ("NewParagraph docstring", "packaged writer brief"):
        text = _prose(_sites()[name]).lower()
        assert "specimen-shaped" in text, name
        assert "code 0" in text, name


# =========================================================================== #
# AC7 (c) — THE SCOPE LIMIT: bitable (18) and sheet (30) are BYTE-UNCHANGED      #
# =========================================================================== #

_BITABLE_SHEET_SURVIVORS = (
    # (path, the WHOLE sentence that must survive byte-for-byte, whitespace normalized)
    ("src/larkdocio/write/model/requests.py",
     "(image / board / embed / bitable / sheet — image/board create only as empty "
     "placeholders, and bitable/sheet are rejected ``1770001 invalid param``)"),
    ("src/larkdocio/write/model/requests.py",
     "there is no block-type discriminator, no image token, no embed url, no sheet/bitable "
     "reference to smuggle one of them through"),
)


@pytest.mark.parametrize("path, claim", _BITABLE_SHEET_SURVIVORS)
def test_a_surviving_bitable_sheet_claim_is_byte_identical_to_the_PINNED_sentence(path, claim):
    """The whole sentence, quoted here and required in the tree word for word — which is what
    makes "unchanged" a measurement rather than a resemblance.

    See the note on :data:`_PINNED_AGAINST` for why the sentence is pinned as a literal
    instead of read out of ``git show origin/develop:<path>``: on a moving ref that comparison
    became a presence check the moment the correction landed, exactly as its own KNOWN LIMIT
    predicted, while a whole-sentence literal is immovable and costs the suite no live-git
    read.
    """
    current = _prose(pathlib.Path(path).read_text(encoding="utf-8"))
    assert claim in current, f"{path} dropped a bitable/sheet claim: {claim!r}"


def test_NOTHING_anywhere_claims_bitable_or_sheet_became_creatable():
    """The over-correction guard, applied across every consumer-reaching surface at once.

    The probe covered mermaid only. So no shipped text may put bitable or sheet on the
    creatable side of a sentence, and the capability floor must not list them either.
    """
    surfaces = dict(_sites())
    surfaces["guide"] = guide(full=True)
    for name, text in surfaces.items():
        low = _prose(text).lower()
        for claim in ("bitable is creatable", "sheet is creatable",
                      "bitable (18) is creatable", "sheet (30) is creatable",
                      "bitable and sheet are creatable"):
            assert claim not in low, f"{name} relicensed an unprobed type: {claim!r}"

    floor = capabilities(full=True)["surfaces"]["docx-write"]["content_constraints"]
    kinds = " ".join(floor["creatable_kinds"]).lower()
    assert "bitable" not in kinds and "sheet" not in kinds, floor["creatable_kinds"]
    # …and the embedded surfaces are still on the not-creatable side, where the evidence
    # leaves them. The floor names them by PRODUCT ("Base" / "Sheet"), which is the consumer's
    # vocabulary — asserted as the floor really words it rather than as this test would.
    not_creatable = " ".join(floor["not_creatable"]).lower()
    assert "embed (iframe / base / sheet)" in not_creatable, floor["not_creatable"]


def test_the_unprobed_types_are_still_STRUCTURALLY_inexpressible():
    """Not merely documented as unsupported — actually unreachable, which is the property the
    closed enum exists for. Asserted through the model rather than through prose."""
    assert not [k for k in NewBlockKind if k.value in ("bitable", "sheet", "image", "board",
                                                       "embed", "iframe")]
    for absent in ("token", "url", "sheet_id", "app_token", "table_id", "file_token"):
        assert not hasattr(NewBlock.paragraph("x"), absent), (
            f"NewBlock grew a {absent!r} field — a hostile type could be smuggled through it")


# =========================================================================== #
# AC8 — findability: mermaid is discoverable as a CAPABILITY, not as a refusal   #
# =========================================================================== #

def test_the_guide_carries_an_EXECUTABLE_diagram_recipe():
    """AC8's substance. The recipe is executed by the extract-and-run harness
    (``tests/guide_recipes.py`` → ``_check_mermaid_authoring``); this asserts a consumer can
    *find* it and that it teaches both halves — the compiler and the create."""
    text = guide(full=True)
    assert "### Recipe: author a mermaid diagram (and change one)" in text
    recipe = text.split("### Recipe: author a mermaid diagram (and change one)", 1)[1]
    recipe = recipe.split("### Recipe:", 1)[0]
    for expected in ("larkdocio.mermaid", "flowchart(", "NewBlock.mermaid(",
                     "DeleteRequest", "dry_run", "apply("):
        assert expected in recipe, f"the diagram recipe never shows {expected}"


def test_the_diagram_recipe_teaches_the_REPLACE_route_and_its_COST():
    recipe = guide(full=True).split(
        "### Recipe: author a mermaid diagram (and change one)", 1)[1].split(
        "### Recipe:", 1)[0]
    # backticks stripped as well as whitespace collapsed: the claims are Markdown-formatted
    # in the shipped guide, and a check that tripped on `code spans` would be a check on the
    # formatting rather than on the promise.
    low = _prose(recipe).lower().replace("`", "").replace("**", "")
    assert "no in-place update" in low, recipe
    assert "delete + re-create" in low or "delete and re-create" in low, recipe
    assert "block_id changes" in low, recipe
    assert "do not cache" in low, recipe


def test_mermaid_is_findable_from_every_discovery_surface():
    """The 0-hit condition the report measured — ``mermaid`` appeared 0 times in ``guide()``
    and 0 times in ``capabilities()`` — cannot return, and now resolves to a capability."""
    import json

    assert "mermaid" in guide(full=True).lower()
    assert "mermaid" in json.dumps(capabilities(full=True)).lower()
    assert "mermaid" in writer_brief().lower()
    assert "mermaid" in capabilities(full=True)["surfaces"]["docx-write"][
        "content_constraints"]["creatable_kinds"]


def test_the_compiler_package_is_reachable_from_the_guide_and_really_exists():
    """A recipe that names a module the wheel does not carry is worse than no recipe."""
    import larkdocio.mermaid as m

    assert "larkdocio.mermaid" in guide(full=True)
    for name in ("flowchart", "sequence", "rules"):
        assert callable(getattr(m, name)), name
