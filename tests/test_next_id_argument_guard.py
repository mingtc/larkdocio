"""LD-622 defect 1 — ``next-id.sh`` parsed NO arguments at all, so a mistyped flag was
silently ignored, the scan still ran, and the script **printed a real issue id on stdout
and exited 0**::

    $ ./scripts/next-id.sh --definitely-not-an-option
    LD-625
    $ echo $?
    0

This is the same class as LD-616's false ``board-drift: clean ✓`` — *an instrument
asserting something it never established* — but one step worse, because it has **a side
effect the caller acts on**: the id names a branch, a file and a commit. So the stdout
emptiness is pinned SEPARATELY from the exit code (AC2): handing out the id is the actual
defect, and a fix that changed only the exit code would leave the dangerous half intact.

**The convention is LD-616's, matched and not re-litigated** (see
``tests/test_check_board_argument_guard.py`` and ``scripts/check-board.sh``'s argv block):
**exit 2** for a read-only instrument a human runs by hand — the code
``scripts/verify.sh`` uses, deliberately NOT 1, which ``move-issue.sh`` /
``archive-progress.sh`` reserve for a MUTATING command — **usage on stderr**, **nothing on
stdout**, and ``--help``/``-h`` prints usage and exits 0.

What is NOT this issue's fix and stays as it was: ``next-id.sh`` gains no real flags (the
issue's Out of scope), and the bare no-argument run keeps its exact contract — one id on
stdout, exit 0, nothing on stderr — which the last test here pins against a disposable
scratch board so the guard proves the refusal did not touch the valid path.
"""
import pathlib
import subprocess

import pytest

# LD-640 AC4: the four shared assertions have ONE definition. What is next-id's own — the
# `LD-` absences, the stray-positional arm, the `--help` mention on stderr, and the valid-path
# arm — stays here, where it is that script's contract.
from argv_refusal_contract import (
    ArgvContract,
    UNKNOWN_ARG,
    assert_help_flag_exits_zero_with_usage,
    assert_unknown_argument_exits_with_the_refusal_code,
    assert_unknown_argument_names_itself_on_stderr,
    assert_unknown_argument_writes_NOTHING_to_stdout,
)
import private_tree  # noqa: E402  (LD-685)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "next-id.sh"

CONTRACT = ArgvContract(script=SCRIPT, timeout=30)
_run = CONTRACT.run


def _scratch_board(tmp_path):
    """A disposable board — never the real one — with a scripts/ copy so
    ``next-id.sh`` resolves the scratch tree as its repo root."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "next-id.sh").write_bytes(SCRIPT.read_bytes())
    (tmp_path / "scripts" / "config.sh").write_text(
        'ISSUE_PREFIX="LD"\n', encoding="utf-8"
    )
    (tmp_path / "progress" / "todo").mkdir(parents=True)
    (tmp_path / "progress" / "todo" / "LD-041-scratch.md").write_text(
        "---\nid: LD-041\n---\n", encoding="utf-8"
    )
    return tmp_path


# --------------------------------------------------------------------------- #
# AC2 — an unknown argument is refused BEFORE any work runs.
# --------------------------------------------------------------------------- #

@private_tree.kit
def test_unknown_argument_exits_two():
    assert_unknown_argument_exits_with_the_refusal_code(CONTRACT)


@private_tree.kit
def test_unknown_argument_usage_on_stderr():
    result = assert_unknown_argument_names_itself_on_stderr(CONTRACT)
    # next-id's own addition: the refusal points at the flag that IS accepted.
    assert "--help" in result.stderr


@private_tree.kit
def test_unknown_argument_hands_out_NO_id_on_stdout():
    """THE defect, pinned on its own: an id on stdout is a side effect the caller
    acts on — it becomes a branch name, a filename and a commit subject."""
    result = assert_unknown_argument_writes_NOTHING_to_stdout(CONTRACT)
    assert "LD-" not in result.stdout


@private_tree.kit
def test_a_stray_positional_is_refused_too():
    """Not only flags: ``next-id.sh 622`` (someone reaching for an argument the
    script never had) must refuse rather than print an unrelated id. next-id's own arm —
    ``UNKNOWN_ARG`` is a flag, and a bare positional is the other reach.
    """
    result = _run(["622"])
    assert result.returncode == 2
    assert result.stdout == ""
    assert "unknown arg" in result.stderr
    assert UNKNOWN_ARG not in result.stderr


# --------------------------------------------------------------------------- #
# AC2 — --help is not a mistake.
# --------------------------------------------------------------------------- #

@private_tree.kit
@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_flag_exits_zero_with_usage_and_no_id(flag):
    result = assert_help_flag_exits_zero_with_usage(CONTRACT, flag)
    # --help must not ALSO hand out an id: usage and a side effect is the same trap.
    assert "LD-0" not in result.stdout and "LD-6" not in result.stdout


# --------------------------------------------------------------------------- #
# The valid path is untouched.
# --------------------------------------------------------------------------- #

@private_tree.kit
def test_bare_run_still_suggests_the_next_id(tmp_path):
    scratch = _scratch_board(tmp_path)
    result = subprocess.run(
        ["bash", str(scratch / "scripts" / "next-id.sh")],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    assert result.stdout == "LD-042\n"
    assert result.stderr == ""
