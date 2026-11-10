"""LD-116 — the two-leg (three-leg) write-gate fidelity differ.

Two halves, proven together here:

1. **The auto-on trigger (shipped src — the engine knows its op types).** The plan/apply
   engine (:mod:`larkdocio.sheets.write_apply`) classifies each write's **op-kinds**
   (:class:`~larkdocio.sheets.write_apply.WriteOpKind`) and derives which fidelity legs
   its surgical proof needs: the cheap live **values leg** always; the export-based
   **style/format leg** (``--verify-style`` AUTO-ON) for a style / number-format / merge /
   structure write; the live **merge leg** for a merge / structure write (the Sheets read-fidelity spec § D4). The
   guard :func:`~larkdocio.sheets.write_apply.certify_gate_legs` is the invariant that a
   **style write cannot be certified surgical without the style leg** — the trigger lives in
   the engine, not a caller's memory.

2. **The differ legs (gate tooling — the sheets_values_diff twin).** ``sheets_fidelity_diff``
   adds the **style/format leg** (diff the LD-114 export reader's styles.xml-derived per-cell
   bold/italic/fill/numFmt between a baseline and a post-write export) and the **merge leg**
   (diff the v3 ``merges`` array, 0-idx end-inclusive) to the LD-113 **values leg** (re-exported
   unchanged). Every failure NAMES the offending cell + attribute, actionable like the docx
   gates' evidence lines.

Offline: synthesized baseline/post workbooks (``xlsx_synth``) → parsed (LD-114 ``parse_xlsx``)
→ each leg exercised red-then-green. The live style-leg cycle on a disposable is S5 (LD-118).
"""
import pytest

import sheets_fidelity_diff as D
import sheets_values_diff as V
import xlsx_synth as X
from larkdocio.sheets.export_reader import parse_xlsx
from larkdocio.sheets.models import Merge
from larkdocio.sheets.write_apply import (
    GateNotVerified,
    ValueWriteRequest,
    WriteOpKind,
    certify_gate_legs,
    effective_verify_style,
    requires_merge_leg,
    requires_style_leg,
)


# --------------------------------------------------------------------------- #
# Test scaffolding — build a parsed workbook with per-cell control over the     #
# four export-reader style attributes (bold / italic / fill_rgb / num_fmt).     #
# --------------------------------------------------------------------------- #

def _wb(specs, merges=()):
    """Synthesize + parse a one-sheet (``Sheet1``) :class:`ParsedWorkbook` from
    ``specs`` — ``{ref: {"value", "bold", "italic", "fill", "numfmt"}}`` — so each
    cell resolves to exactly the style you name (distinct ``s=`` indexes, custom
    numFmt ids ≥164, solid fills). ``merges`` are A1 range strings for the worksheet
    ``<mergeCell>`` refs."""
    fonts = [{}]                                          # 0 = default
    fills = [{"pattern": "none"}, {"pattern": "gray125"}]  # 0/1 reserved in real xlsx
    num_fmts = []                                          # [(id, code)]
    cell_xfs = [{"numFmtId": 0, "fontId": 0, "fillId": 0}]  # 0 = default
    numfmt_ids = {}
    cells = []
    for ref, spec in specs.items():
        bold = spec.get("bold", False)
        italic = spec.get("italic", False)
        fill = spec.get("fill")
        numfmt = spec.get("numfmt")
        value = spec.get("value", "0")
        if bold or italic:
            fonts.append({"bold": bold, "italic": italic})
            font_id = len(fonts) - 1
        else:
            font_id = 0
        if fill:
            fills.append({"pattern": "solid", "fg_rgb": fill})
            fill_id = len(fills) - 1
        else:
            fill_id = 0
        if numfmt:
            if numfmt not in numfmt_ids:
                numfmt_ids[numfmt] = 164 + len(numfmt_ids)
                num_fmts.append((numfmt_ids[numfmt], numfmt))
            num_fmt_id = numfmt_ids[numfmt]
        else:
            num_fmt_id = 0
        cell_xfs.append({"numFmtId": num_fmt_id, "fontId": font_id, "fillId": fill_id})
        cells.append((ref, {"s": len(cell_xfs) - 1, "v": str(value)}))
    styles = X.styles_xml(num_fmts=num_fmts, fonts=fonts, fills=fills, cell_xfs=cell_xfs)
    data = X.build_workbook(
        [{"name": "Sheet1", "cells": cells, "merges": merges}], styles=styles
    )
    return parse_xlsx(data)


# =========================================================================== #
# AC1 — the values leg (always). The differ re-exports the LD-113 values leg    #
# UNCHANGED (kept as-is); a surgical-vs-non-surgical value diff is proven.       #
# =========================================================================== #

