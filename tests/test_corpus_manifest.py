"""The corpus manifest guard (LD-368) — ``requirements/CORPUS.md`` held true, BOTH ways.

**The north star this exists to serve**, ruled in the maintainer seat 2026-08-09 (paraphrased):

    the maintainers' record corpus should be able to regenerate the library — not
    deterministically, but each artifact class narrows the variance.

A corpus that cannot be **enumerated** narrows nothing, because the first question a
regenerating reader asks is *what am I allowed to read?* ``requirements/CORPUS.md`` answers it
**by manifest**, and a manifest entry may be a **location** (*"everything under
``requirements/``"*) where the directory is the unit.

**The shape is borrowed, not invented.** ``tests/test_front_door_doctrine.py`` holds the front
door **complete in both directions** against the code it describes — the README layout table ↔
the real top level of ``src/larkdocio``, the documented CLI options ↔ click's own params. This
file applies that doctrine to the repository's own top level:

1. **Direction 1** — every manifest entry resolves to a real file or directory, unless it is an
   explicitly **marked forward reference** (``forward-referenced (LD-NNN)``), which must name
   the issue that will land it.
2. **Direction 2** — every root ``*.md`` and every top-level directory is **classified**, in
   exactly one of **corpus / process-kit / product / ledger / generated**. *An unclassified
   newcomer reddens the build* — that is the whole point: the repo grows, and nothing else asks
   a new arrival which of those five it is.

**Why the walk is one level deep and nothing more** (LD-368 AC8). A guard that recursed into
``tests/``, ``src/`` and ``dev/`` would ask a human to classify several thousand files, and a
guard nobody keeps green guards nothing. The unit of classification is the unit a reader
actually navigates: a root document, or a top-level directory. Exclusions are **declared and
argued** in :data:`EXCLUDED` below rather than left incidental, and
:func:`test_every_exclusion_is_DECLARED_not_incidental` checks each one against ``.gitignore``
itself.

**No git is invoked** — ``tests/test_no_test_reads_live_git.py`` forbids it suite-wide, and it
is right to: a guard that asked git what is tracked would answer differently on every branch.
This reads the tree, and reads ``.gitignore`` as *text*.
"""
import pathlib
import re
import time

from guard_kit import REPO_ROOT, md_table_rows, section
import private_tree  # noqa: E402  (LD-685)

CORPUS_MD = REPO_ROOT / "requirements" / "CORPUS.md"
GITIGNORE = REPO_ROOT / ".gitignore"

#: The five-word classification vocabulary. Every root document and every top-level directory
#: lands in **exactly one**; a sixth word is a finding, not a row to add.
CLASSES = ("corpus", "process-kit", "product", "ledger", "generated")

#: The marker a manifest entry wears while the thing it names is *scheduled but not yet
#: written*. Listing a future file silently would make direction 1 either a lie or a nag; the
#: marker makes the promise explicit and dated by its issue id.
FORWARD_RE = re.compile(r"^forward-referenced \((LD-\d+)\)$")

#: The headings the guard slices. Renaming one in ``CORPUS.md`` without renaming it here
#: reddens :func:`test_the_document_carries_the_sections_this_guard_reads`, by design.
MANIFEST_HEADING = "## The manifest"
CLASSIFICATION_HEADING = "## Classification"
EDGE_HEADING = "## Edge cases"

# --------------------------------------------------------------------------- #
# THE SCOPE OF THE WALK — root ``*.md`` + top-level directories, and nothing    #
# else. Every exclusion below is DECLARED here with its reason rather than      #
# happening to be skipped, and is cross-checked against ``.gitignore``.         #
# --------------------------------------------------------------------------- #

