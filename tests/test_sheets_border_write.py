"""LD-189 — cell BORDERS (shipped) and WORD-WRAP (refuted), both characterized live first.

**The two verdicts this file pins, per field, because they landed differently.**

* **BORDERS — SHIPPED.** ``borderType`` / ``borderColor`` are real fields of the SAME
  ``appendStyle`` / ``styles_batch_update`` payload LD-188 already writes, so they ride that
  family: no new request type, no new endpoint, no new ``WriteOpKind``. Characterized live
  (``tests/captures/sheets-border-wrap-probe/``, two disposables, both deleted and gone-confirmed):
  the eight accepted values, per-edge geometry, additivity, ``NO_BORDER`` as the clear, and the
  two verbatim refusals (``90204 invalid borderType`` / ``90204 invalid borderColor``).
* **WORD-WRAP — NOT SUPPORTED.** Nine candidate field names, every one answered ``code: 0``
  ``"success"`` with ``updatedCells: 1`` **and a revision bump**, and every one landed nothing.

**Why the wrap verdict is trustworthy, and this is the whole methodological point.** A ``code: 0``
from this endpoint means **nothing on its own**: the probe's control arm sent a deliberately
nonsense field (``{"larkdocioNonsenseFieldXyz": true}``) with no known field beside it, and got
``code: 0 success``, ``updatedCells: 1``, ``revision`` bumped — while the exported cell stayed
completely unstyled. So "accepted" had to be upgraded to "landed" by read-back, and the wrap
candidates are **indistinguishable from the nonsense control** on both counts. The distinguishing
arm removes the last doubt: ``{"hAlign": 0, "wrap": true}`` in ONE request landed the ``hAlign``
(the export shows ``horizontal="left"``) and **not** the wrap — so the export demonstrably does
report alignment attributes, and ``wrapText`` is absent because nothing set it, not because the
reader is blind to it.

**The awkward middle case fires for borders (AC3), and is disclosed rather than hidden.** The
write lands and the exported bytes carry it — but the shipped
:class:`~larkdocio.sheets.export_reader.ExportedCell` surfaces ``bold`` / ``italic`` /
``fill_rgb`` / ``num_fmt`` and **no border**, so the ``--verify-style`` export leg cannot check a
border. Style READ is out of this issue's scope, so the leg is not widened; instead every plan
entry carrying a border says so (``style-border-not-verifiable``). The tests below derive that
disclosure from ``ExportedCell``'s own fields, so it cannot become a lie by a later reader change.
"""
import json
from dataclasses import fields as dataclass_fields

import pytest

from guard_kit import REPO_ROOT, md_table_cells
from larkdocio.capabilities import capabilities
from larkdocio.sheets import ops as sheets_ops
from larkdocio.sheets.export_reader import ExportedCell
from larkdocio.sheets.write_apply import (
    BORDER_CLEAR,
    BORDER_COLOR_REFUSAL_BODY,
    BORDER_REFUSAL_CODE,
    BORDER_TYPES,
    BORDER_TYPE_REFUSAL_BODY,
    STYLE_LEG_OP_KINDS,
    WORD_WRAP_NOT_WRITABLE,
    WORD_WRAP_PROBED_FIELDS,
    BatchStyleWriteRequest,
    CellStyle,
    StyleError,
    StyleSpan,
    StyleWriteRequest,
    WriteOpKind,
    dry_run,
    requires_style_leg,
)

from test_sheets_style_write import FakeStyleGateway, SID, TOKEN
from test_sheets_write_client import _client
from write_harness import StubOpener
import private_tree  # noqa: E402  (LD-685)

_CAPTURES = REPO_ROOT / "tests" / "captures" / "sheets-border-wrap-probe" / "captures"
_PROBE = json.loads((_CAPTURES / "01-border-wrap-characterization.json")
                    .read_text(encoding="utf-8"))
_SEMANTICS = json.loads((_CAPTURES / "02-border-semantics.json").read_text(encoding="utf-8"))
_PROBE_SID = _PROBE["first_sheet_id"]


def _step(needle):
    for step in _PROBE["steps"]:
        if needle in step["label"]:
            return step
    raise AssertionError(f"no probe step labelled {needle!r} in the capture")


def _probe_style(needle):
    """The ``style`` dict one probe arm actually put on the wire."""
    return _step(needle)["request_body"]["appendStyle"]["style"]


