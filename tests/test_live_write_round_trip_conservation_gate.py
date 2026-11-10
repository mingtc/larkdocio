"""⛳ **THE ROUND-TRIP GATE, arm 2 of 4 — CONSERVATION of an omitted opaque block**
(LD-236, WIDENED by human maintainer ruling 2026-08-03).

``@pytest.mark.live_write``, deselected by default. Run it with the whole ring::

    pytest -m live_write

**The catastrophe this arm exists to prevent.** The projection can only carry what the
Markdown dialect can express. A block it cannot express travels as an opaque marker, and an
editing agent that drops that marker must NOT cause the block to be destroyed — nor, and this
is the half that was missed, to be **re-created beside itself**.

**Why the subject is a TABLE and not an image.** The mint said "an image is the natural case".
It is not, and LD-238 (Critical) is the proof: an opaque block whose **marker** is dropped but
whose **content survives** was reported ``conserved-opaque`` *and* re-created by a planned
insert — a document-duplicating plan. An image arm **cannot see that**, because an image
refuses ``not-in-dialect`` later, at compile time, for unrelated reasons: the arm would have
gone green over the defect. A **table** is opaque to the projection (``opaque=table``) *and*
creatable by ``compose()``, so both omission shapes reach the reconciler and both are decided
on their merits.

**Two omission shapes, both required.**

* **(a) marker AND content omitted** — the editor deleted the whole region it could not
  represent. The block is **conserved**: not edited, not deleted, not re-created, and the live
  document still carries it byte-identically afterwards.
* **(b) marker omitted, content kept** — LD-238's shape. The plan **refuses the whole batch**
  (``conserved-block-re-created``) with **zero writes**, so the live document is byte-unchanged.

This arm is the live counterpart of LD-235 AC9. A failure here is a bug in a predecessor, not
a licence to change the engine.

**Target policy (the round-trip-editing spec § gate 3).** A document this arm creates itself, empties and trashes in
a ``finally``, ledgered and independently re-queried at close. Never the canary, never the
zoo, never a real document.
"""
import time

import pytest

import canary_support
import docx_ledger
import roundtrip_gate as rt
from larkdocio.common import get_write_credentials
from larkdocio.write.client import WriteClient
from larkdocio.write.model import RefusalReason
from larkdocio.write.reconcile import ReconciliationState

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

TAIL_LINE = f"a paragraph after the opaque block :: {rt.SUFFIX}"
TAIL_EDITED = f"a paragraph after the opaque block, rewritten :: {rt.SUFFIX}"
TABLE_MD = "| metric | value |\n|---|---|\n| onhold | 12 |\n"


def test_an_opaque_block_omitted_from_the_edited_projection_survives_byte_identically(
    capsys, tmp_path,
):
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
            title=f"larkdocio-LD-236-conservation {int(time.time())}",
        ) as doc:
            doc_id = doc.document_id
            evidence["doc_id"] = doc_id
            try:
                rt.seed_paragraphs(write_client, doc_id, [rt.ANCHOR_LINE, TAIL_LINE])
                rt.seed_markdown(write_client, doc_id, TABLE_MD)

                baseline, root, revision, projection = rt.project(doc_id)
                opaque = rt.opaque_body_ids(projection, doc_id)
                assert len(opaque) == 1, (
                    f"the fixture must carry exactly ONE opaque body block; got {opaque}")
                table_id = opaque[0]
                marker_line, body = rt.segment_of(projection, table_id)
                evidence["opaque"] = {"block_id": table_id, "marker": marker_line.strip(),
                                      "body": body}
                assert "opaque=table" in marker_line, marker_line
                assert "| metric | value |" in body, body

                # ---------- SHAPE (a): marker AND content omitted ----------
                edited_a = projection.markdown.replace(marker_line + body, "")
                edited_a = edited_a.replace(TAIL_LINE, TAIL_EDITED)
                assert marker_line not in edited_a and "| metric | value |" not in edited_a

                result_a = rt.apply_edited_projection(
                    write_client, doc_id, root=root, revision=revision,
                    projection=projection, edited_markdown=edited_a,
                )
                plan_a = result_a["plan"]
                evidence["shape_a_plan"] = plan_a.to_dict()
                assert plan_a.ok, evidence["shape_a_plan"]
                states = {e.block_id: e.state for e in plan_a.entries}
                assert states[table_id] is ReconciliationState.CONSERVED_OPAQUE, states
                assert ReconciliationState.INSERTED not in set(states.values()), (
                    "an omitted opaque block must NOT be re-created by a planned insert — "
                    "that is the LD-238 document-duplicating defect")
                assert table_id not in plan_a.touched_block_ids, plan_a.touched_block_ids
                assert result_a["writes"] == ["_patch_block"], result_a["writes"]

                after_a, _root, _rev = rt.download(doc_id)
                gone, added = rt.changed_lines(baseline, after_a)
                evidence["shape_a_diff"] = {"gone": gone, "added": added}
                assert gone == [TAIL_LINE] and added == [TAIL_EDITED], evidence["shape_a_diff"]
                assert after_a.replace(TAIL_EDITED, TAIL_LINE) == baseline, (
                    "the conserved table did not come back byte-identical")

                # ---------- SHAPE (b): marker omitted, CONTENT KEPT (LD-238) ----------
                before_b, root_b, revision_b, projection_b = rt.project(doc_id)
                table_id_b = rt.opaque_body_ids(projection_b, doc_id)[0]
                marker_b, body_b = rt.segment_of(projection_b, table_id_b)
                edited_b = projection_b.markdown.replace(marker_b, "")   # content stays
                assert body_b.strip() and body_b in edited_b

                result_b = rt.apply_edited_projection(
                    write_client, doc_id, root=root_b, revision=revision_b,
                    projection=projection_b, edited_markdown=edited_b,
                )
                plan_b = result_b["plan"]
                evidence["shape_b_refusals"] = [r.to_dict() for r in plan_b.refusals]
                assert not plan_b.ok, evidence["shape_b_refusals"]
                assert RefusalReason.CONSERVED_BLOCK_RE_CREATED in {
                    r.reason for r in plan_b.refusals}, evidence["shape_b_refusals"]
                assert plan_b.change_count == 0 and plan_b.entries == ()
                assert result_b["requests"] is None and result_b["writes"] == [], (
                    "a refusal compiles nothing, so the zero-write claim is structural")

                after_b, _root, _rev = rt.download(doc_id)
                evidence["shape_b_byte_unchanged"] = after_b == before_b
                assert after_b == before_b, rt.changed_lines(before_b, after_b)
            finally:
                evidence["children_removed"] = rt.empty_document(write_client, doc_id)
    finally:
        report = docx_ledger.close_out(write_client, ledger)
        evidence["close_out"] = report.to_dict()
        with capsys.disabled():
            print(f"\n[live_write:LD-236 arm2 CONSERVATION] {evidence}\n")

    report.raise_if_orphans()
