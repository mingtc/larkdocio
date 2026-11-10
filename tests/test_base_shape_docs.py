# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""LD-315 — the per-field-type WRITE-shape vs READ-BACK-shape section of the shipped guide.

The consumer ask this file guards: a link cell's read shape and write shape are different objects
and nothing said so, so for each writable pair they asked for two columns, the read shape and the
write shape. The read column already shipped; the write column did not, and the
asymmetry was met as a ``TypeError`` or a server refusal instead of as a table.

**What is actually held here is the authoring model, not the prose.** A shape claim is authored
in ONE place — :mod:`larkdocio.base.shape_docs` — and every landing of it in a document is a
byte-identical projection of that one author, on the permissions precedent
(``tests/test_permissions_docs.py``). So there is no third copy to keep, and no copy that can
drift: an edit inside a generated region reddens, a pair the registries gain with no row
reddens, and a row for a pair the registries dropped reddens.
"""
import pathlib
import re

import pytest
from consumer_text import dialect_hits
from guard_kit import REPO_ROOT

from larkdocio import capabilities, guide, guide_sections
from larkdocio.base import cells as base_cells
from larkdocio.base import shape_docs as sd
from larkdocio.base import write_cells
from larkdocio.base.write_vocabulary import NON_WRITABLE_PAIRS
from larkdocio.permissions import region_of

_CAPTURES = REPO_ROOT / "tests" / "captures" / "base-study" / "captures"

#: The section's own name, held HERE rather than in the shipped package: the guide's index is
#: derived from the document at call time, and a section name written down in ``src/`` is the
#: hand-kept list that derivation exists to prevent (``test_guide_sections.py``'s AC7).
SECTION_HEADING = "What a Base cell TAKES and what it HANDS BACK"
SECTION_SLUG = "what-a-base-cell-takes-and-what-it-hands-back"

#: The two documents the raw-shape table lands in. One author, two landings — and now both
#: landings are generated, so "byte-identical" is a property of the projection rather than a
#: cross-check between two hand-kept copies.
RAW_TABLE_DOCS = ("BASE.md", "src/larkdocio/GUIDE.md")


def _doc(rel):
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def _cell_shape_region():
    return region_of(guide(full=True), sd.CELL_SHAPE_REGION_BEGIN.replace(" -->", ""),
                     sd.CELL_SHAPE_REGION_END)


# --------------------------------------------------------------------------- #
# AC1 — the section ships, is reachable, and answers the ask.                   #
# --------------------------------------------------------------------------- #

def test_ac1_the_section_is_a_real_guide_section_reachable_by_HEADING_and_SLUG():
    index = {row["slug"]: row for row in guide_sections()}
    assert SECTION_SLUG in index, sorted(index)
    assert index[SECTION_SLUG]["heading"] == SECTION_HEADING
    assert guide(SECTION_HEADING) == guide(SECTION_SLUG), (
        "heading and slug must name the same section")


def test_ac1_every_writable_pair_shows_its_WRITE_shape_beside_its_READ_shape():
    """The ask itself: two columns, one row per pair, for every pair a value can be written
    to. A row that carries one shape and not the other is the gap this section closes."""
    region = _cell_shape_region()
    for pair in write_cells.WRITABLE_PAIRS:
        row = _row_for(region, pair)
        assert row, f"{pair} has no row in the shape section"
        write_shape = sd.write_shape_for(pair).shape
        assert write_shape in row, f"{pair}'s row does not carry its write shape"
        assert sd.READ_SHAPES[pair].shape in row, (
            f"{pair}'s row does not carry its read-back shape")


def _row_for(region, pair):
    prefix = f"| `{pair[0]} / {pair[1]}`"
    for line in region.splitlines():
        if line.startswith(prefix):
            return line
    return ""


@pytest.mark.parametrize("pair,write_fragment,read_fragment", [
    ((1, "Email"), '`"ada@example.com"`', '`[{"link": "mailto:…"'),
    ((1, "Text"), '`"row"`', '`[{"text": "row", "type": "text"}]`'),
    ((21, "DuplexLink"), '`["rec…"]`', '`{"link_record_ids": ["rec…"]}`'),
    ((22, "Location"), '`"103.8198,1.3521"`', '`{"location": "103.8198,1.3521"'),
    ((11, "User"), '`[{"id": <open_id>}]`', '`[{"id": …, "name": …'),
])
def test_ac1_the_five_named_asymmetries_are_each_LOCATED_in_the_section(
        pair, write_fragment, read_fragment):
    """The five the exit interview walked into, each findable by the reader who hit it."""
    row = _row_for(_cell_shape_region(), pair)
    assert write_fragment in row, f"{pair}: the write shape is not in its row"
    assert read_fragment in row, f"{pair}: the read-back shape is not in its row"


def test_ac1_each_named_asymmetry_is_CALLED_OUT_by_name_below_the_table():
    """A table answers *what shape*; the callouts answer *why the two differ*, which is the
    question the reader who was bitten actually has."""
    region = _cell_shape_region()
    below = region.split("| `1 / Text`")[-1]
    for label in ("Email", "Text", "Link", "Location", "Person"):
        assert f"**{label}" in below, f"{label} is never called out by name"


def test_ac1_a_NON_writable_pair_is_shown_as_non_writable_rather_than_omitted():
    """The table has to answer *can I write this?* — and it cannot answer it by silence."""
    region = _cell_shape_region()
    for pair in NON_WRITABLE_PAIRS:
        row = _row_for(region, pair)
        assert row, f"{pair} is omitted from the shape section instead of shown non-writable"
        assert "not writable" in row, f"{pair}'s row does not say it cannot be written"


# --------------------------------------------------------------------------- #
# AC2 — GENERATED, authored once, projected. Never hand-kept twice.             #
# --------------------------------------------------------------------------- #

def test_ac2_the_cell_shape_region_is_BYTE_IDENTICAL_to_the_projection():
    region = _cell_shape_region()
    assert region, "the guide carries no generated cell-shape region"
    assert region == sd.cell_shape_markdown(), (
        "the guide's cell-shape region has drifted from the registries — regenerate it "
        f"with:  {sd.CELL_SHAPE_REGENERATE}")


@pytest.mark.parametrize("doc_rel", RAW_TABLE_DOCS)
def test_ac2_the_raw_shape_region_is_BYTE_IDENTICAL_to_the_projection(doc_rel):
    region = region_of(_doc(doc_rel), sd.RAW_REGION_BEGIN.replace(" -->", ""),
                       sd.RAW_REGION_END)
    assert region, f"{doc_rel} carries no generated raw-shape region"
    assert region == sd.raw_shape_markdown(), (
        f"{doc_rel}'s raw-shape region has drifted from the cell registry — regenerate it "
        f"with:  {sd.RAW_REGENERATE}")


@pytest.mark.parametrize("doc_rel,begin,end", [
    ("src/larkdocio/GUIDE.md", sd.CELL_SHAPE_REGION_BEGIN, sd.CELL_SHAPE_REGION_END),
    ("src/larkdocio/GUIDE.md", sd.RAW_REGION_BEGIN, sd.RAW_REGION_END),
    ("BASE.md", sd.RAW_REGION_BEGIN, sd.RAW_REGION_END),
])
def test_ac2_each_region_has_exactly_one_begin_and_one_end_fence_IN_ORDER(doc_rel, begin, end):
    text = _doc(doc_rel)
    marker = begin.replace(" -->", "")
    assert text.count(marker) == 1, f"expected exactly one BEGIN fence in {doc_rel}"
    assert text.count(end) == 1, f"expected exactly one END fence in {doc_rel}"
    assert text.index(marker) < text.index(end), "the BEGIN fence must precede the END fence"


@pytest.mark.parametrize("doc_rel,command", [
    ("src/larkdocio/GUIDE.md", sd.CELL_SHAPE_REGENERATE),
    ("src/larkdocio/GUIDE.md", sd.RAW_REGENERATE),
    ("BASE.md", sd.RAW_REGENERATE),
])
def test_ac2_every_generated_region_carries_its_OWN_regeneration_command(doc_rel, command):
    """An instruction that lives away from the thing it regenerates goes stale. Each one of
    these sits inside the region it regenerates."""
    assert command in _doc(doc_rel)


#: A per-``(type, ui_type)`` shape-table row — ``| `1 / Text` | …``. This is the shape of the
#: thing that must never be hand-kept: a table keyed on the pair, claiming its shapes.
_PAIR_ROW = re.compile(r"^\| `\d+ / \w+`", re.MULTILINE)


@pytest.mark.parametrize("doc_rel", RAW_TABLE_DOCS)
def test_ac2_no_per_pair_shape_TABLE_is_hand_kept_anywhere_in_either_document(doc_rel):
    """The forbidden third copy, checked directly: strip every generated region out of a
    document and no per-pair shape row is left behind. Both landings of the read table and the
    new section are projections, so this is the whole of the hand-kept surface — zero.

    **What this deliberately does not police**, because it is a different kind of writing: the
    maintainer matrix's numbered register, whose findings quote a shape *inside a paragraph* as
    the evidence for what was measured. Those are keyed on the finding, not on the pair; they
    are a record of a measurement rather than a claim a reader looks a type up in; and they are
    out of scope for this work by the issue's own boundary. The failure mode this test exists
    for is a fourth copy of the *table*, and that is exactly what it catches.
    """
    outside = _doc(doc_rel)
    for begin, end in ((sd.RAW_REGION_BEGIN, sd.RAW_REGION_END),
                       (sd.CELL_SHAPE_REGION_BEGIN, sd.CELL_SHAPE_REGION_END),
                       (sd.FILTER_SHAPE_REGION_BEGIN, sd.FILTER_SHAPE_REGION_END)):
        region = region_of(outside, begin.replace(" -->", ""), end)
        if region:
            outside = outside.replace(region, "")
    leftover = _PAIR_ROW.findall(outside)
    assert leftover == [], (
        f"{doc_rel} hand-keeps per-pair shape rows outside every generated region: "
        f"{leftover} — that is the third copy this issue forbids")


def test_ac2_enrolling_a_pair_in_the_ENCODER_registry_MOVES_the_section_ON_ITS_OWN(
        monkeypatch):
    """Shown, not asserted. The section is a projection of the registries, so a pair added to
    the write registry appears in it with no edit here and no edit to the document."""
    assert write_cells.WRITABLE_PAIRS == tuple(write_cells._ENCODERS), (
        "WRITABLE_PAIRS is derived from _ENCODERS — if that stops being true this test's "
        "monkeypatch stops mirroring what an enrolment really does")
    before = sd.cell_shape_markdown()
    assert "| `99 / Invented`" not in before

    fake = (99, "Invented")
    encoders = dict(write_cells._ENCODERS)
    encoders[fake] = write_cells._e_plain_string
    monkeypatch.setattr(write_cells, "_ENCODERS", encoders)
    monkeypatch.setattr(write_cells, "WRITABLE_PAIRS", tuple(encoders))
    monkeypatch.setattr(write_cells, "CAPTURE_ANCHORS",
                        {**write_cells.CAPTURE_ANCHORS, fake: "p1-q6-01-value-writes.json"})

    after = sd.cell_shape_markdown()
    assert "| `99 / Invented`" in after, "the section did not move with the registry"
    assert sd.WRITE_SHAPES["_e_plain_string"].shape in _row_for(after, fake)


def test_ac2_a_row_the_registries_cannot_back_states_the_GAP_rather_than_inventing_a_shape(
        monkeypatch):
    """AC7's posture, exercised: an enrolled pair with no established read shape renders the
    absence in the consumer's terms. The traceability guards below are what redden."""
    fake = (99, "Invented")
    encoders = dict(write_cells._ENCODERS)
    encoders[fake] = write_cells._e_plain_string
    monkeypatch.setattr(write_cells, "_ENCODERS", encoders)
    monkeypatch.setattr(write_cells, "WRITABLE_PAIRS", tuple(encoders))
    row = _row_for(sd.cell_shape_markdown(), fake)
    assert sd.SHAPE_NOT_ESTABLISHED in row, row


