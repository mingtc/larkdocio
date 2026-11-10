"""The Sheets FILTER read + its disclosure (LD-155 — the silent-fidelity correctness fix).

The defect
----------
The shipped L1 reader emitted **filter-hidden rows as if they were visible**, with no note,
no field, and no signal of any kind. A human looking at a filtered tab sees N rows; a
consumer reading the same tab through larkdocio saw N + hidden, and could not tell a
filtered sheet from an unfiltered one. Same class as the merged-table collapse (LD-144) and
the metachar escaping (LD-130): a fidelity loss that is *silent*.

The fix is to **read the filter and DISCLOSE it**. Which rows render by default is
deliberately UNCHANGED — that would be an unconsented reader-output change, and it is parked
as a product question with a recommendation on the issue.

The live probe this file is built on (2026-07-29, two self-provisioned disposables, raw
filter-create calls, `finally`-delete, zero-orphan close-out — `tests/captures/sheets-filter-probe/`)
"""
import json
from pathlib import Path

import pytest

from larkdocio.errors import LarkAPIError
from larkdocio.sheets.client import SheetsReadClient
from larkdocio.sheets.extent import UsedRange
from larkdocio.sheets.models import (
    FILTER_ACTIVE,
    FILTER_NONE,
    FILTER_NOT_READ,
    FILTER_UNAVAILABLE,
    Merge,
    SheetFilter,
    SheetTab,
)
from larkdocio.sheets.table import filter_disclosure_note, render_spreadsheet, render_tab

from write_harness import _FakeHTTPResponse

_CAPTURES = Path(__file__).resolve().parent.parent / "tests" / "captures" / "sheets-filter-probe" / "captures"


def _capture(name):
    """One live-probe capture (raw API JSON — the fixture seed the quality bar demands)."""
    return json.loads((_CAPTURES / name).read_text(encoding="utf-8"))


def _response(name):
    return _capture(name)["response"]


# --------------------------------------------------------------------------- #
# Test doubles                                                                 #
# --------------------------------------------------------------------------- #


class StubOpener:
    """Records each GET and returns the next queued payload."""

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.requests = []

    def __call__(self, req, timeout=30):
        self.requests.append({"method": req.get_method(), "url": req.full_url})
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


def _client(opener):
    return SheetsReadClient(
        "cli_x", "sec_x",
        urlopen=opener,
        token_fetcher=lambda *a, **k: "t-tok",
        rate_limiter=NoLimiter(),
    )


def _tab(sheet_id="8e26a5", title="Sheet1", rows=6, cols=2):
    return SheetTab(sheet_id=sheet_id, title=title, index=0,
                    row_count=rows, column_count=cols)


def _grid(n_rows=6):
    """A tiny values matrix: header + data rows, one per sheet row."""
    return [["Name", "Status"]] + [[f"r{i}", "keep"] for i in range(1, n_rows)]


def _used(tab, values=None):
    return UsedRange.from_tab_values(tab, values if values is not None else _grid())


# =========================================================================== #
# The model parse — against the REAL captured payloads                         #
# =========================================================================== #

def test_filter_parse_reads_range_hidden_rows_and_conditions_from_the_live_capture():
    f = SheetFilter.from_response(_response("01-filter-get-range-at-A1.json"))
    assert f is not None
    assert f.range == "8e26a5!A1:B6"
    assert f.filtered_out_rows == (3, 5)
    assert f.hidden_row_count == 2
    assert len(f.columns) == 1
    assert f.columns[0].col == "B"
    assert f.columns[0].conditions[0].filter_type == "multiValue"
    assert f.columns[0].conditions[0].expected == ("keep",)


def test_the_response_omits_compare_type_and_the_parse_does_not_require_it():
    """The create request carried ``compare_type``; the read response does NOT echo it
    back (live-observed). A parse that required it would raise on every real filter."""
    raw = _response("01-filter-get-range-at-A1.json")
    condition = raw["data"]["sheet_filter_info"]["filter_infos"][0]["conditions"][0]
    assert "compare_type" not in condition          # pins the observed shape
    f = SheetFilter.from_response(raw)
    assert f.columns[0].conditions[0].compare_type is None