#: Top-level directory names the walk never classifies, each with why. All but ``.git`` are
#: gitignored — they are *machine state*, not repository content, so asking a human to
#: classify them would be asking about the machine rather than about larkdocio.
EXCLUDED = {
    ".git": "git's own object store — not repository content, and not in .gitignore either",
    ".venv": "the virtualenv (gitignored)",
    ".venv-mutation": "the mutation meter's OWN virtualenv (gitignored) — LD-504: "
                      "scripts/mutation-check.sh installs mutmut there so setproctitle "
                      "never enters the env that runs the suite",
    "venv": "the alternate virtualenv name .gitignore also covers",
    "env": "the third virtualenv name .gitignore covers",
    "build": "packaging scratch from `python -m build` (gitignored)",
    "dist": "the built sdist/wheel (gitignored)",
    ".kanban-wt": "the standing kanban worktree (gitignored)",
    ".kanban-wt.lock": "the kanban worktree's lock directory (gitignored)",
    ".kanban-wt.lock.reap": "the kanban lock's reaper directory (gitignored)",
    ".worktrees": "worktrees made by the using-git-worktrees skill (gitignored)",
    "__pycache__": "bytecode cache (gitignored)",
    ".pytest_cache": "pytest's cache (gitignored)",
    "htmlcov": "coverage HTML output (gitignored)",
    "mutants": "mutmut's throwaway working tree (gitignored)",
}

#: Two *patterns* .gitignore carries that no exact name can express: the egg-info directory
#: (its name follows the distribution) and the sdist staging directory `python -m build`
#: creates for a moment mid-build (``larkdocio-<version>/``). Both are transient build state.
EXCLUDED_PATTERNS = (
    (re.compile(r".+\.egg-info$"), "*.egg-info/ — editable-install metadata (gitignored)"),
    (re.compile(r"^larkdocio-[0-9].*$"), "the sdist staging copy `build` makes (gitignored)"),
)


def is_excluded(name):
    """Is this top-level directory name machine state rather than repository content?"""
    if name in EXCLUDED:
        return True
    return any(pattern.match(name) for pattern, _reason in EXCLUDED_PATTERNS)


def root_documents(root=REPO_ROOT):
    """Every root-level ``*.md`` file — the walk's first half. **One level, never a rglob.**"""
    return sorted(p.name for p in root.iterdir() if p.is_file() and p.suffix == ".md")


def top_level_directories(root=REPO_ROOT):
    """Every top-level directory that is repository content, named with a trailing ``/``.

    One ``iterdir()``. Nothing descends — see the module docstring on why the depth is one.
    """
    return sorted(
        f"{p.name}/" for p in root.iterdir() if p.is_dir() and not is_excluded(p.name))


# --------------------------------------------------------------------------- #
# READING THE DOCUMENT                                                          #
# --------------------------------------------------------------------------- #

class Entry:
    """One manifest row: the path it names, whether it is here yet, and why it is corpus."""

    def __init__(self, path, kind, status, reason):
        self.path = path
        self.kind = kind
        self.status = status
        self.reason = reason

    @property
    def forward_issue(self):
        """``LD-NNN`` if this entry is a marked forward reference, else ``None``."""
        match = FORWARD_RE.match(self.status)
        return match.group(1) if match else None

    def __repr__(self):
        return f"<Entry {self.path} ({self.status})>"


def _unbacktick(cell):
    return cell.strip().strip("`").strip()


def _data_rows(text, heading):
    """The rows of the one table under ``heading``, header row dropped."""
    rows = md_table_rows(section(text, heading))
    return [row for row in rows if row and not row[0].lower().startswith("entry")
            and not row[0].lower().startswith("path")]


def manifest_entries(text):
    """Every manifest row of ``text`` as an :class:`Entry`."""
    return [Entry(_unbacktick(row[0]), _unbacktick(row[1]), _unbacktick(row[2]),
                  row[3].strip() if len(row) > 3 else "")
            for row in _data_rows(text, MANIFEST_HEADING) if len(row) >= 3]


