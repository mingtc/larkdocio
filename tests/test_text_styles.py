"""Behavioral tests for inline text element rendering (core/blocks/text.py).

Covers style stacking (bold + link must keep both), mention_user rendering,
and visible markers for currently-dropped inline variants.
"""
from harness import build_blocks, render

from larkdocio.read.config import Config, OutputConfig
from larkdocio.read.parser import Parser


def _text_block(elements):
    return [{
        "block_id": "t",
        "parent_id": "doc",
        "block_type": 2,
        "text": {"elements": elements},
        "children": [],
    }]


def _render_html(block_dicts):
    """Render block dicts with ``use_html_tags`` ON (the styled-run HTML path).

    Mirrors ``harness.render`` but with a custom Config; takes the same
    ``_text_block([...])`` block-dict list the other tests build.
    """
    blocks = build_blocks(block_dicts)
    cfg = Config(output=OutputConfig(use_html_tags=True))
    return Parser(cfg).parse_docx_content(block_dicts[0]["block_id"], blocks)


def test_bold_hyperlink_keeps_bold_and_link():
    blocks = _text_block([
        {"text_run": {
            "content": "click me",
            "text_element_style": {
                "bold": True,
                "link": {"url": "https%3A%2F%2Fexample.com"},
            },
        }},
    ])
    out = render(blocks, doc_id="t")
    # Both bold markers and the link must survive (bold nested inside the link
    # is valid Markdown that keeps both).
    assert "[**click me**](https://example.com)" in out, f"bold link lost: {out!r}"


def test_inline_code_with_link_keeps_link():
    blocks = _text_block([
        {"text_run": {
            "content": "code",
            "text_element_style": {
                "inline_code": True,
                "link": {"url": "https%3A%2F%2Fexample.com"},
            },
        }},
    ])
    out = render(blocks, doc_id="t")
    assert "`code`" in out, f"inline code lost: {out!r}"
    assert "example.com" in out, f"link lost: {out!r}"


def test_mention_user_rendered_with_at():
    blocks = _text_block([
        {"mention_user": {"user_id": "ou_abc123"}},
    ])
    out = render(blocks, doc_id="t")
    assert "@ou_abc123" in out, f"mention_user not rendered as @id: {out!r}"


def test_unknown_inline_variant_emits_visible_marker():
    blocks = _text_block([
        {"reminder": {"create_user_id": "ou_x"}},
    ])
    out = render(blocks, doc_id="t")
    assert "reminder" in out.lower(), f"reminder silently dropped: {out!r}"


# ---------------------------------------------------------------------------
# LD-013 — inline-style matrix: pin each marker + stacking.
#
# One test per inline marker asserting the *exact* Markdown wrapper the reader
# emits today, against real deserialized SDK payloads. These pin behavior so a
# marker regression reddens the suite. In particular the italic (`_`) and
# strikethrough (`~~`) assertions kill the two surviving mutation probes from
# assessment § 3.3 (italic `_`->`*`, strikethrough `~~`->`~`): mutating either
# marker in blocks/text.py flips these assertions red.
# ---------------------------------------------------------------------------


def _styled(content, style):
    return {"text_run": {"content": content, "text_element_style": style}}


def test_bold_marker_is_double_asterisk():
    out = render(_text_block([_styled("x", {"bold": True})]), doc_id="t")
    assert "**x**" in out, f"bold marker not **: {out!r}"


def test_italic_marker_is_underscore():
    # Kills the italic mutant: `_`->`*` in blocks/text.py flips this red.
    out = render(_text_block([_styled("x", {"italic": True})]), doc_id="t")
    assert "_x_" in out, f"italic marker not _: {out!r}"
    # Guard against the mutant's output (`*x*`), which would otherwise sneak
    # past a substring check inside a bolded run.
    assert "*x*" not in out, f"italic emitted as * (mutant): {out!r}"


def test_strikethrough_marker_is_double_tilde():
    # Kills the strikethrough mutant: `~~`->`~` in blocks/text.py flips this red.
    out = render(_text_block([_styled("x", {"strikethrough": True})]), doc_id="t")
    assert "~~x~~" in out, f"strikethrough marker not ~~: {out!r}"


