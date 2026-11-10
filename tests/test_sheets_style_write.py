"""LD-188 — the CELL STYLE write, promoted out of the test harness into ``src/``.

**The premise, and why this file leans so hard on captures.** The endpoint was API-proven at
LD-107 (``PUT …/style`` with ``appendStyle`` → ``xl/styles.xml`` bold + fill ``FFFFFF00`` +
numFmt ``0.00%``) and has been exercised nightly by the S5 fidelity gate ever since — but only
from ``tests/sheets_write_harness.py``. Nothing in ``src/`` could write a style, so a consumer
could read style and not set it. This issue ships the request family, the two client ops, and
the gated preview/apply legs; the gate wiring it rides
(``WriteOpKind.STYLE`` / ``NUMBER_FORMAT`` in ``STYLE_LEG_OP_KINDS``) was reserved for it in
advance and is **not** extended here.

**Characterized live first** (``dev/sheets-style-write-probe/probe.py``, capture
``01-style-write-characterization.json``, one self-provisioned disposable, deleted and
gone-confirmed) — because three of this issue's AC rest on facts nobody had established:

* **``font.fontSize`` is a STRING, ``"<size>pt/<line-spacing>"``.** A bare int ``10`` is
  **refused** — ``90204 invalid fontSize, fontSize must between 9 and 36`` — a message that
  blames the *range* for what is actually a *shape* error, so a caller who trusts it debugs the
  wrong thing.
* **The 9..36 range REFUSES, it does not clamp** (AC5's fork, answered): ``"8pt/1.5"`` and
  ``"37pt/1.5"`` both → ``90204``, while ``"9pt/1.5"`` and ``"36pt/1.5"`` land (the export's
  ``xl/styles.xml`` shows ``sz="9"`` and ``sz="36"``). So the size is refused at
  **construction**, costing zero API calls.
* **``styles_batch_update`` is NOT immune to the ``90202`` bare-cell trap.** The coverage
  audit's "immune to the 90202 bare-cell trap (it takes a ``ranges`` array)" is **FALSE**:
  ``{"ranges": ["<sid>!C1"]}`` answered ``90202 wrong range=<sid>!C1``, exactly like the
  single-range ``PUT …/style`` does. Both ops therefore force ``Start:End``.
* **A style lands on EXACTLY the cells its range names — a merge does not spread it.** This one
  took two rounds, and the first reading was wrong: round 1 styled the WHOLE of a three-cell
  merge, saw all three cells styled, and read that as the merge spreading the style. Round 2 ran
  the distinguishing experiment — the **anchor alone** — and got ``updatedCells: 1`` with the
  covered cells carrying **no** style at all. So the hazard is the reverse of the one first
  assumed: a target naming only *part* of a merge leaves the region with mixed stored style,
  which shows the moment the merge is dissolved. That is what ``style-partial-merge`` discloses.
* **``formatter`` alone is accepted** (no font, no fill) — a number-format-only write, which is
  why ``WriteOpKind.NUMBER_FORMAT`` is a classification this family really produces.
* **the replies**: ``PUT …/style`` carries its post-write revision at
  ``data.updates.revision``; ``styles_batch_update`` carries **no revision at all**
  (``data.responses[]`` only), so the apply leg falls back to a ``metainfo`` read.

The live round-trip is ``tests/test_live_sheets_style_write_gate.py`` (the src path) beside the
older ``tests/test_live_sheets_style_gate.py`` (the L2 read fidelity).
"""
import json
from pathlib import Path

import pytest

from log_reading_apply import reading_the_log
from larkdocio.capabilities import capabilities
from larkdocio.errors import LarkAPIError, LarkConfigError, LarkDocIOError
from larkdocio.sheets import ops as sheets_ops
from larkdocio.sheets.plan import Refusal
from larkdocio.sheets.write_apply import (
    MAX_FONT_SIZE,
    MERGE_LEG_OP_KINDS,
    MIN_FONT_SIZE,
    STYLE_LEG_OP_KINDS,
    STYLE_VERIFICATION_LEG,
    BatchStyleWriteRequest,
    CellStyle,
    GateNotVerified,
    StyleError,
    StyleSpan,
    StyleWriteRequest,
    ValueWriteRequest,
    WriteOpKind,
    apply,
    certify_gate_legs,
    dry_run,
    effective_verify_style,
    requires_merge_leg,
    requires_style_leg,
)
apply = reading_the_log(apply)
from larkdocio.sheets.disposition import WRITE_SEAMS
from larkdocio.sheets.write_client import SheetsWriteClient

from test_sheets_write_client import _client
from write_harness import StubOpener

REPO_ROOT = Path(__file__).resolve().parent.parent
_PROBE = json.loads(
    (REPO_ROOT / "tests" / "captures" / "sheets-style-write-probe" / "captures"
     / "01-style-write-characterization.json").read_text(encoding="utf-8")
)
_SPIKE = json.loads(
    (REPO_ROOT / "tests" / "captures" / "sheets-write-spike" / "captures"
     / "01-endpoint-matrix.json").read_text(encoding="utf-8")
)["captures"]
_MERGE_PROBE = json.loads(
    (REPO_ROOT / "tests" / "captures" / "sheets-style-write-probe" / "captures"
     / "02-merge-anchor-only.json").read_text(encoding="utf-8")
)
_FIDELITY = json.loads(
    (REPO_ROOT / "tests" / "captures" / "sheets-write-spike" / "captures"
     / "02b-export-fidelity.json").read_text(encoding="utf-8")
)["captures"]

