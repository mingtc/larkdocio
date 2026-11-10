"""LD-414 — generalize ``section=`` access to ``writer_brief()`` / ``release_notes()`` /
``changelog()``, through the SAME seam ``guide(section=...)`` (LD-214) already uses.

**Why this file exists.** LD-214 built the section-access machinery generically
(``_bounded_sections`` / ``_section_index`` / ``_section_text`` all take a bare ``text``) but
wired it to exactly one accessor: ``guide()``. The other three packaged consumer documents are
exactly as big and exactly as un-slice-able (``write/README.md`` 715 lines,
``RELEASE_NOTES.md`` 2,600+ lines, ``CHANGELOG.md`` 3,800+ lines) and had no way to ask for one
part instead of all of it. This suite holds the generalization — same seam, no fork — and the
two measured findings the downtime-queue row named:

* **AC3 — heading levels are per-document, measured, not assumed.** The writer brief reuses the
  guide's own ``(2, 3)``; the release notes and the changelog do NOT — both repeat the exact
  same ``###`` subsection headings under every release, so indexing at ``(2, 3)`` would trip
  the "a slug collision raises" contract on every single call. This suite proves that
  divergence is REQUIRED, not a style choice, by demonstrating the collision that ``(2, 3)``
  produces on the real documents.
* **AC5 — the fence-blindness half is a MEASURED NO-OP.** ``_atx_headings`` is already
  fence-aware (LD-214's own AC), and it is the ONLY heading-scanning implementation in ``src/``
  — every new accessor here reuses it rather than a second regex. Measured per document, so the
  claim is pinned rather than asserted from memory.
"""
import importlib
import pathlib
import re

import pytest

import larkdocio
import packaged_sources
import private_tree
from larkdocio import capabilities
from larkdocio.guide import (
    CHANGELOG_SECTION_LEVELS,
    GUIDE_SECTION_LEVELS,
    LARK_SETUP_SECTION_LEVELS,
    RELEASE_NOTES_SECTION_LEVELS,
    WRITER_BRIEF_SECTION_LEVELS,
    _atx_headings,
    _section_index,
    changelog,
    changelog_sections,
    lark_setup,
    lark_setup_sections,
    release_notes,
    release_notes_sections,
    writer_brief,
    writer_brief_sections,
)
from test_guide_sections import _independent_headings, _naive_headings

_REPO = pathlib.Path(__file__).resolve().parent.parent

#: ``{name: (accessor, sections helper, its levels constant, docs()/entry_points() label)}`` —
#: the table this whole suite is parametrized over, so every AC is checked identically on all
#: three newly-covered documents rather than three near-duplicate test functions.
#: LD-549 enrols the FOURTH document — the Lark-application walkthrough — through the same
#: table rather than a fourth near-duplicate suite, which is the whole point of the seam being
#: generic: a new packaged document costs one row here and inherits every AC below.
_NEW_DOCS = {
    "writer_brief": (writer_brief, writer_brief_sections, WRITER_BRIEF_SECTION_LEVELS),
    "release_notes": (release_notes, release_notes_sections, RELEASE_NOTES_SECTION_LEVELS),
    "changelog": (changelog, changelog_sections, CHANGELOG_SECTION_LEVELS),
    "lark_setup": (lark_setup, lark_setup_sections, LARK_SETUP_SECTION_LEVELS),
}

_NAMES = sorted(_NEW_DOCS)


def _accessor(name):
    return _NEW_DOCS[name][0]


def _sections_fn(name):
    return _NEW_DOCS[name][1]


def _levels(name):
    return _NEW_DOCS[name][2]


# --------------------------------------------------------------------------- #
# AC1 — the SAME seam, no fork: signature, no-arg byte-identity, source proof.  #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", _NAMES)
def test_ac1_the_accessor_takes_an_optional_keyword_capable_section(name):
    import inspect

    signature = inspect.signature(_accessor(name))
    assert list(signature.parameters) == ["section"]
    parameter = signature.parameters["section"]
    assert parameter.default is None
    assert parameter.kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY,
    )
    assert _accessor(name)(section=None) == _accessor(name)()


def test_ac1_no_second_implementation_the_seam_functions_are_reused_verbatim():
    """No copy-paste of the heading scan: every accessor's ``section=`` path calls the SAME
    ``_section_text`` this module defines once, and there is exactly one heading-scanning
    regex anywhere the wheel ships — ``guide._ATX_HEADING`` — never a second one per document."""
    import importlib
    import inspect as _inspect
    import pathlib

    guide_module = importlib.import_module("larkdocio.guide")
    guide_source = _inspect.getsource(guide_module)
    for name in ("writer_brief", "release_notes", "changelog"):
        # each accessor's body calls `_section_text(` — never a second heading regex.
        body = guide_source.split(f"def {name}(", 1)[1].split("\ndef ", 1)[0]
        assert "_section_text(" in body, f"{name}() does not route through _section_text"
        assert "_ATX_HEADING" not in body and "_FENCE_DELIMITER" not in body, (
            f"{name}() defines its own heading/fence scan instead of reusing _atx_headings"
        )
    src_root = pathlib.Path(__file__).resolve().parent.parent / "src" / "larkdocio"
    heading_regex_files = [
        p for p in src_root.rglob("*.py")
        if "__pycache__" not in p.parts and "_ATX_HEADING = " in p.read_text(encoding="utf-8")
    ]
    assert [p.name for p in heading_regex_files] == ["guide.py"], (
        f"a second ATX-heading regex exists outside guide.py: {heading_regex_files}"
    )


