"""LD-149 — Sheets FORMULA writes: the probe-confirmed `FormulaWriteRequest` family.

**The finding this file encodes** (LD-149 probe, live on a self-provisioned disposable
2026-07-28 — spreadsheet_token ``Exampled09268e885dd6d906728``, deleted, zero orphans):

* the documented object form ``{"type":"formula","text":"=SUM(B3:B8)"}`` written through the
  values path **DOES evaluate** — ``Formula`` mode reads back the **expression**
  (``"=SUM(B3:B8)"``), ``UnformattedValue`` / ``FormattedValue`` the **computed value**
  (``21``), ``ToString`` the expression with the leading ``=`` **stripped**
  (``"SUM(B3:B8)"``);
* a **plain ``"=…"`` string NEVER evaluates** — it stores as inert text and reads back
  ``"=SUM(B3:B8)"`` under **all four** render modes, **including ``Formula``**;
* there is **NO ``valueInputOption``** on this API: ``?valueInputOption=USER_ENTERED``,
  ``?valueInputOption=RAW`` and a body-level ``valueInputOption`` are each answered
  ``code 0 / "success"`` and have **zero effect** — the string stays inert (proven three
  ways);
* therefore ``Formula`` mode **alone cannot tell** an inert ``=``-string from a real
  formula. The ONE discriminator is the **computed-value leg**: a cell evaluated iff its
  ``UnformattedValue`` read-back **differs** from its stored expression. Every
  verification here keys on that;
* a **syntactically invalid** formula (``"=SUM("``) is **accepted** by the API (``code 0``)
  and stored **inert** — no error is raised, so the engine must DETECT it, not expect a
  refusal. A **bad function name** (``"=NOTAFUNC(B3)"``) *does* become a real formula whose
  computed value is the error sentinel ``"#NAME?"``;
* the computed value **drifts with the data** (B3 ``1``→``100`` moved ``21``→``120`` with the
  expression unchanged) — which is exactly why the precondition compares the **EXPRESSION**
  (AC3, the maintainer-adopted recommendation).

Offline throughout: a mode-aware duck-typed gateway models the render modes the probe
characterized. The live round-trip is ``tests/test_live_sheets_formula_write_gate.py``.
"""
import json

import pytest

from log_reading_apply import reading_the_log
from larkdocio.errors import LarkAPIError, LarkConfigError
from larkdocio.sheets.formula import (
    COMPUTED_RENDER_OPTION,
    DISPLAY_RENDER_OPTION,
    EQUALS_PREFIX,
    ERROR_SENTINELS,
    EXPRESSION_RENDER_OPTION,
    INERT_STRING_NOTE,
    FormulaExpressionError,
    encode_formula,
    equals_prefixed_cells,
    equals_prefixed_note,
    formula_expression,
    formula_record,
    is_formula_cell,
)
from larkdocio.sheets.write_apply import (
    ApplyLog,
    FormulaWriteRequest,
    Plan,
    Refusal,
    ValueWriteRequest,
    WriteOpKind,
    apply,
    dry_run,
)
apply = reading_the_log(apply)
TOKEN = "shtLD149TOKEN"
SID = "s1"


# =========================================================================== #
# The mode-aware client seam — models EXACTLY what the probe characterized.     #
# =========================================================================== #

class FormulaAwareGateway:
    """A duck-typed write-client stand-in that models Lark's **render modes**.

    A cell written as the object form ``{"type":"formula","text":…}`` is stored as a
    formula: ``Formula`` mode answers the (optionally server-normalized) expression,
    ``UnformattedValue`` / ``FormattedValue`` the computed value. A plain string is stored
    verbatim and answers the SAME text under every mode — the probe's inert signature.

    ``compute`` maps an expression → its computed value (the fake's stand-in for Lark's
    evaluator). An expression absent from ``compute`` models the **API-accepts-but-stores-
    inert** case the probe found for ``"=SUM("``: the computed leg answers the expression
    itself, which is precisely the inert signature.
    """

    def __init__(self, *, revision=1, cells=None, compute=None, normalize=None):
        self.revision = revision
        #: ``{a1_range: matrix}`` — a matrix cell is a scalar/str, or the formula object.
        self.cells = {k: [list(r) for r in v] for k, v in (cells or {}).items()}
        self.compute = dict(compute or {})
        #: ``{sent_expression: server_normalized_expression}`` (Lark quotes tab titles).
        self.normalize = dict(normalize or {})
        self.puts = []
        self.reads = []                 # [(a1_range, mode)]
        self.external_bumps = {}        # {read_revision_call_n: delta}
        self._rev_reads = 0
        self.raise_on_read = {}         # {(a1_range, mode): Exception}
        self.raise_on_put = None

    # -- reads ------------------------------------------------------------ #

    def read_revision(self, spreadsheet_token):
        self._rev_reads += 1
        self.revision += self.external_bumps.pop(self._rev_reads, 0)
        return self.revision

    def read_values(self, spreadsheet_token, a1_range,
                    value_render_option="UnformattedValue"):
        self.reads.append((a1_range, value_render_option))
        boom = self.raise_on_read.get((a1_range, value_render_option))
        if boom is not None:
            raise boom
        matrix = self.cells.get(a1_range)
        if matrix is None:
            return []
        return [[self._render(cell, value_render_option) for cell in row] for row in matrix]

    def _render(self, cell, mode):
        expression = formula_expression(cell)
        if expression is None:
            return cell                      # a plain value renders the same in every mode
        stored = self.normalize.get(expression, expression)
        if mode == EXPRESSION_RENDER_OPTION:
            return stored
        if mode == "ToString":
            return stored[1:] if stored.startswith(EQUALS_PREFIX) else stored
        # the value modes: the computed value, or the expression itself when Lark could not
        # parse it (the probe's `"=SUM("` inert case).
        return self.compute.get(expression, stored)

    # -- the write -------------------------------------------------------- #

    def put_values(self, spreadsheet_token, a1_range, values):
        if self.raise_on_put is not None:
            raise self.raise_on_put
        self.puts.append((a1_range, values))
        self.cells[a1_range] = [list(r) for r in values]
        self.revision += 1
        return {"revision": self.revision}

    def query_tabs(self, spreadsheet_token):
        return [{"sheet_id": SID, "title": "Sheet1", "index": 0}]


