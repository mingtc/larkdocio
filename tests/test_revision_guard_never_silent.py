"""LD-132 — the sheets staleness guard must NEVER be silently off (dogfood F7).

**The bug.** The Sheets value-write spec § D5 advertises a ``revision`` **compare-and-swap** as the sheets
staleness guard: cache ``metainfo.properties.revision`` at plan time, re-read it immediately
before each write, refuse a typed ``STALE_SHEET`` if it advanced. The dogfood session found
``read_revision()`` returning **``0``** on a live, edited spreadsheet (F7), and the seat's
**read-only** raw-API probe confirmed the sentinel is real and per-spreadsheet (the maintainer dogfood
sheet reads raw ``0``; the standing scratch sheet reads ``37`` — tokens recorded in the issue,
deliberately not in test code). On such a sheet the compare-and-swap compares ``0 == 0`` and
**silently no-ops** —
the advertised safety contract is off and a consumer would never know. Reproduced pre-fix:
the plan, the dry-run output and the apply-log carried **no** trace of the word "guard", and
both a value write and a **destructive row delete** were permitted with nothing said.

**The fix under test (the two-tier story, made explicit).**

* **Tier 1 — the ``revision`` compare-and-swap, when the anchor is available.** Every
  :class:`~larkdocio.sheets.plan.Plan` (and its dry-run output) carries an explicit
  ``revision_guard`` field: ``"active"`` on a nonzero anchor, ``"unavailable"`` when the
  plan-time revision is ``0`` / ``None`` — **with the WHY** in ``revision_guard_detail``.
  The marker is **derived from the plan's own revision inside ``Plan.__init__``**, so no code
  path — not even a future op family whose preview leg forgets — can produce a plan that
  lacks it (the structural never-silent guarantee below).
* **Tier 2 — the value precondition, always.** With the anchor unavailable the engine still
  performs its raw ``UnformattedValue`` before/after re-read and refuses
  ``PRECONDITION_MISMATCH``. Which entries that tier actually covers is stated **per entry**
  (``value_precondition``): ``"enforced"`` for a value / rich-cell entry, ``"none"`` for a
  dropdown-rule / structural / merge / tab entry — because claiming a second tier for an op
  that has no cell-value precondition would be the same class of lie LD-131 fixed.
* **Self-healing.** The cached ``0`` is not trusted as "equal forever": **any** nonzero
  advance before the write still refuses ``STALE_SHEET``, and the next plan built on the
  now-nonzero anchor marks the guard ``"active"`` by itself.

Both realities are covered by injected transports, so the fix is correct independently of
what the live arm shows: a sheet whose write **bumps** ``0 → 1`` (the API-created reality,
confirmed live in ``tests/test_live_sheets_revision_guard_gate.py``) **and** a sheet that
reports a **constant 0** despite writes (the UI-created / revision-0-despite-edits reality,
still maintainer-parked live).
"""
import json
from pathlib import Path

import pytest

from log_reading_apply import reading_the_log
from larkdocio import guide
from larkdocio.errors import LarkAPIError
from larkdocio.sheets.plan import _PLAN_TOKEN
from larkdocio.sheets.write_apply import (
    OPS,
    REVISION_GUARD_ACTIVE,
    REVISION_GUARD_UNAVAILABLE,
    VALUE_PRECONDITION_ENFORCED,
    VALUE_PRECONDITION_NONE,
    AddTab,
    ApplyLogEntry,
    DeleteRows,
    DropdownRuleWriteRequest,
    FormulaWriteRequest,
    MergeCells,
    Plan,
    PlanEntry,
    Refusal,
    CellStyle,
    FreezePanes,
    RichCellWriteRequest,
    StyleWriteRequest,
    SetRowProperties,
    ValueWriteRequest,
    apply,
    dry_run,
    revision_guard_semantics,
    revision_guard_status,
)
apply = reading_the_log(apply)
from larkdocio.sheets.write_client import SheetsWriteClient
from larkdocio.sheets.write_range import parse_write_range

TOKEN = "shtLD132TOKEN"
SID = "s1"

# The maintainer dogfood sheet's real, READ-ONLY probed fact (progress.md 2026-07-27): raw
# `metainfo.properties.revision` == 0; the standing scratch sheet reads 37. These are the two
# realities this file pins — no test here addresses any live spreadsheet at all (the fakes
# below are the only "sheets" involved).
DOGFOOD_REVISION = 0
SCRATCH_REVISION = 37


# --------------------------------------------------------------------------- #
# The client seam — one duck-typed stand-in covering EVERY write family, so     #
# the never-silent guarantee can be proven registry-driven over ``OPS``.        #
#                                                                              #
# ``bump_on_write`` models the two realities: True = a write bumps `revision`   #
# +1 (the API-created sheet — LD-107 / the live arm), False = the revision is a #
# CONSTANT sentinel that never moves (the dogfood sheet's F7 reality).          #
# --------------------------------------------------------------------------- #

