"""THE FRONT DOOR — the text a consumer meets first, as parseable data.

Why this module exists
----------------------
``pyproject.toml``'s ``description`` is the wheel's ``Summary`` field and its ``readme =
"README.md"`` makes the root ``README.md`` the wheel's ``METADATA`` **body**. Both are
therefore *shipped strings*, read before any deep doc — and both had rotted: the summary
still called writeback "reserved" fourteen releases after the writer shipped, the keywords
omitted two whole surfaces, the options list omitted two real flags, the layout table
omitted eight modules, one pointer sent readers to a file that explicitly denies carrying
what was claimed for it, and a hard-coded test count was stale by more than five times.

The claims did not decay so much as they were never in scope: the drift guards covered
``guide()`` and ``writer_brief()``, and nothing covered the front door.

Everything here is a **pure function over text** — no assertions. That is deliberate:

* the guards in ``tests/test_front_door_truth.py`` call them over the real files, and
* the same functions are called over **synthetic** text to prove each guard actually bites
  (a cross-check that cannot be shown red is not a cross-check).

Every comparison is derived from the thing it describes — click's real params, the real
top level of ``src/larkdocio``, the real ``package-data`` table, the real surface registry —
so none of it can be satisfied by editing a list in this file.
"""
import ast
import contextlib
import io
import os
import pathlib
import posixpath
import re
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import tokenize
import tomllib
import zipfile

from doc_prose import prose

# --------------------------------------------------------------------------
# LD-660 — THE CROSS-WORKER LOCK, PORTABLE AND STILL A REAL LOCK. The shared
# build artifacts below are produced ONCE per run and consumed by many xdist
# workers, so the lock is not decoration: a no-op fallback would reintroduce a
# genuine race under the default `-n auto`. `fcntl` is POSIX-only, so the
# import is dispatched on the OS family and each branch takes an EXCLUSIVE
# kernel lock on the same file — `flock` on POSIX (byte-for-byte what ran
# before), `msvcrt.locking` on Windows. There is no third branch and no
# silent pass-through: an OS with neither raises ImportError at import time,
# loudly, which is the correct outcome for a suite that cannot serialise.
#
# HONEST SCOPE: only the POSIX branch is EXERCISED here (this repo's CI and
# every developer host is POSIX; `os.name == "nt"` is `pragma: no cover`).
# The Windows branch is written and reviewable, NOT verified — nothing in this
# change claims the suite passes on Windows (LD-669 owns whether a Windows CI
# job exists, which is what would verify it). One further difference worth
# knowing: `msvcrt.LK_LOCK` retries for ~10s and then raises, where `flock`
# blocks indefinitely, so a Windows run under contention fails loudly rather
# than waiting — again, loud beats fake.
# --------------------------------------------------------------------------
if os.name == "nt":  # pragma: no cover - Windows; no POSIX host takes this branch
    import msvcrt

    def _lock_exclusive(handle):
        handle.write(" ")            # LK_LOCK needs a byte range that exists
        handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)

    def _lock_release(handle):
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock_exclusive(handle):
        fcntl.flock(handle, fcntl.LOCK_EX)

    def _lock_release(handle):
        fcntl.flock(handle, fcntl.LOCK_UN)


@contextlib.contextmanager
def shared_artifact_lock(path):
    """Hold an exclusive cross-process lock on ``path`` for the body's duration.

    The one seam both shared-artifact producers below go through, so the
    platform dispatch is written once and any future producer inherits it.
    """
    with open(path, "w", encoding="utf-8") as handle:
        _lock_exclusive(handle)
        try:
            yield handle
        finally:
            _lock_release(handle)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src" / "larkdocio"
README = REPO_ROOT / "README.md"
PYPROJECT = REPO_ROOT / "pyproject.toml"

#: The label a citation of a file the wheel does NOT carry must wear, so a wheel-only
#: consumer knows before clicking. TRANSFORMED by LD-699 (supersession.md § A.1): the REASON —
#: one predictable phrase per meaning, never a synonym — stands; the CONCLUSION "one phrase"
#: became TWO, because the one phrase had two meanings. ``in the dev repo`` is now reserved for
#: the maintainers' private record; ``in the source repository`` is a file any clone carries.
#: Either one answers "was the reader warned this is not in the wheel?", so every check below
#: accepts :data:`REPO_LABELS`; ``tests/test_citation_label_reservation.py`` holds which is which.
DEV_REPO_LABEL = "in the dev repo"
SOURCE_REPO_LABEL = "in the source repository"
REPO_LABELS = (DEV_REPO_LABEL, SOURCE_REPO_LABEL)


def labelled(scope_prose):
    """Whether flattened ``scope_prose`` carries either of :data:`REPO_LABELS`."""
    return any(prose(label) in scope_prose for label in REPO_LABELS)

#: The heading that opens the CONTRIBUTOR half of the README. Above it the reader is assumed
#: to hold nothing but an installed wheel; below it they are assumed to have a clone. The
#: split is the fix for the audience defect: the claims were corrected once already, and the
#: document was *still* wrong because its first instruction (``./setup.sh``) is impossible for
#: the reader ``pip show`` hands it to.
DEVELOPMENT_HEADING = "## Developing larkdocio"

#: How far into the ``METADATA`` body ``print(larkdocio.guide())`` may sit and still count as
#: "near the top". Generous on purpose — the defect was never depth, it was that the one line
#: that matters appeared **nowhere** as code, at any depth, in 322 lines.
#:
#: LD-351 raised this 32→33: the opening enumeration absorbed the sixth surface (Drive), which
#: added exactly one wrapped line to a paragraph that already ran flush against the budget. The
#: guard's intent — the guide line reads near the top — is unchanged; the threshold tracks the
#: legitimately-larger opening.
#:
#: LD-440 raised it 33→38 for the same reason and one further one: the opening census now names
#: contacts and the three Drive WRITE legs (it claimed drive was read-only), which is five more
#: wrapped lines of paragraph. The threshold tracks a census that is now DERIVED-CHECKED against
#: ``capabilities()`` — it may only grow when a surface ships, and the count itself is no longer
#: stated. It is a budget, never a target.
GUIDE_LINE_BUDGET = 38


# --------------------------------------------------------------------------- #
# 0. The sources of truth                                                      #
# --------------------------------------------------------------------------- #

def pyproject():
    """The parsed ``pyproject.toml``."""
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def readme_text():
    """The root ``README.md`` — the wheel's ``METADATA`` body."""
    return README.read_text(encoding="utf-8")


def packaged_doc_paths():
    """Repo-relative paths of every file the wheel carries as package data.

    Derived from ``[tool.setuptools.package-data]`` — never hand-listed, so packaging a new
    doc automatically excuses its citations from the dev-repo label.
    """
    table = pyproject().get("tool", {}).get("setuptools", {}).get("package-data", {})
    paths = set()
    for package, patterns in table.items():
        package_dir = pathlib.Path("src", *package.split("."))
        for pattern in patterns:
            for match in (REPO_ROOT / package_dir).glob(pattern):
                paths.add(match.relative_to(REPO_ROOT).as_posix())
    return paths


def required_surface_keywords():
    """The keyword tokens the shipped surface registry demands, derived from it.

    ``capabilities()`` names its surfaces ``docx-read``, ``docx-comments-read``,
    ``sheets-read``, ``sheets-write``… — so the surface *vocabulary* is already code.
    Generic tokens are dropped: ``read`` does not discriminate anything a document toolkit
    does, and ``embedded``/``deep`` qualify a flag rather than name a surface. What remains
    (``docx``, ``comments``, ``sheets``, ``write``) is exactly what a searcher would type,
    and a new surface family widens the requirement on its own.
    """
    import larkdocio

    generic = {"read", "embedded", "deep"}
    tokens = set()
    for surface_id in larkdocio.capabilities(full=True)["surfaces"]:
        tokens.update(part for part in surface_id.split("-") if part not in generic)
    return tokens


#: Phrases that DENY a write. They are absolute in shape, which is exactly why they rot in
#: silence: the sentence stays true-looking long after the surface it denies has shipped.
#: ``larkdocio.__doc__`` carried *"It writes rows and it does not write the schema"* through
#: fifteen shipped base-schema-write operations, and *"Read-only"* about ``drive/`` through four
#: shipped Drive write surfaces (LD-474).
WRITE_DENIALS = (
    "does not write",
    "doesn't write",
    "cannot write",
    "never writes",
    "writes nothing",
    "read-only",
    "read only",
    "does not create",
    "creates nothing",
)


def writing_domains():
    """``{domain}`` for every surface ``capabilities()`` reports in ``write`` mode.

    Derived, so a **new** write surface widens the front-door requirement on its own — which is
    the whole point: the claim that rotted did so because nothing connected it to the registry.
    """
    import larkdocio

    return {surface["domain"]
            for surface in larkdocio.capabilities(full=True)["surfaces"].values()
            if surface.get("mode") == "write" and surface.get("domain")}


def front_door_blocks(doc=None):
    """``larkdocio.__doc__`` as its per-surface **bullets**, plus the surrounding prose.

    Bullet granularity is what the real rot demanded. Both LD-474 defects put the denial in a
    different *sentence* from the surface word — ``base``'s in *"It writes rows and it does not
    write the schema"* (the word "base" is two sentences back, in the bullet's opening) and
    ``drive``'s in a bare *"Read-only;"* — so a sentence-scoped guard would have passed the
    exact paragraph it exists to catch. A bullet is the unit a reader attributes a claim to.
    """
    import re

    import larkdocio

    text = doc if doc is not None else (larkdocio.__doc__ or "")
    text = text.replace("``", " ").replace("**", "")
    blocks, current = [], []
    for line in text.splitlines():
        if line.startswith("* "):
            if current:
                blocks.append(" ".join(current))
            current = [line[2:]]
        elif line.strip():
            current.append(line.strip())
        else:
            if current:
                blocks.append(" ".join(current))
            current = []
    if current:
        blocks.append(" ".join(current))
    return [re.sub(r"\s+", " ", block).strip() for block in blocks if block.strip()]


def front_door_write_denials(doc=None):
    """``[(domain, phrase, block)]`` — every front-door block that denies a write about a
    domain the registry reports a WRITE surface for.

    A block *names* a domain when the domain word appears in it, so this is word-level like the
    ``Summary`` check: it owes the reader truth, never a house style. To say what a single
    operation does not do, **name the operation and the mechanism** — *"the walk itself issues
    no call on the write pair"* — rather than reaching for an absolute the registry can
    contradict.
    """
    domains = writing_domains()
    offenders = []
    for block in front_door_blocks(doc):
        lowered = block.lower()
        for phrase in WRITE_DENIALS:
            if phrase not in lowered:
                continue
            for domain in sorted(domains):
                if domain in lowered:
                    offenders.append((domain, phrase, block[:160]))
    return offenders


def real_top_level():
    """Every top-level module/package of ``src/larkdocio``, as the README would cite it.

    Sub-packages are directories; modules are ``*.py`` minus ``__init__.py`` (it declares
    the package, it is not a surface a reader navigates to).
    """
    names = set()
    for entry in SRC.iterdir():
        if entry.name.startswith(("_", ".")):
            continue
        if entry.is_dir():
            names.add(f"src/larkdocio/{entry.name}/")
        elif entry.suffix == ".py":
            names.add(f"src/larkdocio/{entry.name}")
    return names


def click_options(command_path=()):
    """Every option string click really defines on ``larkdocio`` / a subcommand.

    ``command_path`` is empty for the top-level group, or ``("download",)`` for a
    subcommand. ``--help`` is excluded: click adds it at parse time and no README documents
    it.
    """
    import click

    from larkdocio.cli import cli

    command = cli
    for name in command_path:
        command = command.commands[name]
    opts = set()
    for param in command.params:
        if not isinstance(param, click.Option):
            continue
        opts.update(param.opts)
        opts.update(param.secondary_opts)
    return opts - {"--help"}


def all_command_options():
    """``{label: option strings}`` for the CLI group **and every subcommand**.

    Derived from ``cli.commands`` for the same reason the ``--help`` enrolment is: a
    subcommand added later must widen what the front door owes a reader on its own, rather
    than waiting for someone to notice a literal list.
    """
    from larkdocio.cli import cli

    covered = {"larkdocio": click_options()}
    for name in sorted(cli.commands):
        covered[f"larkdocio {name}"] = click_options((name,))
    return covered


#: An option token as click prints it in an ``Options:`` section — ``-o, --output TEXT``.
_HELP_OPTION = re.compile(r"^\s{2,}(-[\w-]+(?:,\s+--[\w-]+)*)", re.MULTILINE)


def help_page_options(page):
    """The option strings a **rendered** ``--help`` page shows, minus ``--help`` itself.

    Read off the page rather than off ``command.params`` on purpose: the page is what a user
    has, and the two can legitimately differ (a ``hidden=True`` option is a real param that no
    page shows). Comparing them is how a documented-but-invisible flag gets caught.
    """
    body = page.split("Options:", 1)
    if len(body) == 1:
        return set()
    opts = set()
    for match in _HELP_OPTION.finditer(body[1]):
        opts.update(token.strip() for token in match.group(1).split(","))
    return opts - {"--help"}


#: ``larkdocio`` used as a COMMAND — not as part of ``update_larkdocio.sh`` and not inside a
#: path or a wheel filename. The lookbehind is the whole point: it is what keeps the consumer
#: refresh script's own ``--check`` from reading as a phantom larkdocio flag.
_INVOCATION = re.compile(r"(?<![\w./-])larkdocio\s+(?P<tail>.*)")

#: An option is a **separate word**. Anchoring on the preceding whitespace is what keeps
#: ``larkdocio-1.20.0-py3-none-any.whl`` — printed all over the consuming section, and a
#: hyphen-rich string — from reading as the flags ``-py3``/``-none``/``-any``.
_OPTION_TOKEN = re.compile(r"(?:(?<=\s)|^)(--?[A-Za-z][\w-]*)")


def invocation_option_tokens(text):
    """Option tokens the doc shows being **passed to the ``larkdocio`` command**.

    Wider than the bullet lists (it reads the copy-paste invocations too) and narrower than a
    bare ``--\\w+`` sweep, because a doc that documents a *consumer's* script alongside this
    CLI is not claiming that script's flags are ours. A phantom check that could not tell the
    difference would report a permanent false hit and be deleted.
    """
    tokens = set()
    for line in text.splitlines():
        match = _INVOCATION.search(line)
        if match:
            tokens.update(_OPTION_TOKEN.findall(match.group("tail")))
    return tokens


