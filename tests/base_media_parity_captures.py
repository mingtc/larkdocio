"""The LD-436 base-media parity captures, loaded through the pinned SDK's own deserializer.

PROJECT.md § Quality bar: *"fixtures are deserialized from actual API JSON, not hand-mocked
dicts"*. Every payload here is read from ``tests/captures/base-media-parity-spike/captures/`` at call
time and round-tripped through ``lark_oapi``'s ``BatchQueryMetaResponse``, so a capture edited
or deleted reddens the tests standing on it, and an API drift reddens at deserialization.

Provenance, one line per name (all under ``tests/captures/base-media-parity-spike/captures/``):

* :data:`PERMALINKS` ← ``113-`` — ``metas/batch_query`` with ``doc_type: file`` and
  ``with_url: true`` over **both** shipped ``parent_type`` spellings' tokens plus a token that
  was never minted. The success and its own in-call falsifier, in one answer.
* :data:`WRONG_DOC_TYPE_BITABLE` ← ``116-`` / :data:`WRONG_DOC_TYPE_DOCX` ← ``117-`` — **the
  swallow**: a wrong ``doc_type`` answers ``code:0 Success`` with an EMPTY ``metas`` and the
  reason in ``failed_list``. A ``code:0`` here is not a permalink.
* :data:`AFTER_THE_PARENT_DIED` ← ``132-`` — the same query re-read minutes after the parent
  Base was deleted: both permalinks still resolve, ``failed_list`` is absent. The evidence for
  the caveat that ships with the op — **the permalink outlives the bytes' reachability**.

The two tokens are the spike's own, and they are **media** tokens for a Base that has since
been deleted: nothing here is a live address, and nothing here is credential-class (a
permalink is an address, not a signed link — that distinction is the op's whole disclosure).
"""
import json
from pathlib import Path

from lark_oapi.api.drive.v1 import BatchQueryMetaResponse
from lark_oapi.core.json import JSON

CAPTURES = (Path(__file__).resolve().parent.parent
            / "tests" / "captures" / "base-media-parity-spike" / "captures")

PERMALINKS = "113-ac1-metas-batch-query-with-the-permalink-kept-verbatim-plus-a-bogus-to.json"
WRONG_DOC_TYPE_BITABLE = (
    "116-ac3-metas-batch-query-doc-type-bitable-on-the-bitable-image-token.json")
WRONG_DOC_TYPE_DOCX = "117-ac3-metas-batch-query-doc-type-docx-on-the-bitable-image-token.json"
AFTER_THE_PARENT_DIED = "132-ac6-re-read-metas-batch-query-on-both-media-tokens-same-moment.json"

#: The ``bitable_image`` token — the spike's PNG. Capture ``113-``.
IMAGE_TOKEN = "Example406b7cbfc415633680f8"
#: The ``bitable_file`` token — the spike's HTML file. Capture ``113-``.
FILE_TOKEN = "Exampleff109b60c3cf18ac9bca"
#: A token that was never minted, sent in the SAME call as the two above so the success is a
#: real resolution rather than an endpoint that answers anything. Capture ``113-``.
BOGUS_TOKEN = "ZZZZbogus0000000000000000ZZ"


def capture(name: str) -> dict:
    """One committed capture, parsed. The single door onto the evidence base."""
    path = CAPTURES / name
    assert path.exists(), f"the fixture's evidence is missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def payload(name: str) -> dict:
    """The Lark response body a capture recorded — what the transport hands back."""
    return capture(name)["response"]


def request_body(name: str) -> dict:
    """The request body a capture recorded, as sent."""
    return capture(name)["request"]["body"]


def meta_response(name: str) -> BatchQueryMetaResponse:
    """A captured payload through the pinned SDK's own deserializer."""
    return JSON.unmarshal(json.dumps(payload(name)), BatchQueryMetaResponse)


def response_from(body: dict) -> BatchQueryMetaResponse:
    """A response object from a body **derived** from a capture.

    The two derived cases are stated rather than hidden: a success whose ``url`` was removed
    (nobody has captured one, and the op must still refuse to invent an address) and a
    non-zero answer (this endpoint has never been captured refusing a media token). Both are
    edits of a real payload, never a hand-authored dict.
    """
    return JSON.unmarshal(json.dumps(body), BatchQueryMetaResponse)