# --------------------------------------------------------------------------- #
# AC3 — the pre-existing table is REGENERATED, not duplicated.                  #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("doc_rel", RAW_TABLE_DOCS)
def test_ac3_the_raw_table_still_covers_the_READ_registry_in_REGISTRY_ORDER(doc_rel):
    """Stronger than the set-equality the table shipped under: the rows are the registry's
    own order, which is what lets a row say "the same object shape" and mean the row above."""
    rows = re.findall(r"^\| `(\d+) / (\w+)` \|", _doc(doc_rel), flags=re.MULTILINE)
    documented = tuple((int(t), u) for t, u in rows)
    assert documented[:len(base_cells.PAIRS)] == tuple(base_cells.PAIRS)


def test_ac3_the_raw_table_is_the_SAME_author_as_the_new_section():
    """The whole point of the fork taken here: the old table and the new section are two
    projections of one dict, so a read shape cannot say two things."""
    raw = sd.raw_shape_markdown()
    section = sd.cell_shape_markdown()
    for pair, read in sd.READ_SHAPES.items():
        assert read.shape in raw, f"{pair}'s shape is missing from the raw table"
        assert read.shape in section, f"{pair}'s shape is missing from the new section"


def test_ac3_the_read_registry_and_the_authored_read_shapes_agree_BOTH_ways():
    assert set(sd.READ_SHAPES) == set(base_cells.PAIRS)


