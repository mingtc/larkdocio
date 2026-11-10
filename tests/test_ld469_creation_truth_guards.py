"""LD-469 — the three grep guards for *create the document, say who can read it, fill it*.

The defect class this issue fixes is a **confident wrong sentence**: the shipped guide asserted
without condition that a fresh docx is a document only the app can use and that its member read
answers ``items: []``. That is true of a document created with no folder and **false** of one
created into a folder, which is the case most integrations run. A wrong sentence is not caught
by a type, a signature or a round trip — only by a grep — so the guards here are greps, and they
run over the same consumer-reaching corpus the dialect guard uses.

Three subjects, one per AC:

* **AC1 / AC2** — the old absolute is gone from every consumer surface, and the two measured
  cases (no folder → empty; into a folder → inherited rows marked ``perm_type='container'``)
  are both stated where the claim lives.
* **AC4** — ``create_document(folder_token=…)`` is documented where a consumer meets document
  creation: the guide's docx write handshake and ``writer_brief()``, which had zero mentions.
* **AC5** — the 50-blocks-per-call cap is disclosed on the authoring path: the number, the
  constant's name, the docx-v1 origin, and the fact that the guard fires **at construction, as a
  ValueError, before ``dry_run``** — a different exception shape from the rest of the surface.
"""
import re

import pytest

import consumer_text
from larkdocio import guide, writer_brief
from larkdocio.write.model import MAX_CHILDREN_PER_CALL

#: The sentences LD-469 refuted. Each one shipped; none may come back, in any surface a
#: consumer reads. They are spelled as patterns rather than as literals because the wrong
#: claim is a *shape* — "a fresh document has no members, full stop" — not one wording.
REFUTED_ABSOLUTES = (
    ("a-fresh-docx-answers-items-[]",
     re.compile(r"fresh docx'?s member read answers\s+`*items: \[\]`*", re.I)),
    ("a-document-only-the-app-can-use",
     re.compile(r"a document (?:only the app|nobody but the app|nobody else) can use", re.I)),
    ("born-with-an-empty-member-list",
     re.compile(r"born\s+with\s+an?\s+\**empty member list", re.I)),
    ("every-fresh-document-has-an-empty-member-list",
     re.compile(r"(?:a|every) fresh(?:ly minted)? document has an empty member list", re.I)),
)


@pytest.fixture(scope="module")
def corpus():
    return consumer_text.consumer_corpus()


@pytest.fixture(scope="module")
def guide_text():
    return guide(full=True)


# --------------------------------------------------------------------------- #
# AC1 / AC2 — the ACL sentence.                                                #
# --------------------------------------------------------------------------- #

def test_ac1_no_consumer_surface_carries_the_refuted_absolute(corpus):
    """The measurement, not the edit, is what makes this a rule: a docx filed into a folder
    was measured carrying that folder's rows, so any surface still promising an empty member
    list unconditionally is shipping a claim this project has already falsified."""
    offenders = [
        (label, name, match.group(0))
        for label, text in corpus.items()
        for name, pattern in REFUTED_ABSOLUTES
        for match in pattern.finditer(text)
    ]
    assert not offenders, (
        "a consumer surface still states the refuted absolute — a fresh document's member list "
        f"is empty ONLY when it was created with no folder: {offenders}")


def test_ac1_the_guide_states_BOTH_measured_cases_where_the_claim_lives(guide_text):
    """Both cases, in the section a reader asking *who can read this* actually opens.

    LD-572 AC3 reframed the no-folder case: `folder_token` is required, so that case is no
    longer something a caller of this library can reach — it is a preserved HISTORICAL
    measurement of what Lark itself does with an unaddressed object, not a live choice. The
    two facts this test guards — both cases are stated, and both carry their measurement date
    — still hold; only the "live choice" framing of the no-folder case is gone (see the
    dedicated LD-572 guards in ``test_create_doors.py``)."""
    section = _flat(_section(guide_text, "### Recipe: grant a HUMAN access"))
    assert "a document filed nowhere" in section, (
        "the no-folder case (the control, measured empty) is not stated")
    assert "Created INTO a folder" in section, "the folder case is not stated"
    assert "inherits its parent folder's access" in section
    # Each half carries its verification label, the way every other measured claim here does.
    assert section.count("*Measured 2026-08-15*") >= 2
    assert "round-4" in section.lower()


def test_ac2_container_is_a_word_the_shipped_corpus_knows(guide_text, corpus):
    """``perm_type='container'`` is what a consumer gets back on the wire. Before LD-469 it
    appeared in NO shipped document, so a reader holding one had nothing to look it up in."""
    section = _flat(_section(guide_text, "### Recipe: grant a HUMAN access"))
    assert "perm_type='container'" in section
    assert "comes from the container" in section, (
        "the vocabulary is named but not explained — a reader still cannot tell what a "
        "container row IS")
    reached = [label for label, text in corpus.items() if "container" in text]
    assert reached, "no consumer-reaching surface mentions container membership at all"


# --------------------------------------------------------------------------- #
# AC4 — the argument that decides where the document lands.                    #
# --------------------------------------------------------------------------- #

