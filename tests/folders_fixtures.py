"""Drive **folder-creation** fixtures — DERIVED FROM LD-467'S OWN COMMITTED CAPTURES.

PROJECT.md § Quality bar: *"fixtures are deserialized from actual API JSON, not hand-mocked
dicts"*. Every builder here reads a capture from ``tests/captures/ld467-create-folder/captures/`` at call
time, so a capture edited or deleted reddens the tests standing on it.

Provenance, one line per name (all under ``tests/captures/ld467-create-folder/captures/``, LD-467's two
probe rounds of 2026-08-15):

* :data:`CREATE` ← ``ld467-01-`` — the happy path: ``code 0`` and a ``data`` carrying **exactly
  two keys**, ``token`` and ``url``. That pair is the whole answer; nothing else is in it.
* :data:`CREATE_DUPLICATE_FIRST` / :data:`CREATE_DUPLICATE_SECOND` ← ``ld467-02-`` / ``03-`` —
  the same name twice under one parent. The second answers ``code 0`` with a **distinct
  token**: a second folder, not a reuse and not a refusal.
* :data:`LIST_AFTER_DUPLICATE` ← ``ld467-04-`` — the parent's own listing, showing **two
  folders whose ``name`` is byte-identical**. This is the evidence for the duplicate-name
  disclosure, and it is a listing rather than an inference.
* :data:`PARENT_OMITTED` ← ``ld467-05-`` — the ``folder_token`` key absent: HTTP 400
  ``99992402 field validation failed`` whose ``field_violations`` say ``folder_token is
  required``. **Lark itself refuses an unaddressed create**; there is no default-parent
  behaviour to describe for an absent key.
* :data:`PARENT_EMPTY_STRING` ← ``ld467-07-`` — ``folder_token: ""``: **accepted**, ``code 0``,
  a real token back. Round 2's ``ld467-21-`` then found that folder **in the bot's own root**,
  which is the trap this library refuses locally rather than passing on.
* :data:`PARENT_NOT_FOUND` ← ``ld467-08-`` — a syntactically plausible token nothing resolves:
  ``1061002 params error.``, the drive family's three-causes-one-code answer.
* :data:`NAME_EMPTY` ← ``ld467-09-`` — ``name: ""``: **accepted**, ``code 0``. Round 2's
  ``ld467-24-`` / ``25-`` then read the stored name back as the **empty string** — a permanent
  nameless folder, which is why the shipped verb refuses an empty name locally.
* :data:`PARENT_IS_A_FILE` ← ``ld467-11-`` — a real **file** token as the parent: ``1061002``.
  So this route *does* police the parent, unlike ``upload_all`` (which accepted a mismatched
  ``parent_type`` / ``parent_node`` pair with ``code 0``).
* :data:`FOLDER_DELETED` / :data:`TRASHED_FOLDER_REQUERY` ← ``ld467-12-`` / ``13-`` — a folder
  trashed through ``DELETE drive/v1/files/{token}?type=folder`` (``code 0``), after which
  ``metas/batch_query`` answers ``metas: []`` with ``failed_list: [{code: 970005}]``. A trashed
  **folder** token stops resolving — the opposite of a trashed **file** token, which does not.
"""
import json
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CAPTURES = REPO_ROOT / "tests" / "captures" / "ld467-create-folder" / "captures"

CREATE = "ld467-01-create-the-disposable-parent-under-the-bots-own-root.json"
CREATE_DUPLICATE_FIRST = "ld467-02-duplicate-probe-first-create.json"
CREATE_DUPLICATE_SECOND = "ld467-03-duplicate-probe-SECOND-create-same-name-same-parent.json"
LIST_AFTER_DUPLICATE = "ld467-04-list-the-parent-after-two-identical-names.json"
PARENT_OMITTED = "ld467-05-parent-OMITTED-entirely.json"
PARENT_EMPTY_STRING = "ld467-07-parent-sent-as-the-EMPTY-STRING.json"
PARENT_NOT_FOUND = "ld467-08-parent-that-does-not-exist.json"
NAME_EMPTY = "ld467-09-EMPTY-name.json"
PARENT_IS_A_FILE = "ld467-11-parent-token-that-is-a-FILE-not-a-folder.json"
FOLDER_DELETED = "ld467-12-delete-the-duplicate-folder.json"
TRASHED_FOLDER_REQUERY = "ld467-13-re-query-a-trashed-folder-token.json"
EMPTY_NAME_STORED = "ld467-24-r2-what-name-does-an-empty-named-folder-carry.json"
EMPTY_NAME_METADATA = "ld467-25-r2-metadata-of-the-empty-named-folder.json"
EMPTY_PARENT_LANDED_IN_ROOT = "ld467-21-r2-is-the-empty-parent-folder-in-the-bots-own-root.json"


def capture(name: str) -> dict:
    """One committed capture, parsed. The single door onto the evidence base."""
    path = CAPTURES / name
    assert path.exists(), f"the fixture's evidence is missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def response(name: str) -> dict:
    """The Lark response body a capture recorded — what the transport hands back."""
    return capture(name)["response"]


def created_data(name: str = CREATE) -> dict:
    """The ``data`` object a CREATE capture echoed — ``{"token": …, "url": …}``."""
    return response(name)["data"]


def listed_files(name: str = LIST_AFTER_DUPLICATE) -> list:
    """The ``data.files`` array of a folder listing capture."""
    return response(name)["data"]["files"]


# --------------------------------------------------------------------------- #
# The transport seam — reused from the enumeration fixtures, so every drive leg #
# is asserted against the same recording ``urlopen``.                           #
# --------------------------------------------------------------------------- #

from drive_fixtures import (  # noqa: E402  (after the constants, on purpose)
    Call,
    RecordingTransport,
    fast_limiter,
    token_fetcher,
)


def create_folder_router(answer):
    """A ``route`` for the folder-creation family: one answer for the one ``POST``.

    ``answer`` is a response body or a callable taking the recorded :class:`Call`. Any other
    path asserts loudly — a folder create that reached a second endpoint is a finding, not a
    detail to absorb.
    """

    def route(call):
        assert call.path.endswith("/files/create_folder"), (
            f"the folder create reached {call.path!r}, which is not its endpoint")
        return answer(call) if callable(answer) else answer

    return route