TOKEN = "LD188SPREADSHEETTOKEN"
SID = "9eef9c"


def _step(needle):
    for step in _PROBE["steps"]:
        if needle in step["label"]:
            return step
    raise AssertionError(f"no probe step labelled {needle!r} in the capture")


# --------------------------------------------------------------------------- #
# Offline doubles                                                              #
# --------------------------------------------------------------------------- #

class FakeStyleGateway:
    """A duck-typed write gateway covering the two style seams + the write-side reads, with a
    monotonic ``revision`` and a call journal — so a refusal can assert **zero** API calls and
    a resolved entry exactly one write."""

    def __init__(self, *, revision=7, merges=None, tabs=None, fail_write=None,
                 geometry_none=False, style_reply="updates"):
        self.revision = revision
        self.merges = list(merges or [])
        self.tabs = list(tabs or [{"sheet_id": SID, "title": "Sheet1", "index": 0,
                                   "row_count": 200, "column_count": 20, "merges": []}])
        self.calls = []
        self.writes = []
        self.style_writes = []
        self.batch_style_writes = []
        self.fail_write = fail_write
        self.geometry_none = geometry_none
        self.style_reply = style_reply

    # -- reads --
    def read_revision(self, spreadsheet_token):
        self.calls.append(("read_revision", spreadsheet_token))
        return self.revision

    def read_sheet_geometry(self, spreadsheet_token, sheet_id):
        self.calls.append(("read_sheet_geometry", sheet_id))
        if self.geometry_none:
            return None
        if sheet_id not in {t["sheet_id"] for t in self.tabs}:
            return None
        return {"row_count": 200, "column_count": 20, "merges": [dict(m) for m in self.merges]}

    def query_tabs(self, spreadsheet_token):
        self.calls.append(("query_tabs", spreadsheet_token))
        return [dict(t) for t in self.tabs]

    def read_values(self, spreadsheet_token, a1_range, value_render_option="UnformattedValue"):
        self.calls.append(("read_values", a1_range))
        return [["before"]]

    # -- writes --
    def put_values(self, spreadsheet_token, a1_range, values):
        self.calls.append(("put_values", a1_range))
        self.writes.append(("put_values", a1_range))
        self.revision += 1
        return {"revision": self.revision}

    def put_style(self, spreadsheet_token, a1_range, style):
        self.calls.append(("put_style", a1_range))
        if self.fail_write is not None:
            raise self.fail_write
        self.writes.append(("put_style", a1_range))
        self.style_writes.append((spreadsheet_token, a1_range, json.loads(json.dumps(style))))
        self.revision += 1
        if self.style_reply == "updates":
            return {"updates": {"revision": self.revision, "updatedCells": 1,
                                "updatedRange": a1_range}}
        return {}

    def batch_update_styles(self, spreadsheet_token, style_ranges):
        self.calls.append(("batch_update_styles", len(style_ranges)))
        if self.fail_write is not None:
            raise self.fail_write
        self.writes.append(("batch_update_styles", len(style_ranges)))
        self.batch_style_writes.append(
            (spreadsheet_token, json.loads(json.dumps(style_ranges))))
        self.revision += 1
        # Probed: the batch reply carries NO revision — only per-range `responses`.
        return {"responses": [{"updatedRange": r, "updatedCells": 1}
                              for item in style_ranges for r in item["ranges"]]}


# The transport doubles are IMPORTED, not re-authored: ``write_harness.StubOpener`` already
# records exactly the method / url / body this suite asserts on, and the ``SheetsWriteClient``
# factory already exists in the client suite. A tenth private copy of either would redden
# tests/test_write_harness_double_ownership.py — correctly, since this suite's needs are not
# divergent.
BOLD_FILL_FMT = CellStyle(bold=True, back_color="#FFFF00", formatter="0.00%")


# --------------------------------------------------------------------------- #
# AC1 — the typed request: byte-exact wire bodies against the captures          #
# --------------------------------------------------------------------------- #

def test_ac1_the_style_payload_is_the_spike_s_proven_one_byte_for_byte():
    """The style dict this library emits for the spike's own inputs IS the spike's body."""
    proven = _FIDELITY["write_style"]["request_body"]["appendStyle"]["style"]
    assert proven == {"font": {"bold": True}, "backColor": "#FFFF00", "formatter": "0.00%"}
    assert BOLD_FILL_FMT.wire() == proven
    assert _FIDELITY["write_style"]["code"] == 0        # ...and Lark accepted exactly that


def test_ac1_put_style_matches_the_capture_method_path_body():
    capture = _FIDELITY["write_style"]
    opener = StubOpener([{"code": 0, "data": {"updates": {"revision": 2}}}])
    client = _client(opener)
    client.put_style("Example8f0059b95ae797ae3980", "c8d13e!A1:A1", BOLD_FILL_FMT.wire())
    sent = opener.requests[0]
    assert sent["method"] == capture["method"] == "PUT"
    assert sent["url"].endswith(capture["path"])
    assert sent["body"] == capture["request_body"]


