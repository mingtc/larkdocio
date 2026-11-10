"""LD-185 — row/column DIMENSION PROPERTIES (height / width / hide-show) offline suite.

The **fourth verb** on the dimension path (`PUT …/dimension_range` with
`dimensionProperties{visible, fixedSize}`) — the one the client was missing while insert /
delete / append shipped.

**AC1 is why this file opens where it does.** The two shipped range verbs on this exact path
DISAGREE — `insert_dimension_range` is **0-indexed half-open `[start, end)`**,
`delete_dimension_range` is **1-indexed INCLUSIVE `[start, end]`** — and the PUT verb's
convention was documented nowhere. It was therefore **characterized live** on self-provisioned
disposables before a line of it was written
(`dev/sheets-dimension-probe/probe.py`, captures `01`/`02`/`03`), and the answer is
**1-indexed, INCLUSIVE** — the *delete* convention, not the insert one:

* `{startIndex: 2, endIndex: 3}` + `fixedSize` → the height landed on **sheet rows 2 AND 3**;
* `startIndex: 0` → `90202 invalid dimension range, StartIndex or EndIndex must greater than 0`
  (a 0-indexed reading is not even expressible);
* `{2, 2}` → **row 2 only** (a single-row band is `first == last`);
* a reversed `{5, 3}` → `90202 … EndIndex must greater than or equal to StartIndex`;
* an empty `dimensionProperties` → `90204 dimensionProperties FixedSize and Visible are nil`;
* `fixedSize: -1` → `90204 invalid operation`; `fixedSize: 0` is **accepted** and **CLEARS the
  custom size** (it is emphatically **not** a hide); `1 … 100000` all accepted;
* `{200, 201}` on a 200-row tab → `90202 … endIndex must less than or equal to
  sheetMaxRowCount`, while `{200, 200}` is accepted.

Every one of those facts is pinned by a test here, so the convention cannot be re-guessed.
The live round-trip is `tests/test_live_sheets_dimension_write_gate.py`.
"""
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

import xlsx_synth
from log_reading_apply import reading_the_log
from larkdocio.capabilities import capabilities
from larkdocio.common.transport import WriteTransport
from larkdocio.errors import LarkAPIError, LarkConfigError, LarkDocIOError
from larkdocio.sheets import ops as sheets_ops
from larkdocio.sheets.export_reader import parse_xlsx
from larkdocio.sheets.plan import PlanEntry, Refusal
from larkdocio.sheets.write_apply import (
    DIMENSION_PROPERTY_CONVENTION,
    DIMENSION_VERIFICATION_LEG,
    MAX_DIMENSION_SPAN,
    MERGE_LEG_OP_KINDS,
    STYLE_LEG_OP_KINDS,
    DeleteRows,
    DimensionPropertyError,
    GateNotVerified,
    InsertRowsAt,
    SetColProperties,
    SetRowProperties,
    ValueWriteRequest,
    WriteOpKind,
    apply,
    certify_gate_legs,
    dry_run,
    requires_merge_leg,
    requires_style_leg,
)
apply = reading_the_log(apply)
from larkdocio.sheets.ops import hidden_dimension_note
from larkdocio.sheets.write_client import SheetsWriteClient
from larkdocio.sheets.disposition import WRITE_SEAMS

from write_harness import FakeClock, _FakeHTTPResponse

REPO_ROOT = Path(__file__).resolve().parent.parent
_PROBE_CAPTURES = REPO_ROOT / "tests" / "captures" / "sheets-dimension-probe" / "captures"
_ROUND1 = json.loads((_PROBE_CAPTURES / "01-put-dimension_range-INDEX-CONVENTION.json")
                     .read_text(encoding="utf-8"))
_ROUND2 = json.loads((_PROBE_CAPTURES / "02-dimension_range-EDGES-and-raw-xlsx.json")
                     .read_text(encoding="utf-8"))
_ROUND3 = json.loads((_PROBE_CAPTURES / "03-raw-xlsx-dimension-XML.json")
                     .read_text(encoding="utf-8"))

TOKEN = "LD185SPREADSHEETTOKEN"
SID = "1e8212"


def _probe_step(captures, needle):
    for step in captures["steps"]:
        if needle in step["label"]:
            return step
    raise AssertionError(f"no probe step labelled {needle!r} in the capture")


# --------------------------------------------------------------------------- #
# Offline doubles                                                              #
# --------------------------------------------------------------------------- #

