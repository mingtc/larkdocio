"""Offline unit tests for the Sheets rich-cell write encoders + the multi-select
normalizer (LD-119/D7).

The encoders (:mod:`larkdocio.sheets.rich_encode`) produce the **exact LD-107 Q3
wire shapes** the write spike proved live — hyperlink, styled-runs, @mention, and
multi-select — asserted against the captured request bodies
(``tests/captures/sheets-write-spike/captures/03-rich-cells.json`` / ``03b-dropdown.json``):

* **AC1** — each encoder emits the byte-exact cell the spike wrote;
* **AC2** — a mention defaults ``notify:false`` + ``grantReadPermission:false``
  (least surprise / least privilege, D6), opt-in overrides flip them;
* **AC3** — a multi-select normalizes to an **ordered label set** and encodes the
  ``multipleValue`` object; a **comma inside an option label** yields a typed
  refusal (:class:`~larkdocio.sheets.rich_encode.MultiSelectLabelError`), never a
  silent corruption. The read/write asymmetry (write object → read comma-joined
  string) is normalized to the **same** ordered set via the LD-115 normalizer.

The **test-rigor amplifier** ("go a bit nuts"): the comma refusal (a label
``"a,b"`` refuses), an empty multi-select, unicode in labels + links, a mention
with missing name fields (read-model robustness), and the write/read round-trip
(write object → read comma-joined string → normalize back to the same ordered set).
"""
import json
from pathlib import Path

import pytest

from larkdocio.errors import LarkConfigError
from larkdocio.sheets.cell_model import UserMention, parse_segments
from larkdocio.sheets.rich_encode import (
    DropdownColorsError,
    MultiSelectLabelError,
    encode_dropdown_rule,
    encode_hyperlink,
    encode_mention,
    encode_multi_select,
    encode_styled_run,
    encode_styled_runs,
    normalize_multi_select,
)

_CAPTURES = Path(__file__).resolve().parents[1] / "tests" / "captures" / "sheets-write-spike" / "captures"


def _rich_capture():
    return json.loads((_CAPTURES / "03-rich-cells.json").read_text(encoding="utf-8"))["captures"]


def _write_cell(capture_key):
    """The single written cell (``values[0][0]``) of a capture's PUT request body."""
    cap = _rich_capture()[capture_key]
    return cap["write"]["request_body"]["valueRange"]["values"][0][0]


# =========================================================================== #
# AC1 — each encoder emits the byte-exact LD-107 Q3 wire cell                   #
# =========================================================================== #

def test_hyperlink_encodes_the_exact_spike_wire_cell():
    assert encode_hyperlink("https://www.larksuite.com", text="Lark Suite") == _write_cell("hyperlink")


def test_hyperlink_text_defaults_to_the_link():
    assert encode_hyperlink("https://x.example") == {
        "type": "url", "text": "https://x.example", "link": "https://x.example",
    }


def test_styled_runs_encode_the_exact_spike_wire_cell():
    encoded = encode_styled_runs([
        {"text": "bold ", "bold": True},
        {"text": "then italic", "italic": True, "fore_color": "#FF0000"},
    ])
    assert encoded == _write_cell("styled_runs")


def test_styled_run_only_carries_the_set_style_keys():
    assert encode_styled_run("x", bold=True) == {
        "type": "text", "text": "x", "segmentStyle": {"bold": True},
    }


def test_styled_run_maps_camelcase_wire_keys():
    run = encode_styled_run(
        "y", strikethrough=True, underline=True, fore_color="#00FF00", font_size=12
    )
    assert run == {
        "type": "text",
        "text": "y",
        "segmentStyle": {
            "strikeThrough": True,
            "underline": True,
            "foreColor": "#00FF00",
            "fontSize": 12,
        },
    }


def test_unstyled_run_carries_an_empty_segment_style():
    assert encode_styled_run("plain") == {
        "type": "text", "text": "plain", "segmentStyle": {},
    }


def test_multi_select_encodes_the_exact_spike_wire_cell():
    assert encode_multi_select(["Red", "Green"]) == _write_cell("multi_value")


def test_multi_select_encodes_the_dropdown_capture_wire_cell():
    dropdown = json.loads((_CAPTURES / "03b-dropdown.json").read_text(encoding="utf-8"))["captures"]
    cell = dropdown["multi_write"]["request_body"]["valueRange"]["values"][0][0]
    assert encode_multi_select(["Red", "Green"]) == cell


