"""Unit tests for the typed block/document model + Markdown renderer core (LD-024).

These lock the model+renderer contract independent of the parser/registry:
node types are dumb typed data; ONE renderer serializes per node type; the
renderer carries an escape-literals policy option (DEFAULT OFF = raw passthrough,
exactly today's behavior). Byte-identical end-to-end output is proven separately
by the T1 goldens (test_golden.py); these prove the pieces in isolation.
"""
import pytest

from larkdocio.model import (
    CodeNode,
    DividerNode,
    EquationBlockNode,
    HeadingNode,
    InlineEquation,
    MentionDoc,
    MentionUser,
    QuoteNode,
    RawBlock,
    RawInline,
    StyledText,
    TableCellNode,
    TableNode,
    Text,
    TextNode,
    UnsupportedInline,
    MarkdownRenderer,
    Node,
)


# --- Divider ---------------------------------------------------------------

def test_divider_renders_thematic_break():
    assert MarkdownRenderer().render(DividerNode()) == "---\n"


def test_divider_node_is_a_block_node():
    assert isinstance(DividerNode(), Node)


# --- Inline: literal Text + the escape-literals option (Decision Log #3) ----

def test_text_default_escapes_only_structural_ambiguity():
    # UPDATED BY LD-130 (maintainer-consented output change). The default is no longer
    # raw passthrough: literal text that would PARSE as structure is escaped —
    # here the pairable `*`/`_` emphasis runs, which is exactly the phantom the
    # dogfood F1 report found. Everything that cannot form structure is still
    # untouched: `[x](y)` (links are out of LD-130's scope) and a mid-line `#`.
    r = MarkdownRenderer()  # default escape_literals=False
    assert r.render_inline([Text("a *literal* _star_ [x](y) # 1")]) == (
        r"a \*literal\* \_star\_ [x](y) # 1"
    )


def test_text_default_leaves_unpairable_metacharacters_alone():
    # A LONE delimiter run cannot emphasize anything, so it is not escaped —
    # the LD-130 layer escapes ambiguity, it does not carpet-bomb punctuation
    # (that is what the opt-in escape_literals sledgehammer is for).
    r = MarkdownRenderer()
    assert r.render_inline([Text("2 * 3 = 6 and snake_case")]) == "2 * 3 = 6 and snake_case"


def test_text_escape_on_escapes_markdown_metacharacters():
    # The option is implemented HONESTLY: when on, it backslash-escapes the
    # CommonMark punctuation that carries markdown meaning. Nothing in the
    # pipeline flips this on — it is exercised only here.
    r = MarkdownRenderer(escape_literals=True)
    assert r.render_inline([Text("a *b* _c_")]) == r"a \*b\* \_c\_"


def test_text_escape_on_escapes_backslash_first():
    r = MarkdownRenderer(escape_literals=True)
    # A literal backslash must itself be escaped, and before other chars so we
    # never double-escape an inserted backslash.
    assert r.render_inline([Text(r"a\b*c")]) == r"a\\b\*c"


def test_rawinline_is_never_escaped():
    # RawInline carries already-formatted markup (the strangler bridge to the
    # not-yet-migrated text.py inline formatter). It passes through verbatim
    # regardless of the escape option — escaping it would corrupt real markup.
    on = MarkdownRenderer(escape_literals=True)
    off = MarkdownRenderer(escape_literals=False)
    markup = "**bold** [link](http://x/y) `code`"
    assert on.render_inline([RawInline(markup)]) == markup
    assert off.render_inline([RawInline(markup)]) == markup


def test_inline_sequence_concatenates_in_order():
    r = MarkdownRenderer()
    assert r.render_inline([Text("hello "), RawInline("**world**"), Text("!")]) == "hello **world**!"


# --- Quote (type 15) -------------------------------------------------------

def test_quote_single_line():
    assert MarkdownRenderer().render(QuoteNode(content=[Text("A quoted line")])) == "> A quoted line\n\n"


def test_quote_empty_content_renders_nothing():
    # Matches the legacy handler's early-out: empty content -> "".
    assert MarkdownRenderer().render(QuoteNode(content=[])) == ""


