"""THE S4 GATE — the binding **by-id anchoring** round-trip (LD-137).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it with the whole ring::

    pytest -m live_write

Dogfood **F19** in one sentence: ``apply()`` has always handed back ``created_block_ids``, but
anchors were **quote-only**, so following up on a block you just created meant round-tripping a
verbatim quote out of a fresh read. This gate proves the loop S4 exists for — **author, take
the ids back, anchor the follow-ups by them** — against a real document, plus the two staleness
arms that only a live document can prove.

The ring, against a doc it **creates and destroys itself** (never the read canary, never the
block-zoo doc, never the standing sandbox, never a real document):

1. **creates its own disposable doc** and seeds a two-block narrative baseline (a heading + a
   paragraph) so the first insert has a real reference **anchor**;
2. **downloads + parses it twice**, asserting byte-identity — the determinism control that
   makes every later diff attributable to a write;
3. **authors two blocks through the gate**, anchored the *old* way (a verbatim quote +
   breadcrumb), and keeps the **``created_block_ids``** ``apply`` returns — the ids everything
   below anchors by;
4. **ID-ANCHORED INSERT**: inserts a paragraph ``AFTER`` the created paragraph, addressed **by
   the id ``apply`` just returned** — asserting the plan captured the by-id staleness
   precondition, and that the new line reads back **immediately after** its reference (the
   position semantics, proven live) and the write was **purely additive**;
5. **the COMPARE-AND-SWAP arm**: plans an id-anchored edit, then simulates a concurrent editor
   by rewriting that block out of band, then applies — the entry must refuse **`stale-anchor`
   with no write** (asserted by re-reading: the replacement text never appears);
6. **ID-ANCHORED DELETE**: removes the by-id-inserted block **by its id**, asserting the
   destructive-safe ``removed_payload`` carries what was there and that exactly that one
   Markdown line disappeared (surgical);
7. **the STALE-RACE arm**: a plan built while that block still existed, applied **after** it was
   deleted, must refuse ``stale-anchor`` too — the block cannot be re-read, so what the plan
   previewed cannot be confirmed. No write, no exception, an apply-log all the same;
8. **the VANISHED-ID refusal**: the same (now genuinely dead) live id refuses ``not-found`` at
   dry-run **with the id named in the detail** — the LD-131 mandatory-detail contract on a real
   id, not a synthetic one;
8b. **the ONE-TREE-ONE-BATCH refusal (LD-151 / dogfood F14)**: a two-request batch that queues
   an insert and then anchors on the text that insert *would* create refuses ``not-found`` on a
   **real tree**, and the detail carries the intra-batch cause plus the recovery the arms above
   have already proven live (commit, then anchor by ``created_block_ids``). Dry-run only — zero
   API calls, zero writes, and the document is re-read afterwards to prove it;
9. **tears down** in a ``finally`` so nothing persists — empties the doc's children, verifies
   the authored content is gone, and best-effort trashes the doc.

**The ROOT arm (LD-141)** rides in a **second, separately-provisioned doc** —
``test_s4_gate_ld141_id_anchored_append_into_the_document_root`` — kept apart so it cannot
perturb the ring's line-position and diff assertions. It anchors the document **root by its own
id** with ``APPEND_INTO`` (the only anchor an empty document offers, and the only position the
root accepts) and runs the **title-quote control** beside it. The root is the one node whose own
text lives under its ``page`` container instead of an inline ``content`` list — a shape only a
live root block has — and the ring's blindness to it is how a false ``stale-anchor`` on every
id-anchored root write shipped past a green suite.

**Credentials.** Writes use ``get_write_credentials()`` only. The reader half prefers
``get_read_credentials()`` (the two-app least-privilege separation) and falls back to the
owning write app for a self-provisioned doc a read-only app cannot see — a *read* fallback
only; the write path never borrows read creds. Writes ride the shared throttle (≤3/sec,
``99991400`` backoff).
"""
import difflib
import time

import pytest

import canary_support
from log_reading_apply import reading_the_log
from larkdocio.common import get_read_credentials, get_write_credentials
from larkdocio.errors import LarkDocIOError
from larkdocio.read.client import Client as ReadClient
from larkdocio.read.config import new_config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    Anchor,
    AnchorById,
    DeleteRequest,
    EditRequest,
    InsertPosition,
    InsertRequest,
    NewBlock,
    RefusalReason,
    apply,
    build_whole_paragraph_update,
    dry_run,
)
from larkdocio.write.client import WriteClient, text_block
from larkdocio.write.intrabatch import INTRA_BATCH_HEDGE

