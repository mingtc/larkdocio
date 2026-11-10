"""LD-481 — the table fill costs what the platform charges, and the cap says why.

The bug: filling an authored table spent **two throttled calls per non-empty cell** (a
``get_block`` to find the cell's inner text block, then a ``patch_block`` on it), and
``MAX_TABLE_CELLS = 200`` was the budget written *for that cost* (LD-135). A consumer's
ordinary 6×36 = 216-cell table was therefore refused offline, at construction, by a number
that is **larkdocio's and not Lark's** — measured 2026-08-14 at **463 write API calls /
158.41 s** for those 216 cells, against **one 0.82 s call** for the identical content through
Lark's own ``descendant`` route (spike ``dev/spikes/2026-08-14-table-cell-creation-cap.md``
§ 3c).

What this file pins, all offline against an **injected transport** — the call SEQUENCE and the
batching arithmetic, not a happy return:

* the two new client routes — ``batch_update_blocks`` (``PATCH …/blocks/batch_update``,
  measured working at 48 updates in one call) and ``list_document_blocks`` (the paginated
  document block list);
* that the per-cell ``get_block`` loop **does not come back**: a fill reads the document's
  blocks **once** and writes the cells in ``⌈cells/48⌉`` batched calls, row-major;
* the cap at its **superseded** value and the refusal text that now names the real envelope.

The live arm — the 6×36 case end to end, with the call count measured on the wire — is
``tests/test_live_write_batched_table_fill_gate.py`` (``pytest -m live_write``).
"""
import math

import pytest

from larkdocio.errors import LarkAPIError
from larkdocio.write import (
    MAX_TABLE_CELLS,
    NewBlock,
    RefusedError,
    apply,
    compose,
    dry_run,
)
from larkdocio.write.client import MAX_BATCH_UPDATES_PER_CALL
from larkdocio.write.encode import MAX_CREATE_GRID_AXIS
from larkdocio.write.model import RefusalReason

from write_harness import (
    StubOpener, _block_payload, _by_method, _client, _methods, _page, _para,
    _parent_payload, _run,
)

from test_table_creation import _created, _insert_blocks, _table_block

# LD-481: the batch envelope and the one-call cell envelope are MEASURED EXTERNAL TRUTH; the
# fill's call shape is the product contract this issue bought. If either fails after a
# regeneration the product is wrong, not merely different.
# process/doctrine/conformance-tier.md § A.4.
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



# --------------------------------------------------------------------------- #
# transport payload builders for the new routes                                #
# --------------------------------------------------------------------------- #

def _block_list_page(blocks, *, page_token=None, has_more=False):
    """A ``GET …/documents/{id}/blocks`` page: ``data.items`` + the cursor fields."""
    data = {"items": list(blocks), "has_more": has_more}
    if page_token is not None:
        data["page_token"] = page_token
    return {"code": 0, "data": data}


def _cell_blocks(cell_ids, *, table_id="tbl1", bare=()):
    """The listing rows for a provisioned grid: each type-32 cell wrapping one text block.

    ``bare`` names the cells that come back **without** an inner block — the defensive shape
    the fill must still author into rather than drop.
    """
    rows = [{"block_id": table_id, "block_type": 31, "children": list(cell_ids)}]
    for cell_id in cell_ids:
        rows.append({
            "block_id": cell_id, "block_type": 32, "parent_id": table_id,
            "children": [] if cell_id in bare else [f"{cell_id}t"],
        })
        if cell_id not in bare:
            rows.append({"block_id": f"{cell_id}t", "block_type": 2, "parent_id": cell_id,
                         "children": []})
    return rows


def _batch_ok():
    return {"code": 0, "data": {"blocks": []}}


def _fill_responses(cell_ids, *, table_id="tbl1", bare=(), batches=None):
    """The queued responses for a batched fill: ONE block list, then the batch calls."""
    if batches is None:
        written = [c for c in cell_ids if c not in bare]
        batches = max(0, math.ceil(len(written) / MAX_BATCH_UPDATES_PER_CALL))
    return [_block_list_page(_cell_blocks(cell_ids, table_id=table_id, bare=bare)),
            *[_batch_ok() for _ in range(batches)]]


