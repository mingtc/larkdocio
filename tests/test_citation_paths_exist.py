"""LD-700 (round 3 of the public-export review, T5) — a path labelled "in the source repository"
EXISTS in the source repository.

``tests/test_citation_label_reservation.py`` holds each label to the KIND of path it names (a
private path never wears the source label). Round 3 found the other half missing: shipped
refusal strings labelled recordings "in the source repository" that the tree does not carry, so
the label promised a file a reader could not open. This module resolves every citation into
``tests/captures/`` in the same corpus (the shipped package's code, comments, docstrings and
documents, the root matrices, and ``capabilities(full=True)``), against the files present:

* a full path ``tests/captures/<dir>/…`` must exist — a trailing ``-`` makes it a file-name
  prefix, which must match at least one file;
* a prefix list after a capture directory (``…/captures/ 123-, 124-, summary-probe-08.json``) is
  expanded, and every member must match a file in that directory (a short member such as
  ``13-`` after ``ld467-12-`` keeps the previous member's stem);
* in a run that carries the source label, a bare capture prefix (``ld467-21-``) or a bare
  ``.json`` file name must match a file somewhere under ``tests/captures/`` — unless the
  "in the dev repo" label follows it closely, which says it is a maintainers' record.

LD-703 (round 5, V1) widened the shapes, because a public 1.53.0 note claimed this held while
recordings named ``P1-….json``, the bare ids ``P0`` / ``R2`` and a bare ``captures/753-, 754-``
list in shipped refusal text all escaped it:

* a probe's letter-and-number capture name (``P1-….json``, ``captures/R7-….json``) and the bare
  id after "capture(s)" (``captures P0 and R0``) resolve against every file under
  ``tests/captures/``;
* a directory-relative ``captures/NNN-`` list resolves even in unlabelled shipped text (the
  module's own docstring names the directory), and a bare name after a full ``tests/captures``
  path is read as that path's sibling;
* which label a name is under is decided by position — the first label after it, else the last
  before it — and a name under "in the dev repo", or inside a private path, is a provenance
  note and is not resolved.

LD-716 (round 12, R12-1) added the shape a matrix cell carried past all of the above: a
capture-number list after the WORD "capture(s)" (``captures 105-..108-, 303-``) under the source
label. Its ranges are expanded to every number they span, and every member must resolve in one
common directory, because a bare number such as ``109-`` exists in more than one spike.

Files exist in both trees (``tests/captures/`` is exported whole), so this runs in either.
"""
import re
from pathlib import Path

from larkdocio.common.citations import DEV_REPO_LABEL, SOURCE_REPO_LABEL
from test_citation_label_reservation import corpus

REPO = Path(__file__).resolve().parent.parent
_LABELS = re.compile("|".join(re.escape(l) for l in (DEV_REPO_LABEL, SOURCE_REPO_LABEL)), re.I)
CAPTURES = REPO / "tests" / "captures"

_FULL = re.compile(r"tests/captures/[\w./-]*[\w-]")
_MEMBER = r"(?:(?:[a-z]+\d+-)?\d+-\.\.\d+-|(?:[a-z]+\d+-)?\d+-(?![\w.])|[\w-]+\.json\b)"
_LIST_AFTER_DIR = re.compile(
    r"(tests/captures/[\w.-]+(?:/[\w.-]+)*/)\s*(" + _MEMBER
    + r"(?:(?:\s*(?:,|/|and)\s*|\s+)" + _MEMBER + r")*)")
_BARE_PREFIX = re.compile(r"(?<![\w/.-])([a-z]+\d+-\d+-)(?:\s*/\s*(\d+-))?")
#: A capture's own naming (a number, an ``ld…`` stem, ``summary-``, or a probe's letter-and-number
#: id such as ``P1-`` / ``R7-`` / ``B3-``), so a generic file name such as ``config.json`` in
#: prose is not mistaken for a citation. A directory-relative ``captures/P1-….json`` counts too
#: (LD-703, round 5 V1: the old shape required a digit or a lower-case stem and no ``/`` before
#: it, so ``captures/P1-directory-….json`` and ``R7-….json`` were never looked at).
_BARE_JSON = re.compile(
    r"(?<![\w.-])((?:[A-Z]{1,2}\d+-|\d|[a-z]+\d+-|summary-|[a-z]+-[a-z\d]+-\d)[\w-]*\.json)\b")
