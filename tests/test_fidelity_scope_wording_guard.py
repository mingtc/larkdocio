# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""THE CONTENT GUARD for what the fidelity read leg CLAIMS (LD-154 / dogfood F18, AC2).

The investigation (`tests/test_sheets_fidelity_style_scope.py`) settled the behaviour: the
leg reports **whole-cell (format-level)** style, run-level emphasis arrives over the values
leg, and the two are layered. What shipped was an **absolute** claim — bold/italic
*"invisible to the values API"* — which is false for the run-level emphasis the values API
plainly does carry. A consumer measures the flag against that sentence, turns it on, sees no
change on a hand-bolded sheet, and reasonably concludes the flag is broken.

So this guard is two-sided, and both sides matter:

* **the absolute claim is GONE** from every consumer-reaching surface — not merely
  "somewhere the precise claim also exists". The corpus is
  ``tests/consumer_text.consumer_corpus()``, the same four-pass corpus the internal-dialect
  guard greps (both shipped docs through their public accessors, every emitted string
  literal in ``src/``, every public docstring reached by introspection, and real runtime
  plan/registry values) — so a regrowth anywhere in the shipped text reddens here;
* **the precise claim is PRESENT** in each surface that describes the flag, together with
  the run-level contrast that makes "it added nothing" legible as *expected* rather than
  *broken*.

