"""Helper run manually to author fixture input JSON files.

Run with --update-golden (or LARKDOCIO_UPDATE_GOLDEN=1) via the golden test to
generate the matching .expected.md. This module only defines the inputs.
"""
import json
from pathlib import Path

FIX = Path(__file__).resolve().parent / "fixtures"


def page(children):
    return {"block_id": "root", "parent_id": "doc", "block_type": 1,
            "page": {"elements": [{"text_run": {"content": "Doc Title"}}]},
            "children": [c["block_id"] for c in children]}


def tr(content, **style):
    e = {"text_run": {"content": content}}
    if style:
        e["text_run"]["text_element_style"] = style
    return e


CASES = {}

# simple_text: page + one paragraph
CASES["simple_text"] = [
    page([{"block_id": "t1"}]),
    {"block_id": "t1", "parent_id": "root", "block_type": 2,
     "text": {"elements": [tr("Hello world")]}},
]

# heading_no_children
CASES["heading_no_children"] = [
    page([{"block_id": "h1"}]),
    {"block_id": "h1", "parent_id": "root", "block_type": 3,
     "heading1": {"elements": [tr("A Heading")]}, "children": []},
]

# bullet list
CASES["bullet"] = [
    page([{"block_id": "b1"}, {"block_id": "b2"}]),
    {"block_id": "b1", "parent_id": "root", "block_type": 12,
     "bullet": {"elements": [tr("First item")]}, "children": []},
    {"block_id": "b2", "parent_id": "root", "block_type": 12,
     "bullet": {"elements": [tr("Second item")]}, "children": []},
]

# ordered list (order computed from preceding siblings)
CASES["ordered"] = [
    page([{"block_id": "o1"}, {"block_id": "o2"}, {"block_id": "o3"}]),
    {"block_id": "o1", "parent_id": "root", "block_type": 13,
     "ordered": {"elements": [tr("One")]}, "children": []},
    {"block_id": "o2", "parent_id": "root", "block_type": 13,
     "ordered": {"elements": [tr("Two")]}, "children": []},
    {"block_id": "o3", "parent_id": "root", "block_type": 13,
     "ordered": {"elements": [tr("Three")]}, "children": []},
]

# divider
CASES["divider"] = [
    page([{"block_id": "d1"}]),
    {"block_id": "d1", "parent_id": "root", "block_type": 22, "divider": {}},
]

# code block with language
CASES["code"] = [
    page([{"block_id": "c1"}]),
    {"block_id": "c1", "parent_id": "root", "block_type": 14,
     "code": {"style": {"language": 49},
              "elements": [tr("print('hi')")]}},
]

# quote (type 15)
CASES["quote"] = [
    page([{"block_id": "q1"}]),
    {"block_id": "q1", "parent_id": "root", "block_type": 15,
     "quote": {"elements": [tr("A quoted line")]}},
]

# simple table 2x2 (header row + body row)
CASES["simple_table"] = [
    page([{"block_id": "tbl"}]),
    {"block_id": "tbl", "parent_id": "root", "block_type": 31,
     "table": {"property": {"row_size": 2, "column_size": 2}},
     "children": ["c00", "c01", "c10", "c11"]},
    {"block_id": "c00", "parent_id": "tbl", "block_type": 32, "table_cell": {},
     "children": ["c00t"]},
    {"block_id": "c00t", "parent_id": "c00", "block_type": 2,
     "text": {"elements": [tr("H1")]}},
    {"block_id": "c01", "parent_id": "tbl", "block_type": 32, "table_cell": {},
     "children": ["c01t"]},
    {"block_id": "c01t", "parent_id": "c01", "block_type": 2,
     "text": {"elements": [tr("H2")]}},
    {"block_id": "c10", "parent_id": "tbl", "block_type": 32, "table_cell": {},
     "children": ["c10t"]},
    {"block_id": "c10t", "parent_id": "c10", "block_type": 2,
     "text": {"elements": [tr("a")]}},
    {"block_id": "c11", "parent_id": "tbl", "block_type": 32, "table_cell": {},
     "children": ["c11t"]},
    {"block_id": "c11t", "parent_id": "c11", "block_type": 2,
     "text": {"elements": [tr("b")]}},
]

# image
CASES["image"] = [
    page([{"block_id": "img"}]),
    {"block_id": "img", "parent_id": "root", "block_type": 27,
     "image": {"token": "boxbTOKEN123", "width": 100, "height": 50}},
]


def _cell(cid, parent_id, content):
    """A table_cell (32) holding a single text (2) child — the shape the live
    docx API returns (verified against the harvested Gauntlet payload)."""
    return [
        {"block_id": cid, "parent_id": parent_id, "block_type": 32,
         "table_cell": {}, "children": [cid + "t"]},
        {"block_id": cid + "t", "parent_id": cid, "block_type": 2,
         "text": {"elements": [tr(content)]}},
    ]


# ---------------------------------------------------------------------------
# Authoring sources for the four fixtures that were previously hand-edited JSON
# with no CASES entry (folds assessment C10). Byte-identical to the committed
# files so no golden changes — they are simply now regenerable from this module.
# ---------------------------------------------------------------------------

# bullet_nested_table: a bullet (12) whose child is a 2x2 table (nesting matrix:
# list x table).
CASES["bullet_nested_table"] = [
    page([{"block_id": "b1"}]),
    {"block_id": "b1", "parent_id": "root", "block_type": 12,
     "bullet": {"elements": [tr("Item with a table")]},
     "children": ["tbl"]},
    {"block_id": "tbl", "parent_id": "b1", "block_type": 31,
     "table": {"property": {"row_size": 2, "column_size": 2}},
     "children": ["c00", "c01", "c10", "c11"]},
    *_cell("c00", "tbl", "H1"),
    *_cell("c01", "tbl", "H2"),
    *_cell("c10", "tbl", "a"),
    *_cell("c11", "tbl", "b"),
]

# callout (19): no text of its own — content lives in child blocks, wrapped as a
# blockquote by the handler.
CASES["callout"] = [
    page([{"block_id": "c1"}]),
    {"block_id": "c1", "parent_id": "root", "block_type": 19,
     "callout": {"emoji_id": "bulb"}, "children": ["t1"]},
    {"block_id": "t1", "parent_id": "c1", "block_type": 2,
     "text": {"elements": [tr("Callout body text")]}},
]

# source_synced (49) with an empty elements list and a text child: the handler
# renders the child (does not drop it).
CASES["source_synced_children"] = [
    page([{"block_id": "s1"}]),
    {"block_id": "s1", "parent_id": "root", "block_type": 49,
     "source_synced": {"elements": []}, "children": ["t1"]},
    {"block_id": "t1", "parent_id": "s1", "block_type": 2,
     "text": {"elements": [tr("Child paragraph content")]}},
]

# todo (17) nesting: a parent task with a nested done child (nesting matrix:
# list x list, plus the done-style branch).
CASES["todo_children"] = [
    page([{"block_id": "t1"}]),
    {"block_id": "t1", "parent_id": "root", "block_type": 17,
     "todo": {"elements": [tr("Parent task")]}, "children": ["t1c1"]},
    {"block_id": "t1c1", "parent_id": "t1", "block_type": 17,
     "todo": {"style": {"done": True}, "elements": [tr("Nested done task")]},
     "children": []},
]


# ===========================================================================
# Corpus expansion (LD-012): every remaining registered block type reachable
# from a document, the nesting matrix, and per-type edge cases. Shapes verified
# against the harvested Gauntlet payload (dev-time one-time live read).
# ===========================================================================

# --- Remaining block types -------------------------------------------------

# all_headings: heading1..heading9 (block types 3..11), each a leaf.
CASES["all_headings"] = [
    page([{"block_id": f"h{n}"} for n in range(1, 10)]),
    *[
        {"block_id": f"h{n}", "parent_id": "root", "block_type": n + 2,
         f"heading{n}": {"elements": [tr(f"Heading {n}")]}, "children": []}
        for n in range(1, 10)
    ],
]

# heading_deep_levels_capped (LD-145): the H7-H9 family in its awkward shapes, so the
# ``######`` cap is pinned as OUTPUT and not only as an assertion. Lark stores levels 1-9
# but CommonMark's ATX marker stops at 6, so every marker below is six ``#`` while the
# parsed tree keeps 7/8/9. Deliberately adversarial: an H7 whose TEXT contains ``#``
# (LD-130 escaping interplay — a mid-line hash is content and is never backslashed), an H8
# that owns a child (the heading serializer's other branch), and an H9 whose text opens
# with its own ``# `` marker (which must not deepen the emitted marker to seven).
CASES["heading_deep_levels_capped"] = [
    page([{"block_id": "d7"}, {"block_id": "d8"}, {"block_id": "d9"}]),
    {"block_id": "d7", "parent_id": "root", "block_type": 9,
     "heading7": {"elements": [tr("C# vs #hashtag")]}, "children": []},
    {"block_id": "d8", "parent_id": "root", "block_type": 10,
     "heading8": {"elements": [tr("Deep section")]}, "children": ["d8c"]},
    {"block_id": "d8c", "parent_id": "d8", "block_type": 2,
     "text": {"elements": [tr("body under a level-8 heading")]}, "children": []},
    {"block_id": "d9", "parent_id": "root", "block_type": 11,
     "heading9": {"elements": [tr("# not a marker")]}, "children": []},
]

# heading_with_children: a heading (type 3) that owns child blocks — exercises
# the child-rendering branch of the heading handler.
CASES["heading_with_children"] = [
    page([{"block_id": "hp"}]),
    {"block_id": "hp", "parent_id": "root", "block_type": 3,
     "heading1": {"elements": [tr("Section")]}, "children": ["hc1"]},
    {"block_id": "hc1", "parent_id": "hp", "block_type": 2,
     "text": {"elements": [tr("Body under heading")]}},
]

# equation block (type 16): fenced $$...$$ (distinct from inline $...$).
CASES["equation_block"] = [
    page([{"block_id": "eq1"}]),
    {"block_id": "eq1", "parent_id": "root", "block_type": 16,
     "equation": {"elements": [{"equation": {"content": "e = mc^2"}}]}},
]

