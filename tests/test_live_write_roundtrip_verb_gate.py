"""⛳ **THE LD-492 GATE — the file-first ROUND-TRIP VERB, end to end against a real document.**

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*``, the READ pair,
``LARKDOCIO_DISPOSABLES_FOLDER`` and network). Run **this file by name**, never the bare ring::

    pytest tests/test_live_write_roundtrip_verb_gate.py

**Run the named file, and run the WHOLE file.** ``-k`` on a live gate re-runs the module's
provisioning and re-creates its disposable, which is how a budget overrun happened on
2026-08-16. There is nothing here worth selecting a subset of.

**What this arm proves, and why only a live document can.** Everything about the verb's
*ordering* is provable offline — that the preview is built before anything branches, that
``apply`` takes only the plan ``dry_run`` returned, that the read-back uses ``compose()``. What
no fixture can answer is whether the two phases, run as a caller runs them **with a file system
and a process boundary in between**, actually address the same blocks: whether the snapshot
written by phase A rehydrates to a projection whose ids are the ids Lark patches, whether the
edit made in a text editor on `document.md` reconciles, and whether the re-read composes to
what was authored. So this arm runs the verb — the shipped functions, not a re-implementation:

1. create a disposable document **in the caller-supplied disposables folder** and seed it;
2. ``roundtrip.pull`` into a temporary directory — assert the two files exist;
3. **edit ``document.md`` on disk**, the way an agent would;
4. ``roundtrip.push`` once as a **rehearsal** — assert it wrote nothing;
5. ``roundtrip.push(apply_changes=True)`` — assert the change landed, that the edit was
   **surgical** (nothing outside the target region moved), and that the verb's own read-back
   verification passed **on its own terms**;
6. delete the disposable in a ``finally`` and **re-query** it to prove it is gone.

**Target policy (D-12, binding).** The document is one this arm creates itself and trashes,
ledgered by :mod:`docx_ledger` and independently re-queried at close. **Never the read canary,
never ``LARKDOCIO_WRITE_SCRATCH_DOC``, never a real document.** It uploads nothing: this verb
has no media leg, so the permanent-Drive-media residue budget for this gate is **zero by
construction**.

**Born conforming to the caller-supplied-destination rule (LD-493).** The disposable is created
into ``LARKDOCIO_DISPOSABLES_FOLDER``, named explicitly rather than left to a default, and with
that variable unset this arm **skips loudly** naming it — it does not fall back to the
application's own space, which no human interface can browse.
"""
import time

import pytest

import canary_support
import docx_ledger
import roundtrip_gate as rt
from larkdocio import roundtrip
from larkdocio.common import get_write_credentials
from larkdocio.write.client import WriteClient
from larkdocio.write.reconcile import ReconciliationState

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing the
# statement above (the ring guards read that literal line to prove ring membership).
pytestmark = [pytestmark, pytest.mark.conformance]

BEFORE_LINE = f"context above the verb's edit, untouched :: {rt.SUFFIX}"
TARGET_LINE = f"the region the verb will edit :: {rt.SUFFIX}"
AFTER_LINE = f"context below the verb's edit, untouched :: {rt.SUFFIX}"
EDITED_LINE = f"the region AFTER the verb's edit :: {rt.SUFFIX}"