def _apply_table(rows, *, cell_ids, bare=(), extra=()):
    """Author one table through the real front door against an injected transport.

    Queues exactly the responses the engine asks for: the anchor + live-parent reads, the
    create, one growth answer per axis shortfall (LD-431), the grown grid's re-read, then
    this issue's shape — ONE block list and ``⌈cells/48⌉`` batch answers.
    """
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert_blocks("anchor line", [NewBlock.table(rows)])], tree)
    n_rows, n_cols = len(rows), len(rows[0])
    grows = (max(0, n_rows - MAX_CREATE_GRID_AXIS)
             + max(0, n_cols - MAX_CREATE_GRID_AXIS))
    texts = [t for row in rows for t in row]
    written = [c for c, text in zip(cell_ids, texts) if text and c not in bare]
    filling = [c for c, text in zip(cell_ids, texts) if text]
    opener = StubOpener([
        _block_payload("p1", [_run("anchor line")], parent_id="root"),
        _parent_payload("root", ["p1"]),
        _created("tbl1") if grows else _created(("tbl1", list(cell_ids))),
        *[{"code": 0, "data": {}} for _ in range(grows)],
        *([_table_block("tbl1", cell_ids, col_size=n_cols)] if grows else []),
        *([_block_list_page(_cell_blocks(cell_ids, bare=bare))] if filling else []),
        *[_batch_ok()
          for _ in range(math.ceil(len(written) / MAX_BATCH_UPDATES_PER_CALL))],
        *extra,
    ])
    log = apply(plan, _client(opener), "doc123")
    return opener, log


def _batch_bodies(opener):
    return [r["body"] for r in opener.requests
            if r["method"] == "PATCH" and "batch_update" in r["url"]]


# =========================================================================== #
# AC1 — the client speaks batch_update, and the envelope is the MEASURED one    #
# =========================================================================== #

def test_ac1_batch_update_blocks_patches_the_documents_batch_update_route():
    from test_write_client import StubOpener as ClientStub, _client as _bare_client

    opener = ClientStub([{"code": 0, "data": {"blocks": []}}])
    client = _bare_client(opener)

    updates = [
        {"block_id": "b1", "update_text_elements": {"elements": []}},
        {"block_id": "b2", "update_text_elements": {"elements": []}},
    ]
    data = client.batch_update_blocks("doc123", updates)

    req = opener.requests[0]
    assert req["method"] == "PATCH"
    assert "/open-apis/docx/v1/documents/doc123/blocks/batch_update" in req["url"]
    assert "document_revision_id=-1" in req["url"]
    assert req["body"] == {"requests": updates}
    assert req["auth"] == "Bearer t-test"
    assert data == {"blocks": []}


def test_ac1_an_empty_batch_is_not_sent_at_all():
    """A call that would say nothing costs a throttled slot for nothing."""
    from test_write_client import StubOpener as ClientStub, _client as _bare_client

    opener = ClientStub([])
    assert _bare_client(opener).batch_update_blocks("doc123", []) is None
    assert opener.requests == []


def test_ac1_the_batch_envelope_is_the_measured_forty_eight():
    """48 is not a guess: 48 cell texts updated in ONE call, ``code 0``, all 48 read back
    (spike § 3c, on a disposable the probe created and trashed). 40 and 3 likewise."""
    assert MAX_BATCH_UPDATES_PER_CALL == 48


def test_ac1_a_non_zero_code_from_the_batch_route_raises_typed():
    from test_write_client import StubOpener as ClientStub, _client as _bare_client

    opener = ClientStub([{"code": 1770001, "msg": "invalid param"}])
    with pytest.raises(LarkAPIError) as e:
        _bare_client(opener).batch_update_blocks("doc123", [{"block_id": "b1"}])
    assert "1770001" in str(e.value)


# =========================================================================== #
# AC2 — the cell ids come from ONE document block list, not one GET per cell    #
# =========================================================================== #

