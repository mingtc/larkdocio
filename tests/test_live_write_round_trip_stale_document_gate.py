"""⛳ **THE ROUND-TRIP GATE, arm 3 of 4 — `STALE_DOCUMENT`, live, WITH RECOVERY**
(LD-236; the Markdown-authoring spec's § F1-S7 concurrency arm is the blueprint).

``@pytest.mark.live_write``, deselected by default. Run it with the whole ring::

    pytest -m live_write

**What this arm proves.** A reconciliation is planned against the document as it was read.
Then a **second client** edits the document out of band — the case the per-anchor
``STALE_ANCHOR`` check is structurally blind to, because the drifted block is not the one the
plan touches. ``apply`` then refuses the **whole batch** with ``STALE_DOCUMENT``, **zero
writes measured at the client boundary**, and the document is **byte-unchanged** from its
post-out-of-band state. Finally — and this is the half that makes the refusal usable rather
than merely safe — the same edit **re-planned against a fresh read applies**.

Only a real document can prove this: the guard compares a ``revision_id`` Lark itself
advances, so a double can model the comparison but not the advance.

**Target policy (the round-trip-editing spec § gate 3).** A document this arm creates itself, empties and trashes in
a ``finally``, ledgered and independently re-queried at close. Never the canary, never the
zoo, never a real document.
"""
import time

import pytest

import canary_support
import docx_ledger
import roundtrip_gate as rt
from log_reading_apply import reading_the_log
from larkdocio.common import get_write_credentials
from larkdocio.write import apply, compile_reconciliation, dry_run, reconcile
from larkdocio.write.client import WriteClient, text_block
from larkdocio.write.model import RefusalReason

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

TARGET_LINE = f"the block the reconciliation edits :: {rt.SUFFIX}"
EDITED_LINE = f"the block the reconciliation edits, rewritten :: {rt.SUFFIX}"
OUT_OF_BAND_LINE = f"an out of band edit from a second client :: {rt.SUFFIX}"


def test_drift_under_the_plan_refuses_the_whole_batch_and_a_re_plan_then_applies(
    capsys, tmp_path,
):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    write_client = WriteClient(*get_write_credentials(), rt.DOMAIN)
    # A genuinely SECOND client — its own object, its own token fetch, its own transport and
    # throttle. The out-of-band edit has to come from somewhere other than the object applying
    # the batch, or the arm is a document editing itself.
    other_client = WriteClient(*get_write_credentials(), rt.DOMAIN)
    ledger = docx_ledger.Ledger(tmp_path / "ledger.json")
    evidence = {}

    try:
        with docx_ledger.disposable(
            write_client, ledger,
            title=f"larkdocio-LD-236-stale-document {int(time.time())}",
        ) as doc:
            doc_id = doc.document_id
            evidence["doc_id"] = doc_id
            try:
                rt.seed_paragraphs(write_client, doc_id, [rt.ANCHOR_LINE, TARGET_LINE])

                # 1. PLAN against the document as read (the revision ARMS the guard).
                _md, root, revision, projection = rt.project(doc_id)
                evidence["baseline_revision"] = revision
                plan = reconcile(
                    projection, projection.markdown.replace(TARGET_LINE, EDITED_LINE))
                assert plan.ok, plan.to_dict()
                requests = compile_reconciliation(plan, projection)
                preview = dry_run(requests, root, document_revision_id=revision)
                evidence["revision_guard"] = preview.revision_guard
                assert preview.revision_guard == "active", preview.revision_guard_detail

                # 2. THE OUT-OF-BAND EDIT, from the second client. It deliberately does NOT
                #    touch the block the plan targets, so STALE_ANCHOR is blind to it.
                other_client.create_children(
                    doc_id, doc_id, [text_block(OUT_OF_BAND_LINE)], index=0)
                drifted, _root, drifted_revision = rt.download(doc_id)
                evidence["drifted_revision"] = drifted_revision
                assert drifted_revision != revision, "the out-of-band edit did not drift"

                # 3. APPLY → the WHOLE batch refuses, with ZERO writes measured.
                with rt.measured_writes(write_client) as writes:
                    log = apply(preview, write_client, document_id=doc_id)
                evidence["writes_during_refusal"] = list(writes)
                reasons = [e.to_dict().get("refusal", {}).get("reason") for e in log.entries]
                evidence["refusal_reasons"] = reasons
                assert reasons and set(reasons) == {RefusalReason.STALE_DOCUMENT.value}, (
                    [e.to_dict() for e in log.entries])
                assert writes == [], (
                    "STALE_DOCUMENT must refuse the whole batch BEFORE any write is issued")

                after_refusal, _root, _rev = rt.download(doc_id)
                evidence["byte_unchanged_after_refusal"] = after_refusal == drifted
                assert after_refusal == drifted, rt.changed_lines(drifted, after_refusal)

                # 4. THE RECOVERY: re-download, re-project, re-plan — and it APPLIES.
                _md2, root2, revision2, projection2 = rt.project(doc_id)
                result = rt.apply_edited_projection(
                    write_client, doc_id, root=root2, revision=revision2,
                    projection=projection2,
                    edited_markdown=projection2.markdown.replace(TARGET_LINE, EDITED_LINE),
                )
                evidence["replan_outcomes"] = [
                    e.to_dict()["outcome"] for e in result["log"].entries]
                assert result["plan"].ok, result["plan"].to_dict()
                assert evidence["replan_outcomes"] == ["applied"], (
                    [e.to_dict() for e in result["log"].entries])

                recovered, _root, _rev = rt.download(doc_id)
                gone, added = rt.changed_lines(drifted, recovered)
                evidence["recovery_diff"] = {"gone": gone, "added": added}
                assert gone == [TARGET_LINE] and added == [EDITED_LINE], (
                    evidence["recovery_diff"])
            finally:
                evidence["children_removed"] = rt.empty_document(write_client, doc_id)
    finally:
        report = docx_ledger.close_out(write_client, ledger)
        evidence["close_out"] = report.to_dict()
        with capsys.disabled():
            print(f"\n[live_write:LD-236 arm3 STALE_DOCUMENT] {evidence}\n")

    report.raise_if_orphans()
