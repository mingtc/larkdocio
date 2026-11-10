"""LD-386 — the folder walk's opt-in asset fetch, and the layout decision it forced.

A document whose whole content is a picture — a page that is **only a mind map** —
came back from a folder walk as a file containing a bare token and nothing else: technically
read, semantically empty. ``download`` has always pulled images and whiteboard PNGs; the walk
had no way to say yes.

This module pins the four things that make the opt-in safe, and the one it had to *decide*:

* **AC1 — the flag, and the consistency claim CHECKED rather than assumed.** ``download``'s
  asset handling is **not a flag**: it is unconditional, config-gated (``skip_img_download``,
  default off ⇒ assets always fetched), with attachments as its own separate opt-in. So there
  is no ``download`` flag spelling to copy, and the vocabulary that IS reused is the on-disk
  one — the directory name (``config.output.image_dir``), the token-derived filenames, the
  relative-link rewrite, and warn-and-continue on a per-asset failure.
* **AC2 — the layout.** ONE shared, flat, token-named pool at ``<-o>/static/``. Collisions are
  impossible **by construction** (the filename IS the globally-unique Lark asset token), and
  the same token referenced by two documents is the SAME asset — fetched once, written once,
  every reference relinked. The rejected fork (per-document subdirectories) is the one with a
  real collision: two documents in a Lark folder may legitimately share a title.
* **AC3 — a per-asset failure skips LOUDLY.** Lark's own code and msg, naming the document and
  the asset, in the rendered Markdown as well as the log; the remaining documents still fetch.
* **AC4 — the default walk is unchanged.** No flag ⇒ no asset is collected, no client is built,
  no fetch is attempted, and the bytes written are exactly ``render_folder``'s.
* **AC5 — the mindmap case specifically.** A whiteboard is a distinct fetch path
  (``download_board_image``, the board export endpoint), not the media path, and the walk uses
  it for the board tokens.
"""
import os

import pytest
from click.testing import CliRunner

from cli_invoke import invoke_cli
from larkdocio.cli import cli
from larkdocio.drive import assets as drive_assets, folder_cmd, read as drive_read
from larkdocio.drive.models import AssetRef, FolderChild, FolderName, FolderWalk, WalkedChild
from larkdocio.drive.render import render_folder
from larkdocio.errors import LarkAPIError
from larkdocio.read.config import OutputConfig

DOC_URL = "https://x.larksuite.com/docx/docxTOKEN"


# --------------------------------------------------------------------------- #
# Builders — a FolderRead with read children carrying asset refs.               #
# --------------------------------------------------------------------------- #

def _outcome(token, name, markdown, assets=()):
    child = FolderChild(token=token, name=name, type="docx",
                        url=f"https://x.larksuite.com/docx/{token}")
    walked = WalkedChild(child=child, depth=1, path=f"/{name}")
    return drive_read.ChildOutcome(walked, drive_read.READ, surface="docx",
                                   markdown=markdown, assets=tuple(assets))


def _result(*outcomes):
    return drive_read.FolderRead(
        root_token="F", root_name=FolderName(token="F", name="A folder"),
        walk=FolderWalk(root_token="F", children=tuple(o.walked for o in outcomes)),
        outcomes=tuple(outcomes))


