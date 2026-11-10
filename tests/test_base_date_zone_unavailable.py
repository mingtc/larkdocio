"""LD-659 AC3 — a missing tz database stops silently changing the answer.

The defect, executed on `develop`: `base/cells._zone` caught `ZoneInfoNotFoundError` and fell
back to **UTC**, while the disclosure a caller reads keyed on `.declared` — which is `True` for
a Base that declared a zone. So on a host without the tz database (a slim container; Windows
without the `tzdata` package) every datetime cell was converted in the **wrong zone** and the
read result reported the zone it had been *asked* for. The fallback fired and the disclosure did
not change.

The fix is disclosure, not a dependency: adding `tzdata` at runtime is LD-664's decision, and
the fallback needs disclosing whether or not that ever lands.

**How the missing database is simulated.** `zoneinfo.ZoneInfo` is imported INSIDE
`date_zone.load_zone`, so the name it binds is looked up at call time — the module attribute is
what these tests replace, and there is no import-time default argument holding a stale
reference (the trap that made two agents believe a stub was in force when it was not). Each
test therefore proves the simulation actually bit, by asserting the loadable case first.
"""
import datetime
import sys

import pytest

from larkdocio.base import cells, date_zone
from larkdocio.base.table import assemble_base

DECLARED = "Asia/Shanghai"

#: A ms-epoch instant whose calendar day differs between UTC and Asia/Shanghai (+08:00):
#: 2026-02-28 16:00 UTC is 2026-03-01 00:00 in Shanghai.
INSTANT = 1772294400000

_FORMATTER = {"date_formatter": "yyyy/MM/dd HH:mm"}


@pytest.fixture
def no_tz_database(monkeypatch):
    """Make every ``zoneinfo.ZoneInfo`` construction fail the way a host with no tz database
    fails — including for ``UTC``, which is what a slim container really does."""
    import zoneinfo

    def raise_not_found(*_args, **_kwargs):
        raise zoneinfo.ZoneInfoNotFoundError("No time zone found with key (simulated)")

    monkeypatch.setattr(zoneinfo, "ZoneInfo", raise_not_found)
    # The import inside `load_zone` reads `sys.modules`, so patching the module object is what
    # the call really sees. Asserted rather than assumed:
    assert sys.modules["zoneinfo"].ZoneInfo is raise_not_found
    return raise_not_found


def test_the_simulation_really_bites_and_the_control_really_loads(no_tz_database):
    """The instrument first: if `load_zone` still resolved the zone, every assertion below
    would pass for the wrong reason."""
    assert date_zone.load_zone(DECLARED) is None


def test_with_the_database_present_NOTHING_about_this_changed():
    """The control, which is also the no-drift claim: on an ordinary host the declared zone is
    honoured, nothing is disclosed, and the rendered date is the same byte string as before."""
    provenance = date_zone.resolve_zone(DECLARED)
    assert provenance.zone == DECLARED
    assert provenance.declared is True
    assert provenance.assumed is False
    assert provenance.requested is None
    assert provenance.disclosure is None
    assert cells._format_datetime(INSTANT, _FORMATTER["date_formatter"], DECLARED) == (
        "2026/03/01 00:00")


# --------------------------------------------------------------------------- #
# The fallback still happens — and now it SAYS SO                              #
# --------------------------------------------------------------------------- #

def test_the_fallback_still_renders_in_UTC(no_tz_database):
    """Unchanged on purpose: something has to be rendered, and a fixed zone keeps the output a
    function of the payload. What changed is the silence, not the fallback."""
    assert cells._format_datetime(INSTANT, _FORMATTER["date_formatter"], DECLARED) == (
        "2026/02/28 16:00")


def test_the_provenance_no_longer_reports_the_zone_it_was_ASKED_for(no_tz_database):
    provenance = date_zone.resolve_zone(DECLARED)
    assert provenance.zone == date_zone.ASSUMED_ZONE     # what was really used
    assert provenance.requested == DECLARED              # what was asked for
    assert provenance.declared is True                   # the Base did declare one
    assert provenance.assumed is True                    # and larkdocio still chose the zone


