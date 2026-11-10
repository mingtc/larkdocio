"""The CONSUMER-REACHING TEXT CORPUS + the internal-dialect pattern set (LD-153 / F7).

Why this module exists
----------------------
larkdocio's consumer-facing text used to be written in this repo's **internal issue
dialect** — ``LD-149`` inside ``plan.revision_guard_detail`` (a field an agent may relay
verbatim to a user), ``D2``/``AC3``/``S2``/``T23``/a private-set id in the docstrings of public
symbols, "the PM-adopted choice", "the AST guard extends over it". None of it is resolvable
from any surface a consumer can touch: an issue id, a decision-sheet letter, a story number
or an internal role name means nothing outside this repo, and relaying it makes the library
look like it is leaking its own bug tracker.

This module defines, in one place:

* :func:`dialect_hits` — the **pattern set** (the dialect vocabulary), and
* :func:`consumer_corpus` — the **scope**: every text surface a consumer can reach.

``tests/test_consumer_dialect_guard.py`` is the guard that greps the second with the first.

The scope rule (the load-bearing half)
--------------------------------------
**Inside ``src/``, a ``#`` comment carries the dialect and a docstring / string literal does
not.** Comments are for the maintainer standing in this repo, where ``LD-149`` resolves;
docstrings, emitted messages and shipped docs are read by someone who has only the wheel.
So the corpus below is built from four passes that are all *strings*, and the AST/tokenizer
never yields a comment — which is exactly how ``tests/``, ``dev/``, ``progress.md``,
``requirements/`` and every internal ``#`` comment stay untouched by construction (they are
not in the corpus, so the guard cannot reach them).

To keep an internal reference next to code, put it in a ``#`` comment.

The front door (LD-167)
-----------------------
:func:`shipped_docs` was for months the two accessor-backed deep docs and nothing more, so
everything downstream of it — this file's dialect grep and the content guards that reuse the
corpus — could not see the README, the wheel ``METADATA`` fields or the CLI ``--help``. That
is the whole reason the front door rotted: it was not neglected, it was **out of scope**. It
is in scope now, and the widening cost no new machinery — the guards grep whatever that
function returns. The completeness half (a grep cannot notice an *absence*) lives in
``tests/test_front_door_doctrine.py``.
"""
import ast
import importlib
import inspect
import json
import pathlib
import re

from domain_vocabulary import RETIRED_ID
import front_door

import larkdocio


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src" / "larkdocio"


# --------------------------------------------------------------------------- #
# 1. THE DIALECT VOCABULARY                                                    #
#                                                                              #
# Each entry is (name, compiled pattern, what a replacement should say         #
# instead). The A1-notation exclusions in `decision-ref` are what keeps        #
# `Sheet1!A1:D10` from reading as decision-sheet ref "D10".                    #
# --------------------------------------------------------------------------- #

#: An issue id — ``LD-149``. Unresolvable off this repo's board.
_ISSUE_ID = re.compile(r"\bLD-\d{2,4}\b")

#: A private id: a member of the maintainers' private pattern set (:mod:`domain_vocabulary`),
#: read from the private ledger; in the public tree, where its source is absent, this one class
#: is inert and the others run (LD-705, LD-707).
#:
#: **LEFT CITATION-ONLY BY LD-650.** This pattern matches only the CITATION form. Its reason for
#: staying narrow stands: sibling modules carry the same citation literal, and a sweep that
#: "generalises" an expression can turn a guard QUIET, which passes green instead of reddening.
_PRIVATE_ID = RETIRED_ID

#: An acceptance-criterion ref — ``AC3``. Numbered inside an issue file.
_AC_REF = re.compile(r"\bAC\d+\b")