def description_surface_gaps(description, required=None):
    """The surface words :func:`required_surface_keywords` demands that ``description`` omits.

    **Word-level by design, not phrasing-level.** The ``Summary`` is one line of human prose
    and the guard's business is coverage, not house style: any wording that contains the
    surface's own word passes, so the door can be rewritten freely and still be checked. What
    it forecloses is a whole surface shipping unmentioned in the line a package index shows.
    """
    required = required_surface_keywords() if required is None else required
    lowered = description.lower()
    return sorted(word for word in required if word.lower() not in lowered)


# --------------------------------------------------------------------------- #
# 1. Markdown shredding — sections, paragraphs, citations                      #
# --------------------------------------------------------------------------- #

_HEADING_RE = re.compile(r"^(#{1,6})\s")
_FENCE_RE = re.compile(r"^\s*```")

#: Only ``#``/``##`` open a new section. A ``###`` subsection belongs to its parent, which
#: is how a reader experiences it: a note at the top of "Consuming larkdocio" covers the
#: onboarding / refreshing / update-nag subsections beneath it.
_SECTION_LEVEL = 2


def section_of_line(text, lineno):
    """``(heading, first_lineno)`` of the section containing 1-based ``lineno``."""
    heading, start = "(preamble)", 1
    for index, line in enumerate(text.splitlines(), start=1):
        if index > lineno:
            break
        match = _HEADING_RE.match(line)
        if match and len(match.group(1)) <= _SECTION_LEVEL:
            heading, start = line.strip(), index
    return heading, start


_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_CODE_RE = re.compile(r"`([^`\n]+)`")
_PATHISH = re.compile(r"^[\w./-]+$")
_DOCUMENTY = (".md", ".sh", ".yml", ".yaml", ".json", ".toml", ".example", ".hook", ".py")


def _candidate_paths(line):
    """Path-looking citations in one line: markdown-link targets + inline code spans."""
    found = []
    for match in _LINK_RE.finditer(line):
        found.append(match.group(1).split("#", 1)[0])
    for match in _CODE_RE.finditer(line):
        token = match.group(1).strip()
        if _PATHISH.match(token) and ("/" in token or token.endswith(_DOCUMENTY)):
            found.append(token)
    return found


def cited_repo_paths(text):
    """``[(lineno, path)]`` for every citation that resolves to a file this repo carries.

    A citation of something the repo does *not* have (an external URL, a path in the
    *consumer's* tree such as ``scripts/update_larkdocio.sh``) is not a claim about this
    repo's contents and is left alone.
    """
    cited = []
    seen = set()
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for raw in _candidate_paths(line):
            if raw.startswith(("http://", "https://", "mailto:", "#", "/")):
                continue
            candidate = raw.rstrip("/")
            if not candidate or candidate in (".", "..") or candidate.startswith(".."):
                continue
            # `.git/…` — the READER'S OWN repository metadata. It is the one family the
            # existence test below cannot judge: every clone has a `.git/`, so a document
            # telling a consumer where THEIR git reads hooks from resolves here and reads as a
            # citation of a file this wheel fails to carry. It never can carry one — `.git` is
            # metadata, not a tracked file — so the dev-repo label the guard would demand could
            # only be a falsehood about the reader's own tree. Narrow on purpose: `.gitignore`
            # and `.github/…` are tracked and still seen.
            if candidate == ".git" or candidate.startswith(".git/"):
                continue
            target = REPO_ROOT / candidate
            # `./` — the CLI's default output directory, not a citation of anything.
            if not target.exists() or target.resolve() == REPO_ROOT:
                continue
            # A markdown link spells its target twice (`[`TOOLS.md`](TOOLS.md)`); one
            # citation, one report.
            key = (lineno, candidate)
            if key in seen:
                continue
            seen.add(key)
            cited.append((lineno, raw))
    return cited


def shipped_doc_texts():
    """``{repo-relative path: text}`` for every Markdown document the wheel carries.

    ``README.md`` is in it although ``package-data`` never names it: ``readme = "README.md"``
    makes the wheel carry it as its ``METADATA`` body, which is a stronger claim on a reader's
    attention than any packaged file has. Everything else is derived from ``package-data``, so
    packaging a doc enrols it here with nobody remembering to.
    """
    docs = {"README.md": readme_text()}
    for relative in sorted(packaged_doc_paths()):
        if relative.endswith(".md"):
            docs[relative] = (REPO_ROOT / relative).read_text(encoding="utf-8")
    return docs


def wheel_carries(doc_rel, cited, packaged):
    """Does ``cited``, as written inside ``doc_rel``, resolve to a file the wheel carries?

    Two spellings both count, and both are real:

    * the **repo-relative** path (``src/larkdocio/GUIDE.md``) — how the README names a
      packaged file, since the README is read from the repo root; and
    * the path **relative to the citing document**, which is how a doc names its neighbour.
      Inside the wheel the two release documents are siblings under ``larkdocio/``, so the
      changelog's ``RELEASE_NOTES.md`` link genuinely resolves for a wheel-only reader. This
      leg is what makes packaging a doc actually *excuse* its neighbours' citations rather
      than merely widen a set of strings.

    Resolution is by directory, never by basename — a citation only resolves from the
    directory it is written in.
    """
    if cited in packaged:
        return True
    sibling = posixpath.normpath(posixpath.join(posixpath.dirname(doc_rel), cited))
    return sibling in packaged


def unlabelled_shipped_citations(doc_rel, text, packaged=None):
    """``[(lineno, path, heading)]`` for each citation in ``doc_rel`` of a file the wheel does
    NOT carry that is not labelled :data:`DEV_REPO_LABEL` **at or before** it in its section.

    Section scope is the point: one note under a heading covers every path in that section
    (a per-link label on a fourteen-row table would be unreadable), while a citation added
    *above* the note is still caught.

    A citation of a path that exists **nowhere** is not reported. Deliberate: these documents
    legitimately cite paths in the *consumer's* tree, which resolve for the reader and not
    here, so an existence check would generate permanent false hits. The question answered is
    only *does the wheel carry what it sends you to?*
    """
    packaged = packaged_doc_paths() if packaged is None else packaged
    lines = text.splitlines()
    offenders = []
    for lineno, raw in cited_repo_paths(text):
        if wheel_carries(doc_rel, raw.rstrip("/"), packaged):
            continue
        heading, start = section_of_line(text, lineno)
        scope = prose("\n".join(lines[start - 1:lineno]))
        if labelled(scope):
            continue
        offenders.append((lineno, raw, heading))
    return offenders


def split_at_development_heading(text):
    """``(consumer_half, development_half)`` — ``text`` cut at :data:`DEVELOPMENT_HEADING`.

    The consumer half is a **prefix**, so every line number reported against it is a line
    number in the whole document and the section-scoped helpers above keep working unchanged.
    When the heading is absent the whole document is the consumer half and the development half
    is empty — which is the pre-fix state, and reddens every guard that reads either half
    rather than passing vacuously.
    """
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.strip() == DEVELOPMENT_HEADING:
            return "".join(lines[:index]), "".join(lines[index:])
    return text, ""


def unshipped_citations(text, doc_rel="README.md", packaged=None):
    """``[(lineno, path)]`` for every citation in ``text`` of a repo file the wheel lacks.

    **Label-blind, unlike :func:`unlabelled_shipped_citations`** — and that is the whole point
    of having both. Repo-wide, a labelled pointer into the dev tree is fine: a contributor
    reading the development half has the clone. In the half addressed to someone holding only
    the wheel, the right number of pointers into a tree they do not have is **zero**, labelled
    or not, because the label does not conjure the file.
    """
    packaged = packaged_doc_paths() if packaged is None else packaged
    return [
        (lineno, raw) for lineno, raw in cited_repo_paths(text)
        if not wheel_carries(doc_rel, raw.rstrip("/"), packaged)
    ]


def unlabelled_dev_repo_citations(text, packaged=None):
    """:func:`unlabelled_shipped_citations` for the README — the wheel's ``METADATA`` body.

    Kept as its own name because that is what the front-door truth guards call it; the README
    sits at the repo root, so its doc-relative and repo-relative resolutions coincide and this
    is exactly the general function.
    """
    return unlabelled_shipped_citations("README.md", text, packaged)


# --------------------------------------------------------------------------- #
# 1b. The same question asked of shipped SOURCE (LD-300)                        #
#                                                                              #
#     A docstring is shipped text too — ``help(larkdocio.base)`` and every IDE  #
#     hover render it — but the citation guard above reads packaged MARKDOWN,   #
#     so 28 ``BASE.md`` pointers in ``base/`` sat outside every guard.          #
# --------------------------------------------------------------------------- #

def shipped_python_sources():
    """``{repo-relative path: text}`` for every ``.py`` the wheel carries.

    Derived from the real tree via :func:`source_modules`, so a module added tomorrow is in
    scope on its own — the same property that makes the packaged-doc corpus self-widening.
    """
    return {
        f"src/{module}": (REPO_ROOT / "src" / module).read_text(encoding="utf-8")
        for module in source_modules()
    }


def wheel_carried_paths():
    """Repo-relative paths of **everything** the wheel carries: modules + package data.

    The packaged-doc set alone is the wrong pool for a *source* citation: the wheel carries
    every ``.py`` under the package, so a docstring naming ``schema_settle.py`` cites something
    a wheel-only reader really does have. That this derivation equals the built wheel's own
    ``RECORD`` is not assumed here — it is what ``tests/test_packaging.py`` proves, through
    :func:`wheel_expected_members` / :func:`missing_wheel_members` over a real build.
    """
    return {f"src/{module}" for module in source_modules()} | packaged_doc_paths()


def python_prose_blocks(text):
    """``[(first_line, last_line)]`` for every **prose block** in ``text``, in file order.

    A block is one docstring, or one contiguous run of comment lines. It is the analogue of the
    ``##`` section the packaged-doc guard scopes its label to, and the reason the scope is not
    simply "the module": a module that carries a :data:`DEV_REPO_LABEL` anywhere would then
    excuse every pointer added to it forever — a file-wide waiver wearing a label's clothes,
    and four modules on this tree already show that shape (a labelled capture in the module
    docstring, an unlabelled matrix pointer 300 lines down in an attribute doc).

    Executable string literals are deliberately not prose: a refusal message is emitted text
    with its own guard (``consumer_text``'s emitted-literal pass), and folding it in here would
    make one defect answer to two tables. Docstrings come from :mod:`ast`, so a plain string
    constant mid-function is never mistaken for one; comments come from :mod:`tokenize`,
    including the ``#:`` attribute docs this codebase keeps its per-constant prose in — where a
    third of the ``BASE.md`` pointers lived.
    """
    blocks = []
    try:
        tree = ast.parse(text)
    except SyntaxError:                                   # pragma: no cover - src is importable
        return blocks
    documented = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, documented):
            continue
        body = getattr(node, "body", None)
        if not body or not isinstance(body[0], ast.Expr):
            continue
        first = body[0].value
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            blocks.append((first.lineno, first.end_lineno))
    run = None
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type != tokenize.COMMENT:
            continue
        line = token.start[0]
        if run is not None and line == run[1] + 1:
            run = (run[0], line)
            continue
        if run is not None:
            blocks.append(run)
        run = (line, line)
    if run is not None:
        blocks.append(run)
    return sorted(blocks)


def python_prose_lines(text):
    """The 1-based line numbers of ``text`` that are prose — :func:`python_prose_blocks`, flat."""
    return {
        line for first, last in python_prose_blocks(text) for line in range(first, last + 1)
    }


#: A file citation written **bare**, the way source prose names a document: ``BASE.md register
#: row 13``, ``/SHEETS.md``, ``tests/captures/base-study/captures/p1-q4-02-copy.json``. The markdown
#: helpers only look inside links and code spans because a Markdown author writes citations that
#: way; a docstring frequently does not, and a guard that missed them would report 4 of this
#: issue's 28 pointers. The extension vocabulary is :data:`_DOCUMENTY`, shared with
#: :func:`_candidate_paths` so there is one answer to "what looks like a document".
_BARE_CITATION = re.compile(
    r"(?<![\w.-])(/?\.?(?:[\w.-]+/)*[\w-]+\.(?:"
    + "|".join(extension.lstrip(".") for extension in _DOCUMENTY)
    + r"))\b"
)


def _source_candidate_paths(line):
    """Path-looking citations in one line of source prose: links, code spans, bare names."""
    found = _candidate_paths(line)
    found.extend(match.group(1) for match in _BARE_CITATION.finditer(line))
    return found


def citation_resolves(doc_rel, cited, pool):
    """Does ``cited``, written inside ``doc_rel``, name a file in ``pool``?

    Three spellings resolve, and the third is the one Markdown does not need:

    * the **repo-relative** path, and a leading ``/`` read as the repo root — ``/BASE.md`` is
      how this codebase's prose spells a root document;
    * the path **relative to the citing module**, which is what a link target means; and
    * for a **bare basename** (no directory at all), any file of that name in the pool.
      Deliberate: ``BASE.md register row 13`` names a *document*, not a path — it makes no
      claim about which directory holds it, so it is answered honestly by whether the wheel
      carries such a document anywhere. A citation that spells a directory is held to it.
    """
    bare = cited.lstrip("/").rstrip("/")
    if not bare or bare in (".", ".."):
        return False
    if bare in pool:
        return True
    sibling = posixpath.normpath(posixpath.join(posixpath.dirname(doc_rel), cited.lstrip("/")))
    if sibling in pool:
        return True
    return "/" not in bare and bare in {posixpath.basename(path) for path in pool}


#: Trees that are not "what this repo carries": build output, the virtualenv, the kanban
#: worktree, caches. Asking **git** for the tracked set would be the shorter spelling and is
#: forbidden — ``tests/test_no_test_reads_live_git.py`` rules that no test may read live git or
#: working-tree state, because the answer changes with whoever's branch is out. A directory walk
#: answers the same question from the tree itself.
_UNCARRIED_TREES = (
    ".git", ".venv", ".kanban-wt", ".worktrees", "__pycache__", "build", "dist", "node_modules",
    ".pytest_cache", ".mypy_cache", "mutants", ".eggs",
)