SUM_EXPR = "=SUM(B3:B8)"


def _gateway(**kwargs):
    kwargs.setdefault("cells", {f"{SID}!C1:C1": [[None]]})
    kwargs.setdefault("compute", {SUM_EXPR: 21})
    return FormulaAwareGateway(**kwargs)


def _apply_one(request, gateway):
    plan = dry_run([request], gateway, TOKEN)
    return plan, apply(plan, gateway)


# =========================================================================== #
# AC1 — the probe's characterization, pinned as executable facts.               #
# =========================================================================== #

def test_probe_fact_the_object_form_is_the_documented_wire_shape():
    assert encode_formula(SUM_EXPR) == {"type": "formula", "text": SUM_EXPR}


def test_probe_fact_the_render_mode_constants_name_the_three_legs():
    assert EXPRESSION_RENDER_OPTION == "Formula"
    assert COMPUTED_RENDER_OPTION == "UnformattedValue"
    assert DISPLAY_RENDER_OPTION == "FormattedValue"


def test_probe_fact_all_four_render_modes_are_characterized_for_a_formula_cell():
    """The LD-100 four-mode matrix discipline, pinned from the probe's own read-back."""
    gw = _gateway(cells={f"{SID}!C1:C1": [[encode_formula(SUM_EXPR)]]})
    got = {
        mode: gw.read_values(TOKEN, f"{SID}!C1:C1", value_render_option=mode)[0][0]
        for mode in ("Formula", "UnformattedValue", "FormattedValue", "ToString")
    }
    assert got == {
        "Formula": SUM_EXPR,
        "UnformattedValue": 21,
        "FormattedValue": 21,
        "ToString": "SUM(B3:B8)",       # the leading '=' is STRIPPED (probe)
    }


def test_probe_fact_an_inert_equals_string_reads_identically_under_every_mode():
    """The trap: ``Formula`` mode CANNOT distinguish inert text from a real formula."""
    gw = _gateway(cells={f"{SID}!C2:C2": [[SUM_EXPR]]})
    got = {
        mode: gw.read_values(TOKEN, f"{SID}!C2:C2", value_render_option=mode)[0][0]
        for mode in ("Formula", "UnformattedValue", "FormattedValue", "ToString")
    }
    assert set(got.values()) == {SUM_EXPR}, got


def test_probe_fact_the_evaluated_discriminator_is_the_computed_leg():
    """A cell evaluated iff the computed read-back DIFFERS from the stored expression."""
    assert formula_record(
        expression=SUM_EXPR, stored_expression=SUM_EXPR, computed_value=21)["evaluated"]
    assert not formula_record(
        expression=SUM_EXPR, stored_expression=SUM_EXPR,
        computed_value=SUM_EXPR)["evaluated"]


def test_probe_fact_an_error_sentinel_still_counts_as_evaluated_but_is_flagged():
    """``"=NOTAFUNC(B3)"`` DID become a formula; its computed value is ``"#NAME?"``."""
    rec = formula_record(expression="=NOTAFUNC(B3)", stored_expression="=NOTAFUNC(B3)",
                         computed_value="#NAME?")
    assert rec["evaluated"] is True
    assert rec["error_value"] is True
    assert "#NAME?" in rec["detail"]
    assert "#NAME?" in ERROR_SENTINELS and "#REF!" in ERROR_SENTINELS


