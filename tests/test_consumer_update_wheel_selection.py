"""THE VENDORING GUARD — ``consumers/update_larkdocio.sh`` never vendors a wheel that is
not the version the run was asked for (LD-591).

The defect this guard exists for
--------------------------------
The template's ``dist`` fast path cloned into ``$WORK/$DIST_BRANCH`` — i.e. ``$WORK/dist``
for the default branch name — and did **not** remove that clone when it bailed out. The
build-from-tag fallback then wrote its freshly built wheel into the **same** ``$WORK/dist``,
and selection was ``ls … | head -1``, which is alphabetical. So with the published
branch stale at the PREVIOUS release while the tag had already moved on — precisely the
case the build path exists to cover — the run built the version it was asked for,
vendored the older one, printed the OLD filename against the NEW tag, and exited 0.

So these arms are behavioural, never textual: each one drives the **real script** and
asserts what ends up in ``./vendor/``. ``test_stale_dist_branch_*`` is the reproduction of
the shipped bug and fails against the pre-fix script.

How these tests drive the real script
-------------------------------------
Each case builds a throwaway consumer directory in ``tmp_path``, copies the real
``consumers/update_larkdocio.sh`` into it, and points it at a **local throwaway git repo**
through the script's own documented seams:

* ``LARKDOCIO_REPO_URL`` — documented as overridable *"so the kit self-test can point
  tag-selection at a local throwaway repo without touching the network"*;
* ``LARKDOCIO_DIST_BRANCH`` / ``LARKDOCIO_NO_DIST`` — the fast-path seams the script
  already documents;
* ``PYTHON`` — the interpreter seam (``PYTHON="${PYTHON:-python3}"``). A stub stands in for
  the two invocations the script makes of it (``-m venv`` and ``-m build``), so the wheel
  "build" is instantaneous and its OUTPUT IS THE TEST FIXTURE: the arms decide, via
  ``FAKE_WHEELS``, exactly which wheel filenames land in the build output directory.

Nothing here touches the network and nothing builds a real wheel. ``tests/
test_release_gate_notes.py`` is the prior art for the sandbox shape.
"""
import os
import pathlib
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
UPDATE_SH = REPO_ROOT / "consumers" / "update_larkdocio.sh"

PKG = "larkdocio"
# Two SANDBOX versions, deliberately far above anything this repo will package: a test that
# freezes the currently packaged version goes red the moment the next release is cut
# (``tests/test_version_bump_tolerance.py``). The only property the arms need is that the
# STALE one sorts FIRST alphabetically — which is exactly how the defect chose it.
OLD_VER = "1.98.0"
NEW_VER = "1.99.0"
NEW_WHEEL = f"{PKG}-{NEW_VER}-py3-none-any.whl"
OLD_WHEEL = f"{PKG}-{OLD_VER}-py3-none-any.whl"
TAG = f"v{NEW_VER}"

# A stub interpreter understanding exactly the two invocations update_larkdocio.sh makes:
#   <python> -m venv <dir>                      → a "venv" whose bin/python is this stub
#   <python> -m build --wheel --outdir <dir>    → touch every name in $FAKE_WHEELS there
FAKE_PYTHON = """#!/usr/bin/env bash
set -euo pipefail
case "${2:-}" in
  venv)
    dest="$3"
    mkdir -p "$dest/bin"
    cp "$0" "$dest/bin/python"
    chmod +x "$dest/bin/python"
    printf '#!/usr/bin/env bash\\nexit 0\\n' > "$dest/bin/pip"
    chmod +x "$dest/bin/pip"
    ;;
  build)
    outdir=""
    while [ $# -gt 0 ]; do
      [ "$1" = "--outdir" ] && outdir="${2:-}"
      shift
    done
    [ -n "$outdir" ] || { echo "stub build: no --outdir" >&2; exit 1; }
    mkdir -p "$outdir"
    for w in ${FAKE_WHEELS:-}; do : > "$outdir/$w"; done
    ;;
  *)
    echo "stub python: unexpected invocation: $*" >&2
    exit 1
    ;;
esac
"""


