"""LD-549 — THE LARK-APPLICATION WALKTHROUGH SHIPS IN THE WHEEL, AND IS OPENABLE FROM IT.

Why this module exists
----------------------
``LARK_SETUP.md`` is the ten minutes before a first download: create the app, grant the starter
scope, share the documents onto it, prove one real read. **Nothing in the library works until
those three facts hold**, and none of them is a code change — so it is the document a brand-new
consumer needs *first*. Until this issue the wheel did not carry it, which meant the only reader
who could open it was one holding the publishing repository: exactly the reader who needs it
least. Two consequences were visible from outside:

* the README's consumer half could only **name** it in plain text — the shipped-citation guard
  correctly refuses a link to a file the wheel does not carry — so the pointer a new consumer
  most needs was the one pointer they could not follow; and
* a vendor refresh dropped the guide, the changelog and the release notes beside the wheel and
  **not** the one document that unblocks a first call.

The shape of the fix, and why THIS shape
----------------------------------------
The canonical copy **stays at the repository root**. That is where a reader browsing the
publishing repository finds it, and where its own outbound pointers make sense; ``package-data``
cannot carry a file from there, so the in-package copy is a **materialised twin** — written only
by ``scripts/sync-packaged-notes.sh`` through ``larkdocio.guide.packaged_projection``, and held
byte-identical to that projection here. The projection for this document is the **identity**
(the whole document, byte for byte), unlike the two release documents' recent-N window: a setup
walkthrough grows no section per release and does not go out of date by being old, so a window
would subtract truth and buy nothing.

**An identity projection is not a licence to hand-copy**, and the guard below is what makes that
true rather than said: a packaged copy edited in place fails the byte equality exactly as a stale
window does, and ``--check`` reports it without writing anything.

What is asserted where
----------------------
The four arms mirror the issue's acceptance criteria, and each cites rather than re-tests what a
neighbour already covers:

* **AC1** the twin — declared, materialised, byte-identical, and the guard proven to BITE.
* **AC2** the door — ``lark_setup()`` / ``lark_setup_sections()``, exported, reading the
  **packaged resource**, and present in the ``docs`` registry. The wheel-only arms (an unpacked
  wheel and a ``pip install`` into a clean virtualenv) live in
  ``tests/test_release_notes_accessor.py`` beside their four siblings and are cited here.
* **AC3** the vendor drop — the refresh script's drop and its predates-the-tag skip. The
  FUNCTIONAL proof runs the real script against a local stand-in repository, and that harness is
  bash: it is the kit self-test's ``LD-165/LD-549`` case (``scripts/test/run.sh``). What is
  checked here is the pair of claims a grep can settle, so a silent deletion of either the drop
  or its skip note reddens ``pytest`` too.
* **AC4** the README's links — the observable point of the whole issue: the plain-text mentions
  are now real links, and the citation guard passes **because the wheel carries the file**, not
  because anything was labelled or waived.
"""
import pathlib
import re
import subprocess
import zipfile

import pytest

import front_door as fd
import larkdocio
from retired_particulars import load, value_hits
from larkdocio.guide import (
    LARK_SETUP_RESOURCE,
    NOTES_WINDOW_SECTIONS,
    PACKAGED_TWIN_RESOURCES,
    packaged_projection,
)
from test_shipped_notes import _built_wheel_record, notes_identity_report
import private_tree  # noqa: E402  (LD-685)

# LD-370 — CONFORMANCE-tier: a consumer who cannot start is not helped by anything else the
# wheel carries; shipping this document is the promise. See process/doctrine/conformance-tier.md.
pytestmark = pytest.mark.conformance

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CANONICAL = REPO_ROOT / LARK_SETUP_RESOURCE
PACKAGED = REPO_ROOT / "src" / "larkdocio" / LARK_SETUP_RESOURCE
UPDATER = REPO_ROOT / "consumers" / "update_larkdocio.sh"
SYNC = REPO_ROOT / "scripts" / "sync-packaged-notes.sh"


