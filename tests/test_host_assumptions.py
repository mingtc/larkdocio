# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""LD-660 — the assumptions this repository makes about the HOST it runs on.

Three of them were untrue and unguarded:

1. **That the locale codec is UTF-8.** ``Path.read_text()`` with no ``encoding=`` decodes with
   :func:`locale.getencoding`. On macOS and a UTF-8 Linux that is UTF-8 and every such call is
   invisible; on a Windows default (cp1252/cp932/cp936) the same call either raises
   ``UnicodeDecodeError`` or silently yields mojibake. The shipped read seam
   (``permissions.pathlib_read``) and the guard that holds the shipped permissions
   documentation true (``test_permissions_docs.corpus``) both sat on that assumption, and the
   guard's version **swallowed the decode failure and reported green having read nothing**.
2. **That ``pytest_configure`` can defend an xdist-less install.** It cannot: the ``-n auto``
   in ``addopts`` is rejected by pytest's argument parser before any hook runs.
3. **That ``fcntl`` and ``tomllib`` are always there.** ``fcntl`` is POSIX-only and its
   ``flock`` is load-bearing (it serialises shared build artifacts across xdist workers, so a
   no-op fallback would reintroduce a real race); ``tomllib`` is 3.11+, which the wheel promised
   below until LD-713 raised its floor to 3.11 (D-119, superseded in part).

**Every population here is DERIVED, never hand-listed** — see ``tests/encoding_census.py`` for
why (the same count was hand-written four times and was wrong four times). And every arm below
can fail **because it could not check**, distinctly from passing: the census asserts its own
coverage floors, and the simulation arms assert the simulation actually simulated something.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

import encoding_census
import front_door
import test_permissions_docs as perm_docs
from larkdocio import permissions
import private_tree  # noqa: E402  (LD-685)

REPO_ROOT = encoding_census.REPO_ROOT

#: A byte sequence that is valid UTF-8 and **invalid cp1252**: U+2014 EM DASH followed by
#: U+00A0 NBSP encodes as e2 80 94 c2 a0, and 0x81 / 0x8d / 0x8f / 0x90 / 0x9d are undefined in
#: cp1252 — so the pair below is chosen to contain 0x9d, which makes a cp1252 decode RAISE
#: rather than quietly mojibake. That is what lets one assertion separate "read as UTF-8" from
#: "read with the locale" without needing a Windows host.
UTF8_ONLY_TEXT = "an em—dash, a nbsp and a “quote”"


def test_the_probe_text_really_is_utf8_only():
    """The instrument before the measurement: this fixture must actually discriminate.

    If ``UTF8_ONLY_TEXT`` happened to be cp1252-decodable, every arm below would pass for the
    wrong reason. Asserted rather than assumed.
    """
    raw = UTF8_ONLY_TEXT.encode("utf-8")
    assert raw.decode("utf-8") == UTF8_ONLY_TEXT
    assert b"\x9d" in raw, "the probe must contain a byte cp1252 leaves undefined"
    with pytest.raises(UnicodeDecodeError):
        raw.decode("cp1252")


# --------------------------------------------------------------------------
# AC1 — the shipped read seam
# --------------------------------------------------------------------------


def test_the_shipped_read_seam_decodes_utf8_not_the_locale(tmp_path):
    """``permissions.pathlib_read`` round-trips UTF-8-only bytes on any host.

    Red-watched by removing ``encoding="utf-8"`` from the seam: this arm fails with
    ``UnicodeDecodeError`` under a cp1252 locale, and — the reason the keyword is not merely
    cosmetic — the seam's callers read SHIPPED ``.py`` sources, 6 of which do not decode as
    cp1252 at all.
    """
    target = tmp_path / "probe.py"
    target.write_bytes(UTF8_ONLY_TEXT.encode("utf-8"))
    assert permissions.pathlib_read(target) == UTF8_ONLY_TEXT
    assert permissions.pathlib_read(str(target)) == UTF8_ONLY_TEXT


