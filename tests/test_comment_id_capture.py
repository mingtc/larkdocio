"""LD-158 — ``comment_ids`` captured into the model at BOTH granularities.

The reader has received and discarded ``comment_ids`` since v1.0: it sat in
``test_conformance.GLOBAL_DROP_ALLOWLIST`` classified as "editor metadata". It arrives at
**two** granularities on reads we already perform — a field on ``Block`` (block-level
anchoring) and a field on ``TextElementStyle`` (word-level anchoring) — so throwing it away
discards the only data that can say *which passage* a reviewer objected to.

This is the LD-042 port (``text_color`` / ``background_color``): **consumed-into-model,
dropped-at-render.** The model becomes lossless for a future writer while the ``.md``
projection does not move one byte. So the hard criterion here is ZERO-DRIFT, and this file
carries the in-suite half of it (§ 6): the whole golden corpus re-rendered with ids injected
into every block and every run must still byte-match its ``.expected.md``.

Fixture provenance (the issue makes this a criterion)
-----------------------------------------------------
Re-checked at implementation time, not taken from the mint note:

* ``grep -rl comment_ids tests/fixtures/`` → **0 files**. The corpus still carries no
  ``comment_ids`` at all, so nothing real could be preferred over a hand-authored payload.
  :func:`test_the_golden_corpus_still_carries_no_comment_ids` keeps that finding executable —
  it is also what proves no golden was quietly re-baselined by this work.
* ``tests/captures/comments-probe-captures/`` re-read: ``05-edit-path-comment-ids.json`` records
  ``inline_comment_minted: false``, ``inline_before.block_comment_ids: null`` and
  ``element_comment_ids: [null]``, and both anchored-creation attempts came back
  ``1770001 invalid param``. The API would not mint an anchored comment, so **no real payload
  with a populated ``comment_ids`` exists anywhere in this repo** — at either granularity.

So every payload below is **hand-authored, and therefore synthetic in its pairing**, but it is
synthetic as narrowly as possible and it is never a hand-mocked dict:

* the **objects** are real: every payload goes through :func:`harness.build_blocks`, i.e. the
  SDK's own ``Block(...)`` deserializer, so the tests exercise real ``Block`` and real
  ``TextElementStyle`` instances (``PROJECT.md`` § Quality bar);
* the **run shapes** are real: the three-run paragraph in :data:`_CAPTURED_RUNS` is the
  ``leg1.inside.live_elements_in`` list captured off a live document by the wave-2 probe
  (``tests/captures/comments-probe-captures/05-edit-path-comment-ids.json``) — including the
  ``"bold": false`` style objects Lark really returns on unremarkable runs;
* the **ids** are real: every id used here was really minted against a real disposable by that
  probe and is recorded in ``tests/captures/comments-probe-captures/_run_ledger.json``. That claim is
  itself executable — see :func:`test_the_ids_these_fixtures_use_were_really_minted`;
* only the **pairing** — a real id sitting in a real run's ``comment_ids`` — is synthetic,
  because that is exactly the thing the server refused to create.
"""
import dataclasses
import json
import pathlib

import pytest

from builders import cell, page, table
from harness import FIXTURES_DIR, build_blocks, render

from larkdocio.blocks import get_registry
from larkdocio.model import (
    MarkdownRenderer,
    Node,
    PageNode,
    StyledText,
    TableCellNode,
    TableNode,
    Text,
    TextNode,
    UnknownBlockNode,
)
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_CAPTURES = REPO_ROOT / "tests" / "captures" / "comments-probe-captures"
_LEDGER = _CAPTURES / "_run_ledger.json"
_CAPTURE = _CAPTURES / "05-edit-path-comment-ids.json"

#: Real comment ids the wave-2 probe minted against real disposables, four of them, used as
#: the fixture ids below so the digits are the API's true 19-digit shape.
REAL_ID = "7667711299958083304"
REAL_ID_2 = "7667711015378767586"
REAL_ID_3 = "7667711017745977062"
REAL_ID_4 = "7667711020231577308"

_ALL_IDS = (REAL_ID, REAL_ID_2, REAL_ID_3, REAL_ID_4)


def _minted_ids():
    """Every comment id the probe's own run ledger records as really created."""
    ledger = json.loads(_LEDGER.read_text(encoding="utf-8"))
    return {c["comment_id"] for record in ledger
            for c in record.get("comments_created") or []}


def _captured_runs():
    """The live-captured three-run paragraph (real shapes, ``comment_ids`` on run 1)."""
    payload = json.loads(_CAPTURE.read_text(encoding="utf-8"))
    return payload["leg1"]["inside"]["live_elements_in"]


_CAPTURED_RUNS = _captured_runs()

#: The id the capture's own middle run carries. Unlike the four above this one is the probe's
#: synthetic placeholder — it is quoted, not chosen, because it is what the captured payload
#: literally contains.
_CAPTURED_RUN_ID = "7667000000000000001"