# --------------------------------------------------------------------------- #
# AC1 — the wheel carries it, as a materialised twin of the root file.         #
# --------------------------------------------------------------------------- #

def test_ac1_the_canonical_copy_is_at_the_repo_ROOT_and_the_twin_is_in_the_package():
    """Both files exist and neither is empty. The root one is the canonical: it is what a reader
    of the publishing repository opens, and it is the projection's INPUT."""
    assert CANONICAL.is_file(), f"the canonical walkthrough is missing: {CANONICAL}"
    assert PACKAGED.is_file(), f"the packaged twin is missing: {PACKAGED}"
    assert CANONICAL.read_text(encoding="utf-8").startswith("# Setting up your Lark application")


def test_ac1_it_is_DECLARED_as_package_data_not_swept_in_by_a_glob():
    """Read off ``pyproject.toml``'s own table, because *declared* is the property that makes
    the wheel carry it — and the negative half (no other root document swept in as a side
    effect) is ``tests/test_shipped_notes.py``'s own arm, widened by this landing."""
    packaged = {rel for rel in fd.packaged_doc_paths() if rel.endswith(".md")}
    assert f"src/larkdocio/{LARK_SETUP_RESOURCE}" in packaged, sorted(packaged)


def test_ac1_it_is_enrolled_in_the_ONE_twin_enumeration_the_writer_and_guards_share():
    """The membership list lives in ``larkdocio.guide`` and nowhere else — the sync script reads
    it, the guards read it. A second list is what rots."""
    assert LARK_SETUP_RESOURCE in PACKAGED_TWIN_RESOURCES
    assert LARK_SETUP_RESOURCE not in NOTES_WINDOW_SECTIONS, (
        "the walkthrough must NOT be windowed — a setup walkthrough has no releases to trim, "
        "and a window here would subtract truth"
    )


def test_ac1_the_projection_for_this_document_is_the_IDENTITY():
    """Stated as an equality rather than left implicit: the whole document, byte for byte. The
    reason it is identity and the release documents' is not lives on the function itself."""
    text = CANONICAL.read_text(encoding="utf-8")
    assert packaged_projection(text, LARK_SETUP_RESOURCE) == text


def test_ac1_the_packaged_twin_is_byte_identical_to_the_projection():
    """The drift guard, reusing the release documents' own report function so there is ONE
    definition of "the packaged copy equals the projection of the canonical one"."""
    report = notes_identity_report(names=(LARK_SETUP_RESOURCE,))
    assert not report, report


def test_ac1_the_drift_guard_BITES_on_a_ONE_CHARACTER_divergence(tmp_path):
    """A guard nobody has driven red is a hope. Both copies are staged in a temp tree, one byte
    is changed in the packaged one, and the real report function is asked."""
    root = tmp_path / "root"
    packaged = tmp_path / "pkg"
    root.mkdir()
    packaged.mkdir()
    text = CANONICAL.read_text(encoding="utf-8")
    (root / LARK_SETUP_RESOURCE).write_text(text, encoding="utf-8")
    (packaged / LARK_SETUP_RESOURCE).write_text(text, encoding="utf-8")
    assert not notes_identity_report(root, packaged, names=(LARK_SETUP_RESOURCE,))

    (packaged / LARK_SETUP_RESOURCE).write_text(text + "x", encoding="utf-8")
    report = notes_identity_report(root, packaged, names=(LARK_SETUP_RESOURCE,))
    assert [name for name, _reason in report] == [LARK_SETUP_RESOURCE], report

    # …and a MISSING twin is reported too, which is the state this landing started from.
    (packaged / LARK_SETUP_RESOURCE).unlink()
    assert [name for name, _reason in notes_identity_report(
        root, packaged, names=(LARK_SETUP_RESOURCE,))] == [LARK_SETUP_RESOURCE]