def test_the_seam_is_pinned_to_utf8_in_the_source_not_just_in_effect():
    """The keyword is IN the call, so a UTF-8 host cannot hide its removal.

    The arm above passes on this host even without the keyword (the locale IS UTF-8 here), so
    on its own it would be a guard that cannot fail where it runs. This one reads the shipped
    source and is host-independent.
    """
    source = (REPO_ROOT / "src" / "larkdocio" / "permissions.py").read_text(encoding="utf-8")
    body = source.split("def pathlib_read(", 1)[1]
    call = body.split("return ", 1)[1].split("\n", 1)[0]
    assert 'encoding="utf-8"' in call, (
        f"permissions.pathlib_read must pin the codec; its read call is: {call!r}"
    )


def test_a_decode_failure_cannot_present_as_no_sites_found(monkeypatch):
    """The swallow: ``except OSError`` must not be able to turn a broken read into ``{}``.

    A silent green is the failure mode this whole issue is about. ``UnicodeDecodeError`` is a
    ``ValueError``, so it flies past both call sites' ``except OSError`` — asserted here rather
    than reasoned about, because the reasoning is exactly what a future edit would break.
    """
    boom = UnicodeDecodeError("utf-8", b"\x81", 0, 1, "invalid start byte")

    def refuses(_path):
        raise boom

    monkeypatch.setattr(permissions, "pathlib_read", refuses)
    with pytest.raises(UnicodeDecodeError):
        permissions.constructions_outside_the_guards_reach()
    with pytest.raises(UnicodeDecodeError):
        permissions.denial_owning_sources()


def test_the_swallowed_case_really_is_only_oserror(monkeypatch):
    """The other half: an ``OSError`` still skips, so the arm above is about the codec alone."""

    def refuses(_path):
        raise OSError("gone")

    monkeypatch.setattr(permissions, "pathlib_read", refuses)
    assert permissions.constructions_outside_the_guards_reach() == {}
    assert permissions.denial_owning_sources() == {}


def test_the_shipped_sources_the_seam_reads_are_utf8_and_some_are_not_cp1252():
    """Why AC1 is a live defect and not hygiene — measured over the real shipped tree.

    Derived, not restated: every ``src/larkdocio/**.py`` is read as bytes and decoded both
    ways. The UTF-8 direction must be total (the seam would now raise otherwise) and the
    cp1252 direction must be **non-empty**, which is what makes "the locale default crashes the
    coverage machinery" a fact rather than a worry.
    """
    package = REPO_ROOT / "src" / "larkdocio"
    files = sorted(package.rglob("*.py"))
    assert len(files) > 100, f"only {len(files)} shipped .py files found — the walk is inert"
    undecodable_cp1252 = []
    for path in files:
        raw = path.read_bytes()
        raw.decode("utf-8")  # must be total: a failure here is a real broken source
        try:
            raw.decode("cp1252")
        except UnicodeDecodeError:
            undecodable_cp1252.append(path.relative_to(package).as_posix())
    assert undecodable_cp1252, (
        "no shipped source fails a cp1252 decode — if this ever becomes true the seam's "
        "encoding= is still right, but this arm has stopped measuring anything and should be "
        "re-scoped rather than deleted"
    )


# --------------------------------------------------------------------------
# AC2 — the scope guard stops reporting green while reading nothing
# --------------------------------------------------------------------------


@private_tree.citations
def test_the_permissions_corpus_reads_every_file_as_utf8():
    """The corpus is total over its candidate set — nothing is silently dropped.

    Non-vacuity in one line: the candidate list is re-derived here and the corpus must have an
    entry for **every** member of it. Before LD-660 a decode failure removed a file with no
    signal, so this equality could not have been asserted at all.
    """
    candidates = [rel for rel in perm_docs._repo_files() if not perm_docs._excluded(rel)]
    assert len(candidates) > 300, f"only {len(candidates)} candidates — the walk is inert"
    built = perm_docs.corpus()
    assert sorted(built) == sorted(candidates)


@private_tree.walks_tree
def test_the_corpus_was_measurably_blind_on_a_cp1252_host():
    """How blind: the before/after AC2 asks for, derived at run time rather than quoted.

    ``corpus_as_read_on_a_host_whose_locale_is`` reproduces the pre-fix body with the codec
    substituted — the only host-dependent input the old expression had (its docstring argues
    the fidelity). The cp1252 corpus must be **strictly smaller**, and must be missing the
    shipped guide, which is the file whose absence made the green tick a falsified claim.
    """
    utf8 = perm_docs.corpus_as_read_on_a_host_whose_locale_is("utf-8")
    cp1252 = perm_docs.corpus_as_read_on_a_host_whose_locale_is("cp1252")
    assert sorted(utf8) == sorted(perm_docs.corpus()), (
        "the simulation's utf-8 arm must reproduce the real corpus, or it is not a simulation "
        "of this guard"
    )
    dropped = sorted(set(utf8) - set(cp1252))
    assert dropped, (
        "no file is lost under cp1252 — the simulation measured nothing. Either the corpus has "
        "become pure ASCII (re-scope this arm, do not delete it) or the simulation is broken."
    )
    assert "src/larkdocio/GUIDE.md" in dropped, (
        f"the shipped guide should be among the {len(dropped)} file(s) a cp1252 host loses; "
        f"lost: {dropped[:8]}"
    )


