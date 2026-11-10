"""LD-699 (round 2 of the public-export review, R13) — each repository label says where its path lives.

The label "in the dev repo" used to mean both "the maintainers' private record" and "the public
clone", so a reader could not tell a file they can open from one they cannot. It is now two
labels (``larkdocio.common.citations``):

* **in the source repository** — the path is in every clone, the public one included;
* **in the dev repo** — the path is in the maintainers' private record only.

**What this module checks, exactly.** Every occurrence of either label in:

1. every ``.py`` file under ``src/`` — its comments, its docstrings **and its executable string
   literals**, read with the tokenizer, with implicitly concatenated literals joined the way
   Python joins them at run time (so a label split across two literals is one label);
2. every ``.md`` file under ``src/`` — but in the two packaged release records,
   ``src/larkdocio/RELEASE_NOTES.md`` and ``src/larkdocio/CHANGELOG.md``, only the topmost
   (un-cut) section: a released section is history and is not rewritten after the fact;
3. the root documents ``README.md``, ``LARK_SETUP.md``, ``PERMISSIONS.md``, ``DRIVE.md``,
   ``BASE.md``, ``SHEETS.md``, ``BLOCKS.md`` and ``TOOLS.md``;
4. every string value in the generated ``capabilities(full=True)`` registry.

Fenced code blocks in Markdown are skipped, and so is a label in quotation marks (a mention of
the label, not a use of it).

**The subject of a label** is the repository paths cited just before it in the same run of text
— back to the previous label, and for "in the source repository" at most :data:`WINDOW`
characters (``dev_repo()`` labels a whole citation private when any one of its paths is, so the
private label may sit after a long list) — plus the first path cited just after it: always for
"in the dev repo" (``in the dev repo (requirements/…)``), and for "in the source repository"
only when none precede it. A run of text is one Markdown paragraph or table row, one
comment block, or one string expression. **The rule:** "in the dev repo" must have at least one
private path among its subjects, and "in the source repository" must have none. A label whose
run names no path is not checked (but the corpus is asserted to name subjects for most labels,
so the check cannot pass by finding none).

**Where a path lives** is decided by :func:`lives_in` from the path itself. In the private
repository a further arm holds that decision to the export's own allow-list
(``dev/public-export/export.py``): every cited path that exists here is "source" exactly when the
export would ship it.
"""
import importlib.util
import io
import re
import tokenize
from pathlib import Path

import pytest

import private_tree
from larkdocio.common.citations import (
    DEV_REPO_LABEL,
    REPO_LABELS,
    SOURCE_REPO_LABEL,
    dev_repo,
    is_labelled,
    label_for,
)

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
ROOT_DOCS = ("README.md", "LARK_SETUP.md", "PERMISSIONS.md", "DRIVE.md", "BASE.md", "SHEETS.md",
             "BLOCKS.md", "TOOLS.md")
RELEASE_RECORDS = ("src/larkdocio/RELEASE_NOTES.md", "src/larkdocio/CHANGELOG.md")

PUBLIC_CAPTURE = "tests/captures/ld463-date-only/captures/ld463-01-date-only-zone.json"
PRIVATE_RECORD = "dev/base-study/captures/a.json"

#: How far back (in flattened characters) a label looks for the paths it is talking about.
WINDOW = 200

_PRIVATE_ROOTS = ("dev", "progress", "requirements", "process", ".claude", "docs")
_PRIVATE_DOCS = ("PROJECT.md", "CLAUDE.md", "AGENTS.md", "ARCHIVE.md", "DECISIONS.md")
_SHIPPED_SCRIPTS = ("scripts/verify.sh", "scripts/sync-packaged-notes.sh")

_PATH = re.compile(
    r"(?<![\w./-])("
    r"(?:dev|progress|requirements|process|\.claude|docs|tests|scripts|consumers|src)/[\w.-]+(?:/[\w.-]+)*/?"
    r"|(?:PROJECT|CLAUDE|AGENTS|ARCHIVE|DECISIONS|README|BLOCKS|SHEETS|PERMISSIONS|BASE|DRIVE|TOOLS"
    r"|LARK_SETUP|RELEASE_NOTES|CHANGELOG)\.md)(?![\w/-])")
