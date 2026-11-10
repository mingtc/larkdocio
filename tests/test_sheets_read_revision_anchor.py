"""LD-332 — ONE revision anchor across the sheets READ paths.

``read_used_range`` has always carried one (``UsedRange.revision``, *"for determinism
checks"*); the tab-object paths — ``query_sheets`` and the graceful ``read_tab_filter`` a
document read reaches for — carried none, so a spreadsheet entered a consumer's ledger with
no version to compare against on the next run.

**What the anchor IS was settled by a read-only probe, not by assumption**
(``tests/captures/sheets-revision-anchor-probe/captures/01-revision-scope.json``, four GETs against the
designated read fixture ``LARKDOCIO_SCRATCH_SHEET``, no writes):

* ``metainfo.properties.revision`` and the v2 **values** reply's ``revision`` are the **same
  number** (``37`` on every call of the run) — there is one revision, not two;
* the values reply returned that same ``37`` for **two different tabs**, and ``metainfo``
  carries the number under spreadsheet-level ``properties`` with no per-tab counterpart, so
  the anchor is **per-SPREADSHEET**, not per-tab;
* the v3 tab query carries **no revision at all** — which is why the anchor on the
  tab-object paths has to be read, and why it is read **explicitly** (the ``not-read``
  state, the frozen-panes precedent) rather than silently fetched.

Every arm here is offline against an injected transport, except the capture-truth arm which
reads the committed probe.
"""
import json
import typing
from dataclasses import fields
from pathlib import Path

import pytest

from larkdocio.errors import LarkAPIError
from larkdocio.sheets.client import SheetsReadClient
from larkdocio.sheets.extent import UsedRange
from larkdocio.sheets.models import (
    REVISION_KNOWN,
    REVISION_NOT_READ,
    REVISION_UNAVAILABLE,
    SheetTab,
    parse_revision,
)

from write_harness import StubOpener

_CAPTURE = (Path(__file__).resolve().parent.parent / "tests" / "captures"
            / "sheets-revision-anchor-probe" / "captures" / "01-revision-scope.json")

TOKEN = "shtLD332TOKEN"
SID = "444a1c"


class RaisingOpener:
    """A transport that fails outright — the graceful-degrade arm (the shipped flavour of
    this double; ``StubOpener`` is imported from the shared harness)."""

    def __init__(self, exc):
        self._exc = exc
        self.requests = []

    def __call__(self, req, timeout=30):
        self.requests.append({"method": req.get_method(), "url": req.full_url})
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


def _metainfo(revision=37, *, properties=True, sheets=1):
    data = {"sheets": [{"columnCount": 20, "frozenColCount": 0, "frozenRowCount": 0,
                        "index": i, "rowCount": 200, "sheetId": f"tab{i}",
                        "title": f"Sheet{i}"} for i in range(sheets)]}
    if properties:
        props = {"sheetCount": sheets, "title": "LD-332"}
        if revision is not _ABSENT:
            props["revision"] = revision
        data["properties"] = props
    return {"code": 0, "msg": "success", "data": data}


_ABSENT = object()


def _tab(sheet_id=SID, title="Sheet1", index=0):
    return SheetTab(sheet_id=sheet_id, title=title, index=index,
                    row_count=200, column_count=20)


def _query_body(sheet_ids=(SID,)):
    return {"code": 0, "msg": "success", "data": {"sheets": [
        {"sheet_id": sid, "title": f"T{i}", "index": i,
         "grid_properties": {"row_count": 200, "column_count": 20}}
        for i, sid in enumerate(sheet_ids)]}}


# =========================================================================== #
# AC1 — the DECISION, pinned to its evidence.                                  #
# =========================================================================== #

def test_the_probe_establishes_ONE_revision_and_that_it_is_per_SPREADSHEET():
    """The Decision is not an opinion: the committed capture is what it rests on."""
    observed = json.loads(_CAPTURE.read_text(encoding="utf-8"))["observed"]

    metainfo_rev = observed["metainfo.properties.revision"]
    assert isinstance(metainfo_rev, int)

    values = observed["values_reply_revisions"]
    assert len(values) >= 2, "the per-tab question needs at least two tabs read"
    for label, revs in values.items():
        assert revs["data.revision"] == metainfo_rev, (
            f"{label}: the values reply's revision must be the SAME number metainfo "
            f"reports — two anchors would make the ledger sentence unwritable"
        )
        assert revs["data.valueRange.revision"] == metainfo_rev

    assert observed["v3_tab_query_carries_a_revision"] is False, (
        "the tab query carrying no revision is WHY this anchor must be read explicitly"
    )


# =========================================================================== #
# AC2 — the SAME anchor, reachable from the tab-object paths, uniformly.        #
# =========================================================================== #

def test_the_anchor_is_reachable_from_the_tab_object_path_without_read_used_range():
    """``query_sheets`` → ``read_tabs_revision``: every tab carries the anchor, and ONE
    metainfo call answers the whole spreadsheet (it is per-spreadsheet, so per-tab calls
    would be buying the same number three times)."""
    opener = StubOpener([_query_body(("tab0", "tab1", "tab2")), _metainfo(37, sheets=3)])
    client = _read_client(opener)

    tabs = client.read_tabs_revision(TOKEN, client.query_sheets(TOKEN))

    assert [t.revision for t in tabs] == [37, 37, 37]
    assert {t.revision_state for t in tabs} == {REVISION_KNOWN}
    assert len(opener.requests) == 2, "one tab query + exactly one metainfo read"
    assert "metainfo" in opener.requests[1]["url"]


