"""Guards for the mutation meter (LD-018; amended by LD-504).

The mutation meter is a *tooling* deliverable, not a product-behavior change: an
optional-extra `mutmut` dependency, a `[tool.mutmut]` scope pinning mutation to
`blocks/` + `read/`, and an **advisory** wrapper (`scripts/mutation-check.sh`)
that is deliberately NOT wired into `verify.sh`/`pytest`/CI (the LD-007
self-test-harness precedent). These tests pin those invariants so the meter's
advisory-only posture cannot silently regress into a gate, and so the dep
+ scope stay declared.

**LD-504 moved mutmut out of the `dev` extra into its own `mutation` extra**, and
added the guard at the bottom of this file asserting `setproctitle` — a transitive
mutmut dependency — is not importable in the environment that runs the suite. The
reason is a measurement, not tidiness: see that guard's docstring and the
comment on `pyproject.toml`'s `mutation` extra (the diagnosis write-up itself was a private
record and is retired).

They intentionally do NOT run mutmut (a full run is minutes long and needs the
`mutants/` scratch tree) — the executed baseline lives as a committed report
under `dev/`, per the issue AC.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import private_tree  # noqa: E402  (LD-685)

import tomllib  # stdlib from 3.11 — the project floor since LD-713 (was a <3.11 shim)

_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT = _ROOT / "pyproject.toml"
_WRAPPER = _ROOT / "scripts" / "mutation-check.sh"
_VERIFY = _ROOT / "scripts" / "verify.sh"


#: Where a CI configuration for THIS repository can live, as glob patterns relative to the
#: repo root. Derived rather than hand-pinned to one filename: LD-677 retired the old CI config,
#: and the guard below used to read that ONE path and
#: ``pytest.skip`` when it was absent — so the retirement would have converted a real check
#: into a permanent skip, green because it read nothing. Whatever CI this repository grows
#: next is matched here without editing the guard.
#:
#: Only root-level configuration is matched: a pipeline template shipped FOR a consumer to
#: include in THEIR pipeline would not run against this repository, and Decision Log #3 is
#: about this repository's own CI.
_CI_CONFIG_GLOBS = (
    "*.yml", "*.yaml",                      # .ci-pipeline.yml, azure-pipelines.yml, .drone.yml, …
    ".github/workflows/*.yml", ".github/workflows/*.yaml",
    ".circleci/*.yml", ".circleci/*.yaml",
    ".buildkite/*.yml", ".buildkite/*.yaml",
    "Jenkinsfile",
)


def _ci_config_paths(root=_ROOT):
    """Every CI configuration file for the repository rooted at ``root``.

    Takes ``root`` so the derivation itself is testable against a throwaway tree — see
    :func:`test_the_ci_config_derivation_is_not_inert`. A guard whose population can silently
    become empty is only honest if something else proves the population *finder* still works.
    """
    found = set()
    for pattern in _CI_CONFIG_GLOBS:
        found.update(p for p in root.glob(pattern) if p.is_file())
    return sorted(found)

# When mutmut runs the suite it copies tests/ into a throwaway `mutants/` tree
# and runs pytest with that tree as the repo root — but it does NOT copy
# scripts/ or the repo's CI configuration. These guards assert the REAL repo's layout, cover
# no larkdocio source, and would spuriously fail (aborting the mutation run's
# stats phase) inside that sandbox. Skip them there; they still run in the real
# suite. The sandbox is unambiguous: the copied tree's root is named `mutants`.
#
# LD-504 relies on this exemption for a second, sharper reason. The setproctitle
# guard at the bottom of this file asserts setproctitle is NOT importable — but the
# mutation environment installs mutmut on purpose, so setproctitle IS importable
# there. A guard reddening inside `mutants/` would report every mutant as "killed"
# and silently turn the meter into a liar. Placing it in this module puts it behind
# the same one-line sandbox skip, which is why it lives here and not in a file of
# its own. Outside the sandbox it is a plain, unmarked, unconditional test of the
# default offline suite on every platform.
_IN_MUTMUT_SANDBOX = _ROOT.name == "mutants"
pytestmark = pytest.mark.skipif(
    _IN_MUTMUT_SANDBOX,
    reason="meter guard tests assert real-repo layout; skipped inside mutmut's mutants/ sandbox",
)


def _pyproject() -> dict:
    return tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))


# --- AC1: mutmut is an opt-in TOOLING dependency, never a runtime one -------
# SUPERSESSION (LD-504, CLAUDE.md § Supersession — preserve the reason, replace
# only the conclusion). THE REASON IS UNCHANGED and still enforced below: mutmut
# is a development tool, it must never become a runtime dependency, and it must
# never ship in the wheel. What LD-504 changed is only WHICH EXTRA HOLDS IT — it
# left `dev` for its own `mutation` extra, because installing it into the suite's
# own environment drags in `setproctitle` and pytest-xdist then wedges macOS
# desktops (the measurement is in this file's setproctitle guard below, and in the
# comment on pyproject.toml's `mutation` extra). So the assertion moved one word
# and got STRONGER: mutmut is in `mutation`, ABSENT from `dev`, and absent from
# runtime. Do not "simplify" this back to "mutmut is somewhere in some extra" —
# `dev` is the extra ./setup.sh installs, and that is the whole point.

def _dist_names(reqs):
    return {req.split()[0].split("=")[0].split(">")[0].split("<")[0] for req in reqs}


def test_mutmut_is_a_dev_only_dependency():
    """Transformed by LD-504, and it KEEPS ITS NAME on purpose: "dev-only" is the
    REASON, which did not change — mutmut is a development tool, never a runtime
    dependency, never in the wheel. What moved is only which optional extra declares
    it, so the name stays and the assertions get stricter. (Note the distinction the
    name does NOT make: dev-**only** means "not runtime". It does not mean "in the
    `dev` extra" — after LD-504 it is specifically NOT in `dev`, because `dev` is what
    ./setup.sh installs.)"""
    data = _pyproject()
    extras = data["project"]["optional-dependencies"]

    # The conclusion LD-504 superseded: mutmut lives in `mutation`, not in `dev`.
    assert "mutation" in extras, (
        "no [project.optional-dependencies].mutation extra — LD-504 moved mutmut out of "
        "`dev` into its own extra so ./setup.sh stops installing setproctitle. See "
        "the comment on pyproject.toml's `mutation` extra"
    )
    assert "mutmut" in _dist_names(extras["mutation"]), \
        f"mutmut not in the [mutation] extra: {extras['mutation']}"
    assert "mutmut" not in _dist_names(extras["dev"]), (
        f"mutmut is back in the [dev] extra: {extras['dev']} — `dev` is what ./setup.sh "
        "installs, so this re-arms the setproctitle/launchservicesd freeze LD-504 fixed. "
        "It belongs in the `mutation` extra; see the comment on pyproject.toml's `mutation` extra"
    )

    # The REASON, unchanged since LD-018: never a runtime dependency, never in the wheel.
    runtime = data["project"]["dependencies"]
    assert not any("mutmut" in req for req in runtime), \
        "mutmut leaked into runtime dependencies; it is a development tool only"


# --- AC2 / scope: [tool.mutmut] pins mutation to blocks/ + read/ + model/ ---
# LD-033 (R-S0 net) extended the scope to model/*.py: T2 moved the single
# serializer into model/renderer.py, previously unseen by the meter. Extending
# scope RAISES the honest overall 70.1% → 77.8% (renderer 96.0%).

def test_mutmut_config_scopes_mutation_to_blocks_read_and_model():
    data = _pyproject()
    cfg = data.get("tool", {}).get("mutmut")
    assert cfg is not None, "missing [tool.mutmut] config"
    # Whole package is copied so imports resolve; mutation is scoped via only_mutate.
    assert cfg["source_paths"] == ["src/larkdocio"], \
        f"source_paths must copy the whole package for import resolution: {cfg.get('source_paths')}"
    only = cfg.get("only_mutate", [])
    joined = " ".join(only)
    assert "src/larkdocio/blocks/" in joined and "src/larkdocio/read/" in joined \
        and "src/larkdocio/model/" in joined, \
        f"only_mutate must scope mutation to blocks/ + read/ + model/: {only}"
    # And must NOT mutate anything outside that scope (e.g. cli.py, auth.py, write/).
    assert all(("/blocks/" in p or "/read/" in p or "/model/" in p) for p in only), \
        f"only_mutate escapes the blocks/+read/+model/ scope: {only}"


# --- AC2: the wrapper exists, is executable, advisory, and NOT wired in -----

@private_tree.citations
def test_wrapper_exists_and_is_executable():
    import os
    assert _WRAPPER.is_file(), "scripts/mutation-check.sh is missing"
    assert os.access(_WRAPPER, os.X_OK), "scripts/mutation-check.sh is not executable"


@private_tree.kit
def test_wrapper_is_bash_syntax_clean():
    proc = subprocess.run(["bash", "-n", str(_WRAPPER)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, f"bash -n failed:\n{proc.stderr}"


@private_tree.kit
def test_wrapper_header_documents_advisory_on_demand():
    text = _WRAPPER.read_text(encoding="utf-8").lower()
    assert "advisory" in text, "header must document the wrapper is advisory"
    assert "on-demand" in text or "on demand" in text, \
        "header must document it is on-demand only"
    # It must state it is NOT a gate / NOT wired into verify/pytest/CI.
    assert "not a gate" in text or "not wired" in text or "never a gate" in text, \
        "header must state it is not a gate"


def test_wrapper_not_wired_into_verify():
    assert "mutation-check" not in _VERIFY.read_text(encoding="utf-8"), \
        "verify.sh must NOT call mutation-check.sh (advisory only)"
    assert "mutmut" not in _VERIFY.read_text(encoding="utf-8"), \
        "verify.sh must NOT invoke mutmut (advisory only)"


def test_wrapper_not_wired_into_ci():
    """No CI configuration in this repository may invoke the mutation meter.

    **This test does not skip when there is no CI configuration**, and that is the point.
    It used to read one hard-coded CI config path and ``pytest.skip`` when it was
    missing; LD-677 then retired that file, which would have turned this guard into a
    permanent skip — green because it read nothing, the defect class this repository files
    bugs about. With the population derived, the claim "no CI invokes the meter" is simply
    TRUE over an empty set, and the moment a CI file returns it is read automatically with no
    edit here. :func:`test_the_ci_config_derivation_is_not_inert` is what stops an empty
    population from hiding a broken finder.
    """
    offenders = []
    for path in _ci_config_paths():
        body = path.read_text(encoding="utf-8")
        if "mutation-check" in body or "mutmut" in body:
            offenders.append(str(path.relative_to(_ROOT)))
    assert not offenders, (
        f"these CI configs invoke the mutation meter: {offenders}. CI must NOT run it "
        "(advisory only, never a gate, per Decision Log #3)."
    )


def test_the_ci_config_derivation_is_not_inert(tmp_path):
    """The finder still finds — proved against a throwaway tree, not against this repo's.

    Without this arm, :func:`test_wrapper_not_wired_into_ci` would pass identically whether
    the repository has no CI or the derivation is broken and returns nothing. Here the tree
    is built to contain CI files, so an inert finder reddens.
    """
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".circleci").mkdir()
    planted = {
        tmp_path / ".ci-pipeline.yml": "stages: [test]",
        tmp_path / ".github" / "workflows" / "ci.yml": "on: push",
        tmp_path / ".circleci" / "config.yml": "version: 2.1",
        tmp_path / "Jenkinsfile": "pipeline {}",
    }
    for path, body in planted.items():
        path.write_text(body, encoding="utf-8")
    # A non-CI file that must NOT be collected, so the finder is shown to discriminate.
    (tmp_path / "notes.md").write_text("not a pipeline", encoding="utf-8")

    found = set(_ci_config_paths(tmp_path))
    assert found == set(planted), (
        f"the CI-config derivation is inert or over-broad: found {sorted(found)}, "
        f"expected {sorted(planted)}"
    )


def test_the_repo_has_no_ci_config_and_that_is_recorded(tmp_path):
    """Pin the CURRENT fact, so re-introducing CI is a deliberate, visible act.

    LD-677 retired the old CI config and its AC4 forbids this issue adding a replacement.
    Recording the resulting state as an assertion means a future CI file reddens HERE — a
    one-line update with a reason — rather than arriving unnoticed beside a meter guard whose
    population silently grew. Not a ban on CI: a notification that it arrived.
    """
    present = [str(p.relative_to(_ROOT)) for p in _ci_config_paths()]
    assert present == [], (
        f"this repository now carries CI configuration: {present}. That is fine — but update "
        "this test deliberately, and check that test_wrapper_not_wired_into_ci still says what "
        "you want it to say about the new pipeline (LD-677 AC4)."
    )


# =============================================================================
# LD-504 — the wrapper runs from its OWN virtualenv, structurally
# =============================================================================

_MUT_VENV_DIRNAME = ".venv-mutation"


def _wrapper_text():
    return _WRAPPER.read_text(encoding="utf-8")


def _wrapper_code_lines():
    """The wrapper's executable lines — comments and blank lines dropped.

    The claims below are about what the script DOES, so a comment that *mentions*
    `.venv` (the header explains at length why it must never install there) must
    not read as a code path that touches it.
    """
    lines = []
    for raw in _wrapper_text().splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(raw)
    return lines


@private_tree.kit
def test_ld504_wrapper_declares_its_own_venv_and_it_is_not_the_suite_venv():
    code = "\n".join(_wrapper_code_lines())
    assert _MUT_VENV_DIRNAME in code, (
        f"scripts/mutation-check.sh must build its own virtualenv ({_MUT_VENV_DIRNAME}/); "
        "LD-504 forbids the meter from sharing the suite's env"
    )
    # It resolves that path from a literal, not from an argument or an env override.
    assert 'MUT_VENV="$REPO_ROOT/.venv-mutation"' in code, (
        "the meter's env must be a HARDCODED path — an argument or env override could "
        "resolve it to the suite venv, which is the defect LD-504 fixed"
    )


@private_tree.kit
def test_ld504_no_code_path_installs_anything_into_the_suite_venv():
    """AC4 read as a property, not a run: every `pip install` in the wrapper targets
    the meter's own interpreter, and no line points pip at `.venv`."""
    offenders = []
    for line in _wrapper_code_lines():
        if "pip install" not in line:
            continue
        # Backslash-escaped quotes inside an `echo` hint mean the same thing as the
        # bare form, so compare on the unescaped text — the hints must also point at
        # the meter's interpreter and never at the suite venv.
        unescaped = line.replace('\\"', '"')
        # Every install must go through "$PY", which is bound to the meter's env.
        if '"$PY" -m pip install' not in unescaped:
            offenders.append(line.strip())
    assert not offenders, (
        "these `pip install` lines in scripts/mutation-check.sh do not go through the "
        f"meter's own interpreter: {offenders}"
    )
    # And nothing anywhere in the executable body names the suite venv as an install
    # target. `SUITE_VENV` exists only to be REFUSED, so allow its declaration and the
    # equality guard, and forbid a pip/venv invocation that mentions it.
    for line in _wrapper_code_lines():
        if ".venv/" in line or line.strip().endswith(".venv") or '/.venv"' in line:
            assert "SUITE_VENV=" in line or "$SUITE_VENV" in line, (
                f"a wrapper code line targets the suite venv directly: {line.strip()!r}"
            )
            assert "pip install" not in line and "-m venv" not in line, (
                f"a wrapper code line installs into the suite venv: {line.strip()!r}"
            )


