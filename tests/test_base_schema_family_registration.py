# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""LD-637 AC1 — a schema-op family in the tree but NOT in ``FAMILY_MODULES`` must redden.

**The hole this closes, and the ablation that proved it.** ``base/schema_ops.py``'s
:data:`~larkdocio.base.schema_ops.FAMILY_MODULES` is a hand-written tuple of dotted module
names, and every downstream answer is derived from it — ``registered_families()`` →
``schema_ops()`` / ``destructive_ops()`` / ``destructive_shapes()`` →
``request_destroys_data()`` → the consent fence in :mod:`larkdocio.base.schema_apply`. A family
module that sits in the package and declares ``DESTRUCTIVE_OPS = ("wipe_table",)`` but never
gets its line in the tuple is invisible to **all** of it: ``wipe_table`` is absent from
``schema_ops()`` and from ``destructive_ops()``, ``family_of()`` answers ``None``,
``schema_op()`` raises ``KeyError`` — and ``request_destroys_data()`` therefore answers
``False`` for a request that would delete a table. That was measured, not argued (LD-637's
ablation, re-run against the **whole** offline suite on 2026-09-03: 19,693 passed,
21 skipped, rc=0 — nothing reddened).

**Why nothing caught it, named rather than counted.** Two tests come close and both look the
wrong way. ``test_base_schema_matrix.py::test_the_library_still_REQUESTS_WIDENS_AND_ESCALATES_NOTHING``
is the only test that walks these files on **disk**, and it globs ``schema*.py`` looking for
scope-escalation *words*, so a family module is text to it. And
``test_base_schema_ops.py::test_the_aggregator_is_a_REGISTRATION_POINT_and_a_family_ADDS_ONE_LINE``
asserts ``len(names) == len(set(names)) == len(FAMILY_MODULES)`` — both sides of which are
derived from the tuple, so it compares the registry against **itself**. Neither can see a file
the tuple does not name; only a disk walk can.

