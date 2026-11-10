"""LD-186 — FREEZE PANES through the shipped ``sheets_batch_update`` gate, **and the
``metainfo`` frozen READ leg that makes a freeze verifiable at all**.

The backlog's stated precondition for this issue was **false**. It claimed larkdocio already
read ``frozen_*_count`` in tab metadata; ``grep -rl "frozen_" src/`` was **empty** on the
``develop`` this branch forked from, and ``SHEETS.md``'s ``frozen / hidden (non-filter)`` row
was ``uncaptured`` on the read axis. So a freeze write had **nothing to diff against** — which
is why the read leg ships here, with the write, rather than being assumed.

Every arm in this file is **offline**: an injected transport / a duck-typed client seam. The
payload shapes are the ones the live probe actually observed
(``tests/captures/sheets-freeze-probe/captures/``, two self-provisioned disposables, ``finally``-deleted
with a gone-confirm), read back out of the captures here rather than re-typed by hand, so an
API drift reddens the suite instead of silently corrupting a plan.

What the probe established, and what each fact costs if it is guessed wrong:

* ``metainfo`` carries sheet-level ``frozenRowCount`` / ``frozenColCount`` (camelCase) beside
  ``rowCount`` / ``columnCount`` — one read answers "what is frozen" AND "what fits".
* the v3 tab query carries the same two counts under ``grid_properties``, snake_cased.
* ``updateSheet`` is a **PATCH**: naming one axis leaves the other axis, the title, the index
  and the tab's ``hidden`` flag untouched. A REPLACE reading would silently unfreeze the axis
  a caller did not mention.
* ``frozenRowCount == rowCount`` is **accepted** (all rows frozen); ``rowCount + 1`` is
  refused ``90226 frozenRowCount must less than sheet rowCount``; ``-1`` is refused
  ``90226 frozenRowCount must larger than 0``; ``0`` is accepted and **unfreezes**.
* ``properties`` naming only ``sheetId`` → ``90204 request body is wrong``; a **bool** count
  → ``9499 Invalid parameter type in json: FrozenRowCount``.
* a refused freeze leaves ``revision`` **unmoved**; an accepted one bumps it even when the
  target state equals the current state.
"""
import json
from pathlib import Path

import pytest

from log_reading_apply import reading_the_log
from larkdocio.errors import LarkAPIError
from larkdocio.sheets.client import SheetsReadClient
from larkdocio.sheets.models import (
    FROZEN_ACTIVE,
    FROZEN_NONE,
    FROZEN_NOT_READ,
    FROZEN_UNAVAILABLE,
    FrozenPanes,
    SheetTab,
    parse_frozen_panes,
)

from write_harness import _FakeHTTPResponse

_CAPTURES = Path(__file__).resolve().parent.parent / "tests" / "captures" / "sheets-freeze-probe" / "captures"
_FREEZE_CAPTURE = "01-updateSheet-FREEZE-and-metainfo-frozen-read.json"
_EDGES_CAPTURE = "02-updateSheet-PATCH-invariant-and-EDGES.json"


def _capture(name):
    return json.loads((_CAPTURES / name).read_text(encoding="utf-8"))


def _step(name, label_prefix):
    """The probe step whose label starts with ``label_prefix`` — looked up by MEANING, so
    inserting a step into the probe cannot silently repoint a test at a different call."""
    steps = [s for s in _capture(name)["steps"] if s["label"].startswith(label_prefix)]
    assert len(steps) == 1, f"{label_prefix!r} matched {len(steps)} steps in {name}"
    return steps[0]


# --------------------------------------------------------------------------- #
# Test doubles — the read client's injected transport (the LD-155 pattern).     #
# --------------------------------------------------------------------------- #


class StubOpener:
    """Records each GET and returns the next queued payload."""

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.requests = []

    def __call__(self, req, timeout=30):
        self.requests.append(req.full_url)
        return _FakeHTTPResponse(self._payloads.pop(0))


class RaisingOpener:
    """A transport that fails outright — the graceful-degrade arm."""

    def __init__(self, exc):
        self._exc = exc
        self.requests = []

    def __call__(self, req, timeout=30):
        self.requests.append(req.full_url)
        raise self._exc


class NoLimiter:
    def acquire(self):
        return None


def _read_client(opener):
    return SheetsReadClient(
        "cli_x", "sec_x",
        urlopen=opener,
        token_fetcher=lambda *a, **k: "t-tok",
        rate_limiter=NoLimiter(),
    )


TOKEN = "shtLD186TOKEN"
SID = "966083"


def _metainfo(sheets, revision=7):
    """A ``metainfo`` body in the shape the probe observed."""
    return {"code": 0, "msg": "success",
            "data": {"properties": {"revision": revision, "sheetCount": len(sheets),
                                    "title": "LD-186"},
                     "sheets": list(sheets)}}


def _sheet(sheet_id=SID, *, frozen_rows=0, frozen_cols=0, rows=200, cols=20,
           title="Sheet1", index=0):
    return {"columnCount": cols, "frozenColCount": frozen_cols,
            "frozenRowCount": frozen_rows, "index": index, "rowCount": rows,
            "sheetId": sheet_id, "title": title}


def _tab(sheet_id=SID, title="Sheet1", rows=200, cols=20, index=0):
    return SheetTab(sheet_id=sheet_id, title=title, index=index,
                    row_count=rows, column_count=cols)


# =========================================================================== #
# AC1 — THE `metainfo` FROZEN READ LEG.                                        #
#                                                                              #
# Five arms, exactly as the AC names them: nothing frozen / rows frozen /       #
# columns frozen / both / the read UNAVAILABLE. The fifth is the one that       #
# matters most: a failed read must NOT read as "nothing is frozen" (LD-155).    #
# =========================================================================== #

