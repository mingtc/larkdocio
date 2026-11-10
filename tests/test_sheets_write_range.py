"""Offline unit tests for the A1/range WRITE model (LD-110).

The write client (S1, LD-109) addresses cells by range; rather than fork a
parallel A1 parser, the Sheets value-write spec § F1-S2 **reuses L1's** A1/range + used-range vocabulary
(``sheets/extent.py`` — ``column_number_to_a1`` and its new inverse
``a1_column_to_number`` — and ``UsedRange``), extending it **only** where a write
needs it: a **single-cell normalize** (``B2`` → ``B2:B2``, D2 — a bare cell is not
a writable range), range **validation** (reject inverted / out-of-grid / over the
100-column notation ceiling before any write), and a **used-range-aware target**
(a write can target a discovered used range or an explicit range).

These pin the offline model (no network) — the story is offline, no live gate:

* **AC1** — the write target is built from L1's types and reads its ``Start:End`` back;
* **AC2** — a single-cell target normalizes to ``A1:A1``; a bare cell (``A1Cell``) is
  a coordinate, not a writable range;
* **AC3** — a malformed/inverted/out-of-grid range raises an inspectable typed error
  before any write; a used-range-relative target resolves against L1's extent;
* the **test-rigor amplifier** — a seeded property-style parse→emit→parse round-trip
  corpus (stdlib ``random`` + a FIXED seed, no new deps), column-letter arithmetic
  edges (Z→AA→AZ→BA, the 100-col ceiling), out-of-grid refusal, and torture strings.
"""
import random

import pytest

from larkdocio.errors import LarkConfigError
from larkdocio.sheets.extent import (
    UsedRange,
    a1_column_to_number,
    column_number_to_a1,
)
from larkdocio.sheets.write_client import normalize_write_range
from larkdocio.sheets.write_range import (
    MAX_A1_COLUMN,
    A1Cell,
    WriteRange,
    parse_write_range,
    write_range_from_used_range,
)


# --------------------------------------------------------------------------- #
# AC1 — the write target is built from L1's model and reads its Start:End back  #
# --------------------------------------------------------------------------- #

def test_write_range_built_from_l1_cells_reads_start_end_back():
    """A write target constructed from L1's A1 coordinate types emits an explicit
    ``{sid}!Start:End`` range — the D2 contract the S1 client consumes."""
    wr = WriteRange(A1Cell(1, 1), A1Cell(4, 24), sheet_id="444a1c")
    assert wr.a1() == "444a1c!A1:D24"
    assert wr.n_rows == 24
    assert wr.n_cols == 4


def test_write_range_without_prefix_emits_bare_body():
    assert WriteRange(A1Cell(1, 1), A1Cell(3, 3)).a1() == "A1:C3"


def test_a1cell_parse_emit_round_trip():
    assert A1Cell.parse("B2") == A1Cell(2, 2)
    assert A1Cell.parse("AA100") == A1Cell(27, 100)
    assert A1Cell(2, 2).a1() == "B2"


# --------------------------------------------------------------------------- #
# AC2 — single-cell normalize (D2); a bare A1Cell is not a writable range       #
# --------------------------------------------------------------------------- #

def test_single_cell_target_normalizes_to_start_end():
    wr = parse_write_range("444a1c!B2")
    assert wr.start == wr.end == A1Cell(2, 2)
    assert wr.a1() == "444a1c!B2:B2"
    assert ":" in wr.a1()


def test_single_cell_without_prefix_normalizes():
    assert parse_write_range("B2").a1() == "B2:B2"


def test_a1cell_is_a_coordinate_not_a_writable_range():
    """A bare cell is a coordinate (no colon); only a WriteRange emits a writable
    ``Start:End`` — a single cell must be wrapped as a 1x1 range to be written."""
    cell = A1Cell.parse("B2")
    assert cell.a1() == "B2"
    assert ":" not in cell.a1()
    assert ":" in WriteRange(cell, cell).a1()


# --------------------------------------------------------------------------- #
# AC3 — validation (malformed / inverted / out-of-grid) + used-range awareness  #
# --------------------------------------------------------------------------- #

def test_valid_range_validates_within_grid():
    wr = parse_write_range("444a1c!A1:D24")
    assert wr.validate(grid_rows=200, grid_cols=20) is wr   # returns self, no raise


def test_inverted_range_raises_typed_error():
    wr = parse_write_range("444a1c!C3:A1")
    with pytest.raises(LarkConfigError) as ei:
        wr.validate()
    assert "invert" in str(ei.value).lower()


def test_inverted_on_one_axis_only_raises():
    # start col < end col but start row > end row → still inverted.
    with pytest.raises(LarkConfigError):
        parse_write_range("A5:C1").validate()


