# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""The standing guard: no shipped string sends a wheel-holder to a file the wheel lacks.

The library's refusals and loss previews cite their evidence, and that evidence was recorded
in the maintainer's development repository — ``dev/…`` paths that appear in no artifact a
consumer installs. Cited bare, they read as a next step; followed, they dangle.

The rule, one sentence: **a string a consumer can reach may name a maintainer-repo path only
while wearing ``larkdocio.common.citations.DEV_REPO_LABEL``** — normally by being composed
through :func:`~larkdocio.common.citations.dev_repo`, the one formatter.

Three legs, because a citation reaches a consumer three different ways:

1. :func:`test_no_consumer_reaching_string_cites_an_unlabelled_dev_repo_path` — the shipped
   **text** corpus (every literal under ``src/larkdocio``, every public docstring, every
   string in a real plan's JSON), reusing ``tests/consumer_text.py``'s existing passes.
2. :func:`test_no_composed_source_string_cites_an_unlabelled_dev_repo_path` — the **source**,
   AST-read with the module's own path constants folded into f-strings, so
   ``f"{_CAPTURES}/x.json"`` is judged as the sentence it becomes rather than as its pieces.
   A citation routed through the formatter is excused by construction.
3. :func:`test_no_public_registry_value_cites_an_unlabelled_dev_repo_path` — the **returned
   data**: every string reachable from a public module attribute, which is how an error
   note's ``evidence`` and a loss preview's evidence list actually arrive.

Markdown documents are out of scope for the LABEL legs — ``test_front_door_doctrine.py``
already holds every packaged document to the same label.

**And a fourth leg, the one the three above never had (LD-675): does the cited path EXIST?**
All three legs police whether a citation is *labelled* as a maintainer-repo path; none ever
resolved one. So the 2026-09-18 evidence-tree retirement turned dozens of shipped citations
into dangling pointers with every leg green. :func:`test_every_shipped_maintainer_repo_citation_resolves`
resolves **every** maintainer-repo path under ``src/larkdocio`` — Python *and* packaged
Markdown, labelled or not, routed through :func:`dev_repo` or not — against the tree.

**Who owns which direction** (LD-675 AC5, stated identically in LD-667): this file owns
**existence** for every path matching ``citations.DEV_REPO_PATH`` on the shipped surface, and
**label** for Python strings. ``tests/front_door.py`` (LD-667) owns every OTHER path-shaped
token in packaged docs and source prose, the packaged-Markdown label, and the debt tables.
``front_door.cited_repo_paths`` still *drops* a citation whose target is missing — for a
maintainer-repo path that is now harmless, because the leg here reddens on it first. So
deleting cited evidence is no longer a route to green for this class: it adds a miss here.
"""
import ast
import importlib.util
import re
import dataclasses
import importlib
import io
import tokenize

import pytest

import consumer_text
from guard_kit import REPO_ROOT

from larkdocio.common.citations import (
    DEV_REPO_LABEL,
    REPO_LABELS,
    SOURCE_REPO_LABEL,
    is_labelled,
    DEV_REPO_PATH,
    DEV_REPO_ROOTS,
    cites_dev_repo,
    dev_repo,
    dev_repo_paths,
)
import private_tree  # noqa: E402  (LD-685)

SRC = REPO_ROOT / "src" / "larkdocio"

#: The names that mark a citation as already routed through the one formatter. Bare and
#: dotted, so ``citations.dev_repo(...)`` counts too.
FORMATTER_NAMES = frozenset({"dev_repo"})


def _is_bare_path(text):
    """A literal that is *nothing but* a path — ``"tests/captures/base-study/captures"``.

    These are the composition fragments the modules join their citations out of; labelling a
    fragment would put the label in the middle of the sentence. They are excused HERE and
    caught THERE: leg 2 judges the composed string, leg 3 judges the value a consumer is
    handed.
    """
    return bool(text) and text.strip() == text and not any(c.isspace() for c in text)


def _snippet(text, path):
    start = max(0, text.find(path) - 60)
    return " ".join(text[start:text.find(path) + len(path) + 40].split())


# --------------------------------------------------------------------------- #
# The rule itself                                                              #
# --------------------------------------------------------------------------- #

def test_the_label_is_the_one_the_packaged_docs_already_use():
    """The Python side and the Markdown side wear the SAME phrase — a guard with two
    synonyms is a guard nobody can predict."""
    import front_door

    assert DEV_REPO_LABEL == front_door.DEV_REPO_LABEL
    # LD-699: the labels became two (one per meaning) — still one phrase EACH, on both sides.
    assert SOURCE_REPO_LABEL == front_door.SOURCE_REPO_LABEL
    assert REPO_LABELS == front_door.REPO_LABELS


@private_tree.citations
def test_the_roots_cover_every_directory_the_wheel_leaves_behind():
    assert set(DEV_REPO_ROOTS) >= {"dev", "progress", "requirements"}
    for root in DEV_REPO_ROOTS:
        assert (REPO_ROOT / root).exists(), root
        assert not (SRC / root).exists(), f"{root} is packaged after all — retire its rule"


def test_a_capture_the_repository_carries_under_tests_captures_is_a_repository_citation():
    """LD-694 F8: the recorded responses the evidence cites are carried by the repository as
    ``tests/captures/<probe>/…`` — in BOTH trees, so a reader of the public repository can open
    them — and the shipped citations now name that copy instead of the private ``dev/<probe>/…``.
    It is still a file the wheel does not carry, so it is still a repository citation: it is
    found by the same parser and resolved by the same existence leg. TRANSFORMED by LD-699: it
    used to wear the same label as a private record; it now wears ``SOURCE_REPO_LABEL``, because
    a reader of the public repository CAN open it and the private label says they cannot."""
    path = "tests/captures/ld463-date-only/captures/ld463-01-date-only-zone.json"
    assert dev_repo_paths(f"see {path}") == (path,)
    assert dev_repo(path) == f"{path} ({SOURCE_REPO_LABEL})"
    # Only the capture tree: a citation of a guard TEST module is not this class (the existing
    # rule, unchanged — dev_repo() leaves it alone).
    assert dev_repo("tests/test_guide.py") == "tests/test_guide.py"
    assert (REPO_ROOT / "tests" / "captures").is_dir()


# --------------------------------------------------------------------------- #
# Leg 1 — the shipped TEXT corpus                                              #
# --------------------------------------------------------------------------- #

def _python_text_corpus():
    """Every consumer-reaching string that comes from the CODE (not from a packaged doc)."""
    corpus = {}
    corpus.update(consumer_text.emitted_literals())
    corpus.update(consumer_text.public_docstrings())
    corpus.update(consumer_text.runtime_json_strings())
    return corpus


def test_no_consumer_reaching_string_cites_an_unlabelled_dev_repo_path():
    offenders = []
    for label, text in sorted(_python_text_corpus().items()):
        if not cites_dev_repo(text) or is_labelled(text):
            continue
        if _is_bare_path(text):
            continue
        offenders.append((label, _snippet(text, dev_repo_paths(text)[0])))
    assert not offenders, (
        f"{len(offenders)} consumer-reaching string(s) cite a path the wheel does not carry "
        f"without the {DEV_REPO_LABEL!r} label — route them through "
        f"larkdocio.common.citations.dev_repo(), or drop the path: {offenders[:8]}")


# --------------------------------------------------------------------------- #
# Leg 2 — the SOURCE, with each module's own path constants folded in          #
# --------------------------------------------------------------------------- #

#: The library's own citation constants, folded into an f-string the way the interpreter
#: would. Without this a site that spells the label as ``{DEV_REPO_LABEL}`` — the correct
#: way to put it mid-sentence — would read to this pass as unlabelled.
_CITATION_CONSTANTS = {
    name: value
    for name, value in vars(importlib.import_module("larkdocio.common.citations")).items()
    if isinstance(value, str) and not name.startswith("_")
}


def _module_string_constants(tree):
    """``{name: value}`` for every module-level ``NAME = "…"`` string assignment, plus any
    citation constant the module imports from ``larkdocio.common.citations``."""
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "larkdocio.common.citations":
            for alias in node.names:
                if alias.name in _CITATION_CONSTANTS:
                    constants[alias.asname or alias.name] = _CITATION_CONSTANTS[alias.name]
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        if not isinstance(node.value.value, str):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                constants[target.id] = node.value.value
    return constants


def _render(node, constants):
    """The string ``node`` becomes, or ``None`` if it is not a string expression.

    A placeholder this pass cannot resolve renders as ``…`` — enough to keep the surrounding
    prose intact without pretending to know a runtime value.
    """
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.JoinedStr):
        parts = []
        for piece in node.values:
            if isinstance(piece, ast.FormattedValue):
                parts.append(_render_placeholder(piece.value, constants))
            else:
                parts.append(_render(piece, constants) or "")
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _render(node.left, constants), _render(node.right, constants)
        if left is not None and right is not None:
            return left + right
    return None


def _render_placeholder(node, constants):
    if isinstance(node, ast.Name):
        return constants.get(node.id, "…")
    rendered = _render(node, constants)
    return rendered if rendered is not None else "…"


def _callee(node):
    while isinstance(node, ast.Attribute):
        node = node.value
        if isinstance(node, ast.Name):
            break
    if isinstance(node, ast.Name):
        return node.id
    return None


def _formatted(node):
    """``dev_repo(...)`` / ``citations.dev_repo(...)`` — the citation is routed."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else _callee(func)
    return name in FORMATTER_NAMES


def _bare_private_constant_nodes(tree):
    """Node ids of the ``_NAME = "dev/…"`` fragments modules compose citations out of."""
    ids = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        value = node.value.value
        if not isinstance(value, str) or not _is_bare_path(value):
            continue
        if any(isinstance(t, ast.Name) and t.id.startswith("_") for t in node.targets):
            ids.add(id(node.value))
    return ids


def _source_offenders(source, rel):
    tree = ast.parse(source)
    constants = _module_string_constants(tree)
    excused = _bare_private_constant_nodes(tree)
    found = []

    def walk(node):
        if _formatted(node):
            return
        rendered = _render(node, constants)
        if rendered is not None:
            if (
                cites_dev_repo(rendered)
                and not is_labelled(rendered)
                and id(node) not in excused
            ):
                found.append((f"{rel}:{node.lineno}", _snippet(rendered,
                                                               dev_repo_paths(rendered)[0])))
            return
        for child in ast.iter_child_nodes(node):
            walk(child)

    walk(tree)
    return found


@pytest.mark.parametrize("path", sorted(SRC.rglob("*.py")), ids=lambda p: p.name)
def test_no_composed_source_string_cites_an_unlabelled_dev_repo_path(path):
    rel = path.relative_to(REPO_ROOT).as_posix()
    offenders = _source_offenders(path.read_text(encoding="utf-8"), rel)
    assert not offenders, (
        f"{rel} composes {len(offenders)} citation(s) of a maintainer-repo path with no "
        f"{DEV_REPO_LABEL!r} label: {offenders}")


# --------------------------------------------------------------------------- #
# Leg 3 — the RETURNED data                                                    #
# --------------------------------------------------------------------------- #

def _library_modules():
    names = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).with_suffix("")
        parts = [p for p in rel.parts if p != "__init__"]
        names.append(".".join(["larkdocio", *parts]))
    return names


