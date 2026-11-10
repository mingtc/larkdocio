"""LD-384 — the folder walk can finally say yes to the deep reads ``download`` already offers.

``--deep-read-sheets`` / ``--fidelity-read-sheets`` / ``--deep-read-bases`` existed on
``download`` and on no other verb, so a folder walk returned every embedded sheet and Base as a
placeholder with no way to opt in. This module pins the pass-through, and the three things that
make a mechanical plumbing job safe:

* **one flag grammar, not two** — the ``folder`` options are the SAME option objects' spelling,
  default and help as ``download``'s (both verbs wear one shared ``deep_read_options`` decorator
  in ``larkdocio.cli``, so a second explanation of the same behaviour cannot drift into being);
* **the default is provably unchanged** — with no flags, the docx leg of the walk builds NO
  Sheets client, NO export reader and NO Base client, and ``_parse`` is called exactly the way
  it is today (zero Sheets/Base API calls);
* **skip-loudly is inherited** — a per-child deep-read failure degrades inside the reader (the
  placeholder), and a client that cannot even be built is disclosed as that child's miss while
  the walk continues.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner
from harness import build_blocks

from cli_invoke import invoke_cli
from larkdocio.cli import cli
from larkdocio.drive import folder_cmd, read as drive_read
from larkdocio.drive.models import FolderChild, FolderName, FolderWalk, WalkedChild
from larkdocio.read import download
from larkdocio.read.config import Config
from larkdocio.sheets.extent import UsedRange
from larkdocio.sheets.models import SheetTab

_FLAGS = ("--deep-read-sheets", "--fidelity-read-sheets", "--deep-read-bases")
_CAPTURES = Path(__file__).resolve().parent.parent / "tests" / "captures" / "sheets-spike" / "captures"
ZOO_COMPOUND_TOKEN = "Example38428307171a2bd44d36_EQlPwA"
DOC_URL = "https://x.larksuite.com/docx/docxTOKEN"


def _param(command, opt):
    return next(p for p in cli.commands[command].params if opt in p.opts)


# --------------------------------------------------------------------------- #
# AC1 — one flag grammar: folder's options ARE download's, spelling to help.    #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("opt", _FLAGS)
def test_folder_carries_the_same_option_as_download(opt):
    folder_opt, download_opt = _param("folder", opt), _param("download", opt)
    assert folder_opt.name == download_opt.name
    assert folder_opt.opts == download_opt.opts
    assert folder_opt.is_flag == download_opt.is_flag is True
    assert folder_opt.default == download_opt.default is False
    assert folder_opt.help == download_opt.help, (
        f"{opt} is explained twice — the help text must be the shared constant, not a second "
        "explanation of the same behaviour")


def test_folder_help_renders_the_three_flags():
    out = CliRunner().invoke(cli, ["folder", "--help"]).output
    for opt in _FLAGS:
        assert opt in out


# --------------------------------------------------------------------------- #
# AC1/AC2 — the CLI threads the flags through, and their default is OFF.       #
# --------------------------------------------------------------------------- #

def _capture_handler(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        "larkdocio.cli.handle_folder_command",
        lambda *args, **kwargs: seen.update(args=args, kwargs=kwargs))
    return seen


def test_folder_cli_defaults_every_deep_read_flag_off(monkeypatch):
    seen = _capture_handler(monkeypatch)
    invoke_cli(cli, ["folder", "https://x.larksuite.com/drive/folder/F"])
    assert seen["kwargs"]["deep_read_sheets"] is False
    assert seen["kwargs"]["fidelity_read_sheets"] is False
    assert seen["kwargs"]["deep_read_bases"] is False


def test_folder_cli_threads_the_flags_to_the_handler(monkeypatch):
    seen = _capture_handler(monkeypatch)
    invoke_cli(cli, ["folder", "https://x.larksuite.com/drive/folder/F", *_FLAGS])
    assert seen["kwargs"]["deep_read_sheets"] is True
    assert seen["kwargs"]["fidelity_read_sheets"] is True
    assert seen["kwargs"]["deep_read_bases"] is True


def test_handle_folder_command_threads_the_flags_into_read_folder(monkeypatch, tmp_path):
    seen = {}

    def fake_read_folder(url, **kwargs):
        seen.update(kwargs)
        return _empty_folder_read()

    monkeypatch.setattr(folder_cmd, "read_folder", fake_read_folder)
    monkeypatch.setattr(folder_cmd, "init_env", lambda env_file=None: None)
    folder_cmd.handle_folder_command(
        "https://x.larksuite.com/drive/folder/F", str(tmp_path),
        deep_read_sheets=True, fidelity_read_sheets=True, deep_read_bases=True)
    assert seen["deep_read_sheets"] is True
    assert seen["fidelity_read_sheets"] is True
    assert seen["deep_read_bases"] is True


def test_handle_folder_command_defaults_leave_every_flag_off(monkeypatch, tmp_path):
    seen = {}

    def fake_read_folder(url, **kwargs):
        seen.update(kwargs)
        return _empty_folder_read()

    monkeypatch.setattr(folder_cmd, "read_folder", fake_read_folder)
    monkeypatch.setattr(folder_cmd, "init_env", lambda env_file=None: None)
    folder_cmd.handle_folder_command("https://x.larksuite.com/drive/folder/F", str(tmp_path))
    assert seen["deep_read_sheets"] is False
    assert seen["fidelity_read_sheets"] is False
    assert seen["deep_read_bases"] is False


def _empty_folder_read():
    return drive_read.FolderRead(
        root_token="F", root_name=FolderName(token="F", name="F"),
        walk=FolderWalk(root_token="F", children=()), outcomes=())


# --------------------------------------------------------------------------- #
# read_folder binds the flags into the DEFAULT reader only — an injected        #
# reader keeps the published (surface, url, token, name) seam untouched.        #
# --------------------------------------------------------------------------- #

def _one_docx_walk(monkeypatch):
    child = FolderChild(token="docxTOKEN", name="A doc", type="docx", url=DOC_URL)
    walk = FolderWalk(root_token="F",
                      children=(WalkedChild(child=child, depth=1, path="/A doc"),))
    monkeypatch.setattr(drive_read, "walk_folder", lambda *a, **k: walk)

    class _Client:
        def folder_name(self, token):
            return FolderName(token=token, name="F")

    return _Client()


def test_read_folder_binds_the_flags_into_the_default_reader(monkeypatch):
    seen = {}

    def fake_read_child(surface, **kwargs):
        seen.update(surface=surface, **kwargs)
        return "md"

    monkeypatch.setattr(drive_read, "read_child", fake_read_child)
    drive_read.read_folder("F", client=_one_docx_walk(monkeypatch),
                           deep_read_sheets=True, fidelity_read_sheets=True,
                           deep_read_bases=True)
    assert seen["deep_read_sheets"] is True
    assert seen["fidelity_read_sheets"] is True
    assert seen["deep_read_bases"] is True


def test_read_folder_default_reader_leaves_every_flag_off(monkeypatch):
    seen = {}
    monkeypatch.setattr(drive_read, "read_child",
                        lambda surface, **kwargs: (seen.update(kwargs), "md")[1])
    drive_read.read_folder("F", client=_one_docx_walk(monkeypatch))
    assert seen["deep_read_sheets"] is False
    assert seen["fidelity_read_sheets"] is False
    assert seen["deep_read_bases"] is False


def test_an_injected_reader_still_takes_the_published_four_argument_seam(monkeypatch):
    calls = []

    def only_the_published_seam(surface, *, url, token, name=None):
        calls.append((surface, url, token, name))
        return "md"

    result = drive_read.read_folder("F", client=_one_docx_walk(monkeypatch),
                                    reader=only_the_published_seam,
                                    deep_read_sheets=True)
    assert calls == [("docx", DOC_URL, "docxTOKEN", "A doc")]
    assert result.accounted()


# --------------------------------------------------------------------------- #
# AC2/AC3 — the docx leg: default builds NO deep-read client; opted in it       #
# builds exactly the ones download builds, and the embed renders as content.    #
# --------------------------------------------------------------------------- #

def _explode(*args, **kwargs):
    """Stands in for a deep-read client constructor that must never be reached.

    Deliberately a FUNCTION, not a class with the client's methods on it: it is not a client
    double (it never answers a client call), and shaping it like one would enrol it in the
    gateway-conformance census of real doubles for no gain.
    """
    raise AssertionError("a deep-read client was built while the deep-read flags were OFF")


#: The export reader is reached as ``SheetsExportReader.from_read_credentials(domain)``, so the
#: unreachable stand-in has to carry that one attribute.
_EXPLODING_EXPORT_READER = SimpleNamespace(from_read_credentials=_explode)


def _docx_blocks():
    return build_blocks([
        {"block_id": "root", "parent_id": "doc", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "Doc Title"}}]},
         "children": ["sh"]},
        {"block_id": "sh", "parent_id": "root", "block_type": 30,
         "sheet": {"token": ZOO_COMPOUND_TOKEN, "row_size": None, "column_size": None}},
    ])


class _FakeDocx:
    title = "Doc Title"
    document_id = "root"
    revision_id = 7


class _FakeDocxClient:
    def get_docx_content(self, token):
        return _FakeDocx(), _docx_blocks()


class _FakeSheetsClient:
    """The two methods the type-30 bridge calls, backed by the committed embed captures."""

    def __init__(self, *args, **kwargs):
        self.query_calls = []

    @staticmethod
    def _capture(name):
        return json.loads((_CAPTURES / name).read_text(encoding="utf-8"))

    def query_sheets(self, spreadsheet_token):
        self.query_calls.append(spreadsheet_token)
        return [SheetTab.from_dict(s)
                for s in self._capture("05-embed-tabs.json")["data"]["sheets"]]

    def read_used_range(self, spreadsheet_token, tab, **kwargs):
        values = self._capture("05-embed-values.json")["data"]["valueRange"]["values"]
        return UsedRange.from_tab_values(tab, values)


@pytest.fixture
def docx_leg(monkeypatch):
    """Stub the docx read pipeline at its own entry points; record ``_parse``'s kwargs."""
    seen = {}
    monkeypatch.setattr(download, "init_env", lambda *a, **k: None)
    monkeypatch.setattr(download, "get_read_credentials", lambda: ("app", "secret"))
    monkeypatch.setattr(download, "_resolve_doc",
                        lambda *a, **k: (_FakeDocxClient(), Config(), "docx", "docxTOKEN"))
    real_parse = download._parse

    def spy_parse(client, config, token, **kwargs):
        seen.update(kwargs)
        return real_parse(client, config, token, **kwargs)

    monkeypatch.setattr(download, "_parse", spy_parse)
    return seen