# file attachment (type 23): rendered as a filename line with the token.
CASES["file_attachment"] = [
    page([{"block_id": "f1"}]),
    {"block_id": "f1", "parent_id": "root", "block_type": 23,
     "file": {"token": "Example083a49b9eab9c77d38e0", "name": "sample_logo.svg"}},
]

# view + file attachment (LD-040): the REAL captured payload shape. Lark wraps
# EVERY /file attachment in a type-33 view (view_type=1, sole child = the type-23
# file). Reproduces both live instances from the disposable canary doc
# (sample_logo.svg + test_archive.zip; see gauntlet-run2/). The transparent view
# renders each file by its own handler, so both 📎 markers must appear — before
# LD-040 (type 33 unregistered) these attachments were silently dropped.
CASES["view_file_attachment"] = [
    page([{"block_id": "v1"}, {"block_id": "v2"}]),
    {"block_id": "v1", "parent_id": "root", "block_type": 33,
     "view": {"view_type": 1}, "children": ["vf1"]},
    {"block_id": "vf1", "parent_id": "v1", "block_type": 23,
     "file": {"token": "Example083a49b9eab9c77d38e0", "name": "sample_logo.svg"}},
    {"block_id": "v2", "parent_id": "root", "block_type": 33,
     "view": {"view_type": 1}, "children": ["vf2"]},
    {"block_id": "vf2", "parent_id": "v2", "block_type": 23,
     "file": {"token": "Example910c1a3c7b59e2fff384", "name": "test_archive.zip"}},
]

# grid (type 24) with two grid_column (type 25) children.
CASES["grid_columns"] = [
    page([{"block_id": "g1"}]),
    {"block_id": "g1", "parent_id": "root", "block_type": 24,
     "grid": {"column_size": 2}, "children": ["gc1", "gc2"]},
    {"block_id": "gc1", "parent_id": "g1", "block_type": 25,
     "grid_column": {}, "children": ["gp1"]},
    {"block_id": "gp1", "parent_id": "gc1", "block_type": 2,
     "text": {"elements": [tr("Left column")]}},
    {"block_id": "gc2", "parent_id": "g1", "block_type": 25,
     "grid_column": {}, "children": ["gp2"]},
    {"block_id": "gp2", "parent_id": "gc2", "block_type": 2,
     "text": {"elements": [tr("Right column")]}},
]

# quote_container (type 34): wraps its children as a multi-line blockquote.
CASES["quote_container"] = [
    page([{"block_id": "qc"}]),
    {"block_id": "qc", "parent_id": "root", "block_type": 34,
     "quote_container": {}, "children": ["qp1", "qp2"]},
    {"block_id": "qp1", "parent_id": "qc", "block_type": 2,
     "text": {"elements": [tr("First quoted line")]}},
    {"block_id": "qp2", "parent_id": "qc", "block_type": 2,
     "text": {"elements": [tr("Second quoted line")]}},
]

# mermaid / add_ons (type 40): source stored as JSON in add_ons.record.
CASES["mermaid"] = [
    page([{"block_id": "m1"}]),
    {"block_id": "m1", "parent_id": "root", "block_type": 40,
     "add_ons": {"component_type_id": "blk_640017963d808005a21a6445",
                 "record": "{\"data\": \"graph TD\\n  A --> B\"}"}},
]

# board / whiteboard (type 43): a token surfaced as an image link.
CASES["board"] = [
    page([{"block_id": "bd1"}]),
    {"block_id": "bd1", "parent_id": "root", "block_type": 43,
     "board": {"token": "Examplea9e72fa99efd92d46d89"}},
]

# reference_synced (type 50): content lives in another doc — visible placeholder.
CASES["reference_synced"] = [
    page([{"block_id": "r1"}]),
    {"block_id": "r1", "parent_id": "root", "block_type": 50,
     "reference_synced": {"source_document_id": "docSourceABC",
                          "source_block_id": "blkSource123"}},
]

# merged_table (type 31, HTML path): a 2x2 where the top-left cell spans 2 rows.
# Lark's convention (verified in the harvest): the anchor cell carries the >1
# span; the covered cell is present with a (1,1) span and empty content.
CASES["merged_table"] = [
    page([{"block_id": "mt"}]),
    {"block_id": "mt", "parent_id": "root", "block_type": 31,
     "table": {"property": {"row_size": 2, "column_size": 2,
                            "merge_info": [{"row_span": 2, "col_span": 1},
                                           {"row_span": 1, "col_span": 1},
                                           {"row_span": 1, "col_span": 1},
                                           {"row_span": 1, "col_span": 1}]}},
     "children": ["m00", "m01", "m10", "m11"]},
    *_cell("m00", "mt", "Merged"),
    *_cell("m01", "mt", "Top-right"),
    *_cell("m10", "mt", ""),
    *_cell("m11", "mt", "Bottom-right"),
]

# merged_table_gauntlet (type 31, HTML path, LD-050): the gauntlet 4x4 table
# shape — a 4x4 (col_size 4) grid with TWO anchors and THREE covered
# positions, every covered cell marked (1,1) exactly as the live docx API
# returns them (verified from the harvested gauntlet raw dump: anchor (2,1) at
# idx 6, anchor (1,3) at idx 13; covered idx 10/14/15 all read (1,1) — NOT
# span-0). Coverage is COMPUTED from the anchor spans via an occupancy grid, so
# every covered position emits NO cell and its (1,1) merge_info is ignored;
# every rendered row occupies exactly 4 grid columns. Regression oracle for the
# phantom-column bug (the covered cells' content is dropped, never emitted).
CASES["merged_table_gauntlet"] = [
    page([{"block_id": "gt"}]),
    {"block_id": "gt", "parent_id": "root", "block_type": 31,
     "table": {"property": {
         "row_size": 4, "column_size": 4, "header_row": True,
         "merge_info": [
             {"row_span": 1, "col_span": 1}, {"row_span": 1, "col_span": 1},
             {"row_span": 1, "col_span": 1}, {"row_span": 1, "col_span": 1},
             {"row_span": 1, "col_span": 1}, {"row_span": 1, "col_span": 1},
             {"row_span": 2, "col_span": 1}, {"row_span": 1, "col_span": 1},
             {"row_span": 1, "col_span": 1}, {"row_span": 1, "col_span": 1},
             {"row_span": 1, "col_span": 1}, {"row_span": 1, "col_span": 1},
             {"row_span": 1, "col_span": 1}, {"row_span": 1, "col_span": 3},
             {"row_span": 1, "col_span": 1}, {"row_span": 1, "col_span": 1}]}},
     "children": [f"c{i}" for i in range(16)]},
    *_cell("c0", "gt", "H0"),
    *_cell("c1", "gt", "H1"),
    *_cell("c2", "gt", "H2"),
    *_cell("c3", "gt", "H3"),
    *_cell("c4", "gt", "a"),
    *_cell("c5", "gt", "b"),
    *_cell("c6", "gt", "Tall"),
    *_cell("c7", "gt", "d"),
    *_cell("c8", "gt", "e"),
    *_cell("c9", "gt", "f"),
    *_cell("c10", "gt", "covered-by-Tall"),
    *_cell("c11", "gt", "g"),
    *_cell("c12", "gt", "h"),
    *_cell("c13", "gt", "Wide"),
    *_cell("c14", "gt", "covered-by-Wide-1"),
    *_cell("c15", "gt", "covered-by-Wide-2"),
]

# merged_table_rich_cell (type 31, HTML path, LD-144): the dogfood-round-2 T14
# repro, frozen as a golden. The SAME 2x2 rowspan shape as merged_table, but the
# anchor cell carries every construct the old cell serializer flattened —
#   * a bulleted list, one item with a NESTED bullet under it,
#   * an ordered list right after it (T14: "two lists ran together"),
#   * a paragraph mixing plain text, a bold + HIGHLIGHTED run, and literal
#     `<`/`&` metacharacters (the escaping-interplay case), and
#   * a divider (T14: "a divider became a plain `---` mid-sentence").
# The expected.md is the structure-preserving contract: real <ul>/<ol>/<li> with
# the sub-list nested INSIDE its parent <li>, a real <strong>, real <p>
# separation, a real <hr/> — no Markdown marker anywhere inside the raw-HTML
# <td>, no backslash (LD-130's pin), literal metachars as HTML entities, and
# **no highlight**: colour is consumed-into-model / dropped-at-render (LD-042's
# settled capture-only doctrine), so its ABSENCE here is the doctrine's pin.
CASES["merged_table_rich_cell"] = [
    page([{"block_id": "mt"}]),
    {"block_id": "mt", "parent_id": "root", "block_type": 31,
     "table": {"property": {"row_size": 2, "column_size": 2,
                            "merge_info": [{"row_span": 2, "col_span": 1},
                                           {"row_span": 1, "col_span": 1},
                                           {"row_span": 1, "col_span": 1},
                                           {"row_span": 1, "col_span": 1}]}},
     "children": ["m00", "m01", "m10", "m11"]},
    {"block_id": "m00", "parent_id": "mt", "block_type": 32, "table_cell": {},
     "children": ["rb1", "rb2", "ro1", "ro2", "rp", "rdiv"]},
    {"block_id": "rb1", "parent_id": "m00", "block_type": 12,
     "bullet": {"elements": [tr("Bullet one")]}, "children": ["rb1n"]},
    {"block_id": "rb1n", "parent_id": "rb1", "block_type": 12,
     "bullet": {"elements": [tr("Nested bullet")]}, "children": []},
    {"block_id": "rb2", "parent_id": "m00", "block_type": 12,
     "bullet": {"elements": [tr("Bullet two")]}, "children": []},
    {"block_id": "ro1", "parent_id": "m00", "block_type": 13,
     "ordered": {"elements": [tr("Ordered one")]}, "children": []},
    {"block_id": "ro2", "parent_id": "m00", "block_type": 13,
     "ordered": {"elements": [tr("Ordered two")]}, "children": []},
    {"block_id": "rp", "parent_id": "m00", "block_type": 2,
     "text": {"elements": [tr("A "),
                           tr("bold + highlighted", bold=True, background_color=1),
                           tr(" run <tag> & more")]},
     "children": []},
    {"block_id": "rdiv", "parent_id": "m00", "block_type": 22, "divider": {},
     "children": []},
    *_cell("m01", "mt", "Top-right"),
    *_cell("m10", "mt", ""),
    *_cell("m11", "mt", "Bottom-right"),
]