def test_the_backlog_claim_this_issue_corrects_is_recorded_as_false():
    """The precondition the backlog asserted — "we already read ``frozen_*_count``" — was
    false, and this test is the doc-truth rider for the correction: the frozen read leg is
    LD-186's, and it exists **here**, in ``models`` + both clients."""
    import larkdocio.sheets.models as M

    assert hasattr(M, "parse_frozen_panes"), (
        "the frozen read leg must live in one place, parsing one payload shape family"
    )
    assert {FROZEN_NOT_READ, FROZEN_NONE, FROZEN_ACTIVE, FROZEN_UNAVAILABLE} == {
        "not-read", "none", "active", "unavailable"}, (
        "the frozen state vocabulary quotes the shipped FILTER_* vocabulary (LD-155) rather "
        "than coining a second one"
    )


def test_metainfo_really_carries_the_frozen_counts_in_the_LIVE_capture():
    """The read leg's whole premise, checked against the captured payload rather than the
    backlog's claim: ``metainfo`` reports sheet-level ``frozenRowCount``/``frozenColCount``."""
    before = _step(_FREEZE_CAPTURE, "metainfo BEFORE")["response"]
    sheet = before["data"]["sheets"][0]
    assert {"frozenRowCount", "frozenColCount"} <= set(sheet)
    assert (sheet["frozenRowCount"], sheet["frozenColCount"]) == (0, 0)
    # and the SAME read carries the grid the AC4 bounds check needs — one read, both jobs
    assert (sheet["rowCount"], sheet["columnCount"]) == (200, 20)


def test_the_v3_tab_query_carries_the_same_two_counts_snake_cased():
    """The other payload family the one parser must handle (and the reason the read client's
    already-shipped tab query can surface frozen state for free)."""
    before = _step(_FREEZE_CAPTURE, "v3 sheets/query BEFORE")["response"]
    grid = before["data"]["sheets"][0]["grid_properties"]
    assert {"frozen_row_count", "frozen_column_count"} <= set(grid)


@pytest.mark.parametrize(
    "frozen_rows,frozen_cols,expect_state,expect_is_frozen",
    [
        (0, 0, FROZEN_NONE, False),      # nothing frozen
        (2, 0, FROZEN_ACTIVE, True),     # rows frozen
        (0, 1, FROZEN_ACTIVE, True),     # columns frozen
        (3, 2, FROZEN_ACTIVE, True),     # both
    ],
)
def test_the_frozen_read_reports_all_four_frozen_shapes(frozen_rows, frozen_cols,
                                                        expect_state, expect_is_frozen):
    body = _metainfo([_sheet(frozen_rows=frozen_rows, frozen_cols=frozen_cols)])
    opener = StubOpener([body])
    panes = _read_client(opener).get_frozen_panes(TOKEN)[SID]
    assert (panes.rows, panes.cols) == (frozen_rows, frozen_cols)
    assert panes.is_frozen is expect_is_frozen
    assert len(opener.requests) == 1 and "metainfo" in opener.requests[0]

    # THREE tabs, ONE metainfo call — the read is spreadsheet-scoped, never per tab.
    graceful = StubOpener([_metainfo([
        _sheet(frozen_rows=frozen_rows, frozen_cols=frozen_cols),
        _sheet(sheet_id="tab2", title="Two", index=1),
        _sheet(sheet_id="tab3", title="Three", index=2),
    ])])
    tabs = _read_client(graceful).read_tabs_frozen(
        TOKEN, [_tab(), _tab(sheet_id="tab2"), _tab(sheet_id="tab3")])
    assert tabs[0].frozen_state == expect_state
    assert tabs[0].frozen_panes == panes
    assert [t.frozen_state for t in tabs[1:]] == [FROZEN_NONE, FROZEN_NONE]
    assert len(graceful.requests) == 1 and "metainfo" in graceful.requests[0]


def test_nothing_frozen_is_reported_as_KNOWN_none_not_as_no_knowledge():
    """``frozen: none`` and ``frozen: unavailable`` are different facts and must not collapse:
    the first says "I asked, nothing is frozen", the second "I could not find out"."""
    client = _read_client(StubOpener([_metainfo([_sheet()])]))
    (tab,) = client.read_tabs_frozen(TOKEN, [_tab()])
    assert tab.frozen_state == FROZEN_NONE
    assert tab.frozen_panes == FrozenPanes(rows=0, cols=0, source="metainfo")
    assert tab.frozen_state_detail is None


def test_the_read_UNAVAILABLE_arm_discloses_and_never_claims_nothing_is_frozen():
    """The LD-155 posture, replayed: an injected transport failure must leave the read
    SUCCEEDING (no raise), the tab's frozen state ``unavailable``, the reason recorded, and
    **no** frozen counts invented."""
    opener = RaisingOpener(LarkAPIError("no permission for metainfo (code 99991672)"))
    client = _read_client(opener)

    (tab,) = client.read_tabs_frozen(TOKEN, [_tab()])
    assert tab.frozen_state == FROZEN_UNAVAILABLE
    assert tab.frozen_panes is None, "a failed read must not fabricate a frozen count"
    assert "99991672" in tab.frozen_state_detail
    assert tab.frozen_state != FROZEN_NONE


def test_a_tab_ABSENT_from_the_metainfo_response_is_unavailable_not_unfrozen():
    """The LD-184 lesson (three indistinguishable outcomes cost five days): "the payload came
    back and this tab was not in it" is its own case, and it is NOT "nothing frozen"."""
    client = _read_client(StubOpener([_metainfo([_sheet(sheet_id="otherId")])]))
    (tab,) = client.read_tabs_frozen(TOKEN, [_tab(sheet_id="missingId")])
    assert tab.frozen_state == FROZEN_UNAVAILABLE
    assert tab.frozen_panes is None
    assert "missingId" in tab.frozen_state_detail


def test_a_payload_carrying_NO_frozen_keys_is_unavailable_not_unfrozen():
    """API drift, or a payload family that never had the keys: absent is unknown."""
    driftless = {"columnCount": 20, "index": 0, "rowCount": 200, "sheetId": SID,
                 "title": "Sheet1"}
    panes, reason = parse_frozen_panes(driftless, source="metainfo")
    assert panes is None
    assert "frozenRowCount" in reason and "frozenColCount" in reason

    client = _read_client(StubOpener([_metainfo([driftless])]))
    (tab,) = client.read_tabs_frozen(TOKEN, [_tab()])
    assert tab.frozen_state == FROZEN_UNAVAILABLE
    assert tab.frozen_panes is None


