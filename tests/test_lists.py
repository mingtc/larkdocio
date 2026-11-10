"""Behavioral tests for list block handlers (core/blocks/lists.py).

Covers:
- todo children recursion (the hardening fix): a nested child under a todo
  must appear in the output (mirrors bullet/ordered).
- ordered-list numbering, asserting CURRENT-CORRECT behavior:
    * contiguous siblings number 1, 2, 3
    * a non-ordered sibling interrupting the run resets numbering
    * nested ordered children number independently of their parent run
"""
from harness import build_blocks, render
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser

from builders import page as _page, text_block as _text


def _ordered(bid, parent, content, children=None):
    return {
        "block_id": bid,
        "parent_id": parent,
        "block_type": 13,
        "ordered": {"elements": [{"text_run": {"content": content}}]},
        "children": children or [],
    }


def _todo(bid, parent, content, done=False, children=None):
    todo = {"elements": [{"text_run": {"content": content}}]}
    if done:
        todo["style"] = {"done": True}
    return {
        "block_id": bid,
        "parent_id": parent,
        "block_type": 17,
        "todo": todo,
        "children": children or [],
    }


# --- todo children recursion (the fix) -------------------------------------

def test_todo_renders_nested_child():
    blocks = [
        _page("t1"),
        _todo("t1", "root", "Parent task", children=["t1c1"]),
        _todo("t1c1", "t1", "Nested done task", done=True),
    ]
    out = render(blocks)
    assert "Nested done task" in out, "todo dropped its nested child"
    assert "\t- [x] Nested done task" in out


# --- ordered numbering: current-correct behavior ---------------------------

def test_ordered_contiguous_numbering():
    blocks = [
        _page("o1", "o2", "o3"),
        _ordered("o1", "root", "One"),
        _ordered("o2", "root", "Two"),
        _ordered("o3", "root", "Three"),
    ]
    out = render(blocks)
    assert "1. One" in out
    assert "2. Two" in out
    assert "3. Three" in out


def test_ordered_interrupted_resets_numbering():
    blocks = [
        _page("o1", "o2", "tx", "o3"),
        _ordered("o1", "root", "One"),
        _ordered("o2", "root", "Two"),
        _text("tx", "root", "Interruption"),
        _ordered("o3", "root", "AfterBreak"),
    ]
    out = render(blocks)
    assert "1. One" in out
    assert "2. Two" in out
    # The non-ordered sibling breaks the run; the next ordered resets to 1.
    assert "1. AfterBreak" in out


def test_ordered_resumes_counting_after_break():
    # After a non-ordered sibling breaks the run, the following ordered items
    # form a fresh run that itself counts 1, 2, 3 (not just a single reset).
    blocks = [
        _page("o1", "tx", "o2", "o3", "o4"),
        _ordered("o1", "root", "Before"),
        _text("tx", "root", "Interruption"),
        _ordered("o2", "root", "AfterOne"),
        _ordered("o3", "root", "AfterTwo"),
        _ordered("o4", "root", "AfterThree"),
    ]
    out = render(blocks)
    assert "1. Before" in out
    assert "1. AfterOne" in out
    assert "2. AfterTwo" in out
    assert "3. AfterThree" in out


def test_ordered_two_runs_separated_by_break():
    # Two contiguous runs around an interruption: 1,2 / break / 1,2.
    blocks = [
        _page("a1", "a2", "tx", "b1", "b2"),
        _ordered("a1", "root", "A1"),
        _ordered("a2", "root", "A2"),
        _text("tx", "root", "Break"),
        _ordered("b1", "root", "B1"),
        _ordered("b2", "root", "B2"),
    ]
    out = render(blocks)
    assert "1. A1" in out
    assert "2. A2" in out
    assert "1. B1" in out
    assert "2. B2" in out


def test_ordered_nested_numbers_independently():
    blocks = [
        _page("o1", "o2"),
        _ordered("o1", "root", "Top one", children=["n1", "n2"]),
        _ordered("o2", "root", "Top two"),
        _ordered("n1", "o1", "Nested one"),
        _ordered("n2", "o1", "Nested two"),
    ]
    out = render(blocks)
    assert "1. Top one" in out
    assert "2. Top two" in out
    # Nested ordered items number against their own parent (o1), starting at 1.
    assert "\t1. Nested one" in out
    assert "\t2. Nested two" in out


# --- _ordinal_for fallback paths (mutation net-gaps) ------------------------
#
# These pin the two "return 1" fallbacks in `_ordinal_for`, which the ordinal
# tests above never exercised (every item there has a resolvable parent that
# lists it). They close mutation survivors on lists.py:
#   * mutmut_4         — `if not parent: return 1`  -> `return 2`
#   * mutmut_37/39/40  — `ordinals.get(b.block_id, 1)` default 1 -> None / dropped / 2


def test_ordered_orphan_parent_numbers_from_one():
    # An ordered item whose parent_id points at a block NOT in the map hits the
    # no-parent fallback and numbers from 1 (not 2). Kills mutmut_4.
    blocks = [
        _page("o1"),
        _ordered("o1", "MISSING", "Orphan"),
    ]
    out = render(blocks)
    assert "1. Orphan" in out
    assert "2. Orphan" not in out


def test_ordered_detached_from_parent_children_numbers_from_one():
    # An ordered item whose parent EXISTS but does NOT list it among its
    # children: `_ordinal_for` scans the parent's run (which omits this id) and
    # falls back to `ordinals.get(id, 1)`. Here the item is rendered as a
    # heading's child while its parent_id points back at the (childless-of-it)
    # root, so the default-1 path is the one under test. Kills mutmut_37/39/40.
    heading = {
        "block_id": "h",
        "parent_id": "root",
        "block_type": 3,
        "heading1": {"elements": [{"text_run": {"content": "H"}}]},
        "children": ["o1"],
    }
    o1 = _ordered("o1", "root", "Detached")  # parent_id root, but root.children == ["h"]
    blocks = [_page("h"), heading, o1]
    out = render(blocks)
    assert "1. Detached" in out
    assert "None. Detached" not in out
    assert "2. Detached" not in out


def test_ordered_ordinals_memoized_per_parent():
    # Pins the documented memoization contract of `_ordinal_for` (docstring:
    # "memoized per parent on parser ... scanned at most once"): after a parse,
    # `parser._ordered_ordinals` carries the correct 1-based run map for EVERY
    # parent that had ordered children — not just the last one scanned, and not
    # None. Kills the cache-population survivors mutmut_5/6/11/12/15/35.
    blocks = [
        _page("o1", "o2"),
        _ordered("o1", "root", "Top one", children=["n1", "n2"]),
        _ordered("o2", "root", "Top two"),
        _ordered("n1", "o1", "Nested one"),
        _ordered("n2", "o1", "Nested two"),
    ]
    parser = Parser(Config())
    parser.parse_docx_content("root", build_blocks(blocks))

    memo = parser._ordered_ordinals
    # Both parents are cached (not just the last one scanned), with the correct
    # ordinals — a single scan per parent, memoized on the parser.
    assert memo["root"] == {"o1": 1, "o2": 2}
    assert memo["o1"] == {"n1": 1, "n2": 2}
