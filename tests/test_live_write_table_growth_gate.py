"""THE LD-431 GATE — a table PAST the create-time grid ceiling authors, live, end to end.

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it with the whole ring::

    pytest -m live_write

The bug this gate exists to keep dead: a Markdown table of **ten or more rows** composed
cleanly, planned cleanly, and was then refused by Lark ``1770001 invalid param`` at
``create_children`` — mid-batch, with earlier batches already written. The fix is a
construction change (the create call's auto-provisioned grid form validates nine per axis, so
the engine seeds at nine and appends the rest), and a construction change is exactly the kind
of thing an offline call-sequence assertion can get *internally* consistent and still wrong on
the wire. Hence this gate, and hence its verdict being a **fresh re-download through the
reader** rather than the write's own success code.

The ring, against a doc it **creates and destroys itself** (never the read canary, never the
block-zoo doc, never the standing sandbox, never a real document):

1. **creates its own disposable doc** and seeds a heading + paragraph so the insert has a real
   reference anchor;
2. downloads + parses it **twice**, asserting byte-identity — the determinism control that
   makes any later diff attributable to the write;
3. **authors two tables through the gate** in ONE ``InsertRequest``, both past the ceiling on a
   different axis — a **12×3** (row growth) and a **2×12** (column growth) — via
   ``compose(markdown)`` → ``dry_run`` → ``apply``;
4. **re-downloads and asserts the ROUND-TRIP property** (the Markdown-authoring spec's standing contract): the
   reader's own Markdown for what was created **is** the source fragment, line for line, and
   the live block properties really carry ``row_size: 12`` / ``column_size: 12``;
5. asserts the write was **purely additive** — no baseline line changed or disappeared;
6. **tears down** in a ``finally`` so nothing persists.

**THE SECOND GATE (LD-575) — the shipped GROW op, and the identity it exists to preserve.**
:func:`test_ld575_gate_the_grow_op_appends_a_row_and_preserves_every_cell_id` is the live arm
of the plan-gated table-grow operation. Round 5 measured that ``insert_table_row
{"row_index": -1}`` appends at the end and leaves every pre-existing cell id untouched and in
order; **that measurement is why nobody re-derives the spelling, and it is not a substitute for
this repository proving its own shipped op.** So the gate records every cell id BEFORE the
grow, appends through the op, re-reads, and asserts each one is still there in the same order
with the table's own block id unchanged — on a disposable it creates and destroys itself.
"""
import difflib
import time

import pytest

import canary_support
from larkdocio.common import get_read_credentials, get_write_credentials
from larkdocio.errors import LarkDocIOError
from larkdocio.model import TableNode
from larkdocio.read.client import Client as ReadClient
from larkdocio.read.config import new_config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    Anchor,
    AnchorById,
    GrowTableRequest,
    InsertPosition,
    InsertRequest,
    apply,
    compose,
    dry_run,
)
from larkdocio.write.client import WriteClient, text_block
from larkdocio.write.resolve import _collect_blocks

pytestmark = pytest.mark.live_write
# LD-431: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing the
# statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

DOMAIN = "larksuite.com"

SUFFIX = "ld431gate-7b3e91"
SECTION_HEADING = f"LD431-GATE-SECTION {SUFFIX}"
ANCHOR_LINE = f"anchor paragraph for the oversize-table insert :: {SUFFIX}"

TALL_ROWS, TALL_COLS = 12, 3          # past the ceiling on the ROW axis
WIDE_ROWS, WIDE_COLS = 2, 12          # past the ceiling on the COLUMN axis


def _grid_markdown(rows, cols, tag):
    """A GFM table in **the reader's own emission shape**, so the round-trip is exact."""
    lines = ["| " + " | ".join(f"{tag}-h{c}" for c in range(cols)) + " |",
             "|" + "---|" * cols]
    for r in range(1, rows):
        lines.append("| " + " | ".join(f"{tag}-r{r}c{c}" for c in range(cols)) + " |")
    return "\n".join(lines)


TALL_MD = _grid_markdown(TALL_ROWS, TALL_COLS, f"tall-{SUFFIX}")
WIDE_MD = _grid_markdown(WIDE_ROWS, WIDE_COLS, f"wide-{SUFFIX}")


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