def test_a_HALF_present_payload_is_unavailable_rather_than_half_invented():
    """One axis known and one absent is not knowledge you can diff a write against; reporting
    the known half as fact while zeroing the other is the silent-fidelity sin itself."""
    half = {"frozenRowCount": 2, "index": 0, "rowCount": 200, "columnCount": 20,
            "sheetId": SID, "title": "Sheet1"}
    panes, reason = parse_frozen_panes(half, source="metainfo")
    assert panes is None
    assert "frozenColCount" in reason


def test_a_digit_string_count_is_accepted_because_under_reporting_is_the_silent_failure():
    """Lark itself accepts a string count on the WRITE side (probed: ``frozenRowCount: "2"``
    → code 0), so a digit string on the read side is parsed as the number it plainly names —
    the ``_row_numbers`` posture. A bool is drift, never a count."""
    panes, reason = parse_frozen_panes(
        {"frozenRowCount": "2", "frozenColCount": 0}, source="metainfo")
    assert (panes.rows, panes.cols) == (2, 0) and reason is None

    panes, reason = parse_frozen_panes(
        {"frozenRowCount": True, "frozenColCount": 0}, source="metainfo")
    assert panes is None and "frozenRowCount" in reason


def test_the_v3_grid_properties_shape_parses_through_the_SAME_parser():
    """One parser, two key families — so the two payload shapes cannot drift apart."""
    grid = _step(_FREEZE_CAPTURE, "v3 sheets/query AFTER rows-only freeze")["response"]
    props = grid["data"]["sheets"][0]["grid_properties"]
    panes, reason = parse_frozen_panes(props, keys=("frozen_row_count", "frozen_column_count"),
                                       source="v3-tab-query")
    assert (panes.rows, panes.cols, panes.source) == (2, 0, "v3-tab-query")
    assert reason is None


def test_a_tab_nobody_asked_about_stays_NOT_READ_and_renders_unchanged():
    """The default state is "nobody asked" — so nothing about the shipped read path changes
    until a caller opts in (the reason the goldens are byte-identical)."""
    tab = SheetTab.from_dict(
        {"sheet_id": SID, "title": "Sheet1", "index": 0,
         "grid_properties": {"row_count": 200, "column_count": 20,
                             "frozen_row_count": 2, "frozen_column_count": 1}})
    assert tab.frozen_state == FROZEN_NOT_READ
    assert tab.frozen_panes is None
    assert tab.row_count == 200


def test_get_frozen_panes_raises_on_a_non_zero_code_and_the_graceful_wrapper_does_not():
    """The two-method split the filter read established: the typed op raises (so a caller who
    wants the failure gets it), the graceful wrapper never does."""
    denied = {"code": 99991672, "msg": "no permission", "data": {}}
    client = _read_client(StubOpener([denied]))
    with pytest.raises(LarkAPIError):
        client.get_frozen_panes(TOKEN)

    client2 = _read_client(StubOpener([denied]))
    (tab,) = client2.read_tabs_frozen(TOKEN, [_tab()])
    assert tab.frozen_state == FROZEN_UNAVAILABLE
    assert "99991672" in tab.frozen_state_detail


def test_the_frozen_describe_text_is_human_and_names_both_axes():
    assert FrozenPanes(rows=0, cols=0).describe() == "nothing frozen"
    assert FrozenPanes(rows=2, cols=0).describe() == "2 row(s) frozen, no columns frozen"
    assert FrozenPanes(rows=0, cols=1).describe() == "no rows frozen, 1 column(s) frozen"
    assert FrozenPanes(rows=3, cols=2).describe() == "3 row(s) frozen, 2 column(s) frozen"


# =========================================================================== #
# The write-side seam — a duck-typed gateway that COUNTS every call, so the     #
# "zero API calls on refusal" and "no second batch implementation" claims are   #
# proven rather than asserted.                                                  #
# =========================================================================== #

class FreezeGateway:
    """A duck-typed write-client seam modelling exactly the freeze surface.

    ``sheets`` maps a ``sheet_id`` → its ``metainfo`` sheet dict, so the double answers the
    real payload shape the probe observed (frozen counts **and** the grid, in one read). Every
    call is journalled in ``calls`` in order; ``batch_bodies`` records the verbatim
    ``requests[]`` array each ``sheets_batch_update`` received, which is what makes the
    byte-exact wire assertions possible.
    """

    def __init__(self, *, revision=11, sheets=None, frozen_error=None, batch_error=None,
                 bump_on_write=True):
        self.revision = revision
        self.sheets = {s["sheetId"]: dict(s) for s in (sheets or [_sheet()])}
        self.frozen_error = frozen_error
        self.batch_error = batch_error
        self.bump_on_write = bump_on_write
        self.calls = []
        self.batch_bodies = []

    # -- reads ----------------------------------------------------------- #

    def read_revision(self, spreadsheet_token):
        self.calls.append(("read_revision",))
        return self.revision

    def read_frozen_panes(self, spreadsheet_token, sheet_id=None):
        self.calls.append(("read_frozen_panes", sheet_id))
        if self.frozen_error is not None:
            raise self.frozen_error
        state = {"revision": self.revision,
                 "sheets": {sid: _frozen_record(s) for sid, s in self.sheets.items()}}
        if sheet_id is None:
            return state
        return state["sheets"].get(sheet_id)

    def query_tabs(self, spreadsheet_token):
        self.calls.append(("query_tabs",))
        return [{"sheet_id": sid, "title": s.get("title"), "index": s.get("index"),
                 "row_count": s.get("rowCount"), "column_count": s.get("columnCount"),
                 "merges": []}
                for sid, s in self.sheets.items()]

    def read_sheet_geometry(self, spreadsheet_token, sheet_id):
        self.calls.append(("read_sheet_geometry", sheet_id))
        s = self.sheets.get(sheet_id)
        if s is None:
            return None
        return {"row_count": s.get("rowCount"), "column_count": s.get("columnCount"),
                "merges": []}

    # -- the ONE write seam a freeze uses (already shipped for the tab family) -- #

    def batch_update_sheets(self, spreadsheet_token, requests):
        self.calls.append(("batch_update_sheets", tuple(next(iter(r)) for r in requests)))
        self.batch_bodies.append([dict(r) for r in requests])
        if self.batch_error is not None:
            raise self.batch_error
        replies = []
        for req in requests:
            props = dict((req.get("updateSheet") or {}).get("properties") or {})
            sheet = self.sheets.get(props.get("sheetId"))
            if sheet is None:
                raise LarkAPIError("Code 90215, Msg: sheetId not found")
            # PATCH, exactly as probed: an axis the request does not name is untouched.
            if "frozenRowCount" in props:
                sheet["frozenRowCount"] = props["frozenRowCount"]
            if "frozenColCount" in props:
                sheet["frozenColCount"] = props["frozenColCount"]
            replies.append({"updateSheet": {"properties": dict(props)}})
        if self.bump_on_write:
            self.revision += 1
        return {"replies": replies}

    def api_calls(self):
        return [c[0] for c in self.calls]

    def writes(self):
        return [c for c in self.calls if c[0] == "batch_update_sheets"]


