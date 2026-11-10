"""LD-144 — a merged table's ``<td>`` carries STRUCTURE-PRESERVING HTML.

Dogfood round 2, finding **T14**: a merged table takes the reader's HTML-``<table>``
path, and that path used to render each cell by calling the **Markdown** serializer
and then HTML-escaping the whole result. Inside a raw-HTML ``<td>`` GFM does not
markdown-parse anything, so the consequence was silent, total structure loss:

* a bold run came out as literal ``**bold**`` (renders as neither bold nor asterisks),
* an underline's own ``<u>`` was escaped into visible ``&lt;u&gt;``,
* a divider became a plain ``---`` mid-sentence,
* two lists ran together as one unmarked line of text,
* every paragraph boundary collapsed into a space.

``parse_docx_tree`` on the same cell was fully intact, so this was read-side
serialization only. The fix gives the HTML-table branch its OWN cell serializer that
walks the cell's child NODES and emits real tags.

**Colour stays dropped** — the settled capture-only doctrine (LD-042). AC3 below pins
the *absence* of the highlight so a future change cannot quietly add it.

**Escaping interplay with LD-130.** LD-130 pinned that a raw-HTML ``<td>`` is never
backslash-escaped (a backslash there is VISIBLE text, not an escape). That pin still
holds and is re-asserted here: literal metacharacters inside an HTML cell get
**HTML-entity** treatment where they are ambiguous in HTML (``&``/``<``/``>``, plus
``"`` in an attribute) and are otherwise left completely alone — ``**``, ``#``, ``_``
and backticks are inert in HTML and stay literal, un-backslashed.
"""
import re

import pytest
from builders import cell, page, table
from harness import render
from html_wellformed import (
    assert_wellformed,
    block_content_violations,
    tag_balance_errors,
)

# --------------------------------------------------------------------------- #
# Fixture builders — a merged table whose cell 0 carries arbitrary blocks      #
# --------------------------------------------------------------------------- #


def _p(bid, parent, elements, block_type=2, key="text"):
    return {
        "block_id": bid, "parent_id": parent, "block_type": block_type,
        key: {"elements": list(elements)}, "children": [],
    }


def _run(content, **style):
    el = {"content": content}
    if style:
        el["text_element_style"] = dict(style)
    return {"text_run": el}


def _bullet(bid, parent, content, children=()):
    b = _p(bid, parent, [_run(content)], block_type=12, key="bullet")
    b["children"] = list(children)
    return b


def _ordered(bid, parent, content, children=()):
    b = _p(bid, parent, [_run(content)], block_type=13, key="ordered")
    b["children"] = list(children)
    return b


def _todo(bid, parent, content, done):
    b = _p(bid, parent, [_run(content)], block_type=17, key="todo")
    b["todo"]["style"] = {"done": done}
    return b


def _divider(bid, parent):
    return {"block_id": bid, "parent_id": parent, "block_type": 22,
            "divider": {}, "children": []}


#: A 2x2 merged table: cell 0 anchors a rowspan of 2 (so grid (1,0) is covered and
#: emits nothing) and ``header_row`` is False so cell 0 lands in a ``<td>``.
#:
#: The covered position (1,0) — ``c2`` — is deliberately left **EMPTY** by
#: ``_mt``'s default filler. Every test in this module is about the ANCHOR cell's
#: own serialization (they all read ``_cell0``), and until LD-529 a covered cell's
#: content was discarded, so filling it was invisible. Now it is **absorbed into
#: the anchor's cell**, which would append filler text to every expectation here
#: for no reason. Absorption has its own pins — ``tests/test_merged_cell_absorption.py``
#: and the ``merged_table_gauntlet`` / ``merged_table_covered_cell_image`` goldens.
_ROWSPAN2 = [{"row_span": 2, "col_span": 1}, {"row_span": 1, "col_span": 1},
             {"row_span": 1, "col_span": 1}, {"row_span": 1, "col_span": 1}]


def _mt(cell0_children, *, deeper=(), merge_info=None, col_size=2,
        extra=None, filler=("B", "", "D")):
    """A merged table whose cell 0 carries ``cell0_children`` (block dicts).

    ``deeper`` holds descendants below the cell's direct children (a nested list
    item, say). ``filler`` names the remaining cells' plain text; the default
    leaves the position ``_ROWSPAN2`` covers empty (see that constant's note).
    """
    prop = {"row_size": 2, "merge_info": merge_info or _ROWSPAN2}
    if extra:
        prop.update(extra)
    ids = ["c0"] + [f"c{i + 1}" for i in range(len(filler))]
    blocks = [page("tbl"), table("tbl", "root", col_size, ids, prop)]
    blocks.append(cell("c0", "tbl", [b["block_id"] for b in cell0_children]))
    blocks.extend(cell0_children)
    blocks.extend(deeper)
    for i, txt in enumerate(filler):
        cid = f"c{i + 1}"
        blocks.append(cell(cid, "tbl", [f"{cid}t"]))
        blocks.append(_p(f"{cid}t", cid, [_run(txt)]))
    return blocks


def _headerless(cell0_children, **kw):
    kw.setdefault("extra", {})
    kw["extra"] = {**kw["extra"], "header_row": False}
    return _mt(cell0_children, **kw)