@private_tree.kit
def test_ld504_the_meter_run_turns_xdist_DISTRIBUTION_off():
    """The meter's env must carry `dev` too — `addopts` hardcodes `-n auto` and pytest
    cannot parse it without pytest-xdist installed, so a `[mutation]`-only env would
    fail every mutant with "unrecognized arguments: -n". The price of having xdist
    beside mutmut there is that setproctitle is importable in THAT env, so the run
    must disable distribution: `-n0` means no worker is ever started, so the rename
    xdist would do twice per test never happens. Dropping this export would restore
    the LD-504 freeze for the length of a (minutes-long) meter run."""
    code = "\n".join(_wrapper_code_lines())
    assert "PYTEST_ADDOPTS" in code and "-n0" in code, (
        "scripts/mutation-check.sh must export PYTEST_ADDOPTS with `-n0` so the meter's "
        "own suite runs start no xdist worker and therefore never call setproctitle"
    )
    assert "export PYTEST_ADDOPTS=" in code, \
        "the -n0 override must be EXPORTED so mutmut's pytest subprocesses inherit it"


@private_tree.kit
def test_ld504_wrapper_refuses_if_its_env_ever_resolves_to_the_suite_venv():
    code = "\n".join(_wrapper_code_lines())
    assert '[ "$MUT_VENV" = "$SUITE_VENV" ]' in code, (
        "the wrapper must carry the belt-and-braces refusal: if a future edit makes the "
        "meter's env equal the suite venv, it exits instead of installing"
    )