#: ``python -m build``'s sdist step stages the WHOLE source tree in a transient
#: ``larkdocio-<version>/`` directory at ``REPO_ROOT`` before tarring it, then deletes it.
#: Serially nobody ever saw that window; under xdist ``-n auto`` the other workers are
#: walking the tree at exactly that moment, and the staged COPY joined their corpora —
#: doubling every count (LD-353: the permission-mention ratchet fired at ``117 <= 43``).
#: It is build output like ``build/`` and ``dist/`` and it is not tracked, so every
#: repo-walking corpus disowns it: ``.gitignore`` carries it for the walks derived from
#: ``.gitignore``, this predicate for the hand-kept ones.
SDIST_STAGING_RE = re.compile(r"larkdocio-\d[0-9A-Za-z._]*")


def is_build_staging(name):
    """Is ``name`` a transient ``python -m build`` sdist staging directory?"""
    return SDIST_STAGING_RE.fullmatch(name) is not None


def _uncarried(relative):
    """Is this repo-relative path outside what the repo carries — build output, a
    virtualenv, a cache, or the transient sdist staging tree?"""
    parts = pathlib.PurePosixPath(str(relative).replace(os.sep, "/")).parts
    return any(part in _UNCARRIED_TREES or part.endswith(".egg-info") or is_build_staging(part)
               for part in parts)


def _repo_paths():
    """Every file this repo carries, repo-relative. Cached: the tree is walked once."""
    if "repo_paths" not in _ARTIFACTS:
        found = set()
        for path in REPO_ROOT.rglob("*"):
            relative = path.relative_to(REPO_ROOT)
            if _uncarried(relative.as_posix()):
                continue
            if path.is_file():
                found.add(relative.as_posix())
        _ARTIFACTS["repo_paths"] = found
    return _ARTIFACTS["repo_paths"]


def source_citations(doc_rel, text, carried=None):
    """``[(lineno, path)]`` for each citation in ``doc_rel``'s prose that the WHEEL lacks.

    Scoped exactly like :func:`cited_repo_paths`: a citation of something this repo does not
    have either is not a claim about the wheel's contents (``.env`` is the *reader's* file, and
    a consumer-tree path resolves for them and not here), so only paths the repo really carries
    are reported. Label-blind — see :func:`unlabelled_source_citations`.
    """
    carried = wheel_carried_paths() if carried is None else carried
    prose_lines, repo = python_prose_lines(text), _repo_paths()
    cited, seen = [], set()
    for lineno, line in enumerate(text.splitlines(), start=1):
        if lineno not in prose_lines:
            continue
        for raw in _source_candidate_paths(line):
            if raw.startswith(("http://", "https://", "mailto:", "#")):
                continue
            key = (lineno, raw)
            if key in seen or citation_resolves(doc_rel, raw, carried):
                continue
            seen.add(key)
            if citation_resolves(doc_rel, raw, repo):
                cited.append((lineno, raw))
    return cited


def label_line(text, first, last):
    """The line in the prose block ``first..last`` from which :data:`DEV_REPO_LABEL` is in force,
    or ``None``.

    Read over the block's **flattened** prefix rather than line by line, because the label is a
    four-word phrase and a docstring wraps: ``"… live in the dev\\nrepo, not in the wheel"`` is
    a label, and a per-line search would call it nothing.
    """
    lines = text.splitlines()
    for lineno in range(first, last + 1):
        if labelled(prose("\n".join(lines[first - 1:lineno]))):
            return lineno
    return None


def unlabelled_source_citations(doc_rel, text, carried=None):
    """:func:`source_citations` minus the ones a :data:`DEV_REPO_LABEL` note already covers.

    **The scope is the prose BLOCK, and the label must be in force at the citation's line** —
    the same "one note covers what follows it" rule the packaged-doc guard applies per ``##``
    section, with :func:`python_prose_blocks` standing in for the section. Both halves are
    load-bearing: block scope stops one stray label from waiving a whole file, and the ordering
    keeps the note a promise about the text under it, so a pointer added *above* it still
    reports. A citation in a block with no label at all is never excused by a label elsewhere.
    """
    in_force = {}
    for first, last in python_prose_blocks(text):
        line = label_line(text, first, last)
        for lineno in range(first, last + 1):
            in_force[lineno] = line is not None and lineno >= line
    return [
        (lineno, raw) for lineno, raw in source_citations(doc_rel, text, carried)
        if not in_force.get(lineno)
    ]


# --------------------------------------------------------------------------- #
# 1c. The MIRROR question (LD-659 AC5): a label that calls a SHIPPED file        #
#     unshipped. The two directions are not symmetrical, and what each one       #
#     takes as the label's SUBJECT is why — see :func:`mislabelled_citations`.    #
# --------------------------------------------------------------------------- #

#: How far from the label a citation may sit and still be part of what the label is TALKING
#: ABOUT, in characters of flattened prose. **A clause, not a sentence** — about one wrapped
#: line of this codebase's prose. The width is load-bearing and both of the wider scopes were
#: tried first; :func:`label_subjects` records what each of them got wrong.
LABEL_CLAUSE_WINDOW = 80


def prose_body(doc_rel, text):
    """``text`` reduced to one line of the prose a reader actually reads.

    A ``.py`` file contributes its docstrings and comment runs (:func:`python_prose_lines`), so
    an executable string literal is out of scope; a Markdown file contributes everything outside
    a fenced block, because a fenced example that quotes the label is teaching material and not
    a claim. Emphasis markers and backticks go (``**in the dev repo**`` is the same claim), and
    whitespace collapses so a label wrapped across two lines is still one phrase.

    **Case and underscores are preserved**, unlike :func:`doc_prose.prose`: this text is searched
    for PATHS, and lower-casing turns ``GUIDE.md`` into a file nothing carries while stripping
    ``_`` turns ``BLOCK_TYPES.md`` into one.
    """
    if doc_rel.endswith(".py"):
        prose_lines = python_prose_lines(text)
        body = " ".join(line for number, line in enumerate(text.splitlines(), start=1)
                        if number in prose_lines)
    else:
        kept, in_fence = [], False
        for line in text.splitlines():
            if _FENCE_RE.match(line):
                in_fence = not in_fence
                continue
            if not in_fence:
                kept.append(line)
        body = " ".join(kept)
    return re.sub(r"\s+", " ", re.sub(r"[*`]+", "", body))


def label_subjects(doc_rel, text):
    """``[(label offset, (cited, …))]`` — for each :data:`DEV_REPO_LABEL` in ``doc_rel``, every
    citation inside :data:`LABEL_CLAUSE_WINDOW` of it, in either direction.

    **The clause is the subject, and the two wider scopes are both wrong** — recorded here
    because each was tried against the real corpus first:

    * **the whole file**, which is what reports the ~42 the issue estimated. This repo's own
      guards reject that scope in writing (:func:`python_prose_blocks`: *"a file-wide waiver
      wearing a label's clothes"*): under it every ``GUIDE.md`` mention anywhere in a module that
      labels something else is a mislabel.
    * **the sentence**, which sounds right and is not, because the sentences here are long and
      multi-clause: *"quoted verbatim by ``GUIDE.md`` and by ``SHEETS.md`` (in the dev repo, not
      in the wheel)"* is ONE sentence making one true claim about the second path.

    And the subject is a **set, not the nearest one**, which is the third thing tried: the label
    sits *between* the two paths in *"quoted verbatim by ``GUIDE.md`` and, in the dev repo rather
    than in the wheel, by ``SHEETS.md``"*, and nearest-by-distance picks the wrong one by a
    handful of characters. What the set makes expressible is the rule that actually holds — see
    :func:`mislabelled_citations`.
    """
    body = prose_body(doc_rel, text)
    citations = [(match.start(), match.group(1)) for match in _BARE_CITATION.finditer(body)]
    citations += [(match.start(1), match.group(1)) for match in _LINK_RE.finditer(body)]
    subjects = []
    labels = "|".join(re.escape(label) for label in REPO_LABELS)
    for match in re.finditer(labels, body, re.IGNORECASE):
        near = []
        for offset, cited in citations:
            if cited.startswith(("http://", "https://", "mailto:", "#")):
                continue
            distance = (match.start() - offset if offset <= match.start()
                        else offset - match.end())
            if distance <= LABEL_CLAUSE_WINDOW:
                near.append(cited)
        subjects.append((match.start(), tuple(dict.fromkeys(near))))
    return subjects


def mislabelled_citations(doc_rel, text, carried=None):
    """``[(label offset, subjects)]`` where ``doc_rel`` tells a reader a file is NOT in the wheel
    and **every file that label names is one the wheel carries**.

    The mirror of :func:`unlabelled_source_citations`, and deliberately **not** its mirror image
    in scope. That asymmetry is the design, so it is written here rather than rediscovered:

    * the UNLABELLED question is *"was the reader warned?"*, and a note warns about everything
      under it — so its scope is the whole ``##`` section (or prose block) and it prefers a false
      POSITIVE: a pointer added above the note still reports;
    * the MISLABEL question is *"does this text assert something FALSE?"*, so its scope is the
      clause (:func:`label_subjects`) and it prefers a false NEGATIVE — a false positive here
      demands an edit to prose that is already correct.

    **"Every", not "any", is the false-negative preference made precise.** A clause naming one
    shipped and one unshipped file has a true subject to be talking about, so this guard defers
    to it; only a clause where there is nothing left for the label to be true OF is reported. A
    label with no citation in its clause at all names nothing this can check and is not reported
    either — :func:`label_subjects` still returns it, so a corpus drifting into subject-less
    labels is visible rather than quiet.
    """
    carried = wheel_carried_paths() if carried is None else carried
    return [
        (offset, subjects) for offset, subjects in label_subjects(doc_rel, text)
        if subjects and all(citation_resolves(doc_rel, cited, carried) for cited in subjects)
    ]


#: The branch whose clone a consumer CAN run: the shallow, single-purpose distribution branch
#: that carries the current release's wheel and nothing else. It is the **argument** that is
#: exempt, not the characters — see :func:`dev_repo_clone_lines`.
ARTIFACT_CLONE_BRANCH = "dist"

#: The flags that spell that argument. ``git clone`` accepts ``-b`` as the short form, so a
#: guard that recognised only the long one would report the honest ``-b dist`` clone as a
#: dev-repo clone while claiming its subject is "the ``--branch`` argument".
_BRANCH_FLAGS = ("--branch", "-b")

#: A trailing shell comment: ``#`` at the start of the line or after whitespace. Anchored that
#: way on purpose — a bare ``#`` inside a token (a URL fragment, ``#L12``) is part of the
#: command, not a comment.
_TRAILING_COMMENT = re.compile(r"(?:^|\s)#")


def clones_the_artifact_branch(line):
    """Does ``line`` clone the ``dist`` artifact branch — as an **argument**, not as characters?

    Parsed rather than matched: the comment is cut off first, the remainder is split into
    tokens, and the token after ``--branch`` / ``-b`` (or the right-hand side of
    ``--branch=…``) must equal :data:`ARTIFACT_CLONE_BRANCH` exactly.

    That is three separate laundering shapes closed at once, all of which the substring test
    this replaces exempted: the characters sitting in a trailing ``#`` comment while the
    command clones the dev repo, a longer branch name that merely starts with them
    (``distribution``, ``distro``), and the flag naming some other option's value.
    """
    comment = _TRAILING_COMMENT.search(line)
    tokens = (line[: comment.start()] if comment else line).split()
    for index, token in enumerate(tokens):
        flag, _, inline_value = token.partition("=")
        if flag not in _BRANCH_FLAGS:
            continue
        value = inline_value if token != flag else (
            tokens[index + 1] if index + 1 < len(tokens) else ""
        )
        if value == ARTIFACT_CLONE_BRANCH:
            return True
    return False


def dev_repo_clone_lines(text):
    """``[(lineno, line)]`` for every ``git clone`` in ``text`` that is NOT the artifact clone.

    **The one definition of this predicate** (LD-205): the consumer-half guard and the
    consumer-*arm* guard both call it, so the two cannot be fixed apart.

    Two scopes, deliberately different:

    * a line is a **candidate** on the whole line, comment included — a commented-out dev-repo
      clone in the consumer half is still something the reader is being shown, and reporting it
      can only ever be stricter than the check this replaces;
    * the **exemption** is decided by :func:`clones_the_artifact_branch`, i.e. on the parsed
      ``--branch`` argument of the command itself.

    Line-scoped on purpose: the discriminator is what that very command clones, so a
    ``--branch dist`` elsewhere in the document cannot excuse a dev-repo clone here — and,
    since LD-205, neither can one elsewhere on the *same* line.
    """
    return [
        (lineno, line.strip())
        for lineno, line in enumerate(text.splitlines(), start=1)
        if "git clone" in line and not clones_the_artifact_branch(line)
    ]


# --------------------------------------------------------------------------- #
# 2. The individual claims                                                     #
# --------------------------------------------------------------------------- #

def documented_options(text, marker):
    """The option strings the bullet list introduced by ``marker`` documents.

    The list runs from ``marker`` to the first blank line, and each bullet's options are
    the backticked tokens starting with ``-`` before the em-dash description — so
    ``- `-o`, `--output` — output directory`` documents both spellings.
    """
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if marker in line), None)
    if start is None:
        return set()
    opts = set()
    for line in lines[start + 1:]:
        if not line.strip():
            break
        if not line.lstrip().startswith(("-", "*")):
            continue
        head = line.split("—", 1)[0]
        opts.update(
            token for token in _CODE_RE.findall(head) if token.startswith("-")
        )
    return opts


def two_way_diff(documented, real):
    """``(undocumented, phantom)`` — what the code has that the doc omits, and vice versa.

    Both halves matter: an omission hides a shipped thing (the two sheets flags, the eight
    modules), a phantom advertises something that does not exist. A one-way check would
    have caught neither of the defects this issue fixes.
    """
    return sorted(set(real) - set(documented)), sorted(set(documented) - set(real))


def documented_layout_paths(text):
    """The ``src/larkdocio/...`` paths the package-layout table's first column lists."""
    paths = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        first = stripped.strip("|").split("|", 1)[0].strip()
        for token in _CODE_RE.findall(first):
            if token.startswith("src/larkdocio/"):
                paths.add(token)
    return paths