def test_the_ids_these_fixtures_use_were_really_minted():
    """The provenance claim in the module docstring, made executable: all four ids are in the
    probe's run ledger. If the captures are ever re-recorded this reddens rather than leaving
    the docstring quietly lying about where the digits came from."""
    minted = _minted_ids()
    assert minted, "the run ledger records no created comments"
    assert set(_ALL_IDS) <= minted, sorted(set(_ALL_IDS) - minted)


# --------------------------------------------------------------------------- #
# Payload builders — hand-authored, deserialized by the SDK (never a mock).     #
# --------------------------------------------------------------------------- #

def _run(content, **style):
    """One ``text_run`` TextElement; ``style`` becomes its ``text_element_style``."""
    el = {"content": content}
    if style:
        el["text_element_style"] = dict(style)
    return {"text_run": el}


def _run_with_empty_style(content):
    """A run carrying a *present but empty* ``text_element_style`` — the shape that makes
    the AC4 edge concrete (the SDK still builds a real ``TextElementStyle`` object)."""
    return {"text_run": {"content": content, "text_element_style": {}}}


def _text(bid, parent, elements, comment_ids=None, block_type=2, key="text",
          children=()):
    b = {"block_id": bid, "parent_id": parent, "block_type": block_type,
         key: {"elements": list(elements)}, "children": list(children)}
    if comment_ids is not None:
        b["comment_ids"] = list(comment_ids)
    return b


def _one_block_doc(block):
    """A page root carrying exactly ``block``."""
    return [page(block["block_id"]), block]


def _parse_tree(block_dicts, doc_id="root"):
    return Parser(Config()).parse_docx_tree(doc_id, build_blocks(block_dicts))


def _kids(node):
    """A block node's DIRECT child block nodes, whatever attribute carries them."""
    out = []
    for attr in ("children", "cells"):
        out.extend(getattr(node, attr, None) or [])
    for column in getattr(node, "columns", None) or []:
        out.extend(column)
    return out


def _walk(node):
    """Every BLOCK node in a parsed tree, depth-first."""
    yield node
    for child in _kids(node):
        yield from _walk(child)


def _inlines(node):
    """A block node's own inline nodes (its content / title run)."""
    out = []
    for attr in ("content", "title"):
        value = getattr(node, attr, None)
        if isinstance(value, list):
            out.extend(value)
    return out


def _first(tree, block_id):
    for node in _walk(tree):
        if node.block_id == block_id:
            return node
    raise AssertionError(f"no node for block_id {block_id!r}")


# --------------------------------------------------------------------------- #
# 1. AC1 — the field LEAVES the allowlist, and the guard still does real work.  #
# --------------------------------------------------------------------------- #

def test_comment_ids_is_no_longer_on_the_global_drop_allowlist():
    """AC1's first half, as a permanent pin: re-adding the field to
    ``GLOBAL_DROP_ALLOWLIST`` would make the conformance guard pass **vacuously** again
    (allowlisted instead of consumed), so re-adding it must redden — here."""
    from test_conformance import GLOBAL_DROP_ALLOWLIST

    assert "comment_ids" not in GLOBAL_DROP_ALLOWLIST, (
        "comment_ids is consumed into the model now, so allowlisting it would re-permit "
        "the silent drop the conformance guard exists to catch"
    )


def test_only_comment_ids_left_the_allowlist():
    """The scope fence: ``folded`` / ``wrap`` / ``sequence`` / the geometry set stay
    genuinely dropped. Exactly one member moved."""
    from test_conformance import GLOBAL_DROP_ALLOWLIST

    assert GLOBAL_DROP_ALLOWLIST == {
        "border_color",
        "width", "height", "scale", "align",
        "folded", "wrap", "sequence", "indentation_level",
        "view_type", "obj_type", "fallback_type",
        "row_size", "column_width",
        "width_ratio",
    }


def test_the_text_case_now_passes_by_the_field_mention_MECHANISM():
    """AC1's second half: the ``text:TextElementStyle`` case passes because the handler
    source genuinely reads the field — exactly how ``text_color`` / ``background_color``
    pass since LD-042 — not because anything was allowlisted or the guard weakened.
    Deleting the capture reddens the conformance case itself."""
    from test_conformance import _reader_source

    src = _reader_source("larkdocio.blocks.text")
    assert "comment_ids" in src, (
        "the text handler source no longer mentions comment_ids, so the conformance case "
        "can only be passing by an allowlist — the LD-042 mechanism is broken"
    )


def test_the_conformance_case_for_text_element_style_is_green():
    """Run the real guard for the affected case, so this file fails if the mechanism above
    is satisfied on paper but the guard still objects."""
    from test_conformance import (
        HANDLER_CASES,
        test_handler_consumes_model_fields as guard,
    )

    case = next(c for c in HANDLER_CASES if c[2] == "TextElementStyle")
    guard(*case)