def test_inline_code_marker_is_backtick():
    out = render(_text_block([_styled("x", {"inline_code": True})]), doc_id="t")
    assert "`x`" in out, f"inline code marker not backtick: {out!r}"


def test_underline_marker_is_html_u_tag():
    out = render(_text_block([_styled("x", {"underline": True})]), doc_id="t")
    assert "<u>x</u>" in out, f"underline marker not <u>: {out!r}"


def test_link_marker_is_markdown_link():
    out = render(
        _text_block([_styled("x", {"link": {"url": "https%3A%2F%2Fexample.com"}})]),
        doc_id="t",
    )
    assert "[x](https://example.com)" in out, f"link marker wrong: {out!r}"


def test_inline_equation_marker_is_single_dollar():
    out = render(_text_block([{"equation": {"content": "a^2+b^2"}}]), doc_id="t")
    assert "$a^2+b^2$" in out, f"inline equation not $...$: {out!r}"


# --- Stacking order: multiple styles on one run must nest deterministically ---


def test_stacking_bold_italic_nests_italic_inside_bold():
    out = render(
        _text_block([_styled("x", {"bold": True, "italic": True})]), doc_id="t"
    )
    assert "**_x_**" in out, f"bold+italic stacking wrong: {out!r}"


def test_stacking_strike_code_wraps_strike_in_code():
    out = render(
        _text_block([_styled("x", {"strikethrough": True, "inline_code": True})]),
        doc_id="t",
    )
    assert "`~~x~~`" in out, f"strike+code stacking wrong: {out!r}"


def test_stacking_bold_link_nests_bold_inside_link():
    out = render(
        _text_block([_styled("x", {
            "bold": True,
            "link": {"url": "https%3A%2F%2Fexample.com"},
        })]),
        doc_id="t",
    )
    assert "[**x**](https://example.com)" in out, f"bold+link stacking wrong: {out!r}"


# ---------------------------------------------------------------------------
# LD-013 (Decision Log #2) — the KNOWN-UNFAITHFUL pin,
# RESOLVED BY LD-130.
#
# These two tests used to CHARACTERIZE the gap: literal Markdown metacharacters
# in text-run content were emitted RAW (only table pipes were escaped), so a
# hand-typed "- item" paragraph emitted a real list item. Dogfood F1 found the
# consequence (phantom structure poisons breadcrumb anchoring) and LD-130 closed
# it: the renderer now escapes exactly the STRUCTURAL AMBIGUITY. The tests are
# kept — inverted — as the regression pins for that fix, because the interesting
# half is what is STILL not escaped.
# ---------------------------------------------------------------------------


def test_unambiguous_inline_metachars_still_emitted_raw():
    # Nothing here can form structure: `a*b` is a lone `*` run (unpairable),
    # `b_c` is an INTRAWORD underscore (CommonMark forbids intraword `_`
    # emphasis), and `#`/`>` are mid-line. All stay bare — LD-130 escapes
    # ambiguity, not punctuation.
    out = render(_text_block([_styled("a*b_c#d>e", {})]), doc_id="t")
    assert "a*b_c#d>e" in out, f"inline literals were altered: {out!r}"
    assert "\\" not in out, f"over-escaped an unambiguous metachar: {out!r}"


def test_leading_dash_is_escaped_so_it_stays_a_paragraph():
    # LD-130 (was test_leading_dash_emitted_raw_KNOWN_UNFAITHFUL): a leading
    # "- " in PLAIN content used to emit a real Markdown list item. It is now
    # escaped, so the paragraph stays a paragraph and the text still READS as
    # "- item" in any Markdown viewer.
    out = render(_text_block([_styled("- item", {})]), doc_id="t")
    assert "\\- item" in out, f"leading dash not escaped: {out!r}"


