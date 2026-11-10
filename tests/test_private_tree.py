"""LD-685 — the ``private_tree`` marker and the private-read guard (tests/private_tree.py)."""
import pathlib

import pytest

import private_tree

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


class _Item:
    def __init__(self, nodeid, marks=()):
        self.nodeid = nodeid
        self._marks = {m.name: m for m in (mk.mark for mk in marks)}
        self.added = []

    def get_closest_marker(self, name):
        return self._marks.get(name)

    def add_marker(self, mark):
        self.added.append(mark.mark if hasattr(mark, "mark") else mark)


def test_the_public_tree_skips_a_private_test_WITH_ITS_REASON(tmp_path):
    item, plain = _Item("t::a", [private_tree.kit]), _Item("t::b")
    private_tree.apply([item, plain], tmp_path)  # no dev/ here: the public shape
    assert [m.kwargs["reason"] for m in item.added] == [f"private-only: {private_tree.KIT}"]
    assert plain.added == [], "an unmarked test is never skipped"


def test_the_private_tree_skips_NOTHING(tmp_path):
    (tmp_path / private_tree.PRIVATE_MARKER_DIR).mkdir()
    item = _Item("t::a", [private_tree.kit])
    private_tree.apply([item], tmp_path)
    assert item.added == [], "in the private repository a private_tree test must run"


def test_every_mark_carries_a_reason():
    for name in ("kit", "register", "process", "board", "dev_record", "citations", "walks_tree"):
        mark = getattr(private_tree, name).mark
        assert mark.kwargs.get("reason"), name


@private_tree.dev_record
def test_the_guard_FLAGS_an_undeclared_read_of_a_private_file():
    guard = private_tree.PrivateReadGuard(REPO_ROOT)
    assert guard.active, "dev/public-export/export.py must be found in this repository"
    guard.begin(_Item("t::reads_private"))
    guard.hook("open", (str(REPO_ROOT / "PROJECT.md"), "r", 0))
    guard.hook("open", (str(REPO_ROOT / "README.md"), "r", 0))          # public: not flagged
    guard.hook("open", (str(REPO_ROOT / "tests" / "conftest.py"), "r", 0))  # tests/: exempt
    assert guard.end() == ["PROJECT.md"]


@private_tree.dev_record
def test_the_guard_LETS_A_DECLARED_test_read_private_files():
    guard = private_tree.PrivateReadGuard(REPO_ROOT)
    for marks in ([private_tree.process], [private_tree.walks_tree]):
        guard.begin(_Item("t::declared", marks))
        guard.hook("open", (str(REPO_ROOT / "PROJECT.md"), "r", 0))
        assert guard.end() == []


@private_tree.dev_record
def test_the_guard_is_INSTALLED_and_ACTIVE_in_this_repository():
    assert private_tree.install(REPO_ROOT).active


def test_the_guard_is_INERT_without_the_export_script(tmp_path):
    assert not private_tree.PrivateReadGuard(tmp_path).active


@private_tree.dev_record
def test_the_marker_is_IN_USE_and_every_withheld_module_exists():
    """A marker nobody uses guards nothing; a withheld module that vanished withholds nothing."""
    tests = REPO_ROOT / "tests"
    marked = [p for p in tests.glob("test_*.py") if "@private_tree." in p.read_text(encoding="utf-8")]
    assert len(marked) >= 10, marked
    guard = private_tree.PrivateReadGuard(REPO_ROOT)
    for rel in guard.export.PRIVATE_ONLY:
        assert (REPO_ROOT / rel).is_file(), rel


@private_tree.dev_record
def test_the_guard_FLAGS_running_a_private_script_in_a_subprocess():
    """Running a script is reading it: a test that executes ``scripts/check-board.sh`` and asserts
    on its (empty, in the export) stdout would otherwise pass over nothing in the public tree."""
    guard = private_tree.PrivateReadGuard(REPO_ROOT)
    guard.begin(_Item("t::runs_private"))
    guard.hook("subprocess.Popen", ("bash", ["bash", "scripts/check-board.sh", "--bogus"],
                                    str(REPO_ROOT), None))
    guard.hook("subprocess.Popen", ("bash", ["bash", "scripts/verify.sh", "--help"],
                                    str(REPO_ROOT), None))            # exported: not flagged
    guard.hook("subprocess.Popen", (str(REPO_ROOT / "scripts" / "next-id.sh"), [], None, None))
    assert guard.end() == ["scripts/check-board.sh", "scripts/next-id.sh"]
