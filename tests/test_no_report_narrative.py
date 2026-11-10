"""LD-715 — the exported tree describes each fix by what changed, never by who reported it.

**The rule** (owner ruling, 2026-11-07). A fix is told on its own terms — *"X now refuses Y"* —
with no story of how it came to light: no "a consumer reported / asked / found / lost …", no
consumer verdicts or critiques, and no counts of a consumer's runs. The private repository keeps
its full history; this holds the exported, consumer-facing text.

**Why one guard, and why it runs in both trees.** The private repository's anonymisation guards
(``tests/test_consumer_report_particulars.py``, now ``@private_tree.reports``) held how a cited
report was worded. Once the public text cites no report, that wording has no subject there, and
what has to be held is simpler: that the narrative does not come back. This module holds it over
the same corpus in either tree, so a sentence that would re-introduce it reddens here, in the
change that writes it.

**What is NOT this class.** ``consumer`` is this project's word for whoever uses the library, so a
generic statement in the present tense — *"a consumer runs"*, *"consumers hit both
interchangeably"*, *"the consumer kit"* — is not narrative. Neither is the evidence label
``consumer-observed`` (a verification class, like ``captured`` and ``measured``). The patterns
below are matched by MEANING, not by a list of sentences: a consumer or an integration as the
subject of a past-tense story verb (*reported, reached, walked, fired, source-dived …*, through a
perfect tense and an adverb — *"had independently reached"*); report nouns attached to one; a
COUNT of consumers or integrations (*"two consumers"*, *"eight integrations"*); a review run or
round (*"consumer-review runs"*, *"in one review round"*); a report addressed to the project
(*"reported to this project"*); source-diving; a verdict word (*"called it the best …"*); and one
particular consumer's artefact (*"the consumer's own 6 × 36 table"*) — where the generic *"a
consumer's own writing"* / *"the consumer's own words"* (whoever the caller is) stays spared.
``test_the_patterns_catch_each_framing_and_spare_the_generic_ones`` holds both halves, and every
line LD-715's QA bounce found the first widening missing is one of its plants. The second
bounce found the same story told about *a caller*, *people*, *a user*, *an agent* or *the
six-release reader*, so those subjects are covered too — by the determiner that makes a story
(``_WHO_OTHER``), because *"the caller"* of a documented function is the API's own vocabulary.

**Scope** (LD-715 AC3). The consumer-facing corpus: the shipped package (code, packaged
documents and ``config.json``), every file of the consumer kit (``hooks/post-merge`` included),
and every root file and script ``dev/public-export/export.py`` INCLUDE names outside ``tests/``
— the root ``CHANGELOG.md`` read from its public override source when this is the private tree,
so the bytes held are the bytes the export carries. Test docstrings and
comments are not yet in it — see the LD-715 activity log for what was left.
"""
import re
from pathlib import Path

from guard_kit import REPO_ROOT

ROOT = Path(REPO_ROOT)

#: Where a reader of the public tree meets consumer-facing prose.
#: Every file of ``consumers/`` is text (``hooks/post-merge`` has no suffix), so it is globbed whole.
_GLOBS = ("src/larkdocio/**/*.py", "src/larkdocio/**/*.md", "src/larkdocio/**/*.json",
          "consumers/**/*",
          "BASE.md", "BLOCKS.md", "CHANGELOG.md", "DRIVE.md", "LARK_SETUP.md", "PERMISSIONS.md",
          "README.md", "RELEASE_NOTES.md", "SHEETS.md", "TOOLS.md",
          # the rest of what the export carries outside tests/ (dev/public-export/export.py INCLUDE)
          "pyproject.toml", "MANIFEST.in", "LICENSE", ".gitignore",
          ".env.example", "setup.sh", "scripts/verify.sh", "scripts/sync-packaged-notes.sh")

#: The export writes a few root files from a different source (export.py PUBLIC_OVERRIDES): the
#: private tree's root CHANGELOG.md is the internal log, and the PUBLIC one is this source. Read
#: here, the guard holds the bytes the export will carry; in the public tree the source is absent
#: and the root file already is those bytes.
_PUBLIC_SOURCE = {"CHANGELOG.md": "dev/public-export/public/CHANGELOG.md"}

