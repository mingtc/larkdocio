"""LD-187 — tab REORDER / HIDE / RETITLE: the three ``updateSheet`` fields that ride the
already-shipped ``sheets_batch_update`` seam, plus the two disclosures they owe a consumer.

Every arm here is **offline** (an injected transport / a duck-typed client seam), but every
API fact it pins was **characterized live first** on a self-provisioned, ``finally``-deleted
disposable and is read back out of the committed capture rather than re-typed by hand
(``tests/captures/sheets-tab-presentation-probe/captures/01-updateSheet-index-title-hidden.json``), so an
API drift reddens the suite instead of silently corrupting a plan.

**What the probe settled, and what each fact costs if it is guessed wrong.**

* ``index`` is a **TARGET POSITION** (0-based), not a delta: a tab at 0 asked for ``index: 2``
  lands at 2 and the tabs it passed close the gap. A delta reading would scatter a consumer's
  tab order.
* an index **past the last** one is **silently CLAMPED** — ``index: 4`` and ``index: 99`` on a
  4-tab spreadsheet both answer ``code 0`` and leave the tab last. There is no error to
  surface, which is exactly why this library refuses it at plan time: a silent clamp means the
  stated intent is not what happened.
* ``index: -1`` is the one index Lark itself rejects — ``90204 invalid parameter:
  Requests[0].UpdateSheet.Properties.Index``.
* a **no-op** reorder (a tab asked for the index it already holds) is accepted and does **not
  even bump the revision** — unlike a no-op freeze, which does.
* a **duplicate** title is refused — ``90210 sheetTitle already exist in snapshot`` — but the
  uniqueness check is **case-SENSITIVE**: retitling to ``gamma`` beside an existing ``Gamma``
  answers ``code 0``. Case-folding the check here would refuse a write Lark accepts.
* an **empty** title is refused — ``90207 sheetTitle should not be empty``.
* there is **no length ceiling to be found at 101 characters** (both 100 and 101 answered
  ``code 0`` and the 101-character title really landed), so this library invents none.
* a **retitle does not change the ``sheet_id``** — the id is the stable handle, which is the
  whole point of the join disclosure.
* hiding the **last visible** tab answers ``95201 server error`` — a message that names
  nothing at all, so the refusal is made here, with a real one.
* a **hidden tab's values are still fully readable through this library** (probed: written and
  read back **while hidden**). That is the premise of the hide disclosure.
* **``metainfo`` does not report ``hidden`` at all** — not even for a tab that IS hidden (its
  sheet objects carry only ``columnCount`` / ``frozenColCount`` / ``frozenRowCount`` /
  ``index`` / ``rowCount`` / ``sheetId`` / ``title``). Only the **v3 tab query** carries
  ``hidden``. So the hide/show verification leg is the v3 tab query — the same leg reorder and
  retitle use — and this issue's mint statement that hide would ride a "metainfo hidden leg"
  is corrected by the evidence rather than followed.
"""
import ast
import json
from pathlib import Path

import pytest

from log_reading_apply import reading_the_log
from larkdocio.errors import LarkAPIError

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src" / "larkdocio"
_CAPTURE_PATH = (_ROOT / "tests" / "captures" / "sheets-tab-presentation-probe" / "captures"
                 / "01-updateSheet-index-title-hidden.json")
_FREEZE_CAPTURE_PATH = (_ROOT / "tests" / "captures" / "sheets-freeze-probe" / "captures"
                        / "02-updateSheet-PATCH-invariant-and-EDGES.json")

TOKEN = "shtLD187TOKEN"
SID = "2swukM"          # the probe's own "Beta"


def _capture():
    return json.loads(_CAPTURE_PATH.read_text(encoding="utf-8"))


def _step(prefix, capture_path=_CAPTURE_PATH):
    """The probe step whose label starts with ``prefix`` — looked up by MEANING, so inserting
    a step into the probe cannot silently repoint a test at a different call."""
    steps = [s for s in json.loads(capture_path.read_text(encoding="utf-8"))["steps"]
             if s["label"].startswith(prefix)]
    assert len(steps) == 1, f"{prefix!r} matched {len(steps)} steps"
    return steps[0]


# --------------------------------------------------------------------------- #
# The duck-typed write-client double — the tab set, and `updateSheet` applied    #
# exactly as the probe characterized it.                                        #
# --------------------------------------------------------------------------- #