def test_quote_multiline_content_prefixes_each_line():
    # A rare inline newline in the content: each non-blank line gets "> ", a
    # blank line becomes a bare ">", exactly as the legacy handler did.
    node = QuoteNode(content=[Text("line one\n\nline two")])
    assert MarkdownRenderer().render(node) == "> line one\n>\n> line two\n\n"


def test_quote_preserves_inline_markup_via_rawinline():
    node = QuoteNode(content=[RawInline("**bold** quote")])
    assert MarkdownRenderer().render(node) == "> **bold** quote\n\n"


# --- Headings (types 3..11) ------------------------------------------------

def test_heading_level_1_no_children():
    node = HeadingNode(level=1, content=[Text("A Heading")], children=[])
    assert MarkdownRenderer().render(node) == "# A Heading\n"


def test_heading_level_9_renders_capped_at_six_hashes():
    """LD-145: the marker is clamped to ``######`` (nine ``#`` is not a heading in
    CommonMark), while ``node.level`` keeps the true 9 for tree consumers. This test
    previously pinned the uncapped ``#########`` emission — i.e. it pinned the defect;
    the full treatment lives in ``tests/test_heading_level_cap.py``."""
    node = HeadingNode(level=9, content=[Text("Heading 9")], children=[])
    assert MarkdownRenderer().render(node) == "###### Heading 9\n"
    assert node.level == 9


def test_heading_with_children_blank_line_separates():
    # Mirrors _handle_heading: heading line, a blank line, then each rendered
    # child followed by a newline. Children are child NODES (R-S2 flip); a
    # RawBlock renders its markup verbatim, standing in for a real child at depth 0.
    node = HeadingNode(level=1, content=[Text("Section")], children=[RawBlock("Body under heading\n")])
    assert MarkdownRenderer().render(node) == "# Section\n\nBody under heading\n\n"


def test_heading_absent_content_is_hash_space_only():
    # content=None models the SDK heading attr being absent: the legacy text
    # handler emitted just "# " with no trailing newline (no text-content call).
    node = HeadingNode(level=1, content=None, children=[])
    assert MarkdownRenderer().render(node) == "# "


def test_heading_present_but_empty_content_emits_trailing_newline():
    # content=[] models the heading attr present with no elements: the legacy
    # text handler returned just "\n", so the line is "# \n".
    node = HeadingNode(level=1, content=[], children=[])
    assert MarkdownRenderer().render(node) == "# \n"


# --- Inline: StyledText / mentions / inline equation / unsupported (LD-025) --

def test_styledtext_no_style_is_bare_content():
    assert MarkdownRenderer().render_inline([StyledText("x")]) == "x"


def test_styledtext_markdown_markers_default():
    r = MarkdownRenderer()  # use_html_tags default OFF
    assert r.render_inline([StyledText("x", bold=True)]) == "**x**"
    assert r.render_inline([StyledText("x", italic=True)]) == "_x_"
    assert r.render_inline([StyledText("x", strikethrough=True)]) == "~~x~~"
    assert r.render_inline([StyledText("x", underline=True)]) == "<u>x</u>"
    assert r.render_inline([StyledText("x", inline_code=True)]) == "`x`"


def test_styledtext_html_tags_when_enabled():
    r = MarkdownRenderer(use_html_tags=True)
    assert r.render_inline([StyledText("x", bold=True)]) == "<strong>x</strong>"
    assert r.render_inline([StyledText("x", italic=True)]) == "<em>x</em>"
    assert r.render_inline([StyledText("x", strikethrough=True)]) == "<del>x</del>"
    # Underline is the HTML <u> wrapper regardless of the flag.
    assert r.render_inline([StyledText("x", underline=True)]) == "<u>x</u>"


def test_styledtext_link_wraps_outermost():
    r = MarkdownRenderer()
    assert r.render_inline([StyledText("x", bold=True, link_url="u")]) == "[**x**](u)"
    # code wraps inside a link too.
    assert r.render_inline([StyledText("x", inline_code=True, link_url="u")]) == "[`x`](u)"


def test_styledtext_empty_url_link_still_wraps():
    # link_url="" (link present, empty URL) is distinct from None (no link).
    assert MarkdownRenderer().render_inline([StyledText("x", link_url="")]) == "[x]()"
    assert MarkdownRenderer().render_inline([StyledText("x", link_url=None)]) == "x"


