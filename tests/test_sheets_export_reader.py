"""Offline unit tests for the stdlib-only xlsx-export reader (LD-114).

Two halves, both offline:

* **Export task lifecycle (AC1)** — ``create_export_task`` → ``poll_export_task`` →
  ``download_export`` (and the ``export_xlsx`` orchestration) driven with an injected
  transport fed the ``captures/02b-export-fidelity.json`` shapes: the right
  method/path/body per call, ticket→poll→file_token→download chaining, the typed
  taxonomy on API/job failure, and a **bounded** poll loop that sleeps ≥0.5s.
* **Stdlib-only parse (AC2)** — ``parse_xlsx`` recovers a styled cell's value + bold +
  fill (``FFFFFF00``) + numFmt (``0.00%``) from a synthesized workbook (the fidelity
  sample), plus shared/inline strings, merge refs, multi-sheet resolution, and
  malformed-workbook robustness (missing styles, dangling ``s=``, unknown numFmt id,
  corrupt zip). A source-grep test proves **no new dependency** (D2).

The live export round-trip on a self-provisioned disposable is QA/S5 (LD-118), not here.
"""
import json
import re
from pathlib import Path

import pytest

import xlsx_synth as X
from larkdocio.sheets import export_reader as ER
from larkdocio.sheets.export_reader import (
    SheetsExportReader,
    XlsxParseError,
    parse_xlsx,
)
from larkdocio.errors import LarkAPIError, LarkConfigError, LarkDocIOError

from write_harness import FakeClock

# The committed LD-107 spike capture — the source of the create/poll response shapes.
_CAPTURE = (
    Path(__file__).resolve().parent.parent
    / "tests" / "captures" / "sheets-write-spike" / "captures" / "02b-export-fidelity.json"
)
_CAP = json.loads(_CAPTURE.read_text(encoding="utf-8"))["captures"]
_TOKEN = "Example8f0059b95ae797ae3980"
_TICKET = "7666898784341069545"
_FILE_TOKEN = "Example06ee43f657c66705890b"


# --------------------------------------------------------------------------- #
# Test doubles: a fake clock + a queue-driven urlopen                           #
# --------------------------------------------------------------------------- #


class _Resp:
    def __init__(self, body: bytes, status=200):
        self._b = body
        self.status = status

    def read(self):
        return self._b