def test_docx_leg_default_builds_no_deep_read_client_at_all(docx_leg, monkeypatch):
    monkeypatch.setattr(download, "SheetsReadClient", _explode)
    monkeypatch.setattr(download, "SheetsExportReader", _EXPLODING_EXPORT_READER)
    monkeypatch.setattr(download, "BaseReadClient", _explode)

    markdown, revision, _assets = drive_read._read_docx_markdown(DOC_URL)

    assert docx_leg == {"sheets_client": None, "sheets_export_reader": None,
                        "base_client": None}
    assert "Embedded Sheet" in markdown       # the placeholder, exactly as today
    assert revision == 7


def test_docx_leg_opted_in_builds_the_clients_download_builds(docx_leg, monkeypatch):
    built = {}
    monkeypatch.setattr(download, "SheetsReadClient",
                        lambda *a, **k: built.setdefault("sheets", _FakeSheetsClient()))
    monkeypatch.setattr(download, "SheetsExportReader", SimpleNamespace(
        from_read_credentials=lambda domain: built.setdefault("export", object())))
    monkeypatch.setattr(download, "BaseReadClient",
                        lambda *a, **k: built.setdefault("base", object()))

    markdown, _revision, _assets = drive_read._read_docx_markdown(
        DOC_URL, deep_read_sheets=True, fidelity_read_sheets=True, deep_read_bases=True)

    assert set(built) == {"sheets", "export", "base"}
    assert docx_leg["sheets_client"] is built["sheets"]
    assert docx_leg["sheets_export_reader"] is built["export"]
    assert docx_leg["base_client"] is built["base"]
    # AC3 — the placeholder became content.
    assert "Embedded Sheet" not in markdown
    assert "| A1 header | B1 header | C1 header |" in markdown


