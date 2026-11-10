"""Offline unit tests for **table creation** — the ``NewBlock`` table kind, its encoder
and the cell-fill apply path (LD-135).

The dogfood session's **F3** blocker: the edit side has a rich table story (a
:class:`~larkdocio.write.model.TableLocator` resolves one cell exactly-one-or-refuse) but
**nothing brought a table into existence**, so ``capabilities()`` rendering both ``edit``
and ``insert`` as bare op names let an integration budget for a capability that did not
exist (**F9** — editable ≠ creatable). S2 closes it: a table ``NewBlock`` expresses an
**R×C grid of cell contents + an optional header row**, encodes to the real docx create
shape, and flows through the **existing** ``dry_run`` → ``Plan`` → ``apply`` gate.

**The two-step create is Lark's shape, not ours** (live-proven by the W2 gate, LD-073): a
``create_children`` call carrying a ``block_type: 31`` table with a
``row_size``/``column_size``/``header_row`` property makes Lark **auto-provision the cell
grid** — each cell (type 32) wrapping one inner text block (type 2) — so the authored cell
text is written by **patching each cell's inner block**, the same ``update_text_elements``
patch a whole-cell edit performs. Both halves are asserted here against an **injected
transport** (no network): the call sequence, the payload of every call, and the row-major
order.

**Merged cells are refused, never approximated** (AC4). GFM has no colspan/rowspan, so an
authored table is always a plain grid; a ragged grid — the shape a merged MD table produces
— is refused at construction with a **typed** :class:`~larkdocio.write.model.Refusal`
(``merge-not-expressible``) carrying a mandatory ``detail``, raised as a
:class:`~larkdocio.write.model.RefusedError` (a ``ValueError``, so the LD-134 construction
-refusal discipline is unchanged) and never silently padded.

All offline (a fake clock + a stub opener, real reader handlers as the payload oracle); the
**live** table create on a harness-self-provisioned doc is
``tests/test_live_write_table_create_gate.py`` (``pytest -m live_write``), QA's binding gate.
"""
import json
import math

import pytest

from harness import build_blocks, render

from larkdocio.errors import LarkAPIError
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write.apply import apply
from larkdocio.write.client import MAX_BATCH_UPDATES_PER_CALL
from larkdocio.write.encode import (
    CREATABLE_BLOCK_TYPES,
    block_type_for,
    create_batches,
    encode_block,
    encode_content,
    table_cell_texts,
)
from larkdocio.write.model import (
    MAX_TABLE_CELLS,
    Anchor,
    EditRequest,
    InsertPosition,
    InsertRequest,
    NewBlock,
    NewBlockKind,
    NewParagraph,
    RefusalReason,
    RefusedError,
    TableLocator,
    TextSpan,
)
from larkdocio.write.preview import PlanEntry, dry_run

from write_harness import (
    StubOpener,
    _block_payload,
    _by_method,
    _client,
    _methods,
    _page,
    _para,
    _parent_payload,
    _patch_ok,
    _run,
)



@pytest.fixture(autouse=True)
def _over_the_one_call_envelope(monkeypatch):
    """Hold every table in this file OUTSIDE the one-call envelope, so it takes the
    create-seed-grow-fill route these cases exist to pin.

    LD-482 lifted a table that is an insert's **only** block and fits Lark's measured one-call
    envelope onto the ``descendant`` route. The other route did not go away — it is still what
    a table takes when it shares its entry with another block or overflows the envelope, and
    everything below is its contract. Rather than give every case a 500-cell grid to reach it,
    the envelope itself is set to zero: that is the documented route condition, expressed
    through the published constant the condition reads
    (``larkdocio.write.encode.MAX_ONE_CALL_TABLE_CELLS``), and nothing about the growth path or
    the fill is touched. The route SELECTOR is pinned in
    ``tests/test_table_one_call_construction.py``, which also drives the fallback end to end
    with a real mixed-content batch.
    """
    monkeypatch.setattr("larkdocio.write.encode.MAX_ONE_CALL_TABLE_CELLS", 0)


# --------------------------------------------------------------------------- #
# helpers — requests, transport payloads, and the reader oracle                 #
# --------------------------------------------------------------------------- #

def _insert_blocks(quote, blocks, *, position=InsertPosition.AFTER, breadcrumb=()):
    return InsertRequest(
        reference=Anchor(quote=quote, breadcrumb=breadcrumb),
        position=position,
        content=tuple(blocks),
    )


def _created(*children):
    """A ``create_children`` response. Each argument is either a block id (a bare
    created block) or a ``(block_id, [child_id, ...])`` pair — the shape Lark returns
    for a table whose cells it auto-provisioned."""
    out = []
    for c in children:
        if isinstance(c, tuple):
            out.append({"block_id": c[0], "children": list(c[1])})
        else:
            out.append({"block_id": c})
    return {"code": 0, "data": {"children": out, "document_revision_id": 200}}


