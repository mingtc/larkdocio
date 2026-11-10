"""LD-431 — a composed table taller than 9 rows AUTHORS, instead of failing at write time.

The bug: ``compose()`` accepted a 10-row table, ``dry_run()`` planned it, and Lark refused it
with ``1770001 invalid param`` **after** earlier batches had already been written — a
half-written document, and a refusal arriving from the network at exactly the point the
library's contract promises a compile-time one.

**The root cause is a construction artifact, measured** (`dev/table-row-boundary/findings.md`,
with every call indexed in the four ``probe_NN_summary.json`` roll-ups,
on four disposables the probes created and trashed): the *property-grid* form of
``create_children`` — the one where Lark **auto-provisions** the cells from
``row_size``/``column_size`` — validates **each axis at ≤ 9**. The same document, in the same
run, accepted a 10-row table two other ways. So the engine now **seeds at the ceiling and
grows**: it creates the table at ``min(axis, 9)`` and appends the remaining rows / columns with
``insert_table_row`` / ``insert_table_column``, which read back to ``row_size: 200`` (the
largest grid ``MAX_TABLE_CELLS`` can ever hand it) with no failure at any row.

**No row cap is invented** — a cap would memorialise a limit that is not Lark's. The one
number that *is* a ceiling is on the other axis: the 101st column answers
``1770010 "too many table column"`` in Lark's own words, so ``MAX_TABLE_COLUMNS = 100`` is
refused at **compile time**, beside ``table-cap``, before any network call.

And either way (LD-431 AC6) an API refusal mid-batch now **names the block it was writing** —
index within the composed content and kind, never the authored text, with Lark's own code and
message carried through unedited.

Everything here is offline: the growth calls are asserted against an injected transport, and
the error naming is driven by a client stub that **raises**. The live arm is
``tests/test_live_write_table_growth_gate.py`` (``pytest -m live_write``).
"""
import json

import pytest

from larkdocio.errors import LarkAPIError
from larkdocio.write import (
    MAX_TABLE_CELLS,
    MAX_TABLE_COLUMNS,
    NewBlock,
    RefusedError,
    apply,
    compose,
    dry_run,
)
from larkdocio.write.encode import MAX_CREATE_GRID_AXIS, encode_block, encode_content
from larkdocio.write.model import RefusalReason

from write_harness import (
    StubOpener, _block_payload, _by_method, _client, _page, _para, _parent_payload, _run,
)

from test_table_creation import _created, _insert_blocks, _table_block

# LD-431: this file pins MEASURED EXTERNAL TRUTH (the 9-per-axis create ceiling, the growth
# route, the 100-column ceiling Lark names itself) and one product contract (an API refusal
# names the block it was writing) — if any of it fails after a regeneration the product is
# wrong, not merely different. process/doctrine/conformance-tier.md § A.4.
pytestmark = pytest.mark.conformance

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



def _grid_md(rows, cols):
    """A GFM table of ``rows`` lines INCLUDING the header, ``cols`` wide."""
    out = [" | ".join(f"h{c}" for c in range(cols)),
           " | ".join("---" for _ in range(cols))]
    out += [" | ".join(f"r{r}c{c}" for c in range(cols)) for r in range(1, rows)]
    return "\n".join(f"| {line} |" for line in out)


def _tall_table(rows, cols, *, fill=""):
    return NewBlock.table([[fill] * cols for _ in range(rows)], header_row=True)


def _fill_responses(cell_ids):
    """The batched fill's answers: ONE document block list, then the batch_update calls
    (LD-481 — the per-cell ``get_block`` + ``patch_block`` pair is gone)."""
    from test_table_creation import _fill_responses as _batched
    return _batched(cell_ids)


# =========================================================================== #
# The measured create-time ceiling, and the seed the encoder emits             #
# =========================================================================== #

def test_the_create_time_grid_ceiling_is_the_measured_nine():
    """9 is not a guess: 9×3 and 9×5 created and read back, 10×3 and 10×5 answered
    ``1770001``, in one run on one disposable (`findings.md` § 1)."""
    assert MAX_CREATE_GRID_AXIS == 9


