"""LD-592 — ``guide.py``'s version addressing (A6), its out-of-window refusal wording (B2)
and the unconditional plural in the same function family (C1c).

Three defects that sit in one file and are really two stories:

* **A6 / AC1-AC2 — the wheel parses a bare version well enough to VOUCH for it and not well
  enough to RESOLVE it.** A dated release heading slugs to ``1-43-0-2026-08-31``, so the bare
  ``1.43.0`` a consumer actually types matched nothing and got the generic unknown-section
  refusal — the release just cut being the one a consumer asks about first, and the one that
  could not name itself.
* **B2 / AC3-AC6 — the out-of-window refusal asserted what it cannot check.** It opened with
  *"{v} is a real release"* while the wheel carries only a window, so the assertion is
  uncheckable from inside the wheel and a fabricated in-range version was vouched for. Every
  cut mints a fresh band of never-existed strings, so the set grows with no authored change.
  This is the shape ``src/larkdocio/write/apply.py`` calls the *lying-refusal* defect, and the
  project had already written the argument down at
  ``tests/test_packaged_doc_section_access.py``'s unknown-name mirror assertion — which calls
  this exact wording *"a lie"* while fencing only the unknown-name arm. This suite extends that
  reason to the arm it was never applied to.
* **C1c / AC7 — an unconditional plural**, at six sites, two of which write into the packaged
  wheel's window banner. Fixed as a class through the one ``_agreeing`` helper.

Every version in here is **derived** from the shipped document or from the packaging metadata,
never typed, so nothing in this file moves when the window rolls.
"""
import re

import pytest

import larkdocio
from larkdocio.guide import (
    CHANGELOG_RESOURCE,
    CHANGELOG_SECTION_LEVELS,
    NOTES_WINDOW_SECTIONS,
    RELEASE_NOTES_RESOURCE,
    _bounded_sections,
    _index_text,
    _out_of_window_refusal,
    _release_version,
    _section_text,
    _version_tuple,
    notes_window_banner,
)
from test_shipped_notes import REPO_ROOT

#: ``{name: (accessor, sections helper, window resource)}`` — the two WINDOWED documents, the
#: only two that grew the version arm and the out-of-window refusal.
_WINDOWED = {
    "release_notes": (larkdocio.release_notes, larkdocio.release_notes_sections,
                      RELEASE_NOTES_RESOURCE),
    "changelog": (larkdocio.changelog, larkdocio.changelog_sections, CHANGELOG_RESOURCE),
}
_NAMES = sorted(_WINDOWED)

#: The documents that are NOT windowed — AC2's "nothing else changes" subjects.
_UNWINDOWED = {
    "guide": larkdocio.guide,
    "writer_brief": larkdocio.writer_brief,
    "lark_setup": larkdocio.lark_setup,
}


def _packaged_version() -> str:
    """The version ``pyproject.toml`` currently packages — read, never typed, the same way
    ``test_ld508_…::test_ac5_no_second_section_was_opened_ahead_of_the_packaged_version``
    reads it."""
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version = "([^"]+)"', text, re.M).group(1)


def _window_versions(name) -> list:
    return [_release_version(row["slug"]) for row in _WINDOWED[name][1]()]


def _fabricated_out_of_window_version(name) -> str:
    """A version that (a) parses as older than the window and (b) this project never cut.

    Derived: one minor below the window's own oldest, with a **non-zero patch**. The evidence
    that the patch position is a spelling this project has never used is the tag set itself —
    asserted below in ``test_ac3_the_fabricated_version_really_never_shipped`` — so this is a
    plausible, in-range string a caller could type and the wheel has no way to check.
    """
    oldest = min(_window_versions(name), key=_version_tuple)
    major, minor, _patch = (int(part) for part in oldest.split("."))
    return f"{major}.{minor - 1}.1"


