"""LD-326 — ``read_folder()`` and its one-document rendering.

The centerpiece is **skip-loudly**: a child that fails NEVER fails the walk, and every miss is
disclosed in Lark's own words. The headline promise is the mechanical invariant
``count(children walked) == count(read) + count(disclosed)`` (folders being the third,
structural, category — see :func:`test_AC4_the_mechanical_invariant`).

Fixtures are built THROUGH the LD-324 walker + LD-325 dispatcher over a real ``DriveClient``
wired to the committed-capture-derived recording transport (``tests/drive_fixtures.py``); the
document readers are the one injectable seam (offline: a fake; live: LD-328's canary).
"""
import builtins
import inspect

from larkdocio.errors import LarkAPIError
from larkdocio.drive.client import DriveClient
from larkdocio.drive.read import (
    FolderRead,
    ChildOutcome,
    read_folder,
    read_child_markdown,
    FOLDER,
    READER_RAISED,
    LARK_REFUSED,
    NO_READER,
    MALFORMED,
)
from larkdocio.drive.render import render_folder

import drive_fixtures as fx


# --------------------------------------------------------------------------- #
# Harness — a real DriveClient over the recording transport + an injectable    #
# document reader (the readers are the one seam that must not touch the API     #
# offline).                                                                     #
# --------------------------------------------------------------------------- #

def _drive_client(listings, *, refusals=None, root_token=None, metas=None):
    transport = fx.RecordingTransport(
        fx.listing_router(listings, refusals=refusals, root_token=root_token, metas=metas))
    return DriveClient(
        "app-id", "app-secret", "larksuite.com",
        urlopen=transport, token_fetcher=fx.token_fetcher, rate_limiter=fx.fast_limiter())


def _md_reader(refuse=(), raise_on=()):
    """A fake document reader. ``refuse`` tokens get a Lark refusal (code+msg); ``raise_on``
    tokens get a plain reader bug; everything else reads to a deterministic stub."""
    def reader(surface, *, url, token, name=None):
        if token in refuse:
            raise LarkAPIError(f"drive child {token} refused", code=1061002, msg="params error.")
        if token in raise_on:
            raise KeyError("blocks[3] missing a required field")
        return f"# {name or token}\n\nbody of {token} ({surface})"
    return reader


def _flat(tokens_types, *, root="fldRoot"):
    """One flat folder: ``[(token, type), ...]`` under ``root``. docx/sheet/bitable get a url."""
    children = []
    for token, ctype in tokens_types:
        url = (f"https://x.larksuite.com/{'docx' if ctype == 'docx' else ctype}/{token}"
               if ctype in ("docx", "sheet", "bitable") else None)
        children.append({
            "token": token, "name": f"name-{token}", "type": ctype,
            "parent_token": root, "url": url, "shortcut_info": None,
            "created_time": "1", "modified_time": "2", "owner_id": "o",
        })
    return {root: fx.page(children)}


# --------------------------------------------------------------------------- #
# AC1 — read_folder returns a structured result over the maintainer-tree-shaped fixture #
# --------------------------------------------------------------------------- #

def test_AC1_read_folder_returns_a_structured_result_over_the_real_35_child_tree():
    root = fx.real_tree_root()
    result = read_folder(root, client=_drive_client(fx.real_tree_listings()), reader=_md_reader())

    assert isinstance(result, FolderRead)
    # The walked tree: 35 children, each carrying token/type/name/parent/depth.
    assert len(result.walk.children) == 35
    for walked in result.walk.children:
        assert walked.child.token
        assert walked.depth >= 1
        assert walked.child.parent_token  # every non-root child names its parent
    # One outcome per walked child (a plain, inspectable object — not a generator).
    assert len(result.outcomes) == len(result.walk.children)
    assert all(isinstance(o, ChildOutcome) for o in result.outcomes)
    # The real tree is 27 docx + 6 folder + 2 file.
    assert len(result.reads) == 27
    assert len(result.folders) == 6
    assert len(result.skips) == 2  # the two `file` children — no reader
    # Each read child carries its Markdown; each skip carries a reason.
    assert all(o.markdown for o in result.reads)
    assert all(o.skip and o.skip.reason for o in result.skips)
    # The headline invariant holds mechanically.
    assert result.accounted()


