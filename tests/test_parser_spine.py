"""Parser-core spine tests (LD-031).

The parser spine — ``parse_docx_content`` / the node-producing recursion
primitive / the ``page(1)`` root — plus the recursion/indent contract. These
pin the spine behaviors the T1 net left unexercised, so the byte-identical
rewrite onto the model is safe.

Mutation target (AC2): ``dev/mutation-baseline-2026-07-24.md`` § per-module
reports ``read/parser.py`` at 68.1 % with 15 survivors. A focused mutmut run
(``only_mutate = read/parser.py``) showed the survivors concentrate in two real
net-gaps, killed here TEST-FIRST:

* the **entry-block-missing fallback** — when the ``doc_id`` block is absent
  from the payload the parser reconstructs the document from the top-level
  children (``parent_id == doc_id``), joined with NO separator. The whole path
  was untested: every mutation of it survived (``buf = None``, ``== -> !=``,
  ``parse_docx_block(block, None)`` / ``(None, 0)`` / arg-dropped,
  ``"".join`` -> ``"XXXX".join`` / ``join(None)``). Tests 1-3 below exercise it.
* the **missing/dangling child guard** — ``parse_docx_block`` returns ``""`` for
  a falsy block (a ``child_id`` that resolves to no block); the ``return ""`` ->
  ``return "XXXX"`` mutant survived. Test 4 below.

(The entry-block indent argument mutants — ``parse_docx_block(entry_block, 0)``
-> ``None`` / ``1`` — are EQUIVALENT for a page entry block: page is not a list
type, so the indent tab is never prepended to it, and page recurses its children
at 0 explicitly, so the entry indent never propagates. Not force-killed.)

KEEP (LD-096, mindfulness not immunity): the mutation-kill holder for the parser
spine — the entry-block-missing (headless) fallback reconstruction, the
missing/dangling-child ``return ""`` guard (now also the holder for the removed
``test_page_parser_migration`` missing-child overlap), and the recursion/indent
contract. None expressible as document output. A future audit may revisit.
"""
from harness import build_blocks, render

from larkdocio.read.config import Config
from larkdocio.read.parser import Parser


# --- 1-3: the entry-block-missing fallback (reconstruct from top-level) -----

def test_headless_fallback_reconstructs_from_top_level_children():
    # doc_id points at a page/root block that is ABSENT from the payload; the
    # parser falls back to concatenating the top-level children
    # (parent_id == doc_id) with NO separator between them. Pins that fallback
    # byte-for-byte (it was a cluster of mutation survivors — the path never ran
    # in any test).
    blocks = [
        {"block_id": "t1", "parent_id": "missing_root", "block_type": 2,
         "text": {"elements": [{"text_run": {"content": "alpha"}}]}, "children": []},
        {"block_id": "t2", "parent_id": "missing_root", "block_type": 2,
         "text": {"elements": [{"text_run": {"content": "beta"}}]}, "children": []},
    ]
    out = render(blocks, doc_id="missing_root")
    # Each text block renders "<content>\n"; the fallback joins with NO separator.
    assert out == "alpha\nbeta\n"


def test_headless_fallback_only_includes_direct_children_of_doc_id():
    # A block whose parent is NOT the (missing) doc_id must be excluded from the
    # reconstructed root — pins the `parent_id == doc_id` predicate (the
    # `==` -> `!=` mutant flips inclusion, which this catches in both directions).
    blocks = [
        {"block_id": "t1", "parent_id": "missing_root", "block_type": 2,
         "text": {"elements": [{"text_run": {"content": "top"}}]}, "children": []},
        {"block_id": "t2", "parent_id": "somewhere_else", "block_type": 2,
         "text": {"elements": [{"text_run": {"content": "orphan"}}]}, "children": []},
    ]
    out = render(blocks, doc_id="missing_root")
    assert out == "top\n"
    assert "orphan" not in out


def test_headless_fallback_preserves_payload_order():
    # The reconstructed root keeps the payload's block order (the fallback
    # iterates `blocks`, not a children list) — a join-order regression shows up
    # as swapped text.
    blocks = [
        {"block_id": "b1", "parent_id": "gone", "block_type": 2,
         "text": {"elements": [{"text_run": {"content": "first"}}]}, "children": []},
        {"block_id": "b2", "parent_id": "gone", "block_type": 2,
         "text": {"elements": [{"text_run": {"content": "second"}}]}, "children": []},
        {"block_id": "b3", "parent_id": "gone", "block_type": 2,
         "text": {"elements": [{"text_run": {"content": "third"}}]}, "children": []},
    ]
    assert render(blocks, doc_id="gone") == "first\nsecond\nthird\n"