# ---------------------------------------------------------------------------
# LD-025 — element-stacking SUFFIX composition.
#
# The mutation baseline (dev/mutation-baseline-2026-07-24.md § net-gaps #3)
# flagged the stacking-suffix residue: mutating an inner style's suffix
# composition `suffix = "</em>" + suffix` (drop the `+ suffix`) SURVIVED because
# no test stacked styles in the HTML-tag branch, and several markdown stack
# orders were unexercised. When 2+ styles stack, each inner style's closing
# marker must be PREPENDED to the accumulated suffix so the wrappers nest
# (`<strong><em>x</em></strong>`, not `<strong><em>x</em>`). These tests pin the
# exact nesting for the less-common stack orders in BOTH the markdown and the
# HTML-tag branches; dropping the `+ suffix` on italic/strike/underline reddens
# them (RED-under-mutant → GREEN). Bold is always outermost (its suffix is
# composed against an empty accumulator) so its `+ suffix` mutant is equivalent.
# ---------------------------------------------------------------------------


def test_stacking_bold_strike_nests_strike_inside_bold():
    out = render(_text_block([_styled("x", {"bold": True, "strikethrough": True})]), doc_id="t")
    assert "**~~x~~**" in out, f"bold+strike stacking wrong: {out!r}"


def test_stacking_bold_underline_nests_underline_inside_bold():
    out = render(_text_block([_styled("x", {"bold": True, "underline": True})]), doc_id="t")
    assert "**<u>x</u>**" in out, f"bold+underline stacking wrong: {out!r}"


def test_stacking_italic_strike_nests_strike_inside_italic():
    out = render(_text_block([_styled("x", {"italic": True, "strikethrough": True})]), doc_id="t")
    assert "_~~x~~_" in out, f"italic+strike stacking wrong: {out!r}"


def test_stacking_italic_underline_nests_underline_inside_italic():
    out = render(_text_block([_styled("x", {"italic": True, "underline": True})]), doc_id="t")
    assert "_<u>x</u>_" in out, f"italic+underline stacking wrong: {out!r}"


def test_stacking_all_four_markdown_nests_in_order():
    out = render(
        _text_block([_styled("x", {
            "bold": True, "italic": True, "strikethrough": True, "underline": True,
        })]),
        doc_id="t",
    )
    # bold > italic > strike > underline, each closing marker prepended.
    assert "**_~~<u>x</u>~~_**" in out, f"four-way markdown stacking wrong: {out!r}"


# --- HTML-tag branch (use_html_tags ON) — the survivor the baseline named -----


def test_html_stacking_bold_italic_nests_em_inside_strong():
    # Kills the `suffix = "</em>" + suffix` -> `"</em>"` mutant (baseline #3).
    out = _render_html(_text_block([_styled("x", {"bold": True, "italic": True})]))
    assert "<strong><em>x</em></strong>" in out, f"html bold+italic stacking wrong: {out!r}"


def test_html_stacking_bold_strike_nests_del_inside_strong():
    # Kills the `suffix = "</del>" + suffix` -> `"</del>"` mutant.
    out = _render_html(_text_block([_styled("x", {"bold": True, "strikethrough": True})]))
    assert "<strong><del>x</del></strong>" in out, f"html bold+strike stacking wrong: {out!r}"


def test_html_stacking_bold_underline_nests_u_inside_strong():
    # Kills the `suffix = "</u>" + suffix` -> `"</u>"` mutant.
    out = _render_html(_text_block([_styled("x", {"bold": True, "underline": True})]))
    assert "<strong><u>x</u></strong>" in out, f"html bold+underline stacking wrong: {out!r}"


def test_html_stacking_all_four_nests_in_order():
    out = _render_html(
        _text_block([_styled("x", {
            "bold": True, "italic": True, "strikethrough": True, "underline": True,
        })])
    )
    assert "<strong><em><del><u>x</u></del></em></strong>" in out, (
        f"four-way html stacking wrong: {out!r}"
    )


def test_html_single_styles_use_tags_not_markdown():
    # Pin the single-style HTML wrappers (the branch the markdown-mode tests
    # never touch): bold/italic/strike become <strong>/<em>/<del>.
    assert "<strong>x</strong>" in _render_html(_text_block([_styled("x", {"bold": True})]))
    assert "<em>x</em>" in _render_html(_text_block([_styled("x", {"italic": True})]))
    assert "<del>x</del>" in _render_html(_text_block([_styled("x", {"strikethrough": True})]))