# =========================================================================== #
# AC2 — @mention least-surprise defaults (D6), opt-in overrides                 #
# =========================================================================== #

def test_mention_encodes_the_exact_spike_wire_cell():
    assert encode_mention("ou_examplesecond0000000000000000001") == _write_cell("mention_user")


def test_mention_defaults_notify_and_grant_read_permission_false():
    m = encode_mention("ou_abc")
    assert m["notify"] is False
    assert m["grantReadPermission"] is False
    assert m["textType"] == "openId"
    assert m["text"] == "ou_abc"
    assert m["type"] == "mention"


def test_mention_opt_in_flips_both_flags():
    m = encode_mention("ou_abc", notify=True, grant_read_permission=True)
    assert m["notify"] is True
    assert m["grantReadPermission"] is True


# =========================================================================== #
# AC3 — multi-select ordered-label-set normalization + comma refusal (D7)       #
# =========================================================================== #

def test_multi_select_normalizes_input_labels_strip_and_drop_empty():
    assert encode_multi_select([" Red ", "", "Green"]) == {
        "type": "multipleValue", "values": ["Red", "Green"],
    }


def test_multi_select_preserves_order():
    assert encode_multi_select(["Green", "Red", "Blue"])["values"] == ["Green", "Red", "Blue"]


def test_empty_multi_select_encodes_an_empty_value_list():
    assert encode_multi_select([]) == {"type": "multipleValue", "values": []}


def test_comma_in_option_label_refuses_typed():
    with pytest.raises(MultiSelectLabelError):
        encode_multi_select(["a,b"])


def test_comma_in_option_label_after_other_labels_still_refuses():
    with pytest.raises(MultiSelectLabelError):
        encode_multi_select(["Red", "Green", "a, b"])


def test_comma_refusal_names_the_offending_label():
    with pytest.raises(MultiSelectLabelError) as ei:
        encode_multi_select(["Red", "big,label"])
    assert "big,label" in str(ei.value)


# --------------------------------------------------------------------------- #
# The read/write asymmetry — normalize BOTH sides to the same ordered label    #
# set (reusing the LD-115 MultiSelect normalizer, not a fork).                 #
# --------------------------------------------------------------------------- #

def test_normalize_multi_select_read_string_and_write_object_unify():
    written = encode_multi_select(["Red", "Green"])
    read_back = _rich_capture()["multi_value"]["readback_values"][0][0]  # "Red,Green"
    assert read_back == "Red,Green"
    assert normalize_multi_select(written) == normalize_multi_select(read_back) == ("Red", "Green")


def test_normalize_multi_select_respaced_read_string_unifies():
    # a "Red, Green" (space after comma) read form normalizes to the same ordered set.
    assert normalize_multi_select("Red, Green") == normalize_multi_select("Red,Green")


def test_write_read_round_trip_normalizes_to_the_same_ordered_set():
    labels = ["Green", "Red", "Blue"]
    written = encode_multi_select(labels)
    read_back = ",".join(labels)  # the comma-joined read form Lark returns
    assert normalize_multi_select(written) == normalize_multi_select(read_back) == tuple(labels)


# --------------------------------------------------------------------------- #
# Amplifier — unicode in labels + links, mention with missing name fields.     #
# --------------------------------------------------------------------------- #

def test_unicode_labels_encode_and_round_trip():
    written = encode_multi_select(["红", "绿"])
    assert written["values"] == ["红", "绿"]
    assert normalize_multi_select(written) == normalize_multi_select("红,绿") == ("红", "绿")


def test_unicode_in_hyperlink_text_and_link():
    assert encode_hyperlink("https://x.example/文档", text="文档") == {
        "type": "url", "text": "文档", "link": "https://x.example/文档",
    }


def test_mention_read_model_tolerates_missing_name_fields():
    # A mention readback missing name/en_name must not crash the read model (LD-115
    # UserMention graceful-degrade) — the mention still resolves to its id-only form.
    (seg,) = parse_segments({"type": "mention", "mentionType": 0, "token": "9000000000000000003"})
    assert isinstance(seg, UserMention)
    assert seg.name is None
    assert seg.user_id == "9000000000000000003"