def test_styledtext_content_escaped_only_when_option_on():
    # Content is literal: escape policy applies to it (markers stay structural).
    off = MarkdownRenderer()
    on = MarkdownRenderer(escape_literals=True)
    assert off.render_inline([StyledText("a*b", bold=True)]) == "**a*b**"
    assert on.render_inline([StyledText("a*b", bold=True)]) == r"**a\*b**"


def test_mention_user_renders_at_id():
    assert MarkdownRenderer().render_inline([MentionUser("ou_1")]) == "@ou_1"


def test_mention_doc_renders_markdown_link():
    assert MarkdownRenderer().render_inline([MentionDoc("T", "http://x/y")]) == "[T](http://x/y)"


def test_inline_equation_renders_single_dollar():
    assert MarkdownRenderer().render_inline([InlineEquation("a^2")]) == "$a^2$"


def test_unsupported_inline_renders_marker():
    assert MarkdownRenderer().render_inline([UnsupportedInline("file")]) == "[unsupported inline: file]"


# --- Block: TextNode (2) / CodeNode (14) / EquationBlockNode (16) (LD-025) ---

def test_text_block_present_content_adds_trailing_newline():
    assert MarkdownRenderer().render(TextNode(content=[Text("hello")])) == "hello\n"


def test_text_block_present_but_empty_is_just_newline():
    assert MarkdownRenderer().render(TextNode(content=[])) == "\n"


def test_text_block_absent_content_renders_nothing():
    # content=None models the SDK text attr being absent (legacy emitted "").
    assert MarkdownRenderer().render(TextNode(content=None)) == ""


def test_code_block_fences_with_language():
    node = CodeNode(lang="python", content=[Text("print('hi')")])
    assert MarkdownRenderer().render(node) == "```python\nprint('hi')\n```\n"


def test_code_block_no_language_emits_bare_fence():
    node = CodeNode(lang="", content=[Text("plain")])
    assert MarkdownRenderer().render(node) == "```\nplain\n```\n"


def test_code_block_does_not_strip_the_body():
    # LD-146: REWRITTEN — this test used to assert the defect. It read
    #     "The body is stripped exactly as the legacy handler did."
    #     assert MarkdownRenderer().render(node) == "```\nx\n```\n"
    # i.e. it pinned the whole-body ``.strip()`` inherited from the seed script as
    # though it were a decision, which is part of why the corruption survived to a
    # second dogfood session (report T9). Code-block content is VERBATIM by contract
    # (the read-completeness spec), so the body is emitted byte-for-byte — see
    # tests/test_code_fence_verbatim.py for the full whitespace-torture property.
    node = CodeNode(lang="", content=[Text("  x  ")])
    assert MarkdownRenderer().render(node) == "```\n  x  \n```\n"


def test_equation_block_fences_once():
    assert MarkdownRenderer().render(EquationBlockNode(content="e=mc^2")) == "$$\ne=mc^2\n$$\n"


# --- Table / TableCell (types 31 / 32) — LD-027 -----------------------------

def test_table_cell_concatenates_child_strings():
    assert MarkdownRenderer().render(TableCellNode(children=["a\n", "b\n"])) == "a\nb\n"


def test_table_empty_cells_renders_nothing():
    # Byte-identical to the legacy handler's `if not b.children: return ""`.
    assert MarkdownRenderer().render(TableNode(cells=[])) == ""


def test_table_markdown_header_promotion():
    node = TableNode(cells=["H1\n", "H2\n", "a\n", "b\n"], col_size=2)
    assert MarkdownRenderer().render(node) == "| H1 | H2 |\n|---|---|\n| a | b |\n\n"


def test_table_pipe_in_cell_escaped_by_output_layer_regardless_of_escape_policy():
    # The cell pipe-escape is table STRUCTURE escaping owned by the output layer,
    # distinct from (and unaffected by) the escape-literals policy — which stays
    # DEFAULT OFF (Decision Log #3 / LD-027 AC6). It must fire either way.
    node = TableNode(cells=["a|b\n", "x\n"], col_size=2)
    assert r"a\|b" in MarkdownRenderer().render(node)               # default OFF
    assert r"a\|b" in MarkdownRenderer(escape_literals=True).render(node)