def classifications(text):
    """``{path: (class, reason)}`` from the classification table."""
    table = {}
    for row in _data_rows(text, CLASSIFICATION_HEADING):
        if len(row) >= 2:
            table[_unbacktick(row[0])] = (_unbacktick(row[1]),
                                          row[2].strip() if len(row) > 2 else "")
    return table


# --------------------------------------------------------------------------- #
# THE TWO DIRECTIONS, as pure functions so each can be driven with a SYNTHETIC  #
# tree in a red-proof test as well as with the real one.                        #
# --------------------------------------------------------------------------- #

def unresolved(entries, exists):
    """Direction 1: entries naming something that is not there and is not marked pending."""
    return [entry for entry in entries
            if entry.forward_issue is None and not exists(entry.path)]


def unresolved_message(offenders):
    return (
        "these `requirements/CORPUS.md` manifest entries name a path that does not exist:\n"
        + "\n".join(f"  - {entry.path}" for entry in offenders)
        + "\n\nEither the path moved (correct the manifest entry to where it lives now), or it "
          "has not been written yet — in which case mark the entry "
          "`forward-referenced (LD-NNN)` and name the issue that will land it."
    )


def unclassified(present, classified):
    """Direction 2: things in the repo's top level that ``CORPUS.md`` says nothing about."""
    return sorted(set(present) - set(classified))


def unclassified_message(offenders):
    return (
        "these root documents / top-level directories are NOT classified in "
        "`requirements/CORPUS.md`:\n"
        + "\n".join(f"  - {name}" for name in offenders)
        + "\n\nAdd a row to its `## Classification` table putting each in exactly one of "
        + " / ".join(CLASSES)
        + " — and if it is `corpus`, add it to `## The manifest` with its one-line reason too. "
          "A new top-level arrival that nobody classified is how the corpus silently stops "
          "being complete; that is what this guard exists to prevent."
    )


# =========================================================================== #
# AC1/AC2 — the document exists, is a manifest, and every entry earns its row   #
# =========================================================================== #

@private_tree.citations
def test_the_corpus_manifest_EXISTS_where_the_corpus_lives():
    assert CORPUS_MD.is_file(), (
        "requirements/CORPUS.md is missing — the corpus is only enumerable if something "
        "enumerates it (LD-368)")


@private_tree.register
def test_the_document_carries_the_sections_this_guard_reads():
    text = CORPUS_MD.read_text(encoding="utf-8")
    for heading in (MANIFEST_HEADING, CLASSIFICATION_HEADING, EDGE_HEADING):
        assert section(text, heading).strip(), f"CORPUS.md has no `{heading}` section"


@private_tree.register
def test_every_manifest_entry_carries_a_ONE_LINE_REASON():
    """AC1: a manifest of bare paths tells a regenerating reader nothing about *why* each is
    in the input set — the reason is the part that narrows variance."""
    entries = manifest_entries(CORPUS_MD.read_text(encoding="utf-8"))
    assert entries, "CORPUS.md's manifest table is empty"
    thin = [entry.path for entry in entries if len(entry.reason) < 25]
    assert not thin, f"these manifest entries have no real reason: {thin}"


@private_tree.register
def test_the_manifest_uses_BOTH_forms_locations_and_enumeration():
    """The maintainer's ruling on the form: a manifest entry **may be a LOCATION**. Enumerate where
    enumeration is honest; point at a directory where the directory is the unit."""
    kinds = {entry.kind for entry in manifest_entries(CORPUS_MD.read_text(encoding="utf-8"))}
    assert "location" in kinds and "file" in kinds, kinds


