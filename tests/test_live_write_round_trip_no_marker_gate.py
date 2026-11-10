"""⛳ **THE ROUND-TRIP GATE, arm 4 of 4 — NO MARKER REACHES LARK** (LD-236).

``@pytest.mark.live_write``, deselected by default. Run it with the whole ring::

    pytest -m live_write

**The invariant with no natural barrier.** LD-197 leg 3 measured it live: Lark stores
marker-shaped text **verbatim**. Nothing about the platform keeps an identity marker out of a
document — the only barrier is our own marker-set-aware strip on the way in. So after a
reconciliation this arm re-reads the **whole** document and scans it in **both**
representations for markers of the ids the projection emitted:

* the **raw block payload** the API answered with, serialized whole (a marker could survive in
  stored text the Markdown never renders), and
* the **reader's re-rendered Markdown** (what a consumer actually sees).

Zero occurrences in both, or the arm fails.

**The adversarial control** — a block whose *legitimate* text is marker-shaped — must survive
the round trip **unchanged**. It is what makes the zero result meaningful rather than vacuous:
marker-shaped text demonstrably CAN live in this document, so "no emitted marker is here" is a
statement about the strip, not about the platform being unable to store one.

**How the control is scoped, and why (LD-239).** The control carries its marker-shaped text
**mid-line** and names an id this document's projection never emitted, and the control block
is **not** one of the blocks the reconciliation edits. A mid-line, non-emitted marker is the
shape a real consumer's prose about markers has, and keeping the control non-emitted is what
lets it assert survival rather than absence.

**The mid-line refusal leg (LD-239 AC10).** The same position with the membership flipped —
a **mid-line marker for a block this projection DID emit** — is the shape that used to ride a
compiled ``EditRequest`` body while the guard was line-anchored. It is now a leg of this arm:
the edit is refused, **zero** writes are measured, and the document is **byte-identical**
before and after, so the claim "nothing reached Lark" is read off the live document rather
than off the compiler that refused.

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
# ``_escape_literals`` is the reader's OWN escaper: the LD-239 leg hands back the prose the
# way an editor would, escaped, because that is the form that decodes into a real marker.
from larkdocio.model.renderer import _escape_literals, block_id_marker
from larkdocio.write.client import WriteClient
from larkdocio.write.model import RefusedError

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

#: The id the adversarial control names — never emitted by any projection of this document
#: (it is not a Lark block id at all), so the reconciler reads the line as content, which is
#: what it is.
CONTROL_ID = "LD236LEAKED"
CONTROL_LINE = (
    f"Adversarial control, legitimate prose about markers: {block_id_marker(CONTROL_ID)} "
    f"must survive unchanged :: {rt.SUFFIX}"
)
TARGET_LINE = f"the block the reconciliation edits :: {rt.SUFFIX}"
EDITED_LINE = f"the block the reconciliation edits, rewritten :: {rt.SUFFIX}"


def test_no_projection_marker_reaches_lark_in_either_representation(capsys, tmp_path):
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
            title=f"larkdocio-LD-236-no-marker {int(time.time())}",
        ) as doc:
            doc_id = doc.document_id
            evidence["doc_id"] = doc_id
            try:
                rt.seed_paragraphs(write_client, doc_id, [
                    rt.ANCHOR_LINE, TARGET_LINE, CONTROL_LINE,
                ])

                _md, root, revision, projection = rt.project(doc_id)
                emitted = list(projection.block_ids)
                evidence["emitted_ids"] = emitted
                assert CONTROL_ID not in emitted, (
                    "the control must name an id the projection never emitted")

                # ── LD-239 AC10: THE MID-LINE LEG. The same position as the control with
                # membership flipped — a marker for a block this projection DID emit,
                # mid-sentence — is refused, and the live document proves nothing reached
                # Lark: zero writes measured, byte-identical Markdown across the attempt.
                before, _root_before, _rev_before = rt.download(doc_id)
                leaking = (
                    f"prose that carries {block_id_marker(emitted[-1])} mid-line "
                    f":: {rt.SUFFIX}"
                )
                with rt.measured_writes(write_client) as attempted:
                    with pytest.raises(RefusedError) as excinfo:
                        rt.apply_edited_projection(
                            write_client, doc_id, root=root, revision=revision,
                            projection=projection,
                            edited_markdown=projection.markdown.replace(
                                TARGET_LINE, _escape_literals(leaking)),
                        )
                after, _root_after, _rev_after = rt.download(doc_id)
                evidence["midline_refusal"] = excinfo.value.refusal.to_dict()["reason"]
                evidence["midline_writes"] = attempted
                evidence["midline_document_unchanged"] = after == before
                assert attempted == [], attempted
                assert after == before, rt.changed_lines(before, after)

                result = rt.apply_edited_projection(
                    write_client, doc_id, root=root, revision=revision,
                    projection=projection,
                    edited_markdown=projection.markdown.replace(TARGET_LINE, EDITED_LINE),
                )
                assert result["plan"].ok, result["plan"].to_dict()
                # Pre-flight: nothing the compiler produced carries a marker at all.
                compiled = repr(result["requests"])
                evidence["compiled_marker_hits"] = rt.marker_hits(compiled)
                assert evidence["compiled_marker_hits"] == [], compiled

                # THE SCAN — the WHOLE re-read document, in BOTH representations.
                markdown, _root, _rev = rt.download(doc_id)
                raw = rt.raw_block_payload(doc_id)
                md_hits = rt.marker_hits(markdown)
                raw_hits = rt.marker_hits(raw)
                evidence["markdown_marker_ids"] = sorted({b for _w, b in md_hits})
                evidence["raw_payload_marker_ids"] = sorted({b for _w, b in raw_hits})

                for block_id in emitted:
                    marker = block_id_marker(block_id)
                    assert marker not in markdown, (
                        f"an emitted marker reached the reader's Markdown: {marker}")
                    assert marker not in raw, (
                        f"an emitted marker reached the stored payload: {marker}")

                assert {b for _w, b in md_hits} == {CONTROL_ID}, evidence["markdown_marker_ids"]
                assert {b for _w, b in raw_hits} == {CONTROL_ID}, (
                    evidence["raw_payload_marker_ids"])

                # THE CONTROL SURVIVED UNCHANGED — which is what makes the zero meaningful.
                evidence["control_survived"] = CONTROL_LINE in markdown
                assert CONTROL_LINE in markdown, (
                    "the adversarial control did not survive the round trip verbatim")
                assert EDITED_LINE in markdown and TARGET_LINE not in markdown, (
                    "the reconciliation itself did not land")
            finally:
                evidence["children_removed"] = rt.empty_document(write_client, doc_id)
    finally:
        report = docx_ledger.close_out(write_client, ledger)
        evidence["close_out"] = report.to_dict()
        with capsys.disabled():
            print(f"\n[live_write:LD-236 arm4 NO-MARKER] {evidence}\n")

    report.raise_if_orphans()
