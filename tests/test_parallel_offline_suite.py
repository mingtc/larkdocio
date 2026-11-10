# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""LD-353 — the offline suite runs under ``pytest-xdist -n auto``; the
``live`` / ``zoo`` / ``live_write`` rings stay SERIAL (seat ruling in the issue).

These guards pin the WIRING, not the runtime: that the dep is dev-only, that
``addopts`` carries ``-n auto`` beside the unchanged default ``-m`` expression,
that the ring-selection → serial decision is the one the seat ruled, and that
CLAUDE.md's house rule carries the maintainer's 2026-08-08 carve-out that makes the dep
legal. Two subprocess probes prove the wiring end-to-end: a plain invocation
really gets xdist workers, and ``-m live`` really does not.
"""

import ast
import contextlib
import os
import pathlib
import re
import subprocess
import tempfile
import sys
import tomllib
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = Path(__file__).resolve().parent


def _pyproject():
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


# --- AC1: pytest-xdist is a DEV-only dependency -----------------------------

def test_ac1_xdist_is_in_the_dev_extra():
    dev = _pyproject()["project"]["optional-dependencies"]["dev"]
    names = [re.split(r"[<>=!~;\s]", req, maxsplit=1)[0] for req in dev]
    assert "pytest-xdist" in names, f"pytest-xdist not in the [dev] extra: {dev}"


def test_ac1_xdist_never_reaches_the_wheels_runtime_dependencies():
    runtime = _pyproject()["project"]["dependencies"]
    assert not any("xdist" in req for req in runtime), (
        "pytest-xdist leaked into [project] dependencies — no consumer of the "
        f"wheel may gain a dependency from LD-353: {runtime}"
    )


def test_ac1_the_dev_extra_entry_carries_a_comment_saying_what_it_is_for():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines() if "pytest-xdist" in ln)
    assert "#" in line and len(line.split("#", 1)[1].strip()) > 10, (
        f"the pytest-xdist dev-extra line needs a one-line purpose comment: {line!r}"
    )


def test_ac1_xdist_is_actually_installed_in_this_environment():
    pytest.importorskip("xdist", reason="pytest-xdist must be installed via .[dev]")


# --- AC2: every ordinary offline invocation parallelizes --------------------

def _addopts():
    return _pyproject()["tool"]["pytest"]["ini_options"]["addopts"]


def test_ac2_addopts_wires_n_auto():
    assert "-n auto" in _addopts(), (
        "addopts must carry `-n auto` so a plain `pytest` / `verify.sh` "
        f"parallelizes without anyone passing a flag: {_addopts()!r}"
    )


def test_ac2_addopts_still_carries_the_unchanged_default_marker_expression():
    assert "-m 'not live and not zoo and not live_write'" in _addopts()


def test_ac2_verify_sh_still_delegates_to_a_plain_pytest_invocation():
    """verify.sh must not re-derive the parallelism (or opt out of it): it runs
    bare `python -m pytest`, so it inherits addopts like everyone else."""
    text = (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8")
    assert 'run_gate "pytest"        "$PY" -m pytest\n' in text
    assert "-p no:xdist" not in text and "-n 0" not in text


# --- AC3: the live / zoo / live_write rings stay SERIAL ---------------------

from conftest import ring_selection_requires_serial  # noqa: E402


@pytest.mark.parametrize(
    "markexpr,serial",
    [
        ("not live and not zoo and not live_write", False),  # the default offline ring
        ("live", True),
        ("zoo", True),
        ("live_write", True),
        ("live or zoo", True),
        ("live_write and not zoo", True),
        ("not live", False),
        ("", True),        # `-m ""` selects everything, live rings included
        (None, True),
    ],
)
def test_ac3_ring_selection_decision_table(markexpr, serial):
    assert ring_selection_requires_serial(markexpr) is serial


# --- the two end-to-end probes (AC2 / AC3) ----------------------------------

_PROBE_PARALLEL = """
import os


def test_probe_runs_on_an_xdist_worker():
    assert os.environ.get("PYTEST_XDIST_WORKER"), "not running under an xdist worker"
"""

_PROBE_SERIAL = """
import os
import pytest


@pytest.mark.live
def test_probe_runs_in_the_master_process():
    assert not os.environ.get("PYTEST_XDIST_WORKER"), "live ring was parallelized"