# --------------------------------------------------------------------------- #
# AC1 — a release INSIDE the window resolves by its bare version.               #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", _NAMES)
def test_ac1_every_windowed_release_resolves_by_its_BARE_version(name):
    """For every section the document reports, the bare version parsed out of its slug fetches
    byte-identical text to the slug and to the heading. No literal version appears here."""
    accessor, sections_fn, _resource = _WINDOWED[name]
    rows = sections_fn()
    assert rows, f"{name} reports no sections"
    for row in rows:
        version = _release_version(row["slug"])
        assert version, f"{name}: {row['slug']!r} does not parse as a release"
        by_version = accessor(section=version)
        assert by_version == accessor(section=row["slug"]), version
        assert by_version == accessor(section=row["heading"]), version
        assert by_version.startswith("## " + row["heading"])


@pytest.mark.parametrize("name", _NAMES)
def test_ac1_the_version_pyproject_PACKAGES_resolves_by_its_bare_spelling(name):
    """The release just cut is the one a consumer asks about first."""
    packaged = _packaged_version()
    assert packaged in _window_versions(name), (
        f"{name}: the packaged version {packaged} is not in the window "
        f"{_window_versions(name)} — the window must carry what the wheel says it is"
    )
    assert _WINDOWED[name][0](section=packaged).startswith("## [")


@pytest.mark.parametrize("name", _NAMES)
def test_ac1_the_bare_version_arm_is_case_and_whitespace_tolerant_like_the_others(name):
    accessor = _WINDOWED[name][0]
    version = _window_versions(name)[0]
    assert accessor(section=f"  {version}  ") == accessor(section=version)


# --------------------------------------------------------------------------- #
# AC2 — the version arm is a FALLTHROUGH and nothing else changes.              #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", _NAMES)
def test_ac2_an_exact_slug_or_heading_still_wins_before_the_version_arm(name):
    """The new arm runs only after both exact matches miss, so a document whose heading IS a
    version spelling keeps answering with that section and not with a version lookup."""
    accessor, sections_fn, _resource = _WINDOWED[name]
    for row in sections_fn():
        assert accessor(section=row["slug"]).startswith("## " + row["heading"])
        assert accessor(section=row["heading"].upper()) == accessor(section=row["slug"])


@pytest.mark.parametrize("name", sorted(_UNWINDOWED))
def test_ac2_a_NON_release_document_still_gives_the_plain_unknown_refusal(name):
    """``guide()`` / ``writer_brief()`` / ``lark_setup()`` are behaviourally unchanged: their
    headings do not parse as versions, so a version-shaped name finds nothing and gets the
    plain unknown-section refusal — never the windowed one."""
    with pytest.raises(ValueError) as excinfo:
        _UNWINDOWED[name](section=_packaged_version())
    message = str(excinfo.value)
    assert message.startswith("unknown section"), message
    assert "out-of-window" not in message and "carries a WINDOW" not in message, message


# --------------------------------------------------------------------------- #
# AC3 / AC4 — the out-of-window refusal asserts nothing it cannot check.        #
# --------------------------------------------------------------------------- #

def _every_version_ever_cut() -> set:
    """Every release this project has cut, read out of the **ROOT** changelog — the document
    that keeps every section it ever had (the packaged copy is a window; the root is not).

    **Read from the tree, never from live git.** ``tests/test_no_test_reads_live_git.py``
    forbids a test shelling out to git against this checkout, and the tree carries the same
    evidence: the release script refuses to tag a version that has no section in both release
    documents, so the root changelog's section list *is* the tag list.
    """
    from release_versions import section_starts

    text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    return {version for version, _date, _line in section_starts(text.splitlines())}


