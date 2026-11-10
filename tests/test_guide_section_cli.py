"""LD-228 — ``larkdocio guide --section`` reaches CLI parity with ``guide(section=…)``.

The flag is a **pass-through**: ``guide.py`` owns the naming rule, the boundary rule and the
refusal text, and this file's whole job is to pin that the CLI adds none of its own. Every
semantic assertion below is written as *the CLI equals the API for the same argument*, so the
two cannot drift; the only CLI-specific claims are the surfacing ones — stdout stays empty on a
refusal, the exit status is non-zero, and no traceback reaches the terminal.
"""

import subprocess

import private_tree  # noqa: E402  (LD-691)
import sys
from pathlib import Path

from click.testing import CliRunner

import larkdocio
from larkdocio.cli import cli
from larkdocio.guide import guide_sections
from domain_vocabulary import RETIRED_ID

REPO_ROOT = Path(__file__).resolve().parents[1]


def run(args):
    """Invoke the CLI with stdout and stderr kept separate."""
    return CliRunner().invoke(cli, args, catch_exceptions=True)


def _a_top_level_section():
    """A ``##`` row that actually has ``###`` children — so the nesting claim is not vacuous."""
    rows = guide_sections()
    for position, row in enumerate(rows):
        if row["level"] == 2 and position + 1 < len(rows) and rows[position + 1]["level"] == 3:
            return row, rows[position + 1]
    raise AssertionError("the shipped guide has no ## section with a ### child")


# --------------------------------------------------------------------------- #
# AC1 — the flag exists, is a pass-through, and the no-flag path is unchanged   #
# --------------------------------------------------------------------------- #

def test_ac1_the_section_option_exists_on_the_guide_command():
    option = next(
        (param for param in cli.commands["guide"].params if "--section" in param.opts), None
    )
    assert option is not None, "`larkdocio guide` has no --section option"
    assert not option.is_flag, "--section must take a value, not be a boolean flag"
    assert option.default is None
    assert option.opts == ["--section"], "no short alias is ruled; do not add one"


def test_ac1_no_section_is_BYTE_IDENTICAL_TO_THE_API_FOR_THE_SAME_ARGUMENTS():
    """The claim was "adding --section changed nothing about the bare command", and it was
    written as *the bare command equals ``guide()``*. The front-door swap moved what ``guide()``
    answers (the index, not the document) and the CLI moved with it, so the equality is the same
    equality — restated against the call it always compared to, plus the new ``--full`` pair."""
    for args, expected in ((["guide"], larkdocio.guide()),
                           (["guide", "--full"], larkdocio.guide(full=True))):
        result = run(args)
        assert result.exit_code == 0, result.output
        assert result.stdout == expected
        assert result.stderr == ""


def test_ac1_a_section_prints_the_APIs_bytes_with_no_added_trailing_newline():
    row, _child = _a_top_level_section()
    expected = larkdocio.guide(section=row["slug"])
    result = run(["guide", "--section", row["slug"]])
    assert result.exit_code == 0, result.output
    assert result.stdout == expected
    assert not result.stdout.endswith(expected + "\n")


def test_ac1_the_cli_writes_no_naming_or_boundary_logic_of_its_own():
    """The pass-through, read off the source: `cli.py` may name `guide(section=…)` and nothing
    else — no slugging, no heading scan, no section index."""
    source = (REPO_ROOT / "src" / "larkdocio" / "cli.py").read_text(encoding="utf-8")
    for forbidden in ("_slugify", "_section_text", "_bounded_sections", "guide_sections",
                      "GUIDE_SECTION_LEVELS", "startswith(\"#"):
        assert forbidden not in source, (
            f"cli.py re-implements guide.py's machinery ({forbidden!r}); the flag must be a "
            "pass-through"
        )


# --------------------------------------------------------------------------- #
# AC2 — the semantics are the API's                                             #
# --------------------------------------------------------------------------- #

def test_ac2_slug_heading_case_and_whitespace_all_reach_the_same_bytes():
    row, _child = _a_top_level_section()
    expected = larkdocio.guide(section=row["slug"])
    for spelling in (row["slug"], row["slug"].upper(), row["heading"],
                     row["heading"].upper(), f"  {row['slug']}  "):
        result = run(["guide", "--section", spelling])
        assert result.exit_code == 0, result.output
        assert result.stdout == expected, f"{spelling!r} did not reach the same section"
        assert result.stdout == larkdocio.guide(section=spelling), (
            "the CLI and the API disagree — the flag is no longer a pass-through"
        )


