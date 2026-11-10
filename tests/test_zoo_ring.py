"""Block-zoo live ring (LD-044) — ``@pytest.mark.zoo``, deselected
by default.

The **advisory** sibling of the live read-canary (LD-003). It runs only under
``pytest -m zoo`` (needs real read creds + network) and drives the reader
through its real client + parser against the disposable block-zoo doc named by
``LARKDOCIO_BLOCKZOO_DOC`` — the same shape as a ``--dump`` harvest pass, so a
future zoo revision re-harvests fixtures the same way.

**Advisory, never binding.** Nothing in ``verify.sh``/CI/QA blocks on the zoo
doc being reachable: when the URL or the read creds are missing this test
**skips loudly** (a clear message naming the missing var) — it never fails and
never silently passes. This mirrors the canary's skip-loudly-never-block
discipline exactly (``tests/canary_support.py``).

READ-ONLY — the ring never writes to Lark.
"""
import pytest

import canary_support
from larkdocio.auth import get_read_credentials
from larkdocio.read.client import Client
from larkdocio.read.config import new_config
from larkdocio.read.parser import Parser
from larkdocio.utils.url import validate_download_url

pytestmark = pytest.mark.zoo


def _read_once(url, app_id, app_secret):
    """One independent client+parse cycle against the zoo doc.

    Returns ``(blocks, markdown, block_types)``. Any client failure raises
    (surfacing as a test failure when the ring CAN run), never a swallowed
    ``None``.
    """
    domain, doc_type, token = validate_download_url(url)
    client = Client(app_id, app_secret, domain)

    if doc_type == "wiki":
        node = client.get_wiki_node_info(token)
        doc_type, token = node.obj_type, node.obj_token

    docx, blocks = client.get_docx_content(token)

    parser = Parser(new_config())
    markdown = parser.parse_docx_content(docx.document_id, blocks)

    block_types = sorted({b.block_type for b in blocks})
    return blocks, markdown, block_types


def test_blockzoo_ring_scratch_doc(capsys):
    # Load the repo .env (local runs) — a no-op in CI where creds + URL are
    # injected as variables. Then SKIP LOUDLY if the ring cannot run (advisory:
    # a missing zoo doc/creds is never a failure).
    canary_support.load_env()
    reason = canary_support.blockzoo_missing_reason()
    if reason:
        pytest.skip(reason)

    url = canary_support.blockzoo_doc_url()
    app_id, app_secret = get_read_credentials()

    blocks, markdown, block_types = _read_once(url, app_id, app_secret)

    # Sanity only — the ring is advisory evidence, not a strict oracle (the
    # offline fixtures + goldens are the binding oracle). A zoo doc is a broad
    # block sampler, so assert it read a non-trivial, multi-type document.
    assert len(blocks) >= 10, (
        f"expected a broad block-zoo doc; got only {len(blocks)} blocks"
    )
    assert markdown.strip(), "produced markdown is empty"
    assert len(block_types) >= 3, (
        f"expected a multi-type block-zoo doc; got types {block_types}"
    )

    # Evidence for the QA/Activity log (visible under `pytest -m zoo -s`).
    with capsys.disabled():
        print(
            f"\n[zoo] blocks={len(blocks)} "
            f"md_bytes={len(markdown.encode('utf-8'))} "
            f"types={block_types}"
        )