def test_filtered_out_rows_are_SHEET_ABSOLUTE_and_1_INDEXED():
    """THE index-convention pin, and the single most load-bearing assertion here.

    The probe offset the filter range to ``A3:B8`` precisely so the candidate conventions
    diverge. The hidden data rows sat at the SHEET's rows 5 and 7, so:

        sheet-absolute 1-indexed -> [5, 7]      <-- what the API actually returned
        range-relative 1-indexed -> [3, 5]
        range-relative 0-indexed -> [2, 4]
        sheet-absolute 0-indexed -> [4, 6]

    This is the OPPOSITE of the neighbouring convention in this package: the v3 tab query's
    ``merges`` array is 0-indexed and end-inclusive. Carrying that convention across would
    have named the wrong rows in the disclosure note — and a note that lies is worse than no
    note at all.
    """
    cap = _capture("02-filter-get-offset-range-INDEX-CONVENTION.json")
    f = SheetFilter.from_response(cap["response"])
    assert f.range.endswith("!A3:B8")
    assert f.filtered_out_rows == (5, 7)
    # and the 0-indexed matrix positions a consumer needs are derived in exactly one place
    assert f.matrix_row_indexes == (4, 6)


def test_no_filter_is_a_SUCCESS_response_with_the_key_ABSENT_not_an_error():
    """Live-observed: an unfiltered tab answers ``code 0`` with ``data: {}``."""
    raw = _response("03-filter-get-NO-filter.json")
    assert raw["code"] == 0
    assert "sheet_filter_info" not in raw["data"]
    assert SheetFilter.from_response(raw) is None


def test_a_filter_hiding_nothing_parses_to_an_empty_row_tuple_not_to_None():
    """A filter that exists but currently hides no rows is NOT the same as no filter —
    it must stay distinguishable, because it can hide rows on the next read."""
    raw = {"code": 0, "data": {"sheet_filter_info": {
        "range": "s1!A1:B6", "filtered_out_rows": [], "filter_infos": []}}}
    f = SheetFilter.from_response(raw)
    assert f is not None
    assert f.filtered_out_rows == ()
    assert f.hidden_row_count == 0


def test_hidden_rows_are_sorted_and_deduped_for_a_deterministic_note():
    raw = {"code": 0, "data": {"sheet_filter_info": {
        "range": "s1!A1:B9", "filtered_out_rows": [7, 3, 7, 5]}}}
    assert SheetFilter.from_response(raw).filtered_out_rows == (3, 5, 7)


def test_a_missing_filter_infos_array_degrades_to_no_columns_never_raises():
    raw = {"code": 0, "data": {"sheet_filter_info": {"range": "s1!A1:B6",
                                                     "filtered_out_rows": [2]}}}
    f = SheetFilter.from_response(raw)
    assert f.columns == ()
    assert f.filtered_out_rows == (2,)


def test_a_nonint_row_in_the_payload_is_dropped_rather_than_crashing_the_read():
    """API-drift belt-and-braces: a read must never fail on a filter payload."""
    raw = {"code": 0, "data": {"sheet_filter_info": {
        "range": "s1!A1:B9", "filtered_out_rows": [3, None, "5", 7]}}}
    assert SheetFilter.from_response(raw).filtered_out_rows == (3, 5, 7)


# =========================================================================== #
# The client ops                                                               #
# =========================================================================== #

def test_get_sheet_filter_hits_the_documented_v3_path():
    opener = StubOpener([_response("01-filter-get-range-at-A1.json")])
    f = _client(opener).get_sheet_filter("shtTOKEN", "8e26a5")
    assert opener.requests[0]["method"] == "GET"
    assert opener.requests[0]["url"].endswith(
        "/open-apis/sheets/v3/spreadsheets/shtTOKEN/sheets/8e26a5/filter")
    assert f.filtered_out_rows == (3, 5)