@private_tree.walks_tree
def test_an_undecodable_corpus_file_is_a_failure_not_a_shrug(tmp_path):
    """The positive proof that the swallow is gone — on a COPY, never the working tree.

    A file that cannot be read is the one thing this guard exists to notice, so it must raise
    and it must name the file. The copy is a full corpus copy (the ``root=`` parameter
    ``_repo_files`` documents for exactly this), so no sibling xdist worker can see the
    mutation.
    """
    root = tmp_path / "repo"
    for rel in perm_docs._repo_files():
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((perm_docs.REPO_ROOT / rel).read_bytes())
    assert perm_docs.corpus(root=root), "the copied corpus is empty — the fixture is inert"

    victim = next(rel for rel in perm_docs.corpus(root=root) if rel.endswith(".md"))
    (root / victim).write_bytes(b"latin-1 only: \xff\xfe not utf-8\n")
    with pytest.raises(AssertionError) as caught:
        perm_docs.corpus(root=root)
    assert victim in str(caught.value)
    assert "EXCLUDED_FILES" in str(caught.value), (
        "the message must tell the reader where a genuine skip is declared"
    )


# --------------------------------------------------------------------------
# AC3 — the derived census, which is the deliverable that outlives the sweep
# --------------------------------------------------------------------------


@private_tree.walks_tree
def test_the_census_can_tell_could_not_check_from_found_nothing():
    """The non-vacuity floor, asserted before the population is asserted to be empty.

    An empty population is only good news if the walk actually walked. If ``_census_files()``
    returned nothing — a renamed tree, a moved ``REPO_ROOT`` — the emptiness below would be a
    guard reporting success for having checked no files, which is the exact shape LD-660 was
    filed about.
    """
    coverage = encoding_census.census_coverage()
    assert coverage["files"] > 500, f"the census walked only {coverage['files']} files"
    assert coverage["text_io_calls"] > 500, (
        f"the census saw only {coverage['text_io_calls']} text-I/O calls"
    )
    assert (REPO_ROOT / "src" / "larkdocio" / "permissions.py").exists()


@private_tree.walks_tree
def test_no_encodingless_text_io_call_is_added():
    """**The census guard.** Every text-I/O call in ``src``/``tests``/``scripts`` pins its codec.

    Red-watched by adding a bare ``read_text()`` to a real file. The population is generated by
    AST from the tree itself, so a new site cannot be added without reddening this and nobody
    maintains a list. Binary I/O is exempt and stays exempt — the exemptions and their reasons
    are in ``tests/encoding_census.py``'s module docstring.
    """
    sites = encoding_census.encodingless_text_io_sites()
    assert not sites, (
        f"{len(sites)} encoding-less text-I/O call(s) — add encoding=\"utf-8\":\n"
        + "\n".join(f"  {s.path}:{s.lineno} {s.source}" for s in sites[:25])
    )


def test_the_census_bites_on_an_added_bare_read_text(tmp_path, monkeypatch):
    """The census's own red proof, run against a copy of a real census file.

    The tree is copied and ``REPO_ROOT`` repointed, so the working tree is never mutated — the
    mutation-in-place discipline is used for the handoff's manual red-watch, but a test that
    edits shipped files under ``-n auto`` would be a race, not a proof.
    """
    for tree in encoding_census.CENSUS_TREES:
        (tmp_path / tree).mkdir()
    clean = tmp_path / "tests" / "a_clean_module.py"
    clean.write_text('import pathlib\npathlib.Path("x").read_text(encoding="utf-8")\n',
                     encoding="utf-8")
    monkeypatch.setattr(encoding_census, "REPO_ROOT", tmp_path)
    assert encoding_census.encodingless_text_io_sites() == ()

    clean.write_text('import pathlib\npathlib.Path("x").read_text()\n', encoding="utf-8")
    sites = encoding_census.encodingless_text_io_sites()
    assert [(s.path, s.function) for s in sites] == [("tests/a_clean_module.py", "read_text")]


