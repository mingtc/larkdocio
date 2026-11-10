"""LD-570 — the Base read path in the shipped guide: the read-only sentence's SUBJECT, the
`retain_raw` pointer on the read path, the three-way render ambiguity, and the cell-shapes
legend.

Every assertion here is a **projection check** rather than a spelling check. The four facts the
guide now states are authored in code — the Base write surfaces and their `opt_in` in
:func:`larkdocio.capabilities`, the *"costs no extra API call, only memory"* sentence in
:class:`larkdocio.base.model.SnapshotRecord`'s ``RawNotRetained`` message, the render ambiguity in
:mod:`larkdocio.base.cells` (measured here by rendering all three cells), and the cell-shapes
column encoding in :mod:`larkdocio.base.shape_docs` — so each test asserts **both** sides and
reddens whichever one moves.

The section headings are held HERE, not in ``src/``: the guide's index is derived from the
document at call time, and a heading list written into the package is the hand-kept copy that
derivation exists to prevent.
"""
import re

import pytest

import private_tree  # noqa: E402  (LD-691)
from guard_kit import REPO_ROOT
from larkdocio import capabilities, guide, guide_sections
from larkdocio.base import cells as base_cells
from larkdocio.base import shape_docs as sd
from larkdocio.base.cells import MEASURED_MENTION_TYPES, MEASURED_SEGMENT_KINDS, render_cell
from larkdocio.base.model import RawNotRetained, SnapshotRecord
from larkdocio.base.table import FieldSpec

READ_RECIPE = "Recipe: read a Base to Markdown"
READ_RECIPE_SLUG = "recipe-read-a-base-to-markdown"
SHAPES_SECTION = "What a Base cell TAKES and what it HANDS BACK"

#: The sentence whose unqualified subject put a false capability claim into a consumer's
#: design-review document. It may never come back.
UNQUALIFIED = "**This surface is read-only, end to end.**"

#: The two Base WRITE surface ids the corrected sentence must name. Held here as the
#: *expectation*; every test below joins it against ``capabilities()`` rather than trusting it.
BASE_WRITE_SURFACE_IDS = ("base-write", "base-schema-write")


def _recipe() -> str:
    return guide(READ_RECIPE)


def _flat(text: str) -> str:
    """The prose with its hard line wrapping collapsed — the guide wraps at ~94 columns, so a
    sentence check that keeps the newlines is testing the wrap, not the sentence."""
    return " ".join(text.split())


def _base_write_surfaces() -> dict:
    full = capabilities(full=True)
    return {sid: s for sid, s in full["surfaces"].items()
            if s.get("mode") == "write" and sid.startswith("base")}


def _link_paragraphs() -> str:
    """The *"How much of a link survives the Markdown"* run — the paragraph AC2 augments,
    from its opening bold lead to the next bold lead after *"Where that guarantee stops"*."""
    body = _recipe()
    start = body.index("How much of a link survives the Markdown")
    tail = body.index("**A view is not a projection.**", start)
    return body[start:tail]


# --------------------------------------------------------------------------- #
# AC1 — the read-only sentence names its SUBJECT, names the two surface ids,    #
#       states NO count, and points onward by heading.                          #
# --------------------------------------------------------------------------- #

def test_ac1_the_unqualified_sentence_is_gone_from_the_shipped_guide():
    assert UNQUALIFIED not in guide(full=True), (
        "the sentence whose ambiguous subject was read as *Bases are read-only* is back in "
        "the shipped guide")


def test_ac1_the_read_only_claim_names_its_subject():
    recipe = _recipe()
    hits = [ln for ln in recipe.splitlines() if "read-only, end to end" in ln]
    assert len(hits) == 1, hits
    assert "read surface" in hits[0].lower(), (
        f"the read-only claim still does not say WHAT is read-only: {hits[0]!r}")


def test_ac1_the_recipe_names_both_base_write_surface_ids_and_capabilities_agrees():
    """Bidirectional: every Base write surface `capabilities()` reports is named on the read
    path, and every id named on the read path is a surface `capabilities()` reports."""
    recipe = _recipe()
    truth = set(_base_write_surfaces())
    assert truth == set(BASE_WRITE_SURFACE_IDS), (
        f"the Base write surfaces have changed to {sorted(truth)} — the read recipe's onward "
        "pointer must be re-derived, not left standing")
    for sid in truth:
        assert f"`{sid}`" in recipe, f"the read recipe does not name the write surface {sid!r}"
    for named in re.findall(r"`(base(?:-[a-z]+)+)`", recipe):
        if named.endswith("write"):
            assert named in truth, f"the recipe names {named!r}, which is not a live surface"