@pytest.mark.parametrize("name", _NAMES)
def test_ac6_the_no_argument_call_is_still_the_packaged_resource_verbatim(name):
    """AC6: a new capability never changes an existing consumer's bytes."""
    import importlib.resources as resources

    from larkdocio.guide import (
        CHANGELOG_RESOURCE, LARK_SETUP_RESOURCE, RELEASE_NOTES_RESOURCE, WRITER_BRIEF_PACKAGE,
        WRITER_BRIEF_RESOURCE,
    )

    resource, package = {
        "writer_brief": (WRITER_BRIEF_RESOURCE, WRITER_BRIEF_PACKAGE),
        "release_notes": (RELEASE_NOTES_RESOURCE, "larkdocio"),
        "changelog": (CHANGELOG_RESOURCE, "larkdocio"),
        "lark_setup": (LARK_SETUP_RESOURCE, "larkdocio"),
    }[name]
    packaged = resources.files(package).joinpath(resource).read_text(encoding="utf-8")
    accessor = _accessor(name)
    assert accessor() == packaged
    assert accessor(section=None) == packaged


def test_ac6_guides_own_no_argument_call_is_unaffected_too():
    """The fourth accessor, for completeness — "all four accessors" is the AC's own wording."""
    from larkdocio import guide
    from larkdocio.guide import GUIDE_RESOURCE
    import importlib.resources as resources

    packaged = resources.files("larkdocio").joinpath(GUIDE_RESOURCE).read_text(encoding="utf-8")
    assert guide(full=True) == packaged


# --------------------------------------------------------------------------- #
# AC2 — contract parity: slug/heading (case-insensitive), boundary rule,       #
# unknown-name refusal naming every section, slug collisions raise.           #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", _NAMES)
def test_ac2_slug_and_heading_both_resolve_case_insensitively(name):
    rows = _sections_fn(name)()
    assert rows, f"{name} has no sections at all"
    row = rows[0]
    by_slug = _accessor(name)(section=row["slug"])
    assert _accessor(name)(section=row["heading"]) == by_slug
    assert _accessor(name)(section=row["heading"].upper()) == by_slug
    assert _accessor(name)(section=row["slug"].upper()) == by_slug
    assert _accessor(name)(section=f"  {row['heading']}  ") == by_slug
    assert by_slug.startswith("#" * row["level"] + " " + row["heading"])


@pytest.mark.parametrize("name", _NAMES)
def test_ac2_a_section_ends_before_the_next_same_or_higher_heading(name):
    text = _accessor(name)()
    levels = _levels(name)
    all_headings = [h for h in _independent_headings(text) if h[0] in levels]
    rows = _sections_fn(name)()
    assert [(r["level"], r["heading"]) for r in rows] == all_headings
    for index, row in enumerate(rows):
        section = _accessor(name)(section=row["slug"])
        start = text.index(section)
        after = text[start + len(section):]
        if not after:
            continue
        level, heading = next(
            (lv, h) for lv, h in all_headings[index + 1:] if lv <= row["level"]
        )
        assert after.startswith("#" * level + " " + heading), (
            f"{name}/{row['slug']} does not stop exactly where the next heading begins"
        )


@pytest.mark.parametrize("name", _NAMES)
def test_ac2_REASSEMBLY_every_top_level_section_tiles_the_document(name):
    """The proof that the slicer loses nothing: concatenating every top-level (lowest indexed
    level) section, in order, is the exact tail of the whole document."""
    text = _accessor(name)()
    rows = _sections_fn(name)()
    top_level = min(_levels(name))
    tail = "".join(_accessor(name)(section=r["slug"]) for r in rows if r["level"] == top_level)
    assert text.endswith(tail), f"{name}'s top-level sections do not tile the document's tail"
    preamble = text[:len(text) - len(tail)]
    assert preamble + tail == text
    assert f"\n{'#' * top_level} " not in preamble, (
        f"{name}'s preamble carries a top-level heading — a section was dropped from the index"
    )


@pytest.mark.parametrize("name", _NAMES)
def test_ac2_an_unknown_name_raises_ValueError_naming_every_section_and_the_RIGHT_index(name):
    rows = _sections_fn(name)()
    with pytest.raises(ValueError) as excinfo:
        _accessor(name)(section="this is not a real section name")
    message = str(excinfo.value)
    assert "this is not a real section name" in message
    missing = [row["slug"] for row in rows if row["slug"] not in message]
    assert not missing, f"{name}'s refusal omits {len(missing)} valid names: {missing[:5]}"
    # the refusal points at the RIGHT sibling helper, not at guide_sections() by accident —
    # the concrete failure mode of sharing one function without threading the hint through.
    sections_helper_name = f"{name}_sections"
    docs_key = f"{name}()"
    assert sections_helper_name in message, (
        f"{name}()'s refusal does not point at {sections_helper_name}(): {message}"
    )
    assert f"'{docs_key}'" in message, (
        f"{name}()'s refusal does not point at capabilities()['docs']['{docs_key}']: {message}"
    )
    if name != "guide":
        assert "guide_sections" not in message and "'guide()'" not in message, (
            f"{name}()'s refusal wrongly points at the guide's own index: {message}"
        )
    # LD-540 — THE BOUNDARY, in this direction. The two notes documents ship a recent-N window,
    # so they grew a SECOND refusal for a real release the window no longer carries. An UNKNOWN
    # name must not be dressed in that one: telling a caller who typed nonsense that their
    # release "is a real release … older than the window" is a lie, and telling them where the
    # full history lives is an answer to a question they did not ask. The out-of-window arm's
    # own mirror assertion is in test_ld540_* below.
    # LD-592 EXTENDS THAT REASON to the arm it never reached: the "is a real release" wording
    # is a lie on the OUT-OF-WINDOW arm too, for the same reason stated one line up — the wheel
    # carries only the window and cannot check it — so it is gone from both. This comment is
    # where the argument was already written down; nothing here is a new opinion.
    assert "out-of-window" not in message, (
        f"{name}()'s UNKNOWN-name refusal was laundered into the out-of-window one: {message}"
    )
    assert "carries a WINDOW" not in message