def test_formula_record_always_carries_a_nonempty_detail():
    """LD-131's mandatory-detail discipline: a typed record with no WHY is a riddle."""
    for computed in (21, SUM_EXPR, "#REF!", 0, None):
        rec = formula_record(expression=SUM_EXPR, stored_expression=SUM_EXPR,
                             computed_value=computed)
        assert rec["detail"], rec


def test_formula_record_flags_a_server_normalized_expression():
    """Lark rewrote ``=SUM(Other!A1:A2)`` to ``=SUM('Other'!A1:A2)`` (probe, cross-tab)."""
    rec = formula_record(expression="=SUM(Other!A1:A2)",
                         stored_expression="=SUM('Other'!A1:A2)", computed_value=30)
    assert rec["normalized"] is True
    assert rec["evaluated"] is True
    assert "=SUM('Other'!A1:A2)" in rec["detail"]


# =========================================================================== #
# AC2 — FormulaWriteRequest: frozen, typed, JSON round-tripping, gated.        #
# =========================================================================== #

def test_formula_request_carries_target_and_expression():
    req = FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR)
    assert req.target.a1() == f"{SID}!C1:C1"      # single cell → Start:End (D2)
    assert req.expression == SUM_EXPR
    assert req.values == [[{"type": "formula", "text": SUM_EXPR}]]


def test_formula_request_is_frozen():
    req = FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR)
    with pytest.raises(Exception):
        req.expression = "=1+1"


def test_formula_request_round_trips_through_json():
    req = FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR)
    d = req.to_dict()
    assert json.loads(json.dumps(d)) == d
    assert FormulaWriteRequest.from_dict(d) == req


def test_formula_request_declares_the_value_op_kind_and_formula_write_kind():
    req = FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR)
    assert req.write_kind == "formula"
    assert req.op_kinds == (WriteOpKind.VALUE,)   # cheap values leg only, no export
    assert req.is_rich is False


@pytest.mark.parametrize("bad", ["SUM(B3:B8)", " =SUM(B3:B8)", "", "   ", "42"])
def test_formula_request_refuses_an_expression_that_does_not_start_with_equals(bad):
    """You cannot BUILD a formula request from text Lark would store inert (AC5's trap,
    closed at construction rather than discovered after the write)."""
    with pytest.raises(FormulaExpressionError):
        FormulaWriteRequest.for_a1(f"{SID}!C1", bad)


def test_formula_expression_error_is_a_config_error():
    assert issubclass(FormulaExpressionError, LarkConfigError)


@pytest.mark.parametrize("bad", [None, 42, ["=SUM(A1:A2)"], {"text": "=1+1"}])
def test_formula_request_refuses_a_non_string_expression(bad):
    with pytest.raises(FormulaExpressionError):
        FormulaWriteRequest.for_a1(f"{SID}!C1", bad)


def test_formula_request_flows_through_the_gated_engine():
    gw = _gateway()
    plan, log = _apply_one(FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR), gw)

    assert isinstance(plan, Plan) and isinstance(log, ApplyLog)
    assert gw.puts == [(f"{SID}!C1:C1", [[{"type": "formula", "text": SUM_EXPR}]])]
    (entry,) = log.entries
    assert entry.outcome == "applied"
    assert entry.write_kind == "formula"
    assert entry.revision == gw.revision


def test_formula_write_is_refused_when_the_plan_is_hand_forged():
    """The non-forgeable-Plan gate covers the new family too."""
    gw = _gateway()
    with pytest.raises(TypeError):
        apply([FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR)], gw)


def test_formula_dry_run_issues_zero_writes():
    gw = _gateway()
    dry_run([FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR)], gw, TOKEN)
    assert gw.puts == []


def test_formula_entry_is_stale_sheet_guarded():
    gw = _gateway()
    plan = dry_run([FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR)], gw, TOKEN)
    gw.external_bumps = {gw._rev_reads + 1: 1}
    log = apply(plan, gw)
    assert gw.puts == [], "a stale sheet must refuse the formula write"
    assert log.entries[0].refusal.reason == Refusal.STALE_SHEET


def test_formula_entry_reports_tier_two_as_enforced():
    gw = _gateway()
    plan = dry_run([FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR)], gw, TOKEN)
    assert plan.entries[0].value_precondition == "enforced"


# =========================================================================== #
# AC3 — the precondition compares the EXPRESSION, not the computed value.      #
# =========================================================================== #

def test_dry_run_captures_the_expression_as_the_precondition_basis():
    gw = _gateway(cells={f"{SID}!C1:C1": [[encode_formula("=SUM(A1:A2)")]]},
                  compute={"=SUM(A1:A2)": 7, SUM_EXPR: 21})
    plan = dry_run([FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR)], gw, TOKEN)
    assert plan.entries[0].before == [["=SUM(A1:A2)"]], "the before must be the EXPRESSION"
    assert (f"{SID}!C1:C1", EXPRESSION_RENDER_OPTION) in gw.reads