#: A decision-sheet / story / task / finding ref — ``D9``, ``S2``, ``T23``, ``F14``, and the
#: HYPHENATED spelling the decision sheet actually uses: ``D-73``, ``D-103``, ``S-2``.
#: The lookaround excludes A1 notation: ``A1:D10`` (preceded by ``:``), ``D4:F9`` (followed
#: by a colon AND another cell ref), ``Sheet1!D4`` (preceded by ``!``), ``$D$4``, and ``3D``.
#: A trailing colon alone does NOT excuse it — "S5: the deep read" is exactly the dialect.
#: Two holes were closed here (LD-603): the expression had **no hyphen alternative** and
#: **capped at two digits** while ``requirements/DECISIONS.md`` was already past ``D-100``.
#: It therefore matched a spelling the sheet had essentially stopped using (5 un-hyphenated
#: run labels) and missed the one it uses (241 hyphenated refs, measured 2026-08-31).
#: The optional ``-`` sits AFTER the letter so ``LD-409`` stays
#: excluded by the lookbehind (a letter precedes the ``D``), and ``F-string``/``UTF-8`` stay
#: clean because a digit must follow the hyphen and the letter must not be preceded by one.
_DECISION_REF = re.compile(
    r"(?<![A-Za-z0-9_:!$-])[DSTF]-?\d{1,3}(?![A-Za-z0-9_])(?!:\$?[A-Z]{1,3}\$?\d)"
)

#: A ladder-rung / reader-story label — ``W0``..``W3``, ``R-S2``, "the W-ladder".
_LADDER_REF = re.compile(r"(?<![A-Za-z0-9_-])W[0-3](?![A-Za-z0-9_])|\bR-S\d+\b|\bW-ladder\b")

#: Internal role attribution — "the PM directive", "PM-adopted", "the architect's probe",
#: "Dev's documented call". A consumer cannot consult any of our hats; the decision has to
#: stand on its own stated reason. The lookbehinds keep a time-of-day ("9 PM") legitimate,
#: and the ``\b`` after ``architect`` keeps "architecture" out.
_ROLE_REF = re.compile(r"\bPM\b(?<!\d PM)(?<!\dPM)|\barchitect(?:'s)?\b|\bDev(?:'s)?\b")

#: Internal machinery / process names that are not part of the shipped vocabulary.
_MACHINERY = re.compile(r"\bAST guard\b|\bdogfood\w*", re.IGNORECASE)


#: ``(name, pattern, what to write instead)`` — the enumerated dialect classes (AC2).
DIALECT_PATTERNS = (
    ("issue-id", _ISSUE_ID, "say what changed and why, not which issue changed it"),
    ("private-id", _PRIVATE_ID, "state the fact in consumer terms"),
    ("ac-ref", _AC_REF, "state the criterion itself"),
    ("decision-ref", _DECISION_REF, "state the decision and its reason in plain language"),
    ("ladder-rung", _LADDER_REF, "name the capability, not the tranche that built it"),
    ("role-attribution", _ROLE_REF, "state the rule; a consumer cannot ask the maintainer"),
    ("machinery", _MACHINERY, "name the shipped guard/check a consumer can run"),
)


def dialect_hits(text):
    """Every internal-dialect occurrence in ``text`` as ``[(pattern_name, matched_text)]``."""
    if not isinstance(text, str):
        return []
    hits = []
    for name, pattern, _advice in DIALECT_PATTERNS:
        for match in pattern.finditer(text):
            hits.append((name, match.group(0)))
    return hits


# --------------------------------------------------------------------------- #
# 2. PASS ONE — THE FRONT DOOR: every text a consumer meets before any code.     #
#                                                                              #
#    This pass used to be the two accessor-backed deep docs and nothing else,   #
#    which is why the README, the wheel METADATA fields and the CLI `--help`    #
#    rotted with nobody looking: they were never in scope. Widened in LD-167.   #
# --------------------------------------------------------------------------- #

def cli_group():
    """The live ``larkdocio`` click group, imported at CALL time.

    Deliberately not a module-level import: ``tests/test_cli_logging_config.py`` drops
    ``larkdocio.cli`` from ``sys.modules`` and re-imports it to observe import-time side
    effects, which replaces the group **object**. A module-level binding would leave this
    corpus rendering one object while a caller patched another — so every reader of the group
    (here and in ``tests/front_door.py``) resolves it the same lazy way and they cannot
    disagree.
    """
    from larkdocio.cli import cli

    return cli


