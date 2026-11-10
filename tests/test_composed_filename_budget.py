"""LD-665 — the NAME that reaches the filesystem is budgeted, and a cut name stops
silently destroying a document.

LD-659 put the budget in bytes inside ``sanitize_path_string``. That closed the crash and it
could not close this, because the sanitizer budgets a *component* and cannot see two things:
what its callers wrap around that component, and the fact that a cut maps many titles onto one
name. Executed on the shipped tree of the day, with ``OutputConfig()`` defaults, into one
``-o``: two documents whose titles first differ past the cut produced **one** file, the second
truncating open destroying the first, with no error and no log line.

The legs below are in four groups:

* **the collision** (AC3) — the reproduction, asserted as two surviving files;
* **the budget** (AC2) — a boundary per site, at the limit and one codepoint past it, measured
  in **bytes**, asserting the extension survived;
* **the disclosure** (AC4) — the residual, equal-title case, which is a true fact about the
  user's Drive and is reported rather than renamed away;
* **the census** (AC5) — an AST walk, because a grep cannot support a negative claim.
"""
import ast
import logging
import pathlib
import re

import pytest

import private_tree

from larkdocio.common.filename import ComposedName, compose_name
from larkdocio.common.sanitize import (
    MAX_NAME_BYTES,
    MAX_NAME_CHARS,
    NAME_MAX_BYTES,
    sanitize_path_string,
    truncates,
)
from larkdocio.read.config import new_config
from larkdocio.read.download import _write_markdown

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"

#: A Lark document token as this tenant issues them: 27 characters. Used wherever a leg needs a
#: REALISTIC token rather than a three-letter stand-in, because the token's length is what the
#: composed name's worst case is a function of.
DOC_TOKEN = "doccn" + "A" * 22
FOLDER_TOKEN = "fldcn" + "B" * 22


# --------------------------------------------------------------------------- #
# AC3 — the collision                                                          #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("suffix_pair,label", [
    (("上册", "下册"), "cjk"),
    (("Alpha", "Beta"), "ascii"),
])
def test_two_documents_differing_only_PAST_the_cut_no_longer_share_one_file(
        tmp_path, suffix_pair, label):
    """The ``J`` transcript, both bands. It is parametrized over ASCII as well as CJK on
    purpose: the collision is **pre-existing** and has nothing to do with the byte budget —
    LD-659 only moved where the cut falls, and the ASCII arm is the one that has been live
    since the 100-character ceiling was written.
    """
    stem = "文" * 100 if label == "cjk" else "x" * 100
    first = _write_markdown(new_config(), str(tmp_path), DOC_TOKEN,
                            stem + suffix_pair[0], "# DOC A\n")
    second = _write_markdown(new_config(), str(tmp_path), "doccn" + "Z" * 22,
                             stem + suffix_pair[1], "# DOC B\n")

    assert str(first) != str(second)
    written = sorted(tmp_path.glob("*.md"))
    assert len(written) == 2, [p.name for p in written]
    assert {p.read_text(encoding="utf-8") for p in written} == {"# DOC A\n", "# DOC B\n"}
    # And BOTH still fit: the room for the token came out of the title, not out of the ceiling.
    for path in written:
        assert len(path.name.encode("utf-8")) <= NAME_MAX_BYTES


def test_the_same_document_downloaded_twice_still_overwrites_ITS_OWN_file(tmp_path):
    """The other half of AC3, and the reason the disambiguator is the object's own token rather
    than a counter or a clock: a counter would accumulate copies of one document and break
    every consumer that depends on the path being stable."""
    long_title = "文" * 120
    first = _write_markdown(new_config(), str(tmp_path), DOC_TOKEN, long_title, "# v1\n")
    second = _write_markdown(new_config(), str(tmp_path), DOC_TOKEN, long_title, "# v2\n")

    assert str(first) == str(second)
    assert [p.name for p in tmp_path.glob("*.md")] == [pathlib.Path(first).name]
    assert pathlib.Path(second).read_text(encoding="utf-8") == "# v2\n"


