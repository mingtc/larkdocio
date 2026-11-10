"""Structural guards on requirements/DECISIONS.md's own D-id headings — LD-413.

**Provenance.** LD-398 found a shipped **duplicate `### D-56`** heading (LD-396's entry
collided with LD-379's) and recorded, verbatim, in its Activity log: *"No guard exists on
D-NN uniqueness (finding, not built)."* LD-398 fixed the duplicate by hand; this module is
the guard it named but did not build. Maintainer approved building it 2026-08-11 as an early-finish
from the downtime queue.

**What this guard asserts:**
  * AC1 — every ``### D-<digits>`` heading id is unique across the file. The failure message
    names the duplicated id and the line numbers of every heading that carries it.
  * AC2 — every such heading is well-formed: ``### D-<digits> — <title>`` with a non-empty
    title (em dash ``—``, verified against the real file, not assumed).
  * AC5 — the parse found a plausible number of ids, so a regex that silently matches
    nothing cannot pass vacuously.

**What this guard deliberately does NOT assert, and why (AC3):**
  * **(i) Order.** The register is filed **by theme, not by number** — e.g. ``D-59`` sits
    inside § E between ``D-24`` and ``D-25``; ``D-62``/``D-63`` sit above ``D-09``;
    ``D-56``/``D-57`` sit above ``D-48``. A monotonic-order assertion would either redden
    today or force a reshuffle that destroys the thematic grouping — deliberately not built.
  * **(ii) Gap-freeness.** An id must be retirable (per the register's own "ids are stable,
    never reused" rule) without the guard reddening — so no assertion that ids form a
    contiguous run.

AC4's deliberate-defect proof lives below, in its own section: it feeds ``parse_d_headings``
synthetic text carrying a duplicate id and a malformed heading, and asserts the guard reddens
on each — the parsing is factored to take a string precisely so this is possible.
"""
import re

import pytest

from guard_kit import REPO_ROOT
import private_tree  # noqa: E402  (LD-685)

DECISIONS_MD = REPO_ROOT / "requirements" / "DECISIONS.md"

#: The register's own well-formed heading shape, verified against the real file at
#: implementation time (LD-413): every ``### D-`` heading is ``### D-<digits> — <title>``
#: with an em dash (``—``, U+2014) separator and a non-empty title. ``\d{2,}`` (not ``\d+``)
#: matches the register's own zero-padding (``D-01``..``D-63`` today) while still accepting
#: a future three-digit id without a guard change.
_HEADING_RE = re.compile(r"^###\s+D-(\d{2,})\s+—\s+(.*)$")

#: Any line that OPENS like a D-heading (``### D-...``) regardless of whether it matches the
#: well-formed shape above — used only to classify a heading that fails ``_HEADING_RE`` as
#: "malformed" rather than "not a D-heading at all" (a plain prose line mentioning ``D-NN``
#: never starts with ``### `` and so never reaches this check — see the module docstring's
#: "false positive" concern, ruled out by grep at implementation time).
_HEADING_START_RE = re.compile(r"^###\s+D-")

#: AC5's anti-vacuity floor. The register's own header records 60 headings at mint (max id
#: D-60); the count only grows from further rulings landing. Set comfortably below that so
#: the floor itself never needs bumping, while still catching the failure mode this AC
#: exists for: a rename, a heading-level change, or an encoding change that silently makes
#: the regex match zero headings.
_MIN_EXPECTED_HEADINGS = 50


def parse_d_headings(text):
    """Return ``(ok_headings, malformed_lines)`` for ``text``.

    ``ok_headings`` is a list of ``(id: int, title: str, line_no: int)`` for every line
    matching the register's well-formed heading shape. ``malformed_lines`` is a list of
    ``(line_no, raw_line)`` for every line that opens like a D-heading but does not match
    that shape (e.g. an empty title).

    Takes a string, not the file, so the deliberate-defect tests below (LD-413 AC4) can feed
    synthetic text without touching the real register.
    """
    ok, malformed = [], []
    for line_no, line in enumerate(text.splitlines(), start=1):
        m = _HEADING_RE.match(line)
        if m and m.group(2).strip():
            ok.append((int(m.group(1)), m.group(2).strip(), line_no))
        elif _HEADING_START_RE.match(line):
            malformed.append((line_no, line))
    return ok, malformed


def _duplicate_ids(ok_headings):
    """``{id: [line_no, ...]}`` for every id whose heading appears more than once."""
    by_id = {}
    for id_, _title, line_no in ok_headings:
        by_id.setdefault(id_, []).append(line_no)
    return {id_: lines for id_, lines in by_id.items() if len(lines) > 1}