def test_get_sheet_filter_returns_None_for_a_tab_with_no_filter():
    opener = StubOpener([_response("03-filter-get-NO-filter.json")])
    assert _client(opener).get_sheet_filter("shtTOKEN", "WZhx6") is None


def test_get_sheet_filter_raises_typed_on_a_nonzero_code_like_every_other_read_op():
    opener = StubOpener([{"code": 91403, "msg": "Forbidden"}])
    with pytest.raises(LarkAPIError):
        _client(opener).get_sheet_filter("shtTOKEN", "8e26a5")


# --- the graceful composed op ---------------------------------------------- #

def test_read_tab_filter_marks_a_filtered_tab_active_and_carries_the_hidden_rows():
    opener = StubOpener([_response("01-filter-get-range-at-A1.json")])
    tab = _client(opener).read_tab_filter("shtTOKEN", _tab())
    assert tab.filter_state == FILTER_ACTIVE
    assert tab.filtered_out_rows == (3, 5)
    assert tab.sheet_filter.range == "8e26a5!A1:B6"
    # identity + geometry survive the copy
    assert (tab.sheet_id, tab.title, tab.index) == ("8e26a5", "Sheet1", 0)
    assert (tab.row_count, tab.column_count) == (6, 2)


def test_read_tab_filter_marks_an_unfiltered_tab_none_with_no_hidden_rows():
    opener = StubOpener([_response("03-filter-get-NO-filter.json")])
    tab = _client(opener).read_tab_filter("shtTOKEN", _tab())
    assert tab.filter_state == FILTER_NONE
    assert tab.filtered_out_rows == ()
    assert tab.sheet_filter is None


def test_read_tab_filter_preserves_the_tabs_merges():
    """The filter read must not quietly drop the merge geometry the table join depends on."""
    merges = (Merge(0, 0, 0, 1),)
    base = SheetTab(sheet_id="8e26a5", title="Sheet1", index=0, row_count=6,
                    column_count=2, merges=merges)
    opener = StubOpener([_response("01-filter-get-range-at-A1.json")])
    assert _client(opener).read_tab_filter("shtTOKEN", base).merges == merges


@pytest.mark.parametrize("failure", [
    LarkAPIError("Code 91403, Msg: Forbidden"),
    OSError("connection reset"),
    ValueError("unparseable body"),
])
def test_read_tab_filter_NEVER_fails_the_read_and_discloses_the_absence_of_knowledge(failure):
    """The graceful-degrade contract: a failed or unavailable filter read must not fail the
    read, and the ABSENCE of filter knowledge is itself disclosed — never silently
    collapsed into "no filter"."""
    opener = RaisingOpener(failure)
    tab = _client(opener).read_tab_filter("shtTOKEN", _tab())
    assert tab.filter_state == FILTER_UNAVAILABLE
    assert tab.filtered_out_rows == ()
    assert tab.sheet_filter is None
    assert tab.filter_state_detail                      # the WHY is present
    # the WHY is the real reason, not a generic placeholder: the failure's own text travels
    assert str(failure) in tab.filter_state_detail


def test_unavailable_is_a_DIFFERENT_state_from_no_filter():
    """The distinction the whole graceful path exists to preserve."""
    ok = _client(StubOpener([_response("03-filter-get-NO-filter.json")])).read_tab_filter(
        "shtTOKEN", _tab())
    bad = _client(RaisingOpener(LarkAPIError("Code 91403"))).read_tab_filter(
        "shtTOKEN", _tab())
    assert ok.filtered_out_rows == bad.filtered_out_rows == ()   # indistinguishable by rows
    assert ok.filter_state != bad.filter_state                   # distinguishable by state


def test_a_tab_nobody_asked_about_reports_not_read_never_no_filter():
    """The default state must not claim knowledge the reader never went and got."""
    assert _tab().filter_state == FILTER_NOT_READ
    assert _tab().filtered_out_rows == ()
    assert _tab().sheet_filter is None


