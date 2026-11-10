"""Golden-file regression for the Sheets-table Markdown render (LD-117).

Two deliberate golden sets over ONE fixture (``tests/fixtures/sheets/*.values.json``):

* **DEFAULT** (``*.default.expected.md``) — the values-only render (no fidelity). Pins
  gain **(b)**: a multi-select cell's comma-joined READ form (``"Red,Green"``) renders
  as an ordered ``", "``-joined set (``"Red, Green"``) in the **default** MD, while a
  currency FormattedValue (``"$1,234.56"``) is preserved byte-identical (the digit-flank
  guard) and a single-selection dropdown (``"Blue"``) is unchanged. **This is the ONE
  deliberate default-output change** (D5b) — the prior render was ``"Red,Green"``.

* **FLAGGED FIDELITY** (``*.fidelity.expected.md``) — the same fixture rendered with the
  opt-in export-only cell fidelity (an :class:`ExportedSheet`). Pins gain **(a)**:
  whole-cell (format-level) bold/italic — the emphasis set on the CELL, which the values
  API does not carry (run-level emphasis does, and renders with the flag OFF; LD-154 /
  F18) — renders as MD emphasis via the
  shared serializer, including the **combined** gain (a)+(b) cell — a bold+italic
  multi-select renders ``**_Red, Green_**``.

The DEFAULT golden is what a real values read produces; the FLAGGED golden requires the
opt-in ``--fidelity-read-sheets`` export. Regenerate an intentional change with::

    pytest tests/test_sheets_golden.py --update-golden
    # or  LARKDOCIO_UPDATE_GOLDEN=1 pytest tests/test_sheets_golden.py

and review the diff — that diff IS the deliberate spec-change record (AC3). **docx
goldens are untouched** (this render path is sheets-only — D6).
"""
import json
from pathlib import Path

import pytest

from larkdocio.sheets.export_reader import ExportedCell, ExportedSheet
from larkdocio.sheets.extent import UsedRange
from larkdocio.sheets.models import Merge, SheetTab
from larkdocio.sheets.table import render_spreadsheet

# LD-370 — CONFORMANCE-tier: the Sheets-table Markdown render is consumer-observable output, byte-pinned against a real values payload.
# See process/doctrine/conformance-tier.md (a lens, not a gate).
pytestmark = pytest.mark.conformance

_SHEETS_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sheets"


def _load(name):
    return json.loads((_SHEETS_FIXTURES / f"{name}.values.json").read_text(encoding="utf-8"))


def _tab_and_range(spec):
    merges = tuple(
        Merge(m["start_row"], m["end_row"], m["start_col"], m["end_col"])
        for m in spec.get("merges", [])
    )
    tab = SheetTab(
        sheet_id=spec["sheet_id"],
        title=spec["title"],
        index=0,
        row_count=len(spec["values"]),
        column_count=max((len(r) for r in spec["values"]), default=0),
        merges=merges,
    )
    used_range = UsedRange.from_tab_values(tab, spec["values"])
    return tab, used_range


def _fidelity_sheet(spec):
    cells = {
        ref: ExportedCell(ref=ref, value=None,
                          bold=bool(f.get("bold")), italic=bool(f.get("italic")))
        for ref, f in spec.get("fidelity", {}).items()
    }
    return ExportedSheet(name=spec["title"], cells=cells)


def _assert_golden(name, actual, update_golden):
    expected_path = _SHEETS_FIXTURES / f"{name}.expected.md"
    if update_golden:
        expected_path.write_text(actual, encoding="utf-8")
        pytest.skip(f"updated golden for {name}")
    assert expected_path.exists(), (
        f"Missing golden {expected_path.name}. Run with --update-golden to create it."
    )
    assert actual == expected_path.read_text(encoding="utf-8"), f"drift for '{name}'"


def test_sheets_table_default_golden_gain_b(update_golden):
    # gain (b): multi-select "Red,Green" → "Red, Green"; currency/single-select intact.
    spec = _load("fidelity_gains")
    tab, ur = _tab_and_range(spec)
    actual = render_spreadsheet([(tab, ur)])
    _assert_golden("fidelity_gains.default", actual, update_golden)


def test_sheets_table_fidelity_golden_gain_a(update_golden):
    # gain (a): export-only cell bold/italic → MD emphasis (opt-in), incl. the
    # combined bold+italic multi-select cell.
    spec = _load("fidelity_gains")
    tab, ur = _tab_and_range(spec)
    fidelity = {tab.sheet_id: _fidelity_sheet(spec)}
    actual = render_spreadsheet([(tab, ur)], fidelity=fidelity)
    _assert_golden("fidelity_gains.fidelity", actual, update_golden)


def test_default_and_fidelity_goldens_differ_only_by_emphasis():
    # The two golden sets share the same values; the ONLY difference is the opt-in
    # emphasis markers — proving fidelity adds emphasis and changes nothing else.
    default = (_SHEETS_FIXTURES / "fidelity_gains.default.expected.md").read_text(encoding="utf-8")
    fidelity = (_SHEETS_FIXTURES / "fidelity_gains.fidelity.expected.md").read_text(encoding="utf-8")
    assert default != fidelity
    # Stripping emphasis markers from the flagged golden recovers the default one.
    assert fidelity.replace("**", "").replace("_", "") == default


def test_gain_b_multiselect_default_output_changed():
    # Lock the DELIBERATE gain-(b) default-output change: the multi-select cell reads
    # "Red, Green" (spaced), NOT the prior "Red,Green".
    default = (_SHEETS_FIXTURES / "fidelity_gains.default.expected.md").read_text(encoding="utf-8")
    assert "Red, Green" in default
    assert "Red,Green" not in default
    # And a currency FormattedValue is preserved byte-identical (never "$1, 234.56").
    assert "$1,234.56" in default
