"""THE SUB-SPAN / TEXT-ANCHOR REFUSAL NAMES THE NODE CLASS — and stops lying about children.

Two refusals on the same branch were true about the span and false about the document — the
shape ``write/apply.py``'s ``_subspan_not_splittable_detail`` docstring calls the lying-refusal
defect:

* a sub-span refusal on a ``PageNode`` **whose ``title`` IS the quoted text** returned a
  kind-less ``not_found`` ("the span does not occur in the text runs of block pg1"), which is
  true about the sub-span splitting basis and reads as false about the page;
* a ``RawBlock`` — whose own text is its ``markup`` and which has **no children at all** — was
  told it is a ``CONTAINER`` whose "text lives in its child blocks", with the advice "target the
  text-bearing child block's id", which cannot succeed. Root cause: ``write.resolve``'s
  ``_own_text_source`` does not consult the ``markup`` fallback ``model.plain_text`` does, so the
  block reads as a pure container.

The fix APPENDS an arm to each site. The other half of this module is therefore the
byte-unchanged half: the pre-existing container / by-id write-hostile / diagram / shared
not-found details are pinned as expected-string constants captured BEFORE the change, so an
"improvement" to a shared message reddens here rather than reaching a consumer.
"""
import dataclasses
import importlib

import pytest

from larkdocio import model as M
from larkdocio.model import PageNode, RawBlock, Text, TextNode
from larkdocio.model.node_docs import _field_names, has_own_text, node_classes
from larkdocio.write import resolve
from larkdocio.write.model import AnchorById, RefusalReason, SubSpanEditRequest

#: The MODULE, not the shipped `resolve` FUNCTION of the same name — the fence assertions read
#: module-level constants that the function does not carry.
R = importlib.import_module("larkdocio.write.resolve")


# --------------------------------------------------------------------------- #
# The BYTE-UNCHANGED half — every string below was captured from the shipped    #
# code BEFORE this issue's arms were appended. A diff here is a defect in the   #
# change, never a fixture to update.                                           #
# --------------------------------------------------------------------------- #

CONTAINER_DETAIL = (
    "block_id {bid!r} resolved to block {bid}, a {cls} — a CONTAINER block that carries no "
    "text of its own (its text lives in its child blocks), so a whole-block text replacement "
    "has nothing to patch. Target the text-bearing child block's id instead, or use a "
    "TableLocator (row-key + column) for a table cell"
)

BY_ID_WRITE_HOSTILE_DETAIL = (
    "block_id {bid!r} resolved to a {cls} — image / board / embed / synced content is not "
    "text-patchable, so it can be neither edited nor used as an insertion reference. The id "
    "WAS found, so a different id is the repair, not a different anchor kind; anchor to a "
    "narrative block instead"
)

DIAGRAM_DETAIL = (
    "block_id {bid!r} resolved to block {bid}, a diagram add-on (docx block type 40). A "
    "diagram is CREATABLE but has NO IN-PLACE UPDATE: the docx block-patch surface carries no "
    "add_ons updater at all, so its source cannot be patched. Change it by DELETE + RE-CREATE "
    "at the same index — insert a NewBlock.mermaid(...) positioned BEFORE this block, then "
    "delete this block, both through the ordinary dry_run/apply gate. Note the cost: the "
    "replacement gets a NEW block_id, so do not cache a diagram's block_id across an edit — "
    "re-resolve after one"
)

SHARED_NOT_FOUND_DETAIL = (
    "the span {span!r} does not occur in the text runs of block {bid} (resolved from block_id "
    "{bid!r}) — a sub-span edit's span must be verbatim text of that block"
)


def _subspan(node, span, *, root=None):
    """Resolve a by-id sub-span edit of ``span`` against ``node`` inside a one-page tree."""
    if root is None:
        root = PageNode(block_id="root", title=[Text(content="Doc")], children=[node])
    return resolve(
        SubSpanEditRequest(anchor=AnchorById(block_id=node.block_id), span=span,
                           replacement="X"),
        root,
    )


def _page(span_text="Q3 Revenue Review"):
    return PageNode(block_id="pg1", title=[Text(content=span_text)], children=[])


def _raw(markup="some raw markup here"):
    return RawBlock(block_id="rb1", block_type=999, markup=markup)


# --------------------------------------------------------------------------- #
# 1. THE PAGE NODE — a kind-less not_found on text that is plainly on the page  #
# --------------------------------------------------------------------------- #

def test_subspan_not_found_on_a_page_title_names_the_node_class():
    """The span IS the page's title, so the refusal must name the class and its text home."""
    page = _page()
    refusal = _subspan(page, "Revenue")

    assert refusal.reason is RefusalReason.NOT_FOUND, refusal
    detail = refusal.detail
    assert "PageNode" in detail, detail
    assert "title" in detail, detail
    # It must not read as "those words are not in this document".
    assert detail != SHARED_NOT_FOUND_DETAIL.format(span="Revenue", bid="pg1")


def test_subspan_not_found_on_a_page_title_points_at_the_guide_not_a_second_rule():
    """The basis rule is authored in the shipped guide; the refusal cites it."""
    detail = _subspan(_page(), "Revenue").detail
    assert "larkdocio.guide()" in detail, detail
    assert "content" in detail, detail