def test_query_sheets_spends_no_filter_call_so_the_default_read_cost_is_unchanged():
    tabs_payload = {"code": 0, "data": {"sheets": [
        {"sheet_id": "8e26a5", "title": "Sheet1", "index": 0,
         "grid_properties": {"row_count": 6, "column_count": 2}}]}}
    opener = StubOpener([tabs_payload])
    tabs = _client(opener).query_sheets("shtTOKEN")
    assert len(opener.requests) == 1                       # ONE call, as before
    assert tabs[0].filter_state == FILTER_NOT_READ


# =========================================================================== #
# The model field consistency invariant                                        #
# =========================================================================== #

def test_the_tab_field_and_the_filter_object_can_never_disagree():
    """``filtered_out_rows`` is duplicated onto the tab (the programmatic surface) and
    lives on the filter object. ``with_filter`` is the ONLY writer of both, so they cannot
    drift — pinned here across every shape the amplifier matrix exercises."""
    for rows in ([], [1], [3, 5], [1, 2, 3, 4, 5, 6], [4]):
        f = SheetFilter.from_response(
            {"code": 0, "data": {"sheet_filter_info": {
                "range": "s1!A1:B6", "filtered_out_rows": list(rows)}}})
        tab = _tab().with_filter(f)
        assert tab.filtered_out_rows == f.filtered_out_rows == tuple(rows)
        assert len(tab.filtered_out_rows) == f.hidden_row_count


def test_the_tab_model_stays_frozen_and_serializable():
    import dataclasses

    tab = _tab().with_filter(SheetFilter.from_response(
        _response("01-filter-get-range-at-A1.json")))
    with pytest.raises(dataclasses.FrozenInstanceError):
        tab.filtered_out_rows = (9,)
    blob = dataclasses.asdict(tab)
    assert blob["filtered_out_rows"] == (3, 5)
    assert blob["filter_state"] == FILTER_ACTIVE
    assert blob["sheet_filter"]["range"] == "8e26a5!A1:B6"
    json.dumps(blob)        # round-trippable, like the rest of the model


# =========================================================================== #
# THE DISCLOSURE in the rendered output                                        #
# =========================================================================== #

def test_the_note_names_the_hidden_row_COUNT_and_the_INDEXES():
    tab = _tab().with_filter(SheetFilter.from_response(
        _response("01-filter-get-range-at-A1.json")))
    note = filter_disclosure_note(tab)
    assert "3, 5" in note                 # the indexes
    assert "2 rows" in note               # the count
    assert note.startswith("_(") and note.endswith(")_")


def test_the_note_states_the_rows_are_STILL_INCLUDED_below():
    """Without this sentence the note is ambiguous about the one thing that matters:
    whether the table was filtered for you (it was not)."""
    tab = _tab().with_filter(SheetFilter.from_response(
        _response("01-filter-get-range-at-A1.json")))
    assert "still includes" in filter_disclosure_note(tab)


def test_the_note_states_the_row_numbering_convention():
    """The probe proved the API numbers rows 1-based and sheet-absolute; a note carrying
    bare integers with no stated convention is a trap for a consumer holding a 0-indexed
    matrix."""
    tab = _tab().with_filter(SheetFilter.from_response(
        _response("01-filter-get-range-at-A1.json")))
    assert "first row is 1" in filter_disclosure_note(tab)


def test_the_note_is_ABSENT_for_an_unfiltered_tab_so_it_cannot_leak_into_every_render():
    assert filter_disclosure_note(_tab().with_filter(None)) is None


def test_the_note_is_ABSENT_for_a_tab_nobody_asked_about():
    assert filter_disclosure_note(_tab()) is None


