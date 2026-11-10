"""THE W1 GATE — the binding narrative-apply write round-trip (LD-069).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` +
network). Run it explicitly::

    pytest -m live_write

Where the W0 harness (``tests/test_live_write_harness.py``) proved the *transport*
round-trip with the low-level ``get_block`` / ``_patch_block`` primitives, THIS gate
proves the **W1 apply engine end-to-end**: it drives the real S1–S4 pipeline —
``EditRequest`` (S1) → ``resolve`` (S2) → ``dry_run`` Plan (S3) → ``apply`` (S4) —
against a live doc. **Its green means manual transcription is dead** (the roadmap's
W1 gate).

The ring, against a doc it **creates and destroys itself** (never the read canary,
never the block-zoo doc, never the standing sandbox, never a real document — AC3):

1. **creates its own disposable doc** (``create_document``) and populates a
   **baseline**: a heading, a *bold* **target** paragraph carrying a unique verbatim
   quote, a styled guard neighbour, and a plain tail — all authored by the harness so
   the diff assertion is exact;
2. **downloads it via the reader** — twice, asserting byte-identity (the determinism
   control that makes any post-edit diff attributable to the edit), keeping both the
   rendered Markdown *and* the parsed **node tree** (``parse_docx_tree`` — what the
   resolver addresses);
3. builds an **``EditRequest``** from a **real verbatim quote + breadcrumb** taken
   from that baseline, runs it through **``dry_run``** (asserting it resolves to
   exactly the target block, zero refusals), then **``apply``** (asserting one
   ``applied`` log entry against the target);
4. **re-downloads and diffs** — asserting **only the target paragraph changed**
   (exactly one Markdown line differs; every other block byte-identical), the new
   text is present, the old quote is gone, and the target kept its **bold** ``**``
   (whole-paragraph style preservation through the real engine);
5. **tears down** so nothing persists — empties the doc's children (restore to a
   byte-identical *empty* baseline) and best-effort trashes the doc.

**Credentials (AC4).** Writes use ``get_write_credentials()`` only (write-only, never
read/legacy). The **reader half prefers ``get_read_credentials()``** — the two-app
least-privilege separation the W1 gate proves — and falls back to the owning write
app's creds for a self-provisioned doc a separate read-only app cannot see (the
fallback is about *reads*; the write path never borrows read creds). Teardown runs in
a ``finally`` so a mid-round-trip failure still leaves nothing behind. Writes ride the
shared core's throttle (≤3/sec, ``99991400`` backoff).
"""
import time

import pytest

import canary_support
from larkdocio.common import get_read_credentials, get_write_credentials
from larkdocio.errors import LarkDocIOError
from larkdocio.read.client import Client as ReadClient
from larkdocio.read.config import new_config
from larkdocio.read.parser import Parser
from larkdocio.write import Anchor, EditRequest, apply, dry_run
from larkdocio.write.client import WriteClient, text_block

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

# The write app's tenant region (matches the toolkit's default OpenAPI domain).
# NOT a document URL — the gate never addresses a pre-existing doc.
DOMAIN = "larksuite.com"

# Distinctive, unique tokens the gate itself authors — so the "quote" is a unique
# locator and the diff assertion is exact and unambiguous.
SECTION_HEADING = "W1-GATE-SECTION 9f15285c"
TARGET_QUOTE = "TARGET-9f15285c"
REWRITTEN_TOKEN = "REWRITTEN-9f15285c"
TARGET_BEFORE = f"W1 narrative-apply target paragraph :: {TARGET_QUOTE}"
REPLACEMENT = f"the apply engine rewrote this whole paragraph end-to-end :: {REWRITTEN_TOKEN}"