def test_ac1_a_bare_single_cell_target_is_forced_to_start_end_the_90202_guard():
    """The captured trap: a bare cell on this endpoint is ``90202 wrong range=…``."""
    trap = _SPIKE["style_put"]
    assert trap["code"] == 90202 and "wrong range" in trap["response"]["msg"]
    assert trap["request_body"]["appendStyle"]["range"] == "154e99!B2"   # a BARE cell
    live = _step("BARE single cell")
    assert live["code"] == 90202              # re-confirmed on our own disposable
    opener = StubOpener([{"code": 0, "data": {}}])
    _client(opener).put_style(TOKEN, f"{SID}!B2", {"font": {"bold": True}})
    assert opener.requests[0]["body"]["appendStyle"]["range"] == f"{SID}!B2:B2"


def test_ac1_the_request_carries_the_normalized_start_end_range_itself():
    req = StyleWriteRequest(f"{SID}!B2", CellStyle(bold=True))
    assert req.a1_range == f"{SID}!B2:B2"
    assert req.descriptor()["ranges"] == [f"{SID}!B2:B2"]


def test_ac1_the_request_is_frozen_and_json_round_trips():
    req = StyleWriteRequest(f"{SID}!A1:B2", BOLD_FILL_FMT)
    with pytest.raises(Exception):
        req.target = "nope"
    desc = req.descriptor()
    assert json.loads(json.dumps(desc)) == desc
    assert json.loads(json.dumps(req.style_preview())) == req.style_preview()


def test_ac1_fill_font_and_number_format_are_all_expressible_independently():
    assert CellStyle(back_color="#FFFF00").wire() == {"backColor": "#FFFF00"}
    assert CellStyle(bold=True, italic=True, font_size=18).wire() == {
        "font": {"bold": True, "italic": True, "fontSize": "18pt/1.5"}}
    assert CellStyle(formatter="0.00%").wire() == {"formatter": "0.00%"}
    assert CellStyle(fore_color="#FF0000").wire() == {"foreColor": "#FF0000"}


def test_ac1_and_combined_in_one_style_exactly_as_the_probe_wrote_it():
    combined = _step("E1 combined")["request_body"]["appendStyle"]["style"]
    assert CellStyle(bold=True, italic=True, font_size=18, back_color="#FFFF00",
                     fore_color="#FF0000", formatter="0.00%").wire() == combined
    assert _step("E1 combined")["code"] == 0
    # ...and the export saw every one of them land on E1.
    e1 = _PROBE["export"]["shipped_reader_cells"]["E1"]
    assert (e1["bold"], e1["italic"], e1["fill_rgb"], e1["num_fmt"]) == (
        True, True, "FFFFFF00", "0.00%")
    assert _PROBE["export"]["raw_resolved_fonts"]["E1"]["font"]["sz"] == "18"


def test_ac1_the_style_flows_through_dry_run_then_apply():
    gw = FakeStyleGateway()
    plan = dry_run([StyleWriteRequest(f"{SID}!A1:A1", BOLD_FILL_FMT)], gw, TOKEN)
    assert plan.entries[0].refusal is None
    assert plan.entries[0].write_kind == "style"
    log = apply(plan, gw)
    assert [e.outcome for e in log.entries] == ["applied"]
    assert gw.style_writes == [(TOKEN, f"{SID}!A1:A1", BOLD_FILL_FMT.wire())]
    assert len(gw.writes) == 1


def test_ac1_apply_reads_the_post_write_revision_out_of_the_updates_envelope():
    """Probed: ``PUT …/style`` reports its revision at ``data.updates.revision``."""
    assert _step("A5 fontSize '9pt/1.5'")["response"]["data"]["updates"]["revision"] == 3
    gw = FakeStyleGateway(revision=7)
    log = apply(dry_run([StyleWriteRequest(f"{SID}!A1:A1", CellStyle(bold=True))], gw, TOKEN),
                gw)
    assert log.entries[0].revision == 8
    assert ("read_revision", TOKEN) not in gw.calls[-1:]   # no metainfo fallback needed


def test_ac1_apply_falls_back_to_metainfo_when_the_reply_carries_no_revision():
    gw = FakeStyleGateway(revision=7, style_reply="bare")
    log = apply(dry_run([StyleWriteRequest(f"{SID}!A1:A1", CellStyle(bold=True))], gw, TOKEN),
                gw)
    assert log.entries[0].revision == 8
    assert gw.calls[-1] == ("read_revision", TOKEN)


def test_ac1_the_apply_log_names_the_leg_that_verifies_a_style_write():
    gw = FakeStyleGateway()
    log = apply(dry_run([StyleWriteRequest(f"{SID}!A1:A1", CellStyle(bold=True))], gw, TOKEN),
                gw)
    record = log.entries[0].structural
    assert record["verified_by"] == STYLE_VERIFICATION_LEG == "xlsx-export-style-leg"
    assert "export" in record["verification_note"]


