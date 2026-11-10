"""Behavioral tests for the table block handler (core/blocks/table.py).

Covers the table-escape-pad hardening fix:
- A '|' inside a cell is escaped to '\\|' so it does not create a spurious
  column boundary in the rendered Markdown row.
- A ragged final row (children count not a multiple of col_size) is padded
  with empty cells up to col_size so the row has the right column count.
"""
from harness import render

from builders import cell as _cell, page, table as _table, text_block as _text


def _root(child_ids):
    return page(*child_ids)


def test_pipe_in_cell_is_escaped():
    blocks = [
        _root(["tbl"]),
        _table("tbl", "root", 2, ["c0", "c1"]),
        _cell("c0", "tbl", ["c0t"]),
        _text("c0t", "c0", "a|b"),
        _cell("c1", "tbl", ["c1t"]),
        _text("c1t", "c1", "x"),
    ]
    out = render(blocks)
    # The literal pipe must be escaped so it does not split into a 3rd column.
    assert r"a\|b" in out
    header_row = [ln for ln in out.splitlines() if ln.startswith("| ")][0]
    # Splitting on UNescaped pipes yields 2 columns (+2 empty edge segments).
    import re
    segments = re.split(r"(?<!\\)\|", header_row)
    cells = [s for s in segments if s.strip()]
    assert len(cells) == 2
    assert r"a\|b" in cells[0]


def test_ragged_final_row_is_padded():
    # col_size = 2 but only 3 cells -> final row has 1 real cell + 1 padded.
    blocks = [
        _root(["tbl"]),
        _table("tbl", "root", 2, ["c0", "c1", "c2"]),
        _cell("c0", "tbl", ["c0t"]),
        _text("c0t", "c0", "A"),
        _cell("c1", "tbl", ["c1t"]),
        _text("c1t", "c1", "B"),
        _cell("c2", "tbl", ["c2t"]),
        _text("c2t", "c2", "C"),
    ]
    out = render(blocks)
    rows = [ln for ln in out.splitlines() if ln.startswith("| ")]
    last = rows[-1]
    # Padded to 2 columns => 3 segments, trailing empty cell.
    assert last.count("|") == 3
    assert last.strip().endswith("|  |") or last.strip().endswith("| |")


# --- Markdown-path multi-line cell joins with <br> (LD-041) ------------------


def test_markdown_cell_joins_multiline_with_br():
    """A no-merge (markdown pipe-table) cell with multi-line content joins its
    internal newlines with ``<br>`` (stacking preserved), not a space run-on.

    Pins LD-041 AC1: `.replace("\\n", " ")` on the markdown path (renderer.py
    :374) became a ``<br>`` join. A cell with two block children carries a
    literal newline between them; it must survive as ``<br>`` inside the single
    table row (the row itself stays one physical line).
    """
    blocks = [
        _root(["tbl"]),
        _table("tbl", "root", 2, ["c0", "c1", "c2", "c3"]),
        _cell("c0", "tbl", ["c0t"]),
        _text("c0t", "c0", "H1"),
        _cell("c1", "tbl", ["c1t"]),
        _text("c1t", "c1", "H2"),
        _cell("c2", "tbl", ["c2a", "c2b"]),
        _text("c2a", "c2", "line1"),
        _text("c2b", "c2", "line2"),
        _cell("c3", "tbl", ["c3t"]),
        _text("c3t", "c3", "b"),
    ]
    out = render(blocks)
    # Newline joined with <br>, not collapsed to a space.
    assert "line1<br>line2" in out
    assert "line1 line2" not in out
    # Still a markdown pipe table (no HTML), and the data row is one physical
    # line (the literal newline did not leak through to break the row).
    assert "<table" not in out
    data_row = [ln for ln in out.splitlines() if "line1<br>line2" in ln][0]
    assert data_row.startswith("| ") and data_row.endswith(" |")
    assert "\nline2" not in data_row


