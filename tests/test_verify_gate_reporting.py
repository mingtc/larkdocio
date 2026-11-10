# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""The canonical gate REPORTS the suite it ran — the stacked-quiet defect.

``scripts/verify.sh`` ran ``python -m pytest -q`` while ``pyproject.toml``'s ``addopts``
already supplies ``-q``. Two ``-q`` flags **stack into ``-qq``**, and pytest's second quiet
level drops the summary count line — so the one gate every role runs and every review quotes
printed **no number**, and each "N passed" figure had to come from a separate invocation.

The fix is subtraction: ``addopts`` owns the project's default verbosity and the runner stops
repeating it. Both halves are pinned here, because either alone rots:

* **the ratchet** — the runner's pytest gate passes no verbosity flag of its own, so the
  redundant ``-q`` cannot quietly come back (it reads as harmless explicitness, which is
  exactly how it got there);
* **the mechanism** — the stack really is what suppresses the count, proved on a throwaway
  one-test project outside this repository. Without it the ratchet is a rule with no stated
  reason, and the first person who finds it inconvenient deletes it.

The end-to-end proof that the real runner prints a count lives in the kit's own sandbox
harness (``scripts/test/run.sh``, case LD-196a), which can afford to execute the gate against
a throwaway project; a suite cannot run itself.
"""
import os
import pathlib
import re
import subprocess
import sys

import pytest
import tomllib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
VERIFY = REPO_ROOT / "scripts" / "verify.sh"
PYPROJECT = REPO_ROOT / "pyproject.toml"

#: pytest's summary line, matched by SHAPE and not by number — a test that pinned "6605
#: passed" would redden on every test anyone adds, which is how a count check gets deleted.
COUNT_LINE = re.compile(r"^\d+ passed", re.MULTILINE)

#: Every flag that would re-open the defect (or over-correct it into noise) if the runner
#: started supplying verbosity of its own again.
_VERBOSITY_FLAGS = ("-q", "-qq", "--quiet", "-v", "-vv", "--verbose", "--no-summary")


def _pytest_gate_line():
    """The single ``run_gate "pytest" …`` line from the runner, as written."""
    lines = [
        line.strip()
        for line in VERIFY.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith('run_gate "pytest"')
    ]
    assert len(lines) == 1, f"expected exactly one pytest gate in verify.sh, found {lines}"
    return lines[0]


def _addopts():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return data["tool"]["pytest"]["ini_options"]["addopts"]


# --------------------------------------------------------------------------- #
# 1. One owner of the default verbosity — and it is not the runner.            #
# --------------------------------------------------------------------------- #

def test_addopts_owns_the_projects_default_verbosity():
    """The single definition. Everything downstream (the runner, a bare ``pytest``, an editor's
    test button) inherits the same one quiet level from here."""
    assert "-q" in _addopts().split(), _addopts()


def test_the_runner_repeats_no_verbosity_flag_of_its_own():
    """The ratchet. A second ``-q`` here stacks into ``-qq`` and silences the count line the
    gate exists to report; a ``-v`` would swing the other way and print 6000 test names."""
    tokens = _pytest_gate_line().split()
    offenders = [token for token in tokens if token in _VERBOSITY_FLAGS]
    assert offenders == [], (
        f"verify.sh's pytest gate supplies {offenders}; pyproject's addopts already owns the "
        f"default verbosity, and a second quiet flag stacks into -qq (no count line)"
    )


def test_the_runner_still_runs_pytest_through_the_project_interpreter():
    """The must-not-break half of the subtraction: only the flag went. The gate is still the
    venv interpreter running ``-m pytest``, so nothing about WHICH pytest runs has changed."""
    line = _pytest_gate_line()
    assert '"$PY" -m pytest' in line, line


def test_the_quick_flag_still_gates_only_the_build():
    """``--quick`` keeps its meaning: pytest runs unconditionally, and only ``python -m build``
    sits behind the flag. The count line is the sole difference this change makes."""
    text = VERIFY.read_text(encoding="utf-8")
    pytest_at = text.index('run_gate "pytest"')
    quick_guard_at = text.index('if [ "$QUICK" -eq 0 ]')
    build_at = text.index('run_gate "python -m build"')
    assert pytest_at < quick_guard_at < build_at, (
        "the pytest gate must run before (and outside) the --quick guard, and the build gate "
        "inside it"
    )


def test_the_runner_documents_why_the_flag_is_absent():
    """A deletion with no stated reason invites its own reversal, so the reason lives next to
    the gate: the header stops advertising ``pytest -q`` and the call site says what stacking
    did."""
    text = VERIFY.read_text(encoding="utf-8")
    assert "pytest -q" not in text, "the runner still advertises the flag it no longer passes"
    assert "-qq" in text, "the reason the flag is absent must be recorded at the call site"


# --------------------------------------------------------------------------- #
# 2. THE MECHANISM — proved outside this repository, on a one-test project.     #
# --------------------------------------------------------------------------- #

def _throwaway_project(tmp_path, addopts):
    """A one-test project with its own ``addopts``, so the probe reads that config and never
    this repository's (its own ``pyproject.toml`` is the rootdir marker)."""
    (tmp_path / "pyproject.toml").write_text(
        f'[tool.pytest.ini_options]\naddopts = "{addopts}"\n', encoding="utf-8"
    )
    (tmp_path / "test_probe.py").write_text(
        "def test_probe():\n    assert True\n", encoding="utf-8"
    )
    return tmp_path


