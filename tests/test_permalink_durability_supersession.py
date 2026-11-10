"""THE PERMALINK CROSS-WEEK DURABILITY SUPERSESSION — the claim, its scope, and the census.

Why this file exists
--------------------
The shipped ``record_permalink`` surface said, in two places, that **cross-week durability had
not yet been measured** and therefore claimed no permanence. That was true when it was written
and it stopped being true on **2026-08-15**, when the same three record permalinks were
re-fetched **through the shipped read route** at seven and eight days and came back
**byte-identical**, alongside two attachment permalinks at three days — five links, five
identical, zero drift.

This is a **supersession, not a deletion** (``process/doctrine/supersession.md`` § A.1): the
2026-08-07/08 same-day reading stays on the record **with its date**, only the conclusion moves,
and the guard rows that pinned the old sentence are **transformed** in
``tests/test_absence_claims_guard.py`` rather than struck. What this file holds is the other
half: that the **new** sentence carries its own scope on its face, that it keeps the ceiling the
measurement itself set, and that **no copy of the superseded claim survives anywhere in the
shipped corpus**.

The census reads BOTH ways, and that is the point
-------------------------------------------------
A source-text grep and a value-level grep each miss what the other catches:

* a claim split across two **adjacent string literals** is invisible to a naive source grep —
  the quotes and the newline sit inside the phrase — but the parser folds it into one runtime
  value, so the value pass sees it;
* a claim in a Markdown file, a ``#`` comment, or any text that never becomes a runtime string
  is invisible to the value pass, and only the source pass sees it.

So :func:`census_corpus` builds both, and :func:`census_hits` reads the union. The two release
documents are **excluded as dated records** — a release note that said "not yet measured" was
true of its release — and that exclusion is asserted by its own test, so it cannot quietly
become the place a live claim hides.
"""
import ast
import pathlib
import re

import pytest

import larkdocio
from larkdocio.base.permalink import PERMALINK_RESOLVED, STATE_MEANINGS


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src" / "larkdocio"

#: The root capability matrices and the front door — shipped text a consumer reads, held to the
#: same standard as the wheel's own files.
ROOT_MATRICES = (
    "BLOCKS.md", "SHEETS.md", "BASE.md", "DRIVE.md", "PERMISSIONS.md", "README.md",
)

#: The two release documents, root and packaged: **dated, append-only records.** A sentence
#: under a shipped version heading is history, and history is not edited — the same reasoning
#: ``tests/test_absence_claims_guard.py``'s ``DATED_RECORD_SURFACES`` runs on. The exclusion is
#: exactly these four paths and is asserted below, so it cannot widen into a hiding place.
DATED_RECORD_FILES = frozenset({
    REPO_ROOT / "CHANGELOG.md",
    REPO_ROOT / "RELEASE_NOTES.md",
    SRC / "CHANGELOG.md",
    SRC / "RELEASE_NOTES.md",
})

TEXT_SUFFIXES = frozenset({".py", ".md", ".json"})


def flatten(text):
    """Collapse every whitespace run to one space — a claim that wraps a line is one claim."""
    return " ".join((text or "").split())


#: The **superseded** claim, in the shapes it could survive as. Every pattern is anchored on
#: *cross-week* — the thing that was measured — so an honestly scoped disclosure about what is
#: still unmeasured (past a week, another tenant, a deleted record) is not caught. The claim
#: this issue supersedes is precisely *"cross-week durability is unmeasured"*, and nothing more.
_UNMEASURED = r"(?:unmeasured|not\s+(?:yet\s+)?(?:been\s+)?measured|no\s+claim\s+of\s+permanence|no\s+permanence\s+is\s+claimed)"
SUPERSEDED_CLAIM_PATTERNS = (
    ("cross-week-then-unmeasured",
     re.compile(r"cross[-\s]?week[^.]{0,140}?" + _UNMEASURED, re.IGNORECASE)),
    ("unmeasured-then-cross-week",
     re.compile(_UNMEASURED + r"[^.]{0,140}?cross[-\s]?week", re.IGNORECASE)),
)


def _text_files():
    """Every text file the census reads, in sorted order — the whole shipped corpus minus the
    dated release records."""
    files = [
        path for path in sorted(SRC.rglob("*"))
        if path.is_file() and path.suffix in TEXT_SUFFIXES and "__pycache__" not in path.parts
    ]
    files += [REPO_ROOT / name for name in ROOT_MATRICES]
    return [path for path in files if path not in DATED_RECORD_FILES]