# --- 4: the missing/dangling child guard ------------------------------------

def test_missing_child_block_renders_empty_not_marker():
    # A page whose child_id does not resolve to any block: the missing child
    # contributes nothing (the `if not b: return ""` guard), never a stray
    # marker, but the page's own per-child "\n" separator is still emitted.
    blocks = [
        {"block_id": "root", "parent_id": "doc", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "Doc"}}]},
         "children": ["real", "ghost"]},
        {"block_id": "real", "parent_id": "root", "block_type": 2,
         "text": {"elements": [{"text_run": {"content": "here"}}]}, "children": []},
        # "ghost" is referenced by the page but absent from the payload.
    ]
    out = render(blocks, doc_id="root")
    assert "XXXX" not in out
    # page: "# Doc\n" + "\n" separator, then real ("here\n") + "\n", then the
    # ghost ("" ) + its "\n" separator.
    assert out == "# Doc\n\nhere\n\n\n"


# --- 5-6: the recursion/indent contract (node -> string at a depth) ---------
#
# These pin the same indent contract the retired ``parse_docx_block`` string
# boundary used to guard. Serializing a node to its string at a depth is now
# ``renderer.render(parse_docx_node(b, il), depth=il)`` directly (that IS what
# the boundary delegate did before the R-S5 teardown deleted it, LD-038).

def test_indent_contract_list_type_gets_leading_tab_equal_to_depth():
    # The recursion/indent contract: a list-item block (12/13/17) carries a
    # leading indent of `indent_level` hard tabs — the tab count IS the depth.
    parser = Parser(Config())
    b = build_blocks([
        {"block_id": "x", "parent_id": "root", "block_type": 12,
         "bullet": {"elements": [{"text_run": {"content": "deep"}}]}},
    ])[0]
    parser.block_map["x"] = b
    assert parser.renderer.render(parser.parse_docx_node(b, 0), depth=0) == "- deep\n"
    assert parser.renderer.render(parser.parse_docx_node(b, 3), depth=3) == "\t\t\t- deep\n"


def test_indent_contract_nested_list_child_indents_one_deeper():
    # The other half of the contract: list handlers recurse their children at
    # `indent_level + 1`, so rendering an outer list item at depth 1 puts its
    # inner list child at depth 2 (one extra tab). Pins the recurse-deeper rule
    # (and kills the indent-passthrough survivor: dropping the indent argument
    # crashes the child recursion).
    parser = Parser(Config())
    blocks = build_blocks([
        {"block_id": "outer", "parent_id": "root", "block_type": 12,
         "bullet": {"elements": [{"text_run": {"content": "outer"}}]},
         "children": ["inner"]},
        {"block_id": "inner", "parent_id": "outer", "block_type": 12,
         "bullet": {"elements": [{"text_run": {"content": "inner"}}]},
         "children": []},
    ])
    for blk in blocks:
        parser.block_map[blk.block_id] = blk
    out = parser.renderer.render(parser.parse_docx_node(parser.block_map["outer"], 1), depth=1)
    assert out == "\t- outer\n\t\t- inner\n"


def test_indent_contract_non_list_type_never_indented():
    # A non-list block (a divider) NEVER gets a leading tab, regardless of
    # indent_level — prepending one would corrupt block-level children nested
    # under a list item into indented code blocks (the guard's whole reason).
    parser = Parser(Config())
    d = build_blocks([
        {"block_id": "d", "parent_id": "root", "block_type": 22, "divider": {}},
    ])[0]
    parser.block_map["d"] = d
    assert parser.renderer.render(parser.parse_docx_node(d, 0), depth=0) == "---\n"
    assert parser.renderer.render(parser.parse_docx_node(d, 3), depth=3) == "---\n"


def test_missing_block_renders_empty_string():
    # Serializing a falsy block (a dangling child_id) tolerates it — parse_docx_node
    # yields the empty RawBlock sentinel, which renders "" with no tab even for a
    # would-be list depth.
    parser = Parser(Config())
    assert parser.renderer.render(parser.parse_docx_node(None, 0), depth=0) == ""
    assert parser.renderer.render(parser.parse_docx_node(None, 5), depth=5) == ""
