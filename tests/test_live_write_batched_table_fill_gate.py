"""THE LD-481 GATE — the consumer's 6×36 table authors live, and it costs TENS of calls.

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it with the whole ring::

    pytest -m live_write

The bug this gate exists to keep dead has two halves, and only the live wire can judge either:

1. **the refusal** — a 6 column × 36 row = **216-cell** table was refused offline at
   construction by ``MAX_TABLE_CELLS = 200``, larkdocio's own cost budget, before any API call.
   The budget was honest about a fill that spent **two throttled calls per non-empty cell**;
2. **the cost** — that fill really did spend **463 write API calls / 158.41 s** on those 216
   cells (measured on a disposable, 2026-08-14), 93% of them the per-cell pair.

Both halves are the library's construction, not the platform's: Lark takes the identical table
in a handful of calls. So the fill is batched (one paginated document block list + one
``batch_update`` per 48 cells) and the cap is re-derived from the measured envelope. **An
offline call-sequence assertion can get all of that internally consistent and still be wrong on
the wire** — a batch body Lark rejects, an inner-block id the listing spells differently, a
cell order that is not row-major once Lark provisions it. Hence this gate.

The ring, against a document it **creates and destroys itself** (never the read canary, never
the block-zoo doc, never the standing write scratch doc, never a real document):

1. **creates its own disposable doc** and seeds a heading + paragraph, so the insert has a real
   reference anchor;
2. downloads + parses it **twice**, asserting byte-identity — the determinism control that
   makes any later diff attributable to the write;
3. authors the consumer's exact grid — **6 columns × 36 rows, 216 cells** — through the shipped
   front door (``compose(markdown)`` → ``dry_run`` → ``apply``), **counting every HTTP request
   the write client issues** through an injected ``urlopen``;
4. asserts the **cost class** — ``≤ 60`` API calls and ``≤ 21`` **mutating** calls for 216
   cells, whatever endpoint family carries them (measured 37 through route 2 on 2026-08-15,
   and one mutating call through route 1 on 2026-08-26; the pre-LD-481 per-cell path spent 463
   in 158.41 s). **The count is the pin; the clock is not, and neither is the family**
   (LD-578: the old ⌈216/48⌉ ``batch_update`` pin went stale the day LD-482 lifted the grid
   into one ``/descendant`` call — see ``MAX_MUTATING_WRITE_CALLS`` for the re-cut and for how
   this arm and the LD-482 arm divide cost from shape). Elapsed seconds and the per-family
   census are printed as evidence and asserted on by nothing: a wall-clock threshold in a
   suite is a flake generator, and the thing this change bought is calls, not seconds;
5. **THE VERDICT — a fresh read-back**, never the write's own ``code: 0``: ``row_size 36``,
   ``column_size 6``, 216 cells, and **row-major cell order** at the spike's own probe points
   (``[0]='h0'``, ``[6]='r1c0'``, ``[108]='r18c0'``, ``[215]='r35c5'``);
6. asserts the write was **purely additive** — no baseline line changed or disappeared;
7. **tears down** in a ``finally`` so nothing persists.
"""
import difflib
import time
import urllib.request

import pytest

import canary_support
from larkdocio.common import get_read_credentials, get_write_credentials
from larkdocio.errors import LarkDocIOError
from larkdocio.model import TableNode
from larkdocio.read.client import Client as ReadClient
from larkdocio.read.config import new_config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    MAX_TABLE_CELLS,
    Anchor,
    InsertPosition,
    InsertRequest,
    apply,
    compose,
    dry_run,
)
from larkdocio.write.client import WriteClient, text_block
from larkdocio.write.resolve import _collect_blocks

pytestmark = pytest.mark.live_write
# LD-481: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing the
# statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

DOMAIN = "larksuite.com"

SUFFIX = "ld481gate-4c19af"
SECTION_HEADING = f"LD481-GATE-SECTION {SUFFIX}"
ANCHOR_LINE = f"anchor paragraph for the 216-cell table insert :: {SUFFIX}"

ROWS, COLS = 36, 6                 # the consumer's own grid — 216 cells
CELLS = ROWS * COLS