# --------------------------------------------------------------------------- #
# AC4 — consumer dialect only; nothing a consumer cannot act on.                #
# --------------------------------------------------------------------------- #

def test_ac4_the_new_section_carries_no_internal_dialect():
    assert dialect_hits(_cell_shape_region()) == []


def test_ac4_the_new_section_cites_no_dev_repo_PATH_at_all():
    """The provenance is real and the tests resolve it; the consumer's section states that
    without sending anyone to a path the wheel does not carry."""
    region = _cell_shape_region()
    for fragment in ("dev/", "tests/", "progress/", "requirements/"):
        assert fragment not in region, f"the section cites {fragment} — a wheel-only reader "
    # LD-699: the captures are tests/captures/…, which every clone carries — the SOURCE label.
    assert "in the source repository" in region, (
        "the section claims measured provenance, so it must say where the measurements live")


# --------------------------------------------------------------------------- #
# AC5 — every shape claim is TRACEABLE to already-landed evidence.              #
# --------------------------------------------------------------------------- #

def test_ac5_every_writable_row_resolves_an_ENCODER_and_an_ANCHOR_FILE_that_exists():
    for pair in write_cells.WRITABLE_PAIRS:
        encoder = write_cells.encoder_for(*pair)
        assert encoder is not None, f"{pair} is writable with no encoder"
        assert encoder.__name__ in sd.WRITE_SHAPES, (
            f"{pair}'s encoder {encoder.__name__} has no authored write shape")
        anchor = write_cells.CAPTURE_ANCHORS.get(pair)
        assert anchor, f"{pair} has no capture anchor — its write shape would be a guess"
        assert (_CAPTURES / anchor).exists(), f"{pair} cites a missing capture {anchor}"


