"""SHIP THE NOTES WHERE A CONSUMER CAN READ THEM — the wheel, the vendor drop, the delta.

Why this module exists
----------------------
The distribution model is *vendor a built wheel + pin a local-file requirement*, so a
consumer's **entire** view of larkdocio is the wheel plus whatever the refresh script drops
beside it. Until now that view carried **no changelog and no release notes at all** — which
is how a consumer had to reconstruct six releases of dependency and behavior changes out of
nothing. A release-notes file nobody can read from the wheel solves nothing.

Three contracts, mirroring the acceptance criteria:

* **They ship IN THE WHEEL** — asserted from the built artifact (unzip → ``RECORD``), the
  ``GUIDE.md`` precedent, plus their *content* read back out of the archive so a zero-byte or
  stale copy cannot pass. And the negative half of that: whatever mechanism packages them must
  not sweep any **other** repo-root document in as a side effect.
* **The canonical file stays at the repo root, with a committed in-package copy held
  byte-identical by a drift guard** (the packaging resolution — see § below). The guard is the
  whole mechanism, so it is proven to bite on a one-character divergence.
* **The refresh script drops both beside the vendored wheel**, and ``--check`` answers
  *"should I update?"* with *"and here is what changed"* — the release-notes section headers
  for the versions in between — while staying strictly report-only.

The packaging resolution (option (a), the recommended one)
----------------------------------------------------------
``[tool.setuptools.package-data]`` can only package files that live **inside** a package
directory, and both canonical files live at the repo root with no ``MANIFEST.in`` in the
repo. Of the three options the issue lays out, this takes **(a)**: the canonical file stays
at the repo root (the location that was ruled for it), a committed copy lives at
``src/larkdocio/<name>`` so ``package-data`` can carry it, and
:func:`notes_identity_report` reddens the moment the two diverge. No build machinery is
added (the house rule is git + bash + python only), and a guard is the mechanism this repo
already uses for every other sync problem. The sync is enforced at the one moment it matters
without anybody remembering it: ``scripts/release.sh``'s first preflight runs the suite, so a
release cut with an unsynced copy is refused before it can tag.

The updater is bash, so it is exercised the way a consumer runs it: a **local** stand-in dev
repo (``git init`` + tags, pointed at through the script's own ``LARKDOCIO_REPO_URL`` seam) and
``PYTHON=false`` so the wheel build dies right after the drops — no network, no PyPI, nothing
built. The same posture the kit harness uses for the guide drop.
"""
import importlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import zipfile

import pytest

import consumer_text
import packaged_sources
import front_door
from test_comment_anchor_claim_guard import packaged_markdown, shipped_text_surfaces

# LD-370 — CONFORMANCE-tier: the notes must actually reach the consumer's vendor drop; shipping is the promise.
# See process/doctrine/conformance-tier.md (a lens, not a gate).
pytestmark = pytest.mark.conformance

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src" / "larkdocio"
UPDATER = REPO_ROOT / "consumers" / "update_larkdocio.sh"

#: ``(canonical root file, the committed in-package copy)`` — the two release documents a
#: consumer must be able to read from the wheel. Not hand-derived twice: the packaged half is
#: read back out of ``package-data`` by :func:`test_ac1_both_notes_are_declared_as_package_data`,
#: so this pair and the declaration cannot disagree silently.
NOTES = ("CHANGELOG.md", "RELEASE_NOTES.md")


def notes_window(text, name):
    """The projection under guard, imported at CALL time so this module keeps importing even
    while the window machinery is being edited.

    **LD-549 repointed this at ``packaged_projection`` and the name was kept.** That function IS
    the window for a release document and the identity for one that has no releases to trim
    (the walkthrough), so a report over any mix of root-canonical documents asks each for its
    own projection instead of assuming every twin is windowed. The two release documents get
    byte-for-byte the same expectation as before.
    """
    return importlib.import_module("larkdocio.guide").packaged_projection(text, name)


def notes_window_sections(name):
    """The window size for ``name``, read from its one named constant — never a literal here."""
    return importlib.import_module("larkdocio.guide").NOTES_WINDOW_SECTIONS[name]


# --------------------------------------------------------------------------- #
# The drift guard (AC2) — a pure function, so it can be driven red on demand.  #
# --------------------------------------------------------------------------- #

def notes_identity_report(root=None, packaged=None, names=NOTES, project=None):
    """``[(name, reason)]`` for every release document whose packaged copy is not
    **byte-identical to the recent-N projection of** the canonical root file.

    **The subject narrowed in LD-540; the teeth did not.** Up to and including v1.37.0 the
    packaged copy was byte-identical to the *whole* root file and this function compared the two
    files directly. The wheel now carries a WINDOW — the newest
    ``larkdocio.guide.NOTES_WINDOW_SECTIONS[name]`` release sections plus the root's own preamble
    and a generated disclosure banner — because the reader the in-wheel copy exists for is
    deciding whether to re-pin, and the consumer refresh script serves them from the ROOT file
    out of a cloned tag tree, never from this one (``consumers/update_larkdocio.sh``, the
    ``$CLONE/CHANGELOG.md`` / ``$CLONE/RELEASE_NOTES.md`` reads). What is still asserted is an
    exact, byte-level equality against a **derived** expectation, and it is still the only thing
    that makes the packaged copy trustworthy:

    * **byte-level, not text-level** — for the reason it always was: a line-ending or
      trailing-newline difference must not slip through, because the packaged copy is meant to be
      the same bytes the projection produces.
    * **"identical", never "similar" / "approximately" / "regenerable on request"** — the
      expectation is computed from the root file by the one function that defines the window
      (:func:`larkdocio.guide.notes_window`), so a hand-edited packaged file, a partially
      re-synced one, and one left behind by a release all report here.
    * **and therefore a STALE WINDOW is a divergence.** When a release opens a new
      ``## [X.Y.Z]`` section in a root file, the projection of that root file changes, and a
      packaged copy that was not regenerated stops equalling it. That is what makes it impossible
      to cut a release shipping last release's window: ``scripts/release.sh``'s gate ``[b]`` runs
      ``verify.sh`` (pytest + build) *before* the tag exists, so this function reddens the gate.

    ``project`` is the projection under test, ``(text, name) -> str``; it defaults to the real
    :func:`larkdocio.guide.notes_window`, and the BITES twin below drives the real one too rather
    than a stand-in, so what is proven is the shipped rule and not a mock of it.
    """
    root = REPO_ROOT if root is None else pathlib.Path(root)
    packaged = SRC if packaged is None else pathlib.Path(packaged)
    project = notes_window if project is None else project
    report = []
    for name in names:
        # LD-691 (maintainer ruling 2): the changelog's canonical text is the PUBLIC changelog in both
        # trees, which in the private tree is not the root file — tests/packaged_sources.py.
        canonical, copy = packaged_sources.canonical(root, name), packaged / name
        if not canonical.is_file():
            report.append((name, f"the canonical file is missing: {canonical}"))
            continue
        if not copy.is_file():
            report.append((name, f"the packaged copy is missing: {copy}"))
            continue
        expected = project(canonical.read_text(encoding="utf-8"), name).encode("utf-8")
        actual = copy.read_bytes()
        if actual != expected:
            report.append((
                name,
                "the packaged copy is not byte-identical to the recent-N projection of the "
                f"root file (packaged {len(actual)} B, projection {len(expected)} B)",
            ))
    return report


