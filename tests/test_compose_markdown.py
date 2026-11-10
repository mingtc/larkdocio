"""Offline unit tests for ``compose(markdown)`` — the dialect parser → request compiler
(LD-136).

S1/S2 made structure *creatable*; this story makes it **authorable from Markdown**:
``compose()`` compiles a fragment written in **exactly our reader's dialect** (D4 — the
GFM subset **including the LD-130 escaping rules**) into the ordered typed ``NewBlock``
content an ``InsertRequest`` carries. It **produces content, never writes** — no client,
no credential, no transport.

The binding property (AC3) is a **round-trip against the reader itself**, asserted in
``test_compose_roundtrip_corpus.py``: what the reader emits for blocks composed from ``X``
must be ``X`` again (canonical fragments) or ``X``'s documented normalization, and
composing *that* is a fixed point. This file owns the per-construct contract (AC1), the
escaping-in-reverse contract (AC2), the refusal contract (AC5), and the never-writes
contract (AC6).

Everything here is offline: no network, no clock, no randomness.
"""
import ast
import inspect
from pathlib import Path

import pytest

from larkdocio.write import compose, compose_insert
from larkdocio.write.compose import NOT_EXPRESSIBLE_CONSTRUCTS
from larkdocio.write.model import (
    MAX_CHILDREN_PER_CALL,
    MAX_NEST_DEPTH,
    MAX_TABLE_CELLS,
    Anchor,
    InsertPosition,
    InsertRequest,
    NewBlock,
    NewBlockKind,
    RefusalReason,
    RefusedError,
)


# --------------------------------------------------------------------------- #
# helpers                                                                       #
# --------------------------------------------------------------------------- #

def _refusal(markdown):
    """Compose ``markdown``, asserting it refuses, and return the typed refusal."""
    with pytest.raises(RefusedError) as exc:
        compose(markdown)
    return exc.value.refusal


def _one(markdown):
    """Compose a fragment expected to yield exactly one block."""
    content = compose(markdown)
    assert len(content) == 1, f"expected one block, got {content}"
    return content[0]


# =========================================================================== #
# AC1 — every construct compiles to its S1/S2 kind, in document order          #
# =========================================================================== #

@pytest.mark.parametrize("level", range(1, 7))
def test_ac1_an_atx_heading_composes_to_its_level(level):
    block = _one("#" * level + " Section title\n")
    assert block == NewBlock.heading(level, "Section title")


def test_ac1_a_setext_heading_composes_to_a_level_1_heading():
    """A setext underline is a CommonMark heading; the reader emits ATX, so it composes
    to the same block and re-renders as ``# Title`` (documented normalization)."""
    assert _one("Title\n=====\n") == NewBlock.heading(1, "Title")


def test_ac1_a_paragraph_composes_to_a_paragraph():
    assert _one("Just some prose.\n") == NewBlock.paragraph("Just some prose.")


def test_ac1_a_multi_line_paragraph_keeps_its_soft_break():
    """A soft break inside a paragraph is a newline in the block's text — which is what
    the reader emits it from (one text block, two lines)."""
    assert _one("first line\nsecond line\n") == NewBlock.paragraph("first line\nsecond line")


def test_ac1_a_bullet_list_composes_to_bullet_items():
    assert compose("- one\n- two\n") == (NewBlock.bullet("one"), NewBlock.bullet("two"))


def test_ac1_a_star_bullet_list_composes_to_bullet_items():
    """``*``/``+`` are CommonMark bullets too (the reader emits ``-``)."""
    assert compose("* one\n+ two\n") == (NewBlock.bullet("one"), NewBlock.bullet("two"))


def test_ac1_an_ordered_list_composes_to_ordered_items_without_authoring_numbers():
    """Lark computes an ordered item's ordinal from its position, so the authored numbers
    are deliberately not carried (a number in the request could disagree with the doc)."""
    assert compose("1. one\n2. two\n") == (NewBlock.ordered("one"), NewBlock.ordered("two"))
    assert compose("7) seven\n8) eight\n") == (
        NewBlock.ordered("seven"), NewBlock.ordered("eight"),
    )


def test_ac1_a_todo_list_composes_to_todo_items_in_both_states():
    assert compose("- [ ] open\n- [x] closed\n") == (
        NewBlock.todo("open", done=False), NewBlock.todo("closed", done=True),
    )
    assert compose("- [X] upper\n") == (NewBlock.todo("upper", done=True),)