def test_ac1_the_recipe_says_base_WRITE_ships():
    recipe = _recipe()
    assert "Base WRITE ships**" in _flat(recipe), (
        "the corrected sentence does not point onward to the fact that refutes the "
        "misreading: Base write ships")


def test_ac1_the_on_by_default_claim_projects_opt_in():
    """The recipe says both write surfaces are on by default; `opt_in` is what makes that
    true. Flip either surface to opt-in and this reddens."""
    surfaces = _base_write_surfaces()
    assert all(s.get("opt_in") is False for s in surfaces.values()), surfaces
    assert "on by default" in _recipe()


def test_ac1_the_recipe_states_NO_count_of_base_write_operations():
    """The derivation is two-valued — 26 rows, or 21 ``kind == 'operation'`` rows, which is
    what the guide's own guarded capability matrix enumerates. A bare count in the prose would
    contradict that matrix with no guard reddening, so no count is stated at all."""
    surfaces = _base_write_surfaces()
    all_rows = sum(len(s["operations"]) for s in surfaces.values())
    op_rows = sum(1 for s in surfaces.values()
                  for op in s["operations"] if op.get("kind") == "operation")
    assert all_rows != op_rows, (
        "the two derivations now agree, so the no-count rule may be revisited deliberately — "
        "not silently")
    recipe = _recipe()
    for count in (all_rows, op_rows):
        assert not re.search(rf"\b{count}\b", recipe), (
            f"the read recipe states the count {count} — the derivation is two-valued "
            f"({all_rows} rows vs {op_rows} operation rows) and the guide's own guarded "
            "matrix carries the enumeration")


@pytest.mark.parametrize("heading", (
    "Capability matrix",
    "Recipe: the Base write handshake",
    "Recipe: create, rename and copy a Base (the structural handshake)",
))
def test_ac1_every_onward_pointer_is_a_LIVE_section_heading(heading):
    """Pointed onward by heading, never by line number (``lookup-tables.md``): a heading
    survives an edit above it, and this test reddens if one is renamed."""
    assert heading in {row["heading"] for row in guide_sections()}
    assert f"*{heading}*" in _recipe(), (
        f"the read recipe does not point onward to § {heading!r}")


def test_ac1_no_onward_pointer_is_a_line_number():
    assert not re.search(r"GUIDE\.md:\d+", _recipe())


# --------------------------------------------------------------------------- #
# AC2 — `retain_raw` is named on the READ path, by AUGMENTING the paragraph     #
#       that is already there. One authoring site, no second paraphrase.        #
# --------------------------------------------------------------------------- #

def test_ac2_the_read_recipe_names_retain_raw_at_all():
    assert "retain_raw" in _recipe(), (
        "the Base read recipe still never names `retain_raw`, so a caller solves the problem "
        "with a hand-rolled regex over the Markdown instead")


def test_ac2_the_retain_raw_call_is_read_base_never_read_base_markdown():
    recipe = _recipe()
    assert "`read_base(url, retain_raw=True)`" in recipe
    assert "read_base_markdown(url, retain_raw=True)" not in recipe, (
        "`read_base_markdown` has no `retain_raw` parameter — the parameter is on `read_base` "
        "(base/table.py)")


def test_ac2_read_base_markdown_really_has_no_retain_raw_parameter():
    """The prose above is only correct because of this; assert the signature, do not assume."""
    import inspect

    from larkdocio.base import read_base, read_base_markdown
    assert "retain_raw" not in inspect.signature(read_base_markdown).parameters
    assert "retain_raw" in inspect.signature(read_base).parameters


def test_ac2_every_retain_raw_mention_lives_in_the_ONE_augmented_paragraph():
    """The one-authoring-site discipline: a second paraphrase elsewhere in the recipe is the
    duplicate-authoring defect this wave exists to remove."""
    recipe, para = _recipe(), _link_paragraphs()
    assert recipe.count("retain_raw") == para.count("retain_raw") > 0, (
        "a second `retain_raw` paraphrase has appeared outside the augmented "
        "*How much of a link survives the Markdown* paragraph")


