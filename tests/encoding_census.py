"""The DERIVED census of encoding-less text I/O across this repository (LD-660).

**Why this module exists.** ``Path.read_text()`` / ``Path.write_text()`` / ``open()`` with no
``encoding=`` decode and encode with the **host locale** (:func:`locale.getencoding`). On a
UTF-8 host that is UTF-8 and nothing is visible; on a cp1252/cp932/cp936 host the same call
either raises ``UnicodeDecodeError`` or — the worse outcome — silently produces mojibake, which
a guard then asserts against as if it were the file's bytes. This repository's claims are held
true by its guards, so a guard that cannot read the file it checks is a falsified claim wearing
a green tick.

**The population is derived by AST, never hand-listed.** LD-660's history is the argument: the
same population was hand-counted several times and came back a different number each time. The
one command below is the census; the guard
``tests/test_host_assumptions.py::test_no_encodingless_text_io_call_is_added`` asserts it is
**empty**, so a newly-added bare ``read_text()`` reddens the suite without anyone maintaining a
list. The sweep that emptied it was driven from this same function, so the sweep and the guard
cannot disagree about what the population is.

**What is deliberately NOT in the population.**

* ``read_bytes`` / ``write_bytes`` and any ``open(..., "rb"/"wb")`` — binary I/O is *correctly*
  encoding-less. Naming it would be a false positive, and a census with false positives gets
  suppressed rather than fixed.
* ``os.open`` (a file descriptor), ``tarfile.open`` / ``zipfile`` / ``gzip`` / ``bz2`` /
  ``lzma`` (archive and compressed streams) — none of these takes an ``encoding=`` in the sense
  this census means, so they cannot be "fixed".
* A call that splats ``**kwargs`` — the encoding may be supplied by the caller, so the call
  site is not statically decidable.
* A call whose ``mode`` is a non-literal expression — likewise not statically decidable. The
  census records these separately in :func:`undecidable_sites` so they are **visible** rather
  than silently dropped; see the guard that pins that set.
* A call that already pins the codec **positionally** — ``p.read_text("utf-8")``. See
  :data:`POSITIONAL_ENCODING_INDEX`; this repo has several dozen and they are already correct.
* A bare ``read_text(x)`` / ``write_text(x)`` that is not a ``Path`` method at all. See
  :data:`ATTRIBUTE_ONLY_FUNCTIONS`.

Both of the last two were learned by getting them wrong: the first pass of LD-660's sweep broke
**47 calls that already pin the codec positionally and 6 bare-name helpers — 53 in all**,
producing ``read_text("utf-8", encoding="utf-8")`` at the first kind and passing ``encoding=``
to a local helper at the second, one ``TypeError`` at import time each, surfacing as two
collection errors. The census is the thing that decides, so the census is where the knowledge
lives — including that split, which is :data:`LD660_MERGE_BASE_EXEMPTIONS` and is rendered by
:func:`exemption_sentence` rather than retyped (LD-671 AC4b: this paragraph and the two below
said "53 already-correct **positional** calls", summing two different exemption shapes into one
label and inventing a 54th site that does not exist).
"""

from __future__ import annotations

import ast
import pathlib
from typing import Dict, List, NamedTuple, Tuple

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: The trees the census walks. ``src`` is the shipped package, ``tests`` is the safety net,
#: ``scripts`` is the tooling every role runs. All three read this repo's own UTF-8 files.
CENSUS_TREES: Tuple[str, ...] = ("src", "tests", "scripts")

#: Names whose ``.open`` is not a text-mode file open at all — a file descriptor, an archive
#: member, or a compressed stream. Exempt because there is no ``encoding=`` to add.
NON_TEXT_OPENERS = frozenset({"os", "tarfile", "zipfile", "gzip", "bz2", "lzma", "shelve",
                              "dbm", "socket", "ssl"})

#: The calls the census is about. Each accepts ``encoding=`` and defaults it to the locale.
TEXT_IO_FUNCTIONS = frozenset({"read_text", "write_text", "open"})