def test_ac3_the_fabricated_version_really_never_shipped():
    """The evidence behind the derivation: **no** release this project cut OLDER than a
    window carries a non-zero patch, so an ``x.y.1`` spelling below the window is a version it
    never released — while sitting squarely inside the published 1.x range, which is exactly
    why a caller has no external cue that a vouching refusal is wrong.

    LD-718 narrowed the evidence, not the reason: the first patch release (inside both windows)
    made "no release ever carries a non-zero patch" false, and the derivation only ever reads
    BELOW the window, so that is where the evidence is now checked."""
    cut = _every_version_ever_cut()
    assert cut, "no release sections found — the derivation's evidence cannot be checked"
    for name in _NAMES:
        oldest = min(_window_versions(name), key=_version_tuple)
        older_patches = sorted(v for v in cut if not v.endswith(".0")
                               and _version_tuple(v) < _version_tuple(oldest))
        assert older_patches == [], (
            f"a release older than {name}'s window carries a non-zero patch "
            f"({older_patches}) — the fabricated-version derivation must move"
        )
        fabricated = _fabricated_out_of_window_version(name)
        assert fabricated not in cut
        for relative in ("CHANGELOG.md", "RELEASE_NOTES.md"):
            text = (REPO_ROOT / relative).read_text(encoding="utf-8")
            assert f"## [{fabricated}]" not in text, relative


#: The claims the refusal must not make about a version it cannot check. Each is a phrase that
#: only an existence check could earn.
_UNEARNED_CLAIMS = (
    "is a real release",
    "is a release",
    "really exists",
    "does exist",
    "was released",
    "shipped",
    "it was not deleted",
    "it was not renamed",
)


@pytest.mark.parametrize("name", _NAMES)
def test_ac3_the_refusal_VOUCHES_for_nothing_it_cannot_check(name):
    """AC3, the binding one. A fabricated in-range version takes the out-of-window branch — and
    the message must claim nothing about whether it exists. *Some message is produced* does not
    satisfy this; the absence of the false assertion is the AC."""
    fabricated = _fabricated_out_of_window_version(name)
    with pytest.raises(ValueError) as excinfo:
        _WINDOWED[name][0](section=fabricated)
    message = str(excinfo.value)
    lowered = message.lower()
    for claim in _UNEARNED_CLAIMS:
        assert claim not in lowered, (
            f"the refusal vouches for {fabricated}, which this wheel cannot check: "
            f"{claim!r} in {message}"
        )


@pytest.mark.parametrize("name", _NAMES)
def test_ac4_and_it_still_tells_the_caller_everything_TRUE_it_can(name):
    """Removing the unearned claim may not cost the caller anything the wheel can substantiate,
    and the truthful clause LEADS. Checked for a fabricated name and for a real one."""
    accessor, sections_fn, _resource = _WINDOWED[name]
    rows = sections_fn()
    oldest = min(_window_versions(name), key=_version_tuple)
    newest = max(_window_versions(name), key=_version_tuple)
    major, minor, patch = (int(part) for part in oldest.split("."))
    real_but_older = f"{major}.{minor - 1}.{patch}"
    for asked in (_fabricated_out_of_window_version(name), real_but_older):
        with pytest.raises(ValueError) as excinfo:
            accessor(section=asked)
        message = str(excinfo.value)
        assert message.startswith("out-of-window section"), message
        assert "unknown section" not in message, message
        assert asked in message, message
        assert oldest in message and newest in message, message
        assert "git history" not in message.lower() and "git log" not in message.lower()
        assert f"{name}_sections" in message and f"'{name}()'" in message, message
        opening = f"out-of-window section {asked!r}: "
        if len(rows) < NOTES_WINDOW_SECTIONS[_WINDOWED[name][2]]:
            # LD-691 (maintainer ruling 2): this copy is the WHOLE document (the public changelog starts
            # at the last release made before the project was public). Everything TRUE it can say: that it is whole, how
            # many releases it records, and where older history really lives — and it LEADS.
            assert f"{len(rows)} releases" in message, message
            assert "release_notes()" in message, message
            assert message.startswith(
                opening + "this copy carries every release this document records"), message
        else:
            assert f"newest {len(rows)} releases" in message, message
            assert "not the whole history" in message, message
            assert re.search(r"vendor/larkdocio-(CHANGELOG|RELEASE_NOTES)\.md", message), message
            # The truthful clause LEADS: the first thing after the opening is what this copy
            # carries — not a claim about the name that was asked for.
            assert message.startswith(opening + "this wheel carries a WINDOW"), message


