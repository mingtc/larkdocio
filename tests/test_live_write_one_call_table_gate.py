"""THE LD-482 GATE — the consumer's 6×36 table authors in ONE call, at the right position.

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*``,
``LARKDOCIO_DISPOSABLES_FOLDER`` and network). Run it with the whole ring::

    pytest -m live_write

Three claims live only on the wire, and every one of them is what this gate is for:

1. **the envelope** — Lark takes a whole table subtree (grid, cells, cell text) in one
   ``descendant`` call. Measured: a consumer's exact 36×6 = 216-cell table went
   in as **one call, 0.82 s, code 0**, read back ``row_size 36, column_size 6``, against
   463 calls / 158.41 s through the pre-LD-481 fill;
2. **the position** — the lifted-out table must land **beside its own reference**, in a mixed
   batch as well as alone. This is the binding gate of the issue, and it is the one an offline
   double cannot settle: the double applies the engine's own arithmetic to its own tree, while
   only Lark decides what ``index`` means on the ``descendant`` route (every capture behind the
   route used ``index: -1``, so a **positive** index there is what this gate measures first).
   **LD-496 made that leg discriminate.** The seed carries a **trailing paragraph after
   ``TABLE_ANCHOR``**, so the derived index is provably **mid-list** rather than the append
   position, and the read-back asserts the table landed *between* its anchor and that trailing
   block — a route that ignored ``index`` and appended now visibly fails, where before it read
   back identically. The ``index`` integer is read off the ``/descendant`` request body on the
   wire and printed with the observed child order, so the verdict is auditable without a rerun;
3. **atomicity** — a subtree Lark refuses leaves **nothing**, where the three-movement route
   could leave a half-grown or half-filled table in a real document.

**How this arm divides the question with the LD-481 arm** (LD-578). Both author the consumer's
same 216-cell grid, so the division is stated rather than assumed: **this** arm owns the
**SHAPE** — exactly one ``/descendant`` call, at the derived index, atomic when Lark refuses —
while ``tests/test_live_write_batched_table_fill_gate.py`` owns the **COST**: how many calls, of
whatever family, the grid spends, and that no call is spent per cell. That arm's pin was
originally cut on route 2's ⌈cells/48⌉ ``batch_update`` arithmetic and went stale the day this
route shipped; it is now family-agnostic, so a future route change reddens the arm whose
question actually moved, and only that one.

The ring, against documents it **creates and destroys itself** (never the read canary, never
the block-zoo doc, never the standing write scratch doc, never a real document), in a folder
the caller supplied:

1. **creates its own disposable doc** and seeds a heading + three paragraphs — two distinct
   reference anchors for a MIXED batch, plus the trailing block that keeps the table's index
   off the end of the list;
2. downloads + parses it **twice**, asserting byte-identity — the determinism control that
   makes any later diff attributable to the write;
3. applies ONE batch carrying a paragraph insert after the first anchor and the 216-cell table
   insert after the second, through the shipped front door (``compose(markdown)`` → ``dry_run``
   → ``apply``), **counting every HTTP request the write client issues**;
4. asserts the table cost **exactly one** ``/descendant`` call and **no** grow or fill call;
5. **THE VERDICT — a fresh read-back**, never the write's own ``code: 0``: the live block
   order (paragraph and table each beside their own anchor, the table strictly *before* the
   trailing block and the wire ``index`` positive), ``row_size 36`` /
   ``column_size 6``, 216 cells in **row-major** order at the spike's own probe points, and
   the reader's Markdown carrying every authored line;
6. **the atomicity leg** — a second disposable takes a table one cell past the envelope
   through the raw route and asserts Lark refuses it AND that the document is untouched;
7. **tears down** both documents in a ``finally`` so nothing persists.
"""
import difflib
import json
import time
import urllib.request

import pytest

import canary_support
from larkdocio.common import get_read_credentials, get_write_credentials
from larkdocio.errors import LarkAPIError, LarkDocIOError
from larkdocio.model import TableNode
from larkdocio.read.client import Client as ReadClient
from larkdocio.read.config import new_config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    AnchorById,
    InsertPosition,
    InsertRequest,
    NewParagraph,
    apply,
    compose,
    dry_run,
)
from larkdocio.write.client import MAX_DESCENDANTS_PER_CALL, WriteClient, text_block
from larkdocio.write.encode import (
    MAX_ONE_CALL_TABLE_CELLS,
    encode_content,
    table_descendants,
    table_subtree,
)
from larkdocio.write.resolve import _collect_blocks

pytestmark = pytest.mark.live_write
# The live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing the statement
# above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