#: Where a POSITIONAL ``encoding`` argument sits in each signature, per call shape. A call that
#: already passes the codec positionally — ``p.read_text("utf-8")``, of which this repo has
#: several dozen — is **already correct**, and a census that flagged it would drive a sweep into
#: producing ``read_text("utf-8", encoding="utf-8")``, i.e. a ``TypeError`` at import time. Found
#: the hard way: the first pass of LD-660's sweep did exactly that, breaking
#: 47 calls that already pin the codec positionally and 6 bare-name helpers — 53 in all.
#:
#:   ``Path.read_text(encoding, errors, newline)``            -> 0
#:   ``Path.write_text(data, encoding, errors, newline)``     -> 1
#:   ``Path.open(mode, buffering, encoding, ...)``            -> 2
#:   ``open(file, mode, buffering, encoding, ...)``           -> 3
POSITIONAL_ENCODING_INDEX = {("read_text", True): 0, ("write_text", True): 1,
                             ("open", True): 2, ("open", False): 3}

#: ``read_text`` / ``write_text`` are ``pathlib.Path`` METHODS and are only ever called as
#: attributes. A bare ``read_text(x)`` is somebody's local helper with a colliding name (this
#: repo has one, in tests/test_live_base_disposable_harness.py) and has no ``encoding=`` to add,
#: so matching it would be a false positive — and a sweep acting on it a ``TypeError``.
ATTRIBUTE_ONLY_FUNCTIONS = frozenset({"read_text", "write_text"})


#: **The measurement LD-660's sweep was sized by**, derived at the merge base of LD-660's sweep (a commit of the
#: maintainers' working repository, which the public one's history does not carry) by
#: exporting that pin with ``git archive`` and running THIS module's
#: :func:`encodingless_text_io_sites` over the export — the same code path the guard uses, not a
#: separate script and not a count taken off the sweep's own run.
#:
#: Reproduce::
#:
#:     git archive <that merge base> | tar -x -C /tmp/mb
#:     python -c "import pathlib, encoding_census as ec; \
#:                ec.REPO_ROOT = pathlib.Path('/tmp/mb'); print(ec.summary())"
#:
#: **Why it is a constant here rather than a sentence in a document.** LD-660 first shipped this
#: figure as **205 across tests/**, hand-carried from an early, BUGGY probe run — the one that
#: predated :data:`POSITIONAL_ENCODING_INDEX` and :data:`ATTRIBUTE_ONLY_FUNCTIONS`, so it counted
#: 47 calls that already pin the codec positionally and 6 bare-name helpers — 53 in all,
#: every one of them already correct —
#: and that predated the two ``src/`` fixes, so it had already lost them. Both the total and the
#: tree attribution were wrong, and the error reached a **shipped, packaged** ``CHANGELOG.md``,
#: where it was caught only because a reviewer re-derived instead of reading. A number in shipped
#: prose has to come from the instrument that measures it. So the number lives here, the prose is
#: a **projection** of it via :func:`census_sentence`, and
#: ``tests/test_host_assumptions.py`` holds both packaged copies byte-identical to that
#: projection — the CHANGELOG line can no longer disagree with the census.
LD660_MERGE_BASE_CENSUS = {"read_text": 105, "write_text": 47, "open": 2,
                           "src": 2, "tests": 152, "scripts": 0, "total": 154}

#: **The EXEMPTIONS, split by shape — LD-671 AC4b.** Derived the same way and at the same merge
#: base as :data:`LD660_MERGE_BASE_CENSUS`, by running :func:`exemption_counts` over the export::
#:
#:     git archive <that merge base> | tar -x -C /tmp/mb
#:     python -c "import pathlib, encoding_census as ec; \
#:                ec.REPO_ROOT = pathlib.Path('/tmp/mb'); print(ec.exemption_counts())"
#:
#: Re-derived at ``develop`` on 2026-09-09 and identical, which is expected: no sweep targets
#: this population.
#:
#: **Why the split needed recording at all.** Three sentences in this module said "53
#: already-correct **positional** calls". The conclusion they support is right and was measured
#: — a census without :data:`POSITIONAL_ENCODING_INDEX` and :data:`ATTRIBUTE_ONLY_FUNCTIONS`
#: drives a sweep into breaking that many call sites — but the label summed **two different
#: exemption shapes** into one, and one of the three then reconstructed the missing shape as "one
#: more", giving a 54 that never existed. The figure is measured here and the sentences quote
#: :func:`exemption_sentence` verbatim, held by ``tests/test_host_assumptions.py``; that is the
#: same arrangement that has kept :data:`LD660_MERGE_BASE_CENSUS` from drifting while this one
#: did.
LD660_MERGE_BASE_EXEMPTIONS = {"positional": 47, "bare_name": 6, "total": 53}


