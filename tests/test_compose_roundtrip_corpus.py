"""THE BINDING ROUND-TRIP PROPERTY for ``compose(markdown)``
(LD-136, decision **D4**).

The dialect ``compose()`` accepts is **exactly what our own reader emits**, so the
property is stated against the reader itself — offline, with an injected doc-double
(``tests/compose_roundtrip.py``: the **real** encoder → the block payloads Lark would hold
→ the **real** ``Parser`` + ``MarkdownRenderer``). For a corpus of fragments ``X``:

* **Tier A — canonical form.** For a fragment written the way the reader writes it,
  ``reader_markdown(compose(X)) == X`` **exactly**. This is the strongest form of the
  property and it is what pins the dialect to the reader.
* **Tier A′ — documented normalization.** For a fragment that is *not* in canonical form
  (a tight list, ``1)`` delimiters, a setext heading, CRLF, stray blank lines, a bare URL),
  the expected output is written out **verbatim in the corpus entry**, so every
  normalization this compiler performs is visible in one place and reviewable — nothing is
  hand-waved as "within lossiness".
* **Tier B — fixed point, for EVERY fragment.** ``reader_markdown(compose(·))`` applied to
  its own output is **idempotent**, so each normalization is provably a *normalization*
  and not a *corruption*: nothing keeps drifting, nothing is progressively lost.
* **Tier C — the same property over SEEDED GENERATED fragments** built from the construct
  grammar (``random.Random`` with a fixed seed — deterministic, no network, no clock).

Corpus provenance is itself guarded: every fragment tagged ``golden:<name>`` must appear
**verbatim** inside ``tests/fixtures/<name>.expected.md``, so the corpus cannot drift away
from real reader output; ``dogfood:`` fragments are the three asks that were inexpressible
in dogfood session #1 (report § F2/F3).
"""
import random
from pathlib import Path

import pytest

from compose_roundtrip import doc_double, reader_markdown

from larkdocio.write import compose
from larkdocio.write.model import MAX_NEST_DEPTH

# LD-370 — CONFORMANCE-tier: the round-trip property (compose() accepts exactly what the reader emits) is a stated contract, not an implementation detail.
# See process/doctrine/conformance-tier.md (a lens, not a gate).
pytestmark = pytest.mark.conformance

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


class Frag:
    """One corpus fragment.

    ``src`` is the Markdown composed; ``expect`` is the Markdown the reader must emit for
    the composed blocks — ``None`` means **canonical** (``expect is src``: tier A).
    ``golden`` names the reader golden the fragment was lifted from (provenance guard).
    ``lossy`` names the ONE documented class where the reader's Markdown **projection**
    cannot represent the authored block, so tier B does not apply (the write itself is
    faithful — see ``test_ac3_the_only_fixed_point_exception_is_the_documented_one``).
    """

    def __init__(self, name, src, expect=None, *, golden=None, note=None, lossy=None):
        self.name = name
        self.src = src
        self.expect = src if expect is None else expect
        self.canonical = expect is None
        self.golden = golden
        self.note = note
        self.lossy = lossy

    def __repr__(self):  # pragma: no cover - test ids only
        return self.name


# --------------------------------------------------------------------------- #
# (a) fragments lifted VERBATIM from the reader's own goldens — the dialect     #
#     definition, straight from the horse's mouth.                              #
# --------------------------------------------------------------------------- #