def test_the_disclosure_names_the_zone_the_cause_and_the_remedy(no_tz_database):
    disclosure = date_zone.zone_disclosure(DECLARED)
    assert disclosure == date_zone.UNAVAILABLE_DISCLOSURE.format(zone=DECLARED)
    assert DECLARED in disclosure
    assert "tz database" in disclosure and "tzdata" in disclosure
    assert "wrong calendar day" in disclosure
    assert "re-read" in disclosure


def test_the_two_assumptions_are_DIFFERENT_sentences(no_tz_database):
    """A caller cannot act on "assumed" alone: no declaration means *declare one at create
    time*, an unloadable declaration means *install the tz database here*. One sentence for
    both would give half of them the wrong instruction."""
    assert date_zone.zone_disclosure(None) == date_zone.ASSUMED_DISCLOSURE
    assert date_zone.zone_disclosure(DECLARED) != date_zone.ASSUMED_DISCLOSURE
    assert date_zone.zone_disclosure(DECLARED) != date_zone.zone_disclosure(None)


def test_the_READ_RESULT_carries_all_of_it(no_tz_database):
    read = assemble_base(app_token="app", name="n", time_zone=DECLARED, tables=())
    assert read.date_zone == "UTC"
    assert read.date_zone_assumed is True
    assert read.date_zone_requested == DECLARED
    assert read.date_zone_disclosure == date_zone.UNAVAILABLE_DISCLOSURE.format(zone=DECLARED)


def test_the_read_result_KEEPS_its_old_answers_on_the_two_old_paths():
    """The consumer-facing regression check for a key that changed meaning: `date_zone_assumed`
    still answers exactly as it did for a Base that declares no zone and for one whose zone
    loads. Only the third case — which used to lie — moved."""
    none_declared = assemble_base(app_token="a", name="n", time_zone=None, tables=())
    assert none_declared.date_zone_assumed is True
    assert none_declared.date_zone_requested is None
    assert none_declared.date_zone_disclosure == date_zone.ASSUMED_DISCLOSURE
    honoured = assemble_base(app_token="a", name="n", time_zone=DECLARED, tables=())
    assert honoured.date_zone_assumed is False
    assert honoured.date_zone_requested is None
    assert honoured.date_zone_disclosure is None


# --------------------------------------------------------------------------- #
# One decision, not two                                                        #
# --------------------------------------------------------------------------- #

def test_the_renderer_and_the_disclosure_read_ONE_loader(no_tz_database):
    """The root cause was two independent decisions about one fact. So: the zone
    `_format_datetime` renders in is the zone `resolve_zone` reports, in every case."""
    for asked in (None, "", DECLARED, "UTC", "Mars/Phobos"):
        provenance = date_zone.resolve_zone(asked)
        rendered = cells._format_datetime(INSTANT, "yyyy/MM/dd HH:mm", asked)
        expected = datetime.datetime.fromtimestamp(
            INSTANT / 1000, date_zone.load_zone(provenance.zone))
        assert rendered == expected.strftime("%Y/%m/%d %H:%M"), asked


def test_an_UNKNOWN_zone_name_is_the_same_class_and_is_disclosed_too():
    """No simulation needed for this one — the tz database is present and simply has no such
    key, which used to be silent for exactly the same reason."""
    provenance = date_zone.resolve_zone("Mars/Phobos")
    assert provenance.zone == "UTC"
    assert provenance.requested == "Mars/Phobos"
    assert provenance.disclosure and "Mars/Phobos" in provenance.disclosure


def test_the_assumed_zone_is_loadable_even_with_no_database(no_tz_database):
    """A fallback that can itself fail is not a fallback: `ZoneInfo("UTC")` raises on such a
    host too, so the assumed zone is answered from `datetime`."""
    assert date_zone.load_zone(date_zone.ASSUMED_ZONE) is datetime.timezone.utc
    assert date_zone.load_zone(None) is datetime.timezone.utc
    assert cells._zone(date_zone.ASSUMED_ZONE) is datetime.timezone.utc
