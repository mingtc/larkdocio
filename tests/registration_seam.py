"""LD-633 — the registration-seam claim scanner, **generalised over the package it walks**.

**Why this module exists.** ``tests/test_sheets_registration_seam.py`` (LD-213) is this
project's proven guard for one defect class: *the registry grew and the prose describing it
did not*. Its scan walked exactly one corpus — *"every module under
``src/larkdocio/sheets/``"* — and ``write/`` has the **identical** registration seam
(``larkdocio.write.ops.OPS``, one descriptor per op, four generic dispatch chains reading off
it) and was scanned by **nothing**. The write-side sentence had been understated by three
across two op additions for 35 days (`comment-create` / `comment-remove` LD-202, `grow-table`
LD-575, against a docstring last touched 2026-07-28).

So the deliverable of LD-633 is not a corrected sentence — a sentence re-creates the defect at
the next op addition. It is this: the scan takes its **corpus, its claim shape and its
declared basis as parameters**, and both packages are enrolled.

**What a caller supplies** — one :class:`Seam`:

* ``source_dir`` — the package tree whose ``*.py`` source text is scanned (source text, not
  imported docstrings, so a hand-typed count cannot land in a comment either);
* ``noun_re`` — the population noun the claims are *about* (``famil(y|ies)`` for sheets, the
  apply-path nouns for write). The count words are shared: ``test_discovery_truth._COUNT_WORDS``
  is the ONE table, and this module reads it rather than starting a second one;
* ``is_arity_claim`` — the **discriminator**: given a found claim, is it a claim about the whole
  population's arity, or about some other population / some subset? This is where a guard
  either earns its keep or starts crying wolf, and each package answers it differently (sheets
  by the qualifier word — ``two payload families`` is not an op-family claim; write by the
  whole modifier phrase — ``the three single-re-validation write paths`` is a true statement
  about a *subset* and must never bite);
* ``listed_after`` — optionally, how to read the enumeration that follows the noun, so a guard
  can hold a prose list complete against the registry as well as the count.

**What it deliberately does NOT own.** The per-package *registers* (which docstrings must carry
the claim, which claims are registered history) and the violation report stay in each package's
own guard module: they are that package's policy, they are read by its own tests, and one
shared "violations" function over two different list shapes would be the abstraction that has
to be un-abstracted at the third caller.
"""
import importlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from test_discovery_truth import _COUNT_WORDS, count_word

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Arities worth scanning for. ``zero``/``one`` are excluded deliberately (LD-213's reason,
#: unchanged): "one family" is ordinary English about a single member, never an arity claim,
#: and matching it would make the guard cry wolf on prose it has no business reading.
SCANNED_COUNTS = {w: n for w, n in _COUNT_WORDS.items() if n >= 2}

#: One prose word, possibly wearing a ``**bold**`` marker.
_WORD = r"\*{0,2}[A-Za-z][A-Za-z-]*\*{0,2}"


def claim_regex(noun_re: str) -> "re.Pattern":
    """A claim: a count WORD (optionally bold), then at most two words, then the population
    noun. The words between are the **modifier phrase**, and it is what each seam's
    discriminator judges — so an out-of-scope population is ruled out *structurally* rather
    than allowlisted by site."""
    return re.compile(
        r"\*{0,2}\b(?P<count>" + "|".join(sorted(SCANNED_COUNTS, key=len, reverse=True)) +
        r")\b\*{0,2}\s+(?P<mods>(?:" + _WORD + r"\s+){0,2})(?P<noun>" + noun_re + r")",
        re.IGNORECASE,
    )


class Claim:
    """One arity claim found in a tree: where it is, what it says, what it lists."""

    def __init__(self, path: str, line: int, word: str, mods: str, noun: str, text: str,
                 sentence: str, listed):
        self.path = path
        self.line = line
        self.word = word
        self.mods = " ".join(w.strip("*") for w in mods.split())
        self.noun = " ".join(noun.split())
        self.text = text
        self.sentence = sentence
        self.listed = listed

    @property
    def stated(self) -> int:
        return count_word(self.word)

    @property
    def qualifier(self) -> Optional[str]:
        """The word immediately before the noun — ``None`` when the count qualifies the noun
        directly ("six families")."""
        words = self.mods.split()
        return words[-1] if words else None

    @property
    def site(self) -> str:
        return f"{self.path}:{self.line}"

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"<claim {self.site} {self.text!r}>"


@dataclass(frozen=True)
class Seam:
    """One package's registration seam, as the scanner needs it."""

    #: The dotted package name, for messages.
    package: str
    #: The tree whose ``*.py`` source text is scanned.
    source_dir: Path
    #: The population noun the claims are about (a regex fragment).
    noun_re: str
    #: The discriminator — is this found claim about the whole population's arity?
    is_arity_claim: Callable[[Claim], bool]
    #: What the population is called in a violation message ("request families").
    population: str
    #: How to read the enumeration following the noun, if this seam holds lists too.
    listed_after: Optional[Callable[[str, int], Optional[List[str]]]] = None

    @property
    def regex(self):
        return claim_regex(self.noun_re)


def _sentence_around(text: str, pos: int) -> str:
    start = max(text.rfind(". ", 0, pos), text.rfind(".\n", 0, pos)) + 1
    end_candidates = [e for e in (text.find(". ", pos), text.find(".\n", pos)) if e != -1]
    end = min(end_candidates) if end_candidates else len(text)
    return " ".join(text[start:end].split())


def claims_in(seam: Seam, text: str, path: str, line_offset: int = 1) -> List[Claim]:
    """Every arity claim in ``text`` (a source file or a single docstring)."""
    found = []
    for m in seam.regex.finditer(text):
        claim = Claim(
            path=path,
            line=line_offset + text.count("\n", 0, m.start()),
            word=m.group("count"),
            mods=m.group("mods"),
            noun=m.group("noun"),
            text=" ".join(m.group(0).split()),
            sentence=_sentence_around(text, m.start()),
            listed=(seam.listed_after(text, m.start("noun"))
                    if seam.listed_after is not None else None),
        )
        if not seam.is_arity_claim(claim):
            continue
        found.append(claim)
    return found


def scan_claims(seam: Seam) -> List[Claim]:
    """Every arity claim in the **source text** of the seam's package."""
    claims = []
    for path in sorted(seam.source_dir.rglob("*.py")):
        claims.extend(claims_in(seam, path.read_text(encoding="utf-8"),
                                path.relative_to(REPO_ROOT).as_posix()))
    return claims


def docstring(site: str) -> str:
    """The docstring of a registered site, addressed as ``module`` or ``module:attr.path``."""
    module, _, attrs = site.partition(":")
    obj = importlib.import_module(module)
    for attr in filter(None, attrs.split(".")):
        obj = getattr(obj, attr)
    doc = obj.__doc__
    assert doc, f"{site} has no docstring at all"
    return doc