def test_table_header_row_false_emits_empty_header():
    node = TableNode(cells=["a\n", "b\n"], col_size=2, header_row=False)
    out = MarkdownRenderer().render(node)
    lines = out.splitlines()
    assert lines[0] == "|  |  |"                 # empty header row, width 2
    assert set(lines[1].replace("|", "")) <= {"-"}  # delimiter
    assert "| a | b |" in out                    # first data row NOT promoted


def test_table_ragged_final_row_padded():
    node = TableNode(cells=["A\n", "B\n", "C\n"], col_size=2)
    out = MarkdownRenderer().render(node)
    last = [ln for ln in out.splitlines() if ln.startswith("|")][-1]
    assert last == "| C |  |"


def test_table_merged_emits_html_with_spans_and_escaping():
    # A cell spanning 2 rows takes the HTML path; & < > are HTML-escaped; the
    # header row uses <th>, the body <td>.
    #
    # LD-529 (was: `<th rowspan="2">a &amp; b</th>`, with cell "x" dropped) — the
    # anchor covers grid (1,0), so cell "x" is ABSORBED into the anchor's <th>
    # after its own content. This is the renderer-direct path, where a cell is a
    # bare already-rendered `str` rather than a node tree: such a cell is phrasing
    # content, so the join is `<br/>`. The escaping contract is unchanged and is
    # still what this test is about.
    node = TableNode(
        cells=["a & b\n", "top\n", "x\n", "bot\n"],
        col_size=2,
        merges=[(2, 1), (1, 1), (1, 1), (1, 1)],
    )
    out = MarkdownRenderer().render(node)
    assert out.startswith("<table>\n<thead>")
    assert '<th rowspan="2">a &amp; b<br/>x</th>' in out
    assert "<th>top</th>" in out
    assert "<td>bot</td>" in out
    assert out.endswith("</table>\n\n")


# --- Renderer contract -----------------------------------------------------

def test_renderer_rejects_unknown_node_type():
    class Bogus(Node):
        pass

    with pytest.raises(TypeError):
        MarkdownRenderer().render(Bogus())


def test_nodes_are_dumb_data_no_renderer_import():
    # Nodes must not import the renderer (reusable model; nodes are dumb typed
    # data). Assert the node module's source never references the renderer.
    import inspect
    import larkdocio.model.nodes as nodes_mod

    src = inspect.getsource(nodes_mod)
    assert "renderer" not in src.lower(), "node definitions must not reference the renderer"
    assert "MarkdownRenderer" not in src


# --- Block-dispatch table (LD-085) -----------------------------------------
#
# render() dispatches a block node to its serializer via an exact-type
# ``{type: bound_method}`` table (converted from the prior ~73-line isinstance
# chain). These pin that table's contract: it must cover EVERY block node type,
# and exact-type dispatch is only equivalent to the old isinstance chain because
# every block Node is a DIRECT leaf (no Node-extends-Node subclass shadowing).


def _all_block_node_types():
    """Every concrete block Node subclass DEFINED IN THE MODEL module.

    Walks ``Node.__subclasses__()`` transitively and keeps only classes declared
    in ``larkdocio.model.nodes`` — so a test-local ``class Bogus(Node)`` (defined
    in this file for the unknown-type test) is deliberately excluded.
    """
    found = set()
    stack = list(Node.__subclasses__())
    while stack:
        cls = stack.pop()
        stack.extend(cls.__subclasses__())
        if cls.__module__ == "larkdocio.model.nodes":
            found.add(cls)
    return found


def test_dispatch_table_keys_are_exactly_the_block_node_types():
    # The dispatch table must map EXACTLY the set of block node types — no type
    # left unregistered (would silently hit the TypeError fallback under
    # exact-type dispatch) and no stray key. This is the binding guard for the
    # isinstance-chain -> lookup-table conversion.
    dispatch_keys = set(MarkdownRenderer()._dispatch)
    node_types = _all_block_node_types()
    unregistered = {c.__name__ for c in node_types - dispatch_keys}
    stray = {c.__name__ for c in dispatch_keys - node_types}
    assert not unregistered, f"block node types with no serializer registered: {sorted(unregistered)}"
    assert not stray, f"dispatch keys that are not block node types: {sorted(stray)}"


