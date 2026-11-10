"""LD-327 (the Drive spec § F1-S5 / § D2) — the CLI shape for the folder read.

The commission delegated the CLI shape to Dev with a maintainer-review line, and the recorded
decision is **(a) a new ``folder`` verb**, paired with ``download`` refusing a folder URL by
**naming** the verb that handles it. This module pins both halves offline:

* the ``folder`` verb reads a folder and writes the one rendered Markdown document under ``-o``,
  the on-disk shape the library deliberately leaves to the CLI (D5 / LD-326's ``read.py`` note);
* ``download`` refuses a ``/drive/folder/`` URL with a message that routes to ``folder`` rather
  than merely refusing — the § D2 recommendation, and the ``common/url.py`` routing stance.

The network is faked at the ``read_folder`` seam: the handler is the on-disk wiring, not the
enumeration, which has its own offline suite (``test_drive_read_folder.py``).
"""
import pathlib
import re

from click.testing import CliRunner

from larkdocio.cli import cli
from larkdocio.drive import folder_cmd
from larkdocio.drive.models import FolderChild, FolderName, FolderWalk, WalkedChild
from larkdocio.drive.read import READ, SKIPPED, ChildOutcome, FolderRead, SkipDisclosure


def _fake_folder_read():
    """A tiny two-child folder: one docx read, one ``file`` disclosed — the invariant shape."""
    doc = FolderChild(token="docxTOKEN", name="A doc", type="docx", url="https://x.larksuite.com/docx/docxTOKEN")
    raw = FolderChild(token="fileTOKEN", name="raw.yaml", type="file", url=None)
    walk = FolderWalk(
        root_token="fldrTOKEN",
        children=(WalkedChild(child=doc, depth=1, path="/A doc"),
                  WalkedChild(child=raw, depth=1, path="/raw.yaml")),
    )
    outcomes = (
        ChildOutcome(WalkedChild(child=doc, depth=1, path="/A doc"), READ,
                     surface="docx", markdown="# A doc\n\nbody"),
        ChildOutcome(WalkedChild(child=raw, depth=1, path="/raw.yaml"), SKIPPED,
                     surface=None,
                     skip=SkipDisclosure(mode="no-reader", reason="ships no reader for raw bytes")),
    )
    return FolderRead(root_token="fldrTOKEN",
                      root_name=FolderName(token="fldrTOKEN", name="My Folder"),
                      walk=walk, outcomes=outcomes)


def test_folder_verb_exists_on_the_cli():
    assert "folder" in cli.commands, "the `folder` verb is not registered on the CLI group"


