"""LD-616 — ``check-board.sh`` parsed NO arguments at all, so a mistyped flag was
silently ignored, the normal sweep still ran, and the run printed
``── board-drift: clean ✓`` at exit 0 — a command that did not do what was asked was
indistinguishable from success.

**What is NOT this issue's fix, and stays exactly as it was:** ``exit 0`` on FINDINGS
(a valid run with drift) is deliberate — see ``scripts/check-board.sh``'s own
"CONVENTION: exit 0 ALWAYS (informational)" header comment and its closing verdict
line. This file does not touch that; it only adds a refusal for an argv the script
never accepted in the first place.

Four things are pinned here, matching the issue's AC:

* an unknown argument is refused with a NON-ZERO exit, a usage message on STDERR, and
  **no stdout at all** — so an operator grepping stdout for ``clean ✓`` can never get
  a false match from a run that never happened (AC2);
* ``--help``/``-h`` is not a mistake: it prints usage and exits 0 (AC3);
* a bare, no-argument run is UNCHANGED — same exit 0, same verdict line — on both a
  clean scratch board and one with a constructed finding, proving the argument guard
  didn't touch the valid path (AC4). The report is run against a disposable scratch
  ``CLAUDE_PROJECT_DIR``, never the real board, and the live timestamp line
  (``@ %Y-%m-%dT%H:%M:%S``) is the one line the assertions deliberately don't pin —
  everything else (headers, per-check verdicts, the closing line) must match exactly;
* the exit code chosen for the refusal is **2**, matching ``scripts/verify.sh``'s
  unknown-arg idiom (the closest sibling in kind: both are read-only reporting
  instruments a human runs by hand) and NOT 1 (``move-issue.sh`` /
  ``archive-progress.sh``'s code, reserved for a MUTATING command) (AC5).
"""
import pathlib

import pytest

# LD-640 AC4: the four shared assertions have ONE definition. What is check-board's own —
# every `clean ✓` / `findings above` / `board-drift:` absence and both valid-path arms —
# stays here, where it is that script's contract.
from argv_refusal_contract import (
    ArgvContract,
    assert_help_flag_exits_zero_with_usage,
    assert_unknown_argument_exits_with_the_refusal_code,
    assert_unknown_argument_names_itself_on_stderr,
    assert_unknown_argument_writes_NOTHING_to_stdout,
)
import private_tree  # noqa: E402  (LD-685)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check-board.sh"

#: check-board reads ``CLAUDE_PROJECT_DIR``; a refusal probe must not see the developer's own.
CONTRACT = ArgvContract(script=SCRIPT, timeout=15, scrub=("CLAUDE_PROJECT_DIR",))
_run = CONTRACT.run


def _make_scratch_board(tmp_path, *, with_findings):
    """A disposable board — never the real one — under its own ``progress/``.

    Six status-folder directories exist (the same set ``STATUS_FOLDERS`` names), all
    empty, for the clean case. For the findings case, ``qa_complete/`` gets 11 minimal,
    well-formed issue files (unique ids matching their filenames, no ``## Activity``
    section) — one more than ``QA_COMPLETE_THRESHOLD=10`` — so the ONLY finding
    produced is check (b)'s depth warning; nothing else on the board is disturbed.
    """
    progress = tmp_path / "progress"
    for folder in ("todo", "in_progress", "dev_complete", "qa_complete", "blocked", "done"):
        (progress / folder).mkdir(parents=True)
    if with_findings:
        for n in range(1, 12):
            issue_id = f"LD-90{n:02d}"
            (progress / "qa_complete" / f"{issue_id}-dummy.md").write_text(
                f"---\nid: {issue_id}\n---\n# dummy scratch issue, no Activity section\n",
                encoding="utf-8",
            )
    return tmp_path


# --------------------------------------------------------------------------- #
# AC1 / AC2 — an unknown argument is refused before any work runs.
# --------------------------------------------------------------------------- #

@private_tree.kit
def test_unknown_argument_exits_nonzero():
    assert_unknown_argument_exits_with_the_refusal_code(CONTRACT)


@private_tree.kit
def test_unknown_argument_usage_on_stderr():
    assert_unknown_argument_names_itself_on_stderr(CONTRACT)


@private_tree.kit
def test_unknown_argument_prints_no_verdict_on_stdout():
    """The actual bug: stdout must carry NO verdict line at all — not just a
    different exit code. An operator grepping for ``clean ✓`` must not find one.

    The emptiness is the shared contract; the three named absences below are check-board's
    own, and they stay stated because THIS script's verdict line is what got falsified.
    """
    result = assert_unknown_argument_writes_NOTHING_to_stdout(CONTRACT)
    assert "clean" not in result.stdout
    assert "findings above" not in result.stdout
    assert "board-drift:" not in result.stdout


# --------------------------------------------------------------------------- #
# AC3 — --help is not an error.
# --------------------------------------------------------------------------- #

@private_tree.kit
@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_flag_exits_zero_with_usage(flag):
    assert_help_flag_exits_zero_with_usage(CONTRACT, flag)


# --------------------------------------------------------------------------- #
# AC4 — the informational convention is unchanged for a valid, no-argument run,
# on BOTH a clean scratch board and one with a constructed finding.
# --------------------------------------------------------------------------- #

@private_tree.kit
def test_no_argument_run_clean_scratch_board_unchanged(tmp_path):
    scratch = _make_scratch_board(tmp_path, with_findings=False)
    result = _run([], env_overrides={"CLAUDE_PROJECT_DIR": str(scratch)})
    assert result.returncode == 0
    assert "── board-drift: clean ✓" in result.stdout
    assert "findings above" not in result.stdout
    assert "unknown arg" not in result.stdout


@private_tree.kit
def test_no_argument_run_findings_scratch_board_unchanged(tmp_path):
    scratch = _make_scratch_board(tmp_path, with_findings=True)
    result = _run([], env_overrides={"CLAUDE_PROJECT_DIR": str(scratch)})
    assert result.returncode == 0
    assert "── board-drift: findings above ⚠ (informational; exit 0 by convention)" in result.stdout
    assert "[b] qa_complete/ depth: 11 / 10 threshold  ⚠ over" in result.stdout
    assert "── board-drift: clean ✓" not in result.stdout