@private_tree.register
def test_the_INITIAL_MEMBERSHIP_the_issue_named_is_all_present():
    """AC2, item by item — including the ``TOOLS.md`` ruling and both forward references."""
    paths = {entry.path for entry in manifest_entries(CORPUS_MD.read_text(encoding="utf-8"))}
    for required in (
        "requirements/",                       # a directory member, + CORPUS.md
        "requirements/DECISIONS.md",           # promoted marker → member by LD-369
        "BLOCKS.md", "SHEETS.md", "BASE.md", "DRIVE.md", "PERMISSIONS.md",
        "TOOLS.md",                            # Dev's ruling: IN — argued in CORPUS.md
        "README.md", "RELEASE_NOTES.md",
        "src/larkdocio/GUIDE.md", "src/larkdocio/write/README.md",
        "process/doctrine/conformance-tier.md",  # promoted marker → member by LD-370
    ):
        assert required in paths, f"{required} is missing from CORPUS.md's manifest"


@private_tree.register
def test_a_FORWARD_REFERENCE_is_MARKED_and_names_its_issue():
    """AC2: *marked* as forward-referenced rather than silently listed. A silent listing is
    indistinguishable from a broken path, which is precisely what direction 1 must not be.

    Both markers LD-368 wrote have since been promoted (LD-369, LD-370), so what survives here
    is the **spelling rule** the parser depends on — the half that keeps working for the next
    marker somebody writes."""
    entries = {e.path: e for e in manifest_entries(CORPUS_MD.read_text(encoding="utf-8"))}
    for entry in entries.values():
        if entry.forward_issue is None:
            assert "forward" not in entry.status.lower(), (
                f"{entry.path} says '{entry.status}' — a forward reference must be spelled "
                f"exactly `forward-referenced (LD-NNN)` so the guard can honour it")


@private_tree.register
def test_the_DECISIONS_forward_reference_was_PROMOTED_to_a_real_member():
    """LD-369: the marker's whole point is that it is temporary. `requirements/DECISIONS.md` was
    marked `forward-referenced (LD-369)` by LD-368 and is now a **present** entry backed by a real
    file — so this pins the promotion rather than tolerating a marker that outlived its issue."""
    entry = {e.path: e for e in manifest_entries(CORPUS_MD.read_text(encoding="utf-8"))}[
        "requirements/DECISIONS.md"]
    assert entry.forward_issue is None and entry.status == "present", (
        f"DECISIONS.md is still marked '{entry.status}' — LD-369 landed the file, so the marker "
        f"must be gone; a marker whose issue has landed is a stale promise")
    assert (REPO_ROOT / "requirements/DECISIONS.md").exists()


@private_tree.register
def test_the_CONFORMANCE_TIER_forward_reference_was_PROMOTED_to_a_real_member():
    """LD-370: the second — and last — of LD-368's markers. `process/doctrine/conformance-tier.md`
    was marked `forward-referenced (LD-370)`; LD-370 landed the doctrine, so the marker must be
    gone and the path must resolve. A marker whose issue has landed is a stale promise."""
    entry = {e.path: e for e in manifest_entries(CORPUS_MD.read_text(encoding="utf-8"))}[
        "process/doctrine/conformance-tier.md"]
    assert entry.forward_issue is None and entry.status == "present", (
        f"conformance-tier.md is still marked '{entry.status}' — LD-370 landed the file")
    assert (REPO_ROOT / "process/doctrine/conformance-tier.md").exists()


# =========================================================================== #
# AC5 direction 1 — every manifest entry resolves                              #
# =========================================================================== #

@private_tree.register
def test_DIRECTION_1_every_manifest_entry_RESOLVES_or_is_a_marked_forward_reference():
    entries = manifest_entries(CORPUS_MD.read_text(encoding="utf-8"))
    offenders = unresolved(entries, lambda path: (REPO_ROOT / path).exists())
    assert not offenders, unresolved_message(offenders)


# =========================================================================== #
# AC5 direction 2 — every root doc and top-level directory is classified        #
# =========================================================================== #

@private_tree.register
def test_DIRECTION_2_every_root_document_and_top_level_directory_is_CLASSIFIED():
    table = classifications(CORPUS_MD.read_text(encoding="utf-8"))
    present = root_documents() + top_level_directories()
    offenders = unclassified(present, table)
    assert not offenders, unclassified_message(offenders)