def cli_help_pages():
    """``{label: rendered page}`` — ``--help`` for the CLI group and EVERY subcommand.

    Rendered through click's own test runner, not read off the source strings, so the guard
    sees the page a user sees: the usage line, the assembled options section, and each option's
    help wrapped the way click wraps it. A source-literal scan reads the pieces; a consumer
    reads the page.

    The subcommand set is **derived from the group**, so a subcommand added tomorrow enrols
    itself instead of shipping unguarded because nobody widened a literal list.
    """
    import logging

    from click.testing import CliRunner

    group = cli_group()
    # Rendering `<group> <sub> --help` runs the group callback, which configures the shared
    # `larkdocio` logger. A corpus helper must not mutate process-wide logging state, so the
    # logger is restored exactly as found (the test_cli_logging_config.py contract).
    logger = logging.getLogger("larkdocio")
    saved_handlers, saved_level = logger.handlers[:], logger.level
    # COLUMNS is pinned so the wrapped page is deterministic run to run.
    runner = CliRunner(env={"COLUMNS": "80"})
    try:
        pages = {"larkdocio --help": runner.invoke(
            group, ["--help"], prog_name="larkdocio"
        ).output}
        for name in sorted(group.commands):
            pages[f"larkdocio {name} --help"] = runner.invoke(
                group, [name, "--help"], prog_name="larkdocio"
            ).output
    finally:
        logger.handlers[:] = saved_handlers
        logger.setLevel(saved_level)
    return pages


def shipped_docs():
    """``{label: text}`` for every text surface a consumer reaches **through the wheel**.

    Each member is here because a consumer holding only the wheel reads it:

    * ``guide()`` / ``writer_brief()`` / ``release_notes()`` / ``lark_setup()`` — four of the
      five packaged documents, enrolled **as the accessor returns them**, because that is the
      call a consumer makes. (The fifth, ``changelog()``, is a reasoned exclusion — see below.)
      ``lark_setup()`` joined at LD-549 with the document itself: it is the walkthrough a
      brand-new consumer reads before anything else works, which makes it consumer-facing prose
      by the plainest reading of that phrase, so the dialect grep reads it.
    * ``README.md`` — ``pyproject.toml``'s ``readme = "README.md"`` makes it the wheel's
      ``METADATA`` **body**. It is not documentation *about* the shipped package; it *is*
      shipped text, and the first any consumer reads.
    * the ``description`` and ``keywords`` — the wheel's ``Summary`` and ``Keywords`` headers,
      the one line a package index shows and the words a search has to match.
    * ``RELEASE_NOTES.md`` — packaged since the release documents began shipping, and read
      before re-vendoring. Enrolled through ``release_notes()``, which reads the **packaged
      copy** — that is the text a wheel-only consumer has; a drift from the canonical root
      file is ``tests/test_shipped_notes.py``'s job.
    * the rendered CLI ``--help`` for the group and every subcommand — for anyone who
      installed the console command, this is the entire manual.

    One packaged Markdown file is deliberately **out**, and the exclusion is not silent:

    * ``larkdocio/blocks/BLOCK_TYPES.md`` — a *contributor* document (how to add a handler to
      *this* repo's registry). It has no public accessor and neither shipped doc cites it for
      anything a consumer does, so its internal references resolve for exactly the audience
      that reads it.

    The changelog is IN, as ``changelog() (the packaged CHANGELOG.md)``. Until LD-691 the packaged
    ``larkdocio/CHANGELOG.md`` was the internal engineering log and was excluded here for a stated
    reason — it carried internal vocabulary by construction, and grepping it would either fail
    permanently or force a historical record to be rewritten. That reason is upheld and its
    conclusion superseded (maintainer ruling 2, ``D-121`` (3)): the wheel now ships the project's PUBLIC
    changelog in both trees, which is consumer-facing prose, so it is enrolled and held to the
    same dialect as everything else. The internal log stays at the repository root of the
    maintainers' copy and never ships; ``tests/test_release_notes_accessor.py`` measures that it
    still carries the vocabulary that would redden here.
    """
    project = front_door.pyproject()["project"]
    return {
        "guide()": larkdocio.guide(full=True),
        "writer_brief()": larkdocio.writer_brief(),
        "README.md (the wheel METADATA body)": front_door.readme_text(),
        "pyproject description (the wheel Summary)": project["description"],
        "pyproject keywords (the wheel Keywords)": ", ".join(project["keywords"]),
        "release_notes() (the packaged RELEASE_NOTES.md)": larkdocio.release_notes(),
        "changelog() (the packaged CHANGELOG.md)": larkdocio.changelog(),
        "lark_setup() (the packaged LARK_SETUP.md)": larkdocio.lark_setup(),
        **cli_help_pages(),
    }