def test_the_roundtrip_verb_pulls_edits_and_pushes_one_surgical_change(capsys, tmp_path):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)
    folder_token = canary_support.require_disposables_folder()

    write_client = WriteClient(*get_write_credentials(), rt.DOMAIN)
    ledger = docx_ledger.Ledger(tmp_path / "ledger.json")
    workdir = tmp_path / "edit"
    evidence = {"disposables_folder_named": bool(folder_token)}

    try:
        with docx_ledger.disposable(
            write_client, ledger,
            title=f"larkdocio-LD-492-roundtrip {int(time.time())}",
            folder_token=folder_token,
        ) as doc:
            evidence["doc_id"] = doc.document_id
            try:
                rt.seed_paragraphs(write_client, doc.document_id, [
                    rt.ANCHOR_LINE, BEFORE_LINE, TARGET_LINE, AFTER_LINE,
                ])
                baseline, _root, _revision = rt.download(doc.document_id)

                # ── PHASE A. The shipped verb, not a re-implementation of it.
                # A tenant-host URL for the document this arm just created — the input a
                # caller pastes. `validate_download_url` maps the tenant host back to the API
                # domain, which is exactly the hop the verb has to make for real. Built by the
                # shared harness from the id, so no arm carries a document address of its own.
                url = rt.document_url(doc.document_id)
                pulled = roundtrip.pull(url, workdir)
                evidence["pull"] = pulled.to_dict()
                assert roundtrip.snapshot_path(workdir).exists(), "phase A wrote no snapshot"
                assert roundtrip.markdown_path(workdir).exists(), "phase A wrote no Markdown"
                assert pulled.document_revision_id is not None, (
                    "the read carried no revision, so the staleness guard cannot be armed — "
                    "this arm's revision_guard assertions would prove nothing")

                # ── THE CALLER'S EDIT, on the file, between the phases.
                editable = roundtrip.markdown_path(workdir)
                before_edit = editable.read_text(encoding="utf-8")
                assert TARGET_LINE in before_edit, before_edit
                editable.write_text(
                    before_edit.replace(TARGET_LINE, EDITED_LINE), encoding="utf-8")

                # ── PHASE B, REHEARSAL. The preview is built and NOTHING is written.
                with rt.measured_writes(write_client) as rehearsal_writes:
                    rehearsal = roundtrip.push(workdir)
                evidence["rehearsal_writes"] = list(rehearsal_writes)
                assert rehearsal.applied is False
                assert rehearsal.log is None and rehearsal.verification is None
                assert rehearsal.revision_guard == "active", (
                    "the snapshot carried a revision and the plan is not armed with it")
                assert rehearsal.plan.change_count == 1, rehearsal.plan.to_dict()
                unchanged, _rev = rt.download(doc.document_id)[0], None
                assert unchanged == baseline, (
                    "a rehearsal push changed the document — the preview is not a preview")

                # ── PHASE B, APPLIED.
                pushed = roundtrip.push(workdir, apply_changes=True)
                evidence["push"] = {
                    "applied": pushed.applied,
                    "revision_guard": pushed.revision_guard,
                    "verification": pushed.verification.to_dict(),
                }
                assert pushed.applied is True
                assert pushed.revision_guard == "active"
                assert [e.state for e in pushed.plan.changes] == [
                    ReconciliationState.EDITED], pushed.plan.to_dict()
                assert [e.to_dict()["outcome"] for e in pushed.log.entries] == ["applied"], (
                    [e.to_dict() for e in pushed.log.entries])

                # ── THE VERB'S OWN READ-BACK, on its own terms.
                assert pushed.verification.ok, pushed.verification.to_dict()
                assert pushed.verification.verified, (
                    "the verification passed while verifying nothing — an empty verified list "
                    "is not a clean read-back")
                assert pushed.verification.mismatched == ()

                # ── THE SURGICAL DIFF, measured independently of the verb.
                after, _root, _rev = rt.download(doc.document_id)
                gone, added = rt.changed_lines(baseline, after)
                evidence["diff"] = {"gone": gone, "added": added}
                assert gone == [TARGET_LINE], gone
                assert added == [EDITED_LINE], added
                assert after.replace(EDITED_LINE, TARGET_LINE) == baseline, (
                    "the re-download differs from the baseline somewhere OTHER than the target "
                    "region — the verb's edit was not surgical")
            finally:
                evidence["children_removed"] = rt.empty_document(
                    write_client, doc.document_id)
    finally:
        report = docx_ledger.close_out(write_client, ledger)
        evidence["close_out"] = report.to_dict()
        with capsys.disabled():
            print(f"\n[live_write:LD-492 ROUNDTRIP VERB] {evidence}\n")

    report.raise_if_orphans()