@private_tree.kit
def test_ld504_the_dev_extra_hint_is_gone_and_the_mutation_extra_is_the_instruction():
    """The old fallback hint — `pip install -e ".[dev]"` — is now the exact instruction
    that re-arms the freeze, so it must not be in the file at all."""
    text = _wrapper_text()
    assert '.[dev]' not in text, (
        'scripts/mutation-check.sh still tells the reader to `pip install -e ".[dev]"` — '
        "that instruction re-installs mutmut into the suite env and re-arms the "
        "setproctitle/launchservicesd freeze (LD-504)"
    )
    assert "[mutation]" in text, \
        "the wrapper must name the `mutation` extra as where mutmut comes from"


@private_tree.kit
def test_ld504_wrapper_header_names_the_mutation_extra_not_the_dev_extra():
    """AC6: the header's own dependency claim is corrected in the same change."""
    header = "\n".join(
        ln for ln in _wrapper_text().splitlines() if ln.startswith("#"))
    assert "optional-dependencies].mutation" in header, (
        "the wrapper header must say mutmut lives in the `mutation` extra"
    )
    assert "optional-dependencies].dev" not in header, (
        "the wrapper header still claims mutmut is a `dev` extra — corrected by LD-504"
    )
    assert "dev/2026-08-18-verify-beachball-diagnosis.md" in header, \
        "the header must cite the diagnosis that moved the dependency"


