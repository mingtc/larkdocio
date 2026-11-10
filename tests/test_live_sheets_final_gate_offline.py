"""Offline guards + differ-teeth for THE ARC'S FINAL GATE — the rich + structural
Sheets round-trip ring under the FULL two-leg differ (LD-124).

NOT marked ``live_write`` — these run in the default ``pytest -q`` with no creds and no
network. Two jobs:

1. **The gate's own differ assertions have TEETH (the TEST-RIGOR amplifier).** The final
   gate proves each rich/structural write **surgical** with the full differ (values leg +
   style/format export leg + merge leg) *and* proves a live delete **destructive-safe**
   (its apply-log carries the FULL removed payload). Those assertions are only worth
   running if they REDDEN on a real defect, so — on synthesized fixtures — we prove:
   **a missed style perturbation**, **a missed merge drift**, and **an incomplete
   removed-payload** each raise. If any of those assertions ever goes toothless, the
   binding live gate would pass on a broken write; these tests are the backstop.

2. **The credential-gated gate keeps its shape.** Lint-style guards over the live gate
   source (``tests/test_live_sheets_final_gate.py``) pin the discipline the binding
   round-trip depends on: the module-level ``live_write`` marker, the loud skip, WRITE
   creds only, the D7 disposable-only invariant (never the scratch sheet / read canary /
   zoo / a real doc), and that it actually exercises **all four** write kinds under the
   full differ + the destructive-safe removed-payload assertion + the zero-orphan
   close-out.

The binding round-trip itself (AC2-AC5) only runs under ``pytest -m live_write`` at QA with
write creds against a self-provisioned disposable.
"""
from pathlib import Path

import pytest

import sheets_fidelity_diff as D
import xlsx_synth as X
from larkdocio.sheets.export_reader import parse_xlsx
from larkdocio.sheets.models import Merge


# --------------------------------------------------------------------------- #
# Synthesized parsed workbook — per-cell control over the four export-reader     #
# style attributes (the tests/test_sheets_fidelity_diff.py `_wb` shape).         #
# --------------------------------------------------------------------------- #

def _wb(specs, merges=()):
    """Synthesize + parse a one-sheet ``Sheet1`` :class:`ParsedWorkbook` from
    ``specs`` — ``{ref: {"value","bold","italic","fill","numfmt"}}`` — so each cell
    resolves to exactly the style named (distinct ``s=`` indexes, custom numFmt ids
    ≥164, solid fills)."""
    fonts = [{}]
    fills = [{"pattern": "none"}, {"pattern": "gray125"}]
    num_fmts = []
    cell_xfs = [{"numFmtId": 0, "fontId": 0, "fillId": 0}]
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
# TEETH #3 — the destructive-safe removed-payload assertion (NEW, LD-124/AC3). #
# The gate reads a LIVE delete's apply-log `entry.structural["removed"]` and    #
# asserts it is COMPLETE — enough to reconstruct what was destroyed. Prove the  #
# assertion reddens on an incomplete payload (the TEST-RIGOR amplifier).        #
# =========================================================================== #

_COMPLETE_REMOVED = {
    "a1_range": "sid!A2:C3",
    "values": [["b1", "b2", "b3"], ["c1", "c2", "c3"]],
    "geometry": {"row_count": 4, "column_count": 3, "merges": []},
    "removed_merges": [],
}


def test_assert_removed_payload_complete_passes_on_a_full_payload():
    # a complete payload (addressing range + removed values + pre-write geometry) passes
    # and returns the reconstructable removed values.
    got = D.assert_removed_payload_complete(_COMPLETE_REMOVED)
    assert got == _COMPLETE_REMOVED["values"]


