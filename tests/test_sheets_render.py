"""Offline unit tests for value→Markdown cell rendering (LD-103).

Renders each Sheets cell (from the **FormattedValue** read, D1) to Markdown,
covering the spike's full type matrix. Fixtures come from the LD-100 opener
spike's committed captures (``tests/captures/sheets-spike/captures/02-*.json``) — the
**native column D + hand-adds (B20–B24) are the fidelity authority**; the pasted
column B is a drift reference (spike Q1). ``02-hand-adds-FormattedValue.json`` is
a fresh (2026-07-26, revision 36) read-only capture of the hand-add band pinning
the *current* wire shapes (single/multi dropdowns now populated as bare strings,
the @user mention id field now ``userID`` where the older capture had ``token``).

The renderer **reuses** the docx reader's inline-Markdown serializer
(:class:`larkdocio.model.MarkdownRenderer`) and mirrors its ``resolve_mentions``
graceful-degrade contract (D6) — parity is the point. All offline (no network).

Column indices in the type matrix: A=0 (label), B=1 (pasted drift), C=2 (notes),
D=3 (native authority).
"""
import json
from pathlib import Path

from larkdocio.sheets.render import apply_cell_emphasis, render_cell

_CAPTURES = Path(__file__).resolve().parent.parent / "tests" / "captures" / "sheets-spike" / "captures"


def _capture_values(name):
    payload = json.loads((_CAPTURES / name).read_text(encoding="utf-8"))
    return payload["data"]["valueRange"]["values"]


# The FormattedValue type matrix (444a1c!A1:D24) and the dates capture.
_TYPES = _capture_values("02-types-FormattedValue.json")
_DATES = _capture_values("02-dates-FormattedValue-FormattedString.json")
_HANDADDS = _capture_values("02-hand-adds-FormattedValue.json")

# Native column D (authority) / pasted column B by matrix row (0-indexed).
COL_B, COL_D = 1, 3


def _row(label):
    for r in _TYPES:
        if r and r[0] == label:
            return r
    raise AssertionError(f"no type-matrix row labelled {label!r}")


def _handadd(label):
    for r in _HANDADDS:
        if r and r[0] == label:
            return r
    raise AssertionError(f"no hand-add row labelled {label!r}")


# --------------------------------------------------------------------------- #
# AC6 — null → empty                                                           #
# --------------------------------------------------------------------------- #

def test_null_renders_empty():
    assert render_cell(None) == ""


# --------------------------------------------------------------------------- #
# AC1 — scalars & display strings                                             #
# --------------------------------------------------------------------------- #

def test_plain_string_native():
    assert render_cell(_row("plain string")[COL_D]) == "hello world"


def test_integer_native():
    assert render_cell(_row("integer")[COL_D]) == "42"


def test_float_native():
    assert render_cell(_row("float")[COL_D]) == "3.14159"


def test_negative_number_native():
    assert render_cell(_row("negative number")[COL_D]) == "-273.15"


def test_percentage_display_string():
    # A properly percent-formatted cell's FormattedValue is the display string.
    assert render_cell(_row("percentage")[COL_B]) == "12.34%"


def test_currency_display_string():
    assert render_cell(_row("currency")[COL_D]) == "$1,234.56"


def test_scientific_display_string():
    assert render_cell(_row("big number")[COL_B]) == "1.23E+13"


def test_native_raw_number_renders_as_its_str():
    # Native column D percentage reads back as the raw number 0.1234 under
    # FormattedValue (its percent format was not reapplied) — a raw number
    # renders as its plain str, never a serial/exponent artefact.
    assert render_cell(_row("percentage")[COL_D]) == "0.1234"


def test_string_newline_preserved_for_s4():
    # S3 renders a SINGLE cell; pipe/newline normalisation for table validity is
    # S4's job (LD-104). The raw newline must survive here.
    assert render_cell(_row("string with newline")[COL_D]) == "line one\nline two"