def test_a_table_within_the_ceiling_encodes_byte_identically_to_before():
    """Zero drift for every table that already worked — the growth path must be invisible
    to a grid Lark's property form already accepts."""
    assert encode_block(NewBlock.table([["a", "b"], ["c", "d"]], header_row=True)) == {
        "block_type": 31,
        "table": {"property": {"row_size": 2, "column_size": 2, "header_row": True}},
    }
    assert encode_block(_tall_table(9, 9))["table"]["property"] == {
        "row_size": 9, "column_size": 9, "header_row": True,
    }


@pytest.mark.parametrize("rows, cols, seed_rows, seed_cols", [
    (10, 3, 9, 3),
    (200, 1, 9, 1),
    (2, 40, 2, 9),
    (12, 15, 9, 9),
])
def test_an_oversize_grid_is_SEEDED_at_the_ceiling_not_sent_whole(
        rows, cols, seed_rows, seed_cols):
    """The payload that reaches ``create_children`` never declares an axis past 9 —
    that declaration is the thing Lark refuses."""
    prop = encode_block(_tall_table(rows, cols))["table"]["property"]
    assert prop["row_size"] == seed_rows
    assert prop["column_size"] == seed_cols


def test_the_encoded_child_carries_the_AUTHORED_grid_so_apply_can_grow_it():
    """The seed is not the truth — the authored grid travels beside it, because the apply
    engine is what turns one into the other."""
    encoded = encode_content((_tall_table(12, 15),))
    assert encoded[0].grid == (12, 15)
    assert encoded[0].kind == "table"
    assert encode_content((NewBlock.paragraph("hi"),))[0].grid is None


# =========================================================================== #
# The apply path — seed, grow, then fill                                      #
# =========================================================================== #

def _apply_tall(rows, cols, *, cell_ids, fill=""):
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert_blocks("anchor line", [_tall_table(rows, cols, fill=fill)])],
                   tree)
    grow_calls = max(0, rows - MAX_CREATE_GRID_AXIS) + max(0, cols - MAX_CREATE_GRID_AXIS)
    opener = StubOpener([
        _block_payload("p1", [_run("anchor line")], parent_id="root"),
        _parent_payload("root", ["p1"]),         # its LIVE parent → the index (LD-453)
        _created("tbl1"),
        *[{"code": 0, "data": {}} for _ in range(grow_calls)],
        _table_block("tbl1", cell_ids, col_size=cols),
        *(_fill_responses(cell_ids) if fill else []),
    ])
    log = apply(plan, _client(opener), "doc123")
    return opener, log


def test_a_ten_row_table_is_created_at_nine_then_grown_one_row_at_a_time():
    """The regression the consumer paid for: ``apply`` no longer hands Lark a 10-row
    property grid — it creates 9 and appends the tenth."""
    opener, log = _apply_tall(10, 3, cell_ids=[f"c{i}" for i in range(30)])

    posts = _by_method(opener, "POST")
    assert len(posts) == 1, "the shell is still ONE create call"
    assert posts[0]["body"]["children"][0]["table"]["property"]["row_size"] == 9
    grows = [p for p in _by_method(opener, "PATCH")
             if "insert_table_row" in json.dumps(p["body"])]
    assert [p["body"] for p in grows] == [{"insert_table_row": {"row_index": -1}}]
    assert all("/blocks/tbl1?" in p["url"] for p in grows), (
        "a growth call must address the table block itself")
    assert log.entries[0].outcome == "inserted"
    assert log.entries[0].created_block_ids == ("tbl1",)


def test_both_axes_grow_and_only_by_the_shortfall():
    """A 12×15 grid costs 3 row appends + 6 column appends — never one per line of the
    whole grid, and never one for an axis already within the ceiling."""
    opener, _log = _apply_tall(12, 15, cell_ids=[f"c{i}" for i in range(180)])
    bodies = [p["body"] for p in _by_method(opener, "PATCH")]
    assert bodies.count({"insert_table_row": {"row_index": -1}}) == 3
    assert bodies.count({"insert_table_column": {"column_index": -1}}) == 6


def test_a_grid_within_the_ceiling_issues_no_growth_call_at_all():
    """Zero drift, asserted on the wire: a 9×9 table's call sequence is what it always was."""
    opener, _log = _apply_tall(9, 9, cell_ids=[f"c{i}" for i in range(81)])
    assert _by_method(opener, "PATCH") == []