def _git(root, *args):
    """A git command inside the sandbox, insulated from the developer's own config."""
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1")
    subprocess.run(["git", "-C", str(root), *args], check=True, env=env, capture_output=True)


#: The four documents the build path drops beside the wheel, at the paths the tag's tree
#: carries them (LD-694 F12). Their text names the TAG, so a test can tell a refreshed copy
#: from the consumer's existing one.
TAG_DOCS = {
    "src/larkdocio/GUIDE.md": "GUIDE",
    "CHANGELOG.md": "CHANGELOG",
    "RELEASE_NOTES.md": "RELEASE_NOTES",
    "LARK_SETUP.md": "LARK_SETUP",
}


def _remote(tmp_path, dist_branch=None, dist_wheel=None, docs=False, dist_wheels=None):
    """A throwaway larkdocio repository: one commit on `develop`, carrying ``TAG``.

    When ``dist_branch`` is given, an orphan branch of that name carries ``dist_wheel`` (or
    every name in ``dist_wheels``) — the publish branch the fast path shallow-clones. With
    ``docs``, the tagged tree also carries the four consumer documents (:data:`TAG_DOCS`).
    """
    root = tmp_path / "remote"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "symbolic-ref", "HEAD", "refs/heads/develop")
    for key, value in (
        ("user.email", "test@sandbox.local"),
        ("user.name", "Sandbox Test"),
        ("commit.gpgsign", "false"),
        ("core.hooksPath", str(root / ".git" / "hooks")),
    ):
        _git(root, "config", key, value)
    (root / "README.md").write_text("sandbox larkdocio\n", encoding="utf-8")
    if docs:
        for relative in TAG_DOCS:
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
            (root / relative).write_text(f"{relative} at {TAG}\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed")
    _git(root, "tag", TAG)

    if dist_branch:
        _git(root, "checkout", "-q", "--orphan", dist_branch)
        _git(root, "rm", "-q", "-rf", ".")
        for name in dist_wheels or [dist_wheel]:
            (root / name).write_text("", encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", f"publish {dist_wheel}")
        _git(root, "checkout", "-q", "develop")
    return root


def _consumer(tmp_path):
    """A throwaway consumer repo holding only a copy of the template."""
    root = tmp_path / "consumer"
    (root / "scripts").mkdir(parents=True)
    shutil.copy2(UPDATE_SH, root / "scripts" / "update_larkdocio.sh")
    stub = root / "fake-python"
    stub.write_text(FAKE_PYTHON, encoding="utf-8")
    stub.chmod(0o755)
    return root


def _run(consumer, remote, wheels, *args, **env_overrides):
    env = dict(
        os.environ,
        GIT_CONFIG_NOSYSTEM="1",
        LARKDOCIO_REPO_URL=str(remote),
        PYTHON=str(consumer / "fake-python"),
        FAKE_WHEELS=" ".join(wheels),
    )
    env.update(env_overrides)
    result = subprocess.run(
        ["bash", str(consumer / "scripts" / "update_larkdocio.sh"), *args],
        cwd=consumer,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode, result.stdout, result.stdout + result.stderr


def _vendored(consumer):
    return sorted(p.name for p in (consumer / "vendor").glob(f"{PKG}-*.whl"))


# --------------------------------------------------------------------------- #
# AC1 — the reproduction: dist is stale, the build path runs, and the BUILT     #
#        wheel is what gets vendored. This is the arm the shipped bug fails.    #
# --------------------------------------------------------------------------- #

def test_stale_dist_branch_vendors_the_built_wheel_not_the_stale_clone(tmp_path):
    remote = _remote(tmp_path, dist_branch="dist", dist_wheel=OLD_WHEEL)
    consumer = _consumer(tmp_path)

    code, stdout, output = _run(consumer, remote, [NEW_WHEEL])

    assert code == 0, f"the fallback build path refused:\n{output}"
    assert _vendored(consumer) == [NEW_WHEEL], (
        f"vendored the stale wheel from the {'dist'} clone:\n{output}"
    )
    assert NEW_WHEEL in stdout and OLD_WHEEL not in stdout, (
        f"the printed pin line does not name the built wheel:\n{stdout}"
    )


@pytest.mark.parametrize("branch", ["build", "dist-branch", "output"])
def test_no_dist_branch_name_can_collide_with_the_build_output_dir(tmp_path, branch):
    """AC1 — the separation may not depend on the VALUE of LARKDOCIO_DIST_BRANCH."""
    remote = _remote(tmp_path, dist_branch=branch, dist_wheel=OLD_WHEEL)
    consumer = _consumer(tmp_path)

    code, stdout, output = _run(
        consumer, remote, [NEW_WHEEL], LARKDOCIO_DIST_BRANCH=branch
    )

    assert code == 0, f"the fallback build path refused:\n{output}"
    assert _vendored(consumer) == [NEW_WHEEL], (
        f"the {branch!r} clone collided with the build output:\n{output}"
    )


# --------------------------------------------------------------------------- #
# AC2/AC3 — two wheels in the selection directory is a REFUSAL, never a guess   #
# --------------------------------------------------------------------------- #

def test_two_built_wheels_are_refused_with_both_filenames_named(tmp_path):
    remote = _remote(tmp_path)
    consumer = _consumer(tmp_path)

    code, _stdout, output = _run(
        consumer, remote, [OLD_WHEEL, NEW_WHEEL], LARKDOCIO_NO_DIST="1"
    )

    assert code != 0, f"selection guessed instead of refusing:\n{output}"
    assert OLD_WHEEL in output and NEW_WHEEL in output, (
        f"the refusal does not name both candidates:\n{output}"
    )
    assert "refusing to guess" in output, f"not the shared refusal voice:\n{output}"
    assert _vendored(consumer) == [], f"a refusal still wrote to vendor/:\n{output}"


# --------------------------------------------------------------------------- #
# AC4 — the success line's implicit claim is checked before it is printed       #
# --------------------------------------------------------------------------- #

def test_a_built_wheel_whose_version_is_not_the_tags_is_refused(tmp_path):
    remote = _remote(tmp_path)
    consumer = _consumer(tmp_path)

    code, _stdout, output = _run(
        consumer, remote, [OLD_WHEEL], TAG, LARKDOCIO_NO_DIST="1"
    )

    assert code != 0, f"a wheel that is not the requested version was vendored:\n{output}"
    assert OLD_VER in output and NEW_VER in output, (
        f"the refusal does not name both versions:\n{output}"
    )
    assert _vendored(consumer) == [], f"a refusal still wrote to vendor/:\n{output}"


# --------------------------------------------------------------------------- #
# AC5 — no false negatives on the paths that are legitimately fine              #
# --------------------------------------------------------------------------- #

def test_one_matching_wheel_on_the_no_tag_build_path_succeeds(tmp_path):
    remote = _remote(tmp_path)
    consumer = _consumer(tmp_path)

    code, stdout, output = _run(consumer, remote, [NEW_WHEEL], LARKDOCIO_NO_DIST="1")

    assert code == 0, f"the healthy build path refused:\n{output}"
    assert _vendored(consumer) == [NEW_WHEEL]
    assert stdout.strip() == f"{PKG} @ file:./vendor/{NEW_WHEEL}"


def test_one_matching_wheel_on_the_explicit_tag_build_path_succeeds(tmp_path):
    remote = _remote(tmp_path)
    consumer = _consumer(tmp_path)

    code, _stdout, output = _run(
        consumer, remote, [NEW_WHEEL], TAG, LARKDOCIO_NO_DIST="1"
    )

    assert code == 0, f"the healthy build path refused an explicit tag:\n{output}"
    assert _vendored(consumer) == [NEW_WHEEL]


def test_a_current_dist_branch_still_takes_the_fast_path(tmp_path):
    remote = _remote(tmp_path, dist_branch="dist", dist_wheel=NEW_WHEEL)
    consumer = _consumer(tmp_path)

    # No wheels from the stub builder at all: if the fast path did not serve this run,
    # the build path would produce nothing and the script would die.
    code, _stdout, output = _run(consumer, remote, [])

    assert code == 0, f"the fast path did not serve a current dist branch:\n{output}"
    assert _vendored(consumer) == [NEW_WHEEL]
    assert "fast path" in output


# --------------------------------------------------------------------------- #
# LD-694 F12 — a refusal leaves ./vendor/ EXACTLY as it was. The build path     #
# used to copy the tag's four documents into ./vendor/ BEFORE the build and the #
# version check, so "Nothing was vendored and ./vendor/ is untouched" was false #
# on every refusal: the old wheel ended up beside the new tag's documents.      #
# --------------------------------------------------------------------------- #

def _seed_vendor(consumer):
    """A consumer that already vendors the OLD release: its wheel and its four documents."""
    vendor = consumer / "vendor"
    vendor.mkdir()
    (vendor / OLD_WHEEL).write_text("old wheel\n", encoding="utf-8")
    for doc in TAG_DOCS.values():
        (vendor / f"{PKG}-{doc}.md").write_text(f"{doc} at v{OLD_VER}\n", encoding="utf-8")
    return _snapshot(vendor)


def _snapshot(directory):
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir())}


