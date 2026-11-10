"""Offline unit tests for the plan-gated Sheets value-write apply engine
(LD-111).

W1 S3 lifts value writes into the **same gated discipline** as the docx apply engine
(``src/larkdocio/write/preview.py`` + ``apply.py``): a **findings-agnostic** write
request (target range + values), a **non-forgeable** :class:`Plan` (private token; no
``from_dict``) produced **only** by the mandatory :func:`dry_run` previewer, and an
:func:`apply` that consumes **only** a plan, writes an apply-log, and re-reads the
spreadsheet ``revision`` immediately before **each** write — refusing with a typed
``STALE_SHEET`` (no write) if it advanced (the compare-and-swap staleness anchor, D5),
while the rest of the batch still applies.

These pin the offline engine (injected client seam — the story is offline; the live
component of AC7 is only the read canary, and the write round-trip is S5's gate):

* **AC1** — the findings-agnostic request + a JSON-serializable apply-log round-trip;
  the AST findings-vocabulary guard extends to the sheets model (below);
* **AC2** — the non-forgeable ``Plan`` + mandatory dry-run (no direct-apply entry point);
* **AC3** — the dry-run preview carries per-write target + before/after with ZERO writes;
* **AC4** — the ``revision`` compare-and-swap → ``STALE_SHEET`` staleness races;
* **AC5** — apply-log + throttle completeness (only fresh, resolved writes hit transport).

The **test-rigor amplifier** ("go a bit nuts"): the full staleness-race matrix (advance
between dry-run and apply, stays, one-entry-stale-mid-batch, a write reply that omits
``revision`` → fall back to ``metainfo``), the precondition-mismatch matrix (value drift,
type drift, rich-cell target, vanished tab), plan-forgery attempts, and apply-log
completeness (1:1 with the plan, in order).
"""
import ast
import json
from pathlib import Path

import pytest

from log_reading_apply import reading_the_log
from larkdocio.errors import LarkAPIError
from larkdocio.sheets.write_apply import (
    ApplyLog,
    ApplyLogEntry,
    DropdownRuleWriteRequest,
    Plan,
    PlanEntry,
    Refusal,
    RichCellWriteRequest,
    ValueWriteRequest,
    WriteOpKind,
    apply,
    dry_run,
    effective_verify_style,
    requires_merge_leg,
    requires_style_leg,
)
apply = reading_the_log(apply)
from larkdocio.sheets.write_range import WriteRange, parse_write_range

TOKEN = "shtxxxTOKEN"


# --------------------------------------------------------------------------- #
# The client seam — a duck-typed stand-in modelling a real spreadsheet: a live #
# monotonic ``revision`` (+1 per write, spike Q4), a per-range value store, and #
# a recorded write list. External writers are simulated by scheduling a bump on #
# a given read_revision call.                                                   #
# --------------------------------------------------------------------------- #

class FakeSheetGateway:
    def __init__(self, *, revision, values=None):
        self.revision = revision            # the CURRENT live revision (int)
        self.values = dict(values or {})    # {a1_range: matrix | Exception}
        self.puts = []                      # [(a1_range, values)] — recorded writes
        self.dv_sets = []                   # [(a1_range, rule)] — recorded rule writes
        self.omit_put_revision = False      # put reply returns {"revision": None}
        self.external_bumps = {}            # {read_revision_call_n: delta}
        self._rev_reads = 0
        self.value_reads = []               # [a1_range] — recorded reads

    def read_revision(self, spreadsheet_token):
        self._rev_reads += 1
        self.revision += self.external_bumps.pop(self._rev_reads, 0)
        return self.revision

    def read_values(self, spreadsheet_token, a1_range, value_render_option="UnformattedValue"):
        self.value_reads.append(a1_range)
        v = self.values.get(a1_range)
        if isinstance(v, Exception):
            raise v
        return [] if v is None else v

    def put_values(self, spreadsheet_token, a1_range, values):
        self.puts.append((a1_range, values))
        self.values[a1_range] = values
        self.revision += 1  # every write bumps +1 (spike Q4)
        return {"revision": None if self.omit_put_revision else self.revision}

    def set_data_validation(self, spreadsheet_token, a1_range, rule):
        # the real POST …/dataValidation reply carries `data: {}` (no revision), so the
        # engine's post-write revision always comes from the metainfo fallback (spike Q3/Q4).
        self.dv_sets.append((a1_range, rule))
        self.revision += 1  # every write bumps +1 (spike Q4)
        return {}


def _req(a1, values):
    return ValueWriteRequest.for_a1(a1, values)


# =========================================================================== #
# AC1 — findings-agnostic request + JSON-serializable apply-log round-trip     #
# =========================================================================== #

def test_value_write_request_carries_target_and_values():
    req = ValueWriteRequest.for_a1("s1!B2:C3", [["a", "b"], ["c", "d"]])
    assert isinstance(req.target, WriteRange)
    assert req.target.a1() == "s1!B2:C3"
    assert req.values == [["a", "b"], ["c", "d"]]