@private_tree.register
def test_the_classification_table_has_no_PHANTOM_rows():
    """The other half of direction 2: a row for something that no longer exists is a stale
    claim, and stale claims are how a matrix rots while staying green."""
    table = classifications(CORPUS_MD.read_text(encoding="utf-8"))
    present = set(root_documents() + top_level_directories())
    phantoms = sorted(set(table) - present)
    assert not phantoms, (
        f"CORPUS.md classifies things that are not at the repo's top level: {phantoms} — "
        "delete the row, or correct the path if it moved")


@private_tree.register
def test_every_class_is_one_of_the_FIVE_and_each_path_appears_ONCE():
    text = CORPUS_MD.read_text(encoding="utf-8")
    table = classifications(text)
    bad = {path: klass for path, (klass, _why) in table.items() if klass not in CLASSES}
    assert not bad, f"classes outside the five-word vocabulary: {bad}"
    rows = [_unbacktick(row[0]) for row in _data_rows(text, CLASSIFICATION_HEADING)
            if len(row) >= 2]
    assert len(rows) == len(set(rows)), (
        f"a path is classified twice — 'exactly one' is the rule: "
        f"{sorted({r for r in rows if rows.count(r) > 1})}")


@private_tree.register
def test_every_classification_row_carries_its_REASON():
    table = classifications(CORPUS_MD.read_text(encoding="utf-8"))
    thin = sorted(path for path, (_klass, why) in table.items() if len(why) < 20)
    assert not thin, f"these classification rows assert a bucket without arguing it: {thin}"


@private_tree.register
def test_the_two_TABLES_AGREE_every_corpus_row_is_a_manifest_entry():
    """The bond between the two halves. Calling something ``corpus`` in one table and leaving
    it out of the manifest would let the corpus be two different sets at once."""
    text = CORPUS_MD.read_text(encoding="utf-8")
    table = classifications(text)
    listed = {entry.path for entry in manifest_entries(text)}
    missing = sorted(path for path, (klass, _why) in table.items()
                     if klass == "corpus" and path not in listed)
    assert not missing, (
        f"classified `corpus` but absent from the manifest: {missing}")


# =========================================================================== #
# AC3 — every named edge case is ARGUED INSIDE THE FILE                        #
# =========================================================================== #

#: The edges LD-368 AC3 names by hand, plus the three this issue met while walking the tree.
#: A decision recorded only in a commit message is a FAIL: the next reader has only the file.
EDGE_CASES = (
    "dev/", "PROJECT.md", "CLAUDE.md", "CHANGELOG.md", "ARCHIVE.md", "progress.md",
    "docs/", "consumers/", "TOOLS.md", "PERMISSIONS.md", "tests/",
)


@private_tree.register
def test_every_EDGE_CASE_is_argued_in_CORPUS_MD_itself():
    text = CORPUS_MD.read_text(encoding="utf-8")
    edges = section(text, EDGE_HEADING)
    for name in EDGE_CASES:
        assert f"`{name}`" in edges, (
            f"{name} is not argued in CORPUS.md's `{EDGE_HEADING}` section — AC3: the file "
            f"must argue for itself, because the next reader will have only the file")


@private_tree.register
def test_the_dev_CAPTURES_ruling_is_stated_as_the_issue_framed_it():
    """The one edge the maintainer pre-framed: ``dev/`` probe captures are an **evidence ledger** —
    referenced by the corpus, not corpus-core. Dev states it, or overturns it with a reason."""
    edges = section(CORPUS_MD.read_text(encoding="utf-8"), EDGE_HEADING).lower()
    assert "evidence ledger" in edges, edges[:400]
    assert "referenced" in edges and "corpus-core" in edges