def test_ac1_a_bullet_list_may_mix_todo_and_plain_items():
    assert compose("- [ ] task\n- plain\n") == (
        NewBlock.todo("task"), NewBlock.bullet("plain"),
    )


def test_ac1_an_ordered_item_checkbox_prefix_stays_literal_text():
    """The reader only ever emits a checkbox on a ``-`` item, so ``1. [ ] x`` is an
    ordered item whose text happens to start with a bracket — not a todo."""
    assert compose("1. [ ] x\n") == (NewBlock.ordered("[ ] x"),)


def test_ac1_a_code_fence_composes_with_its_language():
    assert _one("```python\nprint(1)\n```\n") == NewBlock.code("print(1)", language="python")


def test_ac1_a_bare_fence_composes_with_no_language():
    block = _one("```\nplain text\n```\n")
    assert block == NewBlock.code("plain text")
    assert block.language is None


def test_ac1_a_tilde_fence_is_a_fence_too():
    assert _one("~~~go\nx := 1\n~~~\n") == NewBlock.code("x := 1", language="go")


def test_ac1_a_multi_line_fence_keeps_its_body_lines():
    assert _one("```python\na = 1\nb = 2\n```\n") == NewBlock.code(
        "a = 1\nb = 2", language="python",
    )


def test_ac1_an_empty_fence_composes_to_an_empty_code_block():
    assert _one("```\n```\n") == NewBlock.code("")


def test_ac1_a_blockquote_composes_to_a_quote():
    assert _one("> quoted line\n") == NewBlock.quote("quoted line")


def test_ac1_a_multi_line_blockquote_keeps_its_lines_in_one_quote():
    """The reader emits a quote block's multi-line text as consecutive ``> `` lines, so
    they compose back into ONE quote carrying the newline."""
    assert _one("> line a\n> line b\n") == NewBlock.quote("line a\nline b")


def test_ac1_a_gfm_table_composes_to_a_table_with_the_header_promoted():
    block = _one("| Metric | Value |\n|---|---|\n| On-time | 97.2% |\n")
    assert block == NewBlock.table(
        [["Metric", "Value"], ["On-time", "97.2%"]], header_row=True,
    )
    assert block.row_count == 2 and block.column_count == 2


def test_ac1_a_one_by_one_table_composes():
    assert _one("| only |\n|---|\n") == NewBlock.table([["only"]])


def test_ac1_a_table_cell_may_be_empty():
    assert _one("| A | B |\n|---|---|\n|  | b |\n") == NewBlock.table(
        [["A", "B"], ["", "b"]],
    )


def test_ac1_a_table_without_leading_pipes_composes_the_same_grid():
    assert _one("A | B\n--- | ---\na | b\n") == NewBlock.table([["A", "B"], ["a", "b"]])


def test_ac1_a_table_cell_br_is_the_newline_the_reader_emitted_it_for():
    """A Markdown pipe cell cannot hold a literal newline, so the reader emits ``<br>``
    (LD-041). Composing reverses exactly that projection."""
    assert _one("| A |\n|---|\n| one<br>two |\n") == NewBlock.table(
        [["A"], ["one\ntwo"]],
    )
    assert _one("| A |\n|---|\n| one<br/>two |\n") == NewBlock.table(
        [["A"], ["one\ntwo"]],
    )


def test_ac1_mixed_constructs_compose_in_document_order():
    md = (
        "## Plan\n"
        "\n"
        "Intro prose.\n"
        "\n"
        "- first\n"
        "- second\n"
        "\n"
        "1. step\n"
        "\n"
        "- [x] done\n"
        "\n"
        "```python\nx = 1\n```\n"
        "\n"
        "> a quote\n"
        "\n"
        "| A | B |\n|---|---|\n| a | b |\n"
    )
    assert compose(md) == (
        NewBlock.heading(2, "Plan"),
        NewBlock.paragraph("Intro prose."),
        NewBlock.bullet("first"),
        NewBlock.bullet("second"),
        NewBlock.ordered("step"),
        NewBlock.todo("done", done=True),
        NewBlock.code("x = 1", language="python"),
        NewBlock.quote("a quote"),
        NewBlock.table([["A", "B"], ["a", "b"]]),
    )


def test_ac1_compose_returns_a_tuple_of_newblocks_only():
    """The legacy tagless ``NewParagraph`` stays valid *input* to an InsertRequest, but
    the compiler always emits the typed kind (byte-identical payload either way)."""
    content = compose("para\n")
    assert isinstance(content, tuple)
    assert all(isinstance(b, NewBlock) for b in content)
    assert content[0].kind is NewBlockKind.PARAGRAPH


