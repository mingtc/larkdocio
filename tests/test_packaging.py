"""Packaging tests — the console entrypoint resolves, and the artifacts' CONTENTS.

Three levels:
- the entrypoint target (`larkdocio.cli:cli`) imports and is a click command
  group exposing the `download`/`config` subcommands,
- it is declared as a `console_scripts` entry point in pyproject.toml; when the
  package is actually installed (CI / the verification venv), the entry point
  loads to that same object, and
- **what the built wheel and sdist actually CONTAIN** (LD-215). For the whole life
  of the project nothing asserted that: the sdist shipped 222 `tests/test_*.py`
  files — 3,917,577 B, 64% of the tarball — dragged in by setuptools' legacy
  default glob because the repo had no `MANIFEST.in`, and shipped WITHOUT
  `conftest.py` or `fixtures/`, so what presented as the project's verification
  surface could not be run. A one-line manifest with no regression net is one
  setuptools default-behavior change away from silently re-bloating, so the net
  lands with it, and it bites in BOTH directions: an unexpected member reddens,
  and an OWED member that disappeared reddens too — the six declared package-data
  files vanishing from the wheel is the more damaging of the two.

The allow-lists are DERIVED (`front_door.source_modules()` from the real `src/`
tree, `front_door.declared_package_data()` from `[tool.setuptools.package-data]`),
so a seventh declared file makes the guard follow the declaration instead of
crying wolf. The build happens ONCE per session inside
`front_door.packaging_artifacts()` — not a fourth `python -m build` site.
"""
import shutil
import tarfile
from pathlib import Path

import pytest

import front_door

_ROOT = Path(__file__).resolve().parent.parent


def test_entrypoint_target_imports_and_is_a_command_group():
    import click
    from larkdocio.cli import cli

    assert isinstance(cli, click.Group)
    assert set(cli.commands) >= {"download", "config"}


def test_console_script_declared_in_pyproject():
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'larkdocio = "larkdocio.cli:cli"' in text


def test_installed_console_script_loads_when_present():
    """When larkdocio is installed, its console_scripts entry point must load
    to the CLI group. Skipped from a bare source checkout (no metadata)."""
    import importlib.metadata as im

    try:
        eps = im.entry_points(group="console_scripts")
    except Exception:
        pytest.skip("entry-point metadata unavailable")
    matches = [e for e in eps if e.name == "larkdocio"]
    if not matches:
        pytest.skip("larkdocio not installed in this environment")
    from larkdocio.cli import cli

    assert matches[0].load() is cli


# --------------------------------------------------------------------------- #
# The manifest — prune-only, by assertion (LD-215 AC1/AC2)                     #
# --------------------------------------------------------------------------- #

def test_manifest_in_exists_at_the_repo_root():
    assert front_door.MANIFEST_IN.exists(), (
        "MANIFEST.in is missing. Without it setuptools' LEGACY DEFAULT sdist glob "
        "pulls tests/test*.py into the source distribution."
    )


def test_manifest_in_is_prune_only():
    """It contains ONLY exclusions — asserted, not eyeballed.

    `MANIFEST.in` is exactly the mechanism that could start shipping the root
    `CHANGELOG.md` / `RELEASE_NOTES.md` at sdist top level, disturbing the
    root-canonical + src-copy arrangement `pyproject.toml` documents. This issue
    deliberately does not: the file prunes and ships nothing.
    """
    directives = front_door.manifest_directives()
    assert directives, "MANIFEST.in carries no directives at all"
    offenders = [
        (command, argument) for command, argument in directives
        if command in front_door.MANIFEST_INCLUSION_DIRECTIVES
    ]
    assert not offenders, (
        f"MANIFEST.in must be PRUNE-ONLY; found inclusion directive(s): {offenders}"
    )
    assert all(
        command in ("prune", "exclude", "recursive-exclude", "global-exclude")
        for command, _ in directives
    ), f"unexpected non-exclusion directive in MANIFEST.in: {directives}"


#: The denial this issue made false. Asserted against WHITESPACE-NORMALIZED comment
#: prose, never the raw file: in `pyproject.toml` the sentence was hard-wrapped across
#: two comment lines (`…there is no` / `# MANIFEST.in here`), so a raw-literal check
#: forbids a string the file never contained and passes against the unfixed text. That
#: is a test-efficacy defect of exactly the kind this issue exists to close, so the
#: normalization is asserted to BITE below rather than trusted.
MANIFEST_DENIAL = "there is no MANIFEST.in here"

#: The real wrapped form of that sentence, as `pyproject.toml` carried it before this
#: issue. Kept verbatim so the guard is proven red against the text it must reject.
WRAPPED_DENIAL_BEFORE_LD215 = (
    "# canonical copies live at the repo ROOT (the ruled location; there is no\n"
    "# MANIFEST.in here). So the root file stays canonical and\n"
)


