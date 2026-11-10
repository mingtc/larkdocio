"""THE LIVE ARM for the folder asset fetch (LD-386 AC8) — read-only, disposable-only.

``@pytest.mark.live``, deselected by default. Run it with::

    pytest -m live

**What it proves.** That the shipped ``folder --assets`` leg fetches real Lark binaries — an
ordinary **image** and a **whiteboard** (a mindmap / flowchart, which is a distinct endpoint:
the board PNG export, not the media download) — and lands them exactly where the layout ruling
says they land: **one shared, flat, token-named pool** at ``<-o>/static/<asset token>.<ext>``,
with every reference in the rendered Markdown rewritten to that local relative link, and a token
that two documents share fetched **once**.

--------------------------------------------------------------------------------------------
THE SUBJECT — and the honest limit of what a live run can be here
--------------------------------------------------------------------------------------------

The AC asks for a **disposable folder containing an image-bearing and a mindmap-bearing
document**. That resource **cannot be provisioned by this library or by this gate**:
``create_folder`` is a Drive **write**, and Drive writes are permanent — *no purge verb exists
anywhere in* ``drive/v1`` — so a folder created here would be irreversible tenant residue on
every run. This is the same wall ``tests/test_live_drive_canary.py`` documents, and the reason
that gate reads the bot's **own root folder** instead of a self-provisioned one. Provisioning
such a folder is a maintainer/console action, not a code one; ``LARKDOCIO_CANARY_FOLDER`` is the hook
for it and is unset today.

So the arm runs **two legs**, and says plainly which is which:

* **Leg A — the folder leg, live.** A real walk of the subject folder (the ``CANARY_FOLDER``
  override if set, else the bot's own root, discovered live) through the shipped
  ``read_folder(..., assets=True)`` + ``fetch_folder_assets``. It proves the whole path end to
  end on real Lark data. If that folder happens to contain **no** asset-bearing document — the
  bot's root does not today — the leg **says so with the count** rather than passing quietly;
  it does not fabricate a subject.
* **Leg B — the asset leg, live, against the disposable block zoo.**
  ``LARKDOCIO_BLOCKZOO_DOC`` is the standing disposable that actually carries the shapes in
  question (one image and two boards). The document is read through the **same** folder-child
  reader the walk uses, assembled into a ``FolderRead``, rendered by the **same**
  ``render_folder``, and fetched by the **same** ``fetch_folder_assets`` — so every line of
  shipped code under test is the walk's own. The only synthetic part is the folder
  *membership*, which is precisely the resource that cannot be provisioned. Leg B also carries
  the **collision** case, by placing the same document in the result twice: one token, one
  fetch, one file, every reference relinked.

**READ-ONLY, and disposables only.** Nothing here writes to Lark. The one write is to a pytest
``tmp_path``, and the assertions are about that tree; the subject documents are the standing
disposable zoo and the bot's own root — **never** a real document and never the write scratch
doc. The tmp tree is pytest's own and is torn down with the test.

**Skips loudly, never silently.** Without read credentials — or without the zoo doc for leg B —
the gate skips with a message naming exactly what is missing.
"""
import os

import canary_support
import pytest

from larkdocio.common import init_env
from larkdocio.drive import read as drive_read
from larkdocio.drive.assets import ASSET_DIR, BOARD, IMAGE, fetch_folder_assets
from larkdocio.drive.client import DriveClient
from larkdocio.drive.models import FolderChild, FolderName, FolderWalk, WalkedChild
from larkdocio.drive.render import render_folder

pytestmark = pytest.mark.live
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

canary_support.load_env()


@pytest.fixture(scope="module")
def live_env():
    if not canary_support.read_creds_available():
        pytest.skip(canary_support.missing_reason())
    init_env(None)
    return True


# --------------------------------------------------------------------------- #
# Leg A — the folder leg, live, against a real folder.                          #
# --------------------------------------------------------------------------- #

def test_leg_a_a_real_folder_walk_with_assets_lands_them_in_the_shared_pool(
        live_env, tmp_path):
    override = canary_support.canary_folder_override()
    client = DriveClient.from_read_credentials("larksuite.com")
    subject = override or client.root_folder_token()

    result = drive_read.read_folder(subject, client=client, assets=True)
    markdown = render_folder(result)
    markdown, report = fetch_folder_assets(result, markdown, str(tmp_path))

    referenced = sum(len(o.assets or ()) for o in result.reads)
    print(f"\nleg_a: folder={subject} documents_read={len(result.reads)} "
          f"assets_referenced={referenced} fetched={len(report.fetched)} "
          f"misses={len(report.misses)}")

    # Whatever the folder held, the invariants hold.
    assert result.accounted()
    for token in report.fetched:
        landed = [p for p in (tmp_path / ASSET_DIR).iterdir() if p.stem == token]
        assert landed, f"{token} reported fetched but no file named for it is in the pool"
        assert landed[0].stat().st_size > 0
        # The relinked path CONTAINS the token (that is the naming rule), so the check is
        # that no BARE reference `](<token>)` survives.
        assert f"]({token})" not in markdown, "a fetched token was left un-relinked"

    if referenced == 0:
        pytest.skip(
            f"the subject folder ({subject}) contains no asset-bearing document, so the "
            "folder leg cannot exercise a fetch. This is stated, not passed over: a "
            "disposable folder holding an image-bearing and a mindmap-bearing document "
            "cannot be self-provisioned (making one is a permanent Drive write with no purge "
            "verb — see this module's docstring), so it is a console action: set "
            "LARKDOCIO_CANARY_FOLDER to such a folder and "
            "this leg fetches from it. Leg B exercises the same shipped code against the "
            "disposable block zoo.")