# --------------------------------------------------------------------------- #
# AC2 — dates / datetimes via dateTimeRenderOption=FormattedString            #
# --------------------------------------------------------------------------- #

def test_date_formatted_string():
    assert render_cell(_DATES[0][COL_D]) == "7/26/2026"


def test_datetime_formatted_string():
    assert render_cell(_DATES[1][COL_D]) == "7/26/2026 15:30"


def test_date_not_serial_float():
    # A FormattedString date must never surface as its raw serial float.
    assert render_cell(_row("date")[COL_D]) == "7/26/2026"


# --------------------------------------------------------------------------- #
# AC3 — rich text → MD inline (color dropped); hyperlink → [text](link)       #
# --------------------------------------------------------------------------- #

def test_styled_runs_native_inline_markdown():
    out = render_cell(_row("styled text runs")[COL_D])
    assert out == "**bold start** plain middle _italic end_"


def test_styled_runs_color_dropped():
    out = render_cell(_row("styled text runs")[COL_D])
    for leak in ("rgb", "#000000", "foreColor", "color", "fontSize"):
        assert leak not in out


def test_hyperlink_native_text_equals_link():
    assert (
        render_cell(_row("hyperlink")[COL_D])
        == "[https://www.google.com](https://www.google.com)"
    )


def test_hyperlink_labeled_text():
    assert (
        render_cell(_row("hyperlink")[COL_B])
        == "[Lark Suite homepage](https://www.larksuite.com/)"
    )


def test_all_four_inline_marks_and_no_color():
    # A synthesized single styled run exercising every covered mark at once,
    # plus a dropped color (foreColor must never surface).
    seg = [{
        "type": "text",
        "text": "loud",
        "segmentStyle": {
            "bold": True, "italic": True, "strikeThrough": True,
            "underline": True, "foreColor": "rgb(255, 0, 0)", "fontSize": 14,
        },
    }]
    out = render_cell(seg)
    assert out == "**_~~<u>loud</u>~~_**"
    assert "rgb" not in out and "255" not in out


# --------------------------------------------------------------------------- #
# AC4 — @mention → display name, graceful degrade (parity w/ resolve_mentions)#
# --------------------------------------------------------------------------- #

def test_user_mention_resolved_via_map_wins():
    # The external resolution map (parity with the docx resolve_mentions API
    # path) takes precedence over the payload's inline name.
    obj = _handadd("HAND-ADD: @user mention")[COL_B]
    out = render_cell(obj, mention_names={"ou_exampleowner00000000000000000001": "Resolved Person"})
    assert out == "@Resolved Person"


def test_user_mention_degrade_to_inline_name_empty_map():
    # Empty map (the current state until the console availability-range fix) →
    # degrade to the payload's own display name; a read must NEVER fail.
    obj = _handadd("HAND-ADD: @user mention")[COL_B]
    assert render_cell(obj, mention_names={}) == "@Example User"


def test_user_mention_token_field_from_older_capture():
    # The committed 02-types capture carries the id in `token` (not `userID`);
    # both id fields must resolve.
    obj = _row("HAND-ADD: @user mention")[COL_B]
    assert obj.get("token")  # older capture shape
    assert render_cell(obj, mention_names={obj["token"]: "By Token"}) == "@By Token"


def test_user_mention_minimal_never_raises():
    # A mention object with no name/text/id must degrade gracefully, not raise.
    assert render_cell({"type": "mention", "mentionType": 0}) == ""


def test_user_mention_degrade_to_text_when_no_name():
    # No inline name, but a raw @text → fall back to the raw token/text.
    obj = {"type": "mention", "mentionType": 0, "text": "@Someone", "userID": "ou_x"}
    assert render_cell(obj, mention_names={}) == "@Someone"


def test_doc_link_mention_renders_markdown_link():
    obj = _handadd("HAND-ADD: doc-link mention")[COL_B]
    assert render_cell(obj) == (
        "[Larkdocio Scratch]"
        "(https://your-domain.larksuite.com/docx/DocScratchExample0000000001)"
    )