**THE FIX IS A GUARD, NOT A DERIVATION.** Deriving the tuple from this walk would change
**registration order**, which three landed assertions in ``tests/test_base_schema_ops.py`` pin —
``FAMILY_MODULES[0]`` in
:func:`~test_base_schema_ops.test_the_aggregator_is_a_REGISTRATION_POINT_and_a_family_ADDS_ONE_LINE`,
and ``registered_families()[0].ops`` plus the flattened table's first six ops in
:func:`~test_base_schema_ops.test_the_six_app_and_table_ops_are_registered_by_name`. **Three
assertions across two functions, addressed by function name and not by line number**
(`process/doctrine/lookup-tables.md` § A.4): the line numbers this docstring first carried were
already wrong when it landed — it cited lines 41, 89 and 90, where 89-90 are a docstring — and a
corrected pair would have drifted again on the next insertion above them. The names are held
against the sibling module by :func:`test_the_cited_order_pins_still_exist_BY_NAME` below.
Registration order is a published property of the aggregator, so the walk **checks** the tuple
and never replaces it. ``FAMILY_MODULES`` is also the **only** hand-listed
module registry under ``src/larkdocio/**``, so this closes one hole rather than opening a
migration.

**How the walk decides a file is a family module: the three marker names, read by AST, never
by import.** A family module's whole contract with the aggregator is what it exposes at module
level — ``SCHEMA_OP_FAMILY`` (the descriptors), ``DESTRUCTIVE_OPS`` and ``DESTRUCTIVE_SHAPES``
(the two destructiveness declarations the fence unions). Any one of the three makes a file
family-shaped. Read by :mod:`ast` rather than by importing, because the failure this guard
exists for is a module nothing imports: importing to detect it would make the detector depend
on the very registration it is checking, and an unregistered file may not even import cleanly.

**The walk is over the whole package, not just ``base/``** — strictly wider than the hole
found, at no cost in false positives: the three marker names appear at module level nowhere
else under ``src/larkdocio/**``, and a family module dropped into another subpackage would
still be dotted-nameable in the tuple and so would still bypass the fence.
"""
import ast
import pathlib

import pytest

from guard_kit import REPO_ROOT

from larkdocio.base import schema_ops


PACKAGE = REPO_ROOT / "src" / "larkdocio"

#: The module-level names that make a file a schema-op family: the descriptors, and the two
#: destructiveness declarations ``destructive_ops()`` / ``destructive_shapes()`` union.
FAMILY_MARKERS = ("SCHEMA_OP_FAMILY", "DESTRUCTIVE_OPS", "DESTRUCTIVE_SHAPES")


def _dotted(path: pathlib.Path) -> str:
    parts = path.relative_to(PACKAGE.parent).with_suffix("").parts
    return ".".join(parts)


def _module_level_names(path: pathlib.Path) -> set:
    """Every name assigned at module level in ``path``, by AST — no import."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _family_shaped_modules() -> dict:
    """``{dotted module name: the markers it declares}`` for every family-shaped file on disk."""
    found = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        markers = _module_level_names(path) & set(FAMILY_MARKERS)
        if markers:
            found[_dotted(path)] = markers
    return found


# --------------------------------------------------------------------------- #
# The hole: a family on disk that the tuple does not name                      #
# --------------------------------------------------------------------------- #

def test_every_family_shaped_module_ON_DISK_is_registered():
    """THE GUARD. A file that declares a family marker and is not in ``FAMILY_MODULES`` is
    invisible to ``destructive_ops()`` and therefore to the consent fence."""
    unregistered = {
        name: sorted(markers)
        for name, markers in _family_shaped_modules().items()
        if name not in schema_ops.FAMILY_MODULES}
    assert not unregistered, (
        "these modules declare a schema-op family marker but are NOT in "
        "larkdocio.base.schema_ops.FAMILY_MODULES, so every answer derived from it — "
        "schema_ops(), destructive_ops(), destructive_shapes(), request_destroys_data() and "
        "the consent fence in schema_apply — cannot see their ops: "
        f"{unregistered}. Add the dotted name to FAMILY_MODULES (appending, so the pinned "
        "registration order is preserved), or delete the module.")


def test_a_module_declaring_DESTRUCTIVENESS_is_registered_or_its_declaration_is_INERT():
    """The safety half, asserted on its own so it cannot be weakened by loosening the marker
    set: ``DESTRUCTIVE_OPS`` / ``DESTRUCTIVE_SHAPES`` are read **only** through
    ``registered_families()``, so declaring either from an unregistered module is a fence that
    is switched off while reading as if it were on."""
    declared = {
        name: sorted(markers)
        for name, markers in _family_shaped_modules().items()
        if markers & {"DESTRUCTIVE_OPS", "DESTRUCTIVE_SHAPES"}}
    assert declared, "the walk found no destructiveness declaration at all — it is broken"
    unregistered = {n: m for n, m in declared.items()
                    if n not in schema_ops.FAMILY_MODULES}
    assert not unregistered, (
        "a destructiveness declaration in an unregistered module is never unioned by "
        f"destructive_ops()/destructive_shapes(): {unregistered}")


# --------------------------------------------------------------------------- #
# The other direction, and the guard's own non-vacuity                         #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("dotted", schema_ops.FAMILY_MODULES)
def test_every_registered_name_is_a_family_shaped_FILE_on_disk(dotted):
    """The reverse direction, stated as a DISK fact so both directions are readable in one
    place — and deliberately not claimed as new coverage. A dotted name with no module behind
    it is already caught, loudly and everywhere: ``schema_apply.py:85`` flattens the aggregator
    at module level, so ``import larkdocio`` itself raises ``ModuleNotFoundError`` (measured
    while writing this guard), and ``test_base_schema_ops.py:47`` imports each registered name
    and asserts its ``SCHEMA_OP_FAMILY``. What this adds is the failure MESSAGE: the path that
    is missing, next to the walk that would have found it."""
    path = PACKAGE.parent / (dotted.replace(".", "/") + ".py")
    assert path.is_file(), f"{dotted} is registered but there is no such file: {path}"
    assert _module_level_names(path) & set(FAMILY_MARKERS), (
        f"{dotted} is registered but declares none of {FAMILY_MARKERS} at module level")


def test_the_walk_IS_NOT_VACUOUS():
    """A disk walk that finds nothing passes every assertion above, so pin what it must find:
    the four shipped families, and that the walk sees strictly more than the one file whose
    marker it could have hard-coded."""
    found = _family_shaped_modules()
    assert set(schema_ops.FAMILY_MODULES) <= set(found), (
        sorted(found), schema_ops.FAMILY_MODULES)
    assert len(found) >= 4, sorted(found)
    assert all("SCHEMA_OP_FAMILY" in found[name] for name in schema_ops.FAMILY_MODULES)


def test_the_walk_reads_DISK_and_not_the_import_graph():
    """The detector must not depend on the registration it checks. Proven by construction: the
    walk parses files with :mod:`ast`, so a module that is imported by nothing — and one whose
    body would raise on import — is still seen."""
    src = "BOGUS = 1\nSCHEMA_OP_FAMILY = raise_at_import()\n"
    tmp = PACKAGE / "_ld637_never_written.py"
    assert not tmp.exists()
    tree = ast.parse(src)
    names = {t.id for node in tree.body if isinstance(node, ast.Assign)
             for t in node.targets if isinstance(t, ast.Name)}
    assert "SCHEMA_OP_FAMILY" in names, (
        "the marker must be detectable from source alone, with no import and no evaluation")


#: The order pins this module's docstring cites, addressed BY NAME — the whole point of § A.4.
#: ``(function, the assertion subjects it holds)``, one row per cited function.
_CITED_ORDER_PINS = {
    "test_the_aggregator_is_a_REGISTRATION_POINT_and_a_family_ADDS_ONE_LINE":
        ("FAMILY_MODULES[0]",),
    "test_the_six_app_and_table_ops_are_registered_by_name":
        ("registered_families()[0].ops", "[:6] == six"),
}


def test_the_cited_order_pins_still_exist_BY_NAME():
    """A citation nothing checks is a citation that has already drifted (LD-628 AC1c: this
    module landed citing ``lines 41, 89 and 90``, and 89-90 were a docstring).

    So the docstring above names **functions**, and this test resolves them in the sibling
    module and checks each still contains the subject it was cited for. A rename or a deletion
    reddens here, where the citation is, instead of leaving prose pointing at nothing. The
    count — three assertions across two functions — is derived from this register rather than
    typed in the sentence.
    """
    import inspect

    import test_base_schema_ops as sibling

    subjects = 0
    for name, cited in _CITED_ORDER_PINS.items():
        function = getattr(sibling, name, None)
        assert function is not None, (
            f"tests/test_base_schema_ops.py no longer defines {name}() — the citation in this "
            f"module's docstring points at nothing")
        source = inspect.getsource(function)
        body = source.split('"""')[-1] if '"""' in source else source
        for subject in cited:
            assert subject in body, (
                f"{name}() no longer asserts anything about {subject} — the docstring cites it "
                f"as one of the registration-order pins")
            subjects += 1
    assert (len(_CITED_ORDER_PINS), subjects) == (2, 3), (
        "the docstring says THREE assertions across TWO functions; this register now holds "
        f"{subjects} across {len(_CITED_ORDER_PINS)}")