def test_ac5_every_read_shape_cites_a_capture_that_EXISTS():
    for pair, read in sd.READ_SHAPES.items():
        assert read.captures, f"{pair} documents a shape with no capture behind it"
        for citation in read.captures:
            assert (_CAPTURES / pathlib.Path(citation).name).exists(), (
                f"{pair} cites a missing {citation}")


def test_ac5_the_authored_write_shapes_and_the_ENCODERS_agree_BOTH_ways():
    """A new encoder with no shape sentence reddens; a sentence for an encoder that was
    removed reddens too."""
    registered = {encoder.__name__ for encoder in write_cells._ENCODERS.values()}
    assert set(sd.WRITE_SHAPES) == registered


# --------------------------------------------------------------------------- #
# LD-441 — the shared encoder's example may not misrepresent the pair.           #
# --------------------------------------------------------------------------- #

def test_ld441_a_shared_encoder_does_not_give_three_pairs_ONE_example():
    """The table's whole contract is *"the shape you WRITE"* beside *"the shape you READ
    BACK"* — **for the same value**. Three pairs share ``_e_plain_string``, so the Phone row
    read *write* `"row"` → *read back* `"+12025550100"`, which is not a round trip of anything.

    The encoder-keyed sentence is right and stays: it is the ENCODER that decides the shape.
    What was missing is the per-pair **example**, so the override carries only that.
    """
    for pair, expected in (((13, "Phone"), '`"+12025550100"`'),
                           ((1, "Barcode"), '`"BC-9"`')):
        shape = sd.write_shape_for(pair).shape
        assert shape == expected, f"{pair} writes {shape}, which is another pair's value"


