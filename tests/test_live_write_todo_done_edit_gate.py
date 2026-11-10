"""⛳ **THE LD-574 GATE — the todo checkbox really moves, and only the checkbox moves.**

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network) and
refused by the consent fence unless the run names its authorizing issue::

    LARKDOCIO_LIVE_WRITE_AUTHORIZED_BY=LD-574 pytest -m live_write

**Why this arm exists rather than the citation alone.** Round 5 measured the field mask on a
throwaway document, and the shipped builder cites that measurement instead of re-deriving it
(``larkdocio.write.apply.build_todo_done_update``). A citation is why nobody guesses; it is
**not** this repo's proof that its own shipped op does what the op it named does. That proof is
a read-back, here, on a document this arm created — and the read-back is of the RAW block
payload, not of the reader's Markdown, because the properties the mask must leave alone
(``align``, ``folded``, a nested child's identity) are not all projected into Markdown at all.

**What it proves, in one chain.** Seed a nested todo tree through the plan gate → project it →
flip one parent checkbox in the projection and nothing else → reconcile → compile → dry_run →
apply → read the raw payload back and compare it, property by property, with the payload taken
before the write:

* the target's ``todo.style.done`` moved;
* the target's ``align`` and ``folded`` did not, and neither did its own text;
* the nested child's ``block_id``, text and ``done`` state did not;
* every other block's payload is byte-identical, and the whole write was **one** call.

**Target policy (the round-trip-editing spec § gate 3).** A document this arm **creates itself** with the WRITE app,
emptied and trashed in a ``finally``, its id ledgered by :mod:`docx_ledger` and independently
re-queried at close. Never the read canary, never the block-zoo doc, never a real document.
"""
import json
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

PARENT_LINE = f"the parent checkbox under test :: {rt.SUFFIX}"
CHILD_LINE = f"the nested child that must not move :: {rt.SUFFIX}"
SEED = f"- [ ] {PARENT_LINE}\n    - [ ] {CHILD_LINE}\n"


def _todo_blocks(payload):
    """``{block_id: {"text", "done", "align", "folded"}}`` for every todo in the payload.

    Read off the RAW payload the API answered with, so a property Markdown never carries
    (``align`` / ``folded``) is still compared. Keyed by block id, so a comparison is about
    the same blocks rather than about positions.
    """
    out = {}
    for block in json.loads(payload):
        todo = block.get("todo") or {}
        if not todo:
            continue
        style = todo.get("style") or {}
        out[block.get("block_id")] = {
            "text": "".join((el.get("text_run") or {}).get("content", "")
                            for el in todo.get("elements") or []),
            "done": bool(style.get("done")),
            "align": style.get("align"),
            "folded": style.get("folded"),
            "children": list(block.get("children") or []),
        }
    return out


def test_the_checkbox_moves_and_nothing_else_on_the_block_does(capsys, tmp_path):
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
            title=f"larkdocio-LD-574-todo-done {int(time.time())}",
        ) as doc:
            evidence["doc_id"] = doc.document_id
            try:
                rt.seed_paragraphs(write_client, doc.document_id, [rt.ANCHOR_LINE])
                rt.seed_markdown(write_client, doc.document_id, SEED)

                before_payload = rt.raw_block_payload(doc.document_id)
                before = _todo_blocks(before_payload)
                assert len(before) == 2, before
                target_id = next(bid for bid, b in before.items()
                                 if b["text"] == PARENT_LINE)
                child_id = next(bid for bid, b in before.items()
                                if b["text"] == CHILD_LINE)
                evidence["target_id"], evidence["child_id"] = target_id, child_id
                assert before[target_id]["done"] is False, before[target_id]

                baseline, root, revision, projection = rt.project(doc.document_id)
                target_line = f"- [ ] {PARENT_LINE}"
                assert target_line in projection.markdown, projection.markdown

                # THE EDIT: one checkbox, on its own line, and nothing else in the document.
                edited = projection.markdown.replace(target_line, f"- [x] {PARENT_LINE}")
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
                    "one checkbox flip is one changed block")
                assert len(result["requests"]) == 1, result["requests"]
                assert result["requests"][0].todo_done is True, result["requests"][0]

                # The PREVIEW discloses the bit — an approver who cannot see it is being
                # shown a text edit while the apply moves a boolean.
                evidence["preview"] = result["preview"].to_dict()
                assert [e.todo_done for e in result["preview"].entries] == [True], (
                    evidence["preview"])

                evidence["writes"] = list(result["writes"])
                assert result["writes"] == ["_patch_block"], (
                    "a pure flip is ONE patch: the text is not rewritten, which is what "
                    "keeps a styled item's runs from being flattened by a boolean change")
                log = result["log"]
                evidence["log"] = log.to_dict()
                assert [e.outcome for e in log.entries] == ["applied"], evidence["log"]
                assert [e.todo_done for e in log.entries] == [True], (
                    "the log is a receipt: before == after on a pure flip, so the entry has "
                    "to say what actually moved")

                # THE READ-BACK. This is the arm's whole point: the repo proving its own
                # shipped op rather than trusting the mask it cited.
                after_payload = rt.raw_block_payload(doc.document_id)
                after = _todo_blocks(after_payload)
                evidence["read_back"] = {"before": before, "after": after}

                assert after[target_id]["done"] is True, (
                    "the bit did NOT move on the live document — the whole defect, unfixed")
                for prop in ("text", "align", "folded", "children"):
                    assert after[target_id][prop] == before[target_id][prop], (
                        f"the flip moved {prop!r} on the target block; the field mask is "
                        f"supposed to reach `done` and nothing else")
                assert after[child_id] == before[child_id], (
                    "the nested child's id, text or state moved — the mask's blast radius "
                    "is wider than the measurement this repo shipped on")
                assert set(after) == set(before), "a block id appeared or vanished"

                # And the projection is surgical too: exactly one line differs.
                re_read, _root, _rev = rt.download(doc.document_id)
                gone, added = rt.changed_lines(baseline, re_read)
                evidence["diff"] = {"gone": gone, "added": added}
                assert gone == [target_line], gone
                assert added == [f"- [x] {PARENT_LINE}"], added

                # THE RESTORE — reversible without residue, the same as every other arm.
                _md, root2, revision2, projection2 = rt.project(doc.document_id)
                restore = rt.apply_edited_projection(
                    write_client, doc.document_id,
                    root=root2, revision=revision2, projection=projection2,
                    edited_markdown=projection2.markdown.replace(
                        f"- [x] {PARENT_LINE}", target_line),
                )
                assert restore["plan"].ok, restore["plan"].to_dict()
                assert restore["requests"][0].todo_done is False, restore["requests"][0]
                restored, _root, _rev = rt.download(doc.document_id)
                evidence["restored_byte_identical"] = restored == baseline
                assert restored == baseline, rt.changed_lines(baseline, restored)
                assert _todo_blocks(rt.raw_block_payload(doc.document_id)) == before, (
                    "the restore left the payload different from the pre-image")
            finally:
                evidence["children_removed"] = rt.empty_document(
                    write_client, doc.document_id)
    finally:
        report = docx_ledger.close_out(write_client, ledger)
        evidence["close_out"] = report.to_dict()
        with capsys.disabled():
            print(f"\n[live_write:LD-574 todo-done] {evidence}\n")

    report.raise_if_orphans()
