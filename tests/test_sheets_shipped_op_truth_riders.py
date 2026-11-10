"""LD-190 — three shipped-op truth riders, each pinned against its own live evidence.

**(a) The merge family's variants are FENCED, and the reason is a MIS-DISCLOSURE.**
``MergeCells.merge_type`` was a free ``str``, so ``MERGE_ROWS`` / ``MERGE_COLUMNS`` were
expressible on a **destructive** op whose ``loss_preview`` is written for ``MERGE_ALL``. The
probe (``tests/captures/sheets-merge-variant-probe/captures/01-merge-variant-characterization.json``)
answers AC1 with values, not opinion:

* ``MERGE_ROWS`` on a 2x2 produced **two** merge regions — one per row — and **both** row-leading
  cells kept their values, while the shipped preview named ONE anchor and reported the second
  row's leader as LOST. So the preview **over-reported the loss** on a destructive write.
* ``MERGE_COLUMNS`` is the same fault transposed (one region per column, every column's top cell
  kept).
* The endpoint is **strict** — a nonsense ``mergeType``, a lower-case ``merge_rows`` and a
  whitespace-padded ``" MERGE_ROWS "`` each answered ``90204 invalid mergeType`` and landed
  nothing — so a ``code 0`` on the two variants means they really did land, and the
  mis-disclosure was reachable rather than theoretical.

AC2 therefore **fences** (maintainer's recommendation): a typed construction refusal, zero API calls,
naming the one gate-covered variant. These tests hold both halves — the characterization that
justifies the fence, and the fence itself.

**(b) The dropdown colors write/read asymmetry is DISCLOSED** where a consumer looks, and the
doc's claim that we do not read them back is held against ``src/`` itself.

**(c) The numeric read-back trap has a documented comparator.** Re-established live
(``.../captures/02-numeric-read-back.json``): every whole-valued float comes back as an
``int`` — ``18.0`` → ``18``, ``0.0`` → ``0``, ``-3.0`` → ``-3``, ``1e6`` → ``1000000`` — so a
string comparison phantom-diffs while a value comparison is exact.
"""
import json
import pathlib

import pytest

from larkdocio import capabilities
from larkdocio.sheets import values_equivalent, value_differences
from larkdocio.sheets.rich_encode import DROPDOWN_COLORS_NOT_READ_BACK
from larkdocio.sheets.requests import (
    MERGE_ALL,
    MERGE_TYPE_REFUSAL_BODY,
    MERGE_TYPE_REFUSAL_CODE,
    MERGE_VARIANTS_NOT_GATE_COVERED,
    MERGE_VARIANTS_REFUSED,
    SUPPORTED_MERGE_TYPES,
    MergeCells,
    MergeTypeError,
)
from larkdocio.sheets.verify import NUMERIC_READ_BACK_NORMALIZED

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PROBE = json.loads(
    (REPO_ROOT / "tests" / "captures" / "sheets-merge-variant-probe" / "captures"
     / "01-merge-variant-characterization.json").read_text(encoding="utf-8"))
_NUMERIC = json.loads(
    (REPO_ROOT / "tests" / "captures" / "sheets-merge-variant-probe" / "captures"
     / "02-numeric-read-back.json").read_text(encoding="utf-8"))
SID = "154e99"


def _step(prefix):
    return next(s for s in _PROBE["steps"] if s["label"].startswith(prefix))


def _regions(step):
    """The merge regions the probe's arm ADDED (the geometry re-read is cumulative)."""
    return [(m["start_row_index"], m["end_row_index"],
             m["start_column_index"], m["end_column_index"])
            for m in step["merges_after"] or []]


# --------------------------------------------------------------------------- #
# AC1 — the characterization: what the variants DO, and how the shipped model  #
#       mis-described it. These tests read the capture; they invent nothing.   #
# --------------------------------------------------------------------------- #

def test_ac1_the_probe_ran_on_a_self_provisioned_disposable_and_destroyed_it():
    assert _PROBE["deleted"] is True
    assert _PROBE["gone_confirmed"] is True


def test_ac1_the_control_arm_proves_an_unknown_merge_type_is_REFUSED_not_ignored():
    """Before any ``code 0`` means anything: a nonsense ``mergeType`` is rejected, so this
    endpoint does NOT silently ignore the field (unlike the style endpoint of LD-189)."""
    control = _step("X0 control")
    assert control["raised"] is not None
    assert str(MERGE_TYPE_REFUSAL_CODE) in control["raised"]
    assert MERGE_TYPE_REFUSAL_BODY in control["raised"]
    assert control["merges_after"] == []          # and nothing landed


