"""Offline unit tests for the typed cell model (LD-115).

The typed cell model is the **additive** (D3) parallel surface the write-gate
differ (S3) and the MD fidelity gains (S4) consume — richer than L1's per-cell
string render, carrying:

* **value** — raw (`UnformattedValue`) + display (`FormattedValue`) **dual**;
* **`segmentStyle` runs** + **hyperlink / mention / multi-select structure**;
* the export-only **fidelity** — numFmt pattern + cell-level bold/italic/fill (S1);
* **merge membership** — anchor / covered / none, with the region.

The whole story is proven **offline** and **additive**: the shipped `render_cell`
/ table-assembly MD path is untouched (a source-import guard here + goldens
zero-drift at verify time prove no MD change from the model alone), and the model
round-trips through JSON (serializable).

Fixtures: the committed values captures (`tests/captures/sheets-spike/captures/02-*.json`,
the raw+display pairs) + the real Merged-tab merge geometry
(`00-scratch-tabs.json`) + `ExportedCell`/`ExportedSheet` from the S1 reader (the
export-fidelity join) synthesized via the reader's own reference workbook.
"""
import json
from pathlib import Path

import pytest

from larkdocio.sheets.cell_model import (
    DocMention,
    Hyperlink,
    MergeMembership,
    MultiSelect,
    TextRun,
    TypedCell,
    UserMention,
    merge_membership_at,
    parse_segments,
)
from larkdocio.sheets.export_reader import ExportedCell, ExportedSheet
from larkdocio.sheets.models import Merge, SheetTab
from larkdocio.sheets.render import render_cell

_CAPTURES = Path(__file__).resolve().parent.parent / "tests" / "captures" / "sheets-spike" / "captures"


# --------------------------------------------------------------------------- #
# Wire-shape fixtures (the exact live shapes, from the LD-100 captures)         #
# --------------------------------------------------------------------------- #

# A 3-run styled cell (live shape — 02-types-comparison.json "styled text runs").
_STYLED_RUNS = [
    {"type": "text", "text": "bold start",
     "segmentStyle": {"bold": True, "italic": False, "strikeThrough": False,
                      "underline": False, "foreColor": "#000000", "fontSize": 10}},
    {"type": "text", "text": " plain middle",
     "segmentStyle": {"bold": False, "italic": False, "strikeThrough": False,
                      "underline": False, "foreColor": "#000000", "fontSize": 10}},
    {"type": "text", "text": " italic end",
     "segmentStyle": {"bold": False, "italic": True, "strikeThrough": False,
                      "underline": False, "foreColor": "#000000", "fontSize": 10}},
]

# A hyperlink cell (live shape).
_HYPERLINK = [{"cellPosition": None, "link": "https://www.google.com",
               "text": "https://www.google.com", "type": "url"}]

# A @user mention (live rev-36 shape — 02-hand-adds-FormattedValue.json).
_USER_MENTION = {
    "type": "mention", "mentionType": 0, "userID": "ou_exampleowner00000000000000000001",
    "name": "Example User", "en_name": "Example User", "text": "@Example User",
    "link": "https://example.invalid/avatar",
}

# A doc-link mention (live shape — link URL-encoded on the wire).
_DOC_MENTION = {
    "type": "mention", "mentionType": 22, "text": "Larkdocio Scratch",
    "link": "https%3A%2F%2Fyour-domain.larksuite.com%2Fdocx%2FDocScratchExample0000000001",
    "token": "DocScratchExample0000000001",
}

# A multi-select — the WRITE object form and the READ comma-joined-string form.
_MULTI_OBJECT = {"type": "multipleValue",
                 "values": [{"type": "text", "text": "Red"}, {"type": "text", "text": "Green"}]}
_MULTI_OBJECT_BARE = {"type": "multipleValue", "values": ["Red", "Green"]}
_MULTI_STRING_READ = "Red,Green"          # live read form (no space)
_MULTI_STRING_WRITTEN = "Red, Green"      # the D5b write-normalized display