def _run_pytest(project, extra_args=()):
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *extra_args],
        cwd=project,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTEST_ADDOPTS": ""},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout


def test_one_quiet_level_prints_the_count_line(tmp_path):
    """The state the gate is now in: ``addopts``' single ``-q``, and a number to quote."""
    output = _run_pytest(_throwaway_project(tmp_path, "-q"))

    assert COUNT_LINE.search(output), output


def test_a_second_quiet_flag_is_what_suppressed_it(tmp_path):
    """The defect reproduced: the same project, the same one test, one extra ``-q`` on the
    command line — and the summary count is gone. This is what ``verify.sh`` used to do."""
    output = _run_pytest(_throwaway_project(tmp_path, "-q"), extra_args=["-q"])

    assert not COUNT_LINE.search(output), output


@pytest.mark.parametrize("addopts", ["-q", "-q -m 'not live'"])
def test_the_runners_own_invocation_shape_reports_a_count(tmp_path, addopts):
    """The runner's shape end to end, at both the bare and the marker-filtered ``addopts`` this
    project actually uses: no flag from the caller, count line present."""
    output = _run_pytest(_throwaway_project(tmp_path, addopts))

    assert COUNT_LINE.search(output), output


# ===========================================================================
# LD-649 — THE GUARD SET, held in both directions, and its refusal on the
#          canonical run rather than only on --scope
# ===========================================================================
#
# ``GUARD_SET`` was the one registry in the tree not held bidirectionally: no test
# mentioned it (``grep -rn GUARD_SET tests/*.py`` returned nothing), and its own
# vanish-check sat inside ``if [ "$SCOPED" -eq 1 ]`` — so the mandatory gate at the
# dev_complete handoff, at QA and at release never ran it, while the array's comment
# claimed "the runner refuses to start if a listed path has vanished".
#
# WHAT IS DERIVABLE AND WHAT IS NOT, stated because the honest limit matters more than
# the guard: membership is a judgment about what a test's SUBJECT is, and no static
# property of a test module distinguishes a cross-cutting guard from a local one — 199
# of the 600 modules under ``tests/`` walk the tree, so a code-derived population would
# need a ~165-row exclusion list, which is a second hand-kept registry with a worse
# inclusion rule. So the derivation used here is a DECLARATION: each member carries a
# ``GUARD-SET MEMBER`` marker, and the marked set and the array are held EQUAL both
# ways. That catches a member renamed, moved or un-marked, and a guard that declares
# itself but never reaches the array. It does NOT catch a guard that declares nothing
# and is never listed — written down rather than left to be discovered.