class FakeDimensionGateway:
    """A duck-typed write gateway covering the dimension-property seam + the write-side
    reads, with a monotonic ``revision`` (+1 per write, spike Q4) and a call journal — so a
    refusal can assert **zero** API calls and a resolved entry can assert exactly one write.
    """

    def __init__(self, *, revision=7, row_count=200, column_count=20, tabs=None,
                 fail_write=None, geometry_none=False):
        self.revision = revision
        self.row_count = row_count
        self.column_count = column_count
        self.tabs = list(tabs or [{"sheet_id": SID, "title": "Sheet1", "index": 0,
                                   "row_count": row_count, "column_count": column_count,
                                   "merges": []}])
        self.calls = []            # EVERY seam, read or write, in order
        self.writes = []           # write seams only
        self.dimension_writes = []
        self.fail_write = fail_write
        self.geometry_none = geometry_none
        self.external_bumps = {}
        self._rev_reads = 0

    # -- reads --
    def read_revision(self, spreadsheet_token):
        self.calls.append(("read_revision", spreadsheet_token))
        self._rev_reads += 1
        self.revision += self.external_bumps.pop(self._rev_reads, 0)
        return self.revision

    def read_values(self, spreadsheet_token, a1_range, value_render_option="UnformattedValue"):
        self.calls.append(("read_values", a1_range))
        return [["before"]]

    def read_sheet_geometry(self, spreadsheet_token, sheet_id):
        self.calls.append(("read_sheet_geometry", sheet_id))
        if self.geometry_none:
            return None
        if sheet_id not in {t["sheet_id"] for t in self.tabs}:
            return None
        return {"row_count": self.row_count, "column_count": self.column_count, "merges": []}

    def query_tabs(self, spreadsheet_token):
        self.calls.append(("query_tabs", spreadsheet_token))
        return [dict(t) for t in self.tabs]

    # -- writes --
    def put_values(self, spreadsheet_token, a1_range, values):
        self.calls.append(("put_values", a1_range))
        self.writes.append(("put_values", a1_range))
        self.revision += 1
        return {"revision": self.revision}

    def set_dimension_properties(self, spreadsheet_token, sheet_id, major_dimension,
                                 start_index, end_index, properties):
        self.calls.append(("set_dimension_properties", sheet_id))
        if self.fail_write is not None:
            raise self.fail_write
        self.writes.append(("set_dimension_properties", sheet_id))
        self.dimension_writes.append(
            (sheet_id, major_dimension, start_index, end_index, dict(properties)))
        self.revision += 1
        return {}


class StubOpener:
    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.requests = []

    def __call__(self, req, timeout=30):
        body = json.loads(req.data.decode()) if req.data else None
        self.requests.append({"method": req.get_method(), "url": req.full_url, "body": body})
        return _FakeHTTPResponse(self._payloads.pop(0))


def _client(opener):
    clock = FakeClock()
    return SheetsWriteClient(
        "app", "secret", "larksuite.com",
        transport=WriteTransport(max_writes_per_sec=3, time_fn=clock.time,
                                 sleep_fn=clock.sleep),
        urlopen=opener,
        token_fetcher=lambda *a, **k: "t-test",
    )


# --------------------------------------------------------------------------- #
# AC1 — the PUT verb's index convention, characterized FIRST and PINNED        #
# --------------------------------------------------------------------------- #

def test_ac1_the_probe_capture_records_the_raw_request_and_response():
    """The convention is established by EVIDENCE that lives in the repo, not by assertion."""
    step = _probe_step(_ROUND1, "THE CONVENTION PROBE")
    assert step["request_body"]["dimension"]["startIndex"] == 2
    assert step["request_body"]["dimension"]["endIndex"] == 3
    assert step["code"] == 0
    # ...and the read-back leg saw the height land on sheet rows 2 AND 3.
    after = _probe_step(_ROUND1, "xlsx AFTER convention probe")
    changed = [int(r) for r, a in after["observed"]["rows"].items() if a.get("ht")]
    assert sorted(changed) == [2, 3], (
        "the capture no longer shows {2,3} landing on rows 2 and 3 — re-probe before "
        "trusting the convention")


def test_ac1_zero_index_is_refused_by_lark_which_corroborates_1_indexing():
    step = _probe_step(_ROUND1, "FIRST row")            # asked for {0, 1}
    assert step["request_body"]["dimension"]["startIndex"] == 0
    assert step["code"] == 90202
    assert "greater than 0" in step["msg"]


def test_ac1_the_convention_constant_is_the_delete_one_not_the_insert_one():
    assert DIMENSION_PROPERTY_CONVENTION == "1-index-inclusive"
    # the two divergent shipped siblings, for the reader standing right here
    assert InsertRowsAt(SID, before_row=2).descriptor()["convention"] == "0-index-half-open"
    assert DeleteRows(SID, 2, 3).descriptor()["convention"] == "1-index-inclusive"