# --------------------------------------------------------------------------- #
# AC5 — checkbox & dropdown                                                    #
# --------------------------------------------------------------------------- #

def test_checkbox_checked():
    assert render_cell(True) == "☑"  # ☑


def test_checkbox_unchecked():
    assert render_cell(False) == "☐"  # ☐


def test_dropdown_single_bare_string():
    assert render_cell(_handadd("HAND-ADD: dropdown (single)")[COL_B]) == "Single Option 1"


def test_dropdown_multi_bare_string():
    # A multi-select with ONE selection reads back as a bare string (live rev 36).
    assert render_cell(_handadd("HAND-ADD: dropdown (multi)")[COL_B]) == "Multiple Option 1"


def test_dropdown_multi_object_form_2plus():
    # A 2+‑selection multi-select may surface as the documented
    # {"type":"multipleValue"} object (synthesized — not reproducible live while
    # the scratch sheet holds only one selection). Both forms must be handled.
    obj = {"type": "multipleValue", "values": ["Multiple Option 1", "Multiple Option 2"]}
    assert render_cell(obj) == "Multiple Option 1, Multiple Option 2"


def test_dropdown_multi_object_form_segment_dicts():
    # Defensive: the values list may carry segment dicts rather than bare strings.
    obj = {"type": "multipleValue", "values": [
        {"type": "text", "text": "Alpha"}, {"type": "text", "text": "Beta"},
    ]}
    assert render_cell(obj) == "Alpha, Beta"


def test_dropdown_unselected_is_null_empty():
    assert render_cell(None) == ""


# --------------------------------------------------------------------------- #
# LD-117 gain (b) — multi-select → ordered ", "-joined set (DEFAULT MD).       #
# The read comma-joined-string form ("Red,Green", under all render modes —     #
# write Q3 / 03b-dropdown.json) and the write multipleValue-object form unify  #
# to ONE ordered ", "-joined display ("Red, Green"). Numeric strings           #
# (currency/thousands/decimal) are NOT a label set and MUST be preserved: the  #
# read-string multi-select form is indistinguishable from a formatted number   #
# at the value layer, so a comma flanked by digits on both sides marks a       #
# numeric grouping and the cell is left untouched (D5b).                       #
# --------------------------------------------------------------------------- #

def test_dropdown_multi_read_string_gets_space():
    # The load-bearing (b) change: the comma-joined READ form gains the ", ".
    assert render_cell("Red,Green") == "Red, Green"


def test_dropdown_multi_read_string_three_options_ordered():
    # Ordered = sheet order preserved (NOT sorted); every separator normalized.
    assert render_cell("Green,Red,Blue") == "Green, Red, Blue"


def test_dropdown_multi_read_string_idempotent_when_already_spaced():
    assert render_cell("Red, Green") == "Red, Green"


def test_dropdown_multi_both_wire_forms_render_same():
    # AC2: the read comma-joined-string form and the write multipleValue-object
    # form render to the SAME ordered ", "-joined display.
    read_form = render_cell("Red,Green")
    write_form = render_cell({"type": "multipleValue", "values": ["Red", "Green"]})
    assert read_form == write_form == "Red, Green"


def test_multiselect_normalizer_preserves_currency():
    # A currency FormattedValue is a comma-bearing STRING indistinguishable from
    # the read multi-select form except that its comma sits between digits — the
    # digit-flank guard must leave it byte-identical (never "$1, 234.56").
    assert render_cell("$1,234.56") == "$1,234.56"


def test_multiselect_normalizer_preserves_thousands_grouped_int():
    assert render_cell("1,234") == "1,234"
    assert render_cell("1,234,567") == "1,234,567"


def test_multiselect_normalizer_preserves_european_decimal():
    # A comma decimal separator ("3,14") is digit-flanked → not a label set.
    assert render_cell("3,14") == "3,14"