# --- Nesting matrix (lists x tables x code x quotes x callouts) -------------

# nested_bullets: a bullet whose child is an ordered list (list x list).
CASES["nested_bullets"] = [
    page([{"block_id": "nb1"}]),
    {"block_id": "nb1", "parent_id": "root", "block_type": 12,
     "bullet": {"elements": [tr("Level 1 bullet")]}, "children": ["nb1a", "nb1b"]},
    {"block_id": "nb1a", "parent_id": "nb1", "block_type": 13,
     "ordered": {"elements": [tr("Nested one")]}, "children": []},
    {"block_id": "nb1b", "parent_id": "nb1", "block_type": 13,
     "ordered": {"elements": [tr("Nested two")]}, "children": []},
]

# list_nested_code: a bullet whose child is a code block (list x code).
CASES["list_nested_code"] = [
    page([{"block_id": "lc1"}]),
    {"block_id": "lc1", "parent_id": "root", "block_type": 12,
     "bullet": {"elements": [tr("Item with code")]}, "children": ["lc1c"]},
    {"block_id": "lc1c", "parent_id": "lc1", "block_type": 14,
     "code": {"style": {"language": 49}, "elements": [tr("print('nested')")]}},
]

# list_nested_quote: a bullet whose child is a quote block (list x quote).
CASES["list_nested_quote"] = [
    page([{"block_id": "lq1"}]),
    {"block_id": "lq1", "parent_id": "root", "block_type": 12,
     "bullet": {"elements": [tr("Item with quote")]}, "children": ["lq1q"]},
    {"block_id": "lq1q", "parent_id": "lq1", "block_type": 15,
     "quote": {"elements": [tr("Nested quoted line")]}},
]

# callout_with_list: a callout (type 19) wrapping a bullet list (callout x list).
CASES["callout_with_list"] = [
    page([{"block_id": "cl1"}]),
    {"block_id": "cl1", "parent_id": "root", "block_type": 19,
     "callout": {"emoji_id": "monkey_face"}, "children": ["cl1a", "cl1b"]},
    {"block_id": "cl1a", "parent_id": "cl1", "block_type": 12,
     "bullet": {"elements": [tr("First callout item")]}, "children": []},
    {"block_id": "cl1b", "parent_id": "cl1", "block_type": 12,
     "bullet": {"elements": [tr("Second callout item")]}, "children": []},
]

# --- Per-type edge cases ---------------------------------------------------

# callout_empty_children: a callout with no children renders to nothing (the
# empty-children guard).
CASES["callout_empty_children"] = [
    page([{"block_id": "ce"}]),
    {"block_id": "ce", "parent_id": "root", "block_type": 19,
     "callout": {"emoji_id": "bulb"}, "children": []},
]

# code_no_language: a code block with no style at all (None fields) — the
# language falls back to a bare fence.
CASES["code_no_language"] = [
    page([{"block_id": "cnl"}]),
    {"block_id": "cnl", "parent_id": "root", "block_type": 14,
     "code": {"elements": [tr("plain code")]}},
]

# code_unknown_language: a language id not in the DOCX->MD map falls back to "".
CASES["code_unknown_language"] = [
    page([{"block_id": "cul"}]),
    {"block_id": "cul", "parent_id": "root", "block_type": 14,
     "code": {"style": {"language": 999}, "elements": [tr("mystery lang")]}},
]

# code_with_backticks: code content containing triple backticks (fence-hostile
# content pinned as-is).
CASES["code_with_backticks"] = [
    page([{"block_id": "cbt"}]),
    {"block_id": "cbt", "parent_id": "root", "block_type": 14,
     "code": {"style": {"language": 39},
              "elements": [tr("inline ``` and a ` tick")]}},
]

# code_indented_first_line (LD-146 / dogfood round-2 finding T9): the exact repro shape
# — a fence whose FIRST line is indented, with later lines indented deeper — pinned as
# OUTPUT so the verbatim guarantee is a golden and not only an assertion. The reader used
# to `.strip()` the whole joined body, which clipped the first line's indent while every
# later line kept its own; here the first line's four spaces, the deeper interior indents,
# a whitespace-only interior line, a TAB-indented line (tabs vs spaces in one body), and
# the last line's TRAILING whitespace must all survive byte-for-byte. The `# comment` line
# also guards that LD-130's structural escaping never reaches code content.
CASES["code_indented_first_line"] = [
    page([{"block_id": "cif"}]),
    {"block_id": "cif", "parent_id": "root", "block_type": 14,
     "code": {"style": {"language": 49},
              "elements": [tr("    def f():\n"
                              "        # an indented comment, not a heading\n"
                              "        return 1\n"
                              "    \n"
                              "\tresult = f()   ")]}},
]

# code_with_url: a code fence whose content contains bare http(s) URLs. Guards
# LD-054 AC2 — code-fence content is VERBATIM: the always-on bare-URL linkify
# MUST NOT rewrite a URL inside a ``` fence to [url](url) (would corrupt e.g. a
# curl/pip example). No style -> bare fence (the shape a real code block takes).
CASES["code_with_url"] = [
    page([{"block_id": "cwu"}]),
    {"block_id": "cwu", "parent_id": "root", "block_type": 14,
     "code": {"elements": [tr(
         "curl https://api.example.com/v1\n"
         "pip install foo  # see https://pypi.org/project/foo/")]}},
]

# image_no_token: an image block missing its token — emits a visible marker.
CASES["image_no_token"] = [
    page([{"block_id": "imt"}]),
    {"block_id": "imt", "parent_id": "root", "block_type": 27,
     "image": {"width": 100, "height": 50}},
]


# ===========================================================================
# LD-033 (R-S0 net) — deep-nesting / indent gauntlet.
#
# The pre-round nesting matrix was one-fixture-thin (test_nested_block_indent.py
# pinned only bullet_nested_table). These byte-locked goldens are the oracle the
# child-carriage flip (R-S1..R-S5) is proven against: they exercise the indent
# tab semantics — WHO indents (only list types 12/13/17), WHO recurses at what
# depth, and the tab-on-block-child invariant (a block-level child under a list
# item renders at column 0, never tab-indented, so it is not corrupted into a
# CommonMark indented-code block) — at nesting depth >= 3 and across every
# container family. Any depth-off-by-one or tab regression in the flip surfaces
# as a diff here. Byte-locked at creation; NO reader change produces them.
# ===========================================================================

# deep_list_nesting: bullet -> bullet -> bullet, 3 levels (list x list x list).
# Pins the tab deepening: L1 at col 0, L2 one tab, L3 two tabs.
CASES["deep_list_nesting"] = [
    page([{"block_id": "d1"}]),
    {"block_id": "d1", "parent_id": "root", "block_type": 12,
     "bullet": {"elements": [tr("Level 1")]}, "children": ["d2"]},
    {"block_id": "d2", "parent_id": "d1", "block_type": 12,
     "bullet": {"elements": [tr("Level 2")]}, "children": ["d3"]},
    {"block_id": "d3", "parent_id": "d2", "block_type": 12,
     "bullet": {"elements": [tr("Level 3")]}, "children": []},
]

# list_under_heading: a heading (3) whose children are a bullet list, one item of
# which nests a deeper bullet. Headings recurse children at depth 0, so the outer
# bullets sit at col 0 and the nested one gets one tab.
CASES["list_under_heading"] = [
    page([{"block_id": "lh1"}]),
    {"block_id": "lh1", "parent_id": "root", "block_type": 3,
     "heading1": {"elements": [tr("Section")]}, "children": ["lhi1", "lhi2"]},
    {"block_id": "lhi1", "parent_id": "lh1", "block_type": 12,
     "bullet": {"elements": [tr("First")]}, "children": ["lhi1a"]},
    {"block_id": "lhi1a", "parent_id": "lhi1", "block_type": 12,
     "bullet": {"elements": [tr("First nested")]}, "children": []},
    {"block_id": "lhi2", "parent_id": "lh1", "block_type": 12,
     "bullet": {"elements": [tr("Second")]}, "children": []},
]

# deep_callout_list: callout (19) -> bullet -> bullet (callout x list x list).
# The callout prefixes EVERY line with "> ", including the tab-indented nested
# list line — pinning that the blockquote wrap survives nested-list indentation.
CASES["deep_callout_list"] = [
    page([{"block_id": "co1"}]),
    {"block_id": "co1", "parent_id": "root", "block_type": 19,
     "callout": {"emoji_id": "bulb"}, "children": ["cb1", "cb2"]},
    {"block_id": "cb1", "parent_id": "co1", "block_type": 12,
     "bullet": {"elements": [tr("Outer bullet")]}, "children": ["cb1a"]},
    {"block_id": "cb1a", "parent_id": "cb1", "block_type": 12,
     "bullet": {"elements": [tr("Nested bullet")]}, "children": []},
    {"block_id": "cb2", "parent_id": "co1", "block_type": 12,
     "bullet": {"elements": [tr("Second outer")]}, "children": []},
]

# block_child_under_deep_list: bullet -> bullet whose children are a CODE block
# and a QUOTE block (the tab-on-block-child invariant, pinned deep). The list
# ancestors are indented, but a block-level (non-list) child renders at column 0
# with NO tab — tab-indenting a code fence would corrupt it into an indented
# code block.
CASES["block_child_under_deep_list"] = [
    page([{"block_id": "bl1"}]),
    {"block_id": "bl1", "parent_id": "root", "block_type": 12,
     "bullet": {"elements": [tr("Top item")]}, "children": ["bl2"]},
    {"block_id": "bl2", "parent_id": "bl1", "block_type": 12,
     "bullet": {"elements": [tr("Nested item")]}, "children": ["blc", "blq"]},
    {"block_id": "blc", "parent_id": "bl2", "block_type": 14,
     "code": {"style": {"language": 49}, "elements": [tr("deep_code()")]}},
    {"block_id": "blq", "parent_id": "bl2", "block_type": 15,
     "quote": {"elements": [tr("deep quote")]}},
]

