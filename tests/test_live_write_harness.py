"""THE W0 GATE — the self-provisioning live-write harness (LD-064).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` +
network). Run it explicitly::

    pytest -m live_write

It exercises the full write round-trip **against a doc it creates and destroys
itself** — never the read canary, never the block-zoo doc, never a real document
(AC5). Using the write app's own credentials throughout (the app owns what it
creates, so the reader can read it back under the same identity), the ring:

1. **creates its own disposable doc** (``create_document``);
2. **populates a baseline** — a few text blocks, incl. a *bold* sentinel block
   whose surviving ``**`` proves element-level style preservation through the patch;
3. **downloads it via the reader** — twice, asserting byte-identity (the
   determinism control that makes any post-edit diff attributable to the edit);
4. applies **one surgical mutation** — ``get_block`` the sentinel, rebuild its runs
   via the style-preserving ``to_write_elements``, ``_patch_block`` with
   ``update_text_elements``;
5. **re-downloads and diffs** — asserting **only the target region changed**
   (swapping the mutated token back reproduces the baseline byte-for-byte, so every
   other block — including the neighbouring styled block — is byte-identical, and
   the patched block kept its bold ``**``);
6. **tears down** so nothing persists — empties the doc's children (restore) and
   best-effort trashes the doc.

Teardown runs in a ``finally`` so a mid-round-trip failure still leaves nothing
behind. Writes ride the shared core's throttle (≤3/sec, ``99991400`` backoff).
"""
import time

import pytest

import canary_support
from larkdocio.common import get_write_credentials
from larkdocio.errors import LarkDocIOError, MissingDestinationError
from larkdocio.read.client import Client as ReadClient
from larkdocio.read.config import new_config
from larkdocio.read.parser import Parser
from larkdocio.write.client import WriteClient, text_block, to_write_elements

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

# The write app's tenant region (matches the toolkit's default OpenAPI domain).
# NOT a document URL — the harness never addresses a pre-existing doc.
DOMAIN = "larksuite.com"

# Distinctive, unique sentinel tokens the harness itself authors — so the diff
# assertion (swap AFTER→BEFORE == baseline) is exact and unambiguous.
BEFORE_TOKEN = "ALPHA-SENTINEL-9f15285c"
AFTER_TOKEN = "OMEGA-SENTINEL-9f15285c"


def _download_markdown(document_id, app_id, app_secret):
    """Download + parse the doc via the READER (same modules the CLI uses).

    Authenticated with the WRITE app's credentials — it owns the doc it created,
    so it can read it back; this keeps the whole harness under LARK_WRITE_APP_*
    only (AC5) without adding a second app as a collaborator.
    """
    client = ReadClient(app_id, app_secret, DOMAIN)
    docx, blocks = client.get_docx_content(document_id)
    parser = Parser(new_config())
    return parser.parse_docx_content(docx.document_id, blocks)


def test_write_harness_round_trips_its_own_doc(capsys):
    # Load the repo .env (local runs) — a no-op in CI where creds are injected as
    # variables. Then skip LOUDLY if we cannot run.
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    app_id, app_secret = get_write_credentials()
    wc = WriteClient(app_id, app_secret, DOMAIN)

    # 0) THE DESTINATION RULE, proved on the live client before anything is created: a
    #    create that names no destination refuses LOCALLY and sends nothing. Zero API calls,
    #    zero objects — the refusal is the whole observation.
    for spelling in (None, "", "   "):
        with pytest.raises(MissingDestinationError):
            wc.create_document(title="larkdocio-W0-must-not-exist", folder_token=spelling)

    # 1) Create the harness's OWN disposable doc, in the folder a human can see.
    dest_folder = canary_support.require_disposables_folder()
    doc = wc.create_document(title=f"larkdocio-W0-write-harness {int(time.time())}",
                             folder_token=dest_folder)
    doc_id = doc["document_id"]

    evidence = {"doc_id": doc_id}
    baseline_children = [
        text_block(
            f"larkdocio W0 write-harness sentinel :: {BEFORE_TOKEN}",
            style={"bold": True},   # bold => surviving ** proves style preservation
        ),
        text_block("styled-guard neighbour (italic, must stay byte-identical)",
                   style={"italic": True}),
        text_block("plain tail paragraph — untouched"),
    ]
    n_children = len(baseline_children)

    try:
        # 2) Populate the baseline.
        created = wc.create_children(doc_id, doc_id, baseline_children, index=0)
        sentinel_id = created["children"][0]["block_id"]

        # 3) Determinism control: two clean downloads must be byte-identical.
        md_baseline = _download_markdown(doc_id, app_id, app_secret)
        md_baseline_2 = _download_markdown(doc_id, app_id, app_secret)
        assert md_baseline == md_baseline_2, (
            "reader is non-deterministic: two downloads of the unchanged doc differ"
        )
        assert BEFORE_TOKEN in md_baseline, "baseline sentinel missing from download"

        # 4) One surgical mutation: re-validate the block, rebuild its runs with
        #    per-run style preserved, patch at the element level.
        live = wc.get_block(doc_id, sentinel_id)
        new_elements = to_write_elements(
            live["text"]["elements"],
            mutate=lambda c: c.replace(BEFORE_TOKEN, AFTER_TOKEN),
        )
        wc._patch_block(
            doc_id, sentinel_id, {"update_text_elements": {"elements": new_elements}}
        )

        # 5) Re-download and diff: ONLY the target region changed. Swapping the
        #    mutated token back must reproduce the baseline BYTE-FOR-BYTE — so every
        #    other block is byte-identical AND the patched block kept its bold `**`
        #    (a dropped style would change the rendering and break this equality).
        md_after = _download_markdown(doc_id, app_id, app_secret)
        assert md_after != md_baseline, "mutation produced no observable change"
        assert AFTER_TOKEN in md_after, "mutated token missing after patch"
        assert BEFORE_TOKEN not in md_after, "stale token survived the patch"
        assert md_after.replace(AFTER_TOKEN, BEFORE_TOKEN) == md_baseline, (
            "the edit was not surgical: something other than the target region "
            "changed (or the patched block lost its style)"
        )
        evidence["baseline_bytes"] = len(md_baseline.encode("utf-8"))
        evidence["surgical_diff"] = True

    finally:
        # 6) Teardown so NOTHING persists. Empty the doc (restore — needs only
        #    docx:document), verify the content is gone, then best-effort trash it.
        emptied = False
        deleted = None
        try:
            wc.batch_delete(doc_id, doc_id, 0, n_children)
            md_empty = _download_markdown(doc_id, app_id, app_secret)
            emptied = (BEFORE_TOKEN not in md_empty) and (AFTER_TOKEN not in md_empty)
        except LarkDocIOError as e:
            evidence["empty_error"] = str(e)
        try:
            resp = wc.delete_document(doc_id)
            deleted = resp.get("code") if isinstance(resp, dict) else "ok"
        except LarkDocIOError as e:
            deleted = f"skipped ({e})"
        evidence["emptied"] = emptied
        evidence["deleted"] = deleted

    # The teardown restore is a binding part of the gate: nothing persists.
    assert emptied, "teardown failed: sentinel content still present after restore"

    with capsys.disabled():
        print(
            "\n[live_write] "
            f"doc_id={evidence['doc_id']} "
            f"baseline_bytes={evidence.get('baseline_bytes')} "
            f"surgical_diff={evidence.get('surgical_diff')} "
            f"emptied={evidence.get('emptied')} "
            f"deleted={evidence.get('deleted')}"
        )
