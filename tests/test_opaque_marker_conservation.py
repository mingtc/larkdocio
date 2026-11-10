"""Opaque markers and the conservation contract (LD-231).

The projection LD-230 shipped marks every block. This module is about the blocks the
authoring dialect **cannot recreate** — an image, a synced block, a table, an unknown
type — which carry ``<!-- lark:block:<id> opaque=<kind> -->`` instead, and about the
contract that marker states: **conservation is the default posture; destruction is never
inferred** (the round-trip-editing spec § D3).

Two disciplines the tests here enforce rather than describe:

* **The opaque set is DERIVED, never listed.** It is a join of the reader's own handler
  registry, the writer's ``CREATABLE_BLOCK_TYPES``, and the per-type read-lossiness the
  package already ships — so a block type that becomes supported tomorrow lands on one
  side of the line by construction, not by someone remembering to edit a list.
* **The corpora are built here.** The prototype that measured marker survival lives under
  ``dev/marker-preservation-probes/`` and is a BLUEPRINT, never an import.
"""
import re

import pytest

from harness import build_blocks

from larkdocio.blocks import get_registry
from larkdocio.blocks.read_support import READ_SUPPORT
from larkdocio.model import project_block_ids
from larkdocio.model.conservation import (
    CONSERVATION_CONTRACT,
    _clear_caches,
    OPAQUE_CONSTRUCTS,
    PROJECTION_STATES,
    editable_block_types,
    opaque_block_types,
    opaque_kind,
    projection_support,
    unknown_opaque_kind,
)
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write.compose import NOT_EXPRESSIBLE_CONSTRUCTS
from larkdocio.write.encode import CREATABLE_BLOCK_TYPES

#: The test's OWN reader of a projected marker line — the independent second opinion the
#: assertions compare the emitted lists against. ``opaque`` is an OPTIONAL attribute, so
#: one regex covers both marker forms and "is this block opaque" is a group test rather
#: than a heuristic.
_MARKER_LINE = re.compile(
    r"^[ \t>]*<!-- lark:block:(\S+)(?: opaque=(\S+))? -->$"
)


def _markers_in(text):
    """``[(block_id, opaque_kind_or_None), ...]`` in document order."""
    return [
        (m.group(1), m.group(2))
        for m in (_MARKER_LINE.match(line) for line in text.split("\n"))
        if m
    ]


def _tree(block_dicts, doc_id=None):
    blocks = build_blocks(block_dicts)
    return Parser(Config()).parse_docx_tree(doc_id or block_dicts[0]["block_id"], blocks)


# --------------------------------------------------------------------------- #
# Corpus builders — one per amplifier case named in the spec story.              #
# --------------------------------------------------------------------------- #

def _page(bid="doc", children=()):
    return {
        "block_id": bid, "parent_id": "", "block_type": 1,
        "page": {"elements": [{"text_run": {"content": "Zoo"}}]},
        "children": list(children),
    }


def _text(bid, parent, content, children=()):
    return {
        "block_id": bid, "parent_id": parent, "block_type": 2,
        "text": {"elements": [{"text_run": {"content": content}}]},
        "children": list(children),
    }


def _image(bid, parent):
    return {
        "block_id": bid, "parent_id": parent, "block_type": 27,
        "image": {"token": "imgtok", "width": 10, "height": 10},
        "children": [],
    }


def _unknown(bid, parent, block_type=9999, children=()):
    return {
        "block_id": bid, "parent_id": parent, "block_type": block_type,
        "children": list(children),
    }


def _source_synced(bid, parent, content="synced origin"):
    return {
        "block_id": bid, "parent_id": parent, "block_type": 49,
        "source_synced": {"elements": [{"text_run": {"content": content}}]},
        "children": [],
    }


def _mermaid(bid, parent):
    return {
        "block_id": bid, "parent_id": parent, "block_type": 40,
        "add_ons": {
            "component_type_id": "blk_640017963d808005a21a6445",
            "component_id": "c1",
            "record": '{"data":"graph TD;A-->B;","theme":"default","view":"chart"}',
        },
        "children": [],
    }


def _cell(bid, parent, content):
    inner = _text(f"{bid}t", bid, content)
    return [
        {
            "block_id": bid, "parent_id": parent, "block_type": 32,
            "table_cell": {},
            "children": [inner["block_id"]],
        },
        inner,
    ]