def test_the_disambiguating_token_is_never_itself_cut(tmp_path):
    """Uniqueness lives in the token, so the token is the one part that must survive whole. A
    fix that budgeted by slicing the finished name would eat the token's tail (and the ``.md``
    with it) and re-open the collision it was written to close."""
    written = pathlib.Path(
        _write_markdown(new_config(), str(tmp_path), DOC_TOKEN, "文" * 250, "x"))
    assert written.name.endswith(f"_{DOC_TOKEN}.md")


def test_a_name_that_FITS_is_byte_identical_to_what_shipped(tmp_path):
    """The disambiguation is conditional on the cut, and this is the leg that pins it. Nothing
    about an ordinary title's filename moves — which is what makes this a fix for a collision
    rather than a rename of every consumer's outputs."""
    for title in ("My Doc", "SPEC-001_v2", "a" * MAX_NAME_CHARS, "文" * 70):
        written = pathlib.Path(
            _write_markdown(new_config(), str(tmp_path), DOC_TOKEN, title, "x"))
        assert written.name.endswith(f"_{sanitize_path_string(title)}.md")
        assert DOC_TOKEN not in written.name


# --------------------------------------------------------------------------- #
# AC2 — the budget, per site, at the boundary                                  #
# --------------------------------------------------------------------------- #

def test_the_download_name_at_the_boundary_and_one_codepoint_past_it(tmp_path):
    """Site 1 (``_write_markdown``). ``[%Y-%m-%d_%H%M]_`` + ``.md`` is 21 bytes of fixed
    decoration; the boundary walked here is the CHARACTER ceiling, which is what bites first
    for a title of any width once LD-659's byte ceiling is 223."""
    at = pathlib.Path(_write_markdown(
        new_config(), str(tmp_path), DOC_TOKEN, "a" * MAX_NAME_CHARS, "x"))
    past = pathlib.Path(_write_markdown(
        new_config(), str(tmp_path), DOC_TOKEN, "a" * (MAX_NAME_CHARS + 1), "x"))

    assert at.name.endswith(".md") and past.name.endswith(".md")
    assert at.name != past.name          # one codepoint past the cut is a DIFFERENT file
    assert DOC_TOKEN not in at.name      # at the limit nothing was cut
    assert DOC_TOKEN in past.name        # one past it, the cut bit and the token joined
    for path in (at, past):
        assert len(path.name.encode("utf-8")) <= NAME_MAX_BYTES


def _run_folder_command(monkeypatch, out_dir, *, token, name):
    """The real ``handle_folder_command``, with only the network read replaced. Everything
    this issue is about — the composition, the existence check, the write — is executed."""
    from larkdocio.drive import folder_cmd, read as drive_read
    from larkdocio.drive.models import FolderName, FolderWalk

    result = drive_read.FolderRead(
        root_token=token, root_name=FolderName(token=token, name=name),
        walk=FolderWalk(root_token=token, children=()), outcomes=())
    monkeypatch.setattr(folder_cmd, "read_folder", lambda url, **kw: result)
    monkeypatch.setattr(folder_cmd, "init_env", lambda env_file=None: None)
    monkeypatch.setattr(folder_cmd, "render_folder", lambda r: f"# {r.root_token}\n")
    folder_cmd.handle_folder_command("https://x.larksuite.com/drive/folder/F", str(out_dir))


def test_two_FOLDERS_differing_only_past_the_cut_no_longer_share_one_file(
        monkeypatch, tmp_path):
    """Site 2's own reproduction, executed through the shipped command. This site is the
    sharper of the two: it composes **no timestamp at all**, so two folders converging on one
    name collided at any distance in time, not only inside one clock minute."""
    _run_folder_command(monkeypatch, tmp_path, token="fldcnAAA", name="文" * 100 + "上册")
    _run_folder_command(monkeypatch, tmp_path, token="fldcnBBB", name="文" * 100 + "下册")

    written = sorted(tmp_path.glob("*.md"))
    assert len(written) == 2, [p.name for p in written]
    assert {p.read_text(encoding="utf-8") for p in written} == {"# fldcnAAA\n", "# fldcnBBB\n"}
    for path in written:
        assert len(path.name.encode("utf-8")) <= NAME_MAX_BYTES