def _cell0(out):
    """The inner markup of the FIRST emitted table cell."""
    assert "<table>" in out, f"expected the HTML-table path:\n{out}"
    m = re.search(r"<t[dh][^>]*>(.*?)</t[dh]>", out, re.DOTALL)
    assert m, f"no cell found in:\n{out}"
    return m.group(1)


def _table_markup(out):
    m = re.search(r"<table>.*?</table>", out, re.DOTALL)
    assert m, f"no <table> in:\n{out}"
    return m.group(0)


_MD_EMPHASIS_MARKERS = ("**", "~~", "`", "__")


# --------------------------------------------------------------------------- #
# AC1 — real tags for every construct                                          #
# --------------------------------------------------------------------------- #

def test_bold_run_in_merged_cell_emits_strong_not_asterisks():
    """The T14 headline: ``**bold**`` inside raw HTML renders as neither."""
    out = render(_headerless([_p("t0", "c0", [_run("bold", bold=True)])]))
    assert "<strong>bold</strong>" in _cell0(out), out
    assert "**" not in _table_markup(out), out


def test_italic_run_in_merged_cell_emits_em():
    out = render(_headerless([_p("t0", "c0", [_run("it", italic=True)])]))
    assert "<em>it</em>" in _cell0(out), out
    assert "_it_" not in out, out


def test_strikethrough_run_in_merged_cell_emits_s():
    out = render(_headerless([_p("t0", "c0", [_run("gone", strikethrough=True)])]))
    assert "<s>gone</s>" in _cell0(out), out
    assert "~~" not in _table_markup(out), out


def test_underline_run_in_merged_cell_emits_a_LIVE_u_tag():
    """Underline was doubly broken: the renderer emitted ``<u>`` and the cell's
    blanket HTML-escape then turned it into visible ``&lt;u&gt;``."""
    out = render(_headerless([_p("t0", "c0", [_run("under", underline=True)])]))
    assert "<u>under</u>" in _cell0(out), out
    assert "&lt;u&gt;" not in out, out


def test_inline_code_run_in_merged_cell_emits_code_tag_not_backticks():
    out = render(_headerless([_p("t0", "c0", [_run("x = 1", inline_code=True)])]))
    assert "<code>x = 1</code>" in _cell0(out), out
    assert "`" not in _table_markup(out), out


def test_nested_emphasis_composes_as_nested_tags():
    out = render(_headerless([
        _p("t0", "c0", [_run("all", bold=True, italic=True,
                             strikethrough=True, underline=True)]),
    ]))
    inner = _cell0(out)
    assert "<strong><em><s><u>all</u></s></em></strong>" in inner, inner
    assert_wellformed(_table_markup(out))


def test_bulleted_list_in_merged_cell_emits_ul_li():
    out = render(_headerless([
        _bullet("b1", "c0", "one"), _bullet("b2", "c0", "two"),
    ]))
    inner = _cell0(out)
    assert "<ul><li>one</li><li>two</li></ul>" in inner, inner
    assert "- one" not in inner, inner


def test_ordered_list_in_merged_cell_emits_ol_li():
    out = render(_headerless([
        _ordered("o1", "c0", "first"), _ordered("o2", "c0", "second"),
    ]))
    inner = _cell0(out)
    assert "<ol><li>first</li><li>second</li></ol>" in inner, inner
    assert "1. first" not in inner, inner


def test_divider_in_merged_cell_emits_hr():
    out = render(_headerless([
        _p("t0", "c0", [_run("above")]), _divider("d", "c0"),
        _p("t1", "c0", [_run("below")]),
    ]))
    inner = _cell0(out)
    assert "<hr/>" in inner, inner
    assert "---" not in inner, f"the divider is still a mid-sentence '---':\n{inner}"


def test_cell_containing_only_a_divider():
    out = render(_headerless([_divider("d", "c0")]))
    assert _cell0(out) == "<hr/>", out
    assert_wellformed(_table_markup(out))


def test_multiple_paragraphs_in_merged_cell_are_separated_not_run_together():
    """The old path collapsed every newline to a space: ``line1 line2``."""
    out = render(_headerless([
        _p("t0", "c0", [_run("line1")]), _p("t1", "c0", [_run("line2")]),
    ]))
    inner = _cell0(out)
    assert "<p>line1</p><p>line2</p>" in inner, inner
    assert "line1 line2" not in inner, inner


def test_two_adjacent_lists_stay_two_lists():
    """T14's "two lists ran together with no markup" — a bulleted list followed by
    an ordered list must produce a ``<ul>`` AND a separate ``<ol>``."""
    out = render(_headerless([
        _bullet("b1", "c0", "b"), _ordered("o1", "c0", "o"),
    ]))
    inner = _cell0(out)
    assert "<ul><li>b</li></ul><ol><li>o</li></ol>" in inner, inner


def test_bullet_list_after_bullet_list_is_ONE_ul():
    """Consecutive items of the SAME kind group into a single list."""
    out = render(_headerless([
        _bullet("b1", "c0", "a"), _bullet("b2", "c0", "b"), _bullet("b3", "c0", "c"),
    ]))
    inner = _cell0(out)
    assert inner.count("<ul>") == 1 and inner.count("</ul>") == 1, inner
    assert inner.count("<li>") == 3, inner