def test_assert_removed_payload_complete_can_pin_the_reconstructed_values():
    # when the gate knows exactly what the delete destroyed, it can pin the reconstruction
    # byte-exact — the removal is reconstructable, not merely present.
    D.assert_removed_payload_complete(
        _COMPLETE_REMOVED, expected_values=[["b1", "b2", "b3"], ["c1", "c2", "c3"]]
    )
    with pytest.raises(AssertionError) as e:
        D.assert_removed_payload_complete(
            _COMPLETE_REMOVED, expected_values=[["WRONG"]]
        )
    assert "reconstruct" in str(e.value).lower() or "expected" in str(e.value).lower()


def test_assert_removed_payload_complete_reddens_on_a_none_payload():
    # a delete that recorded NO removed payload (the destructive-safe invariant would have
    # REFUSED it) is a total miss — never a TypeError on None.
    with pytest.raises(AssertionError) as e:
        D.assert_removed_payload_complete(None)
    assert "no removed payload" in str(e.value).lower() or "removed" in str(e.value).lower()


@pytest.mark.parametrize("missing", ["a1_range", "values", "geometry"])
def test_assert_removed_payload_complete_reddens_on_each_missing_field(missing):
    # THE amplifier: an incomplete payload (any one of the reconstruct-critical fields
    # dropped) must FAIL, NAMING the missing field — so a payload regression in the
    # engine's snapshot cannot slip past the live gate.
    broken = dict(_COMPLETE_REMOVED)
    broken.pop(missing)
    with pytest.raises(AssertionError) as e:
        D.assert_removed_payload_complete(broken)
    assert missing in str(e.value)


def test_assert_removed_payload_complete_names_all_missing_fields_at_once():
    # a wholly-empty payload names every reconstruct-critical field in one raise (a QA sees
    # the complete gap, not one field at a time).
    with pytest.raises(AssertionError) as e:
        D.assert_removed_payload_complete({})
    msg = str(e.value)
    assert "a1_range" in msg and "values" in msg and "geometry" in msg


# =========================================================================== #
# TEETH #1 — the style/format export leg (auto-on for these write kinds, D9).   #
# The final gate exports baseline vs post-write and proves each rich/structural #
# write surgical: NO style strays onto a guard neighbour. Prove a MISSED style   #
# perturbation reddens (the amplifier: "the style leg catches a stray fill").    #
# =========================================================================== #

def test_style_leg_catches_a_stray_fill_on_a_guard_neighbour_of_a_rich_write():
    # The rich write targets A1:A4 (four rich cells); A5 is a guard neighbour that must
    # keep its style. A stray fill lands on A5 — the style leg (auto-on) must flag A5,
    # not silently pass, exactly as the final gate exports+asserts per write kind.
    rich_targets = ["A1", "A2", "A3", "A4"]
    before = _wb({r: {"value": r} for r in rich_targets + ["A5"]})
    after = _wb({**{r: {"value": r} for r in rich_targets}, "A5": {"fill": "FF00FF00", "value": "A5"}})
    with pytest.raises(AssertionError) as e:
        D.assert_style_surgical(before, after, rich_targets)
    msg = str(e.value)
    assert "A5" in msg and "fill_rgb" in msg      # names the offending neighbour + attr
    assert "FF00FF00" in msg                       # names the drifted value


def test_style_leg_is_clean_when_only_the_targets_carry_style():
    # the GREEN half — a rich write that styles only its own targets (A1 bold) leaves the
    # guard neighbour untouched → surgical, no raise.
    before = _wb({"A1": {"value": "x"}, "A5": {"value": "guard"}})
    after = _wb({"A1": {"bold": True, "value": "x"}, "A5": {"value": "guard"}})
    diffs = D.assert_style_surgical(before, after, ["A1", "A2", "A3", "A4"])
    assert [(d.ref, d.attr) for d in diffs] == [("A1", "bold")]


# =========================================================================== #
# TEETH #2 — the merge leg (live v3 merges array, 0-idx end-inclusive). A rich / #
# dropdown / insert write must NOT touch merges; the merge write's delta is      #
# EXACT. Prove a missed merge drift reddens (the amplifier: "the merge leg       #
# catches a stray merge").                                                       #
# =========================================================================== #