_GOLDEN_FRAGMENTS = [
    Frag("golden-bullet", "- First item\n\n- Second item\n", golden="bullet"),
    Frag("golden-ordered", "1. One\n\n2. Two\n\n3. Three\n", golden="ordered"),
    Frag("golden-quote", "> A quoted line\n", golden="quote"),
    # LD-192 — the diagram. Lifted from the reader's own mermaid golden, which is what makes
    # this fragment the round-trip property itself rather than a hand-written sample: the
    # reader wrote this fence, compose() turns it back into the type-40 block it came from,
    # and the reader writes the same fence again. It was the ONE construct that could not do
    # this before mermaid became creatable.
    Frag("golden-mermaid", "```mermaid\ngraph TD\n  A --> B\n```\n", golden="mermaid"),
    Frag("golden-table", "| H1 | H2 |\n|---|---|\n| a | b |\n", golden="simple_table"),
    Frag(
        "golden-headings",
        "# Heading 1\n\n## Heading 2\n\n### Heading 3\n\n#### Heading 4\n\n"
        "##### Heading 5\n\n###### Heading 6\n",
        golden="all_headings",
    ),
    Frag("golden-nested-bullets", "- Level 1 bullet\n\t1. Nested one\n\t2. Nested two\n",
         golden="nested_bullets"),
    Frag("golden-deep-list", "- Level 1\n\t- Level 2\n\t\t- Level 3\n",
         golden="deep_list_nesting"),
    Frag("golden-todo-children", "- [ ] Parent task\n\t- [x] Nested done task\n",
         golden="todo_children"),
    Frag("golden-list-under-heading",
         "# Section\n\n- First\n\t- First nested\n\n- Second\n",
         golden="list_under_heading"),
    Frag("golden-list-then-code",
         "- Item with code\n\n```python\nprint('nested')\n```\n",
         golden="list_nested_code",
         note="a block child of a list item renders as a Markdown SIBLING; composing it "
              "back yields siblings (documented lossiness — the nesting is invisible)"),
    Frag("golden-list-then-quote", "- Item with quote\n\n> Nested quoted line\n",
         golden="list_nested_quote"),
    Frag("golden-cell-multiline-list",
         "| Structure | Note |\n|---|---|\n"
         "| - Level 1<br>\t- Level 2<br>\t\t- Level 3<br>\t\t\t- Level 4<br>"
         "\t\t\t\t- Level 5 | one row, markers intact |\n",
         golden="table_cell_multiline_list"),
    Frag("golden-simple-text", "Hello world\n", golden="simple_text"),
]


# --------------------------------------------------------------------------- #
# (b) the dogfood session's own asks (report § F2/F3 — the three that were      #
#     INEXPRESSIBLE and halted session #1).                                     #
# --------------------------------------------------------------------------- #

_DOGFOOD_FRAGMENTS = [
    Frag("dogfood-h1", "# Insert an H1\n"),
    Frag("dogfood-bullets-nested",
         "- top bullet\n\t- nested bullet\n\n- second top bullet\n"),
    Frag("dogfood-3x3-table",
         "| Metric | Value | Owner |\n|---|---|---|\n"
         "| On-time delivery | 97.2% | Ops |\n| Defect rate | 0.3% | QA |\n"),
    Frag("dogfood-paragraph-in-empty-doc", "Hello World\n"),
]


# --------------------------------------------------------------------------- #
# (c) the escaping classes (LD-130 read in reverse) + adversarial cases.        #
# --------------------------------------------------------------------------- #

_ESCAPING_FRAGMENTS = [
    Frag("escape-atx", "\\# not a heading\n"),
    Frag("escape-atx-deep", "\\### not a heading\n"),
    Frag("escape-bullet-dash", "\\- not a bullet\n"),
    Frag("escape-bullet-star", "\\* not a bullet\n"),
    Frag("escape-bullet-plus", "\\+ not a bullet\n"),
    Frag("escape-ordered-dot", "1\\. not ordered\n"),
    Frag("escape-ordered-paren", "1\\) not ordered\n"),
    Frag("escape-quote", "\\> not a quote\n"),
    Frag("escape-pipe", "\\| not a table row\n"),
    Frag("escape-thematic-break", "\\---\n"),
    Frag("escape-thematic-break-underscore", "\\___\n"),
    Frag("escape-setext", "not a setext heading\n\\===\n"),
    Frag("escape-bold-pair", "\\*\\*not bold\\*\\*\n"),
    Frag("escape-italic-pair", "\\_\\_not italic\\_\\_\n"),
    Frag("escape-strike-pair", "\\~\\~not struck\\~\\~\n"),
    Frag("escape-code-pair", "a \\` b \\` c\n"),
    Frag("escape-only-fragment",
         "\\# h \\- b \\*\\*x\\*\\* 1\\. o \\> q \\| p\n",
         expect="\\# h - b \\*\\*x\\*\\* 1. o > q | p\n",
         note="the reader escapes MINIMALLY (LD-130): only what would really parse as "
              "structure. A mid-line `-`/`1.`/`>`/`|` cannot start a block, so it comes "
              "back unescaped — composing either form yields the same literal text"),
    Frag("escape-multiline-continuation", "prose line\n\\# not a heading\n"),
    Frag("escape-inside-list-item", "- \\# not a nested heading\n"),
    Frag("escape-inside-quote", "> \\- not a nested bullet\n"),
    Frag("escape-inside-heading", "## \\- not a bullet\n",
         expect="## - not a bullet\n",
         note="a heading's own run is NOT block content (the `##` already started the "
              "line), so the reader leaves a leading `-` in heading text unescaped — and "
              "it composes back as that same literal heading text"),
    Frag("escape-in-table-cell", "| A | B |\n|---|---|\n| a \\| b | \\*x\\* |\n"),
    # LD-619 — the ONE inline construct the dialect accepts inside a cell, in a three-column
    # code / name / link table (placeholders). Tier A (canonical), which
    # is the whole point: the reader emits `[label](url)` from a cell whose run carries
    # text_element_style.link.url, Lark was measured to store that run on both write routes,
    # and so the fragment composes and reads back byte-identical.
    Frag("in-cell-labelled-link",
         "| Code | Name | Link |\n|---|---|---|\n"
         "| EX-01 | Example Item | [Example Item - Details]"
         "(https://example.com/items/example-item) |\n"),
    Frag("in-cell-labelled-link-beside-plain-text",
         "| A |\n|---|\n| see [the details](https://example.com/items/example-item) for detail |\n"),
    Frag("unambiguous-metachars-untouched",
         "Issue #5 costs 2 * 3 in snake_case\n"),
    Frag("lone-metachar-mid-line", "the -- dash and the | pipe mid-line\n"),
    Frag("unambiguous-line-needs-no-escape", "--- not a break\n",
         note="`--- x` is neither a thematic break (a break line carries nothing else) "
              "nor a bullet (`-` must be followed by a space), so nothing is escaped"),
]