def _reachable_strings(value, label, out, seen, depth=0):
    if depth > 8 or len(out) > 20000:
        return
    if isinstance(value, str):
        out.append((label, value))
        return
    if isinstance(value, (bytes, int, float, bool, type(None))):
        return
    if id(value) in seen:
        return
    seen.add(id(value))
    if isinstance(value, dict):
        for key, sub in value.items():
            _reachable_strings(sub, f"{label}[{key!r}]", out, seen, depth + 1)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for index, sub in enumerate(value):
            _reachable_strings(sub, f"{label}[{index}]", out, seen, depth + 1)
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        for field in dataclasses.fields(value):
            _reachable_strings(getattr(value, field.name, None),
                               f"{label}.{field.name}", out, seen, depth + 1)


def test_no_public_registry_value_cites_an_unlabelled_dev_repo_path():
    """The error taxonomy, the op registries, the vocabulary tables and the evidence
    constants — read as VALUES, which is how a consumer meets them."""
    offenders = []
    for modname in _library_modules():
        module = importlib.import_module(modname)
        for name in dir(module):
            if name.startswith("_"):
                continue
            strings = []
            _reachable_strings(getattr(module, name, None), f"{modname}.{name}",
                               strings, set())
            for label, text in strings:
                if cites_dev_repo(text) and not is_labelled(text):
                    offenders.append((label, _snippet(text, dev_repo_paths(text)[0])))
    assert not offenders, (
        f"{len(offenders)} value(s) a consumer is handed name a maintainer-repo path with no "
        f"{DEV_REPO_LABEL!r} label: {sorted(set(offenders))[:8]}")