def test_pyproject_package_data_comment_does_not_deny_the_manifest():
    """The comment that documents the arrangement must not claim there is no manifest.

    A false comment inside the very file that documents the root-canonical +
    src-copy arrangement is how the arrangement rots.
    """
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert MANIFEST_DENIAL.lower() not in front_door.pyproject_comment_prose(text)
    assert "MANIFEST.in" in text, (
        "pyproject.toml's package-data comment should say what MANIFEST.in is for "
        "(pruning) and that it deliberately ships nothing."
    )


def test_the_manifest_denial_check_sees_through_line_wrapping():
    """The above must bite on the WRAPPED sentence, not only an unwrapped one.

    Red-proof for the normalization: the pre-LD-215 text is the input, and the
    forbidden phrase must be found in it. A raw `in text` check does not find it.
    """
    wrapped = WRAPPED_DENIAL_BEFORE_LD215
    assert MANIFEST_DENIAL not in wrapped, "the sentence really was split by wrapping"
    assert MANIFEST_DENIAL.lower() in front_door.pyproject_comment_prose(wrapped)


# --------------------------------------------------------------------------- #
# The sdist — allow-listed, both directions, forbidden trees named (AC1/AC4)   #
# --------------------------------------------------------------------------- #

def test_sdist_ships_no_development_tree():
    sdist, _ = front_door.packaging_artifacts()
    members = front_door.sdist_members(sdist)
    paths = list(members) + list(front_door.sdist_directories(sdist))
    leaked = front_door.leaked_trees(paths)
    assert not leaked, (
        f"the sdist leaks development tree(s) {leaked}: "
        + ", ".join(
            f"{tree}/ → {sum(1 for p in members if p == tree or p.startswith(tree + '/'))} "
            f"files, {sum(size for p, size in members.items() if p == tree or p.startswith(tree + '/'))} B"
            for tree in leaked
        )
    )


def test_sdist_carries_nothing_beyond_the_allow_list():
    sdist, _ = front_door.packaging_artifacts()
    members = front_door.sdist_members(sdist)
    unexpected = front_door.unexpected_sdist_members(members)
    assert not unexpected, (
        f"{len(unexpected)} unexpected sdist member(s): {unexpected[:10]}"
        + (" …" if len(unexpected) > 10 else "")
    )


def test_sdist_carries_everything_it_owes():
    """The other direction — an owed member that vanished."""
    sdist, _ = front_door.packaging_artifacts()
    missing = front_door.missing_sdist_members(front_door.sdist_members(sdist))
    assert not missing, f"the sdist is missing owed member(s): {missing}"


# --------------------------------------------------------------------------- #
# The wheel — the derived allow-list, both directions (AC3/AC4)                #
# --------------------------------------------------------------------------- #

def test_wheel_carries_nothing_beyond_the_derived_allow_list():
    _, wheel = front_door.packaging_artifacts()
    members = front_door.wheel_members(wheel)
    unexpected = front_door.unexpected_wheel_members(members)
    assert not unexpected, f"unexpected wheel member(s): {unexpected}"
    assert not [p for p in members if p.startswith("tests")], "the wheel leaks tests/"


def test_wheel_carries_every_declared_package_data_file():
    """A declared doc silently disappearing from the wheel is the worse regression.

    The expectation is DERIVED from `[tool.setuptools.package-data]`, so a seventh
    declared file widens it automatically.
    """
    _, wheel = front_door.packaging_artifacts()
    members = front_door.wheel_members(wheel)
    missing = front_door.missing_wheel_members(members)
    assert not missing, f"the wheel is missing owed member(s): {missing}"
    declared = front_door.declared_package_data()
    assert declared, "no package-data derived from pyproject.toml — the guard is inert"
    for path in sorted(declared):
        size, _crc = members[path]
        assert size == (_ROOT / "src" / path).stat().st_size, (
            f"{path} in the wheel differs in size from src/{path}"
        )


# --------------------------------------------------------------------------- #
# The OWED set is declaration-derived, not tree-derived (AC4, both directions) #
# --------------------------------------------------------------------------- #
#
# The defect this section closes: the first cut derived the wheel's owed set by
# GLOBBING `src/` for the declared patterns, so the expectation and the artifact
# were computed from the same working tree. `rm src/larkdocio/GUIDE.md`, rebuild →
# the wheel lost a declared shipped doc (222 KB, `guide()`'s whole payload) and the
# guard stayed GREEN, because the file left the expectation at the same instant it
# left the artifact. A missing-direction that can only ever be observed green is not
# a guard — the same lesson as the 222 files, one level up.
#
# So the owed names now come from `[tool.setuptools.package-data]` as DECLARED
# LITERALS (never retyped here — AC4's derivation requirement stands), and the disk
# is the thing CHECKED against them rather than the thing that defines them.