def summary(sites=None) -> Dict[str, int]:
    """``{function/tree: count}`` for a population — the shape :data:`LD660_MERGE_BASE_CENSUS`
    records.

    Defaults to the live tree, which is how a future sweep sizes itself with the same command
    that produced the recorded figure above.
    """
    sites = encodingless_text_io_sites() if sites is None else sites
    out = {name: 0 for name in ("read_text", "write_text", "open")}
    out.update({tree: 0 for tree in CENSUS_TREES})
    for site in sites:
        out[site.function] += 1
        out[site.path.split("/")[0]] += 1
    out["total"] = len(sites)
    return out


def census_sentence(counts=None) -> str:
    """The one rendering of a census figure that any prose may carry.

    Returned as a markdown fragment so a document quotes it **verbatim**; a guard then holds the
    document to it. Hand-typing the same numbers into a sentence is exactly what went wrong.
    """
    counts = LD660_MERGE_BASE_CENSUS if counts is None else counts
    return (f"**{counts['total']}** encoding-less text-I/O calls "
            f"(`read_text` {counts['read_text']}, `write_text` {counts['write_text']}, "
            f"text-mode `open` {counts['open']}) — "
            f"**{counts['tests']} under `tests/`, {counts['src']} in the shipped package**")


class Site(NamedTuple):
    """One encoding-less text-I/O call, addressed so a human can go and look at it."""

    path: str
    lineno: int
    end_lineno: int
    end_col_offset: int
    function: str
    source: str


