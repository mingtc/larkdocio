"""The extract-and-RUN harness for the shipped guide's recipes (LD-133 / dogfood F13).

**Why this exists.** LD-128 verified the guide's recipes by ``compile()``-ing them — a
*syntax* check. Syntax cannot see an **undefined free variable**, so the shipped
docx-write recipe passed the gate while ``NameError``-ing on its first line
(``dry_run(requests, root)`` — ``root`` was never produced). Dogfood F13 found it by
pasting the recipe into a file and running it. This module makes the suite do exactly
that: **extract each fenced recipe from the guide verbatim and EXECUTE it offline**, so a
future guide edit that breaks a recipe reddens the suite instead of shipping.

**The execution contract — no hidden scaffolding.** Every recipe is ``exec``'d in a
namespace containing **builtins only** (:func:`run_recipe`). A recipe therefore has to
import everything it uses, exactly as a consumer's file does; a free variable the recipe
never binds is a ``NameError`` here just as it is in a consumer's terminal. Nothing is
pre-seeded into the namespace, ever.

**What is faked, and what is real.** Only the **network boundary** is replaced — the
HTTP-calling client methods, and ``init_env`` (which would otherwise write a ``.env``
into the cwd). Every line of larkdocio *logic* the recipes teach runs for real: the
parser builds the real node tree from real SDK ``Block`` objects, ``dry_run`` /
``apply`` / ``resolve`` are the shipped engines, ``render_spreadsheet`` is the shipped
renderer. The doubles are subclasses of (or signature-checked against) the shipped
clients — :func:`double_signature_mismatches` reddens if a double drifts from the real
API it stands in for.

**The credential chain is exercised, not bypassed.** ``init_env`` is redirected to load a
**tmp** ``.env`` the stage writes, and the process environment is stripped of every
``LARK_*`` var first. So the recipes' opening ``init_env(...)`` line is *load-bearing* in
the harness exactly as it is in production: delete it and the write recipes raise
``LarkConfigError`` (proven by ``test_discovery_truth.py`` §AC4). ``get_read_credentials``
/ ``get_write_credentials`` are the real resolvers reading that tmp env.

**Where the doubles live (LD-310).** This module is the **recipe** side: it reads the guide,
extracts and runs the recipes, and holds each recipe's post-conditions (the ``_check_*``
functions and ``RECIPE_SPECS``). The **offline double pool** — every ``Offline*`` client,
the fixture payloads, the Markdown call spy and :class:`OfflineStage` / :func:`stage` — now
lives in ``tests/offline_doubles.py`` and is **re-exported here by name** (see the shim
below), so ``import guide_recipes as gr`` still resolves ``gr.stage`` and every
``gr.Offline*``. Edit a double there, edit a recipe check here.
"""
import ast
import builtins
import contextlib
import os
import re
import tempfile
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from larkdocio import guide

# --------------------------------------------------------------------------- #
# 1. Extraction — the guide's sections, its python blocks, and its recipes.     #
# --------------------------------------------------------------------------- #

#: The recipe chapter's own ``##`` heading — kept because it still exists and still holds the
#: chapter's promise (*"every recipe below runs as pasted"*), but **no longer the attribution
#: gate**. See :func:`python_blocks`.
_RECIPES_SECTION = "## Recipes"

#: Matches the start of any ``## `` heading line, used to find the ``##`` section a block sits
#: in. LD-541 made this the attribution boundary: before it, the gate was *"the nearest
#: preceding ``## `` heading is literally ``## Recipes``"*, which was true only while the whole
#: recipe list lived under that one heading. The restructure groups the recipes by consumer
#: task, one ``## Task — …`` heading per task, so that gate would have recognised **zero**
#: recipe blocks. The replacement asks the structural question the old one was a proxy for:
#: *is there a ``### Recipe:`` heading between this block and the ``##`` heading above it?*
#: Measured behaviour-identical on the pre-restructure document — 60 recipes, 65 attributed
#: blocks, 10 orphans, zero attribution changes — so this is the same census read structurally.
_H2_LINE = "\n## "
_PY_FENCE_RE = re.compile(r"```python\n(.*?)```", re.DOTALL)
_RECIPE_HEADING_RE = re.compile(r"^### Recipe: (.+)$", re.MULTILINE)


def _slug(heading: str) -> str:
    """``### Recipe: the docx write handshake`` → ``the-docx-write-handshake``."""
    return re.sub(r"[^a-z0-9]+", "-", heading.strip().lower()).strip("-")


@dataclass(frozen=True)
class PythonBlock:
    """One ````python```` fenced block in the guide, with where it came from."""

    source: str
    #: the ``### Recipe: <name>`` heading it sits under, or ``None`` outside a recipe.
    recipe_heading: Optional[str]
    #: ``True`` when the block sits inside the guide's ``## Recipes`` section.
    in_recipes_section: bool

    @property
    def slug(self) -> Optional[str]:
        return _slug(self.recipe_heading) if self.recipe_heading else None


def python_blocks(text: Optional[str] = None) -> List[PythonBlock]:
    """Every ````python```` block in the guide, tagged with its recipe heading (if any).

    A block's heading is the nearest preceding ``### Recipe:`` line **within its own ``##``
    section**; ``in_recipes_section`` is whether it has one at all — which is the same
    question as *"does this block sit under a recipe?"*, asked structurally instead of by
    naming one heading (see :data:`_H2_LINE`).
    """
    text = guide(full=True) if text is None else text
    out: List[PythonBlock] = []
    for m in _PY_FENCE_RE.finditer(text):
        before = text[: m.start()]
        since_h2 = before[max(before.rfind(_H2_LINE), 0):]
        headings = _RECIPE_HEADING_RE.findall(since_h2)
        out.append(PythonBlock(
            source=m.group(1),
            recipe_heading=headings[-1] if headings else None,
            in_recipes_section=bool(headings),
        ))
    return out


def recipe_headings(text: Optional[str] = None) -> List[str]:
    """Every ``### Recipe: <name>`` heading in the guide, in document order."""
    return [h.strip() for h in _RECIPE_HEADING_RE.findall(guide(full=True) if text is None else text)]


def recipe_preamble(slug: str, text: Optional[str] = None) -> str:
    """The prose between recipe ``slug``'s heading and its first fenced block (LD-138).

    The **preamble is where a consumer reads before pasting**, which is why AC3b requires the
    concurrency warning *there* and not merely somewhere in the guide. Returns the text
    verbatim (bash fences included — a CLI-first recipe's warning may sit above them), so the
    caller decides how to normalize it.
    """
    text = guide(full=True) if text is None else text
    headings = {_slug(h): h for h in recipe_headings(text)}
    heading = headings.get(slug)
    assert heading is not None, f"the guide has no recipe {slug!r}"
    start = text.index(f"### Recipe: {heading}")
    rest = text[start:]
    fence = rest.find("```")
    return rest[:fence] if fence != -1 else rest


#: The **D9 concurrency doctrine**, as the phrases every authoring surface must state
#: (LD-138 AC3b). Asserted at content level after :func:`doc_prose.prose` normalization, so
#: wrapping and emphasis are irrelevant and only the words count.
#:
#: **Wording is coordinated with LD-139 on purpose.** S6 ships the ``STALE_DOCUMENT``
#: refusal whose ``detail`` repeats this doctrine; until it lands, the docs must not name a
#: refusal that does not exist yet — so the required phrasing is deliberately
#: mechanism-free ("the engine refuses when the document changed under the plan") and stays
#: true either way. LD-139 may add the refusal *name* to these surfaces; it must not have to
#: rewrite the doctrine.
CONCURRENCY_WARNING_PHRASES = (
    "do not edit the document",
    "concurrent",
    "refuses",
    "rather than guess",
    "re-download",
    "re-plan",
)


def authoring_recipe_slugs(text: Optional[str] = None) -> List[str]:
    """The recipes that AUTHOR into a docx document — **derived, never hand-listed**.

    A recipe counts when its own code imports the docx write surface and calls ``apply``:
    that is exactly the set for which a concurrent human edit can cause a refusal, so the
    set the D9 warning must cover is computed from the recipes themselves. Hand-listing it
    would let the next write recipe ship without the warning — the failure mode AC3b exists
    to prevent. (The sheets write recipe is not in it: its staleness story is
    ``STALE_SHEET``, documented on its own contract.)
    """
    out = []
    for slug, blocks in recipe_blocks(text).items():
        source = "\n".join(b.source for b in blocks)
        if "larkdocio.write" in source and re.search(r"\bapply\(", source):
            out.append(slug)
    return sorted(out)


def recipe_blocks(text: Optional[str] = None) -> Dict[str, List[PythonBlock]]:
    """``{recipe slug: [its python blocks]}`` for every ``### Recipe:`` heading."""
    out: Dict[str, List[PythonBlock]] = {_slug(h): [] for h in recipe_headings(text)}
    for block in python_blocks(text):
        if block.slug is not None:
            out.setdefault(block.slug, []).append(block)
    return out


def recipe_sources(slug: str) -> List[str]:
    """Every python block of recipe ``slug``, in document order (LD-445).

    Almost every recipe has exactly one — see :func:`recipe_source`. A recipe carrying more
    than one declares it in :data:`RECIPE_SPECS` (``extra_checks``), and **each block is
    executed in a namespace of its own**, sharing nothing but the filesystem: that is what
    makes a *resumable* script (the file-first variant of the copy-this recipe) a claim the
    suite can actually falsify rather than prose.
    """
    blocks = recipe_blocks().get(slug)
    assert blocks, f"recipe {slug!r} carries no python block"
    return [block.source for block in blocks]


def recipe_source(slug: str) -> str:
    """The FIRST python block of recipe ``slug``.

    Historically this asserted there was exactly one. LD-445 kept the *reason* — a recipe's
    blocks must all be executed, never merely compiled or silently skipped — and moved it to
    where it can still bite for a multi-block recipe: ``test_discovery_truth.py``'s
    "every block is executed and checked" guard, which walks :func:`recipe_sources` against
    the spec's ``extra_checks``. The single-block assertion survives for every recipe that
    has not declared extra blocks.
    """
    blocks = recipe_blocks().get(slug)
    assert blocks, f"recipe {slug!r} carries no python block"
    expected = 1 + len(SPEC_BY_SLUG[slug].extra_checks) if slug in SPEC_BY_SLUG else 1
    assert len(blocks) == expected, (
        f"recipe {slug!r} carries {len(blocks)} python blocks but declares {expected}; a "
        "block with no post-condition would run unchecked (or not at all)"
    )
    return blocks[0].source


# --------------------------------------------------------------------------- #
# 2. The free-variable check — what a compile()-only gate is blind to (F13).    #
# --------------------------------------------------------------------------- #

