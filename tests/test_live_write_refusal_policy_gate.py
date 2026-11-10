"""⛳ **THE REFUSAL-POLICY GATE** — `apply()` raises on a refused entry, and the opt-in returns
the same log over the same writes (LD-458 AC7).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it with the whole ring::

    pytest -m live_write

**Why this one is worth a live arm.** The offline suite can prove the raise fires; only a
round-trip can prove the sentence the ruling actually rests on — **"nothing about the writes
changes, only return-vs-raise"**. So the same batch, over the same seeded content, is applied
**twice on two disposables of this gate's own making**: once by default (it raises) and once
with ``allow_partial=True`` (it returns), and both documents are read back and compared. If the
raise had rolled anything back, skipped an entry, or issued a different call, the two read-backs
would differ.

**The batch's refusable entry is the measured shape** the ruling was written from: an
**ambiguous quote** — two identical paragraphs, one anchor — which refuses
``ambiguous-N-candidates`` with every candidate id named, exactly as it did in the consumer
incident where the caller discarded the log and believed the run had applied.

**Target policy (D-12).** Both documents are ones this gate **creates itself** with the WRITE
app, empties and trashes in a ``finally``, their ids ledgered by :mod:`docx_ledger` and
**independently re-queried** at close. Never the read canary, never the write scratch doc,
never a real document.
"""
import time

import pytest

import canary_support
import docx_ledger
import roundtrip_gate as rt
from larkdocio.common import get_write_credentials
from larkdocio.errors import LarkApplyRefusedError
from larkdocio.write import apply, dry_run
from larkdocio.write.client import WriteClient
from larkdocio.write.model import Anchor, EditRequest, RefusalReason

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

#: The entry that APPLIES — unique in the document, so it resolves exactly once.
UNIQUE = f"the unique line this batch edits :: {rt.SUFFIX}"
EDITED = f"the unique line this batch edited :: {rt.SUFFIX}"
#: The entry that REFUSES — seeded TWICE, so the anchor is ambiguous and the engine refuses
#: rather than picking one. This is the measured shape from the consumer incident.
AMBIGUOUS = f"the duplicated line no anchor can name :: {rt.SUFFIX}"

SEED = [rt.ANCHOR_LINE, UNIQUE, AMBIGUOUS, AMBIGUOUS]


def _batch():
    return [
        EditRequest(anchor=Anchor(quote=UNIQUE), replacement=EDITED),
        EditRequest(anchor=Anchor(quote=AMBIGUOUS), replacement="NEVER APPLIED"),
    ]


def _seed_and_plan(write_client, document_id):
    """Seed the identical body, then build the identical two-entry plan against it."""
    rt.seed_paragraphs(write_client, document_id, SEED)
    _md, root, revision, _projection = rt.project(document_id)
    plan = dry_run(_batch(), root, document_revision_id=revision)
    assert [entry.refusal is None for entry in plan.entries] == [True, False], plan.to_dict()
    assert plan.entries[1].refusal.reason is RefusalReason.AMBIGUOUS
    return plan


def _body(markdown):
    """The seeded lines only — the document's own title and the anchor paragraph are noise
    for the comparison, and the two disposables have different titles by construction."""
    return [line for line in markdown.splitlines()
            if rt.SUFFIX in line and rt.ANCHOR_LINE not in line]


def test_a_refused_entry_raises_by_default_and_the_opt_in_returns_over_the_SAME_writes(
    capsys, tmp_path
):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    write_client = WriteClient(*get_write_credentials(), rt.DOMAIN)
    ledger = docx_ledger.Ledger(tmp_path / "ledger.json")
    evidence = {}
    stamp = int(time.time())

    try:
        # ------------------------------------------------------------------ #
        # ARM A — the DEFAULT. The batch raises; the log rides the exception. #
        # ------------------------------------------------------------------ #
        with docx_ledger.disposable(
            write_client, ledger, title=f"larkdocio-LD-458-raise {stamp}",
        ) as raising:
            evidence["raise_doc_id"] = raising.document_id
            try:
                plan = _seed_and_plan(write_client, raising.document_id)
                with pytest.raises(LarkApplyRefusedError) as caught:
                    apply(plan, write_client, document_id=raising.document_id)
                error = caught.value
                evidence["raise_message"] = str(error)
                evidence["raise_refusals"] = list(error.refusals)

                assert len(error.applied) == 1 and error.applied[0].outcome == "applied"
                assert len(error.refused) == 1
                assert error.refusals[0]["reason"] == "ambiguous-N-candidates"
                assert error.refusals[0]["detail"], "a refusal with no detail is not actionable"
                assert "1 of 2 entries applied; 1 refused" in str(error)
                assert "allow_partial=True" in str(error)
                assert len(error.log) == len(plan.entries) == 2

                raised_markdown, _root, _rev = rt.download(raising.document_id)
                evidence["raise_body"] = _body(raised_markdown)
                # The applied entry LANDED and stayed landed: the raise is a report, never a
                # rollback. The refused one wrote nothing.
                assert EDITED in raised_markdown and UNIQUE not in raised_markdown
                assert raised_markdown.count(AMBIGUOUS) == 2
                assert "NEVER APPLIED" not in raised_markdown
            finally:
                evidence["raise_children_removed"] = rt.empty_document(
                    write_client, raising.document_id)

        # ------------------------------------------------------------------ #
        # ARM B — the OPT-IN. The same batch returns, over the same writes.   #
        # ------------------------------------------------------------------ #
        with docx_ledger.disposable(
            write_client, ledger, title=f"larkdocio-LD-458-allow-partial {stamp}",
        ) as returning:
            evidence["opt_in_doc_id"] = returning.document_id
            try:
                plan = _seed_and_plan(write_client, returning.document_id)
                log = apply(plan, write_client, document_id=returning.document_id,
                            allow_partial=True)
                evidence["opt_in_outcomes"] = [entry.outcome for entry in log]

                assert [entry.outcome for entry in log] == ["applied", "refused"]
                assert len(log) == 2 and list(log) == list(log.entries)
                assert len(log.applied) == 1 and len(log.refusals) == 1
                assert log.refusals[0].refusal.reason is RefusalReason.AMBIGUOUS

                returned_markdown, _root, _rev = rt.download(returning.document_id)
                evidence["opt_in_body"] = _body(returned_markdown)
                assert EDITED in returned_markdown and UNIQUE not in returned_markdown
                assert returned_markdown.count(AMBIGUOUS) == 2
                assert "NEVER APPLIED" not in returned_markdown
            finally:
                evidence["opt_in_children_removed"] = rt.empty_document(
                    write_client, returning.document_id)

        # ------------------------------------------------------------------ #
        # THE CLAIM ITSELF: the two documents came back the SAME.             #
        # ------------------------------------------------------------------ #
        assert evidence["raise_body"] == evidence["opt_in_body"], (
            "the raise changed WHICH entries applied — the ruling's one invariant is that "
            "only return-vs-raise moved")
        evidence["same_writes"] = True
    finally:
        report = docx_ledger.close_out(write_client, ledger)
        evidence["close_out"] = report.to_dict()
        with capsys.disabled():
            print(f"\n[live_write:LD-458 REFUSAL-POLICY] {evidence}\n")

    report.raise_if_orphans()