def test_AC1_read_folder_accepts_a_bare_token_or_a_url():
    listings = _flat([("d1", "docx")])
    by_token = read_folder("fldRoot", client=_drive_client(listings), reader=_md_reader())
    by_url = read_folder(
        "https://x.larksuite.com/drive/folder/fldRoot",
        client=_drive_client(listings), reader=_md_reader())
    assert by_token.root_token == by_url.root_token == "fldRoot"
    assert len(by_token.reads) == len(by_url.reads) == 1


# --------------------------------------------------------------------------- #
# AC3 — skip loudly, in Lark's own words; a child that fails never fails the    #
# walk. Four modes, plus the mid-walk injection.                                #
# --------------------------------------------------------------------------- #

def test_AC3a_reader_raises_is_disclosed_and_the_walk_continues():
    listings = _flat([("d1", "docx"), ("boom", "docx"), ("d3", "docx")])
    result = read_folder("fldRoot", client=_drive_client(listings),
                         reader=_md_reader(raise_on=("boom",)))
    assert len(result.reads) == 2 and len(result.skips) == 1
    skip = result.skips[0].skip
    assert skip.mode == READER_RAISED
    assert "blocks[3]" in skip.reason  # the reader's own exception carried through


def test_AC3b_lark_refuses_the_child_in_larks_own_code_and_msg():
    listings = _flat([("d1", "docx"), ("nope", "docx"), ("d3", "docx")])
    result = read_folder("fldRoot", client=_drive_client(listings),
                         reader=_md_reader(refuse=("nope",)))
    assert len(result.reads) == 2 and len(result.skips) == 1
    skip = result.skips[0].skip
    assert skip.mode == LARK_REFUSED
    # Lark's OWN words, never a paraphrase.
    assert skip.code == 1061002
    assert skip.msg == "params error."
    assert "1061002" in skip.reason and "params error." in skip.reason


def test_AC3c_a_child_with_no_reader_is_disclosed_never_read():
    listings = _flat([("d1", "docx"), ("f1", "file"), ("m1", "mindnote")])
    result = read_folder("fldRoot", client=_drive_client(listings), reader=_md_reader())
    assert len(result.reads) == 1 and len(result.skips) == 2
    modes = {s.skip.mode for s in result.skips}
    assert modes == {NO_READER}
    reasons = " ".join(s.skip.reason for s in result.skips)
    assert "mindnote" in reasons  # the unknown type is named, never guessed


def test_AC3d_a_malformed_payload_is_disclosed_and_the_walk_continues():
    # A docx child the listing returned with NO url — AC8 says url is present on 27/27, so its
    # absence is a malformed payload, disclosed rather than guessed.
    bad = {"token": "b1", "name": "bad", "type": "docx", "parent_token": "fldRoot",
           "url": None, "shortcut_info": None}
    good = {"token": "g1", "name": "good", "type": "docx", "parent_token": "fldRoot",
            "url": "https://x.larksuite.com/docx/g1", "shortcut_info": None}
    result = read_folder("fldRoot", client=_drive_client({"fldRoot": fx.page([bad, good])}),
                         reader=_md_reader())
    assert len(result.reads) == 1 and len(result.skips) == 1
    assert result.skips[0].skip.mode == MALFORMED


def test_AC3_mid_walk_injection_34_reads_plus_1_disclosed_miss():
    children = [(f"d{i}", "docx") for i in range(35)]
    children[17] = ("boom", "docx")  # a failure injected into the MIDDLE
    result = read_folder("fldRoot", client=_drive_client(_flat(children)),
                         reader=_md_reader(raise_on=("boom",)))
    assert len(result.walk.children) == 35
    assert len(result.reads) == 34
    assert len(result.skips) == 1
    assert result.skips[0].token == "boom"


# --------------------------------------------------------------------------- #
# AC4 — the mechanical invariant, as a property over a ragged fixture.          #
# --------------------------------------------------------------------------- #