def test_a_changed_computed_value_does_not_spuriously_refuse():
    """AC3, the maintainer-adopted recommendation: a computed value drifts with the DATA (probe:
    B3 1→100 moved 21→120), so comparing it would refuse writes nobody edited."""
    gw = _gateway(cells={f"{SID}!C1:C1": [[encode_formula("=SUM(A1:A2)")]]},
                  compute={"=SUM(A1:A2)": 7, SUM_EXPR: 21})
    plan = dry_run([FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR)], gw, TOKEN)

    gw.compute["=SUM(A1:A2)"] = 999        # the DATA moved; nobody touched the cell
    log = apply(plan, gw)

    assert log.entries[0].outcome == "applied", log.entries[0].to_dict()
    assert gw.puts, "the write must proceed — the expression did not drift"


def test_a_drifted_expression_refuses_precondition_mismatch():
    gw = _gateway(cells={f"{SID}!C1:C1": [[encode_formula("=SUM(A1:A2)")]]},
                  compute={"=SUM(A1:A2)": 7, "=SUM(A1:A9)": 9, SUM_EXPR: 21})
    plan = dry_run([FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR)], gw, TOKEN)

    gw.cells[f"{SID}!C1:C1"] = [[encode_formula("=SUM(A1:A9)")]]   # someone edited it
    log = apply(plan, gw)

    assert gw.puts == [], "a drifted expression must refuse without writing"
    refusal = log.entries[0].refusal
    assert refusal.reason == Refusal.PRECONDITION_MISMATCH
    assert "=SUM(A1:A9)" in refusal.detail and "=SUM(A1:A2)" in refusal.detail


def test_the_precondition_read_uses_the_expression_leg_at_apply_too():
    gw = _gateway(cells={f"{SID}!C1:C1": [[encode_formula("=SUM(A1:A2)")]]},
                  compute={"=SUM(A1:A2)": 7, SUM_EXPR: 21})
    plan = dry_run([FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR)], gw, TOKEN)
    before = len([r for r in gw.reads if r[1] == EXPRESSION_RENDER_OPTION])
    apply(plan, gw)
    after = len([r for r in gw.reads if r[1] == EXPRESSION_RENDER_OPTION])
    assert after > before, "apply must re-read the EXPRESSION for the precondition"


def test_a_plain_string_target_is_a_legitimate_before_for_a_formula_write():
    """Writing a formula over a static value: the expression leg reads the static value
    (a plain cell renders identically in every mode), and that IS the precondition."""
    gw = _gateway(cells={f"{SID}!C1:C1": [["21"]]})
    plan, log = _apply_one(FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR), gw)
    assert plan.entries[0].before == [["21"]]
    assert log.entries[0].outcome == "applied"


# =========================================================================== #
# AC2/AC7 — the plan preview: expression + a computed-value read-back note.     #
# =========================================================================== #

def test_the_plan_preview_shows_the_expression_and_the_computed_read_back_note():
    gw = _gateway(cells={f"{SID}!C1:C1": [[encode_formula("=SUM(A1:A2)")]]},
                  compute={"=SUM(A1:A2)": 7, SUM_EXPR: 21})
    plan = dry_run([FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR)], gw, TOKEN)
    note = plan.entries[0].preview_note

    assert note["kind"] == "formula"
    assert note["expression"] == SUM_EXPR
    assert note["current_expression"] == [["=SUM(A1:A2)"]]
    assert note["current_computed_value"] == [[7]]
    assert note["precondition_compares"] == "expression"
    assert "computed" in note["read_back_note"].lower()
    assert COMPUTED_RENDER_OPTION in note["read_back_note"]


def test_the_formula_preview_note_survives_the_plan_json():
    gw = _gateway()
    plan = dry_run([FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR)], gw, TOKEN)
    wire = json.loads(plan.to_json())
    assert wire["entries"][0]["preview_note"]["expression"] == SUM_EXPR


def test_an_ordinary_value_entry_carries_no_preview_note_key_at_all():
    """Zero-drift: the existing value path's serialized shape is untouched."""
    gw = _gateway(cells={f"{SID}!A1:A1": [["old"]]})
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1", [["new"]])], gw, TOKEN)
    assert plan.entries[0].preview_note is None
    assert "preview_note" not in json.loads(plan.to_json())["entries"][0]


# =========================================================================== #
# The apply-log's formula record + the INERT detection (typed handling).        #
# =========================================================================== #

def test_the_apply_log_records_the_computed_read_back():
    gw = _gateway()
    _plan, log = _apply_one(FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR), gw)
    rec = log.entries[0].formula
    assert rec["expression"] == SUM_EXPR
    assert rec["stored_expression"] == SUM_EXPR
    assert rec["computed_value"] == 21
    assert rec["evaluated"] is True
    assert log.entries[0].formula_evaluated is True
    assert log.formula_not_evaluated == ()