def _merged_tab() -> SheetTab:
    """The real Merged tab (its 5 merges) from the committed tab-query capture."""
    data = json.loads((_CAPTURES / "00-scratch-tabs.json").read_text(encoding="utf-8"))["data"]
    for s in data["sheets"]:
        if s.get("title") == "Merged":
            return SheetTab.from_dict(s)
    raise AssertionError("Merged tab not found in 00-scratch-tabs.json")


# --------------------------------------------------------------------------- #
# AC1 — the model exists; construct from a values cell + an export style, read  #
#       every field back                                                        #
# --------------------------------------------------------------------------- #

def test_ac1_construct_from_values_and_export_reads_every_field_back():
    exported = ExportedCell(ref="A1", value=0.1234, bold=True, italic=False,
                            fill_rgb="FFFFFF00", num_fmt="0.00%")
    cell = TypedCell.from_values(
        raw=0.1234, display="12.34%", exported_cell=exported,
        merge=MergeMembership(role="anchor", region=Merge(0, 0, 0, 2)),
    )
    # value — raw + display dual
    assert cell.raw == 0.1234
    assert cell.display == "12.34%"
    # export-only fidelity — numFmt pattern + cell-level font/fill
    assert cell.fidelity is not None
    assert cell.fidelity.num_fmt == "0.00%"
    assert cell.fidelity.bold is True
    assert cell.fidelity.italic is False
    assert cell.fidelity.fill_rgb == "FFFFFF00"
    # merge membership
    assert cell.merge.role == "anchor"
    assert cell.merge.is_anchor and cell.merge.is_merged
    assert cell.merge.region == Merge(0, 0, 0, 2)


# --------------------------------------------------------------------------- #
# AC3 — dual value + fidelity join (with-export and no-export paths)            #
# --------------------------------------------------------------------------- #

def test_ac3_no_export_degrades_gracefully_fidelity_none_never_raises():
    cell = TypedCell.from_values(raw=0.1234, display="12.34%")  # no exported_cell
    assert cell.raw == 0.1234 and cell.display == "12.34%"
    assert cell.fidelity is None            # graceful — never half-set
    # reading a fidelity field goes through a None-safe accessor, never raises
    assert cell.num_fmt is None
    assert cell.is_bold is None
    assert cell.fill_rgb is None


def test_ac3_with_export_join_populates_fidelity():
    exported = ExportedCell(ref="B2", value=1234.56, bold=False, italic=True,
                            fill_rgb=None, num_fmt='"$"#,##0.00')
    cell = TypedCell.from_values(raw=1234.56, display="$1,234.56", exported_cell=exported)
    assert cell.num_fmt == '"$"#,##0.00'
    assert cell.is_bold is False and cell.is_italic is True
    assert cell.fill_rgb is None            # export present but no fill on this cell


@pytest.mark.parametrize("raw,display", [
    (0.1234, "12.34%"),          # percentage — the canonical dual pair
    (1234.56, "$1,234.56"),      # currency
    (46229, "7/26/2026"),        # date (serial vs display)
    (46229.645833333336, "7/26/2026 15:30"),  # datetime
    (12345700000000, "1.23E+13"),             # scientific
])
def test_dual_value_consistency_raw_and_display_both_carried(raw, display):
    cell = TypedCell.from_values(raw=raw, display=display)
    assert cell.raw == raw
    assert cell.display == display
    assert cell.raw != cell.display          # the whole point of the dual


# --------------------------------------------------------------------------- #
# Amplifier — every SHEETS.md cell type mapped into the model (round-trip each) #
# --------------------------------------------------------------------------- #

_EVERY_CELL_TYPE = [
    ("string", "hello world", "hello world", ()),
    ("newline-string", "line one\nline two", "line one\nline two", ()),
    ("int", 42, 42, ()),
    ("float", 3.14159, 3.14159, ()),
    ("percentage", 0.1234, "12.34%", ()),
    ("currency", 1234.56, "$1,234.56", ()),
    ("scientific", 12345700000000, "1.23E+13", ()),
    ("date", 46229, "7/26/2026", ()),
    ("datetime", 46229.645833333336, "7/26/2026 15:30", ()),
    ("boolean", True, True, ()),
    ("formula", 60, 60, ()),
    ("hyperlink", _HYPERLINK, _HYPERLINK, (Hyperlink,)),
    ("styled-runs", _STYLED_RUNS, _STYLED_RUNS, (TextRun, TextRun, TextRun)),
    ("user-mention", _USER_MENTION, _USER_MENTION, (UserMention,)),
    ("doc-mention", _DOC_MENTION, _DOC_MENTION, (DocMention,)),
    ("dropdown-single", "Single Option 1", "Single Option 1", ()),
    ("dropdown-multi-object", _MULTI_OBJECT, _MULTI_OBJECT, (MultiSelect,)),
    ("null", None, None, ()),
]


