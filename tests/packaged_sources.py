"""Where each packaged twin's canonical text lives — the guards' statement of the rule that
``scripts/sync-packaged-notes.sh`` applies when it writes the packaged copies (LD-691, ``D-121``
(3), maintainer ruling 2).

The wheel ships ONE changelog in both trees: the window of the project's **public** changelog.
In the public tree that is the root ``CHANGELOG.md``. In the maintainers' private copy —
identified, as :mod:`private_tree` does, by a ``dev/`` directory — the root ``CHANGELOG.md`` is the
internal engineering log, and the public changelog lives at
``dev/public-export/public/CHANGELOG.md`` (the export writes it at the root). Every other packaged
twin's source is its root file in both trees.

The script states the same rule for itself; the guards assert the packaged bytes equal the
projection of THIS path, so the two statements cannot disagree without the suite reddening.
"""
import pathlib

import private_tree

PRIVATE_PUBLIC_CHANGELOG = "dev/public-export/public/CHANGELOG.md"


def canonical(repo_root, name):
    """The file whose projection ``src/larkdocio/<name>`` must equal."""
    repo_root = pathlib.Path(repo_root)
    if name == "CHANGELOG.md" and not private_tree.is_public_tree(repo_root):
        return repo_root / PRIVATE_PUBLIC_CHANGELOG
    return repo_root / name


def source_release_count(repo_root, name):
    """How many release sections the canonical source of ``name`` carries."""
    import importlib

    guide = importlib.import_module("larkdocio.guide")
    text = canonical(repo_root, name).read_text(encoding="utf-8")
    return len(guide._bounded_sections(text, guide.NOTES_WINDOW_LEVELS[name]))


def ships_whole(repo_root, name):
    """``True`` when the packaged copy of release document ``name`` is the WHOLE source — it has
    no more sections than its window — so its banner and its refusals must not call it a window.
    The public changelog — whose first entry is the last release made before the project was
    public — is in this state until it outgrows the window (LD-691)."""
    import importlib

    guide = importlib.import_module("larkdocio.guide")
    return source_release_count(repo_root, name) <= guide.NOTES_WINDOW_SECTIONS[name]