def _table_block(table_id, cell_ids, *, col_size=None, header_row=True):
    """A ``get_block`` payload for a live table block carrying its cell ids."""
    return {"code": 0, "data": {"block": {
        "block_id": table_id,
        "block_type": 31,
        "table": {"property": {
            "row_size": max(1, len(cell_ids) // (col_size or len(cell_ids) or 1)),
            "column_size": col_size or len(cell_ids),
            "header_row": header_row,
        }},
        "children": list(cell_ids),
    }}}


def _cell_block(cell_id, inner_ids=None):
    """A ``get_block`` payload for a live table cell (type 32) and its inner block(s).

    The apply engine no longer reads a cell one at a time (LD-481 batched the fill through
    the document block list — see :func:`_cell_blocks`), so this is kept for the suites that
    still assert the SHAPE of a live cell rather than a fill's call sequence."""
    return {"code": 0, "data": {"block": {
        "block_id": cell_id,
        "block_type": 32,
        "table_cell": {},
        "children": list(inner_ids if inner_ids is not None else [f"{cell_id}t"]),
    }}}


def _lark_provisioned(item, *, tid="tbl", doc_id="root"):
    """The block payloads Lark provisions for a created table — the payload ORACLE.

    Takes the authored table ``NewBlock``, encodes it with the real encoder, and builds
    the document Lark would hold afterwards: the type-31 table (with the encoder's own
    property payload), its R×C type-32 cells, and each cell's inner type-2 text block
    carrying the authored cell text. Rendering / parsing THAT with the reader's own
    handlers is what proves "the reader parses what the encoder emitted".

    **One faithfulness detail, live-verified during LD-135** (a one-shot probe on a
    self-provisioned doc, deleted in the same run): Lark **omits a false ``header_row``**
    from the block payload it returns — a table created with ``header_row: true`` reads back
    ``"header_row": true``, one created with ``false`` reads back with the key **absent**.
    The oracle reproduces that omission, so the offline round-trip shows the same Markdown a
    live round-trip does (namely: the reader's absent ⇒ promoted default applies).
    """
    payload = encode_block(item)
    if payload["table"]["property"].get("header_row") is False:
        payload = {**payload, "table": {"property": {
            k: v for k, v in payload["table"]["property"].items() if k != "header_row"
        }}}
    texts = table_cell_texts(item)
    cell_ids = [f"{tid}c{i}" for i in range(len(texts))]
    blocks = [{
        "block_id": doc_id, "parent_id": "doc", "block_type": 1,
        "page": {"elements": []}, "children": [tid],
    }, {
        "block_id": tid, "parent_id": doc_id, "children": cell_ids, **payload,
    }]
    for cell_id, text in zip(cell_ids, texts):
        blocks.append({
            "block_id": cell_id, "parent_id": tid, "block_type": 32,
            "table_cell": {}, "children": [f"{cell_id}t"],
        })
        blocks.append({
            "block_id": f"{cell_id}t", "parent_id": cell_id, "block_type": 2,
            "text": {"elements": [{"text_run": {"content": text}}]}, "children": [],
        })
    return blocks


def _read_back(item):
    """Render an authored table through the READER (via Lark's provisioning shape)."""
    return render(_lark_provisioned(item), doc_id="root")


def _table_lines(item):
    """The rendered table's non-blank lines (the untitled page contributes a blank line
    of its own around the table, which is not what these assertions are about)."""
    return [line for line in _read_back(item).splitlines() if line]


def _tree_of(item):
    """Parse the provisioned document into the node TREE the writer anchors against."""
    blocks = _lark_provisioned(item)
    return Parser(Config()).parse_docx_tree("root", build_blocks(blocks))


_HEADERED_3X3 = NewBlock.table(
    [["Metric", "Value", "Owner"],
     ["On-time delivery", "97.2%", "Ops"],
     ["Defect rate", "0.3%", "QA"]],
    header_row=True,
)


# =========================================================================== #
# AC1 — the table NewBlock: R×C grid + optional header row, frozen, JSON       #
# =========================================================================== #

def test_ac1_table_is_a_kind_in_the_closed_creatable_vocabulary():
    """The kind vocabulary gains ``table`` and stays a **closed** enum — the property
    that keeps image / board / embed / bitable / sheet inexpressible.

    (``mermaid`` joined the enum in LD-192, on live evidence that a specimen-shaped type-40
    create is accepted; closed-ness is about admitting a kind only on evidence, not about the
    set never growing. Nothing there bears on bitable/sheet, which stay inexpressible.)"""
    assert NewBlockKind.TABLE.value == "table"
    assert {k.value for k in NewBlockKind} == {
        "paragraph", "heading", "bullet", "ordered", "todo", "code", "quote", "table",
        "mermaid",
    }


def test_ac1_a_3x3_with_a_header_reads_back_what_was_constructed():
    """AC1 (the named unit test): construct a 3×3 with a header row and read it back."""
    t = _HEADERED_3X3
    assert t.kind is NewBlockKind.TABLE
    assert t.header_row is True
    assert t.row_count == 3
    assert t.column_count == 3
    assert t.rows == (
        ("Metric", "Value", "Owner"),
        ("On-time delivery", "97.2%", "Ops"),
        ("Defect rate", "0.3%", "QA"),
    )


def test_ac1_rows_are_normalized_to_an_immutable_grid():
    """Authored as lists, held as tuples — a frozen value cannot carry a mutable grid a
    consumer could edit out from under a built plan."""
    grid = [["a", "b"], ["c", "d"]]
    t = NewBlock.table(grid)
    grid[0][0] = "MUTATED"
    assert t.rows == (("a", "b"), ("c", "d"))
    assert all(isinstance(row, tuple) for row in t.rows)


def test_ac1_a_table_newblock_is_frozen():
    t = NewBlock.table([["a"]])
    with pytest.raises(Exception):
        t.rows = (("b",),)


def test_ac1_the_header_row_is_optional_and_defaults_to_promoted():
    """AC1 (the *optional* header row): ``header_row`` is a real either-way choice, and the
    default is **True** — what both ends already do (Lark's editor promotes row 0, and the
    reader's documented rule renders an ABSENT flag as promoted). Defaulting to False would
    advertise a distinction the Markdown round-trip cannot show (see the lossiness test in
    AC4)."""
    assert NewBlock.table([["a", "b"], ["c", "d"]]).header_row is True
    assert NewBlock.table([["a", "b"]], header_row=False).header_row is False
    assert NewBlock.table([["a", "b"]], header_row=True).header_row is True


def test_ac1_a_non_table_kind_carries_no_header_row_at_all():
    """The flag is tri-state under the hood (unset / True / False) so that giving tables a
    default of True cannot leak a bogus flag onto every other kind."""
    assert NewBlock.paragraph("p").header_row is None
    assert NewBlock.heading(1, "H").header_row is None


@pytest.mark.parametrize("rows,header_row", [
    ([["only"]], True),                                    # 1×1
    ([["only"]], False),                                   # 1×1, headerless
    ([["a", "b", "c", "d"]], False),                       # 1×N
    ([["a"], ["b"], ["c"], ["d"]], False),                 # N×1
    ([["h1", "h2"], ["a", "b"], ["c", "d"]], True),        # 3×2 with a header
    ([["h1", "h2"], ["a", "b"]], False),                   # 2×2 headerless
])
def test_ac1_every_table_shape_json_round_trips(rows, header_row):
    """AC1: frozen + JSON round-trip across 1×1 / 1×N / N×1 / with + without header."""
    t = NewBlock.table(rows, header_row=header_row)
    back = NewBlock.from_dict(json.loads(json.dumps(t.to_dict())))
    assert back == t
    assert back.rows == t.rows and back.header_row == t.header_row


def test_ac1_the_wire_form_is_kind_tagged_and_carries_the_grid():
    t = NewBlock.table([["a", "b"]], header_row=True)
    assert t.to_dict() == {
        "kind": "table", "text": "", "rows": [["a", "b"]], "header_row": True,
    }


def test_ac1_a_table_round_trips_as_insert_content_beside_the_other_kinds():
    """One content dispatcher: a table is told apart from the tagged non-table kinds and
    the tagless legacy ``NewParagraph`` in the same request."""
    req = _insert_blocks("q", [
        NewBlock.heading(2, "Findings"),
        _HEADERED_3X3,
        NewParagraph("legacy shape"),
    ])
    back = InsertRequest.from_dict(json.loads(json.dumps(req.to_dict())))
    assert back == req
    assert back.content[1].rows == _HEADERED_3X3.rows


# -- the typed structural refusals (never a silent pad, never a crash) --------- #

def test_ac1_a_table_with_no_rows_is_a_typed_refusal():
    with pytest.raises(ValueError) as e:
        NewBlock.table([])
    assert "at least one row" in str(e.value)


def test_ac1_a_table_with_an_empty_row_is_a_typed_refusal():
    with pytest.raises(ValueError) as e:
        NewBlock.table([[]])
    assert "at least one column" in str(e.value)


def test_ac1_a_non_string_cell_is_a_typed_refusal_naming_the_position():
    with pytest.raises(ValueError) as e:
        NewBlock.table([["ok", 42]])
    assert "row 0" in str(e.value) and "column 1" in str(e.value)


def test_ac1_rows_on_a_non_table_kind_is_a_typed_refusal():
    with pytest.raises(ValueError) as e:
        NewBlock(kind=NewBlockKind.PARAGRAPH, text="p", rows=(("a",),))
    assert "table" in str(e.value)


@pytest.mark.parametrize("flag", [True, False])
def test_ac1_a_header_row_flag_on_a_non_table_kind_is_a_typed_refusal(flag):
    with pytest.raises(ValueError) as e:
        NewBlock(kind=NewBlockKind.QUOTE, text="q", header_row=flag)
    assert "table" in str(e.value)


def test_ac1_a_table_carrying_block_text_is_a_typed_refusal():
    """A table's content lives in ``rows``; a ``text`` payload would be silently dropped
    at encode time, so it is refused instead."""
    with pytest.raises(ValueError) as e:
        NewBlock(kind=NewBlockKind.TABLE, text="stray", rows=(("a",),))
    assert "rows" in str(e.value)


def test_ac1_a_table_carrying_children_is_a_typed_refusal():
    with pytest.raises(ValueError) as e:
        NewBlock(kind=NewBlockKind.TABLE, rows=(("a",),),
                 children=(NewBlock.paragraph("p"),))
    assert "children" in str(e.value)


def test_ac1_a_table_nested_under_a_list_item_is_a_typed_refusal():
    """Nesting is a *list* structure in this rung and a nested table is not
    MD-expressible — refused rather than created somewhere the author did not ask for."""
    with pytest.raises(ValueError) as e:
        NewBlock.bullet("item", children=(NewBlock.table([["a"]]),))
    assert "table" in str(e.value).lower()


def test_ac1_a_table_at_exactly_the_documented_cell_cap_is_accepted():
    rows = [["x"] * 10 for _ in range(MAX_TABLE_CELLS // 10)]
    t = NewBlock.table(rows)
    assert t.row_count * t.column_count == MAX_TABLE_CELLS


def test_ac1_one_cell_past_the_cap_is_a_typed_refusal_naming_the_cap():
    rows = [["x"] * 10 for _ in range(MAX_TABLE_CELLS // 10)]
    rows.append(["x"] * 10)
    with pytest.raises(ValueError) as e:
        NewBlock.table(rows)
    assert str(MAX_TABLE_CELLS) in str(e.value)


# =========================================================================== #
# AC2 — the encoder produces the documented create shape (parent table, then    #
#        the cells, in the right order) — asserted at the transport             #
# =========================================================================== #

def test_ac2_the_creatable_block_types_now_include_the_table_family():
    """AC5's code truth, which AC2's payload depends on: types 31 (table) and 32
    (table_cell) join the creatable set — a cell is created *with* its table (Lark
    auto-provisions the grid), which is why 32 is in the set with no kind of its own."""
    assert 31 in CREATABLE_BLOCK_TYPES
    assert 32 in CREATABLE_BLOCK_TYPES


def test_ac2_block_type_for_a_table_is_31():
    assert block_type_for(_HEADERED_3X3) == 31


@pytest.mark.parametrize("rows,header_row,row_size,column_size", [
    ([["only"]], False, 1, 1),
    ([["a", "b", "c"]], False, 1, 3),
    ([["a"], ["b"], ["c"]], False, 3, 1),
    ([["h1", "h2"], ["a", "b"], ["c", "d"]], True, 3, 2),
])
def test_ac2_a_table_encodes_to_the_documented_property_payload(
    rows, header_row, row_size, column_size
):
    """The create shape: a type-31 block whose ``table.property`` declares the grid.
    Lark provisions the cells from THIS property — the payload is the whole grid."""
    assert encode_block(NewBlock.table(rows, header_row=header_row)) == {
        "block_type": 31,
        "table": {"property": {
            "row_size": row_size, "column_size": column_size, "header_row": header_row,
        }},
    }


def test_ac2_the_cell_contents_ride_the_encoded_child_in_row_major_order():
    """The authored cell text travels with the encoded table (row-major, the order Lark
    provisions the grid in) so the apply path can fill each cell without re-deriving it."""
    encoded = encode_content((_HEADERED_3X3,))
    assert len(encoded) == 1
    assert encoded[0].cell_texts == (
        "Metric", "Value", "Owner",
        "On-time delivery", "97.2%", "Ops",
        "Defect rate", "0.3%", "QA",
    )
    assert table_cell_texts(_HEADERED_3X3) == encoded[0].cell_texts


def test_ac2_a_table_is_one_create_batch_and_carries_no_children():
    """A table is a single block in the create call — its cells are Lark's to provision,
    not extra children in the payload."""
    encoded = encode_content((_HEADERED_3X3,))
    assert create_batches(encoded) == ((None, (0,)),)
    assert "children" not in encoded[0].payload["table"]


def test_ac2_a_non_table_kind_carries_no_cell_texts():
    encoded = encode_content((NewBlock.heading(1, "H"), NewParagraph("p")))
    assert [e.cell_texts for e in encoded] == [(), ()]


def test_ac2_the_encoded_table_reads_back_as_a_gfm_table_through_the_reader():
    """The payload oracle: encode → Lark's provisioning shape → the READER's own
    handlers. A headered 3×3 comes back as the GFM table the reader emits."""
    assert _table_lines(_HEADERED_3X3) == [
        "| Metric | Value | Owner |",
        "|---|---|---|",
        "| On-time delivery | 97.2% | Ops |",
        "| Defect rate | 0.3% | QA |",
    ]


def test_ac2_the_header_flag_is_the_only_property_difference_between_the_two_forms():
    """``header_row`` is carried into the create property either way — it is what Lark
    provisions the header state from (live-verified: ``true`` comes back ``true``)."""
    grid = [["a", "b"], ["c", "d"]]
    assert encode_block(NewBlock.table(grid))["table"]["property"]["header_row"] is True
    assert encode_block(
        NewBlock.table(grid, header_row=False))["table"]["property"]["header_row"] is False


def test_ac2_a_headered_table_reads_back_with_row_0_promoted():
    assert _table_lines(NewBlock.table([["a", "b"], ["c", "d"]])) == [
        "| a | b |",        # row 0 IS the header…
        "|---|---|",        # …so the delimiter follows it
        "| c | d |",
    ]


@pytest.mark.parametrize("rows", [
    [["only"]],
    [["a", "b", "c", "d"]],
    [["a"], ["b"], ["c"]],
])
def test_ac2_every_grid_shape_survives_the_reader_round_trip(rows):
    md = _read_back(NewBlock.table(rows))
    for row in rows:
        for cell in row:
            assert cell in md


# -- the apply path at the transport: create the table, then fill its cells ---- #

def _block_list_page(blocks, *, page_token=None, has_more=False):
    """A ``GET …/documents/{id}/blocks`` page: ``data.items`` plus the cursor fields."""
    data = {"items": list(blocks), "has_more": has_more}
    if page_token is not None:
        data["page_token"] = page_token
    return {"code": 0, "data": data}


def _cell_blocks(cell_ids, *, table_id="tbl1", bare=()):
    """The document-listing rows for a provisioned grid — the type-31 table, its type-32
    cells and each cell's inner type-2 text block. ``bare`` names cells listed WITHOUT an
    inner block (the defensive shape the fill must author into rather than drop)."""
    rows = [{"block_id": table_id, "block_type": 31, "children": list(cell_ids)}]
    for cell_id in cell_ids:
        rows.append({"block_id": cell_id, "block_type": 32, "parent_id": table_id,
                     "children": [] if cell_id in bare else [f"{cell_id}t"]})
        if cell_id not in bare:
            rows.append({"block_id": f"{cell_id}t", "block_type": 2, "parent_id": cell_id,
                         "children": []})
    return rows


def _batch_ok():
    """A ``PATCH …/blocks/batch_update`` answer."""
    return {"code": 0, "data": {"blocks": []}}


def _fill_responses(cell_ids, *, table_id="tbl1", bare=(), written=None):
    """The queued responses for filling ``cell_ids`` — **LD-481's shape**: ONE paginated
    document block list (which carries every cell's inner text-block id) then one
    ``batch_update`` answer per run of :data:`MAX_BATCH_UPDATES_PER_CALL`.

    Superseded from the LD-135 shape (a ``get_block`` + a ``patch_block`` per cell): the
    per-cell pair is what cost 2 API calls per cell, and the whole point of the change is
    that it no longer happens. The old builder is not kept beside this one, because a helper
    that queues a call the engine must never issue can only mislead the next reader.
    """
    if written is None:
        written = [c for c in cell_ids if c not in bare]
    batches = math.ceil(len(written) / MAX_BATCH_UPDATES_PER_CALL)
    return [_block_list_page(_cell_blocks(cell_ids, table_id=table_id, bare=bare)),
            *[_batch_ok() for _ in range(batches)]]


def _batch_bodies(opener):
    """The bodies of the batched cell writes, in the order they went out."""
    return [r["body"] for r in opener.requests
            if r["method"] == "PATCH" and "batch_update" in r["url"]]


def test_ac2_apply_creates_the_table_then_patches_each_cell_in_row_major_order():
    """AC2 (the injected-transport call-sequence assertion) — the whole family lands
    atomically through the insert path: ONE ``create_children`` for the table shell at the
    plan's insertion point, then the auto-provisioned cells' inner text blocks written in
    row-major order with the authored content.

    **LD-481 moved HOW those writes go out, not WHAT lands**: the cells' inner block ids
    come from one document block list and the texts ride one batched update, so the bodies
    below are the same ``update_text_elements`` bodies this test always asserted — now
    carried as batch requests rather than one PATCH per cell.
    """
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert_blocks("anchor line", [
        NewBlock.table([["H1", "H2"], ["a", "b"]], header_row=True)])], tree)
    cell_ids = ["c0", "c1", "c2", "c3"]
    opener = StubOpener([
        _block_payload("p1", [_run("anchor line")], parent_id="root"),
        _parent_payload("root", ["p1"]),           # its LIVE parent → the index (LD-453)
        _created("tbl1"),
        _table_block("tbl1", cell_ids, col_size=2),
        *_fill_responses(cell_ids),
    ])
    log = apply(plan, _client(opener), "doc123")

    posts = _by_method(opener, "POST")
    assert len(posts) == 1, "the table shell is ONE create call — Lark provisions the cells"
    assert "/blocks/root/children" in posts[0]["url"]
    assert posts[0]["body"] == {
        "index": 1,
        "children": [{
            "block_type": 31,
            "table": {"property": {
                "row_size": 2, "column_size": 2, "header_row": True,
            }},
        }],
    }
    bodies = _batch_bodies(opener)
    assert len(bodies) == 1, "four cells is one batched call, not four patches"
    assert bodies[0]["requests"] == [
        {"block_id": f"c{i}t",
         "update_text_elements": {"elements": [{"text_run": {"content": t}}]}}
        for i, t in enumerate(("H1", "H2", "a", "b"))
    ]
    assert log.entries[0].outcome == "inserted"
    assert log.entries[0].created_block_ids == ("tbl1",)


def test_ac2_the_cell_ids_in_the_create_response_save_a_round_trip():
    """When the create response already carries the provisioned cell ids, the engine uses
    them instead of re-reading the table block (fewer throttled calls, same result)."""
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert_blocks("anchor line", [NewBlock.table([["a", "b"]])])], tree)
    opener = StubOpener([
        _block_payload("p1", [_run("anchor line")], parent_id="root"),
        _parent_payload("root", ["p1"]),           # its LIVE parent → the index (LD-453)
        _created(("tbl1", ["c0", "c1"])),
        *_fill_responses(["c0", "c1"]),
    ])
    apply(plan, _client(opener), "doc123")

    gets = [r["url"] for r in _by_method(opener, "GET")]
    assert not any("/blocks/tbl1?" in u for u in gets), (
        "the table block was re-read even though the create response carried its cells")
    assert [u.split("/blocks")[1].split("?")[0] for u in gets] == ["/p1", "/root", ""], (
        "the reads are the anchor, its live parent, and ONE document block list — never "
        "a per-cell get_block (LD-481)")


def test_ac2_an_empty_cell_is_left_as_provisioned_and_costs_no_write():
    """An empty authored cell needs no patch — Lark provisions the cell empty. Skipping
    it is a call saved, and the grid shape is unchanged (the cell still exists)."""
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert_blocks("anchor line", [
        NewBlock.table([["a", ""], ["", "d"]])])], tree)
    opener = StubOpener([
        _block_payload("p1", [_run("anchor line")], parent_id="root"),
        _parent_payload("root", ["p1"]),           # its LIVE parent → the index (LD-453)
        _created(("tbl1", ["c0", "c1", "c2", "c3"])),
        *_fill_responses(["c0", "c1", "c2", "c3"], written=["c0", "c3"]),
    ])
    apply(plan, _client(opener), "doc123")

    requests = _batch_bodies(opener)[0]["requests"]
    assert [r["block_id"] for r in requests] == ["c0t", "c3t"]
    assert [r["update_text_elements"]["elements"][0]["text_run"]["content"]
            for r in requests] == ["a", "d"]


