"""LD-567 AC4 — the guide's node-class index: a GENERATED table asking, per class, the two
questions SEPARATELY (does ``plain_text`` return its own text; does ``walk`` descend into it),
never a binary container/own-text split.

**What is actually held here is the authoring model, not the prose**, on the
``base/shape_docs.py`` precedent (``tests/test_base_shape_docs.py``): a shape claim is authored
once, in :mod:`larkdocio.model.node_docs`, and every landing of it in a document is a
byte-identical projection of that one author — so a class the model gains or loses moves the
guide's table on its own, checked BOTH ways: a new ``Node`` subclass with no row reddens, and a
row naming a class the model no longer has reddens too.
"""
import dataclasses

import pytest

from larkdocio import guide
from larkdocio.model import nodes as model_nodes
from larkdocio.model.nodes import Node
from larkdocio.model.node_docs import (
    NODE_CLASS_REGENERATE,
    NODE_CLASS_REGION_BEGIN,
    NODE_CLASS_REGION_END,
    has_own_text,
    node_class_markdown,
    node_classes,
    walk_descends,
)
from larkdocio.permissions import region_of


def _region():
    return region_of(guide(full=True), NODE_CLASS_REGION_BEGIN.replace(" -->", ""),
                     NODE_CLASS_REGION_END)


def _all_model_node_subclasses():
    """Every concrete ``Node`` subclass the shipped model has — the independent enumeration
    :func:`node_classes` is checked against, so the two cannot agree by construction."""
    return {
        obj for name in dir(model_nodes)
        if isinstance(obj := getattr(model_nodes, name), type)
        and issubclass(obj, Node) and obj is not Node
    }


# --------------------------------------------------------------------------- #
# AC4 — the index ships, is reachable, and is byte-identical to the projection. #
# --------------------------------------------------------------------------- #

def test_the_region_exists_in_the_shipped_guide():
    region = _region()
    assert region, "the guide carries no generated node-class-index region"


def test_the_region_is_BYTE_IDENTICAL_to_the_projection():
    region = _region()
    assert region == node_class_markdown(), (
        "the guide's node-class-index region has drifted from larkdocio.model.node_docs — "
        f"regenerate it with: {NODE_CLASS_REGENERATE}"
    )


def test_exactly_one_begin_and_one_end_fence_in_order():
    text = guide(full=True)
    begin = NODE_CLASS_REGION_BEGIN.replace(" -->", "")
    assert text.count(begin) == 1, "expected exactly one BEGIN fence"
    assert text.count(NODE_CLASS_REGION_END) == 1, "expected exactly one END fence"
    assert text.index(begin) < text.index(NODE_CLASS_REGION_END)


def test_the_region_carries_its_own_regeneration_command():
    assert NODE_CLASS_REGENERATE in _region()


# --------------------------------------------------------------------------- #
# AC4 — bidirectional coverage: no class with no row, no row with no class.      #
# --------------------------------------------------------------------------- #

def test_every_shipped_node_subclass_has_a_row():
    region = _region()
    missing = [cls.__name__ for cls in _all_model_node_subclasses()
               if f"`{cls.__name__}`" not in region]
    assert not missing, f"these Node subclasses have no row in the generated index: {missing}"


def test_every_row_names_a_real_node_subclass():
    import re

    region = _region()
    named = set(re.findall(r"\| `([A-Za-z]+)` \|", region))
    real = {cls.__name__ for cls in _all_model_node_subclasses()}
    phantom = named - real
    assert not phantom, f"the index names classes the model does not have: {phantom}"


def test_node_classes_matches_the_independent_enumeration_both_ways():
    assert {c.__name__ for c in node_classes()} == {
        c.__name__ for c in _all_model_node_subclasses()
    }


# --------------------------------------------------------------------------- #
# AC4 — the taxonomy is a genuine two-question split, not a relabelled binary.  #
# --------------------------------------------------------------------------- #