def test_markdown_single_line_cell_unchanged_by_br_join():
    """A single-line markdown cell is byte-identical after the <br> change and
    a literal pipe is still escaped (LD-041 AC1: strip + pipe-escape preserved)."""
    blocks = [
        _root(["tbl"]),
        _table("tbl", "root", 2, ["c0", "c1"]),
        _cell("c0", "tbl", ["c0t"]),
        _text("c0t", "c0", "a|b"),
        _cell("c1", "tbl", ["c1t"]),
        _text("c1t", "c1", "x"),
    ]
    out = render(blocks)
    assert "| a\\|b | x |" in out
    assert "<br>" not in out


# --- Hybrid HTML-on-merge + header_row handling (fix table-merge-html-2) ---


def test_no_merge_table_stays_markdown_byte_identical():
    """A table with no merges must render the exact current Markdown."""
    blocks = [
        _root(["tbl"]),
        _table("tbl", "root", 2, ["c0", "c1", "c2", "c3"]),
        _cell("c0", "tbl", ["c0t"]),
        _text("c0t", "c0", "H1"),
        _cell("c1", "tbl", ["c1t"]),
        _text("c1t", "c1", "H2"),
        _cell("c2", "tbl", ["c2t"]),
        _text("c2t", "c2", "a"),
        _cell("c3", "tbl", ["c3t"]),
        _text("c3t", "c3", "b"),
    ]
    out = render(blocks)
    assert "| H1 | H2 |\n|---|---|\n| a | b |\n\n" in out
    assert "<table" not in out


def test_header_row_false_does_not_promote_first_row():
    """When header_row is False, the first data row must NOT become a header.

    The delimiter still appears (Markdown requires it), but the first row of
    real data stays a data row -> we emit an empty header row above it.
    """
    blocks = [
        _root(["tbl"]),
        _table("tbl", "root", 2, ["c0", "c1", "c2", "c3"],
               extra={"header_row": False}),
        _cell("c0", "tbl", ["c0t"]),
        _text("c0t", "c0", "a"),
        _cell("c1", "tbl", ["c1t"]),
        _text("c1t", "c1", "b"),
        _cell("c2", "tbl", ["c2t"]),
        _text("c2t", "c2", "c"),
        _cell("c3", "tbl", ["c3t"]),
        _text("c3t", "c3", "d"),
    ]
    out = render(blocks)
    rows = [ln for ln in out.splitlines() if ln.startswith("|")]
    # First emitted line is an empty header row (no real data), then delimiter.
    assert rows[0].strip("| ").replace("|", "").strip() == ""
    assert set(rows[1].replace("|", "").strip()) <= {"-"}
    # The real data row 'a | b' appears AFTER the delimiter, not promoted.
    data_lines = [r for r in rows if "a" in r and "b" in r]
    assert data_lines
    assert out.index(data_lines[0]) > out.index(rows[1])


def test_merged_table_emits_valid_html_with_spans_and_th_header():
    """A 2x2 table whose top-left cell spans 2 columns must render HTML with
    colspan=2 and a <th> header row (header_row True)."""
    # merge_info is row-major, parallel to cells. Anchor (0,0) spans 2 cols;
    # the covered cell (0,1) is marked col_span=0 (covered) per Lark convention.
    merge_info = [
        {"row_span": 1, "col_span": 2},  # c0 anchor: spans both columns
        {"row_span": 1, "col_span": 0},  # c1 covered by c0
        {"row_span": 1, "col_span": 1},  # c2 normal
        {"row_span": 1, "col_span": 1},  # c3 normal
    ]
    blocks = [
        _root(["tbl"]),
        _table("tbl", "root", 2, ["c0", "c1", "c2", "c3"],
               extra={"header_row": True, "row_size": 2,
                               "merge_info": merge_info}),
        _cell("c0", "tbl", ["c0t"]),
        _text("c0t", "c0", "Spanning Header"),
        _cell("c1", "tbl", []),
        _cell("c2", "tbl", ["c2t"]),
        _text("c2t", "c2", "a"),
        _cell("c3", "tbl", ["c3t"]),
        _text("c3t", "c3", "b"),
    ]
    out = render(blocks)
    assert "<table" in out
    # Validate it parses as well-formed XML and has the right spans/tags.
    import re
    from xml.etree import ElementTree as ET

    m = re.search(r"<table.*?</table>", out, re.DOTALL)
    assert m, "no <table> block found"
    root = ET.fromstring(m.group(0))
    # The spanning header cell is a <th> with colspan=2.
    ths = root.iter("th")
    span_th = [t for t in ths if t.get("colspan") == "2"]
    assert span_th, "expected a <th colspan=2>"
    assert "Spanning Header" in (span_th[0].text or "")
    # Covered cell must NOT be emitted as its own element in that row.
    thead = root.find("thead")
    assert thead is not None
    header_cells = list(thead.iter("th"))
    assert len(header_cells) == 1
    # Data row uses <td>.
    tds = [t for t in root.iter("td")]
    assert any((t.text or "").strip() == "a" for t in tds)