class FakeRevisionGateway:
    def __init__(self, *, revision, values=None, bump_on_write=True, tabs=None,
                 row_count=10, column_count=6):
        self.revision = revision
        self.values = dict(values or {})
        self.bump_on_write = bump_on_write
        self.tabs = list(tabs or [{"sheet_id": SID, "title": "Sheet1", "index": 0,
                                   "row_count": row_count, "column_count": column_count,
                                   "merges": []}])
        self.row_count = row_count
        self.column_count = column_count
        self.puts = []
        self.dv_sets = []
        self.calls = []
        self.external_bumps = {}     # {read_revision_call_n: delta}
        self._rev_reads = 0

    # -- reads -------------------------------------------------------------- #
    def read_revision(self, spreadsheet_token):
        self._rev_reads += 1
        delta = self.external_bumps.pop(self._rev_reads, 0)
        if delta:
            # `or 0` so a *missing* anchor (None) can still be bumped into existence by an
            # external writer — the None → nonzero race.
            self.revision = (self.revision or 0) + delta
        return self.revision

    def read_values(self, spreadsheet_token, a1_range,
                    value_render_option="UnformattedValue"):
        # LD-149: the formula family reads by render mode (Formula / UnformattedValue). This
        # fake is a staleness probe, not an evaluator, so every mode answers the stored value.
        v = self.values.get(a1_range)
        if isinstance(v, Exception):
            raise v
        return [] if v is None else v

    def read_sheet_geometry(self, spreadsheet_token, sheet_id):
        return {"row_count": self.row_count, "column_count": self.column_count, "merges": []}

    def query_tabs(self, spreadsheet_token):
        return [dict(t) for t in self.tabs]

    # -- writes (each bumps `revision` +1 unless this is a constant-0 sheet) -- #
    def _wrote(self):
        if self.bump_on_write:
            self.revision = (self.revision or 0) + 1

    def put_values(self, spreadsheet_token, a1_range, values):
        self.puts.append((a1_range, values))
        self.values[a1_range] = values
        self._wrote()
        return {"revision": None}     # force the metainfo fallback (spike Q4)

    def set_data_validation(self, spreadsheet_token, a1_range, rule):
        self.dv_sets.append((a1_range, rule))
        self._wrote()
        return {}

    def insert_dimension_range(self, spreadsheet_token, sheet_id, major_dimension, start_index, end_index, inherit_style=None):
        self.calls.append(("insert", major_dimension, start_index, end_index))
        self._wrote()
        return {}

    def delete_dimension_range(self, spreadsheet_token, sheet_id, major_dimension, start_index, end_index):
        self.calls.append(("delete", major_dimension, start_index, end_index))
        self._wrote()
        return {"delCount": end_index - start_index + 1}

    def append_dimension(self, spreadsheet_token, sheet_id, major_dimension, length):
        self.calls.append(("append-dim", major_dimension, length))
        self._wrote()
        return {"addCount": length}

    def append_values(self, spreadsheet_token, a1_range, values, insert_data_option=None):
        self.calls.append(("append-values", a1_range))
        self._wrote()
        return {"updates": {"updatedRows": len(values)}}

    def set_dimension_properties(self, spreadsheet_token, sheet_id, major_dimension, start_index, end_index,
                                 properties):
        self.calls.append(("dimension-property", major_dimension, start_index, end_index, dict(properties)))
        self._wrote()
        return {}                     # the reply carries neither a count nor a revision

    def read_frozen_panes(self, spreadsheet_token, sheet_id=None):
        """The LD-186 frozen read — a READ seam (it mutates nothing), so it is deliberately
        NOT routed through ``_wrote``. It answers the grid the freeze bounds-check needs and
        the frozen counts the freeze verification leg records."""
        self.calls.append(("read_frozen_panes", sheet_id))
        state = {"revision": self.revision,
                 "sheets": {SID: {"frozen_rows": 0, "frozen_cols": 0, "row_count": 200,
                                  "column_count": 20, "title": "Sheet1", "index": 0,
                                  "source": "metainfo"}}}
        return state if sheet_id is None else state["sheets"].get(sheet_id)

    def merge_cells(self, spreadsheet_token, a1_range, merge_type="MERGE_ALL"):
        self.calls.append(("merge", a1_range))
        self._wrote()
        return {"spreadsheetToken": spreadsheet_token}

    def unmerge_cells(self, spreadsheet_token, a1_range):
        self.calls.append(("unmerge", a1_range))
        self._wrote()
        return {"spreadsheetToken": spreadsheet_token}

    def batch_update_sheets(self, spreadsheet_token, requests):
        self.calls.append(("batch-update-sheets", requests))
        self._wrote()
        replies = []
        for req in requests:
            if "addSheet" in req:
                replies.append({"addSheet": {"properties": {"sheetId": "newSID"}}})
            elif "copySheet" in req:
                replies.append({"copySheet": {"properties": {"sheetId": "copySID"}}})
            else:
                replies.append({"deleteSheet": {"result": True}})
        return {"replies": replies}


def _gw(revision=DOGFOOD_REVISION, **kw):
    values = kw.pop("values", None) or {f"{SID}!A1:A1": [["old"]], f"{SID}!A1:F1": [["x"] * 6]}
    return FakeRevisionGateway(revision=revision, values=values, **kw)


def _value_req(a1=f"{SID}!A1:A1", values=None):
    return ValueWriteRequest.for_a1(a1, values or [["new"]])


# One representative request per registered op family, keyed by the registry's ``kind``
# so a NEW family added to ``OPS`` without a probe here reddens the structural test.
def _request_for_kind(kind):
    return {
        "value": _value_req(),
        # LD-149 — the formula family; its tier-2 precondition is the EXPRESSION.
        "formula": FormulaWriteRequest.for_a1(f"{SID}!A1:A1", "=SUM(B1:B2)"),
        "dropdown": DropdownRuleWriteRequest.list_rule(f"{SID}!A1:A1", ["Red", "Green"]),
        "structural": DeleteRows(sheet_id=SID, first=2, last=2),
        # LD-185 — the dimension-property family (row height / column width / hide-show).
        "dimension-property": SetRowProperties(SID, first=2, last=2, fixed_size=60),
        # LD-186 — the freeze-panes family (view state on the shipped batch endpoint).
        "freeze-panes": FreezePanes(SID, rows=2),
        # LD-188 — the cell-style family. It has NO tier-2 value precondition (style is
        # readable only through the export), so tier 1 is the whole guard — which is exactly
        # why it belongs in this structural sweep.
        "style": StyleWriteRequest(f"{SID}!A1:A1", CellStyle(bold=True)),
        "merge": MergeCells(a1_range=f"{SID}!A1:C1"),
        "tab": AddTab(title="LD132-tab"),
    }[kind]