_ADVERSARIAL_FRAGMENTS = [
    # non-canonical inputs, each with its documented normalization written out
    Frag("tight-bullet-list", "- a\n- b\n", expect="- a\n\n- b\n",
         note="a tight list renders loose: consecutive top-level blocks are separated by "
              "the document's own blank line"),
    Frag("star-bullets-normalize-to-dash", "* a\n* b\n", expect="- a\n\n- b\n"),
    Frag("paren-ordered-normalizes-to-dot", "1) one\n2) two\n",
         expect="1. one\n\n2. two\n"),
    Frag("ordered-renumbers-from-one", "7. seven\n8. eight\n",
         expect="1. seven\n\n2. eight\n",
         note="Lark computes an ordered item's ordinal from its position — the authored "
              "number is not carried, so a list always renders 1..N"),
    Frag("setext-normalizes-to-atx", "Title\n=====\n", expect="# Title\n"),
    Frag("setext-h2-normalizes-to-atx", "Sub\n---\n", expect="## Sub\n"),
    Frag("crlf-normalizes-to-lf", "# H\r\n\r\npara\r\n", expect="# H\n\npara\n"),
    Frag("leading-trailing-blank-lines", "\n\n\npara\n\n\n", expect="para\n"),
    Frag("indented-paragraph-normalizes", "   indented prose\n",
         expect="indented prose\n"),
    Frag("space-nested-list-normalizes-to-tab", "- parent\n  - child\n",
         expect="- parent\n\t- child\n"),
    Frag("bare-url-gains-link-syntax", "see http://example.com/a now\n",
         expect="see [http://example.com/a](http://example.com/a) now\n",
         note="the reader auto-links a bare URL (LD-054, always on, no knob) — the one "
              "shape where the reader ADDS Markdown syntax; composing it back yields the "
              "same plain text, which is why the fixed point still holds"),
    Frag("autolink-angle-normalizes", "<http://example.com>\n",
         expect="[http://example.com](http://example.com)\n"),
    Frag("heading-trailing-hashes", "## H ##\n", expect="## H\n"),
    # LD-146: this entry MOVED FROM TIER A′ TO TIER A. It used to carry
    #     expect="```python\nx = 1\n```\n",
    #     note="the reader strips a fence body's edge whitespace on emission, so blank
    #           edge lines inside a fence are not preserved"
    # — i.e. the code-block whitespace corruption (report T9) was written into the
    # corpus as a documented "normalization". It never was one: the blank edge lines
    # are content, and dropping them is lossy, not canonicalizing. Now that the reader
    # emits the fence body verbatim, this fragment is CANONICAL — the strongest tier.
    Frag("fence-blank-edge-lines", "```python\n\nx = 1\n\n```\n"),
    Frag("fence-indented-first-line",
         "```python\n    def f():\n"
         "        # an indented comment, not a heading\n"
         "        return 1\n"
         "    \n"
         "\tresult = f()   \n```\n",
         golden="code_indented_first_line",
         note="LD-146 / dogfood T9: the reader used to drop the FIRST line's indent "
              "while keeping every later line's, so this fragment could not round-trip "
              "at all; it is canonical now"),
    Frag("fence-ascii-art-bare",
         "```\n   /\\_/\\\n  ( o.o )\n   > ^ <\n```\n",
         note="LD-146: whitespace-significant content in an untagged fence — the shape "
              "dogfood round 2 recommends for ASCII art (language=None)"),
    Frag("empty-header-row-table", "|  |  |\n|---|---|\n| a | b |\n"),
    Frag("table-adjacent-to-heading",
         "## Results\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"),
    Frag("table-then-paragraph",
         "| A |\n|---|\n| 1 |\n\nafter the table\n",
         expect="| A |\n|---|\n| 1 |\n\n\nafter the table\n",
         note="a table (like a quote) already ends with its own blank line, and the "
              "document adds its child separator on top — so the reader's canonical form "
              "carries TWO blank lines after a table (see simple_table.expected.md)"),
    Frag("quote-then-paragraph", "> quoted\n\nafter the quote\n",
         expect="> quoted\n\n\nafter the quote\n"),
    Frag("fence-containing-a-fence",
         "````\n```\ninner fence\n```\n````\n",
         expect="```\n```\ninner fence\n```\n```\n",
         lossy="fence-body-containing-a-fence",
         note="the authored block is FAITHFUL (the body is carried verbatim, and Lark "
              "stores it) but the reader always emits a 3-backtick fence, so the inner "
              "fence closes the outer one on re-parse — a reader PROJECTION lossiness, "
              "not a write lossiness. Tier B therefore does not apply to this one class"),
    Frag("list-interrupted-by-paragraph",
         "- a\n\ninterruption\n\n- b\n"),
    Frag("mixed-everything",
         "# Title\n\n"
         "Intro prose with an \\*\\*escaped\\*\\* marker.\n\n"
         "- [x] done task\n\t- [ ] nested open task\n\n"
         "1. first step\n\n2. second step\n\n"
         "```python\nx = 1\n```\n\n"
         "> a quoted conclusion\n\n"
         "| Metric | Value |\n|---|---|\n| a \\| b | 97.2% |\n",
         expect="# Title\n\n"
                "Intro prose with an \\*\\*escaped\\*\\* marker.\n\n"
                "- [x] done task\n\t- [ ] nested open task\n\n"
                "1. first step\n\n2. second step\n\n"
                "```python\nx = 1\n```\n\n"
                "> a quoted conclusion\n\n\n"
                "| Metric | Value |\n|---|---|\n| a \\| b | 97.2% |\n",
         note="every kind in one fragment; the only normalization is the quote's own "
              "trailing blank line (see quote-then-paragraph)"),
    Frag("unicode-and-emoji", "# 标题 🎉\n\n- 项目一\n\n- 项目二\n"),
    Frag("very-long-line", "x" * 500 + "\n"),
    Frag("nesting-at-the-cap",
         "".join("\t" * d + f"- L{d + 1}\n" for d in range(MAX_NEST_DEPTH))),
    Frag("code-with-metachars",
         "```python\n# a real comment\n- not a bullet\n| not a table |\n```\n"),
    Frag("quote-multiline", "> line one\n> line two\n"),
    Frag("table-cell-with-newline", "| A |\n|---|\n| one<br>two |\n"),
    Frag("table-1xN", "| a | b | c | d |\n|---|---|---|---|\n"),
    Frag("table-Nx1", "| a |\n|---|\n| b |\n| c |\n"),
    Frag("empty-table-cells", "| A | B |\n|---|---|\n|  |  |\n"),
    Frag("footnote-reference-is-literal-text", "prose with a ref[^1] inline\n",
         note="only a footnote DEFINITION refuses; a bare reference is literal text in "
              "GFM too, and this proves it round-trips rather than being over-refused"),
    Frag("regex-character-class-is-literal-text", "use [^a-z] to match a non-letter\n"),
    Frag("dollar-signs-are-literal-text", "costs $5 and $$10\n"),
    Frag("at-mention-shape-is-literal-text", "@ou_abc123 shipped it\n",
         note="the reader emits `@<user_id>` for a user mention; it composes as text"),
    Frag("brackets-without-a-destination", "an [aside] in brackets\n"),
    Frag("tab-inside-paragraph-text", "before\tafter\n"),
    Frag("trailing-spaces-are-dropped", "prose with trailing spaces   \n",
         expect="prose with trailing spaces\n"),
]