def _raw(ref):
    """One exported cell's resolved border/alignment, off the probe's raw-XML read."""
    return _PROBE["export"]["raw_border_and_alignment"][ref]


def _edges(ref):
    return sorted(k for k, v in _raw(ref)["border"].items() if v)


# --------------------------------------------------------------------------- #
# AC1 — the probe itself: recorded, on a disposable, with zero orphans.        #
# --------------------------------------------------------------------------- #

def test_ac1_both_probe_rounds_ran_on_deleted_gone_confirmed_disposables():
    """Every live fact below came off a self-provisioned spreadsheet that no longer exists."""
    for capture in (_PROBE, _SEMANTICS):
        assert capture["deleted"] is True
        assert capture["gone_confirmed"] is True
        assert capture["spreadsheet_token"]


def test_ac1_the_control_arm_proves_a_code_0_alone_means_nothing():
    """THE LOAD-BEARING CONTROL: a deliberately nonsense field answers success, bumps the
    revision, reports ``updatedCells: 1`` — and lands nothing. Every other ``code 0`` in this
    file is only meaningful because this arm ran."""
    alone = _step("X0b control")
    assert alone["code"] == 0 and alone["msg"] == "success"
    assert alone["response"]["data"]["updates"]["updatedCells"] == 1
    assert alone["response"]["data"]["updates"]["revision"] == 3
    assert _raw("H2")["s"] == 0                      # nothing landed on the cell
    assert _edges("H2") == []
    # and alongside a known-good field, the nonsense is simply ignored: the bold lands.
    both = _step("X0a control")
    assert both["code"] == 0
    assert _raw("H1")["s"] != 0


# --------------------------------------------------------------------------- #
# AC5 — the PER-FIELD verdict, asserted rather than narrated.                  #
# --------------------------------------------------------------------------- #

def test_ac5_border_verdict_is_shipped_and_wrap_verdict_is_not_supported():
    """Borders are expressible on the typed style; no wrap field exists anywhere on it."""
    names = {f.name for f in dataclass_fields(CellStyle)}
    assert {"border_type", "border_color"} <= names
    assert not [n for n in names if "wrap" in n.lower()], (
        "a wrap knob must NOT ship: every candidate field was refuted live")


# --------------------------------------------------------------------------- #
# AC2 — the confirmed fields ride LD-188's request family, byte-exact.         #
# --------------------------------------------------------------------------- #

def test_ac2_border_type_wire_is_byte_exact_against_the_probe_arm():
    assert CellStyle(border_type="FULL_BORDER").wire() == _probe_style(
        "A1 borderType FULL_BORDER (the documented candidate name)")


def test_ac2_border_type_and_color_wire_is_byte_exact_against_the_probe_arm():
    assert CellStyle(border_type="FULL_BORDER", border_color="#FF0000").wire() == _probe_style(
        "A2 borderType FULL_BORDER + borderColor #FF0000")


def test_ac2_border_rides_with_the_ld188_fields_in_one_style_byte_exact():
    """The G4 arm: bold + fill + border + border colour in a SINGLE style payload."""
    assert CellStyle(bold=True, back_color="#FFFF00",
                     border_type="FULL_BORDER", border_color="#FF0000").wire() == _probe_style(
        "G4 combined: bold + backColor + FULL_BORDER")


def test_ac2_every_probed_accepted_border_type_is_a_member_and_the_set_is_closed():
    accepted = {_probe_style(label)["borderType"] for label in (
        "A1 borderType FULL_BORDER (the documented candidate name)",
        "A4 single edge LEFT_BORDER", "A5 single edge RIGHT_BORDER",
        "A6 single edge TOP_BORDER", "A7 single edge BOTTOM_BORDER",
        "B2:C3 OUTER_BORDER", "B4:C5 INNER_BORDER",
        "D2 CLEAR attempt — borderType NO_BORDER",
    )}
    assert accepted <= BORDER_TYPES
    assert BORDER_TYPES == accepted, "the set is exactly what the probe accepted — no invention"
    for value in accepted:
        assert CellStyle(border_type=value).wire()["borderType"] == value