# =========================================================================== #
# AC1 — the guard is NEVER silently off: the plan + the dry-run output carry an #
# explicit revision_guard marker, with the WHY when it is unavailable.          #
# =========================================================================== #

def test_revision_zero_plan_marks_the_guard_unavailable():
    """The F7 sheet: a plan-time revision of 0 means the compare-and-swap cannot see an
    advance — the plan says so out loud instead of pretending to be guarded."""
    gw = _gw(revision=0)
    plan = dry_run([_value_req()], gw, TOKEN)

    assert plan.revision == 0
    assert plan.revision_guard == REVISION_GUARD_UNAVAILABLE


def test_revision_zero_dry_run_output_carries_the_unavailable_marker():
    """AC1: consumer-visible in the JSON-serializable dry-run output, not only on the object."""
    gw = _gw(revision=0)
    d = dry_run([_value_req()], gw, TOKEN).to_dict()

    assert d["revision_guard"] == REVISION_GUARD_UNAVAILABLE
    assert json.loads(json.dumps(d)) == d, "the marker must be JSON-serializable"


def test_the_unavailable_marker_says_why():
    """A marker with no WHY is a riddle. The detail names the observed anchor value, that
    tier 1 is inert, and that tier 2 (the value precondition) still enforces."""
    gw = _gw(revision=0)
    plan = dry_run([_value_req()], gw, TOKEN)
    why = plan.revision_guard_detail.lower()

    assert plan.revision_guard_detail.strip(), "the unavailable marker must carry a WHY"
    assert "0" in plan.revision_guard_detail
    assert "revision" in why
    assert "precondition" in why, "the WHY must name the second line of defense"
    assert plan.to_dict()["revision_guard_detail"] == plan.revision_guard_detail


def test_revision_none_marks_the_guard_unavailable():
    """A metainfo read that yields no revision at all is equally unguarded — and equally
    marked (never silently treated as a healthy anchor)."""
    gw = _gw(revision=None)
    plan = dry_run([_value_req()], gw, TOKEN)

    assert plan.revision is None
    assert plan.revision_guard == REVISION_GUARD_UNAVAILABLE
    assert "none" in plan.revision_guard_detail.lower()


def test_metainfo_payload_without_a_revision_field_marks_the_guard_unavailable():
    """End-to-end through the REAL client seam (injected transport): a ``metainfo`` payload
    whose ``properties`` carries no ``revision`` → ``read_revision`` is ``None`` → the plan
    marks the guard unavailable. API drift cannot silently disable the guard."""
    class _Resp:
        def __init__(self, payload):
            self._b = json.dumps(payload).encode()

        def read(self):
            return self._b

    payloads = [
        {"code": 0, "data": {"properties": {"title": "no-revision-here"}}},   # metainfo
        {"code": 0, "data": {"valueRange": {"values": [["old"]]}}},            # before-read
        # LD-150 / dogfood F9: a resolved value entry also reads its target under
        # `valueRenderOption=Formula`, so the plan can disclose a LIVE FORMULA it would
        # destroy (the `before` above is UnformattedValue, under which a formula answers its
        # computed scalar and is invisible). Same values here ⇒ no formula ⇒ no note.
        {"code": 0, "data": {"valueRange": {"values": [["old"]]}}},            # formula leg
    ]
    seen = []

    def opener(req, timeout=30):
        seen.append(req.full_url)
        return _Resp(payloads[len(seen) - 1])

    client = SheetsWriteClient(
        "app", "secret", "larksuite.com",
        urlopen=opener, token_fetcher=lambda *a, **k: "t-test",
    )
    plan = dry_run([_value_req()], client, TOKEN)

    assert plan.revision is None
    assert plan.revision_guard == REVISION_GUARD_UNAVAILABLE


@pytest.mark.parametrize("sentinel", [0, None, "0", " 0 ", ""])
def test_every_unavailable_anchor_shape_marks_unavailable(sentinel):
    """The sentinel matrix — an int ``0``, ``None``, and the string shapes an API drift could
    hand back. A ``"0"`` string would compare ``!=`` to a later ``"1"`` and *look* guarded,
    so it is classified unavailable rather than trusted."""
    assert revision_guard_status(sentinel) == REVISION_GUARD_UNAVAILABLE


@pytest.mark.parametrize("healthy", [1, 37, 9999, "37"])
def test_a_nonzero_anchor_is_active(healthy):
    assert revision_guard_status(healthy) == REVISION_GUARD_ACTIVE


def test_healthy_revision_plan_marks_the_guard_active():
    """The standing scratch sheet's reality (revision 37): tier 1 IS available, and the plan
    says ``active`` — the marker is not a blanket disclaimer."""
    gw = _gw(revision=SCRATCH_REVISION)
    plan = dry_run([_value_req()], gw, TOKEN)

    assert plan.revision_guard == REVISION_GUARD_ACTIVE
    assert plan.to_dict()["revision_guard"] == REVISION_GUARD_ACTIVE
    assert "37" in plan.revision_guard_detail


def test_a_healthy_plan_never_claims_the_guard_is_unavailable():
    gw = _gw(revision=SCRATCH_REVISION)
    out = dry_run([_value_req()], gw, TOKEN).to_json()

    assert REVISION_GUARD_UNAVAILABLE not in out