#: **LD-578 — the pin re-cut, the reason kept.** This arm was written when the fill was
#: ⌈cells/48⌉ ``blocks/batch_update`` calls and it asserted that arithmetic on the wire.
#: LD-482 then lifted a lone in-envelope table into **one**
#: ``POST …/blocks/{block}/descendant`` call (D-96), so for this 216-cell grid the batched
#: family is not on the wire at all and the old pin measured **0** — a red gate saying nothing
#: true about the fill. LD-481's *reason* is untouched and is why the arm survives: this exact
#: grid once cost **463 write API calls / 158.41 s** at two throttled calls per non-empty cell,
#: and the fill must never be per-cell again. What moved is the call **family**, so the pin is
#: re-cut onto the **cost class** and counts MUTATING calls of any family: the shipped route
#: spends **one** (measured 2026-08-26 — 3 API calls total, 1.04 s), route 2's batched fill
#: spent ⌈cells/48⌉ + one per
#: grown row, and a per-cell route spends 2 per non-empty cell (432 for this grid). The bound
#: below is an order of magnitude under the cell count, so any per-cell route blows through it
#: while a legitimate re-shaping of the fill — a re-batched route, a split subtree — passes.
#: If a measured count ever lands outside the bound the MEASUREMENT wins and the bound is
#: amended with the reason, never quietly widened.
#:
#: **How the two arms divide the question** (both author this same grid, so the division is
#: stated rather than assumed): **this** arm owns the **COST** — how many calls, of whatever
#: family, the consumer's grid spends, and that no call is spent per cell. The LD-482 arm
#: (``tests/test_live_write_one_call_table_gate.py``) owns the **SHAPE** — exactly one
#: ``/descendant`` call, at the derived index, atomic when Lark refuses. Route 2's own
#: ⌈cells/48⌉ arithmetic stays pinned offline against an injected transport
#: (``tests/test_batched_table_fill.py``), where route 2 still ships. So a future route change
#: reddens the arm whose question actually moved, and only that one; neither arm restates the
#: other's pin, which is exactly how the stale pin LD-578 fixed came to exist.
MAX_MUTATING_WRITE_CALLS = 21

#: The order-of-magnitude bound AC5 pins. **Measured 37** on 2026-08-15 — 2 anchor
#: re-validation reads + 1 create + 27 grow + 1 grid re-read + 1 block list + 5 batched
#: writes — against the **463** the per-cell path spent. The bound is kept at 60 rather than
#: cut to the measurement: the grow leg is one call per row and the list leg one per 500
#: blocks, so a legitimate re-shaping of the same 216 cells moves the count by a few without
#: being a regression, while anything approaching one call per cell blows straight through
#: it. If a measured count ever lands outside the bound the MEASUREMENT wins and the bound is
#: amended with the reason, never quietly widened.
MAX_WRITE_API_CALLS = 60


def _grid_markdown():
    """The consumer's table, in the reader's OWN emission shape so the round trip is exact."""
    lines = ["| " + " | ".join(f"h{c}" for c in range(COLS)) + " |",
             "|" + "---|" * COLS]
    for r in range(1, ROWS):
        lines.append("| " + " | ".join(f"r{r}c{c}" for c in range(COLS)) + " |")
    return "\n".join(lines)


TABLE_MD = _grid_markdown()

#: The spike's own probe points into the row-major cell sequence — the four that would each
#: catch a different transposition (first cell, first cell of row 1, a cell deep in the middle,
#: the last cell).
PROBE_POINTS = {0: "h0", 6: "r1c0", 108: "r18c0", 215: "r35c5"}


class _CountingOpener:
    """A pass-through ``urlopen`` that RECORDS every request the write client issues.

    The call count is the whole measurement, so it is taken at the **transport**, below the
    client's own methods: a batching bug that turned one call into fifty would be invisible to
    a spy that counted method invocations.
    """

    def __init__(self):
        self.requests = []

    def __call__(self, req, timeout=30):
        self.requests.append((req.get_method(), req.full_url.split("?")[0]))
        return urllib.request.urlopen(req, timeout=timeout)

    def reset(self):
        self.requests = []


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

    A cell wraps child block nodes, each carrying an inline sequence; a literal span is a
    ``Text`` whose payload is ``content`` (a str), so the walk collects **str** ``content``
    from inlines and recurses the node ``children``. Reading it off the tree rather than off
    the rendered Markdown is deliberate: a row-major assertion made against a pipe table
    would be an assertion about the renderer's row folding, not about which cell each text
    landed in.
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