def test_ac1_the_sync_scripts_CHECK_mode_reports_this_document_and_writes_nothing():
    """``--check`` is what a human runs, so it is what is exercised: it must name this document
    and it must leave the tree alone (asserted on the bytes, not on the exit code alone)."""
    before = PACKAGED.read_bytes()
    result = subprocess.run(
        [str(SYNC), "--check"], capture_output=True, text=True, cwd=str(REPO_ROOT), check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert LARK_SETUP_RESOURCE in result.stdout, result.stdout
    assert PACKAGED.read_bytes() == before, "--check wrote to the packaged copy"


def test_ac1_the_BUILT_WHEEL_actually_carries_it(tmp_path):
    """The artifact, not the source tree: a ``package-data`` declaration that did not reach the
    wheel is the whole failure mode this arm exists for. Read out of the archive's own member
    list, with its content, so a zero-byte member cannot pass."""
    wheel = _built_wheel_record(tmp_path)
    with zipfile.ZipFile(wheel) as archive:
        member = f"larkdocio/{LARK_SETUP_RESOURCE}"
        assert member in archive.namelist(), sorted(
            n for n in archive.namelist() if n.endswith(".md")
        )
        shipped = archive.read(member).decode("utf-8")
        record = archive.read(
            next(n for n in archive.namelist() if n.endswith(".dist-info/RECORD"))
        ).decode("utf-8")
    assert shipped == PACKAGED.read_text(encoding="utf-8")
    assert member in record, "the walkthrough is in the archive but not in its RECORD"


# --------------------------------------------------------------------------- #
# AC2 — the programmatic door, consistent with its four siblings.              #
# --------------------------------------------------------------------------- #

def test_ac2_the_accessor_and_its_index_are_public_exports():
    for name in ("lark_setup", "lark_setup_sections"):
        assert callable(getattr(larkdocio, name)), f"larkdocio.{name} is not callable"
        assert name in larkdocio.__all__, f"{name} is not in larkdocio.__all__"
    namespace = {}
    exec("from larkdocio import *", namespace)
    assert callable(namespace["lark_setup"]) and callable(namespace["lark_setup_sections"])


def test_ac2_the_accessor_reads_the_PACKAGED_resource_not_a_filesystem_path():
    """The contract every sibling keeps: ``importlib.resources``, so it resolves identically
    from a checkout and from an installed wheel where no ``src/`` tree exists. Shown by the
    bytes it returns and by the absence of any path construction in the function's source."""
    import importlib.resources as resources
    import inspect

    packaged = resources.files("larkdocio").joinpath(LARK_SETUP_RESOURCE).read_text(
        encoding="utf-8"
    )
    assert larkdocio.lark_setup() == packaged
    assert larkdocio.lark_setup(section=None) == packaged
    source = inspect.getsource(larkdocio.lark_setup)
    assert "_packaged(" in source and "open(" not in source


def test_ac2_section_access_works_and_an_unknown_name_names_the_index_helper():
    rows = larkdocio.lark_setup_sections()
    assert rows and {row["level"] for row in rows} <= {2, 3}
    slugs = [row["slug"] for row in rows]
    assert len(slugs) == len(set(slugs)), f"a slug collides: {slugs}"
    first = rows[0]
    section = larkdocio.lark_setup(section=first["slug"])
    assert section.startswith("#" * first["level"] + " " + first["heading"])
    # asked by HEADING as well as by slug, both case-insensitively — the sibling contract
    assert larkdocio.lark_setup(section=first["heading"].upper()) == section
    with pytest.raises(ValueError) as refusal:
        larkdocio.lark_setup(section="not a section of this document")
    assert "lark_setup_sections" in str(refusal.value)


def test_ac2_the_docs_registry_carries_it_with_its_resource_and_its_section_index():
    entry = larkdocio.capabilities(full=True)["docs"]["lark_setup()"]
    assert entry["resource"] == f"larkdocio/{LARK_SETUP_RESOURCE}"
    assert entry["sections"] == [dict(row) for row in larkdocio.lark_setup_sections()]
    assert entry["summary"].strip()
    # The wheel-only arms (an unpacked wheel; a pip install into a clean venv) are in
    # tests/test_release_notes_accessor.py beside their four siblings — cited, not re-run.


#: LD-550 — the five walls, each as ``(a phrase from the wall's heading, the parent step's
#: heading prefix, a phrase that can only come from THAT wall's body)``.
#:
#: The pairing is the assertion that matters, and the reason the table has three columns rather
#: than one: a wall written at the wrong step is worse than no wall, because the reader meets it
#: after the point where it would have saved them. So each row pins **where** it sits as well as
#: **that** it exists, and pins one phrase of its body so a heading with nothing under it fails.
_WALLS = (
    ("is not a bot yet", "1. Create the app", "bot capability is added, not implied"),
    ("tenant or user", "2. Grant scopes", "tenant access token"),
    ("grant list keeps growing", "2. Grant scopes", "one refusal at a time"),
    ("release flow gates members", "3. Let the app REACH your documents", "availability list"),
    ("IP allowlist", "5. Prove it works", "add the **public** address"),
)

#: The label every wall carries, verbatim. It is the negative-claims discipline made visible in
#: the document itself: these are console-side observations from real onboarding attempts, and a
#: reader must not be able to mistake one for a measurement of the API.
_WALL_LABEL = "operator-observed console guidance"


def test_ld550_the_own_app_framing_is_the_FIRST_section_of_the_walkthrough():
    """AC1. The framing is worthless below the steps — somebody who has already created an app
    inside somebody else's tenant has already taken the decision it exists to change. So its
    position is pinned, not merely its presence, and so is the reason it gives (least privilege
    at team scale) rather than only the instruction."""
    rows = larkdocio.lark_setup_sections()
    first = rows[0]
    assert first["level"] == 2 and first["heading"].startswith("Running your own app"), rows[:2]
    assert rows[1]["heading"].startswith("1. Create the app"), rows[:2]
    body = larkdocio.lark_setup(section=first["slug"])
    for needle in ("do not ask to be added", "one app per person, or per team"):
        assert needle in body, f"the own-app framing no longer says {needle!r}"
    assert f"*{_WALL_LABEL}*" in body, (
        "the framing must name the class the walls below belong to, once, out loud"
    )
    # Wrap-insensitive on purpose: the emphasis and the noun phrase land on different lines in
    # the shipped document, and a reflow must not be able to redden a claim that is still there.
    flat = " ".join(body.split())
    assert "**not** measurements of the API" in flat


@pytest.mark.parametrize("phrase,step,content", _WALLS)
def test_ld550_each_wall_sits_AT_ITS_STEP_and_carries_the_label(phrase, step, content):
    """AC2, one arm per wall. The parent step is read off the section index **by position** — the
    nearest level-2 row above the wall — so a wall moved to a different step reddens even though
    every string in the document is unchanged."""
    rows = larkdocio.lark_setup_sections()
    parent = None
    for row in rows:
        if row["level"] == 2:
            parent = row["heading"]
            continue
        if phrase in row["heading"]:
            break
    else:
        raise AssertionError(
            f"no wall heading mentions {phrase!r}: {[r['heading'] for r in rows]}"
        )
    assert parent is not None and parent.startswith(step), (
        f"the {phrase!r} wall sits under {parent!r}, not under {step!r}"
    )
    assert _WALL_LABEL in row["heading"], row["heading"]
    body = larkdocio.lark_setup(section=row["slug"])
    assert content in body, f"the {phrase!r} wall no longer says {content!r}"


def test_ld550_there_are_exactly_FIVE_walls_and_no_unlabelled_sixth():
    """The census half. A sixth wall is welcome — but it arrives with its label and with this
    number moved deliberately, the same discipline the fence/heading triple in
    ``tests/test_packaged_doc_section_access.py`` is under."""
    rows = larkdocio.lark_setup_sections()
    walls = [row for row in rows if row["heading"].startswith("Wall — ")]
    assert len(walls) == len(_WALLS), [row["heading"] for row in walls]
    unlabelled = [row["heading"] for row in walls if _WALL_LABEL not in row["heading"]]
    assert not unlabelled, unlabelled
    assert all(row["level"] == 3 for row in walls), (
        "a wall is a subsection OF a step, never a step of its own"
    )


def test_ld550_the_tenant_identity_is_STATED_and_user_tokens_are_UNMEASURED_not_refuted():
    """AC2's middle clause, and the one with a doctrine behind it. The library's identity is a
    fact about its own code and is stated flatly; the user-token half is a claim about something
    nobody here has run, so it says **unmeasured** rather than *impossible* or *unsupported*."""
    text = larkdocio.lark_setup()
    assert "authenticates as the application on every call, with a tenant access token" in text
    assert "unmeasured, not refuted" in text, (
        "the user-token sentence must carry the unmeasured-not-refuted wording, not a bare "
        "'not supported'"
    )
    for overclaim in ("user tokens are not supported", "user tokens do not work"):
        assert overclaim not in text.lower(), overclaim


def test_ld624_the_wall_says_an_app_s_REACH_EXCEEDS_THE_SHARE_LIST_both_ways_and_scoped():
    """LD-624. It took three live probes to learn something a setup reader should be told in two
    sentences: **an app inherits tenant-wide visibility**, so its reach is WIDER than the operator's
    share list. The finding cuts two ways and both are pinned here, because a one-sided version
    is worse than nothing — the convenient half (check the app first, before reaching for
    per-person identity) saves a reader a large detour, and the uncomfortable half (an exposure
    audit read off the share list UNDER-COUNTS) is the one they most need. If either sentence is
    ever softened away, this reddens.

    Three further arms, one per hazard the wording exists to avoid:

    * **scoped** — one tenant, one app, one folder. Nothing here licenses "an app can always
      read everything",
      and the sentence that forecloses that reading is pinned too;
    * **Lark's behaviour, not ours** — the platform's permission model, never a larkdocio
      feature or a guarantee to build on;
    * **access, not scope** — the same wall discusses the application-versus-signed-in-person
      side of a *grant*, and this addition is about which *objects* a call may touch. A reader
      who conflates the two audits the wrong list.

    Wrap-insensitive on the same reasoning as the own-app arm above: the emphasis and the noun
    phrases land on different lines in the shipped document, and a reflow must not redden a
    claim that is still there.

    One wording note, so it is not "cleaned up" later: the shipped sentences say *visible to the
    whole tenant* rather than *org-wide*. The corpus-wide guard in
    ``tests/test_contacts_resolve_colleague.py`` forbids an unbounded "org-wide" in any
    consumer-reaching text, and it clears the phrase only when a negator happens to sit within the preceding 80
    characters. A claim about document visibility must not depend on the accident of a
    neighbouring word for its legality, so it does not use the idiom at all.
    """
    rows = larkdocio.lark_setup_sections()
    wall = next(row for row in rows if "tenant or user" in row["heading"])
    flat = " ".join(larkdocio.lark_setup(section=wall["slug"]).split())

    # (1) the convenient half.
    assert "check whether the app can already read what you are after" in flat
    # (2) the uncomfortable half — the one that must survive if only one does.
    assert "reach is WIDER than the list of things you shared with it" in flat
    assert "**not answerable from your share list**" in flat
    assert "*your shares, plus anything visible to the whole tenant*" in flat
    assert "**under-counts**" in flat

    # Scoped, and explicitly NOT over-generalised: a measurement is bounded to what it saw — one
    # tenant, one app, one folder. LD-700 (T2) superseded the conclusion that the bound is
    # stated with particulars; the reason stands and the bound stays. The guard holds the
    # bound; the private-ledger test below holds the walkthrough to the ledger's values.
    assert "**one tenant, one app, one folder**" in flat
    assert "a tenant that shares nothing tenant-wide would see none of it" in flat
    for overclaim in (
        "an app can always read anything",
        "every app can read everything",
    ):
        assert overclaim not in flat.lower(), overclaim

    # Lark's model, not a larkdocio feature.
    assert "Lark's own permission model, not anything larkdocio does" in flat

    # Access is not scope.
    assert "This is **access**, not scope" in flat


@private_tree.dev_record
def test_ld700_the_walkthrough_carries_none_of_the_dropped_particulars():
    """LD-700: the walkthrough carries none of the values in the private ledger's
    ``setup_values`` list (tests/retired_particulars.py), which is read at run time."""
    dropped = load("setup_values")
    assert not value_hits(larkdocio.lark_setup(), dropped)
    # …nor does any release-notes paragraph that describes the walkthrough.
    for name in ("RELEASE_NOTES.md", "src/larkdocio/RELEASE_NOTES.md"):
        text = (fd.REPO_ROOT / name).read_text(encoding="utf-8")
        for paragraph in re.split(r"\n(?=- )|\n\n", text):
            if "lark_setup()" in paragraph:
                assert not value_hits(paragraph, dropped), (name, paragraph[:120])


def test_ac2_the_walkthrough_does_not_QUOTE_a_scope_string():
    """The document's own discipline, and the reason it defers to a generated table: a scope
    copied into prose is where drift starts. Checked against the registry's real vocabulary
    rather than a pattern, so it cannot pass by spelling one differently."""
    from test_permissions_docs import _known_scopes

    scopes = _known_scopes()
    text = larkdocio.lark_setup()
    quoted = sorted(scope for scope in scopes if scope in text)
    assert not quoted, (
        f"the walkthrough quotes {quoted} — it must point at the generated table instead"
    )


# --------------------------------------------------------------------------- #
# AC3 — the vendor refresh drops it, and an older tag skips with its own note.  #
# --------------------------------------------------------------------------- #

def test_ac3_the_refresh_script_drops_it_beside_the_wheel():
    """Grep-level, and deliberately so: the FUNCTIONAL proof runs the real script against a
    local stand-in repository with no network, and that harness is bash — the kit self-test's
    ``LD-165/LD-549`` case. What this adds is that a silent deletion of the drop reddens
    ``pytest`` as well, which is the gate every landing runs."""
    text = UPDATER.read_text(encoding="utf-8")
    assert f'SETUP_SRC="$CLONE/{LARK_SETUP_RESOURCE}"' in text, (
        "the drop no longer sources the walkthrough from the checked-out tag's own tree"
    )
    # LD-694 F12: the drop is STAGED and vendored with the wheel after the version check, so
    # the destination is the staging directory; vendor_from_dir() carries it into ./vendor/
    # together with the wheel (tests/test_consumer_update_wheel_selection.py proves that
    # behaviourally). The drop itself — this assertion's subject — is unchanged.
    assert 'SETUP_DEST="$STAGE/${PKG}-LARK_SETUP.md"' in text
    assert "for doc in GUIDE CHANGELOG RELEASE_NOTES LARK_SETUP" in text
    assert f"carries no {LARK_SETUP_RESOURCE}" in text, (
        "the predates-the-document case must skip with its OWN logged note, not silently and "
        "not by failing the run"
    )


@private_tree.kit
def test_ac3_the_dist_FAST_PATH_vendors_it_too_so_the_two_paths_cannot_differ():
    """``./vendor/`` is promised identical whichever path ran. A document dropped by only the
    build path would break that promise silently, which is why both the fast-path loop and the
    publish that fills the branch it reads carry it."""
    assert "for doc in GUIDE CHANGELOG RELEASE_NOTES LARK_SETUP; do" in UPDATER.read_text(
        encoding="utf-8"
    )
    release = (REPO_ROOT / "scripts" / "release.sh").read_text(encoding="utf-8")
    assert "for doc in RELEASE_NOTES CHANGELOG LARK_SETUP; do" in release, (
        "the dist publish does not carry the walkthrough, so the fast path could not vendor it"
    )


# --------------------------------------------------------------------------- #
# AC4 — the README may now LINK it, and the citation guard PASSES.             #
# --------------------------------------------------------------------------- #

#: The link target the README must use — the path the WHEEL carries. The root copy is canonical
#: for editing, but a citation is judged by what an installed reader can open, which is the
#: whole rule ``front_door.wheel_carries`` states: resolution is by directory, never by basename.
_LINK_TARGET = f"src/larkdocio/{LARK_SETUP_RESOURCE}"

#: The two places the issue names — the role router's prerequisite line and the Requirements
#: box — plus the Requirements bullet that repeats it. Each is identified by a phrase near it
#: rather than by a line number, so a reflow does not rot the check.
_LINKED_MENTIONS = (
    "prerequisite for everyone",
    "is the ten-minute walkthrough**",
    "new to Lark",
)


def test_ac4_every_README_mention_of_the_walkthrough_is_a_REAL_LINK():
    """The observable point of the issue. Before it, these were plain text — the guard refuses a
    link to a file the wheel lacks, so naming it was the most the README could do."""
    text = fd.readme_text()
    consumer_half, _development_half = fd.split_at_development_heading(text)
    bare = []
    for lineno, line in enumerate(consumer_half.splitlines(), start=1):
        if LARK_SETUP_RESOURCE not in line:
            continue
        if f"]({_LINK_TARGET})" not in line:
            bare.append((lineno, line.strip()))
    assert not bare, (
        f"the README's consumer half still names {LARK_SETUP_RESOURCE} without linking it to "
        f"{_LINK_TARGET}: {bare}"
    )
    linked = [
        line for line in consumer_half.splitlines() if f"]({_LINK_TARGET})" in line
    ]
    assert len(linked) >= len(_LINKED_MENTIONS), (
        f"expected the walkthrough linked at least {len(_LINKED_MENTIONS)} times in the "
        f"consumer half (the router line, the Requirements box, the Requirements bullet); "
        f"found {len(linked)}"
    )
    # Each named mention has to be *at* one of those links — within two lines of it, because a
    # sentence in this document wraps and the link routinely lands on the following line.
    lines = consumer_half.splitlines()
    linked_at = [i for i, line in enumerate(lines) if f"]({_LINK_TARGET})" in line]
    for needle in _LINKED_MENTIONS:
        anchors = [i for i, line in enumerate(lines) if needle in line]
        assert anchors, f"the README no longer carries the mention near {needle!r}"
        assert any(abs(i - j) <= 2 for i in anchors for j in linked_at), (
            f"the mention near {needle!r} is not one of the linked ones"
        )


def test_ac4_the_link_resolves_INSIDE_THE_WHEEL_which_is_why_the_guard_passes():
    """Stated directly rather than left as a consequence: the guard is satisfied because the
    wheel carries the target, not because anything was labelled or added to a debt table."""
    packaged = fd.packaged_doc_paths()
    assert fd.wheel_carries("README.md", _LINK_TARGET, packaged)
    # …and the spelling the README canNOT use, for the same rule: the root path resolves for a
    # repository reader and for nobody holding a wheel.
    assert not fd.wheel_carries("README.md", LARK_SETUP_RESOURCE, packaged)


def test_ac4_neither_the_README_nor_the_WALKTHROUGH_carries_an_unlabelled_citation():
    """The whole-document statement. The walkthrough is now in the citation guard's scope (it is
    packaged), so its own outbound pointers are held to the same standard — which is why it
    names ``PERMISSIONS.md`` and the matrices as paths **in the dev repo** with the in-wheel
    address beside each, rather than as links a wheel reader cannot follow."""
    texts = fd.shipped_doc_texts()
    doc_rel = f"src/larkdocio/{LARK_SETUP_RESOURCE}"
    assert doc_rel in texts, "the packaged walkthrough is not in the citation guard's scope"
    for label in ("README.md", doc_rel):
        offenders = fd.unlabelled_shipped_citations(label, texts[label])
        assert not offenders, (
            f"{label} sends a wheel-only reader to a file the wheel does not carry with no "
            f"{fd.DEV_REPO_LABEL!r} note at or before it: {offenders}"
        )


def test_ac4_the_citation_check_on_the_walkthrough_BITES_when_the_label_is_removed():
    """The must-bite twin: strip the dev-repo label from a section and its citation is
    reported. Otherwise the arm above could be passing because nothing is being checked."""
    doc_rel = f"src/larkdocio/{LARK_SETUP_RESOURCE}"
    text = fd.shipped_doc_texts()[doc_rel]
    stripped = text
    for label in fd.REPO_LABELS:  # LD-699: either label warns, so strip both
        stripped = stripped.replace(f"**{label}**", "")
        stripped = re.sub(re.escape(label), "", stripped)
    offenders = fd.unlabelled_shipped_citations(doc_rel, stripped)
    assert offenders, (
        "removing every dev-repo label from the walkthrough reported no citation at all — the "
        "arm above proves nothing"
    )


def test_ac4_the_walkthrough_names_its_own_accessor_so_a_wheel_reader_is_not_stranded():
    """The counterpart of the label: a reader told a file is in the dev repo needs the address
    that answers from where they are standing."""
    text = larkdocio.lark_setup()
    assert "larkdocio.lark_setup()" in text
    assert "larkdocio.guide(" in text, (
        "the walkthrough defers its scope rows to the guide, so it has to name the call"
    )


def test_ld638_the_availability_wall_NARROWS_ITS_SHARED_ONTO_IT_clause():
    """LD-638. The availability wall's two-lists bullet is correct — availability is who may use
    the app, sharing is which documents it can see, both real, neither a substitute — and that
    point must survive untouched. Its *completeness* was the defect: read alone, **"still reads
    nothing that has not been shared onto it"** hands an operator back the exact under-count the
    LD-624 wall four sections above exists to prevent, because the clause is true only under the
    reading that a document visible to the whole tenant IS shared onto the app. That
    reading is stated at the tenant-or-user wall and was NOT stated here.

    So the clause is narrowed in place rather than rewritten, and both halves are pinned: the
    parenthetical that supplies the missing reading, and the two-lists sentence it sits inside.

    The wording says *tenant-wide* and not ``org-wide``, for the reason
    ``test_ld624_...`` records at length: the corpus guard in
    ``tests/test_contacts_resolve_colleague.py`` clears that idiom only when a negator lands
    inside the preceding 80 characters, and a claim about document visibility must not depend on
    a neighbouring word's accident for its legality.

    Read by section and wrap-insensitive, like every other wall arm here.
    """
    rows = larkdocio.lark_setup_sections()
    wall = next(row for row in rows if "release flow gates members" in row["heading"])
    flat = " ".join(larkdocio.lark_setup(section=wall["slug"]).split())

    # The narrowing itself — the missing reading, supplied where the clause is read.
    assert (
        "has not been shared onto it **(including tenant-wide visibility)**" in flat
    ), "the shared-onto-it clause lost its tenant-wide narrowing"
    # The phrase stays out of shipped prose.
    assert "org-wide" not in flat.lower()

    # The bullet's own point — untouched, and the reason the fix is a narrowing not a rewrite.
    assert "*Availability* is who may use the app" in flat
    assert "*sharing* is which documents the app can see" in flat
    assert "unusable by another user who is not on its availability list" in flat
