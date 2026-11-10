"""Prose normalization for the **content-level** documentation guards (LD-138).

**Why this exists.** The LD-132 lesson is that a doc guard keyed on an id, a heading or a
table cell is blind to the prose actually rotting — so several guards here assert on
*sentences*. But a literal ``"no merge can be authored" in text`` check is defeated by two
things that have nothing to do with truth:

* **line wrapping** — every shipped doc is hard-wrapped, so a required phrase is routinely
  split across a newline plus indentation;
* **markdown emphasis** — ``**no merge** can be authored`` carries the same claim as the
  unadorned sentence, and an author adding bold must not redden the suite.

Either one makes the guard fail on a *reflow*, and a guard that cries wolf gets weakened
until it guards nothing. :func:`prose` removes both variables: emphasis markers and
backticks are dropped, all whitespace collapses to single spaces, and the text is
lower-cased — so a phrase assertion is about the words and only the words.
"""
import re

#: Markdown emphasis / code markers that never change the meaning of a sentence.
_MARKUP_RE = re.compile(r"[*_`]+")
_WS_RE = re.compile(r"\s+")


def prose(text: str) -> str:
    """``text`` reduced to comparable words: no emphasis markers, single spaces, lower-case.

    >>> prose("while **no merge can be\\n  authored**, a cell edits")
    'while no merge can be authored, a cell edits'
    """
    return _WS_RE.sub(" ", _MARKUP_RE.sub("", text)).strip().lower()


def missing_phrases(text: str, phrases) -> list:
    """The ``phrases`` absent from :func:`prose`-normalized ``text``, in the given order.

    Returned rather than asserted so a caller can name *which* claim went missing (and so
    the same function can be used to prove a guard bites — the red-then-green discipline).
    """
    normalized = prose(text)
    return [p for p in phrases if prose(p) not in normalized]