# ordered_run_reset_nested: an ordered run under a bullet parent, interrupted by
# a non-ordered (text) sibling that RESETS the ordinal. Ordinals: 1, 2, (text),
# 1, 2. The text interruption is a block-level child -> renders at col 0 (no tab)
# while the ordered items carry the parent's one tab.
CASES["ordered_run_reset_nested"] = [
    page([{"block_id": "orn"}]),
    {"block_id": "orn", "parent_id": "root", "block_type": 12,
     "bullet": {"elements": [tr("Parent")]},
     "children": ["oa", "ob", "sep", "oc", "od"]},
    {"block_id": "oa", "parent_id": "orn", "block_type": 13,
     "ordered": {"elements": [tr("one")]}, "children": []},
    {"block_id": "ob", "parent_id": "orn", "block_type": 13,
     "ordered": {"elements": [tr("two")]}, "children": []},
    {"block_id": "sep", "parent_id": "orn", "block_type": 2,
     "text": {"elements": [tr("interruption")]}, "children": []},
    {"block_id": "oc", "parent_id": "orn", "block_type": 13,
     "ordered": {"elements": [tr("reset one")]}, "children": []},
    {"block_id": "od", "parent_id": "orn", "block_type": 13,
     "ordered": {"elements": [tr("reset two")]}, "children": []},
]

# deep_gauntlet: bullet -> ordered -> bullet (3 list levels), the inner list item
# carrying a TABLE, a CODE block, and a QUOTE (lists x table x code x quote, all
# nested >= 3 deep). The list markers deepen by one tab each; the block-level
# children (table/code/quote) render at column 0 regardless of ancestor depth.
CASES["deep_gauntlet"] = [
    page([{"block_id": "g1"}]),
    {"block_id": "g1", "parent_id": "root", "block_type": 12,
     "bullet": {"elements": [tr("Outer list")]}, "children": ["g2"]},
    {"block_id": "g2", "parent_id": "g1", "block_type": 13,
     "ordered": {"elements": [tr("Middle ordered")]}, "children": ["g3"]},
    {"block_id": "g3", "parent_id": "g2", "block_type": 12,
     "bullet": {"elements": [tr("Inner list")]},
     "children": ["gtbl", "gcode", "gquote"]},
    {"block_id": "gtbl", "parent_id": "g3", "block_type": 31,
     "table": {"property": {"row_size": 2, "column_size": 2}},
     "children": ["gc00", "gc01", "gc10", "gc11"]},
    *_cell("gc00", "gtbl", "H1"),
    *_cell("gc01", "gtbl", "H2"),
    *_cell("gc10", "gtbl", "a"),
    *_cell("gc11", "gtbl", "b"),
    {"block_id": "gcode", "parent_id": "g3", "block_type": 14,
     "code": {"style": {"language": 49}, "elements": [tr("inner()")]}},
    {"block_id": "gquote", "parent_id": "g3", "block_type": 15,
     "quote": {"elements": [tr("inner quote")]}},
]


# ===========================================================================
# LD-041 — markdown pipe-table cell joins multi-line content with <br>.
#
# A pipe-table cell cannot hold a literal newline (it would break the row), so
# multi-line cell content is joined with <br> (GitHub-style renderers stack the
# lines) instead of being collapsed to a run-on space line. This fixture pins the
# ≥5-level-nested-list-in-a-cell case (LD-041 AC2): the markers (-, tab indent)
# stay intact, the five levels stack via <br>, and the table stays ONE physical
# row. Markdown (no-merge) path only — the HTML/merge path is out of scope.
# ===========================================================================
CASES["table_cell_multiline_list"] = [
    page([{"block_id": "tbl"}]),
    {"block_id": "tbl", "parent_id": "root", "block_type": 31,
     "table": {"property": {"row_size": 2, "column_size": 2}},
     "children": ["c00", "c01", "c10", "c11"]},
    *_cell("c00", "tbl", "Structure"),
    *_cell("c01", "tbl", "Note"),
    # c10: a 5-level nested bullet list living inside a single markdown cell.
    {"block_id": "c10", "parent_id": "tbl", "block_type": 32, "table_cell": {},
     "children": ["l1"]},
    {"block_id": "l1", "parent_id": "c10", "block_type": 12,
     "bullet": {"elements": [tr("Level 1")]}, "children": ["l2"]},
    {"block_id": "l2", "parent_id": "l1", "block_type": 12,
     "bullet": {"elements": [tr("Level 2")]}, "children": ["l3"]},
    {"block_id": "l3", "parent_id": "l2", "block_type": 12,
     "bullet": {"elements": [tr("Level 3")]}, "children": ["l4"]},
    {"block_id": "l4", "parent_id": "l3", "block_type": 12,
     "bullet": {"elements": [tr("Level 4")]}, "children": ["l5"]},
    {"block_id": "l5", "parent_id": "l4", "block_type": 12,
     "bullet": {"elements": [tr("Level 5")]}, "children": []},
    *_cell("c11", "tbl", "one row, markers intact"),
]


# ===========================================================================
# LD-044 (T3 / the read-completeness spec § S0) — the block-zoo LIVE-evidenced new shapes.
#
# Authored from the TWO preserved zoo --dump passes (session scratchpad
# zoo-run/ = pass 1, zoo-run2/ = pass 2; document token DocBlockZooExample000000001)
# — the survey is dev/zoo-survey-2026-07-25.md. Each fixture reproduces the REAL
# payload SHAPE the live docx API returned for a type T3 must give a disposition.
#
# AC2 discipline — these goldens capture the pre-handler output for each type:
#   * 18/26/30/44-47/53/999 are UNREGISTERED, so the parser warns for each. Since
#     LD-045 (Decision e) the unknown-type fallback renders an unknown block's
#     CHILDREN transparently, so a LEAF unknown (18/26/30/53/999) still emits
#     nothing, while the agenda CONTAINER (44) now surfaces its descendant body
#     text (its type-46 titles live in `elements`, not children, so they await
#     S2/LD-046's dedicated handler). The S1-S4 handler stories UPDATE these
#     goldens deliberately (that diff is the spec record).
#   * 49 source_synced + 27 image are ALREADY handled — those goldens are
#     byte-identical to current output (real rendered content).
# ===========================================================================

# agenda subtree (44/45/46/47) — pass-2. A type-44 agenda wraps two agenda_items
# (45); each item holds a title (46, its text in its OWN `elements`) and a
# content wrapper (47) holding body text blocks. Reproduces the pass-2 subtree:
# item 1's 47 has a non-empty body ("Agenda body text - level 1") + a trailing
# empty paragraph; item 2's 46 carries the descriptive title. Since S2/LD-046 the
# agenda family is REGISTERED (44/45/47 transparent structural wrappers + a real
# 46 title handler reading `elements`), so the golden surfaces BOTH titles and the
# body text, with ZERO `Unknown block type` warnings — agenda no longer rides the
# S1 unknown-type fallback (Decision d + e's design ruling: a known type keeps its
# handler so the fallback warn stays meaningful). `align` on the titles is dropped.
CASES["agenda"] = [
    page([{"block_id": "ag"}]),
    {"block_id": "ag", "parent_id": "root", "block_type": 44,
     "agenda": {}, "children": ["ai1", "ai2"]},
    # --- item 1 ---
    {"block_id": "ai1", "parent_id": "ag", "block_type": 45,
     "agenda_item": {}, "children": ["ai1t", "ai1c"]},
    {"block_id": "ai1t", "parent_id": "ai1", "block_type": 46,
     "agenda_item_title": {"elements": [tr("Agenda title 1")], "align": 1}},
    {"block_id": "ai1c", "parent_id": "ai1", "block_type": 47,
     "agenda_item_content": {}, "children": ["ai1b1", "ai1b2"]},
    {"block_id": "ai1b1", "parent_id": "ai1c", "block_type": 2,
     "text": {"elements": [tr("Agenda body text - level 1")]}},
    {"block_id": "ai1b2", "parent_id": "ai1c", "block_type": 2,
     "text": {"elements": [tr("")]}},
    # --- item 2 ---
    {"block_id": "ai2", "parent_id": "ag", "block_type": 45,
     "agenda_item": {}, "children": ["ai2t", "ai2c"]},
    {"block_id": "ai2t", "parent_id": "ai2", "block_type": 46,
     "agenda_item_title": {
         "elements": [tr("Agenda topic 1 — self-referential sample")],
         "align": 1}},
    {"block_id": "ai2c", "parent_id": "ai2", "block_type": 47,
     "agenda_item_content": {}, "children": ["ai2b1"]},
    {"block_id": "ai2b1", "parent_id": "ai2c", "block_type": 2,
     "text": {"elements": [tr("")]}},
]

# iframe (26) — pass-2, BOTH instances. The URL lives in
# `iframe.component.url` and is PERCENT-ENCODED (`https%3A%2F%2F...`) — S1 must
# `unquote` it before emitting a link. Two real iframe_type values: 15 (a
# YouTube embed) and 99 (a github web-preview card). Unregistered today →
# warn + drop; golden is the empty body.
CASES["iframe"] = [
    page([{"block_id": "if1"}, {"block_id": "if2"}]),
    {"block_id": "if1", "parent_id": "root", "block_type": 26,
     "iframe": {"component": {
         "iframe_type": 15,
         "url": "https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3DdQw4w9WgXcQ"}}},
    {"block_id": "if2", "parent_id": "root", "block_type": 26,
     "iframe": {"component": {
         "iframe_type": 99,
         "url": "https%3A%2F%2Fwww.github.com%2F"}}},
]