# --------------------------------------------------------------------------- #
# Leg 4 — does the cited path EXIST? (LD-675)                                 #
# --------------------------------------------------------------------------- #

#: A citation cut short — a glob (``00-*``), an elision (``001-…json``), a path wrapped across
#: two comment lines, or an unresolved f-string placeholder. What follows it in the text says
#: so, or it ends mid-name. Such a citation resolves only by PREFIX, inside a directory that
#: must itself still exist — so it can still fail, and does when its study tree is gone.
_TRUNCATION_FOLLOWERS = ("*", "…", "{")
_TRUNCATED_ENDINGS = ("-", "_")


def _python_citation_texts(source):
    """Every string a ``.py`` file carries, read the way the PARSER reads it, plus comments.

    A line scan is the wrong instrument here and was measured to be: it cuts
    ``"…delete-the-"`` / ``"file.json"`` (implicit concatenation) in two and reports half a
    path as dangling. The AST joins adjacent literals and :func:`_render` folds the module's
    own path constants into f-strings — the same rendering leg 2 uses. Unlike leg 2 it does
    **not** stop at :func:`dev_repo`: routing a citation through the formatter excuses its
    LABEL, never its EXISTENCE. Comments ship in the wheel's source too, so they are read.
    """
    tree = ast.parse(source)
    constants = _module_string_constants(tree)
    texts = []

    def walk(node):
        rendered = _render(node, constants)
        if rendered is not None:
            texts.append((getattr(node, "lineno", 0), rendered))
            return
        for child in ast.iter_child_nodes(node):
            walk(child)

    walk(tree)
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT:
            texts.append((tok.start[0], tok.string))
    return texts


