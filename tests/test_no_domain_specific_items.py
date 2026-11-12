"""LD-704 AC5, LD-705, LD-707: the public tree carries nothing from a private pattern set.

`D-121` (8): larkdocio contains **no domain-specific items**. This guard keeps
the maintainers' private pattern set out of every file the public export carries, in any form a
reader could recover: in any case, assembled from string pieces or reversed
(:func:`domain_vocabulary.readable_forms`), wrapped across a line break or split by whitespace
(:func:`domain_vocabulary.flattened`), and in another script.

**Where the set lives.** In the private ledger, read by :mod:`domain_vocabulary`, never in this
file: a guard that spelled or described what it bans would publish it. So the tests below that
need the set carry ``@private_tree.dev_record``. In the public tree they are skipped with that
reason, and the tests that prove the detection mechanism on an invented stand-in still run.

**Which files.** Exactly what ``dev/public-export/export.py`` would export: its ``INCLUDE``
allow-list minus ``PRIVATE_ONLY``, with the root ``CHANGELOG.md`` read from its
``PUBLIC_OVERRIDES`` source. A regrowth is therefore caught at review time, before an export is
cut. The private repository's own planning record is not published and is not read here.
"""
import importlib.util
from pathlib import Path

import pytest

import re

from domain_vocabulary import FILE_PLANTS, FORBIDDEN, MUST_MATCH, MUST_NOT_MATCH, line_hits
from guard_kit import REPO_ROOT
import private_tree

ROOT = Path(REPO_ROOT)

_SKIP_PARTS = {".git", ".venv", "dist", "build", "__pycache__", ".pytest_cache"}


def _export_module():
    spec = importlib.util.spec_from_file_location(
        "_ld704_export", ROOT / "dev" / "public-export" / "export.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _public_files():
    """``{exported path: file to read}`` for every file the public tree carries."""
    files = {}
    if private_tree.is_public_tree(ROOT):
        for path in ROOT.rglob("*"):
            rel = path.relative_to(ROOT)
            if path.is_file() and not _SKIP_PARTS.intersection(rel.parts):
                files[rel.as_posix()] = path
        return files
    export = _export_module()
    for entry in export.INCLUDE:
        top = ROOT / entry
        candidates = top.rglob("*") if entry.endswith("/") else [top]
        for path in candidates:
            rel = path.relative_to(ROOT).as_posix()
            if (path.is_file() and not _SKIP_PARTS.intersection(path.relative_to(ROOT).parts)
                    and not path.name.endswith(".pyc") and rel not in export.PRIVATE_ONLY):
                files[rel] = path
    for target, (source, _reason) in export.PUBLIC_OVERRIDES.items():
        files[target] = ROOT / source
    return files


def _hits(files, pattern=FORBIDDEN):
    hits = []
    for rel, path in sorted(files.items()):
        if pattern.search(rel):
            hits.append(f"{rel}: (the path itself)")
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for number, line in line_hits(text, pattern):
            hits.append(f"{rel}:{number}: {line.strip()[:120]}")
    return hits


@private_tree.dev_record
def test_no_public_file_carries_the_private_pattern_set():
    files = _public_files()
    assert len(files) > 100, f"only {len(files)} public files found — the walk is broken"
    hits = _hits(files)
    assert not hits, (
        f"{len(hits)} line(s) carry the private pattern set (D-121 (8), LD-704) — state the "
        f"general fact instead:\n" + "\n".join(hits[:40]))


@private_tree.dev_record
def test_the_pattern_catches_every_shape_it_names(tmp_path):
    """Non-vacuity: each plant the private set lists is caught, each line it lists as ordinary
    is not, and each planted file is reported at the lines it names. The plants are read from
    the ledger with the pattern, so none is written here."""
    assert MUST_MATCH and MUST_NOT_MATCH and FILE_PLANTS, "the ledger lists no plants"
    for text in MUST_MATCH:
        assert FORBIDDEN.search(text), text
    for text in MUST_NOT_MATCH:
        assert not FORBIDDEN.search(text), text
    for index, (text, lines) in enumerate(FILE_PLANTS):
        planted = tmp_path / f"planted{index}.py"
        planted.write_text(text, encoding="utf-8")
        assert [int(hit.split(":", 2)[1]) for hit in _hits({planted.name: planted})] == lines, index


#: An invented stand-in pattern set: safe to publish, so the mechanism is proven here too.
_STAND_IN = re.compile(r"(?i:\bzephyrs?\b|zephyr_|quartz[ _-]?zebra|晴\s*天\s*散\s*步)|KX-(?:\\d|\d)")


@pytest.mark.parametrize("line", [
    'TERM = "ZEPHYR"',
    'TERM = "".join(("z", "e", "p", "h", "y", "r"))',
    'TERM = "zep" + "h" + "yr"',
    'TERM = "ryhpez"[::-1]',
    'LONG = " ".join(("quartz", "zebra"))',
    'LONG = "quartz_" "zebras"',
    "a zephyr_router and a Quartz-Zebra",
    "我们 喜欢 晴天 散步",
    r"re.compile(r'\bKX-\d+')",
    "a quartz\nzebra here",
    "# a quartz\n# zebra here",
    "// a quartz\n  // Zebra here",
    "a quartz\tzebra here",
    "a quartz   zebra here",
    "适合 晴天\n散步",
    "# 适合 晴天\n# 散步",
])
def test_every_readable_form_of_a_term_is_caught(line, tmp_path):
    """The mechanism, on the invented stand-in: spelled, assembled from string pieces, reversed,
    as an identifier, in another script with the characters spaced out, and wrapped across a line break
    (also behind a comment marker) or split by a tab or a run of spaces."""
    path = tmp_path / "planted.py"
    path.write_text(f"ok = 1\n{line}\n", encoding="utf-8")
    assert [hit.split(":", 2)[1] for hit in _hits({"planted.py": path}, _STAND_IN)] == ["2"], line


@pytest.mark.parametrize("line", [
    'x = ("zep", "h")', "the quartz of a zebra", "azephyrb", 'pair = ("zeph", "y")',
    "a quartz.\n# Zebra here", "quartz\n\nthe zebra",
])
def test_an_ordinary_line_is_not_caught(line, tmp_path):
    path = tmp_path / "plain.py"
    path.write_text(line + "\n", encoding="utf-8")
    assert _hits({"plain.py": path}, _STAND_IN) == [], line