def test_the_same_FOLDER_read_twice_still_overwrites_its_own_file_and_says_so(
        monkeypatch, tmp_path, caplog):
    """Folder's half of AC4. The disclosure here is log-only and that asymmetry with
    ``download`` is deliberate — this command's contract is ``-> None``, so there is no result
    object to carry a field on, and giving it one is a surface change LD-665 does not own."""
    _run_folder_command(monkeypatch, tmp_path, token="fldcnAAA", name="Marketing")
    with caplog.at_level(logging.INFO, logger="larkdocio"):
        _run_folder_command(monkeypatch, tmp_path, token="fldcnAAA", name="Marketing")

    assert [p.name for p in tmp_path.glob("*.md")] == ["Marketing.md"]
    assert any("was replaced" in record.getMessage() for record in caplog.records)


def test_an_ordinary_FOLDER_name_is_byte_identical_to_what_shipped(monkeypatch, tmp_path):
    _run_folder_command(monkeypatch, tmp_path, token="fldcnAAA", name="Q3 Planning")
    assert [p.name for p in tmp_path.glob("*.md")] == ["Q3_Planning.md"]


def test_the_folder_name_at_the_boundary_and_one_codepoint_past_it():
    """Site 2 (``drive.folder_cmd``). Composed through the same seam the command calls, with
    the command's own fixed parts — no prefix at all, which is precisely why this site
    collided at ANY distance in time rather than only inside one clock minute."""
    at = compose_name("文" * 74, suffix=".md", token=FOLDER_TOKEN)
    past = compose_name("文" * 75, suffix=".md", token=FOLDER_TOKEN)

    assert at.name.endswith(".md") and past.name.endswith(".md")
    assert at.name != past.name
    assert (at.truncated, past.truncated) == (False, True)
    for composed in (at, past):
        assert len(composed.name.encode("utf-8")) <= NAME_MAX_BYTES


@pytest.mark.parametrize("width,token", [
    ("文", DOC_TOKEN), ("a", DOC_TOKEN), ("文", "t"), ("a", "t"),
])
def test_the_composed_name_is_under_NAME_MAX_in_BYTES_for_every_width(width, token):
    """The limit is bytes, not characters — the whole of LD-659 and the half of LD-665 that is
    arithmetic. The stem is generated well past any ceiling in both widths."""
    composed = compose_name(width * 400, prefix="[2026-09-09_1200]_", suffix=".md", token=token)
    assert len(composed.name.encode("utf-8")) <= NAME_MAX_BYTES
    assert composed.name.endswith(".md")
    # Nothing partial came out of the cut: what was written decodes back to itself.
    assert composed.name.encode("utf-8").decode("utf-8") == composed.name


def test_the_stem_gives_up_the_bytes_and_the_FIXED_parts_never_do():
    """Trap (i) of AC2, stated as a test: a naive slice of the finished name eats the ``.md``.
    Here the token is long enough to force a hard squeeze and the extension still survives."""
    composed = compose_name("文" * 400, prefix="[2026-09-09_1200]_", suffix=".md",
                            token="T" * 200)
    assert composed.name.startswith("[2026-09-09_1200]_")
    assert composed.name.endswith(f"{'T' * 200}.md")


def test_the_worst_case_composed_download_name_is_MEASURED_not_asserted(tmp_path):
    """The number LD-665's handoff states, produced by the instrument that produces the name.

    Stated as a bound rather than a literal on purpose: a hand-typed figure in a test is the
    same defect as a hand-typed figure in prose. What is pinned is that the worst case a real
    call site can reach is under the ceiling, with a realistic 27-character Lark token.
    """
    worst = max(
        len(pathlib.Path(_write_markdown(
            new_config(), str(tmp_path), DOC_TOKEN, width * 400, "x")).name.encode("utf-8"))
        for width in ("文", "a")
    )
    assert worst <= NAME_MAX_BYTES
    # Non-vacuity: a bound nothing approaches would pass while measuring nothing.
    assert worst > NAME_MAX_BYTES - 8