def test_ac1_merge_rows_makes_ONE_MERGE_PER_ROW_and_keeps_every_row_leader():
    """The reality: a 2x2 ``MERGE_ROWS`` produced TWO regions, D1 and D2 both survived."""
    arm = _step("R1 MERGE_ROWS on a 2x2")
    assert arm["raised"] is None                              # it really landed
    assert _regions(arm) == [(0, 0, 3, 4), (1, 1, 3, 4)]      # one region PER ROW
    assert arm["values_after"] == [["D1", None], ["D2", None]]


def test_ac1_merge_columns_makes_ONE_MERGE_PER_COLUMN_and_keeps_every_column_top():
    arm = _step("C1 MERGE_COLUMNS on a 2x2")
    assert arm["raised"] is None
    added = [r for r in _regions(arm) if r not in _regions(_step("R1 MERGE_ROWS on a 2x2"))]
    assert added == [(0, 1, 6, 6), (0, 1, 7, 7)]              # one region PER COLUMN
    assert arm["values_after"] == [["G1", "H1"], [None, None]]


@pytest.mark.parametrize("prefix,survivor", [
    ("R1 MERGE_ROWS on a 2x2", "D2"),
    ("C1 MERGE_COLUMNS on a 2x2", "H1"),
])
def test_ac1_the_shipped_loss_preview_MIS_DISCLOSED_the_destructive_write(prefix, survivor):
    """**The finding that decides AC2.** The shipped preview flagged a cell as LOST that the
    live write KEPT — an over-report of data loss on a destructive op, for both variants."""
    arm = _step(prefix)
    preview = arm["shipped_loss_preview"]
    claimed_lost = [c["ref"] for c in preview["lost_values"]]
    assert survivor in claimed_lost, "the preview did not claim this cell was lost"
    survived = [v for row in arm["values_after"] for v in row if v is not None]
    assert survivor in survived, "the cell the preview called LOST is still there"
    # and the single-rectangle region the preview reports is not the geometry that landed
    assert len(_regions(arm)) > 1


@pytest.mark.parametrize("prefix", [
    "R2 MERGE_ROWS on a 1xN single row",
    "C2 MERGE_COLUMNS on an Nx1 single column",
])
def test_ac1_on_a_single_line_range_the_variant_is_indistinguishable_from_merge_all(prefix):
    """The honest other half: where the range has one row (ROWS) or one column (COLUMNS) the
    variant IS ``MERGE_ALL`` and the shipped preview was right — which is exactly why the fence
    names ``MERGE_ALL`` as the way to express that case rather than pretending it is unreachable."""
    arm = _step(prefix)
    assert arm["raised"] is None
    lost = [c["ref"] for c in arm["shipped_loss_preview"]["lost_values"]]
    survived = [v for row in arm["values_after"] for v in row if v is not None]
    assert not (set(lost) & set(survived))       # nothing the preview called lost survived


def test_ac1_a_variant_over_an_existing_merge_landed_rather_than_refusing():
    """The overlap arm: ``MERGE_ROWS`` over an existing ``MERGE_ALL`` region was ACCEPTED, so
    the unverified path could also reshape geometry a plan had already reasoned about."""
    arm = _step("O2 MERGE_ROWS OVER the existing merge")
    assert arm["raised"] is None
    assert arm["values_after"] == [["E8", None], ["E9", None]]


@pytest.mark.parametrize("prefix,intact", [
    ("V1 lower-case", [["H8", "I8"]]),
    ("V2 whitespace-padded", [["H10", "I10"]]),
])
def test_ac1_lark_itself_refuses_a_lower_case_or_padded_merge_type(prefix, intact):
    """So refusing those spellings client-side pre-empts Lark's own verbatim ``90204`` rather
    than inventing a rule — and nothing is silently repaired for the caller."""
    arm = _step(prefix)
    assert arm["raised"] is not None
    assert MERGE_TYPE_REFUSAL_BODY in arm["raised"]
    assert arm["values_after"] == intact       # nothing merged, nothing lost


# --------------------------------------------------------------------------- #
# AC2 — the FENCE: a typed construction refusal, zero API calls.               #
# --------------------------------------------------------------------------- #