def test_ac1_a_two_row_band_emits_the_native_1_indexed_inclusive_span():
    desc = SetRowProperties(SID, first=2, last=3, fixed_size=60).descriptor()
    assert desc["start_index"] == 2 and desc["end_index"] == 3
    assert desc["convention"] == DIMENSION_PROPERTY_CONVENTION
    assert desc["expected_count"] == 2
    assert desc["major_dimension"] == "ROWS"
    assert desc["op"] == "dimension-property"


def test_ac1_a_single_row_band_is_first_equals_last():
    desc = SetRowProperties(SID, first=2, last=2, fixed_size=99).descriptor()
    assert (desc["start_index"], desc["end_index"], desc["expected_count"]) == (2, 2, 1)
    step = _probe_step(_ROUND2, "SINGLE-row band")
    assert step["request_body"]["dimension"] == {
        "sheetId": _ROUND2["sheet_id"], "majorDimension": "ROWS",
        "startIndex": 2, "endIndex": 2}
    assert step["code"] == 0


def test_ac1_both_ends_of_a_band_are_addressable():
    """First row and last row — an off-by-one cannot hide behind a mid-sheet band."""
    assert SetRowProperties(SID, 1, 1, fixed_size=50).descriptor()["start_index"] == 1
    last = SetRowProperties(SID, 200, 200, fixed_size=50).descriptor()
    assert (last["start_index"], last["end_index"]) == (200, 200)
    # the probe proved {200,200} is accepted on a 200-row tab and {200,201} is not
    assert _probe_step(_ROUND2, "the LAST declared row")["code"] == 0
    assert _probe_step(_ROUND2, "ONE past the declared grid")["code"] == 90202


def test_ac1_the_request_docstring_states_the_convention_beside_the_two_divergent_ones():
    doc = SetRowProperties.__doc__
    assert "1-indexed" in doc and "INCLUSIVE" in doc
    assert "0-indexed" in doc and "half-open" in doc, (
        "the docstring must name the INSERT convention beside this one — that adjacency is "
        "the whole point of AC1")
    assert "delete" in doc.lower()


def test_ac1_the_client_docstring_states_the_convention_too():
    doc = SheetsWriteClient.set_dimension_properties.__doc__
    assert "1-INDEXED" in doc.upper()
    assert "insert_dimension_range" in doc and "delete_dimension_range" in doc


def test_ac1_the_client_puts_the_native_span_on_the_wire_verbatim():
    step = _probe_step(_ROUND3, "row 2 height 60")
    opener = StubOpener([step["response"]])
    client = _client(opener)

    client.set_dimension_properties(
        _ROUND3["spreadsheet_token"], step["request_body"]["dimension"]["sheetId"], "ROWS", 2, 2, {"fixedSize": 60})

    req = opener.requests[0]
    assert req["method"] == "PUT"
    assert req["url"].endswith(
        f"/open-apis/sheets/v2/spreadsheets/{_ROUND3['spreadsheet_token']}/dimension_range")
    assert req["body"] == step["request_body"]        # byte-exact vs the live capture


def test_ac1_the_client_emits_a_hide_body_byte_exactly():
    step = _probe_step(_ROUND3, "row 3 HIDDEN")
    opener = StubOpener([step["response"]])
    client = _client(opener)
    client.set_dimension_properties(
        _ROUND3["spreadsheet_token"], step["request_body"]["dimension"]["sheetId"], "ROWS", 3, 3, {"visible": False})
    assert opener.requests[0]["body"] == step["request_body"]


def test_ac1_the_column_axis_uses_the_same_convention():
    desc = SetColProperties(SID, first=2, last=3, visible=False).descriptor()
    assert desc["major_dimension"] == "COLUMNS"
    assert (desc["start_index"], desc["end_index"]) == (2, 3)
    assert desc["convention"] == DIMENSION_PROPERTY_CONVENTION
    # live corroboration: hiding {2,3} hid columns B AND C
    cols = _probe_step(_ROUND1, "xlsx AFTER column ops")["observed"]["cols"]
    hidden = {int(c["min"]) for c in cols if c.get("hidden") == "true"}
    assert hidden == {2, 3}


# --------------------------------------------------------------------------- #
# AC2 — a typed request through the EXISTING gate                              #
# --------------------------------------------------------------------------- #