def test_ld481_gate_the_consumers_216_cell_table_authors_in_tens_of_calls(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    assert CELLS == 216 and CELLS <= MAX_TABLE_CELLS, (
        f"{CELLS} cells must be inside the {MAX_TABLE_CELLS}-cell cap — this gate exists "
        f"because it once was not")

    opener = _CountingOpener()
    wc = WriteClient(*get_write_credentials(), DOMAIN, urlopen=opener)

    dest_folder = canary_support.require_disposables_folder()
    doc = wc.create_document(title=f"larkdocio-LD481-batched-fill-gate {int(time.time())}",
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

        # 3) AUTHOR the consumer's grid through the shipped front door, from Markdown.
        content = tuple(compose(TABLE_MD))
        assert [c.kind.value for c in content] == ["table"], content
        assert (content[0].row_count, content[0].column_count) == (ROWS, COLS)

        plan = dry_run([InsertRequest(
            reference=Anchor(quote=ANCHOR_LINE, breadcrumb=(SECTION_HEADING,)),
            position=InsertPosition.AFTER,
            content=content,
        )], tree_baseline)
        assert len(plan.refusals) == 0, f"dry-run refused the insert: {plan.refusals!r}"
        assert len(plan.resolved) == 1, f"dry-run did not resolve the insert: {plan!r}"

        opener.reset()                       # count ONLY what apply() spends
        started = time.monotonic()
        log = apply(plan, wc, doc_id)
        elapsed = time.monotonic() - started
        calls = list(opener.requests)

        created = log.entries[0]
        assert created.outcome == "inserted", created.to_dict()
        assert len(created.created_block_ids) == 1 and created.created_block_ids[0]
        table_id = created.created_block_ids[0]
        evidence["created_table_id"] = table_id

        # 4) AC5 — the CALL COUNT is the pin. The clock is evidence and gates nothing.
        mutating = [c for c in calls if c[0] in ("POST", "PATCH", "PUT", "DELETE")]
        batches = [c for c in calls if c[1].endswith("/blocks/batch_update")]
        subtrees = [c for c in calls if c[1].endswith("/descendant")]
        listings = [c for c in calls if c[1].endswith("/blocks")]
        per_cell_reads = [c for c in calls
                          if c[0] == "GET" and "/blocks/" in c[1]
                          and not c[1].endswith("/blocks")]
        evidence.update(api_calls=len(calls), mutating_calls=len(mutating),
                        batch_calls=len(batches), subtree_calls=len(subtrees),
                        list_calls=len(listings), elapsed_s=round(elapsed, 2))
        assert len(calls) <= MAX_WRITE_API_CALLS, (
            f"apply() spent {len(calls)} API calls on {CELLS} cells, over the "
            f"{MAX_WRITE_API_CALLS} bound — the fill is not batched on the wire: {calls}")
        # LD-578 — the COST CLASS, family-agnostic: whichever route carries the cells, the
        # mutating calls may not scale with them. (The route's SHAPE is the LD-482 arm's pin;
        # the family census above is printed as evidence and asserted on by nothing.)
        assert len(mutating) <= MAX_MUTATING_WRITE_CALLS, (
            f"apply() spent {len(mutating)} MUTATING calls on {CELLS} cells, over the "
            f"{MAX_MUTATING_WRITE_CALLS} bound — the fill is spending calls per cell again "
            f"(it once spent 463 in total): {mutating}")
        assert len(per_cell_reads) < CELLS, (
            "a per-cell get_block came back — the fill is 2 calls/cell again")

        # 5) THE VERDICT — a fresh read-back, never the write's own code: 0.
        md_created, tree_created = _download(doc_id)
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
            wc.batch_delete(doc_id, doc_id, 0, n_top + 1)
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
            "\n[live_write:LD481-batched-fill-gate] "
            f"doc_id={evidence['doc_id']} table_id={evidence.get('created_table_id')} "
            f"cells={CELLS} api_calls={evidence.get('api_calls')} "
            f"(bound {MAX_WRITE_API_CALLS}; per-cell path spent 463) "
            f"mutating_calls={evidence.get('mutating_calls')} "
            f"(bound {MAX_MUTATING_WRITE_CALLS} — THE PIN, family-agnostic) "
            f"batch_calls={evidence.get('batch_calls')} "
            f"subtree_calls={evidence.get('subtree_calls')} (census: EVIDENCE ONLY) "
            f"list_calls={evidence.get('list_calls')} "
            f"elapsed_s={evidence.get('elapsed_s')} (EVIDENCE ONLY — gates nothing) "
            f"live_grid={evidence.get('live_grid')} probes={evidence.get('probes')} "
            f"emptied={evidence.get('emptied')} deleted={evidence.get('deleted')}"
        )