# --- Net strengthening: kill the table survivors (LD-027 AC2) ----------------
#
# The mutation baseline (dev/mutation-baseline-2026-07-24.md) left table.py at
# 82.4% (36 survivors). Read against `mutmut show`, the *genuinely-killable*
# survivors all sit in the merge-detection predicates + the HTML/merge path,
# which the tests above barely exercise. These pins characterize CURRENT
# behavior (green on develop) and each goes RED under its named survivor — so
# the same guard holds after the family migrates onto the model (the merge/HTML
# logic moves verbatim into the renderer).


def _merge_table(child_ids, merge_info, col_size=2):
    return _table("tbl", "root", col_size, child_ids,
                  extra={"merge_info": merge_info})


def test_table_without_property_renders_markdown_not_html():
    # No `table.property` at all -> _table_prop is None; _has_merges(None) must
    # be False so we stay on the Markdown path. Kills the survivor that flips
    # `if prop is None: return False` -> `return True`.
    blocks = [
        _root(["tbl"]),
        {"block_id": "tbl", "parent_id": "root", "block_type": 31,
         "table": {}, "children": ["c0", "c1"]},
        _cell("c0", "tbl", ["c0t"]), _text("c0t", "c0", "A"),
        _cell("c1", "tbl", ["c1t"]), _text("c1t", "c1", "B"),
    ]
    out = render(blocks)
    assert "<table" not in out
    assert "| A |" in out  # col_size defaults to 1: each cell is its own row


def test_merge_info_all_unit_spans_renders_markdown_not_html():
    # A table that HAS merge_info but where every span is exactly 1 is not a
    # merged table -> Markdown path. Kills the boundary survivors that weaken
    # `rs > 1` / `cs > 1` to `>= 1` (a 1x1 cell would wrongly force the HTML
    # path) and the trailing `return False -> return True`.
    merge_info = [{"row_span": 1, "col_span": 1} for _ in range(4)]
    blocks = [
        _root(["tbl"]), _merge_table(["c0", "c1", "c2", "c3"], merge_info),
        _cell("c0", "tbl", ["c0t"]), _text("c0t", "c0", "H1"),
        _cell("c1", "tbl", ["c1t"]), _text("c1t", "c1", "H2"),
        _cell("c2", "tbl", ["c2t"]), _text("c2t", "c2", "a"),
        _cell("c3", "tbl", ["c3t"]), _text("c3t", "c3", "b"),
    ]
    out = render(blocks)
    assert "<table" not in out
    assert "| H1 | H2 |" in out


def test_merged_cell_content_is_html_escaped():
    # HTML-path cells run through _html_escape: & < > become entities. The
    # merged_table golden has no such chars, so all nine _html_escape survivors
    # (each `&`/`<`/`>` literal and each `&amp;`/`&lt;`/`&gt;` replacement) live
    # until this pins the exact escaping.
    merge_info = [{"row_span": 2, "col_span": 1}, {"row_span": 1, "col_span": 1},
                  {"row_span": 1, "col_span": 1}, {"row_span": 1, "col_span": 1}]
    blocks = [
        _root(["tbl"]), _merge_table(["c0", "c1", "c2", "c3"], merge_info),
        _cell("c0", "tbl", ["c0t"]), _text("c0t", "c0", "a & b < c > d"),
        _cell("c1", "tbl", ["c1t"]), _text("c1t", "c1", "x"),
        _cell("c2", "tbl", ["c2t"]), _text("c2t", "c2", "y"),
        _cell("c3", "tbl", ["c3t"]), _text("c3t", "c3", "z"),
    ]
    out = render(blocks)
    assert "<table" in out
    assert "a &amp; b &lt; c &gt; d" in out
    assert "a & b < c > d" not in out