def test_ac2_the_cost_sentence_is_the_SHIPPED_one_not_a_new_claim():
    """Quote the sentence the library itself speaks when raw was not retained — do not invent
    a different cost claim. Projected from the live refusal message, not retyped from prose."""
    row = SnapshotRecord(record_id="rec1", cells=(("T", "x"),), raw_fields=None)
    with pytest.raises(RawNotRetained) as excinfo:
        row.raw("T")
    spoken = "it costs no extra API call, only memory"
    assert spoken in str(excinfo.value)
    assert spoken in _flat(_link_paragraphs())


def test_ac2_the_recipe_names_raw_fields_as_the_route():
    assert "`raw_fields`" in _flat(_link_paragraphs())


def test_ac2_no_markdown_parsing_heuristic_is_PUBLISHED():
    """F9: publishing the `[label](url)` regex would enshrine the exact hand-rolled parse two
    consumer legs wrote — wrong for any link whose author typed a label."""
    para = _flat(_link_paragraphs())
    for banned in ("re.match", "re.compile", "re.findall", r"\[([^]]", "regex over"):
        assert banned not in para, f"{banned!r} publishes a Markdown-parsing heuristic"
    assert "never a parse of the rendered Markdown**" in para, (
        "the paragraph names `raw_fields` without saying that parsing the Markdown is the "
        "wrong route")


# --------------------------------------------------------------------------- #
# AC3 — the three-way ambiguity, stated precisely, where the projection is made #
# --------------------------------------------------------------------------- #

def _render(segments, field) -> str:
    return render_cell(segments, field)


_TEXT = FieldSpec(field_name="T", type=1, ui_type="Text")
_URL = FieldSpec(field_name="U", type=15, ui_type="Url")
_HREF = "https://example.larksuite.com/docx/doccnDEADBEEF"


def test_ac3_the_three_way_ambiguity_is_MEASURED_not_asserted():
    """The claim the guide now makes, proved offline: an UNLABELLED `Url` cell and an
    autolinked bare-URL text cell are byte-identical; a LABELLED `Url` cell is byte-identical
    to a mention chip instead. All three shapes are `[text](url)`."""
    autolinked = _render([{"text": _HREF, "type": "text"}], _TEXT)
    unlabelled = _render([{"text": _HREF, "link": _HREF, "type": "url"}], _URL)
    labelled = _render([{"text": "Design review", "link": _HREF, "type": "url"}], _URL)
    chip = _render([{"text": "Design review", "link": _HREF, "type": "mention",
                     "mentionType": MEASURED_MENTION_TYPES[0]}], _TEXT)
    assert autolinked == unlabelled == f"[{_HREF}]({_HREF})"
    assert labelled == chip == f"[Design review]({_HREF})"


def test_ac3_retain_raw_really_keeps_the_three_apart():
    """The remedy the guide points at, proved: the wire body distinguishes what the Markdown
    cannot. ``raw_fields`` is the record's ``fields`` body, untouched."""
    raw = {"T": [{"text": _HREF, "type": "text"}],
           "U": [{"text": "Design review", "link": _HREF, "type": "url"}],
           "M": [{"text": "Design review", "link": _HREF, "type": "mention",
                  "mentionType": "Docx"}]}
    cells = (("T", "x"), ("U", "y"), ("M", "z"))
    row = SnapshotRecord(record_id="rec1", cells=cells, raw_fields=raw)
    assert {row.raw(name)[0]["type"] for name in ("T", "U", "M")} == {"text", "url", "mention"}
    assert row.raw("M")[0]["mentionType"] in MEASURED_MENTION_TYPES


def test_ac3_the_sentence_states_the_ambiguity_precisely():
    para = _flat(_link_paragraphs())
    for fragment in (
        "autolinked",
        "mention chip",
        "`[text](url)`",
        "neither the cell's type nor the segment's kind is recoverable",
        "`read_base(url, retain_raw=True)` is the view that keeps them apart",
    ):
        assert fragment in para, f"the three-way sentence is missing {fragment!r}"


def test_ac3_the_loose_render_identically_claim_is_NOT_shipped():
    """"a `Url` cell and a text cell render identically" is true only for the UNLABELLED
    case — shipping the loose version re-commits the defect this issue fixes."""
    para = _flat(_link_paragraphs())
    assert "unlabelled" in para.lower(), (
        "the sentence does not scope the identical-render claim to the unlabelled case")