def maintainer_repo_citations(shipped_root, repo_root):
    """``(citations, undecodable)`` — every maintainer-repo path cited under ``shipped_root``.

    ``citations`` is a list of ``(file, line, path, next_char)``, ``file`` relative to
    ``repo_root``. The population rule is :data:`~larkdocio.common.citations.DEV_REPO_PATH`,
    the library's own — the very pattern the label legs use — so this leg cannot quietly
    examine a narrower set than they do.
    """
    citations, undecodable = [], []
    for path in sorted(p for p in shipped_root.rglob("*") if p.is_file()):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(repo_root).as_posix()
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            undecodable.append(rel)
            continue
        texts = _python_citation_texts(text) if path.suffix == ".py" else [(0, text)]
        for line, body in texts:
            for match in DEV_REPO_PATH.finditer(body):
                citations.append((rel, line, match.group(0), body[match.end():match.end() + 1]))
    return citations, undecodable


def citation_resolves(path, next_char, repo_root):
    target = path.rstrip(".")
    if (repo_root / target).exists():
        return True
    if target.endswith(_TRUNCATED_ENDINGS) or next_char in _TRUNCATION_FOLLOWERS:
        parent, stem = (repo_root / target).parent, (repo_root / target).name
        return parent.is_dir() and any(child.name.startswith(stem) for child in parent.iterdir())
    return False


def dangling_citations(shipped_root, repo_root):
    """``{(file, path)}`` that resolve nowhere — after asserting the leg can see anything.

    Raises when the population is empty (AC3: an inert guard must redden for THAT reason, not
    pass) or when a shipped file could not be decoded (an unread file is not a clean file).
    """
    citations, undecodable = maintainer_repo_citations(shipped_root, repo_root)
    assert not undecodable, (
        f"these shipped files could not be decoded, so their citations were NOT resolved: "
        f"{undecodable}")
    assert citations, (
        f"no maintainer-repo citation was found under {shipped_root} — the population is "
        "empty, so the guard is inert")
    return {(f, p) for f, _line, p, nxt in citations if not citation_resolves(p, nxt, repo_root)}