def test_the_apply_log_formula_record_survives_json():
    gw = _gateway()
    _plan, log = _apply_one(FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR), gw)
    wire = json.loads(log.to_json())
    assert wire["entries"][0]["formula"]["computed_value"] == 21


def test_a_syntactically_invalid_formula_is_detected_as_inert_not_silently_shipped():
    """The probe: Lark ACCEPTS ``"=SUM("`` (code 0) and stores it as inert text. The write
    lands, so the entry is honestly ``applied`` — but the record says ``evaluated: False``
    with a loud WHY, and the log exposes it as a first-class collection."""
    gw = _gateway(compute={})          # nothing evaluates → the inert signature
    _plan, log = _apply_one(FormulaWriteRequest.for_a1(f"{SID}!C1", "=SUM("), gw)

    entry = log.entries[0]
    assert entry.outcome == "applied", "the write DID land — the log must not deny it"
    assert entry.formula["evaluated"] is False
    assert entry.formula_evaluated is False
    assert log.formula_not_evaluated == (entry,)
    for phrase in ("did NOT evaluate", "INERT TEXT", "Fix the expression"):
        assert phrase in entry.formula["detail"], entry.formula["detail"]


def test_a_formula_over_empty_cells_evaluates_to_zero_and_is_not_flagged_inert():
    """Probe: ``=SUM(Z100:Z110)`` → ``0``. A falsy computed value is still evaluated."""
    expr = "=SUM(Z100:Z110)"
    gw = _gateway(compute={expr: 0})
    _plan, log = _apply_one(FormulaWriteRequest.for_a1(f"{SID}!C1", expr), gw)
    assert log.entries[0].formula["computed_value"] == 0
    assert log.entries[0].formula["evaluated"] is True
    assert log.formula_not_evaluated == ()


def test_a_nested_function_expression_round_trips_verbatim():
    """Probe: ``=IF(SUM(B3:B8)>10,"big","small")`` → ``"big"`` — and the COMMAS and the
    embedded double quotes survive the encoder untouched."""
    expr = '=IF(SUM(B3:B8)>10,"big","small")'
    gw = _gateway(compute={expr: "big"})
    _plan, log = _apply_one(FormulaWriteRequest.for_a1(f"{SID}!C1", expr), gw)
    assert gw.puts[0][1] == [[{"type": "formula", "text": expr}]]
    assert log.entries[0].formula["computed_value"] == "big"


def test_a_bad_function_name_evaluates_to_an_error_sentinel_and_is_flagged():
    expr = "=NOTAFUNC(B3)"
    gw = _gateway(compute={expr: "#NAME?"})
    _plan, log = _apply_one(FormulaWriteRequest.for_a1(f"{SID}!C1", expr), gw)
    rec = log.entries[0].formula
    assert rec["evaluated"] is True and rec["error_value"] is True
    assert rec["computed_value"] == "#NAME?"


def test_a_cross_tab_reference_by_title_is_recorded_with_larks_normalization():
    """Probe: a cross-tab reference works **by TITLE** and Lark quotes it
    (``=SUM(Other!A1:A2)`` → ``=SUM('Other'!A1:A2)``); a reference by **sheet_id** answers
    ``#REF!`` — the inverse of the A1 write-range convention."""
    sent = "=SUM(Other!A1:A2)"
    gw = _gateway(compute={sent: 30}, normalize={sent: "=SUM('Other'!A1:A2)"})
    _plan, log = _apply_one(FormulaWriteRequest.for_a1(f"{SID}!C1", sent), gw)
    rec = log.entries[0].formula
    assert rec["stored_expression"] == "=SUM('Other'!A1:A2)"
    assert rec["normalized"] is True
    assert rec["evaluated"] is True


def test_a_cross_tab_reference_by_sheet_id_records_the_ref_error():
    expr = "=SUM(yyuqI!A1:A2)"
    gw = _gateway(compute={expr: "#REF!"})
    _plan, log = _apply_one(FormulaWriteRequest.for_a1(f"{SID}!C1", expr), gw)
    assert log.entries[0].formula["error_value"] is True


# =========================================================================== #
# AC5 — the LOUD dry-run note for a '='-prefixed PLAIN string.                 #
# =========================================================================== #

def test_an_equals_prefixed_plain_string_gets_the_loud_dry_run_note():
    gw = _gateway(cells={f"{SID}!A1:A1": [["old"]]})
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1", [[SUM_EXPR]])], gw, TOKEN)
    note = plan.entries[0].preview_note

    assert note is not None, "a '='-prefixed plain string MUST be flagged at dry-run"
    assert note["kind"] == "equals-prefixed-plain-string"
    assert note["note"] == INERT_STRING_NOTE
    assert note["cells"] == [{"row": 0, "col": 0, "value": SUM_EXPR}]