@pytest.mark.parametrize("source, flagged", [
    ('p.read_text()', True),
    ('p.read_text(encoding="utf-8")', False),
    ('p.write_text(x)', True),
    ('p.write_text(x, encoding="utf-8")', False),
    ('open(p, "w")', True),
    ('open(p, "w", encoding="utf-8")', False),
    ('open(p)', True),
    ('open(p, "rb")', False),          # binary is correctly encoding-less
    ('open(p, mode="wb")', False),
    ('p.open("wb")', False),           # Path.open takes mode FIRST
    ('p.open("w")', True),
    ('p.read_bytes()', False),
    ('p.write_bytes(b"x")', False),
    ('os.open(p, os.O_RDWR)', False),  # a file descriptor: no encoding to add
    ('tarfile.open(p)', False),
    ('zipfile.open(p)', False),
    ('p.read_text(**kw)', False),      # the caller may be supplying encoding=
])
def test_the_census_classifies_each_call_shape_the_way_it_documents(tmp_path, monkeypatch,
                                                                   source, flagged):
    """Every exemption in the census's docstring, executed rather than asserted in prose.

    This is what stops the exemptions from quietly widening: ``p.open("w")`` must be caught
    even though ``p.open("wb")`` is not, and that distinction lives in one ``index = 0 if
    is_attribute else 1`` that a future edit could invert with no other test noticing.
    """
    for tree in encoding_census.CENSUS_TREES:
        (tmp_path / tree).mkdir()
    (tmp_path / "tests" / "shape.py").write_text(f"{source}\n", encoding="utf-8")
    monkeypatch.setattr(encoding_census, "REPO_ROOT", tmp_path)
    sites = encoding_census.encodingless_text_io_sites()
    assert bool(sites) is flagged, f"{source!r} -> {sites}"


@private_tree.internal_log
def test_the_shipped_changelog_quotes_the_census_rather_than_restating_it():
    """The eleventh wrong number of LD-660's session was the first to reach a SHIPPED artifact.

    The published ``CHANGELOG`` line said *"205 encoding-less text-I/O calls across
    ``tests/**``"*, hand-carried from an early probe run that predated
    ``POSITIONAL_ENCODING_INDEX`` (so it counted every already-correct exemption as a defect —
    the split is ``LD660_MERGE_BASE_EXEMPTIONS``, and the number that used to stand in this
    sentence was the wrong half of it) and
    postdated the two ``src/`` fixes (so it had already lost them). Both the total and the tree
    attribution were wrong, in a document the wheel carries, and it was caught only because a
    reviewer re-derived it instead of reading it.

    The remedy is the one this module already encodes for call sites: **the number comes from
    the instrument**. ``census_sentence`` renders it, the root and packaged ``CHANGELOG`` quote
    that rendering verbatim, and this arm holds all three together — so the shipped line cannot
    disagree with the census, in either direction.
    """
    sentence = encoding_census.census_sentence()
    assert "**154**" in sentence, (
        f"the recorded merge-base census has moved: {sentence!r}. That is allowed — but the "
        "shipped CHANGELOG describes a sweep that already happened at LD-660's merge base, so a change "
        "here means the RECORD changed, not the measurement, and needs its own reason."
    )
    # LD-691 (maintainer ruling 2): the packaged copy is now the PUBLIC changelog, which carries no
    # internal-log entry, so only the root log (where this entry lives) is held. The reason —
    # the line must quote the instrument — is unchanged; it simply no longer ships.
    for rel in ("CHANGELOG.md",):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert sentence in text, (
            f"{rel} no longer carries the census's own rendering of the LD-660 figure. Do not "
            f"retype it — paste encoding_census.census_sentence(), then re-run "
            f"scripts/sync-packaged-notes.sh. Expected:\n  {sentence}"
        )
        # The retired figure as a CLAIM, not as the quoted history. The entry deliberately
        # records what the wrong line said — that record is the point — so a bare "205" check
        # would fire on the confession. This is the third time in LD-660 that a guard nearly
        # matched its own explanation; the pattern is worth naming.
        assert "**205** encoding-less" not in text, (
            f"{rel} asserts the retired 205 figure again"
        )