# source_synced (49) with its OWN inline `elements` AND children including a
# type-27 image — pass-2 (the first LIVE source_synced specimen). Type 49 is
# ALREADY handled (synced.py): the handler renders its own elements then descends
# into children, so this golden is byte-identical to CURRENT output (a real
# rendered block, not a warn+drop). The image (token Exampl...) renders as an
# `![](token)` link — proving the 27-image child inside a 49 is not dropped.
CASES["source_synced_image"] = [
    page([{"block_id": "ss"}]),
    {"block_id": "ss", "parent_id": "root", "block_type": 49,
     "source_synced": {"elements": [tr("Synced Block")], "align": 1},
     "children": ["ssb1", "ssimg", "ssb2"]},
    {"block_id": "ssb1", "parent_id": "ss", "block_type": 2,
     "text": {"elements": [tr(
         "This block is synced only here, and it originates here.  \n\n"
         "It contains an image below:\n")]}},
    {"block_id": "ssimg", "parent_id": "ss", "block_type": 27,
     "image": {"token": "Example24439c80879eeace5bf8",
               "width": 363, "height": 366}},
    {"block_id": "ssb2", "parent_id": "ss", "block_type": 2,
     "text": {"elements": [tr("")]}},
]

# bitable (18) — pass-1 dump ONLY (the sole live type-18 specimen: switching the
# embedded base to a named view converts it to a type-53 reference_base, so the
# CURRENT zoo has no live 18). Payload is `{token, view_type}` with view_type
# null. Since LD-048: placeholder → a 📊 traceable marker naming the block +
# token (golden = the marker line).
#
# LD-250 RE-LABELS this case: its token is a HUSK and must not be cited as evidence of live
# type-18 behaviour. The `_note` below travels IN the JSON (the SDK deserializer drops unknown
# block keys, so it cannot move the golden) because a reader who opens the fixture is exactly
# the reader who needs to know. The case is KEPT rather than retired — the husk is a real,
# reachable state and this golden pins the placeholder a stale embed still renders.
_HUSK_NOTE = (
    "RE-LABELLED, NOT LIVE EVIDENCE (LD-250, AC8). This token is a HUSK: the app "
    "Example3... answers GET /tables with {\"items\": []} — no total, no page_token, no "
    "has_more (dev/base-study/captures/02-bitable18-tables.json) — and its tail is a real "
    "1254041 TableIdNotFound (02-bitable18-fields.json). It is a snapshot taken BEFORE the "
    "block-zoo author converted that block: the live zoo doc now contains no type-18 block at "
    "all (p0-1-01-blockzoo-live-embed-blocks.json). So it must NOT be cited as evidence of how "
    "a type-18 embed behaves — a freshly docx-born one bridges end to end "
    "(p0-1-05-fresh-embed-bridge.json, and the bitable_fresh_embed case below is the Base-era "
    "specimen seeded from it). The fixture is KEPT because the husk is a real, reachable state "
    "and this golden pins the placeholder a stale embed still renders. The `_note` key is "
    "dropped by the SDK deserializer, so it costs the golden nothing."
)

CASES["bitable"] = [
    page([{"block_id": "bt"}]),
    {"_note": _HUSK_NOTE,
     "block_id": "bt", "parent_id": "root", "block_type": 18,
     "bitable": {"token": "Example3b5902b83520533e4650_tblGgEHCSGMXEKQs",
                 "view_type": None}},
]

# bitable_fresh_embed (18) — THE BASE-ERA SPECIMEN (LD-250, AC8). Same block type, same
# DEFAULT rendering (the placeholder — deep-read is off unless a consumer opts in), but the
# token is the one a FRESHLY docx-born embedded Base carried in
# tests/captures/base-study/captures/p0-1-05-fresh-embed-bridge.json, where every leg of the bridge
# answered code:0 (app -> tables(1) -> fields(3) -> records/search(3)). The deep read itself is
# exercised against those captures in tests/test_embedded_base_deep_read.py; this case exists so
# the default path is pinned on a token that is NOT a husk.
CASES["bitable_fresh_embed"] = [
    page([{"block_id": "bt"}]),
    {"_note": (
        "THE BASE-ERA type-18 specimen (LD-250, AC8). Its compound token is the one a FRESHLY "
        "docx-born embedded Base carried in dev/base-study/captures/"
        "p0-1-05-fresh-embed-bridge.json, where every leg of the bridge answered code:0 (app -> "
        "tables(1) -> fields(3) -> records/search(3)). This fixture pins the DEFAULT path only: "
        "deep-read is off, so the reader emits the same traceable placeholder it emits for any "
        "embed. The deep read itself is exercised against the captures in "
        "tests/test_embedded_base_deep_read.py. The `_note` key is dropped by the SDK "
        "deserializer, so it costs the golden nothing."),
     "block_id": "bt", "parent_id": "root", "block_type": 18,
     "bitable": {"token": "Examplec8af798413375ff9bc09_tbloLtUSiQNhlkYX",
                 "view_type": None}},
]

# sheet (30) — pass-2. Payload is `{token, row_size, column_size}` with BOTH
# dims null (so the placeholder marker is token-only). Since LD-048: placeholder →
# a 📊 token-only traceable marker (golden = the marker line).
CASES["sheet"] = [
    page([{"block_id": "sh"}]),
    {"block_id": "sh", "parent_id": "root", "block_type": 30,
     "sheet": {"token": "Example38428307171a2bd44d36_EQlPwA",
               "row_size": None, "column_size": None}},
]

# reference_base (53) — pass-2. A NEW SDK type (off the 1-52 matrix), the
# "named-view" form of an embedded base — distinct from 18; consumers hit both
# interchangeably. Payload is `{token, view_id, layout_mode}`. Since LD-048:
# placeholder → a 📊 traceable marker naming the block + token + view_id (golden =
# the marker line). Was unregistered (the forward-compat warn correctly caught it).
CASES["reference_base"] = [
    page([{"block_id": "rb"}]),
    {"block_id": "rb", "parent_id": "root", "block_type": 53,
     "reference_base": {"token": "Examplef5d787ae62ccf194cb22_tbloRVXCoxKjVR5A",
                        "view_id": "vewFZRvtbd", "layout_mode": "Normal"}},
]

# undefined / 999 (empty) — the API fallback sentinel. Arrives as `{"undefined":
# {}}` (a leaf, no children) — the scope-gated redaction of an embed/link/task
# original. Stays a warn by design (forward-compat sentinel); golden is the
# empty body.
CASES["undefined_999"] = [
    page([{"block_id": "u9"}]),
    {"block_id": "u9", "parent_id": "root", "block_type": 999,
     "undefined": {}},
]


# ===========================================================================
# LD-054 — auto-linkify bare URLs (ALWAYS ON, no knob; maintainer-directed permanent
# consented output change). This is the DELIBERATE bare-URL golden of AC4: bare
# http(s) URLs in plain/styled text render as [url](url), while the four
# guardrails hold in one fixture —
#   * p1  bare URL in a plain run                    → linkified;
#   * p2  URL ending a sentence (trailing '.')       → the '.' stays OUTSIDE;
#   * p3  URL inside parens, then ','                → ')' and ',' stay outside;
#   * p4  URL inside INLINE CODE                     → verbatim, NOT linkified;
#   * p5  a run already carrying a .link             → NOT double-linked;
#   * p6  mention_doc output ([title](url))          → NOT double-linked.
# Every other golden is byte-identical (no other fixture carries a bare URL).
# ===========================================================================
CASES["autolink_bare_urls"] = [
    page([{"block_id": "p1"}, {"block_id": "p2"}, {"block_id": "p3"},
          {"block_id": "p4"}, {"block_id": "p5"}, {"block_id": "p6"}]),
    {"block_id": "p1", "parent_id": "root", "block_type": 2,
     "text": {"elements": [tr("Design file: https://www.figma.com/design/ExampleKey1")]}},
    {"block_id": "p2", "parent_id": "root", "block_type": 2,
     "text": {"elements": [tr("See the spec at https://example.com/spec.")]}},
    {"block_id": "p3", "parent_id": "root", "block_type": 2,
     "text": {"elements": [tr("Reference (https://example.com/a), then more.")]}},
    {"block_id": "p4", "parent_id": "root", "block_type": 2,
     "text": {"elements": [tr("Run this: "),
                           tr("https://example.com/raw?a=1", inline_code=True)]}},
    {"block_id": "p5", "parent_id": "root", "block_type": 2,
     "text": {"elements": [tr("Link to Google", link={"url": "http://www.google.com"})]}},
    {"block_id": "p6", "parent_id": "root", "block_type": 2,
     "text": {"elements": [{"mention_doc": {
         "title": "Example Document",
         "url": "https://your-domain.larksuite.com/wiki/WikiPageExample000000000001"}}]}},
]


# ===========================================================================
# LD-095 — golden-set gap expansion. The migration-file edge cases that render to
# a DETERMINISTIC document output, additively golden-pinned so the byte-identity
# net (not just the handler-unit assertions) covers them. Every existing golden is
# ZERO-DRIFT — these are ADD-ONLY. Each case mirrors an edge documented by a kept
# migration test (test_{pilot,text,table,container,media_file_diagram,page_parser}
# _migration.py); the per-family feasible/infeasible disposition lives in the
# LD-095 issue body. NOT-goldenable families (side-effect token queues, the
# headless DocumentNode fallback, the RawBlock/no-string-arm renderer probes, log-
# warning assertions, unreachable defensive guards) stay as those unit tests.
# ===========================================================================

# -- degenerate / absent-attr inputs (render to empty / a bare marker) -------

# text_absent_attr: a type-2 block with NO `text` attr -> content None -> ""
# (test_text_migration.test_text_handler_absent_text_attr_maps_to_none_content).
CASES["text_absent_attr"] = [
    page([{"block_id": "t"}]),
    {"block_id": "t", "parent_id": "root", "block_type": 2},
]

# text_empty_elements: a type-2 block with a PRESENT-but-empty elements list ->
# content [] -> a bare "\n" line (distinct from the absent-attr "" above; pins the
# None-vs-[] boundary — test_text_handler_present_but_empty_maps_to_empty_list).
CASES["text_empty_elements"] = [
    page([{"block_id": "t"}]),
    {"block_id": "t", "parent_id": "root", "block_type": 2, "text": {"elements": []}},
]

# quote_absent_attr: a type-15 block with NO `quote` attr -> QuoteNode([]) -> ""
# (test_pilot_migration.test_quote_handler_missing_quote_attr_returns_empty_node).
CASES["quote_absent_attr"] = [
    page([{"block_id": "q"}]),
    {"block_id": "q", "parent_id": "root", "block_type": 15},
]