def test_a_bullet_list_and_a_todo_list_are_TWO_uls_not_one():
    """Grouping is by EXACT node type, not by the wrapper tag: bullets and todos
    both wrap in ``<ul>`` yet are two different lists, and folding them into one
    would put a checkbox item inside the bullet list."""
    out = render(_headerless([
        _bullet("b1", "c0", "plain"), _todo("k1", "c0", "task", False),
    ]))
    inner = _cell0(out)
    assert inner.count("<ul>") == 2 and inner.count("</ul>") == 2, inner
    assert inner == ('<ul><li>plain</li></ul>'
                     '<ul><li><input type="checkbox" disabled/> task</li></ul>'), inner


def test_nested_list_nests_a_ul_inside_the_parent_li():
    out = render(_headerless(
        [_bullet("b1", "c0", "outer", children=["b1n"])],
        deeper=[_bullet("b1n", "b1", "inner")],
    ))
    inner = _cell0(out)
    assert "<ul><li>outer<ul><li>inner</li></ul></li></ul>" in inner, inner
    assert_wellformed(_table_markup(out))
    assert "\t" not in inner, f"a Markdown indent tab leaked into HTML:\n{inner}"


def test_two_ordered_runs_split_by_a_bullet_each_restart_at_one():
    """Characterizing the payload truth, so the ``start=`` guard below is honest:
    the handler's ordered-run counter resets on a non-ordered sibling, so each run
    inside a cell really does begin at 1 on the reader path."""
    out = render(_headerless([
        _ordered("o1", "c0", "one"), _bullet("b1", "c0", "break"),
        _ordered("o2", "c0", "two"),
    ]))
    inner = _cell0(out)
    assert inner == "<ol><li>one</li></ol><ul><li>break</li></ul><ol><li>two</li></ol>", inner


def test_an_ordered_run_not_starting_at_one_carries_a_start_attribute():
    """A defensive guard against silent renumbering, reachable from the model API
    (a consumer rendering nodes directly, or any future change to the handler's
    run logic): an ``<ol>`` whose first item is item 3 must SAY so."""
    from larkdocio.model.nodes import (
        OrderedListItemNode, TableCellNode, TableNode, Text,
    )
    from larkdocio.model.renderer import MarkdownRenderer

    cell0 = TableCellNode(children=[
        OrderedListItemNode(order=3, content=[Text("three")]),
        OrderedListItemNode(order=4, content=[Text("four")]),
    ])
    node = TableNode(
        cells=[cell0, TableCellNode(children=[])],
        col_size=2, header_row=False, merges=[(1, 2), (1, 1)],
    )
    out = MarkdownRenderer().render(node)
    assert '<ol start="3"><li>three</li><li>four</li></ol>' in out, out


def test_todo_list_in_merged_cell_emits_real_checkboxes():
    out = render(_headerless([
        _todo("k1", "c0", "done", True), _todo("k2", "c0", "open", False),
    ]))
    inner = _cell0(out)
    assert '<input type="checkbox" checked disabled/>' in inner, inner
    assert '<input type="checkbox" disabled/>' in inner, inner
    assert "[x]" not in inner and "[ ]" not in inner, inner
    assert_wellformed(_table_markup(out))


def test_inline_link_in_merged_cell_emits_an_anchor():
    out = render(_headerless([
        _p("t0", "c0", [{"text_run": {"content": "click",
                                      "text_element_style": {
                                          "link": {"url": "https%3A%2F%2Fexample.com%2Fa"}}}}]),
    ]))
    inner = _cell0(out)
    assert '<a href="https://example.com/a">click</a>' in inner, inner
    assert "](" not in inner, f"an inert Markdown link survived:\n{inner}"


def test_bare_url_in_merged_cell_autolinks_to_an_anchor():
    """The always-on bare-URL pass (LD-054) emitted an INERT ``[url](url)`` inside
    raw HTML. In an HTML cell the autolink must be an ``<a>``."""
    out = render(_headerless([_p("t0", "c0", [_run("see https://example.com/x now")])]))
    inner = _cell0(out)
    assert '<a href="https://example.com/x">https://example.com/x</a>' in inner, inner
    assert "](" not in inner, inner


def test_single_plain_paragraph_cell_stays_bare_phrasing_content():
    """The overwhelmingly common cell — one plain paragraph — emits no ``<p>``
    wrapper, which is both conventional HTML and what keeps every already-shipped
    merged-table golden byte-identical."""
    out = render(_headerless([_p("t0", "c0", [_run("Merged")])]))
    assert '<td rowspan="2">Merged</td>' in out, out
    assert "<p>" not in out, out


def test_THE_LIVE_CELL_SHAPE_a_paragraph_plus_a_trailing_EMPTY_one_stays_bare():
    """Characterizing the real payload, found on the live canary doc: the Lark UI
    leaves a trailing **empty** paragraph inside a human-authored cell, so a cell
    holding one line of text arrives with TWO type-2 children. An empty paragraph
    is not content, so such a cell must stay bare — keying the bare-vs-<p> rule on
    ``len(children)`` instead wrapped every real-world merged cell in a pointless
    ``<p>`` and moved output on documents with no T14 defect at all."""
    out = render(_headerless([
        _p("t0", "c0", [_run("Banana")]),
        _p("t1", "c0", [_run("")]),          # ← the UI's trailing blank line
    ]))
    assert '<td rowspan="2">Banana</td>' in out, out
    assert "<p>" not in out, out