def test_ac2_put_style_sends_the_captured_method_path_and_body_for_a_border():
    """Through the real client + a stub transport: the border write is the SAME endpoint."""
    opener = StubOpener([{"code": 0, "data": {"updates": {"revision": 2}}}])
    client = _client(opener)
    request = StyleWriteRequest(f"{SID}!A2:A2", CellStyle(border_type="FULL_BORDER"))
    client.put_style(TOKEN, request.a1_range, request.style.wire())
    sent = opener.requests[-1]
    captured = _step("A1 borderType FULL_BORDER (the documented candidate name)")
    assert sent["method"] == captured["method"] == "PUT"
    assert sent["url"].endswith(f"/sheets/v2/spreadsheets/{TOKEN}/style")
    assert captured["path"].endswith("/style")
    assert sent["body"] == {
        "appendStyle": {"range": f"{SID}!A2:A2", "style": {"borderType": "FULL_BORDER"}}}


def test_ac2_batch_style_carries_border_type_byte_exact_against_the_capture():
    captured = _step("G2/G3 batch")["request_body"]["data"]
    batch = BatchStyleWriteRequest([
        StyleSpan([f"{_PROBE_SID}!G2:G2"], CellStyle(border_type="FULL_BORDER")),
        StyleSpan([f"{_PROBE_SID}!G3:G3"],
                  CellStyle(border_type="OUTER_BORDER", border_color="#0000FF")),
    ])
    assert batch.wire_data() == captured


def test_ac2_a_border_is_no_new_op_kind_and_the_leg_matrix_is_unchanged():
    """A border is VISUAL — ``WriteOpKind.STYLE``, already in ``STYLE_LEG_OP_KINDS``."""
    assert CellStyle(border_type="FULL_BORDER").op_kinds == (WriteOpKind.STYLE,)
    assert requires_style_leg(CellStyle(border_type="FULL_BORDER").op_kinds) is True
    assert STYLE_LEG_OP_KINDS == frozenset({
        WriteOpKind.STYLE, WriteOpKind.NUMBER_FORMAT,
        WriteOpKind.MERGE, WriteOpKind.STRUCTURE})
    kinds = [v for k, v in vars(WriteOpKind).items()
             if k.isupper() and isinstance(v, str)]
    assert {"style", "number-format", "merge", "structure", "value"} <= set(kinds)
    assert not [k for k in kinds if "border" in k or "wrap" in k]
    assert {d.kind for d in sheets_ops.OPS if "border" in d.kind} == set()


def test_ac2_describe_names_the_border_so_the_plan_semantic_does_too():
    described = CellStyle(border_type="FULL_BORDER", border_color="#FF0000").describe()
    assert "FULL_BORDER" in described and "#FF0000" in described
    assert "border" in CellStyle(border_type=BORDER_CLEAR).describe().lower()


def test_ac2_a_border_alone_is_a_legal_style_and_an_empty_style_still_refuses():
    assert CellStyle(border_type="NO_BORDER").wire() == {"borderType": "NO_BORDER"}
    with pytest.raises(StyleError, match="at least one"):
        CellStyle()


# --- the probed refusals, quoted verbatim, refused at CONSTRUCTION ---------- #

def test_ac2_an_invalid_border_type_is_refused_at_construction_quoting_larks_body():
    for label, value in (("D4 INVALID borderType 'DIAGONAL_ZIGZAG'", "DIAGONAL_ZIGZAG"),
                         ("D5 INVALID borderType lower-case 'full_border'", "full_border"),
                         ("D3 CLEAR attempt — borderType '' (empty string)", "")):
        step = _step(label)
        assert step["code"] == BORDER_REFUSAL_CODE
        assert step["msg"] == BORDER_TYPE_REFUSAL_BODY
        with pytest.raises(StyleError) as exc:
            CellStyle(border_type=value)
        assert BORDER_TYPE_REFUSAL_BODY in str(exc.value)
        assert str(BORDER_REFUSAL_CODE) in str(exc.value)


def test_ac2_border_type_is_case_sensitive_because_lark_refuses_the_lower_case_form():
    assert _step("D5 INVALID borderType lower-case")["code"] == BORDER_REFUSAL_CODE
    with pytest.raises(StyleError):
        CellStyle(border_type="full_border")
    assert _raw("D5")["borderId"] == 0        # and it landed nothing


