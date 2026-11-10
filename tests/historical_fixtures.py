"""Docx **historical read** fixtures — DERIVED FROM THE EDITIONS SPIKE'S COMMITTED CAPTURES.

PROJECT.md § Quality bar: *"fixtures are deserialized from actual API JSON, not hand-mocked
dicts"*. Every builder here reads a capture file from ``tests/captures/editions-spike/captures/`` at call
time, so a capture edited or deleted reddens the tests standing on it — which is the point:
these tests exist to hold a measurement, and a measurement with no evidence behind it is the
failure mode the whole issue guards against.

Provenance, one line per name (all under ``tests/captures/editions-spike/captures/``, LD-404's probe):

* :data:`AT_REVISION_TWO` ← ``13-`` — the **falsification**: the flat blocks route at
  ``document_revision_id=2`` returned the 2-block STATE-ONE body.
* :data:`AT_HEAD` ← ``15-`` — the same document at ``-1`` in the same instant: 3 blocks. The
  pair is what makes the pin *measured* rather than *modelled* (D-05).
* :data:`OVER_RANGE` ← ``205-`` — ``head + 50`` on a 4-revision document: ``code 0`` and
  **head's body**, no error. The trap the op cannot detect.
* :data:`REVISION_ZERO_REFUSED` ← ``206-`` — ``0`` → HTTP 400 ``1770001 invalid param``.
* :data:`REVISION_NON_NUMERIC_REFUSED` ← ``208-`` — ``abc`` → HTTP 400 ``99992402 field
  validation failed``, attributed to the ``document_revision_id`` field.
* :data:`PINNED_PAGE_ONE` ← ``209-`` — a historical read paging (``page_size=1``,
  ``has_more: true``, a real ``page_token``).
* :data:`META_PINNED` ← ``19-`` — the docx **meta** route asked for revision 2 reporting
  ``revision_id: 3``, which is **head**: the meta route ignores the pin.
* :data:`RAW_CONTENT_PINNED` / :data:`RAW_CONTENT_HEAD` ← ``16-`` / ``17-`` — ``raw_content``
  with a numeric pin, byte-identical to the plain head call: that route ignores the pin too.
* :data:`RUNG_1` … :data:`RUNG_4` ← ``201-``–``204-`` — a 4-revision document walked rung by
  rung, reproducing its edit history exactly.
"""
import json
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CAPTURES = REPO_ROOT / "tests" / "captures" / "editions-spike" / "captures"

AT_REVISION_TWO = (
    "13-leg4b-blocks-at-historical-document-revision-id-state-one-read-pair.json")
AT_HEAD = "15-leg4b-blocks-at-head-1-for-comparison.json"
OVER_RANGE = "205-r3-blocks-at-document-revision-id-54.json"
REVISION_ZERO_REFUSED = "206-r3-blocks-at-document-revision-id-0.json"
REVISION_NON_NUMERIC_REFUSED = "208-r3-blocks-at-document-revision-id-abc-non-numeric.json"
PINNED_PAGE_ONE = "209-r3-historical-read-paginates-page-size-1.json"
META_PINNED = "19-leg4d-docx-meta-pinned-at-a-historical-revision.json"
RAW_CONTENT_PINNED = "16-leg4b-raw-content-at-historical-document-revision-id-state-one.json"
RAW_CONTENT_HEAD = "17-leg4b-raw-content-at-head-1-for-comparison.json"
RUNG_1 = "201-r3-blocks-at-document-revision-id-1.json"
RUNG_2 = "202-r3-blocks-at-document-revision-id-2.json"
RUNG_3 = "203-r3-blocks-at-document-revision-id-3.json"
RUNG_4 = "204-r3-blocks-at-document-revision-id-4.json"


def capture(name: str) -> dict:
    """One committed capture, parsed. The single door onto the evidence base."""
    path = CAPTURES / name
    assert path.exists(), f"the fixture's evidence is missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def response(name: str) -> dict:
    """The Lark response body a capture recorded."""
    return capture(name)["response"]


def items(name: str) -> list:
    """The ``data.items`` array of a blocks capture — raw payload dicts."""
    return response(name)["data"]["items"]


def blocks(name: str):
    """The ``data.items`` array as **real SDK Block objects**, the shape the parser eats."""
    from harness import build_blocks

    return build_blocks(items(name))


def document_id(name: str) -> str:
    """The document the capture was taken against, read off its own request path."""
    path = capture(name)["request"]["path"]
    return path.split("/documents/")[1].split("/")[0].split("?")[0]


def texts(name: str) -> list:
    """Every block's text content, in order — the cheapest way to SEE two states differ."""
    out = []
    for item in items(name):
        body = item.get("page") or item.get("text") or {}
        out.append("".join(
            element.get("text_run", {}).get("content", "")
            for element in body.get("elements", [])
        ))
    return out
