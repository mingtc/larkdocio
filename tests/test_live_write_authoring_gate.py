"""⛳ **THE AUTHORING GATE** — the authoring round-trip **and** the live concurrency arm
(LD-140).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it with the whole ring::

    pytest -m live_write

**What this gate is for.** The tranche made structure authorable from Markdown (LD-134 kinds,
LD-135 tables, LD-136 ``compose``), addressable by id (LD-137 ``AnchorById``), and refused
under concurrent drift (LD-139 ``STALE_DOCUMENT``). Every one of those is proven offline
against fixtures and doubles. This is the one place all of it meets **real Lark**, and it
asserts the two claims a double structurally cannot make:

1. **the D4 round-trip, live** — a multi-block fragment (heading · paragraph · nested
   bullet/ordered/todo lists · code · quote · table, plus escaped metacharacters) composed,
   applied to a real document, and **re-downloaded through the shipped reader** comes back as
   **byte-identically the same Markdown**;
2. **the D9 concurrency arm, live** — an armed plan, then a **real** out-of-band edit from a
   **second client**, then ``apply`` → ``STALE_DOCUMENT`` with **zero writes measured**, the
   document byte-unchanged, and a **re-plan that applies** (a recoverable refusal, not a dead
   end).

**The ring itself lives in** ``tests/authoring_gate.py`` **and is shared** with
``tests/test_live_write_authoring_gate_offline.py``, which runs the *same* function against
the fake-Lark doubles on every ``pytest -q``. So this module is deliberately thin: it
provisions a real document, binds the ring to real clients, prints the evidence, and tears
everything down. A ring assertion that would fail reddens offline first; what only a live run
can find — a payload shape, a rendering difference, an API rule — it finds here.

**Allowed targets (AC5).** Every write goes to a document this gate **creates and destroys
itself** — never the read canary, never the block-zoo doc, never the maintainer scratch doc, never a
real document. Writes use ``get_write_credentials()`` only; the reader half prefers
``get_read_credentials()`` (the two-app least-privilege separation) and falls back to the
owning write app because a separate read-only app is not a collaborator on a doc this gate
just provisioned — a *read* fallback only, never the other way. Writes ride the shared
throttle (≤3/sec, ``99991400`` backoff).
"""
import time

import pytest

import authoring_gate as ag
import canary_support
from larkdocio.common import get_read_credentials, get_write_credentials
from larkdocio.errors import LarkDocIOError
from larkdocio.read.client import Client as ReadClient
from larkdocio.read.config import new_config
from larkdocio.read.parser import Parser
from larkdocio.write.client import WriteClient, text_block

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

# The write app's tenant region (the toolkit's default OpenAPI domain). NOT a document URL —
# the gate never addresses a pre-existing doc.
DOMAIN = "larksuite.com"


def _download(document_id):
    """``(markdown, tree, revision)`` through the READER — the modules the CLI uses.

    One read produces all three: ``parse_docx_content`` for the Markdown a consumer gets,
    ``parse_docx_tree`` for the node tree the writer anchors against, and the docx meta's
    ``revision_id`` — which the reader's own ``GetDocumentRequest`` leg already returns, so
    the whole-document staleness anchor (LD-139 / D9) costs **zero extra calls** on the read
    that builds the tree. That is the AC1 finding of S6, re-observed live here every run.
    """
    attempts = []
    if canary_support.read_creds_available():
        attempts.append(get_read_credentials())
    attempts.append(get_write_credentials())

    last_err = None
    for (app_id, app_secret) in attempts:
        try:
            client = ReadClient(app_id, app_secret, DOMAIN)
            docx, blocks = client.get_docx_content(document_id)
            parser = Parser(new_config())
            return (parser.parse_docx_content(docx.document_id, blocks),
                    parser.parse_docx_tree(docx.document_id, blocks),
                    docx.revision_id)
        except Exception as e:  # noqa: BLE001 — try the next identity
            last_err = e
    raise last_err