def shipped_generated_text():
    """``{label: text}`` for the shipped surface a consumer reads that nobody AUTHORED as prose
    — ``capabilities()``'s own bytes, serialized the way a caller prints them.

    **Why it is a sibling of :func:`shipped_docs` rather than a member of it.** ``shipped_docs()``
    is the *authored-prose* corpus: the dialect grep reads it, and so do the front-door
    completeness arms, which cross-check documents against the code they describe. The registry's
    text is already dialect-checked from the other side — every one of its notes is a non-docstring
    literal under ``src/``, which is what :func:`emitted_literals` walks — so enrolling it in
    ``shipped_docs()`` would grep it twice and move guards that have nothing to do with it.

    **It is not a second corpus, and the distinction is the load-bearing one.** A second corpus
    would be a fresh enumeration of *which surfaces ship*, kept beside the one that already
    exists — two lists to drift apart. This is one more surface, defined in the single module that
    owns corpus definitions, for a census that composes the two rather than choosing between
    them: the generated front door is text a consumer reads, so a claim of absence inside it is
    exactly as binding as one in the guide.
    """
    return {
        "capabilities(full=True) (the generated capability census)": json.dumps(
            larkdocio.capabilities(full=True), indent=2, ensure_ascii=False, default=str),
    }


# --------------------------------------------------------------------------- #
# 3. PASS TWO — every emitted string literal in src/ (refusal details, preview  #
#    notes, plan field values, capabilities() registry text, log wording).      #
#                                                                              #
#    Docstrings are excluded here only because pass three walks them by         #
#    introspection; `#` comments are excluded BY CONSTRUCTION (ast never        #
#    yields one), which is the AC6 boundary.                                    #
# --------------------------------------------------------------------------- #

def _docstring_node_ids(tree):
    ids = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None) or []
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            ids.add(id(body[0].value))
    return ids


def emitted_literals():
    """``{label: text}`` for every non-docstring string literal under ``src/larkdocio``."""
    corpus = {}
    for path in sorted(SRC.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        skip = _docstring_node_ids(tree)
        rel = path.relative_to(REPO_ROOT)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in skip
            ):
                corpus[f"{rel}:{node.lineno} (literal)"] = node.value
    return corpus


# --------------------------------------------------------------------------- #
# 4. PASS THREE — the docstrings of PUBLIC symbols, enumerated the way          #
#    capabilities() enumerates: by introspection, not by a hand-kept list.      #
#                                                                              #
#    The seeds are (a) every module the SHIPPED GUIDE tells a consumer to       #
#    import — parsed out of GUIDE.md itself, so a new recipe widens the guard   #
#    automatically — plus (b) the packages/modules `help()` lands on.           #
# --------------------------------------------------------------------------- #

_GUIDE_IMPORT = re.compile(r"^\s*(?:from|import)\s+(larkdocio(?:\.\w+)*)", re.MULTILINE)

#: Seeds a guide recipe does not spell out but `help()` reaches: the three public
#: packages, the node tree a consumer walks, the error taxonomy it catches, and the
#: four packaged-document accessors.
_EXTRA_SEEDS = (
    "larkdocio",
    "larkdocio.common",
    "larkdocio.write",
    "larkdocio.sheets",
    "larkdocio.model",
    # The node-model reference the guide now sends a reader to by name ("help() on it answers
    # which node is a heading, at what level"). Pointing a consumer at a module's docstrings
    # puts them in front of the door, so they are enrolled here — the guard's whole rule is
    # that shipped text a consumer reads is in scope.
    "larkdocio.model.nodes",
    "larkdocio.errors",
    # The taxonomy's AUTHORING site (LD-648). `larkdocio.errors` above is the import path the
    # guide names and stays the seed a consumer's own `help()` call lands on; this second seed
    # is what keeps the taxonomy's own module docstring — the overview of the whole exception
    # family, and the longest consumer-reaching docstring the library ships — inside this
    # corpus after the definitions moved into the shared core. Without it, relocating the file
    # would have taken that text out of the dialect guard's reach without reddening anything.
    "larkdocio.common.errors",
    "larkdocio.capabilities",
    "larkdocio.guide",
    # the modules that define typed values the SHIPPED GUIDE names by name (a guide that
    # says "refused with a typed DimensionSpanError" sends the reader to that class's
    # docstring), but that no recipe imports directly
    "larkdocio.sheets.requests",
    "larkdocio.sheets.write_range",
)


