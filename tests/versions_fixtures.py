"""Drive **versions** fixtures — DERIVED FROM THE EDITIONS SPIKE'S COMMITTED CAPTURES.

PROJECT.md § Quality bar: *"fixtures are deserialized from actual API JSON, not hand-mocked
dicts"*. So every builder here reads a capture file from ``tests/captures/editions-spike/captures/`` at
call time; a capture edited or deleted reddens the tests standing on it, which is the point.

Provenance, one line per name (all under ``tests/captures/editions-spike/captures/``, LD-404's probe):

* :data:`LIST_ONE_PAGE` ← ``07-`` — the LIST shape: three versions, ``has_more: false``, and
  the ten fields a version object carries (``version`` being the token).
* :data:`LIST_PAGE_1` / :data:`LIST_PAGE_2` ← ``08-`` / ``09-`` — the **real** ``page_size=1``
  pair, page 2 fetched with page 1's own ``page_token``. Both pages still report
  ``has_more: true`` (the document held three versions), which is why the exhaustion test
  bounds itself with the page budget rather than pretending the walk ran dry.
* :data:`LIST_EMPTY` ← ``10-`` — a never-versioned document: ``code 0`` with ``items: []``.
* :data:`LIST_NO_OBJ_TYPE` ← ``11-`` — ``obj_type`` omitted: HTTP 400 ``99992402``.
* :data:`CREATE` ← ``02-`` — the CREATE echo: ``data`` **is** the version object, with **no**
  ``update_time``.
* :data:`CREATE_NO_NAME` ← ``04-`` — the name refusal, ``252804105``.
* :data:`CREATE_DUPLICATE` ← ``104-`` — a second ``V1.0`` becomes ``V1.0(1)``: a distinct token.
* :data:`CREATE_300_CHAR` ← ``105-`` — 300 characters accepted and echoed whole.
* :data:`HEAD_BEFORE` / :data:`HEAD_AFTER` ← ``101-`` / ``103-`` — revision ``2`` before the
  create and ``2`` after it: creating a version is **revision-inert**.
* :data:`OBJ_TYPE_BITABLE_REFUSED` ← ``308-`` — ``bitable`` → ``1068411``.
* :data:`OBJ_TYPE_SHEETS_REFUSED` ← ``403-`` — ``sheets`` → ``99992402``, whose own
  ``field_violations`` enumerate ``options: [docx,sheet]``.
* :data:`SHEET_CREATE` / :data:`SHEET_LIST` ← ``402-`` / ``405-`` — ``sheet`` accepted, on a
  disposable spreadsheet.
"""
import json
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CAPTURES = REPO_ROOT / "tests" / "captures" / "editions-spike" / "captures"

LIST_ONE_PAGE = "07-leg1-list-versions-read-pair-page-size-10.json"
LIST_PAGE_1 = "08-leg1-list-versions-page-size-1-pagination-probe.json"
LIST_PAGE_2 = "09-leg1-list-versions-page-2-page-token-honoured.json"
LIST_EMPTY = "10-leg1-list-versions-on-a-never-versioned-doc-empty-vs-denial.json"
LIST_NO_OBJ_TYPE = "11-leg1-list-versions-without-obj-type-is-it-required.json"
CREATE = "02-leg0-leg2-create-version-write-pair-drive-v1-files-versions.json"
CREATE_NO_NAME = "04-leg2-create-version-with-no-name-is-name-required.json"
CREATE_DUPLICATE = "104-r2-create-version-duplicate-name.json"
CREATE_300_CHAR = "105-r2-create-version-300-char-name-limit-disclosure.json"
HEAD_BEFORE = "101-r2-head-revision-before-creating-a-version.json"
HEAD_AFTER = "103-r2-head-revision-after-creating-a-version-inertness.json"
OBJ_TYPE_BITABLE_REFUSED = (
    "308-leg5-drive-file-versions-on-a-base-does-the-versions-family-cover-bita.json")
OBJ_TYPE_SHEETS_REFUSED = "403-r5-create-version-on-a-spreadsheet-obj-type-sheets.json"
SHEET_CREATE = "402-r5-create-version-on-a-spreadsheet-obj-type-sheet.json"
SHEET_LIST = "405-r5-list-versions-on-a-spreadsheet-obj-type-sheet.json"


def capture(name: str) -> dict:
    """One committed capture, parsed. The single door onto the evidence base."""
    path = CAPTURES / name
    assert path.exists(), f"the fixture's evidence is missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def response(name: str) -> dict:
    """The Lark response body a capture recorded — what the transport hands back."""
    return capture(name)["response"]


def items(name: str) -> list:
    """The ``data.items`` array of a LIST capture."""
    return response(name)["data"]["items"]


def created_payload(name: str = CREATE) -> dict:
    """The ``data`` object a CREATE capture echoed — the version object itself."""
    return response(name)["data"]


def head_revision(name: str) -> int:
    """The ``revision_id`` a docx-meta capture recorded."""
    return response(name)["data"]["document"]["revision_id"]


# --------------------------------------------------------------------------- #
# The transport seam — reused from the enumeration fixtures so both drive legs  #
# are asserted against the same recording ``urlopen``.                          #
# --------------------------------------------------------------------------- #

from drive_fixtures import (  # noqa: E402  (after the constants, on purpose)
    Call,
    RecordingTransport,
    fast_limiter,
    token_fetcher,
)

def versions_router(pages, *, create=None):
    """A ``route`` for the versions family.

    ``pages`` is the ordered list of LIST response bodies (page 1, page 2, …) — served in
    order, so a walk that makes one call too many runs off the end loudly rather than
    silently re-reading page 1. ``create`` answers the ``POST``; the docx meta leg
    (the pairing's revision read) is answered by :func:`meta_router` instead.
    """
    remaining = list(pages)

    def route(call):
        if call.method == "POST":
            assert create is not None, "the route was given no CREATE answer"
            return create(call) if callable(create) else create
        assert remaining, (
            f"the walk asked for page {len(pages) + 1} of a {len(pages)}-page listing")
        answer = remaining.pop(0)
        return answer(call) if callable(answer) else answer

    return route


def meta_router(revision_response, inner):
    """Wrap ``inner`` so the docx meta leg (``/open-apis/docx/v1/documents/…``) answers too."""

    def route(call):
        if "/docx/v1/documents/" in call.path:
            return revision_response
        return inner(call)

    return route