def test_ac2_list_document_blocks_walks_the_cursor_to_exhaustion():
    from test_write_client import StubOpener as ClientStub, _client as _bare_client

    opener = ClientStub([
        _block_list_page([{"block_id": "a"}], page_token="p2", has_more=True),
        _block_list_page([{"block_id": "b"}], has_more=False),
    ])
    blocks = _bare_client(opener).list_document_blocks("doc123")

    assert [b["block_id"] for b in blocks] == ["a", "b"]
    assert [r["method"] for r in opener.requests] == ["GET", "GET"]
    assert "/open-apis/docx/v1/documents/doc123/blocks?" in opener.requests[0]["url"]
    assert "page_size=500" in opener.requests[0]["url"]
    assert "page_token" not in opener.requests[0]["url"]
    assert "page_token=p2" in opener.requests[1]["url"]


def test_ac2_the_fill_reads_the_document_blocks_ONCE_and_never_per_cell():
    """THE regression this issue exists to keep dead: 2 API calls per cell.

    A 4-cell table used to cost 4 ``get_block`` + 4 ``patch_block``. It now costs one
    document block list and one batched update — and the per-cell GET must never return.
    """
    opener, log = _apply_table([["H1", "H2"], ["a", "b"]],
                               cell_ids=["c0", "c1", "c2", "c3"])

    gets = [r["url"] for r in _by_method(opener, "GET")]
    assert not any("/blocks/c" in u for u in gets), (
        "a per-cell get_block came back — the fill is 2 calls/cell again")
    listings = [u for u in gets if "/blocks?" in u]
    assert len(listings) == 1, f"the document block list must be read once: {gets}"
    assert log.entries[0].outcome == "inserted"
    assert log.entries[0].created_block_ids == ("tbl1",)


def test_ac2_the_cells_are_written_row_major_in_one_batched_call():
    opener, _log = _apply_table([["H1", "H2"], ["a", "b"]],
                                cell_ids=["c0", "c1", "c2", "c3"])

    bodies = _batch_bodies(opener)
    assert len(bodies) == 1, bodies
    assert bodies[0] == {"requests": [
        {"block_id": f"c{i}t",
         "update_text_elements": {"elements": [{"text_run": {"content": t}}]}}
        for i, t in enumerate(("H1", "H2", "a", "b"))
    ]}


@pytest.mark.parametrize("shape, sizes", [
    ((1, 48), [48]),
    ((1, 49), [48, 1]),
    ((1, 96), [48, 48]),
    ((3, 72), [48, 48, 48, 48, 24]),        # 216 cells — the consumer's cell count
])
def test_ac2_the_batching_arithmetic_is_ceil_cells_over_the_envelope(shape, sizes):
    """216 cells ⇒ **5** batched calls, where the shipped path spent 432."""
    rows_n, cols_n = shape
    rows = [[f"r{r}c{c}" for c in range(cols_n)] for r in range(rows_n)]
    cells = rows_n * cols_n
    cell_ids = [f"c{i}" for i in range(cells)]
    opener, _log = _apply_table(rows, cell_ids=cell_ids)

    bodies = _batch_bodies(opener)
    assert len(bodies) == len(sizes)
    assert [len(b["requests"]) for b in bodies] == sizes
    assert sum(len(b["requests"]) for b in bodies) == cells


def test_ac2_an_empty_cell_still_costs_no_write_and_keeps_row_major_order():
    opener, _log = _apply_table([["a", ""], ["", "d"]],
                                cell_ids=["c0", "c1", "c2", "c3"])
    bodies = _batch_bodies(opener)
    assert len(bodies) == 1
    assert [r["block_id"] for r in bodies[0]["requests"]] == ["c0t", "c3t"]


def test_ac2_a_grid_of_only_empty_cells_reads_nothing_at_all():
    """Nothing to fill ⇒ the block list is not even read."""
    opener, _log = _apply_table([["", ""], ["", ""]], cell_ids=["c0", "c1", "c2", "c3"])
    assert _methods(opener) == ["GET", "GET", "POST"], opener.requests