def test_dispatch_is_by_exact_type_not_isinstance():
    # Exact-type dispatch: every key is a type and each entry is a bound method
    # accepting the uniform (node, depth) signature. A representative multi-type
    # arm (the three agenda wrappers) all resolve to the ONE transparent
    # serializer, exactly as the old ``isinstance(node, (Agenda*, ...))`` arm did.
    from larkdocio.model.nodes import (
        AgendaItemContentNode,
        AgendaItemNode,
        AgendaNode,
    )

    r = MarkdownRenderer()
    transparent = {r._dispatch[AgendaNode], r._dispatch[AgendaItemNode], r._dispatch[AgendaItemContentNode]}
    assert len(transparent) == 1, "the three agenda wrappers must share ONE serializer"
    # Every registered serializer accepts (node, depth) — call each agenda
    # wrapper through render() with a non-zero depth without error.
    assert r.render(AgendaNode(children=[]), 3) == ""


def test_block_nodes_are_direct_node_leaves():
    # LD-085 carveout: exact-type dispatch equals the old isinstance chain ONLY
    # because every block Node is a DIRECT Node leaf — no Node subclass extends
    # another Node, so no node ever relied on matching a BASE-class arm. If a
    # future type grows a Node subclass, exact-type dispatch would silently miss
    # it (hitting the TypeError fallback) — this reddens to force a conscious
    # registration of the new subclass.
    for cls in _all_block_node_types():
        assert cls.__bases__ == (Node,), (
            f"{cls.__name__} bases={cls.__bases__}: not a direct Node leaf — "
            "exact-type dispatch could shadow it; register it explicitly"
        )


# --------------------------------------------------------------------------- #
# THE FULL STYLE-COMBINATION SWEEP — re-homed here by LD-650.                   #
#                                                                              #
# It used to live in a routing-emphasis test module, which retired with the     #
# body-sniffing router it guarded. Its 70 parametrized cases were driving       #
# MarkdownRenderer._styled over EVERY boolean style field of StyledText in BOTH #
# use_html_tags states — the only place in the suite that did — and asserting a #
# routing outcome about the result. The routing half is gone; the sweep is not, #
# because "what does _styled emit for each of the 64 combinations" is a         #
# renderer question that outlives whoever was reading the answer.               #
#                                                                              #
# Retained verbatim from it: the DERIVED enumeration (the flags are read off    #
# the dataclass, so a new boolean style field joins by existing rather than by  #
# being remembered), both use_html_tags states, and the red proof through the   #
# same enumeration the live fence uses.                                        #
# --------------------------------------------------------------------------- #

import dataclasses
import itertools


def style_flags(node_cls=StyledText):
    """The boolean style fields of a ``StyledText``-shaped node — READ off the dataclass.

    Derived, not restated: a new emphasis flag on :class:`StyledText` joins this enumeration by
    existing, which is what makes the coverage test below a real fence rather than a table of
    strings someone has to remember to extend.
    """
    return tuple(
        f.name for f in dataclasses.fields(node_cls) if isinstance(f.default, bool)
    )


#: The marker pair each flag contributes, per ``use_html_tags`` state — the ONE restatement in
#: this sweep, and it is held against the renderer by the arms below in both directions (a flag
#: with no entry reddens the completeness arm; an entry whose markers the renderer does not
#: emit reddens the sweep).
STYLE_MARKERS = {
    "bold": {False: ("**", "**"), True: ("<strong>", "</strong>")},
    "italic": {False: ("_", "_"), True: ("<em>", "</em>")},
    "strikethrough": {False: ("~~", "~~"), True: ("<del>", "</del>")},
    "underline": {False: ("<u>", "</u>"), True: ("<u>", "</u>")},
    "inline_code": {False: ("`", "`"), True: ("`", "`")},
}