# --------------------------------------------------------------------------- #
# AC2 — ONE style-write implementation in the tree                             #
# --------------------------------------------------------------------------- #

def test_ac2_exactly_one_style_write_implementation_exists_in_the_tree():
    """The point of the issue: the harness/library split is ENDED, not duplicated.

    The ``appendStyle`` body and the ``styles_batch_update`` body are each built in exactly
    ONE place in the whole repository — ``SheetsWriteClient``. A second definition (a harness
    copy, a probe helper imported by tests, a "temporary" duplicate) reddens here.
    """
    #: The two BODY-BUILD markers, chosen so reading a capture (``cap["appendStyle"]``) or
    #: naming the endpoint in prose does not count — only assembling the wire body does.
    build_markers = ('{"appendStyle":', '"styles_batch_update")')
    hits = {marker: [] for marker in build_markers}
    for root in (REPO_ROOT / "src", REPO_ROOT / "tests"):
        for path in sorted(root.rglob("*.py")):
            if path == Path(__file__):
                continue                      # this guard names the markers it looks for
            text = path.read_text(encoding="utf-8")
            for marker in build_markers:
                if marker in text:
                    hits[marker].append(str(path.relative_to(REPO_ROOT)))
    for marker, paths in hits.items():
        assert paths == ["src/larkdocio/sheets/write_client.py"], (
            f"{marker} is built in {paths} — a style write has exactly ONE implementation in "
            f"this tree (LD-188 AC2: promote, do not duplicate)")


def test_ac2_the_harness_no_longer_defines_a_style_writer_of_its_own():
    import sheets_write_harness as H
    assert not hasattr(H, "SheetsStyleWriter"), (
        "the harness style writer was promoted into src/ — it must not survive as a second "
        "implementation (LD-188 AC2)")
    text = (REPO_ROOT / "tests" / "sheets_write_harness.py").read_text(encoding="utf-8")
    assert "appendStyle" not in text


def test_ac2_the_shipped_client_is_what_the_l2_read_gate_now_styles_through():
    """The S5 fidelity gate keeps working — through ``src/``, not a harness twin."""
    gate = (REPO_ROOT / "tests" / "test_live_sheets_style_gate.py").read_text(encoding="utf-8")
    assert "H.SheetsStyleWriter" not in gate
    assert "styler=writer" in gate


# --------------------------------------------------------------------------- #
# AC3 — the PRE-WIRED gate: reserved op kinds used, leg matrix UNCHANGED       #
# --------------------------------------------------------------------------- #

def test_ac3_a_visual_style_classifies_as_the_reserved_STYLE_op_kind():
    assert WriteOpKind.STYLE == "style"
    assert StyleWriteRequest(f"{SID}!A1:A1", CellStyle(bold=True)).op_kinds == (
        WriteOpKind.STYLE,)
    assert StyleWriteRequest(f"{SID}!A1:A1", CellStyle(back_color="#FFFF00")).op_kinds == (
        WriteOpKind.STYLE,)


def test_ac3_a_formatter_only_write_classifies_as_NUMBER_FORMAT():
    """Probed: ``formatter`` alone, no font and no fill, is accepted (code 0)."""
    assert _step("formatter ONLY")["code"] == 0
    assert _PROBE["export"]["shipped_reader_cells"]["B1"]["num_fmt"] == "0.00%"
    assert WriteOpKind.NUMBER_FORMAT == "number-format"
    assert StyleWriteRequest(f"{SID}!B1:B1", CellStyle(formatter="0.00%")).op_kinds == (
        WriteOpKind.NUMBER_FORMAT,)


def test_ac3_a_combined_write_classifies_as_BOTH():
    assert StyleWriteRequest(f"{SID}!A1:A1", BOLD_FILL_FMT).op_kinds == (
        WriteOpKind.STYLE, WriteOpKind.NUMBER_FORMAT)


def test_ac3a_requires_style_leg_is_true_for_both_kinds():
    assert requires_style_leg((WriteOpKind.STYLE,)) is True
    assert requires_style_leg((WriteOpKind.NUMBER_FORMAT,)) is True
    for req in (StyleWriteRequest(f"{SID}!A1:A1", CellStyle(bold=True)),
                StyleWriteRequest(f"{SID}!A1:A1", CellStyle(formatter="0.00%")),
                BatchStyleWriteRequest.one_style([f"{SID}!A1:A1"], CellStyle(bold=True))):
        assert requires_style_leg(req.op_kinds) is True
        assert requires_merge_leg(req.op_kinds) is False


def test_ac3b_effective_verify_style_turns_on_automatically():
    kinds = StyleWriteRequest(f"{SID}!A1:A1", CellStyle(bold=True)).op_kinds
    assert effective_verify_style(kinds, verify_style=False) is True
    assert effective_verify_style((WriteOpKind.NUMBER_FORMAT,), verify_style=False) is True
    # ...and a plain value write still does NOT pay for the export.
    assert effective_verify_style(
        ValueWriteRequest.for_a1(f"{SID}!A1", 1).op_kinds, verify_style=False) is False