def test_the_census_own_prose_quotes_the_measured_EXEMPTION_split(tmp_path, monkeypatch):
    """**LD-671 AC4b.** Three sentences in ``encoding_census`` carried the exemption figure by
    hand, and all three were wrong in the same way: they said *"53 already-correct positional
    calls"*, summing two different exemption shapes into one label, and one of them then
    reconstructed the missing shape as *"one more"* — a 54th site that has never existed.

    Same remedy as the CHANGELOG arm above, applied to this module's own prose: the figure is
    measured by ``exempt_sites``, rendered once by ``exemption_sentence``, and quoted verbatim.
    The count is pinned at **three** rather than merely ``>= 1`` so that a sentence dropping the
    quotation reddens as loudly as one contradicting it.
    """
    sentence = encoding_census.exemption_sentence()
    folded = " ".join(sentence.split())
    source = " ".join((REPO_ROOT / "tests" / "encoding_census.py")
                      .read_text(encoding="utf-8").split())
    assert source.count(folded) == 3, (
        f"encoding_census.py carries the exemption rendering {source.count(folded)} time(s), "
        f"expected 3 (the module docstring, POSITIONAL_ENCODING_INDEX, LD660_MERGE_BASE_CENSUS)."
        f" Do not retype the figures — paste encoding_census.exemption_sentence().\n  {sentence}"
    )

    # The renderer is a projection of its input, not a second opinion.
    assert encoding_census.exemption_sentence(
        {"positional": 3, "bare_name": 2, "total": 5}) == (
        "3 calls that already pin the codec positionally and 2 bare-name helpers — 5 in all")

    # ...and the instrument can actually SEE both shapes. Measured on a planted tree, so the
    # arm keeps meaning something if the real repo ever stops carrying an example of one.
    for tree in encoding_census.CENSUS_TREES:
        (tmp_path / tree).mkdir()
    (tmp_path / "tests" / "planted.py").write_text(
        'import pathlib\n'
        'def read_text(x):\n    return x\n'
        'read_text("a")\n'                              # bare name -> a local helper
        'pathlib.Path("p").read_text("utf-8")\n'        # positional codec
        'pathlib.Path("p").write_text("d", "utf-8")\n'  # positional codec, second slot
        'import os\nos.open("p", os.O_RDONLY, 0o644)\n',  # a file descriptor, NOT an exemption
        encoding="utf-8")
    monkeypatch.setattr(encoding_census, "REPO_ROOT", tmp_path)
    assert encoding_census.exemption_counts() == {
        "positional": 2, "bare_name": 1, "total": 3}


def test_the_summary_and_the_sentence_are_derived_from_the_same_sites():
    """The projection is not a second opinion: it counts the population, nothing else.

    Non-vacuity in one line — a synthetic tree with a known answer, so the renderer is measured
    rather than trusted.
    """
    import textwrap

    assert encoding_census.summary(()) == {
        "read_text": 0, "write_text": 0, "open": 0, "src": 0, "tests": 0, "scripts": 0,
        "total": 0}
    made_up = {"read_text": 3, "write_text": 2, "open": 1, "src": 1, "tests": 5, "scripts": 0,
               "total": 6}
    assert encoding_census.census_sentence(made_up) == (
        "**6** encoding-less text-I/O calls (`read_text` 3, `write_text` 2, text-mode `open` 1)"
        " — **5 under `tests/`, 1 in the shipped package**")
    assert textwrap  # the import is the reason this arm reads a tree, not a fixture string


def test_the_summary_counts_a_real_synthetic_population(tmp_path, monkeypatch):
    """And ``summary()`` over a tree with a planted, known population agrees with the walk."""
    for tree in encoding_census.CENSUS_TREES:
        (tmp_path / tree).mkdir()
    (tmp_path / "tests" / "a.py").write_text("p.read_text()\np.write_text(x)\n", encoding="utf-8")
    (tmp_path / "src" / "b.py").write_text('open(p, "w")\n', encoding="utf-8")
    monkeypatch.setattr(encoding_census, "REPO_ROOT", tmp_path)
    counts = encoding_census.summary()
    assert counts == {"read_text": 1, "write_text": 1, "open": 1, "src": 1, "tests": 2,
                      "scripts": 0, "total": 3}


