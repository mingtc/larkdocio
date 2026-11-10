"""A private pattern set the maintainers keep, read from the private ledger (LD-704, LD-705, LD-707).

`D-121` (8): larkdocio contains no domain-specific items. A guard that keeps a pattern out of the
public tree has to be able to say it, and a public guard that says it, or describes it, in any
readable form republishes it. So the pattern set is kept where :mod:`retired_particulars` keeps
its values, in the private ledger ``dev/public-export/retired-particulars.json`` (never
exported), and this module names its members opaquely. It holds only the mechanism, which is
safe to publish.

* **In the private repository** the ledger is present (:data:`AVAILABLE`): every name below is
  the real member and every guard that imports one runs at full strength, over exactly the files
  the export would carry.
* **In the public tree** the ledger is absent. Every member is then a pattern that matches
  nothing (:data:`NEVER`), so the arm of a guard built on it is inert there; the rest of that
  guard still runs. Every test that needs a member itself (one that plants it to prove a guard
  catches it, or one that walks the tree for it) carries ``@private_tree.dev_record`` and is
  skipped with that reason. The export is still checked: ``dev/public-export/scan.py`` holds
  the same set in its private deny-list.
"""
import bisect
import json
import re
from pathlib import Path

from guard_kit import REPO_ROOT

LEDGER = Path(REPO_ROOT) / "dev" / "public-export" / "retired-particulars.json"

#: A regular expression that matches nothing: what every pattern below is without the ledger.
NEVER = "(?!)"


#: A quoted string literal on one line (a prefix letter, then single or double quotes).
_LITERAL = re.compile(r"""(?<![A-Za-z0-9_])[rRbBuUfF]{0,2}(["'])((?:\\.|(?!\1).)*?)\1""")


def readable_forms(line):
    """The line as written, plus what its string literals spell once put back together: joined
    directly and with spaces, and each of those reversed. A term split into pieces
    (``"".join(("x", "y"))``) or written backwards is hidden from a plain search but not from a
    reader; this gives the plain search the reader's view."""
    pieces = [m.group(2) for m in _LITERAL.finditer(line)]
    forms = [line, line[::-1]]
    if len(pieces) > 1:
        for joined in ("".join(pieces), " ".join(pieces)):
            forms += [joined, joined[::-1]]
    return forms


#: What a reader skips at the start of a wrapped line: a comment or quote marker, a list bullet.
_MARKER = re.compile(r"^\s*(?:#+:?|//+|--+|;+|\*+|>+|%+|-(?=\s))?\s*")


def flattened(lines):
    """The lines as a reader takes them in: each one stripped of a leading comment, quote or list
    marker, every whitespace run collapsed to one space, and the lines joined by one space. Also
    the offset at which each line starts in the result, so a match maps back to its line."""
    parts, starts, offset = [], [], 0
    for line in lines:
        part = " ".join(_MARKER.sub("", line).split())
        starts.append(offset)
        parts.append(part)
        offset += len(part) + 1
    return " ".join(parts), starts


def line_hits(text, pattern):
    """``(line number, line)`` for every line in which ``pattern`` finds a readable form, and for
    the first line of a match a plain line search misses: one wrapped across a line break (also
    behind a comment marker on the next line) or split by a tab or a run of spaces."""
    lines = text.splitlines()
    hits = [(number, line) for number, line in enumerate(lines, 1)
            if any(pattern.search(form) for form in readable_forms(line))]
    seen = {number for number, _ in hits}
    flat, starts = flattened(lines)
    for match in pattern.finditer(flat):
        number = bisect.bisect_right(starts, match.start())
        if number not in seen:
            seen.add(number)
            hits.append((number, lines[number - 1]))
    return sorted(hits)


def _load():
    if not LEDGER.is_file():
        return None
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    return {key[len("retired_set_"):]: value for key, value in ledger.items()
            if key.startswith("retired_set_")}


_SET = _load()

#: Whether the private ledger was found (``False`` in the public tree).
AVAILABLE = _SET is not None


def _one(name):
    (value,) = _SET[name]
    return value


#: Everything the public tree must not carry, in any readable form (see :func:`line_hits`).
FORBIDDEN = re.compile(_one("pattern") if AVAILABLE else NEVER)

#: One member of the set as plain text, for a test that plants it; :data:`NEVER` without the
#: ledger.
RETIRED = _one("word") if AVAILABLE else NEVER

#: An id form, which the dialect guards also check.
RETIRED_ID = re.compile(_one("id") if AVAILABLE else NEVER)

#: A string :data:`RETIRED_ID` matches, for a probe; :data:`NEVER` without the ledger.
RETIRED_ID_EXAMPLE = _one("id_example") if AVAILABLE else NEVER

#: The self-test plants: lines :data:`FORBIDDEN` must catch, lines it must not, and
#: ``(file text, the line numbers a scan reports)`` pairs. Empty without the ledger.
MUST_MATCH = tuple(_SET["must_match"]) if AVAILABLE else ()
MUST_NOT_MATCH = tuple(_SET["must_not_match"]) if AVAILABLE else ()
FILE_PLANTS = tuple((text, lines) for text, lines in _SET["file_plants"]) if AVAILABLE else ()
