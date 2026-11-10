"""LD-461 — the printed index convention must be the one the op actually implements.

**The incident.** ``InsertColsAt(before_col=N)`` is 1-based against *displayed* column
position (``start = before_col - 1`` on its way to the wire), while the plan printed
``semantic: 'insert 1 column(s) before column 3'`` immediately beside
``convention: '0-index-half-open'``. A consumer read the ``convention`` line as the basis of
the number in the ``semantic`` line — the only reading the text supported — inserted one slot
early with ``code: 0`` and **no warning**, shifted a real column's data into the new slot and
spent three recovery writes getting back (dogfood round 4, ``dev/dogfood4/verdict-grid.md``
§ 1 row S2 / § 4 finding 9).

**What this file guards, and what it deliberately does NOT.** It hard-codes no landing slot.
For every structural request carrying an index it derives **two** 0-based half-open spans:

* the **wire** span, from the request's own ``descriptor()`` — the very numbers
  :func:`~larkdocio.sheets.ops._apply_structural_one` hands to
  ``insert_dimension_range`` / ``delete_dimension_range`` — reduced through the *printed*
  ``convention``; and
* the **printed** span, from the caller-facing position the diagnostics quote, reduced through
  the *printed* ``position_convention``.

They must be the same span. So a future change that re-bases a parameter, or that flips a wire
convention, without correcting the strings reddens here; and a guard that simply asserted
"start_index == 2" would have proved nothing. The disclosure clause is the other half: where
the caller's number and the wire's number are **different numbers for the same place**, the
descriptor must say which is which, in its own printed text.

Run against 1.33.0's ``InsertColsAt`` / ``InsertRowsAt`` this file is RED (no
``position_convention``, no disclosure phrase in ``semantic``, docstrings presenting the wire
convention as the parameter's own).
"""
import pytest

from larkdocio.sheets.write_apply import (
    AppendDimension,
    AppendRowsWithValues,
    DeleteCols,
    DeleteRows,
    InsertColsAt,
    InsertRowsAt,
    MergeCells,
    ReorderTab,
    SetColProperties,
    SetRowProperties,
    UnmergeCells,
    apply,
    dry_run,
)

from test_sheets_structural_apply import FakeStructuralGateway

SID = "461sheet"
TOKEN = "shtxxxLD461"

#: The ONE phrase every string about a caller-facing structural position must carry, per axis.
#: One wording, so "the docstring, the semantic and the guide all say the same thing" is a
#: string equality rather than a reviewer's judgement call.
def _disclosure(axis: str) -> str:
    return f"1-based against displayed {axis} position"


#: wire ``convention`` → the 0-based, half-open span its ``(start_index, end_index)`` names.
_WIRE_SPAN = {
    "0-index-half-open": lambda s, e: (s, e),
    "1-index-inclusive": lambda s, e: (s - 1, e),
}

#: wire ``convention`` → how the span is written in prose (so the guard can check the
#: ``semantic`` line quotes the REAL wire numbers, not a re-told version of them).
_WIRE_SPAN_TEXT = {
    "0-index-half-open": lambda s, e: f"[{s}, {e})",
    "1-index-inclusive": lambda s, e: f"[{s}, {e}]",
}

#: caller-facing ``position_convention`` → the 0-based slot that position names.
_POSITION_SLOT = {
    "1-index-displayed": lambda p: p - 1,
}

#: (request, the caller-facing field whose value the diagnostics quote as the position).
#: Every request family that puts an index on the wire is here — AC3's sweep, executable.
INDEXED = [
    (InsertRowsAt(SID, before_row=1, count=1), "before_row"),
    (InsertRowsAt(SID, before_row=2, count=1), "before_row"),
    (InsertRowsAt(SID, before_row=7, count=3), "before_row"),
    (InsertColsAt(SID, before_col=1, count=1), "before_col"),
    (InsertColsAt(SID, before_col=2, count=1), "before_col"),
    (InsertColsAt(SID, before_col=7, count=3), "before_col"),
    (DeleteRows(SID, first=2, last=3), "first"),
    (DeleteRows(SID, first=1, last=1), "first"),
    (DeleteCols(SID, first=2, last=3), "first"),
    (SetRowProperties(SID, first=2, last=3, fixed_size=60), "first"),
    (SetColProperties(SID, first=2, last=2, fixed_size=200), "first"),
]