def _table(bid, parent, rows=2, cols=2, merge_info=None):
    cells = []
    cell_ids = []
    for r in range(rows):
        for c in range(cols):
            cid = f"{bid}c{r}{c}"
            cell_ids.append(cid)
            cells.extend(_cell(cid, bid, f"r{r}c{c}"))
    property_ = {"row_size": rows, "column_size": cols}
    if merge_info is not None:
        property_["merge_info"] = merge_info
    return [
        {
            "block_id": bid, "parent_id": parent, "block_type": 31,
            "table": {"cells": cell_ids, "property": property_},
            "children": cell_ids,
        },
        *cells,
    ], cell_ids


def _merged_table(bid, parent):
    """A 2x2 table whose first cell spans both columns — the reader emits HTML for it."""
    merge_info = [
        {"row_span": 1, "col_span": 2},
        {"row_span": 1, "col_span": 1},
        {"row_span": 1, "col_span": 1},
        {"row_span": 1, "col_span": 1},
    ]
    return _table(bid, parent, merge_info=merge_info)


# --------------------------------------------------------------------------- #
# AC1 — the non-expressible set is enumerated from REAL CODE, and the two sides #
# of the line are complementary and exhaustive.                                 #
# --------------------------------------------------------------------------- #

def test_the_two_sides_are_complementary_and_exhaustive_over_the_registry():
    """AC1: every block type the reader registers is on exactly ONE side of the line."""
    registered = set(get_registry())
    editable, opaque = editable_block_types(), opaque_block_types()

    assert not (editable & opaque), (
        f"block types {sorted(editable & opaque)} are on BOTH sides of the "
        f"editable/opaque line."
    )
    unplaced = registered - editable - opaque
    assert not unplaced, (
        f"registered block types {sorted(unplaced)} fall through both sets — a newly "
        f"supported type must land on one side by construction."
    )


def test_a_newly_registered_type_cannot_fall_through_both(monkeypatch):
    """AC1: the sets are a live derivation, not a stored list — register a handler for a
    type nobody has ever seen and it is placed, without any list being edited."""
    registry = dict(get_registry())
    registry[9998] = lambda *a, **k: None
    monkeypatch.setattr("larkdocio.blocks.BLOCK_REGISTRY", registry, raising=True)
    _clear_caches()
    try:
        placed = editable_block_types() | opaque_block_types()
        assert 9998 in placed
        assert (9998 in editable_block_types()) != (9998 in opaque_block_types())
    finally:
        _clear_caches()


def test_editable_is_a_subset_of_what_the_writer_can_actually_create():
    """AC1: the editable side is derived from ``CREATABLE_BLOCK_TYPES`` — the projection
    can never invite an edit the authoring dialect could not compile back."""
    assert editable_block_types() <= set(CREATABLE_BLOCK_TYPES)


def test_a_creatable_type_the_reader_RESHAPES_is_still_opaque():
    """AC1: creatable is necessary, not sufficient. A table (31/32) and a mermaid add-on
    (40) are creatable, but the reader's Markdown for each is a RESHAPED projection of
    the block rather than the block's own content, so each is conserved."""
    for block_type in (31, 32, 40):
        assert block_type in CREATABLE_BLOCK_TYPES
        assert block_type in opaque_block_types(), block_type


def test_every_opaque_construct_reason_is_a_real_NOT_EXPRESSIBLE_CONSTRUCT():
    """AC1: where an opaque kind has a named counterpart in the compiler's closed refusal
    set, the join is pinned — a renamed construct key reddens here instead of leaving the
    projection quoting a reason the compiler no longer has."""
    unknown = {
        kind: construct
        for kind, construct in OPAQUE_CONSTRUCTS.items()
        if construct not in NOT_EXPRESSIBLE_CONSTRUCTS
    }
    assert not unknown, (
        f"opaque kinds {unknown} name constructs the compiler's closed set does not "
        f"carry — NOT_EXPRESSIBLE_CONSTRUCTS is the source of truth."
    )
    assert set(OPAQUE_CONSTRUCTS) <= {opaque_kind(t) for t in opaque_block_types()}