def _receiver_root(node: ast.expr) -> str | None:
    """The leftmost ``Name`` of an attribute chain — ``os`` for ``os.path.open``."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _census_files() -> List[pathlib.Path]:
    """Every ``.py`` file under :data:`CENSUS_TREES`, sorted, so the walk is reproducible."""
    out: List[pathlib.Path] = []
    for tree in CENSUS_TREES:
        root = REPO_ROOT / tree
        if root.is_dir():
            out.extend(sorted(root.rglob("*.py")))
    return out


def _scan(path: pathlib.Path) -> Tuple[List[Site], List[Site], List[Site], List[Site]]:
    """``(encoding_less, undecidable, exempt_positional, exempt_bare_name)`` for one file.

    The last two used to be plain ``continue``s — correct behaviour, invisible measurement.
    They are collected now (LD-671 AC4b) so the figure three sentences in this module quote is
    a **reading of this walk**, not a number somebody carried forward from a run.
    """
    # Read UTF-8 explicitly. The census itself must not be the thing that cannot read the repo.
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    rel = str(path.relative_to(REPO_ROOT))
    flagged: List[Site] = []
    undecidable: List[Site] = []
    exempt_positional: List[Site] = []
    exempt_bare_name: List[Site] = []

    def _site(node) -> Site:
        return Site(rel, node.lineno, node.end_lineno, node.end_col_offset,
                    node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id,
                    (ast.get_source_segment(source, node) or "").split("\n")[0].strip())

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            name, is_attribute = func.attr, True
        elif isinstance(func, ast.Name):
            name, is_attribute = func.id, False
        else:
            continue
        if name not in TEXT_IO_FUNCTIONS:
            continue
        if name in ATTRIBUTE_ONLY_FUNCTIONS and not is_attribute:
            exempt_bare_name.append(_site(node))
            continue  # a local helper with a colliding name, not a Path method
        if any(kw.arg is None for kw in node.keywords):
            continue  # **kwargs splat — the caller may be supplying encoding=
        if any(kw.arg == "encoding" for kw in node.keywords):
            continue  # already pinned by keyword
        pos = POSITIONAL_ENCODING_INDEX.get((name, is_attribute))
        if pos is not None and len(node.args) > pos:
            # Not counted for a call that is not a text open at all: ``os.open(path, flags,
            # mode)`` has three positional arguments and so trips the index, but there is no
            # codec being pinned there — recording it would inflate the exemption figure with a
            # file descriptor. (The `flagged` verdict is the same either way: it is skipped.)
            if not (name == "open" and is_attribute
                    and _receiver_root(func.value) in NON_TEXT_OPENERS):
                exempt_positional.append(_site(node))
            continue  # already pinned POSITIONALLY — see POSITIONAL_ENCODING_INDEX
        site = Site(rel, node.lineno, node.end_lineno, node.end_col_offset, name,
                    (ast.get_source_segment(source, node) or "").split("\n")[0].strip())
        if name == "open":
            if is_attribute and _receiver_root(func.value) in NON_TEXT_OPENERS:
                continue  # fd / archive / compressed stream — no encoding to add
            # ``open(path, mode)`` takes mode second; ``Path.open(mode)`` takes it first.
            index = 0 if is_attribute else 1
            if len(node.args) > index:
                mode: ast.expr | None = node.args[index]
            else:
                mode = next((kw.value for kw in node.keywords if kw.arg == "mode"), None)
            if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
                if "b" in mode.value:
                    continue  # binary mode is correctly encoding-less
            elif mode is not None:
                undecidable.append(site)
                continue
        flagged.append(site)
    return flagged, undecidable, exempt_positional, exempt_bare_name


def encodingless_text_io_sites() -> Tuple[Site, ...]:
    """Every statically-decidable encoding-less text-I/O call in the census trees.

    **This is the population.** The guard asserts it is empty; the sweep that emptied it read
    its worklist from here. A number quoted anywhere in prose about this census is whatever
    ``len(encodingless_text_io_sites())`` says on the day it is asked.
    """
    out: List[Site] = []
    for path in _census_files():
        out.extend(_scan(path)[0])
    return tuple(out)


def undecidable_sites() -> Tuple[Site, ...]:
    """Text-I/O calls whose mode is a non-literal expression — recorded, not silently dropped.

    A census that quietly skips what it cannot decide is exactly the failure mode LD-660 was
    filed about, so these are surfaced and pinned by their own guard instead.
    """
    out: List[Site] = []
    for path in _census_files():
        out.extend(_scan(path)[1])
    return tuple(out)


def exempt_sites() -> Dict[str, Tuple[Site, ...]]:
    """The two ALREADY-CORRECT shapes the census deliberately does not flag, kept apart.

    ``positional`` — the codec is passed positionally (``p.read_text("utf-8")``);
    ``bare_name``  — a local helper that merely shares a ``pathlib`` method's name.

    They are different facts about different code and a sweep breaks them in different ways, so
    they are counted separately. Summing them under one label is what LD-671 AC4b was filed
    about.
    """
    positional: List[Site] = []
    bare_name: List[Site] = []
    for path in _census_files():
        _flagged, _undecidable, pos, bare = _scan(path)
        positional.extend(pos)
        bare_name.extend(bare)
    return {"positional": tuple(positional), "bare_name": tuple(bare_name)}


def exemption_counts(sites=None) -> Dict[str, int]:
    """``{shape: count}`` for :func:`exempt_sites` — the shape
    :data:`LD660_MERGE_BASE_EXEMPTIONS` records."""
    sites = exempt_sites() if sites is None else sites
    counts = {shape: len(found) for shape, found in sites.items()}
    counts["total"] = sum(counts.values())
    return counts


def exemption_sentence(counts=None) -> str:
    """The one rendering of the exemption split that any prose in this repo may carry.

    Same arrangement as :func:`census_sentence`, and for the same reason: a figure typed into a
    sentence drifts from the instrument that measured it, and a figure quoted from the
    instrument cannot. Deliberately grammar-free — a bare noun phrase — so the three sentences
    that carry it can each sit it in their own clause.
    """
    counts = LD660_MERGE_BASE_EXEMPTIONS if counts is None else counts
    return (f"{counts['positional']} calls that already pin the codec positionally and "
            f"{counts['bare_name']} bare-name helpers — {counts['total']} in all")


def census_coverage() -> Dict[str, int]:
    """What the census actually READ — its own non-vacuity, in numbers a guard can assert on.

    An instrument whose failure mode looks like success is worse than none: if the walk found
    no files, or parsed none of them, an empty population would read as a clean repo. The guard
    asserts these floors, so "the census could not check" fails **distinctly** from "the census
    checked and found nothing".
    """
    files = _census_files()
    calls = 0
    for path in files:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
                if name in TEXT_IO_FUNCTIONS or name in {"read_bytes", "write_bytes"}:
                    calls += 1
    return {"files": len(files), "text_io_calls": calls}