def test_shared_subspan_not_found_is_byte_unchanged_when_the_span_is_absent_everywhere():
    """A span that is in NO text home keeps the shipped message, byte for byte."""
    node = TextNode(block_id="tx1", content=[Text(content="hello world")])
    assert _subspan(node, "Revenue").detail == SHARED_NOT_FOUND_DETAIL.format(
        span="Revenue", bid="tx1")

    page = PageNode(block_id="pg1", title=[Text(content="Q3 Review")], children=[])
    assert _subspan(page, "Revenue").detail == SHARED_NOT_FOUND_DETAIL.format(
        span="Revenue", bid="pg1")


# --------------------------------------------------------------------------- #
# 2. THE RAW BLOCK — a container claim about a block with no children          #
# --------------------------------------------------------------------------- #

def test_raw_block_refusal_does_not_claim_it_is_a_container_with_children():
    refusal = _subspan(_raw(), "raw markup")

    assert refusal.reason is RefusalReason.WRITE_HOSTILE, refusal
    detail = refusal.detail
    assert "CONTAINER" not in detail, detail
    # The words the shared container message uses to make the false claim — absent outright,
    # not merely negated, so the issue's own binary check is what this asserts.
    assert "child blocks" not in detail, detail
    assert "its text lives in its child blocks" not in detail, detail
    assert "Target the text-bearing child block's id instead" not in detail, detail
    assert detail != CONTAINER_DETAIL.format(bid="rb1", cls="RawBlock")
    # And it says the true thing in its place: there is no child to target.
    assert "no child" in detail, detail


def test_raw_block_refusal_names_the_class_and_where_its_text_really_lives():
    detail = _subspan(_raw(), "raw markup").detail
    assert "RawBlock" in detail, detail
    assert "markup" in detail, detail
    assert "larkdocio.guide()" in detail, detail


def test_raw_block_whole_block_edit_refusal_takes_the_same_arm():
    """The arm sits on the shared text-anchor seam, so a whole-block edit says it too."""
    from larkdocio.write.model import EditRequest

    raw = _raw()
    root = PageNode(block_id="root", title=[Text(content="Doc")], children=[raw])
    refusal = resolve(EditRequest(anchor=AnchorById(block_id="rb1"),
                                  replacement="X"), root)
    assert refusal.reason is RefusalReason.WRITE_HOSTILE, refusal
    assert "CONTAINER" not in refusal.detail, refusal.detail
    assert "RawBlock" in refusal.detail, refusal.detail


# --------------------------------------------------------------------------- #
# 3. THE BYTE-UNCHANGED HALF — real containers, the fenced kinds, the diagram   #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("node,cls", [
    (M.TableNode(block_id="tb1", cells=[], merges=[]), "TableNode"),
    (M.TableCellNode(block_id="tc1", children=[]), "TableCellNode"),
    (M.GridNode(block_id="gd1", columns=[]), "GridNode"),
    (M.CalloutNode(block_id="co1", children=[]), "CalloutNode"),
    (M.QuoteContainerNode(block_id="qc1", children=[]), "QuoteContainerNode"),
])
def test_a_real_containers_refusal_is_byte_unchanged(node, cls):
    refusal = _subspan(node, "Revenue")
    assert refusal.reason is RefusalReason.WRITE_HOSTILE, refusal
    assert refusal.detail == CONTAINER_DETAIL.format(bid=node.block_id, cls=cls)


@pytest.mark.parametrize("node,cls", [
    (M.ImageNode(block_id="im1", token="t", caption="Revenue caption"), "ImageNode"),
    (M.IframeNode(block_id="if1", url="https://example.com/Revenue"), "IframeNode"),
])
def test_the_fenced_kinds_refusal_is_byte_unchanged(node, cls):
    """ImageNode / IframeNode are already write-hostile and already name the kind."""
    refusal = _subspan(node, "Revenue")
    assert refusal.reason is RefusalReason.WRITE_HOSTILE, refusal
    assert refusal.detail == BY_ID_WRITE_HOSTILE_DETAIL.format(bid=node.block_id, cls=cls)


def test_the_diagram_arms_refusal_is_byte_unchanged():
    node = M.AddOnsNode(block_id="ao1", mermaid_source="graph TD")
    refusal = _subspan(node, "Revenue")
    assert refusal.reason is RefusalReason.WRITE_HOSTILE, refusal
    assert refusal.detail == DIAGRAM_DETAIL.format(bid="ao1")


# --------------------------------------------------------------------------- #
# 4. THE SCOPE FENCE — the census this issue was re-derived from, as a guard    #
# --------------------------------------------------------------------------- #

def test_the_off_content_text_home_census_is_four_classes_two_of_them_fenced():
    """The residue is TWO nodes, not four: image / iframe are already fenced.

    A class joining or leaving either half is a capability change, and it reddens here so it
    cannot arrive as a silent rescope of this refusal text.
    """
    census = {c.__name__: issubclass(c, R.WRITE_HOSTILE_NODE_TYPES)
              for c in node_classes()
              if has_own_text(c) and "content" not in set(_field_names(c))}
    assert census == {"IframeNode": True, "ImageNode": True,
                      "PageNode": False, "RawBlock": False}


def test_write_hostile_node_types_membership_is_unchanged():
    assert tuple(c.__name__ for c in R.WRITE_HOSTILE_NODE_TYPES) == (
        "ImageNode", "BoardNode", "IframeNode", "BitableNode", "SheetNode",
        "ReferenceBaseNode", "SourceSyncedNode", "ReferenceSyncedNode",
    )


def test_a_raw_block_really_has_no_child_sequence_to_target():
    """The falsifier for the arm's central claim: there is no child field to point at."""
    fields = {f.name for f in dataclasses.fields(RawBlock)}
    assert not fields & {"children", "cells", "columns"}, fields
