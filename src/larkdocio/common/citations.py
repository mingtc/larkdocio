"""larkdocio.common.citations — the ONE way this library cites a file it does not ship.

Most of the refusals and loss previews in this library carry an ``evidence`` pointer: the
recorded probe or capture that established the behaviour being described. Such a file is in the
project's source repository rather than in the installed package: the recorded API responses
under ``tests/captures/<probe>/…``, with tenant values replaced, which every clone carries,
including a clone of the public repository (the ``Source`` URL in the package metadata). Such a
citation wears :data:`SOURCE_REPO_LABEL`, **"in the source repository"**, so the reader knows the
file is not in their install but can be opened in a clone.

A citation printed bare reads, to the person holding the wheel, as a file they are supposed to
open and cannot find. So a citation of a repository path is written **once**, here: call
:func:`dev_repo` on the composed text and the label is appended; the fact stays, and the reader
learns in the same breath where the path lives::

    dev_repo("captures/a.json")      # not a repository path — returned unchanged
    dev_repo("tests/captures/ld463-date-only/captures/ld463-01-date-only-zone.json")
                                     # '…ld463-01-date-only-zone.json (in the source repository)'
    dev_repo(dev_repo("tests/captures/ld463-date-only/captures/ld463-01-date-only-zone.json"))
                                     # idempotent

**The maintainers' private records are never cited.** Evidence that exists only in the
maintainers' own working records — which the public repository does not carry — is not named
at all: the sentence states the measured fact itself and, where it matters, says the recording is
unpublished. A citation nobody can follow adds nothing the stated fact did not already carry.
:data:`DEV_REPO_LABEL` and :data:`PRIVATE_ROOTS` are kept only as the vocabulary a guard looks for
when it holds this package free of such citations.
"""
import re
from typing import Optional

#: The label that once marked a citation of the maintainers' PRIVATE record. The package no longer
#: carries any such citation; the phrase is kept, defined once, so a guard can look for it.
DEV_REPO_LABEL = "in the dev repo"

#: The label for a path the source repository carries — public and private trees alike
#: (``tests/captures/…``): not in the wheel, but in any clone. LD-699 (round 2 of the public-export
#: review, R13) split it from :data:`DEV_REPO_LABEL`, which had meant both, so that a reader can
#: tell a file they can open from one they cannot by the label alone.
SOURCE_REPO_LABEL = "in the source repository"

#: Both labels: either one says "not in the wheel"; which one says whether a clone carries it.
REPO_LABELS = (DEV_REPO_LABEL, SOURCE_REPO_LABEL)

#: The roots of the maintainers' private record, a subset of :data:`DEV_REPO_ROOTS`.
PRIVATE_ROOTS = ("dev", "progress", "requirements")

#: The repository directories whose files the wheel never carries. A path under any of them is
#: unreachable for someone holding only the installed package. The first three are the
#: maintainers' private record; ``tests/captures`` is the recorded evidence the repository carries
#: in both trees (LD-694) — not the whole of ``tests/``: a citation of a guard test module is not
#: this class and is left alone.
DEV_REPO_ROOTS = ("dev", "progress", "requirements", "tests/captures")

#: A repo-relative path under one of :data:`DEV_REPO_ROOTS`, as it appears inside prose,
#: a code span or a Markdown link.
DEV_REPO_PATH = re.compile(
    r"(?<![\w./-])(?:%s)/[\w.-]+(?:/[\w.-]+)*" % "|".join(DEV_REPO_ROOTS)
)


def dev_repo_paths(text) -> tuple:
    """Every maintainer-repo path cited in ``text``, in order of appearance."""
    if not isinstance(text, str):
        return ()
    return tuple(match.group(0) for match in DEV_REPO_PATH.finditer(text))


def cites_dev_repo(text) -> bool:
    """Whether ``text`` names a path that only the maintainer's repository carries."""
    return bool(dev_repo_paths(text))


def is_labelled(text) -> bool:
    """Whether ``text`` already wears one of :data:`REPO_LABELS`."""
    return isinstance(text, str) and any(label in text for label in REPO_LABELS)


def is_private_path(path) -> bool:
    """Whether a cited repository ``path`` is in the maintainers' private record."""
    return isinstance(path, str) and path.split("/", 1)[0] in PRIVATE_ROOTS


def label_for(text) -> Optional[str]:
    """The label ``text``'s citations earn: :data:`DEV_REPO_LABEL` when any of them is private,
    :data:`SOURCE_REPO_LABEL` when every one is in the source repository, ``None`` for none."""
    paths = dev_repo_paths(text)
    if not paths:
        return None
    return DEV_REPO_LABEL if any(is_private_path(p) for p in paths) else SOURCE_REPO_LABEL


def dev_repo(text: Optional[str]) -> Optional[str]:
    """``text`` with its label (:func:`label_for`) appended, if it cites a repository path.

    Returns the value unchanged when there is nothing to label — no path, an already-labelled
    string, or a non-string — so it is safe to wrap every evidence pointer, including the ones
    that cite a shipped file or a test module, and safe to apply twice.
    """
    if not cites_dev_repo(text) or is_labelled(text):
        return text
    return f"{text.rstrip()} ({label_for(text)})"
