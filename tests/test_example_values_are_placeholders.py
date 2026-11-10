"""LD-700 (T4, T15) — the ``--route`` and link-label examples are placeholders.

The shipped guide's ``--route`` example reads ``area/section/topic``, the release notes'
routing example ``Example Value``, and the Base url-segment probe's link label ``Example Link``.
The sweep holds the whole public tree to the private ledger's ``example_phrases`` list
(``tests/retired_particulars.py``), read at run time, so it runs here and is skipped, with its
reason, in the export. Phrases are compared word by word, so a respelling with spaces, hyphens or
another case is caught too.
"""
from pathlib import Path

from guard_kit import REPO_ROOT
import private_tree
from retired_particulars import load, phrase_hits

ROOT = Path(REPO_ROOT)


_ROOT_DOCS = ("BASE.md", "BLOCKS.md", "DRIVE.md", "LARK_SETUP.md", "PERMISSIONS.md",
              "README.md", "RELEASE_NOTES.md", "SHEETS.md", "TOOLS.md")
_SUFFIXES = {".py", ".md", ".json", ".sh", ".txt", ".toml", ".yml", ".yaml", ""}


def _public_text_files():
    for top in ("src/larkdocio", "tests", "consumers"):
        for path in sorted((ROOT / top).rglob("*")):
            if path.is_file() and path.suffix in _SUFFIXES and "__pycache__" not in path.parts:
                yield path
    for name in _ROOT_DOCS:
        yield ROOT / name


@private_tree.dev_record
def test_no_retired_example_segment_appears_anywhere_in_the_public_tree():
    phrases = load("example_phrases")
    offenders = []
    for path in _public_text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if phrase_hits(text, phrases):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert not offenders, offenders


def test_the_route_example_is_the_placeholder_tree():
    guide = (ROOT / "src" / "larkdocio" / "GUIDE.md").read_text(encoding="utf-8")
    assert "--route area/section/topic" in guide