# --------------------------------------------------------------------------- #
# 2. AC2 — BLOCK-level capture on the base node.                                #
# --------------------------------------------------------------------------- #

def test_comment_ids_is_declared_ONCE_on_the_Node_base():
    """Dev's documented call: the field rides the **base** ``Node`` (one declaration
    inherited by every block node type), not per-subclass."""
    assert "comment_ids" in {f.name for f in dataclasses.fields(Node)}
    for cls in (TextNode, PageNode, TableNode, TableCellNode, UnknownBlockNode):
        assert "comment_ids" in {f.name for f in dataclasses.fields(cls)}


def test_the_block_level_field_is_kw_only_and_excluded_from_equality():
    """Dev's documented call, the two flags that make it additive: ``kw_only`` so existing
    POSITIONAL constructions are unaffected, and ``compare=False`` so node equality (and
    every structural test keyed on it) is untouched — the ``block_id`` precedent."""
    field = next(f for f in dataclasses.fields(Node) if f.name == "comment_ids")
    assert field.kw_only is True
    assert field.compare is False
    assert field.default is None
    assert TextNode(content=[Text("x")], comment_ids=[REAL_ID]) == TextNode(
        content=[Text("x")]
    )


def test_a_node_built_without_a_source_block_leaves_comment_ids_ABSENT():
    assert TextNode().comment_ids is None
    assert PageNode().comment_ids is None
    # the dangling-child-id sentinel has no source Block: nothing to stamp
    assert Parser(Config()).parse_docx_node(None, 0).comment_ids is None


def test_the_parser_stamps_the_block_level_ids_from_the_source_block():
    tree = _parse_tree(_one_block_doc(
        _text("t1", "root", [_run("body")], comment_ids=[REAL_ID])
    ))
    assert _first(tree, "t1").comment_ids == [REAL_ID]


@pytest.mark.parametrize("block_type", sorted(get_registry()))
def test_EVERY_registered_block_type_carries_its_comment_ids(block_type):
    """AC2's "every block type": ``comment_ids`` is a field on ``Block``, not on one block
    kind, so the capture must be type-blind. It is stamped in the one node-producing
    primitive every registered handler returns through."""
    block = {"block_id": "b1", "parent_id": "root", "block_type": block_type,
             "children": [], "comment_ids": [REAL_ID, REAL_ID_2]}
    node = Parser(Config()).parse_docx_node(build_blocks([block])[0], 0)
    assert isinstance(node, Node)
    assert node.comment_ids == [REAL_ID, REAL_ID_2]


def test_an_UNKNOWN_block_type_keeps_its_comment_ids_like_any_other():
    """The amplifier's unknown-type case: an unregistered type rides ``UnknownBlockNode``
    and must still carry its ids."""
    node = Parser(Config()).parse_docx_node(build_blocks([
        {"block_id": "u1", "parent_id": "root", "block_type": 999,
         "children": [], "comment_ids": [REAL_ID]}
    ])[0], 0)
    assert isinstance(node, UnknownBlockNode)
    assert node.comment_ids == [REAL_ID]


def test_absent_and_present_but_empty_are_DISTINCT_at_block_level():
    """The rule most likely to be fudged: *absent* means the SDK block had no
    ``comment_ids`` field; *present-but-empty* means the API said "nothing anchored here".
    They mean different things to a future writer, so a valid ``[]`` is never falsy-coerced
    to ``None`` and an absent field never becomes ``[]``."""
    absent = _parse_tree(_one_block_doc(_text("a", "root", [_run("x")])))
    empty = _parse_tree(_one_block_doc(
        _text("e", "root", [_run("x")], comment_ids=[])
    ))
    assert _first(absent, "a").comment_ids is None
    assert _first(empty, "e").comment_ids == []
    assert _first(empty, "e").comment_ids is not None


def test_block_level_ids_keep_the_APIs_ORDER_with_no_sort_and_no_dedup():
    ids = [REAL_ID_4, REAL_ID, REAL_ID_3, REAL_ID_2, REAL_ID]
    tree = _parse_tree(_one_block_doc(
        _text("m", "root", [_run("x")], comment_ids=ids)
    ))
    got = _first(tree, "m").comment_ids
    assert got == ids, "the ids are the API's data, not ours to normalize"
    assert got != sorted(got), "this fixture must be unsorted or it proves nothing"
    assert len(got) == 5, "a duplicate id must not be deduped away"


# --------------------------------------------------------------------------- #
# 3. AC3 / AC4 — WORD-level capture, and the plain-run edge CHARACTERIZED.      #
# --------------------------------------------------------------------------- #

def test_StyledText_carries_the_runs_comment_ids():
    tree = _parse_tree(_one_block_doc(_text("t", "root", [
        _run("commented", bold=True, comment_ids=[REAL_ID]),
    ])))
    run = _inlines(_first(tree, "t"))[0]
    assert isinstance(run, StyledText)
    assert run.comment_ids == [REAL_ID]