#: **The tolerance this leg was armed behind is DISCHARGED (LD-676, 2026-09-25).** LD-675 landed
#: it with ``DANGLING_CITATION_DEBT`` — 42 ``(file, path)`` pairs, 28 targets, 22 files, every
#: one a shipped citation the 2026-09-18 prune had left dangling — plus two tests holding that
#: table shrink-only and owned. LD-676 re-pointed or retired every row, each disposition stated
#: in its issue file, and deleted the table, its owner and both tests in the same change. There
#: is no tolerance now: any dangling citation reddens the arm below.


@private_tree.citations
def test_every_shipped_maintainer_repo_citation_resolves():
    missing = sorted(dangling_citations(SRC, REPO_ROOT))
    assert not missing, (
        f"{len(missing)} shipped citation(s) name a maintainer-repo path that exists nowhere — a "
        "reader following it lands on nothing. Re-point it at a path that exists, inline the "
        "fact it carried, or retire the citation; never delete the evidence it names, and never "
        f"answer this with a tolerance table: {missing}")


# ---- AC2: label and existence are separate checks, and cannot be conflated ----

def _fake_tree(tmp_path, module_source):
    repo = tmp_path / "repo"
    (repo / "dev").mkdir(parents=True)
    (repo / "dev" / "real.md").write_text("evidence\n", encoding="utf-8")
    (repo / "src" / "larkdocio").mkdir(parents=True)
    (repo / "src" / "larkdocio" / "mod.py").write_text(module_source, encoding="utf-8")
    return repo, repo / "src" / "larkdocio"


def test_a_LABELLED_citation_of_a_MISSING_path_fails_existence_and_passes_label(tmp_path):
    source = f'MSG = "see dev/gone.md ({DEV_REPO_LABEL})"\n'
    repo, shipped = _fake_tree(tmp_path, source)
    assert not _source_offenders(source, "mod.py"), "the label leg should accept it"
    assert dangling_citations(shipped, repo) == {("src/larkdocio/mod.py", "dev/gone.md")}


def test_a_RESOLVING_path_with_NO_label_fails_label_and_passes_existence(tmp_path):
    source = 'MSG = "see dev/real.md"\n'
    repo, shipped = _fake_tree(tmp_path, source)
    assert _source_offenders(source, "mod.py"), "the label leg should reject it"
    assert dangling_citations(shipped, repo) == set()


def test_routing_through_the_formatter_excuses_the_label_never_the_existence(tmp_path):
    source = 'MSG = dev_repo("see dev/gone.md")\n'
    repo, shipped = _fake_tree(tmp_path, source)
    assert not _source_offenders(source, "mod.py")
    assert dangling_citations(shipped, repo) == {("src/larkdocio/mod.py", "dev/gone.md")}


def test_the_parser_faithful_read_does_not_manufacture_misses(tmp_path):
    """Implicit concatenation, a folded constant, a glob and a wrapped comment all resolve."""
    source = (
        '_STUDY = "dev/study"\n'
        'A = ("see dev/study/captures/05-long-"\n'
        '     "name.json")\n'
        'B = f"{_STUDY}/captures/05-long-name.json"\n'
        'C = "captures dev/study/captures/05-*"\n'
        '# recorded in dev/study/captures/05-long-\n'
        '# name.json\n'
    )
    repo, shipped = _fake_tree(tmp_path, source)
    (repo / "dev" / "study" / "captures").mkdir(parents=True)
    (repo / "dev" / "study" / "captures" / "05-long-name.json").write_text("{}", encoding="utf-8")
    assert dangling_citations(shipped, repo) == set()
    # …and the prefix fallback is not a free pass: gone study tree, same text, all dangle.
    import shutil
    shutil.rmtree(repo / "dev" / "study")
    assert {p for _f, p in dangling_citations(shipped, repo)} >= {
        "dev/study/captures/05-long-name.json", "dev/study/captures/05-"}