def _frozen_record(sheet):
    """The write-side frozen record shape (the write client returns plain dicts, its house
    style — the typed :class:`FrozenPanes` is the READ client's surface)."""
    return {"frozen_rows": sheet.get("frozenRowCount"), "frozen_cols": sheet.get("frozenColCount"),
            "row_count": sheet.get("rowCount"), "column_count": sheet.get("columnCount"),
            "title": sheet.get("title"), "index": sheet.get("index"), "source": "metainfo"}


# =========================================================================== #
# AC2 — A TYPED FREEZE REQUEST THROUGH THE EXISTING GATE.                       #
#                                                                              #
# The wire element is asserted BYTE-EXACT against the live capture's own        #
# request body, and the endpoint is the ALREADY-SHIPPED sheets_batch_update.    #
# =========================================================================== #

def test_the_request_element_is_byte_exact_against_the_LIVE_capture_body():
    """The strongest form of "byte-exact": the element this library builds is compared to the
    body the probe actually put on the wire and Lark answered ``code 0`` to."""
    from larkdocio.sheets.requests import FreezePanes

    for label, request in (
        ("A) updateSheet {sheetId, frozenRowCount: 2}", FreezePanes(SID, rows=2)),
        ("B) updateSheet {sheetId, frozenColCount: 1}", FreezePanes(SID, cols=1)),
        ("C) updateSheet {frozenRowCount: 3, frozenColCount: 2}",
         FreezePanes(SID, rows=3, cols=2)),
        ("E) updateSheet {frozenRowCount: 0, frozenColCount: 0}",
         FreezePanes.unfreeze(SID)),
    ):
        step = _step(_FREEZE_CAPTURE, label)
        assert step["code"] == 0, f"{label} was not an accepted call in the capture"
        (captured,) = step["request_body"]["requests"]
        assert request.descriptor()["request_element"] == captured, label


def test_the_four_freeze_shapes_build_the_expected_elements():
    from larkdocio.sheets.requests import FreezePanes

    assert FreezePanes(SID, rows=1).descriptor()["request_element"] == {
        "updateSheet": {"properties": {"sheetId": SID, "frozenRowCount": 1}}}
    assert FreezePanes(SID, cols=1).descriptor()["request_element"] == {
        "updateSheet": {"properties": {"sheetId": SID, "frozenColCount": 1}}}
    assert FreezePanes(SID, rows=2, cols=1).descriptor()["request_element"] == {
        "updateSheet": {"properties": {"sheetId": SID, "frozenRowCount": 2,
                                       "frozenColCount": 1}}}
    assert FreezePanes.unfreeze(SID).descriptor()["request_element"] == {
        "updateSheet": {"properties": {"sheetId": SID, "frozenRowCount": 0,
                                       "frozenColCount": 0}}}


def test_an_axis_the_request_does_not_name_is_ABSENT_from_the_wire_not_zeroed():
    """The PATCH invariant, on the request side: naming only rows must not put a
    ``frozenColCount: 0`` on the wire, because that would silently unfreeze the other axis."""
    from larkdocio.sheets.requests import FreezePanes

    props = FreezePanes(SID, rows=2).descriptor()["request_element"]["updateSheet"]["properties"]
    assert "frozenColCount" not in props
    props = FreezePanes(SID, cols=2).descriptor()["request_element"]["updateSheet"]["properties"]
    assert "frozenRowCount" not in props


def test_the_capture_PROVES_the_patch_semantics_the_preview_claims():
    """The claim the plan makes to a consumer, checked against the live evidence: after a
    rows-only freeze and then a cols-only freeze, BOTH counts stand."""
    survived = _capture(_FREEZE_CAPTURE)["ROWS_SURVIVED_A_COLS_WRITE"]
    assert survived == [{"sheetId": SID, "frozenRowCount": 2, "frozenColCount": 1}]
    # …and the tab's own title / index / hidden flag survive a freeze too
    assert _capture(_FREEZE_CAPTURE)["PATCH_OR_REPLACE"]["title_survived"] == ["Sheet1"]
    assert _capture(_EDGES_CAPTURE)["PATCH_PRESERVES_HIDDEN"] == {
        "hidden_before_freeze": [True], "hidden_after_freeze": [True], "frozen_after": [2]}