def test_the_loud_note_text_says_exactly_what_will_happen():
    """AC5 asserted VERBATIM: the note names the outcome, the cause, and the fix."""
    assert INERT_STRING_NOTE == (
        "LOUD WARNING: this value starts with '=' but is a PLAIN STRING, so it will be "
        "stored as INERT TEXT, not an evaluating formula. Lark's values API has NO "
        "valueInputOption / USER_ENTERED mode (probed 2026-07-28: the query- and body-level "
        "variants are both answered code 0 and have zero effect), so no flag can make a "
        "plain string evaluate. To write a formula that EVALUATES use "
        "FormulaWriteRequest.for_a1(range, \"=SUM(...)\"), which sends the documented "
        "{\"type\":\"formula\",\"text\":\"=...\"} object form. If you really do want the "
        "literal text, this is already what you get — nothing else changes."
    )


def test_an_ordinary_value_gets_no_note():
    gw = _gateway(cells={f"{SID}!A1:A1": [["old"]]})
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1", [["new value"]])], gw, TOKEN)
    assert plan.entries[0].preview_note is None


@pytest.mark.parametrize("value", [21, 3.5, True, None, "total", "a=b", " =x"])
def test_no_note_for_values_that_do_not_start_with_equals(value):
    gw = _gateway(cells={f"{SID}!A1:A1": [["old"]]})
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1", [[value]])], gw, TOKEN)
    assert plan.entries[0].preview_note is None, value


def test_the_note_flags_an_equals_prefixed_string_that_is_not_a_formula():
    """Probe: ``"=not a formula"`` stores inert. The note fires on the '=' prefix alone —
    the library does not pretend to know which ``=``-strings Lark would parse."""
    gw = _gateway(cells={f"{SID}!A1:A1": [["old"]]})
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1", [["=not a formula"]])], gw, TOKEN)
    assert plan.entries[0].preview_note["cells"][0]["value"] == "=not a formula"


def test_the_note_reports_every_offending_cell_with_its_coordinates():
    gw = _gateway(cells={f"{SID}!A1:B2": [["a", "b"], ["c", "d"]]})
    plan = dry_run(
        [ValueWriteRequest.for_a1(f"{SID}!A1:B2", [["ok", "=SUM(A1:A2)"], ["=1+1", 5]])],
        gw, TOKEN)
    assert plan.entries[0].preview_note["cells"] == [
        {"row": 0, "col": 1, "value": "=SUM(A1:A2)"},
        {"row": 1, "col": 0, "value": "=1+1"},
    ]


def test_a_formula_request_never_gets_the_inert_string_note():
    """The note is for the TRAP, not for the fix — a real formula write must not warn."""
    gw = _gateway()
    plan = dry_run([FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR)], gw, TOKEN)
    assert plan.entries[0].preview_note["kind"] == "formula"


def test_the_note_rides_a_refused_entry_too():
    """An approval UX must see the warning even when the entry was refused."""
    gw = _gateway(cells={f"{SID}!A1:A1": [["old"]]})
    gw.raise_on_read[(f"{SID}!A1:A1", COMPUTED_RENDER_OPTION)] = LarkAPIError(
        "boom: Code: 90215", code=90215, msg="not found sheetId")
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1", [[SUM_EXPR]])], gw, TOKEN)
    assert plan.entries[0].outcome == "refused"
    assert plan.entries[0].preview_note["kind"] == "equals-prefixed-plain-string"


def test_the_note_also_fires_for_an_append_rows_with_values_request():
    """The trap is closed at the ONE preview seam, so every values-bearing family gets it
    — a future family cannot forget."""
    from larkdocio.sheets.write_apply import AppendRowsWithValues

    class _Geo(FormulaAwareGateway):
        def read_sheet_geometry(self, spreadsheet_token, sheet_id):
            return {"row_count": 10, "column_count": 3, "merges": []}

        def append_values(self, spreadsheet_token, a1_range, values, insert_data_option=None):
            return {"updates": {"updatedRows": len(values)}}

    gw = _Geo(revision=1, cells={})
    plan = dry_run([AppendRowsWithValues(f"{SID}!A1:B1", [["x", "=SUM(A1:A2)"]])], gw, TOKEN)
    assert plan.entries[0].preview_note["kind"] == "equals-prefixed-plain-string"


def test_the_helpers_behind_the_note_are_pure_and_directly_testable():
    assert equals_prefixed_cells([["a", "=b"], ["=c"]]) == [
        {"row": 0, "col": 1, "value": "=b"},
        {"row": 1, "col": 0, "value": "=c"},
    ]
    assert equals_prefixed_cells([["a"], [1, None]]) == []
    assert equals_prefixed_note([["=x"]])["note"] == INERT_STRING_NOTE
    assert equals_prefixed_note([["x"]]) is None