@pytest.mark.parametrize("label,raw,display,seg_types",
                         _EVERY_CELL_TYPE, ids=[c[0] for c in _EVERY_CELL_TYPE])
def test_every_cell_type_maps_into_model(label, raw, display, seg_types):
    cell = TypedCell.from_values(raw=raw, display=display)
    assert cell.raw == raw and cell.display == display
    assert tuple(type(s) for s in cell.segments) == seg_types
    # every mapped cell survives a JSON round-trip (serializable)
    assert TypedCell.from_dict(json.loads(json.dumps(cell.to_dict()))) == cell


# --------------------------------------------------------------------------- #
# Segment structure — styled runs, dropped color, hyperlink, mentions          #
# --------------------------------------------------------------------------- #

def test_styled_runs_parse_into_typed_runs_with_style():
    segs = parse_segments(_STYLED_RUNS)
    assert [s.text for s in segs] == ["bold start", " plain middle", " italic end"]
    assert segs[0].style.bold is True and segs[0].style.italic is False
    assert segs[2].style.italic is True and segs[2].style.bold is False
    assert all(isinstance(s, TextRun) for s in segs)


def test_dropped_color_and_fontsize_captured_in_model_but_absent_from_md():
    # A run with a real color + font size: captured in the typed model (L2),
    # dropped by the shared serializer at render (parity with docx color-drop).
    run = [{"type": "text", "text": "loud",
            "segmentStyle": {"bold": True, "italic": True, "strikeThrough": True,
                             "underline": True, "foreColor": "rgb(255, 0, 0)", "fontSize": 14}}]
    seg = parse_segments(run)[0]
    assert seg.style.fore_color == "rgb(255, 0, 0)"   # captured in the model
    assert seg.style.font_size == 14
    out = render_cell(run)
    assert out == "**_~~<u>loud</u>~~_**"             # marks survive
    assert "rgb" not in out and "255" not in out       # color absent from MD


def test_dropped_cell_fill_captured_in_fidelity_absent_from_md():
    exported = ExportedCell(ref="A1", value="x", bold=False, italic=False,
                            fill_rgb="FFFFFF00", num_fmt=None)
    cell = TypedCell.from_values(raw="x", display="x", exported_cell=exported)
    assert cell.fill_rgb == "FFFFFF00"                 # captured in the model
    assert "FFFF" not in render_cell(cell.display)     # no color in the MD render


def test_hyperlink_parses_into_typed_hyperlink():
    seg = parse_segments(_HYPERLINK)[0]
    assert isinstance(seg, Hyperlink)
    assert seg.text == "https://www.google.com"
    assert seg.link == "https://www.google.com"


def test_user_mention_parses_into_typed_mention():
    seg = parse_segments(_USER_MENTION)[0]
    assert isinstance(seg, UserMention)
    assert seg.text == "@Example User"
    assert seg.user_id == "ou_exampleowner00000000000000000001"
    assert seg.name == "Example User"


def test_user_mention_older_capture_token_id_field():
    # The older committed capture carries the id in `token`, not `userID`.
    seg = parse_segments({"type": "mention", "mentionType": 0, "token": "ou_x",
                          "name": "By Token", "text": "@By Token"})[0]
    assert isinstance(seg, UserMention)
    assert seg.user_id == "ou_x"


def test_doc_link_mention_parses_into_typed_doc_mention():
    seg = parse_segments(_DOC_MENTION)[0]
    assert isinstance(seg, DocMention)
    assert seg.text == "Larkdocio Scratch"
    # the link is stored as the raw wire form (structure, not render)
    assert seg.link == _DOC_MENTION["link"]