def test_a_dynamic_mode_is_recorded_as_undecidable_not_dropped(tmp_path, monkeypatch):
    """What the census cannot decide is VISIBLE, because a silent skip is the original sin."""
    for tree in encoding_census.CENSUS_TREES:
        (tmp_path / tree).mkdir()
    (tmp_path / "tests" / "dyn.py").write_text("open(p, mode)\n", encoding="utf-8")
    monkeypatch.setattr(encoding_census, "REPO_ROOT", tmp_path)
    assert encoding_census.encodingless_text_io_sites() == ()
    assert [s.source for s in encoding_census.undecidable_sites()] == ["open(p, mode)"]


@private_tree.walks_tree
def test_the_repo_has_no_undecidable_text_io_site_today():
    """And the real tree's undecidable set is empty, so nothing is hiding behind that door."""
    assert encoding_census.undecidable_sites() == ()


# --------------------------------------------------------------------------
# AC4 — the .env bootstrap write
# --------------------------------------------------------------------------


def test_the_env_bootstrap_write_pins_its_encoding_and_the_template_is_still_ascii():
    """AC4 is HARDENING, not a fix — and this arm records both halves of that claim.

    The template is pure ASCII today, so the locale default could not mangle it; the keyword
    removes the trap for the next edit. The second assertion is the interesting one: if the
    template ever gains non-ASCII punctuation (this codebase uses it nearly everywhere), the
    write is already safe — but the arm below stops being a statement about a *latent* risk,
    and whoever makes it non-ASCII should update this docstring rather than the assertion.
    """
    from larkdocio.common import auth

    source = (REPO_ROOT / "src" / "larkdocio" / "common" / "auth.py").read_text(encoding="utf-8")
    assert "write_text(BOOTSTRAP_ENV_TEMPLATE, encoding=\"utf-8\")" in source
    assert auth.BOOTSTRAP_ENV_TEMPLATE.isascii(), (
        "the bootstrap template is no longer ASCII — the LD-660 keyword is now load-bearing "
        "rather than latent; say so where the claim is made"
    )


def test_the_env_bootstrap_actually_writes_utf8(tmp_path, monkeypatch):
    """And the write is exercised, not only grepped.

    ``load_dotenv`` is stubbed out: ``init_env``'s job here is the FILE, and letting the real
    loader run would push the template's blank credential names into this process's
    ``os.environ`` — a side effect no other test asked for.
    """
    from larkdocio.common import auth

    monkeypatch.setattr(auth, "load_dotenv", lambda *a, **k: None)
    target = tmp_path / "nested" / ".env"
    auth.init_env(env_path=str(target), create=True)
    assert target.read_bytes().decode("utf-8") == auth.BOOTSTRAP_ENV_TEMPLATE


# --------------------------------------------------------------------------
# AC5 — the xdist branch describes protection that exists
# --------------------------------------------------------------------------


def _pytest(*args, env=None):
    return subprocess.run(
        # LD-700: no cache — the child run must leave no .pytest_cache in the checkout.
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
    )


def test_an_xdist_less_run_dies_at_argument_parse_before_any_hook():
    """The measured fact that made the old comment false, pinned as a fact.

    ``-p no:xdist`` reproduces the xdist-absent install for argument-parsing purposes: ``-n``
    is unregistered either way. The run must fail with a **usage** error (EXIT 4) and collect
    nothing, which is what proves ``pytest_configure`` — and so the branch that claims to
    protect this shape — is never reached.
    """
    done = _pytest("-p", "no:xdist", "--collect-only", "tests/test_write_model.py")
    assert done.returncode == 4, done.stdout[-2000:] + done.stderr[-2000:]
    assert "unrecognized arguments: -n" in done.stderr + done.stdout
    assert "collected" not in done.stdout