def test_ac2_merge_all_is_the_only_supported_merge_type():
    assert SUPPORTED_MERGE_TYPES == frozenset({MERGE_ALL})
    assert MERGE_ALL == "MERGE_ALL"
    assert MERGE_VARIANTS_REFUSED == ("MERGE_ROWS", "MERGE_COLUMNS")


def test_ac2_merge_all_still_constructs_and_previews_exactly_as_before():
    """The fence must not touch the shipped, correct path (issue § Out of Scope)."""
    req = MergeCells(f"{SID}!A5:C5")
    assert req.merge_type == MERGE_ALL
    assert req.descriptor()["merge_type"] == MERGE_ALL
    preview = req.loss_preview([["a5", "b5", "c5"]])
    assert preview["anchor"] == {"ref": "A5", "value": "a5"}
    assert [c["ref"] for c in preview["lost_values"]] == ["B5", "C5"]
    assert MergeCells(f"{SID}!A5:C5", merge_type="MERGE_ALL") == req


@pytest.mark.parametrize("variant", ["MERGE_ROWS", "MERGE_COLUMNS"])
def test_ac2_both_variants_are_refused_at_construction(variant):
    with pytest.raises(MergeTypeError) as exc:
        MergeCells(f"{SID}!A1:B2", merge_type=variant)
    message = str(exc.value)
    assert variant in message
    assert MERGE_ALL in message                        # names the supported variant
    assert "tests/captures/sheets-merge-variant-probe" in message  # names its evidence


@pytest.mark.parametrize("spelling", [
    "merge_rows", " MERGE_ROWS ", "merge_all", "MERGE_ALL ", "Merge_All",
    "MERGE_NOTHING_AT_ALL", "", None, 0, ["MERGE_ALL"],
])
def test_ac2_a_variant_spelling_case_or_type_is_refused_too(spelling):
    """Case and whitespace are refused rather than repaired — Lark refuses them itself
    (``90204 invalid mergeType``, probed), so normalizing them here would hide the strictness."""
    with pytest.raises(MergeTypeError):
        MergeCells(f"{SID}!A1:B2", merge_type=spelling)


def test_ac2_the_refusal_is_both_a_config_error_and_a_value_error():
    """The house standard for a construction refusal (``StyleError`` / ``DimensionPropertyError``)."""
    from larkdocio.errors import LarkConfigError

    assert issubclass(MergeTypeError, LarkConfigError)
    assert issubclass(MergeTypeError, ValueError)


def test_ac2_the_refusal_costs_zero_api_calls():
    """Nothing is constructed, so nothing can be dispatched — the refusal is pre-transport."""
    import larkdocio.sheets.write_client as wc

    calls = []
    original = wc.SheetsWriteClient.merge_cells
    try:
        wc.SheetsWriteClient.merge_cells = lambda *a, **k: calls.append(a)
        with pytest.raises(MergeTypeError):
            MergeCells(f"{SID}!A1:B2", merge_type="MERGE_ROWS")
    finally:
        wc.SheetsWriteClient.merge_cells = original
    assert calls == []


def test_ac2_the_loud_statement_carries_the_reason_the_evidence_and_the_repair():
    text = MERGE_VARIANTS_NOT_GATE_COVERED
    for word in ("MERGE_ROWS", "MERGE_COLUMNS", "MERGE_ALL",
                 "tests/captures/sheets-merge-variant-probe"):
        assert word in text
    assert "per row" in text and "per column" in text        # the real geometry
    assert "lost" in text.lower()                            # the mis-disclosure
    assert str(MERGE_TYPE_REFUSAL_CODE) in text and MERGE_TYPE_REFUSAL_BODY in text


def test_ac2_no_merge_type_other_than_merge_all_can_reach_the_wire_builder():
    """Whatever a caller does, a dispatched merge descriptor carries ``MERGE_ALL``."""
    import itertools

    from larkdocio.sheets.requests import UnmergeCells

    for a1 in ("154e99!A1:B2", "154e99!A1:A3", "154e99!C1:E1"):
        assert MergeCells(a1).descriptor()["merge_type"] == MERGE_ALL
    assert "merge_type" not in UnmergeCells(f"{SID}!A1:B2").descriptor()
    assert not list(itertools.filterfalse(
        lambda t: t == MERGE_ALL, [MergeCells(f"{SID}!A1:B2").merge_type]))


