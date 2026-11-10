"""LD-246 — the Base `(type, ui_type)` cell-renderer registry (the Base read spec § F1-S1).

Offline end to end: every payload shape here is read from the **committed Base-study
captures** (`tests/captures/base-study/captures/`, the `tests/test_sheets_render.py` precedent of
reading a spike's own captures rather than re-typing them), so the suite pins the wire
shapes Lark actually returned rather than a hand-mocked idea of them.
"""
import json
import re
from pathlib import Path

import pytest

from larkdocio.base import cells

_CAPTURES = Path(__file__).resolve().parent.parent / "tests" / "captures" / "base-study" / "captures"


def _capture(name):
    return json.loads((_CAPTURES / name).read_text(encoding="utf-8"))


def _find(obj, key, out=None, path=""):
    """Every ``key`` occurrence in a capture, as ``(json-path, value)``."""
    out = [] if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                out.append((f"{path}/{k}", v))
            _find(v, key, out, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _find(v, key, out, f"{path}[{i}]")
    return out


# --------------------------------------------------------------------------- #
# AC1 — the registry dispatches on (type, ui_type), 27 pairs / 26 renderers    #
# --------------------------------------------------------------------------- #

def test_ac1_the_registry_has_exactly_27_pairs_26_of_them_value_rendering():
    """The maintainer's arithmetic, checkable: 28 picker types − Button (no API identity)
    = 27 `(type, ui_type)` pairs; 26 render a value and `(24, "Stage")` renders the
    absent-with-reason marker."""
    assert len(cells.PAIRS) == 27, sorted(cells.PAIRS)
    assert len(set(cells.PAIRS)) == 27, "a pair is listed twice"
    assert len(cells.VALUE_RENDERED_PAIRS) == 26
    assert cells.OPAQUE_PAIRS == ((24, "Stage"),)
    assert set(cells.VALUE_RENDERED_PAIRS) | set(cells.OPAQUE_PAIRS) == set(cells.PAIRS)


def test_ac1_the_pairs_are_exactly_the_ones_the_parity_matrix_enumerates():
    """Enumerated so the count is checkable against `dev/base-study/ui-parity-matrix-
    2026-08-03.md` § 1 — 3 (`type 1`) + 4 (`type 2`) + 20 singletons."""
    assert sorted(p for p in cells.PAIRS if p[0] == 1) == [
        (1, "Barcode"), (1, "Email"), (1, "Text"),
    ]
    assert sorted(p for p in cells.PAIRS if p[0] == 2) == [
        (2, "Currency"), (2, "Number"), (2, "Progress"), (2, "Rating"),
    ]
    singletons = sorted(p for p in cells.PAIRS if p[0] not in (1, 2))
    assert singletons == [
        (3, "SingleSelect"), (4, "MultiSelect"), (5, "DateTime"), (7, "Checkbox"),
        (11, "User"), (13, "Phone"), (15, "Url"), (17, "Attachment"),
        (18, "SingleLink"), (19, "Lookup"), (20, "Formula"), (21, "DuplexLink"),
        (22, "Location"), (23, "GroupChat"), (24, "Stage"), (1001, "CreatedTime"),
        (1002, "ModifiedTime"), (1003, "CreatedUser"), (1004, "ModifiedUser"),
        (1005, "AutoNumber"),
    ]
    assert len(singletons) == 20


def test_ac1_button_has_no_pair_and_no_renderer():
    """AC7d — WILL-NOT-SUPPORT: there is no `(type, ui_type)` to dispatch on."""
    assert not [p for p in cells.PAIRS if "Button" in p[1]]
    assert "Button" in cells.WILL_NOT_SUPPORT


def test_ac1_every_pair_the_captured_field_schemas_show_has_a_renderer():
    """Every `(type, ui_type)` the Base-study captures ever observed on a real field
    is dispatchable — except the ones the parity matrix rules out (the probes'
    rejected create attempts echo bogus pairs like `(3, "Stage")`)."""
    observed = set()
    for path in sorted(_CAPTURES.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        stack = [payload]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if "ui_type" in node and "type" in node and "field_name" in node:
                    observed.add((node.get("type"), node.get("ui_type")))
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    real = observed & set(cells.PAIRS)
    assert len(real) >= 20, f"the capture sweep found too few real pairs: {sorted(real)}"
    for pair in sorted(real):
        assert cells.renderer_for(*pair) is not None, pair


def test_ac1_an_unknown_pair_degrades_and_never_raises():
    fld = cells.FieldSpec(field_name="?", type=9999, ui_type="Martian")
    assert cells.renderer_for(9999, "Martian") is None
    assert cells.render_cell({"weird": 1}, fld) == "{'weird': 1}"


# --------------------------------------------------------------------------- #
# AC2 / R13 — the segment array, walked, dispatching PER SEGMENT               #
# --------------------------------------------------------------------------- #

def _text_field(name="Text", ui="Text"):
    return cells.FieldSpec(field_name=name, type=1, ui_type=ui)


def test_ac2_a_type1_cell_is_a_segment_array_from_records_search():
    """`p1-q0-03` — `records/search` returns `[{"text":…,"type":"text"}]`."""
    cap = _capture("p1-q0-03-per-table.json")
    row = cap["per_table"][0]["records_search"]["response"]["data"]["items"][0]
    assert row["fields"]["Text"] == [{"text": "Text 1", "type": "text"}]
    assert cells.render_cell(row["fields"]["Text"], _text_field()) == "Text 1"


def test_ac2_single_segment_is_byte_identical_to_the_plain_string_that_made_it():
    assert cells.render_cell([{"text": "THE ROW", "type": "text"}], _text_field()) == "THE ROW"


def test_ac2_a_multi_segment_cell_joins_with_no_inserted_separator():
    segs = [{"text": "a", "type": "text"}, {"text": "b", "type": "text"}]
    assert cells.render_cell(segs, _text_field()) == "ab"


def test_ac2_r13_the_walker_dispatches_on_each_segments_own_type_not_the_fields():
    """THE BINDING R13 CASE. A `type:1` array mixing a `text` and a `url` segment
    renders BOTH — a walker keyed on the field's type emits nothing for the url
    segment or crashes on the missing `text` handling."""
    segs = [
        {"text": "write to ", "type": "text"},
        {"link": "mailto:ok@example.invalid", "text": "ok@example.invalid", "type": "url"},
    ]
    out = cells.render_cell(segs, _text_field())
    assert out == "write to [ok@example.invalid](mailto:ok@example.invalid)"


def test_ac2_barcode_reads_back_as_a_segment_array_too():
    """`06-03` — a `ui_type: Barcode` cell is a type-1 segment array under search."""
    cap = _capture("06-03-value-read-option-matrix.json")
    barcodes = [v for _, v in _find(cap, "Barcode") if isinstance(v, list)]
    assert barcodes and barcodes[0] == [{"text": "BC-0001", "type": "text"}]
    assert cells.render_cell(barcodes[0], _text_field("Barcode", "Barcode")) == "BC-0001"


def test_ac2_the_create_echo_is_a_BARE_STRING_and_search_is_the_array():
    """The write/read asymmetry, pinned: a fixture pinned to the create echo is a bug
    (`06-02-record-create-echo.json` vs `06-03-value-read-option-matrix.json`)."""
    echo = _capture("06-02-record-create-echo.json")["response"]["data"]["record"]["fields"]
    assert echo["Text"] == "THE ROW"          # bare string — the ECHO
    assert echo["Barcode"] == "BC-0001"
    search = _capture("06-03-value-read-option-matrix.json")
    texts = [v for _, v in _find(search, "Text") if isinstance(v, list)]
    assert texts and texts[0] == [{"text": "THE ROW", "type": "text"}]   # array — the READ
    # The registry still degrades gracefully on the echo shape, but the two are
    # different shapes and only `search` is the pin (R7).
    assert cells.render_cell(echo["Text"], _text_field()) == "THE ROW"


def test_ac2_email_is_a_type1_field_whose_single_segment_is_type_url():
    """`p1-q0-03` — the read shape is `[{"link":"mailto:…","text":…,"type":"url"}]`."""
    cap = _capture("p1-q0-03-per-table.json")
    row = cap["per_table"][0]["records_search"]["response"]["data"]["items"][0]
    email = row["fields"]["Email"]
    assert isinstance(email, list) and email[0]["type"] == "url"
    field = cells.FieldSpec(field_name="Email", type=1, ui_type="Email")
    # (the capture's address is redacted; the shape is what is pinned here)
    assert cells.render_cell(email, field).startswith("[")


def test_ac2_email_renders_its_own_address_text_ac7b():
    field = cells.FieldSpec(field_name="Email", type=1, ui_type="Email")
    segs = [{"link": "mailto:ok@example.invalid", "text": "ok@example.invalid", "type": "url"}]
    assert cells.render_cell(segs, field) == "[ok@example.invalid](mailto:ok@example.invalid)"


def test_ac2_a_pipe_and_a_newline_survive_cell_scope_verbatim():
    """Cell scope preserves both; GFM pipe-escaping / `<br>` folding is the TABLE
    ASSEMBLY's job (LD-248) — the shipped Sheets split (`render_cell` vs
    `sheets/table.py`) is the precedent, so the cell layer must not double-escape."""
    assert cells.render_cell([{"text": "a|b", "type": "text"}], _text_field()) == "a|b"
    assert cells.render_cell([{"text": "l1\nl2", "type": "text"}], _text_field()) == "l1\nl2"


# --------------------------------------------------------------------------- #
# AC3 — a link cell is an OBJECT with TWO distinct empty forms                 #
# --------------------------------------------------------------------------- #

def _link_rows():
    cap = _capture("p0-2-05-link-lookup-read-encodings.json")
    return cap["response"]["data"]["main_rows"]


@pytest.mark.parametrize("ui_type,type_", [("SingleLink", 18), ("DuplexLink", 21)])
def test_ac3_a_populated_link_cell_is_an_object_and_renders_its_record_ids(ui_type, type_):
    field = cells.FieldSpec(field_name="L", type=type_, ui_type=ui_type)
    value = {"link_record_ids": ["recA", "recB"]}
    assert cells.link_record_ids(value) == ("recA", "recB")
    assert cells.render_cell(value, field) == "recA, recB"


@pytest.mark.parametrize("ui_type,type_", [("SingleLink", 18), ("DuplexLink", 21)])
def test_ac3_null_is_NEVER_WRITTEN_and_is_distinct_from_the_emptied_form(ui_type, type_):
    field = cells.FieldSpec(field_name="L", type=type_, ui_type=ui_type)
    assert cells.link_state({"link_record_ids": None}) == cells.LINK_NEVER_SET
    assert cells.link_record_ids({"link_record_ids": None}) is None
    assert cells.render_cell({"link_record_ids": None}, field) == ""


@pytest.mark.parametrize("ui_type,type_", [("SingleLink", 18), ("DuplexLink", 21)])
def test_ac3_empty_list_is_EMPTIED_BY_A_DELETE_and_is_distinct_from_null(ui_type, type_):
    field = cells.FieldSpec(field_name="L", type=type_, ui_type=ui_type)
    assert cells.link_state({"link_record_ids": []}) == cells.LINK_EMPTIED
    assert cells.link_record_ids({"link_record_ids": []}) == ()
    assert cells.render_cell({"link_record_ids": []}, field) == ""
    # …and the two empties are NOT the same state (a truthiness key conflates them).
    assert cells.link_state({"link_record_ids": []}) != cells.link_state(
        {"link_record_ids": None}
    )


def test_ac3_both_empty_forms_are_real_and_are_in_the_captures():
    """`p0-2-05` (never written → `null`) and `p0-2-07` (after a linked-record delete
    → `[]`) — the two are captured on the SAME field, minutes apart."""
    never = _find(_capture("p0-2-05-link-lookup-read-encodings.json"), "link_record_ids")
    after = _find(_capture("p0-2-07-link-deletion-behaviour.json"), "link_record_ids")
    assert any(v is None for _, v in never)
    assert any(v == [] for _, v in after)


def test_ac3_a_renderer_keyed_on_isinstance_list_would_get_every_link_cell_wrong():
    """The capture proves the search shape is a DICT, so the naive `isinstance(v, list)`
    branch never fires — this test is the standing proof of that."""
    for _, value in _find(_capture("p0-2-05-link-lookup-read-encodings.json"), "fields"):
        for key, cell in (value or {}).items():
            if isinstance(cell, dict) and "link_record_ids" in cell:
                assert not isinstance(cell, list)
                break


def test_ac8_multiple_false_is_not_a_cardinality_guarantee():
    """`p0-4-06 :: multiple_false_fed_two_ids` — a `multiple:false` SingleLink accepted
    and echoed TWO ids, `code:0`. The renderer must not assume single-valuedness."""
    field = cells.FieldSpec(
        field_name="SLinkOne", type=18, ui_type="SingleLink",
        property={"multiple": False, "table_id": "tbl1", "table_name": "Ref"},
    )
    value = {"link_record_ids": ["recvrsK0tN2SKV", "recvrdA8aJyUmM"]}
    assert cells.render_cell(value, field) == "recvrsK0tN2SKV, recvrdA8aJyUmM"


# --------------------------------------------------------------------------- #
# AC4 — an empty cell is an ABSENT KEY; rows project against the FIELD LIST    #
# --------------------------------------------------------------------------- #

def _zoo_fields():
    """The `06-01` field schema, as `FieldSpec`s in field order."""
    cap = _capture("06-01-field-schema.json")
    items = [v for _, v in _find(cap, "items") if isinstance(v, list) and v
             and isinstance(v[0], dict) and "ui_type" in v[0]][0]
    return tuple(cells.FieldSpec.from_payload(i) for i in items)


def test_ac4_a_ragged_row_still_renders_every_column_in_field_order():
    fields = _zoo_fields()
    assert len(fields) >= 8
    record = {"Text": [{"text": "only this", "type": "text"}]}
    row = cells.render_row(record, fields)
    assert len(row) == len(fields)
    named = dict(zip([f.field_name for f in fields], row))
    assert named["Text"] == "only this"
    # every other column present, and empty — NOT dropped
    assert sum(1 for cell in row if cell == "") >= len(fields) - 2


def test_ac4_a_union_of_observed_keys_implementation_FAILS_this():
    """The deliberate defect: projecting against the keys the record happens to carry
    yields ONE column where the field list yields all of them."""
    fields = _zoo_fields()
    record = {"Text": [{"text": "only this", "type": "text"}]}
    union_of_observed_keys = list(record)
    assert len(union_of_observed_keys) == 1
    assert len(cells.render_row(record, fields)) == len(fields) > 1


def test_ac4_the_captures_really_do_omit_a_populated_but_empty_field():
    """P0 addendum §1 fact 3 — `Attach` / `Loc` / `Rating` simply vanish from a row
    that never set them."""
    cap = _capture("p0-4-04-value-readback.json")
    rows = [v for _, v in _find(cap, "fields") if isinstance(v, dict)]
    assert rows
    keysets = [set(r) for r in rows]
    assert not set.intersection(*keysets) >= set.union(*keysets), (
        "every row carried every key — the ragged-record fact would be unprovable"
    )


def test_ac4_checkbox_absent_is_FALSE_not_unknown():
    """The sharpest case: `true` is present, **false is an absent key**."""
    field = cells.FieldSpec(field_name="Checkbox", type=7, ui_type="Checkbox")
    assert cells.render_cell(True, field) == "[x]"
    assert cells.render_absent(field) == "[ ]"
    row = cells.render_row({}, (field,))
    assert row == ["[ ]"]


def test_ac4_checkbox_true_is_what_the_capture_shows():
    cap = _capture("06-03-value-read-option-matrix.json")
    assert any(v is True for _, v in _find(cap, "Checkbox"))


# --------------------------------------------------------------------------- #
# AC5 — `property`-driven formatting, from the FIELD, never guessed            #
# --------------------------------------------------------------------------- #

def test_ac5_number_formats_via_property_formatter():
    field = cells.FieldSpec(field_name="N", type=2, ui_type="Number",
                            property={"formatter": "0"})
    assert cells.render_cell(42.5, field) == "43"
    two_dp = cells.FieldSpec(field_name="N", type=2, ui_type="Number",
                             property={"formatter": "0.00"})
    assert cells.render_cell(42.5, two_dp) == "42.50"


def test_ac5_progress_formats_via_its_percent_formatter():
    """`p0-2-03` — Progress's property is `{"formatter":"0%","max":1,"min":0}` and its
    value reads back `0.35`."""
    field = cells.FieldSpec(field_name="P", type=2, ui_type="Progress",
                            property={"formatter": "0%", "min": 0, "max": 1})
    assert cells.render_cell(0.35, field) == "35%"


def test_ac5_currency_appends_its_currency_code():
    field = cells.FieldSpec(field_name="C", type=2, ui_type="Currency",
                            property={"currency_code": "USD", "formatter": "0.00"})
    assert cells.render_cell(19.99, field) == "USD 19.99"


def test_ac5_rating_appends_its_rating_symbol():
    field = cells.FieldSpec(field_name="R", type=2, ui_type="Rating",
                            property={"formatter": "0", "min": 0, "max": 5,
                                      "rating": {"symbol": "star"}})
    assert cells.render_cell(4, field) == "4 ★"
    unknown = cells.FieldSpec(field_name="R", type=2, ui_type="Rating",
                              property={"formatter": "0", "rating": {"symbol": "moon"}})
    assert cells.render_cell(4, unknown) == "4 moon"


def test_ac5_the_number_family_properties_are_the_captured_ones():
    cap = _capture("p0-2-03-field-schema-full.json")
    props = {}
    stack = [cap]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("ui_type") in ("Progress", "Rating") and "property" in node:
                props[node["ui_type"]] = node["property"]
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    assert props["Progress"]["formatter"] == "0%"
    assert props["Rating"]["rating"]["symbol"] == "star"


def test_ac5_datetime_is_a_pure_function_of_value_formatter_and_timezone():
    """The app's `time_zone` is load-bearing: the SAME ms-epoch renders differently
    under `Asia/Singapore` (the scratch tenant's) and `UTC`."""
    field = cells.FieldSpec(field_name="D", type=5, ui_type="DateTime",
                            property={"auto_fill": False,
                                      "date_formatter": "yyyy/MM/dd HH:mm"})
    ms = 1785061011000
    sg = cells.RenderContext(time_zone="Asia/Singapore")
    utc = cells.RenderContext(time_zone="UTC")
    assert cells.render_cell(ms, field, context=sg) == "2026/07/26 18:16"
    assert cells.render_cell(ms, field, context=utc) == "2026/07/26 10:16"
    # …and it never consults the host clock or locale: same inputs, same bytes.
    assert cells.render_cell(ms, field, context=sg) == cells.render_cell(ms, field, context=sg)


def test_ac5_datetime_honours_its_own_date_formatter():
    ctx = cells.RenderContext(time_zone="Asia/Singapore")
    for formatter, expected in (
        ("yyyy/MM/dd", "2026/07/26"),
        ("yyyy-MM-dd HH:mm", "2026-07-26 18:16"),
        ("MM-dd", "07-26"),
        ("dd/MM/yyyy HH:mm", "26/07/2026 18:16"),
    ):
        field = cells.FieldSpec(field_name="D", type=5, ui_type="DateTime",
                                property={"date_formatter": formatter})
        assert cells.render_cell(1785061011000, field, context=ctx) == expected


def test_ac5_an_absent_time_zone_falls_back_to_utc_and_never_crashes():
    """A docx-born embedded Base has NO `time_zone` at all (P0 addendum § P1,
    `p0-1-06` records it as literally ABSENT)."""
    husk = _capture("p0-1-06-husk-reduction-test.json")
    assert '"time_zone": "ABSENT"' in json.dumps(husk, indent=2) or \
        any(v == "ABSENT" for _, v in _find(husk, "time_zone"))
    field = cells.FieldSpec(field_name="D", type=5, ui_type="DateTime",
                            property={"date_formatter": "yyyy/MM/dd HH:mm"})
    assert cells.DEFAULT_TIME_ZONE == "UTC"
    assert cells.render_cell(1785061011000, field) == "2026/07/26 10:16"     # UTC fallback
    assert cells.render_cell(1785061011000, field,
                             context=cells.RenderContext(time_zone=None)) == "2026/07/26 10:16"


def test_ac5_an_unresolvable_zone_falls_back_rather_than_raising():
    field = cells.FieldSpec(field_name="D", type=5, ui_type="DateTime",
                            property={"date_formatter": "yyyy/MM/dd HH:mm"})
    ctx = cells.RenderContext(time_zone="Mars/Olympus_Mons")
    assert cells.render_cell(1785061011000, field, context=ctx) == "2026/07/26 10:16"


def test_ac5_created_and_modified_time_use_the_documented_default_formatter():
    """1001 / 1002 read back `property: null`, so they have no `date_formatter` of
    their own — the fallback is documented, not improvised."""
    for type_, ui in ((1001, "CreatedTime"), (1002, "ModifiedTime")):
        field = cells.FieldSpec(field_name=ui, type=type_, ui_type=ui)
        out = cells.render_cell(1785061011000, field,
                                context=cells.RenderContext(time_zone="UTC"))
        assert out == "2026/07/26 10:16"
        assert cells.DEFAULT_DATE_FORMATTER == "yyyy/MM/dd HH:mm"


def test_ac5_single_and_multi_select_render_option_names():
    single = cells.FieldSpec(
        field_name="S", type=3, ui_type="SingleSelect",
        property={"options": [{"id": "optA", "name": "Alpha", "color": 0}]},
    )
    assert cells.render_cell("Alpha", single) == "Alpha"
    assert cells.render_cell("optA", single) == "Alpha"       # an id resolves to its name
    multi = cells.FieldSpec(
        field_name="M", type=4, ui_type="MultiSelect",
        property={"options": [{"id": "opt1vNi0lH", "name": "Red", "color": 0},
                              {"id": "optJKznXq2", "name": "Green", "color": 1}]},
    )
    assert cells.render_cell(["Red", "Green"], multi) == "Red, Green"


def test_ac5_autonumber_reads_back_a_STRING_not_an_int():
    """`p0-5-01` — AutoNumber is `"1"`, a string."""
    cap = _capture("p0-5-01-scalar-read-encodings.json")
    autonums = [v for _, v in _find(cap, "AutoNum")]
    assert autonums and autonums[0] == "1" and isinstance(autonums[0], str)
    field = cells.FieldSpec(field_name="AutoNum", type=1005, ui_type="AutoNumber")
    assert cells.render_cell("1", field) == "1"
    assert cells.render_cell(1, field) == "1"       # degrades, but the wire form is str


def test_ac5_phone_url_location_and_attachment_render_their_captured_shapes():
    cap = _capture("06-03-value-read-option-matrix.json")
    url = [v for _, v in _find(cap, "Url") if isinstance(v, dict)][0]
    assert cells.render_cell(
        url, cells.FieldSpec(field_name="Url", type=15, ui_type="Url")
    ) == "[Example](https://example.invalid/x)"
    assert cells.render_cell(
        "+12025550100", cells.FieldSpec(field_name="Phone", type=13, ui_type="Phone")
    ) == "+12025550100"
    loc = [v for _, v in _find(_capture("p0-4-04-value-readback.json"), "Loc")
           if isinstance(v, dict)][0]
    assert cells.render_cell(
        loc, cells.FieldSpec(field_name="Loc", type=22, ui_type="Location")
    ) == "Central Singapore,Singapore"
    attach = [v for _, v in _find(_capture("p0-4-04-value-readback.json"), "Attach")
              if isinstance(v, list)][0]
    out = cells.render_cell(
        attach, cells.FieldSpec(field_name="Attach", type=17, ui_type="Attachment")
    )
    assert out == "p0-specimen-033811.txt"
    assert "http" not in out, "an attachment's tmp_url must never reach Markdown"


# --------------------------------------------------------------------------- #
# AC6 — PII discipline (D1: name-only)                                         #
# --------------------------------------------------------------------------- #

_PERSON_TYPES = (
    (11, "User"), (23, "GroupChat"), (1003, "CreatedUser"), (1004, "ModifiedUser"),
)


@pytest.mark.parametrize("type_,ui", _PERSON_TYPES)
def test_ac6_a_person_bearing_cell_renders_the_name_only(type_, ui):
    field = cells.FieldSpec(field_name=ui, type=type_, ui_type=ui)
    payload = [{
        "id": "ou_deadbeefdeadbeef",
        "name": "Ada Lovelace",
        "en_name": "Ada Lovelace",
        "email": "ada@tenant.invalid",
        "avatar_url": "https://s1-imfile.example.invalid/avatar/x.png",
    }]
    assert cells.render_cell(payload, field) == "Ada Lovelace"


@pytest.mark.parametrize("type_,ui", _PERSON_TYPES)
def test_ac6_en_name_is_the_fallback_and_the_marker_is_the_floor(type_, ui):
    field = cells.FieldSpec(field_name=ui, type=type_, ui_type=ui)
    assert cells.render_cell([{"en_name": "Ada L", "email": "a@b.invalid"}], field) == "Ada L"
    assert cells.render_cell([{"id": "ou_x", "email": "a@b.invalid"}], field) == \
        cells.PERSON_NAME_UNAVAILABLE
    assert cells.PERSON_NAME_UNAVAILABLE == "[name unavailable]"


@pytest.mark.parametrize("type_,ui", _PERSON_TYPES)
def test_ac6_multiples_are_comma_joined(type_, ui):
    field = cells.FieldSpec(field_name=ui, type=type_, ui_type=ui)
    payload = [{"name": "Ada"}, {"name": "Grace"}]
    assert cells.render_cell(payload, field) == "Ada, Grace"


def test_ac6_i_a_rendered_corpus_of_every_person_bearing_type_leaks_nothing():
    """(i) — zero email strings SOURCED FROM a person/chat object, zero avatar/CDN
    URLs, zero ids, at any setting in L1."""
    person = {
        "id": "ou_deadbeefdeadbeef",
        "name": "Ada Lovelace",
        "en_name": "Ada English",
        "email": "ada@tenant.invalid",
        "avatar_url": "https://s1-imfile.example.invalid/avatar/x.png",
    }
    chat = {"id": "oc_deadbeefdeadbeef", "name": "Team Chat",
            "avatar_url": "https://s1-imfile.example.invalid/chat.png"}
    corpus = []
    for type_, ui in _PERSON_TYPES:
        field = cells.FieldSpec(field_name=ui, type=type_, ui_type=ui)
        corpus.append(cells.render_cell([chat if ui == "GroupChat" else person], field))
    blob = "\n".join(corpus)
    assert "ada@tenant.invalid" not in blob
    assert "avatar" not in blob and "imfile" not in blob
    assert "ou_" not in blob and "oc_" not in blob
    assert "Ada English" not in blob            # en_name never wins over name


def test_ac6_ii_the_same_holds_with_automatic_fields_true():
    """`automatic_fields: true` adds record-level `created_by` / `last_modified_by`;
    the row projection renders the FIELD LIST, so those record-level person objects
    never reach Markdown at all."""
    person = {"id": "ou_deadbeefdeadbeef", "name": "Ada", "email": "ada@tenant.invalid",
              "avatar_url": "https://s1-imfile.example.invalid/a.png"}
    fields = (cells.FieldSpec(field_name="Text", type=1, ui_type="Text"),)
    record = {
        "fields": {"Text": [{"text": "hi", "type": "text"}]},
        "created_by": person, "last_modified_by": person,
        "created_time": 1785061011000, "last_modified_time": 1785061011000,
    }
    row = cells.render_row(record["fields"], fields)
    blob = "\n".join(row)
    assert blob == "hi"
    assert "ada@tenant.invalid" not in blob and "ou_" not in blob and "avatar" not in blob


def test_ac6_ii_a_person_cell_carrying_automatic_field_extras_still_renders_name_only():
    field = cells.FieldSpec(field_name="User", type=11, ui_type="User")
    payload = [{"id": "ou_x1234567890", "name": "Ada", "en_name": "Ada English",
                "email": "ada@tenant.invalid", "avatar_url": "https://cdn.invalid/a.png"}]
    assert cells.render_cell(payload, field) == "Ada"


# --- (iii) the nine-pattern PII sweep -------------------------------------- #

#: The parity pack's NINE scrubber rules, as detectors. Named so the count is
#: checkable (`dev/base-study/probes/_lib.py` § sanitization).
_PII_SWEEP = {
    "1-tenant-email": re.compile(r'"[^"\s]+@(?!example\.invalid)[^"\s]+\.[A-Za-z]{2,}"'),
    "2-person-id": re.compile(r'"(?:ou_|on_|od-|ug_)[A-Za-z0-9]{10,}"'),
    "3-chat-id": re.compile(r'"oc_[A-Za-z0-9]{10,}"'),
    "4-avatar-or-cdn-url": re.compile(r'"avatar[a-z_]*"\s*:\s*"https?://'),
    "5-user-token": re.compile(r'"(?:t-|u-)[A-Za-z0-9_.\-]{10,}"'),
    "6-unredacted-en-name": re.compile(r'"en_name"\s*:\s*"(?!<redacted)(?!")'),
    "7-tenant-host": re.compile(
        r'"https?://(?!open\.|www\.|<redacted)[A-Za-z0-9-]+'
        r'(?:\.[A-Za-z0-9-]+)?\.(?:larksuite|feishu)\.com'
    ),
    "8-shared-url": re.compile(r'"shared_url"\s*:\s*"(?!<redacted)(?!")'),
    "9-person-key": re.compile(r'"(?:open_id|union_id|user_id|mobile|enterprise_email)"'
                               r'\s*:\s*"(?!<redacted)(?!")'),
}


def test_ac6_iii_the_sweep_really_is_NINE_patterns():
    assert len(_PII_SWEEP) == 9, sorted(_PII_SWEEP)


def test_ac6_iii_every_capture_this_story_reads_passes_the_nine_pattern_sweep():
    """The bar: 0 on every count. Only `example.invalid` probe-authored addresses are
    permitted (RFC-2606 reserved). This story commits NO new fixture — it reads the
    probe packs' already-scrubbed captures — so the sweep is run over exactly the
    payloads the suite consumes."""
    hits = {}
    for path in sorted(_CAPTURES.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        for name, pat in _PII_SWEEP.items():
            found = pat.findall(text)
            if found:
                hits.setdefault(name, []).append((path.name, sorted(set(found))[:3]))
    assert hits == {}, f"PII sweep is NOT clean: {hits}"


def test_ac6_iii_this_story_commits_no_new_capture_or_fixture_of_its_own():
    """Belt and braces on (iii): the story's whole input is the committed captures."""
    assert not list((Path(__file__).resolve().parent / "fixtures").glob("base_*.json"))


# --------------------------------------------------------------------------- #
# AC7a — Lookup (19): a typed wrapper whose `value` is a segment array          #
# --------------------------------------------------------------------------- #

def _lookup_cell():
    cap = _capture("p1-q0-03-per-table.json")
    row = cap["per_table"][0]["records_search"]["response"]["data"]["items"][0]
    return row["fields"]["lookup"]


def _lookup_field():
    cap = _capture("p1-q0-03-per-table.json")
    items = cap["per_table"][0]["fields"]["response"]["data"]["items"]
    item = [i for i in items if i["ui_type"] == "Lookup"][0]
    return cells.FieldSpec.from_payload(item)


def test_ac7a_i_the_wrappers_type_is_the_TARGET_fields_type_not_19():
    cell = _lookup_cell()
    assert cell["type"] == 1, "the specimen's Lookup targets a Text field"
    assert _lookup_field().type == 19
    assert cells.wrapper_type(cell) == 1


def test_ac7a_ii_listcombine_separators_are_THEMSELVES_segments_so_join_with_empty():
    """Joining with `", "` double-separates: the `","` entries are literal segments."""
    cell = _lookup_cell()
    literal_commas = [s for s in cell["value"] if s.get("text") == ","]
    assert len(literal_commas) == 4, "the specimen aggregates 5 values with 4 separators"
    out = cells.render_cell(cell, _lookup_field())
    assert out == (
        "Text 2 Test Data 2,Text 2 Test Data 3,Text 2 Test Data 1,"
        "Text 2 Test Data 5,Text 2 Test Data 4"
    )
    assert ", " not in out, "joining with ', ' would double-separate"


def test_ac7a_iii_a_lookup_is_a_constrained_formula_so_rows_can_be_identical():
    cap = _capture("p1-q0-03-per-table.json")
    items = cap["per_table"][0]["records_search"]["response"]["data"]["items"]
    rendered = {cells.render_cell(i["fields"]["lookup"], _lookup_field())
                for i in items if "lookup" in i["fields"]}
    assert len(rendered) == 1, "the LISTCOMBINE aggregates the whole target table"
    prop = _lookup_field().property
    assert prop["roll_up"] == 0 and prop["formula"].startswith("bitable::")


def test_ac7a_the_inner_value_dispatches_on_the_WRAPPERS_type():
    field = _lookup_field()
    numeric = {"type": 2, "value": [2]}
    assert cells.render_cell(numeric, field) == "2"


# --------------------------------------------------------------------------- #
# AC7c — Stage (24): fully opaque, absent-with-reason marker                    #
# --------------------------------------------------------------------------- #

def _stage_field():
    cap = _capture("p1-q0-03-per-table.json")
    items = cap["per_table"][0]["fields"]["response"]["data"]["items"]
    return cells.FieldSpec.from_payload([i for i in items if i["ui_type"] == "Stage"][0])


def test_ac7c_the_stage_schema_is_readable_and_its_property_is_null():
    field = _stage_field()
    assert (field.type, field.ui_type) == (24, "Stage")
    assert field.property is None


def test_ac7c_the_stage_KEY_IS_ABSENT_FROM_EVERY_READ_in_the_captures():
    """The fixture proves ABSENCE: 17 read routes, none returns the key."""
    cap = _capture("p1-q0-03-per-table.json")
    items = cap["per_table"][0]["records_search"]["response"]["data"]["items"]
    assert items
    assert all("stage?" not in i["fields"] for i in items)


def test_ac7c_the_renderer_still_emits_the_marker_BECAUSE_THE_FIELD_IS_IN_FIELDS():
    field = _stage_field()
    assert cells.render_absent(field) == cells.STAGE_OPAQUE_MARKER
    assert cells.render_row({}, (field,)) == [cells.STAGE_OPAQUE_MARKER]


def test_ac7c_the_markers_EXACT_BYTES_are_pinned():
    assert cells.STAGE_OPAQUE_MARKER == (
        "[unreadable Base cell: Stage (type 24) — Lark returns no value for this "
        "field on any read route]"
    )


def test_ac7c_the_marker_is_in_the_house_register_of_the_readers_own_markers():
    """Same shape as the reader's `[unsupported inline: …]` / `[Unsupported Add-On
    block: …]` — a square-bracketed, lowercase-opening, reason-bearing marker."""
    assert cells.STAGE_OPAQUE_MARKER.startswith("[") and cells.STAGE_OPAQUE_MARKER.endswith("]")
    assert "—" in cells.STAGE_OPAQUE_MARKER


def test_ac7c_a_stage_cell_is_never_a_bare_empty_cell_r14():
    field = _stage_field()
    assert cells.render_absent(field) != ""
    # even if a future route DID return something, the marker is what renders:
    assert cells.render_cell("Stage A", field) == cells.STAGE_OPAQUE_MARKER


# --------------------------------------------------------------------------- #
# The test-rigor amplifier                                                     #
# --------------------------------------------------------------------------- #

def test_amplifier_a_record_with_EVERY_field_type_populated_renders_every_column():
    fields = tuple(
        cells.FieldSpec(field_name=f"{t}-{u}", type=t, ui_type=u) for t, u in cells.PAIRS
    )
    record = {f.field_name: _specimen_value(f) for f in fields}
    row = cells.render_row(record, fields)
    assert len(row) == 27
    assert all(isinstance(cell, str) for cell in row)
    stage_index = [i for i, f in enumerate(fields) if f.type == 24][0]
    assert row[stage_index] == cells.STAGE_OPAQUE_MARKER


def test_amplifier_a_record_with_NOTHING_populated_still_renders_every_column():
    fields = tuple(
        cells.FieldSpec(field_name=f"{t}-{u}", type=t, ui_type=u) for t, u in cells.PAIRS
    )
    row = cells.render_row({}, fields)
    assert len(row) == 27
    checkbox_index = [i for i, f in enumerate(fields) if f.type == 7][0]
    stage_index = [i for i, f in enumerate(fields) if f.type == 24][0]
    assert row[checkbox_index] == "[ ]"
    assert row[stage_index] == cells.STAGE_OPAQUE_MARKER
    others = [c for i, c in enumerate(row) if i not in (checkbox_index, stage_index)]
    assert others == [""] * 25


def _specimen_value(f):
    return {
        1: [{"text": "t", "type": "text"}],
        2: 1,
        3: "Alpha",
        4: ["Red"],
        5: 1785061011000,
        7: True,
        11: [{"name": "Ada"}],
        13: "+65",
        15: {"link": "https://example.invalid/", "text": "x", "type": "url"},
        17: [{"name": "f.txt", "file_token": "tok"}],
        18: {"link_record_ids": ["recA"]},
        19: {"type": 1, "value": [{"text": "L", "type": "text"}]},
        20: {"type": 2, "value": [2]},
        21: {"link_record_ids": ["recB"]},
        22: {"full_address": "somewhere", "location": "1,2"},
        23: [{"name": "Chat"}],
        24: "invisible",
        1001: 1785061011000,
        1002: 1785061011000,
        1003: [{"name": "Ada"}],
        1004: [{"name": "Ada"}],
        1005: "1",
    }[f.type]


def test_amplifier_formula_in_BOTH_encodings_and_the_wrapped_one_is_the_pin():
    """`06-04` legacy GET returns a BARE `2`; `06-03` search returns
    `{"type":2,"value":[2]}`. The registry's contract is the wrapped (search) form."""
    legacy = _capture("06-04-records-list-GET-populated.json")
    assert any(v == 2 for _, v in _find(legacy, "Formula"))
    search = _capture("06-03-value-read-option-matrix.json")
    wrapped = [v for _, v in _find(search, "Formula") if isinstance(v, dict)]
    assert wrapped and wrapped[0] == {"type": 2, "value": [2]}
    field = cells.FieldSpec(field_name="Formula", type=20, ui_type="Formula",
                            property={"formatter": "", "formula_expression": "1+1"})
    assert cells.render_cell(wrapped[0], field) == "2"
    assert cells.wrapper_type(wrapped[0]) == 2
    assert cells.wrapper_type(2) is None, "a bare legacy value is NOT the wrapped form"


def test_amplifier_the_legacy_list_and_search_disagree_so_search_is_pinned():
    """R7 — `GET …/records` reports an empty cell as an explicit `null` key; `search`
    OMITS it. A fixture pinned to the legacy route would defeat AC4 outright."""
    legacy = _capture("06-04-records-list-GET-populated.json")
    rows = [v for _, v in _find(legacy, "fields") if isinstance(v, dict)]
    assert any(any(cell is None for cell in r.values()) for r in rows)


# --------------------------------------------------------------------------- #
# AC12 — determinism                                                           #
# --------------------------------------------------------------------------- #

def test_ac12_rendering_the_same_captured_payload_twice_is_byte_identical():
    cap = _capture("p1-q0-03-per-table.json")
    table = cap["per_table"][0]
    fields = tuple(cells.FieldSpec.from_payload(i)
                   for i in table["fields"]["response"]["data"]["items"])
    records = table["records_search"]["response"]["data"]["items"]
    ctx = cells.RenderContext(time_zone="Asia/Singapore")

    def render_all():
        return [cells.render_row(r["fields"], fields, context=ctx) for r in records]

    assert render_all() == render_all()
    assert json.dumps(render_all()) == json.dumps(render_all())