def test_freeze_flows_dry_run_to_apply_through_the_SHIPPED_batch_endpoint():
    from larkdocio.sheets.requests import FreezePanes
    from larkdocio.sheets.write_apply import apply, dry_run
    apply = reading_the_log(apply)

    gw = FreezeGateway()
    plan = dry_run([FreezePanes(SID, rows=2)], gw, TOKEN)
    assert len(plan.entries) == 1
    entry = plan.entries[0]
    assert entry.is_resolved and entry.write_kind == "freeze-panes"
    assert entry.structural["op"] == "freeze-panes"
    assert gw.writes() == [], "dry_run must not write"

    log = apply(plan, gw)
    assert [e.to_dict()["outcome"] for e in log.entries] == ["applied"]
    # the ONE write seam, carrying exactly the element the request owns
    assert gw.writes() == [("batch_update_sheets", ("updateSheet",))]
    assert gw.batch_bodies == [[{
        "updateSheet": {"properties": {"sheetId": SID, "frozenRowCount": 2}}}]]
    assert gw.sheets[SID]["frozenRowCount"] == 2
    assert log.entries[0].structural["observed"]["frozen_rows"] == 2


def test_NO_NEW_ENDPOINT_PATH_was_added_for_freeze():
    """AC2's structural claim, proven three ways rather than asserted.

    (1) The write-seam registry the disposition boundary keys on is UNCHANGED — freeze reuses
    ``batch_update_sheets``, so no new write seam had to be declared. (2) The freeze apply leg
    names that seam and no other. (3) The write client gained no new ``sheets/v2`` path suffix:
    the frozen read rides ``metainfo``, which ``read_revision`` already called.
    """
    import inspect
    import re

    from larkdocio.sheets import disposition as D
    from larkdocio.sheets import ops as O
    from larkdocio.sheets import write_client as WC

    # The set is pinned EXACTLY, so any later family that declares a seam has to come through
    # this line and say so. LD-188's style family did — `put_style` / `batch_update_styles`,
    # its own two endpoints — which is a different family's business and does not weaken the
    # freeze claim: (2) below is what proves the freeze leg itself declares none.
    assert D.WRITE_SEAMS == frozenset({
        "put_values", "batch_update_values", "append_values", "prepend_values",
        "set_data_validation", "put_style", "batch_update_styles",
        "insert_dimension_range", "delete_dimension_range",
        "append_dimension", "set_dimension_properties", "merge_cells", "unmerge_cells",
        "batch_update_sheets",
        # LD-447's in-cell image write declares its own seam (it mutates: it stores a picture
        # as a cell's value). Another family's business, exactly like LD-188's style pair
        # above, and it does not weaken the freeze claim: (2) below is what proves the freeze
        # leg itself declares none.
        "put_values_image",
        # LD-448's float-image bind + delete declare their own seams (both mutate: one
        # anchors a picture over a range, the other removes the anchor). Same story again —
        # another family's business, and (2) below is what proves the freeze leg declares
        # none of its own.
        "create_float_image", "delete_float_image",
    }), "freeze must add NO write seam — it rides the shipped sheets_batch_update"

    src = inspect.getsource(O._apply_freeze_one)
    seams = {n for n in D.WRITE_SEAMS if f"client.{n}(" in src}
    assert seams == {"batch_update_sheets"}, seams

    # (3) The write client's API path literals, pinned as the set that was there BEFORE this
    # issue: freeze rides `sheets_batch_update` (shipped for the tab family) and the frozen read
    # rides `metainfo` (shipped for the revision compare-and-swap), so nothing is added. The
    # pinned set is byte-identical to the one extracted from `origin/develop`'s own copy of this
    # module at the fork point — a NEW path literal here reddens.
    paths = set(re.findall(r"/open-apis/[A-Za-z0-9_/{}.\-]*", inspect.getsource(WC)))
    assert paths == {
        "/open-apis/contact/v3/users/batch",
        "/open-apis/drive/v1/files/{token}",
        "/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/{suffix}",
        "/open-apis/sheets/v3/spreadsheets",
        "/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query",
        # LD-448 — the float-image collection on one tab. A v3 path rather than a
        # `_sheets_v2_path` suffix, so it joins the set above rather than the one below; and
        # it is another family's endpoint, which is exactly what this pinned set exists to
        # make someone say out loud. Freeze itself still adds nothing.
        "/open-apis/sheets/v3/spreadsheets/{token}/sheets/{sheet_id}/float_images",
    }, sorted(paths)
    suffixes = set(re.findall(r'_sheets_v2_path\([^,]+,\s*[f]?"([^"{]*)',
                              inspect.getsource(WC)))
    assert {"sheets_batch_update", "metainfo"} <= suffixes
    # `style` / `styles_batch_update` joined at LD-188 (the promoted style write, its own two
    # endpoints) and `values_image` at LD-447 (the in-cell image write — its own endpoint and
    # the ONLY call that route makes: the bytes ride in its body, so it added no upload path
    # either); everything else is the pre-freeze set, so freeze itself still added nothing.
    assert suffixes == {"dataValidation", "dimension_range", "insert_dimension_range",
                        "merge_cells", "metainfo", "sheets_batch_update", "style",
                        "styles_batch_update", "unmerge_cells",
                        "values", "values/", "values_append", "values_batch_update",
                        "values_image", "values_prepend"}, sorted(suffixes)


def test_the_batch_request_builder_seam_is_SHARED_with_the_tab_family():
    """The test that makes LD-187 safe: freeze and the tab ops go through the SAME registry
    seam and the SAME client method, so a second ``sheets_batch_update`` implementation cannot
    quietly appear. Both families own their wire element in ``descriptor()["request_element"]``
    and neither hand-assembles a body."""
    from larkdocio.sheets.ops import OPS
    from larkdocio.sheets.requests import AddTab, DeleteTab, FreezePanes

    riders = [d for d in OPS if "batch_update_sheets" in _apply_source(d)]
    assert {d.kind for d in riders} == {"tab", "freeze-panes"}
    for request in (AddTab("T"), DeleteTab(SID), FreezePanes(SID, rows=1)):
        element = request.descriptor()["request_element"]
        assert isinstance(element, dict) and len(element) == 1


def _apply_source(descriptor):
    import inspect
    return inspect.getsource(descriptor.apply)