def _ragged_client():
    """A ragged tree with a file, a refused child, an unknown type, a shortcut, an empty
    subfolder and a capped branch."""
    root = "fldRoot"
    root_children = [
        fx.child_payload("d1", root),                                    # readable docx
        {"token": "f1", "name": "raw", "type": "file", "parent_token": root, "url": None,
         "shortcut_info": None},                                          # no reader
        {"token": "u1", "name": "board", "type": "mindnote", "parent_token": root,
         "url": None, "shortcut_info": None},                             # unknown type
        {"token": "sc1", "name": "link", "type": "shortcut", "parent_token": root,
         "url": "https://x.larksuite.com/docx/sc1",
         "shortcut_info": {"target_type": "docx", "target_token": "tgt1"}},  # shortcut → docx
        {"token": "subEmpty", "name": "empty", "type": "folder", "parent_token": root,
         "url": None, "shortcut_info": None},                             # empty subfolder
        {"token": "subRef", "name": "refusing", "type": "folder", "parent_token": root,
         "url": None, "shortcut_info": None},                             # holds a refused child
        {"token": "subDeep", "name": "deep", "type": "folder", "parent_token": root,
         "url": None, "shortcut_info": None},                             # capped branch
    ]
    listings = {
        root: fx.page(root_children),
        "subEmpty": fx.page([]),
        "subRef": fx.page([fx.child_payload("refused", "subRef")]),
        "subDeep": fx.page([{"token": "subDeeper", "name": "deeper", "type": "folder",
                             "parent_token": "subDeep", "url": None, "shortcut_info": None}]),
        "subDeeper": fx.page([fx.child_payload("buried", "subDeeper")]),
    }
    return _drive_client(listings)


def test_AC4_the_mechanical_invariant_children_equals_read_plus_disclosed():
    # max_depth=2 caps the subDeep branch (subDeeper is at depth 2; its own child is not walked).
    result = read_folder("fldRoot", client=_ragged_client(),
                         reader=_md_reader(refuse=("refused",)), max_depth=2)

    walked = result.walk.children
    # The partition is total and disjoint: every walked child is accounted for exactly once.
    assert result.accounted()
    assert len(result.outcomes) == len(walked)
    assert {o.token for o in result.outcomes} == {w.child.token for w in walked}
    assert (len(result.reads) + len(result.skips) + len(result.folders)) == len(walked)
    # And the AC4-literal form over the readable (non-folder) children:
    documents = [o for o in result.outcomes if o.kind != FOLDER]
    assert len(documents) == len(result.reads) + len(result.skips)
    # The ragged composition actually exercised each arm:
    assert len(result.folders) >= 3           # subEmpty, subRef, subDeep, subDeeper
    skip_modes = {s.skip.mode for s in result.skips}
    assert {NO_READER, LARK_REFUSED} <= skip_modes
    assert result.walk.truncations            # the capped branch is disclosed by the walk


# --------------------------------------------------------------------------- #
# AC2 — the one-document rendering: tree index, documents, disclosure section.  #
# --------------------------------------------------------------------------- #

def test_AC2_one_document_has_tree_index_then_documents_then_disclosure():
    listings = _flat([("d1", "docx"), ("f1", "file"), ("d2", "docx")])
    result = read_folder("fldRoot", client=_drive_client(listings, metas=None),
                         reader=_md_reader())
    doc = render_folder(result)

    # Three regions in order.
    i_tree = doc.index("## Folder tree")
    i_docs = doc.index("## Documents")
    i_not = doc.index("## Not read")
    assert i_tree < i_docs < i_not
    # Tree index names each child by name and type.
    tree_region = doc[i_tree:i_docs]
    assert "name-d1" in tree_region and "(docx)" in tree_region and "(file)" in tree_region
    # Each read child's Markdown is under its own heading.
    assert "### name-d1" in doc and "body of d1" in doc
    # The disclosure names the skipped child.
    assert "name-f1" in doc[i_not:]


def test_AC2_empty_disclosure_section_is_omitted_and_absence_means_zero_misses():
    listings = _flat([("d1", "docx"), ("d2", "docx")])
    result = read_folder("fldRoot", client=_drive_client(listings), reader=_md_reader())
    doc = render_folder(result)
    assert result.skips == ()
    assert "## Not read" not in doc            # omitted
    # The equivalence: the section is present iff there is at least one miss.
    listings2 = _flat([("d1", "docx"), ("f1", "file")])
    result2 = read_folder("fldRoot", client=_drive_client(listings2), reader=_md_reader())
    doc2 = render_folder(result2)
    assert ("## Not read" in doc2) == (len(result2.skips) > 0)


# --------------------------------------------------------------------------- #
# AC5 — degenerate shapes are ordinary, not errors.                             #
# --------------------------------------------------------------------------- #