"""


@contextlib.contextmanager
def _probe_module(source):
    """Write the one-test probe module in a tempdir **outside the repository**.

    It used to be written into ``tests/`` so the repo's ``addopts`` and
    ``tests/conftest.py`` would apply to the child run — at the price of making
    ``tests/`` a shared MUTABLE directory that every tree-scanning guard walks as
    an immutable corpus (LD-359). The child is now pointed back at the repo's
    config explicitly instead (see ``_run_probe``), so nothing transient is ever
    planted inside the tree anyone scans.
    """
    with tempfile.TemporaryDirectory(prefix="larkdocio-probe-") as tmp:
        probe = pathlib.Path(tmp).resolve() / f"probe_ld353_{uuid.uuid4().hex}.py"
        probe.write_text(source, encoding="utf-8")
        yield probe


def _run_probe(source, extra_args, env_extra=None):
    """Run a one-test probe module with the repo's own config and conftest applied.

    The probe lives outside the repository (``_probe_module``), so the child is
    given the pieces it used to inherit by location: ``-c pyproject.toml`` for
    ``addopts``, ``--rootdir`` for the repo, and ``-p conftest`` (with ``tests/``
    on ``PYTHONPATH``) for the ring-serialization hook. The two end-to-end probes
    below are what prove that wiring: AC2 passes only if ``-n auto`` reached the
    child, AC3 only if ``tests/conftest.py`` did.
    """
    env = dict(os.environ)
    # These guards may themselves be running ON an xdist worker; the child must
    # not inherit that identity or the probe would read the PARENT's answer.
    for leaked in [k for k in env if k.startswith("PYTEST_XDIST")]:
        env.pop(leaked)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(TESTS_DIR)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    env.update(env_extra or {})
    with _probe_module(source) as probe:
        return subprocess.run(
            [sys.executable, "-m", "pytest", str(probe), "-p", "no:cacheprovider",
             "-c", str(ROOT / "pyproject.toml"), "--rootdir", str(ROOT),
             "-p", "conftest", *extra_args],
            cwd=ROOT, env=env, capture_output=True, text=True,
        )


def test_ac2_a_plain_invocation_really_runs_under_xdist_workers():
    # Cap `auto` at 2 workers for the probe — this asserts THAT xdist engaged,
    # not how wide it spread.
    res = _run_probe(_PROBE_PARALLEL, [], {"PYTEST_XDIST_AUTO_NUM_WORKERS": "2"})
    assert res.returncode == 0, res.stdout + res.stderr


def test_ac3_the_live_ring_really_runs_serially():
    res = _run_probe(_PROBE_SERIAL, ["-m", "live"])
    assert res.returncode == 0, res.stdout + res.stderr
    assert "gw0" not in res.stdout, f"xdist worker banner on the live ring:\n{res.stdout}"


# --- LD-359: the probe module never lands inside the scanned repository -----
# The probe used to be written into `tests/` so the repo's addopts and
# tests/conftest.py would apply to the child run. Under `-n auto` that made
# `tests/` a shared MUTABLE directory while other workers were AST-walking it as
# an immutable corpus (test_write_harness_double_ownership, and every other
# tree-scanning guard): glob → unlink → read = FileNotFoundError, i.e. a red
# `verify.sh` unrelated to what the guard guards. The probe now lives in a
# tempdir OUTSIDE the repository and the child is pointed back at the repo's
# config explicitly (`-c pyproject.toml --rootdir <repo> -p conftest`), which is
# why the two end-to-end probes above still prove what they proved: AC2 passes
# only if `addopts` (`-n auto`) reached the child, AC3 only if tests/conftest.py's
# serial hook did.


def test_ld359_the_probe_module_is_created_OUTSIDE_the_repository_tree():
    with _probe_module("def test_noop():\n    pass\n") as probe:
        assert probe.exists(), "the probe must exist for the duration of the child run"
        assert not probe.is_relative_to(ROOT), (
            f"the probe module is inside the repository ({probe}) — every tree-scanning "
            f"guard can glob it and then read it after the unlink (LD-359)"
        )
    assert not probe.exists(), "the probe outlived its context manager"


def test_ld359_no_write_in_this_module_targets_the_repository_tree():
    """AST guard: this module writes files at exactly ONE site, and that site's
    directory comes from ``tempfile`` — so no future transient can be planted in
    ``tests/`` by re-growing the old habit here."""
    tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    writers = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call) and (
                (isinstance(inner.func, ast.Attribute)
                 and inner.func.attr in {"write_text", "write_bytes", "mkdir"})
                or (isinstance(inner.func, ast.Name) and inner.func.id == "open")
            ):
                writers.add(node.name)
    assert writers == {"_probe_module"}, (
        f"this module must create files only inside _probe_module (a tempdir outside "
        f"the repo); found writes in {sorted(writers)}"
    )
    seam = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "_probe_module")
    used = {n.value.id for n in ast.walk(seam)
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
    assert "tempfile" in used, "_probe_module must build its directory with tempfile"


# --- AC6: the ONE isolation defect parallelism exposed ----------------------
# `python -m build` was run once PER PROCESS from REPO_ROOT, so 16 workers ran up
# to 16 concurrent builds over ONE shared in-tree setuptools scratch
# (`build/` staging + `src/larkdocio.egg-info/SOURCES.txt`). Observed failure:
#   error: [Errno 2] No such file or directory:
#          'larkdocio-<version>/src/larkdocio/write/revision.py'
# — one build's sdist staging deleted out from under another's copy. Fixed (not
# skipped, not grouped) by making the packaging artifacts ONE per test RUN,
# shared across workers under a file lock and keyed by xdist's own run id.

import front_door  # noqa: E402


def test_ac6_the_session_artifact_dir_is_keyed_by_the_xdist_run_id(monkeypatch):
    monkeypatch.delenv("PYTEST_XDIST_TESTRUNUID", raising=False)
    assert front_door.session_artifact_dir() is None, (
        "outside an xdist run there is one process, so the per-process temp dir is correct"
    )
    monkeypatch.setenv("PYTEST_XDIST_TESTRUNUID", "deadbeef")
    shared = front_door.session_artifact_dir()
    assert shared is not None and "deadbeef" in shared.name


def test_ac6_every_worker_shares_ONE_build_instead_of_racing_its_own():
    sdist, wheel = front_door.packaging_artifacts()
    shared = front_door.session_artifact_dir()
    if shared is None:
        # Serial run: one process, so the per-process temp dir already IS the
        # run-shared one and there is nothing to race. Asserted rather than
        # SKIPPED so the offline count is identical either way (AC4) — and
        # re-arming here would cost a second whole `python -m build`.
        assert wheel.parent == sdist.parent
        return
    assert wheel.parent == shared and sdist.parent == shared, (
        "the artifacts must live in the run-shared dir, or workers are building "
        f"concurrently into the same repo scratch again: {wheel.parent} != {shared}"
    )
    # A second arming must REUSE, never rebuild — that is the property that
    # removes the race, so pin it on the artifact's own mtime.
    stamp = wheel.stat().st_mtime_ns
    front_door._ARTIFACTS.pop("pair", None)
    again_sdist, again_wheel = front_door.packaging_artifacts()
    assert (again_sdist, again_wheel) == (sdist, wheel)
    assert again_wheel.stat().st_mtime_ns == stamp, "the guard rebuilt instead of reusing"


# --- AC6, the SECOND isolation defect: the transient sdist staging dir ------
# `python -m build`'s sdist step stages the entire source tree in a TRANSIENT
# `larkdocio-<version>/` directory at REPO_ROOT before tarring it. Serially
# nothing ever saw it; under `-n auto` the other 15 workers are walking the tree
# at exactly that moment, so the staged COPY joined their corpora — the mention
# ratchet in test_permissions_docs fired at `117 <= 43` in 2 of 3 parallel runs.
# It is build output like `build/` and `dist/`, and it is not tracked, so every
# repo-walking corpus must disown it: the .gitignore-derived walk via .gitignore
# itself, the two hand-kept walks via `front_door.is_build_staging`.

import test_permissions_docs as perm_docs  # noqa: E402
import test_base_person_chat_addressability as person_docs  # noqa: E402
import private_tree  # noqa: E402  (LD-685)


# The two staging names below are DELIBERATELY implausible versions. What is under
# test is the *shape* the regex must recognise (a release triple, and a triple with a
# PEP 440 dev suffix) — never the version this repo happens to package. Naming the
# packaged version here freezes it, and `release.sh` gates BEFORE it bumps, so the next
# cut would redden this row on a trunk whose gates just passed (LD-372; the guard is
# `tests/test_version_bump_tolerance.py`). Keep them unreachable by any real bump.
@pytest.mark.parametrize("name,staging", [
    ("larkdocio-9.9.9", True),
    ("larkdocio-42.0.1.dev0", True),
    ("larkdocio", False),
    ("larkdocio.egg-info", False),
    ("src", False),
])
def test_ac6_build_staging_dir_is_recognised(name, staging):
    assert front_door.is_build_staging(name) is staging


def test_ac6_gitignore_disowns_the_transient_sdist_staging_dir():
    """The .gitignore-derived corpus (test_permissions_docs) prunes it because
    the repository's own ignore file disowns it — one declaration, honoured."""
    assert perm_docs._ignored("larkdocio-9.9.9")
    assert perm_docs._ignored("larkdocio-9.9.9/src/larkdocio/permissions.py")
    assert not perm_docs._ignored("src/larkdocio/permissions.py")