def test_values_leg_is_the_unchanged_ld113_leg():
    # "keep as-is" — the unified differ re-exports the SAME pure functions the LD-113
    # value gate already uses, so plain value writes stay on the cheap values leg.
    assert D.assert_surgical is V.assert_surgical
    assert D.assert_identical is V.assert_identical
    assert D.changed_cells is V.changed_cells


def test_values_leg_surgical_pass_and_non_surgical_catch():
    before = [["a", "b"], ["c", "d"]]
    surgical = [["a", "b"], ["C2!", "d"]]   # only A2 changed
    assert D.assert_surgical(before, surgical, "A2") == {(1, 0)}

    oversized = [["a", "B!"], ["C2!", "d"]]  # A2 AND B1 changed — stray
    with pytest.raises(AssertionError) as e:
        D.assert_surgical(before, oversized, "A2")
    assert "(0, 1)" in str(e.value)          # the differ NAMES the stray cell


# =========================================================================== #
# AC2 — the style/format leg (export-based). Catches a bold / fill / numFmt      #
# change; names the offending cell + attribute; clean on a no-op.               #
# =========================================================================== #

def test_style_leg_clean_pass_on_identical_workbooks():
    specs = {"A1": {"bold": True, "value": "h"}, "B2": {"fill": "FFFF0000", "value": "1"}}
    assert D.style_diffs(_wb(specs), _wb(specs)) == []
    D.assert_style_clean(_wb(specs), _wb(specs))       # no raise
    D.assert_style_surgical(_wb(specs), _wb(specs), [])  # no target, no change → clean


def test_style_leg_catches_fill_change_on_a_neighbor():
    # The target write is B2; a stray fill lands on the NEIGHBOR A1 — the style leg
    # must flag A1.fill_rgb, not silently pass (the amplifier: fill changed on a neighbor).
    before = _wb({"A1": {"value": "h"}, "B2": {"value": "1"}})
    after = _wb({"A1": {"fill": "FFFF0000", "value": "h"}, "B2": {"value": "1"}})
    with pytest.raises(AssertionError) as e:
        D.assert_style_surgical(before, after, ["B2"])
    msg = str(e.value)
    assert "A1" in msg and "fill_rgb" in msg          # names the offending cell + attribute
    assert "FFFF0000" in msg                          # names the drifted value


def test_style_leg_catches_numfmt_drift():
    before = _wb({"B2": {"value": "0.1234"}})
    after = _wb({"B2": {"numfmt": "0.00%", "value": "0.1234"}})
    diffs = D.style_diffs(before, after)
    assert len(diffs) == 1
    d = diffs[0]
    assert d.ref == "B2" and d.attr == "num_fmt"
    assert d.before is None and d.after == "0.00%"
    assert "B2" in d.describe() and "num_fmt" in d.describe()


def test_style_leg_catches_bold_change():
    before = _wb({"A1": {"value": "h"}})
    after = _wb({"A1": {"bold": True, "value": "h"}})
    diffs = D.style_diffs(before, after)
    assert [(d.ref, d.attr, d.before, d.after) for d in diffs] == [
        ("A1", "bold", False, True)
    ]


def test_style_leg_surgical_pass_when_only_the_target_style_changed():
    before = _wb({"A1": {"value": "h"}, "B2": {"value": "1"}})
    after = _wb({"A1": {"value": "h"}, "B2": {"bold": True, "value": "1"}})
    diffs = D.assert_style_surgical(before, after, ["B2"])   # B2 is the target → clean
    assert [(d.ref, d.attr) for d in diffs] == [("B2", "bold")]


def test_style_leg_numfmt_only_and_fill_only_are_isolated():
    # amplifier: a numFmt-only change and a fill-only change each surface exactly one attr.
    base = _wb({"C3": {"value": "5"}})
    numfmt_only = _wb({"C3": {"numfmt": "#,##0", "value": "5"}})
    fill_only = _wb({"C3": {"fill": "FF00FF00", "value": "5"}})
    assert [d.attr for d in D.style_diffs(base, numfmt_only)] == ["num_fmt"]
    assert [d.attr for d in D.style_diffs(base, fill_only)] == ["fill_rgb"]


# =========================================================================== #
# S5 (LD-118) — assert_cell_style: the ABSOLUTE per-cell fidelity assertion the  #
# live L2 gate keys on. Unlike style_diffs (baseline→post relative), this pins a #
# parsed cell's resolved style to EXACT expected values (bold + fill ARGB +      #
# numFmt pattern — LD-107 Q2), and FAILS ACTIONABLY naming EACH missing/wrong    #
# attribute. The gate's whole point is a missing fill/bold/numFmt reddens loudly. #
# =========================================================================== #