def test_the_authoring_gate_authoring_round_trip_and_live_concurrency_arm(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    write_client = WriteClient(*get_write_credentials(), DOMAIN)
    # A genuinely SECOND client path (AC3b) — its own client object, its own token fetch, its
    # own transport/throttle. The out-of-band edit has to come from somewhere other than the
    # object applying the batch, or the arm is a document editing itself.
    other_client = WriteClient(*get_write_credentials(), DOMAIN)

    dest_folder = canary_support.require_disposables_folder()
    doc = write_client.create_document(
        title=f"larkdocio-S7-authoring-gate {int(time.time())}",
        folder_token=dest_folder)
    doc_id = doc["document_id"]
    evidence = {"doc_id": doc_id}
    teardown = {"emptied": False, "deleted": None}

    try:
        # The seed: one top-level paragraph the fragment is anchored AFTER. It is also the
        # region delimiter — everything below it in the re-download is authored content.
        write_client.create_children(doc_id, doc_id, [text_block(ag.ANCHOR_LINE)], index=0)

        evidence.update(ag.run_authoring_ring(
            write_client=write_client,
            second_write_client=other_client,
            download=_download,
            document_id=doc_id,
        ))
    finally:
        # Teardown on the success AND failure paths (AC3), so nothing persists even on a
        # mid-ring failure. Idempotence is proven offline (the range comes off the LIVE root,
        # so a second call finds nothing); here it runs exactly once, then trashes the doc.
        try:
            teardown = ag.authoring_teardown(write_client, _download, doc_id)
        except LarkDocIOError as exc:
            evidence["teardown_error"] = str(exc)
        evidence.update(teardown)

    assert teardown["emptied"], "teardown failed: authored content still present after restore"

    with capsys.disabled():
        print(
            "\n[live_write:S7-THE-AUTHORING-GATE] "
            f"doc_id={evidence['doc_id']} "
            f"baseline_revision={evidence.get('baseline_revision')!r} "
            f"revision_guard={evidence.get('revision_guard')} "
            f"emptied={teardown.get('emptied')} deleted={teardown.get('deleted')}\n"
            "  --- THE FRAGMENT (composed) ---\n"
            f"{ag.FRAGMENT}"
            "  --- READ BACK (the authored region) ---\n"
            f"{evidence.get('authored_region')}"
            f"  round-trip byte-identical : {evidence.get('round_trip_equal')}\n"
            f"  full-doc diff             : +{evidence.get('added_lines_after_insert')} "
            f"lines, removed={evidence.get('removed_lines_after_insert')}\n"
            f"  created block ids         : {evidence.get('created_block_ids')}\n"
            f"  writes for the round-trip : {evidence.get('round_trip_writes')}\n"
            f"  restore (delete by id)    : {evidence.get('restore_outcomes')} → "
            f"byte-identical={evidence.get('restored_byte_identical')}\n"
            "  --- THE CONCURRENCY ARM (D9) ---\n"
            f"  out-of-band edit landed   : {evidence.get('out_of_band_landed')} "
            f"({ag.OUT_OF_BAND_LINE!r})\n"
            f"  revisions                 : {evidence.get('revisions')}\n"
            f"  refusal                   : {evidence.get('stale_document_reason')} "
            f"(log guard={evidence.get('refused_log_revision_guard')})\n"
            f"  detail                    : {evidence.get('stale_document_detail')!r}\n"
            f"  calls made by the refusal : {evidence.get('refused_calls')} "
            f"writes={evidence.get('refused_writes')}\n"
            f"  doc byte-unchanged        : "
            f"{evidence.get('byte_unchanged_by_the_refused_batch')}\n"
            f"  anchor still matched      : "
            f"{evidence.get('anchor_still_matched_at_refusal')} (so STALE_ANCHOR was blind — "
            f"the refusal is the DOCUMENT guard's)\n"
            f"  re-plan                   : {evidence.get('replan_outcome')} → round-trip "
            f"equal={evidence.get('replan_round_trip_equal')}"
        )