def test_ac5_the_docstring_stops_describing_the_removed_claim():
    """AC5 — the docstring said the message *"says … that the section exists"*. That sentence
    described exactly the claim AC3 removes, so it is corrected in the same change."""
    doc = _out_of_window_refusal.__doc__
    assert "that the section exists" not in doc, doc
    assert "cannot check" in doc or "cannot verify" in doc, doc


# --------------------------------------------------------------------------- #
# AC7 — the plural is fixed as a CLASS, at every site, through one mechanism.   #
# --------------------------------------------------------------------------- #

_ONE_SECTION_NOTES = "preamble\n\n## [1.2.0] — 2026-01-01\n\nthe only release\n"
_ONE_SECTION_GUIDE = "preamble\n\n## Only Section\n\nthe only body\n"


def test_ac7_the_unknown_section_refusal_reads_grammatically_at_one_section():
    """Site 1 — ``_section_text``'s unknown-name refusal."""
    with pytest.raises(ValueError) as excinfo:
        _section_text(_ONE_SECTION_GUIDE, "no-such-thing")
    message = str(excinfo.value)
    assert "the 1 it has is:" in message, message
    assert "the 1 it has are" not in message, message


def test_ac7_the_window_banner_reads_grammatically_at_one_section():
    """Sites 2 and 3 — the banner, which writes **into the packaged wheel**."""
    banner = notes_window_banner(CHANGELOG_RESOURCE, ("1.2.0",), "1.1.0")
    assert "newest 1 release," in banner, banner
    assert "lists the 1 release this copy" in banner, banner
    assert "1 releases" not in banner, banner


def test_ac7_the_out_of_window_refusal_reads_grammatically_at_one_section():
    """Sites 4 and 5 — count and verb in the same sentence."""
    rows = _bounded_sections(_ONE_SECTION_NOTES, CHANGELOG_SECTION_LEVELS)
    message = _out_of_window_refusal(
        "1.1.0", "1.1.0", rows, CHANGELOG_RESOURCE, "changelog_sections", "changelog()",
    )
    assert message is not None
    # LD-691: one section is fewer than the window, so the copy is WHOLE and the refusal says so
    # — the window form at one section is no longer reachable. Same grammar, held on this form.
    assert "every release this document records — 1 release, 1.2.0 —" in message, message
    assert "The 1 release this copy does carry is:" in message, message
    assert "1 releases" not in message, message


def test_ac7_the_guide_index_reads_grammatically_at_one_section():
    """Site 6 — the index header."""
    rendered = _index_text(_ONE_SECTION_GUIDE)
    assert "1 section.\n" in rendered, rendered
    assert "1 sections" not in rendered, rendered


@pytest.mark.parametrize("name", _NAMES)
def test_ac7_at_n_greater_than_one_the_emitted_bytes_are_UNCHANGED(name):
    """The other half of AC7, and why the packaged banner does not churn from this AC alone:
    the plural forms are exactly what they were at every count above one."""
    accessor, sections_fn, resource = _WINDOWED[name]
    # LD-691: the count is what this copy really carries — the window, or fewer when the source
    # is shorter than its window (the public changelog) — and must still be above one here.
    versions = _window_versions(name)
    count = len(versions)
    assert count > 1
    banner = notes_window_banner(resource, tuple(versions), "0.0.0")
    assert f"newest {count} releases," in banner
    assert f"lists the {count} releases this copy" in " ".join(
        line.lstrip("> ") for line in banner.splitlines())
    with pytest.raises(ValueError) as excinfo:
        accessor(section=_fabricated_out_of_window_version(name))
    message = str(excinfo.value)
    if count < NOTES_WINDOW_SECTIONS[resource]:
        assert f"— {count} releases, " in message, message
    else:
        assert f"newest {count} releases (" in message
    assert f"The {count} releases this copy does carry are:" in message