# heading_absent_attr: a type-3 heading with NO heading1 attr -> content None ->
# the renderer emits a bare "# " (dangling prefix, no content — the legacy shape;
# test_pilot_migration.test_heading_absent_attr_maps_to_none_content).
CASES["heading_absent_attr"] = [
    page([{"block_id": "h"}]),
    {"block_id": "h", "parent_id": "root", "block_type": 3, "children": []},
]

# image_absent_payload: a type-27 block with the `image` payload entirely absent
# -> caption sentinel None -> "" (distinct from image_no_token, which has an
# image:{} and emits the "[Image: missing token]" marker; test_media_file_diagram
# _migration.test_image_handler_absent_image_returns_empty_node).
CASES["image_absent_payload"] = [
    page([{"block_id": "i"}]),
    {"block_id": "i", "parent_id": "root", "block_type": 27},
]

# board_no_token: a type-43 board with a present-but-tokenless payload ->
# BoardNode() -> "" (test_media_file_diagram_migration
# .test_board_handler_no_token_returns_empty_node_and_queues_nothing).
CASES["board_no_token"] = [
    page([{"block_id": "b"}]),
    {"block_id": "b", "parent_id": "root", "block_type": 43, "board": {}},
]

# table_no_cells: a type-31 table with an empty children list -> the TableNode()
# early-out -> "" (test_table_migration.test_table_handler_empty_children_is_empty_tablenode).
CASES["table_no_cells"] = [
    page([{"block_id": "tbl"}]),
    {"block_id": "tbl", "parent_id": "root", "block_type": 31,
     "table": {"property": {"column_size": 2}}, "children": []},
]

# -- styled-run edges --------------------------------------------------------

# styled_text_runs: one styled run per marker family (bold / italic /
# strikethrough / underline), each -> StyledText, pinning the renderer's marker
# composition (bold **, italic _, strike ~~, underline <u>) at the document level
# (test_text_migration.test_text_handler_styled_run_is_styledtext pins bold).
CASES["styled_text_runs"] = [
    page([{"block_id": "t"}]),
    {"block_id": "t", "parent_id": "root", "block_type": 2, "text": {"elements": [
        tr("bold", bold=True), tr(" "), tr("italic", italic=True), tr(" "),
        tr("strike", strikethrough=True), tr(" "), tr("under", underline=True)]}},
]

# -- equation quirks ---------------------------------------------------------

# equation_multi_element: a block equation with MULTIPLE elements — each element's
# trailing "\n" is stripped, then the parts are joined (no separator) into one
# $$...$$ body (test_text_migration.test_equation_handler_joins_multiple_elements_stripping_newlines).
CASES["equation_multi_element"] = [
    page([{"block_id": "e"}]),
    {"block_id": "e", "parent_id": "root", "block_type": 16, "equation": {"elements": [
        {"equation": {"content": "a^2 + b^2\n"}},
        {"equation": {"content": " = c^2\n"}}]}},
]

# inline_equation_in_text: an equation element INSIDE a type-2 text block ->
# InlineEquation ($...$), NOT a block $$ equation (the inline-vs-block
# discrimination; test_text_migration.test_inline_equation_in_text_block_is_inline_equation_node).
CASES["inline_equation_in_text"] = [
    page([{"block_id": "t"}]),
    {"block_id": "t", "parent_id": "root", "block_type": 2, "text": {"elements": [
        tr("inline "), {"equation": {"content": "x^2"}}]}},
]

# -- container edges ---------------------------------------------------------

# callout_wrapping_quote: a callout (no emoji) wrapping a quote + a paragraph.
# Pins the "> > " nested-quote prefix AND the callout blank line rendered as "> "
# (WITH the trailing space that distinguishes callout from quote_container — see
# the paired quote_container_wrapping_quote below; test_container_migration
# callout renderer pins).
CASES["callout_wrapping_quote"] = [
    page([{"block_id": "co"}]),
    {"block_id": "co", "parent_id": "root", "block_type": 19,
     "callout": {"emoji_id": "star"}, "children": ["q1", "t1"]},
    {"block_id": "q1", "parent_id": "co", "block_type": 15,
     "quote": {"elements": [tr("Insight")]}},
    {"block_id": "t1", "parent_id": "co", "block_type": 2,
     "text": {"elements": [tr("Follow-up.")]}},
]

# quote_container_multiline: a quote_container wrapping ONE quote whose content
# spans two lines — EVERY line gets the "> > " prefix (test_container_migration
# .test_quote_container_prefixes_every_line_of_multiline_child_via_render).
CASES["quote_container_multiline"] = [
    page([{"block_id": "qc"}]),
    {"block_id": "qc", "parent_id": "root", "block_type": 34,
     "quote_container": {}, "children": ["q1"]},
    {"block_id": "q1", "parent_id": "qc", "block_type": 15,
     "quote": {"elements": [tr("line1\nline2")]}},
]

# quote_container_wrapping_quote: a quote_container wrapping a quote + a paragraph.
# The per-child rstrip drops the quote's trailing blank so NO bare ">" leaks
# between the two children — the load-bearing quote_container behavior, contrasted
# with callout_wrapping_quote above (test_container_migration per-child rstrip pins).
CASES["quote_container_wrapping_quote"] = [
    page([{"block_id": "qc"}]),
    {"block_id": "qc", "parent_id": "root", "block_type": 34,
     "quote_container": {}, "children": ["q1", "t1"]},
    {"block_id": "q1", "parent_id": "qc", "block_type": 15,
     "quote": {"elements": [tr("Insight")]}},
    {"block_id": "t1", "parent_id": "qc", "block_type": 2,
     "text": {"elements": [tr("Follow-up.")]}},
]

# grid_childless_column: a grid with a CHILDLESS column and a populated one — the
# empty column is omitted, so only the populated column renders with no stray
# blank-line separator (test_container_migration.test_grid_handler_skips_childless_columns).
CASES["grid_childless_column"] = [
    page([{"block_id": "g"}]),
    {"block_id": "g", "parent_id": "root", "block_type": 24,
     "grid": {"column_size": 2}, "children": ["gc1", "gc2"]},
    {"block_id": "gc1", "parent_id": "g", "block_type": 25,
     "grid_column": {}, "children": []},
    {"block_id": "gc2", "parent_id": "g", "block_type": 25,
     "grid_column": {}, "children": ["gx"]},
    {"block_id": "gx", "parent_id": "gc2", "block_type": 2,
     "text": {"elements": [tr("Right")]}},
]

# -- media / file / diagram edges -------------------------------------------

# image_with_caption: an image with BOTH a token and a caption -> the alt text is
# populated (the `image` golden has a token but no caption -> empty alt;
# test_media_file_diagram_migration.test_image_handler_returns_image_node_with_token_and_caption).
CASES["image_with_caption"] = [
    page([{"block_id": "i"}]),
    {"block_id": "i", "parent_id": "root", "block_type": 27,
     "image": {"token": "boxcnCAP", "caption": {"content": "Figure 1"}}},
]

# image_missing_token_caption: an image with a caption but NO token -> the
# "[Image: missing token] {caption}" marker — the caption-APPEND branch, which
# image_no_token (empty caption) does not exercise (test_media_file_diagram
# _migration.test_image_renderer_missing_token_marker_with_caption).
CASES["image_missing_token_caption"] = [
    page([{"block_id": "i"}]),
    {"block_id": "i", "parent_id": "root", "block_type": 27,
     "image": {"caption": {"content": "orphan"}}},
]

# add_ons_unsupported: a type-40 add-on whose component_type_id is NOT the Mermaid
# id -> the visible "[Unsupported Add-On block: {id}]" marker (test_media_file
# _diagram_migration.test_add_ons_handler_unsupported_component_sets_marker_id).
CASES["add_ons_unsupported"] = [
    page([{"block_id": "a"}]),
    {"block_id": "a", "parent_id": "root", "block_type": 40,
     "add_ons": {"component_id": "c1", "component_type_id": "blk_OTHER",
                 "record": "{}"}},
]

# add_ons_unknown_component: a type-40 add-on with NO component_type_id -> the id
# defaults to the literal "unknown" (never the string "None") in the marker (the
# `or 'unknown'` fallback; distinct code path from add_ons_unsupported above;
# test_media_file_diagram_migration.test_add_ons_handler_unsupported_none_component_uses_unknown).
CASES["add_ons_unknown_component"] = [
    page([{"block_id": "a"}]),
    {"block_id": "a", "parent_id": "root", "block_type": 40,
     "add_ons": {"record": "{}"}},
]

# mermaid_raw_record: a Mermaid add-on whose record is NOT valid JSON -> the raw
# record string is kept verbatim as the fenced source (the JSONDecodeError
# fallback; test_media_file_diagram_migration.test_add_ons_handler_invalid_json_falls_back_to_raw_record).
CASES["mermaid_raw_record"] = [
    page([{"block_id": "m"}]),
    {"block_id": "m", "parent_id": "root", "block_type": 40,
     "add_ons": {"component_type_id": "blk_640017963d808005a21a6445",
                 "record": "graph TD; A-->B"}},
]

# file_no_token: a file attachment with a name but NO token -> the marker WITHOUT
# the "(token: ...)" suffix (the `file_attachment` golden carries a token;
# test_media_file_diagram_migration.test_file_renderer_without_token).
CASES["file_no_token"] = [
    page([{"block_id": "f"}]),
    {"block_id": "f", "parent_id": "root", "block_type": 23,
     "file": {"name": "notes.txt"}},
]

# file_name_fallback: a file attachment whose name is null -> the "Unknown File
# Attachment" fallback name (token still emitted; test_media_file_diagram
# _migration.test_file_handler_name_none_falls_back).
CASES["file_name_fallback"] = [
    page([{"block_id": "f"}]),
    {"block_id": "f", "parent_id": "root", "block_type": 23,
     "file": {"token": "FTOK", "name": None}},
]

# -- table edges -------------------------------------------------------------