def test_an_UNSTYLED_run_whose_style_carries_ONLY_comment_ids_reaches_StyledText():
    """**AC4, the characterized edge (Dev's documented call).**

    ``_text_run_node`` returns ``Text`` when the run has **no** ``text_element_style``, so
    the open question was a run whose style object carries *only* ``comment_ids`` and no
    style flags. Answer, established against the pinned SDK rather than assumed: the SDK
    deserializes any present ``text_element_style`` — even ``{}`` — into a real
    ``TextElementStyle`` **object**, and a plain object is truthy, so ``if not style`` is
    False and the run reaches ``StyledText`` with every flag falsy. The ids therefore land
    on the model with **no** node-selection change and **no** ``comment_ids`` field on
    ``Text``.

    (An unstyled ``StyledText`` also renders exactly like a bare ``Text`` — the renderer
    pins that already — which is why this edge costs no output bytes either.)
    """
    tree = _parse_tree(_one_block_doc(_text("t", "root", [
        _run("commented", comment_ids=[REAL_ID]),
    ])))
    run = _inlines(_first(tree, "t"))[0]
    assert isinstance(run, StyledText)
    assert run.comment_ids == [REAL_ID]
    assert (run.bold, run.italic, run.strikethrough, run.underline,
            run.inline_code, run.link_url) == (False, False, False, False, False, None)


def test_a_run_with_a_comment_AND_a_link_keeps_both():
    tree = _parse_tree(_one_block_doc(_text("t", "root", [
        _run("linked", link={"url": "https%3A%2F%2Fexample.test%2Fa"},
             comment_ids=[REAL_ID, REAL_ID_2]),
    ])))
    run = _inlines(_first(tree, "t"))[0]
    assert isinstance(run, StyledText)
    assert run.link_url == "https://example.test/a"
    assert run.comment_ids == [REAL_ID, REAL_ID_2]


def test_a_run_with_NO_style_object_maps_to_Text_and_has_no_ids_to_lose():
    """The other side of the characterization: a run with no ``text_element_style`` still
    maps to ``Text``. Nothing is lost there — ``comment_ids`` is a field on
    ``TextElementStyle``, so a run with no style object has no ids at all. ``Text``
    deliberately gains **no** ``comment_ids`` field."""
    tree = _parse_tree(_one_block_doc(_text("t", "root", [_run("plain")])))
    run = _inlines(_first(tree, "t"))[0]
    assert type(run) is Text
    assert "comment_ids" not in {f.name for f in dataclasses.fields(Text)}


def test_absent_and_present_but_empty_are_DISTINCT_at_WORD_level():
    tree = _parse_tree(_one_block_doc(_text("t", "root", [
        _run("no field", bold=True),
        _run("empty list", bold=True, comment_ids=[]),
    ])))
    absent, empty = _inlines(_first(tree, "t"))
    assert absent.comment_ids is None
    assert empty.comment_ids == []
    assert empty.comment_ids is not None


def test_word_level_ids_keep_the_APIs_ORDER_with_no_sort_and_no_dedup():
    ids = [REAL_ID_4, REAL_ID, REAL_ID_3, REAL_ID_2, REAL_ID]
    tree = _parse_tree(_one_block_doc(_text("t", "root", [
        _run("many", italic=True, comment_ids=ids),
    ])))
    got = _inlines(_first(tree, "t"))[0].comment_ids
    assert got == ids
    assert got != sorted(got)
    assert len(got) == 5


def test_BOTH_granularities_on_ONE_block_do_not_shadow_each_other():
    """The amplifier's headline case: a block-level id **and** two runs each carrying
    *different* word-level ids, on one block. An implementation that captures one
    granularity and shadows the other cannot pass this."""
    tree = _parse_tree(_one_block_doc(_text("t", "root", [
        _run("first ", bold=True, comment_ids=[REAL_ID_2]),
        _run("second", italic=True, comment_ids=[REAL_ID_3, REAL_ID_4]),
    ], comment_ids=[REAL_ID])))
    node = _first(tree, "t")
    assert node.comment_ids == [REAL_ID]
    assert [r.comment_ids for r in _inlines(node)] == [
        [REAL_ID_2], [REAL_ID_3, REAL_ID_4]
    ]


def test_the_LIVE_CAPTURED_run_shapes_land_on_the_model():
    """The real captured payload: the probe's live three-run paragraph, whose middle run
    carries ``bold: true`` **and** a ``comment_ids`` list, with the neighbours carrying the
    ``bold: false`` style objects Lark really returns."""
    runs_in = _CAPTURED_RUNS
    assert any("comment_ids" in (r["text_run"].get("text_element_style") or {})
               for r in runs_in), "the capture no longer carries an inline comment id"
    tree = _parse_tree(_one_block_doc(
        {"block_id": "t", "parent_id": "root", "block_type": 2,
         "text": {"elements": runs_in}, "children": []}
    ))
    runs_out = _inlines(_first(tree, "t"))
    assert [type(r) for r in runs_out] == [StyledText] * 3
    assert [r.comment_ids for r in runs_out] == [None, [_CAPTURED_RUN_ID], None]
    assert [r.bold for r in runs_out] == [False, True, False]