def test_ac2_dry_run_previews_and_apply_writes_through_the_gate():
    gw = FakeDimensionGateway()
    plan = dry_run([SetRowProperties(SID, 2, 3, fixed_size=60)], gw, TOKEN)

    assert len(plan.resolved) == 1, plan.refusals
    entry = plan.entries[0]
    assert entry.write_kind == "dimension-property"
    assert entry.target is None                       # a dimension write has no A1 target
    assert entry.structural["properties"] == {"fixedSize": 60}
    assert gw.writes == [], "dry_run must not write"

    log = apply(plan, gw)
    assert log.entries[0].is_applied
    assert gw.dimension_writes == [(SID, "ROWS", 2, 3, {"fixedSize": 60})]
    assert log.entries[0].revision == gw.revision


def test_ac2_the_plan_is_not_forgeable_and_apply_refuses_a_bare_list():
    gw = FakeDimensionGateway()
    with pytest.raises(TypeError):
        apply([SetRowProperties(SID, 2, 2, fixed_size=60)], gw)


def test_ac2_stale_sheet_refuses_the_write_with_zero_writes():
    gw = FakeDimensionGateway()
    plan = dry_run([SetRowProperties(SID, 2, 3, visible=False)], gw, TOKEN)
    gw.revision += 1                                   # someone else wrote
    log = apply(plan, gw)
    assert log.entries[0].refusal.reason == Refusal.STALE_SHEET
    assert gw.writes == []


def test_ac2_the_request_is_frozen_and_the_entry_json_round_trips():
    req = SetRowProperties(SID, 2, 3, visible=False, fixed_size=60)
    with pytest.raises(FrozenInstanceError):
        req.sheet_id = "nope"
    gw = FakeDimensionGateway()
    entry = dry_run([req], gw, TOKEN).entries[0]
    blob = json.dumps(entry.to_dict())                 # JSON-serializable, no tuples/sets
    back = PlanEntry.from_dict(json.loads(blob))
    assert back.structural == entry.structural
    assert back.write_kind == "dimension-property"
    assert back.preview_note == entry.preview_note


def test_ac2_the_whole_plan_serializes():
    gw = FakeDimensionGateway()
    plan = dry_run([SetRowProperties(SID, 2, 3, visible=False)], gw, TOKEN)
    blob = json.loads(plan.to_json())
    assert blob["entries"][0]["structural"]["convention"] == DIMENSION_PROPERTY_CONVENTION


def test_ac2_no_exception_escapes_apply():
    gw = FakeDimensionGateway(fail_write=LarkAPIError("Code 90204, Msg: invalid operation"))
    plan = dry_run([SetRowProperties(SID, 2, 3, fixed_size=60)], gw, TOKEN)
    log = apply(plan, gw)                              # must NOT raise
    assert log.entries[0].refusal is not None
    assert log.entries[0].outcome in ("refused", "failed")


def test_ac2_the_client_seam_is_registered_as_a_WRITE_seam():
    assert "set_dimension_properties" in WRITE_SEAMS


# --------------------------------------------------------------------------- #
# AC3 — its OWN op kind with its OWN verification leg (never the export leg)   #
# --------------------------------------------------------------------------- #

def test_ac3_the_op_kind_is_its_own():
    assert WriteOpKind.DIMENSION_PROPERTY == "dimension-property"
    assert SetRowProperties(SID, 2, 2, fixed_size=60).op_kinds == (
        WriteOpKind.DIMENSION_PROPERTY,)
    assert SetColProperties(SID, 2, 2, fixed_size=60).op_kinds == (
        WriteOpKind.DIMENSION_PROPERTY,)


def test_ac3_it_is_off_the_export_style_leg_and_the_merge_leg():
    kinds = (WriteOpKind.DIMENSION_PROPERTY,)
    assert WriteOpKind.DIMENSION_PROPERTY not in STYLE_LEG_OP_KINDS
    assert WriteOpKind.DIMENSION_PROPERTY not in MERGE_LEG_OP_KINDS
    assert requires_style_leg(kinds) is False
    assert requires_merge_leg(kinds) is False


def test_ac3_certify_gate_legs_accepts_it_on_its_own_leg():
    kinds = (WriteOpKind.DIMENSION_PROPERTY,)
    certify_gate_legs(kinds, values_leg_ran=True)      # no style/merge leg needed
    with pytest.raises(GateNotVerified):
        certify_gate_legs(kinds, values_leg_ran=False)


def test_ac3_the_registry_carries_exactly_one_descriptor_for_the_family():
    descs = [d for d in sheets_ops.OPS if d.kind == "dimension-property"]
    assert len(descs) == 1
    desc = descs[0]
    assert desc.write_kind == "dimension-property"
    assert desc.entry_ops == ("dimension-property",)
    assert set(desc.request_type) == {SetRowProperties, SetColProperties}