def layout_table_rows(text):
    """``[lineno]`` for every table row whose FIRST COLUMN is a ``src/larkdocio/…`` path.

    The line-level twin of :func:`documented_layout_paths` — same rule, same first-column
    discipline — so a caller can ask *where* the layout claim lives rather than only *what* it
    says. That question became load-bearing the moment the table moved: a table's contents can
    be held bidirectionally while the table itself has drifted into the half of the document
    that a wheel-only reader is told to skip.
    """
    rows = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        first = stripped.strip("|").split("|", 1)[0].strip()
        if any(token.startswith("src/larkdocio/") for token in _CODE_RE.findall(first)):
            rows.append(lineno)
    return rows


def layout_table_section(text):
    """``(heading, first_lineno)`` of the ``##`` section the package-layout table sits in.

    ``(None, None)`` when no layout row can be found at all — which is a *failure*, not an
    absence, and the caller asserts it as one.
    """
    rows = layout_table_rows(text)
    if not rows:
        return None, None
    return section_of_line(text, rows[0])


#: A ```` ```python ```` fenced block. The condition this is here to foreclose is literal and
#: was measured: ``grep -c '```python' README.md`` returned **0** — a 322-line front door for a
#: Python library with not one line of Python in it.
_PY_FENCE = re.compile(r"^```python[ \t]*\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)


def python_fences(text):
    """The source of every ```` ```python ```` block in ``text``, in document order."""
    return [match.group(1) for match in _PY_FENCE.finditer(text)]


def fenced_line_numbers(text, statement):
    """``[lineno]`` for every line inside a python fence whose code is exactly ``statement``.

    "Exactly" means before any trailing ``#`` comment and ignoring indentation, so
    ``print(larkdocio.guide())   # the whole guide`` counts and
    ``the README mentions print(larkdocio.guide()) in prose`` does not. A prose mention is what
    the document already had; the complaint is that it never appeared as a line someone could
    run.
    """
    hits = []
    in_python = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            # A fence line either OPENS a python block (only ```python does) or CLOSES
            # whatever was open. Any other language's fence leaves us outside python.
            in_python = not in_python and stripped.rstrip() == "```python"
            continue
        if in_python and line.split("#", 1)[0].strip() == statement:
            hits.append(lineno)
    return hits


def surface_packages():
    """The ``larkdocio`` sub-packages the shipped surface registry names — derived twice over.

    ``capabilities()`` already spells the surface vocabulary in code (``docx-read``,
    ``docx-comments-read``, ``sheets-write``…), and ``src/larkdocio`` already spells which
    sub-packages exist. Intersecting the two is a fact about the code from **both** directions:
    a token that names no package (``docx``, ``embedded``) drops out, a package no surface
    claims (``common``, ``utils``, ``model``, ``blocks``) drops out, and a new surface family
    shipped in a new package widens the set with nobody editing a list here.

    Today it is exactly ``{read, write, sheets, comments}`` — the four the front door claims
    and the package docstring used to claim three of.
    """
    import larkdocio

    tokens = {
        part
        for surface_id in larkdocio.capabilities(full=True)["surfaces"]
        for part in surface_id.split("-")
    }
    packages = {
        name[len("src/larkdocio/"):-1] for name in real_top_level() if name.endswith("/")
    }
    return tokens & packages


#: A surface named the way a package docstring names one — ``` ``sheets/`` ```. The trailing
#: slash is what distinguishes "the shipped surface ``sheets/``" from a passing mention of the
#: word, so a docstring can discuss ``larkdocio.blocks`` without claiming it as a surface.
_DOC_SURFACE = re.compile(r"``(\w+)/``")


def docstring_surface_packages(doc):
    """The ``package/`` names ``doc`` presents as shipped surfaces."""
    return set(_DOC_SURFACE.findall(doc or ""))


#: The two living capability matrices. Both sit at the repo ROOT and the wheel carries
#: neither, so a shipped docstring that names one sends an installed reader to a path they do
#: not have. Their absence from ``package-data`` is asserted, not assumed, by the guard.
MATRIX_DOCS = ("BLOCKS.md", "SHEETS.md")


def unlabelled_matrix_citations(text):
    """The :data:`MATRIX_DOCS` ``text`` names with no :data:`DEV_REPO_LABEL` before the mention.

    Whole-text scope rather than section scope: this reads a *docstring*, which has no ``##``
    sections to scope a note to.
    """
    hits = []
    for name in MATRIX_DOCS:
        for match in re.finditer(re.escape(name), text or ""):
            if not labelled(prose((text or "")[:match.start()])):
                hits.append(name)
                break
    return hits


#: A sentence boundary: a terminator, any closing bracket/quote that trails it, then space.
#: The trailing class matters because these docs end sentences inside parentheses
#: ("…carries no status table.)").
_PARAGRAPH_SENTENCE = re.compile(r"(?<=[.!?])[)\]\"'’”]*\s+")
_WHITESPACE = re.compile(r"\s+")
_BLOCKQUOTE = re.compile(r"^\s*>+\s?", re.MULTILINE)


def _flatten(text):
    """Whitespace-collapsed, lower-cased text with blockquote markers dropped.

    Like :func:`doc_prose.prose` but it keeps ``_`` (the claim under test is about a
    filename containing one) and strips the ``>`` of a wrapped blockquote, which would
    otherwise hide every sentence boundary inside a callout.
    """
    return _WHITESPACE.sub(" ", _BLOCKQUOTE.sub("", text)).lower()


def _paragraphs(text):
    """``[(first_lineno, paragraph_text)]`` — blank-line-separated blocks."""
    blocks, buffer, start = [], [], 1
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.strip():
            if not buffer:
                start = lineno
            buffer.append(line)
        elif buffer:
            blocks.append((start, "\n".join(buffer)))
            buffer = []
    if buffer:
        blocks.append((start, "\n".join(buffer)))
    return blocks


def matrix_misattributions(text):
    """``[(lineno, sentence)]`` where a **single sentence** ties ``BLOCK_TYPES.md`` to a
    support matrix.

    ``BLOCK_TYPES.md`` opens by denying exactly this — "the authoring guide; it deliberately
    carries no per-type status matrix" — and points at ``/BLOCKS.md``, so such a sentence
    sends the reader to a document that refuses the question.

    The unit is the *sentence*, not the line: the claim is routinely split by hard wrapping
    ("…see\\n[`BLOCK_TYPES.md`](…) for\\nthe block-type → Markdown support matrix"), while a
    line window would also flag the legitimate neighbouring shape — "the matrix is
    ``BLOCKS.md``. Authoring mechanics live in ``BLOCK_TYPES.md``." — which is the correction
    itself. The filename is matched in full so the code symbol
    ``CREATABLE_BLOCK_TYPES`` cannot trip it.
    """
    hits = []
    for lineno, paragraph in _paragraphs(text):
        for sentence in _PARAGRAPH_SENTENCE.split(_flatten(paragraph)):
            if "block_types.md" in sentence and "matrix" in sentence:
                hits.append((lineno, sentence.strip()))
    return hits


# Two shapes, because the defect took the SECOND one everywhere the first was banned:
# an exact count ("13500 tests") and a rounded magnitude ("~13.5k cases"). LD-649 added
# the magnitude arm — the original pattern could not see "13.5k" at all (it has no run of
# three digits), which is how the same rottable claim survived at five sites while the
# README was guarded against it. Widened, never narrowed.
_COUNT_NEAR_TEST = re.compile(r"\b\d{3,}\b|~?\b\d+(?:\.\d+)?k\b", re.IGNORECASE)


def rottable_test_counts(text):
    """``[(lineno, number)]`` for every hard-coded test-count claim.

    A count in prose is stale the moment the next test lands, and guarding an exact number
    would redden the suite on every added test — which teaches people to edit the README to
    silence the suite. So the claim is *removed*, and this function is what keeps it gone.
    """
    hits = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if "test" not in line.lower():
            continue
        hits.extend((lineno, match.group(0)) for match in _COUNT_NEAR_TEST.finditer(line))
    return hits


# ---------------------------------------------------------------------------
# LD-649 — the whole-suite-size claim, banned beyond README.md
# ---------------------------------------------------------------------------
#
# ``rottable_test_counts`` above was scoped to README.md, on the reasoning that a count
# in prose is "stale the moment the next test lands". The reasoning was general; the
# enrolment was not. Measured 2026-09-07: the claim "the suite holds ~13.5k cases" stood
# at SEVEN live occurrences across FIVE files (process/doctrine/conformance-tier.md,
# requirements/CORPUS.md x3, tests/test_conformance_tier.py, .claude/roles/dev.md,
# scripts/verify.sh) against 20,248 collected — understated by 49%, and by 33% at the
# two "13.4k" sites. Nothing could see it, because no guard read those files.
#
# WHY THIS IS A SEPARATE, NARROWER DETECTOR rather than ``rottable_test_counts`` pointed
# at more files: those files legitimately carry OTHER four-digit numbers on lines that
# mention tests — the conformance tier's floors, byte sizes, timings — and several are
# DERIVED at run time by the very module that states them, which is the opposite of
# rottable. Applying the general detector there would have produced a guard people
# silence by editing prose. So the ban here is exactly the rotting shape: a magnitude
# asserted about the size of the SUITE / CORPUS / COLLECTION as a whole.
#
#: The files enrolled in the whole-suite-size ban. Every one of them held the claim.
SUITE_SIZE_FILES = (
    "process/doctrine/conformance-tier.md",
    "requirements/CORPUS.md",
    "tests/test_conformance_tier.py",
    ".claude/roles/dev.md",
    "scripts/verify.sh",
)

#: A rounded magnitude ("13.5k", "~13.4k", "20k"). This form ONLY ever means a rounded
#: whole-population size in this repository — nobody writes a pinned floor as "1.2k" —
#: which is what makes it safe to ban outright on a line that talks about tests.
_ROUNDED_MAGNITUDE = re.compile(r"~?\b\d+(?:\.\d+)?k\b", re.IGNORECASE)

#: The subject words that make a magnitude a claim about the population rather than
#: about one family, one file, or one measurement of bytes or seconds.
_SUITE_SUBJECT = re.compile(
    r"\b(suite|corpus|collection|cases|tests|assertions)\b", re.IGNORECASE)


def rottable_suite_size_claims(text):
    """``[(lineno, magnitude)]`` for every rounded whole-suite-size claim in ``text``.

    A line qualifies when it names the population (suite / corpus / collection / cases /
    tests / assertions) AND states a rounded magnitude. Both halves are required, so a
    byte size, a token budget or a timing quoted next to unrelated prose is not a hit.
    """
    lines = text.splitlines()
    hits = []
    for index, line in enumerate(lines):
        found = list(_ROUNDED_MAGNITUDE.finditer(line))
        if not found:
            continue
        # A THREE-LINE WINDOW, not one line: prose here is hard-wrapped at ~95 columns and
        # the real defect wrapped across the break ("does not need all 13.4k\n cases"), so a
        # single-line scan looked clean at the one site that mattered most. Same trap the
        # doc-drift guards solved with whitespace normalization.
        window = " ".join(lines[max(0, index - 1):index + 2])
        if not _SUITE_SUBJECT.search(window):
            continue
        hits.extend((index + 1, match.group(0)) for match in found)
    return hits


def loose_runtime_pins(data=None):
    """Runtime requirements that are NOT exact-pinned — the declared policy, checked.

    The README states that runtime dependencies are pinned exactly, deliberately, for the
    vendored-wheel distribution model. This reads the requirement list back, so loosening a
    pin without amending the declaration reddens.
    """
    data = pyproject() if data is None else data
    return [
        requirement
        for requirement in data["project"]["dependencies"]
        if "==" not in requirement
    ]


def first_screenful(text, lines=24):
    """The opening ``lines`` of ``text`` — what a reader sees before scrolling."""
    return "\n".join(text.splitlines()[:lines])


# --------------------------------------------------------------------------- #
# 2b. THE CLI FRONT DOOR (LD-208) — the group's own claims, as data            #
#                                                                              #
# The `--help` page was the last front-door surface whose claims nothing        #
# checked for COMPLETENESS: the dialect grep read every word of it and could    #
# not notice that it described one surface out of six. Everything below is      #
# derived from the shipped registry or from click itself, for the same reason   #
# the Summary guard is: a hand-pinned sentence is precisely what rotted.        #
# --------------------------------------------------------------------------- #

#: The line that opens the group help's SURFACE ROLL — the list held against
#: ``capabilities()["surfaces"]`` in both directions. A marker rather than a heuristic so the
#: guard reads one deliberate block instead of guessing which words are surface claims. In the
#: docstring the block is preceded by click's ``\b`` no-rewrap marker, which is what keeps an
#: id like ``docx-comments-read`` from being wrapped across two lines.
SURFACE_ROLL_MARKER = "Surfaces in this install:"

#: A surface id as the registry spells one: lowercase words joined by hyphens. The hyphen is
#: required, which is what keeps ordinary prose words out of the parse.
_SURFACE_ID = re.compile(r"\b[a-z][a-z0-9]*(?:-[a-z0-9]+)+\b")


def surface_ids():
    """Every surface id the installed registry reports — the derivation's left-hand side."""
    import larkdocio

    return set(larkdocio.capabilities(full=True)["surfaces"])


def group_help_page():
    """The rendered ``larkdocio --help`` page, straight out of the guarded corpus."""
    import consumer_text

    return consumer_text.cli_help_pages()["larkdocio --help"]


def help_surface_roll(page):
    """The surface ids the rendered help page CLAIMS, read out of the surface roll.

    Bounded to the marker's own block (marker → the next blank line) on purpose: the reverse
    leg has to be able to say *"the page names a surface that does not exist"*, and a scan of
    the whole page would read every hyphenated word of the prose as a claim.
    """
    start = page.find(SURFACE_ROLL_MARKER)
    if start == -1:
        return set()
    rest = page[start + len(SURFACE_ROLL_MARKER):]
    block = re.split(r"\n[ \t]*\n", rest, maxsplit=1)[0]
    return set(_SURFACE_ID.findall(block))


def surface_roll_diff(page, surfaces=None):
    """``(missing, phantom)`` — what the registry has that the page never names, and what the
    page names that the registry does not have.

    ``surfaces`` is injectable so both directions can be driven red against a registry that
    gained or lost a surface, without editing the real one.
    """
    real = surface_ids() if surfaces is None else set(surfaces)
    claimed = help_surface_roll(page)
    return sorted(real - claimed), sorted(claimed - real)


def _surface_modules(mode, caps=None):
    """Every module the registry says IMPLEMENTS the surfaces of one ``mode``, derived from it.

    Each surface's operations, legs and lifecycle rows carry a ``projected_from`` dotted path
    (``larkdocio.write.ops.OPS``, ``larkdocio.write.client.WriteClient``), so the union of their
    module prefixes *is* that half of the library's own address in the source tree.
    """
    import larkdocio

    caps = larkdocio.capabilities(full=True) if caps is None else caps
    modules = set()
    for surface in caps["surfaces"].values():
        if surface.get("mode") != mode:
            continue
        rows = []
        for key in ("operations", "legs", "lifecycle"):
            rows.extend(surface.get(key) or [])
        for row in rows:
            path = row.get("projected_from")
            if not path:
                continue
            # Drop the trailing attribute components (a class, a table), keep the module.
            parts = path.split(".")
            while len(parts) > 1 and module_source(".".join(parts)) is None:
                parts.pop()
            if module_source(".".join(parts)) is not None:
                modules.add(".".join(parts))
    return modules


def write_surface_modules(caps=None):
    """The write engine's modules — the falsifier for the group help's read-only claim."""
    return _surface_modules("write", caps)


def read_surface_modules(caps=None):
    """The read side's modules — needed to tell a write-ONLY package from a mixed one."""
    return _surface_modules("read", caps)


def forbidden_write_modules(caps=None):
    """What a READ-ONLY command line may not reach: the write engine's modules, plus the
    package of any of them that carries **no** read module at all.

    The second half closes the re-export hole: ``larkdocio.write`` is a write-only package, so
    importing the shelf rather than the module underneath it is the same act and is counted the
    same way. ``larkdocio.sheets`` is deliberately NOT counted — it is a mixed read+write
    package the reader legitimately imports — which is the guard's one stated blind spot: a
    hypothetical sheets-write command that touched **only** names re-exported by that shelf
    would pass. Both halves are derived from the registry, so neither is a maintained list.
    """
    write_modules = write_surface_modules(caps)
    read_packages = {name.rsplit(".", 1)[0] for name in read_surface_modules(caps)}
    packages = {name.rsplit(".", 1)[0] for name in write_modules} - read_packages
    return write_modules | {name for name in packages if module_source(name) is not None}


def module_source(name):
    """The source path of a ``larkdocio.*`` module, or ``None`` if there is no such module.

    Resolved by NAME → PATH rather than by importing, because the reachability walk has to be
    able to look at the write engine's address without importing the write engine. The name
    match is **case-sensitive against the directory listing** on purpose: this repo is
    developed on a case-insensitive filesystem, where ``larkdocio.read.Client`` — a CLASS
    imported ``from .client``, not a module — would otherwise resolve to ``client.py`` and be
    walked as if it were one.
    """
    if name != "larkdocio" and not name.startswith("larkdocio."):
        return None
    relative = name.split(".")[1:]
    base = SRC.joinpath(*relative) if relative else SRC
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if not candidate.is_file():
            continue
        parts = candidate.relative_to(SRC.parent).parts
        probe = SRC.parent
        for part in parts:
            if part not in {entry.name for entry in probe.iterdir()}:
                return None
            probe = probe / part
        return candidate
    return None


def _imported_larkdocio_modules(name):
    """The ``larkdocio.*`` modules ``name``'s source imports — absolute and relative."""
    import ast

    source = module_source(name)
    if source is None:
        return set()
    package = name if source.name == "__init__.py" else name.rsplit(".", 1)[0]
    found = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = ".".join(package.split(".")[: len(package.split(".")) - node.level + 1])
                if node.module:
                    base = f"{base}.{node.module}"
            else:
                base = node.module or ""
            if not base:
                continue
            found.add(base)
            found.update(f"{base}.{alias.name}" for alias in node.names)
    return {mod for mod in found if module_source(mod) is not None}


#: WHY A PACKAGE ``__init__`` IS RECORDED AS REACHED BUT NOT WALKED **THROUGH** (LD-632).
#:
#: **The skip is transformed here, not relaxed.** Its reason stands unchanged and is still
#: binding: an ``__init__`` is a **re-export shelf**, so following one would make every module
#: reachable from every other one and the check would mean nothing — the bare ``larkdocio``
#: shelf imports ``write.compose`` so that ``larkdocio.compose`` exists, and
#: ``larkdocio.sheets`` re-exports the write engine beside the reader. Walk through those and
#: ``download`` "reaches" the write engine and the read/write isolation guard collapses into a
#: tautology. That reason is about **interior** nodes, and for interior nodes nothing changes.
#:
#: What changed is only the conclusion for **the walk's own START**. The skip was applied to
#: the start as well, and one of the five reading handlers the isolation assertion names —
#: ``larkdocio.mermaid`` — **is a package**. So that walk visited exactly one node, followed
#: none of its five submodules and returned ``{}``: an arm asserting "reaches no write module"
#: that could not have seen one. A start is not a shelf being *traversed*, it is the subject
#: being *asked about* — asking what ``larkdocio.mermaid`` reaches and being handed nothing is
#: not an answer. So the start is exempt, and the guards carry a per-start precondition that a
#: vacuous walk is a failure rather than a pass
#: (``test_cli_front_door_truth.py::test_ld632_the_reach_walk_from_each_named_start_IS_NOT_VACUOUS``).
#:
#: This is the same shape as :data:`CLI_WRITE_GATEWAY_MODULE` below: preserve the reason,
#: replace only the conclusion (``process/doctrine/supersession.md`` § A.1).
_SHELF_SKIP_EXEMPTS_THE_START = True


def _walk_imports(starts):
    """The one import walk, yielding ``(module, parent)`` in breadth-first order.

    ``parent`` is ``None`` for a start. A package ``__init__`` is yielded (reached) but its own
    imports are not followed **unless it is one of** ``starts`` — see
    :data:`_SHELF_SKIP_EXEMPTS_THE_START` for the reason, which is preserved rather than
    weakened.

    One definition, three consumers (:func:`cli_reachable_modules`, :func:`reach_from`,
    :func:`write_reach_paths`), because a second copy of a walk is a second place for the
    shelf rule to be got wrong.
    """
    starts = list(dict.fromkeys(starts))
    start_set = set(starts)
    parent = {name: None for name in starts}
    seen, queue = set(), list(starts)
    while queue:
        name = queue.pop(0)
        if name in seen:
            continue
        seen.add(name)
        yield name, parent[name]
        source = module_source(name)
        if source is not None and source.name == "__init__.py" and name not in start_set:
            continue  # an INTERIOR shelf: reached, not walked through
        for imported in sorted(_imported_larkdocio_modules(name) - seen):
            parent.setdefault(imported, name)
            queue.append(imported)


def cli_reachable_modules():
    """Every ``larkdocio`` module a CLI command can reach, walked from the command callbacks.

    The walk starts at ``larkdocio.cli`` **and** at each command callback's own module, so a
    command implemented anywhere is followed. What a command *does* is what its own handler
    chain imports by module. The package-``__init__`` rule — reached, not walked through,
    except at a start — is :data:`_SHELF_SKIP_EXEMPTS_THE_START`.
    """
    from larkdocio.cli import cli

    starts = ["larkdocio.cli"]
    for command in cli.commands.values():
        callback = command.callback
        if callback is not None:
            starts.append(callback.__module__)
    return {name for name, _parent in _walk_imports(starts)}


def reach_from(start):
    """Every ``larkdocio`` module reachable from ``start``, including ``start`` itself.

    The precondition surface for the reach assertions: a walk that returns only ``{start}``
    makes every claim about what ``start`` reaches vacuous, and a guard that names a start can
    now say so out loud instead of passing (LD-632 AC4).
    """
    return {name for name, _parent in _walk_imports([start])}


#: THE ONE MODULE THE COMMAND LINE IS ALLOWED TO REACH THE WRITE ENGINE THROUGH (LD-492).
#:
#: **This constant is a supersession, not a relaxation.** Until LD-492 the check below was
#: ``cli_write_reach() == []`` — *no* command handler may reach the write engine — and the
#: **reason** for it stands unchanged and is the reason this is a single named module rather
#: than an allow-list: **a download must never be able to mutate the document it is reading.**
#: What changed is only the conclusion. The command line now ships exactly one writing verb
#: (``larkdocio roundtrip push --apply``), so "nothing reaches the write engine" became false,
#: and the guard that enforced it is **transformed rather than deleted**: every path from
#: ``larkdocio.cli`` into the write engine must pass through this module, which is the verb's
#: own. Give ``download``, ``folder``, ``config``, ``guide`` or ``mermaid`` a write import and
#: :func:`write_reach_paths` reports a path that does not go through it.
CLI_WRITE_GATEWAY_MODULE = "larkdocio.roundtrip"


def write_reach_paths(start="larkdocio.cli", write_modules=None):
    """``{write module: the import chain from ``start`` that reaches it}``.

    The same walk :func:`cli_reachable_modules` performs — :func:`_walk_imports`, one
    definition — with the parent remembered, because *which* write module is reached stopped
    being the interesting question the moment one command legitimately reaches them. The
    interesting question is **through what**, and only a path can answer it.
    """
    write_modules = forbidden_write_modules() if write_modules is None else set(write_modules)
    parents, hits = {}, {}
    for name, parent in _walk_imports([start]):
        parents[name] = parent
        if any(name == w or name.startswith(f"{w}.") for w in write_modules):
            chain, cursor = [], name
            while cursor is not None:
                chain.append(cursor)
                cursor = parents[cursor]
            hits[name] = tuple(reversed(chain))
    return hits


def write_reach_paths_bypassing(gateway=CLI_WRITE_GATEWAY_MODULE, **kwargs):
    """Every write-engine path from the command line that does **not** go through ``gateway``.

    This is the falsifier the read-only doctrine now has: empty means the only route from a
    console command into the write engine is the one writing verb's own module.
    """
    return {
        module: chain
        for module, chain in write_reach_paths(**kwargs).items()
        if gateway not in chain
    }


def cli_write_reach(reachable=None, write_modules=None):
    """The write-engine modules a CLI command can reach.

    Both sides are injectable so the guard can be driven red by pretending a command handler
    lives in the write engine, which is exactly what adding a *second* write subcommand — one
    that did not go through the verb — would do. Since LD-492 this is **not** expected to be
    empty (see :data:`CLI_WRITE_GATEWAY_MODULE`); what must be empty is
    :func:`write_reach_paths_bypassing`.
    """
    reachable = cli_reachable_modules() if reachable is None else set(reachable)
    write_modules = forbidden_write_modules() if write_modules is None else set(write_modules)
    hits = set()
    for module in reachable:
        for write_module in write_modules:
            if module == write_module or module.startswith(f"{write_module}."):
                hits.add(module)
    return sorted(hits)


#: A subcommand shown being INVOKED — ``larkdocio download …``. The option group in the middle
#: is how the documented calling convention is honored structurally rather than by a list of
#: global flags: anything option-shaped (and its value) may sit between the program name and
#: the subcommand.
_SUBCOMMAND_INVOCATION = re.compile(
    r"^larkdocio((?:\s+-{1,2}[\w-]+(?:[= ]\S+)?)*)\s+([a-z][\w-]*)")


def command_lines(text):
    """Every line inside a fenced ``bash`` block that starts with the ``larkdocio`` program.

    The scan is bounded to fenced shell blocks because the README's PROSE says "larkdocio
    itself", "larkdocio repo", "the installed larkdocio version" — English, not invocations.
    A parser that read those as subcommand names would report five phantoms on a correct
    README and get deleted, which is the failure mode a guard has to avoid to stay believed.
    """
    lines, inside = [], False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            inside = stripped[3:].strip().lower() in {"bash", "sh", "shell"} if not inside else False
            continue
        if inside and stripped.startswith("larkdocio"):
            lines.append(stripped)
    return lines


def invoked_subcommands(text):
    """Every subcommand name the text shows being invoked as ``larkdocio [globals] <name>``."""
    found = set()
    for line in command_lines(text):
        match = _SUBCOMMAND_INVOCATION.match(line)
        if match:
            found.add(match.group(2))
    return found


def undocumented_subcommands(text=None):
    """Every real subcommand the README never shows being invoked.

    Derived from ``cli.commands`` for the same reason the ``--help`` enrolment is: a
    subcommand added tomorrow owes the front door a mention on its own.
    """
    from larkdocio.cli import cli

    text = readme_text() if text is None else text
    shown = invoked_subcommands(text)
    return sorted(name for name in cli.commands if name not in shown)


def phantom_subcommands(text=None):
    """Every subcommand the README shows being invoked that click does not define."""
    from larkdocio.cli import cli

    text = readme_text() if text is None else text
    return sorted(invoked_subcommands(text) - set(cli.commands))


# --------------------------------------------------------------------------- #
# 3. The built artifact                                                        #
# --------------------------------------------------------------------------- #

def built_wheel():
    """The wheel in ``dist/`` matching the declared version, or ``None``."""
    version = pyproject()["project"]["version"]
    wheel = REPO_ROOT / "dist" / f"larkdocio-{version}-py3-none-any.whl"
    return wheel if wheel.exists() else None


def wheel_metadata(wheel):
    """The wheel's ``dist-info/METADATA`` text — headers *and* the README body."""
    with zipfile.ZipFile(wheel) as archive:
        name = next(
            member for member in archive.namelist()
            if member.endswith(".dist-info/METADATA")
        )
        return archive.read(name).decode("utf-8")


def metadata_headers(text):
    """``{header: [values]}`` for the ``METADATA`` preamble (before the body)."""
    headers = {}
    for line in text.splitlines():
        if not line.strip():
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers.setdefault(key.strip(), []).append(value.strip())
    return headers


# --------------------------------------------------------------------------- #
# 4. Artifact CONTENTS — what the wheel and the sdist actually carry (LD-215)  #
# --------------------------------------------------------------------------- #
#
# Why here and not in a test file: there are already THREE independent
# ``python -m build`` sites under ``tests/`` (test_shipped_notes.py,
# test_guide.py, test_comment_anchor_claim_guard.py) beside this module's
# pre-built ``dist/`` reader. The content guard must not become a fourth, so the
# build lives ONCE in ``packaging_artifacts()`` below and the guard imports it.

#: Development-only trees that must never reach a source distribution of this
#: library. Named so a failure message says WHICH tree leaked. ``tests/`` is the
#: one that actually did (LD-215: 222 files, 3,917,577 B, 64% of the tarball,
#: dragged in by setuptools' legacy default glob ``tests/test*.py`` because the
#: repo had no ``MANIFEST.in``); ``dev/`` and ``progress/`` are guarded
#: prospectively — they do not leak today.
SDIST_FORBIDDEN_TREES = ("tests", "dev", "progress")

#: Packaging standards a source distribution owes its consumer, at its top
#: level. ``setup.cfg`` is on the list deliberately: no ``setup.cfg`` exists in
#: this repo — the build backend synthesizes it, carrying only ``[egg_info]`` /
#: ``tag_build`` / ``tag_date``, which is harmless and justified (the 07-31 audit's
#: finding 4).
SDIST_REQUIRED_ROOT_FILES = ("PKG-INFO", "README.md", "pyproject.toml", "setup.cfg", "LICENSE")

#: Top-level sdist files that MAY be present without being owed. ``MANIFEST.in``
#: is shipped by setuptools itself whenever it exists.
#: ``LICENSE`` was listed here, with the reason that it "appears only if the project ever
#: declares a license *file* (today it declares license text)". That reason still holds; its
#: condition came true in LD-683 (Apache-2.0, ``license-files = ["LICENSE"]``, D-120), so the
#: conclusion moved: ``LICENSE`` is now OWED, in ``SDIST_REQUIRED_ROOT_FILES`` above.
SDIST_OPTIONAL_ROOT_FILES = ("MANIFEST.in",)

MANIFEST_IN = REPO_ROOT / "MANIFEST.in"

#: Directives that would make ``MANIFEST.in`` ADD files to the sdist. LD-215's
#: manifest is prune-only on purpose: the same mechanism could start shipping the
#: root ``CHANGELOG.md`` / ``RELEASE_NOTES.md`` at sdist top level, and that is a
#: separate maintainer decision about the root-canonical + src-copy arrangement, not a
#: side effect of a prune.
MANIFEST_INCLUSION_DIRECTIVES = ("include", "recursive-include", "global-include", "graft")

_ARTIFACTS = {}


def manifest_directives():
    """``[(command, argument)]`` for each real directive line of ``MANIFEST.in``."""
    directives = []
    for line in MANIFEST_IN.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        command, _, argument = line.partition(" ")
        directives.append((command.strip().lower(), argument.strip()))
    return directives


def built_sdist():
    """The sdist in ``dist/`` matching the declared version, or ``None``.

    The pre-built reader sibling of :func:`built_wheel` — same posture, same
    ``None`` on a plain checkout. **Not** what the content guard runs against:
    see :func:`packaging_artifacts` for why.
    """
    version = pyproject()["project"]["version"]
    sdist = REPO_ROOT / "dist" / f"larkdocio-{version}.tar.gz"
    return sdist if sdist.exists() else None


def run_build(*, cwd, outdir, wheel_only=False):
    """Shell out to ``python -m build`` — **the one place in ``tests/`` that does**.

    Returns the ``CompletedProcess`` rather than raising, because the two callers want
    different postures out of the same invocation: :func:`packaging_artifacts` treats a
    failed build as an AssertionError (LD-215's arming posture — a content guard that can
    skip is absent from the dev loop), while ``test_shipped_notes``' pristine-tree build
    keeps its ``pytest.skip``, since a tree it assembled itself failing to build is a
    statement about the environment, not about the packaging declaration.

    ``cwd`` is a parameter for the same reason: the pristine build is deliberately NOT run
    in ``REPO_ROOT`` (``build/lib/`` staging and a cached ``egg-info/SOURCES.txt`` can both
    put a document in the wheel that ``package-data`` no longer names), so it cannot share
    this module's cached artifacts — only its invocation. LD-221 kept that carve-out and
    unified the call.
    """
    argv = [sys.executable, "-m", "build"]
    if wheel_only:
        argv.append("--wheel")
    argv += ["--outdir", str(outdir)]
    return subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True)