def test_out_of_grid_range_raises_typed_error():
    """A range past the declared grid extent is refused before any write (AC3)."""
    wr = parse_write_range("444a1c!A1:Z300")   # Z=26 > 20 cols; row 300 > 200
    with pytest.raises(LarkConfigError) as ei:
        wr.validate(grid_rows=200, grid_cols=20)
    assert "grid" in str(ei.value).lower()


def test_out_of_grid_column_only_raises():
    with pytest.raises(LarkConfigError):
        parse_write_range("A1:Z10").validate(grid_rows=200, grid_cols=20)


def test_row_below_one_is_malformed():
    # A0 → row 0; not a valid 1-indexed cell.
    with pytest.raises(LarkConfigError):
        parse_write_range("A0:B2").validate()


def test_malformed_range_raises_on_parse():
    for junk in ["", "   ", "!", "A1:B2:C3", "1A:2B", "@!#", "444a1c!"]:
        with pytest.raises(LarkConfigError):
            parse_write_range(junk)


def test_used_range_target_resolves_against_extent():
    """A used-range target resolves against L1's ``UsedRange`` (extent output) —
    the write addresses exactly the discovered used range."""
    ur = UsedRange(
        sheet_id="444a1c",
        a1_range="444a1c!A1:D24",
        revision=34,
        values=[["x"] * 4 for _ in range(24)],
    )
    wr = write_range_from_used_range(ur)
    assert wr.a1() == "444a1c!A1:D24"
    assert wr.validate(grid_rows=200, grid_cols=20) is wr


def test_used_range_from_tab_values_round_trips_to_write_target():
    """The full L1 path: trim a raw matrix into a UsedRange (extent), then build the
    write target from it — reuse, no reforked addressing."""
    from larkdocio.sheets.models import SheetTab

    tab = SheetTab(sheet_id="7pg9wE", title="T", index=0, row_count=200, column_count=20)
    raw = [["a", "b", None], ["c", None, None]] + [[None, None, None]] * 3
    ur = UsedRange.from_tab_values(tab, raw)
    wr = write_range_from_used_range(ur)
    assert wr.a1() == ur.a1_range          # addresses exactly the discovered extent
    assert wr.a1() == "7pg9wE!A1:B2"


def test_empty_used_range_has_no_write_target():
    ur = UsedRange(sheet_id="x", a1_range=None, revision=0, values=[])
    with pytest.raises(LarkConfigError):
        write_range_from_used_range(ur)


def test_open_range_resolves_against_used_range_extent():
    """A whole-column / mixed target resolves its open bound against the discovered
    used-range extent (grid dims) — used-range awareness for open forms."""
    # used range is A1:D24 → resolve A:D and A1:D against a 24x4 extent.
    assert parse_write_range("444a1c!A:D", grid_rows=24, grid_cols=4).a1() == "444a1c!A1:D24"
    assert parse_write_range("444a1c!A1:D", grid_rows=24, grid_cols=4).a1() == "444a1c!A1:D24"


# --------------------------------------------------------------------------- #
# Test-rigor amplifier — column-letter arithmetic (a1_column_to_number)         #
# --------------------------------------------------------------------------- #

def test_a1_column_to_number_bijective_base26():
    assert a1_column_to_number("A") == 1
    assert a1_column_to_number("Z") == 26
    assert a1_column_to_number("AA") == 27
    assert a1_column_to_number("AZ") == 52
    assert a1_column_to_number("BA") == 53
    assert a1_column_to_number("ZZ") == 702
    assert a1_column_to_number("CV") == 100      # the 100-col notation ceiling


def test_a1_column_to_number_is_case_insensitive():
    assert a1_column_to_number("aa") == 27
    assert a1_column_to_number("cv") == 100


def test_a1_column_to_number_inverts_column_number_to_a1():
    for n in [1, 25, 26, 27, 51, 52, 53, 100, 701, 702, 703]:
        assert a1_column_to_number(column_number_to_a1(n)) == n


def test_a1_column_to_number_rejects_non_letters():
    for bad in ["", "A1", "1", "A-", " A", "Ω"]:
        with pytest.raises((LarkConfigError, ValueError)):
            a1_column_to_number(bad)


# --------------------------------------------------------------------------- #
# Test-rigor amplifier — the 100-column notation ceiling (LD-107 Q1)            #
# --------------------------------------------------------------------------- #

def test_max_a1_column_is_the_100_col_ceiling():
    assert MAX_A1_COLUMN == 100
    assert column_number_to_a1(MAX_A1_COLUMN) == "CV"


def test_range_at_the_ceiling_validates():
    parse_write_range("s!A1:CV1").validate()      # CV == 100, no raise