def test_declared_package_data_comes_from_the_declaration_not_the_filesystem():
    """The load-bearing property: a declared name survives its file disappearing.

    Passing a table naming a file that exists nowhere on disk must still yield that
    name. That is precisely what the globbing version could not do, and it is what
    makes `missing_wheel_members` able to report a vanished declared doc.
    """
    ghost = front_door.declared_package_data(table={"larkdocio": ["GHOST.md"]})
    assert ghost == {"larkdocio/GHOST.md"}
    assert not (_ROOT / "src" / "larkdocio" / "GHOST.md").exists()


def test_every_declared_package_data_file_resolves_on_disk():
    """The declaration and the tree must agree — the real-artifact bite.

    `rm src/larkdocio/GUIDE.md` reddens here (a declared name with no file) and in
    `missing_wheel_members`, where the old shape stayed silent.
    """
    unresolved = front_door.unresolved_package_data_literals()
    assert not unresolved, (
        "declared as package data in pyproject.toml but absent from src/: "
        f"{unresolved} — the wheel cannot ship what is not there"
    )


def test_deleting_a_real_declared_file_reddens_the_owed_set(tmp_path):
    """A REAL file deleted from a REAL tree — not a key deleted from a dict.

    The synthetic dict version proved the pure function and nothing about the
    derivation, which is how the hole reached review. Here the declaration is fixed
    text, the artifact's member list is derived from the tree (as a build is), and
    the file is removed from disk — the shape of the regression AC4 calls the more
    damaging of the two.
    """
    pkg = tmp_path / "src" / "larkdocio"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "GUIDE.md").write_text("# guide\n", encoding="utf-8")
    table = {"larkdocio": ["GUIDE.md"]}
    modules = {"larkdocio/__init__.py"}
    expected = front_door.wheel_expected_members(table=table, modules=modules)
    assert expected == {"larkdocio/__init__.py", "larkdocio/GUIDE.md"}

    def built_from_tree():
        """What a build of this tree would put in the wheel."""
        return {
            path.relative_to(tmp_path / "src").as_posix(): (path.stat().st_size, 0)
            for path in pkg.rglob("*") if path.is_file()
        }

    intact = built_from_tree()
    assert front_door.missing_wheel_members(intact, expected=expected) == []
    assert front_door.unresolved_package_data_literals(
        table=table, root=tmp_path / "src") == []

    (pkg / "GUIDE.md").unlink()          # the mutation: a real declared file, gone
    mutated = built_from_tree()
    assert "larkdocio/GUIDE.md" not in mutated
    assert front_door.missing_wheel_members(mutated, expected=expected) == [
        "larkdocio/GUIDE.md"
    ], "the owed set shrank with the tree — the derivation is still tree-derived"
    assert front_door.unresolved_package_data_literals(
        table=table, root=tmp_path / "src") == ["larkdocio/GUIDE.md"]


def test_the_sdist_owed_set_is_declaration_derived_too():
    """The sdist half ran off the same two disk-derived sets, so it had the same hole."""
    owed = front_door.sdist_expected_files(table={"larkdocio": ["GHOST.md"]})
    assert "src/larkdocio/GHOST.md" in owed


def test_no_declared_package_data_pattern_is_a_wildcard():
    """All six declarations are LITERAL names — and that is what makes the owed set real.

    A wildcard (`*.md`, `data/*`) has no name until the filesystem is consulted, so
    its expansion is tree-derived by construction and contributes nothing a
    missing-direction can catch. The answer, stated rather than left implicit: the
    day a wildcard is declared, whoever declares it decides HERE — either spell the
    files as literals (keeping the guard's owed half real), or accept that that one
    entry's owed half is disk-derived and record why. This test is the prompt; it is
    not a ban on wildcards, it is a ban on adding one silently.
    """
    assert front_door.declared_package_data_wildcards() == []
    assert front_door.declared_package_data_wildcards(
        table={"larkdocio": ["*.md", "config.json"]}
    ) == [("larkdocio", "*.md")], "the wildcard detector must actually detect one"


# --------------------------------------------------------------------------- #
# The guard bites — and cannot be silently skipped (AC5/AC6a)                  #
# --------------------------------------------------------------------------- #

