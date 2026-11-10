#!/usr/bin/env bash
# KIT-CLASS: PROJECT — regenerates this project's own packaged release documents; no kit surface. See process/EXTRACTION.md.
# (Names below that the public repository lacks — PROJECT.md, CLAUDE.md, process/, requirements/,
# scripts/release.sh, scripts/finish-pr.sh — are the maintainers' process kit, kept in their
# private working repository. The script itself needs none of them.)
# sync-packaged-notes.sh — THE MATERIALISATION PATH for every in-wheel copy of a document
# whose canonical home is the repository root: CHANGELOG.md and RELEASE_NOTES.md (LD-540) and
# LARK_SETUP.md (LD-549).
#
# THE NAME SAYS "notes" AND THE SCRIPT NOW DOES MORE. Kept deliberately: this path is cited by
# scripts/release.sh, by the guard's own failure message, by pyproject.toml's package-data
# comment, by requirements/CORPUS.md and by several role documents, and a rename buys no truth
# while invalidating every one of those addresses. What it materialises is enumerated in ONE
# place, larkdocio.guide.PACKAGED_TWIN_RESOURCES, so the set is read and never re-listed here.
#
# WHY THIS EXISTS. Until LD-540 the packaged copies were byte-identical twins of the root
# files, so keeping them in sync was `cp CHANGELOG.md src/larkdocio/CHANGELOG.md` and the guard
# that held them together could name that command in its own failure message. The wheel now
# carries a recent-N WINDOW of each release document instead — the root files stay complete —
# so the copy is a PROJECTION and `cp` is the wrong answer. This is the right one, and it is
# the only writer: every projection is defined once, in larkdocio.guide.packaged_projection
# (the window for a release document, the IDENTITY for a document that does not grow a section
# per release), and this script and the guards in tests/test_shipped_notes.py and
# tests/test_packaged_lark_setup.py all call that same function.
#
# An IDENTITY projection is still a projection, not a licence to hand-copy: this script stays
# the only writer and the guard asserts byte equality against the function, so a packaged copy
# somebody edited in place reddens exactly as a stale window does.
#
# USAGE
#   ./scripts/sync-packaged-notes.sh
#       Rewrite every src/larkdocio/<name> in larkdocio.guide.PACKAGED_TWIN_RESOURCES from its
#       root file. Reports the byte count of each projection it wrote, and the release span
#       where the projection is a window.
#
#   ./scripts/sync-packaged-notes.sh --check
#       Report whether each packaged copy already equals the projection of its root file.
#       Exit 0 if every packaged copy matches, 1 if any does not. Writes nothing.
#
# IT ANNOUNCES AN EVICTION, AT THE MOMENT IT TRUNCATES (LD-621, D-111). Opening a release
# section pushes the oldest one out of the window, and until now that happened in silence: the
# span line moved by one and nothing said which section stopped shipping. A silent eviction is
# how LD-621 reached the window's edge unnoticed, so a section leaving the shipped copy is now
# NAMED — `WILL EVICT` under --check, before anything is written, and `EVICTED` in write mode.
# It is a DISCLOSURE, not an error: the truncation is the designed behaviour and the exit code
# is unchanged. What a reader does with it is D-111's rule — content published in an evicted
# section is still in the complete root document, so a guard that requires it reads the ROOT
# copy and keeps any wheel-facing arm conditional.
#
# THE CHANGELOG'S SOURCE IS THE PUBLIC CHANGELOG, IN BOTH TREES (LD-691, D-121 (3), maintainer ruling
# 2). The wheel ships one product: its CHANGELOG.md is the window of the project's PUBLIC
# changelog. In the public tree that file is the root CHANGELOG.md. In the maintainers' private
# copy (identified, as tests/private_tree.py does, by a dev/ directory) the root CHANGELOG.md is
# the internal engineering log, and the public changelog is kept at
# dev/public-export/public/CHANGELOG.md, which the export writes at the root. The same rule is
# stated for the guards in tests/packaged_sources.py; they assert byte equality against it, so a
# disagreement between the two reddens the suite.
#
# WHAT IT NEVER DOES: edit a root file, reflow a byte, decide how big a window is, or decide
# which documents have twins. The window sizes are CHANGELOG_WINDOW_SECTIONS /
# RELEASE_NOTES_WINDOW_SECTIONS in src/larkdocio/guide.py, each carrying its own derivation,
# and the membership is PACKAGED_TWIN_RESOURCES there; this script only applies them.
#
# WHEN IT HAS TO RUN: whenever one of those root documents changes — which, on a release, is
# when the new `## [X.Y.Z]` section is written. It is not a promise that someone remembers: the
# packaged copies are committed and the guards hold each to its projection, so a stale copy
# reddens `pytest` and therefore release.sh's gate [b] before any tag exists.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${SYNC_NOTES_PYTHON:-}"
if [ -z "$PY" ]; then
  if [ -x "$REPO_ROOT/.venv/bin/python" ]; then PY="$REPO_ROOT/.venv/bin/python"; else PY="python3"; fi