def test_the_support_table_answers_every_type_the_reader_knows_about():
    """AC1: the derivation covers the reader's whole world — every registered type and
    every documented one — with a state from the closed vocabulary."""
    support = projection_support()
    known = set(get_registry()) | {row[0] for row in READ_SUPPORT}
    assert known <= set(support)
    assert set(support.values()) <= set(PROJECTION_STATES)


# --------------------------------------------------------------------------- #
# AC2 — an opaque marker carries identity WITHOUT editable content.             #
# --------------------------------------------------------------------------- #

def test_an_image_projects_as_an_opaque_marker_naming_its_kind():
    """AC2 (and the amplifier's image case): LD-197 leg 1's proven form."""
    tree = _tree([_page(children=["img"]), _image("img", "doc")])
    projection = project_block_ids(tree)

    assert "<!-- lark:block:img opaque=image -->" in projection.markdown
    assert "img" in projection.block_ids
    assert "img" in projection.opaque_block_ids


def test_an_opaque_block_still_shows_its_human_readable_content():
    """AC2: opaque means "do not reconcile me", not "hide me" — the projection stays
    readable, so the image's own Markdown is still there under its marker."""
    tree = _tree([_page(children=["img"]), _image("img", "doc")])
    markdown = project_block_ids(tree).markdown

    assert "![](imgtok)" in markdown


def test_opacity_is_machine_detectable_without_heuristics():
    """AC2: the distinction is a named attribute in the marker AND a value on the
    projection — never something a caller has to infer from the block's content."""
    blocks, _ = _table("tbl", "doc")
    tree = _tree([_page(children=["p", "tbl"]), _text("p", "doc", "prose"), *blocks])
    projection = project_block_ids(tree)

    markers = dict(_markers_in(projection.markdown))
    assert markers["p"] is None
    assert markers["tbl"] == "table"
    assert set(projection.opaque_block_ids) == {
        bid for bid, kind in markers.items() if kind is not None
    }
    assert set(projection.opaque_block_ids) <= set(projection.block_ids)


def test_an_editable_block_carries_the_bare_marker_LD_230_shipped():
    """AC2 / the LD-230 boundary: the opaque attribute is strictly ADDITIVE — an editable
    block's marker is byte-identical to the form that shipped."""
    tree = _tree([_page(children=["p"]), _text("p", "doc", "prose")])
    assert "<!-- lark:block:p -->" in project_block_ids(tree).markdown


# --------------------------------------------------------------------------- #
# AC3 — the conservation contract is STATED and machine-readable.               #
# (Enforcement is LD-233 § AC5; this issue states and enumerates.)              #
# --------------------------------------------------------------------------- #

def test_the_conservation_contract_ships_in_the_projections_own_documentation():
    """AC3: a consumer holding only the wheel can read the contract."""
    from larkdocio.model import projection as projection_module

    doc = projection_module.__doc__
    assert "conservation" in doc.lower()
    assert "opaque" in doc.lower()
    for phrase in ("not edited", "not deleted", "omits it"):
        assert phrase in doc, f"the shipped projection docstring never says {phrase!r}"
    assert CONSERVATION_CONTRACT.strip()


def test_the_contract_names_all_four_things_reconciliation_must_not_do():
    """AC3: "left exactly alone" is spelled out, because a reconciler author needs the
    list, not the adjective."""
    contract = CONSERVATION_CONTRACT.lower()
    for phrase in ("not edited", "not deleted", "not re-created", "omits it"):
        assert phrase in contract, phrase


def test_the_opaque_set_is_machine_readable_for_the_reconciler():
    """AC3 (issue rider): LD-233 must be able to ENFORCE against this without parsing
    prose — the per-document opaque id list is a value on the projection and the
    per-type answer is a callable."""
    blocks, _ = _table("tbl", "doc")
    tree = _tree([_page(children=["tbl", "img"]), *blocks, _image("img", "doc")])
    projection = project_block_ids(tree)

    assert isinstance(projection.opaque_block_ids, tuple)
    assert set(projection.opaque_block_ids) == {"doc", "tbl", "img"}
    assert projection.to_dict()["opaque_block_ids"] == list(projection.opaque_block_ids)
    assert opaque_kind(27) == "image"
    assert opaque_kind(2) is None


# --------------------------------------------------------------------------- #
# AC4 — an unknown block type projects opaquely with its type recorded.         #
# --------------------------------------------------------------------------- #

