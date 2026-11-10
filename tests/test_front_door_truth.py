# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""THE FRONT-DOOR TRUTH GUARDS — the wheel's ``Summary``, keywords, and ``METADATA`` body.

``pyproject.toml``'s ``description`` **is** the wheel's ``Summary``; its ``readme =
"README.md"`` makes the root README the wheel's ``METADATA`` **body**. So every claim in
either is a *shipped* string, and the ones a consumer meets first. They had rotted into a
description of a much older package: writeback "reserved" long after the writer shipped,
no ``sheets``/``write`` keywords, a singular-reader opening with spreadsheets unmentioned
for 170 lines, a pointer calling ``BLOCK_TYPES.md`` a support matrix while that file's
first lines deny carrying one, two real CLI flags undocumented, eight modules missing from
the layout table, and a hard-coded test count stale by more than five times.

Each guard below ties one of those claims to the thing it describes — click's real params,
the real top level of ``src/larkdocio``, the real ``package-data`` table, the real surface
registry, the real requirement list — and each cross-check is **also exercised over
synthetic text**, so the guard is proven to bite in both directions rather than merely
passing today.

The helpers live in ``tests/front_door.py`` (pure functions, no assertions).
"""
import pytest

import consumer_text
import front_door as fd
from doc_prose import missing_phrases, prose
import private_tree  # noqa: E402  (LD-685)

# LD-370 — CONFORMANCE-tier: same door, the truth half: every shipped claim must match the code that ships.
# See process/doctrine/conformance-tier.md (a lens, not a gate).
pytestmark = pytest.mark.conformance


@pytest.fixture(scope="module")
def readme():
    return fd.readme_text()


@pytest.fixture(scope="module")
def project():
    return fd.pyproject()["project"]


# =====================================================================
# AC1 — the wheel Summary tells the truth
# =====================================================================

def test_ac1_summary_drops_the_writeback_reserved_claim(project):
    """The writer shipped many releases ago; "reserved" is the single most-read false word."""
    assert "writeback reserved" not in prose(project["description"]), (
        "pyproject's description is the wheel's Summary — the one line a package index "
        "shows — and it still calls writeback reserved."
    )


def test_ac1_summary_names_every_shipped_surface(project):
    """Reader, writer, Sheets and comments all ship; the Summary names all four."""
    missing = missing_phrases(project["description"], ("reader", "writ", "sheets", "comments"))
    assert not missing, f"the wheel Summary does not mention {missing}: {project['description']!r}"


def test_ac1_summary_stays_one_line_and_summary_sized(project):
    """A Summary is one line. ``METADATA`` headers are line-oriented and a package index
    truncates; a changelog here would be unreadable in both."""
    description = project["description"]
    assert "\n" not in description
    assert len(description) <= 200, f"Summary is {len(description)} chars — too long to read"


# =====================================================================
# AC2 — keywords cover the shipped surfaces (derived from the registry)
# =====================================================================

def test_ac2_keywords_cover_every_shipped_surface(project):
    keywords = {word.lower() for word in project["keywords"]}
    required = fd.required_surface_keywords()
    missing = sorted(required - keywords)
    assert not missing, (
        f"the shipped surface registry demands the keywords {missing}, which the wheel does "
        f"not carry — those surfaces are undiscoverable by keyword search. Have: "
        f"{sorted(keywords)}"
    )


def test_ac2_required_keywords_are_derived_from_the_surface_registry():
    """Not a hand-kept list: the tokens come out of ``capabilities()``' surface ids, so a
    new surface family widens the requirement without anyone editing this file."""
    assert fd.required_surface_keywords() >= {"docx", "sheets", "write", "comments"}


# =====================================================================
# AC3 — the README opens on the real package
# =====================================================================

def test_ac3_first_screenful_names_documents_and_spreadsheets(readme):
    """The constraint: a consumer learns in the first screenful that this package does
    documents **and** spreadsheets (Sheets used to appear only at line 177)."""
    missing = missing_phrases(fd.first_screenful(readme), ("reader", "writer", "sheets", "comments"))
    assert not missing, (
        f"the README's first screenful never mentions {missing} — a consumer deciding "
        f"whether this package does spreadsheets has to read on to find out."
    )


def test_ac3_singular_reader_framing_is_gone(readme):
    assert "single development home for this reader" not in prose(readme), (
        "the opening still frames larkdocio as a reader-only project."
    )


# =====================================================================
# AC4 — the false matrix pointer is deleted (repo-wide sweep)
# =====================================================================

#: The product docs swept for the false association. ``CHANGELOG.md`` / ``ARCHIVE.md`` are
#: excluded on purpose: they are historical records of what was true at the time (the claim
#: WAS true at v1.0.0, before the matrix moved to ``/BLOCKS.md``), and rewriting a changelog
#: entry to match today would be the actual falsification.
_SWEPT_DOCS = ("README.md", "TOOLS.md", "BLOCKS.md", "src/larkdocio/blocks/BLOCK_TYPES.md")


def test_ac4_no_product_doc_calls_block_types_a_support_matrix():
    offenders = {}
    for relative in _SWEPT_DOCS:
        text = (fd.REPO_ROOT / relative).read_text(encoding="utf-8")
        hits = fd.matrix_misattributions(text)
        if hits:
            offenders[relative] = hits
    assert not offenders, (
        f"these lines call BLOCK_TYPES.md a support matrix while that file's own opening "
        f"denies carrying one and points at /BLOCKS.md: {offenders}"
    )


def test_ac4_readme_points_at_the_real_matrix_labelled_repo_only(readme):
    lineno = next(
        (
            index for index, line in enumerate(readme.splitlines(), start=1)
            if "BLOCKS.md" in line and "BLOCK_TYPES" not in line
        ),
        None,
    )
    assert lineno, "the README no longer points at /BLOCKS.md, the real support matrix"
    offenders = [entry for entry in fd.unlabelled_dev_repo_citations(readme) if entry[0] == lineno]
    assert not offenders, (
        f"the /BLOCKS.md pointer at line {lineno} is not labelled "
        f"{fd.DEV_REPO_LABEL!r} — the wheel does not carry that file."
    )


def test_ac4_block_types_is_still_cited_for_what_it_is(readme):
    """The fix is precision, not deletion: the authoring guide keeps its pointer."""
    assert "BLOCK_TYPES.md" in readme


def test_ac4_the_misattribution_detector_bites():
    """Red-proof over synthetic text, including the wrapped form the README really used."""
    assert fd.matrix_misattributions(
        "| `src/larkdocio/blocks/` | The block model and the block-type matrix "
        "([`BLOCK_TYPES.md`](src/larkdocio/blocks/BLOCK_TYPES.md)). |"
    )
    assert fd.matrix_misattributions(
        "See [`src/larkdocio/blocks/BLOCK_TYPES.md`](x) for\nthe block-type → Markdown "
        "support matrix.\n"
    )
    assert not fd.matrix_misattributions(
        "See [`BLOCK_TYPES.md`](x) for how to add a block handler.\n"
    )
    # The CORRECTION shape — matrix and authoring guide named in adjacent sentences —
    # must not be flagged, or the guard would forbid its own fix.
    assert not fd.matrix_misattributions(
        "The support matrix is [`BLOCKS.md`](BLOCKS.md). Authoring mechanics live in\n"
        "[`BLOCK_TYPES.md`](x), which carries no status table.\n"
    )
    # A code symbol that merely contains the filename's stem is not a claim about the file.
    assert not fd.matrix_misattributions(
        "The matrix rows are pinned against `larkdocio.write.encode.CREATABLE_BLOCK_TYPES`.\n"
    )


# =====================================================================
# AC5 — the documented options match click, both directions
# =====================================================================

_DOWNLOAD_MARKER = "options (after the subcommand)"
_GLOBAL_MARKER = "options (before the subcommand)"


def test_ac5_download_options_match_click_exactly(readme):
    documented = fd.documented_options(readme, _DOWNLOAD_MARKER)
    assert documented, "the README's `download` options list could not be parsed"
    undocumented, phantom = fd.two_way_diff(documented, fd.click_options(("download",)))
    assert not undocumented, f"`download` defines {undocumented} — the README never says so"
    assert not phantom, f"the README documents {phantom}, which `download` does not define"


def test_ac5_global_options_match_click_exactly(readme):
    documented = fd.documented_options(readme, _GLOBAL_MARKER)
    assert documented, "the README's global options list could not be parsed"
    undocumented, phantom = fd.two_way_diff(documented, fd.click_options())
    assert not undocumented, f"the CLI group defines {undocumented} — the README omits them"
    assert not phantom, f"the README documents {phantom}, which the CLI group does not define"


def test_ac5_sheets_flags_are_documented_with_a_description(readme):
    """The two flags this issue restores, each with prose a reader can act on."""
    lines = readme.splitlines()
    for flag in ("--deep-read-sheets", "--fidelity-read-sheets"):
        bullet = next((line for line in lines if f"`{flag}`" in line and line.lstrip().startswith("-")), None)
        assert bullet, f"{flag} has no options-list bullet"
        assert "—" in bullet and len(bullet.split("—", 1)[1].strip()) > 20, (
            f"{flag} is listed without a usable description: {bullet!r}"
        )


def test_ac5_option_crosscheck_bites_in_both_directions():
    real = fd.click_options(("download",))
    dropped = set(real) - {"--dump"}
    assert fd.two_way_diff(dropped, real)[0] == ["--dump"]
    invented = set(real) | {"--not-a-flag"}
    assert fd.two_way_diff(invented, real)[1] == ["--not-a-flag"]


def test_ac5_options_parser_reads_a_bullet_list_the_way_the_readme_writes_one():
    parsed = fd.documented_options(
        "**`download` options (after the subcommand):**\n"
        "- `-o`, `--output` — output directory.\n"
        "- `--dump` — also write the raw payload.\n"
        "\n"
        "- `--elsewhere` — a bullet in the NEXT paragraph, not part of the list.\n",
        _DOWNLOAD_MARKER,
    )
    assert parsed == {"-o", "--output", "--dump"}


# =====================================================================
# AC6 — the layout table matches src/larkdocio/, both directions
# =====================================================================

def test_ac6_layout_table_matches_the_real_top_level(readme):
    documented = fd.documented_layout_paths(readme)
    undocumented, phantom = fd.two_way_diff(documented, fd.real_top_level())
    assert not undocumented, (
        f"these modules/packages ship but the package-layout table omits them: "
        f"{undocumented} — a consumer navigating by the table concludes they do not exist."
    )
    assert not phantom, f"the layout table lists {phantom}, which does not exist"


def test_ac6_layout_table_covers_the_surfaces_the_old_table_hid(readme):
    documented = fd.documented_layout_paths(readme)
    # ``capabilities`` is a PACKAGE since LD-244 — the locator follows the code; the claim
    # (this surface has a layout row) is unchanged.
    for path in ("src/larkdocio/sheets/", "src/larkdocio/comments/", "src/larkdocio/capabilities/"):
        assert path in documented, f"{path} is still missing from the layout table"


def test_ac6_layout_crosscheck_bites_in_both_directions():
    real = fd.real_top_level()
    assert fd.two_way_diff(real - {"src/larkdocio/sheets/"}, real)[0] == ["src/larkdocio/sheets/"]
    assert fd.two_way_diff(real, real - {"src/larkdocio/sheets/"})[1] == ["src/larkdocio/sheets/"]


def test_ac6_a_new_module_would_redden_the_layout_guard(readme):
    """The failure mode that let eight modules go missing: adding code, not the row."""
    # LD-246: ``base/`` became REAL (and documented), so the probe moved to a name that is not.
    invented = "src/larkdocio/nosuchpackage/"
    assert invented not in fd.real_top_level(), "the probe is stale; pick a name that is fake"
    documented = fd.documented_layout_paths(readme)
    pretend_real = fd.real_top_level() | {invented}
    assert fd.two_way_diff(documented, pretend_real)[0] == [invented]


# =====================================================================
# AC7 — the test-count claim is unrottable because it is GONE
# =====================================================================

def test_ac7_no_hardcoded_test_count_in_the_readme(readme):
    hits = fd.rottable_test_counts(readme)
    assert not hits, (
        f"the README states a test count {hits} — stale the moment the next test lands. "
        f"Describe the suite and tell the reader to run it instead."
    )


def test_ac7_the_readme_still_tells_the_reader_how_to_run_the_suite(readme):
    missing = missing_phrases(readme, ("pytest",))
    assert not missing, "removing the count must not remove the instruction"


def test_ac7_the_count_detector_bites_on_the_old_sentence():
    assert fd.rottable_test_counts("The default suite is **999 offline tests** — deterministic.")
    assert fd.rottable_test_counts("The default suite is 5621 offline tests.")
    assert not fd.rottable_test_counts("The default suite is a large offline suite; run `pytest`.")
    assert not fd.rottable_test_counts("- Python 3.11+ and larkdocio 1.20.0 are fine.")


# =====================================================================
# LD-649 — the same ban, at the four other places that carried the claim
# =====================================================================

#: The verbatim pre-LD-649 clauses, one per enrolled file (``git show`` of the parent
#: commit is the provenance). These are the RED half: the detector must flag every one,
#: or enrolling the files would be a guard green by construction.
_STALE_SUITE_SIZE_CLAIMS = {
    "process/doctrine/conformance-tier.md":
        "The suite holds ~13.5k cases. LD-370 classified the **obvious families only**;",
    "requirements/CORPUS.md":
        "its argument. The suite has ~13.5k cases doing **two different jobs**: some pin",
    "requirements/CORPUS.md (second)":
        "claim the corpus contains 13.5k assertions about the product when it contains",
    "requirements/CORPUS.md (third)":
        "families only, ~1518 cases as a **floor**, not a census of all 13.5k. `product`",
    "tests/test_conformance_tier.py":
        "# ~13.5k tests, and new tests join by the convention in the doctrine document.",
    ".claude/roles/dev.md":
        "Red/green iteration does not need all 13.4k\n   cases. Use",
    "scripts/verify.sh":
        "bite-red test), and at full-suite size those tests are diluted across 13.4k cases,",
}


@private_tree.citations
@pytest.mark.parametrize("relpath", fd.SUITE_SIZE_FILES)
def test_ld649_no_whole_suite_size_claim_in_the_enrolled_files(relpath):
    """The ban that was scoped to README.md now covers every file that held the claim.

    ``rottable_test_counts``' reasoning — a count is stale the moment the next test lands
    — was general, but only README.md was enrolled, so "the suite holds ~13.5k cases"
    stood at seven occurrences across five files against 20,248 collected.
    """
    path = fd.REPO_ROOT / relpath
    assert path.is_file(), f"enrolled file has moved: {relpath} — fix the list, not this test"
    hits = fd.rottable_suite_size_claims(path.read_text(encoding="utf-8"))
    assert not hits, (
        f"{relpath} states a rounded whole-suite size {hits} — stale the moment the next "
        f"test lands, and unguarded prose is where this exact claim went 49% wrong. Drop "
        f"the figure, or derive it at run time (pytest --collect-only)."
    )


@private_tree.citations
def test_ld649_the_enrolled_set_is_not_empty_and_every_member_exists():
    """The guard is not born vacuous: an empty or stale enrolment list would make the
    parametrized arm above pass by having nothing to say."""
    assert len(fd.SUITE_SIZE_FILES) >= 5, (
        "the whole-suite-size ban enrols fewer files than the five measured to carry the "
        "claim — a shrunk list is a shrunk guard"
    )
    missing = [f for f in fd.SUITE_SIZE_FILES if not (fd.REPO_ROOT / f).is_file()]
    assert not missing, f"enrolled files that no longer exist: {missing}"


@pytest.mark.parametrize("label", sorted(_STALE_SUITE_SIZE_CLAIMS))
def test_ld649_the_detector_bites_on_every_verbatim_stale_clause(label):
    """RED proof, per site: each pre-LD-649 clause is flagged by the live detector."""
    assert fd.rottable_suite_size_claims(_STALE_SUITE_SIZE_CLAIMS[label]), (
        f"the detector cannot see the clause it exists to ban ({label})"
    )


def test_ld649_the_detector_does_not_flag_a_magnitude_that_is_not_about_the_suite():
    """The two halves are both required, so unrelated magnitudes survive: a byte budget,
    a token calibration, a timing. Otherwise the enrolled files could not discuss size."""
    assert fd.rottable_suite_size_claims("32 KiB is about ~8k tokens of session budget.") == []
    assert fd.rottable_suite_size_claims("The tier floor is asserted with >= by this module.") == []
    # …but the same magnitude WITH the population word is a hit, which is the whole point.
    assert fd.rottable_suite_size_claims("The suite is ~8k cases.")


def test_ld649_the_readme_detector_gained_the_magnitude_shape_it_could_not_see():
    """``rottable_test_counts`` is widened, not replaced: it kept the exact-count arm and
    gained the rounded one, so the README ban now covers both forms of the same claim."""
    assert fd.rottable_test_counts("The default suite is 5621 offline tests.")      # kept
    assert fd.rottable_test_counts("The default suite is ~13.5k offline tests.")    # gained
    assert fd.rottable_test_counts("The suite holds 20k tests.")                    # gained
    assert not fd.rottable_test_counts("Run `pytest` for the offline suite.")


# =====================================================================
# AC8 — citations of files the wheel does not carry are LABELLED
# =====================================================================

def test_ac8_packaged_set_is_derived_from_package_data():
    packaged = fd.packaged_doc_paths()
    assert "src/larkdocio/GUIDE.md" in packaged
    assert "src/larkdocio/write/README.md" in packaged
    assert "src/larkdocio/blocks/BLOCK_TYPES.md" in packaged
    assert "BLOCKS.md" not in packaged and "TOOLS.md" not in packaged


def test_ac8_every_citation_of_an_unshipped_file_is_labelled(readme):
    offenders = fd.unlabelled_dev_repo_citations(readme)
    assert not offenders, (
        "the README cites files the wheel does not carry without warning a wheel-only "
        f"consumer ({fd.DEV_REPO_LABEL!r} missing from the section, at or before the "
        f"citation): {offenders}"
    )


def test_ac8_label_guard_bites_on_an_unlabelled_citation():
    unlabelled = "## Section\n\nSee [`TOOLS.md`](TOOLS.md) for the CLI contract.\n"
    assert fd.unlabelled_dev_repo_citations(unlabelled)
    labelled = (
        "## Section\n\nThe files below are in the dev repo, not the wheel.\n\n"
        "See [`TOOLS.md`](TOOLS.md) for the CLI contract.\n"
    )
    assert not fd.unlabelled_dev_repo_citations(labelled)


def test_ac8_a_label_after_the_citation_does_not_excuse_it():
    """Section scope, but only backwards — a citation slipped in above the note is caught."""
    text = (
        "## Section\n\nSee [`TOOLS.md`](TOOLS.md).\n\n"
        "The files above are in the dev repo, not the wheel.\n"
    )
    assert fd.unlabelled_dev_repo_citations(text)


def test_ac8_a_packaged_citation_needs_no_label():
    text = "## Section\n\nSee [`src/larkdocio/GUIDE.md`](src/larkdocio/GUIDE.md).\n"
    assert not fd.unlabelled_dev_repo_citations(text)


def test_ac8_a_new_section_does_not_inherit_the_previous_label():
    text = (
        "## First\n\nThese live in the dev repo.\n\nSee [`TOOLS.md`](TOOLS.md).\n\n"
        "## Second\n\nSee [`BLOCKS.md`](BLOCKS.md).\n"
    )
    offenders = fd.unlabelled_dev_repo_citations(text)
    assert [entry[1] for entry in offenders] == ["BLOCKS.md"]


# =====================================================================
# AC9 — the pin policy is declared, and true
# =====================================================================

#: LD-658 AC7 narrowed the first phrase from "its runtime dependencies" to "its own runtime
#: requirements". Same policy, and the same guard — what moved is the SCOPE the sentence claims:
#: "dependencies" reads as the closure, and the closure is not pinned (see
#: `test_ac7_the_readme_does_not_promise_a_CLOSURE_it_does_not_pin`). The declaration must still
#: be present, deliberate, and tied to the release notes.
_PIN_POLICY_CLAIMS = (
    "pins its own runtime requirements to exact versions",
    "deliberate",
    "release notes",
)


def test_ac9_pin_policy_is_declared_in_the_readme(readme):
    missing = missing_phrases(readme, _PIN_POLICY_CLAIMS)
    assert not missing, (
        f"the README does not declare the dependency-pin policy — missing {missing}. "
        f"A consumer reading exact pins with no stated reason assumes carelessness."
    )


def test_ac9_the_declared_policy_matches_the_requirement_list():
    """The declaration is checked against the requirements, so loosening a pin reddens."""
    loose = fd.loose_runtime_pins()
    assert not loose, (
        f"the README declares exact runtime pins but these are not exact: {loose} — "
        f"either restore the pin or amend the declaration."
    )


def test_ac9_the_pin_check_bites_on_a_loosened_requirement():
    assert fd.loose_runtime_pins({"project": {"dependencies": ["click>=8.3.1"]}}) == ["click>=8.3.1"]
    assert not fd.loose_runtime_pins({"project": {"dependencies": ["click==8.3.1"]}})


# =====================================================================
# AC10 — the front door is dialect-free
# =====================================================================

def test_ac10_front_door_carries_no_internal_dialect(readme, project):
    surfaces = {
        "README.md (the wheel METADATA body)": readme,
        "pyproject description (the wheel Summary)": project["description"],
        "pyproject keywords": " ".join(project["keywords"]),
    }
    hits = {label: consumer_text.dialect_hits(text) for label, text in surfaces.items()}
    offenders = {label: found for label, found in hits.items() if found}
    assert not offenders, (
        f"the front door speaks this repo's internal dialect, which resolves nowhere for a "
        f"consumer: {offenders}"
    )


# =====================================================================
# AC11 — the README *is* the METADATA body (why all of this is shipped)
# =====================================================================

def test_ac11_readme_is_declared_as_the_metadata_body():
    assert fd.pyproject()["project"]["readme"] == "README.md"


# =====================================================================
# The amplifier — assert the BUILT artifact, not just the source
# =====================================================================

def test_built_wheel_metadata_carries_the_corrected_front_door():
    """The deliverable is the wheel, so assert its ``dist-info/METADATA`` — a source-only
    check would miss a packaging regression. Skips when ``dist/`` has no wheel for the
    declared version (a plain checkout); ``python -m build`` arms it."""
    wheel = fd.built_wheel()
    if wheel is None:
        pytest.skip("no built wheel for the declared version in dist/ — run `python -m build`")
    metadata = fd.wheel_metadata(wheel)
    headers = fd.metadata_headers(metadata)
    project = fd.pyproject()["project"]

    assert headers["Summary"] == [project["description"]]
    assert "writeback reserved" not in prose(headers["Summary"][0])
    keywords = {word.strip().lower() for word in ",".join(headers["Keywords"]).split(",")}
    assert fd.required_surface_keywords() <= keywords

    body = metadata.split("\n\n", 1)[1]
    assert not missing_phrases(fd.first_screenful(body, 40), ("sheets", "comments"))
    assert not fd.rottable_test_counts(body)
    assert not fd.matrix_misattributions(body)


# =====================================================================
# LD-658 AC7/AC8 — the pin policy claims only the edges we own, and the
# install path discloses that `dist` can lag.
# =====================================================================

#: The two runtime requirement names this project owns whose OWN dependencies are the closure
#: the softened sentence must not claim. Derived from `pyproject.toml`, never listed.
def _runtime_requirement_names():
    import re

    names = []
    for spec in fd.pyproject()["project"]["dependencies"]:
        base = re.split(r"[\[<>=!;\s]", spec.strip())[0]
        if base:
            names.append(base.replace("_", "-").lower())
    return names


def _unpinned_transitive_edges():
    """``[(package, requirement)]`` for every NON-exact edge in the installed RUNTIME closure.

    Derived by walking installed metadata from this project's own four requirements — never a
    hand-kept list, because a hand-kept one is the thing that goes stale and the number in the
    finding (17 at the pin, on that machine) is environment-dependent by nature. Extras are
    excluded (an ``extra ==`` marker is not part of the closure a consumer inherits), and so are
    the dev-only requirements, which never reach a wheel holder.
    """
    import re
    from importlib.metadata import requires

    seen, unpinned = set(), []
    frontier = list(_runtime_requirement_names())
    while frontier:
        name = frontier.pop()
        if name in seen:
            continue
        seen.add(name)
        try:
            reqs = requires(name) or []
        except Exception:                      # noqa: BLE001 — not installed here
            continue
        for raw in reqs:
            spec, _, marker = raw.partition(";")
            if "extra" in marker:
                continue
            spec = spec.strip()
            if "==" not in spec:
                unpinned.append((name, spec))
            base = re.split(r"[\[<>=!;\s(]", spec)[0]
            if base:
                frontier.append(base.replace("_", "-").lower())
    return unpinned


def test_ac7_the_walk_reaches_the_closure_at_all_so_the_claim_below_is_not_vacuous():
    """A guard that walks nothing proves nothing. The direct requirements must be readable and
    at least one of them must have dependencies of its own."""
    names = _runtime_requirement_names()
    assert names, "pyproject declares no runtime dependencies — the walk has no start"
    from importlib.metadata import requires

    reachable = [n for n in names if (requires(n) or [])]
    assert reachable, (
        f"none of {names} reports any dependency of its own — the closure walk cannot see past "
        f"the direct row, which is exactly the blind spot AC7 is about")


def test_ac7_the_readme_does_not_promise_a_CLOSURE_it_does_not_pin(readme):
    """**LD-658 AC7.** The README **is** the wheel's ``METADATA`` body, and it said a fresh clone
    resolves to the same dependency versions the wheel was tested against *"without needing a
    lockfile of its own"*. That is true of the four rows this project writes and **false of the
    closure**: our requirements' own dependencies carry whatever their authors chose, several of
    them nothing at all — five of them direct children of ``lark-oapi``. The guard meant to hold
    the sentence (``test_ac9_the_declared_policy_matches_the_requirement_list``) reads only the
    four direct rows, so it could never have caught this.

    The count is deliberately **not** asserted: it is a property of the installed environment,
    and this repo's staleness doctrine says a number in a claim is derived, dated, or not
    stated. What is asserted is the *sign* — the closure is not fully pinned — which is the only
    thing the sentence has to stop claiming.
    """
    unpinned = _unpinned_transitive_edges()
    flat = " ".join(readme.split())

    if unpinned:
        assert "without needing a lockfile of its own" not in flat, (
            "the README still promises a lockfile-free reproducible resolve while the installed "
            f"runtime closure carries non-exact edges, e.g. {unpinned[:3]}"
        )
        # ...and it must say so rather than merely dropping the overclaim.
        for phrase in ("does not pin the transitive closure", "lockfile in your own project"):
            assert phrase in flat, (
                f"the README drops the overclaim without disclosing the limit: {phrase!r} is "
                f"missing")
    else:
        raise AssertionError(
            "the whole runtime closure is now exactly pinned — the softened README sentence is "
            "now weaker than the truth, and this guard is the place to strengthen it")


def test_ac7_the_four_rows_WE_own_are_still_the_ones_claimed(readme):
    """The softened claim is about a countable set, so it is held against that set — the policy
    still has to be true of everything this project itself writes."""
    assert not fd.loose_runtime_pins(), "a direct row lost its exact pin"
    flat = " ".join(readme.split())
    assert "its own runtime requirements to exact versions" in flat, (
        "the narrowed claim must still say WHAT is pinned, or it discloses a limit without "
        "stating the policy")


#: The heading of the section the pin policy lives in. **Both arms below are scoped to it**, and
#: that scoping is the whole instrument: the names ``lark-oapi`` &c. appear in several other
#: places in a 600-line README, so a whole-file search finds them however the pin paragraph is
#: edited — which is precisely the blind spot LD-658 filed against
#: ``test_ac9_…LOG_STREAM…`` (a whole-file ``find("stderr")``). The first draft of this guard had
#: the same bug and passed both its own red-watch mutations; scoping is what made it bite.
_PIN_SECTION_HEADING = "### Dependencies — exact pins, deliberately"


def _pin_policy_section(readme):
    """The pin-policy section's own text — heading to the next heading of the same level."""
    lines = readme.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == _PIN_SECTION_HEADING)
    end = next((i for i, line in enumerate(lines[start + 1:], start + 1)
                if line.startswith("### ") or line.startswith("## ")), len(lines))
    return " ".join(" ".join(lines[start:end]).split())