@private_tree.internal_log
def test_the_changelog_note_quotes_the_MEASURED_worst_case(tmp_path):
    """Split out of the test above by LD-691, not weakened: the note it holds is an entry in the
    INTERNAL engineering log, which no longer ships in the wheel (the packaged changelog is the
    public one, maintainer ruling 2), so it reads the root ``CHANGELOG.md`` and runs where that log is."""
    worst = max(
        len(pathlib.Path(_write_markdown(
            new_config(), str(tmp_path), DOC_TOKEN, width * 400, "x")).name.encode("utf-8"))
        for width in ("文", "a")
    )
    # The note quotes this measurement rather than a hand-typed figure. Eleven
    # numbers were wrong in one session on this repo and the only one that reached a packaged
    # document was typed by hand, so the two figures the CHANGELOG states about this change are
    # held to the instruments that produce them. `MAX_NAME_BYTES` is imported, not retyped.
    # Whitespace-flattened before matching: the note is wrapped prose, so a phrase that
    # straddles a line break is the same claim and a line-sensitive match would fail on a
    # re-wrap rather than on a wrong number.
    changelog = " ".join((pathlib.Path(__file__).resolve().parent.parent
                          / "CHANGELOG.md")
                         .read_text(encoding="utf-8").split())
    assert f"**{worst} bytes** with a real" in changelog, (
        f"the CHANGELOG does not state the measured worst case of {worst} bytes")
    assert f"component budget of **{MAX_NAME_BYTES} bytes**" in changelog


# --------------------------------------------------------------------------- #
# AC4 — the residual collision is disclosed, not renamed away                  #
# --------------------------------------------------------------------------- #

def test_two_documents_that_GENUINELY_share_a_title_still_share_a_name_and_say_so(
        tmp_path, caplog):
    """The ``K`` transcript. No truncation happened, so the name is faithful and the collision
    is a true fact about the user's Drive (``drive/assets.py`` records that this tenant's own
    root folder holds two documents both named ``Example Pre-existing Document``). Renaming
    behind the caller here would substitute this library's guess for their reality; the duty is to SAY SO."""
    first = _write_markdown(new_config(), str(tmp_path), DOC_TOKEN,
                            "Example Pre-existing Document", "# A\n")
    with caplog.at_level(logging.INFO, logger="larkdocio"):
        second = _write_markdown(new_config(), str(tmp_path), "doccn" + "Z" * 22,
                                 "Example Pre-existing Document", "# B\n")

    assert str(first) == str(second)
    assert first.replaced_existing is False
    assert second.replaced_existing is True
    assert second.disambiguated is False
    assert any("was replaced" in record.getMessage() for record in caplog.records)


def test_the_disclosure_is_SILENT_when_nothing_was_replaced(tmp_path, caplog):
    """Red-watch for the leg above, and the anti-noise arm: a disclosure that fires on every
    run is not a disclosure."""
    with caplog.at_level(logging.INFO, logger="larkdocio"):
        written = _write_markdown(new_config(), str(tmp_path), DOC_TOKEN, "Solo", "# A\n")
    assert written.replaced_existing is False
    assert not any("was replaced" in record.getMessage() for record in caplog.records)


def test_the_written_path_is_still_a_plain_string_to_every_existing_caller(tmp_path):
    """``_write_markdown``'s return type carries two attributes now. It is a ``str`` subclass
    so that this stays true — ten existing tests and every in-process caller treat it as the
    path it is."""
    written = _write_markdown(new_config(), str(tmp_path), DOC_TOKEN, "My Doc", "# A\n")
    assert isinstance(written, str)
    assert written == str(written) == str(tmp_path / pathlib.Path(written).name)
    assert pathlib.Path(written).read_text(encoding="utf-8") == "# A\n"


# --------------------------------------------------------------------------- #
# AC5 — the census, as the guard                                               #
# --------------------------------------------------------------------------- #
#
# INSTRUMENT: `ast`, over the real `src/**` tree. A grep cannot support this claim and this
# repo has published three errors from trying — a negative claim ("no OTHER site composes a
# filename from document text") needs a parse or an execution, because a grep cannot tell an
# f-string from the prose describing one, cannot see through a name binding, and cannot know
# whether the string it matched is a path or a message. The population below is derived from
# the parse tree; the classification is the only hand-kept part, and an undeclared site fails.