def test_ac2_a_cell_provisioned_without_an_inner_block_gets_one_created():
    """Defensive, and never a silent drop: the live-proven shape is a cell wrapping one
    inner text block, but if a cell arrives bare the authored text is CREATED inside it
    rather than dropped."""
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert_blocks("anchor line", [NewBlock.table([["a"]])])], tree)
    opener = StubOpener([
        _block_payload("p1", [_run("anchor line")], parent_id="root"),
        _parent_payload("root", ["p1"]),           # its LIVE parent → the index (LD-453)
        _created(("tbl1", ["c0"])),
        *_fill_responses(["c0"], bare=("c0",)),
        _created("c0newtext"),
    ])
    apply(plan, _client(opener), "doc123")

    posts = _by_method(opener, "POST")
    assert len(posts) == 2
    assert "/blocks/c0/children" in posts[1]["url"]
    assert posts[1]["body"]["children"] == [
        {"block_type": 2, "text": {"elements": [{"text_run": {"content": "a"}}]}}]
    assert not _batch_bodies(opener), "a bare cell has no inner block to batch-update"


def test_ac2_fewer_provisioned_cells_than_authored_is_SAID_not_silently_dropped():
    """If Lark ever provisions a grid that does not match the requested property, the
    authored content would be silently truncated — say so loudly instead.

    **RENAMED at the same landing that transformed the body (LD-643).** It was
    ``…_raises_instead_of_dropping_content``, and the raise is exactly what moved: the
    apply-time disposition boundary types the failure into the log instead of letting it
    escape. A guard whose name still promised a raise while its body asserted a returned log
    would be the next reader's trap. The RULE the name is about — never silently drop the
    caller's content, and name both counts — is unchanged and is what is asserted below.
    """
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert_blocks("anchor line", [
        NewBlock.table([["a", "b"], ["c", "d"]])])], tree)
    opener = StubOpener([
        _block_payload("p1", [_run("anchor line")], parent_id="root"),
        _parent_payload("root", ["p1"]),           # its LIVE parent → the index (LD-453)
        _created(("tbl1", ["c0", "c1"])),     # only 2 of the 4 requested cells
    ])
    # TRANSFORMED, NOT STRUCK (LD-643): the rule is unchanged — a truncated grid is SAID, with
    # both counts named, never silently written short — and both counts are still asserted.
    # What moved is where it is said: the apply-time disposition boundary types the failure
    # into the log rather than letting it escape, so the caller keeps the record of the batch.
    # The table WAS created, so the entry is applied-unverified, not a refusal.
    log = apply(plan, _client(opener), "doc123")
    entry = log.entries[0]
    assert entry.outcome == "applied-unverified"
    assert "4" in entry.refusal.detail and "2" in entry.refusal.detail