#: A capture directory's prefix list written bare, ``captures/753-, 754-`` / ``captures/600-
#: 601- 602-`` / ``captures/756- and 763-`` (LD-703 V1). Every member must name a recording
#: somewhere under ``tests/captures/``.
_BARE_DIR_LIST = re.compile(
    r"(?<![\w./-])captures/\s*(\d+-(?![\w.])(?:(?:\s*,\s*|\s+and\s+|\s+)\d+-(?![\w.]))*)")
#: Capture ids cited bare, ``captures P0 and R0`` / ``capture R2`` (LD-703 V1): each must be the
#: stem of a recording (``P0-….json``) somewhere under ``tests/captures/``.
_BARE_IDS = re.compile(
    r"\bcaptures?\s+([A-Z]{1,2}\d+(?:(?:\s*,\s*|\s+and\s+)[A-Z]{1,2}\d+)*)\b(?![\w-])")

#: A capture-number list after the WORD "capture(s)", ``captures 105-..108-, 303-, in the source
#: repository`` (LD-716, round 12 R12-1). No shape above read it — ``_BARE_DIR_LIST`` needs
#: ``captures/`` and ``_BARE_PREFIX`` an ``ld…`` stem — so a range overrunning what is published
#: by one member passed, and resolving each member against every directory could not have caught
#: it anyway (``109-`` exists in another spike). A list names ONE directory's recordings, so a
#: range is expanded to every number it spans and all the members must resolve in a COMMON
#: directory under ``tests/captures/``.
_NUM_MEMBER = r"(?:\d+-\.\.\d+-|\d+-)(?![\w.])"
_BARE_WORD_LIST = re.compile(
    r"\bcaptures?\s+(" + _NUM_MEMBER + r"(?:(?:\s*,\s*|\s+and\s+|\s*/\s*)" + _NUM_MEMBER + r")*)")

#: An ``ld…`` capture id after the word "capture(s)", with or without its trailing ``-``
#: (``capture ld466-02``), in text no label marks private (LD-716, round 12 R12-2: a shipped
#: comment cited an unpublished recording bare, the second round running; ``_BARE_PREFIX`` needs
#: the trailing ``-`` and the source label, so it never looked). Unlabelled, it must resolve;
#: under "in the dev repo" it is a provenance note.
_BARE_LD_CAPTURE = re.compile(r"\bcaptures?\s+([a-z]+\d+-\d+)-?(?![\w.])")

#: Roots of a full repository path: a name inside one is the full path's business — ``_FULL``
#: resolves a ``tests/captures/…`` path, and a private path is checked by the label guard.
_ROOTS = ("dev", "progress", "requirements", "process", "docs", ".claude", "tests", "src")


_ROOTED = re.compile(r"(?<![\w./-])(?:%s)/[\w./-]+" % "|".join(re.escape(r) for r in _ROOTS))


def _rooted(run, at):
    """Whether the name at ``at`` is the tail of a full repository path (``dev/…/x.json``)."""
    start = at
    while start and (run[start - 1].isalnum() or run[start - 1] in "_./-"):
        start -= 1
    head = run[start:at]
    return "/" in head and head.split("/", 1)[0] in _ROOTS


def _all_names():
    return sorted(p.name for p in CAPTURES.rglob("*") if p.is_file())


def _capture_dirs():
    """``{directory: [file names]}`` for every directory under ``tests/captures/``."""
    dirs = {}
    for p in CAPTURES.rglob("*"):
        if p.is_file():
            dirs.setdefault(p.parent, []).append(p.name)
    return dirs


def _numbers(listed):
    """The capture numbers a bare word list names, a range ``105-..108-`` expanded in full."""
    out = []
    for member in re.findall(r"\d+-\.\.\d+-|\d+-", listed):
        if ".." in member:
            low, high = (int(end.rstrip("-")) for end in member.split(".."))
            out.extend(f"{n:0{len(member.split('..')[0]) - 1}d}-" for n in range(low, high + 1))
        else:
            out.append(member)
    return out


def _member_resolves(member, names, stem=""):
    """One cited member against file names. ``a-..b-`` is a range (both ends must resolve);
    ``x-.json`` is a glob ``x-*.json`` whose ``*`` the flattening dropped."""
    if "-.." in member:
        low, high = member.split("..")
        return _member_resolves(low, names, stem) and _member_resolves(high, names, stem)
    if member.endswith("-.json"):
        member = member[:-len(".json")]
    elif member.endswith(".json"):
        return member in names
    return any(n.startswith(member) or (stem and n.startswith(stem + member)) for n in names)