def test_plan_output_makes_the_two_tier_story_explicit():
    """The two tiers are named in the plan output itself, both ways round, so a consumer
    reading only the JSON knows exactly which guard is holding."""
    unavailable = dry_run([_value_req()], _gw(revision=0), TOKEN).to_dict()
    active = dry_run([_value_req()], _gw(revision=SCRATCH_REVISION), TOKEN).to_dict()

    for out, tier1 in ((unavailable, REVISION_GUARD_UNAVAILABLE),
                       (active, REVISION_GUARD_ACTIVE)):
        tiers = out["revision_guard_tiers"]
        assert tiers["tier1_revision_compare_and_swap"] == tier1
        assert "precondition" in tiers["tier2_value_precondition"].lower()


def test_the_marker_round_trips_through_json():
    plan = dry_run([_value_req()], _gw(revision=0), TOKEN)
    restored = json.loads(plan.to_json())

    assert restored["revision_guard"] == REVISION_GUARD_UNAVAILABLE
    assert restored["revision_guard_detail"] == plan.revision_guard_detail
    assert restored["entries"][0]["revision_guard"] == REVISION_GUARD_UNAVAILABLE


def test_plan_repr_names_the_guard_status():
    """``print(plan)`` is a consumer's first move — the status is visible there too."""
    assert REVISION_GUARD_UNAVAILABLE in repr(dry_run([_value_req()], _gw(revision=0), TOKEN))
    assert REVISION_GUARD_ACTIVE in repr(
        dry_run([_value_req()], _gw(revision=SCRATCH_REVISION), TOKEN))


def test_revision_guard_semantics_is_the_one_source_of_the_marker():
    """One helper produces status + WHY + tiers, so the plan, the log and the docs cannot
    drift apart."""
    sem = revision_guard_semantics(0)

    assert sem["status"] == REVISION_GUARD_UNAVAILABLE
    assert sem["detail"].strip()
    assert sem["tiers"]["tier1_revision_compare_and_swap"] == REVISION_GUARD_UNAVAILABLE
    assert json.loads(json.dumps(sem)) == sem


# =========================================================================== #
# AC2 — with tier 1 unavailable the VALUE PRECONDITION still enforces, and the  #
# plan says per entry which entries that tier actually covers.                  #
# =========================================================================== #

def test_value_drift_on_a_revision_zero_sheet_still_refuses_precondition_mismatch():
    """AC2's core case: the anchor is inert (0 == 0), so tier 2 is the only thing between a
    concurrent edit and a lost update — and it holds, with NO write."""
    gw = _gw(revision=0)
    plan = dry_run([_value_req()], gw, TOKEN)
    gw.values[f"{SID}!A1:A1"] = [["SOMEONE-ELSE-EDITED-THIS"]]   # external value drift

    log = apply(plan, gw)

    assert gw.puts == [], "tier 2 must refuse the write on a revision-0 sheet"
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason == Refusal.PRECONDITION_MISMATCH


def test_rich_cell_drift_on_a_revision_zero_sheet_still_refuses():
    gw = _gw(revision=0, values={f"{SID}!B2:B2": [["old"]]})
    req = RichCellWriteRequest.hyperlink(f"{SID}!B2:B2", "https://example.com", text="link")
    plan = dry_run([req], gw, TOKEN)
    gw.values[f"{SID}!B2:B2"] = [["drifted"]]

    log = apply(plan, gw)

    assert gw.puts == []
    assert log.entries[0].refusal.reason == Refusal.PRECONDITION_MISMATCH


def test_a_clean_value_write_on_a_revision_zero_sheet_still_applies():
    """The marker is a disclosure, NOT a refusal (the F7 'refuse to plan' alternative is out
    of scope): a legitimate write to a revision-0 sheet still goes through."""
    gw = _gw(revision=0)
    log = apply(dry_run([_value_req()], gw, TOKEN), gw)

    assert gw.puts == [(f"{SID}!A1:A1", [["new"]])]
    assert log.entries[0].is_applied


def test_each_entry_names_the_tier_two_that_covers_it():
    """Per-entry, not global: a value / rich entry IS covered by the value precondition; a
    dropdown-rule / structural / merge / tab entry has NO cell-value precondition and the
    plan says ``none`` rather than implying a second tier it does not have."""
    gw = _gw(revision=0)
    plan = dry_run([
        _value_req(),
        RichCellWriteRequest.hyperlink(f"{SID}!B2:B2", "https://example.com"),
        DropdownRuleWriteRequest.list_rule(f"{SID}!C3:C3", ["a", "b"]),
        DeleteRows(sheet_id=SID, first=2, last=2),
        MergeCells(a1_range=f"{SID}!A1:C1"),
        AddTab(title="LD132-tab"),
    ], gw, TOKEN)

    got = [e.value_precondition for e in plan.entries]
    assert got == [
        VALUE_PRECONDITION_ENFORCED,   # value
        VALUE_PRECONDITION_ENFORCED,   # rich cell
        VALUE_PRECONDITION_NONE,       # dropdown rule — no before value
        VALUE_PRECONDITION_NONE,       # structural delete — geometry, not a cell value
        VALUE_PRECONDITION_NONE,       # merge
        VALUE_PRECONDITION_NONE,       # tab
    ]
    assert [e["value_precondition"] for e in plan.to_dict()["entries"]] == got


def test_an_unguarded_structural_delete_is_disclosed_not_hidden():
    """The sharpest edge of the bug: on a revision-0 sheet a DESTRUCTIVE row delete has tier
    1 inert AND no tier 2 at all. The plan discloses both facts — the entry's
    ``value_precondition`` is ``none`` and the plan's WHY warns about exactly that class."""
    gw = _gw(revision=0)
    plan = dry_run([DeleteRows(sheet_id=SID, first=2, last=2)], gw, TOKEN)
    (entry,) = plan.entries

    assert plan.revision_guard == REVISION_GUARD_UNAVAILABLE
    assert entry.revision_guard == REVISION_GUARD_UNAVAILABLE
    assert entry.value_precondition == VALUE_PRECONDITION_NONE
    assert "no second tier" in plan.revision_guard_detail.lower()