def test_ac3c_applying_a_style_write_without_the_export_leg_raises_GateNotVerified():
    kinds = StyleWriteRequest(f"{SID}!A1:A1", BOLD_FILL_FMT).op_kinds
    with pytest.raises(GateNotVerified) as exc:
        certify_gate_legs(kinds, values_leg_ran=True, style_leg_ran=False)
    assert "style/format leg" in str(exc.value)
    assert isinstance(exc.value, LarkDocIOError)
    # ...and it certifies once the leg ran.
    certify_gate_legs(kinds, values_leg_ran=True, style_leg_ran=True)


def test_ac3_the_leg_matrix_is_UNCHANGED_no_new_gate_wiring_was_added():
    """The whole point: this issue adds no gate wiring — the kinds were reserved for it."""
    assert STYLE_LEG_OP_KINDS == frozenset({
        WriteOpKind.STYLE, WriteOpKind.NUMBER_FORMAT, WriteOpKind.MERGE,
        WriteOpKind.STRUCTURE})
    assert MERGE_LEG_OP_KINDS == frozenset({WriteOpKind.MERGE, WriteOpKind.STRUCTURE})
    assert WriteOpKind.STYLE in STYLE_LEG_OP_KINDS
    assert WriteOpKind.NUMBER_FORMAT in STYLE_LEG_OP_KINDS


def test_ac3_no_new_write_op_kind_was_minted_for_this_family():
    kinds = {v for k, v in vars(WriteOpKind).items()
             if not k.startswith("_") and isinstance(v, str)}
    assert kinds == {"value", "style", "number-format", "merge", "structure", "tab",
                     "data-validation", "dimension-property", "freeze-panes"}


# --------------------------------------------------------------------------- #
# AC4 — the batch form: N ranges, ONE call                                     #
# --------------------------------------------------------------------------- #

def test_ac4_batch_update_styles_matches_the_capture_method_path_body():
    capture = _SPIKE["styles_batch_update"]
    opener = StubOpener([{"code": 0, "data": {"responses": []}}])
    client = _client(opener)
    client.batch_update_styles("Example0e7c15c322aeef5d5867", [
        {"ranges": ["154e99!A1:C1"], "style": {"font": {"bold": True},
                                               "backColor": "#D9EAD3"}},
        {"ranges": ["154e99!A2:C2"], "style": {"font": {"italic": True},
                                               "foreColor": "#FF0000"}},
    ])
    sent = opener.requests[0]
    assert sent["method"] == capture["method"] == "PUT"
    assert sent["url"].endswith(capture["path"])
    assert sent["body"] == capture["request_body"]


def test_ac4_a_multi_range_style_write_costs_ONE_call_not_N():
    gw = FakeStyleGateway()
    req = BatchStyleWriteRequest.one_style(
        [f"{SID}!A1:A1", f"{SID}!B1:B1", f"{SID}!C1:C1"], CellStyle(bold=True))
    log = apply(dry_run([req], gw, TOKEN), gw)
    assert [e.outcome for e in log.entries] == ["applied"]
    assert [w[0] for w in gw.writes] == ["batch_update_styles"]      # ONE write seam call
    _token, data = gw.batch_style_writes[0]
    assert data == [{"ranges": [f"{SID}!A1:A1", f"{SID}!B1:B1", f"{SID}!C1:C1"],
                     "style": {"font": {"bold": True}}}]


def test_ac4_N_styles_in_one_call_are_expressible_too():
    gw = FakeStyleGateway()
    req = BatchStyleWriteRequest([
        StyleSpan([f"{SID}!C2:C2"], CellStyle(back_color="#D9EAD3")),
        StyleSpan([f"{SID}!C3:C3"], CellStyle(italic=True, fore_color="#FF0000")),
    ])
    apply(dry_run([req], gw, TOKEN), gw)
    assert len(gw.writes) == 1
    _token, data = gw.batch_style_writes[0]
    assert data == [
        {"ranges": [f"{SID}!C2:C2"], "style": {"backColor": "#D9EAD3"}},
        {"ranges": [f"{SID}!C3:C3"], "style": {"font": {"italic": True},
                                               "foreColor": "#FF0000"}},
    ]
    # both shapes are PROBED accepted: separate elements, and one element with two ranges
    assert _step("TWO ranges, ONE call")["code"] == 0
    assert _step("ONE element carrying TWO ranges")["code"] == 0


def test_ac4_THE_AUDIT_S_IMMUNITY_CLAIM_IS_FALSE_AND_THE_BATCH_NORMALIZES_TOO():
    """The corrected premise. The audit said the ``ranges`` array is ``90202``-immune; the
    probe says it is not, so the batch path forces ``Start:End`` exactly like the single one."""
    bare = _step("BARE single-cell range")
    assert bare["request_body"]["data"][0]["ranges"] == [f"{SID}!C1"]
    assert bare["code"] == 90202 and "wrong range" in bare["msg"]
    opener = StubOpener([{"code": 0, "data": {"responses": []}}])
    _client(opener).batch_update_styles(
        TOKEN, [{"ranges": [f"{SID}!C1", f"{SID}!D1:D2"], "style": {"font": {"bold": True}}}])
    assert opener.requests[0]["body"]["data"][0]["ranges"] == [
        f"{SID}!C1:C1", f"{SID}!D1:D2"]