_IDS = [f"{r.__class__.__name__}-{getattr(r, f)}" for r, f in INDEXED]

#: The subset whose caller-facing number is NOT the number that goes on the wire — computed
#: from the requests themselves at collection, never listed by hand, so a re-basing moves a
#: request into (or out of) the disclosure requirement automatically.
DISAGREEING = [(r, f) for r, f in INDEXED if getattr(r, f) != r.descriptor()["start_index"]]
_DISAGREE_IDS = [f"{r.__class__.__name__}-{getattr(r, f)}" for r, f in DISAGREEING]


def _axis(desc) -> str:
    return "row" if desc["major_dimension"] == "ROWS" else "column"


# =========================================================================== #
# AC4 — the guard: printed strings vs the index the request really puts out.    #
# =========================================================================== #

@pytest.mark.parametrize("req,field", INDEXED, ids=_IDS)
def test_the_printed_diagnostics_name_the_same_slot_the_wire_does(req, field):
    """Both spans derived; neither written down. This is the assertion the incident needed."""
    desc = req.descriptor()
    wire = _WIRE_SPAN[desc["convention"]](desc["start_index"], desc["end_index"])
    position = getattr(req, field)

    if position == desc["start_index"]:
        # MEASURED NEGATIVE (AC3): the caller's number IS the wire's number — one number,
        # one basis, nothing a reader can mis-attribute. Recorded, not assumed.
        assert desc["convention"].startswith("1-index"), desc
        assert str(position) in desc["semantic"], desc["semantic"]
        return

    # The caller's number and the wire's number are DIFFERENT numbers for the same place.
    # The descriptor must therefore state the caller number's own basis, in its own text.
    assert "position_convention" in desc, (
        f"{type(req).__name__}: the diagnostics quote position {position} while the wire "
        f"carries {desc['start_index']} — with no `position_convention`, the neighbouring "
        f"`convention: {desc['convention']!r}` is the only basis a reader can attach to it, "
        f"and it is the WRONG one (LD-461)."
    )
    assert desc["position"] == position, desc
    slot = _POSITION_SLOT[desc["position_convention"]](desc["position"])
    assert (slot, slot + desc["expected_count"]) == wire, (
        f"{type(req).__name__}: the printed diagnostics say the op lands at 0-based slot "
        f"{slot}, the wire says {wire[0]} — the strings and the payload disagree."
    )


def test_at_least_one_shipped_request_really_does_disagree():
    """Guards the guard: if this list ever empties, the disclosure test below stops asserting
    anything and would go green by vacancy."""
    assert {type(r).__name__ for r, _ in DISAGREEING} == {"InsertRowsAt", "InsertColsAt"}


@pytest.mark.parametrize("req,field", DISAGREEING, ids=_DISAGREE_IDS)
def test_a_disagreeing_position_is_disclosed_in_the_semantic_line_itself(req, field):
    """The ``semantic`` line is the one string a consumer prints. Where the two numbers
    differ it must carry BOTH — the position with its basis named, and the real wire span."""
    desc = req.descriptor()
    semantic = desc["semantic"]
    assert _disclosure(_axis(desc)) in semantic, semantic
    assert field in semantic, semantic
    assert _WIRE_SPAN_TEXT[desc["convention"]](desc["start_index"], desc["end_index"]) in semantic, semantic
    assert desc["convention"] in semantic, semantic


def test_every_indexed_structural_request_is_covered_by_this_guard():
    """A new indexed request that skips this file is the way the defect comes back."""
    from larkdocio.sheets import write_apply as W

    covered = {type(r) for r, _ in INDEXED}
    exempt = {
        AppendDimension,          # appends at the grid END — no position to mis-base
        AppendRowsWithValues,     # ditto (the A1 range is the target, not an index)
    }
    seen = set()
    for name in dir(W):
        obj = getattr(W, name)
        if not isinstance(obj, type) or obj in covered or obj in exempt:
            continue
        if getattr(obj, "write_kind", None) in ("structure",):
            seen.add(obj)
    assert not seen, f"indexed structural requests missing from INDEXED: {seen}"