def test_ac2_a_malformed_border_color_is_refused_quoting_the_probed_body():
    step = _step("D7 borderColor in a BAD form")
    assert step["code"] == BORDER_REFUSAL_CODE and step["msg"] == BORDER_COLOR_REFUSAL_BODY
    with pytest.raises(StyleError) as exc:
        CellStyle(border_type="FULL_BORDER", border_color="red")
    assert BORDER_COLOR_REFUSAL_BODY in str(exc.value)


def test_ac2_border_color_without_a_border_type_is_refused_because_lark_SILENTLY_ignores_it():
    """The nastiest arm: ``borderColor`` alone answered ``code 0`` / ``updatedCells: 1`` and
    landed NOTHING. A knob that reports success and does nothing is exactly the half-working
    field this issue exists to avoid, so it is refused before any call."""
    step = _step("D6 borderColor ALONE, no borderType")
    assert step["code"] == 0 and step["msg"] == "success"
    assert step["response"]["data"]["updates"]["updatedCells"] == 1
    assert _edges("D6") == [] and _raw("D6")["s"] == 0        # nothing landed
    with pytest.raises(StyleError) as exc:
        CellStyle(border_color="#00FF00")
    assert "border_type" in str(exc.value)


# --- the characterized SEMANTICS a shipped knob has to state correctly ------ #

def test_ac1_per_edge_border_types_land_exactly_one_edge_each():
    assert _edges("A4") == ["left"]
    assert _edges("A5") == ["right"]
    assert _edges("A6") == ["top"]
    assert _edges("A7") == ["bottom"]
    assert _edges("A2") == ["bottom", "left", "right", "top"]


def test_ac1_outer_border_draws_the_ranges_perimeter_and_inner_the_grid_lines():
    # OUTER_BORDER over B2:C3 — each corner cell gets only its two outside edges.
    assert _edges("B2") == ["left", "top"] and _edges("C2") == ["right", "top"]
    assert _edges("B3") == ["bottom", "left"] and _edges("C3") == ["bottom", "right"]
    # INNER_BORDER over B4:C5 — the internal lines only, no perimeter.
    assert _edges("B4") == ["bottom", "right"] and _edges("C4") == ["bottom", "left"]
    assert _edges("B5") == ["right", "top"] and _edges("C5") == ["left", "top"]


def test_ac1_border_color_lands_as_the_argb_the_export_reports():
    assert _raw("A3")["border"]["left"]["color"]["rgb"] == "FFFF0000"
    assert _raw("G3")["border"]["left"]["color"]["rgb"] == "FF0000FF"


def test_ac1_round_two_semantics_additive_union_and_the_clear():
    v = _SEMANTICS["verdicts"]
    # additive: an unrelated font write on a bordered cell KEEPS the border.
    assert v["P1_additive_border_survives_font_write"] == ["bottom", "left", "right", "top"]
    # two per-edge writes UNION rather than replace.
    assert v["P2_two_edge_writes"] == ["left", "top"]
    # NO_BORDER clears a PARTIAL border, not just a full one.
    assert v["P3_no_border_clears_partial"] == []
    # and it clears only the cells it names — the neighbours keep theirs.
    assert v["P4_subset_cleared_C1"] == []
    for key in ("P4_neighbour_kept_D1", "P4_neighbour_kept_C2", "P4_neighbour_kept_D2"):
        assert v[key] == ["bottom", "left", "right", "top"]


def test_ac1_a_border_does_not_spread_across_a_merge_either():
    """The same asymmetry LD-188 found for fill: a border on part of a merge lands on the
    named cells only — so ``style-partial-merge`` covers a border unchanged."""
    assert _edges("E2") == _edges("E3") == _edges("E4") == [
        "bottom", "left", "right", "top"]           # whole span named → whole span bordered
    assert _edges("F2") == ["bottom", "left", "right", "top"]   # anchor only …
    assert _edges("F3") == [] and _edges("F4") == []            # … covered cells untouched


# --------------------------------------------------------------------------- #
# AC3 — CONFIRMED but NOT read-back-able: the gate limit is DISCLOSED.         #
# --------------------------------------------------------------------------- #

