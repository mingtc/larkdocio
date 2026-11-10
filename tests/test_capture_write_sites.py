"""THE CAPTURE-WRITE CENSUS (LD-620) — every in-tree capture write goes through the sink.

:mod:`capture_sink` is the mechanism and the refusal; **nothing in Python can stop a future
site from calling ``Path.write_text`` on a committed capture anyway.** That is the half this
file holds, and it is why the fix is not "the one gate that fired": four occurrences
(``ld317-01``, ``LD-497`` (reverted on trunk), LD-619's Dev leg, LD-619's QA) came from
**different** gates writing the same way, and a fix aimed at the observed one would have read
as complete while leaving the rest armed.

**The property, in one sentence.** No source file under ``tests/`` may write, create, move or
delete a path that is (i) anchored at **this repository** and (ii) inside a ``captures``
directory — except through :func:`capture_sink.write_capture`.

**Both halves of the address are required, and that is what keeps the scan honest.** A
sandbox capture built under ``tmp_path`` — which is how
``tests/test_capture_sink.py`` demonstrates the hazard, and how it seeds the committed file
the fence protects — is *not* anchored at the repository, so it is not a hit. The exclusion is
**structural** rather than a register entry: an argued register of sandboxes would grow one
row per new sandbox and every row would say the same thing, and a register everyone appends to
guards nothing (the shape borrowed, inverted, from
``tests/test_no_test_reads_live_git.py``'s register of individually argued rows — there the
exception is rare and each row carries its own justification; **its size is deliberately not
quoted here**, because a cross-reference retyped in prose is what LD-628 found stale in three
places, this sentence among them).

**The envelope reaches past the spelling that fired.** The gates spelled it
``CAPTURE.write_text(...)`` at module scope, so a scan matching only that would be satisfied by
a rename. What is followed instead is the *derivation*: any name assigned from an expression
that reaches a repository anchor and a ``captures`` segment carries the taint, at module scope
**and inside a function**, to a fixpoint — which covers the four evasions this project's
guards have met before: a module constant, a **local** indirection
(``path = _CAPTURE_DIR / name`` — the real spelling in
``test_live_base_schema_gate.py``), an **f-string** filename, and ``open(path, "w")`` instead
of a ``Path`` method.

**The two halves used to have to MEET IN ONE EXPRESSION, and three plausible spellings walked
through (LD-623).** LD-620's propagation tainted a name only when its own right-hand side
reached a repository anchor *and* said ``captures``, so a derivation that split the address
across two steps carried nothing: ``ROOT = Path(__file__).parents[1]`` (the repo half, under a
name that does not say ``REPO``) followed by ``ROOT / … / 'captures' / …`` was invisible, as
were a ``Path.cwd()`` anchor and a root handed back by a helper — **4 spellings tried by that
issue's QA, 3 missed.** Nothing in the tree spelled a capture path any of those ways, and the
runtime redirect-and-refusal in :mod:`capture_sink` still catches what this census misses, so
it was a **defence-in-depth gap and not a live hole** — which is why the fix is a widening
rather than an incident. The two halves are now propagated **separately**: a name can hold the
repo half alone and pass it on, and a **function's own** ``return`` expressions bind to its
name, so a root that leaves the module scope and comes back through a call is followed too.
Each of the three is a fixture below, and each was watched red first.

**What it still cannot see, stated rather than implied.** A root read from the environment or
a config file, a root arriving as a **function parameter** (nothing is inferred across call
sites), a name **imported** from another module, and a ``captures`` segment assembled at
runtime from pieces that never spell the word. Those are the honest edge of this scan; the
mechanism that does not depend on any of it is :func:`capture_sink.write_capture`, which
redirects and announces at run time. **This file is the second fence, not the first.**

**No git, and no live-state read.** The scan parses source text and never asks git what is
tracked (``tests/test_no_test_reads_live_git.py``), for the same reason that guard gives: an
answer that depends on the checkout is true once. *"Inside a ``captures`` directory of this
repository"* is a property of the tree, and it is the property the four occurrences shared.
"""
import ast
import pathlib

import capture_sink

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TESTS = REPO_ROOT / "tests"

