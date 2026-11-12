"""THE CUT MAY NOT REDDEN THE TRUNK — the standing guard behind LD-316.

The defect this file exists to prevent, stated once
---------------------------------------------------
``scripts/release.sh`` runs its gates **before** it bumps the version (its own header: gate b,
the whole suite, is step 3; the bump is step 7), and it is right to — the bump *is* the release
commit. The consequence is structural: **any assertion that freezes the packaged version string
is guaranteed to be red the moment a release is cut**, on a trunk whose gates just ran green.
That is what the v1.27.0 cut did to four assertions in three files, and what LD-316 fixed by
making each of them cut-tolerant (see those files' own re-anchor notes).

Fixing four sites is not the answer; **catching the fifth is.** This guard reddens on the branch
that introduces a version-frozen assertion — at review time, when the author is still holding
the file — instead of at the cut, weeks later, on somebody else's clean checkout.

What it does and does NOT forbid
--------------------------------
* **Forbidden:** a bare ``"X.Y.Z"`` literal equal to the **currently packaged** version. That is
  a landing-time photograph; the next cut invalidates it. Express the invariant instead — the
  three LD-316 rewrites are the worked examples (``tests/release_versions.py``'s at-most-one-
  ahead rule; ``tests/capabilities_anchor.py``'s version-normalised digest).
* **Allowed, deliberately:** a ``## [X.Y.Z]`` **section heading** literal. Those name one
  historic disclosure section — a fixed point in the changelog, not the moving current version —
  and a guard over "what release 1.23.0 said" legitimately has to name 1.23.0.
* **Allowed:** any version literal that is not the packaged one (release-flow sandboxes author
  synthetic versions like ``1.99.0``; history guards name shipped ones).
* **Allowed, by PROPERTY and never by an exception list (LD-671 AC2):** a literal that is
  **WATCHED** — bound to a module-level name that some test in this suite holds against the
  packaged version. See :func:`_names_held_against_the_packaged_version`.

The population is ``tests/`` **and** ``src/`` (LD-671 AC2)
---------------------------------------------------------
It used to be ``tests/`` only, which put the guard's blind spot in the one tree where a stale
version literal is **shipped**: ``LD-658`` set ``read/config.py``'s tolerance window to a bare
``"X.Y.Z"`` — exactly the forbidden shape — in the one place this walk did not look. The
guard's reason applies to ``src`` at least as strongly, so ``src`` is in the walk now.

**Why the widening needed a property rather than an exemption.** When ``src`` joined the walk,
two ``src`` literals equalled the packaged version, and both were legitimate:
``larkdocio/__init__.py``'s ``__version__`` — which does not *photograph* the packaged version,
it **IS** it — and ``read/config.py``'s retired-key tolerance window, a deliberately declared
constant that sat one release *ahead* of packaged when LD-658 landed it and **equalled**
packaged after the next cut. (LD-704 discharged that window, so ``__version__`` is the one
left; the property below is unchanged and would admit a future window on the same terms.)

An "ahead of packaged" rule would therefore have reddened the trunk the day after the cut. The
rule that survives the cut is the one ``LD-658``'s own guard already states — **not older than
packaged** — and it is green at equality. But no literal is excused for being *ahead* or
*equal*: each is excused because **a live test holds it against the packaged version**, so it
cannot go stale unnoticed, which is the entire harm LD-316 was filed about. Name a new constant
equal to the packaged version with nothing watching it and this guard reddens; that is the
intended behaviour.
"""
import ast
import functools
import os
from pathlib import Path

import pytest

from release_versions import packaged_version

_TESTS = Path(__file__).resolve().parent
_REPO = _TESTS.parent

#: Sites whose bare literal is legitimately the packaged version, each with the reason it is
#: not a landmine. Keyed by ``(filename, literal)`` — never by line number, which churns.
#: **Empty is the healthy state.** An entry here is a claim that the next cut cannot redden it.
_ALLOWED = {}