def test_dropdown_multi_single_selection_unchanged():
    # A single-selection multi-select reads back as a bare string with no comma —
    # unchanged (no separator to normalize).
    assert render_cell("Multiple Option 1") == "Multiple Option 1"


def test_dropdown_multi_empty_read_string():
    assert render_cell("") == ""


def test_multiselect_normalizer_alpha_label_with_trailing_number():
    # A non-numeric label set whose members mix letters and digits still gets the
    # space (the guard only fires on a digit-BOTH-sides comma).
    assert render_cell("Item 1,Item 2") == "Item 1, Item 2"


# --------------------------------------------------------------------------- #
# Reuse / parity — the shared renderer's config threads through               #
# --------------------------------------------------------------------------- #

def test_styled_run_honors_shared_renderer_html_policy():
    # Passing a use_html_tags renderer proves S3 reuses the docx serializer
    # rather than forking its own emphasis composition (D6 parity).
    from larkdocio.model import MarkdownRenderer
    seg = [{"type": "text", "text": "b", "segmentStyle": {"bold": True}}]
    assert render_cell(seg, renderer=MarkdownRenderer(use_html_tags=True)) == "<strong>b</strong>"


def test_unknown_scalar_type_never_raises():
    # Belt-and-braces: an unexpected value type degrades to str, never raises.
    assert render_cell(3 + 0j) == str(3 + 0j)


# --------------------------------------------------------------------------- #
# LD-117 gain (a) — cell-level bold/italic → MD emphasis (OPT-IN fidelity      #
# read). apply_cell_emphasis wraps an ALREADY-rendered cell string in the      #
# whole-cell emphasis the values API can't see (it lives only in the xlsx      #
# export), reusing the shared serializer's emphasis composition + html-tag     #
# policy. The wrap is the LAST render step, so a bold multi-select cell         #
# ("Red,Green" → "Red, Green" from gain (b)) emphasises the WHOLE set.         #
# --------------------------------------------------------------------------- #

def test_cell_emphasis_bold_wraps_via_serializer():
    assert apply_cell_emphasis("hello", bold=True, italic=False) == "**hello**"


def test_cell_emphasis_italic():
    assert apply_cell_emphasis("hello", bold=False, italic=True) == "_hello_"


def test_cell_emphasis_bold_and_italic_nests_bold_outer():
    # Composition order mirrors the shared serializer (bold wraps italic).
    assert apply_cell_emphasis("hello", bold=True, italic=True) == "**_hello_**"


def test_cell_emphasis_none_is_passthrough():
    # No cell-level style → byte-identical passthrough (the flag-OFF invariant at
    # the cell scope).
    assert apply_cell_emphasis("hello", bold=False, italic=False) == "hello"


def test_cell_emphasis_wraps_the_whole_multiselect_set():
    # gain (a) + gain (b) interaction: a bold multi-select cell emphasises the
    # ENTIRE ordered set, not a fragment.
    rendered = render_cell("Red,Green")            # gain (b) → "Red, Green"
    assert apply_cell_emphasis(rendered, bold=True, italic=False) == "**Red, Green**"


def test_cell_emphasis_honors_html_tag_renderer():
    # Reuse the shared serializer, not a fork: use_html_tags threads through.
    from larkdocio.model import MarkdownRenderer
    out = apply_cell_emphasis("b", bold=True, renderer=MarkdownRenderer(use_html_tags=True))
    assert out == "<strong>b</strong>"


def test_cell_emphasis_does_not_relinkify_prerendered_markup():
    # The cell text is ALREADY rendered MD (a hyperlink cell) — wrapping it must
    # not re-escape or double-link its contents.
    link_cell = render_cell({"type": "url", "link": "https://x.test", "text": "t"})
    assert link_cell == "[t](https://x.test)"
    assert apply_cell_emphasis(link_cell, bold=True) == "**[t](https://x.test)**"


def test_cell_emphasis_empty_stays_empty():
    # A flagged-bold empty cell has no core to emphasise — markers drop.
    assert apply_cell_emphasis("", bold=True, italic=True) == ""