def test_folder_verb_reads_a_folder_and_writes_one_markdown_document(tmp_path, monkeypatch):
    seen = {}

    def fake_read_folder(url, **kwargs):
        seen["url"] = url
        return _fake_folder_read()

    monkeypatch.setattr(folder_cmd, "read_folder", fake_read_folder)
    monkeypatch.setattr(folder_cmd, "init_env", lambda env_file=None: str(env_file))

    out = tmp_path / "out"
    result = CliRunner().invoke(
        cli, ["folder", "https://x.larksuite.com/drive/folder/fldrTOKEN", "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert seen["url"] == "https://x.larksuite.com/drive/folder/fldrTOKEN"

    written = list(out.glob("*.md"))
    assert len(written) == 1, f"expected exactly one .md, got {written}"
    text = written[0].read_text(encoding="utf-8")
    # the rendered doc carries the tree index, the read child, and the disclosure section
    assert "# My Folder" in text
    assert "## Folder tree" in text
    assert "# A doc" in text
    assert "## Not read" in text
    assert "raw.yaml" in text


def test_folder_verb_writes_nothing_and_exits_nonzero_when_read_folder_refuses(tmp_path, monkeypatch):
    from larkdocio.errors import LarkConfigError

    def boom(url, **kwargs):
        raise LarkConfigError("no READ credentials resolved")

    monkeypatch.setattr(folder_cmd, "read_folder", boom)
    monkeypatch.setattr(folder_cmd, "init_env", lambda env_file=None: str(env_file))
    out = tmp_path / "out"
    result = CliRunner().invoke(
        cli, ["folder", "https://x.larksuite.com/drive/folder/fldrTOKEN", "-o", str(out)])
    assert result.exit_code != 0
    assert "no READ credentials" in result.output
    assert not out.exists() or not list(out.glob("*.md"))


def test_download_refuses_a_folder_url_by_NAMING_the_folder_verb():
    """§ D2: a refusal that ROUTES rather than merely refuses — it names the verb that handles
    a folder URL, the ``common/url.py`` routing stance one layer down."""
    from larkdocio.read.download import _NON_DOCUMENT_URL_MESSAGES

    message = _NON_DOCUMENT_URL_MESSAGES["drive"]
    assert "folder" in message.lower()
    # the routing target is named, as a runnable verb
    assert "larkdocio folder" in message
    # and it no longer claims the read is unshipped
    assert "no folder read has shipped" not in message


def test_the_INVALID_URL_refusal_that_ACTUALLY_RENDERS_does_not_deny_the_folder_read():
    """**LD-658 AC2.** The guard above pins the message ``download`` raises for a *recognised*
    folder url. It is not the message a user with a folder link most often meets: mistype the
    host and the url is not recognised at all, and then ``common/url.py``'s
    ``_INVALID_URL_MESSAGE`` renders — from **both** of its raise sites — and that one still
    ended *"no folder read has shipped yet"*. So the sibling was guarded and the renderer was
    not, and a user holding a working folder link was told the feature does not exist.

    Derived, not hand-copied: the string is read off the module, and the capability it must not
    deny is read off ``drive.__all__`` plus the real click verb.
    """
    import click

    from larkdocio import drive
    from larkdocio.cli import cli
    from larkdocio.common import url as url_mod

    message = url_mod._INVALID_URL_MESSAGE
    # the capability the clause denied is real, in both doors, derived from the code:
    assert "read_folder" in drive.__all__
    folder_verb = cli.commands["folder"]
    assert isinstance(folder_verb, click.Command)
    # ...so the renderer may not deny it, and must route to one of the two real doors.
    assert "no folder read has shipped" not in message, (
        "the RENDERING refusal still denies a capability the wheel ships — "
        f"`larkdocio {folder_verb.name}` and `drive.read_folder`")
    assert "larkdocio folder" in message or "read_folder" in message, (
        "a folder url is refused here without naming either door that reads one")
    # the true half of the old clause is KEPT: this parser reports a type, it does not follow.
    assert "not followed" in message


#: ``Readme/Release for <label>`` — the pointer shape two shipped refusals used. The label may
#: carry interior dots (a filename) but never a trailing one, so sentence punctuation is not
#: mistaken for part of the destination.
_RELEASE_POINTER_RE = re.compile(
    r"Readme/Release for ([A-Za-z0-9_\-]+(?:\.[A-Za-z0-9_\-]+)*)")


def _release_pointer_labels():
    """Every ``Readme/Release for <label>`` destination named in a shipped refusal — DERIVED by
    a walk of ``src/**/*.py``, so a new dangling pointer is found without being listed here."""
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "larkdocio"
    found = {}
    for path in sorted(root.rglob("*.py")):
        for label in _RELEASE_POINTER_RE.findall(path.read_text(encoding="utf-8")):
            found.setdefault(label, []).append(str(path.relative_to(root.parent.parent)))
    return found


def test_a_refusal_pointing_at_the_README_or_RELEASE_names_something_they_CARRY():
    """**LD-658 AC2, second half.** Two refusals sent the reader to *"the Readme/Release for
    ``v1_support``"* — a label that appears in **zero** shipped documents, so the pointer had no
    destination. The population is derived by a walk (helper above) rather than listed, and each
    label must resolve in the shipped corpus that the pointer names.
    """
    import consumer_text

    shipped = list(consumer_text.shipped_docs().values())
    assert shipped, "the shipped-doc corpus is empty — this guard would be vacuous"

    unresolved = {label: sites for label, sites in _release_pointer_labels().items()
                  if not any(label in text for text in shipped)}
    assert unresolved == {}, (
        "a shipped refusal points at a Readme/Release section no shipped document carries: "
        f"{unresolved}")


def test_the_release_pointer_guard_BITES_on_a_synthetic_dangling_pointer():
    """The population above is (correctly) empty once AC2 lands, and an empty population makes
    a corpus guard go **quiet, not red**. So the matcher is exercised over synthetic text — the
    SAME compiled object the walk uses, not a retyped copy."""
    assert _RELEASE_POINTER_RE.findall(
        'raise ValueError("x is no longer supported. Please refer to the Readme/Release '
        'for v1_support.")') == ["v1_support"]
    assert _RELEASE_POINTER_RE.findall(
        "see the Readme/Release for RELEASE_NOTES.md") == ["RELEASE_NOTES.md"]
    assert _RELEASE_POINTER_RE.findall("nothing to see here") == []


# --------------------------------------------------------------------------- #
# LD-381 — `folder --dump`: the machine-readable child manifest.                #
#                                                                              #
# The convention is `download --dump`'s, deliberately reused rather than        #
# reinvented: same flag spelling, the sidecar lands in the same `-o` directory  #
# as the human output, and it is named for the TOKEN (not the title) so a       #
# ledger can find it without knowing what the folder is called.                 #
# --------------------------------------------------------------------------- #

def _run_folder(tmp_path, monkeypatch, *extra):
    def fake_read_folder(url, **kwargs):
        return _fake_folder_read()

    monkeypatch.setattr(folder_cmd, "read_folder", fake_read_folder)
    monkeypatch.setattr(folder_cmd, "init_env", lambda env_file=None: str(env_file))
    out = tmp_path / "out"
    result = CliRunner().invoke(
        cli, ["folder", "https://x.larksuite.com/drive/folder/fldrTOKEN",
              "-o", str(out), *extra])
    assert result.exit_code == 0, result.output
    return out


def test_folder_dump_writes_the_sidecar_next_to_the_markdown(tmp_path, monkeypatch):
    import json

    out = _run_folder(tmp_path, monkeypatch, "--dump")
    sidecar = out / "fldrTOKEN.json"
    assert sidecar.exists(), f"expected fldrTOKEN.json, got {sorted(p.name for p in out.iterdir())}"

    manifest = json.loads(sidecar.read_text(encoding="utf-8"))
    assert manifest["folder"] == {
        "token": "fldrTOKEN", "title": "My Folder", "title_disclosure": None}
    assert [(row["title"], row["token"], row["type"]) for row in manifest["children"]] == [
        ("A doc", "docxTOKEN", "docx"), ("raw.yaml", "fileTOKEN", "file")]
    assert all("revision" in row for row in manifest["children"])


def test_folder_dump_follows_download_dumps_naming_convention(tmp_path, monkeypatch):
    """`download --dump` writes ``<doc_token>.json`` into ``-o``; the folder sidecar writes
    ``<root_token>.json`` into ``-o``. One grammar, not two."""
    out = _run_folder(tmp_path, monkeypatch, "--dump")
    assert sorted(p.name for p in out.iterdir()) == ["My_Folder.md", "fldrTOKEN.json"]


def test_folder_without_dump_writes_NO_sidecar(tmp_path, monkeypatch):
    out = _run_folder(tmp_path, monkeypatch)
    assert list(out.glob("*.json")) == []


def test_the_dump_flag_leaves_the_human_output_byte_identical(tmp_path, monkeypatch):
    """AC4: the sidecar is purely additive — the Markdown a human reads does not move."""
    plain = _run_folder(tmp_path / "a", monkeypatch)
    dumped = _run_folder(tmp_path / "b", monkeypatch, "--dump")
    assert (dumped / "My_Folder.md").read_bytes() == (plain / "My_Folder.md").read_bytes()


def test_the_folder_verb_advertises_dump_in_its_help():
    result = CliRunner().invoke(cli, ["folder", "--help"])
    assert result.exit_code == 0
    assert "--dump" in result.output


def test_two_dumps_of_one_folder_read_are_byte_identical(tmp_path, monkeypatch):
    first = _run_folder(tmp_path / "1", monkeypatch, "--dump") / "fldrTOKEN.json"
    second = _run_folder(tmp_path / "2", monkeypatch, "--dump") / "fldrTOKEN.json"
    assert first.read_bytes() == second.read_bytes()
