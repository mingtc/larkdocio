"""LD-189 live gate — the Sheets CELL BORDER write round-trip, through ``src/``.

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it — together with every other family in one ring::

    pytest -m live_write

**Why this arm reads raw XML where its LD-188 sibling reads the shipped reader.** That is the
whole finding it exists to hold honest. A border write lands, and the exported workbook carries it
— but the shipped :class:`~larkdocio.sheets.export_reader.ExportedCell` reports ``bold`` /
``italic`` / ``fill_rgb`` / ``num_fmt`` and **no border**, so the ``--verify-style`` export leg
this write turns on physically cannot check the thing that was written. Widening the reader is
style READ, out of this issue's scope. So the plan **discloses** the gap
(``style-border-not-verifiable``) and this arm proves the write really lands by resolving the
export's own ``xl/styles.xml`` ``borders`` table itself. Both halves matter: the disclosure would
be over-cautious if the border did not land, and the border landing would be a false comfort if
the plan implied the gate had checked it.

What it proves, on **one self-provisioned disposable**:

* **``FULL_BORDER`` + ``borderColor``** on a range, read back per edge with its ARGB;
* **per-edge** values landing exactly one edge each, and **``OUTER_BORDER``** drawing the
  *range's* perimeter (a corner cell getting only its two outside edges) — the two facts a
  caller would otherwise have to guess from the value's name;
* **borders ADD**: a second per-edge write unions with the first rather than replacing it;
* **``NO_BORDER`` is the clear**, and over a subset of a bordered range it clears **only** the
  cells it names — which is also this arm's RESTORE;
* **the disclosure rides a real plan** — ``style-border-not-verifiable`` fires on the live plan
  and names the bordered ranges, while a fill-only plan in the same run does **not** carry it;
* **a border rides with LD-188's own fields** in one style and one call, and the shipped export
  leg still verifies *those* (bold + fill) as usual — the coverage the disclosure claims is real;
* **surgical**: a guard neighbour keeps no border at all.

Writes use the WRITE app only; every target is a **self-provisioned disposable** — never the
scratch sheet, never a real document; the whole disposable is deleted in ``finally`` and the
zero-orphan close-out is a hard gate.

**Word wrap is deliberately not exercised here.** It was refuted (see
:data:`~larkdocio.sheets.requests.WORD_WRAP_NOT_WRITABLE`), nothing ships, and a live arm for a
capability that does not exist would be theatre. Its evidence is the probe capture, pinned offline
by ``tests/test_sheets_border_write.py``.
"""
import json
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

import canary_support
import sheets_write_harness as H
from larkdocio.sheets.export_reader import SheetsExportReader
from larkdocio.sheets.write_apply import (
    BORDER_CLEAR,
    BatchStyleWriteRequest,
    CellStyle,
    StyleSpan,
    StyleWriteRequest,
    apply,
    dry_run,
)
from larkdocio.sheets.write_client import SheetsWriteClient

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

DOMAIN = "larksuite.com"
EXPECT_BORDER_ARGB = "FFFF0000"          # #FF0000 as the export reports it
EXPECT_FILL = "FFFFFF00"                 # #FFFF00, verified through the SHIPPED leg


def _ln(tag):
    return tag.rsplit("}", 1)[-1]


def _borders_by_ref(xlsx: bytes) -> dict:
    """``{A1 ref: {edge: {"style":…, "color": {...}}}}`` resolved off the export itself.

    The shipped reader has no border field (that is the point of this arm), so the border is read
    where it actually lives: each cell's ``s=`` index → ``cellXfs`` → ``borderId`` → the
    ``borders`` table in ``xl/styles.xml``. An **undrawn** edge is present but empty, so an edge
    set is the truthful comparison unit rather than the raw dict.
    """
    with zipfile.ZipFile(BytesIO(xlsx)) as zf:
        styles = ET.fromstring(zf.read("xl/styles.xml"))
        arc = next(n for n in zf.namelist()
                   if n.startswith("xl/worksheets/") and n.endswith(".xml"))
        sheet = ET.fromstring(zf.read(arc))
    borders = []
    for group in styles:
        if _ln(group.tag) != "borders":
            continue
        for border in group:
            rec = {}
            for edge in border:
                entry = dict(edge.attrib)
                for child in edge:
                    if _ln(child.tag) == "color":
                        entry["color"] = dict(child.attrib)
                rec[_ln(edge.tag)] = entry
            borders.append(rec)
    xfs = []
    for group in styles:
        if _ln(group.tag) != "cellXfs":
            continue
        xfs.extend(dict(xf.attrib) for xf in group)
    out = {}
    for node in sheet.iter():
        if _ln(node.tag) != "c":
            continue
        xf = xfs[int(node.attrib.get("s") or 0)] if xfs else {}
        border_id = int(xf.get("borderId") or 0)
        out[node.attrib["r"]] = borders[border_id] if border_id < len(borders) else {}
    return out