class _Bindings(ast.NodeVisitor):
    """Every name a block BINDS anywhere in it (imports, assignments, loop/with/except
    targets, comprehension targets, walrus, def/class, function params).

    Deliberately scope-flattening: a name bound in ANY nested scope counts as bound.
    That can only ever *under*-report an undefined free variable, never invent one — so a
    failure of :func:`undefined_free_names` is always a real, reproducible ``NameError``
    in a straight-line recipe (which is what the guide's recipes are).
    """

    def __init__(self):
        self.names = set()

    # -- imports ---------------------------------------------------------- #
    def visit_Import(self, node):
        for alias in node.names:
            self.names.add(alias.asname or alias.name.split(".")[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        for alias in node.names:
            self.names.add(alias.asname or alias.name)
        self.generic_visit(node)

    # -- any Store/Del target (assign, for, with-as, comprehension, walrus) - #
    def visit_Name(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.names.add(node.id)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        if node.name:
            self.names.add(node.name)
        self.generic_visit(node)

    def _visit_callable(self, node):
        self.names.add(node.name)
        args = node.args
        for a in (list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
                  + [args.vararg, args.kwarg]):
            if a is not None:
                self.names.add(a.arg)
        self.generic_visit(node)

    visit_FunctionDef = _visit_callable
    visit_AsyncFunctionDef = _visit_callable

    def visit_ClassDef(self, node):
        self.names.add(node.name)
        self.generic_visit(node)

    def visit_Global(self, node):
        self.names.update(node.names)

    def visit_Nonlocal(self, node):
        self.names.update(node.names)


def undefined_free_names(source: str) -> List[str]:
    """Names the block LOADS but never binds and that are not builtins.

    This is the check a ``compile()``-only gate cannot make: the shipped docx-write
    recipe compiled cleanly while ``root`` was undefined (dogfood F13). Empty list ⇒ the
    block cannot ``NameError`` on a free variable.
    """
    tree = ast.parse(source)
    binder = _Bindings()
    binder.visit(tree)
    loaded = {
        n.id for n in ast.walk(tree)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
    }
    return sorted(loaded - binder.names - set(dir(builtins)))


# --------------------------------------------------------------------------- #
# 2b. The COMMENTED-OUT-CODE gate — the LD-152 harness hole (dogfood F3).       #
#                                                                               #
# LD-133's two checks both read only the code that RUNS: `undefined_free_names`  #
# parses with `ast` (which discards comments) and `run_recipe` execs (a comment  #
# never runs). So the harness's unit of verification was *executable source*     #
# while a recipe's unit of teaching is *every line a consumer may paste* — and a #
# commented-out alternative is pasted by uncommenting it. That gap is how        #
# `fidelity=exported_by_sheet_id` shipped with the variable undefined, in a      #
# guide whose preamble promises "no undefined free variables".                   #
#                                                                               #
# The closure widens the unit: every python line a consumer could paste is       #
# checked — the live source AND each commented-out statement promoted to live    #
# code — for the three defect classes a pasted line can carry: an undefined free #
# variable, a non-existent symbol, and a syntax error. Deliberately STATIC:      #
# commented alternatives are mutually exclusive with the lines they replace, so  #
# they cannot all be executed; a static check is what can cover all of them.     #
# --------------------------------------------------------------------------- #

#: A whole-line comment: its indent and its body. A **trailing** comment after real code is
#: not a candidate — only a line whose first non-space character is ``#`` can be a
#: commented-out statement.
_WHOLE_LINE_COMMENT_RE = re.compile(r"^(\s*)#[ \t]?(.*)$")


@dataclass(frozen=True)
class CommentedCode:
    """One commented-out **statement** found in a guide block."""

    #: 0-based index into ``source.splitlines()`` — the line the comment occupies.
    lineno: int
    #: the comment's own indentation, preserved when it is promoted.
    indent: str
    #: the statement text (the comment body, ``#`` and one optional space stripped).
    code: str
    #: which statement shape it is — ``assign`` / ``import`` / ``call``, or ``broken``
    #: (unmistakably code, but it does not parse: the syntax-error class).
    kind: str

    def __str__(self) -> str:
        return f"line {self.lineno + 1}: {self.code}"


#: An assignment or a call at the start of the line — ``x = …`` / ``x.y(…``. ``=(?!=)``
#: keeps a comparison out.
_CODE_SHAPE_RE = re.compile(r"^[A-Za-z_][\w.]*\s*(=(?!=)|\()")

#: An import statement's unmistakable shape. The ``import`` keyword is REQUIRED in the
#: ``from`` form so ordinary prose ("from the read recipe above") is not code-shaped.
_IMPORT_SHAPE_RE = re.compile(
    r"^(from\s+[A-Za-z_][\w.]*\s+import\b|import\s+[A-Za-z_][\w.]*)")

_OPENERS = {")": "(", "]": "[", "}": "{"}


def _first_call_never_closes(code: str) -> bool:
    """``True`` when ``code``'s **first** bracket is never closed — the fingerprint of a
    **truncated** statement (``render_spreadsheet(pairs``), which is how a syntax error hides
    in a comment.

    Deliberately the *first* bracket and not "brackets are unbalanced anywhere", because the
    guide's prose comments are full of balanced-then-continued parentheses: ``# apply()
    handed back one id per block it created … Re-read (a plan`` wraps onto the next comment
    line, so its *last* paren is unclosed while the statement-shaped head (``apply()``) is
    perfectly balanced. Anchoring on the first bracket asks "was the call this line opens
    ever finished?", which is the actual truncation signal, and leaves prose alone.
    """
    start = next((i for i, ch in enumerate(code) if ch in "([{"), None)
    if start is None:
        return False
    stack = []
    for ch in code[start:]:
        if ch in "([{":
            stack.append(ch)
        elif ch in _OPENERS:
            if not stack or stack.pop() != _OPENERS[ch]:
                return True
            if not stack:
                return False          # the opening bracket closed — not a truncation
    return bool(stack)


def _statement_kind(code: str) -> Optional[str]:
    """``assign`` / ``import`` / ``call`` if ``code`` is a Python statement of a shape a
    consumer plausibly uncomments — else ``None``.

    **Precision is as load-bearing as recall.** A detector that treated every comment as
    code would redden on the guide's explanatory prose, and the first "fix" would be to
    weaken or delete the detector. Prose happens to parse more often than one expects
    (``values-only (fidelity=None)`` is a valid ``BinOp``), so the filter is not "does it
    parse" but "is it ONE statement of a shape that is unambiguously code": a binding, an
    import, or a bare call. A parenthesized prose fragment is an ``Expr`` of a ``BinOp`` /
    ``Constant`` / ``Tuple`` and is rejected.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    if len(tree.body) != 1:
        return None
    node = tree.body[0]
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return "import"
    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        return "assign"
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        func = node.value.func
        if isinstance(func, (ast.Name, ast.Attribute)):
            return "call"
    return None


def commented_code_lines(source: str) -> List[CommentedCode]:
    """Every commented-out **statement** in ``source``, in document order.

    These are the lines a consumer uncomments — the reason the F3 defect existed at all —
    and therefore the lines the harness has to hold to the same standard as live code.

    A line that is unmistakably code but does **not** parse (an import shape, or an
    assignment/call with unbalanced brackets) is returned with kind ``broken``: promoting it
    is how the **syntax-error** class gets caught inside a comment, where parsing alone can
    never recognize it.
    """
    out: List[CommentedCode] = []
    for i, line in enumerate(source.splitlines()):
        if not line.strip().startswith("#"):
            continue
        m = _WHOLE_LINE_COMMENT_RE.match(line)
        if m is None:
            continue
        body = m.group(2).rstrip()
        kind = _statement_kind(body)
        if kind is None:
            code_shaped = (
                _IMPORT_SHAPE_RE.match(body)
                or (_CODE_SHAPE_RE.match(body) and _first_call_never_closes(body))
            )
            kind = "broken" if code_shaped else None
        if kind is not None:
            out.append(CommentedCode(lineno=i, indent=m.group(1), code=body, kind=kind))
    return out


def uncommented_source(source: str, commented: CommentedCode) -> str:
    """``source`` with ``commented`` promoted to live code **in place** — same line, same
    indentation — so a reported syntax error's line number points at the guide's own line.
    """
    lines = source.splitlines()
    lines[commented.lineno] = commented.indent + commented.code
    return "\n".join(lines) + ("\n" if source.endswith("\n") else "")


def _unresolvable_imports(tree: ast.AST) -> List[str]:
    """Every import statement in ``tree`` that does not resolve — the **non-existent
    symbol** class.

    Resolution is by actually executing the import statement in an isolated namespace
    (never a name heuristic), so a submodule, a re-export and a plain attribute all resolve
    the way they will for the consumer. Only import statements are executed — nothing else
    from the recipe runs here.
    """
    problems = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        statement = ast.unparse(node)
        try:
            exec(compile(statement, "<import check>", "exec"), {})
        except Exception as exc:
            problems.append(f"import does not resolve: {statement!r} → {exc}")
    return problems


def _static_problems(source: str) -> List[str]:
    """The three static defect classes in ONE piece of source, location-free.

    Kept location-free so the caller can subtract the live source's own problems from a
    promoted variant's and report only what promoting the comment introduced.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"syntax error: {exc.msg} (line {exc.lineno})"]
    problems = [
        f"undefined free variable {name!r} — it is never bound, so this line NameErrors "
        f"as pasted"
        for name in undefined_free_names(source)
    ]
    problems.extend(_unresolvable_imports(tree))
    return problems


def static_problems(source: str) -> List[str]:
    """Every static defect in every python line of ``source`` a consumer could paste.

    Covers the **live** source and, one at a time, each **commented-out statement**
    promoted to live code. One at a time (rather than all at once) because two commented
    alternatives may deliberately bind the same name — and because it attributes each
    problem to the exact line that carries it.

    Returns a list of human-readable problems (empty ⇒ clean). Each problem introduced by a
    commented line says so, because "it is in a comment" is the fact that made this class
    invisible for a whole tranche.
    """
    problems = list(_static_problems(source))
    live = set(problems)
    for commented in commented_code_lines(source):
        for problem in _static_problems(uncommented_source(source, commented)):
            if problem in live:
                continue  # already reported against the live source
            problems.append(f"in the commented-out {commented} → {problem}")
    return problems


# --------------------------------------------------------------------------- #
# The offline double pool — DEFINED in ``tests/offline_doubles.py``, re-exported #
# here (LD-310).                                                                #
#                                                                               #
# The pool used to be lines 469-532 + 551-2829 of this file. It moved so that a  #
# recipe edit and a double edit stop being the same file; these explicit         #
# re-exports are the contract that kept all 30 importing modules BYTE-UNCHANGED  #
# — ``gr.stage``, ``gr.OfflineBaseReadClient``, ``gr.markdown_calls`` and every  #
# private fixture constant still resolve through this module, exactly as before. #
# Explicit names (never ``import *``) so what this shim promises is readable in  #
# one place. Same pattern as ``src/larkdocio/write/model/`` and                  #
# ``src/larkdocio/sheets/requests/``.                                           #
# --------------------------------------------------------------------------- #
from offline_doubles import (  # noqa: E402,F401  (re-export shim — see above)
    _as_read_shape,
    _attachment_read_back,
    _AttrBag,
    _CopiedApp,
    _counting,
    _CreatedRecord,
    _DocumentMeta,
    _documents_for,
    _DOUBLE_KNOBS,
    _ENV_VARS,
    _FIXTURE_COMMENT_AUTHOR,
    _FIXTURE_COMMENT_ID,
    _FIXTURE_COMMENT_TEXT,
    _FIXTURE_MENTION_NAME,
    _FIXTURE_MENTION_NAMES,
    _FIXTURE_MENTION_NULL_NAMED,
    _FIXTURE_MENTION_RESOLVED,
    _FIXTURE_MENTION_UNKNOWN,
    _FIXTURE_QUOTE,
    _FIXTURE_TITLE,
    _MARKDOWN_CALLS,
    _offline_field_property,
    _offline_view_property,
    _OfflineBatchGet,
    _OfflineFilterCondition,
    _OfflineView,
    _reset_markdown_calls,
    _WikiNode,
    captured_export_workbook,
    DOUBLE_PAIRS,
    double_signature_mismatches,
    fixture_block_dicts,
    MARKDOWN_CALL_SITES,
    markdown_calls,
    OfflineBaseMediaClient,
    OfflineBaseReadClient,
    OfflineBaseSchemaClient,
    OfflineBaseWriteClient,
    OfflineCommentsReadClient,
    OfflineContactsSearchClient,
    OfflineDocument,
    OfflineDocuments,
    OfflineDocxReadClient,
    OfflineDriveAccessWriteClient,
    OfflineDriveFilesWriteClient,
    OfflineDriveFoldersWriteClient,
    OfflineDriveClient,
    OfflineDriveVersionsWriteClient,
    OfflineFloatImageMediaClient,
    OfflineSheetsExportReader,
    OfflineSheetsMediaClient,
    OfflineSheetsReadClient,
    OfflineSheetsWriteClient,
    OfflineStage,
    OfflineWriteClient,
    REAL_INIT_ENV,
    stage,
)


# --------------------------------------------------------------------------- #
# 3. Execution — builtins-only namespace, network boundary replaced.            #
# --------------------------------------------------------------------------- #

def run_source(src: str, origin: str) -> dict:
    """``exec`` ``src`` in a **builtins-only** namespace; return the namespace (LD-445).

    The one place a recipe block is executed. Nothing is pre-seeded — a name the block does
    not bind is a ``NameError`` here exactly as it is in a consumer's terminal.
    """
    ns = {"__builtins__": builtins,
          "__name__": "guide_recipe_" + re.sub(r"\W+", "_", origin)}
    exec(compile(src, f"<guide recipe: {origin}>", "exec"), ns)
    return ns


def run_recipe(slug: str, *, source: Optional[str] = None) -> dict:
    """``exec`` recipe ``slug``'s FIRST python block; return its namespace.

    ``source`` overrides the extracted text (used by the mutation probes that prove the
    harness bites — e.g. running the recipe with its ``init_env`` line deleted).
    """
    src = recipe_source(slug) if source is None else source
    return run_source(src, slug)


@contextlib.contextmanager
def _scratch_cwd(enabled: bool):
    """Run inside a throwaway cwd when the recipe persists an artefact (LD-445).

    A recipe that writes a file must not write it into the repository, and under ``-n auto``
    two workers running the same recipe must not share the name. **LD-430's guarantee is
    carried over rather than dropped**: the scratch directory is checked for a bootstrapped
    ``.env`` on the way out, which is exactly what the outer ``empty cwd`` test asserts for
    every recipe that does not move.
    """
    if not enabled:
        yield None
        return
    previous = os.getcwd()
    with tempfile.TemporaryDirectory(prefix="larkdocio-recipe-") as scratch:
        os.chdir(scratch)
        try:
            yield scratch
        finally:
            os.chdir(previous)
            assert not os.path.exists(os.path.join(scratch, ".env")), (
                "a recipe run bootstrapped a .env into its scratch cwd — the shipped "
                "init_env ran unpatched somewhere in the chain (LD-430)")


def run_and_check(spec, monkeypatch, tmp_path) -> List[dict]:
    """Stage, execute **every** python block of ``spec``'s recipe, and check each one.

    Each block runs against a **freshly installed stage** and in a namespace of **its own**,
    sharing nothing but the filesystem — so a recipe whose second half claims to resume in a
    later process has that claim executed rather than printed, and block *n+1* meets the
    document as a consumer's later process would (not as block *n* left it). Returns the
    namespaces, in document order.
    """
    checks = (spec.check,) + tuple(spec.extra_checks)
    sources = recipe_sources(spec.slug)
    assert len(sources) == len(checks), (
        f"recipe {spec.slug!r} carries {len(sources)} python blocks but {len(checks)} "
        "post-conditions; every block is executed AND checked, or the guard is a fiction")
    namespaces = []
    with _scratch_cwd(spec.persists_to_disk):
        for n, (src, check) in enumerate(zip(sources, checks), start=1):
            stage(monkeypatch, tmp_path, empty_document=spec.empty_document,
                  base_links=spec.base_links)
            _reset_markdown_calls()      # per-block counts, never accumulated across blocks
            ns = run_source(src, f"{spec.slug}#{n}")
            check(ns)
            namespaces.append(ns)
    return namespaces




# --------------------------------------------------------------------------- #
# 4. Per-recipe post-conditions — what each recipe must have PRODUCED.           #
# --------------------------------------------------------------------------- #

def _check_docx_read(ns):
    assert isinstance(ns["markdown"], str) and ns["markdown"].strip()
    assert "# Overview" in ns["markdown"], ns["markdown"]
    assert _FIXTURE_QUOTE in ns["markdown"], ns["markdown"]


def _check_docx_read_single_call(ns):
    """LD-599 — the recipe's SECOND block: the single-document read door, EXECUTED.

    ``read_child_markdown`` shipped in ``drive.__all__`` and the guide named it zero times
    while naming ``read_folder`` seventeen; the pointer that fixes that is only worth having
    if it is the *working* call, so the same fixtures the manual pipeline above is checked
    against are demanded of it here. A rename or a signature change reddens rather than
    leaving the guide teaching a call that no longer exists.
    """
    assert isinstance(ns["markdown"], str) and ns["markdown"].strip()
    assert "# Overview" in ns["markdown"], ns["markdown"]
    assert _FIXTURE_QUOTE in ns["markdown"], ns["markdown"]


def _check_sheet_read(ns):
    md = ns["markdown"]
    assert "| Name | Qty |" in md, md
    assert "| Widget | 3 |" in md, md

    # LD-472 — the ONE CALL is now at the obviously-named door, and it is EXECUTED here
    # rather than merely named: the recipe's step (0) must really render the workbook, or the
    # "stop here" the prose offers is an untested promise. It was buried in the ghost-tabs
    # recipe until 1.35, which is why this door taught the hand-rolled loop instead.
    assert "| Name | Qty |" in ns["whole_workbook"], ns["whole_workbook"]
    assert ns["whole_workbook"].strip(), "read_spreadsheet_markdown rendered nothing"

    # The filter disclosure ran for real (the staged tab carries a filter hiding row 2):
    # the note is in the output, naming the hidden row...
    assert "Filter active on this tab" in md, md
    assert "spreadsheet row 2" in md, md
    # ...and the hidden row is STILL RENDERED. Both halves matter: the note without the row
    # would mean the recipe quietly started filtering, and the row without the note is the
    # silent-fidelity defect the disclosure exists to end.
    assert "| Widget | 3 |" in md, md
    assert ns["hidden_rows"] == (2,), ns["hidden_rows"]
    assert ns["matrix_offsets"] == (1,), ns["matrix_offsets"]


def _check_ghost_tabs_walk(ns):
    """LD-407 — the walk's own heading: the one-call entry point plus the skip-on-refusal
    disclosure, checked at the exact keys a burned consumer reaches for (``book.skips``,
    ``book.skipped_any``). The fixture carries no ghost tab, so a clean walk (empty
    ``missed``, ``skipped_any is False``) is the correct offline answer — proving the code
    RUNS is what the harness is for; the skip behavior itself is unit-tested against
    ``SpreadsheetReadClient`` directly."""
    md = ns["markdown"]
    assert "| Name | Qty |" in md, md
    assert "| Widget | 3 |" in md, md
    assert ns["book"].skipped_any is False, ns["book"]
    assert ns["missed"] == [], ns["missed"]
    assert ns["skipped_any"] is False, ns["skipped_any"]


def _check_fidelity_read(ns):
    """LD-152 (F17+F19+F3): the standalone L2 fidelity read ran end to end — export leg,
    real stdlib parse, the title→``sheet_id`` join, and a render that **differs** from the
    values-only one.

    Asserting a *difference* is the point: the seat session's fidelity attempt produced
    byte-identical output, which is exactly what a wrong (or missing) join looks like. And
    the styles come from the shipped ``parse_xlsx`` over captured workbook bytes, never from
    a hand-built ``ExportedSheet`` — so the recipe proves the real leg, not a stub."""
    from larkdocio.sheets.export_reader import ExportedSheet, ParsedWorkbook

    workbook = ns["workbook"]
    assert isinstance(workbook, ParsedWorkbook) and workbook.sheets, workbook

    fidelity = ns["fidelity"]
    assert list(fidelity) == ["3bf016"], (
        f"the join must key the export by sheet_id, not title: {fidelity!r}")
    exported = fidelity["3bf016"]
    assert isinstance(exported, ExportedSheet)
    assert exported.name == "Sheet1", exported.name
    assert exported.cell("A1").bold is True, (
        "the shipped stdlib parser did not read the captured workbook's style")

    assert exported.cell("B2").fill_rgb == "FFFFFF00", (
        "the shipped stdlib parser did not read the captured workbook's cell FILL")

    markdown, plain = ns["markdown"], ns["plain"]
    assert "| **Name** | **Qty** |" in markdown, markdown
    assert "| Name | Qty |" in plain, plain
    assert markdown != plain, (
        "the fidelity render is byte-identical to the values-only one — the join did not "
        "reach the renderer")

    # LD-331 — the fill reaches BOTH seams the recipe now teaches: the reading form (the
    # disclosure note, so a colour-encoded sheet is recoverable from the Markdown) and the
    # structured one (`cell_fills`, the same facts for a program). The values-only render
    # states neither, which is the whole friction this closed.
    assert "FFFFFF00 — B2" in markdown, markdown
    assert "FFFFFF00" not in plain, plain
    assert ns["fills"] == {"B2": "FFFFFF00"}, ns["fills"]


def _check_docx_write(ns):
    from larkdocio.model import Node
    from larkdocio.write import Plan

    assert isinstance(ns["root"], Node), "the recipe must produce a parsed node TREE"
    assert isinstance(ns["plan"], Plan)
    (entry,) = ns["plan"].entries
    assert entry.block_id == "p1", f"the anchor did not resolve: {entry.to_dict()}"
    log = ns["log"]
    assert log.entries and all(e.to_dict()["outcome"] == "applied" for e in log.entries), (
        [e.to_dict() for e in log.entries])


def _check_docx_write_empty(ns):
    from larkdocio.write import Plan

    assert isinstance(ns["plan"], Plan)
    (entry,) = ns["plan"].entries
    d = entry.to_dict()
    assert d["outcome"] == "resolved", d
    assert d["position"] == "append-into", d
    # the insertion target is the PAGE node — whose block_id IS the document token.
    assert d["insertion_point"]["parent_block_id"] == ns["doc_token"], d
    assert d["insertion_point"]["index"] == 0, d
    log = ns["log"]
    assert [e.to_dict()["outcome"] for e in log.entries] == ["inserted"], (
        [e.to_dict() for e in log.entries])


def _check_put_image_in_document(ns):
    """LD-433: the recipe really did the three calls, in the measured order, and the verdict
    it reports is the **read-back** rather than any call's own answer.

    Asserted on what the recipe *produced*: the created block is a type-27 image block, the
    upload was parented on **that block id** (never the document), the block in the shared
    offline document now carries the uploaded token, the round trip was hash-verified, and
    the residue ledger holds exactly the one token a live run would have left permanently.
    """
    from larkdocio.write.media import IMAGE_BLOCK_TYPE
    from offline_doubles import OfflineDocxMediaClient

    authored = ns["authored"]
    assert authored.block_id and authored.file_token
    assert authored.bytes_verified is True
    assert authored.size == len(ns["image_bytes"])

    writer = ns["writer"]
    (parent, children, _index), = writer.created
    assert [c["block_type"] for c in children] == [IMAGE_BLOCK_TYPE], children
    # LD-508 — THE RECIPE NO LONGER PASSES width/height, and that is the assertion. The create
    # accepted them and the bind overwrote them (authored 560x560 read back 2560x2560,
    # consumer-observed on one day; authored 120x60 read back 1x1 on a 1x1 PNG, captured
    # 2026-08-19), so a recipe that passed them taught a caller something untrue. The empty
    # property is itself a measured create shape, and the recipe says why in place. The
    # earlier form of this line pinned {"width": 24, "height": 24}; the reason it existed —
    # the recipe's create payload is what it claims to be — is unchanged.
    assert children[0]["image"] == {}, children

    # the upload is bound to the CREATED BLOCK, never to the document
    uploads = [c for c in OfflineDocxMediaClient.calls if c[0] == "upload"]
    assert len(uploads) == 1, OfflineDocxMediaClient.calls
    _op, _name, parent_type, parent_node = uploads[0]
    assert parent_type == "docx_image"
    assert parent_node == authored.block_id
    assert parent_node != ns["doc_token"] and parent_node != parent

    # the bind is the PATCH, and the read-back is what proves it
    assert writer.patches == [
        (authored.block_id, {"replace_image": {"token": authored.file_token}})], writer.patches
    block = writer.get_block(ns["doc_token"], authored.block_id)
    assert block["image"]["token"] == authored.file_token, block

    # …and the round trip really downloaded the bytes again
    assert ("download", authored.file_token) in OfflineDocxMediaClient.calls

    # the permanent residue, ledgered — one token, attached to the image block
    assert OfflineDocxMediaClient.minted == [
        (authored.file_token, "docx_image", authored.block_id)]

    # LD-470 — PLACEMENT. The recipe asks for index=1 and then proves it by re-reading the
    # PARENT'S OWN children list, which is the only thing that can say where a block went: a
    # create answers the block it made, never the order it was made into.
    assert _index == 1, writer.created
    assert parent == ns["doc_token"], writer.created
    root = writer.get_block(ns["doc_token"], ns["doc_token"])
    assert list(root["children"]).index(authored.block_id) == 1, root["children"]
    assert ns["landed_at"] == 1


def _check_an_image_into_a_table_cell(ns):
    """LD-509 — the SECOND block of the image recipe: a table cell really is a legal
    ``parent_block_id``, and the id it used came from ``apply()`` rather than from a guess.

    Asserted on what the recipe produced, because both halves of the claim are falsifiable
    here: the id the recipe put in ``parent_block_id`` is one of the TABLE BLOCK'S OWN
    children (so it is a cell, reached from ``created_block_ids`` + one ``get_block``), and
    the image block reads back with that cell as its ``parent_id``. A recipe that took "the
    last table in the document" would still land an image somewhere and would still print a
    parent — which is exactly why the assertion is against the table this run created.
    """
    from larkdocio.write.media import IMAGE_BLOCK_TYPE

    table_block_id = ns["table_block_id"]
    cells = ns["cells"]
    cell_id = ns["image_cell_id"]
    writer = ns["writer"]

    # the id came from apply(), and it is the TABLE's — the cells are its own children.
    assert ns["log"].entries[0].created_block_ids == (table_block_id,), ns["log"].entries[0]
    assert list(writer.get_block(ns["doc_token"], table_block_id)["children"]) == cells
    assert cell_id in cells and cell_id == cells[3], (cell_id, cells)

    # the image is a real image block, its bytes round-tripped, and its PARENT is the cell.
    shot = ns["shot"]
    assert shot.bytes_verified is True
    landed = ns["landed"]
    assert landed["block_type"] == IMAGE_BLOCK_TYPE, landed
    assert landed["parent_id"] == cell_id, landed
    assert landed["image"]["token"] == shot.file_token, landed


def _check_idempotent_repair(ns):
    """LD-509 — the repair CONVERGES, and the second pass proves it rather than claiming it.

    Four things, each a claim the shipped text makes:

    * the first pass built deletes only for the obsolete blocks the document **still had**
      (the interrupted run had already taken one, so two of three);
    * every one of them applied — there is no ``stale-anchor`` here, because a request for an
      absent block was never built;
    * the second pass built **zero** requests and sent **nothing** — idempotence, measured on
      the double's own call record rather than on the recipe's print;
    * the document really no longer carries any of the obsolete text.
    """
    assert len(ns["first_requests"]) == 2, ns["first_requests"]
    assert [entry.outcome for entry in ns["first_log"].entries] == ["deleted"] * 2, (
        [entry.outcome for entry in ns["first_log"].entries])
    assert ns["first_log"].refusals == (), ns["first_log"].refusals

    assert ns["second_requests"] == [] and ns["second_log"] is None
    assert ns["still_present"](ns["read_document"]()[1]) == {}

    document = OfflineWriteClient.documents.for_token(ns["doc_token"])
    remaining = [document.text_of(block["block_id"]) for block in document.block_dicts()]
    assert not [text for text in remaining if any(f in text for f in ns["OBSOLETE"])], remaining


def _check_put_file_in_document(ns):
    """LD-470: the ATTACHMENT recipe — two blocks, the right one bound, the other one placed.

    Asserted on what the recipe *produced*, and each assertion is a claim the shipped text
    makes: the create really answered a **type-33 wrapper** whose child is the **type-23** file
    block; the upload was parented on the **child**, never the wrapper and never the document;
    the child reads back carrying the uploaded token; and the block that occupies the position
    the caller asked for is the **wrapper**, not the id the caller was handed.
    """
    from larkdocio.write.media import (
        FILE_BLOCK_TYPE,
        FILE_VIEW_WRAPPER_BLOCK_TYPE,
    )
    from offline_doubles import OfflineDocxMediaClient

    attached = ns["attached"]
    assert attached.block_id and attached.wrapper_block_id
    assert attached.block_id != attached.wrapper_block_id, (
        "the whole trap is that these are two different blocks")
    assert attached.bytes_verified is True
    assert attached.size == len(ns["file_bytes"])

    writer = ns["writer"]
    (parent, children, index), = writer.created
    assert [c["block_type"] for c in children] == [FILE_BLOCK_TYPE], children
    assert children[0]["file"] == {}, (
        "a create carrying a name in the file property is REFUSED — the name rides the upload")
    assert (parent, index) == (ns["doc_token"], 0), writer.created

    # the two blocks, each typed from the document the recipe actually wrote into
    wrapper = writer.get_block(ns["doc_token"], attached.wrapper_block_id)
    child = writer.get_block(ns["doc_token"], attached.block_id)
    assert wrapper["block_type"] == FILE_VIEW_WRAPPER_BLOCK_TYPE, wrapper
    assert child["block_type"] == FILE_BLOCK_TYPE, child
    assert list(wrapper["children"]) == [attached.block_id], wrapper

    # the upload is bound to the CHILD — never the wrapper, never the document
    uploads = [c for c in OfflineDocxMediaClient.calls if c[0] == "upload"]
    assert len(uploads) == 1, OfflineDocxMediaClient.calls
    _op, _name, parent_type, parent_node = uploads[0]
    assert parent_type == "docx_file"
    assert parent_node == attached.block_id
    assert parent_node not in (attached.wrapper_block_id, ns["doc_token"])

    # the bind is the PATCH on the child, and the read-back is what proves it
    assert writer.patches == [
        (attached.block_id, {"replace_file": {"token": attached.file_token}})], writer.patches
    assert child["file"]["token"] == attached.file_token, child

    # PLACEMENT — and the twist the shipped text states: what sits at the position asked for
    # is the WRAPPER, while the id the caller holds is one level deeper.
    root = writer.get_block(ns["doc_token"], ns["doc_token"])
    assert list(root["children"]).index(attached.wrapper_block_id) == 0, root["children"]
    assert attached.block_id not in list(root["children"])

    # the permanent residue, ledgered — one token, attached to the FILE block
    assert OfflineDocxMediaClient.minted == [
        (attached.file_token, "docx_file", attached.block_id)]


def _check_put_image_in_sheet(ns):
    """LD-447: the recipe really wrote the picture as the CELL'S VALUE, in one call, and the
    verdict it reports is the fresh read-back rather than the write's own answer.

    Asserted on what the recipe *produced*: the cell now holds an ``embed-image`` value
    carrying the token, the token was minted by the WRITE (nothing was uploaded — the media
    double's upload leg was never called), the round trip was hash-verified, the residue
    ledger holds exactly the one permanent token a live run would have left, and the clear
    really is an ordinary ``""`` value write.
    """
    written = ns["written"]
    assert written.file_token and written.bytes_verified is True
    assert written.size == len(ns["image_bytes"])
    assert written.range and written.revision is not None

    client = ns["write_client"]
    # ONE call carried the bytes: there is no upload leg on this route, and the double would
    # have recorded one. The only media call is the DOWNLOAD the opt-in verification made.
    assert [c[0] for c in OfflineSheetsMediaClient.calls] == ["download"], (
        OfflineSheetsMediaClient.calls)
    assert ("download", written.file_token) in OfflineSheetsMediaClient.calls

    # the permanent residue, ledgered — and minted BY THE WRITE, parented on the workbook
    assert OfflineSheetsMediaClient.minted == [
        (written.file_token, "values_image", ns["spreadsheet_token"])]

    # the cell really holds a picture now — read back through the shipped client
    after_write = ns["written"].file_token
    value_range = client.read_value_range(ns["spreadsheet_token"], ns["target"])
    cleared = value_range["values"][0][0]
    # ...and by the end of the recipe the CLEAR has run, so the cell is the empty string.
    assert cleared == "", value_range
    assert (ns["target"], [[""]]) in client.puts, client.puts
    assert after_write not in ("", None)


def _check_put_float_image_in_sheet(ns):
    """LD-448: the recipe really floated a picture over the range, in three beats, and every
    verdict it reports came from a **fresh query** rather than a call's own answer.

    Asserted on what the recipe *produced*: the upload was parented on the WORKBOOK (not the
    tab and not the cell), the tab lists the float image at the anchor, the round trip was
    hash-verified, the removal is proven by the query rather than by the delete, and the
    permanent media token is still ledgered afterwards — because removing a float image does
    not remove the bytes.
    """
    floated = ns["floated"]
    assert floated.float_image_id and floated.bytes_verified is True
    assert floated.a1_range == ns["anchor"]
    assert floated.size == len(ns["image_bytes"])

    # BEAT 1, and THE TRAP: the upload's parent_node is the spreadsheet token — never the
    # sheet_id, never the anchor cell. The double records what was actually sent.
    uploads = [c for c in OfflineFloatImageMediaClient.calls if c[0] == "upload"]
    # TWO uploads, and the second one is the point: step (d)'s refused multi-cell bind
    # uploaded first and was refused second (LD-472). Both parented on the WORKBOOK.
    assert len(uploads) == 2, OfflineFloatImageMediaClient.calls
    assert all(c[2] == "sheet_image" and c[3] == ns["spreadsheet_token"] for c in uploads)
    _, _, parent_type, parent_node = uploads[0]
    assert parent_type == "sheet_image"
    assert parent_node == ns["spreadsheet_token"]
    assert parent_node != ns["sheet_id"]

    # the permanent residue, ledgered — TWO tokens now: the bound one, and the ORPHAN the
    # refused multi-cell bind in step (d) left behind (LD-472). The second entry is the whole
    # point of that step: the upload precedes bind validation, so a refusal still costs bytes.
    assert OfflineFloatImageMediaClient.minted == [
        (floated.float_image_token, "sheet_image", ns["spreadsheet_token"]),
        (ns["orphan_token"], "sheet_image", ns["spreadsheet_token"])]
    assert ("download", floated.float_image_token) in OfflineFloatImageMediaClient.calls

    # LD-472 — THE RANGE REFUTATION, executed rather than recited: a multi-cell a1_range is
    # refused 1310202, nothing is bound, and the orphan token is real and still resolvable
    # (there is no purge verb, which is the finding).
    assert ns["orphan_token"], "the refused bind did not carry an orphan_file_token"
    assert ns["orphan_token"] != floated.float_image_token
    assert ns["orphan_token"] in OfflineFloatImageMediaClient.store, (
        "the orphan token stopped resolving — that would model a purge that does not exist")

    # (b) the tab really listed it, and (c) the removal really removed it — both read off
    # the shipped client rather than off the recipe's own prints.
    assert ns["listed"] and ns["listed"][0]["float_image_id"] == floated.float_image_id
    assert floated.float_image_id not in ns["remaining"]
    client = ns["write_client"]
    assert client.query_float_images(ns["spreadsheet_token"], ns["sheet_id"]) == []

    # ...and THE BYTES ARE STILL THERE. Removing the anchor does not purge drive media, and
    # a double that quietly dropped the token would model a purge that does not exist.
    assert floated.float_image_token in OfflineFloatImageMediaClient.store


def _check_link_a_file_from_a_sentence(ns):
    """LD-434: the recipe really uploaded a file into the CALLER'S folder, really asked Lark
    for the address, and really authored a run whose anchor text is not the URL.

    Asserted on what the recipe *produced*, never on its text. The permalink is checked to be
    the one the transport SERVED (the double's), which is what proves the shipped code asked
    rather than assembled; the authored block is read back out of the shared offline document
    and its second run must carry the link on ``text_element_style``.
    """
    linked = ns["linked"]
    assert linked.bytes_verified is True
    assert linked.url_class == "permalink"

    # the upload went to the CALLER's folder, on the one measured parent_type
    uploads = [c for c in OfflineDriveFilesWriteClient.calls if c[0] == "upload"]
    assert len(uploads) == 1, OfflineDriveFilesWriteClient.calls
    _op, _name, parent_type, folder = uploads[0]
    assert parent_type == "explorer"
    assert folder == ns["folder_token"] != ns["doc_token"]

    # the URL was ASKED FOR — and it is the transport's, not one the library spelled
    assert ("permalink", linked.file_token) in OfflineDriveFilesWriteClient.calls
    assert linked.url == f"{OfflineDriveFilesWriteClient.host}/file/{linked.file_token}"

    # …and the round trip really downloaded the bytes again
    assert ("download", linked.file_token) in OfflineDriveFilesWriteClient.calls

    # THE SENTENCE: read the authored block back out of the document the recipe wrote to.
    document = OfflineWriteClient.documents.for_token(ns["doc_token"])
    block = document.get(ns["sentence_block_id"])
    elements = (block.get("text") or {}).get("elements") or []
    assert [e["text_run"]["content"] for e in elements] == [
        "For the full details, ", "open the attached file"], elements
    assert "text_element_style" not in elements[0]["text_run"], elements[0]
    assert elements[1]["text_run"]["text_element_style"] == {
        "link": {"url": linked.url}}, elements[1]

    # LD-619 — THE SAME ANCHOR IN A TABLE CELL. Read the created table's cells back out of
    # the same document: the third cell of row 1 must carry the link on its inner run, and
    # the two plain cells beside it must carry no style at all.
    table = document.get(ns["metrics_block_id"])
    inner_runs = []
    for cell_id in table["children"]:
        cell = document.get(cell_id)
        inner = document.get((cell.get("children") or [None])[0])
        inner_runs.append(((inner.get("text") or {}).get("elements") or [{}])[0]
                          .get("text_run", {}))
    contents = [run.get("content") for run in inner_runs]
    assert contents == ["Metric", "Owner", "Detail",
                        "On-time delivery", "Logistics", "Method note"], contents
    assert inner_runs[5]["text_element_style"] == {"link": {"url": linked.url}}, inner_runs[5]
    assert [run for run in inner_runs[:5] if "text_element_style" in run] == []


def _check_the_by_name_lookup_before_uploading(ns):
    """LD-464: the recipe really ASKED the folder what is already in it, before uploading.

    Asserted on what the block produced rather than on its text: the listing reached the
    caller's own folder token, the answer knows it is complete (so ``found is False`` is a
    real absence rather than a truncated one), and its sentence says so. The double serves a
    fixed two-child folder holding neither name, which is the *skip nothing, proceed* arm —
    and the point of the block is that a caller can tell the two arms apart at all.
    """
    already = ns["already"]
    assert already.folder_token == ns["folder_token"]
    assert ("list", ns["folder_token"]) in OfflineDriveClient.calls, (
        "the lookup must have LISTED the folder, not answered from thin air")
    assert already.listed == 2, already
    assert already.found is False and already.tokens == ()
    assert already.complete is True, "a truncated listing must never read as an absence"
    assert "no child" in already.describe() and "no size or digest" in already.describe()


def _check_anchor_by_id(ns):
    """LD-137: the recipe really ran the consumer loop — created ids, then anchored by one.

    Every assertion is on what the recipe *produced*, not on its text: ``apply`` handed back
    real created ids, the follow-up plan resolved **the created id** through an
    :class:`~larkdocio.write.model.AnchorById` (with the by-id staleness precondition
    captured), it applied with zero refusals, and the block the recipe patched is the one it
    created — with its text actually changed in the shared offline document.
    """
    from larkdocio.write import AnchorById, Plan

    created = ns["created_block_ids"]
    assert len(created) == 2 and all(created), (
        f"apply() must hand back one id per authored block: {created!r}")
    assert ns["paragraph_id"] == created[1], (created, ns["paragraph_id"])

    plan = ns["plan"]
    assert isinstance(plan, Plan)
    (entry,) = plan.entries
    assert entry.is_resolved, entry.to_dict()
    assert entry.anchor == AnchorById(block_id=ns["paragraph_id"]), entry.to_dict()
    assert entry.block_id == ns["paragraph_id"], (
        "the by-id anchor did not resolve to the block the recipe created")
    assert entry.precondition_text == "Drafted by the agent.", entry.to_dict()

    log = ns["follow_up_log"]
    assert [e.to_dict()["outcome"] for e in log.entries] == ["applied"], (
        [e.to_dict() for e in log.entries])
    assert log.entries[0].block_id == ns["paragraph_id"]

    document = OfflineWriteClient.documents.for_token(ns["doc_token"])
    assert document.text_of(ns["paragraph_id"]) == (
        "Drafted by the agent, then revised by id."), (
        "the id-anchored edit did not land on the created block")


def _check_authoring(ns):
    """LD-138: the authoring recipe really compiled Markdown → typed content → a landed
    document, and it teaches the **whole** creatable floor while doing it.

    Every assertion is on what the recipe *produced*: the fragment composed to one block per
    creatable kind (pinned against the closed enum, so a kind added later without updating
    the recipe reddens), the plan resolved on the reference block, ``apply`` created a block
    per authored block, **the table's cells really carry their authored text** (the LD-135
    two-step create running for real, not a payload stored and forgotten), the id-anchored
    follow-up landed, and the shipped **reader** renders the authored structure back —
    heading, nested list, todo, table row, fenced code, quote and the escaped metacharacter.
    """
    import harness  # tests/ is on sys.path (conftest)
    from larkdocio.model import Node
    from larkdocio.write import Plan
    from larkdocio.write.model import NewBlockKind

    content = ns["content"]
    assert {b.kind for b in content} == set(NewBlockKind), (
        "the authoring recipe must demonstrate EVERY creatable kind; it composes "
        f"{sorted(b.kind.value for b in content)} out of "
        f"{sorted(k.value for k in NewBlockKind)}"
    )
    assert isinstance(ns["root"], Node), "the recipe must produce a parsed node TREE"

    plan = ns["plan"]
    assert isinstance(plan, Plan)
    (entry,) = plan.entries
    assert entry.is_resolved and entry.block_id == "p1", entry.to_dict()

    log = ns["log"]
    assert [e.to_dict()["outcome"] for e in log.entries] == ["inserted"], (
        [e.to_dict() for e in log.entries])
    created = ns["created_block_ids"]
    assert len(created) >= len(content) and all(created), created

    document = OfflineWriteClient.documents.for_token(ns["doc_token"])
    tables = [b for b in document.blocks.values() if b.get("block_type") == 31]
    assert len(tables) == 1, "the authored table did not land"
    cell_texts = [
        document.text_of(inner)
        for cell in tables[0]["children"]
        for inner in document.blocks[cell]["children"]
    ]
    assert "On-time delivery" in cell_texts and "97.2%" in cell_texts, cell_texts

    follow_up_log = ns["follow_up_log"]
    assert [e.to_dict()["outcome"] for e in follow_up_log.entries] == ["inserted"], (
        [e.to_dict() for e in follow_up_log.entries])

    markdown = harness.render(document.block_dicts(), doc_id=ns["doc_token"])
    for landed in (
        "## Findings",                                   # heading
        "- the week-3 dip recovered by Friday",          # bullet
        "\t- root cause: a stuck approval queue",        # its NESTED child (tab-indented)
        "- [ ] send the summary to the board",           # todo
        "1. confirm the number with finance",            # ordered
        "| On-time delivery | 97.2% |",                  # the table's authored cells
        "```python",                                     # code, with its language
        "> Quoting the brief",                           # quote
        "\\# An escaped metacharacter",                  # the escape survived authoring
    ):
        assert landed in markdown, (
            f"the authored fragment does not read back: {landed!r} missing from\n{markdown}")


def _check_batched_authoring(ns):
    """LD-469: the fragment really was split, chained and landed IN ORDER.

    Every assertion is on what the recipe *produced*. The split is more than one batch (a
    recipe that fitted in one call would teach nothing), each batch is within the shipped cap,
    the chain anchored batch n+1 to a block batch n created — by id, and to the last TOP-LEVEL
    one — and the shipped reader renders the sections back in the authored order, which is the
    one thing the apply-logs cannot say.
    """
    import harness  # tests/ is on sys.path (conftest)
    from larkdocio.write.model import MAX_CHILDREN_PER_CALL

    batches, titles = ns["batches"], ns["TITLES"]
    assert len(batches) > 1, (
        "the recipe's fragment fitted in one call, so it demonstrates no batching at all")
    assert all(len(batch) <= MAX_CHILDREN_PER_CALL for batch in batches), (
        [len(batch) for batch in batches])
    assert sum(len(batch) for batch in batches) == len(ns["content"])

    created = ns["created_block_ids"]
    assert len(created) == len(ns["content"]) and all(created), created
    # The chain: the last reference is an id this run created, not a quote of its own text.
    assert ns["reference"].block_id in created, (
        "the final batch did not anchor by an id the previous batch created")

    # THE ORDER, off the DOCUMENT rather than off the logs — the recipe's own assertion, made
    # again here against the shipped reader so a deleted assert in the recipe cannot hide it.
    document = OfflineWriteClient.documents.for_token(ns["doc_token"])
    markdown = harness.render(document.block_dicts(), doc_id=ns["doc_token"])
    positions = [markdown.index(f"## {title}") for title in titles]
    assert positions == sorted(positions), (
        "the batched fragment did not land in the authored order")


def _check_sheets_write(ns):
    from larkdocio.sheets.plan import Plan

    assert isinstance(ns["plan"], Plan)
    assert ns["sheet_id"] == "3bf016", (
        f"the recipe must obtain a real sheet_id from query_tabs; got {ns.get('sheet_id')!r}")
    (entry,) = ns["plan"].entries
    d = entry.to_dict()
    assert d["outcome"] == "resolved", d
    assert ns["log"].entries
    assert [e.to_dict()["outcome"] for e in ns["log"].entries] == ["applied"], (
        [e.to_dict() for e in ns["log"].entries])
    assert not ns["log"].refusals, [e.to_dict() for e in ns["log"].refusals]


def _check_formula_write(ns):
    """The LD-149 formula recipe: the trap is FLAGGED at dry-run, the fix WRITES the object
    form, and the computed value comes back verified (never inert)."""
    from larkdocio.sheets.formula import INERT_STRING_NOTE

    trap_note = ns["trap"].entries[0].preview_note
    assert trap_note["kind"] == "equals-prefixed-plain-string", trap_note
    assert trap_note["note"] == INERT_STRING_NOTE

    note = ns["note"]
    assert note["kind"] == "formula" and note["expression"] == "=SUM(B3:B8)"
    assert note["precondition_compares"] == "expression"

    entry = ns["entry"]
    assert entry.outcome == "applied", entry.to_dict()
    assert entry.write_kind == "formula"
    assert entry.formula["evaluated"] is True, entry.formula
    assert entry.formula["computed_value"] == 21, entry.formula
    assert ns["log"].formula_not_evaluated == ()
    # EXACTLY one write happened: the dry-runs (both of them) issued none, and the applied
    # formula went out as the object form — never as a bare "=..." string.
    assert ns["write_client"].puts == [
        (f"{ns['sheet_id']}!C1:C1", [[{"type": "formula", "text": "=SUM(B3:B8)"}]])]


def _check_structural_write(ns):
    """LD-152 (F1) — the structural recipe, verified on the **call shapes** it produced.

    Not "it ran": the injected transport records every dimension call, and the assertions pin
    the two opposite index conventions the request objects convert to (insert → a 0-indexed
    half-open span, delete → a 1-indexed inclusive one), the mandatory post-write geometry
    re-read agreeing with the previewed shift, and the destructive delete's removed payload —
    including the ``values_trim`` disclosure, which only appears because the double answers a
    removed-payload read the way the real values API does (the full declared width, pad
    included)."""
    calls = ns["write_client"].dimension_writes
    assert calls == [
        ("insert", "3bf016", "ROWS", 1),
        ("insert", "3bf016", "COLUMNS", 1),
        ("delete", "3bf016", "ROWS", 2),
    ], calls

    grow = ns["grow_log"]
    assert [e.to_dict()["outcome"] for e in grow.entries] == ["applied", "applied"], (
        [e.to_dict() for e in grow.entries])
    assert all(e.structural["shift_verified"] for e in grow.entries), (
        "the engine's post-write geometry re-read did not confirm the previewed shift")
    assert [e.structural["convention"] for e in grow.entries] == [
        "0-index-half-open", "0-index-half-open"], [e.structural for e in grow.entries]

    removed = ns["removed"]
    # 21 columns, not 20: batch 1's column insert really widened the tab, and the removed
    # range is derived from the geometry the previewer read at plan time.
    assert removed["a1_range"] == "3bf016!A2:U3", removed["a1_range"]
    assert removed["values"] == [["Widget", 3], ["Gadget", 5]], removed["values"]
    trim = removed["values_trim"]
    assert (trim["axis"], trim["declared"], trim["used"]) == ("COLUMNS", 21, 2), trim

    shrink = ns["shrink_log"]
    (entry,) = shrink.entries
    assert entry.to_dict()["outcome"] == "applied", entry.to_dict()
    assert entry.structural["convention"] == "1-index-inclusive", entry.structural
    assert entry.structural["reply_count"] == 2, entry.structural
    assert entry.structural["count_mismatch"] is False, entry.structural
    assert entry.structural["removed"]["values"] == removed["values"]

    # the out-of-bounds disclosure was previewed, and it was DRY-RUN ONLY (no fourth call).
    note = ns["out_of_bounds"]
    assert note["kind"] == "out-of-bounds-dimension", note
    assert note["wholly_out_of_bounds"] is True, note


def _check_dimension_property_write(ns):
    """The dimension-property recipe, verified on what it PRODUCED.

    The three things a reader of that recipe is being taught, each asserted rather than
    assumed: the band really goes out **1-indexed inclusive** (the opposite of the insert
    convention on the same endpoint), the hide is **disclosed** while the two size changes are
    **not**, and both the construction refusal (`fixed_size=0`) and the plan-time
    out-of-bounds refusal really fire — the second one having issued no write.
    """
    calls = ns["write_client"].dimension_writes
    assert calls == [
        ("dimension-property", "3bf016", "ROWS", (2, 3), {"fixedSize": 60}),
        ("dimension-property", "3bf016", "COLUMNS", (2, 2), {"fixedSize": 200}),
        ("dimension-property", "3bf016", "ROWS", (4, 4), {"visible": False}),
        ("dimension-property", "3bf016", "ROWS", (4, 4), {"visible": True}),
    ], calls

    plan = ns["plan"]
    assert [e.structural["convention"] for e in plan.entries] == ["1-index-inclusive"] * 3
    assert [[n["kind"] for n in e.preview_notes] for e in plan.entries] == [
        [], [], ["hidden-dimension-fidelity"]], (
        "the hide must be disclosed and a pure size change must not be")
    assert ns["hide_note"]["hidden_rows"] == [4], ns["hide_note"]

    log = ns["log"]
    assert [e.to_dict()["outcome"] for e in log.entries] == ["applied"] * 3
    assert log.entries[0].structural["verified_by"] == "xlsx-export-dimension-leg"
    assert ns["show_log"].entries[0].to_dict()["outcome"] == "applied"

    over = ns["over"]
    assert over.entries[0].refusal.reason == "out-of-bounds-dimension", over.entries[0].to_dict()
    # the refused band issued no write — the four calls above are the whole journal
    assert len(calls) == 4, calls


def _check_style_write(ns):
    """LD-188 — the style recipe, verified on what it PRODUCED.

    What that recipe teaches, each asserted rather than assumed: the single-range write puts the
    validated style dict on the wire with a `Start:End` range, the cost note really rides the
    plan (and names the export leg and the third scope), the number-format-only write is a legal
    write of its own, **N ranges really cost ONE call**, the out-of-range font size is refused
    before any call at all, and the unknown tab refuses at plan time having written nothing.
    """
    client = ns["write_client"]
    kinds = [w[0] for w in client.style_writes]
    assert kinds == ["put_style", "put_style", "batch_update_styles"], client.style_writes

    header = client.style_writes[0]
    assert header[1] == "3bf016!A1:C1", header
    assert header[2] == {"font": {"bold": True, "fontSize": "12pt/1.5"},
                         "backColor": "#D9EAD3"}, header
    assert client.style_writes[1][2] == {"formatter": "0.00%"}, client.style_writes[1]

    cost = ns["cost"]
    assert cost["kind"] == "style-verification-cost"
    assert (cost["verified_by"], cost["scope"]) == ("xlsx-export-style-leg", "drive:export")
    for phrase in ("~1.2 s", "~30 s", "drive:export"):
        assert phrase in cost["note"], cost["note"]

    log = ns["log"]
    assert [e.to_dict()["outcome"] for e in log.entries] == ["applied"]
    assert log.entries[0].structural["verified_by"] == "xlsx-export-style-leg"
    assert ns["percent"].entries[0].to_dict()["outcome"] == "applied"

    # THE batch claim: three ranges, one call, two styles.
    batch = client.style_writes[2]
    assert batch[1] == (("3bf016!A3:C3", "3bf016!A5:C5"), ("3bf016!A4:C4",)), batch
    assert batch[2] == ({"backColor": "#FFFF00"},
                        {"font": {"italic": True}, "foreColor": "#FF0000"}), batch
    assert len(ns["batch"].ranges) == 3
    assert ns["batch_log"].entries[0].to_dict()["outcome"] == "applied"

    unknown = ns["unknown"]
    assert unknown.entries[0].refusal.reason == "unknown-tab", unknown.entries[0].to_dict()
    # the refused plan issued no write — the three calls above are the whole journal
    assert len(client.style_writes) == 3, client.style_writes


def _check_freeze_panes_write(ns):
    """The freeze recipe, verified on what it PRODUCED.

    The four things that recipe teaches, each asserted rather than assumed: the wire really
    carries only the axes the caller named (the PATCH contract), the replacement of an existing
    freeze is really disclosed with both counts, the read-back really reflects the writes, and
    both refusals really fire — the plan-time one having issued no write.
    """
    client = ns["write_client"]
    assert client.freeze_writes == [
        ("3bf016", 1, 1),        # rows=1, cols=1 — one request, both axes
        ("3bf016", 2, None),     # rows=2 alone: the column axis is ABSENT from the wire
        ("3bf016", 0, 0),        # unfreeze BOTH axes
    ], client.freeze_writes

    log = ns["log"]
    assert [e.to_dict()["outcome"] for e in log.entries] == ["applied"]
    assert log.entries[0].structural["observed"] == {"frozen_rows": 1, "frozen_cols": 1}
    assert log.entries[0].structural["verified_by"] == "metainfo-frozen-leg"

    note = ns["note"]
    assert note["kind"] == "freeze-replaces-freeze"
    assert note["current"] == {"frozen_rows": 1, "frozen_cols": 1}
    assert note["target"] == {"frozen_rows": 2, "frozen_cols": 1}
    # the un-named column axis is PRESERVED, which is the trap the recipe exists to close
    assert note["preserved_axes"] == ["frozen_cols"], note

    frozen = ns["frozen"]
    assert (frozen["frozen_rows"], frozen["frozen_cols"]) == (2, 1), frozen
    assert frozen["source"] == "metainfo"

    unfroze = ns["unfroze"]
    assert unfroze.entries[0].structural["observed"] == {"frozen_rows": 0, "frozen_cols": 0}

    over = ns["over"]
    assert over.entries[0].refusal.reason == "frozen-count-out-of-range", (
        over.entries[0].to_dict())
    # the refused count issued no write — the three calls above are the whole journal
    assert len(client.freeze_writes) == 3, client.freeze_writes


def _check_tab_presentation_write(ns):
    """LD-187 — the tab-presentation recipe, verified on what it PRODUCED.

    What that recipe teaches, each asserted rather than assumed: the wire carries the three
    fields and nothing else, the reorder really lands at the position asked for, the retitle
    really discloses both titles while the sheet_id stands still, the hide really discloses
    that the data stays readable AND the values really do read back afterwards, hide/show
    round-trips, and both refusals fire — the plan-time one having issued no write.
    """
    client = ns["write_client"]
    sheet_id = ns["sheet_id"]
    assert client.presentation_writes == [
        (sheet_id, 0, None, None),          # (a) reorder to the front
        (sheet_id, None, "Q3 actuals", None),   # (b) retitle
        (sheet_id, None, None, True),       # (c) hide
        (sheet_id, None, None, False),      # ...and show again
    ], client.presentation_writes

    # every element on the wire is an `updateSheet` naming ONE field beside the sheetId
    elements = [e for e in client.tab_writes if "updateSheet" in e]
    assert len(elements) == 4, elements
    for element in elements:
        props = element["updateSheet"]["properties"]
        assert set(props) - {"sheetId"} <= {"index", "title", "hidden"}, props
        assert len(props) == 2, props

    log = ns["log"]
    assert [e.to_dict()["outcome"] for e in log.entries] == ["applied"]
    assert log.entries[0].structural["verified_by"] == "v3-tab-query-leg"
    assert log.entries[0].structural["observed"]["index"] == 0, (
        log.entries[0].structural["observed"])

    note = ns["note"]
    assert note["kind"] == "retitle-breaks-title-joins"
    assert note["new_title"] == "Q3 actuals" and note["old_title"] != note["new_title"]
    assert note["sheet_id_unchanged"] is True
    assert ns["retitle_log"].entries[0].structural["observed"]["title"] == "Q3 actuals"
    # the sheet_id really did NOT change — the claim the note makes
    assert any(t["sheet_id"] == sheet_id and t["title"] == "Q3 actuals"
               for t in client.query_tabs(ns["spreadsheet_token"]))

    hide_note = ns["hide_note"]
    assert hide_note["kind"] == "hidden-tab-fidelity" and hide_note["hidden"] is True
    assert ns["hide_log"].entries[0].structural["observed"]["hidden"] is True
    # …and the hidden tab really WAS read through the library while hidden — the recipe does
    # the read, so the claim in its disclosure is demonstrated rather than asserted
    assert isinstance(ns["hidden_values"], list), ns["hidden_values"]
    assert ns["show_log"].entries[0].structural["observed"]["hidden"] is False

    over = ns["over"]
    assert over.entries[0].refusal.reason == "tab-index-out-of-range", (
        over.entries[0].to_dict())
    # the refused reorder issued no write — the four writes above are the whole journal
    assert len(client.presentation_writes) == 4, client.presentation_writes


def _check_merge_write(ns):
    """LD-152 (F1) — merge/unmerge: the enumerated value loss, the geometry the merge leg
    re-reads, and the ``no-merge-at-range`` note for an unmerge that dissolves nothing."""
    calls = ns["write_client"].merge_writes
    assert calls == [
        ("merge", "3bf016!B1:C1", "MERGE_ALL"),
        ("unmerge", "3bf016!B1:C1"),
    ], calls

    loss = ns["loss"]
    assert loss["anchor"] == {"ref": "B1", "value": "Qty"}, loss
    assert loss["lost_values"] == [{"ref": "C1", "value": "Notes"}], loss
    assert loss["lost_count"] == 1, loss

    (merged,) = ns["merge_log"].entries
    assert merged.to_dict()["outcome"] == "applied", merged.to_dict()
    assert merged.structural["merges_added"] == [
        {"start_row_index": 0, "end_row_index": 0,
         "start_column_index": 1, "end_column_index": 2}], merged.structural

    (unmerged,) = ns["unmerge_log"].entries
    assert unmerged.to_dict()["outcome"] == "applied", unmerged.to_dict()
    assert unmerged.structural["merges_removed"] == merged.structural["merges_added"], (
        unmerged.structural)

    noop = ns["noop_note"]
    assert noop["kind"] == "no-merge-at-range", noop
    assert "dissolve NOTHING" in noop["note"], noop
    assert len(ns["write_client"].merge_writes) == 2, (
        "the no-op demonstration must be dry-run only — it must issue no third write")


def _check_rich_cell_write(ns):
    """LD-472 — the hyperlink + styled-runs recipe, verified on the WIRE SHAPES it produced.

    Not "it ran": the two capabilities were invisible for eight releases and the correction is
    only worth anything if the code a consumer pastes really writes the encoded cells. So the
    injected transport's ``puts`` are read back and pinned — the ``{"type": "url", …}`` object
    and the ``segmentStyle`` run array, each as a 1×1 matrix through the SAME ``put_values``
    seam a plain value uses — and the value precondition is asserted **enforced**, which is the
    one thing that distinguishes a rich cell from the dropdown rule beside it.
    """
    plan = ns["plan"]
    assert [e.value_precondition for e in plan.entries] == ["enforced", "enforced"], (
        [e.to_dict() for e in plan.entries])
    assert [e.to_dict()["outcome"] for e in plan.entries] == ["resolved", "resolved"], (
        [e.to_dict() for e in plan.entries])

    log = ns["log"]
    assert [e.to_dict()["outcome"] for e in log.entries] == ["applied", "applied"], (
        [e.to_dict() for e in log.entries])
    assert not log.refusals, [e.to_dict() for e in log.refusals]
    assert [e.write_kind for e in log.entries] == ["value", "value"], (
        "a rich cell writes through put_values — it is a request type of the value op")

    puts = ns["write_client"].puts
    assert puts == [
        ("3bf016!A1:A1", [[{"type": "url", "text": "Q4 plan",
                            "link": "https://example.com/q4-plan"}]]),
        ("3bf016!A2:A2", [[[
            {"type": "text", "text": "Blocked",
             "segmentStyle": {"bold": True, "foreColor": "#D93026"}},
            {"type": "text", "text": " — waiting on legal",
             "segmentStyle": {"italic": True}},
        ]]]),
    ], puts

    # The claim the prose makes about the label, read off the plan rather than restated.
    assert plan.entries[0].after == [[
        {"type": "url", "text": "Q4 plan", "link": "https://example.com/q4-plan"}]], (
        plan.entries[0].after)


def _check_dropdown_write(ns):
    """LD-152 (F1) — the dropdown rule: the encoded wire shape the recipe never
    hand-assembles, the ``data-validation`` seam (never ``put_values``), and the colors
    caveat refusing at BUILD time."""
    calls = ns["write_client"].validations
    assert len(calls) == 1, calls
    a1_range, rule = calls[0]
    assert a1_range == "3bf016!A6:A6", a1_range
    assert rule["dataValidationType"] == "list", rule
    assert rule["dataValidation"]["conditionValues"] == ["Draft", "In review", "Shipped"], rule
    assert rule["dataValidation"]["options"]["multipleValues"] is False, rule

    (entry,) = ns["log"].entries
    assert entry.to_dict()["outcome"] == "applied", entry.to_dict()
    assert entry.write_kind == "data-validation", entry.to_dict()
    assert ns["write_client"].puts == [], (
        "a rule is not a cell value — it must not go through put_values")

    assert ns["plan"].entries[0].value_precondition == "none", ns["plan"].entries[0].to_dict()
    assert "colors" in ns["colors_error"], ns["colors_error"]


def _check_tab_write(ns):
    """LD-152 (F1) — tab add/copy/delete: the request elements the request objects own, the
    NEW ``sheetId`` captured from each reply (never the title), and the destructive delete's
    plan-time identity snapshot.

    **LD-472 added the placement half**, which is the recipe's whole doc-truth correction: an
    ``AddTab`` with NO ``index`` lands FIRST (the guide said "append" for eight releases), and
    the append idiom the recipe now hands over — ``index=len(tabs)`` — really lands last. Both
    are asserted against the double's tab order, and the double models the measurement rather
    than the old sentence.
    """
    written = ns["write_client"].tab_writes
    assert written == [
        {"addSheet": {"properties": {"title": "Q4 Draft"}}},
        {"addSheet": {"properties": {"title": "Q4 Appendix", "index": ns["len_tabs"]}}},
        {"copySheet": {"source": {"sheetId": ns["new_sheet_id"]},
                       "destination": {"title": "Q4 Draft (copy)"}}},
        {"deleteSheet": {"sheetId": ns["copy_sheet_id"]}},
    ], written

    assert ns["new_sheet_id"] and ns["new_sheet_id"] != "Q4 Draft", ns["new_sheet_id"]
    assert ns["copy_sheet_id"] and ns["copy_sheet_id"] != ns["new_sheet_id"]

    # THE PLACEMENT TRUTH, measured on a disposable and modelled here: no `index` -> FIRST.
    order = [t["title"] for t in sorted(ns["tabs_after_add"], key=lambda t: t["index"])]
    assert order[0] == "Q4 Draft", (
        f"AddTab with no index must land FIRST — the recipe's correction: {order!r}")
    # ...and the append idiom really appends.
    final = [t["title"] for t in sorted(
        ns["write_client"].query_tabs(ns["spreadsheet_token"]), key=lambda t: t["index"])]
    assert final[-1] == "Q4 Appendix", (
        f"index=len(tabs) must land LAST — the idiom the recipe hands over: {final!r}")

    identity = ns["removed_identity"]
    assert identity["sheet_id"] == ns["copy_sheet_id"], identity
    assert identity["title"] == "Q4 Draft (copy)", identity
    assert identity["row_count"] and identity["column_count"], identity

    for log in (ns["add_log"], ns["copy_log"], ns["delete_log"]):
        assert [e.to_dict()["outcome"] for e in log.entries] == ["applied"], (
            [e.to_dict() for e in log.entries])
    assert ns["delete_log"].entries[0].structural["result"] is True

    remaining = {t["sheet_id"] for t in ns["write_client"].query_tabs(ns["spreadsheet_token"])}
    assert ns["copy_sheet_id"] not in remaining, "the deleted tab is still listed"
    assert ns["new_sheet_id"] in remaining, "the delete removed the wrong tab"


def _check_clear_cells(ns):
    """LD-152 (F10) — ``[[None]]`` really CLEARS: the cells become absent (a re-read answers
    ``None``), and the live-formula case carries the destructive note that the ``before``
    alone cannot show."""
    (entry,) = ns["plan"].entries
    assert entry.before == [["Widget", 3], ["Gadget", 5]], entry.to_dict()
    assert entry.after == [[None, None], [None, None]], entry.to_dict()
    assert [e.to_dict()["outcome"] for e in ns["log"].entries] == ["applied"], (
        [e.to_dict() for e in ns["log"].entries])
    assert not ns["log"].refusals, [e.to_dict() for e in ns["log"].refusals]
    assert ns["after"] == [[None, None], [None, None]], ns["after"]

    note = ns["note"]
    assert note["kind"] == "overwrites-live-formula", note
    assert note["count"] == 1 and note["cells"][0]["ref"] == "B4", note
    assert note["cells"][0]["expression"] == "=SUM(B2:B3)", note
    # the formula demonstration is dry-run only: exactly ONE write happened, the clear.
    assert len(ns["write_client"].puts) == 1, ns["write_client"].puts


def _check_multi_turn(ns):
    """LD-147 (b) + LD-151: the multi-turn queue really survived a serialization boundary, the
    commit really planned FRESH, and the **two-commit idiom** really works end to end.

    Every assertion is on what the recipe produced. The queue holds **strings** (a queue of
    live objects would prove nothing about crossing a turn boundary), each request rebuilt
    from JSON equals a request of its own family, ≥3 families are exercised — including the
    **tagless** ``EditRequest`` record — the plan was built with the whole-document guard
    armed, and every entry of the batch landed.

    **The second commit (LD-151 / dogfood F14) is the part a queue gets wrong.** One tree, one
    batch: no request in commit 1 could have anchored on the section commit 1 creates, because
    preconditions are evaluated against a single consistent snapshot — a batch cannot depend on
    its own writes. So the recipe demonstrates the sanctioned recovery instead of the shape that
    loops: commit 1 hands back ``created_block_ids``, and commit 2 anchors the follow-up by one
    of them through an :class:`~larkdocio.write.model.AnchorById`, resolving to the block commit
    1 created and landing with zero refusals.
    """
    from larkdocio.write import (
        AnchorById,
        DeleteRequest,
        EditRequest,
        InsertRequest,
        Plan,
        SubSpanEditRequest,
    )

    queue = ns["queue"]
    assert len(queue) >= 3, f"the multi-turn queue must hold ≥3 requests: {queue!r}"
    assert all(isinstance(record, str) for record in queue), (
        f"the queue must hold SERIALIZED requests: {[type(r).__name__ for r in queue]}")

    families = (EditRequest, InsertRequest, DeleteRequest, SubSpanEditRequest)
    requests = ns["requests"]
    assert len(requests) == len(queue)
    assert all(isinstance(r, families) for r in requests), [type(r).__name__ for r in requests]
    assert len({type(r) for r in requests}) >= 3, [type(r).__name__ for r in requests]
    for request in requests:
        assert type(request).from_dict(request.to_dict()) == request, request
    assert any("op" not in r.to_dict() for r in requests), (
        "the queue must include the tagless EditRequest form")

    plan = ns["plan"]
    assert isinstance(plan, Plan)
    assert plan.revision_guard == "active", plan.to_dict()
    assert len(plan.entries) == len(requests)
    assert not plan.refusals, [e.to_dict() for e in plan.refusals]

    log = ns["log"]
    outcomes = [e.to_dict()["outcome"] for e in log.entries]
    assert len(outcomes) == len(requests) and "refused" not in outcomes, (
        [e.to_dict() for e in log.entries])

    document = OfflineWriteClient.documents.for_token(ns["doc_token"])
    assert document.text_of("p1") == "Revenue grew 15.0% in Q3.", document.text_of("p1")
    assert document.text_of("h1") == "Overview and outlook", document.text_of("h1")

    # COMMIT 2 — the two-commit idiom, executed (LD-151 / F14).
    created = ns["created_block_ids"]
    assert created and all(created), (
        f"commit 1 must hand back one id per authored block: {created!r}")
    assert ns["findings_heading_id"] == created[0], (created, ns["findings_heading_id"])
    follow_up_plan = ns["follow_up_plan"]
    assert isinstance(follow_up_plan, Plan)
    (follow_up_entry,) = follow_up_plan.entries
    assert follow_up_entry.is_resolved, follow_up_entry.to_dict()
    assert follow_up_entry.anchor == AnchorById(block_id=ns["findings_heading_id"]), (
        follow_up_entry.to_dict())
    assert follow_up_entry.block_id == ns["findings_heading_id"], (
        "the by-id anchor did not resolve to the block commit 1 created")
    assert follow_up_plan.revision_guard == "active", follow_up_plan.to_dict()
    assert [e.to_dict()["outcome"] for e in ns["follow_up_log"].entries] == ["inserted"], (
        [e.to_dict() for e in ns["follow_up_log"].entries])


def _check_subspan_edit(ns):
    """LD-147 (g): the sub-span edit rewrote **only** the span and left its neighbours alone.

    The plan entry's ``before``/``after`` are the span (an ``EditRequest``'s would be the whole
    block — that difference IS the recipe), and the block's text afterwards is the original
    sentence with one substitution.
    """
    from larkdocio.write import Plan

    plan = ns["plan"]
    assert isinstance(plan, Plan)
    (entry,) = plan.entries
    d = entry.to_dict()
    assert d["op"] == "subspan" and d["outcome"] == "resolved", d
    assert (d["before"], d["after"]) == ("12.4%", "15.0%"), d

    assert [e.to_dict()["outcome"] for e in ns["log"].entries] == ["applied"], (
        [e.to_dict() for e in ns["log"].entries])
    assert not ns["log"].refusals, [e.to_dict() for e in ns["log"].refusals]
    document = OfflineWriteClient.documents.for_token(ns["doc_token"])
    assert document.text_of("p1") == "Revenue grew 15.0% in Q3.", document.text_of("p1")


def _check_code_edit(ns):
    """LD-147 (g)+(f): a code block is authored, its body is rewritten by id, and a
    ``language=None`` block ships alongside it as a **bare** fence.

    The read-back is the real reader over the shared offline document, so the fence and its
    language tag are the shipped renderer's output — and the body's indentation surviving is
    LD-146's verbatim guarantee holding through an authored-then-edited round trip.
    """
    import harness  # tests/ is on sys.path (conftest)

    from larkdocio.write import Plan

    plan = ns["plan"]
    assert isinstance(plan, Plan)
    (entry,) = plan.entries
    assert entry.is_resolved and entry.block_id == ns["code_block_id"], entry.to_dict()
    assert [e.to_dict()["outcome"] for e in ns["log"].entries] == ["applied"], (
        [e.to_dict() for e in ns["log"].entries])
    assert not ns["log"].refusals, [e.to_dict() for e in ns["log"].refusals]

    document = OfflineWriteClient.documents.for_token(ns["doc_token"])
    body = document.text_of(ns["code_block_id"])
    assert "def total(rows):" in body and "    return sum(rows)" in body, repr(body)

    markdown = harness.render(document.block_dicts(), doc_id=ns["doc_token"])
    assert "```python\ndef total(rows):\n    return sum(rows)" in markdown, markdown
    ascii_art = document.text_of(ns["ascii_art_block_id"])
    assert "|" in ascii_art and ascii_art in markdown, (repr(ascii_art), markdown)
    assert re.search(r"^```$", markdown, flags=re.MULTILINE), (
        "the language=None block must read back as a BARE fence:\n" + markdown)


def _check_comparator(ns):
    """LD-154 / F15: the verification recipe really exhibits BOTH sides of the comparator
    against a document it wrote to and read back.

    The two booleans are the whole point and they must land on **opposite** answers: a
    stage where ``found_verbatim`` came out ``True`` would mean the reader had stopped
    normalizing and the recipe was teaching a defect that no longer exists; a stage where
    ``same_content`` came out ``False`` would mean the round-trip really does lose content.
    Both are asserted, plus that ``read_back`` is a genuine read of the landed write (the
    loose form is *in the document*, not merely a string the recipe typed out).
    """
    from larkdocio.write import compose

    authored, reader_form = ns["authored"], ns["reader_form"]
    read_back = ns["read_back"]

    assert authored != reader_form, "the recipe's two forms are the same string"
    assert ns["found_verbatim"] is False, (
        "the recipe's own read-back CONTAINS the tight authored form, so the trap it "
        "teaches did not happen:\n" + read_back
    )
    assert ns["found_loose"] is True, (
        "the loose form is not in the read-back, so the recipe never proved the write "
        "landed at all:\n" + read_back
    )
    assert ns["same_content"] is True, "compose-equivalence failed on the recipe's own pair"
    # The comparison must be the real thing, not a hard-coded True.
    assert compose(authored) == compose(reader_form)
    assert "the week-3 dip recovered by Friday" in read_back


def _check_compose_check(ns):
    """LD-518: the batch-discovery recipe really found EVERY construct in its own fragment,
    at the right lines, and did not report the one inside the fence.

    Each assertion is a way the recipe could look right while teaching something false: a
    ``report`` that came back ``ok`` would mean the fragment stopped being a refusing one; a
    short construct list would mean the checker is back to serial discovery; a row pointing
    into the fenced block would mean the recipe's own claim about a fence is wrong; and the
    ``kinds`` / ``lines`` / ``payload`` names are what the recipe hands its reader, so they
    are graded rather than assumed.
    """
    from larkdocio.write import compose

    report, fragment = ns["report"], ns["fragment"]
    assert report.ok is False, "the recipe's fragment composes, so it teaches nothing"
    found = {row.construct for row in report.refusals}
    assert {"bold", "italic", "strikethrough", "link", "empty-list-item", "html"} <= found, (
        f"the recipe's own fragment discovered only {sorted(found)}")
    assert ns["kinds"] == report.constructs and len(ns["kinds"]) == len(found)
    assert ns["lines"] == [row.line for row in report.refusals]
    assert ns["payload"] == report.to_dict() and ns["payload"]["ok"] is False

    # The fence claim, checked against the source rather than trusted: the fenced block sits
    # at the end of the fragment, and no reported line is inside it.
    lines = fragment.split("\n")
    fence_lines = [n for n, line in enumerate(lines, start=1) if line.startswith("```")]
    assert len(fence_lines) == 2, fence_lines
    inside = range(fence_lines[0], fence_lines[1] + 1)
    assert not [row for row in report.refusals if row.line in inside], (
        "a construct inside the fenced block was reported")
    assert "**this** alone" in lines[fence_lines[0]], lines[fence_lines[0]]

    # …and the serial compiler still refuses the same fragment, on the FIRST construct only.
    try:
        compose(fragment)
    except Exception as refused:
        assert report.refusals[0].detail == getattr(refused, "refusal").detail
    else:                                          # pragma: no cover — would be a real bug
        raise AssertionError("compose() accepted the fragment compose_check() refused")


def _check_round_trip(ns):
    """LD-236: the round-trip recipe really ran the whole shipped chain against a document it
    read, and the verification it teaches is the compose comparator rather than string equality.

    Every assertion is on what the recipe *produced*, and each corresponds to a way the recipe
    could look right while teaching something false:

    * the **projection** carries a marker per block and the emitted id list travels with it —
      a recipe that searched the text for markers would be teaching the one thing the
      projection exists to prevent;
    * the **plan** names exactly one edited block and nothing else moved, so the round trip is
      surgical rather than a re-authoring of the document;
    * the compiled batch is **one** request and it carries **no marker** — the strip is what
      keeps identity out of the document, and a recipe whose compiled body carried one would
      be shipping the leak;
    * the write **landed** in the document the double serves (not merely in a variable), and
    * ``same_content`` is a real comparison of two ``compose()`` results, not a hard-coded
      ``True``.
    """
    from larkdocio.model.projection import BlockIdProjection
    from larkdocio.write import compose
    from larkdocio.write.model import EditRequest

    projection = ns["projection"]
    assert isinstance(projection, BlockIdProjection)
    assert projection.block_ids and all(
        f"lark:block:{block_id}" in projection.markdown for block_id in projection.block_ids), (
        "the projection must carry a marker for every identifier it reports as emitted")

    plan = ns["plan"]
    assert plan.ok, [r.to_dict() for r in plan.refusals]
    # LD-471 — the recipe now teaches BOTH halves of what reconcile() plans: the edit it
    # always taught, and an INSERTION (which it planned all along and never showed). In
    # document order, and each anchored to its own marker.
    assert ns["changed"] == ["inserted", "edited"], ns["changed"]
    inserted, edit = plan.changes
    assert (inserted.anchor_block_id, inserted.anchor_position) == ("h1", "after"), (
        inserted.to_dict())
    assert edit.block_id == "p1", edit.to_dict()

    requests = ns["requests"]
    assert len(requests) == 2, requests
    # Edits compile ahead of inserts — one batch, and no request anchored to content another
    # request in it creates (the one-tree-one-batch contract).
    assert [type(request).__name__ for request in requests] == [
        "EditRequest", "InsertRequest"], requests
    assert isinstance(requests[0], EditRequest), requests
    assert "lark:block:" not in repr(requests), (
        "a compiled request body carries an identity marker — the strip is the guarantee that "
        "no marker ever reaches Lark")

    assert [e.to_dict()["outcome"] for e in ns["log"].entries] == [
        "applied", "inserted"], [e.to_dict() for e in ns["log"].entries]
    assert not ns["log"].refusals, [e.to_dict() for e in ns["log"].refusals]

    read_back = ns["read_back"]
    assert "lark:block:" not in read_back, "a marker reached the document"
    assert "Revenue grew 15.0% in Q3." in read_back and "12.4%" not in read_back, read_back
    assert ns["same_content"] is True
    assert compose(ns["region"]) == compose(ns["new_text"])

    document = OfflineWriteClient.documents.for_token(ns["doc_token"])
    assert document.text_of("p1") == "Revenue grew 15.0% in Q3.", document.text_of("p1")


def _check_todo_flip(ns):
    """LD-597: the round-trip recipe's SECOND block really ticked a checkbox — and the box
    moved **in the document the double serves**, not merely in a variable.

    The guide's write-recipe router row promises a worked flip and sends the reader here, so
    the flip is a block of this recipe rather than a recipe of its own. What makes the block
    gradeable at all is ``OfflineDocument.patch``'s ``update_text_style`` arm: the flip is
    applied as a bare done-bit patch (``_apply_narrative`` **skips** the text patch when the
    live text already equals the replacement), so a double that answered success without
    moving the bit would let this whole block "pass" against a checkbox that never moved.
    **Red-proved**: with that arm removed, the two done-bit assertions below fail while every
    other assertion here still passes — which is precisely the receipt-shaped silence the arm
    exists to end.

    The before/after pair is read off the double's **own** stored state — the pre-flip side
    from the revision the recipe planned against (``block_dicts_at``), the post-flip side from
    the live block — so neither side is a recipe variable vouching for itself.
    """
    from larkdocio.write.model import EditRequest

    document = OfflineWriteClient.documents.for_token(ns["doc_token"])
    todo_id = ns["todo_block_id"]
    item = ns["item"]

    # The item was created through the ordinary authoring route, so its id came from the
    # apply log rather than from the shared fixture (which LD-597 must leave byte-identical).
    assert todo_id in document.blocks, (todo_id, sorted(document.blocks))
    assert ns["was_unticked"] is True, "the recipe read a box that was not unticked"

    # BEFORE — the state the revision the plan was armed against described.
    before = {b["block_id"]: b for b in document.block_dicts_at(int(ns["revision"]))}
    assert before[todo_id]["todo"]["style"]["done"] is False, before[todo_id]

    # The plan is surgical and the compiled request carries the BIT, not a reworded body.
    assert ns["flip_states"] == ["edited"], ns["flip_states"]
    requests = ns["requests"]
    assert len(requests) == 1 and isinstance(requests[0], EditRequest), requests
    assert ns["moved_bit"] is True, requests[0].to_dict()
    assert ns["same_words"] is True, requests[0].to_dict()
    assert [e.to_dict()["outcome"] for e in ns["log"].entries] == ["applied"], (
        [e.to_dict() for e in ns["log"].entries])
    assert ns["log"].entries[0].todo_done is True, ns["log"].entries[0].to_dict()

    # AFTER — the box moved on the block itself, and nothing rewrote its words.
    after = document.get(todo_id)
    assert after["todo"]["style"]["done"] is True, after
    assert document.text_of(todo_id) == item, document.text_of(todo_id)

    # ...and the flip is visible to a READ, which is what the recipe teaches as the receipt.
    read_back = ns["read_back"]
    assert f"- [x] {item}" in read_back, read_back
    assert f"- [ ] {item}" not in read_back, read_back
    assert ns["ticked"] is True

def _check_copy_this_update_script(ns):
    """LD-422: the canonical end-to-end update script really ran, START TO FINISH, and the
    two things a "copy this" script can quietly ship wrong are asserted rather than read.

    * **The plan gate survived the copy.** ``preview`` is a real ``Plan`` with its revision
      guard **active** — a script that dropped ``document_revision_id`` to save a line would
      still apply and still look right, and would have silently un-armed ``STALE_DOCUMENT``
      for every consumer who pasted it.
    * **The update is an UPDATE.** Exactly one block moved, it moved as an *edit*, and the
      block that carried the text still carries its own id afterwards — which is the whole
      claim the script makes over a clear-and-rewrite, and the one a green run would not show.
    """
    from larkdocio.model.projection import BlockIdProjection
    from larkdocio.write.model import EditRequest

    projection = ns["projection"]
    assert isinstance(projection, BlockIdProjection)
    assert projection.block_ids, "the script projected no identifiers to update against"

    assert ns["plan"].ok, [r.to_dict() for r in ns["plan"].refusals]
    assert ns["changed"] == ["edited"], ns["changed"]

    preview = ns["preview"]
    assert preview.revision_guard == "active", preview.revision_guard
    requests = ns["requests"]
    assert len(requests) == 1 and isinstance(requests[0], EditRequest), requests
    assert "lark:block:" not in repr(requests), (
        "a compiled request body carries an identity marker — no marker ever reaches Lark")

    assert ns["applied"] == ["applied"], ns["applied"]

    # The id-preserving claim, measured on the double: the paragraph the script edited is the
    # SAME block, holding the new text — not a new block holding it.
    document = OfflineWriteClient.documents.for_token(ns["doc_token"])
    assert document.text_of("p1") == "Revenue grew 15.0% in Q3.", document.text_of("p1")
    assert "p1" in projection.block_ids, projection.block_ids


def _check_table_grow(ns):
    """LD-575: two rows appended to a table that already exists — and every id it started
    with still there, in order.

    The assertion that matters is the one the whole operation exists for: the table's own
    ``block_id`` and every pre-existing cell's survive the grow. So the cell list is captured
    off the double **before** the grow (the ids the create provisioned) and compared against
    the grown one as a PREFIX — same ids, same order, nothing dropped and nothing reordered —
    with the appended cells being exactly what each entry's ``created_block_ids`` claimed.

    The cost disclosure is checked as a MEASUREMENT and not as a formula: the number each entry
    reports must equal the write calls the double actually received for it, which is one, which
    is why ``atomic`` is true.
    """
    from larkdocio.write import Plan

    plan = ns["plan"]
    assert isinstance(plan, Plan) and len(plan.entries) == 2, plan
    document = OfflineWriteClient.documents.for_token(ns["doc_token"])
    table = document.get(ns["table_block_id"])
    assert table["block_type"] == 31, table

    for entry in plan.entries:
        d = entry.to_dict()
        assert d["op"] == "grow-table" and d["outcome"] == "resolved", d
        assert d["block_id"] == ns["table_block_id"], d
        assert "columns" in d["before"] and "columns" in d["after"], d

    log = ns["log"]
    assert [e.to_dict()["outcome"] for e in log.entries] == ["inserted", "inserted"], (
        [e.to_dict() for e in log.entries])
    assert not log.refusals, [e.to_dict() for e in log.refusals]

    appended = [cell for entry in log.entries for cell in entry.created_block_ids]
    assert len(appended) == 4, appended            # two rows of a two-column table
    assert len(set(appended)) == 4, appended
    for entry in log.entries:
        d = entry.to_dict()
        assert d["mutating_write_calls"] == 1, d    # counted, and one append is one call
        assert d["atomic"] is True, d

    # The grid the double now holds: the four cells the create provisioned, IN ORDER, then the
    # four the two grows appended. The prefix is the identity claim.
    cells = list(table["children"])
    assert cells[-4:] == appended, (cells, appended)
    assert len(cells) == 8, cells
    # The pre-existing ids, derived INDEPENDENTLY of the log: off the parsed tree the plan was
    # built against, which is what the table looked like before any row was appended.
    from larkdocio.model import TableNode

    def tables(node):
        if isinstance(node, TableNode):
            yield node
        for child in (getattr(node, "children", None) or ()):
            yield from tables(child)

    (parsed,) = list(tables(ns["root"]))
    before = [cell.block_id for cell in parsed.cells]
    assert len(before) == 4, before
    assert cells[:4] == before, (cells, before)
    prop = table["table"]["property"]
    assert (prop["row_size"], prop["column_size"]) == (4, 2), prop


def _check_restructure(ns):
    """LD-471 — the reorganisation really ran, and its four load-bearing claims are MEASURED
    on the double rather than read off the prose.

    * **The order changed, and the read-back is what says so.** ``landed`` is the document's
      own order after both applies — the recipe's final assertion is executed here, not
      printed.
    * **Identity was preserved.** The LCS blocks kept their ids; only the genuinely-moved
      block was re-created. A recipe that deleted and re-made everything would pass an
      order check and fail this one, which is exactly the difference it teaches.
    * **Insert came BEFORE delete** — measured on the document's own revision history: some
      intermediate revision holds the original **and** its copy (duplication), and none holds
      neither (a hole). That is the recipe's whole safety argument, and the opposite order
      would satisfy every other assertion here.
    * **The comments leg ran.** ``review`` is a real read, and the orphan-risk join was
      computed over the moved set — the step that is worthless if it is skipped when busy.
    """
    from larkdocio.comments import CommentsRead

    assert isinstance(ns["review"], CommentsRead), type(ns["review"])
    assert ns["review"].available, ns["review"].unavailable_reason

    # The order, as the recipe's own read-back saw it.
    assert ns["landed"] == ns["DESIRED"], ns["landed"]

    # Exactly one block moved (the sample authors three, one out of place), and the blocks
    # that did not move kept the ids they had.
    assert len(ns["moved_ids"]) == 1, ns["moved_ids"]
    assert len(ns["recreated"]) == 1, ns["recreated"]
    assert set(ns["survivors"]) == set(ns["kept"]), (ns["survivors"], ns["kept"])
    assert "p1" in ns["kept"], "the block nobody asked to move was re-created anyway"

    # The document really is in the desired order, read off the double rather than off the
    # recipe's own namespace.
    document = OfflineWriteClient.documents.for_token(ns["doc_token"])
    parent = document.get("h1")
    order = [document.text_of(child) for child in parent["children"]]
    assert [ns["label"](text) for text in order] == ns["DESIRED"], order

    # …and the moved block's OLD id is gone: a reorder that only inserted would also satisfy
    # the order assertion above.
    assert ns["moved_ids"][0] not in parent["children"], "the original was never deleted"

    # INSERT BEFORE DELETE, proven on the revision history: one intermediate state holds both
    # the original and its copy. Delete-then-insert would instead leave a state holding
    # neither — the hole this ordering exists to make impossible.
    original, copy = ns["moved_ids"][0], ns["recreated"][0]
    states = [{block["block_id"] for block in snapshot}
              for _revision, snapshot in sorted(document._history.items())]
    states.append({block["block_id"] for block in document.block_dicts()})
    since = next(i for i, state in enumerate(states) if original in state)
    assert any({original, copy} <= state for state in states[since:]), (
        "no revision held the original and its copy at once — the delete ran before the "
        "insert, which is the ordering that leaves a hole")
    assert all(state & {original, copy} for state in states[since:]), (
        "a revision after the block existed held neither it nor its copy — that is the hole")


def _check_copy_this_file_first(ns):
    """LD-445: the copy-this recipe's **file-first variant** ran, and it is the same flow.

    The variant is one block holding two halves — the read leg that ends by writing the
    snapshot, and the resumable entry point that starts at ``load``. Run whole, it must land
    exactly what the canonical script lands; the *isolation* of the second half (that it
    leans on nothing the first half bound) is proved in ``test_file_first_routing.py``, which
    executes it alone.

    The two things a persistence variant can quietly ship wrong are asserted rather than
    read: that the guard is armed **from the snapshot's own revision** (a variant that let
    ``document_revision_id`` go missing would still apply, still look right, and would have
    un-armed ``STALE_DOCUMENT`` for everyone who pasted it), and that the artefacts really
    reached the disk — a "file-first" script that never wrote a file teaches nothing.
    """
    import pathlib

    from larkdocio.write.model import EditRequest

    assert pathlib.Path("document.snapshot").exists(), (
        "the variant's read leg wrote no snapshot — nothing is resumable")
    assert pathlib.Path("document.md").exists(), (
        "the variant wrote no projection file — the editable artefact never reached disk")

    snap = ns["snap"]
    assert snap.document_revision_id is not None, (
        "the snapshot carries no revision, so the compare-and-swap cannot be armed from it")
    # LD-465: …and the DOMAIN came off the file too, which is what makes the section's
    # headline promise ("needs nothing from Part A but the two files") true.
    assert snap.api_domain, (
        "the snapshot carries no api_domain, so the resumed half cannot build a client from "
        "the artefact alone — it would need Part A's URL back")
    assert ns["preview"].revision_guard == "active", ns["preview"].revision_guard
    requests = ns["requests"]
    assert len(requests) == 1 and isinstance(requests[0], EditRequest), requests

    assert ns["applied"] == ["applied"], ns["applied"]
    document = OfflineWriteClient.documents.for_token(snap.document_token)
    assert document.text_of("p1") == "Revenue grew 15.0% in Q3.", document.text_of("p1")


def _check_comments_read(ns):
    """LD-159: the comments recipe ran end to end over the shipped model and the real join.

    Three things are asserted, and each corresponds to a way the recipe could look right while
    teaching something false:

    * the join **resolved** — the fixture paragraph's own anchor came back as a comment, so the
      block-to-comments lookup the recipe teaches produced a real result rather than an empty
      one that would pass any assertion;
    * the author is a **raw id** and no name appears anywhere in the recipe's output, which is
      the one thing a consumer must not be taught to expect;
    * the availability check ran on the **available** branch, so ``review`` is a real read and
      not the degraded object (which would also print nothing and also pass).
    """
    review = ns["review"]
    assert review.available is True, review.unavailable_reason
    assert [c.comment_id for c in review.comments] == [_FIXTURE_COMMENT_ID], review.comments

    comment = review.comments[0]
    assert comment.user_id == _FIXTURE_COMMENT_AUTHOR
    assert comment.user_id.startswith("ou_"), "the author must be a raw open id"
    assert comment.text == _FIXTURE_COMMENT_TEXT
    assert comment.scope == "anchored"
    assert review.missing_ids == ()

    # LD-172: the recipe reads the file's WHOLE comment list — and it read it through the
    # LIST endpoint, not the anchor-scoped batch query. Checked at the transport, because the
    # difference between the two calls is invisible in the count on a one-comment fixture and
    # is exactly what the recipe got wrong (a scoped read reported 71% of a real document as
    # all of it).
    assert review.completeness == "complete", review.disclosure
    assert "the file's whole comment list" in review.disclosure
    assert review.unanchored_ids == (), "the fixture comment is anchored, not whole-document"
    assert OfflineCommentsReadClient.ops == ["list_comments"], (
        f"the recipe hit {OfflineCommentsReadClient.ops} — it must read the file's whole "
        f"comment list, not the anchor-scoped batch query")

    # The block-to-comments direction really resolved against the parsed tree — the recipe's
    # own walk found the anchored paragraph, not merely iterated an empty generator.
    root = ns["root"]
    hits = [node for node in ns["walk"](root) if review.for_node(node)]
    assert [n.block_id for n in hits] == ["p1"], [n.block_id for n in hits]
    assert review.for_node(hits[0])[0].text == _FIXTURE_COMMENT_TEXT

    # And the disclosure the recipe prints is a real sentence about this read.
    assert "1 comment(s) read" in ns["review"].disclosure


def _assert_no_markdown_call(slug: str) -> None:
    """The object-level thesis: this run touched **none** of the three Markdown call sites.

    Asserted from inside the recipe's own check, so **every** runner that executes the spec
    (the offline run, the no-network run) re-proves it rather than one dedicated test.
    """
    calls = markdown_calls()
    assert calls, (
        "the Markdown call spy was not installed — run the recipe through "
        "guide_recipes.stage(...)")
    touched = {name: count for name, count in calls.items() if count}
    assert not touched, (
        f"the object-level recipe {slug!r} made a Markdown call: {touched}. The whole claim "
        "of this recipe is that the object level never produces Markdown.")


def _check_disposable_lifecycle(ns):
    """LD-176: the disposables doctrine, executed — create → use → ``finally``-delete →
    confirm gone.

    Every assertion is on what the recipe *produced*, and each corresponds to a way the
    recipe could look right while teaching something false:

    * the token it used is the one the create **minted** (a recipe that wrote to a
      pre-existing fixture token would prove nothing about self-provisioning);
    * the write really landed in the disposable and reads back;
    * the delete happened **exactly once**, and the double's own lifecycle model — not the
      recipe's optimism — is what says the token stopped resolving;
    * ``confirmed_gone`` came from **observing the deleted-token error**, which is the
      difference between confirming a delete and assuming one from a ``code: 0``.
    """
    from larkdocio.sheets.write_client import SPREADSHEET_GONE_CODE

    client = ns["write_client"]
    token = ns["spreadsheet_token"]

    assert client.created == [token], (client.created, token)
    assert client.puts == [("3bf016!A1:A1", [["disposable"]])], client.puts
    assert ns["read_back"] == [["disposable"]], ns["read_back"]
    assert client.deleted == [token], client.deleted
    assert ns["confirmed_gone"] is True, "the recipe never confirmed the file was gone"

    # The confirmation is real: the token genuinely stops resolving, with the shipped code.
    import pytest as _pytest

    from larkdocio.errors import LarkAPIError

    with _pytest.raises(LarkAPIError) as exc:
        client.query_tabs(token)
    assert exc.value.code == SPREADSHEET_GONE_CODE


def _check_object_level_docx(ns):
    """The object-level docx chain: the TREE, the block's own id, an id-anchored edit that
    landed — and not one Markdown call on the way.

    Every assertion is on what the recipe produced. The node it picked is the fixture
    paragraph (found by walking the tree, not by matching rendered text); it carries the
    review anchor the projection would have dropped, which is what makes "the detail is on
    the tree" a demonstrated fact here rather than a claim; the plan resolved through an
    :class:`~larkdocio.write.model.AnchorById` with the whole-document guard armed; and the
    block's text really changed in the shared offline document.
    """
    from larkdocio.model import Node
    from larkdocio.write import AnchorById, Plan

    assert isinstance(ns["root"], Node), "the recipe must produce a parsed TREE"

    target = ns["target"]
    assert target.block_id == "p1", f"the tree walk picked the wrong block: {target!r}"
    assert target.comment_ids == [_FIXTURE_COMMENT_ID], (
        "the picked node must carry the review anchor the projection drops — otherwise the "
        f"recipe demonstrates nothing about the level difference: {target.comment_ids!r}")

    plan = ns["plan"]
    assert isinstance(plan, Plan)
    (entry,) = plan.entries
    assert entry.is_resolved, entry.to_dict()
    assert entry.anchor == AnchorById(block_id="p1"), entry.to_dict()
    assert plan.revision_guard == "active", plan.to_dict()

    assert [e.to_dict()["outcome"] for e in ns["log"].entries] == ["applied"], (
        [e.to_dict() for e in ns["log"].entries])
    assert not ns["log"].refusals, [e.to_dict() for e in ns["log"].refusals]
    document = OfflineWriteClient.documents.for_token(ns["doc_token"])
    assert document.text_of("p1") == "Revenue grew 15.0% in Q3.", document.text_of("p1")

    _assert_no_markdown_call("change-a-document-at-the-object-level-no-markdown-anywhere")


def _check_object_level_sheets(ns):
    """The object-level sheets chain: values as objects, the cell chosen from the DATA, one
    typed request applied — and not one Markdown call on the way.

    The A1 ref is the assertion that matters: it is computed from the values matrix and the
    used range's own origin, so a recipe that quietly hard-coded a range (or matched text out
    of a rendered table) would not produce it.
    """
    from larkdocio.sheets.plan import Plan

    used = ns["used"]
    assert used.values == [["Name", "Qty"], ["Widget", 3]], used.values
    assert ns["tab"].sheet_id == "3bf016", ns["tab"]
    assert (ns["row_index"], ns["column_index"]) == (1, 1), (
        f"the cell must be located from the DATA: {ns['row_index']}, {ns['column_index']}")
    assert ns["target"] == "3bf016!B2:B2", ns["target"]

    plan = ns["plan"]
    assert isinstance(plan, Plan)
    (entry,) = plan.entries
    assert entry.to_dict()["outcome"] == "resolved", entry.to_dict()
    assert entry.before == [[3]] and entry.after == [[4]], entry.to_dict()

    assert [e.to_dict()["outcome"] for e in ns["log"].entries] == ["applied"], (
        [e.to_dict() for e in ns["log"].entries])
    assert not ns["log"].refusals, [e.to_dict() for e in ns["log"].refusals]
    assert ns["write_client"].puts == [("3bf016!B2:B2", [[4]])], ns["write_client"].puts

    _assert_no_markdown_call("change-a-spreadsheet-at-the-object-level-no-markdown-anywhere")


def _check_mermaid_authoring(ns):
    """LD-192: the diagram recipe really compiled a **structured spec** to Mermaid source,
    landed a type-40 block through the gate, and then **replaced** it — proving the create-only
    story end to end offline, including the cost the docs promise.

    Every assertion is on what the recipe *produced*, and the two that matter most are the two
    a reader of the prose would want proven rather than asserted:

    * the landed block is a real ``add_ons`` payload — block type 40, the shipped
      ``component_type_id``, and a ``record`` whose ``data`` is the **compiled** source (so the
      compiler and the create path really are joined by that string);
    * the replace route **changes the ``block_id``** — the cost the guide, the writer brief and
      the capability floor all state. Here it is measured, not repeated.
    """
    import json

    from larkdocio.blocks.diagram import MERMAID_COMPONENT_TYPE_ID
    from larkdocio.write import Plan
    from larkdocio.write.model import NewBlockKind

    # 1. the compiler ran, and its output is what got wrapped.
    source = ns["source"]
    assert "flowchart TD" in source, source
    assert ns["diagram"].kind is NewBlockKind.MERMAID, ns["diagram"]
    assert ns["diagram"].text == source, "the block must carry the COMPILED source"

    plan = ns["plan"]
    assert isinstance(plan, Plan)
    (entry,) = plan.entries
    assert entry.is_resolved and entry.block_id == "p1", entry.to_dict()
    assert [e.to_dict()["outcome"] for e in ns["log"].entries] == ["inserted"], (
        [e.to_dict() for e in ns["log"].entries])

    # 2. THE REPLACE ROUTE ran: the revised diagram landed and the old block is GONE.
    document = OfflineWriteClient.documents.for_token(ns["doc_token"])
    first_id = ns["diagram_block_id"]
    insert_entry, delete_entry = ns["replace_log"].entries
    assert [e.to_dict()["outcome"] for e in (insert_entry, delete_entry)] == [
        "inserted", "deleted"], [e.to_dict() for e in ns["replace_log"].entries]

    # 3. what the FIRST create landed is read off the DELETE's own removed-payload — the block
    #    itself is gone by now, which is the whole point of the route. This doubles as proof
    #    that the destructive snapshot really is sufficient for a diagram: a `record` recovered
    #    here is a diagram a consumer could put back.
    removed = delete_entry.removed_payload
    assert removed["block_id"] == first_id, removed
    assert removed["block_type"] == 40, removed
    assert removed["add_ons"]["component_type_id"] == MERMAID_COMPONENT_TYPE_ID, removed
    assert json.loads(removed["add_ons"]["record"])["data"] == source, (
        "the removed-payload must carry the COMPILED source the recipe authored")
    new_id = ns["new_diagram_block_id"]
    revised = document.blocks[new_id]
    assert revised["block_type"] == 40, revised
    assert "Archived" in json.loads(revised["add_ons"]["record"])["data"], (
        "the REVISED source must be what the replacement carries")
    assert first_id not in document.blocks, (
        "the replaced diagram must be gone — the route is delete + re-create, not two diagrams")

    # 4. THE COST, measured: a new block_id. This is the claim the docs make; it is proven here
    #    rather than restated, which is the difference between a documented and a hoped-for one.
    assert new_id != first_id, (
        f"the replace route must yield a NEW block_id; got {new_id!r} both times")

    # 5. …and the reader renders the replacement as a diagram fence carrying the new source.
    import harness  # tests/ is on sys.path (conftest)

    markdown = harness.render(document.block_dicts(), doc_id=ns["doc_token"])
    assert "```mermaid" in markdown, markdown
    assert "Archived" in markdown, markdown


def _check_comment_write(ns):
    """The comment pair, executed: created → read back → removed, and gone at the end.

    Every assertion here is about a fact the recipe would get wrong if it were only
    *plausible*. In particular ``made.scope`` comes from the LISTING endpoint, which is the
    only one that reports the scope at all — so this proves the recipe's read-back step is real
    rather than decorative, and that a whole-document comment reads back as one.
    """
    from larkdocio.write import ApplyLog

    log = ns["log"]
    assert isinstance(log, ApplyLog)
    (created,) = log.entries
    assert created.outcome == "commented", created.to_dict()

    comment_id = ns["comment_id"]
    author_id = ns["author_id"]
    assert comment_id and author_id.startswith("ou_"), (comment_id, author_id)

    # The read-back really read back: whole-document, quoting no passage.
    made = ns["made"]
    assert made.comment_id == comment_id
    assert made.scope == "whole-document", made.to_dict()
    assert made.quote is None, made.to_dict()
    assert made.user_id == author_id, (
        "the author the apply-log disclosed is not the author the read reports")

    # The plan disclosed the bot authorship BEFORE the write — the point of the note.
    (planned,) = ns["plan"].entries
    kinds = [n["kind"] for n in planned.preview_notes]
    assert "comment-lands-as-the-app-bot" in kinds, kinds

    # And the removal removed it: the cascade emptied the thread, so the comment is gone.
    removal = ns["removal"]
    (removed,) = removal.entries
    assert removed.outcome == "comment-removed", removed.to_dict()
    assert removed.comment_record["removed_reply_ids"], removed.to_dict()
    assert removed.comment_record["complete"] is True

    from larkdocio.comments import comments as _comments
    after = _comments(ns["doc_token"])
    assert comment_id not in after.by_id, (
        "the recipe reported a removal that left the comment in place")


def _check_name_lookup_mention(ns):
    """LD-229 — the name → open_id → mention chain, run for real offline.

    What this measures, beyond "it did not raise": that the recipe actually went through the
    LOOKUP (the double records the query), that the id it authored with is the id the lookup
    resolved rather than one typed into the recipe, and that the plan still ran its own
    plan-time mention check — the two gates are independent by design and a recipe that made
    one stand in for the other would be teaching the wrong thing.
    """
    assert OfflineContactsSearchClient.queries, (
        "the recipe never called the lookup — it must resolve the name, not hard-code an id")
    lookup = ns["lookup"]
    assert lookup.resolved, f"the recipe's lookup refused: {lookup.refusal}"
    assert ns["open_id"] == lookup.user.open_id
    assert lookup.partiality.is_partial is False

    plan = ns["plan"]
    assert len(plan.entries) == 1
    assert plan.mention_validation in ("verified", "unavailable", "not-applicable")
    assert plan.mention_validation_detail, (
        "the plan's mention check must always say WHY — a silent skip is the failure mode")
    assert plan.mention_validation != "not-applicable", (
        "the plan did not see a mention at all — the recipe is no longer authoring one")
    # `mention_validation_ids` is the check AS DATA — {"checked", "resolved", "invalid"}.
    checked = tuple(plan.mention_validation_ids.get("checked") or ())
    if checked:
        assert lookup.user.open_id in checked
    else:
        # The check could not run on this seam; then the DETAIL must still name the id it
        # could not verify, or the disclosure is a shrug.
        assert lookup.user.open_id in plan.mention_validation_detail
    assert not plan.mention_validation_ids.get("invalid")


def _check_base_read(ns):
    """LD-251: the Base read ran end to end offline — objects first, then the two renders, over
    the committed captures of one real Base.

    Three things are asserted rather than assumed, because each is a rule a plausible-looking
    implementation would break: ``render_base`` of a document already held equals a second full
    read's Markdown (so the "no second network read" claim is exact, not approximate), every row
    is exactly as wide as its table's field list (rows project against the SCHEMA), and the Flow
    column's cells carry the absent-with-reason marker rather than a blank — which is the whole
    reason the marker exists."""
    from larkdocio.base.cells import STAGE_OPAQUE_MARKER
    from larkdocio.base.table import BaseRead

    document = ns["document"]
    assert isinstance(document, BaseRead) and document.tables, document
    markdown = ns["markdown"]
    assert markdown.lstrip().startswith("##"), markdown[:200]
    assert ns["same_markdown_from_scratch"] == markdown, (
        "render_base of the document already held must equal a fresh read's Markdown")

    for table in document.tables:
        for row in table.rows:
            assert len(row.cells) == len(table.fields), (table.name, row.record_id)

    # The captured Base carries a type-24 Flow column, so the marker is really exercised.
    assert ns["unreadable"], "the captured Base should expose at least one unreadable column"
    assert STAGE_OPAQUE_MARKER.split("(")[0] in markdown, markdown[:400]

    # …and no person payload leaked into the reading form (the name-only doctrine).
    for leak in ("avatar", "@", "ou_"):
        if leak == "@":
            continue  # an Email column legitimately renders a mailto: address
        assert leak not in markdown.lower(), leak

    # Read-only, and the pace-bearing client really was the one that answered.
    ops = [call[0] for call in OfflineBaseReadClient.calls]
    assert ops, "the recipe never touched the Base read client"
    assert set(ops) <= {"get_app", "list_tables", "list_fields", "search_records"}, ops
    assert "list_views" not in ops, "a view is not a projection — the read must not list views"


def _check_base_raw_values(ns):
    """LD-293: the opt-in RAW view ran end to end offline, and the recipe's dedupe really is
    done on the wire value rather than on the rendered one.

    Four things are asserted rather than assumed. The rendered cell and the raw value are
    **different objects with different shapes** (a Markdown link against the segment array it
    was built from) — which is the whole reason the accessor exists. The dedupe **found
    something**: the captured table's Email column carries one address on several rows, and a
    comparison over rendered cells is exactly what reported those as distinct. The snapshot
    **carried raw through** rather than dropping it at the model boundary. And the read spent
    **no extra call** for any of it."""
    from larkdocio.base.model import BaseTableSnapshot

    rendered, raw = ns["rendered"], ns["raw"]
    assert isinstance(raw, dict) and raw, "the recipe retained no raw values"
    assert rendered["Email"].startswith("["), rendered["Email"]
    assert isinstance(raw["Email"], list) and raw["Email"][0]["type"] == "url", raw["Email"]
    assert rendered["Email"] != raw["Email"], "raw and rendered must not be the same artefact"

    duplicates = ns["duplicates"]
    assert duplicates, (
        "the captured table shares one address across rows — the dedupe found none, which "
        "is the defect this recipe exists to remove")

    snapshot = ns["snapshot"]
    assert isinstance(snapshot, BaseTableSnapshot) and snapshot.raw_retained
    record = ns["record"]
    assert record.raw("Email") == record.raw_fields["Email"]
    assert record.value("Email") == f"[{record.raw('Email')[0]['text']}]" \
                                    f"({record.raw('Email')[0]['link']})"

    ops = [call[0] for call in OfflineBaseReadClient.calls]
    assert set(ops) <= {"get_app", "list_tables", "list_fields", "search_records"}, ops


def _check_base_write(ns):
    """LD-260 — the Base RECORD write handshake, end to end on the shipped engine.

    Everything above the transport is real: the snapshot's read proof, the offline diff, the
    plan gate, the client-side compare-and-swap and the write-effect oracle. So this asserts
    the properties the recipe teaches rather than that it ran.
    """
    plan, log = ns["plan"], ns["log"]

    # The preview costs nothing and the plan is what apply took. LD-473: the recipe now
    # teaches BOTH halves of a record write — `add` creates a row, `set` changes one — so the
    # plan carries a create and an update, one batch call per family.
    assert len(plan.entries) == 2, plan.to_dict()
    assert plan.api_call_count == 2, "one batch call per FAMILY per table"
    assert sorted(entry.op for entry in plan.entries) == ["create", "update"]

    # THE ORACLE'S POSITIVE HALF, offline: the double moves the anchor like a real Base, so a
    # landed write reads back `applied`. A double that held the revision constant would make
    # the recipe teach `dropped`, which is why the double models the bump at all.
    assert len(log.entries) == len(plan.entries), "the log is 1:1 with the plan"
    assert [entry.outcome for entry in log.entries] == ["applied"] * 2, log.to_dict()
    assert not log.dropped and not log.stale and not log.halted

    # LD-473 AC2 — `draft.add(...)` is how a row is CREATED, and the local handle it returns
    # is paired to the server's id on the applied log entry. A recipe that showed `add` and
    # never showed where the real record_id comes from would leave the guess it corrects
    # only half-corrected.
    from larkdocio.base.model import NEW_RECORD_PREFIX

    assert ns["new_row"].startswith(NEW_RECORD_PREFIX), (
        f"`draft.add` must return a LOCAL, plan-time handle: {ns['new_row']!r}")
    created = ns["created"]
    assert created.get(ns["new_row"]), (
        "the applied create must carry the server's own record id on `created_record_id`, "
        f"keyed by the local handle: {created}")
    assert not created[ns["new_row"]].startswith(NEW_RECORD_PREFIX), (
        "…and the id it landed as is a REAL one, not the handle echoed back")

    # LD-473 AC6 — a Text cell off `search_records` is a SEGMENT ARRAY, and the recipe prints
    # it. This is the shape the shipped cell-shapes section quotes; it runs here.
    cells = ns["first_cells"]
    segments = [value for value in cells.values()
                if isinstance(value, list) and value and isinstance(value[0], dict)
                and "text" in value[0]]
    assert segments, (
        f"no cell in the read came back as a segment array — the recipe's own printout is "
        f"then teaching a shape the fixtures do not carry: {cells}")
    for segment_array in segments:
        for segment in segment_array:
            assert "text" in segment and "type" in segment, segment
    # …and the plainest of them is the `text`-typed one the shipped section quotes. (An Email
    # cell's segments are `url`-typed and carry a `link` beside it — the same array shape, one
    # kind along, which is why the assertion is over the SHAPE and the kind is checked here.)
    assert {segment["type"] for array in segments for segment in array} <= {"text", "url"}, (
        segments)

    # The WRITE client made exactly one call PER FAMILY, and they are the batches the plan named.
    ops = sorted(call[0] for call in OfflineBaseWriteClient.calls)
    assert ops == ["batch_create_records", "batch_update_records"], ops

    # …and the guard really did read: the anchor before and after, plus the tier-2 precondition.
    read_ops = [call[0] for call in OfflineBaseReadClient.calls]
    assert read_ops.count("list_tables") >= 3, read_ops
    assert "search_records" in read_ops, (
        "the value precondition must re-read the cells the update writes")


def _check_field_migration(ns):
    """LD-291 — the guided column-type migration, end to end on the shipped engines.

    Everything above the transport is real: the planner, both plan gates, the loss preview, the
    consent fence, the record engine's compare-and-swap and write-effect oracle, and the
    verification that stands between the copy and the delete. So this asserts the properties the
    recipe teaches rather than the doubles:

    * **the refusal arm really refused** — a column of prose is not a column of numbers, and it
      was decided at plan time with nothing sent;
    * the plan is the five steps in apply order and its destructive step carries the **same**
      loss preview a ``delete_field`` plan carries;
    * the whole sequence landed, in order, and the surviving column carries the OLD name with
      the NEW identity — which is only true if the copy was verified, the delete landed and the
      rename landed.
    """
    plan, log = ns["plan"], ns["log"]
    from larkdocio.base import field_migration as fm

    assert [step.kind for step in plan.steps] == list(fm.MIGRATION_STEPS)
    assert plan.staging_name != "Text 2"
    assert plan.loss_preview["columns"][0]["cells_with_data"] == len(plan.values), (
        "the destructive step's preview must count the same cells the copy is carrying")
    assert [entry.outcome for entry in log.entries] == ["applied"] * 5, log.to_dict()
    assert log.halt is None

    ops = [call[0] for call in OfflineBaseSchemaClient.calls]
    assert ops == ["create_field", "delete_field", "update_field"], ops
    assert [call[0] for call in OfflineBaseWriteClient.calls] == ["batch_update_records"]

    names = ns["names"]
    assert "Text 2" in names and plan.staging_name not in names, names


def _check_base_schema(ns):
    """LD-263 — the Base STRUCTURAL handshake, end to end on the shipped engine.

    Everything above the transport is real: the plan gate, the O3″ disclosure, the bounded
    settle and the read-back rule. So this asserts the properties the recipe teaches:

    * the previewer costs nothing and the plan names how each op will be **verified**;
    * every entry discloses that it carries **no** revision guard;
    * the copy really **settled** — the read double answers ``1254036`` once, so a recipe that
      had dropped the settle would report ``applied-unverified`` here instead of ``applied``;
    * ``created_app_token`` is the handle the recipe then reads the cloned columns through.
    """
    from larkdocio.base.schema_plan import NO_APP_REVISION_CAS

    plan, log = ns["plan"], ns["log"]
    assert [entry.op for entry in plan.entries] == [
        "rename_app", "create_table", "create_table", "batch_create_tables", "rename_table"]
    assert plan.api_call_count == 5, (
        "five writes — the kit rides the create it is on, and LD-322's `primary_field_name=` "
        "create is one call too, not a create plus a rename")
    assert plan.read_calls == 7, (
        "one read-back per entry, PLUS a field listing for EACH of the two creates that name "
        "their columns — a create carrying `fields` answers code:0 either way, so the columns "
        "are the only evidence, and the plan prices that before anything is sent")
    assert all(entry.read_back for entry in plan.entries), (
        "the plan must say how each op will be verified, before anything is sent")
    for entry in plan.entries:
        assert entry.revision_guard is None
        assert entry.revision_guard_disclosure == NO_APP_REVISION_CAS

    assert [entry.outcome for entry in log.entries] == ["applied"] * 5, log.to_dict()

    # LD-336 — the kitted create is verified by the created table's OWN field list, and the
    # first entry of the kit is that table's PRIMARY column (measured; probe ld336-02).
    kitted = log.entries[1]
    landed = kitted.read_back["columns"][0]
    assert landed["asked"] == ["Item", "Unit price"], landed
    assert not landed["missing"] and not landed["mismatched"], landed
    assert landed["primary"] == ["Item"], (
        "the kit's FIRST entry becomes the primary column, under the name the recipe gave")
    # LD-322 — `primary_field_name=` IS a one-entry kit, so it is verified the same way and
    # the column it names reads back as that table's primary one.
    named = log.entries[2].read_back["columns"][0]
    assert named["asked"] == ["Location"], named
    assert not named["missing"] and not named["mismatched"], named
    assert named["primary"] == ["Location"], (
        "`primary_field_name=` names the PRIMARY column, not an extra one")
    assert log.entries[3].read_back.get("columns") is None, (
        "and the batch verb makes no column claim: it authors none")

    copy_log = ns["copy_log"]
    copied = copy_log.entries[0]
    assert copied.outcome == "applied", copied.to_dict()
    assert copied.created_app_token == "appCOPYOFFLINE"
    assert copied.settle["status"] == "settled"
    assert copied.settle["attempts"] == 2, (
        "the double answers 1254036 once, so a real settle takes exactly two reads — a recipe "
        "that returned on the first would have failed above")

    # LD-473 AC1 — the recipe headed "the structural handshake" now performs one: step 0 CREATES
    # a Base, with `folder_token=` on the call, and the token it hands back is what the seeding
    # read-out below is taken through. The recipe carried this heading for two releases while
    # its sample never made a Base at all.
    birth = ns["birth"]
    assert [entry.op for entry in birth.entries] == ["create_app"], birth.to_dict()
    assert birth.entries[0].outcome == "applied", birth.to_dict()
    assert ns["new_app_token"] == birth.entries[0].created_app_token, (
        "the recipe must capture the created Base's token — a token it drops is a Base nothing "
        "can name and nothing can clean up")
    assert ns["birth_plan"].entries[0].request.arguments.get("folder_token") == ns["FOLDER_TOKEN"], (
        "`folder_token=` must reach the request, not merely the prose: it decides where the "
        "Base lands and therefore who can find it")
    assert ns["birth_plan"].entries[0].request.arguments.get("time_zone"), (
        "and the zone is declared at create, which is the one place Lark accepts one")

    # LD-473 AC4 — and the recipe READS BACK what the create produced, rather than asserting
    # that a new Base is empty. A new Base is not empty; the read-out is the disclosure.
    read_ops = [call for call in OfflineBaseReadClient.calls if call[0] == "list_tables"]
    assert any(call[1] == ns["new_app_token"] for call in read_ops), (
        f"the recipe never lists the tables of the Base it just made: {read_ops}")

    ops = [call[0] for call in OfflineBaseSchemaClient.calls]
    assert ops == ["create_app", "rename_app", "create_table", "create_table",
                   "batch_create_tables", "rename_table", "copy_app", "create_field",
                   "delete_field"], ops
    assert OfflineBaseSchemaClient.calls[6][-1] is True, (
        "the recipe's copy must carry without_content=True — the schema-only clone it teaches")

    # LD-319 AC1 — the DELETE portion, which the recipe's prose has always promised and its
    # code did not carry. Three facts, and each is a thing the consumer had to learn by
    # trial: the destructive plan really scanned (a plan built WITHOUT `read_client=` refuses
    # instead), consent was minted from that same plan, and the column is gone on read-back.
    loss_plan, gone = ns["loss_plan"], ns["gone"]
    entry = loss_plan.entries[0]
    assert entry.op == "delete_field" and entry.refusal is None, entry.to_dict()
    assert entry.loss_preview is not None and loss_plan.read_calls >= 1, (
        "a destructive plan is only honest if it ENUMERATED the loss — which costs reads")
    assert gone.entries[0].outcome == "applied", gone.to_dict()
    assert not any(field.field_name == "Scratch"
                   for field in ns["read"].list_fields(ns["app_token"],
                                                       ns["first_table"].table_id)), (
        "the read-back is the only proof a delete landed; the column must be ABSENT")


def _check_base_delete_lifecycle(ns):
    """LD-466 — the disposables doctrine, made followable on the Base surface.

    Four properties, each one a thing the recipe would otherwise be teaching on trust:

    * the delete really ran, and it ran **in the `finally`** — so a body that raised would still
      have cleaned up (the double records every call it was handed);
    * the confirmation is a **read of a real refusal**, not a printed hope: the read double stops
      serving a trashed Base and answers ``1002``, so ``confirmed_gone`` can only be ``True`` if
      the recipe actually asked;
    * the confirmation is asked of the **bitable** side. Drive metadata keeps resolving a trashed
      Base, so a recipe that confirmed there would confirm nothing;
    * the **second** delete raises rather than reporting success — the verb is not idempotent, and
      that one outcome is exactly what ``base_is_gone`` exists to forgive.
    """
    from larkdocio.base.schema_client import base_is_gone

    assert ns["confirmed_gone"] is True, (
        "the recipe's own confirmation step reported the Base was NOT gone — the read double "
        "answers 1002 for a trashed app_token, so this can only fail if the recipe skipped it")
    ops = [call[0] for call in OfflineBaseSchemaClient.calls]
    assert ops.count("delete_base") == 2, (
        f"the recipe must delete once in the `finally` and once more to show the route does not "
        f"lie about a repeat: {ops}")
    assert ops[0] == "create_app" and ops[1] == "delete_base", ops
    reads = [call for call in OfflineBaseReadClient.calls if call[0] == "get_app"]
    assert reads, "the proof is a get_app on the BITABLE side, not a Drive metadata query"
    assert base_is_gone(type("E", (), {"code": 1002})()), (
        "the code the double answers must be one the shipped predicate forgives, or the recipe "
        "would be teaching against a fiction")


def _check_base_row_hierarchy(ns):
    """LD-296 — the row tree, end to end, and the honesty that is the point of it.

    The engine above the transport is the shipped one: the plan gate, the view family's own
    read-back and the tree reconstruction all run for real. So this asserts what the recipe
    teaches:

    * the hierarchy column is authored through the ORDINARY field family and the view write
      is verified by a READ-BACK rather than by a response code;
    * the tree really came back as a tree — three levels, depth 0/1/2, in depth-first order —
      and it NAMES the view it read the hierarchy from;
    * the parent edges were written as ordinary record cells: no hierarchy verb appears in the
      write client's call log at all;
    * the cycle disclosure fires, names the rows, and REFUSES NOTHING — which is the ruling
      this whole recipe exists to make legible.
    """
    from larkdocio.base import hierarchy as hier

    tree = ns["tree"]
    assert tree.configured is True
    assert tree.source == hier.SOURCE_VIEW_HIERARCHY_CONFIG
    assert ns["view_id"] in tree.source_detail, tree.source_detail
    root, child, leaf = ns["root"], ns["child"], ns["leaf"]
    assert [tree.row(r).depth for r in (root, child, leaf)] == [0, 1, 2]
    order = [row.record_id for row in tree.rows]
    assert order.index(root) < order.index(child) < order.index(leaf)
    assert tree.row(child).parent_ids == (root,)
    assert tree.row(leaf).placement == hier.PLACEMENT_CHILD

    # The write side used NOTHING but ordinary record creates.
    ops = {call[0] for call in OfflineBaseWriteClient.calls}
    assert ops == {"create_record"}, ops

    # The view write earned its word from a read-back, not from a code.
    assert ns["log"].entries[0].outcome == "applied"
    assert ns["log"].entries[0].read_back["persisted_hierarchy_config"] == {
        "field_id": ns["parent_field_id"]}

    # And the disclosure discloses without refusing.
    warning = ns["warning"]
    assert warning["refused"] is False and warning["checked"] is True
    assert warning["cycle"]["rows"][0] == root
    assert set(warning["cycle"]["rows"]) == {root, child, leaf}


def _check_base_two_filters(ns):
    """LD-264 — the two filter dialects side by side, and the persistent one verified.

    The engine above the transport is the shipped one: the plan gate, the family's own
    read-back and the semantic comparison all run for real. So this asserts what the recipe
    teaches:

    * the SAME FilterSpec serialises two ways, keyed by name and by id, and the two are
      different types — a consumer who read this recipe cannot cross them by accident;
    * **the read half now TRAVELS (LD-314)**: the recipe's filtered read really came back
      narrower than its unfiltered one, and every row it returned satisfies the filter — so the
      recipe cannot teach a filtered read while quietly receiving the whole table, which is
      exactly what an ignored body key (R12) would look like;
    * the persistent filter really round-tripped: `echoes` is True, and it is True **through**
      the server's own `condition_id` / `field_type` additions, which the double really adds;
    * `applied` was earned by a read-back rather than by a response code;
    * the view was created and deleted through the plan gate, in that order.
    """
    from larkdocio.base.view_filters import SearchFilter, ViewFilterInfo

    wanted, persistent = ns["wanted"], ns["persistent"]
    assert isinstance(persistent, ViewFilterInfo)
    assert isinstance(ns["search_filter"](wanted), SearchFilter)
    assert "field_name" in ns["search_filter"](wanted).to_dict()["conditions"][0]
    assert "field_id" in persistent.to_dict()["conditions"][0]

    everything, subset, column = ns["everything"], ns["subset"], ns["column"]
    assert everything, "the recipe's unfiltered control read returned nothing to compare against"
    assert ns["none_at_all"] == [], (
        f"the recipe's match-nothing filter returned {len(ns['none_at_all'])} rows — a filtered "
        "read that returns the whole table is exactly what an IGNORED filter (R12) returns, and "
        "this line is the one that shows a reader the difference")
    assert {r.record_id for r in subset} <= {r.record_id for r in everything}
    texts = [OfflineBaseReadClient._cell_text(record, column) for record in subset]
    assert all(texts), "`isNotEmpty` returned a row whose cell is empty"
    assert texts == sorted(texts, reverse=True), (
        "the recipe asked for `desc` and the rows came back in some other order")

    entry = ns["log"].entries[0]
    assert entry.outcome == "applied", entry.to_dict()
    assert entry.read_back["echoes"] is True
    assert entry.read_back["persisted"] == persistent.to_dict()
    assert entry.read_back["normalized_away"] == ["condition_id", "field_type"], (
        "the read-back must state which of the server's own keys it dropped — a comparison "
        "that silently ignored unknown keys would pass a filter the server rewrote")

    ops = [call[0] for call in OfflineBaseSchemaClient.calls]
    assert ops == ["create_view", "update_view", "delete_view"], ops
    assert not OfflineBaseReadClient.views, "the recipe tidies the view it made away"


def _check_base_field_creation(ns):
    """LD-283 — the field family, end to end on the shipped engines.

    The pairing registry, both plan gates, the local pair check and the field family's own
    read-back all run for real, so this asserts what the recipe teaches:

    * the type int came from :data:`FIELD_PROPERTY_SHAPES` rather than from a guess, and the
      column that came back really carries the ``property`` the create configured — a link
      column that forgot its target is not the column that was authored;
    * ``update_field`` renamed WITHOUT changing the kind;
    * the conversion was **previewed only**: ``schema_dry_run`` spent nothing, and the plan
      states the cell effect before a byte is sent.
    """
    from larkdocio.base.field_authoring import FIELD_PROPERTY_SHAPES

    log, renamed = ns["log"], ns["renamed"]
    assert [entry.outcome for entry in log.entries] == ["applied", "applied"], log.to_dict()
    assert renamed.entries[0].outcome == "applied", renamed.to_dict()

    status = ns["status"]
    assert status.type == FIELD_PROPERTY_SHAPES["SingleSelect"].field_type == 3
    assert status.ui_type == "SingleSelect"

    fields = {f.field_name: f for f in
              OfflineBaseReadClient(
                  "cli_read_offline", "read-secret-offline").list_fields(
                      ns["app_token"], ns["table_id"])}
    assert "Workflow status" in fields, sorted(fields)
    owner = fields["Owner"]
    assert owner.type == 18 and owner.property is not None, (
        "a link column must read back knowing where it points")
    assert owner.property.table_id == ns["target_table_id"]

    # The conversion was a QUESTION, not an act: no convert_field reached the client.
    ops = [call[0] for call in OfflineBaseSchemaClient.calls]
    assert ops == ["create_field", "create_field", "update_field"], ops
    assert ns["preview"].entries[0].conversion["from"] == "Text"
    assert ns["preview"].entries[0].conversion["to"] == "Barcode"


def _check_base_views(ns):
    """LD-283 — the view lifecycle, end to end, and the honesty that is the point of it.

    * every op went through the plan gate and earned ``applied`` from a **read-back**;
    * the rename, the hide and the clear all ride the family's ONE patch op, ``update_view`` —
      which is why grouping and a saved sort have no knob to find, and why the hidden set
      needed no new op to gain one (LD-438);
    * **the CLEAR really clears**, and it is proven where it matters: ``[]`` reads the view's
      ``property`` back as ``null`` and the read-back reports that as ``applied``, not as a
      swallowed write. An implementation that treated ``[]`` as "not asked for" would leave
      the columns hidden and still print ``applied`` here;
    * ``delete_view`` took **no consent token**: the destructive fence is for ops that lose
      data, and a view holds none. A recipe that had needed one would have raised here;
    * the view the recipe made is tidied away.
    """
    made, renamed, gone = ns["made"], ns["renamed"], ns["gone"]
    hidden, shown = ns["hidden"], ns["shown"]
    assert made.entries[0].outcome == "applied", made.to_dict()
    assert ns["view_id"].startswith("vew")
    assert ns["plan"].entries[0].op == "update_view", ns["plan"].to_dict()
    assert renamed.entries[0].outcome == "applied", renamed.to_dict()
    assert gone.entries[0].outcome == "applied", gone.to_dict()

    assert hidden.entries[0].outcome == "applied", hidden.to_dict()
    assert hidden.entries[0].read_back["persisted_hidden_fields"] == ns["columns"][1:]
    assert shown.entries[0].outcome == "applied", shown.to_dict()
    assert shown.entries[0].read_back["cleared"] is True
    assert shown.entries[0].read_back["persisted_hidden_fields"] in (None, [])

    ops = [call[0] for call in OfflineBaseSchemaClient.calls]
    assert ops == ["create_view", "update_view", "update_view", "update_view",
                   "delete_view"], ops
    assert not OfflineBaseReadClient.views, "the recipe tidies the view it made away"

    # The kanban really was created as a kanban — the allow-list let the right thing through.
    assert OfflineBaseSchemaClient.calls[0][-1] == "kanban", OfflineBaseSchemaClient.calls[0]


def _check_base_media(ns):
    """LD-283 — the attachment out-of-band leg, end to end.

    The shipped module runs for real above the transport: the ``parent_type`` allow-list, the
    ``sha256`` over the bytes as sent, the scrub projection and
    :func:`~larkdocio.base.media.verify_round_trip`'s digest comparison. So this asserts the
    properties the recipe teaches:

    * the round trip is proven **by hash** — the digest ``verify_round_trip`` returned is the
      digest of the bytes that went up, and it is not the file-token or a status code;
    * the upload minted **permanent residue**, and the ledger has it: the disclosure in the
      recipe is a fact about a real run, not a formality;
    * the cell that came back really carried the two signed links, and the scrub really
      dropped them — a check against a cell that never had them would prove nothing;
    * nothing this recipe printed contains a signed link.
    """
    from larkdocio.base.media import EPHEMERAL_ATTACHMENT_KEYS, sha256_of

    uploaded, cell = ns["uploaded"], ns["cell"]
    assert uploaded.sha256 == sha256_of(ns["payload"])
    assert ns["verify_round_trip"](uploaded, ns["downloaded"]) == uploaded.sha256
    assert [entry.outcome for entry in ns["log"].entries] == ["applied"], ns["log"].to_dict()

    assert set(EPHEMERAL_ATTACHMENT_KEYS) <= set(cell), (
        "the read-back must carry the signed links, or the scrub below proves nothing")
    scrubbed = ns["scrub_attachment_cell"](cell)
    assert not set(EPHEMERAL_ATTACHMENT_KEYS) & set(scrubbed), scrubbed
    assert scrubbed["file_token"] == uploaded.file_token
    assert "sign=" not in ns["describe_attachment_cell"](cell)

    minted = OfflineBaseMediaClient.minted
    assert [(token, parent_type) for token, parent_type, _node in minted] == [
        (uploaded.file_token, "bitable_file")], minted
    assert minted[0][2] == ns["app_token"], "parent_node must be the APP token"
    assert [call[0] for call in OfflineBaseMediaClient.calls] == [
        "upload", "download", "permalink"]

    # LD-450 — the address a person can be sent. Two properties the recipe teaches: the link
    # is the file's OWN address (so it carries the token, and it is neither of the cell's two
    # signed links), and asking for it minted nothing — a metadata query is a read.
    link = ns["link"]
    assert link.file_token == uploaded.file_token
    assert link.url.endswith(f"/file/{uploaded.file_token}")
    assert link.title == "q3-report.csv"
    assert "sign=" not in link.url
    assert link.url not in (cell.get("url"), cell.get("tmp_url"))
    assert len(OfflineBaseMediaClient.minted) == 1, (
        "a permalink query must mint no residue — it is a read")


def _check_base_link_resolution(ns):
    """LD-283 — the two halves of a link question, and the rule that keeps them apart.

    The whole point is that the recipe demonstrates the trap rather than describing it: one
    linked record is gone while its target **table** is alive, so

    * ``dangling_link_columns`` is **empty** — correctly, because it reads the schema — and a
      consumer who stopped there would conclude nothing was broken;
    * ``resolve_links=True`` finds the dead row and types it ``dangling``, while the live one
      resolves to the target's **primary field text** rather than to its id;
    * the cost is **disclosed**: the resolution really made extra calls and says how many
      against which target tables.
    """
    from larkdocio.base.link_resolution import LINK_DANGLING, LINK_RESOLVED

    document, resolved = ns["document"], ns["resolved"]
    assert document.link_resolution is None, "the default read must resolve nothing"
    for table in document.tables:
        assert table.dangling_link_columns == (), (
            "the target TABLE is alive, so the free reading must stay empty — that is the "
            "trap this recipe exists to show")

    resolution = resolved.link_resolution
    assert resolution is not None and resolution.api_calls > 0, (
        "an opt-in that cost nothing would mean it never ran")
    assert resolution.tables, resolution
    states = {link.record_id: link.state for link in resolution.records.values()}
    assert LINK_RESOLVED in states.values() and LINK_DANGLING in states.values(), states
    assert states["recDELETEDLONGAGO"] == LINK_DANGLING, states
    assert [link.record_id for link in resolution.dangling] == ["recDELETEDLONGAGO"]

    live = [link for link in resolution.records.values() if link.state == LINK_RESOLVED][0]
    assert live.text and live.text != live.record_id, (
        "a resolved link must render the target's primary field, not the id back")
    assert "extra API call" in resolution.disclosure, resolution.disclosure


def _check_base_computed_provenance(ns):
    """LD-283 — the provenance reading, and the attribution that is half of it.

    The captured Base carries a real Lookup column, so this is the shipped reading over a
    payload Lark actually returned:

    * the table it rolls up from **is** reported;
    * the three keys the transport does not carry come back in ``unavailable`` — as a NAMED
      absence, never as an empty value that would read as *"it aggregates nothing"*;
    * the note attributes the gap rather than leaving it looking like a defect;
    * and the whole reading cost no extra call.
    """
    from larkdocio.base.computed import TRANSPORT_DROPPED_KEYS

    document = ns["document"]
    lookups = [column for table in document.tables for column in table.computed_columns
               if column.ui_type == "Lookup"]
    assert lookups, "the captured Base carries a Lookup column — the reading found none"
    lookup = lookups[0]
    assert lookup.rolls_up_from_table, lookup
    assert set(lookup.unavailable) == set(TRANSPORT_DROPPED_KEYS), lookup.unavailable
    assert lookup.rolls_up_from_field is None and lookup.aggregation is None
    assert "Lark returns all three" in lookup.note, lookup.note

    ops = [call[0] for call in OfflineBaseReadClient.calls]
    assert set(ops) <= {"get_app", "list_tables", "list_fields", "search_records"}, ops


def _check_base_bulk_import(ns):
    """LD-283 — the free dry-run audit, and the arithmetic it is supposed to show.

    ``dry_run`` is the shipped previewer and it really costs nothing, so this asserts the three
    numbers the recipe promises: the unchunked default is **one** call, ``records_per_call=25``
    turns 60 adds into **three**, and each entry names the call it rides in. The apply that
    follows lands them all.
    """
    one_call, chunked = ns["one_call"], ns["chunked"]
    assert one_call.api_call_count == 1, one_call.to_dict()
    assert chunked.api_call_count == 3, chunked.to_dict()
    assert sorted({entry.call_index for entry in chunked.entries}) == [0, 1, 2]
    assert len([e for e in chunked.entries if e.call_index == 0]) == 25
    assert len(chunked.entries) == 60 and not chunked.refusals

    # THE PREVIEW IS FREE: every write call in the log came from apply, never from dry_run.
    log = ns["log"]
    assert len(log.applied) == 60, log.to_dict()
    assert [call[0] for call in OfflineBaseWriteClient.calls] == ["batch_create_records"] * 3


def _check_read_folder(ns):
    """LD-327 (the Drive spec § F1-S5) — the folder read, RUN offline over the staged Drive double.

    The double (``OfflineDriveClient``) returns a fixed two-child folder — one ``docx`` to read
    and one ``file`` to disclose — and the whole orchestration runs for real: the walk, the
    ``type``→reader dispatch, the docx read through the shipped read pipeline, the
    ``children == read + disclosed`` invariant, and the one-document render. Only the two Drive
    HTTP legs (listing + title) and the docx HTTP boundary are replaced.
    """
    from larkdocio.drive.read import FolderRead

    result = ns["result"]
    assert isinstance(result, FolderRead), type(result)
    # The headline promise, asserted inside the recipe too (so the recipe itself is the proof).
    assert result.accounted(), "the walk dropped or double-counted a child"

    reads, skips = result.reads, result.skips
    assert len(reads) == 1, [o.type for o in reads]
    assert reads[0].type == "docx" and reads[0].markdown, reads[0]
    assert len(skips) == 1, [o.type for o in skips]
    assert skips[0].type == "file", skips[0]
    assert skips[0].skip.reason, "a skipped child must carry a reason — never a silent drop"

    markdown = ns["markdown"]
    for region in ("## Folder tree", "## Documents", "## Not read"):
        assert region in markdown, f"the rendered folder is missing {region!r}"
    assert "Q3 launch" in markdown, "the folder title the double serves is missing"
    assert "diagram-source.excalidraw" in markdown, "the disclosed file child is not named"

    # The network was the two Drive legs only — proof the read ran offline through the double.
    kinds = {call[0] for call in OfflineDriveClient.calls}
    assert kinds == {"list", "name"}, OfflineDriveClient.calls


def _check_folder_ledger(ns):
    """LD-474 — the ledger block: ``walk_folder`` + ``client=`` + ``folder_manifest``, RUN.

    Round 4 recorded that these two legs had **zero** guide mentions and that the result shape
    and the ``client=`` idiom were demonstrated together nowhere; this block is that
    demonstration, so it has to execute rather than compile. The post-conditions below are the
    claims the surrounding prose makes — that a manifest row carries the listing's identity
    fields and a revision-with-a-reason, and that it carries **no** size or digest of any kind.
    """
    import json

    from larkdocio.drive.manifest import REVISION_AVAILABLE, REVISION_UNAVAILABLE
    from larkdocio.drive.models import FolderWalk

    walk = ns["walk"]
    assert isinstance(walk, FolderWalk), type(walk)
    assert walk.complete is True, walk.truncations
    assert walk.by_type() == {"docx": 1, "file": 1}, walk.by_type()
    # `.children` is the shape the prose names, and `.child` is the listing row under it.
    assert [walked.child.type for walked in walk.children] == ["docx", "file"]

    # `client=` really carried: read_folder was handed the client the recipe built, so the walk
    # ran twice over ONE double and no second client was constructed behind the caller's back.
    assert ns["result"].accounted()

    manifest = ns["manifest"]
    assert json.loads(json.dumps(manifest)) == manifest, "the manifest is not plain JSON types"
    rows = {row["type"]: row for row in manifest["children"]}
    assert set(rows) == {"docx", "file"}, sorted(rows)

    for kind, row in rows.items():
        # The free identity fields the prose promises on EVERY child.
        for key in ("token", "title", "type", "modified_time", "created_time", "owner_id"):
            assert row.get(key), f"{kind} row is missing {key!r}: {row}"
        assert row["modified_time"].isdigit(), (
            f"{kind}'s modified_time is not the epoch-second string the guide's table shows: "
            f"{row['modified_time']!r}")
        # THE ABSENCE, held: the guide says a ledger cannot compare content identity here.
        for absent in ("size", "digest", "sha256", "etag", "checksum", "content_hash", "md5"):
            assert absent not in row, (
                f"a {absent!r} key appeared on a {kind} row — the guide's 'what you cannot "
                f"build on' list is now wrong and must be re-measured live")

    assert rows["docx"]["revision"]["availability"] == REVISION_AVAILABLE, rows["docx"]
    assert rows["file"]["revision"]["availability"] == REVISION_UNAVAILABLE, rows["file"]
    assert rows["file"]["revision"]["detail"], "an unavailable revision must carry its reason"
    # The per-surface table ships INSIDE the sidecar, which is what the prose tells a consumer.
    assert manifest["revision_sources"]["docx"]["anchor"] == "document.revision_id"


def _check_revision_change_detector(ns):
    """LD-474 — the ``revision_id`` change detector, RUN offline end to end.

    The whole loop is the shipped code: the cheap metadata anchor, the ledger branch, the read
    that only happens on a moved number, the inert-poll assertion the recipe makes about
    itself, and the demonstration edit through the ordinary ``dry_run`` → ``apply`` gate. Only
    the HTTP boundary is a double — and the double advances the document's revision on a write
    exactly as Lark does, which is what makes the *"moved?"* line falsifiable rather than
    decorative.
    """
    before, after = ns["current"], ns["after"]
    assert isinstance(before, int) and before >= 1, before
    assert after == before + 1, (
        f"one authored paragraph moved the revision {before} → {after}; the recipe claims a "
        f"single edit advances it, and the live gate measured 1 → 2")
    assert ns["log"].applied, "the demonstration edit landed nothing, so nothing was detected"

    # The ledger really round-tripped through a file: the recipe writes it, so a second run of
    # the same script takes the unchanged branch — which is the loop's whole point, and is why
    # the demonstration leg reads its own tree instead of borrowing one from a branch.
    ledger_path = ns["ledger_path"]
    assert ledger_path.exists(), "the recipe never wrote its ledger"
    import json as _json

    assert _json.loads(ledger_path.read_text(encoding="utf-8"))[ns["doc_token"]] == before

    # THE COST CLAIM, checked rather than asserted in prose: the DECIDING call is the cheap
    # metadata one, and the inert-poll claim is a third one that must not have moved anything.
    calls = [call[0] for call in ns["client"].calls]
    assert calls[0] == "read_document_revision", calls
    assert calls.count("read_document_revision") == 3, calls
    assert "get_docx_content" in calls, calls


def _check_pin_a_named_version(ns):
    """LD-409 — the named-version pin, RUN offline over the staged Drive doubles.

    Only the two HTTP boundaries are replaced (the create and the listing). Everything the
    recipe teaches runs for real: the ``obj_type`` / ``name`` gates, the ``version`` → ``token``
    rename, the ONE epoch-second conversion, the newest-first sort, and the duplicate-name echo
    the double reproduces because Lark does it.
    """
    from larkdocio.drive.versions import Version, VersionListing
    from larkdocio.drive.versions_write import CreatedVersion

    created = ns["created"]
    assert isinstance(created, CreatedVersion), type(created)
    # THE PAIRING is the recipe's whole point: a name is not enough on its own.
    name, token, revision = ns["name"], ns["version_token"], ns["revision"]
    assert (name, token, revision) == created.triple
    # The pairing is the DOCUMENT's head revision, read immediately before the create — so it
    # is the store's own number, never a constant the harness chose (LD-471).
    assert revision == OfflineDocxReadClient.documents.for_token(ns["doc_token"]).revision, (
        revision)
    assert created.revision_note is None
    # The CREATE echo carries no update_time — reported as absent, never defaulted.
    assert created.version.update_time is None and created.version.updated_at is None

    listing = ns["listing"]
    assert isinstance(listing, VersionListing)
    assert ns["names"] == ["V1.3"], ns["names"]
    assert all(isinstance(version, Version) for version in listing)
    # The one honest conversion ran, and it is UTC-anchored because epoch is.
    import datetime

    assert listing[0].created_at.tzinfo is datetime.timezone.utc

    assert [call[0] for call in OfflineDriveVersionsWriteClient.calls] == ["create"]
    assert ("versions", ns["doc_token"]) in OfflineDriveClient.calls


def _check_grant_a_human_access(ns):
    """LD-432 — the access lifecycle, RUN offline over the staged Drive double.

    Only the HTTP boundary is replaced. The grantee gate, the wire paths and parameters, the
    one-key-per-call PATCH sequence and — the thing this surface exists to get right — the
    **read-back** that decides ``stored`` are all the shipped code running for real.
    """
    from larkdocio.drive.access import AccessOutcome, CopyPermissions, MemberListing

    granted = ns["outcome"]
    assert isinstance(granted, AccessOutcome), type(granted)
    # The grant is judged by the member READ, not by the call: stored is the two agreeing.
    assert granted.stored is True and granted.stored_perm == "full_access"
    assert granted.open_id == OfflineDriveAccessWriteClient.GRANTEE_ID

    listing = ns["listing"]
    assert isinstance(listing, MemberListing), type(listing)
    # THE TRAP, run rather than quoted: the owner is not a member row.
    assert listing.owner_id == OfflineDriveAccessWriteClient.OWNER_ID
    assert OfflineDriveAccessWriteClient.OWNER_ID not in [m.member_id for m in listing.members]

    # LD-456 — the SAME shipped code, addressed at two other object types and once through a
    # URL that names no type at all. Run, not quoted: the type resolution, the wire params and
    # the read-back are the library's, and only the HTTP boundary is the double's.
    assert ns["on_the_base"].stored is True and ns["on_the_base"].stored_perm == "edit"
    assert ns["on_the_sheet"].stored is True and ns["on_the_sheet"].stored_perm == "view"
    assert isinstance(ns["from_a_link"], MemberListing)
    assert ns["from_a_link"].file_token == ns["base_app_token"], (
        "the url's token is what the call addressed — one parse, no hand-rolled split")

    result = ns["result"]
    assert isinstance(result, CopyPermissions), type(result)
    assert result.stored is True
    assert [(s.key, s.stored) for s in result.settings] == [
        ("copy_entity", "anyone_can_view"), ("security_entity", "anyone_can_view")]

    # The lifecycle really ran in both directions and ended empty — the revoke leaves no
    # tombstone, which is the half a grant-only surface could not show.
    methods = [call[0] for call in OfflineDriveAccessWriteClient.calls]
    assert "POST" in methods and "PUT" in methods and "DELETE" in methods and "PATCH" in methods
    assert ("resolve", "someone@example.com") in OfflineDriveAccessWriteClient.calls
    roster = OfflineDriveAccessWriteClient.members[ns["doc_token"]]
    assert roster == {}, f"the revoke left a member behind: {roster}"


def _check_diff_an_edition_against_head(ns):
    """LD-410 — the ledger recipe, RUN offline: create the pairing, then read BOTH ways.

    Only the transport is doubled. The pin gate, the pinned metadata half and its refusal to
    hand back a ``revision_id``, the parser, and the whole ``(name, token, revision)`` pairing
    are the shipped code running for real.
    """
    from larkdocio.read.history import HistoricalDocumentMeta, HistoricalReadRefusedError

    row = ns["ledger_row"]
    assert row["revision"] == ns["created"].triple[2], row
    assert row["token"] and row["name"] == "V1.3", row

    pinned = ns["pinned_meta"]
    assert isinstance(pinned, HistoricalDocumentMeta), type(pinned)
    assert pinned.document_revision_id == row["revision"]
    # THE FENCE: the metadata route ignores the pin, so this object has no revision to give.
    try:
        pinned.revision_id
    except HistoricalReadRefusedError:
        pass
    else:                                       # pragma: no cover - the fence is the point
        raise AssertionError("the pinned meta handed back a revision_id")
    # …while the HEAD read's revision_id is true and is the one the recipe prints.
    assert isinstance(ns["head_meta"].revision_id, int)

    assert isinstance(ns["changed"], bool)
    assert ns["then_markdown"] and ns["now_markdown"]

    # LD-471 — the recipe finishes its own title: a TEXTUAL diff, not a boolean. `diff` is
    # difflib's unified form over the two projections, and `changed` is derived FROM it.
    import difflib

    assert isinstance(ns["diff"], list), type(ns["diff"])
    assert ns["diff"] == list(difflib.unified_diff(
        ns["then_markdown"].splitlines(), ns["now_markdown"].splitlines(),
        fromfile=f"{row['name']} (revision {row['revision']})",
        tofile=f"head (revision {ns['head_meta'].revision_id})", lineterm="")), ns["diff"]
    assert ns["changed"] is bool(ns["diff"])

    # …and the BOUND CHECK ran before either content read was spent — the cheap metadata call
    # that is the only defence against an over-range pin silently answering head.
    assert ns["head_revision"] == ns["head_meta"].revision_id, ns["head_revision"]
    kinds = [call[0] for call in ns["reader"].calls]
    assert kinds.index("read_document_revision") < kinds.index("get_docx_content"), kinds

    # The pin reached the transport on the pinned read and NOT on the head read — the whole
    # capability in one assertion.
    reads = [call for call in ns["reader"].calls if call[0] == "get_docx_content"]
    assert len(reads) == 2, reads
    assert reads[0] == ("get_docx_content", ns["doc_token"], row["revision"]), reads[0]
    assert reads[1] == ("get_docx_content", ns["doc_token"]), reads[1]


def _check_create_a_folder(ns):
    """LD-467: the recipe really created a folder under the parent it named, and the answer it
    printed is the one the transport SERVED.

    Asserted on what the recipe produced rather than on its text: exactly one create reached
    the wire, it carried the caller's parent (never a default and never an empty string), and
    the url is the double's own — which is what proves the shipped code returns Lark's answer
    instead of assembling an address out of a host and a token.
    """
    created = ns["created"]
    assert created.token in OfflineDriveFoldersWriteClient.store
    name, parent = OfflineDriveFoldersWriteClient.store[created.token]
    assert (name, parent) == (created.name, created.parent_token)
    assert parent == ns["parent_token"], "the destination must be the caller's"

    assert OfflineDriveFoldersWriteClient.calls == [
        ("create_folder", created.name, ns["parent_token"])], (
        OfflineDriveFoldersWriteClient.calls)
    # the url is SERVED, not spelled here
    assert created.url == (
        f"{OfflineDriveFoldersWriteClient.host}/drive/folder/{created.token}")


@dataclass(frozen=True)
class RecipeSpec:
    """One recipe's execution spec: how to stage it + what it must have produced."""

    slug: str
    check: Callable[[dict], None]
    empty_document: bool = False
    #: stage a Base carrying a link column with one live and one dead target (LD-283) — the
    #: shape a pure-READ recipe about link resolution has to be handed, exactly as the mention
    #: recipe is handed a mention-bearing document.
    base_links: bool = False
    #: LD-445 — post-conditions for the recipe's SECOND and later python blocks, in document
    #: order, one callable per extra block. Each extra block runs in a namespace of **its
    #: own** (:func:`run_recipe_blocks`), so a recipe can teach a script that resumes in a
    #: later process. Empty for every single-block recipe, which is nearly all of them.
    extra_checks: tuple = ()
    #: LD-445 — this recipe writes an artefact, so it runs with the cwd moved to a scratch
    #: directory: a recipe that persists a file must not litter the repository (nor race
    #: another xdist worker), and the file it wrote is what the next block reads.
    persists_to_disk: bool = False
    #: LD-518 — this recipe reaches NOTHING: no client, no credential, no network, so it
    #: must not open with ``init_env(...)`` (see
    #: ``test_discovery_truth.test_ac4_every_recipe_opens_with_the_env_init_line``, whose
    #: reason is unchanged and whose conclusion this narrow class amends). The declaration is
    #: held honest by execution rather than by trust: every recipe already runs from a cwd
    #: with no ``.env`` in reach.
    needs_no_credentials: bool = False


#: Every recipe the guide ships must appear here — ``test_discovery_truth.py`` asserts
#: the mapping is 1:1 with the guide's ``### Recipe:`` headings, so a NEW recipe with no
#: execution spec (or a spec whose recipe was renamed away) reddens the suite.
RECIPE_SPECS = (
    RecipeSpec("download-a-docx-to-markdown", _check_docx_read,
               # LD-599 — block two is the one-call door, run in its own namespace.
               extra_checks=(_check_docx_read_single_call,)),
    RecipeSpec("read-a-sheet-to-markdown", _check_sheet_read),
    # LD-407 — the whole-workbook walk, given its own heading carrying the burn keywords
    # ("ghost", "workbook", "tab") so a consumer searching after a ghost-tab incident can
    # find it through guide_sections() by name, not only by reading the sheet-read recipe
    # end to end.
    RecipeSpec("ghost-tabs-read-a-whole-workbook-skipping-tabs-lark-refuses",
               _check_ghost_tabs_walk),
    # LD-152 — the standalone L2 fidelity read (F17/F19/F3): the export leg + the
    # title→sheet_id join, against a CAPTURED workbook (no live export in the suite).
    RecipeSpec("read-a-sheet-at-style-fidelity-the-l2-export-leg", _check_fidelity_read),
    # LD-251 — the Base read, over the committed captures of one real Base: objects first, then
    # the reading form both ways (a fresh read, and a re-render of what is already held).
    RecipeSpec("read-a-base-to-markdown", _check_base_read),
    # LD-327 — the Drive folder read: one link in, the whole tree read, the disclosure section
    # a consumer must trust, and the children == read + disclosed invariant, RUN offline over
    # the staged Drive double (a docx read + a file disclosed).
    # LD-474 — the ledger half of the same recipe: `walk_folder` and `folder_manifest` (0 guide
    # mentions before this), the `client=` construction idiom, and the change-detection fields
    # a manifest row actually carries. Run for real over the same double.
    RecipeSpec("read-every-document-in-a-folder", _check_read_folder,
               extra_checks=(_check_folder_ledger,)),
    # LD-474 — the change detector the library already had and never taught: revision_id as the
    # answer to "did this move since I last looked?", with the ledger branch, the inert poll and
    # the demonstration edit all executed. Named for the failure it cures.
    # LD-485 — the recipe's shipped code writes `ingest-ledger.json`; without this flag the
    # harness ran it in the repository's own cwd and littered the repo root every run.
    RecipeSpec(
        "you-re-ingested-a-document-that-never-changed-the-revision-id-change-detector",
        _check_revision_change_detector, persists_to_disk=True),
    # LD-409 — the named-version pin: create (with the head-revision pairing) then list back,
    # over the staged Drive doubles. Named for the failure it cures (D-60): a version name
    # that resolves to nothing later.
    RecipeSpec(
        "your-version-name-resolves-to-nothing-later-pin-a-named-version-and-record-the-"
        "revision-it-named",
        _check_pin_a_named_version),
    # LD-432 — WHO may use a document the app created: grant by email, lower, raise, revoke,
    # read the members WITH the owner, and move the two copy-lever keys. Named for the failure
    # it cures (D-60): a document only the app can use.
    RecipeSpec(
        "grant-a-human-access-and-who-can-already-read-a-document-the-app-just-created",
        _check_grant_a_human_access),
    # LD-410 — the other half of the same ledger: having recorded (name, token, revision),
    # READ AT THE REVISION and diff it against head. Named for what a consumer types after
    # being burned by a keystroke counter (D-60).
    RecipeSpec(
        "diff-a-named-edition-against-head-pin-a-semantic-version-not-a-keystroke-counter",
        _check_diff_an_edition_against_head),
    # LD-260 — the Base RECORD write handshake: snapshot -> edit -> dry_run -> apply, with the
    # client-side compare-and-swap and the write-effect oracle both running for real.
    RecipeSpec("the-base-write-handshake", _check_base_write),
    # LD-263 — the Base STRUCTURAL handshake: create / rename / copy an app, create and rename
    # tables, all behind the same plan gate, with the async copy's bounded settle and the
    # read-back rule both running for real.
    # LD-466 — the recipe's SECOND block: the whole-Base delete, in the create → use →
    # finally-delete → confirm-gone shape the disposables doctrine requires. A separate block
    # (and therefore a separate namespace) because it is a self-contained script a consumer
    # pastes on its own, not a continuation of the structural handshake above it.
    RecipeSpec("create-rename-and-copy-a-base-the-structural-handshake", _check_base_schema,
               extra_checks=(_check_base_delete_lifecycle,)),
    # LD-291 — the GUIDED COLUMN-TYPE MIGRATION: the five-step dance as one plan and one
    # consent, with the plan-time refusal shown beside it.
    RecipeSpec("change-a-column-s-type-the-guided-migration-do-not-hand-roll-this",
               _check_field_migration),
    # LD-264 — the two filter dialects, side by side: one model, two serialisers, and the
    # VIEW one verified by the engine's own read-back rather than by a response code.
    # LD-296 — the row tree: the self-link column, the view property that names it, three
    # ordinary record writes, the client-side depth-first read, and the cycle disclosure
    # that refuses nothing.
    RecipeSpec("build-and-read-a-row-tree-sub-items-and-the-two-shapes-lark-lets-you-build-that-no-tree-can-contain",
               _check_base_row_hierarchy),
    RecipeSpec("filter-a-base-two-ways-the-rows-a-read-returns-and-the-rows-a-person-sees",
               _check_base_two_filters),
    RecipeSpec("the-docx-write-handshake", _check_docx_write),
    # LD-518 — the read-only batch checker that runs BEFORE the authoring recipe below:
    # every inexpressible construct in one pass, with its line, instead of one round trip
    # per construct. Pure offline, no stage and no transport.
    RecipeSpec("find-every-construct-that-will-refuse-one-pass-not-one-attempt-each",
               _check_compose_check, needs_no_credentials=True),
    RecipeSpec("author-a-markdown-fragment-into-a-document", _check_authoring),
    # LD-469 — the fragment that does NOT fit in one call: the split by the shipped cap,
    # the inter-batch anchoring by a created id (the LAST TOP-LEVEL one, because the ids
    # come back in pre-order), and an ordering proof read off the document rather than off
    # the applies, which is the one thing a clean log cannot tell you.
    RecipeSpec("author-more-than-one-call-s-worth-of-blocks-the-50-per-call-cap-batched-in-order",
               _check_batched_authoring),
    # LD-192 — the diagram: a structured spec compiled through `larkdocio.mermaid`, landed as a
    # type-40 add_ons block, then REPLACED (delete + re-create), because no in-place update
    # exists. The spec measures the new block_id rather than repeating the claim.
    RecipeSpec("author-a-mermaid-diagram-and-change-one", _check_mermaid_authoring),
    # LD-154 (dogfood F15) — the verification comparator: authored-vs-read-back is
    # compose-equivalence, never string equality.
    RecipeSpec("verify-what-you-authored-compose-equivalence-not-string-equality",
               _check_comparator),
    # LD-236 — the id-anchored round trip, shown whole: project → edit → reconcile → compile
    # → the same dry_run/apply gate → verify by compose-equivalence. LD-422 renamed the
    # heading BY TASK (D-60, third application) without touching the mechanism in its body:
    # the consumer who hand-rolled a destructive rewrite searched "update" / "change" /
    # "edit an existing document" and this recipe answered to none of them.
    # LD-597 — …plus its checkbox leg as a SECOND block: the write-recipe router row promises
    # a worked flip and points here, so the flip lands inside this recipe rather than as a
    # recipe of its own. Its own namespace, its own post-condition, graded on the done bit.
    RecipeSpec(
        "update-an-existing-document-change-or-edit-many-blocks-at-once-without-re-authoring-it",
        _check_round_trip, extra_checks=(_check_todo_flip,)),
    # LD-422 — the canonical "copy this" script: the preamble every write consumer was
    # re-implementing (url → token → wiki hop → read → parse → project → edit → reconcile →
    # dry_run → apply), shipped once as a real recipe under this harness rather than as prose.
    # LD-445 — …and its FILE-FIRST VARIANT, the same flow with the read written to disk. A
    # second block of the SAME recipe on purpose: persistence is a mode of this recipe, never
    # a fifth editing path with a heading of its own.
    RecipeSpec("copy-this-the-end-to-end-update-script-from-url-to-applied-edit",
               _check_copy_this_update_script,
               extra_checks=(_check_copy_this_file_first,),
               persists_to_disk=True),
    # LD-471 — the RESTRUCTURE recipe. Delete-and-recreate is the contract (there is no move),
    # so the discipline it teaches is what a consumer would otherwise re-invent per incident:
    # comments first, insert before delete, LCS-preserved identity, and a read-back that
    # asserts the ORDER — the one thing a fully-applied log cannot tell you.
    # LD-575 — the table GROW: append a row to a table that already exists, through the gate.
    # It runs the identity claim rather than reading it — the ids the create provisioned are
    # still there, in order, with the appended row's cells behind them.
    RecipeSpec("add-a-row-to-a-table-that-already-exists", _check_table_grow),
    RecipeSpec("reorganise-a-document-there-is-no-move-so-a-reorder-is-delete-and-recreate",
               _check_restructure),
    # LD-509 — the repair leg for an interrupted rewrite: re-read, re-derive against the
    # FRESH read, and never build a delete for a block that is already gone. Named for the
    # disaster a burned consumer searches (D-60), and it runs twice so the harness executes
    # the convergence rather than reading the word "idempotent".
    RecipeSpec(
        "a-rate-limit-interrupted-your-rewrite-and-the-re-push-refuses-stale-anchor-the-"
        "idempotent-repair",
        _check_idempotent_repair),
    RecipeSpec("anchor-a-follow-up-by-a-created-block-id", _check_anchor_by_id),
    # LD-433 — the one authoring route that does NOT go through the plan gate, because it
    # needs bytes: create the image block, upload bound to it, PATCH to bind.
    # LD-509 — its SECOND block: a table cell as `parent_block_id`, with the cell id reached
    # from `created_block_ids` (the table's id) + one `get_block`, never from a position.
    RecipeSpec("put-an-image-in-a-document-create-upload-bind", _check_put_image_in_document,
               extra_checks=(_check_an_image_into_a_table_cell,)),
    # LD-470 — the attachment sibling, which the recipe above had NAMED for two releases while
    # shipping only an image sample. Its own trap is the WRAPPER: two blocks, and the id the
    # caller is handed is deliberately not the one that occupies the position they asked for.
    RecipeSpec("attach-a-file-to-a-document-the-attachment-card",
               _check_put_file_in_document),
    # LD-447 — the sheets twin, and the other route that does NOT go through a plan gate,
    # for the same reason: it needs bytes. One call, a fresh read-back for a verdict, and a
    # clear that is an ordinary "" value write.
    RecipeSpec("put-a-picture-in-a-cell-the-in-cell-image-write", _check_put_image_in_sheet),
    # LD-448 — the OTHER sheets picture route, and a different product: three beats, an
    # upload parented on the WORKBOOK, and a fresh query as the verdict for both the bind
    # and the removal.
    RecipeSpec("float-a-picture-over-a-single-cell-anchor-the-float-image-write",
               _check_put_float_image_in_sheet),
    # LD-434 — the two halves of "open the attached file": a file with an openable URL, and an anchor
    # on a run whose text is not that URL.
    # LD-464 added the SECOND block: the by-name lookup a caller runs BEFORE the upload,
    # because a second upload of the same name mints a second file object.
    RecipeSpec("link-a-file-from-a-sentence",
               _check_link_a_file_from_a_sentence,
               extra_checks=(_check_the_by_name_lookup_before_uploading,)),
    # LD-467 — the ONE R3 organize verb: create a folder under a parent, run over a double
    # that MODELS the duplicate-name behaviour rather than smoothing it.
    RecipeSpec(
        "create-a-folder-to-organise-into-and-the-one-thing-it-will-do-that-surprises-people",
        _check_create_a_folder),
    RecipeSpec("write-into-an-empty-document", _check_docx_write_empty, empty_document=True),
    # LD-472 — the two rich-cell kinds that shipped INVISIBLE: zero guide hits and no
    # __doc__, while their two siblings each had a recipe. Named for what a consumer types
    # ("hyperlink", "styled run", "cell") so the search that failed in dogfood round 4 lands.
    RecipeSpec("write-a-hyperlink-and-a-styled-run-into-a-cell", _check_rich_cell_write),
    # LD-229 — the name lookup, shown where its one shipped consumer is: a sheet-cell mention.
    RecipeSpec("author-a-sheet-cell-that-mentions-a-teammate", _check_name_lookup_mention),
    RecipeSpec("the-sheets-write-handshake", _check_sheets_write),
    # LD-176 — the disposables doctrine, made followable: the shipped create/delete pair in
    # the create → use → finally-delete → confirm-gone shape the doctrine requires.
    RecipeSpec("work-against-a-disposable-spreadsheet-create-use-delete",
               _check_disposable_lifecycle),
    RecipeSpec("write-a-live-formula-into-a-sheet", _check_formula_write),
    # LD-152 (dogfood F1) — the four sheets-write families that shipped with no recipe:
    # the DESTRUCTIVE half of the surface. Plus the clear (F10), which has no op of its own.
    RecipeSpec("insert-and-delete-rows-and-columns-a-structural-write",
               _check_structural_write),
    RecipeSpec(
        "set-a-row-s-height-a-column-s-width-and-hide-a-row-a-dimension-property-write",
        _check_dimension_property_write),
    # LD-188 — the CELL STYLE family, promoted out of the test harness: one range, a
    # number-format-only write, and N ranges in ONE call. LD-189 added BORDERS to the
    # same recipe (and its refuted word-wrap half), which is what renamed the heading.
    RecipeSpec("set-a-cell-s-fill-font-border-and-number-format-a-style-write",
               _check_style_write),
    RecipeSpec("freeze-and-unfreeze-rows-and-columns-a-freeze-panes-write",
               _check_freeze_panes_write),
    RecipeSpec("merge-and-unmerge-cells", _check_merge_write),
    RecipeSpec("add-a-dropdown-list-rule-to-a-range", _check_dropdown_write),
    RecipeSpec("add-copy-and-delete-a-tab", _check_tab_write),
    # LD-187 — the tab-PRESENTATION trio (reorder / retitle / hide-show) on the same
    # `updateSheet` seam, with both disclosures and both refusal classes exercised.
    RecipeSpec("reorder-retitle-and-hide-a-tab-a-tab-presentation-write",
               _check_tab_presentation_write),
    RecipeSpec("clear-cells-there-is-no-clear-operation", _check_clear_cells),
    # LD-147 — the round-2 documentation tranche: the multi-turn queue (b) and the two
    # help()-only operations that now have worked recipes (g).
    RecipeSpec("accumulate-edits-across-turns-a-multi-turn-request-queue", _check_multi_turn),
    RecipeSpec("edit-part-of-a-paragraph-a-sub-span-edit", _check_subspan_edit),
    RecipeSpec("edit-a-code-block-s-text", _check_code_edit),
    # LD-159 — the comments READ: the join from a parsed block to what a reviewer said.
    RecipeSpec("read-the-comments-on-a-document", _check_comments_read),
    # LD-168 — the OBJECT-LEVEL pair: read → change, for a document and for a spreadsheet,
    # with the zero-Markdown call spy asserting the path touched none of the three Markdown
    # call sites. These two are the level section's thesis in executable form.
    RecipeSpec("change-a-document-at-the-object-level-no-markdown-anywhere",
               _check_object_level_docx),
    RecipeSpec("change-a-spreadsheet-at-the-object-level-no-markdown-anywhere",
               _check_object_level_sheets),
    # LD-202 — the comment WRITE pair: create → read back what was MADE → take it back.
    RecipeSpec("leave-a-comment-on-a-document-and-take-it-back", _check_comment_write),
    # LD-293 — the opt-in RAW value view: dedupe on the wire value instead of re-deriving it
    # from the library's own Markdown (the mailto trap, in executable form).
    RecipeSpec("compare-base-rows-on-the-raw-values", _check_base_raw_values),
    # LD-283 — the five recipe-less Base areas, plus the bulk-import audit. Each one runs the
    # shipped engine over the committed captures; the doubles grew only where a recipe needed
    # a shape they lacked (a created column's `property`, `records/batch_get`, the media leg).
    RecipeSpec("add-a-column-and-change-one-s-name", _check_base_field_creation),
    # LD-418 — the not-settable classification (grouping/sort/hidden fields), renamed for
    # its own findability (D-60, second application) without splitting the recipe: the
    # classification is inseparable from the view lifecycle it explains create_view's
    # unconfigured-ness through.
    RecipeSpec(
        "create-configure-and-delete-a-view-hidden-columns-are-settable-grouping-and-a-saved-sort-are-not",
        _check_base_views,
    ),
    RecipeSpec("attach-a-file-to-a-record-and-prove-the-bytes-survived", _check_base_media),
    RecipeSpec("resolve-link-columns-to-names-and-find-the-ones-pointing-at-a-deleted-table",
               _check_base_link_resolution, base_links=True),
    RecipeSpec("read-what-a-lookup-or-formula-column-rolls-up-from",
               _check_base_computed_provenance),
    RecipeSpec("price-a-bulk-import-before-you-send-it", _check_base_bulk_import),
)

SPEC_BY_SLUG = {spec.slug: spec for spec in RECIPE_SPECS}