def notes_claim_copies(name, marker, normalize=None):
    """``[(label, text)]`` — every copy of release document ``name`` in which a claim identified
    by the substring ``marker`` must hold. The canonical root file is always in the list; the
    packaged copy is in it when, and only when, the WINDOW still carries the release section the
    marker sits in.

    **Why this exists (LD-540), and why it is not a weakening.** Until v1.37.0 the packaged copy
    was the whole root file, so "this claim ships" and "this claim is written down" were the same
    sentence and a dozen guards asserted a marker against both copies with one literal. The wheel
    now carries a recent-N window, so a claim written into 1.28.0 stops shipping the moment 1.28.0
    rolls off the back — through no edit, and with the repository's own copy unchanged. Asserting
    the marker against the packaged copy unconditionally would redden on a correct tree; dropping
    the packaged copy from the assertion would let a claim disappear from the wheel unnoticed,
    which is the failure this round keeps finding. So neither:

    * **the ROOT copy is asserted unconditionally.** A claim deleted from the authoring source
      reddens here, with the full force it always had — this function raises if ``marker`` is
      absent from the root, rather than returning a shorter list.
    * **the PACKAGED copy is asserted whenever the window carries it**, and when it does not, this
      function PROVES that is the window's doing: the section holding the marker in the root must
      be older than the oldest release the packaged copy carries. A marker missing from the
      packaged copy while its section is still inside the window is a defect and reddens here.

    So a caller loops over whatever comes back and asserts its claim on each, and the number of
    copies is derived from the window rather than from a number anyone maintains.

    ``normalize`` is the caller's own text folding — e.g. whitespace collapse — applied only to
    decide PRESENCE. Markdown wraps, so a sentence a caller cares about legitimately spans a line
    break; the copies handed back are always the raw bytes the caller then asserts over in its own
    terms.
    """
    guide_module = importlib.import_module("larkdocio.guide")
    fold = (lambda text: text) if normalize is None else normalize
    marker_folded = fold(marker)
    root_text = (REPO_ROOT / name).read_text(encoding="utf-8")
    packaged_text = (SRC / name).read_text(encoding="utf-8")
    if marker_folded not in fold(root_text):
        raise AssertionError(
            f"{name} (the canonical root copy) does not carry {marker!r} at all — the claim was "
            f"deleted from its authoring source, which no window explains"
        )
    copies = [(f"{name} (root)", root_text)]
    if marker_folded in fold(packaged_text):
        copies.append((f"src/larkdocio/{name} (the packaged window)", packaged_text))
        return copies

    levels = guide_module.NOTES_WINDOW_LEVELS[name]
    rows = guide_module._bounded_sections(root_text, levels)
    holding = next(
        (row for row in rows if marker_folded in fold(root_text[row[3]:row[4]])), None
    )
    assert holding is not None, (
        f"{name}: {marker!r} is in the root file but in no release section of it — so its "
        f"absence from the packaged copy cannot be explained by the window"
    )
    held_in = guide_module._release_version(holding[2])
    packaged_rows = guide_module._bounded_sections(packaged_text, levels)
    carried = [
        v for v in (guide_module._release_version(row[2]) for row in packaged_rows) if v
    ]
    oldest = min(carried, key=guide_module._version_tuple)
    assert held_in is not None and guide_module._version_tuple(
        held_in
    ) < guide_module._version_tuple(oldest), (
        f"{name}: {marker!r} is missing from the packaged copy but its section ({held_in}) is "
        f"INSIDE the window ({oldest} and newer) — the shipped copy lost a live claim, which the "
        f"window does not explain. Regenerate with {_SYNC_COMMAND}."
    )
    return copies


_SYNC_COMMAND = "./scripts/sync-packaged-notes.sh"


def _sync_hint():
    return _SYNC_COMMAND


def test_ac2_the_packaged_copies_are_byte_identical_to_the_canonical_root_files():
    """AC2: the drift guard that makes option (a) honest. The root file is canonical; the
    in-package copy exists only so ``package-data`` can carry it into the wheel.

    **LD-540 narrowed what "the copy" means** — it is now the recent-N projection of the root
    file rather than the whole of it, because the wheel ships a window and the repository keeps
    the history. The guard's own claim did not weaken: it is still an exact byte comparison
    against a derived expectation, and it is now ALSO the stale-window guard (see
    :func:`notes_identity_report`). The fix is one command, and the message names it."""
    report = notes_identity_report()
    assert not report, (
        "a packaged release document is not the projection of its canonical root file — the "
        "root file is the one to edit, then regenerate the packaged copy:\n    "
        + _sync_hint()
        + "\n  "
        + "\n  ".join(f"{name}: {reason}" for name, reason in report)
    )


def _synthetic_root(directory, name, versions):
    """A miniature release document with ``versions`` sections, newest first — enough structure
    for the real projection to run on, written under ``tmp_path`` so no real file is touched."""
    body = ["# Notes", "", "A preamble sentence that the projection keeps verbatim.", ""]
    for index, version in enumerate(versions):
        body += [f"## [{version}] — 2026-08-{20 - index:02d}", "", f"- entry for {version}.", ""]
    (directory / name).write_text("\n".join(body) + "\n", encoding="utf-8")


def test_ac2_the_identity_guard_BITES_on_a_one_character_divergence(tmp_path):
    """AC2 (red-then-green, over the SAME function that guards, and over the REAL projection):
    one changed character in one copy reddens; the projection's own bytes green it; a missing
    copy reddens too.

    **LD-540 re-based this on the real window.** It used to write the same one-line text into
    both directories, which was a faithful fixture while the copy was the whole file. Now the
    expectation is computed, so the fixture writes a multi-section root document and lets
    :func:`larkdocio.guide.notes_window` produce the packaged side — the guard is proven on the
    rule that actually ships, not on a stand-in for it.
    """
    root, packaged = tmp_path / "root", tmp_path / "pkg"
    root.mkdir(), packaged.mkdir()
    versions = ["1.20.%d" % n for n in range(9, -1, -1)]
    for name in NOTES:
        _synthetic_root(root, name, versions)
        text = (root / name).read_text(encoding="utf-8")
        (packaged / name).write_text(notes_window(text, name), encoding="utf-8")
    assert notes_identity_report(root, packaged) == []

    # the projection really is a WINDOW of this fixture, or the arms below prove nothing.
    projected = (packaged / "CHANGELOG.md").read_text(encoding="utf-8")
    assert projected.count("\n## [") == notes_window_sections("CHANGELOG.md") < len(versions)

    # one character, in one file → RED, and it names the file that diverged.
    (packaged / "CHANGELOG.md").write_text(projected + " ", encoding="utf-8")
    report = notes_identity_report(root, packaged)
    assert [name for name, _ in report] == ["CHANGELOG.md"]

    # a whitespace-only divergence is still a divergence (byte-level, not text-level).
    (packaged / "CHANGELOG.md").write_text(projected + "\n", encoding="utf-8")
    assert [name for name, _ in notes_identity_report(root, packaged)] == ["CHANGELOG.md"]

    # a missing packaged copy → RED (the failure mode of forgetting the copy entirely).
    (packaged / "CHANGELOG.md").unlink()
    (packaged / "RELEASE_NOTES.md").unlink()
    assert sorted(name for name, _ in notes_identity_report(root, packaged)) == sorted(NOTES)


def test_ac2_a_STALE_WINDOW_left_behind_by_a_release_reddens(tmp_path):
    """LD-540 — **the guard the window makes necessary, and the one AC4 asks for.** The window
    moves on every release: opening a new ``## [X.Y.Z]`` section at the top of a root file drops
    the oldest one out of the projection. A packaged copy that was correct for the previous
    release is therefore WRONG the moment the next section is written, and nothing else in the
    suite would notice — the packaged file is well-formed, tiles, indexes and reads fine; it is
    simply last release's window.

    Planted here as the exact shape it polices: project, then open a new newest section in the
    root and leave the packaged copy alone. Both documents must report, and the reason must name
    the projection rather than merely saying "different", because the person reading the failure
    needs to know to regenerate rather than to hand-edit.

    Driven entirely under ``tmp_path`` — no real file is touched, so this proves the negative
    without a working-tree side effect.
    """
    root, packaged = tmp_path / "root", tmp_path / "pkg"
    root.mkdir(), packaged.mkdir()
    versions = ["1.20.%d" % n for n in range(9, -1, -1)]
    for name in NOTES:
        _synthetic_root(root, name, versions)
        (root / name).read_text(encoding="utf-8")
        (packaged / name).write_text(
            notes_window((root / name).read_text(encoding="utf-8"), name), encoding="utf-8"
        )
    assert notes_identity_report(root, packaged) == [], "the fixture must start in sync"

    # The next release is cut: a new newest section is written into each ROOT file only.
    for name in NOTES:
        _synthetic_root(root, name, ["1.21.0"] + versions)

    report = notes_identity_report(root, packaged)
    assert sorted(name for name, _ in report) == sorted(NOTES), (
        f"a window left behind by a release did not redden: {report}"
    )
    for _name, reason in report:
        assert "projection" in reason, (
            f"the failure does not say the copy is not the PROJECTION, so the reader cannot "
            f"tell regenerate-me from hand-edit-me: {reason!r}"
        )