def test_ac3_both_dispatch_keyings_find_the_family():
    gw = FakeDimensionGateway()
    req = SetRowProperties(SID, 2, 3, fixed_size=60)
    assert sheets_ops.classify(req) == "dimension-property"
    entry = dry_run([req], gw, TOKEN).entries[0]
    assert sheets_ops.descriptor_for_entry(entry).kind == "dimension-property"


def test_ac3_a_dimension_write_is_not_classified_structural():
    """It changes presentation, not geometry — so it must not inherit the structural
    op-kind (which would drag the export style leg + the merge leg back on)."""
    req = SetRowProperties(SID, 2, 3, fixed_size=60)
    assert getattr(req, "is_structural", False) is False
    assert WriteOpKind.STRUCTURE not in req.op_kinds


# --------------------------------------------------------------------------- #
# AC4 — the verification leg is DECIDED (b: the xlsx export) and DOCUMENTED     #
# --------------------------------------------------------------------------- #

def test_ac4_the_cheap_reads_carry_no_dimension_property_which_is_why_the_leg_is_the_export():
    """The evidence behind the (b) decision: after ELEVEN dimension writes, neither
    ``metainfo`` nor v3 ``sheets/query`` reports a single row height, column width or
    row/column hidden flag — so option (a) is not available at all."""
    meta = _probe_step(_ROUND1, "metainfo AFTER")["response"]["data"]
    sheet = meta["sheets"][0]
    assert set(sheet) == {"columnCount", "frozenColCount", "frozenRowCount", "index",
                          "rowCount", "sheetId", "title"}
    v3 = _probe_step(_ROUND1, "v3 sheets/query AFTER")["response"]["data"]["sheets"][0]
    assert set(v3["grid_properties"]) == {"column_count", "frozen_column_count",
                                          "frozen_row_count", "row_count"}
    assert v3["hidden"] is False, "v3 reports the TAB's own hidden flag, never a row's"


def test_ac4_the_export_leg_reads_row_heights_and_hidden_rows():
    """The chosen leg, over xlsx bytes reproducing the captured worksheet XML verbatim
    (`tests/captures/sheets-dimension-probe/captures/03-raw-xlsx-dimension-XML.json`)."""
    blob = xlsx_synth.build_workbook([{
        "name": "Sheet1",
        "cells": [("A1", {"t": "inlineStr", "inline": "A1"})],
        "default_row_height": "20",
        "default_col_width": "13",
        "rows": {2: {"ht": "44", "customHeight": "true"},
                 3: {"ht": "20", "customHeight": "true", "hidden": "true"}},
        "cols": [{"min": 2, "max": 2, "width": "25", "customWidth": "true", "hidden": "false"}],
    }])
    sheet = parse_xlsx(blob).first_sheet
    assert sheet.default_row_height == "20"
    assert sheet.default_col_width == "13"
    assert sheet.row_dimension(2).size == "44"
    assert sheet.row_dimension(2).custom_size is True
    assert sheet.row_dimension(2).hidden is False
    assert sheet.row_dimension(3).hidden is True
    assert sheet.col_dimension(2).size == "25"
    assert sheet.col_dimension(2).hidden is False
    assert sheet.row_dimension(1) is None, "a row with no dimension attrs reports nothing"


def test_ac4_a_later_duplicate_col_entry_wins_as_the_capture_requires():
    """The live export emits column 3 TWICE — `hidden="false"` then `hidden="true"`
    (capture 03). Last wins, or the reader would report a hidden column as visible."""
    raw = _ROUND3["RAW_AFTER_DIMENSION_WRITES"]
    assert raw.count('max="3" min="3"') == 2, "the capture no longer duplicates <col> — re-probe"
    blob = xlsx_synth.build_workbook([{
        "name": "Sheet1",
        "cells": [("A1", {"t": "inlineStr", "inline": "A1"})],
        "cols": [{"min": 3, "max": 3, "width": "13", "customWidth": "true", "hidden": "false"},
                 {"min": 3, "max": 3, "width": "13", "customWidth": "true", "hidden": "true"}],
    }])
    assert parse_xlsx(blob).first_sheet.col_dimension(3).hidden is True


def test_ac4_a_workbook_with_no_dimension_attributes_reads_empty_and_unchanged():
    """ZERO-DRIFT: the additive dimension read cannot disturb a workbook that has none."""
    blob = xlsx_synth.fidelity_workbook()
    sheet = parse_xlsx(blob).first_sheet
    assert sheet.row_dimensions == {} and sheet.col_dimensions == {}
    assert sheet.default_row_height is None and sheet.default_col_width is None
    assert sheet.cell("A1").num_fmt == "0.00%"          # the shipped fidelity read intact