@pytest.mark.parametrize("name", _NAMES)
def test_ac2_a_slug_collision_at_this_documents_OWN_levels_raises(name):
    """The refusal contract, exercised generically: two headings at the document's own indexed
    level(s) that derive the same slug refuse at index-build time rather than serving one."""
    levels = _levels(name)
    level = min(levels)
    marker = "#" * level
    document = f"# T\n\n{marker} Read a sheet\n\nx\n\n{marker} Read a Sheet!\n\ny\n"
    with pytest.raises(ValueError) as excinfo:
        _section_index(document, levels=levels)
    message = str(excinfo.value)
    assert "read-a-sheet" in message
    assert "Read a sheet" in message and "Read a Sheet!" in message


# --------------------------------------------------------------------------- #
# AC3 — heading levels are MEASURED per document, and the divergence is        #
# REQUIRED for the notes/changelog, not a style choice.                       #
# --------------------------------------------------------------------------- #

def test_ac3_the_writer_brief_reuses_the_guides_own_levels():
    assert WRITER_BRIEF_SECTION_LEVELS == GUIDE_SECTION_LEVELS == (2, 3)


def test_ac3_the_release_notes_and_changelog_are_indexed_at_level_2_ONLY():
    assert RELEASE_NOTES_SECTION_LEVELS == (2,)
    assert CHANGELOG_SECTION_LEVELS == (2,)


@pytest.mark.parametrize("name", ["release_notes"])
def test_ac3_indexing_these_two_documents_at__2_3__WOULD_collide(name):
    """The measured REASON the divergence is required, not stylistic: every release repeats
    the same `###` subsection headings, so `(2, 3)` collides on the real, shipped document —
    proved here on the document itself, not on a synthetic decoy.

    LD-691 (maintainer ruling 2) moved the ``changelog`` case to the test below: the shipped changelog is
    now the PUBLIC one, which starts at the last release made before the project was public and
    does not yet repeat a ``###`` heading, so the collision cannot be measured on it until a second release opens one. The
    measured reason for ``CHANGELOG_SECTION_LEVELS`` lives in the internal log, and is held there."""
    text = _accessor(name)()
    with pytest.raises(ValueError) as excinfo:
        _section_index(text, levels=(2, 3))
    message = str(excinfo.value).lower()
    assert "two headings" in message or "collision" in message or "ambiguous" in message