@pytest.mark.parametrize("wheels", [[OLD_WHEEL], [], [OLD_WHEEL, NEW_WHEEL]],
                         ids=["wrong-version", "no-wheel-built", "two-wheels-built"])
def test_a_refused_build_leaves_vendor_byte_identical(tmp_path, wheels):
    remote = _remote(tmp_path, docs=True)
    consumer = _consumer(tmp_path)
    before = _seed_vendor(consumer)

    code, _stdout, output = _run(consumer, remote, wheels, TAG, LARKDOCIO_NO_DIST="1")

    assert code != 0, f"the run did not refuse:\n{output}"
    assert _snapshot(consumer / "vendor") == before, (
        f"a refusal changed ./vendor/ (the tag's documents were dropped before the check):"
        f"\n{output}")


def test_a_successful_build_refreshes_the_wheel_and_all_four_documents(tmp_path):
    remote = _remote(tmp_path, docs=True)
    consumer = _consumer(tmp_path)
    _seed_vendor(consumer)

    code, _stdout, output = _run(consumer, remote, [NEW_WHEEL], TAG, LARKDOCIO_NO_DIST="1")

    assert code == 0, f"the healthy build path refused:\n{output}"
    after = _snapshot(consumer / "vendor")
    assert sorted(after) == sorted([NEW_WHEEL] + [f"{PKG}-{d}.md" for d in TAG_DOCS.values()])
    for relative, doc in TAG_DOCS.items():
        assert after[f"{PKG}-{doc}.md"] == f"{relative} at {TAG}\n".encode(), doc