# =========================================================================== #
# LD-120 — dropdown-RULE encoder (the dataValidation family).                   #
# A list rule encodes conditionValues + options.multipleValues; the 90204       #
# colors caveat (highlightValidData:true needs a colors array 1:1 with values)  #
# is caught as a typed DropdownColorsError BEFORE the write, never on the wire.  #
# =========================================================================== #

def _dropdown_capture():
    return json.loads((_CAPTURES / "03b-dropdown.json").read_text(encoding="utf-8"))["captures"]


def test_dropdown_rule_encodes_the_exact_spike_wire_shape():
    # the 03b capture's POST body minus its `range` (the range is the client's job).
    body = _dropdown_capture()["dv_set_valid"]["request_body"]
    expected = {k: v for k, v in body.items() if k != "range"}
    assert encode_dropdown_rule(["Red", "Green", "Blue"], multiple_values=True) == expected


def test_dropdown_rule_shape_is_type_plus_datavalidation():
    rule = encode_dropdown_rule(["A", "B"], multiple_values=True)
    assert rule["dataValidationType"] == "list"
    assert rule["dataValidation"]["conditionValues"] == ["A", "B"]
    assert rule["dataValidation"]["options"]["multipleValues"] is True


def test_dropdown_rule_defaults_single_select_highlight_off_no_colors():
    # AC2: highlightValidData defaults false; a single-select rule (multipleValues
    # default false) carries NO colors key when highlight is off.
    rule = encode_dropdown_rule(["A", "B", "C"])
    opts = rule["dataValidation"]["options"]
    assert opts == {"multipleValues": False, "highlightValidData": False}
    assert "colors" not in opts


def test_dropdown_rule_preserves_condition_value_order():
    rule = encode_dropdown_rule(["Green", "Red", "Blue"])
    assert rule["dataValidation"]["conditionValues"] == ["Green", "Red", "Blue"]


def test_dropdown_rule_highlight_true_with_one_to_one_colors_attaches_them():
    rule = encode_dropdown_rule(
        ["Red", "Green", "Blue"],
        highlight_valid_data=True,
        colors=["#FF0000", "#00FF00", "#0000FF"],
    )
    opts = rule["dataValidation"]["options"]
    assert opts["highlightValidData"] is True
    assert opts["colors"] == ["#FF0000", "#00FF00", "#0000FF"]


def test_dropdown_rule_highlight_true_without_colors_refuses_typed():
    # AC2: the 90204 caveat — a highlightValidData:true with no colors array is
    # refused BEFORE the write (a typed DropdownColorsError), never sent to Lark.
    with pytest.raises(DropdownColorsError):
        encode_dropdown_rule(["Red", "Green", "Blue"], highlight_valid_data=True)


def test_dropdown_rule_highlight_true_colors_length_mismatch_refuses_typed():
    with pytest.raises(DropdownColorsError):
        encode_dropdown_rule(
            ["Red", "Green", "Blue"], highlight_valid_data=True, colors=["#FF0000", "#00FF00"]
        )


def test_dropdown_colors_error_names_the_mismatch():
    with pytest.raises(DropdownColorsError) as ei:
        encode_dropdown_rule(["Red", "Green"], highlight_valid_data=True, colors=["#FF0000"])
    msg = str(ei.value)
    assert "90204" in msg and "2" in msg and "1" in msg


def test_dropdown_colors_error_is_a_lark_config_error():
    # under LarkConfigError (an unsupported-input problem, like MultiSelectLabelError),
    # so `except LarkConfigError` / `except LarkDocIOError` catch it.
    assert issubclass(DropdownColorsError, LarkConfigError)


def test_dropdown_rule_highlight_false_ignores_stray_colors():
    # colors are only meaningful with highlight on; with highlight off they are
    # dropped (the wire shape stays the highlight-off form — no phantom colors key).
    rule = encode_dropdown_rule(["A", "B"], colors=["#FF0000", "#00FF00"])
    assert "colors" not in rule["dataValidation"]["options"]


def test_dropdown_rule_single_vs_multi_differ_only_in_multiple_values():
    single = encode_dropdown_rule(["A", "B"])
    multi = encode_dropdown_rule(["A", "B"], multiple_values=True)
    assert single["dataValidation"]["options"]["multipleValues"] is False
    assert multi["dataValidation"]["options"]["multipleValues"] is True
    assert single["dataValidation"]["conditionValues"] == multi["dataValidation"]["conditionValues"]
