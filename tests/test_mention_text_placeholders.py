"""LD-703 (round 5 of the public-export review, V4) — a person named in a mention's text is from
the placeholder cast.

Round 5 found one ordinary first name, in the exact shape of a hand-added Sheets ``@mention``
(``"text": "@…"``), in a test fixture: the only personal name outside the placeholder cast. A
recorded mention's display text is a real person's name by construction, so a literal of that
shape is held to the cast here — in ``src/`` and ``tests/`` alike — rather than left to a reader.

The cast: a name that starts ``Example`` (``@Example User``, ``@Example Second User``), or one of
the few generic stand-ins below that name nobody.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: The mention texts that name nobody, each a test double's own wording.
_GENERIC = {"@nobody", "@x", "@Someone", "@By Token"}

_MENTION_TEXT = re.compile(r"""["']text["']\s*:\s*["'](@[^"'\n]*)["']""")


def mention_texts(text):
    return _MENTION_TEXT.findall(text)


def outside_the_cast(texts):
    return [t for t in texts if not t.startswith("@Example") and t not in _GENERIC]


def test_the_shape_is_read_in_both_quote_styles_and_held_to_the_cast():
    found = mention_texts('{"type": "mention", "text": "@Invented Person"} '
                          "{'text': '@Example User'}")
    assert found == ["@Invented Person", "@Example User"]
    assert outside_the_cast(found) == ["@Invented Person"]


def test_every_mention_text_literal_names_someone_from_the_placeholder_cast():
    offenders = []
    for root in ("src", "tests"):
        for path in sorted((REPO / root).rglob("*.py")):
            if path.name == Path(__file__).name:     # states the shape, so it carries it
                continue
            for name in outside_the_cast(mention_texts(path.read_text(encoding="utf-8"))):
                offenders.append(f"{path.relative_to(REPO).as_posix()}: {name}")
    assert offenders == []