def test_a_filter_hiding_ZERO_rows_still_gets_a_note_saying_so():
    """The decision, pinned: the note reports the FILTER's presence, not merely a loss.
    A live filter that happens to hide nothing today can hide rows tomorrow, and silence
    would make a filtered tab indistinguishable from an unfiltered one — the exact defect
    class this issue fixes."""
    tab = _tab().with_filter(SheetFilter.from_response(
        {"code": 0, "data": {"sheet_filter_info": {"range": "s1!A1:B6",
                                                   "filtered_out_rows": []}}}))
    note = filter_disclosure_note(tab)
    assert note is not None
    assert "no rows" in note


def test_the_unavailable_note_discloses_the_ABSENCE_of_filter_knowledge_with_the_why():
    tab = _tab().with_filter_unavailable("the filter read was refused: Forbidden")
    note = filter_disclosure_note(tab)
    assert "could not be read" in note
    assert "unknown" in note
    assert "Forbidden" in note                # the WHY travels into the note


def test_the_note_singularizes_for_exactly_one_hidden_row():
    tab = _tab().with_filter(SheetFilter.from_response(
        {"code": 0, "data": {"sheet_filter_info": {"range": "s1!A1:B6",
                                                   "filtered_out_rows": [4]}}}))
    note = filter_disclosure_note(tab)
    assert "1 row" in note and "1 rows" not in note
    assert "row 4" in note and "rows 4" not in note


# --- the amplifier matrix -------------------------------------------------- #

@pytest.mark.parametrize("label,rows", [
    ("first row", [1]),
    ("last row", [6]),
    ("middle band", [3, 4]),
    ("non-contiguous", [2, 4, 6]),
    ("all rows", [1, 2, 3, 4, 5, 6]),
    ("zero rows", []),
])
def test_every_hidden_row_shape_discloses_consistently(label, rows):
    tab = _tab().with_filter(SheetFilter.from_response(
        {"code": 0, "data": {"sheet_filter_info": {"range": "s1!A1:B6",
                                                   "filtered_out_rows": list(rows)}}}))
    note = filter_disclosure_note(tab)
    assert note is not None, label
    assert tab.filtered_out_rows == tuple(rows), label
    for row in rows:
        assert str(row) in note, f"{label}: row {row} missing from the note"
    if rows:
        assert f"{len(rows)} row" in note, label


def test_a_filter_whose_range_is_NARROWER_than_the_used_range_needs_no_arithmetic():
    """Because the numbers are sheet-absolute, a filter covering only part of the tab
    reports rows that already line up with the rendered table's own row numbering — the
    case that would have been an off-by-N under a range-relative convention."""
    cap = _capture("02-filter-get-offset-range-INDEX-CONVENTION.json")
    tab = SheetTab(sheet_id="ce58f1", title="Sheet1", index=0, row_count=8,
                   column_count=2).with_filter(SheetFilter.from_response(cap["response"]))
    note = filter_disclosure_note(tab)
    assert "5, 7" in note
    # the hidden rows point at the right grid rows: row 5 is "r2/drop", row 7 is "r4/drop"
    grid = cap["grid_written"]
    for row in tab.filtered_out_rows:
        assert grid[row - 1][1] == "drop"


# =========================================================================== #
# AC4 — WHICH ROWS RENDER BY DEFAULT IS UNCHANGED                              #
# =========================================================================== #

def test_the_filtered_render_is_the_unfiltered_render_PLUS_THE_NOTE_and_nothing_else():
    """The invariance proof: strip the one added note line out of a filtered tab's render
    and the bytes are IDENTICAL to the same tab rendered with no filter knowledge. So the
    fix can only ever ADD a disclosure — it cannot move, drop, or reorder a row."""
    plain_tab = _tab()
    filtered_tab = plain_tab.with_filter(SheetFilter.from_response(
        _response("01-filter-get-range-at-A1.json")))
    used = _used(plain_tab)

    plain = render_tab(plain_tab, used)
    filtered = render_tab(filtered_tab, used)
    assert filtered != plain

    note = filter_disclosure_note(filtered_tab)
    assert note in filtered
    assert filtered.replace(f"{note}\n\n", "", 1) == plain


