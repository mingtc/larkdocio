"""LD-529 — a merge-covered grid position keeps its CONTENT, not its ``<td>``.

**The defect this module pins.** ``MarkdownRenderer._table_html`` computes merged-table
occupancy from the anchors' spans (LD-050) and emits **no** cell at a covered position.
Emitting no cell also discarded the covered cell's whole subtree, because the content was
only ever reached through the ``<td>`` that was never written — so a merged table silently
lost whatever a covered position held: text, and equally an image, whose token the parser
had *already* queued on ``parser.img_tokens`` so the bytes downloaded and nothing linked
them.

**The rule now.** The rendered content of a covered position is **absorbed into the
``<td>``/``<th>`` of the anchor whose span claims it**, appended after the anchor's own
content, in row-major order of the positions that anchor claims, with no marker wrapping
it. See ``MarkdownRenderer._html_merged_cell`` for the serialization (``<br/>`` when every
contributing cell is phrasing-only, otherwise concatenation with each phrasing piece in a
``<p>``) and ``model/table_occupancy.occupancy`` for which anchor owns which position.

**What LD-050 ruled and what LD-529 replaced.** LD-050's finding stands untouched: real
Lark marks a covered cell ``(1,1)``, not span-0, so coverage must be *computed* from
preceding anchors and the covered cell's own ``merge_info`` ignored — reading it emitted a
phantom ``<td>`` and misaligned every row a rowspan intersected (the gauntlet
4x4 table). So the layout conclusion is re-asserted here, verbatim in substance: **no
cell at a covered position, and every rendered row occupies exactly ``col_size`` grid
columns.** What LD-529 replaced is the one *corollary* LD-050 never weighed — that the
covered cell's content went with its ``<td>``. That was a side effect of a layout fix (its
covered-cell text was hand-authored placeholder invented for the alignment proof), and it
is what this module now polices in the opposite direction.
"""
import json
import re
from xml.etree import ElementTree as ET

import pytest
from builders import cell as _cell, page, table as _table, text_block as _text
from harness import FIXTURES_DIR, render
# The grid-occupancy check is REUSED from the LD-050 guard's own module, never
# forked: the two must agree on what "every row occupies col_size columns" means.
from test_table import _grid_columns_per_row

from larkdocio.model.table_occupancy import covered_positions, occupancy


# --------------------------------------------------------------------------- #
# Shape builders — every cell carries a UNIQUE label, so conservation is        #
# countable in both directions (nothing lost, nothing duplicated).             #
# --------------------------------------------------------------------------- #

def _labelled(merge_info, col_size, n_cells=None, blank=()):
    """A merged table whose cell *i* holds the unique label ``L<i:02d>``.

    ``blank`` names cell indices that hold an EMPTY paragraph instead — the shape
    a real merged table has at a covered position, and the one that must
    contribute absolutely nothing.
    """
    n = n_cells if n_cells is not None else len(merge_info)
    ids = [f"c{i}" for i in range(n)]
    blocks = [page("tbl"),
              _table("tbl", "root", col_size, ids,
                     extra={"merge_info": merge_info, "header_row": False})]
    labels = []
    for i in range(n):
        blocks.append(_cell(f"c{i}", "tbl", [f"c{i}t"]))
        text = "" if i in blank else f"L{i:02d}"
        if text:
            labels.append(text)
        blocks.append(_text(f"c{i}t", f"c{i}", text))
    return blocks, labels


def _m(rs, cs):
    return {"row_span": rs, "col_span": cs}


def _u(n):
    return [_m(1, 1) for _ in range(n)]


#: The gauntlet 4x4 table shape LD-050 was filed on: 4x4, anchor (2,1)@6 and
#: anchor (1,3)@13, every other cell marked (1,1) — including the three covered
#: positions 10/14/15, exactly as a real Lark payload marks them.
_GAUNTLET = _u(16)
_GAUNTLET[6] = _m(2, 1)
_GAUNTLET[13] = _m(1, 3)

#: A covered cell that is ITSELF marked as an anchor — the duplication trap. idx0
#: rowspan-2 claims (1,0)=idx3; idx3's own colspan-2 must be IGNORED (or idx4
#: would vanish) and its content absorbed exactly once.
_COVERED_IS_ANCHOR = _u(6)
_COVERED_IS_ANCHOR[0] = _m(2, 1)
_COVERED_IS_ANCHOR[3] = _m(1, 2)

#: TWO anchors claiming the SAME position — only a malformed payload does this.
#: idx1 rowspan-2 claims (1,1)=idx4; idx3 colspan-3 also reaches (1,1). First
#: claimer in document order owns it, so idx4's content is absorbed ONCE.
_OVERLAPPING_ANCHORS = _u(6)
_OVERLAPPING_ANCHORS[1] = _m(2, 1)
_OVERLAPPING_ANCHORS[3] = _m(1, 3)

#: An anchor whose span runs OFF the grid (rowspan 3 on a 2-row table): it claims
#: positions that hold no cell, which must absorb nothing and crash nothing.
_SPAN_OFF_GRID = _u(4)
_SPAN_OFF_GRID[0] = _m(3, 1)