def test_ac1_an_empty_fragment_composes_to_no_content():
    assert compose("") == ()


@pytest.mark.parametrize("blank", ["   ", "\n\n\n", "   \n\t\n  ", "\r\n\r\n"])
def test_ac1_a_whitespace_only_fragment_composes_to_no_content(blank):
    assert compose(blank) == ()


def test_ac1_crlf_and_lf_compose_identically():
    lf = "# H\n\npara\n\n- item\n"
    assert compose(lf.replace("\n", "\r\n")) == compose(lf)
    assert compose("# H\r\npara2\r\n") == (
        NewBlock.heading(1, "H"), NewBlock.paragraph("para2"),
    )


def test_ac1_leading_and_trailing_blank_lines_are_not_content():
    assert compose("\n\n\npara\n\n\n") == (NewBlock.paragraph("para"),)


def test_ac1_a_non_string_fragment_is_a_type_error():
    with pytest.raises(TypeError):
        compose(None)
    with pytest.raises(TypeError):
        compose(["# not markdown"])


# --------------------------------------------------------------------------- #
# AC1 — nesting                                                                 #
# --------------------------------------------------------------------------- #

def test_ac1_a_tab_indented_nested_list_composes_as_children():
    """Tabs are what the reader emits for a nested list item."""
    assert compose("- parent\n\t- child\n") == (
        NewBlock.bullet("parent", children=(NewBlock.bullet("child"),)),
    )


def test_ac1_a_space_indented_nested_list_composes_the_same_tree():
    assert compose("- parent\n  - child\n") == compose("- parent\n\t- child\n")


def test_ac1_three_level_nesting_composes_three_deep():
    tree = _one("- L1\n\t- L2\n\t\t- L3\n")
    assert tree == NewBlock.bullet("L1", children=(
        NewBlock.bullet("L2", children=(NewBlock.bullet("L3"),)),
    ))
    assert tree.depth == 3


def test_ac1_nesting_may_mix_list_kinds():
    assert _one("- bullet\n\t1. ordered\n\t\t- [ ] todo\n") == NewBlock.bullet(
        "bullet", children=(
            NewBlock.ordered("ordered", children=(NewBlock.todo("todo"),)),
        ),
    )


def test_ac1_a_list_interrupted_by_a_paragraph_composes_as_siblings():
    assert compose("- a\n\ninterruption\n\n- b\n") == (
        NewBlock.bullet("a"), NewBlock.paragraph("interruption"), NewBlock.bullet("b"),
    )


def test_ac1_nesting_at_exactly_the_documented_cap_composes():
    md = "".join("\t" * d + f"- L{d + 1}\n" for d in range(MAX_NEST_DEPTH))
    assert _one(md).depth == MAX_NEST_DEPTH


def test_ac1_no_item_text_is_silently_lost_at_the_cap():
    """The parser's OWN nesting limit must not bite before larkdocio's documented cap.

    ``markdown-it``'s default ``maxNesting`` (20) is reached at ~10 list levels and past it
    the parser **silently drops** the over-deep item's inline content — a ten-level list
    came back with an EMPTY tenth item. Composing that would author an empty block (a
    silent content drop). The compiler derives the parser's limit from
    ``MAX_NEST_DEPTH``, so every level's text survives to the cap."""
    md = "".join("\t" * d + f"- L{d + 1}\n" for d in range(MAX_NEST_DEPTH))
    texts, block = [], _one(md)
    while block is not None:
        texts.append(block.text)
        block = block.children[0] if block.children else None
    assert texts == [f"L{d + 1}" for d in range(MAX_NEST_DEPTH)]


# =========================================================================== #
# AC2 — the dialect is the READER's: LD-130 escaping honored IN REVERSE         #
# =========================================================================== #

@pytest.mark.parametrize("escaped,literal", [
    ("\\# not a heading", "# not a heading"),          # atx
    ("\\## not a heading", "## not a heading"),        # atx, deeper
    ("\\- not a bullet", "- not a bullet"),            # bullet
    ("\\* not a bullet", "* not a bullet"),
    ("\\+ not a bullet", "+ not a bullet"),
    ("1\\. not ordered", "1. not ordered"),            # ordered delimiter (never the digit)
    ("1\\) not ordered", "1) not ordered"),
    ("\\> not a quote", "> not a quote"),              # quote
    ("\\| not a table row", "| not a table row"),      # pipe
    ("\\*\\*not bold\\*\\*", "**not bold**"),          # emphasis pair
    ("\\_\\_not italic\\_\\_", "__not italic__"),
    ("\\~\\~not struck\\~\\~", "~~not struck~~"),      # strikethrough pair
    ("a \\` b \\` c", "a ` b ` c"),                    # code-span pair
    ("\\-\\-\\- not a break", "--- not a break"),      # thematic break
])
def test_ac2_an_escaped_metachar_composes_to_literal_text(escaped, literal):
    """AC2, one test per escape class: the reader escapes a metachar so plain text can
    never masquerade as structure (LD-130); composing reverses it, so the escape yields
    **literal text** and never structure."""
    block = _one(escaped + "\n")
    assert block.kind is NewBlockKind.PARAGRAPH
    assert block.text == literal