def test_rows_and_columns_in_ONE_request_and_in_TWO_both_land():
    from larkdocio.sheets.requests import FreezePanes
    from larkdocio.sheets.write_apply import apply, dry_run
    apply = reading_the_log(apply)

    one = FreezeGateway()
    apply(dry_run([FreezePanes(SID, rows=3, cols=2)], one, TOKEN), one)
    assert one.batch_bodies == [[{"updateSheet": {"properties": {
        "sheetId": SID, "frozenRowCount": 3, "frozenColCount": 2}}}]]
    assert (one.sheets[SID]["frozenRowCount"], one.sheets[SID]["frozenColCount"]) == (3, 2)

    two = FreezeGateway()
    log = apply(dry_run([FreezePanes(SID, rows=3), FreezePanes(SID, cols=2)], two, TOKEN), two)
    assert [e.to_dict()["outcome"] for e in log.entries] == ["applied", "applied"]
    # two entries → two batch calls, each ONE element (the per-entry doctrine, not a merge)
    assert [len(b) for b in two.batch_bodies] == [1, 1]
    assert (two.sheets[SID]["frozenRowCount"], two.sheets[SID]["frozenColCount"]) == (3, 2)
    # and the capture proves Lark accepts both shapes
    assert _capture(_FREEZE_CAPTURE)["BOTH_ONE_REQUEST"][0]["frozenRowCount"] == 3
    assert _capture(_FREEZE_CAPTURE)["TWO_IN_ONE_BATCH"][0]["frozenRowCount"] == 1


def test_unfreeze_is_a_freeze_of_zero_and_really_clears_both_axes():
    from larkdocio.sheets.requests import FreezePanes
    from larkdocio.sheets.write_apply import apply, dry_run
    apply = reading_the_log(apply)

    gw = FreezeGateway(sheets=[_sheet(frozen_rows=3, frozen_cols=2)])
    log = apply(dry_run([FreezePanes.unfreeze(SID)], gw, TOKEN), gw)
    assert log.entries[0].to_dict()["outcome"] == "applied"
    assert (gw.sheets[SID]["frozenRowCount"], gw.sheets[SID]["frozenColCount"]) == (0, 0)
    assert log.entries[0].structural["unfreezes"] is True
    # the capture's own unfreeze arm
    assert _capture(_FREEZE_CAPTURE)["UNFREEZE"][0]["frozenRowCount"] == 0


def test_a_stale_spreadsheet_refuses_the_freeze_with_STALE_SHEET_and_writes_nothing():
    from larkdocio.sheets.requests import FreezePanes
    from larkdocio.sheets.write_apply import apply, dry_run
    apply = reading_the_log(apply)

    gw = FreezeGateway(revision=11)
    plan = dry_run([FreezePanes(SID, rows=2)], gw, TOKEN)
    gw.revision = 12                      # somebody else wrote between plan and apply
    log = apply(plan, gw)
    assert log.entries[0].refusal.reason == "stale-sheet"
    assert gw.writes() == []


def test_a_freeze_plan_cannot_be_forged():
    """The non-forgeable ``Plan`` invariant, on this family too."""
    from larkdocio.sheets.plan import Plan

    with pytest.raises(Exception):
        Plan([], revision=1, spreadsheet_token=TOKEN)


# =========================================================================== #
# AC3 — A NEW OP KIND VERIFIED BY ITS OWN LEG.                                  #
#                                                                              #
# Freeze is VIEW state: not cell content, not merge geometry. So it is off the  #
# export style leg and off the v3 merge leg (the TAB / DATA_VALIDATION posture) #
# and it is verified by AC1's frozen read instead.                              #
# =========================================================================== #

def test_freeze_triggers_NEITHER_the_style_leg_NOR_the_merge_leg():
    from larkdocio.sheets.requests import (
        MERGE_LEG_OP_KINDS,
        STYLE_LEG_OP_KINDS,
        FreezePanes,
        WriteOpKind,
        certify_gate_legs,
        effective_verify_style,
        requires_merge_leg,
        requires_style_leg,
    )

    kinds = FreezePanes(SID, rows=2).op_kinds
    assert kinds == (WriteOpKind.FREEZE_PANES,)
    assert WriteOpKind.FREEZE_PANES not in STYLE_LEG_OP_KINDS
    assert WriteOpKind.FREEZE_PANES not in MERGE_LEG_OP_KINDS
    assert requires_style_leg(kinds) is False
    assert requires_merge_leg(kinds) is False
    assert effective_verify_style(kinds) is False
    # the gate certifies a freeze on the always-on values leg alone
    certify_gate_legs(kinds, values_leg_ran=True)


def test_the_freeze_leg_is_NAMED_in_the_apply_log_with_why_it_is_the_right_one():
    from larkdocio.sheets.ops import FREEZE_VERIFICATION_LEG
    from larkdocio.sheets.requests import FreezePanes
    from larkdocio.sheets.write_apply import apply, dry_run
    apply = reading_the_log(apply)

    gw = FreezeGateway()
    log = apply(dry_run([FreezePanes(SID, rows=2)], gw, TOKEN), gw)
    record = log.entries[0].structural
    assert record["verified_by"] == FREEZE_VERIFICATION_LEG == "metainfo-frozen-leg"
    assert "metainfo" in record["verification_note"]
    # unlike the dimension leg, this one is CHEAP, so it really runs inside apply
    assert record["observed"] == {"frozen_rows": 2, "frozen_cols": 0}
    assert record["frozen_before"] == {"frozen_rows": 0, "frozen_cols": 0}


def test_the_freeze_preview_states_what_it_does_NOT_touch():
    from larkdocio.sheets.requests import FreezePanes

    preview = FreezePanes(SID, rows=2).freeze_preview()
    assert preview["kind"] == "freeze-panes"
    assert preview["changes_values"] is False
    assert preview["changes_geometry"] is False
    assert preview["changes_merges"] is False
    assert preview["patch"] is True
    # and the live capture backs the "values are untouched" claim
    assert _capture(_FREEZE_CAPTURE)["VALUES_AFTER_FREEZE"] == [
        ["h1", "h2"], ["r2", "x"], ["r3", "y"], ["r4", "z"]]