def test_ld441_the_write_example_ROUND_TRIPS_against_the_pairs_own_read_shape():
    """The property the row claims, asserted directly: for every writable pair the written
    literal must appear in the shape that pair reads back. A shared example is exactly what
    breaks this, which is why it is the check rather than a spelling assertion."""
    broken = []
    for pair in write_cells.WRITABLE_PAIRS:
        read = sd.READ_SHAPES.get(pair)
        if read is None:
            continue
        literal = sd.write_shape_for(pair).shape.strip("`").strip('"')
        # Only a concrete scalar makes this claim checkable. A write or read shape carrying
        # an ELISION (`{"link": …}`) documents a structure, not a value, and there is nothing
        # for the two columns to agree on.
        if not literal or "…" in literal or "…" in read.shape:
            continue
        if literal.startswith(("[", "{")):
            continue
        # `True` reads back as JSON `true`: the same value in two spellings, which is the
        # asymmetry that row is FOR.
        if literal.lower() not in read.shape.lower():
            broken.append((pair, literal, read.shape))
    assert not broken, (
        "a write example that does not appear in the same pair's read-back shape makes the "
        f"two columns describe different values: {broken}")


def test_ld441_the_shared_SENTENCE_is_still_shared_only_the_EXAMPLE_is_per_pair():
    """Scope of the fix, pinned: the note is the encoder's and stays one string for all three
    pairs — duplicating it is how two copies of one rule drift apart."""
    note = sd.WRITE_SHAPES["_e_plain_string"].note
    for pair in ((1, "Text"), (13, "Phone"), (1, "Barcode")):
        assert sd.write_shape_for(pair).note == note


def test_ld441_a_pair_with_no_override_still_gets_its_ENCODERS_example():
    """The default path is untouched — the override is a lookup that falls through."""
    assert sd.write_shape_for((1, "Text")).shape == sd.WRITE_SHAPES["_e_plain_string"].shape
    assert set(sd.WRITE_SHAPE_EXAMPLES) <= set(write_cells.WRITABLE_PAIRS), (
        "an override keyed to a pair no registry knows is a sentence about nothing")


def test_ac5_every_writable_pair_is_also_a_READ_registry_pair():
    assert set(write_cells.WRITABLE_PAIRS) <= set(base_cells.PAIRS)


# --------------------------------------------------------------------------- #
# AC6 — discovery guards, and the section is NOT a recipe.                      #
# --------------------------------------------------------------------------- #

def test_ac6_capabilities_carries_the_section_in_its_guide_index():
    rows = capabilities(full=True)["docs"]["guide()"]["sections"]
    assert any(row["slug"] == SECTION_SLUG for row in rows), (
        "the section is unreachable from capabilities()'s own index")


def test_ac6_the_section_carries_no_python_block_so_it_is_not_a_recipe():
    """A code block with no execution spec is the one thing not allowed. This section carries
    no code block at all, exactly as the raw-shape table above it does not."""
    assert "```python" not in guide(SECTION_SLUG)
    assert not SECTION_HEADING.startswith("Recipe:")


# --------------------------------------------------------------------------- #
# AC7 — an undocumented shape is a gap stated, never a shape invented.          #
# --------------------------------------------------------------------------- #