# =========================================================================== #
# Self-healing — the cached 0 is never trusted as "equal forever".              #
# =========================================================================== #

def test_zero_to_one_advance_before_the_write_still_refuses_stale_sheet():
    """The API-created reality (0 → 1 on the first write, confirmed live): a plan cached at
    revision 0 still refuses ``STALE_SHEET`` when the anchor advances to 1 before its write.
    'Unavailable' means "cannot see an advance FROM 0 yet", never "compare disabled"."""
    gw = _gw(revision=0)
    plan = dry_run([_value_req()], gw, TOKEN)
    assert plan.revision_guard == REVISION_GUARD_UNAVAILABLE
    gw.external_bumps = {gw._rev_reads + 1: 1}    # someone writes → 0 → 1

    log = apply(plan, gw)

    assert gw.puts == [], "a 0 → 1 advance must still refuse (no write)"
    (entry,) = log.entries
    assert entry.outcome == "stale"
    assert entry.refusal.reason == Refusal.STALE_SHEET
    assert "0 -> 1" in entry.refusal.detail


def test_none_to_nonzero_advance_before_the_write_still_refuses_stale_sheet():
    gw = _gw(revision=None)
    plan = dry_run([_value_req()], gw, TOKEN)
    gw.revision = 5                                # the anchor appears mid-flight

    log = apply(plan, gw)

    assert gw.puts == []
    assert log.entries[0].refusal.reason == Refusal.STALE_SHEET


def test_the_guard_self_activates_once_the_anchor_is_nonzero():
    """Step 4 of the live arm, offline: the sheet's first write moved 0 → 1, so the NEXT plan
    is built on a nonzero anchor and marks itself ``active`` with no consumer action."""
    gw = _gw(revision=0)
    apply(dry_run([_value_req()], gw, TOKEN), gw)          # the first write: 0 → 1
    assert gw.revision == 1

    plan2 = dry_run([_value_req(values=[["newer"]])], gw, TOKEN)

    assert plan2.revision == 1
    assert plan2.revision_guard == REVISION_GUARD_ACTIVE


def test_a_constant_zero_sentinel_sheet_stays_marked_forever():
    """The other reality (a sheet that reports 0 despite writes — the maintainer-parked variant):
    the anchor never becomes meaningful, so EVERY plan against it is marked unavailable and
    tier 2 is the permanent contract. No silent drift into a false ``active``."""
    gw = _gw(revision=0, bump_on_write=False)
    apply(dry_run([_value_req()], gw, TOKEN), gw)
    assert gw.revision == 0, "this double models the constant-0 sentinel"

    plan2 = dry_run([_value_req(values=[["newer"]])], gw, TOKEN)

    assert plan2.revision_guard == REVISION_GUARD_UNAVAILABLE
    assert plan2.entries[0].value_precondition == VALUE_PRECONDITION_ENFORCED


def test_a_healthy_anchor_that_does_not_move_applies():
    gw = _gw(revision=37)
    log = apply(dry_run([_value_req()], gw, TOKEN), gw)

    assert log.entries[0].is_applied
    assert gw.puts


def test_a_healthy_anchor_that_advances_refuses_stale_sheet():
    gw = _gw(revision=37)
    plan = dry_run([_value_req()], gw, TOKEN)
    gw.external_bumps = {gw._rev_reads + 1: 1}    # 37 → 38

    log = apply(plan, gw)

    assert gw.puts == []
    assert log.entries[0].refusal.reason == Refusal.STALE_SHEET


# =========================================================================== #
# The apply-log — the bug report's third silent surface.                        #
# =========================================================================== #

def test_apply_log_entries_record_the_plan_time_guard_status():
    """Pre-fix, an applied entry on a revision-0 sheet was indistinguishable from a fully
    guarded write. Every apply-log entry now carries the plan-time tier-1 status."""
    gw = _gw(revision=0)
    log = apply(dry_run([_value_req()], gw, TOKEN), gw)
    assert [e.revision_guard for e in log.entries] == [REVISION_GUARD_UNAVAILABLE]
    assert log.to_dict()["entries"][0]["revision_guard"] == REVISION_GUARD_UNAVAILABLE

    healthy = _gw(revision=37)
    healthy_log = apply(dry_run([_value_req()], healthy, TOKEN), healthy)
    assert [e.revision_guard for e in healthy_log.entries] == [REVISION_GUARD_ACTIVE]


def test_every_apply_log_entry_of_a_mixed_batch_carries_the_status():
    """1:1 with the plan, every outcome (applied / refused / stale) — no entry is silent."""
    gw = _gw(revision=0, values={f"{SID}!A1:A1": [["old"]],
                                 f"{SID}!B2:B2": LarkAPIError("unreadable range")})
    plan = dry_run([_value_req(), _value_req(a1=f"{SID}!B2:B2")], gw, TOKEN)
    log = apply(plan, gw)

    assert len(log.entries) == 2
    assert all(e.revision_guard == REVISION_GUARD_UNAVAILABLE for e in log.entries)


def test_apply_log_entry_marker_round_trips_through_json():
    entry = ApplyLogEntry.applied(
        target=parse_write_range(f"{SID}!A1:A1"), before=[["a"]], after=[["b"]], revision=0,
    ).with_revision_guard(REVISION_GUARD_UNAVAILABLE)
    d = entry.to_dict()

    assert json.loads(json.dumps(d)) == d
    assert ApplyLogEntry.from_dict(d) == entry
    assert ApplyLogEntry.from_dict(d).revision_guard == REVISION_GUARD_UNAVAILABLE


