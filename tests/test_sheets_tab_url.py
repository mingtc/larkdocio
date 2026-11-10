"""sheets.tab_url — the one click-proven mintable grammar (group (c)/M4).

A pure, offline function. The tenant host is an INPUT (it reaches the function on the
sheet's own URL), never derived from an API domain and never invented.
"""
import inspect
import pathlib

import pytest

import larkdocio.sheets as sheets
from larkdocio.common.url import SHEETS_CELL_LINK_UI_ONLY
from larkdocio.sheets.tab_link import tab_url

SHEET_URL = "https://your-domain.larksuite.com/sheets/SheetScratchExample00000001"
PM_WORKING_STRING = (
    "https://your-domain.larksuite.com/sheets/SheetScratchExample00000001?sheet=7pg9wE"
)


@pytest.mark.conformance
def test_builds_the_pm_exact_working_string_from_its_parts():
    assert tab_url(SHEET_URL, "7pg9wE") == PM_WORKING_STRING


@pytest.mark.conformance
def test_the_tenant_host_comes_from_the_input_url_not_an_api_domain():
    # A different tenant host must be preserved verbatim — proving the host is an input.
    got = tab_url("https://your-domain.feishu.cn/sheets/TOKEN123", "sid9")
    assert got == "https://your-domain.feishu.cn/sheets/TOKEN123?sheet=sid9"


@pytest.mark.conformance
def test_a_sheet_url_that_already_carries_a_query_is_rebuilt_cleanly():
    got = tab_url(f"{SHEET_URL}?sheet=old&rangeId=x", "7pg9wE")
    assert got == PM_WORKING_STRING


@pytest.mark.parametrize("bad", ["", "not-a-url", "https:///sheets/tok", "ftp://h/sheets/t"])
@pytest.mark.conformance
def test_a_missing_or_hostless_url_is_a_refusal_not_a_default(bad):
    with pytest.raises(ValueError):
        tab_url(bad, "7pg9wE")


@pytest.mark.conformance
def test_a_non_sheets_url_is_refused():
    with pytest.raises(ValueError):
        tab_url("https://your-domain.larksuite.com/docx/DOC123", "7pg9wE")


@pytest.mark.conformance
def test_a_missing_sheet_id_is_a_refusal():
    with pytest.raises(ValueError):
        tab_url(SHEET_URL, "")


@pytest.mark.conformance
def test_token_and_sheet_id_are_carried_unaltered():
    got = tab_url("https://h.larksuite.com/sheets/Keeps_UnderScores", "Sheet_Id_9")
    assert got == "https://h.larksuite.com/sheets/Keeps_UnderScores?sheet=Sheet_Id_9"


def test_docstring_quotes_the_cell_link_warning_verbatim():
    assert SHEETS_CELL_LINK_UI_ONLY in (tab_url.__doc__ or "")


@pytest.mark.conformance
def test_tab_url_is_reexported_on_the_sheets_facade():
    assert sheets.tab_url is tab_url
    assert "tab_url" in sheets.__all__


def test_tab_url_makes_no_api_call_and_derives_no_host_from_the_api_domain():
    src = pathlib.Path(inspect.getsourcefile(tab_url)).read_text(encoding="utf-8")
    # a pure string function: no client, no transport, and it never reuses
    # validate_download_url's API domain to derive the host.
    for forbidden in ("Client", "requests", "http.client", "validate_download_url", ".request("):
        assert forbidden not in src, f"tab_link.py must not reference {forbidden!r}"
