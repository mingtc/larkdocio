"""The machine-readable folder manifest — ``folder --dump``'s sidecar (LD-381).

The consumer's use case is a **change-detection ledger**: walk a folder, record what is there,
and on the next run fetch only what moved. The rendered Markdown answers that question for a
human and not at all for a program, so this module's subject is the *other* projection of the
same ``FolderRead``: a JSON object with one row per walked child carrying **title, token, type
and revision**, built the way ``download --dump`` builds its sidecar rather than under a second
grammar.

Three properties are load-bearing and each has its own arm here:

1. **Every walked child gets a row** — the manifest inherits ``FolderRead.accounted()``'s
   promise, so a skipped child is a row with its disclosure, never an absence.
2. **A revision is never fabricated.** Where the child's type exposes an anchor larkdocio
   already holds, the row carries it; where it does not, the row says so **explicitly** —
   ``availability: "unavailable"`` plus the honest reason. There is no third state in which a
   missing revision looks like a present one, and no key is silently dropped (an absent key and
   a clean value are indistinguishable to a machine).
3. **It is a pure function of the read** — no clock, no environment, no dict-iteration order —
   so two dumps of one result are byte-identical.
"""
import json

import pytest

from larkdocio.drive.manifest import (
    REVISION_AVAILABLE,
    REVISION_SOURCES,
    REVISION_UNAVAILABLE,
    folder_manifest,
)
from larkdocio.drive.models import (
    CycleDisclosure,
    FolderChild,
    FolderName,
    FolderWalk,
    RefusedFolder,
    Truncation,
    WalkedChild,
)
from larkdocio.drive.read import (
    FOLDER,
    LARK_REFUSED,
    NO_READER,
    READ,
    SKIPPED,
    ChildOutcome,
    FolderRead,
    SkipDisclosure,
)


# --------------------------------------------------------------------------- #
# A fixture folder with one child of every shape the manifest must describe.    #
# --------------------------------------------------------------------------- #

def _walked(child, depth=1, path=None):
    return WalkedChild(child=child, depth=depth, path=path or f"/{child.name or child.token}")


def _fixture_read():
    doc = FolderChild(
        token="docxT", name="A doc", type="docx",
        url="https://x.larksuite.com/docx/docxT", parent_token="fldrT",
        created_time="1700000000", modified_time="1700009999", owner_id="ou_1")
    sheet = FolderChild(token="shtT", name="A sheet", type="sheet",
                        url="https://x.larksuite.com/sheets/shtT")
    base = FolderChild(token="bseT", name="A base", type="bitable",
                       url="https://x.larksuite.com/base/bseT")
    sub = FolderChild(token="subT", name="Sub", type="folder",
                      url="https://x.larksuite.com/drive/folder/subT")
    raw = FolderChild(token="filT", name="raw.yaml", type="file", url=None)
    denied = FolderChild(token="denT", name="Denied", type="docx",
                         url="https://x.larksuite.com/docx/denT")

    children = (_walked(doc), _walked(sheet), _walked(base), _walked(sub),
                _walked(raw, depth=2, path="/Sub/raw.yaml"), _walked(denied))
    walk = FolderWalk(
        root_token="fldrT", children=children, listing_calls=3, max_depth_reached=2,
        truncations=(Truncation(cap="children", limit=5, at_folder="subT", at_path="/Sub",
                                not_visited=("x1",)),),
        cycles=(CycleDisclosure(token="cycT", path="/Sub/loop", first_seen_path="/",
                                note="met twice"),),
        refusals=(RefusedFolder(token="refT", path="/Sub/closed", note="Lark refused"),),
    )
    outcomes = (
        ChildOutcome(_walked(doc), READ, surface="docx", markdown="# A doc", revision=42),
        ChildOutcome(_walked(sheet), READ, surface="sheets", markdown="| a |", revision=7),
        ChildOutcome(_walked(base), READ, surface="base", markdown="## t"),
        ChildOutcome(_walked(sub), FOLDER, surface="drive"),
        ChildOutcome(_walked(raw, depth=2, path="/Sub/raw.yaml"), SKIPPED, surface=None,
                     skip=SkipDisclosure(mode=NO_READER,
                                         reason="larkdocio ships no reader for raw bytes")),
        ChildOutcome(_walked(denied), SKIPPED, surface="docx",
                     skip=SkipDisclosure(mode=LARK_REFUSED, reason="Lark refused this child",
                                         code=1254005, msg="permission denied",
                                         surface="docx")),
    )
    return FolderRead(root_token="fldrT",
                      root_name=FolderName(token="fldrT", name="My Folder"),
                      walk=walk, outcomes=outcomes)