def test_markdown_is_in_the_existence_population(tmp_path):
    repo, shipped = _fake_tree(tmp_path, 'X = 1\n')
    (shipped / "GUIDE.md").write_text("See [it](dev/gone.md) and `dev/real.md`.\n",
                                      encoding="utf-8")
    assert dangling_citations(shipped, repo) == {("src/larkdocio/GUIDE.md", "dev/gone.md")}


# ---- AC3: it cannot pass vacuously ----

def test_an_EMPTY_corpus_reddens_for_being_empty(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src" / "larkdocio").mkdir(parents=True)
    (repo / "src" / "larkdocio" / "mod.py").write_text("X = 1\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="the guard is inert"):
        dangling_citations(repo / "src" / "larkdocio", repo)


def test_an_UNDECODABLE_file_reddens_rather_than_being_skipped(tmp_path):
    repo, shipped = _fake_tree(tmp_path, 'MSG = "see dev/real.md"\n')
    (shipped / "blob.bin").write_bytes(b"\xff\xfe dev/gone.md")
    with pytest.raises(AssertionError, match="could not be decoded"):
        dangling_citations(shipped, repo)


# --------------------------------------------------------------------------- #
# The bug this issue was filed for, pinned                                     #
# --------------------------------------------------------------------------- #

def test_the_person_refusal_no_longer_routes_a_consumer_to_a_file_they_lack():
    """The refusal a caller reads at the moment they are blocked. It kept the fact — the
    other-user name→id gap is deferred and nothing here stands in for it — and dropped the
    citation of a queue document that ships nowhere."""
    from larkdocio.base.cells import FieldSpec
    from larkdocio.base.write_cells import PersonNameNotResolvableError, encode_cell

    spec = FieldSpec(field_id="fld1", field_name="Owner", type=11, ui_type="User")
    with pytest.raises(PersonNameNotResolvableError) as excinfo:
        encode_cell("Ada Lovelace", spec)

    message = str(excinfo.value)
    assert "downtime-queue" not in message and not cites_dev_repo(message), message
    # the actionable half survives intact
    assert "IDS ONLY" in message
    assert "larkdocio.contacts.resolve_user" in message
    assert "HARVEST" in message


# --------------------------------------------------------------------------- #
# Proof the guard bites                                                        #
# --------------------------------------------------------------------------- #

LEAK = 'MSG = f"the probe that proved it is at {_CAPTURES}/x.json, read it"\n'
FIXED = 'MSG = dev_repo(f"the probe that proved it is at {_CAPTURES}/x.json, read it")\n'
PREAMBLE = '_CAPTURES = "dev/base-study/captures"\n'


def test_the_source_leg_bites_on_a_newly_introduced_leak():
    assert _source_offenders(PREAMBLE + LEAK, "fake.py"), "the guard let a leak through"
    assert not _source_offenders(PREAMBLE + FIXED, "fake.py")
    assert not _source_offenders(
        PREAMBLE + 'MSG = "…at dev/x.md (in the dev repo), recorded once"\n', "fake.py")


def test_the_source_leg_still_bites_when_the_path_is_spelled_inline():
    assert _source_offenders('MSG = "see dev/downtime-queue.md"\n', "fake.py")
    assert _source_offenders('raise X("recorded in progress/todo/notes.md")\n', "fake.py")


def test_a_bare_private_fragment_is_excused_but_only_while_private():
    assert not _source_offenders('_CAPTURES = "dev/base-study/captures"\n', "fake.py")
    assert _source_offenders('EVIDENCE = "dev/base-study/captures/x.json"\n', "fake.py")


def test_the_formatter_is_idempotent_and_leaves_a_clean_string_alone():
    assert dev_repo("captures/a.json") == "captures/a.json"
    assert dev_repo(None) is None
    once = dev_repo("dev/base-study/captures/a.json")
    assert once == f"dev/base-study/captures/a.json ({DEV_REPO_LABEL})"
    assert dev_repo(once) == once
    assert dev_repo("tests/test_live_base_views.py") == "tests/test_live_base_views.py"


# --------------------------------------------------------------------------- #
# Leg 5 — a private ROOT DOCUMENT is cited only with the label (LD-708, Y1)     #
# --------------------------------------------------------------------------- #
#
# The four legs above know a private record by its directory (``dev/``, ``progress/``,
# ``requirements/``), so a citation of a private root document — "PROJECT.md § Quality bar" —
# escaped all of them, and 14 shipped evidence strings plus a handful of docstrings cited
# PROJECT.md bare while the 1.53.0 changelog said such citations were gone. This leg reads
# every file under ``src/`` (Python and packaged Markdown) and asks that each mention of a
# private root document wear :data:`DEV_REPO_LABEL` within :data:`_LABEL_REACH` characters.
#
# The list is hand-kept here only because the public tree has no allow-list to derive it from;
# in this repository :func:`test_the_private_root_documents_are_exactly_what_the_export_withholds`
# holds it, both ways, to ``dev/public-export/export.py``'s INCLUDE.

#: The root documents the export does not ship, plus the planning record's register (which
#: lives under ``requirements/`` and is cited by its bare name).
PRIVATE_ROOT_DOCS = ("AGENTS.md", "ARCHIVE.md", "CLAUDE.md", "PROJECT.md", "progress.md")
CITED_BY_BARE_NAME = ("DECISIONS.md",)

_PRIVATE_DOC = re.compile(
    r"(?<![\w./-])(?:%s)(?![\w-])"
    % "|".join(re.escape(d) for d in PRIVATE_ROOT_DOCS + CITED_BY_BARE_NAME))
#: Python implicit concatenation and comment/docstring line breaks, folded to one space so a
#: label wrapped onto the next line still counts as next to its citation.
_JOIN = re.compile(r'(?:"\s*\n\s*(?:f|r|rf|fr)?"|\n\s*(?:#\s*)?)')
_LABEL_REACH = 80


def private_doc_misses(text):
    """Each unlabelled mention of a private root document in ``text``, as a short snippet."""
    flat = re.sub(r"[ \t]+", " ", _JOIN.sub(" ", text))
    misses = []
    for match in _PRIVATE_DOC.finditer(flat):
        if DEV_REPO_LABEL not in flat[match.end():match.end() + _LABEL_REACH]:
            misses.append(" ".join(flat[max(0, match.start() - 40):match.end() + 40].split()))
    return misses


def test_no_shipped_file_cites_a_private_root_document_without_the_label():
    files = sorted(p for p in SRC.rglob("*") if p.suffix in (".py", ".md") and p.is_file())
    assert len(files) > 50, len(files)
    offenders = []
    for path in files:
        for snippet in private_doc_misses(path.read_text(encoding="utf-8")):
            offenders.append((str(path.relative_to(REPO_ROOT)), snippet))
    assert not offenders, (
        f"{len(offenders)} shipped mention(s) of a private root document without "
        f"{DEV_REPO_LABEL!r}: {offenders[:8]}")


def test_the_root_document_leg_bites_and_reads_across_a_line_break():
    assert private_doc_misses("see PROJECT.md § Quality bar")
    assert private_doc_misses("cites CLAUDE.md's house rules")
    assert not private_doc_misses('"under PROJECT.md (in the "\n    "dev repo) the rule"')
    assert not private_doc_misses("(PROJECT.md § Quality\nbar, in the dev repo)")
    # A path that merely ends in the name, and a shipped document, are not this class.
    assert not private_doc_misses("requirements/DECISIONS.md and README.md")


@private_tree.citations
def test_the_private_root_documents_are_exactly_what_the_export_withholds():
    spec = importlib.util.spec_from_file_location(
        "_export", REPO_ROOT / "dev" / "public-export" / "export.py")
    export = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(export)
    withheld = {p.name for p in REPO_ROOT.glob("*.md") if not export.included(p.name)}
    assert withheld == set(PRIVATE_ROOT_DOCS), (withheld, PRIVATE_ROOT_DOCS)
    for name in CITED_BY_BARE_NAME:
        assert any(not export.included(str(p.relative_to(REPO_ROOT)))
                   for p in REPO_ROOT.rglob(name) if ".venv" not in p.parts), name