# --------------------------------------------------------------------------- #
# Amplifier — multi-select: BOTH wire forms normalize into the model the same   #
# --------------------------------------------------------------------------- #

def test_multi_select_both_wire_forms_normalize_identically():
    from_object = MultiSelect.from_wire(_MULTI_OBJECT)
    from_object_bare = MultiSelect.from_wire(_MULTI_OBJECT_BARE)
    from_read_string = MultiSelect.from_wire(_MULTI_STRING_READ)
    from_written_string = MultiSelect.from_wire(_MULTI_STRING_WRITTEN)
    expected = MultiSelect(options=("Red", "Green"))
    assert from_object == expected
    assert from_object_bare == expected
    assert from_read_string == expected        # "Red,Green" (no space)
    assert from_written_string == expected     # "Red, Green" (write-normalized)
    # all four are the identical model value
    assert from_object == from_object_bare == from_read_string == from_written_string


def test_multi_select_object_in_cell_becomes_a_multiselect_segment():
    cell = TypedCell.from_values(raw=_MULTI_OBJECT, display=_MULTI_OBJECT)
    assert len(cell.segments) == 1
    assert cell.segments[0] == MultiSelect(options=("Red", "Green"))


def test_multi_select_empty_and_defensive_forms():
    assert MultiSelect.from_wire("") == MultiSelect(options=())
    assert MultiSelect.from_wire({"type": "multipleValue"}) == MultiSelect(options=())
    assert MultiSelect.from_wire(None) == MultiSelect(options=())


# --------------------------------------------------------------------------- #
# Amplifier — merge membership against the real Merged-tab fixture               #
# --------------------------------------------------------------------------- #

def test_merge_membership_against_merged_tab_fixture():
    tab = _merged_tab()
    merges = tab.merges
    # A1:C1 = Merge(0,0,0,2): A1 anchor, B1/C1 covered, D1 none.
    assert merge_membership_at(0, 0, merges).role == "anchor"
    assert merge_membership_at(0, 1, merges).role == "covered"
    assert merge_membership_at(0, 2, merges).role == "covered"
    assert merge_membership_at(0, 3, merges).role == "none"
    # A3:A5 = Merge(2,4,0,0): A3 anchor, A4/A5 covered (the vertical boundary merge).
    assert merge_membership_at(2, 0, merges).role == "anchor"
    assert merge_membership_at(3, 0, merges).role == "covered"
    assert merge_membership_at(4, 0, merges).role == "covered"
    # B7:D8 = Merge(6,7,1,3): B7 anchor, the 2x3 block covered.
    assert merge_membership_at(6, 1, merges).role == "anchor"
    assert merge_membership_at(7, 3, merges).role == "covered"
    assert merge_membership_at(6, 3, merges).role == "covered"
    # a cell outside every merge
    assert merge_membership_at(20, 20, merges).role == "none"
    assert merge_membership_at(20, 20, merges).region is None


def test_merge_membership_carries_the_region():
    merges = (Merge(0, 0, 0, 2),)
    covered = merge_membership_at(0, 1, merges)
    assert covered.is_covered and not covered.is_anchor
    assert covered.region == Merge(0, 0, 0, 2)


# --------------------------------------------------------------------------- #
# at_position — the grid-position join (merge membership + export fidelity)     #
# --------------------------------------------------------------------------- #

def test_at_position_joins_merge_and_export_by_a1_ref():
    exported = ExportedSheet(name="Merged", cells={
        "A1": ExportedCell(ref="A1", value="Header", bold=True, italic=False,
                           fill_rgb="FFDDDDDD", num_fmt=None),
    })
    tab = _merged_tab()
    # A1 is the anchor of A1:C1 and has an export style.
    a1 = TypedCell.at_position(0, 0, raw="Header", display="Header",
                               merges=tab.merges, exported_sheet=exported)
    assert a1.merge.role == "anchor"
    assert a1.is_bold is True and a1.fill_rgb == "FFDDDDDD"
    # B1 is covered and has NO export cell → fidelity None, never raises.
    b1 = TypedCell.at_position(0, 1, raw=None, display=None,
                               merges=tab.merges, exported_sheet=exported)
    assert b1.merge.role == "covered"
    assert b1.fidelity is None