# ---------------------------------------------------------------------------
# LD-042 — capture text colors (fg/bg) into the model (consumed-into-model,
# dropped-at-render). The maintainer non-lossy-model principle: the read path must not
# be lossy at the MODEL level even where the .md projection drops the field, so
# a future writer can round-trip. The renderer keeps ignoring colors, so the
# .md output is byte-identical — these tests pin both the capture AND the
# byte-identical projection.
# ---------------------------------------------------------------------------


def _run_node(content, style):
    """Build one text_run's inline node via the real handler."""
    from lark_oapi.api.docx.v1.model.text_element import TextElement
    from larkdocio.blocks.text import _text_run_node

    e = TextElement({"text_run": {"content": content, "text_element_style": style}})
    return _text_run_node(Parser(Config()), e.text_run)


def test_styled_run_captures_colors_into_model():
    # AC1/AC2: the StyledText node CARRIES the fg/bg color enum values the SDK
    # exposes on text_element_style (Feishu color enum ints).
    from larkdocio.model import StyledText

    node = _run_node("x", {"text_color": 5, "background_color": 7})
    assert isinstance(node, StyledText)
    assert node.text_color == 5
    assert node.background_color == 7


def test_styled_run_without_colors_defaults_none():
    # AC1: fields default to absent (None) so existing constructions are
    # unaffected — a bold-only run carries no color.
    node = _run_node("x", {"bold": True})
    assert node.text_color is None
    assert node.background_color is None


def test_plain_unstyled_run_is_still_text_not_styled():
    # AC2: plain (no-style) runs are unaffected — they map to Text, which has no
    # color fields at all.
    from lark_oapi.api.docx.v1.model.text_element import TextElement
    from larkdocio.blocks.text import _text_run_node
    from larkdocio.model import Text

    e = TextElement({"text_run": {"content": "x"}})
    node = _text_run_node(Parser(Config()), e.text_run)
    assert isinstance(node, Text)
    assert not hasattr(node, "text_color")


def test_colored_run_renders_identical_to_uncolored():
    # AC3: renderer ignores colors — a colored+styled run's .md is byte-identical
    # to the same run without color.
    colored = render(
        _text_block([_styled("hello", {"bold": True, "text_color": 5, "background_color": 7})]),
        doc_id="t",
    )
    plain = render(_text_block([_styled("hello", {"bold": True})]), doc_id="t")
    assert colored == plain, f"colors leaked into output: {colored!r} != {plain!r}"


def test_color_only_run_renders_same_as_plain_text():
    # AC3: a run whose ONLY style is color renders exactly like literal text —
    # the color is captured into the model but dropped at render.
    colored = render(_text_block([_styled("hello", {"text_color": 5})]), doc_id="t")
    plain = render(_text_block([{"text_run": {"content": "hello"}}]), doc_id="t")
    assert colored == plain, f"color-only run altered output: {colored!r} != {plain!r}"


# ---------------------------------------------------------------------------
# LD-052 — edge whitespace inside emphasis/strike markers is an invalid
# CommonMark delimiter (a `**` immediately preceded by whitespace is not
# right-flanking, so it can't close). `_styled` must relocate leading/trailing
# whitespace OUTSIDE the marker stack: {leading_ws}{prefix}{core}{suffix}{trailing_ws}.
# Whitespace-only runs drop markers entirely; inline-code runs are EXCLUDED
# (code spans tolerate internal spaces and treat ** literally — left byte-identical).
# ---------------------------------------------------------------------------


def test_trailing_space_bold_relocates_space_outside_markers():
    # The Finding-6 case: `**Capacity Bounds: **` (space inside closer) is broken.
    out = render(_text_block([_styled("Capacity Bounds: ", {"bold": True})]), doc_id="t")
    assert "**Capacity Bounds:** " in out, f"trailing space not relocated: {out!r}"
    assert "**Capacity Bounds: **" not in out, f"space still inside closer: {out!r}"


def test_leading_space_bold_relocates_space_outside_markers():
    out = render(_text_block([_styled(" hi", {"bold": True})]), doc_id="t")
    assert " **hi**" in out, f"leading space not relocated: {out!r}"
    assert "** hi**" not in out, f"space still inside opener: {out!r}"


