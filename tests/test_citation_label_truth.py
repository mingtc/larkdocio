# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""LD-659 AC5 — the *"in the dev repo, not in the wheel"* label cannot come to name a file the
wheel carries.

**The AC's figure, re-derived: TWO, not ~42** — and this module is the derivation, which is what
the AC asked to be left behind (*"derive the population from the built wheel … and leave the
derivation as the guard so the label cannot drift again"*; its own ~42 is *"approximate and must
be replaced by the derived figure"*).

**Two** were found and corrected in this change, and the standing population is now zero.

The first was in `sheets/ops/__init__.py`'s contributor checklist, which read
*"REGISTER ``src/larkdocio/GUIDE.md`` — HAND-KEPT (in the dev repo)"*. There the parenthetical
meant *hand-kept rather than derived*, but it is the same four words the citation guards read as
*you do not have this file* — and the guide ships in the wheel. Corrected in this change; the two
rows around it (`tests/test_sheets_md_matrix.py`, `SHEETS.md`) carry the label truthfully.

The second was in `LARK_SETUP.md` — a **packaged** document, so a wheel-only reader met it —
which sent them to *"`README.md` in the dev repo, which is also the wheel's own description
page"*. The clause after the label contradicts the label: the README **is** in their install,
as its `METADATA` body. It now says so first. (Corrected at the root, the canonical home, and
materialised into the wheel copy by `scripts/sync-packaged-notes.sh`, never hand-edited.)

**Where ~42 comes from, since the number will be cited: the scope, not the labels.** Measured at
this pin, a WHOLE-FILE scope reports 36 in shipped Python alone — and that scope is one this
repo's own guards reject in writing (`front_door.python_prose_blocks`: *"a file-wide waiver
wearing a label's clothes"*). A SENTENCE scope, which sounds right, reports about ten, because
the sentences here are long: *"quoted verbatim by ``GUIDE.md`` and by ``SHEETS.md`` (in the dev
repo, not in the wheel)"* is one sentence making one true claim about the second path. The rule
that answers the question actually asked is the label's own CLAUSE, and a mislabel is a clause
with nothing unshipped left in it for the label to be true of (`front_door.mislabelled_citations`
carries the rule and the two rejected scopes). The arm at the bottom of this module pins the
coarse scope against a real example, so the next reader meeting a bigger figure does not have to
re-derive why it is bigger.

An empty population is exactly the condition under which a guard can pass because it could not
look, so every assertion below is paired: the corpora are asserted non-empty, the label is
asserted PRESENT in them, the detector is proven to fire on a crafted mislabel, and it is proven
to read the **manifest** rather than a hard-coded list of names.
"""
import pathlib

import pytest

import front_door as fd

REPO = pathlib.Path(__file__).resolve().parent.parent

#: Everything the wheel really carries, derived from the tree the wheel is built from.
#: ``tests/test_packaging.py`` is what proves that derivation equals a real build's ``RECORD``.
CARRIED = fd.wheel_carried_paths()


def corpus():
    """``{repo-relative path: text}`` for every file in the SHIPPED corpus that carries the
    label at all — every ``.py`` the wheel packages, plus every Markdown document it packages,
    plus the README (the wheel's ``METADATA`` body).

    **Derived from packaging, so a new module or a newly packaged document joins on its own**;
    the two existing citation guards read the same two corpora, which is the point — one corpus,
    two questions asked of it.

    **Why not the whole repo:** a walk over every file also collects the documents that DISCUSS
    this label — audit reports, dogfood harness records, a closed issue's notes, this module's
    own docstring — and a sentence quoting the label is not a sentence making the claim. Those
    hits were measured at this pin (nine repo-wide, seven of them meta) and excluding them by
    corpus is honest; excluding them by exception list would not be. The frozen copy of a
    packaged document under ``dev/dogfood5/harness/`` is captured evidence and is out of scope
    for the same reason: it is a record of what shipped, not a claim being made now.
    """
    found = {}
    texts = dict(fd.shipped_python_sources())
    texts.update(fd.shipped_doc_texts())
    for relative, text in texts.items():
        if fd.DEV_REPO_LABEL in text:
            found[relative] = text
    return found


# --------------------------------------------------------------------------- #
# The instrument, before its answer                                           #
# --------------------------------------------------------------------------- #

def test_the_corpus_is_not_empty_and_the_label_is_really_in_it():
    """The first way this guard could go quiet: nothing to read."""
    population = corpus()
    assert len(population) > 10, sorted(population)
    assert any(relative.endswith(".py") for relative in population)
    assert any(relative.endswith(".md") for relative in population)
    subjects = [subject
                for relative, text in population.items()
                for _offset, subject in fd.label_subjects(relative, text)]
    assert len(subjects) > 30, f"only {len(subjects)} labels — has the label been reworded?"
    named = [subject for subject in subjects if subject is not None]
    assert len(named) > 20, (
        f"only {len(named)} of {len(subjects)} labels name a file within the subject window — "
        "the detector has stopped finding subjects, which would make its answer vacuous")


def test_the_manifest_the_question_is_asked_of_is_the_real_one():
    """The second way: a manifest that came back empty would make every label 'correct'."""
    assert "src/larkdocio/GUIDE.md" in CARRIED
    assert "src/larkdocio/write/README.md" in CARRIED
    assert "src/larkdocio/read/download.py" in CARRIED
    # And the documents the label legitimately covers are NOT in it:
    for absent in ("BLOCKS.md", "SHEETS.md", "PERMISSIONS.md", "BASE.md", "DRIVE.md",
                   "tests/front_door.py"):
        assert absent not in CARRIED, absent


def test_the_detector_fires_on_a_CRAFTED_mislabel():
    """The third way: a detector that reports nothing whatever it is given."""
    text = '"""The guide `GUIDE.md` lives in the dev repo, not in the wheel."""\n'
    found = fd.mislabelled_citations("src/larkdocio/x.py", text, CARRIED)
    assert [subjects for _offset, subjects in found] == [("GUIDE.md",)]


def test_the_detector_is_SILENT_on_the_same_sentence_labelling_an_unshipped_file():
    """The pair to it: the label's subject is the nearest citation, so a sentence that names a
    shipped file and then labels an unshipped one is correct and must stay quiet."""
    text = ('"""Quoted verbatim by `GUIDE.md` and by `SHEETS.md` '
            '(in the dev repo, not in the wheel)."""\n')
    assert fd.mislabelled_citations("src/larkdocio/x.py", text, CARRIED) == []
    assert [subjects for _offset, subjects in
            fd.label_subjects("src/larkdocio/x.py", text)] == [("GUIDE.md", "SHEETS.md")]


