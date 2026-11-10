"""THE SECTION-DATE GATE — ``release.sh`` refuses a release-section header dated EARLIER
than the newest date written inside that same section (LD-443, gate f).

Why a gate and not a sentence
-----------------------------
Both release documents already promised, in their own headers, that a section is written
*"at the cut, by whoever cuts the release"*. The promise did not hold: the ``[1.33.0]``
sections carried a header date a full day older than the work described inside them, while
the cut had not been taken at all. A header promise is exactly what failed, so the repair is
a mechanism — the release script now reads the section it is about to tag and refuses a
header date its own body contradicts, naming both dates and the file.

The rule is one-directional on purpose. A section may legitimately quote an OLDER date (a
measurement taken weeks ago, a superseded ruling); it may not be dated BEFORE something it
says happened, because that is a release dated before the changes it contains.

How these tests drive the real script
-------------------------------------
Same harness as ``test_release_gate_notes.py`` — a throwaway git repo, a copy of the real
``scripts/release.sh``, ``--dry-run`` so every preflight runs and nothing mutates, and the
heavy gates stubbed through the script's own documented test seams. The only gate under
test is the new one.

Tier: REGRESSION, unmarked. These pin THIS repository's own artefacts (a section header
against its own body; a shipped document's header text), not a claim about Lark's API —
see ``process/doctrine/conformance-tier.md`` § A.4.
"""
from domain_vocabulary import RETIRED_ID
import pathlib
import re

import pytest

