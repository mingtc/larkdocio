"""LD-130 — plain text must NEVER masquerade as Markdown structure.

The reader used to serialize a plain ``TextNode``'s text **verbatim**, so a
paragraph reading ``# Fake H1`` was byte-indistinguishable from the document's
real title. Dogfood finding **F1** (``dev/dogfood/2026-07-27-session/report.md``):
phantom headings/lists/tables poison every doc→Markdown→tool round-trip and, worse,
the heading path a consumer derives for ``Anchor.breadcrumb`` — anchoring edits
against structure that was never in the real tree.

**Every assertion here goes through the reference parser** (the test-only
``markdown-it-py`` dev extra), not through string equality: the contract is not
"the output contains a backslash", it is "the output does not PARSE as structure,
and the literal text survives verbatim". A round-trip through the reference
parser is the only way to state that.

Two invariants are pinned together, because either alone is satisfiable by a
broken renderer:

1. **plain text never becomes structure** (escape enough), and
2. **real structure and real styled runs are untouched** (escape no more).
"""
import json

import pytest

import builders
from harness import FIXTURES_DIR, render

MarkdownIt = pytest.importorskip("markdown_it").MarkdownIt

# The reference parser: CommonMark + the GFM extensions our renderer emits
# (pipe tables, ~~strikethrough~~). Enabling the extensions is deliberate — a
# phantom that only forms under GFM (a table row) must still be caught.
def _md():
    return MarkdownIt("commonmark").enable("table").enable("strikethrough")


#: Token types that mean "a block-level structure started here". A plain
#: paragraph of literal text must produce NONE of these.
_STRUCTURE_OPENS = frozenset({
    "heading_open",
    "bullet_list_open",
    "ordered_list_open",
    "table_open",
    "blockquote_open",
    "hr",
    "fence",
    "code_block",
    "html_block",
})

#: Inline token types that mean "inline markup formed here". A plain paragraph
#: of literal text must produce only text/softbreak children.
_INLINE_MARKUP = frozenset({
    "strong_open",
    "em_open",
    "s_open",
    "code_inline",
    "link_open",
    "html_inline",
})


def _render_fixture(name):
    block_dicts = json.loads(
        (FIXTURES_DIR / f"{name}.input.json").read_text(encoding="utf-8")
    )
    return render(block_dicts)


def _one_paragraph_doc(text):
    """A minimal docx: a page titled ``Doc`` holding ONE plain paragraph."""
    return [builders.page("p"), builders.text_block("p", "root", text)]


def _paragraphs(markdown):
    """Every paragraph in ``markdown`` as ``(literal_text, child_token_types)``.

    ``literal_text`` joins the inline children's content (a ``softbreak`` counts
    as the newline it stands for), so it is the text a consumer READS BACK — the
    round-trip side of the contract.
    """
    out = []
    tokens = _md().parse(markdown)
    for i, tok in enumerate(tokens):
        if tok.type != "paragraph_open":
            continue
        inline = tokens[i + 1]
        kinds = [c.type for c in (inline.children or [])]
        text = "".join(
            "\n" if c.type == "softbreak" else c.content
            for c in (inline.children or [])
        )
        out.append((text, kinds))
    return out


def _structure_tokens(markdown):
    return [t.type for t in _md().parse(markdown) if t.type in _STRUCTURE_OPENS]


# --------------------------------------------------------------------------- #
# AC1 / AC3 — one class per metacharacter, asserted through the reference parser
# --------------------------------------------------------------------------- #

#: The report's own repro set, one entry per structural-ambiguity class, plus the
#: metachar-ONLY paragraphs (a bare ``#`` is an empty ATX heading; a bare ``-`` is
#: an empty list item; ``---`` is a thematic break) and the multi-line shapes that
#: only a two-line paragraph can form (setext underline, a GFM delimiter row).
_PHANTOM_CASES = [
    "# Fake H1",
    "## Fake H2",
    "###### Fake H6",
    "- Apples",
    "* Star",
    "+ Plus",
    "> Quoted",
    "| Fruit | Season |",
    "1. First",
    "9) Ninth",
    "text with **stars** and _score_",
    "a `code` span",
    "a ~~strike~~ run",
    "__bold via underscores__",
    "#",
    "-",
    ">",
    "|",
    "---",
    "***",
    "___",
    "===",
    "水果 — # 假标题 with **粗体** markers",
    "Fake Setext Title\n=====",
    "Fake Setext H2\n---",
    "Fruit | Season\n--|--",
    "| a | b |\n| --- | --- |",
]