def test_ac2_a_fragment_that_is_only_escaped_text_is_one_paragraph():
    src = "\\# h \\- b \\*\\*x\\*\\* 1\\. o \\> q \\| p\n"
    assert _one(src) == NewBlock.paragraph("# h - b **x** 1. o > q | p")


def test_ac2_the_unescaped_forms_are_still_structure():
    """The other half of the contract: escaping is what makes the difference — the same
    text unescaped composes to the real construct."""
    assert _one("# a heading\n") == NewBlock.heading(1, "a heading")
    assert _one("- a bullet\n") == NewBlock.bullet("a bullet")
    assert _one("> a quote\n") == NewBlock.quote("a quote")


def test_ac2_an_escaped_pipe_in_a_table_cell_is_a_literal_pipe():
    assert _one("| A |\n|---|\n| a \\| b |\n") == NewBlock.table([["A"], ["a | b"]])


def test_ac2_an_escape_on_a_continuation_line_composes_to_literal_text():
    """The reader escapes EVERY line of a multi-line run, not just the first."""
    assert _one("prose\n\\# not a heading\n") == NewBlock.paragraph(
        "prose\n# not a heading",
    )


def test_ac2_a_metachar_that_cannot_start_structure_is_untouched():
    """LD-130 leaves an unambiguous metachar alone (``Issue #5``, ``2 * 3``,
    ``snake_case``), so composing sees it verbatim — no escape to reverse."""
    assert _one("Issue #5 costs 2 * 3 in snake_case\n") == NewBlock.paragraph(
        "Issue #5 costs 2 * 3 in snake_case",
    )


def test_ac2_a_heading_whose_text_starts_with_a_hash_composes_that_hash_as_text():
    assert _one("# # literal hash\n") == NewBlock.heading(1, "# literal hash")


# =========================================================================== #
# AC5 — an out-of-dialect construct REFUSES with a typed detail naming it       #
# =========================================================================== #

def test_ac5_the_refusal_reason_is_its_own_typed_value():
    assert RefusalReason.NOT_IN_DIALECT.value == "not-in-dialect"


@pytest.mark.parametrize("construct,md", [
    ("image", "![alt](sometoken)\n"),
    ("link", "see [the doc](https://example.com/x)\n"),
    ("bold", "**bold** text\n"),
    ("italic", "*italic* text\n"),
    ("strikethrough", "~~struck~~ text\n"),
    ("inline-code", "a `code span` here\n"),
    ("html", "<u>underlined</u>\n"),
    ("html", "<div>block</div>\n"),
    ("thematic-break", "---\n"),
    ("indented-code-block", "    indented code\n"),
    ("hard-break", "line a  \nline b\n"),
    ("footnote", "[^1]: the note\n"),
    ("footnote", "[^note-label]: a labelled note\n"),
    ("merged-table", "<table>\n<tr><td>a</td></tr>\n</table>\n"),
])
def test_ac5_an_out_of_dialect_construct_refuses_naming_it(construct, md):
    """AC5: never a silent drop and never a best-effort approximation — a typed refusal
    naming the construct and why (LD-131's mandatory ``detail``)."""
    refusal = _refusal(md)
    assert refusal.reason in (
        RefusalReason.NOT_IN_DIALECT, RefusalReason.MERGE_NOT_EXPRESSIBLE,
    )
    assert construct in refusal.detail
    assert refusal.detail.strip()


def test_ac5_a_merged_table_refuses_as_a_MERGE_not_a_generic_dialect_miss():
    """The reader emits an HTML ``<table>`` for a merged table, so *that* shape is a
    merge — and it reuses the LD-135 merge refusal rather than inventing a second story."""
    refusal = _refusal("<table>\n<tr><td rowspan=\"2\">a</td></tr>\n</table>\n")
    assert refusal.reason is RefusalReason.MERGE_NOT_EXPRESSIBLE
    assert "merged-table" in refusal.detail