# =========================================================================== #
# STRUCTURAL never-silent — no code path can produce a plan lacking the marker. #
# =========================================================================== #

def test_every_registered_op_family_yields_a_marked_plan():
    """Registry-driven over ``OPS`` (the ONE registration seam): every op family's plan —
    and every entry in it — carries the marker. A family added to ``OPS`` without a probe
    here reddens this test, so the guarantee cannot rot as families are added."""
    for desc in OPS:
        gw = _gw(revision=0)
        plan = dry_run([_request_for_kind(desc.kind)], gw, TOKEN)

        assert plan.revision_guard == REVISION_GUARD_UNAVAILABLE, desc.kind
        assert plan.to_dict()["revision_guard"] == REVISION_GUARD_UNAVAILABLE, desc.kind
        for entry in plan.entries:
            assert entry.revision_guard == REVISION_GUARD_UNAVAILABLE, desc.kind
            assert entry.value_precondition in (
                VALUE_PRECONDITION_ENFORCED, VALUE_PRECONDITION_NONE), desc.kind


def test_a_plan_built_from_unmarked_entries_is_stamped_at_construction():
    """The structural guarantee: ``Plan.__init__`` DERIVES the marker from its own revision
    and stamps every entry, so a preview leg that forgets (a future family, a hand-built
    entry) still cannot yield a silent plan. Reaching for the private construction token is
    deliberate here — it is the only way to prove the guarantee holds at the seam every
    plan must pass through."""
    bare = PlanEntry.resolved(target=parse_write_range(f"{SID}!A1:A1"),
                              before=[["a"]], after=[["b"]])
    assert bare.revision_guard is None, "a loose entry is not yet part of any plan"

    plan = Plan([bare], revision=0, spreadsheet_token=TOKEN, _token=_PLAN_TOKEN)

    assert plan.entries[0].revision_guard == REVISION_GUARD_UNAVAILABLE
    assert plan.revision_guard == REVISION_GUARD_UNAVAILABLE


@pytest.mark.parametrize("revision", [0, None, 1, 37, "0", "37"])
def test_no_plan_can_exist_without_a_status_and_a_why(revision):
    plan = Plan([], revision=revision, spreadsheet_token=TOKEN, _token=_PLAN_TOKEN)
    out = plan.to_dict()

    assert plan.revision_guard in (REVISION_GUARD_ACTIVE, REVISION_GUARD_UNAVAILABLE)
    assert plan.revision_guard_detail.strip()
    assert out["revision_guard"] == plan.revision_guard
    assert out["revision_guard_detail"] == plan.revision_guard_detail
    assert out["revision_guard_tiers"]["tier1_revision_compare_and_swap"] == plan.revision_guard


def test_the_guard_status_is_derived_and_cannot_be_overridden():
    """Derived, not stored: there is no writable ``revision_guard`` slot to set to a
    comfortable lie."""
    plan = Plan([], revision=0, spreadsheet_token=TOKEN, _token=_PLAN_TOKEN)

    with pytest.raises(AttributeError):
        plan.revision_guard = REVISION_GUARD_ACTIVE


def test_two_spreadsheets_in_one_run_carry_independent_markers():
    """Not a global / process-wide flag: the anchor is a property of ONE spreadsheet, so a
    revision-0 sheet and a healthy sheet planned in the same run mark independently (the
    per-target amplifier row — ``dry_run`` is per-spreadsheet by construction)."""
    sick = _gw(revision=0)
    healthy = _gw(revision=37)

    plan_sick = dry_run([_value_req()], sick, "shtSICK")
    plan_healthy = dry_run([_value_req()], healthy, "shtXHOPWOY")

    assert plan_sick.revision_guard == REVISION_GUARD_UNAVAILABLE
    assert plan_healthy.revision_guard == REVISION_GUARD_ACTIVE
    assert plan_sick.spreadsheet_token == "shtSICK"
    assert plan_healthy.spreadsheet_token == "shtXHOPWOY"


# =========================================================================== #
# The F7 scenario, end to end — the exact pre-fix silence, now impossible.      #
# =========================================================================== #

def test_the_f7_dogfood_scenario_is_no_longer_silent():
    """The reproduction from the bug report: plan + apply a value write AND a destructive row
    delete against a sheet whose revision reads a constant 0. Pre-fix the whole flow —
    plan, dry-run output, apply-log — contained no trace of the guard's state (probed:
    ``"guard" in json.dumps(plan.to_dict()) -> False``); every surface now carries it."""
    gw = _gw(revision=DOGFOOD_REVISION, bump_on_write=False)
    plan = dry_run([_value_req(), DeleteRows(sheet_id=SID, first=2, last=2)], gw, TOKEN)

    out = json.dumps(plan.to_dict())
    assert "revision_guard" in out
    assert REVISION_GUARD_UNAVAILABLE in out

    log = apply(plan, gw)
    assert all(e.revision_guard == REVISION_GUARD_UNAVAILABLE for e in log.entries)
    assert "revision_guard" in log.to_json()


# =========================================================================== #
# AC4 (docs, drift-guarded) — SHEETS.md tells the two-tier story honestly.      #
# =========================================================================== #

_SHEETS_MD = Path(__file__).resolve().parents[1] / "SHEETS.md"


def _staleness_row() -> str:
    for line in _SHEETS_MD.read_text(encoding="utf-8").splitlines():
        if line.startswith("| STALE_SHEET compare-and-swap guard "):
            return line
    raise AssertionError("SHEETS.md has no STALE_SHEET compare-and-swap guard row")