@pytest.fixture()
def manifest():
    return folder_manifest(_fixture_read())


def _row(manifest, token):
    return next(row for row in manifest["children"] if row["token"] == token)


# --------------------------------------------------------------------------- #
# AC1 — the shape: title / token / type / revision on every child.              #
# --------------------------------------------------------------------------- #

def test_the_folder_itself_is_identified_by_token_and_title(manifest):
    assert manifest["folder"] == {
        "token": "fldrT", "title": "My Folder", "title_disclosure": None}


def test_an_unresolved_folder_title_is_disclosed_never_invented():
    read = _fixture_read()
    unnamed = FolderRead(
        root_token=read.root_token,
        root_name=FolderName(token="fldrT", disclosure="Lark returned no title for fldrT"),
        walk=read.walk, outcomes=read.outcomes)
    folder = folder_manifest(unnamed)["folder"]
    assert folder["title"] is None
    assert folder["title_disclosure"] == "Lark returned no title for fldrT"


def test_every_child_row_carries_the_four_fields_the_consumer_asked_for(manifest):
    for row in manifest["children"]:
        assert set(("title", "token", "type", "revision")) <= set(row)


def test_a_child_row_carries_the_listing_fields_verbatim(manifest):
    assert _row(manifest, "docxT") == {
        "title": "A doc",
        "token": "docxT",
        "type": "docx",
        "surface": "docx",
        "outcome": "read",
        "path": "/A doc",
        "depth": 1,
        "url": "https://x.larksuite.com/docx/docxT",
        "parent_token": "fldrT",
        "created_time": "1700000000",
        "modified_time": "1700009999",
        "owner_id": "ou_1",
        "revision": {
            "availability": REVISION_AVAILABLE,
            "value": 42,
            "anchor": "document.revision_id",
            "detail": REVISION_SOURCES["docx"]["detail"],
        },
        "skip": None,
    }


def test_larks_own_type_word_is_carried_through_untranslated(manifest):
    assert _row(manifest, "shtT")["type"] == "sheet"
    assert _row(manifest, "shtT")["surface"] == "sheets"
    assert _row(manifest, "bseT")["type"] == "bitable"
    assert _row(manifest, "bseT")["surface"] == "base"


def test_the_walk_is_FLAT_and_nesting_rides_path_and_depth(manifest):
    """The decision: one flat list, nesting carried by ``path``/``depth`` — the walk's own
    order, and ``download --dump``'s flat ``blocks`` list is the precedent. No row nests
    another."""
    assert [row["token"] for row in manifest["children"]] == [
        "docxT", "shtT", "bseT", "subT", "filT", "denT"]
    assert _row(manifest, "filT")["depth"] == 2
    assert _row(manifest, "filT")["path"] == "/Sub/raw.yaml"
    assert not any("children" in row for row in manifest["children"])


# --------------------------------------------------------------------------- #
# AC2/AC3 — accounted-for, and revision honesty.                                #
# --------------------------------------------------------------------------- #

def test_every_walked_child_has_exactly_one_row(manifest):
    read = _fixture_read()
    assert read.accounted()
    assert [row["token"] for row in manifest["children"]] == [
        w.child.token for w in read.walk.children]


def test_counts_are_reported_so_a_ledger_need_not_recount(manifest):
    assert manifest["counts"] == {
        "children": 6, "read": 3, "skipped": 2, "folders": 1}


def test_a_docx_revision_is_present_because_the_read_already_held_it(manifest):
    revision = _row(manifest, "docxT")["revision"]
    assert revision["availability"] == REVISION_AVAILABLE
    assert revision["value"] == 42


def test_a_sheet_revision_is_present_off_the_values_reply(manifest):
    revision = _row(manifest, "shtT")["revision"]
    assert revision["availability"] == REVISION_AVAILABLE
    assert revision["value"] == 7
    assert revision["anchor"] == "properties.revision"


def test_a_base_revision_is_UNAVAILABLE_and_says_why(manifest):
    """Base's anchor is per TABLE, not per document — so there is no one number for a Base
    child, and the row says that instead of picking one."""
    revision = _row(manifest, "bseT")["revision"]
    assert revision["availability"] == REVISION_UNAVAILABLE
    assert revision["value"] is None
    assert "per-table" in revision["detail"]
    assert "read_base" in revision["detail"]


def test_a_folder_child_has_no_revision_and_is_not_pretended_to(manifest):
    revision = _row(manifest, "subT")["revision"]
    assert revision["availability"] == REVISION_UNAVAILABLE
    assert revision["value"] is None
    assert revision["anchor"] is None