def test_merged_table_with_fewer_merge_info_than_cells():
    # merge_info shorter than the cell list: cells past its end fall to
    # span_for's (1, 1) fallback. Kills the `idx < len` -> `idx <= len` survivor
    # (which would IndexError) and the `return 1, 1` -> `return 2, 1` / `1, 2`
    # survivors (which would emit a spurious span on the out-of-range cell).
    merge_info = [{"row_span": 2, "col_span": 1}, {"row_span": 1, "col_span": 1},
                  {"row_span": 1, "col_span": 1}]  # only 3 entries for 4 cells
    blocks = [
        _root(["tbl"]), _merge_table(["c0", "c1", "c2", "c3"], merge_info),
        _cell("c0", "tbl", ["c0t"]), _text("c0t", "c0", "Anchor"),
        _cell("c1", "tbl", ["c1t"]), _text("c1t", "c1", "B"),
        _cell("c2", "tbl", ["c2t"]), _text("c2t", "c2", "C"),
        _cell("c3", "tbl", ["c3t"]), _text("c3t", "c3", "D"),
    ]
    out = render(blocks)
    assert "<table" in out
    import re
    m = re.search(r"<td[^>]*>D</td>", out)
    assert m, "out-of-range cell D not rendered as a plain <td>"
    assert "rowspan" not in m.group(0) and "colspan" not in m.group(0)


def test_merged_cell_with_missing_span_fields_emits_no_span_attr():
    # A merge_info entry that omits row_span/col_span -> getattr yields None ->
    # span_for normalizes to (1, 1) -> no rowspan/colspan attr. Kills the
    # `1 if rs is None else rs` -> `2 if ...` survivors (row + col).
    merge_info = [{"row_span": 2, "col_span": 1}, {},
                  {"row_span": 1, "col_span": 1}, {"row_span": 1, "col_span": 1}]
    blocks = [
        _root(["tbl"]), _merge_table(["c0", "c1", "c2", "c3"], merge_info),
        _cell("c0", "tbl", ["c0t"]), _text("c0t", "c0", "Anchor"),
        _cell("c1", "tbl", ["c1t"]), _text("c1t", "c1", "Plain"),
        _cell("c2", "tbl", ["c2t"]), _text("c2t", "c2", "y"),
        _cell("c3", "tbl", ["c3t"]), _text("c3t", "c3", "z"),
    ]
    out = render(blocks)
    assert "<table" in out
    import re
    m = re.search(r"<t[hd][^>]*>Plain</t[hd]>", out)
    assert m, "cell with missing span fields not rendered"
    assert "rowspan" not in m.group(0) and "colspan" not in m.group(0)


def test_covered_cell_does_not_suppress_following_cell():
    # A covered cell (span 0) is `continue`-skipped, not `break`-ed: a real cell
    # after it in the same row must still render. Kills the `continue` -> `break`
    # survivor.
    merge_info = [{"row_span": 1, "col_span": 2}, {"row_span": 1, "col_span": 0},
                  {"row_span": 1, "col_span": 1}]
    blocks = [
        _root(["tbl"]), _merge_table(["c0", "c1", "c2"], merge_info, col_size=3),
        _cell("c0", "tbl", ["c0t"]), _text("c0t", "c0", "Wide"),
        _cell("c1", "tbl", []),  # covered by c0's colspan
        _cell("c2", "tbl", ["c2t"]), _text("c2t", "c2", "After"),
    ]
    out = render(blocks)
    assert "<table" in out
    assert "After" in out


