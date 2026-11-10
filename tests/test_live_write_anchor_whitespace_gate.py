"""⛳ **THE ANCHOR SOFT-RETURN GATE** — the whitespace near-miss, and the line-splice garble
(LD-455 AC5).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it with the whole ring::

    pytest -m live_write

**Why this one cannot be proved offline.** The whole defect rests on an API fact: that Lark
**stores a literal newline inside a single text run** and hands it back inside one block, so
the reader's Markdown shows it as an ordinary line wrap. A fixture asserting that is a fixture
asserting its own author's belief. This arm authors the soft return **on the wire**, reads the
document back, and proves the premise before it claims anything about the two behaviours built
on it.

**Arm A — the refusal names the near-miss.** A whole sentence copied off the wrapped paragraph
differs from what is stored by one invisible character. ``dry_run`` refuses ``not-found`` — and
the ``detail`` now names the block, quotes its stored spelling and offers a fragment that does
match. **Zero writes, measured at the client boundary**, not inferred.

**Arm B — the garble, forced and then repaired.** The teeth come first, because a gate never
shown failing on the defect it guards is not known to detect it: the arm re-creates the shipped
recipe's **old line-splice idiom** in place, applies it through the shipped chain, and asserts
the document really comes back with the sentence's ending written twice while ``plan.ok`` was
``True``. Then it repairs the same block through ``replace_block_markdown`` — the block-safe
splice the recipe now teaches — and reads back the exact text that was asked for.

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
from larkdocio.model.projection import replace_block_markdown
from larkdocio.model.renderer import unescape_literals
from larkdocio.write.resolve import longest_matching_fragment
from larkdocio.write import apply, dry_run
from larkdocio.write.client import WriteClient
from larkdocio.write.model import Anchor, AnchorById, EditRequest
from larkdocio.write.reconcile import ReconciliationState

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

#: The measured shape from dogfood round 4 — a soft return landing mid-sentence, exactly
#: where terminal word-wrap would have put one.
HEAD = f"Revenue grew 12.4% in {rt.SUFFIX}"
TAIL = "Q3. The board asked for a breakdown by region."
SOFT_RETURN_TEXT = f"{HEAD}\n{TAIL}"
#: What a consumer copies off the wrapped paragraph: the same words, one space instead of the
#: newline. One invisible character away from the stored text, and it refuses.
COPIED_QUOTE = f"{HEAD} {TAIL}"
CORRECT_EDIT = f"Revenue grew 15.0% in {rt.SUFFIX} Q3. The board asked for a breakdown by region."


def test_a_soft_return_paragraph_diagnoses_its_near_miss_and_survives_a_block_safe_edit(
    capsys, tmp_path
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
            title=f"larkdocio-LD-455-anchor-whitespace {int(time.time())}",
        ) as doc:
            evidence["doc_id"] = doc.document_id
            try:
                # ----------------------------------------------------------- #
                # THE PREMISE, on the wire: author a soft return and read it   #
                # back inside ONE block.                                       #
                # ----------------------------------------------------------- #
                rt.seed_paragraphs(write_client, doc.document_id, [rt.ANCHOR_LINE, HEAD])
                _md, root, revision, _proj = rt.project(doc.document_id)
                target = next(
                    node for node in _walk(root)
                    if node.block_id and HEAD in _plain(node) and node.block_id != root.block_id
                )
                seed = dry_run(
                    [EditRequest(anchor=AnchorById(block_id=target.block_id),
                                 replacement=SOFT_RETURN_TEXT)],
                    root, document_revision_id=revision,
                )
                assert not seed.refusals, [r.to_dict() for r in seed.refusals]
                apply(seed, write_client, document_id=doc.document_id)

                baseline, root, revision, projection = rt.project(doc.document_id)
                block = next(
                    node for node in _walk(root)
                    if node.block_id == target.block_id
                )
                stored = _plain(block)
                evidence["stored_text"] = repr(stored)
                assert stored == SOFT_RETURN_TEXT, (
                    "Lark did not store the newline inside one text run, so this arm's "
                    "premise does not hold on this tenant and it would prove nothing")
                body = _segment_body(projection, block.block_id)
                evidence["projected_lines"] = len(body.splitlines())
                assert len(body.splitlines()) == 2, body
                assert unescape_literals(body).replace("\n", " ") == COPIED_QUOTE

                # ----------------------------------------------------------- #
                # ARM A — the near-miss is NAMED, and nothing is written.      #
                # ----------------------------------------------------------- #
                with rt.measured_writes(write_client) as writes:
                    plan = dry_run(
                        [EditRequest(anchor=Anchor(quote=COPIED_QUOTE),
                                     replacement="never applied")],
                        root, document_revision_id=revision,
                    )
                assert writes == [], writes
                refusal = plan.entries[0].refusal
                assert refusal is not None, plan.to_dict()
                evidence["arm_a_detail"] = refusal.detail
                assert f"block {block.block_id!r} differs only in whitespace" in refusal.detail
                assert repr(stored) in refusal.detail
                assert "re-read the document and copy the quote verbatim" not in refusal.detail
                # ...and the fragment the refusal offers really does resolve. WHICH fragment
                # that is comes from the shipped function, never from this file's guess — a
                # hand-picked one would be testing this file's own belief about the advice.
                fragment = longest_matching_fragment(COPIED_QUOTE, stored)
                assert repr(fragment) in refusal.detail
                probe = dry_run([EditRequest(anchor=Anchor(quote=fragment),
                                             replacement="never applied")], root)
                assert probe.entries[0].refusal is None, probe.to_dict()

                # ----------------------------------------------------------- #
                # ARM B, THE TEETH — the OLD line-splice idiom, in place.      #
                # ----------------------------------------------------------- #
                lines = projection.markdown.splitlines(keepends=True)
                i = next(n for n, line in enumerate(lines)
                         if unescape_literals(line).startswith("Revenue grew"))
                lines[i] = f"Revenue grew 15.0% in {rt.SUFFIX} Q3.\n"
                spliced = rt.apply_edited_projection(
                    write_client, doc.document_id,
                    root=root, revision=revision, projection=projection,
                    edited_markdown="".join(lines),
                )
                evidence["forced_defect_plan_ok"] = spliced["plan"].ok
                assert spliced["plan"].ok, [r.to_dict() for r in spliced["plan"].refusals]
                assert [e.state for e in spliced["plan"].changes] == [
                    ReconciliationState.EDITED]

                garbled, root2, revision2, projection2 = rt.project(doc.document_id)
                stored2 = _plain(next(node for node in _walk(root2)
                                      if node.block_id == block.block_id))
                evidence["garbled_text"] = repr(stored2)
                assert stored2.count("Q3.") == 2, (
                    "the old line-splice did NOT garble the sentence, so this gate is not "
                    "known to be able to fail on the defect it guards")
                assert "Q3.\nQ3." in stored2, stored2

                # ----------------------------------------------------------- #
                # ARM B, THE FIX — the block-safe splice, read back verbatim.  #
                # ----------------------------------------------------------- #
                repaired = rt.apply_edited_projection(
                    write_client, doc.document_id,
                    root=root2, revision=revision2, projection=projection2,
                    edited_markdown=replace_block_markdown(
                        projection2, block.block_id, CORRECT_EDIT),
                )
                assert repaired["plan"].ok, [r.to_dict()
                                             for r in repaired["plan"].refusals]
                final, root3, _rev3 = rt.download(doc.document_id)
                stored3 = _plain(next(node for node in _walk(root3)
                                      if node.block_id == block.block_id))
                evidence["repaired_text"] = repr(stored3)
                assert stored3 == CORRECT_EDIT, stored3
                assert stored3.count("Q3.") == 1, stored3
                assert CORRECT_EDIT in final, final
                evidence["baseline_had_the_soft_return"] = SOFT_RETURN_TEXT.replace(
                    "\n", " ") in baseline.replace("\n", " ")
            finally:
                evidence["children_removed"] = rt.empty_document(
                    write_client, doc.document_id)
    finally:
        report = docx_ledger.close_out(write_client, ledger)
        evidence["close_out"] = report.to_dict()
        with capsys.disabled():
            print(f"\n[live_write:LD-455 ANCHOR-SOFT-RETURN] {evidence}\n")

    report.raise_if_orphans()


def _walk(root):
    from larkdocio.model import walk

    return walk(root)


def _plain(node):
    from larkdocio.write.resolve import block_plain_text

    return block_plain_text(node)


def _segment_body(projection, block_id):
    from larkdocio.model.projection import block_markdown

    return block_markdown(projection, block_id)