def test_a_cell_of_ONLY_empty_paragraphs_emits_an_empty_cell():
    out = render(_headerless([
        _p("t0", "c0", [_run("")]), _p("t1", "c0", [_run("   ")]),
    ]))
    assert '<td rowspan="2"></td>' in out, out


# --------------------------------------------------------------------------- #
# AC2 — no inert Markdown markers inside the HTML context                      #
# --------------------------------------------------------------------------- #

def test_no_markdown_emphasis_markers_anywhere_in_a_rich_merged_table():
    out = render(_headerless([
        _bullet("b1", "c0", "b"),
        _ordered("o1", "c0", "o"),
        _p("t0", "c0", [_run("bold", bold=True, background_color=1),
                        _run("it", italic=True),
                        _run("st", strikethrough=True),
                        _run("cd", inline_code=True)]),
        _divider("d", "c0"),
    ]))
    markup = _table_markup(out)
    for marker in _MD_EMPHASIS_MARKERS:
        assert marker not in markup, f"inert Markdown marker {marker!r} in:\n{markup}"
    assert "---" not in markup, markup


def test_html_cell_is_still_never_backslash_escaped_LD130_pin_holds():
    """LD-130's reason stands: GFM does not markdown-parse inside an HTML block, so
    a backslash in a ``<td>`` is VISIBLE text. Structure now comes from tags, so no
    escape is needed for it — and none may appear."""
    out = render(_headerless([
        _p("t0", "c0", [_run("# H")]), _p("t1", "c0", [_run("- x")]),
        _p("t2", "c0", [_run("1. y")]), _p("t3", "c0", [_run("| p |")]),
        _p("t4", "c0", [_run("a * b * c")]),
    ]))
    markup = _table_markup(out)
    assert "\\" not in markup, f"escaping leaked into raw HTML cells:\n{markup}"
    # …and the literal metachars survive verbatim (they are inert in HTML).
    assert "<p># H</p>" in markup and "<p>- x</p>" in markup, markup
    assert "<p>a * b * c</p>" in markup, markup


# --------------------------------------------------------------------------- #
# AC3 — COLOUR STAYS DROPPED (settled capture-only doctrine; do NOT reopen)     #
# --------------------------------------------------------------------------- #

def test_highlight_colour_is_ABSENT_from_the_emitted_html_cell():
    """Pinning the doctrine, not a gap: colour is consumed-into-model and
    dropped-at-render (LD-042). The structure-preserving rewrite must NOT sneak a
    style/bgcolor/``<mark>`` into the new tags."""
    out = render(_headerless([
        _p("t0", "c0", [_run("hi", bold=True, background_color=1, text_color=2)]),
    ]))
    markup = _table_markup(out)
    assert "<strong>hi</strong>" in markup, markup
    for forbidden in ("style=", "bgcolor", "<mark", "background", "color"):
        assert forbidden not in markup.lower(), (
            f"colour leaked into the HTML cell via {forbidden!r}:\n{markup}"
        )


def test_the_colour_is_still_CAPTURED_in_the_model_only_the_render_drops_it():
    """The other half of capture-only: the tree path keeps ``background_color``, so
    the drop is a *rendering* choice a future writer can still round-trip."""
    from harness import build_blocks
    from larkdocio.model import StyledText
    from larkdocio.read.config import Config
    from larkdocio.read.parser import Parser

    blocks = _headerless([
        _p("t0", "c0", [_run("hi", bold=True, background_color=1)]),
    ])
    tree = Parser(Config()).parse_docx_tree("root", build_blocks(blocks))

    found = []

    def walk(node):
        for run in getattr(node, "content", None) or []:
            if isinstance(run, StyledText):
                found.append(run)
        for child in (getattr(node, "children", None) or []):
            walk(child)
        for c in (getattr(node, "cells", None) or []):
            walk(c)

    walk(tree)
    assert any(r.background_color == 1 and r.bold for r in found), found


# --------------------------------------------------------------------------- #
# Escaping interplay — HTML entities, no double-escape, no injection            #
# --------------------------------------------------------------------------- #

def test_literal_angle_brackets_and_ampersand_become_entities():
    out = render(_headerless([_p("t0", "c0", [_run("a & b < c > d")])]))
    assert _cell0(out) == "a &amp; b &lt; c &gt; d", out


def test_a_literal_entity_in_the_text_is_escaped_exactly_ONCE():
    """The source text literally contains ``&amp;``. Emitting it verbatim would
    render as ``&``, silently changing the document; escaping the ``&`` once yields
    ``&amp;amp;``, which renders back as the literal ``&amp;`` the author typed."""
    out = render(_headerless([_p("t0", "c0", [_run("literal &amp; entity")])]))
    assert _cell0(out) == "literal &amp;amp; entity", out


def test_html_injection_in_cell_text_is_neutralised():
    out = render(_headerless([
        _p("t0", "c0", [_run("<script>alert(1)</script>")]),
        _p("t1", "c0", [_run("plain")]),
    ]))
    markup = _table_markup(out)
    assert "<script>" not in markup, markup
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in markup, markup
    assert_wellformed(markup)