def _joined_strings(node):
    """The concatenation a **runtime** value would be, for one expression node.

    ``ast`` already folds *adjacent* literals into a single ``Constant`` — which is exactly the
    blind spot of a source grep — and this walks ``+`` chains on top of that, so a claim spelled
    ``"cross-week durability " + "has not been measured"`` is one string here too.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _joined_strings(node.left)
        right = _joined_strings(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def runtime_values(source, label):
    """``{label: value}`` for every string value a module would hold at runtime."""
    values = {}
    try:
        tree = ast.parse(source)
    except SyntaxError:  # pragma: no cover - a syntax error is another test's failure
        return values
    for index, node in enumerate(ast.walk(tree)):
        text = _joined_strings(node)
        if text:
            values[f"{label} [value @line {getattr(node, 'lineno', 0)}#{index}]"] = text
    return values


def census_corpus():
    """``{label: text}`` — the source pass and the value pass, together."""
    corpus = {}
    for path in _text_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        corpus[f"{rel} [source]"] = source
        if path.suffix == ".py":
            corpus.update(runtime_values(source, rel))
    return corpus


def census_hits(corpus):
    """``[(label, pattern_name, matched)]`` — every surviving copy of the superseded claim."""
    hits = []
    for label, text in corpus.items():
        flat = flatten(text)
        for name, pattern in SUPERSEDED_CLAIM_PATTERNS:
            for match in pattern.finditer(flat):
                hits.append((label, name, match.group(0)))
    return sorted(hits)


# --------------------------------------------------------------------------- #
# 1. THE CLAIM ITSELF — measured, and scoped on its face.                       #
# --------------------------------------------------------------------------- #

_RESOLVED = STATE_MEANINGS[PERMALINK_RESOLVED]

#: A permanence word used as a claim about the address. ``permanence`` in *"no permanence is
#: claimed"* is the ceiling, not the claim, and is deliberately not in this set.
_PERMANENCE_WORDS = re.compile(r"\bpermanent(?:ly)?\b|\bforever\b", re.IGNORECASE)


def test_the_resolved_meaning_NO_LONGER_says_the_measurement_is_owed():
    """The defect, gone: the sentence a consumer reads no longer says it is unmeasured."""
    assert "not yet measured" not in _RESOLVED
    assert not census_hits({"STATE_MEANINGS[PERMALINK_RESOLVED]": _RESOLVED})


def test_the_resolved_meaning_carries_its_SCOPE_on_its_face():
    """The measurement without its scope is a bigger claim than the evidence: the date, the one
    tenant, the route it was read on, and the records being intact are all part of the fact."""
    missing = [
        element for element, present in (
            ("the date of the measurement (2026-08-15)", "2026-08-15" in _RESOLVED),
            ("one tenant", "one tenant" in _RESOLVED),
            ("the route (record_permalink / records/batch_get)",
             "record_permalink" in _RESOLVED and "records/batch_get" in _RESOLVED),
            ("the records were intact for the duration",
             re.search(r"records intact", _RESOLVED) is not None),
        ) if not present
    ]
    assert not missing, f"the claim ships without its scope: {missing}\n{_RESOLVED}"


def test_the_resolved_meaning_claims_DURABILITY_not_PERMANENCE():
    """The ceiling the measurement set for itself: *measured durable at week scale*, never
    *permanent*. A week of evidence does not license a forever word."""
    assert not _PERMANENCE_WORDS.search(_RESOLVED), _RESOLVED
    assert "durable at week scale" in _RESOLVED


def test_BOTH_dated_readings_survive_so_the_supersession_is_LEGIBLE():
    """§ A.1 applied literally: only the conclusion moved. The same-day/cross-session reading
    stays on the record with its date beside the cross-week one, so a reader can see what was
    known when instead of meeting a silently rewritten sentence."""
    assert "2026-08-07/08" in _RESOLVED, "the earlier reading lost its date"
    assert "across sessions on the same day" in _RESOLVED
    assert "2026-08-15" in _RESOLVED


def test_the_HONEST_CEILING_ships_with_the_claim():
    """Two limits, both reachable from shipped text: durable is not permanent, and a durable
    address is not a promise the bytes behind it are still fetchable (attachment permalinks
    stayed byte-identical while a download of their bytes answered 404)."""
    guide = larkdocio.guide(full=True)
    for surface, text in (("the state meaning", _RESOLVED), ("the guide", guide)):
        flat = flatten(text)
        assert re.search(r"no permanence is claimed|no claim of permanence", flat), surface
        assert "404" in flat, f"{surface}: the link-outlives-the-bytes limit is not reachable"


# --------------------------------------------------------------------------- #
# 2. THE GUIDE PROJECTION — it moves in the same change.                        #
# --------------------------------------------------------------------------- #

def test_the_PACKAGED_GUIDE_no_longer_carries_the_superseded_sentence():
    """The front-door half: the guide is shipped consumer text, so it is corrected here, not in
    a later sweep."""
    flat = flatten(larkdocio.guide(full=True))
    assert "Cross-week durability has not yet been measured" not in flat
    assert "2026-08-15" in flat
    assert "is not yet measured, so this still makes no claim of permanence" in flat


# --------------------------------------------------------------------------- #
# 3. THE CENSUS — over the shipped corpus, read both ways.                      #
# --------------------------------------------------------------------------- #

def test_NO_copy_of_the_superseded_claim_survives_in_the_shipped_corpus():
    """The sweep, as a standing guard rather than a one-off grep. It ships even at zero
    survivors: its value is that it reddens on the *next* one."""
    hits = census_hits(census_corpus())
    assert not hits, "the superseded claim still ships:\n  " + "\n  ".join(
        f"{label} [{name}]: {matched!r}" for label, name, matched in hits)


def test_the_census_reads_BOTH_the_source_text_AND_the_runtime_values():
    """The lesson that cost two reviews: each pass is blind to what the other catches. A claim
    split across adjacent literals is one value and two source fragments; a claim in Markdown is
    source text and never a value. Both blind spots are proven here on synthetic input."""
    split_across_literals = (
        '"""a docstring"""\n'
        'NOTE = (\n'
        '    "cross-week durability "  # first read 2026-08-08. Re-probe owed.\n'
        '    "has not yet been measured"\n'
        ')\n'
    )
    assert not census_hits({"src.py [source]": split_across_literals}), (
        "the synthetic split claim must be invisible to the SOURCE pass, or this proves nothing")
    assert census_hits(runtime_values(split_across_literals, "src.py")), (
        "the VALUE pass must catch a claim split across adjacent literals")

    markdown_only = "Cross-week durability has not yet been measured, so nothing is claimed."
    assert census_hits({"GUIDE.md [source]": markdown_only}), (
        "the SOURCE pass must catch a claim in text that never becomes a runtime value")


def test_an_HONESTLY_SCOPED_disclosure_is_NOT_caught_by_the_census():
    """Calibration. The census hunts the *superseded* claim — cross-week durability being
    unmeasured — not the honest scoping the doctrine prescribes for what is still unknown. A
    census that reddened on the ceiling would be deleted within a month."""
    honest = (
        "durability past that week, on another tenant, or for a record somebody deletes is not "
        "yet measured, so this still makes no claim of permanence"
    )
    assert not census_hits({"guide [source]": honest}), census_hits({"guide [source]": honest})


def test_the_DATED_RECORD_exclusion_is_EXACTLY_the_two_release_documents():
    """The exclusion is reasoned, bounded and asserted — never a hiding place. Exactly four
    paths (two documents, root and packaged), each of which really is a dated append-only
    record, and **every other** text file in the shipped corpus is read."""
    assert len(DATED_RECORD_FILES) == 4
    for path in DATED_RECORD_FILES:
        assert path.is_file(), path
        assert re.search(r"^## \[\d+\.\d+\.\d+\] — \d{4}-\d{2}-\d{2}",
                         path.read_text(encoding="utf-8"), re.MULTILINE), (
            f"{path} is excluded as a DATED record but carries no dated release heading")

    everything = {
        path for path in SRC.rglob("*")
        if path.is_file() and path.suffix in TEXT_SUFFIXES and "__pycache__" not in path.parts
    } | {REPO_ROOT / name for name in ROOT_MATRICES}
    assert set(_text_files()) == everything - DATED_RECORD_FILES, (
        "the census skipped a file that is not one of the two dated release documents")
    assert (SRC / "GUIDE.md") in set(_text_files())
    assert (SRC / "base" / "permalink.py") in set(_text_files())


@pytest.mark.parametrize("survivor", [
    "Cross-week durability has not yet been measured",
    "cross-week durability is not yet measured, so no permanence is claimed",
    "the cross week case remains unmeasured",
    "unmeasured, and it is the cross-week case that is owed",
])
def test_the_census_BITES_on_every_shape_of_the_superseded_claim(survivor):
    """Deliberate defect, four spellings. A census only worth shipping is one proven to redden."""
    assert census_hits({"scratch [source]": survivor}), survivor
