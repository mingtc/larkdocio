"""LD-700 (round 3 of the public-export review, T6/T7) — the consumer README, the root README
(the wheel's METADATA body) and the rendered ``--help`` agree with what ``capabilities()``
reports.

Round 3 found two denials of shipped capability in exactly these three texts: the consumer
README said *no comment write ships at all* while ``comment-create`` and ``comment-remove`` are
docx-write operations, and the README and ``--help`` said *hidden fields are not offered* while
``update_view`` sets them. Both are the same class as LD-474's front-door paragraph: a sentence
true-looking long after the registry moved. Each claim below is DERIVED from the registry (or
from the shipped signature the registry's operation calls), so the check moves when the
registry does; each denial pattern is the shape the rotted sentence took.
"""
import inspect
import re

import pytest

import consumer_text
import front_door as fd
import larkdocio
from larkdocio.base.view_client import BaseViewOps


def _flat(text):
    return re.sub(r"\s+", " ", text.replace("**", "").replace("`", "")).strip()


def _texts():
    out = {
        "consumers/README.md": (fd.REPO_ROOT / "consumers" / "README.md").read_text(encoding="utf-8"),
        "README.md": fd.readme_text(),
    }
    out.update(consumer_text.cli_help_pages())
    return {label: _flat(text) for label, text in out.items()}


def _operation_names(surface):
    return {op["name"] for op in larkdocio.capabilities(full=True)["surfaces"][surface]["operations"]}


def comment_write_ships():
    return any(name.startswith("comment-") for name in _operation_names("docx-write"))


def hidden_columns_ship():
    return ("update_view" in _operation_names("base-schema-write")
            and "hidden_fields" in inspect.signature(BaseViewOps.update_view).parameters)


#: ``(claim, does the registry report it?, denial patterns)``.
CLAIMS = (
    ("a comment write (create / remove on a docx)", comment_write_ships, (
        r"no comment write ships",
        r"comments? (?:are |is )?read only",
        r"comments read-only",
    )),
    ("hidden columns on a Base view", hidden_columns_ship, (
        r"hidden (?:fields|columns)[^.;]{0,60}\bnot offered",
        r"hidden (?:fields|columns)[^.;]{0,60}\b(?:is|are) not (?:settable|supported)",
    )),
)


@pytest.mark.parametrize("claim, reported, denials", CLAIMS, ids=[c[0] for c in CLAIMS])
def test_no_front_door_text_denies_what_the_registry_reports(claim, reported, denials):
    assert reported(), f"the registry no longer reports {claim}; re-derive this claim"
    offenders = []
    for label, text in _texts().items():
        for pattern in denials:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                offenders.append((label, text[max(0, match.start() - 60):match.end() + 20]))
    assert not offenders, offenders


def test_the_consumer_readme_names_the_comment_write_it_ships():
    text = _texts()["consumers/README.md"].lower()
    assert re.search(r"comments?[^.]{0,80}\bcreate\b[^.]{0,40}\bremove\b", text), (
        "the consumer README's family list must say what the comment surface writes")


def test_the_denial_patterns_bite_on_the_sentences_that_shipped():
    """Red on the literal round-3 text, so the patterns are proven on the real rot."""
    rotted = {
        "a comment write (create / remove on a docx)":
            "Comments READ only — a comment create is refused by Lark's own API on a document "
            "passage and on a Base, so no comment write ships at all",
        "hidden columns on a Base view":
            "Grouping, hidden fields and a view-level sort are not offered",
    }
    for claim, _reported, denials in CLAIMS:
        assert any(re.search(p, _flat(rotted[claim]), re.IGNORECASE) for p in denials), claim
