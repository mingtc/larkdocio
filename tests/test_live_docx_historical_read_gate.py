"""THE HISTORICAL-READ GATE (LD-410) — the revision pin, proved FALSIFIABLY against real Lark.

``@pytest.mark.live_write``, deselected by default. Run it explicitly::

    pytest -m live_write

**Why this gate is a WRITE gate for a READ capability.** A read-only canary cannot produce two
states, and a pinned read that cannot be distinguished from a head read proves nothing (D-05):
"it returned blocks" is what a *silently ignored* parameter also does. So this gate creates its
own disposable, gives it a **second state**, and asserts the pinned body **differs** from the
head body read in the same run. That difference is the whole claim.

Four things only a live run can establish:

1. **The pin BITES on the route the shipped read uses** — the flat blocks list. The captures
   established it on a probe's own transport; this establishes it on `get_docx_content`'s.
2. **The earlier body is the earlier body** — the block added in state two is ABSENT from the
   pinned read and PRESENT in the head read, in the same run, on the same document.
3. **An out-of-range revision silently returns HEAD** — the trap the shipped words state and
   the operation cannot detect. Asserted here so the disclosure stays true, or reddens.
4. **The document meta route ignores the pin** — re-measured through the shipped
   `read_document_revision`, which is why a pinned read carries no `revision_id` at all.

**Disposables only (D-12).** The document this gate touches it created itself, in this run, and
trashes in a ``finally``. It names **no** pre-existing document: not the read canary, not
``LARKDOCIO_WRITE_SCRATCH_DOC``, not ``LARKDOCIO_SCRATCH_BASE``, not ``LARKDOCIO_SCRATCH_SHEET``,
not the block zoo and not the comment zoo. Gone-ness is proved by an **independent re-query**
after the delete, never by the delete's own return code.

**Gentle.** One document, one edit, and a handful of reads, each on the shipped clients. No
burst, no retention probe — how far back the pin reaches is answered ``unmeasured`` in the
shipped words and this gate does not go looking for the edge.

**Skips loudly, never silently.** Without write credentials the whole gate skips with a message
naming exactly what is missing.

**It ships WITH its mirror.** Everything it claims *about itself* — the disposables-only
posture, the self-created subject, the teardown, the independent re-query — is exactly the class
of claim a credential-less run "verifies" by not running, so it is verified in
``test_live_docx_historical_read_gate_offline.py`` on every plain ``pytest``.
"""
import time

import canary_support
import pytest

from larkdocio.common import get_read_credentials, get_write_credentials
from larkdocio.errors import LarkAPIError
from larkdocio.read.client import Client
from larkdocio.read.history import HistoricalDocumentMeta, HistoricalReadRefusedError
from larkdocio.write.client import WriteClient, text_block

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing the
# statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

#: The write app's tenant region — matches the toolkit's default OpenAPI domain. NOT a document
#: reference: this gate never addresses a file it did not create.
DOMAIN = "larksuite.com"

#: How far past head the over-range probe reaches. Large enough that no concurrent edit could
#: make it a real revision.
OVER_RANGE_STRIDE = 50


def _texts(blocks):
    """Every block's text content — the cheapest way to SEE two states differ."""
    out = []
    for block in blocks:
        for holder in ("page", "text"):
            body = getattr(block, holder, None)
            if body is None:
                continue
            out.append("".join(
                (getattr(element, "text_run", None).content or "")
                for element in (body.elements or [])
                if getattr(element, "text_run", None) is not None))
    return out