def test_the_anchor_uses_the_SAME_name_and_type_as_UsedRange_revision():
    """One concept, one name, one type — not a second vocabulary two files apart."""
    used = {f.name: f.type for f in fields(UsedRange)}
    tab = {f.name: f.type for f in fields(SheetTab)}
    assert "revision" in used and "revision" in tab
    assert typing.get_type_hints(UsedRange)["revision"] == typing.get_type_hints(SheetTab)[
        "revision"], "the anchor's type must be int | None on both paths"


def test_read_tab_filter_still_never_raises_and_PRESERVES_the_anchor():
    """The defining property of the graceful wrapper is untouched, and the two opt-in reads
    compose in either order — an anchor already stamped survives a filter read, and a filter
    already resolved survives the revision read."""
    tab = _tab()

    stamped = _read_client(StubOpener([_metainfo(37)])).read_tabs_revision(TOKEN, [tab])[0]
    after_filter = _read_client(
        RaisingOpener(LarkAPIError("no permission for the filter (code 99991672)"))
    ).read_tab_filter(TOKEN, stamped)
    assert after_filter.revision == 37 and after_filter.revision_state == REVISION_KNOWN
    assert after_filter.filter_state == "unavailable"

    filtered = _read_client(
        RaisingOpener(LarkAPIError("no permission for the filter (code 99991672)"))
    ).read_tab_filter(TOKEN, tab)
    both = _read_client(StubOpener([_metainfo(37)])).read_tabs_revision(TOKEN, [filtered])[0]
    assert both.revision == 37 and both.filter_state == "unavailable"


def test_read_revision_returns_the_raw_anchor_and_raises_like_every_other_read_op():
    """The strict leg beside the graceful one — the shipped pattern on this client."""
    client = _read_client(StubOpener([_metainfo(41)]))
    assert client.read_revision(TOKEN) == 41

    denied = {"code": 99991672, "msg": "no permission", "data": {}}
    with pytest.raises(LarkAPIError):
        _read_client(StubOpener([denied])).read_revision(TOKEN)


# =========================================================================== #
# AC3 — unknown reads None and means NOT KNOWN; 0 is a real value, never       #
# synthesized; not-asked-for is its own state and is never silently fetched.    #
# =========================================================================== #

def test_a_tab_from_the_plain_query_is_NOT_READ_not_revision_zero():
    """No read attempted ⇒ no knowledge claimed. ``revision`` is ``None``, and ``None``
    means *not known* — it is emphatically not ``0``, which this API uses as a real value."""
    opener = StubOpener([_query_body()])
    (tab,) = _read_client(opener).query_sheets(TOKEN)

    assert tab.revision is None
    assert tab.revision_state == REVISION_NOT_READ
    assert tab.revision_state_detail is None
    assert not any("metainfo" in url for r in opener.requests for url in [r["url"]]), (
        "the anchor must never be silently fetched by a read the caller did not ask for"
    )


def test_read_tab_filter_alone_fetches_no_revision():
    opener = StubOpener([{"code": 0, "msg": "success", "data": {}}])
    tab = _read_client(opener).read_tab_filter(TOKEN, _tab())
    assert tab.revision_state == REVISION_NOT_READ
    assert not any("metainfo" in url for r in opener.requests for url in [r["url"]])


def test_revision_ZERO_is_a_KNOWN_answer_and_is_carried_as_zero():
    """A fresh spreadsheet really does report ``0`` (the write side's revision-guard leg
    pinned it). Zero is knowledge; it must not degrade to ``unavailable``."""
    (tab,) = _read_client(StubOpener([_metainfo(0)])).read_tabs_revision(TOKEN, [_tab()])
    assert tab.revision == 0
    assert tab.revision_state == REVISION_KNOWN


def test_a_payload_carrying_NO_revision_is_UNAVAILABLE_never_zero():
    (tab,) = _read_client(
        StubOpener([_metainfo(_ABSENT)])).read_tabs_revision(TOKEN, [_tab()])
    assert tab.revision is None, "an absent revision must never be laundered into 0"
    assert tab.revision_state == REVISION_UNAVAILABLE
    assert "revision" in tab.revision_state_detail


def test_a_FAILED_revision_read_is_UNAVAILABLE_with_the_reason_and_never_raises():
    opener = RaisingOpener(LarkAPIError("no permission for metainfo (code 99991672)"))
    tabs = _read_client(opener).read_tabs_revision(TOKEN, [_tab(), _tab("tab1")])

    assert [t.revision for t in tabs] == [None, None]
    assert {t.revision_state for t in tabs} == {REVISION_UNAVAILABLE}
    assert "99991672" in tabs[0].revision_state_detail


@pytest.mark.parametrize("raw", ["37", True, 1.5, None, {"revision": 37}])
def test_a_non_int_revision_is_UNAVAILABLE_carrying_the_raw_value_seen(raw):
    """API drift must not change the anchor's type. Only a real ``int`` is knowledge; a
    digit-string, a bool, a float or an absent key is an honest unknown."""
    revision, reason = parse_revision(raw)
    assert revision is None
    assert repr(raw) in reason

    (tab,) = _read_client(
        StubOpener([_metainfo(raw)])).read_tabs_revision(TOKEN, [_tab()])
    assert tab.revision is None and tab.revision_state == REVISION_UNAVAILABLE


def test_the_revision_state_vocabulary_quotes_the_shipped_state_vocabulary():
    assert (REVISION_NOT_READ, REVISION_UNAVAILABLE) == ("not-read", "unavailable")
    assert REVISION_KNOWN == "known"