@pytest.mark.parametrize("text", _PHANTOM_CASES, ids=[repr(c) for c in _PHANTOM_CASES])
def test_plain_text_never_parses_as_structure_and_round_trips(text):
    """AC1 + AC3: a plain paragraph of ``text`` re-parses as ONE paragraph whose
    literal text is ``text`` — no phantom heading/list/table/quote/hr, and no
    phantom emphasis/code span. The round-trip half also proves the escaping is
    VISUALLY transparent (``\\#`` renders as ``#``)."""
    out = render(_one_paragraph_doc(text))

    # The page title is the ONLY real structure in this document.
    assert _structure_tokens(out) == ["heading_open"], (
        f"plain text {text!r} produced phantom structure; markdown:\n{out!r}"
    )

    paras = _paragraphs(out)
    assert len(paras) == 1, f"expected one paragraph, got {paras!r} from:\n{out!r}"
    literal, kinds = paras[0]
    assert literal == text, f"text did not round-trip; markdown:\n{out!r}"
    assert not (set(kinds) & _INLINE_MARKUP), (
        f"plain text {text!r} produced inline markup {kinds!r}; markdown:\n{out!r}"
    )


def test_report_repro_fixture_has_no_phantom_structure():
    """AC3: the report's exact repro doc — every metachar class in one document —
    yields exactly ONE heading (the real page title) and nothing else structural."""
    out = _render_fixture("metachar_plain_text")
    assert _structure_tokens(out) == ["heading_open"], (
        f"phantom structure in the repro fixture; markdown:\n{out}"
    )
    html = _md().render(out)
    assert "<h1>Scratch Doc</h1>" in html          # the REAL title survives
    assert "<h1>Fake H1</h1>" not in html          # the phantom does not
    for tag in ("<ul>", "<ol>", "<table>", "<blockquote>", "<hr", "<strong>", "<em>", "<code>"):
        assert tag not in html, f"phantom {tag} in:\n{html}"


def test_mid_line_metacharacters_are_left_alone():
    """A metachar that CANNOT start a block (mid-line ``#``/``-``/``*``, a lone
    ``*``, a single intraword ``_``) is NOT escaped — the fix escapes ambiguity,
    it does not carpet-bomb punctuation."""
    text = "Issue #5 costs 5 - 10 dollars, 2 * 3 = 6, snake_case stays"
    out = render(_one_paragraph_doc(text))
    assert "\\" not in out, f"over-escaped an unambiguous metachar:\n{out!r}"
    assert _paragraphs(out) == [(text, ["text"])]


def test_word_leading_hash_is_not_a_heading_and_stays_bare():
    # `#hashtag` / `-Apples` / `1.First` are NOT block markers in CommonMark
    # (no space after the marker), so nothing is escaped.
    for text in ("#hashtag", "-Apples", "1.First", "5.5 rating"):
        out = render(_one_paragraph_doc(text))
        assert "\\" not in out, f"{text!r} over-escaped:\n{out!r}"
        assert _paragraphs(out)[0][0] == text


# --------------------------------------------------------------------------- #
# AC2 — REAL structure is byte-unchanged                                      #
# --------------------------------------------------------------------------- #

def test_real_structure_nodes_are_byte_identical():
    """AC2: real heading / bullet / ordered / todo / quote / table / divider
    output is byte-for-byte what it was before LD-130 — the markers are
    STRUCTURE and are never escaped."""
    from larkdocio.model import (
        BulletListItemNode,
        DividerNode,
        HeadingNode,
        OrderedListItemNode,
        QuoteNode,
        TableNode,
        Text,
        TodoListItemNode,
    )
    from larkdocio.model.renderer import MarkdownRenderer

    r = MarkdownRenderer()
    assert r.render(HeadingNode(level=1, content=[Text("Title")])) == "# Title\n"
    assert r.render(HeadingNode(level=3, content=[Text("Sub")])) == "### Sub\n"
    assert r.render(BulletListItemNode(content=[Text("Apples")])) == "- Apples\n"
    assert r.render(OrderedListItemNode(content=[Text("First")], order=1)) == "1. First\n"
    assert r.render(TodoListItemNode(content=[Text("Task")], done=False)) == "- [ ] Task\n"
    assert r.render(QuoteNode(content=[Text("Quoted")])) == "> Quoted\n\n"
    assert r.render(DividerNode()) == "---\n"
    assert r.render(TableNode(cells=["H1\n", "H2\n", "a\n", "b\n"], col_size=2)) == (
        "| H1 | H2 |\n|---|---|\n| a | b |\n\n"
    )


