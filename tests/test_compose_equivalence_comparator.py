"""THE VERIFICATION COMPARATOR — compose-equivalence, not string equality
(LD-154 / dogfood F15, AC4).

**The defect.** An agent authors `- a\\n- b`, applies it, reads the document back, and
string-compares to check its own write. The reader emits **loose** lists (a blank line
between items), so the comparison fails — on **every list ever authored** — while nothing
whatsoever was lost. The agent's rational conclusion is "my write was mangled". It was not:
a blank line between list items is a **rendering** choice, and both forms carry the same two
bullets.

**The rule this pins.** Authored-vs-read-back verification compares the **content**, by
compiling both sides with ``compose()``, not the **strings**.

**DEV'S DOCUMENTED CALL — a recipe, not a helper.** AC4 offers either. This ships the
recipe, because ``compose()`` already returns a tuple of **frozen** ``NewBlock`` values, so
the comparator IS ``compose(a) == compose(b)`` — one expression, in the standard library's
own equality. A shipped ``compose_equivalent(a, b)`` helper would be a public symbol whose
entire body is ``==``: it adds surface without adding capability, and it would **hide the one
thing the consumer has to understand** (that the comparison happens in the *typed-content*
domain, not the string domain) behind a name that reads like a string utility. It would also
have to decide what to do when the read-back is **outside the dialect** — a pre-existing bold
run in the compared region — where a bool return can only lie; ``compose()``'s own typed
``not-in-dialect`` refusal names the construct **and its line**, which is the useful answer.
The equality is pinned as a property here (`test_compose_results_compare_by_value`) so the
recipe's one-liner cannot rot into a lie.

The corpus below is proven **through the reader itself** (the offline doc-double: the real
encoder → the block payloads Lark would hold → the real ``Parser`` + ``MarkdownRenderer``),
not against hand-written "read-back" strings. So each pair is the reader's *actual* emission,
which is the only version of the claim worth making.
"""
import pytest

import guide_recipes as gr
from compose_roundtrip import reader_markdown

import larkdocio
from larkdocio.write import compose

RECIPE_SLUG = "verify-what-you-authored-compose-equivalence-not-string-equality"


class Pair:
    """One authored fragment and why it is in the corpus."""

    def __init__(self, name, authored, *, why):
        self.name = name
        self.authored = authored
        self.why = why

    def __repr__(self):  # pragma: no cover - test ids only
        return self.name


#: The amplifier corpus: every list shape, plus a list next to a paragraph (where the
#: blank-line normalization could plausibly have swallowed a boundary).
CORPUS = (
    Pair("bullet-tight", "- a\n- b\n", why="THE reported case"),
    Pair("ordered-tight", "1. one\n2. two\n", why="ordered lists normalize the same way"),
    Pair("todo-tight", "- [ ] draft\n- [x] send\n", why="todo carries a checkbox too"),
    Pair(
        "nested-tight",
        "- parent\n    - child\n- sibling\n",
        why="nesting must survive the normalization, not be flattened",
    ),
    Pair(
        "list-adjacent-to-paragraph",
        "A paragraph.\n\n- a\n- b\n",
        why="the paragraph/list boundary is where a blank-line rule could eat content",
    ),
    Pair(
        "list-then-paragraph",
        "- a\n- b\n\nA trailing paragraph.\n",
        why="the other side of the same boundary",
    ),
)


def _reader_form(authored: str) -> str:
    """What the reader really emits for ``authored`` once it exists in a document."""
    return reader_markdown(compose(authored))


# --------------------------------------------------------------------------- #
# AC4 — string-DIFFERENT but compose-EQUAL, for the whole corpus.              #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("pair", CORPUS, ids=lambda p: p.name)
def test_authored_and_read_back_differ_as_STRINGS(pair):
    """The spurious diff, reproduced: a plain ``==`` (or ``in``) fails."""
    read_back = _reader_form(pair.authored)
    assert read_back != pair.authored, (
        f"{pair.name}: the reader's emission is already byte-identical to the authored "
        f"form, so this pair proves nothing about the comparator ({pair.why})"
    )
    assert pair.authored not in read_back, (
        f"{pair.name}: containment also has to fail, or an agent's `authored in read_back` "
        f"check would have worked and there would be no defect to document"
    )