def test_ac2_the_window_is_defined_in_exactly_ONE_place():
    """LD-540 — the anti-second-copy claim, asserted rather than promised. The number of sections
    the wheel carries is named once per document in ``src/larkdocio/guide.py``, and every other
    reader of it — this guard, the materialisation script, the shipped banner, the out-of-window
    refusal — goes through :data:`larkdocio.guide.NOTES_WINDOW_SECTIONS`. A second hand-kept
    copy of N is the failure mode this test exists to make impossible to add quietly.
    """
    guide_module = importlib.import_module("larkdocio.guide")

    assert set(guide_module.NOTES_WINDOW_SECTIONS) == set(NOTES)
    assert guide_module.NOTES_WINDOW_SECTIONS["CHANGELOG.md"] is (
        guide_module.CHANGELOG_WINDOW_SECTIONS
    )
    assert guide_module.NOTES_WINDOW_SECTIONS["RELEASE_NOTES.md"] is (
        guide_module.RELEASE_NOTES_WINDOW_SECTIONS
    )
    # The two constants are SEPARATE names carrying separate derivations, even at equal value:
    # the documents are not mirrors and a shared constant would hide the day they diverge.
    source = (SRC / "guide.py").read_text(encoding="utf-8")
    assert source.count("CHANGELOG_WINDOW_SECTIONS = ") == 1
    assert source.count("RELEASE_NOTES_WINDOW_SECTIONS = ") == 1
    # and nothing outside guide.py writes a window size down.
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        if path.name == "guide.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert "WINDOW_SECTIONS = " not in text, f"{path} states a window size of its own"


# --------------------------------------------------------------------------- #
# AC1 — both files ship IN THE WHEEL, asserted from the built artifact.        #
# --------------------------------------------------------------------------- #

def test_ac1_both_notes_are_declared_as_package_data():
    """AC1 (fast, always-on): the mechanism that lands them in the wheel — the
    ``larkdocio`` package-data list carries both, read out of ``pyproject.toml``."""
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    declared = re.search(r"^larkdocio\s*=\s*\[([^\]]*)\]", text, re.MULTILINE)
    assert declared, "pyproject has no [tool.setuptools.package-data] larkdocio entry"
    for name in NOTES:
        assert name in declared.group(1), (
            f"pyproject [tool.setuptools.package-data] larkdocio must list {name} — "
            "otherwise it does not reach the wheel and a consumer cannot read it"
        )


def _built_wheel_record(tmp_path=None):
    """The pristine-inputs wheel — **one per test RUN**, shared by all five consumers.

    LD-355: the caching moved to ``front_door.run_shared_artifact``, so the build happens
    once per RUN instead of once per PROCESS (the default ``--dist load`` scatters a
    module's tests across workers, so the old module-level cache was re-armed by every
    worker that received one of the five modules' tests). ``tmp_path`` is accepted and
    ignored — the artifact no longer belongs to any one test's temp dir — and kept so the
    five call sites read unchanged.
    """
    return front_door.pristine_wheel()


def build_pristine_wheel(outdir):
    """Build a wheel from a **pristine copy** of the packaging inputs, into ``outdir``.

    **LD-221 carve-out — this is the one site NOT repointed at**
    ``front_door.packaging_artifacts()``, and the reason is the whole paragraph below:
    that seam builds in ``REPO_ROOT``, where both local artifacts named here are present,
    so taking its wheel would silently retire the residue-immunity this guard exists for —
    a **narrowing**, which LD-221 AC-A3 forbids. What LD-221 did instead: the invocation
    goes through ``front_door.run_build`` (the single build site) and the result is cached,
    so the tests that read it share ONE build. LD-355 widened that cache from per-PROCESS to
    per-RUN (``front_door.run_shared_artifact``) — same artifact, same assertions below,
    built once for the whole ``-n auto`` run instead of once per worker.

    Not built in the repo root, and not from a naive copy of it either — **two** local
    artifacts can make an in-wheel assertion pass over a declaration that is no longer there,
    and both were observed while probing this guard (removing the documents from
    ``package-data`` still produced a wheel containing them, twice, for two different
    reasons):

    * ``build/lib/`` — ``setuptools`` stages package data there and only ever *adds*, so a
      document packaged once keeps being copied into every later wheel built in that tree; and
    * ``src/*.egg-info/SOURCES.txt`` — the editable install leaves a **cached manifest**, and
      ``setuptools`` reads it as one, so every path it lists is packaged regardless of the
      current declaration.

    Excluding both makes the artifact a function of the committed inputs and nothing else.
    The shipped wheel is never at risk from either — the refresh script builds in a fresh
    clone that has neither — but a *guard* that can pass on local residue is not a guard.
    """
    try:
        import build  # noqa: F401
    except Exception:
        pytest.skip("the 'build' module is unavailable in this environment")

    pristine = outdir / "pristine"
    pristine.mkdir()
    shutil.copytree(
        REPO_ROOT / "src", pristine / "src",
        ignore=shutil.ignore_patterns("*.egg-info", "__pycache__", "build", "dist"),
    )
    for name in ("pyproject.toml", "README.md", *NOTES):
        shutil.copy(REPO_ROOT / name, pristine / name)
    assert not (pristine / "build").exists()
    assert not list(pristine.rglob("*.egg-info")), (
        "the pristine copy still carries an egg-info manifest, which would package files the "
        "declaration no longer names"
    )

    proc = front_door.run_build(cwd=pristine, outdir=outdir, wheel_only=True)
    if proc.returncode != 0:
        pytest.skip(f"wheel build could not run here:\n{proc.stderr[-800:]}")
    wheels = list(outdir.glob("larkdocio-*.whl"))
    assert wheels, "python -m build produced no larkdocio wheel"
    return wheels[0]


def test_ac1_both_notes_ship_in_the_wheel_RECORD_with_their_content(tmp_path):
    """AC1 (the binding proof — the artifact, not the declaration): build the wheel, assert both
    files are in its ``RECORD``, and read their **content back out of the archive** so a zero-byte
    or stale copy cannot pass. The bytes must equal the **projection** of the canonical root file.

    **LD-540 narrowed what "the bytes" are.** They used to be the whole root file; the wheel now
    carries a recent-N window, so the expectation is computed by the one function that defines the
    window rather than read off a second file. The teeth are unchanged and the subject is still the
    real archive member: a zero-byte copy, a truncated-by-accident copy, a hand-edited copy and a
    copy left behind by a release all fail here, and this is the arm that proves it in the ARTIFACT
    rather than in the tree."""
    wheel = _built_wheel_record(tmp_path)
    with zipfile.ZipFile(wheel) as archive:
        record = next((n for n in archive.namelist() if n.endswith("/RECORD")), None)
        assert record, "the built wheel has no RECORD"
        record_text = archive.read(record).decode("utf-8")
        for name in NOTES:
            member = f"larkdocio/{name}"
            assert member in record_text, (
                f"{member} is not in the wheel RECORD — it did not ship, so a consumer "
                "reading only the wheel still cannot see what changed"
            )
            shipped = archive.read(member).decode("utf-8")
            assert "## [" in shipped, f"{member} shipped without a single release section"
            assert re.search(r"^## \[\d+\.\d+\.\d+\] — \d{4}-\d{2}-\d{2}", shipped, re.M), (
                f"{member} shipped without a '## [X.Y.Z] — date' section header"
            )
            expected = notes_window(
                packaged_sources.canonical(REPO_ROOT, name).read_text(encoding="utf-8"), name
            )
            assert shipped == expected, (
                f"the {member} inside the wheel is not the projection of the canonical root "
                f"file (wheel {len(shipped)} chars, projection {len(expected)} chars)"
            )
            # The window is a WINDOW inside the artifact too, not merely in the tree: the
            # narrowing is what this issue shipped, so the built wheel has to show it.
            # TRANSFORMED by LD-691, not deleted: a source with no more sections than the window
            # (the public changelog, which starts at the last release made before the project was
            # public) ships whole, and
            # its banner must then say so instead of claiming a window.
            source_sections = packaged_sources.canonical(REPO_ROOT, name).read_text(
                encoding="utf-8").count("\n## [")
            want = min(notes_window_sections(name), source_sections)
            assert shipped.count("\n## [") == want, (
                f"{member} shipped {shipped.count(chr(10) + '## [')} release sections, not the "
                f"{want} its window and its source declare"
            )
            disclosure = ("carries a WINDOW of the newest" if source_sections > want
                          else "carries every release this document records")
            assert disclosure in shipped, (
                f"{member} shipped without its own window disclosure — a reader who opens it "
                "would have no way to know how much of the history it holds"
            )
        # the consumer-facing notes must ship WITH the criteria that make them readable
        notes = archive.read("larkdocio/RELEASE_NOTES.md").decode("utf-8")
        assert "INCLUDE" in notes and "EXCLUDE" in notes, (
            "the packaged release notes lost the relevance criteria stated in their header"
        )