def test_real_structure_still_parses_as_structure():
    """AC2, the other half: the real nodes still PARSE as their structure (the
    escaping did not neuter a real heading into a paragraph)."""
    out = _render_fixture("metachar_in_real_structure")
    html = _md().render(out)
    assert "<h2>" in html, f"real heading lost:\n{html}"
    assert "<ul>" in html, f"real bullet list lost:\n{html}"
    assert "<ol>" in html, f"real ordered list lost:\n{html}"
    assert "<blockquote>" in html, f"real quote lost:\n{html}"
    assert "<table>" in html, f"real table lost:\n{html}"


def test_metachar_text_inside_real_structure_does_not_nest_phantom_structure():
    """A real bullet whose TEXT is ``# Fake H1`` must stay a plain list item —
    ``- # Fake H1`` would nest an ATX heading INSIDE the item."""
    from larkdocio.model import BulletListItemNode, Text
    from larkdocio.model.renderer import MarkdownRenderer

    out = MarkdownRenderer().render(BulletListItemNode(content=[Text("# Fake H1")]))
    tokens = [t.type for t in _md().parse(out)]
    assert "heading_open" not in tokens, f"phantom heading inside a list item: {out!r}"
    assert "bullet_list_open" in tokens, f"real bullet list lost: {out!r}"
    html = _md().render(out)
    assert "# Fake H1" in html


def test_metachar_text_inside_real_quote_does_not_nest_phantom_structure():
    from larkdocio.model import QuoteNode, Text
    from larkdocio.model.renderer import MarkdownRenderer

    out = MarkdownRenderer().render(QuoteNode(content=[Text("- Apples")]))
    tokens = [t.type for t in _md().parse(out)]
    assert "blockquote_open" in tokens, f"real quote lost: {out!r}"
    assert "bullet_list_open" not in tokens, f"phantom list inside a quote: {out!r}"


# --------------------------------------------------------------------------- #
# AC4 — interplay guards: linkify, real styled runs, table-cell composition    #
# --------------------------------------------------------------------------- #

def test_bare_url_still_linkifies_next_to_a_metachar():
    """AC4(a): the always-on bare-URL pass still fires, and the URL destination
    is never escaped (an underscore in the path must survive verbatim)."""
    text = "see http://x.test/a_b_c and _also_ this"
    out = render(_one_paragraph_doc(text))
    assert "[http://x.test/a_b_c](http://x.test/a_b_c)" in out, out
    html = _md().render(out)
    assert 'href="http://x.test/a_b_c"' in html, html
    assert "<em>" not in html, f"phantom emphasis around the link:\n{html}"


def test_linkify_url_inside_a_leading_metachar_line():
    # A paragraph that BOTH starts with a phantom bullet and carries a URL: the
    # bullet is escaped, the link is still built.
    out = render(_one_paragraph_doc("- see https://x.test/p"))
    html = _md().render(out)
    assert "<ul>" not in html, html
    assert 'href="https://x.test/p"' in html, html


def test_real_styled_runs_are_not_escaped():
    """AC4(b): ``**bold**`` produced by an actual bold run still emits (and
    parses as) real emphasis."""
    from larkdocio.model import StyledText
    from larkdocio.model.renderer import MarkdownRenderer

    r = MarkdownRenderer()
    assert r.render_inline([StyledText("bold", bold=True)]) == "**bold**"
    assert r.render_inline([StyledText("it", italic=True)]) == "_it_"
    assert r.render_inline([StyledText("s", strikethrough=True)]) == "~~s~~"
    assert r.render_inline([StyledText("c", inline_code=True)]) == "`c`"
    html = _md().render(r.render_inline([StyledText("bold", bold=True)]))
    assert "<strong>bold</strong>" in html, html