def test_escaping_composes_with_the_new_tags_no_double_escaping_of_our_own_markup():
    out = render(_headerless([
        _p("t0", "c0", [_run("<b>", bold=True)]),
        _p("t1", "c0", [_run("second")]),
    ]))
    markup = _table_markup(out)
    assert "<strong>&lt;b&gt;</strong>" in markup, markup
    assert "&lt;strong&gt;" not in markup, markup


def test_a_link_url_is_attribute_escaped():
    out = render(_headerless([
        _p("t0", "c0", [{"text_run": {
            "content": "x",
            "text_element_style": {"link": {"url": "https%3A%2F%2Fexample.com%2F%3Fa%3D1%26b%3D2"}},
        }}]),
    ]))
    inner = _cell0(out)
    assert '<a href="https://example.com/?a=1&amp;b=2">x</a>' in inner, inner


def test_a_quote_in_a_link_url_cannot_break_out_of_the_attribute():
    out = render(_headerless([
        _p("t0", "c0", [{"text_run": {
            "content": "x",
            "text_element_style": {"link": {"url": 'https%3A%2F%2Fexample.com%2F%22%3E%3Cb%3E'}},
        }}]),
    ]))
    inner = _cell0(out)
    assert '"><b>' not in inner, f"attribute break-out:\n{inner}"
    assert "&quot;" in inner, inner
    assert_wellformed(_table_markup(out))


# --------------------------------------------------------------------------- #
# AC6 — well-formedness by a real HTML parse, not a string compare              #
# --------------------------------------------------------------------------- #

def test_the_full_round2_repro_cell_is_wellformed_html():
    out = render(_headerless([
        _bullet("b1", "c0", "Bullet one", children=["b1n"]),
        _bullet("b2", "c0", "Bullet two"),
        _ordered("o1", "c0", "Ordered one"),
        _ordered("o2", "c0", "Ordered two"),
        _p("t0", "c0", [_run("A "), _run("bold", bold=True, background_color=1),
                        _run(" tail <x> & more")]),
        _divider("d", "c0"),
    ], deeper=[_bullet("b1n", "b1", "Nested bullet")]))
    markup = _table_markup(out)
    assert not tag_balance_errors(markup), tag_balance_errors(markup)
    assert not block_content_violations(markup), block_content_violations(markup)


def test_the_wellformedness_guard_actually_bites():
    """Red-then-green on the guard itself, so AC6 is not an always-true assertion."""
    assert tag_balance_errors("<td><strong>x</td>")
    assert tag_balance_errors("<td><ul><li>a</ul></li></td>")
    assert block_content_violations("<td>stray<p>block</p></td>")
    assert not tag_balance_errors("<td><ul><li>a</li></ul></td>")
    assert not block_content_violations("<td><p>a</p><p>b</p></td>")
    # A list item legitimately mixes its own text with a nested list.
    assert not block_content_violations("<td><ul><li>a<ul><li>b</li></ul></li></ul></td>")


# --------------------------------------------------------------------------- #
# Amplifier — spans, header rows, and the non-merged path staying untouched     #
# --------------------------------------------------------------------------- #

def test_a_cell_spanning_both_rows_and_columns_keeps_its_rich_content():
    merge_info = [{"row_span": 2, "col_span": 2}, {"row_span": 1, "col_span": 1},
                  {"row_span": 1, "col_span": 1}, {"row_span": 1, "col_span": 1}]
    out = render(_headerless(
        [_bullet("b1", "c0", "a"), _divider("d", "c0")],
        merge_info=merge_info, filler=("B", "C", "D"),
    ))
    m = re.search(r'<td rowspan="2" colspan="2">(.*?)</td>', out, re.DOTALL)
    assert m, out
    assert "<ul><li>a</li></ul><hr/>" in m.group(1), m.group(1)
    assert_wellformed(_table_markup(out))


def test_a_merged_table_WITH_a_header_row_gets_rich_th_content():
    out = render(_mt([
        _p("t0", "c0", [_run("Head", bold=True)]),
        _p("t1", "c0", [_run("sub")]),
    ]))
    m = re.search(r'<th rowspan="2">(.*?)</th>', out, re.DOTALL)
    assert m, out
    assert "<p><strong>Head</strong></p><p>sub</p>" == m.group(1), m.group(1)
    assert "<thead>" in out and "<tbody>" in out, out


def test_the_NON_merged_pipe_table_path_is_byte_unchanged():
    """AC5's other half: the GFM pipe path is untouched — same rich content in an
    UNMERGED table still emits Markdown markers and the ``<br>`` line join."""
    blocks = [
        page("tbl"), table("tbl", "root", 2, ["c0", "c1"]),
        cell("c0", "tbl", ["p0", "p1"]),
        _p("p0", "c0", [_run("bold", bold=True)]),
        _p("p1", "c0", [_run("second")]),
        cell("c1", "tbl", ["p2"]), _p("p2", "c1", [_run("x")]),
    ]
    out = render(blocks)
    assert "<table>" not in out, f"an unmerged table took the HTML path:\n{out}"
    assert "| **bold**<br>second | x |" in out, out