def test_an_unknown_block_type_projects_opaquely_naming_the_type():
    """AC4: the kind reuses the reader's OWN unknown-block vocabulary ("Unknown block
    type N", the warning it already logs naming the type and the block id) rather than
    inventing a second one. The marker already carries the block id."""
    tree = _tree([_page(children=["u"]), _unknown("u", "doc", block_type=9999)])
    projection = project_block_ids(tree)

    assert unknown_opaque_kind(9999) == "unknown-block-type-9999"
    assert "<!-- lark:block:u opaque=unknown-block-type-9999 -->" in projection.markdown
    assert "u" in projection.opaque_block_ids


def test_an_unknown_LEAF_block_is_still_anchored_even_though_it_renders_nothing():
    """AC4 + the amplifier's completeness clause: a leaf unknown emits no Markdown of its
    own, and conserving it is exactly what the marker is for — so the projection anchors
    it rather than losing it. (An EDITABLE block that renders nothing still gets no
    marker: there is nothing to conserve and nothing to point at.)"""
    tree = _tree([_page(children=["u"]), _unknown("u", "doc", block_type=9999)])
    projection = project_block_ids(tree)

    assert "u" in projection.block_ids
    assert "u" in projection.opaque_block_ids


def test_an_unknown_CONTAINER_still_surfaces_its_editable_children():
    """AC4: the unknown-type fallback renders children transparently, and the projection
    does not swallow them — the container is conserved, its known children are not."""
    tree = _tree([
        _page(children=["u"]),
        _unknown("u", "doc", block_type=9999, children=["p"]),
        _text("p", "u", "inner prose"),
    ])
    projection = project_block_ids(tree)

    markers = dict(_markers_in(projection.markdown))
    assert markers["u"] == "unknown-block-type-9999"
    assert markers["p"] is None
    assert "inner prose" in projection.markdown


# --------------------------------------------------------------------------- #
# AC5 — tables are opaque in this rung (D13b); cells are not addressable.       #
# --------------------------------------------------------------------------- #

def test_a_table_is_opaque_and_its_cells_are_not_individually_addressable():
    """AC5: one marker, on the table block. No cell id is emitted, so an edited cell has
    no anchor to compile a request against — the opacity that makes LD-233's "an edited
    cell produces no request" true."""
    blocks, cell_ids = _table("tbl", "doc")
    tree = _tree([_page(children=["tbl"]), *blocks])
    projection = project_block_ids(tree)

    assert "<!-- lark:block:tbl opaque=table -->" in projection.markdown
    assert "tbl" in projection.opaque_block_ids
    leaked = set(cell_ids) & set(projection.block_ids)
    assert not leaked, f"table cell ids {sorted(leaked)} leaked into the projection."


def test_a_MERGED_table_which_the_reader_emits_as_HTML_is_opaque_too():
    """AC5 + the amplifier's merged-table case: a merged table comes out as raw HTML, the
    one shape Markdown has no syntax for at all."""
    blocks, cell_ids = _merged_table("mtbl", "doc")
    tree = _tree([_page(children=["mtbl"]), *blocks])
    projection = project_block_ids(tree)

    assert "<!-- lark:block:mtbl opaque=table -->" in projection.markdown
    assert "<table>" in projection.markdown
    assert not set(cell_ids) & set(projection.block_ids)


def test_the_docs_name_the_cell_patch_path_as_the_supported_route():
    """AC5: naming the alternative is part of the contract — an agent told "no" without a
    route takes the route anyway."""
    from larkdocio.model import projection as projection_module

    doc = projection_module.__doc__.lower()
    assert "cell" in doc and "patch" in doc


# --------------------------------------------------------------------------- #
# The rigor amplifier — the remaining named cases.                              #
# --------------------------------------------------------------------------- #

def test_a_synced_block_is_conserved():
    tree = _tree([_page(children=["s"]), _source_synced("s", "doc")])
    projection = project_block_ids(tree)

    assert "<!-- lark:block:s opaque=source_synced -->" in projection.markdown
    assert "s" in projection.opaque_block_ids