class QueueOpener:
    """Serves queued responses in order and records each request.

    Each queued item is a dict (JSON-encoded) or raw ``bytes`` (served verbatim —
    e.g. the downloaded xlsx). Records method / url / parsed body / auth header."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    def __call__(self, req, timeout=30):
        body = json.loads(req.data.decode()) if req.data else None
        self.requests.append({
            "method": req.get_method(),
            "url": req.full_url,
            "body": body,
            "auth": req.headers.get("Authorization"),
        })
        item = self._responses[len(self.requests) - 1]
        payload = item if isinstance(item, (bytes, bytearray)) else json.dumps(item).encode()
        return _Resp(bytes(payload))


def _reader(responses, **kw):
    clock = FakeClock()
    from larkdocio.common.transport import RateLimiter
    reader = SheetsExportReader(
        token_provider=lambda: "tok-TEST",
        urlopen=QueueOpener(responses),
        rate_limiter=RateLimiter(5, time_fn=clock.time, sleep_fn=clock.sleep),
        sleep_fn=clock.sleep,
        **kw,
    )
    return reader, clock


# --------------------------------------------------------------------------- #
# AC1 — export task lifecycle                                                   #
# --------------------------------------------------------------------------- #

def test_export_xlsx_runs_create_poll_download_in_sequence():
    """create → poll(job_status 0) → download, each hitting the right method+path,
    chained ticket→poll and file_token→download, returning the downloaded bytes."""
    xlsx = X.fidelity_workbook()
    reader, _ = _reader([
        _CAP["export_create"]["response"],       # create → ticket
        _CAP["export_poll_final"]["response"],    # poll → job_status 0 + file_token
        xlsx,                                     # download → bytes
    ])
    out = reader.export_xlsx(_TOKEN)
    assert out == xlsx

    reqs = reader._urlopen.requests
    assert len(reqs) == 3
    # create: POST /drive/v1/export_tasks with the exact body
    assert reqs[0]["method"] == "POST"
    assert reqs[0]["url"].endswith("/open-apis/drive/v1/export_tasks")
    assert reqs[0]["body"] == {"file_extension": "xlsx", "token": _TOKEN, "type": "sheet"}
    # poll: GET /drive/v1/export_tasks/{ticket}?token=
    assert reqs[1]["method"] == "GET"
    assert f"/open-apis/drive/v1/export_tasks/{_TICKET}" in reqs[1]["url"]
    assert f"token={_TOKEN}" in reqs[1]["url"]
    # download: GET /drive/v1/export_tasks/file/{file_token}/download
    assert reqs[2]["method"] == "GET"
    assert reqs[2]["url"].endswith(
        f"/open-apis/drive/v1/export_tasks/file/{_FILE_TOKEN}/download"
    )
    # bearer applied on every call
    assert all(r["auth"] == "Bearer tok-TEST" for r in reqs)


def test_poll_waits_pending_then_returns_done_and_sleeps_between_polls():
    """A pending job_status is polled again after a ≥0.5s sleep; the loop returns
    the result once job_status hits 0."""
    pending = {"code": 0, "data": {"result": {"job_status": 1}}}
    done = {"code": 0, "data": {"result": {"job_status": 0, "file_token": _FILE_TOKEN}}}
    reader, clock = _reader([pending, pending, done])
    result = reader.poll_export_task(_TICKET, _TOKEN)
    assert result["file_token"] == _FILE_TOKEN
    # two pending polls → two inter-poll sleeps, each ≥ 0.5s
    assert len(clock.sleeps) == 2
    assert all(dt >= 0.5 for dt in clock.sleeps)


def test_poll_timeout_is_bounded_and_raises_typed_error():
    """An always-pending job never loops forever: after ``max_polls`` it raises a
    typed LarkAPIError (no infinite loop)."""
    pending = {"code": 0, "data": {"result": {"job_status": 2}}}
    reader, clock = _reader([pending] * 10, max_polls=3)
    with pytest.raises(LarkAPIError) as ei:
        reader.poll_export_task(_TICKET, _TOKEN)
    assert "3" in str(ei.value)
    assert len(reader._urlopen.requests) == 3  # bounded — exactly max_polls polls


def test_poll_job_failure_raises_typed_error_with_message():
    """A non-zero, non-pending job_status is an export failure → typed LarkAPIError
    carrying the job_error_msg."""
    failed = {"code": 0, "data": {"result": {
        "job_status": 112, "job_error_msg": "export exceeded max cells"}}}
    reader, _ = _reader([failed])
    with pytest.raises(LarkAPIError) as ei:
        reader.poll_export_task(_TICKET, _TOKEN)
    assert "112" in str(ei.value)
    assert "export exceeded max cells" in str(ei.value)


def test_create_maps_nonzero_lark_code_to_typed_error():
    """A non-zero Lark code on create surfaces as a typed LarkAPIError carrying the code."""
    reader, _ = _reader([{"code": 1069902, "msg": "export permission denied"}])
    with pytest.raises(LarkAPIError) as ei:
        reader.create_export_task(_TOKEN)
    assert ei.value.code == 1069902


def test_create_without_ticket_raises_typed_error():
    reader, _ = _reader([{"code": 0, "data": {}}])
    with pytest.raises(LarkAPIError):
        reader.create_export_task(_TOKEN)


# --------------------------------------------------------------------------- #
# AC3 — credential duty (WRITE app for the write gate; READ app for read-side)  #
# --------------------------------------------------------------------------- #

def test_from_write_credentials_uses_write_creds(monkeypatch):
    """The write-gate export path resolves creds via ``get_write_credentials`` and
    the token provider fetches a token with THOSE creds (never read/legacy)."""
    captured = {}
    monkeypatch.setattr(ER, "get_write_credentials", lambda: ("WID", "WSEC"))
    monkeypatch.setattr(ER, "get_read_credentials", lambda: ("RID", "RSEC"))
    monkeypatch.setattr(ER, "apply_ipv4_pin", lambda: None)
    monkeypatch.setattr(
        ER, "fetch_tenant_access_token",
        lambda app_id, app_secret, domain, **kw: captured.update(
            id=app_id, secret=app_secret) or "tok-write",
    )
    reader = SheetsExportReader.from_write_credentials()
    assert reader._token_provider() == "tok-write"
    assert captured == {"id": "WID", "secret": "WSEC"}


def test_from_read_credentials_uses_read_creds(monkeypatch):
    """The read-side fidelity leg (D1 — READ-app drive:export PROVEN) runs on READ creds."""
    captured = {}
    monkeypatch.setattr(ER, "get_read_credentials", lambda: ("RID", "RSEC"))
    monkeypatch.setattr(ER, "apply_ipv4_pin", lambda: None)
    monkeypatch.setattr(
        ER, "fetch_tenant_access_token",
        lambda app_id, app_secret, domain, **kw: captured.update(
            id=app_id, secret=app_secret) or "tok-read",
    )
    reader = SheetsExportReader.from_read_credentials()
    assert reader._token_provider() == "tok-read"
    assert captured == {"id": "RID", "secret": "RSEC"}


def test_from_read_credentials_missing_creds_is_typed_config_error(monkeypatch):
    monkeypatch.setattr(ER, "get_read_credentials", lambda: ("", ""))
    monkeypatch.setattr(ER, "apply_ipv4_pin", lambda: None)
    with pytest.raises(LarkConfigError):
        SheetsExportReader.from_read_credentials()


def test_poll_interval_below_floor_is_refused():
    """The gentle-poll floor is enforced: a poll interval < 0.5s is a config error."""
    with pytest.raises(LarkConfigError):
        SheetsExportReader(token_provider=lambda: "t", poll_interval=0.1)


# --------------------------------------------------------------------------- #
# AC2 — stdlib-only parse: the fidelity sample                                  #
# --------------------------------------------------------------------------- #

def test_parse_recovers_bold_fill_numfmt_and_value():
    """The LD-107 Q2 fidelity: cell A1 → value 0.1234, bold, fill FFFFFF00, numFmt 0.00%."""
    wb = parse_xlsx(X.fidelity_workbook())
    cell = wb.first_sheet.cell("A1")
    assert cell.value == 0.1234
    assert cell.bold is True
    assert cell.italic is False
    assert cell.fill_rgb == "FFFFFF00"
    assert cell.num_fmt == "0.00%"


def test_read_workbook_orchestrates_export_then_parse():
    """``read_workbook`` = export_xlsx + parse_xlsx (the full read-side entry)."""
    reader, _ = _reader([
        _CAP["export_create"]["response"],
        _CAP["export_poll_final"]["response"],
        X.fidelity_workbook(),
    ])
    wb = reader.read_workbook(_TOKEN)
    assert wb.first_sheet.cell("A1").num_fmt == "0.00%"


def test_italic_font_is_recovered():
    styles = X.styles_xml(
        fonts=[{}, {"italic": True}],
        cell_xfs=[{"numFmtId": 0, "fontId": 0, "fillId": 0},
                  {"numFmtId": 0, "fontId": 1, "fillId": 0}],
    )
    wb = parse_xlsx(X.build_workbook(
        [{"name": "S", "cells": [("A1", {"s": 1, "v": "5"})]}], styles=styles))
    cell = wb.first_sheet.cell("A1")
    assert cell.italic is True
    assert cell.bold is False


def test_cell_without_style_index_is_default():
    """A cell with no ``s=`` takes the default style (not bold, no fill, no numFmt)."""
    wb = parse_xlsx(X.build_workbook(
        [{"name": "S", "cells": [("A1", {"v": "42"})]}]))
    cell = wb.first_sheet.cell("A1")
    assert cell.value == 42
    assert cell.bold is False
    assert cell.fill_rgb is None
    assert cell.num_fmt is None


def test_shared_string_cell_is_resolved():
    wb = parse_xlsx(X.build_workbook(
        [{"name": "S", "cells": [("A1", {"t": "s", "v": "1"})]}],
        shared_strings=["zero", "hello world"]))
    assert wb.first_sheet.cell("A1").value == "hello world"


def test_inline_string_cell_is_resolved():
    wb = parse_xlsx(X.build_workbook(
        [{"name": "S", "cells": [("A1", {"t": "inlineStr", "inline": "inline text"})]}]))
    assert wb.first_sheet.cell("A1").value == "inline text"


def test_boolean_cell_is_resolved():
    wb = parse_xlsx(X.build_workbook(
        [{"name": "S", "cells": [("A1", {"t": "b", "v": "1"}),
                                 ("B1", {"t": "b", "v": "0"})]}]))
    assert wb.first_sheet.cell("A1").value is True
    assert wb.first_sheet.cell("B1").value is False


def test_integer_value_stays_int():
    wb = parse_xlsx(X.build_workbook(
        [{"name": "S", "cells": [("A1", {"v": "42"})]}]))
    assert wb.first_sheet.cell("A1").value == 42
    assert isinstance(wb.first_sheet.cell("A1").value, int)


def test_merge_refs_are_recovered():
    wb = parse_xlsx(X.build_workbook(
        [{"name": "S", "cells": [("A1", {"v": "1"})], "merges": ["A1:C1", "A3:A5"]}]))
    assert wb.first_sheet.merges == ("A1:C1", "A3:A5")


def test_builtin_numfmt_id_resolves_to_standard_pattern():
    """A built-in numFmt id (no custom ``<numFmt>``) resolves to its standard pattern."""
    styles = X.styles_xml(
        cell_xfs=[{"numFmtId": 0, "fontId": 0, "fillId": 0},
                  {"numFmtId": 10, "fontId": 0, "fillId": 0}])  # 10 = "0.00%"
    wb = parse_xlsx(X.build_workbook(
        [{"name": "S", "cells": [("A1", {"s": 1, "v": "0.5"})]}], styles=styles))
    assert wb.first_sheet.cell("A1").num_fmt == "0.00%"


# --------------------------------------------------------------------------- #
# AC2 — multi-sheet resolution                                                  #
# --------------------------------------------------------------------------- #

def test_multi_sheet_resolves_names_and_picks_right_worksheet():
    wb = parse_xlsx(X.build_workbook([
        {"name": "First", "cells": [("A1", {"t": "inlineStr", "inline": "on first"})]},
        {"name": "Second", "cells": [("A1", {"t": "inlineStr", "inline": "on second"})]},
    ]))
    assert [s.name for s in wb.sheets] == ["First", "Second"]
    assert wb.sheet("First").cell("A1").value == "on first"
    assert wb.sheet("Second").cell("A1").value == "on second"


def test_workbook_without_sheet_map_falls_back_to_discovery():
    wb = parse_xlsx(X.build_workbook(
        [{"name": "Ignored", "cells": [("A1", {"v": "7"})]}], include_workbook=False))
    assert len(wb.sheets) == 1
    assert wb.first_sheet.cell("A1").value == 7


# --------------------------------------------------------------------------- #
# Test-rigor amplifier — malformed / edge workbooks (typed errors, no crash)    #
# --------------------------------------------------------------------------- #

def test_missing_styles_xml_degrades_gracefully():
    """A workbook with no ``xl/styles.xml`` still yields values (style → default)."""
    wb = parse_xlsx(X.build_workbook(
        [{"name": "S", "cells": [("A1", {"s": 1, "v": "9"})]}], include_styles=False))
    cell = wb.first_sheet.cell("A1")
    assert cell.value == 9
    assert cell.bold is False and cell.fill_rgb is None and cell.num_fmt is None


def test_style_index_out_of_range_degrades_gracefully():
    """A dangling ``s=`` index (beyond cellXfs) → default style, value intact, no crash."""
    styles = X.styles_xml(cell_xfs=[{"numFmtId": 0, "fontId": 0, "fillId": 0}])
    wb = parse_xlsx(X.build_workbook(
        [{"name": "S", "cells": [("A1", {"s": 99, "v": "3"})]}], styles=styles))
    cell = wb.first_sheet.cell("A1")
    assert cell.value == 3
    assert cell.bold is False


def test_unknown_numfmt_id_is_none_not_a_crash():
    styles = X.styles_xml(cell_xfs=[{"numFmtId": 0, "fontId": 0, "fillId": 0},
                                    {"numFmtId": 999, "fontId": 0, "fillId": 0}])
    wb = parse_xlsx(X.build_workbook(
        [{"name": "S", "cells": [("A1", {"s": 1, "v": "1"})]}], styles=styles))
    assert wb.first_sheet.cell("A1").num_fmt is None


def test_corrupt_zip_raises_typed_parse_error():
    with pytest.raises(XlsxParseError):
        parse_xlsx(b"this is not a zip file at all")


def test_parse_error_is_a_larkdocio_error():
    """XlsxParseError is under the toolkit's base type (except LarkDocIOError catches it)."""
    assert issubclass(XlsxParseError, LarkDocIOError)


