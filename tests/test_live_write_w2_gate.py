"""THE W2 GATE — the binding table-cell write round-trip (LD-073).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` +
network). Run it explicitly (with the whole ring — W0 + W1 + W2)::

    pytest -m live_write

Where the W1 gate (``tests/test_live_write_w1_gate.py``) proved the apply engine
end-to-end on a **narrative paragraph**, THIS gate proves it on a **table cell** —
the one shape the spike found bare quotes cannot address (``97.2%`` in 6 blocks
doc-wide; write-spike Test 5). Its green is the roadmap's **W2 stop-or-W3 decision
point**: table-cell patching works surgically end-to-end.

The ring, against a doc it **creates and destroys itself** (the hermetic arm of AC3 —
never the read canary, never the block-zoo doc, never the standing sandbox, never a
real document):

1. **creates its own disposable doc** (``create_document``) and populates a
   **baseline**: a heading (so the ``TableLocator`` carries a real breadcrumb), a
   **3×2 table** the harness authors cell-by-cell — a header row (``Metric`` |
   ``Value``), a **target data row** whose key cell is a unique verbatim ``row_key``
   and whose value cell carries a unique ``BEFORE`` token, and a **guard data row**
   that must stay byte-identical — and a plain tail paragraph. The table shell is
   created via ``create_children`` (a docx block-type-31 table with a
   row_size/column_size property; Lark auto-provisions the cell grid, each cell
   wrapping one inner text block), then each cell's **inner text block** is filled by
   patching it — the same block a whole-cell edit later patches;
2. **downloads it via the reader** — twice, asserting byte-identity (the determinism
   control that makes any post-edit diff attributable to the edit), keeping both the
   rendered Markdown *and* the parsed **node tree** (``parse_docx_tree`` — what the
   table resolver addresses);
3. builds a **``TableLocator`` ``EditRequest``** — row-key from the real key cell +
   a column-target (the ``Value`` header) + the heading breadcrumb — runs it through
   **``dry_run``** (asserting it resolves to exactly the target cell, row/column
   identification present, zero refusals), then **``apply``** (asserting one
   ``applied`` log entry against the target cell, through the DOUBLE re-validation);
4. **re-downloads and diffs** — asserting **only the target cell's row line changed**
   (exactly one Markdown line differs; every other line — header, separator, the
   guard row, the surrounding blocks — byte-identical), the new value is present, the
   old value is gone, and the changed line still carries the row's key cell (the row
   identity held);
5. **tears down** so nothing persists — empties the doc's children (restore to a
   byte-identical *empty* baseline) and best-effort trashes the doc.

**Credentials (AC4).** Writes use ``get_write_credentials()`` only (write-only, never
read/legacy). The **reader half prefers ``get_read_credentials()``** — the two-app
least-privilege separation — and falls back to the owning write app's creds for a
self-provisioned doc a separate read-only app cannot see (the fallback is about
*reads*; the write path never borrows read creds). Teardown runs in a ``finally`` so a
mid-round-trip failure still leaves nothing behind. Writes ride the shared core's
throttle (≤3/sec, ``99991400`` backoff).
"""
import time

import pytest

import canary_support
from larkdocio.common import get_read_credentials, get_write_credentials
from larkdocio.errors import LarkDocIOError
from larkdocio.model import TableNode
from larkdocio.read.client import Client as ReadClient
from larkdocio.read.config import new_config
from larkdocio.read.parser import Parser
from larkdocio.write import EditRequest, TableLocator, apply, dry_run
from larkdocio.write.client import WriteClient, text_block
from larkdocio.write.resolve import _collect_blocks, _first_text_block_id

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

# The write app's tenant region (matches the toolkit's default OpenAPI domain).
# NOT a document URL — the gate never addresses a pre-existing doc.
DOMAIN = "larksuite.com"

# Distinctive, unique tokens the gate itself authors — so the row-key is a unique
# locator, the value cell is unambiguous, and the diff assertion is exact. The suffix
# makes every token greppable and collision-free within the self-created doc.
SUFFIX = "w2gate-7b3f091a"
SECTION_HEADING = f"W2-GATE-SECTION {SUFFIX}"
ROW_KEY = f"On-time delivery :: {SUFFIX}"            # key cell of the TARGET data row
COLUMN_HEADER = "Value"                              # header cell of the target column
VALUE_BEFORE = f"97.2% :: BEFORE-{SUFFIX}"           # value cell (target) — baseline
REPLACEMENT = f"99.9% :: REWRITTEN-{SUFFIX}"         # the whole-cell replacement text