_LABEL = re.compile("|".join(re.escape(label) for label in REPO_LABELS), re.IGNORECASE)
_ABBREVIATED = re.compile(r"\((?:the )?(?:dev|source) repo\)", re.IGNORECASE)


def lives_in(path):
    """``"private"`` or ``"source"`` — where a cited repository path lives, from the path."""
    path = path.rstrip("/.")
    if path.split("/", 1)[0] in _PRIVATE_ROOTS or path in _PRIVATE_DOCS:
        return "private"
    if path.startswith("scripts/") and path not in _SHIPPED_SCRIPTS:
        return "private"
    return "source"


# --------------------------------------------------------------------------- #
# Reading the corpus into runs of text                                         #
# --------------------------------------------------------------------------- #

def _flat(text):
    return re.sub(r"\s+", " ", re.sub(r"[*`]+", "", text)).strip()


_QUOTES = re.compile(r"""(?:^|(?<=\s))[rbfuRBFU]{0,2}(?:'''|\"\"\"|'|")|(?:'''|\"\"\"|'|")(?=\s|$)""")


def python_runs(source):
    """Comment blocks, and string expressions with adjacent literals joined — via ``tokenize``."""
    runs, current, kind = [], [], None
    middle = {getattr(tokenize, "FSTRING_MIDDLE", -1), getattr(tokenize, "FSTRING_END", -1)}

    def flush():
        nonlocal current, kind
        if current:
            runs.append((kind, current))
        current, kind = [], None

    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT:
            if kind != "comment":
                flush()
            kind = "comment"
            current.append(tok.string.lstrip("#:").strip())
        elif tok.type == tokenize.STRING or tok.type == getattr(tokenize, "FSTRING_START", -1):
            if kind != "string":
                flush()
            kind = "string"
            current.append(tok.string)
        elif tok.type in middle and kind == "string":
            current[-1] += tok.string
        elif tok.type in (tokenize.NL, tokenize.NEWLINE) and kind == "comment":
            continue
        elif tok.type == tokenize.NL and kind == "string":
            continue
        else:
            flush()
    flush()
    out = []
    for kind, parts in runs:
        if kind == "string":
            parts = [_QUOTES.sub("", p) for p in parts]
            out.append(_flat("".join(parts)))
        else:
            out.append(_flat(" ".join(parts)))
    return [r for r in out if r]


def markdown_runs(text):
    runs, in_fence, para = [], False, []
    for line in text.splitlines():
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.lstrip().startswith("|"):
            runs.append(_flat(line))
        elif not line.strip():
            runs.append(_flat(" ".join(para)))
            para = []
        else:
            para.append(line)
    runs.append(_flat(" ".join(para)))
    return [r for r in runs if r]


def _top_section(text):
    starts = [m.start() for m in re.finditer(r"^## \[", text, re.M)]
    return text[starts[0]:starts[1]] if len(starts) > 1 else text


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, (list, tuple)):
        for value in node:
            yield from _strings(value)


def corpus():
    """``{source name: [run of text, …]}`` — the scope stated in the module docstring."""
    out = {}
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" not in path.parts:
            out[path.relative_to(REPO).as_posix()] = python_runs(path.read_text(encoding="utf-8"))
    for path in sorted(SRC.rglob("*.md")):
        rel = path.relative_to(REPO).as_posix()
        if ".egg-info" in rel:
            continue
        text = path.read_text(encoding="utf-8")
        out[rel] = markdown_runs(_top_section(text) if rel in RELEASE_RECORDS else text)
    for name in ROOT_DOCS:
        out[name] = markdown_runs((REPO / name).read_text(encoding="utf-8"))
    import larkdocio
    out["capabilities(full=True)"] = [_flat(s) for s in _strings(larkdocio.capabilities(full=True))]
    return out