def test_ld504_the_meters_env_is_gitignored():
    ignored = (_ROOT / ".gitignore").read_text(encoding="utf-8")
    import re as _re
    assert _re.search(rf"^{_re.escape(_MUT_VENV_DIRNAME)}/?$", ignored, _re.M), (
        f"{_MUT_VENV_DIRNAME}/ is not gitignored — the meter's env would show up as "
        "untracked repository content"
    )


# =============================================================================
# LD-504 — THE GUARD: setproctitle must not be importable where the suite runs
# =============================================================================

def test_setproctitle_is_absent_from_the_test_environment():
    """pytest-xdist renames each worker process to the test currently running IF
    `setproctitle` happens to be importable — `xdist/remote.py:32` imports it
    opportunistically inside a try/except ImportError whose fallback is a no-op, and
    `:224` / `:230` (via `worker_title()` at `:60`) call it TWICE PER TEST.

    On macOS that rename is not a local operation. It is
    `_LSSetApplicationInformationItem` -> `_LSSetApplicationInformation` ->
    `LSClientToServerConnection::sendWithReply` ->
    `xpc_connection_send_message_with_reply_sync`: a SYNCHRONOUS XPC round-trip into
    `launchservicesd`, which serialises on a single dispatch queue AND broadcasts an
    "application name changed" notification that makes every running AppKit app
    (`-[NSMenuBarDisplayManager _applicationNameChanged:]` ->
    `-[NSRunningApplication _fetchDynamicProperties]` -> `_LSCopyApplicationInformation`)
    synchronously query LaunchServices back. So the cost is
    **O(tests x running applications)** — which is why it reproduced on a working
    desktop and never in a headless test.

    MEASURED on a macOS desktop during one ordinary
    `./scripts/verify.sh`: **7,333 turnstile-blocked samples** waiting on
    `launchservicesd` against 48 for the next-worst blocker; 148.1 s of daemon CPU
    (2.00 cores) inside a 74 s run; `loginwindow`, the menu bar, Terminal, the IDE,
    the browser and the chat client all blocked — **the whole desktop frozen for the
    length of the run** — while the machine used only about half of its cores. Removing
    `setproctitle` alone: 65.2 s daemon CPU (0.96 cores), and no freeze, confirmed by
    direct observation.

    Nothing in `src/`, `tests/` or `scripts/` uses `setproctitle`. It is pure
    collateral: it arrives only as a transitive dependency of `mutmut`, the advisory,
    on-demand mutation meter that is never a gate. So it has no reason to be in any
    environment that runs this suite, and this test is what keeps it out.

    Platform-independent on purpose: the pain is macOS-specific, the declaration is
    not. A Linux CI carrying `setproctitle` would re-arm the trap for the next mac.
    (The one exemption is mutmut's own `mutants/` sandbox, where mutmut IS installed
    by design — this module's `pytestmark` skips there, so the meter is not corrupted
    by a guard that "kills" every mutant.)
    """
    import importlib.util

    assert importlib.util.find_spec("setproctitle") is None, (
        "setproctitle is importable in this environment, so pytest-xdist will rename "
        "every worker twice per test and each rename is a synchronous XPC call into "
        "macOS launchservicesd — measured at 7,333 turnstile-blocked samples and a "
        "fully frozen desktop for the length of a verify.sh run.\n"
        "It is not ours: it comes in as a transitive dependency of mutmut. mutmut "
        "belongs to the `mutation` extra "
        "([project.optional-dependencies].mutation), NEVER to `dev`, and "
        "scripts/mutation-check.sh installs it into its own virtualenv "
        "(.venv-mutation/).\n"
        "Fix: `pip uninstall -y setproctitle mutmut` in this environment, and run the "
        "meter via ./scripts/mutation-check.sh instead.\n"
        "The measurements are in the comment on pyproject.toml's `mutation` extra."
    )

