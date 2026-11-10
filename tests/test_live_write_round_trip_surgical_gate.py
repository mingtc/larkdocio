"""⛳ **THE ROUND-TRIP GATE, arm 1 of 4 — the SURGICAL round trip** (LD-236).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it with the whole ring::

    pytest -m live_write

**What this arm proves.** Download → **project** the document to Markdown carrying one
identity marker per block → edit the projection the way an agent would (rewrite one block's
text, touch nothing else) → **reconcile** → compile → apply → **re-download and diff**: only
the target region changed and every other line is byte-identical. Then the same chain in
reverse restores the document to a **byte-identical baseline**, which is the claim a
"surgical" edit actually makes — not merely that the intended line changed, but that the
round trip is reversible without residue.

Everything upstream of this is provable offline against fixtures. What only a real document
can answer is whether the block ids the reader hands back really address the blocks Lark
patches, and whether a patched paragraph re-reads as the same Markdown shape it had before.

**Target policy (the round-trip-editing spec § gate 3).** The document is one this arm **creates itself** with the
WRITE app (which owns what it creates, so the editor-collaborator grant is automatic), emptied
and trashed in a ``finally``, its id ledgered by :mod:`docx_ledger` and **independently
re-queried** at close. Never the read canary, never the block-zoo doc, never a real document.
"""
import time

import pytest

import canary_support
import docx_ledger
import roundtrip_gate as rt
from larkdocio.common import get_write_credentials
from larkdocio.write.client import WriteClient
from larkdocio.write.reconcile import ReconciliationState

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

BEFORE_LINE = f"context above the edit, untouched :: {rt.SUFFIX}"
TARGET_LINE = f"the target region before the edit :: {rt.SUFFIX}"
AFTER_LINE = f"context below the edit, untouched :: {rt.SUFFIX}"
EDITED_LINE = f"the target region AFTER the edit :: {rt.SUFFIX}"


def test_the_round_trip_is_surgical_and_restores_to_a_byte_identical_baseline(capsys, tmp_path):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    write_client = WriteClient(*get_write_credentials(), rt.DOMAIN)
    ledger = docx_ledger.Ledger(tmp_path / "ledger.json")
    evidence = {}

    try:
        with docx_ledger.disposable(
            write_client, ledger,
            title=f"larkdocio-LD-236-surgical {int(time.time())}",
        ) as doc:
            evidence["doc_id"] = doc.document_id
            try:
                rt.seed_paragraphs(write_client, doc.document_id, [
                    rt.ANCHOR_LINE, BEFORE_LINE, TARGET_LINE, AFTER_LINE,
                ])

                baseline, root, revision, projection = rt.project(doc.document_id)
                evidence["block_ids"] = list(projection.block_ids)
                assert TARGET_LINE in projection.markdown, projection.markdown

                # THE AGENT'S EDIT: one block's text, in the projection it was handed.
                edited = projection.markdown.replace(TARGET_LINE, EDITED_LINE)
                assert edited != projection.markdown

                result = rt.apply_edited_projection(
                    write_client, doc.document_id,
                    root=root, revision=revision, projection=projection,
                    edited_markdown=edited,
                )
                plan = result["plan"]
                evidence["plan"] = plan.to_dict()
                assert plan.ok, evidence["plan"]
                assert [e.state for e in plan.changes] == [ReconciliationState.EDITED], (
                    "exactly one block changed, so exactly one entry may be a change")
                assert len(result["requests"]) == 1, result["requests"]
                evidence["writes"] = list(result["writes"])
                assert result["writes"] == ["_patch_block"], (
                    "a one-block text edit is ONE patch — anything more is not surgical")
                assert [e.to_dict()["outcome"] for e in result["log"].entries] == ["applied"], (
                    [e.to_dict() for e in result["log"].entries])

                # THE DIFF. Only the target region moved; everything else byte-identical.
                after, _root, _rev = rt.download(doc.document_id)
                gone, added = rt.changed_lines(baseline, after)
                evidence["diff"] = {"gone": gone, "added": added}
                assert gone == [TARGET_LINE], gone
                assert added == [EDITED_LINE], added
                assert after.replace(EDITED_LINE, TARGET_LINE) == baseline, (
                    "the re-download differs from the baseline somewhere OTHER than the "
                    "target region — the edit was not surgical")

                # THE RESTORE. The same chain, in reverse, back to the baseline BYTES.
                _md, root2, revision2, projection2 = rt.project(doc.document_id)
                restore = rt.apply_edited_projection(
                    write_client, doc.document_id,
                    root=root2, revision=revision2, projection=projection2,
                    edited_markdown=projection2.markdown.replace(EDITED_LINE, TARGET_LINE),
                )
                assert restore["plan"].ok, restore["plan"].to_dict()
                restored, _root, _rev = rt.download(doc.document_id)
                evidence["restored_byte_identical"] = restored == baseline
                assert restored == baseline, rt.changed_lines(baseline, restored)
            finally:
                evidence["children_removed"] = rt.empty_document(
                    write_client, doc.document_id)
    finally:
        report = docx_ledger.close_out(write_client, ledger)
        evidence["close_out"] = report.to_dict()
        with capsys.disabled():
            print(f"\n[live_write:LD-236 arm1 SURGICAL] {evidence}\n")

    report.raise_if_orphans()