def test_ac7_the_pin_section_is_LOCATABLE_so_the_arms_below_are_not_vacuous():
    """A section-scoped guard whose section cannot be found checks nothing."""
    section = _pin_policy_section(fd.readme_text())
    assert _PIN_SECTION_HEADING in section
    assert len(section) > 400, f"the pin section is suspiciously short: {len(section)} chars"


def test_ac7_the_claim_NAMES_its_antecedent_and_the_names_are_held_BOTH_ways(readme):
    """**LD-658 fix round, defect 5.** The paragraph said *"the exact pins above are not a
    guarantee about the whole graph"* while **"the pins above" referred to nothing**: no pin
    literal appears in this file at all (grep for ``lark-oapi==`` and friends returns zero). A
    sentence that points at an antecedent it does not have is unfollowable, which is the defect
    class this whole issue exists to remove — so the requirements are now NAMED, and the naming
    is held against ``pyproject.toml`` **in both directions**, *within the section*.

    Names, not versions, and deliberately: a version literal here would be a second copy of the
    pin, and a copy is what drifts (it is also what ``tests/test_version_bump_tolerance.py``
    exists to prevent). The versions ride the wheel's own ``Requires-Dist`` headers, which the
    paragraph tells the reader to read.

    The prose states **no count**, so nothing here has to derive one — and the set equality below
    is what makes adding or removing a requirement redden rather than silently falsifying a
    number somebody might reintroduce.
    """
    section = _pin_policy_section(readme)
    declared = set(_runtime_requirement_names())
    assert declared, "pyproject declares no runtime dependencies"

    # Scoped to the ENUMERATING SENTENCE, not the section — third tightening, and the last one
    # that mattered. `lark-oapi` is mentioned three times in this section (the policy, the
    # closure caveat, the DeprecationWarning note), so a section-wide presence test stays green
    # while the enumeration itself is gutted. Only the sentence that IS the antecedent counts.
    marker = "Those requirements are "
    assert section.count(marker) == 1, (
        f"expected exactly one enumerating sentence introduced by {marker!r}; found "
        f"{section.count(marker)} — the antecedent must have one unambiguous home")
    enumeration = section.split(marker, 1)[1].split(".")[0]

    missing = sorted(name for name in declared if f"`{name}`" not in enumeration)
    assert not missing, (
        f"the pin policy's enumerating sentence does not name {missing} (it reads "
        f"{enumeration!r}) — either name every requirement the policy claims to cover, or stop "
        f"referring to 'the requirements named above'")

    # ...and the other direction: it may not advertise a requirement this project does not have.
    import re

    stated = {m.group(1) for m in re.finditer(r"`([a-z0-9][a-z0-9._-]+)`", enumeration)}
    phantom = sorted(n for n in stated & _KNOWN_PACKAGE_WORDS if n not in declared)
    assert not phantom, (
        f"the pin-policy section names {phantom} as a pinned runtime requirement of this "
        f"project, and pyproject does not declare it")

    # The antecedent must be reachable from the sentence that leans on it, IN THIS SECTION.
    assert "requirements named above" in section, (
        "the closure sentence lost its antecedent again — it must point at the named list")
    for spelling in (f"{name}==" for name in declared):
        assert spelling not in section, (
            f"{spelling!r} froze a version into the wheel's METADATA body; name the "
            f"requirement and let Requires-Dist carry the version")