_W = r"[\s#:*>]+"  # a word gap that may cross a wrapped line, a comment marker or emphasis
_WHO = (r"\b(?:a|an|one|two|three|four|five|six|seven|eight|the|every|each|independent|real|"
        r"fresh|downstream|separate)" + _W + r"(?:\w+" + _W + r")?(?:consumers?|integrations?)(?:'s)?")
#: The story's subject is not always called a consumer: ``a caller wrote``, ``people reached
#: for``, ``one user said``, ``an agent lost a day``, ``the six-release reader was burned`` tell
#: the same story (LD-715's second QA bounce). These words are ALSO the API's ordinary
#: vocabulary — ``the values the caller wrote``, ``what the caller asked for``, ``a user
#: session``, ``nothing a reader met said`` — so the meaning is held by the determiner: a story
#: is told about AN unnamed one (*a / an / one / two …*) or about ``people``, never about THE
#: caller of the function being documented, and never inside ``nothing / anything a reader …``.
_OTHER = r"(?:callers?|users?|readers?|agents?|teams?)"
_WHO_OTHER = (r"(?:(?<!nothing\s)(?<!anything\s)(?<!everything\s)\b(?:a|an|one|two|three|four|"
              r"five|six|seven|eight|independent|real|fresh|downstream|separate)" + _W +
              r"(?:[\w-]+" + _W + r")?" + _OTHER + r"(?:'s)?|\bpeople)")
#: Perfect tense and an adverb sit between the subject and the verb of a story just as often as
#: not — *"two consumers had independently reached"*, *"had already walked through"*.
_TENSE = (r"(?:(?:had|have|has)" + _W + r")?(?:(?:already|independently|separately|both|each|"
          r"all|\w+ly)" + _W + r")?")
_STORY_VERB = (r"(?:reported|asked|said|wrote|found|discovered|believed|lost|ran|met|"
               r"reached(?!" + _W + r"(?:this|that|the)" + _W + r"(?:branch|path|route|line|code)\b)|"
               r"walked|fired|tried|guessed|stumbled|struggled|complained|praised|called|"
               r"source-dived|re-derived|was" + _W + r"(?:burned|bitten)|got" + _W +
               r"(?:burned|bitten)|kept" + _W + r"(?:arriving|asking|reaching|hitting|coming)|"
               r"hand-wrote|hand-rewrote|hand-rebuilt|hand-rolled|came" + _W + r"to" + _W +
               r"report|hit(?:" + _W + r"(?:that|this|it|the|a)\b|\s+`))")
_REPORT_NOUN = (r"(?:report|critique|review|session|incident|verdict|field" + _W +
                r"exercise)\b")
_COUNT = r"(?:two|three|four|five|six|seven|eight|nine|ten|twelve|\d+)"