def test_ac4_the_batch_request_normalizes_its_own_ranges_as_well():
    req = BatchStyleWriteRequest.one_style([f"{SID}!C1"], CellStyle(bold=True))
    assert req.descriptor()["ranges"] == [f"{SID}!C1:C1"]
    assert req.wire_data() == [{"ranges": [f"{SID}!C1:C1"],
                                "style": {"font": {"bold": True}}}]


def test_ac4_an_empty_batch_is_refused_at_construction():
    with pytest.raises(StyleError) as exc:
        BatchStyleWriteRequest([])
    assert "no range" in str(exc.value).lower()
    with pytest.raises(StyleError):
        BatchStyleWriteRequest.one_style([], CellStyle(bold=True))


# --------------------------------------------------------------------------- #
# AC5 — the clamps: REFUSED pre-I/O (characterized), zero API calls            #
# --------------------------------------------------------------------------- #

def test_ac5_the_font_size_range_is_a_REFUSAL_not_a_silent_clamp():
    """AC5's fork, answered by evidence: 8 and 37 are refused, 9 and 36 land."""
    assert _step("UNDER the documented 9 floor")["code"] == 90204
    assert _step("OVER the documented 36 ceiling")["code"] == 90204
    assert (_step("the floor itself")["code"], _step("the ceiling itself")["code"]) == (0, 0)
    fonts = _PROBE["export"]["raw_resolved_fonts"]
    assert fonts["A5"]["font"]["sz"] == "9"       # the floor LANDED as asked
    assert fonts["A6"]["font"]["sz"] == "36"      # so did the ceiling
    # ...and neither out-of-range arm left any style behind (no silent clamp).
    for ref in ("A3", "A4"):
        assert fonts[ref]["s"] == 0
    assert (MIN_FONT_SIZE, MAX_FONT_SIZE) == (9, 36)


def test_ac5_an_out_of_range_font_size_refuses_at_construction_with_the_verbatim_body():
    for bad in (8, 37, 0, -1, 100):
        with pytest.raises(StyleError) as exc:
            CellStyle(font_size=bad)
        msg = str(exc.value)
        assert "invalid fontSize, fontSize must between 9 and 36" in msg   # Lark's own body
        assert "font_size=9" in msg and "font_size=36" in msg              # exampled repairs
        assert isinstance(exc.value, LarkConfigError)
        assert isinstance(exc.value, ValueError)


def test_ac5_the_boundaries_themselves_are_accepted():
    assert CellStyle(font_size=9).wire() == {"font": {"fontSize": "9pt/1.5"}}
    assert CellStyle(font_size=36).wire() == {"font": {"fontSize": "36pt/1.5"}}


def test_ac5_the_wire_form_is_the_STRING_a_bare_int_is_refused_by_lark():
    """Probed: a bare int ``fontSize`` is refused — and its message BLAMES THE RANGE."""
    step = _step("bare int")
    assert step["request_body"]["appendStyle"]["style"]["font"]["fontSize"] == 10
    assert step["code"] == 90204
    assert step["msg"] == "invalid fontSize, fontSize must between 9 and 36"
    # so the caller-facing form is an int and the wire string is built HERE, once.
    assert CellStyle(font_size=10).wire()["font"]["fontSize"] == "10pt/1.5"


def test_ac5_a_bool_or_float_font_size_is_refused_rather_than_coerced():
    for bad in (True, 12.0, "12", "12pt/1.5"):
        with pytest.raises(StyleError):
            CellStyle(font_size=bad)


def test_ac5_a_style_with_no_property_at_all_is_refused():
    with pytest.raises(StyleError) as exc:
        CellStyle()
    assert "no style" in str(exc.value).lower()


def test_ac5_a_malformed_colour_is_refused_rather_than_sent():
    for bad in ("FFFF00", "#FFF", "#GGGGGG", "yellow", "#ffff000", 16776960):
        with pytest.raises(StyleError) as exc:
            CellStyle(back_color=bad)
        assert "#RRGGBB" in str(exc.value)
    assert CellStyle(back_color="#ffff00").wire() == {"backColor": "#ffff00"}


def test_ac5_a_non_string_formatter_is_refused():
    for bad in (0, 0.0, True, "", "   "):
        with pytest.raises(StyleError):
            CellStyle(formatter=bad)


def test_ac5_bold_and_italic_must_be_bools():
    for bad in ("true", 1, "no"):
        with pytest.raises(StyleError):
            CellStyle(bold=bad)
        with pytest.raises(StyleError):
            CellStyle(italic=bad)


def test_ac5_every_construction_refusal_costs_ZERO_api_calls():
    gw = FakeStyleGateway()
    for factory in (lambda: CellStyle(font_size=8),
                    lambda: CellStyle(),
                    lambda: CellStyle(back_color="nope"),
                    lambda: StyleWriteRequest("banana", CellStyle(bold=True)),
                    lambda: BatchStyleWriteRequest([])):
        with pytest.raises((StyleError, LarkConfigError)):
            factory()
    assert gw.calls == [] and gw.writes == []