A ``#`` comment is deliberately out of scope (it is not in the corpus by construction): a
maintainer standing in this repo may write whatever shorthand they like next to the code.
"""
import re

import consumer_text

import larkdocio
from larkdocio.cli import cli
from larkdocio.sheets.embed import deep_read_embedded_sheet
from larkdocio.sheets.render import apply_cell_emphasis
from larkdocio.sheets.table import render_matrix, render_spreadsheet, render_tab

# --------------------------------------------------------------------------- #
# The claim, in both directions.                                               #
# --------------------------------------------------------------------------- #

#: The ABSOLUTE claim, in every phrasing it shipped in. Each is false as written: the
#: values API carries run-level ``segmentStyle`` emphasis, so "the values API cannot see
#: bold" is only true of bold applied as a CELL FORMAT.
FORBIDDEN_ABSOLUTE_CLAIMS = (
    "invisible to the values",
    "values api cannot see",
    "values read cannot see",
    "values api can't see",
)

#: The claim is only wrong when its **subject** is emphasis. "A values read cannot see a
#: **merge**" is the same sentence shape and is simply TRUE (merge geometry really does
#: live only in the v3 tab query), so the guard reads the phrase's own neighbourhood and
#: fires only on the style subject. Banning the sentence shape outright would have forced
#: a correct statement to be reworded to satisfy a guard — the tail wagging the dog.
_STYLE_SUBJECT = re.compile(r"bold|italic|emphasis", re.IGNORECASE)

#: How far either side of the phrase counts as its subject. Small on purpose: a wide
#: window in a long document picks up an unrelated paragraph's "bold".
_SUBJECT_WINDOW = 120

#: A **quoted** span — the shape a document uses when it is naming a sentence rather than
#: asserting one. Bounded and newline-free so a stray quote cannot swallow a page.
_QUOTED = re.compile(r'"[^"\n]{1,240}"|“[^”\n]{1,240}”')

#: A retraction of the quoted sentence, in the phrasings a release note actually uses.
_RETRACTION = re.compile(
    r"\b(?:is|are|was|were|has\s+been|have\s+been)\s+(?:now\s+)?"
    r"(?:gone|removed|dropped|deleted|corrected|replaced|reworded|retired)\b"
    r"|\bno\s+longer\b",
    re.IGNORECASE,
)

#: How far past the closing quote a retraction still governs it. Deliberately short: the
#: retraction has to be part of the same clause, not merely somewhere in the paragraph.
_RETRACTION_WINDOW = 60


def _retracted_quotes(text: str):
    """``[(start, end)]`` character spans of a quote the surrounding clause RETRACTS.

    The claim is only a claim when a document **asserts** it. A release note announcing the
    correction has to quote the false sentence to say it is gone, and a guard that fired there
    would forbid the announcement of its own fix — which is how a guard stops being obeyed.

    Both conditions are required, and that is what keeps the carve-out from being a loophole:
    the phrase must sit inside a quoted span **and** that span must be immediately retracted.
    A quoted assertion still bites; an unquoted assertion near the word "removed" still bites.
    """
    spans = []
    for match in _QUOTED.finditer(text):
        tail = text[match.end():match.end() + _RETRACTION_WINDOW]
        head = text[max(0, match.start() - _RETRACTION_WINDOW):match.start()]
        if _RETRACTION.search(tail) or _RETRACTION.search(head):
            spans.append((match.start(), match.end()))
    return spans


#: The precise scope, which is what the export leg actually reads.
SCOPE_PHRASE = "whole-cell (format-level)"

#: The contrast that makes a no-op render legible. Both halves are required: the term
#: itself, and the values API it travels over.
CONTRAST_TERM = "run-level"
CONTRAST_CARRIER = "values API"


def flatten(text: str) -> str:
    """Collapse every whitespace run to one space.

    **Load-bearing, not cosmetic.** A docstring wraps its prose, so the claim shipped in
    ``apply_cell_emphasis`` as ``"invisible to the\\nvalues API"`` — a flat substring grep
    walks straight past it, and the first draft of this guard did exactly that (it reported
    4 hits where there were 6). Every side of the guard reads flattened text, so reflowing
    a paragraph can never hide or reveal a claim.
    """
    return " ".join((text or "").split())


def _flag_summary() -> str:
    return larkdocio.capabilities(full=True)["flags"]["fidelity_read_sheets"]["summary"]


def _cli_help() -> str:
    for param in cli.commands["download"].params:
        if param.name == "fidelity_read_sheets":
            return param.help
    raise AssertionError("the download command has no --fidelity-read-sheets option")


def _guide_flag_row() -> str:
    for line in larkdocio.guide(full=True).splitlines():
        if line.startswith("| `fidelity_read_sheets`"):
            return line
    raise AssertionError("the guide's flag table has no fidelity_read_sheets row")


#: Every surface that DESCRIBES the flag, and must therefore state its scope precisely.
#: ``render_matrix`` is the one the seat session found the precise claim in — it is here so
#: it can never become the only one again.
def flag_describing_surfaces() -> dict:
    """``{label: flattened text}`` — flattened so a line wrap cannot hide a phrase.

    Comparisons against this map are **case-insensitive** (see :func:`_says`): a sentence
    that opens with "Run-level emphasis…" states the contrast exactly as well as one that
    mentions it mid-sentence, and a guard that cared would be enforcing prose style rather
    than content.
    """
    return {label: flatten(text) for label, text in {
        "capabilities()['flags']['fidelity_read_sheets']['summary']": _flag_summary(),
        "guide() flag-table row": _guide_flag_row(),
        "cli --fidelity-read-sheets help": _cli_help(),
        "render_matrix.__doc__": render_matrix.__doc__,
        "apply_cell_emphasis.__doc__": apply_cell_emphasis.__doc__,
        "render_tab.__doc__": render_tab.__doc__,
        "render_spreadsheet.__doc__": render_spreadsheet.__doc__,
        "deep_read_embedded_sheet.__doc__": deep_read_embedded_sheet.__doc__,
    }.items()}


# --------------------------------------------------------------------------- #
# AC2 (negative half) — the absolute claim is GONE, everywhere.                #
# --------------------------------------------------------------------------- #

def absolute_style_claim_hits(corpus=None):
    """``[(label, snippet)]`` for every place the corpus still makes the ABSOLUTE claim
    **about emphasis**. Exposed so a mutation probe can call it directly."""
    corpus = consumer_text.consumer_corpus() if corpus is None else corpus
    hits = []
    for label, raw in corpus.items():
        text = flatten(raw)
        lowered = text.lower()
        retracted = _retracted_quotes(text)
        for claim in FORBIDDEN_ABSOLUTE_CLAIMS:
            start = 0
            while (where := lowered.find(claim, start)) != -1:
                start = where + 1
                window = text[max(0, where - _SUBJECT_WINDOW):
                              where + len(claim) + _SUBJECT_WINDOW]
                if not _STYLE_SUBJECT.search(window):
                    continue        # the subject is a merge / geometry — a true claim
                if any(begin <= where < end for begin, end in retracted):
                    continue        # quoted and retracted — naming the claim, not making it
                hits.append((label, f"…{text[max(0, where - 80):where + 120]}…"))
    return hits


def test_the_absolute_claim_is_absent_from_every_consumer_reaching_surface():
    hits = [f"{label}: {snippet}" for label, snippet in absolute_style_claim_hits()]
    assert not hits, (
        "a consumer-reaching surface still claims the fidelity leg's styles are invisible "
        "to the values API. That is false for RUN-level emphasis, which the values API "
        f"carries; say {SCOPE_PHRASE!r} instead.\n  " + "\n  ".join(hits)
    )


def test_the_guard_BITES_on_a_regrown_claim_even_when_it_is_LINE_WRAPPED():
    """Red-then-green on the detector itself, in the shape that actually defeated the first
    draft: the claim spread across a docstring's line wrap.

    Without :func:`flatten` this corpus reports **zero** hits while plainly making the
    claim — which is how two of the six real occurrences hid."""
    wrapped = {
        "a docstring": (
            "Wrap a cell's text in emphasis.\n\n"
            "Cell bold / italic live only in the export (invisible to the\n"
            "values API), so this runs on the opt-in path.\n"
        ),
    }
    assert absolute_style_claim_hits(wrapped), (
        "the guard did not see a wrapped claim — flatten() is not doing its job")

    # And the naive version really is blind to it, which is what makes flatten() earn its
    # place rather than being defensive noise.
    naive = [text for text in wrapped.values() if "invisible to the values" in text]
    assert not naive, "the wrap no longer splits the phrase; this probe is stale"


def test_the_guard_does_NOT_bite_a_true_claim_about_MERGE_geometry():
    """The other side of the boundary — a MUST-NOT-bite. "A values read cannot see a merge"
    is the same sentence shape and is simply TRUE; the shipped guide and ``sheets/ops/``
    both say it. A guard that fired here would force correct prose to be reworded."""
    true_claims = {
        "the guide's merge paragraph": (
            "Merge geometry lives only in the v3 tab query. A values read cannot see a "
            "merge, so the tab's merges array comes from query_sheets."
        ),
        "a preview note": (
            "the merge geometry (query_sheets(...)['merges']) — merge geometry lives ONLY "
            "in the v3 tab query; a values read cannot see it."
        ),
    }
    assert not absolute_style_claim_hits(true_claims), (
        "the guard fired on a true statement about merges — the ban must be scoped to the "
        "emphasis subject, not to the sentence shape"
    )


def test_the_guard_does_NOT_bite_a_QUOTED_claim_that_the_sentence_RETRACTS():
    """The third boundary, found when the guarded corpus widened over the release notes.

    A release note announcing the correction has to **quote** the false sentence in order to
    say it is gone. Firing there would mean the guard forbids the announcement of its own fix —
    the same failure mode that made a line-window misattribution detector flag its own
    correction. A retraction is not an assertion.
    """
    retractions = {
        "the release note that announces the fix": (
            'The claim that cell emphasis is "invisible to the values API" is gone: the '
            "export-fidelity read reports whole-cell, format-level styling, while run-level "
            "emphasis arrives over the values leg."
        ),
        "the same thing said the other way round": (
            'A sentence saying bold is "invisible to the values API" was removed from every '
            "surface that describes the flag."
        ),
    }
    assert not absolute_style_claim_hits(retractions), (
        "the guard fired on a QUOTED-AND-RETRACTED claim — it now forbids describing its own "
        "fix, which is how a guard gets deleted rather than obeyed"
    )


def test_the_retraction_carve_out_is_not_a_LOOPHOLE():
    """And it must be narrow. Quoting alone does not excuse the claim, and neither does the
    word "removed" somewhere nearby — the claim has to be quoted **and** retracted."""
    quoted_but_asserted = {
        "a quote with no retraction": (
            'The fidelity leg reads bold, which is "invisible to the values API".'
        ),
    }
    assert absolute_style_claim_hits(quoted_but_asserted), (
        "a quoted claim with nothing retracting it is still the claim"
    )

    unquoted_near_a_retraction = {
        "an assertion beside an unrelated removal": (
            "The deprecated helper was removed. Cell bold is invisible to the values API."
        ),
    }
    assert absolute_style_claim_hits(unquoted_near_a_retraction), (
        "an UNQUOTED assertion is the claim however many retraction words sit near it"
    )


def test_the_subject_scoping_is_not_so_wide_that_it_never_bites():
    """And the scoping must not be a loophole: the same merge sentence in a paragraph that
    IS about bold is still the wrong claim, and is still caught."""
    about_style = {
        "a mixed paragraph": (
            "The fidelity leg reads a cell's bold and italic. A values read cannot see it."
        ),
    }
    assert absolute_style_claim_hits(about_style)


def test_the_corpus_the_guard_greps_is_the_full_four_pass_corpus():
    """The guard is only as wide as its corpus, so pin that the corpus really is the
    four-pass one (a dropped pass would silently narrow this guard to nothing)."""
    corpus = consumer_text.consumer_corpus()
    assert set(consumer_text.shipped_docs()) <= set(corpus)
    for pass_fn in (
        consumer_text.emitted_literals,
        consumer_text.public_docstrings,
        consumer_text.runtime_json_strings,
    ):
        keys = set(pass_fn())
        assert keys, f"corpus pass {pass_fn.__name__} is empty"
        assert keys <= set(corpus), f"corpus pass {pass_fn.__name__} is not in the corpus"


# --------------------------------------------------------------------------- #
# AC2 (positive half) — the precise claim is PRESENT, in every surface.        #
# --------------------------------------------------------------------------- #

def _says(text: str, phrase: str) -> bool:
    return phrase.lower() in (text or "").lower()


def test_every_flag_describing_surface_states_the_whole_cell_scope():
    missing = [
        label for label, text in flag_describing_surfaces().items()
        if not _says(text, SCOPE_PHRASE)
    ]
    assert not missing, (
        f"these surfaces describe the fidelity leg without naming its scope "
        f"{SCOPE_PHRASE!r}: {missing}"
    )


def test_every_flag_describing_surface_names_the_run_level_contrast():
    missing = [
        label for label, text in flag_describing_surfaces().items()
        if not (_says(text, CONTRAST_TERM) and _says(text, CONTRAST_CARRIER))
    ]
    assert not missing, (
        f"these surfaces name the scope but not the contrast — a consumer cannot tell "
        f"'added nothing' from 'broken' without being told {CONTRAST_TERM!r} emphasis "
        f"comes through the {CONTRAST_CARRIER}: {missing}"
    )


def test_the_no_op_case_is_called_expected_not_broken_where_a_consumer_decides():
    """The three surfaces a consumer actually reads before turning the flag on must say,
    in words, that adding nothing to a run-level-styled sheet is the correct outcome."""
    for label in (
        "capabilities()['flags']['fidelity_read_sheets']['summary']",
        "guide() flag-table row",
        "cli --fidelity-read-sheets help",
    ):
        text = flag_describing_surfaces()[label]
        assert re.search(r"already|expected", text, re.IGNORECASE), (
            f"{label} does not tell a consumer that a run-level-styled sheet is ALREADY "
            f"rendered with emphasis, so the flag adding nothing there is expected:\n{text}"
        )


def test_the_scope_phrase_is_dialect_free():
    """AC7: the new strings must pass the internal-dialect guard too."""
    for label, text in flag_describing_surfaces().items():
        hits = consumer_text.dialect_hits(text or "")
        assert not hits, f"{label} carries internal dialect: {hits}"
