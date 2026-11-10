"""THE COMMENT-ANCHOR ARM, LIVE AND READ-ONLY — ``@pytest.mark.live``.

Run it explicitly (needs read creds + network + the shared comment document's URL)::

    pytest -m live

**Why this arm is read-only, and why that is the strongest arm available.** The refusal this
issue adds is decided at **plan time**, from the parsed tree, before any client exists — so
proving it live needs a document that really has an inline comment anchor, and nothing else.
Two facts settle where that document can come from:

* Lark has **no anchored-comment create** on either surface (proved across 18 candidate
  routes by the opener spike, re-confirmed by the round-2 run: the v1 route accepts the
  anchor fields and silently creates an unanchored comment). So a **self-provisioned
  disposable cannot be given** a word-level anchor, and a live *write* arm for the carry has
  no way to set up its own subject;
* the only document that carries real anchors is the **shared comment document**, which this
  issue may **read** and may never write.

So this arm reads that document and drives the plan-time half against it, with the apply
engine wired to an opener that **raises on contact** — the zero-write proof is structural
here, not a matter of trusting the refusal: if the refusal ever failed to fire, the test
errors instead of writing. The payload half (which ids land on which emitted run) is pinned
offline against the same document's **captured bytes** in
``tests/test_comment_anchor_real_payloads.py``.

Skips loudly when the URL or the read credentials are absent — never a silent pass.
"""
import os

import canary_support
import pytest

from log_reading_apply import reading_the_log
from larkdocio.auth import get_read_credentials
from larkdocio.model import StyledText
from larkdocio.read.client import Client
from larkdocio.read.config import new_config
from larkdocio.read.parser import Parser
from larkdocio.utils.url import validate_download_url
from larkdocio.write.model import AnchorById, EditRequest, RefusalReason, SubSpanEditRequest
from larkdocio.write.preview import dry_run
from larkdocio.write.apply import apply
from larkdocio.write.client import WriteClient
from larkdocio.common.transport import WriteTransport

# This arm's subject is the LOG — which entry refused, with which typed reason, having issued
# which calls — not the return-vs-raise policy (pinned in tests/test_apply_refusal_policy.py
# and proved live in tests/test_live_write_refusal_policy_gate.py). So it opts into partial
# application once, here, the same way the offline log-reading suites do.
apply = reading_the_log(apply)

pytestmark = pytest.mark.live
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

#: The shared comment document, from the environment — never hard-coded in a test.
ZOO_DOC_ENV = "LARKDOCIO_COMMENT_ZOO_DOC"


class RefuseToTalk:
    """A urlopen double that raises on ANY request — the structural zero-write proof."""

    def __init__(self):
        self.attempts = []

    def __call__(self, req, timeout=30):
        self.attempts.append(req.full_url)
        raise AssertionError(
            f"the engine attempted an API call for a pre-I/O refusal: {req.get_method()} "
            f"{req.full_url}"
        )


def _sealed_client():
    """A write client that cannot reach Lark: dummy credentials, a stub token fetcher, and
    an opener that raises. Nothing about this client can touch the shared document."""
    opener = RefuseToTalk()
    client = WriteClient(
        "no-app", "no-secret", "larksuite.com",
        transport=WriteTransport(max_writes_per_sec=3),
        urlopen=opener,
        token_fetcher=lambda *a, **k: "no-token",
    )
    return client, opener


def _walk(node):
    yield node
    for child in getattr(node, "children", ()) or ():
        yield from _walk(child)
    for cell in getattr(node, "cells", ()) or ():
        yield from _walk(cell)


def _word_level_anchors(node):
    inlines = getattr(node, "content", None)
    if not isinstance(inlines, list):
        return []
    return [i for x in inlines if isinstance(x, StyledText) and x.comment_ids
            for i in x.comment_ids]


def test_the_comment_anchor_refusal_fires_on_a_REAL_anchored_block(capsys):
    canary_support.load_env()
    url = (os.environ.get(ZOO_DOC_ENV) or "").strip()
    if not url:
        pytest.skip(f"{ZOO_DOC_ENV} is unset — the shared comment document's URL is needed")
    reason = canary_support.missing_reason()
    if reason and "LARKDOCIO_CANARY_DOC" not in reason:
        pytest.skip(reason)

    domain, doc_type, token = validate_download_url(url)
    app_id, app_secret = get_read_credentials()
    client = Client(app_id, app_secret, domain)
    if doc_type == "wiki":
        node = client.get_wiki_node_info(token)
        doc_type, token = node.obj_type, node.obj_token

    # ONE read. This is the whole network cost of this arm, and it is a read.
    docx, blocks = client.get_docx_content(token)
    tree = Parser(new_config()).parse_docx_tree(docx.document_id, blocks)

    nodes = list(_walk(tree))
    word_anchored = [(n.block_id, _word_level_anchors(n)) for n in nodes
                     if _word_level_anchors(n)]
    block_only = [n.block_id for n in nodes
                  if getattr(n, "comment_ids", None) and not _word_level_anchors(n)]
    with capsys.disabled():
        print(f"\n[comment-anchor arm] blocks={len(nodes)} "
              f"word_anchored={len(word_anchored)} block_level_only={len(block_only)}")
    assert word_anchored, (
        "the shared comment document reports no word-level anchor at all — either the "
        "document changed or the reader stopped capturing them; this arm cannot prove "
        "anything without one"
    )

    block_id, ids = word_anchored[0]
    node = next(n for n in nodes if n.block_id == block_id)

    # (1) the whole-block edit refuses, at plan time, naming the real ids.
    plan = dry_run([EditRequest(anchor=AnchorById(block_id=block_id),
                                replacement="THIS MUST NEVER BE WRITTEN")], tree)
    (entry,) = plan.entries
    assert entry.refusal.reason is RefusalReason.COMMENT_ANCHORS_PRESENT, entry.to_dict()
    for comment_id in ids:
        assert comment_id in entry.refusal.detail
    assert "sub-span" in entry.refusal.detail.lower()

    # (2) applying that plan issues NOTHING — the opener would raise on contact.
    sealed, opener = _sealed_client()
    log = apply(plan, sealed, token)
    assert opener.attempts == [], opener.attempts
    assert log.entries[0].refusal.reason is RefusalReason.COMMENT_ANCHORS_PRESENT

    # (3) the recovery the refusal names resolves on the same real block.
    span = next(x.content for x in node.content
                if isinstance(x, StyledText) and x.comment_ids).strip().split(" ")[0]
    recovery = dry_run([SubSpanEditRequest(anchor=AnchorById(block_id=block_id), span=span,
                                           replacement="X")], tree)
    assert recovery.entries[0].is_resolved, recovery.entries[0].to_dict()

    # (4) a block carrying only a BLOCK-level anchor is NOT refused (no false refusal).
    if block_only:
        proceeds = dry_run([EditRequest(anchor=AnchorById(block_id=block_only[0]),
                                        replacement="ALSO NEVER WRITTEN")], tree)
        assert proceeds.entries[0].is_resolved, proceeds.entries[0].to_dict()
        sealed2, opener2 = _sealed_client()
        # It resolves, so applying it WOULD write — which is exactly why it is not applied
        # here. The plan entry is the assertion; the sealed client is never used.
        assert opener2.attempts == [] and sealed2 is not None
    else:
        with capsys.disabled():
            print("[comment-anchor arm] no block-level-only anchor live — arm (4) "
                  "unavailable on this document (offline tests cover it)")