def public_seed_modules():
    """Every module name whose ``help()`` output a consumer can reach."""
    named = set(_GUIDE_IMPORT.findall(larkdocio.guide(full=True)))
    return sorted(named | set(_EXTRA_SEEDS))


def _public_names(module):
    declared = getattr(module, "__all__", None)
    if declared:
        return list(declared)
    return [name for name in dir(module) if not name.startswith("_")]


def public_docstrings():
    """``{label: docstring}`` for every module / class / function / method / property a
    consumer reaches through the public API."""
    corpus = {}
    seen_docs = set()

    def take(obj, label):
        doc = getattr(obj, "__doc__", None)
        if not isinstance(doc, str) or not doc.strip():
            return
        if doc in seen_docs:
            return
        seen_docs.add(doc)
        corpus[label] = doc

    for modname in public_seed_modules():
        try:
            module = importlib.import_module(modname)
        except ImportError:  # pragma: no cover — a guide typo is caught by test_guide.py
            continue
        take(module, f"help({modname})")
        for name in _public_names(module):
            obj = getattr(module, name, None)
            if obj is None or inspect.ismodule(obj):
                continue
            owner = getattr(obj, "__module__", "") or ""
            if not owner.startswith("larkdocio"):
                continue
            take(obj, f"{modname}.{name}")
            if not inspect.isclass(obj):
                continue
            for attr, member in vars(obj).items():
                if attr.startswith("_"):
                    continue
                if isinstance(member, property):
                    take(member.fget, f"{modname}.{name}.{attr}")
                elif isinstance(member, (staticmethod, classmethod)):
                    take(member.__func__, f"{modname}.{name}.{attr}")
                else:
                    take(member, f"{modname}.{name}.{attr}")
    return corpus


# --------------------------------------------------------------------------- #
# 5. PASS FOUR — RUNTIME VALUES, not source literals. This is where F7's worst  #
#    instance lived: `plan.revision_guard_detail` is composed at runtime, so a  #
#    source-literal grep alone can miss a value a consumer is handed.           #
# --------------------------------------------------------------------------- #

def _json_strings(label, value, out, depth=0):
    if depth > 12:
        return
    if isinstance(value, str):
        out[label] = value
    elif isinstance(value, dict):
        for key, sub in value.items():
            _json_strings(f"{label}.{key}", sub, out, depth + 1)
    elif isinstance(value, (list, tuple)):
        for index, sub in enumerate(value):
            _json_strings(f"{label}[{index}]", sub, out, depth + 1)


def capabilities_strings():
    """``{label: text}`` for every string inside :func:`larkdocio.capabilities`' output.

    **Both doors.** The registry has two shapes a consumer reads — the no-argument summary
    and the whole payload behind ``full=True`` — and the dialect guard has to grep both, or
    the front door's own text would be the one shipped string nothing checks. Labelled by the
    call that returns it, so a finding names the door it came from.
    """
    out = {}
    _json_strings("capabilities(full=True)", larkdocio.capabilities(full=True), out)
    _json_strings("capabilities()", larkdocio.capabilities(), out)
    return out


def _docx_plan_dicts():
    """Real docx plans, serialized — armed guard, unarmed guard, and a refusal."""
    from larkdocio.model import PageNode, Text, TextNode
    from larkdocio.write.model import Anchor, EditRequest
    from larkdocio.write.preview import dry_run

    root = PageNode(
        title=[Text("Doc")],
        children=[TextNode(content=[Text("the target line")], block_id="blk1")],
        block_id="root",
    )
    requests = [
        EditRequest(anchor=Anchor(quote="the target line"), replacement="new text"),
        EditRequest(anchor=Anchor(quote="no such line anywhere"), replacement="new text"),
    ]
    return {
        "docx dry_run(...).to_dict() [guard unavailable]": dry_run(requests, root).to_dict(),
        "docx dry_run(..., document_revision_id=7).to_dict() [guard active]": dry_run(
            requests, root, document_revision_id=7
        ).to_dict(),
    }