# =========================================================================== #
# AC4 — REFUSALS PRE-I/O.                                                       #
#                                                                              #
# The boundary Lark's own message LIES about: `frozenRowCount == rowCount` is    #
# ACCEPTED (all rows frozen — probed, code 0), while `rowCount + 1` answers      #
# `90226 frozenRowCount must less than sheet rowCount`. Refuse on the PROBED     #
# boundary, never on the message's wording.                                     #
# =========================================================================== #

def test_the_capture_pins_the_boundary_the_lark_message_misstates():
    all_rows = _step(_FREEZE_CAPTURE, "F) frozenRowCount = rowCount")
    over_rows = _step(_FREEZE_CAPTURE, "G) frozenRowCount = rowCount + 1")
    over_cols = _step(_FREEZE_CAPTURE, "H) frozenColCount = columnCount + 1")
    negative = _step(_FREEZE_CAPTURE, "I) frozenRowCount: -1")

    assert all_rows["code"] == 0, "freezing EVERY row is accepted — the ceiling is <= rowCount"
    assert _capture(_FREEZE_CAPTURE)["FREEZE_ALL_ROWS"][0]["frozenRowCount"] == 200
    assert (over_rows["code"], over_rows["msg"]) == (
        90226, "frozenRowCount must less than sheet rowCount")
    assert (over_cols["code"], over_cols["msg"]) == (
        90226, "frozenColCount must less than sheet columnCount")
    assert (negative["code"], negative["msg"]) == (
        90226, "frozenRowCount must larger than 0")
    # and a refused freeze left the revision UNMOVED (nothing landed)
    assert _capture(_FREEZE_CAPTURE)["OVER_ROW_COUNT"]["sheets_after"][0]["frozenRowCount"] == 200


def test_freezing_EVERY_row_is_RESOLVED_not_refused():
    """The one-off that a naive ``< count`` reading of Lark's message would wrongly refuse."""
    from larkdocio.sheets.requests import FreezePanes
    from larkdocio.sheets.write_apply import dry_run

    gw = FreezeGateway(sheets=[_sheet(rows=200, cols=20)])
    plan = dry_run([FreezePanes(SID, rows=200), FreezePanes(SID, cols=20)], gw, TOKEN)
    assert [e.is_resolved for e in plan.entries] == [True, True]


@pytest.mark.parametrize("kwargs,axis,asked,count", [
    ({"rows": 201}, "row", 201, 200),
    ({"cols": 21}, "column", 21, 20),
    ({"rows": 2, "cols": 21}, "column", 21, 20),
])
def test_a_count_past_the_grid_refuses_at_PLAN_time_with_ZERO_api_calls(kwargs, axis,
                                                                       asked, count):
    from larkdocio.sheets.requests import FreezePanes
    from larkdocio.sheets.write_apply import apply, dry_run
    apply = reading_the_log(apply)

    gw = FreezeGateway(sheets=[_sheet(rows=200, cols=20)])
    plan = dry_run([FreezePanes(SID, **kwargs)], gw, TOKEN)
    entry = plan.entries[0]
    assert not entry.is_resolved
    assert entry.refusal.reason == "frozen-count-out-of-range"
    detail = entry.refusal.detail
    assert f"{asked}" in detail and f"{count}" in detail and axis in detail
    assert "90226" in detail, "the refusal quotes the Lark body it pre-empts"
    assert "FreezePanes(" in detail, "an exampled error names the valid form"

    # ZERO write calls — on the plan AND on the apply of that plan (the call-count spy)
    assert gw.writes() == []
    log = apply(plan, gw)
    assert gw.writes() == []
    assert log.entries[0].refusal.reason == "frozen-count-out-of-range"


@pytest.mark.parametrize("kwargs,needle", [
    ({"rows": -1}, "must larger than 0"),
    ({"cols": -5}, "must larger than 0"),
    ({"rows": True}, "Invalid parameter type"),
    ({"cols": 2.5}, "whole number"),
    ({}, "request body is wrong"),
])
def test_a_count_that_cannot_be_meant_refuses_at_CONSTRUCTION_for_zero_calls(kwargs, needle):
    """Everything knowable from the caller's own arguments refuses **before** the request
    object exists, so it cannot cost a call at all — strictly earlier than plan time, and the
    house pattern (``DimensionPropertyError`` / ``FormulaExpressionError``). Each message
    quotes the probed Lark body it pre-empts and shows a valid form."""
    from larkdocio.sheets.requests import FreezeError, FreezePanes

    with pytest.raises(FreezeError) as exc:
        FreezePanes(SID, **kwargs)
    text = str(exc.value)
    assert needle in text, text
    assert "FreezePanes(" in text, text


def test_freeze_error_is_both_a_config_error_and_a_ValueError():
    from larkdocio.errors import LarkConfigError, LarkDocIOError
    from larkdocio.sheets.requests import FreezeError

    assert issubclass(FreezeError, LarkConfigError)
    assert issubclass(FreezeError, LarkDocIOError)
    assert issubclass(FreezeError, ValueError)


def test_an_unknown_sheet_id_refuses_UNKNOWN_TAB_with_a_did_you_mean_and_no_write():
    from larkdocio.sheets.requests import FreezePanes
    from larkdocio.sheets.write_apply import dry_run

    step = _step(_FREEZE_CAPTURE, "J) updateSheet on an UNKNOWN sheetId")
    assert (step["code"], step["msg"]) == (90215, "sheetId not found")

    gw = FreezeGateway(sheets=[_sheet(sheet_id="realId", title="Sheet1")])
    plan = dry_run([FreezePanes("zzzz99", rows=1)], gw, TOKEN)
    entry = plan.entries[0]
    assert entry.refusal.reason == "unknown-tab"
    assert "realId" in entry.refusal.detail
    assert gw.writes() == []