@private_tree.register
def test_each_edge_case_ARGUMENT_is_more_than_a_sentence():
    """An 'argument' that is one clause is a verdict. Each edge gets a paragraph."""
    edges = section(CORPUS_MD.read_text(encoding="utf-8"), EDGE_HEADING)
    assert len(edges.split()) > 700, (
        f"the edge-case section is {len(edges.split())} words — too thin to have argued "
        f"{len(EDGE_CASES)} edges")


# =========================================================================== #
# AC6 — the guard is SEEN to redden for an unclassified newcomer                #
# =========================================================================== #

def test_an_UNCLASSIFIED_NEW_ROOT_DOCUMENT_is_rejected_BY_NAME(tmp_path):
    """A synthetic top level: the same two functions the real test uses, driven over a tree
    that has a newcomer nobody classified."""
    (tmp_path / "README.md").write_text("#\n", encoding="utf-8")
    (tmp_path / "NEW_THING.md").write_text("#\n", encoding="utf-8")
    offenders = unclassified(root_documents(tmp_path), {"README.md": ("corpus", "…")})
    assert offenders == ["NEW_THING.md"], offenders
    message = unclassified_message(offenders)
    assert "NEW_THING.md" in message, message                       # names the offender…
    assert "Add a row" in message and "corpus" in message           # …and says what to do


def test_an_UNCLASSIFIED_NEW_TOP_LEVEL_DIRECTORY_is_rejected_BY_NAME(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "newdir").mkdir()
    offenders = unclassified(top_level_directories(tmp_path), {"src/": ("product", "…")})
    assert offenders == ["newdir/"], offenders
    assert "newdir/" in unclassified_message(offenders)


def test_the_walk_IGNORES_machine_state_so_the_guard_stays_livable(tmp_path):
    """The must-not-bite arm: a `.venv`, a `build`, a `dist`, an egg-info and a mid-build
    sdist staging directory must NOT be reported as unclassified newcomers."""
    # NB a deliberately implausible version — naming the *packaged* one would freeze it, and
    # `tests/test_version_bump_tolerance.py` reddens on exactly that (LD-316, LD-372).
    for name in (".venv", "build", "dist", "larkdocio-42.0.1", "src.egg-info", "__pycache__"):
        (tmp_path / name).mkdir()
    (tmp_path / "src").mkdir()
    assert top_level_directories(tmp_path) == ["src/"]


# =========================================================================== #
# AC7 — the guard is SEEN to redden for an entry that stops resolving           #
# =========================================================================== #

def test_a_manifest_entry_that_STOPS_RESOLVING_is_rejected_BY_NAME():
    entries = [Entry("BLOCKS.md", "file", "present", "the docx block matrix"),
               Entry("GONE.md", "file", "present", "deleted out from under the manifest"),
               Entry("requirements/DECISIONS.md", "file", "forward-referenced (LD-369)", "…")]
    offenders = unresolved(entries, lambda path: path == "BLOCKS.md")
    assert [entry.path for entry in offenders] == ["GONE.md"], offenders
    message = unresolved_message(offenders)
    assert "GONE.md" in message and "forward-referenced (LD-NNN)" in message, message


def test_a_FORWARD_REFERENCE_is_not_reported_while_it_is_still_pending():
    """The marker has to actually buy something, or the honest thing would be a stub file."""
    pending = Entry("requirements/DECISIONS.md", "file", "forward-referenced (LD-369)", "…")
    assert unresolved([pending], lambda path: False) == []


def test_an_UNMARKED_missing_entry_is_NOT_excused_by_the_marker_existing():
    plain = Entry("requirements/DECISIONS.md", "file", "present", "…")
    assert [e.path for e in unresolved([plain], lambda path: False)] == [
        "requirements/DECISIONS.md"]


# =========================================================================== #
# AC8 — the scope is one level deep, the exclusions are declared, it is fast    #
# =========================================================================== #