# This gate's subject is the LOG — which entry landed, which refused, with which typed
# reason — not the return-vs-raise policy (pinned offline in
# tests/test_apply_refusal_policy.py, proved live in
# tests/test_live_write_refusal_policy_gate.py). So it opts into partial application
# once, here, the same way the offline log-reading suites do.
apply = reading_the_log(apply)

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

# The write app's tenant region (the toolkit's default OpenAPI domain). NOT a document URL —
# the gate never addresses a pre-existing doc.
DOMAIN = "larksuite.com"

# Unique, greppable tokens the gate authors itself, so every assertion is exact.
SUFFIX = "s4gate-71b3fd0e"
SECTION_HEADING = f"S4-GATE-SECTION {SUFFIX}"
ANCHOR_LINE = f"anchor paragraph for the first insert :: {SUFFIX}"

AUTHORED_HEADING = f"Findings :: {SUFFIX}"
AUTHORED_LINE = f"authored by a QUOTE anchor :: {SUFFIX}"
BY_ID_LINE = f"authored by an ID anchor :: {SUFFIX}"
DRIFT_LINE = f"rewritten out of band by somebody else :: {SUFFIX}"
NEVER_LINE = f"THIS MUST NEVER REACH THE DOCUMENT :: {SUFFIX}"
# The one-tree-one-batch arm's sentence: authored only INSIDE a queued insert, so it exists
# nowhere in the live document at the moment the batch is planned. Never applied.
INTRA_BATCH_LINE = f"queued by this batch and therefore not in the tree yet :: {SUFFIX}"

# LD-141's root arm (a second, separately-provisioned doc — see its test below).
ROOT_BY_ID_LINE = f"appended INTO the document root BY ITS ID :: {SUFFIX}"
ROOT_QUOTE_LINE = f"appended INTO the document root by its TITLE QUOTE :: {SUFFIX}"


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


def _line_index(markdown, needle):
    """The index of the single Markdown line containing ``needle`` (asserts uniqueness)."""
    hits = [i for i, line in enumerate(markdown.splitlines()) if needle in line]
    assert len(hits) == 1, f"expected exactly one line carrying {needle!r}; got {hits}"
    return hits[0]


def _live_own_text(block):
    """A live block's own ``text_run`` text — the exact reduction the apply engine's
    pre-write re-validation performs (find the type-named content container, concatenate its
    ``text_run`` contents). Used by the LD-141 root arm to read what the engine WILL compare
    the plan's precondition against, rather than assuming it."""
    return "".join(
        element["text_run"].get("content", "")
        for value in block.values()
        if isinstance(value, dict) and isinstance(value.get("elements"), list)
        for element in value["elements"] if element.get("text_run") is not None)