def session_artifact_dir():
    """The dir every worker of ONE xdist run shares for the built artifacts, or
    ``None`` when not running under xdist.

    LD-353 (the isolation defect `-n auto` exposed). :func:`packaging_artifacts`
    cached its build **per process**, which is one build per xdist worker — up to
    16 concurrent ``python -m build`` invocations over the SAME in-tree setuptools
    scratch (``build/`` staging and ``src/larkdocio.egg-info/SOURCES.txt``). They
    stomped on each other's sdist staging, and a run failed with
    ``[Errno 2] No such file or directory: 'larkdocio-1.29.0/src/…/revision.py'``.
    The shared resource is the working tree's build scratch, so the fix is one
    build **per run** rather than per process — keyed by xdist's own run id, which
    every worker of a run agrees on and no two runs share.
    """
    runid = os.environ.get("PYTEST_XDIST_TESTRUNUID")
    if not runid:
        return None
    return pathlib.Path(tempfile.gettempdir()) / f"larkdocio-artifacts-{runid}"


def argv_literal_sites(*tokens):
    """``["tests/<file>.py:<lineno>", ...]`` for every real argv literal in ``tests/`` whose
    string constants include all of ``tokens`` — e.g. ``("-m", "build")``.

    LD-355 folded two byte-identical walkers into this one (``test_packaging``'s
    ``python -m build`` site count and ``test_parallel_offline_suite``'s ``python -m venv``
    one). Each caller keeps its own assertion and its own message; only the walk is shared.

    **AST-based, not grep-based, and deliberately so:**
    ``tests/test_no_test_reads_live_git.py`` carries the exact argv
    ``[sys.executable, "-m", "build"]`` inside a triple-quoted **fixture source string** (its
    "does not bite a non-git subprocess" case). A grep bites that; a walk over real
    list/tuple literals cannot, because a string is not a list. The unit is the **argv
    literal** rather than the ``subprocess`` call, so building the argv one line above the
    call — which :func:`run_build` does, to append ``--wheel`` conditionally — neither hides
    a site nor needs the walk to do dataflow.

    **A file that vanishes mid-walk is skipped, not an error.** LD-353's lesson in its second
    form: under ``-n auto`` this walk runs while other workers are executing, and
    ``test_parallel_offline_suite._run_probe`` deliberately writes a transient
    ``probe_*.py`` into ``tests/`` and deletes it a moment later. A file that is gone by the
    time it is read cannot be a call site, so it is disowned exactly like the sdist staging
    dir was — the alternative is a guard that fails for a reason unrelated to what it guards.
    """
    sites = []
    for path in sorted((REPO_ROOT / "tests").rglob("*.py")):
        try:
            source = path.read_text(encoding="utf-8")
        except FileNotFoundError:  # a transient probe module, deleted mid-walk
            continue
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.List, ast.Tuple)):
                continue
            literals = [
                element.value for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            ]
            if all(token in literals for token in tokens):
                sites.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{node.lineno}")
    return sites