@private_tree.internal_log
def test_ac3_indexing_the_INTERNAL_changelog_at__2_3__WOULD_collide():
    """The changelog half of the test above, on the document the level choice was measured on —
    the internal engineering log at the root of the maintainers' copy (LD-691)."""
    import pathlib as _pathlib

    text = (_pathlib.Path(__file__).resolve().parent.parent / "CHANGELOG.md").read_text(
        encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        _section_index(text, levels=(2, 3))
    message = str(excinfo.value).lower()
    assert "two headings" in message or "collision" in message or "ambiguous" in message


@pytest.mark.parametrize("name", ["release_notes", "changelog"])
def test_ac3_but_at_level_2_ALONE_there_is_no_collision(name):
    """**LD-540 re-based the sanity floor on the window instead of a literal.** The floor used to
    read ``len(rows) >= 10``, written when these documents carried twenty-odd releases each and
    meaning *"an index that collapsed to almost nothing means the level-2 scan broke"*. The wheel
    now carries a recent-N WINDOW, so the number of indexed releases is a **known** quantity — the
    window constant — and the honest floor is equality against that one source rather than a
    literal that a smaller window would falsify and a larger one would not catch. The reason
    survives intact and gets sharper: an index that loses or gains a release now reddens, where
    ``>= 10`` would have shrugged at nine of them vanishing."""
    rows = _sections_fn(name)()
    slugs = [r["slug"] for r in rows]
    assert len(slugs) == len(set(slugs)), f"{name} has duplicate level-2 slugs: {slugs}"
    guide_module = importlib.import_module("larkdocio.guide")
    resource = {
        "release_notes": guide_module.RELEASE_NOTES_RESOURCE,
        "changelog": guide_module.CHANGELOG_RESOURCE,
    }[name]
    # LD-691: a source with fewer sections than the window (the public changelog) ships whole,
    # so the floor is the smaller of the window and the source's own count — still exact.
    expected = min(guide_module.NOTES_WINDOW_SECTIONS[resource],
                   packaged_sources.source_release_count(_REPO, resource))
    assert len(rows) == expected, (
        f"{name} indexes {len(rows)} releases; the window this document ships is {expected}"
    )
    assert {r["level"] for r in rows} == {2}


def test_ac3_the_writer_brief_census_has_no_collision_at__2_3__either():
    rows = writer_brief_sections()
    slugs = [r["slug"] for r in rows]
    assert len(slugs) == len(set(slugs))
    assert {r["level"] for r in rows} == {2, 3}
    assert len(rows) >= 10


# --------------------------------------------------------------------------- #
# AC4 — an index per document, exported and DISCOVERABLE the way               #
# guide_sections() is, and capabilities()["docs"][...]["sections"] for all.    #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", _NAMES)
def test_ac4_the_sections_helper_is_exported_from_the_top_level(name):
    helper_name = f"{name}_sections"
    assert helper_name in larkdocio.__all__
    assert getattr(larkdocio, helper_name) is _sections_fn(name)
    namespace = {}
    exec("from larkdocio import *", namespace)
    assert callable(namespace[helper_name])


@pytest.mark.parametrize("name", _NAMES)
def test_ac4_capabilities_docs_row_carries_the_SAME_index(name):
    rows = _sections_fn(name)()
    entry = capabilities(full=True)["docs"][f"{name}()"]
    assert entry["sections"] == [dict(r) for r in rows]
    assert isinstance(entry["sections"], list)
    assert "section_addressing" in entry
    assert f"{name}(section=" in entry["section_addressing"]


def test_ac4_every_docs_row_now_carries_sections_not_only_the_guides():
    docs = capabilities(full=True)["docs"]
    assert set(docs) == {
        "guide()", "writer_brief()", "release_notes()", "changelog()", "lark_setup()",
    }
    for label, row in docs.items():
        assert row.get("sections"), f"{label} lost its section index"


@pytest.mark.parametrize("name", _NAMES)
def test_ac4_the_entry_point_registry_describes_the_new_export(name):
    helper_name = f"{name}_sections"
    entry = capabilities(full=True)["entry_points"][helper_name]
    assert entry["kind"] == "function"
    assert entry["summary"].strip() and entry["cost"].strip()
    assert "no api call" in entry["cost"].lower()


# --------------------------------------------------------------------------- #
# AC5 — the fence-blindness half is a MEASURED NO-OP: one heading scanner,     #
# already fence-aware, reused by every new accessor. Numbers pinned.          #
# --------------------------------------------------------------------------- #

#: The sentinel a document's row carries INSTEAD of a heading census, when the census is not
#: the thing being pinned. Reading it means: measure the document in front of you, and assert
#: only the invariant — ``fences == 0`` and ``naive == real``, i.e. this document has no
#: fence-blind path for the heading scanner to get wrong. Nothing about how many headings it
#: happens to have.
FENCE_BLIND_ONLY = "fence-blindness only — the census is incidental and is not pinned"

#: ``{document: (fence_delimiter_lines, naive_hash_matches, real_atx_headings)}``, or
#: :data:`FENCE_BLIND_ONLY` — the measurement from the issue's own ``## Decision``, pinned where
#: the census is the claim, and replaced by the invariant where it is not.
#:
#: **LD-540 retired the two notes rows' absolute counts, and the ledger below them with those
#: counts.** The wheel now carries a recent-N WINDOW of each release document instead of the
#: whole thing, so a section rolls OFF THE BACK at every release: the heading census of both
#: packaged notes documents would move at every single release **with no authored change at
#: all** — the exact shape of a guard that teaches people to edit the guard rather than the
#: door, and the shape this file's own neighbour already refuses for the same reason (the
#: changelog's principled exclusion from the per-citation ratchet in
#: ``test_front_door_doctrine``, whose recorded reason is *"a per-citation ratchet here would
#: also redden on every release"*). What the AC ever pinned is what the dict's own comment
#: already said it pinned — *"fences==0 / naive==real … whatever the census happens to be"* —
#: so that is now what the two notes rows carry, measured on the real document at run time.
#: **``writer_brief`` keeps its pinned triple**: it is the interesting row (fences ARE present
#: and DO suppress decoy headings, 18 naive vs 15 real), it does not move with a release, and
#: pinning it is what proves the fence-awareness fires rather than being idle.
#:
#: THE LEDGER BELOW IS CLOSED, NOT DELETED. Every row in it is the recorded reason a census
#: moved at one landing, and those reasons remain true of the landings that wrote them; what is
#: no longer true is that the next landing owes a row. The last row is LD-542's (135 -> 136).
#: A landing after LD-540 adds nothing here: the census is derived, so there is nothing to
#: re-cut and nothing to explain.
_FENCE_MEASUREMENTS = {
    # 18/15 → 19/16: the brief gained ONE level-3 heading — the projected table of the kinds
    # that accept `spans=`, which until then were enumerated in a private constant and in no
    # shipped document at all. No example was added, so the fence census stays 4 and the
    # naive-vs-real GAP stays 3, which is the property this row exists to prove.
    # 19/16 → 20/17 (LD-564): the dialect section gained ONE level-3 heading disclosing the
    # 50-per-call cap is NOT a compose() refusal (it fires later, in InsertRequest's own
    # constructor). No fence and no example added, so the fence census stays 4 and the
    # naive-vs-real GAP stays 3.
    # 20/17 → 21/18 and the fence census 4 → 6 (LD-518): the dialect section gained ONE
    # level-3 heading — "Finding every refusal in one pass — `compose_check`" — carrying ONE
    # fenced example (a ```python block, i.e. two fence lines). So both halves of this row
    # move together and for one reason, and the property the row exists to prove is unchanged:
    # the naive-vs-real GAP stays **3**, because the new fence hides no decoy heading.
    "writer_brief": (6, 21, 18),
    # The two notes documents grow a `## [X.Y.Z]` heading plus its subsections at every
    # release section that is opened, so their pair moves with the notes — by design, and in
    # THIS one place (LD-453 folded LD-425's duplicate literal into this dict). The
    # measurement the AC pins is fences==0 / naive==real: neither document has a fence-blind
    # path, whatever the census happens to be. `writer_brief` is the interesting row and it
    # does not move.
    # changelog 121 → 122 (LD-465): the open `## [1.34.0]` section gained a `### Added`
    # subsection — it had `### Fixed` and `### Changed` only, and a new field on the snapshot
    # artefact is an addition. One level-3 heading, no level-2 heading, no fence.
    # LD-471 opened `## [1.35.0]` in both: the changelog section carries one `### Fixed`
    # (121 → 122 was LD-465's; 122 → 124 is this one's heading pair), and the notes section
    # carries the mandatory four subsections plus its own `## [1.35.0]` (99 → 104).
    # LD-480 opened `## [1.36.0]` in both, because the `## [1.34.0]` section its entry was first
    # written under has since been CUT and dated and a cut section is a dated release record no
    # later landing may edit: the changelog section carries one `### Fixed` (124 → 126, the
    # heading pair), and the notes section carries the mandatory four subsections plus its own
    # `## [1.36.0]` (104 → 109).
    # LD-487 lands INTO that already-open `## [1.36.0]` (no new level-2 heading in either): the
    # changelog section gains one `### Added` subsection beside its `### Fixed` (126 → 127), and
    # the notes entry joins the `### New capabilities` subsection that section already carries,
    # so the notes census does not move (109).
    # LD-486 lands into the same already-open `## [1.36.0]`: the changelog section gains one
    # `### Changed` subsection beside its `### Added` / `### Fixed` (127 → 128), because a
    # superseded wording is neither an addition nor a fix; the notes entry joins the
    # `### Behavior changes you can observe` subsection that section already carries, so the
    # notes census does not move (109). No level-2 heading in either, no fence.
    # LD-476 opens `## [1.37.0]` in both, because `## [1.36.0]` has since been CUT and dated and
    # a cut section is a dated release record no later landing may edit: the changelog section
    # carries one `### Changed` (128 → 130, the heading pair — a disclosure re-stated as a
    # measured claim is neither an addition nor a fix), and the notes section carries the
    # mandatory four subsections plus its own `## [1.37.0]` (109 → 114). No fence in either.
    # LD-497 lands INTO that already-open `## [1.37.0]` (no new level-2 heading in either): the
    # changelog section gains one `### Fixed` subsection beside its `### Changed` (130 → 131),
    # because a dropped link restored is a fix and not a re-statement; the notes entry joins the
    # `### Behavior changes you can observe`, `### Upgrade & compatibility` and
    # `### Known limitations` subsections that section already carries, so the notes census does
    # not move (114). No fence in either.
    # LD-510 lands into the same already-open `## [1.37.0]`: the changelog entry joins the
    # `### Changed` subsection that section already carries (a superseded conclusion is neither
    # an addition nor a fix), and the notes entries join the `### Behavior changes you can
    # observe` and `### Known limitations` subsections it already carries. No level-3 heading is
    # opened in either document and no level-2 heading, so NEITHER pair moves (114 / 131).
    # LD-513 lands INTO that already-open `## [1.37.0]` — CHANGELOG.md only, one new
    # `### Process` subsection beside its `### Fixed`/`### Changed` (131 → 132): three
    # scripts/**+.claude/workflows/** kit riders are board mechanics per this file's own
    # EXCLUDE criterion, so RELEASE_NOTES.md gets no entry and its census does not move (114).
    # No fence in either.
    # LD-529 opens `## [1.38.0]` in both, because `## [1.37.0]` has since been CUT, dated and
    # TAGGED (v1.37.0, pyproject version = 1.37.0) and a cut section is a dated release record no
    # later landing may edit: the changelog section carries one `### Fixed` (132 -> 134, the
    # heading pair), and the notes section carries the mandatory four subsections plus its own
    # `## [1.38.0]` (114 -> 119). No column-0 fence in either — the notes entry's one HTML
    # example is an indented fence inside a bullet, the same shape the `## [1.37.0]` section's
    # own shell example already uses, which is why the fence census stays 0 and naive == real.
    # LD-531 lands INTO that already-open `## [1.38.0]` in both. The changelog section gains one
    # `### Changed` subsection beside LD-529's `### Fixed` (134 -> 135): re-homing where a Lark
    # code's meaning is authored, and replacing the reader's substring routing with typed
    # routing, is neither an addition nor a fix. The notes entries join the four mandatory
    # subsections that section already carries — `### New capabilities` gains its first real
    # content, replacing the `None.` LD-529 wrote there, which is a bullet and not a heading — so
    # NO level-3 heading is opened in the notes and no level-2 heading in either, and the notes
    # census does not move (119). No column-0 fence in either: the notes entry's one python
    # example is an indented fence inside a bullet, the same shape the merged-table entry's HTML
    # example already uses, so the fence census stays 0 and naive == real.
    # LD-475 lands INTO that same already-open `## [1.38.0]`, AFTER LD-531 opened its
    # `### Changed`: its changelog entry is one more bullet in that subsection, so it opens NO
    # heading of either level and the changelog census does not move (135). Its notes entry joins
    # the `### New capabilities`, `### Behavior changes you can observe` and
    # `### Upgrade & compatibility` subsections that section already carries, so the notes census
    # does not move either (119). No column-0 fence is added, so the fence census stays 0 and
    # naive == real in both.
    # LD-542 lands INTO that same already-open `## [1.38.0]` and opens ONE new `### Process`
    # subsection beside LD-531's `### Changed` and LD-529's `### Fixed` (135 -> 136) — the same
    # shape, and for the same stated reason, as LD-513's `### Process` in the release below
    # (131 -> 132): a `finish-pr.sh` repair is board mechanics, neither an addition nor a fix to
    # anything a caller can observe. `scripts/**` only, no `src/**` change, no consumer-visible
    # byte, so RELEASE_NOTES.md gets NO entry under this file's own EXCLUDE criterion and its
    # census does not move (119). No column-0 fence is added in either document, so the fence
    # census stays 0 and naive == real in both.
    # LD-540: both rows below were `(0, 119, 119)` and `(0, 136, 136)` at the moment the window
    # landed. They are the last census figures either document will ever have pinned here.
    "release_notes": FENCE_BLIND_ONLY,
    "changelog": FENCE_BLIND_ONLY,
    # LD-549 — the Lark-application walkthrough carries a PINNED TRIPLE, like `writer_brief`
    # and unlike the two notes rows, and the reason is the one the sentinel's own note gives:
    # the sentinel exists for a census a RELEASE moves, and no release moves this document (it
    # grows no section per release and nothing rolls off its back). It also could not take the
    # sentinel even if that were wanted — the sentinel's arm asserts `fences == 0`, and this
    # document has 6 fence delimiter lines (three examples: one python, two shell). Measured at
    # this landing: 6 fences, 7 naive `^#` matches, 7 real headings — equal, because its fences
    # carry no decoy heading, which is the fence-blindness claim the AC pins here.
    # `writer_brief` remains the row that proves the fence-awareness actually FIRES (18 vs 15).
    # LD-550 moves the heading half of that triple, 7 -> 13, and the fence half not at all. The
    # document gained the own-app framing (one level-2 heading) and the five operator-observed
    # walls it was missing — the bot-settings page split under step 1, the tenant-vs-user
    # permission column and the growing grant list under step 2, the release flow's reach over
    # availability and membership under step 3, and the IP allowlist under step 5 (five level-3
    # headings). No example was added, so the fence census stays 6 and naive == real still
    # holds: the six delimiter lines are the same three examples, and no wall hides a decoy
    # heading inside one.
    "lark_setup": (6, 13, 13),
}


@pytest.mark.parametrize("name", sorted(_FENCE_MEASUREMENTS))
def test_ac5_the_measured_no_op_fence_naive_and_real_counts(name):
    """Pins the AC5 measurement: none of these documents has a fence-blind path that
    ``_atx_headings`` misses. ``write/README.md`` is the interesting case (fences ARE present
    and DO suppress decoy headings — proving the fence-awareness fires, not merely that there
    is nothing to be blind to); the notes and the changelog carry no fences at all, so the
    naive and real counts are trivially equal; ``LARK_SETUP.md`` (LD-549) sits between the two
    — fences present, no decoy heading among them, so its equality is measured rather than
    structural.

    **LD-540 — THE PER-RELEASE RE-CUT IS GONE, AND WHY.** Until this issue the two notes rows
    pinned absolute heading counts and every landing that opened a subsection owed a comment row
    explaining the movement — around fifty lines of ledger by the end. The wheel now ships a
    recent-N WINDOW of each release document, so a section rolls off the BACK at every release
    and those counts would move with no authored change at all: the ceremony would have gone from
    "a row per landing that touches the notes" to "a row per release, forever, for nothing". So
    the two rows now carry :data:`FENCE_BLIND_ONLY` and the invariant is measured here instead.
    **What the next reader needs to know:** the window's back edge is DERIVED (no pin, no
    ceremony — the projection is a function of the root document and the one window constant), and
    a heading census of either packaged notes document is no longer pinned anywhere. The one thing
    still pinned is ``writer_brief``'s triple, which no release moves."""
    text = _accessor(name)()
    fences = [line for line in text.split("\n") if re.match(r"^(`{3,}|~{3,})", line)]
    naive = _naive_headings(text)
    real = _independent_headings(text)
    pinned = _FENCE_MEASUREMENTS[name]
    if pinned is FENCE_BLIND_ONLY:
        # LD-540: the invariant, measured, with NO census pinned — see the dict's own note. The
        # per-release re-cut this row used to owe is GONE, because the wheel now ships a WINDOW
        # of this document and a section rolls off the back at every release: an absolute count
        # here would redden with no authored change at all, which is a guard that trains people
        # to edit the guard. What the AC pins is fence-blindness, and that is what is checked.
        assert len(fences) == 0, f"{name}: a fence appeared where the census assumed none"
        assert len(naive) == len(real), (
            f"{name}: a fence-blind path opened — naive {len(naive)} vs real {len(real)}"
        )
        return
    fence_count, naive_count, real_count = pinned
    assert len(fences) == fence_count, f"{name}: fence count moved to {len(fences)}"
    assert len(naive) == naive_count, f"{name}: naive ^# count moved to {len(naive)}"
    assert len(real) == real_count, f"{name}: real heading count moved to {len(real)}"


def test_ac5_write_readmes_fences_DO_suppress_a_real_naive_vs_real_gap():
    """The write brief is the one document of the three with fences AND a naive/real gap
    (18 vs 15) — proof the fence-awareness this module reuses is actually exercised on it,
    not merely present and idle."""
    text = writer_brief()
    naive = _naive_headings(text)
    real = _independent_headings(text)
    assert len(naive) > len(real), (
        "the write brief's naive-vs-real gap closed — this test no longer proves anything"
    )


@pytest.mark.parametrize("name", sorted(_FENCE_MEASUREMENTS))
def test_ac5_no_bypass_the_naive_and_real_counts_are_EQUAL_when_there_are_no_fences(name):
    """The direct statement of the "measured no-op" verdict: where a document carries NO
    fences at all (the notes, the changelog), a fence-blind bug is structurally impossible —
    there is nothing for a naive scan to get wrong. Where fences ARE present (the write brief;
    and the walkthrough, LD-549), the fenced arm below holds the pinned triple and the previous
    test proves the awareness actually fires on the one document with a real gap."""
    pinned = _FENCE_MEASUREMENTS[name]
    text = _accessor(name)()
    if pinned is FENCE_BLIND_ONLY:
        # LD-540: measured rather than read off a pin — the claim is identical, and it no longer
        # depends on a number that a release moves.
        assert len([l for l in text.split("\n") if re.match(r"^(`{3,}|~{3,})", l)]) == 0
        assert len(_naive_headings(text)) == len(_independent_headings(text))
        return
    fence_count, naive_count, real_count = pinned
    if fence_count == 0:
        assert naive_count == real_count


def test_ac5_the_only_heading_scanning_regex_anywhere_in_src_is_guides():
    """The other half of "no bypass": nothing else in the shipped package scans for ATX
    headings by any other means, so there is no second, un-fence-aware implementation any
    packaged document's section index could quietly fall back to."""
    import pathlib

    src_root = pathlib.Path(__file__).resolve().parent.parent / "src" / "larkdocio"
    offenders = []
    for path in src_root.rglob("*.py"):
        if "__pycache__" in path.parts or path.name == "guide.py":
            continue
        source = path.read_text(encoding="utf-8")
        if re.search(r"\^#\{1,6\}|_ATX_HEADING|startswith\(.#.\)\s*and", source):
            offenders.append(str(path))
    assert not offenders, f"a second heading-scanning implementation exists: {offenders}"


# --------------------------------------------------------------------------- #
# AC7 — the guide documents section access for ALL FOUR documents.             #
# --------------------------------------------------------------------------- #

def test_ac7_the_guide_documents_section_access_for_every_new_accessor():
    from larkdocio import guide

    text = guide(full=True)
    for name in _NAMES:
        assert f"{name}(section=" in text, f"the guide never mentions {name}(section=...)"
        assert f"{name}_sections()" in text, f"the guide never mentions {name}_sections()"


def test_ac7_the_guide_states_each_documents_own_indexed_levels():
    from larkdocio import guide

    text = guide(full=True)
    assert "level-2 ONLY" in text or "level-2 alone" in text.lower(), (
        "the guide does not state that the notes/changelog are indexed at level 2 alone"
    )


def test_ac7_the_new_guide_example_actually_runs():
    """A `python` fence that does not run is worse than prose (the LD-133 discipline). This
    extracts the fence this issue adds and executes it in a plain builtins-only namespace —
    the same standard ``guide_recipes.run_recipe`` holds every OTHER guide example to."""
    import builtins

    from larkdocio import guide

    text = guide(full=True)
    # LD-549 renamed the heading (three documents -> four) when the walkthrough joined the
    # seam; the fence it extracts is the same one, now carrying the fourth document's leg too.
    section = text.split("### Reading ONE section of the other four documents", 1)[1]
    blocks = re.findall(r"```python\n(.*?)```", section, flags=re.DOTALL)
    assert len(blocks) == 1, f"expected exactly one python fence, found {len(blocks)}"
    namespace = {"__builtins__": builtins}
    exec(compile(blocks[0], "<guide LD-414 example>", "exec"), namespace)


@private_tree.internal_log
def test_ac10_the_release_notes_and_changelog_announce_the_new_capability():
    """LD-414 was announced in ``[1.33.0]``, and that section is **read from the repository's
    own copies**, not through the accessors.

    Not a weakening — a consequence of LD-540's window, transformed rather than dropped
    (LD-560, which opened ``[1.41.0]`` and slid ``[1.33.0]`` out of the wheel's recent-N
    projection). What an announcement claim is *about* is the release document, and the
    complete release document is the repository file; the accessor returns a window whose job
    is the *recent* releases and which is expected to age past an old announcement. The claim
    that the CAPABILITY stays reachable from the wheel is a different claim, and it is held
    where it belongs — by this module's own ``section=`` tests and by
    ``tests/test_release_notes_accessor.py``'s fallback-surface arm.
    """
    import inspect
    import pathlib

    import larkdocio

    root = pathlib.Path(inspect.getfile(larkdocio)).parents[2]
    for path_text, label in (
        ((root / "RELEASE_NOTES.md").read_text("utf-8"), "RELEASE_NOTES.md"),
        ((root / "CHANGELOG.md").read_text("utf-8"), "CHANGELOG.md"),
    ):
        section = path_text.split("## [1.33.0]", 1)[1].split("\n## [1.32.0]", 1)[0]
        assert "writer_brief_sections" in section, f"{label} does not announce LD-414"
        assert "release_notes_sections" in section
        assert "changelog_sections" in section


# --------------------------------------------------------------------------------------- #
# LD-540 — THE OUT-OF-WINDOW REFUSAL. The wheel ships a recent-N window of each release      #
# document, so `section=` grew a SECOND failure that must never be confused with the first.  #
# --------------------------------------------------------------------------------------- #

_WINDOWED = ("release_notes", "changelog")


def _window_resource(name):
    guide_module = importlib.import_module("larkdocio.guide")
    return {
        "release_notes": guide_module.RELEASE_NOTES_RESOURCE,
        "changelog": guide_module.CHANGELOG_RESOURCE,
    }[name]


@pytest.mark.parametrize("name", _WINDOWED)
def test_ld540_an_OUT_OF_WINDOW_release_refuses_with_its_OWN_message_naming_a_PATH(name):
    """AC2's binding proof: naming a release **older** than the shipped window refuses with a
    message that (a) is its own message and not the unknown-section one, (b) says what the
    window is, and (c) names **a path** the full history sits at.

    **``git history`` is not an address** (``process/doctrine/lookup-tables.md``), so this asserts
    a real openable path is present and that no wording sends the reader to a revision history
    instead. The oldest release the window carries is read off the document, so this test needs no
    literal version and does not move when the window rolls.

    **TRANSFORMED, not struck (LD-592 / supersession).** Every invariant above is unchanged and
    still asserted; one assertion moved and one arm was added.

    * *Moved:* this test used to assert ``"is a real release" in message`` — i.e. it asserted
      the defect. That opening is an **existence claim the wheel cannot check**: the packaged
      copy carries only the window, so the assertion was vouching for any version-shaped string
      that sorts below it, and every cut mints a fresh band of such strings with no authored
      change. The reason the clause existed — *do not tell a caller their real release does not
      exist* — is preserved in full and is now carried by the ``"unknown section" not in
      message`` and ``startswith("out-of-window section")`` assertions plus the window/span/path
      clauses, none of which claim anything about the asked-for name. The project had already
      written this argument down for the sibling arm: the comment above the unknown-name mirror
      assertion earlier in this file calls exactly this wording *a lie*, and fenced only that
      arm. This extends that reason to the arm it never reached.
    * *Added:* the second parametrized subject is a **fabricated** in-range version — one minor
      below the window's oldest with a non-zero patch, a spelling this project has never cut
      (0 of its ``v*`` tags carry a non-zero patch; the evidence is asserted in
      ``test_ld592_…::test_ac3_the_fabricated_version_really_never_shipped``). It must get the
      same true message, and vouch for nothing.
    """
    rows = _sections_fn(name)()
    guide_module = importlib.import_module("larkdocio.guide")
    # LD-691: fewer sections than the window means the copy is the WHOLE document.
    whole = len(rows) < guide_module.NOTES_WINDOW_SECTIONS[_window_resource(name)]
    oldest = min(
        (guide_module._release_version(r["slug"]) for r in rows),
        key=guide_module._version_tuple,
    )
    major, minor, patch = (int(part) for part in oldest.split("."))
    # One minor BELOW the window's own oldest — a version this project really cut, and by
    # construction outside the window whatever the window happens to be. Beside it, the same
    # coordinate with a NON-ZERO patch: in range, plausible, and never cut.
    for asked in (f"{major}.{minor - 1}.{patch}", f"{major}.{minor - 1}.1"):
        with pytest.raises(ValueError) as excinfo:
            _accessor(name)(section=asked)
        message = str(excinfo.value)

        assert message.startswith("out-of-window section"), message
        assert "unknown section" not in message, (
            "the out-of-window refusal was laundered into the unknown-section one — a caller "
            f"would be told a real release does not exist: {message}"
        )
        assert asked in message, message
        assert "is a real release" not in message, (
            "the refusal vouches for a version the wheel cannot check — it carries only the "
            f"window, so this assertion cannot be earned from inside it: {message}"
        )
        if whole:
            # The whole document ships: the refusal must not call it a window, and points at
            # where the older history really is (the release notes, a public call).
            assert "carries every release this document records" in message, message
            assert oldest in message and "release_notes()" in message, message
        else:
            assert f"newest {len(rows)} releases" in message and oldest in message, message
            assert re.search(r"vendor/larkdocio-(CHANGELOG|RELEASE_NOTES)\.md", message), (
                f"the refusal names no openable PATH for the full history: {message}"
            )
        assert "git history" not in message.lower() and "git log" not in message.lower(), (
            "a revision history is not an address — the refusal must name a path a reader "
            "can open"
        )
        # It still points at the RIGHT index, the way the unknown-section refusal does.
        assert f"{name}_sections" in message and f"'{name}()'" in message, message


@pytest.mark.parametrize("name", _WINDOWED)
def test_ld540_a_release_INSIDE_the_window_still_resolves_unchanged(name):
    """The other side of the boundary: every release the window carries is still fetchable by its
    own slug and by its heading, byte for byte, through the unchanged path. A refusal that fired
    for an in-window release would be the real regression."""
    for row in _sections_fn(name)():
        by_slug = _accessor(name)(section=row["slug"])
        by_heading = _accessor(name)(section=row["heading"])
        assert by_slug == by_heading
        assert by_slug.startswith("## " + row["heading"])


@pytest.mark.parametrize("name", _WINDOWED)
def test_ld540_a_NON_VERSION_name_still_gets_the_UNKNOWN_refusal_not_the_window_one(name):
    """The discrimination is on whether the name parses as a **release version**, so a name that
    never was one keeps the original message. This is the mirror of the assertion added to
    ``test_ac2_an_unknown_name_raises_ValueError_naming_every_section_and_the_RIGHT_index``, and
    together they are what stops either failure from being dressed as the other."""
    with pytest.raises(ValueError) as excinfo:
        _accessor(name)(section="reading a sheet into markdown")
    message = str(excinfo.value)
    assert message.startswith("unknown section"), message
    assert "out-of-window" not in message and "carries a WINDOW" not in message, message


@pytest.mark.parametrize("name", _WINDOWED)
def test_ld540_the_packaged_copy_DISCLOSES_its_own_window_above_the_first_section(name):
    """The narrowing is disclosed where a reader meets it — at the top of the shipped document,
    not only in a refusal they may never trigger. The banner is preamble, never a heading: a
    heading here would enter this document's own section index and break the reassembly contract
    the AC2 tiling test asserts, so that is checked too."""
    text = _accessor(name)()
    head = text[: text.index("\n## [")]
    resource = _window_resource(name)
    # LD-691: a copy that ships its WHOLE source discloses that instead of a window.
    disclosure = ("carries every release this document records"
                  if packaged_sources.ships_whole(_REPO, resource)
                  else "carries a WINDOW of the newest")
    assert disclosure in head, (
        f"{name}'s shipped copy has no window disclosure above its first release section"
    )
    assert "vendor/larkdocio-" in head, "the banner names no openable path for the full history"
    assert "\n## " not in head, (
        "the banner opened a top-level heading — it must be preamble, or a section leaves the "
        "index and the reassembly contract breaks"
    )
    rows = _sections_fn(name)()
    guide_module = importlib.import_module("larkdocio.guide")
    assert len(rows) == min(guide_module.NOTES_WINDOW_SECTIONS[resource],
                            packaged_sources.source_release_count(_REPO, resource))


@pytest.mark.parametrize("name", _WINDOWED)
def test_ld540_the_ROOT_document_keeps_every_section_it_ever_had(name):
    """B1, asserted from the other end: the window RELOCATES history, it does not rewrite it. The
    repository's own copy must still carry strictly more sections than the wheel's, and every
    section the wheel carries must be present in the root **byte for byte** — a truncation that
    edited a cut, dated section would fail here rather than in a review."""
    import pathlib as _pathlib

    guide_module = importlib.import_module("larkdocio.guide")
    resource = _window_resource(name)
    # LD-691 (maintainer ruling 2): the canonical source of the packaged changelog is the PUBLIC changelog
    # (tests/packaged_sources.py); the internal root log is not what the window relocates.
    root_text = packaged_sources.canonical(
        _pathlib.Path(__file__).resolve().parent.parent, resource
    ).read_text(encoding="utf-8")
    levels = guide_module.NOTES_WINDOW_LEVELS[resource]
    root_rows = guide_module._bounded_sections(root_text, levels)
    packaged = _accessor(name)()
    packaged_rows = guide_module._bounded_sections(packaged, levels)
    if packaged_sources.ships_whole(_pathlib.Path(__file__).resolve().parent.parent, resource):
        assert len(root_rows) == len(packaged_rows), (
            f"{resource} ships whole, yet the wheel's copy and its source differ in sections")
    else:
        assert len(root_rows) > len(packaged_rows), (
            f"the root {resource} carries no more sections than the wheel's window — the history "
            "was truncated at the source, which is not what this change does"
        )
    root_by_slug = {row[2]: root_text[row[3]:row[4]] for row in root_rows}
    for row in packaged_rows:
        assert row[2] in root_by_slug, f"{row[2]} ships but is absent from the root document"
        assert packaged[row[3]:row[4]] == root_by_slug[row[2]], (
            f"{row[2]} differs between the shipped window and the root document — the projection "
            "must relocate bytes, never rewrite them"
        )