def labels_in(run):
    """``[(label, subjects)]`` for every label used (not quoted) in one run of text."""
    found, previous_end = [], 0
    for match in _LABEL.finditer(run):
        start, end = match.span()
        before = run[max(0, start - 2):start]
        if before.rstrip("(").endswith(('"', "“", "'")):
            previous_end = end
            continue
        # Asymmetric on purpose, like front_door.mislabelled_citations: the private label looks
        # back to the previous label (dev_repo() labels a whole citation private when ANY of
        # its paths is), the source label only WINDOW characters (it must name no private path).
        private_label = match.group(0).lower() == DEV_REPO_LABEL
        lo = previous_end if private_label else max(previous_end, start - WINDOW)
        subjects = [m.group(1) for m in _PATH.finditer(run[lo:start])]
        following = _PATH.search(run[end:end + 40 if subjects else end + 80])
        if following and (private_label or not subjects):
            subjects.append(following.group(1))
        found.append((match.group(0).lower(), tuple(subjects)))
        previous_end = end
    return found


def violations(runs_by_source):
    bad, total, with_subject = [], 0, 0
    for source, runs in runs_by_source.items():
        for run in runs:
            for label, subjects in labels_in(run):
                total += 1
                if not subjects:
                    continue
                with_subject += 1
                private = [s for s in subjects if lives_in(s) == "private"]
                if label == DEV_REPO_LABEL and not private:
                    bad.append(f"{source}: 'in the dev repo' names only source paths {subjects}")
                if label == SOURCE_REPO_LABEL and private:
                    bad.append(f"{source}: 'in the source repository' names private {private}")
            # LD-699 QA: an ABBREVIATED label ("(dev repo)") escaped the classification above, which
            # matches only the full phrases. A label is written in full or not at all.
            if _ABBREVIATED.search(run):
                bad.append(f"{source}: abbreviated label {_ABBREVIATED.search(run).group(0)!r} — "
                           "write '(in the dev repo)' or '(in the source repository)'")
    return bad, total, with_subject


# --------------------------------------------------------------------------- #
# The formatter                                                               #
# --------------------------------------------------------------------------- #

def test_a_capture_every_clone_carries_is_in_the_SOURCE_repository():
    assert dev_repo(PUBLIC_CAPTURE) == f"{PUBLIC_CAPTURE} ({SOURCE_REPO_LABEL})"


def test_a_private_record_keeps_the_dev_repo_label():
    assert dev_repo(PRIVATE_RECORD) == f"{PRIVATE_RECORD} ({DEV_REPO_LABEL})"


def test_one_private_path_makes_the_whole_citation_private():
    text = f"{PUBLIC_CAPTURE} and {PRIVATE_RECORD}"
    assert label_for(text) == DEV_REPO_LABEL
    assert dev_repo(text).endswith(f"({DEV_REPO_LABEL})")


@pytest.mark.parametrize("path", [PUBLIC_CAPTURE, PRIVATE_RECORD])
def test_either_label_counts_as_labelled_so_the_formatter_stays_idempotent(path):
    once = dev_repo(path)
    assert is_labelled(once)
    assert dev_repo(once) == once
    assert sum(once.count(label) for label in REPO_LABELS) == 1


def test_a_text_with_no_repository_path_is_untouched():
    assert dev_repo("captures/a.json") == "captures/a.json"
    assert label_for("nothing here") is None


# --------------------------------------------------------------------------- #
# The corpus                                                                   #
# --------------------------------------------------------------------------- #

def test_the_corpus_is_the_stated_scope_and_is_not_vacuous():
    runs = corpus()
    for name in ROOT_DOCS + ("src/larkdocio/GUIDE.md", "src/larkdocio/permissions.py",
                             "capabilities(full=True)"):
        assert name in runs, name
    _, total, with_subject = violations(runs)
    assert total > 200, total
    assert with_subject > total // 2, (with_subject, total)
    used = {label for rs in runs.values() for r in rs for label, _ in labels_in(r)}
    assert used == set(REPO_LABELS)