def test_malformed_worksheet_xml_raises_typed_parse_error():
    bad = X.zip_xlsx({
        "xl/workbook.xml": X.workbook_xml(["S"]),
        "xl/_rels/workbook.xml.rels": X.workbook_rels_xml(1),
        "xl/worksheets/sheet1.xml": "<worksheet><sheetData><row>OPEN",  # unclosed
        "xl/styles.xml": X.styles_xml(),
    })
    with pytest.raises(XlsxParseError):
        parse_xlsx(bad)


# --------------------------------------------------------------------------- #
# AC2 — no new dependency (D2)                                                   #
# --------------------------------------------------------------------------- #

def test_export_reader_imports_no_forbidden_dependency():
    """D2 absolute: the reader parses with zipfile + xml.etree only — no ``import``
    of openpyxl / lxml / pandas / xlrd / xlsxwriter (prose mentions in the docstring,
    which name the banned deps, don't count — only real import statements)."""
    src = Path(ER.__file__).read_text(encoding="utf-8")
    for forbidden in ("openpyxl", "lxml", "pandas", "xlrd", "xlsxwriter"):
        assert not re.search(
            rf"^\s*(?:import|from)\s+{forbidden}\b", src, re.MULTILINE
        ), f"export_reader must not import {forbidden!r} (D2)."
    assert "import zipfile" in src
    assert re.search(r"import xml\.etree", src)