# --------------------------------------------------------------------------- #
# 4. Nesting — a pipe cell, a merged (HTML) cell, a nested list item.           #
# --------------------------------------------------------------------------- #

def _pipe_table_doc(inner):
    return [page("tbl"), table("tbl", "root", 1, ["c0"]),
            cell("c0", "tbl", [inner["block_id"]]), inner]


def _merged_table_doc(cell0_blocks, cell0_comment_ids=None):
    """A 2x2 table with a rowspan on cell 0, so the HTML ``<table>`` path is taken."""
    merge_info = [{"row_span": 2, "col_span": 1}, {"row_span": 1, "col_span": 1},
                  {"row_span": 1, "col_span": 1}, {"row_span": 1, "col_span": 1}]
    prop = {"row_size": 2, "merge_info": merge_info, "header_row": False}
    ids = ["c0", "c1", "c2", "c3"]
    blocks = [page("tbl"), table("tbl", "root", 2, ids, prop)]
    c0 = cell("c0", "tbl", [b["block_id"] for b in cell0_blocks])
    if cell0_comment_ids is not None:
        c0["comment_ids"] = list(cell0_comment_ids)
    blocks.append(c0)
    blocks.extend(cell0_blocks)
    for cid, txt in zip(ids[1:], ("B", "C", "D")):
        blocks.append(cell(cid, "tbl", [f"{cid}t"]))
        blocks.append(_text(f"{cid}t", cid, [_run(txt)]))
    return blocks


def test_ids_survive_inside_a_PIPE_table_cell():
    inner = _text("p0", "c0", [_run("in cell", bold=True, comment_ids=[REAL_ID_2])],
                  comment_ids=[REAL_ID])
    tree = _parse_tree(_pipe_table_doc(inner))
    node = _first(tree, "p0")
    assert node.comment_ids == [REAL_ID]
    assert _inlines(node)[0].comment_ids == [REAL_ID_2]


def test_ids_survive_inside_a_MERGED_table_cell():
    inner = _text("p0", "c0", [_run("merged", bold=True, comment_ids=[REAL_ID_2])],
                  comment_ids=[REAL_ID_3])
    tree = _parse_tree(_merged_table_doc([inner], cell0_comment_ids=[REAL_ID]))
    assert _first(tree, "c0").comment_ids == [REAL_ID]
    assert _first(tree, "p0").comment_ids == [REAL_ID_3]
    assert _inlines(_first(tree, "p0"))[0].comment_ids == [REAL_ID_2]


def test_ids_survive_inside_a_NESTED_list_item():
    blocks = [
        page("b1"),
        _text("b1", "root", [_run("outer", comment_ids=[REAL_ID_2])],
              comment_ids=[REAL_ID], block_type=12, key="bullet", children=["b2"]),
        _text("b2", "b1", [_run("inner", comment_ids=[REAL_ID_4])],
              comment_ids=[REAL_ID_3], block_type=12, key="bullet"),
    ]
    tree = _parse_tree(blocks)
    assert _first(tree, "b1").comment_ids == [REAL_ID]
    assert _first(tree, "b2").comment_ids == [REAL_ID_3]
    assert _inlines(_first(tree, "b2"))[0].comment_ids == [REAL_ID_4]


# --------------------------------------------------------------------------- #
# 5. AC5 — NODE-TYPE SELECTION IS UNCHANGED.                                    #
# --------------------------------------------------------------------------- #

_INPUTS = sorted(FIXTURES_DIR.glob("*.input.json"))
_CASE_IDS = [p.name[: -len(".input.json")] for p in _INPUTS]


def _inject(value, block_ids, run_ids, create_style):
    """Deep-copy ``value``, stamping ``comment_ids`` onto every block dict and every
    ``text_run``'s style.

    ``create_style`` also *creates* a style object on a run that had none — the aggressive
    shape, which must still cost zero output bytes.
    """
    if isinstance(value, list):
        return [_inject(v, block_ids, run_ids, create_style) for v in value]
    if not isinstance(value, dict):
        return value
    out = {k: _inject(v, block_ids, run_ids, create_style) for k, v in value.items()}
    if "block_type" in out and "block_id" in out:
        out["comment_ids"] = list(block_ids)
    run = out.get("text_run")
    if isinstance(run, dict) and ("text_element_style" in run or create_style):
        style = dict(run.get("text_element_style") or {})
        style["comment_ids"] = list(run_ids)
        run["text_element_style"] = style
    return out