def test_ac6_front_door_repo_paths_disowns_the_transient_sdist_staging_dir():
    assert front_door._uncarried("larkdocio-9.9.9/README.md")
    assert not front_door._uncarried("README.md")


def test_ac6_person_mandate_corpus_disowns_the_transient_sdist_staging_dir():
    assert person_docs._out_of_tree("larkdocio-9.9.9/dev/downtime-queue.md")
    assert not person_docs._out_of_tree("dev/downtime-queue.md")


# --- AC8: the CLAUDE.md house-rule amendment lands in this same change ------

def _house_rule_clause():
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    i = text.index("**No new tooling dependencies")
    rest = text[i:]
    end = rest.find("\n- ", 1)
    return rest if end == -1 else rest[:end]


@private_tree.process
def test_ac8_house_rule_names_the_dev_only_pytest_plugin_carveout():
    clause = _house_rule_clause()
    assert "pytest-xdist" in clause and "pytest-testmon" in clause
    assert "dev-only" in clause
    assert "2026-08-08" in clause, "the amendment must name the maintainer ruling's date"


@private_tree.process
def test_ac8_house_rule_preserves_its_original_reason_and_the_rest_of_the_ban():
    clause = _house_rule_clause()
    # LD-336 precedent: preserve the REASON, supersede only the conclusion.
    assert "git + bash + python" in clause
    for banned in ("Node", "package.json", "node_modules"):
        assert banned in clause, f"the amendment dropped the {banned} ban"
    assert "runtime" in clause.lower(), "the amendment must still forbid new RUNTIME deps"