def test_value_write_request_single_cell_normalizes_to_start_end():
    # reuse S2's parse_write_range → a bare cell is not a writable range (D2)
    req = ValueWriteRequest.for_a1("s1!B2", [["x"]])
    assert req.target.a1() == "s1!B2:B2"


def test_value_write_request_round_trips_through_json():
    req = ValueWriteRequest.for_a1("s1!A1:A1", [[42]])
    d = req.to_dict()
    assert json.loads(json.dumps(d)) == d
    assert ValueWriteRequest.from_dict(d) == req


def test_apply_log_entry_applied_round_trips_through_json():
    entry = ApplyLogEntry.applied(
        target=parse_write_range("s1!A1:A1"),
        before=[["old"]],
        after=[["new"]],
        revision=7,
    )
    d = entry.to_dict()
    assert json.loads(json.dumps(d)) == d
    assert ApplyLogEntry.from_dict(d) == entry


def test_apply_log_stale_entry_round_trips_through_json():
    entry = ApplyLogEntry.stale(
        target=parse_write_range("s1!A1:A1"),
        refusal=Refusal.stale_sheet(cached=3, live=5),
    )
    d = entry.to_dict()
    assert json.loads(json.dumps(d)) == d
    assert ApplyLogEntry.from_dict(d) == entry


def test_apply_log_aggregate_round_trips_through_json():
    log = ApplyLog(entries=(
        ApplyLogEntry.applied(target=parse_write_range("s1!A1:A1"),
                              before=[["a"]], after=[["b"]], revision=2),
        ApplyLogEntry.refused(target=parse_write_range("s1!B1:B1"),
                             refusal=Refusal.precondition_mismatch(expected=[["x"]], live=[["y"]])),
    ))
    d = log.to_dict()
    assert json.loads(json.dumps(d)) == d


# --------------------------------------------------------------------------- #
# AC1 (cont.) — the AST findings-vocabulary guard EXTENDS to the sheets model  #
# (same scan the docx write/model guard runs — no consumer findings/severity/  #
# accept-reject vocabulary couples into the library surface).                  #
# --------------------------------------------------------------------------- #

# LD-125 split the 2,057-line ``write_apply.py`` god module into a facade over four concern
# modules; the guard now scans the WHOLE sheets write surface so the findings-agnostic +
# stdlib/larkdocio-only guarantees follow the code into ``requests`` / ``plan`` / ``ops`` /
# ``merge_geometry`` (they were all one file before the split).
# LD-224 then split ``requests.py`` into a package on the same principle, so its members
# are DERIVED from the tree here rather than listed by name.
# LD-532 did the same to ``ops.py`` — now a package too — for the same reason, so its
# members are DERIVED from the tree as well.
_SHEETS_DIR = Path(__file__).resolve().parents[1] / "src" / "larkdocio" / "sheets"
_SHEETS_WRITE_MODULES = tuple(
    [_SHEETS_DIR / name
     for name in ("write_apply.py", "plan.py", "merge_geometry.py")]
    + sorted(p for p in (_SHEETS_DIR / "requests").rglob("*.py")
             if "__pycache__" not in p.parts)
    + sorted(p for p in (_SHEETS_DIR / "ops").rglob("*.py")
             if "__pycache__" not in p.parts)
)


def _write_apply_trees():
    return [ast.parse(p.read_text(encoding="utf-8")) for p in _SHEETS_WRITE_MODULES]