def test_the_xdist_hook_body_only_ASSIGNS_so_the_absent_case_needs_no_guard():
    """AC5's second fact, derived from the shipped source by AST rather than by reading it.

    The retired ``hasattr`` guard was justified by the claim that the body would otherwise READ
    ``config.option.numprocesses`` and raise ``AttributeError``. It does not: every
    ``config.option`` access in the hook body is either an assignment target — assignment to an
    ``argparse.Namespace`` cannot raise, it creates the attribute — or a ``getattr`` with a
    default. This arm reddens the moment a bare read appears, which is the *only* edit that
    would make an xdist-absent guard necessary again.
    """
    import ast

    source = (REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    hook = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "pytest_configure")

    assigned, read = set(), set()
    for node in ast.walk(hook):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Attribute)
                        and target.value.attr == "option"):
                    assigned.add(target.attr)
        elif (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute)
              and node.value.attr == "option" and isinstance(node.ctx, ast.Load)):
            read.add(node.attr)

    assert assigned == {"numprocesses", "dist"}, assigned
    assert read == set(), (
        f"the hook body now READS config.option.{sorted(read)} directly. On a run with xdist "
        "unloaded that attribute may not exist, which is the one condition that would make an "
        "absent-xdist guard necessary again — see the LD-660 note in tests/conftest.py."
    )
    # The safe read is the getattr-with-default one, and it must still be there.
    assert 'getattr(config.option, "markexpr", "")' in source


def test_removing_the_hasattr_guard_really_is_harmless_measured_not_argued():
    """The guard is deleted, so the invocation it "protected" must now run clean — including a
    markexpr that actually ENTERS the assigning body.

    The previous arm here was **vacuous** and QA caught it: it asserted "no ``AttributeError``"
    on a run whose ``-m`` expression deselects every ring, so
    ``ring_selection_requires_serial`` returned ``False`` and the body was never entered at
    all — green with the guard and without it. This one selects ``zoo``, which forces the
    body's two assignments to execute with ``numprocesses`` **unregistered**. If assignment to
    an absent ``argparse.Namespace`` attribute could ever raise, this reddens.
    """
    entering = _pytest("-p", "no:xdist", "-o", "addopts=-q", "-m", "zoo",
                       "--collect-only", "tests/test_write_model.py")
    # EXIT 5 is "no tests collected" — every test in that module is deselected by `-m zoo`,
    # which is the point: the run must reach COLLECTION, i.e. `pytest_configure` completed. A
    # raise inside the hook is EXIT 3 with an INTERNALERROR, never 5.
    assert entering.returncode in (0, 5), entering.stdout[-3000:] + entering.stderr[-2000:]
    assert "AttributeError" not in entering.stdout + entering.stderr
    assert "INTERNALERROR" not in entering.stdout + entering.stderr

    deselecting = _pytest("-p", "no:xdist",
                          "-o", "addopts=-q -m 'not live and not zoo and not live_write'",
                          "tests/test_write_model.py")
    assert deselecting.returncode == 0, deselecting.stdout[-3000:] + deselecting.stderr[-2000:]
    assert " passed" in deselecting.stdout