@pytest.mark.parametrize("pair", CORPUS, ids=lambda p: p.name)
def test_authored_and_read_back_are_EQUAL_under_compose(pair):
    """The comparator that is true: same content, therefore nothing was lost."""
    read_back = _reader_form(pair.authored)
    assert compose(pair.authored) == compose(read_back), (
        f"{pair.name}: compose-equivalence failed, which would mean the round-trip really "
        f"did lose something — a far bigger problem than a comparator ({pair.why})"
    )


def _dense(text):
    """Non-blank lines only, with leading whitespace collapsed to its depth in tabs.

    Two normalizations, because there are two differences (see
    ``test_the_reader_writes_nesting_with_a_TAB``)."""
    out = []
    for line in text.splitlines():
        if not line.strip():
            continue
        stripped = line.lstrip(" \t")
        indent = line[: len(line) - len(stripped)]
        depth = indent.count("\t") + indent.count(" ") // 4
        out.append("\t" * depth + stripped)
    return out


@pytest.mark.parametrize("pair", CORPUS, ids=lambda p: p.name)
def test_the_whole_difference_is_blank_lines_plus_the_nesting_indent(pair):
    """Strengthens the claim from "equal content" to "and here is the ENTIRE difference":
    normalize away blank lines and the indent *style* and the strings themselves match.

    Without this, "compose-equal" could be hiding a real difference that ``compose()``
    happens to erase."""
    assert _dense(_reader_form(pair.authored)) == _dense(pair.authored)


def test_the_reader_writes_nesting_with_a_TAB():
    """A SECOND reason string comparison fails, found while building this corpus and not
    in the original report: the reader indents a nested list item with a **tab**, so an
    agent that authored four spaces sees that difference too.

    It matters for the guidance: the read-back is not merely "the same text with blank
    lines added", so a consumer cannot get away with stripping blank lines and comparing.
    Both indent styles are accepted on the way in (the dialect table says so), and both
    compose to the same nesting — which is exactly why the comparator has to be
    compose-equivalence rather than any amount of string massaging."""
    read_back = _reader_form("- parent\n    - child\n")
    assert "\t- child" in read_back
    assert "    - child" not in read_back
    assert compose("- parent\n    - child\n") == compose("- parent\n\t- child\n")


def test_compose_results_compare_by_value():
    """The property the recipe's one-liner rests on: ``compose()`` yields frozen values, so
    ``==`` compares CONTENT. If ``NewBlock`` ever grew identity equality, the shipped
    recipe would start silently answering ``False`` for equal content — this reddens first.
    """
    a, b = compose("- a\n- b\n"), compose("- a\n\n- b\n")
    assert a is not b
    assert a == b
    assert compose("- a\n") != compose("- b\n")           # and it still discriminates
    assert all(type(block).__dataclass_fields__ for block in a)


# --------------------------------------------------------------------------- #
# AC4 — the guidance SHIPS, and it EXECUTES in the recipe harness.             #
# --------------------------------------------------------------------------- #

def test_the_guide_states_the_comparator_rule():
    text = larkdocio.guide(full=True)
    flat = " ".join(text.split())
    assert "compose-equivalence" in flat, (
        "the guide never names the comparator, so a consumer has no term to look up")
    assert "not string equality" in flat, (
        "the guide must say what NOT to use — the defect is that string equality looks "
        "like the obvious check")
    assert "rendering" in flat


def test_the_comparator_recipe_exists_and_is_registered_for_execution():
    assert RECIPE_SLUG in gr.recipe_blocks(), (
        f"the guide has no {RECIPE_SLUG!r} recipe; recipes: {sorted(gr.recipe_blocks())}")
    assert RECIPE_SLUG in gr.SPEC_BY_SLUG, (
        f"{RECIPE_SLUG!r} has no execution spec, so it would ship unexecuted")


def test_the_comparator_recipe_runs_and_demonstrates_BOTH_sides(monkeypatch, tmp_path):
    """The load-bearing one: the shipped recipe is extracted VERBATIM and executed, and it
    must actually exhibit the trap **and** the fix against a real read-back of a document
    it really wrote to."""
    ns = gr.stage(monkeypatch, tmp_path).run(RECIPE_SLUG)
    gr.SPEC_BY_SLUG[RECIPE_SLUG].check(ns)