def test_ac1_no_OTHER_repo_root_document_is_swept_into_the_wheel(tmp_path):
    """The amplifier's side-effect check: the packaging mechanism must carry **exactly** the
    documents it claims. A glob that swept the repo root in would be a real regression — the
    process docs, the board, and the internal matrices are not for consumers."""
    wheel = _built_wheel_record(tmp_path)
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    top_level_md = sorted(
        n.split("/", 1)[1] for n in names
        if n.startswith("larkdocio/") and n.count("/") == 1 and n.endswith(".md")
    )
    # LD-549 added LARK_SETUP.md — the Lark-application walkthrough — as the THIRD root-canonical
    # document with a materialised in-package copy. The pin is widened, deliberately, and NOT
    # replaced by a derivation: the whole value of this list is that a packaging change has to be
    # typed here by a human who then owns the sentence "a consumer should receive this".
    assert top_level_md == [
        "CHANGELOG.md", "GUIDE.md", "LARK_SETUP.md", "RELEASE_NOTES.md",
    ], f"the wheel's top-level packaged Markdown set changed: {top_level_md}"
    # The side-effect arm's exclusion set is the DECLARED twin set, read from the one place it is
    # enumerated (``larkdocio.guide.PACKAGED_TWIN_RESOURCES``) — so a root document packaged on
    # purpose leaves this arm through the front door, while one swept in by a glob still trips it.
    twins = set(importlib.import_module("larkdocio.guide").PACKAGED_TWIN_RESOURCES)
    root_docs = {p.name for p in REPO_ROOT.glob("*.md")} - twins
    for doc in sorted(root_docs):
        assert f"larkdocio/{doc}" not in names, (
            f"the wheel picked up the repo-root {doc} as a side effect of the packaging "
            "mechanism — package-data must name the declared root-canonical documents "
            f"({sorted(twins)}) and nothing else"
        )
    assert not [n for n in names if not n.startswith(("larkdocio/", "larkdocio-"))], (
        "the wheel carries a member outside the package and its dist-info"
    )


# --------------------------------------------------------------------------- #
# AC3 — the package-data-derived guards auto-enrol them. VERIFY, don't assume.  #
# --------------------------------------------------------------------------- #

def test_ac3_the_comment_claim_guards_package_data_parse_enrols_both_notes():
    """AC3: ``packaged_markdown()`` claims in its own docstring that *"packaging a new doc
    widens this guard without anyone remembering to"*. A docstring is a claim — this is the
    check. Both packaged copies must appear, keyed by their repo-relative path."""
    enrolled = packaged_markdown()
    for name in NOTES:
        label = f"src/larkdocio/{name}"
        assert label in enrolled, (
            f"{label} is packaged but the package-data-derived corpus did not pick it up: "
            f"{sorted(enrolled)}"
        )


def test_ac3_the_enrolled_notes_reach_the_shipped_text_corpus_that_greps_them():
    """AC3, one layer out: enrolment is only worth citing if the corpus the guards actually
    grep contains the text. It does — and that is the observed behavior, not an assumption."""
    corpus = shipped_text_surfaces()
    for name in NOTES:
        label = f"src/larkdocio/{name}"
        assert label in corpus and corpus[label].strip(), (
            f"{label} is enrolled but its text is not in the guard's corpus"
        )


def test_ac3_the_front_door_packaged_path_set_also_widens():
    """AC3, the second package-data-derived mechanism (the front-door citation labeller):
    it derives its packaged set the same way, so it widens too."""
    packaged = front_door.packaged_doc_paths()
    for name in NOTES:
        assert f"src/larkdocio/{name}" in packaged


# --------------------------------------------------------------------------- #
# The updater — a LOCAL stand-in dev repo, no network, nothing built.          #
# --------------------------------------------------------------------------- #

_CHANGELOG_FIXTURE = """\
# Changelog

## [1.20.0] — 2026-07-29

### Added
- CHANGELOG-MARKER

## [1.19.0] — 2026-07-28

### Added
- older

## [1.13.0] — 2026-07-27

### Added
- a release from before the notes began
"""

_NOTES_FIXTURE = """\
# Release notes

NOTES-MARKER — what changed that affects you.

## [1.20.0] — 2026-07-29

### New capabilities

- a thing you can call.

### Behavior changes you can observe

None.

### Upgrade & compatibility

- no dependency moved.

### Known limitations

None.

## [1.19.0] — 2026-07-28

### New capabilities

None.

### Behavior changes you can observe

- output moved.

### Upgrade & compatibility

None.

### Known limitations

None.
"""


def _git(*args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)


def _require_git():
    if shutil.which("git") is None:  # pragma: no cover - environment guard
        pytest.skip("git is unavailable — the updater cannot be exercised here")


def _seed_dev_repo(path, commits):
    """A local stand-in for the larkdocio dev repo: ``[(tag, {relpath: text})]``, committed
    and tagged in order. Pointed at through the script's ``LARKDOCIO_REPO_URL`` seam, so
    nothing touches the network."""
    _require_git()
    path.mkdir(parents=True, exist_ok=True)
    _git("init", "-q", ".", cwd=path)
    _git("config", "user.email", "test@sandbox.local", cwd=path)
    _git("config", "user.name", "Sandbox Test", cwd=path)
    _git("config", "commit.gpgsign", "false", cwd=path)
    for tag, files in commits:
        for rel, text in files.items():
            target = path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        _git("add", "-A", cwd=path)
        _git("commit", "-q", "-m", f"seed {tag}", cwd=path)
        _git("tag", tag, cwd=path)
    return path


def _run_updater(consumer, repo, *args, python="false"):
    """Run the real updater from ``consumer`` against the local ``repo``.

    ``PYTHON=false`` makes the wheel build die immediately **after** the doc drops (the kit
    harness's own posture for the guide drop), so the drops are proven with no venv, no PyPI
    and no network."""
    env = dict(os.environ, LARKDOCIO_REPO_URL=str(repo), PYTHON=python)
    return subprocess.run(
        ["bash", str(UPDATER), *args], cwd=str(consumer),
        capture_output=True, text=True, env=env,
    )


#: A stand-in interpreter whose "build" emits the one wheel the tag asks for (``WHEEL_VERSION``).
#: LD-694 F12: the four documents are vendored WITH the wheel, after the build and the version
#: check, so the drop arms below need a build that succeeds. They used to run with
#: ``PYTHON=false`` and read the documents a dying build had already left in ``./vendor/`` —
#: which was the defect itself (a refusal said "./vendor/ is untouched" after writing to it).
_BUILDING_PYTHON = """#!/usr/bin/env bash
case "${2:-}" in
  venv) mkdir -p "$3/bin"; cp "$0" "$3/bin/python"; printf '#!/bin/sh\\nexit 0\\n' > "$3/bin/pip"
        chmod +x "$3/bin/python" "$3/bin/pip" ;;
  build) while [ $# -gt 0 ]; do [ "$1" = "--outdir" ] && out="$2"; shift; done
         mkdir -p "$out"; : > "$out/larkdocio-${WHEEL_VERSION}-py3-none-any.whl" ;;
  *) exit 1 ;;
esac
"""