def test_ac3_the_shipped_export_reader_surfaces_no_border_field():
    """The premise of the disclosure, derived from the reader rather than asserted in prose:
    if a border field is ever added to ``ExportedCell`` this test reddens and the disclosure
    must be revisited."""
    names = {f.name for f in dataclass_fields(ExportedCell)}
    assert names == {"ref", "value", "bold", "italic", "fill_rgb", "num_fmt"}
    assert not [n for n in names if "border" in n or "wrap" in n]


def test_ac3_a_border_plan_entry_discloses_that_the_style_leg_cannot_verify_it():
    gateway = FakeStyleGateway()
    plan = dry_run([StyleWriteRequest(f"{SID}!A1:B2", CellStyle(border_type="FULL_BORDER"))],
                   gateway, TOKEN)
    notes = _notes(plan.entries[0])
    disclosure = _note_of_kind(notes, "style-border-not-verifiable")
    assert disclosure is not None
    assert "border" in disclosure["note"].lower()
    assert "ExportedCell" in disclosure["note"]
    assert disclosure["border_ranges"] == [f"{SID}!A1:B2"]


def test_ac3_the_disclosure_is_ABSENT_from_a_style_that_carries_no_border():
    """Exactly those fields — a fill / font / number-format plan must not carry it."""
    for style in (CellStyle(bold=True), CellStyle(back_color="#FFFF00"),
                  CellStyle(formatter="0.00%"), CellStyle(italic=True, font_size=12)):
        plan = dry_run([StyleWriteRequest(f"{SID}!A1:B2", style)], FakeStyleGateway(), TOKEN)
        assert _note_of_kind(_notes(plan.entries[0]),
                            "style-border-not-verifiable") is None


def test_ac3_the_disclosure_fires_for_the_batch_form_and_names_only_bordered_ranges():
    gateway = FakeStyleGateway()
    plan = dry_run([BatchStyleWriteRequest([
        StyleSpan([f"{SID}!A1:A1"], CellStyle(bold=True)),
        StyleSpan([f"{SID}!B1:B1", f"{SID}!C1:C1"], CellStyle(border_type="OUTER_BORDER")),
    ])], gateway, TOKEN)
    disclosure = _note_of_kind(_notes(plan.entries[0]), "style-border-not-verifiable")
    assert disclosure["border_ranges"] == [f"{SID}!B1:B1", f"{SID}!C1:C1"]


def test_ac3_the_disclosure_does_not_displace_the_ld188_notes_it_rides_beside():
    """Notes COMPOSE — the export-cost note and the border disclosure both survive."""
    plan = dry_run([StyleWriteRequest(f"{SID}!A1:B2",
                                      CellStyle(bold=True, border_type="FULL_BORDER"))],
                   FakeStyleGateway(), TOKEN)
    kinds = {n["kind"] for n in _notes(plan.entries[0])}
    assert {"style-verification-cost", "style-border-not-verifiable"} <= kinds


def test_ac3_the_disclosure_never_claims_a_verification_happened():
    plan = dry_run([StyleWriteRequest(f"{SID}!A1:B2", CellStyle(border_type="FULL_BORDER"))],
                   FakeStyleGateway(), TOKEN)
    note = _note_of_kind(_notes(plan.entries[0]), "style-border-not-verifiable")["note"]
    # It must say the border is NOT verified …
    assert "NOT VERIFIED" in note
    # … and say what IS, so the caller neither over- nor under-reads the leg's coverage.
    assert "verified as usual" in note
    # and it must not pretend the border did not land — it did; only the CHECK is missing.
    assert "does land" in note


# --------------------------------------------------------------------------- #
# AC4 — WORD-WRAP: REFUTED, and documented loudly.                            #
# --------------------------------------------------------------------------- #

def test_ac4_every_probed_wrap_candidate_answered_success_and_landed_nothing():
    """Nine field names, nine ``code: 0``, nine unstyled cells — the refutation, re-derived
    from the capture instead of trusted from prose."""
    arms = [s for s in _PROBE["steps"] if "wrap candidate" in s.get("label", "")]
    assert len(arms) == 9
    for step in arms:
        assert step["code"] == 0 and step["msg"] == "success"
        ref = step["request_body"]["appendStyle"]["range"].split("!")[1].split(":")[0]
        assert _raw(ref)["alignment"] is None or "wrapText" not in _raw(ref)["alignment"], (
            f"{step['label']}: a wrap actually landed — the verdict would need revisiting")


