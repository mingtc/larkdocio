"""The ``private_tree`` marker (LD-685): a test whose subject exists only in the private repository.

larkdocio is developed in a private working repository and published as a one-way export of the
product (``D-120``). The working repository also holds the process kit (``scripts/`` beyond the
gate runner, the board, ``process/``, the role docs), the decision register (``requirements/``) and
the evidence record (``dev/``). Some tests guard those: that a script refuses a bad argument, that
the decision register is well formed, that every citation the shipped code makes into ``dev/``
still resolves. In the public tree their subject does not exist.

Such a test carries ``@private_tree.<reason>`` (one of the marks below). What that means:

* **In the private repository it always runs.** The marker changes nothing there: the skip below
  fires only when ``dev/`` is absent, and ``dev/`` is the private record.
* **In the public tree it is skipped, and says why.** The reason is printed in pytest's skip
  report, so a reader sees which guards did not run and what they guard — a skip with a stated
  reason, never a guard that silently passes over nothing.

A test that reads a recorded API response is NOT private: the response is copied, with tenant
values replaced, to ``tests/captures/`` and the test reads it there.
"""
import pytest

#: The private repository's evidence record. Its absence is what identifies the public tree.
PRIVATE_MARKER_DIR = "dev"

KIT = "runs the private process kit's scripts/ (board, release and index tooling)"
REGISTER = "reads the private decision register or corpus manifest under requirements/"
PROCESS = "reads the private process documents (PROJECT.md, CLAUDE.md, process/, .claude/)"
BOARD = "reads the private kanban board (progress/, ARCHIVE.md)"
DEV_RECORD = "reads the private evidence record under dev/"
INTERNAL_LOG = ("reads the internal engineering CHANGELOG.md, which the public export replaces "
                "with a fresh public changelog (export.py PUBLIC_OVERRIDES, LD-691)")
CITATIONS = ("checks that a citation or evidence pointer into the private record (dev/, "
             "process/, requirements/) resolves, or that a corpus spanning it is complete")
REPORTS = ("holds the private repository's rules for how a cited field report is anonymised "
           "(no report file named, no encounter dated, no verbatim quote); the public tree "
           "carries no report narrative at all, which tests/test_no_report_narrative.py holds "
           "(LD-715)")

kit = pytest.mark.private_tree(reason=KIT)
register = pytest.mark.private_tree(reason=REGISTER)
process = pytest.mark.private_tree(reason=PROCESS)
board = pytest.mark.private_tree(reason=BOARD)
dev_record = pytest.mark.private_tree(reason=DEV_RECORD)
citations = pytest.mark.private_tree(reason=CITATIONS)
internal_log = pytest.mark.private_tree(reason=INTERNAL_LOG)
reports = pytest.mark.private_tree(reason=REPORTS)


def is_public_tree(repo_root):
    return not (repo_root / PRIVATE_MARKER_DIR).is_dir()


def apply(items, repo_root):
    """Skip every ``private_tree`` item, with its reason, when running in the public tree."""
    if not is_public_tree(repo_root):
        return
    for item in items:
        closest = getattr(item, "get_closest_marker", None)  # a guard's fake item may lack it
        mark = closest("private_tree") if closest else None
        if mark is not None:
            reason = mark.kwargs.get("reason") or (mark.args[0] if mark.args else "")
            item.add_marker(pytest.mark.skip(reason=f"private-only: {reason}"))


# --------------------------------------------------------------------------------------------- #
# The write-time guard (LD-685 AC3): a test that reads a private file must say so.              #
# --------------------------------------------------------------------------------------------- #

WALKS = ("walks a corpus spanning the whole repository; in the public export it checks the "
         "public subset, which is still a real check")
walks_tree = pytest.mark.walks_tree(reason=WALKS)

#: Never "private files": local state that is not part of either tree.
_IGNORED_TOPS = {".git", ".venv", ".venv-mutation", "dist", "build", ".kanban-wt", ".pytest_cache",
                 ".env", "__pycache__"}


class PrivateReadGuard:
    """Record, per test, every file it opens that the public export does not carry.

    Active only in the private repository, and only when the export's allow-list
    (``dev/public-export/export.py``) is present to say what the export carries. A test opening
    such a file must carry ``private_tree`` (its subject is private) or ``walks_tree`` (it scans
    the whole repository and still checks the public subset). Paths under ``tests/`` are exempt:
    suite-wide scanners legitimately read the test modules the export withholds.
    """

    def __init__(self, repo_root):
        import importlib.util
        import os

        self.root = os.path.realpath(repo_root)
        self.current = None
        self.seen = set()
        self.export = None
        path = os.path.join(self.root, PRIVATE_MARKER_DIR, "public-export", "export.py")
        if os.path.isfile(path):
            spec = importlib.util.spec_from_file_location("_ld685_export", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.export = module

    @property
    def active(self):
        return self.export is not None

    def is_private(self, rel):
        top = rel.split("/", 1)[0]
        if top in _IGNORED_TOPS or rel.startswith("tests/") or "/__pycache__/" in rel:
            return False
        # The source of a PUBLIC_OVERRIDES entry IS exported, under its target's name (LD-691): the
        # public changelog kept at dev/public-export/public/CHANGELOG.md is the export's root
        # CHANGELOG.md, so a test reading it reads a file the public tree has.
        sources = {source for source, _reason in getattr(self.export, "PUBLIC_OVERRIDES", {}).values()}
        if rel in sources:
            return False
        return (not self.export.included(rel)) or rel in self.export.PRIVATE_ONLY

    def hook(self, event, args):
        """Audit hook. ``open``: the file opened. ``subprocess.Popen``: the executable and every
        argv token, resolved against the child's cwd — running a private script is a read of it
        (LD-685 QA: a test that ran ``scripts/check-board.sh`` used to pass the guard silently)."""
        if self.current is None or not args:
            return
        import os

        if event == "open":
            self._note(args[0], os.getcwd())
        elif event == "subprocess.Popen":
            executable, argv, cwd = (list(args) + [None, None, None])[:3]
            base = os.fsdecode(cwd) if isinstance(cwd, (str, bytes, os.PathLike)) else os.getcwd()
            tokens = [executable] + (list(argv) if isinstance(argv, (list, tuple)) else [argv])
            for token in tokens:
                self._note(token, base)

    def _note(self, target, base):
        import os

        if not isinstance(target, (str, bytes, os.PathLike)):
            return
        try:
            name = os.fsdecode(target)
        except (TypeError, ValueError):
            return
        if not name or "\0" in name:
            return
        full = os.path.realpath(name if os.path.isabs(name) else os.path.join(base, name))
        if full.startswith(self.root + os.sep) and os.path.isfile(full):
            rel = os.path.relpath(full, self.root).replace(os.sep, "/")
            if self.is_private(rel):
                self.seen.add(rel)

    def begin(self, item):
        exempt = (item.get_closest_marker("private_tree") or item.get_closest_marker("walks_tree")
                  or item.nodeid.split("::", 1)[0] in self.export.PRIVATE_ONLY)
        self.current = None if exempt else item.nodeid
        self.seen = set()

    def end(self):
        self.current = None
        seen, self.seen = sorted(self.seen), set()
        return seen


GUARD = None


def install(repo_root):
    """Create and register the guard once per process (an audit hook cannot be removed)."""
    import sys

    global GUARD
    if GUARD is None:
        GUARD = PrivateReadGuard(repo_root)
        if GUARD.active:
            sys.addaudithook(GUARD.hook)
    return GUARD