fi

MODE="write"
case "${1:-}" in
  --check) MODE="check" ;;
  "") ;;
  *) echo "sync-packaged-notes.sh: unknown argument '$1' — pass --check or nothing." >&2; exit 2 ;;
esac

MODE="$MODE" "$PY" - "$REPO_ROOT" <<'PYEOF'
import os
import pathlib
import sys

root = pathlib.Path(sys.argv[1])

#: The public changelog's home in the maintainers' private copy (see the header). In the public
#: tree there is no dev/ directory and the root CHANGELOG.md is the public changelog.
PRIVATE_PUBLIC_CHANGELOG = "dev/public-export/public/CHANGELOG.md"


def _canonical(resource):
    if resource == "CHANGELOG.md" and (root / "dev").is_dir():
        return root / PRIVATE_PUBLIC_CHANGELOG
    return root / resource

sys.path.insert(0, str(root / "src"))
import importlib

guide = importlib.import_module("larkdocio.guide")
mode = os.environ["MODE"]

#: What a reader must do about an eviction — printed with every announcement rather than left to
#: be looked up, because the rule is the whole reason the announcement is worth making.
_EVICTION_RULE = (
    ". They stay COMPLETE in the root document; this is the window's designed behaviour, not an "
    "error. A guard that requires content published in an evicted section reads the ROOT copy "
    "and keeps its wheel-facing arm conditional (D-111)."
)


def _versions(path, resource):
    """The release versions a materialised copy currently carries, newest first — ``[]`` when it
    does not exist yet or carries no bounded section."""
    if not path.is_file():
        return []
    rows = guide._bounded_sections(
        path.read_text(encoding="utf-8"), guide.NOTES_WINDOW_LEVELS[resource]
    )
    return [v for v in (guide._release_version(row[2]) for row in rows) if v]

drift = []
for resource in sorted(guide.PACKAGED_TWIN_RESOURCES):
    canonical = _canonical(resource)
    packaged = root / "src" / "larkdocio" / resource
    if not canonical.is_file():
        print(f"sync-packaged-notes: the canonical file is missing: {canonical}", file=sys.stderr)
        sys.exit(1)
    text = canonical.read_text(encoding="utf-8")
    projection = guide.packaged_projection(text, resource)
    encoded = projection.encode("utf-8")
    label = f"{resource}: {len(encoded)} B"
    keep = guide.NOTES_WINDOW_SECTIONS.get(resource)
    evicted = []
    if keep is None:
        # The identity projection: no window, so there is no span to report. Saying so is the
        # point — a silent row would read like a window whose span the script forgot to print.
        label += ", the WHOLE document (identity projection, no window)"
    else:
        rows = guide._bounded_sections(text, guide.NOTES_WINDOW_LEVELS[resource])
        span = [guide._release_version(row[2]) or row[1] for row in rows[:keep]]
        label += f", {len(span)} sections ({span[-1]} .. {span[0]})"
        # THE EVICTION, NAMED (LD-621 / D-111). Which sections the copy about to be replaced
        # still carries that the new projection does not — computed against the copy on disk, so
        # this fires exactly when a section stops shipping and stays quiet on every other run.
        evicted = [v for v in _versions(packaged, resource) if v not in set(span)]
    if mode == "check":
        current = packaged.read_bytes() if packaged.is_file() else None
        if current == encoded:
            print(f"  in sync   {label}")
        else:
            have = "missing" if current is None else f"{len(current)} B"
            print(f"  STALE     {label} — the packaged copy is {have}")
            drift.append(resource)
        if evicted:
            print(f"  WILL EVICT {resource}: {', '.join(evicted)} — writing the projection "
                  "removes these sections from the shipped copy" + _EVICTION_RULE)
    else:
        packaged.write_bytes(encoded)
        print(f"  wrote     {label}")
        if evicted:
            print(f"  EVICTED   {resource}: {', '.join(evicted)} — no longer in the shipped "
                  "copy" + _EVICTION_RULE)

if drift:
    print(
        "sync-packaged-notes: "
        + ", ".join(drift)
        + " — the packaged copy is not the projection of its root file. Run "
        "./scripts/sync-packaged-notes.sh (no arguments) to rewrite it.",
        file=sys.stderr,
    )
    sys.exit(1)
PYEOF