def test_ac2_a_cell_listed_without_an_inner_block_is_still_authored_into():
    """The defensive shape survives the rewrite: a bare cell gets a text block CREATED
    inside it rather than having its authored content dropped."""
    opener, _log = _apply_table([["a", "b"]], cell_ids=["c0", "c1"], bare=("c0",),
                                extra=[_created("c0newtext")])
    posts = _by_method(opener, "POST")
    assert len(posts) == 2 and "/blocks/c0/children" in posts[1]["url"]
    assert posts[1]["body"]["children"] == [
        {"block_type": 2, "text": {"elements": [{"text_run": {"content": "a"}}]}}]
    bodies = _batch_bodies(opener)
    assert [r["block_id"] for r in bodies[0]["requests"]] == ["c1t"]


def test_ac2_a_cell_the_listing_never_carried_is_SAID_not_silently_dropped():
    """A cell that is not in the document listing cannot be addressed at all — say so,
    rather than silently leaving the consumer's text unwritten.

    **RENAMED with its body (LD-643).** The old name was ``…_raises_instead_of_dropping_
    content``; the apply-time disposition boundary is what moved the raise into the log, and a
    guard whose name promises a raise its body no longer asserts is the next reader's trap.
    The rule — the unaddressable cell is named, never quietly skipped — is unchanged.
    """
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert_blocks("anchor line", [NewBlock.table([["a", "b"]])])], tree)
    opener = StubOpener([
        _block_payload("p1", [_run("anchor line")], parent_id="root"),
        _parent_payload("root", ["p1"]),
        _created(("tbl1", ["c0", "c1"])),
        _block_list_page(_cell_blocks(["c0"])),          # c1 is missing from the listing
    ])
    # TRANSFORMED, NOT STRUCK (LD-643): the rule is unchanged — an unaddressable cell is
    # SAID, never silently left unwritten — and the id is still named. What moved is where it
    # is said: the apply-time disposition boundary now types the failure into the log instead
    # of letting it escape, so the caller keeps the record of what the batch had already done.
    # The table itself WAS created, which is why this is applied-unverified and not a refusal.
    log = apply(plan, _client(opener), "doc123")
    entry = log.entries[0]
    assert entry.outcome == "applied-unverified"
    assert entry.refusal.reason.value == "unverified-write"
    assert "c1" in entry.refusal.detail


def test_ac2_the_cost_shape_of_the_consumers_six_by_thirty_six_table():
    """The whole point, counted on the wire: ``1 create + 27 grow + 1 re-read + 1 list +
    5 batch`` — tens of calls, where the shipped path spent 463 (spike § 3c)."""
    tree = _page(_para("p1", "anchor line"))
    rows = [[f"r{r}c{c}" for c in range(6)] for r in range(36)]
    plan = dry_run([_insert_blocks("anchor line", [NewBlock.table(rows)])], tree)
    cell_ids = [f"c{i}" for i in range(216)]
    opener = StubOpener([
        _block_payload("p1", [_run("anchor line")], parent_id="root"),
        _parent_payload("root", ["p1"]),
        _created("tbl1"),
        *[{"code": 0, "data": {}} for _ in range(27)],       # the grow calls
        _table_block("tbl1", cell_ids, col_size=6),          # the grown grid re-read
        *_fill_responses(cell_ids),
    ])
    apply(plan, _client(opener), "doc123")

    assert len(opener.requests) == 37, [
        (r["method"], r["url"]) for r in opener.requests]
    assert len(_batch_bodies(opener)) == 5
    written = [r["block_id"] for b in _batch_bodies(opener) for r in b["requests"]]
    assert written == [f"c{i}t" for i in range(216)], "row-major order, end to end"