def test_every_label_says_where_its_path_lives():
    bad, _, _ = violations(corpus())
    assert not bad, f"{len(bad)} mislabelled citation(s):\n" + "\n".join(bad[:40])


# --- the check bites, both directions, in a literal and in a matrix -------- #

_LITERAL_PRIVATE_AS_SOURCE = (
    'EVIDENCE = (\n    "the upload answered code:0 "\n'
    '    "(dev/media-spike/captures/203-x.json, in the source "\n    "repository)")\n')
_LITERAL_SOURCE_AS_DEV = (
    'EVIDENCE = (\n    "the merge refused "\n'
    '    "(tests/captures/sheets-merge-variant-probe/captures/01-x.json "\n'
    '    "in the dev repo).")\n')
_MATRIX_PRIVATE_AS_SOURCE = (
    "| op | route | evidence |\n|---|---|---|\n"
    "| upload | POST | `dev/media-spike/captures/203-x.json` (in the source repository) |\n")
_MATRIX_SOURCE_AS_DEV = (
    "| op | route | evidence |\n|---|---|---|\n"
    "| list | GET | `tests/captures/editions-spike/captures/07-x.json` (in the dev repo) |\n")


@pytest.mark.parametrize("runs", [
    python_runs(_LITERAL_PRIVATE_AS_SOURCE), python_runs(_LITERAL_SOURCE_AS_DEV),
    markdown_runs(_MATRIX_PRIVATE_AS_SOURCE), markdown_runs(_MATRIX_SOURCE_AS_DEV),
], ids=["literal-private-as-source", "literal-source-as-dev",
        "matrix-private-as-source", "matrix-source-as-dev"])
def test_the_check_BITES(runs):
    bad, total, _ = violations({"crafted": runs})
    assert total == 1 and len(bad) == 1, (runs, bad)


@pytest.mark.parametrize("runs", [
    python_runs(_LITERAL_PRIVATE_AS_SOURCE.replace('in the source "\n    "repository',
                                                   'in the dev "\n    "repo')),
    markdown_runs(_MATRIX_SOURCE_AS_DEV.replace("in the dev repo", "in the source repository")),
], ids=["literal-correct", "matrix-correct"])
def test_the_check_is_SILENT_on_the_correct_label(runs):
    bad, total, _ = violations({"crafted": runs})
    assert total == 1 and not bad, (runs, bad)


def test_a_quoted_label_is_a_mention_not_a_use():
    runs = markdown_runs('A path labelled "(in the dev repo)" under `tests/captures/x.json`.\n')
    assert violations({"crafted": runs})[1] == 0


# --- the path rule agrees with what the export ships ----------------------- #

@private_tree.citations
def test_lives_in_agrees_with_the_export_allow_list():
    spec = importlib.util.spec_from_file_location(
        "_export", REPO / "dev" / "public-export" / "export.py")
    export = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(export)
    cited = {s for rs in corpus().values() for r in rs for _, subs in labels_in(r) for s in subs}
    checked, disagree = 0, []
    for path in sorted(cited):
        clean = path.rstrip("/.")
        if not (REPO / clean).exists():
            continue
        checked += 1
        if (REPO / clean).is_dir():
            ships = export.included(clean + "/") or any(
                p.startswith(clean + "/") for p in export.INCLUDE)
        else:
            ships = export.included(clean) and clean not in export.PRIVATE_ONLY
        if (lives_in(clean) == "source") != bool(ships):
            disagree.append((clean, lives_in(clean), ships))
    assert checked > 50, checked
    assert not disagree, disagree


def test_an_ABBREVIATED_label_is_rejected():
    """LD-699 QA: six "(dev repo)" labels in SHEETS.md cited public captures and the guard, which
    matches only the full phrases, never saw them."""
    bad, _, _ = violations({"fixture.md": ["a capture `tests/captures/x/captures/1.json` (dev repo)"]})
    assert any("abbreviated label" in b for b in bad)
    bad, _, _ = violations({"fixture.md": ["a capture `tests/captures/x/captures/1.json` (in the source repository)"]})
    assert not any("abbreviated label" in b for b in bad)