def _run_building_updater(tmp_path, consumer, repo, tag):
    """:func:`_run_updater` with a build that succeeds and produces ``tag``'s own wheel."""
    stub = tmp_path / "building-python"
    stub.write_text(_BUILDING_PYTHON, encoding="utf-8")
    stub.chmod(0o755)
    env = dict(os.environ, LARKDOCIO_REPO_URL=str(repo), PYTHON=str(stub),
               WHEEL_VERSION=tag.lstrip("v"), LARKDOCIO_NO_DIST="1")
    proc = subprocess.run(["bash", str(UPDATER), tag], cwd=str(consumer),
                          capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stderr[-800:]
    return proc


@pytest.fixture()
def consumer(tmp_path):
    path = tmp_path / "consumer"
    (path / "vendor").mkdir(parents=True)
    return path


def _vendored(consumer, version):
    (consumer / "vendor" / f"larkdocio-{version}-py3-none-any.whl").write_bytes(b"")


# --------------------------------------------------------------------------- #
# AC4 — the updater drops both beside the vendored wheel.                      #
# --------------------------------------------------------------------------- #

def test_ac4_build_mode_drops_both_documents_beside_the_vendored_wheel(tmp_path, consumer):
    """AC4: sourced from the CHECKED-OUT TAG's own tree (the guide-drop shape), so the drop is
    the same bytes that tag's wheel packages. It is STAGED before the build and lands in
    ``./vendor/`` with the wheel, after the version check (LD-694 F12)."""
    repo = _seed_dev_repo(tmp_path / "devrepo", [
        ("v1.20.0", {"CHANGELOG.md": _CHANGELOG_FIXTURE, "RELEASE_NOTES.md": _NOTES_FIXTURE}),
    ])
    proc = _run_building_updater(tmp_path, consumer, repo, "v1.20.0")

    changelog = consumer / "vendor" / "larkdocio-CHANGELOG.md"
    notes = consumer / "vendor" / "larkdocio-RELEASE_NOTES.md"
    assert changelog.is_file(), f"no changelog drop: {proc.stderr[-600:]}"
    assert notes.is_file(), f"no release-notes drop: {proc.stderr[-600:]}"
    assert "CHANGELOG-MARKER" in changelog.read_text(encoding="utf-8")
    assert "NOTES-MARKER" in notes.read_text(encoding="utf-8")
    assert changelog.read_text(encoding="utf-8") == _CHANGELOG_FIXTURE
    assert notes.read_text(encoding="utf-8") == _NOTES_FIXTURE


def test_ac4_a_tag_without_release_notes_logs_a_clear_skip_and_keeps_going(tmp_path, consumer):
    """AC4: an older tag genuinely carries no release notes, so the skip path is the NORMAL
    case for a while — a logged note, never an error, and the changelog drop still happens."""
    repo = _seed_dev_repo(tmp_path / "devrepo", [
        ("v1.13.0", {"CHANGELOG.md": _CHANGELOG_FIXTURE}),
    ])
    proc = _run_building_updater(tmp_path, consumer, repo, "v1.13.0")

    assert (consumer / "vendor" / "larkdocio-CHANGELOG.md").is_file(), (
        "the changelog drop must not be skipped just because the notes are absent"
    )
    assert not (consumer / "vendor" / "larkdocio-RELEASE_NOTES.md").exists()
    assert "carries no RELEASE_NOTES.md" in proc.stderr, (
        f"no clear skip note for a tag without release notes:\n{proc.stderr[-800:]}"
    )
    assert "skipping" in proc.stderr
    # and it kept going: the build step (PYTHON=false) is what stopped the run, not the drop.
    assert "Building the wheel" in proc.stderr


def test_ac4_a_tag_without_a_changelog_logs_its_own_distinct_skip(tmp_path, consumer):
    """AC4: two documents, two distinct notes — a reader must be able to tell which one the
    tag is missing (the release-gate arms' own distinct-message discipline)."""
    repo = _seed_dev_repo(tmp_path / "devrepo", [
        ("v1.20.0", {"RELEASE_NOTES.md": _NOTES_FIXTURE}),
    ])
    proc = _run_building_updater(tmp_path, consumer, repo, "v1.20.0")
    assert "carries no CHANGELOG.md" in proc.stderr
    assert (consumer / "vendor" / "larkdocio-RELEASE_NOTES.md").is_file()


# --------------------------------------------------------------------------- #
# AC5 — --check prints the version delta's release-notes section headers.       #
# --------------------------------------------------------------------------- #

_SPAN_REPO = [
    ("v1.13.0", {"CHANGELOG.md": _CHANGELOG_FIXTURE}),
    ("v1.19.0", {"CHANGELOG.md": _CHANGELOG_FIXTURE, "RELEASE_NOTES.md": _NOTES_FIXTURE}),
    ("v1.20.0", {"CHANGELOG.md": _CHANGELOG_FIXTURE, "RELEASE_NOTES.md": _NOTES_FIXTURE}),
]


def _delta_block(stderr):
    """The what-changed report's own lines, from its title through its closing pointer."""
    lines = stderr.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("What changed")), None)
    assert start is not None, f"no what-changed report in:\n{stderr[-1500:]}"
    end = next(i for i, line in enumerate(lines[start:], start) if "full text:" in line)
    return lines[start:end + 1]


def test_ac5_multi_version_delta_prints_every_intervening_header(tmp_path, consumer):
    """AC5: vendored 1.18.0 → latest 1.20.0 prints BOTH intervening headers, newest first,
    verbatim as ``## [X.Y.Z] — date`` so the output is stable and greppable.

    Asserted as the WHOLE rendered block, not with substring probes: the ordering, the
    indentation, and — the part a substring check cannot see — the fact that a subsection with
    nothing to report contributes **no line at all**. In the fixture, *Known limitations* is
    empty in both releases and *New capabilities* is empty in one, so a printer that stopped
    filtering would show up here as extra lines rather than slipping through."""
    repo = _seed_dev_repo(tmp_path / "devrepo", _SPAN_REPO)
    _vendored(consumer, "1.18.0")
    proc = _run_updater(consumer, repo, "--check")

    assert proc.returncode == 0, proc.stderr[-800:]
    assert _delta_block(proc.stderr) == [
        "What changed between 1.18.0 and 1.20.0:",
        "  ## [1.20.0] — 2026-07-29",
        "    - New capabilities",
        "    - Upgrade & compatibility",
        "  ## [1.19.0] — 2026-07-28",
        "    - Behavior changes you can observe",
        "  (full text: ./vendor/larkdocio-RELEASE_NOTES.md, refreshed when you update)",
    ]
    report = proc.stderr
    assert "Known limitations" not in report, (
        "a subsection with nothing to report must contribute no line at all — four fixed "
        "titles per release would bury the ones that matter"
    )
    assert "None." not in report
    assert "a thing you can call" not in report, "bodies must not be dumped into the report"


def test_ac5_one_version_delta_prints_exactly_that_header(tmp_path, consumer):
    repo = _seed_dev_repo(tmp_path / "devrepo", _SPAN_REPO)
    _vendored(consumer, "1.19.0")
    proc = _run_updater(consumer, repo, "--check")
    assert proc.returncode == 0
    assert "## [1.20.0] — 2026-07-29" in proc.stderr
    assert "## [1.19.0]" not in proc.stderr, (
        "the vendored version's own section is not part of the delta (the span is exclusive "
        "of what you already have)"
    )


def test_ac5_an_already_current_vendored_copy_prints_no_delta(tmp_path, consumer):
    """AC5: nothing to print — and, because there is nothing to print, nothing is cloned
    either. The steady state of the advisory nag must stay one lightweight remote query."""
    repo = _seed_dev_repo(tmp_path / "devrepo", _SPAN_REPO)
    _vendored(consumer, "1.20.0")
    proc = _run_updater(consumer, repo, "--check")
    assert proc.returncode == 0
    assert proc.stdout.strip() == (
        "UP TO DATE: vendored larkdocio 1.20.0 matches the latest tag."
    )
    assert "## [" not in proc.stderr
    assert "Cloning" not in proc.stderr and "clone" not in proc.stderr.lower()


def test_ac5_a_version_in_the_span_with_no_notes_section_gets_a_clear_note(tmp_path, consumer):
    """AC5: the un-noted-release path — a version documented in the changelog but not in the
    notes must produce a **clear note, not a crash** and not silence."""
    repo = _seed_dev_repo(tmp_path / "devrepo", _SPAN_REPO)
    _vendored(consumer, "1.12.0")
    proc = _run_updater(consumer, repo, "--check")
    assert proc.returncode == 0
    assert "## [1.20.0] — 2026-07-29" in proc.stderr
    assert "1.13.0" in proc.stderr and "no release-notes section" in proc.stderr, (
        f"no clear note for the un-noted release in the span:\n{proc.stderr[-1200:]}"
    )


def test_ac5_a_latest_tag_carrying_no_notes_at_all_is_a_note_not_a_crash(tmp_path, consumer):
    repo = _seed_dev_repo(tmp_path / "devrepo", [
        ("v1.13.0", {"CHANGELOG.md": _CHANGELOG_FIXTURE}),
    ])
    _vendored(consumer, "1.12.0")
    proc = _run_updater(consumer, repo, "--check")
    assert proc.returncode == 0
    assert "carries no RELEASE_NOTES.md" in proc.stderr
    assert "UPDATE AVAILABLE" in proc.stdout