def test_ac2_a_top_level_name_INCLUDES_its_children_and_a_child_name_stops():
    parent, child = _a_top_level_section()
    parent_out = run(["guide", "--section", parent["slug"]]).stdout
    child_out = run(["guide", "--section", child["slug"]]).stdout
    assert child_out in parent_out, "the ## section does not contain its ### child"
    assert len(child_out) < len(parent_out)
    assert child_out.startswith("### ")
    assert child_out.count("\n## ") == 0, "the ### section ran past the next ##"
    assert child_out == larkdocio.guide(section=child["slug"])


def test_ac2_every_shipped_section_matches_the_api_exactly():
    for row in guide_sections():
        assert run(["guide", "--section", row["slug"]]).stdout == \
            larkdocio.guide(section=row["slug"]), f"{row['slug']} diverged"


# --------------------------------------------------------------------------- #
# AC3 — the unknown-section refusal is the API's, surfaced the CLI way          #
# --------------------------------------------------------------------------- #

def _api_refusal(name):
    try:
        larkdocio.guide(section=name)
    except ValueError as refusal:
        return str(refusal)
    raise AssertionError(f"{name!r} unexpectedly named a real section")


def test_ac3_an_unknown_section_refuses_with_the_APIs_OWN_MESSAGE_verbatim():
    result = run(["guide", "--section", "no-such-section-here"])
    assert result.exit_code != 0
    assert result.stdout == "", "a refusal wrote to stdout; a shell redirect is half-written"
    assert _api_refusal("no-such-section-here") in result.stderr
    assert "larkdocio.guide_sections()" in result.stderr
    assert str(len(guide_sections())) in result.stderr
    assert "Traceback (most recent call last)" not in result.stderr


def test_ac3_a_refusal_leaves_a_REDIRECTED_FILE_EMPTY(tmp_path):
    """The load-bearing property, in a real child process with a real shell redirect."""
    out = tmp_path / "out.md"
    with out.open("wb") as handle:
        proc = subprocess.run(
            [sys.executable, "-m", "larkdocio.cli", "guide", "--section", "typo"],
            cwd=str(tmp_path), stdout=handle, stderr=subprocess.PIPE,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO_ROOT / "src"),
                 "PYTHONDONTWRITEBYTECODE": "1"},
        )
    stderr = proc.stderr.decode("utf-8", "replace")
    assert proc.returncode != 0
    assert out.read_bytes() == b""
    assert "unknown section 'typo'" in stderr
    assert "Traceback (most recent call last)" not in stderr
    assert "ValueError" not in stderr, "the exception class name leaked into the message"


# --------------------------------------------------------------------------- #
# AC4 — the option's help text                                                  #
# --------------------------------------------------------------------------- #

def test_ac4_the_help_text_says_what_it_takes_what_comes_back_and_the_default():
    page = " ".join(run(["guide", "--help"]).stdout.split())
    assert "--section" in page
    for claim in ("heading", "slug", "case-insensitive", "whole guide"):
        assert claim in page, f"the --section help never says {claim!r}"
    assert "LD-" not in page and not RETIRED_ID.search(page), "internal dialect in a shipped help page"


# --------------------------------------------------------------------------- #
# AC5 / AC6 — the front door and the disclosure                                 #
# --------------------------------------------------------------------------- #

def test_ac5_the_falsified_live_sentences_are_gone_and_the_option_is_documented():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    tools = (REPO_ROOT / "TOOLS.md").read_text(encoding="utf-8")
    assert "Takes no options" not in readme
    assert "No options and no arguments." not in tools
    assert "--section" in readme, "the front-door guard's literal search target"
    assert "larkdocio guide --section" in tools


@private_tree.internal_log
def test_ac5_the_1_23_0_RELEASE_HISTORY_is_left_byte_untouched():
    for name in ("RELEASE_NOTES.md", "CHANGELOG.md"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        start = text.index("## [1.23.0]")
        end = text.index("## [1.22.0]")
        assert "--section" not in text[start:end], (
            f"{name}'s 1.23.0 section was edited; release history is immutable"
        )


@private_tree.internal_log
def test_ac6_the_disclosure_is_appended_to_the_existing_1_26_0_section():
    notes = (REPO_ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    notes_126 = notes[notes.index("## [1.26.0]"):notes.index("## [1.25.0]")]
    changelog_126 = changelog[changelog.index("## [1.26.0]"):changelog.index("## [1.25.0]")]
    capabilities = notes_126[notes_126.index("### New capabilities"):
                             notes_126.index("### Behavior changes you can observe")]
    assert "--section" in capabilities
    assert "None." not in capabilities, "the New capabilities placeholder was left in place"
    assert "--section" in changelog_126
    assert notes.count("## [1.26.0]") == 1 and changelog.count("## [1.26.0]") == 1
    for section in ("### New capabilities", "### Behavior changes you can observe",
                    "### Upgrade & compatibility", "### Known limitations"):
        assert section in notes_126