def test_after_growing_the_cell_ids_are_RE_READ_not_taken_from_the_create_response():
    """The create response lists the cells of the **seed** grid; after growth that list is
    short by exactly the appended rows, and filling against it would strand content."""
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert_blocks("anchor line", [_tall_table(10, 1, fill="x")])], tree)
    all_cells = [f"c{i}" for i in range(10)]
    opener = StubOpener([
        _block_payload("p1", [_run("anchor line")], parent_id="root"),
        _parent_payload("root", ["p1"]),         # its LIVE parent → the index (LD-453)
        _created(("tbl1", all_cells[:9])),          # the SEED's nine cells
        {"code": 0, "data": {}},                    # the growth call
        _table_block("tbl1", all_cells, col_size=1),
        *_fill_responses(all_cells),
    ])
    apply(plan, _client(opener), "doc123")

    gets = [r["url"].split("/blocks")[1].split("?")[0] for r in _by_method(opener, "GET")]
    assert "/tbl1" in gets, (
        "the grown table was not re-read — the stale nine-cell list would drop a row")
    written = [request["block_id"]
               for p in _by_method(opener, "PATCH") if "batch_update" in p["url"]
               for request in p["body"]["requests"]]
    assert written == [f"{c}t" for c in all_cells], "every authored cell must be written"


# =========================================================================== #
# The OTHER axis — a measured ceiling, refused before the network              #
# =========================================================================== #

def test_the_column_ceiling_is_the_measured_hundred():
    """Lark's own sentence at the 101st column: ``1770010 too many table column``
    (`findings.md` § 4). Not an estimate — the number in the capture."""
    assert MAX_TABLE_COLUMNS == 100


def test_a_table_past_the_column_ceiling_is_refused_at_construction():
    """Under the cell cap a 1×150 grid is composable, so without this it would fail
    live — the exact failure mode this issue exists to end."""
    with pytest.raises(ValueError) as exc:
        NewBlock.table([[""] * 150], header_row=True)
    message = str(exc.value)
    assert "150" in message and str(MAX_TABLE_COLUMNS) in message
    assert "column cap" in message
    assert "split the table" in message.lower()
    assert NewBlock.table([[""] * MAX_TABLE_COLUMNS], header_row=True).column_count == 100


def test_the_column_refusal_does_not_disturb_the_cell_cap():
    """``table-cap`` keeps its own label and its own ordering: a grid over the cell cap
    still refuses as the cell cap, and the cell cap is checked first, so no existing refusal
    changes label.

    **The cap's VALUE was superseded 200 → 500 (LD-481)** — the fill no longer costs a pair
    of throttled calls per cell, so the budget that number expressed no longer describes
    anything. The assertion is transformed rather than struck: what it exists to hold is
    that the two caps stay distinct and ordered, and it still holds exactly that at the
    number the code now carries."""
    assert MAX_TABLE_CELLS == 500
    with pytest.raises(ValueError) as exc:
        NewBlock.table([["x"] * 8 for _ in range(80)])       # 640 cells, 8 columns
    assert "cell" in str(exc.value) and "column cap" not in str(exc.value)


def test_compose_labels_the_column_refusal_with_its_own_construct():
    """A refusal a consumer greps for must not arrive wearing the cell cap's name.

    The reachable shape is a **header-only** wide table: with two rows a 101-column grid is
    already 202 cells, so the older cell cap answers first (and keeps its label — that is
    the zero-drift ordering, asserted above)."""
    with pytest.raises(RefusedError) as exc:
        compose(_grid_md(1, 150))
    refusal = exc.value.refusal
    assert refusal.reason is RefusalReason.NOT_IN_DIALECT
    assert refusal.detail.startswith("table-column-cap at line "), refusal.detail
    assert str(MAX_TABLE_COLUMNS) in refusal.detail


def test_a_tall_table_now_composes_and_plans_and_the_payload_is_sendable():
    """End to end, offline: the shape that used to blow up at ``apply`` compiles to a
    seed payload Lark's own validator accepts."""
    content = tuple(compose(_grid_md(40, 5)))
    assert len(content) == 1 and content[0].row_count == 40
    prop = encode_block(content[0])["table"]["property"]
    assert (prop["row_size"], prop["column_size"]) == (9, 5)


# =========================================================================== #
# AC6 — an API refusal names the block it was writing                          #
# =========================================================================== #