def test_docx_leg_sheets_only_leaves_the_base_client_unbuilt(docx_leg, monkeypatch):
    monkeypatch.setattr(download, "SheetsReadClient", lambda *a, **k: _FakeSheetsClient())
    monkeypatch.setattr(download, "SheetsExportReader", _EXPLODING_EXPORT_READER)
    monkeypatch.setattr(download, "BaseReadClient", _explode)

    drive_read._read_docx_markdown(DOC_URL, deep_read_sheets=True)

    assert docx_leg["sheets_client"] is not None
    assert docx_leg["sheets_export_reader"] is None
    assert docx_leg["base_client"] is None


def test_read_child_routes_the_flags_to_the_docx_leg(monkeypatch):
    seen = {}
    monkeypatch.setattr(drive_read, "_read_docx_markdown",
                        lambda url, **kwargs: (seen.update(url=url, **kwargs), ("md", None))[1])
    drive_read.read_child("docx", url=DOC_URL, token="T", name="A doc",
                          deep_read_sheets=True, deep_read_bases=True)
    assert seen["deep_read_sheets"] is True
    assert seen["fidelity_read_sheets"] is False
    assert seen["deep_read_bases"] is True


def test_a_deep_read_child_that_raises_is_disclosed_and_the_walk_continues(monkeypatch):
    """Skip-loudly is inherited: a per-child deep-read explosion is that child's miss."""
    def boom(url, **kwargs):
        raise RuntimeError("the Base client could not be built")

    monkeypatch.setattr(drive_read, "_read_docx_markdown", boom)
    result = drive_read.read_folder("F", client=_one_docx_walk(monkeypatch),
                                    deep_read_bases=True)
    assert result.accounted()
    assert len(result.skips) == 1
    assert result.skips[0].skip.mode == drive_read.READER_RAISED
