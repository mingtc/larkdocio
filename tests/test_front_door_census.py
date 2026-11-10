"""THE OPENING CENSUS AND THE GUIDE-SIZE LITERAL — the two front-door claims nothing pinned.

``tests/test_front_door_doctrine.py`` already holds the wheel ``Summary`` against the
surfaces ``capabilities()`` reports. The README's **opening paragraph** — the census a reader
meets before the Summary, before the router, before anything — was held against nothing, and
it rotted exactly the way the Summary once did: it still said drive was *folder read* after
three drive WRITE surfaces shipped, and it never named contacts at all in the half of the
document a wheel-only consumer reads. The same is true of the guide's size, stated as a hard
``200 KB`` in four places while the document had grown past 500 KiB.

**Why this is a separate module rather than more tests in the doctrine file.** That file
carries a module-level ``pytest.mark.conformance``. These guards pin one internal projection
(the README census) against another (``capabilities()``) and ban a literal — a rewrite from
the corpus may legitimately word the census differently, so the tier question answers *merely
different*, not *product wrong*. Regression-tier is therefore correct
(``process/doctrine/conformance-tier.md`` § A.1/A.4), and a mark cannot be removed per-test
from a module-level ``pytestmark``. Same helpers, same derived-from-code discipline, no mark.
"""
import front_door as fd


# --------------------------------------------------------------------------- #
# The census ↔ capabilities(), both directions                                  #
# --------------------------------------------------------------------------- #

def test_the_opening_census_names_every_surface_family_capabilities_reports():
    gaps = fd.census_gaps()
    assert not gaps, (
        f"the README's opening paragraph — the first product claim anyone reads — never says "
        f"{gaps}, so a reader deciding whether this library can do that thing concludes it "
        f"cannot. Census: {fd.opening_census()!r}"
    )


def test_dropping_a_surface_word_from_the_census_reddens_PER_WORD():
    """Proven red one word at a time, so the guard cannot be satisfied by a census that
    happens to mention a single surface."""
    census = fd.opening_census()
    assert census, "the README has no opening paragraph to check"
    for word in sorted(fd.required_surface_keywords()):
        if word.lower() not in census.lower():
            continue
        crippled = census.lower().replace(word.lower(), "thing")
        assert word in fd.census_gaps(crippled, {word}), (
            f"removing {word!r} from the census did not redden the check"
        )


def test_the_census_check_is_WORD_LEVEL_and_does_not_dictate_the_prose():
    """The deliberate limit: reword the census entirely, keep the surface words, still green.
    The guard owes the reader coverage, not a house style."""
    reworded = (
        "A Lark kit: docx to Markdown, gated writes, sheets both ways, base tables and "
        "their schema, drive folders with their versions, access and files, comments, contacts."
    )
    assert fd.census_gaps(reworded) == []


def test_the_census_may_not_advertise_a_surface_that_does_not_exist():
    phantoms = fd.census_phantom_families()
    assert not phantoms, (
        f"the opening census bolds {phantoms}, which name no surface capabilities() reports "
        f"and no recorded prose alias (front_door.CENSUS_ALIASES)"
    )


def test_the_phantom_check_bites_on_an_invented_surface():
    assert fd.census_phantom_families("Six surfaces ship: the **telepathy** engine.") == [
        "telepathy"
    ]


def test_the_phantom_check_does_not_bite_on_a_recorded_prose_alias():
    assert fd.census_phantom_families("the **reader** and the **writer**") == []


def test_the_census_helper_reads_the_paragraph_and_not_the_whole_readme():
    census = fd.opening_census()
    assert census.startswith("A Python toolkit for Lark"), census[:60]
    assert "Start here" not in census


# --------------------------------------------------------------------------- #
# The guide-size literal                                                        #
# --------------------------------------------------------------------------- #

def test_no_front_door_file_states_the_guide_size_as_a_hard_number():
    offenders = fd.guide_size_literal_offenders()
    assert not offenders, (
        "a hard KB size for the packaged guide drifts silently — it read 200 KB while the "
        f"document was past 500 KiB. State the magnitude in prose instead. Offenders: "
        f"{offenders}"
    )


def test_the_literal_guard_bites_on_the_shape_that_shipped(tmp_path):
    doc = tmp_path / "door.md"
    doc.write_text("It is over 200 KB as one string.\n", encoding="utf-8")
    # An absolute path wins the ``REPO_ROOT / rel`` join, so the real reader is exercised.
    offenders = fd.guide_size_literal_offenders([str(doc)])
    assert [(lineno, line) for _p, lineno, line in offenders] == [
        (1, "It is over 200 KB as one string.")
    ]
    assert fd.GUIDE_SIZE_LITERAL.search("about 511KB one string")
    assert not fd.GUIDE_SIZE_LITERAL.search("hundreds of KB as one string")


def test_the_guide_size_DEBT_table_names_only_files_that_still_carry_the_literal():
    """The debt table cannot outlive its debt: when LD-441 de-numbers the guide, this
    reddens until the entry is deleted."""
    stale = [
        path
        for path in fd.GUIDE_SIZE_DEBT
        if not fd.guide_size_literal_offenders([path])
    ]
    assert not stale, (
        f"{stale} no longer carries a hard guide-size literal — delete the "
        f"front_door.GUIDE_SIZE_DEBT entry with the fix, not in a later sweep"
    )


def test_the_debt_TABLE_IS_EMPTY_and_the_guide_moved_into_the_guarded_scope():
    """TRANSFORMED, not deleted (`supersession.md` § A.1). The original reason stands: the
    guide's own copy of the literal was owned by another issue and had to be *recorded* rather
    than silently tolerated. LD-441 paid that debt, so the conclusion moves — the file is no
    longer an exception in a table, it is inside the scope the guard reads, which is a
    strictly stronger position than the one this test used to pin.

    The dated release records stay out, for the unchanged reason: their entries are records of
    what was true at a release, not current claims.
    """
    assert "src/larkdocio/GUIDE.md" in fd.GUIDE_SIZE_SCOPE
    assert not fd.GUIDE_SIZE_DEBT, (
        f"a new debt entry appeared: {fd.GUIDE_SIZE_DEBT} — the table is a ledger of owned "
        "exceptions, and an entry needs the issue that owns it")
    for record in ("CHANGELOG.md", "RELEASE_NOTES.md"):
        assert record not in fd.GUIDE_SIZE_SCOPE


def test_the_literal_exemption_is_a_MEASUREMENT_of_something_else_not_a_loophole():
    """LD-441: the one exempt marker names the guide's raw-retention MEMORY figure, which is
    evidence about a payload rather than a size claim about this document. The exemption is
    pinned to a marker that must still exist, so it cannot outlive its line."""
    guide_text = (fd.REPO_ROOT / "src/larkdocio/GUIDE.md").read_text(encoding="utf-8")
    for marker in fd.GUIDE_SIZE_LITERAL_EXEMPT:
        lines = [ln for ln in guide_text.splitlines()
                 if marker in ln and fd.GUIDE_SIZE_LITERAL.search(ln)]
        assert lines, (
            f"the {marker!r} exemption no longer covers any KB literal — delete it rather "
            "than leave a standing hole in the guard")