# --- LD-511 AC4: `also_copy` stays honest against the failure mode it fixes -
#
# REACH, STATED HONESTLY: this catches exactly the shape of LD-511's own
# defect — a MODULE-SCOPE (top-level, i.e. NOT nested in a function/class)
# assignment whose value calls `.read_text(` / `.read(` on an expression that
# names a repo-root file. That is the shape that makes mutmut's whole
# stats-collection run abort at import (a `pytest` collection error, not a
# single test failure) inside the throwaway `mutants/` tree, because that
# tree only gets `also_copy` entries beyond the package + tests/ +
# pyproject.toml (mutmut copies those three unconditionally).
#
# WHAT THIS DOES NOT CATCH (do not assume it does):
#   - A `Path` bound at module scope whose `.read_text()` call is deferred
#     into a test function or fixture body (e.g. BLOCKS.md's own
#     `_BLOCKS_MD` in tests/test_blocks_md_matrix.py) — a DIFFERENT failure mode (one test
#     errors when it runs; the whole stats run does not abort at collection).
#   - A file read only reachable via a `@pytest.mark.parametrize(...)`
#     argument list computed at collection time (LD-511's own smoke run hit
#     exactly this for `tests/captures/base-study/captures/*.json` — a real, separate,
#     OUT-OF-SCOPE defect this guard deliberately does not chase; see the
#     LD-511 Handoff).
#   - Any read inside an imported helper module's OWN functions (only its
#     module-level statements are swept, same rule as for test files).
# A guard whose claimed reach exceeds this WOULD be worse than none (the
# charter's Phase-4 lesson) — this one is scoped to say only what it proves.
def test_also_copy_covers_every_module_scope_root_doc_read():
    import ast

    cfg = _pyproject()
    also_copy = set(cfg.get("tool", {}).get("mutmut", {}).get("also_copy", []))

    # Candidate repo-root docs a test module could plausibly read at import
    # time. Deliberately a closed, small, named list (not "every file in the
    # repo") — the same set LD-511's own census walked by hand.
    candidates = (
        "BASE.md", "BLOCKS.md", "SHEETS.md", "DRIVE.md", "PERMISSIONS.md",
        "README.md", "CHANGELOG.md", "RELEASE_NOTES.md",
        "requirements/DECISIONS.md",
    )

    offenders = []
    for path in sorted((_ROOT / "tests").rglob("*.py")):  # LD-654: population must be recursive
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for node in tree.body:  # module scope ONLY — not nested defs/classes
            if not isinstance(node, ast.Assign):
                continue
            call = node.value
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and call.func.attr in ("read_text", "read")):
                continue
            # Does the call chain mention one of the candidate filenames as a
            # string literal anywhere in its receiver expression?
            literals = {n.value for n in ast.walk(call.func.value)
                        if isinstance(n, ast.Constant) and isinstance(n.value, str)}
            for candidate in candidates:
                name = candidate.rsplit("/", 1)[-1]
                if name in literals and candidate not in also_copy:
                    offenders.append(f"{path.name}:{node.lineno} reads {candidate!r} "
                                      f"at module scope but it is not in also_copy")

    assert not offenders, (
        "also_copy is missing an import-time root-doc read (LD-511's defect shape):\n"
        + "\n".join(offenders)
    )
