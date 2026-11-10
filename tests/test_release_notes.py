"""THE SHAPE + FILTER GUARD for ``/RELEASE_NOTES.md`` (LD-164).

Why this file exists
--------------------
``CHANGELOG.md`` is the **internal** engineering log — it records issue ids, refactor
passes, test-count movements and board mechanics, because that is what it is for. A
consumer vendoring the wheel had no filtered view of *what changed that affects them*, and
the consequence already happened: the reference consumer was burned across the
1.14.0 → 1.20.0 span. ``RELEASE_NOTES.md`` is the consumer-facing, **filtered** companion.

The failure mode this guard exists to prevent is not "the file is missing" — it is
"**the file silently becomes a second changelog**". So the guard pins three things:

1. **The shape** — one ``#`` title, ``## [X.Y.Z] — YYYY-MM-DD`` per release, and the four
   fixed ``###`` subsections in a fixed order, so the convention is machine-usable
   (a ``--check`` printer can parse it).
2. **The filter, written as criteria in the file's own header** — the include list AND the
   exclude list, each named class present. A future author applies them without
   re-deriving judgement; a partial header cannot pass.
3. **The filter enforced on the file's own content** — the exclusion classes are greppable,
   and they are already enumerated by the consumer-dialect pattern set
   (``tests/consumer_text.py``: issue ids, design-record ids, criterion refs,
   decision/story refs, ladder labels, role names). This guard **reuses that pattern set**
   rather than defining a second one, which is also what makes the later widening of the
   guarded consumer corpus over this file born green.

Plus the back-fill span and the **version-ahead rule**: *at most one* section may sit ahead of
the packaged version — that one is the **cut in progress** (``scripts/release.sh`` runs the
whole suite *before* it bumps the version, and refuses to tag a version with no section, so
the cut state necessarily has one section ahead); **two or more is pre-writing releases that
do not exist** and stays refused. The rule itself — and the full account of the deadlock that
corrected it — lives in :mod:`release_versions`.
"""
from domain_vocabulary import RETIRED_ID_EXAMPLE
import pathlib
import re

import pytest

import packaged_sources  # noqa: E402  (LD-691)
import private_tree  # noqa: E402  (LD-691)

import consumer_text
from consumer_text import dialect_hits
from release_versions import (
    SECTION_RE,
    ahead_refusal,
    packaged_version,
    section_starts,
    version_key,
    versions_ahead,
)

# LD-370 — CONFORMANCE-tier: RELEASE_NOTES.md is a corpus member: every line in it is a consumer promise.
# See process/doctrine/conformance-tier.md (a lens, not a gate).
pytestmark = pytest.mark.conformance

REPO_ROOT = pathlib.Path(consumer_text.REPO_ROOT)
NOTES_PATH = REPO_ROOT / "RELEASE_NOTES.md"
CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"

#: The four fixed subsections, in their fixed order (AC2).
SUBSECTIONS = (
    "### New capabilities",
    "### Behavior changes you can observe",
    "### Upgrade & compatibility",
    "### Known limitations",
)

#: The back-fill span the issue commissions: exactly 1.14.0 .. 1.20.0, no gaps, nothing
#: earlier. 1.14.0 is where the reference consumer's span begins.
BACKFILL_SPAN = ("1.14.0", "1.15.0", "1.16.0", "1.17.0", "1.18.0", "1.19.0", "1.20.0")


#: Ordering only — the version parts carry no semantics (maintainer directive).
_version_key = version_key


@pytest.fixture(scope="module")
def notes():
    assert NOTES_PATH.exists(), (
        "RELEASE_NOTES.md does not exist at the repo root — the consumer-facing, filtered "
        "companion to CHANGELOG.md."
    )
    return NOTES_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def lines(notes):
    return notes.splitlines()


@pytest.fixture(scope="module")
def sections(lines):
    """``[(version, date, body_lines)]`` in file order — fence-aware (see
    :func:`release_versions.section_starts`): a heading quoted inside a fenced block is an
    example, not a release.
    """
    found = section_starts(lines)
    out = []
    for position, (version, date, start) in enumerate(found):
        end = found[position + 1][2] if position + 1 < len(found) else len(lines)
        out.append((version, date, lines[start + 1:end]))
    return out


@pytest.fixture(scope="module")
def header(lines, sections):
    """Everything above the first release section — the filter criteria live here."""
    starts = section_starts(lines)
    first = starts[0][2] if starts else len(lines)
    return "\n".join(lines[:first])


