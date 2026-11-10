"""LD-622 defect 4 — ``scripts/reanchor-capabilities.sh`` measured a tree the operator
was not looking at, printed success, and changed nothing they asked it to change.

The mechanism, exactly: the embedded python did ``sys.path.insert(0, "tests")`` and
**never put `src` on the path at all**. Run from the main checkout that is harmless —
this repo's ``.venv`` carries an editable-install ``.pth`` that appends the main
checkout's ``src``, so the right module happened to be found. Run **inside a git
worktree** the same ``.pth`` is what answers, so ``import larkdocio`` returned the
**main checkout's** package while the script was cutting the pin for the **worktree**.

Measured pre-fix, in a worktree whose ``src/larkdocio/capabilities/_assembly.py``
diverged from the main checkout's::

    $ cd <worktree> && ./scripts/reanchor-capabilities.sh --check
      the pin matches the tree — every address is where the table says it is.
    rc=0

That is the sharpest instance of this issue's class: not an unverified claim but **work
performed against the wrong subject while reporting done** — and it sits on the cut's
critical path, since re-anchoring is the one step a new release section forces, so an
operator cutting from a worktree got a green re-anchor and a stale pin.

**AC5b is the reason this file exists rather than a one-line path edit.** Adding ``src``
to ``sys.path`` without a test that proves WHICH TREE was resolved is precisely the
omission that kept this invisible, so every test below asserts the tree:

* ``test_a_divergence_in_the_worktrees_own_src_is_what_gets_measured`` — the divergence
  IS the proof. The worktree's ``_assembly.py`` is edited, and ``--check`` must report
  the payload MOVED (rc=1) **and** name the worktree's own file as the resolved module.
  Pre-fix this test's exact scenario printed the line quoted above at rc=0.
* ``test_an_untouched_worktree_still_reports_the_pin_matching`` — the control, so the
  guard cannot pass by simply being red inside any worktree.
* ``test_it_REFUSES_when_larkdocio_resolves_outside_the_invoked_tree`` — the read-back
  fence. With the worktree's ``src/larkdocio`` moved aside, the environment's ``.pth``
  still answers the import; the script must **refuse (rc=2)** naming both paths rather
  than measure the wrong tree. This is the arm that makes the path fix *checkable*
  instead of merely present.

The worktree is a worktree of a **throwaway sandbox repo** this test builds in ``tmp_path``
from the current tree's ``src`` / anchor / script — never of this checkout. The hazard needs
no help from the live repository to be real: the interpreter's editable-install ``.pth``
points at the main checkout's ``src``, which is exactly the foreign tree that used to answer
the import.
"""
import os
import pathlib
import shutil
import subprocess
import sys

import pytest
import private_tree  # noqa: E402  (LD-685)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT_REL = "scripts/reanchor-capabilities.sh"
ANCHOR_REL = "tests/capabilities_anchor.py"
ASSEMBLY_REL = "src/larkdocio/capabilities/_assembly.py"
PINNED_TITLE = 'title="docx reader — download a Lark docx/wiki document to clean Markdown"'
PROBE_TITLE = 'title="LD-622 PROBE — this worktree only"'


def _git(cwd, *args, check=True):
    """Every call names its repository through a mandatory ``cwd`` — and that repository is
    always a ``tmp_path`` one this test built (see ``sandbox_worktree``)."""
    result = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                            timeout=180, env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1"})
    if check and result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {cwd}:\n{result.stderr}")
    return result


@pytest.fixture()
def sandbox_worktree(tmp_path):
    """A genuine ``git worktree`` — of a THROWAWAY repo, never of this checkout.

    The sandbox repo carries the three files the script needs (``src/larkdocio``,
    ``tests/capabilities_anchor.py``, the script itself), copied from this tree so the pin
    and the sources start consistent. A worktree is then added inside the sandbox, which is
    where the script runs.

    The hazard under test survives that isolation untouched, which is the whole reason this
    works: the interpreter is ``sys.executable``, whose editable-install ``.pth`` appends the
    **real main checkout's** ``src``. So "the wrong tree that answers the import" is genuine,
    not simulated — and the live repository is never a git target.
    """
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "tests").mkdir()
    shutil.copytree(REPO_ROOT / "src", repo / "src",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(REPO_ROOT / ANCHOR_REL, repo / ANCHOR_REL)
    shutil.copy2(REPO_ROOT / SCRIPT_REL, repo / SCRIPT_REL)

    _git(tmp_path, "init", str(repo))
    for key, value in (("user.email", "test@sandbox.local"), ("user.name", "Sandbox Test"),
                       ("commit.gpgsign", "false"), ("core.hooksPath", "/dev/null")):
        _git(repo, "config", key, value)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "seed the reanchor sandbox", "--quiet")

    worktree = tmp_path / "wt"
    _git(repo, "worktree", "add", "--detach", str(worktree), "HEAD")
    assert (worktree / ".git").exists(), "the sandbox worktree was not created"
    return worktree