def test_ac5_a_ragged_pipe_table_refuses_instead_of_being_padded_or_truncated():
    """GFM **silently** pads a short row and **truncates** a long one, so the token
    stream alone cannot see raggedness — the compiler counts the source cells itself.
    A ragged grid is the shape a merged table produces (LD-135)."""
    refusal = _refusal("| A | B |\n|---|---|\n| only-one |\n")
    assert refusal.reason is RefusalReason.MERGE_NOT_EXPRESSIBLE
    assert "merged-table" in refusal.detail
    long_row = _refusal("| A | B |\n|---|---|\n| x | y | z |\n")
    assert long_row.reason is RefusalReason.MERGE_NOT_EXPRESSIBLE


def test_ac5_a_refusal_detail_names_the_1_based_line_of_the_construct():
    refusal = _refusal("fine prose\n\nmore prose\n\n![alt](tok)\n")
    assert "line 5" in refusal.detail


def test_ac5_a_refusal_detail_counts_lines_across_a_soft_break():
    refusal = _refusal("prose\nmore prose\n**bold on line 3**\n")
    assert "line 3" in refusal.detail


def test_ac5_a_block_child_inside_a_list_item_refuses():
    """A list item carries its own text plus **nested list items** — the reader renders
    any other block child at column 0 (a sibling in Markdown), so an authored block child
    is not expressible and is never silently relocated."""
    second_para = _refusal("- item\n\n  second paragraph\n")
    assert second_para.reason is RefusalReason.NOT_IN_DIALECT
    assert "list-item-block-child" in second_para.detail
    fence = _refusal("- item\n\n  ```python\n  x\n  ```\n")
    assert "list-item-block-child" in fence.detail


def test_ac5_an_empty_list_item_refuses():
    refusal = _refusal("- \n")
    assert "empty-list-item" in refusal.detail


def test_ac5_a_block_child_inside_a_blockquote_refuses():
    """Lark's creatable quote block (type 15) carries ONE text run; a quote *container*
    (type 34) is not creatable, so a multi-block blockquote is not expressible."""
    two_paras = _refusal("> first\n>\n> second\n")
    assert "blockquote-block-child" in two_paras.detail
    fenced = _refusal("> ```\n> x\n> ```\n")
    assert "blockquote-block-child" in fenced.detail


def test_ac5_a_nested_blockquote_refuses():
    assert "blockquote-block-child" in _refusal("> outer\n>\n> > inner\n").detail


def test_ac5_an_unknown_code_language_refuses_naming_the_token():
    refusal = _refusal("```notalanguage\nx\n```\n")
    assert refusal.reason is RefusalReason.NOT_IN_DIALECT
    assert "notalanguage" in refusal.detail
    assert "unknown-code-language" in refusal.detail
    # the recovery is actionable: the supported set is discoverable
    assert "supported_code_languages" in refusal.detail


def test_ac5_a_fence_info_string_carrying_more_than_a_language_refuses():
    refusal = _refusal("```python title=demo.py\nx\n```\n")
    assert "code-fence-info" in refusal.detail


def test_ac5_nesting_deeper_than_the_documented_cap_refuses_with_the_cap_named():
    md = "".join("\t" * d + f"- L{d + 1}\n" for d in range(MAX_NEST_DEPTH + 1))
    refusal = _refusal(md)
    assert refusal.reason is RefusalReason.NOT_IN_DIALECT
    assert "nesting-too-deep" in refusal.detail
    assert str(MAX_NEST_DEPTH) in refusal.detail


def test_ac5_a_table_past_the_documented_cell_cap_refuses_with_the_cap_named():
    columns = 5
    rows = MAX_TABLE_CELLS // columns + 1
    header = "| " + " | ".join(f"c{c}" for c in range(columns)) + " |\n"
    delim = "|" + "|".join(["---"] * columns) + "|\n"
    body = "".join(
        "| " + " | ".join(f"r{r}c{c}" for c in range(columns)) + " |\n"
        for r in range(rows - 1)
    )
    refusal = _refusal(header + delim + body)
    assert str(MAX_TABLE_CELLS) in refusal.detail