# The 3×2 table the harness authors, row-major (col_size = 2). Row 0 is the header;
# row 1 is the target (key cell ROW_KEY, value cell VALUE_BEFORE); row 2 is a guard
# row that must stay byte-identical through the edit.
TABLE_ROWS = 3
TABLE_COLS = 2
CELL_CONTENTS = [
    "Metric", COLUMN_HEADER,        # (0,0) (0,1)  — header row
    ROW_KEY, VALUE_BEFORE,          # (1,0) (1,1)  — target data row
    "Defect rate", "0.3%",          # (2,0) (2,1)  — guard data row
]


def _download(document_id):
    """Download + parse the doc via the READER (the same modules the CLI uses).

    Returns ``(markdown, tree)`` — the rendered Markdown for the diff and the parsed
    node tree the table resolver addresses.

    AC4: the reader half **prefers read creds**. For a doc this gate self-provisioned
    with the *write* app, a separate read-only app is not a collaborator, so a read-cred
    download can 403 / not-find; we then fall back to the owning write app's creds. The
    fallback is a READ concern only — the write path (below) never borrows read creds.
    """
    attempts = []
    if canary_support.read_creds_available():
        attempts.append(("read", get_read_credentials()))
    attempts.append(("write", get_write_credentials()))

    last_err = None
    for _label, (app_id, app_secret) in attempts:
        try:
            client = ReadClient(app_id, app_secret, DOMAIN)
            docx, blocks = client.get_docx_content(document_id)
            parser = Parser(new_config())
            markdown = parser.parse_docx_content(docx.document_id, blocks)
            tree = parser.parse_docx_tree(docx.document_id, blocks)
            return markdown, tree
        except (LarkDocIOError, Exception) as e:  # noqa: BLE001 — try the next identity
            last_err = e
    raise last_err


def _find_table(tree):
    """The single :class:`TableNode` in the parsed tree (the one the harness created)."""
    for node, _path in _collect_blocks(tree):
        if isinstance(node, TableNode):
            return node
    return None