def test_merged_cell_with_two_paragraphs_separates_them_as_real_blocks():
    # WAS `test_merged_cell_flattens_newlines_to_space`, which pinned the old
    # `replace("\n", " ")` collapse — the exact defect LD-144 fixes: a multi-block
    # cell came back as one run-together line ("line1 line2") with no signal
    # anything had been lost. A merged cell's blocks are now REAL HTML blocks
    # (CONSENTED reader-output change, LD-144 AC1/AC5).
    #
    # The no-literal-newline invariant the old collapse existed to protect is
    # STILL pinned below: a blank line terminates a CommonMark HTML block, which
    # would tear the <table> in half, so no cell may contain a raw newline.
    merge_info = [{"row_span": 2, "col_span": 1}, {"row_span": 1, "col_span": 1},
                  {"row_span": 1, "col_span": 1}, {"row_span": 1, "col_span": 1}]
    blocks = [
        _root(["tbl"]), _merge_table(["c0", "c1", "c2", "c3"], merge_info),
        _cell("c0", "tbl", ["c0a", "c0b"]),
        _text("c0a", "c0", "line1"), _text("c0b", "c0", "line2"),
        _cell("c1", "tbl", ["c1t"]), _text("c1t", "c1", "x"),
        _cell("c2", "tbl", ["c2t"]), _text("c2t", "c2", "y"),
        _cell("c3", "tbl", ["c3t"]), _text("c3t", "c3", "z"),
    ]
    out = render(blocks)
    assert "<table" in out
    assert "<p>line1</p><p>line2</p>" in out, out
    assert "line1 line2" not in out, out
    assert "line1\nline2" not in out
    for line in out.splitlines():
        if line.startswith("<t") and "line1" in line:
            assert line.endswith("</th>") or line.endswith("</td>"), line


def test_merged_cell_with_both_rowspan_and_colspan():
    # A cell spanning both rows and columns must carry BOTH attrs. Kills the
    # colspan `attrs += ...` -> `attrs = ...` survivor, which would clobber the
    # already-accumulated rowspan.
    merge_info = [{"row_span": 2, "col_span": 2}, {"row_span": 0, "col_span": 0},
                  {"row_span": 0, "col_span": 0}, {"row_span": 0, "col_span": 0}]
    blocks = [
        _root(["tbl"]), _merge_table(["c0", "c1", "c2", "c3"], merge_info),
        _cell("c0", "tbl", ["c0t"]), _text("c0t", "c0", "Big"),
        _cell("c1", "tbl", []), _cell("c2", "tbl", []), _cell("c3", "tbl", []),
    ]
    out = render(blocks)
    assert "<table" in out
    import re
    m = re.search(r"<th[^>]*>Big</th>", out)
    assert m, "spanning cell not rendered as <th>"
    assert 'rowspan="2"' in m.group(0)
    assert 'colspan="2"' in m.group(0)


# --- LD-050: covered cells are COMPUTED from anchor spans, not read from
# merge_info. Real Lark marks a covered cell (1,1) (NOT span-0), so the covered
# position must be derived from the preceding anchor's rowspan/colspan via an
# occupancy grid. Evidence: the gauntlet 4x4 table, col_size 4 — anchor
# (2,1)@idx6, anchor (1,3)@idx13, covered idx 10/14/15 all read (1,1).
#
# LD-529 replaced ONE corollary of that ruling and nothing else: the covered
# cell's CONTENT no longer goes with its <td>. The layout half below — no cell at
# a covered position, every row exactly col_size wide — is LD-050 verbatim and is
# asserted unchanged. -------------------------------------------------------


def _grid_columns_per_row(table_html: str):
    """Grid columns occupied by each rendered <tr>: the colspans emitted in the
    row PLUS the columns carried in by a rowspan from a row above (which emit no
    cell in this row). This is the standard HTML-table occupancy check — every
    row of a well-formed table occupies the same number of grid columns."""
    import re
    from xml.etree import ElementTree as ET

    m = re.search(r"<table.*?</table>", table_html, re.DOTALL)
    assert m, "no <table> block found"
    root = ET.fromstring(m.group(0))
    carry = 0  # columns still occupied by a rowspan carried in from above
    next_carry = 0
    widths = []
    for tr in list(root.iter("tr")):
        emitted = sum(int(c.get("colspan", 1)) for c in tr)
        widths.append(emitted + carry)
        # Columns this row's cells hand down to the NEXT row via rowspan>1.
        next_carry = sum(int(c.get("colspan", 1))
                         for c in tr if int(c.get("rowspan", 1)) > 1)
        # (test shapes here use rowspan==2, so a carried column lasts one row)
        carry = next_carry
    return widths