def _node_shape(node):
    """The node-CLASS skeleton of a tree — types only, no payload."""
    return (
        type(node).__name__,
        tuple(type(i).__name__ for i in _inlines(node)),
        tuple(_node_shape(c) for c in _kids(node)),
    )


@pytest.mark.parametrize("input_path", _INPUTS, ids=_CASE_IDS)
def test_node_type_selection_is_unchanged_across_the_whole_corpus(input_path):
    """AC5: the capture must not re-shape the tree. For every golden fixture, the sequence
    of node CLASSES (block and inline) is identical with and without ids injected — so a
    plain run still maps to ``Text`` and a styled run still to ``StyledText``."""
    base = json.loads(input_path.read_text(encoding="utf-8"))
    doc_id = base[0]["block_id"]
    before = _node_shape(_parse_tree(base, doc_id))
    after = _node_shape(_parse_tree(
        _inject(base, [REAL_ID], [REAL_ID_2], create_style=False), doc_id))
    assert before == after


def test_the_documented_node_selection_RULE():
    """The rule AC4 established, pinned as a table so it cannot drift silently. Note the
    last row: a *present but empty* style object already reached ``StyledText`` before this
    issue, and still does — that is pre-existing behavior this capture does not touch."""
    tree = _parse_tree(_one_block_doc(_text("t", "root", [
        _run("no style at all"),
        _run("style with only a comment", comment_ids=[REAL_ID]),
        _run("style with a flag", bold=True),
        _run_with_empty_style("present but empty style"),
    ])))
    assert [type(r).__name__ for r in _inlines(_first(tree, "t"))] == [
        "Text", "StyledText", "StyledText", "StyledText",
    ]


# --------------------------------------------------------------------------- #
# 6. AC6 — ZERO-DRIFT, in-suite. The corpus rendered WITH ids must byte-match.  #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("input_path", _INPUTS, ids=_CASE_IDS)
def test_the_golden_corpus_is_byte_identical_with_ids_on_every_block_and_run(input_path):
    """The hard criterion, made executable inside the suite rather than only proved by an
    untouched ``.expected.md``: inject ``comment_ids`` into **every** block and **every**
    already-styled run of every fixture and re-render. Not one byte may move."""
    case = input_path.name[: -len(".input.json")]
    expected = (FIXTURES_DIR / f"{case}.expected.md").read_text(encoding="utf-8")
    base = json.loads(input_path.read_text(encoding="utf-8"))
    injected = _inject(base, [REAL_ID, REAL_ID_2], [REAL_ID_3], create_style=False)
    assert render(injected, base[0]["block_id"]) == expected


@pytest.mark.parametrize("input_path", _INPUTS, ids=_CASE_IDS)
def test_byte_identical_even_when_a_STYLE_OBJECT_IS_CREATED_for_the_comment(input_path):
    """The aggressive variant: a comment lands on a run that had no ``text_element_style``
    at all, so the payload gains one. That flips the run from ``Text`` to an **unstyled**
    ``StyledText`` — and an unstyled ``StyledText`` is pinned to render exactly like a bare
    ``Text``, so the projection still may not move."""
    case = input_path.name[: -len(".input.json")]
    expected = (FIXTURES_DIR / f"{case}.expected.md").read_text(encoding="utf-8")
    base = json.loads(input_path.read_text(encoding="utf-8"))
    injected = _inject(base, [REAL_ID], [REAL_ID_2], create_style=True)
    assert render(injected, base[0]["block_id"]) == expected


def test_the_golden_corpus_still_carries_no_comment_ids():
    """AC8's finding, kept executable — and the pin that no golden was re-baselined by this
    work: no file under ``tests/fixtures/`` mentions the field."""
    hits = [p.name for p in sorted(FIXTURES_DIR.iterdir()) if p.is_file()
            and "comment_ids" in p.read_text(encoding="utf-8", errors="ignore")]
    assert not hits, f"a fixture now carries comment_ids: {hits}"


# --------------------------------------------------------------------------- #
# 7. AC7 — the renderer NEVER emits a comment id, on EITHER dispatch.           #
# --------------------------------------------------------------------------- #

def _assert_no_id(out):
    for bad in _ALL_IDS + (_CAPTURED_RUN_ID,):
        assert bad not in out, f"the renderer leaked comment id {bad}:\n{out}"


@pytest.mark.parametrize("use_html_tags", [False, True])
def test_the_renderer_emits_no_comment_id_at_either_granularity(use_html_tags):
    """Fed nodes carrying ids directly (not via the parser), the ONE serializer must emit
    none of them — and the output must equal what the same nodes render to without ids."""
    renderer = MarkdownRenderer(use_html_tags=use_html_tags)
    with_ids = renderer.render(PageNode(
        title=[Text("T")],
        children=[TextNode(
            content=[StyledText(content="hi", bold=True,
                                comment_ids=[REAL_ID_2, REAL_ID_3])],
            comment_ids=[REAL_ID, REAL_ID_4],
        )],
        comment_ids=[REAL_ID],
    ))
    without = renderer.render(PageNode(
        title=[Text("T")],
        children=[TextNode(content=[StyledText(content="hi", bold=True)])],
    ))
    _assert_no_id(with_ids)
    assert with_ids == without