def test_ac4_the_wrap_candidates_are_indistinguishable_from_the_nonsense_control():
    """This is the proof, not the ``code 0``: every candidate behaves EXACTLY like a field
    name that was invented to be meaningless."""
    control = _step("X0b control")["response"]["data"]["updates"]
    for step in [s for s in _PROBE["steps"] if "wrap candidate" in s.get("label", "")]:
        updates = step["response"]["data"]["updates"]
        assert (step["code"], updates["updatedCells"]) == (0, control["updatedCells"])


def test_ac4_the_distinguishing_arm_proves_the_export_does_report_alignment():
    """``{"hAlign": 0, "wrap": true}`` — ONE request, one field landed and one did not. So the
    export is not blind to alignment; ``wrapText`` is missing because nothing set it."""
    step = _step("C8 wrap candidate")
    assert step["request_body"]["appendStyle"]["style"] == {"hAlign": 0, "wrap": True}
    alignment = _raw("C8")["alignment"]
    assert alignment["horizontal"] == "left"          # the REAL field landed
    assert "wrapText" not in alignment                # the wrap did not


def test_ac4_the_probed_field_names_are_recorded_in_src_exactly_as_probed():
    """``WORD_WRAP_PROBED_FIELDS`` is the authored record of what was tried; it must match the
    capture, so the documented limit cannot overstate or understate the search."""
    probed = [json.dumps(s["request_body"]["appendStyle"]["style"], sort_keys=True)
              for s in _PROBE["steps"] if "wrap candidate" in s.get("label", "")]
    assert sorted(json.dumps(f, sort_keys=True) for f in WORD_WRAP_PROBED_FIELDS) == sorted(probed)


def test_ac4_the_loud_statement_names_the_evidence_and_refuses_to_paraphrase_it():
    text = WORD_WRAP_NOT_WRITABLE
    assert "word wrap" in text.lower() or "word-wrap" in text.lower()
    assert "success" in text                       # the verbatim reply that means nothing
    assert "tests/captures/sheets-border-wrap-probe" in text  # the evidence pointer
    assert "hAlign" in text                        # the distinguishing arm
    for word in ("wrap", "wrapText", "wrapStrategy", "textWrap", "autoWrap"):
        assert word in text


def test_ac4_no_half_working_wrap_field_reached_the_wire_builder():
    """Nothing in the style payload builder can emit a wrap key, under any input."""
    style = CellStyle(bold=True, italic=True, font_size=12, back_color="#FFFF00",
                      fore_color="#FF0000", formatter="0.00%",
                      border_type="FULL_BORDER", border_color="#FF0000")
    assert not [k for k in style.wire() if "wrap" in k.lower()]
    with pytest.raises(TypeError):
        CellStyle(wrap=True)


def test_ac4_the_guide_and_sheets_md_carry_the_loud_statement():
    guide = (REPO_ROOT / "src" / "larkdocio" / "GUIDE.md").read_text(encoding="utf-8")
    sheets_md = (REPO_ROOT / "SHEETS.md").read_text(encoding="utf-8")
    for text in (guide, sheets_md):
        assert "NOT A WRITABLE CELL-STYLE FIELD" in text
        assert "tests/captures/sheets-border-wrap-probe" in text
    # and the stale pre-LD-189 claim that borders are unwritable is GONE.
    assert "wrap and borders are not among the fields" not in guide
    assert "they remain unwritable for now" not in guide


# --------------------------------------------------------------------------- #
# AC7 — the truth rows, and the backlog's mis-filing corrected.               #
# --------------------------------------------------------------------------- #

def test_ac7_capabilities_projects_the_settable_style_fields_off_cell_style_itself():
    """So the answer to "can a style write set a border? a wrap?" is DERIVED, not asserted."""
    style_op = next(op for op in capabilities(full=True)["surfaces"]["sheets-write"]["operations"]
                    if op["name"] == "style")
    assert style_op["style_fields"] == [f.name for f in dataclass_fields(CellStyle)]
    assert "border_type" in style_op["style_fields"]
    assert not [f for f in style_op["style_fields"] if "wrap" in f]
    assert style_op["style_fields_not_writable"] == ["word-wrap"]