def _code_identifiers(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
    return names


def test_sheets_write_apply_imports_only_stdlib_and_larkdocio():
    import sys

    roots = set()
    for tree in _write_apply_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                if node.module:
                    roots.add(node.module.split(".")[0])
    allowed = set(sys.stdlib_module_names) | {"larkdocio"}
    assert roots <= allowed, f"non-stdlib/non-larkdocio imports: {roots - allowed}"


def test_sheets_write_apply_references_no_findings_vocabulary():
    idents = set()
    for tree in _write_apply_trees():
        idents |= {n.lower() for n in _code_identifiers(tree)}
    for word in ("finding", "layer", "severity", "accepted", "rejected"):
        offenders = {n for n in idents if word in n}
        assert not offenders, f"findings-schema vocabulary in identifiers: {offenders}"


# =========================================================================== #
# AC2 — non-forgeable Plan + mandatory dry-run (D4): no direct-apply entry     #
# =========================================================================== #

def test_plan_cannot_be_hand_constructed():
    with pytest.raises(TypeError):
        Plan([], revision=0, spreadsheet_token=TOKEN)


def test_plan_has_no_from_dict_forge_vector():
    assert not hasattr(Plan, "from_dict")


def test_apply_rejects_a_non_plan_argument():
    gw = FakeSheetGateway(revision=0)
    with pytest.raises(TypeError):
        apply([_req("s1!A1:A1", [["x"]])], gw)  # a bag of requests is not a Plan


def test_apply_rejects_a_list_of_plan_entries():
    gw = FakeSheetGateway(revision=0)
    entry = PlanEntry.resolved(target=parse_write_range("s1!A1:A1"),
                               before=[["a"]], after=[["b"]])
    with pytest.raises(TypeError):
        apply([entry], gw)


def test_only_a_dry_run_plan_reaches_apply():
    gw = FakeSheetGateway(revision=1, values={"s1!A1:A1": [["old"]]})
    plan = dry_run([_req("s1!A1:A1", [["new"]])], gw, TOKEN)
    assert isinstance(plan, Plan)
    log = apply(plan, gw)  # the ONLY accepted path
    assert log.entries[0].is_applied


# =========================================================================== #
# AC3 — dry-run preview content: per-write target + before/after, ZERO writes  #
# =========================================================================== #

def test_dry_run_previews_before_from_read_and_after_from_request():
    gw = FakeSheetGateway(revision=4, values={"s1!A1:B1": [["old-a", "old-b"]]})
    plan = dry_run([_req("s1!A1:B1", [["new-a", "new-b"]])], gw, TOKEN)
    (entry,) = plan.entries
    assert entry.is_resolved
    assert entry.target.a1() == "s1!A1:B1"
    assert entry.before == [["old-a", "old-b"]]
    assert entry.after == [["new-a", "new-b"]]


def test_dry_run_performs_zero_writes():
    gw = FakeSheetGateway(revision=4, values={"s1!A1:A1": [["old"]]})
    dry_run([_req("s1!A1:A1", [["new"]])], gw, TOKEN)
    assert gw.puts == []  # the previewer structurally never writes


def test_dry_run_caches_revision_at_plan_time():
    gw = FakeSheetGateway(revision=9, values={"s1!A1:A1": [["old"]]})
    plan = dry_run([_req("s1!A1:A1", [["new"]])], gw, TOKEN)
    assert plan.revision == 9
    assert plan.spreadsheet_token == TOKEN


# =========================================================================== #
# AC4 — revision compare-and-swap → STALE_SHEET (D5): the staleness-race matrix #
# =========================================================================== #

def test_revision_stays_the_same_writes():
    gw = FakeSheetGateway(revision=2, values={"s1!A1:A1": [["old"]]})
    plan = dry_run([_req("s1!A1:A1", [["new"]])], gw, TOKEN)
    log = apply(plan, gw)
    (entry,) = log.entries
    assert entry.is_applied
    assert gw.puts == [("s1!A1:A1", [["new"]])]


def test_revision_advances_between_dry_run_and_apply_is_stale_no_write():
    gw = FakeSheetGateway(revision=2, values={"s1!A1:A1": [["old"]]})
    plan = dry_run([_req("s1!A1:A1", [["new"]])], gw, TOKEN)
    # an external writer bumps revision before apply's pre-write re-read (call #2).
    gw.external_bumps = {2: 1}
    log = apply(plan, gw)
    (entry,) = log.entries
    assert not entry.is_applied
    assert entry.refusal.reason == Refusal.STALE_SHEET
    assert gw.puts == []  # STALE_SHEET → no write


def test_revision_advances_between_dry_run_and_apply_carries_cached_and_live():
    gw = FakeSheetGateway(revision=5, values={"s1!A1:A1": [["old"]]})
    plan = dry_run([_req("s1!A1:A1", [["new"]])], gw, TOKEN)
    gw.external_bumps = {2: 3}  # jumps 5 -> 8
    log = apply(plan, gw)
    entry = log.entries[0]
    assert entry.refusal.reason == Refusal.STALE_SHEET
    assert "5" in entry.refusal.detail and "8" in entry.refusal.detail


def test_one_entry_goes_stale_mid_batch_only_that_one_skips():
    gw = FakeSheetGateway(revision=1, values={
        "s1!A1:A1": [["a0"]],
        "s1!B1:B1": [["b0"]],
        "s1!C1:C1": [["c0"]],
    })
    plan = dry_run([
        _req("s1!A1:A1", [["a1"]]),
        _req("s1!B1:B1", [["b1"]]),
        _req("s1!C1:C1", [["c1"]]),
    ], gw, TOKEN)
    # read_revision call order: #1 = dry_run cache; #2 = entry A pre-read; A writes (rev+1);
    # #3 = entry B pre-read (external bump here) — B stale; #4 = entry C pre-read (resynced).
    gw.external_bumps = {3: 1}
    log = apply(plan, gw)
    outcomes = [e.outcome for e in log.entries]
    assert outcomes == ["applied", "stale", "applied"]
    assert gw.puts == [("s1!A1:A1", [["a1"]]), ("s1!C1:C1", [["c1"]])]  # B never written


def test_batch_of_writes_advances_the_compare_and_swap_anchor_as_we_write():
    # our own writes bump revision +1 each; a batch must NOT self-poison into STALE.
    gw = FakeSheetGateway(revision=0, values={
        "s1!A1:A1": [["a0"]], "s1!B1:B1": [["b0"]], "s1!C1:C1": [["c0"]],
    })
    plan = dry_run([
        _req("s1!A1:A1", [["a1"]]),
        _req("s1!B1:B1", [["b1"]]),
        _req("s1!C1:C1", [["c1"]]),
    ], gw, TOKEN)
    log = apply(plan, gw)
    assert [e.outcome for e in log.entries] == ["applied", "applied", "applied"]
    assert len(gw.puts) == 3


def test_write_reply_omitting_revision_falls_back_to_metainfo():
    gw = FakeSheetGateway(revision=4, values={"s1!A1:A1": [["old"]]})
    gw.omit_put_revision = True  # the put reply carries revision: null (spike Q1/Q4)
    plan = dry_run([_req("s1!A1:A1", [["new"]])], gw, TOKEN)
    log = apply(plan, gw)
    entry = log.entries[0]
    assert entry.is_applied
    # the applied entry records the post-write revision read back from metainfo (5),
    # not None — the fallback fired.
    assert entry.revision == 5


# =========================================================================== #
# AC5 — apply-log + throttle completeness: only fresh, resolved writes write    #
# =========================================================================== #

def test_applied_entry_carries_target_values_and_post_revision():
    gw = FakeSheetGateway(revision=0, values={"s1!A1:A1": [["old"]]})
    plan = dry_run([_req("s1!A1:A1", [["new"]])], gw, TOKEN)
    entry = apply(plan, gw).entries[0]
    assert entry.target.a1() == "s1!A1:A1"
    assert entry.after == [["new"]]
    assert entry.before == [["old"]]
    assert entry.revision == 1  # post-write revision (0 -> 1)


def test_refused_entry_does_not_hit_the_transport():
    # a rich-cell target is refused at dry_run; apply carries the refusal, no write.
    gw = FakeSheetGateway(revision=0, values={"s1!A1:A1": [[{"type": "mention", "text": "@x"}]]})
    plan = dry_run([_req("s1!A1:A1", [["new"]])], gw, TOKEN)
    assert plan.entries[0].refusal.reason == Refusal.RICH_CELL_TARGET
    log = apply(plan, gw)
    assert not log.entries[0].is_applied
    assert gw.puts == []


def test_apply_log_is_one_to_one_with_the_plan_in_order():
    gw = FakeSheetGateway(revision=0, values={
        "s1!A1:A1": [["a0"]],
        "s1!B1:B1": [[{"type": "url", "link": "x", "text": "y"}]],  # rich → refused at dry_run
        "s1!C1:C1": [["c0"]],
    })
    plan = dry_run([
        _req("s1!A1:A1", [["a1"]]),
        _req("s1!B1:B1", [["b1"]]),
        _req("s1!C1:C1", [["c1"]]),
    ], gw, TOKEN)
    log = apply(plan, gw)
    assert len(log.entries) == len(plan.entries) == 3
    assert [e.target.a1() for e in log.entries] == ["s1!A1:A1", "s1!B1:B1", "s1!C1:C1"]
    assert [e.outcome for e in log.entries] == ["applied", "refused", "applied"]


def test_stale_entry_does_not_hit_the_transport():
    gw = FakeSheetGateway(revision=2, values={"s1!A1:A1": [["old"]]})
    plan = dry_run([_req("s1!A1:A1", [["new"]])], gw, TOKEN)
    gw.external_bumps = {2: 1}
    apply(plan, gw)
    assert gw.puts == []


# =========================================================================== #
# Precondition-mismatch matrix (amplifier): value drift, type drift, rich-cell #
# target (at apply), vanished tab.                                             #
# =========================================================================== #

def test_precondition_value_drift_refuses_no_write():
    gw = FakeSheetGateway(revision=3, values={"s1!A1:A1": [["captured"]]})
    plan = dry_run([_req("s1!A1:A1", [["new"]])], gw, TOKEN)
    # the target value drifts but revision is unchanged (the precondition is the second,
    # per-target guard behind the global compare-and-swap).
    gw.values["s1!A1:A1"] = [["drifted"]]
    log = apply(plan, gw)
    entry = log.entries[0]
    assert entry.refusal.reason == Refusal.PRECONDITION_MISMATCH
    assert gw.puts == []


def test_precondition_type_drift_refuses_no_write():
    gw = FakeSheetGateway(revision=3, values={"s1!A1:A1": [[42]]})
    plan = dry_run([_req("s1!A1:A1", [[43]])], gw, TOKEN)
    gw.values["s1!A1:A1"] = [["42"]]  # number -> string: 42 != "42"
    log = apply(plan, gw)
    assert log.entries[0].refusal.reason == Refusal.PRECONDITION_MISMATCH
    assert gw.puts == []


def test_rich_cell_target_at_dry_run_refuses():
    gw = FakeSheetGateway(revision=0, values={
        "s1!A1:A1": [[{"type": "mention", "mentionType": 0, "text": "@Example User"}]],
    })
    plan = dry_run([_req("s1!A1:A1", [["plain"]])], gw, TOKEN)
    assert plan.entries[0].refusal.reason == Refusal.RICH_CELL_TARGET


def test_proposed_rich_cell_value_at_dry_run_refuses():
    gw = FakeSheetGateway(revision=0, values={"s1!A1:A1": [["old"]]})
    plan = dry_run([_req("s1!A1:A1", [[{"type": "multipleValue", "values": ["Red"]}]])], gw, TOKEN)
    assert plan.entries[0].refusal.reason == Refusal.RICH_CELL_TARGET


def test_rich_cell_target_at_apply_refuses_no_write():
    gw = FakeSheetGateway(revision=0, values={"s1!A1:A1": [["old"]]})
    plan = dry_run([_req("s1!A1:A1", [["new"]])], gw, TOKEN)
    gw.values["s1!A1:A1"] = [[{"type": "url", "link": "x", "text": "y"}]]  # became rich
    log = apply(plan, gw)
    assert log.entries[0].refusal.reason == Refusal.RICH_CELL_TARGET
    assert gw.puts == []


def test_vanished_tab_at_dry_run_refuses():
    # NOTE (LD-150 / dogfood F20): this fixture used `code=90202` as a stand-in for "the range
    # could not be read". `90202` is `validate RangeVal fail` — a statement about the RANGE, not
    # the tab — and is now DELIBERATELY re-categorized `malformed-range` (see the sibling test
    # below). The vanished-tab story keeps the code its apply-time twin already used (1310249).
    gw = FakeSheetGateway(revision=0, values={"s1!A1:A1": LarkAPIError("tab gone", code=1310249)})
    plan = dry_run([_req("s1!A1:A1", [["new"]])], gw, TOKEN)
    assert plan.entries[0].refusal.reason == Refusal.TAB_VANISHED


def test_a_90202_range_at_dry_run_refuses_malformed_range_not_vanished():
    """LD-150 / F20 — the one deliberate re-categorization in this issue, pinned here next to
    the staleness story it used to be confused with."""
    gw = FakeSheetGateway(revision=0, values={
        "s1!A1:A1": LarkAPIError("Code: 90202, Msg: validate RangeVal fail", code=90202)})
    plan = dry_run([_req("s1!A1:A1", [["new"]])], gw, TOKEN)
    assert plan.entries[0].refusal.reason == Refusal.MALFORMED_RANGE


def test_vanished_tab_at_apply_refuses_no_write():
    gw = FakeSheetGateway(revision=0, values={"s1!A1:A1": [["old"]]})
    plan = dry_run([_req("s1!A1:A1", [["new"]])], gw, TOKEN)
    gw.values["s1!A1:A1"] = LarkAPIError("tab vanished", code=1310249)
    log = apply(plan, gw)
    assert log.entries[0].refusal.reason == Refusal.TAB_VANISHED
    assert gw.puts == []


# =========================================================================== #
# Refusal typing — a small, typed, findings-agnostic vocabulary                #
# =========================================================================== #

def test_refusal_reasons_are_distinct():
    reasons = {
        Refusal.STALE_SHEET,
        Refusal.PRECONDITION_MISMATCH,
        Refusal.RICH_CELL_TARGET,
        Refusal.TAB_VANISHED,
    }
    assert len(reasons) == 4


def test_refusal_round_trips_through_json():
    r = Refusal.stale_sheet(cached=1, live=4)
    d = r.to_dict()
    assert json.loads(json.dumps(d)) == d
    assert Refusal.from_dict(d) == r


# =========================================================================== #
# Plan partitions — resolved / refusals inspection surface (approval UX)       #
# =========================================================================== #

def test_plan_partitions_resolved_and_refusals():
    gw = FakeSheetGateway(revision=0, values={
        "s1!A1:A1": [["ok"]],
        "s1!B1:B1": [[{"type": "mention", "text": "@x"}]],  # rich → refused
    })
    plan = dry_run([_req("s1!A1:A1", [["x"]]), _req("s1!B1:B1", [["y"]])], gw, TOKEN)
    assert len(plan.resolved) == 1
    assert len(plan.refusals) == 1
    assert plan.to_json()  # inspectable / serializable for a consumer's approval UX


# =========================================================================== #
# LD-119 — rich-cell writes through the gated engine.                          #
# The LD-111 refuse-on-rich restriction is LIFTED for the ENCODED TYPES ONLY   #
# (a RichCellWriteRequest); a raw structured value on the PLAIN ValueWrite     #
# path still refuses. Rich writes stay Plan→dry-run→apply + STALE_SHEET-gated. #
# =========================================================================== #

def _hyperlink_req(a1, link="https://x.example", text="X"):
    return RichCellWriteRequest.hyperlink(a1, link, text=text)


def test_rich_cell_write_request_wraps_the_encoded_cell_into_a_1x1_matrix():
    req = RichCellWriteRequest.hyperlink("s1!A1:A1", "https://x.example", text="X")
    assert req.target.a1() == "s1!A1:A1"
    assert req.values == [[{"type": "url", "text": "X", "link": "https://x.example"}]]
    assert req.op_kinds == (WriteOpKind.VALUE,)
    assert req.is_rich is True


def test_plain_value_request_is_not_rich():
    assert ValueWriteRequest.for_a1("s1!A1:A1", [["x"]]).is_rich is False


def test_rich_hyperlink_write_flows_through_dry_run_and_apply():
    gw = FakeSheetGateway(revision=0, values={"s1!A1:A1": [["old"]]})
    plan = dry_run([_hyperlink_req("s1!A1:A1")], gw, TOKEN)
    assert len(plan.resolved) == 1 and len(plan.refusals) == 0
    log = apply(plan, gw)
    (entry,) = log.entries
    assert entry.is_applied
    assert gw.puts == [("s1!A1:A1", [[{"type": "url", "text": "X", "link": "https://x.example"}]])]
    assert entry.revision == 1  # every write bumps +1


def test_rich_styled_runs_write_encodes_and_applies():
    gw = FakeSheetGateway(revision=0, values={"s1!A2:A2": [["old"]]})
    req = RichCellWriteRequest.styled_runs("s1!A2:A2", [
        {"text": "bold ", "bold": True},
        {"text": "then italic", "italic": True, "fore_color": "#FF0000"},
    ])
    log = apply(dry_run([req], gw, TOKEN), gw)
    assert log.entries[0].is_applied
    written_cell = gw.puts[0][1][0][0]
    assert written_cell == [
        {"type": "text", "text": "bold ", "segmentStyle": {"bold": True}},
        {"type": "text", "text": "then italic", "segmentStyle": {"italic": True, "foreColor": "#FF0000"}},
    ]


def test_rich_mention_write_carries_notify_false_defaults():
    gw = FakeSheetGateway(revision=0, values={"s1!A3:A3": [["old"]]})
    req = RichCellWriteRequest.mention("s1!A3:A3", "ou_abc")
    apply(dry_run([req], gw, TOKEN), gw)
    written_cell = gw.puts[0][1][0][0]
    assert written_cell == {
        "type": "mention", "text": "ou_abc", "textType": "openId",
        "notify": False, "grantReadPermission": False,
    }


def test_rich_mention_opt_in_notify_flows_through():
    gw = FakeSheetGateway(revision=0, values={"s1!A3:A3": [["old"]]})
    req = RichCellWriteRequest.mention("s1!A3:A3", "ou_abc", notify=True, grant_read_permission=True)
    apply(dry_run([req], gw, TOKEN), gw)
    written_cell = gw.puts[0][1][0][0]
    assert written_cell["notify"] is True and written_cell["grantReadPermission"] is True


def test_rich_multi_select_write_encodes_the_multiple_value_object():
    gw = FakeSheetGateway(revision=0, values={"s1!A4:A4": [["old"]]})
    req = RichCellWriteRequest.multi_select("s1!A4:A4", ["Red", "Green"])
    apply(dry_run([req], gw, TOKEN), gw)
    assert gw.puts[0][1][0][0] == {"type": "multipleValue", "values": ["Red", "Green"]}


def test_rich_multi_select_comma_in_label_refuses_at_request_build():
    # the typed refusal fires at encode time — you cannot even build the request (D7).
    from larkdocio.sheets.rich_encode import MultiSelectLabelError

    with pytest.raises(MultiSelectLabelError):
        RichCellWriteRequest.multi_select("s1!A4:A4", ["a,b"])


def test_rich_write_is_stale_sheet_guarded_no_write():
    gw = FakeSheetGateway(revision=2, values={"s1!A1:A1": [["old"]]})
    plan = dry_run([_hyperlink_req("s1!A1:A1")], gw, TOKEN)
    gw.external_bumps = {2: 1}  # an external writer bumps revision before apply's re-read
    log = apply(plan, gw)
    (entry,) = log.entries
    assert not entry.is_applied
    assert entry.refusal.reason == Refusal.STALE_SHEET
    assert gw.puts == []  # STALE_SHEET → no write


def test_rich_write_precondition_mismatch_refuses_no_write():
    gw = FakeSheetGateway(revision=3, values={"s1!A1:A1": [["captured"]]})
    plan = dry_run([_hyperlink_req("s1!A1:A1")], gw, TOKEN)
    gw.values["s1!A1:A1"] = [["drifted"]]  # target drifts (revision unchanged)
    log = apply(plan, gw)
    assert log.entries[0].refusal.reason == Refusal.PRECONDITION_MISMATCH
    assert gw.puts == []


def test_rich_write_to_a_currently_rich_target_resolves():
    # A rich target's structured "before" is EXPECTED for a rich write — it must NOT
    # refuse RICH_CELL_TARGET the way the plain-value path does (the encoded-types lift).
    current_link = [{"cellPosition": None, "link": "https://old.example", "text": "old", "type": "url"}]
    gw = FakeSheetGateway(revision=0, values={"s1!A1:A1": [current_link]})
    plan = dry_run([_hyperlink_req("s1!A1:A1")], gw, TOKEN)
    assert len(plan.resolved) == 1, f"a rich write over a rich target must resolve: {plan!r}"
    log = apply(plan, gw)
    assert log.entries[0].is_applied
    assert gw.puts == [("s1!A1:A1", [[{"type": "url", "text": "X", "link": "https://x.example"}]])]


def test_plain_value_path_still_refuses_a_raw_structured_proposed_value():
    # The lift is for ENCODED types ONLY: a raw structured dict on the PLAIN path still
    # refuses RICH_CELL_TARGET (you must go through a RichCellWriteRequest).
    gw = FakeSheetGateway(revision=0, values={"s1!A1:A1": [["old"]]})
    plan = dry_run([_req("s1!A1:A1", [[{"type": "multipleValue", "values": ["Red"]}]])], gw, TOKEN)
    assert plan.entries[0].refusal.reason == Refusal.RICH_CELL_TARGET
    assert apply(plan, gw).entries[0].outcome == "refused"
    assert gw.puts == []


def test_rich_resolved_plan_entry_round_trips_through_json_with_the_rich_flag():
    gw = FakeSheetGateway(revision=0, values={"s1!A1:A1": [["old"]]})
    plan = dry_run([_hyperlink_req("s1!A1:A1")], gw, TOKEN)
    d = plan.entries[0].to_dict()
    assert json.loads(json.dumps(d)) == d
    assert d["rich"] is True
    assert PlanEntry.from_dict(d).rich is True


def test_rich_and_plain_writes_batch_in_one_plan_in_order():
    gw = FakeSheetGateway(revision=0, values={
        "s1!A1:A1": [["a0"]],
        "s1!A2:A2": [["b0"]],
    })
    plan = dry_run([
        _req("s1!A1:A1", [["plain"]]),
        _hyperlink_req("s1!A2:A2"),
    ], gw, TOKEN)
    log = apply(plan, gw)
    assert [e.outcome for e in log.entries] == ["applied", "applied"]
    assert gw.puts[0] == ("s1!A1:A1", [["plain"]])
    assert gw.puts[1] == ("s1!A2:A2", [[{"type": "url", "text": "X", "link": "https://x.example"}]])


# =========================================================================== #
# LD-120 — dropdown-RULE writes through the gated engine.                       #
# A DropdownRuleWriteRequest (POST …/dataValidation) flows Plan → dry-run →      #
# apply, revision-compare-and-swap (STALE_SHEET) guarded like every write, but  #
# with NO scalar value-precondition (a rule is not a cell value). The rule op   #
# writes via the client's set_data_validation seam, never put_values.           #
# =========================================================================== #

def _dropdown_req(a1="s1!A1:A1", conds=("Red", "Green", "Blue"), **kw):
    return DropdownRuleWriteRequest.list_rule(a1, list(conds), **kw)


def test_dropdown_rule_request_carries_target_rule_and_op_kind():
    req = _dropdown_req("s1!A1:A1", multiple_values=True)
    assert req.target.a1() == "s1!A1:A1"
    assert req.rule == {
        "dataValidationType": "list",
        "dataValidation": {
            "conditionValues": ["Red", "Green", "Blue"],
            "options": {"multipleValues": True, "highlightValidData": False},
        },
    }
    assert req.is_rich is False
    assert req.write_kind == "data-validation"
    assert req.op_kinds == (WriteOpKind.DATA_VALIDATION,)


def test_dropdown_rule_single_cell_normalizes_to_start_end():
    req = _dropdown_req("s1!B2")
    assert req.target.a1() == "s1!B2:B2"


def test_dropdown_rule_90204_guard_fires_at_request_build():
    # the colors caveat refuses at build time — you cannot even construct the request
    # with highlight on and no matching colors (D6 / AC2).
    from larkdocio.sheets.rich_encode import DropdownColorsError

    with pytest.raises(DropdownColorsError):
        DropdownRuleWriteRequest.list_rule("s1!A1:A1", ["Red", "Green"], highlight_valid_data=True)


def test_dropdown_rule_flows_through_dry_run_and_apply():
    gw = FakeSheetGateway(revision=0)
    plan = dry_run([_dropdown_req("s1!A1:A1", multiple_values=True)], gw, TOKEN)
    assert len(plan.resolved) == 1 and len(plan.refusals) == 0
    log = apply(plan, gw)
    (entry,) = log.entries
    assert entry.is_applied
    assert gw.dv_sets == [("s1!A1:A1", {
        "dataValidationType": "list",
        "dataValidation": {
            "conditionValues": ["Red", "Green", "Blue"],
            "options": {"multipleValues": True, "highlightValidData": False},
        },
    })]
    assert gw.puts == []                       # never the value endpoint
    assert entry.revision == 1                 # every write bumps +1 (via metainfo fallback)


def test_dropdown_rule_single_select_writes_multiple_values_false():
    gw = FakeSheetGateway(revision=0)
    apply(dry_run([_dropdown_req("s1!A1:A1")], gw, TOKEN), gw)
    _a1, rule = gw.dv_sets[0]
    assert rule["dataValidation"]["options"]["multipleValues"] is False


def test_dropdown_rule_dry_run_performs_zero_writes():
    gw = FakeSheetGateway(revision=3)
    dry_run([_dropdown_req("s1!A1:A1")], gw, TOKEN)
    assert gw.dv_sets == [] and gw.puts == []


def test_dropdown_rule_caches_revision_at_plan_time():
    gw = FakeSheetGateway(revision=7)
    plan = dry_run([_dropdown_req("s1!A1:A1")], gw, TOKEN)
    assert plan.revision == 7


def test_dropdown_rule_is_stale_sheet_guarded_no_write():
    gw = FakeSheetGateway(revision=2)
    plan = dry_run([_dropdown_req("s1!A1:A1")], gw, TOKEN)
    gw.external_bumps = {2: 1}  # an external writer bumps revision before apply's re-read
    log = apply(plan, gw)
    (entry,) = log.entries
    assert not entry.is_applied
    assert entry.refusal.reason == Refusal.STALE_SHEET
    assert gw.dv_sets == []  # STALE_SHEET → no rule write


def test_dropdown_rule_does_not_read_or_require_a_value_precondition():
    # a rule is not a scalar cell value: the engine must NOT read_values for the
    # precondition on a rule write (there is nothing to compare), yet still writes.
    gw = FakeSheetGateway(revision=0)
    apply(dry_run([_dropdown_req("s1!A1:A1")], gw, TOKEN), gw)
    assert gw.value_reads == []       # no before/precondition value read for a rule
    assert len(gw.dv_sets) == 1


def test_dropdown_rule_op_kinds_trigger_no_style_or_merge_leg():
    # a data-validation rule is verified by its own dataValidation GET (the S6 rule leg),
    # NOT the export style leg or the v3 merge leg — so it must trigger neither.
    kinds = (WriteOpKind.DATA_VALIDATION,)
    assert requires_style_leg(kinds) is False
    assert requires_merge_leg(kinds) is False
    assert effective_verify_style(kinds) is False


def test_dropdown_rule_batches_with_value_and_rich_in_order():
    gw = FakeSheetGateway(revision=0, values={
        "s1!A1:A1": [["a0"]],
        "s1!A3:A3": [["c0"]],
    })
    plan = dry_run([
        _req("s1!A1:A1", [["plain"]]),
        _dropdown_req("s1!A2:A2", multiple_values=True),
        _hyperlink_req("s1!A3:A3"),
    ], gw, TOKEN)
    log = apply(plan, gw)
    assert [e.outcome for e in log.entries] == ["applied", "applied", "applied"]
    assert gw.puts[0] == ("s1!A1:A1", [["plain"]])
    assert gw.dv_sets == [("s1!A2:A2", {
        "dataValidationType": "list",
        "dataValidation": {
            "conditionValues": ["Red", "Green", "Blue"],
            "options": {"multipleValues": True, "highlightValidData": False},
        },
    })]
    assert gw.puts[1] == ("s1!A3:A3", [[{"type": "url", "text": "X", "link": "https://x.example"}]])


def test_dropdown_rule_request_to_dict_is_json_serializable():
    req = _dropdown_req("s1!A1:A1", multiple_values=True)
    d = req.to_dict()
    assert json.loads(json.dumps(d)) == d
    assert d["target"] == "s1!A1:A1"
    assert d["kind"] == "dropdown-rule"


def test_dropdown_rule_plan_entry_round_trips_json_with_write_kind():
    gw = FakeSheetGateway(revision=0)
    plan = dry_run([_dropdown_req("s1!A1:A1")], gw, TOKEN)
    d = plan.entries[0].to_dict()
    assert json.loads(json.dumps(d)) == d
    assert d["write_kind"] == "data-validation"
    assert PlanEntry.from_dict(d).write_kind == "data-validation"


def test_dropdown_rule_stale_mid_batch_only_that_one_skips():
    gw = FakeSheetGateway(revision=1, values={"s1!A1:A1": [["a0"]]})
    plan = dry_run([
        _req("s1!A1:A1", [["a1"]]),
        _dropdown_req("s1!A2:A2"),
    ], gw, TOKEN)
    # read_revision order: #1 dry_run cache; #2 entry-A pre-read; A writes (rev+1);
    # #3 entry-B (dropdown) pre-read — external bump here → B stale.
    gw.external_bumps = {3: 1}
    log = apply(plan, gw)
    assert [e.outcome for e in log.entries] == ["applied", "stale"]
    assert gw.puts == [("s1!A1:A1", [["a1"]])]
    assert gw.dv_sets == []  # the stale rule write never fired