class TabGateway:
    """A spreadsheet's tab list behind the client seam the engine actually calls.

    ``batch_update_sheets`` reproduces the **probed** semantics, not a guess: ``index`` is a
    target position applied as remove-then-insert (and an out-of-range index is CLAMPED, code
    0, never an error), ``title`` is refused ``90210`` on an exact case-sensitive collision and
    ``90207`` when empty, ``hidden`` is refused ``95201`` when it would hide the last visible
    tab, and a request that changes nothing does **not** bump the revision.
    """

    def __init__(self, *, revision=11, tabs=None, query_error=None, batch_error=None,
                 query_error_after=None, drop_hidden_key=False, drop_tab_after=None):
        self.revision = revision
        self.tabs = [dict(t) for t in (tabs or [
            {"sheet_id": "2szEoE", "title": "Gamma", "index": 0, "hidden": False},
            {"sheet_id": "2sCs5a", "title": "Delta", "index": 1, "hidden": False},
            {"sheet_id": SID, "title": "Beta", "index": 2, "hidden": False},
            {"sheet_id": "4b399c", "title": "Sheet1", "index": 3, "hidden": False},
        ])]
        self.query_error = query_error
        self.query_error_after = query_error_after
        self.drop_hidden_key = drop_hidden_key
        self.drop_tab_after = drop_tab_after
        self.batch_error = batch_error
        self.calls = []
        self.batch_bodies = []
        self._wrote = False

    # -- reads ----------------------------------------------------------- #

    def read_revision(self, spreadsheet_token):
        self.calls.append(("read_revision",))
        return self.revision

    def query_tabs(self, spreadsheet_token):
        self.calls.append(("query_tabs",))
        if self.query_error is not None:
            raise self.query_error
        if self._wrote and self.query_error_after is not None:
            raise self.query_error_after
        out = []
        for t in sorted(self.tabs, key=lambda t: t["index"]):
            if self._wrote and t["sheet_id"] == self.drop_tab_after:
                continue
            record = {"sheet_id": t["sheet_id"], "title": t["title"], "index": t["index"],
                      "row_count": 200, "column_count": 20, "merges": [],
                      "hidden": t["hidden"]}
            if self.drop_hidden_key:
                record["hidden"] = None
            out.append(record)
        return out

    def read_sheet_geometry(self, spreadsheet_token, sheet_id):
        self.calls.append(("read_sheet_geometry", sheet_id))
        return {"row_count": 200, "column_count": 20, "merges": []}

    # -- the ONE write seam (already shipped for the tab family) --------- #

    def batch_update_sheets(self, spreadsheet_token, requests):
        self.calls.append(("batch_update_sheets", tuple(next(iter(r)) for r in requests)))
        self.batch_bodies.append([dict(r) for r in requests])
        self._wrote = True
        if self.batch_error is not None:
            raise self.batch_error
        replies = []
        changed = False
        for req in requests:
            props = dict((req.get("updateSheet") or {}).get("properties") or {})
            tab = next((t for t in self.tabs if t["sheet_id"] == props.get("sheetId")), None)
            if tab is None:
                raise LarkAPIError("Code 90215, Msg: sheetId not found")
            if "index" in props:
                target = min(max(props["index"], 0), len(self.tabs) - 1)   # CLAMPED (probed)
                order = [t for t in sorted(self.tabs, key=lambda t: t["index"])
                         if t is not tab]
                order.insert(target, tab)
                for position, t in enumerate(order):
                    changed = changed or t["index"] != position
                    t["index"] = position
            if "title" in props:
                if not props["title"]:
                    raise LarkAPIError("Code 90207, Msg: sheetTitle should not be empty")
                if any(t["title"] == props["title"] and t is not tab for t in self.tabs):
                    raise LarkAPIError(
                        "Code 90210, Msg: sheetTitle already exist in snapshot")
                changed = changed or tab["title"] != props["title"]
                tab["title"] = props["title"]
            if "hidden" in props:
                if props["hidden"] and not any(
                        not t["hidden"] for t in self.tabs if t is not tab):
                    raise LarkAPIError("Code 95201, Msg: server error")
                changed = changed or tab["hidden"] != props["hidden"]
                tab["hidden"] = props["hidden"]
            replies.append({"updateSheet": {"properties": dict(props)}})
        if changed:
            self.revision += 1
        return {"replies": replies}

    # -- introspection --------------------------------------------------- #

    def writes(self):
        return [c for c in self.calls if c[0] == "batch_update_sheets"]

    def order(self):
        return [(t["index"], t["sheet_id"], t["title"], t["hidden"])
                for t in sorted(self.tabs, key=lambda t: t["index"])]


def _plan(requests, gw, token=TOKEN, **kwargs):
    from larkdocio.sheets.write_apply import dry_run

    return dry_run(requests, gw, token, **kwargs)


# =========================================================================== #
# AC1 — THE SHARED `updateSheet` SEAM: EXTENDED, NEVER DUPLICATED.              #
# =========================================================================== #

def _dict_literals_with_key(key):
    """Every ``{... "<key>": ...}`` dict LITERAL in the shipped package, as
    ``(relative path, lineno, enclosing def)``. A docstring that merely mentions the key is
    not a match — only a real dict key is."""
    found = []
    for path in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        scopes = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                for child in ast.walk(node):
                    scopes.setdefault(id(child), node.name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            if any(isinstance(k, ast.Constant) and k.value == key for k in node.keys):
                found.append((str(path.relative_to(_SRC)), node.lineno,
                              scopes.get(id(node))))
    return found


def test_the_updateSheet_element_is_built_in_exactly_ONE_place():
    """AC1's structural teeth. This test **would fail if a second request builder were
    introduced** — which is precisely what keeps the freeze family's seam from forking now
    that a second family rides it."""
    sites = _dict_literals_with_key("updateSheet")
    assert len(sites) == 1, (
        f"the `updateSheet` wire element must be assembled in ONE place; found {sites}")
    (path, _lineno, scope) = sites[0]
    # LD-224 split ``sheets/requests.py`` into a package; the ONE place is unchanged in
    # kind and in scope — only its file name moved, to the tab family's own module.
    assert path == "sheets/requests/_tabs.py", path
    assert scope == "update_sheet_element", scope


def test_every_updateSheet_family_request_goes_through_the_shared_builder():
    """Behavioural half of AC1: each request's ``request_element`` IS the shared builder's
    output over its own validated ``properties`` — freeze included, so the seam is genuinely
    shared and not merely adjacent."""
    from larkdocio.sheets.requests import (
        FreezePanes,
        ReorderTab,
        RetitleTab,
        SetTabVisibility,
        update_sheet_element,
    )

    for request in (FreezePanes(SID, rows=2), FreezePanes.unfreeze(SID),
                    ReorderTab(SID, 0), RetitleTab(SID, "Q3"),
                    SetTabVisibility.hide(SID), SetTabVisibility.show(SID)):
        assert request.descriptor()["request_element"] == update_sheet_element(
            request.properties), type(request).__name__


def test_the_shared_builder_copies_its_properties_so_a_request_cannot_be_mutated_later():
    from larkdocio.sheets.requests import ReorderTab, update_sheet_element

    request = ReorderTab(SID, 1)
    element = update_sheet_element(request.properties)
    element["updateSheet"]["properties"]["index"] = 99
    assert request.properties["index"] == 1


def test_no_second_sheets_batch_update_CALL_SHAPE_exists():
    """Every ``batch_update_sheets`` call in the package passes exactly the one element the
    request itself owns — ``[desc["request_element"]]``. A second body assembler anywhere would
    show up here as a third call shape."""
    shapes = []
    for path in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "batch_update_sheets"):
                continue
            shapes.append((str(path.relative_to(_SRC)), ast.unparse(node.args[1])))
    assert shapes, "the tab families must still reach the shipped batch endpoint"
    assert {shape for (_path, shape) in shapes} == {"[desc['request_element']]"}, shapes