class _RaisingClient:
    """A client stub that answers the reference read, then refuses the create."""

    def __init__(self, *, fail_on_call=1):
        self.calls = 0
        self.fail_on_call = fail_on_call

    def get_block(self, document_id, block_id):
        # LD-453: the insert path also reads the reference's LIVE parent for its index, so
        # the root must list the reference — else the entry refuses stale before creating.
        return {"block_id": block_id, "block_type": 2, "parent_id": "root",
                "text": {"elements": [{"text_run": {"content": "anchor line"}}]},
                "children": ["p1"] if block_id == "root" else []}

    def read_document_revision(self, document_id):
        return 1

    def create_children(self, document_id, block_id, children, index=-1):
        self.calls += 1
        if self.calls >= self.fail_on_call:
            raise LarkAPIError("create children failed: Code: 1770001, Msg: invalid param")
        return {"children": [{"block_id": f"b{i}"} for i in range(len(children))]}


def _refusal_detail(log):
    """The classified refusal ``detail`` of the one entry that failed.

    LD-643 — the naming these cases pin (index + kind, Lark's own code/msg, never the
    authored text) is unchanged; the apply-time disposition boundary changed only WHERE a
    consumer reads it. ``_naming_the_block`` still re-raises with the block named, and
    ``apply()`` now catches that named error one level out and puts its message verbatim into
    the log entry, which is the thing a caller keeps.
    """
    failing = [e for e in log.entries if e.refusal is not None]
    assert len(failing) == 1, [e.outcome for e in log.entries]
    return failing[0].refusal.detail


def test_an_api_refusal_names_the_block_index_and_kind():
    """The consumer's own cheapest good idea: a bisect over 200 blocks becomes one line."""
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert_blocks("anchor line", [NewBlock.table([["a"]])])], tree)
    # TRANSFORMED, NOT STRUCK (LD-643): every assertion below is the one this test has always
    # made — Lark's code and message unedited, the index, the kind. What moved is the CARRIER:
    # since the apply-time disposition boundary, the named refusal reaches the consumer as the
    # log entry's `detail` instead of as a traceback, so the bisect it saves is still one line
    # and the batch's record survives with it.
    message = _refusal_detail(apply(plan, _RaisingClient(), "doc123", allow_partial=True))
    assert "Code: 1770001, Msg: invalid param" in message, (
        "Lark's own code and message must be carried through unedited")
    assert "index 0" in message
    assert "table" in message


def test_the_naming_reports_the_whole_batch_when_the_batch_is_not_one_block():
    """``create_children`` refuses a batch, not a block, and the engine does not guess
    which member was at fault — it names the range and the kinds, which is the slice of
    the composed content the consumer has to look at."""
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert_blocks("anchor line", [
        NewBlock.heading(1, "H"), NewBlock.paragraph("p"), NewBlock.table([["a"]]),
    ])], tree)
    message = _refusal_detail(apply(plan, _RaisingClient(), "doc123", allow_partial=True))
    assert "indexes 0-2" in message
    assert "heading" in message and "paragraph" in message and "table" in message


def test_the_error_never_carries_the_authored_TEXT():
    """A caller's content may be sensitive and an error string ends up in logs — index and
    kind only."""
    secret = "SENSITIVE-TEXT-4f2b"
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert_blocks("anchor line", [
        NewBlock.paragraph(secret), NewBlock.table([[secret]]),
    ])], tree)
    assert secret not in _refusal_detail(apply(plan, _RaisingClient(), "doc123", allow_partial=True))


def test_a_failure_while_GROWING_a_table_names_that_exact_block():
    """A growth call is per-block, so the naming is exact rather than a range."""
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert_blocks("anchor line", [
        NewBlock.paragraph("intro"), _tall_table(10, 1),
    ])], tree)
    opener = StubOpener([
        _block_payload("p1", [_run("anchor line")], parent_id="root"),
        _parent_payload("root", ["p1"]),         # its LIVE parent → the index (LD-453)
        _created("b0", "tbl1"),
        {"code": 1770010, "msg": "too many table column"},
    ])
    message = _refusal_detail(apply(plan, _client(opener), "doc123"))
    assert "1770010" in message and "too many table column" in message
    assert "index 1" in message and "table" in message