def test_assert_cell_style_passes_on_the_full_ld107_q2_fidelity():
    # the exact LD-107 Q2 styled cell: bold + fill FFFFFF00 + numFmt 0.00%.
    cell = _wb(
        {"A1": {"bold": True, "fill": "FFFFFF00", "numfmt": "0.00%", "value": "0.1234"}}
    ).first_sheet.cell("A1")
    D.assert_cell_style(cell, bold=True, fill_rgb="FFFFFF00", num_fmt="0.00%")  # no raise


def test_assert_cell_style_fails_actionably_when_the_fill_is_missing():
    # THE amplifier (issue TEST RIGOR): a synthesized workbook whose target carries
    # the bold + numFmt but LACKS the fill — the assertion must FAIL, naming fill_rgb
    # with expected→actual, not silently pass on "some style".
    cell = _wb(
        {"A1": {"bold": True, "numfmt": "0.00%", "value": "0.1234"}}  # no fill
    ).first_sheet.cell("A1")
    with pytest.raises(AssertionError) as e:
        D.assert_cell_style(cell, bold=True, fill_rgb="FFFFFF00", num_fmt="0.00%")
    msg = str(e.value)
    assert "fill_rgb" in msg and "FFFFFF00" in msg    # names the missing attribute + expected
    assert "A1" in msg                                # names the cell
    assert "bold" not in msg and "num_fmt" not in msg  # the satisfied attrs are NOT flagged


def test_assert_cell_style_fails_when_bold_missing():
    cell = _wb(
        {"A1": {"fill": "FFFFFF00", "numfmt": "0.00%", "value": "0.1234"}}  # no bold
    ).first_sheet.cell("A1")
    with pytest.raises(AssertionError) as e:
        D.assert_cell_style(cell, bold=True, fill_rgb="FFFFFF00", num_fmt="0.00%")
    assert "bold" in str(e.value)


def test_assert_cell_style_fails_when_numfmt_missing():
    cell = _wb(
        {"A1": {"bold": True, "fill": "FFFFFF00", "value": "0.1234"}}  # no numFmt
    ).first_sheet.cell("A1")
    with pytest.raises(AssertionError) as e:
        D.assert_cell_style(cell, bold=True, fill_rgb="FFFFFF00", num_fmt="0.00%")
    msg = str(e.value)
    assert "num_fmt" in msg and "0.00%" in msg


def test_assert_cell_style_reports_all_missing_attributes_at_once():
    # a wholly-unstyled cell fails on ALL THREE named attributes in one raise (so a QA
    # sees the complete gap, not one-at-a-time).
    cell = _wb({"A1": {"value": "0.1234"}}).first_sheet.cell("A1")
    with pytest.raises(AssertionError) as e:
        D.assert_cell_style(cell, bold=True, fill_rgb="FFFFFF00", num_fmt="0.00%")
    msg = str(e.value)
    assert "bold" in msg and "fill_rgb" in msg and "num_fmt" in msg


def test_assert_cell_style_none_cell_is_a_total_miss_not_a_crash():
    # a target that vanished from the export (cell is None) is a loud miss naming the
    # ref + every expected attribute — never an AttributeError.
    with pytest.raises(AssertionError) as e:
        D.assert_cell_style(None, ref="A1", bold=True, fill_rgb="FFFFFF00")
    msg = str(e.value)
    assert "A1" in msg and "bold" in msg and "fill_rgb" in msg


def test_assert_cell_style_only_checks_named_attributes():
    # an unnamed attribute (italic here) is not asserted — the gate names exactly the
    # three it wrote (bold/fill/numFmt), and an incidental italic must not trip it.
    cell = _wb(
        {"A1": {"bold": True, "italic": True, "fill": "FFFFFF00", "value": "0.1234"}}
    ).first_sheet.cell("A1")
    D.assert_cell_style(cell, bold=True, fill_rgb="FFFFFF00")  # italic unnamed → no raise


# =========================================================================== #
# AC3 — the merge leg (live v3 merges array, 0-idx end-inclusive). A merge      #
# add / remove is caught, without any export.                                   #
# =========================================================================== #

def test_merge_leg_identical_pass():
    before = [Merge(0, 0, 0, 2)]
    after = [Merge(0, 0, 0, 2)]
    assert D.merge_delta(before, after) == (set(), set())
    D.assert_merges_identical(before, after)   # no raise


def test_merge_leg_catches_an_added_region():
    before = []
    after = [Merge(0, 0, 0, 2)]                # A1:C1 newly merged
    added, removed = D.merge_delta(before, after)
    assert added == {(0, 0, 0, 2)} and removed == set()
    with pytest.raises(AssertionError) as e:
        D.assert_merges_identical(before, after)
    assert "(0, 0, 0, 2)" in str(e.value)      # names the region