def _reanchor_check(cwd):
    """Run ``--check`` from *cwd* with the SAME interpreter pytest runs under — the one whose
    editable-install ``.pth`` appends the MAIN CHECKOUT's ``src``. That environment is the
    hazard, not a contrivance for the test."""
    env = os.environ.copy()
    env["PYTHON"] = sys.executable
    env.pop("PYTHONPATH", None)
    return subprocess.run(
        ["bash", str(pathlib.Path(cwd) / SCRIPT_REL), "--check"],
        capture_output=True, text=True, cwd=str(cwd), env=env, timeout=300,
    )


# --------------------------------------------------------------------------- #
# AC5b — the tree it was INVOKED in is the tree it measures.
# --------------------------------------------------------------------------- #

@private_tree.kit
def test_a_divergence_in_the_worktrees_own_src_is_what_gets_measured(sandbox_worktree):
    assembly = sandbox_worktree / ASSEMBLY_REL
    source = assembly.read_text(encoding="utf-8")
    assert PINNED_TITLE in source, (
        "test fixture is stale: the surface title this test diverges is gone from "
        f"{ASSEMBLY_REL}. Pick another payload-visible literal — the divergence IS the proof."
    )
    assembly.write_text(source.replace(PINNED_TITLE, PROBE_TITLE), encoding="utf-8")

    result = _reanchor_check(sandbox_worktree)

    # WHICH TREE (AC5b): the resolved module must be the worktree's own file.
    assert f"larkdocio resolved from:    {sandbox_worktree}/src/larkdocio/__init__.py" in result.stdout, (
        "the script did not name the tree it resolved, or resolved the wrong one\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    assert str(REPO_ROOT / "src" / "larkdocio") not in result.stdout, (
        "the MAIN CHECKOUT's package was resolved from inside a worktree — the defect"
    )
    # ...and the divergence it measured is reported, rather than a false match.
    assert result.returncode == 1, (
        "a worktree whose src diverges from the pin reported no drift — the pre-fix "
        f"behaviour (rc=0, 'the pin matches the tree')\nstdout={result.stdout!r}"
    )
    assert "MOVED" in result.stdout
    assert "surfaces/docx-read" in result.stdout
    assert "the pin matches the tree" not in result.stdout


@private_tree.kit
def test_an_untouched_worktree_still_reports_the_pin_matching(sandbox_worktree):
    """The control: the guard must not pass by being red inside every worktree."""
    result = _reanchor_check(sandbox_worktree)
    assert f"larkdocio resolved from:    {sandbox_worktree}/src/larkdocio/__init__.py" in result.stdout
    assert result.returncode == 0, (
        f"an untouched worktree reported drift\nstdout={result.stdout!r}\n"
        f"stderr={result.stderr!r}"
    )
    assert "the pin matches the tree" in result.stdout


@private_tree.kit
def test_it_REFUSES_when_larkdocio_resolves_outside_the_invoked_tree(sandbox_worktree):
    """The read-back fence. Path-first is not enough on its own: something else can
    always answer the import (an editable ``.pth``, a ``PYTHONPATH``, a wheel in
    site-packages). So the resolved module is read back and a foreign one is REFUSED —
    nothing measured, nothing written, both paths named."""
    shutil.move(str(sandbox_worktree / "src" / "larkdocio"), str(sandbox_worktree / "src" / "larkdocio_moved"))

    result = _reanchor_check(sandbox_worktree)

    assert result.returncode == 2, (
        "the script measured (or crashed on) a foreign package instead of refusing\n"
        f"rc={result.returncode} stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "REFUSING to measure" in result.stderr
    assert str(sandbox_worktree) in result.stderr                      # the tree it was invoked in
    assert str(REPO_ROOT / "src" / "larkdocio") in result.stderr  # the tree that answered
    assert "the pin matches the tree" not in result.stdout
    assert "MOVED" not in result.stdout
