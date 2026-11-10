"""Offline unit tests for used-range discovery + in-memory trim (LD-102).

The Sheets values API returns the **full declared grid** with trailing cells as
``null`` (spike Q2: a 200×20 sheet reads back 200×20, never trimmed server-side).
So L1 must find the true used range itself: read the tab's **declared grid** extent
from the v3 tab-query metadata as the **upper bound** (never read past it — no
iterative over-probe), then **trim trailing all-null rows/columns** in memory to
the minimal bounding range. Interior blanks — empty interior cells AND
merge-covered ``null``s — must survive so S4's merge join (LD-104) stays correct.

Every matrix here is fed from the LD-100 opener spike's **committed captures**
(``tests/captures/sheets-spike/captures/01-extent-*.json``) — the exact bytes a real 200×20
read returned — so the fixtures pin real payload shapes and an API drift reddens
the suite (PROJECT.md § Quality bar). All offline: a stub opener, no network.
"""
import json
import urllib.parse
from pathlib import Path

from larkdocio.sheets.extent import (
    UsedRange,
    column_number_to_a1,
    declared_grid_range,
    trim_trailing_nulls,
    used_range_a1,
)
from larkdocio.sheets.client import SheetsReadClient
from larkdocio.sheets.models import SheetTab

from write_harness import _FakeHTTPResponse

_CAPTURES = Path(__file__).resolve().parent.parent / "tests" / "captures" / "sheets-spike" / "captures"


def _capture(name):
    return json.loads((_CAPTURES / name).read_text(encoding="utf-8"))


def _extent_values(name):
    """The raw (untrimmed) 200×20 values matrix from an ``01-extent-*`` capture."""
    return _capture(name)["data"]["valueRange"]["values"]


# --------------------------------------------------------------------------- #
# Test doubles (offline — a stub opener; mirrors test_sheets_client)            #
# --------------------------------------------------------------------------- #


class StubOpener:
    """Records each urllib GET and returns the next queued payload (a dict)."""

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.requests = []

    def __call__(self, req, timeout=30):
        self.requests.append({"method": req.get_method(), "url": req.full_url})
        return _FakeHTTPResponse(self._payloads[len(self.requests) - 1])


def _client(opener, **kw):
    return SheetsReadClient(
        "app", "secret", "larksuite.com",
        urlopen=opener,
        token_fetcher=lambda *a, **k: "t-test",
        **kw,
    )


def _requested_range(url):
    """The A1 range from a values-endpoint URL path (``.../values/{sheetId}!A1:T200``)."""
    path = urllib.parse.urlsplit(url).path
    return urllib.parse.unquote(path.rsplit("/values/", 1)[1])


def _parse_end(a1_range):
    """(end_col_index_0based, end_row_1based) of an A1 range's END corner.

    ``444a1c!A1:T200`` → col T = index 19, row 200.
    """
    end = a1_range.split("!", 1)[1].split(":")[1]
    letters = "".join(c for c in end if c.isalpha())
    digits = "".join(c for c in end if c.isdigit())
    col = 0
    for ch in letters:
        col = col * 26 + (ord(ch) - ord("A") + 1)
    return col - 1, int(digits)


# --------------------------------------------------------------------------- #
# AC1 — the declared grid is the UPPER BOUND (no iterative over-probe)          #
# --------------------------------------------------------------------------- #

def test_column_number_to_a1_bijective_base26():
    assert column_number_to_a1(1) == "A"
    assert column_number_to_a1(20) == "T"      # the scratch sheet's 20-col grid
    assert column_number_to_a1(26) == "Z"
    assert column_number_to_a1(27) == "AA"
    assert column_number_to_a1(52) == "AZ"
    assert column_number_to_a1(53) == "BA"
    assert column_number_to_a1(702) == "ZZ"


def test_declared_grid_range_covers_exactly_the_declared_grid():
    # A 200×20 declared grid → its own extent A1:T200, never one cell further.
    assert declared_grid_range("444a1c", 200, 20) == "444a1c!A1:T200"
    end_col, end_row = _parse_end(declared_grid_range("444a1c", 200, 20))
    assert end_row <= 200 and end_col <= 20 - 1   # bounded BY the grid, not past it