def _join_and(items):
    """``["a"]`` -> ``"a"``, ``["a", "b"]`` -> ``"a and b"``, 3+ -> Oxford-comma list."""
    items = [str(i) for i in items]
    if len(items) < 2:
        return items[0] if items else ""
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


@pytest.fixture(scope="module")
def decisions_text():
    return DECISIONS_MD.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# AC1 — every D-id heading is unique                                          #
# --------------------------------------------------------------------------- #

@private_tree.register
def test_every_d_id_heading_is_unique(decisions_text):
    ok, _malformed = parse_d_headings(decisions_text)
    dups = _duplicate_ids(ok)
    assert not dups, "duplicate D-id heading(s) in requirements/DECISIONS.md: " + "; ".join(
        f"D-{id_:02d} appears at lines {_join_and(lines)}"
        for id_, lines in sorted(dups.items())
    )


# --------------------------------------------------------------------------- #
# AC2 — every D-id heading is well-formed                                     #
# --------------------------------------------------------------------------- #

@private_tree.citations
def test_every_d_id_heading_is_well_formed(decisions_text):
    _ok, malformed = parse_d_headings(decisions_text)
    assert not malformed, (
        "malformed D-heading(s) in requirements/DECISIONS.md (expected "
        "`### D-<digits> — <non-empty title>`): " + "; ".join(
            f"line {line_no}: {raw!r}" for line_no, raw in malformed
        )
    )


# --------------------------------------------------------------------------- #
# AC5 — the guard cannot pass vacuously                                       #
# --------------------------------------------------------------------------- #

@private_tree.citations
def test_the_guard_found_a_plausible_number_of_headings(decisions_text):
    ok, _malformed = parse_d_headings(decisions_text)
    assert len(ok) >= _MIN_EXPECTED_HEADINGS, (
        f"parsed only {len(ok)} D-headings from requirements/DECISIONS.md; the floor is "
        f"{_MIN_EXPECTED_HEADINGS} — a regex matching zero (or near-zero) headings is this "
        "guard's own quiet-death mode (a rename, a heading-level change, an encoding change) "
        "and must be reported as a failure, never mistaken for a clean file"
    )


# --------------------------------------------------------------------------- #
# AC4 — the deliberate-defect proof that the guard actually BITES              #
# --------------------------------------------------------------------------- #

_SYNTHETIC_DUP = """\
### D-01 — First ruling

Body text.

### D-02 — Second ruling

Body text.

### D-01 — Reused id by accident

Body text.
"""


def test_DEFECT_a_duplicate_id_is_found_at_both_line_numbers():
    ok, _malformed = parse_d_headings(_SYNTHETIC_DUP)
    by_id = {}
    for id_, _title, line_no in ok:
        by_id.setdefault(id_, []).append(line_no)
    assert by_id.get(1) == [1, 9], by_id


_SYNTHETIC_MALFORMED = """\
### D-01 — Well-formed ruling

Body text.

### D-02 —

Body text with an empty title.
"""


def test_DEFECT_a_malformed_heading_is_flagged():
    ok, malformed = parse_d_headings(_SYNTHETIC_MALFORMED)
    assert [id_ for id_, _t, _l in ok] == [1]
    assert malformed and malformed[0][0] == 5


# --------------------------------------------------------------------------- #
# LD-451 — D-78's Provenance names the guard file that actually carries the   #
# "THE FOURTH DIRECTION" section it cites, not a stale sibling file           #
# --------------------------------------------------------------------------- #

#: The Provenance sentence's own shape: a backtick-quoted guard filename directly
#: followed by ``§ "THE FOURTH DIRECTION"``. Deliberately narrow (not a general
#: "every tests/ path mentioned exists" sweep) — this guards the one cross-reference
#: LD-451 found stale, the same way it was found: by resolving the pointer.
_FOURTH_DIRECTION_PROVENANCE_RE = re.compile(
    r"`(tests/test_[A-Za-z0-9_]+\.py)`\s*§\s*\"THE FOURTH DIRECTION\""
)


@private_tree.citations
def test_d78_fourth_direction_provenance_names_a_file_that_carries_the_section(decisions_text):
    m = _FOURTH_DIRECTION_PROVENANCE_RE.search(decisions_text)
    assert m, (
        'D-78\'s Provenance no longer cites a guard as `tests/test_....py` § "THE FOURTH '
        'DIRECTION" — update this guard\'s regex alongside the register text.'
    )
    cited_path = REPO_ROOT / m.group(1)
    assert cited_path.is_file(), (
        f"D-78's Provenance cites {m.group(1)!r}, which does not exist"
    )
    assert "FOURTH DIRECTION" in cited_path.read_text(encoding="utf-8"), (
        f"D-78's Provenance cites {m.group(1)!r}, but that file carries no "
        '"FOURTH DIRECTION" section — the pointer is stale (LD-451).'
    )