def test_ac2_a_grid_of_only_empty_cells_costs_no_call_beyond_the_create():
    """Nothing to fill ⇒ nothing is read either: an all-empty grid does not even look up
    the provisioned cell ids (Lark already created them empty)."""
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert_blocks("anchor line", [
        NewBlock.table([["", ""], ["", ""]])])], tree)
    opener = StubOpener([
        _block_payload("p1", [_run("anchor line")], parent_id="root"),
        _parent_payload("root", ["p1"]),           # its LIVE parent → the index (LD-453)
        _created("tbl1"),
    ])
    log = apply(plan, _client(opener), "doc123")
    assert _methods(opener) == ["GET", "GET", "POST"], opener.requests
    assert log.entries[0].created_block_ids == ("tbl1",)


def test_ac2_a_created_table_with_no_id_is_SAID_and_nothing_is_addressed():
    """Defensive: if the create response comes back without the table's block id, the
    authored cells have no home — say so, rather than issuing a call against ``None``.

    **RENAMED with its body (LD-643)**, for the reason given on the sibling above: the defect
    is still said and no call is still issued, but it is said in the apply-log rather than as
    an escaping traceback, so the old ``…_raises_…`` name contradicted what is asserted here.
    """
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert_blocks("anchor line", [NewBlock.table([["a"]])])], tree)
    opener = StubOpener([
        _block_payload("p1", [_run("anchor line")], parent_id="root"),
        _parent_payload("root", ["p1"]),           # its LIVE parent → the index (LD-453)
        {"code": 0, "data": {"children": [{}], "document_revision_id": 200}},
    ])
    # TRANSFORMED, NOT STRUCK (LD-643): same shape as the case above — the defect is still
    # SAID and no call is still issued against a missing id (the second assertion below is
    # untouched); it is now said in the log rather than as an escaping traceback.
    log = apply(plan, _client(opener), "doc123")
    entry = log.entries[0]
    assert entry.outcome == "applied-unverified"
    assert "block id" in entry.refusal.detail
    assert len(_by_method(opener, "GET")) == 2, (
        "no call may be issued against a missing block id")