#: Package names this repo has ever declared as a RUNTIME requirement, so the reverse arm above
#: can tell "a package we no longer depend on is still advertised" from the many other
#: backticked words in the section. Historical, hence hand-kept and small; the FORWARD arm is
#: the derived one and is what catches an addition.
_KNOWN_PACKAGE_WORDS = {
    "lark-oapi", "click", "python-dotenv", "markdown-it-py", "mdurl",
    "pytest", "pytest-xdist", "build", "mutmut", "setproctitle", "tzdata",
}


def test_ac8_the_install_path_discloses_that_dist_can_lag(readme):
    """**LD-658 AC8.** Step 0 sends consumers to clone the ``dist`` branch and offers
    build-from-tag as an alternative, but never said ``dist`` **can be stale** — while
    ``consumers/update_larkdocio.sh`` knows it can (its own header: *"If ``dist`` is absent … or
    stale … it FALLS BACK"*, and *"The tag remains AUTHORITATIVE for every version"*). This repo
    watched ``dist`` serve the previous release's wheel for over 70 minutes.

    Held against the script's own words, so the README cannot say something the tool contradicts.
    """
    from pathlib import Path

    script = (Path(__file__).resolve().parents[1]
              / "consumers" / "update_larkdocio.sh").read_text(encoding="utf-8")
    assert "AUTHORITATIVE" in script, (
        "the script no longer states which side wins; this guard's premise is gone")

    flat = " ".join(readme.split())
    assert "dist" in flat
    assert "authoritative" in flat.lower(), (
        "step 0 offers two sources of the wheel and does not say which one wins when they "
        "disagree — a consumer who cloned `dist` mid-release installs the previous version and "
        "has no way to know")