# --- AC9: the doc surface that states the dev extras stays true -------------

@private_tree.process
def test_ac9_project_md_dev_extras_clause_names_xdist():
    text = (ROOT / "PROJECT.md").read_text(encoding="utf-8")
    i = text.index("Dev extras:")
    rest = text[i:]
    end = rest.find("\n- ", 1)
    assert "pytest-xdist" in (rest if end == -1 else rest[:end])


# --- LD-355: the OTHER expensive setups are run-shared too -------------------
# LD-353 made the packaging artifacts ONE build per RUN. Two more expensive
# setups were still cached PER PROCESS, i.e. re-done by every xdist worker that
# happened to receive one of their tests (the default `--dist load` scatters a
# module's tests across workers, so "module-scoped" is not one setup):
#
#   * the PRISTINE-inputs wheel (`test_shipped_notes._built_wheel_record`) — a
#     second `python -m build`, wanted by FIVE modules; and
#   * the clean venv the installed-wheel guards probe — `python -m venv` plus an
#     offline `pip install`, built at THREE byte-identical sites; SIX of those
#     setups were observed in one `-n auto` run at ~5 s each.
#
# Both now go through `front_door.run_shared_artifact`, the same run-keyed,
# file-locked seam LD-353 built for `packaging_artifacts`. Nothing about what the
# consuming guards ASSERT changes — they get the same artifact, built once.


