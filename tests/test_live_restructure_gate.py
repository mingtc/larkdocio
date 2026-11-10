"""⛳ **THE RESTRUCTURE GATE** — a whole-document reorganisation, live, against a document
this gate makes itself (LD-471 AC5).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it with the whole ring::

    pytest -m live_write

**Why this one is worth a live arm.** The offline harness proves the shipped recipe *runs*.
Only a round trip proves the sentence the recipe exists for: **a fully-applied, refusal-free
log is compatible with a document in the wrong order** — order is precisely what the log does
not describe, so the read-back is the only witness. This gate therefore asserts the **order**
off a fresh read, not the calls' outcomes, and it asserts the other half too: the blocks the
longest-common-subsequence left alone still carry the **ids they had**, because a
reorganisation that re-created everything would pass an order check while destroying every
anchor in the document.

**The gate runs the guide's OWN code for the part that is easy to get subtly wrong**: the
`longest_common_subsequence` function is sliced out of the shipped recipe and executed here.
A recipe that shipped a broken LCS would redden this gate rather than a consumer's document.

**The comments leg is real, and its two halves are weighted differently.** The READ is what
the recipe's step 1 turns on — whether a re-create would strand a conversation — so it is
asserted: the read must be *available* (never read "unavailable" as "there are none") and the
orphan-risk join runs over the moved set. The comment CREATE that gives it something to find
is taken with the partial opt-in and **not** asserted: Lark answers its own `2200 Internal
Error` intermittently on a freshly created document (measured 2026-08-15 by this gate's own
probe), and a reorganisation gate a server-side flake can fail is a gate nobody trusts. When
the create does land, the gate asserts the distinction it demonstrates — a whole-document
comment is reachable by no block anchor, so it puts nothing at risk.

**Target policy (D-12).** The document is one this gate **creates itself** with the WRITE app,
empties and trashes in a ``finally``, its id ledgered by :mod:`docx_ledger` and independently
re-queried at close. Never the read canary, never the write scratch doc, never a real document.
"""
import time

import pytest

import canary_support
import docx_ledger
import guide_recipes as gr
import roundtrip_gate as rt
from larkdocio.comments import comments
from larkdocio.common import get_write_credentials
from larkdocio.model import plain_text, walk
from larkdocio.write import (
    AnchorById,
    CreateCommentRequest,
    DeleteRequest,
    InsertPosition,
    InsertRequest,
    NewBlock,
    apply,
    dry_run,
)
from larkdocio.write.client import WriteClient

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

RESTRUCTURE_SLUG = "reorganise-a-document-there-is-no-move-so-a-reorder-is-delete-and-recreate"

#: Seeded deliberately out of order — the shape of the incident this recipe was written for.
STEPS = [f"Step 2 — open an incident channel :: {rt.SUFFIX}",
         f"Step 3 — brief the duty manager :: {rt.SUFFIX}",
         f"Step 1 — page the on-call engineer :: {rt.SUFFIX}"]
DESIRED = ["Step 1", "Step 2", "Step 3"]


def _guide_lcs():
    """``longest_common_subsequence`` — sliced out of the SHIPPED recipe and executed.

    One definition, and the live gate runs the consumer's copy of it. Deliberately not
    re-implemented here: a second implementation would agree with itself and prove nothing.
    """
    source = "\n".join(gr.recipe_sources(RESTRUCTURE_SLUG))
    start = source.index("def longest_common_subsequence(")
    end = source.index("\n# ---", start)
    namespace = {}
    exec(compile(source[start:end], "<guide recipe: restructure>", "exec"), namespace)
    return namespace["longest_common_subsequence"]


def _ordered_steps(document_id):
    """``(tree, [(block_id, text)])`` for the seeded paragraphs, in the document's own order."""
    _markdown, root, revision = rt.download(document_id)
    steps = [(node.block_id, plain_text(node)) for node in walk(root)
             if rt.SUFFIX in plain_text(node) and rt.ANCHOR_LINE not in plain_text(node)]
    return root, revision, steps


def _labels(steps):
    return [next((fragment for fragment in DESIRED if fragment in text), text)
            for _block_id, text in steps]


