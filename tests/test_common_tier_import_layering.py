"""LD-648 — ``larkdocio.common`` is the BOTTOM tier, and this is the guard that says so.

**The defect this file exists for.** ``errors.py`` sat at the package top level and imported
``common.error_codes``, while four modules under ``common/`` — ``auth``, ``transport``,
``sdk_client``, ``destination`` — imported ``larkdocio.errors`` back, all at MODULE SCOPE. That
is a live cycle. It resolved only because ``common/error_codes.py`` and ``common/citations.py``
happened to import nothing from ``larkdocio.errors``, and **nothing guarded that**. Measured by
ablation (seat, 2026-09-05, and re-run on this branch): adding one plausible line —
``from larkdocio.errors import LarkAPIError`` — to ``common/error_codes.py`` made ``import
larkdocio`` fail outright with ``ImportError: cannot import name 'LarkAPIError' from partially
initialized module 'larkdocio.errors'``. One import in either of two files made the whole
package unimportable, and the suite would have reported it as 20,000 errors with no name on the
cause.

**The invariant, stated positively.** No module under ``larkdocio/common/`` imports anything
outside ``larkdocio.common`` at module scope. Not ``larkdocio.errors``, not the bare
``larkdocio`` package, not a sibling surface. That is what makes ``common/`` a floor rather
than a participant, and it is what makes the cycle **structurally** impossible instead of
accidentally absent.

**Module scope, not every import.** A function-local import is deferred past module
initialisation and cannot form an import-time cycle, so it is deliberately NOT an offence here
(:func:`test_a_function_local_upward_import_is_NOT_an_offence` pins that as a choice, not an
oversight). ``errors._denial_for`` reaching ``permissions.denial_from`` from inside a function
body is the in-tree example of the pattern being allowed on purpose.

**Why one arm is a cold subprocess.** A cycle bites at an ENTRY POINT, and in a pytest session
``larkdocio`` is always already in ``sys.modules`` before any assertion runs — collection
imports it. The entry point that matters here is the one nobody exercises: a consumer (or a
sibling module) whose FIRST larkdocio import is a ``common/`` leaf. Only a fresh interpreter
can be entered that way. The idiom, and the reason it must **fail rather than skip** when it
cannot establish its answer, are the ones ``tests/test_base_destructive_claim_truth.py``
established for ``_COLD_REACHABILITY_PROBE``: a guard that goes quiet has stopped guarding, so
a non-zero return code or unparseable output is a FAILURE here, never a shrug. There is no
``pytest.skip`` branch in this file on purpose.
"""
import ast
import json
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "larkdocio"
COMMON = SRC / "common"

#: The tier. A module-scope import target is upward unless it is this package or inside it.
TIER = "larkdocio.common"


