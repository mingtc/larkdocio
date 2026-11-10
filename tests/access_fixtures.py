"""Drive **access** fixtures — DERIVED FROM THE PERMISSIONS SPIKE'S COMMITTED CAPTURES.

PROJECT.md § Quality bar: *"fixtures are deserialized from actual API JSON, not hand-mocked
dicts"*. Every builder here reads a capture file from ``tests/captures/permissions-spike/captures/`` at
call time, so a capture edited or deleted reddens the tests standing on it.

Provenance, one line per name (all under ``tests/captures/permissions-spike/captures/``, LD-420's probes):

* :data:`MEMBERS_EMPTY` ← ``702-`` — a freshly minted docx: ``code 0`` with ``items: []``. The
  constructive fact behind the whole feature — the owner is **not** a member row.
* :data:`META_OWNER` ← ``704-`` — ``metas/batch_query``: ``owner_id`` is the bot's own
  ``open_id`` on a document it created.
* :data:`GRANT_FULL_ACCESS` ← ``707-`` — the ``POST …/members`` echo (**not** the finding).
* :data:`MEMBERS_FULL_ACCESS` ← ``708-`` — the independent read-back that **is** the finding.
* :data:`GRANT_EDIT` / :data:`MEMBERS_EDIT` ← ``729-`` / ``730-`` — the ``edit`` floor.
* :data:`UPDATE_RAISE` / :data:`MEMBERS_AFTER_RAISE` ← ``731-`` / ``732-`` — raise to
  ``full_access``.
* :data:`UPDATE_LOWER` / :data:`MEMBERS_AFTER_LOWER` ← ``733-`` / ``734-`` — lower to ``view``.
* :data:`REVOKE` / :data:`MEMBERS_AFTER_REVOKE` ← ``736-`` / ``737-`` — the revoke leaves
  ``items: []``, not a tombstone.
* :data:`PUBLIC_BASELINE` ← ``705-`` — the eight keys a fresh docx's public settings carry,
  with ``copy_entity`` / ``security_entity`` both ``anyone_can_edit``.
* :data:`PATCH_COPY` / :data:`PUBLIC_AFTER_COPY` ← ``709-`` / ``710-`` — ``copy_entity`` stored.
* :data:`PATCH_SECURITY` / :data:`PUBLIC_AFTER_SECURITY` ← ``711-`` / ``712-`` —
  ``security_entity`` stored.
* :data:`PATCH_LOCK_SWITCH` ← ``721-`` — ``lock_switch`` refused ``1063001``: read-only on this
  PATCH route.
* :data:`PATCH_EXTERNAL_ACCESS` ← ``715-`` — ``external_access_entity`` refused ``91009``.
* :data:`PATCH_INVENTED_KEY` ← ``725-`` — the invented-key control, **refused** rather than
  accepted-and-ignored: the reason an accepted value may be read as a stored value **on this
  route** (D-59).
* :data:`MEMBERS_V2_404` ← ``703-`` — ``drive/v2/permissions/{token}/members`` is not a route.
* :data:`GROUP_SHAPE` ← ``735-`` — the ONE group call, made with a synthetic id, which is why
  group grants are **unmeasured** rather than refused.
* :data:`TRANSFER_SWALLOW_ECHO` / :data:`TRANSFER_SWALLOW_READBACK` ← ``759-`` / ``760-`` — the
  measured swallow on the member route: accepted, not stored. The reason every op here reads
  its own work back.
"""
import json
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CAPTURES = REPO_ROOT / "tests" / "captures" / "permissions-spike" / "captures"

MEMBERS_EMPTY = "702-ld420-leg0-b-list-permission-members-of-a-doc-the-bot-just-created-v1.json"
MEMBERS_V2_404 = (
    "703-ld420-leg0-c-list-permission-members-v2-for-a-second-view-of-the-same-.json")
META_OWNER = "704-ld420-leg0-d-drive-meta-owner-id-and-url-for-the-fresh-disposable.json"
PUBLIC_BASELINE = "705-ld420-leg0-e-baseline-permission-public-payload-every-key-it-returns.json"
GRANT_FULL_ACCESS = (
    "707-ld420-leg1-b-grant-full-access-to-the-resolved-grantee-the-echo-not-th.json")
MEMBERS_FULL_ACCESS = (
    "708-ld420-leg1-c-independent-member-list-read-back-after-the-full-access-g.json")