@pytest.mark.parametrize("token", ["filT", "denT"])
def test_a_skipped_child_is_a_ROW_with_its_disclosure_never_an_absence(manifest, token):
    row = _row(manifest, token)
    assert row["outcome"] == "skipped"
    assert row["skip"]["reason"]
    assert row["revision"]["availability"] == REVISION_UNAVAILABLE
    assert row["revision"]["value"] is None


def test_a_lark_refusal_quotes_larks_own_code_and_msg(manifest):
    assert _row(manifest, "denT")["skip"] == {
        "mode": LARK_REFUSED,
        "reason": "Lark refused this child",
        "code": 1254005,
        "msg": "permission denied",
    }


def test_an_unavailable_revision_points_at_the_free_anchor_that_IS_there(manifest):
    """The honest consolation: the listing gives ``modified_time`` for every child at no extra
    call, so a ledger is not left with nothing."""
    for token in ("bseT", "subT", "filT", "denT"):
        assert "modified_time" in _row(manifest, token)["revision"]["detail"]


def test_a_read_that_came_back_without_a_revision_says_SO_rather_than_zero():
    """Never launder a missing anchor into a real value — ``0`` is a revision a spreadsheet can
    actually have."""
    read = _fixture_read()
    outcomes = tuple(
        ChildOutcome(o.walked, o.kind, surface=o.surface, markdown=o.markdown,
                     skip=o.skip, revision=None) if o.token == "shtT" else o
        for o in read.outcomes)
    manifest = folder_manifest(
        FolderRead(root_token=read.root_token, root_name=read.root_name,
                   walk=read.walk, outcomes=outcomes))
    revision = _row(manifest, "shtT")["revision"]
    assert revision["availability"] == REVISION_UNAVAILABLE
    assert revision["value"] is None
    assert "did not carry" in revision["detail"]


def test_the_per_type_revision_table_ships_INSIDE_the_sidecar(manifest):
    """AC3's "state which types were measured to expose what" is data a program can read, not
    only prose in a doc it will never open."""
    assert manifest["revision_sources"] == REVISION_SOURCES
    assert set(REVISION_SOURCES) == {"docx", "sheets", "base", "folder", "file"}
    for surface, entry in REVISION_SOURCES.items():
        assert entry["availability"] in (REVISION_AVAILABLE, REVISION_UNAVAILABLE)
        assert entry["detail"], f"{surface} has no stated reason"


# --------------------------------------------------------------------------- #
# The walk's own disclosures ride along — a truncated walk must not read as a    #
# complete folder.                                                              #
# --------------------------------------------------------------------------- #

def test_the_walks_incompleteness_is_on_the_sidecar(manifest):
    walk = manifest["walk"]
    assert walk["complete"] is False
    assert walk["listing_calls"] == 3
    assert walk["max_depth_reached"] == 2
    [truncation] = walk["truncations"]
    assert {key: truncation[key] for key in
            ("cap", "limit", "at_folder", "at_path", "not_visited")} == {
        "cap": "children", "limit": 5, "at_folder": "subT", "at_path": "/Sub",
        "not_visited": ["x1"]}
    assert truncation["describe"].startswith("Enumeration stopped at the children cap (5)")
    assert walk["cycles"] == [
        {"token": "cycT", "path": "/Sub/loop", "first_seen_path": "/", "note": "met twice"}]
    assert walk["refusals"] == [
        {"token": "refT", "path": "/Sub/closed", "note": "Lark refused"}]


def test_a_clean_walk_reads_complete_with_empty_disclosure_lists():
    read = _fixture_read()
    clean = FolderRead(
        root_token=read.root_token, root_name=read.root_name,
        walk=FolderWalk(root_token="fldrT", children=read.walk.children,
                        listing_calls=1, max_depth_reached=1),
        outcomes=read.outcomes)
    walk = folder_manifest(clean)["walk"]
    assert walk["complete"] is True
    assert walk["truncations"] == [] and walk["cycles"] == [] and walk["refusals"] == []


# --------------------------------------------------------------------------- #
# Determinism — a pure function of the result.                                  #
# --------------------------------------------------------------------------- #

def test_two_manifests_of_one_result_are_byte_identical():
    first = json.dumps(folder_manifest(_fixture_read()), indent=4, ensure_ascii=False)
    second = json.dumps(folder_manifest(_fixture_read()), indent=4, ensure_ascii=False)
    assert first == second


def test_the_manifest_is_json_serializable_with_no_custom_encoder(manifest):
    """A sidecar a consumer must import larkdocio to decode is not machine-readable."""
    assert json.loads(json.dumps(manifest)) == manifest