def test_ac2_the_batch_bodies_carry_the_same_update_the_per_cell_patch_carried():
    """Zero drift in what lands in a cell: the batched request is the identical
    ``update_text_elements`` body a whole-cell edit builds, plus the block it addresses."""
    opener, _log = _apply_table([["hello"]], cell_ids=["c0"])
    request = _batch_bodies(opener)[0]["requests"][0]
    assert set(request) == {"block_id", "update_text_elements"}
    assert request["update_text_elements"] == {
        "elements": [{"text_run": {"content": "hello"}}]}


# =========================================================================== #
# AC3 — the cap moved, under the supersession rule                             #
# =========================================================================== #

def test_ac3_the_cell_cap_is_the_measured_five_hundred():
    """Superseded from 200 (LD-135's cost budget) to 500, anchored on Lark's own one-call
    envelope: 999 descendants pass, 1001 fail, ``descendants = 2 × cells + 1`` ⇒ 499 cells
    (spike § 3b). 500 is the round number one cell above the measured pass."""
    assert MAX_TABLE_CELLS == 500


#: LD-135's recorded reason, word for word as it stood at 1.33.0 (``requests.py:177-184``).
#: It is the HISTORICAL reason and it does not change; the conclusion it once justified
#: (``MAX_TABLE_CELLS = 200``) is what this issue replaces.
LD_135_REASON = (
    "each **non-empty** cell then costs its own pair of throttled calls (read the cell to "
    "find its inner text block, patch that block), so a grid's cost is linear in its cells "
    "at ≤3 writes/sec — a 200-cell table is already ~400 serialized calls"
)