def test_sheets_md_staleness_row_documents_the_two_tier_story():
    row = _staleness_row().lower()

    assert "revision_guard" in row, "the row must name the consumer-visible marker"
    assert "unavailable" in row
    assert "tier 1" in row and "tier 2" in row
    assert "revision-0" in row or "revision 0" in row
    assert "ld-132" in row, "the row must cite the issue that shipped the two-tier story"


def test_capabilities_stale_sheet_contract_states_the_two_tiers():
    """``capabilities()`` is the machine-readable contract a consumer reads before trusting
    the guard — it must not keep advertising an unconditional compare-and-swap."""
    from larkdocio import capabilities

    summary = capabilities(full=True)["safety_contracts"]["STALE_SHEET"]["summary"].lower()

    assert "unavailable" in summary
    assert "precondition" in summary


# =========================================================================== #
# AC4 (docs, drift-guarded) — the SHIPPED consumer guide (`larkdocio.guide()`,  #
# packaged IN THE WHEEL) tells the same two-tier story.                         #
#                                                                              #
# The existing guide↔capabilities() guard (tests/test_guide.py) is **id-based** #
# — it checks that the guide NAMES the `STALE_SHEET` contract, not what it SAYS #
# about it — so the pre-fix prose ("the revision is cached at plan time and     #
# re-read before EACH write", i.e. unconditionally) could keep shipping in      #
# every vendored wheel with nothing red. These are CONTENT-level guards: the    #
# needles are DERIVED FROM CODE (the serialized field names + every status the  #
# engine can actually emit), the two regions that describe the guard must carry #
# them, and no block anywhere in the guide may describe the compare-and-swap    #
# mechanism without disclosing that its anchor may be unavailable.              #
# =========================================================================== #

def _md_blocks(text: str) -> list:
    """``text`` split into prose blocks — one per table row, per **top-level** bullet (with
    its continuation lines and its nested sub-bullets) and per blank-line-separated
    paragraph; fenced code is skipped. Block granularity is what makes "this claim carries
    its qualifier" checkable: a needle somewhere else in the document does not excuse an
    unqualified sentence here."""
    blocks: list = []
    buf: list = []
    in_fence = False

    def flush():
        if buf:
            blocks.append("\n".join(buf))
            buf.clear()

    for line in text.splitlines():
        s = line.strip()
        if s.startswith("```"):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not s:
            flush()
            continue
        if s.startswith("|"):
            flush()
            blocks.append(line)
            continue
        if line.startswith(("- ", "* ")):      # a TOP-LEVEL bullet (indented ⇒ a sub-bullet,
            flush()                            # which stays part of its parent's block)
        buf.append(line)
    flush()
    return blocks


def _staleness_vocabulary() -> dict:
    """The needles a doc region MUST carry — **derived from the engine**, never hand-typed:
    the serialized names of the two disclosure fields (found by looking for the keys whose
    values ARE the emitted statuses) plus every status / per-entry value the engine can
    actually produce. Rename a field or add a status in code and this vocabulary changes, so
    the guide's prose has to follow or redden."""
    gw = _gw(revision=DOGFOOD_REVISION)
    plan = dry_run([_value_req(), DeleteRows(sheet_id=SID, first=2, last=2)], gw, TOKEN)
    out = plan.to_dict()

    statuses = {revision_guard_status(DOGFOOD_REVISION),
                revision_guard_status(SCRATCH_REVISION)}
    tier2_values = {e.value_precondition for e in plan.entries}
    assert statuses == {REVISION_GUARD_ACTIVE, REVISION_GUARD_UNAVAILABLE}
    assert tier2_values == {VALUE_PRECONDITION_ENFORCED, VALUE_PRECONDITION_NONE}

    marker_fields = sorted(k for k, v in out.items() if isinstance(v, str) and v in statuses)
    entry = out["entries"][0]
    tier2_fields = sorted(k for k, v in entry.items()
                          if isinstance(v, str) and v in tier2_values and k not in marker_fields)
    assert len(marker_fields) == 1, f"expected ONE plan-level marker field, got {marker_fields}"
    assert len(tier2_fields) == 1, f"expected ONE per-entry tier-2 field, got {tier2_fields}"

    return {
        "fields": (marker_fields[0], tier2_fields[0]),
        "statuses": tuple(sorted(statuses)),
        "tier2_values": tuple(sorted(tier2_values)),
    }


def _missing_staleness_needles(region: str) -> list:
    """The code-derived needles a region fails to name (empty ⇒ the region tells the whole
    two-tier story in the engine's own vocabulary). THE checker — reused by the live guards
    AND by the red-then-green bite test, so the check that guards is the check that bites."""
    vocab = _staleness_vocabulary()
    low = region.lower()
    needles = [f"`{n}`" for n in (*vocab["fields"], *vocab["statuses"], *vocab["tier2_values"])]
    return [n for n in needles if n not in low]


def _unconditional_compare_and_swap_blocks(text: str) -> list:
    """Blocks that DESCRIBE the mechanism (they name the compare-and-swap AND the ``revision``
    anchor it compares) yet never disclose that the anchor may be unavailable — exactly the
    sentence dogfood F7 filed as untrue."""
    vocab = _staleness_vocabulary()
    qualifiers = (*vocab["statuses"], vocab["fields"][0],
                  "when available", "when the anchor is available")
    out = []
    for block in _md_blocks(text):
        low = block.lower()
        if ("compare-and-swap" in low and "revision" in low
                and not any(q in low for q in qualifiers)):
            out.append(block)
    return out