def test_ac5_no_vendored_wheel_yet_reports_the_verdict_without_a_delta(tmp_path, consumer):
    """There is no lower bound to a span when nothing is vendored, so the delta would be
    unbounded — the verdict alone, and no clone."""
    repo = _seed_dev_repo(tmp_path / "devrepo", _SPAN_REPO)
    proc = _run_updater(consumer, repo, "--check")
    assert proc.returncode == 0
    assert "no larkdocio wheel vendored yet" in proc.stdout
    assert "## [" not in proc.stderr


def test_ac5_the_delta_can_be_turned_off_for_the_advisory_nag_path(tmp_path, consumer):
    """The nag hook fires on every ``git pull`` and its own documentation promises **one
    lightweight remote query**. So the delta — which needs the notes file, and therefore a
    throwaway clone — is skippable through a documented environment seam, and the shipped hook
    uses it. The human running ``--check`` in a terminal still gets the delta."""
    repo = _seed_dev_repo(tmp_path / "devrepo", _SPAN_REPO)
    _vendored(consumer, "1.18.0")
    env = dict(os.environ, LARKDOCIO_REPO_URL=str(repo), PYTHON="false",
               LARKDOCIO_CHECK_NOTES="0")
    proc = subprocess.run(["bash", str(UPDATER), "--check"], cwd=str(consumer),
                          capture_output=True, text=True, env=env)
    assert proc.returncode == 0
    assert "UPDATE AVAILABLE" in proc.stdout
    assert "## [" not in proc.stderr


# --------------------------------------------------------------------------- #
# AC6 — --check stays report-only.                                             #
# --------------------------------------------------------------------------- #