def test_a_string_carriage_cell_is_still_taken_verbatim_and_entity_escaped():
    """The renderer-direct unit path constructs cells as already-rendered strings
    (no nodes to walk). That carriage stays verbatim text — entity-escaped, never
    backslash-escaped, and never re-interpreted as structure."""
    from larkdocio.model.nodes import TableNode
    from larkdocio.model.renderer import MarkdownRenderer

    node = TableNode(
        # idx 2 is COVERED by idx 0's rowspan, so cells 0/1/3 are the emitted ones.
        cells=["# H & <b>\n", "**x**\n", "covered\n", "- d\n"],
        col_size=2, merges=[(2, 1), (1, 1), (1, 1), (1, 1)],
    )
    out = MarkdownRenderer().render(node)
    assert "<table>" in out, out
    assert "\\" not in out, out
    assert "# H &amp; &lt;b&gt;" in out, out
    # A string carriage is TEXT, not a node tree — nothing to promote into tags.
    assert "**x**" in out, out
    assert "- d" in out, out


# --------------------------------------------------------------------------- #
# The HTML-block integrity invariant — the scariest failure mode                 #
# --------------------------------------------------------------------------- #
#
# A BLANK LINE terminates a CommonMark/GFM HTML block. If any cell serializer ever
# emitted one, the <table> would be cut in half: the tail would be re-parsed as
# Markdown and the reader's output would contain a torn, half-escaped table. The
# old path was safe only because it collapsed EVERY newline to a space; the new one
# has to earn that safety per emitter (<br/> for a hard break, &#10; inside <pre>).


def _no_blank_line_inside_table(out):
    markup = _table_markup(out)
    assert "\n\n" not in markup, f"a BLANK LINE would tear the HTML block:\n{markup}"


def test_a_code_block_in_a_merged_cell_keeps_its_lines_without_a_blank_line():
    blocks = _headerless([{
        "block_id": "cd", "parent_id": "c0", "block_type": 14,
        "code": {"elements": [_run("def f():\n\n    return 1")],
                 "style": {"language": 49}},
        "children": [],
    }])
    out = render(blocks)
    inner = _cell0(out)
    assert "<pre><code>" in inner and "</code></pre>" in inner, inner
    assert "&#10;" in inner, inner
    assert "```" not in inner, inner
    _no_blank_line_inside_table(out)


def test_a_quote_and_a_callout_in_a_merged_cell_become_blockquotes():
    quote = {"block_id": "q", "parent_id": "c0", "block_type": 15,
             "quote": {"elements": [_run("quoted")]}, "children": []}
    out = render(_headerless([quote, _p("t1", "c0", [_run("after")])]))
    inner = _cell0(out)
    assert "<blockquote>quoted</blockquote>" in inner, inner
    assert "> quoted" not in inner, inner
    _no_blank_line_inside_table(out)


def test_a_table_nested_in_a_merged_cell_nests_a_real_html_table():
    """A GFM pipe table would be inert inside a ``<td>``, so a nested table becomes
    a nested ``<table>`` whatever its own merge state — and the recursion must not
    leak the outer cell's rendering mode."""
    inner_tbl = table("in", "c0", 2, ["i0", "i1"], {"row_size": 1})
    blocks = _headerless([inner_tbl], deeper=[
        cell("i0", "in", ["i0t"]), _p("i0t", "i0", [_run("A")]),
        cell("i1", "in", ["i1t"]), _p("i1t", "i1", [_run("B")]),
    ])
    out = render(blocks)
    # The OUTER cell holds the nested table, so slice by the outer <td> opener
    # rather than the cell regex (which would stop at the nested table's own </th>).
    markup = out[out.index('<td rowspan="2">'):]
    assert markup.startswith('<td rowspan="2"><table>'), markup
    assert "<th>A</th>" in markup and "<th>B</th>" in markup, markup
    assert "|" not in markup, f"an inert pipe table survived:\n{markup}"
    assert out.count("<table>") == 2, out
    _no_blank_line_inside_table(out)


def test_a_marker_only_block_in_a_merged_cell_falls_back_to_an_escaped_paragraph():
    """The documented residue: a block whose Markdown is a FIXED marker string
    (a file attachment here) has no HTML form of its own, so it degrades to an
    escaped paragraph — well-formed, newline-free, and no worse than before."""
    out = render(_headerless([{
        "block_id": "f", "parent_id": "c0", "block_type": 23,
        "file": {"name": "spec.pdf", "token": "tok1"}, "children": [],
    }, _p("t1", "c0", [_run("after")])]))
    inner = _cell0(out)
    assert "<p>" in inner and "spec.pdf" in inner, inner
    _no_blank_line_inside_table(out)
    assert_wellformed(_table_markup(out))


def test_the_rich_golden_survives_a_real_markdown_parse_as_ONE_html_block():
    """End-to-end with the reference parser the repo already ships (markdown-it-py):
    the reader's output must reach a consumer as one intact ``html_block``, with the
    structure tags inside it untouched."""
    from markdown_it import MarkdownIt

    from harness import FIXTURES_DIR

    md = FIXTURES_DIR.joinpath("merged_table_rich_cell.expected.md").read_text(
        encoding="utf-8")
    tokens = MarkdownIt("commonmark").enable("table").enable("strikethrough").parse(md)
    html_blocks = [t.content for t in tokens if t.type == "html_block"]
    assert len(html_blocks) == 1, [t.type for t in tokens]
    block = html_blocks[0]
    assert block.startswith("<table>") and block.rstrip().endswith("</table>"), block
    for tag in ("<ul>", "<ol>", "<li>", "<strong>", "<hr/>", "<p>"):
        assert tag in block, (tag, block)
    assert "**" not in block and "\\" not in block, block