#: An f-string whose constant parts end in a filesystem extension — i.e. one that composes a
#: filename. Deliberately shape-based rather than a list of extensions this library happens to
#: write today, so a new one is caught rather than skipped.
_EXTENSION = re.compile(r"\.[A-Za-z0-9]{2,4}$")

#: Every filename-composing f-string in ``src/**``, classified. **Keyed by the f-string
#: itself** (module, enclosing function, and the expression as :func:`ast.unparse` renders it),
#: not by the function — and that granularity was bought with a failed red-watch, not chosen on
#: taste. Keyed by function alone, the first version of this table passed while a freshly
#: injected ``f"{title}.md"`` sat inside ``_write_markdown``, because that function was already
#: declared for a *different* composition. Green while unable to look is the one failure a
#: census guard cannot be allowed to have, so the key is the composition.
#:
#: The price is that renaming a local variable inside one of these f-strings reddens this table
#: and costs a one-line edit. That is the intended trade: the alternative made a new
#: composition invisible.
#:
#: The classes:
#:
#: * ``text-derived`` — the stem comes from document-supplied text (a title, a folder name), so
#:   it can be CUT and can therefore collide. **These must live in the composition seam**, and
#:   the leg below asserts exactly that rather than trusting the label;
#: * ``token-derived`` — built from a Lark-issued identifier, which carries no budget and is not
#:   owed one (``drive/assets.py`` records the argument, LD-665 scopes them out with it);
#: * ``citation`` — a path to evidence in the dev repo, read never written;
#: * ``archive-member`` — a member path inside a zip container, not a filesystem name.
DECLARED_COMPOSITIONS = {
    ("larkdocio/common/filename.py", "compose_name",
     "f'{prefix}{stem}{suffix}'"): "text-derived",
    ("larkdocio/common/filename.py", "compose_name",
     "f'{prefix}{stem}{marker}{suffix}'"): "text-derived",
    ("larkdocio/common/filename.py", "compose_name",
     "f'{prefix}{token}{suffix}'"): "text-derived",
    ("larkdocio/common/filename.py", "compose_name", "f'_{token}'"): "text-derived",
    ("larkdocio/common/filename.py", "compose_name",
     "f'{prefix}{marker}{suffix}'"): "text-derived",
    ("larkdocio/read/download.py", "_write_markdown", "f'{doc_token}.md'"): "token-derived",
    ("larkdocio/read/download.py", "_write_markdown",
     "f'[{now_str}]_{doc_token}.md'"): "token-derived",
    ("larkdocio/read/download.py", "_dump_json", "f'{doc_token}.json'"): "token-derived",
    ("larkdocio/drive/folder_cmd.py", "_dump_manifest",
     "f'{result.root_token}.json'"): "token-derived",
    ("larkdocio/read/client.py", "download_image", "f'{img_token}.png'"): "token-derived",
    ("larkdocio/read/client.py", "download_board_image",
     "f'{whiteboard_id}.png'"): "token-derived",
    ("larkdocio/base/loss_preview.py", "field_delete_loss",
     "f'{_CAPTURES}/06-06-destructive-ops.json'"): "citation",
    ("larkdocio/base/loss_preview.py", "field_delete_loss",
     "f'{_CAPTURES}/p0-2-07-link-deletion-behaviour.json'"): "citation",
    ("larkdocio/base/loss_preview.py", "field_delete_loss",
     "f'{_CAPTURES}/p0-5-02-symmetric-link-deletion.json'"): "citation",
    ("larkdocio/base/loss_preview.py", "select_option_shrink_loss",
     "f'{_CAPTURES}/ld462-01-select-option-shrink.json'"): "citation",
    ("larkdocio/base/loss_preview.py", "select_option_shrink_loss",
     "f'{_CAPTURES}/ld339-01-select-option-id-remint.json'"): "citation",
    ("larkdocio/base/loss_preview.py", "table_delete_loss",
     "f'{_CAPTURES}/p0-5-02-symmetric-link-deletion.json'"): "citation",
    ("larkdocio/base/loss_preview.py", "table_delete_loss",
     "f'{_CAPTURES}/06-06-destructive-ops.json'"): "citation",
    ("larkdocio/sheets/export_reader.py", "_resolve_sheets",
     "f'xl/worksheets/sheet{i + 1}.xml'"): "archive-member",
}