def test_a_label_that_names_nothing_nearby_has_NO_subject_and_is_reported_as_such():
    """Not silently dropped: a corpus drifting into labels that name nothing is visible."""
    text = '"""The captures live in the dev repo, not in the wheel. ' + ("filler " * 80) + '"""\n'
    assert [subjects for _offset, subjects in
            fd.label_subjects("src/larkdocio/x.py", text)] == [()]
    assert fd.mislabelled_citations("src/larkdocio/x.py", text, CARRIED) == []


def test_the_detector_reads_the_MANIFEST_not_a_list_of_names():
    """AC6's second direction: a file that stops shipping. The same sentence must stop being a
    mislabel when the manifest stops carrying the file — otherwise the guard is a name list
    wearing a derivation's clothes."""
    text = '"""See `GUIDE.md` — in the dev repo, not in the wheel."""\n'
    assert fd.mislabelled_citations("src/larkdocio/x.py", text, CARRIED)
    unshipped = {path for path in CARRIED if path != "src/larkdocio/GUIDE.md"}
    assert fd.mislabelled_citations("src/larkdocio/x.py", text, unshipped) == []


def test_the_two_directions_are_COMPLEMENTARY_on_one_text():
    """The pair, on one file, both ways round: whichever way the manifest goes, exactly one of
    the two guards has something to say about a citation."""
    labelled = "## S\n\nSee `src/larkdocio/GUIDE.md` — in the dev repo, not in the wheel.\n"
    unlabelled = "## S\n\nSee `src/larkdocio/GUIDE.md` for the recipe.\n"
    packaged = fd.packaged_doc_paths()
    # GUIDE.md IS packaged: the labelled citation is the false one.
    assert fd.mislabelled_citations("README.md", labelled, CARRIED)
    assert fd.unlabelled_shipped_citations("README.md", unlabelled, packaged) == []
    # Pretend it is not: now the label is right and its absence is the defect.
    without = {path for path in packaged if path != "src/larkdocio/GUIDE.md"}
    assert fd.mislabelled_citations("README.md", labelled,
                                    CARRIED - {"src/larkdocio/GUIDE.md"}) == []
    assert fd.unlabelled_shipped_citations("README.md", unlabelled, without)


# --------------------------------------------------------------------------- #
# The answer                                                                  #
# --------------------------------------------------------------------------- #

def test_no_SHIPPED_file_calls_a_SHIPPED_file_unshipped():
    """The AC's question, over the derived corpus, at clause scope. **Two** were found and
    corrected in this change; the standing population is **zero**, and that is the derived
    figure that replaces the AC's approximate ~42."""
    offenders = {}
    for relative, text in corpus().items():
        found = fd.mislabelled_citations(relative, text, CARRIED)
        if found:
            offenders[relative] = found
    assert offenders == {}, (
        "these sentences tell a reader a file is not in the wheel, and the wheel carries it: "
        f"{offenders}"
    )


@pytest.mark.parametrize("relative", sorted(corpus()))
def test_no_SHIPPED_FILE_calls_a_shipped_file_unshipped(relative):
    """The same question per file, so a failure names the file rather than a dict. Parametrized
    off the corpus derivation, so a new module or packaged document joins on its own."""
    assert fd.mislabelled_citations(relative, corpus()[relative], CARRIED) == []


# --------------------------------------------------------------------------- #
# Why the coarse scope reported ~42 — pinned, because the number will be cited #
# --------------------------------------------------------------------------- #

def test_the_BLOCK_scope_over_reports_on_a_REAL_sentence_pair():
    """The refutation, as behavior rather than as prose: this is a real shipped block whose
    label is scoped by its own wording (*"that last one"*), and a block- or file-scoped
    instrument counts its `GUIDE.md` mention as a mislabel. This is the arm to read before
    citing a bigger population figure than this module's own."""
    relative = "src/larkdocio/sheets/ops/__init__.py"
    text = (REPO / relative).read_text(encoding="utf-8")
    # LD-699: SHEETS.md is in every clone, so its label is the source-repository one now.
    assert "that last one in the source repository, not in the wheel" in " ".join(text.split())
    assert "GUIDE.md" in text
    # Sentence scope: silent, because the label's own sentence names only SHEETS.md.
    assert fd.mislabelled_citations(relative, text, CARRIED) == []
    # Block scope: reports it. (The whole-file scope is this, only wider.)
    in_force = {}
    for first, last in fd.python_prose_blocks(text):
        line = fd.label_line(text, first, last)
        for number in range(first, last + 1):
            in_force[number] = line is not None and number >= line
    block_scoped = [
        cited
        for number, raw in enumerate(text.splitlines(), start=1) if in_force.get(number)
        for cited in fd._source_candidate_paths(raw)
        if fd.citation_resolves(relative, cited, CARRIED)
    ]
    assert block_scoped, "the coarse scope must really report here, or there is nothing to refute"