def test_a_frozen_read_that_FAILS_at_plan_time_refuses_rather_than_writing_blind():
    """The plan cannot bounds-check a freeze it cannot read the grid for, so it refuses — the
    same posture the dimension-property preview takes. The read leg's own degrade-and-disclose
    arm is AC1's; a plan that cannot see the tab does not guess."""
    from larkdocio.sheets.requests import FreezePanes
    from larkdocio.sheets.write_apply import dry_run

    gw = FreezeGateway(frozen_error=LarkAPIError("Code 99991672, Msg: no permission"))
    entry = dry_run([FreezePanes(SID, rows=2)], gw, TOKEN).entries[0]
    assert not entry.is_resolved
    assert entry.refusal.reason in {"unknown-tab", "tab-vanished"}
    assert "99991672" in entry.refusal.detail
    assert gw.writes() == []


# =========================================================================== #
# AC5 — A FREEZE THAT REPLACES AN EXISTING FREEZE SAYS SO.                      #
# =========================================================================== #

def test_a_freeze_over_an_existing_freeze_NAMES_both_the_current_and_the_target():
    from larkdocio.sheets.requests import FreezePanes
    from larkdocio.sheets.write_apply import dry_run

    gw = FreezeGateway(sheets=[_sheet(frozen_rows=2, frozen_cols=1)])
    entry = dry_run([FreezePanes(SID, rows=4)], gw, TOKEN).entries[0]
    (note,) = entry.preview_notes
    assert note["kind"] == "freeze-replaces-freeze"
    assert note["current"] == {"frozen_rows": 2, "frozen_cols": 1}
    assert note["target"] == {"frozen_rows": 4, "frozen_cols": 1}
    text = note["note"]
    assert "2 row(s) frozen" in text and "1 column(s) frozen" in text
    assert "4" in text
    # LD-150's shipped vocabulary, quoted rather than re-coined
    assert "Nothing is refused" in text
    assert "re-plan" in text and "if that is not what you meant" in text


def test_no_existing_freeze_means_NO_replacement_note():
    from larkdocio.sheets.requests import FreezePanes
    from larkdocio.sheets.write_apply import dry_run

    gw = FreezeGateway(sheets=[_sheet(frozen_rows=0, frozen_cols=0)])
    entry = dry_run([FreezePanes(SID, rows=2)], gw, TOKEN).entries[0]
    assert entry.preview_notes == ()
    assert entry.is_resolved


def test_an_UNFREEZE_over_an_existing_freeze_is_disclosed_too():
    """The most surprising case: unfreezing silently discards somebody's frozen band."""
    from larkdocio.sheets.requests import FreezePanes
    from larkdocio.sheets.write_apply import dry_run

    gw = FreezeGateway(sheets=[_sheet(frozen_rows=3, frozen_cols=2)])
    (note,) = dry_run([FreezePanes.unfreeze(SID)], gw, TOKEN).entries[0].preview_notes
    assert note["kind"] == "freeze-replaces-freeze"
    assert note["target"] == {"frozen_rows": 0, "frozen_cols": 0}
    assert "nothing frozen" in note["note"]


def test_a_freeze_that_changes_NOTHING_still_says_so_rather_than_looking_like_a_change():
    """Probed: repeating an identical freeze still bumps ``revision``, so a no-op freeze is a
    real write. The plan says the target equals the current state."""
    from larkdocio.sheets.requests import FreezePanes
    from larkdocio.sheets.write_apply import dry_run

    assert _capture(_EDGES_CAPTURE)["IDEMPOTENCE"]["repeat_bumped"] is True

    gw = FreezeGateway(sheets=[_sheet(frozen_rows=2)])
    (note,) = dry_run([FreezePanes(SID, rows=2)], gw, TOKEN).entries[0].preview_notes
    assert note["kind"] == "freeze-replaces-freeze"
    assert note["unchanged"] is True
    assert "already" in note["note"]


def test_the_replacement_note_states_the_PATCH_rule_for_the_UNNAMED_axis():
    """A caller freezing rows over a tab with frozen columns must be told the columns stay."""
    from larkdocio.sheets.requests import FreezePanes
    from larkdocio.sheets.write_apply import dry_run

    gw = FreezeGateway(sheets=[_sheet(frozen_rows=0, frozen_cols=1)])
    (note,) = dry_run([FreezePanes(SID, rows=2)], gw, TOKEN).entries[0].preview_notes
    assert note["preserved_axes"] == ["frozen_cols"]
    assert "column" in note["note"]


def test_the_replacement_note_survives_from_the_plan_into_the_apply_log():
    """The F8 lesson: a warning that dies between plan and log is the bug."""
    from larkdocio.sheets.requests import FreezePanes
    from larkdocio.sheets.write_apply import apply, dry_run
    apply = reading_the_log(apply)

    gw = FreezeGateway(sheets=[_sheet(frozen_rows=2)])
    log = apply(dry_run([FreezePanes(SID, rows=4)], gw, TOKEN), gw)
    kinds = [n["kind"] for n in log.entries[0].preview_notes]
    assert kinds == ["freeze-replaces-freeze"]


def test_per_tab_independence_a_freeze_on_one_tab_leaves_the_other_alone():
    from larkdocio.sheets.requests import FreezePanes
    from larkdocio.sheets.write_apply import apply, dry_run
    apply = reading_the_log(apply)

    gw = FreezeGateway(sheets=[_sheet(sheet_id="tabA"), _sheet(sheet_id="tabB", index=1)])
    apply(dry_run([FreezePanes("tabA", rows=2)], gw, TOKEN), gw)
    assert gw.sheets["tabA"]["frozenRowCount"] == 2
    assert gw.sheets["tabB"]["frozenRowCount"] == 0
    # the capture's own per-tab arm
    assert _capture(_EDGES_CAPTURE)["PER_TAB_INDEPENDENCE"] == {
        "4AVkA0": {"frozenRowCount": 0, "frozenColCount": 1},
        "8e8887": {"frozenRowCount": 2, "frozenColCount": 0}}