def _guide_stale_sheet_contract_row() -> str:
    rows = [b for b in _md_blocks(guide(full=True)) if b.strip().startswith("| `STALE_SHEET`")]
    assert len(rows) == 1, (
        "the shipped guide must carry exactly one `STALE_SHEET` safety-contract row; "
        f"found {len(rows)}"
    )
    return rows[0]


def _guide_stale_sheet_semantics_bullet() -> str:
    # LD-457 TRANSFORMED THE LOCATOR, NOT THE CHECK. The bullet's prose used to name the
    # refusal `STALE_SHEET`, which is not what the wire carries — `Refusal.STALE_SHEET` is
    # the string `stale-sheet`, so a consumer's `== "STALE_SHEET"` retry guard never fired.
    # The guide now spells the wire value everywhere it names the refusal, so this locator
    # follows it (derived from the engine, never re-typed). Everything the bullet must SAY
    # — both tiers, revision-0, self-healing, never-silently-off — is unchanged below.
    needle = Refusal.STALE_SHEET
    bullets = [b for b in _md_blocks(guide(full=True))
               if b.strip().startswith("- ") and needle in b and "semantics" in b.lower()]
    assert len(bullets) == 1, (
        f"the shipped guide's sheets-write recipe must carry exactly one `{needle}` "
        f"semantics bullet; found {len(bullets)}"
    )
    return bullets[0]


def test_guide_stale_sheet_contract_row_tells_the_two_tier_story():
    """The guide's safety-contract table is a consumer's first read of what the write surface
    refuses. Its `STALE_SHEET` row must name both tiers in the engine's own vocabulary — not
    the pre-fix unconditional compare-and-swap sentence."""
    row = _guide_stale_sheet_contract_row()
    low = row.lower()

    assert not _missing_staleness_needles(row), (
        f"the guide's STALE_SHEET row omits code-derived needles: "
        f"{_missing_staleness_needles(row)}"
    )
    assert "tier 1" in low and "tier 2" in low, "both tiers must be named as tiers"
    assert "constant `0`" in low or "constant 0" in low, (
        "the row must state the revision-0 reality that makes tier 1 unavailable"
    )
    assert any(p in low for p in ("revision-`0`", "revision-0", "revision 0")), (
        "AC4: the row must say plainly that a revision-0 spreadsheet marks tier 1 unavailable"
    )


def test_guide_stale_sheet_semantics_bullet_tells_the_two_tier_story():
    """The recipe's `STALE_SHEET` semantics bullet is the prose F7 filed as untrue. It must
    now carry the whole contract: both tiers, the revision-0 reality, and self-healing."""
    bullet = _guide_stale_sheet_semantics_bullet()
    low = bullet.lower()

    assert not _missing_staleness_needles(bullet), (
        f"the guide's STALE_SHEET semantics bullet omits code-derived needles: "
        f"{_missing_staleness_needles(bullet)}"
    )
    assert "tier 1" in low and "tier 2" in low
    assert "constant `0`" in low or "constant 0" in low, (
        "the bullet must state the revision-0 reality (the F7 sheet)"
    )
    assert any(p in low for p in ("revision-`0`", "revision-0", "revision 0")), (
        "AC4: the bullet must say plainly that a revision-0 spreadsheet marks tier 1 "
        "unavailable"
    )
    assert "self-heal" in low, "the bullet must state the self-healing behavior"
    assert "never silently off" in low, (
        "the bullet must state the invariant plainly — the guard is never silently off"
    )


def test_no_guide_block_describes_the_compare_and_swap_as_unconditional():
    """The anti-rot guard: ANY block of the shipped guide that describes the mechanism must
    disclose the anchor's availability. A future edit that re-writes the honest wording back
    into the unconditional sentence reddens this, wherever in the guide it lands."""
    offenders = _unconditional_compare_and_swap_blocks(guide(full=True))

    assert not offenders, (
        "the shipped guide describes the revision compare-and-swap without disclosing that "
        f"the anchor can be unavailable (LD-132):\n\n" + "\n\n".join(offenders)
    )


# The wording that shipped on `develop` — verbatim, the sentence dogfood F7 filed as untrue.
_PRE_FIX_CONTRACT_ROW = (
    "| `STALE_SHEET` | sheets-write | Sheets compare-and-swap: the revision is cached at "
    "plan time and re-read before EACH write; a bump refuses `STALE_SHEET` (no write) and "
    "resyncs so the rest of the batch applies. |"
)
_PRE_FIX_SEMANTICS_BULLET = (
    "- **`STALE_SHEET` semantics:** `apply` re-reads the `revision` immediately before EACH\n"
    "  write. If it advanced since plan time (someone else edited), that entry **refuses\n"
    "  `STALE_SHEET` with no write** and resyncs the anchor so the rest of the batch still\n"
    "  applies — a compare-and-swap, not a blind overwrite."
)


def test_the_guide_content_guard_bites_red_then_green():
    """AC5 for the docs half: the SAME two checkers that guard the shipped guide bite on the
    pre-fix prose and green on the shipped prose — so this guard is proven to catch the exact
    rot it exists for (the id-based guide↔capabilities() guard cannot see prose at all)."""
    for stale in (_PRE_FIX_CONTRACT_ROW, _PRE_FIX_SEMANTICS_BULLET):
        assert _missing_staleness_needles(stale), (
            "the pre-fix wording must be caught as incomplete"
        )
        assert _unconditional_compare_and_swap_blocks(stale), (
            "the pre-fix wording must be caught as an unconditional mechanism claim"
        )

    assert not _missing_staleness_needles(_guide_stale_sheet_contract_row())
    assert not _missing_staleness_needles(_guide_stale_sheet_semantics_bullet())
    assert not _unconditional_compare_and_swap_blocks(guide(full=True))