def test_the_HTML_CELL_dispatch_leaks_no_comment_id():
    """The second serializer: a merged table takes the HTML ``<td>`` path, which has its own
    cell renderer. It must not leak an id either — at block or word granularity."""
    inner = _text("p0", "c0", [_run("merged", bold=True, comment_ids=[REAL_ID_2])],
                  comment_ids=[REAL_ID_3])
    out = render(_merged_table_doc([inner], cell0_comment_ids=[REAL_ID]), "root")
    assert "<table>" in out, f"expected the HTML-table path:\n{out}"
    _assert_no_id(out)
    plain = _text("p0", "c0", [_run("merged", bold=True)])
    assert out == render(_merged_table_doc([plain]), "root")


def test_the_PIPE_cell_dispatch_leaks_no_comment_id():
    inner = _text("p0", "c0", [_run("cellular", italic=True, comment_ids=[REAL_ID_2])],
                  comment_ids=[REAL_ID])
    out = render(_pipe_table_doc(inner), "root")
    _assert_no_id(out)
    plain = _text("p0", "c0", [_run("cellular", italic=True)])
    assert out == render(_pipe_table_doc(plain), "root")


# --------------------------------------------------------------------------- #
# 8. AC9 — determinism.                                                         #
# --------------------------------------------------------------------------- #

def test_two_parses_of_the_same_payload_agree_in_model_AND_bytes():
    """Including an id order that looks non-deterministic: it is the API's order and is
    stored unchanged, so both parses see the same sequence."""
    ids = [REAL_ID_4, REAL_ID, REAL_ID_3, REAL_ID_2]
    blocks = _one_block_doc(_text("t", "root", [
        _run("a", bold=True, comment_ids=ids),
        _run("b", comment_ids=list(reversed(ids))),
    ], comment_ids=ids))
    first_tree = _parse_tree(blocks)
    second_tree = _parse_tree(blocks)
    assert first_tree == second_tree
    # node equality is blind to the block-level field by design, so compare it explicitly
    assert ([n.comment_ids for n in _walk(first_tree)]
            == [n.comment_ids for n in _walk(second_tree)])
    # ``getattr`` because a plain ``Text`` (the page title's run) deliberately has no
    # such field at all — that absence is itself part of the characterized rule.
    assert ([getattr(r, "comment_ids", None) for n in _walk(first_tree) for r in _inlines(n)]
            == [getattr(r, "comment_ids", None) for n in _walk(second_tree) for r in _inlines(n)])
    assert render(blocks, "root") == render(blocks, "root")


def test_a_reused_parser_does_not_leak_ids_between_parses():
    parser = Parser(Config())
    with_ids = build_blocks(_one_block_doc(
        _text("t", "root", [_run("x", comment_ids=[REAL_ID])], comment_ids=[REAL_ID])
    ))
    # the second payload's run is styled (so it is a StyledText that COULD hold ids)
    # but carries none — nothing may bleed across from the first parse
    without = build_blocks(_one_block_doc(_text("t", "root", [_run("x", bold=True)])))
    parser.parse_docx_tree("root", with_ids)
    tree = parser.parse_docx_tree("root", without)
    assert _first(tree, "t").comment_ids is None
    run = _inlines(_first(tree, "t"))[0]
    assert isinstance(run, StyledText)
    assert run.comment_ids is None


# --------------------------------------------------------------------------- #
# 9. AC10 — NO public read surface, NO join, NO rendering.                      #
# --------------------------------------------------------------------------- #