DOMAIN = "larksuite.com"

SUFFIX = "ld482gate-7b3e11"
SECTION_HEADING = f"LD482-GATE-SECTION {SUFFIX}"
TABLE_ANCHOR = f"anchor paragraph for the one-call table :: {SUFFIX}"
MARKER_ANCHOR = f"anchor paragraph for the mixed-batch marker :: {SUFFIX}"
MARKER_TEXT = f"MARKER belongs directly after its own anchor :: {SUFFIX}"

#: The block that makes the positional leg DISCRIMINATE (LD-496). Seeded **after**
#: ``TABLE_ANCHOR``, it is why the index the engine derives for the ``/descendant`` call is
#: mid-list rather than the append position — with ``TABLE_ANCHOR`` last, a route that ignored
#: ``index`` altogether produced a byte-identical read-back and the assertion passed either way.
TRAILING_TEXT = f"TRAILING paragraph — the table must land BEFORE me :: {SUFFIX}"

ROWS, COLS = 36, 6                 # the consumer's own grid — 216 cells
CELLS = ROWS * COLS

#: What the table itself may cost. **One** — that is the whole claim. The bound is not a
#: budget with slack: a second call on this route would mean the subtree did not go whole.
MAX_TABLE_WRITE_CALLS = 1

#: The spike's own probe points into the row-major cell sequence — the four that would each
#: catch a different transposition (first cell, first cell of row 1, a cell deep in the middle,
#: the last cell).
PROBE_POINTS = {0: "h0", 6: "r1c0", 108: "r18c0", 215: "r35c5"}


def _grid_markdown():
    """The consumer's table, in the reader's OWN emission shape so the round trip is exact."""
    lines = ["| " + " | ".join(f"h{c}" for c in range(COLS)) + " |",
             "|" + "---|" * COLS]
    for r in range(1, ROWS):
        lines.append("| " + " | ".join(f"r{r}c{c}" for c in range(COLS)) + " |")
    return "\n".join(lines)


TABLE_MD = _grid_markdown()


class _CountingOpener:
    """A pass-through ``urlopen`` that RECORDS every request the write client issues.

    Taken at the **transport**, below the client's own methods: a route that quietly fell back
    to create-then-fill would be invisible to a spy that counted method invocations.

    It also keeps the ``index`` integer each ``/descendant`` body carried (LD-496). That is the
    wire half of LD-482's AC2 and it is observable nowhere else: the client returns Lark's
    answer, not what it asked for, and a `(method, url)` pair cannot tell a positive index from
    ``-1``. Read off the body rather than reconstructed, so it is a measurement of the request
    that actually went out.
    """

    def __init__(self):
        self.requests = []
        self.descendant_indexes = []

    def __call__(self, req, timeout=30):
        url = req.full_url.split("?")[0]
        self.requests.append((req.get_method(), url))
        if url.endswith("/descendant"):
            try:
                self.descendant_indexes.append(
                    json.loads((req.data or b"").decode("utf-8"))["index"])
            except (ValueError, KeyError, UnicodeDecodeError) as e:  # noqa: BLE001
                self.descendant_indexes.append(f"unreadable ({e})")
        return urllib.request.urlopen(req, timeout=timeout)

    def reset(self):
        self.requests = []
        self.descendant_indexes = []


def _download(document_id):
    """Download + parse via the READER (the modules the CLI uses): ``(markdown, tree)``."""
    attempts = []
    if canary_support.read_creds_available():
        attempts.append(get_read_credentials())
    attempts.append(get_write_credentials())

    last_err = None
    for (app_id, app_secret) in attempts:
        try:
            client = ReadClient(app_id, app_secret, DOMAIN)
            docx, blocks = client.get_docx_content(document_id)
            parser = Parser(new_config())
            return (parser.parse_docx_content(docx.document_id, blocks),
                    parser.parse_docx_tree(docx.document_id, blocks))
        except Exception as e:  # noqa: BLE001 — try the next identity
            last_err = e
    raise last_err


def _tables(tree):
    return [node for node, _path in _collect_blocks(tree) if isinstance(node, TableNode)]


def _cell_text(cell):
    """One ``TableCellNode``'s plain text — what the reader made of what was written.

    Read off the tree rather than off the rendered Markdown deliberately: a row-major
    assertion made against a pipe table would be an assertion about the renderer's row
    folding, not about which cell each text landed in.
    """
    out = []

    def walk(node):
        for inline in getattr(node, "content", None) or ():
            payload = getattr(inline, "content", None)
            if isinstance(payload, str):
                out.append(payload)
        for child in getattr(node, "children", None) or ():
            walk(child)

    walk(cell)
    return "".join(out).strip()