# =========================================================================== #
# The plain-value path's refusal now names the RIGHT request class.             #
# =========================================================================== #

def test_a_formula_object_inside_a_plain_value_request_is_told_to_use_formula_request():
    """Before LD-149 this said "use a RichCellWriteRequest" — wrong advice for a formula."""
    gw = _gateway(cells={f"{SID}!A1:A1": [["old"]]})
    plan = dry_run(
        [ValueWriteRequest.for_a1(f"{SID}!A1", [[encode_formula(SUM_EXPR)]])], gw, TOKEN)
    refusal = plan.entries[0].refusal
    assert refusal.reason == Refusal.RICH_CELL_TARGET
    assert "FormulaWriteRequest" in refusal.detail


def test_a_non_formula_structured_cell_still_points_at_the_rich_request():
    """Zero-drift on the pre-existing message for every non-formula structured cell."""
    gw = _gateway(cells={f"{SID}!A1:A1": [["old"]]})
    plan = dry_run(
        [ValueWriteRequest.for_a1(f"{SID}!A1", [[{"type": "url", "link": "x"}]])],
        gw, TOKEN)
    assert plan.entries[0].refusal.detail == (
        "proposed values contain a structured (rich) cell — use a RichCellWriteRequest")


# =========================================================================== #
# Merge interaction (probe: a formula into a merge ANCHOR works).               #
# =========================================================================== #

def test_a_formula_into_a_merge_anchor_is_allowed():
    gw = _gateway(cells={f"{SID}!E1:E1": [[None]]})
    merges = [{"start_row_index": 0, "end_row_index": 0,
               "start_column_index": 4, "end_column_index": 5}]
    plan = dry_run([FormulaWriteRequest.for_a1(f"{SID}!E1", SUM_EXPR)], gw, TOKEN,
                   merges=merges)
    assert plan.entries[0].outcome == "resolved"


def test_a_formula_into_a_merge_covered_cell_is_refused():
    gw = _gateway(cells={f"{SID}!F1:F1": [[None]]})
    merges = [{"start_row_index": 0, "end_row_index": 0,
               "start_column_index": 4, "end_column_index": 5}]
    plan = dry_run([FormulaWriteRequest.for_a1(f"{SID}!F1", SUM_EXPR)], gw, TOKEN,
                   merges=merges)
    assert plan.entries[0].refusal.reason == Refusal.MERGED_CELL_TARGET


# =========================================================================== #
# Unreadable-range classification (LD-131 parity) + LD-148 disposition parity.  #
# =========================================================================== #

def test_an_unknown_tab_at_plan_time_refuses_unknown_tab_with_a_did_you_mean():
    gw = _gateway(cells={})
    gw.raise_on_read[("Sheet1!C1:C1", EXPRESSION_RENDER_OPTION)] = LarkAPIError(
        "nope: Code: 90215", code=90215, msg="not found sheetId")
    plan = dry_run([FormulaWriteRequest.for_a1("Sheet1!C1", SUM_EXPR)], gw, TOKEN)
    refusal = plan.entries[0].refusal
    assert refusal.reason == Refusal.UNKNOWN_TAB
    assert "sheet_id" in refusal.detail and SID in refusal.detail


def test_a_vanished_tab_at_apply_time_refuses_tab_vanished():
    gw = _gateway()
    plan = dry_run([FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR)], gw, TOKEN)
    gw.raise_on_read[(f"{SID}!C1:C1", EXPRESSION_RENDER_OPTION)] = LarkAPIError(
        "gone: Code: 90215", code=90215, msg="not found sheetId")
    log = apply(plan, gw)
    assert gw.puts == []
    assert log.entries[0].refusal.reason == Refusal.TAB_VANISHED


def test_an_api_error_on_the_formula_write_is_an_entry_scoped_refusal():
    """LD-148 parity: the new family honours the disposition invariant."""
    gw = _gateway()
    plan = dry_run(
        [FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR),
         FormulaWriteRequest.for_a1(f"{SID}!C1", "=1+1")],
        gw, TOKEN)
    gw.raise_on_put = LarkAPIError("bad: Code: 90204", code=90204, msg="id not found")
    log = apply(plan, gw)

    assert len(log.entries) == len(plan.entries)
    assert log.entries[0].refusal.reason == Refusal.API_ERROR
    assert log.halt is None, "an entry-scoped error must not halt the batch"


def test_a_post_write_verification_failure_is_applied_unverified():
    """The computed read-back happens AFTER the write, so its failure must be recorded as
    ``applied-unverified`` (the change IS on the sheet) — never as "nothing landed"."""
    gw = _gateway()
    plan = dry_run([FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR)], gw, TOKEN)
    gw.raise_on_read[(f"{SID}!C1:C1", COMPUTED_RENDER_OPTION)] = LarkAPIError(
        "read died: <urlopen error timed out>")
    log = apply(plan, gw)

    assert gw.puts, "the write itself went through"
    entry = log.entries[0]
    assert entry.outcome == "applied-unverified"
    assert entry.is_applied is True and entry.is_verified is False
    assert log.halted is True