#: Well-formed shapes: every rendered row must occupy exactly col_size columns.
_WELL_FORMED = [
    pytest.param(_GAUNTLET, 4, id="gauntlet-rowspan-and-colspan"),
    pytest.param([_m(2, 1)] + _u(3), 2, id="rowspan-2"),
    pytest.param([_m(1, 2)] + _u(3), 2, id="colspan-2"),
    pytest.param([_m(2, 2)] + _u(3), 2, id="rowspan-2-colspan-2"),
    pytest.param(_COVERED_IS_ANCHOR, 3, id="covered-cell-is-itself-an-anchor"),
]

#: Every shape, well-formed or not, for the conservation sweep.
_ALL_SHAPES = _WELL_FORMED + [
    pytest.param(_OVERLAPPING_ANCHORS, 3, id="two-anchors-claim-one-position"),
    pytest.param(_SPAN_OFF_GRID, 2, id="anchor-span-runs-off-the-grid"),
]


def _table_markup(out):
    m = re.search(r"<table>.*?</table>", out, re.DOTALL)
    assert m, f"no <table> in:\n{out}"
    return m.group(0)


# --------------------------------------------------------------------------- #
# AC1(a) — LD-050's LAYOUT conclusion is untouched                             #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("merge_info,col_size", _WELL_FORMED)
def test_ac1a_no_cell_is_emitted_at_a_covered_position(merge_info, col_size):
    """LD-050, preserved: a covered position emits NO ``<td>``/``<th>``.

    Counted structurally — the emitted cells are exactly the grid positions that
    are NOT covered — so absorbing the covered content cannot have smuggled a
    phantom cell back in.
    """
    blocks, _ = _labelled(merge_info, col_size)
    out = render(blocks)
    root = ET.fromstring(_table_markup(out))
    emitted = sum(1 for _ in root.iter("td")) + sum(1 for _ in root.iter("th"))
    covered = covered_positions(len(merge_info), [
        (m["row_span"], m["col_span"]) for m in merge_info], col_size)
    assert emitted == len(merge_info) - len(covered)


@pytest.mark.parametrize("merge_info,col_size", _WELL_FORMED)
def test_ac1a_every_row_still_occupies_exactly_col_size_columns(merge_info, col_size):
    """LD-050's other half, preserved: no phantom column comes back."""
    blocks, _ = _labelled(merge_info, col_size)
    widths = _grid_columns_per_row(render(blocks))
    assert widths == [col_size] * len(widths), widths


# --------------------------------------------------------------------------- #
# AC1(b) — the COVERED SET does not move                                       #
# --------------------------------------------------------------------------- #

def test_ac1b_the_gauntlet_covered_set_is_unchanged():
    """The positions treated as covered are the SAME ones as before LD-529 —
    only their content's fate changed. Pinned as literals so a future edit to the
    occupancy walk cannot quietly re-fate a position."""
    spans = [(m["row_span"], m["col_span"]) for m in _GAUNTLET]
    assert covered_positions(16, spans, 4) == {(2, 2), (3, 2), (3, 3)}


def test_ac1b_a_rowspan_shape_covered_set_is_unchanged():
    spans = [(2, 1), (1, 1), (1, 1), (1, 1)]
    assert covered_positions(4, spans, 2) == {(1, 0)}


@pytest.mark.parametrize("merge_info,col_size", _ALL_SHAPES)
def test_ac1b_occupancy_and_covered_positions_agree(merge_info, col_size):
    """``covered_positions`` is a VIEW onto ``occupancy``'s single pass (AC5:
    extended, not forked) — the two can never disagree about coverage."""
    spans = [(m["row_span"], m["col_span"]) for m in merge_info]
    n = len(merge_info)
    assert occupancy(n, spans, col_size)[0] == covered_positions(n, spans, col_size)


# --------------------------------------------------------------------------- #
# AC1(c) — CONSERVATION, both ways: nothing lost, nothing duplicated           #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("merge_info,col_size", _ALL_SHAPES)
def test_ac1c_every_cells_content_appears_exactly_once(merge_info, col_size):
    blocks, labels = _labelled(merge_info, col_size)
    out = render(blocks)
    for label in labels:
        assert out.count(label) == 1, (
            f"{label} appears {out.count(label)}x, expected exactly 1:\n{out}")


@pytest.mark.parametrize("merge_info,col_size", _ALL_SHAPES)
def test_ac1c_the_output_holds_no_content_the_payload_does_not(merge_info, col_size):
    """The other direction: the labels in the output are exactly the payload's."""
    blocks, labels = _labelled(merge_info, col_size)
    out = render(blocks)
    assert sorted(re.findall(r"L\d\d", out)) == sorted(labels)