def test_merge_leg_catches_a_removed_region():
    before = [Merge(0, 0, 0, 2)]
    after = []
    added, removed = D.merge_delta(before, after)
    assert added == set() and removed == {(0, 0, 0, 2)}


def test_merge_leg_asserts_an_expected_delta():
    before = [Merge(0, 0, 0, 2)]
    after = [Merge(0, 0, 0, 2), Merge(2, 4, 0, 0)]   # A3:A5 added, A1:C1 kept
    D.assert_merge_change(before, after, added=[Merge(2, 4, 0, 0)])


def test_merge_leg_accepts_v3_dicts_and_tuples_and_merge_objects():
    v3 = [{"start_row_index": 0, "end_row_index": 0,
           "start_column_index": 0, "end_column_index": 2}]
    assert D.merge_delta(v3, [Merge(0, 0, 0, 2)]) == (set(), set())
    assert D.merge_delta([(0, 0, 0, 2)], [Merge(0, 0, 0, 2)]) == (set(), set())


# =========================================================================== #
# AC2 / AC4 — the AUTO-ON trigger: the engine knows its op-kinds; --verify-style #
# auto-on for style/format/merge/structure; a plain value write stays cheap.     #
# =========================================================================== #

def test_value_write_request_reports_value_op_kind_only():
    req = ValueWriteRequest.for_a1("A1:A1", [["x"]])
    assert req.op_kinds == (WriteOpKind.VALUE,)


def test_requires_style_leg_auto_on_matrix():
    # style / number-format / merge / structure each REQUIRE the export style leg…
    assert requires_style_leg([WriteOpKind.STYLE]) is True
    assert requires_style_leg([WriteOpKind.NUMBER_FORMAT]) is True
    assert requires_style_leg([WriteOpKind.MERGE]) is True
    assert requires_style_leg([WriteOpKind.STRUCTURE]) is True
    # …a plain value write does NOT (cheap values leg only, no export).
    assert requires_style_leg([WriteOpKind.VALUE]) is False


def test_effective_verify_style_flag_and_auto_on():
    # a value-only write leaves --verify-style OFF even though nothing was requested…
    assert effective_verify_style([WriteOpKind.VALUE]) is False
    # …an explicit flag can still force it on…
    assert effective_verify_style([WriteOpKind.VALUE], verify_style=True) is True
    # …and a style/merge/structure write forces it on regardless of the flag (auto-on).
    assert effective_verify_style([WriteOpKind.STYLE], verify_style=False) is True
    assert effective_verify_style([WriteOpKind.MERGE], verify_style=False) is True


def test_requires_merge_leg_only_for_merge_or_structure():
    assert requires_merge_leg([WriteOpKind.MERGE]) is True
    assert requires_merge_leg([WriteOpKind.STRUCTURE]) is True
    assert requires_merge_leg([WriteOpKind.STYLE]) is False
    assert requires_merge_leg([WriteOpKind.VALUE]) is False


def test_a_value_only_write_triggers_no_export_leg():
    # AC4: a plain value write is certified surgical on the cheap values leg ALONE —
    # no style/export leg required (proves plain value writes stay export-free).
    req = ValueWriteRequest.for_a1("A2:A2", [["v"]])
    certify_gate_legs(req.op_kinds, values_leg_ran=True, style_leg_ran=False,
                      merge_leg_ran=False)   # no raise


def test_a_style_write_cannot_be_gate_verified_without_the_style_leg():
    # AC2 core: the invariant — a style write certified on the values leg alone RAISES,
    # naming the missing style/format leg. The trigger lives in the engine.
    with pytest.raises(GateNotVerified) as e:
        certify_gate_legs([WriteOpKind.STYLE], values_leg_ran=True, style_leg_ran=False)
    msg = str(e.value)
    assert "style" in msg.lower() and "verify-style" in msg
    # …and once the style leg ran, the same write certifies clean.
    certify_gate_legs([WriteOpKind.STYLE], values_leg_ran=True, style_leg_ran=True)


def test_a_merge_write_cannot_be_gate_verified_without_the_merge_leg():
    # a merge write needs BOTH the style leg (auto-on) and the merge leg.
    with pytest.raises(GateNotVerified) as e:
        certify_gate_legs([WriteOpKind.MERGE], values_leg_ran=True,
                          style_leg_ran=True, merge_leg_ran=False)
    assert "merge" in str(e.value).lower()
    certify_gate_legs([WriteOpKind.MERGE], values_leg_ran=True,
                      style_leg_ran=True, merge_leg_ran=True)   # no raise


def test_the_always_on_values_leg_is_mandatory_for_any_write():
    with pytest.raises(GateNotVerified) as e:
        certify_gate_legs([WriteOpKind.VALUE], values_leg_ran=False)
    assert "values leg" in str(e.value)