def test_covered_cells_computed_from_anchor_spans_not_merge_info():
    """LD-050 regression — the gauntlet 4x4 table shape.

    A 4x4 merged table (col_size 4) where the two anchors are (2,1)@idx6 and
    (1,3)@idx13, and the three covered positions (idx 10/14/15) are marked
    (1,1) in merge_info — EXACTLY as a real Lark payload marks them. Covered
    positions must emit NO cell (occupancy computed from the anchors) and every
    rendered row must occupy exactly 4 grid columns. **That is LD-050's reason and
    LD-050's conclusion, and both are unchanged:** before the occupancy-grid fix
    the covered (1,1) cells emitted phantom <td>s and rows 2/3 gained extra
    columns, and reading a covered cell's own span is still what brings that back.

    **What LD-529 overtook.** This test used to assert the covered cells' content
    was DROPPED — ``"COVERED-10" not in out`` and its two siblings. LD-050 never
    weighed content: its covered-cell text was hand-authored placeholder invented
    for this alignment proof (``tests/_make_fixtures.py``), so dropping the
    content was a side effect of a layout fix, not a ruling about content — and it
    silently ate text and in-cell images alike. So those three assertions are
    INVERTED here: the content must now be present **inside the covering anchor's
    own cell**, absorbed after the anchor's own content. What this test now
    polices is that the layout half survived the content half's replacement.
    """
    # 16 cells, all (1,1) except the two anchors. Covered idx 10/14/15 are (1,1).
    merge_info = [{"row_span": 1, "col_span": 1} for _ in range(16)]
    merge_info[6] = {"row_span": 2, "col_span": 1}   # anchor -> covers (2,2)=idx10
    merge_info[13] = {"row_span": 1, "col_span": 3}  # anchor -> covers idx14,15

    child_ids = [f"c{i}" for i in range(16)]
    blocks = [_root(["tbl"]), _merge_table(child_ids, merge_info, col_size=4)]
    covered = {10, 14, 15}
    for i in range(16):
        cid = f"c{i}"
        tid = f"c{i}t"
        blocks.append(_cell(cid, "tbl", [tid]))
        label = f"COVERED-{i}" if i in covered else f"cell{i}"
        blocks.append(_text(tid, cid, label))

    out = render(blocks)
    assert "<table" in out

    # LD-529 (was: dropped entirely) — covered-cell content is absorbed into the
    # cell of the anchor whose span claims it, row-major, and appears exactly once.
    assert '<td rowspan="2">cell6<br/>COVERED-10</td>' in out, out
    assert '<td colspan="3">cell13<br/>COVERED-14<br/>COVERED-15</td>' in out, out
    for label in ("COVERED-10", "COVERED-14", "COVERED-15"):
        assert out.count(label) == 1, f"{label} appears {out.count(label)}x:\n{out}"

    # Every rendered row occupies exactly col_size (=4) grid columns.
    widths = _grid_columns_per_row(out)
    assert widths == [4, 4, 4, 4], f"row grid-widths not all 4: {widths}"

    # The two anchors carry their spans; no other cell carries a span.
    import re
    from xml.etree import ElementTree as ET
    m = re.search(r"<table.*?</table>", out, re.DOTALL)
    root = ET.fromstring(m.group(0))
    rowspan_cells = [c for c in root.iter() if c.get("rowspan")]
    colspan_cells = [c for c in root.iter() if c.get("colspan")]
    assert [c.get("rowspan") for c in rowspan_cells] == ["2"]
    assert [c.get("colspan") for c in colspan_cells] == ["3"]