def test_read_used_range_reads_only_within_declared_grid_no_over_probe():
    """AC1: extent discovery requests the DECLARED grid as the upper bound and
    issues exactly ONE read — no iterative probing past the grid."""
    tab = SheetTab(sheet_id="444a1c", title="Types", index=0,
                   row_count=200, column_count=20)
    opener = StubOpener([_capture("01-extent-Types.json")])
    client = _client(opener)

    result = client.read_used_range("SheetScratchExample00000001", tab)

    # Exactly one values read — no iterative over-probe (AC1).
    values_reads = [r for r in opener.requests if "/values/" in r["url"]]
    assert len(values_reads) == 1
    # The requested range is bounded by the declared grid (never past it).
    req_range = _requested_range(values_reads[0]["url"])
    end_col, end_row = _parse_end(req_range)
    assert end_row <= tab.row_count
    assert end_col <= tab.column_count - 1
    # And it discovered + trimmed the true used range.
    assert isinstance(result, UsedRange)
    assert result.a1_range == "444a1c!A1:D24"


# --------------------------------------------------------------------------- #
# AC2 — trailing all-null rows AND columns trimmed to the minimal used range    #
# --------------------------------------------------------------------------- #

def test_trim_types_extent_fixture_to_a1_d24():
    """The Types tab: 200×20 declared read → minimal used range A1:D24 (spike Q2)."""
    trimmed = trim_trailing_nulls(_extent_values("01-extent-Types.json"))

    assert len(trimmed) == 24                       # 200 rows → 24 used rows
    assert all(len(row) == 4 for row in trimmed)    # 20 cols → 4 used cols (A:D)
    assert used_range_a1("444a1c", trimmed) == "444a1c!A1:D24"


def test_trim_merged_extent_fixture_to_a1_c10():
    """The Merged tab: 200×20 declared read → minimal used range A1:C10 (spike Q2)."""
    trimmed = trim_trailing_nulls(_extent_values("01-extent-Merged.json"))

    assert len(trimmed) == 10                       # 200 rows → 10 used rows
    assert all(len(row) == 3 for row in trimmed)    # 20 cols → 3 used cols (A:C)
    assert used_range_a1("7pg9wE", trimmed) == "7pg9wE!A1:C10"


def test_trim_strips_trailing_null_rows_and_columns_synthetic():
    raw = [
        ["a", None, "c", None, None],   # cols D,E are a trailing-null column region
        [None, "e", None, None, None],
        [None, None, None, None, None],  # an INTERIOR all-null row (row 4 has data)
        ["g", None, "i", None, None],
        [None, None, None, None, None],  # trailing all-null row → trimmed
        [None, None, None, None, None],  # trailing all-null row → trimmed
    ]
    assert trim_trailing_nulls(raw) == [
        ["a", None, "c"],
        [None, "e", None],
        [None, None, None],
        ["g", None, "i"],
    ]


def test_trim_all_null_matrix_returns_empty():
    assert trim_trailing_nulls([]) == []
    assert trim_trailing_nulls([[None, None], [None], [None, None, None]]) == []


# --------------------------------------------------------------------------- #
# AC3 — interior nulls (empty interior cells + merge-covered nulls) preserved   #
# --------------------------------------------------------------------------- #

def test_interior_empty_cell_survives_trim():
    """A null NOT in a trailing all-null row/col is retained as an empty cell."""
    raw = [
        ["a", "b", "c", None],
        ["d", None, "f", None],   # the interior null at B2 must survive
        [None, None, None, None],  # trailing all-null row → trimmed
    ]
    trimmed = trim_trailing_nulls(raw)
    assert trimmed == [["a", "b", "c"], ["d", None, "f"]]
    assert trimmed[1][1] is None   # interior blank preserved, not dropped


def test_interior_all_null_row_survives_on_merged_fixture():
    """Merged row 2 (index 1) is entirely null but INTERIOR (data above and below)
    — the trim must keep it, not collapse it (it feeds the S4 merge join)."""
    trimmed = trim_trailing_nulls(_extent_values("01-extent-Merged.json"))
    assert trimmed[1] == [None, None, None]     # interior all-null row preserved


def test_merge_covered_interior_nulls_survive_on_merged_fixture():
    """The A1:C1 merge's covered cells read back as ``null``; the anchor row must
    keep those interior blanks so S4 can join them against the merges metadata."""
    trimmed = trim_trailing_nulls(_extent_values("01-extent-Merged.json"))
    # A1 anchor carries the value; B1/C1 (merge-covered) stay null within the box.
    assert trimmed[0] == ["merged title spanning A1:C1", None, None]


def test_interior_null_survives_on_types_fixture():
    """The Types data column C is blank on many rows (interior nulls); those blanks
    must survive the trim to A1:D24, not be mistaken for trailing padding."""
    trimmed = trim_trailing_nulls(_extent_values("01-extent-Types.json"))
    # Row 2 (index 1): 'plain string' | 'hello world' | <blank C> | 'hello world'.
    assert trimmed[1] == ["plain string", "hello world", None, "hello world"]
    assert trimmed[1][2] is None