def _path_resolves(path):
    if "-.." in path.rsplit("/", 1)[-1]:
        head, _, tail = path.rpartition("/")
        low, high = tail.split("..")
        return _path_resolves(f"{head}/{low}") and _path_resolves(f"{head}/{high}")
    target = REPO / path
    if target.exists():
        return True
    if path.endswith("-"):
        parent = target.parent
        return parent.is_dir() and any(p.name.startswith(target.name) for p in parent.iterdir())
    return False


def unresolved(runs_by_source):
    bad = []
    names = _all_names()
    dirs = _capture_dirs()
    for source, runs in runs_by_source.items():
        for run in runs:
            for match in _FULL.finditer(run):
                path = match.group(0)
                if path.endswith("-.json"):
                    path = path[:-len(".json")]
                if not _path_resolves(path):
                    bad.append(f"{source}: {match.group(0)}")
            for match in _LIST_AFTER_DIR.finditer(run):
                directory = REPO / match.group(1)
                here = sorted(p.name for p in directory.iterdir()) if directory.is_dir() else []
                stem = ""
                for member in re.findall(_MEMBER, match.group(2)):
                    lead = re.match(r"[a-z]+\d+-", member)
                    if lead:
                        stem = lead.group(0)
                    if not _member_resolves(member, here, stem):
                        bad.append(f"{source}: {match.group(1)}{member}")
            labels = [(m.start(), m.end(), m.group(0).lower())
                      for m in re.finditer(_LABELS, run)]

            def _governing(start, end):
                """The label a citation at ``[start, end)`` is under: the first label after it
                (``path (label)``), else the last one before it (``label: path, path``)."""
                after = [label for s_, _, label in labels if s_ >= end]
                if after:
                    return after[0]
                before = [label for _, e_, label in labels if e_ <= start]
                if before:
                    return before[-1]
                # No label at all: a bare name is read against the full path cited before it
                # (``tests/captures/x/300-….json · 301-….json``), as a reader reads it.
                paths = [m for m in _ROOTED.finditer(run, 0, start)]
                if paths and paths[-1].group(0).startswith("tests/captures/"):
                    return SOURCE_REPO_LABEL
                return None

            def _check(match, bare_dir=False):
                """Whether this citation must resolve: under the source label always; under no
                label only for a directory-relative ``captures/…`` (the shipped text's own
                module names the directory, LD-703 V1); never under the dev-repo label."""
                label = _governing(*match.span())
                if label == DEV_REPO_LABEL or _rooted(run, match.start()):
                    return False
                return label == SOURCE_REPO_LABEL or (
                    bare_dir or match.group(0).startswith("captures/")
                    or run[max(0, match.start() - 9):match.start()] == "captures/")

            for match in _BARE_PREFIX.finditer(run):
                if not _check(match):
                    continue
                prefix, short = match.groups()
                if not _member_resolves(prefix, names):
                    bad.append(f"{source}: {prefix}")
                stem = re.match(r"[a-z]+\d+-", prefix).group(0)
                if short and not _member_resolves(stem + short, names):
                    bad.append(f"{source}: {stem}{short}")
            for match in _BARE_JSON.finditer(run):
                if not _check(match):
                    continue
                if not _member_resolves(match.group(1), names):
                    bad.append(f"{source}: {match.group(1)}")
            for match in _BARE_DIR_LIST.finditer(run):
                if not _check(match, bare_dir=True):
                    continue
                for member in re.findall(r"\d+-", match.group(1)):
                    if not _member_resolves(member, names):
                        bad.append(f"{source}: captures/{member}")
            for match in _BARE_WORD_LIST.finditer(run):
                if _governing(*match.span()) != SOURCE_REPO_LABEL or _rooted(run, match.start()):
                    continue
                numbers = _numbers(match.group(1))
                if not any(all(_member_resolves(n, here) for n in numbers)
                           for here in dirs.values()):
                    missing = [n for n in numbers
                               if not any(_member_resolves(n, h) for h in dirs.values())]
                    bad.append(f"{source}: captures {match.group(1)}"
                               + (f" (missing {', '.join(missing)})" if missing
                                  else " (no one directory holds them all)"))
            for match in _BARE_LD_CAPTURE.finditer(run):
                if _governing(*match.span()) == DEV_REPO_LABEL or _rooted(run, match.start()):
                    continue
                if not _member_resolves(match.group(1) + "-", names):
                    bad.append(f"{source}: capture {match.group(1)}")
            for match in _BARE_IDS.finditer(run):
                if _governing(*match.span()) != SOURCE_REPO_LABEL:
                    continue
                for capture_id in re.findall(r"[A-Z]{1,2}\d+", match.group(1)):
                    if not _member_resolves(capture_id + "-", names):
                        bad.append(f"{source}: capture {capture_id}")
    return sorted(set(bad))