def test_ac2_the_transport_docstring_names_the_fence_so_a_raw_caller_is_not_misled():
    """The client stays a faithful transport (house layering), so its docstring must say
    where the refusal lives and that a raw call gets NO loss preview."""
    from larkdocio.sheets.write_client import SheetsWriteClient

    doc = SheetsWriteClient.merge_cells.__doc__
    assert "MERGE_ROWS" in doc and "MERGE_COLUMNS" in doc
    assert "MergeCells" in doc
    assert "no loss preview" in doc.lower()


def test_ac6_capabilities_projects_the_merge_types_off_the_supported_set():
    """So "which merge types can I use?" is answered by the code, not by a hand-kept list."""
    merge_op = next(op for op in capabilities(full=True)["surfaces"]["sheets-write"]["operations"]
                    if op["name"] == "merge")
    assert merge_op["merge_types"] == sorted(SUPPORTED_MERGE_TYPES)
    assert merge_op["merge_types_refused"] == list(MERGE_VARIANTS_REFUSED)
    # and no OTHER op carries the merge keys
    others = [op for op in capabilities(full=True)["surfaces"]["sheets-write"]["operations"]
              if op["name"] != "merge"]
    assert not [op for op in others if "merge_types" in op]


# --------------------------------------------------------------------------- #
# AC3 / AC4 — (b) the dropdown colors write/read asymmetry, disclosed.          #
# --------------------------------------------------------------------------- #

def test_ac3_the_asymmetry_statement_names_both_field_names_and_the_consequence():
    text = DROPDOWN_COLORS_NOT_READ_BACK
    assert "options.colors" in text
    assert "colorValueMap" in text
    assert "not" in text.lower()
    assert "highlightValidData" in text


def test_ac3_both_consumer_documents_carry_the_asymmetry():
    guide = (REPO_ROOT / "src" / "larkdocio" / "GUIDE.md").read_text(encoding="utf-8")
    sheets_md = (REPO_ROOT / "SHEETS.md").read_text(encoding="utf-8")
    for text in (guide, sheets_md):
        assert "colorValueMap" in text
        assert DROPDOWN_COLORS_NOT_READ_BACK in text


def test_ac4_the_deferred_read_is_held_TRUE_by_src_itself():
    """The doc says larkdocio does not read the rule back. That claim is checked against the
    code by **tokenizing** it: ``colorValueMap`` may appear only in prose — a string constant or
    a comment — never as a name, attribute or key the library actually reads. The moment a read
    ships, this reddens and the doc must change with it."""
    import io
    import token as tok
    import tokenize

    src = REPO_ROOT / "src"
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "colorValueMap" not in text:
            continue
        for item in tokenize.generate_tokens(io.StringIO(text).readline):
            if "colorValueMap" not in item.string:
                continue
            assert item.type in (tok.STRING, tok.COMMENT), (
                f"{path.relative_to(src)}:{item.start[0]} reads colorValueMap as "
                f"{tok.tok_name[item.type]}: {item.line!r}")


def test_ac4_capabilities_records_the_dropdown_field_that_cannot_be_read_back():
    dropdown = next(op for op in capabilities(full=True)["surfaces"]["sheets-write"]["operations"]
                    if op["name"] == "dropdown")
    assert dropdown["fields_not_read_back"] == ["options.colors"]


# --------------------------------------------------------------------------- #
# AC5 — (c) the numeric read-back trap and the comparator that survives it.     #
# --------------------------------------------------------------------------- #

def test_ac5_the_probe_re_established_f19_live_on_a_destroyed_disposable():
    assert _NUMERIC["deleted"] is True and _NUMERIC["gone_confirmed"] is True
    f19 = next(a for a in _NUMERIC["arms"] if a["written"] == 18.0)
    assert f19["written_type"] == "float" and f19["read_back_type"] == "int"
    assert f19["read_back"] == 18
    assert f19["string_equal"] is False and f19["value_equal"] is True


@pytest.mark.parametrize("written,read_back", [
    (18.0, 18), (0.0, 0), (-3.0, -3), (1e6, 1000000), (2.5 * 4, 10),
])
def test_ac5_a_whole_valued_float_is_string_UNEQUAL_and_method_EQUAL(written, read_back):
    """**Both halves, on every value the amplifier names.** The trap (string comparison) and
    the fix (the documented comparator) are asserted on the same pair."""
    assert str(written) != str(read_back)                       # THE TRAP
    assert values_equivalent([[written]], [[read_back]])        # THE FIX
    assert value_differences([[written]], [[read_back]]) == []


