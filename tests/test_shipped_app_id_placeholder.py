"""LD-678 — no real-looking Lark app id ships; the one console link carries a placeholder.

A Lark application id is ``cli_`` + 16 lowercase hex characters. The shipped source carried
exactly one — inside ``OBSERVED_DENIALS``' console ``help_url`` — where the pre-migration census
had ruled a **placeholder**: a console link works with any app id, so a placeholder loses
nothing, while a concrete id sends a reader to a console page for an app that is not theirs
(and, after the identity scrub, for one that does not exist), and is exactly what an auditor
hunting a credential flags first.

**The population is the whole ``src/larkdocio`` tree, every file, walked from the disk.** That
is a SUPERSET of what the wheel packs (the wheel is built from it via ``package-data``), which is
the safe direction for a "must never appear" guard: it can over-examine, never under-examine.
It is deliberately not read from ``dist/`` — ``front_door.built_wheel()`` is ``None`` on a fresh
clone, and a guard that skips there is the vacuity class this repository files bugs about. Nor
from git (``tests/test_no_test_reads_live_git.py`` forbids it).

**A file that cannot be decoded FAILS the guard rather than being skipped**: a scan that
silently passes over what it cannot read reports clean because it read nothing.
"""
from pathlib import Path
import re

from larkdocio import permissions as perm

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_ROOT = REPO_ROOT / "src" / "larkdocio"

#: The shape of a Lark application id. Case-insensitive on purpose: an upper-cased id is
#: still an id, and the cost of the wider net is zero while the tree carries none.
APP_ID = re.compile(r"\bcli_[0-9a-f]{16}\b", re.IGNORECASE)

#: The ruled form (AC1). Angle brackets cannot occur in a real id, so it cannot be mistaken
#: for one, and "your" says whose id belongs there.
PLACEHOLDER = "<your-app-id>"


def _scan(root):
    """``(files_read, offenders, undecodable)`` over every file under ``root``.

    ``__pycache__`` is excluded: bytecode is a build artefact of the very ``.py`` files being
    read, not a second source, and it is not text.
    """
    files_read, offenders, undecodable = [], [], []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if "__pycache__" in path.parts:
            continue
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            undecodable.append(str(path.relative_to(root)))
            continue
        files_read.append(path)
        for lineno, line in enumerate(text.splitlines(), 1):
            for hit in APP_ID.findall(line):
                offenders.append(f"{path.relative_to(root)}:{lineno}: {hit}")
    return files_read, offenders, undecodable


def test_no_real_looking_app_id_ships():
    files_read, offenders, undecodable = _scan(SHIPPED_ROOT)
    assert files_read, "no shipped file was read — the guard is inert"
    assert SHIPPED_ROOT / "permissions.py" in files_read, (
        "the walk did not reach permissions.py, the one module that ever carried an app id — "
        "the population is wrong, not clean")
    assert not undecodable, (
        f"these shipped files could not be decoded, so they were NOT scanned: {undecodable}. "
        "An unread file is not a clean file.")
    assert not offenders, (
        f"a Lark app id ships: {offenders}. A console link works with ANY app id, so use the "
        f"placeholder {PLACEHOLDER!r} — a concrete id sends the reader to an app that is not "
        "theirs (LD-678).")


def test_the_console_link_carries_the_placeholder():
    """AC1, pinned on the registry itself rather than on a line of source text."""
    links = [d.help_url for d in perm.OBSERVED_DENIALS if d.help_url is not None]
    assert links, "OBSERVED_DENIALS carries no console link — nothing here is being checked"
    for url in links:
        assert f"/app/{PLACEHOLDER}/auth" in url, (
            f"a shipped console link does not carry the placeholder: {url!r}")


def test_the_scanner_is_not_inert(tmp_path):
    """The instrument bites: a planted id is reported, and an unreadable file is REPORTED."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "clean.py").write_text(f'URL = "/app/{PLACEHOLDER}/auth"\n',
                                                encoding="utf-8")
    (tmp_path / "pkg" / "leaky.md").write_text("see /app/cli_0123456789abcdef/auth\n",
                                               encoding="utf-8")
    (tmp_path / "pkg" / "shouty.txt").write_text("CLI_0123456789ABCDEF\n", encoding="utf-8")
    (tmp_path / "pkg" / "blob.bin").write_bytes(b"\xff\xfe\x00not utf-8")
    (tmp_path / "pkg" / "__pycache__").mkdir()
    (tmp_path / "pkg" / "__pycache__" / "x.pyc").write_bytes(b"\xff cli_0123456789abcdef")

    files_read, offenders, undecodable = _scan(tmp_path)

    assert [o.split(":")[0] for o in offenders] == ["pkg/leaky.md", "pkg/shouty.txt"], offenders
    assert undecodable == ["pkg/blob.bin"], undecodable
    assert len(files_read) == 3, files_read