def _packaged():
    return packaged_version((_REPO / "pyproject.toml").read_text(encoding="utf-8"))


#: Prose is not a pin. A DOCSTRING — or any bare string statement — may name a version freely:
#: explaining *why* the v1.27.0 cut reddened this suite is the opposite of freezing it, and a
#: guard that forbade the explanation would have deleted its own rationale. Only strings the
#: code actually USES are inspected. (Comments are not in the AST at all, for the same reason.)
def _string_constants(path):
    """``[(literal, lineno)]`` for every string constant *used as a value* in *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    prose = {id(node.value) for node in ast.walk(tree)
             if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)}
    return [(node.value, node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in prose]


def test_the_packaged_version_is_readable_and_the_guard_below_is_not_vacuous():
    """A guard that cannot find the version it forbids forbids nothing."""
    packaged = _packaged()
    assert packaged.count(".") == 2, packaged
    from larkdocio import __version__
    assert __version__ == packaged, (
        f"pyproject says {packaged}, the package says {__version__} — a half-applied bump")


#: LD-654 — the population MUST be recursive. ``tests/`` already has subdirectories
#: (``fixtures/``, ``fixtures/reconcile/``, ``fixtures/reconcile/leg2-trials/``,
#: ``fixtures/sheets/``); they hold zero ``.py`` files today, which is exactly what let a flat
#: ``glob("*.py")`` pass as "exhaustive" for as long as it did — the day one of them (or a new
#: sibling) gains a test module, the flat form would silently stop checking it, and a frozen
#: version literal there would sail through a release. ``rglob`` cannot have that blind spot.
_FLAT = sorted(_TESTS.glob("*.py"))
_RECURSIVE = sorted(_TESTS.rglob("*.py"))

#: LD-671 AC2 — ``src`` joins the walk. Derived the same way and for the same reason; a stale
#: literal here is worse, because it is the one that SHIPS.
_SRC = sorted((_REPO / "src").rglob("*.py"))

#: The whole population, in one place so the count is derived rather than described.
_POPULATION = _RECURSIVE + _SRC

#: Names that MEAN "the version this build is packaging". A literal compared against — or
#: passed in one expression alongside — any of these is being HELD to the packaged version by
#: a live test, which is exactly the thing a landing-time photograph is not.
_PACKAGED_VERSION_NAMES = frozenset({"__version__", "packaged_version"})


def _operand_names(node):
    """Every identifier *node* mentions — ``Name`` ids and attribute tails."""
    return {inner.id if isinstance(inner, ast.Name) else inner.attr
            for inner in ast.walk(node)
            if isinstance(inner, (ast.Name, ast.Attribute))}


def _import_aliases(tree):
    """``{local name: imported name}`` for every ``from X import A as B`` in *tree*.

    Without this the walk below would look for an imported constant (``from X import NAME as
    tolerated`` was the LD-658 shape) and find only ``tolerated``, and the guard would report an unwatched literal that is in fact watched
    twice over — an instrument reporting a defect it invented.
    """
    return {alias.asname or alias.name: alias.name
            for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
            for alias in node.names}


@functools.lru_cache(maxsize=1)
def _names_held_against_the_packaged_version():
    """Every IMPORTED name this suite asserts about alongside the packaged version.

    **This is the property that replaces an exception list** (LD-671 AC2). LD-316's harm is not
    that a version literal exists — ``__version__`` is one — it is that a literal goes stale
    **unnoticed**, so the trunk discovers it at the next cut. A name a live test holds against
    the packaged version cannot do that: the day it drifts, that test says so. So the question
    this guard asks about a ``src`` literal is not *"is it ahead?"* (which the ``v1.51.0`` cut
    made false overnight) and not *"is it config.py?"* (which is an exemption wearing a
    property's clothes) — it is **"is anything watching it?"**

    A watch site is an ``assert`` statement that mentions a packaged-version name
    (:data:`_PACKAGED_VERSION_NAMES`); what it marks as watched are the names in that statement
    the module **imported**, resolved through ``as`` aliases back to the identifier the shipped
    module binds. Both halves are load-bearing and each was added because the looser form was
    wrong:

    * **``assert``, not any expression** — an assertion is a CLAIM. Counting every call that
      happened to take the version as an argument marked ordinary local variables
      (``caps``, ``payload``, ``version``) as watched, and a constant in ``src`` named ``version``
      would then have been excused by an accident of naming.
    * **imported, not any identifier** — a test that watches a shipped constant has to import it.
      Filtering to the module's own import table drops every local temporary, which is what
      makes the marked set small enough to read.
    """
    held = set()
    for path in _RECURSIVE:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        aliases = _import_aliases(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assert):
                continue
            mentioned = _operand_names(node)
            if not (mentioned & _PACKAGED_VERSION_NAMES):
                continue
            held |= {aliases[name] for name in mentioned if name in aliases}
    return frozenset(held)


def _module_level_names_bound_at(path, literal, lineno):
    """The module-level names *path* binds *literal* to **at that line** — the handle a watcher
    would use.

    Keyed by line and not by value, and the difference is not cosmetic: keying by value alone
    made every occurrence of the literal in a file share the excuse earned by ONE of them, so a
    second, unwatched constant next to a watched one sailed through. Caught by this issue's own
    AC4 red-watch, which planted exactly that shape and stayed green until the line was part of
    the key.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = set()
    for node in tree.body:
        value = getattr(node, "value", None)
        if not (isinstance(value, ast.Constant) and value.value == literal
                and value.lineno == lineno):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names |= {t.id for t in targets if isinstance(t, ast.Name)}
    return names


def test_the_WATCHED_property_admits_only_what_is_actually_watched():
    """The exemption's own non-vacuity — in both directions, because it fails in both.

    Too wide and it excuses every literal in ``src``; too narrow and it reports the real,
    watched constants as defects. So: the set is non-empty, it contains the name the widened
    population legitimately turns up, and it does **not** contain a name nothing watches.
    """
    held = _names_held_against_the_packaged_version()
    assert held, (
        "no name in this suite is held against the packaged version — the watch walk found "
        "nothing, so every src literal below would be excused by an empty rule. This guard "
        "must fail because it COULD NOT CHECK, not pass because it found no objection.")
    assert "__version__" in held, sorted(held)[:20]
    assert "AN_IDENTIFIER_NO_TEST_IN_THIS_SUITE_MENTIONS" not in held


def test_a_watched_constant_does_not_lend_its_excuse_to_the_line_below_it(tmp_path):
    """The exemption is per-BINDING, not per-value — and this is the arm that says so.

    The first draft of the widening keyed the excuse by ``(file, literal)``. That reads
    plausibly and is wrong: a module with one watched constant then excused **every** other
    occurrence of the same string in the same file, which is precisely the shape a planted
    landmine takes. Exercised over a synthetic module so the arm keeps working after the real
    tree stops containing an example.
    """
    version = "7.7.7"                      # synthetic: never the packaged version
    module = tmp_path / "synthetic.py"
    module.write_text(f'WATCHED = "{version}"\nUNWATCHED = "{version}"\n', encoding="utf-8")
    bindings = {lineno: _module_level_names_bound_at(module, version, lineno)
                for _literal, lineno in _string_constants(module)}
    assert bindings == {1: {"WATCHED"}, 2: {"UNWATCHED"}}, bindings


def test_the_flat_and_recursive_globs_still_agree_so_a_new_subdirectory_cannot_go_quiet():
    """AC2 (LD-654) — the announcement wire, not the fix.

    AC1 already makes the population above ``rglob``-derived, so a test module in a future
    ``tests/`` subdirectory is covered regardless of this test. What this test adds is
    NOTICE: the day ``tests/`` actually grows a subdirectory holding a ``.py`` file, this
    reddens — on purpose, and it FAILS rather than merely logging, because a disclosure that
    only prints is exactly the shape of silence that let the flat glob pass as exhaustive for
    as long as it did (LD-654's own discovery: nothing reddened when the population narrowed).

    Failing here is not obstructive: it can only fire on a genuinely rare, structural event —
    a brand-new subdirectory under ``tests/`` starting to hold Python — never on the routine
    work of adding or editing a test file at the existing flat level. When it does fire, the
    fix is a conscious one-line acknowledgment (e.g. widening this docstring's subdirectory
    list above, or confirming nothing else in the suite still assumes ``tests/`` is flat) —
    not a silent absorption.
    """
    flat = {p.relative_to(_TESTS) for p in _FLAT}
    recursive = {p.relative_to(_TESTS) for p in _RECURSIVE}
    assert flat == recursive, (
        f"tests/ has grown a subdirectory holding .py files: "
        f"{sorted(str(p) for p in recursive - flat)}. The population above already covers "
        f"them (it is rglob-derived per AC1), so no version-bump coverage was lost — but this "
        f"is a structural change worth one deliberate look, not a silent pass."
    )


def test_the_population_covers_BOTH_trees_and_neither_half_is_empty():
    """LD-671 AC2's own non-vacuity. A ``src`` half that silently resolved to nothing would
    restore the exact blind spot this widening closes, and would do it while showing green."""
    assert _RECURSIVE, "the tests/ half of the population is empty"
    assert _SRC, "the src/ half of the population is empty — the widening is inert"
    assert len(_POPULATION) == len(_RECURSIVE) + len(_SRC)
    assert not any(p in _RECURSIVE for p in _SRC), "the two halves must not overlap"


def _offenders(path, version):
    """``[(literal, lineno)]`` in *path* that freeze *version* — the one definition both freeze
    tests below apply, so "frozen" means the same thing for the packaged and the next version."""
    offenders = [
        (literal, lineno) for literal, lineno in _string_constants(path)
        # The heading form is the documented exception; a bare literal is not.
        if version in literal and f"[{version}]" not in literal
    ]
    # WATCHED (LD-671 AC2), checked before the exception list on purpose — a property that
    # holds is the answer, and _ALLOWED is the confession you make when none does.
    held = _names_held_against_the_packaged_version()
    offenders = [(literal, lineno) for literal, lineno in offenders
                 if not (_module_level_names_bound_at(path, literal, lineno) & held)]
    return [(literal, lineno) for literal, lineno in offenders
            if (path.name, literal) not in _ALLOWED]


#: LD-718 AC2 — the environment variable ``scripts/release.sh`` exports around gate b, naming
#: the version it is ABOUT to cut. The guard below cannot otherwise see it: the bump that makes
#: the target "the packaged version" happens after every gate has run.
RELEASE_TARGET_ENV = "LARKDOCIO_RELEASE_TARGET"


def _next_versions(packaged):
    """The versions the next cut could plausibly be: the next patch and the next minor, plus
    the target ``release.sh`` names when it is cutting.

    larkdocio's numbers carry no major/minor semantics (``tests/release_versions.py``), so the
    two increments every cut so far has taken are checked at landing time, and anything else —
    a skipped number, a first-part increment — is caught at gate b by the explicit target,
    which no successor arithmetic can predict. The first-part increment is left to the target
    on purpose: ``X+1.0.0`` is the usual synthetic "legitimate next cut" in the release-rule
    tests, and checking it every day would refuse those until the day it is actually cut.
    """
    major, minor, patch = (int(part) for part in packaged.split("."))
    candidates = {f"{major}.{minor}.{patch + 1}", f"{major}.{minor + 1}.0"}
    target = os.environ.get(RELEASE_TARGET_ENV, "").strip().removeprefix("v")
    if target:
        candidates.add(target)
    candidates.discard(packaged)
    return sorted(candidates)


@pytest.mark.parametrize(
    "path", _POPULATION, ids=lambda p: str(p.relative_to(_REPO)))
def test_no_module_FREEZES_the_currently_packaged_version_string(path):
    packaged = _packaged()
    offenders = _offenders(path, packaged)
    assert offenders == [], (
        f"{path.name} freezes the packaged version {packaged!r} at "
        f"{[lineno for _literal, lineno in offenders]}. THE RULE: release.sh gates BEFORE it "
        f"bumps (header steps 3 vs 7), so a frozen version literal is red the moment the next "
        f"release is cut — on a trunk whose gates just passed. Assert the INVARIANT instead: "
        f"`release_versions.ahead_refusal` for a disclosure-section claim, "
        f"`capabilities_anchor.anchor_digest` for a canonical-output anchor, or "
        f"`larkdocio.__version__` where the point really is 'the installed version'. If the "
        f"literal is a DECLARED constant that must carry this version — a tolerance window, a "
        f"shipped `__version__` — bind it to a module-level name and have a test HOLD that name "
        f"against the packaged version; the guard then excuses it by that property, and the day "
        f"it drifts something says so. Only if no property fits, add it to _ALLOWED with its "
        f"reason."
    )


@pytest.mark.parametrize(
    "path", _POPULATION, ids=lambda p: str(p.relative_to(_REPO)))
def test_no_module_FREEZES_the_NEXT_version_string_either(path):
    """LD-718 — the same rule, applied one cut EARLY.

    The guard above is sound and still let v1.53.0 ship red: a README pin naming
    ``v1.53.0`` matched no packaged version while every gate ran, and became the packaged
    version only by the bump, after the last gate. A literal is a landmine for the cut that
    makes it current, so it is refused while it is still the NEXT version — at landing time
    for every plausible increment, and at ``release.sh``'s gate b for the exact target it
    exports in :data:`RELEASE_TARGET_ENV`.
    """
    packaged = _packaged()
    frozen = {version: [lineno for _literal, lineno in _offenders(path, version)]
              for version in _next_versions(packaged)}
    frozen = {version: lines for version, lines in frozen.items() if lines}
    assert frozen == {}, (
        f"{path.name} names a version the NEXT cut would make the packaged one "
        f"(packaged is {packaged!r}): {frozen} (version: lines). Green today, red the moment "
        f"that version is cut — the LD-718 shape. Use a placeholder (`vX.Y.Z`) or "
        f"derive it from `larkdocio.__version__` at test time; the rule and its remedies are "
        f"test_no_module_FREEZES_the_currently_packaged_version_string's message."
    )


def test_the_next_version_set_is_not_vacuous_and_honours_the_release_target(monkeypatch):
    """The early arm's own non-vacuity: it checks something, never the packaged version (the
    arm above owns that), and the target ``release.sh`` exports is in the set — with or
    without the leading ``v`` the script accepts."""
    packaged = _packaged()
    monkeypatch.delenv(RELEASE_TARGET_ENV, raising=False)
    plausible = _next_versions(packaged)
    assert len(plausible) == 2 and packaged not in plausible, plausible
    monkeypatch.setenv(RELEASE_TARGET_ENV, "v97.0.3")     # synthetic: a skipped number
    assert "97.0.3" in _next_versions(packaged)


def test_a_planted_NEXT_version_literal_is_refused(tmp_path):
    """The red-watch, kept as a permanent arm: a module pinning the next patch version — the
    exact LD-718 shape — is an offender for the early arm and not for the packaged one. The
    literal is built at run time so this file does not plant it in itself."""
    major, minor, patch = (int(part) for part in _packaged().split("."))
    upcoming = f"{major}.{minor}.{patch + 1}"
    module = tmp_path / "planted.py"
    module.write_text(f'PIN = ("scripts/update_larkdocio.sh v{upcoming}",)\n', encoding="utf-8")
    assert upcoming in _next_versions(_packaged())
    assert _offenders(module, upcoming) == [(f"scripts/update_larkdocio.sh v{upcoming}", 1)]
    assert _offenders(module, _packaged()) == []