def test_ac7_sheets_md_records_the_per_field_verdict_with_its_evidence():
    sheets_md = (REPO_ROOT / "SHEETS.md").read_text(encoding="utf-8")
    assert "shipped-LD-189" in sheets_md
    assert "borderType" in sheets_md and "borderColor" in sheets_md
    assert "01-border-wrap-characterization.json" in sheets_md
    assert "02-border-semantics.json" in sheets_md


@private_tree.dev_record
def test_ac7_the_backlogs_misfiling_of_word_wrap_under_dimensions_is_corrected():
    backlog = (REPO_ROOT / "dev" / "backlog-2026-07-28-feature-menu.md").read_text(
        encoding="utf-8")
    dimension_row = next(line for line in backlog.splitlines()
                         if "dimensionProperties" in line and "fixedSize" in line)
    # LD-242: md_table_cells drops the empty leading field a bare split("|") leaves, so
    # the deliberate second-cell index moves 2 -> 1; the cell is trimmed, which the two
    # assertions below (a lower-cased substring test and a repr in the failure message)
    # cannot see.
    title = md_table_cells(dimension_row)[1]
    assert "wrap" not in title.lower(), (
        "wrap must not be listed as a DELIVERABLE of the dimension item — it is a cell-style "
        f"field and LD-189 refuted it there. Got: {title!r}")
    # the correction is recorded IN that row rather than silently dropped, so the next reader
    # does not re-file it here a second time.
    assert "CORRECTED (LD-189)" in dimension_row and "REFUTED" in dimension_row
    assert "LD-189" in backlog


# --------------------------------------------------------------------------- #
# Local helpers                                                               #
# --------------------------------------------------------------------------- #

def _notes(entry):
    note = entry.preview_note
    if note is None:
        return []
    if note.get("kind") == "multiple":
        return list(note["notes"])
    return [note]


def _note_of_kind(notes, kind):
    for note in notes:
        if note.get("kind") == kind:
            return note
    return None


# --------------------------------------------------------------------------- #
# LD-631 — `CellStyle.has_border`: the predicate, and the mechanism it is NOT.  #
#                                                                              #
# The property is public and shipped in the docstring corpus, and nothing in    #
# this repository read it — so its docstring's claim about how the              #
# `style-border-not-verifiable` note is produced had never been checked, and    #
# it was wrong: the note reads the SERIALIZED span, not this property. The      #
# docstring now says that, and these two tests hold both halves.               #
# --------------------------------------------------------------------------- #

def test_ld631_has_border_is_exactly_border_type_is_set():
    """The predicate itself, over the real accepted vocabulary plus the clear: a border of any
    kind is a border, ``NO_BORDER`` included (it is a border WRITE — the clear), and a style
    with no ``border_type`` is not, whatever else it carries."""
    for value in BORDER_TYPES:
        assert CellStyle(border_type=value).has_border is True
    assert CellStyle(border_type=BORDER_CLEAR).has_border is True
    # A colour with no type never reaches the predicate at all: the dataclass refuses it,
    # because a borderColor sent alone reports success and lands nothing. So the predicate
    # has no "coloured but unbordered" case to get wrong.
    with pytest.raises(StyleError):
        CellStyle(border_color="#FF0000")
    for style in (CellStyle(bold=True), CellStyle(back_color="#FFFF00"),
                  CellStyle(formatter="0.00%")):
        assert style.has_border is False


def test_ld631_the_not_verifiable_note_does_NOT_go_through_has_border():
    """What the docstring used to claim, refuted where it matters: the note is computed from
    the span's own serialized style, so a span assembled WITHOUT a ``CellStyle`` — the shape
    that has no property to read — still gets the disclosure, and a span that carries a
    ``CellStyle`` reporting no border still gets none."""
    bordered = {"spans": [{"ranges": [f"{SID}!A1:A1"],
                           "style": CellStyle(border_type="FULL_BORDER").wire()}]}
    hand_rolled = {"spans": [{"ranges": [f"{SID}!A1:A1"],
                              "style": {"borderType": "FULL_BORDER"}}]}
    plain = {"spans": [{"ranges": [f"{SID}!A1:A1"],
                        "style": CellStyle(bold=True).wire()}]}
    note = sheets_ops.style_border_not_verifiable_note
    assert note(bordered) is not None
    assert note(hand_rolled) == note(bordered), (
        "the note is keyed off the serialized borderType, so the two shapes agree")
    assert note(plain) is None