def test_ld431_gate_a_table_past_the_create_grid_ceiling_round_trips(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    wc = WriteClient(*get_write_credentials(), DOMAIN)

    dest_folder = canary_support.require_disposables_folder()
    doc = wc.create_document(title=f"larkdocio-LD431-growth-gate {int(time.time())}",
                             folder_token=dest_folder)
    doc_id = doc["document_id"]
    evidence = {"doc_id": doc_id}
    seed = [
        {"block_type": 3,
         "heading1": {"elements": [{"text_run": {"content": SECTION_HEADING}}]}},
        text_block(ANCHOR_LINE),
    ]
    n_top = len(seed)

    try:
        wc.create_children(doc_id, doc_id, seed, index=0)

        md_baseline, tree_baseline = _download(doc_id)
        md_baseline_2, _ = _download(doc_id)
        assert md_baseline == md_baseline_2, (
            "reader is non-deterministic: two downloads of the unchanged doc differ")
        assert not _tables(tree_baseline), "the baseline must carry no table yet"

        # 3) AUTHOR both oversize grids through the gate, from Markdown.
        content = tuple(compose(TALL_MD)) + tuple(compose(WIDE_MD))
        assert [c.kind.value for c in content] == ["table", "table"], content
        assert (content[0].row_count, content[0].column_count) == (TALL_ROWS, TALL_COLS)
        assert (content[1].row_count, content[1].column_count) == (WIDE_ROWS, WIDE_COLS)

        plan = dry_run([InsertRequest(
            reference=Anchor(quote=ANCHOR_LINE, breadcrumb=(SECTION_HEADING,)),
            position=InsertPosition.AFTER,
            content=content,
        )], tree_baseline)
        assert len(plan.refusals) == 0, f"dry-run refused the insert: {plan.refusals!r}"
        assert len(plan.resolved) == 1, f"dry-run did not resolve the insert: {plan!r}"

        revision_before = wc.read_document_revision(doc_id)
        log = apply(plan, wc, doc_id)            # ← used to raise 1770001 right here
        created = log.entries[0]
        assert created.outcome == "inserted", created.to_dict()
        assert len(created.created_block_ids) == 2, created.created_block_ids
        assert all(created.created_block_ids), created.created_block_ids
        evidence["created_table_ids"] = created.created_block_ids

        # 3b) THE DISCLOSURE, on the route that loses atomicity (LD-562). Two grown grids in
        # one entry: created, grown a line per call, then filled — so the entry must report
        # more than one write call and must say so out loud rather than leave a consumer to
        # infer it from an absent field. The live revision delta is printed beside it as
        # corroboration (EVIDENCE ONLY — the document's counter is Lark's, not a contract).
        evidence["disclosed_write_calls"] = created.mutating_write_calls
        evidence["revision_delta"] = (
            wc.read_document_revision(doc_id) - revision_before
            if isinstance(revision_before, int) else "unavailable")
        assert created.mutating_write_calls is not None, (
            "an inserted entry with no disclosed cost — absence would be read as atomic")
        assert created.mutating_write_calls > 1, created.to_dict()
        assert created.atomic is False, created.to_dict()

        # 4) THE VERDICT — a fresh read-back through the reader, not the write's own code.
        md_created, tree_created = _download(doc_id)
        lines = md_created.splitlines()
        for source in (TALL_MD, WIDE_MD):
            for line in source.splitlines():
                assert line in lines, (
                    f"the round trip lost a line of the authored table: {line!r}")

        live_props = [
            (wc.get_block(doc_id, bid).get("table") or {}).get("property") or {}
            for bid in created.created_block_ids
        ]
        assert [p.get("row_size") for p in live_props] == [TALL_ROWS, WIDE_ROWS], live_props
        assert [p.get("column_size") for p in live_props] == [TALL_COLS, WIDE_COLS], (
            live_props)
        evidence["live_grid"] = [(p.get("row_size"), p.get("column_size"))
                                 for p in live_props]

        created_tables = _tables(tree_created)
        assert len(created_tables) == 2, f"expected two tables; got {len(created_tables)}"
        assert [len(t.cells) for t in created_tables] == [
            TALL_ROWS * TALL_COLS, WIDE_ROWS * WIDE_COLS], (
            "the grown grid must carry every authored cell")
        evidence["cell_counts"] = [len(t.cells) for t in created_tables]

        # 5) …and nothing else moved.
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
            "\n[live_write:LD431-growth-gate] "
            f"doc_id={evidence['doc_id']} "
            f"created_table_ids={evidence.get('created_table_ids')} "
            f"live_grid={evidence.get('live_grid')} "
            f"cell_counts={evidence.get('cell_counts')} "
            f"disclosed_write_calls={evidence.get('disclosed_write_calls')} "
            f"revision_delta={evidence.get('revision_delta')} (EVIDENCE ONLY) "
            f"emptied={evidence.get('emptied')} deleted={evidence.get('deleted')}"
        )