def test_ac5_every_probed_arm_agrees_with_the_comparator():
    """The comparator is held against the live capture rather than against hand-picked pairs."""
    for arm in _NUMERIC["arms"]:
        assert values_equivalent([[arm["written"]]], [[arm["read_back"]]]), arm["label"]


def test_ac5_a_rendered_or_json_comparison_is_the_trap_the_guidance_names():
    """The phantom diff a consumer actually hits: the reader RENDERS ``18.0`` as ``"18.0"`` and
    the read-back as ``"18"``, so comparing Markdown (or ``json.dumps``) reports a change."""
    from larkdocio.sheets import render_cell

    assert render_cell(18.0) != render_cell(18)
    assert json.dumps([[18.0]]) != json.dumps([[18]])
    assert values_equivalent([[18.0]], [[18]])


def test_ac5_the_comparator_is_typed_and_does_not_launder_real_differences():
    """A tolerance would hide real drift; a *typed* comparison keeps every real difference
    visible — a text ``"18.0"`` is NOT the number 18, a bool is not 1, and 18.01 is not 18."""
    assert not values_equivalent([["18.0"]], [[18]])
    assert not values_equivalent([[True]], [[1]])
    assert not values_equivalent([[18.01]], [[18]])
    assert not values_equivalent([["a", "b"]], [["a", "c"]])


def test_ac5_an_empty_cell_reads_back_as_null_or_a_shorter_row_and_both_are_equivalent():
    """The other read-back normalization a self-check trips over: an empty cell comes back as
    ``None`` and a trailing empty cell may not come back at all."""
    assert values_equivalent([["a", ""]], [["a", None]])
    assert values_equivalent([["a", None]], [["a"]])
    assert values_equivalent([["a"], []], [["a"]])
    assert not values_equivalent([["a", "b"]], [["a"]])


def test_ac5_value_differences_reports_the_a1_ref_of_every_real_difference():
    diffs = value_differences([["a", 18.0, 1], ["x", "y", "z"]],
                              [["a", 18, 2], ["x", "Y", "z"]],
                              origin="B2")
    assert [d["ref"] for d in diffs] == ["D2", "C3"]
    assert diffs[0] == {"ref": "D2", "written": 1, "read_back": 2}


def test_ac5_the_loud_statement_names_the_normalization_the_trap_and_the_fix():
    text = NUMERIC_READ_BACK_NORMALIZED
    assert "18.0" in text and "18" in text
    assert "string" in text.lower()
    assert "values_equivalent" in text
    assert "tests/captures/sheets-merge-variant-probe" in text


def test_ac5_the_guidance_ships_in_the_guide_and_is_discoverable_from_sheets_md():
    guide = (REPO_ROOT / "src" / "larkdocio" / "GUIDE.md").read_text(encoding="utf-8")
    sheets_md = (REPO_ROOT / "SHEETS.md").read_text(encoding="utf-8")
    assert NUMERIC_READ_BACK_NORMALIZED in guide
    assert "values_equivalent" in guide and "values_equivalent" in sheets_md
    assert "compare values, not their string forms" in guide


# --------------------------------------------------------------------------- #
# AC6 — the truth rows + the rider ledger.                                     #
# --------------------------------------------------------------------------- #

def test_ac6_sheets_md_merge_row_records_the_per_variant_reality_and_the_refusal():
    sheets_md = (REPO_ROOT / "SHEETS.md").read_text(encoding="utf-8")
    merge_row = next(ln for ln in sheets_md.splitlines()
                     if ln.startswith("| merge cells |"))
    for word in ("MERGE_ROWS", "MERGE_COLUMNS", "refused", "MergeTypeError",
                 "01-merge-variant-characterization.json"):
        assert word in merge_row, word


def test_ac6_sheets_md_data_validation_row_records_the_colors_asymmetry():
    sheets_md = (REPO_ROOT / "SHEETS.md").read_text(encoding="utf-8")
    row = next(ln for ln in sheets_md.splitlines()
               if ln.startswith("| data-validation (dropdown rules) |"))
    assert "colorValueMap" in row
    assert "`uncaptured`" in row          # the read is still deliberately deferred


def test_ac6_the_public_facade_exports_the_comparator_and_the_refusal():
    import larkdocio.sheets as sheets

    for name in ("values_equivalent", "value_differences", "MergeTypeError",
                 "SUPPORTED_MERGE_TYPES"):
        assert name in sheets.__all__, name
        assert getattr(sheets, name) is not None