def test_ac5_an_unrecognized_construct_hits_the_closed_world_fallback():
    """The compiler is **closed-world**: it recognizes a construct or refuses. The two
    catch-all labels are the guarantee that a future parser version (or an enabled
    extension) can never introduce a construct that is silently ignored — so they are
    exercised directly with a node type the dialect does not have."""
    from larkdocio.write.compose import _Compiler

    class _FakeNode:
        type = "definition_list"
        map = (2, 3)
        children = ()
        content = ""

    compiler = _Compiler("line1\nline2\nline3\n")
    with pytest.raises(RefusedError) as block_exc:
        compiler._blocks([_FakeNode()], depth=1)
    assert block_exc.value.refusal.detail.startswith("block at line 3")
    assert "definition_list" in block_exc.value.refusal.detail

    class _FakeInline:
        type = "inline"
        map = (0, 1)
        children = (_FakeNode(),)

    with pytest.raises(RefusedError) as inline_exc:
        compiler._inline_text(_FakeInline())
    assert inline_exc.value.refusal.detail.startswith("inline at line 1")
    assert "definition_list" in inline_exc.value.refusal.detail


def test_ac5_every_refusal_the_compiler_can_raise_carries_a_construct_and_a_reason():
    """The construct labels are a closed, documented set (the lossiness table's code
    truth) — every one is a non-empty label with a non-empty ``why``."""
    assert NOT_EXPRESSIBLE_CONSTRUCTS
    for construct, why in NOT_EXPRESSIBLE_CONSTRUCTS.items():
        assert construct and construct == construct.strip()
        assert why and why.strip()


@pytest.mark.conformance
def test_ld433_the_image_refusal_is_transformed_not_deleted():
    """SUPERSESSION, the "preserve the reason, replace the conclusion" shape.

    A Markdown ``![](…)`` is **still refused** — the compiler holds no bytes and makes no
    network call, and that reason is unchanged. What was superseded is the refusal's
    *conclusion*: it used to end by telling the caller to **wait** for a media rung that has
    since shipped. It must now name the op that does it, and it must not go back to telling
    anyone to wait."""
    why = NOT_EXPRESSIBLE_CONSTRUCTS["image"].lower()
    assert "put_image_in_document" in why           # the conclusion, superseded
    assert "wait" not in why                        # …and the stale one gone
    assert "no bytes" in why or "has no bytes" in why  # the reason, preserved

    with pytest.raises(RefusedError):               # …and it is still a refusal
        compose("![alt](tok)\n")


def test_ac5_compose_raises_only_the_typed_refusal_never_a_bare_value_error():
    """One error type out of the compiler: a caught construction ``ValueError`` (a cap, an
    impossible block) is re-raised as a ``RefusedError`` carrying the typed refusal, so a
    consumer never has to parse a message string."""
    for md in ("![a](b)\n", "---\n", "```nope\nx\n```\n", "- \n"):
        with pytest.raises(RefusedError):
            compose(md)


def test_ac5_the_link_exception_is_only_the_readers_own_bare_url_autolink():
    """The reader auto-linkifies a bare URL (LD-054, always on, no knob), so ``[u](u)``
    composes back to the literal URL — while a link with different text refuses."""
    assert _one("see [http://example.com](http://example.com) now\n") == NewBlock.paragraph(
        "see http://example.com now",
    )
    assert _one("<http://example.com>\n") == NewBlock.paragraph("http://example.com")
    assert "link" in _refusal("see [label](http://example.com)\n").detail


def test_ac5_a_bracket_shape_in_literal_text_refuses_rather_than_mis_authoring():
    """The documented ASYMMETRY (reported to the maintainer, NOT fixed here): LD-130 escapes
    line-leading block markers and pairable emphasis runs, **not** ``[``-bracket shapes.
    So a paragraph whose literal text looks like a link or an image is re-emitted by the
    reader unescaped and refuses on re-composition. Refusing is the honest outcome — the
    alternative is authoring a link the consumer did not write."""
    assert "link" in _refusal("literal [a](b) text\n").detail
    assert "image" in _refusal("literal ![a](b) text\n").detail


def test_ac5_only_a_footnote_DEFINITION_refuses_a_bare_reference_is_literal_text():
    """The footnote refusal is deliberately narrow. A footnote **definition**
    (``[^1]: …``) is the unambiguous marker of footnote intent and has no creatable
    block. A bare ``[^1]`` *reference* — and a regex character class like ``[^a-z]``, which
    is the identical shape — is literal text in CommonMark **and** in GFM without a
    definition, so it composes verbatim. Refusing those would refuse content that provably
    round-trips, which is its own kind of dishonesty."""
    assert "footnote" in _refusal("[^1]: the note\n").detail
    assert _one("prose with a ref[^1] inline\n") == NewBlock.paragraph(
        "prose with a ref[^1] inline",
    )
    assert _one("use [^a-z] to match a non-letter\n") == NewBlock.paragraph(
        "use [^a-z] to match a non-letter",
    )
    assert _one("| Pattern |\n|---|\n| [^a-z] |\n") == NewBlock.table(
        [["Pattern"], ["[^a-z]"]],
    )