def test_ld482_gate_the_216_cell_table_goes_in_ONE_call_and_lands_where_it_was_asked(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    assert CELLS <= MAX_ONE_CALL_TABLE_CELLS, (
        f"{CELLS} cells must be INSIDE the one-call envelope — this gate is about the "
        f"one-call route, and a grid outside it would silently test the other one")
    assert table_descendants(CELLS) <= MAX_DESCENDANTS_PER_CALL

    opener = _CountingOpener()
    wc = WriteClient(*get_write_credentials(), DOMAIN, urlopen=opener)

    dest_folder = canary_support.require_disposables_folder()
    doc = wc.create_document(title=f"larkdocio-LD482-one-call-table-gate {int(time.time())}",
                             folder_token=dest_folder)
    doc_id = doc["document_id"]
    evidence = {"doc_id": doc_id}
    seed = [
        {"block_type": 3,
         "heading1": {"elements": [{"text_run": {"content": SECTION_HEADING}}]}},
        text_block(MARKER_ANCHOR),
        text_block(TABLE_ANCHOR),
        text_block(TRAILING_TEXT),      # LD-496 — keeps the table's index OFF the end
    ]
    n_top = len(seed)

    try:
        created_seed = wc.create_children(doc_id, doc_id, seed, index=0)
        seed_ids = [c["block_id"] for c in created_seed["children"]]
        marker_anchor_id, table_anchor_id, trailing_id = seed_ids[1], seed_ids[2], seed_ids[3]

        md_baseline, tree_baseline = _download(doc_id)
        md_baseline_2, _ = _download(doc_id)
        assert md_baseline == md_baseline_2, (
            "reader is non-deterministic: two downloads of the unchanged doc differ")
        assert not _tables(tree_baseline), "the baseline must carry no table yet"

        # 3) ONE batch, MIXED: a paragraph after its anchor, the table after its own.
        content = tuple(compose(TABLE_MD))
        assert [c.kind.value for c in content] == ["table"], content
        assert (content[0].row_count, content[0].column_count) == (ROWS, COLS)

        plan = dry_run(
            [
                InsertRequest(reference=AnchorById(block_id=marker_anchor_id),
                              position=InsertPosition.AFTER,
                              content=(NewParagraph(MARKER_TEXT),)),
                InsertRequest(reference=AnchorById(block_id=table_anchor_id),
                              position=InsertPosition.AFTER,
                              content=content),
            ],
            tree_baseline,
        )
        assert len(plan.refusals) == 0, f"dry-run refused: {plan.refusals!r}"
        assert len(plan.resolved) == 2, f"dry-run did not resolve both: {plan!r}"

        opener.reset()
        started = time.monotonic()
        log = apply(plan, wc, doc_id)
        elapsed = time.monotonic() - started
        calls = list(opener.requests)

        marker_id = log.entries[0].created_block_ids[0]
        table_entry = log.entries[1]
        assert table_entry.outcome == "inserted", table_entry.to_dict()
        assert len(table_entry.created_block_ids) == 1 and table_entry.created_block_ids[0], (
            "block-id reporting must be unchanged: ONE created id, the table's")
        table_id = table_entry.created_block_ids[0]
        evidence.update(created_table_id=table_id, created_marker_id=marker_id)

        # 4) THE COST — one descendant call for the whole table, no grow, no fill.
        descendant_calls = [c for c in calls if c[1].endswith("/descendant")]
        grow_or_fill = [c for c in calls
                        if c[0] == "PATCH" and "/blocks/" in c[1]]
        evidence.update(api_calls=len(calls), descendant_calls=len(descendant_calls),
                        elapsed_s=round(elapsed, 2))
        assert len(descendant_calls) == MAX_TABLE_WRITE_CALLS, (
            f"the table must cost exactly one /descendant call; got "
            f"{len(descendant_calls)}: {calls}")
        assert not grow_or_fill, (
            f"a grow or fill PATCH came back — the three-movement route is back: {grow_or_fill}")

        # 4b) THE DISCLOSURE — what each entry SAYS it cost, against what the wire saw
        # (LD-562). The offline arm proves the count equals the double's calls; this one
        # proves it on the real endpoint, and it costs nothing extra: the calls are already
        # recorded above. Both entries here are one call, so both disclose atomic.
        mutating = [c for c in calls if c[0] != "GET"]
        disclosed = [entry.mutating_write_calls for entry in log.entries]
        evidence.update(disclosed_write_calls=disclosed, mutating_calls=len(mutating))
        assert None not in disclosed, (
            f"every inserted entry must disclose its measured cost: {disclosed}")
        assert sum(disclosed) == len(mutating), (
            f"the log disclosed {sum(disclosed)} write calls; the wire saw "
            f"{len(mutating)}: {mutating}")
        assert table_entry.mutating_write_calls == len(descendant_calls)
        assert [entry.atomic for entry in log.entries] == [True, True], (
            "one call each — neither entry may report itself non-atomic")

        # 5) THE VERDICT — a fresh read-back, never the write's own code: 0.
        md_created, tree_created = _download(doc_id)
        live_root = wc.get_block(doc_id, doc_id)
        order = list(live_root.get("children") or ())
        evidence["live_order"] = order
        # Named, so the printed order is readable as GEOMETRY rather than as six opaque ids.
        roles = {marker_anchor_id: "marker_anchor", marker_id: "MARKER",
                 table_anchor_id: "table_anchor", table_id: "TABLE",
                 trailing_id: "trailing"}
        evidence["order_named"] = [roles.get(b, "seed") for b in order]
        assert order.index(marker_id) == order.index(marker_anchor_id) + 1, (
            f"the MARKER did not land beside its own anchor: {order}")
        assert order.index(table_id) == order.index(table_anchor_id) + 1, (
            f"the TABLE did not land beside its own anchor — the binding gate: {order}")
        # LD-496 — THE DISCRIMINATING ASSERTION. The table's anchor is no longer last, so an
        # implementation that ignored `index` and appended would put the table AFTER the
        # trailing block. Only this line can tell the two apart.
        assert order.index(trailing_id) == order.index(table_id) + 1, (
            f"the TABLE did not land BETWEEN its anchor and the trailing block — this is "
            f"what an append-equivalent /descendant route looks like: {evidence['order_named']}")

        # …and the other half of it: the integer actually sent. Every capture behind this
        # route used `index: -1`; a POSITIVE, mid-list one is the thing LD-482 left unmeasured.
        sent = list(opener.descendant_indexes)
        assert len(sent) == MAX_TABLE_WRITE_CALLS, f"expected one /descendant body: {sent}"
        wire_index = sent[0]
        evidence["descendant_index"] = wire_index
        assert isinstance(wire_index, int) and wire_index > 0, (
            f"the /descendant call did not carry a positive index: {wire_index!r} — the "
            f"positional claim on this route is unproven at index -1")
        assert wire_index == order.index(table_anchor_id) + 1, (
            f"the sent index {wire_index} is not the live child index of the reference + 1 "
            f"({order.index(table_anchor_id) + 1}) — LD-482 AC2: {evidence['order_named']}")
        assert wire_index < len(order) - 1, (
            f"the sent index {wire_index} IS the append position in a list of {len(order)} — "
            f"the geometry stopped discriminating and this leg proves nothing")

        live_property = (wc.get_block(doc_id, table_id).get("table") or {}).get(
            "property") or {}
        assert live_property.get("row_size") == ROWS, live_property
        assert live_property.get("column_size") == COLS, live_property
        evidence["live_grid"] = (live_property.get("row_size"),
                                 live_property.get("column_size"))

        created_tables = _tables(tree_created)
        assert len(created_tables) == 1, f"expected one table; got {len(created_tables)}"
        cells = list(created_tables[0].cells)
        assert len(cells) == CELLS, f"expected {CELLS} cells; got {len(cells)}"
        probed = {index: _cell_text(cells[index]) for index in PROBE_POINTS}
        assert probed == PROBE_POINTS, (
            f"the cells are not in ROW-MAJOR order: {probed} != {PROBE_POINTS}")
        evidence["probes"] = probed

        lines = md_created.splitlines()
        for line in TABLE_MD.splitlines():
            assert line in lines, (
                f"the round trip lost a line of the authored table: {line!r}")

        # 6) …and nothing else moved.
        removed = [d for d in difflib.ndiff(md_baseline.splitlines(), lines)
                   if d.startswith("- ")]
        assert not removed, f"the insert was not purely additive; lost lines: {removed}"

    finally:
        emptied = False
        deleted = None
        try:
            wc.batch_delete(doc_id, doc_id, 0, n_top + 2)
            md_empty, tree_empty = _download(doc_id)
            emptied = SUFFIX not in md_empty and not _tables(tree_empty)
        except LarkDocIOError as e:
            evidence["empty_error"] = str(e)
        try:
            resp = wc.delete_document(doc_id)
            deleted = resp.get("code") if isinstance(resp, dict) else "ok"
        except LarkDocIOError as e:
            deleted = f"skipped ({e})"
        evidence["emptied"] = emptied
        evidence["deleted"] = deleted

    assert emptied, "teardown failed: authored table content still present after restore"

    with capsys.disabled():
        print(
            "\n[live_write:LD482-one-call-table-gate] "
            f"doc_id={evidence['doc_id']} table_id={evidence.get('created_table_id')} "
            f"cells={CELLS} descendants={table_descendants(CELLS)} "
            f"api_calls={evidence.get('api_calls')} "
            f"descendant_calls={evidence.get('descendant_calls')} "
            f"(the shipped fill spent 37 for the same grid, the per-cell path 463) "
            f"elapsed_s={evidence.get('elapsed_s')} (EVIDENCE ONLY — gates nothing) "
            f"live_grid={evidence.get('live_grid')} probes={evidence.get('probes')} "
            f"descendant_index={evidence.get('descendant_index')} "
            f"live_order={evidence.get('order_named')} "
            f"live_order_ids={evidence.get('live_order')} "
            f"emptied={evidence.get('emptied')} "
            f"deleted={evidence.get('deleted')}"
        )


def test_ld482_gate_a_subtree_ONE_CELL_past_the_envelope_is_refused_and_creates_NOTHING(
        capsys):
    """The atomicity claim, measured rather than reasoned: the boundary the spike bisected is
    still where it was, and the refusal leaves the document exactly as it was.

    A separate disposable, because the point is that the document is untouched afterwards —
    asserting that inside the document the first leg authored into would be weaker.
    """
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    opener = _CountingOpener()
    wc = WriteClient(*get_write_credentials(), DOMAIN, urlopen=opener)

    dest_folder = canary_support.require_disposables_folder()
    doc = wc.create_document(title=f"larkdocio-LD482-atomicity-gate {int(time.time())}",
                             folder_token=dest_folder)
    doc_id = doc["document_id"]
    evidence = {"doc_id": doc_id}

    over = MAX_ONE_CALL_TABLE_CELLS + 1                 # 500 cells = 1001 descendants
    assert table_descendants(over) == MAX_DESCENDANTS_PER_CALL + 1

    try:
        from larkdocio.write.model import NewBlock

        rows = [[f"c{r}x{c}" for c in range(4)] for r in range(over // 4)]
        child = encode_content((NewBlock.table(rows),))[0]
        root_temp, descendants = table_subtree(child)
        assert len(descendants) == table_descendants(over)

        with pytest.raises(LarkAPIError) as excinfo:
            wc.create_descendant(doc_id, doc_id, children_id=[root_temp],
                                 descendants=descendants, index=-1)
        evidence["refusal"] = str(excinfo.value)

        # THE VERDICT — nothing was created. Read it back, do not trust the error.
        md_after, tree_after = _download(doc_id)
        assert not _tables(tree_after), (
            "a refused subtree left a table behind — atomicity does not hold")
        evidence["tables_after"] = 0
        evidence["markdown_len"] = len(md_after)

        # …and the control: one cell fewer goes in, so the boundary is the envelope and not
        # some other property of this body.
        inside = [[f"c{r}x{c}" for c in range(4)]
                  for r in range(MAX_ONE_CALL_TABLE_CELLS // 4)]
        child_ok = encode_content((NewBlock.table(inside),))[0]
        ok_temp, ok_descendants = table_subtree(child_ok)
        assert len(ok_descendants) <= MAX_DESCENDANTS_PER_CALL
        wc.create_descendant(doc_id, doc_id, children_id=[ok_temp],
                             descendants=ok_descendants, index=-1)
        _, tree_ok = _download(doc_id)
        assert len(_tables(tree_ok)) == 1, "the control table did not land"
        evidence["control_cells"] = len(inside) * 4

    finally:
        deleted = None
        try:
            resp = wc.delete_document(doc_id)
            deleted = resp.get("code") if isinstance(resp, dict) else "ok"
        except LarkDocIOError as e:
            deleted = f"skipped ({e})"
        evidence["deleted"] = deleted

    with capsys.disabled():
        print(
            "\n[live_write:LD482-atomicity-gate] "
            f"doc_id={evidence['doc_id']} over_envelope_cells={over} "
            f"descendants={table_descendants(over)} "
            f"refusal={evidence.get('refusal')!r} "
            f"tables_after_refusal={evidence.get('tables_after')} "
            f"control_cells={evidence.get('control_cells')} "
            f"deleted={evidence.get('deleted')}"
        )