def test_ac2_a_table_lands_beside_the_other_kinds_in_one_insert():
    """A mixed authored fragment: the top-level group is still ONE create call (heading +
    table + paragraph), and only the table costs the extra cell fills."""
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert_blocks("anchor line", [
        NewBlock.heading(2, "Findings"),
        NewBlock.table([["a"]]),
        NewParagraph("tail"),
    ])], tree)
    opener = StubOpener([
        _block_payload("p1", [_run("anchor line")], parent_id="root"),
        _parent_payload("root", ["p1"]),           # its LIVE parent → the index (LD-453)
        _created("h1", ("tbl1", ["c0"]), "p2"),
        *_fill_responses(["c0"]),
    ])
    log = apply(plan, _client(opener), "doc123")

    posts = _by_method(opener, "POST")
    assert len(posts) == 1
    assert [c["block_type"] for c in posts[0]["body"]["children"]] == [4, 31, 2]
    assert log.entries[0].created_block_ids == ("h1", "tbl1", "p2")
    assert _methods(opener) == ["GET", "GET", "POST", "GET", "PATCH"]
    assert len(_batch_bodies(opener)) == 1


# =========================================================================== #
# AC3 — cell content reuses the authored inline model (verbatim in, escaped     #
#        by the READER on the way back out — the LD-130/S1 discipline)          #
# =========================================================================== #