#: The marker a GUARD_SET member carries, at the top of the file, above its docstring.
GUARD_SET_MARKER = "# GUARD-SET MEMBER"

#: The floor the population must clear. Not a pinned count (that would redden for every
#: guard legitimately added) — a floor, in the shape ``TIER_FLOOR`` and
#: ``heading_index.py``'s ``EmptyRegistry`` arm use, so this can never pass over an
#: empty or catastrophically shrunken set. 36 members as landed by LD-649.
GUARD_SET_FLOOR = 30


def _guard_set_from_runner(text=None):
    """The GUARD_SET array, parsed out of the runner itself — never re-typed here.

    Re-typing the list in the test would give the two sides a common author and prove
    nothing; the runner is the single source, exactly as the array's own comment claims
    ("the membership is READABLE HERE, without running anything").
    """
    text = VERIFY.read_text(encoding="utf-8") if text is None else text
    assert "GUARD_SET=(" in text, "the runner no longer declares a GUARD_SET array"
    body = text.split("GUARD_SET=(", 1)[1].split("\n)", 1)[0]
    return [
        line.strip()
        for line in body.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _marked_modules():
    """Every ``tests/*.py`` whose head declares itself a GUARD_SET member."""
    return [
        f"tests/{path.name}"
        for path in sorted((REPO_ROOT / "tests").rglob("*.py"))  # LD-654: recursive population
        if any(
            line.startswith(GUARD_SET_MARKER)
            for line in path.read_text(encoding="utf-8").splitlines()[:12]
        )
    ]


def test_the_guard_set_population_is_not_empty_and_clears_its_floor():
    """The non-vacuity arm, first, because every arm below is trivially true over an
    empty set — the exact way LD-647 shipped a guard that skipped in 100% of runs."""
    listed = _guard_set_from_runner()
    marked = _marked_modules()
    assert len(listed) >= GUARD_SET_FLOOR, (
        f"scripts/verify.sh's GUARD_SET holds {len(listed)} paths, under the floor of "
        f"{GUARD_SET_FLOOR}. Either the always-on drift-guard floor has been gutted, or "
        f"the parse above broke — both are failures, and neither may be silent."
    )
    assert len(marked) >= GUARD_SET_FLOOR, (
        f"only {len(marked)} test modules carry the {GUARD_SET_MARKER!r} marker, under "
        f"the floor of {GUARD_SET_FLOOR} — the derived side of this guard has collapsed, "
        f"which would make every equality below pass over almost nothing."
    )


def test_every_guard_set_member_declares_itself_one():
    """LIST → TREE, beyond mere existence: a listed module that lost its marker (a copy,
    a move, a rewrite that dropped the head comment) reddens here."""
    unmarked = sorted(set(_guard_set_from_runner()) - set(_marked_modules()))
    assert not unmarked, (
        f"these GUARD_SET members carry no {GUARD_SET_MARKER!r} marker: {unmarked}. Add "
        f"the marker at the top of each file (the wording is uniform — copy it from a "
        f"sibling), or take the module out of the array in scripts/verify.sh."
    )


def test_every_module_that_declares_itself_a_guard_is_in_the_array():
    """TREE → LIST — the direction that did not exist before LD-649. A new cross-cutting
    guard that marks itself and never reaches the array is invisible to every --scope run
    and nothing reddened; now this does, naming the file."""
    unlisted = sorted(set(_marked_modules()) - set(_guard_set_from_runner()))
    assert not unlisted, (
        f"these modules declare themselves GUARD_SET members but are not in the array in "
        f"scripts/verify.sh: {unlisted}. Add them to GUARD_SET in the same change (the "
        f"inclusion rule is stated above the array), or drop the marker."
    )


def test_every_guard_set_member_exists_on_disk():
    """The list cannot outlive its subject. The runner enforces this too, at start-up and
    on every invocation; this arm is the suite's own copy of that answer, so a rename is
    caught even by someone running pytest directly."""
    vanished = sorted(
        path for path in _guard_set_from_runner()
        if not (REPO_ROOT / path).is_file()
    )
    assert not vanished, (
        f"GUARD_SET names paths that no longer exist: {vanished} — fix the array in "
        f"scripts/verify.sh (LD-354); the guard floor must stay complete."
    )


def test_the_vanished_guard_check_is_not_inside_the_scope_branch():
    """AC5/AC7 — the refusal runs on the CANONICAL gate, not only on --scope.

    Read structurally rather than by grepping a sentence: the existence check must appear
    before the ``if [ "$SCOPED" -eq 1 ]; then`` block that selects the scoped pytest gate,
    and must not be nested inside any ``SCOPED`` conditional. Before LD-649 it was, so a
    bare ``./scripts/verify.sh`` — the run that is mandatory at dev_complete, at QA and at
    release — never executed it.
    """
    text = VERIFY.read_text(encoding="utf-8")
    lines = text.splitlines()

    def line_of(needle, start=0):
        for index in range(start, len(lines)):
            if needle in lines[index]:
                return index
        raise AssertionError(f"scripts/verify.sh no longer contains {needle!r}")

    check = line_of('for g in "${GUARD_SET[@]}"; do [ -e "$g" ]')
    # The nearest enclosing/preceding SCOPED conditional must NOT be an open `if` that the
    # check sits inside: between the check and the top of the file there must be no
    # `if [ "$SCOPED" -eq 1 ]; then` that has not been closed. The simplest observable form
    # of that: the check precedes EVERY `SCOPED -eq 1` conditional that guards a gate.
    scoped_gate = line_of('if [ "$SCOPED" -eq 1 ]; then')
    assert check < scoped_gate, (
        "the GUARD_SET existence check is at line "
        f"{check + 1} and the first `if [ \"$SCOPED\" -eq 1 ]; then` block opens at line "
        f"{scoped_gate + 1} — the check is inside the --scope branch again, so a bare "
        "`./scripts/verify.sh` (the mandatory gate at dev_complete, QA and release) does "
        "not run it. Hoist it back above the branch (LD-649)."
    )
    # And the first SCOPED conditional the file opens is the one this check must precede:
    # nesting it inside a NEW, earlier `if [ "$SCOPED" -eq 1 ]; then` would move that
    # line above the check and redden this same assertion, so the ordering is sufficient.


def test_the_runner_refuses_a_vanished_guard_on_the_bare_invocation(tmp_path):
    """The end-to-end half: a COPY of the runner with one GUARD_SET entry pointed at a
    path that does not exist, invoked with NO arguments, must refuse before running any
    gate. Executed rather than asserted about — a claim about a runner's behaviour that no
    one runs is the defect this issue fixed.

    The copy is invoked from a throwaway directory whose only content is the script, so the
    run can never reach pytest or the build even if the refusal regressed.
    """
    text = VERIFY.read_text(encoding="utf-8")
    listed = _guard_set_from_runner(text)
    victim = listed[0]
    ablated = text.replace(
        f"\n  {victim}\n", "\n  tests/test_no_such_guard_ld649.py\n", 1)
    assert ablated != text, "failed to ablate a GUARD_SET entry"

    sandbox = tmp_path / "scripts"
    sandbox.mkdir()
    script = sandbox / "verify.sh"
    script.write_text(ablated, encoding="utf-8")
    script.chmod(0o755)

    result = subprocess.run(
        ["bash", str(script)], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert result.returncode == 2, (
        "a bare invocation of the runner did not refuse on a vanished GUARD_SET path "
        f"(exit {result.returncode}); stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "test_no_such_guard_ld649.py" in result.stderr, (
        f"the refusal does not name the missing path: {result.stderr!r}"
    )
    assert "GATE:" not in result.stdout, (
        f"the runner started a gate before refusing: {result.stdout!r}"
    )