def test_w2_gate_table_cell_apply_round_trip(capsys):
    # Load the repo .env (local runs) — a no-op in CI where creds are injected as
    # variables. Then skip LOUDLY if we cannot run.
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    wc = WriteClient(*get_write_credentials(), DOMAIN)

    # 1) Create the gate's OWN disposable doc.
    dest_folder = canary_support.require_disposables_folder()
    doc = wc.create_document(title=f"larkdocio-W2-gate {int(time.time())}",
                             folder_token=dest_folder)
    doc_id = doc["document_id"]

    evidence = {"doc_id": doc_id}
    # Top-level children: a heading (real breadcrumb), the table SHELL (Lark
    # auto-provisions its cell grid from the property), and a plain tail.
    top_children = [
        {"block_type": 3, "heading1": {"elements": [{"text_run": {"content": SECTION_HEADING}}]}},
        {
            "block_type": 31,
            "table": {
                "property": {
                    "row_size": TABLE_ROWS,
                    "column_size": TABLE_COLS,
                    "header_row": True,
                }
            },
        },
        text_block("plain tail paragraph — untouched"),
    ]
    n_top = len(top_children)

    try:
        # 2) Populate the shell, then FILL each cell's inner text block. The shell's
        #    cells come back empty (one inner text block each); download+parse to
        #    discover those inner block ids (row-major, via the resolver's own
        #    _first_text_block_id), then patch each with its authored content — the
        #    same inner-block patch a whole-cell edit later performs.
        wc.create_children(doc_id, doc_id, top_children, index=0)

        _md_shell, tree_shell = _download(doc_id)
        table_shell = _find_table(tree_shell)
        assert table_shell is not None, "created table not found in the parsed shell"
        assert len(table_shell.cells) == TABLE_ROWS * TABLE_COLS, (
            f"expected {TABLE_ROWS * TABLE_COLS} auto-provisioned cells; got "
            f"{len(table_shell.cells)}"
        )
        inner_ids = [_first_text_block_id(c) for c in table_shell.cells]
        assert all(bid is not None for bid in inner_ids), (
            f"every cell must wrap an inner text block to fill; got {inner_ids!r}"
        )
        for bid, content in zip(inner_ids, CELL_CONTENTS):
            wc._patch_block(
                doc_id, bid,
                {"update_text_elements": {"elements": [{"text_run": {"content": content}}]}},
            )

        # 3) Determinism control: two clean downloads of the filled doc must be
        #    byte-identical (so any post-edit diff is attributable to the edit).
        md_baseline, tree_baseline = _download(doc_id)
        md_baseline_2, _ = _download(doc_id)
        assert md_baseline == md_baseline_2, (
            "reader is non-deterministic: two downloads of the unchanged doc differ"
        )
        assert ROW_KEY in md_baseline, "baseline row-key cell missing from download"
        assert VALUE_BEFORE in md_baseline, "baseline target value missing from download"
        assert REPLACEMENT not in md_baseline, "replacement token already present pre-edit"

        # 4) THE PIPELINE. Build a TableLocator EditRequest from the REAL key cell +
        #    column header + heading breadcrumb, then S3 dry-run → S4 apply.
        edit = EditRequest(
            anchor=TableLocator(
                row_key=ROW_KEY,
                column_header=COLUMN_HEADER,
                breadcrumb=(SECTION_HEADING,),
            ),
            replacement=REPLACEMENT,
        )
        plan = dry_run([edit], tree_baseline)
        assert len(plan.resolved) == 1, (
            f"dry-run must resolve to exactly one cell; got {plan!r}"
        )
        assert len(plan.refusals) == 0, f"dry-run refused the edit: {plan.refusals!r}"
        planned = plan.resolved[0]
        target_cell_id = planned.block_id
        assert planned.cell is not None, "resolved table entry lost its cell context"
        assert (planned.cell.row, planned.cell.column) == (1, 1), (
            f"resolved the wrong cell coords: {(planned.cell.row, planned.cell.column)!r}"
        )
        assert planned.cell.column_label == COLUMN_HEADER, (
            f"column label mismatch: {planned.cell.column_label!r}"
        )
        assert VALUE_BEFORE in planned.before, "plan.before lost the target value"
        assert planned.after == REPLACEMENT, "plan.after is not the replacement text"

        log = apply(plan, wc, doc_id)
        assert len(log.entries) == 1, f"apply-log is not 1:1 with the plan: {log!r}"
        applied = log.entries[0]
        assert applied.outcome == "applied", (
            f"the edit was not applied: {applied.to_dict()!r}"
        )
        assert applied.block_id == target_cell_id, (
            "apply patched a different cell than planned"
        )
        assert VALUE_BEFORE in applied.before, "apply-log before lost the target value"
        assert applied.after == REPLACEMENT, "apply-log after is not the replacement"

        # 5) Re-download and diff: ONLY the target cell's row line changed.
        md_after, _ = _download(doc_id)
        assert md_after != md_baseline, "the apply produced no observable change"
        assert REPLACEMENT in md_after, "rewritten value missing after apply"
        assert VALUE_BEFORE not in md_after, "stale target value survived the apply"

        before_lines = md_baseline.splitlines()
        after_lines = md_after.splitlines()
        assert len(before_lines) == len(after_lines), (
            "line count changed — the edit was not confined to one cell's row"
        )
        changed = [i for i in range(len(before_lines)) if before_lines[i] != after_lines[i]]
        assert len(changed) == 1, (
            "the edit was not surgical: more than the target cell's row line changed "
            f"(changed line indices: {changed})"
        )
        ci = changed[0]
        assert VALUE_BEFORE in before_lines[ci], "the changed line is not the target value"
        assert REPLACEMENT in after_lines[ci], "the changed line lost the replacement"
        # The changed line is the target ROW: its key cell survives on both sides (the
        # row identity held; only the value cell changed, not the whole row).
        assert ROW_KEY in before_lines[ci] and ROW_KEY in after_lines[ci], (
            "the changed line is not the row-key's row — a whole-row shift, not a cell edit"
        )

        evidence["baseline_bytes"] = len(md_baseline.encode("utf-8"))
        evidence["target_cell_id"] = target_cell_id
        evidence["cell_coords"] = (planned.cell.row, planned.cell.column)
        evidence["changed_line_index"] = ci
        evidence["changed_before"] = before_lines[ci]
        evidence["changed_after"] = after_lines[ci]
        evidence["surgical_diff"] = True

    finally:
        # 6) Teardown so NOTHING persists (restore to a byte-identical EMPTY baseline).
        #    Empty the top-level children (needs only docx:document), verify gone, then
        #    best-effort trash the doc. Runs on success AND failure (no orphan / drift).
        emptied = False
        deleted = None
        try:
            wc.batch_delete(doc_id, doc_id, 0, n_top)
            md_empty, _ = _download(doc_id)
            emptied = (
                ROW_KEY not in md_empty
                and VALUE_BEFORE not in md_empty
                and REPLACEMENT not in md_empty
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

    # The teardown restore is a binding part of the gate: nothing persists.
    assert emptied, "teardown failed: target content still present after restore"

    with capsys.disabled():
        print(
            "\n[live_write:W2-gate] "
            f"doc_id={evidence['doc_id']} "
            f"baseline_bytes={evidence.get('baseline_bytes')} "
            f"target_cell_id={evidence.get('target_cell_id')} "
            f"cell_coords={evidence.get('cell_coords')} "
            f"changed_line_index={evidence.get('changed_line_index')} "
            f"surgical_diff={evidence.get('surgical_diff')} "
            f"emptied={evidence.get('emptied')} "
            f"deleted={evidence.get('deleted')}\n"
            f"  before: {evidence.get('changed_before')!r}\n"
            f"  after : {evidence.get('changed_after')!r}"
        )