_SHARED = {}


def run_shared_artifact(name, produce):
    """Produce an expensive test artifact **once per test RUN** and hand it to everyone.

    LD-355. LD-353 gave :func:`packaging_artifacts` this shape for one artifact; this is
    the same shape, generalised, because it was not the only expensive setup being re-done
    per process. The default ``--dist load`` scatters a module's tests across workers, so a
    ``scope="module"`` fixture is one setup **per worker that receives one of its tests** —
    six clean-venv constructions were observed in a single ``-n auto`` run.

    ``produce(outdir) -> pathlib.Path`` is called at most once per run: the first caller in
    the run holds an exclusive lock, produces into ``outdir``, and records the resulting path
    in a stamp file every other worker then reads. ``produce`` may raise (or
    ``pytest.skip``) — the lock is released either way and each process re-decides
    independently, so an environment skip stays a skip everywhere.

    Outside xdist there is one process, so the module-level cache already IS run-shared and
    a private temp dir is used. Either way the directory outlives the run in the system temp
    dir, exactly as :func:`packaging_artifacts`' does; the OS reclaims it.

    **Immutable by contract.** Callers READ the artifact; nothing writes into ``outdir``
    after ``produce`` returns. A mutable shared artifact would be an isolation hazard of
    precisely the kind LD-353 made observable.
    """
    if name in _SHARED:
        return _SHARED[name]
    shared = session_artifact_dir()
    if shared is None:
        outdir = pathlib.Path(tempfile.mkdtemp(prefix=f"larkdocio-{name}-"))
        _SHARED[name] = produce(outdir)
        return _SHARED[name]
    shared.mkdir(parents=True, exist_ok=True)
    stamp = shared / f"{name}.path"
    lock = shared.parent / f"{shared.name}.{name}.lock"
    with shared_artifact_lock(lock):
        if not stamp.exists():
            outdir = shared / name
            outdir.mkdir(parents=True, exist_ok=True)
            produced = produce(outdir)
            stamp.write_text(str(produced), encoding="utf-8")
        _SHARED[name] = pathlib.Path(stamp.read_text(encoding="utf-8"))
    return _SHARED[name]


def pristine_wheel():
    """The wheel built from a **pristine copy** of the packaging inputs — one per RUN.

    The producer lives in ``test_shipped_notes`` (with the assertions that make the copy
    pristine); this is only the run-sharing seam, so five modules stop paying for five
    builds of the same artifact. Deliberately **not** :func:`packaging_artifacts`' wheel —
    that one is built in ``REPO_ROOT`` where local residue can package a document the
    declaration no longer names, which is the very immunity the pristine build exists for
    (LD-221 AC-A3 forbids collapsing them, and a guard in
    ``test_parallel_offline_suite`` pins it).
    """
    from test_shipped_notes import build_pristine_wheel

    return run_shared_artifact("pristine-wheel", build_pristine_wheel)


def _install_pristine_wheel_into(outdir):
    """``python -m venv`` + an OFFLINE ``pip install`` of the pristine wheel.

    **The one place in ``tests/`` that shells out to ``python -m venv``** — the same rule,
    and the same reason, as :func:`run_build` for ``python -m build`` (a guard in
    ``test_parallel_offline_suite`` pins the count at one).

    The path is ``<outdir>/venv/v`` on purpose: the three consumers each assert that the
    probe's ``larkdocio.__file__`` sits inside the installed copy rather than the repo, one
    spelling that ``/venv/`` and two spelling it ``/v/``, so the shared venv keeps **both**
    components and neither assertion is weakened (the dev checkout's env dir is ``/.venv/``,
    which contains neither).
    """
    import pytest  # local: front_door is also imported by a bare `python -c` probe

    venv_dir = outdir / "venv" / "v"
    made = subprocess.run([sys.executable, "-m", "venv", str(venv_dir)],
                          capture_output=True, text=True)
    if made.returncode != 0:  # pragma: no cover — environment guard
        pytest.skip(f"a virtualenv could not be created here:\n{made.stderr[-500:]}")
    bin_dir = venv_dir / ("Scripts" if sys.platform == "win32" else "bin")
    python = bin_dir / "python"
    if not python.exists():  # pragma: no cover — environment guard
        pytest.skip("the created virtualenv has no interpreter")
    installed = subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", "--no-index",
         "--disable-pip-version-check", "-q", str(pristine_wheel())],
        capture_output=True, text=True,
    )
    if installed.returncode != 0:  # pragma: no cover — environment guard
        pytest.skip(f"the wheel could not be installed offline:\n{installed.stderr[-500:]}")
    return venv_dir


def clean_wheel_venv():
    """A throwaway venv with the pristine wheel installed **offline** — one per RUN.

    LD-355. Three modules built this, byte-identically, at ~5 s each; because the default
    ``--dist load`` scatters a module's tests across workers, SIX constructions were
    observed in one ``-n auto`` run. It is read-only after creation (every consumer runs a
    subprocess out of it with its own ``cwd``), so it is safe to share — see
    :func:`run_shared_artifact` on the immutability contract.

    Returns ``{"python", "console", "env"}``. ``--no-deps --no-index`` means nothing is
    fetched; the runtime dependencies are supplied by pointing ``PYTHONPATH`` at this
    interpreter's own site-packages, which is not a *site* directory for the child, so the
    editable ``src/`` ``.pth`` never enters its ``sys.path``. The per-call existence checks
    below are cheap and are what keep each consumer's SKIP a skip rather than an error.
    """
    import pytest  # local: front_door is also imported by a bare `python -c` probe

    venv_dir = run_shared_artifact("clean-venv", _install_pristine_wheel_into)
    bin_dir = venv_dir / ("Scripts" if sys.platform == "win32" else "bin")
    python = bin_dir / "python"
    console = bin_dir / ("larkdocio.exe" if sys.platform == "win32" else "larkdocio")
    if not python.exists():  # pragma: no cover — environment guard
        pytest.skip("the created virtualenv has no interpreter")
    if not console.exists():  # pragma: no cover — environment guard
        pytest.skip("the installed wheel provided no `larkdocio` console script")
    site = pathlib.Path(sysconfig.get_paths()["purelib"])
    return {"python": python, "console": console,
            "env": {"PYTHONPATH": str(site), "PYTHONDONTWRITEBYTECODE": "1",
                    "PATH": "/usr/bin:/bin"}}


def _artifact_pair(outdir):
    version = pyproject()["project"]["version"]
    return (outdir / f"larkdocio-{version}.tar.gz",
            outdir / f"larkdocio-{version}-py3-none-any.whl")


def _build_into(outdir):
    proc = run_build(cwd=REPO_ROOT, outdir=outdir)
    if proc.returncode != 0:
        raise AssertionError(
            "python -m build failed while arming the packaging content guard:\n"
            + (proc.stdout or "") + (proc.stderr or "")
        )
    for path in _artifact_pair(outdir):
        if not path.exists():
            raise AssertionError(
                f"python -m build produced no {path.name}; built: "
                f"{sorted(p.name for p in outdir.iterdir())}"
            )