def test_the_three_presentation_writes_flow_dry_run_to_apply_through_the_SHIPPED_endpoint():
    from larkdocio.sheets.requests import ReorderTab, RetitleTab, SetTabVisibility
    from larkdocio.sheets.write_apply import apply
    apply = reading_the_log(apply)

    for request, op in ((ReorderTab(SID, 0), "reorder-tab"),
                        (RetitleTab(SID, "Renamed"), "retitle-tab"),
                        (SetTabVisibility.hide(SID), "set-tab-visibility")):
        gw = TabGateway()
        plan = _plan([request], gw)
        entry = plan.entries[0]
        assert entry.is_resolved, entry.to_dict()
        assert entry.write_kind == "tab", entry.write_kind
        assert entry.structural["op"] == op
        assert gw.writes() == [], "dry_run must not write"

        log = apply(plan, gw)
        assert [e.to_dict()["outcome"] for e in log.entries] == ["applied"], op
        assert gw.writes() == [("batch_update_sheets", ("updateSheet",))], op
        assert gw.batch_bodies == [[request.descriptor()["request_element"]]], op


def test_a_presentation_plan_cannot_be_forged():
    from larkdocio.sheets.plan import Plan

    with pytest.raises(Exception):
        Plan([], revision=1, spreadsheet_token=TOKEN)


def test_a_stale_spreadsheet_refuses_every_presentation_write_and_writes_nothing():
    from larkdocio.sheets.requests import ReorderTab, RetitleTab, SetTabVisibility
    from larkdocio.sheets.write_apply import apply
    apply = reading_the_log(apply)

    for request in (ReorderTab(SID, 0), RetitleTab(SID, "Renamed"),
                    SetTabVisibility.hide(SID)):
        gw = TabGateway(revision=11)
        plan = _plan([request], gw)
        gw.revision = 12                  # somebody else wrote between plan and apply
        log = apply(plan, gw)
        assert log.entries[0].refusal.reason == "stale-sheet"
        assert gw.writes() == []


# =========================================================================== #
# AC2 — THE SHIPPED `WriteOpKind.TAB`, REUSED. NO NEW OP KIND, NO NEW ROW.      #
# =========================================================================== #

def test_the_presentation_writes_are_the_SHIPPED_tab_op_kind():
    from larkdocio.sheets.requests import (
        ReorderTab,
        RetitleTab,
        SetTabVisibility,
        WriteOpKind,
    )

    for request in (ReorderTab(SID, 0), RetitleTab(SID, "Q3"), SetTabVisibility.hide(SID)):
        assert request.op_kinds == (WriteOpKind.TAB,), type(request).__name__
        assert request.write_kind == "tab"


def test_NO_new_op_kind_was_added():
    """AC2's conservative call, pinned: the op-kind vocabulary is exactly what shipped."""
    from larkdocio.sheets.requests import WriteOpKind

    kinds = {name: value for name, value in vars(WriteOpKind).items()
             if name.isupper() and isinstance(value, str)}
    assert set(kinds.values()) == {
        "value", "style", "number-format", "merge", "structure", "tab", "data-validation",
        "dimension-property", "freeze-panes"}, kinds


def test_the_tab_leg_stays_off_the_style_leg_and_the_merge_leg():
    from larkdocio.sheets.requests import (
        MERGE_LEG_OP_KINDS,
        STYLE_LEG_OP_KINDS,
        WriteOpKind,
        certify_gate_legs,
        effective_verify_style,
        requires_merge_leg,
        requires_style_leg,
    )

    kinds = (WriteOpKind.TAB,)
    assert requires_style_leg(kinds) is False
    assert requires_merge_leg(kinds) is False
    assert effective_verify_style(kinds) is False
    assert WriteOpKind.TAB not in STYLE_LEG_OP_KINDS
    assert WriteOpKind.TAB not in MERGE_LEG_OP_KINDS
    # the tab leg certifies a presentation write with the cheap values leg alone
    certify_gate_legs(kinds, values_leg_ran=True)


def test_the_tab_family_is_ONE_descriptor_carrying_all_six_ops():
    """No near-duplicate registry row: the three new ops join the tab descriptor's own
    ``entry_ops`` rather than minting a second family on the same endpoint."""
    from larkdocio.sheets.ops import OPS

    tab = [d for d in OPS if d.write_kind == "tab"]
    assert len(tab) == 1, [d.kind for d in OPS]
    assert set(tab[0].entry_ops) == {"add-tab", "copy-tab", "delete-tab",
                                     "reorder-tab", "retitle-tab", "set-tab-visibility"}
    assert len(OPS) == 9, [d.kind for d in OPS]   # + the LD-188 style family