def test_at_position_no_export_sheet_is_graceful():
    cell = TypedCell.at_position(5, 5, raw=1, display="1")
    assert cell.merge.role == "none"
    assert cell.fidelity is None
    assert cell.num_fmt is None


# --------------------------------------------------------------------------- #
# JSON round-trip (serializable) — the model survives dumps→loads→from_dict     #
# --------------------------------------------------------------------------- #

_ROUND_TRIP_CELLS = {
    "scalar": TypedCell.from_values(raw=42, display=42),
    "percentage-with-fidelity": TypedCell.from_values(
        raw=0.1234, display="12.34%",
        exported_cell=ExportedCell(ref="A1", value=0.1234, bold=True, italic=False,
                                   fill_rgb="FFFFFF00", num_fmt="0.00%")),
    "styled-runs": TypedCell.from_values(raw=_STYLED_RUNS, display=_STYLED_RUNS),
    "hyperlink": TypedCell.from_values(raw=_HYPERLINK, display=_HYPERLINK),
    "user-mention": TypedCell.from_values(raw=_USER_MENTION, display=_USER_MENTION),
    "doc-mention": TypedCell.from_values(raw=_DOC_MENTION, display=_DOC_MENTION),
    "multi-select": TypedCell.from_values(raw=_MULTI_OBJECT, display=_MULTI_OBJECT),
    "merge-covered": TypedCell.from_values(
        raw=None, display=None,
        merge=MergeMembership(role="covered", region=Merge(0, 0, 0, 2))),
}


@pytest.mark.parametrize("name", list(_ROUND_TRIP_CELLS), ids=list(_ROUND_TRIP_CELLS))
def test_json_round_trip_is_lossless(name):
    cell = _ROUND_TRIP_CELLS[name]
    wire = json.dumps(cell.to_dict())          # must be JSON-serializable
    restored = TypedCell.from_dict(json.loads(wire))
    assert restored == cell


def test_to_dict_is_pure_json_types():
    cell = _ROUND_TRIP_CELLS["percentage-with-fidelity"]
    d = cell.to_dict()
    # a strict json.dumps with no default= proves every leaf is a JSON-native type
    json.dumps(d)
    assert set(d) == {"raw", "display", "segments", "fidelity", "merge"}


# --------------------------------------------------------------------------- #
# AC2 — ADDITIVE: the model cannot touch the L1 MD path (D3)                    #
# --------------------------------------------------------------------------- #

def _imported_modules(module) -> set:
    """The set of module names an actual `import` / `from … import` statement in a
    module's source references (AST-parsed — prose in docstrings is ignored)."""
    import ast

    src = Path(module.__file__).read_text(encoding="utf-8")
    names = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
    return names


def test_cell_model_does_not_import_render_or_table():
    """The typed model is a parallel surface — it must not import the shipped MD
    render/table path, so it can never perturb L1 output (AST, not prose)."""
    import larkdocio.sheets.cell_model as CM
    imported = _imported_modules(CM)
    assert not any(m.endswith("sheets.render") or m.endswith("sheets.table")
                   for m in imported), imported


def test_render_and_table_do_not_import_cell_model():
    """The shipped MD path must not consume the typed model — the model is
    additive, so render.py / table.py are blind to it (zero golden drift)."""
    import larkdocio.sheets.render as R
    import larkdocio.sheets.table as T
    for mod in (R, T):
        imported = _imported_modules(mod)
        assert not any(m.endswith("cell_model") for m in imported), (mod, imported)


def test_render_cell_output_unchanged_by_building_a_typed_cell():
    """Building a TypedCell from a value must not change what render_cell emits
    for that same value (the model reads, never mutates — additive)."""
    cases = [
        ("hello world", "hello world"),
        (42, "42"),
        (True, "☑"),
        (None, ""),
        (_STYLED_RUNS, "**bold start** plain middle _italic end_"),
        (_HYPERLINK, "[https://www.google.com](https://www.google.com)"),
        (_MULTI_OBJECT, "Red, Green"),
    ]
    for value, expected in cases:
        before = render_cell(value)
        _ = TypedCell.from_values(raw=value, display=value)   # build the model
        after = render_cell(value)
        assert before == expected == after