def packaging_artifacts():
    """``(sdist, wheel)`` built from the CURRENT working tree — never skippable.

    The arming posture, stated (LD-215 AC6a). ``built_wheel()`` /
    :func:`built_sdist` read a pre-built ``dist/`` and return ``None`` on a plain
    checkout, so every existing consumer of them calls ``pytest.skip``. A content
    guard modelled that way would be **absent from the normal dev loop**, and
    ``verify.sh`` does not rescue it: its gate order is ``pytest`` THEN
    ``python -m build`` (see ``scripts/verify.sh``), so the artifacts the suite
    would need do not exist yet when the suite runs. Worse, ``dist/`` is
    gitignored and sticky — a stale tarball from a previous build would let the
    guard pass on contents the working tree no longer produces.

    So the guard BUILDS: one ``python -m build`` per test RUN — cached in this
    module, and (under xdist) shared across every worker of the run via
    :func:`session_artifact_dir` behind an exclusive file lock, because the build
    scratch it uses lives in the working tree and cannot take two builds at once
    (LD-353). That is the same cost ``verify.sh``'s own build gate already pays,
    and it is what makes a packaging-content assertion true of the tree in front
    of you.
    """
    if "pair" not in _ARTIFACTS:
        shared = session_artifact_dir()
        if shared is None:
            outdir = pathlib.Path(tempfile.mkdtemp(prefix="larkdocio-artifacts-"))
            _build_into(outdir)
            _ARTIFACTS["pair"] = _artifact_pair(outdir)
        else:
            shared.mkdir(parents=True, exist_ok=True)
            lock = shared.parent / f"{shared.name}.lock"
            with shared_artifact_lock(lock):
                if not all(p.exists() for p in _artifact_pair(shared)):
                    _build_into(shared)
            _ARTIFACTS["pair"] = _artifact_pair(shared)
    return _ARTIFACTS["pair"]


def sdist_members(sdist):
    """``{path: size}`` for every FILE in the sdist, relative to its top dir."""
    with tarfile.open(sdist) as archive:
        return {
            member.name.split("/", 1)[1]: member.size
            for member in archive.getmembers()
            if member.isfile() and "/" in member.name
        }


def sdist_directories(sdist):
    """Every DIRECTORY entry in the sdist, relative to its top dir.

    Separate from :func:`sdist_members` because ``prune`` and
    ``recursive-exclude`` differ exactly here: the latter drops a tree's files and
    leaves its directory entry behind.
    """
    with tarfile.open(sdist) as archive:
        return {
            member.name.split("/", 1)[1]: None
            for member in archive.getmembers()
            if member.isdir() and "/" in member.name
        }.keys()


def wheel_members(wheel):
    """``{path: (size, crc)}`` for every member of the wheel.

    Size + CRC rather than a whole-file hash: a zip's own metadata (timestamps,
    build ordering) differs between two builds of identical content, so
    byte-identity of the archive is the wrong question — identity of the members
    is the right one.
    """
    with zipfile.ZipFile(wheel) as archive:
        return {i.filename: (i.file_size, i.CRC) for i in archive.infolist()}


def source_modules():
    """Every ``.py`` under ``src/larkdocio``, as the WHEEL would name it.

    Derived from the real tree, so a module added tomorrow is expected on its own.
    """
    return {
        path.relative_to(SRC.parent).as_posix()
        for path in SRC.rglob("*.py")
        if "__pycache__" not in path.parts
    }


def package_data_table(table=None):
    """The raw ``[tool.setuptools.package-data]`` table, or an injected stand-in.

    Injectable so every derivation below can be exercised over a *declaration* the
    working tree does not contain — which is the whole point: see
    :func:`declared_package_data`.
    """
    if table is not None:
        return table
    return pyproject().get("tool", {}).get("setuptools", {}).get("package-data", {})


#: A glob metacharacter. A pattern carrying one has no NAME until the filesystem is
#: consulted, so it cannot contribute to an owed set that must survive the
#: filesystem — see :func:`declared_package_data_wildcards`.
_WILDCARD_RE = re.compile(r"[*?\[]")


def _package_dir(package):
    """``"larkdocio.write"`` → ``"larkdocio/write"``, as the wheel names it."""
    return "/".join(package.split("."))


def declared_package_data(table=None):
    """Every DECLARED package-data name, as the WHEEL would name it. No filesystem.

    DERIVED from ``[tool.setuptools.package-data]`` rather than typed a second time
    — a seventh declared file must make the guard FOLLOW the declaration instead of
    crying wolf.

    **Read literally from the declaration, NOT globbed off disk (LD-215 AC4, second
    round).** The first cut expanded the patterns with ``Path.glob`` — so the owed
    set was computed from the same working tree the artifact is built from, and a
    declared file that vanished left the *expectation* at the same instant it left
    the *artifact*: ``rm src/larkdocio/GUIDE.md``, rebuild, guard still green, a
    222 KB shipped doc gone. The owed half of a guard that can only ever be observed
    green is not a guard. So the names come from the declaration and the disk is what
    gets CHECKED against them (:func:`unresolved_package_data_literals`).

    Wildcard patterns are excluded here on purpose and reported separately.
    """
    names = set()
    for package, patterns in package_data_table(table).items():
        for pattern in patterns:
            if _WILDCARD_RE.search(pattern):
                continue
            names.add(posixpath.join(_package_dir(package), pattern))
    return names


def declared_package_data_wildcards(table=None):
    """``[(package, pattern)]`` for every declared pattern that is a glob.

    Empty today — all six declarations are literal filenames, which is what lets
    :func:`declared_package_data` be name-derived. A wildcard's expansion can only
    come off the filesystem, so it contributes nothing to the missing-direction; the
    guard reports it rather than silently absorbing it, so whoever declares the first
    one decides explicitly (spell it as literals, or record why that entry's owed half
    is disk-derived).
    """
    return sorted(
        (package, pattern)
        for package, patterns in package_data_table(table).items()
        for pattern in patterns
        if _WILDCARD_RE.search(pattern)
    )


def globbed_package_data(table=None):
    """Wildcard declarations expanded off disk, as the wheel would name them.

    Used only by the FORBID direction — a file the build legitimately ships under a
    declared wildcard must not read as an unexpected member. Deliberately *not* part
    of the owed set (see :func:`declared_package_data`).
    """
    names = set()
    for package, pattern in declared_package_data_wildcards(table):
        package_dir = pathlib.Path("src", *package.split("."))
        for match in (REPO_ROOT / package_dir).glob(pattern):
            if match.is_file():
                names.add(posixpath.join(_package_dir(package), match.name))
    return names


def allowed_package_data(table=None):
    """Every package-data file the artifacts MAY carry: declared literals + globs."""
    return declared_package_data(table) | globbed_package_data(table)


def unresolved_package_data_literals(table=None, root=None):
    """Declared literal names with no file on disk — declaration and tree disagree.

    The real-artifact bite the globbing shape could not have: a declared doc deleted
    from ``src/`` reddens *here* (and in :func:`missing_wheel_members`, whose owed set
    no longer shrinks with the tree).
    """
    src = SRC.parent if root is None else pathlib.Path(root)
    return sorted(
        name for name in declared_package_data(table)
        if not (src / name).is_file()
    )


def dist_info_prefix():
    """The wheel's ``*.dist-info/`` directory name, from the declared version."""
    return f"larkdocio-{pyproject()['project']['version']}.dist-info/"


#: The egg-info members a source distribution owes (the backend writes more; these
#: three are the accounting a reader looks for). Any other egg-info member is allowed.
EGG_INFO_REQUIRED = ("PKG-INFO", "SOURCES.txt", "top_level.txt")
EGG_INFO_PREFIX = "src/larkdocio.egg-info/"


def sdist_expected_files(table=None, modules=None):
    """Every path a source distribution of this library OWES, derived.

    The ``src/`` tree (real modules + the DECLARED package-data names), the packaging
    standards, and the egg-info accounting. Nothing else — a development tree is not
    part of a source *distribution* of this library. The package-data half is
    declaration-derived, so this half of the guard has the same real bite the wheel's
    does (LD-215 AC4, second round).
    """
    modules = source_modules() if modules is None else modules
    expected = set(SDIST_REQUIRED_ROOT_FILES)
    expected |= {f"src/{path}" for path in modules | declared_package_data(table)}
    expected |= {EGG_INFO_PREFIX + name for name in EGG_INFO_REQUIRED}
    return expected


def unexpected_sdist_members(paths):
    """Every sdist path outside the allow-list. Pure — runs over synthetic input."""
    allowed_src = {f"src/{path}" for path in source_modules() | allowed_package_data()}
    unexpected = []
    for path in paths:
        if path in SDIST_REQUIRED_ROOT_FILES or path in SDIST_OPTIONAL_ROOT_FILES:
            continue
        if path.startswith(EGG_INFO_PREFIX) or path in allowed_src:
            continue
        unexpected.append(path)
    return sorted(unexpected)


def missing_sdist_members(paths, expected=None):
    """Every owed sdist path that is absent. The half a forbid-only guard misses."""
    expected = sdist_expected_files() if expected is None else expected
    return sorted(expected - set(paths))


def leaked_trees(paths):
    """Which development trees (by NAME) appear among ``paths``."""
    leaked = set()
    for tree in SDIST_FORBIDDEN_TREES:
        for path in paths:
            if path == tree or path.startswith(tree + "/"):
                leaked.add(tree)
                break
    return sorted(leaked)


def wheel_expected_members(table=None, modules=None):
    """Every path the WHEEL owes: the package's modules + the DECLARED package data.

    ``dist-info`` members are backend-written and allow-listed by prefix rather
    than enumerated, so a metadata file the backend adds tomorrow is not a false
    positive.

    **The two halves are derived differently on purpose (LD-215 AC4).** The
    package-data half is name-derived from the declaration, so it survives its files
    disappearing. The module half is still ``src/**.py`` off disk — a judgment call,
    recorded: a declaration for the modules exists nowhere (``packages.find`` names a
    *directory*, not files), and a module vanishing from ``src/`` is anything but
    silent — imports across the suite break, the README layout table's bidirectional
    guard (:func:`real_top_level`) reddens, and ``capabilities()`` changes shape. The
    package-data files had no such second witness, which is exactly why AC4 singles
    them out as the more damaging regression.
    """
    modules = source_modules() if modules is None else modules
    return modules | declared_package_data(table)


def unexpected_wheel_members(paths):
    """Every wheel path outside the allow-list. Pure — runs over synthetic input."""
    allowed = source_modules() | allowed_package_data()
    prefix = dist_info_prefix()
    return sorted(
        path for path in paths
        if path not in allowed and not path.startswith(prefix)
    )


def missing_wheel_members(paths, expected=None):
    """Every owed wheel path that is absent — a declared file that disappeared."""
    expected = wheel_expected_members() if expected is None else expected
    return sorted(expected - set(paths))


def pyproject_comment_prose(text=None):
    """``pyproject.toml``'s COMMENT text as comparable prose.

    Leading ``#`` stripped, then whitespace collapsed (:func:`doc_prose.prose`), so a
    phrase assertion is immune to the file's hard wrapping. LD-215's first round
    forbade the raw literal ``"there is no MANIFEST.in here"`` — a string the file
    never contained, because the sentence was split across two comment lines, so the
    check passed against the very text it was written to reject.
    """
    text = PYPROJECT.read_text(encoding="utf-8") if text is None else text
    lines = [
        re.sub(r"^\s*#\s?", "", line)
        for line in text.splitlines()
        if line.lstrip().startswith("#")
    ]
    return prose(" ".join(lines))


# --------------------------------------------------------------------------- #
# 6. LD-440 — the OPENING CENSUS and the guide-size literal                     #
#                                                                              #
# The census — the README's first paragraph — is the whole product claim a      #
# reader meets before anything else, and it rotted through the LD-403..LD-434   #
# arc: it still called drive "folder read" after three drive WRITE surfaces     #
# shipped. Nothing covered it, because `Summary` coverage was the only          #
# census pinned. These helpers pin the paragraph the same derived way.          #
# --------------------------------------------------------------------------- #

#: Census words that name a surface family in prose rather than in a surface id. Recorded
#: with the id each stands for, so the reverse check can tell a legitimate synonym from a
#: surface somebody invented in the opening paragraph.
CENSUS_ALIASES = {
    "reader": "docx-read",
    "writer": "docx-write",
    "documents": "docx-read",
    "spreadsheets": "sheets-read",
    "bases": "base-read",
    "bitable": "base-read",
    "folder": "drive-read",
    "authoring": "docx-write",
    "markdown": "docx-read",
}


def opening_census(text=None):
    """The README's opening paragraph — everything between the ``# larkdocio`` H1 and the
    first blank line after it. That paragraph IS the product claim; a surface missing from
    it is a surface the reader concludes does not exist.
    """
    text = readme_text() if text is None else text
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("# ")), None)
    if start is None:
        return ""
    body = []
    for line in lines[start + 1:]:
        if line.strip() == "":
            if body:
                break
            continue
        body.append(line)
    return "\n".join(body)


def census_gaps(text=None, required=None):
    """The surface words :func:`required_surface_keywords` demands that the census omits.

    Same word-level contract as :func:`description_surface_gaps` — derived from
    ``capabilities()``, so a new surface family widens the requirement with nobody editing
    a list, and the prose stays the author's to write.
    """
    census = opening_census() if text is None else text
    required = required_surface_keywords() if required is None else required
    lowered = census.lower()
    return sorted(word for word in required if word.lower() not in lowered)


_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_WORD = re.compile(r"[A-Za-z][A-Za-z-]+")

#: Connective words that appear inside a bolded census term ("**documents, spreadsheets and
#: bases**") and name nothing. Listed rather than guessed at, so the reverse check reports a
#: real invention instead of English.
_CENSUS_STOPWORDS = frozenset({"and", "or", "the", "its", "their", "plus", "with", "of"})


def census_phantom_families(text=None):
    """Bolded census terms that name no surface ``capabilities()`` reports.

    The other direction of the same guard: the census may not advertise a surface family
    that does not exist. Only **bolded** terms are read — those are the census's own
    naming device — and a term counts as real when it appears in a surface id or is a
    recorded prose alias for one (:data:`CENSUS_ALIASES`).
    """
    import larkdocio

    census = opening_census() if text is None else text
    surfaces = list(larkdocio.capabilities(full=True)["surfaces"])
    phantoms = []
    for span in _BOLD.findall(census):
        for word in _WORD.findall(span):
            low = word.lower()
            if low in _CENSUS_STOPWORDS or low in CENSUS_ALIASES:
                continue
            if any(low in sid for sid in surfaces):
                continue
            phantoms.append(word)
    return sorted(set(phantoms))


#: The guide's byte size, stated as a hard number, is a claim that drifts silently — it was
#: ``200 KB`` in four places while the document had grown past 500 KiB. The literal is banned
#: from the front door; a magnitude may be stated only in non-numeric prose.
GUIDE_SIZE_LITERAL = re.compile(r"\b\d{2,4}\s?KB\b", re.IGNORECASE)