def test_a_reorganisation_lands_the_ORDER_and_keeps_the_ids_that_did_not_move(
    capsys, tmp_path
):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    longest_common_subsequence = _guide_lcs()
    write_client = WriteClient(*get_write_credentials(), rt.DOMAIN)
    ledger = docx_ledger.Ledger(tmp_path / "ledger.json")
    evidence = {}

    try:
        with docx_ledger.disposable(
            write_client, ledger, title=f"larkdocio-LD-471-restructure {int(time.time())}",
        ) as target:
            document_id = target.document_id
            evidence["document_id"] = document_id
            try:
                rt.seed_paragraphs(write_client, document_id, [rt.ANCHOR_LINE] + STEPS)

                # A real comment on the file, so step 1 has something to find. Taken with the
                # opt-in and NOT asserted: comment creation answers Lark's own `2200 Internal
                # Error` intermittently on a freshly created document (measured 2026-08-15,
                # this gate's own probe), and a reorganisation gate that a server-side flake
                # can fail is a gate nobody trusts. The leg under test is the READ.
                commented = apply(
                    dry_run([CreateCommentRequest(
                        text=f"the reviewer's note :: {rt.SUFFIX}")], None),
                    write_client, document_id=document_id, allow_partial=True)
                (comment_entry,) = commented.entries
                evidence["comment_created"] = comment_entry.outcome
                if comment_entry.refusal is not None:
                    evidence["comment_refusal"] = comment_entry.refusal.detail

                # --- STEP 1: THE COMMENTS, FIRST -------------------------------- #
                review = comments(document_id)
                assert review.available, review.unavailable_reason
                evidence["comments_read"] = review.completeness
                evidence["unanchored"] = list(review.unanchored_ids)
                if comment_entry.outcome == "commented":
                    # It is reachable by no block anchor, so it puts nothing at risk — and
                    # that is a DISTINCTION, not an empty list: the comment really is there.
                    assert review.unanchored_ids, review.disclosure

                # --- STEP 2: WHAT IS ALREADY IN THE RIGHT PLACE ------------------ #
                root, revision, steps = _ordered_steps(document_id)
                evidence["before"] = _labels(steps)
                assert evidence["before"] == ["Step 2", "Step 3", "Step 1"], evidence["before"]

                texts = dict(steps)
                current_ids = [block_id for block_id, _text in steps]
                desired_ids = [next(block_id for block_id, text in steps if fragment in text)
                               for fragment in DESIRED]
                kept = set(longest_common_subsequence(current_ids, desired_ids))
                moved_ids = [b for b in desired_ids if b not in kept]
                assert len(moved_ids) == 1, (moved_ids, kept)
                evidence["kept_ids"] = sorted(kept)
                evidence["moved_ids"] = moved_ids

                # --- STEP 3: THE ORPHAN RISK, over the MOVED set ----------------- #
                at_risk = {block_id: [c.text for c in review.for_node(node)]
                           for node in walk(root)
                           for block_id in [node.block_id] if block_id in set(moved_ids)}
                assert not any(at_risk.values()), at_risk

                # --- STEP 4: INSERT THE COPIES, BEFORE ANY DELETE ---------------- #
                requests, run, anchor = [], [], None
                for block_id in desired_ids:
                    if block_id in kept:
                        if run:
                            requests.append((anchor, tuple(run)))
                            run = []
                        anchor = block_id
                    else:
                        run.append(NewBlock.paragraph(texts[block_id]))
                if run:
                    requests.append((anchor, tuple(run)))
                first_kept = next(b for b in desired_ids if b in kept)
                inserts = [InsertRequest(
                    reference=AnchorById(block_id=anchor or first_kept),
                    position=InsertPosition.AFTER if anchor else InsertPosition.BEFORE,
                    content=content) for anchor, content in requests]
                plan = dry_run(inserts, root, document_revision_id=revision)
                assert plan.revision_guard == "active", plan.revision_guard
                log = apply(plan, write_client, document_id=document_id)
                recreated = [b for entry in log for b in entry.created_block_ids]
                evidence["recreated"] = recreated
                assert len(recreated) == len(moved_ids), (recreated, moved_ids)

                # The DUPLICATION state is real and is the point of the ordering: at this
                # moment the document holds the moved content twice, never zero times.
                _root, _rev, mid = _ordered_steps(document_id)
                assert len(mid) == len(STEPS) + 1, _labels(mid)

                # --- STEP 5: NOW DELETE THE ORIGINALS ---------------------------- #
                root, revision, _steps = _ordered_steps(document_id)
                removals = dry_run(
                    [DeleteRequest(target=AnchorById(block_id=b)) for b in moved_ids],
                    root, document_revision_id=revision)
                removal_log = apply(removals, write_client, document_id=document_id)
                assert not removal_log.refusals, [e.to_dict() for e in removal_log.refusals]
                assert all(entry.removed_payload for entry in removal_log.applied), (
                    "a delete with no removed_payload is a destructive edit with no record")

                # --- STEP 6: THE READ-BACK, AND IT ASSERTS THE ORDER ------------- #
                _root, _rev, after = _ordered_steps(document_id)
                evidence["after"] = _labels(after)
                assert evidence["after"] == DESIRED, evidence["after"]

                surviving = [block_id for block_id, _text in after if block_id in kept]
                assert surviving == [b for b in desired_ids if b in kept], (
                    "a block nobody asked to move was re-created — its id, and everything "
                    "anchored to it, is gone")
                assert moved_ids[0] not in [b for b, _t in after]
            finally:
                evidence["children_removed"] = rt.empty_document(write_client, document_id)

        report = docx_ledger.close_out(write_client, ledger)
        report.raise_if_orphans()
        evidence["close_out"] = report.to_dict()
    finally:
        with capsys.disabled():
            print("\n[restructure gate]")
            for key, value in evidence.items():
                print(f"  {key}: {value}")