# =========================================================================== #
# AC3 — THE VERIFICATION LEG: THE v3 TAB QUERY, FOR ALL THREE FIELDS.           #
#                                                                              #
# The issue's mint expected `hidden` to ride a `metainfo` leg. The evidence     #
# says otherwise, and the evidence wins.                                       #
# =========================================================================== #

def test_metainfo_does_NOT_report_hidden_even_for_a_HIDDEN_tab():
    """The premise correction, proven from BOTH probe families' captures: the freeze probe hid
    a tab and then read ``metainfo``, and the sheet objects carry no ``hidden`` key at all."""
    after_hide = _step("state AFTER hide", _FREEZE_CAPTURE_PATH)["observed"]
    hidden_ids = [s["sheet_id"] for s in after_hide["v3_sheets"] if s.get("hidden")]
    assert hidden_ids, "the freeze probe's hide step must really have hidden a tab"
    for sheet in after_hide["metainfo_sheets"]:
        assert "hidden" not in sheet, sheet

    # and this issue's own probe measured the same thing, key by key
    hide_one = _capture()["HIDE_ONE"]
    assert hide_one["metainfo_reports_hidden"] is False
    assert hide_one["metainfo_keys"] == ["columnCount", "frozenColCount", "frozenRowCount",
                                         "index", "rowCount", "sheetId", "title"]
    assert hide_one["v3_hidden"]["2szEoE"] is True


def test_the_v3_tab_query_is_where_hidden_lives_and_query_tabs_surfaces_it():
    """The write-side tab query gains the field it always carried on the wire — the same
    endpoint, so this costs **zero new HTTP**."""
    from write_harness import _FakeHTTPResponse

    v3 = _step("state AFTER hiding Gamma")["observed"]["v3_sheets"]
    assert any(s["hidden"] for s in v3), "the capture must contain a hidden tab"
    body = {"code": 0, "msg": "success", "data": {"sheets": v3}}

    class _Opener:
        def __init__(self):
            self.urls = []

        def __call__(self, req, timeout=30):
            self.urls.append(req.full_url)
            return _FakeHTTPResponse(body)

    from larkdocio.sheets.write_client import SheetsWriteClient

    opener = _Opener()
    client = SheetsWriteClient("cli", "sec", urlopen=opener,
                               token_fetcher=lambda *a, **k: "t-tok")
    tabs = client.query_tabs(TOKEN)
    assert {t["sheet_id"]: t["hidden"] for t in tabs} == {
        s["sheet_id"]: s["hidden"] for s in v3}
    assert len(opener.urls) == 1 and "sheets/query" in opener.urls[0]


def test_an_ABSENT_hidden_key_is_reported_as_UNKNOWN_never_as_visible():
    """The LD-186 honesty rule, replayed on this field: "I could not find out" and "the tab is
    visible" are different facts and must not collapse."""
    from write_harness import _FakeHTTPResponse
    from larkdocio.sheets.write_client import SheetsWriteClient

    body = {"code": 0, "msg": "success",
            "data": {"sheets": [{"sheet_id": SID, "title": "Beta", "index": 0,
                                 "grid_properties": {"row_count": 200, "column_count": 20}}]}}
    client = SheetsWriteClient(
        "cli", "sec", urlopen=lambda req, timeout=30: _FakeHTTPResponse(body),
        token_fetcher=lambda *a, **k: "t-tok")
    (tab,) = client.query_tabs(TOKEN)
    assert tab["hidden"] is None, tab
    assert tab["hidden"] is not False


@pytest.mark.parametrize(
    "make_request,expect_observed",
    [
        (lambda: __import__("larkdocio.sheets.requests", fromlist=["x"]).ReorderTab(SID, 0),
         {"index": 0, "title": "Beta", "hidden": False}),
        (lambda: __import__("larkdocio.sheets.requests",
                            fromlist=["x"]).RetitleTab(SID, "Beta-2"),
         {"index": 2, "title": "Beta-2", "hidden": False}),
        (lambda: __import__("larkdocio.sheets.requests",
                            fromlist=["x"]).SetTabVisibility.hide(SID),
         {"index": 2, "title": "Beta", "hidden": True}),
    ],
)
def test_every_presentation_write_is_read_back_by_the_v3_TAB_LEG_inside_apply(
        make_request, expect_observed):
    from larkdocio.sheets.ops import TAB_VERIFICATION_LEG
    from larkdocio.sheets.write_apply import apply
    apply = reading_the_log(apply)

    gw = TabGateway()
    log = apply(_plan([make_request()], gw), gw)
    record = log.entries[0].structural
    assert record["verified_by"] == TAB_VERIFICATION_LEG
    assert record["observed"] == expect_observed, record
    # the leg is the ALREADY-DECLARED read seam, run after the write
    assert [c[0] for c in gw.calls].count("query_tabs") >= 2


def test_a_failed_verification_READ_is_recorded_as_unknown_not_as_success():
    from larkdocio.sheets.requests import SetTabVisibility
    from larkdocio.sheets.write_apply import apply
    apply = reading_the_log(apply)

    gw = TabGateway(query_error_after=LarkAPIError("Code 99991672, Msg: no permission"))
    log = apply(_plan([SetTabVisibility.hide(SID)], gw), gw)
    record = log.entries[0].structural
    assert record["observed"] is None
    assert "99991672" in record["observation_note"]


def test_a_tab_ABSENT_from_the_read_back_is_recorded_as_unknown_not_as_visible():
    from larkdocio.sheets.requests import RetitleTab
    from larkdocio.sheets.write_apply import apply
    apply = reading_the_log(apply)

    gw = TabGateway(drop_tab_after=SID)
    log = apply(_plan([RetitleTab(SID, "Beta-2")], gw), gw)
    record = log.entries[0].structural
    assert record["observed"] is None
    assert SID in record["observation_note"]