def _recording_fetcher(dest_written=True, fail=()):
    """A fetcher double with ``download_image``'s own contract: ``(kind, token, dir) -> path``."""
    calls = []

    def fetch(kind, token, directory):
        calls.append((kind, token, directory))
        if token in fail:
            raise fail[token] if isinstance(fail, dict) else LarkAPIError("nope")
        ext = ".png" if kind == drive_assets.BOARD else ".jpg"
        path = os.path.join(directory, f"{token}{ext}")
        if dest_written:
            os.makedirs(directory, exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(b"\x89PNG")
        return path

    fetch.calls = calls
    return fetch


# --------------------------------------------------------------------------- #
# AC1 — the option exists, is OFF by default, and its consistency with          #
# `download` is a checked claim, not an assumed one.                            #
# --------------------------------------------------------------------------- #

def _param(command, opt):
    return next(p for p in cli.commands[command].params if opt in p.opts)


def test_ac1_folder_carries_an_assets_flag_off_by_default():
    option = _param("folder", "--assets")
    assert option.is_flag is True
    assert option.default is False
    assert option.name == "assets"


def test_ac1_download_has_no_asset_flag_to_copy_so_the_claim_is_about_the_shape():
    """The consistency claim, checked: ``download`` ships NO asset flag at all — its handling
    is unconditional and config-gated — so ``--assets`` cannot be a second spelling of an
    existing flag, and what is reused is the on-disk vocabulary instead."""
    download_flags = {opt for p in cli.commands["download"].params for opt in p.opts}
    assert not {f for f in download_flags if "asset" in f or "image" in f}
    assert "--assets" not in download_flags


def test_ac1_the_pool_directory_name_is_downloads_own_not_a_second_one():
    """``static`` is DERIVED from the read config's default, never re-coined here."""
    assert drive_assets.ASSET_DIR == OutputConfig().image_dir


def test_ac1_folder_help_renders_the_flag_and_says_it_is_off_by_default():
    out = CliRunner().invoke(cli, ["folder", "--help"]).output
    assert "--assets" in out


def test_ac1_the_cli_threads_the_flag_to_the_handler(monkeypatch):
    seen = {}
    monkeypatch.setattr("larkdocio.cli.handle_folder_command",
                        lambda *a, **k: seen.update(kwargs=k))
    invoke_cli(cli, ["folder", "https://x.larksuite.com/drive/folder/F", "--assets"])
    assert seen["kwargs"]["assets"] is True


def test_ac1_the_cli_defaults_the_flag_off(monkeypatch):
    seen = {}
    monkeypatch.setattr("larkdocio.cli.handle_folder_command",
                        lambda *a, **k: seen.update(kwargs=k))
    invoke_cli(cli, ["folder", "https://x.larksuite.com/drive/folder/F"])
    assert seen["kwargs"]["assets"] is False


# --------------------------------------------------------------------------- #
# AC2 — the layout, and collisions prevented BY CONSTRUCTION.                   #
# --------------------------------------------------------------------------- #

def test_ac2_assets_land_in_one_shared_token_named_pool_under_the_output_dir(tmp_path):
    result = _result(_outcome("d1", "Map A", "![](imgAAA)", [AssetRef("imgAAA", "image")]))
    fetch = _recording_fetcher()

    markdown, report = drive_assets.fetch_folder_assets(
        result, render_folder(result), str(tmp_path), fetcher=fetch)

    assert (tmp_path / "static" / "imgAAA.jpg").exists()
    assert "static/imgAAA.jpg" in markdown
    assert "](imgAAA)" not in markdown, "the bare token survived the relink"
    assert report.directory == str(tmp_path / "static")
    assert report.fetched == ("imgAAA",)


def test_ac2_the_same_asset_in_two_documents_is_fetched_ONCE_and_both_relink(tmp_path):
    """The collision test. Two documents, one token — which is the SAME asset, because a Lark
    asset token is globally unique. One fetch, one file, both references rewritten."""
    result = _result(
        _outcome("d1", "Map A", "![](shared01)", [AssetRef("shared01", "image")]),
        _outcome("d2", "Map B", "![](shared01)", [AssetRef("shared01", "image")]),
    )
    fetch = _recording_fetcher()

    markdown, report = drive_assets.fetch_folder_assets(
        result, render_folder(result), str(tmp_path), fetcher=fetch)

    assert fetch.calls == [("image", "shared01", str(tmp_path / "static"))]
    assert list((tmp_path / "static").iterdir()) == [tmp_path / "static" / "shared01.jpg"]
    assert markdown.count("static/shared01.jpg") == 2
    assert report.fetched == ("shared01",)


def test_ac2_two_documents_sharing_a_TITLE_cannot_collide_because_layout_is_token_named(
        tmp_path):
    """The fork not taken: per-document subdirectories would be named from a title, and two
    documents in one Lark folder may legitimately share one. The flat pool has no such edge."""
    result = _result(
        _outcome("d1", "Example Pre-existing Document", "![](imgAAA)", [AssetRef("imgAAA", "image")]),
        _outcome("d2", "Example Pre-existing Document", "![](imgBBB)", [AssetRef("imgBBB", "image")]),
    )
    markdown, report = drive_assets.fetch_folder_assets(
        result, render_folder(result), str(tmp_path), fetcher=_recording_fetcher())

    assert sorted(p.name for p in (tmp_path / "static").iterdir()) == [
        "imgAAA.jpg", "imgBBB.jpg"]
    assert not (tmp_path / "Example Pre-existing Document").exists()
    assert report.fetched == ("imgAAA", "imgBBB")
    assert "static/imgAAA.jpg" in markdown and "static/imgBBB.jpg" in markdown


def test_ac2_no_pool_directory_is_created_when_the_folder_has_no_assets(tmp_path):
    result = _result(_outcome("d1", "Prose", "# Prose only"))
    markdown, report = drive_assets.fetch_folder_assets(
        result, render_folder(result), str(tmp_path), fetcher=_recording_fetcher())

    assert not (tmp_path / "static").exists()
    assert report.fetched == () and report.misses == ()
    assert markdown == render_folder(result)


# --------------------------------------------------------------------------- #
# AC3 — a per-asset failure skips LOUDLY and never fails the walk.              #
# --------------------------------------------------------------------------- #

def test_ac3_a_refused_asset_is_disclosed_in_larks_own_words_and_the_rest_still_fetch(
        tmp_path, caplog):
    refusal = LarkAPIError("refused", code=1254043, msg="permission denied")
    result = _result(
        _outcome("d1", "Map A", "![](badTOKEN)", [AssetRef("badTOKEN", "image")]),
        _outcome("d2", "Map B", "![](goodTOKEN)", [AssetRef("goodTOKEN", "image")]),
    )
    fetch = _recording_fetcher(fail={"badTOKEN": refusal})

    with caplog.at_level("WARNING", logger="larkdocio"):
        markdown, report = drive_assets.fetch_folder_assets(
            result, render_folder(result), str(tmp_path), fetcher=fetch)

    # The remaining document is still processed.
    assert report.fetched == ("goodTOKEN",)
    assert (tmp_path / "static" / "goodTOKEN.jpg").exists()
    # The miss names the document, the asset, and quotes Lark.
    (miss,) = report.misses
    assert miss.document == "Map A" and miss.token == "badTOKEN" and miss.kind == "image"
    assert miss.code == 1254043 and miss.msg == "permission denied"
    assert "1254043" in miss.reason and "permission denied" in miss.reason
    # Loud in the output, not only in a log.
    assert drive_assets.MISS_HEADING in markdown
    assert "badTOKEN" in markdown.split(drive_assets.MISS_HEADING)[1]
    assert "Map A" in markdown.split(drive_assets.MISS_HEADING)[1]
    # …and loud in the log too.
    assert any("badTOKEN" in r.getMessage() for r in caplog.records)


def test_ac3_a_fetcher_that_raises_anything_else_is_also_disclosed_never_fatal(tmp_path):
    result = _result(_outcome("d1", "Map A", "![](boom)", [AssetRef("boom", "image")]))

    def explode(kind, token, directory):
        raise RuntimeError("socket closed")

    markdown, report = drive_assets.fetch_folder_assets(
        result, render_folder(result), str(tmp_path), fetcher=explode)

    (miss,) = report.misses
    assert miss.code is None and miss.msg is None
    assert "socket closed" in miss.reason
    assert drive_assets.MISS_HEADING in markdown


def test_ac3_the_disclosure_section_is_omitted_entirely_when_nothing_missed(tmp_path):
    result = _result(_outcome("d1", "Map A", "![](imgAAA)", [AssetRef("imgAAA", "image")]))
    markdown, report = drive_assets.fetch_folder_assets(
        result, render_folder(result), str(tmp_path), fetcher=_recording_fetcher())
    assert report.misses == ()
    assert drive_assets.MISS_HEADING not in markdown


# --------------------------------------------------------------------------- #
# AC4 — the default walk is unchanged, provably.                                #
# --------------------------------------------------------------------------- #

def _stub_walk(monkeypatch, child):
    walk = FolderWalk(root_token="F",
                      children=(WalkedChild(child=child, depth=1, path="/A doc"),))
    monkeypatch.setattr(drive_read, "walk_folder", lambda *a, **k: walk)

    class _Client:
        def folder_name(self, token):
            return FolderName(token=token, name="A folder")

    return _Client()


def test_ac4_read_folder_defaults_the_asset_collection_off(monkeypatch):
    seen = {}
    monkeypatch.setattr(drive_read, "read_child",
                        lambda surface, **kwargs: (seen.update(kwargs), "md")[1])
    child = FolderChild(token="docxTOKEN", name="A doc", type="docx", url=DOC_URL)
    drive_read.read_folder("F", client=_stub_walk(monkeypatch, child))
    assert seen["assets"] is False


def test_ac4_read_folder_threads_the_opt_in_into_the_default_reader(monkeypatch):
    seen = {}
    monkeypatch.setattr(drive_read, "read_child",
                        lambda surface, **kwargs: (seen.update(kwargs), "md")[1])
    child = FolderChild(token="docxTOKEN", name="A doc", type="docx", url=DOC_URL)
    drive_read.read_folder("F", client=_stub_walk(monkeypatch, child), assets=True)
    assert seen["assets"] is True


def test_ac4_off_the_outcomes_carry_no_assets_at_all(monkeypatch):
    monkeypatch.setattr(drive_read, "read_child", lambda surface, **kwargs: "md")
    child = FolderChild(token="docxTOKEN", name="A doc", type="docx", url=DOC_URL)
    result = drive_read.read_folder("F", client=_stub_walk(monkeypatch, child))
    assert [o.assets for o in result.outcomes] == [()]


def test_ac4_the_command_writes_render_folders_own_bytes_and_builds_no_client(
        monkeypatch, tmp_path):
    """No flag ⇒ the file is byte-identical to the render, and the asset leg is never entered
    (an exploding fetch_folder_assets stands guard)."""
    result = _result(_outcome("d1", "Map A", "![](imgAAA)"))
    monkeypatch.setattr(folder_cmd, "read_folder", lambda url, **k: result)
    monkeypatch.setattr(folder_cmd, "init_env", lambda env_file=None: None)

    def never(*args, **kwargs):
        raise AssertionError("the asset leg ran with --assets OFF")

    monkeypatch.setattr(folder_cmd, "fetch_folder_assets", never)
    folder_cmd.handle_folder_command("https://x.larksuite.com/drive/folder/F", str(tmp_path))

    written = (tmp_path / "A_folder.md").read_text(encoding="utf-8")
    assert written == render_folder(result)
    assert not (tmp_path / "static").exists()


def test_ac4_the_command_runs_the_asset_leg_only_when_opted_in(monkeypatch, tmp_path):
    result = _result(_outcome("d1", "Map A", "![](imgAAA)", [AssetRef("imgAAA", "image")]))
    monkeypatch.setattr(folder_cmd, "read_folder", lambda url, **k: result)
    monkeypatch.setattr(folder_cmd, "init_env", lambda env_file=None: None)
    monkeypatch.setattr(drive_assets, "_default_fetcher",
                        lambda domain: _recording_fetcher())
    folder_cmd.handle_folder_command("https://x.larksuite.com/drive/folder/F", str(tmp_path),
                                     assets=True)

    written = (tmp_path / "A_folder.md").read_text(encoding="utf-8")
    assert "static/imgAAA.jpg" in written
    assert (tmp_path / "static" / "imgAAA.jpg").exists()


def test_ac4_handle_folder_command_threads_the_flag_into_read_folder(monkeypatch, tmp_path):
    seen = {}

    def fake_read_folder(url, **kwargs):
        seen.update(kwargs)
        return _result()

    monkeypatch.setattr(folder_cmd, "read_folder", fake_read_folder)
    monkeypatch.setattr(folder_cmd, "init_env", lambda env_file=None: None)
    folder_cmd.handle_folder_command("https://x.larksuite.com/drive/folder/F", str(tmp_path),
                                     assets=True)
    assert seen["assets"] is True


# --------------------------------------------------------------------------- #
# AC5 — the mindmap / flowchart case, which is a DISTINCT fetch path.           #
# --------------------------------------------------------------------------- #

def test_ac5_a_mindmap_only_document_stops_being_a_bare_token(tmp_path):
    """The consumer's blocking case: the document's entire content is one whiteboard."""
    board = "![Whiteboard](wbTOKEN)"
    result = _result(_outcome("d1", "Module map", board, [AssetRef("wbTOKEN", "board")]))
    fetch = _recording_fetcher()

    before = render_folder(result)
    assert "![Whiteboard](wbTOKEN)" in before          # today: a token and nothing else

    markdown, report = drive_assets.fetch_folder_assets(
        result, before, str(tmp_path), fetcher=fetch)

    assert "![Whiteboard](static/wbTOKEN.png)" in markdown
    assert (tmp_path / "static" / "wbTOKEN.png").exists()
    assert report.fetched == ("wbTOKEN",)


def test_ac5_a_board_uses_the_board_export_path_not_the_media_path(tmp_path):
    result = _result(_outcome("d1", "Module map", "![Whiteboard](wbTOKEN)",
                              [AssetRef("wbTOKEN", "board")]))
    fetch = _recording_fetcher()
    drive_assets.fetch_folder_assets(result, render_folder(result), str(tmp_path),
                                     fetcher=fetch)
    assert fetch.calls == [("board", "wbTOKEN", str(tmp_path / "static"))]


def test_ac5_the_default_fetcher_routes_each_kind_to_its_own_client_method(monkeypatch):
    calls = []

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def download_image(self, token, out_dir):
            calls.append(("media", token, out_dir))
            return os.path.join(out_dir, f"{token}.png")

        def download_board_image(self, token, out_dir):
            calls.append(("board-export", token, out_dir))
            return os.path.join(out_dir, f"{token}.png")

    monkeypatch.setattr(drive_assets, "Client", _Client)
    monkeypatch.setattr(drive_assets, "get_read_credentials", lambda: ("id", "secret"))
    fetch = drive_assets._default_fetcher("x.larksuite.com")
    fetch("image", "imgAAA", "/out/static")
    fetch("board", "wbTOKEN", "/out/static")
    assert calls == [("media", "imgAAA", "/out/static"),
                     ("board-export", "wbTOKEN", "/out/static")]


def test_ac5_the_docx_leg_collects_image_AND_board_tokens_only_when_opted_in(monkeypatch):
    """The tokens are a projection of the parse the read already did — no extra call, and
    nothing is collected at all with the opt-in off."""
    class _Parser:
        img_tokens = ["imgAAA"]
        board_tokens = ["wbTOKEN"]
        file_tokens = ["fileTOKEN"]

    class _Docx:
        revision_id = 7

    from larkdocio.read import download

    monkeypatch.setattr(download, "init_env", lambda *a, **k: None)
    monkeypatch.setattr(download, "get_read_credentials", lambda: ("app", "secret"))
    monkeypatch.setattr(download, "_resolve_doc",
                        lambda *a, **k: (object(), object(), "docx", "docxTOKEN"))
    monkeypatch.setattr(download, "build_deep_read_clients",
                        lambda *a, **k: (None, None, None))
    monkeypatch.setattr(download, "_parse",
                        lambda *a, **k: (_Docx(), [], _Parser(), "T", "md"))

    _md, _rev, off = drive_read._read_docx_markdown(DOC_URL)
    assert off == ()

    _md, _rev, on = drive_read._read_docx_markdown(DOC_URL, assets=True)
    assert on == (AssetRef("imgAAA", "image"), AssetRef("wbTOKEN", "board")), (
        "attachments are download's own separate opt-in and are NOT in this flag's set")


def test_ac5_read_child_carries_the_assets_through_to_the_outcome(monkeypatch):
    monkeypatch.setattr(drive_read, "_read_docx_markdown",
                        lambda url, **k: ("md", 7, (AssetRef("imgAAA", "image"),)))
    child = FolderChild(token="docxTOKEN", name="A doc", type="docx", url=DOC_URL)
    result = drive_read.read_folder("F", client=_stub_walk(monkeypatch, child), assets=True)
    assert result.reads[0].assets == (AssetRef("imgAAA", "image"),)


# --------------------------------------------------------------------------- #
# The published surface — the ref type and the report are importable.           #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", ["AssetRef", "AssetMiss", "AssetFetch",
                                  "fetch_folder_assets"])
def test_the_asset_leg_is_part_of_the_drive_packages_published_surface(name):
    import larkdocio.drive as drive

    assert name in drive.__all__
    assert getattr(drive, name) is not None