@pytest.mark.parametrize("construct,md", [
    ("empty-heading", "# \n"),
    ("empty-quote", ">\n"),
    ("empty-quote", "> \n"),
    ("empty-list-item", "- \n"),
    ("empty-list-item", "1. \n"),
])
def test_ac5_a_marker_with_no_content_refuses_naming_which_marker(construct, md):
    """A marker kind is a marker **plus content** (LD-134), so an empty one is refused —
    and the refusal names WHICH marker rather than a generic block failure."""
    refusal = _refusal(md)
    assert construct in refusal.detail


def test_ac5_a_refusal_inside_a_block_keeps_its_own_construct_not_a_generic_label():
    """Regression guard for a bug found in self-review: the inline refusal
    (image/bold/link) was being caught while building the enclosing block and re-raised as
    a generic ``block`` refusal, burying the precise construct at the FRONT of the detail
    where a consumer reads it. The precise construct must lead."""
    for md, construct in (
        ("# a heading with an ![img](t)\n", "image"),
        ("- a bullet with **bold**\n", "bold"),
        ("> a quote with a `span`\n", "inline-code"),
        ("| A |\n|---|\n| a cell with ![img](t) |\n", "image"),
    ):
        detail = _refusal(md).detail
        assert detail.startswith(construct), detail
        assert not detail.startswith("block at line")


# =========================================================================== #
# The 50-per-call cap is NOT one of compose()'s own refusals (bug fix: the      #
# cap fires late, in InsertRequest's constructor, as a plain ValueError).       #
# =========================================================================== #

def test_compose_of_fifty_one_top_level_blocks_still_returns_all_of_them():
    """AC3 (pinned, no-behaviour-change): compose() places no ceiling on the number
    of top-level blocks — an early refusal here would break the legitimate
    compose-then-slice-into-batches flow. n=50 and n=51 both compose in full; the
    50-per-call cap is enforced one step later, by ``InsertRequest``."""
    md = "".join(f"p{i}\n\n" for i in range(MAX_CHILDREN_PER_CALL + 1))
    content = compose(md)
    assert len(content) == MAX_CHILDREN_PER_CALL + 1 == 51


def test_the_fifty_per_call_cap_raises_a_plain_value_error_not_a_refused_error():
    """The cap fires at ``InsertRequest`` construction, not inside ``compose()`` — and
    the exception it raises is a plain ``ValueError``, never the compiler's own typed
    ``RefusedError``. Documenting this cap as a ``RefusedError`` (the way every other
    documented cap in this table is) would describe a refusal that does not exist on
    the wire."""
    md = "".join(f"p{i}\n\n" for i in range(MAX_CHILDREN_PER_CALL + 1))
    content = compose(md)  # composes cleanly — no RefusedError
    with pytest.raises(ValueError) as exc:
        InsertRequest(reference=Anchor(quote="q"), position=InsertPosition.AFTER, content=content)
    assert not isinstance(exc.value, RefusedError)
    assert str(MAX_CHILDREN_PER_CALL) in str(exc.value)


def test_ac1_composes_own_docstring_routes_the_caller_to_the_cap():
    """AC1: ``compose()``'s docstring names ``MAX_CHILDREN_PER_CALL``, says the
    top-level count is ``len(compose(...))``, says WHERE the refusal fires
    (``InsertRequest``'s own constructor), and names the exception TYPE — a plain
    ``ValueError``, explicitly NOT the ``RefusedError`` the docstring's existing
    ``:raises RefusedError:`` clause otherwise implies covers every documented cap.
    The value itself is never retyped in prose: it is projected from the constant
    (the same ``<<PLACEHOLDER>>``-replace discipline ``WriteClient._patch_block``'s
    docstring already uses), so a constant move cannot leave a stale number behind."""
    doc = compose.__doc__ or ""
    assert "MAX_CHILDREN_PER_CALL" in doc
    assert str(MAX_CHILDREN_PER_CALL) in doc
    assert "<<MAX_CHILDREN_PER_CALL>>" not in doc, "the placeholder was never substituted"
    assert "len(compose(" in doc, "the docstring never shows the len(...) check"
    assert "InsertRequest" in doc, "the docstring never says WHERE the cap fires"
    assert "ValueError" in doc, "the docstring never names the exception TYPE"
    assert "not a `RefusedError`" in doc or "not a RefusedError" in doc, (
        "the docstring's existing ':raises RefusedError: ... any documented cap' clause is "
        "false for THIS cap and must be disambiguated, not left to imply coverage"
    )