def test_the_walk_is_ONE_LEVEL_DEEP_and_never_descends(tmp_path):
    """A nested ``*.md`` is not a root document and a nested directory is not top-level —
    otherwise this guard would ask a human to classify several thousand files."""
    (tmp_path / "ROOT.md").write_text("#\n", encoding="utf-8")
    nested = tmp_path / "pkg" / "deep"
    nested.mkdir(parents=True)
    (nested / "NESTED.md").write_text("#\n", encoding="utf-8")
    assert root_documents(tmp_path) == ["ROOT.md"]
    assert top_level_directories(tmp_path) == ["pkg/"]


def test_every_EXCLUSION_is_DECLARED_not_incidental():
    """AC8: each excluded name carries a reason here, and — except ``.git``, which git owns
    and never ignores — is really covered by ``.gitignore``. Read as text; no git is invoked
    (``tests/test_no_test_reads_live_git.py`` forbids it, and would catch it)."""
    ignored = GITIGNORE.read_text(encoding="utf-8")
    for name, reason in EXCLUDED.items():
        assert len(reason) > 15, f"{name} is excluded without a stated reason"
        if name == ".git":
            continue
        leaf = name.rsplit("/", 1)[-1]
        assert re.search(rf"^{re.escape(leaf)}/?$", ignored, re.M), (
            f"{name} is excluded from the walk but .gitignore does not cover it — an "
            f"exclusion the repository itself does not agree with is a hole in direction 2")
    for pattern, reason in EXCLUDED_PATTERNS:
        assert len(reason) > 15, f"{pattern.pattern} is excluded without a stated reason"


def test_the_REAL_top_level_is_small_and_the_walk_is_NEGLIGIBLE():
    """State the runtime; if it is not trivially fast, the scope is wrong (AC8)."""
    start = time.perf_counter()
    for _ in range(20):
        root_documents()
        top_level_directories()
    elapsed = (time.perf_counter() - start) / 20
    assert elapsed < 0.05, f"one walk took {elapsed * 1000:.1f}ms — the scope is wrong"
    assert len(root_documents()) + len(top_level_directories()) < 60, (
        "the top level grew past what a hand-kept classification table can carry — that is a "
        "finding for the maintainer, not a bigger table")


# =========================================================================== #
# AC9 — this issue adds a guard; it moves no consumer-facing byte               #
# =========================================================================== #

def test_CORPUS_MD_ships_in_no_wheel_and_claims_no_consumer_surface():
    """``requirements/`` is dev-repo-only. If CORPUS.md ever needs to ship, that is a
    packaging decision with its own issue — not a side effect of this guard."""
    assert CORPUS_MD.relative_to(REPO_ROOT).parts[0] == "requirements"
    packaged = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "CORPUS.md" not in packaged, (
        "CORPUS.md reached pyproject.toml — the corpus manifest is a dev-repo artifact")
    assert not (REPO_ROOT / "src" / "larkdocio" / "CORPUS.md").exists()


@private_tree.register
def test_the_manifest_paths_are_REPO_RELATIVE_and_POSIX():
    """So a reader (and a regenerating agent) can join them onto the repo root and stop."""
    for entry in manifest_entries(CORPUS_MD.read_text(encoding="utf-8")):
        assert not entry.path.startswith("/"), entry
        assert "\\" not in entry.path and ".." not in entry.path, entry
        assert entry.kind in ("file", "location"), entry
        if entry.kind == "location":
            assert entry.path.endswith("/"), f"{entry.path} is a location without a slash"


@private_tree.register
def test_the_document_points_at_THIS_guard_so_the_next_editor_finds_it():
    text = CORPUS_MD.read_text(encoding="utf-8")
    assert "tests/test_corpus_manifest.py" in text, (
        "CORPUS.md must name the guard that holds it true — a matrix whose guard is invisible "
        "gets edited as prose")
    assert pathlib.Path(__file__).name == "test_corpus_manifest.py"