def test_ld355_the_pristine_wheel_is_produced_ONCE_PER_RUN_not_once_per_worker():
    """The pristine wheel is run-shared, and a second arming REUSES it.

    Pinned on the artifact's own mtime, exactly as the LD-353 guard above does:
    "same path" alone would also be true of a rebuild into a fixed location.
    """
    wheel = front_door.pristine_wheel()
    assert wheel.exists() and wheel.suffix == ".whl"
    mtime = wheel.stat().st_mtime_ns

    # (a) true in BOTH modes: a second arming reuses. Pinned on the artifact's own
    # mtime, exactly as the LD-353 guard above does — "same path" alone would also
    # be true of a rebuild into a fixed location.
    again = front_door.pristine_wheel()
    assert again == wheel and again.stat().st_mtime_ns == mtime, "it rebuilt"

    # (b) the cross-WORKER half, which only exists under xdist: the artifact is in
    # the run-shared dir, and a worker arriving with an empty in-process cache
    # (which is every worker but the first) still gets that one wheel.
    shared = front_door.session_artifact_dir()
    if shared is None:
        # Serial: one process, so the in-process cache proven in (a) already IS the
        # run-wide sharing. Asserted rather than SKIPPED so the offline count is
        # identical either way (LD-353 AC4).
        assert "pristine-wheel" in front_door._SHARED
        return
    assert shared in wheel.parents, (
        "the pristine wheel must live in the run-shared dir, or every worker is "
        f"paying for its own `python -m build` again: {wheel} not under {shared}"
    )
    front_door._SHARED.pop("pristine-wheel", None)
    cold = front_door.pristine_wheel()
    assert cold == wheel
    assert cold.stat().st_mtime_ns == mtime, "a cold worker rebuilt instead of reusing"


def test_ld355_the_pristine_wheel_is_NOT_the_packaging_artifacts_wheel():
    """The LD-221 carve-out survives the dedupe.

    `packaging_artifacts()` builds in REPO_ROOT, where `build/lib/` and the editable
    install's cached `SOURCES.txt` are present — either can make an in-wheel assertion
    pass over a declaration that is no longer there. The pristine wheel exists to be
    immune to exactly that, so sharing must NOT have collapsed the two into one.
    """
    _, packaged = front_door.packaging_artifacts()
    assert front_door.pristine_wheel() != packaged, (
        "the pristine wheel became the repo-root build's wheel — the residue immunity "
        "test_shipped_notes documents is gone (LD-221 AC-A3 forbids that narrowing)"
    )


#: The single module allowed to shell out to ``python -m venv``. Same rule, and the same
#: reason, as ``test_packaging._THE_BUILD_SITE``: "don't hand-roll a fourth clean venv" is
#: exactly what the next installed-wheel guard would re-invent from scratch — there were
#: THREE byte-identical constructions when LD-355 counted, at ~5 s each.
_THE_VENV_SITE = "tests/front_door.py"


def test_ld355_the_test_tree_creates_a_clean_venv_at_exactly_ONE_site():
    sites = front_door.argv_literal_sites("-m", "venv")
    assert [site.split(":")[0] for site in sites] == [_THE_VENV_SITE], (
        f"tests/ shells out to `python -m venv` at {sites} — it must happen at exactly "
        f"one site ({_THE_VENV_SITE}); route the rest through front_door.clean_wheel_venv()."
    )


def test_ld355_the_clean_venv_is_created_ONCE_PER_RUN_not_once_per_worker():
    """Same property as the pristine wheel, on the other expensive setup."""
    venv = front_door.clean_wheel_venv()
    python, console = venv["python"], venv["console"]
    assert python.exists() and console.exists()
    mtime = python.stat().st_mtime_ns

    again = front_door.clean_wheel_venv()
    assert again["python"] == python and python.stat().st_mtime_ns == mtime, "it rebuilt"

    shared = front_door.session_artifact_dir()
    if shared is None:
        assert "clean-venv" in front_door._SHARED
        return
    assert shared in python.parents
    front_door._SHARED.pop("clean-venv", None)
    cold = front_door.clean_wheel_venv()
    assert cold["python"] == python
    assert python.stat().st_mtime_ns == mtime, "a cold worker rebuilt instead of reusing"


def test_ld355_the_shared_venv_path_still_proves_the_INSTALLED_copy_answered():
    """The three consumers assert the probe's ``larkdocio.__file__`` sits under ``/venv/``
    (test_release_notes_accessor) or ``/v/`` (the two CLI guards). Those assertions are what
    make each arm evidence rather than decoration, so the shared venv keeps BOTH path
    components — and neither is satisfiable by the repo checkout, whose env dir is
    ``/.venv/`` (no ``/venv/`` substring) and which has no ``/v/`` component at all.
    """
    where = str(front_door.clean_wheel_venv()["python"])
    assert "/venv/" in where and "/v/" in where, where
    assert "/venv/" not in str(ROOT / ".venv") and "/v/" not in str(ROOT / ".venv")