def test_an_unknown_hidden_state_is_not_laundered_into_visible_by_the_leg():
    from larkdocio.sheets.requests import ReorderTab
    from larkdocio.sheets.write_apply import apply
    apply = reading_the_log(apply)

    gw = TabGateway(drop_hidden_key=True)
    log = apply(_plan([ReorderTab(SID, 0)], gw), gw)
    assert log.entries[0].structural["observed"]["hidden"] is None


def test_the_add_copy_delete_arms_are_untouched_by_this_issue():
    """The shipped half of the family keeps its own log shape — this issue extends the seam,
    it does not rewrite what LD-122 shipped."""
    from larkdocio.sheets.requests import AddTab
    from larkdocio.sheets.write_apply import apply
    apply = reading_the_log(apply)

    gw = TabGateway()
    log = apply(_plan([AddTab("Fresh")], gw), gw)
    record = log.entries[0].structural
    assert record["op"] == "add-tab"
    assert "verified_by" not in record


# =========================================================================== #
# AC4 — HIDE CARRIES A FIDELITY DISCLOSURE.                                     #
# =========================================================================== #

def test_the_capture_PROVES_a_hidden_tab_is_still_readable_through_the_library():
    """The disclosure's premise, measured live rather than asserted: values were written to a
    tab **while it was hidden** and read straight back through the shipped client."""
    assert _capture()["HIDDEN_TAB_STILL_READABLE"]["values"] == [["hidden-1"], ["hidden-2"]]


def test_HIDE_carries_the_note_and_SHOW_carries_none():
    from larkdocio.sheets.requests import SetTabVisibility

    gw = TabGateway()
    (note,) = _plan([SetTabVisibility.hide(SID)], gw).entries[0].preview_notes
    assert note["kind"] == "hidden-tab-fidelity"
    assert note["sheet_id"] == SID
    assert note["title"] == "Beta"
    assert note["hidden"] is True

    shown = TabGateway(tabs=[{"sheet_id": SID, "title": "Beta", "index": 0, "hidden": True},
                             {"sheet_id": "other", "title": "Other", "index": 1,
                              "hidden": False}])
    assert _plan([SetTabVisibility.show(SID)], shown).entries[0].preview_notes == ()


def test_the_hide_note_states_the_data_stays_READABLE_and_is_not_removed():
    from larkdocio.sheets.requests import SetTabVisibility

    gw = TabGateway()
    (note,) = _plan([SetTabVisibility.hide(SID)], gw).entries[0].preview_notes
    text = note["note"]
    assert "fidelity event, not a formatting change" in text
    assert "still" in text and "readable" in text.lower()
    assert "NOT deleted" in text
    # hiding is not protecting and not removing — said in as many words
    assert "protect" in text and "remove" in text


def test_the_hide_note_speaks_the_SHIPPED_disclosure_vocabulary():
    """AC4's wording constraint: the note quotes the vocabulary the dimension-hide disclosure
    already ships rather than coining a second one."""
    from larkdocio.sheets.ops import hidden_dimension_note, hidden_tab_note

    dimension = hidden_dimension_note({"hides": True, "start_index": 5, "end_index": 5,
                                       "major_dimension": "ROWS"})["note"]
    tab = hidden_tab_note({"op": "set-tab-visibility", "sheet_id": SID, "hidden": True},
                          {"sheet_id": SID, "title": "Beta", "hidden": False})["note"]
    for phrase in ("a fidelity event, not a formatting change",
                   "The data is NOT deleted",
                   "reader still emits it"):
        assert phrase in dimension, phrase
        assert phrase in tab, phrase


def test_the_hide_note_carries_no_issue_ids_or_internal_dialect():
    from larkdocio.sheets.requests import RetitleTab, SetTabVisibility

    gw = TabGateway()
    for request in (SetTabVisibility.hide(SID), RetitleTab(SID, "Beta-2")):
        (note,) = _plan([request], TabGateway()).entries[0].preview_notes
        text = note["note"]
        assert "LD-" not in text and "AC" not in text.replace("ACCEPT", "")
        assert "probe" not in text.lower() or "probed" in text.lower()
    assert gw.writes() == []


def test_hiding_an_ALREADY_hidden_tab_is_disclosed_as_a_no_op_not_as_a_new_hide():
    from larkdocio.sheets.requests import SetTabVisibility

    gw = TabGateway(tabs=[{"sheet_id": SID, "title": "Beta", "index": 0, "hidden": True},
                          {"sheet_id": "other", "title": "Other", "index": 1,
                           "hidden": False}])
    (note,) = _plan([SetTabVisibility.hide(SID)], gw).entries[0].preview_notes
    assert note["kind"] == "hidden-tab-fidelity"
    assert note["already"] is True
    assert "already" in note["note"].lower()


# =========================================================================== #
# AC5 — RETITLE CARRIES A JOIN-BREAKAGE DISCLOSURE.                             #
# =========================================================================== #

def test_the_capture_PROVES_a_retitle_leaves_the_sheet_id_UNCHANGED():
    plain = _capture()["RETITLE_PLAIN"]
    assert plain["sheet_id_survived"] is True
    assert plain["reply"] == [{"updateSheet": {"properties": {"sheetId": "2sCs5a",
                                                             "title": "Delta-renamed"}}}]