PATCH_COPY = "709-ld420-ac3-patch-copy-entity-to-anyone-can-view-candidate-lever.json"
PUBLIC_AFTER_COPY = "710-ld420-ac3-read-back-after-patching-copy-entity.json"
PATCH_SECURITY = "711-ld420-ac3-patch-security-entity-to-anyone-can-view-candidate-lever.json"
PUBLIC_AFTER_SECURITY = "712-ld420-ac3-read-back-after-patching-security-entity.json"
PATCH_EXTERNAL_ACCESS = "715-ld420-ac3-patch-external-access-entity-to-open-candidate-lever.json"
PATCH_LOCK_SWITCH = "721-ld420-ac3-patch-lock-switch-to-true-candidate-lever.json"
PATCH_INVENTED_KEY = "725-ld420-ac3-invented-key-control-patch-zzz-ld420-control.json"
GRANT_EDIT = "729-ld420-leg3-b-grant-edit-to-the-resolved-grantee.json"
MEMBERS_EDIT = "730-ld420-leg3-c-independent-member-list-read-back-after-the-edit-grant.json"
UPDATE_RAISE = "731-ld420-ac8-update-raise-the-member-from-edit-to-full-access.json"
MEMBERS_AFTER_RAISE = "732-ld420-ac8-read-back-after-the-update-to-full-access.json"
UPDATE_LOWER = "733-ld420-ac8-downgrade-lower-the-member-from-full-access-to-view.json"
MEMBERS_AFTER_LOWER = "734-ld420-ac8-read-back-after-the-downgrade-to-view.json"
GROUP_SHAPE = (
    "735-ld420-ac8-group-shape-one-capture-only-member-type-opendepartmentid-no.json")
REVOKE = "736-ld420-ac8-revoke-remove-the-member-entirely.json"
MEMBERS_AFTER_REVOKE = "737-ld420-ac8-read-back-after-the-revoke.json"
TRANSFER_SWALLOW_ECHO = (
    "759-ld420-leg2-h-recovery-can-the-app-re-add-itself-as-a-full-access-membe.json")
TRANSFER_SWALLOW_READBACK = (
    "760-ld420-leg2-i-read-back-the-member-list-after-the-self-re-add-attempt.json")

#: The grantee the spike resolved from a committed test address (capture ``706-``).
GRANTEE_OPEN_ID = "ou_exampleowner00000000000000000001"
#: The bot's own ``open_id`` — the OWNER of a document it created (capture ``704-``).
BOT_OPEN_ID = "ou_examplebot0000000000000000000001"
#: The address already committed as a test constant in
#: ``tests/test_live_contacts_resolve_colleague.py``; no new identity enters here.
GRANTEE_EMAIL = "example.user@example.com"

DOC = "Example96b1f1037377879d8dd5"


def capture(name: str) -> dict:
    """One committed capture, parsed. The single door onto the evidence base."""
    path = CAPTURES / name
    assert path.exists(), f"the fixture's evidence is missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def response(name: str) -> dict:
    """The Lark response body a capture recorded — what the transport hands back."""
    return capture(name)["response"]


def request(name: str) -> dict:
    """The request a capture recorded — method, path and body, as sent."""
    return capture(name)["request"]


def members(name: str) -> list:
    """The ``data.items`` array of a member-list capture."""
    return response(name)["data"]["items"]


def public_payload(name: str) -> dict:
    """The ``data.permission_public`` object of a public-settings capture."""
    return response(name)["data"]["permission_public"]


def owner_id(name: str = META_OWNER) -> str:
    """The ``owner_id`` a ``metas/batch_query`` capture recorded."""
    return response(name)["data"]["metas"][0]["owner_id"]


# --------------------------------------------------------------------------- #
# The transport seam — reused from the enumeration fixtures so every drive leg  #
# is asserted against the same recording ``urlopen``.                           #
# --------------------------------------------------------------------------- #

from drive_fixtures import (  # noqa: E402  (after the constants, on purpose)
    Call,
    RecordingTransport,
    fast_limiter,
    token_fetcher,
)


def access_router(*, members_pages=(), member_write=None, public_pages=(), public_patch=None,
                  meta=None):
    """A ``route`` for the whole access family.

    ``members_pages`` are the ``GET …/members`` bodies served in order (so a read-back that
    fires one time too many runs off the end loudly rather than re-reading a stale answer);
    ``member_write`` answers the POST/PUT/DELETE; ``public_pages`` are the
    ``GET …/public`` bodies; ``public_patch`` answers the PATCH (a callable sees the
    :class:`Call`); ``meta`` answers ``metas/batch_query``.
    """
    remaining_members = list(members_pages)
    remaining_public = list(public_pages)

    def route(call):
        if call.path.endswith("/metas/batch_query"):
            assert meta is not None, "the route was given no metas/batch_query answer"
            return meta(call) if callable(meta) else meta
        if "/permissions/" in call.path and call.path.endswith("/public"):
            if call.method == "PATCH":
                assert public_patch is not None, "the route was given no PATCH answer"
                return public_patch(call) if callable(public_patch) else public_patch
            assert remaining_public, "the client read the public settings once too often"
            answer = remaining_public.pop(0)
            return answer(call) if callable(answer) else answer
        if call.method == "GET":
            assert remaining_members, "the client read the member list once too often"
            answer = remaining_members.pop(0)
            return answer(call) if callable(answer) else answer
        assert member_write is not None, "the route was given no member-write answer"
        return member_write(call) if callable(member_write) else member_write

    return route


class FixedResolver:
    """A stand-in ``resolve_colleague`` — the contacts leg, injected.

    Records every keyword it was handed, so a test can prove the SHIPPED verb was called with
    the email and nothing else was invented beside it.
    """

    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer
