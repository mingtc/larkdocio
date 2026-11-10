"""LD-640 — the argv-refusal contract, **one definition, parametrized over the script**.

**Why this module exists.** LD-616 found that ``scripts/check-board.sh`` parsed no arguments
at all, so a mistyped flag was silently ignored and the run still printed
``── board-drift: clean ✓`` at exit 0. LD-622 defect 1 found the identical defect in
``scripts/next-id.sh``, one step worse — it printed a real issue id, a side effect the caller
turns into a branch, a filename and a commit. The fix was the same convention both times, and
so was the guard: ``tests/test_check_board_argument_guard.py`` and
``tests/test_next_id_argument_guard.py`` each spelled out the same four assertions by copy.

THE CONTRACT — for a READ-ONLY instrument a human runs by hand
==============================================================
* an unknown argument ⇒ **exit 2** (``scripts/verify.sh``'s idiom, deliberately NOT 1, which
  ``move-issue.sh`` / ``archive-progress.sh`` reserve for a MUTATING command);
* ``"unknown arg"`` on **stderr**, with the offending token echoed back;
* **nothing on stdout** — an operator grepping stdout must never get a false match from a run
  that never happened, and must never be handed a value the refusal did not compute;
* ``--help`` / ``-h`` is not a mistake: **usage on stdout, exit 0, empty stderr**.

**What stays in each guard's own file** (the same split ``tests/registration_seam.py``
(LD-633) and ``tests/git_sandbox.py`` (LD-640 AC3) settled): every assertion about *that
script's own* output — check-board's ``clean ✓`` / ``findings above`` / ``board-drift:``
absences, next-id's ``LD-`` absence and its stray-positional arm — and the **valid-path
arms**, which are that script's contract and are also the safety net proving the refusal did
not touch the path that works. This module owns the shape shared by both, and nothing else.
``tests/guard_kit.py``'s LD-242 doctrine applies: the next instrument enrols BY IMPORT, NOT
BY COPY.

A **census** over the scripts that owe this contract is a separate, parked issue; this module
is its prerequisite, not its implementation. Nothing here claims to know which scripts are
enrolled.
"""
import os
import subprocess
from dataclasses import dataclass, field
from typing import Tuple

#: The token used to probe the refusal — a flag no script will ever grow.
UNKNOWN_ARG = "--definitely-not-an-option"

#: The exit code the contract fixes. Written once, here.
REFUSAL_EXIT = 2


@dataclass(frozen=True)
class ArgvContract:
    """One script under the contract, plus the facts about *invoking* it.

    ``scrub`` and ``timeout`` are per-script invocation facts, not policy about the contract:
    check-board reads ``CLAUDE_PROJECT_DIR`` and must not see the developer's own, and the two
    scripts are differently slow.
    """

    script: os.PathLike
    timeout: float = 15.0
    scrub: Tuple[str, ...] = field(default=())

    def run(self, args, env_overrides=None, cwd=None):
        """The script, run through ``bash``, capturing both streams as text."""
        env = os.environ.copy()
        for name in self.scrub:
            env.pop(name, None)
        if env_overrides:
            env.update(env_overrides)
        return subprocess.run(
            ["bash", str(self.script), *args],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(cwd) if cwd else None,
            timeout=self.timeout,
        )


def assert_unknown_argument_exits_with_the_refusal_code(contract):
    """Exit :data:`REFUSAL_EXIT`, not merely non-zero and not 1."""
    result = contract.run([UNKNOWN_ARG])
    assert result.returncode == REFUSAL_EXIT, (
        f"expected exit {REFUSAL_EXIT} (LD-616's convention for a read-only instrument a "
        f"human runs by hand), got {result.returncode}\n"
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    return result


def assert_unknown_argument_names_itself_on_stderr(contract):
    """``"unknown arg"`` on stderr, with the offending token echoed — a refusal a reader can
    act on without re-running the command."""
    result = contract.run([UNKNOWN_ARG])
    assert "unknown arg" in result.stderr, result.stderr
    assert UNKNOWN_ARG in result.stderr, (
        f"the refusal does not echo the token it refused: {result.stderr!r}")
    return result


def assert_unknown_argument_writes_NOTHING_to_stdout(contract):
    """THE defect, in both incidents: stdout must be empty, so no run that never happened can
    be mistaken — by an operator's grep or by a caller reading a value — for one that did."""
    result = contract.run([UNKNOWN_ARG])
    assert result.stdout == "", (
        f"a refused run printed something on stdout: {result.stdout!r}")
    return result


def assert_help_flag_exits_zero_with_usage(contract, flag):
    """``--help``/``-h`` prints usage on stdout and exits 0 with an empty stderr."""
    result = contract.run([flag])
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    assert "Usage" in result.stdout, result.stdout
    assert result.stderr == "", result.stderr
    return result