def emitted_style_spellings(node_cls=StyledText, renderer_cls=MarkdownRenderer,
                            content="Domain"):
    """Every spelling the RENDERER can emit for one literal, over the full flag product.

    Yields ``(case_id, flags_on, rendered)`` across both ``use_html_tags`` states — so bold is
    covered as ``**x**`` and as ``<strong>x</strong>``, and nesting orders like
    ``` `**_x_**` ``` come out of the composition itself rather than being imagined here.
    """
    flags = style_flags(node_cls)
    for use_html_tags in (False, True):
        renderer = renderer_cls(use_html_tags=use_html_tags)
        for combo in itertools.product((False, True), repeat=len(flags)):
            kwargs = dict(zip(flags, combo))
            on = tuple(name for name, value in kwargs.items() if value)
            case_id = ("html" if use_html_tags else "md") + "-" + "+".join(on or ("plain",))
            yield (case_id, use_html_tags, on,
                   renderer._styled(node_cls(content=content, **kwargs)))


STYLE_SWEEP = list(emitted_style_spellings())


def test_the_style_enumeration_is_read_off_the_dataclass_and_is_not_empty():
    """A derivation that silently read nothing would green every case below it."""
    assert style_flags() == (
        "bold",
        "italic",
        "strikethrough",
        "underline",
        "inline_code",
    ), "the boolean style fields of StyledText changed — the coverage below follows them"
    assert len(STYLE_SWEEP) == 2 * 2 ** len(style_flags())


def test_every_style_flag_has_a_declared_marker_pair():
    """The completeness direction: a new boolean field with no entry in STYLE_MARKERS makes
    the sweep below silently stop checking it."""
    assert set(style_flags()) == set(STYLE_MARKERS)


@pytest.mark.parametrize(
    "use_html_tags, flags_on, rendered",
    [(h, f, r) for _i, h, f, r in STYLE_SWEEP],
    ids=[i for i, _h, _f, _r in STYLE_SWEEP],
)
def test_every_combination_the_renderer_can_emit_wraps_the_content_it_was_given(
    use_html_tags, flags_on, rendered
):
    """The fence. Every ENABLED flag contributes its marker pair, no DISABLED flag's marker
    leaks in, and the literal survives in the middle whatever the stack around it."""
    assert "Domain" in rendered
    for flag in flags_on:
        opener, closer = STYLE_MARKERS[flag][use_html_tags]
        assert opener in rendered and closer in rendered, (flag, rendered)
    for flag in style_flags():
        if flag in flags_on:
            continue
        opener, _closer = STYLE_MARKERS[flag][use_html_tags]
        if any(opener in STYLE_MARKERS[on][use_html_tags][0] or
               STYLE_MARKERS[on][use_html_tags][0] in opener for on in flags_on):
            continue  # `_` inside `<em>`-shaped siblings etc. — not a leak
        assert opener not in rendered, (flag, rendered)
    assert rendered.strip() != "" and rendered != "Domain" or not flags_on


@dataclasses.dataclass
class _HighlightedText(StyledText):
    """A hypothetical future style flag."""

    highlight: bool = False


class _HighlightRenderer(MarkdownRenderer):
    """A hypothetical future ``_styled`` branch: ``==x==`` around the whole stack."""

    def _styled(self, n, **kwargs):
        out = super()._styled(n, **kwargs)
        if getattr(n, "highlight", False):
            out = f"=={out}=="
        return out


def test_the_sweep_BITES_on_a_marker_branch_it_does_not_know_about():
    """Red proof, through the SAME enumeration the live fence uses.

    A renderer that grew a ``==`` branch driven by a new ``StyledText`` boolean is picked up by
    ``style_flags``/``emitted_style_spellings`` with no edit here — the new flag has no
    STYLE_MARKERS entry, so the completeness arm reddens, and the emitted spelling really does
    differ. *If someone adds a marker branch to ``_styled``, does this go red?* Yes, both ways.
    """
    assert "highlight" in style_flags(_HighlightedText)
    assert "highlight" not in STYLE_MARKERS, (
        "the completeness arm above is what reddens for a new flag; it must not be pre-satisfied"
    )
    cases = list(emitted_style_spellings(_HighlightedText, _HighlightRenderer))
    marked = [case_id for case_id, _h, on, rendered in cases
              if "highlight" in on and rendered.startswith("==")]
    assert len(marked) == len(cases) // 2, marked
    assert not [r for _i, _h, on, r in cases if "highlight" not in on and r.startswith("==")]