def test_ac5_a_malformed_a1_target_is_refused_by_the_a1_model_before_any_call():
    with pytest.raises(LarkConfigError) as exc:
        StyleWriteRequest(f"{SID}!banana", CellStyle(bold=True))
    assert "A1" in str(exc.value) or "cell" in str(exc.value)


# --------------------------------------------------------------------------- #
# AC6 — THE GATE'S COST IS DISCLOSED ON THE PLAN                               #
# --------------------------------------------------------------------------- #

def _notes_of(entry):
    from larkdocio.sheets.plan import preview_notes_of
    return list(preview_notes_of(entry.preview_note))


def _note_kinds(entry):
    return {n.get("kind") for n in _notes_of(entry)}


def test_ac6_a_style_write_s_plan_discloses_the_export_leg_s_cost():
    gw = FakeStyleGateway()
    plan = dry_run([StyleWriteRequest(f"{SID}!A1:A1", BOLD_FILL_FMT)], gw, TOKEN)
    note = next(n for n in _notes_of(plan.entries[0])
                if n["kind"] == "style-verification-cost")
    text = note["note"]
    # LD-152's ALREADY-SHIPPED wording, quoted rather than re-coined.
    for phrase in ("asynchronous whole-workbook export", "create", "poll", "download",
                   "unzip", "parse", "~1.2 s", "~30 s", "drive:export"):
        assert phrase in text, f"the shipped export-cost wording lost {phrase!r}"
    assert note["verified_by"] == STYLE_VERIFICATION_LEG
    assert note["scope"] == "drive:export"


def test_ac6_the_same_note_rides_a_number_format_only_write():
    gw = FakeStyleGateway()
    plan = dry_run([StyleWriteRequest(f"{SID}!B1:B1", CellStyle(formatter="0.00%"))],
                   gw, TOKEN)
    assert "style-verification-cost" in _note_kinds(plan.entries[0])


def test_ac6_the_note_is_ABSENT_from_a_plain_value_write_plan():
    """It must not leak into every plan — a value write pays for no export."""
    gw = FakeStyleGateway()
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1", "x")], gw, TOKEN)
    assert "style-verification-cost" not in _note_kinds(plan.entries[0])
    for entry in plan.entries:
        assert "drive:export" not in json.dumps(entry.preview_note or {})


def test_ac6_the_note_is_absent_from_a_value_only_BATCH_plan():
    gw = FakeStyleGateway()
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1", "x"),
                    ValueWriteRequest.for_a1(f"{SID}!A2", "y")], gw, TOKEN)
    assert json.dumps([e.preview_note for e in plan.entries]).count(
        "style-verification-cost") == 0


def test_ac6_the_cost_wording_is_not_a_second_definition_of_ld152_s():
    """The phrases live in ONE place in src/ (the note builder), quoting the guide."""
    guide = (REPO_ROOT / "src" / "larkdocio" / "GUIDE.md").read_text(encoding="utf-8")
    assert "**~1.2 s**" in guide and "**worst case is ~30 s**" in guide
    assert "drive:export" in guide


# --------------------------------------------------------------------------- #
# The merge question (the amplifier's "characterize and pin"), and the FIRST     #
# READING OF IT WAS WRONG — which is why there are two capture rounds.           #
# --------------------------------------------------------------------------- #

def test_a_style_lands_on_exactly_the_cells_its_range_names_probed():
    """Round 1 styled the WHOLE of a three-cell merge and got three styled cells with
    ``updatedCells: 3``; read as "a merge spreads the style", which it is not — the range had
    named three cells. Round 2 is the distinguishing experiment: the **anchor alone**."""
    round1 = _PROBE["export"]["shipped_reader_cells"]
    for ref in ("D1", "D2", "D3"):
        assert round1[ref]["fill_rgb"] == "FFFFFF00", (
            "round 1 no longer shows the whole-span style write landing on all three cells")
    assert _step("MERGED span")["response"]["data"]["updates"]["updatedCells"] == 3

    step = _MERGE_PROBE["steps"][1]
    assert step["request_body"]["appendStyle"]["range"].endswith("!A1:A1")
    assert step["code"] == 0
    assert step["response"]["data"]["updates"]["updatedCells"] == 1, (
        "the anchor-only write must report ONE updated cell — that is the whole finding")
    cells = _MERGE_PROBE["export"]["cells"]
    assert cells["A1"]["fill_rgb"] and cells["A1"]["bold"] is True
    assert cells["A2"]["fill_rgb"] is None and cells["A3"]["fill_rgb"] is None, (
        "a merge does NOT spread a style to its covered cells")


def test_the_plan_discloses_a_style_that_names_only_PART_of_a_merge():
    gw = FakeStyleGateway(merges=[{"start_row_index": 0, "end_row_index": 2,
                                   "start_column_index": 3, "end_column_index": 3}])
    plan = dry_run([StyleWriteRequest(f"{SID}!D1:D1", CellStyle(back_color="#FFFF00"))],
                   gw, TOKEN)
    note = next(n for n in _notes_of(plan.entries[0]) if n["kind"] == "style-partial-merge")
    assert "mixed stored style" in note["note"]
    assert "does NOT spread" in note["note"]
    # the repair is handed back, not described: the range that names the WHOLE region
    assert note["whole_regions"] == [f"{SID}!D1:D3"], note
    assert f"{SID}!D1:D3" in note["note"]