def test_merge_leg_catches_a_stray_merge_on_a_non_merge_write():
    # a rich / dropdown / insert write must leave merges byte-identical; a stray merge that
    # appeared (0-idx end-inclusive A1:C1) must redden assert_merges_identical, NAMING it.
    with pytest.raises(AssertionError) as e:
        D.assert_merges_identical([], [Merge(0, 0, 0, 2)])
    assert "(0, 0, 0, 2)" in str(e.value)


def test_merge_leg_catches_the_wrong_delta_on_the_merge_write():
    # the merge write's surgical proof is an EXACT delta; a drift (the write claimed to add
    # A5:C5 == 0-idx (4,4,0,2) but the live merges show a DIFFERENT region added) reddens
    # assert_merge_change, showing got-vs-expected.
    before = []
    after = [Merge(4, 4, 0, 1)]                       # A5:B5 added — NOT the expected A5:C5
    with pytest.raises(AssertionError) as e:
        D.assert_merge_change(before, after, added=[Merge(4, 4, 0, 2)])
    msg = str(e.value)
    assert "(4, 4, 0, 1)" in msg and "(4, 4, 0, 2)" in msg   # got vs expected


def test_merge_leg_exact_delta_passes_on_the_real_merge():
    # the GREEN half — the merge write added EXACTLY A5:C5 (0-idx (4,4,0,2)), none removed.
    D.assert_merge_change([], [Merge(4, 4, 0, 2)], added=[Merge(4, 4, 0, 2)], removed=[])


# =========================================================================== #
# SHAPE GUARDS — lint over the credential-gated live gate source so a future     #
# edit cannot quietly break the discipline the binding round-trip depends on     #
# (the tests/test_live_sheets_style_gate_offline.py posture, widened to the       #
# final-gate ring: all four write kinds + the full differ + destructive-safe).   #
# =========================================================================== #

GATE_SRC = Path(__file__).resolve().parent / "test_live_sheets_final_gate.py"


def _src() -> str:
    return GATE_SRC.read_text(encoding="utf-8")


def test_gate_file_exists():
    assert GATE_SRC.exists(), (
        f"the arc's final-gate file {GATE_SRC.name} must exist (LD-124 AC1)."
    )


def test_gate_marked_live_write_at_module_level():
    # a module-level `pytestmark = pytest.mark.live_write` is how every family joins the ONE
    # ring — one `pytest -m live_write` selects them ALL together (AC1/AC5).
    assert "pytestmark = pytest.mark.live_write" in _src(), (
        "the final gate must set module-level pytestmark = pytest.mark.live_write so it "
        "joins the SINGLE live_write ring (AC1/AC5)."
    )


def test_gate_skips_loudly_when_write_creds_unset():
    src = _src()
    assert "live_write_missing_reason" in src and "pytest.skip" in src, (
        "the gate must gate on canary_support.live_write_missing_reason() and pytest.skip "
        "with it — a creds-less env skips LOUDLY, never runs silently past absent creds "
        "(AC1)."
    )


def test_gate_exercises_all_four_write_kinds():
    src = _src()
    # (1) rich cell — all four encoded types; (2) dropdown rule; (3) structural insert/delete;
    # (4) merge/tab. Each drives the gated engine (dry_run→apply). AC2/AC5.
    for kind, tokens in {
        "rich cell": ("RichCellWriteRequest", ".hyperlink(", ".styled_runs(", ".mention(", ".multi_select("),
        "dropdown rule": ("DropdownRuleWriteRequest",),
        "structural insert/delete": ("InsertRowsAt", "DeleteRows"),
        "merge/tab": ("MergeCells", "UnmergeCells", "AddTab"),
    }.items():
        for tok in tokens:
            assert tok in src, (
                f"the final gate must exercise the {kind!r} write kind (missing {tok!r}) — "
                "all four rich/structural kinds run in the one ring (AC2/AC5)."
            )
    assert "dry_run(" in src and "apply(" in src, (
        "every write kind must flow through the gated engine (dry_run → apply) — never a "
        "raw client write (AC2)."
    )


