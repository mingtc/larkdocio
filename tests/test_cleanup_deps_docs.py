# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""Sanity tests for the cleanup-deps-docs hardening item (carried into larkdocio).

Asserts the *fixed* state:
- The package's RUNTIME dependencies don't include deps nothing in the package
  imports (mdformat, mdurl, tabulate).
- **Re-truthed in LD-136:** this file used to assert ``markdown-it-py`` may *never*
  be a runtime dep, because nothing in the package imported it (it was the
  test-only reference parser). ``compose(markdown)`` now parses **with it** — the
  dialect it compiles IS CommonMark + GFM tables/strikethrough, and hand-rolling a
  second definition of that dialect would have made the binding round-trip property
  prove only that two hand-rolled halves agree (architect's recorded call, the Markdown-authoring spec
  § F1-S3). So the guard now asserts the **invariant behind** the old rule rather
  than the rule: *every runtime dependency is actually imported by the package, and
  every dep the package imports is declared*. A dep nothing imports still fails.
- The dead, never-called ``download_image_raw`` method is removed from
  ``larkdocio.read.client.Client``.
"""

import re
from pathlib import Path

from larkdocio.read.client import Client

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src" / "larkdocio"

#: distribution name → the module name it is imported as.
_RUNTIME_DEPS = {
    "lark-oapi": "lark_oapi",
    "click": "click",
    "python-dotenv": "dotenv",
    "markdown-it-py": "markdown_it",
}


def _runtime_dependencies_block() -> str:
    """Return the lowercased text of the `[project].dependencies = [...]` array
    only (NOT the optional `dev` extra). Parsed from pyproject.toml text so this
    works from a bare source checkout — no install / toml parser required.

    ``#`` comment lines are stripped: this guard is about what is **declared**, and a
    comment explaining *why* a dep is (or is not) here must not read as a declaration.
    """
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r"(?ms)^dependencies\s*=\s*\[(.*?)\]", text)
    assert m, "could not locate the [project].dependencies array in pyproject.toml"
    declared = "\n".join(
        line for line in m.group(1).splitlines() if not line.strip().startswith("#")
    )
    return declared.lower()


def _package_imports() -> set:
    """Every top-level module name the shipped package imports."""
    roots = set()
    for path in sorted(_SRC.rglob("*.py")):
        for match in re.finditer(
            r"^\s*(?:import|from)\s+([A-Za-z_][\w.]*)", path.read_text(encoding="utf-8"),
            re.M,
        ):
            roots.add(match.group(1).split(".")[0])
    return roots


def test_runtime_deps_have_no_dead_deps():
    """A dep nothing in the package imports must not be a RUNTIME dependency."""
    runtime = _runtime_dependencies_block()
    for dead in ("mdformat", "mdurl", "tabulate"):
        assert dead not in runtime, (
            f"{dead} is not imported by the package and must not be a RUNTIME dependency"
        )


def test_every_runtime_dep_is_actually_imported_by_the_package():
    """The invariant the old markdown-it-py rule was a special case of: a declared
    runtime dep must be one the shipped package really imports."""
    imports = _package_imports()
    for dist, module in _RUNTIME_DEPS.items():
        assert module in imports, (
            f"{dist} is declared as a runtime dependency but nothing in "
            f"src/larkdocio imports {module!r} — drop it or use it"
        )


def test_every_third_party_import_is_a_declared_runtime_dep():
    """The other direction: the package may not import a distribution it does not
    declare (the failure mode a promoted dep introduces if pyproject is not updated)."""
    runtime = _runtime_dependencies_block()
    for dist, module in _RUNTIME_DEPS.items():
        if module in _package_imports():
            assert dist in runtime, (
                f"src/larkdocio imports {module!r} but {dist} is not in the RUNTIME "
                f"dependencies — a consumer installing the wheel would ImportError"
            )


def test_markdown_it_py_is_a_runtime_dep_now_that_compose_parses_with_it():
    """LD-136's dependency promotion, pinned explicitly: ``compose()`` parses with the
    same reference parser the reader's escaping tests measure against, so it is a
    RUNTIME dep (and no longer a dev extra)."""
    from larkdocio.write import compose

    assert compose("# H\n") and "markdown-it-py" in _runtime_dependencies_block()


def test_download_image_raw_method_removed():
    assert not hasattr(Client, "download_image_raw"), (
        "download_image_raw is dead code (zero callers) and should be deleted"
    )
