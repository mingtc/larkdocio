"""larkdocio.common.citations — the ONE way this library cites a file it does not ship.

Most of the refusals and loss previews in this library carry an ``evidence`` pointer: the
recorded probe or capture that established the behaviour being described. Such a file is in
the project's repository rather than in the installed package, and there are two kinds of it,
each with its own label so the reader can tell them apart:

* **"in the source repository"** (:data:`SOURCE_REPO_LABEL`) — a file every clone carries,
  including a clone of the public repository (the ``Source`` URL in the package metadata). The
  recorded API responses most evidence cites are of this kind: ``tests/captures/<probe>/…``,
  with tenant values replaced. A reader holding a clone can open it.
* **"in the dev repo"** (:data:`DEV_REPO_LABEL`) — a file in the maintainers' private working
  repository: recordings and records under ``dev/``, ``progress/`` and ``requirements/``. The
  public repository is a one-way export of the product without them, so this is a
  **maintainer's provenance note**, not a file a reader of the public repository or the wheel
  can open.

A citation printed bare reads, to the person holding the wheel, as a file they are supposed to
open and cannot find. So a citation of a repository path is written **once**, here: call
:func:`dev_repo` on the composed text and the right label is appended (the private one if any
cited path is private); the fact stays, and the reader learns in the same breath whether the
path is something to open or a provenance note::

    dev_repo("captures/a.json")      # not a repository path — returned unchanged
    dev_repo("tests/captures/ld463-date-only/captures/ld463-01-date-only-zone.json")
                                     # '…ld463-01-date-only-zone.json (in the source repository)'
    dev_repo("dev/editions-spike/findings.md")      # '…findings.md (in the dev repo)'
    dev_repo(dev_repo("dev/editions-spike/findings.md"))   # idempotent

**What the private label does and does not promise.** Because a reader cannot follow it, every
sentence that carries one also **states the measured fact itself**, so the reader loses nothing
by not following it. Inside the working repository the citation guard still resolves every
labelled path in the shipped source and fails on one that dangles, and where a fact's evidence
was retired the sentence says so and states the fact rather than pointing at nothing.

The alternative, where a sentence reads perfectly well without the path, is simply to leave
the path out: a citation nobody can follow adds nothing that the stated fact did not already
carry. Both are correct; what is not correct is a bare, unexplained path — or one that
leads nowhere.

(LD-699 split the label in two. Until then "in the dev repo" covered both kinds, so the same
four words meant "open it in your clone" and "you cannot open this".)
"""
import re
from typing import Optional

#: The label for a path in the maintainers' PRIVATE record (``dev/``, ``progress/``,
#: ``requirements/``): a provenance note, not a file a reader of the public repository can open.
#: One phrase, never a synonym — a reader (and a guard) can predict it.
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