def test_leading_and_trailing_space_bold():
    out = render(_text_block([_styled(" hi ", {"bold": True})]), doc_id="t")
    assert " **hi** " in out, f"edge ws not relocated both sides: {out!r}"


def test_internal_whitespace_preserved():
    # Only EDGE whitespace moves; interior spaces stay put.
    out = render(_text_block([_styled("a b ", {"bold": True})]), doc_id="t")
    assert "**a b** " in out, f"internal ws not preserved / edge not moved: {out!r}"


def test_italic_trailing_space_relocates():
    out = render(_text_block([_styled("x ", {"italic": True})]), doc_id="t")
    assert "_x_ " in out, f"italic trailing ws not relocated: {out!r}"
    assert "_x _" not in out, f"space still inside italic closer: {out!r}"


def test_strike_trailing_space_relocates():
    out = render(_text_block([_styled("x ", {"strikethrough": True})]), doc_id="t")
    assert "~~x~~ " in out, f"strike trailing ws not relocated: {out!r}"
    assert "~~x ~~" not in out, f"space still inside strike closer: {out!r}"


# --- Stacking: relocate ONCE around the composed run, not per marker ----------


def test_stacking_bold_italic_relocates_edge_ws_once_around_composed_run():
    out = render(
        _text_block([_styled("  x  ", {"bold": True, "italic": True})]), doc_id="t"
    )
    assert "  **_x_**  " in out, f"stacked relocation wrong: {out!r}"
    assert "**_  x  _**" not in out, f"space still inside markers: {out!r}"


def test_stacking_all_four_relocates_edge_ws_once():
    out = render(
        _text_block([_styled("x ", {
            "bold": True, "italic": True, "strikethrough": True, "underline": True,
        })]),
        doc_id="t",
    )
    assert "**_~~<u>x</u>~~_** " in out, f"four-way stacked relocation wrong: {out!r}"


# --- Whitespace-only styled run: drop the markers entirely --------------------


def test_whitespace_only_bold_drops_markers():
    out = render(_text_block([_styled("   ", {"bold": True})]), doc_id="t")
    assert "****" not in out, f"empty emphasis emitted for whitespace-only run: {out!r}"
    assert "**" not in out, f"markers not dropped for whitespace-only run: {out!r}"


def test_whitespace_only_stacked_drops_all_markers():
    out = render(
        _text_block([_styled(" ", {"bold": True, "italic": True})]), doc_id="t"
    )
    assert "**" not in out and "_" not in out, f"markers not dropped: {out!r}"


# --- Inline code EXCLUDED — byte-identical (code spans tolerate spaces) --------


def test_inline_code_trailing_space_left_byte_identical():
    out = render(_text_block([_styled("code ", {"inline_code": True})]), doc_id="t")
    assert "`code `" in out, f"inline-code run was altered: {out!r}"


def test_bold_inline_code_trailing_space_not_relocated():
    # inline_code present -> the whole run is excluded from relocation.
    out = render(
        _text_block([_styled("x ", {"bold": True, "inline_code": True})]), doc_id="t"
    )
    assert "`**x **`" in out, f"inline-code run altered: {out!r}"


# --- Link outermost: relocation keeps bold valid ------------------------------


def test_bold_link_trailing_space_keeps_bold_valid():
    out = render(
        _text_block([_styled("foo ", {
            "bold": True, "link": {"url": "https%3A%2F%2Fexample.com"},
        })]),
        doc_id="t",
    )
    assert "[**foo** ](https://example.com)" in out, f"bold+link relocation wrong: {out!r}"
    assert "**foo **" not in out, f"space still inside closer: {out!r}"


# --- HTML-tag mode + underline: relocated too (single code path — dev's call) --


def test_html_bold_trailing_space_relocated():
    out = _render_html(_text_block([_styled("x ", {"bold": True})]))
    assert "<strong>x</strong> " in out, f"html bold edge ws not relocated: {out!r}"


def test_underline_trailing_space_relocated_for_consistency():
    # Underline (<u>) tolerates internal whitespace, so relocation is not required
    # for correctness; we normalize anyway so all styles share one code path.
    out = render(_text_block([_styled("x ", {"underline": True})]), doc_id="t")
    assert "<u>x</u> " in out, f"underline edge ws not relocated: {out!r}"