def test_ac3_the_three_named_kinds_are_the_MEASURED_vocabulary():
    """AC5: a measured-vocabulary claim is projected from the constant, not retyped."""
    para = _flat(_link_paragraphs())
    for kind in MEASURED_SEGMENT_KINDS:
        assert f"`{kind}`" in para or kind in para, f"segment kind {kind!r} goes unnamed"
    assert base_cells.MEASURED_SEGMENT_KINDS == ("text", "url", "mention")


def test_ac3_the_dedupe_recipe_is_CROSS_REFERENCED_not_paraphrased():
    assert "Recipe: compare Base rows on the raw values" in _flat(_link_paragraphs())


# --------------------------------------------------------------------------- #
# AC4 — the cell-shapes legend, in the PROSE ABOVE the generated region.        #
# --------------------------------------------------------------------------- #

def _shapes_prose() -> str:
    """The section's prose, up to (never including) the generated region's marker."""
    body = guide(SHAPES_SECTION)
    return body[:body.index(sd.CELL_SHAPE_REGION_BEGIN.replace(" -->", ""))]


def test_ac4_the_legend_explains_every_part_of_the_Field_type_column():
    prose = _shapes_prose()
    for part in ("`type`", "`ui_type`", "field picker"):
        assert part in _flat(prose), f"the legend never explains {part}"


def test_ac4_the_legend_example_is_DERIVED_from_the_generated_table():
    """The legend's worked example is the table's own first row, so a registry reordering
    reddens here instead of leaving a legend describing a row that moved."""
    region = sd.cell_shape_markdown()
    first = [ln for ln in region.splitlines()
             if ln.startswith("| `") and " · " in ln][0]
    encoded = first.split("|")[1].strip()          # e.g. "`1 / Text` · Text"
    assert encoded in _flat(_shapes_prose()), (
        f"the legend's example does not match the table's first row cell {encoded!r}")


def test_ac4_the_legend_is_OUTSIDE_the_byte_pinned_generated_region():
    """The region stays byte-identical to its generator: the legend was typed in the prose
    above the marker, and `shape_docs.py` was not edited."""
    from larkdocio.permissions import region_of
    region = region_of(guide(full=True), sd.CELL_SHAPE_REGION_BEGIN.replace(" -->", ""),
                       sd.CELL_SHAPE_REGION_END)
    assert region == sd.cell_shape_markdown()
    assert "field picker" not in region


# --------------------------------------------------------------------------- #
# AC6/AC7 — the notes deliverable, and the guards that bite silent mistakes.    #
# --------------------------------------------------------------------------- #

def _root(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def _section(text: str, header: str) -> str:
    start = text.index(header)
    nxt = text.find("\n## ", start + len(header))
    return text[start:] if nxt == -1 else text[start:nxt]


@pytest.mark.parametrize("rel", (pytest.param("CHANGELOG.md", marks=private_tree.internal_log), "RELEASE_NOTES.md"))
def test_ac6_the_notes_land_in_the_open_1_41_0_section(rel):
    section = _section(_root(rel), "## [1.41.0]")
    assert "read-only, end to end" in section, (
        f"{rel}'s [1.41.0] section does not call out the corrected read-only sentence")
    assert "retain_raw" in section


def test_ac6_the_release_notes_state_no_behaviour_change():
    section = _section(_root("RELEASE_NOTES.md"), "## [1.41.0]")
    assert "no behaviour change" in section.lower()


def test_ac7_no_internal_dialect_reaches_the_consumer_corpus():
    """The dialect grep's own tokens, checked at the two files this issue edits."""
    for rel in ("src/larkdocio/GUIDE.md", "RELEASE_NOTES.md"):
        text = _root(rel)
        for token in ("LD-570", " D4 ", "AC3"):
            assert token not in text, f"{token!r} leaked into {rel}"


def test_ac7_no_forward_looking_phrase_was_added_to_the_read_recipe():
    """The absence-claims census pins `guide()` at exactly two forward-looking phrases."""
    recipe = _recipe()
    for phrase in ("not yet", "future release", "does not ship today", "will ship"):
        assert phrase not in recipe.lower(), f"{phrase!r} would move the absence census"


def test_ac7_no_new_KB_figure_and_no_new_level_3_heading_in_the_read_recipe():
    recipe = _recipe()
    assert not re.search(r"\b\d{2,4}\s?KB\b", recipe)
    assert not [ln for ln in recipe.splitlines()[1:] if ln.startswith("### ")]
