"""LD-385 — a live-ring gate must at least be INVOCABLE, and that is checkable offline.

A ``live`` / ``live_write`` gate is deselected by default, so ``./scripts/verify.sh`` — the
full offline suite — never executes a line of it. That makes one narrow class of edit
invisible until somebody actually reaches for the ring: a **function-local import that
shadows a module-level name the same function already used above it**. Python binds the
whole name locally for the entire function, so the earlier use raises ``UnboundLocalError``
*by construction*, on every invocation, before a single API call goes out.

That is exactly what LD-385's own AC8 gate hit: a convenience
``from larkdocio.sheets.export_reader import SheetsExportReader`` added deep inside
``tests/test_live_sheets_style_gate.py`` shadowed the module-level import the gate had
already used ~100 lines earlier to build its reader. Offline was green; the binding live
gate could not start.

This guard is a **static** check — it never imports or runs a gate, needs no credentials,
and costs a parse per live-ring file. It lives OUTSIDE the ``tests/test_live_*.py``
namespace on purpose: that glob is the live-gate registry's discovered set
(``tests/test_gate_registry.py``), and this is an offline guard *about* the rings, not a
gate in them. It flags only the unambiguous shape: a name is bound
in a function *solely* by a local import, and is loaded on an earlier line. A local import
that shadows nothing used above it is idiomatic and stays legal (18 such imports exist in
this tree and none are flagged).
"""

import ast
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

# The live rings: the files the default suite never executes.
LIVE_RING_FILES = sorted(
    p for p in TESTS_DIR.rglob("test_live_*.py")  # LD-654: recursive population
    if not p.name.endswith("_offline.py")
)

_SCOPE_BREAKERS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def _own_scope_nodes(fn):
    """Every node in ``fn``'s own scope — nested functions/classes are their own scope."""
    stack = list(fn.body)
    while stack:
        node = stack.pop()
        yield node
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _SCOPE_BREAKERS):
                continue
            stack.append(child)


def _binding_lines(fn):
    """name -> (first line that binds it, first line an *import* binds it)."""
    bindings, import_bindings = {}, {}

    def bind(name, lineno):
        if name and (name not in bindings or lineno < bindings[name]):
            bindings[name] = lineno

    args = fn.args
    for a in [*args.posonlyargs, *args.args, *args.kwonlyargs,
              args.vararg, args.kwarg]:
        if a is not None:
            bind(a.arg, fn.lineno)

    for node in _own_scope_nodes(fn):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                bind(name, node.lineno)
                if name not in import_bindings or node.lineno < import_bindings[name]:
                    import_bindings[name] = node.lineno
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bind(node.id, node.lineno)
        elif isinstance(node, ast.withitem) and node.optional_vars is not None:
            for sub in ast.walk(node.optional_vars):
                if isinstance(sub, ast.Name):
                    bind(sub.id, sub.lineno)
        elif isinstance(node, ast.ExceptHandler):
            bind(node.name, node.lineno)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            for name in node.names:
                bind(name, 0)  # explicitly not a local binding — never flag it

    return bindings, import_bindings


def _shadowing_local_imports(path):
    """(function, name, use_line, import_line) for each UnboundLocalError-by-construction."""
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    findings = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        bindings, import_bindings = _binding_lines(fn)
        if not import_bindings:
            continue
        for node in _own_scope_nodes(fn):
            if not (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)):
                continue
            import_line = import_bindings.get(node.id)
            if import_line is None:
                continue
            # Only when the local import is the ONLY thing that binds the name, and the
            # use sits above it — anything else is legal shadowing, not a guaranteed crash.
            if bindings.get(node.id) == import_line and node.lineno < import_line:
                findings.append((fn.name, node.id, node.lineno, import_line))
    return sorted(set(findings))


def test_no_live_ring_gate_is_unbound_by_a_shadowing_local_import():
    offenders = []
    for path in LIVE_RING_FILES:
        for fn_name, name, use_line, import_line in _shadowing_local_imports(path):
            offenders.append(
                f"{path.name}::{fn_name} — {name!r} is used at line {use_line} but the "
                f"only binding is a function-local import at line {import_line}; the gate "
                f"raises UnboundLocalError before it reaches the API"
            )
    assert not offenders, (
        "a live-ring gate cannot even start (the default offline suite never runs it, so "
        "this is invisible without this guard):\n  " + "\n  ".join(offenders)
    )


def test_the_guard_has_live_ring_files_to_check():
    # A guard whose corpus silently empties is a guard that passes for the wrong reason.
    assert len(LIVE_RING_FILES) >= 50, len(LIVE_RING_FILES)
    names = {p.name for p in LIVE_RING_FILES}
    assert "test_live_sheets_style_gate.py" in names, sorted(names)[:5]


def test_the_guard_bites_on_the_exact_shape_it_was_written_for(tmp_path):
    # The LD-385 shape, reproduced verbatim in miniature: a module-level import used at the
    # top of the function, re-imported locally further down.
    offender = tmp_path / "test_live_fake_gate.py"
    offender.write_text(
        "from larkdocio.sheets.export_reader import SheetsExportReader\n"
        "\n"
        "def test_gate():\n"
        "    reader = SheetsExportReader.from_write_credentials('x')\n"
        "    from larkdocio.sheets.export_reader import SheetsExportReader\n"
        "    return reader, SheetsExportReader\n",
        encoding="utf-8",
    )
    assert _shadowing_local_imports(offender) == [
        ("test_gate", "SheetsExportReader", 4, 5)
    ]


def test_the_guard_leaves_ordinary_local_imports_alone(tmp_path):
    ok = tmp_path / "test_live_fine_gate.py"
    ok.write_text(
        "import json\n"
        "\n"
        "def test_gate():\n"
        "    import json  # shadows, but nothing above used it\n"
        "    from larkdocio.drive import read as drive_read\n"
        "    return json.dumps({}), drive_read\n",
        encoding="utf-8",
    )
    assert _shadowing_local_imports(ok) == []