def test_the_disclosure_is_absent_when_the_target_covers_the_WHOLE_region():
    """Nothing to disclose: naming the whole merge styles every cell of it, which is what the
    caller asked for. A note here would cry wolf on the correct usage."""
    gw = FakeStyleGateway(merges=[{"start_row_index": 0, "end_row_index": 2,
                                   "start_column_index": 3, "end_column_index": 3}])
    plan = dry_run([StyleWriteRequest(f"{SID}!D1:D3", CellStyle(bold=True))], gw, TOKEN)
    assert "style-partial-merge" not in _note_kinds(plan.entries[0])


def test_the_disclosure_is_absent_when_the_range_hits_no_merge_at_all():
    gw = FakeStyleGateway(merges=[{"start_row_index": 0, "end_row_index": 2,
                                   "start_column_index": 3, "end_column_index": 3}])
    plan = dry_run([StyleWriteRequest(f"{SID}!A1:A1", CellStyle(bold=True))], gw, TOKEN)
    assert "style-partial-merge" not in _note_kinds(plan.entries[0])


def test_the_merge_read_costs_no_extra_call_it_rides_the_tab_read():
    gw = FakeStyleGateway(merges=[{"start_row_index": 0, "end_row_index": 2,
                                   "start_column_index": 3, "end_column_index": 3}])
    dry_run([StyleWriteRequest(f"{SID}!D1:D1", CellStyle(bold=True))], gw, TOKEN)
    assert [c[0] for c in gw.calls].count("read_sheet_geometry") == 1
    assert "read_values" not in [c[0] for c in gw.calls]      # no before-snapshot is taken


def test_the_cost_note_and_the_merge_note_coexist_neither_displaces_the_other():
    gw = FakeStyleGateway(merges=[{"start_row_index": 0, "end_row_index": 2,
                                   "start_column_index": 3, "end_column_index": 3}])
    plan = dry_run([StyleWriteRequest(f"{SID}!D2:D2", BOLD_FILL_FMT)], gw, TOKEN)
    assert _note_kinds(plan.entries[0]) == {"style-verification-cost", "style-partial-merge"}


# --------------------------------------------------------------------------- #
# The engine's standard discipline still applies to the new family             #
# --------------------------------------------------------------------------- #

def test_an_unknown_tab_refuses_at_plan_time_with_a_did_you_mean():
    gw = FakeStyleGateway()
    plan = dry_run([StyleWriteRequest("Sheet1!A1:A1", CellStyle(bold=True))], gw, TOKEN)
    refusal = plan.entries[0].refusal
    assert refusal.reason == Refusal.UNKNOWN_TAB
    assert SID in refusal.detail          # the did-you-mean names the real sheet_id
    assert gw.writes == []                # ZERO writes


def test_a_stale_revision_refuses_the_style_write_and_writes_nothing():
    gw = FakeStyleGateway(revision=7)
    plan = dry_run([StyleWriteRequest(f"{SID}!A1:A1", CellStyle(bold=True))], gw, TOKEN)
    gw.revision = 99                       # somebody else edited the spreadsheet
    log = apply(plan, gw)
    assert log.entries[0].outcome == "stale"
    assert log.entries[0].refusal.reason == Refusal.STALE_SHEET
    assert gw.writes == []


def test_an_api_error_on_the_style_write_is_typed_and_entry_scoped():
    gw = FakeStyleGateway(fail_write=LarkAPIError("nope", code=90204))
    plan = dry_run([StyleWriteRequest(f"{SID}!A1:A1", CellStyle(bold=True))], gw, TOKEN)
    log = apply(plan, gw)
    assert log.entries[0].outcome == "refused"
    assert log.entries[0].refusal.reason == Refusal.API_ERROR


def test_the_two_style_seams_are_registered_as_WRITE_seams():
    """Forget this and the engine reports "nothing landed" about a call that landed."""
    assert {"put_style", "batch_update_styles"} <= WRITE_SEAMS


def test_the_family_is_registered_once_in_the_ONE_dispatch_seam():
    style = [d for d in sheets_ops.OPS if d.kind == "style"]
    assert len(style) == 1
    desc = style[0]
    assert desc.write_kind == "style"
    assert desc.entry_ops == ("style",)
    assert set(desc.request_type) == {StyleWriteRequest, BatchStyleWriteRequest}
    assert sheets_ops.classify(StyleWriteRequest(f"{SID}!A1:A1", CellStyle(bold=True))) == \
        "style"


def test_capabilities_reports_the_style_write_ops():
    """DERIVED off OPS — nothing hand-edited, which is the registration seam working."""
    surface = capabilities(full=True)["surfaces"]["sheets-write"]
    ops = {op["name"]: op for op in surface["operations"]}
    assert "style" in ops
    assert ops["style"]["projected_from"] == "larkdocio.sheets.ops.OPS"
    assert set(ops["style"]["request_types"]) == {"StyleWriteRequest",
                                                 "BatchStyleWriteRequest"}
    assert ops["style"]["permissions"]["api_using"] is True
    assert ops["style"]["permissions"]["credential_app"] == "write"