def test_a_pinned_read_returns_the_EARLIER_BODY_and_head_returns_HEADs(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    write_app, write_secret = get_write_credentials()
    read_app, read_secret = get_read_credentials()
    if not (read_app and read_secret):
        pytest.skip("no READ credentials in the environment; the pinned read is a READ")

    wc = WriteClient(write_app, write_secret, DOMAIN)
    reader = Client(read_app, read_secret, DOMAIN)

    nonce = str(int(time.time()))
    state_one = f"larkdocio historical-read gate :: STATE-ONE {nonce}"
    state_two = f"larkdocio historical-read gate :: STATE-TWO {nonce}"
    row = {"file_token": None, "revision_at_state_one": None, "revision_at_state_two": None,
           "pinned_texts": None, "head_texts": None, "over_range_texts": None,
           "meta_revision_under_a_pin": None, "file_absent_after_delete": None}

    dest_folder = canary_support.require_disposables_folder()
    doc = wc.create_document(title=f"larkdocio-historical-read-gate {nonce}",
                             folder_token=dest_folder)
    doc_id = doc["document_id"]
    row["file_token"] = doc_id
    try:
        # STATE ONE — one line, and the revision that describes it.
        wc.create_children(doc_id, doc_id, [text_block(state_one)], index=0)
        row["revision_at_state_one"] = wc.read_document_revision(doc_id)

        # STATE TWO — a second line, so the two states are distinguishable BY CONTENT.
        wc.create_children(doc_id, doc_id, [text_block(state_two)], index=0)
        row["revision_at_state_two"] = wc.read_document_revision(doc_id)

        # THE PINNED READ, through the shipped op.
        pinned_meta, pinned_blocks = reader.get_docx_content(
            doc_id, document_revision_id=row["revision_at_state_one"])
        row["pinned_texts"] = _texts(pinned_blocks)
        assert isinstance(pinned_meta, HistoricalDocumentMeta), type(pinned_meta)

        # THE HEAD READ, in the same run, through the same op with no pin.
        head_meta, head_blocks = reader.get_docx_content(doc_id)
        row["head_texts"] = _texts(head_blocks)

        # THE OVER-RANGE PROBE — the trap the shipped words disclose.
        _over_meta, over_blocks = reader.get_docx_content(
            doc_id, document_revision_id=row["revision_at_state_two"] + OVER_RANGE_STRIDE)
        row["over_range_texts"] = _texts(over_blocks)

        # THE META ROUTE under a pin is not reachable through the shipped op at all (it does
        # not call it), so the disclosure is re-measured on the op that DOES read meta.
        row["meta_revision_under_a_pin"] = wc.read_document_revision(doc_id)

        print(f"[historical gate {nonce}] {row}")
    finally:
        try:
            wc.delete_document(doc_id)
        except Exception as exc:                # pragma: no cover - teardown must not mask
            row["delete_error"] = str(exc)
        # ZERO ORPHANS, verified INDEPENDENTLY: re-query and require Lark to say it is gone.
        try:
            wc.get_document(doc_id)
            row["file_absent_after_delete"] = False
        except LarkAPIError:
            row["file_absent_after_delete"] = True
        with capsys.disabled():
            print(f"[historical gate close-out] {row}")

    # (1) FALSIFICATION — the two reads DISAGREE, which is what makes the pin measured here.
    assert row["pinned_texts"] != row["head_texts"], (
        "the pinned read and the head read returned the same body, so this run proves "
        "NOTHING about the pin — it is exactly what a silently ignored parameter looks like")
    assert state_one in row["pinned_texts"], row["pinned_texts"]
    assert state_two not in row["pinned_texts"], (
        "the pinned read carried content written AFTER the revision it pinned")
    assert state_two in row["head_texts"], row["head_texts"]

    # (2) The pinned metadata carries the pin and refuses a revision_id.
    assert pinned_meta.document_revision_id == row["revision_at_state_one"]
    assert head_meta.revision_id == row["revision_at_state_two"], (
        "the HEAD read's meta must report head's revision — that is the number that is true")
    with pytest.raises(HistoricalReadRefusedError):
        pinned_meta.revision_id

    # (3) THE TRAP, live: a revision far past head comes back as head, with no error.
    assert row["over_range_texts"] == row["head_texts"], (
        "an out-of-range revision no longer returns head silently — the shipped disclosure "
        "says it does, so either the API changed or the disclosure is now wrong")

    # (4) The meta route ignores the pin: it reports HEAD's revision, which is why the pinned
    # read carries none.
    assert row["meta_revision_under_a_pin"] == row["revision_at_state_two"]

    # (5) The local refusals cost no call — proved here on the LIVE client, so a refusal that
    # quietly went to the wire would be visible as a Lark error rather than a local one.
    for refused in (0, -1, -2, "2"):
        with pytest.raises(HistoricalReadRefusedError):
            reader.get_docx_content(doc_id, document_revision_id=refused)

    assert row["file_absent_after_delete"] is True, "the disposable survived its delete"