def test_the_retitle_note_names_BOTH_titles_and_says_the_sheet_id_is_the_stable_handle():
    from larkdocio.sheets.requests import RetitleTab

    gw = TabGateway()
    (note,) = _plan([RetitleTab(SID, "Q3 actuals")], gw).entries[0].preview_notes
    assert note["kind"] == "retitle-breaks-title-joins"
    assert note["old_title"] == "Beta"
    assert note["new_title"] == "Q3 actuals"
    assert note["sheet_id"] == SID
    assert note["sheet_id_unchanged"] is True
    text = note["note"]
    assert "Beta" in text and "Q3 actuals" in text
    assert SID in text
    assert "stale" in text
    assert "unchanged" in text
    assert gw.writes() == []


def test_a_retitle_to_the_tab_s_OWN_current_title_is_a_no_op_not_a_broken_join():
    from larkdocio.sheets.requests import RetitleTab

    gw = TabGateway()
    (note,) = _plan([RetitleTab(SID, "Beta")], gw).entries[0].preview_notes
    assert note["kind"] == "tab-presentation-no-op"
    assert "no-op" in note["note"] or "nothing" in note["note"]


# =========================================================================== #
# AC6 — REFUSALS, WITH THE API'S OWN ANSWERS CHARACTERIZED NOT ASSUMED.          #
# =========================================================================== #

def test_a_negative_index_cannot_be_BUILT_and_quotes_the_probed_body():
    from larkdocio.sheets.requests import ReorderTab, TabPresentationError

    probed = _step("G) index=-1")
    assert probed["code"] == 90204
    with pytest.raises(TabPresentationError) as exc:
        ReorderTab(SID, -1)
    assert probed["msg"] in str(exc.value)
    assert "ReorderTab(" in str(exc.value)         # an exampled repair


@pytest.mark.parametrize("bad", [True, False, 1.5, "0", None])
def test_a_non_whole_index_cannot_be_BUILT(bad):
    from larkdocio.sheets.requests import ReorderTab, TabPresentationError

    with pytest.raises(TabPresentationError):
        ReorderTab(SID, bad)


def test_an_EMPTY_title_cannot_be_BUILT_and_quotes_the_probed_body():
    from larkdocio.sheets.requests import RetitleTab, TabPresentationError

    probed = _step("K) title=''")
    assert probed["code"] == 90207
    with pytest.raises(TabPresentationError) as exc:
        RetitleTab(SID, "")
    assert probed["msg"] in str(exc.value)
    assert "RetitleTab(" in str(exc.value)


@pytest.mark.parametrize("bad", ["   ", "\t", None, 7, True])
def test_a_whitespace_only_or_non_string_title_cannot_be_BUILT(bad):
    from larkdocio.sheets.requests import RetitleTab, TabPresentationError

    with pytest.raises(TabPresentationError):
        RetitleTab(SID, bad)


def test_a_non_bool_visibility_cannot_be_BUILT():
    from larkdocio.sheets.requests import SetTabVisibility, TabPresentationError

    for bad in (1, 0, "true", None):
        with pytest.raises(TabPresentationError):
            SetTabVisibility(SID, bad)


def test_an_index_past_the_last_tab_refuses_at_PLAN_time_with_ZERO_calls_on_the_wire():
    """Lark ACCEPTS this and silently clamps (probed, ``code 0``) — which is exactly why the
    refusal is made here: a silent clamp means the stated intent is not what happened."""
    from larkdocio.sheets.plan import Refusal
    from larkdocio.sheets.requests import ReorderTab
    from larkdocio.sheets.write_apply import apply
    apply = reading_the_log(apply)

    clamped = _capture()["INDEX_OUT_OF_RANGE"]
    assert clamped["at_count"]["code"] == 0 and clamped["far"]["code"] == 0

    gw = TabGateway()
    plan = _plan([ReorderTab(SID, 4)], gw)               # 4 tabs → 0..3 are the legal indices
    entry = plan.entries[0]
    assert entry.refusal.reason == Refusal.TAB_INDEX_OUT_OF_RANGE
    detail = entry.refusal.detail
    assert "4" in detail and "3" in detail               # asked, and the last legal index
    assert "clamp" in detail.lower()
    assert gw.writes() == []
    apply(plan, gw)
    assert gw.writes() == [], "a refused reorder must not reach the wire at apply either"


def test_a_DUPLICATE_title_refuses_at_PLAN_time_quoting_the_probed_body():
    from larkdocio.sheets.plan import Refusal
    from larkdocio.sheets.requests import RetitleTab
    from larkdocio.sheets.write_apply import apply
    apply = reading_the_log(apply)

    probed = _step("I) title='Gamma'")
    assert probed["code"] == 90210

    gw = TabGateway()
    plan = _plan([RetitleTab(SID, "Gamma")], gw)         # 'Gamma' is another tab's title
    entry = plan.entries[0]
    assert entry.refusal.reason == Refusal.DUPLICATE_TAB_TITLE
    assert probed["msg"] in entry.refusal.detail
    assert "2szEoE" in entry.refusal.detail              # WHICH tab already holds it
    assert gw.writes() == []
    apply(plan, gw)
    assert gw.writes() == []


def test_a_CASE_ONLY_difference_is_ACCEPTED_because_lark_accepts_it():
    """The probed nuance a casefolded check would have got wrong: Lark's uniqueness test is
    case-SENSITIVE, so ``gamma`` beside ``Gamma`` is a legal retitle (``code 0``)."""
    from larkdocio.sheets.requests import RetitleTab
    from larkdocio.sheets.write_apply import apply
    apply = reading_the_log(apply)

    probed = _step("J) title='gamma'")
    assert probed["code"] == 0

    gw = TabGateway()
    plan = _plan([RetitleTab(SID, "gamma")], gw)
    assert plan.entries[0].is_resolved, plan.entries[0].to_dict()
    apply(plan, gw)
    assert dict((t["sheet_id"], t["title"]) for t in gw.tabs)[SID] == "gamma"


