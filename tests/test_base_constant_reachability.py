"""LD-307 — a disclosure constant no code path reaches is a promise the consumer never receives.

``src/larkdocio/base/`` publishes its facts as **module-level constants**: code tables,
``(type, ui_type)`` pair sets, refusal prose, evidence citations. Each one is a promise, and a
promise is only kept if something reads it. Twice now a constant has been found **defined once
and referenced by nothing** — LD-295 found the first by hand, and the 2026-08-06 refactor audit
found two more (`dev/refactor-audit-2026-08-06.md` § T6, in the dev repo) — both times because a
human happened to look. **Nothing looked.** This module is the thing that looks.

Two guards, one finding:

1. **The standing sweep** (:func:`test_every_base_constant_is_read_by_src_or_named_by_a_test`).
   Every public module-level ``ALL_CAPS`` constant under ``base/`` must be **referenced from
   ``src/`` outside its own definition line**, or **named by a test**, or listed in
   :data:`DECLARED_UNWIRED` with a written reason. Bidirectional: an allow-list entry whose
   constant has vanished — or which is now wired — reddens too, so the list cannot rot into a
   rubber stamp.

   The two halves of the rule read the tree differently, on purpose. On the ``src/`` side a
   **textual** name anywhere counts, prose included: a constant cited by a neighbouring
   module's ``#:`` comment genuinely has a reader, and modules that cross-cite each other in
   prose would otherwise look dead. On the ``tests/`` side only a name the test module
   **evaluates** counts (AST-read: a load, an attribute, an import) — because a constant named
   in a test's *docstring* is described, not asserted, and a guard that accepted a mention
   would be satisfiable by writing this very paragraph.

2. **The one table this sweep was born from**
   (:func:`test_every_entry_scoped_code_classifies_entry_scoped`). ``disposition``'s
   ``ENTRY_SCOPED_CODES`` documented the codes the classifier reaches by
   *fall-through* — correct behaviour, dead documentation, and free to drift. It is now an
   assertion instead of a comment, in both directions the audit named: disjoint from
   ``SYSTEMIC_CODES``, and every listed code classified entry-scoped by
   ``classify_apply_exception`` itself.

**The mechanism is proven on synthetic input, not only on the tree.** A guard whose allow-list
happens to be empty would otherwise assert nothing about the allow-list's own discipline, and a
sweep whose enumerator quietly returned ``()`` would pass forever. So the pure functions
(:func:`module_level_constants`, :func:`name_index`, :func:`unreachable`,
:func:`reason_defects`, :func:`stale_declarations`) are exercised against a planted unwired
constant in a temporary directory — the audit's own "plant it and watch the guard name it" step,
run on every ``pytest``.

Scope: ``base/`` only, which is where the measurement was taken. Widening the sweep to
``write/``, ``sheets/`` or ``common/`` is a separate, separately-sized question.
"""
import ast
import re

import pytest

from guard_kit import REPO_ROOT

from larkdocio.base import disposition as disposition_module

SRC = REPO_ROOT / "src"
TESTS = REPO_ROOT / "tests"
BASE = SRC / "larkdocio" / "base"

#: Constants that are deliberately unwired, each with the reason it is correct that way.
#: **A reason per entry is the whole point** — an allow-list of bare names is a rubber stamp on
#: its second use. Adding an entry means writing why no reader is the right answer; the guards
#: below reject an empty reason, a name that no longer exists, and a name that has since found a
#: reader. Empty today: LD-307 left ``base/`` with nothing to declare.
DECLARED_UNWIRED = {}

#: A reason has to be a sentence someone wrote, not a token someone typed to get green.
REASON_MIN_CHARS = 40

#: Tokens that mean "I did not write a reason".
PLACEHOLDER_WORDS = ("todo", "tbd", "n/a", "na", "fixme", "xxx", "unused", "dead", "?")

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


# --------------------------------------------------------------------------- #
# The mechanics — pure functions, so the guard can be pointed at a fake tree   #
# --------------------------------------------------------------------------- #