#: name → the pattern of one framing of the class.
PATTERNS = {
    "a consumer + a story verb": re.compile(_WHO + _W + _TENSE + _STORY_VERB, re.IGNORECASE),
    "a caller, user, reader, agent or team + a story verb": re.compile(
        _WHO_OTHER + _W + _TENSE + _STORY_VERB, re.IGNORECASE),
    "a reader or caller, burned": re.compile(
        r"\bthe" + _W + r"(?:[\w-]+" + _W + r")?" + _OTHER + _W + r"(?:was|were|got)" + _W +
        r"(?:burned|bitten)\b", re.IGNORECASE),
    "the founding incident": re.compile(r"\b(?:founding" + _W + r"(?:incident|report)\b|"
                                        r"(?:that|this)" + _W + r"incident's\b)", re.IGNORECASE),
    "labelled as reported": re.compile(r"\blabell?ed" + _W + r"as" + _W + r"reported\b",
                                       re.IGNORECASE),
    "a consumer's report noun": re.compile(_WHO + _W + _REPORT_NOUN, re.IGNORECASE),
    "a consumer's agent, or a consumer ask": re.compile(r"\bconsumer(?:'s" + _W + r"agent|" + _W +
                                                       r"ask)\b", re.IGNORECASE),
    "consumer-reported": re.compile(r"\bconsumer[- ]reported\b", re.IGNORECASE),
    "reported by a consumer": re.compile(r"\breported" + _W + r"by" + _W + r"(?:a|an|one|the)" + _W +
                                         r"(?:\w+" + _W + r")?consumer", re.IGNORECASE),
    "a consumer's run, counted": re.compile(r"\b(?:one|two|\d+)" + _W + r"(?:\w+" + _W +
                                            r")?consumer" + _W + r"runs?\b(?!" + _W + r"(?:it|a|the|this))",
                                            re.IGNORECASE),
    "in consumer use": re.compile(r"\bin" + _W + r"consumer" + _W + r"use\b", re.IGNORECASE),
    "the reporter": re.compile(r"\bthe" + _W + r"reporter\b", re.IGNORECASE),
    "consumers or integrations, counted": re.compile(
        r"\b" + _COUNT + _W + r"(?:(?:separate|independent|different|distinct|real|downstream)"
        + _W + r")?(?:consumers|integrations)\b(?!" + _W + r"of\b)", re.IGNORECASE),
    "a review run or round": re.compile(r"\b(?:consumer[- ]review|review" + _W +
                                        r"(?:runs?|rounds?))\b", re.IGNORECASE),
    "reported to this project": re.compile(r"\breported" + _W + r"to" + _W + r"(?:this|the)" +
                                           _W + r"project\b", re.IGNORECASE),
    "source-diving": re.compile(r"\bsource[- ]div(?:ing|ed|ers?|es?)\b", re.IGNORECASE),
    "a verdict word": re.compile(r"\b(?:called|rated|judged|named|praised)(?:" + _W +
                                 r"(?:it|this|that|them))?" + _W + r"(?:the" + _W +
                                 r")?(?:best|worst|clearest|most" + _W + r"\w+)\b",
                                 re.IGNORECASE),
    "one consumer's own artefact": re.compile(
        r"\bthe" + _W + r"consumer's" + _W + r"own" + _W + r"(?:[\w×=-]+" + _W + r"){0,5}?"
        r"(?:grid|table|example|shape|idea|repo|project|run|case)\b", re.IGNORECASE),
}

#: This file states the rule, so it names the framings it forbids.
_EXEMPT = {"tests/test_no_report_narrative.py"}


def _corpus():
    seen = set()
    for pattern in _GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            rel = path.relative_to(ROOT).as_posix()
            if rel in _EXEMPT or rel in seen or not path.is_file() or "__pycache__" in rel:
                continue
            seen.add(rel)
            source = ROOT / _PUBLIC_SOURCE.get(rel, rel)
            yield rel, (source if source.is_file() else path).read_text(encoding="utf-8")


def narrative(text):
    """``[(line, framing, matched)]`` for every report-narrative framing in ``text``."""
    found = []
    for name, regex in PATTERNS.items():
        for match in regex.finditer(text):
            found.append((text.count("\n", 0, match.start()) + 1, name, match.group(0)))
    return sorted(found)