def test_a_client_seam_without_a_render_option_refuses_invalid_request_not_a_crash():
    """A third-party duck-typed seam whose ``read_values`` takes no
    ``value_render_option`` cannot serve a formula write — the plan REFUSES with an
    actionable typed reason instead of letting a ``TypeError`` escape ``dry_run``."""
    class _NoRenderOption(FormulaAwareGateway):
        def read_values(self, spreadsheet_token, a1_range):   # no render option
            return []

    gw = _NoRenderOption(revision=1)
    plan = dry_run([FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR)], gw, TOKEN)
    refusal = plan.entries[0].refusal
    assert refusal.reason == Refusal.INVALID_REQUEST
    assert "value_render_option" in refusal.detail


# =========================================================================== #
# The multi-select / comma interplay — the non-regression the AC calls for.     #
# =========================================================================== #

def test_a_comma_bearing_formula_is_not_treated_as_a_multi_select_value():
    """A formula expression is full of commas; the multi-select comma-join normalizer must
    not touch it, and the comma-in-label refusal must not fire on it."""
    from larkdocio.sheets.rich_encode import normalize_multi_select

    expr = '=IF(SUM(B3:B8)>10,"big","small")'
    req = FormulaWriteRequest.for_a1(f"{SID}!C1", expr)     # builds — no comma refusal
    assert req.values[0][0]["text"] == expr

    cell = req.values[0][0]
    assert normalize_multi_select(cell) == (), (
        "a formula cell is not a multi-select — it must normalize to no options")


def test_the_multi_select_comma_label_refusal_is_unchanged():
    from larkdocio.sheets.rich_encode import MultiSelectLabelError, encode_multi_select

    with pytest.raises(MultiSelectLabelError):
        encode_multi_select(["Red,Green"])


def test_render_cell_still_respects_the_digit_flank_guard_for_a_computed_number():
    """A formula's computed value can be a formatted number string containing commas; the
    LD-117 digit-flank guard must keep leaving it alone (non-regression)."""
    from larkdocio.sheets.render import render_cell

    assert render_cell("$1,234.56") == "$1,234.56"


# =========================================================================== #
# The decoder helpers.                                                          #
# =========================================================================== #

@pytest.mark.parametrize("cell,expected", [
    ({"type": "formula", "text": "=1+1"}, "=1+1"),
    ({"type": "formula", "text": ""}, None),
    ({"type": "url", "link": "x"}, None),
    ("=1+1", None),
    (None, None),
    (21, None),
    ([{"type": "formula", "text": "=1+1"}], None),
])
def test_formula_expression_decodes_only_the_object_form(cell, expected):
    assert formula_expression(cell) == expected
    assert is_formula_cell(cell) is (expected is not None)


# =========================================================================== #
# Registry wiring — the family registers ONCE and both dispatchers agree.       #
# =========================================================================== #

def test_the_formula_family_is_registered_in_the_ops_registry():
    from larkdocio.sheets.ops import OPS, classify, descriptor_for_entry

    (desc,) = [d for d in OPS if d.kind == "formula"]
    assert desc.write_kind == "formula"
    assert desc.entry_ops == ()
    assert FormulaWriteRequest in desc.request_type
    assert classify(FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR)) == "formula"

    gw = _gateway()
    plan = dry_run([FormulaWriteRequest.for_a1(f"{SID}!C1", SUM_EXPR)], gw, TOKEN)
    assert descriptor_for_entry(plan.entries[0]) is desc


def test_capabilities_projects_the_formula_family():
    from larkdocio.capabilities import capabilities

    ops = capabilities(full=True)["surfaces"]["sheets-write"]["operations"]
    (formula,) = [o for o in ops if o["name"] == "formula"]
    assert formula["request_types"] == ["FormulaWriteRequest"]
    assert formula["write_kind"] == "formula"


def test_the_public_package_exports_the_formula_surface():
    import larkdocio.sheets as sheets

    assert sheets.FormulaWriteRequest is FormulaWriteRequest
    assert "FormulaWriteRequest" in sheets.__all__


def test_an_empty_verification_read_back_is_reported_as_its_own_story():
    """Both legs answering nothing is NOT the inert-text signature — it says so, so the two
    can never be confused in an audit record."""
    rec = formula_record(expression=SUM_EXPR, stored_expression=[], computed_value=[])
    assert rec["evaluated"] is False
    assert "VERIFICATION EMPTY" in rec["detail"]
    assert "inert" not in rec["detail"].lower()