def test_gate_runs_the_full_two_leg_differ():
    src = _src()
    # values leg (live used-range diff), always.
    assert "assert_surgical(" in src, (
        "the gate must run the VALUES leg (assert_surgical) per write kind (AC2)."
    )
    # style/format leg — export-based, AUTO-ON (D9): the shipped export reader + the
    # surgical style diff over guard neighbours.
    assert "SheetsExportReader" in src and "assert_style_surgical(" in src, (
        "the gate must run the STYLE/FORMAT export leg AUTO-ON (SheetsExportReader export "
        "→ assert_style_surgical) so a stray style on a neighbour reddens (AC2, D9)."
    )
    # merge leg — the live v3 merges diff (exact delta for the merge write; identical for a
    # non-merge write).
    assert "assert_merge_change(" in src and "assert_merges_identical(" in src, (
        "the gate must run the MERGE leg (assert_merge_change for the merge write, "
        "assert_merges_identical for a non-merge write) — the geometry a values read can't "
        "reconstruct (AC2)."
    )


def test_gate_asserts_destructive_safe_removed_payload():
    src = _src()
    # AC3 — a LIVE delete's apply-log carries the FULL removed payload; assert it complete.
    assert "assert_removed_payload_complete(" in src, (
        "the gate must assert the LIVE delete's apply-log removed payload is complete "
        "(assert_removed_payload_complete) — destructive-safe, reconstructable (AC3)."
    )
    assert 'structural["removed"]' in src or "structural['removed']" in src, (
        "the destructive-safe proof must read the removed payload from the delete's "
        "apply-log entry.structural['removed'] (AC3)."
    )


def test_gate_restores_byte_identical_and_closes_out_zero_orphan():
    src = _src()
    # AC4 — each round-trip restores byte-identical (re-diff) …
    assert "assert_identical(" in src, (
        "the gate must restore byte-identical and re-diff (assert_identical) — AC4."
    )
    # … then delete-in-finally (harness disposable) + the zero-orphan close-out hard gate.
    assert "H.disposable(" in src or "disposable(" in src, (
        "the gate must self-provision via the LD-112 harness disposable() (delete-in-finally)"
        " — AC4/AC6."
    )
    assert "close_out(" in src and ("raise_if_orphans" in src or "all_clean" in src), (
        "the gate must run the zero-orphan close-out and assert ZERO orphans (AC4)."
    )


def test_gate_uses_write_credentials_only():
    src = _src()
    assert "from_write_credentials" in src, (
        "the gate must build every surface from *_from_write_credentials (LARK_WRITE_APP_* "
        "— the write-only resolver) — AC6, D1."
    )
    assert "get_read_credentials" not in src, (
        "the final gate needs NO read app (the WRITE app owns the disposable it creates "
        "and exports) — it must not reference get_read_credentials (AC6, D1)."
    )


def test_gate_never_references_scratch_canary_zoo_or_external_docs():
    src = _src()
    forbidden = [
        "LARKDOCIO_CANARY_DOC", "CANARY_DOC_ENV", "canary_doc_url",
        "LARKDOCIO_BLOCKZOO_DOC", "BLOCKZOO_DOC_ENV", "blockzoo_doc_url",
        "LARKDOCIO_WRITE_SCRATCH_DOC",
        "LARKDOCIO_SCRATCH_SHEET", "SCRATCH_SHEET_ENV", "scratch_sheet_url",
        "LARKDOCIO_SCRATCH_BASE",
        "larksuite.com/sheets/", "feishu.cn/sheets/",
        "larksuite.com/docx/", "feishu.cn/docx/",
        "feishu.cn/wiki/", "larksuite.com/wiki/",
    ]
    for token in forbidden:
        assert token not in src, (
            f"the final gate must not reference {token!r} — it writes ONLY against the "
            "disposable it self-provisions; never the scratch sheet, the read canary, the "
            "zoo, the sandbox, or a real document (AC6, D7)."
        )