def test_styled_run_whose_text_itself_contains_markers():
    """A REAL bold run whose literal text contains ``**``: the run's markers stay
    structural, the literal ``**`` inside is escaped, and the result parses as
    ONE bold span whose text keeps the literal asterisks."""
    from larkdocio.model import StyledText
    from larkdocio.model.renderer import MarkdownRenderer

    out = MarkdownRenderer().render_inline([StyledText("a **b** c", bold=True)])
    html = _md().render(out)
    assert html.count("<strong>") == 1, html
    assert "**b**" in html, html


def test_inline_code_content_is_verbatim():
    """A code span's content is VERBATIM — escaping inside it would surface a
    literal backslash to the reader."""
    from larkdocio.model import StyledText
    from larkdocio.model.renderer import MarkdownRenderer

    out = MarkdownRenderer().render_inline([StyledText("# not a heading **x**", inline_code=True)])
    assert out == "`# not a heading **x**`", out
    assert "<code># not a heading **x**</code>" in _md().render(out)


def test_code_fence_content_is_verbatim():
    """A fenced code block is VERBATIM: no escaping may leak into source code."""
    out = _render_fixture("code")
    assert "\\" not in out, f"escaping leaked into a code fence:\n{out}"


def test_table_cell_pipe_escape_is_not_doubled():
    """AC4(c): the table renderer's structural pipe-escape composes with the new
    plain-text escaping — a cell's literal ``|`` is escaped exactly ONCE, so the
    table still parses and the cell text reads back with a literal pipe."""
    out = _render_fixture("metachar_in_real_structure")
    assert "\\\\|" not in out, f"double-escaped pipe:\n{out}"
    html = _md().render(out)
    assert "<table>" in html, html
    assert "| pipe" in html, f"cell pipe text lost:\n{html}"


def test_metachar_only_cells_inside_a_real_table():
    """A real table whose cells are metachar-only text: the table still parses,
    and no cell content becomes structure (a GFM cell is an inline context, so
    line-leading markers are not escaped there — no needless backslash noise)."""
    from larkdocio.model import MarkdownRenderer

    node_cells = ["# H\n", "- x\n", "**b**\n", "| p\n"]
    from larkdocio.model.nodes import TableNode

    out = MarkdownRenderer().render(TableNode(cells=node_cells, col_size=2))
    html = _md().render(out)
    assert "<table>" in html, html
    assert "<h1>" not in html and "<ul>" not in html, html


def test_merged_table_html_cell_content_is_not_escaped():
    """A merged table renders as an HTML ``<table>``, and GFM does NOT markdown-parse
    inside an HTML block — so a backslash there would be VISIBLE text, not an
    escape. The HTML cell path stays raw."""
    from larkdocio.model.nodes import TableNode
    from larkdocio.model.renderer import MarkdownRenderer

    node = TableNode(
        cells=["# H\n", "b\n", "**x**\n", "d\n"],
        col_size=2,
        merges=[(2, 1), (1, 1), (1, 1), (1, 1)],
    )
    out = MarkdownRenderer().render(node)
    assert "<table>" in out, out
    assert "\\" not in out, f"escaping leaked into raw HTML cells:\n{out}"


# --------------------------------------------------------------------------- #
# The LIVE payload shape — a style object with every flag false                #
# --------------------------------------------------------------------------- #

def test_unstyled_styled_run_the_live_payload_shape_is_escaped():
    """The dogfood evidence came from a LIVE doc, where a plain run arrives with a
    ``text_element_style`` object whose every flag is false — so it becomes a
    ``StyledText``, not a bare ``Text``. That path must escape too, or the fix
    would work only on hand-authored fixtures."""
    from harness import build_blocks
    from larkdocio.blocks.text import build_inline
    from larkdocio.read.config import Config
    from larkdocio.read.parser import Parser

    block = {
        "block_id": "t", "parent_id": "doc", "block_type": 2,
        "text": {"elements": [
            {"text_run": {"content": "# Fake H1",
                          "text_element_style": {"bold": False, "italic": False}}}
        ]},
    }
    b = build_blocks([block])[0]
    parser = Parser(Config())
    from larkdocio.model import StyledText
    assert isinstance(build_inline(parser, b.text)[0], StyledText), (
        "payload-shape assumption broken: expected the StyledText path"
    )
    out = parser.parse_docx_content("t", [b])
    assert out == "\\# Fake H1\n", repr(out)
    assert _structure_tokens(out) == []


