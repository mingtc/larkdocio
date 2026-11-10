"""THE SINGLE LIVE READ ARM for the Drive enumeration client (LD-324 AC11).

``@pytest.mark.live``, deselected by default. Run it with::

    pytest -m live

**What it is, and what it is deliberately not.** *One* arm proving the shipped client reaches a
real folder and comes back with sane, typed data. It is **not** the determinism canary — that is
LD-328, the tranche's live gate — and keeping this small is the point: a story that spends the
tranche's live budget early leaves nothing for the gate that matters.

**Its subject is the BOT'S OWN root folder, discovered live** (the Drive spec § D7). It needs no
Maintainer-designated folder and never touches one: the arm asks
``GET /drive/explorer/v2/root_folder/meta`` who the caller is, then lists that folder's first
page. Nothing here depends on the maintainer's real tree.

**Read-only, and provably so.** Every op in :data:`larkdocio.drive.ops.OPS` declares
``mutates: False`` — asserted here *before* the first call, so a future write op cannot be
smuggled onto this path — and the arm's own verbs are checked against the declared set.

**Gentle.** Two calls, both through the client's own limiter (one per 1.2 s, the spike's own
spacing). No recursion: a real root folder could be arbitrarily deep, and this arm is not the
place to find out. Rate limits are not probed.

**Skips loudly, never silently.** Without read credentials the whole module skips with a message
naming exactly what is missing.
"""
import canary_support
import pytest

from larkdocio.drive import ops as drive_ops
from larkdocio.drive.client import DriveClient
from larkdocio.drive.models import CHILD_FIELDS

pytestmark = pytest.mark.live
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

canary_support.load_env()


def missing_reason():
    """Why this arm cannot run, or ``None`` — the skip message, so absence is never silence."""
    if not canary_support.read_creds_available():
        return (
            "Read credentials unset — set LARK_READ_APP_ID/LARK_READ_APP_SECRET (or the "
            "legacy LARK_APP_ID/LARK_APP_SECRET) to run the live Drive enumeration arm."
        )
    return None


def tenant_domain():
    """The API domain to talk to — taken from the canary doc's URL when one is configured (so
    a ``feishu.cn`` tenant is not addressed at ``larksuite.com``), else the package default.

    The canary doc is used **only** as a domain hint; this arm never reads it.
    """
    raw = canary_support.canary_doc_url()
    if not raw:
        return "larksuite.com"
    try:
        from larkdocio.common import validate_download_url

        return validate_download_url(raw)[0]
    except Exception:  # noqa: BLE001 - a malformed hint must not fail the arm
        return "larksuite.com"


@pytest.fixture(scope="module")
def drive_client():
    reason = missing_reason()
    if reason:
        pytest.skip(reason)
    return DriveClient.from_read_credentials(tenant_domain())


def test_the_registry_declares_the_whole_arm_read_only_BEFORE_it_calls_anything():
    # TRANSFORMED, not deleted (LD-409, D-24): this arm touches ONLY the R1 enumeration legs,
    # and that set is still read-only. The whole-registry answer moved when create_version was
    # registered, so the claim is asserted at the scope the arm actually has — and the mutating
    # set is pinned too, so a SECOND write op cannot arrive on this path unnoticed.
    assert drive_ops.read_only(drive_ops.ENUMERATION_OPS), (
        "a mutating op reached the Drive registry; this arm runs against a real tenant and "
        "must not be the thing that discovers that")
    # LD-432 widened the registry's verb set (the access family declares PUT, DELETE and
    # PATCH), so the claim is asserted at the scope this arm actually has: the ENUMERATION's
    # own declared verbs. Nothing this arm calls can be anything but a GET or one of the
    # declared query POSTs.
    assert sorted({d.http_method for d in drive_ops.ENUMERATION_OPS}) == ["GET", "POST"]
    # TRANSFORMED, not bumped (LD-487): document_security_level joined folder_name on the
    # metas/batch_query endpoint, so the declared-read POST set is two rather than one. The
    # REASON is unchanged — a documented query POST must be VISIBLY declared a read, or the
    # registry classifies it as a write — so the set is pinned by NAME and every member must
    # declare mutates is False. A THIRD declared-read POST reddens this gate instead of
    # silently joining a count.
    query_posts = {d.name: d for d in drive_ops.query_posts()}
    assert set(query_posts) == {"folder_name", "document_security_level"}
    assert all(d.mutates is False for d in query_posts.values())


def test_the_live_arm_reaches_the_bots_own_root_folder_and_lists_it(drive_client):
    root = drive_client.root_folder_token()
    assert root, "the root_folder/meta leg returned no token"

    contents = drive_client.list_folder_children(root)

    # A brand-new tenant's root can legitimately be empty; what must hold is that whatever came
    # back is the shape the client claims to parse.
    for child in contents.children:
        assert child.token, "a child arrived with no token"
        assert child.type, "a child arrived with no type"
        for field in CHILD_FIELDS:
            assert hasattr(child, field), field

    assert contents.has_more in (True, False)
    assert drive_client.api_calls == 2, (
        f"the arm's live budget is 2 calls; it spent {drive_client.api_calls}")