def test_the_patterns_catch_each_framing_and_spare_the_generic_ones():
    """Each plant is an invented sentence of the class; each spared one is generic usage the
    exported text legitimately carries."""
    for plant in (
        "which is the jump a consumer reported making — six releases",
        "A consumer hit ``for_a1(...)`` and got a bare error",
        "two independent consumers asked for exactly this",
        "and one consumer\nhand-rebuilt the manifest that already ships",
        "it is a **consumer-reported incident** (a refused token)",
        "on one tenant, reported by one consumer on one day",
        "one consumer run believed the sentence",
        "Twice, in consumer use, a run was believed complete",
        "The reporter agreed, and it is the right reading",
        "**The failure this cures**, as a consumer's report put it",
        "a consumer's agent built one of these from a client",
        "#: authored across two Bases in a consumer session were dead",
        "The consumer ask that produced this section",
        # LD-715's QA bounce: each line the first widening missed, as it stood
        "entry). A green call proved nothing and the read-back was yours. **Two separate integrations\n"
        "  walked through it in one review round, and one of them fired an unproven field mask",
        "one string, and eight independent consumer-review runs recorded the same two-sided defect",
        "while the thing they called the best onboarding surface",
        "item's own text and the nested child's id / text / state untouched. Two consumers had\n"
        "    independently reached this spelling by source-diving, one of them firing an **unproven**",
        "#: about a *public* method, to disclose the price of walking through a door two consumers had\n"
        "#: already walked through blind.",
        "because those are the two things two separate\n#: consumers reached off-road for in one review round",
        "in search results — reported to this project, **not measured by it**.)",
        # the re-sweep with the wider guard
        "a symbol reachable only by knowing that is the discoverability failure a consumer already\n"
        "# reported once",
        "shape, and the consumer's own 6 × 36 = 216-cell table **measured 1 call / 0.82 s** on it",
        "The consumer's own cheapest good idea, and the one this issue could grant outright",
        "Two different consumers reach this branch",
        "the difference between a refusal a caller acts on and one that sends them source-diving",
        # LD-715's second QA bounce: the same story with a subject other than a consumer
        "for a long time nothing in the shipped documentation said so per type. A caller wrote\n"
        "``[\"recvra1g7Vj6RQ\"]`` into a link cell, read back ``{\"link_record_ids\": [...]}``, and met the",
        "#:   the founding incident for packaging these documents in the wheel at all",
        "#:   the six-release reader was burned by a wheel that carried NO notes at all, and this",
        "#:   so that incident's reader is served by the root copy.",
        "  - **The exact migration action — and both of the things people actually reached for now have",
        "- **The write-recipe router — the table you read before choosing how to write — gained the two\n"
        "  rows people kept arriving for, and lost a claim that was not true.**",
        "**So there is no \"escape hatch\" row to reach for, and the two things people reached for it are",
        "**Every value form above was measured or is labelled as reported, never guessed.**",
        "one user said it was the best onboarding surface",
        "an agent lost a day to the missing mask",
    ):
        assert narrative(plant), plant
    for generic in (
        "``preflight`` is the one surface a consumer runs before writing",
        "distinct from bitable (18), which consumers hit interchangeably",
        "nothing a consumer installs or runs",
        "the consumer kit's refresh script",
        "because a consumer agent reading a bare reason has nothing to act on",
        "the capability consumers ask for most",
        "a `consumer-observed` half is a shape observed working outside this project",
        "silences a diagnostic the consumer never asked to have silenced",
        "what costs a consumer a round of trial-and-error",
        "the task in the consumer's own words, the module that performs it",
        "It is stated in the consumer's own document because the reader of a shape table",
        "without larkdocio knowing the consumer's own ids",
        "every marker-shaped line instead would delete a consumer's own writing about markers",
        "an integration test that reaches the server",
        "two calls, one per route, and the review of a plan before it applies",
        "Two different callers reach this branch",
        # the second QA's two false positives, and the API's own use of the wider subjects
        "two consumers of the same Base see the same rows",
        "a consumer reached this branch only by passing dry_run",
        "its pending edits and additions carry the values the caller wrote, before any encoding",
        "**The body carries what the caller asked for, and nothing else.**",
        "so nothing a reader met said that a library-level url-to-Markdown entry point existed",
        "so anything the reader wrote, `compose` turns back into the same content",
        "a user session is the identity the call runs as",
        "The pre-LD-146 reader ran the fence body through the inline escaper",
    ):
        assert not narrative(generic), generic


def test_no_report_narrative_in_the_consumer_facing_corpus():
    offenders = [f"{rel}:{line}: [{name}] {matched!r}"
                 for rel, text in _corpus() for line, name, matched in narrative(text)]
    assert not offenders, (
        "the exported text tells a fix as a report story (LD-715): describe what changed instead"
        " — 'X now refuses Y'\n  " + "\n  ".join(offenders))