# =========================================================================== #
# THE LD-575 GATE — the shipped grow op, live, with the identity read-back      #
# =========================================================================== #

GROW_SUFFIX = "ld575gate-4c1a08"
GROW_HEADING = f"LD575-GATE-SECTION {GROW_SUFFIX}"
GROW_ANCHOR = f"anchor paragraph for the table grow :: {GROW_SUFFIX}"

#: The seed grid. Small on purpose: what this gate proves is identity, and four ids prove it
#: exactly as well as four hundred while costing four hundred fewer throttled calls.
SEED_ROWS, SEED_COLS = 2, 2
SEED_MD = _grid_markdown(SEED_ROWS, SEED_COLS, f"grow-{GROW_SUFFIX}")


def test_ld575_gate_the_grow_op_appends_a_row_and_preserves_every_cell_id(capsys):
    """Append a row to a table that already exists — and prove every id it had survived.

    The verdict is a **fresh read-back through the live block**, not the write's own success
    code: the cell ids recorded before the append must be a PREFIX of the ones after it (same
    ids, same order, none dropped, none reordered), the appended cells must be exactly what the
    apply-log entry claimed came into existence, and the table's own block id must not move.
    """
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    wc = WriteClient(*get_write_credentials(), DOMAIN)
    dest_folder = canary_support.require_disposables_folder()
    doc = wc.create_document(title=f"larkdocio-LD575-grow-gate {int(time.time())}",
                             folder_token=dest_folder)
    doc_id = doc["document_id"]
    evidence = {"doc_id": doc_id}
    seed = [
        {"block_type": 3,
         "heading1": {"elements": [{"text_run": {"content": GROW_HEADING}}]}},
        text_block(GROW_ANCHOR),
    ]
    n_top = len(seed)

    try:
        wc.create_children(doc_id, doc_id, seed, index=0)
        md_baseline, tree_baseline = _download(doc_id)

        # 1) A table to grow, authored through the ordinary gate.
        content = tuple(compose(SEED_MD))
        authored = apply(dry_run([InsertRequest(
            reference=Anchor(quote=GROW_ANCHOR, breadcrumb=(GROW_HEADING,)),
            position=InsertPosition.AFTER,
            content=content,
        )], tree_baseline), wc, doc_id)
        table_id = authored.entries[0].created_block_ids[0]
        evidence["table_id"] = table_id

        # 2) THE IDS IT STARTS WITH, off the live block itself.
        before_block = wc.get_block(doc_id, table_id)
        cells_before = list(before_block.get("children") or ())
        assert len(cells_before) == SEED_ROWS * SEED_COLS, cells_before
        evidence["cells_before"] = cells_before

        # 3) THE GROW, through the plan gate — two rows, two requests, one call each.
        _md, tree_seeded = _download(doc_id)
        revision_before = wc.read_document_revision(doc_id)
        plan = dry_run(
            [GrowTableRequest(anchor=AnchorById(block_id=table_id)) for _ in range(2)],
            tree_seeded, document_revision_id=revision_before)
        assert not plan.refusals, f"dry-run refused the grow: {plan.refusals!r}"
        assert [e.op for e in plan.entries] == ["grow-table", "grow-table"], plan
        evidence["previewed"] = [(e.before, e.after) for e in plan.entries]

        log = apply(plan, wc, doc_id)
        assert [e.outcome for e in log.entries] == ["inserted", "inserted"], (
            [e.to_dict() for e in log.entries])
        for entry in log.entries:
            assert entry.mutating_write_calls == 1, entry.to_dict()
            assert entry.atomic is True, entry.to_dict()
        appended_claimed = [c for e in log.entries for c in e.created_block_ids]
        evidence["appended_claimed"] = appended_claimed
        evidence["disclosed_write_calls"] = [e.mutating_write_calls for e in log.entries]

        # 4) THE VERDICT — the live grid, read back.
        after_block = wc.get_block(doc_id, table_id)
        assert after_block.get("block_id") == table_id, (
            "the table's OWN block id moved — the whole point of this op is that it does not")
        cells_after = list(after_block.get("children") or ())
        evidence["cells_after"] = cells_after
        assert cells_after[:len(cells_before)] == cells_before, (
            f"a pre-existing cell id was dropped or reordered: "
            f"before={cells_before} after={cells_after}")
        assert cells_after[len(cells_before):] == appended_claimed, (
            "the appended cells are not the ones the apply log named")
        prop = (after_block.get("table") or {}).get("property") or {}
        assert (prop.get("row_size"), prop.get("column_size")) == (
            SEED_ROWS + 2, SEED_COLS), prop
        evidence["live_grid"] = (prop.get("row_size"), prop.get("column_size"))
        evidence["revision_delta"] = (
            wc.read_document_revision(doc_id) - revision_before
            if isinstance(revision_before, int) else "unavailable")

        # 5) The grown table reads back through the READER with its authored text intact and
        #    nothing else in the document moved.
        md_grown, tree_grown = _download(doc_id)
        (grown,) = _tables(tree_grown)
        assert grown.block_id == table_id, grown.block_id
        assert len(grown.cells) == (SEED_ROWS + 2) * SEED_COLS, len(grown.cells)
        for line in SEED_MD.splitlines()[:2]:      # the header and its delimiter
            assert line in md_grown.splitlines(), line
        removed = [d for d in difflib.ndiff(md_baseline.splitlines(), md_grown.splitlines())
                   if d.startswith("- ")]
        assert not removed, f"the grow was not purely additive; lost lines: {removed}"

        # 6) THE REFUSAL, live: a mid-table index is refused at PLAN time, so nothing is sent.
        refused = dry_run([GrowTableRequest(anchor=AnchorById(block_id=table_id),
                                           row_index=0)], tree_grown)
        assert len(refused.refusals) == 1, refused
        reason_value = refused.entries[0].refusal.reason.value
        assert reason_value == "table-grow-unsupported", reason_value
        evidence["refusal"] = reason_value
        assert wc.get_block(doc_id, table_id).get("children") == cells_after, (
            "a refused grow touched the document")

    finally:
        emptied = False
        deleted = None
        try:
            wc.batch_delete(doc_id, doc_id, 0, n_top + 1)
            md_empty, tree_empty = _download(doc_id)
            emptied = GROW_SUFFIX not in md_empty and not _tables(tree_empty)
        except LarkDocIOError as e:
            evidence["empty_error"] = str(e)
        try:
            resp = wc.delete_document(doc_id)
            deleted = resp.get("code") if isinstance(resp, dict) else "ok"
        except LarkDocIOError as e:
            deleted = f"skipped ({e})"
        evidence["emptied"] = emptied
        evidence["deleted"] = deleted

    assert emptied, "teardown failed: the grown table is still present after restore"

    with capsys.disabled():
        print(
            "\n[live_write:LD575-grow-gate] "
            f"doc_id={evidence['doc_id']} table_id={evidence.get('table_id')} "
            f"cells_before={evidence.get('cells_before')} "
            f"cells_after={evidence.get('cells_after')} "
            f"appended_claimed={evidence.get('appended_claimed')} "
            f"previewed={evidence.get('previewed')} "
            f"live_grid={evidence.get('live_grid')} "
            f"disclosed_write_calls={evidence.get('disclosed_write_calls')} "
            f"refusal={evidence.get('refusal')} "
            f"revision_delta={evidence.get('revision_delta')} (EVIDENCE ONLY) "
            f"emptied={evidence.get('emptied')} deleted={evidence.get('deleted')}"
        )