def test_every_hidden_row_is_STILL_RENDERED_the_default_is_untouched():
    """The parked product question, pinned as behavior: the reader does NOT drop the
    hidden rows. Changing that would be an unconsented output change."""
    plain_tab = _tab()
    used = _used(plain_tab)
    filtered_tab = plain_tab.with_filter(SheetFilter.from_response(
        _response("01-filter-get-range-at-A1.json")))
    rendered = render_tab(filtered_tab, used)
    for row in used.values:
        assert f"| {row[0]} | {row[1]} |" in rendered
    # and the row count in the table body is unchanged (header + separator + 5 body rows)
    assert len([ln for ln in rendered.splitlines() if ln.startswith("|")]) == len(used.values) + 1


def test_an_unfiltered_tab_renders_BYTE_IDENTICALLY_to_a_filter_unaware_one():
    tab = _tab()
    used = _used(tab)
    assert render_tab(tab.with_filter(None), used) == render_tab(tab, used)


def test_render_spreadsheet_discloses_per_tab_and_leaves_the_other_tabs_alone():
    a = SheetTab(sheet_id="a", title="Filtered", index=0, row_count=6, column_count=2)
    b = SheetTab(sheet_id="b", title="Plain", index=1, row_count=6, column_count=2)
    a_filtered = a.with_filter(SheetFilter.from_response(
        _response("01-filter-get-range-at-A1.json")))
    pairs_plain = [(a, _used(a)), (b, _used(b))]
    pairs_mixed = [(a_filtered, _used(a)), (b, _used(b))]

    plain = render_spreadsheet(pairs_plain)
    mixed = render_spreadsheet(pairs_mixed)
    note = filter_disclosure_note(a_filtered)
    assert mixed.count(note) == 1
    assert mixed.replace(f"{note}\n\n", "", 1) == plain


def test_the_note_sits_between_the_heading_and_the_table():
    """A disclosure that follows the data it qualifies is a footnote nobody reads."""
    tab = _tab().with_filter(SheetFilter.from_response(
        _response("01-filter-get-range-at-A1.json")))
    lines = render_tab(tab, _used(tab)).splitlines()
    assert lines[0].startswith("## ")
    assert lines[2].startswith("_(")
    assert lines[4].startswith("|")


def test_an_empty_tab_still_discloses_its_filter():
    """The empty-sheet marker must not swallow the disclosure."""
    tab = SheetTab(sheet_id="e1", title="Empty", index=0, row_count=1, column_count=1)
    tab = tab.with_filter(SheetFilter.from_response(
        _response("01-filter-get-range-at-A1.json")))
    out = render_tab(tab, UsedRange.from_tab_values(tab, [[None]]))
    assert "_(empty sheet)_" in out
    assert filter_disclosure_note(tab) in out


def test_the_unavailable_disclosure_reaches_the_rendered_output_too():
    tab = _tab().with_filter_unavailable("the filter read was refused: Forbidden")
    rendered = render_tab(tab, _used(tab))
    assert "could not be read" in rendered


def test_the_note_is_dialect_free():
    """Consumer-reaching text carries no internal issue ids, decision letters or role
    names — the guard that enforces this repo-wide, applied directly to the new strings."""
    from consumer_text import dialect_hits

    tabs = [
        _tab().with_filter(SheetFilter.from_response(
            _response("01-filter-get-range-at-A1.json"))),
        _tab().with_filter(SheetFilter.from_response(
            {"code": 0, "data": {"sheet_filter_info": {"range": "s1!A1:B6",
                                                       "filtered_out_rows": []}}})),
        _tab().with_filter_unavailable("the filter read was refused: Forbidden"),
    ]
    for tab in tabs:
        note = filter_disclosure_note(tab)
        assert not dialect_hits(note), (note, dialect_hits(note))


def test_the_note_survives_the_gfm_table_it_sits_beside():
    """A stray pipe in the note would open a spurious column in some renderers."""
    tab = _tab().with_filter(SheetFilter.from_response(
        _response("01-filter-get-range-at-A1.json")))
    assert "|" not in filter_disclosure_note(tab)