def _sheets_plan_dicts():
    """Real sheets plans, serialized — both staleness-guard statuses + a refusal."""
    from test_sheets_write_apply import FakeSheetGateway  # tests/ is on sys.path

    from larkdocio.sheets.write_apply import ValueWriteRequest, dry_run

    values = {"s1!A1:A1": [["before"]]}
    requests = [
        ValueWriteRequest.for_a1("s1!A1:A1", [["after"]]),
        ValueWriteRequest.for_a1("s1!A1:A1", [["a", "b"]]),  # shape mismatch → a refusal
    ]
    out = {}
    for label, revision in (("active", 12), ("unavailable", 0)):
        gateway = FakeSheetGateway(revision=revision, values=dict(values))
        plan = dry_run(requests, gateway, "shtTOKEN")
        out[f"sheets dry_run(...).to_dict() [guard {label}]"] = plan.to_dict()
    return out


def runtime_json_strings():
    """``{label: text}`` for every string VALUE in a real plan's / log's JSON.

    Built from actual :func:`dry_run` output on both surfaces (armed and unarmed staleness
    guard, plus a refused entry) and from :func:`larkdocio.capabilities`, so the guard reads
    what a consumer is handed rather than what the source happens to spell.
    """
    out = dict(capabilities_strings())
    for label, payload in {**_docx_plan_dicts(), **_sheets_plan_dicts()}.items():
        # Round-trip through JSON so the guard reads exactly the bytes a consumer relays.
        _json_strings(label, json.loads(json.dumps(payload)), out)
    return out


# --------------------------------------------------------------------------- #
# 5b. THE COPYABLE SKILL PACK — consumer-reaching text that does NOT ship in    #
#     the wheel, so it is a corpus of its own rather than a fifth pass.         #
# --------------------------------------------------------------------------- #

#: The router pack a consumer repo installs from ``consumers/`` (never from the wheel — an
#: agent harness discovers skills as FILES in the working repo).
SKILL_PACK = REPO_ROOT / "consumers" / "skills"


def skill_pack_files():
    """Every file in the pack — a **directory sweep**, so a new router cannot be missed.

    A hand-listed set is the very defect the pack exists not to be: one more copy of the
    truth, rotting the moment somebody adds a file and forgets the list.
    """
    if not SKILL_PACK.is_dir():
        return []
    return sorted(path for path in SKILL_PACK.rglob("*") if path.is_file())


def skill_pack_docs():
    """``{repo-relative path: text}`` for every file in the copyable skill pack.

    Deliberately **not** folded into :func:`consumer_corpus`. That corpus's whole rule is
    *text a consumer reaches through the wheel*, and the pack is copied into the consumer's
    repository instead of packaged — enrolling it there would falsify the definition every
    other reader of that function relies on. The guards that need it
    (``tests/test_consumer_skill_pack.py`` and the citation resolver in
    ``tests/test_guide_citation_resolution.py``) ask for it by name.
    """
    return {
        f"consumers/skills/{path.relative_to(SKILL_PACK).as_posix()}":
            path.read_text(encoding="utf-8")
        for path in skill_pack_files()
    }


# --------------------------------------------------------------------------- #
# 6. THE CORPUS                                                                #
# --------------------------------------------------------------------------- #

def consumer_corpus():
    """``{label: text}`` — every consumer-reaching text surface, all four passes."""
    corpus = {}
    corpus.update(shipped_docs())
    corpus.update(emitted_literals())
    corpus.update(public_docstrings())
    corpus.update(runtime_json_strings())
    return corpus


def corpus_dialect_report(corpus=None):
    """``[(label, pattern_name, matched, snippet)]`` for every hit in the corpus."""
    corpus = consumer_corpus() if corpus is None else corpus
    report = []
    for label, text in corpus.items():
        for name, pattern, _advice in DIALECT_PATTERNS:
            for match in pattern.finditer(text):
                start = max(0, match.start() - 60)
                end = min(len(text), match.end() + 40)
                snippet = " ".join(text[start:end].split())
                report.append((label, name, match.group(0), snippet))
    return report