def test_the_resolver_expands_prefix_lists_and_catches_a_missing_member():
    runs = {"x": ["tests/captures/ld467-create-folder/captures/ ld467-07- and ld467-99-, "
                  "in the source repository"]}
    assert "x: tests/captures/ld467-create-folder/captures/ld467-99-" in unresolved(runs)
    assert not any("ld467-07-" in miss for miss in unresolved(runs))
    runs = {"y": ["captures ld467-07- / 13- and 999-nope.json (in the source repository)"]}
    assert unresolved(runs) == ["y: 999-nope.json"]
    runs = {"z": ["captures ld467-07- / 12- (in the source repository)"]}
    assert unresolved(runs) == ["z: ld467-12-"]


def test_every_capture_citation_in_the_shipped_corpus_resolves():
    assert unresolved(corpus()) == []


def test_LD703_the_resolver_sees_letter_ids_bare_lists_and_names_after_a_capture_path():
    """Round 5 (V1): the shapes the first resolver missed — a probe's letter-and-number capture
    (``P1-….json``, or the bare id ``P0``), a directory-relative ``captures/753-, 754-`` list in
    unlabelled shipped text, and a bare name following a full ``tests/captures`` path. A name
    under the dev-repo label, or read against a private path, is a provenance note and is not
    resolved here."""
    spike = "tests/captures/name-lookup-spike (in the source repository)"
    runs = {"a": [spike + ": captures/P99-x-READ.json and "
                  "reprobe/captures/R1-search-owner-exact-READ.json"]}
    assert unresolved(runs) == ["a: P99-x-READ.json"]
    runs = {"b": ["captures P2 and P99 under " + spike]}
    assert unresolved(runs) == ["b: capture P99"]
    runs = {"c": ["The transfer STORES (captures/756-, 999-) and is one-way (captures/600- 601-)"]}
    assert unresolved(runs) == ["c: captures/999-"]
    runs = {"d": ["captures/999- and P99-x.json (dev/permissions-spike/findings.md, "
                  "in the dev repo)"]}
    assert unresolved(runs) == []
    runs = {"e": ["tests/captures/editions-spike/captures/300-summary-leg-5-base-history.json"
                  " · 999-leg.json · subitems-z-99-nope.json"]}
    assert unresolved(runs) == ["e: 999-leg.json", "e: subitems-z-99-nope.json"]
    runs = {"f": ["dev/base-media-parity-spike/findings.md (captures 124-, summary-probe-99.json)"]}
    assert unresolved(runs) == []


def test_LD716_a_bare_capture_number_list_resolves_in_ONE_directory_with_ranges_expanded():
    """Round 12 (R12-1): ``SHEETS.md`` cited ``captures 105-..109-, 303-, 304-, in the source
    repository`` in a matrix cell; ``109-`` is not in that spike, and no shape read the list. A
    member missing everywhere, a range overrunning its directory, and a list split across two
    directories are each caught; a list one directory holds in full is not."""
    label = ", in the source repository)"
    assert unresolved({"a": ["(captures 105-..108-, 303-, 304-" + label]}) == []
    assert unresolved({"b": ["(captures 105-..109-, 303-, 304-" + label]}) == [
        "b: captures 105-..109-, 303-, 304- (no one directory holds them all)"]
    assert unresolved({"c": ["(captures 107-..109-" + label]}) == [
        "c: captures 107-..109- (no one directory holds them all)"]
    assert unresolved({"d": ["(capture 98765-" + label]}) == ["d: captures 98765- (missing 98765-)"]
    # Under the dev-repo label it is a provenance note and is not resolved here.
    assert unresolved({"e": ["(captures 98765-, in the dev repo)"]}) == []


def test_LD716_an_unlabelled_ld_capture_id_after_capture_must_resolve():
    """Round 12 (R12-2): ``capture ld466-02`` sat bare in a shipped comment, and no recording of
    that name is published. Unlabelled it must resolve; labelled private it is not resolved."""
    assert unresolved({"a": ["(capture ld466-02), so it is not a route"]}) == ["a: capture ld466-02"]
    assert unresolved({"b": ["(capture ld466-04), so it is"]}) == []
    assert unresolved({"c": ["(capture ld466-02, in the dev repo; not published)"]}) == []