@pytest.mark.parametrize("literal", [
    "# not a heading",
    "- not a list",
    "> not a quote",
    "**not bold**",
    "1. not ordered",
    "a|b",
    "back\\slash",
    "日本語 ✅",
])
def test_ac3_authored_cell_text_lands_literal_in_the_payload(literal):
    """AC3: a cell carries text with the S1 escaping discipline — the encoder ships it
    **verbatim** (escaping is the reader's job on the way out, never the encoder's on the
    way in), so what lands in the document is exactly what was authored."""
    assert table_cell_texts(NewBlock.table([[literal]])) == (literal,)
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert_blocks("anchor line", [NewBlock.table([[literal]])])], tree)
    opener = StubOpener([
        _block_payload("p1", [_run("anchor line")], parent_id="root"),
        _parent_payload("root", ["p1"]),           # its LIVE parent → the index (LD-453)
        _created(("tbl1", ["c0"])),
        *_fill_responses(["c0"]),
    ])
    apply(plan, _client(opener), "doc123")
    assert _batch_bodies(opener)[0]["requests"] == [{
        "block_id": "c0t",
        "update_text_elements": {"elements": [{"text_run": {"content": literal}}]}}]


def test_ac3_a_pipe_in_a_cell_is_escaped_by_the_readers_table_serializer():
    """A pipe would break the GFM row, so the READER escapes it (`\\|`) — the authored
    text stays literal in the document. Composition with the table renderer, proven."""
    md = _read_back(NewBlock.table([["a|b", "plain"]]))
    assert "| a\\|b | plain |" in md