def test_AC5_empty_folder_renders_a_valid_document_not_an_exception():
    result = read_folder("fldRoot", client=_drive_client({"fldRoot": fx.page([])}),
                         reader=_md_reader())
    doc = render_folder(result)
    assert result.outcomes == ()
    assert isinstance(doc, str) and doc.strip()          # not an empty string
    assert "empty" in doc.lower()


def test_AC5_folder_of_only_subfolders_renders_the_tree_and_no_documents():
    listings = {"fldRoot": fx.page([
        {"token": "s1", "name": "sub1", "type": "folder", "parent_token": "fldRoot",
         "url": None, "shortcut_info": None}]), "s1": fx.page([])}
    doc = render_folder(read_folder("fldRoot", client=_drive_client(listings),
                                    reader=_md_reader()))
    assert "## Folder tree" in doc and "sub1" in doc
    assert "## Documents" not in doc                       # nothing readable


def test_AC5_no_readable_child_at_all_renders_the_misses():
    listings = _flat([("f1", "file"), ("f2", "file")])
    doc = render_folder(read_folder("fldRoot", client=_drive_client(listings),
                                    reader=_md_reader()))
    assert "## Documents" not in doc
    assert "## Not read" in doc and "name-f1" in doc


def test_AC5_single_child_folder_renders_one_document():
    doc = render_folder(read_folder(
        "fldRoot", client=_drive_client(_flat([("d1", "docx")])), reader=_md_reader()))
    assert "### name-d1" in doc and "body of d1" in doc


def test_AC5_unresolved_folder_name_renders_by_token_with_the_name_disclosed():
    # metas=None ⇒ folder_name() degrades to a disclosure; the folder renders by its token,
    # its name never invented.
    result = read_folder("fldRoot", client=_drive_client(_flat([("d1", "docx")]), metas=None),
                         reader=_md_reader())
    assert result.root_name.resolved is False
    doc = render_folder(result)
    assert "fldRoot" in doc                               # by token
    assert result.root_name.disclosure and result.root_name.disclosure in doc


def test_AC5_resolved_folder_name_titles_the_document():
    result = read_folder(
        "fldRoot", reader=_md_reader(),
        client=_drive_client(_flat([("d1", "docx")]),
                             metas=fx.folder_meta_response("fldRoot", "My Folder")))
    assert result.root_name.name == "My Folder"
    assert render_folder(result).startswith("# My Folder")


# --------------------------------------------------------------------------- #
# AC6 — determinism.                                                            #
# --------------------------------------------------------------------------- #

def test_AC6_the_same_input_renders_byte_identically_twice():
    listings = _flat([("d1", "docx"), ("f1", "file"), ("d2", "docx")])
    r1 = render_folder(read_folder("fldRoot", client=_drive_client(listings),
                                   reader=_md_reader()))
    r2 = render_folder(read_folder("fldRoot", client=_drive_client(listings),
                                   reader=_md_reader()))
    assert r1 == r2


def test_AC6_render_reads_no_clock_locale_or_env():
    import larkdocio.drive.render as render_mod
    src = inspect.getsource(render_mod)
    for forbidden in ("import time", "import datetime", "import random", "from datetime",
                      "os.environ", "time.time", "locale.get", "random."):
        assert forbidden not in src, f"render path must not read {forbidden!r}"


# --------------------------------------------------------------------------- #
# AC7 — the library writes no files.                                            #
# --------------------------------------------------------------------------- #

def test_AC7_read_folder_and_render_write_no_files(monkeypatch):
    real_open = builtins.open

    def no_write_open(file, mode="r", *args, **kwargs):
        if any(flag in mode for flag in ("w", "a", "x", "+")):
            raise AssertionError(f"the library path wrote a file: {file!r} ({mode})")
        return real_open(file, mode, *args, **kwargs)

    import os
    monkeypatch.setattr(builtins, "open", no_write_open)
    monkeypatch.setattr(os, "makedirs", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("the library path made a directory")))

    listings = _flat([("d1", "docx"), ("f1", "file")])
    result = read_folder("fldRoot", client=_drive_client(listings), reader=_md_reader())
    render_folder(result)   # no assertion raised == no writes


# --------------------------------------------------------------------------- #
# AC8 — existing readers are called, not reimplemented.                         #
# --------------------------------------------------------------------------- #