#: The one module allowed to compose a name from document-supplied text.
SEAM = "larkdocio/common/filename.py"


def filename_compositions():
    """``{(relative path, enclosing function, the f-string)}`` for every filename-composing
    f-string in
    ``src/**`` — derived by :mod:`ast`, never imported and never hand-listed.

    **Two rules, and the second one is not padding.** Everywhere else a composition is
    recognised by SHAPE — the constant parts end in an extension. Inside the seam that test is
    structurally blind: the seam's whole job is that the extension is its CALLER's
    (``f"{prefix}{stem}{suffix}"``), so it has no constant extension to match and the
    shape-based walk cannot see the one site that matters most. Left that way, the
    ``text-derived`` class below would be hand-asserted rather than derived — a guard green
    because it could not look, which is the failure this file exists to prevent elsewhere. So
    the seam module contributes every f-string it builds, by module.
    """
    found = set()
    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(function):
                if not isinstance(node, ast.JoinedStr):
                    continue
                if not any(isinstance(p, ast.FormattedValue) for p in node.values):
                    continue
                constants = "".join(
                    p.value for p in node.values
                    if isinstance(p, ast.Constant) and isinstance(p.value, str)
                )
                if relative == SEAM or _EXTENSION.search(constants):
                    found.add((relative, function.name, ast.unparse(node)))
    return found


def test_every_filename_composition_in_src_is_declared():
    """**Red-watch:** add ``os.path.join(out, f"{title}.md")`` anywhere under ``src/`` and this
    fails as an undeclared site. Non-empty first: a walk that found nothing would pass every
    other leg in this section while checking the empty set."""
    sites = filename_compositions()
    assert sites, "the AST walk found no filename composition at all — the walk is broken"
    assert sites == set(DECLARED_COMPOSITIONS)


def test_only_the_SEAM_composes_a_name_from_document_supplied_text():
    """The claim AC5 is actually about. The label in the table is not trusted: a site declared
    ``text-derived`` outside the seam fails here, which is the shape the two fixed sites had
    before this change."""
    outside = [
        key for key, kind in DECLARED_COMPOSITIONS.items()
        if kind == "text-derived" and key[0] != SEAM
    ]
    assert outside == [], outside
    # And the seam is really in the WALKED population — a class whose only member is a table
    # row nothing derived would be a guard gone quiet.
    inside = {key for key, kind in DECLARED_COMPOSITIONS.items() if kind == "text-derived"}
    assert inside, "no text-derived site declared at all"
    assert inside <= filename_compositions()


def test_the_two_fixed_call_sites_really_go_THROUGH_the_seam():
    """The other direction, and the one that catches a site that stops calling the seam without
    adding an f-string of its own — e.g. by building the name with ``+`` or ``str.join``. AST
    again: the call has to be there in the parse tree of the writing function itself."""
    for module, function in (("larkdocio/read/download.py", "_write_markdown"),
                             ("larkdocio/drive/folder_cmd.py", "handle_folder_command")):
        tree = ast.parse((SRC / module).read_text(encoding="utf-8"))
        target = next(
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function
        )
        assert any(
            isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
            and call.func.id == "compose_name"
            for call in ast.walk(target)
        ), f"{module}::{function} no longer composes its filename through the seam"


def test_the_seam_answers_with_the_DECISION_and_not_just_a_string():
    """A helper that returned a bare ``str`` could not have told ``DownloadResult`` that the
    name was disambiguated, and the fact would have had to be re-derived (or logged)."""
    composed = compose_name("文" * 400, suffix=".md", token=DOC_TOKEN)
    assert isinstance(composed, ComposedName)
    assert (composed.truncated, composed.disambiguated) == (True, True)
    assert truncates("文" * 400) is True
    assert truncates("My Doc") is False
    # A name that is REDUCED but not cut is not a truncation — spaces became underscores.
    assert sanitize_path_string("My Doc") != "My Doc"
