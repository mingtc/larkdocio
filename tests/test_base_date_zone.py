"""LD-463 — THE one Base timezone policy, pinned against the AC1 measurement.

Every number in this file comes out of one committed capture,
``tests/captures/ld463-date-only/captures/ld463-01-date-only-zone.json`` (verdict:
``dev/ld463-date-only/ld463-verdict.md``), and the tests are written so that a re-measurement
that disagreed would redden them rather than be absorbed:

* **Lark stores the ms-epoch VERBATIM** — 21 of 21 records read back the integer that was sent.
  So a Base date value is an *instant*, the calendar date is manufactured at render time out of
  a zone, and the write side's refusal to take a zone costs nothing.
* **Lark's own day boundary for a zone-less Base was measured at 16:00 UTC** (its ``is
  ["Today"]`` filter matched the 00…14 UTC hours of one UTC day and not the 16…22 ones) — i.e.
  **UTC+8**. So the renderer's silent ``UTC`` fallback is not merely *an* assumption, it is a
  **falsified** one for such a Base, in the direction that renders a local-midnight value one
  calendar day early. That number is a **measurement on one tenant**, so it is recorded where
  the policy is authored and is NOT shipped as a constant the library reasons from.
* **``POST /bitable/v1/apps`` ACCEPTS ``time_zone``**, echoes it, and ``GET …/apps/{app}`` reads
  it back — while a Base this library created carried no ``time_zone`` key **at all**. So the
  ``None`` in the bug report is this library's own create talking, and the fix has a root.
"""
import datetime as dt
import importlib
import inspect
import json
import re
from pathlib import Path

import pytest

from larkdocio.base import date_zone
from larkdocio.base.cells import (
    DEFAULT_TIME_ZONE,
    FieldSpec,
    RenderContext,
    render_cell,
)
from larkdocio.base.table import assemble_base

_CAPTURE = (Path(__file__).resolve().parents[1] / "tests" / "captures" / "ld463-date-only" / "captures"
            / "ld463-01-date-only-zone.json")

#: The zone each write convention in the capture authored its midnight in.
_CONVENTION_ZONE = {
    "utc_midnight": "UTC",
    "plus8_midnight": "Asia/Singapore",
    "minus5_midnight": "America/New_York",
}

_DATE_ONLY = FieldSpec(field_name="DateOnly", type=5, ui_type="DateTime",
                       property={"date_formatter": "yyyy/MM/dd"})


