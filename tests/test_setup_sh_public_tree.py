"""``setup.sh`` depends on nothing the public repository lacks (LD-694 F10).

The public repository is a one-way export of this one (``D-120``). ``setup.sh`` ships in it as
the README's developer quickstart, and it used to do two things there that only make sense in
the private working repository:

* ``git config core.hooksPath scripts/githooks`` — a directory the export does not carry. Git
  then reads hooks from a directory that does not exist, which **silently switches off every
  hook the developer already had** in ``.git/hooks/``;
* its closing "next steps" sent the reader to ``progress/todo/``, ``./scripts/check-board.sh``,
  ``CLAUDE.md`` and ``PROJECT.md`` — none of which exist there.

Both are now conditional on the thing existing. These arms drive the **real script** in a
throwaway git repository with a stub interpreter (no venv is built, nothing is installed, no
suite runs), once shaped like the public tree and once like the private one.
"""
import os
import pathlib
import shutil
import subprocess

from git_sandbox import git

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SETUP_SH = REPO_ROOT / "setup.sh"

#: Understands the three invocations dev mode makes: ``-m venv <dir>``, ``-m pip …`` and
#: ``-m pytest -q``. The "venv" it makes holds a copy of itself as ``bin/python``.
FAKE_PYTHON = """#!/usr/bin/env bash
case "${2:-}" in
  venv) mkdir -p "$3/bin"; cp "$0" "$3/bin/python"; chmod +x "$3/bin/python" ;;
  pip|pytest) exit 0 ;;
  *) echo "stub python: unexpected: $*" >&2; exit 1 ;;
esac
"""

PRIVATE_POINTERS = ("progress/todo", "check-board.sh", "CLAUDE.md", "PROJECT.md")


def _tree(tmp_path, private):
    root = tmp_path / "larkdocio"
    root.mkdir()
    shutil.copy2(SETUP_SH, root / "setup.sh")
    (root / "pyproject.toml").write_text("[project]\nname = 'larkdocio'\n", encoding="utf-8")
    if private:
        (root / "scripts" / "githooks").mkdir(parents=True)
        (root / "scripts" / "check-board.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        (root / "progress" / "todo").mkdir(parents=True)
        (root / "CLAUDE.md").write_text("x\n", encoding="utf-8")
        (root / "PROJECT.md").write_text("x\n", encoding="utf-8")
    stub = tmp_path / "fake-python"
    stub.write_text(FAKE_PYTHON, encoding="utf-8")
    stub.chmod(0o755)
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", HOME=str(tmp_path), PYTHON=str(stub))
    env.pop("GIT_DIR", None)
    git(root, "init", "-q")
    return root, env


def _run(root, env):
    result = subprocess.run(["bash", "setup.sh"], cwd=root, env=env, capture_output=True,
                            text=True)
    hooks = git(root, "config", "--local", "--get", "core.hooksPath", check=False)
    return result, hooks.stdout.strip()


def test_in_the_public_tree_setup_leaves_core_hooks_path_alone(tmp_path):
    root, env = _tree(tmp_path, private=False)

    result, hooks_path = _run(root, env)

    assert result.returncode == 0, result.stderr
    assert hooks_path == "", (
        f"setup.sh pointed core.hooksPath at {hooks_path!r}, a directory this tree lacks — "
        "git would silently stop running the developer's own hooks")


def test_in_the_public_tree_setup_names_no_private_file(tmp_path):
    root, env = _tree(tmp_path, private=False)

    result, _ = _run(root, env)

    named = [p for p in PRIVATE_POINTERS if p in result.stderr + result.stdout]
    assert not named, f"setup.sh sent the reader to files this tree lacks: {named}"


def test_in_the_private_tree_setup_still_wires_the_hooks_and_the_board(tmp_path):
    root, env = _tree(tmp_path, private=True)

    result, hooks_path = _run(root, env)

    assert result.returncode == 0, result.stderr
    assert hooks_path == "scripts/githooks"
    assert all(p in result.stderr for p in PRIVATE_POINTERS), result.stderr