def _module_name(path):
    """``larkdocio.common.foo`` for ``src/larkdocio/common/foo.py`` (``__init__`` folds up)."""
    parts = list(path.relative_to(SRC.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _module_scope_statements(tree):
    """Every AST node executed at module initialisation, and none that is not.

    A ``def``/``async def`` body is skipped whole — that is the deferred case. A ``class``
    body IS executed at import, so its statements are walked (its methods are not).
    """
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(stmt, ast.ClassDef):
            for inner in stmt.body:
                if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                yield from ast.walk(inner)
            continue
        yield from ast.walk(stmt)


def module_scope_larkdocio_imports(source, me):
    """Every ``larkdocio`` module ``source`` imports AT MODULE SCOPE, as dotted names.

    Relative imports are resolved against ``me`` so ``from .url import x`` inside
    ``larkdocio.common.doc_link`` reads as ``larkdocio.common.url`` — an intra-tier import must
    not read as an unknown, or the checker would answer by accident.
    """
    targets = set()
    for node in _module_scope_statements(ast.parse(source)):
        if isinstance(node, ast.Import):
            targets.update(a.name for a in node.names if a.name.split(".")[0] == "larkdocio")
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = me.split(".")[: -node.level]
                targets.add(".".join(base + ([node.module] if node.module else [])))
            elif node.module and node.module.split(".")[0] == "larkdocio":
                targets.add(node.module)
    return sorted(targets)


def upward_imports_from(source, me):
    """The module-scope imports in ``source`` that reach OUTSIDE :data:`TIER`."""
    return [t for t in module_scope_larkdocio_imports(source, me)
            if t != TIER and not t.startswith(TIER + ".")]


def _tier_modules():
    return sorted(COMMON.rglob("*.py"))


# --------------------------------------------------------------------------- #
# AC1(a) — THE STRUCTURAL INVARIANT                                            #
# --------------------------------------------------------------------------- #

def test_the_tier_is_not_empty():
    """The checker's own non-vacuity: an empty walk would pass every arm below."""
    names = [_module_name(p) for p in _tier_modules()]
    assert len(names) >= 10, names
    assert TIER in names, f"the package __init__ itself must be in the walk — got {names}"


def test_no_module_under_common_imports_upward_at_module_scope():
    """THE invariant. ``common/`` is the floor: nothing in it reaches a higher tier at import.

    This is the arm that was RED before the relocation (four offenders: ``auth``,
    ``destination``, ``sdk_client``, ``transport``, all on ``larkdocio.errors``) and is what
    makes the cycle impossible rather than absent by luck.
    """
    offenders = {}
    for path in _tier_modules():
        me = _module_name(path)
        upward = upward_imports_from(path.read_text(encoding="utf-8"), me)
        if upward:
            offenders[me] = upward
    assert offenders == {}, (
        "a module under larkdocio/common/ imports OUTSIDE the tier at module scope, which is "
        "how the errors<->common cycle was formed. Move the dependency into common/, or defer "
        "the import into the function that needs it:\n  "
        + "\n  ".join(f"{m} -> {t}" for m, t in sorted(offenders.items())))


# --------------------------------------------------------------------------- #
# AC1(b) — THE CHECKER IS PROVEN TO BITE, on the measured ablation's own shape  #
# --------------------------------------------------------------------------- #

#: The exact line the seat injected into ``common/error_codes.py`` to prove the cycle live.
#: Held as source text, not as an edit to a real file: a guard whose bite is demonstrated by
#: mutating the tree cannot be demonstrated in a green run.
_ABLATION_LINE = "from larkdocio.errors import LarkAPIError\n"


def test_the_layering_checker_BITES_on_the_measured_ablation():
    """The ablation that made ``import larkdocio`` fail is detected as an offence."""
    assert upward_imports_from(_ABLATION_LINE, "larkdocio.common.error_codes") == [
        "larkdocio.errors"]


def test_the_layering_checker_BITES_on_a_bare_package_import_too():
    """``import larkdocio`` from inside the tier runs the package ``__init__`` — also upward."""
    assert upward_imports_from("import larkdocio\n", "larkdocio.common.url") == ["larkdocio"]
    assert upward_imports_from("from larkdocio import capabilities\n",
                               "larkdocio.common.url") == ["larkdocio"]


def test_an_intra_tier_import_is_NOT_an_offence_absolute_or_relative():
    """Both spellings of an in-tier import read as in-tier, so the arm above cannot pass by
    failing to resolve a relative import."""
    assert upward_imports_from("from larkdocio.common.url import validate_download_url\n",
                               "larkdocio.common.doc_link") == []
    assert upward_imports_from("from .url import validate_download_url\n",
                               "larkdocio.common.doc_link") == []
    assert upward_imports_from("from . import url\n", "larkdocio.common.doc_link") == []


def test_a_function_local_upward_import_is_NOT_an_offence():
    """INTENTIONALLY UNCONSTRAINED, and pinned as a choice.

    A deferred import cannot form an import-time cycle. ``errors._denial_for`` reaching
    ``permissions.denial_from`` from a function body is the in-tree instance of the pattern
    this arm declines to forbid.
    """
    deferred = "def f():\n    from larkdocio.errors import LarkAPIError\n    return LarkAPIError\n"
    assert upward_imports_from(deferred, "larkdocio.common.error_codes") == []


def test_a_class_body_upward_import_IS_an_offence():
    """A class body executes at import, so an import inside one is not deferred."""
    in_class = "class C:\n    from larkdocio.errors import LarkAPIError\n"
    assert upward_imports_from(in_class, "larkdocio.common.error_codes") == ["larkdocio.errors"]


# --------------------------------------------------------------------------- #
# AC1(c) — THE COLD INTERPRETER, entered at a common/ leaf                     #
# --------------------------------------------------------------------------- #

#: Entered at ``larkdocio.common.error_codes`` — the deepest leaf of the tier and the exact
#: file the ablation mutated — so the FIRST larkdocio import in the process is a floor module.
#: Then every module of the package is imported, so "the package imports cleanly" is measured
#: over the whole tree rather than over whatever this session happened to touch.
_COLD_IMPORT_PROBE = """
import json

# The entry point that matters, and the one no pytest session can produce: the first
# larkdocio import in this process is a common/ leaf.
import larkdocio.common.error_codes  # noqa: F401

import importlib
import pkgutil

import larkdocio

failures, imported = {}, 0
for found in pkgutil.walk_packages(larkdocio.__path__, "larkdocio."):
    try:
        importlib.import_module(found.name)
        imported += 1
    except Exception as exc:
        failures[found.name] = f"{type(exc).__name__}: {exc}"
print(json.dumps({"failures": failures, "n_imported": imported}))
"""


def test_the_package_imports_CLEANLY_from_a_cold_interpreter_entered_at_the_tier():
    """No skip branch, by design: an arm that cannot establish its answer must FAIL.

    A non-zero return code is the ablation's own signature — that is how the cycle announced
    itself — so it is asserted on directly rather than through the parsed payload.
    """
    proc = subprocess.run([sys.executable, "-c", _COLD_IMPORT_PROBE],
                          capture_output=True, text=True)
    assert proc.returncode == 0, (
        "the cold import probe did not run to completion, so nothing was measured — that is a "
        "FAILURE of this guard, never a skip. A cycle between the tier and a higher module "
        f"shows up here first:\n{proc.stderr[-3000:]}")
    assert proc.stdout.strip(), f"the probe printed nothing:\n{proc.stderr[-3000:]}"
    measured = json.loads(proc.stdout)
    assert measured["failures"] == {}, (
        "module(s) of the package could not be imported in a cold interpreter whose first "
        "larkdocio import was a common/ leaf: " + json.dumps(measured["failures"], indent=1))
    assert measured["n_imported"] > 200, (
        "the probe imported implausibly few modules, so its empty failure set means nothing: "
        f"{measured['n_imported']}")


# --------------------------------------------------------------------------- #
# AC3 — THE SHIM IS TRANSPARENT: identity, and completeness in BOTH directions  #
# --------------------------------------------------------------------------- #
#
# `larkdocio.errors` is the import path every recipe in the shipped guide uses, and LD-648
# deliberately did NOT deprecate it — so this door is a permanent public surface, not a
# waypoint. What makes it safe is that it re-exports the SAME OBJECTS rather than importable
# look-alikes, and that its name set cannot drift from the core's in either direction.
#
# Identity, not importability: a fork (a re-declared class, a wrapper function) would satisfy
# `from larkdocio.errors import LarkAPIError` and then fail the only thing that matters —
# `except larkdocio.errors.LarkAPIError` catching what the library actually raises.


def test_the_shim_and_the_core_declare_the_SAME_public_names():
    """Both directions in one assertion, so neither side can grow a name alone."""
    import larkdocio.common.errors as core
    import larkdocio.errors as shim

    assert shim.__all__ == core.__all__, (
        "the re-export at larkdocio.errors and the core taxonomy disagree about the public "
        f"surface. only_on_shim={sorted(set(shim.__all__) - set(core.__all__))} "
        f"only_in_core={sorted(set(core.__all__) - set(shim.__all__))}")


def test_every_public_name_is_the_SAME_OBJECT_on_both_paths():
    """Identity (``is``), never importability — the property the whole shim exists for."""
    import larkdocio.common.errors as core
    import larkdocio.errors as shim

    forks = [name for name in core.__all__
             if getattr(shim, name, None) is not getattr(core, name)]
    assert forks == [], (
        "larkdocio.errors re-binds a name to a DIFFERENT object than the core defines, so "
        "`except` on one path would miss what the other raises: " + ", ".join(forks))


def test_neither_module_has_a_public_name_its_ALL_omits():
    """``__all__`` is held to the live surface, so it cannot be a hand-kept subset.

    This is the arm that makes the list DERIVED rather than curated: a name bound at the top
    level of either module and left out of ``__all__`` is invisible to ``import *`` and to
    ``help()``, which is exactly how a public name goes quiet during a relocation.
    """
    import larkdocio.common.errors as core
    import larkdocio.errors as shim

    for module in (core, shim):
        live = sorted(n for n in dir(module) if not n.startswith("_"))
        assert live == sorted(module.__all__), (
            f"{module.__name__}: __all__ does not match the module's public surface. "
            f"public_but_unlisted={sorted(set(live) - set(module.__all__))} "
            f"listed_but_absent={sorted(set(module.__all__) - set(live))}")


def test_import_star_off_the_shim_binds_the_whole_family():
    """The consumer-side spelling of the two arms above, executed rather than described."""
    import larkdocio.common.errors as core

    namespace = {}
    exec("from larkdocio.errors import *", namespace)  # noqa: S102 — the surface under test
    bound = {k: v for k, v in namespace.items() if not k.startswith("__")}
    assert sorted(bound) == sorted(core.__all__)
    assert all(bound[name] is getattr(core, name) for name in core.__all__)


def test_help_on_the_shim_still_documents_the_WHOLE_family():
    """``help(larkdocio.errors)`` is a consumer-reaching surface, and ``__all__`` is what keeps
    it whole.

    ``pydoc`` documents only the members a module DEFINES — unless ``__all__`` names them. So
    on a re-export without ``__all__`` this page would list nothing at all, and the module a
    consumer is pointed at when something failed would answer with an empty page. That is not
    a style preference about ``__all__``; it is the mechanism, asserted.
    """
    import pydoc

    import larkdocio.common.errors as core
    import larkdocio.errors as shim

    page = _plain(pydoc.render_doc(shim))
    for section in ("CLASSES", "FUNCTIONS", "DATA"):
        assert section in page, f"help(larkdocio.errors) has no {section} section:\n{page[:800]}"
    missing = [name for name in core.__all__ if name not in page]
    assert missing == [], (
        "help(larkdocio.errors) does not document public name(s) the module re-exports — the "
        f"page went partly blank: {missing}")


def _plain(rendered):
    """``pydoc``'s overstrike bolding (``x\\x08x``) stripped, so a name can be searched for."""
    out, i = [], 0
    while i < len(rendered):
        if i + 1 < len(rendered) and rendered[i + 1] == "\x08":
            i += 2
            continue
        out.append(rendered[i])
        i += 1
    return "".join(out)