# =========================================================================== #
# AC6 — compose() NEVER writes: no client, no credential, no transport          #
# =========================================================================== #

_COMPOSE_PY = Path(__file__).resolve().parent.parent / "src" / "larkdocio" / "write" / "compose.py"


def _identifiers(tree):
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
    return out


def test_ac6_the_compiler_module_never_touches_a_client_or_a_transport():
    idents = {n.lower() for n in _identifiers(ast.parse(_COMPOSE_PY.read_text(encoding="utf-8")))}
    for forbidden in (
        "client", "writeclient", "urlopen", "request", "socket", "apply",
        "token", "secret", "app_id", "credentials", "post", "http",
    ):
        assert forbidden not in idents, (
            f"compose.py references {forbidden!r} — the compiler produces content and "
            f"must never write"
        )


def test_ac6_the_compiler_imports_only_stdlib_markdown_it_and_larkdocio():
    allowed_roots = {"markdown_it", "larkdocio"}
    tree = ast.parse(_COMPOSE_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            root = name.split(".")[0]
            assert root in allowed_roots or root in {
                "dataclasses", "typing", "re", "enum",
            }, f"compose.py imports {name!r}"


def test_ac6_compose_takes_no_client_argument():
    params = list(inspect.signature(compose).parameters)
    assert params == ["markdown"]


def test_ac6_compose_runs_with_every_credential_stripped_from_the_environment(monkeypatch):
    """AC6, the behavioral half: no credential is consulted. Strip every Lark variable
    and compose a full fragment — it must succeed."""
    for var in (
        "LARK_APP_ID", "LARK_APP_SECRET", "LARK_READ_APP_ID", "LARK_READ_APP_SECRET",
        "LARK_WRITE_APP_ID", "LARK_WRITE_APP_SECRET", "LARKDOCIO_CANARY_DOC",
    ):
        monkeypatch.delenv(var, raising=False)
    assert compose("# H\n\n- a\n\t- b\n\n| A |\n|---|\n| x |\n")


def test_ac6_compose_issues_no_network_call(monkeypatch):
    """Belt-and-braces: poison the socket layer, then compose."""
    import socket

    def _boom(*a, **k):  # pragma: no cover - must never run
        raise AssertionError("compose() opened a socket")

    monkeypatch.setattr(socket.socket, "connect", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)
    assert compose("para\n\n> q\n\n```python\nx\n```\n")


# =========================================================================== #
# AC1/AC6 — compose_insert(): the thin anchor-taking convenience                #
# =========================================================================== #

def test_compose_insert_pairs_the_content_with_an_anchor_and_position():
    request = compose_insert(
        "# H\n\npara\n",
        reference=Anchor(quote="Hello World", breadcrumb=("Intro",)),
        position=InsertPosition.AFTER,
    )
    assert isinstance(request, InsertRequest)
    assert request.reference == Anchor(quote="Hello World", breadcrumb=("Intro",))
    assert request.position is InsertPosition.AFTER
    assert request.content == compose("# H\n\npara\n")


def test_compose_insert_defaults_to_inserting_after_the_reference():
    request = compose_insert("para\n", reference=Anchor(quote="q"))
    assert request.position is InsertPosition.AFTER


def test_compose_insert_of_an_empty_fragment_refuses_rather_than_building_an_empty_insert():
    with pytest.raises(ValueError):
        compose_insert("   \n", reference=Anchor(quote="q"))


def test_the_compiler_is_reachable_from_the_public_top_level():
    """The documented surface call (D-A): ``compose`` / ``compose_insert`` sit at the top
    level beside ``capabilities()`` / ``guide()`` **and** under ``larkdocio.write``, and both
    paths are the same object — the dogfood session's complaint was discoverability."""
    import larkdocio
    from larkdocio.write import compose as write_compose

    assert larkdocio.compose is write_compose
    assert "compose" in larkdocio.__all__ and "compose_insert" in larkdocio.__all__
    assert larkdocio.compose("# H\n")


def test_compose_insert_round_trips_through_json_like_any_request():
    request = compose_insert(
        "- [x] done\n\t- child\n", reference=Anchor(quote="q"),
    )
    assert InsertRequest.from_dict(request.to_dict()) == request