# table_header_row_false: header_row explicitly False -> the first row is NOT
# promoted; Markdown has no headerless syntax, so an EMPTY header row is emitted
# above the delimiter and every real row (incl. the first) stays as data
# (test_table_migration.test_table_handler_preserves_header_row_false).
CASES["table_header_row_false"] = [
    page([{"block_id": "tbl"}]),
    {"block_id": "tbl", "parent_id": "root", "block_type": 31,
     "table": {"property": {"row_size": 1, "column_size": 2, "header_row": False}},
     "children": ["c0", "c1"]},
    *_cell("c0", "tbl", "Name"),
    *_cell("c1", "tbl", "Value"),
]

# table_default_col_size: a table with `table:{}` (NO property block) -> col_size
# defaults to 1 and header_row (None) defaults to True (test_table_migration
# .test_table_handler_defaults_col_size_when_property_absent).
CASES["table_default_col_size"] = [
    page([{"block_id": "tbl"}]),
    {"block_id": "tbl", "parent_id": "root", "block_type": 31, "table": {},
     "children": ["c0"]},
    *_cell("c0", "tbl", "A"),
]

# -- page-title gate / spine edges -------------------------------------------

# page_blank_title: a page whose title elements are EMPTY -> no "# " heading (the
# renderer's .strip() gate; test_page_parser_migration.test_page_renderer_blank_title_emits_no_heading).
CASES["page_blank_title"] = [
    {"block_id": "root", "parent_id": "doc", "block_type": 1,
     "page": {"elements": []}, "children": ["b"]},
    {"block_id": "b", "parent_id": "root", "block_type": 2,
     "text": {"elements": [tr("Body text")]}},
]

# page_whitespace_title: a page whose title is WHITESPACE-ONLY -> strips to empty
# -> no "# " heading (test_page_parser_migration.test_page_renderer_whitespace_only_title_emits_no_heading).
CASES["page_whitespace_title"] = [
    {"block_id": "root", "parent_id": "doc", "block_type": 1,
     "page": {"elements": [tr("   ")]}, "children": ["b"]},
    {"block_id": "b", "parent_id": "root", "block_type": 2,
     "text": {"elements": [tr("Body")]}},
]

# page_dangling_child: a page with a DANGLING child id ("ghost" resolves to no
# block) -> the slot is kept as an empty node so the page's per-child "\n"
# separator is still emitted; the child is NOT dropped (test_page_parser
# _migration.test_page_handler_missing_child_is_empty_node_not_dropped).
CASES["page_dangling_child"] = [
    {"block_id": "root", "parent_id": "doc", "block_type": 1,
     "page": {"elements": [tr("Doc Title")]}, "children": ["real", "ghost"]},
    {"block_id": "real", "parent_id": "root", "block_type": 2,
     "text": {"elements": [tr("x")]}},
]


# ---------------------------------------------------------------------------
# LD-130 — the dogfood F1 repro, as a golden. Plain (type-2) paragraphs whose
# LITERAL text is a Markdown metacharacter pattern must not emit structure. One
# paragraph per ambiguity class, plus the unambiguous control (p12 — nothing may
# be escaped there) and a unicode paragraph (p13).
# ---------------------------------------------------------------------------
_METACHAR_PARAGRAPHS = [
    "# Fake H1",
    "- Apples",
    "* Star",
    "+ Plus",
    "> Quoted",
    "| Fruit | Season |",
    "1. First",
    "text with **stars** and _score_",
    "a `code` span and a ~~strike~~ run",
    "---",
    "#",
    "Issue #5 costs 5 - 10 dollars, 2 * 3 = 6, snake_case stays",
    "水果 — # 假标题 with **粗体** markers",
]
CASES["metachar_plain_text"] = [
    # The page title is the document's ONE real heading — the report's live
    # evidence was that "# Fake H1" became byte-indistinguishable from it.
    {"block_id": "root", "parent_id": "doc", "block_type": 1,
     "page": {"elements": [tr("Scratch Doc")]},
     "children": [f"p{i}" for i in range(1, len(_METACHAR_PARAGRAPHS) + 1)]},
] + [
    {"block_id": f"p{i}", "parent_id": "root", "block_type": 2,
     "text": {"elements": [tr(content)]}}
    for i, content in enumerate(_METACHAR_PARAGRAPHS, start=1)
]

# metachar_in_real_structure: the other half of the contract — REAL structure
# nodes (heading / bullet / ordered / quote / table) whose TEXT carries the same
# metacharacters. The markers are structure and stay bare; the text is escaped
# in block context and left alone inside a GFM cell (an inline-only context, so
# the cell's own pipe-escape is never doubled).
CASES["metachar_in_real_structure"] = [
    {"block_id": "root", "parent_id": "doc", "block_type": 1,
     "page": {"elements": [tr("Real Doc")]},
     "children": ["h2", "b1", "o1", "q1", "tbl"]},
    {"block_id": "h2", "parent_id": "root", "block_type": 4,
     "heading2": {"elements": [tr("Real Section")]}, "children": []},
    {"block_id": "b1", "parent_id": "root", "block_type": 12,
     "bullet": {"elements": [tr("# Fake H1 inside a real bullet")]}, "children": []},
    {"block_id": "o1", "parent_id": "root", "block_type": 13,
     "ordered": {"elements": [tr("1. nested numbering in a real ordered item")]},
     "children": []},
    {"block_id": "q1", "parent_id": "root", "block_type": 15,
     "quote": {"elements": [tr("- Apples in a real quote")]}},
    {"block_id": "tbl", "parent_id": "root", "block_type": 31,
     "table": {"property": {"row_size": 2, "column_size": 2}},
     "children": ["c00", "c01", "c10", "c11"]},
    *_cell("c00", "tbl", "H1"),
    *_cell("c01", "tbl", "H2"),
    *_cell("c10", "tbl", "| pipe and # hash"),
    *_cell("c11", "tbl", "**stars** in a cell"),
]


# ── in-cell images (LD-506) ────────────────────────────────────────────────────
#
# THE CORPUS BLIND SPOT THIS FILLS, measured by the maintainer 2026-08-18: six fixtures
# carry a ``"block_type": 27`` and **none of them also carries a
# ``"block_type": 32``** — so an image inside a table cell, a position a consumer
# reported, had no golden at all, which is
# why the suite was green on a shape a consumer measured as broken
# (a consumer's report, in the maintainers' records).
#
# PROVENANCE — and it is TWO-TIER, so read which tier a case is in before quoting it.
#
# TIER 1, THE PRIMARY FIXTURE ``table_cell_image`` IS A REAL PAYLOAD, ITS STRUCTURE VERBATIM.
# It is the block list of a real docx document, exactly as
# ``GET /open-apis/docx/v1/documents/{id}/blocks`` returned it, captured by
# ``dev/ld506-in-cell-image/probes/probe_ld506_live_capture.py`` on 2026-08-19 →
# ``dev/ld506-in-cell-image/captures/002-in-cell-image-raw-payload.json``
# (key ``blocks_flat_route``). Nothing below is transcribed or simplified: the
# ``text_element_style`` / ``style`` sub-objects and the ``parent_id: ""`` on the root
# are as Lark sent them. The block ids and the media token are NOT: in this tree they
# are the substitution map's placeholders (``tests/captures/README.md``), replaced
# consistently, so every id still points where Lark's did; and the three cell texts
# are neutral words (``Variant`` / ``Image`` / ``Variant A``) in place of the probe's
# own sample text — the text is not what this fixture pins. The document was created by that probe, one image was authored into
# one cell by the shipped ``put_image_in_document`` with the cell's own block id as
# ``parent_block_id``, and the payload was read straight back. That upload is the
# ONE permanent media token LD-506 was authorised to mint (§ Media budget;
# ``captures/000-budget-declared.json``, committed before the send).
#
# THE ONE STRUCTURAL FACT THE REAL PAYLOAD TAUGHT US, and it is why this fixture
# was re-derived rather than left as a transcription: **a real table cell ALWAYS
# carries an auto-provisioned inner text block (type 2), and an authored image is
# appended AFTER it.** So the image cell's children are ``[<empty text>, <image>]``
# — "an image as a cell's only child" is a shape Lark does not produce for an
# authored image. It is rendering-inert here (measured: the projection is identical
# with and without the empty sibling), but a fixture claiming a shape the API never
# emits is a provenance claim it does not have, so the real one is pinned instead.
#
# TIER 2, THE FOUR OTHER CASES ARE DERIVED BY EDITING that captured JSON — the
# route the issue's § Media budget requires ("any further fixture shape is built by
# EDITING the captured JSON into a sibling fixture with its provenance stated
# in-file — never by a second upload"). They keep the short synthetic ids of the
# fixture family for readability and they SIMPLIFY AWAY the auto-provisioned empty
# text sibling described above; their table/cell/image payload shapes match the
# real capture and are corroborated by two older committed real read-backs,
# ``dev/table-row-boundary/captures/11-read-back-after-the-shipped-path.json``
# (table(31)/table_cell(32)) and
# ``dev/media-spike/captures/521-fixture-final-read-back-what-the-fixture-actually-contains.json``
# (image(27), and the two older media tokens they carry).


def _live_image(bid, parent_id, token):
    """An image(27) block in the shape a live read-back returns (media-spike 521-)."""
    return {"block_id": bid, "parent_id": parent_id, "block_type": 27,
            "image": {"align": 2, "height": 60, "scale": 1,
                      "token": token, "width": 120}}


def _live_cell(cid, parent_id, child_ids):
    """A table_cell(32) in the live read-back shape: ``table_cell: {}`` + children."""
    return {"block_id": cid, "parent_id": parent_id, "block_type": 32,
            "table_cell": {}, "children": list(child_ids)}


def _live_table(bid, cell_ids, column_size, row_size,
                header_row=True, merge_info=None):
    """A table(31) in the live read-back shape (``cells`` + full ``property``)."""
    return {"block_id": bid, "parent_id": "root", "block_type": 31,
            "table": {"cells": list(cell_ids),
                      "property": {"column_size": column_size,
                                   "column_width": [100] * column_size,
                                   "header_row": header_row,
                                   "merge_info": merge_info or [
                                       {"col_span": 1, "row_span": 1}
                                       for _ in cell_ids],
                                   "row_size": row_size}},
            "children": list(cell_ids)}