def module_level_constants(path):
    """Every public module-level ``ALL_CAPS`` constant assigned in ``path``.

    Returns ``((name, lineno), ...)`` in source order. Annotated assignments count — a
    ``NAME: Tuple[...] = ...`` is the same promise as a bare one, and a line-anchored grep for
    ``^[A-Z]`` followed by ``=`` misses every one of them.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
        else:
            continue
        for target in targets:
            name = target.id
            if len(name) > 1 and not name.startswith("_") and name == name.upper():
                found.append((name, node.lineno))
    return tuple(found)


def base_constants(root=None):
    """``((module, name, lineno), ...)`` for every module under ``root`` (default ``base/``)."""
    root = BASE if root is None else root
    return tuple(
        (path.name, name, lineno)
        for path in sorted(root.rglob("*.py"))  # LD-654: population must be recursive
        for name, lineno in module_level_constants(path)
    )


def name_index(files, relative_to=None):
    """``{identifier: ((relpath, lineno), ...)}`` over ``files``.

    Every identifier on every line, comments and docstrings included. That breadth is the
    point: a constant named in a sibling module's ``#:`` comment has a reader, and treating
    prose as invisible would call it dead.
    """
    relative_to = REPO_ROOT if relative_to is None else relative_to
    index = {}
    for path in files:
        rel = path.relative_to(relative_to).as_posix()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for name in set(_IDENTIFIER.findall(line)):
                index.setdefault(name, []).append((rel, lineno))
    return index


def evaluated_name_index(files, relative_to=None):
    """``{identifier: ((relpath, lineno), ...)}`` for names the module actually **evaluates**.

    AST-read, so a name that appears only inside a string or a comment is absent. This is the
    index the ``tests/`` side of the rule uses: asserting on a constant is a reader, writing its
    name in a docstring is not.
    """
    relative_to = REPO_ROOT if relative_to is None else relative_to
    index = {}
    for path in files:
        rel = path.relative_to(relative_to).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Name):
                keys = (node.id,)
            elif isinstance(node, ast.Attribute):
                keys = (node.attr,)
            elif isinstance(node, ast.alias):
                keys = tuple(k for k in (node.name, node.asname) if k)
            else:
                continue
            for key in keys:
                index.setdefault(key, []).append((rel, getattr(node, "lineno", 0)))
    return index


def references(name, index, ignoring=()):
    """Where ``name`` appears in ``index``, minus the ``(relpath, lineno)`` sites in ``ignoring``."""
    skip = set(ignoring)
    return tuple(site for site in index.get(name, ()) if site not in skip)


def _definition_site(module, lineno, prefix="src/larkdocio/base"):
    return (f"{prefix}/{module}", lineno)


def unreachable(constants, src_index, test_index, declared=(), prefix="src/larkdocio/base"):
    """``constants`` that no ``src/`` line outside their own definition and no test names.

    Entries present in ``declared`` are excluded — that is what the allow-list is for.
    """
    declared = set(declared)
    out = []
    for module, name, lineno in constants:
        if name in declared:
            continue
        defsite = _definition_site(module, lineno, prefix)
        if references(name, src_index, ignoring=(defsite,)):
            continue
        if references(name, test_index):
            continue
        out.append((module, name, lineno))
    return tuple(out)


def reason_defects(declared):
    """``((name, complaint), ...)`` for every allow-list entry whose reason is not a reason."""
    out = []
    for name, reason in sorted(declared.items()):
        if not isinstance(reason, str) or not reason.strip():
            out.append((name, "no reason written"))
            continue
        text = reason.strip()
        if len(text) < REASON_MIN_CHARS:
            out.append((name, f"reason is {len(text)} chars, floor is {REASON_MIN_CHARS}"))
        elif text.lower().strip(".") in PLACEHOLDER_WORDS or " " not in text:
            out.append((name, f"placeholder, not a reason: {text!r}"))
    return tuple(out)


def stale_declarations(declared, constants, src_index, test_index,
                       prefix="src/larkdocio/base"):
    """``((name, complaint), ...)`` for allow-list entries that have outlived their purpose.

    Two ways an entry rots, both of which turn the list into a lie: the constant is **gone**,
    or it is **wired now**. Either way the entry must be deleted, not carried.
    """
    sites = {name: (module, lineno) for module, name, lineno in constants}
    out = []
    for name in sorted(declared):
        if name not in sites:
            out.append((name, "no such constant under base/ any more — delete the entry"))
            continue
        module, lineno = sites[name]
        readers = references(name, src_index,
                             ignoring=(_definition_site(module, lineno, prefix),))
        readers += references(name, test_index)
        if readers:
            out.append((name, f"wired now ({readers[0][0]}:{readers[0][1]}) — delete the entry"))
    return tuple(out)


# --------------------------------------------------------------------------- #
# The tree, read once                                                          #
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def tree():
    constants = base_constants()
    return {
        "constants": constants,
        "src": name_index(sorted(SRC.rglob("*.py"))),
        "tests": evaluated_name_index(sorted(TESTS.rglob("*.py"))),
    }


# --------------------------------------------------------------------------- #
# 1. The standing sweep                                                        #
# --------------------------------------------------------------------------- #

def test_every_base_constant_is_read_by_src_or_named_by_a_test(tree):
    """The guard itself. A constant nothing reads is a promise nothing delivers."""
    dead = unreachable(tree["constants"], tree["src"], tree["tests"], DECLARED_UNWIRED)
    assert not dead, (
        "these base/ constants are defined and read by nothing — wire each one into a live "
        "guard, delete it, or add it to DECLARED_UNWIRED with the reason no reader is "
        "correct:\n" + "\n".join(f"  src/larkdocio/base/{m}:{n}::{name}"
                                 for m, name, n in dead))


def test_the_sweep_actually_enumerates_base_rather_than_nothing(tree):
    """The vacuous-guard failure mode, closed: an enumerator that returns ``()`` passes the
    sweep above forever. Floors, not exact counts — the population grows with the surface."""
    constants = tree["constants"]
    modules = {module for module, _, _ in constants}
    assert len(constants) >= 200, f"only {len(constants)} constants enumerated"
    assert len(modules) >= 25, f"only {len(modules)} base/ modules enumerated"
    names = {name for _, name, _ in constants}
    for anchor in ("SYSTEMIC_CODES", "NON_WRITABLE_PAIRS", "PAIRS"):
        assert anchor in names, f"{anchor} is a module-level base/ constant and was missed"


# --------------------------------------------------------------------------- #
# 2. ENTRY_SCOPED_CODES — the table this sweep found, now an assertion          #
# --------------------------------------------------------------------------- #

def _coded_lark_error(code):
    """A ``LarkAPIError`` shaped the way the apply boundary meets one: coded, with a message."""
    from larkdocio.errors import LarkAPIError

    return LarkAPIError(f"Lark rejected the call: Code: {code}, Msg: classified here",
                        code=code, msg="classified here")


def misclassified_entry_scoped_codes(module):
    """Codes ``ENTRY_SCOPED_CODES`` lists that ``classify_apply_exception`` does NOT continue on.

    A function rather than an inline loop so the mutation proof below can run the same check
    against a deliberately broken table.
    """
    return tuple(
        (code, disposition.scope, disposition.reason)
        for code, disposition in (
            (code, module.classify_apply_exception(_coded_lark_error(code), wrote=False))
            for code in module.ENTRY_SCOPED_CODES)
        if disposition.scope != module.ENTRY_SCOPED or not disposition.continues
    )


def test_the_two_base_code_tables_are_disjoint():
    """The half that gives the classification assertion its teeth. ``classify_apply_exception``
    is an allow-list on ``SYSTEMIC_CODES`` with entry-scoped as the fall-through, so a code in
    both tables would be classified by the wrong one and the documentation would still read
    true."""
    overlap = sorted(set(disposition_module.ENTRY_SCOPED_CODES)
                     & set(disposition_module.SYSTEMIC_CODES))
    assert overlap == [], (
        f"codes claimed by BOTH base/disposition tables: {overlap}. SYSTEMIC_CODES wins in the "
        "classifier, so the ENTRY_SCOPED_CODES row is a promise the code does not keep")
    assert len(set(disposition_module.ENTRY_SCOPED_CODES)) == \
        len(disposition_module.ENTRY_SCOPED_CODES), "a code listed twice"
    assert disposition_module.ENTRY_SCOPED_CODES, "the table this guard exists for is empty"


def test_every_entry_scoped_code_classifies_entry_scoped():
    """The table becomes an assertion (LD-307 B2). It documented the codes the classifier reaches
    by *fall-through* — correct, and free to drift away from the classifier in silence, because
    no code path and no test read it. Now one does."""
    wrong = misclassified_entry_scoped_codes(disposition_module)
    assert wrong == (), "\n".join(
        f"  {code} classified {scope}/{reason}, but ENTRY_SCOPED_CODES documents it as "
        f"entry-scoped" for code, scope, reason in wrong)


def test_a_systemic_code_is_not_entry_scoped_so_the_assertion_above_can_fail():
    """Entry-scoped is the fall-through, so the guard above must be shown to distinguish
    something — otherwise it would pass over any table at all, including a wrong one."""
    for code in disposition_module.SYSTEMIC_CODES:
        verdict = disposition_module.classify_apply_exception(_coded_lark_error(code),
                                                             wrote=False)
        assert verdict.halts and verdict.scope == disposition_module.SYSTEMIC, (code, verdict)


def test_moving_one_code_into_systemic_codes_reddens_the_classification_guard(monkeypatch):
    """The mutation proof B2 asks for, automated: promote the first entry-scoped code to
    systemic and the guard names it. A guard nobody has watched fail is a guess."""
    victim = disposition_module.ENTRY_SCOPED_CODES[0]
    monkeypatch.setattr(disposition_module, "SYSTEMIC_CODES",
                        disposition_module.SYSTEMIC_CODES + (victim,))
    wrong = misclassified_entry_scoped_codes(disposition_module)
    assert [code for code, _, _ in wrong] == [victim], wrong
    assert wrong[0][1] == disposition_module.SYSTEMIC


# --------------------------------------------------------------------------- #
# 3. The allow-list's own discipline (B4 bidirectional, B5)                     #
# --------------------------------------------------------------------------- #

def test_every_declared_unwired_entry_carries_a_written_reason():
    """The anti-goal, as an assertion: *the allow-list must carry a written reason per entry,
    or the guard becomes a rubber stamp on its second use.*"""
    assert isinstance(DECLARED_UNWIRED, dict), "a mapping name → reason, never a bare set"
    defects = reason_defects(DECLARED_UNWIRED)
    assert not defects, "\n".join(f"  {name}: {why}" for name, why in defects)


def test_no_declared_unwired_entry_has_rotted(tree):
    """The other direction: an entry whose constant is gone, or which is wired now, reddens."""
    stale = stale_declarations(DECLARED_UNWIRED, tree["constants"], tree["src"], tree["tests"])
    assert not stale, "\n".join(f"  {name}: {why}" for name, why in stale)


# --------------------------------------------------------------------------- #
# 4. The mechanism, proven on a planted constant                                #
# --------------------------------------------------------------------------- #

def _fake_tree(tmp_path):
    """A two-module fake ``base/`` plus a fake ``tests/``, planted with one unwired constant."""
    src = tmp_path / "src" / "larkdocio" / "base"
    src.mkdir(parents=True)
    (src / "alpha.py").write_text(
        "READ_BY_SIBLING = 'a'\n"
        "READ_BY_ITS_OWN_MODULE: str = 'b'\n"
        "READ_BY_A_TEST = 'c'\n"
        "CITED_IN_A_SIBLINGS_COMMENT = 'd'\n"
        "NAMED_ONLY_IN_TEST_PROSE = 'e'\n"
        "PLANTED_UNWIRED = 'nobody reads me'\n"
        "_PRIVATE_UNWIRED = 'excluded: not public surface'\n"
        "lower_case_unwired = 'excluded: not a constant'\n"
        "\n"
        "def f():\n"
        "    return READ_BY_ITS_OWN_MODULE\n",
        encoding="utf-8")
    (src / "beta.py").write_text(
        "from .alpha import READ_BY_SIBLING\n"
        "#: see CITED_IN_A_SIBLINGS_COMMENT for the established value\n",
        encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_named.py").write_text(
        '"""A docstring that says NAMED_ONLY_IN_TEST_PROSE and asserts nothing."""\n'
        "from alpha import READ_BY_A_TEST\n"
        "assert READ_BY_A_TEST\n",
        encoding="utf-8")
    constants = base_constants(src)
    return {
        "constants": constants,
        "src": name_index(sorted((tmp_path / "src").rglob("*.py")), relative_to=tmp_path),
        "tests": evaluated_name_index(sorted(tests.rglob("*.py")), relative_to=tmp_path),
    }


def test_a_planted_unwired_constant_is_named_by_the_sweep(tmp_path):
    """The audit's move-5 mutation proof, automated: plant one, watch the guard name it.

    ``NAMED_ONLY_IN_TEST_PROSE`` rides along as the second offender — a constant a test file
    *mentions in its docstring* and never evaluates is dead, and the AST-read ``tests/`` index
    is what makes the sweep say so.
    """
    fake = _fake_tree(tmp_path)
    dead = unreachable(fake["constants"], fake["src"], fake["tests"])
    assert sorted(name for _, name, _ in dead) == [
        "NAMED_ONLY_IN_TEST_PROSE", "PLANTED_UNWIRED"], dead


def test_the_sweep_counts_every_way_a_constant_is_genuinely_alive(tmp_path):
    """Four readers, each proven to satisfy the sweep — otherwise a green sweep would only mean
    the rule is too loose to fail: a sibling's import, the defining module itself, a sibling's
    prose citation, and a test that evaluates the name."""
    fake = _fake_tree(tmp_path)
    names = {name for _, name, _ in fake["constants"]}
    assert names == {"READ_BY_SIBLING", "READ_BY_ITS_OWN_MODULE", "READ_BY_A_TEST",
                     "CITED_IN_A_SIBLINGS_COMMENT", "NAMED_ONLY_IN_TEST_PROSE",
                     "PLANTED_UNWIRED"}, (
        "the enumerator must skip _private and lower_case module-level assignments")
    dead = {name for _, name, _ in unreachable(fake["constants"], fake["src"], fake["tests"])}
    for alive in ("READ_BY_SIBLING", "READ_BY_ITS_OWN_MODULE", "READ_BY_A_TEST",
                  "CITED_IN_A_SIBLINGS_COMMENT"):
        assert alive not in dead, alive


def test_declaring_the_planted_constant_silences_the_sweep(tmp_path):
    """The allow-list works — which is exactly why it needs the two rot guards below."""
    fake = _fake_tree(tmp_path)
    dead = unreachable(fake["constants"], fake["src"], fake["tests"],
                       {"PLANTED_UNWIRED": "x" * REASON_MIN_CHARS,
                        "NAMED_ONLY_IN_TEST_PROSE": "y" * REASON_MIN_CHARS})
    assert dead == ()


def test_the_reason_check_rejects_the_ways_a_reason_is_not_written():
    """B5's assertion proven to bite, on input the real allow-list does not have to contain."""
    offenders = {
        "EMPTY": "",
        "BLANK": "   ",
        "SHORT": "dead code",
        "PLACEHOLDER": "TODO" + "." * REASON_MIN_CHARS,
        "ONE_TOKEN": "unwired" + "-wontfix" * 8,
        "NOT_A_STRING": None,
    }
    assert {name for name, _ in reason_defects(offenders)} == set(offenders)
    good = {"FINE": ("No reader is correct here because the value is read by the packaging "
                     "step, which is not Python.")}
    assert reason_defects(good) == ()


def test_a_rotted_declaration_is_named_in_both_of_its_two_shapes(tmp_path):
    """Bidirectional, in LD-299's AC3 shape: the list cannot outlive what it excuses."""
    fake = _fake_tree(tmp_path)
    reason = "x" * REASON_MIN_CHARS
    vanished = stale_declarations({"GONE_ENTIRELY": reason}, fake["constants"],
                                  fake["src"], fake["tests"])
    assert [name for name, _ in vanished] == ["GONE_ENTIRELY"]
    assert "no such constant" in vanished[0][1]

    wired = stale_declarations({"READ_BY_SIBLING": reason}, fake["constants"],
                               fake["src"], fake["tests"])
    assert [name for name, _ in wired] == ["READ_BY_SIBLING"]
    assert "wired now" in wired[0][1]

    assert stale_declarations({"PLANTED_UNWIRED": reason}, fake["constants"],
                              fake["src"], fake["tests"]) == (), (
        "an entry that is genuinely unwired and genuinely present must NOT be called stale")
