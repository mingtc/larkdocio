"""⛳ **THE ROUND-TRIP GATE, arm 5 — ESCAPE IDENTITY on an untouched line** (LD-454 AC4).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it with the whole ring::

    pytest -m live_write

**What this arm proves.** The projection escapes literal text (``--`` → ``\\-\\-``), and a
fenced code block's body is the one place the authoring dialect will **not** decode that
again on the way back — a backslash inside a fence is a backslash to CommonMark itself. So
before LD-454 a caller who edited **one** line of a runbook's code block wrote every *other*
line back to Lark in its escaped form, as authored intent, and the plan preview did not read
as a warning. This arm seeds a two-line code block, edits **one** line through the shipped
chain, reads the document back, and asserts the untouched line is **byte-identical** — with
no backslash anywhere in the re-read Markdown or in the raw block payload.

**And it carries its own teeth.** A gate that has never been shown failing on the defect it
guards is not known to detect it, so the second leg **re-creates the pre-fix compile in
place** — the same plan, composed and shipped without the verbatim decode — applies it to
the same disposable, and asserts the corruption **really appears** on the untouched line.
Then the shipped chain repairs it and the repair is verified. Both halves' evidence is
printed.

**Target policy (the round-trip-editing spec § gate 3).** The document is one this arm **creates itself** with the
WRITE app (which owns what it creates, so the editor-collaborator grant is automatic),
emptied and trashed in a ``finally``, its id ledgered by :mod:`docx_ledger` and
**independently re-queried** at close. Never the read canary, never the block-zoo doc, never
a real document.
"""
import time

import pytest

import canary_support
import docx_ledger
import roundtrip_gate as rt
from larkdocio.common import get_write_credentials
# The reader's OWN escaper — the repair leg writes its replacement in the projection's
# domain, and a hand-spelled "\\-\\-" would only prove this file agrees with itself.
from larkdocio.model.renderer import _escape_literals
from larkdocio.write import apply, compose, dry_run
from larkdocio.write.client import WriteClient
from larkdocio.write.model import AnchorById, EditRequest
from larkdocio.write.reconcile import ReconciliationState

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

#: The measured shape from dogfood round 4 (run D2-opus-high) — a shell line carrying ``--``.
UNTOUCHED_LINE = f"deploy rollback --service {rt.SUFFIX}"
TARGET_LINE = f"echo done {rt.SUFFIX}"
EDITED_LINE = f"echo finished {rt.SUFFIX}"
#: What the projection escapes it to, and therefore what must never reach the document.
CORRUPTED_LINE = f"deploy rollback \\-\\-service {rt.SUFFIX}"


def _code_fence(*lines):
    return "```bash\n" + "\n".join(lines) + "\n```"