# =========================================================================== #
# AC1 — the diagnostics agree with the payload that actually goes on the wire.  #
# =========================================================================== #

@pytest.mark.parametrize("before_col", [1, 2, 7])
def test_the_wire_call_lands_where_the_printed_diagnostics_say_it_will(before_col):
    """End to end through the apply seam: the recorded ``insert_dimension_range`` call is
    the ground truth, and the plan's own printed strings are read back against it."""
    gw = FakeStructuralGateway(row_count=10, column_count=8)
    plan = dry_run([InsertColsAt(SID, before_col=before_col, count=1)], gw, TOKEN)
    desc = plan.entries[0].structural
    apply(plan, gw)

    op, _sid, major, start, end = gw.calls[0]
    assert (op, major) == ("insert", "COLUMNS")
    slot = _POSITION_SLOT[desc["position_convention"]](desc["position"])
    assert (start, end) == (slot, slot + 1), (
        f"printed diagnostics point at 0-based slot {slot}; the wire call is [{start}, {end})"
    )
    assert _WIRE_SPAN_TEXT[desc["convention"]](start, end) in desc["semantic"]
    assert _disclosure("column") in desc["semantic"]


# =========================================================================== #
# AC1 / AC3 — the docstrings and the shipped docs say the same thing.           #
# =========================================================================== #

@pytest.mark.parametrize("cls,field,axis", [
    (InsertRowsAt, "before_row", "row"),
    (InsertColsAt, "before_col", "column"),
])
def test_the_insert_docstrings_state_the_parameter_basis_and_label_the_wire_one(cls, field, axis):
    doc = cls.__doc__ or ""
    assert _disclosure(axis) in doc, f"{cls.__name__} docstring omits the parameter's basis"
    assert field in doc
    # Where the docstring names the endpoint's own 0-based convention it must be LABELLED as
    # the wire's — the 1.33.0 text put "(native 0-idx half-open)" straight after the
    # parameter, which is the sentence the consumer read as the parameter's basis.
    for marker in ("0-idx", "0-index"):
        for line in doc.splitlines():
            if marker in line:
                assert "wire" in line, (
                    f"{cls.__name__}: {line.strip()!r} names a 0-based convention without "
                    f"saying it is the WIRE's, not {field}'s"
                )


@pytest.mark.parametrize("path", ["src/larkdocio/GUIDE.md", "SHEETS.md"])
def test_the_shipped_docs_state_the_caller_facing_position_convention(path):
    from pathlib import Path

    text = Path(__file__).resolve().parents[1].joinpath(path).read_text(encoding="utf-8")
    assert "before_col" in text
    assert _disclosure("column") in text, f"{path} never states before_col's own basis"


# =========================================================================== #
# AC3 — the rest of the sweep, as measured negatives rather than assumptions.   #
# =========================================================================== #

def test_the_append_requests_print_no_index_and_so_need_no_basis():
    for req in (AppendDimension(SID, "ROWS", 2),
                AppendRowsWithValues(f"{SID}!A1:B1", [["x", "y"]])):
        desc = req.descriptor()
        assert "start_index" not in desc and "convention" not in desc, desc


def test_the_merge_requests_address_by_a1_range_not_by_a_raw_index():
    for req in (MergeCells(f"{SID}!A1:B2"), UnmergeCells(f"{SID}!A1:B2")):
        desc = req.descriptor()
        assert "start_index" not in desc and "convention" not in desc, desc
        # the only address printed is the A1 range, whose basis is universal
        assert desc["a1_range"] in desc["semantic"]


def test_reorder_tab_already_labels_its_own_zero_based_position():
    """The tab op that DOES print an index labels it — the precedent this fix follows."""
    desc = ReorderTab(SID, index=2).descriptor()
    assert desc["zero_based"] is True and desc["index_is_target_position"] is True
    assert "0-based" in desc["semantic"] and "2" in desc["semantic"]