def test_at_least_one_class_answers_no_to_both_questions():
    """The whole reason AC4 exists: a binary container/own-text split cannot represent a class
    that answers no to both, and at least one real class does."""
    neither = [cls for cls in node_classes()
               if not has_own_text(cls) and not walk_descends(cls)]
    assert neither, "no class answers 'no' to both questions — the two-question design is untested"


@pytest.mark.parametrize("name", [
    "DividerNode", "GridColumnNode", "BoardNode", "AddOnsNode", "FileNode",
    "ReferenceSyncedNode", "BitableNode", "SheetNode", "ReferenceBaseNode",
])
def test_the_nine_classes_named_by_the_mint_ruling_answer_no_to_both(name):
    """FIX-PROGRAM-SCRUTINY named these nine as the reason a binary split is false — pinned
    individually so a future change to any one of them is a deliberate, reviewed edit."""
    cls = getattr(model_nodes, name)
    assert not has_own_text(cls), f"{name} now has own text — the taxonomy moved"
    assert not walk_descends(cls), f"{name} now has a container field — the taxonomy moved"


def test_table_and_table_cell_answer_no_own_text_yes_descends():
    """The specific defect this issue closes: a table and a table cell are containers whose
    OWN reduction is empty — never a class that answers yes to own-text."""
    from larkdocio.model.nodes import TableCellNode, TableNode

    for cls in (TableNode, TableCellNode):
        assert not has_own_text(cls), f"{cls.__name__} unexpectedly carries its own text"
        assert walk_descends(cls), f"{cls.__name__} unexpectedly carries no container field"


def test_heading_node_answers_yes_to_both():
    """A sanity check on the "both" case the binary split also could not represent: a heading
    carries its own text AND children `walk` descends into."""
    from larkdocio.model.nodes import HeadingNode

    assert has_own_text(HeadingNode)
    assert walk_descends(HeadingNode)


# --------------------------------------------------------------------------- #
# AC4 — no public export moved; the generator stays reachable only by dotted   #
# import, exactly like base/shape_docs.py.                                     #
# --------------------------------------------------------------------------- #

def test_node_docs_module_has_no_all_and_is_not_reexported_from_model():
    import larkdocio.model as model
    import larkdocio.model.node_docs as node_docs

    assert not hasattr(node_docs, "__all__"), (
        "larkdocio.model.node_docs must carry NO __all__ entry — a public export here would "
        "move larkdocio.capabilities() bytes for a documentation generator"
    )
    for name in ("node_class_markdown", "node_classes", "has_own_text", "walk_descends"):
        assert not hasattr(model, name), (
            f"larkdocio.model re-exports {name!r} from node_docs — it must stay reachable only "
            f"by the dotted import larkdocio.model.node_docs"
        )


def test_tree_module_all_is_unchanged_by_this_issue():
    from larkdocio.model import tree

    assert tree.__all__ == ["walk", "plain_text"], (
        "tree.__all__ must stay exactly as it is — capabilities/_projections.py projects "
        "docx-read operations off it"
    )


# --------------------------------------------------------------------------- #
# AC4 — the generator reads tree.py's OWN field-name constants, never a second, #
# hand-typed copy (the F9 trap this issue was warned about).                    #
# --------------------------------------------------------------------------- #

def test_has_own_text_reads_trees_own_text_field_constants():
    """A class gaining a field named in `tree._TEXT_FIELD_NAMES` or
    `_TEXT_FALLBACK_FIELD_NAMES` must move `has_own_text` with NO edit to node_docs.py — proven
    by constructing a throwaway subclass with such a field and checking the answer follows."""
    from larkdocio.model import tree

    @dataclasses.dataclass
    class _ProbeCaption(Node):
        caption: str = ""

    assert has_own_text(_ProbeCaption)
    assert tree._TEXT_FALLBACK_FIELD_NAMES == ("caption", "url", "markup")


def test_walk_descends_reads_trees_own_container_field_constants():
    from larkdocio.model import tree

    @dataclasses.dataclass
    class _ProbeChildren(Node):
        children: list = dataclasses.field(default_factory=list)

    assert walk_descends(_ProbeChildren)
    assert tree._CHILD_SEQUENCE_FIELD_NAMES == ("children", "cells")