def test_an_untouched_code_line_survives_the_round_trip_byte_identical(capsys, tmp_path):
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
            title=f"larkdocio-LD-454-escape-identity {int(time.time())}",
        ) as doc:
            evidence["doc_id"] = doc.document_id
            try:
                rt.seed_paragraphs(write_client, doc.document_id, [rt.ANCHOR_LINE])
                rt.seed_markdown(write_client, doc.document_id,
                                 _code_fence(UNTOUCHED_LINE, TARGET_LINE))

                baseline, root, revision, projection = rt.project(doc.document_id)
                evidence["projection_escaped_the_untouched_line"] = (
                    CORRUPTED_LINE in projection.markdown)
                assert CORRUPTED_LINE in projection.markdown, (
                    "the projection did not escape the untouched line, so this arm would "
                    "prove nothing about decoding it again")
                assert UNTOUCHED_LINE in baseline, baseline

                # THE EDIT: one line of the fence, in the projection the caller was handed.
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
                    "one edited code block is exactly one change")
                evidence["replacement"] = [
                    r.replacement for r in result["requests"]
                    if isinstance(r, EditRequest)]
                assert evidence["replacement"] == [
                    f"{UNTOUCHED_LINE}\n{EDITED_LINE}"], (
                    "the compiled replacement carries the projection's escaping into a line "
                    "the caller never edited")

                # THE READ-BACK. The untouched line, byte for byte, off the real document.
                after, _root, _rev = rt.download(doc.document_id)
                gone, added = rt.changed_lines(baseline, after)
                evidence["diff"] = {"gone": gone, "added": added}
                assert gone == [TARGET_LINE], gone
                assert added == [EDITED_LINE], added
                assert UNTOUCHED_LINE in after, after
                assert CORRUPTED_LINE not in after, (
                    "the untouched line came back escaped — the corruption LD-454 fixes")
                payload = rt.raw_block_payload(doc.document_id)
                evidence["backslash_in_raw_payload"] = "\\\\" in payload
                assert CORRUPTED_LINE not in payload, (
                    "the stored block text carries the escape even though the reader's "
                    "Markdown does not")

                # ------------------------------------------------------------- #
                # THE TEETH: the pre-fix compile, re-created in place.           #
                # ------------------------------------------------------------- #
                _md2, root2, revision2, projection2 = rt.project(doc.document_id)
                entry = next(e for e in rt.reconcile_only(
                    projection2,
                    projection2.markdown.replace(EDITED_LINE, TARGET_LINE),
                ).changes if e.state is ReconciliationState.EDITED)
                # Exactly what the compiler did before the fix: compose the edited
                # Markdown and ship the composed body WITHOUT decoding the verbatim text.
                undecoded = "\n\n".join(item.text for item in compose(entry.after_markdown))
                evidence["forced_defect_replacement"] = undecoded
                assert "\\-\\-" in undecoded, (
                    "the forced defect is not a defect — the control proves nothing")
                defect_plan = dry_run(
                    [EditRequest(anchor=AnchorById(block_id=entry.block_id),
                                 replacement=undecoded)],
                    root2, document_revision_id=revision2,
                )
                assert not defect_plan.refusals, [r.to_dict() for r in defect_plan.refusals]
                apply(defect_plan, write_client, document_id=doc.document_id)

                corrupted, root3, revision3, projection3 = rt.project(doc.document_id)
                evidence["defect_reproduced"] = CORRUPTED_LINE in corrupted
                assert CORRUPTED_LINE in corrupted, (
                    "the pre-fix compile did NOT corrupt the untouched line, so this gate "
                    "is not known to be able to fail on the defect it guards")

                # AND THE REPAIR, through the shipped chain, verified. The replacement body
                # is written in the projection's OWN domain — structure raw, literal text
                # escaped by the reader's own escaper — which is what an editor holds.
                _marker, old_body = rt.segment_of(projection3, entry.block_id)
                clean = (
                    "```bash\n"
                    + _escape_literals(UNTOUCHED_LINE) + "\n"
                    + _escape_literals(TARGET_LINE) + "\n```\n\n"
                )
                repaired = projection3.markdown.replace(old_body, clean)
                assert repaired != projection3.markdown
                repair = rt.apply_edited_projection(
                    write_client, doc.document_id,
                    root=root3, revision=revision3, projection=projection3,
                    edited_markdown=repaired,
                )
                assert repair["plan"].ok, repair["plan"].to_dict()
                final, _root, _rev = rt.download(doc.document_id)
                evidence["repaired"] = CORRUPTED_LINE not in final and UNTOUCHED_LINE in final
                assert CORRUPTED_LINE not in final, final
                assert UNTOUCHED_LINE in final, final
            finally:
                evidence["children_removed"] = rt.empty_document(
                    write_client, doc.document_id)
    finally:
        report = docx_ledger.close_out(write_client, ledger)
        evidence["close_out"] = report.to_dict()
        with capsys.disabled():
            print(f"\n[live_write:LD-454 arm5 ESCAPE-IDENTITY] {evidence}\n")

    report.raise_if_orphans()