#: Attribute calls that write, create, move or remove the thing they are called on. ``mkdir``
#: is in the list because creating ``dev/<study>/captures/`` is how an untracked-litter run
#: starts, and ``git status --porcelain`` is not empty with a stray directory in it either.
MUTATING = {"write_text", "write_bytes", "mkdir", "touch", "replace", "rename", "unlink",
            "open", "hardlink_to", "symlink_to"}

#: ``{method: the argument counts that make it a PATH method}`` — the one name in
#: :data:`MUTATING` that a **string** also answers to (LD-623). ``Path.replace(target)`` moves
#: a file and takes exactly one argument; ``str.replace(old, new[, count])`` takes two or
#: three and moves nothing. Once either half of the address travels under a name, a string
#: lifted out of a capture's own JSON inherits the taint, and three honest sites went red on
#: their ``str.replace`` (``test_base_platform_anomaly.py``'s ``ld329_msg``, and two renders in
#: ``test_sheets_filter_read.py``). The discriminator is the arity, not a name allow-list: a
#: register of exempt sites would have to be edited by the next test that reads a capture.
ARITY_DISCRIMINATED = {"replace": (1,)}

#: Substrings that mark an expression as anchored at **this repository** rather than at a
#: sandbox. ``__file__`` covers the ``Path(__file__).resolve().parents[1] / …`` idiom every
#: live gate uses; the two names cover the helpers that hand the root out ready-made. The two
#: working-directory spellings joined in LD-623: the suite's rootdir **is** the repository, so
#: a capture built off the cwd lands in the tree exactly like a ``__file__``-anchored one, and
#: the mirror-image false positive (a test that has chdir'd into a sandbox) is accepted
#: deliberately — it costs one honest site a route through the sink, while the false negative
#: costs a committed capture.
REPO_ANCHORS = ("__file__", "REPO_ROOT", "REPO", ".cwd()", "getcwd()")

#: The directory name that makes a path a capture path. One word, deliberately: the corpus's
#: own convention is ``dev/<study>/captures/``, and a path that does not say ``captures`` is
#: not part of the evidence regime this fence protects.
CAPTURE_SEGMENT = "captures"

#: The sanctioned call. A site that writes a capture writes it through this.
SANCTIONED = "write_capture"


def _names(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _assignments(scope_body):
    """``[(name, value_node)]`` for every plain assignment in a scope, in source order."""
    out = []
    for node in ast.walk(ast.Module(body=list(scope_body), type_ignores=[])):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        if not targets or getattr(node, "value", None) is None:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                out.append((target.id, node.value))
    return out


def _returns(tree):
    """``[(function name, returned expression)]`` — a function BINDS ITS NAME to what it hands
    back, so ``_root() / … / 'captures'`` is the same derivation as ``ROOT / … / 'captures'``.

    Over-approximating on purpose in one place: a ``return`` inside a *nested* function is
    attributed to the outer one as well. For a fence the safe direction is more taint, not
    less — the cost is a site being asked to route through the sink, which is where it belongs
    anyway.
    """
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Return) and inner.value is not None:
                out.append((node.name, inner.value))
    return out


def tainted_names(tree):
    """``(repo_names, capture_names)`` — the two halves of the address, propagated SEPARATELY.

    ``repo_names`` hold a path anchored at this repository; ``capture_names`` hold one that is
    *also* inside a ``captures`` directory (so ``capture_names <= repo_names``).

    Followed to a fixpoint over the whole module (module scope, every function body, and every
    function's own ``return`` — see :func:`_returns`) together: a constant feeding a local
    feeding an f-string is the same derivation, and splitting the scopes would only reward
    moving one link of the chain into a helper.

    **Why the halves are separate (LD-623).** Requiring them to meet in ONE expression is what
    let ``ROOT = Path(__file__).parents[1]`` and then ``ROOT / … / 'captures'`` through: the
    first assignment carried the repo half and nothing propagated it, the second said
    ``captures`` and had no anchor of its own. Splitting the sets keeps the *conjunction* at
    the write site — where it always was, and where it is what excludes a ``tmp_path``
    sandbox — while letting either half travel under a name.
    """
    repo, captures = set(), set()
    bindings = _assignments(tree.body) + _returns(tree)
    changed = True
    while changed:
        changed = False
        for name, value in bindings:
            source = ast.unparse(value)
            referenced = _names(value)
            reaches_repo = (any(a in source for a in REPO_ANCHORS)
                            or bool(referenced & repo))
            says_captures = CAPTURE_SEGMENT in source or bool(referenced & captures)
            if reaches_repo and name not in repo:
                repo.add(name)
                changed = True
            if reaches_repo and says_captures and name not in captures:
                captures.add(name)
                changed = True
    return repo, captures