def test_the_public_package_surface_is_unchanged():
    import larkdocio

    assert larkdocio.__all__ == [
        # `release_notes` / `changelog` are the accessors for the two release documents the
        # wheel already carried with no way to open them; the pin is widened deliberately,
        # and neither is a read surface.
        # `guide_sections` is the shipped guide's section index, added beside `guide` so a
        # caller can ask for one section of a 200 KB document instead of all of it. The pin is
        # widened deliberately, and it is emphatically not a read surface: it reads a packaged
        # resource, reaches no Lark document and touches no comment.
        # `writer_brief_sections` / `release_notes_sections` / `changelog_sections` (LD-414)
        # generalize that same section index to the other three packaged documents — same
        # non-read-surface reasoning, same widened pin.
        # `lark_setup` / `lark_setup_sections` (LD-549) are the accessor and section index for
        # the Lark-application walkthrough — the fifth packaged consumer document, and the one
        # a brand-new consumer needs first. Same non-read-surface reasoning again, same widened
        # pin: it reads a packaged resource, reaches no Lark document and touches no comment.
        "__version__", "capabilities", "guide", "guide_sections", "writer_brief",
        "writer_brief_sections", "release_notes", "release_notes_sections", "changelog",
        # `compose_check` (LD-518) is the read-only batch checker beside `compose`: it reports
        # every construct a fragment cannot express instead of stopping at the first. The pin
        # is widened deliberately, and it is as far from a read surface as `compose` itself —
        # it compiles a string offline, holds no client and no credential, reaches no Lark
        # document and touches no comment.
        "changelog_sections", "lark_setup", "lark_setup_sections", "compose", "compose_check",
        "compose_insert",
        # `preflight` / `check_permissions` are the advisory permission pre-check, which
        # already existed and was already documented — it was reachable by module path and
        # missing from this list, which is why a consumer could only find it by full-text
        # search. Widened deliberately (LD-208). It reads NO document and NO comment: it
        # probes scope gates against deliberately nonexistent ids, so it is not a read
        # surface either, which is what this test is here to hold.
        "preflight", "check_permissions",
    ]


def test_the_read_package_exports_are_unchanged():
    """The read package declares no export list (unchanged) and grew no module. Pinned on
    the package's FILES rather than on ``dir()``, which reflects whatever other tests
    happened to import first and so would make this order-dependent."""
    import larkdocio.read as read_pkg

    assert getattr(read_pkg, "__all__", None) is None
    modules = sorted(p.name for p in
                     (REPO_ROOT / "src" / "larkdocio" / "read").rglob("*.py"))  # LD-654: recursive
    assert modules == [
        "__init__.py", "client.py", "config.py", "config_cmd.py", "download.py",
        # LD-410: the docx historical read's pin gate, its metadata half and the three
        # measured disclosures around ``document_revision_id``. Same shape as the two
        # modules below — internal to the read package, reached through the read client's
        # own signature, and __all__ on the package is still absent.
        "history.py",
        # LD-173: the @mention substitution moved OUT of download.py into its own module so
        # the download pipeline and the Parser read-client seam call ONE implementation
        # (structural CLI-vs-Python parity). It exports no public package surface — this
        # list is still the whole read package, and __all__ is still absent.
        "mentions.py",
        "parser.py",
        # LD-334: the unfetched-references queue + its end-of-download summary. Same shape
        # as mentions.py above — an internal module of the read package, no public package
        # surface added, __all__ still absent.
        "references.py",
    ]


def test_the_model_exports_gained_no_new_node_type():
    from larkdocio import model

    # Counted over the exported NODE TYPES, which is what this guard is about. The model
    # package also exports plain functions (the tree-reading helpers, the block-identity
    # projection and its inverse) and two classes that are not nodes (the renderer and the
    # projection's result value), so a raw ``len(__all__)`` — or even a count of every
    # exported class — would report one of those as a new node type.
    types = [
        n for n in model.__all__
        if isinstance(getattr(model, n), type)
        and issubclass(getattr(model, n), (model.Node, model.Inline))
    ]
    assert len(types) == 43, types
    assert not [n for n in model.__all__ if "omment" in n]


def test_the_READER_still_carries_no_comments_accessor():
    """The scope fence, re-pointed at what it was really protecting (LD-159).

    Its original form said "no comments accessor exists anywhere", which was the right fence
    while the anchors had no consumer: this issue captured ids and deliberately stopped there.
    A typed comments read has since shipped as its **own** surface, so the blanket would now
    forbid shipped behaviour instead of guarding anything.

    What it was actually protecting is the boundary, and that is asserted here at full
    strength: the document reader and its parser gained NO comments accessor, so converting a
    document still makes no comment call and produces no comment text. The comments read lives
    in a separate module a caller reaches for on purpose — which is also why the
    ``no_comments_api_call_is_reachable_from_the_read_path`` test below still passes untouched.
    """
    import larkdocio.read.client as read_client

    for surface in (read_client, Parser, read_client.Client):
        assert not [n for n in dir(surface) if "comment" in n.lower()], surface

    # The one name the package itself gained is the SUBMODULE — not a reader method, and not
    # re-exported into the top-level API's ``__all__``.
    import larkdocio

    assert "comments" not in larkdocio.__all__
    assert [n for n in dir(larkdocio) if "comment" in n.lower()] == ["comments"]
    import types

    assert isinstance(larkdocio.comments, types.ModuleType)


def test_no_comments_api_call_is_reachable_from_the_read_path():
    """No join here: nothing on the read path names the comments endpoint or its join
    verb."""
    offenders = []
    for part in ("read", "blocks", "model"):
        for path in sorted((REPO_ROOT / "src" / "larkdocio" / part).rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for token in ("batch_query", "/comments", "comment_replies"):
                if token in text:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {token}")
    assert not offenders, offenders