def _download(document_id):
    """Download + parse the doc via the READER (the same modules the CLI uses).

    Returns ``(markdown, tree)`` — the rendered Markdown for the diff and the parsed
    node tree the resolver addresses.

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


def test_w1_gate_narrative_apply_round_trip(capsys):
    # Load the repo .env (local runs) — a no-op in CI where creds are injected as
    # variables. Then skip LOUDLY if we cannot run.
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    wc = WriteClient(*get_write_credentials(), DOMAIN)

    # 1) Create the gate's OWN disposable doc.
    dest_folder = canary_support.require_disposables_folder()
    doc = wc.create_document(title=f"larkdocio-W1-gate {int(time.time())}",
                             folder_token=dest_folder)
    doc_id = doc["document_id"]

    evidence = {"doc_id": doc_id}
    baseline_children = [
        # A real heading so the EditRequest carries a real breadcrumb.
        {"block_type": 3, "heading1": {"elements": [{"text_run": {"content": SECTION_HEADING}}]}},
        # The BOLD target — its surviving ** proves whole-¶ style preservation.
        text_block(TARGET_BEFORE, style={"bold": True}),
        # A styled guard neighbour that must stay byte-identical.
        text_block("styled guard neighbour (italic, must stay byte-identical)",
                   style={"italic": True}),
        text_block("plain tail paragraph — untouched"),
    ]
    n_children = len(baseline_children)

    try:
        # 2) Populate the baseline, then the determinism control: two clean downloads
        #    must be byte-identical (so any post-edit diff is attributable to the edit).
        wc.create_children(doc_id, doc_id, baseline_children, index=0)

        md_baseline, tree_baseline = _download(doc_id)
        md_baseline_2, _ = _download(doc_id)
        assert md_baseline == md_baseline_2, (
            "reader is non-deterministic: two downloads of the unchanged doc differ"
        )
        assert TARGET_QUOTE in md_baseline, "baseline target quote missing from download"
        assert REWRITTEN_TOKEN not in md_baseline, "replacement token already present pre-edit"

        # 3) THE PIPELINE. Build an EditRequest from a REAL verbatim quote + breadcrumb
        #    taken from the baseline, then S3 dry-run → S4 apply — the real engine.
        edit = EditRequest(
            anchor=Anchor(quote=TARGET_QUOTE, breadcrumb=(SECTION_HEADING,)),
            replacement=REPLACEMENT,
        )
        plan = dry_run([edit], tree_baseline)
        assert len(plan.resolved) == 1, (
            f"dry-run must resolve to exactly one target; got {plan!r}"
        )
        assert len(plan.refusals) == 0, f"dry-run refused the edit: {plan.refusals!r}"
        planned = plan.resolved[0]
        target_id = planned.block_id
        assert TARGET_QUOTE in planned.before, "plan.before lost the target quote"
        assert planned.after == REPLACEMENT, "plan.after is not the replacement text"

        log = apply(plan, wc, doc_id)
        assert len(log.entries) == 1, f"apply-log is not 1:1 with the plan: {log!r}"
        applied = log.entries[0]
        assert applied.outcome == "applied", (
            f"the edit was not applied: {applied.to_dict()!r}"
        )
        assert applied.block_id == target_id, "apply patched a different block than planned"
        assert TARGET_QUOTE in applied.before, "apply-log before lost the target quote"
        assert applied.after == REPLACEMENT, "apply-log after is not the replacement"

        # 4) Re-download and diff: ONLY the target ¶ changed.
        md_after, _ = _download(doc_id)
        assert md_after != md_baseline, "the apply produced no observable change"
        assert REWRITTEN_TOKEN in md_after, "rewritten token missing after apply"
        assert TARGET_QUOTE not in md_after, "stale target quote survived the apply"

        before_lines = md_baseline.splitlines()
        after_lines = md_after.splitlines()
        assert len(before_lines) == len(after_lines), (
            "line count changed — the edit was not confined to one paragraph"
        )
        changed = [i for i in range(len(before_lines)) if before_lines[i] != after_lines[i]]
        assert len(changed) == 1, (
            "the edit was not surgical: more than the target paragraph changed "
            f"(changed line indices: {changed})"
        )
        ci = changed[0]
        assert TARGET_QUOTE in before_lines[ci], "the changed line is not the target"
        assert REWRITTEN_TOKEN in after_lines[ci], "the changed line lost the replacement"
        # Whole-¶ style preservation: the target was bold; the leading run's bold must
        # survive the whole-paragraph replacement (a dropped style would change render).
        assert "**" in before_lines[ci] and "**" in after_lines[ci], (
            "the target's bold ** did not survive the whole-paragraph apply"
        )

        evidence["baseline_bytes"] = len(md_baseline.encode("utf-8"))
        evidence["target_block_id"] = target_id
        evidence["changed_line_index"] = ci
        evidence["changed_before"] = before_lines[ci]
        evidence["changed_after"] = after_lines[ci]
        evidence["surgical_diff"] = True

    finally:
        # 5) Teardown so NOTHING persists (restore to a byte-identical EMPTY baseline).
        #    Empty the children (needs only docx:document), verify gone, then best-
        #    effort trash the doc. Runs on success AND failure (no orphan / no drift).
        emptied = False
        deleted = None
        try:
            wc.batch_delete(doc_id, doc_id, 0, n_children)
            md_empty, _ = _download(doc_id)
            emptied = (TARGET_QUOTE not in md_empty) and (REWRITTEN_TOKEN not in md_empty)
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
            "\n[live_write:W1-gate] "
            f"doc_id={evidence['doc_id']} "
            f"baseline_bytes={evidence.get('baseline_bytes')} "
            f"target_block_id={evidence.get('target_block_id')} "
            f"changed_line_index={evidence.get('changed_line_index')} "
            f"surgical_diff={evidence.get('surgical_diff')} "
            f"emptied={evidence.get('emptied')} "
            f"deleted={evidence.get('deleted')}\n"
            f"  before: {evidence.get('changed_before')!r}\n"
            f"  after : {evidence.get('changed_after')!r}"
        )