CORPUS = (
    _GOLDEN_FRAGMENTS + _DOGFOOD_FRAGMENTS + _ESCAPING_FRAGMENTS + _ADVERSARIAL_FRAGMENTS
)


# =========================================================================== #
# corpus integrity — provenance and shape                                      #
# =========================================================================== #

def test_the_corpus_covers_every_construct_and_is_uniquely_named():
    names = [f.name for f in CORPUS]
    assert len(names) == len(set(names))
    assert len(CORPUS) >= 60, "the corpus is the amplifier — keep it broad"


@pytest.mark.parametrize("frag", [f for f in CORPUS if f.golden], ids=repr)
def test_every_golden_sourced_fragment_appears_verbatim_in_that_golden(frag):
    """Provenance guard: the corpus is not hand-invented Markdown — the fragments tagged
    ``golden:`` are lifted from the reader's own golden output, and this binds them to it.
    A reader change that alters the emission reddens HERE, not silently."""
    golden = (_FIXTURES / f"{frag.golden}.expected.md").read_text(encoding="utf-8")
    assert frag.src in golden, (
        f"{frag.name} claims to come from {frag.golden}.expected.md but does not appear "
        f"in it verbatim"
    )


# =========================================================================== #
# AC3 — THE BINDING PROPERTY                                                    #
# =========================================================================== #