def _edges(borders, ref):
    """The edges actually DRAWN on one cell."""
    return sorted(k for k, v in (borders.get(ref) or {}).items() if v)


def _note(plan_entry, kind):
    for note in plan_entry.preview_notes:
        if note["kind"] == kind:
            return note
    return None


def test_sheets_border_write_gate_round_trip(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    gateway = H.SheetsLifecycleGateway.from_write_credentials(DOMAIN)
    writer = SheetsWriteClient.from_write_credentials(DOMAIN)
    exporter = SheetsExportReader.from_write_credentials(DOMAIN)

    tmpdir = tempfile.mkdtemp(prefix="ld189-sheets-border-gate-")
    ledger = H.Ledger(Path(tmpdir) / "run_ledger.json")

    evidence = {}
    with H.disposable(gateway, ledger, writer=writer, styler=writer) as d:
        evidence["token"] = d.token
        assert d.token, "create yielded no spreadsheet_token"
        sid = d.first_sheet_id
        evidence["sheet_id"] = sid

        # A1:B2 the OUTER_BORDER range · A3 the per-edge target · B3 the union target
        # · C1 the guard neighbour · C3 the border-rides-with-fill target.
        d.put_values(f"{sid}!A1:C3", [["a1", "b1", "guard-C1"],
                                      ["a2", "b2", "c2"],
                                      ["edge-A3", "union-B3", "combo-C3"]])

        baseline = _borders_by_ref(exporter.export_xlsx(d.token))
        for ref in ("A1", "B1", "A2", "B2", "A3", "B3", "C1", "C3"):
            assert _edges(baseline, ref) == [], (
                f"{ref} is unexpectedly pre-bordered: {baseline.get(ref)!r}")
        evidence["baseline_edges"] = {r: _edges(baseline, r)
                                      for r in ("A1", "A3", "B3", "C1", "C3")}

        # 1) OUTER_BORDER + colour over a RANGE — and the disclosure on a real plan.
        plan = dry_run([StyleWriteRequest(
            f"{sid}!A1:B2", CellStyle(border_type="OUTER_BORDER",
                                      border_color="#FF0000"))], writer, d.token)
        assert len(plan.resolved) == 1, f"the border write refused at dry-run: {plan.refusals!r}"
        disclosure = _note(plan.entries[0], "style-border-not-verifiable")
        assert disclosure is not None, (
            "a live border plan carried no style-border-not-verifiable note — the caller would "
            "believe the export leg checked the border")
        assert disclosure["border_ranges"] == [f"{sid}!A1:B2"], disclosure
        evidence["disclosure"] = {"ranges": disclosure["border_ranges"],
                                  "verified_by": disclosure["verified_by"]}
        assert apply(plan, writer).entries[0].is_applied

        # 2) A per-edge write, then a SECOND one — borders ADD rather than replace.
        assert apply(dry_run([StyleWriteRequest(f"{sid}!A3:A3",
                                                CellStyle(border_type="LEFT_BORDER"))],
                             writer, d.token), writer).entries[0].is_applied
        union = apply(dry_run([StyleWriteRequest(f"{sid}!B3:B3",
                                                 CellStyle(border_type="LEFT_BORDER"))],
                              writer, d.token), writer)
        assert union.entries[0].is_applied
        assert apply(dry_run([StyleWriteRequest(f"{sid}!B3:B3",
                                                CellStyle(border_type="TOP_BORDER"))],
                             writer, d.token), writer).entries[0].is_applied

        # 3) A border RIDING WITH LD-188's own fields, in one style — the shipped leg still
        #    verifies the bold + fill half, which is exactly the coverage the note claims.
        combo = dry_run([StyleWriteRequest(
            f"{sid}!C3:C3", CellStyle(bold=True, back_color="#FFFF00",
                                      border_type="FULL_BORDER",
                                      border_color="#FF0000"))], writer, d.token)
        assert _note(combo.entries[0], "style-border-not-verifiable") is not None
        assert _note(combo.entries[0], "style-verification-cost") is not None, (
            "the LD-188 cost note was displaced by the LD-189 one — notes must COMPOSE")
        assert apply(combo, writer).entries[0].is_applied

        # 3b) …and a FILL-ONLY plan in the same run must NOT carry the border disclosure.
        fill_only = dry_run([StyleWriteRequest(f"{sid}!A2:A2",
                                              CellStyle(back_color="#D9EAD3"))],
                            writer, d.token)
        assert _note(fill_only.entries[0], "style-border-not-verifiable") is None, (
            "a style with no border claimed a border limitation")
        assert apply(fill_only, writer).entries[0].is_applied

        # 4) Read every one of those back — borders off the raw export, fill off the shipped leg.
        after = _borders_by_ref(exporter.export_xlsx(d.token))
        evidence["after_edges"] = {r: _edges(after, r)
                                   for r in ("A1", "B1", "A2", "B2", "A3", "B3", "C1", "C3")}
        # OUTER_BORDER draws the RANGE's perimeter: each corner gets its two outside edges.
        assert _edges(after, "A1") == ["left", "top"], evidence["after_edges"]
        assert _edges(after, "B1") == ["right", "top"], evidence["after_edges"]
        assert _edges(after, "A2") == ["bottom", "left"], evidence["after_edges"]
        assert _edges(after, "B2") == ["bottom", "right"], evidence["after_edges"]
        assert after["A1"]["left"]["color"]["rgb"] == EXPECT_BORDER_ARGB, after["A1"]
        # per-edge lands exactly one edge; a second per-edge write UNIONS with the first.
        assert _edges(after, "A3") == ["left"], evidence["after_edges"]
        assert _edges(after, "B3") == ["left", "top"], (
            f"two per-edge writes did not union — borders replace after all: "
            f"{evidence['after_edges']}")
        # the combined style: the border landed AND the shipped leg sees the bold + fill.
        assert _edges(after, "C3") == ["bottom", "left", "right", "top"], (
            evidence["after_edges"])
        combo_cell = exporter.read_workbook(d.token).first_sheet.cell("C3")
        assert combo_cell.bold is True and combo_cell.fill_rgb == EXPECT_FILL, (
            f"the border rode in and broke the fields the gate CAN verify: {combo_cell!r}")
        evidence["combo_shipped_leg"] = {"bold": combo_cell.bold,
                                         "fill_rgb": combo_cell.fill_rgb}
        # surgical: the guard neighbour has no border at all.
        assert _edges(after, "C1") == [], (
            f"the guard neighbour C1 was bordered — the write was not surgical: "
            f"{after.get('C1')!r}")

        # 5) RESTORE — NO_BORDER over a SUBSET, which must clear only what it names.
        restore = apply(dry_run([BatchStyleWriteRequest([
            StyleSpan([f"{sid}!A1:B2", f"{sid}!A3:A3", f"{sid}!C3:C3"],
                      CellStyle(border_type=BORDER_CLEAR)),
        ])], writer, d.token), writer)
        assert restore.entries[0].is_applied, (
            f"the border restore refused: {restore.entries[0].to_dict()['refusal']}")
        restored = _borders_by_ref(exporter.export_xlsx(d.token))
        evidence["restored_edges"] = {r: _edges(restored, r)
                                      for r in ("A1", "B1", "A2", "B2", "A3", "B3", "C3")}
        for ref in ("A1", "B1", "A2", "B2", "A3", "C3"):
            assert _edges(restored, ref) == [], (
                f"{ref} still carries a border after NO_BORDER: {restored.get(ref)!r}")
        # …and B3, deliberately left OUT of the clear, still has its union: the clear is
        # scoped to the cells it names, which is what makes it a safe restore.
        assert _edges(restored, "B3") == ["left", "top"], (
            f"NO_BORDER over a subset cleared a cell it did not name: {restored.get('B3')!r}")
        assert exporter.read_workbook(d.token).first_sheet.cell("A3").value == "edge-A3", (
            "the border round-trip disturbed a cell VALUE")
    # 6) delete-in-finally fired on with-exit (the whole disposable is removed).

    report = H.close_out(gateway, ledger)
    report.raise_if_orphans()
    assert report.all_clean, f"close-out found orphans: {report.orphans!r}"

    with capsys.disabled():
        print(
            "\n[LD-189 border-write gate] "
            f"token={evidence['token']} sheet_id={evidence['sheet_id']} "
            f"disclosure={json.dumps(evidence.get('disclosure'))} "
            f"baseline={json.dumps(evidence['baseline_edges'])} "
            f"after={json.dumps(evidence['after_edges'])} "
            f"combo_shipped_leg={json.dumps(evidence.get('combo_shipped_leg'))} "
            f"restored={json.dumps(evidence['restored_edges'])} "
            f"orphans={report.orphans!r}"
        )