@pytest.mark.parametrize("children,expected", [
    ([("text", "solo")], "solo"),
    ([("bullet", "only")], "<ul><li>only</li></ul>"),
    ([("ordered", "only")], "<ol><li>only</li></ol>"),
    ([("divider", None)], "<hr/>"),
])
def test_each_construct_ALONE_in_a_cell(children, expected):
    built = []
    for i, (kind, txt) in enumerate(children):
        bid = f"x{i}"
        if kind == "text":
            built.append(_p(bid, "c0", [_run(txt)]))
        elif kind == "bullet":
            built.append(_bullet(bid, "c0", txt))
        elif kind == "ordered":
            built.append(_ordered(bid, "c0", txt))
        else:
            built.append(_divider(bid, "c0"))
    out = render(_headerless(built))
    assert _cell0(out) == expected, out


# --------------------------------------------------------------------------- #
# LD-637 AC2 — the HTML cell's INLINE chain past Text/StyledText               #
#                                                                              #
# The gap, and why reading the corpus BY NODE TYPE could not see it.           #
# ``_html_inline_one`` (``model/renderer.py:1369``) dispatches seven inline    #
# kinds. Everything above pins the first two — ``Text`` and ``StyledText`` —   #
# and the remaining five (``MentionUser``, ``MentionDoc``, ``InlineEquation``, #
# ``UnsupportedInline``, ``RawInline``) were pinned only on the MARKDOWN path, #
# where each already has its own tests. So the corpus looked complete when     #
# read by node type while 29 of ``renderer.py``'s 33 uncovered lines sat in    #
# this branch — and ``_table()`` takes it for ANY merged-cell table, which is  #
# a production shape and not an edge case.                                     #
#                                                                              #
# These are OUTPUT-PRODUCING branches, not refusal fences: each one emits a    #
# different string here than on the Markdown path, and for ``MentionDoc`` the  #
# Markdown form (``[title](url)``) is INERT inside a ``<td>`` — exactly the    #
# T14 class this module exists for. ``test_the_markdown_path_emits_the_INERT_`` #
# ``form_which_is_why_this_branch_exists`` states that contrast directly, so   #
# the pins below cannot be mistaken for duplicates of the Markdown ones.       #
# --------------------------------------------------------------------------- #

def _rich_inline_cell(elements):
    """A merged table whose anchor cell is one paragraph of ``elements``."""
    return render(_headerless([_p("t0", "c0", elements)]))


def test_a_user_mention_in_a_merged_cell_emits_the_raw_id_as_phrasing():
    """Offline-pure: the node keeps the raw open id, so the cell shows ``@ou_…``.
    Name resolution is a download-time pass (LD-053) and does not run here."""
    out = _rich_inline_cell([{"mention_user": {"user_id": "ou_abc"}}])
    assert _cell0(out) == "@ou_abc", out
    assert_wellformed(_table_markup(out))


def test_a_user_mention_whose_id_carries_HTML_METACHARS_is_entity_escaped():
    out = _rich_inline_cell([{"mention_user": {"user_id": "ou_<a>&b"}}])
    assert _cell0(out) == "@ou_&lt;a&gt;&amp;b", out
    assert "\\" not in _table_markup(out), out


def test_a_doc_mention_in_a_merged_cell_emits_a_REAL_ANCHOR():
    """The headline of this branch: a ``<td>`` markdown-parses nothing, so the
    mention has to arrive as a tag."""
    out = _rich_inline_cell([{"mention_doc": {"title": "Spec",
                                              "url": "https://x/y"}}])
    assert _cell0(out) == '<a href="https://x/y">Spec</a>', out
    assert "[Spec]" not in _table_markup(out), out
    assert_wellformed(_table_markup(out))


def test_a_doc_mentions_TITLE_and_URL_are_escaped_on_their_OWN_terms():
    """Title as phrasing content, URL as an attribute — a quote in the URL must
    not break out of ``href``, the same fence the plain-link tests hold."""
    out = _rich_inline_cell([{"mention_doc": {
        "title": 'A & B <spec>', "url": 'https://x/y?q="1"&z=2'}}])
    inner = _cell0(out)
    assert inner == ('<a href="https://x/y?q=&quot;1&quot;&amp;z=2">'
                     'A &amp; B &lt;spec&gt;</a>'), inner
    assert '"><' not in inner, inner
    assert_wellformed(_table_markup(out))


def test_a_doc_mention_with_NO_URL_still_emits_a_wellformed_empty_href():
    """``_html_link`` coerces a missing URL to ``""`` rather than ``None`` — the
    live shape from a mention whose target the reader could not resolve."""
    out = _rich_inline_cell([{"mention_doc": {"title": "Untargeted"}}])
    assert _cell0(out) == '<a href="">Untargeted</a>', out
    assert_wellformed(_table_markup(out))