def test_ac7_no_pair_in_either_registry_has_an_UNESTABLISHED_shape_today():
    """The enumeration that shows there is no gap to spike: every read pair has an authored
    shape with a capture, and every writable pair has an encoder with an anchor."""
    unestablished = [pair for pair in base_cells.PAIRS if pair not in sd.READ_SHAPES]
    unanchored = [pair for pair in write_cells.WRITABLE_PAIRS
                  if pair not in write_cells.CAPTURE_ANCHORS]
    assert (unestablished, unanchored) == ([], [])
    assert sd.SHAPE_NOT_ESTABLISHED not in sd.cell_shape_markdown(), (
        "a rendered gap means a shape is being described that nothing measured")


# --------------------------------------------------------------------------- #
# LD-341 — the THIRD sibling: the per-type FILTER-CONDITION shape reference.     #
# --------------------------------------------------------------------------- #

FILTER_SECTION_HEADING = "The shape of a Base filter condition, per field type"
FILTER_SECTION_SLUG = "the-shape-of-a-base-filter-condition-per-field-type"

#: The four comparison operators Lark lists but this library does not ship. A row that presented
#: one as working would be the guess the whole table exists to refuse.
COMPARISON_OPERATORS = ("isGreater", "isGreaterEqual", "isLess", "isLessEqual")


def _filter_region():
    return region_of(guide(full=True), sd.FILTER_SHAPE_REGION_BEGIN.replace(" -->", ""),
                     sd.FILTER_SHAPE_REGION_END)


def test_filter_the_section_is_a_real_guide_section_reachable_by_HEADING_and_SLUG():
    index = {row["slug"]: row for row in guide_sections()}
    assert FILTER_SECTION_SLUG in index, sorted(index)
    assert index[FILTER_SECTION_SLUG]["heading"] == FILTER_SECTION_HEADING
    assert guide(FILTER_SECTION_HEADING) == guide(FILTER_SECTION_SLUG)


def test_filter_capabilities_carries_the_section_in_its_guide_index():
    rows = capabilities(full=True)["docs"]["guide()"]["sections"]
    assert any(row["slug"] == FILTER_SECTION_SLUG for row in rows), (
        "the filter-shape section is unreachable from capabilities()'s own index")


def test_filter_region_is_BYTE_IDENTICAL_to_the_projection():
    region = _filter_region()
    assert region, "the guide carries no generated filter-shape region"
    assert region == sd.filter_shape_markdown(), (
        "the guide's filter-shape region has drifted from view_filters — regenerate it "
        f"with:  {sd.FILTER_SHAPE_REGENERATE}")


def test_filter_region_has_exactly_one_begin_one_end_and_its_regenerate_command():
    text = _doc("src/larkdocio/GUIDE.md")
    marker = sd.FILTER_SHAPE_REGION_BEGIN.replace(" -->", "")
    assert text.count(marker) == 1
    assert text.count(sd.FILTER_SHAPE_REGION_END) == 1
    assert text.index(marker) < text.index(sd.FILTER_SHAPE_REGION_END)
    assert sd.FILTER_SHAPE_REGENERATE in text


def test_filter_every_documented_pair_has_a_ROW_and_an_unknown_one_says_so():
    """Every pair the sibling tables carry gets a filter row too — a present `shape not
    established` row is an answer, an absent one would read as an oversight (AC2 iii)."""
    region = _filter_region()
    for pair in sd._documented_pairs():
        row = _row_for(region, pair)
        assert row, f"{pair} has no filter row"
        if pair not in sd.FILTER_SHAPES:
            assert sd.SHAPE_NOT_ESTABLISHED in row, (
                f"{pair} has no evidence but its row does not say `shape not established`")


def test_filter_every_evidence_backed_row_carries_a_KNOWN_verification_label():
    """LD-403 made the label ROUTE-SCOPED: each half carries its own, and both land in the row."""
    for pair, shape in sd.FILTER_SHAPES.items():
        for route in (shape.search, shape.view):
            assert route.evidence in sd.FILTER_EVIDENCE_CLASSES, (
                f"{pair} carries an unknown evidence label {route.evidence!r}")
            assert route.evidence in _row_for(_filter_region(), pair)