def _spans(tree):
    return [(n.lineno, n.end_lineno or n.lineno, n.name)
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _enclosing(spans, lineno):
    inner = [name for start, end, name in spans if start <= lineno <= end]
    return inner[-1] if inner else "<module>"


def capture_write_sites(source, path="<string>"):
    """``[(path, lineno, function, spelling)]`` — every unsanctioned in-repo capture write."""
    tree = ast.parse(source)
    repo_names, capture_names = tainted_names(tree)
    spans = _spans(tree)
    hits = []

    def target_of(call):
        func = call.func
        if isinstance(func, ast.Attribute) and func.attr in MUTATING:
            if func.attr in ARITY_DISCRIMINATED and (
                    len(call.args) + len(call.keywords)) not in ARITY_DISCRIMINATED[func.attr]:
                return None, None
            return func.value, f".{func.attr}()"
        if isinstance(func, ast.Name) and func.id == "open" and call.args:
            mode = " ".join(ast.unparse(a) for a in call.args[1:] + [
                k.value for k in call.keywords if k.arg == "mode"])
            if any(ch in mode for ch in ("w", "a", "x", "+")):
                return call.args[0], "open()"
        return None, None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target, spelling = target_of(node)
        if target is None:
            continue
        expression = ast.unparse(target)
        referenced = _names(target)
        # The CONJUNCTION lives here, at the write site — both halves of the address, however
        # each of them arrived. That is what keeps a ``tmp_path`` capture out (neither half is
        # anchored at this repository) and a non-capture in-repo write out (the ``captures``
        # half is missing), which the two negative fixtures below hold.
        reaches_repo = (any(a in expression for a in REPO_ANCHORS)
                        or bool(referenced & repo_names))
        says_captures = CAPTURE_SEGMENT in expression or bool(referenced & capture_names)
        if not (reaches_repo and says_captures):
            continue
        hits.append((path, node.lineno, _enclosing(spans, node.lineno),
                     f"{expression[:60]}{spelling}"))
    return hits


def scan_tree(root=TESTS):
    hits = []
    for path in sorted(pathlib.Path(root).rglob("*.py")):
        hits.extend(capture_write_sites(path.read_text(encoding="utf-8"),
                                        path.relative_to(root).as_posix()))
    return hits


# =========================================================================== #
# AC4 — the census                                                              #
# =========================================================================== #

def test_ac4_NO_site_in_the_suite_writes_an_in_repo_capture_path_directly():
    """The property, over the whole of ``tests/**``.

    A new live gate that writes its capture the old way reddens here with **no registration
    step anywhere** — the same construction ``tests/live_write_fence.py`` chose for the consent
    fence, and for the same reason: a list of the gates that write captures would have to be
    edited by the leg that adds one.
    """
    offenders = scan_tree()
    assert not offenders, (
        "these sites write a capture path inside this repository directly:\n" + "\n".join(
            f"  tests/{p}:{line} — {spelling} in {func}()" for p, line, func, spelling in
            offenders
        ) + f"\n\nRoute the write through capture_sink.{SANCTIONED}(), which redirects it out "
            "of the working tree and says so out loud. An armed live_write run overwrote "
            "committed captures belonging to closed issues four times this way "
            f"({capture_sink.PRIOR_OCCURRENCES}) — see tests/capture_sink.py."
    )


def test_ac4_every_live_gate_that_writes_a_capture_is_ROUTED_not_merely_silent():
    """Direction two: the gates that *used* to write captures still write them — through the
    sink.

    Direction one alone is satisfiable by deleting the writes, which would be the worse
    outcome: the probes' captures are how a re-run's reading is compared with the committed
    one at all. So the files that carried a capture write are named here, and each must import
    the sink and call it.
    """
    routed = {
        "test_live_base_field_migration.py": "ld291-01-guided-migration",
        "test_live_base_media_gate.py": "ld519-01",
        "test_live_base_minimal_form.py": "ld317-01-minimal-form-sweep",
        "test_live_base_relational_gate.py": "ld272-01-relational-round-trip",
        "test_live_base_row_hierarchy.py": "ld296-01-row-hierarchy-live",
        "test_live_base_schema_fields.py": "ld262-01-field-authoring-probes",
        "test_live_base_schema_gate.py": "base-study",
        "test_live_base_views.py": "ld288",
        "test_live_docx_removal_routes_gate.py": "ld601",
    }
    missing = {}
    for name in sorted(routed):
        text = (TESTS / name).read_text(encoding="utf-8")
        if "capture_sink" not in text or f"{SANCTIONED}(" not in text:
            missing[name] = "does not call the sink"
    assert not missing, (
        f"these gates carried a capture write and must route it through capture_sink."
        f"{SANCTIONED}(): {missing}"
    )


# =========================================================================== #
# The scan's own envelope — the four evasions, each measured                     #
# =========================================================================== #

def test_the_scan_catches_the_MODULE_CONSTANT_spelling_that_actually_fired():
    source = (
        "from pathlib import Path\n"
        "CAPTURE = Path(__file__).resolve().parent.parent / 'dev' / 'x' / 'captures' / 'c.json'\n"
        "def probe():\n"
        "    CAPTURE.write_text('{}')\n"
    )
    assert [h[1] for h in capture_write_sites(source)] == [4]


def test_the_scan_follows_a_LOCAL_indirection_the_real_gate_used():
    """``path = _CAPTURE_DIR / name`` — ``test_live_base_schema_gate.py``'s own spelling, and
    the one a module-scope-only scan walks straight past."""
    source = (
        "from pathlib import Path\n"
        "_CAPTURE_DIR = Path(__file__).resolve().parent.parent / 'dev' / 'x' / 'captures'\n"
        "def _write_capture(name, blob):\n"
        "    _CAPTURE_DIR.mkdir(parents=True, exist_ok=True)\n"
        "    path = _CAPTURE_DIR / name\n"
        "    path.write_text(blob)\n"
    )
    assert [h[1] for h in capture_write_sites(source)] == [4, 6]


def test_the_scan_catches_an_F_STRING_filename_and_a_bare_open():
    source = (
        "import pathlib\n"
        "DIR = pathlib.Path(__file__).parent.parent / 'dev' / 'y' / 'captures'\n"
        "def probe(leg):\n"
        "    out = DIR / f'ld601-{leg}.json'\n"
        "    with open(out, 'w') as handle:\n"
        "        handle.write('{}')\n"
    )
    assert [h[1] for h in capture_write_sites(source)] == [5]


# --------------------------------------------------------------------------- #
# LD-623 — the three spellings QA tried that walked straight through.            #
#                                                                             #
#   Nothing in the tree spells a capture path any of these ways today, so this   #
#   was a DEFENCE-IN-DEPTH gap and not a live hole (the runtime redirect and     #
#   refusal in ``capture_sink`` still catch what the census misses). Each one    #
#   was watched RED before the propagation was widened.                          #
# --------------------------------------------------------------------------- #

def test_the_scan_follows_a_TWO_STEP_root_whose_name_says_nothing_about_the_repo():
    """``ROOT = Path(__file__).parents[1]`` and then ``ROOT / … / 'captures' / …``.

    The commonest spelling in this very suite, and the one the original propagation could not
    see: neither assignment carries both halves of the address, so neither was tainted and the
    write was invisible. The repo half is now carried by a name of its own.
    """
    source = (
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "def probe():\n"
        "    (ROOT / 'dev' / 'x' / 'captures' / 'c.json').write_text('{}')\n"
    )
    assert [h[1] for h in capture_write_sites(source)] == [4]


def test_the_scan_follows_a_CWD_anchor():
    """``Path.cwd()`` is a repository anchor for the run this fence is about.

    The suite's rootdir *is* the repository, so a capture built off the working directory lands
    in the tree exactly like a ``__file__``-anchored one. The residual risk is the mirror image
    — a test that has chdir'd into a sandbox — and it is accepted deliberately: the cost of
    that false positive is one honest site routing through the sink, and the cost of the false
    negative is a committed capture overwritten (four times, ``capture_sink.PRIOR_OCCURRENCES``).
    """
    source = (
        "import pathlib\n"
        "def probe():\n"
        "    out = pathlib.Path.cwd() / 'dev' / 'x' / 'captures' / 'c.json'\n"
        "    out.write_text('{}')\n"
    )
    assert [h[1] for h in capture_write_sites(source)] == [4]


def test_the_scan_follows_a_root_a_HELPER_RETURNED():
    """``def _root(): return Path(__file__)…`` and then ``_root() / … / 'captures'``.

    A derivation that leaves the expression and comes back through a call. The helper's own
    ``return`` is read, so its NAME becomes an anchor — which is the same fixpoint the module
    already ran over assignments, extended to the one edge that could be reached by moving a
    link of the chain into a function.
    """
    source = (
        "from pathlib import Path\n"
        "def _root():\n"
        "    return Path(__file__).resolve().parents[1]\n"
        "def probe():\n"
        "    path = _root() / 'dev' / 'x' / 'captures' / 'c.json'\n"
        "    path.write_text('{}')\n"
    )
    assert [h[1] for h in capture_write_sites(source)] == [6]


def test_the_scan_tells_a_PATH_MOVE_from_a_STRING_replace_by_ARITY():
    """The one false positive the widening produced, narrowed rather than exempted.

    Both halves of the address now travel under a name, so a **string** lifted out of a
    capture's own JSON is tainted too — and ``str.replace(old, new)`` shares its name with
    ``Path.replace(target)``, the move. Three honest sites reddened on exactly that. The
    discriminator is arity: one argument is a move, two or three are a substitution.
    """
    move = (
        "from pathlib import Path\n"
        "def probe():\n"
        "    out = Path(__file__).parent / 'dev' / 'x' / 'captures' / 'c.json'\n"
        "    out.replace(Path(__file__).parent / 'dev' / 'x' / 'captures' / 'd.json')\n"
    )
    assert [h[1] for h in capture_write_sites(move)] == [4]

    substitution = (
        "import json\n"
        "from pathlib import Path\n"
        "def _capture(name):\n"
        "    return json.loads((Path(__file__).parent / 'captures' / name).read_text())\n"
        "def message(table_id):\n"
        "    template = _capture('c.json')['msg']\n"
        "    return template.replace('old', table_id)\n"
    )
    assert capture_write_sites(substitution) == []


def test_the_scan_does_NOT_fire_on_a_sandbox_capture_or_on_a_READ():
    """Both halves of the address are required. A ``tmp_path`` capture is not this repository's
    evidence, and reading a committed capture is what the whole corpus is *for*."""
    source = (
        "from pathlib import Path\n"
        "CAPTURE = Path(__file__).resolve().parent.parent / 'dev' / 'x' / 'captures' / 'c.json'\n"
        "def test_reads(tmp_path):\n"
        "    blob = CAPTURE.read_text()\n"
        "    scratch = tmp_path / 'dev' / 'x' / 'captures' / 'c.json'\n"
        "    scratch.parent.mkdir(parents=True)\n"
        "    scratch.write_text(blob)\n"
    )
    assert capture_write_sites(source) == []


def test_the_scan_does_not_fire_on_a_non_capture_in_repo_write():
    """The fence is about the evidence corpus, not about every path in the tree — the golden
    updaters (``--update-golden``, ``tests/fixtures/*.expected.md``) are a different, opt-in,
    human-typed mechanism and are named in this issue's handoff rather than swept in here."""
    source = (
        "from pathlib import Path\n"
        "FIX = Path(__file__).resolve().parent / 'fixtures'\n"
        "def update(name, body):\n"
        "    (FIX / f'{name}.expected.md').write_text(body)\n"
    )
    assert capture_write_sites(source) == []