def test_ac4_the_apply_log_names_the_chosen_leg_and_why_it_is_not_run_per_apply():
    gw = FakeDimensionGateway()
    log = apply(dry_run([SetRowProperties(SID, 2, 3, fixed_size=60)], gw, TOKEN), gw)
    record = log.entries[0].structural
    assert record["verified_by"] == DIMENSION_VERIFICATION_LEG == "xlsx-export-dimension-leg"
    assert "export" in record["verification_note"].lower()
    # the reason the leg is NOT wired into the per-apply path
    assert "not run per apply" in record["verification_note"].lower()
    assert ("read_sheet_geometry", SID) in gw.calls        # the plan's own cheap read
    # ...and no export was attempted from the apply path
    assert not any(c[0].startswith("export") for c in gw.calls)


# --------------------------------------------------------------------------- #
# AC5 — a HIDE is disclosed as a FIDELITY EVENT (LD-150/LD-155 vocabulary)      #
# --------------------------------------------------------------------------- #

def test_ac5_a_hide_carries_the_fidelity_note():
    gw = FakeDimensionGateway()
    entry = dry_run([SetRowProperties(SID, 2, 3, visible=False)], gw, TOKEN).entries[0]
    notes = [n for n in entry.preview_notes if n["kind"] == "hidden-dimension-fidelity"]
    assert len(notes) == 1
    note = notes[0]
    assert note["dimension"] == "ROWS"
    assert note["span"] == [2, 3]
    assert note["count"] == 2
    assert note["hidden_rows"] == [2, 3]


def test_ac5_the_note_quotes_the_shipped_disclosure_vocabulary():
    """AC5 says QUOTE LD-150/LD-155's shipped note vocabulary, not re-coin it."""
    note = hidden_dimension_note(
        SetRowProperties(SID, 2, 3, visible=False).descriptor(),
        {"row_count": 200, "column_count": 20})
    text = note["note"]
    assert "Hidden from anyone viewing this spreadsheet" in text
    assert "numbered as the spreadsheet numbers them, where the first row is 1" in text
    assert "still" in text and "emit" in text.lower()


def test_ac5_a_pure_size_change_carries_NO_disclosure():
    """The note must not leak into every plan — only a hide makes data invisible."""
    gw = FakeDimensionGateway()
    entry = dry_run([SetRowProperties(SID, 2, 3, fixed_size=60)], gw, TOKEN).entries[0]
    assert entry.preview_note is None
    assert entry.preview_notes == ()


def test_ac5_a_show_carries_NO_disclosure():
    gw = FakeDimensionGateway()
    entry = dry_run([SetRowProperties(SID, 2, 3, visible=True)], gw, TOKEN).entries[0]
    assert entry.preview_notes == ()


def test_ac5_the_hide_note_composes_with_another_note():
    """LD-150: a disclosure must never displace another disclosure."""
    gw = FakeDimensionGateway()
    plan = dry_run(
        [SetRowProperties(SID, 2, 3, visible=False),
         ValueWriteRequest.for_a1(f"{SID}!A1:A1", [["=SUM(A2:A3)"]])],
        gw, TOKEN)
    kinds = {n["kind"] for n in plan.entries[0].preview_notes}
    assert kinds == {"hidden-dimension-fidelity"}
    # the neighbouring entry keeps its own note — neither displaced the other
    assert plan.entries[1].preview_notes


def test_ac5_the_note_rides_a_column_hide_too():
    gw = FakeDimensionGateway()
    entry = dry_run([SetColProperties(SID, 3, 3, visible=False)], gw, TOKEN).entries[0]
    note = entry.preview_notes[0]
    assert note["dimension"] == "COLUMNS"
    assert note["hidden_columns"] == ["C"]


def test_ac5_the_note_rides_a_hide_that_also_resizes():
    gw = FakeDimensionGateway()
    entry = dry_run([SetRowProperties(SID, 4, 4, visible=False, fixed_size=60)],
                    gw, TOKEN).entries[0]
    assert entry.structural["properties"] == {"visible": False, "fixedSize": 60}
    assert entry.preview_notes[0]["kind"] == "hidden-dimension-fidelity"