def test_AC8_read_folder_feeds_the_docx_reader_the_listings_own_url():
    seen = {}

    def spy(surface, *, url, token, name=None):
        seen[token] = (surface, url)
        return "md"

    listings = _flat([("d1", "docx")])
    read_folder("fldRoot", client=_drive_client(listings), reader=spy)
    assert seen["d1"] == ("docx", "https://x.larksuite.com/docx/d1")


def test_AC8_default_reader_dispatches_base_to_read_base_markdown(monkeypatch):
    calls = {}
    import larkdocio.drive.read as read_mod

    def fake_base(url, **kw):
        calls["base"] = url
        return "base-md"

    monkeypatch.setattr(read_mod, "read_base_markdown", fake_base)
    out = read_child_markdown("base", url="https://x.larksuite.com/base/bt", token="bt")
    assert out == "base-md" and calls["base"] == "https://x.larksuite.com/base/bt"


def test_AC8_default_reader_dispatches_docx_through_the_existing_parse_pipeline(monkeypatch):
    import larkdocio.drive.read as read_mod
    monkeypatch.setattr(read_mod, "_read_docx_markdown",
                        lambda url, **flags: (f"docx-md::{url}", None))
    out = read_child_markdown("docx", url="https://x.larksuite.com/docx/d1", token="d1")
    assert out == "docx-md::https://x.larksuite.com/docx/d1"


# --------------------------------------------------------------------------- #
# LD-381 — the reader seam may hand back a REVISION alongside the Markdown.     #
#                                                                              #
# A change-detection ledger needs an anchor per child, and for the two surfaces  #
# whose read already carries one (docx's document.revision_id, a spreadsheet's   #
# properties.revision off the values reply) it costs ZERO extra calls to keep    #
# it instead of discarding it at the boundary. The seam stays backward           #
# compatible: a reader that returns a plain string still works and its outcome   #
# simply has no revision — which the manifest then reports as UNAVAILABLE        #
# rather than as a value.                                                        #
# --------------------------------------------------------------------------- #

def test_LD381_a_reader_returning_a_plain_string_still_works_and_has_no_revision():
    client = _drive_client(_flat([("d1", "docx")]))
    result = read_folder("fldRoot", client=client, reader=_md_reader())
    [outcome] = result.reads
    assert outcome.markdown.startswith("# name-d1")
    assert outcome.revision is None


def test_LD381_a_reader_returning_a_ChildRead_carries_its_revision_onto_the_outcome():
    from larkdocio.drive.read import ChildRead

    def reader(surface, *, url, token, name=None):
        return ChildRead(markdown=f"# {token}", revision=99)

    client = _drive_client(_flat([("d1", "docx")]))
    result = read_folder("fldRoot", client=client, reader=reader)
    [outcome] = result.reads
    assert outcome.markdown == "# d1"
    assert outcome.revision == 99


def test_LD381_a_skipped_child_never_carries_a_revision():
    client = _drive_client(_flat([("d1", "docx"), ("f1", "file")]))
    result = read_folder("fldRoot", client=client, reader=_md_reader(refuse=("d1",)))
    assert [o.revision for o in result.skips] == [None, None]


def test_LD381_the_default_reader_returns_the_docx_revision_it_already_read(monkeypatch):
    """``_parse`` already returns the document object; its ``revision_id`` was fetched by the
    block read this walk performed, so keeping it costs nothing."""
    import larkdocio.drive.read as read_mod
    from larkdocio.drive.read import read_child

    monkeypatch.setattr(read_mod, "_read_docx_markdown",
                        lambda url, **flags: ("docx-md", 41))
    out = read_child("docx", url="https://x.larksuite.com/docx/d1", token="d1")
    assert (out.markdown, out.revision) == ("docx-md", 41)


def test_LD381_read_child_markdown_still_returns_a_bare_string(monkeypatch):
    """The published entry point's contract does not move — the revision-carrying reader is a
    NEW function beside it, not a changed one."""
    import larkdocio.drive.read as read_mod
    monkeypatch.setattr(read_mod, "_read_docx_markdown", lambda url, **flags: ("docx-md", 41))
    assert read_child_markdown(
        "docx", url="https://x.larksuite.com/docx/d1", token="d1") == "docx-md"