@pytest.mark.parametrize("frag", CORPUS, ids=repr)
def test_ac3_tier_a_the_reader_emits_the_expected_markdown_for_composed_content(frag):
    """Tier A / A′: what the reader emits for ``compose(X)`` is ``X`` itself (canonical
    fragments) or exactly the normalization the corpus entry documents."""
    assert reader_markdown(compose(frag.src)) == frag.expect


@pytest.mark.parametrize("frag", [f for f in CORPUS if not f.lossy], ids=repr)
def test_ac3_tier_b_compose_of_the_readers_output_is_a_fixed_point(frag):
    """Tier B: composing the reader's own output reproduces the same content, and the
    reader's emission is idempotent — so every normalization is a normalization, not a
    progressive loss."""
    first = reader_markdown(compose(frag.src))
    content = compose(first)
    assert content == compose(frag.expect)
    assert reader_markdown(content) == first


def test_ac3_the_only_fixed_point_exception_is_the_documented_one():
    """The tier-B carve-out is pinned, not hand-waved: exactly ONE documented class is
    exempt — a **fence body that itself contains a fence line**. The authored block is
    faithful (the body is carried verbatim and Lark stores it); the reader always emits a
    3-backtick fence, so re-reading it splits the block. That is a reader **projection**
    lossiness, it is in the shipped lossiness table, and nothing else may join it without
    this test being changed deliberately."""
    exempt = {f.lossy for f in CORPUS if f.lossy}
    assert exempt == {"fence-body-containing-a-fence"}

    # And the exception is real in exactly the way documented: pass 1 is faithful, pass 2
    # splits — the block content Lark holds is right either way.
    from larkdocio.write.model import NewBlock, NewBlockKind

    src = "````\n```\ninner fence\n```\n````\n"
    assert compose(src) == (NewBlock.code("```\ninner fence\n```"),)
    reread = compose(reader_markdown(compose(src)))
    assert [b.kind for b in reread] == [
        NewBlockKind.CODE, NewBlockKind.PARAGRAPH, NewBlockKind.CODE,
    ]


@pytest.mark.parametrize("frag", [f for f in CORPUS if f.canonical], ids=repr)
def test_ac3_a_canonical_fragment_round_trips_byte_identically(frag):
    """The headline statement, isolated so it cannot hide behind a normalization: for a
    fragment in the reader's own dialect the round-trip is byte-identical."""
    assert reader_markdown(compose(frag.src)) == frag.src