def test_ac4_the_guide_documents_create_document_with_its_folder_token(guide_text):
    """LD-572 AC3 moved "what the argument decides, when it is missing" out of this section
    (it used to restate the app's-own-space consequence inline, presenting the omission as a
    live choice against a signature that refuses it) — this section now cross-references
    § "Where a new object goes" rather than restating it, and states plainly that the
    DESTINATION is required.

    **LD-586 transformed the pinned phrase, keeping the reason.** It used to require the words
    ``both are required``, which were false of the shipped signature: ``title`` defaults to the
    empty string and is never validated, so ``create_document(folder_token=f)`` creates an
    untitled document. Only ``folder_token`` is fenced, which is what the method's own docstring
    says — so the guard now pins that, and forbids the overclaim it used to require."""
    section = _flat(_section(guide_text, "### Recipe: the docx write handshake"))
    assert "create_document(title=" in section and "folder_token=" in section, (
        "the handshake does not show the two-argument form of create_document")
    assert "`folder_token` is the required one" in section, (
        "the handshake does not say the destination is the required argument")
    assert "both are required" not in section, (
        "`title` is not required, so this phrase overclaims the fence")
    assert "Where a new object goes" in section, (
        "the handshake does not point at the rule for what the argument decides")


def test_ac4_writer_brief_documents_it_too_and_stops_calling_it_teardown():
    """``writer_brief()`` had **zero** ``folder_token`` mentions and labelled the create verb
    ``(harness/teardown)`` — a consumer-facing verb filed as plumbing."""
    brief = writer_brief()
    assert "folder_token" in brief, "writer_brief() still never mentions folder_token"
    assert "`create_document` (harness/teardown)" not in brief, (
        "create_document is still labelled harness/teardown; it is consumer-facing")


# --------------------------------------------------------------------------- #
# AC5 — the 50-blocks-per-call cap, on the authoring path.                     #
# --------------------------------------------------------------------------- #

CAP_PAGES = (
    "## Authoring from Markdown",
    "### Recipe: the docx write handshake",
    "### Recipe: author a Markdown fragment into a document",
)


@pytest.mark.parametrize("heading", CAP_PAGES)
def test_ac5_the_cap_is_disclosed_where_a_large_fragment_is_authored(guide_text, heading):
    """The number and the constant, on every page a consumer authoring a big fragment reads."""
    section = _section(guide_text, heading)
    assert str(MAX_CHILDREN_PER_CALL) in section, (
        f"{heading!r} never states the number ({MAX_CHILDREN_PER_CALL})")
    assert "MAX_CHILDREN_PER_CALL" in section, (
        f"{heading!r} never names the constant, so the number cannot be looked up in code")


def test_ac5_the_caps_ORIGIN_and_its_EXCEPTION_SHAPE_are_both_stated(guide_text):
    """Two facts, both of which cost round-4 consumers time: the cap is **docx v1's**
    ``create_children`` window, and its guard fires at CONSTRUCTION as a ``ValueError`` —
    before ``dry_run``, in a different shape from every typed refusal on this surface."""
    section = _flat(_section(guide_text, "## Authoring from Markdown"))
    assert "create_children" in section, "the cap's origin (the docx v1 call) is not named"
    assert "ValueError" in section, "the exception SHAPE is not stated"
    assert "before `dry_run`" in section, (
        "the guard's timing is not stated — a consumer expects a typed refusal in the plan")


def test_ac5_the_number_the_guide_states_is_the_constants_own(guide_text):
    """A hand-typed 50 that drifts from the code is the next wrong sentence. The guide may
    state the number, but every page that does must also name the constant it came from."""
    for heading in CAP_PAGES:
        section = _section(guide_text, heading)
        for standalone in re.finditer(r"\b50\b", section):
            assert "MAX_CHILDREN_PER_CALL" in section, standalone.group(0)
    assert MAX_CHILDREN_PER_CALL == 50, (
        "the constant moved; every guide page stating the number must be re-cut with it")


def test_ld564_the_write_readme_dialect_section_also_co_locates_the_constant():
    """LD-564 — the same co-location discipline as the CAP_PAGES guard just above,
    extended to the genuinely silent shipped surface: ``write/README.md``'s compose
    dialect section (reachable as ``writer_brief()``), which named ``MAX_NEST_DEPTH``
    and ``MAX_TABLE_CELLS`` but not ``MAX_CHILDREN_PER_CALL`` before this fix. The
    guide itself needed no change here (LD-469 already landed it)."""
    section = writer_brief(section="The composable Markdown dialect (`compose`)")
    assert "MAX_CHILDREN_PER_CALL" in section, (
        "the dialect section never names the 50-per-call cap's constant")
    for standalone in re.finditer(r"\b50\b", section):
        assert "MAX_CHILDREN_PER_CALL" in section, standalone.group(0)
    assert MAX_CHILDREN_PER_CALL == 50, (
        "the constant moved; write/README.md's dialect section must be re-cut with it")


# --------------------------------------------------------------------------- #
# AC6 — the batching recipe is present (that it RUNS is guide_recipes' job).   #
# --------------------------------------------------------------------------- #

def test_ac6_the_batching_recipe_exists_and_teaches_all_three_steps(guide_text):
    section = _flat(_section(guide_text, "### Recipe: author more than one call's worth of blocks"))
    for taught in ("MAX_CHILDREN_PER_CALL", "AnchorById", "created_block_ids"):
        assert taught in section, f"the batching recipe never uses {taught}"
    assert "..." not in section.replace("...,", ""), (
        "the recipe carries an ellipsis where a call belongs — it must be pasteable whole")


def _flat(text):
    """``text`` with every whitespace run collapsed — so a guard pins a SENTENCE rather than
    the column the guide happens to wrap it at."""
    return " ".join(text.split())


def _section(text, heading):
    """The text from ``heading`` up to the next heading of the same or a higher level."""
    start = text.index(heading)
    level = len(heading) - len(heading.lstrip("#"))
    rest = text[start + len(heading):]
    ends = [m.start() for m in re.finditer(r"^#{1,%d} " % level, rest, re.M)]
    return heading + (rest[:ends[0]] if ends else rest)