def test_the_conftest_comment_no_longer_claims_the_unreachable_shape():
    """The comment is the artifact AC5 is about, so its text is guarded too.

    AC5's binding sentence is that a comment describing protection that does not exist is not
    acceptable. LD-660 violated it twice — once inherited, once freshly written — so what is
    guarded here is that the guard is DELETED and that both facts justifying the deletion are
    recorded beside it.
    """
    source = (REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    hook = source.split("def pytest_configure(", 1)[1].split("\ndef ", 1)[0]
    # CODE lines only. The prose above the body deliberately QUOTES the retired guard in order
    # to explain why it went, so a check over raw text would fire on the explanation itself —
    # the same trap this file already hit once.
    code = "\n".join(line for line in hook.splitlines() if not line.strip().startswith("#"))
    # The guard is GONE, not reworded: no `hasattr(...numprocesses...)` in front of the body,
    # and no early `return` that could reintroduce one.
    assert "numprocesses" not in code.split("if ring_selection_requires_serial", 1)[0], (
        "an xdist-absent guard is back in front of the body. AC5's ruling was to delete it and "
        "record why the case is undefended — see the LD-660 note in tests/conftest.py."
    )
    assert not [line for line in code.splitlines() if line.strip().startswith("return")], (
        "the hook grew an early return — re-derive the AC5 argument before adding one"
    )
    # BOTH recorded facts must stay next to the deletion; either alone makes it look careless.
    assert "unrecognized arguments" in hook, "fact 1 (the shape cannot reach the hook) has gone"
    assert "cannot raise" in hook, "fact 2 (the body only assigns) has gone"
    assert 'addopts = "-q -n auto' in (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"), (
        "if -n auto leaves addopts, the reachability argument above changes and the comment "
        "must be re-derived"
    )


def test_the_default_addopts_still_deselects_all_three_rings():
    """The safety property AC5 must not weaken, restated where the xdist claim is made.

    Three existing guards already assert this; this arm is here so that anyone editing
    ``addopts`` *for the parallelism* trips over the deselection in the same file.
    """
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "-m 'not live and not zoo and not live_write'" in text


# --------------------------------------------------------------------------
# AC6 — the POSIX / 3.11 imports
# --------------------------------------------------------------------------


def test_the_shared_artifact_lock_is_a_real_exclusive_lock(tmp_path):
    """The lock actually locks — a second process must block, not sail through.

    A no-op fallback would reintroduce the race the lock exists to prevent (shared build
    artifacts, produced once per run, consumed by every xdist worker), so "portable" is only
    acceptable if it is still exclusive. Measured by holding the lock here and having a child
    process try to take it: the child must not acquire it until this process lets go.
    """
    lock = tmp_path / "artifact.lock"
    script = (
        "import sys, pathlib\n"
        f"sys.path.insert(0, {str(REPO_ROOT / 'tests')!r})\n"
        "import front_door\n"
        f"with front_door.shared_artifact_lock({str(lock)!r}):\n"
        f"    pathlib.Path({str(tmp_path / 'child.stamp')!r}).write_text('in', encoding='utf-8')\n"
    )
    with front_door.shared_artifact_lock(lock):
        child = subprocess.Popen([sys.executable, "-c", script],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass  # the expected outcome: it is still waiting on the lock
        assert not (tmp_path / "child.stamp").exists(), (
            "the child entered the critical section while the lock was held — the lock is a "
            "no-op and the shared-artifact race is back"
        )
    out, err = child.communicate(timeout=60)
    assert child.returncode == 0, out + err
    assert (tmp_path / "child.stamp").read_text(encoding="utf-8") == "in"


def test_the_lock_dispatch_names_both_os_families_and_no_third_branch():
    """Portability is claimed only where it is implemented — and never as a fake.

    ``fcntl`` must no longer be a top-level import (that is the ImportError a Windows
    collection would hit), both branches must take a real kernel lock, and there must be no
    ``pass``/no-op third branch. The Windows branch is UNVERIFIED here and says so in its own
    comment; nothing in this change claims the suite passes on Windows (LD-669).
    """
    source = (REPO_ROOT / "tests" / "front_door.py").read_text(encoding="utf-8")
    head = source.split('if os.name == "nt"', 1)[0]
    assert "\nimport fcntl\n" not in head, "fcntl is a top-level import again"
    assert "msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)" in source
    assert "fcntl.flock(handle, fcntl.LOCK_EX)" in source
    assert "NOT verified" in source, "the honest-scope note about Windows has gone"


def test_the_suite_declares_its_own_python_floor_and_the_wheels_equals_it():
    """AC6's ``tomllib`` decision, and the wheel floor that now matches it.

    The suite needs 3.11 (``tests/front_door.py`` imports ``tomllib``). LD-660 kept the
    wheel's ``requires-python`` at ``>=3.10`` because nothing under ``src/larkdocio/``
    imported ``tomllib`` — true, but it promised a version the suite cannot collect on, so
    nothing tested it. SUPERSEDED IN PART by LD-713 (owner ruling 2026-11-07, ``D-119``):
    the reason "two claims, asserted separately" stands; the conclusion is now that the
    wheel's floor EQUALS the suite's. Both halves are still asserted, read from the parsed
    ``pyproject.toml`` rather than a byte pattern, so neither floor can move alone.
    """
    import conftest

    assert conftest.SUITE_PYTHON_FLOOR == (3, 11)
    assert "tomllib" in conftest.SUITE_PYTHON_FLOOR_REASON
    assert sys.version_info >= conftest.SUITE_PYTHON_FLOOR

    import tomllib

    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = pyproject["project"]["requires-python"]
    floor = ".".join(str(n) for n in conftest.SUITE_PYTHON_FLOOR)
    assert declared == f">={floor}", (
        f"the WHEEL promises {declared!r} but the suite's floor is {floor}: a wheel floor "
        "below the suite's is a promise nothing tests (LD-713), and one above it is a suite "
        "claim the wheel no longer makes — move both together, and say why in D-119"
    )