# Two real media tokens, both already committed under dev/media-spike/captures/
# (permanent, already-ledgered residue of LD-433 — this issue mints nothing).
_TOK_A = "Example5b74e41794c11195d4e5"
_TOK_B = "Example9b10513d2f7ee3b9c064"

# table_cell_image — TIER 1: A REAL PAYLOAD, ITS STRUCTURE VERBATIM (see the § header above).
# A two-column table whose second column holds a picture — as the API actually
# returns it. Do not "tidy" this list:
# every style sub-object and the empty `parent_id` on the root came off the wire
# (the ids and tokens are the map's consistent placeholders), and the empty text block at `doxlgExa…` is the cell's auto-provisioned
# inner block that the authored image was appended after. Source of truth:
# dev/ld506-in-cell-image/captures/002-in-cell-image-raw-payload.json
#   → ["blocks_flat_route"]   (probe_ld506_live_capture.py, 2026-08-19)
_STYLE_OFF = {"bold": False, "inline_code": False, "italic": False,
              "strikethrough": False, "underline": False}


def _captured_text(bid, parent_id, content):
    """A text(2) block exactly as the 002- capture returned it."""
    return {"block_id": bid, "block_type": 2, "parent_id": parent_id,
            "text": {"elements": [{"text_run": {
                "content": content, "text_element_style": dict(_STYLE_OFF)}}],
                "style": {"align": 1, "folded": False}}}


CASES["table_cell_image"] = [
    {"block_id": "Examplee952f37af51cbcffdce1", "block_type": 1,
     "children": ["doxlgExample3c9c34d6a6dcf68"],
     "page": {"elements": [{"text_run": {
         "content": "larkdocio-LD-506-in-cell-image 1787081171",
         "text_element_style": dict(_STYLE_OFF)}}],
         "style": {"align": 1}},
     "parent_id": ""},
    {"block_id": "doxlgExample3c9c34d6a6dcf68", "block_type": 31,
     "children": ["doxlgExamplefdcd83e6f9f2c53", "doxlgExample19f049012999344",
                  "doxlgExample6da5a96cb59e2ec", "doxlgExamplebcbb97c6d1b317b"],
     "parent_id": "Examplee952f37af51cbcffdce1",
     "table": {"cells": ["doxlgExamplefdcd83e6f9f2c53",
                         "doxlgExample19f049012999344",
                         "doxlgExample6da5a96cb59e2ec",
                         "doxlgExamplebcbb97c6d1b317b"],
               "property": {"column_size": 2, "column_width": [100, 100],
                            "header_row": True,
                            "merge_info": [{"col_span": 1, "row_span": 1},
                                           {"col_span": 1, "row_span": 1},
                                           {"col_span": 1, "row_span": 1},
                                           {"col_span": 1, "row_span": 1}],
                            "row_size": 2}}},
    {"block_id": "doxlgExamplefdcd83e6f9f2c53", "block_type": 32,
     "children": ["doxlgExampleddacc5dcff5fec9"],
     "parent_id": "doxlgExample3c9c34d6a6dcf68", "table_cell": {}},
    _captured_text("doxlgExampleddacc5dcff5fec9",
                   "doxlgExamplefdcd83e6f9f2c53", "Variant"),
    {"block_id": "doxlgExample19f049012999344", "block_type": 32,
     "children": ["doxlgExamplefa1821fbc2d0175"],
     "parent_id": "doxlgExample3c9c34d6a6dcf68", "table_cell": {}},
    _captured_text("doxlgExamplefa1821fbc2d0175",
                   "doxlgExample19f049012999344", "Image"),
    {"block_id": "doxlgExample6da5a96cb59e2ec", "block_type": 32,
     "children": ["doxlgExample18795a8c8cdfc67"],
     "parent_id": "doxlgExample3c9c34d6a6dcf68", "table_cell": {}},
    _captured_text("doxlgExample18795a8c8cdfc67",
                   "doxlgExample6da5a96cb59e2ec", "Variant A"),
    # THE CELL THE IMAGE LIVES IN — TWO children, and that is the real shape:
    # the auto-provisioned empty text block first, the authored image after it.
    {"block_id": "doxlgExamplebcbb97c6d1b317b", "block_type": 32,
     "children": ["doxlgExampleb0651016353a877", "doxlgExample62d93f236e57a0b"],
     "parent_id": "doxlgExample3c9c34d6a6dcf68", "table_cell": {}},
    _captured_text("doxlgExampleb0651016353a877",
                   "doxlgExamplebcbb97c6d1b317b", ""),
    # width/height read back as 1x1 although the probe REQUESTED 120x60 — the
    # create-time geometry did not bind. Recorded, not acted on: that is LD-508's.
    {"block_id": "doxlgExample62d93f236e57a0b", "block_type": 27,
     "image": {"align": 2, "height": 1, "scale": 1,
               "token": "Examplec11ec9e2c11b40f4193c", "width": 1},
     "parent_id": "doxlgExamplebcbb97c6d1b317b"},
]

# table_cell_image_beside_text: image and text as siblings in ONE cell — the
# pipe path joins a cell's lines with <br>, so the image must survive that join.
CASES["table_cell_image_beside_text"] = [
    page([{"block_id": "tcb"}]),
    _live_table("tcb", ["tcb0", "tcb1"], 2, 1),
    _live_cell("tcb0", "tcb", ["tcb0t"]),
    {"block_id": "tcb0t", "parent_id": "tcb0", "block_type": 2,
     "text": {"elements": [tr("Variant A")]}},
    _live_cell("tcb1", "tcb", ["tcb1t", "tcb1i"]),
    {"block_id": "tcb1t", "parent_id": "tcb1", "block_type": 2,
     "text": {"elements": [tr("image:")]}},
    _live_image("tcb1i", "tcb1", _TOK_A),
]

# table_cell_two_images: two images in ONE cell (both must project, both queued).
CASES["table_cell_two_images"] = [
    page([{"block_id": "tct"}]),
    _live_table("tct", ["tct0", "tct1"], 1, 2),
    _live_cell("tct0", "tct", ["tct0t"]),
    {"block_id": "tct0t", "parent_id": "tct0", "block_type": 2,
     "text": {"elements": [tr("Images")]}},
    _live_cell("tct1", "tct", ["tct1a", "tct1b"]),
    _live_image("tct1a", "tct1", _TOK_A),
    _live_image("tct1b", "tct1", _TOK_B),
]

# merged_table_cell_image: an in-cell image on the MERGED table's HTML path —
# the image sits in the ANCHOR cell of a colspan-2 merge, so it must emit
# `<img src="{token}"/>` (the token preserved for the T1 relink), NOT `![](…)`.
_MERGE_COLSPAN2 = [{"col_span": 2, "row_span": 1}, {"col_span": 1, "row_span": 1},
                   {"col_span": 1, "row_span": 1}, {"col_span": 1, "row_span": 1}]

CASES["merged_table_cell_image"] = [
    page([{"block_id": "mci"}]),
    _live_table("mci", ["mci0", "mci1", "mci2", "mci3"], 2, 2,
                header_row=False, merge_info=_MERGE_COLSPAN2),
    _live_cell("mci0", "mci", ["mci0i"]),
    _live_image("mci0i", "mci0", _TOK_A),
    _live_cell("mci1", "mci", []),
    _live_cell("mci2", "mci", ["mci2t"]),
    {"block_id": "mci2t", "parent_id": "mci2", "block_type": 2,
     "text": {"elements": [tr("Variant A")]}},
    _live_cell("mci3", "mci", ["mci3t"]),
    {"block_id": "mci3t", "parent_id": "mci3", "block_type": 2,
     "text": {"elements": [tr("Light")]}},
]

# merged_table_covered_cell_image: the ONE measured drop (LD-506, offline shape
# matrix, dev/ld506-in-cell-image/captures/001-offline-shape-matrix.json case 5).
# The image sits at a grid position CLAIMED by the preceding anchor's colspan.
# `_table_html`'s computed-occupancy rule (LD-050) emits NO cell there, so the
# image is dropped from the projection while its token is STILL queued on
# `parser.img_tokens` — the file downloads and nothing links it.
#
# THIS GOLDEN PINS A DEFECT, DELIBERATELY AND LOUDLY. It is not a statement that
# the behaviour is correct: the matching assertion in
# `tests/test_in_cell_image_projection.py` is a STRICT xfail on the correct
# expectation, so a future fix reddens the suite and forces both to move
# together. The fix is NOT taken here — it would move the pre-existing
# `merged_table_gauntlet` golden (whose covered cells carry text), which LD-506
# § AC5 makes a FAIL condition. Referred to the maintainer; see
# `dev/ld506-in-cell-image/findings.md` § "Finding B".
CASES["merged_table_covered_cell_image"] = [
    page([{"block_id": "mcc"}]),
    _live_table("mcc", ["mcc0", "mcc1", "mcc2", "mcc3"], 2, 2,
                header_row=False, merge_info=_MERGE_COLSPAN2),
    _live_cell("mcc0", "mcc", ["mcc0t"]),
    {"block_id": "mcc0t", "parent_id": "mcc0", "block_type": 2,
     "text": {"elements": [tr("Images")]}},
    _live_cell("mcc1", "mcc", ["mcc1i"]),
    _live_image("mcc1i", "mcc1", _TOK_A),
    _live_cell("mcc2", "mcc", ["mcc2t"]),
    {"block_id": "mcc2t", "parent_id": "mcc2", "block_type": 2,
     "text": {"elements": [tr("Variant A")]}},
    _live_cell("mcc3", "mcc", ["mcc3t"]),
    {"block_id": "mcc3t", "parent_id": "mcc3", "block_type": 2,
     "text": {"elements": [tr("Light")]}},
]


def write_inputs():
    FIX.mkdir(parents=True, exist_ok=True)
    for name, blocks in CASES.items():
        path = FIX / f"{name}.input.json"
        path.write_text(json.dumps(blocks, indent=2) + "\n", encoding="utf-8")
    return list(CASES.keys())


if __name__ == "__main__":
    names = write_inputs()
    print("wrote inputs:", names)