def test_s4_gate_anchor_by_id_round_trip(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    wc = WriteClient(*get_write_credentials(), DOMAIN)

    # 1) The gate's OWN disposable doc + a narrative baseline to anchor against.
    dest_folder = canary_support.require_disposables_folder()
    doc = wc.create_document(title=f"larkdocio-S4-anchor-by-id-gate {int(time.time())}",
                             folder_token=dest_folder)
    doc_id = doc["document_id"]
    evidence = {"doc_id": doc_id}
    seed = [
        {"block_type": 3,
         "heading1": {"elements": [{"text_run": {"content": SECTION_HEADING}}]}},
        text_block(ANCHOR_LINE),
    ]

    try:
        wc.create_children(doc_id, doc_id, seed, index=0)

        # 2) Baseline + the determinism control.
        md_baseline, tree_baseline = _download(doc_id)
        md_baseline_2, _ = _download(doc_id)
        assert md_baseline == md_baseline_2, (
            "reader is non-deterministic: two downloads of the unchanged doc differ")

        # 3) AUTHOR through the gate with a QUOTE anchor — and keep the ids it returns.
        quote_insert = InsertRequest(
            reference=Anchor(quote=ANCHOR_LINE, breadcrumb=(SECTION_HEADING,)),
            position=InsertPosition.AFTER,
            content=(NewBlock.heading(2, AUTHORED_HEADING),
                     NewBlock.paragraph(AUTHORED_LINE)),
        )
        plan = dry_run([quote_insert], tree_baseline)
        assert len(plan.refusals) == 0, f"dry-run refused the insert: {plan.refusals!r}"
        assert plan.resolved[0].precondition_text is None, (
            "a QUOTE-anchored entry must carry no by-id precondition")
        log = apply(plan, wc, doc_id)
        created = log.entries[0]
        assert created.outcome == "inserted", created.to_dict()
        assert len(created.created_block_ids) == 2 and all(created.created_block_ids), (
            f"apply() must return one id per authored block: {created.created_block_ids!r}")
        heading_id, paragraph_id = created.created_block_ids
        evidence["created_block_ids"] = list(created.created_block_ids)

        md_created, tree_created = _download(doc_id)
        assert AUTHORED_LINE in md_created and AUTHORED_HEADING in md_created, md_created
        removed = [d for d in difflib.ndiff(md_baseline.splitlines(),
                                            md_created.splitlines()) if d.startswith("- ")]
        assert not removed, f"the first insert was not purely additive; lost: {removed}"

        # 4) ID-ANCHORED INSERT — addressed by the id apply() just returned (F19's loop).
        by_id_insert = InsertRequest(
            reference=AnchorById(block_id=paragraph_id),
            position=InsertPosition.AFTER,
            content=(NewBlock.paragraph(BY_ID_LINE),),
        )
        by_id_plan = dry_run([by_id_insert], tree_created)
        assert len(by_id_plan.refusals) == 0, (
            f"the by-id insert refused at dry-run: {by_id_plan.refusals!r}")
        (by_id_entry,) = by_id_plan.resolved
        assert by_id_entry.block_id == paragraph_id, (
            "the by-id reference did not resolve to the block the engine created")
        assert by_id_entry.precondition_text == AUTHORED_LINE, (
            f"the plan must capture the by-id staleness precondition: "
            f"{by_id_entry.precondition_text!r}")
        by_id_log = apply(by_id_plan, wc, doc_id)
        assert by_id_log.entries[0].outcome == "inserted", by_id_log.entries[0].to_dict()
        (by_id_block,) = by_id_log.entries[0].created_block_ids
        assert by_id_block, "the id-anchored insert returned no created id"
        evidence["by_id_created"] = by_id_block

        md_by_id, tree_by_id = _download(doc_id)
        assert _line_index(md_by_id, BY_ID_LINE) == _line_index(md_by_id, AUTHORED_LINE) + 2, (
            "position=AFTER did not place the by-id insert immediately after its reference")
        removed = [d for d in difflib.ndiff(md_created.splitlines(),
                                            md_by_id.splitlines()) if d.startswith("- ")]
        assert not removed, f"the by-id insert was not purely additive; lost: {removed}"

        # 5) THE COMPARE-AND-SWAP ARM — plan, let somebody else edit the block, then apply.
        stale_plan = dry_run(
            [EditRequest(anchor=AnchorById(block_id=by_id_block), replacement=NEVER_LINE)],
            tree_by_id)
        assert len(stale_plan.refusals) == 0, stale_plan.refusals
        # the "concurrent editor": rewrite the very block the plan is anchored to.
        wc._patch_block(doc_id, by_id_block, build_whole_paragraph_update([], DRIFT_LINE))
        stale_log = apply(stale_plan, wc, doc_id)
        (stale_entry,) = stale_log.entries
        assert stale_entry.outcome == "refused", stale_entry.to_dict()
        assert stale_entry.refusal.reason is RefusalReason.STALE_ANCHOR, (
            stale_entry.to_dict())
        assert by_id_block in stale_entry.refusal.detail
        evidence["compare_and_swap_detail"] = stale_entry.refusal.detail

        md_drifted, tree_drifted = _download(doc_id)
        assert NEVER_LINE not in md_drifted, (
            "a stale id-anchored edit WROTE — the compare-and-swap did not hold")
        assert DRIFT_LINE in md_drifted, md_drifted

        # 6+7) Plan two ops against the current tree, DELETE by id, then apply the other one
        #      against the block that no longer exists (the stale race).
        race_plan = dry_run(
            [EditRequest(anchor=AnchorById(block_id=by_id_block), replacement=NEVER_LINE)],
            tree_drifted)
        delete_plan = dry_run([DeleteRequest(target=AnchorById(block_id=by_id_block))],
                              tree_drifted)
        assert len(delete_plan.refusals) == 0, delete_plan.refusals
        assert delete_plan.resolved[0].block_id == by_id_block

        delete_log = apply(delete_plan, wc, doc_id)
        (deleted_entry,) = delete_log.entries
        assert deleted_entry.outcome == "deleted", deleted_entry.to_dict()
        assert deleted_entry.block_id == by_id_block
        payload_text = "".join(
            e.get("text_run", {}).get("content", "")
            for e in deleted_entry.removed_payload.get("elements", []))
        assert DRIFT_LINE in payload_text, (
            f"the destructive delete lost its removed payload: "
            f"{deleted_entry.removed_payload!r}")
        evidence["removed_payload_text"] = payload_text

        md_deleted, _ = _download(doc_id)
        assert DRIFT_LINE not in md_deleted, md_deleted
        gone = [d for d in difflib.ndiff(md_drifted.splitlines(), md_deleted.splitlines())
                if d.startswith("- ")]
        assert [d for d in gone if DRIFT_LINE in d], gone
        added = [d for d in difflib.ndiff(md_drifted.splitlines(), md_deleted.splitlines())
                 if d.startswith("+ ") and d.strip("+ ")]
        assert not added, f"the by-id delete was not surgical; it added lines: {added}"
        assert AUTHORED_LINE in md_deleted and SECTION_HEADING in md_deleted, (
            "the by-id delete removed more than its target")

        # 7) THE STALE RACE — the plan was built while the block existed; it is gone now.
        race_log = apply(race_plan, wc, doc_id)
        (race_entry,) = race_log.entries
        assert race_entry.outcome == "refused", race_entry.to_dict()
        assert race_entry.refusal.reason is RefusalReason.STALE_ANCHOR, race_entry.to_dict()
        assert by_id_block in race_entry.refusal.detail
        evidence["stale_race_detail"] = race_entry.refusal.detail

        md_race, tree_race = _download(doc_id)
        assert md_race == md_deleted, (
            "the stale-race entry WROTE — a vanished block must refuse with zero writes")

        # 8) THE VANISHED-ID REFUSAL — the same real, now-dead id, refused WITH its detail.
        vanished = dry_run([DeleteRequest(target=AnchorById(block_id=by_id_block))], tree_race)
        (vanished_entry,) = vanished.entries
        assert not vanished_entry.is_resolved, vanished_entry.to_dict()
        assert vanished_entry.refusal.reason is RefusalReason.NOT_FOUND, (
            vanished_entry.to_dict())
        assert by_id_block in vanished_entry.refusal.detail, (
            "a vanished id must refuse with the ID NAMED in the detail (LD-131)")
        evidence["vanished_detail"] = vanished_entry.refusal.detail

        # 8b) THE ONE-TREE-ONE-BATCH ARM (LD-151 / dogfood F14) — a batch cannot depend on its
        #     own writes, proven on a REAL tree. Queue an insert whose authored sentence exists
        #     nowhere in the document, then anchor an edit on that very sentence: the second
        #     entry refuses `not-found` and its detail names the intra-batch cause plus the
        #     recovery this member has already proven live (commit, then anchor by
        #     created_block_ids). Dry-run only — `dry_run` takes no client, so this arm issues
        #     ZERO API calls and the plan is never applied.
        intra = dry_run([
            InsertRequest(
                reference=Anchor(quote=ANCHOR_LINE, breadcrumb=(SECTION_HEADING,)),
                position=InsertPosition.AFTER,
                content=(NewBlock.paragraph(INTRA_BATCH_LINE),),
            ),
            EditRequest(anchor=Anchor(quote=INTRA_BATCH_LINE, breadcrumb=()),
                        replacement=NEVER_LINE),
        ], tree_race)
        intra_insert, intra_edit = intra.entries
        assert intra_insert.is_resolved, intra_insert.to_dict()
        assert not intra_edit.is_resolved, intra_edit.to_dict()
        assert intra_edit.refusal.reason is RefusalReason.NOT_FOUND, intra_edit.to_dict()
        assert INTRA_BATCH_HEDGE in intra_edit.refusal.detail, (
            "the intra-batch refusal must carry the commit-then-anchor recovery, not the "
            f"re-read that cannot succeed: {intra_edit.refusal.detail!r}")
        evidence["intra_batch_detail"] = intra_edit.refusal.detail

        md_intra, _ = _download(doc_id)
        assert md_intra == md_race, "the intra-batch arm WROTE — a dry-run must not touch Lark"

    finally:
        # 9) Teardown so NOTHING persists — on success AND failure.
        emptied = False
        deleted = None
        try:
            # Empty the whole top level, read off the LIVE root rather than counted by hand:
            # this gate's own ring deletes one of the blocks it created, so a hard-coded range
            # would be wrong by exactly that block (and an over-wide range is an API error that
            # leaves the content behind).
            live_children = wc.get_block(doc_id, doc_id).get("children") or []
            if live_children:
                wc.batch_delete(doc_id, doc_id, 0, len(live_children))
            md_empty, _ = _download(doc_id)
            emptied = (
                SECTION_HEADING not in md_empty
                and AUTHORED_LINE not in md_empty
                and AUTHORED_HEADING not in md_empty
                and BY_ID_LINE not in md_empty
                and DRIFT_LINE not in md_empty
                and NEVER_LINE not in md_empty
                and INTRA_BATCH_LINE not in md_empty
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

    assert emptied, "teardown failed: authored content still present after restore"

    with capsys.disabled():
        print(
            "\n[live_write:S4-anchor-by-id-gate] "
            f"doc_id={evidence['doc_id']} "
            f"created_block_ids={evidence.get('created_block_ids')} "
            f"by_id_created={evidence.get('by_id_created')} "
            f"emptied={evidence.get('emptied')} "
            f"deleted={evidence.get('deleted')}\n"
            f"  removed payload text : {evidence.get('removed_payload_text')!r}\n"
            f"  compare-and-swap     : {evidence.get('compare_and_swap_detail')!r}\n"
            f"  stale race (deleted) : {evidence.get('stale_race_detail')!r}\n"
            f"  vanished id (dry-run): {evidence.get('vanished_detail')!r}\n"
            f"  intra-batch (dry-run): {evidence.get('intra_batch_detail')!r}"
        )


def test_s4_gate_ld141_id_anchored_append_into_the_document_root(capsys):
    """LD-141 — THE ROOT ARM, live: an ``APPEND_INTO`` anchored at the document root **by its
    id**, with the title-quote control beside it, against a doc created empty.

    The root is the only anchor target an empty document offers (``GUIDE.md`` § "Recipe: write
    into an empty document") and ``APPEND_INTO`` is the only position it accepts, so this is
    the one anchor a from-scratch authoring pass reaches for by id. It is also the only node
    whose own text lives under its ``page`` container rather than an inline ``content`` list —
    a shape **only a live root block** has. That asymmetry is what let a false ``stale-anchor``
    ship: the plan captured ``''`` off ``content`` while the engine read the live page title
    back, so the write refused every time on an untouched document. The quote-anchored control
    applied fine, which is what made it a by-id-**only** regression — so both anchor kinds run
    here, against the same document, in one run.

    Its OWN disposable doc, created and destroyed in this test — never the read canary, the
    block zoo, the sandbox, or a real document. Kept separate from the ring above so the root
    arm cannot perturb that ring's line-position and diff assertions.
    """
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    wc = WriteClient(*get_write_credentials(), DOMAIN)
    requested_title = f"larkdocio-LD141-root-anchor-gate {int(time.time())}"
    dest_folder = canary_support.require_disposables_folder()
    doc = wc.create_document(title=requested_title, folder_token=dest_folder)
    doc_id = doc["document_id"]
    evidence = {"doc_id": doc_id, "requested_title": requested_title}

    try:
        # A docx document_id IS its root block id, so this reads the page block itself —
        # exactly the read the engine's pre-write re-validation will perform.
        live_root = wc.get_block(doc_id, doc_id)
        root_title = _live_own_text(live_root)
        evidence["live_root_keys"] = sorted(live_root)
        evidence["live_root_text"] = root_title
        assert root_title, (
            f"the live root carries no own text to anchor on: keys={sorted(live_root)}")

        # Baseline + the determinism control that makes every later diff attributable.
        md_baseline, tree_baseline = _download(doc_id)
        md_baseline_2, _ = _download(doc_id)
        assert md_baseline == md_baseline_2, (
            "reader is non-deterministic: two downloads of the unchanged doc differ")
        assert tree_baseline.block_id == doc_id, (
            f"the parsed root must carry the document id as its block_id (that is what makes "
            f"AnchorById(doc_id) resolvable): {tree_baseline.block_id!r}")

        # THE BUG — the root, by id, APPEND_INTO, on a document nothing has touched.
        by_id_plan = dry_run(
            [InsertRequest(reference=AnchorById(block_id=doc_id),
                           position=InsertPosition.APPEND_INTO,
                           content=(NewBlock.paragraph(ROOT_BY_ID_LINE),))],
            tree_baseline)
        assert len(by_id_plan.refusals) == 0, (
            f"the root-id insert refused at dry-run: {by_id_plan.refusals!r}")
        (by_id_entry,) = by_id_plan.resolved
        assert by_id_entry.block_id == doc_id
        assert by_id_entry.precondition_text == root_title, (
            f"the by-id precondition must be what the live root READS BACK — its page title "
            f"(LD-141): captured {by_id_entry.precondition_text!r}, live {root_title!r}")
        evidence["by_id_precondition"] = by_id_entry.precondition_text

        by_id_log = apply(by_id_plan, wc, doc_id)
        (by_id_applied,) = by_id_log.entries
        assert by_id_applied.outcome == "inserted", (
            f"an id-anchored APPEND_INTO against the UNTOUCHED document root was refused — "
            f"LD-141 has regressed: {by_id_applied.to_dict()}")
        (by_id_created,) = by_id_applied.created_block_ids
        assert by_id_created, "the root-id insert returned no created id"
        evidence["by_id_created"] = by_id_created

        md_root, tree_root = _download(doc_id)
        assert ROOT_BY_ID_LINE in md_root, md_root
        removed = [d for d in difflib.ndiff(md_baseline.splitlines(), md_root.splitlines())
                   if d.startswith("- ")]
        assert not removed, f"the root-id insert was not purely additive; lost: {removed}"

        # THE CONTROL — the identical insert anchored by the root's TITLE QUOTE. It always
        # worked; asserting it here is what keeps "by-id is interchangeable" honest.
        quote_plan = dry_run(
            [InsertRequest(reference=Anchor(quote=root_title),
                           position=InsertPosition.APPEND_INTO,
                           content=(NewBlock.paragraph(ROOT_QUOTE_LINE),))],
            tree_root)
        assert len(quote_plan.refusals) == 0, (
            f"the title-quote control refused at dry-run: {quote_plan.refusals!r}")
        (quote_entry,) = quote_plan.resolved
        assert quote_entry.block_id == doc_id, (
            "the title quote must resolve to the same root block the id did")
        assert quote_entry.precondition_text is None, (
            "a QUOTE-anchored entry must carry no by-id precondition")
        quote_log = apply(quote_plan, wc, doc_id)
        (quote_applied,) = quote_log.entries
        assert quote_applied.outcome == "inserted", quote_applied.to_dict()
        evidence["quote_created"] = list(quote_applied.created_block_ids)

        md_final, _ = _download(doc_id)
        assert ROOT_QUOTE_LINE in md_final, md_final
        removed = [d for d in difflib.ndiff(md_root.splitlines(), md_final.splitlines())
                   if d.startswith("- ")]
        assert not removed, f"the control insert was not purely additive; lost: {removed}"
        assert _line_index(md_final, ROOT_QUOTE_LINE) > _line_index(md_final, ROOT_BY_ID_LINE), (
            "APPEND_INTO must append LAST — the second insert landed above the first")
        evidence["both_anchor_kinds_inserted"] = True

    finally:
        # Teardown so NOTHING persists — on success AND failure.
        emptied = False
        deleted = None
        try:
            live_children = wc.get_block(doc_id, doc_id).get("children") or []
            if live_children:
                wc.batch_delete(doc_id, doc_id, 0, len(live_children))
            md_empty, _ = _download(doc_id)
            emptied = ROOT_BY_ID_LINE not in md_empty and ROOT_QUOTE_LINE not in md_empty
        except LarkDocIOError as e:
            evidence["empty_error"] = str(e)
        try:
            resp = wc.delete_document(doc_id)
            deleted = resp.get("code") if isinstance(resp, dict) else "ok"
        except LarkDocIOError as e:
            deleted = f"skipped ({e})"
        evidence["emptied"] = emptied
        evidence["deleted"] = deleted

    assert emptied, "teardown failed: authored content still present after restore"

    with capsys.disabled():
        print(
            "\n[live_write:S4-anchor-by-id-gate:LD-141-root] "
            f"doc_id={evidence['doc_id']} "
            f"by_id_created={evidence.get('by_id_created')} "
            f"quote_created={evidence.get('quote_created')} "
            f"emptied={evidence.get('emptied')} "
            f"deleted={evidence.get('deleted')}\n"
            f"  live root keys       : {evidence.get('live_root_keys')}\n"
            f"  live root own text   : {evidence.get('live_root_text')!r}\n"
            f"  by-id precondition   : {evidence.get('by_id_precondition')!r}"
        )