def test_the_sdist_guard_reddens_on_a_reinjected_tests_tree(tmp_path):
    """SIMULATED regression, stated as such: re-inject `tests/` into a built sdist.

    The guard was first shown red against the REAL unfixed sdist at the branch
    point (222 members, 3,917,577 B — recorded in the issue's Handoff notes). This
    keeps that red reproducible forever without needing an unfixed tree.
    """
    sdist, _ = front_door.packaging_artifacts()
    version = front_door.pyproject()["project"]["version"]
    poisoned = tmp_path / sdist.name
    shutil.copy(sdist, poisoned)
    extracted = tmp_path / "x"
    with tarfile.open(poisoned) as archive:
        archive.extractall(extracted, filter="data")
    top = extracted / f"larkdocio-{version}"
    leaked_dir = top / "tests"
    leaked_dir.mkdir(exist_ok=True)
    (leaked_dir / "test_smuggled.py").write_text("assert True\n", encoding="utf-8")
    repacked = tmp_path / "repacked.tar.gz"
    with tarfile.open(repacked, "w:gz") as archive:
        archive.add(top, arcname=f"larkdocio-{version}")

    members = front_door.sdist_members(repacked)
    paths = list(members) + list(front_door.sdist_directories(repacked))
    assert front_door.leaked_trees(paths) == ["tests"]
    assert "tests/test_smuggled.py" in front_door.unexpected_sdist_members(members)
    # …and the clean article still passes both halves.
    clean = front_door.sdist_members(sdist)
    assert front_door.leaked_trees(list(clean)) == []
    assert front_door.unexpected_sdist_members(clean) == []


def test_the_wheel_guard_bites_in_both_directions_on_synthetic_input():
    """The PURE FUNCTIONS, over synthetic input — and only that.

    This deletes a key from a dict, so it proves `missing_wheel_members` reports an
    absent member and nothing about where the expectation came from. The derivation
    is proven separately, against a real file on a real tree, by
    `test_deleting_a_real_declared_file_reddens_the_owed_set`. Reading this test as
    proof of the missing-direction is exactly the mistake this issue's first round
    made.
    """
    members = dict.fromkeys(front_door.wheel_expected_members(), (0, 0))
    assert front_door.unexpected_wheel_members(members) == []
    assert front_door.missing_wheel_members(members) == []
    members["larkdocio/smuggled.txt"] = (0, 0)
    assert front_door.unexpected_wheel_members(members) == ["larkdocio/smuggled.txt"]
    victim = sorted(front_door.declared_package_data())[0]
    del members[victim]
    assert front_door.missing_wheel_members(members) == [victim]


def test_the_content_guard_is_armed_rather_than_skipped():
    """The posture, asserted (AC6a).

    `built_wheel()` / `built_sdist()` return None on a plain checkout and their
    existing consumers `pytest.skip`. `verify.sh` does not rescue that: it runs the
    pytest gate BEFORE the `python -m build` gate, so the artifacts would not exist
    when the suite needs them. Hence the guard builds its own, and this test proves
    both halves of that reasoning — the ordering, and that the build really armed.
    """
    verify = (_ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8")
    pytest_gate = verify.index('run_gate "pytest"')
    build_gate = verify.index('run_gate "python -m build"')
    assert pytest_gate < build_gate, (
        "verify.sh now builds before pytest — the pre-built dist/ reader would be a "
        "viable arming path and this guard's build could be dropped."
    )
    sdist, wheel = front_door.packaging_artifacts()
    assert sdist.exists() and wheel.exists()
    assert sdist.parent != _ROOT / "dist", (
        "the guard must build into a throwaway dir, never the sticky gitignored dist/"
    )


# --------------------------------------------------------------------------- #
# LD-221 AC-A2 — ONE build site in the whole test tree.                        #
# --------------------------------------------------------------------------- #

#: The single module allowed to shell out to ``python -m build``. LD-215 built the
#: session-cached seam and did not migrate the pre-existing sites, so the count went
#: 3 → 4 (a wheel built four times per run, ~4-5 s each). The rule is stated as a
#: guard rather than a convention because "don't add a fifth" is exactly the kind of
#: thing a new packaging test re-invents from scratch.
_THE_BUILD_SITE = "tests/front_door.py"


def _build_invocation_sites():
    """``["<relpath>:<lineno>", ...]`` for every REAL ``python -m build`` argv in ``tests/``.

    LD-355: the walk itself moved to ``front_door.argv_literal_sites`` — which carries the
    AST-not-grep reasoning verbatim, and which is now also race-tolerant, since under
    ``-n auto`` it runs while another worker may be writing and deleting a transient probe
    module in ``tests/``. This guard's assertion and message are unchanged.
    """
    return front_door.argv_literal_sites("-m", "build")


def test_the_test_tree_shells_out_to_python_dash_m_build_exactly_once():
    """LD-221 AC-A2: exactly ONE ``python -m build`` subprocess site in ``tests/``,
    and it is ``front_door.py``'s. Every other packaging assertion takes its artifact
    from the session-cached seam instead of paying for its own wheel."""
    sites = _build_invocation_sites()
    assert [site.split(":")[0] for site in sites] == [_THE_BUILD_SITE], (
        f"tests/ shells out to `python -m build` at {sites} — it must happen at exactly "
        f"one site ({_THE_BUILD_SITE}); route the rest through front_door."
    )