# --------------------------------------------------------------------------- #
# AC6 — refusals are pre-I/O, typed and EXAMPLED, and cost ZERO API calls       #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("factory", [SetRowProperties, SetColProperties])
def test_ac6_a_reversed_band_refuses_at_construction(factory):
    with pytest.raises(DimensionPropertyError) as exc:
        factory(SID, first=5, last=2, fixed_size=60)
    msg = str(exc.value)
    assert "reversed" in msg
    assert "first=2, last=5" in msg                     # the swap repair, spelled out
    assert "first=5, last=5" in msg                     # the single-row repair
    assert "1-indexed INCLUSIVE" in msg
    # the probed Lark answer this pre-empts
    assert "EndIndex must greater than or equal to StartIndex" in msg


def test_ac6_the_reversed_refusal_is_also_a_ValueError_and_a_LarkConfigError():
    assert issubclass(DimensionPropertyError, ValueError)
    assert issubclass(DimensionPropertyError, LarkConfigError)
    assert issubclass(DimensionPropertyError, LarkDocIOError)


def test_ac6_no_property_at_all_refuses_at_construction():
    with pytest.raises(DimensionPropertyError) as exc:
        SetRowProperties(SID, 2, 3)
    msg = str(exc.value)
    assert "visible" in msg and "fixed_size" in msg
    assert "FixedSize and Visible are nil" in msg       # the probed 90204 it pre-empts


def test_ac6_fixed_size_zero_refuses_and_says_what_lark_actually_does_with_it():
    with pytest.raises(DimensionPropertyError) as exc:
        SetRowProperties(SID, 2, 3, fixed_size=0)
    msg = str(exc.value)
    assert "does not hide" in msg.lower()
    assert "visible=False" in msg                       # the repair for the likely intent
    assert "clear" in msg.lower() and "default" in msg.lower()


def test_ac6_a_negative_fixed_size_refuses_at_construction():
    with pytest.raises(DimensionPropertyError) as exc:
        SetRowProperties(SID, 2, 3, fixed_size=-1)
    assert "invalid operation" in str(exc.value)        # the probed 90204
    step = _probe_step(_ROUND2, "fixedSize=-1")
    assert step["code"] == 90204


def test_ac6_a_non_bool_visible_refuses_at_construction():
    with pytest.raises(DimensionPropertyError):
        SetRowProperties(SID, 2, 3, visible="false")


def test_ac6_a_sub_one_band_refuses_at_construction():
    with pytest.raises(ValueError):
        SetRowProperties(SID, 0, 3, fixed_size=60)


def test_ac6_the_5000_dimension_ceiling_is_enforced_at_5000_and_5001():
    assert MAX_DIMENSION_SPAN == 5000
    ok = SetRowProperties(SID, 1, 5000, fixed_size=60)          # exactly at the ceiling
    assert ok.descriptor()["expected_count"] == 5000
    with pytest.raises(DimensionPropertyError) as exc:
        SetRowProperties(SID, 1, 5001, fixed_size=60)
    assert "5000" in str(exc.value) and "5001" in str(exc.value)


def test_ac6_every_construction_refusal_costs_ZERO_api_calls():
    """A call-count spy: a request that cannot be built never reaches a gateway at all."""
    gw = FakeDimensionGateway()
    for bad in (lambda: SetRowProperties(SID, 5, 2, fixed_size=60),
                lambda: SetRowProperties(SID, 2, 3),
                lambda: SetRowProperties(SID, 2, 3, fixed_size=0),
                lambda: SetRowProperties(SID, 2, 3, fixed_size=-1),
                lambda: SetRowProperties(SID, 1, 5001, fixed_size=60)):
        with pytest.raises((DimensionPropertyError, ValueError)):
            dry_run([bad()], gw, TOKEN)
    assert gw.calls == [], f"a refused request touched the API: {gw.calls!r}"


def test_ac6_a_band_past_the_tabs_row_count_refuses_at_plan_time_with_zero_writes():
    gw = FakeDimensionGateway(row_count=200)
    plan = dry_run([SetRowProperties(SID, 199, 205, fixed_size=60)], gw, TOKEN)
    entry = plan.entries[0]
    assert not entry.is_resolved
    assert entry.refusal.reason == Refusal.OUT_OF_BOUNDS_DIMENSION
    detail = entry.refusal.detail
    assert "200" in detail and "205" in detail
    assert "sheetMaxRowCount" in detail                  # the probed 90202 it pre-empts
    assert "AppendDimension" in detail                   # the grow-the-tab repair
    assert gw.writes == [], "a plan-time refusal must issue no write"
    # and applying the plan still writes nothing
    assert apply(plan, gw).entries[0].refusal.reason == Refusal.OUT_OF_BOUNDS_DIMENSION
    assert gw.writes == []