@pytest.fixture(scope="module")
def capture():
    return json.loads(_CAPTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def calendar_rows(capture):
    rows = [row for row in capture["values"] if row["kind"] == "calendar-date"]
    assert len(rows) == 9, "the capture carries three conventions × three dates"
    return rows


def render(value, zone):
    return render_cell(value, _DATE_ONLY, context=RenderContext(time_zone=zone))


# --------------------------------------------------------------------------- #
# The measurement itself, held against the capture                             #
# --------------------------------------------------------------------------- #

def test_the_capture_shows_LARK_STORES_THE_EPOCH_VERBATIM(capture):
    """(a). If this ever stops being true the whole policy below is re-opened."""
    assert all(row["stored_equals_sent"] for row in capture["values"])
    assert capture["a_batch_create"]["code"] == 0


def test_the_capture_shows_LARKS_OWN_DAY_BOUNDARY_IS_1600_UTC(capture):
    """(b). The absolute-time oracle: the server's own ``Today``, on a zone-less Base.

    The measurement is asserted against the capture, and the policy module is required to
    **cite** it — but the hour is deliberately not a library constant: it is one tenant's
    offset, and a library that hard-coded it would have replaced a wrong guess with a
    narrower one.
    """
    oracle = capture["b_server_day_oracle"]
    assert oracle["code"] == 0
    assert oracle["hours_matching_today_utc"] == [0, 2, 4, 6, 8, 10, 12, 14]
    assert oracle["hours_not_matching_today_utc"] == [16, 18, 20, 22]
    doc = date_zone.__doc__ or ""
    assert "16:00" in doc and "ld463-01-date-only-zone" in doc, (
        "the policy must cite the measurement that falsified the UTC assumption")
    assert not any(name.endswith("_UTC_HOUR") or name.endswith("_OFFSET")
                   for name in vars(date_zone)), (
        "one tenant's measured offset is evidence, not a constant this library renders from")


def test_the_capture_shows_a_LIBRARY_CREATED_BASE_CARRIES_NO_ZONE_KEY(capture):
    """(c). The ``None`` is our create's omission, not Lark withholding an answer."""
    fresh = capture["c_fresh_api_created_base"]
    assert fresh["time_zone_key_present_in_raw_json"] is False
    assert fresh["sdk_view"]["sdk_time_zone"] is None
    zoned = capture["c_create_body_time_zone"]
    assert zoned["create_code"] == 0
    assert zoned["create_echo_time_zone"] == "Asia/Singapore"
    assert zoned["app_meta_after_create"]["time_zone_raw_value"] == "Asia/Singapore"


def test_the_capture_shows_NOTHING_ELSE_ON_THE_APP_PAYLOAD_CARRIES_A_ZONE(capture):
    """(d). Enumerated rather than asserted, so the claim's edge is visible."""
    keys = set(capture["c_fresh_api_created_base"]["app_payload_keys"])
    assert keys == {"app_token", "formula_type", "is_advanced", "name", "revision"}


# --------------------------------------------------------------------------- #
# AC2 — the round trip is correct, or disclosed; never silently shifted        #
# --------------------------------------------------------------------------- #

def test_a_DECLARED_zone_makes_the_date_only_round_trip_EXACT(calendar_rows):
    """AC2, first fork, over every measured (convention, date) pair.

    Read in the zone the value was authored in, every one of the nine stored integers renders
    the calendar date that was intended — including the month boundary and the year boundary.
    """
    for row in calendar_rows:
        zone = _CONVENTION_ZONE[row["convention"]]
        assert render(row["stored_DateOnly"], zone) == row["intended_calendar_date"], row


def test_the_SILENT_UTC_FALLBACK_IS_THE_DEFECT_and_the_capture_proves_the_shift(calendar_rows):
    """The bug, as a permanent regression test: a local-midnight value read with no zone lands
    one calendar day early. This asserts the defect still *exists as a fact about the epoch* —
    what the fix changes is that it is no longer **silent** (below) and no longer the path a
    Base this library creates takes at all."""
    shifted = [row for row in calendar_rows if row["convention"] == "plus8_midnight"]
    assert shifted, "the capture must carry the +8 convention that reproduced the report"
    for row in shifted:
        intended = dt.date.fromisoformat(row["intended_calendar_date"].replace("/", "-"))
        rendered = render(row["stored_DateOnly"], None)
        assert rendered == (intended - dt.timedelta(days=1)).strftime("%Y/%m/%d"), row
        assert date_zone.zone_disclosure(None), (
            "and it may never be silent: the assumption that produced this date must be "
            "disclosed")


# --------------------------------------------------------------------------- #
# AC4 — the None path is an explicit, disclosed assumption                     #
# --------------------------------------------------------------------------- #

def test_resolve_zone_on_NONE_is_an_ASSUMPTION_carrying_its_own_disclosure():
    provenance = date_zone.resolve_zone(None)
    assert provenance.declared is False
    assert provenance.zone == date_zone.ASSUMED_ZONE == "UTC"
    disclosure = provenance.disclosure
    assert disclosure and disclosure == date_zone.zone_disclosure(None)
    for expected in ("UTC", "one calendar day", "time_zone"):
        assert expected in disclosure, f"the disclosure must name {expected!r}"


def test_resolve_zone_on_a_DECLARED_zone_discloses_NOTHING_because_nothing_was_assumed():
    provenance = date_zone.resolve_zone("Asia/Singapore")
    assert provenance.declared is True
    assert provenance.zone == "Asia/Singapore"
    assert provenance.disclosure is None
    assert date_zone.zone_disclosure("Asia/Singapore") is None


def test_an_EMPTY_STRING_zone_is_the_same_absence_as_None():
    """The wire's two spellings of "no zone" — an absent key and an empty value — are one fact."""
    assert date_zone.resolve_zone("") == date_zone.resolve_zone(None)


def test_the_READ_RESULT_carries_the_disclosure_where_a_consumer_can_see_it():
    """AC4's chosen home: the read's own provenance, not only a docstring.

    Derived from ``time_zone`` rather than stored beside it, so the two can never disagree —
    which is also why no golden output moves: nothing is added to the rendered bytes.
    """
    assumed = assemble_base(app_token="app", name="n", time_zone=None, tables=())
    assert assumed.date_zone_assumed is True
    assert assumed.date_zone == date_zone.ASSUMED_ZONE
    assert assumed.date_zone_disclosure == date_zone.zone_disclosure(None)
    declared = assemble_base(app_token="app", name="n", time_zone="Asia/Singapore", tables=())
    assert declared.date_zone_assumed is False
    assert declared.date_zone == "Asia/Singapore"
    assert declared.date_zone_disclosure is None


def test_the_disclosure_is_NEVER_in_the_rendered_bytes_zero_drift():
    """AC4 discloses on the result object; AC2's "no silent shift" is not paid for with a
    reader-output change. A marker in the Markdown would move every Base golden there is."""
    from larkdocio.base.table import render_base

    assumed = assemble_base(app_token="app", name="n", time_zone=None, tables=())
    assert date_zone.ASSUMED_DISCLOSURE not in render_base(assumed)


# --------------------------------------------------------------------------- #
# AC3 — one policy, authored once, referenced from both sides                  #
# --------------------------------------------------------------------------- #

def test_the_policy_is_AUTHORED_ONCE_and_the_render_constant_IS_that_authoring():
    assert DEFAULT_TIME_ZONE is date_zone.ASSUMED_ZONE
    for clause in ("instant", "create", "UTC"):
        assert clause in date_zone.POLICY, f"the policy statement must name {clause!r}"


@pytest.mark.parametrize("module_name", [
    "larkdocio.base.cells",            # the read side, which picks the zone
    "larkdocio.base.table",            # the read result, which discloses the pick
    "larkdocio.base.client",           # the read of the app payload that reports it
    "larkdocio.base.write_cells",      # the write side, which refuses one
    "larkdocio.base.schema_client",    # the one route that can DECLARE one
    "larkdocio.base.schema_plan",      # the plan that previews the declaration
])
def test_BOTH_SIDES_REFERENCE_the_one_policy_rather_than_restating_it(module_name):
    module = importlib.import_module(module_name)
    source = inspect.getsource(module)
    assert "date_zone" in source, (
        f"{module_name} must reference larkdocio.base.date_zone rather than carry its own "
        "second story about timezones")


def test_rendering_is_STILL_a_pure_function_of_value_formatter_and_zone(monkeypatch):
    """The promise the fix may not break — including on the None path, which is the one that
    changed. A host clock or locale may not reach the output."""
    before = [render(row, None) for row in (1772294400000, 1798732800000, 1786636800000)]
    monkeypatch.setenv("TZ", "Pacific/Kiritimati")
    monkeypatch.setenv("LC_ALL", "de_DE.UTF-8")
    assert [render(row, None) for row in (1772294400000, 1798732800000, 1786636800000)] == before


def test_the_policy_module_reads_NO_HOST_CLOCK():
    """``cells.py``'s promise, enforced at the one new module that could have broken it.

    **Anchored at a word boundary** (LD-659): a bare substring search reports
    ``datetime.timezone.utc`` — which reads no clock at all, and is what the tz-database
    fallback returns — as a host-clock read, because ``dateTIME.TIMEzone`` contains
    ``time.time``. A guard that fires on the correct code teaches the next author to write it
    differently, which is the opposite of what this one is for.
    """
    source = inspect.getsource(date_zone)
    for forbidden in ("datetime.now", "time.time", "localtime", "tzlocal", "utcnow"):
        assert not re.search(r"\b" + re.escape(forbidden), source), (
            f"{forbidden} would make rendering host-dependent")


def test_that_word_boundary_still_catches_the_thing_it_is_FOR():
    """The other half: narrowing the pattern may not have narrowed it to nothing."""
    for forbidden in ("datetime.now", "time.time", "localtime", "tzlocal", "utcnow"):
        assert re.search(r"\b" + re.escape(forbidden), f"x = {forbidden}()"), forbidden
    assert not re.search(r"\b" + re.escape("time.time"), "return datetime.timezone.utc")