def _project_version():
    return packaged_version(PYPROJECT_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# AC1 — the file exists and is DISTINCT from CHANGELOG.md                       #
# --------------------------------------------------------------------------- #

def test_release_notes_exists_at_the_repo_root(notes):
    assert notes.strip(), "RELEASE_NOTES.md is empty"


@pytest.mark.parametrize("which", ["root", "packaged source"])
def test_release_notes_is_not_a_copy_of_the_changelog(notes, which):
    # LD-691: held against BOTH changelogs where they differ — the root one, and the public
    # changelog the packaged copy is projected from (tests/packaged_sources.py).
    path = (CHANGELOG_PATH if which == "root"
            else packaged_sources.canonical(CHANGELOG_PATH.parent, "CHANGELOG.md"))
    changelog = path.read_text(encoding="utf-8")
    assert notes != changelog, "RELEASE_NOTES.md is a byte copy of CHANGELOG.md"
    # The two files must not share long verbatim runs: a copied paragraph is the smoking
    # gun of a second changelog. Compare non-trivial prose lines.
    def prose(text):
        return {
            line.strip()
            for line in text.splitlines()
            if len(line.strip()) > 60 and not line.strip().startswith("#")
        }

    shared = prose(notes) & prose(changelog)
    assert not shared, (
        "RELEASE_NOTES.md shares verbatim prose lines with CHANGELOG.md — the notes are a "
        f"filtered restatement, not a copy: {sorted(shared)[:3]}"
    )


@private_tree.internal_log
def test_the_changelog_still_carries_its_own_history():
    """AC1 the other way round: the notes did not MIGRATE entries out of the changelog."""
    changelog = CHANGELOG_PATH.read_text(encoding="utf-8")
    for version in BACKFILL_SPAN + ("1.0.0", "1.13.0"):
        assert f"## [{version}]" in changelog, (
            f"CHANGELOG.md lost its ## [{version}] section — the notes are ADDITIVE"
        )


# --------------------------------------------------------------------------- #
# AC2 — the section convention is fixed and machine-greppable                   #
# --------------------------------------------------------------------------- #

def test_exactly_one_h1_title(lines):
    h1s = [line for line in lines if line.startswith("# ") and not line.startswith("##")]
    assert len(h1s) == 1, f"expected exactly one `#` title, found {h1s}"
    assert lines[0].startswith("# "), "the `#` title must open the file"


def test_every_h2_is_a_release_section(lines):
    offenders = [
        line for line in lines
        if line.startswith("## ") and not SECTION_RE.match(line)
    ]
    assert not offenders, (
        "every `##` heading must be a release section `## [X.Y.Z] — YYYY-MM-DD` so the "
        f"convention stays machine-greppable: {offenders}"
    )


def test_heading_nesting_is_well_formed(lines):
    """No `###` before the first `##`, and no heading deeper than `###`."""
    seen_section = False
    for line in lines:
        if SECTION_RE.match(line):
            seen_section = True
        elif line.startswith("### "):
            assert seen_section, f"`{line}` appears before any release section"
        elif re.match(r"^#{4,} ", line):
            raise AssertionError(f"heading deeper than `###` breaks the convention: {line}")


def test_at_least_one_release_section(sections):
    assert sections, "RELEASE_NOTES.md carries no `## [X.Y.Z] — YYYY-MM-DD` section"


@pytest.mark.parametrize("version", BACKFILL_SPAN)
def test_every_section_carries_all_four_subsections_in_order(version, sections):
    """DOCUMENTED CALL (AC2): a subsection with nothing to say is written explicitly as
    "None." rather than omitted — so all four are ALWAYS present, in order. That makes the
    shape unconditionally parseable and proves the author considered each class.
    """
    body = next(body for released, _date, body in sections if released == version)
    found = [line for line in body if line.startswith("### ")]
    assert found == list(SUBSECTIONS), (
        f"section {version} subsections {found} != the fixed order {list(SUBSECTIONS)}"
    )


def test_an_empty_subsection_says_none_explicitly(sections):
    """The documented call, enforced: a subsection is never left blank."""
    for version, _date, body in sections:
        current = None
        content = {}
        for line in body:
            if line.startswith("### "):
                current = line
                content[current] = []
            elif current and line.strip():
                content[current].append(line.strip())
        for subsection, payload in content.items():
            assert payload, (
                f"{version} / {subsection} is blank — write \"None.\" explicitly so an "
                "empty subsection is a decision, not an omission"
            )


def test_sections_are_in_descending_version_order(sections):
    versions = [version for version, _date, _body in sections]
    assert versions == sorted(versions, key=_version_key, reverse=True), (
        f"release sections must read newest-first: {versions}"
    )


def test_section_dates_match_the_changelog(sections):
    """The notes and the changelog agree on when each version was cut.

    TRANSFORMED by LD-691 (maintainer ruling 2), not weakened. The INTERNAL engineering log (the root
    ``CHANGELOG.md`` of the maintainers' copy) must still carry a dated section for EVERY version
    in the notes. The PUBLIC changelog (the root in the public tree, and the packaged copy's
    source here) starts at the last release made before the project was public, so it is held
    to agreement on every version it records — and now runs here too, where before it did not exist."""
    root = CHANGELOG_PATH.parent
    logs = [(packaged_sources.canonical(root, "CHANGELOG.md"), False)]
    if not private_tree.is_public_tree(root):
        logs.append((CHANGELOG_PATH, True))
    for path, complete in logs:
        changelog = path.read_text(encoding="utf-8")
        for version, date, _body in sections:
            expected = re.search(
                rf"^## \[{re.escape(version)}\] — (\d{{4}}-\d{{2}}-\d{{2}})$",
                changelog,
                re.MULTILINE,
            )
            if expected is None and not complete:
                continue
            assert expected, f"{path.name} has no dated section for {version}"
            assert date == expected.group(1), (
                f"{version}: notes say {date}, {path} says {expected.group(1)}"
            )


# --------------------------------------------------------------------------- #
# AC3 — THE RELEVANCE FILTER, WRITTEN AS USABLE CRITERIA IN THE FILE'S HEADER   #
# --------------------------------------------------------------------------- #

#: Every INCLUDE class the issue names, with the phrasings that count as stating it.
INCLUDE_CLASSES = {
    "public symbols": ("public symbol",),
    "CLI flags": ("CLI flag",),
    "observable behavior changes": ("observable behavior change",),
    "new or changed refusals and disclosures": ("refusal", "disclosure"),
    "credential / scope requirements": ("credential", "scope"),
    "dependency adds and pin moves": ("dependency add", "pin move"),
    "known limitations": ("known limitation",),
}

#: Every EXCLUDE class the issue names.
EXCLUDE_CLASSES = {
    "internal refactors": ("internal refactor",),
    "test / CI / board / process work": ("test", "board", "process work"),
    "issue and design-record ids": ("issue id", "design-record id"),
    "role names": ("role name",),
    "wave labels": ("wave label",),
}


def _lowered_header(header):
    """Lowercased with whitespace collapsed — a criterion split across a wrapped line
    still states the criterion, so the check must not be defeated by line breaks."""
    return " ".join(header.lower().split())


def test_the_header_declares_an_include_list_and_an_exclude_list(header):
    lowered = _lowered_header(header)
    assert "include" in lowered, "the header states no INCLUDE criteria"
    assert "exclude" in lowered, "the header states no EXCLUDE criteria"


@pytest.mark.parametrize("label, phrasings", sorted(INCLUDE_CLASSES.items()))
def test_header_include_list_is_complete(label, phrasings, header):
    lowered = _lowered_header(header)
    assert all(phrase.lower() in lowered for phrase in phrasings), (
        f"the header's INCLUDE criteria never name {label!r} — a future author would have "
        "to re-derive the judgement this file exists to record"
    )


@pytest.mark.parametrize("label, phrasings", sorted(EXCLUDE_CLASSES.items()))
def test_header_exclude_list_is_complete(label, phrasings, header):
    lowered = _lowered_header(header)
    assert all(phrase.lower() in lowered for phrase in phrasings), (
        f"the header's EXCLUDE criteria never name {label!r} — without it the file drifts "
        "into a second changelog"
    )


def test_the_header_says_the_file_is_distinct_from_the_changelog(header):
    lowered = _lowered_header(header)
    assert "changelog.md" in lowered, (
        "the header must name CHANGELOG.md and say how this file differs from it"
    )


def test_the_header_states_who_writes_a_section_and_when(header):
    lowered = _lowered_header(header)
    assert "cut" in lowered, (
        "the header must say the section is authored at release-cut time (the duty the "
        "release gate enforces)"
    )


# --------------------------------------------------------------------------- #
# AC4 — the filter is SELF-ENFORCING on its own content                         #
#        (reusing the consumer-dialect pattern set, not a second one)           #
# --------------------------------------------------------------------------- #

def test_the_notes_carry_no_internal_dialect(notes):
    """The excluded identifier classes are exactly the consumer-dialect pattern set."""
    hits = dialect_hits(notes)
    assert hits == [], (
        "RELEASE_NOTES.md speaks this repo's internal dialect — a consumer has only the "
        f"wheel, so none of these resolve: {hits[:12]}"
    )


@pytest.mark.parametrize(
    "probe, expected_class",
    [
        ("the escaping fix (LD-130) changed this", "issue-id"),
        pytest.param(f"the escaping fix ({RETIRED_ID_EXAMPLE})", "private-id",
                     marks=private_tree.dev_record),  # the probe is private (LD-705, LD-707)
        ("the mandatory-detail discipline (AC3)", "ac-ref"),
        ("previews through the S2 resolver", "decision-ref"),
        ("W3 added insert/delete", "ladder-rung"),
        ("the PM-adopted choice", "role-attribution"),
    ],
)
def test_the_reused_guard_bites_on_each_excluded_class(probe, expected_class):
    """Proof the reused pattern set actually detects what AC4 forbids."""
    hits = dialect_hits(probe)
    assert expected_class in {name for name, _matched in hits}, (
        f"{probe!r} was not classified as {expected_class!r} — the reused guard is blind"
    )


def test_the_guard_reddens_when_an_issue_id_is_inserted(notes):
    """Red-proof in situ: the real file plus one injected issue id must fail."""
    injected = notes + "\n- carried over from LD-149\n"
    hits = dialect_hits(injected)
    assert ("issue-id", "LD-149") in hits, (
        "injecting an issue id into the real notes did not redden the guard"
    )


def test_the_guard_does_not_false_positive_on_legitimate_notes_prose():
    """A version string, an A1 range and a real symbol name must all pass."""
    for legitimate in (
        "v1.18.0 added `compose(markdown)`",
        "`Sheet1!A1:D10` still reads the same",
        "`markdown-it-py==4.2.0` is a new runtime dependency",
        "cells render as `Red, Green`",
        "refuses with `MERGED_CELL_TARGET`",
    ):
        assert dialect_hits(legitimate) == [], f"false positive on {legitimate!r}"


# --------------------------------------------------------------------------- #
# AC8 — the back-fill span: exactly 1.14.0 .. 1.20.0                            #
# --------------------------------------------------------------------------- #

def test_the_backfill_covers_the_span_with_no_gaps(sections):
    present = {version for version, _date, _body in sections}
    missing = [version for version in BACKFILL_SPAN if version not in present]
    assert not missing, f"the back-fill span is incomplete — missing {missing}"


def test_nothing_earlier_than_the_span_is_backfilled(sections):
    floor = _version_key(BACKFILL_SPAN[0])
    too_old = [
        version for version, _date, _body in sections if _version_key(version) < floor
    ]
    assert not too_old, (
        f"back-filled earlier than {BACKFILL_SPAN[0]}, which is out of scope: {too_old}"
    )


def test_the_span_records_the_new_runtime_dependency(sections):
    """The pointed case: a runtime dependency APPEARING is exactly what a vendoring
    consumer must be told, and it is the class of change the consumer review stumbled on.
    """
    body = "\n".join(
        next(body for version, _date, body in sections if version == "1.18.0")
    )
    assert "markdown-it-py" in body, (
        "1.18.0 does not name `markdown-it-py`, the dependency promoted to RUNTIME in "
        "that release — the one dependency move in the whole back-filled span"
    )
    upgrade = body.split("### Upgrade & compatibility", 1)
    assert len(upgrade) == 2, "1.18.0 has no Upgrade & compatibility subsection"
    upgrade_body = upgrade[1].split("### ", 1)[0]
    assert "markdown-it-py" in upgrade_body, (
        "the dependency move must be recorded under Upgrade & compatibility, where a "
        "consumer looks before re-vendoring"
    )


def test_every_section_addresses_dependencies_under_upgrade(sections):
    """"Upgrade & compatibility MUST carry every dependency add or pin move" (AC2) — so
    every section states the dependency position, even when it is "no change".
    """
    for version, _date, body in sections:
        text = "\n".join(body)
        upgrade_body = text.split("### Upgrade & compatibility", 1)[1].split("### ", 1)[0]
        assert "depend" in upgrade_body.lower(), (
            f"{version} / Upgrade & compatibility never mentions dependencies — a "
            "consumer cannot tell 'nothing moved' from 'nobody checked'"
        )


# --------------------------------------------------------------------------- #
# The version-ahead rule: AT MOST ONE section ahead — the cut in progress       #
# (LD-169; born as LD-164's AC9 scope fence)                                    #
# --------------------------------------------------------------------------- #

def test_at_most_one_section_ahead_of_the_packaged_version(sections):
    """**THE STANDING RULE: one section ahead is the CUT IN PROGRESS; two or more is
    pre-writing releases that do not exist.**

    Why it is shaped that way — ``scripts/release.sh`` runs **gate b (the whole suite)
    BEFORE it bumps the version** (the bump *is* the release commit, and the script owns it
    atomically), while **gate e refuses to tag a version whose ``## [X.Y.Z]`` sections are
    not already written**. So at every preflight the packaged version is still the OLD one
    and the version being cut is **necessarily one ahead** — a no-section-ahead ceiling makes
    gate b and gate e mutually unsatisfiable and *no release can be cut at all*. That is not
    a loosened guard: the thing LD-164's AC9 actually forbade — **pre-writing releases that
    do not exist yet** — is still refused, from the second version ahead onwards.

    "One ahead" means **any single version greater than the packaged one**, never a computed
    successor: larkdocio's numbers carry **no major/minor semantics (maintainer directive)**, so
    ``1.20.1``, ``1.21.0`` and ``2.0.0`` are all equally legitimate next cuts and successor
    arithmetic would refuse valid ones. See :mod:`release_versions` for the rule itself.
    """
    refusal = ahead_refusal([version for version, _date, _body in sections], _project_version())
    assert refusal is None, refusal


@pytest.mark.parametrize(
    "authored, ok, why",
    [
        ((), True, "nothing ahead — the state between cuts"),
        (("1.20.0",), True, "the packaged version itself is not ahead"),
        (("1.19.0", "1.20.0"), True, "history only"),
        (("1.20.0", "1.21.0"), True, "THE CUT STATE — exactly one ahead"),
        (("1.20.1",), True, "a patch-shaped next cut is one ahead, not a successor mismatch"),
        (("2.0.0",), True, "a major-shaped next cut is equally legitimate (no semantics)"),
        (("1.22.0",), True, "a SKIPPED number is still one single version ahead"),
        (("1.21.0", "1.22.0"), False, "two ahead — the second is a release that does not exist"),
        (("1.20.1", "1.21.0"), False, "two ahead, adjacent numbers — still pre-writing"),
        (("1.21.0", "1.22.0", "1.23.0"), False, "three ahead"),
    ],
)
def test_the_ahead_rule_permits_one_and_refuses_two_or_more(authored, ok, why):
    """The boundary pinned EXACTLY, both ways, against the packaged version 1.20.0 —
    including the cases successor arithmetic would get wrong (``1.20.1``, ``2.0.0``, and the
    deliberate gap ``1.22.0``: all **green**, because a skipped number is a legitimate choice
    when the version carries no meaning beyond monotonic order).
    """
    refusal = ahead_refusal(authored, "1.20.0")
    assert (refusal is None) is ok, f"{authored} should be {'accepted' if ok else 'refused'} — {why}: {refusal}"


def test_the_refusal_explains_the_RULE_not_just_the_violation():
    """A future reader must learn the rule from the failure, not re-derive it."""
    refusal = ahead_refusal(("1.20.0", "1.21.0", "1.22.0"), "1.20.0")
    assert refusal is not None
    assert "1.21.0" in refusal and "1.22.0" in refusal, (
        f"the refusal must name the offending versions: {refusal}"
    )
    assert "1.20.0" in refusal, f"the refusal must name the packaged version: {refusal}"
    assert "at most one" in refusal.lower(), (
        f"the refusal must state the RULE (at most one section ahead — the cut in "
        f"progress), not just the violation: {refusal}"
    )
    # …and it must not name a version that is NOT ahead (1.20.0 appears as the packaged
    # version, never in the offending list).
    assert refusal.count("1.20.0") == 1, f"the packaged version is listed as an offender: {refusal}"


def test_duplicate_headers_for_the_same_ahead_version_count_once():
    """DISTINCT versions ahead is the count that matters — a duplicated header of the one
    version being cut is a different defect (shape/order), not pre-writing.
    """
    assert ahead_refusal(("1.21.0", "1.21.0"), "1.20.0") is None


def test_the_rule_is_read_off_the_real_pyproject_version():
    """The ceiling tracks the PACKAGED version, so the allowance moves with each cut
    instead of being pinned to a number in the test.
    """
    assert re.fullmatch(r"\d+\.\d+\.\d+", _project_version())
    assert versions_ahead(("9.99.0",), _project_version()) == ["9.99.0"]
    assert versions_ahead((_project_version(),), _project_version()) == []


# --------------------------------------------------------------------------- #
# The parse is FENCE-AWARE — a quoted example is not a release section          #
# --------------------------------------------------------------------------- #

def test_the_section_parse_ignores_a_fenced_pseudo_section():
    """SETTLED (LD-169): the parse is **fence-aware**. The file's own header documents the
    section shape, so a future author quoting a *concrete* example inside a ``` fence would
    otherwise have that example counted as a real release — silently reshaping the back-fill
    span, the descending-order check and the version-ahead rule.
    """
    lines = [
        "# Release notes",
        "",
        "```markdown",
        "## [9.9.9] — 2026-01-01",
        "```",
        "~~~",
        "## [8.8.8] — 2026-01-01",
        "~~~",
        "## [1.20.0] — 2026-07-29",
        "real",
    ]
    assert [version for version, _date, _index in section_starts(lines)] == ["1.20.0"]


def test_a_fenced_pseudo_section_cannot_smuggle_a_version_ahead():
    """The two halves composed: a fenced example ahead of the packaged version is not a
    section, so it neither trips the rule nor consumes the one-ahead allowance.
    """
    lines = [
        "# Release notes",
        "```",
        "## [9.9.9] — 2026-01-01",
        "```",
        "## [1.21.0] — 2026-07-29",
        "## [1.20.0] — 2026-07-29",
    ]
    versions = [version for version, _date, _index in section_starts(lines)]
    assert versions == ["1.21.0", "1.20.0"]
    assert ahead_refusal(versions, "1.20.0") is None


def test_a_fence_of_one_kind_does_not_close_a_fence_of_the_other():
    """A ``~~~`` line inside a ``` block is content, not a closing fence — otherwise the
    parse would resume mid-example and read the rest of the block as sections.
    """
    lines = [
        "```",
        "~~~",
        "## [9.9.9] — 2026-01-01",
        "```",
        "## [1.20.0] — 2026-07-29",
    ]
    assert [version for version, _date, _index in section_starts(lines)] == ["1.20.0"]


def test_no_fenced_block_in_the_real_notes_impersonates_a_release_section(lines):
    """Belt to the fence-aware brace: ``scripts/release.sh``'s gate e greps the file with a
    plain ``^## \\[X.Y.Z\\]`` — it is fence-BLIND and is deliberately not changed here
    (LD-169 § Out of Scope). So the two views can only diverge if a fenced block ever carries
    a *concrete* version heading. This pins that to zero on the real file, which keeps gate e
    honest (it can never be satisfied by a quoted example) without touching the script. The
    header quotes the shape as ``## [X.Y.Z] — YYYY-MM-DD`` — placeholders, inline, in no
    fence — so this is green today and stays a deliberate decision if it ever changes.
    """
    fence_blind = [index for index, line in enumerate(lines) if SECTION_RE.match(line)]
    fence_aware = [index for _v, _d, index in section_starts(lines)]
    assert fence_blind == fence_aware, (
        "RELEASE_NOTES.md carries a concrete `## [X.Y.Z]` heading inside a fenced block at "
        f"line(s) {sorted(set(fence_blind) - set(fence_aware))} — the fence-aware guard "
        "would ignore it while gate e's grep would accept it as a real section"
    )


def test_the_release_gate_is_what_forces_the_next_section(header):
    """The header points at the enforcement, so the duty is discoverable from the file.

    TRANSFORMED by LD-691 (D-121 (3)), not deleted: the header still has to name the release gate,
    but as "the release tooling" — the public tree does not carry ``scripts/release.sh``, so a
    path to it is a pointer its reader cannot follow. That the gate exists is the kit's own
    guard's job (``tests/test_release_gate_notes.py``)."""
    assert "release tooling" in header and "refuses to tag" in header, (
        "the header must name the release gate that refuses to tag a version with no "
        "section here"
    )