def test_an_inline_equation_in_a_merged_cell_keeps_its_dollar_delimiters():
    out = _rich_inline_cell([{"equation": {"content": "x^2"}}])
    assert _cell0(out) == "$x^2$", out


def test_an_inline_equations_body_is_ENTITY_escaped_and_never_backslashed():
    """A ``<`` in TeX is ambiguous in HTML and must become an entity; a ``^`` or
    a ``_`` is inert in HTML and stays literal (LD-130's pin)."""
    out = _rich_inline_cell([{"equation": {"content": "a<b & c_1^2\n"}}])
    assert _cell0(out) == "$a&lt;b &amp; c_1^2$", out
    assert "\\" not in _table_markup(out), out


@pytest.mark.parametrize("variant", ["reminder", "file", "inline_block",
                                     "link_preview", "undefined"])
def test_every_UNSUPPORTED_inline_variant_marks_itself_in_a_merged_cell(variant):
    """All five variants the parser can produce reach this branch, and each says
    which one it was — a marker, never a silent drop."""
    out = _rich_inline_cell([{variant: {}}])
    assert _cell0(out) == f"[unsupported inline: {variant}]", out
    assert_wellformed(_table_markup(out))


def test_a_RawInline_in_a_merged_cell_passes_its_markup_through_VERBATIM():
    """``RawInline`` is the one kind in this chain the docx parser no longer
    produces (LD-025 replaced the bridge with typed inlines), so it is driven
    through the node tree — the same renderer-direct carriage
    ``test_a_STRING_cell_carriage_is_still_text_not_structure`` uses. Its markup
    is ALREADY formatted, so it is emitted unescaped."""
    from larkdocio.model.nodes import (
        RawInline, TableCellNode, TableNode, Text, TextNode)
    from larkdocio.model.renderer import MarkdownRenderer

    node = TableNode(
        cells=[TableCellNode(children=[
                   TextNode(content=[RawInline("<u>already formatted</u>")])]),
               TableCellNode(children=[TextNode(content=[Text("B")])])],
        col_size=2, header_row=False, merges=[(2, 1), (1, 1)],
    )
    out = MarkdownRenderer().render(node)
    assert "<table>" in out, out
    assert _cell0(out) == "<u>already formatted</u>", out
    assert "&lt;u&gt;" not in out, out
    assert_wellformed(_table_markup(out))


def test_the_WHOLE_inline_chain_in_ONE_merged_cell_is_wellformed():
    """All five kinds plus ``Text`` and ``StyledText`` in a single ``<td>`` —
    the shape a human-authored merged cell actually has."""
    from larkdocio.model.nodes import (
        InlineEquation, MentionDoc, MentionUser, RawInline, StyledText,
        TableCellNode, TableNode, Text, TextNode, UnsupportedInline)
    from larkdocio.model.renderer import MarkdownRenderer

    inlines = [MentionUser("ou_1"), Text(" "),
               MentionDoc("Spec", "https://x/y"), Text(" "),
               InlineEquation("x^2"), Text(" "),
               UnsupportedInline("file"), Text(" "),
               RawInline("<u>u</u>"), Text(" "),
               StyledText("bold", bold=True)]
    node = TableNode(
        cells=[TableCellNode(children=[TextNode(content=inlines)]),
               TableCellNode(children=[TextNode(content=[Text("B")])])],
        col_size=2, header_row=False, merges=[(2, 1), (1, 1)],
    )
    out = MarkdownRenderer().render(node)
    assert _cell0(out) == ('@ou_1 <a href="https://x/y">Spec</a> $x^2$ '
                           '[unsupported inline: file] <u>u</u> '
                           '<strong>bold</strong>'), _cell0(out)
    markup = _table_markup(out)
    assert not tag_balance_errors(markup), tag_balance_errors(markup)
    assert not block_content_violations(markup), block_content_violations(markup)
    for marker in _MD_EMPHASIS_MARKERS:
        assert marker not in markup, (marker, markup)
    assert "\n" not in _cell0(out), _cell0(out)


def test_the_markdown_path_emits_the_INERT_form_which_is_why_this_branch_exists():
    """The contrast, pinned so the tests above are not read as duplicates of the
    Markdown ones. The SAME cell tree with no merge takes the pipe-table path and
    emits ``[Spec](https://x/y)`` — which inside a raw-HTML ``<td>`` would be
    literal brackets, the T14 loss. Both forms are correct on their own path;
    that they DIFFER is the whole reason the HTML chain needs its own pins."""
    from larkdocio.model.nodes import (
        MentionDoc, TableCellNode, TableNode, Text, TextNode)
    from larkdocio.model.renderer import MarkdownRenderer

    def rendered(merges):
        node = TableNode(
            cells=[TableCellNode(children=[
                       TextNode(content=[MentionDoc("Spec", "https://x/y")])]),
                   TableCellNode(children=[TextNode(content=[Text("B")])])],
            col_size=2, header_row=False, merges=merges)
        return MarkdownRenderer().render(node)

    md = rendered([(1, 1), (1, 1)])
    html = rendered([(2, 1), (1, 1)])
    assert "<table>" not in md and "[Spec](https://x/y)" in md, md
    assert "<table>" in html and "[Spec](" not in html, html
    assert '<a href="https://x/y">Spec</a>' in html, html