def test_a_mermaid_diagram_is_create_only_and_therefore_conserved():
    """The writer can bring a mermaid block into existence, but its source is an add-on
    record rather than patchable text — creating one is not editing one."""
    tree = _tree([_page(children=["m"]), _mermaid("m", "doc")])
    projection = project_block_ids(tree)

    assert "<!-- lark:block:m opaque=add_ons -->" in projection.markdown
    assert "```mermaid" in projection.markdown


def test_a_document_of_NOTHING_BUT_opaque_blocks_is_still_well_formed():
    """The amplifier's hardest case: no editable block anywhere. The projection must
    still parse as itself and its id set must be complete."""
    table_blocks, cell_ids = _table("tbl", "doc")
    tree = _tree([
        _page(children=["img", "s", "m", "tbl", "u"]),
        _image("img", "doc"),
        _source_synced("s", "doc"),
        _mermaid("m", "doc"),
        *table_blocks,
        _unknown("u", "doc", block_type=9999),
    ])
    projection = project_block_ids(tree)

    assert set(projection.block_ids) == {"doc", "img", "s", "m", "tbl", "u"}
    assert set(projection.opaque_block_ids) == set(projection.block_ids)
    assert [bid for bid, _ in _markers_in(projection.markdown)] == list(
        projection.block_ids
    )
    assert not set(cell_ids) & set(projection.block_ids)


def test_the_id_set_stays_the_authoritative_record_across_both_marker_forms():
    """Mixed document: the emitted list is still exactly what the text carries, in
    document order, with the opaque subset a real subset of it."""
    table_blocks, _ = _table("tbl", "doc")
    tree = _tree([
        _page(children=["p", "img", "tbl"]),
        _text("p", "doc", "prose"),
        _image("img", "doc"),
        *table_blocks,
    ])
    projection = project_block_ids(tree)

    assert [bid for bid, _ in _markers_in(projection.markdown)] == list(
        projection.block_ids
    )
    assert set(projection.opaque_block_ids) < set(projection.block_ids)


# --------------------------------------------------------------------------- #
# AC8 — the front door: the conservation fact ships, because /BLOCKS.md cannot.  #
# --------------------------------------------------------------------------- #

def _shipped_projection_support():
    from larkdocio import capabilities

    return capabilities(full=True)["surfaces"]["docx-read"]["block_projection_support"]


def test_the_shipped_capability_carries_the_conservation_fact():
    """AC8: /BLOCKS.md is a repo-root document `package-data` cannot reach, so the answer
    a consumer needs travels in the wheel — with the contract attached, since a per-type
    label with no contract is a word rather than a guarantee."""
    shipped = _shipped_projection_support()

    assert shipped["contract"] == CONSERVATION_CONTRACT
    assert set(shipped["state_meanings"]) == set(PROJECTION_STATES)
    assert shipped["types"][str(27)] == "opaque"
    assert shipped["types"][str(2)] == "editable"


def test_the_shipped_states_are_the_derivation_itself_not_a_stored_copy():
    """AC8: same discipline as the read-support projection's ``handled`` flag."""
    shipped = _shipped_projection_support()

    assert {int(t): s for t, s in shipped["types"].items()} == projection_support()
    assert {int(t): k for t, k in shipped["kinds"].items()} == {
        t: opaque_kind(t) for t in opaque_block_types()
    }


def test_the_shipped_projection_answer_round_trips_through_json():
    import json

    from larkdocio import capabilities

    revived = json.loads(json.dumps(capabilities(full=True)))
    assert (
        revived["surfaces"]["docx-read"]["block_projection_support"]["contract"]
        == CONSERVATION_CONTRACT
    )


def test_the_guide_tells_a_consumer_which_blocks_are_conserved():
    """AC8: the shipped consumer guide is where an agent meets the projection, so it is
    where the opaque half has to be named too."""
    from larkdocio import guide

    text = guide(full=True).lower()
    assert "opaque=" in text
    assert "conserv" in text
    assert "cell-patch" in text or "cell patch" in text


@pytest.mark.parametrize("block_type,kind", [(27, "image"), (31, "table"), (49, "source_synced")])
def test_the_per_type_kind_is_the_readers_own_name_for_the_type(block_type, kind):
    """The kind vocabulary is not invented here: it is the block matrix's own type name,
    which is what the reader, the matrix and the shipped read projection all use."""
    assert opaque_kind(block_type) == kind
