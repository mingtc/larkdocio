"""LD-640 — the throwaway-git-sandbox bootstrap, **one definition, imported not copied**.

**Why this module exists.** Three guard modules each need the same thing before they can
assert anything: a disposable work repository whose ``origin`` is a *local bare* repository,
both built inside a ``tmp_path``, both pointed at ``develop``, and configured so a
developer's own git config cannot reach them. That bootstrap was written out three times,
byte-identically:

* ``tests/test_finish_pr_truthful_claims.py`` (LD-622) — ``Sandbox``;
* ``tests/test_release_readback_claims.py`` (LD-625) — ``ReleaseSandbox``, in the dev repo only;
* ``tests/test_push_readback_claims.py`` (LD-625's harness reused) — ``PushSandbox``, in the dev
  repo only (both test the maintainers' release script, which this repository does not carry).

So this module owns the **mechanism** and nothing else, the same split
``tests/registration_seam.py`` (LD-633) settled for the registration scanner: what each
sandbox *seeds into* the repo — a board, release stubs, a copy of ``push-retry.sh``, a
receive log — is that guard's policy and stays in its own file. ``tests/guard_kit.py``'s
LD-242 doctrine applies: **the next sandbox enrols BY IMPORT, NOT BY COPY.**

THE INVARIANT THIS MODULE CARRIES — READ IT BEFORE CHANGING :func:`git`
======================================================================
**No call through :func:`git` may ever operate on the real repository.** The mechanism is
that the repository is a **mandatory first parameter**: ``git`` has no default ``cwd``, so
``subprocess`` cannot fall back to the pytest process's own working directory — which *is*
this checkout. That property is what makes the whole family safe, and it is why
``tests/test_no_test_reads_live_git.py`` exempts this one function by name (register key
``git_sandbox.py::git``) instead of exempting each caller.

**What would violate it** — any of these is the defect, not a style question:

* giving ``cwd`` a default value, or making it optional/keyword-with-default;
* accepting a ``cwd`` the caller did not derive from a ``tmp_path`` — e.g. ``REPO_ROOT``,
  ``Path.cwd()``, ``os.getcwd()``, or a path read out of the environment;
* adding a ``-C``/``--git-dir``/``--work-tree`` argument at a call site, which would let the
  named ``cwd`` be silently overridden by argv;
* dropping ``GIT_CONFIG_NOSYSTEM``, or removing the ``commit.gpgsign`` /
  ``core.hooksPath=/dev/null`` keys from :func:`bootstrap_origin_and_work` — the sandbox
  would then execute the developer's own hooks and signing key inside a test.

**Deliberately NOT enrolled here** (stated so the inclusion rule is auditable rather than
implied): ``tests/test_release_gate_notes.py::_git`` and
``tests/test_consumer_update_wheel_selection.py::_git``. Both build a **single non-bare**
repository, invoke git through ``git -C <root>`` rather than a ``cwd``, return nothing
(``check=True`` and no ``CompletedProcess``), and set ``core.hooksPath`` to the sandbox's own
real hooks directory because their subjects *install hooks*. Folding them in would change
their behaviour; they are a different invoker, not a copy of this one.
"""
import os
import pathlib
import shutil
import subprocess

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"

#: The config a sandbox repository gets so that a developer's global/system git config —
#: a signing key, a hooks path, an identity — cannot reach a test run.
SANDBOX_CONFIG = (
    ("user.email", "test@sandbox.local"),
    ("user.name", "Sandbox Test"),
    ("init.defaultBranch", "develop"),
    ("commit.gpgsign", "false"),
    ("core.hooksPath", "/dev/null"),
)


def git(cwd, *args, check=True):
    """Every call names its repository through a mandatory ``cwd`` — always a ``tmp_path``
    sandbox the caller built, never this checkout."""
    result = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                            timeout=120, env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1"})
    if check and result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {cwd}:\n{result.stderr}")
    return result


def bootstrap_origin_and_work(root, origin, work):
    """A bare ``origin`` plus a work repo, both on ``develop``, both hermetically configured.

    Every git call goes through :func:`git`, which REQUIRES a ``cwd`` — so no invocation can
    fall back to the process's own directory (the live repo). Returns nothing; the caller
    owns what it seeds next.
    """
    origin.parent.mkdir(parents=True, exist_ok=True)
    git(root, "init", "--bare", str(origin))
    git(origin, "symbolic-ref", "HEAD", "refs/heads/develop")

    work.mkdir(parents=True)
    git(root, "init", str(work))
    git(work, "symbolic-ref", "HEAD", "refs/heads/develop")
    for key, value in SANDBOX_CONFIG:
        git(work, "config", key, value)


def copy_scripts_into(work):
    """This repo's ``scripts/`` copied into the sandbox, minus ``scripts/test`` (fixture
    trees the scripts under test have no business finding)."""
    shutil.copytree(SCRIPTS, work / "scripts")
    shutil.rmtree(work / "scripts" / "test", ignore_errors=True)