#: Front-door surfaces the literal guard reads. ``CHANGELOG.md`` / ``RELEASE_NOTES.md`` are
#: deliberately absent: their entries are DATED RECORDS of what was true at a release, not
#: current claims, and rewriting history to match today is the opposite of the discipline.
#: LD-441 admitted ``src/larkdocio/GUIDE.md`` — the guide's own copy of the literal was the
#: last one, and the debt table it used to sit in is now empty (see ``GUIDE_SIZE_DEBT``).
GUIDE_SIZE_SCOPE = ("README.md", "src/larkdocio/cli.py", "TOOLS.md",
                    "src/larkdocio/GUIDE.md")

#: Known, owned debt — a front-door-adjacent file that still carries the literal, with the
#: issue that owns it. ``test_ac10_*`` reddens when an entry stops being needed, so the
#: table cannot outlive its debt. **Empty since LD-441 de-numbered the guide**; the entry was
#: not deleted silently — its file moved into ``GUIDE_SIZE_SCOPE`` in the same change, which
#: is what "the debt is paid" means here.
GUIDE_SIZE_DEBT = {}

#: A KB literal that measures something OTHER than the packaged guide, and therefore is not
#: this guard's business. LD-441: the guide's ``retain_base_raw_values`` flag row states the
#: MEMORY cost of raw retention (≈260 KB of raw against ≈38 KB of rendered cells, on a
#: 64-row read of a real four-column table). That is a *measurement of a payload*, not a size
#: claim about this document — de-numbering it would delete the evidence, which is the
#: opposite of the discipline the literal ban exists for.
#: The marker is the MEASUREMENT ITSELF, not the flag's name, for two reasons: it appears in
#: both places the figure is stated (the flag table and the raw-retention recipe), and if the
#: measurement is ever re-taken the exemption stops matching and has to be re-cut deliberately
#: rather than quietly covering a new number.
GUIDE_SIZE_LITERAL_EXEMPT = ("≈260 KB against ≈38 KB",)


def guide_size_literal_offenders(paths=None):
    """``[(path, lineno, line)]`` for every hard KB guide-size claim in the scope."""
    offenders = []
    for rel in (GUIDE_SIZE_SCOPE if paths is None else paths):
        target = REPO_ROOT / rel
        if not target.exists():
            continue
        for lineno, line in enumerate(target.read_text(encoding="utf-8").splitlines(), 1):
            if any(marker in line for marker in GUIDE_SIZE_LITERAL_EXEMPT):
                continue
            if GUIDE_SIZE_LITERAL.search(line):
                offenders.append((rel, lineno, line.strip()))
    return offenders


STALE_READ_ONLY_CLAIM = re.compile(r"command line (?:is|stays) read-only")

STALE_READ_ONLY_CLAIM_EXEMPT_FILES = {
    "src/larkdocio/CHANGELOG.md",
    "src/larkdocio/RELEASE_NOTES.md",
}

#: A specific, honest exemption for a claim that is being QUOTED (as superseded), not made —
#: LD-483-style: each entry is a ``(reason, fragment)`` pair, where ``fragment`` is a
#: distinguishing substring of the MATCHED LINE ITSELF, never a neighbourhood around it.
#: LD-502 round 2 (QA FAIL on AC4): the original design joined a +-5-line window around a
#: candidate match and required the markers to co-occur somewhere in it — which exempted ANY
#: stale-claim match landing near the markers, including an unrelated false claim planted a few
#: lines away, not just the one sentence the markers describe. Binding to the matched line's own
#: text closes that: a neighbouring line has no window to land inside, because there is no
#: window at all — only the exact line the fragment names can ever match.
#: Checked by ``test_ld502_the_quotation_exemption_allow_list_is_held_honest`` against the real
#: shipped text: the fragment must be a substring of a line that is itself a genuine
#: :data:`STALE_READ_ONLY_CLAIM` match, and of exactly one such line — an entry whose fragment no
#: longer sits on a real match (the text moved) or that binds to more than one match (too generic
#: to be honest) reddens. Only ever consulted for the two files in
#: :data:`STALE_READ_ONLY_CLAIM_EXEMPT_FILES`, and only for a match still inside the open
#: (un-cut) top section — a match already inside a cut section is exempt on cut-ness alone.
#: LD-502 round 3 (QA FAIL on AC4, again): binding to "the matched LINE contains the fragment"
#: still exempted a WHOLE line, and a line can carry more than one
#: :data:`STALE_READ_ONLY_CLAIM` match — so a line holding both a verbatim copy of the fragment
#: AND a brand-new, unrelated false claim was excused entirely, new claim included. Each MATCH is
#: now judged on its own span: exempt only if that match's own start/end lie inside the
#: fragment's own span on the line, so a match outside the fragment (before it, after it, or on a
#: different line) can never borrow the exemption, no matter what else shares the line.
STALE_READ_ONLY_CLAIM_QUOTATION_EXEMPT = {
    "src/larkdocio/CHANGELOG.md": (
        (
            "the LD-492 supersession entry: the phrase is wrapped in the file's *\"...\"* "
            "markdown-quote styling and attributed to 'the layout table' as the source being "
            "retired, not a claim being made — the whole quotation sits on this one line.",
            "layout table's *\"the command line stays read-only\"*",
        ),
    ),
    "src/larkdocio/RELEASE_NOTES.md": (
        (
            "the LD-492 supersession entry: 'said' marks this as reported speech about what "
            "the README used to claim, not a live claim of its own — the whole clause sits on "
            "this one line.",
            "said the command line is read-only",
        ),
    ),
}


def _is_quoted_as_superseded(rel, line, match):
    """True if ``match`` — a single :data:`STALE_READ_ONLY_CLAIM` match object found on
    ``line`` — is covered by an entry in :data:`STALE_READ_ONLY_CLAIM_QUOTATION_EXEMPT`: i.e.
    THIS SPECIFIC MATCH's own span lies inside the fragment's own span on the line, proving THIS
    match is part of a quotation of a superseded claim, not a live one.

    LD-502 round 3: round 2 bound the exemption to "the matched line contains the fragment",
    which is a LINE-level test even though a line can carry more than one match — so a line
    holding a verbatim copy of the fragment *and* a brand-new, unrelated false claim was exempt
    whole, new claim included. Binding to match-span-inside-fragment-span judges each match on
    its own: a match whose characters are not the fragment's own characters is never exempt, no
    matter what else shares its line."""
    entries = STALE_READ_ONLY_CLAIM_QUOTATION_EXEMPT.get(rel)
    if not entries:
        return False
    for _reason, fragment in entries:
        start = line.find(fragment)
        if start == -1:
            continue
        end = start + len(fragment)
        if match.start() >= start and match.end() <= end:
            return True
    return False


def stale_read_only_claims():
    """``[(path, lineno, line)]`` for every live blanket "the command line is read-only /
    stays read-only" claim anywhere under ``src/`` — the phrasing LD-492 made false the moment
    ``roundtrip push --apply`` shipped (LD-495).

    ``CHANGELOG.md`` and ``RELEASE_NOTES.md`` are exempt in exactly two shapes, both keyed on
    the claim's own section, never on "everything after the first header" (LD-502 — that
    boundary wrongly exempted the currently-open section too, since the topmost ``## [x.y.z]``
    section in either file is normally still **un-cut**, per each file's own preamble):

    1. **A CUT section is wholesale exempt.** A cut, dated, closed release is a historical
       record and must never be edited (``scripts/release.sh`` gate f enforces the date half of
       that rule already), so any claim inside one — quoted or asserted — stands. Cut sections
       start at the file's **second** ``## [`` header onward; the topmost section, and any text
       before it, is never cut and is fully in scope.
    2. **A claim QUOTED AS SUPERSEDED inside the still-open top section is individually
       exempt**, via the narrow, reason-carrying :data:`STALE_READ_ONLY_CLAIM_QUOTATION_EXEMPT`
       allow-list — a claim being *retired* (describing what LD-492 corrected) is not a claim
       being *made*. **The exemption binds to the specific MATCH's own span, never the whole
       line** (LD-502 round 3 — binding to "the line contains the fragment" still let a
       brand-new, unrelated match sharing that line with a verbatim copy of the fragment borrow
       the exemption): a line can carry more than one match, and each is judged on its own — a
       match is exempt only if its own characters lie inside the exact fragment span an
       allow-list entry names, never because some OTHER match on the same line does. The line is
       reported only if at least one of its matches is not exempt, so a genuinely new claim is
       caught whether it sits before, after, or (on a different line) nowhere near the real
       quotation — which is exactly the hole this rule closes.
    """
    offenders = []
    for path in sorted((REPO_ROOT / "src").rglob("*")):
        if not path.is_file() or path.suffix not in (".py", ".md"):
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        cut_section_starts_at = None
        exempt_file = rel in STALE_READ_ONLY_CLAIM_EXEMPT_FILES
        if exempt_file:
            headers = [i for i, line in enumerate(lines) if line.startswith("## [")]
            if len(headers) >= 2:
                cut_section_starts_at = headers[1]
        for i, line in enumerate(lines):
            if cut_section_starts_at is not None and i >= cut_section_starts_at:
                continue
            matches = list(STALE_READ_ONLY_CLAIM.finditer(line))
            if not matches:
                continue
            if exempt_file and all(
                _is_quoted_as_superseded(rel, line, m) for m in matches
            ):
                continue
            offenders.append((rel, i + 1, line.strip()))
    return offenders


def group_option_block(page=None):
    """The ``Options:`` block of the rendered group page — the options click defines ON THE
    GROUP, as opposed to any option the prose above it mentions belonging to a subcommand.

    LD-440 needed the distinction: the group help must be free to SAY that
    ``download --deep-read-bases`` exists (denying it was the defect) while still not
    advertising it as a group-level option.
    """
    page = group_help_page() if page is None else page
    if "Options:" not in page:
        return ""
    tail = page.split("Options:", 1)[1]
    return tail.split("\nCommands:", 1)[0]


# =====================================================================
# LD-645 — THE DRIVE WRITE LEGS' VERIFICATION POSTURE, DERIVED ONCE.
#
# WHY THIS LIVES HERE. Three shipped artifacts gave three different counts of
# how many Drive write legs verify their own write, and the front door — the
# README, which IS the wheel's METADATA body — gave a fourth: it introduced
# FOUR legs, enumerated THREE, and said the read-back was on "the access leg
# only". Nothing was looking, which is this module's own diagnosis of its
# original defect, in a new place. The split is now derived from the census in
# ONE function and every guard that states it imports THIS one.
# =====================================================================

#: The safety contracts whose subject is an IN-LIBRARY verification of a Drive write —
#: performed by the shipped call path, not by a credential-gated live gate. A leg declaring
#: one verifies; a leg declaring none does not.
DRIVE_VERIFYING_CONTRACTS = {
    "read-back-is-the-verdict",     # the access leg: a member read AFTER the write
    "bytes-verified-round-trip",    # the file leg: a re-download compared by sha256 + length
}

#: Contracts a Drive write leg may declare that are NOT an in-library verification, each with
#: the reason it is not. Enumerated rather than inferred so that a NEW Drive contract cannot
#: land unclassified and be silently read as "does not verify" — the shape of the defect this
#: whole cluster was: silence answering for two opposite facts.
DRIVE_NON_VERIFYING_CONTRACTS = {
    # WHERE a new object goes. A destination refusal is about the ask, not about the write's
    # outcome, and it fires BEFORE any call.
    "caller-supplied-destination",
    # The versions leg's pre-write revision read, declared to say what it IS: a pairing that
    # makes (name, token, revision) one row, never a verdict on the write.
    "version-pairing-is-not-a-verdict",
}


def drive_write_legs(surfaces):
    """``{surface id: spec}`` for every Drive surface whose mode is ``write``."""
    return {
        sid: spec for sid, spec in surfaces.items()
        if spec.get("domain") == "drive" and spec.get("mode") == "write"
    }


def drive_verification_split(surfaces):
    """``(legs, verified, unverified)`` — the census's own answer to AC1's question.

    Raises rather than guesses when a leg declares a contract this module has never
    classified: an unclassified contract makes the split silently wrong in whichever
    direction the default happens to be.
    """
    legs = drive_write_legs(surfaces)
    unclassified = {}
    for sid, spec in legs.items():
        unknown = (set(spec.get("safety_contracts") or ())
                   - DRIVE_VERIFYING_CONTRACTS - DRIVE_NON_VERIFYING_CONTRACTS)
        if unknown:
            unclassified[sid] = sorted(unknown)
    if unclassified:
        raise AssertionError(
            f"unclassified Drive write contract(s) {unclassified} — add each to "
            f"DRIVE_VERIFYING_CONTRACTS or DRIVE_NON_VERIFYING_CONTRACTS (with its reason) "
            f"in tests/front_door.py before any guard restates the split"
        )
    verified = {sid for sid, spec in legs.items()
                if DRIVE_VERIFYING_CONTRACTS & set(spec.get("safety_contracts") or ())}
    return legs, verified, set(legs) - verified


def drive_leg_aliases(sid):
    """The words prose is allowed to identify one leg by, DERIVED from its surface id.

    ``drive-files-write`` → ``{"files", "file"}``, ``drive-access-write`` → ``{"access"}``.
    A README says *"the file leg"* and *"an access grant"* rather than ``put_file_in_folder``,
    so a guard demanding op names would have demanded prose no consumer document writes.
    """
    segment = sid.split("-")[1]
    aliases = {segment}
    if segment.endswith("s") and not segment.endswith("ss"):
        aliases.add(segment[:-1])
    return aliases


#: The marker that identifies a front-door paragraph making a claim about the Drive write
#: legs as a SET. A paragraph that names the set is a paragraph that owes the whole set.
DRIVE_LEG_SET_MARKER = "drive write leg"


def drive_leg_paragraphs(text):
    """Every paragraph of ``text`` that speaks about the Drive write legs as a set.

    Paragraphs are split BEFORE ``prose()`` normalises each one: this document wraps its
    prose, and a phrase match across a line break silently returns nothing (measured on this
    very issue). Each returned paragraph is therefore one line of comparable words.
    """
    return [prose(para) for para in re.split(r"\n\s*\n", text)
            if DRIVE_LEG_SET_MARKER in prose(para)]


def drive_legs_missing_from(paragraph, legs):
    """Which of ``legs`` a paragraph enumerating the set fails to identify at all."""
    lowered = paragraph.lower()
    return sorted(
        sid for sid in legs
        if not (any(alias in lowered for alias in drive_leg_aliases(sid))
                or sid in lowered)
    )