def test_filter_a_captured_row_cites_a_capture_FILE_that_EXISTS():
    """A `captured` HALF is only as good as the file behind it — the same bar the read table
    holds. A `measured` / `consumer-observed` / `unmeasured` half carries no capture."""
    for pair, shape in sd.FILTER_SHAPES.items():
        for route in (shape.search, shape.view):
            if route.evidence == "captured":
                assert route.captures, f"{pair} is labelled captured but cites no capture"
                for name in route.captures:
                    assert (_CAPTURES / name).exists(), f"{pair} cites a missing capture {name}"
            else:
                assert route.captures == (), (
                    f"{pair} is {route.evidence!r} yet carries capture files, which overclaims")


def test_filter_the_CHECKBOX_row_states_the_MEASURED_shape_PER_ROUTE():
    """**Transformed, not deleted (LD-403).** The reason this row once shipped a weaker label
    stands: the consumer's `("is", (True,))` was a report, not a capture, and the table said so.
    What is superseded is the conclusion — the view half has now been probed, the two routes
    turned out to take DIFFERENT spellings, and each half carries its own capture."""
    row = _row_for(_filter_region(), (7, "Checkbox"))
    shape = sd.FILTER_SHAPES[(7, "Checkbox")]
    assert '("is", (True,))' in row, row
    assert shape.search.evidence == "captured" and shape.view.evidence == "captured"
    assert shape.search.value != shape.view.value, (
        "the two routes were measured to take different spellings — a row that gave them one "
        "sentence is the defect LD-403 fixed")
    assert "[true]" in shape.view.value and "1254001" in shape.view.value


def test_filter_the_SELECT_rows_state_the_two_routes_as_DIFFERENT_answers():
    """AC1: name for the search route, id for the view route — the split LD-318 measured."""
    for pair in ((3, "SingleSelect"), (4, "MultiSelect")):
        shape = sd.FILTER_SHAPES[pair]
        assert "name" in shape.search.value
        assert "id" in shape.view.value
        assert shape.search.value != shape.view.value


def test_filter_no_COMPARISON_operator_is_presented_as_working():
    """AC2 (ii): the four comparison operators appear ONLY inside Lark's own quoted enum, with
    the `not shipped` caveat — never as a shipped operator the table implies works."""
    region = _filter_region()
    assert "not shipped and are not implied" in region
    assert "1254018" in region
    enum = sd.SERVER_VIEW_OPERATOR_ENUM
    assert enum in region
    outside_enum = region.replace(enum, "")
    for op in COMPARISON_OPERATORS:
        assert op not in outside_enum, (
            f"{op} appears outside Lark's quoted enum — the table implies it works")


def test_filter_the_shipped_operator_vocabulary_is_PROJECTED_from_view_filters():
    """The operator set, valueless pair and conjunctions are READ from view_filters, not
    re-spelled here — so the reference cannot claim an operator the serialiser does not ship."""
    region = _filter_region()
    for op in sd.FILTER_OPERATORS:
        assert f"`{op}`" in region, f"the shipped operator {op} is missing from the reference"
    for op in sd.VALUELESS_OPERATORS:
        assert f"`{op}`" in region
    for conj in sd.CONJUNCTIONS:
        assert f"`{conj}`" in region


def test_filter_region_carries_no_internal_dialect_and_no_dev_repo_PATH():
    region = _filter_region()
    assert dialect_hits(region) == []
    for fragment in ("dev/", "tests/", "progress/", "requirements/", "LD-"):
        assert fragment not in region, f"the filter section cites {fragment} — a wheel-only reader cannot open it"
    # LD-699: the captures are tests/captures/…, which every clone carries — the SOURCE label.
    assert "in the source repository" in region, "the section claims provenance, so it must say where"


def test_filter_the_section_carries_no_python_block_so_it_is_not_a_recipe():
    assert "```python" not in guide(FILTER_SECTION_SLUG)