def test_ac3_a_metachar_cell_cannot_masquerade_as_structure_after_the_round_trip():
    """The LD-130 escaping composes with table creation, by its documented rule: a GFM
    pipe-table cell is an **inline-only** context, so a line-leading marker is *not*
    backslash-escaped there — it cannot parse as structure anyway, because it never starts
    a line: it sits inside the pipe row. The authored text is therefore literal AND
    structurally inert."""
    md = _read_back(NewBlock.table([["# not a heading", "**not bold**"]]))
    # the line-leading marker is left bare (inline context), the pairable inline run IS
    # escaped — the reader's two-half rule, unchanged by table authoring.
    assert "| # not a heading | \\*\\*not bold\\*\\* |" in md
    assert not any(line.startswith("#") for line in md.splitlines()), md


def test_ac3_a_pairable_inline_delimiter_in_a_cell_stays_the_readers_business():
    """The inline half of the LD-130 discipline still runs inside a cell (it is an inline
    context): the authored text lands verbatim in the document, and whatever the reader
    does with pairable delimiters on the way out is the reader's documented rule, not the
    encoder's. Pinned so a future escaping change is a *visible* decision."""
    assert table_cell_texts(NewBlock.table([["*a* and *b*"]])) == ("*a* and *b*",)
    assert "| \\*a\\* and \\*b\\* |" in _read_back(NewBlock.table([["*a* and *b*"]]))


def test_ac3_a_newline_in_a_cell_is_documented_lossiness_not_a_broken_row():
    """A GFM cell cannot hold a literal newline. The authored text lands verbatim in the
    document; the READER joins the lines with ``<br>`` (its documented behavior), so the
    table still parses — the lossiness is in the Markdown projection, not the write."""
    t = NewBlock.table([["line one\nline two"]])
    assert table_cell_texts(t) == ("line one\nline two",)
    md = _read_back(t)
    assert "| line one<br>line two |" in md


# =========================================================================== #
# AC4 — merged cells are REFUSED, not approximated (a typed Refusal + detail)    #
# =========================================================================== #

def test_ac4_a_ragged_grid_is_a_typed_refusal_carrying_the_merge_reason():
    """AC4: an MD table that cannot be represented as a plain grid — the shape a merged
    table produces — yields a **typed** refusal with a mandatory ``detail``, never a
    silently padded (or truncated) grid."""
    with pytest.raises(RefusedError) as e:
        NewBlock.table([["a", "b", "c"], ["d", "e"]])
    refusal = e.value.refusal
    assert refusal.reason is RefusalReason.MERGE_NOT_EXPRESSIBLE
    assert refusal.detail
    assert "merge" in refusal.detail.lower()
    assert "row 1" in refusal.detail and "3" in refusal.detail


def test_ac4_the_merge_refusal_is_a_valueerror_so_construction_discipline_is_unchanged():
    """``RefusedError`` IS a ``ValueError`` — the LD-134 "caps refuse at construction"
    contract (and any consumer already catching ``ValueError``) is untouched."""
    assert issubclass(RefusedError, ValueError)
    with pytest.raises(ValueError):
        NewBlock.table([["a", "b"], ["c"]])


def test_ac4_the_merge_refusal_serializes_like_every_other_refusal():
    """It is the same typed vocabulary the resolver/apply engine speak, so a consumer's
    approval UX renders it with no new case — and it round-trips through JSON."""
    from larkdocio.write.model import Refusal

    with pytest.raises(RefusedError) as e:
        NewBlock.table([["a"], ["b", "c"]])
    d = e.value.refusal.to_dict()
    assert d["reason"] == "merge-not-expressible"
    assert d["detail"]
    assert Refusal.from_dict(json.loads(json.dumps(d))) == e.value.refusal


def test_ac4_a_span_is_structurally_inexpressible_in_the_authored_grid():
    """There is no colspan / rowspan to smuggle a merge through: a table ``NewBlock``
    carries a grid of **strings** and nothing else, so a merge cannot be requested at
    all — the refusal above is the only way an author learns it, and it is never
    approximated by padding."""
    import dataclasses

    fields = {f.name for f in dataclasses.fields(NewBlock)}
    # SUPERSEDED IN PART: the REASON is unchanged — a table's grid carries strings and
    # nothing else, so a MERGE cannot be requested at all. Only the word `spans` left this
    # list, and it left because it now names something else entirely: `NewBlock.spans` is the
    # INLINE run sequence that carries a link anchor, and a TABLE is refused it outright
    # (asserted immediately below), so it is not a merge-smuggling route. Transformed, not
    # dropped.
    for smuggle in ("colspan", "rowspan", "merges", "merge_info"):
        assert smuggle not in fields
    with pytest.raises(ValueError, match="spans"):
        NewBlock(kind=NewBlockKind.TABLE, rows=(("a",),),
                 spans=(TextSpan("x", link_url="https://example.com/f"),))
    assert all(isinstance(c, str) for row in _HEADERED_3X3.rows for c in row)


def test_ac4_a_headerless_table_is_documented_projection_lossiness():
    """The second documented lossiness LD-135 found (live-verified, then pinned here):
    ``header_row=False`` **is** sent and **is** stored — but Lark **omits a false flag** from
    the payload it returns, and the reader cannot tell "absent" from "false", so its
    documented absent ⇒ promoted default applies and a headerless authored table reads back
    through Markdown with row 0 as the header. The write is not lost; the *Markdown
    projection* cannot show it. Pinned so the asymmetry stays a documented decision instead
    of a surprise (and so a future reader change to the default is a visible one)."""
    headerless = NewBlock.table([["a", "b"], ["c", "d"]], header_row=False)
    # the flag really is in the create payload…
    assert encode_block(headerless)["table"]["property"]["header_row"] is False
    # …and the round-trip through Lark's payload shape still promotes row 0.
    assert _table_lines(headerless) == ["| a | b |", "|---|---|", "| c | d |"]
    assert _table_lines(headerless) == _table_lines(NewBlock.table([["a", "b"], ["c", "d"]]))