def test_ac1c_a_covered_cell_that_is_itself_an_anchor_claims_nothing():
    """The duplication trap, spelled out: idx3 is covered by idx0 AND marked
    colspan-2. Its own span must be ignored — so idx4 keeps its own cell — and
    its content absorbed into idx0 exactly once."""
    blocks, _ = _labelled(_COVERED_IS_ANCHOR, 3)
    out = render(blocks)
    assert '<td rowspan="2">L00<br/>L03</td>' in out, out
    assert "<td>L04</td>" in out, out
    assert out.count("L03") == 1
    assert 'colspan' not in out, out


def test_ac1c_two_anchors_claiming_one_position_absorb_it_once():
    """A malformed payload where two spans reach the same position: the FIRST
    anchor in document order owns it, so the content is absorbed once, not twice."""
    blocks, _ = _labelled(_OVERLAPPING_ANCHORS, 3)
    out = render(blocks)
    assert out.count("L04") == 1, out
    assert '<td rowspan="2">L01<br/>L04</td>' in out, out


# --------------------------------------------------------------------------- #
# AC1(d) — an EMPTY covered cell changes NOTHING                               #
# --------------------------------------------------------------------------- #

def test_ac1d_an_empty_covered_cell_contributes_absolutely_nothing():
    """No separator, no whitespace — the anchor's cell is byte-identical to what
    it emitted before LD-529. This is why ``merged_table.expected.md`` and
    ``merged_table_rich_cell.expected.md`` (both have an empty covered cell) do
    not move. How often that shape occurs in real documents is UNMEASURED and is
    not claimed here (see this module's docstring)."""
    blocks, _ = _labelled([_m(2, 1)] + _u(3), 2, blank={2})
    out = render(blocks)
    assert '<td rowspan="2">L00</td>' in out, out
    assert "<br/>" not in out, out


@pytest.mark.parametrize("case", ["merged_table", "merged_table_rich_cell"])
def test_ac1d_the_empty_covered_cell_goldens_are_byte_identical(case):
    """Belt-and-braces beside ``test_golden``: these two committed merged-table
    goldens have empty covered positions and MUST NOT move under LD-529."""
    blocks = json.loads(
        (FIXTURES_DIR / f"{case}.input.json").read_text(encoding="utf-8"))
    expected = (FIXTURES_DIR / f"{case}.expected.md").read_text(encoding="utf-8")
    assert render(blocks) == expected


# --------------------------------------------------------------------------- #
# AC1 — order is row-major and deterministic                                   #
# --------------------------------------------------------------------------- #

def test_absorption_order_is_row_major():
    """A 1x3 anchor claims (0,1) then (0,2): the two absorbed pieces appear in
    grid order, not payload-id order or set order."""
    blocks, _ = _labelled([_m(1, 3)] + _u(5), 3)
    out = render(blocks)
    assert '<td colspan="3">L00<br/>L01<br/>L02</td>' in out, out


@pytest.mark.parametrize("merge_info,col_size", _ALL_SHAPES)
def test_two_renders_of_one_payload_are_byte_identical(merge_info, col_size):
    blocks, _ = _labelled(merge_info, col_size)
    assert render(blocks) == render(blocks)


# --------------------------------------------------------------------------- #
# The serialization, pinned in both of its two cases                            #
# --------------------------------------------------------------------------- #

def test_phrasing_only_pieces_join_with_a_br():
    blocks, _ = _labelled([_m(2, 1)] + _u(3), 2)
    assert '<td rowspan="2">L00<br/>L02</td>' in render(blocks)


def test_a_block_level_piece_forces_the_phrasing_pieces_into_paragraphs():
    """Block markup cannot sit beside bare phrasing content without a wrapper, so
    the join switches to ``<p>``-separated blocks. Here the covered cell holds an
    image, which has no paragraph form of its own."""
    blocks = [
        page("tbl"),
        _table("tbl", "root", 2, ["c0", "c1", "c2", "c3"],
               extra={"merge_info": [_m(1, 2), _m(1, 1), _m(1, 1), _m(1, 1)],
                      "header_row": False}),
        _cell("c0", "tbl", ["c0t"]), _text("c0t", "c0", "Anchor"),
        _cell("c1", "tbl", ["c1i"]),
        {"block_id": "c1i", "parent_id": "c1", "block_type": 27,
         "image": {"token": "TOKEN123", "width": 10, "height": 10}, "children": []},
        _cell("c2", "tbl", ["c2t"]), _text("c2t", "c2", "Variant A"),
        _cell("c3", "tbl", ["c3t"]), _text("c3t", "c3", "Light"),
    ]
    out = render(blocks)
    assert ('<td colspan="2"><p>Anchor</p>'
            '<img src="TOKEN123" alt=""/></td>') in out, out


@pytest.mark.parametrize("merge_info,col_size", _ALL_SHAPES)
def test_no_blank_line_is_ever_emitted_inside_a_cell(merge_info, col_size):
    """The law a merged cell lives under: a blank line TERMINATES the CommonMark
    HTML block and tears the ``<table>`` in half. Absorption may not introduce one."""
    markup = _table_markup(render(_labelled(merge_info, col_size)[0]))
    assert "\n\n" not in markup, markup