@pytest.mark.parametrize("frag", CORPUS, ids=repr)
def test_ac3_the_doc_double_carries_only_creatable_block_types(frag):
    """The round-trip is only meaningful if the doc-double is honest: every block it holds
    must be one the encoder can really create (plus the page root and the cell family Lark
    provisions itself)."""
    from larkdocio.write.encode import CREATABLE_BLOCK_TYPES

    for block in doc_double(compose(frag.src))[1:]:
        assert block["block_type"] in CREATABLE_BLOCK_TYPES


def test_ac3_the_corpus_exercises_every_composable_kind():
    """Coverage assertion over the corpus itself: every creatable kind appears."""
    from larkdocio.write.model import NewBlockKind

    seen = set()

    def walk(blocks):
        for block in blocks:
            seen.add(block.kind)
            walk(block.children)

    for frag in CORPUS:
        walk(compose(frag.src))
    assert seen == set(NewBlockKind)


# =========================================================================== #
# AC3 (tier C) — the same property over SEEDED generated fragments              #
# =========================================================================== #

_SEED = 20260728


def _generated_fragment(rng) -> str:
    """Build a fragment from the construct grammar — deterministic given ``rng``."""
    words = ["alpha", "beta", "gamma", "delta", "97.2%", "Ops", "QA", "#5", "a-b", "x_y"]
    langs = [None, "python", "go", "json", "bash"]

    def text():
        return " ".join(rng.choice(words) for _ in range(rng.randint(1, 4)))

    def list_lines(marker_kind, depth=0, budget=2):
        lines = []
        for _ in range(rng.randint(1, 3)):
            if marker_kind == "bullet":
                marker = "- "
            elif marker_kind == "ordered":
                marker = f"{rng.randint(1, 9)}. "
            else:
                marker = "- [x] " if rng.random() < 0.5 else "- [ ] "
            lines.append("\t" * depth + marker + text())
            if budget and rng.random() < 0.4:
                lines.extend(list_lines(
                    rng.choice(["bullet", "ordered", "todo"]), depth + 1, budget - 1,
                ))
        return lines

    def block():
        pick = rng.choice(
            ["heading", "paragraph", "bullet", "ordered", "todo", "code", "quote", "table"]
        )
        if pick == "heading":
            return "#" * rng.randint(1, 6) + " " + text()
        if pick == "paragraph":
            return text()
        if pick in ("bullet", "ordered", "todo"):
            return "\n".join(list_lines(pick))
        if pick == "code":
            lang = rng.choice(langs)
            body = "\n".join(text() for _ in range(rng.randint(1, 3)))
            return f"```{lang or ''}\n{body}\n```"
        if pick == "quote":
            return "\n".join("> " + text() for _ in range(rng.randint(1, 2)))
        columns = rng.randint(1, 3)
        rows = rng.randint(1, 3)
        head = "| " + " | ".join(text() for _ in range(columns)) + " |"
        delim = "|" + "|".join(["---"] * columns) + "|"
        body = [
            "| " + " | ".join(text() for _ in range(columns)) + " |"
            for _ in range(rows)
        ]
        return "\n".join([head, delim] + body)

    return "\n\n".join(block() for _ in range(rng.randint(1, 4))) + "\n"


def _generated_corpus(count=200):
    rng = random.Random(_SEED)
    return [_generated_fragment(rng) for _ in range(count)]


def test_ac3_tier_c_generated_fragments_reach_a_fixed_point():
    """Tier C: 200 seeded fragments from the construct grammar. Each must compose, and the
    reader's emission of the composed blocks must be a **fixed point** under
    compose→render — the property with no hand-written expectations to lean on."""
    for index, src in enumerate(_generated_corpus()):
        first = reader_markdown(compose(src))
        second = reader_markdown(compose(first))
        assert second == first, f"generated fragment #{index} did not settle:\n{src!r}"
        assert compose(first) == compose(second)


def test_ac3_tier_c_is_deterministic():
    """The generated corpus is seeded, so the suite cannot flake: two builds are equal."""
    assert _generated_corpus(25) == _generated_corpus(25)


def test_ac3_tier_c_generates_a_real_variety():
    corpus = _generated_corpus()
    assert len({len(src) for src in corpus}) > 20
    joined = "".join(corpus)
    for marker in ("# ", "- ", "- [x] ", "```", "> ", "|---"):
        assert marker in joined