def test_range_past_the_ceiling_is_refused():
    # CW == 101 → over the notation ceiling.
    assert a1_column_to_number("CW") == 101
    with pytest.raises(LarkConfigError) as ei:
        parse_write_range("s!A1:CW1").validate()
    assert "ceiling" in str(ei.value).lower() or "column" in str(ei.value).lower()


# --------------------------------------------------------------------------- #
# Test-rigor amplifier — torture strings                                        #
# --------------------------------------------------------------------------- #

def test_torture_single_cell_range():
    assert parse_write_range("A1:A1").a1() == "A1:A1"


def test_torture_full_column_resolves_against_grid():
    assert parse_write_range("A:A", grid_rows=200, grid_cols=20).a1() == "A1:A200"


def test_torture_full_column_without_grid_is_unbounded():
    with pytest.raises(LarkConfigError) as ei:
        parse_write_range("A:A")
    assert "grid" in str(ei.value).lower() or "unbounded" in str(ei.value).lower()


def test_torture_mixed_range_resolves_end_row_against_grid():
    assert parse_write_range("A1:C", grid_rows=200, grid_cols=20).a1() == "A1:C200"


def test_torture_inverted_range_flagged_not_silently_fixed():
    wr = parse_write_range("C3:A1")
    assert wr.start == A1Cell(3, 3) and wr.end == A1Cell(1, 1)   # preserved, not reordered
    with pytest.raises(LarkConfigError):
        wr.validate()


def test_torture_unicode_whitespace_sheet_prefix_preserved_verbatim():
    """The sheet-id prefix is an opaque token (unicode / internal whitespace
    preserved verbatim); only the cell-range body is parsed strictly."""
    wr = parse_write_range("  Ω 表 sheet!A1:B2  ")
    assert wr.sheet_id == "Ω 表 sheet"
    assert wr.a1() == "Ω 表 sheet!A1:B2"


def test_torture_whitespace_around_endpoints_tolerated():
    assert parse_write_range("s! A1 : B2 ").a1() == "s!A1:B2"


# --------------------------------------------------------------------------- #
# Test-rigor amplifier — seeded property-style parse→emit→parse round-trip      #
# --------------------------------------------------------------------------- #

_SEED = 110_110  # FIXED seed — deterministic corpus, no new deps (stdlib random).
_SHEET_PREFIXES = ["", "154e99!", "abc123!", "444a1c!", "Ω 表!"]


def _gen_a1(rng):
    """A single seeded A1 target: bounded range or (20%) a single cell, start<=end."""
    prefix = rng.choice(_SHEET_PREFIXES)
    sc = rng.randint(1, MAX_A1_COLUMN)
    sr = rng.randint(1, 5000)
    ec = rng.randint(sc, MAX_A1_COLUMN)   # canonical: end col >= start col
    er = rng.randint(sr, 5000)            # canonical: end row >= start row
    start = f"{column_number_to_a1(sc)}{sr}"
    if rng.random() < 0.2:
        return f"{prefix}{start}"          # single cell → normalizes to start:start
    return f"{prefix}{start}:{column_number_to_a1(ec)}{er}"


def test_property_parse_emit_parse_is_a_stable_fixpoint():
    """Over a seeded corpus: ``emit(parse(x))`` is idempotent (canonical) and
    ``parse(canon(x)) == parse(x)`` — the parse→emit→parse identity."""
    rng = random.Random(_SEED)
    for _ in range(600):
        s = _gen_a1(rng)
        parsed = parse_write_range(s)
        canon = parsed.a1()
        # emitting again and re-parsing yields the same object (fixpoint).
        assert parse_write_range(canon) == parsed
        # and emit is idempotent (already canonical Start:End).
        assert parse_write_range(canon).a1() == canon


def test_property_every_emitted_range_is_start_end():
    """No seeded target ever emits a bare cell — the D2 structural guarantee that
    feeds the S1 client (parity with write_client.normalize_write_range)."""
    rng = random.Random(_SEED + 1)
    for _ in range(600):
        s = _gen_a1(rng)
        emitted = parse_write_range(s).a1()
        # strip the opaque prefix, then the body must carry a colon.
        body = emitted.rsplit("!", 1)[-1]
        assert ":" in body, f"bare cell emitted for {s!r}: {emitted!r}"


# --------------------------------------------------------------------------- #
# Consistency with the S1 client's minimal guard (feeds LD-109's guarantee)     #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("target", [
    "s!B2", "154e99!A1:C3", "A1", "abc123!CV100", "444a1c!A1:D24",
])
def test_model_emit_agrees_with_write_client_normalize(target):
    """The model's emit is byte-identical to the S1 client's ``normalize_write_range``
    for a bounded/single-cell target — one addressing scheme, two layers (the model
    validates; the client keeps the minimal Start:End guard)."""
    assert parse_write_range(target).a1() == normalize_write_range(target)