def test_ac4_the_lossiness_is_documented_in_the_guide_and_the_matrix():
    """AC4: the merged-cell lossiness is **documented**, not discovered — in the shipped
    consumer guide (`larkdocio.guide()`) and in the block matrix's write-support row."""
    from pathlib import Path

    from larkdocio import guide

    text = guide(full=True).lower()
    assert "merged" in text
    assert "colspan" in text or "rowspan" in text
    blocks_md = (Path(__file__).resolve().parents[1] / "BLOCKS.md").read_text(encoding="utf-8").lower()
    assert "merged" in blocks_md and ("colspan" in blocks_md or "rowspan" in blocks_md)


# =========================================================================== #
# AC5 — truth rows: capabilities() reflects table creation                      #
# =========================================================================== #

def _floor():
    from larkdocio import capabilities

    return capabilities(full=True)["surfaces"]["docx-write"]["content_constraints"]


def test_ac5_the_capabilities_floor_states_that_a_table_is_creatable():
    floor = _floor()["floor"].lower()
    assert "table" in floor
    assert "not creatable in this rung: a table" not in floor
    for word in ("grid", "header"):
        assert word in floor, f"the floor must describe the authored table shape: {word}"


def test_ac5_the_floor_no_longer_lists_a_plain_table_as_not_creatable():
    """The F14 lie in reverse: with S2 shipped, claiming a table cannot be created is
    exactly as wrong as LD-134's stale heading claim was."""
    not_creatable = _floor()["not_creatable"]
    joined = " ".join(not_creatable).lower()
    assert "merged" in joined, (
        f"the merged-cell exclusion must be named: {not_creatable}")
    for entry in not_creatable:
        low = entry.lower()
        if low.startswith("table"):
            raise AssertionError(f"a plain table IS creatable since S2: {entry!r}")


def test_ac5_the_floor_keeps_the_editable_not_creatable_nuance_truthful():
    """F9 still holds, in its S2 form: a **merged** table reads and its unmerged cells
    edit, but no merge can be authored."""
    joined = " ".join(_floor()["editable_not_creatable"]).lower()
    assert "merge" in joined
    assert not set(_floor()["editable_not_creatable"]) & set(_floor()["creatable"])


def test_ac5_the_projection_is_still_pure_code_truth():
    """The creatable set stays projected off ``InsertRequest.content`` — the table kind
    rides the existing ``NewBlock`` union member, so no hand-list appeared."""
    cc = _floor()
    assert cc["creatable"] == ["NewBlock", "NewParagraph"]
    assert cc["projected_from"] == "larkdocio.write.model.InsertRequest.content"
    for field in ("rows", "header_row"):
        assert field in cc["creatable_content_fields"], cc["creatable_content_fields"]


# =========================================================================== #
# AC6 — the composition the story exists for: create a table, then EDIT a cell  #
#        through the shipped TableLocator path (offline, end to end)             #
# =========================================================================== #

def test_ac6_a_created_table_is_addressable_by_the_shipped_table_locator():
    """The create → edit composition: author a table, let Lark provision it (the encoder's
    own payload + the reader's own parse), then resolve a ``TableLocator`` against the
    parsed tree — the created table is a first-class edit target, closing the
    editable-but-not-creatable gap from the other side."""
    tree = _tree_of(_HEADERED_3X3)
    plan = dry_run([EditRequest(
        anchor=TableLocator(row_key="On-time delivery", column_header="Value"),
        replacement="99.9%",
    )], tree)
    assert len(plan.refusals) == 0, plan.refusals
    assert len(plan.resolved) == 1
    entry = plan.resolved[0]
    assert (entry.cell.row, entry.cell.column) == (1, 1)
    assert entry.before == "97.2%"


def test_ac6_the_created_table_cell_edit_applies_through_the_gate():
    """…and the resolved cell edit really patches that cell's inner text block through the
    unchanged W2 apply path (the DOUBLE re-validation), so the composition is proven end
    to end, not merely resolvable."""
    tree = _tree_of(_HEADERED_3X3)
    plan = dry_run([EditRequest(
        anchor=TableLocator(row_key="On-time delivery", column_header="Value"),
        replacement="99.9%",
    )], tree)
    cell = plan.resolved[0].cell
    opener = StubOpener([
        _block_payload(cell.key_text_block_id, [_run("On-time delivery")]),
        _block_payload(cell.target_text_block_id, [_run("97.2%")]),
        _patch_ok(),
    ])
    log = apply(plan, _client(opener), "doc123")
    assert log.entries[0].outcome == "applied"
    patch = _by_method(opener, "PATCH")[0]
    assert cell.target_text_block_id in patch["url"]
    assert patch["body"] == {
        "update_text_elements": {"elements": [{"text_run": {"content": "99.9%"}}]}}


def test_ac6_a_table_reaches_lark_only_through_a_dry_run_plan():
    """The gate is unchanged: a hand-built plan entry carrying a table cannot be applied."""
    with pytest.raises(TypeError):
        apply([PlanEntry.insert_resolved(
            reference=Anchor(quote="q"),
            content=(_HEADERED_3X3,),
            position="after",
            block_id="b1",
            insertion_point=None,
        )], _client(StubOpener([])), "doc123")


def test_ac6_a_dry_run_of_a_table_issues_no_write_and_previews_the_grid():
    """Zero writes at dry-run, and the mandatory preview shows the authored grid so an
    approval UX can render the table before a single call."""
    tree = _page(_para("p1", "anchor line"))
    opener = StubOpener([])
    plan = dry_run([_insert_blocks("anchor line", [_HEADERED_3X3])], tree)
    assert opener.requests == []
    shown = plan.to_dict()["entries"][0]["content"][0]
    assert shown["kind"] == "table"
    assert shown["rows"][0] == ["Metric", "Value", "Owner"]
    assert shown["header_row"] is True


def test_ac6_the_plan_round_trips_a_table_through_json():
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert_blocks("anchor line", [_HEADERED_3X3])], tree)
    entry = plan.entries[0]
    back = PlanEntry.from_dict(json.loads(json.dumps(entry.to_dict())))
    assert back.content == entry.content == (_HEADERED_3X3,)
