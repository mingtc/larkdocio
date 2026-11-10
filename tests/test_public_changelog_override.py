"""The public changelog override (LD-691, D-121 ruling 3, maintainer ruling 2) — held here, in the private
repository.

The wheel ships the PUBLIC changelog in both trees. Here the root ``CHANGELOG.md`` is the internal
engineering log and the public changelog is ``dev/public-export/public/CHANGELOG.md``;
``dev/public-export/export.py``'s ``PUBLIC_OVERRIDES`` writes it at the export's root. Every test
here reads ``dev/`` and is ``@private_tree.dev_record``: in the export the override has already
been applied, and ``tests/test_shipped_notes.py`` holds the packaged copy to its source in both
trees (``tests/packaged_sources.py``).

What these guards hold:

* the packaged ``src/larkdocio/CHANGELOG.md`` is byte-identical to the projection
  ``scripts/sync-packaged-notes.sh`` writes — the one function it calls,
  ``larkdocio.guide.packaged_projection`` — of the PUBLIC changelog, never of the internal log;
* the override table names exactly this pair, with a stated reason;
* the public log keeps the ``## [X.Y.Z] — YYYY-MM-DD`` section shape the packaged-notes tooling
  reads, and carries no issue id and no private-path citation (the reason it exists).
"""
import importlib
import importlib.util
import pathlib
import re

import private_tree
from domain_vocabulary import RETIRED_ID

REPO = pathlib.Path(__file__).resolve().parent.parent
PUBLIC = REPO / "dev" / "public-export" / "public"
PUBLIC_ROOT = PUBLIC / "CHANGELOG.md"
PUBLIC_PACKAGED = REPO / "src" / "larkdocio" / "CHANGELOG.md"
EXPORT_SCRIPT = REPO / "dev" / "public-export" / "export.py"

EXPECTED_OVERRIDES = {"CHANGELOG.md": "dev/public-export/public/CHANGELOG.md"}


def _export_module():
    spec = importlib.util.spec_from_file_location("_ld691_export", EXPORT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@private_tree.dev_record
def test_the_packaged_changelog_is_the_projection_of_the_PUBLIC_changelog():
    guide = importlib.import_module("larkdocio.guide")
    expected = guide.packaged_projection(PUBLIC_ROOT.read_text(encoding="utf-8"), "CHANGELOG.md")
    assert PUBLIC_PACKAGED.read_bytes() == expected.encode("utf-8"), (
        f"{PUBLIC_PACKAGED.relative_to(REPO)} is not the packaged projection of "
        f"{PUBLIC_ROOT.relative_to(REPO)}. Re-project it the way scripts/sync-packaged-notes.sh "
        "does: run ./scripts/sync-packaged-notes.sh — never hand-edit it."
    )


@private_tree.dev_record
def test_override_table_names_the_public_changelog_with_its_reason():
    overrides = _export_module().PUBLIC_OVERRIDES
    assert {target: source for target, (source, _reason) in overrides.items()} == EXPECTED_OVERRIDES
    for target, (source, reason) in overrides.items():
        assert (REPO / source).is_file(), f"override source for {target} is missing: {source}"
        assert reason.strip(), f"override for {target} carries no reason"


@private_tree.dev_record
def test_public_changelog_keeps_the_section_shape_and_no_private_vocabulary():
    text = PUBLIC_ROOT.read_text(encoding="utf-8")
    headings = re.findall(r"^## .*$", text, flags=re.MULTILINE)
    assert headings, "the public changelog has no release section"
    for heading in headings:
        assert re.fullmatch(r"## \[\d+\.\d+\.\d+\] — \d{4}-\d{2}-\d{2}", heading), heading
    assert not re.search(r"\b(?:LD|D)-\d+\b|" + RETIRED_ID.pattern, text), "the public changelog quotes an issue id"
    for private in ("dev/", "progress/", "requirements/", "process/", "PROJECT.md", "CLAUDE.md"):
        assert private not in text, f"the public changelog cites a private path: {private}"