def test_html_tag_style_policy_still_escapes_plain_content():
    """With ``use_html_tags`` on, the style markers become HTML tags — the literal
    content still follows the same escaping rule."""
    from larkdocio.model import StyledText, Text
    from larkdocio.model.renderer import MarkdownRenderer

    r = MarkdownRenderer(use_html_tags=True)
    assert r.render_inline([StyledText("x", bold=True)]) == "<strong>x</strong>"
    assert r.render_inline([Text("**lit**")]) == r"\*\*lit\*\*"


def test_emphasis_pairing_spans_a_linkified_url():
    """A pair that STRADDLES a bare URL is still escaped: the pairing decision is
    taken over the text outside the URLs, not per URL-split fragment."""
    out = render(_one_paragraph_doc("*em http://x.test/p em*"))
    html = _md().render(out)
    assert "<em>" not in html, f"emphasis formed across the link:\n{html}"
    assert 'href="http://x.test/p"' in html, html


def test_second_line_of_a_multiline_paragraph_is_a_line_start_too():
    """A text run carrying an embedded newline: EVERY line is a block-content line
    start, so a marker on line 2 is escaped as well."""
    out = render(_one_paragraph_doc("intro line\n- second line bullet"))
    assert _structure_tokens(out) == ["heading_open"], out
    assert _paragraphs(out) == [("intro line\n- second line bullet", ["text", "softbreak", "text"])]


# --------------------------------------------------------------------------- #
# The breadcrumb phantom — the reason F1 is Critical and not cosmetic          #
# --------------------------------------------------------------------------- #

def _md_heading_path_of(markdown, target_text):
    """The enclosing heading path a CONSUMER derives from our Markdown for the
    paragraph whose literal text is ``target_text`` — the same outline rule the
    write side's breadcrumb walk uses (pop to level, then push)."""
    tokens = _md().parse(markdown)
    stack = []          # [(level, text)]
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open":
            level = int(tok.tag[1:])
            text = tokens[i + 1].content
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, text))
            i += 3
            continue
        if tok.type == "paragraph_open" and tokens[i + 1].content == target_text:
            return tuple(t for (_lvl, t) in stack)
        i += 1
    raise AssertionError(f"paragraph {target_text!r} not found in:\n{markdown}")


def test_breadcrumb_derived_from_our_markdown_sees_no_phantom_heading():
    """The heading path a consumer computes FROM OUR MARKDOWN must equal the one
    the write side computes from the real typed tree. A phantom heading in the
    Markdown makes a consumer anchor edits against structure that never existed
    (dogfood F1's "why this is not cosmetic")."""
    from larkdocio.read.config import Config
    from larkdocio.read.parser import Parser
    from larkdocio.write.resolve import _collect_blocks, block_plain_text

    blocks = [
        builders.page("h", "fake", "target"),
        builders.heading1("h", "root", "Real Section", []),
        builders.text_block("fake", "root", "# Fake H1"),
        builders.text_block("target", "root", "the target paragraph"),
    ]
    markdown = render(blocks)

    from harness import build_blocks
    root = Parser(Config()).parse_docx_tree("root", build_blocks(blocks))
    tree_paths = {
        block_plain_text(node): path
        for node, path in _collect_blocks(root)
    }

    # The real tree: the target sits under the REAL heading only.
    assert tree_paths["the target paragraph"] == ("Real Section",)
    # And the Markdown a consumer parses agrees — the fake heading is invisible.
    assert _md_heading_path_of(markdown, "the target paragraph") == ("Real Section",)
    # The ONLY headings in the Markdown are the two real ones (the page title and
    # the real H1); the fake one stayed a paragraph.
    tokens = _md().parse(markdown)
    headings = [
        tokens[i + 1].content
        for i, t in enumerate(tokens)
        if t.type == "heading_open"
    ]
    assert headings == ["T", "Real Section"], markdown


# --------------------------------------------------------------------------- #
# The escape_literals sledgehammer is untouched (the wider, opt-in policy)     #
# --------------------------------------------------------------------------- #

def test_escape_literals_option_still_escapes_everything():
    from larkdocio.model import Text
    from larkdocio.model.renderer import MarkdownRenderer

    r = MarkdownRenderer(escape_literals=True)
    assert r.render_inline([Text("a *b* _c_")]) == r"a \*b\* \_c\_"
    assert r.render_inline([Text(r"a\b*c")]) == r"a\\b\*c"