def _tree_snapshot(root):
    return {
        str(p.relative_to(root)): (p.stat().st_mode, p.read_bytes())
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def test_ac6_check_leaves_the_consumer_tree_byte_for_byte_untouched(tmp_path, consumer):
    """AC6: snapshot before, snapshot after, assert equality — including the ``vendor/``
    directory entries. ``--check`` is the one mode a consumer runs casually."""
    repo = _seed_dev_repo(tmp_path / "devrepo", _SPAN_REPO)
    _vendored(consumer, "1.18.0")
    (consumer / "requirements.txt").write_text("larkdocio @ file:./vendor/x.whl\n", encoding="utf-8")

    before = _tree_snapshot(consumer)
    before_dirs = sorted(str(p.relative_to(consumer)) for p in consumer.rglob("*"))
    proc = _run_updater(consumer, repo, "--check")
    assert proc.returncode == 0
    assert _tree_snapshot(consumer) == before
    assert sorted(str(p.relative_to(consumer)) for p in consumer.rglob("*")) == before_dirs


def test_ac6_check_does_not_mutate_the_dev_repo_it_reads(tmp_path, consumer):
    """AC6: and it must not mutate the source either — the report reads a THROWAWAY clone, so
    the dev repo's own checkout and refs are untouched."""
    repo = _seed_dev_repo(tmp_path / "devrepo", _SPAN_REPO)
    _vendored(consumer, "1.18.0")
    before = _git("rev-parse", "HEAD", cwd=repo).stdout, _git("status", "--porcelain",
                                                             cwd=repo).stdout
    _run_updater(consumer, repo, "--check")
    after = _git("rev-parse", "HEAD", cwd=repo).stdout, _git("status", "--porcelain",
                                                            cwd=repo).stdout
    assert before == after


def test_ac6_the_stdout_verdict_contract_is_unchanged(tmp_path, consumer):
    """AC6 (the exit-code and output contract): the machine-readable answer stays **exactly
    one line on stdout** — an installed advisory hook matches on it, and a consumer may grep
    it. The delta is narration and goes to stderr, like every other narrated line here."""
    repo = _seed_dev_repo(tmp_path / "devrepo", _SPAN_REPO)
    _vendored(consumer, "1.18.0")
    proc = _run_updater(consumer, repo, "--check")
    assert proc.returncode == 0
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"--check's stdout is no longer one verdict line: {lines}"
    assert lines[0].startswith("UPDATE AVAILABLE: vendored 1.18.0 < latest 1.20.0.")
    assert "## [" not in proc.stdout


def test_ac6_the_installed_nag_hook_still_matches_the_verdict_it_greps(tmp_path, consumer):
    """AC6, end to end through the artifact that consumes ``--check``: the shipped hook body
    matches ``UPDATE AVAILABLE*`` against the captured stdout. Run the real hook against the
    real script and assert it still recognises the verdict and still exits 0."""
    repo = _seed_dev_repo(tmp_path / "devrepo", _SPAN_REPO)
    _vendored(consumer, "1.18.0")
    scripts = consumer / "scripts"
    scripts.mkdir()
    shutil.copy(UPDATER, scripts / "update_larkdocio.sh")
    (scripts / "update_larkdocio.sh").chmod(0o755)
    hook = REPO_ROOT / "consumers" / "hooks" / "post-merge"
    env = dict(os.environ, LARKDOCIO_REPO_URL=str(repo), PYTHON="false")
    proc = subprocess.run(["bash", str(hook)], cwd=str(consumer),
                          capture_output=True, text=True, env=env)
    assert proc.returncode == 0
    assert "[larkdocio] UPDATE AVAILABLE" in proc.stdout
    assert "Update is DELIBERATE and manual" in proc.stdout


# --------------------------------------------------------------------------- #
# The install recipe is EXECUTED, in a repo whose ``core.hooksPath`` is set.    #
# --------------------------------------------------------------------------- #
# Prose is not evidence that a recipe works, and this one silently did not: git
# reads hooks ONLY from the directory ``core.hooksPath`` names once it is set, so
# a hook copied into ``.git/hooks`` is never called — no warning, no error, exit
# 0. Measured on git 2.51.0: same repo, same hook file, the config the only
# difference; the merge completes and says nothing. And this nag is quiet on
# success by design, so a consumer cannot tell "not wired" from "up to date".
#
# So the recipe is not read here, it is RUN — extracted from the shipped
# template's own Install header and executed against a sandbox consumer repo
# that has ``core.hooksPath`` set, with a real merge as the observable.

#: A command line inside the hook template's Install header — the block a consumer copies.
#: Indentation is the marker: narration sits at ``# ``, commands at ``#     ``.
_RECIPE_COMMAND = re.compile(r"#     (\S.*?)\s*$")


def install_recipe_commands(text):
    """The commands the hook template's own Install header tells a consumer to run."""
    commands, inside = [], False
    for line in text.splitlines():
        if line.startswith("# \u2500\u2500 Install"):
            inside = True
            continue
        if inside and re.match(r"^# \u2500{3,}", line):
            break
        if inside:
            match = _RECIPE_COMMAND.fullmatch(line)
            if match:
                commands.append(match.group(1))
    return commands


def _sandbox_consumer_repo(path, hooks_dir):
    """A throwaway consumer repo with ``core.hooksPath`` set and two branches to merge.

    Never the live checkout: every call names ``cwd=path``, the identity and hooks config are
    the sandbox's own, and the trunk plus a side branch are created here so a merge can be run.
    """
    _require_git()
    (path / "scripts").mkdir(parents=True, exist_ok=True)
    _git("init", "-q", "-b", "main", ".", cwd=path)
    for key, value in (("user.email", "test@sandbox.local"), ("user.name", "Sandbox Test"),
                       ("commit.gpgsign", "false"), ("core.hooksPath", hooks_dir)):
        _git("config", key, value, cwd=path)
    (path / hooks_dir).mkdir(parents=True, exist_ok=True)
    (path / "trunk.txt").write_text("trunk\n", encoding="utf-8")
    _git("add", "-A", cwd=path)
    _git("commit", "-q", "-m", "trunk", cwd=path)
    _git("switch", "-q", "-c", "side", cwd=path)
    (path / "side.txt").write_text("side\n", encoding="utf-8")
    _git("add", "-A", cwd=path)
    _git("commit", "-q", "-m", "side", cwd=path)
    _git("switch", "-q", "main", cwd=path)


def test_the_shipped_install_recipe_wires_a_hook_that_FIRES_under_core_hooksPath(tmp_path):
    """Run the shipped recipe verbatim in a repo with ``core.hooksPath`` set; merge; observe.

    The assertion is the consumer's own observable — the nag line in the output of a real
    ``git merge`` — so a recipe that installs into a directory git has been configured not to
    read fails here instead of failing silently in every repo that adopted this project's kit.
    """
    hook_src = REPO_ROOT / "consumers" / "hooks" / "post-merge"
    recipe = install_recipe_commands(hook_src.read_text(encoding="utf-8"))
    assert recipe, "the hook template's Install header carries no runnable command lines"

    consumer = tmp_path / "consumer"
    _sandbox_consumer_repo(consumer, "githooks")
    if "not a git command" in _git("hook", "run", "post-merge", cwd=consumer).stderr:
        pytest.skip("this git predates `git hook run`, which the recipe's verify step uses")

    shutil.copy(hook_src, consumer / "scripts" / "larkdocio-post-merge.hook")
    stub = consumer / "scripts" / "update_larkdocio.sh"
    stub.write_text("#!/bin/sh\necho 'UP TO DATE: vendored 9.9.9 is the latest tag.'\n",
                    encoding="utf-8")
    stub.chmod(0o755)

    ran = subprocess.run(["bash", "-e", "-c", "\n".join(recipe)], cwd=str(consumer),
                         capture_output=True, text=True)
    assert ran.returncode == 0, f"the shipped recipe failed:\n{ran.stdout}\n{ran.stderr}"

    merged = _git("merge", "side", cwd=consumer)
    assert merged.returncode == 0, merged.stderr
    # Both streams: git forwards a hook's own stdout to its stderr, and what the assertion is
    # about is whether the CONSUMER sees the line, not which descriptor carried it.
    seen = merged.stdout + merged.stderr
    assert "[larkdocio] UP TO DATE" in seen, (
        "the hook the shipped recipe installed did NOT fire on a real merge in a repo whose "
        "core.hooksPath is set — which is exactly the silent failure this recipe had: git "
        f"reads hooks from {(consumer / 'githooks')}, and the recipe put one somewhere else.\n"
        f"recipe run: {recipe}\nmerge output: {seen!r}")


# --------------------------------------------------------------------------- #
# AC7 — the updater's own docs match what it now drops.                        #
# --------------------------------------------------------------------------- #

def _updater_text():
    return UPDATER.read_text(encoding="utf-8")


def test_ac7_the_updater_header_block_lists_every_vendor_drop():
    """AC7: the header comment block is what a consumer reads before running it. It must name
    every artifact that lands in ``vendor/`` — the wheel, the guide, and now both release
    documents."""
    header = "\n".join(
        line for line in _updater_text().splitlines()[:70] if line.startswith("#")
    )
    for expected in ("larkdocio-GUIDE.md", "larkdocio-CHANGELOG.md",
                     "larkdocio-RELEASE_NOTES.md", ".whl"):
        assert expected in header, (
            f"the updater's header block does not list {expected} among what lands in vendor/"
        )


def test_ac7_the_consumer_facing_docs_name_the_two_new_drops():
    """AC7: the two documents that tell a consumer what a refresh leaves behind — the
    onboarding page and the shipped guide — must both name the new drops."""
    for path in (REPO_ROOT / "consumers" / "README.md", SRC / "GUIDE.md"):
        text = path.read_text(encoding="utf-8")
        for expected in ("larkdocio-CHANGELOG.md", "larkdocio-RELEASE_NOTES.md"):
            assert expected in text, f"{path.name} does not mention the {expected} drop"


def test_ac7_the_nag_hook_documents_the_seam_that_keeps_it_lightweight():
    """AC7: the hook's header promises one lightweight remote query. It now opts out of the
    delta to keep that true, so the promise and the mechanism must both be visible there."""
    text = (REPO_ROOT / "consumers" / "hooks" / "post-merge").read_text(encoding="utf-8")
    assert "LARKDOCIO_CHECK_NOTES" in text, (
        "the hook must opt out of the release-notes delta (and say so) so a git pull still "
        "costs one lightweight remote query"
    )


# --------------------------------------------------------------------------- #
# AC8 — every consumer-facing string the updater emits is dialect-free.        #
# --------------------------------------------------------------------------- #

#: A line that EMITS text to a consumer. A ``#`` comment is deliberately out of scope, the
#: same boundary the shipped-text corpus draws: a comment is read by a maintainer standing in
#: this repo, where an issue id resolves.
_EMITTING_LINE = re.compile(r"^\s*(?:log|echo|die)\s+[\"']")


def _logical_lines(text):
    """``[(first lineno, logical line)]`` with backslash-continuations **joined**.

    Load-bearing, not tidiness. A long message is wrapped as ``log "…first half" \\`` +
    ``"…second half"``, so a line-by-line scan reads the continuation as a line that emits
    nothing and walks past whatever it says — the exact shape in which a second false claim
    once hid from a bug report in this repo. One message is one line here.
    """
    out, pending, start = [], "", None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if start is None:
            start = lineno
        line = raw.strip()
        if line.endswith("\\"):
            pending += line[:-1].rstrip() + " "
            continue
        out.append((start, (pending + line).strip()))
        pending, start = "", None
    if pending:
        out.append((start, pending.strip()))
    return out


def updater_emitted_strings(text=None):
    """``{label: line}`` for every logical line of the updater that emits text to a consumer."""
    text = _updater_text() if text is None else text
    return {
        f"update_larkdocio.sh:{lineno}": line
        for lineno, line in _logical_lines(text)
        if _EMITTING_LINE.match(line)
    }


def test_the_updaters_printed_reinstall_hint_is_a_refresh_and_says_no_deps():
    """LD-343: every install hint the updater PRINTS is a **refresh** of an existing consumer
    venv — the deps are already there, and the one thing that moved is the local wheel. So the
    hint must carry ``--no-deps``: ``--force-reinstall`` applies to the whole resolution, and
    without it a refresh goes back to the index for ``lark-oapi``, ``click``, ``python-dotenv``,
    ``markdown-it-py`` and their closure — slow, network-bound where the distribution model says
    it needs no host beyond PyPI, and able to pull a *different* transitive version into a venv
    that was working.

    Scoped deliberately to what the **updater** emits. The first-install hints
    (``consumers/README.md``, ``consumers/setup-consumer.sh``) install into a possibly-bare venv
    and must keep dependency resolution — ``--no-deps`` there ships an ``ImportError`` as the
    first consumer experience. Reuses this module's own extractor rather than a second copy.
    """
    hints = {
        label: line
        for label, line in updater_emitted_strings().items()
        if "pip install" in line
    }
    assert hints, "the updater no longer prints an install hint — did the extractor break?"
    missing = [
        f"{label}: {line}"
        for label, line in hints.items()
        if "--force-reinstall" in line and "--no-deps" not in line
    ]
    assert not missing, (
        "a printed refresh hint re-resolves every transitive dependency; add --no-deps:\n  "
        + "\n  ".join(missing)
    )
    # …and the two sites say the same sentence, so they cannot drift apart.
    bodies = {line.split("pip install", 1)[1].split("'", 1)[0] for line in hints.values()}
    assert len(bodies) == 1, f"the two printed hints have drifted apart: {bodies}"


def test_ac8_every_emitted_updater_string_is_dialect_free():
    """AC8: the log lines and the ``--check`` report are consumer-facing text, so they are
    held to the same rule as everything the wheel carries — no issue id, no requirement id, no
    internal label. Uses the shipped pattern set, not a second copy of it."""
    hits = []
    for label, line in updater_emitted_strings().items():
        for name, matched in consumer_text.dialect_hits(line):
            hits.append(f"{label}: {name} → {matched!r} in {line}")
    assert not hits, (
        "the updater emits internal dialect to a consumer (say what changed, not which "
        "issue changed it):\n  " + "\n  ".join(hits)
    )


def test_ac8_the_emitted_string_scan_BITES_and_is_scoped_to_emitting_lines():
    """AC8, red-then-green over the same extractor: dialect in an emitted line is caught, the
    same dialect in a ``#`` comment is deliberately not, and a non-emitting line is not
    mistaken for output."""
    sample = (
        '# LD-165 explains why this exists\n'
        'log "NOTE: skipping the drop (pre-LD-128 tag)."\n'
        'CLONE="$WORK/repo"   # LD-999\n'
    )
    emitted = updater_emitted_strings(sample)
    assert list(emitted) == ["update_larkdocio.sh:2"]
    assert consumer_text.dialect_hits(next(iter(emitted.values())))
    assert not consumer_text.dialect_hits(
        'log "NOTE: this tag is older than the shipped consumer guide."'
    )


def test_ac8_the_scan_reads_a_WRAPPED_message_as_one_line():
    """AC8, the shape that hides: a message split with a trailing ``\\`` puts its second half
    on a line that emits nothing, so a line-by-line scan walks past whatever it says. Both
    halves must be scanned — proven by putting the dialect in the CONTINUATION."""
    wrapped = (
        'log "NOTE: this tag predates the notes — skipping the drop" \\\n'
        '    "(see LD-149 for the reason)."\n'
    )
    emitted = updater_emitted_strings(wrapped)
    assert list(emitted) == ["update_larkdocio.sh:1"], (
        "a wrapped message must be reported as ONE logical line at its opening line number"
    )
    hits = consumer_text.dialect_hits(next(iter(emitted.values())))
    assert [matched for _name, matched in hits] == ["LD-149"], (
        "the continuation half of a wrapped message was not scanned"
    )
    # …and the real script's wrapped messages are clean when read that way.
    assert any("\\" not in line and "skipping the release-notes drop" in line
               for line in updater_emitted_strings().values()), (
        "the wrapped release-notes skip note is not being joined into one logical line"
    )


def test_ac8_the_shipped_notes_are_documents_not_code():
    """AC8: what this surface adds under ``src/larkdocio`` is **documents** — the two packaged
    notes copies — and neither is code that could change behavior.

    **Rescoped from a branch diff to a standing property.** The original form of this test ran
    ``git diff develop...HEAD -- src/`` and failed on any touched file that was not ``.md``.
    That asserted a property of **one branch** (the notes branch, which legitimately shipped no
    code) rather than a property of the repository, so on every later code branch it reddened
    for a change it was never about — a guard that cries wolf, which is how guards get
    weakened until they guard nothing. The standing claim it was really making is the one
    below, and the load-bearing half of it — that each packaged copy is **byte-identical** to the
    projection of its canonical root file (LD-540 narrowed the subject; the equality is still
    exact) — is asserted by this module's own drift guard, so the notes still cannot rot or
    diverge. Delegated here rather than re-spelled, so there is one statement of the rule.
    """
    for name in NOTES:
        packaged = SRC / name
        assert packaged.suffix == ".md", f"{name} is not a document"
        assert packaged.is_file(), f"the packaged copy of {name} is missing"
    assert notes_identity_report() == []


# --------------------------------------------------------------------------- #
# LD-621 / D-111 — THE EVICTION IS ANNOUNCED, at the moment it truncates.      #
# --------------------------------------------------------------------------- #
#
# The window rolling is designed, but until now it was SILENT: opening a release section pushed
# the oldest one out of the shipped copy and the only trace was a span line moving by one. That
# silence is how LD-621 reached the window's edge with a wheel-facing guard still resting on the
# section at it. The writer now NAMES the sections a run removes — and the proof below drives the
# real script, because a disclosure nobody has seen printed is a hope.
#
# The script derives its own REPO_ROOT from its location, so a copy of it inside a staged tree
# targets that tree and never this one. In the staged tree the four materialised documents are
# real copies (they are what gets written and mutated) and every other package member is a
# SYMLINK — so staging costs no megabytes and the real ``src/`` is only ever read.

_SYNC_SCRIPT = REPO_ROOT / "scripts" / "sync-packaged-notes.sh"


def _staged_tree(tmp_path):
    guide_module = importlib.import_module("larkdocio.guide")
    twins = set(guide_module.PACKAGED_TWIN_RESOURCES)
    (tmp_path / "scripts").mkdir()
    shutil.copy2(_SYNC_SCRIPT, tmp_path / "scripts" / _SYNC_SCRIPT.name)
    package = tmp_path / "src" / "larkdocio"
    package.mkdir(parents=True)
    for entry in SRC.iterdir():
        if entry.name in twins:
            shutil.copy2(entry, package / entry.name)
        else:
            (package / entry.name).symlink_to(entry)
    for name in twins:
        # The staged tree has no dev/, so it is public-shaped: its root CHANGELOG.md must be the
        # PUBLIC changelog the packaged copy is projected from (LD-691, tests/packaged_sources.py).
        shutil.copy2(packaged_sources.canonical(REPO_ROOT, name), tmp_path / name)
    return tmp_path


def _run_sync(tree, *args, expect=0):
    """``expect`` is asserted rather than ignored: ``--check`` on a stale tree exits 1 BY DESIGN
    (that is the gate release.sh leans on), and an eviction announcement must not disturb it —
    the disclosure rides the existing exit code, it does not invent one."""
    result = subprocess.run(
        [str(tree / "scripts" / _SYNC_SCRIPT.name), *args],
        capture_output=True, text=True, cwd=str(tree), check=False,
        env={**os.environ, "SYNC_NOTES_PYTHON": sys.executable},
    )
    assert result.returncode == expect, (
        f"exit {result.returncode}, expected {expect}\n" + result.stdout + result.stderr)
    return result.stdout


def test_ld621_a_run_that_evicts_NOTHING_says_nothing_about_eviction(tmp_path):
    """The quiet half, and it is the half that makes the loud half worth reading: on a tree
    already in sync the writer is idempotent and announces no eviction. A banner printed on
    every run is a banner nobody reads."""
    tree = _staged_tree(tmp_path)
    for args in ((), ("--check",)):
        stdout = _run_sync(tree, *args)
        assert "EVICT" not in stdout, stdout


@pytest.mark.parametrize("name", ["RELEASE_NOTES.md", "CHANGELOG.md"])
def test_ld621_the_section_a_new_release_pushes_out_of_the_window_is_NAMED(tmp_path, name):
    """The disclosure LD-621's AC5 commissions, driven end to end: a section is opened in the
    staged root document, and the writer names the release that stops shipping — under
    ``--check`` before a byte is written, and again as it writes.

    The expected version is DERIVED from the copy on disk (the oldest release it carries), never
    typed: a literal here would be a photograph of today's window and would redden at the next
    cut for no reason — which is the exact failure class this issue exists to close.
    """
    tree = _staged_tree(tmp_path)
    guide_module = importlib.import_module("larkdocio.guide")
    packaged = tree / "src" / "larkdocio" / name
    # A document shorter than its window evicts nothing when a section opens (LD-691: the public
    # changelog starts at the last release made before the project was public). Fill the staged copy to its window with
    # synthetic OLDER sections first, so the eviction this test exists for can happen at all.
    window = guide_module.NOTES_WINDOW_SECTIONS[name]
    staged = (tree / name).read_text(encoding="utf-8")
    have = len(guide_module._bounded_sections(staged, guide_module.NOTES_WINDOW_LEVELS[name]))
    if have < window:
        filler = "".join(f"\n## [0.0.{n}] — 2000-01-01\n\nA staged older section.\n"
                         for n in range(window - have, 0, -1))
        (tree / name).write_text(staged.rstrip("\n") + "\n" + filler, encoding="utf-8")
        _run_sync(tree)
    rows = guide_module._bounded_sections(
        packaged.read_text(encoding="utf-8"), guide_module.NOTES_WINDOW_LEVELS[name]
    )
    carried = [v for v in (guide_module._release_version(row[2]) for row in rows) if v]
    oldest = carried[-1]

    root = tree / name
    text = root.read_text(encoding="utf-8")
    head = text.index("\n## [") + 1
    root.write_text(
        text[:head] + f"## [9.99.0] — 2099-12-31\n\nA staged section.\n\n" + text[head:],
        encoding="utf-8",
    )

    def _carried():
        rows_now = guide_module._bounded_sections(
            packaged.read_text(encoding="utf-8"), guide_module.NOTES_WINDOW_LEVELS[name]
        )
        return [v for v in (guide_module._release_version(row[2]) for row in rows_now) if v]

    before = packaged.read_bytes()
    warned = _run_sync(tree, "--check", expect=1)
    assert f"WILL EVICT {name}" in warned and oldest in warned, warned
    assert packaged.read_bytes() == before, "--check announced the eviction but also performed it"

    wrote = _run_sync(tree)
    assert f"EVICTED   {name}" in wrote and oldest in wrote, wrote
    assert oldest not in _carried(), (
        f"{name} was announced as evicting {oldest} and still ships that section")
    # The announcement carries the RULE, not just the fact: a reader learns where the content
    # still lives and what a guard requiring it must do, instead of re-deriving D-111.
    assert "stay COMPLETE in the root document" in wrote and "D-111" in wrote, wrote
    # …and the run that follows it is quiet again: the eviction is an EVENT, not a state.
    assert "EVICT" not in _run_sync(tree), "the announcement repeats after the truncation"