import private_tree  # noqa: E402  (LD-685)
from test_release_gate_notes import (  # the shared sandbox harness
    OTHER,
    TARGET,
    _commit,
    _run_release,
    _sandbox,
    _unmutated,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

SECTION_RE = re.compile(r"^## \[(?P<version>\d+\.\d+\.\d+)\][^\n]*?(?P<date>\d{4}-\d{2}-\d{2})")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _write_dated_doc(path, title, sections):
    """`sections` is a list of (version, header_date, [body dates…])."""
    body = [f"# {title}", ""]
    for version, header_date, inner_dates in sections:
        body += [f"## [{version}] — {header_date}", ""]
        for inner in inner_dates:
            body += [f"- measured {inner} on one tenant.", ""]
        body += ["seeded section", ""]
    path.write_text("\n".join(body), encoding="utf-8")


def _seed(root, *, changelog, notes):
    _write_dated_doc(root / "CHANGELOG.md", "Changelog", changelog)
    _write_dated_doc(root / "RELEASE_NOTES.md", "Release notes", notes)
    _commit(root, "seed dated sections")


# --------------------------------------------------------------------------- #
# AC6 — the gate bites, in each file independently                             #
# --------------------------------------------------------------------------- #

@private_tree.kit
def test_a_correctly_dated_section_passes(tmp_path):
    root = _sandbox(tmp_path, [TARGET, OTHER], [TARGET, OTHER])
    _seed(
        root,
        changelog=[(TARGET, "2026-08-13", ["2026-08-12", "2026-07-01"]), (OTHER, "2026-07-29", [])],
        notes=[(TARGET, "2026-08-13", ["2026-08-13"]), (OTHER, "2026-07-29", [])],
    )
    code, output = _run_release(root)
    assert code == 0, f"the gate refused a correctly dated section:\n{output}"
    assert "all gates green" in output
    _unmutated(root)


@private_tree.kit
def test_a_stale_changelog_header_date_refuses(tmp_path):
    root = _sandbox(tmp_path, [TARGET, OTHER], [TARGET, OTHER])
    _seed(
        root,
        changelog=[(TARGET, "2026-08-11", ["2026-08-12"]), (OTHER, "2026-07-29", [])],
        notes=[(TARGET, "2026-08-13", []), (OTHER, "2026-07-29", [])],
    )
    code, output = _run_release(root)
    assert code != 0, f"a section dated before its own content was tagged:\n{output}"
    assert "CHANGELOG.md" in output, f"the refusal never names the file:\n{output}"
    assert "2026-08-11" in output and "2026-08-12" in output, (
        f"the refusal must name BOTH dates so the cutter knows what to write:\n{output}"
    )
    _unmutated(root)


@private_tree.kit
def test_a_stale_notes_header_date_refuses(tmp_path):
    root = _sandbox(tmp_path, [TARGET, OTHER], [TARGET, OTHER])
    _seed(
        root,
        changelog=[(TARGET, "2026-08-13", []), (OTHER, "2026-07-29", [])],
        notes=[(TARGET, "2026-08-10", ["2026-08-12"]), (OTHER, "2026-07-29", [])],
    )
    code, output = _run_release(root)
    assert code != 0, f"a notes section dated before its own content was tagged:\n{output}"
    assert "RELEASE_NOTES.md" in output, f"the refusal never names the file:\n{output}"
    assert "2026-08-10" in output and "2026-08-12" in output
    _unmutated(root)


@private_tree.kit
def test_correcting_the_header_date_turns_the_gate_green(tmp_path):
    """Red → green on the new gate alone: only the header date changes."""
    root = _sandbox(tmp_path, [TARGET, OTHER], [TARGET, OTHER])
    _seed(
        root,
        changelog=[(TARGET, "2026-08-11", ["2026-08-12"]), (OTHER, "2026-07-29", [])],
        notes=[(TARGET, "2026-08-13", []), (OTHER, "2026-07-29", [])],
    )
    assert _run_release(root)[0] != 0
    _seed(
        root,
        changelog=[(TARGET, "2026-08-12", ["2026-08-12"]), (OTHER, "2026-07-29", [])],
        notes=[(TARGET, "2026-08-13", []), (OTHER, "2026-07-29", [])],
    )
    code, output = _run_release(root)
    assert code == 0, f"correcting the header date did not turn the gate green:\n{output}"


@private_tree.kit
def test_an_older_date_inside_the_section_is_fine(tmp_path):
    """One-directional: a section may quote a measurement older than its own header."""
    root = _sandbox(tmp_path, [TARGET, OTHER], [TARGET, OTHER])
    _seed(
        root,
        changelog=[(TARGET, "2026-08-13", ["2026-01-04", "2025-12-31"]), (OTHER, "2026-07-29", [])],
        notes=[(TARGET, "2026-08-13", ["2026-02-02"]), (OTHER, "2026-07-29", [])],
    )
    code, output = _run_release(root)
    assert code == 0, f"an older in-body date was treated as staleness:\n{output}"


@private_tree.kit
def test_only_the_target_section_is_read(tmp_path):
    """A LATER section's newer dates must not make the target look stale, and an OLDER
    section's own staleness is not this cut's business — history is not swept."""
    root = _sandbox(tmp_path, [TARGET, OTHER], [TARGET, OTHER])
    _seed(
        root,
        changelog=[
            (TARGET, "2026-08-13", ["2026-08-13"]),
            (OTHER, "2026-07-29", ["2026-09-30"]),  # a stale OLD section — not swept
        ],
        notes=[(TARGET, "2026-08-13", []), (OTHER, "2026-07-29", ["2026-09-30"])],
    )
    code, output = _run_release(root)
    assert code == 0, f"the gate read a section it was not tagging:\n{output}"


@private_tree.kit
def test_the_refusal_says_what_to_change(tmp_path):
    root = _sandbox(tmp_path, [TARGET, OTHER], [TARGET, OTHER])
    _seed(
        root,
        changelog=[(TARGET, "2026-08-11", ["2026-08-12"]), (OTHER, "2026-07-29", [])],
        notes=[(TARGET, "2026-08-13", []), (OTHER, "2026-07-29", [])],
    )
    line = [l for l in _run_release(root)[1].splitlines() if l.startswith("release.sh:")][-1]
    assert "header" in line.lower(), line
    assert f"[{TARGET}]" in line, line


# --------------------------------------------------------------------------- #
# AC7 — the runbook that actually RUNS carries the rule                        #
# --------------------------------------------------------------------------- #

@private_tree.kit
def test_the_release_script_runbook_states_the_date_rule():
    header = []
    for line in (REPO_ROOT / "scripts" / "release.sh").read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            header.append(line)
        else:
            break
    text = "\n".join(header).lower()
    assert "cutter" in text, "release.sh's runbook comment never says the date is the cutter's"
    assert "gate f" in text, "release.sh's runbook comment does not enumerate the new gate"


# --------------------------------------------------------------------------- #
# AC5 — both release documents say, in their OWN headers, whose date it is      #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", ["RELEASE_NOTES.md", "CHANGELOG.md"])
def test_the_document_header_says_the_date_is_the_cutters(name):
    text = (REPO_ROOT / name).read_text(encoding="utf-8")
    header = text.split("\n## [", 1)[0]
    lowered = header.lower()
    assert "the date" in lowered and "cutter" in lowered, (
        f"{name}'s own header never says whose the section DATE is — the promise that "
        "already failed once was left as prose about who WRITES the section."
    )
    assert "placeholder" in lowered, (
        f"{name}'s header does not say an un-cut section's date is a placeholder with no "
        "authority, so a worker cannot tell it is safe to leave alone."
    )
    # TRANSFORMED by LD-691 (D-121 (3)), not deleted: the reason stands — the header must name
    # the mechanism that enforces the rule. What changed is the spelling it may use: the public
    # tree does not carry scripts/release.sh, so RELEASE_NOTES.md (and the public changelog) name
    # it as "the release tooling", which a public reader can take at its word rather than follow
    # to a file that is not there. That release.sh really carries the date gate is held above by
    # test_the_release_script_runbook_states_the_date_rule, in this repository.
    assert "release.sh" in header or "release tooling" in lowered, (
        f"{name}'s header states the rule without naming the mechanism that enforces it."
    )


@pytest.mark.parametrize("name", ["RELEASE_NOTES.md", "CHANGELOG.md"])
def test_the_packaged_copy_is_byte_identical(name):
    """The gate this file guards reads the ROOT document, so the packaged copy has to be a
    faithful function of that root or the gate is checking a file nobody ships.

    **LD-540 narrowed the subject and moved the definition, and kept the teeth.** Until v1.37.0
    "faithful" meant *the same bytes as the whole root file*, and this test spelled that
    comparison out itself — a second copy of a rule that lives elsewhere. The wheel now carries a
    recent-N WINDOW, so "faithful" means *byte-identical to the projection of the root file*, and
    the comparison is delegated to the ONE function that defines it
    (``test_shipped_notes.notes_identity_report``) rather than re-implemented here. What this test
    still asserts, unchanged, is that this document's packaged copy is exactly what its root
    produces — including that a release which moved the window and did not regenerate the copy
    reddens right here, before the gate below it is ever reached.
    """
    from test_shipped_notes import notes_identity_report

    report = notes_identity_report(names=(name,))
    assert report == [], f"src/larkdocio/{name} is not the projection of the root {name}: {report}"


# --------------------------------------------------------------------------- #
# AC9 — the consumer file's newest section carries no issue id                  #
# --------------------------------------------------------------------------- #

def test_the_newest_notes_section_carries_no_issue_id():
    text = (REPO_ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    body = text.split("\n## [", 1)[1]
    newest = body.split("\n## [", 1)[0]
    hits = re.findall(r"\bLD-\d+\b|" + RETIRED_ID.pattern, newest)
    assert hits == [], f"issue/private-set ids in the consumer notes' newest section: {sorted(set(hits))}"