def test_hiding_the_LAST_visible_tab_refuses_at_PLAN_time_quoting_the_probed_body():
    from larkdocio.sheets.plan import Refusal
    from larkdocio.sheets.requests import SetTabVisibility
    from larkdocio.sheets.write_apply import apply
    apply = reading_the_log(apply)

    hide_all = _capture()["HIDE_ALL"]
    last = hide_all["attempts"][-1]
    assert last["code"] == 95201 and last["msg"] == "server error"
    assert len(hide_all["visible_left"]) == 1, "one tab must stay visible, live"

    gw = TabGateway(tabs=[{"sheet_id": SID, "title": "Beta", "index": 0, "hidden": False},
                          {"sheet_id": "hidden1", "title": "H1", "index": 1, "hidden": True}])
    plan = _plan([SetTabVisibility.hide(SID)], gw)
    entry = plan.entries[0]
    assert entry.refusal.reason == Refusal.LAST_VISIBLE_TAB
    assert "95201" in entry.refusal.detail
    assert "server error" in entry.refusal.detail
    assert gw.writes() == []
    apply(plan, gw)
    assert gw.writes() == []


def test_hiding_the_ONLY_tab_of_a_single_tab_spreadsheet_refuses_the_same_way():
    from larkdocio.sheets.plan import Refusal
    from larkdocio.sheets.requests import SetTabVisibility

    gw = TabGateway(tabs=[{"sheet_id": SID, "title": "Beta", "index": 0, "hidden": False}])
    entry = _plan([SetTabVisibility.hide(SID)], gw).entries[0]
    assert entry.refusal.reason == Refusal.LAST_VISIBLE_TAB
    assert gw.writes() == []


def test_hide_is_NOT_refused_when_another_tab_s_visibility_is_UNKNOWN():
    """The refusal must rest on proof. A tab whose ``hidden`` state could not be read is
    **possibly visible**, so the hide is allowed rather than refused on a guess."""
    from larkdocio.sheets.requests import SetTabVisibility

    gw = TabGateway(drop_hidden_key=True,
                    tabs=[{"sheet_id": SID, "title": "Beta", "index": 0, "hidden": False},
                          {"sheet_id": "unknown1", "title": "U", "index": 1, "hidden": True}])
    entry = _plan([SetTabVisibility.hide(SID)], gw).entries[0]
    assert entry.is_resolved, entry.to_dict()


def test_a_title_at_101_characters_is_NOT_refused_because_no_limit_was_FOUND():
    """The library invents no ceiling: both 100 and 101 characters answered ``code 0`` and the
    101-character title really landed (probed)."""
    from larkdocio.sheets.requests import RetitleTab

    length = _capture()["RETITLE_LENGTH"]
    assert length["at_100"]["code"] == 0 and length["at_101"]["code"] == 0
    assert 101 in length["title_lengths_after"]

    gw = TabGateway()
    assert _plan([RetitleTab(SID, "L" * 101)], gw).entries[0].is_resolved


def test_an_unknown_sheet_id_refuses_UNKNOWN_TAB_with_a_did_you_mean():
    from larkdocio.sheets.plan import Refusal
    from larkdocio.sheets.requests import ReorderTab, RetitleTab, SetTabVisibility

    for request in (ReorderTab("zzzz99", 0), RetitleTab("zzzz99", "X"),
                    SetTabVisibility.hide("zzzz99")):
        gw = TabGateway()
        entry = _plan([request], gw).entries[0]
        assert entry.refusal.reason == Refusal.UNKNOWN_TAB, entry.to_dict()
        assert "Beta" in entry.refusal.detail          # the did-you-mean listing
        assert gw.writes() == []


def test_an_unreadable_tab_set_refuses_rather_than_writing_blind():
    from larkdocio.sheets.requests import SetTabVisibility

    gw = TabGateway(query_error=LarkAPIError("Code 99991672, Msg: no permission"))
    entry = _plan([SetTabVisibility.hide(SID)], gw).entries[0]
    assert entry.refusal is not None
    assert gw.writes() == []


# =========================================================================== #
# AC7 — REORDER SEMANTICS, PINNED AGAINST THE LIVE CHARACTERIZATION.            #
# =========================================================================== #

def test_index_is_a_TARGET_POSITION_not_a_delta():
    """The AC7 answer, straight off the capture: a tab at index 0 asked for ``index: 2`` ends
    at **2**. Under a delta reading it would have ended at 2 only by coincidence — the second
    arm (a tab at 1 asked for 3, landing at 3) removes the coincidence."""
    cap = _capture()
    assert cap["BASELINE_ORDER"][0][1:3] == ["2sCs5a", "Delta"]      # Delta at index 0

    middle = cap["INDEX_TO_MIDDLE"]
    assert middle["asked_index"] == 2
    assert [row[1] for row in middle["order"]] == ["2szEoE", "2swukM", "2sCs5a", "4b399c"]
    assert next(row[0] for row in middle["order"] if row[1] == "2sCs5a") == 2

    last = cap["INDEX_TO_LAST"]
    assert last["asked_index"] == 3 and last["tab_count"] == 4
    assert next(row[0] for row in last["order"] if row[1] == "2swukM") == 3


def test_the_tabs_a_reorder_passes_CLOSE_THE_GAP():
    """How the *other* indices shift — the second half of AC7. Delta leaving index 0 pulls
    Gamma and Beta up by one; nothing is left with a hole or a duplicate index."""
    order = _capture()["INDEX_TO_MIDDLE"]["order"]
    assert [row[0] for row in order] == [0, 1, 2, 3]
    assert [row[1] for row in order][:2] == ["2szEoE", "2swukM"]      # both moved up