def test_ac6_a_band_past_the_tabs_column_count_refuses_too():
    gw = FakeDimensionGateway(column_count=20)
    entry = dry_run([SetColProperties(SID, 20, 21, fixed_size=60)], gw, TOKEN).entries[0]
    assert entry.refusal.reason == Refusal.OUT_OF_BOUNDS_DIMENSION
    assert "sheetMaxColumnCount" in entry.refusal.detail or "column" in entry.refusal.detail


def test_ac6_the_last_declared_row_is_in_bounds():
    gw = FakeDimensionGateway(row_count=200)
    assert dry_run([SetRowProperties(SID, 200, 200, fixed_size=60)],
                   gw, TOKEN).entries[0].is_resolved


def test_ac6_an_unknown_tab_refuses_with_a_did_you_mean():
    gw = FakeDimensionGateway()
    entry = dry_run([SetRowProperties("nosuchtab", 2, 3, fixed_size=60)], gw, TOKEN).entries[0]
    assert entry.refusal.reason == Refusal.UNKNOWN_TAB
    assert SID in entry.refusal.detail          # the did-you-mean names the real tab
    assert gw.writes == []


def test_ac6_an_unreadable_tab_refuses_tab_vanished():
    gw = FakeDimensionGateway(geometry_none=True)
    entry = dry_run([SetRowProperties(SID, 2, 3, fixed_size=60)], gw, TOKEN).entries[0]
    assert entry.refusal.reason in (Refusal.TAB_VANISHED, Refusal.UNKNOWN_TAB)
    assert gw.writes == []


# --------------------------------------------------------------------------- #
# The test-rigor amplifier                                                     #
# --------------------------------------------------------------------------- #

def test_amp_visible_and_fixed_size_independently_and_together():
    for kwargs, wire in (
        ({"visible": False}, {"visible": False}),
        ({"fixed_size": 60}, {"fixedSize": 60}),
        ({"visible": True, "fixed_size": 60}, {"visible": True, "fixedSize": 60}),
    ):
        assert SetRowProperties(SID, 2, 2, **kwargs).descriptor()["properties"] == wire


def test_amp_a_hide_then_show_round_trip_is_idempotent():
    gw = FakeDimensionGateway()
    for _ in range(2):
        apply(dry_run([SetRowProperties(SID, 2, 2, visible=False)], gw, TOKEN), gw)
        apply(dry_run([SetRowProperties(SID, 2, 2, visible=True)], gw, TOKEN), gw)
    props = [w[4] for w in gw.dimension_writes]
    assert props == [{"visible": False}, {"visible": True}] * 2
    # live corroboration: a second visible=true was accepted and changed nothing
    assert _probe_step(_ROUND1, "idempotent?")["code"] == 0
    assert _probe_step(_ROUND1, "xlsx AFTER show round-trip")["observed"] is not None


def test_amp_a_band_crossing_the_used_range_edge_is_allowed():
    """Crossing the USED extent is legal (only the DECLARED grid bounds the band) — probed."""
    gw = FakeDimensionGateway(row_count=200)
    assert dry_run([SetRowProperties(SID, 4, 7, fixed_size=155)], gw, TOKEN).entries[0].is_resolved
    assert _probe_step(_ROUND1, "crossing the USED-range edge")["code"] == 0


def test_amp_the_semantic_restates_the_intent_in_english():
    hide = SetRowProperties(SID, 2, 3, visible=False).descriptor()["semantic"]
    assert "row" in hide and "2..3" in hide and "hide" in hide.lower()
    size = SetColProperties(SID, 2, 2, fixed_size=200).descriptor()["semantic"]
    assert "column" in size and "200" in size


def test_amp_a_batch_of_dimension_writes_applies_in_order():
    gw = FakeDimensionGateway()
    log = apply(dry_run([SetRowProperties(SID, 2, 2, fixed_size=60),
                         SetColProperties(SID, 2, 2, fixed_size=200),
                         SetRowProperties(SID, 3, 3, visible=False)], gw, TOKEN), gw)
    assert [e.is_applied for e in log.entries] == [True, True, True]
    assert [w[1] for w in gw.dimension_writes] == ["ROWS", "COLUMNS", "ROWS"]


# --------------------------------------------------------------------------- #
# AC8 — truth-rows: capabilities() gains the op                                #
# --------------------------------------------------------------------------- #

def test_ac8_capabilities_reports_the_dimension_property_op():
    ops = capabilities(full=True)["surfaces"]["sheets-write"]["operations"]
    row = next((o for o in ops if o["name"] == "dimension-property"), None)
    assert row is not None, [o["name"] for o in ops]
    assert row["write_kind"] == "dimension-property"
    assert row["entry_ops"] == ["dimension-property"]
    assert set(row["request_types"]) == {"SetRowProperties", "SetColProperties"}