def test_a_dist_branch_with_two_wheels_is_never_chosen_from_by_sort_order(tmp_path):
    """LD-694 F24 — the fast path picked ``ls | head -1`` of the dist clone; two wheels there
    is the same refusal-not-guess as everywhere else, so the run falls back to building."""
    # The matching wheel sorts FIRST, so ``head -1`` would have taken it without a word about
    # the second candidate beside it — which is exactly the guess the docs say never happens.
    other = f"{PKG}-{NEW_VER}.post1-py3-none-any.whl"
    remote = _remote(tmp_path, dist_branch="dist", dist_wheels=[NEW_WHEEL, other])
    consumer = _consumer(tmp_path)

    code, stdout, output = _run(consumer, remote, [NEW_WHEEL], TAG)

    assert code == 0, f"the fallback build path refused:\n{output}"
    assert "fast path" not in output.split("Vendored:")[-1], output
    assert "build-from-tag" in output, f"the two-wheel dist clone was not refused:\n{output}"
    assert _vendored(consumer) == [NEW_WHEEL]


def test_a_dist_wheel_vendored_with_NO_tag_to_check_against_says_so(tmp_path):
    """Round 9 (Z20): no tag named and none on the remote — the fast path has no version to
    compare the dist wheel with. It still serves the wheel, and it now says the check was
    not made instead of passing over the edge silently."""
    remote = _remote(tmp_path, dist_branch="dist", dist_wheel=NEW_WHEEL)
    _git(remote, "tag", "-d", TAG)
    consumer = _consumer(tmp_path)

    code, _stdout, output = _run(consumer, remote, [])

    assert code == 0, output
    assert _vendored(consumer) == [NEW_WHEEL]
    assert "is NOT checked against a tag" in output, output