def _cap_comment_block():
    """The ``#:`` comment block immediately above ``MAX_TABLE_CELLS``, as one line."""
    import larkdocio.write.model.requests as requests_module

    with open(requests_module.__file__, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    index = next(i for i, line in enumerate(lines)
                 if line.startswith("MAX_TABLE_CELLS")) - 1
    block = []
    while lines[index].startswith("#:"):
        block.append(lines[index][2:].strip())
        index -= 1
    return " ".join(reversed(block))


def test_ac3_the_constant_keeps_LD_135s_reason_verbatim_as_the_historical_one():
    """Supersession, not a strike: the reason survives word for word and only the
    CONCLUSION moves (``process/doctrine/supersession.md`` § A.1). A rationale-free strike
    is what gets a settled argument re-litigated."""
    assert LD_135_REASON in _cap_comment_block()


@pytest.mark.parametrize("fragment", [
    "LD-135",                       # whose conclusion moved
    "LD-481",                       # what moved it
    "BATCHED",                      # WHAT CHANGED: the per-cell cost math
    "499",                          # the measured anchor
    "1000 descendants",             # what that anchor is a ceiling on
    "measured",                     # labelled a measurement, not a budget guess
    "tenant_access_token",          # its D-59 route scope
])
def test_ac3_the_new_conclusion_says_what_changed_and_what_anchors_it(fragment):
    assert fragment in _cap_comment_block()


def test_ac3_no_shipped_prose_still_calls_200_THE_CEILING():
    """The supersession has to reach every sentence that read the old conclusion back as a
    fact about the world, not just the constant. ``_grow_table_grid``'s LD-431 note glossed
    its measurement — *the row axis grew to 200* — as "the MAX_TABLE_CELLS ceiling, i.e. as
    far as anything can ask for". The MEASUREMENT stays true and is not touched; the gloss
    is false at 500, and worse, it is false in the direction that invents a platform limit
    LD-431 never found. It is TRANSFORMED (what was measured, and that past it is unmeasured
    rather than refused), never struck."""
    import importlib

    # ``larkdocio.write.apply`` the ATTRIBUTE is the public function; the module is reached
    # through the import machinery, not through attribute access on the package.
    apply_module = importlib.import_module("larkdocio.write.apply")
    with open(apply_module.__file__, encoding="utf-8") as handle:
        source = handle.read()
    start = source.index("def _grow_table_grid")
    doc = source[start:source.index('"""', source.index('"""', start) + 3)]

    assert "the row axis grew to **200**" in doc, (
        "LD-431's measurement is evidence and does not move")
    assert "as far as anything can ask for" not in doc, (
        "200 is no longer the cap, so it cannot be glossed as the most anything can ask for")
    assert "unmeasured" in doc, (
        "rows past LD-431's 200 are unmeasured, not refuted — say so (D-59)")


def test_ac3_a_table_at_exactly_the_new_cap_is_accepted_and_one_past_is_refused():
    at_cap = NewBlock.table([["x"] * 10 for _ in range(MAX_TABLE_CELLS // 10)])
    assert at_cap.row_count * at_cap.column_count == MAX_TABLE_CELLS
    with pytest.raises(ValueError):
        NewBlock.table([["x"] * 10 for _ in range(MAX_TABLE_CELLS // 10 + 1)])


def test_ac3_the_consumers_six_by_thirty_six_table_now_composes():
    """216 cells — the exact grid the consumer was refused."""
    md = "\n".join(
        ["| " + " | ".join(f"h{c}" for c in range(6)) + " |", "|" + "---|" * 6]
        + ["| " + " | ".join(f"r{r}c{c}" for c in range(6)) + " |" for r in range(1, 36)]
    )
    content = tuple(compose(md))
    assert len(content) == 1
    assert (content[0].row_count, content[0].column_count) == (36, 6)


# =========================================================================== #
# AC4 — the refusal names the real envelope, the real owner, and what to do     #
# =========================================================================== #

def _cap_refusal_message():
    with pytest.raises(ValueError) as e:
        NewBlock.table([["x"] * 10 for _ in range(MAX_TABLE_CELLS // 10 + 1)])
    return str(e.value)


@pytest.mark.parametrize("fragment", [
    "510 cells",                       # what was asked for
    "500-cell",                        # the cap, named
    "larkdocio's own",                 # whose cap it is
    "499",                             # the measured one-call envelope
    "1000 descendants",                # what that envelope is a ceiling on
    "100 columns",                     # Lark's own ceiling, which this is NOT
    "1770010",                         # in Lark's own words
    "no row cap",                      # the ceiling that does not exist
    "never truncated",                 # the standing promise
])
def test_ac4_the_construction_refusal_states_the_envelope_and_the_owner(fragment):
    assert fragment in _cap_refusal_message()


def test_ac4_the_refusal_prescribes_a_SIZE_to_split_into_not_a_bare_split():
    message = _cap_refusal_message()
    assert "500 cells or fewer" in message or "≤500 cells" in message, message


@pytest.mark.parametrize("fragment", ["500", "499", "larkdocio's own", "100 columns"])
def test_ac4_composes_table_cap_refusal_says_the_same_things(fragment):
    md = "\n".join(
        ["| " + " | ".join(f"h{c}" for c in range(6)) + " |", "|" + "---|" * 6]
        + ["| " + " | ".join(f"r{r}c{c}" for c in range(6)) + " |" for r in range(1, 90)]
    )
    with pytest.raises(RefusedError) as e:
        compose(md)
    refusal = e.value.refusal
    assert refusal.reason is RefusalReason.NOT_IN_DIALECT
    assert refusal.detail.startswith("table-cap at line "), refusal.detail
    assert fragment in refusal.detail


def test_ac4_the_refusal_still_fires_at_construction_with_ZERO_api_calls():
    """Preserved exactly: the refusal precedes ``dry_run`` entirely, so nothing is
    half-written and no request is issued."""
    opener = StubOpener([])
    _client(opener)                      # a client exists; it is never asked for anything
    with pytest.raises(ValueError):
        NewBlock.table([["x"] * 10 for _ in range(MAX_TABLE_CELLS // 10 + 1)])
    assert opener.requests == []


def test_ac4_the_column_cap_keeps_its_own_label_under_the_raised_cell_cap():
    """A 1×150 header-only grid is 150 cells — well under the raised cap — so the column
    refusal is the one that fires, and it is still Lark's number, not ours."""
    with pytest.raises(ValueError) as e:
        NewBlock.table([[""] * 150], header_row=True)
    assert "column cap" in str(e.value) and "1770010" in str(e.value)
    assert "cell" not in str(e.value).split("column cap")[0]