def test_a_NO_OP_reorder_is_accepted_and_does_not_even_bump_the_revision():
    """The amplifier's decision, pinned in both directions: Lark accepts it and the revision
    does **not** move (unlike a no-op freeze, which bumps it), so this library accepts it too
    and discloses it as a no-op instead of refusing."""
    noop = _capture()["INDEX_NOOP"]
    assert noop["revision_moved"] is False

    from larkdocio.sheets.requests import ReorderTab
    from larkdocio.sheets.write_apply import apply
    apply = reading_the_log(apply)

    gw = TabGateway()
    plan = _plan([ReorderTab(SID, 2)], gw)               # Beta already sits at index 2
    entry = plan.entries[0]
    assert entry.is_resolved
    (note,) = entry.preview_notes
    assert note["kind"] == "tab-presentation-no-op"
    before = gw.revision
    apply(plan, gw)
    assert gw.revision == before, "a no-op reorder must not be reported as a revision bump"


@pytest.mark.parametrize("target,expected_first", [(0, SID), (3, "2szEoE"), (1, "2szEoE")])
def test_reorder_to_first_middle_and_last_all_land_where_asked(target, expected_first):
    from larkdocio.sheets.requests import ReorderTab
    from larkdocio.sheets.write_apply import apply
    apply = reading_the_log(apply)

    gw = TabGateway()
    apply(_plan([ReorderTab(SID, target)], gw), gw)
    assert next(t["index"] for t in gw.tabs if t["sheet_id"] == SID) == target
    assert gw.order()[0][1] == expected_first
    assert sorted(t["index"] for t in gw.tabs) == [0, 1, 2, 3]


def test_the_reorder_preview_declares_the_convention_it_uses():
    from larkdocio.sheets.requests import ReorderTab

    preview = ReorderTab(SID, 2).presentation_preview()
    assert preview["kind"] == "reorder-tab"
    assert preview["index"] == 2
    assert preview["index_is_target_position"] is True
    assert preview["zero_based"] is True
    assert preview["changes_values"] is False


# =========================================================================== #
# The amplifier's remaining arms: one batch vs two, hide/show idempotence.       #
# =========================================================================== #

def test_a_reorder_AND_a_retitle_in_ONE_plan_both_land():
    from larkdocio.sheets.requests import ReorderTab, RetitleTab
    from larkdocio.sheets.write_apply import apply
    apply = reading_the_log(apply)

    assert _capture()["ONE_BATCH_PAIR"]["code"] == 0
    gw = TabGateway()
    log = apply(_plan([ReorderTab(SID, 0), RetitleTab(SID, "Beta-2")], gw), gw)
    assert [e.to_dict()["outcome"] for e in log.entries] == ["applied", "applied"]
    tab = next(t for t in gw.tabs if t["sheet_id"] == SID)
    assert (tab["index"], tab["title"]) == (0, "Beta-2")


def test_the_same_pair_in_TWO_plans_lands_the_same_way():
    from larkdocio.sheets.requests import ReorderTab, RetitleTab
    from larkdocio.sheets.write_apply import apply
    apply = reading_the_log(apply)

    gw = TabGateway()
    apply(_plan([ReorderTab(SID, 0)], gw), gw)
    apply(_plan([RetitleTab(SID, "Beta-2")], gw), gw)
    tab = next(t for t in gw.tabs if t["sheet_id"] == SID)
    assert (tab["index"], tab["title"]) == (0, "Beta-2")


def test_hide_then_show_is_IDEMPOTENT_and_a_repeat_is_a_no_op_live_too():
    idem = _capture()["HIDE_SHOW_IDEMPOTENCE"]
    rev = idem["revisions"]
    assert rev[0] == rev[1], "a repeated hide did not bump the revision, live"
    assert rev[2] == rev[3], "a repeated show did not bump the revision, live"
    assert all(hidden is False for hidden in idem["v3_hidden"].values())

    from larkdocio.sheets.requests import SetTabVisibility
    from larkdocio.sheets.write_apply import apply
    apply = reading_the_log(apply)

    gw = TabGateway()
    apply(_plan([SetTabVisibility.hide(SID)], gw), gw)
    assert next(t["hidden"] for t in gw.tabs if t["sheet_id"] == SID) is True
    apply(_plan([SetTabVisibility.hide(SID)], gw), gw)
    apply(_plan([SetTabVisibility.show(SID)], gw), gw)
    apply(_plan([SetTabVisibility.show(SID)], gw), gw)
    assert next(t["hidden"] for t in gw.tabs if t["sheet_id"] == SID) is False


def test_a_presentation_write_moves_no_cell_and_no_geometry():
    from larkdocio.sheets.requests import ReorderTab, RetitleTab, SetTabVisibility

    assert _capture()["VALUES_UNMOVED"]["first_tab"] == [["a"], ["b"], ["c"]]
    for request in (ReorderTab(SID, 0), RetitleTab(SID, "X"), SetTabVisibility.hide(SID)):
        preview = request.presentation_preview()
        assert preview["changes_values"] is False
        assert preview["changes_geometry"] is False
        assert preview["changes_merges"] is False
        assert request.is_structural is False


def test_the_public_names_are_re_exported_from_the_write_apply_facade():
    import larkdocio.sheets.write_apply as facade

    for name in ("ReorderTab", "RetitleTab", "SetTabVisibility", "TabPresentationError",
                 "update_sheet_element", "TAB_VERIFICATION_LEG"):
        assert hasattr(facade, name), name
