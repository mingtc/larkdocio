"""Values the public tree must not carry, read from a private record at run time (LD-700).

**Superseded in part (LD-700 QA fix round; supersession.md § A.1).** The REASON is unchanged: a
guard written as a literal list re-publishes the very values it keeps out. The first CONCLUSION
— hold them as unsalted digests in the public tests — was wrong for a value from a small space,
which a digest does not protect. No digest is kept: the values live in
``dev/public-export/retired-particulars.json`` (private, never exported), and every test that
reads it is ``@private_tree.dev_record`` — it runs here and is skipped, with its reason, in the
public export.
"""
import json
import re
from pathlib import Path

from guard_kit import REPO_ROOT

LEDGER = Path(REPO_ROOT) / "dev" / "public-export" / "retired-particulars.json"

#: A word, after case-folding: the unit :func:`phrase_hits` compares.
_WORDS = re.compile(r"[0-9a-z]+")


def load(group):
    """The list stored under ``group`` in the private ledger."""
    values = json.loads(LEDGER.read_text(encoding="utf-8"))[group]
    assert values, f"the private ledger's {group!r} list is empty"
    return values


def value_hits(text, values):
    """Every value occurring in ``text``, case-insensitively."""
    folded = text.casefold()
    return [value for value in values if value.casefold() in folded]


def phrase_hits(text, phrases):
    """Every phrase occurring in ``text`` as consecutive words, however they are separated or
    cased (``Some Words``, ``some_words`` and ``some-words`` are one phrase)."""
    joined = "_" + "_".join(_WORDS.findall(text.casefold())) + "_"
    return [p for p in phrases if "_" + "_".join(_WORDS.findall(p.casefold())) + "_" in joined]
