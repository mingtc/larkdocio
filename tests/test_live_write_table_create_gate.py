"""THE S2 GATE — the binding **table-creation** round-trip (LD-135).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it with the whole ring::

    pytest -m live_write

Where the **W2** gate (``tests/test_live_write_w2_gate.py``) proved the apply engine on a
table cell of a table the harness had built with a **raw** ``create_children`` call, THIS
gate proves the thing that did not exist until S2: **the engine itself creates the table**,
through the plan-gated ``dry_run`` → ``Plan`` → ``apply`` path, and then **edits a cell of
the table it just created** — dogfood **F3** closed end to end, live.

The ring, against a doc it **creates and destroys itself** (never the read canary, never the
block-zoo doc, never the standing sandbox, never a real document):

1. **creates its own disposable doc** (``create_document``) and seeds a two-block narrative
   baseline (a heading + a paragraph) so the insert has a real reference **anchor**;
2. **downloads + parses it** (twice, asserting byte-identity — the determinism control that
   makes any later diff attributable to the write), keeping the rendered Markdown and the
   node **tree** the writer anchors against;
3. **authors two tables through the gate** in ONE ``InsertRequest``:
   * a **2×2 headered** grid whose data row carries a unique ``row_key`` + a ``BEFORE``
     value cell (the edit target for step 6), and
   * a **1×2 headerless** grid whose cells carry a **pipe** and an MD **metacharacter** —
     so the round-trip proves the reader's cell escaping composes with authored content, and
     that ``header_row=False`` really reaches the document (asserted on the **live block
     property**, because Lark omits a false flag from the payload it returns, which is the
     documented projection lossiness);
   then ``dry_run`` (asserting it resolves with zero refusals) → ``apply`` (asserting the
   created block ids come back);
4. **re-downloads and asserts the authored structure reads back**: the headered table's
   header/delimiter/data rows, the pipe cell escaped (``\\|``), the metacharacter cell
   literal, and both grids present with their authored dimensions — plus that the write was
   **purely additive** (no baseline line changed or disappeared);
5. **re-parses and edits a cell of the created table** through the shipped
   :class:`~larkdocio.write.model.TableLocator` path (``dry_run`` → ``apply``) — the
   composition S2 exists for: *creatable* content is immediately *editable* content;
6. **re-downloads and asserts the cell edit was surgical** — exactly one Markdown line
   changed, and it is the target row (its key cell survived);
7. **tears down** in a ``finally`` so nothing persists — empties the doc's children,
   verifies the authored content is gone, and best-effort trashes the doc.

**Credentials.** Writes use ``get_write_credentials()`` only. The reader half prefers
``get_read_credentials()`` (the two-app least-privilege separation) and falls back to the
owning write app for a self-provisioned doc a read-only app cannot see — a *read* fallback
only; the write path never borrows read creds. Writes ride the shared throttle (≤3/sec,
``99991400`` backoff), and the grid is deliberately small (6 cells) because each non-empty
cell costs its own pair of throttled calls.
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
    EditRequest,
    InsertPosition,
    InsertRequest,
    NewBlock,
    TableLocator,
    apply,
    dry_run,
)
from larkdocio.write.client import WriteClient, text_block
from larkdocio.write.resolve import _collect_blocks

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

# The write app's tenant region (the toolkit's default OpenAPI domain). NOT a document URL —
# the gate never addresses a pre-existing doc.
DOMAIN = "larksuite.com"

# Unique, greppable tokens the gate authors itself, so every assertion is exact.
SUFFIX = "s2gate-4c19ab7e"
SECTION_HEADING = f"S2-GATE-SECTION {SUFFIX}"
ANCHOR_LINE = f"anchor paragraph for the table insert :: {SUFFIX}"

COLUMN_HEADER = "Value"
ROW_KEY = f"On-time delivery :: {SUFFIX}"
VALUE_BEFORE = f"97.2% :: BEFORE-{SUFFIX}"
VALUE_AFTER = f"99.9% :: REWRITTEN-{SUFFIX}"

# The headerless grid's amplifier cells: a pipe (the reader must escape it) and a
# line-leading MD metacharacter (a GFM cell is an inline-only context — it stays literal).
PIPE_CELL = f"a|b :: {SUFFIX}"
METACHAR_CELL = f"# not a heading :: {SUFFIX}"

HEADERED = NewBlock.table(
    [["Metric", COLUMN_HEADER],
     [ROW_KEY, VALUE_BEFORE]],
    header_row=True,
)
HEADERLESS = NewBlock.table([[PIPE_CELL, METACHAR_CELL]], header_row=False)


def _download(document_id):
    """Download + parse via the READER (the modules the CLI uses): ``(markdown, tree)``.

    Prefers READ creds; falls back to the owning WRITE app because a separate read-only app
    is not a collaborator on a doc this gate self-provisioned. The fallback is a READ
    concern only — the write path never borrows read creds.
    """
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
            markdown = parser.parse_docx_content(docx.document_id, blocks)
            tree = parser.parse_docx_tree(docx.document_id, blocks)
            return markdown, tree
        except Exception as e:  # noqa: BLE001 — try the next identity
            last_err = e
    raise last_err


def _tables(tree):
    """Every :class:`TableNode` in the parsed tree, in document order."""
    return [node for node, _path in _collect_blocks(tree) if isinstance(node, TableNode)]


def test_s2_gate_table_creation_round_trip(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    wc = WriteClient(*get_write_credentials(), DOMAIN)

    # 1) The gate's OWN disposable doc + a narrative baseline to anchor against.
    dest_folder = canary_support.require_disposables_folder()
    doc = wc.create_document(title=f"larkdocio-S2-table-gate {int(time.time())}",
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

        # 2) Baseline + the determinism control.
        md_baseline, tree_baseline = _download(doc_id)
        md_baseline_2, _ = _download(doc_id)
        assert md_baseline == md_baseline_2, (
            "reader is non-deterministic: two downloads of the unchanged doc differ")
        assert not _tables(tree_baseline), "the baseline must carry no table yet"

        # 3) AUTHOR THE TABLES THROUGH THE GATE (the thing that did not exist before S2).
        insert = InsertRequest(
            reference=Anchor(quote=ANCHOR_LINE, breadcrumb=(SECTION_HEADING,)),
            position=InsertPosition.AFTER,
            content=(HEADERED, HEADERLESS),
        )
        plan = dry_run([insert], tree_baseline)
        assert len(plan.refusals) == 0, f"dry-run refused the insert: {plan.refusals!r}"
        assert len(plan.resolved) == 1, f"dry-run did not resolve the insert: {plan!r}"
        assert [c.kind.value for c in plan.resolved[0].content] == ["table", "table"]

        log = apply(plan, wc, doc_id)
        assert len(log.entries) == 1, f"apply-log is not 1:1 with the plan: {log!r}"
        created = log.entries[0]
        assert created.outcome == "inserted", created.to_dict()
        assert len(created.created_block_ids) == 2, created.created_block_ids
        assert all(created.created_block_ids), (
            f"a created table id came back empty: {created.created_block_ids!r}")
        evidence["created_table_ids"] = created.created_block_ids

        # 4) The authored structure reads back — and the write was purely ADDITIVE.
        md_created, tree_created = _download(doc_id)
        lines = md_created.splitlines()
        assert f"| Metric | {COLUMN_HEADER} |" in lines, md_created
        assert "|---|---|" in lines, md_created
        assert f"| {ROW_KEY} | {VALUE_BEFORE} |" in lines, md_created
        assert f"| {PIPE_CELL.replace('|', chr(92) + '|')} | {METACHAR_CELL} |" in lines, (
            "the pipe cell must read back escaped and the metachar cell literal")

        # header_row reached the document either way — asserted on the LIVE block property,
        # not on the Markdown: Lark echoes `header_row: true` for the headered table and
        # OMITS a false flag for the headerless one (so the reader's absent ⇒ promoted
        # default applies to the Markdown projection — the documented lossiness).
        live_props = [
            (wc.get_block(doc_id, bid).get("table") or {}).get("property") or {}
            for bid in created.created_block_ids
        ]
        assert live_props[0].get("header_row") is True, live_props[0]
        assert live_props[1].get("header_row") in (None, False), live_props[1]
        assert [p.get("row_size") for p in live_props] == [2, 1], live_props
        assert [p.get("column_size") for p in live_props] == [2, 2], live_props
        evidence["live_properties"] = live_props
        removed = [d for d in difflib.ndiff(md_baseline.splitlines(), lines)
                   if d.startswith("- ")]
        assert not removed, f"the insert was not purely additive; lost lines: {removed}"

        created_tables = _tables(tree_created)
        assert len(created_tables) == 2, (
            f"expected the two authored tables; got {len(created_tables)}")
        assert [len(t.cells) for t in created_tables] == [4, 2], (
            "the authored grid dimensions must be what Lark provisioned")
        assert [t.col_size for t in created_tables] == [2, 2], created_tables
        evidence["cell_counts"] = [len(t.cells) for t in created_tables]

        # 5) THE COMPOSITION: edit a cell of the table the engine just created.
        edit_plan = dry_run([EditRequest(
            anchor=TableLocator(row_key=ROW_KEY, column_header=COLUMN_HEADER,
                                breadcrumb=(SECTION_HEADING,)),
            replacement=VALUE_AFTER,
        )], tree_created)
        assert len(edit_plan.refusals) == 0, edit_plan.refusals
        assert len(edit_plan.resolved) == 1, edit_plan
        cell = edit_plan.resolved[0].cell
        assert (cell.row, cell.column) == (1, 1), (cell.row, cell.column)
        assert edit_plan.resolved[0].before == VALUE_BEFORE

        edit_log = apply(edit_plan, wc, doc_id)
        assert edit_log.entries[0].outcome == "applied", edit_log.entries[0].to_dict()

        # 6) …and it was surgical: exactly one line changed, and it is the target row.
        md_edited, _ = _download(doc_id)
        before_lines, after_lines = md_created.splitlines(), md_edited.splitlines()
        assert len(before_lines) == len(after_lines), (
            "line count changed — the cell edit was not confined to its row")
        changed = [i for i in range(len(before_lines))
                   if before_lines[i] != after_lines[i]]
        assert len(changed) == 1, f"the cell edit was not surgical: {changed}"
        ci = changed[0]
        assert VALUE_BEFORE in before_lines[ci] and VALUE_AFTER in after_lines[ci]
        assert ROW_KEY in before_lines[ci] and ROW_KEY in after_lines[ci], (
            "the changed line is not the row-key's row")
        evidence["changed_line_before"] = before_lines[ci]
        evidence["changed_line_after"] = after_lines[ci]
        evidence["surgical_diff"] = True

    finally:
        # 7) Teardown so NOTHING persists — on success AND failure.
        emptied = False
        deleted = None
        try:
            # the seed's 2 blocks + the 2 authored tables (best effort: the range covers
            # everything this gate created at the top level)
            wc.batch_delete(doc_id, doc_id, 0, n_top + 2)
            md_empty, tree_empty = _download(doc_id)
            emptied = (
                ROW_KEY not in md_empty
                and VALUE_BEFORE not in md_empty
                and VALUE_AFTER not in md_empty
                and PIPE_CELL not in md_empty
                and not _tables(tree_empty)
            )
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
            "\n[live_write:S2-table-gate] "
            f"doc_id={evidence['doc_id']} "
            f"created_table_ids={evidence.get('created_table_ids')} "
            f"cell_counts={evidence.get('cell_counts')} "
            f"live_properties={evidence.get('live_properties')} "
            f"surgical_diff={evidence.get('surgical_diff')} "
            f"emptied={evidence.get('emptied')} "
            f"deleted={evidence.get('deleted')}\n"
            f"  cell before: {evidence.get('changed_line_before')!r}\n"
            f"  cell after : {evidence.get('changed_line_after')!r}"
        )