# --------------------------------------------------------------------------- #
# Leg B — the asset leg, live, on real image + real mindmap/flowchart boards.   #
# --------------------------------------------------------------------------- #

def _zoo_result(url, token, *, copies=1):
    """Read the disposable zoo document through the folder's OWN child reader, and dress the
    result as the ``FolderRead`` the walk would have produced for it."""
    produced = drive_read.read_child("docx", url=url, token=token, name="Block zoo",
                                     assets=True)
    outcomes = []
    for index in range(copies):
        child = FolderChild(token=f"{token}{'' if index == 0 else f'-copy{index}'}",
                            name="Block zoo" if index == 0 else f"Block zoo (copy {index})",
                            type="docx", url=url)
        walked = WalkedChild(child=child, depth=1, path=f"/{child.name}")
        outcomes.append(drive_read.ChildOutcome(
            walked, drive_read.READ, surface="docx", markdown=produced.markdown,
            revision=produced.revision, assets=produced.assets))
    return drive_read.FolderRead(
        root_token="zoo", root_name=FolderName(token="zoo", name="Asset arm"),
        walk=FolderWalk(root_token="zoo", children=tuple(o.walked for o in outcomes)),
        outcomes=tuple(outcomes))


@pytest.fixture(scope="module")
def zoo(live_env):
    url = canary_support.blockzoo_doc_url()
    if url is None:
        pytest.skip(
            f"{canary_support.BLOCKZOO_DOC_ENV} is unset — the disposable document carrying "
            "an image and whiteboard blocks is what this leg fetches from; without it the "
            "asset leg cannot be exercised live.")
    return url, url.rsplit("/", 1)[-1]


def test_leg_b_a_real_image_and_a_real_mindmap_land_in_the_token_named_pool(zoo, tmp_path):
    url, token = zoo
    result = _zoo_result(url, token)
    referenced = result.reads[0].assets
    kinds = {ref.kind for ref in referenced}

    markdown, report = fetch_folder_assets(
        result, render_folder(result), str(tmp_path))

    print(f"\nleg_b: doc={token} referenced={len(referenced)} kinds={sorted(kinds)} "
          f"fetched={len(report.fetched)} misses={[m.reason for m in report.misses]} "
          f"pool={sorted(p.name for p in (tmp_path / ASSET_DIR).iterdir())}")

    assert referenced, "the zoo document referenced no asset at all — its shape has drifted"
    assert BOARD in kinds, (
        "the zoo document carries no whiteboard block, so the mindmap / flowchart path — the "
        "consumer's blocking case — is not exercised by this run")
    assert IMAGE in kinds, "the zoo document carries no image block"
    assert report.complete, f"assets were refused: {[m.reason for m in report.misses]}"

    pool = tmp_path / ASSET_DIR
    for ref in referenced:
        landed = [p for p in pool.iterdir() if p.stem == ref.token]
        assert landed, f"{ref.kind} {ref.token} did not land in the pool"
        assert landed[0].stat().st_size > 0, f"{ref.token} landed empty"
        # THE LAYOUT, live: flat, under -o, named for the token — no per-document directory.
        assert landed[0].parent == pool
        assert f"{ASSET_DIR}/{landed[0].name}" in markdown
        assert f"]({ref.token})" not in markdown, "a bare token survived the relink"


def test_leg_b_the_same_asset_in_two_documents_is_fetched_once(zoo, tmp_path):
    """The collision case, live: the same document twice ⇒ the same tokens twice ⇒ still one
    file per token, because the filename IS the token."""
    url, token = zoo
    result = _zoo_result(url, token, copies=2)
    distinct = {ref.token for outcome in result.reads for ref in outcome.assets}

    markdown, report = fetch_folder_assets(
        result, render_folder(result), str(tmp_path))

    pool = sorted(p.name for p in (tmp_path / ASSET_DIR).iterdir())
    print(f"\nleg_b_collision: documents=2 distinct_tokens={len(distinct)} "
          f"fetched={len(report.fetched)} pool={pool}")

    assert len(report.fetched) == len(distinct), "an asset was fetched more than once"
    assert len(pool) == len(distinct)
    for name in pool:
        stem = os.path.splitext(name)[0]
        assert markdown.count(f"{ASSET_DIR}/{name}") == 2, (
            f"{stem} is referenced by two documents; both references must be relinked")
